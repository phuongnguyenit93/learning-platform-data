# Không dùng password làm encryption key trực tiếp

## 1. Vấn đề: mật khẩu không phải khóa AES

Giả sử một ứng dụng Java cho phép người dùng đặt mật khẩu **"MyInvoice2026!"** và dùng chính chuỗi đó làm khóa mã hóa hồ sơ. Lập trình viên có thể thử chuyển chuỗi thành UTF-8, đệm thêm byte để đủ 32 byte rồi gọi AES-256:

~~~java
// SAI: Chỉ minh họa anti-pattern, không sử dụng.
byte[] keyBytes = Arrays.copyOf(
    password.getBytes(StandardCharsets.UTF_8), 32);
SecretKeySpec key = new SecretKeySpec(keyBytes, "AES");
~~~

Mã có thể chạy nếu tạo được đúng số byte mà API yêu cầu. Nhưng **khóa dài 256 bit trên giấy không đồng nghĩa có 256 bit entropy**. Mật khẩu do con người chọn thường bị giới hạn bởi từ vựng, thói quen, quy tắc đặt mật khẩu và những thông tin có thể đoán. Một kẻ lấy được ciphertext có thể thử các mật khẩu ứng viên để tìm khóa đúng.

Các biến thể tưởng là tốt hơn nhưng vẫn sai về bản chất gồm:

~~~text
AESKey = password.getBytes(UTF_8)
AESKey = padWithZeros(password, 32)
AESKey = truncate(password, 32)
AESKey = SHA256(password)
AESKey = SHA256(password + "constant-salt")
AESKey = MD5(password) || MD5(password)
~~~

Các phép này **không biến một mật khẩu dễ đoán thành khóa ngẫu nhiên mạnh**. Một hàm băm nhanh như SHA-256 thậm chí cho phép kẻ tấn công thử nhiều ứng viên rất nhanh trong tấn công ngoại tuyến. Đệm hoặc cắt byte còn dễ tạo ra các khóa có cấu trúc dễ đoán, không đồng nhất và không có kế hoạch rotation.

**Nguyên tắc của bài học:** **không sử dụng password trực tiếp làm encryption key**. Nếu trường hợp sử dụng bắt buộc dựa vào mật khẩu (ví dụ người dùng tự mã hóa tệp), hãy dùng **password-based KDF** được thiết kế cho mật khẩu, **salt** riêng và một cơ chế **mã hóa có xác thực (AEAD)**. Với dữ liệu doanh nghiệp có KMS/HSM, thường nên **sinh DEK ngẫu nhiên** để mã hóa dữ liệu rồi **bọc DEK bằng KEK** được quản lý thích hợp.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **password**, **entropy**, **raw encryption key**, **password-derived key**, **DEK** và **KEK**.
2. Hiểu vì sao **SHA-256(password)**, thêm muối cố định hoặc đệm mật khẩu đều không phải phương án dẫn xuất khóa an toàn cho người dùng.
3. Chọn **Argon2id, scrypt hoặc PBKDF2-HMAC-SHA256** cho trường hợp mật khẩu cần tham gia tạo khóa.
4. Thiết kế mô hình **password → KDF → KEK → wrapped DEK → AEAD ciphertext**, cùng các trường salt/nonce/tag và metadata.
5. Phân biệt **mã hóa dữ liệu bằng passphrase** với **xác minh mật khẩu đăng nhập**.
6. Thực hiện ví dụ Java 17 dùng PBKDF2 và AES-GCM, biết giới hạn của ví dụ.
7. Quản lý việc đổi mật khẩu, rotation/re-encrypt, khôi phục, thu hồi quyền và audit trong hệ thống key management.

## 2. Password khác key ở những thuộc tính nào?

### 2.1. Entropy chứ không phải độ dài chuỗi quyết định mức khó đoán

**Entropy** trong ngữ cảnh khóa mật mã phản ánh độ bất định của nguồn sinh ra bí mật đối với kẻ tấn công. Một khóa AES-256 được sinh đúng bằng **cryptographically secure random number generator (CSPRNG)** nhằm có độ bất định tương ứng với không gian khóa 256 bit. Một password do người dùng nhớ và gõ lại thường có phân phối khác xa ngẫu nhiên đều.

| Tiêu chí | Password/passphrase | Khóa đối xứng ngẫu nhiên |
| --- | --- | --- |
| Nguồn | Con người chọn hoặc bộ quản lý mật khẩu tạo | CSPRNG/KMS/HSM phù hợp |
| Mục đích điển hình | Chứng minh quyền truy cập, mở tệp do người dùng kiểm soát | Bảo vệ dữ liệu/MAC/key wrapping |
| Dễ bị thử đoán? | Có thể, nhất là mật khẩu tái sử dụng hoặc có quy luật | Không thực tế nếu đủ mạnh, sinh đúng và không lộ |
| Cách biểu diễn | Chuỗi ký tự Unicode/byte có encoding | Byte key theo thuật toán quy định |
| Vòng đời | Đặt/đổi/khôi phục theo người dùng, có thể quên | Quản lý key ID/version, cryptoperiod, rotation, thu hồi |
| Sự cố khi lộ | Có thể ảnh hưởng nhiều dịch vụ do tái sử dụng | Ảnh hưởng phạm vi dữ liệu và mục đích dùng khóa |

Một passphrase dài, được tạo ngẫu nhiên từ nguồn đáng tin, có thể mạnh hơn mật khẩu tự nghĩ ra. Nhưng **API mã hóa vẫn cần đầu vào khóa đúng loại và giao thức quản lý tham số**; đừng đưa trực tiếp chuỗi ký tự vào AES chỉ vì passphrase có vẻ phức tạp.

### 2.2. Hash không tự tạo thêm entropy

Giả sử một mật khẩu chỉ có khoảng \(2^{30}\) khả năng thực tế trong mô hình kẻ tấn công. SHA-256 xuất ra 256 bit, nhưng kẻ tấn công vẫn có thể băm các ứng viên mật khẩu để thử. Độ dài digest **không nâng không gian đoán bí mật lên \(2^{256}\)**.

~~~text
password dễ đoán ──SHA-256──> chuỗi 256 bit
   30 bit entropy              vẫn phụ thuộc đầu vào 30 bit

password dễ đoán ──password-based KDF──> chuỗi 256 bit
   30 bit entropy              không thêm entropy bí mật,
                               nhưng mỗi lần thử có chi phí lớn hơn
~~~

**Password-based KDF làm tấn công ngoại tuyến đắt hơn**, không làm mật khẩu yếu trở thành khóa ngẫu nhiên 256 bit. Vì vậy vẫn cần tăng chất lượng password/passphrase, giới hạn quyền, bảo vệ dữ liệu và cân nhắc cơ chế phục hồi khi cần.

### 2.3. Kẻ tấn công kiểm tra password ứng viên bằng cách nào?

Nếu một tệp sử dụng **AEAD** như AES-GCM, kết quả giải mã có **authentication tag**. Với mỗi password ứng viên, attacker có thể:

1. Đọc salt và tham số KDF vốn thường được lưu công khai.
2. Dẫn xuất một khóa ứng viên.
3. Thử mở bản mã bằng nonce, AAD và tag đã lưu.
4. Nếu xác thực tag thành công, password có khả năng đúng; nếu sai thì thử ứng viên khác.

Đây là **offline password guessing**: attacker có bản sao dữ liệu và không cần gửi mỗi lần thử đến server. Rate limit hoặc khóa tài khoản trên API **không trực tiếp giới hạn tốc độ thử ngoại tuyến**. KDF chậm/chịu chi phí bộ nhớ có ý nghĩa chính trong tình huống này.

## 3. Những anti-pattern phổ biến

### 3.1. Chuyển password thành byte rồi dùng ngay

~~~java
// SAI: password có độ dài khác nhau, key không đủ entropy,
// encoding và padding không phải KDF.
byte[] key = password.getBytes(StandardCharsets.UTF_8);
Cipher cipher = Cipher.getInstance("AES/ECB/PKCS5Padding");
~~~

Đoạn trên còn sử dụng **AES-ECB**, chế độ không nên dùng cho dữ liệu nghiệp vụ vì làm lộ cấu trúc và thiếu tính xác thực. Hai lỗi độc lập:

- **Key derivation sai:** password không phải encryption key đúng chuẩn.
- **Chế độ mã hóa sai:** ECB không cung cấp authenticated encryption.

Thay ECB bằng GCM **chưa khắc phục** nếu khóa vẫn được hình thành trực tiếp từ password.

### 3.2. SHA-256(password) làm AES-256 key

~~~java
// SAI cho password-based encryption.
byte[] derived = MessageDigest.getInstance("SHA-256")
    .digest(password.getBytes(StandardCharsets.UTF_8));
SecretKeySpec key = new SecretKeySpec(derived, "AES");
~~~

Đây là hash nhanh, không có **per-file/per-user salt đúng quy tắc** và không có cơ chế chi phí nhằm làm chậm thử đoán. Thêm một chuỗi **"my-app-salt"** cố định rồi SHA-256 một lần vẫn không tương đương **PBKDF2, scrypt hoặc Argon2id**.

### 3.3. Tự lặp hash thay vì dùng password-based KDF chuẩn

Một số thiết kế tự lặp SHA-256 vài nghìn lần hoặc thêm timestamp. Cách này khó kiểm chứng tính đúng đắn, thiếu quy ước tham số, dễ mắc lỗi domain separation, encoding, hạ cấp hoặc tính chi phí. **Không tự chế KDF** khi có lựa chọn đã được phân tích và hỗ trợ trong thư viện.

### 3.4. Dùng chung một password cho tất cả tenant

Nếu toàn bộ hệ thống dựa vào mật khẩu cấu hình chung để mã hóa mọi hóa đơn, việc lộ một password có thể ảnh hưởng tất cả tenant và mọi bản backup liên quan. Rotation cần giải mã/mã hóa lại nhiều dữ liệu, thường không thể tách quyền truy cập giữa service.

Ngay cả khi dùng PBKDF2 đúng cách, **một bí mật gốc chung** vẫn là một điểm tập trung rủi ro. Với hệ thống doanh nghiệp, nên cân nhắc **DEK ngẫu nhiên theo đối tượng/nhóm dữ liệu và KEK tách theo môi trường, dịch vụ hoặc tenant**.

### 3.5. Dùng password verifier làm encryption key

Một hệ thống có thể lưu **hash/verifier mật khẩu đăng nhập** để xác thực người dùng. Không được lấy giá trị verifier đó làm AES key cho dữ liệu nghiệp vụ. Nếu database chứa verifier bị lộ, attacker đã có sẵn vật liệu dùng như khóa mã hóa mà **không cần biết password gốc**.

**Password authentication** và **data encryption** là hai miền mục đích độc lập; phải phân tách khóa và quy trình quản lý.

## 4. Lựa chọn đúng: password-based key derivation function

**Password-based KDF** nhận password, salt và các tham số chi phí; nó đưa ra kết quả dùng trong một lược đồ có thiết kế phù hợp, giúp tăng chi phí thử password ứng viên. Phân biệt với **HKDF** dùng cho vật liệu bí mật mật mã mạnh.

| KDF | Đặc điểm chính | Dùng khi nào |
| --- | --- | --- |
| **Argon2id** | Memory-hard, điều chỉnh memory/time/parallelism; được thiết kế cho mật khẩu | Phương án phổ biến cho password hashing và password-based key derivation mới khi thư viện/chính sách cho phép |
| **scrypt** | Tốn CPU và bộ nhớ có thể cấu hình | Khi hệ sinh thái hỗ trợ tốt, cần một password-based KDF có chi phí bộ nhớ |
| **PBKDF2-HMAC-SHA256** | Dẫn xuất qua nhiều vòng HMAC; tương thích rộng, có trong Java JCA | Yêu cầu tương thích/tiêu chuẩn hoặc môi trường Java chưa có thư viện Argon2id |
| **HKDF-SHA256** | KDF nhanh dạng Extract/Expand, hỗ trợ context/domain separation | Với IKM mạnh như shared secret từ key agreement đã xác thực hoặc root key ngẫu nhiên; **không thay password-based KDF khi password yếu** |
| **SHA-256(password)** | Hash nhanh, không được thiết kế để chống thử password | **Không dùng** làm cơ chế tạo encryption key trực tiếp từ password |

### 4.1. Salt dùng để làm gì?

**Salt** thông thường là byte **không bí mật**, được tạo theo quy tắc thuật toán; với password-based encryption có thể sinh **salt ngẫu nhiên riêng cho mỗi file hoặc đối tượng**.

~~~text
Password P + Salt A + parameters ──KDF──> Key A
Password P + Salt B + parameters ──KDF──> Key B

Salt A khác Salt B ⇒ kết quả thông thường khác nhau
~~~

Lợi ích:

- Hai tệp mã hóa bằng cùng một password không tự có cùng password-derived key nếu dùng salt khác.
- Khó tái sử dụng trực tiếp bảng kết quả đoán mật khẩu đã tính cho salt khác.
- Giúp phân biệt phiên bản/đối tượng khi thiết kế metadata và khôi phục.

**Salt không phải secret**. Lưu salt trong header của bản mã là bình thường. Nếu attacker có password đúng, họ cũng có thể dùng salt công khai để dẫn xuất key. **Salt không thay cho mật khẩu đủ mạnh hoặc KDF đủ chi phí**.

### 4.2. Iterations, memory cost và parallelism

- **PBKDF2:** chọn iteration count theo chính sách và benchmark. Số lần quá thấp tạo điều kiện thử nhanh; số lần quá cao có thể gây độ trễ hoặc DoS.
- **Argon2id:** điều chỉnh memory cost, time cost, parallelism dựa trên máy chủ hoặc thiết bị mục tiêu và mô hình đe dọa.
- **scrypt:** có các tham số điều chỉnh chi phí CPU/bộ nhớ, cần kiểm tra giới hạn và cấu hình khi xác minh.
- **Output length:** kết quả đủ cho thuật toán cần dùng, ví dụ 32 byte cho AES-256, nhưng **không hàm ý 256 bit entropy đầu vào**.

Tham số nên được **lưu cùng bản mã** (trừ secrets), **phiên bản hóa**, **giới hạn giá trị có thể chấp nhận** và cập nhật theo chính sách. Không nhận tham số chi phí từ header chưa được tin cậy rồi sử dụng không giới hạn tài nguyên.

### 4.3. Password encoding cũng là một phần giao thức

Password có thể chứa Unicode, dấu tiếng Việt, emoji hoặc ký tự có nhiều cách biểu diễn. Hai bên tạo byte khác nhau sẽ dẫn xuất ra hai khóa khác nhau. Cần thống nhất:

- API dùng **char[]**, byte hay chuỗi, với charset/normalization nào.
- Salt là **byte ngẫu nhiên**, không phải text tùy tiện.
- Phiên bản KDF và thư viện có quy tắc xử lý password rõ ràng.
- Có chính sách tương thích dữ liệu cũ khi thay chuẩn encoding.

Không tự “normalize” password ở bước giải mã nếu hệ thống trước đó dùng quy tắc khác mà không có chiến lược migration.

## 5. Kiến trúc đơn giản: password → KDF → AES-GCM

Đối với **mã hóa tệp cá nhân bằng passphrase**, một mô hình cơ bản hợp lý là:

~~~mermaid
flowchart TD
    P["Password/passphrase"] --> KDF["Password-based KDF: Argon2id / scrypt / PBKDF2"]
    S["Salt ngẫu nhiên + cost + version"] --> KDF
    KDF --> K["Encryption key"]
    K --> E["AEAD Encrypt: AES-GCM"]
    D["Plaintext"] --> E
    N["Nonce duy nhất theo khóa"] --> E
    A["AAD: format + object ID"] --> E
    E --> C["Ciphertext + authentication tag"]
    C --> F["Tệp được mã hóa"]
    S --> F
    N --> F
~~~

Khi mở tệp, bên nhận dùng **cùng password**, salt, KDF algorithm và parameters để dẫn xuất **cùng encryption key**, sau đó cung cấp nonce, ciphertext, tag và AAD để giải mã. Nếu password sai hoặc bản mã bị sửa, phép xác thực AEAD phải thất bại.

**Chú ý ba giới hạn:**

1. Một password yếu vẫn có thể bị thử đoán ngoại tuyến trên ciphertext.
2. Đổi password trong cách này thường **đòi hỏi giải mã rồi mã hóa lại dữ liệu**, trừ khi kiến trúc lưu một khóa dữ liệu độc lập.
3. Mất password có thể làm dữ liệu **không thể khôi phục** nếu không có recovery design.

Trong ứng dụng có nhiều tệp hoặc dữ liệu dài hạn, việc **tách DEK và KEK** thường thuận tiện và an toàn hơn về vận hành.

## 6. Kiến trúc ưu tiên cho dữ liệu dài hạn: DEK ngẫu nhiên và KEK dẫn xuất

**Envelope encryption** tách khóa mã hóa nội dung **DEK (Data Encryption Key)** và khóa bảo vệ DEK **KEK (Key Encryption Key)**.

Với kịch bản người dùng mở tệp bằng passphrase:

1. Sinh **DEK ngẫu nhiên** có entropy phù hợp, chẳng hạn 32 byte cho AES-256.
2. Dùng DEK với **AES-GCM** và nonce phù hợp để mã hóa tệp.
3. Sinh salt ngẫu nhiên và dùng **password-based KDF** để tạo **password-derived KEK**.
4. Dùng cơ chế **key wrapping có xác thực** (ví dụ AES-KW/KWP, hoặc AES-GCM với nonce và AAD đúng quy tắc) để bọc DEK dưới KEK.
5. Lưu **wrapped DEK, salt, KDF version/parameters, wrap nonce/tag, data nonce/tag, format version và metadata cần thiết** cạnh ciphertext.
6. Khi mở tệp, dẫn xuất lại KEK từ password; **unwrap DEK** rồi mới dùng DEK để giải mã nội dung.

~~~mermaid
flowchart TD
    PW["Password"] --> F["Password KDF + salt + cost"]
    F --> KEK["Password-derived KEK"]
    RNG["CSPRNG"] --> DEK["DEK ngẫu nhiên"]
    KEK --> W["Authenticated key wrapping"]
    DEK --> W
    W --> WD["Wrapped DEK"]
    DEK --> G["AES-GCM data encryption"]
    TXT["Plaintext"] --> G
    G --> CT["Ciphertext + data nonce/tag"]
    WD --> STORE["Encrypted package"]
    CT --> STORE
    META["KDF algorithm/version/salt + wrap metadata"] --> STORE
~~~

### 6.1. Vì sao tách DEK và KEK hữu ích?

| Nhu cầu | Dùng trực tiếp password-derived DEK | Tách random DEK + password-derived KEK |
| --- | --- | --- |
| Đổi password | Thường phải re-encrypt nội dung | Có thể chỉ cần **unwrap rồi rewrap cùng DEK** bằng KEK từ password mới |
| Nhiều người được cấp quyền | Khó chia sẻ nếu một key gắn với một password | Có thể lưu **nhiều wrapped copies của cùng DEK** cho những quyền mở khác nhau |
| Dữ liệu lớn | Mỗi lần đổi password phải xử lý toàn bộ payload | Rewrap thường chỉ xử lý DEK ngắn |
| Rotation khóa dữ liệu | Gắn chặt với việc đổi password | Có thể xoay DEK riêng theo chính sách |
| Mất hoặc lộ password | Dữ liệu/khóa liên quan bị ảnh hưởng | **Vẫn bị ảnh hưởng** nếu attacker mở được DEK; tách lớp bọc không xóa nguy cơ brute force |

**Điều quan trọng:** password-derived KEK vẫn được bảo vệ bởi **sức mạnh password và chi phí KDF**, không tự an toàn như KEK ngẫu nhiên trong KMS. Tách lớp giúp quản lý và rotation nhưng **không cứu được dữ liệu đã bị attacker giải mã**.

### 6.2. Nếu có KMS/HSM thì sao?

Trong hệ thống backend, thường không cần bắt người quản trị nhập password để dẫn xuất khóa của toàn bộ database. Phương án phù hợp hơn có thể là:

~~~text
KMS/HSM giữ KEK không xuất được
          |
          | GenerateDataKey / Wrap / Unwrap theo IAM
          v
DEK ngẫu nhiên -> AES-GCM dữ liệu
          |
          v
Ciphertext + wrapped DEK + key ID/version + nonce/tag
~~~

KMS/HSM cung cấp **quyền quản lý, rotation, audit và ranh giới giữ KEK** mà password-based KDF tự thân không có. Một principal có quyền gọi Decrypt/Unwrap rộng vẫn nguy hiểm ngay cả khi KEK non-exportable; phải giới hạn IAM theo workload, tenant và nghiệp vụ.

**Đừng nhầm:**

- Password-based KDF tạo **KEK từ password** khi use case cần người dùng nhập passphrase.
- **KMS KEK** thường là khóa bí mật mạnh được quản lý bởi dịch vụ khóa; không nhất thiết liên quan password.
- **DEK ngẫu nhiên** bảo vệ dữ liệu; nếu cần nhiều người truy cập, có thể bọc DEK bằng nhiều KEK được cấp quyền riêng.

## 7. Salt, nonce, AAD, tag và metadata phải đi cùng bản mã

Khi thiết kế định dạng tệp mã hóa, không chỉ lưu mỗi ciphertext.

| Trường | Ví dụ vai trò | Bí mật? | Điều quan trọng |
| --- | --- | --- | --- |
| **formatVersion** | Chọn cách phân tích gói | Không | Không tự chấp nhận algorithm/format cũ bị cấm |
| **kdfAlgorithm** | Argon2id, scrypt hoặc PBKDF2-HMAC-SHA256 | Không | Tên/phiên bản phải thuộc allowlist |
| **kdfParameters** | Iterations, memory/time, output length | Không | Giới hạn tài nguyên và hỗ trợ migration |
| **salt** | Dẫn xuất KEK từ password | Không | Tạo ngẫu nhiên riêng; lưu để tái dẫn xuất |
| **wrappedDek** | DEK được bọc dưới KEK | Không cần bí mật riêng nếu wrap đúng | Phải có xác thực/tính toàn vẹn |
| **wrapNonce/tag** | Tham số của AES-GCM dùng bọc DEK | Không | Không tái dùng nonce với cùng KEK |
| **dataNonce/tag** | Tham số của AEAD mã hóa dữ liệu | Không | Không tái dùng nonce với cùng DEK |
| **AAD/context** | Object ID, tenant, purpose, schema | Thường không | Byte nhất quán; lấy ngữ cảnh kỳ vọng từ nguồn tin cậy |
| **ciphertext** | Nội dung đã mã hóa | Có thể lưu ngoài ranh giới tin cậy | Không dùng plaintext nếu tag chưa xác thực |
| **key ID/version** | Chọn đúng lớp khóa/phiên bản | Thường không | Không cho attacker tự chỉ định khóa/trust root tùy ý |

Ví dụ cấu trúc minh họa:

~~~json
{
  "formatVersion": 1,
  "objectId": "invoice-154",
  "kdf": "PBKDF2WithHmacSHA256",
  "iterations": 600000,
  "saltBase64": "<random salt>",
  "wrapAlgorithm": "AES-256-GCM",
  "wrapNonceBase64": "<unique wrap nonce>",
  "wrappedDekAndTagBase64": "<authenticated encrypted DEK>",
  "dataAlgorithm": "AES-256-GCM",
  "dataNonceBase64": "<unique data nonce>",
  "ciphertextAndTagBase64": "<encrypted invoice>"
}
~~~

Các chuỗi trong dấu ngoặc chỉ minh họa, **không phải dữ liệu mã hóa thật**. Gói lưu trên disk có thể công khai salt và nonce. **Không lưu password, KEK dạng rõ hoặc DEK dạng rõ** trong gói.

### 7.1. AES-GCM cần nonce không trùng cho mỗi khóa

Với AES-GCM, việc **tái sử dụng cùng nonce dưới cùng khóa** có thể gây mất cả tính bí mật và tính toàn vẹn. Độ dài nonce 96 bit thường được sử dụng. Nếu dùng nonce ngẫu nhiên, cần đánh giá số lượng lần mã hóa dưới cùng khóa và xác suất va chạm; nếu cần bảo đảm chặt, dùng chiến lược nonce duy nhất có quản lý trạng thái phù hợp.

Trong mô hình hai tầng ở trên:

- **DEK** bảo vệ payload và cần **data nonce** đúng quy tắc.
- **KEK** bảo vệ DEK và cần **wrap nonce** đúng quy tắc nếu dùng AES-GCM làm cơ chế wrap.
- Khi đổi password và tái dẫn xuất **KEK mới**, nên tạo **salt và wrap nonce mới**.
- Khi **rewrap** cùng DEK, **ciphertext dữ liệu và data nonce có thể giữ nguyên**.

Đừng dùng **salt = nonce** theo một quy ước tùy tiện rồi giả định các yêu cầu của hai trường giống nhau. Salt có vai trò trong KDF; nonce có vai trò trong AEAD.

### 7.2. AAD ràng buộc bản mã với mục đích và tài nguyên

**Additional Authenticated Data (AAD)** là metadata **được xác thực nhưng không mã hóa**. Có thể ràng buộc:

~~~text
AAD cho wrapped DEK = Encode("myapp/v1", "wrap-dek", objectId)
AAD cho ciphertext  = Encode("myapp/v1", "encrypt-data", objectId)
~~~

Khi giải mã, objectId kỳ vọng phải đến từ **tài nguyên đã được xác định và phân quyền**. Nếu ứng dụng chỉ tin objectId do bản ghi không tin cậy cung cấp, attacker có thể di chuyển **nguyên cả gói ciphertext + metadata** sang một vị trí khác và vẫn qua được tag trong ngữ cảnh đó.

Encoding AAD phải là **byte chính xác**, không nhập nhằng và có phiên bản: length-prefix, kiểu dữ liệu, charset, thứ tự trường. Nếu hai bên dựng AAD khác nhau, tag sẽ thất bại ngay cả khi password đúng.

### 7.3. Kiểm tra thứ tự xác thực

Không trả plaintext ra UI, không ghi dữ liệu lâu dài hoặc thực hiện nghiệp vụ với dữ liệu **chưa được xác thực**. Một số API streaming có thể đưa ra plaintext trước khi xác thực tag cuối; bên sử dụng phải trì hoãn hành động cho tới khi **AEAD authentication hoàn tất**.

**Không có đường fallback bỏ tag, bỏ AAD hoặc dùng AES-ECB/CBC** chỉ để giải mã khi password không mở được tệp cũ. Đó là hạ cấp bảo mật có thể bị lợi dụng.

## 8. Ví dụ Java 17: password KDF → KEK → bọc DEK → mã hóa AES-GCM

Ví dụ sau là một **mô hình kỹ thuật học tập**, sử dụng các API chuẩn có sẵn trong Java 17:

- **PBKDF2WithHmacSHA256** tạo KEK 256 bit từ password + salt + iterations.
- **SecureRandom** tạo DEK 256 bit, salt và nonce.
- **AES/GCM/NoPadding** dùng một lần để **bọc DEK** (như một mã hóa có xác thực cho vật liệu khóa ngắn) và một lần khác để **mã hóa plaintext bằng DEK**.
- **AAD** khác nhau theo purpose để tránh trộn lớp bọc với lớp dữ liệu.
- **Đổi password** có thể chỉ unwrap/rewrap DEK, giữ nguyên ciphertext của dữ liệu.

**Giới hạn quan trọng:** trong production, cân nhắc **Argon2id hoặc scrypt** qua thư viện có bảo trì khi chính sách cho phép; hoặc dùng KMS/HSM quản lý KEK. AES-GCM dùng để bảo vệ DEK cần nonce/tag và quy trình an toàn; có thể dùng **AES-KW/AES-KWP** hoặc API key wrap của KMS khi phù hợp hơn. Ví dụ không triển khai đầy đủ lưu tệp, IAM, chính sách account, retry hay backup.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

public final class PasswordEnvelopeDemo {
    private static final SecureRandom RNG = new SecureRandom();

    private static final int FORMAT_VERSION = 1;
    private static final int SALT_BYTES = 16;
    private static final int NONCE_BYTES = 12;
    private static final int AES_KEY_BYTES = 32;
    private static final int GCM_TAG_BITS = 128;
    // Minh họa, cần benchmark và chính sách khi triển khai thực tế.
    private static final int ITERATIONS = 600_000;
    private static final int MAX_ACCEPTED_ITERATIONS = 2_000_000;

    public record Envelope(
            int formatVersion,
            int iterations,
            String objectId,
            byte[] salt,
            byte[] wrapNonce,
            byte[] wrappedDekAndTag,
            byte[] dataNonce,
            byte[] ciphertextAndTag) {}

    // Chỉ áp dụng cho PBKDF2WithHmacSHA256 của bản demo.
    private static byte[] deriveKek(
            char[] password, byte[] salt, int iterations) throws Exception {
        if (salt == null || salt.length != SALT_BYTES
                || iterations < 1
                || iterations > MAX_ACCEPTED_ITERATIONS) {
            throw new IllegalArgumentException("Unsupported KDF parameters");
        }

        PBEKeySpec spec = new PBEKeySpec(
            password, salt, iterations, AES_KEY_BYTES * 8);
        try {
            SecretKeyFactory kdf = SecretKeyFactory.getInstance(
                "PBKDF2WithHmacSHA256");
            return kdf.generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    private static byte[] randomBytes(int size) {
        byte[] result = new byte[size];
        RNG.nextBytes(result);
        return result;
    }

    private static byte[] aad(String purpose, String objectId) {
        try {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(buffer);

            putString(out, "password-envelope-demo/v1");
            out.writeInt(FORMAT_VERSION);
            putString(out, purpose);
            putString(out, objectId);
            out.flush();
            return buffer.toByteArray();
        } catch (IOException e) {
            throw new IllegalStateException("AAD encoding failed", e);
        }
    }

    private static void putString(DataOutputStream out, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length); // Length prefix là số byte UTF-8.
        out.write(bytes);
    }

    private static byte[] gcm(
            int mode,
            byte[] rawKey,
            byte[] nonce,
            byte[] data,
            byte[] aad) throws Exception {
        if (rawKey.length != AES_KEY_BYTES
                || nonce.length != NONCE_BYTES) {
            throw new IllegalArgumentException("Invalid key/nonce length");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(mode, new SecretKeySpec(rawKey, "AES"),
            new GCMParameterSpec(GCM_TAG_BITS, nonce));
        cipher.updateAAD(aad); // AAD phải được cấp trước dữ liệu.
        return cipher.doFinal(data);
    }

    // Mã hóa nội dung bằng DEK ngẫu nhiên, KEK do KDF tạo chỉ bọc DEK.
    public static Envelope encrypt(
            char[] password, String trustedObjectId, byte[] plaintext)
            throws Exception {

        byte[] salt = randomBytes(SALT_BYTES);
        byte[] wrapNonce = randomBytes(NONCE_BYTES);
        byte[] dataNonce = randomBytes(NONCE_BYTES);
        byte[] dek = randomBytes(AES_KEY_BYTES);
        byte[] kek = null;

        try {
            kek = deriveKek(password, salt, ITERATIONS);

            byte[] ciphertextAndTag = gcm(Cipher.ENCRYPT_MODE,
                dek, dataNonce, plaintext,
                aad("encrypt-data", trustedObjectId));

            byte[] wrappedDekAndTag = gcm(Cipher.ENCRYPT_MODE,
                kek, wrapNonce, dek,
                aad("wrap-dek", trustedObjectId));

            return new Envelope(
                FORMAT_VERSION, ITERATIONS, trustedObjectId,
                salt, wrapNonce, wrappedDekAndTag,
                dataNonce, ciphertextAndTag);
        } finally {
            Arrays.fill(dek, (byte) 0);
            if (kek != null) Arrays.fill(kek, (byte) 0);
        }
    }

    private static byte[] unwrapDek(
            char[] password, Envelope stored, String expectedObjectId)
            throws Exception {

        if (stored.formatVersion() != FORMAT_VERSION
                || !stored.objectId().equals(expectedObjectId)) {
            throw new IllegalArgumentException("Format/context mismatch");
        }

        byte[] kek = deriveKek(
            password, stored.salt(), stored.iterations());
        try {
            byte[] dek = gcm(Cipher.DECRYPT_MODE, kek,
                stored.wrapNonce(), stored.wrappedDekAndTag(),
                aad("wrap-dek", expectedObjectId));

            if (dek.length != AES_KEY_BYTES) {
                Arrays.fill(dek, (byte) 0);
                throw new IllegalArgumentException("Invalid DEK size");
            }
            return dek;
        } finally {
            Arrays.fill(kek, (byte) 0);
        }
    }

    public static byte[] decrypt(
            char[] password, Envelope stored, String expectedObjectId)
            throws Exception {
        // Production: trước đó phải kiểm tra identity và quyền tài nguyên.
        byte[] dek = unwrapDek(password, stored, expectedObjectId);
        try {
            return gcm(Cipher.DECRYPT_MODE, dek,
                stored.dataNonce(), stored.ciphertextAndTag(),
                aad("encrypt-data", expectedObjectId));
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }

    // Đổi password: giữ nguyên DEK và ciphertext dữ liệu;
    // chỉ tạo KEK mới và bản bọc DEK mới.
    public static Envelope rewrapPassword(
            char[] oldPassword, char[] newPassword,
            Envelope stored, String expectedObjectId) throws Exception {

        byte[] dek = unwrapDek(oldPassword, stored, expectedObjectId);
        byte[] freshSalt = randomBytes(SALT_BYTES);
        byte[] freshWrapNonce = randomBytes(NONCE_BYTES);
        byte[] newKek = null;

        try {
            newKek = deriveKek(newPassword, freshSalt, ITERATIONS);
            byte[] freshWrappedDek = gcm(Cipher.ENCRYPT_MODE, newKek,
                freshWrapNonce, dek, aad("wrap-dek", expectedObjectId));

            return new Envelope(FORMAT_VERSION, ITERATIONS, expectedObjectId,
                freshSalt, freshWrapNonce, freshWrappedDek,
                stored.dataNonce(), stored.ciphertextAndTag());
        } finally {
            Arrays.fill(dek, (byte) 0);
            if (newKek != null) Arrays.fill(newKek, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        char[] oldPassword = "demo-old-passphrase-only".toCharArray();
        char[] newPassword = "demo-new-passphrase-only".toCharArray();
        byte[] data = "invoice=154;amount=250000"
            .getBytes(StandardCharsets.UTF_8);
        try {
            Envelope original = encrypt(
                oldPassword, "invoice-154", data);
            byte[] decrypted = decrypt(
                oldPassword, original, "invoice-154");
            System.out.println("Initial decrypt works: "
                + Arrays.equals(data, decrypted));

            Envelope rotated = rewrapPassword(
                oldPassword, newPassword, original, "invoice-154");
            byte[] reopened = decrypt(
                newPassword, rotated, "invoice-154");
            System.out.println("New password decrypts: "
                + Arrays.equals(data, reopened));

            System.out.println("Data ciphertext unchanged by rewrap: "
                + Arrays.equals(original.ciphertextAndTag(),
                                rotated.ciphertextAndTag()));

            // Không in password/DEK/KEK/ciphertext nhạy cảm vào log.
        } finally {
            Arrays.fill(oldPassword, '\0');
            Arrays.fill(newPassword, '\0');
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
Initial decrypt works: true
New password decrypts: true
Data ciphertext unchanged by rewrap: true
~~~

### 8.1. Đọc hiểu mã theo hai tầng khóa

**Tầng 1 — Mã hóa dữ liệu:**

~~~text
random DEK (32 byte) + data nonce
      └──AES-GCM + data AAD──> ciphertextAndTag
~~~

**Tầng 2 — Bảo vệ DEK:**

~~~text
password + random salt + PBKDF2 parameters ──> KEK
random DEK + KEK + wrap nonce + wrap AAD ──> wrappedDekAndTag
~~~

Khi giải mã, password-derived KEK chỉ có một nhiệm vụ: **mở DEK**. Sau đó DEK dùng cho AES-GCM dữ liệu. Nhờ vậy, đổi password có thể **thay lớp bọc** mà không phải mã hóa lại nội dung có thể rất lớn.

### 8.2. Vì sao mã vẫn chỉ để học?

- **PBKDF2 iterations là tham số minh họa**, không phải chuẩn bất biến; cần theo chính sách và benchmark hệ thống.
- **Argon2id/scrypt** có thể phù hợp hơn cho password mới tùy chính sách và khả năng tích hợp thư viện.
- **SecureRandom tạo nonce** cho ví dụ từng đối tượng. Sản phẩm thật cần thiết kế giới hạn số lần mã hóa dưới một KEK/DEK, tránh nonce reuse và xử lý concurrency.
- **Salt và parameters đến từ package có thể bị sửa**: code giới hạn độ dài/iterations nhưng production còn phải có allowlist thuật toán, giới hạn kích thước package, quota và chiến lược chống DoS.
- **Arrays.fill** chỉ giảm thời gian giữ một số bản sao mảng trong JVM; PBEKeySpec, SecretKeySpec, provider và GC có thể tạo bản sao nội bộ. Không bảo đảm xóa hoàn toàn khóa khỏi bộ nhớ.
- **Record chứa byte[] mutable**: trong production, nên thiết kế API bất biến/defensive copy và serialization an toàn; tránh caller sửa mảng sau khi kiểm tra.
- **Đổi password trong demo không hủy bản sao envelope cũ**. Một backup chứa wrapped DEK cũ vẫn có thể mở bằng password cũ; không tuyên bố password cũ đã bị thu hồi trên mọi bản sao.
- **Không có quyền truy cập/định danh** trong ví dụ: cần kiểm tra tenant, object ID, principal được phép trước khi xử lý bản mã.
- **Không có định dạng persistent versioned** hoàn chỉnh, chống rollback, key escrow hoặc recovery policy.

**Không tự triển khai một dịch vụ quản lý mật khẩu hoặc hệ thống mã hóa tệp production từ ví dụ mà chưa có review bảo mật.** Ưu tiên thư viện/định dạng đã được kiểm chứng và chính sách quản lý khóa rõ ràng.

## 9. Đổi mật khẩu, rotation và revocation: khác nhau thế nào?

### 9.1. Đổi password có thể chỉ rewrap DEK

Trong mô hình dữ liệu tách DEK/KEK:

~~~text
Trước:
Password P1 --KDF(salt1)--> KEK1 --unwrap--> DEK --decrypt--> Data

Sau rewrap:
Password P2 --KDF(salt2)--> KEK2 --unwrap--> CÙNG DEK --decrypt--> Data
                                 ^
                    wrapped DEK mới dưới KEK2
~~~

Đổi password bằng rewrap thường có các bước:

1. Xác thực người yêu cầu có quyền đổi password và quyền với tài nguyên.
2. Dùng password cũ hoặc một đường phục hồi được cấp quyền để unwrap DEK.
3. Sinh **salt mới**, dẫn xuất **KEK mới** từ password mới bằng KDF/parameters được phê duyệt.
4. Bọc lại DEK dưới KEK mới với **wrap nonce/tag** và metadata mới.
5. Ghi nhận một bản envelope mới **theo cơ chế cập nhật nguyên tử** để tránh mất dữ liệu giữa chừng.
6. Kiểm tra việc mở bằng password mới, quản lý backup và các bản sao wrapped DEK cũ.
7. Giới hạn/tắt đường sử dụng password cũ ở các hệ thống quản lý phiên và khóa liên quan.

**Rewrap** không cần mã hóa lại phần nội dung nếu DEK không đổi. Tuy nhiên, **không thể coi đây là thu hồi password cũ tuyệt đối** khi attacker có bản backup chứa wrapped DEK từ trước.

### 9.2. Nếu password cũ hoặc DEK đã bị lộ

Phân biệt:

| Sự cố | Rewrap đủ không? | Lý do |
| --- | --- | --- |
| Người dùng chủ động đổi password, **không có bằng chứng lộ** | Thường đủ cho đường truy cập hiện tại, nếu backup được quản trị | Mục tiêu chỉ thay bí mật mở khóa trong tương lai |
| Password cũ đã lộ, attacker có **bản sao wrapped DEK cũ** | **Không đủ** | Attacker vẫn có thể dẫn xuất KEK cũ để unwrap DEK từ bản sao |
| Password cũ đã lộ nhưng không có dữ liệu/bản sao bị đánh cắp | Cần đánh giá | Cần chặn đường truy cập cũ, rà soát log, credential và phạm vi |
| DEK rõ bị lộ | **Không đủ** | Bọc lại DEK không xóa được giá trị DEK mà attacker biết |
| KEK trong KMS bị lộ cùng wrapped DEK | **Không đủ** | Có thể cần DEK mới và re-encrypt dữ liệu liên quan |
| Người dùng quên password và không có recovery mechanism | Có thể **không giải được** | Password-derived KEK không thể tái tạo nếu không biết password |

Khi cần **thực sự thay bí mật mã hóa dữ liệu**, phải tạo **DEK mới** và **re-encrypt** nội dung bằng DEK mới, nonce/tag/AAD theo thiết kế. Việc này không xóa những bản sao plaintext đã bị exfiltrate, nhưng giúp dữ liệu dưới khóa mới không tiếp tục phụ thuộc vào DEK cũ.

### 9.3. Password reset cho dữ liệu được mã hóa phía client

Trong mô hình **zero-knowledge/client-side encryption**, server có thể không có khả năng lấy DEK dạng rõ. Khi người dùng quên password:

- Nếu **không có recovery key/recovery envelope** được thiết kế trước, dữ liệu có thể không thể khôi phục.
- Nếu có **recovery key** riêng, nó phải được cấp phát và bảo vệ như một credential/khóa rất nhạy cảm.
- Nếu có nhiều thiết bị, có thể lưu **wrapped DEK riêng theo public key của từng thiết bị** với giao thức chuẩn và xác thực thiết bị.
- Cơ chế reset password của tài khoản **không tự cho phép mở lại dữ liệu đã mã hóa** nếu chưa được thiết kế đường unwrap hợp lệ.

Không xây “master password của admin” ẩn trong code để mở mọi dữ liệu; điều này có thể phá mô hình tin cậy và tạo điểm lộ nghiêm trọng.

## 10. Phân biệt password hashing đăng nhập và password-based encryption

Hai trường hợp đều có chữ “password” và có thể dùng password-based KDF, nhưng mục tiêu rất khác nhau.

| Tiêu chí | Xác minh password đăng nhập | Mã hóa dữ liệu bằng passphrase |
| --- | --- | --- |
| Mục tiêu | So sánh password ứng viên với verifier | Tạo/mở khóa mã hóa dữ liệu |
| Có cần plaintext password sau đó? | Không | Người dùng phải cung cấp password đúng khi cần giải mã hoặc dùng recovery |
| Dữ liệu cần lưu | Verifier/hash + salt + KDF version/params | Salt, KDF metadata, nonce/tag, ciphertext, wrapped DEK nếu có |
| Có cần DEK/KEK không? | Không nhất thiết | Thường có, nhất là với nhiều tệp hoặc dữ liệu dài hạn |
| Đổi password | Rehash khi có password mới | Rewrap hoặc re-encrypt theo kiến trúc |
| Khi database bị lộ | Kẻ tấn công thử đoán password từ verifier | Kẻ tấn công thử đoán password từ bản mã/tag/wrapped DEK |
| Khôi phục | Reset password có thể lập verifier mới | Reset password không tự tái tạo khóa giải mã cũ |

**Không dùng verifier làm encryption key.** Nếu database chứa verifier bị đánh cắp, attacker đã có giá trị có thể đóng vai trò khóa nếu ứng dụng thiết kế sai. Lúc đó KDF đắt đến mấy cũng không giúp giữ bí mật dữ liệu đã bị mã hóa bằng chính verifier công khai từ database.

### 10.1. Pepper không sửa được mọi vấn đề

**Pepper** là một bí mật bổ sung được giữ ngoài database (ví dụ KMS/HSM hoặc secret store), thường liên quan tới quy trình bảo vệ verifier. Nó không thay salt riêng và password-based KDF.

Đối với password-based encryption, có thể có mô hình kết hợp thêm một secret từ server để tạo hoặc mở KEK, nhưng đây là một **kiến trúc quản lý quyền và khả năng khôi phục** riêng, không được tự ghép password với pepper qua phép nối rồi SHA-256. Nó ảnh hưởng mạnh đến **offline availability** (không còn mở được dữ liệu khi server không sẵn sàng) và **rotation**. Cần dùng một thiết kế đã được phân tích, có tách miền và backup/recovery.

## 11. Vòng đời khóa và ranh giới IAM/KMS/HSM

Đối với một hệ thống quản lý khóa, bài toán không kết thúc sau khi gọi PBKDF2 hoặc Argon2id.

| Giai đoạn | Password-based encryption | Key management liên quan |
| --- | --- | --- |
| **Tạo** | Sinh salt, tham số và DEK/nonce đúng chuẩn | CSPRNG, KDF policy, thuật toán/độ dài |
| **Cấp phát** | Xác định ai được cấp quyền mở dữ liệu hoặc recovery envelope | IAM theo principal, tenant, resource |
| **Lưu trữ** | Chỉ lưu wrapped DEK/ciphertext/metadata; không log password/KEK/DEK rõ | KMS/HSM, secret storage, backup và phân tách quyền |
| **Sử dụng** | Nhận password an toàn, derive KEK, unwrap DEK, decrypt AEAD | KDF cost limit, rate limit online, giới hạn quyền và audit |
| **Rotation** | Đổi password, salt/KEK; có thể rewrap DEK | Key ID/version, migration, kiểm tra bản sao cũ |
| **Thu hồi** | Chặn credential và đường unwrap cũ, đánh giá bản sao | Kiểm soát phiên, thay quyền KMS, xử lý sự cố |
| **Hủy** | Chỉ hủy khóa/bản bọc khi đã kiểm tra phụ thuộc dữ liệu | Đảm bảo khả năng restore theo thời hạn giữ |
| **Kiểm toán** | Theo dõi đổi password, lỗi unwrap, thay recovery key | Log an toàn, giám sát lạm dụng và phê duyệt |

### 11.1. KMS/HSM có bảo đảm password-derived KEK an toàn không?

Nếu ứng dụng gửi password cho KMS dưới dạng plaintext trong một thao tác không được thiết kế cho password-based encryption, việc đó có thể làm **lộ password qua API, log, nhà cung cấp hoặc ranh giới không mong muốn**. Cần hiểu KMS hỗ trợ thao tác nào, có **DeriveKey** không, điều kiện giữ secret ra sao và chính sách audit những gì.

KMS/HSM không tự “sửa” một password quá yếu nếu password vẫn là đầu vào chính và attacker có bản mã để thử offline. Ngược lại, nếu hệ thống có **KEK ngẫu nhiên non-exportable trong KMS**, có thể tránh việc dùng password làm bí mật bảo vệ dữ liệu trực tiếp.

### 11.2. Phân quyền theo người dùng, tenant và workload

Một người dùng nhập đúng passphrase **không đủ** để ứng dụng cho phép mở tệp của tenant khác nếu hệ thống dựa vào quyền tổ chức:

- **Xác thực:** người gọi có danh tính gì, phiên đã được bảo vệ ra sao?
- **Ủy quyền:** principal đó được phép truy cập object/tenant nào?
- **Khóa:** người đó có đúng wrapped DEK/KEK của đối tượng đã cấp quyền không?
- **Ngữ cảnh:** AAD và key context có ràng buộc với tenant/object đã xác thực không?
- **Kiểm toán:** ai thực hiện, khóa/version nào được sử dụng, có bất thường không?

Phân tách **production/staging/dev**, dịch vụ và tenant nếu cần để hạn chế phạm vi lộ khóa. Đừng chia sẻ một password mã hóa root giữa tất cả môi trường.

## 12. Threat model: những rủi ro cần kiểm soát

| Rủi ro | Dấu hiệu | Kiểm soát |
| --- | --- | --- |
| **Offline password guessing** | Attacker có ciphertext, salt, nonce và tag | Password mạnh, memory-hard KDF/chi phí PBKDF2 theo chính sách, quản trị bản sao |
| **Salt cố định/tái sử dụng vô tội vạ** | Các đối tượng có chung password-derived KEK | Salt riêng, định dạng metadata và vòng đời rõ |
| **Nonce reuse dưới AES-GCM key** | Nhiều bản mã dùng cùng key/nonce | Nonce duy nhất, giới hạn mã hóa, rotation |
| **Không xác thực ciphertext/DEK bọc** | Dùng CBC/ECB không có MAC, bỏ tag | AEAD hoặc wrapping chuẩn có xác thực |
| **Header/metadata bị sửa** | Bản mã chuyển tenant/object | AAD, kiểm tra quyền tài nguyên, canonical serialization |
| **KDF cost từ header không tin cậy** | Gói mã hóa yêu cầu tính toán khổng lồ | Allowlist thuật toán, giới hạn cost/size, resource quotas |
| **Password/KEK/DEK bị log** | Secrets xuất hiện trong telemetry, crash dumps | Secret hygiene, redaction, quy tắc memory handling |
| **Một root password chung** | Mọi tenant/backup phụ thuộc một bí mật | DEK độc lập, KEK tách môi trường/tenant, KMS/HSM |
| **Mất password** | Không thể derive KEK đúng | Recovery key/recovery envelope có kiểm soát hoặc chấp nhận mất dữ liệu |
| **Đổi password chỉ rewrap nhưng backup cũ còn** | Password cũ mở được wrapped DEK đã sao chép | Backup retention, revoke access, đánh giá re-encrypt |
| **Lạm dụng quyền KMS Decrypt/Unwrap** | Workload bị chiếm có thể lấy DEK | IAM least privilege, rate controls, audit, anomaly detection |
| **Replay/rollback gói cũ** | Bản gói hợp lệ cũ được thay vào vị trí hiện tại | Version/counter/state chống rollback ở tầng nghiệp vụ |
| **Tưởng KDF tạo 256 bit entropy từ password yếu** | Mật khẩu đơn giản nhưng dùng output 32 byte | Giáo dục entropy và đánh giá mô hình đe dọa đúng |

### 12.1. Đổi password không tự chống rollback

Kẻ tấn công có thể giữ **bản encrypted package cũ** gồm wrapped DEK dưới password cũ, rồi thay file hiện tại bằng bản đó. Nếu ứng dụng chỉ kiểm tra AEAD tag mà không có **trạng thái/phiên bản đáng tin bên ngoài package**, nó có thể không biết đó là một bản cũ hợp lệ.

Cần cân nhắc **monotonic version, server-side state, secure counters, lịch sử phiên bản được xác thực** hoặc biện pháp tương ứng theo hệ thống. Một tag hợp lệ chỉ chứng minh tính toàn vẹn **trong một ngữ cảnh mật mã**, không tự bảo đảm freshness.

### 12.2. Trường hợp chia sẻ tệp cho nhiều người dùng

Nếu Alice và Bob cần mở cùng dữ liệu, tránh đặt **password chung công khai** cho cả nhóm. Có thể thiết kế:

- Một **DEK ngẫu nhiên** mã hóa tệp.
- Mỗi người được cấp một **wrapped DEK** riêng dưới KEK phù hợp.
- Mỗi bản bọc có **recipient/identity, thuật toán, key version và policy** rõ ràng.
- Khi thu hồi Bob, phải đánh giá **Bob đã có DEK hay bản mã** chưa: xóa wrapped DEK của Bob không làm Bob quên DEK đã lấy.

Nếu cần thu hồi tính bí mật với dữ liệu **trong tương lai**, có thể phải **thay DEK và re-encrypt**, đồng thời kiểm soát bản sao đã phân phối. Không thể thu hồi dữ liệu đã đọc/đã sao chép chỉ bằng thao tác xóa một key envelope.

## 13. Khi nào dùng password, khi nào dùng KMS?

| Bối cảnh | Thiết kế thường phù hợp | Điều cần đặc biệt lưu ý |
| --- | --- | --- |
| Người dùng mã hóa một file offline | Passphrase mạnh → password KDF → KEK/DEK → AEAD | Offline guessing, mất password, salt/params/nonce/tag và recovery |
| Ứng dụng di động cần dữ liệu cục bộ | Khóa ngẫu nhiên được bảo vệ trong keystore của hệ điều hành khi có thể | Thiết bị bị chiếm, backup, biometric/PIN không luôn là encryption key trực tiếp |
| Dịch vụ Java mã hóa database nhiều tenant | DEK ngẫu nhiên + KEK trong KMS/HSM + IAM | Tách quyền, key version, audit, rotation và restore |
| Đăng nhập tài khoản | Password verifier bằng Argon2id/scrypt/PBKDF2 phù hợp | Không dùng verifier làm AES key; rate limit, MFA/recovery |
| Giao tiếp TLS | Key agreement được xác thực + KDF theo giao thức | Không lấy password người dùng làm TLS traffic key |
| Phân phối DEK cho đối tác | Key wrapping/KEM hoặc public-key encryption theo chuẩn, xác thực public key | Không gửi DEK rõ hay thay bằng cùng password yếu |
| Backup dài hạn | KMS key/KEK có kế hoạch khôi phục; AEAD và metadata đầy đủ | RTO/RPO, phụ thuộc khóa cũ, kiểm thử restore thực tế |

**Mục tiêu không phải xóa bỏ password khỏi mọi sản phẩm.** Password là một dạng credential hợp lệ trong nhiều hệ thống, nhưng nó nên **đi qua cơ chế dẫn xuất và chính sách kiểm soát phù hợp**, không tự hóa thân thành encryption key AES chỉ nhờ encoding hoặc hashing.

## 14. Checklist triển khai

1. **Phân biệt rõ:** use case là password login verifier hay password-based file encryption?
2. **Nguồn bí mật:** password đủ mạnh chưa; có thể thay bằng DEK ngẫu nhiên/KMS không?
3. **Password KDF:** đã chọn Argon2id/scrypt/PBKDF2 phù hợp, không dùng raw password hoặc SHA-256(password)?
4. **Salt:** riêng theo đối tượng, tạo đúng quy tắc, lưu cùng metadata để tái dẫn xuất?
5. **Cost:** iterations/memory/time/parallelism đã benchmark, giới hạn DoS và có version?
6. **Encoding:** xử lý Unicode và byte password nhất quán qua các phiên bản?
7. **DEK/KEK:** có nên tách DEK ngẫu nhiên khỏi KEK dẫn xuất để dễ rotation/rewrap?
8. **AEAD:** đang dùng AES-GCM hoặc cơ chế phù hợp, có tag xác thực và xử lý lỗi đúng?
9. **Nonce:** không lặp dưới cùng key; quản lý riêng tầng wrap và tầng data?
10. **AAD:** metadata an ninh được ràng buộc với tenant/object/purpose và mã hóa byte không nhập nhằng?
11. **Metadata:** giữ format version, thuật toán KDF, salt, cost, wrap nonce/tag, data nonce/tag, key ID?
12. **Không ghi secrets:** password, KEK, DEK không xuất hiện trong source/log/telemetry/file package?
13. **IAM:** đúng principal mới có quyền truy cập tài nguyên và thao tác unwrap/Decrypt?
14. **Rotation:** đã phân biệt password rewrap, DEK re-encrypt và KEK KMS rotation?
15. **Compromise:** nếu password/DEK/KEK hoặc quyền dùng khóa bị lộ, xác định được phạm vi ảnh hưởng?
16. **Backup:** bản gói cũ còn mở được bằng password/KEK cũ hay không; có cơ chế thu hồi/kiểm kê?
17. **Recovery:** mất password thì có đường khôi phục được phê duyệt hay chấp nhận mất dữ liệu?
18. **Audit:** theo dõi thay khóa, thay KDF, lỗi unwrap, lạm dụng KMS mà không lộ mật mã?
19. **Replay/rollback:** có yêu cầu freshness/version được kiểm tra ở ngoài bản mã không?
20. **Thử nghiệm:** test đúng password, sai password, ciphertext/tag bị sửa, context sai, salt/iterations sai, rotation và restore?

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Mật khẩu có 12 ký tự và SHA-256 trả về 32 byte. Có thể gọi đó là khóa có 256 bit entropy không?

**Đáp án:** Không. Độ dài output không nâng entropy của nguồn. Nếu mật khẩu dễ đoán, attacker có thể thử mật khẩu và băm nhanh đến khi giải được bản mã.

**Câu 2.** Vì sao PBKDF2 hoặc Argon2id có ích hơn SHA-256(password) cho bài toán mã hóa bằng password?

**Đáp án:** Chúng là password-based KDF được thiết kế cho đầu vào dễ bị thử đoán; tăng chi phí CPU và/hoặc bộ nhớ của mỗi lần đoán mật khẩu. Chúng không khiến mật khẩu yếu tự biến thành khóa ngẫu nhiên mạnh.

**Câu 3.** Salt có cần được giấu khỏi attacker không?

**Đáp án:** Thường không. Salt có thể lưu công khai cùng bản mã; nó làm phân tách lần dẫn xuất và giảm khả năng tái dùng kết quả tính trước. Bí mật chính là password, và hệ thống vẫn phải bảo vệ password tốt.

**Câu 4.** Vì sao không dùng password verifier lưu trong database để mã hóa hóa đơn?

**Đáp án:** Nếu verifier bị lộ cùng database, attacker có thể có ngay byte được dùng làm encryption key mà không cần đoán mật khẩu. Password authentication và encryption phải tách rời.

**Câu 5.** Lợi ích của random DEK + password-derived KEK so với dùng password-derived key trực tiếp mã hóa tệp lớn là gì?

**Đáp án:** Khi đổi password, có thể unwrap và rewrap DEK bằng KEK mới, không phải re-encrypt tệp lớn. Đồng thời dễ quản lý nhiều cách cấp quyền mở tệp. Tuy nhiên độ an toàn khi attacker thử password vẫn phụ thuộc password/KDF.

**Câu 6.** Sau khi đổi password và rewrap DEK, các bản sao encrypted package cũ có tự mất khả năng giải mã không?

**Đáp án:** Không. Nếu attacker còn package cũ và biết password cũ, họ có thể mở wrapped DEK cũ. Rewrap không xóa bản sao hay bí mật đã bị lộ.

**Câu 7.** Một tệp AES-GCM dùng nonce lặp dưới cùng DEK nhưng password KDF rất mạnh. Dữ liệu có an toàn không?

**Đáp án:** Không. Nonce reuse của AES-GCM có thể phá tính bí mật và toàn vẹn bất kể KEK được dẫn xuất tốt thế nào.

**Câu 8.** Người dùng quên password của tệp mã hóa phía client, server chỉ giữ ciphertext và không có recovery envelope. Server có thể đơn giản reset password để giải tệp cũ không?

**Đáp án:** Không. Reset mật khẩu xác thực không tự tái tạo KEK/DEK cũ. Không có recovery key hoặc cách mở hợp lệ khác thì dữ liệu có thể không khôi phục được.

**Câu 9.** KMS/HSM giữ KEK non-exportable, nhưng workload bị chiếm có quyền Decrypt mọi DEK. Có nguy cơ không?

**Đáp án:** Có. Attacker có thể lạm dụng quyền unwrap/decrypt để lấy DEK hoặc plaintext thông qua API, dù không trích xuất KEK. Cần IAM theo phạm vi, giám sát và audit.

**Câu 10.** Nếu KDF đã có salt, có thể dùng salt như nonce cho AES-GCM mà không cần kiểm tra gì nữa không?

**Đáp án:** Không. Salt phục vụ dẫn xuất khóa; nonce phục vụ AEAD và phải tuân thủ quy tắc duy nhất theo khóa. Hai tham số có yêu cầu và vòng đời riêng.

## Kết luận

**Không dùng password làm encryption key trực tiếp** vì password không phải nguồn key material ngẫu nhiên mạnh, còn phép encoding, padding hoặc băm nhanh không tự tạo thêm entropy. Nếu bắt buộc dùng passphrase để mở dữ liệu, hãy sử dụng **password-based KDF** được thiết kế cho việc chống thử đoán, **salt riêng, tham số/phiên bản rõ, authenticated encryption và cơ chế khôi phục phù hợp**.

Với dữ liệu lâu dài hoặc nhiều người dùng, thiết kế **DEK ngẫu nhiên + KEK bảo vệ DEK** giúp phân tách vai trò khóa, hỗ trợ rewrap/rotation và giới hạn rủi ro vận hành. Khi có KMS/HSM, hãy dùng quyền quản lý khóa, IAM và audit thay vì đặt một password chung vào mọi workload. **Mã hóa chỉ an toàn đến mức bí mật và quyền sử dụng khóa được bảo vệ; khóa 256 bit được tạo từ mật khẩu yếu vẫn có thể là điểm yếu lớn nhất của hệ thống.**
