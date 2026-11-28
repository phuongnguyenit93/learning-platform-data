# Hash không phải encryption: Phân biệt hash, MAC và mã hóa

Một ứng dụng Java cần lưu mật khẩu, kiểm tra file có bị sửa khi tải xuống và bảo vệ hồ sơ khách hàng trong database. Cả ba công việc đều liên quan đến mật mã, nhưng **không thể dùng cùng một thao tác hash để thay cho mã hóa hoặc xác thực**. Hash giúp tạo dấu vân tay của dữ liệu; encryption giúp giữ bí mật dữ liệu có thể giải mã lại bằng khóa; còn MAC giúp kiểm tra dữ liệu có được tạo hoặc chấp nhận bởi một bên sở hữu khóa bí mật chung hay không.

Trong chương **Hash và MAC** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, phân biệt đúng ba cơ chế này quyết định cách thiết kế vòng đời khóa từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy. Bài học kết nối hàm băm với HMAC, chữ ký số, AES-GCM, KMS/HSM, envelope encryption, phân quyền và kiểm toán để tránh việc dùng hash như một dạng “mã hóa dữ liệu” giả.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **cryptographic hash là hàm một chiều**, không có thao tác decrypt tương ứng.
2. Phân biệt **hash, encryption, MAC/HMAC, digital signature** theo mục đích, đầu vào khóa, khả năng khôi phục và bảo đảm an ninh.
3. Hiểu các thuộc tính **preimage resistance, second-preimage resistance, collision resistance**, và giới hạn của chúng khi dữ liệu đầu vào dễ đoán.
4. Chọn cách xử lý phù hợp cho file, mật khẩu, API webhook, dữ liệu cá nhân và bản ghi cần giữ bí mật.
5. Viết ví dụ Java 17 sử dụng **SHA-256** và **HMAC-SHA-256** mà không tự tạo thuật toán mật mã.
6. Lập kế hoạch bảo vệ, phân phối và xoay vòng khóa MAC khi kết hợp với KMS/HSM, AEAD và kiểm toán.

## 2. Cryptographic hash thực hiện việc gì?

**Cryptographic hash function** là một hàm xác định nhận thông điệp có độ dài bất kỳ trong giới hạn của thuật toán và trả về một giá trị tóm tắt (*digest*), thường có độ dài cố định với các hàm như SHA-256.

~~~text
                  H(message) = digest

 "invoice=123;amount=250000" -- SHA-256 --> 32 byte digest
 "invoice=123;amount=250001" -- SHA-256 --> một digest khác

               Không có H.decrypt(digest)
~~~

Ví dụ: **SHA-256** tạo digest dài **256 bit (32 byte)**. Dữ liệu là một file 1 KB hay 1 GB thì SHA-256 vẫn trả 32 byte, nếu xử lý được đầu vào đó. Vì lượng đầu vào lớn hơn rất nhiều so với không gian digest, **chắc chắn tồn tại những đầu vào khác nhau cho cùng một digest**; thuật toán an toàn chỉ nhằm khiến việc tìm ra các trường hợp va chạm hữu ích trở nên rất khó.

Hàm hash phổ biến **không nhận khóa bí mật**. Ai có dữ liệu đều có thể tính SHA-256 của dữ liệu đó, nên việc công bố digest **không tự chứng minh ai đã tạo dữ liệu** và cũng không làm dữ liệu trở nên bí mật.

### 2.1. Vì sao hash không phải encryption?

**Encryption (mã hóa)** được thiết kế để một bên có **khóa giải mã phù hợp** có thể khôi phục plaintext. **Hash** được thiết kế để tạo digest phục vụ kiểm tra, không có thuật toán đảo ngược nhận digest và trả lại duy nhất thông điệp gốc.

| Câu hỏi | Hash mật mã, ví dụ SHA-256 | Mã hóa, ví dụ AES-GCM |
|---|---|---|
| Mục tiêu chính | Tạo dấu vân tay, thành phần trong kiểm tra toàn vẹn/chữ ký/MAC | Giữ bí mật plaintext và xác thực dữ liệu mã hóa |
| Có khóa bí mật không? | **Không** với SHA-256 thông thường | **Có**, khóa AES |
| Có khôi phục chính xác plaintext từ kết quả không? | **Không có phép decrypt** | **Có**, nếu có đúng khóa và tham số, tag hợp lệ |
| Kích thước kết quả | SHA-256 luôn 32 byte | Ciphertext dài theo dữ liệu, thêm nonce/tag/metadata |
| Dùng cho dữ liệu cần đọc lại? | Không thay được mã hóa | Có, nếu được cấp quyền giải mã |
| Chứng minh người gửi? | **Không** | AEAD tag chứng minh bên tạo/kiểm tra biết khóa chung, nhưng không phải chữ ký số độc lập |
| Khi đầu vào dễ đoán | Có thể thử đoán và so sánh hash | Không thể thử giải mã nếu thiếu khóa trong mô hình bảo mật đúng |

Mệnh đề **“Hash không giải mã được”** không có nghĩa “hash của dữ liệu luôn bảo vệ được bí mật”. Nếu tập đầu vào nhỏ, kẻ tấn công có thể **đoán thông điệp, hash từng ứng viên và so sánh digest**. Chúng không đảo ngược toán học của SHA-256 mà thực hiện **dictionary/brute-force attack** lên không gian đầu vào.

### 2.2. Hash khác encoding và obfuscation

- **Base64/hex:** chỉ là cách biểu diễn byte dưới dạng chuỗi; decode được mà không cần khóa.
- **URL encoding:** cách biểu diễn ký tự trong URL; không phải bảo mật.
- **Hash:** không có thao tác đảo ngược theo thiết kế, nhưng có thể bị dò khi đầu vào dễ đoán.
- **Encryption:** có cơ chế giải mã cho chủ thể sở hữu khóa được phép.
- **Obfuscation:** che giấu cách biểu diễn hoặc xử lý để làm khó đọc, không thay thế cryptography.

Một trường dữ liệu đã được biến thành hex dài 64 ký tự có thể là SHA-256 digest, nhưng cũng có thể chỉ là 32 byte ngẫu nhiên được encode. **Không thể xác định loại bảo vệ chỉ từ hình dạng chuỗi.**

## 3. Ba tính chất an toàn của hàm băm mật mã

Giả sử **H** là hàm băm và đầu ra có **n bit**:

| Tính chất | Bài toán kẻ tấn công muốn giải | Mức khó kỳ vọng chung cho hash n-bit lý tưởng |
|---|---|---|
| **Preimage resistance** | Biết digest y, tìm bất kỳ x sao cho H(x)=y | Khoảng 2^n phép thử trong mô hình lý tưởng |
| **Second-preimage resistance** | Biết thông điệp x, tìm x' khác x mà H(x')=H(x) | Khoảng 2^n phép thử trong mô hình lý tưởng, với các điều kiện thông thường |
| **Collision resistance** | Tự tìm hai đầu vào bất kỳ x != x' mà H(x)=H(x') | Khoảng 2^(n/2) phép thử do birthday bound |

Với SHA-256, độ khó va chạm chung kỳ vọng khoảng **2^128** phép thử, còn preimage chung khoảng **2^256** trong mô hình lý tưởng. Đây là mức tham chiếu về an ninh chung, **không bảo đảm tương tự đối với mật khẩu ngắn hoặc các cấu trúc đầu vào dễ đoán**. Các tính chất chính xác còn phụ thuộc thuật toán và mô hình tấn công.

### 3.1. Collision không giống đoán plaintext

**Collision:** tìm hai tài liệu khác nhau có cùng digest mà không bị ràng buộc vào một tài liệu cụ thể. Điều này có thể phá những hệ thống coi digest là đại diện duy nhất, đáng tin cho tài liệu.

**Preimage/dictionary attack:** biết hash của một mã PIN 6 chữ số rồi thử lần lượt 1.000.000 mã PIN là hoàn toàn khác bài toán preimage 256-bit chung. Kẻ tấn công không cần phá SHA-256 để đoán một PIN ít entropy.

**Second preimage:** khi đã có file hợp lệ cụ thể, kẻ tấn công tìm file khác cho cùng digest của file đó. Đây là bài toán khác với việc tự tạo hai file bất kỳ có digest giống nhau.

### 3.2. Thuật toán nào phù hợp?

| Thuật toán | Vai trò hiện nay | Lưu ý |
|---|---|---|
| **SHA-256, SHA-384, SHA-512** (SHA-2) | Phổ biến cho digest, chữ ký số, HMAC và nhiều giao thức | Dùng đúng thuật toán theo policy/giao thức |
| **SHA3-256, SHA3-512** | Họ SHA-3, thay thế phù hợp trong những thiết kế hỗ trợ | Không tương thích byte với SHA-2 cùng độ dài |
| **SHAKE128/SHAKE256** | Extendable-output function, có thể chọn độ dài đầu ra | Không mặc định “hash nào cũng có output cố định” |
| **SHA-1** | Không phù hợp cho ứng dụng mới đòi hỏi collision resistance | Đã có tấn công va chạm thực tế; tránh dùng cho chữ ký/kiểm tra toàn vẹn có đối thủ |
| **MD5** | Không phù hợp để làm hash mật mã bảo vệ dữ liệu khỏi đối thủ | Có va chạm thực tế; không dùng làm cơ chế tin cậy an ninh |

MD5/SHA-1 vẫn có thể xuất hiện trong hệ thống cũ hoặc checksum phi an ninh, nhưng **không dùng digest của chúng như bằng chứng chống sửa đổi trước kẻ tấn công chủ động**. Cũng không chọn “SHA-512” để băm mật khẩu trực tiếp với suy nghĩ digest dài hơn sẽ chống brute force tốt: cần một **password hashing/KDF có chủ đích làm chậm việc đoán**.

## 4. Hash, MAC, chữ ký số và AEAD giải quyết các vấn đề khác nhau

~~~mermaid
flowchart TD
    D["Cần bảo vệ dữ liệu"] --> Q{"Yêu cầu chính?"}
    Q -->|"Dấu vân tay hoặc phát hiện sai khác, nguồn digest đã tin cậy"| H["Cryptographic hash"]
    Q -->|"Xác thực thông điệp giữa các bên chia sẻ khóa bí mật"| M["MAC / HMAC"]
    Q -->|"Bên thứ ba xác minh tác giả bằng public key"| S["Digital signature"]
    Q -->|"Giữ bí mật và xác thực ciphertext"| E["AEAD: AES-GCM"]
    Q -->|"Mật khẩu cần kiểm tra sau này"| P["Password hashing: Argon2id / scrypt / PBKDF2"]
~~~

| Cơ chế | Đầu vào khóa | Đầu ra | Bảo vệ bí mật? | Điều nó thực sự xác thực |
|---|---|---|---|---|
| **SHA-256** | Không | Digest | Không | Bản thân nó không xác thực người tạo; chỉ so sánh dữ liệu với digest được tin cậy |
| **HMAC-SHA-256** | Khóa đối xứng bí mật | MAC tag | Không | Bên tạo tag biết khóa chung, trong phạm vi chính sách phân phối khóa |
| **Ed25519 / RSA-PSS** | Private key để ký, public key để verify | Digital signature | Không | Khớp với khóa ký; danh tính chỉ được xác nhận nếu public key đã gắn với nguồn đáng tin |
| **AES-256-GCM** | Khóa AES, nonce, AAD | Ciphertext và authentication tag | **Có** | Ciphertext/AAD chưa bị sửa dưới khóa được dùng, nếu triển khai đúng |
| **Argon2id/scrypt/PBKDF2** | Mật khẩu + salt + tham số thuật toán | Password verifier/hash được dẫn xuất | Không giải mã mật khẩu | Kiểm tra ứng viên mật khẩu bằng tính lại dẫn xuất; không thay thế xác thực phiên |

Một hash **không có bí mật** có thể được kẻ tấn công tính lại sau khi sửa dữ liệu. Do đó **hash gửi cạnh file qua cùng một nguồn không đáng tin không chứng minh file chưa bị sửa một cách ác ý**. Muốn xác thực file, phải có digest được lấy từ kênh tin cậy, chữ ký số, MAC hoặc giao thức xác thực phù hợp.

## 5. MAC và HMAC: Thêm khóa bí mật vào kiểm tra thông điệp

**Message Authentication Code (MAC)** dùng một khóa bí mật và thông điệp để tính **tag**. Bên kiểm tra có khóa tương ứng tính lại tag rồi so sánh. Không biết khóa thì kẻ tấn công không thể dễ dàng tạo tag hợp lệ cho thông điệp khác, dưới các giả định bảo mật của MAC.

**HMAC** là một cấu trúc MAC dùng hàm băm mật mã theo quy tắc đã được chuẩn hóa. **HMAC-SHA-256** sử dụng SHA-256 bên trong và một khóa bí mật; nó **khác hẳn** việc tính SHA-256 của thông điệp hoặc tự ghép **SHA256(secret || message)**.

~~~text
Không có khóa:
    digest = SHA256(message)
    Bất kỳ ai có message đều tạo được digest.

Có khóa bí mật:
    tag = HMAC_SHA256(macKey, message)
    Người không sở hữu macKey không thể tạo tag hợp lệ tùy ý.

Bên nhận:
    expected = HMAC_SHA256(macKey, receivedMessage)
    constantTimeCompare(expected, receivedTag)
~~~

### 5.1. HMAC đem lại điều gì và không đem lại điều gì?

| Bảo đảm | Có? | Giải thích |
|---|---|---|
| Toàn vẹn thông điệp trước đối thủ không có khóa | **Có**, khi dùng đúng | Thay nội dung thường làm HMAC tag không còn hợp lệ |
| Xác thực dựa trên sở hữu khóa chung | **Có** | Chỉ principal được cấp khóa MAC mới nên có khả năng tạo tag |
| Giữ bí mật message | **Không** | Message vẫn ở dạng đọc được nếu không được mã hóa riêng |
| Chứng minh một người gửi độc lập với người nhận | **Không** | Cả hai bên biết cùng khóa có thể tạo tag; không có tính chất chữ ký bất đối xứng |
| Chống replay | **Không tự có** | Message và tag cũ vẫn hợp lệ nếu không kiểm soát timestamp/nonce/message ID |
| Định danh tenant hoặc quyền của người gọi | **Không tự có** | Cần IAM/workload identity, binding context và kiểm tra policy |

Ví dụ webhooks: phía gửi và nhận có **HMAC key** được phân phối an toàn. Bên gửi tính tag trên **chính xác raw request body** (và các trường header ngữ cảnh đã quy định). Bên nhận xác minh tag và kiểm tra timestamp, request ID, cửa sổ thời gian để ngăn replay. Nếu ký lại một JSON đã parse và serialize khác đi, byte đầu vào sẽ khác nên tag không khớp.

### 5.2. HMAC, CMAC và GMAC

- **HMAC:** MAC dựa trên hash, ví dụ HMAC-SHA-256; có API **Mac** trong Java.
- **CMAC:** MAC dựa trên block cipher, như AES-CMAC, có đặc tính và quy tắc sử dụng riêng.
- **GMAC:** phần xác thực của GCM khi không mã hóa plaintext; **nonce phải duy nhất theo khóa**, tương tự điều kiện an toàn của GCM.

Không lấy cùng một khóa AES tùy ý dùng cho AES-GCM và GMAC hay một giao thức khác mà không có thiết kế phân tách mục đích. Trong hệ thống có nhiều loại operation, nên tách khóa hoặc **dẫn xuất khóa con có domain separation** bằng một KDF phù hợp theo giao thức.

## 6. Ví dụ Java 17: Hash SHA-256 và HMAC-SHA-256

Đoạn mã dùng thư viện chuẩn Java để minh họa: cùng một thông điệp có thể được hash không cần khóa hoặc được xác thực bằng HMAC key bí mật. Chương trình tạo khóa HMAC tạm thời để học; môi trường production cần cơ chế quản lý key material, owner, ID/version và quyền sử dụng.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class HashVsMacExample {
    private static byte[] sha256(byte[] message) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        return digest.digest(message);
    }

    private static byte[] hmacSha256(
            SecretKey macKey, byte[] message) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(macKey);
        return mac.doFinal(message);
    }

    public static void main(String[] args) throws Exception {
        byte[] original = "order=123;total=500000"
                .getBytes(StandardCharsets.UTF_8);
        byte[] changed = "order=123;total=900000"
                .getBytes(StandardCharsets.UTF_8);

        System.out.println("SHA-256: "
                + HexFormat.of().formatHex(sha256(original)));
        System.out.println("Digest changed: "
                + !MessageDigest.isEqual(
                        sha256(original), sha256(changed)));

        // Khóa HMAC được tạo ngẫu nhiên, không hardcode secret.
        KeyGenerator keyGenerator = KeyGenerator.getInstance("HmacSHA256");
        SecretKey macKey = keyGenerator.generateKey();

        byte[] sentTag = hmacSha256(macKey, original);
        boolean accepted = MessageDigest.isEqual(
                sentTag, hmacSha256(macKey, original));
        boolean tamperedAccepted = MessageDigest.isEqual(
                sentTag, hmacSha256(macKey, changed));

        System.out.println("Original MAC valid: " + accepted);
        System.out.println("Tampered MAC valid: " + tamperedAccepted);

        // Không ghi macKey.getEncoded(), private key hoặc mật khẩu ra log.
    }
}
~~~

Lưu thành **HashVsMacExample.java**, chạy với JDK 17+:

~~~bash
javac HashVsMacExample.java
java HashVsMacExample
~~~

Kết quả mong đợi: **Digest changed: true**, **Original MAC valid: true**, **Tampered MAC valid: false**. Với hash thuần túy, bất kỳ ai cũng có thể tính SHA-256 của thông điệp đã bị sửa; còn với MAC, bên không có khóa bí mật không thể tự tạo tag mới tương ứng.

**Chú ý triển khai:**

1. **MessageDigest.getInstance("SHA-256")** chỉ trả digest, không mã hóa và không dùng khóa.
2. **Mac.getInstance("HmacSHA256")** dùng SecretKey; không ghép chuỗi bí mật với thông điệp để giả lập HMAC.
3. **MessageDigest.isEqual** giúp so sánh các byte tag theo cách hạn chế rủi ro rò thông tin thời gian so sánh. Nó không thay thế bảo vệ khóa hoặc xác thực request.
4. Các bên phải thống nhất **byte message**, encoding, trường dữ liệu, thứ tự và định dạng. Với JSON, ưu tiên dùng raw bytes theo contract hoặc canonical representation chuẩn hóa.
5. Một tag hợp lệ không chứng minh request là mới. Nếu không có nonce/timestamp/message ID được bảo vệ và cơ chế kiểm tra replay, một request cũ có thể được gửi lại.
6. Demo sử dụng **HMAC key trong bộ nhớ JVM** để dễ hiểu; KMS/HSM có thể cung cấp API **GenerateMac/VerifyMac** hoặc tương đương, tùy dịch vụ.

### 6.1. Java kiểm tra digest của một file

Khi file lớn, nên hash **theo luồng** thay vì nạp toàn bộ vào RAM:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class FileSha256 {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: FileSha256 <path>");
        }
        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                sha256.update(buffer, 0, count);
            }
        }
        System.out.println(HexFormat.of().formatHex(sha256.digest()));
    }
}
~~~

Digest này có thể dùng để đối chiếu với một giá trị SHA-256 được cấp từ **nguồn tin cậy**. Nếu file và chuỗi SHA-256 đều bị thay bởi cùng kẻ tấn công, so sánh digest vẫn có thể “PASS” dù file độc hại. Vì vậy **hash không thay thế chữ ký số của bản phát hành**.

## 7. Vì sao không lưu mật khẩu bằng SHA-256 trực tiếp?

Mật khẩu của người dùng thường có entropy thấp hơn nhiều so với một khóa AES ngẫu nhiên. Nếu lưu **SHA256(password)**, kẻ tấn công lấy được bảng hash có thể thử hàng triệu ứng viên phổ biến để tìm mật khẩu trùng digest. SHA-256 được thiết kế để **tính nhanh**, nên trực tiếp hash mật khẩu tạo điều kiện cho tấn công dò đoán ngoại tuyến.

Đối với **password storage**, nên dùng cơ chế **password hashing** phù hợp, chẳng hạn **Argon2id** (ưu tiên khi nền tảng hỗ trợ), **scrypt** hoặc **PBKDF2** với tham số được điều chỉnh theo môi trường và chính sách hiện hành.

~~~mermaid
flowchart LR
    P["Mật khẩu người dùng"] --> F["Password hashing / KDF"]
    S["Salt ngẫu nhiên riêng mỗi mật khẩu"] --> F
    C["Tham số memory/time/iterations + version"] --> F
    F --> D["Password verifier / derived hash"]
    D --> DB[("Kho lưu trữ cùng salt, parameters và version")]
    V["Lần đăng nhập sau"] --> X["Dẫn xuất lại từ mật khẩu nhập"]
    DB --> X
    X --> Y["So sánh verifier và kiểm tra chính sách xác thực"]
~~~

### 7.1. Salt và pepper

- **Salt:** giá trị ngẫu nhiên, **riêng cho từng password verifier**; có thể lưu cùng hash. Salt giúp tránh việc hai người cùng mật khẩu tạo cùng verifier khi tham số giống nhau và làm giảm hiệu quả bảng tính sẵn/rainbow table. **Salt không phải khóa bí mật**.
- **Pepper:** bí mật bổ sung do ứng dụng quản lý riêng khỏi database, khi kiến trúc có yêu cầu. Pepper cần bảo vệ bằng KMS/HSM/secret management, phân quyền và vòng đời riêng; **pepper không thay thế salt và password hashing**.
- **Work factor:** tham số thời gian/bộ nhớ/iteration ảnh hưởng chi phí thử đoán. Phải theo dõi khả năng phần cứng, DoS, thời gian xác thực và hướng dẫn hiện hành; không gắn một con số iteration cố định cho mọi hệ thống mãi mãi.

Trong hệ thống cần xác thực mật khẩu, việc **encrypt password rồi decrypt để so sánh** thường tạo ra rủi ro không cần thiết vì hệ thống giữ khả năng khôi phục plaintext hàng loạt. Password verifier có salt và thuật toán chuyên dụng là phương án thông thường, trừ những bài toán rất khác có yêu cầu nghiệp vụ đặc biệt.

### 7.2. Hash một email hoặc số điện thoại có đủ bảo vệ riêng tư?

**Không.** Email, số điện thoại và mã định danh thường có cấu trúc, thậm chí có thể liệt kê hoặc đoán được. SHA-256(email) vẫn có thể bị khôi phục bằng cách thử ứng viên. Hash thuần túy cũng tạo **dấu liên kết ổn định** nếu cùng dữ liệu đầu vào được hash giống nhau ở nhiều tập dữ liệu.

Nếu cần một định danh dùng để **đối chiếu** mà hạn chế việc đoán thông điệp, có thể cân nhắc **HMAC với khóa bí mật** được bảo vệ và domain separation theo use case. Nhưng HMAC có thể cho phép liên kết bản ghi khi dùng chung khóa, và nếu khóa bị lộ, đầu vào dễ đoán vẫn bị dò lại. Với thông tin cần **đọc lại**, phải dùng **encryption** có quản lý khóa và quyền giải mã phù hợp.

## 8. Hash trong chữ ký số, mã hóa và key derivation

Hash có thể là **thành phần** của giao thức mật mã mạnh mà không phải bản thân nó là encryption:

### 8.1. Chữ ký số

Một số sơ đồ chữ ký như RSA-PSS hoặc ECDSA dùng hàm băm trong quá trình ký/xác minh. Bên ký sử dụng **private key**; bên nhận dùng **public key đáng tin cậy** kiểm tra chữ ký. Không được gọi một SHA-256 digest đặt cạnh file là “chữ ký số”.

~~~text
SHA-256(message)                  -> digest, bất kỳ ai cũng tạo được
Sign(privateKey, message/digest)  -> signature theo đúng thuật toán
Verify(publicKey, message, signature) -> hợp lệ hoặc không
~~~

Với **Ed25519**, thuật toán ký có quy trình hash nội bộ riêng; ứng dụng không tự mặc định rằng mọi API chữ ký đều cần nhận một digest SHA-256 đã băm trước. Phải dùng đúng API và chuẩn định dạng chữ ký được áp dụng.

### 8.2. AES-GCM và MAC khác nhau thế nào?

**AES-GCM** là AEAD: ciphertext được giữ bí mật dưới khóa AES và authentication tag xác minh ciphertext/AAD. **HMAC** xác thực thông điệp nhưng **không mã hóa** thông điệp. Nếu chỉ dùng HMAC trên plaintext, bên nhận thấy plaintext; nếu dùng AES-GCM, bên chưa có khóa không được đọc plaintext theo mô hình bảo mật phù hợp.

Không cần tự cộng thêm HMAC lên mỗi AES-GCM ciphertext theo một sơ đồ tự phát. Nếu giao thức yêu cầu **Encrypt-then-MAC** hoặc chữ ký số bổ sung, cần xác định khóa riêng, ngữ cảnh, thứ tự, phạm vi dữ liệu được bảo vệ và API theo chuẩn. GCM đã có authentication tag cho bản mã.

### 8.3. HKDF không phải hash để “mã hóa khóa”

**HKDF (HMAC-based Key Derivation Function)** dùng HMAC theo quy trình **extract/expand** để dẫn xuất các khóa con từ input keying material (IKM) phù hợp cùng salt và info. **HKDF không phải encryption** và không tự làm một mật khẩu yếu trở nên có entropy cao. Nó thường dùng để **dẫn xuất các khóa khác nhau cho những mục đích khác nhau** theo domain separation.

Ví dụ một bí mật chung từ **ECDH/X25519** có thể được đưa qua KDF theo giao thức để tạo khóa AES-GCM và các khóa cần thiết khác. Còn nếu một DEK đã được tạo ngẫu nhiên trong KMS, **envelope encryption** thường bảo vệ nó bằng KEK/wrapping mechanism; không thể thay bước wrapping bằng việc chỉ lưu **SHA256(DEK)** vì digest không khôi phục lại được DEK.

### 8.4. Hash và kiểm soát key material

Trong quản lý khóa, digest đôi khi được dùng làm **fingerprint/identifier** của public key hoặc artifact. Một **public-key fingerprint** chỉ hữu ích khi người dùng so sánh với fingerprint nhận qua **kênh tin cậy**. Hash của private key không nên được ghi log hoặc công bố một cách tùy tiện: tuy private key ngẫu nhiên mạnh khó suy ra từ digest, việc phát hành thông tin về secret có thể không cần thiết và vi phạm policy quản lý khóa.

Một **key ID/version** là metadata; nó không thay thế khóa, không cấp quyền sử dụng và không xác thực public key chỉ vì có vẻ giống hash dài.

## 9. Vòng đời HMAC key trong KMS/HSM

**SHA-256 không cần bí mật khóa**, nhưng **HMAC-SHA-256 cần MAC key bí mật**. Khi triển khai HMAC trong nhiều service, các vấn đề của key management xuất hiện: ai tạo khóa, ai được sử dụng, cách phân phối, version, rotation, revocation và thời hạn chấp nhận tag cũ.

~~~mermaid
flowchart TD
    A["Tạo HMAC key bằng CSPRNG hoặc KMS/HSM"] --> B["Gán keyId, version, owner, purpose"]
    B --> C["Phân phối/cấp quyền sử dụng an toàn"]
    C --> D["GenerateMac / VerifyMac hoặc HMAC trong vùng tin cậy"]
    D --> E["Audit caller, action, keyId, result"]
    E --> F["Tạo phiên bản MAC key mới khi rotation"]
    F --> G["Chuyển việc tạo tag mới sang khóa mới"]
    G --> H["Cho phép verify tag cũ có giới hạn nếu nghiệp vụ cần"]
    H --> I["Thu hồi/vô hiệu hóa và hủy sau khi hết phụ thuộc"]
~~~

| Thành phần | Là gì? | Yêu cầu quản lý |
|---|---|---|
| **HMAC key** | Key material bí mật, dùng cho Generate/Verify MAC | Giữ bí mật, giới hạn principal và scope, version hóa, rotate |
| **SHA-256 digest** | Giá trị hash không khóa | Không cần quản lý như secret, nhưng phải xét thông tin rò rỉ từ dữ liệu dễ đoán |
| **HMAC tag** | Giá trị xác thực thông điệp | Có thể gửi cùng message; cần chống replay và quản lý khóa xác minh |
| **keyId/keyVersion** | Metadata tham chiếu khóa MAC | Chống sửa trái phép, chỉ chọn trong danh sách khóa được phép |
| **Audit record** | Ai dùng khóa, lúc nào, kết quả ra sao | Không ghi HMAC key, token bí mật hay plaintext nhạy cảm |

Một số KMS/HSM cho phép **GenerateMac/VerifyMac** bằng khóa HMAC không xuất được; API và loại khóa hỗ trợ phụ thuộc nhà cung cấp. Nếu ứng dụng giữ HMAC key trong bộ nhớ, phải bảo vệ đường phân phối khóa và giới hạn nơi tồn tại bản rõ. **Non-exportable** giảm nguy cơ lộ byte khóa, nhưng workload có quyền GenerateMac quá rộng vẫn có thể tạo tag cho thông điệp giả.

### 9.1. Rotation và kiểm tra thông điệp cũ

Giả sử API webhook chuyển từ **mac-key-v3** sang **mac-key-v4**:

1. Tạo và cấp quyền sử dụng v4, phát hành key ID mới bằng kênh tin cậy.
2. Chuyển **GenerateMac** cho webhook mới sang v4.
3. Trong khoảng thời gian chuyển tiếp giới hạn, bên nhận có thể **VerifyMac** bằng v3 cho request chưa hết hạn nếu chính sách cho phép.
4. Ràng buộc **key ID, timestamp, request ID và body** vào dữ liệu xác thực; chỉ cho phép key ID đã đăng ký, kiểm tra replay.
5. Vô hiệu hóa v3 sau khi hết window chấp nhận; audit trước khi hủy và xử lý bản sao khóa còn tồn tại.

Không thử mọi MAC key vô hạn hoặc cho phép caller tự trỏ đến một **key URL** bất kỳ. Nếu phát hiện **HMAC key bị lộ**, chỉ đổi alias mà vẫn chấp nhận tag được tạo bằng khóa lộ sẽ khiến kẻ tấn công tiếp tục tạo request hợp lệ. Cần thu hồi và ứng phó theo rủi ro.

### 9.2. MAC và mã hóa dữ liệu trong envelope encryption

Trong **envelope encryption**, một **DEK** mã hóa dữ liệu bằng AES-GCM; một **KEK** trong KMS/HSM bảo vệ DEK. **Hash(DEK)** không phải wrapped DEK và không giúp khôi phục DEK. Nếu giao thức có thêm HMAC để xác thực metadata hoặc thông điệp, **HMAC key** phải được định nghĩa và quản lý độc lập theo purpose hoặc được dẫn xuất đúng chuẩn, không dùng bừa DEK/KEK làm khóa MAC.

Khi KEK được xoay vòng, có thể **rewrap** DEK theo quy trình được hỗ trợ; hash của ciphertext không có khả năng thực hiện rewrap. Khi DEK bị hủy, bản mã có thể trở nên không giải mã được; digest của plaintext hoặc ciphertext **không khôi phục dữ liệu**.

## 10. Những lỗi thiết kế phổ biến

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| **SHA256(customerName)** rồi gọi là “đã mã hóa tên” | Dữ liệu dễ đoán, không thể đọc lại đúng; vẫn rò rỉ mẫu/khả năng đối chiếu | Nếu cần đọc lại, dùng AES-GCM/envelope encryption; bảo vệ DEK bằng KMS |
| Lưu **SHA256(password)** không salt và cost | Dễ bị dò mật khẩu phổ biến từ hash bị lộ | Argon2id/scrypt/PBKDF2, salt riêng và tham số được duy trì |
| Dùng MD5/SHA-1 làm bằng chứng không bị giả mạo | Rủi ro va chạm, thiết kế lỗi thời | SHA-2/SHA-3 và xác thực nguồn bằng signature/MAC khi cần |
| Gửi file và SHA-256 qua cùng một nguồn không tin cậy | Kẻ tấn công thay cả file và digest | Chữ ký số hoặc digest từ kênh đã tin cậy |
| Gọi **SHA256(secret + data)** là HMAC | Thiết kế MAC tự tạo, có thể có lỗ hổng cấu trúc | Dùng HMAC theo API chuẩn |
| Dùng HMAC để “mã hóa” payload webhook | Nội dung vẫn đọc được | Mã hóa AEAD riêng nếu cần bí mật |
| Dùng HMAC nhưng không kiểm tra timestamp/request ID | Request hợp lệ cũ bị replay | MAC bao phủ ngữ cảnh và chính sách chống replay |
| So sánh tag bằng code tự viết lộ thời gian | Có thể rò rỉ thông tin tag theo timing | Dùng API verify hoặc so sánh byte an toàn thích hợp |
| Cho caller tự đặt keyId, algorithm mà không kiểm tra | Chọn sai khóa hoặc hạ cấp thuật toán | Allowlist, key registry tin cậy và policy theo principal |
| Tái dùng cùng khóa cho HMAC, AES-GCM, wrapping | Vi phạm tách purpose, tăng phạm vi sự cố | Dùng khóa riêng hoặc KDF với domain separation đúng |
| Ghi HMAC key/DEK/private key vào log | Lộ key material, giả mạo/giải mã trái phép | Cấm log secret, phân quyền và giám sát |
| Nghĩ AES-GCM tag là chữ ký số | Nhầm tính xác thực khóa chung với tác giả độc lập | Dùng chữ ký bất đối xứng khi cần kiểm tra bởi bên thứ ba |
| Hủy MAC key khi còn webhook cũ cần verify | Mất khả năng xác minh thông điệp còn hiệu lực | Lập kế hoạch key version và khoảng chuyển tiếp có giới hạn |

## 11. Tình huống thực tế: hệ thống lưu hồ sơ và nhận webhook

Một doanh nghiệp có ba luồng:

**Luồng A – Lưu hồ sơ khách hàng.** Ứng dụng phải đọc lại địa chỉ và số điện thoại sau này. **Không dùng SHA-256 để thay dữ liệu gốc**: điều này làm mất khả năng đọc lại và có thể rò rỉ dữ liệu dễ đoán. Thay vào đó, mã hóa bằng **AES-GCM** với DEK phù hợp, bảo vệ DEK bằng KEK/KMS, lưu nonce/tag/key reference và kiểm tra IAM trước khi decrypt. Nếu cần tìm kiếm đối chiếu, thiết kế cơ chế index chuyên biệt có đánh giá rủi ro, không dùng hash thuần như một lời hứa bảo mật.

**Luồng B – Nhận webhook từ đối tác.** Dữ liệu request có thể được nhìn thấy ở phía nhận, nhưng bên nhận phải xác minh request có đến từ một bên được cấp HMAC key không. Thiết lập **HMAC-SHA-256** trên bytes được quy định, cùng timestamp và message ID. Bảo vệ HMAC key bằng secret management/KMS/HSM nếu hỗ trợ, dùng key ID/version có policy và chống replay trước khi xử lý giao dịch.

**Luồng C – Phát hành gói phần mềm.** Người tải muốn biết file không bị thay thế. Bên phát hành tạo **chữ ký số** trên artifact hoặc manifest theo định dạng đáng tin cậy. Người tải xác minh với public key phát hành từ trust anchor phù hợp. Có thể hiển thị SHA-256 để tra cứu và đối chiếu, nhưng một chuỗi SHA-256 không xác thực nguồn công bố không đủ để chứng minh file an toàn.

Ba luồng có nhu cầu bảo vệ khác nhau. Cố dùng một hàm băm cho cả ba sẽ dẫn đến những sai lầm thiết kế nghiêm trọng dù code SHA-256 luôn trả digest hợp lệ.

## 12. Checklist chọn hash, MAC, signature hay encryption

1. **Cần khôi phục dữ liệu?** Nếu có, sử dụng **encryption** với quản lý khóa; không dùng hash thay ciphertext.
2. **Chỉ cần phát hiện file thay đổi?** Dùng hash để đối chiếu, nhưng bảo đảm **nguồn digest được tin cậy** nếu có đối thủ.
3. **Cần xác thực thông điệp giữa hai bên chia sẻ secret?** Dùng **MAC/HMAC** theo giao thức, kèm ngữ cảnh, key ID/version và anti-replay.
4. **Cần bên thứ ba kiểm tra tác giả?** Dùng **digital signature** cùng public-key trust, không dùng digest hoặc MAC để thay thế.
5. **Cần lưu password verifier?** Dùng **password hashing/KDF chuyên dụng** với salt và work factor, không dùng SHA-256 trực tiếp.
6. **Cần giữ bí mật và toàn vẹn dữ liệu?** Dùng AEAD như **AES-GCM**, quản lý nonce không trùng theo khóa và AAD chính xác.
7. **Có dữ liệu đầu vào dễ đoán?** Không coi hash thuần là ẩn danh; đánh giá dictionary attack, linkability và nhu cầu HMAC/encryption.
8. **Đã tách purpose của khóa chưa?** HMAC key, DEK, KEK, private signing key có policy và vòng đời thích hợp.
9. **Đã có kế hoạch rotation/recovery?** Đảm bảo các thông điệp cũ cần verify, bản mã cũ cần decrypt và backup được xử lý trước khi hủy khóa.
10. **Đã có IAM/audit?** Giới hạn GenerateMac/VerifyMac, Sign/Decrypt/Unwrap và bảo vệ key material khỏi log, code, CI/CD.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không thể lấy SHA-256 digest của một tệp để “giải mã” lại tệp ban đầu?

**Trả lời:** SHA-256 là hàm một chiều tạo digest 256 bit. Không có khóa giải mã và nhiều đầu vào khác nhau có thể trùng digest; không tồn tại phép giải mã khôi phục duy nhất tệp gốc.

**Câu 2.** Kẻ tấn công biết SHA-256 của một mã PIN gồm 6 chữ số. SHA-256 có còn bảo đảm giữ kín mã PIN không?

**Trả lời:** **Không.** Kẻ tấn công có thể thử tối đa khoảng một triệu ứng viên PIN rồi so sánh digest. Đây là tấn công vào không gian đầu vào nhỏ, không đòi hỏi phá SHA-256.

**Câu 3.** Vì sao SHA-256(file) gửi kèm file không đủ chứng minh file do nhà phát hành tin cậy tạo ra?

**Trả lời:** Bất kỳ ai cũng có thể sửa file và tính digest mới. Cần digest qua kênh tin cậy hoặc chữ ký số hợp lệ gắn với khóa phát hành đã được xác thực.

**Câu 4.** HMAC-SHA-256 có mã hóa nội dung webhook không?

**Trả lời:** **Không.** Nó tạo MAC tag phục vụ kiểm tra tính toàn vẹn/tính xác thực dựa trên secret key chung. Muốn giữ bí mật payload phải dùng mã hóa phù hợp.

**Câu 5.** HMAC tag hợp lệ có nghĩa request không thể bị phát lại không?

**Trả lời:** **Không.** Cần bảo vệ và kiểm tra timestamp, request ID/sequence, thời hạn và trạng thái xử lý theo giao thức.

**Câu 6.** Có thể lưu SHA256(DEK) để sau này thay thế được wrapped DEK trong envelope encryption không?

**Trả lời:** **Không.** Hash không khôi phục DEK; phải dùng cơ chế wrapping/encryption key material hoặc giữ khả năng dẫn xuất theo giao thức đã thiết kế đúng.

**Câu 7.** HMAC key trong HSM không xuất được, vậy đã chặn hoàn toàn nguy cơ giả mạo webhook?

**Trả lời:** **Chưa.** Workload bị chiếm mà có quyền GenerateMac vẫn có thể yêu cầu HSM tạo tag hợp lệ. Phải kiểm soát quyền sử dụng khóa, giới hạn scope, ghi audit và theo dõi bất thường.

**Điểm cốt lõi:** **Hash không phải encryption**. Hash tạo dấu vân tay không khóa; HMAC dùng **khóa bí mật** để xác thực thông điệp; chữ ký số dùng **private/public key** để cho phép xác minh theo danh tính tin cậy; còn AES-GCM dùng **khóa đối xứng** để mã hóa và xác thực dữ liệu. Chọn đúng cơ chế, quản lý khóa và kiểm tra quyền theo vòng đời mới tạo ra hệ thống bảo mật thực sự.
