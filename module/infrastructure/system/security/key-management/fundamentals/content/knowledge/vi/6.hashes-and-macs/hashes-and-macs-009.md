# Hash password và password hashing khác nhau

> **Chương:** Hash và MAC  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Hai cách gọi có thực sự chỉ hai kỹ thuật khác nhau?

Trong tài liệu và mã nguồn, bạn có thể gặp những cụm như **hash password**, **password hash**, **hashing a password** hoặc **password hashing**. Chúng rất dễ bị hiểu nhầm là hai thuật toán khác nhau.

**Không có hai primitive mật mã độc lập mang tên “hash password” và “password hashing”.** Khác biệt chủ yếu nằm ở **cách dùng từ và mức độ nhấn mạnh**:

| Cụm từ | Nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| **Hash password / hash a password** | Động từ: thực hiện thao tác băm một mật khẩu; đôi khi là tên hàm | `hashPassword(password)` |
| **Password hash** | Danh từ: giá trị được lưu để kiểm tra mật khẩu, có thể kèm salt/thuật toán/tham số | `storedPasswordHash` |
| **Password hashing** | Danh từ: toàn bộ **kỹ thuật và quy trình** chuyển mật khẩu thành giá trị kiểm chứng an toàn khi đăng ký và đăng nhập | Sinh salt, dùng Argon2id, lưu verifier và kiểm tra khi đăng nhập |
| **General-purpose hashing** | Băm dữ liệu bằng SHA-256, SHA-512... cho mục đích tổng quát | `SHA-256(fileBytes)` |

Một lời gọi `SHA-256(password)` **đúng là đã “hash password” theo nghĩa đen**, nhưng **không tạo thành một thiết kế password hashing an toàn** để lưu mật khẩu đăng nhập. Thuật toán băm tổng quát được thiết kế để chạy nhanh, trong khi hệ thống xác thực cần giảm tốc độ thử đoán mật khẩu ngoại tuyến khi cơ sở dữ liệu bị lộ.

Vì vậy, khi đánh giá hệ thống, đừng chỉ hỏi **“Mật khẩu có được hash không?”**. Hãy hỏi **“Hệ thống dùng password hashing algorithm nào, sinh salt ra sao, tham số chi phí thế nào, xác minh và nâng cấp ra sao?”**.

## 2. Vì sao mật khẩu cần quy trình riêng?

**Mật khẩu do con người đặt thường có entropy thấp** và có thể bị đoán theo từ điển, mẫu phổ biến hoặc dữ liệu lộ từ những dịch vụ khác. Ngay cả khi hàm băm có khả năng chống va chạm tốt, kẻ tấn công vẫn có thể đoán từng mật khẩu ứng viên rồi so sánh kết quả với giá trị đã đánh cắp.

Giả sử cơ sở dữ liệu lưu:

~~~text
username       password_hash
alice          SHA256("password123")
bob            SHA256("password123")
~~~

Hai mật khẩu giống nhau sẽ tạo kết quả giống nhau khi không có salt. Kẻ tấn công không cần đảo ngược SHA-256 bằng toán học: họ chỉ cần thử `password123`, tính SHA-256 và đối chiếu. GPU có thể tính lượng rất lớn hash tổng quát trong thời gian ngắn.

**Password hashing đúng cách** dùng thuật toán được thiết kế cho mật khẩu, thường với:

1. **Salt riêng và ngẫu nhiên cho từng giá trị mật khẩu**, để cùng mật khẩu không cho cùng bản ghi lưu trữ.
2. **Chi phí tính toán được cấu hình**, để mỗi lần thử đoán của kẻ tấn công trở nên đắt hơn.
3. **Khả năng lưu thuật toán và tham số**, hỗ trợ xác minh mật khẩu cũ và nâng cấp chính sách.
4. **So sánh kết quả an toàn**, cùng cơ chế xác thực ứng dụng như giới hạn tốc độ, giám sát và MFA khi phù hợp.

Password hashing làm **tăng chi phí đoán**, không khiến mật khẩu yếu trở thành không thể đoán và không thay thế chính sách xác thực toàn hệ thống.

## 3. Các thuật ngữ cần phân biệt

### 3.1. Hash function và password hashing function

Hàm băm mật mã tổng quát nhận dữ liệu bất kỳ và trả về giá trị cố định:

~~~text
digest = SHA-256(message)
~~~

Nó hữu ích cho kiểm tra toàn vẹn, làm thành phần của HMAC, chữ ký số hoặc KDF. Nhưng tốc độ nhanh **không phù hợp khi trực tiếp lưu giá trị kiểm chứng mật khẩu**.

Password hashing function được thiết kế để thực hiện các phép tính tốn chi phí hơn:

~~~text
verifier = PasswordHash(password, salt, costParameters)
~~~

Một số giải pháp còn tiêu thụ đáng kể **bộ nhớ**, khiến việc thử hàng loạt mật khẩu trên phần cứng song song đắt hơn.

### 3.2. Salt là gì?

**Salt** là chuỗi ngẫu nhiên được tạo mới cho mỗi mật khẩu cần lưu. Salt **không phải bí mật**; nó được lưu cùng kết quả và tham số để xác minh về sau.

~~~text
Alice: PasswordHash("same-password", salt_A, params) -> hash_A
Bob:   PasswordHash("same-password", salt_B, params) -> hash_B

salt_A != salt_B  => thông thường hash_A != hash_B
~~~

Salt ngăn việc dùng chung một bảng hash tính sẵn cho mọi người dùng và khiến hai tài khoản có cùng mật khẩu thường không có cùng verifier. Salt **không** ngăn thử đoán một tài khoản cụ thể nếu kẻ tấn công đã có cả hash lẫn salt.

Salt nên được sinh bằng **CSPRNG** (ví dụ `SecureRandom` của Java), đủ dài theo yêu cầu thư viện/tiêu chuẩn. Không lấy salt từ username, timestamp hoặc một hằng số dùng chung. Nếu thư viện password hashing tự sinh và lưu salt an toàn, ưu tiên dùng API đó.

### 3.3. Pepper là gì?

**Pepper** là một **bí mật bổ sung** do hệ thống quản lý ngoài cơ sở dữ liệu mật khẩu. Có thể tích hợp pepper qua một thiết kế HMAC hoặc cơ chế có khóa phù hợp, theo hướng dẫn của thư viện và kiến trúc an toàn.

| Tiêu chí | Salt | Pepper |
| --- | --- | --- |
| Phải bí mật? | **Không** | **Có** |
| Phạm vi | Thường riêng cho từng mật khẩu/bản ghi | Thường bí mật do ứng dụng hoặc miền bảo mật quản lý |
| Lưu ở đâu? | Cùng bản ghi password hash | Tách khỏi cơ sở dữ liệu, ví dụ secret store/KMS/HSM phù hợp |
| Mục đích | Chống dùng lại kết quả tính sẵn; tách kết quả giữa người dùng | Tăng khó khăn nếu chỉ database bị lộ nhưng pepper còn bí mật |
| Rotation | Không cần thay định kỳ chỉ vì thời gian | Phải có kế hoạch thay và xử lý dữ liệu phụ thuộc khi nghi lộ |

Pepper **không thay thế salt và thuật toán password hashing thích hợp**. Nếu dùng pepper chung, cần xác định ai có quyền đọc/dùng, cách kiểm toán, cách thay và cách xử lý khi KMS không sẵn sàng. Khi thay pepper, nhiều thiết kế **không thể cập nhật tất cả verifier ngoại tuyến** vì hệ thống không biết mật khẩu dạng rõ; có thể phải nâng cấp khi người dùng đăng nhập hoặc yêu cầu đặt lại mật khẩu. Không hard-code pepper trong source code.

### 3.4. Password hash khác HMAC và encryption thế nào?

| Cơ chế | Đầu vào bí mật | Công dụng điển hình | Có giải mã ngược được không? |
| --- | --- | --- | --- |
| **SHA-256 thông thường** | Không cần khóa | Băm dữ liệu tổng quát | Không; nhưng không chống đoán mật khẩu hiệu quả |
| **HMAC-SHA-256** | Secret key dùng tạo/kiểm tra MAC | Xác thực thông điệp, webhook, thành phần KDF | Không; không mặc nhiên là password hashing an toàn |
| **Argon2id/scrypt/bcrypt/PBKDF2 theo chính sách** | Password, salt và tham số | Lưu giá trị kiểm chứng mật khẩu | Không; xác minh bằng tính lại |
| **AES-GCM/ChaCha20-Poly1305** | Secret key mã hóa | Giữ bí mật dữ liệu có thể giải mã | **Có**, nếu còn đúng khóa và metadata |

Không mã hóa mật khẩu đăng nhập bằng AES rồi lưu khóa giải mã ở ứng dụng chỉ để sau này so sánh password. Luồng xác thực thông thường **không cần khôi phục mật khẩu gốc**. Đối với những giao thức thật sự cần truy xuất một bí mật khác, hãy thiết kế secret management riêng, không gọi đó là password hashing.

## 4. Những thuật toán password hashing nên biết

| Thuật toán | Đặc trưng | Lưu ý triển khai |
| --- | --- | --- |
| **Argon2id** | Có cấu hình bộ nhớ, số lượt và mức song song; kết hợp đặc tính kháng các kiểu tấn công phù hợp | Thường được ưu tiên cho hệ thống mới khi có thư viện an toàn và chính sách cho phép; điều chỉnh tham số theo năng lực máy |
| **scrypt** | Memory-hard; gây chi phí bộ nhớ và tính toán cho kẻ thử đoán | Chọn và đo các tham số `N`, `r`, `p` qua thư viện được duy trì |
| **bcrypt** | Thuật toán thích nghi dựa trên tham số cost, đã được dùng rộng rãi | Kiểm tra **giới hạn đầu vào** của bản triển khai (thường 72 byte) và cách xử lý Unicode; tránh cắt mật khẩu âm thầm |
| **PBKDF2-HMAC-SHA-256** | Lặp PRF nhiều lần; có trong nhiều môi trường chuẩn/JDK | Chọn số vòng theo chính sách, benchmark hiệu năng; không có tính memory-hard như Argon2id/scrypt |
| **SHA-256/SHA-512 đơn lẻ; MD5; SHA-1** | Hash tổng quát/thuật toán cũ, chạy nhanh hoặc không đáp ứng yêu cầu hiện đại | **Không dùng trực tiếp** để lưu password verifier cho hệ thống mới |

Không chọn tham số chỉ bằng cách sao chép một con số cố định từ ví dụ. Tham số cần dựa trên **hướng dẫn hiện hành, cấu hình máy chủ, tải xác thực, độ trễ chấp nhận được và bảo vệ chống DoS**. Kiểm tra mỗi lần tăng cost trên môi trường gần production, kể cả khi hệ thống nhiều người dùng đăng nhập đồng thời.

### Argon2id hoạt động ở mức giao diện ra sao?

Một thư viện Argon2id thường nhận mật khẩu, salt và các tham số bộ nhớ/thời gian/song song; sau đó trả về verifier:

~~~text
password + random salt
       |
       v
Argon2id(memoryCost, timeCost, parallelism)
       |
       v
encoded password verifier
~~~

Định dạng **PHC string** thường có cấu trúc tương tự:

~~~text
$argon2id$v=19$m=19456,t=2,p=1$<encoded-salt>$<encoded-hash>
~~~

Đây là **ví dụ cấu trúc lưu trữ và tham số minh họa**, không phải khuyến nghị cấu hình cho mọi hệ thống. Trường phiên bản/chi phí/salt/verifier cho phép thư viện biết cách kiểm tra một bản ghi cũ. Khi dùng thư viện thực tế, ưu tiên API `hash` và `verify` trực tiếp thay vì tự ghép/parse chuỗi PHC.

## 5. Luồng đăng ký và đăng nhập

### 5.1. Đăng ký hoặc thay mật khẩu

~~~mermaid
flowchart TD
    P[Người dùng cung cấp password qua TLS] --> V[Kiểm tra chính sách và độ dài đầu vào]
    V --> S[Tạo salt ngẫu nhiên mới]
    S --> H[Password hashing function với cost đã định]
    H --> R[Lưu algorithm + params + salt + verifier]
    R --> DB[(Kho tài khoản)]
    H -.-> X[Không lưu plaintext password]
~~~

Một ví dụ minh họa:

~~~text
accountId = "user-42"
password = [chỉ tồn tại trong yêu cầu và bộ nhớ cần thiết]
salt = CSPRNG(16 bytes)
verifier = Argon2id(password, salt, approvedParameters)

Lưu: accountId, algorithm, parameters, salt, verifier, updatedAt
Không lưu: plaintext password
~~~

Salt không phải bí mật nên có thể nằm trong trường của verifier; không cần đặt salt ở KMS. Nếu dùng pepper, vật liệu pepper phải được bảo vệ riêng và tích hợp theo thiết kế được phê duyệt.

### 5.2. Đăng nhập

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Dịch vụ xác thực
    participant DB as Cơ sở dữ liệu
    U->>A: username + password qua TLS
    A->>DB: Tìm bản ghi xác thực
    DB-->>A: Algorithm + params + salt + verifier
    A->>A: PasswordHash(password nhập, salt, params)
    A->>A: So sánh verifier an toàn
    A-->>U: Thành công / thất bại theo chính sách
    Note over A: Nếu cần: nâng cấp cost/algorithm sau khi xác minh thành công
~~~

Hệ thống **không cần giải mã** password hash. Nó thực hiện lại đúng thuật toán với salt và tham số đã lưu rồi so sánh kết quả; các thư viện password hashing thường cung cấp `verify(candidate, encodedHash)` để bao trọn xử lý này.

Sau khi xác minh thành công, hệ thống có thể phải thực hiện **MFA, kiểm soát rủi ro, kiểm tra trạng thái tài khoản và tạo session/token**. Password hashing chỉ là một thành phần của xác thực.

## 6. Ví dụ Java 17: lưu và kiểm tra verifier bằng PBKDF2

Để minh họa các bước mà không cần dependency bên ngoài, Java 17 có `SecretKeyFactory` với `PBKDF2WithHmacSHA256`. Ví dụ dưới đây lưu **algorithm, iteration count, salt và derived key** trong một bản ghi. Giá trị mật khẩu demo là giả; ứng dụng thực nên ưu tiên thư viện Argon2id khi phù hợp với yêu cầu và môi trường triển khai.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PasswordHashingDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int SALT_BYTES = 16;
    private static final int OUTPUT_BITS = 256;
    // Minh họa; benchmark và thay theo chính sách được cập nhật.
    private static final int CURRENT_ITERATIONS = 600_000;
    private static final int MAX_STORED_ITERATIONS = 5_000_000;

    private static byte[] derive(
            char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(
                password, salt, iterations, OUTPUT_BITS);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    // Bản ghi: thuật toán $ iterations $ salt(base64) $ verifier(base64)
    static String hashPassword(char[] password)
            throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] derived = derive(password, salt, CURRENT_ITERATIONS);
        try {
            return "pbkdf2-sha256$" + CURRENT_ITERATIONS + "$"
                    + Base64.getEncoder().encodeToString(salt) + "$"
                    + Base64.getEncoder().encodeToString(derived);
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    }

    static boolean verifyPassword(char[] candidate, String stored)
            throws GeneralSecurityException {
        String[] fields = stored.split("\\$", -1);
        if (fields.length != 4 || !"pbkdf2-sha256".equals(fields[0])) {
            return false;
        }

        final int iterations;
        final byte[] salt;
        final byte[] expected;
        try {
            iterations = Integer.parseInt(fields[1]);
            if (iterations < 1 || iterations > MAX_STORED_ITERATIONS) {
                return false; // Giới hạn chi phí do record lỗi/độc hại.
            }
            salt = Base64.getDecoder().decode(fields[2]);
            expected = Base64.getDecoder().decode(fields[3]);
            if (salt.length != SALT_BYTES
                    || expected.length != OUTPUT_BITS / 8) {
                return false;
            }
        } catch (IllegalArgumentException invalidRecord) {
            return false;
        }

        byte[] actual = derive(candidate, salt, iterations);
        try {
            return MessageDigest.isEqual(expected, actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "demo-secret-only".toCharArray();
        char[] wrongPassword = "wrong-password".toCharArray();
        try {
            String storedVerifier = hashPassword(password);
            System.out.println("Valid: "
                    + verifyPassword(password, storedVerifier));
            System.out.println("Invalid: "
                    + verifyPassword(wrongPassword, storedVerifier));
            // Chỉ lưu storedVerifier; không in password thật ra log.
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrongPassword, '\0');
        }
    }
}
~~~

**Giới hạn và điểm cần kiểm tra:**

- Đây là **ví dụ học thuật về PBKDF2**, không thay thế thư viện quản lý mật khẩu hoàn chỉnh. Ở production, ưu tiên API `hash/verify/needsRehash` của thư viện đã được đánh giá thay vì tự định nghĩa định dạng và bộ kiểm tra.
- `CURRENT_ITERATIONS` là **tham số minh họa**, phải được hiệu chỉnh bằng benchmark, chính sách và tư vấn bảo mật hiện hành. Giới hạn `MAX_STORED_ITERATIONS` cũng cần được tính theo khả năng chịu tải của hệ thống.
- Mỗi lần tạo verifier, `SecureRandom` sinh **salt mới**; khi verify phải dùng **salt và iteration count đã lưu**, không tự sinh salt khác.
- `MessageDigest.isEqual` giảm rủi ro so sánh byte làm lộ chênh lệch thời gian; hệ thống vẫn cần phòng ngừa **username enumeration, throttling, lockout phù hợp và DoS**. Không coi ví dụ này là bảo vệ hoàn chỉnh trước timing attack.
- `char[]` cho phép xóa một số bản sao đầu vào do mã nguồn kiểm soát, nhưng Java runtime hoặc thư viện có thể vẫn tạo bản sao; chuỗi literal trong `main` chỉ nhằm minh họa. Đầu vào thật nên đi qua API bảo mật, tránh ghi vào log, dump và tracing.
- Khi nhận mật khẩu Unicode, cần xác định chính sách **mã hóa ký tự, chuẩn hóa có chủ đích và tương thích giữa phiên bản thư viện**; tránh tự ý thay đổi giá trị người dùng đã đặt khiến họ không thể đăng nhập.
- Sau đăng nhập thành công, nếu policy hiện hành mạnh hơn `iterations` của bản ghi, có thể **rehash từ mật khẩu vừa nhập** bằng salt mới và tham số mới, rồi cập nhật verifier an toàn.

## 7. Những điều password hashing không làm

Password hashing **không cung cấp mọi thuộc tính mật mã** chỉ vì nó dùng thuật toán mạnh.

### 7.1. Không dùng để kiểm tra tính toàn vẹn tùy ý của thông điệp

Muốn một webhook có bằng chứng được tạo bởi bên chia sẻ khóa, hãy dùng **HMAC** với secret key riêng và quy trình chống replay. Password hashing được tối ưu cho dữ liệu entropy thấp và xác minh mật khẩu; không phải primitive ký/xác thực thông điệp thay HMAC.

### 7.2. Không thay chữ ký số

Một verifier PBKDF2 hoặc Argon2id không thể dùng như public key xác minh chữ ký của người gửi. Với chữ ký số, hãy sử dụng thuật toán **Ed25519, ECDSA hoặc RSA-PSS** phù hợp, đồng thời kiểm soát private key trong HSM/KMS và phân phối public key đáng tin.

### 7.3. Không dùng để mã hóa dữ liệu cần đọc lại

Password hash **không thể giải mã** để lấy password gốc. Nếu cần mã hóa số định danh, hồ sơ hay backup và sau đó giải mã, phải dùng **AEAD như AES-GCM/ChaCha20-Poly1305**, khóa đối xứng và mô hình DEK/KEK. KMS/HSM có thể quản lý các khóa đó, nhưng không phải là nơi lưu bản mã password thay cho password hashing.

### 7.4. Không tự chống đăng nhập thử hàng loạt

Kẻ tấn công có thể gửi nhiều yêu cầu đăng nhập **trực tuyến**. Cần giới hạn tần suất, theo dõi hoạt động bất thường, chính sách khóa tài khoản hợp lý, MFA khi phù hợp và xử lý phản hồi tránh tiết lộ tài khoản tồn tại. Thuật toán chậm làm tăng chi phí xác minh cho máy chủ nữa, nên cần **quản lý tài nguyên và phòng chống DoS**.

## 8. Liên hệ với key management, KMS/HSM và kiểm toán

Mật khẩu của người dùng và khóa mật mã của ứng dụng **khác nhau về chức năng**, nhưng cùng đòi hỏi quản trị vòng đời bí mật và chính sách truy cập rõ ràng.

| Đối tượng | Vòng đời | Nơi quản lý điển hình |
| --- | --- | --- |
| **Mật khẩu người dùng** | Đặt mới → xác minh → thay/đặt lại → vô hiệu khi cần | Password verifier được lưu trong kho danh tính; không lưu password rõ |
| **Salt** | Tạo mới với mỗi verifier → lưu cùng verifier → thay khi rehash | Kho dữ liệu xác thực; không cần KMS vì salt không bí mật |
| **Pepper (nếu dùng)** | Sinh và cấp phát bí mật → kiểm soát quyền → rotation/xử lý sự cố | Secret store, KMS/HSM hoặc cơ chế tương đương theo khả năng |
| **DEK/KEK** | Sinh → bọc/lưu/giải mã → xoay vòng → thu hồi/hủy | KMS/HSM + chính sách IAM, backup và audit |
| **Khóa HMAC/chữ ký số** | Sinh → cấp quyền ký/kiểm tra → rotation → thu hồi | KMS/HSM/keystore tùy yêu cầu; audit theo thao tác |

### 8.1. Dùng KMS/HSM cho pepper như thế nào?

Nếu chính sách sử dụng pepper, có thể đặt pepper trong secret manager và cấp quyền cho **dịch vụ xác thực**. Một số KMS/HSM cung cấp API HMAC, cho phép dịch vụ dùng khóa bí mật cho phép tính MAC mà không phải xuất khóa ra bộ nhớ ứng dụng. **Không phải mọi KMS đều hỗ trợ API HMAC hoặc Argon2id**, và việc đưa pepper vào quy trình cần có thiết kế đã được đánh giá để bảo đảm khả năng xác minh và phục hồi.

Tránh cho mọi service account quyền đọc pepper, khóa DEK và private key cùng lúc. Tách trách nhiệm quản trị và quyền dùng, ghi audit các thay đổi policy và truy cập bí mật, không ghi giá trị bí mật vào log.

### 8.2. Rotation không đồng nghĩa có thể tính lại verifier ngoại tuyến

Khi **nâng cấp password hashing** từ PBKDF2 cũ sang Argon2id, cơ sở dữ liệu chỉ có hash không thể trực tiếp suy ra password gốc để tính hash mới. Có thể:

1. Xác minh bằng thuật toán và tham số cũ khi người dùng đăng nhập.
2. Sau lần xác minh thành công, tính verifier mới từ password vừa cung cấp cùng salt mới.
3. Thay bản ghi một cách nhất quán và ghi nhận trạng thái nâng cấp.
4. Với tài khoản lâu không đăng nhập hoặc bị ảnh hưởng bởi sự cố, cân nhắc quy trình **đặt lại mật khẩu** theo chính sách.

Với **pepper bị lộ**, phải đánh giá đặc biệt vì chỉ đổi giá trị pepper không giúp xác minh các verifier đã được bảo vệ theo cách cũ. Có thể cần hỗ trợ giai đoạn chuyển đổi có kiểm soát, phát hành lại verifier khi đăng nhập, hoặc reset mật khẩu. Nếu database cũng bị lộ, cần coi những verifier cũ như đã bị thu thập, dù hệ thống đã đổi thuật toán sau đó.

### 8.3. Kiểm toán đúng thứ cần kiểm toán

Nên ghi được thời gian thay mật khẩu, kết quả xác minh, thay chính sách hashing, nâng cấp hash, đăng nhập bất thường, cấp quyền sử dụng pepper và hoạt động quản trị KMS. Tuyệt đối không log **password gốc, pepper, khóa bí mật, DEK hay token phiên**. Việc ghi cả bản password hash vào log cũng làm tăng bề mặt rò rỉ verifier không cần thiết.

Nếu cần tra cứu sự cố, dùng **account ID, request ID, phiên bản chính sách hashing và loại sự kiện**, kết hợp phân quyền bảo vệ audit log.

## 9. Các lỗi thực tế và cách khắc phục

| Lỗi | Hệ quả | Cách làm phù hợp |
| --- | --- | --- |
| Lưu `SHA-256(password)` không salt | Dễ so khớp mật khẩu chung và thử đoán rất nhanh | Dùng Argon2id/scrypt/bcrypt/PBKDF2 theo chính sách với salt riêng |
| Dùng một salt cố định cho mọi người | Người cùng mật khẩu vẫn có hash giống nhau; dễ tấn công quy mô lớn | Sinh salt riêng bằng CSPRNG |
| Dùng salt như bí mật cần giấu trong KMS | Phức tạp hóa hệ thống nhưng không giải quyết đúng bài toán | Lưu salt cùng verifier; nếu có pepper thì giữ riêng |
| Dùng bcrypt mà không xét giới hạn 72 byte | Phần cuối mật khẩu có thể không ảnh hưởng kết quả ở một số triển khai | Dùng API/thư viện phù hợp, kiểm tra giới hạn byte và chính sách đầu vào |
| Chọn cost cực nhỏ để đăng nhập nhanh | Hạ chi phí đoán mật khẩu ngoại tuyến | Chọn tham số theo tiêu chuẩn/chính sách và benchmark |
| Chọn cost quá cao mà không chống DoS | Tấn công đăng nhập hàng loạt làm quá tải CPU/RAM | Rate limit, giới hạn tài nguyên, cân bằng cost và khả năng phục vụ |
| “Mã hóa” mật khẩu bằng AES và lưu khóa cạnh DB | Mất khóa/DB có thể làm lộ mật khẩu dạng rõ | Lưu password verifier không thể giải ngược |
| Không lưu tên thuật toán/phiên bản/tham số | Không kiểm tra được verifier cũ sau nâng cấp | Lưu định dạng có metadata, có kế hoạch rehash |
| Log password hoặc pepper để debug | Bí mật lan sang hệ thống log, trace, backup | Cấm và lọc log dữ liệu xác thực |
| Tin rằng password hashing chống phishing/replay | Mật khẩu vẫn có thể bị lừa nhập hoặc đánh cắp phiên | Phòng vệ xác thực nhiều lớp, MFA/passkey khi phù hợp |
| Đổi pepper nhưng bỏ qua tài khoản cũ | Không xác minh được hoặc vẫn dùng thiết kế đã lộ | Kế hoạch version/rehash/reset và diễn tập khôi phục |
| Dùng một pepper/khóa bí mật cho mọi mục đích | Một sự cố ảnh hưởng nhiều hệ thống | Tách khóa theo mục đích và phạm vi dịch vụ |

## 10. Tình huống thực tế: nâng cấp hệ thống đăng nhập cũ

Một nền tảng đã từng lưu `SHA-256(password)` trong bảng `accounts`. Nhóm an ninh muốn chuyển sang **Argon2id** nhưng không có mật khẩu dạng rõ của người dùng và không được lưu chúng chỉ để di chuyển.

**Kế hoạch chuyển đổi hợp lý:**

1. Đánh giá rủi ro và xác định bản ghi đang dùng thuật toán nào. Nếu format cũ không có metadata, thiết lập quy tắc nhận diện đáng tin từ dữ liệu hệ thống.
2. Với tài khoản đăng nhập, xác minh password bằng cơ chế cũ **chỉ trong nhánh chuyển đổi có kiểm soát**. Nếu thành công, tạo salt mới, tạo Argon2id verifier theo chính sách và cập nhật bằng giao dịch thích hợp.
3. Với tài khoản không đăng nhập trong thời gian chuyển đổi, định nghĩa thời hạn và quy trình yêu cầu reset password khi cần.
4. Loại bỏ dần cơ chế SHA-256 cũ khi không còn phụ thuộc; ghi audit thay đổi mà không ghi password.
5. Nếu cơ sở dữ liệu hash cũ đã bị rò rỉ, đánh giá tác động và kích hoạt quy trình ứng phó sự cố, thay vì chỉ công bố rằng phiên bản mới đã an toàn.

**Nếu hệ thống còn dùng pepper:** lưu bí mật trong KMS/HSM hoặc secret store theo năng lực thực tế và quyền tối thiểu. Thiết kế luồng verify phải phân biệt phiên bản pepper để chuyển đổi có kiểm soát, nhưng không chấp nhận bí mật cũ vô hạn. Khi pepper bị lộ, có thể cần reset mật khẩu trên phạm vi chịu ảnh hưởng.

**Với dữ liệu cá nhân lưu cùng tài khoản:** password hash bảo vệ **xác thực**; thông tin cá nhân có thể cần thêm **AES-GCM/ChaCha20-Poly1305 và DEK được bọc bởi KEK trong KMS**. Một người dùng đăng nhập thành công vẫn phải qua kiểm tra quyền trước khi đọc dữ liệu tenant khác. Đây là hai lớp bảo vệ khác nhau.

## 11. Checklist triển khai

- [ ] Đã phân biệt thao tác “hash password”, giá trị “password hash” và quy trình “password hashing”?
- [ ] Không lưu mật khẩu bằng MD5, SHA-1, SHA-256/SHA-512 đơn lẻ hoặc mật mã đảo ngược?
- [ ] Dùng thư viện password hashing được duy trì, ưu tiên Argon2id khi phù hợp?
- [ ] Có salt ngẫu nhiên riêng, tham số chi phí được benchmark và lưu cùng verifier?
- [ ] Có xác minh bằng API chuyên dụng, so sánh an toàn và từ chối dữ liệu malformed?
- [ ] Có giới hạn đầu vào, chính sách Unicode và kiểm thử nhiều môi trường?
- [ ] Có rate limit, giám sát, xử lý lỗi đăng nhập tránh lộ thông tin và MFA khi phù hợp?
- [ ] Có phương án rehash khi chính sách/thuật toán thay đổi?
- [ ] Nếu dùng pepper, đã bảo vệ riêng, kiểm soát quyền, kiểm toán và có kế hoạch rotation/reset?
- [ ] Không có password, pepper, token và verifier không cần thiết trong log hoặc dump?
- [ ] Đã tách password verifier với khóa HMAC, khóa ký, DEK/KEK và quyền KMS?
- [ ] Có quy trình khôi phục tài khoản, ứng phó rò rỉ hash và sao lưu an toàn?

## 12. Câu hỏi tự kiểm tra

**1. “Hash password” và “password hashing” có phải hai thuật toán khác nhau không?**  
Không. Cách thứ nhất thường nói về thao tác băm mật khẩu, cách thứ hai thường nói về toàn bộ phương pháp lưu và xác minh mật khẩu. Quan trọng là thuật toán và quy trình được sử dụng có phù hợp để chống đoán mật khẩu hay không.

**2. Vì sao SHA-256 có tính chất mật mã tốt vẫn không phù hợp để lưu password hash trực tiếp?**  
Vì nó được thiết kế để tính rất nhanh; attacker có thể thử rất nhiều mật khẩu đoán được, nhất là sau khi có dữ liệu hash.

**3. Salt có phải lưu bí mật trong KMS không?**  
Không. Salt được lưu công khai cùng verifier. Cần sinh riêng, đủ ngẫu nhiên; pepper nếu dùng mới là bí mật phải quản lý ngoài database.

**4. Password hashing có giải mã để lấy mật khẩu cũ không?**  
Không. Hệ thống xác minh bằng cách tính lại từ password ứng viên, salt và tham số đã lưu rồi so sánh.

**5. Password hashing khác HMAC thế nào?**  
HMAC dùng secret key để xác thực thông điệp; password hashing được thiết kế để làm việc với password entropy thấp và cố tình đặt chi phí cho mỗi lần thử. HMAC trực tiếp trên password không thay thế việc thiết kế password hashing đầy đủ.

**6. Có thể nâng tất cả hash PBKDF2 cũ lên Argon2id mà không cần password người dùng không?**  
Thông thường không. Có thể rehash khi người dùng đăng nhập thành công hoặc yêu cầu đặt lại mật khẩu.

**7. Đổi pepper trong KMS có tự làm hash cũ an toàn sau khi dữ liệu đã lộ không?**  
Không. Cần biết kiến trúc sử dụng pepper, đánh giá phạm vi lộ và kế hoạch chuyển đổi hoặc reset; các bản ghi đã bị lấy trước đó vẫn là dữ liệu đã bị thu thập.

## Ghi nhớ

**“Hash password” thường mô tả hành động băm mật khẩu; “password hashing” là kỹ thuật và quy trình lưu, kiểm tra mật khẩu theo cách chống thử đoán hiệu quả.** Một hash SHA-256 thông thường không đủ để bảo vệ mật khẩu đăng nhập. Hãy dùng thuật toán chuyên dụng như **Argon2id** (hoặc lựa chọn phù hợp theo chính sách), salt ngẫu nhiên riêng, tham số chi phí được hiệu chỉnh, verifier có metadata, quy trình verify và rehash an toàn. Nếu dùng **pepper**, phải quản lý nó như secret key qua kiểm soát truy cập, KMS/HSM/secret store và chính sách rotation. Phân biệt rõ password hashing với **HMAC, chữ ký số và mã hóa dữ liệu bằng DEK/KEK** giúp hệ thống quản lý khóa và xác thực đúng mục đích, dễ kiểm toán và ứng phó sự cố hơn.
