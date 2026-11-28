# Secret key

> **Chương:** Thuật ngữ cốt lõi  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Secret key là gì?

**Secret key (khóa bí mật)** là một giá trị mật mã mà các bên được ủy quyền phải giữ kín để thực hiện một hoặc nhiều thao tác mật mã. Trong ngữ cảnh **mật mã đối xứng (symmetric cryptography)**, secret key thường chính là **khóa đối xứng**: bên mã hóa và bên giải mã sử dụng cùng một khóa hoặc các khóa tương đương được dẫn xuất theo quy tắc xác định.

Ví dụ: ứng dụng dùng một secret key AES để mã hóa số tài khoản trước khi lưu xuống cơ sở dữ liệu. Khi cần đọc, ứng dụng phải có quyền sử dụng khóa phù hợp để giải mã. Dù cơ sở dữ liệu chứa toàn bộ bản mã, người không có khóa vẫn không thể giải mã một cách khả thi nếu thuật toán, chế độ hoạt động và cách triển khai đều an toàn.

Không nên hiểu secret key đơn thuần là một chuỗi cấu hình phải giấu. Đó là **vật liệu mật mã có mục đích sử dụng, độ dài, phạm vi truy cập, phiên bản và vòng đời**. Việc một thuật toán mạnh có bảo vệ được dữ liệu hay không phụ thuộc đáng kể vào cách tạo, lưu trữ, cấp quyền, sử dụng, xoay vòng và hủy secret key.

### Ba điều cần nhớ

1. **Tính bí mật:** Ai có secret key và đủ dữ liệu liên quan có thể thực hiện những thao tác được thiết kế cho khóa đó; vì vậy phải giới hạn người và hệ thống được sử dụng.
2. **Tính đúng mục đích:** Một khóa mã hóa dữ liệu không nên tùy tiện dùng làm khóa HMAC, khóa bọc khóa hoặc dùng lại giữa các môi trường.
3. **Tính quản trị:** Phải biết khóa do ai quản lý, thuộc phiên bản nào, bảo vệ dữ liệu gì, khi nào hết hiệu lực và hậu quả nếu bị lộ hoặc bị mất.

## 2. Phân biệt secret key với những khái niệm gần nhau

Thuật ngữ **secret key** đôi khi được dùng theo nghĩa rộng là bất kỳ khóa nào phải giữ bí mật. Tuy nhiên, khi thảo luận về mô hình **đối xứng so với bất đối xứng**, nên gọi rõ tên để tránh nhầm lẫn:

| Khái niệm | Bản chất | Ai cần biết hoặc có quyền sử dụng? | Ví dụ |
| --- | --- | --- | --- |
| **Secret key / symmetric key** | Một khóa bí mật dùng cho thuật toán đối xứng | Các bên có quyền mã hóa/giải mã hoặc tạo/kiểm tra MAC theo thiết kế | Khóa AES-256, khóa HMAC |
| **Private key** | Thành phần bí mật của cặp khóa bất đối xứng | Chủ thể sở hữu khóa hoặc dịch vụ ký/giải mã được ủy quyền | Khóa riêng RSA, Ed25519 |
| **Public key** | Thành phần công khai của cặp khóa bất đối xứng | Có thể phân phối công khai, nhưng phải xác thực đúng chủ sở hữu khi cần | Khóa công khai để xác minh chữ ký |
| **Password** | Bí mật do người dùng đặt hoặc cung cấp | Người dùng; hệ thống xác thực nên lưu bản băm mật khẩu chuyên dụng | Mật khẩu đăng nhập |
| **API key / access token** | Thông tin xác thực hoặc ủy quyền cho API | Client được cấp và dịch vụ xác minh | Token gọi dịch vụ |
| **DEK** | Secret key dùng để mã hóa dữ liệu trực tiếp | Dịch vụ mã hóa/giải mã được phép | Khóa AES cho bản ghi khách hàng |
| **KEK** | Khóa dùng để bọc hoặc bảo vệ khóa khác | KMS/HSM hoặc thành phần có quyền dùng KEK | Khóa cấp cao trong KMS |

**Private key cũng là khóa cần giữ bí mật**, nhưng thuật ngữ này thường chỉ thành phần của hệ bất đối xứng. Với AES hoặc HMAC, hãy dùng tên **secret key/khóa đối xứng**; với RSA hoặc Ed25519, hãy nói **private key và public key**.

**Secret key khác password:** password của con người thường có entropy thấp, khó phù hợp để dùng trực tiếp làm khóa AES. Khi buộc phải dẫn xuất khóa từ mật khẩu, cần dùng cơ chế dẫn xuất khóa từ mật khẩu thích hợp với salt và tham số chi phí được lựa chọn cẩn thận, như Argon2id hoặc scrypt theo thiết kế hệ thống. Việc lấy trực tiếp byte của mật khẩu để làm khóa không an toàn.

**Secret key khác API key:** API key thông thường dùng nhận diện hoặc cấp quyền gọi API; nó không nhất thiết là vật liệu để AES, HMAC hay thuật toán mật mã khác thực hiện phép toán. Dù vậy, API key vẫn là bí mật cần được quản lý.

## 3. Secret key được sử dụng để làm gì?

### 3.1. Mã hóa và giải mã dữ liệu

Với thuật toán mã hóa đối xứng như AES hoặc ChaCha20, ứng dụng sử dụng một khóa bí mật để biến dữ liệu rõ thành bản mã và khôi phục dữ liệu khi có quyền.

Nên ưu tiên **mã hóa có xác thực (Authenticated Encryption with Associated Data — AEAD)**, chẳng hạn **AES-GCM** hoặc **ChaCha20-Poly1305**, để bảo vệ đồng thời tính bí mật và phát hiện sửa đổi trái phép bản mã.

~~~text
Mã hóa:
  (ciphertext, tag) = Encrypt(secretKey, nonce, plaintext, AAD)

Giải mã:
  plaintext = Decrypt(secretKey, nonce, ciphertext, tag, AAD)
  Nếu khóa/nonce/AAD/tag/bản mã không khớp: từ chối giải mã.
~~~

Ở đây:

- **Secret key:** phải được giữ bí mật, chỉ cấp cho thao tác được phép.
- **Nonce/IV:** thường không cần giữ bí mật, nhưng phải tuân thủ quy tắc duy nhất của thuật toán và chế độ; đặc biệt **không tái sử dụng cùng nonce với cùng khóa trong AES-GCM**.
- **AAD:** dữ liệu không cần mã hóa nhưng được xác thực cùng bản mã, chẳng hạn mã tenant và ID bản ghi.
- **Authentication tag:** thông tin xác thực để phát hiện dữ liệu hoặc ngữ cảnh bị thay đổi.

Với cùng một secret key, việc tái sử dụng nonce trong AES-GCM có thể phá vỡ các bảo đảm bảo mật. **Bí mật của khóa không bù đắp được lỗi sử dụng nonce.** Một nonce ngẫu nhiên 96 bit là lựa chọn thường gặp, nhưng vẫn cần kiểm soát nguy cơ trùng lặp và giới hạn số lần mã hóa theo từng khóa; với lưu lượng lớn có thể cần cách cấp nonce bảo đảm không trùng.

### 3.2. Tạo và xác minh mã xác thực thông điệp (MAC)

**HMAC** dùng secret key và hàm băm mật mã để tạo **Message Authentication Code (MAC)**. Bên kiểm tra cũng cần có secret key tương ứng.

~~~text
tag = HMAC(secretKey, message)
valid = VerifyMAC(secretKey, message, tag)
~~~

HMAC giúp kiểm tra **tính toàn vẹn và tính xác thực của thông điệp trong phạm vi các bên cùng chia sẻ khóa**. HMAC **không mã hóa** nội dung; thông điệp vẫn có thể đọc được. HMAC cũng **không tạo tính không thể chối bỏ như chữ ký số bất đối xứng**, vì bất kỳ bên nào biết secret key chung đều có thể tạo MAC hợp lệ.

Ví dụ: hai dịch vụ nội bộ dùng khóa HMAC riêng để xác minh nội dung webhook. Bên nhận phải xác minh MAC bằng cách so sánh an toàn với tấn công thời gian và kiểm tra thêm timestamp, nonce hoặc ID sự kiện để hạn chế phát lại. Không nên dùng cùng secret key này làm khóa AES mã hóa dữ liệu.

### 3.3. Dẫn xuất khóa và bọc khóa

Một khóa gốc có entropy cao có thể được dùng với **Key Derivation Function (KDF)** như HKDF để tạo các khóa con **khác nhau cho từng mục đích**. Ví dụ:

~~~text
rootSecret --HKDF(context="encryption")--> encryptionKey
           --HKDF(context="authentication")--> macKey
~~~

Trong đó, ngữ cảnh dẫn xuất phải được thiết kế để tách biệt mục đích và phù hợp giao thức. **HKDF không biến một password yếu thành khóa mạnh hơn entropy đầu vào**; việc dẫn xuất từ mật khẩu phải dùng KDF chuyên dành cho mật khẩu.

Một **KEK (Key Encryption Key)** là khóa dùng để bọc hoặc bảo vệ **DEK (Data Encryption Key)**. Cả DEK lẫn KEK đều có thể là secret key đối xứng, nhưng vai trò quản lý và mức độ nhạy cảm của chúng khác nhau.

## 4. Những tính chất quyết định độ an toàn của secret key

| Tính chất | Ý nghĩa | Ví dụ quyết định thiết kế |
| --- | --- | --- |
| **Độ ngẫu nhiên / entropy** | Khóa khó đoán, khó vét cạn | Tạo bằng CSPRNG hoặc KMS thay vì từ timestamp |
| **Độ dài khóa** | Quy mô không gian khóa, phù hợp thuật toán | AES cho phép khóa 128, 192 hoặc 256 bit |
| **Mục đích sử dụng** | Tránh việc dùng một khóa cho nhiều cơ chế | Tách khóa AES và HMAC |
| **Phạm vi ảnh hưởng** | Dữ liệu nào bị tác động khi khóa lộ | Tách khóa theo môi trường, dịch vụ hoặc tenant khi cần |
| **Quyền sử dụng** | Ai được mã hóa, giải mã, bọc/mở bọc | IAM/KMS policy theo nguyên tắc ít quyền nhất |
| **Vòng đời và phiên bản** | Khi nào tạo, kích hoạt, thay, ngừng và hủy | Gắn key ID/version với bản mã |
| **Khả năng phục hồi** | Khả năng đọc lại dữ liệu còn thời hạn lưu giữ | Backup/khôi phục khóa có kiểm soát |

**Độ dài khóa không phải là toàn bộ câu chuyện:** AES-256 với khóa sinh từ chuỗi đoán được hoặc khóa bị lộ trong log có thể kém an toàn hơn AES-128 với khóa sinh và quản lý đúng cách. Với lựa chọn thuật toán cụ thể, cần dựa vào yêu cầu bảo mật, tiêu chuẩn áp dụng, ràng buộc hiệu năng và chính sách hiện hành.

**Khóa dài cũng không tự bảo đảm tính toàn vẹn.** Chẳng hạn, thuật toán AES là một mật mã khối; chọn chế độ hoạt động sai có thể không cung cấp xác thực bản mã. Không dùng ECB để bảo vệ dữ liệu thông thường. Với dữ liệu ứng dụng, ưu tiên AEAD và xử lý lỗi xác thực đúng cách.

## 5. Vòng đời của một secret key

Key management bảo vệ secret key từ khi hình thành đến lúc không còn tồn tại trong các vị trí có thể sử dụng.

~~~mermaid
flowchart LR
    A[Quy định mục đích và quyền] --> B[Sinh khóa]
    B --> C[Cấp phát và kích hoạt]
    C --> D[Lưu trữ và sử dụng]
    D --> E[Xoay vòng / thay thế]
    E --> D
    D --> F[Ngừng dùng / vô hiệu hóa]
    F --> G[Lưu giữ nếu cần giải mã dữ liệu cũ]
    G --> H[Hủy an toàn]
~~~

### 5.1. Sinh khóa (generation)

Khóa đối xứng phải được sinh từ **nguồn ngẫu nhiên an toàn về mật mã (CSPRNG)** hoặc thông qua KMS/HSM phù hợp. Tránh:

- Dùng số ngẫu nhiên thông thường của ngôn ngữ lập trình;
- Dùng timestamp, UUID không được thiết kế làm khóa hoặc mã định danh dự đoán được;
- Tự nối chuỗi, băm thông tin dễ đoán rồi tuyên bố đã có khóa đủ mạnh;
- Tự thiết kế thuật toán sinh khóa hoặc giao thức dẫn xuất khóa khi đã có thư viện được thẩm định.

Ví dụ trong Java, **KeyGenerator** sinh khóa AES bằng cơ chế mật mã của nhà cung cấp; **SecureRandom** phục vụ sinh nonce và vật liệu ngẫu nhiên phù hợp. Trong môi trường sản xuất, hãy cân nhắc để KMS tạo DEK và bảo vệ phiên bản khóa cấp cao.

### 5.2. Cấp phát (provisioning) và lưu trữ (storage)

Chỉ những workload đã xác thực và có mục đích hợp lệ mới được sử dụng khóa. Khi có lựa chọn, **khóa cấp cao không xuất khỏi KMS/HSM**; ứng dụng gọi dịch vụ để yêu cầu thao tác hoặc nhận DEK tạm thời đã được cấp quyền.

Không lưu secret key dạng rõ trong source code, repository, biến cấu hình đưa vào image, file được commit, log hoặc tracing. Biến môi trường cũng không mặc nhiên an toàn: chúng có thể bị lộ qua quyền truy cập tiến trình, công cụ chẩn đoán hoặc cấu hình triển khai. Nếu phải truyền vật liệu khóa, cần bảo vệ kênh truyền và danh tính hai đầu.

Khóa ở **RAM** vẫn có rủi ro qua memory dump, debugger, lỗi ứng dụng hoặc máy chủ bị chiếm. Giảm thời gian tồn tại của DEK dạng rõ, giới hạn quyền tiến trình và tránh copy/serialize khóa không cần thiết. Trong Java, cố gắng xóa dữ liệu byte nhạy cảm chỉ mang tính giảm rủi ro vì runtime và thư viện có thể tạo bản sao ngoài tầm kiểm soát.

### 5.3. Sử dụng (use) và kiểm toán (audit)

Quyền cần tách theo thao tác: dịch vụ ghi có thể chỉ cần **Encrypt/GenerateDataKey**, dịch vụ đọc được cấp **Decrypt/Unwrap** khi thực sự cần; việc xóa khóa hoặc sửa policy thuộc vai trò quản trị riêng.

Mỗi yêu cầu sử dụng KMS nên có khả năng liên hệ với **danh tính dịch vụ, key ID, thao tác, thời điểm, kết quả và request/correlation ID**, tùy mức hỗ trợ của nền tảng. Theo dõi các bất thường như decrypt tăng đột biến, thay policy ngoài quy trình, thử dùng khóa của môi trường khác hoặc yêu cầu xóa khóa bất ngờ. Không ghi nội dung khóa hay dữ liệu rõ vào audit log.

### 5.4. Xoay vòng (rotation) và thay thế

Khi đến lịch thay khóa hoặc có dấu hiệu rò rỉ:

1. Sinh và kích hoạt phiên bản secret key mới.
2. Chuyển **mã hóa dữ liệu mới** sang phiên bản mới.
3. Duy trì khả năng giải mã bản mã cũ bằng khóa cũ trong thời gian cần thiết.
4. Quyết định có cần mã hóa lại dữ liệu cũ hay chỉ bọc lại DEK, tùy loại khóa và mô hình rủi ro.
5. Thu hẹp quyền khóa cũ, ngừng sử dụng và cuối cùng hủy theo chính sách.

**Rotation không tự giải quyết sự cố lộ khóa.** Nếu một DEK đã bị lấy cắp, kẻ tấn công có thể vẫn giải mã những bản mã đã thu thập. Cần đánh giá phạm vi dữ liệu, thay khóa phù hợp, mã hóa lại dữ liệu bị ảnh hưởng khi cần và xử lý các bản sao khóa còn tồn tại.

### 5.5. Vô hiệu hóa, thu hồi và hủy

**Disable** thường ngăn khóa được sử dụng nhưng có thể đảo ngược; **retire** là ngừng sử dụng cho dữ liệu mới; **destroy** là hủy vật liệu khóa để không thể dùng lại. “Thu hồi” cần được hiểu theo cơ chế cụ thể: khóa đối xứng được kiểm soát qua chính sách, trạng thái và thay thế khóa; thu hồi chứng thư số lại có cơ chế riêng cho hệ bất đối xứng.

Trước khi hủy, phải biết các **backup, snapshot, dữ liệu lưu trữ lâu dài, bản sao ở vùng khác và hệ thống phụ thuộc** có còn cần khóa không. Hủy mọi bản sao sử dụng được của một secret key có thể khiến dữ liệu mã hóa bằng khóa đó **không thể phục hồi** — được gọi là **cryptographic erasure** trong những điều kiện thích hợp. Xóa một bản ghi khóa trong KMS chưa đủ để khẳng định đã xóa dữ liệu nếu khóa vẫn còn ở nơi khác hoặc còn các bản sao plaintext.

## 6. Secret key trong KMS, HSM và envelope encryption

**KMS (Key Management Service)** là lớp dịch vụ quản lý khóa, phiên bản, quyền sử dụng và hoạt động kiểm toán. **HSM (Hardware Security Module)** là thiết bị cung cấp ranh giới phần cứng cho vật liệu khóa và các thao tác mật mã; KMS có thể dùng HSM làm nền tảng bảo vệ. KMS không tự thay thế cho phân quyền nghiệp vụ, bảo vệ ứng dụng và bảo vệ dữ liệu ở đầu cuối.

Để mã hóa lượng dữ liệu lớn, thiết kế **envelope encryption** thường sử dụng:

- **DEK:** secret key AES tạm thời để mã hóa trực tiếp dữ liệu.
- **KEK:** khóa bọc DEK, thường được KMS/HSM bảo vệ và kiểm soát quyền dùng.
- **Wrapped DEK:** bản DEK được bảo vệ bằng KEK, có thể lưu cùng ciphertext.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant KMS as KMS/HSM
    participant DB as Cơ sở dữ liệu
    App->>KMS: GenerateDataKey / yêu cầu tạo DEK
    KMS-->>App: DEK dạng rõ tạm thời + wrapped DEK
    App->>App: AES-GCM mã hóa dữ liệu bằng DEK
    App->>DB: Ciphertext + nonce + tag + wrapped DEK + key ID
    Note over App: Giảm tối đa thời gian giữ DEK dạng rõ
    App->>DB: Đọc payload đã mã hóa
    DB-->>App: Ciphertext và wrapped DEK
    App->>KMS: Decrypt/Unwrap wrapped DEK
    KMS-->>App: DEK (nếu được cấp quyền)
    App->>App: AES-GCM giải mã, xác minh tag/AAD
~~~

**Phân biệt xoay KEK và xoay DEK:** nếu thay KEK và cơ chế hỗ trợ, hệ thống có thể **rewrap** các DEK mà không cần mã hóa lại toàn bộ dữ liệu. Nếu DEK cần thay vì bị lộ hoặc đã vượt giới hạn sử dụng, dữ liệu được mã hóa bằng DEK cũ thường phải **giải mã và mã hóa lại** dưới DEK mới.

Việc dùng envelope encryption không có nghĩa ứng dụng không bao giờ thấy secret key: trong mẫu luồng phổ biến, ứng dụng có **DEK dạng rõ ngắn hạn**. Với yêu cầu bảo vệ cao hơn, có thể chọn kiến trúc thực hiện thao tác mật mã trong vùng tin cậy hoặc dịch vụ kiểm soát đặc biệt, đánh đổi thêm về độ trễ, khối lượng dữ liệu và chi phí.

## 7. Ví dụ Java: tạo và sử dụng secret key với AES-GCM

Ví dụ dưới đây minh họa **sinh khóa AES-256, mã hóa có xác thực, và giải mã**. Nó không phải hệ thống lưu trữ khóa đầy đủ. Khi triển khai thực tế, nên lấy DEK qua quy trình KMS/envelope encryption, lưu metadata cần thiết và kiểm soát quyền truy cập.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class SecretKeyDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int GCM_NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;

    public static void main(String[] args) throws Exception {
        // Sinh secret key AES từ nguồn ngẫu nhiên mật mã của provider.
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey secretKey = generator.generateKey();

        // Trong ví dụ một lần, sinh nonce 96 bit mới.
        // Hệ thống lớn phải bảo đảm không trùng nonce trên cùng secret key.
        byte[] nonce = new byte[GCM_NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        // AAD phải được xác định từ ngữ cảnh đáng tin cậy khi giải mã.
        byte[] aad = "tenant-42|record-1001"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Du lieu can bao ve"
                .getBytes(StandardCharsets.UTF_8);

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, secretKey,
                new GCMParameterSpec(GCM_TAG_BITS, nonce));
        encryptor.updateAAD(aad);
        // Với JCA, doFinal trả ciphertext kèm authentication tag.
        byte[] ciphertextAndTag = encryptor.doFinal(plaintext);

        // Lưu nonce + ciphertextAndTag + metadata key ID/version.
        // KHÔNG lưu secretKey dạng rõ cùng bản mã.

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(Cipher.DECRYPT_MODE, secretKey,
                new GCMParameterSpec(GCM_TAG_BITS, nonce));
        decryptor.updateAAD(aad);
        byte[] restored = decryptor.doFinal(ciphertextAndTag);

        if (!Arrays.equals(plaintext, restored)) {
            throw new IllegalStateException("Data mismatch");
        }
        System.out.println("Giai ma va xac thuc thanh cong");
    }
}
~~~

**Những điểm cần kiểm tra khi chuyển ví dụ thành sản phẩm:**

1. **Không dùng lại nonce với cùng khóa.** Mỗi lần mã hóa cần nonce hợp lệ; quản lý nguy cơ trùng ở nhiều instance, nhiều lần restart và theo giới hạn thuật toán.
2. **Lưu key ID và phiên bản.** Khi đã rotation, ứng dụng cần xác định phiên bản khóa/DEK phù hợp để mở dữ liệu cũ.
3. **Dùng AAD từ ngữ cảnh tin cậy.** Với dữ liệu nhiều tenant, giá trị tenant ID/record ID khi giải mã phải gắn với đối tượng đã được phân quyền, tránh chỉ tin metadata do phía không đáng tin tự cung cấp.
4. **Xử lý lỗi xác thực.** Bản mã/tag/AAD không hợp lệ phải bị từ chối; không bỏ qua ngoại lệ xác thực hoặc trả về plaintext từng phần.
5. **Giảm tồn tại của plaintext và DEK.** Không in dữ liệu thật hoặc key ra console/log; áp dụng chính sách an toàn cho bộ nhớ, dump và tracing.
6. **Dùng KMS cho vòng đời khóa.** Đoạn code tự sinh khóa trong bộ nhớ chỉ minh họa API, chưa giải quyết khả năng khôi phục, cấp quyền, audit và quản lý rotation.

## 8. Rủi ro phổ biến và cách phòng tránh

| Sai lầm | Rủi ro | Thực hành phù hợp |
| --- | --- | --- |
| Hard-code secret key hoặc đẩy lên Git | Người có quyền đọc source có thể lấy khóa | Dùng KMS/secret store, quét rò rỉ, thay khóa bị lộ |
| Dùng một secret key cho mọi dịch vụ, tenant và môi trường | Phạm vi ảnh hưởng khi lộ quá lớn | Tách theo mục đích và ranh giới dữ liệu thích hợp |
| Lưu DEK dạng rõ ngay cạnh ciphertext | Mất cơ sở dữ liệu có thể lộ cả khóa | Envelope encryption và tách quyền với KEK |
| Cấp quyền giải mã cho mọi service account | Workload bị chiếm có thể giải mã dữ liệu ngoài nhiệm vụ | Least privilege theo thao tác, danh tính và phạm vi |
| Sử dụng AES-GCM nhưng lặp nonce | Có thể làm mất bảo đảm bảo mật và toàn vẹn | Thiết kế cấp nonce duy nhất, giám sát giới hạn sử dụng |
| Mất khóa hoặc xóa khóa cũ quá sớm | Không giải mã được dữ liệu và backup | Lập bản đồ phụ thuộc, khôi phục và thời hạn lưu giữ |
| Xoay khóa nhưng không thay dữ liệu bị ảnh hưởng khi khóa đã lộ | Bản mã cũ vẫn bị đe dọa | Ứng phó sự cố, re-encrypt/rewrap theo loại khóa |
| In secret key/DEK/plaintext ra log hoặc trace | Bí mật lan sang hệ thống quan sát | Cấm logging bí mật, redaction và giám sát truy cập |
| Dùng cùng khóa để mã hóa và tạo MAC độc lập | Trộn mục đích, tạo rủi ro giao thức | Sinh khóa riêng hoặc dẫn xuất khóa theo ngữ cảnh |
| Nghĩ rằng quyền KMS Decrypt tương đương quyền đọc dữ liệu nghiệp vụ | Vượt quyền ở lớp ứng dụng | Kiểm tra cả quyền người dùng và quyền workload |

## 9. Ví dụ tình huống: hệ thống lưu dữ liệu nhiều khách hàng

Một dịch vụ lưu thông tin cá nhân của nhiều tenant. Hệ thống chọn AES-GCM, mỗi bản ghi có DEK được tạo bởi KMS hoặc theo phạm vi khóa phù hợp, và KEK của production được bảo vệ trong KMS.

**Khi ghi:** dịch vụ kiểm tra quyền nghiệp vụ, lấy DEK hợp lệ, tạo nonce mới, mã hóa dữ liệu với tenant ID và record ID làm AAD, sau đó lưu ciphertext, tag, nonce, wrapped DEK và key ID/version.

**Khi đọc:** dịch vụ kiểm tra quyền truy cập bản ghi; chỉ sau đó mới yêu cầu KMS mở wrapped DEK. Dịch vụ giải mã với AAD được xác định từ tenant và record đã được xác thực. Nếu ciphertext bị tráo sang một bản ghi khác mà AAD không khớp, xác minh tag phải thất bại.

**Khi tài khoản dịch vụ bị chiếm:** nhóm an ninh cần khóa hoặc thu hẹp quyền KMS, rà soát các lần decrypt bất thường, xác định DEK/KEK và dữ liệu bị ảnh hưởng, tổ chức rotation và mã hóa lại nếu cần. Nếu chỉ thu hồi quyền của tài khoản nhưng kẻ tấn công đã lấy được DEK hoặc plaintext, phải đánh giá riêng lượng dữ liệu có thể đã lộ.

**Khi chuẩn bị xóa KEK cũ:** nhóm vận hành phải xác nhận không còn wrapped DEK và bản sao lưu nào phụ thuộc vào phiên bản đó; nếu còn, cần rewrap hoặc giữ khóa cũ ở trạng thái phù hợp trong thời gian lưu giữ.

Trong ví dụ này, **secret key là tài sản mật mã cần quản lý**. Cơ sở dữ liệu, quyền đọc nghiệp vụ, quyền KMS, metadata bản mã, audit và khả năng khôi phục đều liên quan trực tiếp đến tính an toàn của nó.

## 10. Checklist dành cho kỹ sư

- [ ] Đã xác định rõ secret key dùng cho mã hóa, MAC hay bọc khóa?
- [ ] Khóa được sinh bởi CSPRNG hoặc KMS, có độ dài phù hợp thuật toán?
- [ ] Đã phân biệt khóa đối xứng với private key, password và API key?
- [ ] Đã tách khóa theo mục đích, môi trường và phạm vi ảnh hưởng phù hợp?
- [ ] Có chính sách IAM/KMS ít quyền nhất cho từng thao tác và workload?
- [ ] Không có secret key dạng rõ trong source code, log, image hoặc bản ghi dữ liệu?
- [ ] Với AES-GCM, nonce không bị tái sử dụng cùng khóa; AAD và tag được xác minh?
- [ ] Payload mã hóa có key ID/version, nonce, tag và wrapped DEK khi cần?
- [ ] Có chiến lược rotation, đọc dữ liệu cũ, rewrap/re-encrypt và ứng phó lộ khóa?
- [ ] Đã kiểm tra khả năng khôi phục dữ liệu và phụ thuộc trước khi hủy khóa?
- [ ] Audit có đủ thông tin điều tra nhưng không làm lộ khóa hay plaintext?

## 11. Câu hỏi tự kiểm tra

**Câu 1. Secret key trong AES có giống private key trong RSA không?**  
Không. Secret key trong AES là khóa đối xứng. Private key là thành phần bí mật của cặp khóa bất đối xứng; public key tương ứng có thể công khai.

**Câu 2. HMAC có bảo vệ tính bí mật nội dung thông điệp không?**  
Không. HMAC giúp xác minh tính toàn vẹn và nguồn tạo MAC trong nhóm có chung secret key; để bảo mật nội dung phải dùng cơ chế mã hóa phù hợp.

**Câu 3. Vì sao không nên đưa một chuỗi mật khẩu tùy ý vào AES như khóa?**  
Vì độ dài ký tự không bảo đảm entropy và password có thể bị đoán; khi dẫn xuất khóa từ mật khẩu cần một KDF chuyên dụng phù hợp.

**Câu 4. Có thể công khai nonce và key ID không?**  
Thông thường có: nonce và key ID không phải là secret key. Tuy nhiên nonce phải đáp ứng yêu cầu duy nhất theo khóa và metadata phải được xử lý đúng, đặc biệt khi gắn AAD với ngữ cảnh tin cậy.

**Câu 5. Vì sao rotation KEK không nhất thiết phải mã hóa lại toàn bộ ciphertext?**  
Vì có thể chỉ cần bọc lại DEK dưới KEK mới. Ngược lại, nếu thay DEK đã dùng để mã hóa dữ liệu, thường phải mã hóa lại dữ liệu liên quan.

**Câu 6. Nếu xóa secret key thì bản mã chắc chắn bị xóa an toàn chưa?**  
Chưa chắc. Cần xác nhận mọi bản sao khóa khả dụng đã bị hủy và xem xét plaintext còn tồn tại, backup, snapshot cùng các hệ thống phụ thuộc.

## Ghi nhớ

**Secret key là khóa cần giữ bí mật để thực hiện thao tác mật mã, điển hình là khóa đối xứng trong AES và HMAC.** Bảo vệ secret key yêu cầu nhiều hơn việc giấu một chuỗi: phải sinh khóa an toàn, dùng đúng thuật toán và mục đích, kiểm soát quyền qua KMS/HSM khi phù hợp, áp dụng envelope encryption, quản lý nonce/metadata, ghi audit, xoay vòng và hủy khóa có kế hoạch. Một secret key bị lộ hoặc bị mất có thể làm mất **tính bí mật** hoặc **khả năng phục hồi dữ liệu**, ngay cả khi thuật toán mật mã được lựa chọn là mạnh.
