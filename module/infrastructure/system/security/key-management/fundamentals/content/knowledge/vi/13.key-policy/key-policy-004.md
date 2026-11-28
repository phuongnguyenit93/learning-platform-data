# Key storage policy: Chính sách lưu trữ khóa mật mã an toàn

Một hệ thống Java dùng AES-GCM mã hóa hồ sơ khách hàng, HMAC xác thực yêu cầu và Ed25519 ký tài liệu. Nhóm phát triển đã lựa chọn thuật toán đúng, nhưng lại lưu **DEK bản rõ trong database**, **private signing key dưới dạng PEM trong container image**, còn **KEK được chép sang nhiều máy để phòng khi KMS ngừng hoạt động**. Hệ thống có thể tạo ra ciphertext và chữ ký hợp lệ về mặt toán học, nhưng **kiến trúc lưu trữ khóa đã làm mất đi phần lớn giá trị của mật mã**.

**Key storage policy (chính sách lưu trữ khóa)** là tập hợp các quy tắc xác định **vật liệu khóa nào được giữ ở đâu, dưới hình thức gì, ai có quyền truy cập/sử dụng/xuất/khôi phục, trong bao lâu, bằng phương pháp bảo vệ nào và với bằng chứng kiểm toán nào**. Chính sách phải bao phủ bản sao khóa trong bộ nhớ, tệp cấu hình, database, kho bí mật, KMS/HSM, bản sao lưu, thiết bị dự phòng và các môi trường chạy ứng dụng.

Trong chương **Key policy** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề này gắn trực tiếp với vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**, đồng thời kết nối AES-GCM, RSA/Ed25519, chữ ký số, HMAC, KDF, envelope encryption, IAM và audit. **Lưu trữ an toàn** không chỉ là bật mã hóa ổ đĩa; điều quyết định là có bảo vệ đúng **key material**, **ranh giới tin cậy** và **quyền thực hiện phép toán mật mã** hay không.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **key material**, **key metadata**, **key identifier**, **wrapped key**, **plaintext DEK**, **KEK**, **private/public key** và các secret trung gian.
2. Thiết kế chính sách lưu trữ theo **mức độ nhạy cảm, purpose, tenant, environment, cryptoperiod và threat model**.
3. Giải thích khi nào nên dùng **KMS/HSM non-exportable**, key handle, key wrapping, encrypted keystore và bộ nhớ tiến trình.
4. Áp dụng **envelope encryption** mà không lưu nhầm DEK bản rõ cùng ciphertext hoặc dùng sai AES-GCM nonce/AAD.
5. Xác lập quyền **Create, Encrypt, Decrypt, Sign, Wrap, Unwrap, Export, Rotate, Disable và Destroy** theo nguyên tắc tối thiểu.
6. Thiết kế backup/restore, rotation và hủy khóa sao cho không làm mất dữ liệu hoặc tạo bản sao bí mật không kiểm soát.
7. Xây dựng policy kiểm thử được trong Java 17, hiểu ranh giới giữa **metadata policy gate** và enforcement thực ở KMS/HSM.

## 2. Chính sách lưu trữ bảo vệ đối tượng nào?

Một chương trình không chỉ có một loại khóa. Trước tiên phải **kiểm kê loại material và điều kiện sử dụng**.

| Loại dữ liệu | Ví dụ | Nhạy cảm? | Hướng lưu trữ |
|---|---|---|---|
| **Root key / master key / KEK** | Khóa bảo vệ những khóa con hoặc DEK | **Rất cao** | KMS/HSM hoặc ranh giới bảo vệ có mức assurance phù hợp; hạn chế/không xuất |
| **DEK bản rõ** | AES-256 key dùng mã hóa một tập dữ liệu | **Cao** | Chỉ xuất hiện nơi thực hiện mật mã, thời gian tối thiểu; không lưu dạng bản rõ trong DB/log |
| **Wrapped/encrypted DEK** | DEK được bảo vệ dưới KEK | Nhạy cảm nhưng đã được bảo vệ | Có thể lưu kèm ciphertext theo thiết kế, quyền truy cập và integrity phù hợp |
| **Private signing key** | Ed25519, ECDSA hoặc RSA-PSS private key | **Rất cao** | Ưu tiên non-exportable trong KMS/HSM cho signing service |
| **Public verification key** | Public key/JWKS để Verify signature | Thông thường **không bí mật** | Có thể công bố, nhưng **nguồn tin cậy và tính toàn vẹn** phải được xác minh |
| **HMAC key** | Secret của webhook/API MAC | **Cao** | Secret store/KMS/HSM theo khả năng; giới hạn principal và purpose |
| **KDF root, IKM, PRK, OKM** | Root secret và khóa dẫn xuất bằng HKDF | **Cao** | Root được cô lập; PRK/OKM không log và giữ ít lâu; kiểm soát DeriveKey |
| **Ephemeral private key/session secret** | X25519 private scalar hoặc khóa phiên | **Cao** | Giới hạn phạm vi phiên/bộ nhớ, hủy bản sao khi hết nhu cầu |
| **Password/pepper** | User password tạm thời, pepper đăng nhập | **Cao** | Password verifier dùng password hashing; pepper ở kho bí mật có chính sách riêng |
| **Key ID/version/state/purpose** | KMS resource ID, rotation metadata | Thường không phải secret | Registry có integrity, authorization, audit và khả năng tra cứu lịch sử |
| **Certificate, salt, nonce** | X.509, HKDF salt, GCM nonce | Thường không bí mật | Phải đúng định dạng/nguồn/tính duy nhất theo thuật toán |

**Không được lưu khóa bí mật trong một hệ thống chỉ vì hệ thống đó đã mã hóa ở tầng đĩa.** Nếu database chứa cả ciphertext và khóa giải mã bản rõ, việc chiếm quyền đọc database có thể làm mất cả hai lớp bảo vệ. Nếu HSM giữ KEK nhưng một bản sao KEK xuất ra tệp log, tính non-exportable trong HSM không còn giải quyết được rủi ro bản sao đó.

### 2.1. Key material khác key metadata

~~~text
Key inventory record:
    keyId         = "billing-sign-v3"
    algorithm     = "Ed25519"
    purpose       = "SIGN"
    tenant        = "tenant-42"
    state         = "ACTIVE"
    providerRef   = "kms://approved-provider/..."
    exportPolicy  = "DENY"

Private key bytes:
    chỉ nằm trong ranh giới mật mã được phê duyệt
    không nằm trong inventory record, source code hoặc log
~~~

Key ID, alias, owner, policy reference và vòng đời là **metadata** để quản trị. Metadata thường không cần giữ bí mật như private key nhưng cần được **bảo vệ tính toàn vẹn**, vì sửa **keyId**, **tenant**, **state** hoặc **policyRef** có thể làm ứng dụng chọn sai khóa hoặc vượt quyền.

### 2.2. Những câu hỏi chính sách phải trả lời

- **Ai sở hữu?** Application, tenant, bộ phận chịu trách nhiệm, hệ thống quản trị.
- **Khóa dùng làm gì?** Encrypt/Decrypt, Sign/Verify, Wrap/Unwrap, MAC hoặc DeriveKey.
- **Khóa ở đâu?** KMS/HSM, vault, encrypted keystore, database, memory, backup, thiết bị đối tác.
- **Có xuất được không?** Raw export, wrapped export, public-key export và backup có ngữ nghĩa khác nhau.
- **Ai được gọi phép toán?** Workload identity, human operator, break-glass principal.
- **Thời gian sử dụng?** Cryptoperiod, TTL cho derived key/cache và điều kiện retire/rotate.
- **Làm sao khôi phục?** Key version, wrapped DEK, restore procedure, backup/escrow được phép.
- **Làm sao chứng minh?** Policy version, audit actor/operation, provider state, kiểm thử từ chối và bằng chứng hủy.

## 3. Bốn nguyên tắc nền tảng

### 3.1. Phân loại trước khi chọn nơi lưu trữ

**Không nên áp một quy tắc đồng nhất cho mọi loại khóa.** Root KEK bảo vệ hàng triệu DEK cần mức kiểm soát khác một khóa phiên chỉ sống vài giây. Public key của đối tác cần **authenticity** nhiều hơn confidentiality. Mật khẩu do người dùng chọn cần password hashing, không phải chỉ đặt trong một biến môi trường.

Một policy tốt mô tả **risk tier** theo impact của compromise và phạm vi dữ liệu:

| Risk tier minh họa | Khóa điển hình | Yêu cầu |
|---|---|---|
| **Critical** | Root/KEK tập trung, signing CA/issuer private key | Ranh giới KMS/HSM được phê duyệt, non-exportable nếu có thể, quyền tách biệt, audit mạnh |
| **High** | Tenant KEK, HMAC signing secret, private encryption key | KMS/HSM/secret service theo threat model, quản lý vòng đời và quyền chặt |
| **Restricted ephemeral** | Plaintext DEK, PRK/OKM, session secret | Chỉ hiện diện trong phạm vi thực thi được phép, hạn chế sao chép, cleanup best effort |
| **Public integrity-sensitive** | Public key, certificate, key ID/registry metadata | Nguồn tin cậy, kiểm tra integrity, thay đổi có kiểm soát |

**Tier chỉ là ví dụ thiết kế**, không phải phân hạng chuẩn áp dụng toàn cầu. Quyết định cuối cùng cần có threat model và chính sách tổ chức.

### 3.2. Tách khóa bảo vệ khỏi dữ liệu cần bảo vệ

**Envelope encryption** tách **DEK** (mã hóa dữ liệu) khỏi **KEK** (bọc DEK). Database có thể giữ ciphertext và wrapped DEK trong cùng record, còn KEK được giữ tại KMS/HSM theo policy.

Tách lớp chỉ hữu ích khi **quyền Decrypt/Unwrap KEK không được cấp vô hạn** cho bất kỳ workload nào đọc được database. Nếu mọi service có quyền đọc ciphertext đều có thể Unwrap mọi DEK, ranh giới bảo vệ yếu đi.

### 3.3. Giảm khả năng xuất raw key và thời gian sống của bản rõ

Ưu tiên **key handle/non-exportable key** cho root/KEK và private signing key khi khả năng provider và yêu cầu nghiệp vụ phù hợp. Với plaintext DEK cần dùng local AES-GCM, kiểm soát **thời điểm xuất, nơi xuất, TTL, vùng nhớ, số bản sao và quyền của caller**.

Non-exportable **không có nghĩa không thể lạm dụng khóa**. Một principal có quyền Sign hoặc Decrypt quá rộng vẫn có thể yêu cầu HSM/KMS thực hiện thao tác trái phép dù không biết key bytes.

### 3.4. Policy phải có enforcement và bằng chứng

Một tệp chính sách ghi **DENY_EXPORT** không tự ngăn lập trình viên gọi một API export nếu provider vẫn cho phép. Phải kiểm tra chính sách **ở ranh giới thực hiện hành động**, ví dụ key attributes trong HSM, IAM/key policy tại KMS, workload authorization và inventory control plane.

**Enforcement**, **monitoring**, **đánh giá ngoại lệ** và **kiểm thử khôi phục** quan trọng hơn việc chỉ có tài liệu chính sách.

## 4. Chọn nơi lưu trữ: KMS, HSM, keystore, vault và memory

| Nơi lưu | Điểm mạnh | Giới hạn/rủi ro | Phù hợp khi |
|---|---|---|---|
| **HSM chuyên dụng** | Khóa có thể non-exportable; phép toán trong ranh giới mật mã chuyên biệt | Chi phí, latency, HA, API/algorithm support, backup policy và vận hành | Root, signing key, KEK có yêu cầu assurance cao |
| **Managed KMS** | Key policy, IAM, rotation và audit được dịch vụ hỗ trợ | Có thể trả plaintext DEK, còn phụ thuộc cloud account và quyền API | Envelope encryption, quản lý KEK theo tổ chức |
| **Secrets manager/vault** | Cấp secret cho workload, versioning/lease/audit theo sản phẩm | Nhiều sản phẩm trả raw secret ra process; không tương đương HSM | Secret ứng dụng, HMAC key khi policy cho phép |
| **Encrypted keystore file** | Có thể vận hành offline, hỗ trợ một số provider Java | File và password/key bảo vệ file là hai bí mật cần quản lý; backup và filesystem ACL | Workload cục bộ, legacy hoặc yêu cầu offline có đánh giá |
| **Database lưu wrapped key** | Gắn key reference/ciphertext, quản lý theo đối tượng | Không bảo vệ nếu unwrap permission quá rộng hoặc metadata bị tráo | Wrapped DEK/PKI metadata, không phải raw KEK |
| **Process memory** | Cần thiết cho một số phép toán local | Heap dump, native copies, GC, cache, RCE/host compromise | Secret/DEK tạm, lifetime tối thiểu |
| **Tệp PEM/JSON bản rõ** | Dễ thao tác | Secret bị lộ qua image, backup, log, permission lỗi | **Không nên dùng** cho private/secret key production |
| **Mã nguồn/container image/Git** | Không phải secure key storage | Rò rỉ qua clone, build cache, artifact và lịch sử commit | **Không được** chứa raw secret/private key |
| **Environment variable** | Dễ inject trong một số hệ thống | Có thể lộ qua diagnostic, child process, config dump, quyền runtime | Chỉ khi policy chấp nhận rủi ro và không có lựa chọn tốt hơn |

**Không mặc định mọi KMS/HSM giống nhau:** một provider có thể hỗ trợ **GenerateDataKey**, một provider khác chỉ có **Encrypt/Decrypt/Sign**, HSM có thể yêu cầu PKCS#11 attributes và session khác nhau. Mọi tuyên bố về **non-exportability, backup, import, rotation, deletion và vùng tồn tại raw key** đều phải được xác minh trong contract cụ thể.

### 4.1. Non-exportable là một thuộc tính, không phải trạng thái an toàn tuyệt đối

Một private key non-exportable có thể vẫn bị lạm dụng bởi **Sign oracle** nếu IAM/policy cho phép caller không đáng tin ký những bytes tùy ý. Tương tự, khóa KEK non-exportable vẫn có thể bị dùng để **Unwrap** những DEK trái phép nếu principal có quyền quá rộng.

Policy phải bảo vệ hai tài sản riêng:

1. **Tính bí mật của key material:** không export, backup/restore có bảo vệ, giới hạn bản sao.
2. **Quyền sử dụng key material:** ai được Sign, Decrypt, DeriveKey, Unwrap, trong tenant/purpose/context nào.

### 4.2. Encrypted keystore không thay thế quản trị password

Nếu ứng dụng lưu private key trong một **PKCS#12/keystore** có mật khẩu, vẫn phải giải quyết:

- Password của keystore đến từ đâu? Có hardcode trong mã nguồn, config hoặc environment không?
- Ai có quyền đọc file keystore, snapshot, bản sao lưu và password?
- Khi load keystore, private key có xuất hiện dưới dạng object có thể export trong JVM không?
- Có phân tách keystore theo môi trường/tenant hoặc purpose không?
- Có cách thay password, thay key, backup, restore và ghi audit không?

**Keystore file bị mã hóa + password nằm cạnh file với cùng quyền đọc** thường là một ranh giới bảo vệ yếu khi host bị chiếm. Với yêu cầu cao, giữ key trong KMS/HSM và dùng handle sẽ giảm phần key material phải đưa vào process.

### 4.3. Ứng dụng Java và giới hạn zeroization

Với **byte[]** và **char[]**, có thể ghi đè những mảng do caller sở hữu trong **finally**; tuy nhiên **SecretKeySpec**, **KeyStore**, **Mac**, **Cipher**, native provider hoặc JVM có thể giữ bản sao khác. **String** không có API hủy nội dung đáng tin. **System.gc()** không phải biện pháp xóa khóa.

Tránh chuyển raw key sang **Base64 String, toString, JSON serialization, exception message hoặc trace** trừ khi một giao thức bắt buộc và đã có cơ chế quản lý bản sao. Nếu cần xử lý raw DEK trong JVM, đặt giới hạn lifetime, log redaction, dump policy, phân quyền host và incident response.

## 5. Data at rest, in transit, in use và backup

Chính sách lưu trữ chỉ đủ khi bao phủ **mọi trạng thái có thể chứa material**, không chỉ database chính.

| Trạng thái | Nguy cơ | Kiểm soát cần đánh giá |
|---|---|---|
| **At rest** | File, database, disk/snapshot chứa key bytes | Wrap/encrypt key, KMS/HSM, ACL, storage encryption, metadata integrity |
| **In transit** | Secret bị lộ khi truyền qua mạng hoặc service boundary | Kênh bảo mật/authenticated channel, mTLS/TLS phù hợp, giới hạn người nhận |
| **In use** | Heap/native memory, RCE, debug, cache | Key handle nếu có thể, least privilege, thời gian sống ngắn, hạn chế dump |
| **Backup/replica** | Material được sao chép ngoài policy hoặc hủy không hết | Backup encryption, độc lập quyền, kiểm tra restore, retention và deletion |
| **Development/CI** | Khóa production xuất hiện trong build/test pipeline | Tách môi trường, secret injection phù hợp, không commit/log secret |
| **Disposal** | Key vẫn còn trong cache, swap, snapshot, HSM backup | Quy trình destroy/crypto-erasure với inventory dependency và bằng chứng |

Một host có **full-disk encryption** có thể bảo vệ dữ liệu khi ổ bị lấy vật lý, nhưng **không tự bảo vệ key material trước người có quyền đọc sau khi hệ thống boot**. Mô hình kiểm soát phải xét cả quyền runtime, sự cố credential và thao tác KMS.

## 6. Envelope encryption đúng với storage policy

Một mô hình phổ biến:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant KMS as KMS/HSM quản lý KEK
    participant DB as Storage
    App->>KMS: Xin cấp DEK hoặc wrap DEK theo quyền
    KMS-->>App: DEK tạm + wrapped DEK
    App->>App: AES-GCM Encrypt(payload, DEK, nonce, AAD)
    App->>DB: Lưu ciphertext, tag, nonce, wrapped DEK, keyRef
    App->>App: Hủy best-effort bản sao plaintext DEK
    Note over KMS: KEK không xuất raw material
    App->>DB: Đọc bản ghi theo quyền truy cập
    DB-->>App: Ciphertext + envelope metadata
    App->>KMS: Decrypt/Unwrap wrapped DEK đúng context
    KMS-->>App: Plaintext DEK theo policy
    App->>App: AES-GCM Verify tag rồi mới dùng plaintext
~~~

Sơ đồ là **một pattern minh họa**, không phải hợp đồng API chung cho mọi provider. Một số KMS hỗ trợ **GenerateDataKey**, một số yêu cầu caller tự sinh DEK và gọi **WrapKey/Encrypt**, một số giữ DEK bên trong crypto service. Chính sách phải nêu rõ **nơi có plaintext DEK và nơi có KEK** ở từng biến thể.

### 6.1. Storage requirements cho mỗi thành phần

| Thành phần | Nơi lưu hợp lý | Không nên |
|---|---|---|
| **KEK** | KMS/HSM/approved key boundary, non-exportable khi phù hợp | Commit file raw KEK hoặc chép cho mọi ứng dụng |
| **Plaintext DEK** | Bộ nhớ của tiến trình được cấp quyền, TTL ngắn hoặc ranh giới crypto service | Lưu thường trực cạnh ciphertext |
| **Wrapped DEK** | Database/object storage cùng envelope, có keyRef và policy | Giả định nó không cần quản lý vì đã được wrap |
| **Nonce AES-GCM** | Metadata của bản mã, đảm bảo duy nhất **với cùng DEK** | Dùng cố định hoặc lặp lại trên cùng DEK |
| **AAD** | Có thể lưu/tái dựng từ metadata và ngữ cảnh đáng tin | Tin tenant ID do người gọi tự khai để bỏ qua IAM |
| **Key ID/version** | Metadata có integrity và khả năng resolve lâu dài | Chỉ lưu alias động; thay version mà không migrate đúng |

### 6.2. AAD, nonce và key version

AES-GCM yêu cầu **nonce không được tái sử dụng với cùng một AES key**. Nonce 96 bit là lựa chọn phổ biến, nhưng việc lấy ngẫu nhiên không làm xác suất trùng bằng 0. Ứng dụng nhiều instance phải quản lý nonce toàn bộ phạm vi của DEK và giới hạn số lượt encrypt theo thiết kế.

AAD có thể ràng buộc **tenant, record ID, algorithm, schema version, purpose**. Nếu đưa **wrapping key version** vào AAD payload, việc rewrap DEK từ KEK-v3 sang v4 mà chỉ sửa metadata sẽ làm **GCM tag không khớp**. Thiết kế cần phân ranh giới giữa **payload AAD** và **metadata của lớp wrapping**, xác thực đúng cả hai theo giao thức. Không tự thay một trường JSON rồi coi dữ liệu đã migrate an toàn.

### 6.3. Rewrap khác re-encrypt

~~~text
Payload ciphertext = AES-GCM(DEK-v7, plaintext, nonce, AAD)
Wrapped DEK v3     = Wrap(KEK-v3, DEK-v7)

Rotate KEK:
    Wrapped DEK v4 = Wrap(KEK-v4, DEK-v7)
    Payload có thể giữ nguyên nếu AAD/policy tương thích.

Rotate DEK:
    DEK-v8 được tạo mới
    Payload phải decrypt và re-encrypt bằng DEK-v8 để thay DEK.
~~~

Nếu **DEK đã lộ**, chỉ rewrap bằng KEK mới **không khắc phục lộ DEK**. Nếu **KEK đã lộ**, cần khoanh vùng mọi DEK đã được wrap và đánh giá ciphertext/hệ quả. Storage policy phải phân biệt trường hợp nào cần **rewrap**, **re-encrypt**, **revoke** hoặc **rotate signing key**.

## 7. Viết storage policy thành các điều kiện có thể kiểm tra

Một tài liệu nói “khóa quan trọng phải được bảo vệ” quá mơ hồ để kiểm tra. Chính sách khả thi cần mô tả **thuộc tính khóa, điều kiện lưu trữ, quyền dùng, ngoại lệ và bằng chứng**.

Ví dụ **schema minh họa**, không phải cấu hình thực của KMS hay chuẩn chung:

~~~yaml
policyId: crypto-key-storage-production-v1
scope:
  environment: production
  keyKinds:
    - ROOT_KEK
    - PRIVATE_SIGNING
    - HMAC_KEY
    - DATA_KEY
requirements:
  ROOT_KEK:
    allowedStorage: [HSM, APPROVED_KMS]
    rawExport: DENY
    keyUsage: [WRAP, UNWRAP]
    adminSeparation: REQUIRED
    audit: REQUIRED
  PRIVATE_SIGNING:
    allowedStorage: [HSM, APPROVED_KMS]
    rawExport: DENY
    keyUsage: [SIGN]
    businessApproval: REQUIRED
  HMAC_KEY:
    allowedStorage: [HSM, APPROVED_KMS]
    rawExport: DENY
    keyUsage: [GENERATE_MAC, VERIFY_MAC]
  DATA_KEY:
    allowedStorage: [APPROVED_CRYPTO_SERVICE, PROCESS_MEMORY_EPHEMERAL]
    persistentPlaintextStorage: DENY
    maxLocalKeyLifetimeSeconds: 60
    encryptedAtRestWhenPersistent: REQUIRED
exceptions:
  approval: SECURITY_REVIEW
  expiresAt: REQUIRED
  audit: REQUIRED
~~~

**Không áp schema trên trực tiếp vào một nhà cung cấp** mà chưa ánh xạ được các thuộc tính thực. Chẳng hạn **APPROVED_KMS** là một loại tài sản theo chính sách nội bộ; KMS có thể không hỗ trợ tính năng **DeriveKey**, non-exportable hay key usage như mong đợi. **maxLocalKeyLifetimeSeconds** là một giới hạn vận hành cần thiết kế thực thi, không phải thuộc tính tự có trong Java byte array.

### 7.1. Ma trận kiểm soát bắt buộc

| Điều kiện | Root/KEK | Private signing key | HMAC key | DEK dùng local AES-GCM |
|---|---|---|---|---|
| Xác thực owner, tenant, environment | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| Tham chiếu immutable key ID/version | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc để restore |
| Không lưu raw material trong Git/CI/log | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| Non-exportable trong KMS/HSM | Ưu tiên/bắt buộc theo tier | Ưu tiên/bắt buộc theo tier | Nếu provider/policy cho phép | Không luôn khả thi nếu mã hóa tại ứng dụng |
| Phạm vi operations | Wrap/Unwrap/Derive theo purpose | Sign, không Decrypt | Generate/Verify MAC | Encrypt/Decrypt với DEK |
| Kiểm soát bản sao trong memory | Khi tồn tại | Khi tồn tại | Khi tồn tại | **Đặc biệt quan trọng** |
| Backup, restore và rotation | Theo recovery policy | Theo ký và xác minh lịch sử | Theo thời gian chấp nhận MAC | Theo ciphertext dependency |
| Audit sử dụng và thay đổi policy | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc tại ranh giới liên quan |

**Non-exportable** cần được đánh giá cùng nhu cầu **HA, DR, key backup và hủy**. Một HSM có thể hỗ trợ sao lưu key material trong **wrapped/secure backup domain** dù không cho ứng dụng xuất private key bản rõ. Không được suy từ chữ non-exportable rằng không có backup hoặc không thể di chuyển vật liệu qua quy trình thiết bị được phê duyệt.

### 7.2. Quy tắc chọn khóa khi có nhiều version

**Mã hóa/ký mới:** chọn key version đang được phép thực hiện tác vụ, từ registry/alias đã được quản lý và ghi lại **resolved key ID/version thực tế**.

**Giải mã/Verify lịch sử:** dùng reference version đã được xác thực và chính sách tương ứng. Nếu khóa đã retire, có thể tồn tại đường **decrypt-only** hoặc **verify-only** theo mục đích, nhưng không mặc định rằng một key ở trạng thái Suspended vẫn được Unwrap.

**Cấm alias làm nguồn thật duy nhất cho ciphertext cũ:** alias thay đổi khi rotation; chỉ giữ alias có thể làm mất khả năng chọn đúng material đã bảo vệ bản ghi trước đó.

## 8. IAM, phân quyền và separation of duties

Storage policy phải kiểm soát **người/ứng dụng có thể điều khiển phép toán** chứ không chỉ tập trung khóa được đặt ở đâu.

| Principal minh họa | Quyền cần thiết | Quyền nên tránh |
|---|---|---|
| **Billing signing service** | Sign bằng key được cấp cho billing, đúng tenant/purpose | Export private key, DestroyKey, Sign bằng root key khác |
| **Customer data service** | GenerateDataKey/Decrypt wrapped DEK theo scope bản ghi | Unwrap toàn bộ tenant không liên quan, sửa IAM key policy |
| **Security key administrator** | Tạo, rotate, disable và review policy theo quy trình | Mặc định được giải mã mọi dữ liệu khách hàng |
| **Auditor** | Đọc audit metadata, key state, policy history | Đọc raw key, gọi Sign/Decrypt chỉ vì có quyền xem log |
| **Backup operator** | Chạy backup/restore được kiểm soát và phê duyệt | Raw key export ngoài ranh giới và tự xóa key |
| **Incident responder** | Emergency suspend/revoke theo scope được cấp | Tự động reactivate khóa đã bị xác nhận compromised |

### 8.1. Các nguyên tắc quan trọng

1. **Least privilege:** cấp đúng thao tác, key ID/version, tenant, environment và thời hạn cần thiết.
2. **Separation of duties:** người đổi key policy/alias không tự động có quyền dùng private key hoặc đọc plaintext; quyết định nhạy cảm có thể cần hai người phê duyệt.
3. **Workload identity:** tránh chia sẻ một master credential cho mọi microservice; cấp danh tính riêng có thể thu hồi.
4. **Purpose binding:** private signing key không được dùng cho RSA decryption chỉ vì thuật toán có cùng họ RSA.
5. **Business authorization:** KMS có thể cho Sign, nhưng Signing Service phải kiểm tra hóa đơn/tài liệu **đã được duyệt** trước khi ký; tránh signing oracle.
6. **Tenant isolation:** đối chiếu tenant từ danh tính và quyền truy cập bản ghi; không tin mỗi trường tenantId hoặc keyId do client tự cung cấp.
7. **Key state enforcement:** chặn dùng khóa Suspended/Disabled/Compromised theo policy ở điểm thực hiện mật mã.
8. **Break-glass:** quy trình cấp quyền khẩn cấp có TTL, approval, phạm vi giới hạn, ghi audit và rà soát hậu kiểm.

### 8.2. Encryption context và AAD không phải IAM

Một KMS có thể hỗ trợ **encryption context**; AES-GCM có **AAD**. Chúng có thể ràng buộc metadata như tenant, record ID hoặc key purpose để ngăn tráo ngữ cảnh. Nhưng một field tenantId do attacker tự gửi **không đủ để xác thực quyền truy cập**. Phải lấy tenant từ nguồn tin cậy và kiểm tra quyền bản ghi trước khi gọi Unwrap/Decrypt.

Một tài khoản được phép gọi **KMS Decrypt trên mọi khóa** có thể trở thành **confused deputy** nếu application dùng keyId từ request để giải mã hộ người dùng khác. Storage policy và IAM phải cùng ngăn đường này.

## 9. Kiểm toán chính sách lưu trữ khóa

Key inventory cho biết khóa tồn tại; **audit trail** cho biết các thao tác và thay đổi policy đã diễn ra. Cần phân biệt **administrative events** và **cryptographic-use events**.

### 9.1. Các sự kiện nên ghi

| Loại sự kiện | Metadata hữu ích |
|---|---|
| **Create/Import key** | actor, keyId/version, owner, purpose, provider, approval, time |
| **Grant/Revoke permission** | principal, policy revision, scope, reason, approver |
| **Encrypt/Decrypt/Wrap/Unwrap/Sign/MAC** | keyId/version, workload, operation, tenant, result, request ID |
| **Export/Backup/Restore** | approval, key class, destination/security domain, outcome |
| **Rotate/Alias switch** | old/new key reference, effective time, dependency plan |
| **Suspend/Disable/Destroy** | incident/ticket, actor, effective state, approval, evidence |
| **KMS/HSM provider change** | module/firmware/config version, key mapping, audit reference |

**Không log:** raw DEK/KEK/private key, PRK, root secret, plaintext của khách hàng, password, bearer token hoặc nội dung tài liệu nhạy cảm. Audit bản thân có thể tiết lộ tenant, key ID hoặc cấu trúc hệ thống nên cũng cần **phân quyền, retention, integrity và bảo vệ đường ghi**.

### 9.2. Bằng chứng kiểm thử policy

Một báo cáo tuân thủ nên trả lời:

- Có thể tạo một private signing key production **ngoài kho đã phê duyệt** không?
- Một workload được quyền Encrypt có vô tình được **Export** hoặc **DestroyKey** không?
- Khi đặt key ở **SUSPENDED**, lệnh Sign/Unwrap thực tế có bị chặn trên data plane không?
- Key ID/version trong inventory có tương ứng **resource thực** ở KMS/HSM và alias hiện hành không?
- Những DEK plaintext đã cấp cho ứng dụng tồn tại bao lâu và được cleanup/cache/invalidate ra sao?
- Bản sao lưu khóa có được mã hóa, hạn chế quyền và thử restore định kỳ trong môi trường tách biệt không?
- Khi hủy, có xác minh **backup, replica, key export và các nhánh derived keys** không?

**Tài liệu policy không đủ thay cho bằng chứng enforcement.** Reconciliation định kỳ giữa registry, provider inventory và audit giúp phát hiện policy drift, orphaned keys và key usage trái mục đích.

## 10. Java 17: Mô hình kiểm tra Key storage policy trước khi dùng khóa

Ví dụ sau không lưu hoặc xuất **bất kỳ raw key material** nào. Thay vào đó, nó mô hình hóa **metadata của khóa**, nơi lưu, trạng thái, purpose, tenant và quyền của caller. Một **policy gate** sẽ từ chối cấu hình yếu trước khi một ứng dụng gọi KMS/HSM.

**Chú ý:** đây là mô hình đào tạo, **không phải IAM thật hay data-plane enforcement**. Trong production, cùng quyết định phải được thực thi tại provider/crypto gateway và được audit; một boolean truyền vào hàm không thay thế bằng chứng danh tính hoặc quyền bản ghi.

~~~java
import java.util.Set;

public final class KeyStoragePolicyDemo {
    enum Kind {
        ROOT_KEK, PRIVATE_SIGNING, HMAC_KEY, DATA_KEY
    }

    enum Location {
        KMS, HSM, PROCESS_MEMORY, ENCRYPTED_KEYSTORE,
        PLAINTEXT_FILE, ENVIRONMENT_VARIABLE
    }

    enum State {
        ACTIVE, DECRYPT_ONLY, SUSPENDED, DESTROYED
    }

    enum Operation {
        ENCRYPT, DECRYPT, SIGN, WRAP, UNWRAP,
        GENERATE_MAC, VERIFY_MAC
    }

    record KeyDescriptor(
            String keyId, int version, String tenantId,
            Kind kind, Location location, boolean rawExportAllowed,
            State state, Set<Operation> allowedOperations,
            int localLifetimeSeconds) {
        KeyDescriptor {
            if (keyId == null || keyId.isBlank()
                    || tenantId == null || tenantId.isBlank()
                    || version < 1 || kind == null || location == null
                    || state == null || allowedOperations == null) {
                throw new IllegalArgumentException("Invalid metadata");
            }
            allowedOperations = Set.copyOf(allowedOperations);
        }
    }

    record Request(
            String authenticatedTenant, Operation operation,
            boolean identityVerified, boolean iamAllowed,
            boolean resourceAllowed) {}

    record Decision(boolean allowed, String reason) {}

    static Decision check(KeyDescriptor key, Request request) {
        if (!request.identityVerified() || !request.iamAllowed()
                || !request.resourceAllowed()
                || !key.tenantId().equals(request.authenticatedTenant())) {
            return new Decision(false, "IDENTITY_OR_SCOPE_DENIED");
        }

        if (key.state() == State.SUSPENDED
                || key.state() == State.DESTROYED) {
            return new Decision(false, "KEY_NOT_USABLE");
        }
        if (key.state() == State.DECRYPT_ONLY
                && request.operation() != Operation.DECRYPT
                && request.operation() != Operation.UNWRAP) {
            return new Decision(false, "DECRYPT_ONLY");
        }
        if (!key.allowedOperations().contains(request.operation())) {
            return new Decision(false, "OPERATION_NOT_ALLOWED");
        }

        // Ràng buộc loại khóa với mục đích mật mã.
        boolean kindSupportsOperation = switch (key.kind()) {
            case ROOT_KEK -> request.operation() == Operation.WRAP
                    || request.operation() == Operation.UNWRAP;
            case PRIVATE_SIGNING ->
                    request.operation() == Operation.SIGN;
            case HMAC_KEY ->
                    request.operation() == Operation.GENERATE_MAC
                    || request.operation() == Operation.VERIFY_MAC;
            case DATA_KEY -> request.operation() == Operation.ENCRYPT
                    || request.operation() == Operation.DECRYPT;
        };
        if (!kindSupportsOperation) {
            return new Decision(false, "KEY_PURPOSE_MISMATCH");
        }

        boolean managedBoundary =
                key.location() == Location.KMS
                || key.location() == Location.HSM;

        // Policy minh họa cho khóa dài hạn có độ nhạy cao.
        if (key.kind() == Kind.ROOT_KEK
                || key.kind() == Kind.PRIVATE_SIGNING
                || key.kind() == Kind.HMAC_KEY) {
            if (!managedBoundary || key.rawExportAllowed()) {
                return new Decision(false, "STORAGE_POLICY_VIOLATION");
            }
        }

        // DEK được phép nằm tạm trong memory hoặc ranh giới KMS/HSM.
        if (key.kind() == Kind.DATA_KEY) {
            if (key.location() == Location.PROCESS_MEMORY) {
                if (key.localLifetimeSeconds() <= 0
                        || key.localLifetimeSeconds() > 60) {
                    return new Decision(false, "DATA_KEY_TTL_VIOLATION");
                }
            } else if (!managedBoundary || key.rawExportAllowed()) {
                return new Decision(false, "DATA_KEY_STORAGE_DENIED");
            }
        }
        return new Decision(true, "ALLOW");
    }

    static void print(String label, Decision decision) {
        System.out.println(label + ": " + decision.allowed()
                + " / " + decision.reason());
    }

    public static void main(String[] args) {
        KeyDescriptor signing = new KeyDescriptor(
                "billing-sign-v3", 3, "tenant-42",
                Kind.PRIVATE_SIGNING, Location.HSM, false,
                State.ACTIVE, Set.of(Operation.SIGN), 0);

        Request allowedSign = new Request(
                "tenant-42", Operation.SIGN, true, true, true);
        print("HSM signing", check(signing, allowedSign));

        KeyDescriptor badStorage = new KeyDescriptor(
                "billing-sign-unsafe", 1, "tenant-42",
                Kind.PRIVATE_SIGNING, Location.PLAINTEXT_FILE, true,
                State.ACTIVE, Set.of(Operation.SIGN), 0);
        print("Plaintext private key", check(badStorage, allowedSign));

        Request otherTenant = new Request(
                "tenant-OTHER", Operation.SIGN, true, true, true);
        print("Cross tenant", check(signing, otherTenant));

        KeyDescriptor suspended = new KeyDescriptor(
                "billing-sign-v3", 3, "tenant-42",
                Kind.PRIVATE_SIGNING, Location.HSM, false,
                State.SUSPENDED, Set.of(Operation.SIGN), 0);
        print("Suspended key", check(suspended, allowedSign));

        KeyDescriptor oldDataKey = new KeyDescriptor(
                "customer-dek-17", 1, "tenant-42",
                Kind.DATA_KEY, Location.PROCESS_MEMORY, true,
                State.DECRYPT_ONLY,
                Set.of(Operation.ENCRYPT, Operation.DECRYPT), 30);
        print("Old DEK decrypt", check(oldDataKey, new Request(
                "tenant-42", Operation.DECRYPT, true, true, true)));
        print("Old DEK encrypt", check(oldDataKey, new Request(
                "tenant-42", Operation.ENCRYPT, true, true, true)));
    }
}
~~~

Lưu thành **KeyStoragePolicyDemo.java** và chạy với JDK 17+:

~~~bash
javac KeyStoragePolicyDemo.java
java KeyStoragePolicyDemo
~~~

Kết quả dự kiến:

~~~text
HSM signing: true / ALLOW
Plaintext private key: false / STORAGE_POLICY_VIOLATION
Cross tenant: false / IDENTITY_OR_SCOPE_DENIED
Suspended key: false / KEY_NOT_USABLE
Old DEK decrypt: true / ALLOW
Old DEK encrypt: false / DECRYPT_ONLY
~~~

### 10.1. Những gì demo chưa thể đảm bảo

1. **Không chứa key material:** không chứng minh HSM đã giữ private key non-exportable; chỉ kiểm tra metadata do chương trình tạo.
2. **Không có IAM thật:** thuộc tính identityVerified/iamAllowed/resourceAllowed được **giả lập**. Production phải lấy danh tính và quyền từ nguồn xác thực độc lập.
3. **Không có KMS API:** policy gate không ngăn một ứng dụng khác gọi thẳng KMS nếu key policy vẫn cho phép. Phải chặn ở enforcement point.
4. **Không có TTL thực thi:** localLifetimeSeconds là metadata; chưa có cache invalidation, timer hoặc giới hạn bộ nhớ.
5. **DECRYPT_ONLY là quy ước demo:** không phải mọi KMS đều có trạng thái đó. Suspended/Compromised có thể phải cấm mọi thao tác bí mật.
6. **Không đánh giá thuật toán/entropy:** các key ID chỉ là định danh; bên tạo khóa phải dùng key-generation provider và CSPRNG đúng chính sách.
7. **Không có concurrency/consistency:** inventory phải được version hóa; update policy và key state cần xử lý race giữa kiểm tra và phép toán.
8. **Không có backup, zeroization và audit:** các kiểm soát này cần được thực hiện ở tầng phù hợp.
9. **Không có exception workflow:** production muốn giữ một HMAC key trong secret vault được phê duyệt có thể cần rule khác; không được tự nới rule để pass test.
10. **Không chứng nhận storage security:** để đạt assurance cần đánh giá provider, kiến trúc, IAM, cách cấp key, data plane và restore.

## 11. Backup, khôi phục thảm họa và hủy khóa

**Một khóa được bảo vệ tuyệt đối nhưng không có phương án khôi phục phù hợp có thể khiến dữ liệu mất vĩnh viễn.** Ngược lại, một chính sách sao lưu khóa không kiểm soát có thể tạo nhiều đường lấy raw material, làm vô hiệu hóa mục tiêu non-exportable hoặc hủy khóa.

### 11.1. Bảo vệ khóa trong backup

Một kế hoạch backup/DR phải xác định:

1. **Vật liệu nào được backup?** Root/KEK, phiên bản của khóa, wrapped DEK, certificate, key metadata, audit và policy.
2. **Hình thức backup:** key material được wrap, secure HSM backup, replicated KMS key hoặc chỉ backup ciphertext/metadata tùy provider.
3. **Ai được khôi phục:** quyền BackupKey khác quyền RestoreKey, khác quyền Decrypt và DestroyKey.
4. **Đích lưu:** vùng/partition/account/quốc gia, mã hóa tại rest và transit, phân quyền độc lập, immutability nếu phù hợp.
5. **Mất mát có thể chấp nhận:** Recovery Point Objective/Recovery Time Objective và nguy cơ phụ thuộc một provider/region.
6. **Key version và mapping:** restore đúng identity/material cần thiết để decrypt bản mã lịch sử, không tạo nhầm key ID mới trỏ tới material khác.
7. **Kiểm tra restore:** có thể giải mã một bản ghi mẫu cũ/verify một chữ ký mẫu bằng quyền được phê duyệt không?
8. **Retention và destruction:** sau khi hủy khóa chính, những bản backup nào còn chứa material và được phép giữ bao lâu?

**Không giả định backup là có thể xuất raw KEK.** Một HSM có thể sao lưu trong **security domain được bảo vệ** và không cung cấp byte bản rõ cho ứng dụng; một cloud KMS có thể có replication/restore semantics khác. Storage policy phải tôn trọng hợp đồng provider và yêu cầu compliance.

### 11.2. Encryption key escrow và recovery

Một số tổ chức có yêu cầu **key escrow** hoặc quy trình khôi phục đặc biệt cho dữ liệu dài hạn. Đây là mục tiêu về **khả năng sẵn sàng/tuân thủ**, nhưng đồng thời tạo thêm bản sao bí mật hoặc thêm chủ thể có quyền khôi phục.

Nếu áp dụng, phải xác định **khi nào được dùng, ai phê duyệt, mấy người cần phối hợp, đường truy cập có TTL, dữ liệu nào được phục hồi, cách audit và cách hủy bản sao sau xử lý**. Không tự chia khóa thành các chuỗi con tùy tiện rồi coi đó là secret sharing an toàn; nếu cần chia sẻ khóa theo ngưỡng, dùng **giao thức/provider được kiểm chứng**.

### 11.3. Hủy khóa khác xóa metadata

~~~text
Xóa dòng key inventory   != hủy key material trong KMS/HSM
Disable key API          != hủy bản sao raw key đã xuất
Wipe local byte[]        != xóa mọi bản sao trong JVM/backup
Rotate KEK               != thay DEK đã lộ
Hủy một derived key      != crypto-erasure nếu root còn cho rederive
~~~

**Crypto-erasure** đòi hỏi loại bỏ khả năng khôi phục những key material thực sự cần để giải mã, xét cả **backup, cache, replicated KMS, escrow, snapshots và key hierarchy**. Trước khi hủy, cần dependency inventory cho ciphertext, wrapped DEK, chữ ký và pháp lý/lưu trữ. Hủy quá sớm có thể khiến dữ liệu không còn giải mã được; hủy quá muộn làm tăng exposure.

## 12. Vòng đời khóa và thay đổi chính sách lưu trữ

~~~mermaid
flowchart TD
    A["Generate/Import key qua nguồn được chấp thuận"] --> B["Classify: kind, purpose, owner, tenant"]
    B --> C["Chọn KMS/HSM/vault hoặc approved ephemeral location"]
    C --> D["Đăng ký keyId/version, export controls, IAM"]
    D --> E["Activate và dùng theo policy có audit"]
    E --> F["Giám sát TTL/cache, key use, backup và cryptoperiod"]
    F --> G["Rotate: tạo material/version mới"]
    G --> H["Chuyển Encrypt/Sign mới; xử lý dữ liệu cũ"]
    H --> I["Retire/Disable/Revoke nếu phù hợp"]
    I --> J["Xác minh phụ thuộc/retention/restore"]
    J --> K["Destroy và kiểm soát backup/copies"]
~~~

### 12.1. Key generation và provisioning

Khóa AES/HMAC hoặc private key phải được tạo bằng **CSPRNG/key generator được phê duyệt** hoặc bên trong KMS/HSM theo policy. Với cặp RSA/EC/Ed25519, không tự sinh seed từ timestamp/PID. **Key ID** chỉ nhận diện khóa, không làm key material mạnh lên.

Khi provisioning, đặt đúng **purpose, owner, tenant, key state, cryptoperiod, export attributes và grants**. Môi trường test và production nên có **key boundary và quyền khác nhau**; không dùng cùng một root KEK cho môi trường test để tiện chạy integration test.

### 12.2. Storage trong khi sử dụng

Giới hạn cached DEK, key handle, private key object và session secret. Cache có thể cải thiện hiệu năng nhưng làm tăng thời gian material có thể bị thu thập từ memory. Định nghĩa **TTL, max entries, principal scope, invalidation sau revoke/rotate và fail behavior**.

Một **HSM key non-exportable** có thể vẫn được dùng qua một session đang mở; một **local DEK** đã unwrap có thể tiếp tục Encrypt/Decrypt dù KEK ở KMS đã bị suspended. Phải hiểu thời điểm enforcement có hiệu lực trên các bản sao và phiên đã cấp.

### 12.3. Rotation

| Khóa | Chiến lược | Tác động |
|---|---|---|
| **KEK** | Tạo version mới, chuyển Wrap mới, rewrap DEK cũ nếu yêu cầu | Có thể không cần re-encrypt payload nếu cùng DEK và AAD không đổi |
| **DEK** | Tạo DEK mới, dùng cho ciphertext mới hoặc re-encrypt dữ liệu cũ | Phải cập nhật nonce, tag và metadata đúng bản mã |
| **Private signing key** | Ký mới bằng key mới, phát hành public key/certificate tin cậy | Public key cũ có thể vẫn cần Verify chữ ký lịch sử |
| **HMAC key** | Chuyển MAC mới sang key version mới, quản lý thời hạn chấp nhận tag cũ | Bên nhận cần chọn đúng key version và chống replay |
| **KDF root** | Tạo root mới, version hóa salt/info/KDF scheme | Derived keys cũ không tự chuyển sang root mới |

**Khi rotate một khóa đã lộ**, không nên chỉ cập nhật alias hoặc dùng cùng vật liệu khóa với ID mới. Kế hoạch phải xét phạm vi dữ liệu/chữ ký đã bị ảnh hưởng, revoked trust, session/token cache và loại migration cần thiết.

### 12.4. Suspension, compromise và destruction

**Suspended/Disabled** là trạng thái/quyền chặn API theo policy; material có thể vẫn tồn tại. **Compromised** là tình huống mất niềm tin vào bí mật hoặc quyền sử dụng; cần quy trình thay thế, không đơn thuần mở lại sau timeout. **Destroyed** nói về việc hủy material trong phạm vi được quản lý, nhưng vẫn cần xét bản sao ngoài ranh giới.

Đối với một private key nghi bị lộ, chặn Sign ở KMS không ngăn một đối thủ có bản sao tạo chữ ký offline. Cần phối hợp với **public-key trust, certificate revocation, JWKS, token/session revocation và thông báo đối tác** khi thích hợp.

## 13. Incident response: Khi chính sách lưu trữ bị vi phạm

### 13.1. Bốn tình huống cần phân biệt

| Sự cố | Tác động chính | Phản ứng ưu tiên |
|---|---|---|
| **Plaintext DEK xuất hiện trong log** | Có thể giải mã những ciphertext dùng DEK đó nếu attacker cũng có ciphertext | Cô lập log, thu hồi quyền, đánh giá thay DEK và re-encrypt |
| **KEK/root secret bị lộ** | Có thể ảnh hưởng nhiều wrapped/derived DEK | Disable/rotate root/KEK, khoanh vùng nhánh, đánh giá toàn bộ DEK và ciphertext |
| **Private signing key bị export trái phép** | Có thể tạo chữ ký giả ngoài KMS | Chặn Sign, rotate/revoke, kiểm tra tin cậy chữ ký/token và thông báo bên phụ thuộc |
| **Workload có quyền Unwrap quá rộng nhưng không lộ KEK** | Lạm dụng API và truy cập DEK trái phép | Thu hồi credential/grants, audit operation, giảm quyền và khoanh vùng dữ liệu |

**Sự cố lộ quyền sử dụng khóa vẫn nghiêm trọng dù không có raw key export.** Nếu một principal đã gọi Decrypt trái phép và thu được plaintext, chỉ rotate KEK sau đó không bảo đảm dữ liệu đã bị truy cập được giữ bí mật.

### 13.2. Quy trình xử lý

1. **Phát hiện và cô lập:** khóa quyền độc hại, tạm dừng thao tác nhạy cảm tại enforcement point, kiểm soát access tới logs/snapshots.
2. **Định danh:** lấy key ID/version, material type, owner, tenant, provider, exportability, bản sao và time window.
3. **Đánh giá tác động:** plaintext DEK/KEK/private key có bị sao chép không, những người/ứng dụng nào có quyền và dữ liệu nào bị ảnh hưởng?
4. **Chọn hành động:** revoke credential, disable key, rotate, rewrap, re-encrypt, revoke certificate/JWKS/token hoặc đóng phiên.
5. **Khôi phục an toàn:** provision key mới qua nguồn entropy được chấp thuận, kiểm tra quyền và backup, thử restore/migration theo runbook.
6. **Audit và hậu kiểm:** bảo toàn chứng cứ, cập nhật controls/detection; **không** đưa raw secret vào ticket hoặc bản tường trình.

### 13.3. Không dùng đường khôi phục làm lỗ hổng mới

Một quy trình emergency cho phép mọi người xuất KEK bản rõ để khôi phục có thể tạo rủi ro lớn hơn sự cố ban đầu. Quyền khẩn cấp cần **tạm thời, scope hẹp, được phê duyệt, dùng đúng API/provider, có giám sát và bị thu hồi sau xử lý**. Không để đường break-glass tự động được dùng làm fallback khi KMS timeout.

## 14. Threat model: Lỗi thiết kế storage policy phổ biến

| Lỗi | Hậu quả | Biện pháp |
|---|---|---|
| Private key trong Git hoặc container image | Lộ qua commit/build cache và mọi bản sao triển khai | KMS/HSM, không commit key material, rotate nếu lộ |
| DEK bản rõ lưu cạnh ciphertext | Mất ranh giới bí mật khi database bị đọc | Envelope encryption, wrapped DEK, KEK tách quyền |
| KEK non-exportable nhưng Unwrap grants quá rộng | Mọi principal được cấp quyền có thể lấy nhiều DEK | IAM theo tenant/purpose/context, audit và quota |
| Keystore password nằm cùng file với cùng quyền | Host compromise mở cả keystore và password | Secret injection/isolated store, tối thiểu quyền |
| Log Base64(privateKey) để debug | Credential dài hạn bị nhân bản vào telemetry | Không log secret; secret scanning và incident response |
| HMAC key dùng chung test và production | Mất phân tách miền tin cậy | Environment-specific key hierarchy |
| Một signing key dùng đồng thời Decrypt và Sign | Vi phạm key purpose và mở rộng bề mặt tấn công | Separate key purpose, algorithm allowlist |
| Không version hóa key ID khi rotate | Mất khả năng resolve khóa lịch sử | Immutable key/version reference, registry và dependency |
| Không kiểm soát AES-GCM nonce theo DEK | Nonce reuse phá tính bảo mật dù key lưu an toàn | Nonce uniqueness toàn phạm vi, invocation limits |
| Cho request tự chọn tenant/key ID để Unwrap | Cross-tenant access, confused deputy | Authenticate/authorize record, key policy, encryption context |
| Root KDF bị lộ nhưng chỉ đổi HKDF info | Đối thủ vẫn có thể derive các key con | Root mới, re-encrypt/rotate nhánh ảnh hưởng |
| Backup chứa raw key ở nơi không bảo vệ | Có đường lấy key ngoài KMS/HSM | Backup domain bảo vệ, quyền độc lập, retention |
| Xóa key inventory thay vì key material | Khóa vẫn còn trong HSM hoặc backup | Destruction API và xác minh bản sao |
| Hủy KEK khi vẫn còn wrapped DEK cũ | Mất khả năng giải mã dữ liệu | Dependency inventory, restore test, migration |
| Chỉ kiểm tra policy ở UI | Service khác gọi thẳng KMS vẫn thực hiện thao tác | Enforcement tại crypto gateway/KMS/HSM |
| Thu hồi KMS permission nhưng quên DEK cache | Workload vẫn có thể decrypt offline | Cache invalidation, dừng workload/phiên và TTL |
| Audit ghi key ID nhưng không có key version | Không biết material thực dùng lúc sự cố | Log resolved keyId/version và provider scope |

## 15. Case study: Chính sách lưu trữ khóa cho nền tảng giao dịch

Một nền tảng có **Billing Service**, **Customer Data Service**, **Auth Service** và **KMS/HSM**. Billing ký hóa đơn bằng Ed25519, Customer Data mã hóa hồ sơ bằng AES-GCM, Auth phát JWT ký số và một tích hợp webhook dùng HMAC.

### 15.1. Thiết kế ban đầu có vấn đề

- Billing lưu private key PEM trong container image để tránh độ trễ gọi Sign qua HSM.
- Customer Data lưu plaintext DEK và ciphertext trong cùng database.
- Auth dùng chung một signing key cho staging và production.
- HMAC key được đặt trong config file và truyền qua nhiều nhóm vận hành.
- Không có mapping key ID/version, nên mỗi lần rotate có nguy cơ làm lỗi Verify hoặc Decrypt lịch sử.

### 15.2. Áp dụng storage policy theo từng lớp

1. **Inventory:** tạo logical key family cho từng purpose, owner, environment và tenant; ghi key ID/version/algorithm/state/policy reference.
2. **Billing signing key:** tạo private signing key non-exportable trong KMS/HSM được chấp thuận; Billing chỉ có quyền Sign cho tài liệu được duyệt, không Export/Destroy.
3. **Public-key trust:** công bố public key/certificate từ nguồn tin cậy, dùng version/kid đúng issuer; giữ khả năng Verify tài liệu lịch sử theo policy.
4. **Customer data:** chuyển sang per-object/random DEK được wrap bởi tenant KEK, lưu wrapped DEK, nonce và ciphertext/tag trong envelope; không lưu raw DEK.
5. **IAM:** Customer Data chỉ Unwrap đúng tenant/resource và kiểm tra bản ghi trước khi gọi KMS; một service role toàn cục không tự được Decrypt mọi tenant.
6. **AES-GCM:** nonce unique per DEK, AAD ràng buộc record/tenant/context theo schema nhất quán, có version và migration strategy.
7. **Auth:** tách signing key giữa môi trường, theo dõi JWKS cache và TTL; rotation không làm mất public key cần Verify token chưa hết hạn trừ khi có sự cố.
8. **Webhook HMAC:** secret được cấp qua service có policy/rotation; không để trong Git, log hay config image, không dùng làm private signing key bất đối xứng.
9. **Backup:** kiểm tra KMS/HSM provider backup domain, inventory dependency và restore test; không mở raw key export đại trà để dự phòng.
10. **Audit:** ghi Sign/Decrypt/Unwrap, principal, tenant, key version, policy outcome, ticket rotation; không ghi material hoặc dữ liệu khách hàng.
11. **Incident response:** nếu private key/DEK/KEK lộ, đánh giá phạm vi và thay material tương ứng, không chỉ đổi alias hoặc rewrap nguyên DEK đã lộ.

### 15.3. Chỉ số vận hành để chứng minh chính sách có hiệu lực

Có thể theo dõi:

- **Tỷ lệ critical private keys** được quản lý trong ranh giới KMS/HSM đã phê duyệt và đáp ứng export policy.
- **Số principal có quyền Export/Decrypt/Sign rộng** ngoài policy được phê duyệt.
- **Số khóa không có owner, purpose, version hoặc inventory record**.
- **Số key version đã đến hạn rotate** và phụ thuộc ciphertext/chữ ký còn mở.
- **Số lần deny do policy**, thay đổi policy không có approval và các lần break-glass.
- **Tình trạng backup restore tests**, việc phát hiện keystore/password cùng chỗ và orphaned key material.

Các số liệu này giúp kiểm tra thực chất; một dashboard báo “100% encrypted at rest” không có nghĩa toàn bộ private key đã được bảo vệ trước lạm dụng API hoặc bản sao không kiểm soát.

## 16. Checklist kiểm tra Key storage policy trước production

1. **Classification:** đã phân biệt root/KEK, DEK, private/public key, HMAC secret, IKM/PRK/OKM và metadata?
2. **Storage boundary:** mỗi key class có approved provider/location, non-exportability/backup capability được xác minh?
3. **No plaintext persistence:** có bảo đảm không lưu raw KEK/DEK/private key trong DB, Git, image, log, CI artifact hoặc snapshot trái policy?
4. **Trust và identity:** public key/JWKS/certificate được xác thực nguồn và có key ID/version theo issuer?
5. **Key usage:** purpose, algorithm, state, owner và tenant được kiểm tra trước Sign/Decrypt/Unwrap?
6. **IAM:** workload có danh tính riêng, least privilege theo key và operation, không có quyền Export/Destroy không cần thiết?
7. **Encryption context/AAD:** có ràng buộc đúng tenant/record/version và không thay authorization bằng metadata do caller tự gửi?
8. **Envelope:** DEK và KEK tách bạch, wrapped DEK lưu đúng, key version lịch sử được resolve chính xác?
9. **Nonce/cryptography:** AES-GCM dùng nonce không trùng theo DEK; Sign/Verify, HMAC/KDF dùng đúng algorithm và key purpose?
10. **Memory:** plaintext DEK/session secret sống tối thiểu, có cache policy, xử lý dump và cleanup best effort?
11. **Backup/recovery:** backup được bảo vệ, có approval, retention, DR/restore tests và không lộ material qua đường khôi phục?
12. **Rotation:** có phân biệt rewrap KEK, re-encrypt DEK, signing-key rotation và root-KDF rotation?
13. **Revocation/destruction:** có xử lý các bản sao đã xuất, backup, derived key, cached DEK và dữ liệu lịch sử trước khi hủy?
14. **Audit:** ghi actor, key ID/version, operation, outcome, policy revision và reason mà không ghi secret?
15. **Enforcement:** policy có được chặn tại KMS/HSM/crypto gateway, được test cả các đường gọi trực tiếp?
16. **Exceptions:** mọi ngoại lệ có owner, lý do, approval, TTL, phạm vi và phương án thay thế về đúng policy?
17. **Reconciliation:** đối soát key inventory với provider/alias/IAM để phát hiện orphaned keys và policy drift?
18. **Incident response:** có runbook riêng cho lộ DEK, KEK, private signing key, HMAC secret và lạm dụng API?

### Câu hỏi tự kiểm tra

**Câu 1.** Database đã bật disk encryption, nên có thể lưu DEK bản rõ cùng ciphertext được không?

**Trả lời:** **Không nên.** Disk encryption không tạo ra ranh giới độc lập khi attacker có quyền đọc database đang chạy. Nên dùng envelope encryption hoặc cơ chế bảo vệ key material phù hợp.

**Câu 2.** Private key trong HSM non-exportable có đồng nghĩa workload không thể bị lạm dụng để ký tài liệu giả?

**Trả lời:** **Không.** Workload có quyền Sign có thể trở thành signing oracle. Cần IAM, purpose, kiểm tra nghiệp vụ, hạn mức và audit.

**Câu 3.** Wrapped DEK có thể lưu cùng ciphertext không?

**Trả lời:** **Có thể**, đây là pattern của envelope encryption khi KEK được bảo vệ tách biệt, Unwrap được phân quyền và envelope metadata được xử lý đúng.

**Câu 4.** Rotate KEK có bắt buộc re-encrypt toàn bộ plaintext không?

**Trả lời:** **Không nhất thiết.** Có thể rewrap DEK dưới KEK mới trong một thiết kế tương thích AAD. Nếu DEK đã lộ hoặc đổi DEK, phải xem xét re-encrypt.

**Câu 5.** Khóa bị disable trong KMS có làm plaintext DEK đã cấp cho JVM biến mất không?

**Trả lời:** **Không.** Cached/plaintext DEK đã xuất có thể tiếp tục được dùng; cần TTL, invalidation, workload/session control và chính sách dữ liệu.

**Câu 6.** Một file PKCS#12 được đặt mật khẩu và password nằm ngay cùng thư mục với file. Có tự đáp ứng storage policy cho critical private key không?

**Trả lời:** **Không.** Phải xét người có quyền đọc cả file và password, runtime exposure, backup và assurance; với yêu cầu cao nên cân nhắc KMS/HSM non-exportable.

**Câu 7.** Nếu root HKDF vẫn còn, xóa một derived DEK khỏi JVM đã bảo đảm crypto-erasure chưa?

**Trả lời:** **Chưa.** Root, salt/info và version còn có thể dẫn xuất lại cùng khóa. Hủy dữ liệu cần đánh giá toàn bộ đường phục hồi key material.

**Câu 8.** Public verification key có cần giữ bí mật như private signing key không?

**Trả lời:** **Không.** Public key có thể công bố, nhưng phải bảo vệ **nguồn tin cậy, tính toàn vẹn, liên kết issuer và key version**.

**Câu 9.** Nếu chỉ đổi key alias trong KMS, dữ liệu cũ đã được rotate chưa?

**Trả lời:** **Không.** Dữ liệu cũ vẫn phụ thuộc DEK/KEK đã dùng lúc mã hóa, trừ khi có rewrap hoặc re-encrypt thực sự.

**Câu 10.** Khi backup khóa đã có, có thể xóa key material chính ngay mà không thử restore không?

**Trả lời:** **Không.** Phải kiểm tra restore, quyền/định danh khóa, phụ thuộc ciphertext/chữ ký và retention. Hủy khóa quá sớm có thể gây mất dữ liệu vĩnh viễn.

**Câu 11.** Key policy trong YAML ghi DENY_EXPORT. Đã đủ để bảo đảm không thể export khóa chưa?

**Trả lời:** **Chưa.** Cần enforcement ở provider/key attributes/IAM, cùng kiểm thử từ chối và audit các đường truy cập thực tế.

**Câu 12.** Một key storage policy an toàn có thể chỉ tập trung vào confidentiality của key bytes không?

**Trả lời:** **Không.** Cần bảo vệ cả **quyền dùng khóa, tính toàn vẹn metadata, backup/recovery, vòng đời, trạng thái, audit và khả năng ứng phó**.

**Điểm cốt lõi:** **Key storage policy** là một hợp đồng kiểm soát đầy đủ vòng đời **key material và quyền sử dụng nó**, không chỉ là quy định “mã hóa khóa khi lưu trên đĩa”. Một thiết kế an toàn cần phân loại khóa, ưu tiên **KMS/HSM với export controls phù hợp**, dùng **envelope encryption** cho DEK, giới hạn raw key trong memory, áp dụng **least-privilege IAM và policy ở enforcement point**, quản lý **key ID/version, backup, rotation, thu hồi, hủy và audit**. Chính sách chỉ đáng tin khi **được kiểm thử, đối soát và có bằng chứng vận hành**.
