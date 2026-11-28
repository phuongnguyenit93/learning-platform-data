# Key purpose metadata: Khai báo và thực thi mục đích sử dụng khóa mật mã

Một nền tảng thanh toán dùng KMS/HSM để bảo vệ nhiều loại khóa: **KEK** bọc DEK, **DEK** mã hóa dữ liệu bằng AES-GCM, **private signing key** ký hóa đơn, **HMAC key** xác thực webhook và **root secret** dùng dẫn xuất khóa. Các khóa được sinh bằng thuật toán mạnh và lưu tại nhà cung cấp tin cậy. Tuy nhiên, một ngày nhóm phát triển nhận thấy cùng một khóa AES được dùng để vừa **mã hóa dữ liệu khách hàng** vừa **bọc DEK**, bởi vì ứng dụng chỉ lưu trường **algorithm = AES-256**, không ghi trường **purpose** hay giới hạn operation nào được phép.

Vấn đề không phải AES-256 đột nhiên yếu. Vấn đề là **thiết kế không phân tách vai trò của khóa**, khiến người vận hành không thể biết khóa nào phải rotate, service nào được quyền sử dụng, liệu một lỗi Decrypt có thể trở thành Unwrap oracle và mức độ dữ liệu bị ảnh hưởng khi khóa lộ.

**Key purpose metadata** là thông tin có cấu trúc mô tả **một khóa được tạo ra và được phép sử dụng để phục vụ mục đích mật mã/nghiệp vụ nào**. Ví dụ:

- Khóa **customer-data-dek-v7**: mã hóa/giải mã payload AES-GCM của tenant A; không dùng bọc khóa khác.
- Khóa **tenant-a-kek-v3**: bảo vệ DEK bằng Wrap/Unwrap theo policy; không trực tiếp mã hóa dữ liệu nghiệp vụ.
- Khóa **billing-sign-v4**: tạo chữ ký hóa đơn trong Sign API; không xuất private key hoặc dùng để mã hóa.
- Khóa **webhook-partner-x-hmac-v2**: tạo và kiểm tra HMAC cho protocol webhook cụ thể; không dùng làm JWT signing key.
- Khóa **tenant-root-kdf-v1**: chỉ dùng DeriveKey theo context/namespace đã định nghĩa; không gửi root material tới mọi microservice.

Một record metadata tốt giúp **thiết kế, triển khai, kiểm toán và quản lý vòng đời khóa**, nhưng **một nhãn purpose tự nó không chặn được phép toán sai**. Để an toàn, mục đích phải được ánh xạ thành **key type/algorithm, allowed operations, KMS/HSM attributes, IAM/key policy, authorization trong ứng dụng và kiểm tra data plane**.

Trong chương **Key use** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài học kết nối key purpose metadata với vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi/hủy**, mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, phân quyền và kiểm toán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa **key purpose metadata** và phân biệt với **key algorithm**, **allowed operation**, **business purpose**, **keyUsage của certificate**, **key state** và **IAM permission**.
2. Thiết kế key inventory gồm **key ID/version, type, purpose, tenant, environment, owner, provider, storage, exportability, lifecycle, cryptoperiod và operations**.
3. Kiểm tra một operation có hợp lệ với **purpose, key state, identity, tenant, dữ liệu và thời gian** trước khi dùng vật liệu khóa.
4. Liên hệ metadata với **JWK use/key_ops, X.509 KeyUsage/EKU, PKCS#11 usage attributes** và chính sách thực tế của KMS/HSM mà không nhầm các trường với nhau.
5. Ngăn lỗi **cross-purpose key reuse, algorithm confusion, key-substitution, cross-tenant unwrap, signing oracle và metadata tampering**.
6. Hiểu cách **domain separation**, KDF context, AEAD AAD và envelope key version hỗ trợ phân tách purpose nhưng **không thay IAM**.
7. Áp dụng key purpose metadata vào **rotation/revocation, migration, backup/restore, cryptoperiod, audit** và điều tra sự cố.
8. Chạy ví dụ **Java 17** triển khai policy gate metadata trước AES-GCM và Ed25519, minh họa những giới hạn khi enforcement chỉ nằm trong application.

## 2. Key purpose là gì và không phải là gì?

### 2.1. Purpose trả lời câu hỏi khác algorithm

| Trường | Câu hỏi trả lời | Ví dụ | Điều không thể suy ra |
|---|---|---|---|
| **Algorithm** | Dùng thuật toán nào? | AES-256-GCM, Ed25519, HMAC-SHA256 | AES-256 có được dùng làm KEK hay DEK không? |
| **Key type/class** | Key thuộc loại vật liệu nào? | Symmetric, asymmetric private/public, secret, key handle | Khóa có quyền ký mọi tài liệu hay không? |
| **Cryptographic purpose** | Khóa phục vụ chức năng mật mã nào? | CONTENT_ENCRYPTION, DATA_KEY_WRAPPING, DIGITAL_SIGNATURE | Caller có quyền với record nào? |
| **Business purpose** | Phục vụ quy trình nghiệp vụ nào? | BILLING_INVOICE_SIGNING, CUSTOMER_PII, WEBHOOK_PARTNER_X | Provider có enforce business rule này không? |
| **Allowed operations** | Có thể gọi API nào? | ENCRYPT, DECRYPT, WRAP, UNWRAP, SIGN, VERIFY | Operation được phép với mọi dữ liệu không? |
| **Authorized principals** | Ai được dùng khóa? | billing-signer, customer-reader, restore-worker | Một user cuối có quyền với hóa đơn/record cụ thể? |
| **Key state** | Hiện tại khóa được dùng trong giai đoạn nào? | ACTIVE, DECRYPT_ONLY, SUSPENDED, DESTROYED | Purpose ban đầu có thay đổi khi trạng thái đổi không? |
| **Exportability** | Raw material có được đưa khỏi provider? | NON_EXPORTABLE, APPROVED_WRAP_ONLY | Sign/Decrypt API không thể bị lạm dụng? |
| **Key ID/version** | Khóa vật lý/logical version nào? | tenant-a-kek/v3 | Principal có được phép dùng chỉ vì biết ID? |

Ví dụ **AES-256** có thể xuất hiện ở hai nơi:

~~~text
Key A:
  keyType     = SYMMETRIC
  algorithm   = AES-256-GCM
  purpose     = CONTENT_ENCRYPTION
  operations  = ENCRYPT, DECRYPT
  scope       = tenant-A / invoice-data

Key B:
  keyType     = SYMMETRIC
  algorithm   = AES-KW (KEK sử dụng AES)
  purpose     = DATA_KEY_WRAPPING
  operations  = WRAP, UNWRAP
  scope       = tenant-A / envelope-DEK
~~~

**Hai khóa cần tách key material** dù đều thuộc họ AES. Không lấy cùng 32 byte của Key A làm KEK của Key B chỉ vì hai API đều nhận một mảng byte có kích thước hợp lệ.

### 2.2. Purpose không phải tên gọi tùy ý

Đặt tên **production-master-key** hay **current-secret** không đủ để biết:

- khóa dùng cho **MAC** hay **mã hóa**;
- được cấp **raw key** hay chỉ key handle;
- có được **Sign** ngoài luồng phê duyệt không;
- khóa thuộc tenant nào và có thể chia sẻ cross-tenant không;
- cryptoperiod cho Encrypt mới khác thời hạn Decrypt/Verify cũ như thế nào;
- ai chịu trách nhiệm rotate, revoke, destroy và restore.

Purpose nên có **taxonomy ổn định, kiểm soát version, owner, key usage policy và validation**. Hạn chế dùng chuỗi tự do kiểu **purpose = misc** hay **purpose = any** cho production. Nếu có trường ngoại lệ, cần người duyệt, phạm vi, TTL và audit riêng.

### 2.3. Hai tầng: “khóa dùng cho việc gì” và “ai được làm việc đó”

~~~mermaid
flowchart TD
    R["Yêu cầu: principal, tenant, record, operation, keyRef"] --> I["Xác thực workload/user identity"]
    I --> B["Business authorization: có quyền với record?"]
    B --> M["Trusted key inventory: purpose, algorithm, state, version"]
    M --> P["Key-use policy: purpose + allowed operations + principal"]
    P --> K["Provider KMS/HSM/IAM enforcement"]
    K --> C["Crypto operation: Sign / Decrypt / Wrap / MAC"]
    C --> A["Audit: decision, keyRef, operation, outcome"]
~~~

Một key record ghi **purpose = CUSTOMER_DATA** không ngăn một KMS role được cấp **Decrypt** quá rộng. **Metadata là dữ liệu dùng ra quyết định; enforcement phải tồn tại tại đúng ranh giới mà thao tác được thực thi.**

## 3. Cấu trúc metadata đề xuất cho key inventory

### 3.1. Bộ trường cốt lõi

| Nhóm | Trường đề xuất | Ý nghĩa |
|---|---|---|
| **Identity** | keyId, version, providerKeyRef, familyId | Nhận diện bất biến một key version/material |
| **Cryptography** | keyType, algorithm, keySize/curve, keyPurpose, allowedOperations | Xác định đúng cơ chế và giới hạn key reuse |
| **Business scope** | businessPurpose, tenantId, environment, resourceDomain | Tách dữ liệu/ứng dụng và độ nhạy cảm |
| **Ownership** | keyOwner, securityOwner, technicalCustodian | Ai duyệt, vận hành, kiểm tra và chịu trách nhiệm |
| **Storage** | provider, region/partition, HSM/KMS/vault, exportability | Nơi material nằm và ranh giới có thể xuất |
| **Lifecycle** | state, createdAt, activatedAt, encryptUntil, decryptUntil, retirementAt | Phân biệt thời hạn tạo ciphertext mới và đọc lịch sử |
| **Authorization** | allowedPrincipals, policyRef/revision, constraints | Nối metadata với IAM/key policy thực |
| **Protocol binding** | dataFormatVersion, aadSchema, kdfContext, issuer/audience | Đảm bảo đúng giao thức/namespace |
| **Recovery** | backupDomain, dependencies, migrationStatus, rotationPlan | Không hủy khóa vẫn còn bảo vệ archive |
| **Audit** | lastReview, lastUsed, policyChangeRef, incidentRef | Truy vết quản trị mà không lưu raw key |

**Đây không phải yêu cầu mọi provider phải có đúng những field này.** Nhiều trường là metadata của **application key registry/inventory**, không phải thuộc tính native mà KMS/HSM có thể enforce. Cần ánh xạ hai lớp bằng reference đáng tin và kiểm tra drift.

### 3.2. Schema ví dụ: Ba key purpose khác nhau

~~~yaml
schemaVersion: 1
keys:
  - keyId: tenant-a-invoice-dek
    version: 7
    type: SYMMETRIC_SECRET
    algorithm: AES-256-GCM
    keyPurpose: CONTENT_ENCRYPTION
    businessPurpose: INVOICE_PII
    tenantId: tenant-a
    environment: production
    state: ACTIVE
    allowedOperations: [ENCRYPT, DECRYPT]
    owner: invoice-data-owner
    storage: APPROVED_CRYPTO_BOUNDARY
    exportability: RESTRICTED
    contentAadSchema: invoice-record-v2
  - keyId: tenant-a-kek
    version: 3
    type: SYMMETRIC_SECRET
    algorithm: AES-KW
    keyPurpose: DATA_KEY_WRAPPING
    businessPurpose: ENVELOPE_DEK_PROTECTION
    tenantId: tenant-a
    environment: production
    state: ACTIVE
    allowedOperations: [WRAP, UNWRAP]
    owner: platform-key-owner
    storage: APPROVED_KMS_HSM
    exportability: NON_EXPORTABLE
    providerKeyRef: provider/account/region/tenant-a-kek-v3
  - keyId: billing-signing
    version: 4
    type: ASYMMETRIC_PRIVATE
    algorithm: Ed25519
    keyPurpose: DIGITAL_SIGNATURE
    businessPurpose: BILLING_INVOICE_SIGNATURE
    tenantId: tenant-a
    environment: production
    state: ACTIVE
    allowedOperations: [SIGN]
    owner: billing-key-owner
    storage: APPROVED_HSM
    exportability: NON_EXPORTABLE
    providerKeyRef: provider/partition/billing-sign-v4
~~~

Đoạn YAML là **mô hình minh họa** để giải thích metadata; **không phải cấu hình KMS/HSM thực thi được**. Không thêm trường hoặc thay metadata của các file bài học từ ví dụ này. Tên **keyId**, **providerKeyRef** và **tenant** trong ví dụ không đại diện tài sản thật. Các field **exportability = NON_EXPORTABLE** phải được xác minh bằng **thuộc tính provider**; viết chữ đó trong YAML tự tạo **không** khiến khóa trở thành non-exportable.

### 3.3. Khi nào purpose nên chia thành hai trường?

Mục đích mật mã thường có tính phổ quát (**DIGITAL_SIGNATURE**, **DATA_KEY_WRAPPING**, **HMAC_AUTHENTICATION**), còn mục đích nghiệp vụ cần chi tiết theo tổ chức (**INVOICE_SIGNATURE**, **CUSTOMER_PII_AT_REST**, **PAYMENT_WEBHOOK**).

Tách hai trường có lợi:

- **Crypto validation:** một Digital Signature key chỉ được phép SIGN/VERIFY theo key type; không dùng làm KEK.
- **Resource authorization:** khóa ký hóa đơn chỉ ký **hóa đơn đã được duyệt**, không ký tùy ý các thông điệp khác.
- **Inventory reporting:** tìm mọi key dùng ký và lọc riêng keys của Billing.
- **Incident scope:** một HMAC key của đối tác X không đồng nghĩa mọi HMAC key của tổ chức bị lộ.

Không biến business purpose thành một chuỗi quá chi tiết đến mức mỗi request tạo một loại metadata mới. **Taxonomy nên có hierarchy hoặc codebook được quản lý**, ánh xạ purpose ổn định tới policy.

## 4. Phân loại purpose theo loại khóa

| Key purpose | Key/material điển hình | Allowed operations | Không nên dùng để |
|---|---|---|---|
| **CONTENT_ENCRYPTION** | AES-GCM DEK | ENCRYPT, DECRYPT | Wrap DEK khác, Sign, GenerateMac |
| **DATA_KEY_WRAPPING** | AES-KW/KWP KEK hoặc KMS wrapping key | WRAP, UNWRAP | Payload encryption tùy ý, HMAC chung |
| **DIGITAL_SIGNATURE** | Ed25519/ECDSA/RSA-PSS private key | SIGN; public key VERIFY | Decrypt DEK, mã hóa customer data |
| **PUBLIC_KEY_ENCRYPTION** | RSA-OAEP private/public keypair | ENCRYPT/WRAP bằng public, DECRYPT/UNWRAP bằng private theo protocol | Sign bằng cùng keypair không được duyệt |
| **HMAC_AUTHENTICATION** | HMAC-SHA256 secret | GENERATE_MAC, VERIFY_MAC | Encrypt hoặc làm signing key non-repudiation |
| **KEY_DERIVATION** | HKDF root/IKM hoặc KDF provider handle | DERIVE_KEY theo context cho phép | Export root cho mọi service |
| **TLS_CLIENT_AUTH** | mTLS private key/certificate theo profile | TLS handshake/Proof-of-possession | Ký hóa đơn nghiệp vụ hoặc unwrap DEK |
| **TOKEN_SIGNING** | JWT/JWS issuer private key | SIGN token đúng issuer/audience/policy | Ký firmware hoặc tài liệu nghiệp vụ khác |
| **FIRMWARE_CODE_SIGNING** | Private code-signing key | SIGN artifact đã qua release approval | Ký JWT hoặc webhook payload |
| **BACKUP_RECOVERY** | HSM recovery share/backup wrapping key | RECOVER/RESTORE theo quorum | Encrypt dữ liệu tùy ý hoặc mở rộng IAM tự động |

**Không suy allowed operations chỉ từ thuật toán**. Ví dụ cùng Ed25519 có thể được dùng cho **JWT signing** hoặc **firmware signing**, nhưng nên dùng **hai keypairs riêng** để tránh một dịch vụ có quyền Sign của giao thức này tạo chữ ký hợp lệ trong giao thức kia.

### 4.1. Đối xứng: DEK, KEK và HMAC

Một DEK AES-256 được dùng cho **payload content encryption** và một KEK AES-256 được dùng cho **key wrapping** có thể cùng độ dài, nhưng **không có cùng purpose**. Nên sinh material độc lập; nếu có key hierarchy, cần KDF có domain separation rõ và policy tại boundary.

**HMAC key** phải được phân phối theo sender/receiver và protocol. Bên biết HMAC key có thể tạo tag hợp lệ, nên HMAC **không tự cung cấp tính không thể chối bỏ** như chữ ký số bất đối xứng. Không dùng HMAC secret đã cấp cho webhook làm root để dẫn xuất khóa cơ sở dữ liệu.

### 4.2. Bất đối xứng: Ký khác mã hóa

Một private signing key không được đưa cho service chỉ Verify. Ngược lại một public encryption key dùng bọc DEK cần được xác thực **recipient identity**, chứ không phải chỉ kiểm tra key length. Với RSA, dù keypair về mặt toán học có thể sử dụng trong nhiều primitive, **tái sử dụng cùng keypair cho RSA-OAEP và RSA-PSS** không nên là mặc định; hãy phân chia theo purpose/giao thức và provider policy.

### 4.3. KDF root và domain separation

Với HKDF, một master/IKM có thể dẫn xuất nhiều khóa, nhưng cần phân biệt rõ **info/context và output length/type**:

~~~text
IKM (được bảo vệ bởi KMS/HSM)
   |
   +-- HKDF(info="app:v1/tenant-A/invoice-encryption")
   |      -> DEK_Invoice_Tenant_A
   |
   +-- HKDF(info="app:v1/tenant-A/webhook-hmac")
   |      -> HMAC_Webhook_Tenant_A
   |
   +-- HKDF(info="app:v1/tenant-B/invoice-encryption")
          -> DEK_Invoice_Tenant_B
~~~

Các giá trị trong ví dụ là nhãn logic, **không phải thiết kế KDF production hoàn chỉnh**. Phải tuân thủ **HKDF-Extract/Expand, IKM entropy, salt handling, info encoding, output length và provider contract**; không dùng SHA-256(root || text) như một KDF tự chế. **Domain separation giảm nguy cơ dùng nhầm derived key** nhưng không sửa được việc **root secret đã bị lộ** hoặc principal có quyền DeriveKey tùy ý.

## 5. Key purpose metadata trong JWK, X.509, PKCS#11 và KMS/HSM

Không có một trường **purpose** chuẩn duy nhất tương đương cho mọi hệ thống mật mã. Các chuẩn, chứng thư và sản phẩm có **ngữ nghĩa khác nhau**. Cần phân biệt **metadata mô tả**, **constraints được provider thực thi** và **policy nghiệp vụ**.

### 5.1. JWK: use, key_ops, alg và kid

Một **JSON Web Key (JWK)** có thể có những trường:

| JWK member | Ý nghĩa | Lưu ý |
|---|---|---|
| **kty** | Loại khóa, ví dụ OKP, EC, RSA, oct | Không đủ xác định purpose hoặc caller được phép |
| **crv** | Curve/type trong một số key types | Phải tương thích thuật toán và thư viện |
| **use** | Public key use, thường **sig** hoặc **enc** | Định hướng mục đích, không phải IAM |
| **key_ops** | Danh sách operation, ví dụ sign/verify/encrypt/decrypt/wrapKey/unwrapKey/deriveKey | Nếu có cùng use, phải nhất quán ngữ nghĩa |
| **alg** | Thuật toán intended cho key, theo JOSE | Không chấp nhận algorithm tùy ý từ token header |
| **kid** | Định danh khóa | Không là secret hoặc quyền truy cập |

Một JWK **public** minh họa metadata cho khóa dùng xác minh chữ ký:

~~~json
{
  "kty": "OKP",
  "crv": "Ed25519",
  "kid": "billing-sign-v4",
  "use": "sig",
  "key_ops": ["verify"],
  "alg": "EdDSA",
  "x": "<BASE64URL_PUBLIC_KEY_BYTES>"
}
~~~

**Placeholder** trên không phải JWK dùng được trong thực tế. Nó chỉ minh họa field. **Không đưa private key member vào JWKS công khai.** Một issuer ký token thường quản lý private key riêng; JWKS chứa public verification material.

Quan trọng:

- **use = sig** và **key_ops = verify** trong public JWK có thể hợp lý: public key chỉ xác minh, private key riêng để Sign.
- **use = enc** không đồng nghĩa key đã được phép mở mọi tenant's EDK; recipient identity và application policy vẫn cần.
- **key_ops** và **alg** được khai báo không làm key tự an toàn nếu verifier **không kiểm tra** hoặc **tin untrusted JWK**.
- Với JWT, **alg/kid từ token header là input chưa tin cậy**. Verifier phải cố định algorithm allowlist, issuer, audience, trust source và cách chọn key.
- Một server có thể đăng JWK mới trong JWKS nhưng **cache của verifier** còn key cũ; key rotation/withdrawal cần chính sách TTL, trust và token lifetime.

Ví dụ bất nhất cần từ chối hoặc xử lý theo protocol policy:

~~~text
JWK: use = "sig", key_ops = ["unwrapKey"]
Ý nghĩa mâu thuẫn: key intended ký nhưng lại đề nghị unwrap.

JWK: alg = "EdDSA", key type = oct (shared symmetric secret)
Không tương thích với key type mong đợi cho EdDSA.

Request: JWT header đòi "alg":"none" hoặc URL key tùy ý
Không được override verifier policy vì token tự khai như vậy.
~~~

### 5.2. X.509: KeyUsage và ExtendedKeyUsage (EKU)

Một certificate X.509 có thể chứa:

- **KeyUsage**: những loại thao tác hoặc cách sử dụng khóa công khai được chứng thư cho phép, ví dụ digitalSignature, keyEncipherment, keyAgreement, keyCertSign.
- **ExtendedKeyUsage (EKU)**: mục đích ứng dụng cụ thể hơn, ví dụ serverAuth, clientAuth, codeSigning hoặc profile khác.
- **Subject Alternative Name (SAN)**: danh tính (DNS, URI, v.v.) cần được CA xác thực theo enrollment policy.

Với **mTLS client certificate**, thông tin đúng không chỉ là “certificate được một CA ký”. Peer cần kiểm tra **certificate path, thời hạn, SAN/trust domain, KeyUsage/EKU theo profile, trạng thái thu hồi** và authorization đối với dịch vụ/route.

Với **code signing certificate**, keyUsage và EKU phù hợp có thể chỉ ra intent **CodeSigning**, nhưng certificate **không tự chứng minh pipeline đã approve artifact** hoặc private key chưa bị lộ.

**Không đồng nhất X.509 KeyUsage = JWK use = field keyPurpose trong inventory.** Chúng có mục đích bổ trợ, khác phạm vi, khác enforcement. Một certificate không có EKU hoặc có EKU mở rộng cần được kiểm tra theo **validation profile**, không mặc định chấp nhận mọi purpose.

### 5.3. PKCS#11: Các thuộc tính usage trên đối tượng khóa

Trong PKCS#11, khóa/token có thể mang những thuộc tính điều khiển operation và khả năng xuất:

| Thuộc tính khái niệm | Ý nghĩa sử dụng |
|---|---|
| **CKA_ENCRYPT / CKA_DECRYPT** | Khóa cho phép Encrypt/Decrypt khi cơ chế phù hợp |
| **CKA_SIGN / CKA_VERIFY** | Khóa cho phép Sign/Verify |
| **CKA_WRAP / CKA_UNWRAP** | Khóa cho phép Wrap/Unwrap material |
| **CKA_DERIVE** | Khóa cho phép DeriveKey |
| **CKA_SENSITIVE** | Ràng buộc việc lộ một số thành phần nhạy cảm theo token |
| **CKA_EXTRACTABLE** | Thuộc tính liên quan khả năng xuất key material |
| **CKA_LABEL / CKA_ID** | Định danh/nhãn đối tượng, không thay authorization |

**Các attribute cụ thể có semantics và ràng buộc tạo/sửa tùy token/provider.** Một token có thể ngăn operation không phù hợp ngay trong HSM. Nhưng ngay cả khi **CKA_SIGN = true**, vẫn cần kiểm soát **ai đăng nhập token/session và nội dung nào được phép ký**. HSM có thể bị biến thành signing oracle nếu policy chỉ kiểm tra operation mà không kiểm tra business purpose.

Ngược lại, tự thêm **purpose = INVOICE_SIGNATURE** vào CKA_LABEL hoặc registry bên ngoài **không tự tạo ra token-enforced restriction** với nội dung hóa đơn.

### 5.4. KMS: Provider usage khác business purpose

Một KMS thường có khái niệm **key type, key usage, allowed algorithms, state, IAM/key policies, resource tags/labels và grants**. Tên trường và tổ hợp hợp lệ phụ thuộc sản phẩm; chẳng hạn một provider phân biệt khóa **encrypt/decrypt** với **sign/verify**, nhưng không có field native **chỉ ký hóa đơn đã được quản lý duyệt**.

Thiết kế nên dùng nhiều lớp:

~~~text
Application key inventory:
    keyPurpose = BILLING_INVOICE_SIGNATURE
    owner = billing-security-owner
    tenant = tenant-a
    allowedService = billing-signer
    keyRef = provider key ID/version

Provider crypto policy:
    key type = asymmetric signing key
    algorithms = approved signature suite
    allow principal billing-signer -> Sign
    deny raw private key export / policy mutation

Business authorization:
    invoiceId thuộc tenant-a
    invoice status = approved for signing
    canonical message = đúng invoice schema

Audit:
    requestId, principal, invoiceRef, keyRef/version,
    authorization decision, Sign result, timestamp
~~~

**Tags/labels thường hỗ trợ quản trị, thống kê hoặc policy condition theo khả năng provider; chúng không mặc nhiên khóa chặt crypto operation.** Nếu một principal có quyền sửa tag hoặc registry metadata để đổi purpose, cần thiết kế chống **metadata tampering** và tránh policy escalation kiểu “đổi nhãn thành allowed rồi gọi Sign”.

### 5.5. So sánh ba kiểu kiểm soát

| Kiểu | Ví dụ | Có thể bảo đảm gì? | Không tự bảo đảm gì? |
|---|---|---|---|
| **Descriptive metadata** | Inventory keyPurpose, owner, label | Truy vấn, quản lý, review, làm input cho policy | Từ chối phép toán ở HSM khi bypass ứng dụng |
| **Provider-enforced attribute/policy** | HSM CKA_WRAP; KMS key usage và IAM | Từ chối operations không được provider cho phép | Caller có quyền với từng business record |
| **Application/domain authorization** | Billing được Sign invoice đã approved | Ràng buộc request với purpose, tenant và nghiệp vụ | Ngăn direct KMS API nếu provider grant quá rộng |

Kiểm soát mạnh cần **cả ba lớp được nối bằng identity/key reference chính xác**, không để một lớp tự nhận thay thế lớp kia.

## 6. Kiến trúc kiểm tra purpose khi dùng khóa

### 6.1. Luồng chuẩn: request → metadata → provider

~~~mermaid
sequenceDiagram
    participant Caller as Authenticated caller
    participant App as Crypto application
    participant Registry as Trusted Key Registry
    participant Policy as Policy decision
    participant KMS as KMS/HSM
    participant Audit as Audit store
    Caller->>App: action, recordRef, desired key purpose
    App->>App: AuthN + resource/tenant authorization
    App->>Registry: Resolve immutable keyRef/version
    Registry-->>App: purpose, algorithm, state, owner, policyRef
    App->>Policy: Check action + purpose + principal + resource + state
    alt Denied
        Policy-->>App: DENY + reason code
        App->>Audit: Deny event, no raw secret
        App-->>Caller: Controlled denial
    else Allowed
        Policy-->>App: ALLOW under approved constraints
        App->>KMS: Operation with scoped identity/keyRef/context
        KMS-->>App: Crypto result or provider denial
        App->>Audit: KeyRef/version, operation, principal, outcome
        App-->>Caller: Authorized result
    end
~~~

**Lấy metadata từ registry đáng tin theo keyRef đã được kiểm tra**, không lấy toàn bộ fields từ HTTP request rồi tự xem là policy. Với **alias** có thể đổi, cần resolve **immutable provider key reference/version** cho ciphertext/chữ ký lịch sử.

### 6.2. Các điều kiện cần hội đủ

Trước khi gọi crypto API, decision logic tối thiểu nên xét:

1. **Identity**: token/certificate hợp lệ, issuer/audience/subject, principal được phép dùng key?
2. **Resource authorization**: caller có quyền với invoice/record/tenant thuộc request?
3. **Environment/tenant**: key chỉ dùng đúng production/staging và tenant scope?
4. **Key reference**: đúng key ID, version, provider account/partition/region, không do untrusted input đổi?
5. **Purpose**: operation có cùng keyPurpose và businessPurpose?
6. **Algorithm/key type**: thuật toán được allowlist, tương thích material và protocol?
7. **Key state/cryptoperiod**: ACTIVE cho Encrypt/Sign mới; lịch sử có thể Decrypt/Verify theo policy?
8. **Exportability**: operation có làm raw private key/KEK xuất khỏi boundary trái policy?
9. **Quotas/usage policy**: hạn mức, approval, TTL của grant, điều kiện signing hoặc unwrap?
10. **Provider enforcement**: chính provider thực hiện authentication/authorization, không chỉ code client-side?

**Tính đúng của metadata không đủ để bảo vệ chống RCE.** Một attacker chiếm workload có quyền trực tiếp gọi KMS/HSM có thể bỏ qua một policy gate chỉ nằm trong controller. Cần **scoped KMS/HSM policy, separated workload roles hoặc crypto gateway** để khóa đường bypass theo threat model.

### 6.3. Phân quyền người quản trị và người sử dụng

| Vai trò | Trách nhiệm | Không nên mặc định |
|---|---|---|
| **Key owner** | Xác định keyPurpose và businessPurpose, cryptoperiod, data dependencies | Tự xuất raw root/KEK |
| **Security administrator** | Duyệt taxonomy, policy, IAM, exportability, SoD | Có quyền Sign/Decrypt dữ liệu nghiệp vụ |
| **KMS/HSM operator** | Tạo/rotate/backup/restore key theo approval | Dùng mọi key cho mọi purpose |
| **Service owner** | Định nghĩa nhu cầu operation và business resource scope | Tự sửa keyPurpose để được cấp thêm quyền |
| **Workload principal** | Gọi đúng crypto operations đã cấp | ManagePolicy, ExportKey, DestroyKey |
| **Independent auditor** | Đối soát metadata, provider attributes, grants và logs | Tự sửa policy rồi tự duyệt kết quả |

**Không nên cho principal được phép Sign có thể tự đổi metadata purpose hoặc tự CreateGrant** để mở rộng khả năng sử dụng. Với hành động nhạy cảm như đổi keyPurpose, export raw material, thay key policy hoặc destroy, cần **approval độc lập và trail**.

## 7. Purpose metadata trong envelope encryption

Một bản ghi envelope điển hình gồm:

~~~text
Plaintext record
    |
    | AES-GCM Encrypt bằng DEK purpose=CONTENT_ENCRYPTION
    v
Content ciphertext + tag + nonce

Plaintext DEK
    |
    | Wrap bằng KEK purpose=DATA_KEY_WRAPPING
    v
Encrypted DEK (EDK)

Envelope lưu:
  contentCiphertext/tag/nonce
  encryptedDEK/wrap parameters
  content keyRef/version, wrapping keyRef/version
  format, algorithm, tenant, record, AAD context
~~~

**DEK và KEK có purpose khác nhau**. Key purpose metadata giúp hệ thống không nhận một **content DEK** vào API **WrapKey** như một KEK chỉ vì hai key đều có 256-bit entropy.

### 7.1. Content purpose và wrapping purpose là hai namespace

Một envelope có thể khai báo hai references độc lập:

~~~json
{
  "envelopeVersion": 2,
  "tenantId": "tenant-a",
  "recordId": "invoice-001",
  "content": {
    "algorithm": "AES-256-GCM",
    "keyPurpose": "CONTENT_ENCRYPTION",
    "dekRef": "tenant-a-invoice-dek/v7",
    "nonce": "<BASE64_CONTENT_NONCE>",
    "ciphertextWithTag": "<BASE64_CONTENT_CIPHERTEXT>"
  },
  "wrapping": {
    "algorithm": "AES-KW",
    "keyPurpose": "DATA_KEY_WRAPPING",
    "kekRef": "tenant-a-kek/v3",
    "encryptedDek": "<BASE64_EDK>"
  }
}
~~~

Định dạng này chỉ mang tính **minh họa**, không thay provider ciphertext blob hoặc envelope format đã được phê duyệt. **Mọi trường purpose đọc từ storage có thể bị sửa** nếu storage không đáng tin; ứng dụng phải xác minh với **trusted registry + authenticated context** thay vì suy rằng JSON tự mô tả là đúng.

### 7.2. AAD và purpose binding

Với AES-GCM, AAD có thể ràng buộc **tenant, record, content format version, key purpose và DEK identifier**:

~~~text
contentAAD =
    encodeLengthPrefixed(
      "content:aes-gcm:v2",
      tenantId, recordId, contentDekId, contentPurpose
    )
~~~

**AAD không phải secret và không tự chứng minh caller có quyền**. Nếu attacker tự đặt **tenantId = victim** và service có KMS Unwrap grant quá rộng, tag có thể hợp lệ nhưng authorization đã sai. Phải so tenant/record với authenticated principal và storage ownership **trước khi Unwrap**.

**Tách content AAD khỏi wrapping metadata** là quan trọng khi rewrap KEK. Nếu content tag ràng buộc **KEK version** rồi version thay đổi, ciphertext content có thể không verify được nếu không re-encrypt/re-authenticate theo migration plan.

### 7.3. Purpose sau rotation

Khi đổi **KEK-v3 → KEK-v4**:

- Purpose vẫn **DATA_KEY_WRAPPING**; key ID/version thay để chỉ vật liệu mới.
- EDK lịch sử có thể vẫn cần KEK-v3 để Unwrap.
- **Rewrap** giữ nguyên DEK, chỉ đổi cách bảo vệ DEK; content purpose không tự đổi.
- Nếu **DEK-v7 đã bị lộ**, rewrap không khôi phục confidentiality; phải đánh giá **DEK rotation và re-encryption**.

Một thay đổi mục đích từ **CONTENT_ENCRYPTION** sang **DATA_KEY_WRAPPING** không nên được coi là rotation metadata. Đó là **thay đổi thiết kế security boundary**; an toàn hơn là tạo khóa mới đúng purpose và migrate dữ liệu bằng workflow có kiểm soát.

## 8. Purpose metadata trong chữ ký số, JWT và mTLS

### 8.1. Ký hóa đơn khác ký JWT

Hai hệ thống đều có thể dùng Ed25519:

~~~text
billing-signing:
   purpose = BILLING_INVOICE_SIGNATURE
   operation = SIGN invoice canonical bytes
   allowedPrincipal = billing-signer
   provider = HSM non-exportable key

jwt-issuer-signing:
   purpose = JWT_ACCESS_TOKEN_SIGNATURE
   operation = SIGN token theo issuer/audience/claims policy
   allowedPrincipal = token-issuer
   provider = KMS/HSM signing key
~~~

**Không dùng cùng private key cho hai mục đích** nếu không có lý do và đánh giá bảo mật rõ ràng. Nếu một private key bị lộ hoặc Sign permission bị lạm dụng, việc tách key material sẽ giảm khả năng một sự cố ảnh hưởng hai giao thức.

Ngay cả khi hai service được cấp **SIGN**, key purpose metadata không thể xác định một thông điệp có thực sự là **hóa đơn đã được duyệt** hay **JWT có đúng claims**. Việc đó cần **domain authorization, canonical message encoding, issuer/audience validation, approval và audit**.

### 8.2. Token header, JWKS và algorithm confusion

JWT/JWS verifier cần:

- Một tập **issuer và public keys** tin cậy, không tải key từ URL tùy ý của token.
- **Algorithm allowlist** và ràng buộc key type/alg/issuer, không tự chọn mode theo header chưa tin.
- **kid** gắn với trusted JWKS/key registry, không phải một bearer token.
- Kiểm tra **issuer, audience, expiry, token type, signature và business authorization**.
- Policy về **retired/compromised verification keys**, cache JWKS và lịch sử phiên.

**Key purpose metadata = JWT_SIGNATURE** có thể giúp chặn dùng key ký hóa đơn để Verify access token, nhưng không thay thế toàn bộ kiểm tra token.

### 8.3. mTLS và certificate purpose

Một certificate clientAuth có thể phục vụ xác thực service với gateway nhưng **không tự trao quyền KMS Unwrap**. X.509 **EKU, SAN, chain và trust** được kiểm tra ở bước TLS; sau đó key-use policy quyết định service identity này có được dùng **KEK của tenant A** hay không.

Không tự coi **certificate keyUsage digitalSignature** là giấy phép được ký mọi loại nội dung nghiệp vụ. TLS client authentication và invoice signing là **business purposes khác nhau**, nên có keypair, trust và approval tách biệt khi phù hợp.

## 9. Purpose, key state và cryptoperiod: Ba trục độc lập

Giả sử một private signing key được tạo với **purpose = BILLING_INVOICE_SIGNATURE**. Purpose đó không đổi chỉ vì key chuyển trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> PRE_ACTIVE: Create và kiểm tra policy
    PRE_ACTIVE --> ACTIVE: Approve/activate
    ACTIVE --> RETIRED: Hết thời gian Sign mới
    ACTIVE --> SUSPENDED: Sự cố hoặc pause
    SUSPENDED --> ACTIVE: Review/approval nếu an toàn
    SUSPENDED --> COMPROMISED: Có bằng chứng lộ material
    RETIRED --> DESTROYED: Hết retention/dependency
    COMPROMISED --> DESTROYED: Migration/retention review
    DESTROYED --> [*]
~~~

Đây là **state model khái niệm**, không phải mô tả chính xác states của mọi KMS. Trong thực tế:

- **ACTIVE** có thể cho SIGN/ENCRYPT mới nếu cryptoperiod còn hiệu lực.
- **RETIRED** có thể vẫn cho **VERIFY/DECRYPT lịch sử** theo policy và key type; không cho Sign/Encrypt mới.
- **SUSPENDED** có thể cấm mọi operation cho đến khi có review, tùy threat model/provider.
- **COMPROMISED** đòi hỏi incident response; không được tự chuyển thành ACTIVE chỉ bằng đổi metadata.
- **DESTROYED** chỉ nên thực hiện sau khi rà **ciphertext, EDK, archive, backup, escrow và nhu cầu Verify**.

Một **cryptoperiod** không nhất thiết bằng lifetime của key object. Khóa có thể hết thời hạn **tạo chữ ký mới**, nhưng public key còn cần để **xác minh chữ ký lịch sử**. Ngược lại private key non-exportable đã bị compromise không nên tiếp tục Sign chỉ vì còn hạn hợp đồng.

### 9.1. Ma trận operation theo state

| State mô hình | ENCRYPT/SIGN/WRAP mới | DECRYPT/VERIFY/UNWRAP lịch sử | Ghi chú |
|---|---|---|---|
| **PRE_ACTIVE** | Không | Không, trừ test trong môi trường được phê duyệt | Chờ activation/policy review |
| **ACTIVE** | Có nếu đúng purpose/IAM/cryptoperiod | Có nếu được cấp phép | Không có nghĩa mọi caller đều có quyền |
| **RETIRED** | Không | Có thể, theo retention/trust policy | Cần version và algorithm lịch sử |
| **SUSPENDED** | Không | Không hoặc rất hạn chế theo provider | Không tự bypass để giữ availability |
| **COMPROMISED** | Không | Chỉ theo quy trình sự cố/trust policy | Đánh giá thay key, migrate dữ liệu |
| **DESTROYED** | Không | Không bằng material đã hủy | Phải xác định mọi copy/recovery path |

**Sự tồn tại của keyRef** không chứng minh key còn khả dụng. Kiểm tra state nên lấy từ **trusted registry/provider** và quan tâm **effective time/propagation**, không dùng một cache trạng thái vô thời hạn.

### 9.2. Key ID/version khác purpose

Ví dụ:

~~~text
billing-signing / version 4:
    purpose = BILLING_INVOICE_SIGNATURE
    state   = RETIRED (không Sign mới)

billing-signing / version 5:
    purpose = BILLING_INVOICE_SIGNATURE
    state   = ACTIVE
~~~

**Rotation tạo/đưa vào sử dụng material mới** đúng purpose. Không chỉ sửa trường version thành 5 cho metadata của material v4 rồi nói khóa đã rotate. Ngoài ra, một alias như **billing-signing-current** có thể đổi mục tiêu; signatures và ciphertext lịch sử nên ghi **immutable key ID/version** tương ứng.

### 9.3. Xử lý thay purpose thật sự

Đổi từ **JWT_TOKEN_SIGNING** sang **CODE_SIGNING** không chỉ là cập nhật một label. Những công việc cần:

1. **Key owner** xác nhận yêu cầu business purpose mới, tác động tới trust và người nhận.
2. **Security** đánh giá algorithm/key usage, key reuse và cross-protocol attacks.
3. **KMS/HSM operator** tạo key mới trong boundary phù hợp, cấp grants tách biệt.
4. **Ứng dụng** đổi canonical message schema, keyRef, protocol validation, IAM và audit.
5. **Verifier/recipient** nhận public keys/trust anchors/versions mới theo nguồn đáng tin.
6. **Dữ liệu lịch sử** được duy trì hoặc migrate theo policy; key cũ được retire/revoke đúng quy trình.

Không tự cho service ký bất kỳ dữ liệu nào bằng private key hiện tại chỉ vì thư viện JCA cho phép gọi Signature.sign().

## 10. Governance và chất lượng metadata

### 10.1. Ai tạo, phê duyệt, sửa purpose?

| Hành động | Người đề xuất | Người chịu trách nhiệm | Người triển khai | Kiểm chứng |
|---|---|---|---|---|
| Tạo taxonomy purpose | Security architecture | Security governance | Platform registry team | Independent reviewer |
| Khởi tạo key với purpose mới | Service owner | Key owner | KMS/HSM operator | Security + audit |
| Cấp Sign/Unwrap grant | Application owner | Key owner + Security theo rủi ro | IAM/KMS operator | Negative test |
| Chuyển key state | Service/key owner | Key owner | Authorized operator | Lifecycle audit |
| Rotate key | Key owner hoặc incident team | Key owner | Operator/migration worker | Restore/Verify test |
| Thay business purpose | Service owner | Security + Key owner | New-key migration team | Audit và compatibility test |
| Destroy key | Key owner | Approver theo retention/SoD | KMS/HSM custodian | Dependency + backup review |

Với thao tác **thay purpose hoặc allowed operations**, phải ghi nhận **before/after metadata, policy revision, approver, principal, time, impact assessment và kết quả kiểm tra provider**. Một người không nên vừa tự sửa policy cho phép Sign vừa tự ký dữ liệu ngoài quy trình.

### 10.2. Kiểm tra tính nhất quán từ inventory tới provider

Ví dụ một drift:

~~~text
Inventory:
    purpose = DATA_KEY_WRAPPING
    allowedOperations = [WRAP, UNWRAP]

Provider:
    IAM grant cho service-X gồm Decrypt và GenerateMac ngoài scope
    hoặc HSM token có CKA_SIGN=true trên key liên quan

=> Inventory đẹp nhưng provider cho phép đường dùng khác.
~~~

Đối soát theo kỳ hoặc theo thay đổi:

- **Provider key type/algorithm** tương thích purpose và key inventory?
- **Provider grants/roles** có vượt allowed operations/tenants?
- **PKCS#11 attributes** có bật operation ngoài mục đích?
- **JWK/JWKS** có mô tả nhất quán use/key_ops/alg với key type?
- **X.509 certificate profiles** có EKU/SAN đúng mục đích và trust?
- **Key state/rotation** có đồng bộ sang consumers/cache/trust store?
- **Owner/service** có còn hoạt động, không phải orphan key hoặc leaver?

**Trạng thái không khớp phải được đưa thành exception có owner, priority, deadline và mitigation**, không âm thầm cập nhật nhãn inventory để “hợp thức hóa” quyền quá rộng.

### 10.3. Không dùng dữ liệu tùy ý làm source of truth

Một attacker có thể sửa envelope metadata thành **keyPurpose = JWT_SIGNATURE** hoặc đổi JWK **use = sig**. Nếu ứng dụng tin metadata từ storage/token mà không so với trusted registry, attacker có thể tạo **purpose substitution**.

Phân loại dữ liệu:

| Nguồn | Độ tin cậy phù hợp |
|---|---|
| **Trusted key registry** có IAM, change approval và audit | Nguồn tham chiếu chính cho purpose/keyRef theo thiết kế |
| **KMS/HSM key attributes** do provider xác thực | Nguồn thực thi cho key type/usage/state |
| **Certificate/JWK từ issuer đáng tin** | Nguồn public metadata theo trust/policy của giao thức |
| **Envelope/JSON trong database** | Dữ liệu có thể bị thay, cần authenticity/binding và authorization |
| **HTTP body/query/JWT header** | Untrusted input, không phải policy nguồn |
| **Log hoặc file CSV import** | Chỉ chứng cứ/phụ trợ; phải xác minh trước khi cập nhật quyền |

Không dùng **client-provided keyPurpose** để sửa key registry hoặc cấp quyền mới. Khi thật sự cần một request có desired purpose, coi đó là **yêu cầu để policy kiểm tra**, không phải kết luận policy cho phép.

## 11. Java 17: Policy gate thực thi key purpose metadata trước khi dùng khóa

Ví dụ sau tạo **hai key families với vật liệu độc lập**: AES-GCM cho **CONTENT_ENCRYPTION** và Ed25519 cho **BILLING_INVOICE_SIGNATURE**. Metadata nằm trong **registry giả lập do ứng dụng tin cậy**, không nhận từ HTTP body. Mỗi key có **immutable keyRef/version, algorithm, purpose, business purpose, tenant, environment, key state, cryptoperiod và grants theo từng service**.

Một **PolicyGate** kiểm tra:

- Danh tính service đã xác thực (trong demo dùng một cờ giả lập).
- Tenant/environment khớp key metadata.
- Quyền nghiệp vụ với record đã được xác minh.
- Expected purpose và business purpose đúng với metadata nguồn.
- Algorithm tương thích purpose, operation được purpose và grants cho phép.
- Key state **ACTIVE** cho Encrypt/Sign mới; **RETIRED** chỉ có thể Decrypt/Verify theo policy.
- Thời hạn operation mới chưa hết.

Nếu ALLOW, crypto layer mới gọi Java JCA. Với Ed25519, service ký một **thông điệp hóa đơn được encode có version và length-prefix**, không ký chuỗi tùy ý do người dùng đưa. Với AES-GCM, AAD ràng buộc tenant, record và purpose.

**Quan trọng:** Đây là ví dụ học thuật; **không có IdP/KMS/HSM, provider IAM thực, approval workflow hoặc non-exportable key**. Đối với production, kiểm tra metadata ở tầng Java cần được củng cố bằng **KMS/HSM key usage attributes và IAM** để một attacker không bypass bằng gọi provider trực tiếp. Code không tạo bất kỳ file nào ngoài source Java do người học tự lưu nếu thực hành.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class KeyPurposeMetadataDemo {
    enum Purpose {
        CONTENT_ENCRYPTION, DATA_KEY_WRAPPING,
        DIGITAL_SIGNATURE, HMAC_AUTHENTICATION
    }
    enum Operation {
        ENCRYPT, DECRYPT, WRAP, UNWRAP,
        SIGN, VERIFY, GENERATE_MAC, VERIFY_MAC
    }
    enum Algorithm {
        AES_256_GCM, AES_KW, ED25519, HMAC_SHA256
    }
    enum State {
        ACTIVE, RETIRED, SUSPENDED, COMPROMISED
    }

    private static final SecureRandom RNG = new SecureRandom();
    private static final String ENVIRONMENT = "production";

    record KeyRef(String keyId, int version) {
        KeyRef {
            if (keyId == null || keyId.isBlank() || version < 1) {
                throw new IllegalArgumentException("Invalid key reference");
            }
        }
    }

    record Metadata(
            KeyRef ref,
            Purpose purpose,
            String businessPurpose,
            Algorithm algorithm,
            String tenantId,
            String environment,
            State state,
            Instant newUseUntil,
            Map<String, Set<Operation>> grants) {
        Metadata {
            Objects.requireNonNull(ref);
            Objects.requireNonNull(purpose);
            Objects.requireNonNull(algorithm);
            Objects.requireNonNull(state);
            Objects.requireNonNull(newUseUntil);
            if (businessPurpose == null || businessPurpose.isBlank()
                    || tenantId == null || tenantId.isBlank()
                    || environment == null || environment.isBlank()
                    || grants == null) {
                throw new IllegalArgumentException("Invalid metadata");
            }
            // Demo dùng các Set immutable; provider policy còn phải kiểm tra.
            Map<String, Set<Operation>> copy = new HashMap<>();
            grants.forEach((principal, operations) ->
                    copy.put(principal, Set.copyOf(operations)));
            grants = Map.copyOf(copy);
        }

        Metadata withState(State updated) {
            return new Metadata(
                    ref, purpose, businessPurpose, algorithm,
                    tenantId, environment, updated,
                    newUseUntil, grants);
        }
    }

    record Entry(
            Metadata metadata,
            SecretKey symmetricKey,
            KeyPair signingKeyPair) {}

    static final class TrustedRegistry {
        private final Map<KeyRef, Entry> entries = new HashMap<>();

        void add(Entry entry) {
            Objects.requireNonNull(entry);
            if (entries.putIfAbsent(
                    entry.metadata().ref(), entry) != null) {
                throw new IllegalArgumentException("Duplicate keyRef");
            }
        }

        Entry get(KeyRef ref) {
            return entries.get(ref);
        }

        // Chỉ demo: production yêu cầu approval và IAM để đổi state.
        void setState(KeyRef ref, State state) {
            Entry old = entries.get(ref);
            if (old == null) {
                throw new IllegalArgumentException("Unknown key");
            }
            entries.put(ref, new Entry(
                    old.metadata().withState(state),
                    old.symmetricKey(), old.signingKeyPair()));
        }
    }

    record Identity(
            String principal,
            String tenantId,
            String environment,
            boolean authenticated) {}

    record Request(
            Identity identity,
            KeyRef keyRef,
            Purpose expectedPurpose,
            String expectedBusinessPurpose,
            Operation operation,
            boolean resourceAuthorized) {}

    record Decision(boolean allowed, String reason) {}

    static boolean compatible(
            Purpose purpose, Algorithm algorithm, Operation operation) {
        return switch (purpose) {
            case CONTENT_ENCRYPTION ->
                    algorithm == Algorithm.AES_256_GCM
                    && (operation == Operation.ENCRYPT
                        || operation == Operation.DECRYPT);
            case DATA_KEY_WRAPPING ->
                    algorithm == Algorithm.AES_KW
                    && (operation == Operation.WRAP
                        || operation == Operation.UNWRAP);
            case DIGITAL_SIGNATURE ->
                    algorithm == Algorithm.ED25519
                    && (operation == Operation.SIGN
                        || operation == Operation.VERIFY);
            case HMAC_AUTHENTICATION ->
                    algorithm == Algorithm.HMAC_SHA256
                    && (operation == Operation.GENERATE_MAC
                        || operation == Operation.VERIFY_MAC);
        };
    }

    static boolean historical(Operation operation) {
        return operation == Operation.DECRYPT
                || operation == Operation.UNWRAP
                || operation == Operation.VERIFY
                || operation == Operation.VERIFY_MAC;
    }

    static Decision authorize(TrustedRegistry registry, Request req) {
        if (req == null || req.identity() == null
                || req.keyRef() == null || req.expectedPurpose() == null
                || req.operation() == null
                || req.expectedBusinessPurpose() == null) {
            return new Decision(false, "INVALID_REQUEST");
        }
        Identity caller = req.identity();
        if (!caller.authenticated()) {
            return new Decision(false, "IDENTITY_NOT_TRUSTED");
        }
        Entry entry = registry.get(req.keyRef());
        if (entry == null) {
            return new Decision(false, "KEY_NOT_FOUND");
        }
        Metadata meta = entry.metadata();
        if (!meta.tenantId().equals(caller.tenantId())
                || !meta.environment().equals(caller.environment())
                || !req.resourceAuthorized()) {
            return new Decision(false, "RESOURCE_OR_SCOPE_DENIED");
        }
        if (meta.purpose() != req.expectedPurpose()
                || !meta.businessPurpose().equals(
                        req.expectedBusinessPurpose())) {
            return new Decision(false, "PURPOSE_MISMATCH");
        }
        if (!compatible(
                meta.purpose(), meta.algorithm(), req.operation())) {
            return new Decision(false, "ALGORITHM_OR_OP_MISMATCH");
        }
        Set<Operation> serviceOps =
                meta.grants().get(caller.principal());
        if (serviceOps == null || !serviceOps.contains(req.operation())) {
            return new Decision(false, "PRINCIPAL_NOT_GRANTED");
        }
        if (meta.state() == State.SUSPENDED
                || meta.state() == State.COMPROMISED) {
            return new Decision(false, "KEY_STATE_DENIED");
        }
        if (meta.state() == State.RETIRED
                && !historical(req.operation())) {
            return new Decision(false, "RETIRED_HISTORICAL_ONLY");
        }
        if (!historical(req.operation())
                && !Instant.now().isBefore(meta.newUseUntil())) {
            return new Decision(false, "NEW_USE_PERIOD_EXPIRED");
        }
        return new Decision(true, "APPROVED_FOR_KEY_USE");
    }

    static Entry require(
            TrustedRegistry registry, Request req) {
        Decision decision = authorize(registry, req);
        if (!decision.allowed()) {
            throw new SecurityException(decision.reason());
        }
        return registry.get(req.keyRef());
    }

    static void putString(DataOutputStream out, String value)
            throws Exception {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static byte[] contentAad(
            String tenant, String record, KeyRef ref) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(output)) {
            out.writeInt(1);
            putString(out, "CONTENT_ENCRYPTION");
            putString(out, tenant);
            putString(out, record);
            putString(out, ref.keyId());
            out.writeInt(ref.version());
        }
        return output.toByteArray();
    }

    record Envelope(byte[] nonce, byte[] ciphertextWithTag) {
        Envelope {
            nonce = nonce.clone();
            ciphertextWithTag = ciphertextWithTag.clone();
        }
        @Override
        public byte[] nonce() {
            return nonce.clone();
        }
        @Override
        public byte[] ciphertextWithTag() {
            return ciphertextWithTag.clone();
        }
    }

    static Envelope encrypt(
            TrustedRegistry registry, Request req,
            String recordId, byte[] plaintext) throws Exception {
        if (req.operation() != Operation.ENCRYPT) {
            throw new SecurityException("Wrong crypto entrypoint");
        }
        Entry entry = require(registry, req);
        byte[] nonce = new byte[12];
        RNG.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, entry.symmetricKey(),
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(contentAad(
                req.identity().tenantId(), recordId, req.keyRef()));
        return new Envelope(nonce, cipher.doFinal(plaintext));
    }

    static byte[] decrypt(
            TrustedRegistry registry, Request req,
            String recordId, Envelope envelope) throws Exception {
        if (req.operation() != Operation.DECRYPT) {
            throw new SecurityException("Wrong crypto entrypoint");
        }
        Entry entry = require(registry, req);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, entry.symmetricKey(),
                new GCMParameterSpec(128, envelope.nonce()));
        cipher.updateAAD(contentAad(
                req.identity().tenantId(), recordId, req.keyRef()));
        return cipher.doFinal(envelope.ciphertextWithTag());
    }

    static byte[] canonicalInvoice(
            String tenant, String invoiceId, long amountMinor)
            throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(output)) {
            out.writeInt(1);
            putString(out, "BILLING_INVOICE_SIGNATURE");
            putString(out, tenant);
            putString(out, invoiceId);
            out.writeLong(amountMinor);
        }
        return output.toByteArray();
    }

    static byte[] sign(
            TrustedRegistry registry, Request req,
            byte[] canonicalMessage) throws Exception {
        if (req.operation() != Operation.SIGN) {
            throw new SecurityException("Wrong crypto entrypoint");
        }
        Entry entry = require(registry, req);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(entry.signingKeyPair().getPrivate());
        signer.update(canonicalMessage);
        return signer.sign();
    }

    static boolean verify(
            TrustedRegistry registry, Request req,
            byte[] canonicalMessage, byte[] signature)
            throws Exception {
        if (req.operation() != Operation.VERIFY) {
            throw new SecurityException("Wrong crypto entrypoint");
        }
        Entry entry = require(registry, req);
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(entry.signingKeyPair().getPublic());
        verifier.update(canonicalMessage);
        return verifier.verify(signature);
    }

    static Request request(
            Identity who, KeyRef ref, Purpose purpose,
            String businessPurpose, Operation operation) {
        // resourceAuthorized=true CHỈ là dữ liệu giả lập.
        return new Request(
                who, ref, purpose, businessPurpose, operation, true);
    }

    public static void main(String[] args) throws Exception {
        TrustedRegistry registry = new TrustedRegistry();
        Instant newUseUntil = Instant.now().plus(Duration.ofDays(7));

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        KeyRef dataRef = new KeyRef("tenant-a-content-dek", 7);
        registry.add(new Entry(new Metadata(
                dataRef, Purpose.CONTENT_ENCRYPTION,
                "INVOICE_PII", Algorithm.AES_256_GCM,
                "tenant-a", ENVIRONMENT, State.ACTIVE,
                newUseUntil, Map.of(
                        "invoice-writer", Set.of(Operation.ENCRYPT),
                        "invoice-reader", Set.of(Operation.DECRYPT))),
                generator.generateKey(), null));

        KeyPairGenerator pairGenerator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyRef signRef = new KeyRef("billing-signing", 4);
        registry.add(new Entry(new Metadata(
                signRef, Purpose.DIGITAL_SIGNATURE,
                "BILLING_INVOICE_SIGNATURE", Algorithm.ED25519,
                "tenant-a", ENVIRONMENT, State.ACTIVE,
                newUseUntil, Map.of(
                        "billing-signer", Set.of(Operation.SIGN),
                        "billing-verifier", Set.of(Operation.VERIFY))),
                null, pairGenerator.generateKeyPair()));

        Identity writer = new Identity(
                "invoice-writer", "tenant-a", ENVIRONMENT, true);
        Identity reader = new Identity(
                "invoice-reader", "tenant-a", ENVIRONMENT, true);
        Identity signer = new Identity(
                "billing-signer", "tenant-a", ENVIRONMENT, true);
        Identity verifier = new Identity(
                "billing-verifier", "tenant-a", ENVIRONMENT, true);
        Identity otherTenant = new Identity(
                "invoice-writer", "tenant-b", ENVIRONMENT, true);

        byte[] sample = "Synthetic invoice payload"
                .getBytes(StandardCharsets.UTF_8);
        Envelope envelope = encrypt(
                registry, request(writer, dataRef,
                        Purpose.CONTENT_ENCRYPTION,
                        "INVOICE_PII", Operation.ENCRYPT),
                "invoice-001", sample);
        byte[] recovered = decrypt(
                registry, request(reader, dataRef,
                        Purpose.CONTENT_ENCRYPTION,
                        "INVOICE_PII", Operation.DECRYPT),
                "invoice-001", envelope);
        System.out.println("AES-GCM roundtrip: "
                + Arrays.equals(sample, recovered));
        Arrays.fill(recovered, (byte) 0);

        byte[] invoice = canonicalInvoice(
                "tenant-a", "invoice-001", 100_000L);
        byte[] signature = sign(
                registry, request(signer, signRef,
                        Purpose.DIGITAL_SIGNATURE,
                        "BILLING_INVOICE_SIGNATURE", Operation.SIGN),
                invoice);
        System.out.println("Invoice signature verifies: "
                + verify(registry, request(verifier, signRef,
                        Purpose.DIGITAL_SIGNATURE,
                        "BILLING_INVOICE_SIGNATURE", Operation.VERIFY),
                        invoice, signature));

        Decision wrongPurpose = authorize(registry, request(
                signer, dataRef, Purpose.DIGITAL_SIGNATURE,
                "BILLING_INVOICE_SIGNATURE", Operation.SIGN));
        System.out.println("Sign using DEK denied: "
                + !wrongPurpose.allowed());

        Decision crossTenant = authorize(registry, request(
                otherTenant, dataRef, Purpose.CONTENT_ENCRYPTION,
                "INVOICE_PII", Operation.ENCRYPT));
        System.out.println("Cross-tenant denied: "
                + !crossTenant.allowed());

        registry.setState(signRef, State.RETIRED);
        Decision retiredSign = authorize(registry, request(
                signer, signRef, Purpose.DIGITAL_SIGNATURE,
                "BILLING_INVOICE_SIGNATURE", Operation.SIGN));
        System.out.println("Retired cannot Sign: "
                + !retiredSign.allowed());
        System.out.println("Retired can Verify under demo policy: "
                + verify(registry, request(verifier, signRef,
                        Purpose.DIGITAL_SIGNATURE,
                        "BILLING_INVOICE_SIGNATURE", Operation.VERIFY),
                        invoice, signature));

        Arrays.fill(sample, (byte) 0);
        Arrays.fill(invoice, (byte) 0);
        // SecretKey/Cipher/KeyPair có thể giữ material trong JVM.
        // Đây KHÔNG phải bảo đảm zeroization toàn bộ bản sao.
    }
}
~~~

Lưu phần mã trên thành **KeyPurposeMetadataDemo.java** và chạy bằng **JDK 17+**:

~~~bash
javac KeyPurposeMetadataDemo.java
java KeyPurposeMetadataDemo
~~~

Các kết quả logic mong đợi:

~~~text
AES-GCM roundtrip: true
Invoice signature verifies: true
Sign using DEK denied: true
Cross-tenant denied: true
Retired cannot Sign: true
Retired can Verify under demo policy: true
~~~

### 11.1. Những gì ví dụ thật sự chứng minh

Ví dụ tách hai key materials độc lập với metadata khác nhau:

| Thử nghiệm | Key purpose / operation | Kết quả |
|---|---|---|
| Writer dùng AES-GCM cho invoice | CONTENT_ENCRYPTION + ENCRYPT | Được phép khi đúng principal |
| Reader giải mã cùng key version | CONTENT_ENCRYPTION + DECRYPT | Được phép và GCM tag được kiểm tra |
| Billing ký invoice | DIGITAL_SIGNATURE + SIGN | Được phép và Ed25519 ký thông điệp canonical |
| Truyền DEK vào đường SIGN | Purpose/algorithm/operation không phù hợp | Bị policy gate chặn |
| Tenant B dùng DEK của tenant A | Tenant mismatch | Bị từ chối trước crypto |
| Signing key chuyển RETIRED | SIGN mới | Từ chối |
| Verifier dùng public key của version retired | VERIFY lịch sử | Được phép trong chính sách mô phỏng |

**Với production, việc Verify bằng public key thường không cần truy cập private key.** Demo lưu KeyPair trong cùng registry cho gọn; hệ thống thật nên có **public-key distribution/trust store riêng**, private signing key non-exportable và policy kiểm tra chữ ký theo issuer/record/time.

### 11.2. Giới hạn bắt buộc khi suy từ demo sang production

1. **Identity được mô phỏng bằng boolean authenticated**; nó không thay kiểm tra token/certificate, issuer, audience, signature, expiry hay device/workload attestation.
2. **Business authorization dùng boolean resourceAuthorized**; nếu một API nhận cờ này từ request body thì có thể bypass. Phải lấy quyết định từ hệ thống phân quyền tin cậy.
3. **Metadata registry nằm trong memory và có thể bị sửa bởi code trong process**; production cần IAM, tamper-resistant audit, approval và provider enforcement.
4. **Khóa được sinh, giữ trong JVM**, không non-exportable; key object/JCA provider có thể tạo bản sao và không thể zeroize tuyệt đối chỉ nhờ Array.fill.
5. **Không có KMS/HSM IAM, CKA attributes hoặc secure key usage policy**; ALLOW trong Java không chứng minh provider cho phép hoặc cấm operation tương ứng.
6. **State RETIRED là mô hình riêng**; provider thật có thể suspend mọi phép toán hoặc có trạng thái khác. Verification trust cho chữ ký cũ cần profile riêng.
7. **Không có TTL cho Decrypt/Verify lịch sử**; production cần retention, key revocation và validity/trust policy theo nghiệp vụ.
8. **Random 96-bit nonce AES-GCM có xác suất trùng khác 0**; ví dụ chỉ Encrypt một lần. Với nhiều replica, cần nonce strategy và invocation limits theo cùng DEK.
9. **Không có envelope wrapping/KEK**, backup/restore hoặc persistence. Khi process mất SecretKey, ciphertext demo không còn đường giải mã.
10. **Không có rate limit, quotas, anti-replay, request signing, data classification, audit bền vững hay incident response**.
11. **Không có domain separation toàn diện cho mọi giao thức**; ký hóa đơn cần schema canonical được phê duyệt, chống replay và kiểm tra trạng thái duyệt.
12. **Không ngăn direct API bypass** nếu một workload có quyền provider đủ rộng. Phải cấu hình provider policies và tách quyền tạo grants khỏi quyền Sign/Decrypt.
13. **Không tự động kiểm tra KeyUsage/EKU/JWK key_ops**; các protocol adapters cần kiểm tra metadata nguồn theo chuẩn tương ứng.
14. **Không xử lý state propagation/revision cache**; multi-region KMS/grant changes có thể chưa hiệu lực tức thì.

**Điểm học được:** Mục đích sử dụng khóa không nên được suy từ thuật toán hoặc tên file. Một **trusted metadata + policy gate** giúp ứng dụng từ chối sớm thao tác sai, nhưng **mức bảo đảm cuối cùng phụ thuộc việc provider và giao thức cũng thực thi cùng các ranh giới đó**.

## 12. Threat model: Khi purpose metadata bị bỏ qua hoặc bị thao túng

| Sai lầm / kiểu tấn công | Hậu quả có thể xảy ra | Biện pháp chính |
|---|---|---|
| **Chỉ lưu algorithm, không có purpose** | AES key bị dùng đồng thời làm DEK, KEK hoặc secret khác | Khởi tạo purpose và key usage policy bất biến theo version |
| **Một private key dùng JWT và invoice signing** | Compromise một giao thức ảnh hưởng giao thức khác; Sign oracle xuyên domain | Keypair tách biệt, canonical message, protocol-bound authorization |
| **Key có purpose ký nhưng HSM cấp Decrypt/Unwrap** | Provider grants vượt key inventory, cross-purpose use | Mapping purpose → key type/attributes, provider policy audit |
| **Bật CKA_SIGN trên key chỉ dùng Wrap** | Token có thể thực thi ngoài mục tiêu | HSM attribute validation và config reconciliation |
| **Đổi label purpose để xin quyền mới** | Metadata-based privilege escalation | Trusted registry, write IAM/SoD, independent approval |
| **Tin keyPurpose từ envelope JSON** | Attacker đổi purpose/tráo keyRef | So registry, authenticated metadata, key ID/version validation |
| **Chỉ kiểm tra JWK use mà tin header token** | Algorithm/key substitution, signature acceptance sai | Trusted issuer/JWKS, key type/alg allowlist, JWT validation |
| **Public key lấy từ URL do client chỉ định** | Encrypt DEK tới attacker hoặc Verify chữ ký giả | Authenticated recipient/issuer key distribution |
| **Nhầm X.509 clientAuth và quyền Sign nghiệp vụ** | mTLS identity có thể ký hóa đơn ngoài thẩm quyền | EKU/SAN check + separate business purpose authorization |
| **Cùng HMAC key cho nhiều partner** | Một partner lộ key ảnh hưởng toàn bộ partners | Key per partner/protocol, rotation, TTL và anti-replay |
| **Dẫn xuất khóa không domain separation** | Derived key reuse giữa tenant/purpose | KDF context/encoding độc lập, root governance |
| **Cryptoperiod hết nhưng key vẫn Encrypt mới** | Tăng exposure, trái policy và key usage limits | ACTIVE/new-use deadline check, provider state enforcement |
| **Retired key bị block mọi Verify lịch sử** | Chữ ký hoặc dữ liệu archive không còn sử dụng được | Tách new-use cryptoperiod và historical-use retention |
| **Compromised key được “sửa purpose” rồi kích hoạt lại** | Không phục hồi tính bí mật, tin key đã lộ | Incident response, new material, trust/key migration |
| **Alias current được dùng mở ciphertext lịch sử** | Rotation khiến key trỏ sai version | Immutable keyRef/version trong ciphertext/envelope |
| **KMS Decrypt grant quá rộng** | Workload thành decryption oracle cho nhiều tenant | Least privilege, tenant/resource authorization, purpose checks |
| **App kiểm tra policy nhưng direct KMS call không bị hạn chế** | Bypass policy gate khi RCE | Provider policy, separate identities hoặc trusted crypto gateway |
| **Không ghi provenance của metadata** | Không chứng minh ai thay purpose, version, grant | Approved changes, revision, immutable audit |
| **Xóa KEK sau khi chỉ sửa state/label** | Mất khả năng mở EDK cũ | Dependency inventory, restore test, retention review |
| **Log key material kèm purpose để dễ debug** | Tạo bản sao DEK/KEK/private key trong log | Audit metadata-only, secret redaction và dump controls |

### 12.1. Ví dụ key-substitution khi metadata chưa được xác thực

~~~text
Storage record:
    keyRef = tenant-A-dek-v7
    declaredPurpose = CONTENT_ENCRYPTION

Attacker sửa record:
    keyRef = tenant-B-kek-v2
    declaredPurpose = CONTENT_ENCRYPTION

Service sai:
    Tin declaredPurpose từ JSON
    Dùng một IAM role có quyền Decrypt/Unwrap mọi key
    Gọi API trước khi kiểm tra tenant/key owner

Service đúng:
    Xác thực principal/resource tenant trước
    Resolve keyRef từ trusted registry đúng namespace/version
    So keyType, purpose, state, algorithm và allowed operations
    Provider IAM từ chối key ngoài scope
    AEAD/AAD phát hiện context không hợp lệ sau đó
~~~

**GCM tag là kiểm tra tính toàn vẹn của ciphertext đối với key/AAD đã dùng**, không bảo đảm rằng user được quyền đọc một record. Nếu ứng dụng đã Unwrap trái phép bằng một role quá rộng, kiểm tra tag sau đó không sửa được lỗi authorization trước đó.

### 12.2. Cross-protocol signing oracle

Giả sử token issuer và invoice signer chia sẻ private Ed25519 key. Một API ký invoice nhận **bytes tùy ý** từ client thay vì canonical invoice record từ database, thì attacker có thể thử đưa bytes có cấu trúc JWT/JWS vào API đó và lấy chữ ký hợp lệ đối với key issuer (phụ thuộc protocol encoding và điều kiện tấn công).

Không phải mọi giao thức đều có cùng cách encode bytes; **domain separation bằng keypair riêng, structured message prefix, purpose authorization và kiểm soát dữ liệu ký** giảm rủi ro. Chỉ thêm nhãn purpose vào metadata nhưng vẫn cho signer ký bất kỳ byte array nào **không đủ**.

### 12.3. Lỗ hổng do đồng bộ metadata chậm

Trong multi-region:

~~~text
revision 20: key v7 ACTIVE / allowed ENCRYPT
revision 21: key v7 RETIRED / chỉ cho DECRYPT

Region B nhận revision 21.
Region A còn cache revision 20 và tiếp tục Encrypt mới.
Event revision 20 đến muộn sau revision 21 tại một consumer.
~~~

Cần **revision monotonic, effective time, bounded cache TTL, notification/reconciliation** và policy quyết định liệu có chấp nhận cửa sổ stale hay không. Nếu rủi ro không cho phép stale, **quyền provider** cũng phải dừng operation chứ không chỉ đổi metadata trên dashboard.

## 13. Rotation, revocation, retention và hủy khóa theo purpose

### 13.1. Vòng đời cho DEK content encryption

1. **Generate:** DEK từ CSPRNG/KMS, ghi purpose CONTENT_ENCRYPTION, algorithm AES-GCM và tenant/record scope.
2. **Provision:** cấp đúng workload Encrypt/Decrypt theo principal, dữ liệu và thời điểm.
3. **Use:** nonce unique với cùng DEK, AAD ràng buộc record/tenant, không log raw key.
4. **Rotate:** chuyển Encrypt mới sang DEK version mới; với dữ liệu cũ cần **re-encrypt** nếu muốn đổi material bảo vệ payload.
5. **Retire:** có thể giữ DEK cũ cho Decrypt archive khi policy yêu cầu.
6. **Compromise:** đánh giá dữ liệu đã bị ảnh hưởng; chỉ thay KEK/rewrap không khôi phục bí mật của DEK đã lộ.
7. **Destroy:** chỉ sau khi mọi ciphertext/backup/replica còn phụ thuộc đã được xử lý và retention cho phép.

**Không kết luận “đã crypto-erase dữ liệu” chỉ vì xóa một field trong key inventory**. Phải xét material, copies, backup, wrapped DEK và những đường khôi phục.

### 13.2. Vòng đời cho KEK purpose DATA_KEY_WRAPPING

~~~text
KEK-v3 ACTIVE:
    Wrap DEK mới và Unwrap EDK cũ khi được phép

KEK-v4 ACTIVE, KEK-v3 RETIRED:
    Wrap DEK mới bằng v4
    Unwrap EDK cũ dưới v3 theo retention
    Rewrap EDK v3 -> v4 theo migration nếu cần

KEK-v3 DESTROY:
    Chỉ sau khi rà EDK/backup/archive còn phụ thuộc và restore test
~~~

**Rewrap** đổi lớp bảo vệ của **cùng DEK**, không phải **DEK rotation**. Khi metadata purpose của KEK thay đổi một cách đột ngột (ví dụ bị gán CONTENT_ENCRYPTION) phải coi đó là **mâu thuẫn governance**, không làm một migration tự động thiếu kiểm tra.

### 13.3. Vòng đời cho signing key

- Khi tạo mới, chỉ provision quyền **SIGN** cho principal được phê duyệt; public key có thể được phân phối rộng hơn nhưng vẫn cần trusted source.
- Khi hết cryptoperiod Sign mới, chuyển signing sang version mới; các chữ ký cũ có thể cần **VERIFY** theo retention/trust profile.
- Nếu raw private key đã bị lộ, có thể tạo chữ ký offline; chỉ thu hồi KMS Sign không khắc phục bản copy đó.
- Cần cập nhật **JWT JWKS/kid hoặc certificate/trust store**, xử lý chữ ký/tokens liên quan theo issuer và thời điểm.
- **Verify toán học thành công** không tự đồng nghĩa chữ ký còn được tổ chức tin cậy sau compromise/revocation.

### 13.4. Vòng đời cho HMAC

- Gắn HMAC key với partner/service, protocol namespace và key version.
- **GENERATE_MAC** và **VERIFY_MAC** có thể có thời điểm dừng khác nhau để hỗ trợ cửa sổ chuyển version.
- Bên nhận cần chống replay bằng timestamp, nonce/message ID hoặc session controls theo giao thức.
- Khi secret lộ, mọi bên biết secret có thể tạo MAC; đánh giá thay secret và dừng chấp nhận version cũ.
- Không đổi HMAC key purpose sang digital signature vì HMAC không trở thành non-repudiation.

### 13.5. Offboarding và chuyển quyền sử dụng

Nếu service owner hoặc Security administrator rời tổ chức, **purpose của key không tự đổi**, nhưng owner, grants, approvers và credential có thể cần thay. Phải:

- Chuyển owner và HSM custodian/quorum theo policy.
- Revoke IAM grants, human sessions/tokens, PAT/SSH/certificates của người rời.
- Đánh giá shared secrets mà người đó đã biết để rotate; kiểm tra raw key exposure riêng.
- Giữ machine identity hợp pháp sau khi chuyển quyền vận hành, không disable bừa production bot.
- Đối soát key purpose metadata với provider access sau thay đổi.

### 13.6. Khi nào thay purpose là hành động nguy hiểm?

Một metadata migration có thể thêm trường **businessPurpose** cho một khóa cũ khi tài liệu lịch sử đủ tin cậy; nhưng nếu thực tế khóa đã được dùng cho nhiều operation, không thể chỉ sửa metadata để biến quá khứ thành key separation an toàn.

Với **legacy multi-purpose key**, nên:

1. Inventory thực tế những nơi dùng key, thuật toán, tenant và hệ thống phụ thuộc.
2. Tạo **keys riêng** đúng từng purpose, ưu tiên non-exportable ở provider phù hợp.
3. Chuyển consumers sang key mới và cập nhật metadata key ID/version.
4. Với dữ liệu cần đọc cũ, lập kế hoạch **Decrypt/Verify migration** có kiểm soát.
5. Giới hạn key cũ về historical operations và cuối cùng retire/destroy khi hợp lệ.

**Không tái sử dụng chính raw bytes của legacy key cho nhiều key IDs mới** rồi cho rằng chúng đã được tách. Identity và label mới không tạo vật liệu bí mật độc lập.

## 14. Audit, metric và đối soát metadata với key usage thực

### 14.1. Audit nên trả lời những câu hỏi nào?

Với mỗi request hoặc thay đổi policy, tổ chức cần có thể xác định:

1. **Ai** (human/workload principal và nguồn identity) đã đề xuất và thực hiện?
2. **Khóa nào** (provider, key ID/version, tenant/environment, key family)?
3. **Purpose nào** được công bố trong trusted inventory, business request thuộc purpose nào?
4. **Operation nào** đã được yêu cầu và KMS/HSM có thực sự thực hiện hay từ chối?
5. **State/cryptoperiod nào** áp dụng tại thời điểm đó?
6. **Quyết định authorization** đến từ policy version nào, có event ID/correlation ID và audit reason code nào?
7. Có **approval** khi sửa purpose, principal grant, exportability hoặc state không?
8. Có **bản sao key material hoặc dữ liệu phụ thuộc** cần rotate/re-encrypt/re-verify không?

### 14.2. Log vừa đủ, không ghi key bytes

| Nên ghi | Vì sao cần | Không nên ghi |
|---|---|---|
| key ID/version, keyPurpose, businessPurpose | Truy vết đúng key family và mục đích | Raw DEK/KEK, HMAC secret, private key PEM |
| principal, tenant, environment, operation | Tìm cross-tenant/cross-purpose usage | Access token/password hoặc secrets trong header |
| resourceRef đã giảm PII, request ID | Gắn vào business authorization | Plaintext khách hàng, toàn bộ invoice không cần thiết |
| decision ALLOW/DENY, reason code | Điều tra policy mismatch | Dữ liệu debug chứa key material |
| provider result, effectiveAt, policy revision | Phân biệt API accepted và enforcement effective | Toàn bộ KMS Decrypt/GenerateDataKey response |
| approval/change ticket, actor | Chứng minh SoD và quy trình thay đổi | PIN/HSM share/recovery secret |
| rotation/migration outcome, dependencies | Theo dõi key lifecycle | Bản sao ciphertext/EDK vượt phạm vi audit |

Key ID và purpose thường **không phải raw secret**, nhưng có thể tiết lộ **tenant names, service topology và ứng dụng nhạy cảm**. Log/audit store phải có quyền truy cập, retention và tính toàn vẹn phù hợp. Không cho người có thể sửa key policy tự xóa audit không để lại dấu vết.

### 14.3. Phát hiện purpose drift

Các metric quan trọng:

- **Số key không có purpose hoặc owner**, nhất là production keys.
- **Số key có purpose = OTHER/ANY**, hoặc được nhiều service dùng khác business domains.
- **Số key mà allowed operations trong inventory khác provider-enforced operations**.
- **Số key có keyType/algorithm mâu thuẫn purpose**, ví dụ Ed25519 được khai để ENCRYPT payload.
- **Số Sign/Decrypt/Unwrap operations trên key versions retired hoặc ngoài cryptoperiod**.
- **Số grants còn cho phép ChangePolicy/Export/Destroy ngoài người có quyền**.
- **Số HMAC secrets dùng chung nhiều đối tác/tenants** và thời gian xoay vòng.
- **Số envelopes chưa có immutable keyRef/version hoặc AAD schema**.
- **Số signing keys có thể export raw bytes ngoài policy**.
- **Số exceptions tồn đọng**: owner, thời hạn, compensating controls và bằng chứng đóng.

Một key **không được dùng gần đây** không nhất thiết có thể destroy, vì có thể phục vụ archive hoặc chữ ký dài hạn. Audit coverage/retention cũng có giới hạn; thiếu event không phải bằng chứng key chưa từng được dùng.

## 15. Kiểm thử chính sách purpose trước production

### 15.1. Bảng test có cả ALLOW và DENY

| Test case | Kỳ vọng | Tầng xác minh |
|---|---|---|
| Billing Sign invoice approved bằng đúng signing key | **ALLOW** | Business policy + KMS/HSM Sign |
| Billing thử Sign JWT bằng invoice signing key | **DENY** | Purpose/business domain |
| Token issuer thử ký invoice bằng JWT signing key | **DENY** | Grants + purpose separation |
| Customer writer dùng DEK để Encrypt đúng record | **ALLOW** | Resource auth + AES-GCM |
| Customer writer dùng DEK làm KEK Wrap | **DENY** | Key purpose/operation mismatch |
| Customer reader dùng KEK của tenant khác | **DENY** | Tenant + IAM/KMS boundary |
| Service gửi purpose=SIGN trong JSON cho AES DEK | **DENY** | Trusted registry không tin caller input |
| Ed25519 key bị khai algorithm AES-GCM | **DENY** | Algorithm/type compatibility |
| KEK RETIRED được dùng Wrap mới | **DENY** | Lifecycle/cryptoperiod |
| KEK RETIRED dùng Unwrap archive hợp lệ | **ALLOW theo policy** | Historical key use |
| Signing key RETIRED dùng Sign mới | **DENY** | Lifecycle/cryptoperiod |
| Public key retired Verify chữ ký cũ còn trusted | **ALLOW theo trust policy** | Signature trust/verification |
| Key SUSPENDED gọi mọi crypto operation | **DENY theo provider policy** | Effective key state |
| Provider grant cho phép SIGN trái inventory purpose | **Phát hiện drift/vi phạm** | Direct provider negative tests |
| JWK có use/key_ops mâu thuẫn | **DENY** | JOSE adapter/policy |
| TLS client cert có SAN sai service | **DENY** | PKI trust/identity |
| API token có issuer hợp lệ nhưng audience sai | **DENY** | Workload identity validation |
| Ciphertext/AAD bị sửa | **AEAD failure** | Data integrity |
| Envelope cũ được replay thay version mới | **Phát hiện nếu anti-rollback yêu cầu** | Record revision/business policy |
| KMS outage và cache state quá hạn | **Fail closed/approved DR**, không bypass | Resilience + security |

**Một positive test hợp lệ không chứng minh hệ thống có least privilege.** Cần thử **negative operations** ở cả application endpoint và provider API trực tiếp trong môi trường thử được cấp phép. Không mang key material sản xuất vào unit-test logs.

### 15.2. Kiểm thử JWK/X.509/PKCS#11

- **JWK/JWS:** thử không chấp nhận algorithm ngoài allowlist, kid không thuộc issuer, key_ops trái use, key type/curve không phù hợp.
- **Certificate:** thử chain và SAN sai, KeyUsage/EKU trái profile, certificate hết hạn hoặc bị revoke theo chính sách validator.
- **HSM token:** kiểm tra CKA_SIGN/CKA_WRAP/CKA_EXTRACTABLE và cơ chế crypto operation thực tế; không chỉ xem nhãn CKA_LABEL.
- **KMS:** đối soát grant/key usage/algorithms và thử operation bị cấm theo provider contract. Nhiều provider không có một field business purpose native; bắt buộc có application-level auth.

### 15.3. Kiểm thử thay đổi metadata

Trường hợp quan trọng là **metadata tampering**:

~~~text
Trước:
  key = tenant-a-kek-v3
  trustedPurpose = DATA_KEY_WRAPPING
  allowedOps = WRAP/UNWRAP

Thử:
  request body khai purpose = DIGITAL_SIGNATURE
  hoặc database envelope khai purpose = DIGITAL_SIGNATURE

Kỳ vọng:
  Trusted registry vẫn cho purpose = DATA_KEY_WRAPPING.
  API SIGN bị từ chối; không tạo grant mới.
  Nếu cần đổi purpose thật, tạo new-key migration.
~~~

Kiểm tra cả **rollback** của policy revision. Nếu một consumer nhận update cũ làm allowed operations mở rộng sau khi đã revoke, reconciliation phải phát hiện và ngăn chặn.

### 15.4. Kiểm thử khi rotate và phục hồi

- Khi **KEK rotation**, encrypted DEK cũ có thể được Unwrap bằng key version lịch sử theo chính sách; rewrap không thay content purpose.
- Khi **DEK rotation**, record phải được re-encrypt nếu muốn đổi key bảo vệ payload; version/AAD/nonce phải đúng.
- Khi **signing key rotation**, public key mới phân phối qua trust hợp lệ; chữ ký lịch sử xử lý theo retention/revocation.
- Khi **HMAC rotation**, receiver chấp nhận phiên bản cũ/mới chỉ trong grace period được duyệt, từ chối sau khi kết thúc.
- Khi **KDF root rotation**, các derived keys có thể bị ảnh hưởng; phải đánh giá dữ liệu/consumers đang dựa vào output cũ.
- Khi **backup restore**, đảm bảo đúng provider key ID/version, purpose, allowed operations và encryption context; không bỏ policy checks chỉ để khôi phục nhanh.

Không giả định **KMS DisableKey** xóa raw DEK cached trong JVM hoặc kết thúc mọi JWT đã phát. Cần hiểu hiệu lực provider, session TTL, data plane và những bản sao vật liệu ngoài KMS.

## 16. Incident response: Purpose mismatch có phải key compromise?

**Không phải mọi purpose mismatch đều chứng minh key bytes đã lộ.** Một metadata drift có thể do lỗi migration, key alias đổi, cấu hình IAM sai, thao tác admin hoặc cố ý khai thác. Tuy nhiên cũng không nên xem purpose mismatch chỉ là lỗi hiển thị nếu nó **cho phép crypto operation trái policy**.

### 16.1. Runbook xử lý

1. **Ghi nhận sự kiện**: keyRef/version, trusted purpose, actual operation, caller, tenant, policy/provider revision, thời điểm.
2. **Xác minh nguồn**: inventory có đúng không, provider attributes/grants đã đổi thế nào, có stale cache/event không?
3. **Xác định data-plane exposure**: đã có Sign/Decrypt/Unwrap/GenerateMac thực sự thành công ngoài scope hay chỉ yêu cầu bị từ chối?
4. **Cô lập phù hợp**: thu hồi grants hoặc tạm hạn chế key use theo risk; cân nhắc availability và phụ thuộc ciphertext/verify.
5. **Đánh giá material exposure**: raw key có được export không, plaintext DEK/HMAC secret có thể đã được trả về process không, signatures nào có thể bị giả?
6. **Đổi policy và material đúng mức**: nếu chỉ là grant sai thì revoke và sửa SoD; nếu raw key lộ phải đánh giá rotate/re-encrypt/revoke trust.
7. **Khôi phục**: update metadata/registry từ nguồn tin cậy, kiểm tra provider state và đúng key versions; thử positive/negative operations.
8. **Hậu kiểm**: audit và tập trung vào root cause — metadata governance, default permissions, review, CI/CD, identity, session.

### 16.2. Ba trường hợp cần phân biệt

| Tình huống | Kết luận ban đầu | Hướng xử lý |
|---|---|---|
| Inventory nói KEK chỉ Wrap, KMS role vô tình có Decrypt; chưa có dấu hiệu gọi API | **Permission drift**, chưa chứng minh key/DEK lộ | Revoke grant, negative test, audit history |
| Workload đã dùng Unwrap ngoài tenant, nhận plaintext DEK | **Data-key exposure khả dĩ**, dù KEK non-exportable | Cô lập workload, xác định EDK/record, xem xét DEK rotation/re-encrypt |
| Raw private signing key bị tải về artifact và được dùng offline | **Private-key compromise khả dĩ** | Rotate signing key, revoke trust/certificate/JWKS theo scope, điều tra chữ ký/token |

**Rewrap DEK bằng KEK khác không sửa được việc DEK đã lộ.** **Thay nhãn purpose cũng không sửa được raw private key đã bị sao chép**. Các thao tác phải phù hợp với loại material và phạm vi ảnh hưởng.

### 16.3. Khi key chỉ nằm trong HSM nhưng API Sign bị lạm dụng

Một private key non-exportable có thể **chưa lộ raw bytes**, nhưng attacker dùng một service có quyền Sign rộng để phát hành chữ ký sai. Runbook không chỉ là rotate:

- Thu hồi hoặc hạn chế **Sign grants/sessions** của principal bị ảnh hưởng.
- Khoanh vùng **message hashes, request IDs, business records và signed artifacts**.
- Đánh giá khả năng phân biệt chữ ký hợp lệ/trái phép theo audit và data provenance.
- Chuyển signing sang key version mới nếu risk/trust policy yêu cầu, cập nhật verifiers.
- Đưa **business authorization** tới trước HSM Sign; tránh Sign tùy ý byte array từ client.

Điểm chính: **purpose metadata** phải là một phần của quyết định **trước phép toán**, không chỉ một nhãn để xem sau sự cố.

## 17. Case study: Key purpose metadata cho nền tảng thanh toán nhiều tenant

### 17.1. Bối cảnh

Nền tảng gồm:

~~~text
Billing Service            -> Sign hóa đơn điện tử
Customer Data Writer       -> AES-GCM Encrypt dữ liệu khách hàng
Customer Data Reader       -> AES-GCM Decrypt theo quyền record
Envelope Key Gateway       -> Wrap/Unwrap DEK dưới tenant KEK
Webhook Gateway            -> HMAC thông điệp gửi từng partner
Token Issuer               -> Sign JWT access token
KMS/HSM                    -> Quản lý key materials và grants
Key Registry / Audit       -> Purpose, owner, lifecycle, metadata, events
~~~

Một lập trình viên nhận thấy API KMS trả về **key ID, algorithm, state** nên xây dựng key registry chỉ có ba trường đó. Các khóa AES không có ranh giới **DEK/KEK**, còn keypair Ed25519 được dùng cho cả **invoice** và **JWT**. Khi rotate alias, một số khách hàng không giải mã được archive, và đội an ninh không xác định rõ một service đã dùng khóa cho purpose nào.

### 17.2. Thiết kế chưa tốt

~~~yaml
keys:
  - name: current-aes-key
    algorithm: AES-256
    state: active
  - name: current-signing-key
    algorithm: Ed25519
    state: active
~~~

Cấu hình này thiếu:

- **Material key ID/version** bất biến; alias current có thể đổi trỏ sang key khác.
- **Purpose, operation, tenant, environment và business domain**.
- **Owner, allowed principals, provider account/partition, exportability**.
- **Content vs wrapping AAD và envelope key dependencies**.
- **Lifecycle/cryptoperiod**: thời gian cho Encrypt/Sign mới so với Decrypt/Verify lịch sử.
- **Approval, audit, migration/backup**.

Vì metadata không mô tả mục đích, người vận hành khó phát hiện rằng cùng AES key dùng để Wrap DEK và Encrypt payload; việc một service có quyền Sign chưa nói được nó được phép ký hóa đơn hay token.

### 17.3. Thiết kế cải tiến

**Bước 1 — Xây taxonomy có kiểm soát.** Định nghĩa CONTENT_ENCRYPTION, DATA_KEY_WRAPPING, BILLING_INVOICE_SIGNATURE, JWT_ACCESS_TOKEN_SIGNATURE, PARTNER_WEBHOOK_MAC, KDF_DERIVATION, TLS_CLIENT_AUTH. Tách cryptographic purpose và business purpose; định nghĩa các operation/algorithm tương thích.

**Bước 2 — Tạo key material riêng.** Customer DEK, tenant KEK, Billing Ed25519 keypair, JWT Ed25519 keypair và HMAC secret cho từng partner có key IDs/versions độc lập. Không copy cùng material rồi gắn nhiều labels.

**Bước 3 — Gắn owner và provider reference.** Key inventory chứa key ID/version và scope tới đúng KMS/HSM resource, không chỉ alias; owner chịu trách nhiệm rotation và retention.

**Bước 4 — Cấu hình enforcement.** IAM/KMS/HSM chỉ cấp operations đúng key purpose: Billing Sign trên billing-sign, Token Issuer Sign trên jwt-sign, Envelope Gateway Wrap/Unwrap tenant KEK; không service nào có quyền mặc định ExportRawKey hoặc Destroy.

**Bước 5 — Ràng buộc business authorization.** Billing chỉ ký record đã approved; Customer Reader chỉ đọc record thuộc tenant và quyền của caller; JWT issuer kiểm tra claims/issuer/audience; Webhook dùng HMAC theo partner và chống replay.

**Bước 6 — Enforce format.** Envelope ghi content DEK và wrapping KEK references riêng, có AAD cho tenant/record/key purpose; chữ ký có canonical bytes và version; verifier chọn public key từ trust source.

**Bước 7 — Hoàn thiện vòng đời.** Key trạng thái RETIRED có thể cho Decrypt/Verify lịch sử theo policy; Encrypt/Sign mới chỉ dùng Active/current version. Migration có concurrency control và restore test.

**Bước 8 — Thực hiện negative tests.** Chạy thử dùng DEK để Wrap, dùng Billing key để ký JWT, cross-tenant Unwrap, sửa client-provided purpose, dùng signing key Retired để Sign; mọi yêu cầu trái policy phải bị từ chối cả khi cố đi trực tiếp tới provider.

**Bước 9 — Audit và đối soát.** Thống kê effective grants/attributes và actual usage so với inventory, phát hiện orphan keys, purpose drift và IAM quá rộng.

### 17.4. Kết quả mong đợi

- Một **DEK lộ** có phạm vi ảnh hưởng giới hạn theo record/object/batch, không kéo theo việc raw KEK phải nằm trong cùng JVM.
- **KEK rotation** có thể rewrap EDK nhưng không thay content purpose; archive tiếp tục có đường Unwrap đúng key version.
- Một **Billing signing key** không thể được Token Issuer sử dụng chỉ vì cùng thuật toán Ed25519.
- **HMAC key** của Partner A không dùng làm MAC của Partner B.
- Hệ thống có thể chứng minh theo audit rằng **principal nào đã làm operation gì trên keyPurpose nào**, với approved policy.
- Khi xảy ra sự cố, đội an ninh đánh giá đúng **permission drift, API misuse hay material compromise**, từ đó chọn biện pháp phù hợp.

Kết quả này không đến từ **field keyPurpose đơn lẻ**. Nó cần đồng bộ **metadata, trust, provider restrictions, data formats, business authorization và lifecycle**.

## 18. Checklist Key purpose metadata trước khi triển khai

1. **Taxonomy:** Có danh mục cryptographic purpose được quản lý, không cho OTHER/ANY tùy tiện trong production?
2. **Business purpose:** Có phân biệt invoice signing, JWT signing, webhook HMAC, customer data và firmware signing?
3. **Key identity:** Mỗi material có key ID/version bất biến, provider reference, tenant/environment?
4. **Algorithm:** Key type/curve/size/algorithm có tương thích với purpose và protocol?
5. **Operations:** Allowed operations được khai báo theo purpose và ánh xạ đúng với provider APIs?
6. **No key reuse:** Có tránh dùng cùng material cho CONTENT_ENCRYPTION và DATA_KEY_WRAPPING, hoặc ký JWT và invoice?
7. **KDF context:** Nếu derive nhiều key từ root, có domain separation, info encoding, purpose/tenant scope và root protection?
8. **Owner:** Có Key owner, Security owner, custodian và on-call chịu trách nhiệm?
9. **Provider policy:** IAM/key grants và HSM/PKCS#11 attributes có enforce usage thật, không chỉ là tags?
10. **JWK:** use, key_ops, alg, kid, key type và trusted issuer có nhất quán theo JOSE profile?
11. **X.509:** KeyUsage/EKU, SAN, chain và certificate revocation có được kiểm tra đúng ứng dụng?
12. **Identity:** Service token có issuer, audience, subject, expiry và scope tin cậy?
13. **Business authorization:** Caller có quyền với dữ liệu/record trước khi Sign/Decrypt/Unwrap?
14. **Storage:** Raw DEK/KEK/private key có nằm ở boundary cho phép, exportability được xác nhận bằng provider?
15. **State/cryptoperiod:** ACTIVE cho Sign/Encrypt mới; RETIRED/COMPROMISED/DESTROYED được xử lý đúng policy?
16. **AAD:** Tenant, record, purpose/keyRef được encode nhất quán và authenticated khi giao thức cần?
17. **Envelope:** DEK/KEK có metadata riêng, không nhầm content và wrapping purpose, ghi immutable versions?
18. **Rotation:** Thay key material/cryptoperiod không được thay bằng sửa một nhãn/version ảo?
19. **Rewrap vs re-encrypt:** Có phân biệt đổi KEK của EDK và thay DEK mã hóa content?
20. **Nonce:** AES-GCM nonce không lặp theo cùng DEK/KEK, kể cả multi-instance và restore?
21. **Audit:** Có before/after metadata, revision, actor, approver, usage results nhưng không ghi raw key?
22. **SoD:** Người xin grant/thay purpose không tự sửa provider policy và xóa audit được?
23. **Drift:** Có đối soát inventory với provider key usage/attributes, role grants, certificate profiles?
24. **Tampering:** Purpose từ request/JSON/JWK chưa tin có được kiểm tra với trusted registry và trust source?
25. **Negative tests:** Dùng sai purpose, wrong algorithm, cross-tenant, retired key new-use và direct KMS bypass đều bị từ chối?
26. **Historical use:** Dữ liệu/transaction ký trước vẫn có key versions/trust để Decrypt/Verify theo retention?
27. **Backup/DR:** Archive, wrapped DEK, KEK versions, root recovery và restoration permissions có được kiểm chứng?
28. **Revocation:** Biết khác nhau giữa revoke IAM, disable key, rotate secret, revoke certificate và destroy material?
29. **Offboarding:** Owner mới, grants, HSM custodian và shared secrets đã được rà khi nhân sự/service rời?
30. **Incident response:** Có cách xử lý riêng metadata drift, KMS API misuse và raw key compromise?
31. **Cache:** Key state/purpose/grants cache có TTL, revision và effective-time semantics, tránh stale re-grant?
32. **Public metadata:** Key IDs/JWKS/cert có integrity và trust, không chỉ dễ tải hoặc khó đoán?

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Key purpose metadata khác gì algorithm?

**Trả lời:** Algorithm chỉ cơ chế, ví dụ AES-256-GCM hoặc Ed25519; purpose nói **khóa được phép dùng cho chức năng nào** như CONTENT_ENCRYPTION, DATA_KEY_WRAPPING hoặc BILLING_INVOICE_SIGNATURE. Hai khóa có cùng thuật toán có thể cần vật liệu và quyền tách biệt.

**Câu 2.** Đặt keyPurpose = DATA_KEY_WRAPPING vào YAML có tự ngăn mọi service gọi Decrypt hoặc Sign không?

**Trả lời:** **Không.** Đây có thể chỉ là metadata mô tả. Cần cấu hình IAM/KMS/HSM operations đúng, kiểm tra identity và policy tại nơi thực thi.

**Câu 3.** Một private Ed25519 key ký hóa đơn có nên được dùng luôn để ký JWT access token không?

**Trả lời:** **Không nên mặc định.** Nên dùng keypairs khác nhau theo business purpose và protocol, tránh cross-protocol signing oracle và giảm blast radius.

**Câu 4.** JWK use = sig có tự chứng minh public key được phát hành bởi issuer đáng tin không?

**Trả lời:** **Không.** use chỉ mô tả mục đích. Verifier phải xác thực nguồn public key/JWKS, issuer, audience, algorithm và token claims theo policy.

**Câu 5.** X.509 KeyUsage digitalSignature có nghĩa một mTLS client certificate được quyền ký hóa đơn không?

**Trả lời:** **Không.** KeyUsage/EKU là profile sử dụng chứng thư; quyền ký hóa đơn là business authorization riêng, nên tách keys khi phù hợp.

**Câu 6.** PKCS#11 CKA_WRAP và CKA_UNWRAP liên quan đến gì?

**Trả lời:** Chúng mô tả/kiểm soát khả năng dùng một key object cho Wrap/Unwrap theo token/provider. Nhãn CKA_LABEL không tự làm một business purpose được enforce.

**Câu 7.** Nếu tenant B biết keyId của tenant A, họ có được Unwrap vì metadata không bí mật không?

**Trả lời:** **Không.** KeyId không phải bearer credential. Business authorization và provider IAM/key policies phải từ chối cross-tenant use.

**Câu 8.** Tại sao việc chuyển purpose của một DEK thành KEK qua sửa metadata là nguy hiểm?

**Trả lời:** Vì raw material ban đầu có thể đã được dùng cho content encryption và có copies/nonce/security assumptions riêng. Sửa nhãn không tạo material độc lập hay migration; nên tạo KEK mới đúng purpose.

**Câu 9.** Key RETIRED còn dùng được để VERIFY hoặc DECRYPT lịch sử không?

**Trả lời:** **Có thể**, theo trust/retention và provider policy. Không được Sign/Encrypt mới nếu cryptoperiod đã hết; compromised/suspended có quy tắc khác.

**Câu 10.** Một hồ sơ đã đổi alias current từ KEK-v3 sang v4 thì mọi EDK cũ tự được rewrap chưa?

**Trả lời:** **Chưa.** Phải theo dõi EDK phụ thuộc v3 và migration. Alias không làm vật liệu EDK cũ thay đổi.

**Câu 11.** Khi DEK lộ, chỉ rewrap cùng DEK bằng KEK mới có khôi phục confidentiality không?

**Trả lời:** **Không.** Người biết raw DEK vẫn có thể giải mã ciphertext dùng key cũ. Cần đánh giá DEK rotation và re-encryption.

**Câu 12.** AAD có thể chứng minh một caller được phép dùng key chỉ vì tenantId khớp không?

**Trả lời:** **Không.** AAD bảo vệ tính toàn vẹn bytes của context dưới AEAD, không thay thế kiểm tra quyền từ trusted identity và resource ownership.

**Câu 13.** Một HSM key có CKA_SIGN = true có nghĩa mọi thông điệp được ký đều được nghiệp vụ chấp thuận không?

**Trả lời:** **Không.** HSM cho phép crypto operation, nhưng logic chấp thuận invoice/firmware/token phải ở policy/gateway và được audit.

**Câu 14.** Khác nhau giữa keyPurpose và key state là gì?

**Trả lời:** Purpose mô tả **chức năng**; state mô tả **giai đoạn khả dụng**. Billing signing key có thể ACTIVE rồi RETIRED nhưng vẫn là billing signing key.

**Câu 15.** Vì sao không nên cho client gửi một JSON tự khai purpose rồi hệ thống lập tức sử dụng?

**Trả lời:** JSON có thể bị giả/sửa. Cần resolve purpose/keyRef từ trusted registry và provider attributes, kiểm tra algorithm, state, identity và authorization trước crypto.

**Câu 16.** Purpose mismatch có chắc raw key material đã bị lộ không?

**Trả lời:** **Không.** Có thể là drift hoặc config lỗi; phải điều tra actual operations, grants, exports và exposure. Khi raw key lộ, cần xử lý rotation/trust/data riêng.

**Câu 17.** Nếu provider IAM cho phép Sign trên key nhưng app policy DENY, một workload bị RCE có thể bypass không?

**Trả lời:** **Có thể**, nếu principal gọi KMS/HSM trực tiếp. Cần enforce ở provider, giới hạn grants hoặc tách crypto gateway/identity theo threat model.

**Câu 18.** Cryptoperiod của signing key hết có nghĩa xóa public key khỏi JWKS/trust store ngay không?

**Trả lời:** **Không mặc định.** Verifier có thể còn cần public key để Verify token/chữ ký lịch sử. Thời gian trust phụ thuộc expiry, revocation và protocol.

**Câu 19.** Nếu một KDF root bị lộ, đổi nhãn info có đủ bảo vệ các derived keys không?

**Trả lời:** **Không.** Đối thủ có root có thể dẫn xuất lại các nhánh nếu biết context. Cần đánh giá thay root và derived material bị ảnh hưởng.

**Câu 20.** Hệ thống đã có metadata đầy đủ và mọi API trả HTTP 200 có thể coi key policy đã được thực thi chính xác chưa?

**Trả lời:** **Chưa.** Cần kiểm tra provider attributes/grants, trạng thái có hiệu lực ở data plane, direct API negative tests, audit và các tình huống rotation/revocation.

## 20. Tổng kết

**Key purpose metadata** là hợp đồng quản trị quan trọng chỉ rõ **một khóa được dùng cho mục đích mật mã và nghiệp vụ nào**. Nó không phải thuật toán, không phải IAM grant và cũng không chỉ là nhãn hiển thị. Khi gắn với **key type, algorithm, allowed operations, tenant/owner, key ID/version, state, cryptoperiod và provider policy**, metadata giúp ngăn dùng sai khóa, lập kế hoạch rotation và khoanh vùng sự cố.

Những nguyên tắc cần giữ:

- **Tách key material theo purpose:** DEK khác KEK, JWT signing khác invoice signing, HMAC secret theo protocol/partner và root KDF được bảo vệ riêng.
- **Không tin untrusted metadata:** resolve key reference/purpose từ nguồn có thẩm quyền; kiểm tra JWK/X.509/PKCS#11/KMS semantics phù hợp.
- **Enforce nhiều lớp:** service identity, business authorization, trusted registry, provider usage attributes/IAM và audit cùng chỉ về một chính sách.
- **Không nhầm purpose với lifecycle:** key RETIRED có thể còn cho historical-use theo policy, compromised material không được “chữa” bằng sửa nhãn.
- **Kiểm thử cả ALLOW và DENY:** wrong purpose, wrong principal, wrong tenant, wrong algorithm, expired cryptoperiod, direct KMS bypass và metadata tampering.

**Điểm cốt lõi:** Một khóa mạnh chỉ thực sự được dùng an toàn khi **đúng người, đúng dữ liệu, đúng operation, đúng mục đích và đúng thời điểm**. Key purpose metadata tạo ngôn ngữ chung để áp dụng các ràng buộc ấy; **KMS/HSM, IAM, ứng dụng và quy trình kiểm toán** phải cùng thực thi thay vì chỉ lưu một trường đẹp trong key inventory.
