# Key export — Xuất khóa mật mã an toàn trong quy trình phân phối khóa

## 1. Key export là gì?

**Key export** (*xuất khóa mật mã*) là quá trình đưa một **đối tượng khóa**, **vật liệu khóa**, hoặc **biểu diễn được bảo vệ của vật liệu khóa** ra khỏi nơi khóa đang được quản lý để một hệ thống, người nhận hoặc môi trường khác có thể sử dụng hay lưu giữ theo chính sách.

Cần phân biệt rõ: **export public key**, **export raw symmetric/private key**, **export wrapped key** và **backup/replication do thiết bị quản lý** là các hành động có **mức rủi ro và ý nghĩa khác nhau**.

Ví dụ:

- Public key của dịch vụ ký hóa đơn có thể được công bố để bên nhận **verify chữ ký**.
- HMAC secret chia sẻ cho đối tác là **bí mật**, nên việc gửi ra ngoài phải nằm trong quy trình phân phối được phê duyệt.
- Một DEK được bọc dưới KEK có thể được lưu bên cạnh ciphertext trong envelope encryption; **wrapped DEK không phải raw DEK**.
- Private signing key non-exportable trong HSM được thiết kế để **không xuất dưới dạng rõ qua API thông thường**. Khi cần thay HSM, tổ chức có thể phải dùng quy trình **backup/restore chuyên dụng** hoặc **tạo key mới**, tùy thuộc thiết bị.

Trong chương **Key distribution** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, Key export gắn với vòng đời từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy khóa**. Đây cũng là nơi kết nối mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Nguyên tắc cốt lõi:** **Không phải khóa nào cũng được phép xuất; không phải dạng xuất nào cũng làm lộ khóa; và xuất khóa dưới dạng đã mã hóa không tự bảo đảm người nhận, mục đích hoặc quá trình import là đúng.**

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **raw export**, **wrapped export**, **public-key export**, **backup/replication** và **remote cryptographic use**.
2. Đánh giá vì sao xuất secret/private key làm thay đổi **trust boundary** và **blast radius**.
3. Hiểu cách dùng **KEK, AES Key Wrap, public-key wrapping, KMS/HSM và PKCS#11** theo khả năng nền tảng.
4. Thiết kế phê duyệt, phân quyền, **dual control**, định danh recipient, vận chuyển an toàn và audit.
5. Phân tích key export đối với **DEK/KEK, HMAC, private signing key, ECDH và recovery key**.
6. Dùng Java JCA minh họa **wrap/unwrap một AES key** mà không log raw key.
7. Lập kế hoạch migration, import, rollback, rotation và ứng cứu khi xuất khóa sai phạm.

## 2. Thuật ngữ cơ bản: export không phải một operation duy nhất

| Thuật ngữ | Ý nghĩa | Raw secret có đi ra khỏi vùng cũ không? |
| --- | --- | --- |
| **Public-key export** | Công bố public key hoặc chứng thư | Không; đây là dữ liệu public trong key pair |
| **Plaintext/raw export** | Đưa bytes secret/private key ra khỏi boundary | **Có** |
| **Wrapped-key export** | Bọc secret/private key dưới wrapping key được phép | Vật liệu dưới dạng rõ **không nên rời khỏi vùng bảo vệ trong giai đoạn wrapping**, nếu thiết bị hỗ trợ xử lý nội bộ |
| **Encrypted backup** | Sao lưu key material dưới cơ chế được quản lý | Tùy product; thường được bảo vệ và giới hạn nơi restore |
| **Replication/cluster sync** | Đồng bộ khóa giữa các thiết bị/partition | Tùy boundary, trust và cơ chế vendor |
| **Key reference export** | Gửi key ID/URI/handle/metadata | Không xuất material; recipient vẫn cần quyền dùng khóa |
| **Remote cryptographic operation** | Gửi yêu cầu `Sign`, `Decrypt`, `Unwrap` tới KMS/HSM | Key gốc có thể không rời thiết bị |
| **Key derivation** | Tạo key con qua KDF từ secret gốc | Key con có thể đi ra ngoài, tùy API/policy |
| **Key migration** | Di chuyển chức năng và phụ thuộc sang hệ thống khác | Có thể cần export/import, hoặc chỉ rotate và migrate dữ liệu |

### Ví dụ

~~~text
HSM giữ private signing key
  |-- GetPublicKey --> public key / certificate (được phép công bố)
  |-- Sign(digest) --> signature (private key vẫn ở HSM)
  |-- ExportRawPrivateKey --> bị chặn nếu key non-exportable
  |-- ProtectedBackup --> chỉ khi thiết bị và chính sách hỗ trợ

KMS giữ KEK
  |-- GenerateDataKey --> DEK plaintext tạm + wrapped DEK (tùy API)
  |-- Wrap/Unwrap --> thao tác với DEK theo chính sách
  |-- ExportRawKEK --> có thể không được hỗ trợ
~~~

**Một API tên `Decrypt` trả plaintext DEK** vẫn có ý nghĩa **đưa một secret ra client**, dù tên API không chứa chữ “Export”. Đánh giá rủi ro theo **vật liệu nào rời boundary**, không chỉ tên lệnh.

## 3. Key export làm thay đổi trust boundary như thế nào?

Trước khi xuất, một key có thể nằm trong **HSM/KMS boundary** với điều kiện non-exportable, IAM và audit rõ ràng. Sau khi xuất raw key, **thêm một bản sao** có thể nằm trong RAM, file, network buffer, CI runner hoặc secret manager ở một hệ thống khác.

~~~mermaid
flowchart LR
    K[HSM/KMS chứa secret] -->|Remote Sign/Unwrap| O[Kết quả phép toán]
    K -->|Wrapped export theo policy| W[Ciphertext của khóa]
    W --> T[Đường truyền được bảo vệ]
    T --> D[Recipient import/unwrap boundary]
    K -.->|Raw plaintext export, nếu được cho phép| R[Host memory/file]
    R --> X[Rủi ro copy, dump, log, backup]
    O --> A[Ứng dụng nghiệp vụ]
    D --> B[Target key inventory và IAM]
~~~

### 3.1. Confidentiality

Khi raw key tồn tại ở nhiều nơi, đối thủ có **nhiều đường tấn công hơn**: filesystem, memory dump, build artifact, snapshot, log, backup hoặc credential của recipient.

### 3.2. Integrity và authenticity

Bí mật được chuyển qua kênh mã hóa **chưa chắc là khóa đúng**. Người nhận phải xác thực **nguồn gửi, resource/key ID, algorithm, purpose, recipient binding và phiên bản**; nếu không có thể import nhầm key hoặc key bị thay thế.

### 3.3. Availability và recoverability

Không export có thể tăng kiểm soát bí mật, nhưng cũng tạo yêu cầu về **backup/HA/DR**. Hệ thống phải chọn cơ chế phục hồi có bảo đảm phù hợp, không tự tạo bản raw export ngoài chính sách để “cho chắc”.

### 3.4. Accountability

Khi nhiều bản sao secret tồn tại, khó kết luận **ai đã dùng raw key ở bên ngoài**. KMS/HSM không nhìn thấy mọi operation thực hiện offline với bản sao đã xuất. Audit export phải ghi **bản sao được gửi tới đâu, ai nhận, khi nào, key version và mục đích**.

## 4. Key export có cần thiết không?

Không phải yêu cầu “chuyển khóa” nào cũng cần xuất vật liệu.

### Ưu tiên phương án ít rủi ro hơn khi đạt mục tiêu

| Nhu cầu | Phương án nên đánh giá trước | Khi nào cần export? |
| --- | --- | --- |
| Ứng dụng muốn ký số | Gọi `Sign` trong KMS/HSM bằng key handle | Chỉ khi hệ thống đích thực sự không thể dùng remote signer và policy cho phép |
| Bên thứ ba cần verify chữ ký | Công bố **public key/certificate** qua trust channel | Không xuất private key |
| Ứng dụng muốn giải mã dữ liệu | KMS `Decrypt/Unwrap`, envelope encryption | Có thể trả **DEK tạm**, nhưng không export KEK |
| Chuyển cloud account/provider | Tạo key mới, rewrap hoặc re-encrypt dữ liệu | Nếu phải giữ nguyên vật liệu và có cơ chế được hỗ trợ |
| Backup HSM | Protected backup/replication theo vendor | Không dùng raw export nếu không bắt buộc |
| Phân phối HMAC secret cho đối tác | Provisioning bí mật qua kênh có xác thực, giới hạn purpose | Có thể cần chia sẻ secret, nhưng tránh plaintext email/chat |
| Luân chuyển signing key | Sinh key pair mới, phân phối public key mới | Không cần export private key cũ |
| Chuyển cấu hình ứng dụng | Phân phối key reference/IAM | Không cần di chuyển raw key |

Một quyết định xuất khóa hợp lệ phải chứng minh **tại sao phương án chỉ dùng key handle, public key hoặc key rotation không đáp ứng yêu cầu**.

## 5. Phân loại key trước khi export

Khác key type đồng nghĩa khác quy tắc phân phối.

| Loại khóa | Tính chất | Nguyên tắc export |
| --- | --- | --- |
| **AES DEK** | Secret đối xứng mã hóa dữ liệu | Có thể xuất **dạng wrapped**, hoặc plaintext ngắn hạn cho workload theo design; tránh lưu rõ |
| **KEK** | Secret bảo vệ nhiều DEK | Ưu tiên non-exportable trong KMS/HSM; phạm vi ảnh hưởng lớn |
| **HMAC key** | Secret chia sẻ để tạo/verify MAC | Chỉ đưa cho đúng đối tác/principal; bảo vệ kênh và phiên bản |
| **Private RSA/ECDSA/Ed25519 signing key** | Secret tạo chữ ký | Ưu tiên non-exportable khi rủi ro yêu cầu; export ngoại lệ phải kiểm soát mạnh |
| **Public key / certificate** | Không bí mật, dùng verify/encrypt/trust | Thường được phân phối, nhưng phải **xác thực nguồn và binding** |
| **Static ECDH/X25519 private key** | Secret tạo shared secret | Không gửi cho peer trong giao thức ECDH thông thường |
| **Ephemeral ECDHE private key** | Secret phiên tạm thời | Không export/lưu dài hạn nếu giao thức không yêu cầu |
| **Root/CA signing key** | Trust anchor với ảnh hưởng rộng | Thường kiểm soát nghiêm ngặt, ceremony và dual control |
| **Recovery key** | Có thể mở nhiều bí mật hoặc backup | Quyền hạn hẹp, truy cập đặc biệt, cân nhắc quorum/threshold |

### Đừng nhầm public key với secret

Public key được tạo **từ private key tương ứng** nên hai thành phần có liên hệ toán học. Export public key là bình thường trong PKI, JWT/JWKS hoặc ECDH; **export private key** là hành động nhạy cảm khác hẳn.

### Không tái sử dụng key material vì tiện phân phối

Không dùng cùng 32 byte cho AES-GCM, HMAC và wrapping chỉ vì “dễ gửi một secret”. Tách **purpose, key usage và cryptoperiod** giúp hạn chế blast radius khi một bên nhận bị lộ khóa.

## 6. Plaintext export: tại sao phải hạn chế?

**Plaintext export** chuyển vật liệu bí mật ra nơi nhận ở dạng có thể sử dụng trực tiếp. Nó có thể cần trong một số hệ thống legacy, recovery hoặc migration, nhưng là đường rủi ro cao.

### Các điểm lộ thường bị bỏ sót

- Key bytes trong **heap/native memory, clipboard, shell history hoặc process arguments**.
- Secret xuất hiện trong **log, stack trace, tracing payload, packet capture**.
- File tạm không mã hóa, thư mục download hoặc home directory của operator.
- Secret được lưu trong CI variable/output hoặc build artifact.
- Bản sao trong **backup/snapshot** của host xử lý export.
- Credential/chứng thư xác thực kênh truyền và target import bị dùng sai.
- Người nhận tiếp tục giữ raw key sau khi đã import xong.

### Kiểm soát tối thiểu nếu chính sách thật sự cho phép

1. Có **lý do được phê duyệt** với key ID/version, scope, recipient và thời hạn.
2. Đường truyền **có xác thực và bảo mật**, ưu tiên wrapping bằng key của recipient.
3. Hạn chế nơi key xuất hiện dạng rõ: môi trường cô lập, quyền tối thiểu, không lưu log.
4. Không gửi key qua email/chat không được thiết kế để trao đổi bí mật.
5. Xác minh recipient import thành công **trước khi** xóa bản ở nguồn.
6. Thu hồi quyền/credential export, xử lý file tạm và kiểm tra backup.
7. Ghi audit metadata; **không lưu raw key trong ticket hay audit event**.

**Một lần raw export có thể phá vỡ giả định “private key chưa từng tồn tại ngoài HSM”**. Việc import trở lại rồi đánh dấu non-exportable không xóa được nguy cơ các bản sao cũ.

## 7. Wrapped-key export: đưa khóa ra ngoài dưới dạng được bảo vệ

**Key wrapping** dùng **KEK hoặc cơ chế khóa công khai được thiết kế cho việc bảo vệ khóa** để tạo một bản bọc (*wrapped key blob*). Recipient phải có **đúng quyền và khả năng unwrap** để khôi phục key ở boundary đích.

~~~mermaid
sequenceDiagram
    participant O as Key owner
    participant C as Source key custodian
    participant S as Source KMS/HSM
    participant T as Secure transfer channel
    participant D as Destination KMS/HSM
    participant A as Auditor
    O->>C: Phê duyệt export key/version/purpose/recipient
    C->>S: Yêu cầu wrap đúng key và KEK/mechanism
    S-->>C: Wrapped key blob + metadata được phép
    C->>T: Gửi package và manifest có kiểm tra toàn vẹn
    T->>D: Chuyển đúng người nhận đã xác thực
    D->>D: Verify manifest/policy và unwrap/import
    D-->>C: Receipt có identity, key handle và kết quả
    C->>A: Source + destination audit, approval và receipt
~~~

### Những điều wrapping bảo vệ

- Bản bọc có thể giữ key material **không xuất hiện dạng rõ trên đường truyền** nếu source/recipient xử lý trong boundary.
- Chỉ bên có wrapping/unwrapping key hoặc private recipient key tương ứng mới có thể unwrap theo thiết kế.
- Cơ chế chuẩn có thể cung cấp **kiểm tra toàn vẹn đối với key material**.

### Những điều wrapping không tự bảo đảm

- Recipient đã được **key owner phê duyệt** hay chưa.
- Bản bọc được gửi cho **đúng tenant/environment/target HSM**.
- Metadata ngoài bản bọc như `keyId`, `purpose`, `expiresAt` đã được **xác thực** chưa.
- Secret không bị lộ **trước khi wrap hoặc sau khi unwrap**.
- Quyền quản trị/backup tại đích có tương đương với nguồn không.
- Bản key trong source còn được sử dụng hoặc phải bị thu hồi như thế nào.

**Key wrapping không phải một giấy phép xuất khóa.** Cơ chế export vẫn cần IAM, approval, recipient authentication và audit.

## 8. Wrapping key (KEK): quản lý riêng với khóa được xuất

Một **KEK** dùng để bảo vệ khóa khác không nên đồng thời trở thành khóa mã hóa mọi dữ liệu và khóa ký mọi artifact. Trong thiết kế phân tách, KEK có **purpose, key usage, IAM, cryptoperiod và ranh giới lưu trữ riêng**.

### Quy tắc chính

- KEK phải được tạo và bảo vệ theo **thuật toán và độ dài phù hợp**.
- Ứng dụng/role có quyền **Wrap** không mặc nhiên có quyền **Unwrap**, và ngược lại.
- Khi vận chuyển liên tổ chức, phải biết **ai giữ KEK** và liệu một bên không tin cậy có quyền unwrap hay không.
- Cần **version hóa wrapping key** để recipient biết nên unwrap bằng phiên bản nào.
- Nếu KEK lộ, phải đánh giá **toàn bộ wrapped keys** mà đối thủ có thể tiếp cận.
- Không hard-code KEK vào source code hoặc đưa vào cùng package chứa wrapped key.
- Không dùng thuật toán key wrapping tự chế hoặc tự sử dụng AES-ECB như một cơ chế wrap.

### Khi wrapped DEK nằm cạnh ciphertext

Trong envelope encryption, **wrapped DEK có thể được lưu cùng ciphertext** nếu wrapping scheme, KEK và quyền được bảo vệ đúng. Điều này không biến wrapped DEK thành dữ liệu không cần kiểm soát: metadata, access control và backup vẫn quan trọng.

### KEK non-exportable và DEK exportable

Một thiết kế phổ biến:

~~~text
KMS/HSM:
  KEK (non-exportable)
      |
      +-- Wrap / Unwrap DEK theo IAM

Ứng dụng / object store:
  ciphertext dữ liệu
  wrapped DEK
  KEK key ID/version
  nonce, tag, AAD profile
~~~

**Raw KEK không cần rời KMS/HSM**. Một số API có thể cung cấp DEK plaintext ngắn hạn cho ứng dụng, tùy sản phẩm và policy, vì ứng dụng cần DEK để AES-GCM xử lý dữ liệu. Phải phân biệt **DEK ra ngoài boundary** với **KEK ra ngoài boundary**.

## 9. Chọn cơ chế key wrapping an toàn

Không phải mọi thuật toán mã hóa đều phù hợp làm phương thức export key. Cần chọn **thuật toán/format chuẩn, được hỗ trợ bởi cả source và destination** và đúng loại key.

| Cơ chế | Trường hợp phù hợp | Điểm cần kiểm tra |
| --- | --- | --- |
| **AES Key Wrap (AES-KW)** | Bọc key material có độ dài đúng yêu cầu của cơ chế | RFC 3394 hoặc đặc tả ứng dụng, độ dài hợp lệ, tính toàn vẹn key, KEK |
| **AES Key Wrap with Padding (AES-KWP)** | Bọc key material có độ dài không phù hợp AES-KW thông thường | RFC 5649, padding/format, khả năng tương thích |
| **AEAD như AES-GCM** | Mã hóa package có AAD gắn metadata | Nonce không lặp dưới key, tag, giao thức/package được thiết kế đúng |
| **RSA-OAEP** | Bọc secret có kích thước nhỏ theo key transport design | Padding, hash/MGF1, giới hạn kích thước plaintext, xác thực recipient |
| **HPKE / hybrid public-key encryption** | Bảo vệ secret cho recipient public key theo suite và protocol hỗ trợ | Suite, key validation, context, identity binding và format |
| **Native HSM protected export / backup** | Migration/backup trong hệ sinh thái thiết bị | Vendor-specific key format, firmware, partition, ACL và restore policy |

### 9.1. AES-KW không phải AES-GCM

AES Key Wrap có cơ chế và quy tắc độ dài riêng, **không dùng nonce/IV ngẫu nhiên theo cách AES-GCM**. Không lấy một ví dụ GCM rồi đổi tên thành “AESWrap”; mỗi thuật toán có đặc tả riêng.

AES-KW **không tự xác thực metadata tùy ý bên ngoài blob** như recipient ID, source purpose hay expiration. Nếu ứng dụng cần bảo vệ toàn bộ manifest, phải dùng **cơ chế xác thực cấu trúc package**, ví dụ chữ ký số hoặc AEAD/AAD được thiết kế và thực thi đúng.

### 9.2. RSA-OAEP không phải giải pháp cho file lớn

RSA-OAEP thường dùng bảo vệ **vật liệu ngắn**, ví dụ một DEK. Giới hạn kích thước phụ thuộc modulus và hash. Không dùng RSA-OAEP để mã hóa cả database/file; kết hợp với **AEAD symmetric encryption** hoặc scheme hybrid chuẩn.

### 9.3. Encryption không đủ nếu thiếu xác thực nguồn

Một ciphertext mã hóa cho public key của recipient **không tự cho biết nó đến từ người gửi hợp lệ**. Để ngăn thay thế khóa, phải xác thực **source, manifest, approved action và target** bằng thiết kế có trust anchor đúng.

### 9.4. Đừng tự chế định dạng gói export

Nên dùng **chuẩn/protocol và API provider đã được phân tích**, với versioning rõ. Nếu hai HSM không tương thích wrapped-key format hoặc thuật toán, giải pháp đúng có thể là **tạo key mới và di chuyển dữ liệu**, không tìm cách ép xuất plaintext từ khóa vốn non-exportable.

## 10. Non-exportable, sensitive và key attributes trong HSM

Với **HSM/PKCS#11**, key material có thể được kiểm soát bởi **object attributes**, mechanism, token policy và vai trò người gọi.

| Thuộc tính PKCS#11 điển hình | Vai trò | Lưu ý |
| --- | --- | --- |
| `CKA_EXTRACTABLE` | Cho phép key được xuất/wrap theo cơ chế hỗ trợ | `false` thường chặn đường wrapped export PKCS#11 thông thường |
| `CKA_SENSITIVE` | Hạn chế việc truy vấn giá trị nhạy cảm | Không đồng nghĩa key không thể được wrap nếu extractable |
| `CKA_ALWAYS_SENSITIVE` | Ghi nhận key luôn sensitive theo semantics token | Không thay xác minh provenance đầy đủ |
| `CKA_NEVER_EXTRACTABLE` | Ghi nhận key chưa từng extractable trong phạm vi token | Không chứng minh key chưa từng có bản sao trước import |
| `CKA_WRAP` | Cho phép key làm wrapping key | Không tự chứng minh được phép xuất mọi key |
| `CKA_UNWRAP` | Cho phép key làm unwrapping key | Cần policy recipient và target attributes |
| `CKA_WRAP_WITH_TRUSTED` | Có thể yêu cầu wrapping key có thuộc tính trusted | Phụ thuộc cách hỗ trợ/kiểm soát của token |
| `CKA_TRUSTED` | Thuộc tính tin cậy phục vụ một số mechanism/policy | Quyền đặt thuộc tính phải kiểm soát mạnh |
| `CKA_ID` / `CKA_LABEL` | Tìm và nhận diện key object | Label không bắt buộc duy nhất |
| `CKA_PRIVATE` | Kiểm soát mức truy cập object khi chưa login | Không đồng nghĩa `CKA_CLASS=CKO_PRIVATE_KEY` |

### 10.1. HSM non-exportable là một quyết định từ đầu

Nếu yêu cầu **“private key không bao giờ rời boundary dưới dạng rõ qua đường export”**, cách mạnh là **generate-in-HSM** rồi cấu hình non-exportable ngay từ lúc tạo, cùng chính sách backup/HA tương ứng.

Import một private key đã tồn tại ngoài HSM rồi đặt `CKA_EXTRACTABLE=false` **không xóa được những bản copy cũ**.

### 10.2. Không hiểu sai `C_WrapKey`

Trong PKCS#11, **`C_WrapKey`** là operation chuẩn cho việc bọc khóa khi **wrapping key, key được bọc, mechanism và session** thỏa các điều kiện áp dụng. Nó **không** là “lối thoát” chắc chắn để export một key bị đặt non-extractable.

Thiết bị có thể có **protected backup/clone** không thực hiện bằng API xuất khóa thông thường. Quy trình này phải được đánh giá theo tài liệu vendor và điều kiện tin cậy, không được gọi nhầm là một raw export tự do.

### 10.3. Cơ chế backup không chứng minh key có thể xuất tùy ý

Một HSM có thể hỗ trợ backup nội bộ của key non-exportable dưới dạng **chỉ restore được trong một trust domain được kiểm soát**. Điều đó khác với việc cho phép operator nhận raw key hoặc unwrap ở bất kỳ thiết bị nào.

## 11. Managed KMS, cloud HSM và Key export

Mỗi dịch vụ **KMS/HSM** có API, key type và export policy riêng. Không được suy đoán tính năng từ một tên gọi chung.

### Nhóm tình huống thường gặp

**Managed KMS với KEK non-exportable**

- Có key resource và IAM.
- Cung cấp các operation như `Encrypt`, `Decrypt`, `GenerateDataKey`, `ReEncrypt` hoặc `Sign` tùy provider.
- Không mặc định hỗ trợ tải raw KEK/private key.
- `GenerateDataKey` có thể trả **DEK plaintext và bản bọc**, tùy API: điều này **không có nghĩa KEK bị export**.

**Cloud HSM cho khách hàng quản trị trực tiếp**

- Có thể có PKCS#11, key object attributes, session/role và mechanism.
- Một số key được cấu hình **extractable**; những key khác là **non-exportable**.
- Migration/backup có thể dựa vào cluster, secure clone hoặc vendor wrapping format.

**Self-hosted/on-prem HSM**

- Tổ chức chịu trách nhiệm lớn hơn cho thiết bị vật lý, custody, backup media, firmware, quorum và DR.
- Điều kiện tamper/zeroization và **backup restore** phải được diễn tập.
- Không có một định dạng wrapped export chung chắc chắn chạy giữa mọi vendor.

### Bốn câu hỏi trước khi phê duyệt

1. **Key type này có export được theo API/provider không?**
2. **Có thể export ở dạng nào: public, wrapped, protected backup hay raw?**
3. **Những người nào có thể sửa policy để cho phép export hoặc import?**
4. **Sau khi chuyển, target có thể bảo vệ vật liệu ở mức tương đương không?**

Nếu câu trả lời cho câu 1 là **không**, đừng tự tìm “đường vòng” để ép xuất key. Cân nhắc **rotate tại đích** và **migrate các phụ thuộc mật mã**.

## 12. Vai trò và separation of duties trong Key export

Key export, đặc biệt với raw secret hoặc private key, nên là một trong các thao tác được **phân quyền chặt** trong vòng đời khóa.

| Vai trò | Trách nhiệm | Không mặc nhiên được làm |
| --- | --- | --- |
| **Key owner** | Quyết định mục đích, recipient, điều kiện cho phép export và risk acceptance | Tải raw key chỉ vì là owner |
| **Key custodian** | Vận hành HSM/KMS, chọn mechanism được duyệt, tổ chức bàn giao | Tự phê duyệt và gửi key đến đích tùy ý |
| **Security approver** | Rà soát thuật toán, boundary, phương thức wrapping, recipient và ngoại lệ | Sử dụng key cho nghiệp vụ |
| **Destination custodian** | Xác minh target, import, áp dụng policy và giữ evidence | Cho phép key được dùng ngoài purpose |
| **Key user / workload** | Dùng key theo operation đã cấp | Xuất hoặc thay key policy tùy ý |
| **Auditor** | Đối chiếu approvals, source/recipient, export/import và deletion | Nhận raw key làm bằng chứng |
| **Incident responder** | Cô lập khi nghi export sai phạm | Tự hủy key mà không xét dữ liệu phụ thuộc |

### Dual control và key ceremony

Với **root/CA key, recovery key, HSM master key**, hoặc export có phạm vi ảnh hưởng lớn, có thể cần:

- Hai approver **độc lập** theo chính sách.
- Key ceremony với operator và witness.
- Quorum/threshold hoặc split knowledge **nếu thiết bị và cơ chế hỗ trợ**.
- Quy tắc tách người **đề xuất, phê duyệt, thực thi và nhận**.

**Dual control khác split knowledge và M-of-N.** Hai click từ cùng một người hoặc hai account do một admin kiểm soát không bảo đảm độc lập. Không tự cắt đôi một AES key để tuyên bố đã có secret sharing an toàn.

### Đánh giá quyền gián tiếp

Một operator không có `ExportKey` nhưng có thể tự **sửa key policy, đổi IAM role, chuyển alias hoặc cấp grant** vẫn có thể gây lộ khóa qua các API khác. Thiết kế phải ngăn **self-escalation**, không chỉ chặn đúng một action tên “export”.

## 13. Quy trình phê duyệt trước khi export

Không nên có một nút “Download secret” luôn mở cho người quản trị.

~~~mermaid
flowchart TD
    A[Yêu cầu export có key ID/version, purpose, target] --> R[Đánh giá: có cần xuất vật liệu không?]
    R -->|Không| ALT[Remote operation / public key / new key + migration]
    R -->|Có| C[Kiểm tra policy exportability, risk tier]
    C -->|Không cho phép| DENY[Từ chối, ghi audit]
    C -->|Cho phép| OWNER[Key owner approval]
    OWNER --> SEC[Security approval độc lập nếu cần]
    SEC --> ID[Verify recipient identity, destination boundary, algorithm]
    ID --> CHECK[Preflight: metadata, key state, expected revision, TTL]
    CHECK -->|Không đạt| DENY
    CHECK -->|Đạt| EXPORT[Wrap / export bằng provider API được duyệt]
    EXPORT --> TRANS[Authenticated transport + integrity-protected package]
    TRANS --> IMPORT[Destination verify + unwrap/import]
    IMPORT --> AUDIT[Receipt, audit correlation, inventory + cleanup]
~~~

### Những trường request bắt buộc ràng buộc

- **Key ID và key material version**, không chỉ alias.
- **Key type, purpose, algorithm, environment và tenant scope**.
- **Destination principal/organization/partition**, resource và recipient key fingerprint.
- **Export mode** (`PUBLIC`, `WRAPPED`, `PROTECTED_BACKUP`, hoặc `RAW_EXCEPTION`).
- **Wrapping mechanism**, KEK/recipient public key và parameters.
- **Lý do và thời hạn**; nguồn phê duyệt và change request.
- **Số lần được thực hiện**, idempotency và trạng thái key dự kiến.
- **Điều kiện xử lý ở đích**: import, non-exportable, usage, audit, retention.
- **Yêu cầu cleanup/retirement** tại nguồn và nơi trung gian.

### Không tái sử dụng phê duyệt cho hành động khác

Một approval cho **public key export** không được dùng cho **private key export**. Một approval cho `key-v2` không được áp sang `key-v3` hoặc tenant khác.

Nên gắn approval với **canonical request digest** hoặc cơ chế bất biến tương đương, có identity, thời hạn và policy revision. Hash một chuỗi do client tự cung cấp **không chứng minh người duyệt có thẩm quyền**; nguồn approval phải được xác thực.

## 14. Bảo vệ người nhận: identity, trust và recipient binding

**Một khóa được wrap an toàn nhưng gửi cho sai recipient vẫn có thể là sự cố nghiêm trọng.**

### 14.1. Xác thực public key của recipient

Khi bọc cho recipient bằng RSA-OAEP/HPKE hoặc scheme hybrid, không đơn giản lấy một public key được gửi qua chat rồi tin tưởng. Cần xác minh:

- Recipient identity và quyền được tổ chức chấp thuận.
- Public key/certificate từ **kênh tin cậy** hoặc nguồn PKI/attestation được kiểm chứng.
- Certificate chain, key usage, expiry/revocation khi áp dụng.
- Key fingerprint/recipient key ID được ràng buộc vào request đã duyệt.
- Destination HSM/KMS có bảo vệ **private unwrap key** phù hợp không.

### 14.2. Xác thực symmetric wrapping KEK

Nếu sử dụng shared KEK giữa hai môi trường, phải biết **ai giữ KEK và cách phân phối ban đầu**. Một wrapped blob bị lấy cắp có thể bị unwrap bởi bất kỳ bên nào có **đúng KEK**.

Đừng đặt `wrappedKey` và **raw KEK** trong cùng một package.

### 14.3. Metadata phải được ràng buộc integrity

Các trường như `keyId`, `purpose`, `tenant`, `source`, `destination`, `algorithm`, `createdAt` có thể bị thay nếu chỉ nằm trong một JSON/YAML không được xác thực. Cần **manifest được xác thực** bằng chữ ký số, AEAD associated data hoặc cơ chế protocol đã được thiết kế đúng.

**AES-KW tự nó bảo vệ key payload**, nhưng không tự ràng buộc mọi trường manifest ngoài blob.

### 14.4. Transport encryption không thay thế package protection

mTLS/TLS bảo vệ một đoạn đường truyền khi cấu hình và trust đúng. Khi package được lưu ở queue, object store hoặc chuyển tiếp nhiều lần, **wrapped-key protection và manifest integrity** vẫn có giá trị độc lập.

## 15. Mẫu export package an toàn ở mức metadata

Một bản ghi xuất khóa có thể mang metadata như sau:

~~~yaml
schemaVersion: "1"
exportRequestId: "exp-2030-0048"
source:
  service: "billing-platform"
  environment: "production"
  keyId: "billing-dek-v5"
  keyVersion: "v5"
  keyType: "AES_256"
  purpose: "INVOICE_DATA_ENCRYPTION"
destination:
  organizationRef: "approved-partner-a"
  targetBoundaryRef: "recipient-hsm-partition-id"
  recipientWrappingKeyRef: "recipient-wrap-key-v2"
  recipientKeyFingerprintRef: "approved-fingerprint"
export:
  mode: "WRAPPED"
  mechanism: "AES-KW-or-provider-approved-mechanism"
  wrappedKeyEncoding: "base64"
  wrappedKey: "<protected-key-blob-placeholder>"
  manifestIntegrityReference: "signed-manifest-or-authenticated-context"
  requestExpiresAtUtc: "2030-06-01T12:00:00Z"
approval:
  ownerApprovalRef: "owner-approval-42"
  securityApprovalRef: "security-approval-19"
  sourcePolicyRevision: "key-policy-r27"
destinationPolicy:
  requestedUsage: ["Encrypt", "Decrypt"]
  desiredExportability: "NON_EXPORTABLE_AFTER_IMPORT"
  importReceiptRequired: true
audit:
  sourceEventRef: "source-provider-event"
  transferCorrelationId: "transfer-correlation-id"
~~~

**Đây là schema minh họa**, không phải định dạng import chuẩn có thể nạp trực tiếp vào mọi KMS/HSM. Các trường placeholder cần được thay bằng vật liệu và references theo cơ chế thật.

### Không coi YAML này là bằng chứng phê duyệt

Bản ghi chỉ **tham chiếu** approvals; một attacker có thể ghi bất kỳ chuỗi nào nếu nó không được kiểm soát. Executor phải tra cứu **nguồn approval đáng tin**, xác thực identity, request digest, trạng thái, phạm vi và TTL.

### Không ghi raw key vào package hoặc log

`wrappedKey` vẫn là dữ liệu cần kiểm soát theo chính sách, nhưng khác **plaintext key material**. Đừng thêm trường `rawKey` “để debug” hoặc lưu master/KEK bên cạnh bản bọc.

## 16. Java 11+: minh họa export một AES key ở dạng wrapped

Ví dụ dưới đây sử dụng JCA/JCE để tạo:

- Một **DEK AES-256** cần chuyển.
- Một **KEK AES-256 riêng**, dùng cơ chế **AES Key Wrap**.
- Một bản **wrapped key blob** thông qua `Cipher.WRAP_MODE`.
- Một bước **unwrap** và kiểm tra bằng cách mã hóa/giải mã dữ liệu thử với khóa nhận được.

**Đây là ví dụ về cryptographic wrapping trong JVM, không phải HSM-backed export**. Trong production, source/destination phải dùng provider/KMS/HSM có **key policy, audit, recipient authentication và quản trị KEK** phù hợp.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class WrappedKeyExportDemo {
    private static final SecureRandom RNG = new SecureRandom();

    static SecretKey newAes256Key() throws GeneralSecurityException {
        KeyGenerator kg = KeyGenerator.getInstance("AES");
        kg.init(256, RNG);
        return kg.generateKey();
    }

    static byte[] wrapKey(SecretKey dek, SecretKey kek)
            throws GeneralSecurityException {
        // "AESWrap" là tên transformation JCE được một số
        // provider hỗ trợ; cần xác minh mapping/mechanism.
        Cipher wrapping = Cipher.getInstance("AESWrap");
        wrapping.init(Cipher.WRAP_MODE, kek);
        return wrapping.wrap(dek);
    }

    static SecretKey unwrapKey(byte[] wrapped, SecretKey kek)
            throws GeneralSecurityException {
        Cipher unwrapping = Cipher.getInstance("AESWrap");
        unwrapping.init(Cipher.UNWRAP_MODE, kek);
        return (SecretKey) unwrapping.unwrap(
                wrapped, "AES", Cipher.SECRET_KEY);
    }

    static byte[] encryptDemo(SecretKey key, byte[] nonce,
                              byte[] aad, byte[] plaintext)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext);
    }

    static byte[] decryptDemo(SecretKey key, byte[] nonce,
                              byte[] aad, byte[] encrypted)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(encrypted);
    }

    public static void main(String[] args) throws Exception {
        SecretKey dek = newAes256Key(); // Khóa dữ liệu được xuất
        SecretKey kek = newAes256Key(); // Khóa wrapping riêng
        byte[] wrappedDek = wrapKey(dek, kek);

        // Bên nhận phải được cung cấp/quản lý đúng KEK qua
        // kênh riêng đã được xác thực; KHÔNG gửi raw KEK trong package.
        SecretKey importedDek = unwrapKey(wrappedDek, kek);

        byte[] nonce = new byte[12];
        RNG.nextBytes(nonce); // Nonce GCM mới cho phép mã hóa thử
        byte[] aad = "training-only/tenant-a/invoice"
                .getBytes(StandardCharsets.UTF_8);
        byte[] input = "test-invoice-data"
                .getBytes(StandardCharsets.UTF_8);

        byte[] encrypted = encryptDemo(dek, nonce, aad, input);
        byte[] output = decryptDemo(importedDek, nonce, aad, encrypted);

        System.out.println("Wrapped export created: "
                + (wrappedDek.length > 0));
        System.out.println("Imported key works: "
                + MessageDigest.isEqual(input, output));
        System.out.println("Wrapped bytes length: "
                + wrappedDek.length);

        // Không in SecretKey.getEncoded(), raw KEK, DEK,
        // plaintext, wrappedKey blob, token hoặc HSM PIN.
        // Production: key provenance, recipient binding,
        // manifest signature, IAM, rotation và audit riêng.
    }
}
~~~

**Kết quả dự kiến** (đối với provider hỗ trợ `AESWrap` và AES-256):

~~~text
Wrapped export created: true
Imported key works: true
Wrapped bytes length: 40
~~~

### Vì sao kết quả wrapped length thường 40 byte?

Với **AES Key Wrap RFC 3394** và một key payload 32 byte, output thường có **8 byte overhead** (tổng 40 byte), theo format AES-KW. Đây không phải kích thước cố định của mọi cơ chế wrapping hoặc mọi loại key.

### Ví dụ chứng minh được gì?

- `dek` và `kek` được sinh riêng.
- `Cipher.wrap` tạo một blob được bảo vệ dưới wrapping key.
- Recipient có đúng KEK có thể `unwrap` và dùng DEK khôi phục để decrypt dữ liệu mẫu.
- **Không cần in raw key bytes** để kiểm tra chức năng.

### Ví dụ không chứng minh được gì?

1. Không chứng minh DEK/KEK nằm trong HSM, vì code dùng provider trong JVM.
2. Không chứng minh một recipient bên ngoài đã được xác thực; code dùng **cùng KEK trong một JVM** để đơn giản hóa.
3. `AESWrap` không bảo vệ **manifest metadata** ngoài wrapped blob; production cần integrity/binding.
4. Không có dual control, approval, key ID/version, IAM, TTL, replay protection hay kiểm tra destination key policy.
5. Không thực hiện backup/import giữa hai token thật, không bảo đảm HSM A ↔ HSM B tương thích.
6. `Cipher.unwrap` có thể tạo key object **exportable trong JVM**; không coi kết quả đó là non-exportable.
7. Với provider hoặc key attributes khác, `wrap()` có thể bị từ chối; **không fallback sang raw export**.
8. AES-GCM đoạn test dùng **nonce tươi**; các lần mã hóa thật phải có quản lý nonce và giới hạn sử dụng tương ứng.

### Lưu ý về Java provider

Tên `AESWrap`, việc dùng `Cipher.WRAP_MODE` và khả năng xuất/unwrap một `SecretKey` là **phụ thuộc provider và key type**. Với PKCS#11, `SecretKey` có thể là **handle không xuất được**, và provider phải có cơ chế wrap hợp lệ. **Không ép lấy `getEncoded()`** chỉ để vượt lỗi `wrap()`.

## 17. Tại đích: import, validate và áp dụng policy trước khi sử dụng

**Xuất thành công ở nguồn không có nghĩa việc chuyển khóa đã an toàn.** Key phải được tiếp nhận bởi **đúng boundary đích** với thuộc tính và quyền phù hợp.

### Quy trình nhận khóa

1. **Xác thực package/source** và kiểm tra manifest integrity.
2. So khớp **request ID, key ID/version, purpose, algorithm, tenant và recipient** với approval.
3. Kiểm tra key material transfer **chưa hết hạn** và chưa được sử dụng trái chính sách.
4. Unwrap/import bằng API đích, tránh đưa plaintext key lên host nếu không cần.
5. Áp dụng attributes như **allowed operations, sensitivity, non-exportability và key owner** theo khả năng provider.
6. Kiểm tra **import receipt**, trạng thái và mapping từ source ID sang target ID.
7. Thử phép toán bằng dữ liệu test, không cần xuất raw key để “so sánh”.
8. Ghi audit và cập nhật **key inventory/lineage**.
9. Chỉ kích hoạt production sau kiểm thử và phê duyệt **pre-activation** phù hợp.
10. Dọn file tạm, hạn chế bản sao, thu hồi quyền export/transfer không còn cần.

### Gắn key identity ở target

Một key được import có thể nhận **provider resource ID hoặc PKCS#11 `CKA_ID` khác**. Cần lưu mapping:

~~~text
sourceKey: billing-dek-v5 @ source-kms
targetKey: imported-dek-47 @ recipient-hsm
materialReference: approved-transfer-event-0048
purpose: invoice-data-encryption
targetKeyVersion: import-v1
~~~

**Không dùng label trùng để suy ra key material trùng**. Kiểm thử cryptographic interoperability bằng operation hợp lệ và metadata đáng tin.

### Khóa import và provenance

Sau import, một HSM có thể đánh dấu key **non-exportable**, nhưng thực tế raw key đã từng tồn tại ở source hoặc trên đường chuyển. Thông tin **generated/imported/restored**, export history và các bản sao phải được giữ trong inventory để đánh giá rủi ro.

## 18. Key export trong envelope encryption: DEK và KEK

Đây là use case rất quan trọng trong **Key distribution**.

~~~mermaid
flowchart TD
    APP[Ứng dụng có quyền] --> REQ[Generate DEK / request wrap]
    REQ --> KMS[KMS/HSM giữ KEK]
    KMS -->|DEK plaintext tạm nếu API cho phép| ENC[AES-GCM encrypt dữ liệu]
    KMS -->|Wrapped DEK| STORE[(Ciphertext + wrapped DEK + key ID)]
    ENC --> STORE
    STORE --> READ[Reader được IAM cho phép]
    READ --> UNWRAP[KMS/HSM unwrap DEK]
    UNWRAP --> DEC[AES-GCM decrypt, verify tag/AAD]
    KEK[KEK non-exportable] --> KMS
~~~

### 18.1. Wrapped DEK có phải export không?

Ở góc độ phân phối key material, **wrapped DEK là một dạng khóa được đưa ra ngoài dưới bảo vệ mật mã**. Nó có thể được lưu trong database hoặc chuyển sang service khác **nếu** đã thiết kế đúng quyền unwrap, thuật toán và metadata.

### 18.2. Plaintext DEK từ `GenerateDataKey`

Một số managed KMS trả cả **plaintext DEK** và **encrypted/wrapped DEK**. Điều này cho phép ứng dụng thực hiện AES-GCM trên dữ liệu lớn mà không bắt KMS xử lý toàn bộ payload. Nhưng raw DEK có thể tồn tại trong **memory/cache** của ứng dụng.

Vì vậy cần giới hạn **TTL, phạm vi dùng, logging, crash dumps và đường giải mã offline**. **Disable KEK không tự xóa DEK đã nằm trong cache**.

### 18.3. Không cần export KEK khi thay KMS

Khi di chuyển từ `KEK-A` sang `KEK-B`, một kế hoạch có thể **unwrap DEK bằng KEK-A trong boundary an toàn và rewrap bằng KEK-B**, hoặc dùng API transcrypt/rewrap được hỗ trợ. Chuyển nguyên raw KEK-A thường **không phải phương án ưu tiên**.

### 18.4. Rewrap khác re-encrypt

- **Rewrap:** DEK không đổi; ciphertext dữ liệu thường không đổi.
- **Re-encrypt:** thay DEK trực tiếp mã hóa dữ liệu, tạo ciphertext/nonce/tag mới theo AEAD.

Nếu **DEK đã lộ**, rewrap cùng DEK dưới KEK mới **không khôi phục bí mật**. Cần đánh giá **thay DEK và re-encrypt**, kể cả ảnh hưởng dữ liệu lịch sử.

## 19. Export trong PKI, signing và key agreement

### 19.1. Công bố public verification key

Đối với ECDSA/RSA-PSS/Ed25519, **public key** có thể được xuất và phân phối qua certificate, JWKS hoặc kênh được xác thực. Bên nhận phải kiểm tra **chain/trust, key usage, key ID, algorithm và policy**.

**Public key có thể công khai nhưng không có nghĩa bất kỳ public key nào do bên gửi tự khai đều đáng tin.**

### 19.2. Private signing key non-exportable

Private signing key của CA, release-signing hoặc hóa đơn có giá trị cao thường nên sinh và giữ trong HSM với **key usage `Sign` và export policy nghiêm ngặt** theo risk tier.

Nếu phải chuyển sang HSM khác, đánh giá:

- Secure backup/clone nếu provider hỗ trợ.
- Cross-HSM wrapping có tương thích và được chính sách cho phép không?
- Tạo **signing key pair mới**, cập nhật public key/chứng thư/trust và ngừng key cũ.
- Retention của **public verification material** cho chữ ký lịch sử.

**Certificate renewal dùng cùng private key không phải private-key rotation**. **Export public certificate không phải export private key**.

### 19.3. JWT signing key và JWKS

Trong OAuth/OIDC/JWT, public keys có thể được phân phối qua **JWKS**. Bên kiểm tra cần ràng buộc nguồn trust và thuật toán, không tin vào bất kỳ URL hoặc `kid` do attacker đưa trong token.

Export private signing key để chạy nhiều issuer thường tăng blast radius; cân nhắc **signing service tập trung** hoặc key pair khác theo tenant/issuer và design.

### 19.4. ECDH/X25519

Giao thức ECDH thường trao đổi **public key có xác thực**, không gửi private agreement key cho peer. **ECDH thuần túy không tự chống MITM**; phải xác thực peer và dùng KDF/key schedule phù hợp.

Với **ephemeral ECDHE**, private key phiên nên được tạo và loại bỏ theo giao thức; **không export/sao lưu dài hạn** chỉ để “truy vết handshake”.

### 19.5. HMAC secret với đối tác

HMAC là **symmetric authentication**: sender và receiver thường cùng biết key. Khi cần chia sẻ, phải dùng provisioning path được phê duyệt, key version riêng theo đối tác, thời hạn, anti-replay và rotation. Không dùng public key/certificate export để “thay” việc bảo vệ HMAC secret.

## 20. Backup, replication và disaster recovery không đồng nghĩa export raw key

Một key non-exportable vẫn có thể có chiến lược **backup/DR** theo cơ chế riêng của HSM/KMS. Phải xác định **đúng giới hạn**.

| Cơ chế | Mục tiêu | Điều cần kiểm tra |
| --- | --- | --- |
| HSM protected backup | Khôi phục key sau lỗi thiết bị | Trust domain, recovery roles, firmware, media, audit |
| HSM cluster replication | Availability giữa các node | Lỗi xóa nhầm có lan tới replica không |
| Cloud KMS multi-region replication | Sử dụng key ở nhiều vùng theo provider | Key identity, policy, quyền, consistency và product limits |
| Key-wrapping export/import | Chuyển material đến recipient cho phép | Wrapping mechanism, recipient binding, import policy |
| Raw secret backup | Tạo bản sao secret ngoài boundary | Risk tier rất cao; chỉ khi policy cho phép và có kiểm soát |
| Public certificate archive | Giữ khả năng verify lịch sử | Không chứa private key, cần provenance/trust metadata |

### HA không thay thế backup

HSM cluster có thể giúp khắc phục lỗi node, nhưng nếu operator xóa nhầm key và thay đổi được replicate, **các node cùng mất key**. Phải có recovery strategy chống **lỗi logic**, không chỉ lỗi phần cứng.

### Khôi phục cần thử nghiệm

Restore drill nên dùng **test key/data** và xác nhận key được import đúng purpose/attributes, có thể thực hiện phép toán cần thiết, audit đầy đủ, và **không cần tải raw key ra cho người vận hành**.

### Destruction phải xét bản sao

Khi hủy key, phải kiểm tra **backup, replica, wrapped key, DR media, cache** và retention. **Xóa alias/record metadata không đồng nghĩa key material đã được hủy**.

## 21. Lifecycle sau khi export: ownership, rotation và thu hồi

Một lần export có thể tạo thêm **key copies và trách nhiệm quản trị**.

### 21.1. Trước activation

Ở đích, key nên ở trạng thái **pre-activation** đến khi xác minh:

- Đúng recipient, owner và purpose.
- Đúng algorithm, key size, key usage và export policy.
- Đã kiểm tra IAM, restrictions và negative tests.
- Đã có backup/restore plan và audit correlation.
- Không cần giữ bản sao plaintext trung gian.

### 21.2. Khi active

Hai bên cần biết **ai là owner/custodian**, ai được `Encrypt`, `Decrypt`, `Sign` hoặc `GenerateMac`, cryptoperiod và incident contact. Nếu xuất cùng một raw key cho nhiều bên, **compromise ở bất kỳ bên nào** có thể ảnh hưởng toàn bộ nơi dùng key đó.

### 21.3. Rotation

Nếu secret shared với đối tác, đổi khóa ở một bên **không tự đổi ở bên kia**. Cần phối hợp key version, cutover, thời hạn chấp nhận legacy, retry và emergency revoke.

### 21.4. Thu hồi

**Revoke quyền truy cập** tại source không làm biến mất raw key đã được export. Nếu key bí mật đã nằm tại recipient hoặc bị sao chép, cần **thay key material** và xử lý trust/dữ liệu/chữ ký liên quan.

### 21.5. Hủy

Không hủy source material trước khi xác minh target import, backup/DR và mọi phụ thuộc được xử lý. Ngược lại, cũng không giữ một nguồn raw export không hạn định mà thiếu owner hoặc mục đích.

## 22. Audit: phải chứng minh điều gì về Key export?

**Key export là một sự kiện có thể thay đổi vĩnh viễn nơi vật liệu khóa tồn tại**, nên audit phải đáng tin cậy và đủ liên kết với source/recipient.

### Event schema minh họa

~~~yaml
schemaVersion: "1"
eventType: "KEY_EXPORT_COMPLETED"
eventId: "evt-2030-0912"
requestId: "exp-2030-0048"
source:
  keyId: "billing-dek-v5"
  version: "v5"
  providerResourceRef: "source-key-resource"
  exportPolicyRevision: "policy-r27"
destination:
  organizationRef: "approved-partner-a"
  targetBoundaryRef: "recipient-hsm-partition-id"
  wrappingKeyRef: "recipient-wrap-key-v2"
action:
  exportMode: "WRAPPED"
  mechanism: "AES-KW"
  result: "SUCCESS"
  recipientReceiptRef: "import-receipt-id"
authorization:
  requestedBy: "source-custodian-a"
  ownerApprovalRef: "owner-approval-42"
  securityApprovalRef: "security-approval-19"
occurredAtUtc: "2030-05-20T09:00:00Z"
auditCorrelationId: "transfer-correlation-id"
~~~

Đây là **định dạng ví dụ**, không phải schema event dùng chung cho mọi KMS/HSM. Không ghi wrapped key blob hay bất kỳ secret nếu không cần cho mục đích audit; chỉ giữ **tham chiếu** tới artifact trong kho bảo vệ.

### Các event cần nối lại

1. Yêu cầu export được tạo và scope được đóng băng.
2. Owner/security approval theo policy.
3. Kiểm tra recipient certificate/fingerprint và target capability.
4. Provider xuất **public/wrapped/protected backup** hoặc từ chối.
5. Package được vận chuyển tới endpoint cụ thể.
6. Destination verify, import và đặt key attributes.
7. Recipient thử phép toán được phép, gửi receipt.
8. Cleanup file tạm và thu hồi grant/role export.
9. Key inventory cập nhật source–destination relationship.
10. Sự kiện rotate, suspend, revoke hoặc destroy sau này.

**Source audit success không thay thế receipt của recipient**. Nếu import thất bại, phải biết package nào đang nằm ở đâu và quyền retry ra sao.

### Không ghi raw key trong audit

Ngay cả khi auditor yêu cầu “bằng chứng key đã chuyển”, cách đúng là **provider event, key ID/version, receipt, checksum/manifest reference và test operation**. Không đưa DEK/private key bytes vào log hoặc ticket.

## 23. Incident response khi export sai phạm

Các tình huống thường gặp:

- Raw private key được tải về bởi người không được duyệt.
- Wrapped secret được gửi cho **sai recipient**, nơi có khả năng unwrap.
- Wrapping KEK hoặc private unwrap key của recipient bị compromise.
- Package có metadata sai hoặc bị attacker thay đổi.
- Bản secret tồn tại trong log, CI/CD artifact hoặc backup không kiểm soát.
- Operator dùng quyền cao để tạm bật exportability rồi khôi phục policy.
- Đích import sai usage hoặc tự cấp quyền `Sign/Decrypt` vượt scope.

### Runbook khái niệm

1. **Nhận diện:** key ID/version, nguồn, recipient, export mode, wrapping key, actors, thời gian và tình trạng transfer.
2. **Cô lập:** thu hồi quyền/credential export, chặn API và đường vận chuyển, bảo vệ audit.
3. **Đánh giá bản sao:** raw secret đã xuất hiện ở đâu? Có nằm trong memory/log/file/backup/recipient không?
4. **Đánh giá khả năng unwrap:** đối thủ có wrapped blob **và** KEK/private unwrap key hoặc đường oracle không?
5. **Liệt kê phụ thuộc:** ciphertext, wrapped DEK, chữ ký, HMAC messages, dữ liệu backup và các bên dùng key.
6. **Thay material khi cần:** generate key mới, update IAM, cutover, rewrap hoặc re-encrypt đúng loại sự cố.
7. **Thu hồi trust:** với signing key, cập nhật certificate/JWKS/verification policy, đánh giá chữ ký đã phát.
8. **Kiểm tra legacy:** không hủy key cũ khi còn dữ liệu phải recover; trường hợp key lộ cần quyền legacy cực hẹp và incident policy.
9. **Notification và hậu kiểm:** thông báo tổ chức/đối tác theo quy trình, ghi toàn bộ evidence và cải thiện kiểm soát.
10. **Audit reconciliation:** xác nhận không còn export/unwrapping trái policy sau khi cô lập.

### Nhận diện đúng loại rủi ro

**Wrapped key blob bị lộ** không đồng nghĩa raw key chắc chắn đã bị lộ. Nhưng nếu kẻ tấn công giữ **đúng unwrap key** hoặc có quyền API unwrap, nguy cơ có thể tương đương raw key.

**Private key đã raw-export** không thể trở về trạng thái “chưa từng xuất” bằng một lệnh import/non-exportable. Nếu không chứng minh được các bản sao được kiểm soát, phải xem xét **rotation và tác động chữ ký lịch sử**.

### Rewrap không chữa được raw DEK compromise

Nếu đối thủ đã biết DEK plaintext, việc bọc lại **cùng DEK** dưới KEK mới không xóa khả năng giải mã ciphertext cũ. Cần cân nhắc **thay DEK và re-encrypt dữ liệu**, cùng đánh giá bản sao đã bị lấy.

## 24. Case study: chuyển DEK qua đối tác xử lý hóa đơn

### Bối cảnh

Hệ thống Billing có các invoice đã mã hóa bằng **DEK AES-256**. Một đối tác được phép xử lý một tập dữ liệu giới hạn trong thời gian hợp đồng. Nhóm phát triển đề xuất **gửi DEK qua chat** để đối tác giải mã.

Đề xuất này **không đáp ứng mục tiêu bảo vệ khóa**, vì không kiểm soát recipient, retention, key version và nơi xuất hiện raw DEK.

### Thiết kế cải thiện

1. **Key owner** xác nhận đối tác được nhận dữ liệu gì, mục đích và thời hạn.
2. **Application/data owner** chỉ đưa ra đúng những invoice trong scope; không chia sẻ DEK toàn tenant nếu chỉ cần một số record.
3. **Security reviewer** xác định đối tác có HSM/KMS hoặc public wrapping key đáng tin không.
4. **Custodian** tạo DEK riêng cho phạm vi đối tác hoặc **rewrap DEK được phép**; không export KEK chính của doanh nghiệp.
5. **Package** gồm ciphertext, wrapped DEK, đúng key/algorithm metadata và manifest được xác thực.
6. **Destination custodian** import vào nơi bảo vệ, giới hạn usage và cung cấp receipt.
7. **Ứng dụng đối tác** giải mã trong phạm vi đã duyệt, có audit và không log DEK.
8. **Khi hợp đồng kết thúc**, hai bên xử lý retention, quyền truy cập và dữ liệu đã tạo theo chính sách.

### Vì sao không nên gửi một DEK dùng cho toàn bộ tenant?

Một DEK per-tenant có thể mở được nhiều record hơn phạm vi đối tác cần. Khi xuất raw key hoặc cho recipient unwrap, nguy cơ rò rỉ vượt dữ liệu hợp đồng. Giải pháp tốt hơn có thể là **re-encrypt tập invoice được chia sẻ dưới DEK riêng** hoặc cung cấp dữ liệu qua API có kiểm soát.

### Bài học

**Key export phải theo nguyên tắc phân phối tối thiểu cả về secret lẫn dữ liệu**: đúng recipient, đúng key, đúng phạm vi và đúng thời gian. Wrapping giúp bảo vệ vận chuyển, nhưng **authorization của dữ liệu** vẫn cần kiểm soát độc lập.

## 25. Case study: di chuyển private signing key khỏi HSM cũ

### Bối cảnh

Doanh nghiệp có private signing key `invoice-signing-v3` trong HSM cũ, được cấu hình **non-exportable**. Thiết bị sẽ ngừng hỗ trợ, và nhóm muốn chuyển sang HSM mới mà **giữ nguyên private key**.

### Những lựa chọn cần đánh giá

| Phương án | Có thể phù hợp? | Rủi ro/điều kiện |
| --- | --- | --- |
| **Protected HSM migration/backup** | Nếu vendor hỗ trợ | Phải đúng trust domain, firmware, role, approval và audit |
| **Cross-HSM wrapped export** | Chỉ nếu key attributes/mechanism cho phép | Key non-exportable có thể **không cho phép** đường này |
| **Raw private-key export** | Không phù hợp với chính sách non-exportable đã cam kết | Có thể không thể thực hiện bằng API; rủi ro bản sao |
| **Sinh signing key pair mới** | Thường là hướng khả thi khi không thể chuyển material | Cần cấp chứng thư, cập nhật verifier/trust và cutover |
| **Remote signing qua HSM cũ tạm thời** | Có thể là giai đoạn chuyển tiếp | Rủi ro availability, support, latency và kế hoạch retire |

### Kế hoạch nếu chọn key pair mới

1. Key owner phê duyệt vòng đời, mục đích và thời điểm chuyển.
2. Key custodian sinh **private/public pair mới trong HSM mới**.
3. Phân phối **public key/chứng thư mới** qua trust channel.
4. Kiểm thử verifier xử lý cả chữ ký v3 lịch sử và chữ ký v4 mới theo chính sách.
5. Chuyển workload ký mới sang v4 và chặn new-sign bằng v3.
6. Giữ thông tin **verification của v3** phục vụ chữ ký lịch sử.
7. Chỉ hủy vật liệu v3 sau khi đáp ứng retention, compliance và quy trình phê duyệt.

### Tại sao “giữ nguyên private key bằng mọi giá” có thể sai?

Việc giữ nguyên khóa có thể tránh thay đổi verifier, nhưng nếu phải **phá chính sách non-exportability** hoặc đưa raw private key ra host, rủi ro có thể vượt lợi ích. **Tạo key mới, quản trị certificate/JWKS và hỗ trợ trust transition** thường phù hợp hơn.

## 26. Sai lầm thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Gọi export public key là export private key | Nhầm rủi ro và chính sách | Phân loại rõ vật liệu |
| Chuyển raw DEK qua chat/email | Mất kiểm soát bản sao và recipient | Wrapped export, authenticated delivery |
| Gửi wrapped key cùng raw KEK | Bọc khóa mất ý nghĩa bảo mật | Quản trị KEK độc lập |
| Dùng cùng raw key cho dữ liệu, HMAC và wrapping | Tăng blast radius và cross-protocol risk | Tách purpose/key material |
| Dùng AES-ECB tùy ý làm “key wrapping” | Thiếu format và integrity chuẩn | AES-KW/KWP hoặc provider mechanism chuẩn |
| Coi AES-KW tự bảo vệ manifest metadata | Attacker có thể thay các trường ngoài blob | Chữ ký/AEAD AAD hoặc authenticated protocol |
| Lấy public wrapping key từ kênh không xác thực | Có thể bọc cho attacker | Verify certificate/fingerprint/recipient |
| Coi TLS bảo đảm package an toàn mãi mãi | File có thể lưu/chuyển tiếp sau TLS | Wrapping và manifest integrity |
| Bật `extractable=true` cho mọi key HSM | Mở đường xuất vật liệu trái chính sách | Non-exportable mặc định cho key critical |
| Dùng `getEncoded()` để bypass HSM policy | Có thể làm lộ raw secret | Dùng provider APIs, không ép raw export |
| Đọc `CKA_SENSITIVE` rồi cho rằng key không wrap được | Hiểu sai attribute | Xác minh `CKA_EXTRACTABLE` và mechanism |
| Dùng protected backup như file export tự do | Vượt boundary/khó restore | Vendor backup/restore policy |
| Export key nhưng không kiểm tra import | Không có bằng chứng recipient dùng được | Receipt + thử operation hợp lệ |
| Đặt key non-exportable sau import rồi tuyên bố chưa từng lộ | Bản sao cũ vẫn có thể tồn tại | Provenance và cleanup |
| Quên HSM PIN/credential trong script | Secret nằm trong repo/log/history | Credential management, MFA/PAM |
| Chỉ ghi source export success | Không biết package đã tới đâu | Source–transfer–destination audit |
| Dùng label/alias làm định danh key duy nhất | Dễ chuyển nhầm material/version | Key ID/version/fingerprint |
| Cho admin tự sửa policy để export | Self-escalation | Dual control, IAM boundary, audit |
| Coi revoke access xóa raw secret đã phát | Recipient vẫn có bản sao | Rotation, recovery/incident plan |
| Chỉ rewrap khi raw DEK đã lộ | Dữ liệu vẫn giải mã được bằng DEK cũ | Re-encrypt và đánh giá lịch sử |
| Hủy source trước khi thử target restore | Mất key hoặc dữ liệu không thể phục hồi | Migration preflight/DR validation |
| Không xét backup/replica của secret | Vật liệu tiếp tục tồn tại ngoài inventory | Lineage và retention |
| Export private signing key để scale verifier | Không cần thiết, tăng rủi ro | Phân phối public key/verify service |
| Chuyển ECDH private key cho peer | Sai mô hình agreement | Chỉ trao public key có xác thực |
| Không kiểm tra key type của provider | Wrapped format không tương thích | Compatibility test + fallback an toàn |

## 27. Checklist kiểm thử và đánh giá Key export

### A. Trước export

1. **Purpose:** Có bằng chứng nghiệp vụ buộc phải export key material thay vì chỉ dùng key handle/API?
2. **Key classification:** Key là public, DEK, KEK, HMAC, signing, agreement hay recovery?
3. **Exportability:** Key attributes và policy cho phép `PUBLIC`, `WRAPPED`, backup hay raw exception?
4. **Provenance:** Key được sinh trong HSM, import hay restore; từng có bản sao ngoài boundary không?
5. **Owner/custodian:** Có người chịu trách nhiệm phê duyệt, thực thi và nhận?
6. **Approval:** Có dual control/separation of duties khi risk tier yêu cầu?
7. **Exact scope:** Approval ràng buộc key ID/version, tenant, purpose, algorithm, target và thời hạn?
8. **Recipient:** Public wrapping key/certificate hoặc shared KEK đã được xác thực qua nguồn tin cậy?
9. **Algorithm:** Wrapping mechanism/format hỗ trợ bởi cả source và destination?
10. **IAM:** Exporter không thể tự cấp quyền raw export hoặc sửa policy/audit để bypass?
11. **Business data:** Có đang export một key mở được nhiều dữ liệu hơn phạm vi người nhận cần?

### B. Trong transfer và import

12. **No raw logging:** Không có key, KEK, HSM PIN, token hoặc plaintext trong log, trace, ticket.
13. **Boundary:** Đường wrap/unwrap được thực thi trong nơi bảo vệ theo thiết kế; không có file tạm plaintext ngoài chính sách?
14. **Package integrity:** Key payload và manifest metadata được xác thực đúng?
15. **Recipient binding:** Đúng target partition/account, key fingerprint, operation và quyền import?
16. **Transport:** Kênh có xác thực và bảo mật; package lưu ở queue/storage vẫn được bảo vệ?
17. **Replay:** Request hết hạn hoặc dùng lại bị từ chối theo workflow?
18. **Import attributes:** Key tại đích có usage, non-exportability, owner và policy phù hợp?
19. **Receipt:** Có import receipt, key ID mapping và phép toán thử hợp lệ mà không in raw material?
20. **Error path:** Khi wrap/import lỗi, không tự fallback sang plaintext export hoặc bỏ integrity check.

### C. Sau export

21. **Inventory:** Có bản đồ source–destination, number of copies, key lineage và cryptoperiod?
22. **Audit:** Có request/approval/source provider/transport/destination events liên kết?
23. **Cleanup:** File tạm, transfer tokens và quyền elevated export đã được thu hồi?
24. **Rotation:** Các bên biết key version, cutover, legacy period và incident contact?
25. **Backup/DR:** Có chiến lược khôi phục và retention không làm tăng secret copies không kiểm soát?
26. **Revocation:** Hiểu rằng revoke ở source không tự vô hiệu raw copy tại destination?
27. **Compromise:** Runbook xử lý wrapped key lộ, unwrap key lộ, raw key lộ và credential bị lấy?
28. **Data migration:** Nếu thay DEK/KEK, có phân biệt rewrap với re-encrypt?
29. **Signing trust:** Nếu key ký thay mới, public verifier/chứng thư/JWKS và chữ ký lịch sử vẫn được xử lý?
30. **Destruction readiness:** Chỉ hủy key tại nguồn sau khi import/restore và phụ thuộc đã được xác minh?
31. **Negative tests:** Sai recipient, sai key ID/version, hết hạn, thay manifest, thiếu approval, export forbidden đều phải bị chặn.
32. **Review:** Có thể chứng minh **key nào đã đi đâu, bằng cơ chế nào, ai phê duyệt, còn bao nhiêu bản sao và ai được dùng**?

## 28. Ghi nhớ và nguyên tắc ra quyết định

**Key export** là việc đưa khóa hoặc một biểu diễn của khóa qua **ranh giới quản lý/bảo vệ**. Không được đánh đồng **public-key export**, **raw secret export**, **wrapped-key export** và **protected HSM backup**. Với private signing key hoặc KEK có phạm vi ảnh hưởng lớn, **non-exportable trong HSM/KMS** thường là kiểm soát quan trọng; không nên cố vượt kiểm soát vì sự tiện lợi. Nếu thật sự cần phân phối secret, phải dùng **wrapping mechanism chuẩn, recipient authentication, manifest integrity, IAM least privilege, approvals phù hợp và audit có thể đối chiếu từ nguồn đến đích**.

Trong **envelope encryption**, DEK có thể tồn tại dưới dạng plaintext tạm và **wrapped DEK** được lưu cùng ciphertext, trong khi KEK vẫn nằm trong KMS/HSM. **Rewrap DEK** khác **re-encrypt dữ liệu bằng DEK mới**; nếu raw DEK đã bị lộ, chỉ thay KEK không giải quyết được sự cố. Với **chữ ký số và key agreement**, thường chỉ cần phân phối **public key có xác thực**, không phải private key.

Một quy trình Key export tốt phải trả lời chính xác: **Khóa nào? Dạng xuất nào? Ai được quyết định? Gửi cho ai? Bảo vệ bằng gì? Đích dùng và lưu thế nào? Có bằng chứng gì? Khi nào bản sao được thu hồi hoặc hủy?** Mọi câu trả lời phải nhất quán với **vòng đời khóa, separation of duties, KMS/HSM, key inventory, rotation, incident response và retention**.
