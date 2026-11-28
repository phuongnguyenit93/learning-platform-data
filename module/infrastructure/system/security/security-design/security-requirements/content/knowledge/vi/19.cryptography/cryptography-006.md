# Hashing mật khẩu

## 1. Mục tiêu và mô hình đe dọa

Hashing mật khẩu là cách tạo dữ liệu kiểm chứng để hệ thống xác nhận một mật khẩu được nhập mà không cần lưu lại mật khẩu rõ. Khi thiết kế đúng, kho xác thực chứa kết quả của một hàm dành cho mật khẩu cùng thông tin cần để kiểm chứng, thay vì chứa bí mật có thể được đọc trực tiếp hoặc giải mã lại bằng một khóa ứng dụng.

Mục tiêu không phải tuyên bố rằng mật khẩu không bao giờ bị đoán ra. Mục tiêu là làm cho mỗi lần thử ngoại tuyến có chi phí đáng kể, giảm khả năng dùng chung kết quả tính trước và giới hạn tác động khi dữ liệu xác thực bị lộ.

Trong thiết kế yêu cầu bảo mật, cần giả định kẻ tấn công có thể lấy được một bản sao cơ sở dữ liệu hoặc backup. Khi đó, họ có thể thử mật khẩu trên hạ tầng riêng, không phải đi qua API đăng nhập của ứng dụng. Rate limit của ứng dụng vẫn cần cho thử trực tuyến nhưng không thể trực tiếp giới hạn số lần đoán trên bản sao đã bị lấy đi.

Sau bài này, người học có thể:

- Phân biệt password hashing với hash nhanh, mã hóa và encoding.
- Đặc tả salt, profile thuật toán và tham số chi phí có thể kiểm chứng.
- Xác định vai trò, nơi lưu và vòng đời của pepper nếu thiết kế sử dụng nó.
- Thiết kế luồng tạo, kiểm chứng và nâng cấp bản ghi mật khẩu.
- Đặt yêu cầu về dữ liệu đầu vào, khả dụng, log và khôi phục.

Bài tập trung vào mật khẩu được máy chủ kiểm chứng. Access token ngẫu nhiên, khóa mã hóa, PIN mở khóa thiết bị cục bộ và bí mật xác thực máy-máy có mô hình khác; không tự áp toàn bộ thiết kế mật khẩu người dùng cho mọi loại secret.

## 2. Chọn đúng loại biến đổi

### 2.1. Encoding không bảo vệ mật khẩu

Base64 hoặc biểu diễn hexadecimal chỉ chuyển cách biểu diễn dữ liệu. Chúng không làm cho mật khẩu khó khôi phục với người đọc được bản ghi.

Một cột chứa Base64 của mật khẩu rõ vẫn là lưu mật khẩu theo cách có thể đảo lại trực tiếp. Base64 có thể được dùng để lưu salt hoặc hash dưới dạng văn bản, nhưng mức bảo vệ đến từ phép tính mật mã trước đó, không đến từ Base64.

### 2.2. Mã hóa giải quyết một nhu cầu khác

Mã hóa có khóa phù hợp khi hệ thống thật sự cần lấy lại dữ liệu gốc. Với mật khẩu đăng nhập, hệ thống thường chỉ cần kiểm chứng, không cần đọc lại mật khẩu người dùng.

Nếu chỉ mã hóa mật khẩu bằng một khóa ứng dụng, việc mất cả dữ liệu và khóa có thể cho phép khôi phục hàng loạt mật khẩu. Chức năng “quên mật khẩu” nên dẫn tới thiết lập mật khẩu mới qua một luồng phục hồi được bảo vệ, không phải giải mã mật khẩu cũ để gửi lại.

### 2.3. Hash nhanh không phải password hashing

Các hàm hash tổng quát được thiết kế để tính hiệu quả. Đặc tính đó không phù hợp làm cơ chế lưu mật khẩu chỉ bằng một lần gọi, vì kẻ có bản sao dữ liệu có thể kiểm tra rất nhiều dự đoán nhanh chóng. OWASP phân biệt các hàm dành cho mật khẩu như Argon2id hoặc PBKDF2 với việc chỉ dùng SHA-256 trực tiếp. [OWASP: Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

```text
Không phải profile lưu mật khẩu phù hợp:
  SHA-256(password)
  SHA-256(password || salt) với một lần hash nhanh

Mô hình cần đặc tả:
  PasswordKDF(password, salt, tham_số_chi_phí, profile)
```

Không tự thay một password KDF bằng vòng lặp hash do ứng dụng sáng tác. Cấu trúc thuật toán, cách xử lý đầu vào và tham số phải thuộc cơ chế đã được đánh giá và thư viện phù hợp.

## 3. Salt và pepper có mục tiêu khác nhau

### 3.1. Salt là dữ liệu riêng cho từng lần tạo bản ghi

Salt là đầu vào không cần giữ bí mật, được tạo để các mật khẩu giống nhau không dễ dùng chung cùng một kết quả tính. Hai tài khoản dùng cùng mật khẩu vẫn nên có salt độc lập và kết quả lưu khác nhau.

Salt cần được tạo bằng nguồn ngẫu nhiên phù hợp mật mã. Không dùng username, thời gian hệ thống hoặc một chuỗi cố định toàn ứng dụng thay cho salt ngẫu nhiên theo bản ghi.

Một lựa chọn trong profile của bài là salt 16 byte. RFC 9106 khuyến nghị độ dài này cho hashing mật khẩu với Argon2 và yêu cầu quan tâm tính riêng của salt. [RFC 9106, mục 3.1](https://www.rfc-editor.org/rfc/rfc9106.html#section-3.1)

Salt có thể lưu cạnh hash. Nó không có nhiệm vụ ngăn người đọc cơ sở dữ liệu biết đầu vào salt; nhiệm vụ của nó là chống việc dùng chung kết quả và tính trước hiệu quả trên nhiều bản ghi.

### 3.2. Không tạo salt mới khi kiểm chứng một bản ghi cũ

Khi kiểm chứng, hệ thống dùng salt đã lưu của bản ghi đó. Nếu tạo salt ngẫu nhiên khác rồi so sánh hash, kết quả sẽ khác ngay cả khi mật khẩu đúng.

Salt mới được dùng khi tạo một bản ghi mới: đăng ký, thay mật khẩu hoặc nâng cấp hash sau khi có mật khẩu đúng. Không dựa vào việc cùng một người dùng để tái sử dụng salt của họ cho mọi lần thay mật khẩu.

### 3.3. Pepper là secret của hệ thống

Pepper bổ sung một bí mật do hệ thống quản lý vào thiết kế bảo vệ mật khẩu. Khác salt, pepper không nên được lưu cùng bản ghi hash trong cùng phạm vi mà một lần lộ cơ sở dữ liệu sẽ lấy được tất cả.

Một thiết kế có thể dùng dịch vụ quản lý secret, KMS hoặc HSM theo mô hình triển khai. NIST nêu khả năng bổ sung một bước có khóa bí mật chỉ verifier biết; cách áp dụng cần được xác định cho chính scheme được chọn. [NIST SP 800-63B-4: Password verifiers](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/)

Không chỉ nối một chuỗi pepper vào mật khẩu rồi mặc định đó là thiết kế đã đúng. Cần xác định thư viện, vị trí sử dụng pepper, định dạng đầu vào, quyền truy cập secret và cách phân biệt các phiên bản pepper.

### 3.4. Pepper làm phát sinh yêu cầu vận hành

Nếu pepper không khả dụng, hệ thống có thể không kiểm chứng được mật khẩu theo scheme đó. Không được bỏ pepper hoặc thử một cách kiểm chứng yếu hơn để cho đăng nhập thành công.

Khi đổi pepper, không mặc định có thể tính lại mọi bản ghi từ hash cũ mà không biết mật khẩu. Tùy thiết kế, có thể cần nâng cấp lúc người dùng đăng nhập hoặc yêu cầu thiết lập lại mật khẩu. Trường hợp pepper bị lộ cần kế hoạch xử lý riêng, không chỉ đổi tên secret.

Nếu hệ thống dùng pepper, bản ghi có thể lưu định danh phiên bản khóa, còn giá trị secret nằm ở phạm vi được bảo vệ riêng. Các giá trị đầu vào từ client không được tự chọn khóa hoặc đường dẫn secret tùy ý.

## 4. Thuật toán, profile và tham số chi phí

### 4.1. Ưu tiên cơ chế dành cho mật khẩu

Argon2id là một lựa chọn hiện đại có tham số bộ nhớ, số lượt và mức song song. OWASP đưa ra một cấu hình tối thiểu tham khảo gồm 19 MiB bộ nhớ, hai lượt và mức song song một; không nên hiểu mức tối thiểu đó là cấu hình tối ưu cố định cho mọi hệ thống. [OWASP: Argon2id](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#argon2id)

RFC 9106 có các lựa chọn tham số với mục tiêu và ngân sách tài nguyên riêng, trong đó có phương án Argon2id 64 MiB, ba lượt và bốn lane cho bối cảnh hạn chế bộ nhớ hơn phương án đầu tiên của tài liệu. Sự khác nhau này cho thấy phải đọc bối cảnh khuyến nghị và đo trên môi trường đích. [RFC 9106, mục 4](https://www.rfc-editor.org/rfc/rfc9106.html#section-4)

Các phương án khác như scrypt hoặc PBKDF2 cần được chọn theo ràng buộc nền tảng và profile đã phê duyệt. Không tự fallback sang một thuật toán yếu hơn nếu thư viện ưu tiên chưa được cài hoặc gặp lỗi.

### 4.2. Chi phí có nhiều chiều

| Cơ chế/tham số | Ảnh hưởng cần xem xét |
| --- | --- |
| Bộ nhớ cho mỗi lần Argon2 | Chi phí mỗi phép thử và tổng bộ nhớ khi nhiều lần kiểm chứng đồng thời |
| Số lượt hoặc iteration | Thời gian tính mỗi lần tạo/kiểm chứng |
| Mức song song | Cách dùng tài nguyên tính toán theo triển khai và phần cứng |
| Độ dài salt và đầu ra | Định dạng dữ liệu và các điều kiện của profile |
| Số lần kiểm chứng đồng thời | Khả năng phục vụ và rủi ro cạn tài nguyên của verifier |

Không đổi đơn vị KiB, MiB, byte hoặc bit tùy ý khi chuyển từ tài liệu sang cấu hình. Một tên tham số đúng nhưng giá trị sai đơn vị có thể làm cấu hình khác rất xa mục tiêu.

### 4.3. Đo hiệu năng để đặt một hợp đồng thực tế

Ngưỡng chi phí phải làm cho đoán ngoại tuyến đắt hơn trong khi hệ thống vẫn phục vụ được lưu lượng hợp lệ. Cần đo trên phần cứng, runtime, thư viện và mức đồng thời tương ứng với môi trường triển khai.

Ví dụ, nếu một phép tính dùng 64 MiB, 100 phép tính đồng thời có thể cần khoảng 6.25 GiB chỉ cho phần bộ nhớ đó, chưa tính những thành phần khác. Một cấu hình mạnh trên một request có thể tạo lỗi khả dụng nếu không có giới hạn đồng thời phù hợp.

Không giảm work factor tự động khi tải cao hoặc có nhiều lần đăng nhập thất bại. Điều đó làm policy lưu mật khẩu phụ thuộc vào điều kiện mà bên ngoài có thể tác động. Cần kiểm soát tải bằng admission, rate limit và ngân sách tài nguyên đã thiết kế.

### 4.4. Profile phải có định danh và nội dung bất biến

Một profile cần xác định thuật toán, phiên bản nếu có, tham số, cách xử lý mật khẩu và định dạng lưu. Nếu đổi một điều kiện ảnh hưởng kết quả, phải tạo phiên bản profile mới.

```text
PASSWORD_PROFILE_A:
  Thuật toán và phiên bản được phê duyệt.
  Salt 16 byte từ nguồn ngẫu nhiên mật mã.
  Bộ tham số chi phí và độ dài đầu ra cố định.
  Quy tắc xử lý ký tự/byte được xác định.
  Cách dùng pepper và định danh khóa nếu có.
```

Không tái sử dụng cùng một tên profile nhưng thay work factor hoặc normalization mà không lưu lại thông tin cần để kiểm chứng dữ liệu cũ.

## 5. Bản ghi và dữ liệu đầu vào

### 5.1. Lưu đủ thông tin để kiểm chứng và nâng cấp

Bản ghi thường cần định danh scheme/profile, salt và kết quả tính. Nếu tham số không được ánh xạ bất biến từ profile, phải lưu chúng theo một định dạng được kiểm soát. Một số thư viện cung cấp chuỗi tự mô tả; hệ thống vẫn cần parser và allowlist phù hợp.

| Trường | Mục đích |
| --- | --- |
| Algorithm/profile ID | Chọn đúng cách kiểm chứng đã được phê duyệt |
| Phiên bản và tham số | Tái lập chính xác phép tính của bản ghi |
| Salt | Đầu vào riêng của bản ghi |
| Hash/verifier output | Dữ liệu đối chiếu với kết quả tính lại |
| Pepper key ID nếu dùng | Chọn đúng phiên bản secret trong phạm vi được cho phép |
| Credential version | Hỗ trợ cập nhật đồng thời và nâng cấp an toàn |

Không trả các trường này qua API hồ sơ người dùng hoặc log nghiệp vụ thông thường. Hash không phải mật khẩu rõ nhưng vẫn là dữ liệu nhạy cảm có thể phục vụ tấn công ngoại tuyến.

### 5.2. Tham số lưu trữ cũng phải được kiểm soát trước khi dùng

Một bản ghi tự mô tả có thể chứa tham số sai hoặc quá lớn do dữ liệu hỏng, migration lỗi hoặc tác động không được phép. Không đưa trực tiếp một iteration count hay memory cost tùy ý từ bản ghi vào hàm tính trước khi kiểm tra giới hạn.

Registry profile có thể giới hạn những scheme được đọc và những tham số được chấp nhận. Scheme không biết, thiếu salt hoặc dữ liệu sai định dạng phải không dẫn tới một nhánh cho phép đăng nhập hay kiểm tra plaintext dự phòng.

### 5.3. Mật khẩu phải có hợp đồng ký tự nhất quán

Hệ thống cần xác định giới hạn độ dài, cách biểu diễn ký tự và quy tắc normalization trước hashing. Nếu chọn NFC cho Unicode, phải áp dụng nhất quán ở đăng ký, đổi mật khẩu và kiểm chứng. NIST khuyến nghị NFC khi chấp nhận mật khẩu Unicode và yêu cầu kiểm chứng toàn bộ mật khẩu thay vì cắt ngầm. [NIST SP 800-63B-4: Password processing](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/)

Không tự trim, đổi hoa/thường hoặc cắt chuỗi ở một lớp mà các lớp khác không biết. Nếu sản phẩm chủ động có quy tắc biến đổi nào, quy tắc đó phải thuộc hợp đồng được đánh giá và phiên bản hóa.

Giới hạn tính theo ký tự, UTF-16 code unit hay byte cần được ghi rõ. Cùng một chuỗi tiếng Việt có thể có số byte khác số ký tự; không được suy ra hai giới hạn là tương đương.

### 5.4. Không lưu mật khẩu để hỗ trợ kỹ thuật

Mật khẩu chỉ nên tồn tại trong phạm vi xử lý cần thiết. Không đưa nó vào telemetry, query string, sự kiện nghiệp vụ hoặc bản ghi lỗi. Màn hình hỗ trợ không được có chức năng đọc lại mật khẩu người dùng.

Luồng reset, thay mật khẩu và các kênh đăng ký khác nhau phải dùng cùng dịch vụ tạo bản ghi được phê duyệt, tránh một đường nhập phụ vẫn lưu plaintext hoặc dùng profile cũ.

## 6. Viết yêu cầu bảo mật có thể nghiệm thu

### 6.1. Yêu cầu nền tảng

```text
REQ-PWD-HASH-01 — Lưu dữ liệu kiểm chứng mật khẩu

Mọi mật khẩu do hệ thống quản lý để xác thực người dùng phải được chuyển
thành verifier bằng password hashing scheme thuộc profile đã phê duyệt.

Mỗi lần tạo bản ghi phải dùng salt mới từ nguồn ngẫu nhiên mật mã và lưu
đủ thông tin để kiểm chứng đúng profile. Không lưu mật khẩu rõ, bản encoding
của mật khẩu rõ hoặc ciphertext có thể khôi phục mật khẩu thay cho verifier.

Khi profile không khả dụng hoặc bản ghi không hợp lệ, hệ thống không được
dùng cơ chế yếu hơn hoặc bỏ qua kiểm chứng để xác thực thành công.
```

### 6.2. Các yêu cầu bổ sung

| Mã | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| REQ-PWD-HASH-02 | Salt phải mới theo mỗi lần tạo bản ghi, đạt độ dài profile và không lấy từ định danh dự đoán được | Dữ liệu tạo nhiều bản ghi và luồng sinh salt |
| REQ-PWD-HASH-03 | Thuật toán, tham số và xử lý ký tự phải được phiên bản hóa; dữ liệu cũ đọc bằng đúng profile cũ được cho phép | Bản ghi và registry profile |
| REQ-PWD-HASH-04 | Parser phải giới hạn định dạng, kích thước và tham số trước khi thực hiện phép tính tốn tài nguyên | Trường hợp bản ghi sai và tham số vượt ngưỡng |
| REQ-PWD-HASH-05 | Luồng kiểm chứng phải dùng phép so sánh phù hợp của thư viện, không tự so sánh từng ký tự rồi dừng sớm | Vị trí so sánh và hợp đồng hàm được dùng |
| REQ-PWD-HASH-06 | Profile yếu hoặc cũ phải có kế hoạch nâng cấp mà không ghi đè một lần thay mật khẩu mới hơn | Luồng rehash và tình huống cạnh tranh |
| REQ-PWD-HASH-07 | Mật khẩu, pepper và verifier không được lộ qua log hoặc response không phục vụ xác thực | Response, log, trace và các đường lỗi |
| REQ-PWD-HASH-08 | Nếu dùng pepper, secret phải nằm trong phạm vi được bảo vệ riêng và có hành vi rõ khi mất khả dụng hoặc cần xoay | Quyền truy cập secret, phục hồi và luồng lỗi |
| REQ-PWD-HASH-09 | Năng lực phục vụ phải được kiểm chứng với chi phí profile và giới hạn đồng thời đã chọn | Đo độ trễ, CPU, bộ nhớ và hành vi khi quá tải |

Không coi việc một cột được đặt tên `password_hash` là bằng chứng thực thi. Cần quan sát luồng tạo, định dạng thực tế, kết quả kiểm chứng và các đường thay đổi mật khẩu.

## 7. Ví dụ Java: một profile PBKDF2 có giới hạn rõ

### 7.1. Phạm vi của ví dụ

Ví dụ dùng PBKDF2-HMAC-SHA-256 để minh họa bằng các API JDK. Nó không có nghĩa PBKDF2 phải thay Argon2id trong mọi hệ thống. Profile thực tế vẫn cần được lựa chọn và phê duyệt theo phần trước.

Mốc 600.000 iteration phù hợp với một mốc tham khảo hiện hành của OWASP cho PBKDF2-HMAC-SHA-256. Con số này không thay đo năng lực, rà soát định kỳ hoặc các yêu cầu riêng của môi trường. [OWASP: PBKDF2](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#pbkdf2)

Profile minh họa có salt 16 byte, đầu ra 32 byte và định danh bất biến chứa phiên bản cấu hình. Tham số không được lấy tùy ý từ request hoặc bản ghi:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.Objects;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordHashExample {

    private static final String PROFILE = "pbkdf2-sha256-600k-v1";
    private static final int ITERATIONS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int HASH_BYTES = 32;
    private static final SecureRandom RANDOM = new SecureRandom();

    public record StoredHash(
            String profile,
            String saltBase64,
            String hashBase64) {
    }

    private PasswordHashExample() {
    }

    public static StoredHash create(char[] password)
            throws GeneralSecurityException {

        Objects.requireNonNull(password, "password");

        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] hash = derive(password, salt);

        try {
            return new StoredHash(
                    PROFILE,
                    Base64.getEncoder().encodeToString(salt),
                    Base64.getEncoder().encodeToString(hash));
        } finally {
            Arrays.fill(hash, (byte) 0);
        }
    }

    public static boolean verify(char[] password, StoredHash stored)
            throws GeneralSecurityException {

        Objects.requireNonNull(password, "password");

        if (stored == null || !PROFILE.equals(stored.profile())) {
            return false;
        }

        if (stored.saltBase64() == null || stored.hashBase64() == null
                || stored.saltBase64().length() != 24
                || stored.hashBase64().length() != 44) {
            return false;
        }

        byte[] salt;
        byte[] expected;

        try {
            salt = Base64.getDecoder().decode(stored.saltBase64());
            expected = Base64.getDecoder().decode(stored.hashBase64());
        } catch (IllegalArgumentException invalidEncoding) {
            return false;
        }

        if (salt.length != SALT_BYTES || expected.length != HASH_BYTES) {
            return false;
        }

        byte[] actual = derive(password, salt);
        try {
            return MessageDigest.isEqual(expected, actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    private static byte[] derive(char[] password, byte[] salt)
            throws GeneralSecurityException {

        PBEKeySpec spec = new PBEKeySpec(
                password, salt, ITERATIONS, HASH_BYTES * 8);

        try {
            SecretKeyFactory factory =
                    SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
            return factory.generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }
}
```

`SecureRandom` cung cấp nguồn sinh số ngẫu nhiên phù hợp mật mã. Ví dụ không seed bằng một hằng số hoặc giá trị dự đoán được. [Java SE 21: SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html)

### 7.2. Vì sao bản ghi chỉ chứa profile thay vì iteration tùy ý?

Ví dụ chỉ nhận một profile được biết trước, nên một bản ghi không thể yêu cầu thực hiện hàng tỷ vòng bằng cách thay trường iteration. Dự án có nhiều profile cần một registry hữu hạn cùng parser giới hạn dữ liệu trước khi chọn verifier.

Định danh `pbkdf2-sha256-600k-v1` phải luôn ánh xạ về cùng thuật toán, tham số và quy tắc đầu vào. Nếu cần tăng iteration, phải tạo profile mới và giữ khả năng đọc profile cũ trong thời gian migration được phê duyệt.

Độ dài Base64 24 và 44 trong ví dụ tương ứng đầu ra chuẩn có padding cho salt 16 byte và hash 32 byte. Đây là lựa chọn định dạng của ví dụ; không áp các độ dài này cho mọi scheme hoặc cách mã hóa khác.

### 7.3. Xử lý dữ liệu mật khẩu trong bộ nhớ

`PBEKeySpec` giữ bản sao mật khẩu và có `clearPassword()` để xóa bản sao nội bộ đó. Mảng `char[]` của caller vẫn cần được quản lý theo vòng đời của caller. [Java SE 21: PBEKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html)

Không chuyển mật khẩu sang `String` chỉ để log hoặc truyền giữa các lớp nếu không cần. Việc dùng mảng có thể hỗ trợ giảm thời gian giữ dữ liệu, nhưng không chứng minh toàn bộ bản sao trong framework, provider hoặc bộ nhớ hệ thống đã được xóa tuyệt đối.

### 7.4. Phép so sánh và luồng lỗi

Ví dụ dùng `MessageDigest.isEqual` cho hai mảng verifier cùng độ dài, thay cho vòng lặp tự dừng tại byte khác đầu tiên. Điều này không đồng nghĩa mọi nhánh của luồng đăng nhập có thời gian giống hệt nhau. [Java SE 21: MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D))

Lỗi provider được ném ra để lớp tích hợp xử lý như sự cố, không bị chuyển thành nhánh fallback sang hash nhanh. Bản ghi sai hoặc profile không biết không được kiểm chứng thành công; vận hành cần phân biệt các lỗi này nội bộ mà không trả chi tiết nhạy cảm cho caller.

Ví dụ chưa triển khai validation mật khẩu, normalization, pepper, rate limit, repository hoặc rehash. Các mục đó vẫn phải có hợp đồng ở luồng tích hợp; không xem lớp minh họa như một hệ thống xác thực hoàn chỉnh.

## 8. Luồng tạo, kiểm chứng và nâng cấp

### 8.1. Tạo bản ghi mới

```text
Nhận mật khẩu qua kênh được bảo vệ
    → áp dụng hợp đồng mật khẩu và xử lý ký tự đã chọn
    → chọn profile hiện hành từ cấu hình được kiểm soát
    → tạo salt mới
    → lấy pepper đúng phiên bản nếu scheme yêu cầu
    → tính verifier
    → lưu bản ghi đầy đủ trong giao dịch phù hợp
    → kết thúc vòng đời dữ liệu rõ không còn cần thiết
```

Đăng ký, đổi mật khẩu, reset và nhập tài khoản qua một kênh được phép không nên có các cách lưu riêng không đồng nhất. Một đường phụ dùng profile yếu có thể làm mất bảo đảm của cả hệ thống dù luồng đăng ký chính đã đúng.

### 8.2. Kiểm chứng

Hệ thống tải đúng bản ghi gắn với tài khoản, kiểm tra định dạng/profile và áp dụng lại đúng phép xử lý. Không tạo salt mới hoặc dùng tham số hiện hành để kiểm chứng bản ghi cũ nếu các tham số đó đã thay đổi.

Nếu một username không tồn tại có luồng xử lý khác xa username tồn tại, có thể xuất hiện tín hiệu suy ra tài khoản. Thiết kế đăng nhập cần xét thông báo, thời gian và cơ chế đối chứng phù hợp, trong giới hạn ngân sách chống lạm dụng.

Không giải quyết vấn đề này bằng cách dùng một hash quá rẻ cho mọi tài khoản. Kiểm soát khả dụng, enumeration và hashing phải được phối hợp thay vì hy sinh một mục tiêu để chữa mục tiêu khác.

### 8.3. Rehash sau khi xác nhận mật khẩu đúng

Một cách nâng cấp thông thường là kiểm chứng bằng profile đang lưu, sau đó khi mật khẩu đúng thì tạo verifier mới theo profile hiện hành với salt mới.

```text
Đọc bản ghi và credential version hiện tại
    → kiểm chứng bằng profile của bản ghi
    → nếu không khớp: không nâng cấp từ dữ liệu chưa được xác nhận
    → nếu khớp và cần nâng cấp: tạo verifier mới
    → cập nhật có điều kiện theo credential version đã đọc
```

Không thể lấy hash cũ rồi gọi một KDF mới lên nó và mặc định kết quả là mật khẩu đã được băm trực tiếp theo profile mới. Nếu một thiết kế chuyển tiếp dùng hash lồng nhau, đó là scheme riêng cần được mô tả và đánh giá, không phải phép migration tự động tương đương.

### 8.4. Tránh ghi đè một lần thay mật khẩu mới hơn

Một request đăng nhập có thể đang rehash trong lúc request khác reset mật khẩu. Nếu rehash ghi đè vô điều kiện, nó có thể khôi phục verifier của mật khẩu cũ sau khi reset đã thành công.

Cần transaction hoặc cập nhật có điều kiện theo phiên bản/verifier đã đọc. Khi điều kiện không còn đúng, xử lý theo hợp đồng cạnh tranh và không tự ghi đè dữ liệu mới.

### 8.5. Tài khoản không đăng nhập lại

Lazy rehash không tự nâng cấp các tài khoản lâu không sử dụng. Kế hoạch chuyển đổi cần xác định thời gian giữ verifier cũ, thời điểm yêu cầu reset hoặc vô hiệu hóa cơ chế cũ và cách xử lý các tài khoản còn lại.

Backup và môi trường phục hồi có thể chứa profile hoặc pepper key ID cũ. Khôi phục phải được kiểm soát để không âm thầm làm sống lại mật khẩu đã thay hoặc một scheme đã bị loại bỏ khỏi sử dụng.

## 9. Khả dụng và ranh giới tài nguyên

### 9.1. Phép tính đắt cần admission phù hợp

Hashing cố ý tăng chi phí mỗi phép thử. Đó cũng là công việc mà API đăng ký, đăng nhập và reset có thể bị gọi lặp lại. Cần giới hạn tần suất, số phép tính đồng thời, hàng đợi và kích thước đầu vào theo rủi ro của từng luồng.

Không chỉ bảo vệ endpoint đăng nhập trong khi endpoint kiểm tra mật khẩu hiện tại hoặc đăng ký có thể tạo số phép tính không giới hạn. Những đường sử dụng cùng tài nguyên cần được kiểm kê.

### 9.2. Không hạ chi phí khi gặp sự cố

Nếu không còn tài nguyên hoặc dịch vụ secret cần thiết không khả dụng, hệ thống phải xử lý theo hợp đồng lỗi. Không chấp nhận mật khẩu mà chưa kiểm chứng, bỏ pepper, đổi sang SHA-256 hoặc lưu một profile rẻ tạm thời mà không có quyết định bảo mật riêng.

Khi profile mới được triển khai, cần xem cả chi phí verify và rehash trong cùng lần đăng nhập. Một request nâng cấp có thể thực hiện hai phép tính, làm mức tải khác trường hợp chỉ verify.

### 9.3. Giới hạn đầu vào không phải cắt ngầm

Một request quá lớn có thể bị từ chối trước khi thực hiện KDF theo hợp đồng đã công bố. Không cắt nó thành một tiền tố rồi xác thực như thể đó là toàn bộ mật khẩu.

Trong migration từ một scheme có giới hạn đầu vào riêng, cần giữ ngữ nghĩa kiểm chứng cũ theo policy và chuyển đổi có chủ ý. Ví dụ, giới hạn 72 byte của bcrypt trong các hệ thống legacy không phải giới hạn 72 ký tự Unicode cho mọi cách triển khai. [OWASP: bcrypt input limits](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#input-limits-of-bcrypt)

## 10. Ma trận nghiệm thu

### 10.1. Tính đúng đắn và bảo vệ dữ liệu

| Tình huống | Kỳ vọng | Bằng chứng |
| --- | --- | --- |
| Tạo bản ghi rồi nhập đúng mật khẩu | Kiểm chứng thành công theo profile đã lưu | Kết quả verifier và profile |
| Nhập mật khẩu khác | Không xác thực thành công | Kết quả xử lý và không tạo phiên hợp lệ |
| Cùng mật khẩu tạo hai bản ghi độc lập | Salt và kết quả trong mẫu khác nhau theo thiết kế | Bản ghi và luồng CSPRNG; không chỉ dựa vào mẫu |
| Đổi mật khẩu | Tạo verifier mới với salt mới | Dữ liệu trước/sau và kiểm chứng mật khẩu cũ/mới |
| Sai Base64, thiếu salt, sai độ dài | Không vào nhánh thành công | Kết quả parse và không bypass |
| Profile không được hỗ trợ hoặc tham số vượt ngưỡng | Không tính tùy ý hoặc fallback yếu | Luồng chọn profile và ngân sách tài nguyên |
| Mật khẩu Unicode hoặc gần giới hạn đầu vào | Hành vi đúng hợp đồng, không cắt ngầm | Các đường tạo và kiểm chứng |
| Provider hoặc pepper không khả dụng | Không cấp phiên dựa trên dữ liệu chưa được kiểm chứng | Nhánh lỗi và tác động thực tế |
| Rehash cạnh tranh với reset | Không ghi đè mật khẩu mới bằng verifier cũ | Phiên bản dữ liệu và kết quả cập nhật |
| Đường lỗi, trace hoặc response hồ sơ | Không có mật khẩu, pepper hoặc verifier ngoài phạm vi được phép | Response và nguồn quan sát |

### 10.2. Kịch bản nâng cấp profile

```text
Given:
  Tài khoản có verifier thuộc profile cũ còn được phép kiểm chứng.
  Profile hiện hành có cấu hình mới đã được phê duyệt.

When:
  Người dùng nhập đúng mật khẩu và luồng nâng cấp hoàn tất.

Then:
  Verifier mới mang đúng định danh profile hiện hành và salt mới.
  Mật khẩu tiếp tục được kiểm chứng đúng theo hợp đồng ký tự.
  Không lưu thêm mật khẩu rõ hoặc bản sao phục vụ nâng cấp về sau.
  Cập nhật không ghi đè một credential version mới hơn.
```

### 10.3. Kiểm chứng tham số và hiệu năng

Cần kiểm tra giá trị có hiệu lực, không chỉ giá trị ghi trong tài liệu. Một wrapper có thể có default khác hoặc bỏ qua tham số nếu dùng sai API.

Bằng chứng hiệu năng nên ghi phần cứng, runtime/provider, phiên bản thư viện, profile, mức đồng thời và phân vị độ trễ. Kết quả trên máy phát triển không tự đại diện cho giới hạn tài nguyên của container production.

Các test vector của cơ chế và thư viện có thể giúp kiểm chứng tính tương thích. Không tự kết luận một cài đặt mật mã đã đúng chỉ vì create và verify do cùng một đoạn code viết ra khớp nhau; cả hai có thể đang lặp cùng một lỗi.

### 10.4. Phạm vi của phép so sánh

Kiểm tra dùng đúng hàm so sánh là bằng chứng triển khai cần thiết, nhưng không đủ để tuyên bố toàn bộ API không có kênh thời gian. Các nhánh tài khoản không tồn tại, bản ghi lỗi, profile khác và rehash có thể có đặc tính khác.

Yêu cầu chống lộ thông tin qua luồng đăng nhập cần có đánh giá riêng theo mô hình đe dọa và khả năng đo. Không dùng một assertion thời gian nhỏ trên một lần chạy để chứng minh một bảo đảm tuyệt đối.

## 11. Vận hành, backup và xử lý sự cố

### 11.1. Bảo vệ verifier như dữ liệu xác thực

Quyền đọc kho mật khẩu phải được giới hạn theo nhiệm vụ. Không sao chép verifier sang analytics, môi trường thử nghiệm hoặc dịch vụ không cần nó chỉ vì trường dữ liệu đã là hash.

Backup, bản sao dữ liệu và export đều thuộc phạm vi. Mã hóa lưu trữ và kiểm soát quyền đọc là các lớp bổ sung, không phải lý do để bỏ KDF dành cho mật khẩu.

### 11.2. Phân biệt lộ bản sao với quyền sửa dữ liệu

Password hashing chủ yếu tăng khả năng chống đoán khi verifier bị lấy đi. Nếu một bên có thể sửa kho xác thực, họ có thể tác động đến bản ghi hoặc quan hệ tài khoản; cần yêu cầu toàn vẹn, quyền ghi và audit độc lập.

Không nên mô tả thuật toán băm là cơ chế tự ngăn mọi loại chiếm quyền ứng dụng hoặc cơ sở dữ liệu. Phạm vi bảo vệ phải phù hợp với năng lực thực tế của cơ chế.

### 11.3. Kế hoạch khi hash hoặc pepper bị lộ

Cần xác định dữ liệu bị lấy, profile và thời điểm liên quan, khả năng tiếp cận pepper, mức độ ảnh hưởng tới tài khoản và các bước phục hồi được phê duyệt. Tăng work factor cho những bản ghi mới không tự sửa một bản sao hash cũ đã nằm ngoài hệ thống.

Việc reset mật khẩu, vô hiệu hóa phiên hoặc xoay secret thuộc kế hoạch ứng phó tương ứng. Không gửi mật khẩu cũ cho người dùng hoặc cố “giải mã hash” để hỗ trợ điều tra.

### 11.4. Theo dõi chuyển đổi mà không log secret

Có thể quan sát số bản ghi theo profile, tỷ lệ nâng cấp, lỗi parser, lỗi provider và chi phí verify/rehash. Không cần log hash hay mật khẩu để biết migration còn bao nhiêu tài khoản.

Khi thay thư viện hoặc provider, cần kiểm chứng tương thích dữ liệu và profile cũ còn trong phạm vi. Một thay đổi dependency không được âm thầm đổi quy tắc ký tự, salt hoặc định dạng đầu ra.

## 12. Những kết luận cần tránh

### 12.1. “Đầu ra 256 bit nên mật khẩu có độ mạnh 256 bit”

Độ dài verifier không biến mật khẩu yếu thành một secret có entropy tương ứng. Kẻ đoán vẫn có thể thử các mật khẩu phổ biến với chi phí của scheme. Chất lượng mật khẩu và các yếu tố xác thực khác có mục tiêu riêng.

### 12.2. “Có salt nên có thể dùng một lần SHA-256”

Salt giải quyết việc dùng chung kết quả; chi phí mỗi phép thử là một điều kiện khác. Cần cả scheme thích hợp và salt theo bản ghi.

### 12.3. “Pepper có thể lưu trong cùng bảng cho tiện”

Khi secret đi cùng dữ liệu mà nó cần bảo vệ trong cùng phạm vi bị lộ, lớp phân tách dự kiến không còn. Cần thiết kế quyền và vòng đời secret đúng với mục tiêu sử dụng pepper.

### 12.4. “Chỉ cần tăng iteration mà không đổi profile”

Nếu verifier cũ được kiểm chứng bằng tham số mới không đúng, người dùng có thể không đăng nhập được. Nội dung profile đã lưu phải bất biến hoặc bản ghi phải tự mô tả đầy đủ thông tin được kiểm soát.

### 12.5. “Đăng nhập đúng một lần chứng minh toàn bộ cơ chế an toàn”

Cần kiểm chứng cả dữ liệu sai, nhiều bản ghi, Unicode, migration, cạnh tranh, đường lỗi và ngân sách tài nguyên. Tính đúng đắn chức năng chỉ là một phần của hợp đồng bảo mật.

## 13. Hồ sơ yêu cầu mẫu

```text
Tài sản:
  Mật khẩu người dùng và tính toàn vẹn của quyết định xác thực.

Mô hình đe dọa:
  Bản sao cơ sở dữ liệu hoặc backup có thể bị đọc ngoài hệ thống.
  Đường xác thực cũng có thể bị gọi với lưu lượng cao hoặc dữ liệu lỗi.

Thiết kế:
  Dùng password hashing profile đã phê duyệt và phiên bản hóa.
  Salt mới cho từng lần tạo bản ghi, từ nguồn ngẫu nhiên mật mã.
  Lưu đủ metadata để kiểm chứng; không lưu plaintext hoặc ciphertext thay thế.
  Pepper nếu có nằm ở phạm vi bảo vệ riêng và có kế hoạch vòng đời.

Luồng kiểm chứng:
  Kiểm tra profile/định dạng trước khi tính.
  Áp dụng đúng hợp đồng ký tự và so sánh bằng hàm phù hợp.
  Không có nhánh bỏ qua hoặc giảm bảo vệ khi lỗi.

Vòng đời:
  Rehash khi có mật khẩu đúng, cập nhật có điều kiện chống ghi đè.
  Có kế hoạch cho tài khoản lâu không đăng nhập và backup chứa profile cũ.

Bằng chứng:
  Bản ghi mẫu, tham số có hiệu lực, test vector/tương thích, luồng reset,
  Unicode, bản ghi lỗi, cạnh tranh, hiệu năng và quan sát không lộ secret.
```

Hashing mật khẩu đáp ứng mục tiêu khi kho xác thực không giữ mật khẩu có thể đọc lại, mỗi phép đoán phải chịu chi phí đã chọn và hệ thống vẫn kiểm chứng đúng qua các lần thay đổi. Yêu cầu bảo mật cần nối được thuật toán, salt, tham số, xử lý đầu vào, vòng đời secret và bằng chứng nghiệm thu thành một hợp đồng thực thi rõ ràng.
