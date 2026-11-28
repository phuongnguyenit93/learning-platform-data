# DEK encryption: Mã hóa và bảo vệ Data Encryption Key trong envelope encryption

Một dịch vụ thanh toán lưu hàng triệu chứng từ, hóa đơn và hồ sơ khách hàng. Nội dung mỗi chứng từ được mã hóa bằng AES-GCM với một **Data Encryption Key (DEK)** riêng. Nếu ứng dụng ghi DEK bản rõ cạnh ciphertext, ai đọc được database có thể giải mã toàn bộ dữ liệu tương ứng, dù thuật toán AES-GCM được dùng đúng. Giải pháp phổ biến là **mã hóa/bọc DEK bằng một Key Encryption Key (KEK)** được quản lý độc lập, rồi chỉ lưu **wrapped/encrypted DEK** cùng bản mã.

**DEK encryption** trong chương **Envelope encryption** là bước **bảo vệ chính DEK** trước khi lưu hoặc phân phối, thường bằng một KEK, KMS/HSM hoặc public key của bên nhận. Cần phân biệt hai phép toán:

- **Data encryption:** dùng **DEK** để mã hóa dữ liệu nghiệp vụ thành ciphertext.
- **DEK encryption / key wrapping:** dùng **KEK** hoặc cơ chế bọc khóa được phê duyệt để bảo vệ DEK, tạo **encrypted DEK (EDK)** hay **wrapped DEK**.

Hai lớp bảo vệ này có **key material, quyền truy cập, nonce/IV, metadata, thuật toán và vòng đời khác nhau**. Đổi KEK không tự đổi DEK. Mã hóa DEK không tự bảo vệ dữ liệu nếu ứng dụng cho mọi caller tùy ý Unwrap, hoặc nếu plaintext DEK bị lưu vào log/cache không kiểm soát.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, nội dung này liên kết mật mã đối xứng, bất đối xứng, KMS/HSM, kiểm soát truy cập, kiểm toán và vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy**. Mục tiêu là thiết kế một envelope giải mã được trong nhiều năm mà vẫn giới hạn rủi ro khi một lớp khóa hoặc một dịch vụ gặp sự cố.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt rõ **DEK, KEK, plaintext DEK, encrypted DEK, key identifier và key version**; giải thích vì sao DEK phải được bảo vệ riêng với ciphertext.
2. Mô tả luồng **Encrypt payload → Protect DEK → Store envelope → Unprotect DEK → Decrypt payload**, trong đó có KMS/HSM và IAM.
3. Chọn cơ chế bảo vệ DEK phù hợp: **KMS GenerateDataKey/Encrypt, AES-KW/AES-KWP, AES-GCM có AAD, RSA-OAEP hoặc KEM/DEM**.
4. Thiết kế envelope với **algorithm ID, format version, key ID/version, nonce/IV, ciphertext/tag, wrapped DEK và authenticated metadata**.
5. Phân tích **nonce uniqueness, AAD, key confusion, tenant isolation, key rotation, rewrap và re-encrypt**.
6. Hiểu ví dụ Java 17 về **AES-GCM cho payload và AES-GCM riêng cho DEK**, có kiểm tra tampering và thực hiện rewrap.
7. Thiết lập **least privilege, key caching/TTL, audit, backup/restore và phản ứng khi KEK hoặc DEK bị lộ**.

## 2. DEK encryption đứng ở đâu trong envelope encryption?

### 2.1. Hai lớp khóa, hai ranh giới tin cậy

~~~mermaid
flowchart LR
    P["Plaintext của record"] -->|"AES-GCM với DEK"| C["Payload ciphertext + tag"]
    D["DEK ngẫu nhiên"] -->|"AES-GCM / AES-KW / KMS wrap dùng KEK"| E["Encrypted DEK / Wrapped DEK"]
    K["KEK trong KMS/HSM"] --> E
    C --> S[("Envelope trong database")]
    E --> S
    M["Nonce, AAD schema, key ID/version"] --> S
    K -. "Thông thường không lưu bản rõ tại DB" .-> S
~~~

Một luồng đơn giản:

~~~text
DEK <- CSPRNG / KMS GenerateDataKey        (32 byte nếu chọn AES-256)

payloadCiphertext = AEAD_Encrypt(
    key = DEK,
    nonce = payloadNonce,
    plaintext = businessData,
    aad = contentAAD
)

encryptedDek = ProtectKey(
    wrappingKey = KEK,
    plaintextKey = DEK,
    algorithm = approvedKeyWrapAlgorithm,
    context = authorizedKeyContext
)

Database lưu:
    payloadCiphertext + authenticationTag
    payloadNonce
    encryptedDek + wrap metadata (nonce/tag nếu cần)
    content algorithm, wrapping algorithm
    key ID/version, tenant/record/format metadata

Database KHÔNG lưu plaintext DEK hoặc KEK.
~~~

**KEK không bắt buộc là AES key**: một public encryption key RSA có thể bảo vệ một DEK bằng RSA-OAEP; một giao thức KEM/DEM có thể đóng gói key material đối xứng. Tuy nhiên với mô hình KMS nội bộ, một **symmetric KEK** do KMS/HSM quản lý là lựa chọn rất thường gặp.

### 2.2. Bảng phân biệt các đối tượng

| Đối tượng | Công dụng | Có thể lưu cùng ciphertext? | Bảo vệ cần có |
|---|---|---|---|
| **DEK bản rõ** | AES-GCM Encrypt/Decrypt payload | **Không nên** lưu thường trực | Secret memory lifecycle, quyền sử dụng, không log |
| **EDK / wrapped DEK** | Dạng đã được bảo vệ của DEK | **Có thể**, theo thiết kế | Integrity/context, KEK access control, metadata |
| **KEK** | Encrypt/Wrap hoặc Decrypt/Unwrap DEK | **Không** ở dạng bản rõ với database đó | KMS/HSM, key policy, IAM, backup có kiểm soát |
| **Payload ciphertext/tag** | Dữ liệu đã mã hóa và xác thực | **Có** | Authenticated decryption, access control, retention |
| **Nonce/IV** | Tham số dùng cùng thuật toán AEAD/wrapping | **Có**, thường không bí mật | Phải đúng kích thước và không tái sử dụng với cùng key khi thuật toán yêu cầu |
| **AAD / encryption context** | Ràng buộc tenant/record/purpose/format | **Có thể** lưu/tái tạo | Encode nhất quán, so với nguồn tin cậy, không thay IAM |
| **Key ID/version** | Chọn chính xác KEK đã bảo vệ DEK | **Có** | Registry integrity, namespace, không nhầm alias động |
| **Key alias** | Chọn khóa hiện tại cho operation mới | Có thể ghi làm thông tin phụ | Không thay thế immutable key reference của bản mã lịch sử |

**EDK không phải một “DEK mới”**. Nó là biểu diễn được bảo vệ của **cùng key material**, thường cần được giải mã trước khi dùng để mở payload. Trong một số API/provider, wrapped key là một blob opaque có định dạng nội bộ; ứng dụng không nên tự giải thích từng byte của blob đó.

### 2.3. Khi nào cần DEK theo bản ghi, tập tin hoặc lô?

**Không có một kích thước DEK scope đúng cho mọi hệ thống.**

| Chiến lược | Ưu điểm | Rủi ro/chi phí |
|---|---|---|
| **Một DEK cho mỗi record** | Khoanh vùng sự cố tốt; dễ cryptographic erasure theo record khi mọi bản sao được xử lý | Nhiều EDK, KMS requests và metadata |
| **Một DEK cho mỗi object/file** | Hợp lý với object storage, dễ tổ chức envelope | Với file rất lớn phải quản lý chunk/nonce và kích thước |
| **Một DEK cho mỗi batch/segment** | Giảm overhead khi volume lớn | Một DEK lộ ảnh hưởng nhiều bản ghi; cần nonce/state toàn bộ batch |
| **Một DEK lâu dài cho nhiều tenant** | Ít keys hơn | **Không nên** khi cần tenant isolation, blast radius nhỏ |

Chọn scope dựa vào **phân loại dữ liệu, mức rủi ro, tần suất truy cập, giới hạn API KMS, số lần AES-GCM Encrypt, khả năng rotation và yêu cầu xóa dữ liệu**. Không dùng một DEK cho mọi tenant chỉ để tiết kiệm số lần wrap.

## 3. Các thuộc tính an toàn bắt buộc khi mã hóa DEK

**Bọc DEK không chỉ có nghĩa “dùng một thuật toán mã hóa nào đó chạy qua 32 byte”.** Một key-wrap mechanism an toàn phải bảo vệ bí mật, hỗ trợ kiểm tra tính toàn vẹn theo thiết kế, tránh nhầm mục đích khóa và có cách xác thực ngữ cảnh.

### 3.1. Confidentiality và integrity

- **Confidentiality:** ai chỉ đọc EDK không được suy ra DEK nếu chưa có KEK và quyền sử dụng hợp lệ.
- **Integrity:** khi EDK, nonce, thuật toán hoặc authenticated context bị sửa, thao tác Unwrap phải phát hiện và không trả key material sai làm dữ liệu đi vào trạng thái không xác định.
- **Binding:** không thể tùy ý lấy EDK của tenant A gắn sang record tenant B mà hệ thống vẫn cho sử dụng như một bản ghi hợp lệ.
- **Purpose separation:** KEK dành cho wrapping không bị ứng dụng dùng tùy tiện làm payload DEK, HMAC key hoặc signing key.
- **Recoverability:** đúng key version và metadata được giữ đủ lâu để mở ciphertext lịch sử theo retention.

Một cơ chế như **AES-GCM** có authentication tag; **AES-KW/AES-KWP** là cơ chế key wrapping được chuẩn hóa với kiểm tra tính toàn vẹn theo đặc tính của nó. **AES-ECB tự chế, XOR với KEK hoặc AES-CBC không có authentication** không phải cơ chế bọc DEK nên chọn cho hệ thống mới.

### 3.2. Nonce/IV là theo từng lớp và từng key

Nếu cả payload và DEK đều được mã hóa bằng AES-GCM:

~~~text
payloadNonce: dùng với DEK, riêng cho mỗi payload encryption
wrapNonce:    dùng với KEK, riêng cho mỗi DEK wrapping operation

(DEK, payloadNonce) không được lặp khi Encrypt payload.
(KEK, wrapNonce)    không được lặp khi Encrypt DEK.
~~~

Kích thước nonce 96 bit thường được dùng với AES-GCM, nhưng **random nonce từ CSPRNG chỉ cho xác suất trùng thấp chứ không bảo đảm tuyệt đối**. Một KEK bọc hàng tỷ DEK trên nhiều replica phải có **nonce strategy và giới hạn số invocation** phù hợp. Không dùng nonce cố định cho wrap, không dùng một counter bị reset sau restore mà không có quản lý toàn hệ thống.

**AES-KW/AES-KWP không dùng cùng cơ chế nonce ngẫu nhiên của AES-GCM**. Không tự “thêm IV GCM” vào API AESWrap hoặc giả định mỗi thuật toán có metadata giống nhau.

### 3.3. Authenticity của metadata

Thông tin **tenantId, recordId, DEK reference, KEK ID/version, wrapAlgorithm, contentAlgorithm và formatVersion** ảnh hưởng đến cách resolve key hoặc cách giải mã. Chúng cần có **schema chuẩn hóa và ràng buộc tính toàn vẹn** trong appropriate cryptographic layer.

**AAD không được mã hóa, nhưng được xác thực** bởi AEAD. Nếu ứng dụng đưa **tenantId từ body request** vào AAD mà không so với tenant của authenticated principal, AAD có thể hợp lệ trong khi **authorization vẫn sai**.

Trong các hệ thống cho phép **rewrap DEK mà không re-encrypt payload**, cần tách:

- **Content AAD:** chỉ những thông tin sẽ giữ nguyên nếu payload ciphertext giữ nguyên, ví dụ tenant, record ID, content algorithm, DEK ID và content format version.
- **Wrapping AAD/context:** thông tin phục vụ lớp bọc DEK, ví dụ KEK ID/version, tenant, record ID và định danh/tóm tắt ciphertext được liên kết.

**Đưa KEK version vào content AAD có thể làm rewrap khó hơn**: khi đổi KEK-v3 sang v4, AAD của payload đổi, khiến tag AES-GCM cũ không còn xác thực với AAD mới. Đây không phải lỗi AES-GCM, mà là lỗi thiết kế ranh giới metadata.

## 4. Những cách bảo vệ DEK phổ biến

### 4.1. KMS-managed key encryption

Một KMS có thể hỗ trợ:

1. **GenerateDataKey:** tạo DEK ngẫu nhiên và trả plaintext DEK cùng ciphertext blob của DEK dưới KEK được chỉ định, theo policy của provider.
2. **Encrypt/Decrypt:** mã hóa/giải mã một lượng key material hoặc dữ liệu nhỏ, nếu API hỗ trợ kích thước, thuật toán và type tương ứng.
3. **WrapKey/UnwrapKey:** đóng gói key material trực tiếp theo cơ chế provider, có thể trả handle hoặc material đã được wrap.
4. **ReEncrypt/Rewrap:** chuyển blob được bảo vệ từ KEK cũ sang KEK mới khi provider hỗ trợ, với semantics và encryption context riêng.

Tên và tính năng **khác nhau giữa AWS KMS, Google Cloud KMS, Azure Key Vault, HSM và các giải pháp tự quản**. Một số cho phép output plaintext DEK, một số đưa operation vào HSM/crypto service. **Không được giả định tất cả hỗ trợ một API chung hoặc mặc nhiên key version từ output là một chuỗi có thể đoán**.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant KMS as KMS/HSM (giữ KEK)
    participant Store as Database/Object Store
    App->>KMS: GenerateDataKey hoặc Wrap(DEK) theo principal, keyRef, context
    KMS-->>App: Plaintext DEK (nếu API trả) + encrypted DEK
    App->>App: AES-GCM Encrypt payload bằng DEK
    App->>Store: Lưu ciphertext, nonce, tag, EDK và metadata
    Note over App: Dọn plaintext DEK best effort sau khi dùng
    App->>Store: Đọc envelope khi có yêu cầu hợp lệ
    Store-->>App: Payload, EDK, keyRef/version/context
    App->>App: Kiểm tra quyền truy cập record, tenant, format
    App->>KMS: Decrypt/Unwrap EDK theo scope được phép
    KMS-->>App: Plaintext DEK theo policy
    App->>App: AES-GCM Verify tag rồi trả plaintext đúng quyền
~~~

**KMS có thể giữ KEK non-exportable, nhưng không tự xóa plaintext DEK đã trả về JVM**. Cache, heap dump, log, unprivileged process access và session credentials cần chính sách riêng.

### 4.2. AES Key Wrap (AES-KW) và AES Key Wrap with Padding (AES-KWP)

**AES-KW** và **AES-KWP** là các cơ chế chuẩn hóa để wrap key material. Chúng giải quyết bài toán key wrapping với cấu trúc và kiểm tra tính toàn vẹn chuyên biệt, thay vì bắt ứng dụng tự thiết kế IV/AAD.

| Cơ chế | Thích hợp với | Cần biết |
|---|---|---|
| **AES-KW (RFC 3394)** | Material có độ dài phù hợp với khối 64 bit và yêu cầu thuật toán | Chịu ràng buộc về độ dài plaintext; kiểm tra integrity theo chuẩn |
| **AES-KWP (RFC 5649)** | Material có độ dài không khớp yêu cầu AES-KW thông thường | Có padding, xử lý lengths theo format riêng |
| **AES-GCM với plaintext là DEK** | AEAD hỗ trợ AAD tùy ý, phù hợp khi có nonce management | Bắt buộc nonce unique per KEK, tag verification và context binding |

Với KMS/HSM, hãy chọn **thuật toán/key-wrap mode mà provider chấp thuận**. Không giả định chuỗi tên JCA **AESWrap**, **AESWrapPad** hay **AES/GCM/NoPadding** được mọi provider hỗ trợ như nhau; không tự thay thế mode để tương thích mà bỏ security review.

### 4.3. AES-GCM để mã hóa DEK

Nếu dùng AES-GCM cho lớp KEK:

~~~text
encryptedDekAndTag = AES-GCM-Encrypt(
    KEK,
    wrapNonce,             -- unique với KEK đó
    plaintextDEK,          -- bytes của DEK
    wrapAAD               -- tenant, purpose, metadata được ràng buộc
)

DEK = AES-GCM-Decrypt(
    KEK,
    wrapNonce,
    encryptedDekAndTag,
    đúng wrapAAD
)
~~~

DEK chỉ được trả về **sau khi tag được xác minh**. Không có bước “Decrypt bytes trước, nếu lỗi tag thì vẫn giữ key tạm” trong API được thiết kế an toàn. Về logic, bên nhận không được dùng output khi authentication fail.

### 4.4. RSA-OAEP hoặc KEM/DEM cho nhiều bên nhận

Khi bên nhận có **public encryption key** và bên gửi không có quyền tới symmetric KEK chung, có thể **wrap DEK bằng RSA-OAEP** hoặc dùng một cơ chế KEM/DEM được chuẩn hóa (ví dụ một profile HPKE). Các lưu ý:

- **RSA-OAEP** có giới hạn độ dài plaintext theo modulus và hash; thích hợp bảo vệ DEK nhỏ, không phải file lớn.
- Dùng **OAEP với hash/MGF1 được chỉ định rõ theo protocol**, không dùng RSA textbook hoặc PKCS#1 v1.5 encryption cho thiết kế mới khi không bắt buộc.
- **KEM** sinh shared secret và thường cần **KDF + AEAD**; không đồng nhất một public-key ciphertext với AES wrapped DEK.
- **Bên nhận có thể có nhiều phiên bản private key**: lưu recipient key identifier, algorithm suite và metadata cần thiết để mở dữ liệu lịch sử.
- **Tin cậy public key** phải đến từ PKI/trust store/pinning hoặc cơ chế được xác thực; một public key tùy ý do attacker cung cấp không bảo đảm recipient identity.

Một envelope cho nhiều người nhận có thể chứa nhiều **recipient-wrapped DEKs** bảo vệ **cùng DEK** cho một payload, nhưng điều đó mở rộng số principal có thể giải mã. Mỗi recipient entry cần key ID/version/trust scope và policy, không sao chép plaintext DEK vào metadata.

## 5. Thiết kế envelope: Đủ để đọc lại đúng khóa sau nhiều năm

### 5.1. Một schema minh họa

~~~json
{
  "envelopeVersion": 1,
  "tenantId": "tenant-42",
  "recordId": "invoice-2026-001",
  "dekId": "dek-e1f0",
  "contentAlgorithm": "AES-256-GCM",
  "contentNonce": "<BASE64_12_BYTES>",
  "contentCiphertextWithTag": "<BASE64_PAYLOAD_AND_TAG>",
  "keyProtection": {
    "wrappingAlgorithm": "AES-256-GCM",
    "kekProvider": "approved-kms",
    "kekKeyId": "tenant-42-kek",
    "kekVersion": "v3",
    "wrapNonce": "<BASE64_12_BYTES>",
    "encryptedDekWithTag": "<BASE64_WRAPPED_KEY_AND_TAG>"
  }
}
~~~

Đây là **schema học thuật**, không phải định dạng của một nhà cung cấp. Trong production, một **KMS ciphertext blob** có thể là cấu trúc opaque và không cần ứng dụng tách wrapNonce/tag; giữ nguyên blob theo provider API. Các chuỗi trong dấu ngoặc nhọn là **placeholder**, không phải dữ liệu thật. **Base64 chỉ là encoding**, không biến DEK bản rõ thành dữ liệu an toàn.

### 5.2. Schema cần ghi rõ những điều gì?

| Field | Lý do | Rủi ro khi thiếu hoặc sai |
|---|---|---|
| **envelopeVersion** | Phân biệt schema/encoding theo thời gian | Parse nhầm data và AAD |
| **tenantId/recordId** | Phạm vi dữ liệu, ràng buộc quyền và AAD | Cross-tenant swap/confused deputy |
| **dekId** | Nhận diện DEK logical/material và scope | Không biết DEK nào liên kết payload |
| **contentAlgorithm** | Chọn đúng AEAD/format | Algorithm confusion và downgrade |
| **contentNonce** | Cần để AES-GCM mở payload | Không thể giải mã hoặc nonce reuse khi encrypt |
| **contentCiphertextWithTag** | Payload đã bảo vệ và authenticated tag | Không thể verify integrity |
| **wrappingAlgorithm** | Chọn đúng key protection mode | Parse sai EDK; unwrap không xác thực |
| **kekKeyId + version** | Tìm đúng KEK, không phụ thuộc alias hiện tại | Lỗi khi rotate hoặc trỏ sai material |
| **wrapped blob + wrap parameters** | Dữ liệu cần mở plaintext DEK | Không có đường khôi phục DEK |
| **binding/context version** | Tái tạo AAD và liên hệ content/wrap | Sửa metadata không bị phát hiện |

**Key ID/version là metadata, không phải quyền truy cập.** Đọc được mọi field trong envelope không đồng nghĩa caller được phép gọi KMS Decrypt. Phải kiểm tra authenticated principal, tenant, owner, purpose, key state và IAM/key policy.

### 5.3. Canonical encoding và AAD

Không xây AAD bằng cách nối chuỗi không ranh giới:

~~~text
SAI:
  aad = tenantId + recordId
  ("ab", "c") và ("a", "bc") có thể thành cùng chuỗi.

TỐT HƠN:
  AAD = version || length(tenantId) || tenantId
                || length(recordId) || recordId
                || length(contentAlgorithm) || contentAlgorithm
                || length(dekId) || dekId
~~~

Dùng một **encoding xác định, có version, không nhập nhằng**, ví dụ length-prefix UTF-8, schema binary chuẩn hoặc canonical encoding đã được hai đầu thống nhất. Không tin vào thứ tự field tự nhiên của JSON hoặc cách serializer xuất whitespace/key ordering nếu hai phía cần tạo lại AAD từ JSON.

### 5.4. Ràng buộc encrypted DEK với payload

Nếu EDK và ciphertext được lưu như hai blob độc lập, kẻ tấn công có quyền sửa storage có thể **đánh tráo EDK giữa các record**. Trong mô hình có AEAD payload, thường thao tác tráo dẫn tới authentication failure, nhưng vẫn có nguy cơ **chọn nhầm key, DoS, nhầm audit hoặc lạm dụng trước khi verify**.

Một phương án là cho **wrapping AAD** bao gồm **tenant, record ID, DEK ID, content algorithm và digest của content nonce + ciphertext/tag**. Khi rewrap dưới KEK mới, content ciphertext không đổi, digest vẫn giữ nguyên; wrap AAD có thể thêm **kekKeyId/version** mới. Khi payload bị sửa hoặc EDK bị tráo, authentication verification ở một trong hai lớp sẽ thất bại.

**Digest không tự cung cấp authentication**: ở đây nó trở thành một thành phần của **AAD được bảo vệ bởi authentication tag của wrapping AEAD**. Nếu dùng AES-KW/KWP hoặc provider KMS có context model khác, phải chọn **cơ chế binding tương đương theo protocol**, không tự cho rằng AES-KW hỗ trợ AAD tùy ý.

## 6. Encrypt, Decrypt và Rewrap: Ba operation không giống nhau

### 6.1. Tạo envelope mới

Một luồng mã hóa bản ghi mới được thiết kế chặt chẽ:

1. **Xác thực principal** và quyền **Write/Encrypt** của tenant và record. Không nhận tenant từ body như bằng chứng đã được phân quyền.
2. **Chọn KEK** theo policy và key family dành cho tenant; resolve **key ID/version cụ thể** của KEK Active, đúng algorithm/purpose/region.
3. **Sinh DEK mới** bằng CSPRNG/JCA KeyGenerator hoặc KMS GenerateDataKey; không lấy DEK từ timestamp, password entropy thấp hay key ID.
4. **Sinh content nonce mới** đúng chiến lược của AEAD và kích thước phù hợp; gắn content AAD được encode rõ.
5. **Encrypt payload bằng DEK**; kiểm tra mọi lỗi trước khi persist.
6. **Protect DEK bằng KEK** qua KMS/HSM/key wrapping đã phê duyệt; nếu dùng AES-GCM local thì sinh wrap nonce mới và wrap AAD riêng.
7. **Lưu nguyên khối envelope** theo transaction/atomicity thích hợp: payload ciphertext/tag, EDK, nonce, key references, algorithms và format.
8. **Xóa buffer raw DEK best effort** và giảm thời gian tồn tại key object; audit operation và key reference, không log DEK hoặc plaintext.

Một KMS GenerateDataKey có thể sinh plaintext DEK và encrypted blob **trước khi ứng dụng mã hóa payload**. Điều đó vẫn tương đương về logic nếu metadata binding và xử lý lỗi được thực hiện đúng. Không buộc mọi KMS phải cho caller “mã hóa payload rồi mới wrap DEK”.

### 6.2. Đọc envelope và giải mã

~~~mermaid
sequenceDiagram
    participant Client as Authenticated caller
    participant App as Application
    participant DB as Encrypted record storage
    participant Registry as Key registry / policy
    participant KMS as KMS/HSM
    Client->>App: Read recordId trong tenant được cấp quyền
    App->>App: AuthN + resource/tenant authorization
    App->>DB: Load envelope
    DB-->>App: Content ciphertext, EDK, metadata
    App->>App: Parse format/lengths, kiểm tra tenant/record
    App->>Registry: Resolve immutable KEK keyId/version, purpose/state
    Registry-->>App: Approved provider key reference
    App->>KMS: Unwrap EDK, context đúng, IAM approved
    KMS-->>App: Plaintext DEK hoặc operation result
    App->>App: AES-GCM Verify tag với content AAD
    alt Hợp lệ
        App-->>Client: Plaintext theo quyền
    else Lỗi integrity/authorization
        App-->>Client: Denied/invalid (không trả plaintext)
    end
    App->>App: Cleanup DEK best effort + safe audit
~~~

Chú ý các lớp:

- **Envelope từ database có thể bị thao túng**. Trước khi gọi KMS, validate schema/size/keyRef/tenant theo nguồn tin cậy và giới hạn provider resources.
- **KMS permission được kiểm tra trước content tag verification**. Vì vậy không được coi tag GCM như điều kiện duy nhất quyết định được phép chọn KEK nào.
- Nếu **Unwrap thất bại**, không thử liên tục mọi KEK để tìm khóa phù hợp; hành vi đó có thể thành **key enumeration, unwrap oracle** hoặc làm tăng chi phí. Có thể áp dụng migration/fallback **được định nghĩa rõ bằng version**.
- Nếu content authentication tag sai, **không dùng plaintext từng phần**; báo lỗi kiểm soát và audit metadata, không log ciphertext/key/plaintext nhạy cảm quá mức.
- Nếu KMS provider trả **opaque key handle** thay vì plaintext DEK, ứng dụng cần theo đúng API; không ép xuất raw material chỉ để dùng cùng mẫu code local.

### 6.3. Rewrap: Thay KEK mà không thay DEK

Rewrap là **đổi lớp bảo vệ DEK**, không nhất thiết thay payload:

~~~text
Ban đầu:
    Content = AES-GCM(DEK-7, payload, nonce-1, contentAAD)
    EDK-v3  = Wrap(KEK-v3, DEK-7, wrapContext-v3)

Sau khi rotate KEK:
    DEK-7   = Unwrap(KEK-v3, EDK-v3, wrapContext-v3)
    EDK-v4  = Wrap(KEK-v4, DEK-7, wrapContext-v4)

    Content không đổi nếu contentAAD và dữ liệu không đổi.
    KEK reference, EDK và wrap metadata phải đổi nhất quán.
~~~

Nếu provider hỗ trợ **server-side re-encryption/rewrap**, nên đánh giá để giảm việc plaintext DEK đi qua ứng dụng. Rewrap không có nghĩa luôn có API **ReEncrypt** tương ứng ở mọi nhà cung cấp, và một số API chỉ xử lý ciphertext key blobs của chính provider đó.

Quy trình production nên:

1. Kiểm tra **owner, tenant, purpose và key state** của cả KEK cũ/mới.
2. Mở EDK cũ bằng đúng key/version/context đã lưu.
3. Bọc lại cùng DEK dưới KEK mới, dùng **wrap nonce mới** nếu thuật toán cần.
4. Ghi atomic envelope revision với **EDK mới + key ID/version mới + wrap metadata mới**, giữ content layer nguyên vẹn theo thiết kế.
5. Đọc/verify thử một mẫu sau migration theo quyền được phép.
6. Đếm các EDK còn phụ thuộc KEK cũ; **không destroy cũ khi vẫn còn bản ghi hoặc backup cần nó**.

**Nếu content AAD đã gắn KEK-v3 thì việc chỉ đổi metadata KEK-v4 sẽ làm content tag sai.** Khi gặp schema như vậy, migration có thể buộc cập nhật content authentication (và đôi khi re-encrypt) hoặc phải thay đổi format một cách có kiểm soát. Không tự vô hiệu hóa AAD để làm cho dữ liệu “mở được”.

### 6.4. Re-encrypt: Khi thay DEK

Thay DEK cần xử lý payload:

~~~text
DEK-old = Unwrap(KEK-old, EDK-old)
plaintext = AEAD-Decrypt(DEK-old, oldNonce, oldCiphertext, oldAAD)
DEK-new = CSPRNG
newContent = AEAD-Encrypt(DEK-new, newNonce, plaintext, newAAD)
newEDK = Wrap(KEK-current, DEK-new, newWrapContext)
Persist new envelope atomically, audit và cleanup plaintext/DEK.
~~~

**Chỉ rewrap DEK-old không phải DEK rotation.** Khi **DEK-old lộ**, đối thủ vẫn có thể giải mã những ciphertext dùng DEK-old dù KEK mới. Re-encrypt làm giảm sự phụ thuộc của dữ liệu lưu trữ mới vào DEK cũ, **nhưng không thu hồi được ciphertext/plaintext mà đối thủ đã sao chép trước đó**.

### 6.5. Concurrency và atomicity

Với database có ghi đồng thời, migration có thể gặp **race**:

~~~text
T1: Worker A đọc envelope revision 7 để rewrap KEK-v3 -> v4.
T2: Worker B sửa payload và ghi envelope revision 8.
T3: Worker A ghi EDK v4 dựa trên revision 7.

Nếu không có concurrency control:
    EDK có thể không còn khớp payload đang lưu.
~~~

Áp dụng **optimistic locking/compare-and-swap theo envelope revision**, hoặc transaction phù hợp. Luồng rewrap phải bảo vệ **blob ciphertext và metadata liên kết**, không chỉ cập nhật cột EDK độc lập. Retry phải phát sinh **wrap nonce mới nếu thực hiện AES-GCM encryption lại dưới cùng KEK** và theo dõi idempotency phù hợp; tránh replay một thao tác sang record khác.

## 7. Key hierarchy, owner và access control

### 7.1. KEK hierarchy cho nhiều tenant

~~~mermaid
flowchart TD
    R["Root key / HSM security boundary"] --> A["Tenant-A KEK / key family"]
    R --> B["Tenant-B KEK / key family"]
    A --> A1["EDK record A-1"]
    A --> A2["EDK record A-2"]
    B --> B1["EDK record B-1"]
    B --> B2["EDK record B-2"]
    A1 --> AC1["Ciphertext A-1, DEK-A1"]
    A2 --> AC2["Ciphertext A-2, DEK-A2"]
    B1 --> BC1["Ciphertext B-1, DEK-B1"]
    B2 --> BC2["Ciphertext B-2, DEK-B2"]
~~~

Sơ đồ diễn tả **quan hệ bảo vệ logic**. Tùy provider, root key không nhất thiết là một KEK trực tiếp mà ứng dụng được phép gọi; key hierarchy có thể nằm hoàn toàn trong KMS/HSM. Không tự suy từ hình vẽ rằng có thể export root material hoặc derive tenant KEK tùy ý.

**Tenant separation** có thể được thực hiện bằng key riêng, IAM scopes và encryption context, hoặc kết hợp các yếu tố. Dùng KEK riêng theo tenant giúp giới hạn blast radius và có lifecycle riêng, nhưng **vẫn phải kiểm tra người dùng có quyền với record**, vì workload có quyền Decrypt rộng vẫn có thể trở thành confused deputy.

### 7.2. Mẫu chính sách permission

| Principal | Quyền cần thiết | Không được mặc định |
|---|---|---|
| **Key administrator** | Create/Rotate/Disable/Review policy theo approval | Decrypt/Unwrap mọi EDK hoặc Export raw KEK |
| **Customer Data Service** | GenerateDataKey/Unwrap cho tenant, record, purpose được cấp quyền | ManageKeyPolicy, Destroy, quyền toàn bộ tenant |
| **Billing Service** | Sign với private signing key được chỉ định | Unwrap customer DEK hoặc dùng signing key như KEK |
| **Key migration worker** | Unwrap KEK cũ + Wrap KEK mới theo danh sách record/migration job có phê duyệt | Đọc tùy ý plaintext nghiệp vụ, Export mọi root key |
| **Backup/DR operator** | Backup/restore theo security domain, scope đã duyệt | Raw key export không kiểm soát hoặc bypass approval |
| **Independent auditor** | Đọc metadata, IAM changes, key versions và events | Raw secret, Sign/Decrypt chỉ vì được xem audit |

Một **migration worker** có thể cần quyền tương đối nhạy cảm. Nên giới hạn quyền bằng **approval, TTL, allowlist key IDs/versions, tenant scope, request context, monitored execution** và audit độc lập. Nếu provider hỗ trợ rewrap **không trả raw DEK** cho worker, có thể giảm exposure.

### 7.3. Encryption context không thay quyền

Một số KMS nhận **encryption context** như tập field ngoài ciphertext. Nếu context được dùng làm AAD hoặc điều kiện key policy, phải:

- Lấy tenant/record từ **authenticated business context**, không tin trường do caller tùy ý đặt.
- Bảo đảm key usage policy giới hạn **context được phép** nếu provider hỗ trợ.
- Lưu đủ context hoặc cách tái tạo có phiên bản, không làm mất khả năng decrypt lịch sử.
- Không log context nhạy cảm quá mức, vì nhiều provider coi encryption context là metadata được ghi audit.
- Không coi một key ID khó đoán là authorization; nó có thể lộ công khai trong envelope.

**AES-GCM AAD ràng buộc ciphertext vào context, nhưng không chứng minh caller được phép yêu cầu KMS mở DEK.** Hai lớp cần được kiểm tra riêng.

### 7.4. Key ID, alias và version

Phân biệt:

- **Logical key family:** tenant-42/customer-data có thể có nhiều KEK versions.
- **Key ID/version:** tham chiếu material/slot thật mà provider dùng để Unwrap.
- **Alias current:** tiện cho encryption mới, có thể đổi mục tiêu khi rotate.
- **EDK của bản ghi lịch sử:** phải lưu **resolved key reference** thực dùng, không chỉ alias có thể đổi.

Khi KMS không biểu diễn key version theo cách ứng dụng kỳ vọng, hãy dùng **provider-defined immutable key reference** và mapping inventory được quản lý. Không tự dựng version tưởng tượng rồi truyền vào API.

## 8. Runtime memory và cache của plaintext DEK

### 8.1. Plaintext DEK sống trong RAM có rủi ro gì?

Một KMS có thể trả **raw DEK trong response**. Từ thời điểm đó, key có thể tồn tại trong:

- byte[] và SecretKeySpec/SecretKey object;
- internal buffers của JCA/JCE provider/Cipher;
- heap/native memory, dump, swap, crash reports;
- cache của crypto service hoặc SDK;
- log/debug/telemetry nếu lập trình sai.

**Key encryption bảo vệ DEK khi lưu trữ, nhưng không tự bảo vệ DEK đang được sử dụng trong bộ nhớ**. Cần giới hạn thời gian sống, số bản sao, quyền debug/dump, host/container isolation và xử lý memory theo hợp đồng provider.

### 8.2. Dùng DEK cache khi nào?

| Cách dùng | Ưu điểm | Nguy cơ |
|---|---|---|
| **Unwrap mỗi request** | Lifetime DEK ngắn, state/policy mới được áp dụng thường xuyên | Latency/cost KMS, outage |
| **Cache theo request/batch** | Giảm unwrap cho dữ liệu liên quan | Material tồn tại trong thời gian batch |
| **Cache có TTL, scope, capacity** | Tăng throughput | DEK cũ vẫn ở RAM sau revoke/rotation, memory exposure |
| **Crypto service giữ key handle** | Business app không cần raw DEK | Service vẫn cần IAM, isolation, anti-oracle |

Cache phải phân biệt **tenant, DEK/wrapped key reference, key version, purpose, environment**; không dùng alias current chung và không chứa DEK bản rõ trong JSON session. Khi **KEK bị disable**, DEK đã unwrap vẫn có thể dùng offline; cần **lease/cache invalidation, TTL, workload/session control**. Một TTL chỉ giới hạn ứng dụng thiện chí, không ngăn đối thủ đã sao chép DEK.

### 8.3. Cleanup trong Java

~~~java
byte[] plaintextDek = receiveAuthorizedDekFromKms();
try {
    // Encrypt/decrypt với JCA. Các provider có thể copy material.
} finally {
    java.util.Arrays.fill(plaintextDek, (byte) 0);
}
~~~

Ghi đè mảng gốc là **best effort**. **SecretKeySpec sao chép bytes đầu vào**, provider có thể giữ bản khác, JVM GC không bảo đảm wipe tức thì và System.gc không phải biện pháp xóa key. Hạn chế gọi **getEncoded()**, chuyển key sang String/Base64, in raw secret vào exception hoặc lưu heap dump không bảo vệ.

### 8.4. KEK non-exportable không loại bỏ mọi oracle

Một workload có quyền KMS Decrypt/Unwrap trên hàng nghìn EDK có thể **bị lợi dụng như decryption oracle** nếu endpoint nghiệp vụ không kiểm tra quyền record. Dù KEK không thể xuất, người tấn công vẫn có thể yêu cầu dịch vụ trả plaintext.

**Least privilege** phải áp dụng tại **IAM/KMS, business authorization và crypto gateway**, đồng thời audit **người gọi, key ID/version, tenant, operation, result**, không ghi DEK.

## 9. Java 17: Mã hóa payload bằng DEK và mã hóa DEK bằng KEK

Ví dụ tự chạy sau thể hiện **hai lớp AES-GCM độc lập**:

- Lớp **content:** DEK 256 bit ngẫu nhiên + content nonce 96 bit, AES-GCM tag 128 bit; AAD gắn tenant/record/DEK ID.
- Lớp **key protection:** KEK 256 bit riêng + wrap nonce 96 bit khác, AES-GCM tag 128 bit; AAD gắn tenant/record/DEK ID, KEK version và **SHA-256 digest của content nonce + ciphertext/tag**.
- Registry minh họa **KEK version 1** ở trạng thái **DECRYPT_ONLY** sau rotation và **version 2** đang **ACTIVE**.
- Rewrap xác thực EDK theo KEK cũ, sau đó mã hóa **cùng DEK** dưới KEK mới mà **không đổi content ciphertext**.
- Decrypt kiểm tra tenant, record, key state/usage và GCM tags trước khi trả plaintext.

**Giới hạn bảo mật:** Để không phụ thuộc dịch vụ ngoài, demo sinh KEK ngay trong JVM và dùng raw DEK trong byte[]. Trong production, **KEK quan trọng nên được quản lý bằng KMS/HSM**, và thao tác bọc/mở DEK nên đi qua provider có IAM/audit. Hai nonce ngẫu nhiên 96 bit trong demo chỉ phù hợp với số lượt dùng nhỏ; **không** có bảo đảm uniqueness tuyệt đối trên một KEK bọc DEK hàng triệu lần trên nhiều node.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class DekEncryptionExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int DEK_BYTES = 32;
    private static final String CONTENT_ALG = "AES-256-GCM";
    private static final String WRAP_ALG = "AES-256-GCM";

    enum State {
        ACTIVE, DECRYPT_ONLY, SUSPENDED
    }

    record KekRef(String keyId, int version) {
        KekRef {
            if (keyId == null || keyId.isBlank() || version < 1) {
                throw new IllegalArgumentException("Invalid KEK ref");
            }
        }
    }

    record Kek(
            KekRef ref,
            String tenantId,
            String purpose,
            State state,
            SecretKey material) {}

    // Registry minh họa; production cần IAM, provider policy và audit.
    static final class KekRegistry {
        private final Map<KekRef, Kek> keys = new HashMap<>();

        void register(Kek key) {
            if (keys.putIfAbsent(key.ref(), key) != null) {
                throw new IllegalStateException("Duplicate KEK ref");
            }
        }

        void setState(KekRef ref, State state) {
            Kek old = keys.get(ref);
            if (old == null) {
                throw new IllegalArgumentException("Unknown key ref");
            }
            keys.put(ref, new Kek(
                    old.ref(), old.tenantId(), old.purpose(),
                    state, old.material()));
        }

        Kek resolve(
                String authenticatedTenant,
                KekRef ref,
                boolean forWrap) {
            Kek key = keys.get(ref);
            if (key == null
                    || !key.tenantId().equals(authenticatedTenant)
                    || !"DEK_PROTECTION".equals(key.purpose())) {
                throw new SecurityException("Key not available");
            }
            if (forWrap) {
                if (key.state() != State.ACTIVE) {
                    throw new SecurityException("KEK cannot wrap");
                }
            } else if (key.state() != State.ACTIVE
                    && key.state() != State.DECRYPT_ONLY) {
                throw new SecurityException("KEK cannot unwrap");
            }
            return key;
        }
    }

    // Envelope không chứa raw DEK. Byte arrays được sao chép phòng
    // trường hợp caller tự sửa dữ liệu sau khi khởi tạo record.
    record Envelope(
            int version,
            String tenantId,
            String recordId,
            String dekId,
            String contentAlg,
            String wrapAlg,
            KekRef kekRef,
            byte[] contentNonce,
            byte[] contentCiphertextWithTag,
            byte[] wrapNonce,
            byte[] encryptedDekWithTag) {
        Envelope {
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(recordId);
            Objects.requireNonNull(dekId);
            Objects.requireNonNull(contentAlg);
            Objects.requireNonNull(wrapAlg);
            Objects.requireNonNull(kekRef);
            contentNonce = Objects.requireNonNull(contentNonce).clone();
            contentCiphertextWithTag =
                    Objects.requireNonNull(contentCiphertextWithTag).clone();
            wrapNonce = Objects.requireNonNull(wrapNonce).clone();
            encryptedDekWithTag =
                    Objects.requireNonNull(encryptedDekWithTag).clone();
        }

        @Override
        public byte[] contentNonce() {
            return contentNonce.clone();
        }
        @Override
        public byte[] contentCiphertextWithTag() {
            return contentCiphertextWithTag.clone();
        }
        @Override
        public byte[] wrapNonce() {
            return wrapNonce.clone();
        }
        @Override
        public byte[] encryptedDekWithTag() {
            return encryptedDekWithTag.clone();
        }
    }

    static byte[] newNonce() {
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        return nonce;
    }

    static void putString(DataOutputStream out, String value)
            throws Exception {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static void putBytes(DataOutputStream out, byte[] value)
            throws Exception {
        out.writeInt(value.length);
        out.write(value);
    }

    // Không đưa KEK version vào content AAD: rewrap không làm
    // content ciphertext mất hiệu lực.
    static byte[] contentAad(
            String tenant, String record, String dekId)
            throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(1); // format version
            putString(out, "CONTENT");
            putString(out, CONTENT_ALG);
            putString(out, tenant);
            putString(out, record);
            putString(out, dekId);
        }
        return buffer.toByteArray();
    }

    static byte[] digestContent(
            byte[] nonce, byte[] ciphertextWithTag) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        digest.update(nonce); // fixed 12-byte nonce
        digest.update(ciphertextWithTag);
        return digest.digest();
    }

    static byte[] wrapAad(
            String tenant, String record, String dekId,
            KekRef ref, byte[] contentNonce,
            byte[] contentCiphertextWithTag) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(1); // format version
            putString(out, "DEK-WRAP");
            putString(out, WRAP_ALG);
            putString(out, CONTENT_ALG);
            putString(out, tenant);
            putString(out, record);
            putString(out, dekId);
            putString(out, ref.keyId());
            out.writeInt(ref.version());
            putBytes(out, digestContent(
                    contentNonce, contentCiphertextWithTag));
        }
        return buffer.toByteArray();
    }

    static void checkEnvelope(
            String authenticatedTenant,
            String expectedRecordId,
            Envelope envelope) {
        if (envelope.version() != 1
                || !CONTENT_ALG.equals(envelope.contentAlg())
                || !WRAP_ALG.equals(envelope.wrapAlg())
                || !authenticatedTenant.equals(envelope.tenantId())
                || !expectedRecordId.equals(envelope.recordId())
                || envelope.dekId().isBlank()
                || envelope.contentNonce().length != NONCE_BYTES
                || envelope.wrapNonce().length != NONCE_BYTES
                || envelope.contentCiphertextWithTag().length
                       < TAG_BITS / 8
                || envelope.encryptedDekWithTag().length
                       != DEK_BYTES + TAG_BITS / 8) {
            throw new SecurityException("Invalid envelope or scope");
        }
    }

    static byte[] wrapDek(
            Kek kek, byte[] dek, String tenant, String record,
            String dekId, byte[] contentNonce, byte[] contentCiphertext,
            byte[] wrapNonce) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, kek.material(),
                new GCMParameterSpec(TAG_BITS, wrapNonce));
        cipher.updateAAD(wrapAad(
                tenant, record, dekId, kek.ref(),
                contentNonce, contentCiphertext));
        return cipher.doFinal(dek);
    }

    static byte[] unwrapDek(
            Kek kek, Envelope envelope) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, kek.material(),
                new GCMParameterSpec(TAG_BITS, envelope.wrapNonce()));
        cipher.updateAAD(wrapAad(
                envelope.tenantId(), envelope.recordId(),
                envelope.dekId(), envelope.kekRef(),
                envelope.contentNonce(),
                envelope.contentCiphertextWithTag()));
        byte[] dek = cipher.doFinal(envelope.encryptedDekWithTag());
        if (dek.length != DEK_BYTES) {
            Arrays.fill(dek, (byte) 0);
            throw new SecurityException("Invalid DEK length");
        }
        return dek;
    }

    static Envelope encrypt(
            KekRegistry registry, String authenticatedTenant,
            String recordId, KekRef kekRef, byte[] plaintext)
            throws Exception {
        Kek kek = registry.resolve(
                authenticatedTenant, kekRef, true);
        Objects.requireNonNull(plaintext);
        if (recordId == null || recordId.isBlank()) {
            throw new IllegalArgumentException("Invalid record");
        }

        byte[] dek = new byte[DEK_BYTES];
        RNG.nextBytes(dek);
        try {
            String dekId = "dek-" + UUID.randomUUID();
            byte[] contentNonce = newNonce();
            Cipher dataCipher = Cipher.getInstance("AES/GCM/NoPadding");
            dataCipher.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, contentNonce));
            dataCipher.updateAAD(
                    contentAad(authenticatedTenant, recordId, dekId));
            byte[] contentCiphertext = dataCipher.doFinal(plaintext);

            byte[] wrapNonce = newNonce();
            byte[] edk = wrapDek(
                    kek, dek, authenticatedTenant, recordId,
                    dekId, contentNonce, contentCiphertext, wrapNonce);

            return new Envelope(
                    1, authenticatedTenant, recordId, dekId,
                    CONTENT_ALG, WRAP_ALG, kekRef,
                    contentNonce, contentCiphertext, wrapNonce, edk);
        } finally {
            // Wipe mảng gốc; JCA/SecretKeySpec có thể còn copy.
            Arrays.fill(dek, (byte) 0);
        }
    }

    static byte[] decrypt(
            KekRegistry registry, String authenticatedTenant,
            String expectedRecordId, Envelope envelope) throws Exception {
        checkEnvelope(
                authenticatedTenant, expectedRecordId, envelope);
        Kek kek = registry.resolve(
                authenticatedTenant, envelope.kekRef(), false);
        byte[] dek = unwrapDek(kek, envelope);
        try {
            Cipher dataCipher = Cipher.getInstance("AES/GCM/NoPadding");
            dataCipher.init(Cipher.DECRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(
                            TAG_BITS, envelope.contentNonce()));
            dataCipher.updateAAD(contentAad(
                    envelope.tenantId(), envelope.recordId(),
                    envelope.dekId()));
            return dataCipher.doFinal(
                    envelope.contentCiphertextWithTag());
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }

    // Chỉ thay lớp KEK: payload ciphertext/nonce/AAD không đổi.
    static Envelope rewrap(
            KekRegistry registry, String authenticatedTenant,
            String expectedRecordId, Envelope old,
            KekRef newKekRef) throws Exception {
        checkEnvelope(authenticatedTenant, expectedRecordId, old);
        Kek oldKek = registry.resolve(
                authenticatedTenant, old.kekRef(), false);
        Kek newKek = registry.resolve(
                authenticatedTenant, newKekRef, true);
        byte[] dek = unwrapDek(oldKek, old);
        try {
            byte[] newWrapNonce = newNonce();
            byte[] newEncryptedDek = wrapDek(
                    newKek, dek, old.tenantId(), old.recordId(),
                    old.dekId(), old.contentNonce(),
                    old.contentCiphertextWithTag(), newWrapNonce);
            return new Envelope(
                    old.version(), old.tenantId(), old.recordId(),
                    old.dekId(), old.contentAlg(), old.wrapAlg(),
                    newKekRef, old.contentNonce(),
                    old.contentCiphertextWithTag(), newWrapNonce,
                    newEncryptedDek);
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }

    static Kek makeKek(
            String keyId, int version, String tenant) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return new Kek(new KekRef(keyId, version), tenant,
                "DEK_PROTECTION", State.ACTIVE,
                generator.generateKey());
    }

    public static void main(String[] args) throws Exception {
        KekRegistry registry = new KekRegistry();
        Kek v1 = makeKek("tenant-42-kek", 1, "tenant-42");
        Kek v2 = makeKek("tenant-42-kek", 2, "tenant-42");
        registry.register(v1);
        registry.register(v2);

        byte[] input = "Sample invoice, not real customer data"
                .getBytes(StandardCharsets.UTF_8);
        try {
            Envelope old = encrypt(
                    registry, "tenant-42", "invoice-01",
                    v1.ref(), input);
            byte[] oldPlaintext = decrypt(
                    registry, "tenant-42", "invoice-01", old);
            try {
                System.out.println("Old KEK decrypt works: "
                        + Arrays.equals(input, oldPlaintext));
            } finally {
                Arrays.fill(oldPlaintext, (byte) 0);
            }

            // Rotation: KEK-v1 chỉ còn dùng mở dữ liệu lịch sử.
            registry.setState(v1.ref(), State.DECRYPT_ONLY);
            Envelope migrated = rewrap(
                    registry, "tenant-42", "invoice-01",
                    old, v2.ref());
            System.out.println("Payload unchanged after rewrap: "
                    + Arrays.equals(old.contentCiphertextWithTag(),
                                    migrated.contentCiphertextWithTag()));
            byte[] newPlaintext = decrypt(
                    registry, "tenant-42", "invoice-01", migrated);
            try {
                System.out.println("New KEK decrypt works: "
                        + Arrays.equals(input, newPlaintext));
            } finally {
                Arrays.fill(newPlaintext, (byte) 0);
            }

            try {
                encrypt(registry, "tenant-42", "invoice-02",
                        v1.ref(), input);
                throw new AssertionError("Old KEK was used to wrap");
            } catch (SecurityException expected) {
                System.out.println("Retired KEK cannot wrap new DEK");
            }

            try {
                decrypt(registry, "tenant-OTHER", "invoice-01",
                        migrated);
                throw new AssertionError("Cross-tenant read accepted");
            } catch (SecurityException expected) {
                System.out.println("Cross-tenant read denied");
            }

            byte[] tamperedEdk = migrated.encryptedDekWithTag();
            tamperedEdk[0] ^= 1;
            Envelope badEdk = new Envelope(
                    migrated.version(), migrated.tenantId(),
                    migrated.recordId(), migrated.dekId(),
                    migrated.contentAlg(), migrated.wrapAlg(),
                    migrated.kekRef(), migrated.contentNonce(),
                    migrated.contentCiphertextWithTag(),
                    migrated.wrapNonce(), tamperedEdk);
            try {
                decrypt(registry, "tenant-42", "invoice-01", badEdk);
                throw new AssertionError("Modified DEK was accepted");
            } catch (AEADBadTagException expected) {
                System.out.println("Modified EDK rejected by tag");
            }

            byte[] tamperedPayload =
                    migrated.contentCiphertextWithTag();
            tamperedPayload[0] ^= 1;
            Envelope badPayload = new Envelope(
                    migrated.version(), migrated.tenantId(),
                    migrated.recordId(), migrated.dekId(),
                    migrated.contentAlg(), migrated.wrapAlg(),
                    migrated.kekRef(), migrated.contentNonce(),
                    tamperedPayload, migrated.wrapNonce(),
                    migrated.encryptedDekWithTag());
            try {
                decrypt(registry, "tenant-42", "invoice-01",
                        badPayload);
                throw new AssertionError("Modified payload accepted");
            } catch (AEADBadTagException expected) {
                System.out.println("Modified payload rejected by tag");
            }
        } finally {
            Arrays.fill(input, (byte) 0);
        }
    }
}
~~~

Lưu thành **DekEncryptionExample.java**, chạy với JDK 17+:

~~~bash
javac DekEncryptionExample.java
java DekEncryptionExample
~~~

Các dòng kết quả mong đợi:

~~~text
Old KEK decrypt works: true
Payload unchanged after rewrap: true
New KEK decrypt works: true
Retired KEK cannot wrap new DEK
Cross-tenant read denied
Modified EDK rejected by tag
Modified payload rejected by tag
~~~

### 9.1. Phân tích hai lớp AAD trong code

**Content AAD** ràng buộc DEK identifier, tenant, record và content algorithm, **không chứa KEK version**. Do đó rewrap KEK-v1 sang KEK-v2 không thay đổi content ciphertext, nonce, authentication tag hoặc content AAD.

**Wrap AAD** ràng buộc thêm KEK reference/version và digest của content nonce + ciphertext/tag. Thay một byte EDK làm **wrap tag** lỗi; thay một byte ciphertext làm **digest được đưa vào wrap AAD** khác đi, cũng dẫn tới wrap-tag failure trước khi mở DEK. Nếu một attacker chỉ sửa content AAD metadata như tenant/record/dekId, AAD tái tạo sẽ khác và authentication verification thất bại, ngoài các kiểm tra authorization sớm.

**Đây không phải một tiêu chuẩn envelope đã được công bố**, mà là ví dụ để thấy rõ ý nghĩa của domain separation và authenticated metadata. Khi triển khai, dùng **protocol/library được review**, thống nhất serialization, key rotation và lựa chọn thuật toán theo yêu cầu bảo mật của tổ chức.

### 9.2. Giới hạn của ví dụ Java

1. **KEK được sinh và lưu trong JVM**; production nên dùng KMS/HSM khi policy yêu cầu, không giữ raw KEK ở registry nội bộ.
2. **Không có IAM thật**. Hàm nhận authenticatedTenant nhưng trong demo nó là một tham số, không phải danh tính đã được một IdP xác minh. Production phải kiểm tra quyền record.
3. **Random 96-bit nonce có xác suất collision khác 0**. Một KEK dùng cho rất nhiều EDK cần nonce generation strategy/invocation limits được đánh giá; demo chỉ wrap vài lần.
4. **AES-GCM wrapping là một thiết kế AEAD**, không tự thay thế mọi thuộc tính/hợp đồng của AES-KW, AES-KWP hoặc KMS ciphertext blob.
5. **Schema custom chưa có mạng/storage/serialization chuẩn**; Envelope record chứa bytes trong RAM, không phải JSON production.
6. **KeyRegistry in-memory không có concurrency, backup hay multi-region consistency**, chỉ minh họa state; production dùng key versions/aliases theo provider contract.
7. **Không có audit bền vững**, quotas, rate limits, monitoring hoặc incident response integration.
8. **Arrays.fill chỉ xóa mảng raw DEK mà code sở hữu**. SecretKeySpec và Cipher có thể giữ bản copy; không được kết luận zeroization tuyệt đối.
9. **Không có replay protection**; envelope hợp lệ có thể bị gửi lại. Business layer cần record revision, version, anti-replay hoặc transaction semantics phù hợp.
10. **Không bảo đảm integrity độc lập của toàn bộ database**: nếu attacker thay cả record bằng một envelope cũ cùng tenant/record, cần revision/anti-rollback policy ở tầng dữ liệu.
11. **Chưa có KMS outage/restore flow**; registry mất là không thể mở envelope về sau. Production cần persistent key references, backup và được phép truy cập keys lịch sử.
12. **Trạng thái DECRYPT_ONLY là quy ước đào tạo**; mỗi provider có key state semantics riêng. Khi key đã compromised hoặc suspended, decrypt/unwrap có thể phải bị từ chối.
13. **Không thực hiện content re-encryption bằng DEK mới**; rewrap chỉ thay KEK như mô tả, không chữa được DEK compromise.
14. **Không dùng ví dụ để claim production readiness**; hệ thống thật còn phải giải quyết cipher suite migration, input limits, rate limits, IAM, key hierarchy và kiểm thử toàn diện.

## 10. Vòng đời khóa: Tạo, lưu, dùng, rotate, retire và destroy

Trong envelope encryption, **DEK và KEK có hai vòng đời độc lập nhưng liên kết**. Mỗi thao tác thay đổi một lớp có thể ảnh hưởng tới lớp còn lại và tới dữ liệu đã lưu.

### 10.1. Tạo key material và key metadata

Khi tạo **KEK**:

- Chọn **key type/algorithm/purpose** phù hợp cho ProtectKey/UnprotectKey.
- Tạo trong KMS/HSM hoặc crypto boundary đã duyệt; ưu tiên **non-exportable KEK** với lớp rủi ro cao.
- Gán **immutable key ID/version, owner, tenant, environment và policy reference**.
- Tách quyền **Create/Manage/Rotate/Destroy** khỏi **Wrap/Unwrap/Decrypt**.
- Định nghĩa cryptoperiod, key states và backup/restore trước khi production tạo EDK.

Khi tạo **DEK**:

- Sinh từ CSPRNG/provider có assurance phù hợp, ví dụ AES-256 DEK 32 byte, không dùng một password hoặc SHA-256(timestamp).
- Định nghĩa **scope** (record/object/batch), purpose, nonce strategy và invocation limit.
- Giới hạn **plaintext DEK** trong memory/crypto service; sau khi dùng, chỉ lưu EDK.
- Có metadata đủ để biết DEK nào bảo vệ ciphertext nào và KEK version nào mở được nó.

### 10.2. Sử dụng: Quyền Wrap khác Unwrap

Một dịch vụ chỉ ghi dữ liệu mới có thể cần quyền tạo/wrap DEK mà **không cần mở tất cả EDK lịch sử**. Một dịch vụ chỉ đọc dữ liệu lịch sử có thể được cấp **Unwrap** theo key references được phép. Không mặc định mọi principal có quyền **Encrypt** đều có quyền **Decrypt** trên mọi record.

Một mô hình phân tách:

~~~text
Writer:
    GenerateDataKey / Wrap new DEK
    AES-GCM Encrypt payload được phép
    Không có quyền DestroyKey/ExportRawKEK

Reader:
    Authorize record/tenant
    Unwrap DEK theo key version đã lưu
    AES-GCM Verify + Decrypt payload
    Không tự sửa KEK alias hoặc policy

Key administrator:
    Manage grants, rotate, suspend theo approval
    Không mặc nhiên có quyền đọc plaintext
~~~

**Authorization trong ứng dụng là bắt buộc** ngay cả khi KMS có IAM. Một service role được quyền gọi Unwrap cho hàng nghìn tenant có thể bị lợi dụng để giải mã hộ caller không có quyền record.

### 10.3. KEK rotation

KEK rotation có thể diễn ra theo hai cách:

| Kiểu | Hành động | Hệ quả |
|---|---|---|
| **Lazy rotation** | Mã hóa/wrap EDK mới bằng KEK hiện tại; EDK cũ vẫn dưới KEK cũ | Cần giữ quyền Unwrap và key material cũ cho dữ liệu lịch sử |
| **Active rewrap migration** | Mở EDK cũ và bọc lại dưới KEK mới theo từng record | Giảm phụ thuộc KEK cũ, cần consistency, audit và kiểm thử restore |

Không có một lựa chọn tốt tuyệt đối. **Lazy rotation** giảm chi phí migration nhưng kéo dài thời gian giữ KEK cũ. **Active rewrap** rút ngắn sự phụ thuộc nhưng cần xử lý transaction, throughput, KMS quotas và format/AAD. Với dữ liệu archive dài hạn, cả hai đều cần **key inventory/dependency tracking**.

**Key alias chỉ có vai trò lựa chọn khóa cho thao tác mới**; nếu alias được đổi từ KEK-v3 sang KEK-v4, EDK cũ không tự được rewrap. Đường Decrypt phải resolve **version chính xác đã được dùng**.

### 10.4. DEK rotation

Có thể xảy ra khi:

- DEK đến giới hạn cryptoperiod hoặc usage/nonce limit.
- DEK đã bị lộ qua heap dump, log hoặc export trái phép.
- Cần giảm blast radius, thay scope per-batch sang per-record.
- Chuyển thuật toán/format hoặc yêu cầu tuân thủ.

Với **dữ liệu cũ cần thay DEK**, phải giải mã bằng DEK cũ, mã hóa lại bằng DEK mới và nonce mới, tạo EDK tương ứng. Mọi quá trình di chuyển plaintext phải có **authorization, bảo vệ memory/transit, audit và rollback/retry plan**.

**DEK rotation không tương đương rewrap**: rewrap giữ nguyên raw DEK, còn re-encrypt dưới key mới mới thực sự đổi material bảo vệ payload.

### 10.5. Suspend, revoke và compromise

Một KEK ở trạng thái **Suspended/Disabled** có thể bị KMS từ chối Unwrap tùy provider, nhưng:

- Các **plaintext DEK đã unwrap** vẫn có thể hiện diện trong JVM.
- Một **bản sao raw KEK** đã xuất ngoài KMS có thể tiếp tục được dùng offline.
- **Key ID đã bị thu hồi quyền** không tự loại bỏ ciphertext/EDK đã được sao chép.
- Một **token/service credential** đã cấp có thể còn hiệu lực đến khi provider/session xử lý.

Nếu material **compromised**, một thao tác “resume” đơn thuần không làm material tin cậy trở lại. Phải xác định **material nào đã lộ**, dữ liệu nào bị ảnh hưởng và cần **revoke, rotate, rewrap, re-encrypt hoặc key destruction** nào.

### 10.6. Destroy và crypto-erasure

**Hủy KEK** khiến những EDK chỉ còn được bảo vệ dưới KEK đó **không thể mở lại**, nếu không còn bản copy/recovery path phù hợp. Điều này có thể hỗ trợ crypto-erasure trong một số mô hình, nhưng không được kết luận “đã xóa dữ liệu” khi:

- KEK còn trong backup/replica/escrow.
- DEK đã được unwrap và lưu ở host hoặc phía khách hàng.
- Root/derived key còn cho phép **rederive** KEK.
- Ciphertext có EDK thứ hai dưới recipient key khác.
- Plaintext đã được export ra hệ thống khác.

Trước khi destroy, cần **key dependency inventory**, retention/legal hold, bản sao lưu và thử khôi phục dữ liệu theo phạm vi hợp lệ. **Xóa metadata/key ID khỏi database khác với key material destruction**; nên giữ tombstone/audit theo policy để ngăn tái sử dụng ID.

## 11. Backup, recovery và KMS outage

### 11.1. Muốn khôi phục dữ liệu cần những thành phần nào?

Một bản backup chỉ chứa **ciphertext payload** thường **không đủ**. Cần:

1. **Ciphertext/tag** và content nonce.
2. **EDK/wrapped DEK** đúng record.
3. **KEK key ID/version và provider mapping** hoặc recipient private key tương ứng.
4. **KEK material/restore path** hợp lệ theo KMS/HSM provider.
5. **AAD/encryption context** và format/algorithm versions để tái tạo.
6. **IAM/quyền phục hồi** được phê duyệt, cùng key lifecycle state cho phép Unwrap/Decrypt.
7. **Dữ liệu nghiệp vụ** cần để xác thực record/tenant và tránh lấy EDK sai scope.

**Một bản backup đã được Encrypt nhưng thiếu wrapped DEK hoặc KEK version có thể không restore được**. Ngược lại, lưu raw KEK cạnh ciphertext trong backup chỉ để restore nhanh tạo ra ranh giới bảo vệ yếu.

### 11.2. Disaster recovery của KEK

KMS/HSM có thể hỗ trợ replication/backup/key import/secure domain recovery, nhưng **ngữ nghĩa và giới hạn khác nhau**. Một key non-exportable vẫn có thể có **secure HSM backup** mà ứng dụng không thể xuất raw bytes. Do đó:

- Kiểm tra provider có hỗ trợ **cùng key material, key identifier/version và key usage** sau restore hay không.
- Thử mở **EDK lịch sử** sau restore, không chỉ thử tạo key mới.
- Giới hạn và kiểm toán quyền Backup/Restore/Export/Destroy, có independent approval với thao tác nhạy cảm.
- Đảm bảo DR không dựa vào **một cá nhân giữ HSM quorum share** hoặc một service account không còn owner.
- Xác định retention của backup key material để xử lý crypto-erasure có chứng cứ.

### 11.3. KMS timeout hoặc region outage

Không giải quyết outage bằng cách **hardcode một raw KEK trong source code** hoặc lưu KEK plaintext trên disk. Quy trình có thể:

~~~text
KMS unavailable?
    |
    +-- Operation chưa có plaintext DEK:
    |     fail closed / queue / approved DR route
    |
    +-- Local DEK lease còn hiệu lực:
    |     xử lý theo policy thời hạn và scope đã duyệt
    |
    +-- Local DEK lease hết hạn:
          KHÔNG tự kéo dài vô hạn
          chuyển sang đường DR hoặc báo lỗi có kiểm soát
~~~

Availability phải được cân bằng với confidentiality: một cache DEK dài hạn giúp đọc khi KMS outage nhưng cũng làm tăng exposure và có thể bỏ qua revocation. Quy tắc **TTL, maximum stale lifetime, credential revocation và key state** phải được định nghĩa **trước khi xảy ra sự cố**.

### 11.4. Tính nhất quán nhiều region và event order

Nếu **KEK-v3** bị suspend ở region A nhưng region B còn cache policy cũ, các request có thể thấy kết quả khác nhau. Cần:

- Tài liệu hóa effective time/propagation của provider.
- Gắn **policy/key state revision** và key version rõ ràng trong inventory.
- Chống **stale events** làm re-enable key hoặc đổi alias về target cũ.
- Áp dụng idempotent retry và data migration compare-and-swap.
- Audit những operation hoàn thành trong cửa sổ chuyển trạng thái.

Không được suy từ một event **RotateCompleted** rằng mọi EDK đã được rewrap; phải thống kê dependencies và có bằng chứng đối soát storage thực tế.

## 12. Audit, key inventory và kiểm soát vận hành

### 12.1. Key inventory tối thiểu

| Nhóm | Metadata cần có |
|---|---|
| **KEK identity** | provider/account/partition/region, key ID/version, algorithm, state |
| **Ownership** | owner, tenant, service, environment, approved purpose |
| **Key hierarchy** | root/family, KEK version, EDK references, backup/restore domain |
| **Data dependencies** | record/object dataset, encrypted DEK count, cipher version, retention |
| **Access** | principals, key policy, grants, authorization context, expiry |
| **Rotation** | active/wrapping version, old/unwrapping versions, migration status |
| **Audit** | create, wrap, unwrap, rewrap, grant/revoke, disable, destroy events |
| **Recovery** | key material restore contract, backup tests, incident owner |

**Inventory không phải nơi chứa raw KEK hoặc plaintext DEK.** Nó chứa metadata để quản trị, ánh xạ key references và truy vết lifecycle. Các key IDs có thể lộ cấu trúc tenant hoặc hệ thống, nên inventory cũng cần quyền đọc và retention phù hợp.

### 12.2. Audit những gì và không log gì?

Nên ghi:

- authenticated principal/workload, tenant, request ID;
- key ID/version thực dùng và provider scope;
- operation như GenerateDataKey, Wrap, Unwrap, Decrypt, Rewrap, Rotate;
- policy decision, outcome, thời điểm và correlation ID;
- migration revision, error category, số EDK đã xử lý;
- incident/approval reference cho key state hoặc key material changes.

**Không ghi** plaintext DEK/KEK, private key, KMS raw response, passwords, token, dữ liệu khách hàng hoặc plaintext chỉ để “debug lỗi unwrap”. **EDK** tuy là ciphertext của khóa cũng cần được coi là dữ liệu nhạy cảm theo context/retention; không nên in toàn bộ blob vào log.

### 12.3. Metrics và cảnh báo

Các chỉ số hữu ích:

- **Số Unwrap/Decrypt calls** theo principal, tenant, KEK version và tỷ lệ lỗi.
- **Số EDK còn phụ thuộc KEK version cũ** sau rotation.
- **Tỷ lệ rewrap thành công** và record revisions còn chờ.
- **Số DEK plaintext cache entries** và TTL vượt policy.
- **Số key policies/grants** có quyền Decrypt/Sign/Unwrap quá rộng.
- **Nonce/invocation counters** hoặc usage limits theo key nếu thiết kế hỗ trợ.
- **Tỷ lệ authentication failures** bất thường trên EDK/content, kiểm soát không biến lỗi thành oracle.
- **Trạng thái backup/restore test** của KEK và EDK.
- **Thời gian revoke effective** và những stale sessions còn hiện hữu.

Không khẳng định không có key leak chỉ vì logs không ghi key material. Memory dumps, provider exports, backup snapshots và raw plaintext DEK từng đi qua application vẫn cần kiểm soát riêng.

## 13. Threat model: Các lỗi DEK encryption phổ biến

| Sai lầm | Hậu quả có thể xảy ra | Kiểm soát phù hợp |
|---|---|---|
| Lưu **plaintext DEK** cạnh ciphertext | Ai đọc database có thể giải mã payload | Wrap/Encrypt DEK, KEK độc lập trong KMS/HSM |
| Lưu raw KEK cùng database/backup EDK | Hai lớp mã hóa mất ý nghĩa ranh giới | Tách nơi lưu, IAM và secure backup domain |
| Tự bọc DEK bằng **AES-ECB** hoặc XOR | Không có bảo vệ integrity/không đúng security contract | Dùng AES-KW/KWP, AEAD hoặc KMS-approved algorithm |
| Dùng AES-GCM **wrapNonce cố định** cùng KEK | Nonce reuse phá an toàn AEAD của lớp EDK | Unique nonce per KEK, invocation limits và key rotation |
| Dùng lại **payloadNonce** với cùng DEK | Mất confidentiality/integrity của payload | Unique nonce per DEK across all replicas |
| Dùng chung một key làm **DEK và KEK** | Key purpose confusion và tăng blast radius | Key separation/domain separation và purpose-specific policy |
| Không xác thực **encrypted DEK** | Bit-flipping/tráo key material hoặc key confusion | Key-wrap integrity/tag verification |
| Không ràng buộc EDK với tenant/record | EDK swapping hoặc confused-deputy behavior | Context binding, AAD, authorization trước Unwrap |
| Chỉ dùng **tenant ID do client đưa vào** | KMS có thể mở key tenant khác | Authenticated tenant, record ownership, IAM |
| Chỉ lưu **alias current-key** | Rotate làm không tìm được KEK cũ | Ghi immutable key ID/version hoặc provider ref |
| Tin trường **algorithm** từ storage | Downgrade/algorithm confusion | Allowlist và key type/purpose checks |
| Không có schema version/AAD encoding | Khác serializer dẫn tới authentication failure | Canonical encoding/versioned protocol |
| Gắn **KEK version vào content AAD** rồi rewrap | GCM payload tag sai sau migration | Tách content/wrap binding, migration có kế hoạch |
| Rewrap không bảo vệ revision | Ghi EDK mới không khớp ciphertext mới | Atomic update, compare-and-swap |
| Tự động thử mọi KEK khi Unwrap lỗi | Key enumeration/oracle và phí KMS tăng | Resolve đúng key version, bounded fail-closed errors |
| KMS role được quyền **Decrypt mọi KEK** | Một RCE/confused deputy mở được nhiều tenant | Least privilege, resource authorization, audit |
| DEK plaintext cache quá lâu | Unwrap revoke không chặn decrypt offline | TTL/capacity/invalidation, workload isolation |
| Heap dump/log chứa DEK | Secret bị phát tán qua telemetry/support | Memory hygiene, secure diagnostics, secret redaction |
| KEK rotation nhưng không rewrap/cập nhật dependency | Dữ liệu cũ vẫn cần KEK cũ và có thể không restore | Key inventory, lazy/active rotation plan |
| DEK đã lộ nhưng chỉ rewrap | Đối thủ vẫn giải mã được ciphertext cũ | Thay DEK, re-encrypt, incident response |
| Destroy KEK không kiểm tra archive/backup | Mất khả năng mở EDK lịch sử | Dependency review và restore testing |
| Đổi sang RSA-OAEP nhưng tin public key đầu vào | DEK được mã hóa tới khóa của attacker | Recipient key trust/PKI/pinning |
| Chia sẻ EDK cho quá nhiều recipients | Tăng số private keys có thể mở payload | Recipient minimization, policies và audit |
| Không giới hạn kích thước envelope | Parser/DoS, bất thường trước KMS call | Bounds checks, format validation, quotas |
| Không chống **replay/rollback envelope cũ** | Bản mã cũ hợp lệ được dùng lại | Record revision/anti-rollback policy ngoài AEAD |

### 13.1. Authentication failure không nói được nguyên nhân duy nhất

Một lỗi **AEADBadTagException** có thể xuất phát từ:

- EDK/ciphertext bị sửa;
- sai KEK/DEK material hoặc version;
- sai nonce hoặc AAD encoding;
- wrapper metadata bị thay;
- lỗi migration/retry;
- ciphertext bị hỏng do storage/transport;
- thậm chí thay đổi record context có chủ đích.

Đừng tự động quy kết “attacker đã sửa dữ liệu” khi chưa có evidence. **Không tiết lộ chi tiết “key tồn tại”, “key đúng nhưng context sai”, “tag sai ở byte nào” cho caller không tin cậy**; có thể giữ thông tin chẩn đoán phù hợp trong audit nội bộ đã bảo vệ.

### 13.2. Những giới hạn của AEAD cần nhớ

AEAD chứng minh **tính xác thực của dữ liệu đối với một key và AAD cụ thể**, không chứng minh:

1. **Caller** có quyền truy cập bản ghi.
2. **KEK** được tạo bởi provider đáng tin nếu registry bị chiếm.
3. Ciphertext là **phiên bản mới nhất** (không tự chống rollback).
4. Plaintext chưa từng bị đọc bởi một principal khác trước đó.
5. Plaintext DEK không tồn tại trong heap dump hoặc backup ngoài quyền.
6. Quyền Sign/Decrypt/Unwrap đã bị thu hồi trên mọi session.

Vì vậy DEK encryption cần **cryptographic correctness + authorization + operational lifecycle** để tạo thành một hệ thống an toàn.

## 14. Kiểm thử kỹ thuật và hành vi thất bại

### 14.1. Bộ kiểm thử tối thiểu

| Test | Kết quả mong đợi | Lớp được kiểm |
|---|---|---|
| Encrypt mới bằng KEK Active | Có EDK + ciphertext hợp lệ | Data plane + key registry |
| Unwrap EDK đúng KEK/version/context | DEK hợp lệ và payload verify thành công | Key protection |
| KEK sai version | Từ chối/unwrap authentication error | Key resolution + wrap integrity |
| Đổi tenant/record của envelope | Bị deny hoặc tag failure | Authorization + AAD |
| Tráo một byte EDK/tag | Không trả DEK plaintext | Wrap integrity |
| Tráo content nonce/ciphertext/tag | Không trả plaintext đã tin cậy | Content integrity/wrap binding |
| Thay algorithm hoặc format ngoài allowlist | Bị từ chối trước crypto hoặc theo protocol | Input validation |
| Rotate KEK, giữ data ciphertext | Rewrap đúng, decrypt vẫn được | Rewrap + metadata binding |
| Đổi DEK và re-encrypt payload | Payload mới hợp lệ, key scope mới | DEK rotation |
| Cố Wrap với KEK đã DECRYPT_ONLY | Bị chặn | Lifecycle policy |
| KMS key Suspended/Disabled | Unwrap theo policy bị deny | Provider enforcement |
| Gọi Unwrap từ tenant khác | Deny bất kể biết EDK và key ID | Access control |
| Migration với hai ghi đồng thời | Không tạo EDK/payload revision mismatch | Transaction/concurrency |
| Cache DEK quá TTL | Không tiếp tục dùng ngoài policy | Secret lifecycle |
| KMS timeout/region failure | Retry có giới hạn/fail closed/approved DR | Availability and security |
| Restore archive bằng key version cũ | Đọc được theo quyền hợp lệ | Backup/retention |
| Raw DEK xuất hiện trong log hoặc dump test | Cảnh báo vi phạm và xử lý bảo mật | Operational controls |
| Envelope cũ replay trên cùng record | Bị phát hiện theo revision policy nếu cần | Business anti-rollback |

**Không kiểm thử trên raw production key bằng cách in hoặc export nó vào test harness.** Dùng **synthetic key/ciphertext**, provider test partition được cho phép và data-plane negative tests không tiết lộ dữ liệu thật.

### 14.2. Fault injection có kiểm soát

Một số tình huống cần kiểm tra ngoài happy path:

- **KMS Decrypt trả lỗi permission:** không fallback sang hardcoded KEK hoặc dùng key khác tự động.
- **KMS timeout sau khi unwrap có thể đã hoàn thành:** retry phải idempotent theo semantics; không tăng số lần wrap nonce trùng nếu tự mã hóa lại.
- **EDK tồn tại nhưng content thiếu/truncated:** từ chối trước khi trả plaintext; audit format/integrity category.
- **Đổi alias trong lúc request đang chạy:** record phải lưu đúng resolved KEK version đã thực sự wrap.
- **Crash giữa migration rewrap:** dữ liệu vẫn ở một revision self-consistent, không có trạng thái nửa cũ nửa mới.
- **Multi-region key policy replication chậm:** xác định effective time và deny/allow theo policy có chứng cứ.
- **Backup thiếu một key version:** phát hiện trong DR drill trước khi retirement/destruction.
- **Cipher format v1/v2 cùng tồn tại:** parser và canonical AAD theo version, không thử sai algorithm rồi fallback mơ hồ.

### 14.3. Code review cho DEK encryption

Khi review một pull request, nên hỏi:

1. **DEK có được sinh mới đúng scope** hay vô tình dùng chung static key?
2. **Plaintext DEK đi qua lớp nào**, có bị serialize/log/copy thành String không?
3. **KEK có được quản lý đúng policy**, có non-exportable nếu yêu cầu không?
4. **Key ID/version** ghi trong record là thực dùng hay chỉ alias trước khi resolve?
5. **Nonce uniqueness** có xét mọi instance/restart/migration với cùng key không?
6. **AAD** có encoding xác định, binding đúng và không biến caller input thành authorization không?
7. **Unwrap error** có fail closed và tránh trả plaintext/tag diagnostics nhạy cảm không?
8. **Rewrap** có bảo toàn content ciphertext/AAD và atomic envelope revision không?
9. **DEK compromise** có buộc xử lý re-encrypt thay vì chỉ rewrap không?
10. **DR plan** có đủ EDK, KEK material/version và restoration permissions không?

## 15. Incident response: KEK và DEK bị lộ có hậu quả khác nhau

### 15.1. Trường hợp plaintext DEK bị lộ

Ví dụ một heap dump có khả năng chứa DEK của 500 hóa đơn và đã được một principal không có thẩm quyền tải xuống.

1. **Cô lập đường lộ:** giới hạn quyền truy cập dump và khả năng tạo thêm dump; bảo toàn bằng chứng theo quy trình.
2. **Xác định DEK scope:** inventory record IDs, ciphertext/backup/replica còn được bảo vệ bởi DEK bị ảnh hưởng.
3. **Đánh giá tính tin cậy:** dump thực sự có thể chứa raw DEK không, có log đọc file hay sự kiện export không?
4. **Ngừng/giới hạn key use** theo mức độ sự cố; thu hồi credential và phiên liên quan.
5. **Tạo DEK mới** bằng cơ chế được phê duyệt; re-encrypt dữ liệu khi cần theo record scope và transactional migration.
6. **Ghi EDK mới** dưới KEK được phép, dùng nonce mới và AAD/schema đúng.
7. **Cập nhật cache, audit và phụ thuộc**, kiểm tra restore, xử lý plaintext/ciphertext đã có khả năng bị sao chép.

**Đổi KEK hoặc rewrap EDK cũ không loại bỏ rủi ro với DEK mà attacker đã biết.** Đó là lý do inventory phải cho biết chính xác một DEK đã được dùng cho những record nào.

### 15.2. Trường hợp KEK bị lộ

Một KEK có thể bọc hàng triệu DEK. Nếu raw KEK bị lộ, **blast radius thường lớn hơn lộ một DEK đơn lẻ**, tùy số EDK còn tồn tại, khả năng truy cập EDK của attacker và cấu trúc key hierarchy.

Runbook:

1. Xác định **KEK key ID/version, provider, tenant và phạm vi EDK**.
2. Thu hồi quyền sử dụng và cô lập bản sao/credential có rủi ro.
3. Tạo **KEK mới** trong KMS/HSM, phê duyệt alias/key policy.
4. **Đánh giá EDK cũ đã có thể bị unwrap bởi attacker hay không**. Nếu attacker có KEK và EDK, plaintext DEK tương ứng có thể đã lộ.
5. Rewrap cho dữ liệu cần tiếp tục dùng, nhưng **đừng coi rewrap là khôi phục confidentiality của những DEK có thể đã lộ**.
6. Với DEK có khả năng bị lộ, ưu tiên thay DEK và **re-encrypt** dữ liệu theo risk assessment.
7. Kiểm tra key versions, backup, consumer, key status và khả năng restore trước khi destroy KEK cũ.
8. Audit/sự cố: actor, times, keyRefs, grants, affected records và quyết định giảm thiểu; không đưa raw KEK/DEK vào ticket.

### 15.3. Trường hợp chỉ có quyền Unwrap bị lạm dụng

Đôi khi **KEK non-exportable** vẫn an toàn về bytes, nhưng một service account có quyền **Unwrap rộng** bị chiếm và attacker đã gọi KMS để mở EDK. Lúc này cần xử lý:

- **Revoke credential/grants**, phiên và workload điều khiển.
- **Kiểm tra KMS audit** để xác định EDK nào đã được mở.
- **Đánh giá dữ liệu/DEK bị trả về** và quyền đọc ciphertext của attacker.
- **Giảm quyền** theo tenant, purpose, resource, duration và monitoring.
- Quyết định DEK rotation/re-encryption theo exposure, **không mặc nhiên kết luận KEK material đã lộ**.

### 15.4. Trường hợp private key bảo vệ DEK bị lộ

Nếu envelope dùng RSA-OAEP hoặc public-key wrapping tới recipient, **private encryption key** bị lộ có thể cho attacker mở **DEKs đã được bảo vệ bằng public key tương ứng**, nếu họ có recipient ciphertext. Đổi certificate hay recipient alias không tự bảo vệ lại những envelope cũ. Cần thay recipient keypair và **rewrap/migrate recipient entries**, đánh giá **DEK/ciphertext exposure**, phối hợp owner và trust store.

**Private signing key** là tài sản khác private decryption key: dùng để Sign/Verify, không nên tái sử dụng làm khóa giải mã DEK chỉ để tiết kiệm key management. Nếu signing key bị lộ, cần xử lý **chữ ký, JWKS/certificate và phiên/token**, không chỉ rewrap EDK.

## 16. Case study: Mã hóa chứng từ nhiều tenant với KMS

### 16.1. Thiết kế ban đầu

Một nền tảng thanh toán chạy nhiều instance Java:

~~~text
Tenant A: invoice-001, invoice-002, ...
Tenant B: invoice-101, invoice-102, ...
Storage: relational database + object archive
Crypto: AES-256-GCM per invoice
KMS: KEK per tenant hoặc key family theo chính sách
~~~

Team triển khai đầu tiên theo cách: **một DEK chung cho tất cả tenant**, ghi DEK Base64 vào một cột cạnh ciphertext, và chỉ dùng alias **current-kek** trong metadata để “tương lai có thể rotate”.

**Vấn đề:**

- **Base64(DEK)** vẫn là DEK bản rõ, ai đọc database có thể giải mã.
- **Một DEK toàn hệ thống** làm blast radius rất lớn và khó kiểm soát nonce uniqueness.
- **Alias động** không đủ để xác định KEK version lịch sử.
- **KMS role toàn cục** có thể Unwrap mọi tenant, dễ thành confused deputy.
- Không có **AAD record/tenant binding**, nên metadata có thể bị tráo.
- Không có **restore test**, dẫn tới rủi ro mất dữ liệu khi KEK cũ bị xóa.

### 16.2. Thiết kế cải tiến

1. **Mỗi invoice có DEK riêng** được sinh từ nguồn CSPRNG hoặc KMS GenerateDataKey, đúng AES-256.
2. **Payload** được mã hóa bằng AES-GCM, nonce theo DEK và content AAD chứa tenant, invoice ID, format version.
3. **KEK của tenant** được giữ trong approved KMS/HSM; ứng dụng chỉ có rights Wrap/Unwrap theo workload identity và key purpose được duyệt.
4. **EDK** được lưu cùng ciphertext, nonce/tag và **immutable KEK ID/version**; không lưu plaintext DEK.
5. **Binding** bảo vệ tenant/record/dekId, tránh tráo EDK hoặc payload; KMS context cũng dùng metadata đã xác thực theo provider semantics.
6. **AuthN/AuthZ nghiệp vụ** kiểm tra caller có quyền với invoice trước khi gọi KMS.
7. **Tách roles:** writer tạo DEK mới/Wrap, reader chỉ Unwrap theo record được phép, admin quản lý policy nhưng không được Decrypt mặc định.
8. **Rotation:** KEK mới dùng cho EDK mới; migration worker rewrap các EDK cũ có compare-and-swap và audit. Nếu DEK lộ, thay DEK và re-encrypt.
9. **Memory:** DEK plaintext chỉ sống trong crypto boundary/lease giới hạn, không log/serialize hay đưa vào session/cache vô thời hạn.
10. **Backup:** lưu đủ ciphertext, EDK, KEK reference, AAD schema và KMS restore plan; định kỳ thử mở invoice archive mẫu.
11. **Monitoring:** theo dõi Unwrap theo principal/key version, số EDK còn trên KEK cũ, cache age và lỗi authentication.
12. **Incident:** khi service token bị lộ, revoke grants/session, điều tra KMS Unwrap calls; đánh giá liệu DEK/record nào cần re-encrypt.

### 16.3. Kết quả mong đợi và giới hạn

Kiến trúc mới giới hạn tác động của một DEK bị lộ, giúp audit đúng key version, hỗ trợ rotate KEK mà không buộc decrypt/re-encrypt toàn bộ payload trong mọi trường hợp, và cải thiện khả năng phục hồi lịch sử.

Tuy nhiên **envelope encryption không tự chống lại RCE trong một process được phép lấy plaintext DEK**, cũng không tự sửa IAM quá rộng, AEAD nonce reuse, một public key recipient không được xác thực hoặc dữ liệu plaintext đã bị đọc. Các lớp bảo vệ phải hoạt động đồng bộ.

## 17. Checklist DEK encryption trước khi đưa vào production

1. **Purpose:** DEK chỉ dùng mã hóa nội dung, KEK chỉ bảo vệ key material theo chính sách? Có tránh tái sử dụng một key cho Sign/HMAC/Wrap tùy tiện?
2. **Entropy:** DEK/KEK được sinh bằng CSPRNG hoặc KMS/HSM approved provider, không từ timestamp/password entropy thấp?
3. **DEK scope:** per-record/per-object/per-batch được lựa chọn theo blast radius, capacity, nonce và retention?
4. **KEK storage:** KEK nằm trong approved KMS/HSM/crypto boundary, không raw key trong Git, database, CI, image hoặc logs?
5. **Key mechanism:** dùng AES-KW/KWP, AEAD hoặc provider key-wrap được duyệt, không tự chế AES-ECB/XOR?
6. **Raw DEK exposure:** biết DEK plaintext hiện diện ở process/SDK/native layer nào và thời gian bao lâu?
7. **Nonce content:** uniqueness của AES-GCM nonce được bảo đảm/giới hạn **theo từng DEK** trên mọi instance và retry?
8. **Nonce wrap:** nếu dùng AEAD để wrap, nonce **không tái sử dụng với cùng KEK** trên mọi server/region/migration?
9. **Metadata binding:** tenant, record, purpose, algorithm, DEK reference và key version được đưa vào context/AAD theo schema rõ?
10. **Canonical encoding:** có version và encoding length-prefix/canonical để tránh AAD ambiguity?
11. **KMS authorization:** principal/tenant/resource được xác thực trước Unwrap, IAM/key policy theo key ID/version và purpose?
12. **Algorithm allowlist:** parser không cho storage/caller tùy ý downgrade mode hoặc thay provider URL?
13. **Key IDs:** envelope ghi resolved immutable KEK ID/version, không chỉ alias current có thể đổi?
14. **Envelope completeness:** có content nonce/tag, EDK, wrap parameters, context và mọi metadata cần giải mã lịch sử?
15. **Rewrap semantics:** content AAD không bị thay ngoài ý muốn, EDK mới và KEK metadata được ghi atomic?
16. **DEK rotation:** có đường thay raw DEK và re-encrypt dữ liệu khi DEK lộ hoặc hết cryptoperiod?
17. **Concurrency:** compare-and-swap/revision kiểm soát update song song và rollback envelope cũ?
18. **Failure handling:** Unwrap/AEAD thất bại fail closed, không trả plaintext/key bytes và không thử vô hạn mọi KEK?
19. **Cache lifecycle:** TTL/capacity/tenant scope, invalidation khi revoke/rotate và hiểu giới hạn zeroization JVM?
20. **Restore:** backup có đầy đủ EDK, ciphertext, nonce, AAD scheme, KEK versions và quyền restore? Đã thử DR?
21. **Lifecycle:** biết khi nào KEK được phép Encrypt/Wrap hay chỉ Decrypt/Unwrap, và khi nào có thể Destroy?
22. **Audit:** ghi actor/key reference/operation/result, không log raw DEK, KEK, private key, plaintext hoặc token?
23. **Incident response:** có runbook riêng cho lộ DEK, KEK, recipient private key và lạm dụng KMS API?
24. **Negative tests:** tampered EDK, wrong tenant, wrong key version, modified payload/AAD và disabled key đều bị từ chối?
25. **External recipients:** RSA-OAEP/KEM public key được xác thực từ trust store/PKI/pinning và cập nhật rotation đúng cách?
26. **Non-repudiation và signatures:** không nhầm envelope encryption với digital signature; nguồn gửi cần được xác thực/ký riêng khi threat model yêu cầu?

### Câu hỏi tự kiểm tra

**Câu 1.** DEK encryption khác gì mã hóa dữ liệu bằng DEK?

**Trả lời:** Mã hóa dữ liệu dùng **DEK** bảo vệ payload; DEK encryption/key wrapping dùng **KEK** hoặc recipient public key bảo vệ **chính DEK**. Hai lớp có quyền, nonce, metadata và vòng đời riêng.

**Câu 2.** Có thể lưu EDK cùng payload ciphertext trong một database không?

**Trả lời:** **Có thể**, đây là pattern của envelope encryption khi KEK độc lập được bảo vệ, quyền Unwrap được kiểm soát và metadata có integrity/context binding. Không lưu DEK bản rõ cạnh ciphertext.

**Câu 3.** Tại sao dùng AES-GCM wrap DEK phải có wrap nonce mới cho mỗi lần wrap dưới cùng KEK?

**Trả lời:** AES-GCM yêu cầu nonce không bị dùng lại với cùng key trong encryption operations. Nonce reuse với KEK có thể phá tính bí mật và xác thực của EDK.

**Câu 4.** AES-KW/AES-KWP có cần quản lý random 96-bit wrap nonce như AES-GCM không?

**Trả lời:** **Không theo cùng cách.** Chúng là cơ chế wrapping có cấu trúc/requirements riêng. Phải làm theo thuật toán/provider contract, không áp nhầm metadata AES-GCM.

**Câu 5.** KMS giữ KEK non-exportable có bảo đảm mọi DEK không xuất hiện trong JVM không?

**Trả lời:** **Không.** Các API như GenerateDataKey/Decrypt có thể trả **plaintext DEK** cho caller. Cần kiểm soát RAM, TTL/cache, dump và quyền sử dụng.

**Câu 6.** Một record chỉ lưu alias current-kek. Khi alias đổi sang KEK-v4, ứng dụng luôn mở được EDK tạo dưới KEK-v3 chứ?

**Trả lời:** **Không bảo đảm.** Alias động không thể thay thế key ID/version thực sự dùng lúc wrap. Cần record/provider reference đủ để resolve khóa lịch sử.

**Câu 7.** Có thể rewrap từ KEK-v3 sang KEK-v4 mà giữ nguyên content ciphertext không?

**Trả lời:** **Có**, khi raw DEK không đổi và content AAD/schema không phụ thuộc metadata KEK thay đổi. EDK và wrap metadata phải được tạo lại và cập nhật nguyên tử.

**Câu 8.** Nếu DEK đã bị lộ, rewrap DEK cũ dưới KEK mới có đủ bảo vệ ciphertext không?

**Trả lời:** **Không.** Người biết DEK vẫn có thể giải mã ciphertext dùng DEK đó. Cần đánh giá thay DEK, re-encrypt và xử lý dữ liệu có thể đã bị thu thập.

**Câu 9.** AAD chứa tenantId từ request có thay thế kiểm tra IAM/business authorization không?

**Trả lời:** **Không.** AAD xác thực bytes trong context nhưng không chứng minh caller có quyền với tenant/record. Phải lấy tenant từ authenticated identity và kiểm tra quyền trước Unwrap.

**Câu 10.** Nếu bị sửa một byte của EDK được bảo vệ bằng AES-GCM, hệ thống nên làm gì?

**Trả lời:** **Từ chối Unwrap** khi authentication tag không hợp lệ, không trả hay dùng plaintext DEK. Ghi audit metadata phù hợp và điều tra nếu cần, không log raw key.

**Câu 11.** KMS bị outage có nên tự chuyển sang một KEK cố định trong source code không?

**Trả lời:** **Không.** Cách này phá ranh giới bảo vệ và quyền truy cập. Dùng DR được phê duyệt, cache lease có giới hạn nếu policy cho phép hoặc fail closed.

**Câu 12.** Vì sao không destroy KEK-v3 ngay sau khi chuyển alias sang KEK-v4?

**Trả lời:** Nhiều EDK lịch sử có thể vẫn chỉ được bảo vệ dưới KEK-v3, bao gồm backup/archive. Phải kiểm tra dependencies, rewrap/migration và restore trước khi hủy.

**Câu 13.** Digest SHA-256 của content ciphertext trong wrap AAD có phải tự nó là chữ ký số không?

**Trả lời:** **Không.** Hash không có khóa không xác thực nguồn. Trong ví dụ, digest được bảo vệ thông qua **AEAD authentication tag của lớp wrap**; chữ ký số và trust của sender là cơ chế riêng.

**Câu 14.** Nếu public key recipient đến từ URL do attacker đưa, RSA-OAEP có bảo đảm chỉ đối tác thật giải mã được DEK không?

**Trả lời:** **Không.** RSA-OAEP bảo vệ theo public key được sử dụng; nếu đó là key attacker, attacker có thể giải mã. Phải xác thực danh tính recipient và nguồn public key.

**Câu 15.** AES-GCM tag hợp lệ có tự bảo đảm record đó là bản mới nhất không?

**Trả lời:** **Không.** Một envelope cũ còn nguyên cũng có thể có tag hợp lệ. Nếu cần chống replay/rollback, thêm record revision/sequence và policy ở tầng storage/business.

**Câu 16.** Nếu lộ quyền KMS Unwrap nhưng KEK vẫn non-exportable, có thể bỏ qua incident response vì material chưa bị xuất không?

**Trả lời:** **Không.** Đối thủ có thể dùng API để mở EDK và lấy plaintext DEK. Phải thu hồi quyền, điều tra Unwrap events, xác định affected records và quyết định rotation/re-encryption.

## 18. Tổng kết

**DEK encryption** là phần quan trọng tạo nên envelope encryption: **payload được mã hóa bằng DEK, còn DEK được bảo vệ bởi KEK/recipient mechanism**. Kiến trúc này cho phép tách quyền truy cập dữ liệu khỏi quyền quản lý root/key-encryption material, giảm phạm vi sự cố và hỗ trợ KEK rotation mà không luôn phải mã hóa lại payload.

Một hệ thống đáng tin phải đồng thời bảo đảm:

- **Crypto correctness:** key wrapping/AEAD đúng thuật toán, nonce uniqueness theo từng key, tag verification và encoding metadata nhất quán.
- **Trust và authorization:** tenant/record/key purpose được xác thực trước KMS, key ID/version không thay IAM, recipient public key phải đáng tin cậy.
- **Lifecycle và recovery:** biết EDK nào phụ thuộc KEK version nào, phân biệt **rewrap** với **re-encrypt**, giữ khả năng mở dữ liệu lịch sử và chỉ destroy sau dependency/backup review.
- **Operations:** plaintext DEK trong JVM có lifetime và quyền giới hạn; KMS/HSM, audit, cache, incident response và DR được thực thi ở đúng điểm.

**Điểm cốt lõi:** **Mã hóa DEK không phải chỉ tạo thêm một lớp ciphertext.** Đây là thiết kế **key hierarchy, authenticated context, quyền sử dụng khóa và vòng đời độc lập giữa DEK với KEK**. Chọn đúng cơ chế bọc khóa, lưu đúng immutable key reference, dùng AAD/nonce chính xác và kiểm soát Unwrap ở KMS/HSM giúp dữ liệu được bảo vệ trong cả trạng thái lưu trữ, sử dụng, xoay vòng và khôi phục.
