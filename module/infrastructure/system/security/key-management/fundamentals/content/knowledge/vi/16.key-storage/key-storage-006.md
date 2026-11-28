# KMS – Key Management Service và cách lưu trữ, sử dụng khóa mật mã an toàn

**KMS (Key Management Service)** là dịch vụ quản lý khóa mật mã cung cấp một hoặc nhiều chức năng như **tạo khóa, lưu giữ và bảo vệ vật liệu khóa, áp chính sách quyền, thực hiện phép toán mật mã, quản lý trạng thái/vòng đời khóa và ghi nhật ký kiểm toán**. Thay vì mỗi ứng dụng tự chép một khóa AES hoặc private key vào source code, cấu hình hay database, ứng dụng có thể tham chiếu tới một **key object trong KMS** và thực hiện thao tác được cho phép thông qua API có xác thực.

Trong chương **Key storage** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, KMS là thành phần quan trọng để liên kết khóa đối xứng, bất đối xứng, chữ ký số, HSM, envelope encryption, kiểm soát truy cập và kiểm toán. Một thiết kế KMS tốt phải hỗ trợ toàn bộ vòng đời **tạo → cấp phát/đăng ký → lưu trữ → sử dụng → xoay vòng → vô hiệu hóa/thu hồi → hủy**, đồng thời giúp giảm hậu quả khi mất quyền truy cập hoặc một workload bị xâm nhập.

> **Phân biệt cốt lõi:** **KMS không phải thuật toán mã hóa, cũng không tự bảo đảm ứng dụng an toàn.** KMS có thể bảo vệ KEK hoặc private key, nhưng ứng dụng vẫn phải kiểm tra quyền truy cập dữ liệu, dùng đúng thuật toán/nonce/AAD, không ghi secret vào log và xử lý khóa bị lộ. Khả năng quản lý key material, non-exportable, HSM-backed, rotate và backup **tùy nhà cung cấp, loại khóa và cấu hình**.

## 1. Bài toán KMS giải quyết

Giả sử Billing Service cần mã hóa hàng triệu hóa đơn. Nếu ứng dụng dùng một khóa AES cố định trong JAR:

- Mỗi bản triển khai đều giữ cùng một **bí mật dài hạn**.
- Người có bản build hoặc quyền đọc cấu hình có thể tìm cách lấy khóa.
- Khó phân biệt khóa production, staging và khóa của từng tenant.
- Khi khóa bị lộ, phải thay secret trên mọi instance và xác định hàng triệu bản mã bị ảnh hưởng.
- Không có điểm quản trị trung tâm để giới hạn người có quyền dùng khóa và xem lịch sử hoạt động.
- Việc sao lưu và khôi phục dễ tạo **bản sao khóa không kiểm soát**.

KMS giúp chuyển trọng tâm từ **“ứng dụng sở hữu mọi key bytes”** sang **“ứng dụng được phép yêu cầu các phép toán hoặc vật liệu khóa theo chính sách”**.

Ví dụ, Billing Service chỉ được gọi API KMS để **tạo DEK và giải bọc DEK của dữ liệu Billing**; Payment Service chỉ được yêu cầu **ký số bằng một signing key đã phê duyệt**; dịch vụ xác minh chữ ký không nhất thiết có quyền ký.

### 1.1. Những mục tiêu chính

| Mục tiêu | KMS có thể hỗ trợ | Điều ứng dụng vẫn phải làm |
| --- | --- | --- |
| **Bảo vệ khóa** | Giữ KEK/private key trong miền quản lý, áp giới hạn xuất khóa. | Không hard-code secret, hạn chế DEK rõ trong RAM, tránh rò log. |
| **Kiểm soát truy cập** | Xác thực principal, IAM/key policy, quyền theo operation/key. | Kiểm tra quyền người dùng đối với tenant/object/nghiệp vụ. |
| **Mã hóa dữ liệu** | Encrypt/Decrypt hoặc GenerateDataKey tùy API. | Dùng AEAD, nonce và AAD đúng; lưu ciphertext và metadata. |
| **Ký số** | Sign bằng private key được bảo vệ khi sản phẩm hỗ trợ. | Kiểm tra nội dung được ký, quyền phát hành, trust tại verifier. |
| **Xoay vòng khóa** | Tạo material/version mới, cập nhật trạng thái hoặc alias. | Xử lý ciphertext cũ, rewrap/re-encrypt, chuyển consumer. |
| **Kiểm toán** | Log actor, key ID, operation và kết quả khi được cấu hình. | Không log plaintext/DEK, đối chiếu sự kiện nghiệp vụ. |
| **Khả năng phục hồi** | HA, backup/restore hoặc multi-region theo khả năng. | Thiết kế RPO/RTO, inventory dependency và restore drill. |

**Biết key ID không đồng nghĩa có quyền sử dụng khóa.** Tuy nhiên, nếu một workload được cấp quyền `Decrypt` quá rộng, KMS sẽ thực hiện thao tác đã được cho phép dù caller của ứng dụng không đáng được truy cập dữ liệu đó. Vì thế cần hai lớp **KMS IAM** và **application authorization**.

## 2. KMS chứa những thành phần nào?

Một KMS thực tế có thể gồm:

1. **Key objects:** tài nguyên đại diện cho khóa, thuật toán, usage, owner, version và lifecycle state.
2. **Key material custody:** nơi sinh và bảo vệ vật liệu mật mã, có thể dựa vào HSM hoặc giải pháp khác tùy sản phẩm.
3. **Cryptographic operations:** các API Encrypt/Decrypt, Wrap/Unwrap, Sign/Verify, GenerateDataKey hoặc GenerateRandom trong phạm vi được hỗ trợ.
4. **Access policy:** ai được gọi thao tác nào, trên khóa nào và dưới điều kiện nào.
5. **Lifecycle controls:** activate, disable, rotate, retire, schedule deletion và quản trị imported key material.
6. **Audit/monitoring:** nhật ký thao tác và thay đổi chính sách, cảnh báo bất thường.
7. **Availability/recovery controls:** phương án phục hồi, phân vùng quyền, vùng triển khai và bản sao theo khả năng nhà cung cấp.

~~~mermaid
flowchart TD
    APP["Billing / Payment / API Service"] --> IDENT["Workload identity"]
    IDENT --> POLICY["IAM, key policy, key usage và điều kiện"]
    POLICY --> API["KMS cryptographic API"]
    API --> CUSTODY["Bảo vệ key material - HSM hoặc cơ chế provider"]
    CUSTODY --> KEY["KEK / Signing key / Root key"]
    API --> DEK["Data key hoặc kết quả mật mã"]
    API --> AUDIT["Audit log và giám sát"]
    GOV["Security / Key owner"] --> META["Key registry, version và lifecycle"]
    META --> API
    GOV --> POLICY
    DEK --> APP
~~~

Đây là **sơ đồ chức năng**, không phải cam kết rằng mọi KMS cung cấp toàn bộ API trong cùng một sản phẩm. **KMS quản lý khóa** còn **HSM** là một loại thành phần có thể bảo vệ và thực thi phép toán mật mã trong ranh giới phần cứng.

### 2.1. KMS khác HSM ở đâu?

| Khía cạnh | KMS | HSM |
| --- | --- | --- |
| **Bản chất** | Dịch vụ/lớp quản trị khóa và API. | Thiết bị hoặc dịch vụ phần cứng bảo vệ khóa và xử lý mật mã theo thiết kế. |
| **Trọng tâm** | Định danh khóa, IAM, lifecycle, rotation, audit, tích hợp ứng dụng. | Ranh giới bảo vệ vật liệu khóa, hạn chế trích xuất, chống can thiệp theo khả năng. |
| **Triển khai** | Managed cloud, on-prem, hybrid; có thể tích hợp HSM. | Thiết bị riêng, cụm HSM hoặc HSM-as-a-service. |
| **Quyền dùng khóa** | Chính sách API/role và điều kiện truy cập. | Quyền slot/partition/session/operator, cơ chế quorum theo sản phẩm. |
| **Khả năng xuất khóa** | Phụ thuộc loại khóa, origin, API và policy. | Phụ thuộc cấu hình và loại key; không mặc định mọi key đều non-exportable. |
| **Phục hồi** | Có thể hỗ trợ dịch vụ đa vùng, backup và recovery. | Có thể cần secure backup, token, recovery domain hoặc quorum. |

**“HSM-backed” không tự có nghĩa tất cả phép toán đều chạy trong HSM, mọi key đều non-exportable hoặc toàn bộ dịch vụ đạt cùng cấp chứng nhận.** Khi có yêu cầu tuân thủ, phải kiểm tra **phạm vi chứng nhận, cấu hình và loại key/operation cụ thể**, không chỉ tên sản phẩm.

### 2.2. KMS không phải secret manager

**Secret manager** thường lưu và cấp phát secret dạng dữ liệu (API tokens, mật khẩu, chuỗi kết nối, certificate bundles). **KMS** tập trung vào **vật liệu khóa mật mã và các phép toán/chính sách quản lý khóa**. Một giải pháp có thể dùng KMS để mã hóa secret lưu trong secret manager, nhưng chúng không nên bị đánh đồng.

Ví dụ: cần lưu một **mật khẩu database**, dùng secret manager với chính sách đọc/rotate phù hợp. Cần dùng **private key ký release không xuất khỏi miền bảo vệ**, chọn KMS/HSM hỗ trợ Sign theo policy. Cần mã hóa hàng triệu bản ghi, thường dùng **envelope encryption** thay vì gửi từng payload lớn vào API KMS.

## 3. Các loại khóa và API KMS thường gặp

| Loại khóa | Công dụng | API/khả năng minh họa |
| --- | --- | --- |
| **Symmetric KEK** | Bảo vệ DEK, hoặc mã hóa dữ liệu nhỏ theo API. | GenerateKey, Encrypt, Decrypt, Wrap/Unwrap, Rotate. |
| **DEK** | Mã hóa dữ liệu bằng AES-GCM trong ứng dụng. | GenerateDataKey trả DEK tạm thời và wrapped DEK nếu API hỗ trợ. |
| **Asymmetric signing key** | Ký số Ed25519/ECDSA/RSA-PSS. | Sign, GetPublicKey hoặc Verify theo sản phẩm. |
| **Asymmetric encryption key** | Bảo vệ secret/key transport theo cơ chế được cho phép. | Encrypt/Decrypt như RSA-OAEP khi hỗ trợ. |
| **MAC key** | Tạo/xác minh HMAC theo key usage. | GenerateMac/VerifyMac hoặc API tương đương nếu provider hỗ trợ. |
| **Imported/BYOK key** | Tổ chức mang vật liệu khóa đã tạo từ bên ngoài. | ImportKeyMaterial/WrapForImport theo quy trình được hỗ trợ. |
| **Root/master/recovery key** | Bảo vệ cấp cao hoặc phục hồi hệ thống. | Thường có cơ chế và quyền đặc biệt; không mặc định ứng dụng được dùng trực tiếp. |

Không suy rằng **cùng một key object hỗ trợ mọi thao tác**. Một khóa Ed25519 dùng để ký **không phải khóa X25519 để thỏa thuận khóa**; một khóa AES dùng WRAP không tự phù hợp để ký JWT; một khóa được phép Encrypt không tự được phép Decrypt.

### 3.1. Key generation khác key usage

**GenerateKey** thường tạo vật liệu khóa và một đối tượng có identity/metadata. **GenerateDataKey** trong mô hình envelope encryption có thể tạo một **DEK ngẫu nhiên mới** để ứng dụng sử dụng, đồng thời cung cấp bản mã của DEK đã được bảo vệ bởi KEK.

Kết quả KMS phải được kiểm tra theo hợp đồng API: key ID, thuật toán, trạng thái, độ dài key, encryption context và quyền. **Không hard-code DEK** hoặc tự tạo bằng `Random` không dành cho mật mã rồi nhờ KMS bọc.

**CSPRNG/KMS/HSM entropy** là nền tảng sinh khóa. Tuy nhiên việc sinh khóa đúng vẫn cần **cấp phát, lưu trữ, sử dụng và rotate** đúng ranh giới.

## 4. Envelope encryption – Cách dùng KMS phổ biến với dữ liệu lớn

**Envelope encryption** tách khóa dữ liệu **DEK (Data Encryption Key)** và khóa bọc **KEK (Key Encryption Key)**:

- **DEK:** khóa AES-GCM dùng để mã hóa dữ liệu nghiệp vụ; có thể tồn tại rõ trong RAM ứng dụng trong thời gian ngắn theo thiết kế.
- **KEK:** khóa do KMS quản lý để bảo vệ DEK; lý tưởng là ứng dụng **không nhận KEK dạng rõ**.
- **Wrapped DEK:** bản mã hoặc dạng khóa đã được bọc, lưu cùng dữ liệu được mã hóa.
- **Metadata:** key reference, version/format, nonce/tag và encryption context cần cho giải mã.

~~~mermaid
sequenceDiagram
    participant A as Billing Service
    participant K as KMS
    participant D as Database
    A->>K: GenerateDataKey(KEK ref, encryption context)
    K-->>A: DEK rõ tạm thời + wrapped DEK
    Note over A: Sinh nonce, AES-GCM mã hóa với AAD
    A->>D: Ciphertext + nonce/tag + wrapped DEK + metadata
    Note over A: Hạn chế tồn tại DEK rõ trong RAM
    A->>D: Đọc bản ghi được phép
    D-->>A: Ciphertext và metadata
    A->>K: DecryptDataKey(wrapped DEK, context)
    K-->>A: DEK rõ tạm thời sau khi policy cho phép
    Note over A: AES-GCM kiểm tra tag, rồi mới dùng plaintext
~~~

**Vì sao cách này hữu ích?** Ứng dụng có thể mã hóa dữ liệu bằng AEAD hiệu quả tại nơi xử lý, trong khi KMS chỉ cần bảo vệ các DEK. Chi phí, kích thước payload và giới hạn API KMS không còn bị nhân lên theo từng byte của dữ liệu lớn.

**Đổi lại**, DEK rõ vẫn có thể hiện diện trong bộ nhớ của ứng dụng. Nếu attacker chiếm quyền workload đúng thời điểm, họ có thể đọc DEK hoặc plaintext dù KEK non-exportable. KMS **giảm bề mặt giữ KEK**, không loại bỏ mọi rủi ro endpoint.

### 4.1. AAD và encryption context là gì?

**Additional Authenticated Data (AAD)** của AES-GCM là dữ liệu **được xác thực nhưng không mã hóa** cùng bản mã. Ví dụ AAD có thể gắn **tenantId, invoiceId, purpose và schemaVersion** với ciphertext.

**Encryption context** trong một số KMS là map hoặc dữ liệu ngữ cảnh được provider liên kết mật mã với thao tác bọc/giải bọc. Giá trị và semantics **phụ thuộc sản phẩm**, thường không được coi là bí mật và có thể xuất hiện trong audit.

Hai lớp nên **phối hợp**, nhưng không mặc định chúng là cùng một API:

| Lớp | Ví dụ ràng buộc | Tác dụng |
| --- | --- | --- |
| **Application authorization** | User X chỉ được đọc invoice-123 của tenant A. | Quyết định **ai được phép truy cập dữ liệu** trước khi gọi KMS. |
| **KMS context/policy** | purpose=billing-invoice, tenant=A, object=invoice-123. | Giới hạn hoặc ràng buộc thao tác với DEK/KEK theo khả năng provider. |
| **AEAD AAD** | schema, tenant, object, purpose, key reference. | Phát hiện thay đổi metadata ảnh hưởng ý nghĩa ciphertext. |
| **Database ACL** | Câu truy vấn chỉ trả bản ghi của tenant A. | Chặn truy cập dữ liệu ngoài phạm vi ở lớp lưu trữ. |

**KMS Decrypt thành công không chứng minh request hợp lệ ở lớp nghiệp vụ.** Nếu ứng dụng lấy `tenantId` từ một body chưa xác thực và tự đưa vào encryption context, một IAM policy rộng vẫn có thể cho phép thao tác trên tenant không được phép.

### 4.2. Phải lưu những gì với ciphertext?

~~~yaml
envelopeFormat: "billing-envelope-v1"
dataAlgorithm: "AES-256-GCM"
tenantRef: "tenant-A"
objectRef: "invoice-123"
keyRef: "kms://prod/billing/invoice-kek"
keyVersionRef: "provider-or-application-version-if-available"
nonce: "<base64-96-bit-nonce>"
ciphertextWithTag: "<base64-ciphertext-and-tag>"
wrappedDek: "<base64-kms-encrypted-data-key>"
~~~

Đây là **schema minh họa**, không phải dữ liệu thật hoặc định dạng KMS chuẩn. Cần bảo vệ tính toàn vẹn của các trường quan trọng, xác định encoding, key version và cách diễn giải AAD. Một số KMS có thể tự chứa key reference/version trong wrapped key blob và không công khai material version; ứng dụng phải tuân theo **hợp đồng của nhà cung cấp**.

**Không lưu plaintext DEK trong cùng bản ghi**. Khi phải khôi phục dữ liệu cũ, cần giữ đủ **wrapped DEK, KEK recovery path, nonce/tag, context và metadata**, không chỉ ciphertext.

## 5. Lưu trữ khóa trong KMS: key material, metadata và custody

Một hệ thống KMS thường phân biệt:

1. **Key identity:** ID, name, ARN/resource URI và alias.
2. **Key material:** bytes bí mật được bảo vệ hoặc logic sử dụng khóa, tùy loại.
3. **Key metadata:** thuật toán, usage, origin, version, status, owner, tags và timestamps.
4. **Policy:** principal nào được gọi API, quyền tạo/chỉnh/xóa.
5. **Audit:** lịch sử thao tác, thay đổi cấu hình, phê duyệt và nguồn gọi.

**Không dùng alias hiện tại như một phiên bản vật liệu khóa bất biến.** Alias `billing-current` có thể đổi từ khóa cũ sang khóa mới. Để giải mã bản mã lịch sử, phải có **key reference/version** hoặc dựa trên cơ chế giải mã lịch sử mà provider thực sự bảo đảm.

### 5.1. Non-exportable có nghĩa gì?

Một khóa **non-exportable** là khóa mà cơ chế quản lý **không cho xuất vật liệu dạng rõ qua những đường API được quy định**. Ý nghĩa chính xác phụ thuộc sản phẩm và chính sách.

- **Không cho ứng dụng lấy bytes KEK/private key** qua API thông thường.
- **Không ngăn ứng dụng được cấp quyền gọi Sign/Decrypt/Unwrap** trên khóa đó.
- **Không đồng nghĩa không có bản backup nội bộ**: provider/HSM có thể có cơ chế sao lưu phục hồi an toàn mà không xuất raw key ra ứng dụng.
- **Không tự có forward secrecy** hoặc khả năng hủy mọi bản sao lập tức.
- **Không tự ngăn attacker dùng credential hợp lệ**: IAM, condition, network policy, workflow approval và audit vẫn rất quan trọng.

**Đừng nhầm non-exportable với khả năng khôi phục tuyệt đối.** Có sản phẩm không thể phục hồi một key object sau khi qua giai đoạn xóa; cũng có loại imported material cần người dùng giữ nguồn riêng. Phải kiểm chứng cụ thể trước khi chọn phương án DR.

### 5.2. BYOK và import key material

**Bring Your Own Key (BYOK)** cho phép tổ chức tạo/giữ vật liệu khóa theo một quy trình được phép rồi nhập vào môi trường quản lý phù hợp. Một số nhà cung cấp hỗ trợ cơ chế **wrap key for import**, import có thời hạn hoặc chính sách riêng cho imported material.

Những rủi ro cần kiểm soát:

- Nguồn sinh khóa và chất lượng RNG/entropy có đáng tin không?
- Key material được chuyển bằng cơ chế **bọc/nhập khóa được provider hỗ trợ**, không qua plaintext file/ticket?
- Ai có quyền nhập, kích hoạt, xóa và thay thế?
- Nơi tạo khóa ban đầu có còn bản sao và ai quản lý bản sao đó?
- Rotation có tự động như khóa KMS-generated hay phải import thế hệ mới?
- Nếu imported material bị xóa/hết hạn, có thể phục hồi bằng quy trình nào?
- Có nguy cơ một khóa được import đồng thời vào nhiều môi trường rồi dùng sai key usage hoặc tenant không?

**Import key material không tự nâng mức bảo mật của khóa**. Nếu khóa đã bị lộ trước khi nhập, KMS không thể làm cho các bản mã/chữ ký lịch sử dùng khóa đó trở lại an toàn.

## 6. Phân quyền KMS: ai được làm gì với khóa nào?

Trong một hệ thống bảo mật tốt, **khả năng sử dụng khóa** tách biệt với **quyền quản trị khóa**.

| Role minh họa | Quyền cần thiết | Không nên mặc định có |
| --- | --- | --- |
| **Billing writer** | GenerateDataKey với KEK Billing, theo environment/context. | Sign Payment, ExportKey, DeleteKey, thay policy. |
| **Billing reader** | DecryptDataKey hoặc Unwrap được giới hạn. | Decrypt mọi tenant, Rotate/Destroy. |
| **Payment signer** | Sign bằng signing key được phê duyệt. | Đọc private key, dùng mọi signing key, tự thay trust. |
| **Signature verifier** | GetPublicKey/Verify trên public key tin cậy. | Sign bằng private key. |
| **Key administrator** | Tạo key object, quản trị trạng thái/policy trong phạm vi. | Đọc plaintext khách hàng hoặc tự có mọi quyền Decrypt. |
| **Security approver** | Duyệt rotate, revoke, backup/restore hoặc destroy theo chính sách. | Tự thực hiện mọi thao tác mà không cần người vận hành. |
| **Auditor** | Xem metadata và log đã được lọc. | Lấy secret hoặc dùng Sign/Decrypt. |

Các quyền như `Encrypt`, `Decrypt`, `Sign`, `Verify`, `GenerateDataKey`, `ScheduleKeyDeletion` chỉ là tên **minh họa phổ biến**, không bảo đảm tương ứng 1-1 với từng nhà cung cấp.

### 6.1. Workload identity và least privilege

- Dùng **workload identity** hoặc credential ngắn hạn do platform cấp; không hard-code cloud access key trong source/image.
- Phân vùng **dev/test/staging/production** và tenant hoặc dữ liệu có yêu cầu cách ly.
- Áp **least privilege** theo resource, operation, caller, key usage và điều kiện ngữ cảnh được hỗ trợ.
- Hạn chế quyền sửa policy, xóa khóa, export/import và thay trust root.
- Kiểm tra **đường leo thang quyền**: một principal có quyền sửa IAM hoặc key policy có thể tự cấp Decrypt/Sign về sau.
- Không cho caller trực tiếp cung cấp arbitrary `keyId` hoặc `kmsEndpoint` mà không kiểm tra allowlist server-side.
- Theo dõi việc dùng quyền Sign/Decrypt vượt hành vi bình thường.

**Chứng minh danh tính workload không phải authorization của người dùng cuối**. Ví dụ service Billing có quyền KMS hợp lệ nhưng user đang gọi API không được đọc invoice của tenant khác. Quyết định đó vẫn thuộc ứng dụng và kho dữ liệu.

### 6.2. Multi-tenant: dùng chung KEK hay tách khóa?

Có nhiều mô hình hợp lệ, tùy mức cách ly và chi phí:

| Thiết kế | Lợi ích | Rủi ro/điều kiện |
| --- | --- | --- |
| **Một KEK chung cho nhiều tenant** | Ít key objects, dễ vận hành hơn. | Blast radius lớn; phải có authorization/cryptographic context chính xác. |
| **KEK riêng theo tenant** | Dễ kiểm kê, phân quyền và giới hạn ảnh hưởng ở cấp tenant. | Nhiều key objects, chính sách và chi phí vận hành lớn hơn. |
| **KEK theo nhóm dữ liệu/ứng dụng** | Cân bằng giữa số khóa và phạm vi ảnh hưởng. | Cần mapping rõ tenant/dataset và quy trình đổi scope. |
| **DEK riêng mỗi object/partition** | Giới hạn tác động nếu một DEK bị lộ. | Tăng metadata/wrapped DEK, KMS requests và yêu cầu quản lý version. |

**Không có một cấu hình tối ưu cho mọi hệ thống.** Thiết kế phải dựa trên data classification, mô hình đe dọa, API provider, yêu cầu hủy dữ liệu, throughput và mức độ tách biệt tenant.

## 7. Java 17: dùng KMS theo mô hình envelope encryption

Đoạn mã sau minh họa một **ứng dụng Java 17** sử dụng **KMS adapter** được cấp từ bên ngoài. Tất cả bytes của **KEK/private signing key** đều nằm ngoài code ứng dụng; KMS tạo/giải bọc **DEK** và thực thi IAM theo hợp đồng của adapter. Ứng dụng dùng **AES-GCM** cho dữ liệu, ràng buộc tenant/object/purpose và kiểm tra quyền trước khi giải mã.

**Không phải một KMS SDK cụ thể**: ví dụ được viết với các interface để tách **logic ứng dụng** khỏi nhà cung cấp. Muốn dùng production cần cài adapter từ SDK chính thức, kiểm tra trust/IAM, xử lý retry/quota và tích hợp key registry, backup/restore.

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

public final class KmsEnvelopeEncryptionExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int DEK_BYTES = 32;   // AES-256
    private static final int NONCE_BYTES = 12; // 96-bit AES-GCM nonce
    private static final int TAG_BITS = 128;
    private static final String FORMAT = "billing-envelope-v1";

    public interface KmsClient {
        DataKey generateDataKey(
                String kekRef, Map<String, String> context) throws Exception;

        byte[] decryptDataKey(
                String kekRef, byte[] wrappedDek,
                Map<String, String> context) throws Exception;
    }

    public interface AccessPolicy {
        // Authorization dựa trên principal và đối tượng thực,
        // không tin tenant/object ID tùy ý của client.
        void requireAllowed(String principal, String tenant,
                            String objectId, String operation);

        // Key reference được cấp từ registry/config đáng tin.
        String activeKekFor(String tenant);

        // KMS keyRef/version cũ nào còn được đọc theo policy?
        boolean allowedForDecrypt(
                String tenant, String kekRef, String version);
    }

    public record DataKey(
            byte[] plaintextDek, byte[] wrappedDek, String version) {}

    public record EncryptedRecord(
            String tenant, String objectId,
            String kekRef, String keyVersion,
            byte[] wrappedDek, byte[] nonce, byte[] ciphertextWithTag) {}

    private final KmsClient kms;
    private final AccessPolicy policy;

    public KmsEnvelopeEncryptionExample(
            KmsClient kms, AccessPolicy policy) {
        this.kms = Objects.requireNonNull(kms);
        this.policy = Objects.requireNonNull(policy);
    }

    private static Map<String, String> kmsContext(
            String tenant, String objectId) {
        // Context không phải secret; SDK/provider có thể log các giá trị.
        return Map.of("purpose", FORMAT,
                      "tenant", tenant, "objectId", objectId);
    }

    private static byte[] aad(String tenant, String objectId,
                              String kekRef, String keyVersion)
            throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        // Prefix độ dài: tránh hai tập trường khác nhau nối thành cùng bytes.
        for (String field : new String[] {
                FORMAT, tenant, objectId, kekRef, keyVersion }) {
            byte[] value = field.getBytes(StandardCharsets.UTF_8);
            out.writeInt(value.length);
            out.write(value);
        }
        out.flush();
        return bytes.toByteArray();
    }

    public EncryptedRecord encrypt(
            String principal, String tenant, String objectId,
            byte[] plaintext) throws Exception {
        Objects.requireNonNull(plaintext);
        if (tenant == null || tenant.isBlank()
                || objectId == null || objectId.isBlank()) {
            throw new SecurityException("Invalid object identity");
        }
        // Kiểm tra quyền ứng dụng trước khi cấp DEK.
        policy.requireAllowed(principal, tenant, objectId, "ENCRYPT");
        String kekRef = policy.activeKekFor(tenant);
        if (kekRef == null || kekRef.isBlank()) {
            throw new SecurityException("No approved KEK");
        }

        DataKey generated = kms.generateDataKey(
                kekRef, kmsContext(tenant, objectId));
        byte[] dek = generated == null ? null : generated.plaintextDek();
        try {
            if (dek == null || dek.length != DEK_BYTES
                    || generated.wrappedDek() == null
                    || generated.wrappedDek().length == 0
                    || generated.version() == null
                    || generated.version().isBlank()) {
                throw new SecurityException("Invalid KMS data key");
            }

            // Mỗi lần encrypt trong demo nhận DEK mới từ provider.
            byte[] nonce = new byte[NONCE_BYTES];
            RANDOM.nextBytes(nonce);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(
                    tenant, objectId, kekRef, generated.version()));
            byte[] ciphertext = cipher.doFinal(plaintext);

            return new EncryptedRecord(
                    tenant, objectId, kekRef, generated.version(),
                    generated.wrappedDek().clone(), nonce, ciphertext);
        } finally {
            if (dek != null) Arrays.fill(dek, (byte) 0);
        }
    }

    public byte[] decrypt(
            String principal, String trustedTenant,
            String trustedObjectId, EncryptedRecord record)
            throws Exception {
        Objects.requireNonNull(record);
        // Không lấy trustedTenant từ dữ liệu bản ghi chưa xác thực.
        policy.requireAllowed(
                principal, trustedTenant, trustedObjectId, "DECRYPT");
        if (!Objects.equals(trustedTenant, record.tenant())
                || !Objects.equals(trustedObjectId, record.objectId())
                || record.kekRef() == null
                || record.keyVersion() == null
                || !policy.allowedForDecrypt(
                        trustedTenant, record.kekRef(), record.keyVersion())
                || record.wrappedDek() == null
                || record.wrappedDek().length == 0
                || record.nonce() == null
                || record.nonce().length != NONCE_BYTES
                || record.ciphertextWithTag() == null
                || record.ciphertextWithTag().length < TAG_BITS / 8) {
            throw new SecurityException("Invalid encrypted record");
        }

        byte[] dek = kms.decryptDataKey(
                record.kekRef(), record.wrappedDek(),
                kmsContext(trustedTenant, trustedObjectId));
        try {
            if (dek == null || dek.length != DEK_BYTES) {
                throw new SecurityException("Invalid unwrapped DEK");
            }
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, record.nonce()));
            cipher.updateAAD(aad(
                    trustedTenant, trustedObjectId,
                    record.kekRef(), record.keyVersion()));
            // doFinal kiểm tra tag; lỗi => không dùng/không trả plaintext.
            return cipher.doFinal(record.ciphertextWithTag());
        } finally {
            if (dek != null) Arrays.fill(dek, (byte) 0);
        }
    }
}
~~~

### 7.1. Ranh giới bảo mật trong code

1. **KEK không xuất khỏi KMS** theo hợp đồng kiến trúc; code chỉ biết `kekRef`.
2. **Workload identity và IAM** do adapter/SDK kiểm tra tại KMS; dữ liệu client không được tự cấp quyền đó.
3. **Application authorization** nằm ở `AccessPolicy.requireAllowed`, phải kiểm tra quyền theo principal và đối tượng từ nguồn tin cậy trước khi gọi KMS.
4. **DEK rõ chỉ xuất hiện tạm thời** khi ứng dụng làm AEAD; `Arrays.fill` giảm thời gian giữ bytes trên một mảng nhưng không bảo đảm xóa mọi bản sao trong JVM/provider.
5. **Ciphertext chứa wrapped DEK, nonce và key reference/version** để đọc và rotate về sau.
6. **KMS context và AES-GCM AAD** gắn `tenant`, `objectId`, purpose và version; AAD được mã hóa bằng trường có độ dài để tránh nhầm lẫn.
7. **Fail closed**: key ID sai, tenant sai, context sai, GCM tag sai hoặc KMS AccessDenied không được bỏ qua.
8. **AES-GCM nonce** được tạo ngẫu nhiên 96 bit. Demo giả định provider tạo **DEK mới mỗi lần encrypt**; khi reuse một DEK phải thiết kế ngân sách nonce và giới hạn mã hóa theo key.

### 7.2. Phần demo không giải quyết

- Không có **implementation KmsClient**: API, giới hạn kích thước/context, encryption key version và hành vi error/retry phụ thuộc provider.
- Không có **implementation AccessPolicy**: quyền tenant/object phải dựa trên identity/session và database đã xác thực, không phải tham số do caller tự điền.
- `record` chứa `byte[]` là **mutable qua reference**, không tự immutable. Production nên clone hoặc dùng cấu trúc bảo vệ ở trust boundary.
- Không có **bộ nhớ/đường phân phối DEK chống core dump**, transaction lưu ciphertext + metadata, cache giới hạn, quota và rate limiting.
- Không chứng minh **non-exportability/attestation** hoặc backup/DR của KMS.
- Không có kiểm thử real KMS, key rotation, old key decryption, tamper/tenant negative cases, restore drill hoặc audit correlation.
- Giá trị `version` do adapter trả về là một **abstraction**, không đồng nghĩa mọi KMS cung cấp material version ID. Adapter phải dựa vào key reference/version đã được provider và hệ thống inventory xác thực.
- Nếu provider không trả DEK rõ hoặc không hỗ trợ loại thao tác này, cần dùng **mô hình tương đương được phê duyệt**, không tự xuất khóa để bù.

## 8. Sử dụng KMS cho chữ ký số và xác thực

Ngoài envelope encryption, KMS có thể giữ **private signing key** và cung cấp API **Sign** cho các dịch vụ cần xác thực sự kiện hoặc release artifact.

~~~text
Payment Service
   -> kiểm tra nghiệp vụ/authorization trước khi ký
   -> chuẩn hóa event bytes, chọn signing key ref được duyệt
   -> KMS/HSM Sign(keyRef, message/digest theo algorithm API)
   <- signature + key reference
   -> phát hành sự kiện cùng signature

Ledger Service
   -> nhận public key/chứng chỉ từ nguồn tin cậy
   -> kiểm tra issuer, key usage, audience, tenant, event ID
   -> Verify chữ ký đúng algorithm/bytes
   -> chống replay và kiểm tra quyền trước khi ghi sổ
~~~

**Private key không cần rời KMS/HSM để ký** nếu provider hỗ trợ thuật toán, nhưng một principal có quyền `Sign` trái phép vẫn có thể tạo chữ ký hợp lệ. Cần giới hạn **ai ký, ký loại thông điệp nào, ký trong workflow nào, và ai có thể thay trust mapping**.

### 8.1. Public key và chứng chỉ

Public key không bí mật, có thể phân phối qua **key registry, PKI, JWKS hoặc cơ chế pinning** theo giao thức. Nhưng **một chữ ký hợp lệ dưới public key do attacker gửi** không chứng minh đó là danh tính Payment Service.

Verifier phải kiểm tra **nguồn public key đáng tin, issuer, purpose, thuật toán, key ID, thời hạn và trạng thái thu hồi** theo chính sách. Một KMS không tự thay thế hệ thống PKI hoặc authorization nghiệp vụ.

### 8.2. KMS cũng không tự giải quyết key establishment

KMS có thể quản lý private key bất đối xứng hoặc PSK, nhưng một kết nối TLS 1.3/mTLS vẫn cần **giao thức xác thực, trao đổi khóa và key schedule đúng**, không chỉ gọi API tạo key pair. **X25519/ECDH thuần** không tự chống MITM; phải ràng buộc public key với danh tính qua một giao thức được đánh giá.

## 9. Vòng đời key object trong KMS

Mỗi hệ thống KMS có enum/trạng thái riêng. Một mô hình khái niệm:

~~~mermaid
flowchart LR
    CREATED["CREATED / IMPORT_PENDING"] --> ENABLED["ENABLED / ACTIVE"]
    ENABLED --> ROTATING["ROTATION: key version/successor mới"]
    ROTATING --> RETIRED["RETIRED key/version cũ"]
    ENABLED --> DISABLED["DISABLED / REVOKED theo policy"]
    RETIRED --> DELETE["PENDING_DELETION"]
    DISABLED --> DELETE
    DELETE --> DESTROYED["DESTROYED"]
~~~

Trong mô hình thực tế, có thể có **tái kích hoạt, tạm dừng, hủy lịch xóa hoặc trạng thái imported material**. Không giả định mọi chuyển trạng thái đều được phép hoặc cùng ý nghĩa.

| Giai đoạn | KMS/owner thường làm | Ứng dụng phải lưu ý |
| --- | --- | --- |
| **Tạo** | Sinh hoặc nhập vật liệu, tạo key identity và policy. | Không dùng khóa trước khi đáp ứng kiểm tra owner/usage/nguồn gốc. |
| **Cấp phát/đăng ký** | Gắn IAM/key usage, alias, provenance, tags và key registry. | Dùng trusted key reference, phân biệt tenant/env. |
| **Lưu trữ** | Bảo vệ KEK/private key, thiết lập backup/recovery. | Không export secret ngoài policy, tránh cache dài hạn. |
| **Sử dụng** | Thực thi Sign/Decrypt/Wrap theo IAM và trạng thái. | Kiểm tra quyền dữ liệu, context, AAD, nonce và kết quả. |
| **Xoay vòng** | Tạo material version mới hoặc key object successor. | Hỗ trợ đọc/Verify/Unwrap lịch sử và migration. |
| **Vô hiệu hóa/thu hồi** | Chặn operation hoặc thay trust theo phạm vi. | Dừng dùng khóa nghi lộ, làm sạch cache/đổi phiên. |
| **Hủy** | Hủy key material theo quy trình và bằng chứng. | Đối soát ciphertext, wrapped DEK, backups và retention. |

**Trạng thái ENABLED không có nghĩa IAM cho phép mọi phép toán**; một khóa có thể tồn tại nhưng caller vẫn bị từ chối `Decrypt`. Ngược lại, **disable key không phải tiêu hủy key material**; phương án xử lý sự cố và kiểm toán cần phân biệt chúng.

## 10. Rotation: đổi KEK, đổi DEK và đổi khóa ký

### 10.1. Xoay vòng KEK

Một KMS có thể hỗ trợ **automatic rotation trong cùng key object** hoặc yêu cầu **tạo object mới**. Một số provider có thể giải mã ciphertext cũ nhờ giữ các thế hệ key material tương ứng; nơi khác cần lưu key object/reference cụ thể.

**Không sửa mỗi alias rồi coi mọi DEK đã được bọc lại.** Nếu mục tiêu là loại bỏ phụ thuộc vào một KEK cũ, cần **rewrap wrapped DEKs** hoặc một kế hoạch migration theo API hỗ trợ, đối soát cả archive/backup.

### 10.2. Xoay vòng DEK

Nếu **DEK v1** dùng mã hóa dữ liệu, **DEK v2** là vật liệu mới. Đổi DEK cho dữ liệu cũ thường cần **decrypt rồi re-encrypt/migrate** theo quyền và chính sách. Chỉ rewrap **cùng DEK v1** dưới KEK v4 không thay dữ liệu được bảo vệ bởi DEK đó.

**Đặc biệt:** khi DEK v1 đã bị lộ, rotate KEK không làm bản mã cũ trở lại bí mật. Phải đánh giá dữ liệu/backup bị ảnh hưởng và khả năng re-encrypt dưới DEK mới.

### 10.3. Xoay vòng signing key

Khi Payment Service chuyển từ **S1** sang **S2**:

1. Sinh S2 theo thuật toán và key usage được duyệt.
2. Đăng ký public key/chứng chỉ S2 tại nguồn trust đáng tin.
3. Kiểm tra các verifier đã có khả năng Verify S2.
4. Chuyển quyền **Sign mới** sang S2.
5. Giữ S1 cho **Verify lịch sử** nếu chính sách cho phép, nhưng không tự cho S1 ký mới.
6. Khi S1 bị nghi lộ, cập nhật trust/revocation và đánh giá chữ ký trong khoảng ảnh hưởng.

**S2 được tin cậy không tự làm mọi chữ ký S1 đáng tin**. Verifier cần kiểm tra key version và chính sách thời gian, không chỉ key ID.

## 11. Key inventory, backup/DR và crypto-shredding

Một KMS mạnh vẫn có thể dẫn tới **mất dữ liệu vĩnh viễn** nếu xóa khóa trước khi đánh giá phụ thuộc. Key inventory cần liên kết:

~~~text
KEK / KMS key version
   |-- WRAPS --> DEK-A --> ENCRYPTS --> invoice-2026
   |                          |-- STORED_IN --> archive/snapshot
   |-- WRAPS --> DEK-B --> ENCRYPTS --> ledger-archive
   |                          |-- STORED_IN --> backup-region-2
   |-- USED_BY --> Billing Service read/write
~~~

Với signing key, inventory còn cần **consumer trust, certificate, release artifacts và các sự kiện đã ký**.

### 11.1. Backup chính xác những gì?

- **Khả năng phục hồi key material** theo provider-native recovery/HSM secure backup khi cần.
- **Key reference/version, alias history, trạng thái và policy**.
- **Wrapped DEK, ciphertext, nonce/tag, AAD context và metadata schema**.
- **Trust stores, public certificates, lịch sử revocation và bản ghi audit**.
- **Dependency mapping và backup catalog** để biết dữ liệu nào còn cần khóa cũ.

**Không phải mọi private key có thể hoặc nên xuất để backup.** Một số HSM có quy trình secure backup riêng; một số cloud KMS áp giới hạn khôi phục/xóa khác nhau. Cần **kiểm thử restore**, không chỉ dựa vào dashboard “backup completed”.

### 11.2. RPO/RTO và miền lỗi

**RPO** đo mức trạng thái có thể mất; **RTO** đo thời gian mục tiêu để phục hồi. Với key storage, phải xét thêm **các key versions mới được dùng ngay trước sự cố**: database có ciphertext dưới DEK v27 nhưng backup metadata/recovery chỉ còn v26 có thể không giải mã được.

Một cơ chế multi-region replication có thể giúp availability nhưng **không tự là backup chống xóa nhầm hoặc ransomware**, vì hành động xóa/compromise có thể được sao chép. Thiết kế DR cần xem **failure domain, quyền admin, phương án khôi phục độc lập và thử dữ liệu mã hóa thực tế**.

### 11.3. Crypto-shredding có thật sự hoàn tất?

**Crypto-shredding** là chủ đích làm dữ liệu mã hóa không còn đường giải mã bằng cách hủy khóa cần thiết. Không thể tuyên bố hoàn tất chỉ vì:

- Xóa alias KMS.
- Chuyển `status=DESTROYED` trong inventory.
- Tắt permission của một workload.
- Xóa một bản backup nhưng vẫn còn bản sao key ở HSM/escrow/region khác.

Cần xác định **mọi bản sao vật liệu khóa và đường khôi phục** thuộc phạm vi phải hủy, đồng thời xem xét plaintext/DEK từng bị xuất và dữ liệu đã được sao chép ngoài hệ thống. Nếu provider không hỗ trợ hủy một material version cụ thể, phải thiết kế phạm vi khóa để đáp ứng chính sách từ đầu.

## 12. Audit và observability khi dùng KMS

KMS là điểm thuận tiện để ghi nhận hoạt động mật mã, nhưng log KMS phải được **đối chiếu với ngữ cảnh ứng dụng**.

| Sự kiện | Metadata hữu ích | Không nên ghi |
| --- | --- | --- |
| **KeyCreated/Imported** | actor, key ID, type, usage, origin, policy version. | Raw key/seed/import secret. |
| **PolicyChanged** | actor, old/new policy ref, approval và thời điểm. | Credential hoặc recovery shares. |
| **GenerateDataKey** | workload, KEK ref, purpose, request ID, result. | Plaintext DEK. |
| **Decrypt/Unwrap** | actor/workload, key ID, result, reason code, context đã lọc. | DEK/KEK rõ, plaintext dữ liệu. |
| **Sign** | signing key ref, workflow/actor, digest reference được phép, result. | Private key hoặc nội dung nhạy cảm không cần thiết. |
| **Rotate/Disable/Revoke** | old/new refs, lý do, approval, policy revision. | Secret hoặc nguyên liệu khôi phục. |
| **ScheduledDeletion/Destroyed** | key ref, dependencies checked, actor, time và bằng chứng. | Bất kỳ bản sao key material nào còn dùng được. |

**Encryption context có thể được ghi trong audit** ở một số KMS. Vì vậy không đưa **mật khẩu, token, PII nhạy cảm hoặc DEK rõ** vào context chỉ để tiện debug. Hãy dùng định danh phù hợp, có phân loại dữ liệu và giới hạn quyền xem log.

### 12.1. Những cảnh báo đáng thiết lập

- Đột biến số lượt `Decrypt`/ `Sign` từ principal không thường dùng.
- API `AccessDenied` tăng sau thay đổi IAM, policy hoặc deployment.
- Request tới key khác environment/tenant hoặc ngoài giờ triển khai được phê duyệt.
- Key bị `DISABLED` nhưng workload vẫn cố Encrypt/Unwrap.
- Signing key `RETIRED` tiếp tục được gọi Sign.
- Thay đổi key policy, trust root, alias hoặc schedule deletion bất thường.
- KMS throttling/latency và tỷ lệ giải mã AES-GCM thất bại.

Khi có sự cố, đừng chỉ nhìn log KMS: một API Decrypt hợp lệ về IAM nhưng sai **tenant authorization** có thể chỉ xuất hiện rõ ở application audit. Cần correlation ID và sự phân tách quyền giữa người sử dụng KMS và người kiểm soát audit.

## 13. Tình huống thực tế: Billing, Payment và Ledger

Một nền tảng thanh toán gồm ba dịch vụ:

- **Billing Service** dùng KMS để sinh và giải bọc DEK, mã hóa hóa đơn bằng AES-GCM.
- **Payment Service** dùng KMS/HSM để ký sự kiện thanh toán bằng signing key Ed25519/ECDSA đã được phê duyệt.
- **Ledger Service** xác minh chữ ký bằng public key từ key registry/JWKS/PKI đáng tin.

### 13.1. Dòng mã hóa dữ liệu

1. Billing xác thực caller và kiểm tra quyền trên **invoice-123 của tenant A**.
2. Billing chọn **KEK Billing đã được duyệt** từ registry/config tin cậy.
3. KMS kiểm tra workload identity, key policy và context rồi cấp **DEK tạm + wrapped DEK**.
4. Billing sinh nonce, dùng AES-GCM với AAD gắn tenant/object/purpose và lưu ciphertext/tag cùng wrapped DEK/key reference.
5. Khi đọc, Billing kiểm tra quyền một lần nữa trước khi yêu cầu KMS giải bọc DEK.
6. Sau khi KMS trả DEK, Billing kiểm tra AES-GCM tag và chỉ trả plaintext nếu hợp lệ.

**Lỗi cần tránh:** chỉ vì principal Billing được phép dùng một KEK chung mà cho bất kỳ user nào giải mã mọi invoice thuộc KEK đó. **Tenant isolation là trách nhiệm kết hợp của ứng dụng, dữ liệu và KMS policy**.

### 13.2. Dòng ký số

1. Payment chuẩn hóa event (issuer, event ID, tenant, amount, currency, timestamp/purpose).
2. Payment kiểm tra nghiệp vụ rồi gọi `Sign` theo key reference/usage policy được duyệt.
3. Ledger lấy public key từ nguồn tin cậy, Verify chữ ký, kiểm tra **issuer, audience, event ID, tenant, quyền và chống replay**.
4. Khi S2 thay S1, Payment và Ledger phối hợp chuyển theo lịch, giữ hoặc từ chối chữ ký cũ theo trạng thái tin cậy.

**Chữ ký hợp lệ không tự chứng minh giao dịch được phép.** Nếu Ledger bỏ qua event ID và idempotency, một sự kiện cũ hợp lệ vẫn có thể bị phát lại.

### 13.3. Sự cố giả định: mất quyền KMS

Sau một thay đổi IAM, Billing nhận hàng loạt `AccessDenied` khi giải bọc DEK. Hướng xử lý phù hợp:

1. Phân biệt lỗi policy/credential với mất key material.
2. Điều tra actor, key ID, context và thay đổi IAM qua audit.
3. Khôi phục quyền **tối thiểu** cho workload được phép, theo quy trình phê duyệt hoặc break-glass có giới hạn nếu thực sự cần.
4. Không xuất KEK dạng rõ và không fallback sang AES key hard-coded.
5. Kiểm tra decrypt bằng dữ liệu thử đã được phép; xác minh không mở quyền ngoài tenant.
6. Ghi lại sự cố, sửa kiểm thử/IaC và theo dõi lỗi sau khắc phục.

Nếu KMS **thực sự mất khả năng khôi phục key material**, không thể sửa vấn đề bằng thay alias tùy ý. Cần đánh giá **provider recovery và các DEK/ciphertext đang phụ thuộc**.

## 14. Sai lầm thường gặp khi triển khai KMS

| Sai lầm | Hậu quả | Phòng vệ |
| --- | --- | --- |
| Coi có KMS là đủ, không kiểm tra tenant | Workload có thể giải mã dữ liệu ngoài quyền nghiệp vụ. | Authorization ứng dụng + IAM + context/AAD đúng. |
| Hard-code KEK/DEK trong code rồi vẫn gọi một API KMS khác | Secret vẫn lộ qua source/artifact. | KMS-managed key material, CSPRNG, workload identity. |
| Cấp `Decrypt`, `Sign`, `Delete` cho cùng mọi service | Một workload compromise có tác động rất lớn. | Least privilege, separation of duties, policy review. |
| Tin rằng non-exportable ngăn mọi lạm dụng | Kẻ có quyền Sign/Decrypt vẫn có thể dùng API hợp lệ. | Giới hạn workflow, key usage, actor/context và audit. |
| Dùng một KEK chung không giới hạn tenant | Blast radius khi lộ quyền/key material lớn. | Chọn mức phân vùng KEK/DEK theo threat model. |
| Không xác thực public key của signer | Chấp nhận chữ ký giả nếu public key do attacker cung cấp. | Trusted PKI/JWKS/key registry, kiểm tra issuer/usage. |
| Lưu DEK rõ trong database/log | Vô hiệu hóa lợi ích của envelope encryption. | Chỉ lưu wrapped DEK; hạn chế RAM và log. |
| Reuse AES-GCM nonce dưới cùng DEK | Phá confidentiality/integrity của AEAD. | Nonce uniqueness và giới hạn key usage. |
| Truyền PII/secret vào encryption context | Rò qua audit hoặc metadata. | Context không bí mật, phân loại và lọc dữ liệu. |
| Chỉ lưu current alias, bỏ key version | Khó hoặc không thể giải mã dữ liệu lịch sử. | Lưu key reference/version và metadata theo provider. |
| Coi KEK rotation tương đương DEK rotation | Dữ liệu dùng DEK bị lộ vẫn rủi ro. | Rewrap KEK vs re-encrypt DEK theo tình huống. |
| Disable/hủy KEK khi backup còn phụ thuộc | Có thể không khôi phục được dữ liệu. | Dependency inventory và restore drill trước hủy. |
| Nhầm replication với bản backup độc lập | Xóa/compromise có thể lan sang replica. | Phân tích failure domain và recovery strategy. |
| KMS timeout thì fallback sang key cố định | Tạo đường vượt kiểm soát khi dịch vụ lỗi. | Fail closed, HA/retry có giới hạn và DR đã được duyệt. |
| Không theo dõi KMS quota/latency | Tăng lỗi/throttling và gián đoạn dịch vụ. | Caching có giới hạn, backoff, metrics và capacity planning. |
| Tự tin mọi provider hỗ trợ cùng API/version | Sai contract, lỗi migration hoặc decrypt. | Kiểm tra tài liệu, SDK và trạng thái thực của provider. |
| Đặt toàn bộ quyền backup/export/restore ở một người | Tạo điểm phá hoại và lộ root key. | Quorum/dual control khi rủi ro yêu cầu, audit độc lập. |

## 15. Checklist kiến trúc KMS cho production

1. **Scope:** khóa nào cần KMS, khóa nào cần HSM ranh giới cao hơn, và dữ liệu nào cần envelope encryption?
2. **Algorithm/key usage:** AES-GCM, Ed25519/ECDSA/RSA-PSS, HMAC, RSA-OAEP... có được provider và security policy hỗ trợ không?
3. **Key generation:** khóa được sinh bằng CSPRNG/DRBG phù hợp; origin/BYOK có được kiểm chứng không?
4. **Identity:** workload sử dụng credential ngắn hạn và được xác thực độc lập không?
5. **IAM:** mỗi service chỉ có quyền API và key IDs cần thiết; ai có thể thay policy, disable hoặc delete?
6. **Authorization:** ứng dụng kiểm tra quyền tenant/object trước KMS `Decrypt`/`Sign` không?
7. **Custody:** KEK/private key có non-exportable theo thiết kế; nếu không thì rủi ro xuất key được kiểm soát thế nào?
8. **Data encryption:** DEK có được sinh đủ entropy, dùng đúng AES-GCM nonce/tag/AAD không?
9. **Metadata:** ciphertext lưu wrapped DEK, key reference/version, nonce/tag, schema và context phục vụ restore không?
10. **Key separation:** DEK, KEK, signing key, MAC key và session key có tách purpose và policy không?
11. **Rotation:** có cách chuyển KEK/signing key, rewrap DEK hoặc re-encrypt dữ liệu không? Consumer có sẵn sàng không?
12. **Inventory:** có owner, version/predecessor, dependency graph và dữ liệu backup liên quan không?
13. **Compromise:** có runbook revoke/disable, đánh giá DEK đã lộ và các chữ ký bị giả mạo không?
14. **DR:** khả năng key recovery có được provider hỗ trợ, kiểm thử với old/new key versions và backup thật theo quyền không?
15. **Crypto-shredding:** có kiểm kê mọi bản sao key/escrow/replica thuộc phạm vi hủy không?
16. **Audit:** log đủ key ID, actor, operation, result, nhưng không chứa secret và PII không cần thiết không?
17. **Performance:** đã tính latency, quotas, retry có giới hạn, idempotency và key caching constraints không?
18. **Operational review:** có owner được chỉ định cho policy, rotation, incident response và phê duyệt hủy khóa không?

## 16. Câu hỏi tự kiểm tra

1. **KMS** là gì, khác HSM và secret manager ở những điểm nào?
2. Vì sao có KMS không đồng nghĩa ứng dụng tự động được phân quyền dữ liệu đúng?
3. **DEK** và **KEK** khác nhau về mục đích, vị trí và thời gian tồn tại như thế nào?
4. Trong envelope encryption, tại sao ứng dụng thường lưu **wrapped DEK** thay vì raw DEK?
5. Vì sao cần ràng buộc **tenant, object và purpose** trong AAD/context? Chúng có thay application authorization không?
6. Một key được đánh dấu **non-exportable** có còn bị lạm dụng qua `Sign` hoặc `Decrypt` không?
7. Một KMS key ID và một **key material version** có nhất thiết là cùng một thứ không?
8. Khi rotate KEK, có phải mọi bản mã đều đã được re-encrypt dưới DEK mới không?
9. Nếu DEK cũ đã lộ, chỉ rewrap nó dưới KEK mới có đủ không?
10. Vì sao private signing key trong KMS vẫn cần verifier kiểm tra nguồn public key và issuer?
11. Khi tạo một key bằng BYOK, cần kiểm tra provenance, nhập vật liệu, hạn dùng và nguồn backup thế nào?
12. Nếu KMS bị outage, ứng dụng có nên dùng một AES key hard-coded để duy trì dịch vụ không?
13. Một key bị **DISABLED** có giống key đã **DESTROYED** không?
14. Vì sao multi-region replication không tự bảo đảm có bản backup phục hồi sau khi xóa nhầm?
15. Trước khi hủy KEK, key inventory cần tìm các **wrapped DEK, ciphertext, backups và consumers** nào?
16. Những dữ liệu gì nên và không nên đưa vào KMS audit log và encryption context?

**Ghi nhớ:** **KMS** là hệ thống **quản lý, bảo vệ và kiểm soát việc sử dụng khóa mật mã**, không chỉ là nơi lưu bytes bí mật. Thiết kế đúng kết hợp **KMS/HSM custody, khóa DEK/KEK và envelope encryption, workload identity, IAM, ứng dụng kiểm tra quyền dữ liệu, thuật toán và nonce/AAD chuẩn, rotation, thu hồi, backup/DR, key inventory và audit**. Mục tiêu cuối cùng không chỉ là khóa khó bị lấy cắp, mà còn là **khóa được dùng đúng người, đúng dữ liệu, đúng mục đích và có thể được thay thế hoặc hủy an toàn trong suốt vòng đời**.
