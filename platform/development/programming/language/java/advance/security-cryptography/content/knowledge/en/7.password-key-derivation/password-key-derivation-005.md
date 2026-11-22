# 7.5 Tạo, lưu và kiểm tra bản ghi mật khẩu với đầy đủ tham số

Một ứng dụng Java không nên lưu mật khẩu dưới dạng văn bản thuần, mật khẩu được mã hóa có thể giải mã, hoặc kết quả băm nhanh như SHA-256 chạy một lần. Khi cơ sở dữ liệu bị lộ, đối thủ có thể thử rất nhiều mật khẩu ngoại tuyến. Mục tiêu của **password hashing / password-based key derivation** là tạo một **bộ xác minh mật khẩu** khó đoán lại bằng cách sử dụng thuật toán chuyên dụng có chi phí tính toán cao, **salt ngẫu nhiên riêng** và **các tham số được lưu đầy đủ**.

Bài này tập trung vào **vòng đời của một bản ghi mật khẩu**: tạo bản ghi khi đăng ký/đổi mật khẩu, lưu đúng định dạng, đọc và xác minh khi đăng nhập, phát hiện bản ghi cần nâng cấp, và xử lý dữ liệu/thiết lập bất hợp lệ. Ví dụ Java 17+ dùng **PBKDF2WithHmacSHA256** có sẵn trong JDK để biên dịch độc lập. Khi hệ thống có thư viện được duy trì phù hợp, **Argon2id** thường là lựa chọn ưu tiên cho mật khẩu vì có cơ chế chi phí bộ nhớ; phần sau sẽ giải thích đầy đủ tham số tương ứng.

## 1. Bản ghi mật khẩu là gì?

Một bản ghi mật khẩu là **dữ liệu cần thiết để xác minh mật khẩu đã nhập mà không lưu mật khẩu gốc**. Nó không chỉ là một chuỗi hash. Một thiết kế thực tế cần nhận diện chính xác thuật toán, tham số, salt và giá trị dẫn xuất; có thể cần version để đọc các bản ghi cũ sau khi nâng cấp.

~~~text
Khi tạo tài khoản / thay đổi mật khẩu:
    password + salt ngẫu nhiên + thuật toán + tham số chi phí
                            |
                            v
                 KDF / password hasher
                            |
                            v
            derived verifier + metadata
                            |
                            v
       lưu PASSWORD_RECORD vào database

Khi đăng nhập:
    password người dùng nhập + metadata/salt từ PASSWORD_RECORD
                            |
                            v
              chạy cùng KDF và tham số
                            |
                            v
         so sánh bộ xác minh một cách phù hợp
                            |
                 đúng / sai mật khẩu
~~~

Salt **không cần bí mật** và thường lưu cùng bản ghi. Giá trị dẫn xuất cũng không phải mật khẩu gốc, nhưng là dữ liệu bảo mật nhạy cảm: người đọc được database có thể thực hiện đoán mật khẩu ngoại tuyến. Cần kiểm soát quyền truy cập, sao lưu và xuất dữ liệu.

### Password hashing khác các cơ chế khác thế nào?

| Cơ chế | Mục đích | Dùng lưu mật khẩu đăng nhập? |
| --- | --- | --- |
| SHA-256 một lần | Tính dấu vân tay dữ liệu nhanh | **Không.** Tốc độ cao giúp kẻ tấn công thử hàng loạt mật khẩu. |
| HMAC-SHA256 một lần | Xác thực thông điệp bằng khóa bí mật | **Không tự đủ.** Chưa có chi phí chuyên dụng để chống đoán ngoại tuyến. |
| AES-GCM | Mã hóa dữ liệu có thể giải mã bằng khóa | **Không phải cơ chế chính cho password verifier.** Việc lấy lại mật khẩu gốc không cần thiết. |
| PBKDF2-HMAC-SHA256 | Dẫn xuất có nhiều vòng lặp, salt | **Có thể dùng** với cấu hình chi phí được hiệu chỉnh và các giới hạn thích hợp. |
| Argon2id | Password hashing có chi phí CPU và bộ nhớ cấu hình được | **Ưu tiên khi có thư viện phù hợp**, định cấu hình và kiểm thử đúng. |
| bcrypt / scrypt | Thuật toán password hashing chuyên dụng | Có thể dùng khi phù hợp yêu cầu; cần hiểu giới hạn độ dài/encoding và tham số. |

**Không “giải mã” password hash khi đăng nhập.** Server lặp lại phép dẫn xuất với mật khẩu người dùng vừa nhập rồi kiểm tra kết quả.

## 2. Mối đe dọa và giới hạn bảo vệ

Giả sử database gồm tên tài khoản và password record bị sao chép. Đối thủ có thể chọn mật khẩu thử, lấy salt/params từ record và tính hash ngoại tuyến để dò. **Mỗi lần thử càng tốn CPU/bộ nhớ, việc dò càng đắt**, nhưng không có thuật toán nào làm một mật khẩu quá phổ biến trở thành bí mật không thể đoán.

Những biện pháp cần có cùng lúc:

1. Password hasher đủ mạnh, work factor hợp lý, salt ngẫu nhiên riêng cho mỗi bản ghi.
2. Chính sách mật khẩu và quy trình đăng nhập phù hợp; tránh mật khẩu phổ biến/bị lộ và hỗ trợ MFA khi cần.
3. Rate limit, phát hiện credential stuffing và khóa/chờ có kiểm soát **ở bước đăng nhập trực tuyến**.
4. Giới hạn quyền đọc password record, mã hóa bản sao lưu khi cần và giữ bí mật vận hành.
5. Quy trình reset mật khẩu, đổi mật khẩu, nâng cấp hash và quản lý phiên an toàn.

**Rate limit không làm chậm việc tấn công ngoại tuyến trên database đã bị lấy cắp.** Ngược lại, một KDF rất chậm không tự bảo vệ endpoint khỏi request flood; phải hiệu chỉnh công suất đăng nhập và giới hạn concurrency.

## 3. Một bản ghi đầy đủ cần những tham số nào?

Không được phụ thuộc vào giá trị mặc định trong code đang chạy để giải thích một bản ghi tạo từ phiên bản cũ. Các tham số thiết yếu cần đi cùng bản ghi, hoặc được tham chiếu một cách ổn định qua **format version**.

| Thuộc tính | Ý nghĩa | Ví dụ PBKDF2 / Argon2id |
| --- | --- | --- |
| **Format version** | Cách parse bản ghi, chính sách encoding, phép tiền xử lý, sơ đồ thuật toán | p1 hoặc profile Argon2id có version xác định. |
| **Algorithm** | Thuật toán password hashing/KDF chính xác | PBKDF2WithHmacSHA256 / Argon2id. |
| **PRF / hash nội bộ** | Cơ chế bên trong KDF khi thuật toán yêu cầu | HMAC-SHA-256 với PBKDF2; không tự suy từ tên “PBKDF2”. |
| **Salt** | Dãy byte ngẫu nhiên độc lập, thường ≥16 byte cho thiết kế mới | 16 byte sinh bằng SecureRandom, lưu dạng Base64url. |
| **Work factor** | Chi phí theo thuật toán | PBKDF2: iteration count; Argon2id: memory m, passes t, parallelism p. |
| **Derived output length** | Số byte/bit của verifier sau dẫn xuất | 256 bit = 32 byte trong ví dụ PBKDF2. |
| **Hash/verifier** | Giá trị đã dẫn xuất được lưu để so sánh | Binary bytes biểu diễn bằng Base64/PHC format. |
| **Định dạng biểu diễn** | Quy tắc thứ tự field, delimiter, Base64, version và parser | Chuỗi có phân tách hoặc cấu trúc JSON/columns rõ ràng. |
| **Pepper key version** (nếu dùng) | Chỉ định bí mật bổ sung nằm ngoài database, để vận hành rotation | ID tham chiếu khóa, **không lưu chính pepper** trong password record. |

Salt, iteration count, bộ băm và hash length **không phải password** và có thể lưu cùng bản ghi. Không lưu hoặc log mật khẩu plaintext; cũng không gộp pepper secret vào record.

### 3.1. Ví dụ schema PBKDF2 của ứng dụng

Trong bài dùng định dạng do ứng dụng quy định:

~~~text
p1$PBKDF2WithHmacSHA256$600000$256$SALT_BASE64URL$VERIFIER_BASE64URL
 |              |              |    |          |                 |
version      algorithm      rounds bits     salt bytes      derived bytes
~~~

Dòng trên là **sơ đồ các trường**, không phải giá trị record đã được tính hợp lệ. Khi chạy Java demo, SALT_BASE64URL và VERIFIER_BASE64URL được thay bằng giá trị Base64url thực tế, khác nhau mỗi lần tạo record.

Ý nghĩa:

- **p1:** schema phiên bản 1. Parser phải biết p1 dùng thuật toán nào, cách chuyển ký tự mật khẩu thành input của KDF, độ dài salt và output, các dạng encoding được cho phép.
- **PBKDF2WithHmacSHA256:** tên thuật toán chuẩn được JDK sử dụng; HMAC-SHA256 là hàm PRF bên trong PBKDF2.
- **600000:** 600.000 vòng lặp, thuộc record cụ thể. Không lấy 600.000 từ biến “giá trị hiện tại” khi xác minh record cũ có 200.000 vòng.
- **256:** số **bit** đầu ra; 256 bit = 32 byte. Không nhầm số bit này với entropy của mật khẩu.
- **Salt:** 16 byte sinh ngẫu nhiên cho lần tạo record.
- **Verifier:** 32 byte dẫn xuất từ mật khẩu + salt + các tham số, mã hóa Base64url để lưu trong một trường text.

**Không lưu chuỗi String password trong record.** Một bản ghi mới phải có salt mới ngay cả khi người dùng nhập lại đúng cùng mật khẩu cũ.

### 3.2. Các lựa chọn lưu trữ

Có thể lưu toàn bộ record đã version hóa vào một cột VARCHAR/TEXT có giới hạn đủ lớn, hoặc tách các field (algorithm, iteration_count, salt, verifier, version) thành những cột typed trong database. Cả hai cách đều hợp lệ nếu:

- Có **hợp đồng định dạng** ổn định, kiểm tra length/encoding và không cắt mất ký tự Base64.
- Thao tác lưu khi đăng ký/đổi password là **atomic**, tránh trộn salt mới với verifier cũ.
- Khóa duy nhất của tài khoản và quyền truy cập database được kiểm soát.
- Có kế hoạch đọc record cũ khi nâng cấp algorithm, version, work factor.
- Không dùng hash làm token đăng nhập hoặc public identifier của tài khoản.

Độ dài của trường Base64 theo **ký tự**, còn chiều dài của salt/verifier theo **byte**. Ví dụ 16 byte salt mã hóa Base64url không padding thường dài 22 ký tự, 32 byte verifier thường dài 43 ký tự. Parser phải decode rồi kiểm tra chiều dài byte thực tế.

## 4. Chọn thuật toán và tham số: không mặc định cho mọi môi trường

OWASP Password Storage Cheat Sheet khuyến nghị Argon2id khi có hỗ trợ phù hợp và gợi ý cấu hình tối thiểu có ý nghĩa như **m=19456 KiB (19 MiB), t=2, p=1**. Argon2id có các tham số **memory (m)**, **passes (t)** và **parallelism (p)**; chúng cần đo hiệu năng trên môi trường thật. Tăng p không có nghĩa nhân số lần lặp và không tự nhân lượng RAM m.

Với PBKDF2-HMAC-SHA256, OWASP nêu **600.000 iterations** trong hướng dẫn liên quan FIPS; ví dụ Java sử dụng mốc này và vẫn phải benchmark theo CPU, lưu lượng đăng nhập, giới hạn timeout và nhu cầu tuân thủ thực tế. **Tham số bảo mật là quyết định có phiên bản**, không phải một hằng số bất biến mãi mãi.

| Thuật toán | Các tham số phải giữ | Cách đánh giá |
| --- | --- | --- |
| PBKDF2-HMAC-SHA256 | PRF, iterations, salt, output length, encoding | Benchmark thời gian verify trên runtime và phần cứng triển khai; kiểm soát giới hạn iteration trong parser. |
| Argon2id | variant, version (thường v=19), m KiB, t, p, salt, output length | Benchmark RAM và CPU mỗi lần verify, tổng concurrency, memory exhaustion và các limits. |
| scrypt | N, r, p, salt, output length | Đánh giá bộ nhớ, CPU và giới hạn cho mỗi request. |
| bcrypt | variant/prefix, cost, salt và chuỗi hash theo format thư viện | Kiểm tra giới hạn byte của password, cách xử lý encoding và khả năng nâng cấp cost. |

Ưu tiên thư viện password-hashing được duy trì, có format/encoder/verify API hoàn chỉnh. Không tự thiết kế phép băm bằng cách gọi SHA-256 trong vòng lặp thủ công. Thuật toán password hashing cần được triển khai và đánh giá theo chuẩn, không lắp từ các primitive tùy ý.

## 5. Tạo record mới khi đăng ký hoặc đổi mật khẩu

Một luồng tạo record nên làm theo thứ tự sau:

1. Nhận mật khẩu thông qua kênh HTTPS, kiểm tra chính sách đăng ký và giới hạn kích thước hợp lý để tránh tiêu tốn tài nguyên quá mức.
2. Nếu có quy tắc **Unicode normalization**, phải định nghĩa rõ (ví dụ NFC), áp dụng **nhất quán** lúc tạo và lúc xác minh, và gắn với format version. Không tự trim/lowercase mật khẩu nếu không có chính sách rõ.
3. Chọn **thuật toán/profile hiện tại** từ cấu hình server, không để browser chỉ định thuật toán hoặc giảm work factor.
4. Sinh **salt mới bằng SecureRandom**, độc lập với user ID, email, timestamp hoặc password. Salt nên riêng cho mỗi lần đổi password.
5. Thực thi password hasher với salt và **đầy đủ tham số profile**; nhận verifier bytes.
6. Đóng gói version, algorithm, iterations (hoặc m/t/p), salt, output length, verifier và key version nếu dùng pepper.
7. Lưu **atomic** cùng account record theo quyền của ứng dụng; không lưu mật khẩu plaintext hoặc derived key trong log.
8. Giới hạn thời gian tồn tại của password và verifier tạm trong bộ nhớ khi có thể; xóa dữ liệu trong char[]/byte[] do ứng dụng sở hữu khi không cần nữa.

Salt khác nhau khiến hai người có cùng password thường có verifier khác nhau, đồng thời ngăn sử dụng trực tiếp bảng hash tiền tính chung. **Salt không thay thế work factor**, không cần được giấu, và không giống pepper.

## 6. Xác minh record: dùng chính tham số đã lưu

Khi đăng nhập, **không được** chỉ gọi KDF với tham số hiện tại của application rồi so sánh. Cần lấy tham số từ record để xác minh đúng bản cũ.

~~~text
Tài khoản + password ứng viên
             |
             v
Tìm password record theo tài khoản
             |
             v
Parse version + algorithm + params + salt + verifier
             |
      kiểm tra allowlist, bounds, length
             |
        sai -> từ chối
             |
             v
KDF(candidate, storedSalt, storedParams)
             |
             v
So sánh bytes với storedVerifier
        |                |
      khớp            không khớp
        |                |
        v                v
Kiểm tra nâng cấp      từ chối
        |
        v
Xác thực + quản lý phiên theo chính sách
~~~

Các điểm quan trọng:

- **Chọn thuật toán theo allowlist và version đáng tin**, không để một chuỗi lưu trữ hoặc người dùng tùy ý kích hoạt bất kỳ thuật toán/giá trị cost nào.
- **Đọc salt đã lưu**, không sinh salt mới khi xác minh; salt mới sẽ tạo output khác.
- **Dùng iterations/m/t/p của record**, không dùng work factor mới cho record cũ.
- **Kiểm tra độ dài và upper bound** trước khi chạy KDF. Một record bị sửa thành “999.999.999 iterations” có thể khiến endpoint treo hoặc bị từ chối phục vụ.
- **So sánh toàn bộ derived verifier** với phép so sánh phù hợp như MessageDigest.isEqual cho mảng cố định; không dùng prefix hay so sánh chuỗi có thể lộ thông tin thời gian.
- **Xác minh đúng mới được đánh dấu authenticated**; công việc rehash và phát hành session phải đứng sau bước này.
- **Phân biệt lỗi record hỏng và sai mật khẩu trong log nội bộ**, nhưng phản hồi bên ngoài tránh tiết lộ tài khoản có tồn tại hay nguyên nhân mật mã nhạy cảm.

MessageDigest.isEqual chỉ hạn chế sự phụ thuộc timing vào **nội dung bytes** trong điều kiện thích hợp; nó không làm toàn bộ endpoint constant-time vì lookup, decode, KDF, network và xử lý lỗi vẫn có thời gian khác nhau.

## 7. Java 17+: tạo, lưu dạng chuỗi, xác minh và kiểm tra cần rehash

Ví dụ độc lập dưới đây dùng **SecretKeyFactory**, **PBEKeySpec**, **SecureRandom**, Base64url và **MessageDigest.isEqual**. Nó tạo hai record với tham số khác nhau, xác minh password đúng/sai, xác định record cũ cần rehash và kiểm tra giới hạn iterations trước khi thực thi KDF.

Với mục đích minh họa, profile **p1** chỉ hỗ trợ PBKDF2-HMAC-SHA256, salt đúng 16 byte, verifier đúng 32 byte và iterations trong khoảng **100.000–2.000.000**, trong đó **600.000** là cost hiện tại. Khoảng này là **quy tắc parse của bản demo**, không có nghĩa 100.000 là cấu hình nên dùng để tạo record mới; đường tạo record công khai dùng 600.000. Record lịch sử được tạo ở 200.000 chỉ để minh họa migration.

Lưu file **PasswordRecordDemo.java**:

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PasswordRecordDemo {
    private static final String VERSION = "p1";
    private static final String ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final int CURRENT_ITERATIONS = 600_000;
    private static final int MIN_ALLOWED_ITERATIONS = 100_000;
    private static final int MAX_ALLOWED_ITERATIONS = 2_000_000;
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;
    private static final int KEY_BYTES = KEY_BITS / 8;
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DECODER = Base64.getUrlDecoder();

    private record Parsed(int iterations, byte[] salt, byte[] expected) {}

    public static String create(char[] password) throws GeneralSecurityException {
        return createAtCost(password, CURRENT_ITERATIONS);
    }

    private static String createAtCost(char[] password, int iterations)
            throws GeneralSecurityException {
        requirePassword(password);
        checkIterations(iterations);
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] derived = derive(password, salt, iterations);
        try {
            return String.join("$", VERSION, ALGORITHM,
                    Integer.toString(iterations), Integer.toString(KEY_BITS),
                    ENCODER.encodeToString(salt), ENCODER.encodeToString(derived));
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    }

    public static boolean verify(char[] candidate, String stored)
            throws GeneralSecurityException {
        requirePassword(candidate);
        Parsed p = parse(stored);
        byte[] actual = derive(candidate, p.salt(), p.iterations());
        try {
            return MessageDigest.isEqual(p.expected(), actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    public static boolean needsRehash(String stored) {
        Parsed p = parse(stored);
        return p.iterations() < CURRENT_ITERATIONS;
    }

    private static byte[] derive(char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, KEY_BITS);
        try {
            SecretKeyFactory factory = SecretKeyFactory.getInstance(ALGORITHM);
            return factory.generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    private static Parsed parse(String stored) {
        if (stored == null || stored.length() > 256) {
            throw new IllegalArgumentException("Malformed password record");
        }
        String[] parts = stored.split("\\$", -1);
        if (parts.length != 6
                || !VERSION.equals(parts[0])
                || !ALGORITHM.equals(parts[1])
                || !Integer.toString(KEY_BITS).equals(parts[3])) {
            throw new IllegalArgumentException("Unsupported password record");
        }
        final int iterations;
        try {
            iterations = Integer.parseInt(parts[2]);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Bad iteration count", e);
        }
        checkIterations(iterations);
        final byte[] salt;
        final byte[] expected;
        try {
            salt = DECODER.decode(parts[4]);
            expected = DECODER.decode(parts[5]);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("Bad Base64url", e);
        }
        if (salt.length != SALT_BYTES || expected.length != KEY_BYTES
                || !ENCODER.encodeToString(salt).equals(parts[4])
                || !ENCODER.encodeToString(expected).equals(parts[5])) {
            throw new IllegalArgumentException("Invalid salt or verifier encoding");
        }
        return new Parsed(iterations, salt, expected);
    }

    private static void checkIterations(int count) {
        if (count < MIN_ALLOWED_ITERATIONS || count > MAX_ALLOWED_ITERATIONS) {
            throw new IllegalArgumentException("Iteration count out of policy");
        }
    }

    private static void requirePassword(char[] chars) {
        if (chars == null || chars.length == 0) {
            throw new IllegalArgumentException("Missing password");
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "Một mật khẩu ví dụ dài".toCharArray();
        char[] wrong = "Một mật khẩu khác".toCharArray();
        try {
            String saved = create(password);
            System.out.println("Số trường bản ghi: " + saved.split("\\$", -1).length);
            System.out.println("Mật khẩu đúng: " + verify(password, saved));
            System.out.println("Mật khẩu sai: " + verify(wrong, saved));
            System.out.println("Bản ghi hiện tại cần nâng cấp: " + needsRehash(saved));

            String old = createAtCost(password, 200_000);
            System.out.println("Bản ghi cũ xác minh được: " + verify(password, old));
            System.out.println("Bản ghi cũ cần nâng cấp: " + needsRehash(old));

            String[] fields = saved.split("\\$", -1);
            fields[2] = "999999999";
            boolean rejected = false;
            try {
                verify(password, String.join("$", fields));
            } catch (IllegalArgumentException expected) {
                rejected = true;
            }
            System.out.println("Tham số vượt giới hạn bị từ chối: " + rejected);
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
~~~

Biên dịch với JDK 17+ và chạy:

~~~bash
javac --release 17 -encoding UTF-8 PasswordRecordDemo.java
java PasswordRecordDemo
~~~

Đầu ra đáng tin cậy:

~~~text
Số trường bản ghi: 6
Mật khẩu đúng: true
Mật khẩu sai: false
Bản ghi hiện tại cần nâng cấp: false
Bản ghi cũ xác minh được: true
Bản ghi cũ cần nâng cấp: true
Tham số vượt giới hạn bị từ chối: true
~~~

Không in giá trị salt/hash thực tế nên stdout vẫn giống nhau về mặt kiểm tra dù mỗi lần chạy tạo salt và verifier khác nhau. Bản ghi có **sáu trường**: version, algorithm, iterations, output bits, salt Base64url, derived bytes Base64url. Trong demo, password được đặt bằng string literal để có chương trình độc lập; ứng dụng thật nhận từ request và nên tránh tạo thêm bản sao String không cần thiết.

### Giải thích các thành phần Java

- **SecureRandom** sinh 16 byte salt mới ở createAtCost. Không dùng java.util.Random, currentTimeMillis hoặc email làm salt.
- **PBEKeySpec(password, salt, iterations, KEY_BITS)** đóng gói đúng input của phép PBKDF2. **KEY_BITS là số bit output**, không phải số iteration.
- **SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")** lấy implementation KDF từ provider; **generateSecret(spec).getEncoded()** lấy 32 byte dẫn xuất trong provider phù hợp với ví dụ.
- **PBEKeySpec.clearPassword()** xóa bản sao char[] nằm trong key spec. Caller chịu trách nhiệm xóa char[] input khi dùng xong; đó là lý do main dùng **Arrays.fill**. Việc xóa không bảo đảm mọi bản sao trong JVM/HTTP stack đều biến mất tức thì.
- **Base64url không padding** chỉ là định dạng text để lưu byte; không mã hóa bí mật và không tăng độ mạnh của mật khẩu.
- **parse()** kiểm tra đúng version, tên thuật toán, output bits, số trường, iteration bounds, salt/verifier byte length và Base64url canonical trước khi chạy phép tính tốn kém.
- **MessageDigest.isEqual** so sánh đủ 32 byte verifier. Vì parser cố định output size, không có logic “khớp n byte đầu”.
- **needsRehash()** của demo kiểm tra iteration count cũ so với cấu hình mới. Khi triển khai nhiều thuật toán/phiên bản, cần mở rộng hàm này để xét cả algorithm, params, output length, salt policy và format version.

**Ranh giới ví dụ:** chương trình không triển khai HTTP endpoint, DB transaction, MFA, pepper, account lockout, nhiều scheme lịch sử hoặc unicode normalization tùy chọn. Những phần đó là trách nhiệm của dịch vụ xác thực và được giải thích bên dưới.

### Vì sao parse cần kiểm tra bounds?

Một record có iterations 2.000.000.000, salt decode dài hàng megabyte hoặc verifier không đúng 32 byte có thể làm cạn CPU/RAM nếu được đưa thẳng vào KDF. Parser kiểm tra **độ dài chuỗi**, **algorithm/version allowlist**, **iteration minimum/maximum**, **kích thước bytes đã giải mã** trước khi thực hiện công việc.

Giới hạn MAX_ALLOWED_ITERATIONS trong code là **chính sách triển khai cần cập nhật có kiểm soát**. Không tự thay bằng giá trị từ user request. Nếu hệ thống có record cũ với tham số ngoài policy, cần một đường migration được thiết kế riêng, không bỏ kiểm tra hoặc tự sử dụng bất kỳ giá trị tùy ý nào.

## 8. Kết nối ví dụ với database

Một service có thể lưu record như sau:

~~~text
users
----------------------------------------------
id               BIGINT / UUID
email            VARCHAR UNIQUE
password_record  VARCHAR / TEXT
password_changed_at TIMESTAMP
record_version   INTEGER (nếu cần optimistic locking)
----------------------------------------------
~~~

**password_record** chứa đủ metadata để kiểm tra. Cột **password_changed_at** phục vụ quản lý phiên/lịch sử vận hành theo chính sách, không được dùng làm salt. **record_version** là dữ liệu điều phối cập nhật DB và khác hoàn toàn với format version p1 trong nội dung password record.

### Đăng ký

1. Validate account, chính sách mật khẩu và xác thực email theo ứng dụng.
2. Gọi create(password char[]) để sinh salt và derived verifier.
3. Lưu record mới cùng user trong transaction; ghi audit event không chứa password, verifier hay bí mật.
4. Xóa password buffer do mình sở hữu trong finally; không đưa vào access log/exception.

### Đăng nhập

1. Tìm user theo identity, áp dụng rate limit và cơ chế chống dò mật khẩu.
2. Nếu có record hợp lệ, gọi verify(candidate, storedRecord).
3. Khi verify trả true, tiếp tục các bước kiểm soát trạng thái tài khoản, MFA khi cần, tạo session và cập nhật thông tin đăng nhập phù hợp.
4. Nếu record đã yếu theo policy, tạo record mới **với salt mới và tham số hiện tại** sau khi xác minh thành công; cập nhật database bằng điều kiện version/compare-and-swap.
5. Nếu verify sai hoặc record lỗi, không phát session; phản hồi chung để hạn chế user enumeration.

### Đổi và đặt lại mật khẩu

Không dùng thao tác “decode hash thành password cũ”. Sau khi thực hiện xác thực/ủy quyền cho luồng đổi hoặc reset, tạo **record hoàn toàn mới** với salt, params và verifier mới, cập nhật atomic, và thu hồi session/token theo chính sách. Không tái sử dụng record cũ hay salt cũ chỉ vì người dùng nhập cùng một mật khẩu.

## 9. Từ PBKDF2 sang Argon2id: record có m, t, p

Nếu dùng Argon2id, ngoài algorithm và salt/hash, bản ghi phải chứa **version thuật toán, memory cost, time cost, parallelism và output length**. Một chuẩn biểu diễn thường gặp là **PHC string format**, với cấu trúc khái niệm:

~~~text
$argon2id$v=19$m=19456,t=2,p=1$<salt đã mã hóa>$<hash đã mã hóa>
~~~

Đây là mô tả format để nhận diện trường, **không phải một bản hash hợp lệ để copy dùng xác minh**. Với Argon2id:

- **argon2id** xác định biến thể phù hợp cho password hashing.
- **v=19** thể hiện version thuật toán Argon2 (decimal 19 tương ứng version 0x13).
- **m=19456** là tổng bộ nhớ dùng trong phép tính, **đơn vị KiB**, tương đương 19 MiB.
- **t=2** là số lượt/passes, **không phải 2 giây**.
- **p=1** là số lanes/parallelism; không có nghĩa mỗi lane nhận m KiB riêng, vì m là tổng.
- **salt và hash** phải được lưu đủ bytes; trong PHC format thư viện thường mã hóa bằng Base64 không padding theo quy ước của format.
- **Output length** có thể được xác định từ hash bytes trong format; vẫn phải được profile/library xác định và validate.

Java 17 không có engine SecretKeyFactory Argon2id mặc định được bảo đảm trên mọi JDK. Dùng thư viện password hashing đáng tin, được cập nhật và cung cấp hàm **hash(password, params)** / **verify(encoded, password)** và parse PHC. Đừng tự viết Argon2id từ các phép SHA/bitwise.

**Migration giữa thuật toán:** khi chuyển PBKDF2 sang Argon2id, vẫn giữ khả năng verify các record PBKDF2 hợp lệ được phép; sau login thành công, hash lại bằng Argon2id với salt mới rồi thay record atomically. Không thể chuyển hash PBKDF2 thành hash Argon2id **mà không biết mật khẩu**; bản hash cũ không phải password input thích hợp cho hash mới.

## 10. Nâng cấp tham số và schema mà không mất khả năng đăng nhập

Password hashing cost cần có đường nâng cấp theo thời gian. Khi CPU/GPU và khả năng tấn công tăng, profile hiện tại có thể trở nên yếu. **Record mang đủ tham số** cho phép xác minh bản cũ rồi **rehash on successful login**.

~~~text
Người dùng nhập password
        |
        v
Verify với algorithm + params + salt của record đang lưu
        |
     thành công?
      /       \
    Không      Có
     |         |
    Reject     v
        Record có đạt profile hiện hành?
                /         \
              Có           Không
              |              |
        Auth session    Tạo salt mới + hash theo profile mới
                               |
                               v
                    Cập nhật atomic nếu record
                    cũ vẫn là bản đang lưu
                               |
                               v
                       Auth session
~~~

### Quy tắc migration quan trọng

1. **Chỉ nâng cấp sau khi verify đúng mật khẩu gốc**; đừng biến stored hash thành mật khẩu mới.
2. **Profile mới phải được cấu hình phía server**, không tin tham số do client gửi.
3. **Tạo salt mới**, tính record mới hoàn chỉnh; không sửa riêng field iterations và giữ nguyên verifier.
4. **Tránh race:** hai login song song hoặc login cùng password reset có thể tranh cập nhật. Dùng optimistic lock/compare-and-swap dựa trên record version hoặc hash của giá trị cũ theo chính sách DB, tránh ghi đè record mới hơn.
5. **Không hạ cấp:** nếu record đã có cost/algorithm mạnh hơn profile trên node cũ, không ghi lại theo profile thấp hơn.
6. **Đối với account lâu không đăng nhập**, migration on-login không cập nhật được ngay; có thể cần kế hoạch truyền thông/đặt lại mật khẩu phù hợp.
7. **Giữ bộ verifier cũ có thời hạn** khi đang chuyển đổi nếu policy cho phép, ghi nhận loại algorithm/params hỗ trợ; không giữ legacy format vô hạn mà không có quyết định an toàn.

### Khi cần đổi normalization hoặc encoding

Quy tắc xử lý mật khẩu ký tự Unicode là **một phần của hợp đồng format**. Chuyển từ “không chuẩn hóa” sang “Unicode NFC” có thể làm thay đổi input bytes dẫn xuất. Không đổi cách xử lý trong lúc xác minh record cũ rồi xem tất cả record cũ là sai. Gắn version với normalization policy và migrate khi có password gốc lúc đăng nhập.

Với PBKDF2 qua Java PBEKeySpec, cách provider diễn giải char[] thành byte input cần được kiểm thử trong môi trường triển khai, nhất là password có dấu tiếng Việt, ký tự ngoài ASCII và dấu kết hợp. Cần thống nhất encoding/normalization trong giao thức; không tự chuyển password thành bytes rồi thay thế bằng String không rõ charset hoặc trim.

## 11. Salt, pepper và những bí mật nằm ở đâu?

### 11.1. Salt

Salt là **giá trị ngẫu nhiên không bí mật**, giúp các mật khẩu bằng nhau có hash khác nhau và cản trở bảng tra cứu tính trước. Salt phải:

- Được sinh bằng **SecureRandom** hoặc RNG mật mã tương đương.
- Mới cho **mỗi bản ghi/mỗi lần đổi mật khẩu**, không dùng một salt chung toàn ứng dụng.
- Đủ dài để xác suất trùng rất nhỏ; ví dụ 16 byte (128 bit).
- Lưu kèm record để sử dụng lại khi verify; không thay đổi salt lúc kiểm tra.

Không dùng user ID, email, username hay thời gian như nguồn salt chính; chúng thường dự đoán được, thiếu tính ngẫu nhiên và có thể trùng.

### 11.2. Pepper

Pepper là **bí mật bổ sung** được quản lý **tách khỏi cơ sở dữ liệu password record**, ví dụ trong KMS/HSM hoặc secret manager được phân quyền. Nó giúp tăng defense in depth khi chỉ database bị lộ nhưng hệ thống quản lý pepper còn an toàn.

- **Không lưu pepper trong password_record**, không commit source code hoặc ghi log.
- Nếu dùng pepper, cần thiết kế chính xác vị trí kết hợp với password hash (chẳng hạn post-hash HMAC theo chính sách được đánh giá); đừng tự nối chuỗi một cách mơ hồ rồi gọi đó là peppering an toàn.
- Có thể lưu **pepper key ID** không bí mật để tìm đúng secret khi verify; quản lý rotation khác với salt.
- Mất pepper có thể khiến không thể kiểm tra mật khẩu cũ; lộ pepper cần xử lý sự cố/rotation và có thể yêu cầu reset mật khẩu tùy kiến trúc.
- Pepper không thay thế thuật toán memory-hard/slow, salt riêng hoặc MFA.

Ví dụ Java ở phần 7 **không dùng pepper** để giữ bài toán cơ bản minh bạch và tự chạy được.

## 12. Đầu vào không hợp lệ và xử lý lỗi

Một bản ghi bị hỏng hoặc được nhập từ một hệ thống cũ có thể thiếu fields, salt bị cắt, algorithm lạ hay iteration count không hợp lệ. Cần **từ chối sớm** và không thử sửa bằng heuristic khi đây là dữ liệu xác thực.

| Dạng lỗi | Điều hệ thống nên làm |
| --- | --- |
| Thiếu format version hoặc version không hỗ trợ | Reject với lý do vận hành nội bộ phù hợp; không tự thử mọi parser không giới hạn. |
| Algorithm ngoài allowlist | Reject, không fallback về MD5/SHA-1 hay hash nhanh. |
| Iterations = 0 / âm / vượt max | Reject **trước khi chạy PBKDF2**, tránh DoS. |
| Argon2 m/t/p quá cao hoặc vô lý | Reject theo profile/bounds trước phép tính nặng về RAM/CPU. |
| Salt rỗng, quá ngắn, bị cắt hoặc không đúng encoding | Reject; không phát sinh salt mới để “khôi phục” record cũ. |
| Verifier thiếu bytes / khác output length | Reject; không so sánh prefix hoặc bỏ qua byte bị thiếu. |
| Wrong password | KDF tạo bytes khác và verify false; không cấp session. |
| Không có user hoặc user bị vô hiệu | Ứng xử thống nhất và có rate limit, tránh lộ thông tin tài khoản. |
| Provider không hỗ trợ algorithm hoặc cấu hình | Xử lý lỗi hệ thống có kiểm soát và cảnh báo vận hành; không tự hạ security level. |

**Một record là dữ liệu cần validate, kể cả khi nằm trong database.** Có thể bị hỏng bởi migration, bug, thao tác quản trị hoặc dữ liệu bị sao chép/tráo. Upper bound iteration, output length và kích thước envelope là thiết yếu để tránh lạm dụng tài nguyên.

### Sai password và tính thời gian phản hồi

Một phép so sánh mảng đúng cách **không đảm bảo toàn bộ endpoint phản hồi cố định thời gian**. DB lookup, parse, KDF, MFA và rate limit có thời gian khác nhau. Cần chính sách chống user enumeration, quan sát thực tế, rate limit và xử lý thông điệp lỗi chung; không cố đưa cả hệ thống thành constant-time bằng vài lời gọi sleep tùy tiện.

## 13. Bảo mật bộ nhớ và xử lý dữ liệu nhạy cảm trong Java

**char[]** thường phù hợp hơn String để nhận password ở những API cho phép caller kiểm soát bộ nhớ: có thể dùng **Arrays.fill(password, '\0')** khi đã hoàn tất. **PBEKeySpec.clearPassword()** xóa bản sao bên trong key spec. Tuy nhiên:

- HTTP framework, JSON parser, logging hoặc các thư viện khác có thể đã tạo String/buffer riêng; xóa một char[] **không chứng minh** đã xóa mọi bản sao.
- Không in password, token, pepper hoặc derived verifier ra log, trace, error page, metrics labels hoặc telemetry.
- Không dùng password hoặc salt làm khóa Map/cache lâu dài; hạn chế password tồn tại qua nhiều thread hoặc async task không cần thiết.
- Các **byte[] của derived verifier tạm** nên xóa sau sử dụng khi có thể. Bản hash cần lưu dài hạn trong database nhưng không cần giữ lại nhiều bản sao bộ nhớ.
- Không dùng String.equals cho đối chiếu verifier dạng text; decode ra bytes đúng length rồi dùng cách so sánh phù hợp.
- SecretKeyFactory/PBEKeySpec phải được khởi tạo đúng lần dùng; không chia sẻ mutable password buffer giữa các request song song.

**Lưu ý:** việc in số lượng field và kết quả true/false trong demo là an toàn cho bài học; ở production, không ghi nội dung record vào access log, kể cả khi hash không phải plaintext.

## 14. Kiểm thử đầy đủ cho password record

| Ca kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Tạo record mới | Password hợp lệ, current profile | Có version/algorithm/params/salt/verifier; salt ngẫu nhiên; record parse được. |
| Đúng password | Record vừa tạo + cùng password | Verify true. |
| Sai password | Cùng record + password khác | Verify false. |
| Tạo lại cùng password | Hai lần create cùng chuỗi | Salt khác nhau với xác suất áp đảo, verifier cũng khác, cả hai record đều verify đúng password. |
| Wrong salt | Đổi một byte salt trong record nhưng giữ verifier | Verify false hoặc reject theo kiểm tra format. |
| Wrong verifier | Đổi một byte derived hash được lưu | Verify false. |
| Mất field | Cắt record hoặc bỏ delimiter | Reject trước KDF. |
| Base64url lỗi | Ký tự hoặc padding không hợp lệ theo profile | Reject; không silently normalize. |
| Iterations bằng 0 | Record PBKDF2 cost bất hợp lệ | Reject trước KDF. |
| Iterations cực lớn | 999.999.999 | Reject trước KDF, tránh CPU exhaustion. |
| Output length khác | Record ghi 256 bit nhưng hash thiếu byte | Reject; không so prefix. |
| Legacy profile | Bản ghi 200.000 iterations thuộc tập được cho phép | Verify vẫn đúng, needsRehash=true. |
| Current profile | Bản ghi 600.000 iterations | Verify đúng, needsRehash=false. |
| Concurrent login | Hai lần đăng nhập/chuyển đổi tham số cùng lúc | Không tạo trạng thái DB không nhất quán hoặc ghi đè reset password. |
| Unicode | Ký tự có dấu, emoji, tổ hợp dấu theo policy | Round-trip tạo/verify nhất quán với cùng encoding và normalization. |
| Rehash + failed password | Wrong password trên record legacy | Không đổi database record. |
| Rehash + successful password | Valid password trên record legacy | Record mới dùng salt và profile mới, cập nhật atomic. |

Không cần chứng minh “salt không bao giờ trùng” bằng một test chạy hai lần; với salt 128 bit, điều bảo đảm thực tế dựa trên CSPRNG và xác suất va chạm thấp, cộng thiết kế vận hành phù hợp.

### Kiểm thử khi chuyển JDK/provider

Một hệ thống có thể thay JDK, security provider, môi trường FIPS hoặc thư viện password hasher. Cần thử xác minh **những record lịch sử đã được tạo trên môi trường cũ**, đặc biệt với password có ký tự Unicode, thay vì chỉ kiểm tra create→verify trong cùng JVM phiên bản mới. Định dạng record đầy đủ là điều kiện cần, nhưng vẫn phải thống nhất cách chuyển password ký tự thành input KDF.

## 15. Những sai lầm điển hình

1. **Chỉ lưu hash mà bỏ salt/iterations/algorithm.** Khi thay config, record cũ không còn được xác minh đáng tin.
2. **SHA-256(password) hoặc SHA-256(password+salt) một lần.** Không đủ chi phí để chống offline guessing.
3. **Dùng cùng salt cho mọi user.** Làm mất lợi ích chính của unique salt.
4. **Dùng timestamp, email hoặc Random để sinh salt.** Thiếu ngẫu nhiên mật mã.
5. **Đổi iteration hiện tại rồi dùng nó verify mọi record cũ.** Kết quả không khớp dù password đúng.
6. **Nâng field iterations trong DB mà không tính lại verifier.** Record trở nên không thể xác minh.
7. **Nhận cost do client gửi.** Cho phép hạ bảo mật hoặc tạo request tiêu tốn CPU/RAM.
8. **Bỏ kiểm tra upper bound của KDF params.** Record lỗi/độc hại có thể gây từ chối dịch vụ.
9. **Lưu pepper ngay cạnh hash và salt.** Không còn lợi ích bảo vệ bổ sung khi chỉ database bị lộ.
10. **Log password, derived verifier hoặc record nhạy cảm.** Làm tăng số nơi chứa dữ liệu có thể dùng để đoán password.
11. **So sánh hash bằng prefix, equals không phù hợp hoặc chỉ kiểm tra vài byte.** Làm yếu tiêu chí xác minh.
12. **Đổi normalization/encoding không version hóa.** Người dùng nhập đúng password nhưng không đăng nhập được.
13. **Tin rằng PBKDF2 256-bit output khiến password 8 ký tự có 256-bit entropy.** Entropy phụ thuộc cách tạo password, không do output length.
14. **Đổi sang Argon2id bằng cách hash lại hash PBKDF2.** Không tạo được verifier đúng theo password gốc, dẫn đến bảo vệ và migration sai.
15. **Rehash trước khi verify thành công.** Có thể thay record của user khi chưa chứng minh người yêu cầu biết password.
16. **Chỉ đo latency từng verify mà không xét tổng tải song song.** KDF quá tốn tài nguyên có thể làm nghẽn dịch vụ.
17. **Dùng password hash như bearer token.** Ai lấy được record có thể giả mạo qua đường API sai kiến trúc; record chỉ phục vụ xác minh server-side.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Hai người dùng có cùng mật khẩu, tại sao password record của họ thường không bằng nhau?  
**Trả lời:** Mỗi record có salt ngẫu nhiên riêng; cùng password nhưng salt khác sẽ sinh verifier khác. Salt phải lưu cùng record để verifier biết dùng salt nào.

**Câu 2.** Sau khi tăng PBKDF2 từ 200.000 lên 600.000 vòng, có thể xác minh tất cả record bằng 600.000 vòng không?  
**Trả lời:** Không. Record cũ phải xác minh bằng 200.000 vòng đã lưu. Chỉ khi password đúng mới có thể tạo record mới bằng 600.000 vòng và salt mới.

**Câu 3.** PBEKeySpec(password, salt, 600000, 256) có nghĩa chương trình đã tạo “mật khẩu 256 bit” không?  
**Trả lời:** Không. 256 là **số bit output của phép dẫn xuất**, không đo entropy của password. Password yếu vẫn có thể bị đoán ngoại tuyến.

**Câu 4.** Bên nhận thấy record ghi 1.000.000.000 iterations. Có nên chạy SecretKeyFactory để “kiểm thử cho chắc” không?  
**Trả lời:** Không. Phải validate upper bound trước khi tốn CPU, từ chối record ngoài chính sách và cảnh báo vận hành phù hợp.

**Câu 5.** Salt có cần giữ bí mật như pepper không?  
**Trả lời:** Không. Salt công khai và lưu kèm record. Pepper là bí mật bổ sung tách khỏi database nếu kiến trúc chọn dùng.

**Câu 6.** Nếu đổi từ PBKDF2 sang Argon2id, có thể chuyển toàn bộ record offline mà không biết password gốc không?  
**Trả lời:** Không thể tạo verifier Argon2id của password từ verifier PBKDF2 một cách tương đương. Cần password gốc khi đăng nhập thành công hoặc quy trình reset.

**Câu 7.** MessageDigest.isEqual có làm endpoint login hoàn toàn constant-time không?  
**Trả lời:** Không. Nó hữu ích khi so sánh bytes verifier; các nhánh lookup, parse, KDF, rate limit và vận hành vẫn có đặc tính timing riêng.

**Câu 8.** Một record được lưu dạng Base64url có được “mã hóa” và không cần phân quyền đọc không?  
**Trả lời:** Không. Base64url là encoding, không phải encryption. Stored verifier vẫn cần bảo vệ quyền truy cập và sao lưu.

**Câu 9.** Trong Argon2id, m=19456,t=2,p=1 có nghĩa gì?  
**Trả lời:** 19 MiB bộ nhớ, 2 passes và 1 lane/degree of parallelism. Đây là những tham số thuật toán cần lưu kèm record, không phải salt/hash bytes.

**Câu 10.** Rehash on login có thể ghi đè password mới nếu người dùng vừa reset trong request khác?  
**Trả lời:** Có nguy cơ nếu update vô điều kiện. Dùng optimistic locking/compare-and-swap để chỉ thay record nếu bản đang lưu vẫn là record đã xác minh.

## 17. Tổng kết và nguồn tham khảo

Một **password record đúng** chứa đủ thông tin để tái thực thi phép kiểm tra: **format version, algorithm, work factor, salt, output length, verifier**, và mọi metadata bổ sung liên quan đến encoding/pepper. Tạo record bằng salt mới và current profile; xác minh bằng params **đã lưu**; chỉ rehash sau khi xác minh đúng và cập nhật DB atomic. Java 17 cung cấp PBKDF2WithHmacSHA256 để minh họa trực tiếp; Argon2id cần thư viện được duy trì phù hợp và phải giữ đầy đủ m/t/p cùng version.

Nguồn kỹ thuật có thể đối chiếu khi thiết kế thực tế:

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) — thuật toán, salt, work factor, pepper, nâng cấp hash.
- [RFC 9106 — Argon2 Memory-Hard Function](https://www.rfc-editor.org/rfc/rfc9106.html) — Argon2id, m/t/p và cấu trúc tham số.
- [Java SE 21 — PBEKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html) — password char[], salt, iteration, key length, clearPassword.
- [Java SE 21 — SecretKeyFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKeyFactory.html) — derive/generateSecret qua JCA.
- [Java SE 21 — SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html) — tạo salt ngẫu nhiên mật mã.
- [Java SE 21 — MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html) — so sánh verifier bytes.