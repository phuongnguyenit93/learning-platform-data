# Password hashing trong quản lý mật khẩu

**Password hashing** là quá trình biến mật khẩu thành một giá trị kiểm chứng bằng hàm băm mật khẩu chuyên dụng. Hệ thống lưu giá trị đã băm cùng salt và tham số thuật toán, rồi dùng chúng để kiểm tra mật khẩu người dùng nhập ở lần đăng nhập sau. Hệ thống không cần lưu mật khẩu gốc và cũng không thể khôi phục mật khẩu từ giá trị băm theo một thao tác giải mã thông thường.

Mật khẩu do con người chọn thường có entropy thấp hơn khóa mật mã được sinh ngẫu nhiên. Kẻ tấn công có thể thử hàng triệu hoặc hàng tỷ phỏng đoán ngoại tuyến nếu lấy được cơ sở dữ liệu tài khoản. Vì vậy, hàm băm mật khẩu cần được thiết kế để làm mỗi lần đoán tốn thời gian hoặc bộ nhớ, đồng thời dùng salt riêng cho từng mật khẩu. Đây là một phần quan trọng của quản lý thông tin xác thực và cần được kết hợp với kiểm soát truy cập, giới hạn đăng nhập, MFA và quy trình xử lý sự cố.

## 1. Password hashing khác mã hóa như thế nào?

Mã hóa được thiết kế để dữ liệu có thể khôi phục bằng khóa giải mã. Password hashing được thiết kế để kiểm tra một phỏng đoán mà không cần khôi phục mật khẩu ban đầu.

| Cơ chế | Có thể khôi phục dữ liệu gốc? | Mục đích |
|---|---|---|
| Mã hóa đối xứng | Có, nếu có khóa giải mã phù hợp. | Bảo vệ dữ liệu cần đọc lại. |
| Mã hóa bất đối xứng | Có, bằng khóa riêng tương ứng trong mô hình mã hóa. | Trao đổi dữ liệu hoặc khóa. |
| Hash mật khẩu | Không có thao tác giải mã. | Lưu bộ kiểm chứng để xác minh mật khẩu. |
| KDF mật khẩu | Tạo đầu ra dẫn xuất từ mật khẩu và tham số. | Làm chậm việc đoán mật khẩu; một số KDF còn hỗ trợ dẫn xuất khóa. |

Không nên mã hóa mật khẩu đăng nhập rồi lưu khóa giải mã bên cạnh cơ sở dữ liệu. Nếu ứng dụng chỉ cần xác minh người dùng biết mật khẩu, hãy lưu password hash bằng một thuật toán chuyên dụng. Khi ứng dụng thực sự cần dùng mật khẩu để mở dữ liệu đã mã hóa, đó là một bài toán dẫn xuất khóa khác; cần thiết kế riêng và không dùng password hash đăng nhập như khóa mã hóa.

## 2. Vì sao không dùng SHA-256 hoặc MD5 trực tiếp?

Các hàm băm tổng quát như SHA-256 được tối ưu để tính nhanh. Tốc độ đó có lợi cho kiểm tra tính toàn vẹn dữ liệu lớn, nhưng lại có hại khi lưu mật khẩu: kẻ tấn công có thể thử rất nhiều mật khẩu trong thời gian ngắn trên CPU hoặc GPU.

MD5 và SHA-1 còn có điểm yếu về va chạm và không phù hợp cho lưu mật khẩu. Ngay cả SHA-256 hiện vẫn là hàm băm mật mã hữu ích, nhưng dùng trực tiếp một lần như SHA-256(password) không tạo ra cơ chế lưu mật khẩu đủ chậm.

Ví dụ cách làm không an toàn:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] hash = digest.digest(password.getBytes(StandardCharsets.UTF_8));
~~~

Đoạn mã trên không có salt riêng và chỉ thực hiện một lần băm nhanh. Kẻ tấn công có thể tạo trước bảng phỏng đoán, tận dụng GPU hoặc kiểm tra cùng một mật khẩu trên nhiều tài khoản. Việc lặp SHA-256 thủ công một số lần cũng không thay thế được một password hashing scheme đã được thiết kế và phân tích chuyên môn.

Hàm băm mật khẩu chuyên dụng sử dụng tham số chi phí để làm mỗi lần kiểm tra tốn tài nguyên hơn. Một số thuật toán còn tiêu tốn bộ nhớ đáng kể để làm giảm lợi thế của phần cứng song song chuyên dụng.

## 3. Salt: giá trị ngẫu nhiên riêng cho từng mật khẩu

**Salt** là dữ liệu ngẫu nhiên được tạo riêng cho mỗi lần thiết lập mật khẩu và được lưu cùng password hash. Salt không phải bí mật. Mục đích của salt là khiến cùng một mật khẩu ở hai tài khoản tạo ra hai giá trị dẫn xuất khác nhau, đồng thời ngăn việc tái sử dụng hiệu quả các bảng băm được tính trước.

Ví dụ, hai người dùng cùng chọn một mật khẩu:

~~~text
User A: password + salt_A -> password_hash_A
User B: password + salt_B -> password_hash_B
~~~

Vì salt khác nhau, hai giá trị hash cũng khác nhau. Khi xác minh, hệ thống đọc salt đã lưu của tài khoản, chạy cùng thuật toán và tham số với mật khẩu được nhập, rồi so sánh kết quả.

Salt nên được tạo bằng bộ sinh số ngẫu nhiên mật mã như **SecureRandom**, có độ dài đủ lớn và không được tái sử dụng có chủ ý giữa các bản ghi. 16 byte (128 bit) là lựa chọn phổ biến cho salt. Không dùng username, email, số điện thoại hoặc thời gian hiện tại làm salt vì các giá trị đó có thể đoán được và thường bị lặp.

Salt được lưu công khai cùng hash:

| Trường | Có bí mật không? | Vai trò |
|---|---|---|
| Salt | Không | Làm cho mỗi hash riêng biệt và chống bảng tra cứu dùng chung. |
| Password hash | Không phải mật khẩu gốc, nhưng cần bảo vệ | Dữ liệu để xác minh phỏng đoán mật khẩu. |
| Pepper | Có | Bí mật bổ sung do hệ thống quản lý, dùng cùng password hashing scheme nếu thiết kế hỗ trợ. |

Salt không làm cho một mật khẩu yếu trở nên mạnh. Nó khiến việc tấn công phải tính lại cho từng salt, nhưng kẻ tấn công vẫn có thể thử các mật khẩu phổ biến cho từng tài khoản.

## 4. Các thuật toán password hashing phổ biến

Lựa chọn thuật toán phải xét đến mức chống dò đoán, khả năng tương thích, thư viện đang được duy trì và yêu cầu chứng nhận.

| Thuật toán | Đặc điểm | Khi cân nhắc |
|---|---|---|
| Argon2id | KDF mật khẩu có tính memory-hard; kết hợp đặc tính của Argon2i và Argon2d. Có các tham số bộ nhớ, số vòng và mức song song. | Lựa chọn ưu tiên phổ biến cho hệ thống mới nếu thư viện và môi trường hỗ trợ. |
| scrypt | KDF memory-hard, dùng các tham số chi phí CPU/bộ nhớ và mức song song. | Phù hợp khi cần KDF chống tấn công song song và có thư viện đáng tin cậy. |
| bcrypt | Thuật toán password hashing có tham số cost; được sử dụng rộng rãi và có định dạng lưu trữ phổ biến. | Hữu ích cho hệ thống cần tương thích rộng; cần chú ý giới hạn độ dài đầu vào của triển khai. |
| PBKDF2 | KDF dựa trên PRF như HMAC; số vòng lặp điều chỉnh chi phí tính toán. | Phù hợp khi cần khả năng tương thích Java/JCA hoặc môi trường yêu cầu thuật toán được phê duyệt, chẳng hạn một số cấu hình FIPS. |

Với ứng dụng mới, Argon2id thường là lựa chọn tốt nếu có thư viện được duy trì và cấu hình phù hợp. PBKDF2 là lựa chọn có sẵn trong nhiều môi trường Java tiêu chuẩn qua **SecretKeyFactory**, nhưng phải đặt số vòng lặp đủ cao theo hướng dẫn hiện hành và đo trên phần cứng thực tế. Không nên chọn thuật toán chỉ vì nó có sẵn trong JDK.

### Tham số chi phí

- **Argon2id:** memory cost, time cost và parallelism. Bộ nhớ càng lớn và số vòng càng nhiều thì mỗi lần kiểm tra thường càng tốn tài nguyên.
- **scrypt:** N, r và p điều chỉnh chi phí CPU/bộ nhớ và song song.
- **bcrypt:** cost factor điều chỉnh số vòng xử lý theo cơ chế của thuật toán; cost tăng làm chi phí tăng theo cấp số nhân.
- **PBKDF2:** iteration count là số vòng lặp của hàm dẫn xuất; số vòng càng cao thì phép tính càng chậm.

Không có một bộ tham số tối ưu cho mọi máy chủ. Cần benchmark để mỗi lần xác minh đủ tốn kém với kẻ tấn công nhưng vẫn đáp ứng độ trễ đăng nhập và tải đồng thời của hệ thống. Đo cả thời gian p95/p99, CPU, bộ nhớ và khả năng chịu tải khi nhiều người dùng đăng nhập cùng lúc. Tham số phải được lưu trong bản ghi để có thể xác minh lại và nâng cấp sau này.

## 5. Cấu trúc bản ghi password hash

Một bản ghi nên chứa đủ thông tin để hệ thống biết cách xác minh mật khẩu mà không phụ thuộc vào cấu hình ngầm của ứng dụng:

~~~text
algorithm$version$parameters$salt$derived_hash
~~~

Ví dụ về cấu trúc logic:

~~~text
argon2id$v=19$m=...,t=...,p=...$<salt-base64>$<hash-base64>
~~~

Đây chỉ là mẫu minh họa, không phải giá trị tham số có thể dùng trực tiếp. Thư viện Argon2 thường cung cấp hàm encode/verify theo định dạng chuẩn của nó; nên dùng định dạng đó thay vì tự phát minh quy tắc tuần tự hóa.

Với PBKDF2, ứng dụng có thể lưu các trường riêng trong cơ sở dữ liệu hoặc dùng chuỗi định dạng có phiên bản, ví dụ:

~~~text
pbkdf2-sha256$<iterations>$<salt-base64>$<hash-base64>
~~~

Các trường quan trọng gồm:

- Tên thuật toán và phiên bản/biến thể.
- Tham số chi phí cần thiết để tái tạo phép dẫn xuất.
- Salt riêng của bản ghi.
- Độ dài đầu ra hoặc định dạng hash nếu không cố định theo thuật toán.
- Giá trị hash đã dẫn xuất.

Khi đọc bản ghi, chỉ chấp nhận thuật toán trong allowlist và giới hạn phạm vi tham số hợp lệ. Bản ghi bị sửa để chứa iteration count hoặc memory cost cực lớn có thể khiến dịch vụ tiêu thụ tài nguyên quá mức. Cần kiểm tra kích thước đầu vào, tham số tối đa và định dạng trước khi thực hiện phép tính.

## 6. Ví dụ password hashing với PBKDF2 trong Java

JCA cung cấp **SecretKeyFactory** cho PBKDF2. Ví dụ sau sinh salt ngẫu nhiên 16 byte, dẫn xuất 256 bit bằng PBKDF2-HMAC-SHA-256 và lưu thông tin thuật toán, số vòng, salt cùng hash. Số vòng trong ví dụ được truyền từ cấu hình để tổ chức có thể benchmark và nâng cấp mà không sửa logic.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordHasher {
    private static final String ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final int SALT_BYTES = 16;
    private static final int HASH_BITS = 256;
    private static final int MIN_NEW_ITERATIONS = 600_000;
    private static final int MAX_ITERATIONS = 2_000_000;
    private static final SecureRandom RANDOM = new SecureRandom();

    private PasswordHasher() {
    }

    public static PasswordHash hash(char[] password, int iterations)
            throws GeneralSecurityException {
        if (password == null || password.length == 0) {
            throw new IllegalArgumentException("Mật khẩu không hợp lệ");
        }
        if (iterations < MIN_NEW_ITERATIONS
                || iterations > MAX_ITERATIONS) {
            throw new IllegalArgumentException("Iteration count không hợp lệ");
        }

        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);

        byte[] derived = derive(password, salt, iterations);
        try {
            return new PasswordHash(ALGORITHM, iterations, salt, derived);
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    }

    public static boolean verify(
            char[] candidate, PasswordHash stored)
            throws GeneralSecurityException {
        if (candidate == null || stored == null) {
            return false;
        }
        if (!ALGORITHM.equals(stored.algorithm)
                || stored.iterations < 1
                || stored.iterations > MAX_ITERATIONS) {
            throw new IllegalArgumentException(
                    "Bản ghi password hash không hợp lệ");
        }

        byte[] candidateHash =
                derive(candidate, stored.salt, stored.iterations);
        try {
            return MessageDigest.isEqual(candidateHash, stored.hash);
        } finally {
            Arrays.fill(candidateHash, (byte) 0);
        }
    }

    private static byte[] derive(
            char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {
        PBEKeySpec spec =
                new PBEKeySpec(password, salt, iterations, HASH_BITS);
        try {
            SecretKeyFactory factory =
                    SecretKeyFactory.getInstance(ALGORITHM);
            return factory.generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    public static final class PasswordHash {
        private final String algorithm;
        private final int iterations;
        private final byte[] salt;
        private final byte[] hash;

        public PasswordHash(
                String algorithm,
                int iterations,
                byte[] salt,
                byte[] hash) {
            if (algorithm == null
                    || iterations < 1
                    || iterations > MAX_ITERATIONS
                    || salt == null
                    || salt.length != SALT_BYTES
                    || hash == null
                    || hash.length != HASH_BITS / 8) {
                throw new IllegalArgumentException(
                        "Bản ghi password hash không hợp lệ");
            }
            this.algorithm = algorithm;
            this.iterations = iterations;
            this.salt = salt.clone();
            this.hash = hash.clone();
        }

        public String getAlgorithm() {
            return algorithm;
        }

        public int getIterations() {
            return iterations;
        }

        public byte[] getSalt() {
            return salt.clone();
        }

        public byte[] getHash() {
            return hash.clone();
        }
    }
}
~~~

Ví dụ tập trung minh họa luồng PBKDF2. Ngưỡng 600.000 vòng là mốc tham khảo cho PBKDF2-HMAC-SHA-256, không phải giá trị tối ưu cho mọi môi trường; cần đối chiếu hướng dẫn hiện hành, yêu cầu chứng nhận và benchmark để đặt ngưỡng mới phù hợp. Giới hạn 2.000.000 vòng chỉ là hàng rào đầu vào minh họa; hãy đặt giới hạn tối đa theo chính sách vận hành và các phiên bản hash mà hệ thống thực sự hỗ trợ. Hàm hash chỉ tạo bản ghi mới từ ngưỡng tối thiểu, còn verify cho phép đọc hash cũ có số vòng thấp hơn để hỗ trợ rehash on login. Lớp PasswordHash giữ bản sao riêng của salt/hash và trả bản sao qua getter để tránh mã gọi bên ngoài sửa trực tiếp dữ liệu xác minh.

Khi gọi verify, lấy bản ghi của tài khoản, tạo mảng char từ đầu vào mật khẩu và truyền cùng bản ghi vào hàm. Sau khi hoàn tất, phía gọi nên xóa mảng mật khẩu mà nó sở hữu:

~~~java
char[] candidate = passwordInput.toCharArray();
try {
    boolean authenticated = PasswordHasher.verify(candidate, storedHash);
    // Tiếp tục luồng đăng nhập theo kết quả xác minh.
} finally {
    Arrays.fill(candidate, '\0');
}
~~~

Xóa mảng giúp giảm thời gian dữ liệu còn trong vùng nhớ do ứng dụng quản lý, nhưng không bảo đảm xóa mọi bản sao do JVM, thư viện giao diện hoặc provider tạo ra. Tránh chuyển mật khẩu sang String nếu có thể vì String là immutable và không thể chủ động ghi đè nội dung.

Áp dụng việc xóa mảng cho cả luồng tạo mật khẩu mới lẫn luồng xác minh. Mảng đầu vào thuộc quyền quản lý của phía gọi; hàm PasswordHasher không tự xóa nó để tránh thay đổi dữ liệu mà bên gọi có thể còn cần dùng.

**Lưu ý:** PBKDF2WithHmacSHA256 cần được hỗ trợ bởi provider JCA đang dùng. Hãy kiểm thử tên thuật toán và hành vi trên đúng phiên bản JDK/provider triển khai. Ví dụ sử dụng API chuẩn của Java, nhưng không thay thế benchmark hoặc chính sách tham số của hệ thống.

## 7. Dùng Argon2id, scrypt hoặc bcrypt trong ứng dụng Java

Các thuật toán Argon2id, scrypt và bcrypt thường được cung cấp bởi thư viện chuyên dụng thay vì API JCA tiêu chuẩn trong mọi bản JDK. Khi lựa chọn thư viện:

1. Chọn dự án được duy trì, có tài liệu rõ ràng, phiên bản phát hành và lịch sử xử lý lỗ hổng.
2. Ưu tiên API tạo hash và verify có định dạng lưu trữ đầy đủ thuật toán, salt và tham số.
3. Dùng bộ tham số theo hướng dẫn bảo mật hiện hành, rồi benchmark trên hạ tầng thật.
4. Kiểm tra giới hạn độ dài mật khẩu, cách mã hóa Unicode và cách xử lý lỗi.
5. Không tự viết lại thuật toán hoặc tự ghép các primitive mật mã thành một password hashing scheme.

Với bcrypt, nhiều triển khai giới hạn đầu vào ở 72 byte. Đây là giới hạn theo byte của triển khai, không nhất thiết là 72 ký tự Unicode. Nếu hệ thống hỗ trợ mật khẩu dài hoặc nhiều ngôn ngữ, cần hiểu rõ hành vi thư viện và tránh cắt cụt âm thầm. Với scrypt và Argon2id, cần giới hạn tài nguyên để bản ghi giả mạo không khiến dịch vụ cấp phát quá nhiều bộ nhớ hoặc CPU.

## 8. Pepper: bí mật bổ sung ngoài salt

**Pepper** là một bí mật dùng chung hoặc theo nhóm được kết hợp vào quy trình xác minh mật khẩu. Khác với salt, pepper không được lưu trong cùng cơ sở dữ liệu với password hash. Nó cần được lưu ở secret manager, KMS hoặc HSM và chỉ cấp cho thành phần xác minh có quyền.

Pepper có thể làm giảm giá trị của bản sao cơ sở dữ liệu bị đánh cắp nếu kẻ tấn công không lấy được bí mật này. Tuy nhiên:

- Pepper không thay thế salt riêng cho từng tài khoản.
- Nếu ứng dụng và pepper cùng bị xâm nhập, lợi ích bổ sung có thể mất.
- Mất pepper có thể khiến toàn bộ mật khẩu không thể xác minh.
- Xoay vòng pepper khó hơn xoay vòng salt vì hash cũ phụ thuộc vào pepper cũ.

Nếu triển khai pepper, cần có kế hoạch phiên bản hóa và di trú. Một cách vận hành là giữ pepper cũ trong thời gian chuyển tiếp, xác minh người dùng bằng phiên bản gắn với bản ghi, rồi tạo lại hash với pepper mới sau lần đăng nhập thành công. Nếu pepper bị lộ, cần đánh giá phạm vi ảnh hưởng và buộc đặt lại mật khẩu khi không thể tái tạo hash an toàn.

## 9. Xác minh mật khẩu an toàn

Quy trình xác minh cơ bản:

1. Tìm bản ghi tài khoản theo định danh đã chuẩn hóa theo chính sách.
2. Đọc thuật toán, phiên bản, tham số, salt và hash từ bản ghi.
3. Kiểm tra định dạng và giới hạn tham số trước khi tính toán.
4. Dẫn xuất giá trị từ mật khẩu người dùng nhập với đúng salt và tham số đã lưu.
5. So sánh hai giá trị bằng hàm so sánh phù hợp cho dữ liệu mật mã, chẳng hạn MessageDigest.isEqual trong Java.
6. Nếu hợp lệ, kiểm tra có cần nâng cấp tham số hoặc thuật toán hay không.

Không so sánh hash bằng toán tử chuỗi hoặc vòng lặp tự viết có thể dừng ngay khi gặp byte khác nhau. So sánh không phụ thuộc nội dung giúp giảm rò rỉ thời gian. Cũng không nên trả thông báo phân biệt quá chi tiết như “sai mật khẩu”, “tài khoản tồn tại” hoặc “hash lỗi” cho người chưa xác thực; phản hồi bên ngoài nên tránh tiết lộ sự tồn tại của tài khoản.

Password hashing chỉ bảo vệ dữ liệu kiểm chứng khi cơ sở dữ liệu bị lấy cắp. Nó không ngăn kẻ tấn công thử mật khẩu trực tiếp trên endpoint đăng nhập. Cần thêm rate limiting, theo dõi hành vi bất thường, MFA, phát hiện credential stuffing và cơ chế khóa/chậm đăng nhập được thiết kế để tránh bị lạm dụng gây từ chối dịch vụ.

## 10. Nâng cấp thuật toán và tham số theo thời gian

Phần cứng ngày càng nhanh và tiêu chuẩn an toàn có thể thay đổi. Vì vậy, hệ thống phải lưu tham số theo từng bản ghi và có khả năng nâng cấp hash.

Một chiến lược phổ biến là **rehash on login**:

1. Người dùng đăng nhập và hash cũ được xác minh thành công.
2. Ứng dụng so sánh thuật toán/tham số trong bản ghi với chính sách hiện tại.
3. Nếu hash cũ yếu hoặc dùng tham số thấp, ứng dụng tạo salt mới và hash lại bằng cấu hình hiện tại.
4. Cập nhật bản ghi một cách nguyên tử sau khi xác minh thành công.
5. Lần đăng nhập tiếp theo sử dụng cấu hình mới.

Không thể nâng cấp một hash cũ lên thuật toán mới nếu không có mật khẩu gốc hoặc một quy trình đặt lại mật khẩu. Hash không thể giải mã. Với tài khoản không đăng nhập trong thời gian dài, có thể yêu cầu đặt lại mật khẩu theo chính sách hoặc giữ cơ chế xác minh cũ trong thời gian chuyển đổi có giới hạn.

Khi thay đổi định dạng bản ghi, giữ thông tin phiên bản và hỗ trợ đọc các định dạng cũ trong thời gian di trú. Tránh thay đổi toàn bộ hash bằng một phép băm nhanh trên giá trị hash cũ rồi coi đó là nâng cấp tương đương; cách đó không tăng entropy của mật khẩu và có thể tạo thêm rủi ro tương thích.

## 11. Chính sách mật khẩu và bảo vệ tài khoản

Hash mạnh là một lớp phòng thủ. Chất lượng mật khẩu và cách hệ thống tiếp nhận mật khẩu vẫn quan trọng:

- Cho phép mật khẩu dài và hỗ trợ passphrase; không cắt cụt âm thầm.
- Chặn mật khẩu phổ biến, đã bị lộ hoặc dễ đoán bằng danh sách kiểm tra phù hợp.
- Không ép thay đổi mật khẩu định kỳ nếu không có dấu hiệu xâm phạm hoặc yêu cầu chính sách cụ thể.
- Không yêu cầu quy tắc thành phần ký tự phức tạp đến mức khiến người dùng chọn mật khẩu dễ đoán; ưu tiên độ dài và khả năng chống đoán.
- Không gửi mật khẩu qua log, telemetry, URL, email hoặc thông báo lỗi.
- Dùng TLS để bảo vệ mật khẩu trên đường truyền; password hashing ở máy chủ không thay thế TLS.
- Hỗ trợ MFA hoặc passkey để giảm rủi ro khi mật khẩu bị đoán hoặc tái sử dụng.

Nếu hệ thống chuẩn hóa Unicode, cần áp dụng cùng một quy tắc khi đăng ký, xác minh và đặt lại mật khẩu. Không tự ý trim khoảng trắng hoặc chuyển chữ hoa/thường nếu điều đó làm thay đổi mật khẩu mà người dùng đã chọn. Quy tắc chuẩn hóa phải được xác định trước và giữ ổn định để tránh người dùng bị khóa khỏi tài khoản.

## 12. Xử lý sự cố và các sai lầm thường gặp

| Sai lầm hoặc sự cố | Rủi ro | Cách xử lý |
|---|---|---|
| Lưu mật khẩu dạng rõ | Lộ toàn bộ mật khẩu khi cơ sở dữ liệu hoặc backup bị truy cập. | Buộc đặt lại mật khẩu, điều tra phạm vi lộ và triển khai password hashing phù hợp. |
| Dùng MD5, SHA-1 hoặc SHA-256 trực tiếp | Kẻ tấn công có thể thử đoán rất nhanh. | Chuyển sang Argon2id, scrypt, bcrypt hoặc PBKDF2 với tham số phù hợp. |
| Dùng cùng salt cho mọi tài khoản | Cùng mật khẩu tạo cùng hash và hỗ trợ tấn công dùng chung bảng tra cứu. | Sinh salt ngẫu nhiên riêng cho từng lần tạo hash. |
| Salt quá ngắn hoặc dự đoán được | Tăng nguy cơ trùng và giảm khả năng chống bảng tra cứu. | Dùng SecureRandom và salt đủ dài, thường ít nhất 16 byte. |
| Tham số chi phí quá thấp | Tấn công ngoại tuyến có thể thử quá nhiều mật khẩu. | Benchmark và tăng cost theo chính sách, sau đó rehash khi đăng nhập. |
| Tham số không giới hạn khi đọc bản ghi | Bản ghi độc hại có thể gây tiêu thụ CPU/bộ nhớ quá mức. | Kiểm tra allowlist thuật toán, kích thước trường và giới hạn cost trước khi tính. |
| Lộ pepper | Kẻ tấn công có thể dùng pepper cùng bản sao hash để dò đoán. | Xoay vòng bí mật, đánh giá phạm vi và yêu cầu đặt lại mật khẩu khi cần. |
| Không thể xác minh sau khi đổi thuật toán | Tài khoản bị khóa do không còn đọc được định dạng cũ. | Phiên bản hóa định dạng, duy trì đọc trong giai đoạn chuyển tiếp và có quy trình reset. |
| Lỗi xác minh làm lộ tài khoản tồn tại | Hỗ trợ dò danh sách tài khoản. | Chuẩn hóa phản hồi bên ngoài và theo dõi hành vi dò đoán. |

Khi cơ sở dữ liệu password hash bị lộ, không được giả định salt hoặc thuật toán đã làm cho mật khẩu an toàn tuyệt đối. Cần đánh giá loại hash, tham số, số lượng tài khoản, khả năng lộ pepper và nguy cơ người dùng tái sử dụng mật khẩu. Có thể cần buộc đặt lại mật khẩu, vô hiệu hóa phiên đăng nhập, xoay bí mật liên quan và thông báo theo quy trình ứng phó sự cố.

## 13. Checklist triển khai

- [ ] Dùng password hashing scheme chuyên dụng; không dùng hash nhanh một lần.
- [ ] Mỗi bản ghi có salt ngẫu nhiên riêng, đủ dài.
- [ ] Chọn Argon2id, scrypt, bcrypt hoặc PBKDF2 theo yêu cầu và môi trường.
- [ ] Tham số chi phí được benchmark trên hạ tầng thật và có kế hoạch nâng cấp.
- [ ] Bản ghi lưu thuật toán, phiên bản, tham số, salt và giá trị hash.
- [ ] Đầu vào và tham số bản ghi được giới hạn để tránh tiêu thụ tài nguyên quá mức.
- [ ] So sánh kết quả bằng hàm phù hợp cho dữ liệu mật mã.
- [ ] Mật khẩu và pepper không xuất hiện trong log hoặc cùng cơ sở dữ liệu hash.
- [ ] Có rate limiting, MFA và giám sát đăng nhập bất thường.
- [ ] Có quy trình rehash on login, đặt lại mật khẩu, xử lý sự cố và di trú định dạng.

Password hashing giúp hệ thống xác minh người dùng mà không lưu mật khẩu gốc. Mức bảo vệ phụ thuộc vào thuật toán chuyên dụng, salt riêng, tham số chi phí, cách quản lý pepper và quy trình vận hành tài khoản. Khi kết hợp các yếu tố này với kiểm soát đăng nhập và kế hoạch nâng cấp, hệ thống giảm đáng kể giá trị của cơ sở dữ liệu xác thực nếu dữ liệu bị lộ.
