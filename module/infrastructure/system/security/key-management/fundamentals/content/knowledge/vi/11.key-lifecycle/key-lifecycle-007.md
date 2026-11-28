# Generate key (Sinh khóa mật mã an toàn)

## 1. Generate key là gì?

**Generate key (sinh khóa)** là quá trình tạo **vật liệu khóa mật mã (key material)** đáp ứng yêu cầu của một thuật toán và chính sách bảo mật, bằng một cơ chế sinh khóa được thiết kế cho mật mã. Đây là điểm khởi đầu của vòng đời khóa: nếu khóa dễ đoán, bị lặp, sinh sai thuật toán hoặc bị lộ ngay lúc tạo, các bước lưu trữ, cấp quyền và xoay vòng sau đó không thể tự biến khóa yếu thành khóa mạnh.

Ví dụ, để mã hóa dữ liệu bằng AES-256-GCM, ứng dụng cần một khóa AES **256 bit được tạo từ nguồn ngẫu nhiên mật mã phù hợp**. Việc lấy chuỗi mật khẩu ngắn, băm SHA-256 rồi dùng 32 byte kết quả làm khóa **không tương đương** với sinh khóa AES ngẫu nhiên có độ khó đoán 256 bit.

Trong chương **Key lifecycle** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, Generate key kết nối trực tiếp với:

- **Mật mã đối xứng:** tạo DEK, KEK hoặc khóa HMAC đúng độ dài và mục đích.
- **Mật mã bất đối xứng:** sinh các cặp private/public key cho chữ ký số, mã hóa hoặc thỏa thuận khóa theo thuật toán.
- **Chữ ký số:** giữ private signing key bí mật và cấp phát public verification key đúng danh tính.
- **KMS/HSM:** tạo và bảo vệ khóa trong miền tin cậy, hạn chế xuất key material.
- **Envelope encryption:** tạo DEK độc lập rồi bọc bằng KEK, thay vì dùng một khóa duy nhất cho mọi dữ liệu.
- **IAM, kiểm toán và vòng đời:** quyết định ai được tạo khóa, khóa thuộc ai, dùng để làm gì, tồn tại bao lâu và xử lý thế nào khi có sự cố.

> **Phân biệt quan trọng:** *Sinh khóa* là tạo vật liệu mới; *cấp phát khóa* là đưa khóa hoặc quyền sử dụng khóa tới thành phần hợp lệ; *dẫn xuất khóa (derive key)* là tính keying material từ một bí mật đầu vào bằng KDF; *import khóa* là đưa vật liệu đã tồn tại vào hệ quản lý. Chúng có yêu cầu và rủi ro khác nhau.

~~~mermaid
flowchart LR
    A["Xác định mục đích và thuật toán"] --> B["Chọn miền sinh khóa: KMS/HSM hoặc CSPRNG"]
    B --> C["Generate key material"]
    C --> D["Gán key ID, version, owner, usage"]
    D --> E["Thiết lập quyền và lưu khóa"]
    E --> F["Kiểm tra sử dụng theo chính sách"]
    F --> G["ACTIVE: Encrypt/Decrypt/Sign..."]
    G --> H["Rotate / Revoke / Destroy"]
~~~

Một triển khai có thể tạo key material và metadata theo nhiều bước hoặc giao dịch khác nhau; sơ đồ trên nêu **trách nhiệm cần hoàn tất** trước khi khóa được đưa vào sử dụng, không quy định thứ tự API bắt buộc cho mọi nhà cung cấp.

## 2. Sinh khóa khác tạo một chuỗi byte ngẫu nhiên ở đâu?

Một chương trình có thể tạo ra 32 byte trông rất ngẫu nhiên. Tuy nhiên, chỉ có 32 byte chưa đủ để kết luận đã tạo được một khóa an toàn.

| Tiêu chí | Sinh byte ngẫu nhiên nói chung | Sinh khóa mật mã đúng cách |
|---|---|---|
| Nguồn | Có thể là PRNG thống kê hoặc dữ liệu bất kỳ | **CSPRNG/DRBG**, OS RNG hoặc HSM đáng tin |
| Độ dài | Theo nhu cầu ứng dụng | Theo **thuật toán, security strength và chính sách** |
| Phân bố | Có thể bị thiên lệch | Phù hợp quy tắc sinh khóa của thuật toán |
| Miền giá trị | Bất kỳ byte nào | Có thể cần giới hạn hoặc cấu trúc toán học riêng |
| Key usage | Không xác định | Rõ mục đích: encrypt, decrypt, sign, verify, wrap, unwrap... |
| Quyền | Thường chưa có | IAM, owner, môi trường, phạm vi sử dụng |
| Vòng đời | Không nhất thiết được theo dõi | Key ID/version, cryptoperiod, rotation/revocation/destruction |
| Kiểm toán | Có thể không có | Theo dõi ai tạo, khi nào, bằng chính sách nào |

**AES key** là một chuỗi bit có độ dài hợp lệ được tạo đúng yêu cầu mật mã. **ECDSA private key** thường là một số nguyên nằm trong miền giá trị của nhóm elliptic; **RSA private key** phải được sinh bằng quy trình tạo các tham số và số nguyên tố có kiểm tra cần thiết; **Ed25519** có cách sinh seed và private/public key riêng.

Vì vậy **không thể sinh 32 byte tùy ý rồi gắn nhãn "RSA private key" hoặc "ECDSA private key"**. Hãy dùng **KeyGenerator/KeyPairGenerator** hoặc API sinh khóa của KMS/HSM theo đúng thuật toán.

## 3. Xác định mục đích trước khi sinh khóa

Bước đầu tiên không phải là gọi random API, mà là xác định **vì sao khóa tồn tại**.

| Nhu cầu | Loại khóa thường dùng | Tác vụ được phép | Không nên nhầm với |
|---|---|---|---|
| Mã hóa tài liệu/bản ghi | **AES DEK** | Encrypt, decrypt | Signing key |
| Bảo vệ nhiều DEK | **KEK / KMS key** | Wrap, unwrap hoặc API mã hóa khóa phù hợp | DEK lưu cùng dữ liệu |
| Xác thực webhook nội bộ | **HMAC key** | GenerateMac, VerifyMac | Chữ ký số công khai |
| Ký JWT/phần mềm/chứng từ | **Private signing key** | Sign | AES key hoặc ECDH key |
| Xác minh chữ ký | **Public verification key** | Verify | Secret key |
| Thỏa thuận bí mật phiên | **ECDHE/X25519 private key** | KeyAgreement theo giao thức | Static signing key |
| Bảo vệ secret bằng passphrase | **Password-derived key** | Bọc/giải bọc hoặc kiểm tra mật khẩu theo thiết kế | Khóa ngẫu nhiên từ CSPRNG |
| Khóa phục hồi | **Recovery key** | Phục hồi được kiểm soát | Quyền giải mã thường ngày |

Từ mục đích, xác định thêm **algorithm**, **key size/curve**, **cryptoperiod**, **phạm vi tenant/môi trường**, **khả năng export**, **thời gian lưu giữ** và **hành vi khi thu hồi**.

Ví dụ, signing key phục vụ nhiều tháng có thể cần chứng chỉ và kế hoạch đồng bộ verifier. DEK cho một tài liệu có thể được tạo riêng, bọc dưới KEK và không cần phân phối công khai. Một ephemeral X25519 key chỉ phục vụ handshake thường không cần giữ lâu trong cơ sở dữ liệu.

### 3.1. Key usage và tách nhiệm vụ

Một ứng dụng chỉ cần **Encrypt** không mặc nhiên cần **Decrypt**; dịch vụ chỉ **Verify** chữ ký không cần private signing key. Nếu KMS hỗ trợ chính sách tác vụ riêng, hãy cấp đúng khả năng cần thiết.

**Không sử dụng một vật liệu khóa cho nhiều mục đích không liên quan** chỉ vì thuật toán cho phép nhận cùng một chuỗi byte. Tách key giúp giảm phạm vi sự cố và làm rõ quyền, giới hạn sử dụng, rotation và audit.

## 4. Entropy, CSPRNG và nguồn sinh khóa

### 4.1. Độ dài khóa không đồng nghĩa entropy

Một khóa có **256 bit độ dài** chỉ đạt mức khó đoán tương ứng nếu cách sinh thực sự cung cấp đủ bất định theo yêu cầu. Nếu một chương trình tạo:

~~~text
seed = currentTimeMillis()
key  = SHA256(UTF8(seed))
~~~

thì đối thủ biết khoảng thời gian tạo key có thể thử các seed ứng viên. SHA-256 không bổ sung entropy độc lập cho timestamp.

Một **CSPRNG (Cryptographically Secure Pseudorandom Number Generator)** hoặc **DRBG** dùng trạng thái được khởi tạo bằng entropy phù hợp để cung cấp byte khó dự đoán. Các nền tảng thường cung cấp cơ chế này qua **OS crypto RNG**, **Java SecureRandom**, thư viện mật mã đã được đánh giá hoặc **RNG bên trong HSM**.

### 4.2. Quy tắc nguồn ngẫu nhiên

- Ưu tiên **KeyGenerator, KeyPairGenerator hoặc API GenerateKey/GenerateDataKey** của hệ thống đã được đánh giá, thay vì tự tạo byte theo công thức.
- Trong Java, dùng **SecureRandom** theo provider đáng tin; **không** dùng java.util.Random, ThreadLocalRandom, timestamp, PID, UUID hoặc bộ đếm làm nguồn cho private key/DEK.
- Không tự seed một PRNG bằng hằng số hoặc dữ liệu dễ đoán rồi cho rằng nó an toàn vì output dài.
- Không coi việc **hash nhiều lần** là cách tăng entropy của input có ít khả năng.
- Kiểm tra hành vi khởi tạo khi **early boot, VM clone, snapshot/restore, process fork và thiết bị nhúng** nếu môi trường có những rủi ro này.
- Nếu nguồn random hoặc provider đáng tin **không sẵn sàng**, không tự chuyển sang nguồn yếu để tiếp tục tạo khóa.

### 4.3. Random không phải lúc nào cũng có nghĩa duy nhất

Một giá trị ngẫu nhiên hữu hạn có thể **va chạm**. Việc sinh những **DEK độc lập** bằng CSPRNG tạo xác suất trùng cực nhỏ nếu thuật toán và nguồn đúng, nhưng thiết kế phân phối khóa còn cần kiểm soát **ID, phiên bản, tenant và phạm vi sử dụng**.

Quan trọng hơn, **AES-GCM nonce** cần **không tái sử dụng dưới cùng khóa**; tạo nonce ngẫu nhiên là một cách đáp ứng **theo xác suất** trong giới hạn thích hợp, còn counter được cấp phát không trùng có thể phù hợp dù dễ dự đoán. **Nonce** không đồng nghĩa **khóa AES**, và yêu cầu uniqueness của nonce phải được quản lý riêng sau khi sinh key.

## 5. Sinh khóa đối xứng

### 5.1. AES DEK

**DEK (Data Encryption Key)** bảo vệ nội dung dữ liệu, ví dụ với **AES-GCM**. Các lựa chọn độ dài AES phổ biến là 128, 192 hoặc 256 bit, tùy chính sách và khả năng tương thích. Với một thiết kế chọn **AES-256-GCM**, ứng dụng cần 32 byte key material được sinh phù hợp.

Một bản ghi dữ liệu có thể lưu:

~~~yaml
# Metadata minh họa, không phải schema cố định của KMS
recordId: doc-904
tenantId: tenant-42
dataAlgorithm: AES-256-GCM
dataKeyRef: dek-doc-904
wrappingKeyRef: kms-documents-v3
encryptedDataKey: "<base64-encrypted-DEK>"
nonce: "<base64-12-byte-nonce>"
ciphertextWithTag: "<base64-ciphertext-and-tag>"
~~~

Bản ghi **không** nên lưu plaintext DEK cạnh ciphertext. **Encrypted DEK** và key references có thể lưu kèm ciphertext theo kiến trúc envelope encryption.

### 5.2. HMAC key

**HMAC-SHA-256** dùng một khóa đối xứng bí mật để tính authentication tag. Khóa nên được sinh từ CSPRNG với entropy thích hợp và được quản lý theo mục đích. Ví dụ một **khóa ngẫu nhiên 32 byte** là cấu hình thường dùng cho HMAC-SHA-256, nhưng cần tuân thủ giao thức và chính sách cụ thể.

Không nhầm **HMAC key** với SHA-256 digest: hash thông điệp không có khóa nên bất kỳ ai cũng có thể tính lại; HMAC dựa vào bí mật chia sẻ. Khi nhiều bên giữ cùng HMAC key, **mọi bên biết khóa đều có khả năng tạo MAC**.

### 5.3. KEK

**KEK (Key Encryption Key)** dùng để bảo vệ DEK. KEK có thể được sinh và giữ **bên trong KMS/HSM**, sau đó ứng dụng chỉ gọi API **wrap/unwrap hoặc encrypt/decrypt cho key material** theo chính sách. Tính năng cụ thể phụ thuộc nhà cung cấp và thuật toán.

Không cần và không nên **xuất KEK dạng rõ ra ứng dụng** nếu nghiệp vụ chỉ cần KMS wrap DEK và dịch vụ có thể thực hiện điều đó. Giữ KEK ở ranh giới bảo mật giúp giảm nơi xuất hiện key material và đơn giản hóa kiểm toán.

## 6. Sinh cặp khóa bất đối xứng

### 6.1. Khóa ký ECDSA

Khi tạo **ECDSA key pair**, private key phải nằm trong miền giá trị hợp lệ của curve, còn public key được suy ra theo quy tắc thuật toán. Ví dụ **NIST P-256 (secp256r1)** thường đi cùng **SHA256withECDSA** trong hệ thống ký phù hợp.

Private key phải bí mật. Public key có thể được công bố nhưng cần **xác thực danh tính** qua chứng chỉ/trust store/JWKS. Khi ký ECDSA, số bí mật **k theo từng chữ ký** còn có yêu cầu riêng: làm lộ hoặc dùng lại k sai cách có thể làm lộ private key. Việc sinh private key mạnh **không tự bảo đảm** từng thao tác Sign an toàn nếu provider tạo k sai.

### 6.2. Khóa Ed25519

**Ed25519** là thuật toán chữ ký thuộc họ **EdDSA**, khác ECDSA. Các API/provider cung cấp cách sinh private/public key phù hợp với Ed25519; **không** lấy một byte array tùy ý rồi đổi tên nó thành EC P-256 hay RSA.

### 6.3. Khóa RSA

**RSA key pair** phải được sinh bởi thuật toán có các kiểm tra toán học phù hợp. Không tự chọn hai số ngẫu nhiên bất kỳ làm số nguyên tố. Khi thiết kế mới, chọn kích thước và sơ đồ ký/mã hóa theo chuẩn/khả năng hỗ trợ, ví dụ **RSA-PSS** cho chữ ký trong nhiều trường hợp và **RSA-OAEP** nếu sử dụng RSA encryption phù hợp.

**Không dùng cùng một private key RSA cho mọi loại thao tác** nếu mục đích, policy hoặc giao thức không cho phép. Chữ ký số, giải mã và key transport cần được phân biệt rõ.

### 6.4. Khóa thỏa thuận phiên: ECDHE/X25519

Các cặp khóa **ephemeral ECDH/X25519** thường được sinh cho một handshake hoặc phạm vi ngắn theo giao thức, giúp thiết lập shared secret. **Key agreement tự nó không xác thực đối tác**; cần chứng chỉ/chữ ký/PSK và transcript binding để chống MITM.

Private ephemeral keys cần được giữ bí mật và giảm thời gian sống. Không ghi session secrets vào log vì có thể làm mất bảo vệ của **forward secrecy**.

### 6.5. Tổng kết

| Cơ chế | Key generation | Key usage | Cách kiểm tra |
|---|---|---|---|
| **AES** | KeyGenerator/CSPRNG hoặc KMS | Encrypt/Decrypt theo mode | AEAD tag hoặc kết quả decrypt hợp lệ |
| **HMAC** | CSPRNG hoặc KMS | GenerateMac/VerifyMac | Kiểm tra tag bằng secret |
| **ECDSA** | EC KeyPairGenerator/KMS-HSM | Sign/Verify | Public key và trust policy |
| **Ed25519** | Ed25519 KeyPairGenerator/KMS-HSM | Sign/Verify | Public key và trust policy |
| **RSA-PSS** | RSA KeyPairGenerator/KMS-HSM | Sign/Verify | Public key và tham số PSS nhất quán |
| **X25519** | X25519 KeyPairGenerator/provider | KeyAgreement | Kiểm tra shared secret trong giao thức có xác thực |

## 7. Generate key, derive key và import key

Ba thao tác có thể xuất hiện cùng một hệ thống nhưng không thể đánh đồng:

| Thao tác | Đầu vào | Đầu ra | Rủi ro nổi bật |
|---|---|---|---|
| **Generate** | Entropy và thông số thuật toán | Vật liệu khóa mới | RNG yếu, thông số sai, export không kiểm soát |
| **Derive** | Bí mật gốc, KDF, salt/info/context và tham số | Keying material dẫn xuất | Bí mật gốc yếu, thiếu domain separation, KDF không phù hợp |
| **Import** | Key material đã tồn tại và thông tin nguồn gốc | Khóa được đăng ký trong KMS/HSM/keystore | Khóa đã lộ, yếu hoặc từng dùng ở phạm vi khác |

### 7.1. HKDF không phải password KDF

**HKDF** thường dùng dẫn xuất nhiều khóa từ một bí mật mật mã có entropy phù hợp, như shared secret của giao thức thỏa thuận khóa, với nhãn tách mục đích và ngữ cảnh.

Ngược lại, nếu đầu vào là **mật khẩu con người**, nên dùng **password-based KDF** được thiết kế chống thử đoán offline như Argon2id hoặc scrypt; PBKDF2 có thể cần thiết ở một số môi trường tuân thủ/tương thích. Một vòng SHA-256(password) không phải quy trình Generate AES key mạnh.

### 7.2. Import khóa không tự tăng độ mạnh

KMS/HSM có thể **bảo vệ** một khóa được import nhưng không biến key material vốn dễ đoán thành ngẫu nhiên mạnh. Cần đánh giá nguồn sinh khóa, quyền export, lịch sử sử dụng, môi trường và trách nhiệm khi quyết định import.

**Trường hợp điển hình:** doanh nghiệp chuyển một KEK đang dùng từ hệ thống cũ sang HSM mới. Phải xác định KEK cũ từng được lưu ở đâu, ai có bản sao, có bị lộ/thu hồi không, và liệu nên **generate KEK mới** rồi rewrap DEK thay vì tiếp tục nhập vật liệu đã từng xuất hiện ở nhiều host.

## 8. Chọn nơi tạo khóa: ứng dụng, KMS hay HSM?

| Lựa chọn | Ưu điểm | Đánh đổi/giới hạn |
|---|---|---|
| **Java KeyGenerator/KeyPairGenerator** | Tích hợp nhanh với JCA, phù hợp một số DEK hoặc khóa phiên | Key material có thể tồn tại trong RAM ứng dụng; phụ thuộc provider/OS RNG |
| **Managed KMS** | IAM, audit, trạng thái khóa, chính sách dùng và API quản lý tập trung | Khả năng thuật toán, export, version, API và quota khác nhau theo dịch vụ |
| **HSM** | Có thể bảo vệ private key/KEK trong ranh giới phần cứng và thực hiện phép toán bên trong | Cần quản trị thiết bị/provider, vai trò, HA, backup và chi phí vận hành |
| **Keystore được bảo vệ** | Có thể phù hợp ứng dụng desktop/on-premises | Phụ thuộc quyền OS, password/PIN, backup và bảo vệ host |
| **Secret store** | Hỗ trợ cấp phát một số khóa/secret dạng rõ tới workload | Không đồng nghĩa key operations được bảo vệ trong HSM |

**Non-exportable** là thuộc tính quan trọng với private signing key hoặc KEK nếu hạ tầng hỗ trợ. Tuy nhiên, một khóa **không xuất được** vẫn có thể bị **lạm dụng thao tác Sign/Decrypt/Unwrap** nếu principal được cấp quyền quá rộng.

### 8.1. Câu hỏi quyết định vị trí sinh khóa

1. **Có được phép có plaintext key trong RAM ứng dụng không?** Nếu không, ưu tiên thao tác trong KMS/HSM và API tương thích.
2. **Ai sở hữu khóa?** Tenant, tổ chức, dịch vụ hay người dùng cuối?
3. **Có yêu cầu chứng nhận/tuân thủ?** Xem thuật toán, provider, chế độ hoạt động và ranh giới bảo mật được phê duyệt.
4. **Khóa có cần sao lưu/phục hồi?** Cách làm của KEK, signing key và ephemeral key rất khác nhau.
5. **Nếu KMS không sẵn sàng thì làm gì?** Thiết kế fail-safe hoặc đường dự phòng được phê duyệt, không tự dùng nguồn random yếu.
6. **Có yêu cầu chống lạm dụng?** IAM, tách quyền, phê duyệt thao tác nhạy cảm, quota và audit.

## 9. Luồng sinh DEK bằng KMS trong envelope encryption

Một kiến trúc thường gặp khi lưu dữ liệu nhạy cảm:

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng đã xác thực
    participant K as KMS / HSM
    participant S as Kho dữ liệu

    A->>K: Yêu cầu GenerateDataKey (KEK reference, context)
    K-->>A: Plaintext DEK (nếu API cho phép) + encrypted DEK
    Note over A: AES-GCM encrypt với DEK và nonce hợp lệ
    A->>S: Ciphertext + tag + nonce + encrypted DEK + metadata
    Note over A: Giảm thời gian tồn tại plaintext DEK trong RAM
    A->>K: Audit qua dịch vụ khi gọi API
~~~

**Lưu ý:** Đây là ví dụ về một dạng API KMS có thể trả **plain DEK** cho ứng dụng; **không phải mọi KMS đều có cùng tên API, payload hoặc khả năng trả key plaintext**. Nếu ứng dụng không được phép nhận DEK rõ, cần chọn thiết kế thực hiện phép toán trong miền tin cậy hoặc sử dụng API dữ liệu phù hợp.

### 9.1. Những gì cần lưu với bản mã

- **Encrypted DEK**, không phải plaintext DEK.
- **Key reference** tới KEK và phiên bản/cách tra khóa theo API.
- **Thuật toán mã hóa dữ liệu** và các tham số cần thiết.
- **Nonce/IV, ciphertext và authentication tag** của phép AES-GCM.
- **Context/AAD** được ràng buộc đúng với tenant, đối tượng hoặc chính sách; metadata bản ghi phải được bảo vệ chống tráo đổi theo thiết kế.
- Thông tin phiên bản định dạng để hỗ trợ migration/rotation.

### 9.2. Khi rotate KEK và khi rotate DEK

**Rotation KEK** có thể cho phép **rewrap encrypted DEK** mà không mã hóa lại toàn bộ dữ liệu, nếu DEK chưa bị lộ và giải pháp/thuật toán hỗ trợ.

**Rotation DEK** thường phải dẫn đến **tạo DEK mới và mã hóa lại dữ liệu** liên quan; chỉ rewrap DEK cũ không thay thế vật liệu khóa mã hóa dữ liệu.

**Nếu DEK đã bị lộ**, rewrap không thể khiến bản sao DEK trong tay đối thủ trở lại bí mật. Cần đánh giá dữ liệu đã bị thu thập và phương án re-encrypt/ứng phó sự cố.

## 10. Java JCA: sinh AES-256 DEK bằng SecureRandom

Ví dụ Java 17+ sử dụng **KeyGenerator** để sinh một AES-256 key trong JVM, sau đó mã hóa và giải mã một bản ghi bằng AES-GCM với nonce 12 byte mới.

Đây là **ví dụ thao tác mật mã để học**, chưa có lưu trữ lâu dài, KMS wrap DEK, xác thực tenant, điều phối nonce cho nhiều instance hay xử lý rotation.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class GenerateAesKeyExample {
    private static final SecureRandom RANDOM = new SecureRandom();

    public record EncryptedRecord(
            byte[] nonce, byte[] ciphertextWithTag) {}

    public static SecretKey generateDek() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RANDOM);
        return generator.generateKey();
    }

    public static EncryptedRecord encrypt(
            SecretKey dek, byte[] plaintext, byte[] aad)
            throws Exception {
        byte[] nonce = new byte[12]; // 96-bit AES-GCM nonce
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            dek,
            new GCMParameterSpec(128, nonce)
        );
        cipher.updateAAD(aad);
        byte[] ciphertextWithTag = cipher.doFinal(plaintext);
        return new EncryptedRecord(nonce, ciphertextWithTag);
    }

    public static byte[] decrypt(
            SecretKey dek, EncryptedRecord record, byte[] aad)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE,
            dek,
            new GCMParameterSpec(128, record.nonce())
        );
        cipher.updateAAD(aad);
        return cipher.doFinal(record.ciphertextWithTag());
    }

    public static void main(String[] args) throws Exception {
        // Sinh DEK mới, không hard-code key material.
        SecretKey dek = generateDek();

        byte[] aad = "tenant=42;record=901"
            .getBytes(StandardCharsets.UTF_8);
        byte[] original = "Ho so nhay cam"
            .getBytes(StandardCharsets.UTF_8);

        EncryptedRecord record = encrypt(dek, original, aad);
        byte[] restored = decrypt(dek, record, aad);

        try {
            if (!Arrays.equals(original, restored)) {
                throw new IllegalStateException("Round-trip mismatch");
            }
            System.out.println("AES-256-GCM round-trip OK");
        } finally {
            Arrays.fill(restored, (byte) 0);
            Arrays.fill(original, (byte) 0);
        }

        // Ví dụ KHÔNG lưu key; production cần KMS/KEK,
        // key ID/version, nonce policy và vòng đời rõ ràng.
    }
}
~~~

### 10.1. Bài học quan trọng từ đoạn mã

- **KeyGenerator("AES")** biết cách tạo AES key theo provider, thay vì lấy những byte từ mật khẩu và tự coi đó là khóa mạnh.
- **SecureRandom** phải được hỗ trợ bởi provider/OS RNG phù hợp; không tự seed bằng timestamp hay thay bằng java.util.Random.
- **AES-GCM nonce** cần **không trùng với cùng DEK** trong toàn bộ đời encrypt của DEK. Mẫu ngẫu nhiên này chỉ minh họa một lần mã hóa, **không chứng minh tính duy nhất tuyệt đối cho hệ thống quy mô lớn**.
- **AAD** được xác thực, không mã hóa; bên giải mã phải dùng đúng bytes AAD. Ràng buộc tenant/record bằng AAD có thể ngăn một số kiểu tráo đổi bản mã nếu ứng dụng xử lý metadata và quyền đúng.
- **SecretKey** ở ví dụ được giữ trong JVM; không có cam kết key nằm trong HSM hay có thể xóa hoàn toàn khỏi bộ nhớ. **Arrays.fill** chỉ xóa những mảng byte do chương trình trực tiếp kiểm soát.
- Không log key, ciphertext plaintext, access token hoặc cấu hình có secret. Nonce thường công khai nhưng phải quản lý theo đúng phạm vi khóa.

### 10.2. Tại sao không xuất key để lưu trong application.yml?

Trong nhiều provider, gọi \`SecretKey.getEncoded()\` có thể trả vật liệu khóa dạng rõ; việc đưa byte đó vào file cấu hình, Git repository, image hoặc log làm tăng đáng kể phạm vi phơi lộ.

Nếu muốn lưu lâu dài, nên dùng **KMS/HSM hoặc kho khóa được thiết kế cho việc bảo vệ secret**, có quyền truy cập, key ID/version, backup và kế hoạch rotation. Nếu ứng dụng lưu **encrypted DEK**, vẫn phải bảo vệ KEK và quyền **unwrap**.

## 11. Java JCA: sinh cặp khóa ECDSA P-256 để ký số

Ví dụ minh họa sinh cặp khóa bất đối xứng và xác minh chữ ký. Khóa chỉ tồn tại trong bộ nhớ để diễn giải thao tác; trong sản xuất, private signing key thường cần được bảo vệ bằng KMS/HSM hoặc provider có ranh giới phù hợp.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;

public final class GenerateSigningKeyExample {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(
            new ECGenParameterSpec("secp256r1"),
            new SecureRandom()
        );
        KeyPair pair = generator.generateKeyPair();

        byte[] message = "document=42;version=1"
            .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(pair.getPrivate(), new SecureRandom());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);

        if (!verifier.verify(signature)) {
            throw new IllegalStateException("ECDSA verification failed");
        }
        System.out.println("ECDSA sign/verify OK");
    }
}
~~~

**Giải thích:**

- Cặp khóa được tạo bằng **KeyPairGenerator("EC")** với tham số curve **secp256r1**.
- **Private key** dùng để ký; **public key** dùng để xác minh. Verifier không cần và không nên nhận private key.
- Tên **SHA256withECDSA** thường bao gồm bước hash bằng SHA-256 bên trong API. Không tự hash trước khi gọi nếu API đang mong nhận message.
- **Chữ ký hợp lệ không tự chứng minh danh tính chủ thể**: phải xác thực public key qua chứng chỉ/trust store và kiểm tra mục đích, thời hạn, quyền, chống replay.
- Trong ECDSA, nonce bí mật **k theo từng lần ký** phải được provider sinh/dẫn xuất đúng; nếu k lộ hoặc bị dùng lại sai cách, private key có thể bị suy ra.
- Kết quả chữ ký Java có thể ở định dạng **DER**, trong khi một số giao thức như **JWS ES256** yêu cầu **raw r ∥ s**; cần đáp ứng encoding của giao thức.

### 11.1. Có nên lưu private key để khôi phục?

Tùy mục đích. Với **private signing key**, có thể sử dụng key mới và giữ **public key/chứng chỉ cùng bằng chứng thời gian** để xác minh tài liệu lịch sử, thay vì sao lưu private key dưới dạng rõ. Tuy nhiên, một số hệ thống có yêu cầu khôi phục đặc thù.

Với **DEK**, làm mất khóa có thể làm mất vĩnh viễn khả năng giải mã dữ liệu. Vì thế backup, key wrapping và kế hoạch restore phải được thiết kế trước; không sao chép tùy tiện plaintext key để giải quyết tính sẵn sàng.

## 12. Metadata, định danh và cryptoperiod sau khi sinh khóa

Một key material mới cần được đưa vào **hệ thống quản lý có thể vận hành được**:

| Metadata | Vì sao cần? |
|---|---|
| **Key ID** | Tham chiếu khóa ổn định mà không phải tiết lộ key material |
| **Key version / material identifier** | Phân biệt vật liệu khóa khi rotate, tránh alias trỏ nhầm |
| **Algorithm và parameters** | Phục vụ API đúng thuật toán và dữ liệu lịch sử |
| **Key usage** | Giới hạn các phép toán và mục đích |
| **Owner / tenant / environment** | Kiểm soát ranh giới tổ chức, môi trường và phạm vi dữ liệu |
| **Origin / provider** | Biết khóa sinh trong KMS/HSM hay import từ nơi khác |
| **Export policy** | Xác định vật liệu được phép rời miền bảo vệ hay không |
| **Creation timestamp** | Theo dõi vòng đời và kiểm toán |
| **Activation / cryptoperiod** | Xác định khi nào được ký/mã hóa dữ liệu mới |
| **Rotation / revocation state** | Xác định phiên bản hiện hành và trạng thái khóa cũ |
| **Audit correlation ID** | Liên kết yêu cầu tạo khóa với phê duyệt hoặc workflow |

Một metadata model khái niệm:

~~~yaml
# Minh họa logic quản lý, không phải API bắt buộc của một KMS
keyId: signing-order-service
version: v1
algorithm: ECDSA-P256-SHA256
usage: [sign]
owner: order-service
environment: production
origin: managed-hsm
exportable: false
state: ACTIVE
cryptoperiodPolicy: "approved-policy-reference"
~~~

**Không xem alias hoặc tên file là vật liệu khóa.** Đổi alias chưa chắc tạo khóa mới. Ngược lại, khi có version mới, bản mã/chữ ký và hệ thống xác minh phải có metadata đủ để dùng đúng vật liệu lịch sử.

## 13. IAM: ai được GenerateKey và sử dụng khóa mới?

Một nguyên tắc quan trọng là **người được tạo khóa không nhất thiết được giải mã hoặc thay chính sách tùy ý**.

| Vai trò mẫu | Quyền có thể cần | Quyền không tự động được cấp |
|---|---|---|
| **Security administrator** | Định nghĩa key policy, quy trình phê duyệt và kiểm toán | Không nhất thiết được đọc plaintext DEK |
| **Key lifecycle operator** | Tạo version, rotate/disable theo phê duyệt | Không tự có quyền decrypt mọi dữ liệu |
| **Application encryptor** | Encrypt/GenerateDataKey trong phạm vi cho phép | Không được ScheduleDelete hoặc ChangePolicy |
| **Application decryptor** | Decrypt/Unwrap theo tenant và nghiệp vụ | Không được tạo signing key cho tổ chức |
| **Signing workload** | Sign trên key/mục đích cụ thể | Không được export private key hoặc ký mọi nội dung |
| **Verifier** | GetPublicKey/Verify theo nguồn tin cậy | Không cần private signing key |
| **Auditor** | Đọc metadata/event cần thiết | Không được quyền thao tác khóa nếu không có lý do |

### 13.1. Kiểm soát ở cả KMS và nghiệp vụ

KMS có thể biết workload A được phép gọi **Sign**, nhưng không tự biết nội dung đơn hàng được **người có thẩm quyền phê duyệt** hay chưa. Ứng dụng phải kiểm tra **người dùng, vai trò, tenant, phạm vi dữ liệu, purpose và trạng thái nghiệp vụ** trước khi gọi API.

Một khóa **non-exportable** vẫn có thể bị lạm dụng bởi principal có quyền Sign/Decrypt quá rộng. Bởi vậy GenerateKey an toàn cần đi kèm **key policy chính xác, separation of duties, quota, giám sát và quyền thay chính sách được bảo vệ**.

## 14. Audit thao tác sinh khóa

Nhật ký kiểm toán cần giúp tổ chức trả lời: **Ai tạo khóa? Tại sao? Bằng thuật toán nào? Trong môi trường nào? Khóa đã đi đâu?**

Những trường thường hữu ích:

- **Timestamp** và môi trường.
- **Workload principal/user/role** thực hiện hoặc phê duyệt.
- **Operation** (GenerateKey, GenerateDataKey, ImportKey...), kết quả và mã lỗi.
- **Key ID/version, algorithm, usage, origin và policy reference**.
- **Request/correlation ID** để liên kết với hệ thống quản lý thay đổi.
- Sự kiện **Rotate, Disable, Revoke, Delete, ChangePolicy**, nếu có.
- Tần suất tạo khóa bất thường theo principal, tenant, vùng hoặc thời điểm.

**Không log private key, plaintext DEK, seed/CSPRNG state, token, pepper hoặc toàn bộ dữ liệu bí mật**. Nếu audit cần ghi fingerprint của **public key**, phải biết fingerprint không tự xác thực danh tính chủ sở hữu.

Tạo quá nhiều khóa cũng có thể là dấu hiệu **lạm dụng API, sai vòng đời, vượt quota hoặc tấn công tài nguyên**, chứ không chỉ một chỉ số hoạt động bình thường.

## 15. Generate key gắn với toàn bộ vòng đời ra sao?

~~~mermaid
flowchart LR
    A["Generate: vật liệu mới"] --> B["Provision: key ID, policy, public key"]
    B --> C["Store: KMS/HSM/keystore"]
    C --> D["Use: encrypt/decrypt/sign/wrap"]
    D --> E["Rotate: sinh phiên bản mới"]
    E --> F["Migrate dữ liệu và verifier"]
    F --> G["Disable / Revoke"]
    G --> H["Retain có kiểm soát / Destroy"]
~~~

| Giai đoạn | Quyết định gắn với khóa mới |
|---|---|
| **Generation** | Nguồn entropy, thuật toán, key usage, origin và kích thước |
| **Provisioning** | Ai nhận quyền; public key/chứng chỉ phân phối theo kênh nào |
| **Storage** | Có export được không; backup, HSM, KEK bảo vệ key material |
| **Usage** | Cryptoperiod, AAD/nonce, role, logging, rate limit |
| **Rotation** | Tạo **vật liệu mới**, cập nhật alias và dữ liệu/verifier liên quan |
| **Revocation** | Chặn sử dụng và rút niềm tin đối với key đã bị lộ |
| **Destruction** | Hủy khi không còn phụ thuộc hợp lệ; tính đến dữ liệu cũ và backup |

### 15.1. Tạo khóa mới không hoàn thành rotation nếu chưa chuyển phụ thuộc

Ví dụ, sinh KEK v4 nhưng DEK cũ vẫn được wrap dưới KEK v3. KMS có thể báo **v4 ACTIVE**, nhưng việc hủy v3 quá sớm khiến dữ liệu không thể giải mã. Cần **theo dõi phụ thuộc, rewrap và kiểm chứng restore**.

Với signing key, sinh private key v4 chưa đủ nếu verifier chưa biết public key/chứng chỉ mới. Phải phát hành khóa công khai tin cậy và xử lý cache/JWKS/trust store.

### 15.2. Sinh khóa mới sau khi phát hiện rò rỉ

Nếu một DEK hoặc private signing key bị lộ, việc GenerateKey giúp **giới hạn nguy cơ tương lai**, nhưng:

- Dữ liệu cũ đã bị giải mã không tự lấy lại bí mật.
- Bản sao plaintext DEK/private key trong tay đối thủ không biến mất.
- Verifier vẫn có thể tin public key cũ đến khi áp dụng revocation.
- Một bản mã cũ dưới DEK bị lộ vẫn có thể bị giải mã nếu đối thủ đã thu thập.

Cần phối hợp **re-encrypt dữ liệu, rewrap khi phù hợp, cập nhật trust, thu hồi phiên/token và điều tra audit** theo bản chất sự cố.

## 16. Lỗi thường gặp khi GenerateKey

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Sinh khóa AES từ SHA256(password) một lần | Entropy bị giới hạn bởi password | Dùng CSPRNG hoặc password KDF nếu bắt buộc dựa passphrase |
| Dùng java.util.Random hoặc timestamp seed | Có thể dự đoán key material | SecureRandom/KeyGenerator hoặc KMS |
| Dùng cùng key cho production và test | Lộ từ môi trường thấp làm ảnh hưởng production | Tách môi trường và quyền |
| Tái dùng một DEK toàn tổ chức | Phạm vi ảnh hưởng lớn khi lộ | Phân tách theo tenant/dataset/object tùy threat model |
| Nhầm mục đích ký và mã hóa | Sai key usage hoặc triển khai mật mã không phù hợp | Chọn đúng loại khóa và policy trước khi sinh |
| Khóa được sinh mạnh nhưng xuất/log ra ngoài | Mất bí mật ngay tại thời điểm tạo | Non-exportable khi cần, không log material |
| Sinh KEK bằng ứng dụng rồi hard-code | Vật liệu khóa dễ bị sao chép | Sinh và lưu trong KMS/HSM |
| Dùng cùng nonce AES-GCM cho hai lần encrypt | Phá bảo mật AEAD dù key mạnh | Thiết kế nonce uniqueness cho từng DEK |
| Không có key ID/version | Khó giải mã dữ liệu sau rotation | Ghi metadata và version ngay khi cấp phát |
| Không kiểm tra CSPRNG sau VM clone/restore | Có thể lặp seed/state trong hệ thống lỗi | Dùng OS/provider hỗ trợ và đánh giá môi trường |
| Import một khóa yếu rồi cho rằng HSM làm nó mạnh | Key vẫn có thể bị đoán | Kiểm tra origin hoặc sinh vật liệu mới |
| Quyền GenerateKey và Delete/ChangePolicy quá rộng | Lạm dụng tạo/hủy khóa hoặc vượt quyền | IAM least privilege, phân tách nhiệm vụ |
| Chỉ tạo key mới mà không chuyển encrypted DEK/verifier | Không hoàn thành rotation | Kế hoạch migration, rewrap/re-encrypt và trust updates |
| Hủy key quá sớm | Mất khả năng giải mã hoặc kiểm tra dữ liệu lịch sử | Kiểm kê phụ thuộc, backup và retention |
| Không audit GenerateKey | Khó điều tra khóa bất thường | Ghi metadata, caller, kết quả và phê duyệt, không ghi secret |

## 17. Tình huống thực tế: nền tảng lưu tài liệu nhiều tenant

Một nền tảng Java lưu chứng từ của nhiều tenant. Ban đầu, nhóm phát triển dùng **một AES-256 key** trong biến môi trường cho mọi hồ sơ và mọi môi trường.

**Những vấn đề:**

1. Key có thể bị sao chép vào cấu hình, CI log hoặc công cụ chẩn đoán.
2. Nếu một workload bị chiếm quyền, đối thủ có thể giải mã **nhiều tenant**.
3. Không có key version cho từng bản ghi; rotation đòi hỏi thay cùng lúc toàn bộ hệ thống.
4. Một số instance dùng nonce counter bắt đầu từ 0 với cùng DEK, gây nguy cơ trùng nonce AES-GCM.

### Thiết kế lại

~~~mermaid
flowchart TD
    R["Yêu cầu tạo tài liệu đã xác thực"] --> IAM["Kiểm tra IAM + tenant + nghiệp vụ"]
    IAM --> KMS["KMS/HSM: GenerateDataKey dưới KEK của tenant"]
    KMS --> DEK["DEK ngẫu nhiên cho phạm vi dữ liệu"]
    DEK --> ENC["AES-GCM encrypt với nonce duy nhất"]
    D["Plaintext tài liệu"] --> ENC
    ENC --> C["Ciphertext + tag + nonce"]
    KMS --> W["Encrypted DEK + KEK reference"]
    C --> DB["Kho dữ liệu"]
    W --> DB
    IAM --> AUDIT["Audit tạo/sử dụng khóa"]
    KMS --> AUDIT
~~~

**Quy trình đề xuất:**

1. Đăng ký **KEK theo tenant hoặc miền tin cậy phù hợp** trong KMS/HSM, với quyền wrap/unwrap được phân tách.
2. Khi tạo tài liệu, xác thực caller và kiểm tra tenant; yêu cầu **DEK mới hoặc DEK có phạm vi được kiểm soát** bằng API KMS/KeyGenerator đáng tin.
3. Mã hóa dữ liệu bằng AES-GCM, cấp nonce **không trùng dưới DEK**, kể cả retry/restart/multiwriter.
4. Lưu ciphertext, tag, nonce, encrypted DEK, key ID/version và metadata liên quan; không lưu DEK rõ cùng bản mã.
5. Hạn chế DEK plaintext trong RAM và kiểm toán lời gọi KMS; không ghi vào log.
6. Định nghĩa rotation **KEK** (rewrap DEK) khác rotation **DEK** (thường phải re-encrypt), cùng quá trình kiểm tra dữ liệu và backup.
7. Khi phát hiện lỗi nguồn random hoặc lộ key material, lập danh sách khóa/bản mã chịu ảnh hưởng và thực hiện thu hồi/thay khóa/điều tra thích hợp.

**Giá trị nhận được:** mỗi lớp khóa có mục đích rõ ràng, quyền truy cập tách biệt, phạm vi ảnh hưởng nhỏ hơn, có lịch sử phiên bản và có khả năng xử lý sự cố mà không tùy tiện xóa dữ liệu hợp lệ.

## 18. Kiểm thử GenerateKey ở mức hệ thống

| Tình huống kiểm thử | Kết quả kỳ vọng |
|---|---|
| Sinh AES-256 DEK bằng provider được phép | Đúng thuật toán/độ dài, key usable theo chính sách |
| Sinh ECDSA P-256 key pair | Private/public key hợp lệ; ký và verify thành công |
| Dùng khóa không phù hợp với thuật toán yêu cầu | API từ chối |
| Principal không có quyền GenerateKey | Bị từ chối và có audit |
| Principal chỉ Verify cố gọi Sign | Bị từ chối |
| KMS/HSM hoặc RNG không sẵn sàng | Không fallback sang PRNG yếu |
| Sinh DEK trong môi trường test | Không có quyền dùng KEK production |
| Tạo key mới sau rotation | Vật liệu mới và metadata version chính xác |
| Dữ liệu cũ sau rotation KEK | Vẫn được decrypt sau rewrap theo thiết kế |
| Tạo DEK rồi mã hóa AES-GCM | Nonce/tag đúng và dữ liệu decrypt xác thực |
| Cố encrypt với nonce đã dùng dưới cùng DEK | Bị ngăn hoặc thiết kế chứng minh không tái cấp phát |
| Tạo khóa sau VM snapshot/restore | Không lặp key/nonce do cơ chế seed/state bị lỗi |
| Lấy public key của signing key | Phân phối đúng nguồn tin cậy, private key không bị xuất trái phép |
| Private key non-exportable | Không có API export khi policy cấm |
| KMS audit GenerateKey | Có principal, key ID/version, thời điểm, kết quả nhưng không lộ material |
| Xóa key khi còn encrypted DEK phụ thuộc | Quy trình chặn hoặc yêu cầu phê duyệt/di trú theo chính sách |
| Key bị revoke nhưng caller thử dùng lại | Không còn được phép tạo hoạt động mới ngoài chính sách |

**Chú ý:** Việc sinh 1.000 khóa đều khác nhau **không chứng minh RNG có entropy đủ**. Kiểm thử ứng dụng cần kết hợp đánh giá provider, nguồn entropy, chính sách key generation và các kịch bản lỗi; không thay thế kiểm chứng mật mã chuyên sâu.

## 19. Câu hỏi tự kiểm tra

**Câu 1. Generate key khác derive key ở đâu?**

**Trả lời:** Generate tạo vật liệu khóa mới từ nguồn ngẫu nhiên/mật mã theo thuật toán; derive tính keying material từ một bí mật đầu vào bằng KDF theo ngữ cảnh. Không tự đồng nhất entropy hai cách.

**Câu 2. SHA-256 của một mật khẩu có tạo AES-256 key mạnh không?**

**Trả lời:** Không. Output dài 256 bit nhưng entropy bị giới hạn bởi mật khẩu; cần password KDF nếu bắt buộc dựa trên password hoặc CSPRNG để sinh khóa độc lập.

**Câu 3. Tại sao cần chọn key usage trước khi sinh?**

**Trả lời:** Thuật toán, API, quyền, thời hạn và rủi ro của Encrypt/Decrypt, Sign/Verify, Wrap/Unwrap khác nhau; tách purpose giúp giảm lạm dụng.

**Câu 4. Private signing key và public verification key được sử dụng thế nào?**

**Trả lời:** Private key ký, public key xác minh. Public key có thể công khai nhưng phải được xác thực danh tính; private key phải bí mật và quyền Sign phải được giới hạn.

**Câu 5. HSM có tự nâng entropy của một DEK yếu được import không?**

**Trả lời:** Không. HSM có thể giữ key material an toàn hơn, không thay đổi thực tế rằng khóa nhập vào vốn dễ đoán.

**Câu 6. Tại sao nên sinh DEK độc lập thay vì dùng cùng một KEK mã hóa trực tiếp mọi file?**

**Trả lời:** Tách DEK/KEK hỗ trợ phân phạm vi dữ liệu, rotation/rewrap và giảm tác động khi lộ một DEK, nếu kiến trúc quyền được thiết kế đúng.

**Câu 7. Nếu tạo AES key rất mạnh thì có thể dùng nonce cố định AES-GCM không?**

**Trả lời:** Không. Với mỗi DEK, nonce phải không trùng giữa các lần encrypt; key mạnh không cứu được lỗi nonce reuse.

**Câu 8. Đổi tên alias có nghĩa đã Generate key mới không?**

**Trả lời:** Không. Alias chỉ là định danh/tham chiếu; phải chắc chắn vật liệu khóa mới thực sự được tạo.

**Câu 9. Nếu KMS trả plaintext DEK, ứng dụng cần làm gì?**

**Trả lời:** Giới hạn thời gian tồn tại trong RAM, chỉ sử dụng theo quyền và mục đích, không log, lưu encrypted DEK/metadata và quản lý nonce.

**Câu 10. Generate key trong HSM có nghĩa mọi thao tác ký đều đúng nghiệp vụ không?**

**Trả lời:** Không. Caller được cấp quyền Sign quá rộng vẫn có thể yêu cầu HSM ký nội dung trái phép; cần kiểm tra quyền nghiệp vụ, IAM và audit.

**Câu 11. Tại sao metadata key ID/version quan trọng?**

**Trả lời:** Nó cho biết phải dùng vật liệu nào để giải mã/xác minh dữ liệu cũ sau rotation và hỗ trợ quản lý phụ thuộc, thu hồi, kiểm toán.

**Câu 12. Sinh signing key v2 có đủ để client tin chữ ký mới không?**

**Trả lời:** Không. Phải phân phối public key/chứng chỉ v2 qua nguồn đáng tin và cập nhật verifier/trust store/JWKS.

**Câu 13. Có thể hủy ngay KEK cũ sau khi tạo KEK mới không?**

**Trả lời:** Không nếu encrypted DEK hoặc backup còn phụ thuộc. Cần rewrap/migrate và kiểm chứng trước khi hủy theo chính sách.

**Câu 14. Java Random và SecureRandom khác nhau về vai trò?**

**Trả lời:** Random dành cho nhiều nhu cầu ngẫu nhiên thống kê; SecureRandom cung cấp giao diện CSPRNG phù hợp sinh secret theo provider và cấu hình được đánh giá.

**Câu 15. Reseed RNG sau sự cố có làm key yếu cũ mạnh lên không?**

**Trả lời:** Không. Cần khoanh vùng và thay những khóa bị ảnh hưởng, cùng xử lý dữ liệu/chữ ký/token đã tạo bằng chúng.

## 20. Checklist trước khi đưa khóa mới vào ACTIVE

Trước khi cho một khóa mới tạo tham gia sản xuất, hãy xác nhận:

- **Purpose:** khóa phục vụ Encrypt, Decrypt, Sign, Verify, Wrap, Unwrap hay KeyAgreement?
- **Algorithm:** AES, HMAC, ECDSA, Ed25519, RSA hay X25519? Tham số và kích thước được phép?
- **Randomness:** nguồn entropy và CSPRNG/DRBG/HSM đã được phê duyệt? Không dùng Random/timestamp/seed yếu?
- **Origin:** key được Generate trong KMS/HSM hay import? Có bằng chứng về nguồn và mức phơi lộ?
- **Key material:** private/symmetric key có được giữ bí mật; policy export và backup đúng không?
- **Identity:** key ID/version, owner, tenant, environment, purpose và metadata thuật toán đã sẵn sàng?
- **IAM:** chỉ principal hợp lệ có quyền sử dụng; quyền tạo, ký, giải mã, rotate và delete có được tách?
- **Cryptoperiod:** thời điểm kích hoạt, thời gian mã hóa/ký mới, retention và rotation đã được xác định?
- **Encryption:** nếu dùng AES-GCM, nonce uniqueness, AAD, tag, key version đã được thiết kế cho toàn hệ thống?
- **Envelope encryption:** DEK có được wrap dưới KEK và encrypted DEK được lưu đúng, không xuất plaintext quá mức?
- **Signing:** public key/chứng chỉ được phân phối có xác thực, verifier và cache biết đúng key version?
- **Testing:** phép thử encrypt/decrypt hoặc sign/verify đạt; các failure path từ chối an toàn?
- **Audit:** có lịch sử GenerateKey, caller, key ID/version và kết quả, không chứa key material?
- **Incident response:** nếu phát hiện key yếu/lộ, có thể rotate/revoke, rewrap/re-encrypt, cập nhật trust và điều tra không?

**Ghi nhớ:** **Generate key không đơn giản là lấy một chuỗi byte ngẫu nhiên.** Một khóa tốt phải được tạo bằng **thuật toán và nguồn entropy phù hợp**, trong **miền tin cậy được kiểm soát**, có **mục đích, phiên bản, chủ sở hữu, IAM và kiểm toán rõ ràng**. Chỉ khi gắn bước sinh khóa với **KMS/HSM, DEK/KEK, envelope encryption, chữ ký số và toàn bộ vòng đời tạo–sử dụng–xoay vòng–thu hồi–hủy**, hệ thống mới có nền tảng quản lý khóa an toàn và vận hành được.
