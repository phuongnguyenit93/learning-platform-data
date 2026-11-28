# Salt và pepper

Trong chương **Password và cryptographic key** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích salt và pepper trong quá trình lưu trữ mật khẩu an toàn. Cả hai đều được dùng cùng password hashing hoặc key derivation function (KDF), nhưng có vai trò khác nhau: salt là giá trị ngẫu nhiên riêng cho từng mật khẩu và được lưu cùng verifier; pepper là bí mật bổ sung do hệ thống giữ tách khỏi cơ sở dữ liệu. Kết hợp đúng giúp giảm hiệu quả của tấn công dùng bảng tính sẵn và tấn công đoán mật khẩu offline khi kẻ tấn công chỉ lấy được database.

## 1. Salt là gì?

**Salt** là một giá trị ngẫu nhiên được tạo riêng cho mỗi mật khẩu trước khi đưa mật khẩu vào password hashing scheme hoặc KDF. Salt thường được lưu công khai cùng kết quả dẫn xuất. Salt không cần giữ bí mật và không phải khóa mã hóa.

Mục đích chính của salt:

- Làm cho cùng một mật khẩu tạo ra các kết quả dẫn xuất khác nhau ở các tài khoản hoặc lần tạo khác nhau.
- Ngăn kẻ tấn công dùng một bảng rainbow table hoặc kết quả tính sẵn để tra cứu hàng loạt.
- Buộc kẻ tấn công phải tính lại KDF cho từng salt khi thử đoán mật khẩu.
- Hỗ trợ mỗi bản ghi mật khẩu có tham số và kết quả độc lập.

Ví dụ, hai tài khoản cùng chọn mật khẩu giống nhau nhưng có salt khác nhau sẽ có password verifier khác nhau. Khi database bị lộ, kẻ tấn công không thể nhận ra ngay hai tài khoản dùng cùng mật khẩu chỉ bằng cách so sánh giá trị hash.

Salt không làm mật khẩu yếu trở nên mạnh. Nếu mật khẩu dễ đoán, kẻ tấn công vẫn có thể thử từng phỏng đoán bằng salt và KDF đã biết. Salt làm mất lợi thế tính sẵn theo lô; độ khó của mỗi lần thử vẫn phụ thuộc mật khẩu và chi phí của KDF.

## 2. Pepper là gì?

**Pepper** là một bí mật bổ sung được kết hợp với mật khẩu hoặc kết quả KDF trước khi lưu password verifier. Khác với salt, pepper phải được bảo vệ và lưu ngoài cơ sở dữ liệu chứa thông tin xác thực.

Pepper có thể được lưu trong:

- Secret manager hoặc vault có kiểm soát truy cập.
- HSM hoặc KMS, nếu dịch vụ hỗ trợ thao tác HMAC hoặc phép toán cần thiết.
- Cấu hình bí mật được cấp cho ứng dụng qua cơ chế bảo mật của nền tảng, với quyền đọc hạn chế.

Pepper nên là giá trị ngẫu nhiên có entropy cao do hệ thống tạo, không phải một mật khẩu do quản trị viên tự nghĩ ra. Không lưu pepper trong cùng bảng database với salt và verifier; nếu cả ba nằm cùng một nơi, pepper không còn tạo ra lớp bảo vệ độc lập khi database bị đánh cắp.

Pepper thường được quản lý ở cấp ứng dụng hoặc môi trường, có thể chia theo hệ thống hoặc miền bảo mật. Không nhất thiết tạo một pepper riêng cho từng người dùng. Nếu dùng chung một pepper, phạm vi ảnh hưởng khi bí mật này bị lộ sẽ rộng; có thể tách theo ứng dụng, môi trường hoặc tenant khi kiến trúc và khả năng vận hành cho phép.

## 3. Phân biệt salt và pepper

| Thuộc tính | Salt | Pepper |
|---|---|---|
| Mục đích | Tạo đầu vào riêng cho từng mật khẩu, chống tra cứu tính sẵn | Thêm bí mật ngoài database để tăng khả năng chống tấn công khi chỉ lộ database |
| Tính bí mật | Không cần bí mật | Phải bí mật |
| Phạm vi | Thường riêng cho từng password record | Thường dùng theo ứng dụng, môi trường hoặc tenant |
| Nơi lưu | Cùng record với verifier và KDF parameters | Secret manager, KMS/HSM hoặc kho bí mật tách biệt |
| Cách tạo | Giá trị ngẫu nhiên mới cho mỗi password record | Bí mật ngẫu nhiên có entropy cao |
| Khi đổi mật khẩu | Tạo salt mới | Thường tiếp tục dùng pepper version hiện hành |
| Khi rotate | Không cần giữ bí mật; tạo salt mới khi tạo verifier mới | Cần quy trình chuyển đổi version và giữ khả năng xác minh bản ghi cũ |

Salt và pepper không thay thế nhau. Salt chống việc dùng chung kết quả tính sẵn giữa các bản ghi; pepper bổ sung một bí mật mà kẻ tấn công lấy database đơn thuần không có. Một hệ thống lưu salt đúng cách nhưng để pepper trong database không đạt được lợi ích của pepper.

## 4. Vì sao cần salt?

Giả sử một hệ thống chỉ lưu:

~~~text
hash = SHA-256(password)
~~~

Nếu hai người dùng chọn cùng mật khẩu, kết quả hash giống nhau. Kẻ tấn công có thể tính trước hash của những mật khẩu phổ biến rồi so sánh với database. Tấn công này đặc biệt hiệu quả khi hàm băm rất nhanh.

Khi thêm salt:

~~~text
verifier = KDF(password, salt, parameters)
~~~

mỗi bản ghi có salt khác nhau. Kẻ tấn công không thể dùng một kết quả đã tính cho salt A để kiểm tra bản ghi có salt B. Tuy nhiên, salt được lưu công khai nên kẻ tấn công vẫn có thể chạy KDF cho từng phỏng đoán. Vì vậy cần dùng password hashing scheme hoặc KDF có chi phí phù hợp.

## 5. Vì sao cần pepper?

Pepper bổ sung một bí mật không nằm trong database. Một cách triển khai phổ biến là:

1. Dùng KDF với password, salt và tham số để tạo giá trị dẫn xuất.
2. Dùng HMAC với pepper key để tạo verifier cuối cùng.
3. Lưu verifier, salt, tham số KDF và pepper version trong database.
4. Khi đăng nhập, lấy đúng pepper version từ kho bí mật, tính lại verifier và so sánh.

~~~mermaid
flowchart TD
    A[Password người dùng] --> B[KDF / password hashing]
    C[Salt công khai] --> B
    D[KDF parameters] --> B
    B --> E[Derived value]
    F[Pepper key trong KMS/HSM] --> G[HMAC]
    E --> G
    G --> H[Password verifier]
    H --> I[Database]
    C --> I
    D --> I
    J[Pepper version] --> I
~~~

Nếu kẻ tấn công chỉ lấy được database, họ có salt, tham số và verifier nhưng không có pepper key để kiểm tra phỏng đoán bằng quy trình đầy đủ. Điều này làm giảm khả năng tấn công offline. Nếu kẻ tấn công đồng thời lấy được pepper hoặc có thể gọi dịch vụ HMAC không giới hạn, lớp bảo vệ này có thể mất tác dụng.

Pepper không ngăn được tấn công đăng nhập trực tuyến, phishing, malware trên thiết bị người dùng hoặc việc chiếm quyền tiến trình ứng dụng có thể đọc password khi người dùng nhập. Vẫn cần rate limiting, MFA, giám sát đăng nhập và bảo vệ ứng dụng.

## 6. Salt phải được tạo và lưu như thế nào?

Salt cần được tạo bằng nguồn ngẫu nhiên mật mã, có độ dài đủ lớn và mới cho mỗi password record. Một lựa chọn thực tế phổ biến là ít nhất 16 byte ngẫu nhiên (128 bit), trừ khi chuẩn hoặc thư viện được chọn yêu cầu khác.

Trong Java, có thể dùng SecureRandom:

~~~java
import java.security.SecureRandom;

public final class SaltGenerator {
    private static final int SALT_LENGTH_BYTES = 16;

    public static byte[] newSalt(SecureRandom random) {
        byte[] salt = new byte[SALT_LENGTH_BYTES];
        random.nextBytes(salt);
        return salt;
    }
}
~~~

Salt không cần mã hóa và có thể lưu dạng byte array hoặc encoding như Base64. Mỗi bản ghi nên giữ salt của chính nó cùng KDF algorithm, tham số chi phí, độ dài đầu ra và phiên bản định dạng.

Không dùng:

- Một salt cố định cho toàn hệ thống.
- Username, email hoặc ID tài khoản làm salt duy nhất.
- Timestamp hoặc số thứ tự có thể đoán được.
- Một salt giống nhau cho tất cả tài khoản.
- Một salt lấy từ password hoặc từ dữ liệu do người dùng kiểm soát mà không qua CSPRNG.

Khi người dùng đổi mật khẩu hoặc reset password, tạo salt mới và tạo verifier mới. Không cần giữ salt cũ để bảo mật; chỉ giữ metadata lịch sử nếu có yêu cầu kiểm toán cụ thể.

## 7. Chọn password hashing scheme hoặc KDF

Salt và pepper chỉ là các thành phần của quy trình. Phần cốt lõi là password hashing scheme/KDF được thiết kế để làm mỗi lần thử mật khẩu tốn tài nguyên.

| Scheme | Đặc điểm | Lưu ý |
|---|---|---|
| Argon2id | KDF memory-hard, kết hợp chi phí bộ nhớ và thời gian | Lựa chọn mạnh cho password storage khi có thư viện đã được đánh giá và cấu hình phù hợp |
| scrypt | KDF memory-hard, tăng chi phí bộ nhớ khi đoán mật khẩu | Phù hợp khi thư viện và policy hỗ trợ |
| PBKDF2 | KDF dựa trên HMAC với số vòng lặp cấu hình | Có hỗ trợ rộng trong Java JCA; cần benchmark iteration count và nâng cấp theo policy |
| bcrypt | Password hashing scheme lâu đời, có cost factor | Cần lưu ý giới hạn độ dài password và quy tắc encoding của implementation |
| SHA-256/SHA-512 trực tiếp | Hàm hash nhanh, không phải password hashing scheme | Không dùng trực tiếp để lưu mật khẩu người dùng |

Với hệ thống mới, ưu tiên Argon2id nếu có thư viện đáng tin cậy, được duy trì và đáp ứng môi trường triển khai. PBKDF2WithHmacSHA256 là lựa chọn phổ biến trong Java JCA khi cần tích hợp chuẩn sẵn có hoặc đáp ứng yêu cầu tương thích. Tham số phải được chọn theo policy hiện hành và đo trên phần cứng thực tế; không có một iteration count duy nhất phù hợp mọi hệ thống.

KDF cần đủ tốn kém để làm chậm tấn công offline nhưng không khiến đăng nhập hợp lệ gây cạn kiệt tài nguyên. Cần giới hạn số lần KDF chạy đồng thời, rate limit endpoint đăng nhập và theo dõi tải bất thường.

Với mật khẩu có ký tự Unicode, cần xác định quy tắc chuẩn hóa và cách chuyển ký tự thành đầu vào KDF, rồi áp dụng giống nhau khi đăng ký, đăng nhập và reset. Không được âm thầm thay đổi quy tắc giữa các phiên bản ứng dụng. Khi đổi JDK hoặc provider PBKDF2, nên kiểm thử bằng test vector có mật khẩu ngoài ASCII để phát hiện khác biệt trong cách xử lý ký tự.

## 8. Lưu password verifier cùng metadata

Một record password storage cần đủ thông tin để tái tạo đúng kết quả khi xác minh:

| Trường | Ví dụ nội dung | Bí mật? |
|---|---|---|
| Algorithm | Argon2id hoặc PBKDF2WithHmacSHA256 | Không |
| Salt | 16 byte ngẫu nhiên hoặc dài hơn theo policy | Không |
| Parameters | memory cost, time cost, parallelism hoặc iteration count, key length | Không |
| Verifier | Kết quả password hashing sau khi áp dụng pepper nếu có | Có giá trị nhạy cảm; không phải password plaintext |
| Pepper version | ID/version để chọn pepper key phù hợp | Không phải pepper key; vẫn cần kiểm soát |
| Format version | Phiên bản schema/encoding của record | Không |

Salt và tham số có thể lưu cùng verifier trong một chuỗi định dạng chuẩn do thư viện password hashing cung cấp. Nếu tự thiết kế schema, phải có versioning rõ ràng và parser kiểm tra chặt chẽ. Không cho phép dữ liệu trong database tự chọn thuật toán tùy ý hoặc tham số cực lớn gây cạn kiệt CPU/bộ nhớ.

Pepper key không được lưu trong record này. Database chỉ nên chứa một định danh/version cho phép ứng dụng lấy đúng key từ kho bí mật.

## 9. Kết hợp pepper với KDF

Có nhiều cách kết hợp pepper. Một cách thường dùng là áp dụng HMAC với pepper key lên đầu ra KDF để tạo verifier cuối:

~~~text
derived = KDF(password, salt, parameters)
verifier = HMAC(pepper_key, domain || derived)
~~~

Trong đó domain là chuỗi phân tách mục đích (domain separation) cố định, ví dụ password-verifier-v1. Việc phân tách mục đích tránh dùng cùng pepper key cho các loại dữ liệu khác nhau. Cũng có thiết kế dùng pepper ở bước tiền xử lý password trước KDF; nếu chọn cách này, phải dùng thư viện và quy trình đã được đánh giá, xác định rõ encoding và giới hạn độ dài.

Không tự nối pepper vào password bằng chuỗi tùy tiện rồi coi đó là một chuẩn mật mã. Cần dùng HMAC hoặc cơ chế keyed construction đã được thiết kế, có domain separation và quản lý key version.

Ví dụ minh họa bên dưới dùng PBKDF2WithHmacSHA256 trong JCA, sau đó HMAC kết quả bằng pepper key. Trong production, pepper key nên được lấy qua KMS/HSM hoặc secret manager; nếu provider hỗ trợ HMAC trực tiếp với key handle không exportable, không cần đưa pepper bytes vào heap ứng dụng.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordVerifier {
    private static final int SALT_BYTES = 16;
    private static final int DERIVED_KEY_BITS = 256;
    private static final byte[] DOMAIN =
            "password-verifier-v1".getBytes(StandardCharsets.UTF_8);

    public static byte[] newSalt(SecureRandom random) {
        byte[] salt = new byte[SALT_BYTES];
        random.nextBytes(salt);
        return salt;
    }

    public static byte[] createVerifier(
            char[] password,
            byte[] salt,
            int iterations,
            SecretKey pepperKey) throws GeneralSecurityException {

        if (password == null || salt == null || salt.length < SALT_BYTES
                || iterations <= 0 || pepperKey == null) {
            throw new IllegalArgumentException("Invalid KDF input");
        }

        PBEKeySpec spec = new PBEKeySpec(
                password, salt, iterations, DERIVED_KEY_BITS);
        byte[] derivedBytes = null;
        try {
            SecretKeyFactory factory =
                    SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
            derivedBytes = factory.generateSecret(spec).getEncoded();
            if (derivedBytes == null) {
                throw new GeneralSecurityException(
                        "Provider did not expose PBKDF2 output");
            }

            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(pepperKey);
            mac.update(DOMAIN);
            return mac.doFinal(derivedBytes);
        } finally {
            spec.clearPassword();
            if (derivedBytes != null) {
                Arrays.fill(derivedBytes, (byte) 0);
            }
        }
    }

    public static boolean verify(
            byte[] storedVerifier,
            char[] candidatePassword,
            byte[] salt,
            int iterations,
            SecretKey pepperKey) throws GeneralSecurityException {

        if (storedVerifier == null || storedVerifier.length != 32) {
            throw new IllegalArgumentException("Invalid stored verifier");
        }
        byte[] candidateVerifier = createVerifier(
                candidatePassword, salt, iterations, pepperKey);
        try {
            return MessageDigest.isEqual(
                    storedVerifier, candidateVerifier);
        } finally {
            Arrays.fill(candidateVerifier, (byte) 0);
        }
    }
}
~~~

Đây là ví dụ minh họa luồng, không phải thư viện password storage hoàn chỉnh. Ứng dụng phải lưu algorithm, salt, iteration count, key length, pepper version và format version; phải lấy đúng pepper key theo version trước khi xác minh. Caller chịu trách nhiệm xóa mảng password của mình sau khi dùng. PBEKeySpec.clearPassword xóa bản sao password do PBEKeySpec giữ; việc xóa mảng byte tạm giảm thời gian giữ thêm bản sao nhưng không bảo đảm xóa mọi bản sao trong heap hoặc bộ nhớ provider.

Ví dụ giả định provider có thể dùng SecretKey pepper cho HMAC. Với pepper key không exportable trong HSM/KMS, provider phải hỗ trợ thao tác HMAC trực tiếp bằng key handle. Nếu không, dùng API MAC của dịch vụ hoặc adapter đã được đánh giá; không export pepper trái policy chỉ để làm cho ví dụ chạy.

## 10. Salt và pepper trong quy trình đăng ký, đăng nhập

### Khi đăng ký hoặc đổi mật khẩu

1. Nhận password qua kênh được bảo vệ và áp dụng chính sách password.
2. Tạo salt ngẫu nhiên mới cho record.
3. Chọn KDF và tham số theo policy hiện hành.
4. Lấy pepper key version hiện hành từ kho bí mật.
5. Dẫn xuất password bằng KDF.
6. Áp dụng HMAC/keyed step với pepper để tạo verifier cuối.
7. Lưu verifier, salt, KDF parameters, pepper version và format version.
8. Xóa các bản sao password và dữ liệu dẫn xuất tạm khi có thể.

### Khi đăng nhập

1. Đọc record và kiểm tra format version, thuật toán cùng tham số có nằm trong allowlist không.
2. Lấy salt và pepper version từ record.
3. Lấy pepper key tương ứng từ secret manager/KMS/HSM.
4. Dẫn xuất candidate verifier bằng đúng KDF và tham số đã lưu.
5. So sánh verifier theo cách chống timing phù hợp.
6. Nếu hợp lệ và tham số cũ không còn đạt policy, nâng cấp verifier bằng KDF parameters, salt và pepper version mới.
7. Ghi audit về kết quả và quá trình nâng cấp mà không ghi password, pepper hoặc verifier vào log.

Nếu pepper service không khả dụng, xác minh phải thất bại an toàn hoặc đi theo quy trình phục hồi được phê duyệt. Không bỏ qua pepper để cho phép đăng nhập bằng cách so sánh KDF output trực tiếp.

## 11. Pepper được bảo vệ như thế nào?

Pepper là bí mật có phạm vi ảnh hưởng lớn. Nếu pepper bị lộ cùng database, kẻ tấn công có thể kiểm tra phỏng đoán password offline bằng đầy đủ quy trình. Do đó:

- Lưu pepper trong secret manager, KMS hoặc HSM; không lưu trong database password record.
- Không commit pepper vào Git, Dockerfile, image layer, file cấu hình mẫu hoặc log.
- Hạn chế quyền lấy hoặc sử dụng pepper theo service identity và nguyên tắc tối thiểu.
- Nếu dùng HSM/KMS, ưu tiên thao tác HMAC bằng key handle không exportable.
- Tách pepper giữa development, staging và production.
- Cân nhắc tách theo ứng dụng hoặc tenant để giới hạn blast radius.
- Ghi audit cho việc truy cập hoặc sử dụng pepper, không ghi giá trị bí mật.
- Giới hạn tốc độ gọi KDF/HMAC để tránh lạm dụng dịch vụ.
- Có quy trình backup, rotation, phục hồi và xử lý compromise.

Nếu pepper được cấp qua biến môi trường, cần kiểm soát quyền xem process environment, crash dump, diagnostic endpoint và log triển khai. Biến môi trường tiện cho cấu hình nhưng không tự động là kho bí mật an toàn.

## 12. Pepper rotation và versioning

Pepper không thể được rotate giống salt. Salt được lưu công khai và có thể tạo mới bất kỳ khi nào tạo verifier mới. Pepper là bí mật bên ngoài database; muốn đổi pepper, ứng dụng phải còn khả năng xác minh các record được tạo bằng pepper cũ.

Mỗi record nên lưu pepper version hoặc key ID. Khi rotate:

1. Tạo pepper key mới trong secret manager/KMS/HSM.
2. Đặt version mới làm phiên bản dùng cho tài khoản mới và các lần cập nhật.
3. Giữ pepper cũ ở trạng thái chỉ dùng để xác minh trong giai đoạn chuyển đổi.
4. Khi người dùng đăng nhập thành công bằng pepper cũ, tạo salt mới và verifier mới bằng pepper hiện hành.
5. Cập nhật record một cách nguyên tử để tránh mất trạng thái nếu tiến trình dừng giữa chừng.
6. Theo dõi số record còn dùng version cũ.
7. Khi không còn record phụ thuộc, thu hồi hoặc hủy pepper cũ theo policy.

Không thể tính lại verifier mới từ verifier cũ chỉ bằng cách thay pepper nếu không có password gốc. Nếu tài khoản không đăng nhập trong thời gian chuyển đổi, tổ chức có thể tiếp tục giữ pepper cũ trong thời hạn được phê duyệt hoặc yêu cầu reset password trước khi ngừng key cũ.

Nếu pepper bị compromise, đánh giá phạm vi và thời gian phơi nhiễm. Có thể cần rotate khẩn cấp, yêu cầu đổi mật khẩu, tăng giám sát đăng nhập và thông báo theo quy trình ứng phó. Chỉ thay pepper trong hệ thống không làm cho các verifier đã bị lộ trở nên an toàn trở lại nếu kẻ tấn công đã có đủ dữ liệu và bí mật cũ.

## 13. KDF parameters và nâng cấp verifier

KDF parameters cũng cần versioning. Khi phần cứng mạnh hơn hoặc policy thay đổi, hệ thống có thể tăng chi phí dẫn xuất. Cần lưu các tham số theo từng record thay vì giả định mọi tài khoản luôn dùng cùng cấu hình.

Quy trình nâng cấp:

- Xác thực bằng thuật toán và tham số đang lưu.
- Sau khi xác thực thành công, tạo salt mới.
- Dùng KDF và tham số mới đã được benchmark.
- Dùng pepper version hiện hành.
- Ghi verifier mới và metadata trong cùng một transaction.
- Giữ lại dữ liệu cũ chỉ trong thời gian cần thiết cho tính nhất quán; không log hoặc lưu bản sao không cần thiết.

Với Argon2id, metadata thường gồm memory cost, time cost, parallelism và output length. Với PBKDF2, metadata gồm PRF, iteration count, salt và key length. Không cho phép attacker chỉnh record để buộc server dùng tham số quá lớn; validate tham số và áp dụng giới hạn tài nguyên.

## 14. Salt/pepper không phải encryption key

Salt và pepper trong password storage không đồng nghĩa với DEK hoặc KEK trong mã hóa dữ liệu.

| Khái niệm | Vai trò | Có dùng để giải mã dữ liệu không? |
|---|---|---|
| Salt | Làm đầu vào KDF riêng cho từng password record | Không |
| Pepper | Bí mật bổ sung cho password verifier | Không nên dùng như khóa mã hóa dữ liệu |
| Password verifier | Giá trị dùng để xác minh password | Không |
| DEK | Khóa mã hóa dữ liệu | Có, dùng để giải mã ciphertext tương ứng |
| KEK | Khóa bảo vệ hoặc bọc DEK | Dùng để unwrap DEK theo thiết kế |

Không dùng pepper làm KEK hoặc AES key chỉ vì nó là một bí mật. Mỗi mục đích cần key riêng, thuật toán phù hợp, metadata và vòng đời riêng. Nếu cần tạo khóa mã hóa từ password, hãy dùng password-based encryption/KDF theo chuẩn và quản lý nonce, authentication tag, salt, tham số cùng khả năng phục hồi dữ liệu.

## 15. Những tấn công salt và pepper giúp giảm thiểu

| Tấn công | Salt giúp gì? | Pepper giúp gì? |
|---|---|---|
| Rainbow table/precomputed hash | Làm kết quả phụ thuộc salt riêng, phá lợi thế tra cứu tính sẵn | Không phải vai trò chính |
| Cùng password có cùng hash | Khi salt riêng, verifier khác nhau | Có thể thêm lớp khác nhưng không thay salt |
| Database-only offline cracking | Không ngăn được thử từng password với salt đã lộ, nhưng buộc tính riêng từng record | Ngăn hoặc làm khó việc kiểm tra phỏng đoán nếu pepper vẫn bí mật |
| Database và application secret cùng bị lộ | Không đủ để bảo vệ password yếu | Lợi ích pepper giảm hoặc mất |
| Online password guessing | Không trực tiếp ngăn | Không trực tiếp ngăn |
| Phishing/credential stuffing | Không trực tiếp ngăn | Không trực tiếp ngăn |

Vì vậy, salt/pepper cần được kết hợp với KDF phù hợp, password policy hợp lý, MFA, rate limiting, phát hiện credential stuffing và quy trình ứng phó khi database hoặc secret manager bị xâm phạm.

## 16. Sai lầm thường gặp

- **Dùng một salt cố định:** làm các bản ghi mất tính độc lập và tạo điều kiện tra cứu tính sẵn.
- **Dùng username làm salt:** giá trị dễ đoán và có thể lặp lại khi username trùng hoặc thay đổi.
- **Giữ salt bí mật thay vì tạo pepper:** salt có thể và nên được lưu cùng verifier; không có lợi khi giấu nó như một bí mật.
- **Lưu pepper trong cùng database:** database breach lấy được cả salt, verifier và pepper.
- **Hard-code pepper trong source code:** bí mật có thể rò qua Git, artifact hoặc build log.
- **Dùng một pepper cho mọi hệ thống:** tăng phạm vi ảnh hưởng khi một ứng dụng bị xâm phạm.
- **Dùng SHA-256 trực tiếp cho password:** hàm hash nhanh khiến thử đoán offline rẻ.
- **Dùng PBKDF2 với iteration count thấp hoặc cố định mãi:** chi phí đoán mật khẩu không theo kịp năng lực phần cứng.
- **Không lưu pepper version:** không thể chọn đúng bí mật khi xác minh record cũ sau rotation.
- **Rotate pepper rồi xóa key cũ ngay:** tài khoản chưa đăng nhập có thể không còn xác minh được.
- **Cố chuyển verifier cũ sang pepper mới mà không có password:** không thể tạo verifier tương đương chỉ từ verifier đã lưu.
- **Cho database quyết định KDF parameters không giới hạn:** record bị sửa có thể buộc server tiêu thụ CPU/bộ nhớ quá mức.
- **Tin pepper thay thế MFA và rate limit:** các tấn công trực tuyến và phishing vẫn có hiệu quả.

## 17. Ví dụ thiết kế record password

Một record có thể lưu cấu trúc logic như sau:

~~~json
{
  "userId": "user-123",
  "passwordScheme": "PBKDF2WithHmacSHA256+HMAC-SHA256",
  "formatVersion": 1,
  "salt": "base64-random-salt",
  "iterations": 250000,
  "derivedKeyBits": 256,
  "pepperVersion": "password-pepper-v3",
  "verifier": "base64-keyed-verifier"
}
~~~

Đây là ví dụ minh họa cấu trúc, không phải tham số khuyến nghị dùng nguyên trạng. Iteration count phải được benchmark và đặt theo policy hiện hành. Pepper thực tế không nằm trong JSON; chỉ có version để backend chọn key tương ứng từ kho bí mật.

Khi đăng nhập, backend kiểm tra formatVersion và scheme theo allowlist, xác thực tham số nằm trong giới hạn, lấy pepperVersion từ secret manager, tính lại verifier và so sánh. Nếu hợp lệ nhưng tham số cũ, backend có thể nâng cấp record theo quy trình đã nêu.

## 18. Checklist triển khai salt và pepper

- [ ] Mỗi password record có salt ngẫu nhiên riêng, tối thiểu theo policy (thường từ 16 byte).
- [ ] Salt được tạo bằng CSPRNG như SecureRandom và lưu cùng verifier.
- [ ] Dùng password hashing scheme/KDF phù hợp; không dùng hash nhanh trực tiếp.
- [ ] KDF parameters được benchmark, lưu cùng record và giới hạn khi đọc.
- [ ] Pepper là bí mật ngẫu nhiên, không nằm trong database hoặc source code.
- [ ] Pepper được lưu trong secret manager/KMS/HSM với quyền tối thiểu.
- [ ] Verifier dùng keyed construction được đánh giá, có domain separation và version.
- [ ] Record lưu pepper version/key ID nhưng không lưu pepper value.
- [ ] So sánh verifier theo cách chống timing phù hợp.
- [ ] Có rate limiting, MFA và giám sát đăng nhập bất thường.
- [ ] Có kế hoạch pepper rotation và giữ key cũ cho tới khi migration hoàn tất.
- [ ] Có quy trình reset password nếu pepper bị compromise hoặc không thể migrate record cũ.
- [ ] Không log password, salt-derived verifier hoặc pepper key material.
- [ ] Có kiểm thử đăng ký, đăng nhập, reset, migration và lỗi khi secret manager không khả dụng.

Salt và pepper giải quyết hai vấn đề khác nhau trong password storage. Salt công khai tạo đầu vào riêng cho từng bản ghi và ngăn lợi thế tra cứu tính sẵn; pepper là bí mật tách khỏi database để giảm khả năng kiểm tra đoán mật khẩu offline khi chỉ lộ dữ liệu xác thực. Chúng chỉ phát huy tác dụng khi kết hợp với KDF phù hợp, metadata có version, lưu pepper an toàn và quy trình rotation được thiết kế trước. Pepper không thay thế MFA, rate limiting hoặc bảo vệ ứng dụng; salt cũng không làm mật khẩu yếu trở nên mạnh.
