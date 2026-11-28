# Không sinh key từ từ khóa dễ đoán

## 1. Vì sao không được sinh khóa mật mã từ từ khóa dễ đoán?

Một **khóa mật mã (cryptographic key)** phải có cấu trúc, độ dài và đặc biệt là **mức độ khó dự đoán** phù hợp với thuật toán và mô hình đe dọa. Nếu ứng dụng tạo khóa từ một từ, cụm từ hoặc giá trị mà người khác có thể đoán hoặc liệt kê được, kẻ tấn công có thể thử các ứng viên để tìm ra khóa, dù ứng dụng dùng một thuật toán mạnh như **AES-256-GCM**.

Ví dụ không an toàn:

~~~text
Từ khóa con người chọn: "my-company-secret"
           |
           v
   SHA-256(UTF-8(text))
           |
           v
  32 byte được gọi là "AES-256 key"
~~~

Đầu ra SHA-256 dài **256 bit**, nhưng số lượng khóa có thể xảy ra vẫn bị giới hạn bởi số lượng từ khóa đầu vào mà đối thủ có thể đoán. **Hash không tự tạo ra entropy còn thiếu**. Nếu đầu vào nằm trong một từ điển ngắn, đối thủ chỉ cần duyệt từ điển, băm từng mục và thử giải mã/xác minh.

Trong chương **Key generation** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, quy tắc “Không sinh key từ từ khóa dễ đoán” là nguyên tắc xuyên suốt:

- **Sinh DEK/KEK, khóa AES, HMAC:** ưu tiên **CSPRNG/DRBG** được phê duyệt hoặc KMS/HSM.
- **Sinh cặp khóa RSA/ECDSA/Ed25519/X25519:** dùng key generator đúng thuật toán và provider đáng tin.
- **Khi bắt buộc xuất phát từ mật khẩu người dùng:** sử dụng **password-based KDF** phù hợp và chấp nhận rủi ro đoán mật khẩu; không coi nó tương đương một khóa ngẫu nhiên.
- **Lưu trữ và vận hành:** kết hợp envelope encryption, IAM, versioning, rotation, revocation, audit và hủy khóa theo vòng đời.

**Điểm cần nhớ:** *khóa có đúng 256 bit* và *khóa có độ khó đoán tương đương 256 bit* là hai mệnh đề khác nhau.

### 1.1. Ví dụ ứng dụng mắc lỗi

~~~java
// KHÔNG AN TOÀN: minh họa anti-pattern, không dùng production.
byte[] bytes = java.security.MessageDigest
    .getInstance("SHA-256")
    .digest("company-prod-2026".getBytes(
        java.nio.charset.StandardCharsets.UTF_8));

javax.crypto.SecretKey key =
    new javax.crypto.spec.SecretKeySpec(bytes, "AES");
~~~

Không có lỗi cú pháp nào khiến API từ chối khóa trên. AES có thể hoạt động và bài test encrypt/decrypt có thể **PASS**, nhưng người biết quy ước đặt tên hoặc đoán được từ khóa sẽ tính ra cùng key bytes.

**Điều nguy hiểm** là tính đúng đắn chức năng bị nhầm với tính an toàn của quá trình sinh khóa.

## 2. Độ dài, entropy và khả năng đoán khác nhau thế nào?

**Độ dài khóa** cho biết có bao nhiêu bit trong biểu diễn. **Entropy** mô tả độ bất định của nguồn sinh trong một mô hình xác suất. Một khóa dài 256 bit có thể chỉ chứa vài chục bit bất định nếu được suy ra từ một nguồn nhỏ.

Với tập N lựa chọn có xác suất bằng nhau, lượng bất định theo bit được tính bằng:

\[
H = \log_2(N).
\]

Bảng minh họa:

| Nguồn đầu vào | Số ứng viên giả định | Entropy tối đa nếu đều nhau | Kết luận |
|---|---:|---:|---|
| Một trong 10.000 từ khóa quen thuộc | 10.000 | Khoảng **13,3 bit** | Rất ít so với khóa ngẫu nhiên |
| Mã PIN 6 chữ số, phân bố đều | 1.000.000 | Khoảng **19,9 bit** | Có thể liệt kê trong nhiều mô hình offline |
| Timestamp tính bằng giây trong một ngày | 86.400 | Khoảng **16,4 bit** | Dễ khoanh vùng nếu biết ngày tạo |
| 16 byte sinh độc lập từ CSPRNG thích hợp | \(2^{128}\) kết quả khả dĩ | Tối đa **128 bit** | Phù hợp khóa 128-bit nếu nguồn bảo đảm |
| 32 byte sinh độc lập từ CSPRNG thích hợp | \(2^{256}\) kết quả khả dĩ | Tối đa **256 bit** | Phù hợp tạo vật liệu ngẫu nhiên 256-bit |

Các dòng dùng CSPRNG dựa trên **giả định nguồn và generator hoạt động đúng**, không phải khẳng định mọi hệ thống sinh 32 byte đều đạt đúng 256 bit entropy.

### 2.1. Min-entropy và thiên lệch

Người dùng thường chọn những cụm từ phổ biến với xác suất **không đồng đều**. Trong an ninh mật mã, xác suất của ứng viên **dễ đoán nhất** rất quan trọng.

Một cách mô tả là **min-entropy**:

\[
H_\infty(X)=-\log_2\bigl(\max_x P[X=x]\bigr).
\]

Nếu một mật khẩu rất phổ biến được chọn với xác suất cao, đối thủ thử nó đầu tiên và có thể thành công nhanh hơn kết quả đếm tổng số chuỗi lý thuyết.

Không thể tính độ mạnh thực tế chỉ bằng **số ký tự**, vì những chuỗi như “Welcome2026!”, tên ứng dụng, ngày sinh hoặc tên tenant có cấu trúc dễ bị đoán.

### 2.2. Hash dài không kéo dài không gian tìm kiếm

Giả sử từ khóa chỉ có N khả năng và hệ thống tạo:

\[
K = \operatorname{SHA256}(\mathrm{UTF8}(\text{keyword})).
\]

Với một hàm xác định, số giá trị K có thể được tạo không vượt quá N:

\[
\lvert\{K\}\rvert \leq N.
\]

Khi đối thủ biết phương pháp sinh khóa, họ thử từng **keyword ứng viên**, tính SHA-256 và kiểm tra đầu ra. Độ dài hàm băm không làm tăng số lượng ứng viên ban đầu.

## 3. Những nguồn đầu vào dễ đoán cần tránh

| Nguồn | Ví dụ | Lý do không phù hợp để sinh khóa trực tiếp |
|---|---|---|
| **Từ khóa thông dụng** | “secret”, “admin”, “company-key” | Có trong dictionary và các mẫu thường gặp |
| **Tên hệ thống/tenant** | “orders-prod”, “tenant-42” | Có thể quan sát hoặc suy từ URL, log, cấu hình |
| **Mật khẩu người dùng ngắn** | Chuỗi người tự nhớ, dùng lại nhiều nơi | Dễ tấn công dictionary/offline nếu có ciphertext |
| **Biến môi trường hard-code** | Giá trị chung trong image hoặc deployment | Có thể bị sao chép và không phải nguồn entropy mới |
| **Timestamp/PID** | Giờ khởi động, process ID | Không gian ứng viên nhỏ và có cấu trúc |
| **Counter / sequence ID** | 1, 2, 3… | Dễ đoán theo thứ tự |
| **UUID không rõ nguồn** | UUID dựa trên thời gian/định danh khác, hoặc UUID từ PRNG yếu | Format UUID không cam kết mức bảo mật của key |
| **java.util.Random** | Seed từ thời gian | PRNG không được thiết kế để tạo khóa bí mật |
| **ThreadLocalRandom** | Sinh bytes trong workload | Dành cho ngẫu nhiên thông thường, không phải key generation |
| **Seed cố định** | \`new Random(1234)\`, CSPRNG tự cấu hình từ seed yếu | Có thể tái tạo chuỗi output hoặc làm giảm bảo mật |
| **SHA-256 của thông tin công khai** | Hash hostname, email, IP | Vẫn dễ tính bởi người biết đầu vào |
| **Một khóa dùng chung mọi môi trường** | Prod/staging/test cùng secret | Lộ ở môi trường yếu làm ảnh hưởng toàn bộ |
| **“Random” lấy từ chuỗi có sẵn** | Lấy 32 ký tự đầu của một câu dài | Chuỗi nhìn phức tạp nhưng không được sinh ngẫu nhiên |

**Không phải mọi UUID đều yếu**: ví dụ UUIDv4 được sinh bằng nguồn ngẫu nhiên phù hợp có một mức bất định nhất định, nhưng **UUID không phải API key generation** và không thể tự coi mọi dạng UUID hoặc mọi implementation có đủ entropy/đúng key format. Với AES/HMAC, hãy dùng key generator hoặc CSPRNG được kiểm chứng.

### 3.1. Trường hợp dễ gây nhầm lẫn: một cụm từ rất dài

Một câu dài do con người tự nghĩ không tự động cung cấp nhiều entropy. Câu văn, ca dao, khẩu hiệu công ty, cách viết theo mẫu và biến thể tên sản phẩm đều có thể xuất hiện trong danh sách đoán.

**Passphrase sinh từ các từ được chọn ngẫu nhiên một cách độc lập** có tính chất khác với câu do người tự chọn. Tuy nhiên, ngay cả passphrase ngẫu nhiên vẫn là **secret mà người có thể biết, ghi lại hoặc bị phishing**; khi nhiệm vụ chỉ cần một DEK ngẫu nhiên, không có lý do kỹ thuật để chuyển nó thành mật khẩu do người nhớ.

## 4. Đối thủ có thể đoán key như thế nào?

Có hai mô hình cần phân biệt.

### 4.1. Tấn công offline

Nếu đối thủ có **ciphertext + nonce/IV + tag**, hoặc một vật kiểm tra tương đương, họ có thể thử những từ khóa ứng viên **ngoài hệ thống**:

~~~mermaid
flowchart LR
    A["Danh sách từ khóa ứng viên"] --> H["SHA-256 hoặc KDF theo cấu hình đã biết"]
    H --> K["Khóa ứng viên"]
    K --> V["Thử giải mã hoặc kiểm tra AEAD tag"]
    C["Ciphertext, nonce và tag đã thu thập"] --> V
    V --> Q{"Ứng viên hợp lệ?"}
    Q -->|Không| A
    Q -->|Có| R["Nguy cơ lộ plaintext / giả mạo dữ liệu"]
~~~

Với **AES-GCM**, một tag hợp lệ là tín hiệu xác thực mạnh để thử khóa ứng viên khi có đủ dữ liệu. Đối thủ không cần đăng nhập hay gọi API KMS cho mỗi lần thử nếu cấu trúc ứng dụng cho phép kiểm tra offline.

Tốc độ đoán phụ thuộc thuật toán dẫn xuất, thiết bị, số ứng viên và dữ liệu đã có. **Không cần đưa ra một con số guesses/second cố định** để nhận ra rằng từ khóa ít bất định là rủi ro.

### 4.2. Tấn công online

Nếu việc kiểm tra secret chỉ thực hiện qua một server có hạn mức, logging, khóa tài khoản hoặc MFA, tốc độ thử có thể bị giới hạn. Nhưng không nên giả định một khóa AES được tạo từ từ khóa có bảo vệ **online-only**: khi ciphertext/tag hoặc bản hash bị lấy, đối thủ có thể chuyển sang offline.

**Kết luận:** Kiểm soát API rate limit không thay thế việc sinh key có entropy cao.

### 4.3. Tác động khi dùng chung key

Nếu ứng dụng tạo cùng khóa từ **tên công ty** rồi dùng cho mọi tenant, đối thủ chỉ cần đoán **một khóa** để mở phạm vi dữ liệu lớn. Ngay cả khi từ khóa từng là bí mật, việc **reuse** làm tăng blast radius.

Với chữ ký số, một private key hoặc seed dễ đoán có thể cho phép đối thủ tạo chữ ký hợp lệ, không chỉ giải mã dữ liệu.

## 5. Vì sao “hash nhiều lần” không giải quyết gốc vấn đề?

Các phương án sau **không đủ** để biến từ khóa yếu thành một khóa ngẫu nhiên mạnh:

~~~text
SHA256(keyword)
SHA256(SHA256(keyword))
MD5(keyword) nối với SHA256(keyword)
Base64(SHA256(keyword))
Truncate/Pad(keyword, 32 bytes)
SHA256(keyword || appName || "some-fixed-salt")
~~~

**Lý do chung:** các giá trị trên được tính **xác định từ đầu vào dễ đoán**, cùng các tham số công khai hoặc cố định. Đối thủ có thể lặp lại quy trình cho từng ứng viên.

### 5.1. Salt công khai không phải nguồn entropy bí mật

**Salt** ngẫu nhiên và riêng biệt giúp phân biệt kết quả dẫn xuất khi hai người có cùng password, hạn chế việc dùng lại bảng tính trước. Nó **không làm password yếu trở thành password có 256 bit entropy**.

Ví dụ:

\[
K=\mathrm{KDF}(\text{password},\text{salt},\text{cost}).
\]

Đối thủ biết salt (thường được lưu công khai cạnh ciphertext) vẫn thử từng password ứng viên. Salt chủ yếu ngăn dùng cùng một phép tính/lookup chung cho quá nhiều người và hỗ trợ phân tách kết quả.

### 5.2. Pepper khác salt

Một **pepper** là secret dùng thêm trong một số thiết kế password protection, được bảo vệ ngoài kho password hashes, có thể trong KMS/HSM. Nó có thể bổ sung lớp kiểm soát trong mô hình cụ thể, nhưng tạo **bài toán quản lý secret và rotation** riêng.

**Pepper không phải lý do để dùng trực tiếp password yếu làm DEK**, và một pepper nếu bị dùng như bí mật dài hạn cũng phải có entropy, owner, quyền và lifecycle tương ứng.

### 5.3. KDF chậm chỉ làm mỗi lần đoán tốn kém hơn

Password-based KDF như **Argon2id**, **scrypt** hoặc **PBKDF2** làm tăng chi phí thử mỗi ứng viên theo các tham số. Chúng **không thể khôi phục entropy đã thiếu** nếu password chỉ là một trong vài lựa chọn phổ biến.

Đây là cơ chế quản lý rủi ro khi **bắt buộc** phụ thuộc mật khẩu, không phải cách thay thế sinh khóa ngẫu nhiên cho hệ thống không cần password.

## 6. Chọn cơ chế sinh key theo nhu cầu

| Nhu cầu | Cách phù hợp | Tránh |
|---|---|---|
| **AES DEK cho tài liệu/dataset** | \`KeyGenerator("AES")\` với CSPRNG, hoặc KMS GenerateDataKey | \`SHA256(tenantName)\` |
| **KEK/master key** | Generate trong KMS/HSM, non-exportable khi hỗ trợ | Lưu secret hard-code trong app |
| **HMAC key / API MAC secret** | Generate byte ngẫu nhiên từ CSPRNG theo chính sách | Mật khẩu chung, tên service |
| **RSA/ECDSA/Ed25519 key pair** | KeyPairGenerator/KMS/HSM đúng thuật toán | Seed hoặc private scalar suy từ từ khóa |
| **X25519/ECDHE ephemeral key** | Provider secure key generation theo giao thức | Reuse private key cố định/timestamp |
| **Khóa mã hóa file khi chỉ biết password** | Password-based KDF mạnh + salt + version/params + AEAD | SHA256(password) rồi encrypt |
| **Lưu password để đăng nhập** | Password hashing/verification phù hợp (Argon2id/scrypt/PBKDF2 theo yêu cầu) | Mã hóa password bằng key hard-code hoặc lưu plaintext |
| **Dẫn xuất nhiều subkeys từ secret mạnh** | HKDF và nhãn domain separation | Dùng cùng bytes cho mọi purpose |
| **Token/credential ngẫu nhiên** | SecureRandom/CSPRNG với độ dài theo threat model | UUID không kiểm soát nguồn hoặc timestamp |

### 6.1. Generate khác derive và import

- **Generate key:** tạo key material mới bằng cơ chế random/key generator thích hợp.
- **Derive key:** dùng KDF từ một **bí mật đã có** theo salt/info/context, ví dụ từ ECDH shared secret hoặc mật khẩu.
- **Import key:** đưa key material đã tồn tại vào KMS/HSM; không làm tăng entropy của nguồn vốn yếu.

Nếu nghiệp vụ không yêu cầu một người **nhớ** hoặc **nhập** password để mở khóa, **đừng thêm password vào key generation** chỉ để “dễ cấu hình”.

## 7. Nguồn sinh khóa an toàn: OS CSPRNG, DRBG và KMS/HSM

**CSPRNG (cryptographically secure pseudorandom number generator)** cung cấp output khó dự đoán khi trạng thái được khởi tạo an toàn và thuật toán vận hành đúng. Một **DRBG** là cơ chế sinh số ngẫu nhiên xác định dùng seed/entropy đầu vào và quy trình reseed theo đặc tả.

Nguồn được dùng trong thiết kế:

- **OS cryptographic RNG** được hệ điều hành hỗ trợ và cập nhật.
- **Java SecureRandom** của provider đáng tin, theo chính sách môi trường.
- **KeyGenerator/KeyPairGenerator** trừu tượng hóa việc sinh khóa phù hợp từng thuật toán.
- **KMS/HSM GenerateKey/GenerateDataKey/GenerateRandom** nếu nhà cung cấp hỗ trợ tính năng phù hợp.

**Không tự seed một CSPRNG bằng một chuỗi dễ đoán và tin rằng output sẽ an toàn vì API mang tên SecureRandom.** Chi tiết trộn entropy, setSeed và provider có thể khác nhau; cách bảo thủ là để provider/OS xử lý khởi tạo entropy theo hướng dẫn, và không dùng một nguồn yếu thay thế.

### 7.1. “SecureRandom.getInstanceStrong()” có phải luôn tốt hơn không?

Không nhất thiết cho mọi ứng dụng. \`SecureRandom.getInstanceStrong()\` chọn một provider/thuật toán từ cấu hình của môi trường và có thể **chặn hoặc có đặc tính vận hành không phù hợp** ở một số hệ thống. \`new SecureRandom()\` với provider đã được đánh giá thường là lựa chọn khả thi.

Việc chọn provider cần xét **yêu cầu bảo mật, nguồn entropy, availability, FIPS/compliance nếu áp dụng**, và kiểm thử trong container/VM. Không tự tạo fallback sang \`java.util.Random\` khi SecureRandom/KMS lỗi.

### 7.2. Cẩn trọng với VM snapshot, container và early boot

Snapshot/restore sai cách hoặc RNG chưa được khởi tạo đủ có thể ảnh hưởng tính độc lập của secret, đặc biệt trong môi trường hạn chế entropy. Hệ thống cần dùng runtime/OS/provider có cơ chế reseed thích hợp, kiểm tra hành vi khởi động và chính sách clone/restore.

**Không kiểm thử tính an toàn chỉ bằng cách tạo 1.000 khóa và thấy chúng khác nhau**. Tính không trùng lặp trong một mẫu nhỏ không chứng minh seed khó đoán hay trạng thái generator chống tấn công.

## 8. Java: các anti-pattern cần nhận diện trong code review

### 8.1. Băm từ khóa thành AES key

~~~java
// SAI: đầu vào có thể đoán được, SHA-256 không tăng entropy.
String phrase = "shop-prod-master-key";
byte[] material = java.security.MessageDigest
    .getInstance("SHA-256")
    .digest(phrase.getBytes(java.nio.charset.StandardCharsets.UTF_8));
javax.crypto.SecretKey aes =
    new javax.crypto.spec.SecretKeySpec(material, "AES");
~~~

### 8.2. Tạo key từ Random và seed cố định

~~~java
// SAI: Random không phải cryptographic RNG.
java.util.Random random = new java.util.Random(20261128L);
byte[] key = new byte[32];
random.nextBytes(key);
// new SecretKeySpec(key, "AES") không sửa được nguồn key yếu.
~~~

### 8.3. Dùng thông tin công khai làm “secret”

~~~java
// SAI: tenantId và tên service có thể bị quan sát/đoán.
String source = tenantId + ":" + serviceName;
byte[] material = java.security.MessageDigest
    .getInstance("SHA-256")
    .digest(source.getBytes(java.nio.charset.StandardCharsets.UTF_8));
~~~

Dù tenantId là một chuỗi dài hay được encode bằng Base64, nó không tự trở thành bí mật mật mã.

### 8.4. Seed deterministic để test

Một seed cố định đôi khi hữu ích trong test mô phỏng **không liên quan secret**, nhưng **không được đi vào production key generation**. Với test mật mã, nên dùng **test vectors** và fake providers trong phạm vi kiểm thử để tái lập kết quả, thay vì sửa code production nhận seed yếu.

### 8.5. Quy tắc code review

Tìm những dấu hiệu như:

- \`MessageDigest.digest(password.getBytes(...))\` sau đó \`new SecretKeySpec(..., "AES")\`.
- \`new Random(...)\`, \`ThreadLocalRandom\`, \`Math.random()\` dùng để tạo secret.
- Key bytes hoặc seed được tính từ \`System.currentTimeMillis()\`, hostname, username, tenant name.
- \`Base64.getDecoder().decode(...)\` nhận giá trị hard-code và tạo private/symmetric key.
- Biến \`encryptionKey\` nằm trong source, test fixtures hoặc image dùng chung production.
- \`SecureRandom\` bị thay bằng custom PRNG không được đánh giá.

**Lưu ý:** Có những API dùng hash hoặc KDF một cách đúng đắn trong *key schedule*. Phải xem **nguồn bí mật đầu vào và purpose**, không kết luận mọi xuất hiện của SHA-256 gần key đều sai.

## 9. Java 17: sinh AES-256 DEK ngẫu nhiên đúng cách

Ví dụ sau sử dụng \`KeyGenerator\` để tạo **AES-256 key** và \`SecureRandom\` để tạo **nonce 96 bit** cho một lần mã hóa AES-GCM. Demo chạy một lần trong RAM để minh họa luồng, **không phải thiết kế lưu key dài hạn hoặc nonce cho nhiều writers production**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class GenerateRandomAesKeyExample {
    private static final SecureRandom RNG = new SecureRandom();

    public record CipherRecord(byte[] nonce, byte[] ciphertextAndTag) {}

    public static SecretKey generateDek() throws Exception {
        KeyGenerator gen = KeyGenerator.getInstance("AES");
        gen.init(256, RNG);
        return gen.generateKey();
    }

    public static CipherRecord encrypt(
            SecretKey dek, byte[] plaintext, byte[] aad)
            throws Exception {
        byte[] nonce = new byte[12];
        RNG.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE, dek,
            new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return new CipherRecord(nonce, cipher.doFinal(plaintext));
    }

    public static byte[] decrypt(
            SecretKey dek, CipherRecord record, byte[] aad)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE, dek,
            new GCMParameterSpec(128, record.nonce()));
        cipher.updateAAD(aad);
        return cipher.doFinal(record.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        SecretKey dek = generateDek();

        byte[] aad = "tenant=42;object=901"
            .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Example protected content"
            .getBytes(StandardCharsets.UTF_8);

        CipherRecord record = encrypt(dek, plaintext, aad);
        byte[] restored = decrypt(dek, record, aad);
        try {
            if (!Arrays.equals(plaintext, restored)) {
                throw new IllegalStateException("Mismatch");
            }
            System.out.println("Random DEK + AES-GCM OK");
        } finally {
            Arrays.fill(plaintext, (byte) 0);
            Arrays.fill(restored, (byte) 0);
        }

        // Production: cần KMS/KEK, key ID/version, nonce
        // uniqueness toàn hệ thống, IAM và vòng đời key.
    }
}
~~~

### 9.1. Tại sao ví dụ này tốt hơn SHA256(keyword)?

- **KeyGenerator("AES")** sinh vật liệu khóa theo đúng thuật toán và độ dài.
- **SecureRandom** là giao diện CSPRNG, không lấy từ tên app hoặc một passphrase cố định.
- Không có nguồn secret được hard-code trong Java source.
- **AES-GCM** dùng nonce riêng cho phép Encrypt và kiểm tra tag khi Decrypt.
- **AAD** gắn metadata vào quá trình xác thực, dù bản thân AAD không được mã hóa.
- Đoạn code **không log DEK** hoặc private material.

### 9.2. Những điều ví dụ không bảo đảm

- **Nonce 12 byte sinh ngẫu nhiên** chỉ hỗ trợ uniqueness theo xác suất; ở quy mô nhiều writer/khối lượng cao phải thiết kế giới hạn sử dụng key và cơ chế nonce toàn hệ thống phù hợp.
- **SecretKey trong JVM** có thể tồn tại trong heap/provider và không có bảo đảm zeroization hoàn toàn.
- **Cùng một DEK** không nên được sử dụng ngoài cryptoperiod và phạm vi đã định.
- Bản ghi thực tế phải lưu **nonce, ciphertext, tag, key ID/version, encrypted DEK hoặc reference**, và quản lý AAD/format nhất quán.
- Không có **KMS wrap, recovery, tenant authorization, error handling, storage** hay rotate trong demo.

**Không được dùng plaintext key hard-code thay cho KMS chỉ để tăng khả năng tái lập bài test.**

## 10. KMS/HSM và envelope encryption: khi ứng dụng không nên giữ master key

Trong hệ thống lưu trữ có nhiều người dùng, cách phổ biến là tách **DEK** khỏi **KEK**:

- **DEK (Data Encryption Key):** khóa mã hóa trực tiếp dữ liệu bằng AES-GCM.
- **KEK (Key Encryption Key):** bảo vệ DEK bằng cơ chế wrap/encrypt phù hợp; thường nằm trong KMS/HSM.
- **Encrypted DEK:** bản mã của DEK có thể được lưu cạnh ciphertext.
- **Key reference/version:** giúp xác định KEK cần dùng để unwrap trong vòng đời dữ liệu.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng đã xác thực
    participant K as KMS/HSM
    participant D as Data store

    A->>K: GenerateDataKey dưới KEK đã quản lý
    K-->>A: Plaintext DEK nếu API cho phép + encrypted DEK
    Note over A: AES-GCM encrypt với nonce phù hợp
    A->>D: Ciphertext, tag, nonce, encrypted DEK, metadata
    Note over A: Giảm thời gian sống plaintext DEK
    A->>K: Audit qua KMS API
~~~

**Không phải KMS nào cũng có API GenerateDataKey cùng ngữ nghĩa.** Một số dịch vụ tạo DEK trong ứng dụng hoặc xử lý cryptographic operation bên trong provider. Hãy dùng đúng API và capability đã xác minh, không giả định KEK có thể export hoặc mọi provider hỗ trợ X25519.

### 10.1. Vì sao không lấy tên tenant làm DEK?

Nếu ứng dụng tính \`SHA256(tenantId)\` cho DEK, kẻ biết tenantId có thể tính ra khóa. Envelope encryption với **DEK được sinh an toàn** và **KEK được bảo vệ trong KMS/HSM** giải quyết bài toán khác: tách miền tin cậy, hạn chế export, tập trung IAM/audit và hỗ trợ rotation có kiểm soát.

**Một KEK mạnh không làm DEK yếu được dẫn xuất từ tên tenant thành bí mật.** Nếu plaintext DEK vốn đoán được, dù encrypted DEK được wrap dưới KMS KEK, đối thủ có thể thử nguồn DEK dự đoán được trực tiếp với ciphertext/tag.

### 10.2. KMS không thay trách nhiệm IAM

Một KEK non-exportable vẫn có thể bị lạm dụng nếu principal có quyền **Decrypt/Unwrap** quá rộng. Cần tách key administrator, data owner, encryptor/decryptor và auditor, theo **least privilege**, xác thực tenant và giám sát bất thường.

## 11. Khi buộc phải tạo khóa từ mật khẩu người dùng

Có tình huống hợp lệ mà ứng dụng cần mã hóa một file và **chỉ người biết mật khẩu mới mở được**, chẳng hạn tệp backup cá nhân, kho offline hoặc một định dạng mã hóa dựa mật khẩu. Trong trường hợp này, **không thể đơn giản thay bằng DEK ngẫu nhiên nếu không có cơ chế khác để phân phối hoặc bảo vệ DEK**.

Hướng đúng là **password-based key derivation** với password đủ mạnh, salt ngẫu nhiên, tham số tính toán thích hợp và AEAD.

~~~mermaid
flowchart TD
    P["Password / passphrase người dùng cung cấp"] --> K["Password-based KDF"]
    S["Salt ngẫu nhiên, lưu công khai"] --> K
    C["Algorithm + cost parameters"] --> K
    K --> E["Keying material cho AEAD / key wrapping"]
    E --> A["AES-GCM encrypt/decrypt"]
    A --> D["Ciphertext, tag, nonce"]
    S --> M["Metadata định dạng"]
    C --> M
    D --> M
~~~

**Phải chấp nhận giới hạn:** nếu người dùng chọn password như “password123” hoặc tên công ty, kẻ có ciphertext vẫn có thể thử password offline. KDF khiến mỗi lần thử tốn tài nguyên hơn, **không bảo đảm password yếu trở thành khóa ngẫu nhiên 256-bit**.

### 11.1. Những lựa chọn KDF

| Cơ chế | Tính chất | Khi cân nhắc |
|---|---|---|
| **Argon2id** | Password hashing/KDF memory-hard, điều chỉnh time và memory cost | Lựa chọn hiện đại thường được ưu tiên nếu thư viện/nền tảng hỗ trợ |
| **scrypt** | KDF memory-hard, điều chỉnh cost/memory | Phương án phù hợp theo yêu cầu thư viện/khả năng triển khai |
| **PBKDF2-HMAC-SHA-256** | Điều chỉnh iteration count, hỗ trợ rộng trong Java/JCA | Khi cần tương thích/tuân thủ và cấu hình tham số đúng |
| **HKDF-SHA-256** | Dẫn xuất subkeys từ input key material có entropy thích hợp | Không phải password KDF chống dictionary offline |
| **SHA-256(password)** | Hash nhanh, chi phí thử đoán thấp | Không dùng làm password-based encryption key derivation |

**Tham số KDF phải được chọn từ chính sách và hướng dẫn bảo mật hiện hành, benchmark trên phần cứng đích và cân nhắc nguy cơ từ chối dịch vụ**, không hard-code một giá trị cũ rồi coi là phù hợp mãi mãi.

### 11.2. Salt, metadata và kiểm thử mật khẩu

- **Salt:** ngẫu nhiên, đủ dài theo thiết kế; ví dụ 16 byte là độ dài thường dùng. Salt không cần bí mật nhưng phải được lưu chính xác.
- **Không dùng một salt cố định cho mọi người hoặc mọi file** khi thiết kế yêu cầu salt riêng: người dùng có cùng password sẽ cho cùng derived key và tăng nguy cơ tái sử dụng tính toán.
- **Metadata:** lưu KDF algorithm/version, salt, cost parameters, AEAD algorithm, nonce/IV và authentication tag theo định dạng nhất quán.
- **AAD:** ràng buộc version, object ID hoặc thông tin không được phép tráo đổi khi thiết kế yêu cầu.
- **Password input:** không log, không truyền trong URL, không hard-code trong code hoặc test deployment sản xuất.
- **Sai password:** AEAD tag verification phải thất bại, không trả plaintext chưa xác thực cho người dùng.
- **Không có recovery secret:** có thể mất dữ liệu nếu password bị quên; phải giải thích và thiết kế recovery riêng nếu yêu cầu.

### 11.3. Password-derived KEK để bọc DEK

Trong một số kiến trúc, thay vì dùng password-derived key trực tiếp mã hóa dữ liệu, ứng dụng:

1. Generate **DEK ngẫu nhiên** bằng CSPRNG.
2. Dùng password-based KDF tạo **key-encryption key** từ password và salt.
3. Dùng cơ chế **authenticated key wrapping/AEAD** được thiết kế phù hợp để bảo vệ DEK.
4. Lưu encrypted DEK, salt/KDF parameters, AEAD metadata.
5. Khi password đúng, dẫn xuất KEK để unwrap DEK rồi giải mã dữ liệu.

Thiết kế này hỗ trợ **thay password / rewrap DEK** mà không nhất thiết re-encrypt dữ liệu, **nếu DEK chưa lộ**. Nhưng đối thủ có encrypted DEK và metadata vẫn có thể **thử password offline**; bảo mật cuối cùng còn giới hạn bởi password và chi phí KDF.

## 12. Java JCA: minh họa PBKDF2 khi bắt buộc dùng password

Ví dụ sau chỉ minh họa **cách dẫn xuất keying material từ password** khi nhu cầu thật sự yêu cầu password. Nó không phải lựa chọn mặc định cho server-side DEK. Với hệ thống mới, cân nhắc **Argon2id/scrypt qua thư viện được đánh giá** nếu phù hợp, hoặc PBKDF2 theo chính sách tương thích/tuân thủ.

~~~java
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;
import javax.crypto.SecretKey;

public final class PasswordBasedKeyExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int SALT_LENGTH = 16;

    public record DerivedKey(SecretKey key, byte[] salt, int iterations) {}

    public static DerivedKey deriveFromPassword(
            char[] password,
            int iterations) throws Exception {
        if (password == null || password.length == 0) {
            throw new IllegalArgumentException("Password required");
        }
        if (iterations < 1) {
            throw new IllegalArgumentException("Invalid iterations");
        }

        byte[] salt = new byte[SALT_LENGTH];
        RNG.nextBytes(salt);

        PBEKeySpec spec = new PBEKeySpec(
            password, salt, iterations, 256);

        byte[] output = null;
        try {
            SecretKeyFactory factory =
                SecretKeyFactory.getInstance(
                    "PBKDF2WithHmacSHA256");
            output = factory.generateSecret(spec).getEncoded();
            return new DerivedKey(
                new SecretKeySpec(output, "AES"),
                salt,
                iterations
            );
        } finally {
            spec.clearPassword();
            if (output != null) {
                Arrays.fill(output, (byte) 0);
            }
            // Caller phải chủ động xử lý/xóa char[] password
            // trong phạm vi bộ nhớ mình có quyền kiểm soát.
        }
    }

    // Production cần thiết kế hàm derive để đọc lại salt và
    // iterations từ metadata khi decrypt, không tạo salt mới.
    // Không lấy mật khẩu giả/hard-code trong chương trình.
}
~~~

### 12.1. Những điểm cần hiểu

- \`SecretKeyFactory("PBKDF2WithHmacSHA256")\` là một **password KDF** hỗ trợ trực tiếp trong JCA; tính phù hợp còn phụ thuộc **iterations, password quality và threat model**.
- 16 byte salt được sinh bằng **SecureRandom**, không phải một chuỗi cố định hay tên người dùng.
- \`SecretKeySpec\` sao chép key material sang một đối tượng có thể giữ bí mật trong JVM; xóa mảng \`output\` chỉ là **best-effort**, không xóa mọi bản sao do provider giữ.
- Để giải mã file cũ, phải dẫn xuất lại **từ cùng password, salt, KDF algorithm và cost parameters**; tạo salt mới mỗi lần decrypt sẽ cho khóa khác.
- Demo chỉ dẫn xuất khóa, **không lưu trữ, không mã hóa, không kiểm tra tag hoặc quản lý recovery**. Production cần định dạng dữ liệu, giới hạn input/parameter để tránh DoS, chính sách lỗi và kiểm thử.
- \`iterations\` được đưa vào làm **cấu hình bắt buộc**, không coi bất kỳ số cụ thể nào là luôn an toàn ở mọi thời điểm; phải định nghĩa **min/max theo policy**, benchmark và cập nhật định kỳ.
- Mật khẩu yếu vẫn có thể bị đoán dù có PBKDF2.

### 12.2. Không dùng password-based KDF để xử lý vấn đề có thể tránh được

Nếu một service cần mã hóa hóa đơn mà không có yếu tố con người nhập password, hãy **Generate DEK bằng CSPRNG/KMS**, không bắt người quản trị nhập “master password” rồi dùng PBKDF2 chỉ để có key. Cách thêm password không cần thiết làm tăng điểm lỗi và nguy cơ mất dữ liệu khi người biết password rời tổ chức.

## 13. HKDF, domain separation và ranh giới sử dụng

**HKDF** thích hợp khi có **input key material đủ mạnh**, ví dụ shared secret được thiết lập qua giao thức (EC)DHE đã xác thực, hoặc một key gốc ngẫu nhiên theo thiết kế.

Sơ đồ khái niệm:

\[
PRK=\mathrm{HKDF\!-\!Extract}(salt,IKM), \quad
OKM=\mathrm{HKDF\!-\!Expand}(PRK,info,L).
\]

- **IKM:** secret ban đầu có đặc tính entropy phù hợp.
- **Salt:** tham số theo key schedule, có thể công khai, không phải mật khẩu thứ hai.
- **Info:** nhãn ràng buộc mục đích, phiên bản, role, tenant và transcript khi giao thức quy định.
- **L:** số byte cần dẫn xuất.

Ví dụ phân tách theo ngữ cảnh:

~~~text
IKM: shared secret từ key agreement đã xác thực
     |
     +-- HKDF(info="app/v1:client-to-server") --> traffic key A
     |
     +-- HKDF(info="app/v1:server-to-client") --> traffic key B
     |
     +-- HKDF(info="app/v1:exporter")        --> exporter material
~~~

**Không lấy \`IKM = SHA256("company-secret")\` rồi coi HKDF đã sửa vấn đề entropy.** Một KDF xác định không biến đầu vào dễ đoán thành bí mật ngẫu nhiên mạnh khi đối thủ có thể lặp phép tính.

### 13.1. Key agreement cũng cần ngẫu nhiên và xác thực

ECDHE/X25519 giúp hai bên tạo shared secret, thường dùng trong giao thức như TLS. Nhưng:

- Private ephemeral keys phải được sinh đúng thuật toán/provider.
- Public shares và transcript cần xác thực theo giao thức để chống MITM.
- Shared secret nên qua **key schedule/KDF chuẩn** để dẫn xuất traffic keys.
- **Forward secrecy** có các giả định cụ thể về ephemeral secret/traffic key và không tự bảo vệ khi plaintext/session secret đã bị lộ.

Một khóa ký dài hạn yếu có thể cho phép đối thủ mạo danh trong các handshake mới dù phần ECDHE mạnh. Vì vậy **nguồn sinh private signing key** cũng quan trọng như nguồn sinh DEK.

## 14. Password hashing và encryption key generation là hai bài toán khác nhau

Một lỗi kiến trúc thường gặp là nhầm **lưu mật khẩu đăng nhập** với **sinh khóa mã hóa dữ liệu**.

### 14.1. Lưu mật khẩu để đăng nhập

Ứng dụng xác thực cần một **password verifier**, không cần giải mã ngược password. Phương án phổ biến là dùng password hashing/KDF được thiết kế phù hợp, lưu salt, thuật toán, tham số và verifier; lúc đăng nhập, tính lại và so sánh an toàn.

~~~text
Đăng ký:
  Password + salt ngẫu nhiên + KDF parameters
                      |
                      v
                  Password KDF
                      |
                      v
          Verifier + salt + params được lưu

Đăng nhập:
  Nhận password -> Tính lại theo metadata
       -> So sánh và áp dụng kiểm soát online
~~~

**Không dùng SHA-256(password) một lần** làm password verifier ở hệ thống mới: phép tính nhanh giúp đối thủ thử dictionary offline nếu database bị lộ.

### 14.2. Mã hóa dữ liệu bằng password

Khi người dùng cần mở một tệp offline bằng passphrase, ứng dụng cần **password-derived key**, salt, KDF parameters, AEAD và cơ chế phục hồi thích hợp. Kẻ có ciphertext/tag có thể thử password offline, nên password quality rất quan trọng.

### 14.3. Mã hóa dữ liệu backend

Khi không có nhu cầu con người nhớ mật khẩu, dùng **DEK sinh ngẫu nhiên** và KEK trong KMS/HSM thường phù hợp hơn.

| Bài toán | Mục tiêu | Vật liệu cần quản lý |
|---|---|---|
| Login password | Kiểm tra password, không khôi phục plaintext | Password verifier + salt + KDF params |
| Password-protected file | Dùng password mở dữ liệu | Password-derived KEK hoặc encryption key + AEAD |
| Server-side storage | Mã hóa độc lập password con người | Random DEK + encrypted DEK + KMS KEK |
| Digital signature | Ký bằng private key an toàn | Key pair + key usage + certificate/trust |
| Key agreement | Tạo shared secret theo giao thức | Secure ephemeral key pairs + transcript + KDF |

## 15. Cặp khóa bất đối xứng cũng không được sinh từ từ khóa

Không thể lấy một digest của một cụm từ rồi tùy ý coi đó là private key **RSA, ECDSA, Ed25519 hoặc X25519** vừa hợp lệ vừa an toàn.

### 15.1. ECDSA

Với một elliptic curve phù hợp, private scalar phải thỏa quy tắc của nhóm:

\[
1 \leq d < n,
\]

trong đó n là bậc nhóm liên quan. Public key thường được mô tả là \(Q=dG\).

Nếu d được suy từ dictionary, đối thủ có thể tạo public key cho từng ứng viên private scalar rồi so với public key đã công bố. Đây có thể là **tấn công offline không cần ciphertext**.

ECDSA còn yêu cầu nonce bí mật **k cho từng chữ ký** được tạo/dẫn xuất đúng. Lặp hoặc lộ k có thể tiết lộ private key ngay cả khi private key ban đầu được sinh mạnh.

### 15.2. RSA

RSA key pair cần quy trình tạo tham số/số nguyên tố và các kiểm tra theo thuật toán. Không tự ghép hai số ngẫu nhiên bất kỳ, và không seed generator bằng timestamp hay một từ khóa đoán được.

### 15.3. Ed25519 và X25519

Ed25519 dùng cho chữ ký, X25519 cho key agreement. Chúng có cách xử lý key và purpose khác nhau. Một seed 32 byte **không có nghĩa** nó khó đoán nếu thực chất được tính từ SHA-256 của từ khóa phổ biến.

**Không dùng lại cùng một seed/private key cho nhiều mục đích** ngoài một giao thức đã được thiết kế/đánh giá riêng. Nên tách Sign, KeyAgreement và Encrypt theo key usage.

### 15.4. Ví dụ Java tạo ECDSA key pair đúng API

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;

public final class RandomEcKeyExample {
    public static KeyPair generateP256() throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance("EC");
        gen.initialize(
            new ECGenParameterSpec("secp256r1"),
            new SecureRandom());
        return gen.generateKeyPair();
    }
}
~~~

Ví dụ minh họa key generation, **không thay** việc bảo vệ private key trong KMS/HSM, phân phối public trust, IAM, nonce của thuật toán ký và audit.

## 16. Chính sách sinh khóa và vai trò KMS/HSM

Chính sách nên được định nghĩa trước khi workload sinh/import khóa.

| Thuộc tính | Câu hỏi |
|---|---|
| Allowed algorithms | AES, HMAC, RSA, ECDSA, Ed25519, X25519 được phép ở đâu? |
| Security strength | Độ dài AES, RSA modulus, EC curve phù hợp? |
| Origin | Key sinh trong KMS/HSM, SecureRandom provider hay import? |
| Entropy | CSPRNG/DRBG/OS RNG và reseed policy đáng tin? |
| Export policy | Private/symmetric key có thể xuất dạng rõ không? |
| Key usage | Encrypt/Decrypt, Sign/Verify, Wrap/Unwrap hay agreement? |
| Owner/tenant | Ai chịu trách nhiệm và phạm vi dữ liệu? |
| Cryptoperiod | Bao lâu được phép tạo ciphertext/chữ ký mới? |
| Rotation | Cách sinh material mới và chuyển consumers? |
| Compromise response | Nếu key yếu, phải thay và migrate dữ liệu thế nào? |
| IAM/audit | Ai tạo, duyệt, sử dụng và kiểm tra độc lập? |

### 16.1. Khóa được sinh trong HSM

HSM có thể sinh và giữ KEK/private signing key **bên trong ranh giới phần cứng**, hỗ trợ non-exportable và phép toán theo quyền. Tuy nhiên, một principal có quyền Sign/Decrypt quá rộng vẫn có thể **lạm dụng HSM như oracle**. IAM, SoD, owner, logging và business authorization vẫn cần thiết.

### 16.2. Import key yếu không làm nó mạnh

Nếu DEK được tính từ SHA-256 của một từ khóa rồi import vào KMS, nhà cung cấp chỉ giúp bảo vệ material trong phạm vi hệ thống của họ, **không tăng entropy của DEK**. KMS wrap cũng không làm dữ liệu đang mã hóa bằng DEK đoán được trở nên bí mật.

### 16.3. Không dựng master key từ một câu “bí mật” con người nhớ

Một master keyword chung cho toàn công ty tạo **single point of compromise**, khó kiểm soát version, quyền và khôi phục. Khi hệ thống cần master/KEK, hãy generate từ nguồn đã phê duyệt và quản lý bằng KMS/HSM theo vòng đời rõ ràng.

## 17. Phân tách phạm vi khóa để giảm blast radius

Ngay cả key được sinh mạnh cũng có rủi ro lớn nếu dùng chung mọi môi trường và mục đích. Nên phân tách:

- **Môi trường:** production khác staging và development.
- **Tenant/dataset/object:** theo độ nhạy cảm, nhu cầu rotation và threat model.
- **Purpose:** AES DEK khác HMAC, KEK, signing key, agreement key.
- **Version:** khi rotate phải tạo vật liệu mới, không chỉ đổi alias.
- **Cryptoperiod:** ngừng dùng để tạo dữ liệu/chữ ký mới khi hết thời hạn.
- **Traffic direction/epoch:** subkeys theo nhãn trong giao thức bảo vệ kênh.

### 17.1. Khóa khác nhau không đồng nghĩa khó đoán

~~~text
tenant-1 -> SHA256("tenant-1")
tenant-2 -> SHA256("tenant-2")
tenant-3 -> SHA256("tenant-3")
~~~

Ba kết quả khác nhau nhưng đều có thể tính lại khi biết quy luật. **Uniqueness** và **unpredictability** là hai thuộc tính khác nhau. Tenant ID nên được đưa vào **authorization và AAD/context** khi thích hợp, không dùng làm nguồn bí mật.

## 18. Gắn GenerateKey với toàn bộ vòng đời

~~~mermaid
flowchart LR
    A["Purpose, owner, algorithm"] --> B["Generate strong key"]
    B --> C["Register key ID/version"]
    C --> D["Protect and provision via IAM"]
    D --> E["Use within purpose and nonce rules"]
    E --> F["Rotate new material + cutover"]
    F --> G["Retire / Revoke"]
    G --> H["Dependency review + Destroy"]
    I["Inventory và audit"] --> C
    I --> E
    I --> F
    I --> H
~~~

| Giai đoạn | Rủi ro liên quan key dễ đoán | Kiểm soát |
|---|---|---|
| Define | Chọn password chung vì tiện | Purpose, algorithm, origin, strength policy |
| Generate | SHA-256 của keyword, Random/seed cố định | CSPRNG/KeyGenerator/KMS/HSM |
| Provision | Key rõ nằm trong Git/image | Secret channel, non-exportable nếu phù hợp |
| Storage | Plaintext DEK nằm cùng ciphertext | Envelope encryption/KEK boundary |
| Use | Cùng key mọi tenant hoặc lặp GCM nonce | Key scope, nonce schedule, limits |
| Rotate | Chỉ đổi tên alias | New material version, migration |
| Revoke | Key yếu vẫn đoán được sau khi Disable | Đổi bí mật và public trust nếu cần |
| Destroy | Xóa KEK khi vẫn còn encrypted DEK | Dependency inventory, retention, backup evidence |

**Key registry cần** provider, owner, key ID/material version, algorithm, purpose, origin, cryptoperiod, creation time, allowed operations và trạng thái. Những thông tin này giúp tìm tất cả keys được sinh trong một đợt RNG lỗi.

## 19. Policy-as-code: hạn chế nguồn key dễ đoán

Một policy logic có thể biểu diễn như sau. Đây **không phải cấu hình native của bất kỳ cloud KMS cụ thể nào**:

~~~yaml
policyName: secure-key-generation
policyVersion: 1
generation:
  allowedOrigins:
    - APPROVED_CSPRNG
    - APPROVED_KMS
    - APPROVED_HSM
  forbidHumanSelectedKeyword: true
  forbidHashOfPredictableMetadata: true
  forbidNonCryptographicPrng: true
  forbidFixedSeedForProduction: true
  requireAlgorithmSpecificKeyGenerator: true
  requireOwnerUsageAndVersion: true
passwordBasedEncryption:
  requireApprovedPasswordKdf: true
  requireRandomPerObjectSalt: true
  requireKdfParametersAndVersion: true
  requireAuthenticatedEncryption: true
operations:
  requireLeastPrivilegeIam: true
  prohibitSecretMaterialInLogs: true
  requireAudit: true
incidentResponse:
  identifyWeakOriginKeyVersions: true
  replaceKeysFromWeakSources: true
  prohibitDestructionWithoutDependencyReview: true
~~~

**Policy-as-code chỉ hữu ích khi được thực thi** qua CI/static analysis, provisioning workflow, IAM/KMS guards, audit và kiểm thử. File YAML không tự bảo đảm keys hiện có đều mạnh.

### 19.1. Code review và kiểm soát tự động

- Cảnh báo các đường **MessageDigest(password/tenantId) → SecretKeySpec**.
- Phát hiện Random/ThreadLocalRandom/Math.random dùng sinh secret.
- Kiểm tra hard-coded key bytes, deterministic seeds, secret trong Git/image.
- Yêu cầu key origin/provenance cho thao tác ImportKey.
- Cấm cấp Delete/ChangePolicy tùy tiện cho dịch vụ chỉ Encrypt/Decrypt.
- Kiểm tra owner, usage, version và trạng thái trước Activate.

**Không coi mọi lời gọi SHA-256 là lỗi.** SHA-256 được dùng hợp lệ trong chữ ký, hash, HKDF/HMAC, transcript và kiểm tra toàn vẹn; cần xem **nguồn dữ liệu và vai trò kết quả**.

## 20. Audit và key inventory để phát hiện nguồn sinh yếu

| Nhóm metadata | Ví dụ trường | Ý nghĩa |
|---|---|---|
| Identity | provider, account, region, key ID/version | Định danh đúng material |
| Origin | generated/imported, provider/keygen path | Phân biệt nguồn |
| Parameters | algorithm, size/curve, purpose | Xác minh policy |
| Accountability | owner, requester, approver, service | Trách nhiệm |
| Lifecycle | created, activated, rotation due, state | Tìm thời kỳ ảnh hưởng |
| Dependencies | encrypted DEK, dataset, certificate refs | Thực hiện migration |
| IAM | principals, grants, policy changes | Đánh giá lạm dụng |
| Audit events | Generate/Import, Encrypt/Sign/Unwrap | Khoanh vùng sự cố |
| Exceptions | source attestation, risk approval | Theo dõi rủi ro tồn dư |

**Không lưu plaintext DEK/KEK, private key, HMAC secret, seed/CSPRNG state, password hoặc bearer token vào audit.**

Một số key generator yếu vẫn có thể tạo 1.000 keys khác nhau; **không tìm thấy collision không chứng minh entropy đủ**. Cần đánh giá provider, nguồn entropy, môi trường khởi tạo, provenance và các cơ chế kiểm thử phù hợp.

## 21. Ứng phó khi phát hiện khóa đang dùng được sinh từ từ khóa dễ đoán

Một cuộc kiểm toán phát hiện **DEK production** được tạo từ SHA-256 của một câu chung do nhóm tự chọn. Dù hệ thống đã mã hóa hàng triệu bản ghi, tính bí mật của DEK **không còn được đánh giá dựa trên 256 bit ngẫu nhiên**, mà bị giới hạn bởi không gian các cụm từ đoán được.

**Không chỉ thay dòng code bằng SecureRandom rồi đóng sự cố**. Ciphertext, chữ ký, encrypted DEK hoặc backup cũ vẫn có thể phụ thuộc vật liệu yếu.

### 21.1. Runbook có kiểm soát

~~~mermaid
flowchart TD
    A["Phát hiện predictable key generation"] --> B["Khoanh vùng nguồn, phiên bản, thời kỳ"]
    B --> C["Ngừng tạo mới và ngừng dùng key yếu cho Encrypt/Sign"]
    C --> D["Inventory dữ liệu, backup, key references, consumers"]
    D --> E["Generate key mới bằng nguồn đã phê duyệt"]
    E --> F["Cutover writers/signers/consumers"]
    F --> G{"Key type?"}
    G -->|DEK| H["Re-encrypt dữ liệu chịu ảnh hưởng"]
    G -->|KEK| I["Rewrap DEK và đánh giá DEK có thể lộ"]
    G -->|Signing/HMAC| J["Thay key và cập nhật trust/consumers"]
    H --> K["Verify integrity, restore, IAM"]
    I --> K
    J --> K
    K --> L["Retire/revoke cũ; incident audit"]
~~~

Quy trình thực hành:

1. **Định danh** công thức cũ, nguồn từ khóa, version ứng dụng và key ID/material version.
2. **Xác định phạm vi** production/staging, tenant, dữ liệu, ký số, API MAC và giai đoạn triển khai.
3. **Đánh giá khả năng đoán** khi đối thủ có ciphertext/tag, public key hoặc các vật kiểm tra khác.
4. **Containment:** chặn hoạt động tạo dữ liệu/chữ ký mới bằng key yếu, giới hạn IAM khi cần; không vội destroy trước khi có đường phục hồi.
5. **Generate replacement:** dùng CSPRNG/KMS/HSM và algorithm phù hợp; tạo **vật liệu mới thực sự**, không chỉ đổi alias.
6. **Migration:** theo đúng loại khóa:
   - **DEK yếu:** cần xem xét **re-encrypt dữ liệu** bằng DEK mới.
   - **KEK yếu:** rewrap encrypted DEK và xác định liệu plaintext DEK có thể đã bị suy ra/lộ để quyết định re-encrypt.
   - **HMAC/PSK yếu:** thay secret, cập nhật mọi bên chấp nhận MAC và replay controls.
   - **Private signing key yếu:** phát hành key pair mới, phân phối public trust/JWKS/certificate, xử lý chữ ký/token lịch sử.
7. **Verification:** kiểm thử decrypt/verify, backup restore, key version mapping, IAM, AAD/nonce, consumers và audit.
8. **Lifecycle:** retire/revoke theo incident; chỉ destroy vật liệu cũ sau khi kiểm tra dependencies, retention và bằng chứng provider.
9. **Post-incident review:** xác định dữ liệu có thể đã bị giải mã, trách nhiệm thông báo, sửa code path và thêm CI/policy guard.

### 21.2. Thay khóa hôm nay không làm dữ liệu đã lộ trở lại bí mật

Nếu đối thủ đã suy ra key yếu và thu thập ciphertext, họ có thể đã giải mã dữ liệu trước khi migration. **Re-encrypt** bảo vệ dữ liệu mới hoặc những bản sao chưa bị lấy, nhưng không xóa thông tin đối thủ đã biết.

Nếu private signing key yếu đã bị suy ra, đối thủ có thể ký **ngoài KMS/HSM**, nên DisableKey tại một provider không đủ; phải cập nhật mọi verifier và nguồn trust.

### 21.3. Đừng mất dữ liệu khi hủy key cũ

Encrypted DEK và ciphertext có thể tồn tại trong backup, archive hoặc DR. Không xóa KEK/DEK trước khi kiểm kê, kiểm thử restore và xác định retention. Phải phân biệt **ScheduleDelete** với **DESTROYED thực tế**.

## 22. Case study: dùng tenantId để tạo khóa AES trong nền tảng Java

Một nền tảng nhiều tenant từng triển khai:

~~~text
tenantId = "shop-42"
DEK = SHA256(UTF8(tenantId))
AES-GCM encrypt tài liệu thuộc tenant đó
~~~

Nhóm phát triển tưởng rằng **mỗi tenant một key khác nhau** là đủ để cô lập dữ liệu. Thực tế tenant ID có thể xuất hiện ở URL, logs hoặc API responses, khiến DEK có thể được **tính trực tiếp**.

### 22.1. Những lỗi độc lập

| Vấn đề | Tác động |
|---|---|
| DEK suy từ tenantId | Key có thể đoán hoặc tính lại |
| Không có key ID/version | Rotation và đọc dữ liệu lịch sử khó |
| Không quản lý encrypted DEK/KEK | Thiếu miền bảo vệ vật liệu khóa |
| Cùng DEK lâu dài | Rủi ro tăng khi usage/nonce không được kiểm soát |
| Multiwriter với nonce không phối hợp | Có thể trùng nonce AES-GCM |
| Service có quyền mọi tenant | Credential compromise gây blast radius lớn |
| Không có owner và audit | Không ai chịu trách nhiệm lifecycle |

### 22.2. Kiến trúc thay thế

~~~mermaid
flowchart TD
    R["Yêu cầu đã xác thực"] --> A["Authorization: tenant, object, purpose"]
    A --> K["KMS: GenerateDataKey dưới KEK phù hợp"]
    K --> D["DEK ngẫu nhiên"]
    D --> E["AES-GCM với nonce không trùng"]
    X["Plaintext tài liệu"] --> E
    E --> C["Ciphertext + tag + nonce"]
    K --> W["Encrypted DEK + KEK reference/version"]
    C --> S["Storage: dữ liệu theo tenant"]
    W --> S
    A --> L["Audit: tenant, owner, key version"]
    K --> L
~~~

Thiết kế mới:

- **tenantId chỉ là metadata để phân quyền**, không phải bí mật.
- **DEK được sinh an toàn**, độc lập với tên tenant.
- **KEK trong KMS/HSM** bảo vệ DEK theo quyền, không cần xuất KEK rõ.
- **Key ID/version** cho phép đọc dữ liệu lịch sử và rotation.
- **AAD** có thể ràng buộc tenant/object/version vào xác thực theo giao thức dữ liệu, nhưng vẫn cần business authorization.
- **Nonce uniqueness** phải được bảo đảm dưới mỗi DEK, kể cả retry, restart và multiwriter.

### 22.3. Migration dữ liệu

1. Thống kê bản ghi được mã hóa bằng công thức cũ và xác định data format/version.
2. Chặn mọi Encrypt mới bằng DEK suy từ tenantId.
3. Sinh DEK mới theo phạm vi được xác định (object/dataset/tenant).
4. Decrypt bản ghi cũ trong một workflow có kiểm soát, kiểm tra AEAD tag và AAD.
5. Re-encrypt dữ liệu dưới DEK mới, với nonce và metadata mới.
6. Kiểm chứng integrity, khả năng đọc, backup restore và trạng thái job retry.
7. Audit và điều tra khả năng dữ liệu cũ đã bị đối thủ giải mã.
8. Ngăn tái xuất hiện công thức cũ bằng CI/static checks và review key provenance.

**Thay tenantId bằng một tên dài hơn không giải quyết vấn đề.** Secret cần được sinh theo cơ chế mật mã, không suy ra từ định danh công khai.

## 23. Case study: file offline được bảo vệ bằng passphrase

Một ứng dụng desktop cần mã hóa tài liệu để người dùng mở lại bằng passphrase ngay cả khi không có mạng hoặc KMS. Đây là tình huống **password-based encryption có thể hợp lý**, nhưng có giới hạn cố hữu.

Thiết kế tham khảo:

1. Nhận password qua giao diện phù hợp; không log hoặc đưa password vào URL.
2. Sinh một **DEK ngẫu nhiên** cho file.
3. Sinh **salt riêng**; dẫn xuất key-wrapping key từ password bằng Argon2id/scrypt/PBKDF2 theo chính sách.
4. Bọc DEK bằng authenticated key wrapping/AEAD đã được thiết kế đúng, với nonce/format thích hợp.
5. Mã hóa file bằng AEAD dùng DEK; quản lý AAD, tag và nonce.
6. Lưu encrypted DEK, salt, KDF algorithm/cost/version, nonce, tag, ciphertext.
7. Khi mở file, giới hạn tham số không tin cậy để tránh DoS, dẫn xuất KEK từ password rồi unwrap DEK.
8. Sai password hoặc sai authentication tag phải **từ chối plaintext**.
9. Thiết kế backup/recovery nếu cần; nếu password và recovery path đều mất, có thể mất dữ liệu.
10. Khi đổi password, có thể **rewrap DEK** mà không re-encrypt nếu DEK chưa lộ. Nếu password-derived KEK/DEK cũ đã bị lộ, phải đánh giá lại phạm vi.

**Điểm then chốt:** đối thủ có file mã hóa vẫn có thể thử password offline. KDF cost giúp tăng chi phí, nhưng không biến mật khẩu phổ biến thành bí mật 256 bit. Nếu phù hợp UX, nên hỗ trợ passphrase được sinh ngẫu nhiên và khuyến khích người dùng không dùng lại password.

## 24. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| SHA-256 của từ “secret” làm AES key | Hash dài không tăng entropy | KeyGenerator/CSPRNG/KMS |
| SHA-256(password) rồi AES-GCM | Dễ dictionary offline | Password-based KDF khi thực sự cần password |
| Hash nhiều vòng một keyword | Vẫn cùng tập ứng viên nhỏ | Không chọn keyword làm nguồn secret |
| Base64 tên app thành key | Encoding không tạo randomness | Generate key đúng thuật toán |
| Random.nextBytes cho secret | Không phải CSPRNG | SecureRandom/KeyGenerator |
| Seed từ timestamp/hằng số | Có thể suy đoán, tái tạo | Provider/OS entropy, không tự seed yếu |
| Chung key production và staging | Lộ ở môi trường thấp ảnh hưởng production | Tách key material theo môi trường |
| Dùng tenantId làm DEK | ID thường có thể quan sát | Dùng ID cho IAM/AAD, không làm secret |
| Dùng UUID tùy ý thay key generator | Format UUID không cam kết key strength/format | Dùng API key generation chuẩn |
| Nonce AES-GCM cố định | Trùng (key, nonce) phá AEAD | Nonce schedule theo key |
| Plaintext DEK nằm cạnh ciphertext | Dữ liệu và key lộ cùng lúc | Envelope encryption |
| Import key yếu vào HSM và coi mạnh | Không tăng entropy của material | Generate key mới từ nguồn tin cậy |
| Rewrap một DEK đã lộ rồi tuyên bố an toàn | Đối thủ vẫn giữ/suy ra DEK | Thay DEK, đánh giá re-encrypt |
| Chỉ đổi alias khi rotate | Vật liệu cũ có thể không đổi | Generate material version mới |
| Chỉ Disable signing key yếu | Đối thủ có thể ký ngoài HSM | Revoke trust, update verifier |
| Dùng một key cho AES và HMAC | Trộn purpose, rủi ro phân phối | Key separation |
| Log SecretKey.getEncoded() | Lộ plaintext key material | Chỉ log metadata và references |
| Không lưu salt/KDF params | Không thể derive lại để giải mã | Lưu version, salt, parameters |
| Cho rằng KDF chữa được mật khẩu phổ biến | KDF chỉ tăng cost mỗi lần đoán | Password quality và threat model |
| Thay code nhưng không migrate dữ liệu | Ciphertext cũ vẫn dưới key yếu | Re-encrypt/rewrap và restore |
| Xóa KEK ngay khi phát hiện lỗi | Mất DEK/backup phụ thuộc | Containment và dependency review |

## 25. Kiểm thử chất lượng key generation và chính sách

| Tình huống | Kỳ vọng |
|---|---|
| Generate AES-256 bằng KeyGenerator chuẩn | Key đúng thuật toán/độ dài, usable theo policy |
| Tạo key từ từ khóa công khai | Static/policy review cảnh báo, từ chối production |
| Hash password một lần thành AES key | Static/policy review phát hiện |
| Seed cố định trong Random | Bị chặn hoặc cảnh báo |
| SecureRandom/KMS không sẵn sàng | Fail-safe, không dùng fallback yếu |
| ImportKey không có provenance | Đánh giá và phê duyệt hoặc từ chối |
| ExportKey từ key non-exportable | Provider/IAM từ chối |
| Encryptor gọi ChangeKeyPolicy/DeleteKey | Bị chặn và audit |
| Staging principal gọi production KEK | Bị từ chối theo scope |
| DEK sinh từ tenantId | Review phát hiện nguồn dự đoán được |
| AES-GCM nonce trùng dưới cùng DEK | Không cho tái sử dụng theo thiết kế |
| Sửa AAD hoặc tag bản mã | Decrypt thất bại; không xuất plaintext |
| Password-based KEK với salt riêng | Metadata đủ để derive lại |
| Dùng salt mới khi mở file cũ | Thử nghiệm chứng minh lỗi thiết kế |
| Password yếu có ciphertext/tag | Threat model ghi rõ nguy cơ dictionary offline |
| KDF parameters từ file không tin cậy quá lớn | Bị giới hạn để tránh resource exhaustion |
| Signing key sinh đúng KeyPairGenerator | Sign/Verify hợp lệ, public key có trust binding |
| Phát hiện signing key yếu | Có key rotation và verifier migration |
| KEK rotate thông thường, DEK chưa lộ | Rewrap và kiểm thử restore |
| DEK bị compromise nhưng chỉ rewrap | Workflow cảnh báo chưa xử lý lộ DEK |
| KEK còn encrypted DEK phụ thuộc | Destruction guard từ chối |
| Audit GenerateKey | Có actor, origin, key ID/version, không có material |
| VM snapshot/restore | Đánh giá RNG/nonce states sau phục hồi |
| Dữ liệu sau migration | Bản mã mới kiểm chứng được, backup restore |
| 1.000 keys không trùng | **Không kết luận** đã chứng minh entropy mạnh |

**Functional correctness không chứng minh key khó đoán.** Round-trip AES-GCM PASS chỉ cho biết encrypt/decrypt dùng key và metadata nhất quán.

## 26. Câu hỏi tự kiểm tra

**Câu 1. Vì sao SHA-256 của một từ khóa ngắn không tạo AES-256 key mạnh?**

**Trả lời:** Vì không gian ứng viên vẫn bị giới hạn bởi từ khóa dễ đoán. Độ dài 256 bit của digest không tự tăng entropy.

**Câu 2. Nếu chọn đều một trong 10.000 từ, entropy tối đa khoảng bao nhiêu?**

**Trả lời:** \(\log_2(10000)\approx13{,}3\) bit, thấp xa một khóa ngẫu nhiên AES-128/256.

**Câu 3. Một mật khẩu tự nghĩ dài 32 ký tự có chắc mạnh hơn 16 byte CSPRNG không?**

**Trả lời:** Không chắc. Một câu dài nhưng phổ biến hoặc có cấu trúc vẫn có thể dễ đoán; số ký tự không chứng minh entropy.

**Câu 4. Salt ngẫu nhiên làm password yếu thành bí mật 256 bit không?**

**Trả lời:** Không. Salt giúp phân tách kết quả và chống tính toán chung, không thêm entropy bí mật vào password.

**Câu 5. Password-based KDF nhằm giải quyết điều gì?**

**Trả lời:** Tăng chi phí thử đoán và dẫn xuất key theo password, salt/params phù hợp khi bắt buộc dùng mật khẩu; không thay thế CSPRNG.

**Câu 6. HKDF có phải công cụ chống dictionary cho password yếu không?**

**Trả lời:** Không. HKDF được dùng khi input key material có entropy thích hợp, không thiết kế để làm password-hardening KDF.

**Câu 7. Có thể dùng java.util.Random tạo AES key không?**

**Trả lời:** Không nên. Dùng SecureRandom/KeyGenerator hoặc KMS/HSM phù hợp.

**Câu 8. UUIDv4 có thay KeyGenerator cho mọi thuật toán không?**

**Trả lời:** Không. UUID không phải API tạo khóa theo thuật toán, key usage và security strength cụ thể.

**Câu 9. HSM có làm key yếu đã import trở thành mạnh không?**

**Trả lời:** Không. HSM bảo vệ việc lưu và sử dụng material trong miền tin cậy, không tăng entropy quá khứ của key.

**Câu 10. Khi DEK yếu bị lộ, đổi KEK bọc nó có đủ không?**

**Trả lời:** Không. Đối thủ vẫn có thể suy hoặc giữ DEK; thường phải đánh giá thay DEK và re-encrypt.

**Câu 11. Private ECDSA key suy từ từ khóa có thể bị tấn công khi public key đã biết không?**

**Trả lời:** Có. Đối thủ thử các private scalar ứng viên và so sánh public key tương ứng.

**Câu 12. Key khác nhau cho từng tenant có chứng minh key khó đoán không?**

**Trả lời:** Không. Key suy từ những tenantId khác nhau vẫn có thể tính trực tiếp.

**Câu 13. Nếu sinh DEK mới, có thể dùng một nonce GCM đã dùng ở key cũ không?**

**Trả lời:** Nonce cần duy nhất **dưới mỗi key**; với key độc lập mới, nonce space được quản lý theo key mới, nhưng không được reuse dưới cùng key, kể cả restart/multiwriter.

**Câu 14. Mã hóa file offline bằng password nên làm gì?**

**Trả lời:** Dùng password-based KDF theo policy, salt/params/version, authenticated encryption và hiểu giới hạn offline dictionary.

**Câu 15. Vì sao sửa code GenerateKey chưa đủ khi đã có nhiều dữ liệu dưới key yếu?**

**Trả lời:** Ciphertext/chữ ký/backup cũ vẫn phụ thuộc material yếu. Cần inventory, migration, trust update, kiểm thử restore và điều tra dữ liệu có thể bị lộ.

## 27. Checklist triển khai và ghi nhớ

Trước khi đưa cơ chế tạo khóa vào production:

- **Purpose:** xác định key dùng Encrypt/Decrypt, HMAC, Sign/Verify, Wrap/Unwrap hay KeyAgreement?
- **Algorithm:** chọn AES size, RSA modulus, EC curve và provider theo policy?
- **Randomness:** dùng CSPRNG/DRBG/OS RNG hoặc KMS/HSM; không dùng keyword, timestamp, Random hay fixed seed?
- **Entropy:** hiểu độ dài digest khác entropy nguồn; không nhầm encoding/hash với bí mật mới?
- **Human input:** nghiệp vụ có thật sự yêu cầu một password con người nhớ không? Nếu không, tạo DEK ngẫu nhiên.
- **Password derivation:** nếu bắt buộc, dùng KDF phù hợp, salt riêng, cost policy, AEAD và metadata version?
- **HKDF:** chỉ dùng theo key schedule với secret phù hợp, không thay password KDF?
- **Key purpose:** tách DEK, KEK, HMAC, signing và agreement keys?
- **Scope:** phân tách environment, tenant, data domain và material versions?
- **KMS/HSM:** origin, exportability, IAM/grants, audit, APIs và provider behavior được xác minh?
- **Envelope encryption:** DEK ngẫu nhiên, KEK được bảo vệ, encrypted DEK và key reference được lưu đúng?
- **AES-GCM:** nonce uniqueness, tag, AAD và giới hạn sử dụng từng DEK có được quản lý?
- **Asymmetric keys:** dùng KeyPairGenerator chuẩn, private key bí mật, public key có trust binding?
- **Lifecycle:** owner, key ID/version, cryptoperiod, rotation, revocation, backup và destruction?
- **Audit:** không ghi key bytes/seed/password; vẫn có đủ metadata điều tra?
- **CI guard:** phát hiện SHA256(keyword), Random cho secrets, hard-coded material và import không rõ nguồn?
- **Incident response:** có thể tìm ciphertext, encrypted DEK, backups, signatures và consumers bị ảnh hưởng khi generator lỗi?
- **Migration:** biết khi nào rewrap KEK, khi nào thay DEK/re-encrypt, khi nào revoke signing trust?
- **Verification:** test negative IAM, nonce, KDF metadata, provider failure, restore và stale consumer?
- **Destruction:** không hủy vật liệu còn phụ thuộc và có evidence provider khi hủy hoàn tất?

**Ghi nhớ:** **Không sinh key từ từ khóa dễ đoán** là nguyên tắc bảo vệ gốc rễ của mật mã ứng dụng. **Hash, Base64, salt hoặc tên gọi “AES-256 key” không tự sinh entropy bí mật**. Khi cần key mới, sử dụng **CSPRNG/KeyGenerator hoặc KMS/HSM** theo thuật toán và phạm vi; chỉ dùng **password-based KDF** khi hệ thống thật sự phụ thuộc password và phải thừa nhận rủi ro đoán offline. Kết hợp **key inventory, DEK/KEK, envelope encryption, IAM, audit, rotation, revocation và quy trình ứng phó** để bảo vệ khóa an toàn suốt vòng đời từ tạo đến hủy.
