# Không dùng lại key sai mục đích — Phân tách mục đích sử dụng khóa mật mã

## 1. Vì sao không được dùng lại key sai mục đích?

**Không dùng lại key sai mục đích** (*avoid cross-purpose key reuse*) là nguyên tắc: **mỗi vật liệu khóa mật mã phải được tạo, gán và sử dụng đúng thuật toán, giao thức, dữ liệu, vai trò và phạm vi đã được phê duyệt**. Không lấy một khóa đã dùng cho nhiệm vụ này đem sang nhiệm vụ khác chỉ vì chúng cùng cần “32 byte bí mật” hoặc cùng thư viện hỗ trợ.

Ví dụ, một hệ thống Billing có:

- **DEK** AES-256-GCM dùng để mã hóa hóa đơn.
- **KEK** dùng để bọc DEK.
- **HMAC key** xác thực webhook đối tác.
- **Private signing key** dùng ký hóa đơn phát hành.
- **Key agreement private key** dùng thiết lập shared secret với một peer theo giao thức.

Nếu nhóm phát triển dùng cùng một chuỗi 32 byte `BILLING_SECRET` cho **DEK, KEK và HMAC**, ba chức năng này trở thành các mặt phụ thuộc của **một bí mật**. Khi khóa bị lộ ở webhook, rủi ro có thể lan sang dữ liệu mã hóa và đường bọc khóa; việc xoay chỉ một nhiệm vụ cũng rất khó.

Tuy nhiên, **không phải mọi việc dùng một khóa nhiều lần đều sai**:

- Một **AES-GCM DEK** có thể mã hóa **nhiều thông điệp trong cùng purpose** khi **nonce không bị lặp dưới cùng key**, giới hạn sử dụng và cryptoperiod được tuân thủ.
- **Cùng AES key** có thể được dùng để **encrypt và decrypt cùng bộ dữ liệu** vì đây là tính chất bình thường của mật mã đối xứng, dù quyền của writer và reader phải tách phù hợp.
- **Một KEK** có thể bọc nhiều DEK theo giới hạn và chính sách đã được thiết kế; không bắt buộc mỗi lần `Wrap` đều có một KEK mới.
- **Một public verification key** có thể dùng verify nhiều chữ ký của cùng signing key pair trong phạm vi được phê duyệt.

Điểm cần ngăn là **sai mục đích** (*cross-purpose*), **sai phạm vi** (*cross-tenant, cross-environment, cross-protocol*) và **sai điều kiện sử dụng** (đã quá hạn, đã deactivated/compromised, không đúng key usage).

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài thuộc chương **Key use (Sử dụng khóa)** và liên hệ chặt với vòng đời **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**, mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, phân quyền và kiểm toán.

> **Thông điệp chính:** Không đánh giá “khóa có đủ số bit không?” một cách tách biệt. Hãy hỏi **khóa được tạo để làm gì, ai được dùng, dùng bằng thuật toán nào, ở đâu, đến khi nào và điều gì xảy ra khi khóa bị lộ**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **key purpose**, **key usage**, **operation**, **scope** và **key reuse hợp lệ**.
2. Giải thích nguy cơ của việc dùng chung vật liệu cho **AES, HMAC, key wrapping, signing và agreement**.
3. Phân biệt **sinh key độc lập bằng CSPRNG** và **dẫn xuất subkey qua KDF có domain separation**.
4. Thiết kế phân tách **DEK/KEK, tenant, environment, protocol direction và cryptoperiod**.
5. Sử dụng **KMS/HSM/PKCS#11, IAM và policy gate** để ngăn thao tác sai mục đích.
6. Viết ví dụ Java 11 tạo key riêng, kiểm tra purpose/role và minh họa HKDF.
7. Thiết kế negative tests, audit, rotation và ứng cứu khi phát hiện key reuse sai.

## 2. Phân biệt key, key ID, purpose và operation

Bốn khái niệm thường bị trộn lẫn:

| Khái niệm | Câu hỏi | Ví dụ | Điều không được suy ra |
| --- | --- | --- | --- |
| **Key material** | Chuỗi bit bí mật/khóa bất đối xứng thực sự là gì? | Raw AES secret, private EC scalar | Hai tên khác nhau chưa chắc khác material |
| **Key ID / alias / version** | Hệ thống tham chiếu khóa bằng tên nào? | `billing-dek-v3` | Đổi tên không đổi material |
| **Key purpose** | Khóa bảo vệ tài sản hoặc giao thức nào? | `INVOICE_DATA_ENCRYPTION` | Purpose string không tự chặn API |
| **Key usage / operation** | Phép toán gì được thực hiện? | `Encrypt`, `Decrypt`, `Wrap`, `Sign` | API có operation không có nghĩa principal được phép |
| **Scope** | Tenant, environment, dataset, peer, direction nào? | `tenant-a/prod/records` | Trùng thuật toán không cho phép dùng xuyên scope |
| **Cryptoperiod / state** | Khóa còn hiệu lực cho new-use không? | `ACTIVE`, `DEACTIVATED` | Deactivated không nhất thiết đã hủy material |

Một key record tốt cần thể hiện **mục đích trước khi sinh**, rồi ràng buộc identity, thuật toán, chính sách và trạng thái.

### Sai lầm: đổi tên khóa là đã tách mục đích

~~~text
alias: billing-aes-dek   ──┐
                          ├──> raw bytes X
alias: webhook-hmac-key ──┘
~~~

Dù có hai alias, **vật liệu vẫn là X**. Nếu `webhook-hmac-key` bị lộ, kẻ tấn công có thể có raw bytes được dùng cho DEK.

Một **key handle khác** cũng chưa đủ chứng minh tách biệt. Có thể hai handle tham chiếu một material import giống nhau, hoặc hai key version ở một logical resource cần được xác định theo provider.

## 3. Khi nào key reuse là bình thường, khi nào là sai?

### Sử dụng bình thường trong cùng purpose

| Tình huống | Có thể chấp nhận? | Điều kiện |
| --- | --- | --- |
| Cùng DEK AES-GCM encrypt nhiều record | **Có** | Nonce uniqueness và usage limits theo key; đúng scope và cryptoperiod |
| Cùng AES key encrypt và decrypt cùng dataset | **Có** | Quyền của principal, data access, nonce/AAD/tag và trạng thái phù hợp |
| Cùng KEK bọc nhiều DEK | **Có** | Wrapping mechanism chuẩn, scope, giới hạn và IAM |
| Cùng signing key ký nhiều invoice | **Có** | Đúng purpose, approvals, algorithm/nonce nếu cần, cryptoperiod |
| Cùng HMAC key xác thực nhiều webhook của cùng đối tác | **Có** | Giao thức, anti-replay, message serialization, retention và rotation |
| Public key verify nhiều chữ ký cùng domain | **Có** | Trusted key/certificate và policy xác minh |
| Cùng key hash/MAC làm cả DEK và webhook HMAC | **Không nên** | Cần material riêng hoặc subkey được tách miền |
| Cùng private EC key cho ECDSA và ECDH không phân tích | **Không nên** | Tách key pair và đúng giao thức |
| Cùng AES key cho prod và staging | **Không nên** | Tách môi trường/trust boundary |
| Cùng raw encryption key cho các tenant cần cách ly | **Không nên khi yêu cầu cô lập** | Material/derivation domain/permission theo tenant |
| Dùng key đã `COMPROMISED` tiếp cho new encrypt | **Không** | Thay key và incident response |

**Key separation không đồng nghĩa sinh một key mới cho mọi lời gọi API.** Nhiều thuật toán được thiết kế để sử dụng một key qua nhiều thông điệp trong giới hạn được quy định. Mục tiêu là **đúng ranh giới mật mã và quản trị**, không tạo càng nhiều key càng tốt.

### “Dùng để decrypt” có phải sai mục đích của encryption key?

Không. Với **AES**, **encrypt và decrypt** là hai chiều của cùng bài toán bảo vệ dữ liệu. Hệ thống có thể quy định **writer chỉ Encrypt**, **reader có Decrypt**, nhưng đó là phân quyền operation. Cùng DEK về mặt toán học vẫn giải mã được ciphertext. **Không được mô tả AES key là không thể decrypt chỉ vì key usage được đặt “encrypt-only”.**

## 4. Vì sao tái sử dụng vật liệu giữa giao thức nguy hiểm?

Một thiết kế “mỗi thuật toán riêng đã an toàn” không có nghĩa **kết hợp các thuật toán với cùng secret** là an toàn. Mỗi cơ chế bảo mật dựa trên một tập giả định:

- Thuật toán giả định **key được sinh với entropy và định dạng phù hợp**.
- Giao thức giả định **attacker được phép gọi một số oracle**, không nhất thiết có oracle của thuật toán khác với cùng key.
- Phân tích bảo mật có thể giả định **key độc lập giữa vai trò, session hoặc hướng truyền**.
- IAM/key usage có thể giả định **chỉ một nhóm service** cần dùng key.
- Kế hoạch rotation giả định **một key phục vụ một domain rủi ro có thể kiểm kê**.

Việc chia sẻ một raw secret giữa nhiều nhiệm vụ có thể tạo **cross-protocol interactions**, mở đường lạm dụng ngoài phạm vi chứng minh bảo mật, đồng thời tăng **blast radius** khi secret bị lộ.

### Nguy cơ thường thấy nhất không cần tấn công mật mã phức tạp

Giả sử webhook service phải phân phối HMAC key cho một đối tác. Nếu **HMAC secret chính là AES DEK** của Billing, chỉ cần phía đối tác giữ secret không an toàn là dữ liệu mã hóa của doanh nghiệp bị đặt vào rủi ro. Không cần phá AES hay HMAC.

Do vậy, **tách key material** vừa là kiểm soát mật mã vừa là **giới hạn số chủ thể được tiếp cận bí mật**.

### Rủi ro tăng theo đường phân phối

~~~mermaid
flowchart TD
    Shared[Một secret dùng cho 4 purpose] --> AES[AES-GCM data encryption]
    Shared --> MAC[Webhook HMAC]
    Shared --> Wrap[Wrap data keys]
    Shared --> Auth[Token/session auth]
    MAC --> Partner[Đối tác cũng biết secret]
    Partner --> Risk[Compromise đối tác có thể ảnh hưởng nhiều domain]
    Risk --> Rotation[Phải đánh giá rotation cho tất cả purpose]
~~~

## 5. Không dùng AES DEK làm HMAC key

Một **AES key** và một **HMAC key** đều có thể là chuỗi bytes bí mật nhưng **purpose và mô hình sử dụng khác**.

### Phản ví dụ

~~~java
// PHẢN VÍ DỤ — không dùng trong production:
byte[] sameSecret = obtainSecretForDataEncryption();
javax.crypto.SecretKey aes =
        new javax.crypto.spec.SecretKeySpec(sameSecret, "AES");
javax.crypto.SecretKey hmac =
        new javax.crypto.spec.SecretKeySpec(sameSecret, "HmacSHA256");
~~~

Hai `SecretKeySpec` được gắn nhãn thuật toán khác nhau nhưng **chứa cùng raw bytes**. Đổi tên thuật toán không tạo tính độc lập mật mã.

### Thiết kế tốt hơn

~~~text
DEK = CSPRNG.Generate(256 bits)             # dùng AES-256-GCM
MAC_KEY = CSPRNG.Generate(256 bits)         # dùng HMAC-SHA-256

Hoặc, trong một key schedule được phân tích:
PRK = HKDF-Extract(salt, master_secret)
DEK = HKDF-Expand(PRK, info="billing/v1/aes-gcm", L=32)
MAC_KEY = HKDF-Expand(PRK, info="billing/v1/webhook-hmac", L=32)
~~~

**Hai cách có giả định compromise khác nhau:** nếu master bị lộ, **mọi subkey cùng master** có thể bị tính lại. Sinh các khóa riêng và bảo vệ ở những boundary độc lập có thể giới hạn ảnh hưởng tốt hơn.

### AES-GCM đã có authentication tag, cần HMAC nữa không?

AES-GCM là **AEAD**, vừa bảo vệ bí mật vừa xác thực ciphertext/AAD theo security model của nó. Không mặc định cần gắn thêm HMAC ngoài GCM.

Nếu hệ thống **có giao thức HMAC độc lập** (chẳng hạn webhook), dùng **HMAC key riêng**. Không coi GCM authentication tag là chữ ký số có khả năng chứng minh danh tính một signer riêng biệt: các bên biết cùng symmetric key có thể tạo tag hợp lệ.

## 6. Không dùng DEK làm KEK và ngược lại

Trong **envelope encryption**:

- **DEK** (*Data Encryption Key*) trực tiếp mã hóa dữ liệu bằng AES-GCM hoặc AEAD phù hợp.
- **KEK** (*Key Encryption Key*) bảo vệ DEK thông qua key wrapping hoặc provider API tương ứng.

~~~mermaid
flowchart TD
    Plain[Plaintext record] --> AEAD[AES-GCM Encrypt/Decrypt]
    DEK[DEK: DATA_ENCRYPTION] --> AEAD
    AEAD --> Store[(Ciphertext + nonce + tag + AAD context)]
    DEK --> Wrapped[Wrapped DEK]
    KEK[KEK: KEY_WRAPPING trong KMS/HSM] --> Wrapped
    Wrapped --> Store
    Inv[Key inventory: purpose, IDs, versions, owner] --> DEK
    Inv --> KEK
~~~

### Vì sao phải tách?

1. **Phạm vi:** Một KEK có thể bảo vệ rất nhiều DEK; lộ KEK có blast radius lớn.
2. **Quyền:** Writer có thể cần quyền `Wrap` nhưng không cần `Unwrap`; reader ngược lại theo nghiệp vụ.
3. **Nơi lưu:** KEK có thể là **non-exportable trong HSM/KMS**, DEK có thể tồn tại ngắn hạn trong ứng dụng.
4. **Rotation:** Rotate KEK có thể **rewrap DEK** mà không đổi dữ liệu; rotate DEK có thể phải **re-encrypt**.
5. **Audit:** `Wrap/Unwrap` và `Encrypt/Decrypt` cần được theo dõi ở những lớp khác nhau.

### Phản ví dụ

Một dịch vụ dùng `billing-master-aes` để **AES-GCM encrypt record** và đồng thời **AES-Wrap các DEK của dịch vụ khác**. Sự cố ở luồng record có thể ảnh hưởng cả kho keys; chính sách key usage trở nên khó bảo vệ.

### KMS/HSM không luôn expose cùng API

Một managed KMS có thể cung cấp `Encrypt`/`Decrypt` trên key resource, trong khi API `GenerateDataKey` trả plaintext DEK tạm và bản bọc. **Không được suy ra rằng mọi API KMS có `WrapKey` theo cùng tên hoặc có thể export raw KEK.**

Cần xác định **material thực**, loại operation và boundary theo provider.

## 7. Không trộn khóa mã hóa với khóa ký số

**Encryption** bảo vệ bí mật nội dung. **Digital signature** bảo vệ authenticity/integrity theo cơ chế xác minh bằng public key, và thường cần chứng cứ về người ký hoặc authority.

### Chọn khóa đúng nhiệm vụ

| Tác vụ | Key và cơ chế điển hình | Lỗi cần tránh |
| --- | --- | --- |
| Encrypt record | AES-GCM DEK | Dùng signing private key như secret mã hóa |
| Bọc DEK cho recipient | RSA-OAEP, HPKE hoặc AES-KW theo thiết kế | Dùng raw RSA hoặc scheme tự chế |
| Ký hóa đơn | RSA-PSS, ECDSA hoặc Ed25519 | Dùng cùng key material vào encryption/decryption tùy tiện |
| Verify chữ ký | Public verification key/certificate | Coi `kid` do client đưa là trust anchor |
| Ký release artifact | Signing key riêng, approval exact digest | Dùng cùng key với token issuer hoặc CA root |

### RSA key pair có thể dùng OAEP và PSS?

RSA về mặt biểu diễn toán học có thể được các API hỗ trợ cho cả **RSA-OAEP encryption/decryption** và **RSA-PSS signatures** trong những trường hợp nhất định. Nhưng **không vì thế mà dùng một key pair cho cả hai** nếu không có chuẩn/giao thức và chính sách được đánh giá đặc biệt.

Đối với thiết kế hệ thống mới, nên dùng **key pair riêng**:

~~~text
invoice-data-transport-rsa-key    -> RSA-OAEP / approved hybrid encryption
invoice-signing-rsa-key           -> RSA-PSS digital signatures
~~~

**Không được giả định** rằng thành công ở `Cipher.getInstance(...)` hay `Signature.getInstance(...)` chứng minh việc tái sử dụng key pair xuyên giao thức là an toàn.

### Public key được công bố không phải key misuse

Một public key có thể được phân phối tới nhiều verifier trong cùng purpose. Việc lộ public key là điều bình thường trong asymmetric cryptography, nhưng **nguồn tin cậy, certificate chain, key usage và vòng đời public key** phải đúng.

## 8. ECDSA, Ed25519 không đồng nghĩa ECDH, X25519

**ECDSA/Ed25519** là các cơ chế chữ ký số. **ECDH/X25519** là các cơ chế/thành phần thỏa thuận khóa. Tính chất đường cong và biểu diễn private key có thể tạo cảm giác “cùng một secret scalar là dùng được”, nhưng đây là những **giao thức với giả định khác nhau**.

### Khuyến nghị cho thiết kế mới

- Sinh **signing key pair** riêng, purpose `SIGNATURE`.
- Sinh **agreement key pair** riêng, purpose `KEY_AGREEMENT`.
- Gắn key usage và allowed operation tương ứng.
- Với agreement, dùng **peer public key authentication**, xác minh theo giao thức và **KDF/context binding**.
- Không tự chuyển đổi Ed25519 private key sang X25519 hoặc ngược lại vì thuận tiện.

### ECDH không tự xác thực peer

Một ứng dụng gọi `KeyAgreement` có thể tính được shared secret với public key của bất kỳ peer hợp lệ nào, nhưng **không tự chứng minh đó là peer mong muốn**. Thiếu xác thực peer có thể dẫn tới MITM.

Vì vậy tách signing key/agreement key vẫn phải đi kèm **authenticated key establishment protocol**, chứ không chỉ tạo hai đối tượng khóa.

### Ephemeral agreement key

Một giao thức ECDHE có thể sinh key pair tạm theo phiên để hỗ trợ forward secrecy theo điều kiện giao thức. **Không tái dùng private ephemeral secret qua các phiên** trái key schedule chỉ để tiết kiệm entropy hoặc tối ưu tốc độ.

## 9. Không dùng một secret cho mọi tenant, môi trường và service

Ngay cả khi hai tác vụ cùng dùng AES-GCM, việc dùng chung raw DEK giữa các **trust domains** khác nhau có thể sai về mục đích quản trị.

### Các miền phân tách phổ biến

| Miền | Câu hỏi thiết kế | Ví dụ |
| --- | --- | --- |
| **Environment** | Dev/staging/prod có cùng secret không? | Production DEK không được sao sang staging |
| **Tenant** | Tenant A có thể ảnh hưởng tenant B khi key lộ không? | DEK riêng theo tenant nếu cách ly là yêu cầu |
| **Service** | Service A có cần raw key của service B? | Identity signing key không ở Billing worker |
| **Dataset** | PII, invoices, audit logs có cùng cryptoperiod? | DEK khác cho dữ liệu nhạy cảm |
| **Protocol** | Webhook HMAC và JWT signing có chung secret? | Không; khác key/purpose |
| **Direction** | Client→server và server→client có cùng traffic key? | Key schedule giao thức thường tách chiều |
| **Partner** | Các đối tác biết chung một HMAC key? | HMAC secret riêng theo đối tác |
| **Epoch/key version** | Sau rotation có thực sự là key mới? | `dek-v2` khác vật liệu v1 |

### Tenant isolation không phải chỉ thêm tenant ID vào tên

Nếu tất cả tenant đều được mã hóa bằng **cùng raw AES key**, việc đặt key alias theo tenant không tự tăng cách ly. Tách **key material** hoặc dùng **KDF có context tenant** là hai phương án có giả định bảo mật khác nhau, cần được chọn theo risk tier.

**HKDF context theo tenant không thay IAM**: nếu attacker có quyền chọn `tenantId` tự do và gọi derive từ master chung, họ có thể tạo subkey của tenant khác trừ khi API kiểm tra ràng buộc principal–tenant.

### Không sao chép khóa production vào staging

Dữ liệu production đã khử nhạy cảm vẫn không phải lý do tốt để copy **private signing key, raw KEK hoặc DEK production** sang môi trường ít được bảo vệ. Tạo **test keys** từ nguồn an toàn và giữ inventory riêng.

## 10. Domain separation — phân tách mục đích ngay trong KDF

Có những hệ thống cần nhiều **subkeys** từ một master secret hoặc một shared secret thỏa thuận. Trong trường hợp này có thể sử dụng **KDF chuẩn** và **domain separation**.

### HKDF (RFC 5869)

HKDF có hai giai đoạn:

~~~text
PRK = HKDF-Extract(salt, IKM)

K_enc = HKDF-Expand(PRK,
    info = "billing/key-schedule/v1/tenant-a/AES-GCM-record", L = 32)

K_mac = HKDF-Expand(PRK,
    info = "billing/key-schedule/v1/tenant-a/HMAC-webhook", L = 32)
~~~

- **IKM (Input Keying Material):** bí mật đầu vào có entropy phù hợp.
- **Salt:** giá trị cho giai đoạn Extract theo đặc tả, thường không bí mật.
- **PRK:** pseudorandom key trung gian.
- **`info`:** nhãn/ngữ cảnh phân biệt purpose, protocol, role, version và scope.
- **L:** độ dài output cần cho thuật toán.

Các đầu ra khác `info` có thể có **tính tách biệt về mặt mật mã theo giả định HKDF/PRF an toàn**, nhưng **đều phụ thuộc cùng master**. Chúng **không độc lập tuyệt đối về thông tin**.

### Cảnh báo quan trọng

1. Nếu **master lộ**, kẻ tấn công có thể tính lại **mọi subkey** có context biết được.
2. Nếu **master ít entropy**, HKDF không tự làm tăng entropy không thể đoán của nguồn.
3. **Cùng master/salt/info/L** tạo **cùng subkey**, nên `info` phải version hóa khi cần khóa mới.
4. Khác `info` **không chứng minh authorization**: API vẫn phải chặn tenant khác hoặc purpose không được phép.
5. **Không tự tạo key schedule của TLS hoặc giao thức production** khi đã có đặc tả chuẩn phải tuân theo.
6. Không dùng `SHA-256(master || label)` tùy tiện thay cho KDF nếu chưa có phân tích; dùng KDF tiêu chuẩn và test vectors.

### So sánh hai mô hình phân tách

| Tiêu chí | Sinh khóa riêng với CSPRNG | Dẫn xuất subkey từ master với HKDF |
| --- | --- | --- |
| Có master chung quyết định subkeys? | Không bắt buộc | **Có** |
| Lộ một child/subkey có mặc nhiên suy ra key khác? | Không, dưới giả định nguồn sinh an toàn | Không, dưới giả định KDF phù hợp |
| Lộ master/source state | Có thể ảnh hưởng nhiều khóa theo mô hình/state compromise | **Ảnh hưởng mọi subkey có thể derive** |
| Có thể rederive từ metadata không? | Không nếu không giữ/backup key | Có nếu còn master, salt và context |
| Quản trị | Nhiều key objects/KEKs và access rules | Master là tài sản trọng yếu, cần kiểm soát derive |
| Khi dùng | Key tách mạnh giữa service/tenant/domain | Session key schedule và subkey theo giao thức |
| Rủi ro | Storage, provisioning, RNG, copies | Master dependency và domain collision |

**Không có quy tắc “HKDF luôn tốt hơn” hoặc “mọi subkey phải là key độc lập sinh trực tiếp”.** Chọn theo security goals và lifecycle, không chỉ số lượng keys.

## 11. Thiết kế nhãn context và encoding không mơ hồ

Một KDF dùng `info` khác cho hai purpose chỉ hữu ích nếu **nhãn được định nghĩa có cấu trúc và không trùng do cách mã hóa**.

### Phản ví dụ nối chuỗi mơ hồ

~~~text
encode("ab", "c") = "abc"
encode("a", "bc") = "abc"
~~~

Dù hai tuple khác nhau, `info` vẫn trùng. Nếu đầu vào có tenant ID, record ID, protocol role, key version hoặc session ID, cần **canonical encoding/length-prefix** hoặc một format được đặc tả rõ.

### Những trường thường cần đưa vào key context

- **Protocol/application ID** và version.
- **Key purpose:** `data-encryption`, `webhook-mac`, `exporter`.
- **Algorithm suite:** AES-GCM, HMAC-SHA-256, traffic suite.
- **Tenant/peer identity** hoặc data domain.
- **Environment/region** khi đó là trust boundary cần thiết.
- **Direction/role:** client write vs server write, sender vs recipient.
- **Epoch/key version/session identity** khi key schedule yêu cầu.

**Không cho client tự đưa `purpose` để chọn derive key** mà không có kiểm tra quyền. Việc `info` là bytes công khai không có nghĩa bất kỳ ai được phép chọn một context khác để lấy secret của chức năng khác.

### Salt không phải purpose

Không coi một **salt khác nhau** là cơ chế thay thế hoàn chỉnh cho **`info` phân biệt miền**. Salt hỗ trợ HKDF-Extract theo mô hình; `info` được dùng ràng buộc ngữ cảnh HKDF-Expand.

## 12. Nonce separation: đúng key nhưng sai nonce vẫn không an toàn

Ngay cả khi một DEK được sử dụng **đúng purpose AES-GCM**, việc dùng nó sai quy tắc nonce có thể phá bảo mật.

### Nguyên tắc với AES-GCM

~~~text
(ciphertext, tag) = AES-GCM-Encrypt(DEK, nonce, AAD, plaintext)

Không được tái sử dụng cùng cặp (DEK, nonce)
cho hai lần mã hóa khác nhau trái đặc tả.
~~~

Nonce thường không phải secret, nhưng phải **đảm bảo uniqueness theo thiết kế**. Có thể dùng counter được phân bổ an toàn hoặc nonce ngẫu nhiên 96 bit từ CSPRNG trong giới hạn được tính toán.

### Những sai lầm phổ biến

- Dùng **nonce cố định** với cùng DEK cho mọi bản ghi.
- Mỗi worker bắt đầu **counter nonce từ 0** nhưng cùng raw key.
- Snapshot/restore VM khiến **trạng thái tạo nonce hoặc DRBG bị lặp**.
- Re-encrypt payload mới nhưng copy lại nonce cũ dưới **cùng DEK**.
- Dùng tenant ID/hash ngắn làm nonce mà không chứng minh duy nhất.
- Dùng một DEK quá lâu mà không theo dõi **số lần encrypt hoặc giới hạn dữ liệu**.

**Tách DEK theo tenant/record** có thể giúp chia phạm vi nonce và blast radius, nhưng không thay quy tắc **mỗi key/nonce pair phải tuân theo GCM**.

### AAD cũng cần tách đúng domain

AAD (*Additional Authenticated Data*) ràng buộc ciphertext với metadata được xác thực, như `tenantId`, `recordId`, `keyVersion` và `schemaVersion`.

~~~text
AAD = canonicalEncode(
    domain = "billing-record/v2",
    tenant = "tenant-a",
    record = "invoice-0042",
    dekVersion = "v2"
)
~~~

AAD không được giữ bí mật, nhưng nếu bị thay so với lúc encrypt, **authentication tag phải fail**. Không tự động tin mọi metadata do client gửi; phải kiểm tra domain/business ownership trước khi dùng.

## 13. Java 11+: sinh riêng các key theo purpose và chặn nhầm operation

Đoạn mã sau minh họa cách:

- Sinh **DEK AES-256** và **KEK AES-256** bằng hai lần gọi riêng, không reuse bytes.
- Sinh **HMAC-SHA-256 key** bằng `KeyGenerator` riêng.
- Sinh **hai EC key pairs khác nhau** cho signing và agreement, dù cùng curve P-256.
- Ràng buộc **purpose + operation + principal** ở tầng Java demo.
- Dùng AES-GCM và HMAC chỉ theo đúng purpose, kiểm tra negative tests.

**Mã có tính minh họa policy**, không thay KMS/HSM hoặc cryptographic boundary. Các key này đều được tạo/giữ trong cùng JVM nên attacker có quyền đọc process memory vẫn có thể lấy raw material hoặc bypass policy.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class KeyPurposeSeparationDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    enum Purpose {
        RECORD_ENCRYPTION,
        KEY_WRAPPING,
        WEBHOOK_AUTHENTICATION,
        SIGNING,
        KEY_AGREEMENT
    }

    enum Action {
        ENCRYPT, DECRYPT, WRAP, UNWRAP, GENERATE_MAC,
        VERIFY_MAC, SIGN, DERIVE
    }

    enum Principal {
        RECORD_WRITER, RECORD_READER, WEBHOOK_SENDER,
        KEY_CUSTODIAN
    }

    static final class ManagedSecretKey {
        final String id;
        final Purpose purpose;
        final SecretKey material;

        ManagedSecretKey(String id, Purpose purpose, SecretKey material) {
            this.id = id;
            this.purpose = purpose;
            this.material = material;
        }
    }

    static void require(ManagedSecretKey key, Principal principal,
                        Purpose expectedPurpose, Action action) {
        if (key == null || principal == null
                || expectedPurpose == null || action == null) {
            throw new SecurityException("Missing policy context");
        }
        if (key.purpose != expectedPurpose) {
            throw new SecurityException("Wrong cryptographic purpose");
        }

        boolean allow =
                (expectedPurpose == Purpose.RECORD_ENCRYPTION
                    && action == Action.ENCRYPT
                    && principal == Principal.RECORD_WRITER)
                || (expectedPurpose == Purpose.RECORD_ENCRYPTION
                    && action == Action.DECRYPT
                    && principal == Principal.RECORD_READER)
                || (expectedPurpose == Purpose.WEBHOOK_AUTHENTICATION
                    && action == Action.GENERATE_MAC
                    && principal == Principal.WEBHOOK_SENDER);

        if (!allow) {
            throw new SecurityException("Operation not authorized");
        }
    }

    static SecretKey generate(String algorithm, int bits)
            throws GeneralSecurityException {
        KeyGenerator kg = KeyGenerator.getInstance(algorithm);
        kg.init(bits, RANDOM);
        return kg.generateKey();
    }

    static KeyPair newP256Pair() throws GeneralSecurityException {
        KeyPairGenerator kg = KeyPairGenerator.getInstance("EC");
        kg.initialize(new ECGenParameterSpec("secp256r1"), RANDOM);
        return kg.generateKeyPair();
    }

    static byte[] encryptRecord(
            ManagedSecretKey dek, Principal principal,
            byte[] plaintext, byte[] nonce, byte[] aad)
            throws GeneralSecurityException {

        require(dek, principal, Purpose.RECORD_ENCRYPTION,
                Action.ENCRYPT);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, dek.material,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext);
    }

    static byte[] decryptRecord(
            ManagedSecretKey dek, Principal principal,
            byte[] ciphertextAndTag, byte[] nonce, byte[] aad)
            throws GeneralSecurityException {

        require(dek, principal, Purpose.RECORD_ENCRYPTION,
                Action.DECRYPT);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, dek.material,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    static byte[] webhookMac(
            ManagedSecretKey hmacKey, Principal principal,
            byte[] message) throws GeneralSecurityException {

        require(hmacKey, principal,
                Purpose.WEBHOOK_AUTHENTICATION, Action.GENERATE_MAC);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(hmacKey.material);
        return mac.doFinal(message);
    }

    public static void main(String[] args) throws Exception {
        ManagedSecretKey dek = new ManagedSecretKey(
                "billing-dek-v1", Purpose.RECORD_ENCRYPTION,
                generate("AES", 256));

        ManagedSecretKey kek = new ManagedSecretKey(
                "billing-kek-v1", Purpose.KEY_WRAPPING,
                generate("AES", 256));

        ManagedSecretKey hmac = new ManagedSecretKey(
                "billing-webhook-hmac-v1",
                Purpose.WEBHOOK_AUTHENTICATION,
                generate("HmacSHA256", 256));

        // Đây là hai cặp private/public riêng cho hai purpose.
        KeyPair signingPair = newP256Pair();
        KeyPair agreementPair = newP256Pair();

        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce);
        byte[] aad = "billing/v1/tenant-a/invoice-42"
                .getBytes(StandardCharsets.UTF_8);
        byte[] input = "training-invoice"
                .getBytes(StandardCharsets.UTF_8);

        byte[] ciphertext = encryptRecord(
                dek, Principal.RECORD_WRITER, input, nonce, aad);
        byte[] recovered = decryptRecord(
                dek, Principal.RECORD_READER, ciphertext, nonce, aad);

        byte[] macTag = webhookMac(hmac,
                Principal.WEBHOOK_SENDER,
                "event-1".getBytes(StandardCharsets.UTF_8));

        System.out.println("Record round-trip: "
                + MessageDigest.isEqual(input, recovered));
        System.out.println("MAC length: " + macTag.length);
        System.out.println("KEK purpose: " + kek.purpose);
        System.out.println("Signing pair type: "
                + signingPair.getPrivate().getAlgorithm());
        System.out.println("Agreement pair type: "
                + agreementPair.getPrivate().getAlgorithm());

        try {
            // Dùng DEK làm HMAC key bị policy gate từ chối.
            webhookMac(dek, Principal.WEBHOOK_SENDER, input);
            throw new AssertionError("Cross-purpose use accepted");
        } catch (SecurityException expected) {
            System.out.println("Cross-purpose use: denied");
        }

        try {
            // Writer không được Decrypt, dù cùng DEK có thể decrypt
            // về mặt toán học.
            decryptRecord(dek, Principal.RECORD_WRITER,
                    ciphertext, nonce, aad);
            throw new AssertionError("Writer decrypt accepted");
        } catch (SecurityException expected) {
            System.out.println("Writer decrypt: denied");
        }

        // Không in raw key, private key, plaintext hoặc HSM PIN.
        // Production: KMS/HSM, IAM, lifecycle, audit, nonce limits.
    }
}
~~~

### Kết quả minh họa

~~~text
Record round-trip: true
MAC length: 32
KEK purpose: KEY_WRAPPING
Signing pair type: EC
Agreement pair type: EC
Cross-purpose use: denied
Writer decrypt: denied
~~~

### Hiểu đúng giới hạn

1. **`ManagedSecretKey` và `require()` chỉ là gate trong code**; một người điều khiển JVM có thể lấy `SecretKey` rồi gọi JCE trực tiếp.
2. Các hàm `generate("AES", 256)` tạo DEK và KEK **bằng các lần sinh riêng**, nhưng mã không bọc DEK thật. Để wrap, phải dùng **AES-KW/provider KMS/HSM** được hỗ trợ và policy phù hợp.
3. Hai lần `newP256Pair()` tạo **hai key pairs riêng**. Public key trong mỗi pair có liên hệ toán học với private key; không gọi hai thành phần đó là hai khóa độc lập.
4. **Nonce ngẫu nhiên 96 bit** minh họa một lần encrypt; không chứng minh tránh va chạm khi triển khai trên nhiều node/region lâu dài.
5. **AES-GCM tag** được xác minh bởi `doFinal()` khi decrypt; không coi nó là chữ ký số.
6. **HMAC key** cần được chia sẻ/giữ đúng đối tác và giao thức, không chỉ sinh đúng algorithm.
7. `MessageDigest.isEqual` chỉ kiểm tra kết quả một bài test, không chứng minh tính an toàn RNG hoặc key separation ở production.
8. Không dùng mã này làm bằng chứng rằng private key không xuất được, vì không có HSM.

**Điều cần học ở code:** cả **mật mã đúng** lẫn **quyền đúng** đều cần thiết; một lớp không thể thay thế lớp kia.

## 14. Java 11+: dẫn xuất subkeys có domain separation bằng HKDF-SHA-256

Đôi khi hệ thống cần sinh nhiều key từ **một master secret đủ mạnh**, ví dụ key schedule của một giao thức. Đoạn mã sau minh họa HKDF-Extract/Expand cho **hai purpose khác nhau**, không phải một triển khai key hierarchy production hoàn chỉnh.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HkdfPurposeSeparationDemo {
    private static final SecureRandom RNG = new SecureRandom();

    static byte[] hmac(byte[] key, byte[] data)
            throws GeneralSecurityException {
        Mac m = Mac.getInstance("HmacSHA256");
        m.init(new SecretKeySpec(key, "HmacSHA256"));
        return m.doFinal(data);
    }

    static byte[] extract(byte[] salt, byte[] ikm)
            throws GeneralSecurityException {
        return hmac(salt, ikm);
    }

    // Chỉ minh họa HKDF-Expand cho đúng 32 byte = 1 block SHA-256.
    static byte[] expand32(byte[] prk, String info)
            throws GeneralSecurityException {
        byte[] context = info.getBytes(StandardCharsets.UTF_8);
        byte[] blockInput = Arrays.copyOf(
                context, context.length + 1);
        blockInput[context.length] = 1;
        try {
            return hmac(prk, blockInput); // T(1) = HMAC(PRK, info || 0x01)
        } finally {
            Arrays.fill(blockInput, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] master = new byte[32];
        byte[] salt = new byte[32];
        RNG.nextBytes(master);
        RNG.nextBytes(salt);

        byte[] prk = null;
        byte[] aesKey = null;
        byte[] macKey = null;
        try {
            prk = extract(salt, master);

            aesKey = expand32(prk,
                    "billing/key-schedule/v1/prod/tenant-a/record-aes-gcm");
            macKey = expand32(prk,
                    "billing/key-schedule/v1/prod/tenant-a/webhook-hmac");

            System.out.println("Same subkey: "
                    + MessageDigest.isEqual(aesKey, macKey));

            // Không in key bytes, PRK hoặc master.
        } finally {
            Arrays.fill(master, (byte) 0);
            Arrays.fill(salt, (byte) 0);
            if (prk != null) Arrays.fill(prk, (byte) 0);
            if (aesKey != null) Arrays.fill(aesKey, (byte) 0);
            if (macKey != null) Arrays.fill(macKey, (byte) 0);
        }
    }
}
~~~

Kết quả **điển hình**:

~~~text
Same subkey: false
~~~

### Những giới hạn bắt buộc nhớ

- Đây là mô hình **một block HKDF-Expand**. Nếu cần nhiều bytes hơn, dùng **implementation HKDF chuẩn**, tuân thủ RFC 5869, giới hạn độ dài và test vectors.
- Dùng `info` khác giúp phân tách mục đích **dưới giả định KDF an toàn**. Việc in `false` không phải chứng minh toán học rằng subkeys độc lập.
- **Lộ master** có thể làm lộ tất cả subkeys. Cần quản lý master/PRK như bí mật trọng yếu và kiểm kê parent–child relationship.
- **Cùng master, salt, info, L** tạo **cùng output**; HKDF không tự rotate chỉ vì ứng dụng khởi động lại.
- `Arrays.fill` chỉ là biện pháp **best effort**; JVM/native provider có thể có các bản sao khác.
- Các label cố định trong demo chỉ phù hợp giáo dục. Với context thay đổi theo tenant/peer/role, cần canonical encoding có trường length-prefix.
- **Đừng dùng password yếu làm master** rồi nghĩ HKDF tự chống đoán mật khẩu. Password-based key material đòi KDF phù hợp với threat model như Argon2id/scrypt/PBKDF2.
- **KDF không tự thực thi IAM**; API phải từ chối workload yêu cầu dẫn xuất subkey cho purpose/tenant không thuộc quyền.

## 15. KMS key usage và IAM phải đồng nhất với purpose

**Managed KMS** thường phân loại key theo **key spec/type và key usage**. Một số tài nguyên dùng cho **symmetric Encrypt/Decrypt**, một số cho **Sign/Verify**, **Generate/Verify MAC** hoặc key agreement tùy provider.

Không có một schema chung cho mọi KMS.

### Hai lớp chính sách

**Lớp 1 — Key capability**

Có thể key resource thuộc loại **symmetric encryption** và provider hỗ trợ `Encrypt`/`Decrypt`. Loại capability này **không tự cho mọi principal mọi operation**.

**Lớp 2 — Principal authorization**

Một workload có thể được cấp **Encrypt-only** trên đúng key ID, trong khi reader được cấp Decrypt theo scope. Cả hai đều dùng **cùng AES material** dưới sự cưỡng chế của KMS.

### Mẫu policy khái niệm

~~~yaml
# Mẫu thiết kế, KHÔNG phải cấu hình IAM chạy trực tiếp.
keys:
  - id: "billing-dek-or-kms-key-v3"
    purpose: "INVOICE_DATA_ENCRYPTION"
    capability: "SYMMETRIC_ENCRYPTION"
    state: "ACTIVE"
    allowedPrincipals:
      - principal: "billing-writer"
        operations: ["Encrypt"]
      - principal: "billing-reader"
        operations: ["Decrypt"]
    forbiddenCrossPurposeOperations:
      - "Sign"
      - "GenerateMac"
      - "UseAsKeyWrappingKey"
    requireBusinessAuthorization: true
    auditKeyUse: true

  - id: "billing-signing-v3"
    purpose: "INVOICE_SIGNATURE"
    capability: "ASYMMETRIC_SIGN_VERIFY"
    allowedPrincipals:
      - principal: "invoice-signing-gateway"
        operations: ["Sign"]
    requireApprovedDocumentDigest: true
~~~

**Lưu ý:** tên `billing-dek-or-kms-key-v3` là ví dụ tài sản logic. Một KMS resource có thể thực chất là **KEK bảo vệ DEK**, không trực tiếp giữ mọi DEK và không kiểm soát được AES-GCM chạy offline tại JVM. Luôn ánh xạ policy tới **material và operation thực**.

### Kiểm soát quyền gián tiếp

Một service có thể không được `Decrypt` nhưng lại có quyền:

- Tự `CreateGrant` cấp Decrypt cho mình.
- Sửa IAM/key policy hoặc role trust.
- Gọi một service khác như **decryption oracle** không kiểm tra business scope.
- Đọc memory của process giữ plaintext DEK.
- Truy cập key backup, import/export hoặc secrets store chứa raw material.

**Chặn những đường vòng này** mới đạt mục tiêu key usage separation trên thực tế.

## 16. HSM và PKCS#11: gắn allowed operations vào key object

Với **HSM**, policy có thể được cưỡng chế ở mức token/partition và key object. **PKCS#11** có các attributes liên quan:

| Attribute | Ý nghĩa điển hình |
| --- | --- |
| `CKA_ENCRYPT` | Cho phép dùng key object để mã hóa |
| `CKA_DECRYPT` | Cho phép dùng key object để giải mã |
| `CKA_SIGN` | Cho phép tạo chữ ký bằng key phù hợp |
| `CKA_VERIFY` | Cho phép xác minh chữ ký |
| `CKA_WRAP` | Cho phép bọc key khác |
| `CKA_UNWRAP` | Cho phép giải bọc key khác |
| `CKA_DERIVE` | Cho phép dẫn xuất khóa |
| `CKA_SENSITIVE` | Giới hạn truy vấn giá trị nhạy cảm |
| `CKA_EXTRACTABLE` | Liên quan khả năng xuất/wrap material |
| `CKA_PRIVATE` | Giới hạn khả năng truy cập object khi chưa đăng nhập |
| `CKA_ID` / `CKA_LABEL` | Định danh/tìm kiếm object, không thay authorization |

### Một key AES được phép Encrypt nhưng không Decrypt

~~~text
Key ID: hsm-object-enc-01
CKA_ENCRYPT = true
CKA_DECRYPT = false
CKA_WRAP = false
CKA_SIGN = false
CKA_EXTRACTABLE = false
~~~

**Đây là ví dụ policy logic**, không phải cấu hình đúng cho mọi HSM. Cần xác nhận mechanism, object attributes, quyền thay đổi attributes và cách key được sinh/nhập.

### Ba giới hạn quan trọng

1. **HSM attributes chỉ có hiệu lực đối với vật liệu được bảo vệ trong boundary của nó.** Nếu raw key đã bị export/import từ nơi khác, bản sao ngoài HSM có thể bị sử dụng không theo attributes.
2. Nếu key object chỉ cho Encrypt nhưng dữ liệu cần giải mã sau này, phải thiết kế **đường Decrypt hợp lệ** từ đầu; không đặt policy khiến dữ liệu không thể phục hồi.
3. Non-exportability và scope không tự ngăn **signing/decrypt oracle** khi một workload có quyền operation nhưng thiếu business approval.

### Java provider cũng phải được chọn đúng

`Cipher.getInstance("AES/GCM/NoPadding")` có thể chọn provider theo thứ tự cấu hình và xử lý bằng phần mềm. Không thể suy ra lệnh đã chạy trong HSM chỉ vì key ID có tên “hsm”. Cần xác minh provider, key handle, token, supported mechanisms và log thực tế.

## 17. Key generation: tạo đúng key ngay từ đầu

Một khi các key đã được sử dụng sai và lưu dữ liệu, việc “đổi purpose” hoặc “đổi alias” không làm những tác động lịch sử biến mất. **Tạo đúng key từ đầu** là biện pháp mạnh.

### Quy trình đề xuất

1. Xác định **purpose**, dữ liệu/giao thức, owner, tenant, environment và risk tier.
2. Chọn **thuật toán/key spec/key size** phù hợp với purpose.
3. Xác định **generation model**: CSPRNG riêng, KMS/HSM-generated hoặc KDF-derived theo key schedule chuẩn.
4. Kiểm tra **nguồn entropy/DRBG**, không dùng timestamp/PID/`java.util.Random` để tạo secret.
5. Gắn **key usage/allowed operations**, IAM/PKCS#11 attributes và export policy.
6. Đặt key vào **pre-activation**; kiểm thử wrong-purpose và wrong-principal deny trước production.
7. Ghi **key ID/version, key origin, purpose, parent key nếu KDF-derived, cryptoperiod** vào inventory.
8. Có **rotation/backup/DR/destruction runbook** trước khi cấp key cho workload.
9. Bảo đảm không log raw key hoặc secret seed.
10. Phê duyệt **activation** rồi mới cho new-use production.

### Không tự seed DRBG bằng giá trị đoán được

Một `SecureRandom` được sử dụng đúng với provider thích hợp tốt hơn việc tự triển khai pseudo-random key generator hoặc seed bằng `System.currentTimeMillis()`.

Với **VM/container snapshot, fork hoặc restore**, cần đánh giá nguy cơ lặp trạng thái RNG và khả năng reseed/clone safety của runtime. Không dùng timestamp làm cách chữa lỗi chất lượng entropy.

### Hai key ID không chứng minh hai key độc lập

Một hệ thống tạo `data-key-v1` và `mac-key-v1` nhưng cùng seed cố định rồi tự hash có thể cho đầu ra khác nhau mà vẫn dự đoán được. **Security property** phải đến từ nguồn sinh/KDF đúng, không phải số lượng metadata entries.

## 18. Key inventory: đưa purpose thành dữ liệu quản trị kiểm tra được

Muốn phát hiện cross-purpose reuse, cần inventory ghi nhận **mối quan hệ giữa key, material, workflow và nơi sử dụng**.

### Schema minh họa

~~~yaml
# Metadata mẫu, không chứa raw key material.
keys:
  - keyId: "billing-dek-v2"
    materialVersion: "v2"
    purpose: "INVOICE_DATA_ENCRYPTION"
    algorithm: "AES-256-GCM"
    tenantScope: "tenant-a"
    environment: "production"
    origin: "KMS_GENERATED"
    generationModel: "INDEPENDENT_RANDOM"
    parentKeyId: null
    approvedOperations: ["Encrypt", "Decrypt"]
    disallowedPurposes: ["HMAC", "SIGNING", "KEY_WRAPPING"]
    owner: "billing-data-owner"
    custodian: "platform-key-team"
    lifecycleState: "ACTIVE"

  - keyId: "billing-webhook-hmac-v2"
    materialVersion: "v2"
    purpose: "WEBHOOK_AUTHENTICATION"
    algorithm: "HMAC-SHA-256"
    tenantScope: "partner-a"
    environment: "production"
    origin: "KMS_GENERATED"
    generationModel: "INDEPENDENT_RANDOM"
    parentKeyId: null
    approvedOperations: ["GenerateMac", "VerifyMac"]
    disallowedPurposes: ["DATA_ENCRYPTION", "KEY_WRAPPING"]
    owner: "billing-integration-owner"
    custodian: "platform-key-team"
    lifecycleState: "ACTIVE"

  - keyId: "billing-master-v2"
    materialVersion: "v2"
    purpose: "APPROVED_KDF_PARENT"
    algorithm: "HKDF-SHA-256-compatible-input"
    environment: "production"
    origin: "HSM_GENERATED"
    approvedOperations: ["DeriveApprovedSubkey"]
    lifecycleState: "ACTIVE"
~~~

**Không lưu raw DEK, HMAC secret, private scalar, PRK hay master trong inventory.** Metadata cũng phải được bảo vệ khỏi thay đổi trái phép.

### Những quan hệ cần lưu

- **Parent–child lineage** khi keys được dẫn xuất.
- **KEK–wrapped DEK** dependencies.
- **Key–ciphertext/data scope** dependencies.
- **Signing private key–public verification material/certificate** relationship.
- **Key version–alias/current routing** mapping.
- **Source/generated/imported/restored** history.
- **Workload principals** được cấp operation.
- **Backup/replica locations** và retention.

### Phát hiện key reuse sai

Không chỉ đối chiếu **key names**. Cần tìm đường:

- Cùng raw secret bị cấu hình lại dưới hai thuật toán.
- Một key được dùng bởi service ngoài purpose.
- Hai alias trỏ cùng provider key material.
- Workload có grants mới ngoài inventory.
- Key derivation labels/context trùng hoặc không có canonical encoding.
- Một key đã deactivated vẫn xuất hiện trong new-use.
- Dev/staging trỏ tới production key ID.

## 19. Phân quyền theo operation, purpose và data scope

Chỉ có `purpose` trong YAML không đủ; việc thực thi phải gắn với **principal + key ID/version + operation + scope + state**.

### Ví dụ ma trận quyền

| Principal | DEK Invoice | KEK Wrap | Webhook HMAC | Signing key |
| --- | --- | --- | --- | --- |
| **Billing writer** | Encrypt trong tenant được phép | Wrap/GDK theo kiến trúc | Deny | Deny |
| **Billing reader** | Decrypt sau data authorization | Unwrap theo quyền | Deny | Deny |
| **Webhook service** | Deny | Deny | GenerateMac partner scope | Deny |
| **Invoice signer** | Deny | Deny | Deny | Sign digest được duyệt |
| **Key custodian** | Quản trị lifecycle theo approval | Rotate/backup theo policy | Provision theo policy | Quản trị key, không tự ký |
| **Auditor** | Chỉ metadata/log | Chỉ metadata/log | Chỉ metadata/log | Chỉ metadata/log |

**Lưu ý:** Nếu DEK ở JVM và AES-GCM thực hiện offline, “deny Decrypt” ở KMS có thể **không ngăn local decrypt bằng raw DEK đã được cấp**. Phải xác định đúng trust boundary.

### Kiểm tra trước mỗi operation

~~~text
ALLOW khi và chỉ khi:
    principal đã được xác thực
    AND operation nằm trong policy của key
    AND key purpose phù hợp với request purpose
    AND tenant/environment/data scope hợp lệ
    AND key lifecycle cho phép operation ở thời điểm đó
    AND business approval cần thiết đã được xác minh
    AND key/provider không bị suspend hoặc compromised
~~~

- Với `Sign`, kiểm tra **exact content digest/manifest và approval** khi nghiệp vụ yêu cầu.
- Với `Decrypt`, kiểm tra **data ownership, record scope và mục đích**.
- Với `Derive`, giới hạn context/tenant/role được phép.
- Với `Wrap/Unwrap`, kiểm tra **đúng KEK và key lineage**.

Không coi **user-supplied purpose** là bằng chứng authorization; phải lấy context từ route, identity và resource metadata đáng tin.

## 20. Separation of duties và dual control

**Separation of duties (SoD)** giúp ngăn một cá nhân hoặc service vừa **tạo policy, tự phê duyệt, tự dùng key, vừa xóa log**.

### Vai trò điển hình

| Vai trò | Trách nhiệm | Quyền không tự có |
| --- | --- | --- |
| **Key owner** | Phê duyệt purpose, cryptoperiod, risk acceptance | Raw secret, mọi Decrypt/Sign |
| **Key custodian** | Sinh, lưu, rotate, backup key theo quy trình | Tự dùng key để đọc dữ liệu nghiệp vụ |
| **Key user/workload** | Dùng operation đúng mục đích | Thay policy, export, rotate hoặc destroy |
| **Security approver** | Review thuật toán, key separation, IAM | Tự thực thi thay policy |
| **Auditor** | Kiểm tra key usage và evidence | Sửa hoặc xóa log |
| **Incident responder** | Cô lập, điều tra và phục hồi | Dùng compromised key tiếp không cần đánh giá |

### Khi nào cần dual control?

Không bắt buộc hai người cho mỗi AES-GCM encryption. Dual control có thể phù hợp khi:

- Tạo hoặc restore **root KEK, CA key, recovery secret**.
- Thay policy để một key được sử dụng cho purpose/operation mới.
- **Export raw private key/KEK**, import key nhạy cảm.
- Mở quyền `Decrypt` hoặc `Sign` ngoài workflow.
- Destroy key khiến dữ liệu không thể khôi phục.
- Xử lý break-glass hoặc key ceremony có rủi ro cao.

**Dual control, split knowledge và M-of-N là các khái niệm khác nhau.** Chúng phải được thực hiện bằng workflow/cryptographic mechanism có bảo đảm, không chỉ hai nút bấm từ hai tài khoản do cùng một người kiểm soát.

## 21. Vòng đời khóa và key-purpose compatibility

Key purpose phải được tôn trọng ở mọi trạng thái, không chỉ khi key đang ACTIVE.

| State/giai đoạn | Nguyên tắc sử dụng |
| --- | --- |
| **Pre-activation** | Chưa cho phép new-use production; xác minh purpose/usage/IAM |
| **Active** | Chỉ cho phép operation đúng purpose và cryptoperiod |
| **Suspended** | Chặn operation theo policy; xử lý cached plaintext key |
| **Deactivated** | Dừng new-use; có thể giữ **legacy decrypt/verify** theo retention |
| **Compromised** | Cô lập, thay vật liệu và đánh giá mọi purpose đã từng dùng |
| **Destroyed** | Chỉ sau khi đã xử lý dữ liệu, backup và retention |
| **Rotation** | Sinh vật liệu mới, chuyển writer, giữ reader legacy đúng phạm vi |

### Một key v1 được dùng cho nhiều purpose thì rotation khó hơn

Khi một secret đồng thời dùng cho **webhook MAC** và **database encryption**, đổi secret vì sự cố webhook có thể làm reader mất khả năng giải mã dữ liệu cũ.

Tách material từ đầu cho phép:

- Rotate **webhook HMAC key** không chạm ciphertext dữ liệu.
- Rotate **DEK** và re-encrypt record nếu cần.
- Rotate **KEK** và rewrap DEK nếu mục tiêu chỉ thay khóa bọc.
- Rotate **signing key** và phát public verification key/certificate mới.

### Rewrap không phải re-encrypt

Nếu raw **DEK** bị lộ, rewrap **cùng DEK** bằng KEK mới **không khôi phục confidentiality**. Đối thủ có DEK vẫn decrypt được ciphertext cũ. Cần cân nhắc **thay DEK, re-encrypt dữ liệu và đánh giá bản sao lịch sử**.

Nếu lộ **KEK**, phải xác định những wrapped DEK nào có thể bị giải bọc, không tự suy ra tất cả DEK đã hoặc chưa lộ khi chưa điều tra.

### Key version phải phản ánh vật liệu thực

Đổi alias từ `key-v1` thành `key-v2` nhưng vẫn trỏ tới cùng key material **không phải cryptographic rotation**. Cần xác minh origin, material version và behavior qua provider.

## 22. Audit và phát hiện cross-purpose key use

**Audit** cần trả lời: **principal nào đã sử dụng key nào cho operation và purpose nào, với decision/outcome gì?**

### Event ví dụ

~~~yaml
schemaVersion: "1"
eventType: "KEY_USE_DECISION"
requestId: "req-2030-0021"
occurredAtUtc: "2030-05-12T11:20:00Z"
actor: "webhook-service-prod"
resource:
  keyId: "billing-dek-v2"
  keyVersion: "v2"
  registeredPurpose: "INVOICE_DATA_ENCRYPTION"
requested:
  operation: "GenerateMac"
  purpose: "WEBHOOK_AUTHENTICATION"
  tenantScope: "partner-a"
authorization:
  decision: "DENY"
  reasonCode: "WRONG_KEY_PURPOSE"
  policyRevision: "policy-v19"
execution:
  providerOperationInvoked: false
  outcome: "NOT_EXECUTED"
auditCorrelationId: "corr-9a11"
~~~

Đây là **schema minh họa**, không phải log chuẩn chung cho mọi KMS/HSM. Không lưu **raw key bytes, HSM PIN, plaintext, request body nhạy cảm hoặc access token** trong event.

### Những tín hiệu đáng giám sát

- Key `DATA_ENCRYPTION` bất ngờ xuất hiện trong operation `GenerateMac`/`Sign`/`Wrap`.
- Key được dùng từ **staging** trên tài nguyên production.
- Workload bắt đầu truy vấn **tenant khác** hoặc data scope chưa được phê duyệt.
- `CreateGrant`/`ChangePolicy` xảy ra ngay trước một lần `Decrypt` bất thường.
- Aliases được đổi để trỏ tới key material của purpose khác.
- Một private signing key bị dùng qua API/endpoint **không yêu cầu approval digest**.
- DEK bị export hoặc xuất hiện trong log/secret manager ngoài nơi bảo vệ.
- Key đã deactivated vẫn tạo **ciphertext/signature mới**.
- KDF context không có purpose hoặc xuất hiện nhãn trùng giữa các subkey.

### Đừng nhầm provider success với business authorization

HSM có thể `Sign` đúng phép mật mã trên digest do client đưa, nhưng digest đó **có thể là artifact không được phê duyệt**. Cần kết hợp **application audit, IAM/control-plane audit và KMS/HSM operation audit** để xác định hành động có đúng mục đích thật không.

### Điểm mù của raw DEK cached

Một **DEK plaintext** được ứng dụng cache có thể được dùng hàng nghìn lần mà **không tạo thêm KMS event**. 0 lượt `Unwrap` trong hôm nay không chứng minh 0 lượt local decrypt.

Phải kiểm toán **business data access, cache policy và key use tại ứng dụng** mà không ghi secret.

## 23. Kiểm thử chống dùng lại key sai mục đích

Không thể chứng minh an toàn chỉ bằng cách sinh 100 keys rồi kiểm tra các bytes khác nhau. Cần cả **key provenance, policy, integration tests và threat model**.

### Negative tests

~~~text
1) service = webhook-sender
   request = GenerateMac(keyId = billing-dek-v2)
   expected = DENY (wrong key purpose)

2) service = billing-writer
   request = Decrypt(keyId = billing-dek-v2)
   expected = DENY tại provider/service boundary

3) service = invoice-signer
   request = Sign(keyId = invoice-ecdh-key-v1)
   expected = DENY (wrong algorithm/purpose/usage)

4) service = staging-app
   request = Encrypt(keyId = production-dek-v2)
   expected = DENY (environment mismatch)

5) service = tenant-a-worker
   request = DeriveSubkey(master, info = tenant-b-domain)
   expected = DENY (cross-tenant derivation)

6) service = billing-service
   request = CreateGrant(Decrypt -> itself)
   expected = DENY (self-escalation)

7) service = old-writer
   request = Encrypt(keyId = deactivated-dek-v1)
   expected = DENY (no new-use)

8) service = reviewer
   request = ExportRawKey(keyId = root-kek)
   expected = DENY (custody/export policy)
~~~

### Test integrity và data correctness

- **GCM wrong nonce strategy:** kiểm tra thiết kế uniqueness qua multi-node/restart/restore, không cố cố tình tái sử dụng nonce production.
- **AAD mismatch:** thay tenant/record/key version phải làm decrypt authentication fail.
- **Wrong DEK:** sai key phải bị từ chối, không fallback “thử hết khóa”.
- **Signing key switch:** artifact ký bởi key version mới phải xác minh với public key/certificate tương ứng.
- **KDF vectors:** implement HKDF phải đối chiếu test vectors chuẩn, không chỉ kiểm tra hai đầu ra không trùng.
- **Key lifecycle:** suspended/compromised key bị chặn ở provider, không chỉ ở mock.
- **Backup restore:** dữ liệu cũ vẫn decrypt/verify được trong phạm vi hợp lệ sau rotation.

### Test operational boundaries

- Một principal có thể gọi **provider API trực tiếp** để bypass app policy không?
- Một admin có thể sửa key policy rồi tự dùng secret và xóa log không?
- Có plaintext DEK trong CI logs, env vars, file backup hoặc crash dump không?
- Key inventory có ghi cả KDF parent/child và wrapped DEK/KEK dependencies không?
- Incident team có thể liệt kê mọi nơi cùng material từng được import không?

**Integration test ở đúng boundary mới chứng minh controls được cưỡng chế.** Unit test `if (purpose != ...)` chỉ kiểm tra logic cục bộ.

## 24. Case study: Billing dùng một secret cho AES và webhook HMAC

### Bối cảnh

Billing v1 lấy `BILLING_MASTER_SECRET` từ biến môi trường. Mã ứng dụng dùng chính bytes đó cho:

~~~text
new SecretKeySpec(secret, "AES")         -> encrypted invoices
new SecretKeySpec(secret, "HmacSHA256")  -> partner webhook MAC
~~~

Đối tác cần verify webhook, nên nhóm gửi secret qua một kênh provisioning. Một ngày đối tác báo bị lộ credential.

### Đánh giá rủi ro

1. **Raw secret chung đã được chia sẻ** cho đối tác.
2. Nếu attacker giữ secret, họ có thể tính MAC và có khả năng giải mã những invoice được mã hóa dưới cùng key nếu có ciphertext.
3. Đổi webhook key trong cấu hình mà **giữ cùng DEK** có thể vẫn để lộ dữ liệu cũ.
4. Nếu đổi raw key toàn bộ trong một bước, reader có thể không còn đọc được ciphertext cũ.
5. KMS/HSM không thể bảo vệ một raw secret đã phân phối ra ngoài chỉ bằng cách thay alias.

### Thiết kế cải thiện

| Purpose | Key mới | Nơi giữ và quyền |
| --- | --- | --- |
| Invoice data | `invoice-dek-v2` AES-GCM | DEK độc lập, scope theo tenant/data |
| DEK wrapping | `billing-kek-v2` | KMS/HSM, restricted Wrap/Unwrap |
| Partner webhook MAC | `partner-a-hmac-v2` | Secret riêng cho đối tác, rotation định kỳ |
| Invoice signature | `invoice-signing-v2` | Private signing key ở HSM khi cần |
| Agreement | `partner-agreement-v2` | Key pair riêng theo protocol AKE |

### Quy trình chuyển đổi

1. **Inventory:** tìm dữ liệu và các service dùng `BILLING_MASTER_SECRET`.
2. **Incident scope:** xác định những ciphertext cũ và webhook messages có thể bị ảnh hưởng.
3. **Generate:** tạo **DEK, KEK, HMAC key và signing keys riêng** qua nguồn tin cậy.
4. **Deploy readers:** hỗ trợ key version cũ/mới với legacy decrypt được kiểm soát.
5. **Cutover writers:** dữ liệu mới dùng DEK v2, webhook mới dùng HMAC v2.
6. **Re-encrypt** dữ liệu liên quan nếu raw DEK cũ đã lộ; xử lý nonce/AAD/metadata/version đúng.
7. **Revoke old secret** và xử lý backups/caches theo retention và incident policy.
8. **Audit:** chứng minh không còn new-use key cũ, không service khác dùng HMAC key làm DEK.

### Điểm không được kết luận

**Mã hóa lại hôm nay không xóa được ciphertext/raw key mà đối thủ đã sao chép trước đó.** Cần đánh giá dữ liệu đã lộ, nghĩa vụ thông báo và lịch sử từ thời điểm key có thể bị compromise.

## 25. Case study: cùng cặp RSA cho giải mã và ký JWT

Một identity service dùng **cùng RSA private key** để giải mã các secret được gửi cho server và ký access token. Điều này trộn **key transport/decryption** với **token-signing trust**.

### Vấn đề

- Decryption endpoint và signing endpoint trở thành hai đường tương tác với **cùng private key**.
- Lộ hoặc lạm dụng quyền decryption có thể làm tăng rủi ro cho signing domain, và ngược lại, tùy protocol/implementation.
- Việc rotate token signing key có thể ảnh hưởng những ciphertext gửi trước đó.
- KMS key usage/IAM khó tách biệt khi key cùng gánh hai chức năng.
- Logs/approval khó chỉ ra mỗi operation đúng cryptographic purpose.

### Thiết kế mới

~~~text
rsa-transport-key-v2:
    purpose = DATA_KEY_TRANSPORT
    operation = RSA-OAEP decrypt hoặc KEM flow tương ứng

jwt-signing-key-v2:
    purpose = TOKEN_SIGNING
    operation = RSA-PSS/approved signing algorithm
    verifier = JWKS/certificate qua trust channel
~~~

Nếu giao thức cho phép, dùng **hybrid public-key encryption/HPKE** cho việc trao đổi secret, và **signing key riêng** cho JWT.

### Cutover

- Cập nhật bên gửi/recipient trước khi ngừng transport key cũ.
- Phân phối **JWKS/public verification key mới** trước khi phát JWT ký bằng key v2.
- Giữ public verification key cũ đủ cho token hoặc chữ ký còn hiệu lực theo retention.
- Ngừng new decrypt/new sign bằng key cũ theo chính sách, nhưng đừng hủy trước khi hoàn tất dependencies.
- Kiểm tra `alg`, `kid`, trust và authorization không cho client chỉ định thuật toán tùy ý.

**Tách key pair không thay thế kiểm tra certificate/JWKS hoặc business authorization.**

## 26. Case study: HKDF có nhãn sai gây trùng subkeys

Một key schedule dùng:

~~~text
K_a = HKDF-Expand(PRK, info = app || role || purpose, L=32)
K_b = HKDF-Expand(PRK, info = app || role || purpose, L=32)
~~~

Các trường là chuỗi biến độ dài nhưng được nối trực tiếp không có delimiter hoặc length-prefix. Những tuple khác nhau có thể tạo cùng `info`.

### Hậu quả

- Các purpose/tenant khác nhau có thể **nhận cùng subkey** nếu context bytes trùng.
- Một bug ở parser có thể khiến API dẫn xuất key cho sai role.
- Unit test với một số nhãn thông thường không nhất thiết phát hiện mọi collision.
- Nếu master bị lộ, toàn bộ subkeys đã dẫn xuất dưới master đó có thể bị ảnh hưởng.

### Cải thiện

1. Định nghĩa **schema context chính tắc** có domain tag, version, purpose, tenant và role.
2. Mỗi trường được length-prefix hoặc dùng encoding chuẩn không mơ hồ.
3. Cố định **approved contexts** cho các purpose quan trọng; không nhận `info` tùy tiện từ request.
4. Kiểm thử cross-purpose collisions với các input ranh giới.
5. So với **RFC 5869 test vectors** cho implementation KDF.
6. Lưu **lineage master→subkey** trong inventory, không lưu raw material.
7. Nếu đã có subkeys sai purpose, tạo key schedule mới và migrate dữ liệu/giao thức, không chỉ sửa tên hiển thị.

## 27. Sai lầm phổ biến và cách phòng tránh

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng cùng raw 32 byte cho AES và HMAC | Lộ một purpose có thể lộ purpose kia | Key riêng hoặc HKDF domain-separated đúng |
| Dùng DEK trực tiếp để wrap key khác | Trộn dữ liệu và key hierarchy | KEK riêng, key wrapping chuẩn |
| Dùng RSA key pair cho OAEP và PSS tùy tiện | Tăng cross-protocol/key-usage risk | Tách transport/decryption và signing key pair |
| Dùng một EC key cho ECDSA và ECDH tùy tiện | Trộn signing và agreement protocol | Tạo pair riêng và AKE chuẩn |
| Tự chuyển Ed25519 private key sang X25519 | Sai assumptions/implementation risk | Dùng khóa riêng theo giao thức |
| Coi hai alias khác nhau là hai material độc lập | Thực tế có thể dùng chung bytes | Kiểm tra key provenance/material version |
| Dùng một key prod trong staging | Trust boundary bị chia sẻ | Tạo keys riêng theo environment |
| Dùng cùng HMAC secret cho mọi partner | Compromise một partner ảnh hưởng tất cả | Secret riêng theo partner và version |
| Dùng cùng raw DEK cho tenant cần cách ly | Blast radius lớn | Key granularity theo tenant/object |
| Dùng `SHA-256(master||label)` tự chế | Có thể sai thiết kế KDF/domain separation | HKDF/KDF chuẩn, approved labels |
| Coi HKDF subkeys là độc lập tuyệt đối | Lộ master ảnh hưởng mọi child | Bảo vệ master, inventory lineage |
| Ghép KDF `info` không canonical | Trùng context ngoài ý định | Length-prefix/versioned encoding |
| Cho client chọn purpose/tenant derive tự do | Cross-tenant/cross-purpose use | Authorization trước derive |
| Dùng AES-GCM nonce cố định/lặp | Có thể phá confidentiality/integrity | Quản lý nonce uniqueness và usage limits |
| Tạo key bằng timestamp/PID/`Random` | Secret dễ đoán | CSPRNG/DRBG chuẩn |
| Nghĩ `CKA_ENCRYPT` bảo vệ key sau raw export | Attributes không áp dụng ngoài token | Non-exportability, key custody |
| Nghĩ KMS key type `ENCRYPT_DECRYPT` cấp quyền mọi operation | Hiểu sai phân quyền | IAM theo principal/action/resource |
| Writer có raw DEK mà tuyên bố không thể decrypt | Có thể giải mã offline | Kiến trúc boundary phù hợp |
| Key owner tự duyệt và dùng key không audit | SoD không thực | Dual control/PAM và independent audit |
| Chỉ unit test policy, không gọi provider | Có thể bypass bằng API khác | Integration negative tests |
| Dùng alias mới nhưng vẫn raw material cũ | Không rotation thật | Sinh key mới và kiểm tra version |
| Rewrap DEK đã lộ rồi tuyên bố an toàn | Đối thủ vẫn decrypt được ciphertext | Thay DEK, re-encrypt và incident response |
| Xóa old KEK/DEK khi còn archive | Mất khả năng khôi phục | Dependency inventory và restore drills |
| Không ghi parent/child của KDF | Không xác định phạm vi master compromise | Inventory lineage và cryptoperiod |
| In raw key để xác minh uniqueness | Lộ key trong log/SIEM | Chỉ log ID và provenance |
| Thấy output hai key khác nhau nên tuyên bố RNG an toàn | Thử nghiệm không chứng minh security | Đánh giá provider/entropy và chuẩn |
| Dùng HMAC tag thay chữ ký số | Không có public verification/non-repudiation phù hợp | Chọn primitive theo mục tiêu |
| Dùng ECDH không peer authentication | MITM | Authenticated key exchange |
| Giữ một secret vô thời hạn vì nhiều service phụ thuộc | Tăng blast radius và nợ rotation | Tách purpose và chiến lược migration |

## 28. Checklist production — Không dùng lại key sai mục đích

### Thiết kế và sinh khóa

1. **Purpose rõ:** Mỗi key có mục đích, thuật toán, protocol, dữ liệu và owner được xác định?
2. **Granularity:** Key scope per service/tenant/partner/object hợp lý với blast radius?
3. **Material separation:** Không copy cùng raw bytes sang AES/HMAC/KEK/signing/agreement?
4. **Environment:** Không dùng chung key production với test/staging?
5. **Algorithm:** Key length, mode, curve, signature/wrapping scheme được phê duyệt?
6. **Entropy:** Key generation dùng CSPRNG/DRBG/KMS/HSM và kiểm soát seed/snapshot?
7. **KDF:** Nếu subkey từ master, có HKDF/KDF chuẩn, context canonical, purpose labels và lineage?
8. **Master compromise:** Runbook xác định được tất cả descendants, không tuyên bố subkeys độc lập tuyệt đối?
9. **Asymmetric roles:** Encryption key pair, signing key pair, agreement key pair tách đúng purpose?
10. **Pre-activation:** Key mới chưa dùng production cho đến khi policy/test đạt?

### Phân quyền và vận hành

11. **Key usage:** KMS/HSM/PKCS#11 cho phép đúng operations, đúng key attributes?
12. **IAM:** Principal được xác thực và cấp tối thiểu theo key ID/version/operation?
13. **Tenant/business scope:** Không để user chọn tenant/purpose tùy ý rồi vượt quyền?
14. **Indirect access:** `CreateGrant`, policy edit, secret export, backups, decryption oracle có bị kiểm soát?
15. **Raw key handling:** DEK plaintext không bị log/copy vào nơi ngoài boundary?
16. **DEK/KEK separation:** Encryption và wrapping khác material và permission?
17. **GCM nonce:** Không lặp nonce dưới cùng key; có giới hạn use và xử lý multi-node/restart?
18. **AAD/tag:** Context chính tắc, reader xác minh authentication tag trước khi tin plaintext?
19. **HMAC protocol:** Secret riêng theo partner và có anti-replay/rotation?
20. **Signing:** `Sign` chỉ áp lên digest/manifest đúng workflow đã phê duyệt?
21. **Agreement:** ECDH/X25519 có peer authentication và KDF/key schedule chuẩn?
22. **Dual control:** Thay purpose/rights, export/recovery/destroy cần approval độc lập khi rủi ro cao?
23. **Inventory:** Có provenance, material version, parent-child, KEK–DEK và data dependencies?
24. **Audit:** Ghi actor, key ID/version, registered/requested purpose, action, allow/deny, outcome và policy revision mà không chứa secret?

### Rotation, tests và incident response

25. **Cryptoperiod:** Key state và hạn dùng cho new-use/legacy use được kiểm soát?
26. **Rotation:** Sinh material mới, reader-first/writer cutover và không tiếp tục dùng key cũ ngoài policy?
27. **Rewrap vs re-encrypt:** Hiểu đúng loại khóa nào bị thay và khi raw DEK lộ cần làm gì?
28. **Backup/DR:** Có restore drill, biết archive/replica nào còn phụ thuộc old key?
29. **Negative tests:** Sai purpose, tenant, env, principal, operation, lifecycle đều bị provider từ chối?
30. **KDF tests:** Có test vectors và kiểm thử context collision/encoding?
31. **Compromise scope:** Khi một key lộ, có thể xác định **toàn bộ purpose và data** đã từng dùng material đó?
32. **Post-incident:** Có kế hoạch loại key dùng sai, migrate dữ liệu/trust, thu hồi grants, sửa nguồn sinh và audit?
33. **Monitoring:** Có cảnh báo key xuất hiện ở service/protocol trái purpose hoặc trạng thái đã deactivated?
34. **Success criteria:** Có chứng cứ rằng hệ thống **không còn dùng chung raw material ngoài danh sách ngoại lệ được phê duyệt**?

### Ghi nhớ

**Không dùng lại key sai mục đích** nghĩa là **không tự ý mang cùng vật liệu mật mã qua các giao thức, thuật toán, vai trò, tenant hoặc trust domains khác nhau**. Một key có thể được sử dụng nhiều lần **trong đúng purpose** nếu quy tắc thuật toán, cryptoperiod và key usage được tuân thủ: ví dụ AES-GCM bảo vệ nhiều record với **nonce không lặp dưới cùng key**, hoặc một key pair ký nhiều tài liệu hợp lệ.

Để bảo vệ hệ thống, hãy tạo **DEK, KEK, HMAC, signing và agreement keys riêng** khi cần, hoặc dẫn xuất **subkeys có domain separation** bằng KDF chuẩn trong một key hierarchy được đánh giá. **Subkey cùng master không độc lập tuyệt đối**: master lộ có thể ảnh hưởng cả cây. **Key ID/alias khác, Java class khác hoặc tên thuật toán khác không chứng minh vật liệu đã tách.** Bảo đảm thực tế đến từ **key provenance, KMS/HSM key usage, IAM least privilege, approval độc lập, kiểm soát raw key, key inventory và audit**.

Khi phát hiện một key đã bị dùng sai mục đích, đừng chỉ đổi tên hoặc policy. Cần **đánh giá những nơi material đã xuất hiện, key nào khác phụ thuộc, dữ liệu/chữ ký/giao thức đã bị ảnh hưởng, sau đó tạo key mới và migrate đúng loại**. Đó là cách biến nguyên tắc key separation thành một **biện pháp giảm blast radius có thể kiểm chứng trong suốt vòng đời khóa**.
