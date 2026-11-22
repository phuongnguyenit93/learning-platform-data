# 7.2 Vì sao băm nhanh một lần không đủ cho mật khẩu có entropy thấp

## Mục tiêu

Hiểu vì sao `SHA-256(password)` dù dùng thuật toán hash mạnh vẫn **không phù hợp để lưu mật khẩu do con người chọn**; phân tích tấn công đoán mật khẩu offline, entropy thấp, salt, chi phí xử lý và lựa chọn password hashing scheme. Sau bài, bạn có thể dùng Java 17 để chứng minh giới hạn của hash nhanh và tạo/verifier bản ghi PBKDF2 có salt, iterations và so sánh an toàn.

## 1. Vì sao “SHA-256 rất mạnh” chưa phải câu trả lời?

SHA-256 là **cryptographic hash function** có đầu ra cố định 256 bit (32 byte, 64 ký tự hex). Đây là primitive tốt cho toàn vẹn dữ liệu và nhiều giao thức mật mã. Tuy nhiên, hash function được thiết kế để tính **hiệu quả**, còn lưu mật khẩu cần làm cho **mỗi lần thử password** tốn tài nguyên.

Xét:

```text
password = một bí mật do người dùng chọn

stored_hash = SHA-256(password)

Để xác minh:
SHA-256(password_đăng_nhập) == stored_hash ?
```

Nếu database bị rò rỉ, attacker có thể lấy `stored_hash` và tự thử password trên máy của họ. Không cần “đảo ngược” SHA-256. Họ chỉ cần chọn ứng viên `p`, tính `SHA-256(p)`, so sánh với hash bị lộ. Phép tính càng nhanh, họ thử được càng nhiều ứng viên trong cùng thời gian.

Không có lỗi mật mã mới trong SHA-256 ở đây: **bài toán yếu nằm ở phân phối password đầu vào và cách sử dụng**. SHA-512 hay SHA3-256 chạy một lần không giải quyết được bản chất đó.

| SHA-256 phù hợp cho | Kho lưu password cần |
| --- | --- |
| Digest nhanh, xác định, hỗ trợ nhiều giao thức | Chi phí **có chủ đích** cho từng lần đoán |
| Kháng tìm tiền ảnh trên dữ liệu đủ khó đoán | Chống tấn công danh sách password phổ biến |
| Đầu ra luôn 256 bit | Không đánh đồng độ dài hash với entropy đầu vào |
| Không có khái niệm salt/work factor bắt buộc | Salt riêng, cost điều chỉnh, version để nâng cấp |

**Thông điệp chính:** mật khẩu dễ đoán không tự trở thành bí mật 256 bit khi được băm thành 256 bit.

## 2. Entropy thấp là điều gì?

**Entropy** mô tả mức độ khó dự đoán một bí mật, dựa trên **cách nó được sinh/chọn** và phân phối xác suất. Nếu mật khẩu được lấy đồng đều ngẫu nhiên từ `N` lựa chọn độc lập, số bit thông tin xấp xỉ:

```text
H ≈ log2(N) bit
```

Ví dụ: một mã PIN gồm **6 chữ số, sinh đều ngẫu nhiên** có `10^6` khả năng, tương ứng khoảng **19,93 bit**, dù `SHA-256(PIN)` có 256-bit output.

Người dùng thường không chọn ngẫu nhiên đồng đều. Họ có thể dùng từ phổ biến, năm sinh, tên thú cưng, bàn phím, chuỗi số, mẫu thêm dấu `!` hoặc password đã bị lộ trên dịch vụ khác. Các ứng viên không đồng xác suất, nên attacker có thể ưu tiên **mẫu có xác suất cao** trước.

- Một password dài vẫn có thể yếu nếu là câu rất phổ biến hoặc mẫu dễ đoán.
- Nhiều ký tự đặc biệt không chứng minh entropy cao nếu mọi người đều thêm chúng theo mẫu.
- Passphrase nhiều từ **được lấy ngẫu nhiên độc lập** thường khó đoán hơn câu người dùng tự nghĩ dựa vào ngữ cảnh quen thuộc.
- Password manager tạo secret ngẫu nhiên độc lập có thể cung cấp entropy cao; password reuse trên nhiều dịch vụ làm mất lợi thế khi có vụ rò rỉ.

Đừng tính “entropy chính xác” của mật khẩu người dùng chỉ bằng số chữ cái, chữ số và dấu. Entropy phụ thuộc **phân phối lựa chọn**, không phải số ký tự hash hay vẻ phức tạp bên ngoài.

### 2.1 Kháng tiền ảnh (preimage resistance) có bị phá không?

**Không.** Kháng tiền ảnh mô tả việc tìm đầu vào cho digest nói chung khó đến mức nào khi đầu vào có không gian đủ lớn. Với mật khẩu do con người chọn, attacker lại làm một việc hẹp hơn:

```text
candidate_1 -> SHA-256 -> so sánh với hash bị lộ
candidate_2 -> SHA-256 -> so sánh với hash bị lộ
candidate_3 -> SHA-256 -> so sánh với hash bị lộ
...
```

Nếu ứng viên thứ hai chính là password, attacker đã tìm được password mà không cần giải phương trình ngược của SHA-256. Password entropy thấp làm **không gian phỏng đoán hữu ích** nhỏ và dễ ưu tiên.

## 3. Mô hình tấn công offline sau khi database bị lộ

Giả sử một bản sao database gồm các bản ghi:

```text
account_id | password_hash
-----------+-------------------------------------
user_a     | SHA-256(password_A)
user_b     | SHA-256(password_B)
```

Attacker lấy được bảng này. Từ đó họ không cần gửi request đăng nhập. Họ tự chạy thuật toán trên phần cứng mình kiểm soát:

```text
Bản sao password hashes đã bị lộ
                |
                v
Tập ứng viên mật khẩu phổ biến,
password từng rò rỉ, biến thể có quy luật...
                |
                v
Tính SHA-256(candidate) offline
                |
                v
So với hash trong database
        /                   \
     trùng                 không trùng
       |                       |
 tìm password          thử candidate khác
```

Những yếu tố khiến attacker thuận lợi:

1. **Không có giới hạn request từ hệ thống thật**: CAPTCHA, khóa tài khoản, rate limit ở login endpoint không chặn các phép thử offline.
2. **Tính song song rất lớn**: các hash nhanh được tính hiệu quả trên CPU/GPU và phần cứng chuyên dụng.
3. **Dữ liệu từ các lần rò rỉ trước**: dictionary chứa các password có xác suất cao, không cần duyệt đều tất cả chuỗi có thể.
4. **Cùng một password tạo cùng hash khi không có salt**: attacker có thể phát hiện trùng lặp và dùng kết quả tính toán cho nhiều tài khoản.

Mô hình thời gian đơn giản:

```text
thời_gian_đoán ≈ số_ứng_viên_cần_thử / tốc_độ_thử
```

Đây là quan hệ khái niệm; tốc độ thực tế phụ thuộc phần cứng và thuật toán. Không nên công bố “attacker chắc chắn crack trong X giây” khi không có dữ liệu đo. **Chi phí của mỗi phép thử** là đòn bẩy mà hệ thống có thể tác động bằng password KDF có work factor.

## 4. Hash nhanh không có salt, có salt và password KDF

### 4.1 Không có salt

```text
stored = SHA-256(password)
```

Các tài khoản cùng password có cùng digest. Một bảng tra cứu/dictionary tính trước có thể dùng lại. Việc lấy SHA-512 một lần hoặc đổi hex sang Base64 không thay đổi bản chất này.

### 4.2 Có salt nhưng vẫn hash nhanh

```text
salt = random_16_bytes()
stored = SHA-256(salt || password)
database = (salt, stored)
```

**Salt** là byte ngẫu nhiên **riêng cho mỗi bản ghi** (chẳng hạn 16 byte bằng `SecureRandom`), được lưu cùng verifier; **không cần bí mật**.

Salt mang lại lợi ích quan trọng: những tài khoản cùng password thường có hash khác nhau; giảm hiệu quả các bảng tra cứu hash dựng sẵn và việc tái sử dụng chung công sức tính cho nhiều account.

Nhưng attacker biết `salt` khi database bị lộ. Họ vẫn tính:

```text
SHA-256(salt_của_tài_khoản || candidate)
```

cho từng ứng viên. Đây vẫn là một SHA-256 **rất nhanh**. Vì vậy **salt là cần thiết nhưng chưa đủ**.

### 4.3 Salt kết hợp password hashing scheme chuyên dụng

```text
stored = PasswordKDF(password, unique_salt, work_factor)
record = (algorithm, version, parameters, salt, stored)
```

Giờ mỗi phép thử phải chạy công việc lặp lại hoặc tốn bộ nhớ theo tham số, thay vì một SHA-256. Attacker vẫn có thể đoán, nhưng **mỗi lần đoán trở nên đắt hơn**. Salt giúp chống precomputation và phân biệt bản ghi; KDF làm tăng chi phí cho từng candidate. Hai vai trò bổ sung nhau.

| Cách làm | Chống bảng tra cứu dựng sẵn chung? | Làm chi phí mỗi lần thử cao? | Phù hợp password storage? |
| --- | --- | --- | --- |
| `SHA-256(password)` | Không | Không | **Không** |
| `SHA-256(salt || password)` | Có, nếu salt riêng | Không đáng kể | **Không** |
| `PBKDF2(password, salt, iterations)` | Có | Có, theo số vòng | Có, với cấu hình phù hợp |
| `Argon2id(password, salt, m, t, p)` | Có | Có, CPU + memory-hard | Có, thường ưu tiên cho hệ thống mới |

**Không dùng chung một salt tĩnh toàn hệ thống**, không lấy username/time/PID làm salt thay CSPRNG và không cố giấu salt trong source code. Salt khác với **pepper** là bí mật bổ sung được bảo vệ ngoài database.

## 5. Thực hành 1: chứng minh salt không dừng offline guessing

Ví dụ này sử dụng **dữ liệu tự tạo để học tập**. Nó dùng SHA-256 một lần, hai salt **cố định để stdout có thể lặp lại**. Không sao chép cách sinh salt hay cách lưu verifier này sang production.

Tạo file **`FastHashGuessDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;

public class FastHashGuessDemo {
    private static byte[] sha256(byte[] salt, String text) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        if (salt != null) {
            digest.update(salt);
        }
        return digest.digest(text.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        String example = "classroom-only";
        byte[] saltA = HexFormat.of().parseHex("00112233445566778899aabbccddeeff");
        byte[] saltB = HexFormat.of().parseHex("ffeeddccbbaa99887766554433221100");

        System.out.println("unsalted repeat equals: " +
                Arrays.equals(sha256(null, example), sha256(null, example)));
        System.out.println("different salts change digest: " +
                !Arrays.equals(sha256(saltA, example), sha256(saltB, example)));

        byte[] stolenHash = sha256(saltA, example);
        String[] dictionary = {"welcome", "password1", "classroom-only", "letmein"};
        int attempts = 0;
        boolean found = false;
        for (String guess : dictionary) {
            attempts++;
            if (MessageDigest.isEqual(stolenHash, sha256(saltA, guess))) {
                found = true;
                break;
            }
        }
        System.out.println("offline guess matched: " + found);
        System.out.println("candidate attempts: " + attempts);
    }
}
```

Biên dịch/chạy trên Java 17 trở lên:

```bash
javac --release 17 FastHashGuessDemo.java
java FastHashGuessDemo
```

Đầu ra đã kiểm chứng:

```text
unsalted repeat equals: true
different salts change digest: true
offline guess matched: true
candidate attempts: 3
```

Giải thích kết quả:

- `SHA-256` là hàm xác định, cùng input cho cùng output.
- Hai salt khác nhau tạo input khác nhau nên hai digest khác nhau; salt chống việc nhìn hash giống nhau và tra bảng tính trước.
- Attacker giả lập biết **salt công khai** và hash, rồi tính lại từng ứng viên. Ứng viên thứ ba khớp, dù hash có salt.
- `MessageDigest.isEqual` có ích khi so sánh byte, nhưng **không** làm SHA-256 một lần thành thuật toán password storage.

Điều này giải thích tại sao phải có **cả salt lẫn cơ chế làm chậm phép thử**, không chỉ thêm một chuỗi vào input SHA-256.

## 6. Vì sao phải dùng password KDF có cost?

**Password-based key derivation / password hashing scheme** nhận password, salt và tham số độ khó. Nó cố ý tiêu tốn công việc khi sinh verifier. Người dùng hợp pháp thường cần một lần verify; attacker muốn thử rất nhiều password, nên chi phí sẽ nhân lên.

```text
Đăng ký:
password + salt_mới + algorithm/params
               |
               v
     PasswordKDF(...)
               |
               v
lưu {scheme, version, params, salt, verifier}

Xác minh:
password nhập + salt/params lưu trữ
               |
               v
     cùng PasswordKDF(...)
               |
               v
so sánh verifier -> accept / reject
```

Không nên tự tạo “SHA-256 lặp 1.000 lần” làm sơ đồ riêng: các thuật toán password KDF có thiết kế/kiểm chứng, tham số, định dạng và các chi tiết an toàn cần tuân theo.

### 6.1 Các thuật toán quan trọng

| Phương án | Work factor | Đặc tính | Lưu ý |
| --- | --- | --- | --- |
| **Argon2id** | Bộ nhớ `m`, số passes `t`, mức song song `p` | **Memory-hard**; làm phép thử song song quy mô lớn đắt RAM | Thường ưu tiên cho hệ thống mới, cần thư viện được bảo trì |
| **scrypt** | `N`, `r`, `p` | Memory-hard | Tốt nếu không thể dùng Argon2id |
| **bcrypt** | Cost tăng theo cấp số mũ | Chủ yếu CPU | Hệ thống cũ; chú ý giới hạn đầu vào thường **72 byte** |
| **PBKDF2-HMAC-SHA256** | `iterations` | Chuỗi HMAC lặp; **không memory-hard** | Chuẩn hóa, Java 17 có sẵn, phù hợp chính sách/tương thích |
| **SHA-256 một lần** | Không có cost | Rất nhanh | Không lưu password trực tiếp |

Theo OWASP Password Storage Cheat Sheet, những **mốc tham khảo cần cập nhật theo thời gian** gồm:

- Argon2id: một cấu hình cơ sở **`m=19 MiB, t=2, p=1`**; tài liệu nêu các kết hợp RAM/iterations tương đương về mục tiêu.
- scrypt: chẳng hạn `N=2^17, r=8, p=1`.
- bcrypt: cost từ **10** cho trường hợp tương thích với hệ thống cũ; xử lý giới hạn 72 byte cẩn thận.
- PBKDF2-HMAC-SHA256: **600.000 iterations** hoặc hơn theo hướng dẫn OWASP hiện có.

Đây **không phải các con số có thể so trực tiếp** giữa thuật toán (2 vòng Argon2id không tương đương 2 vòng PBKDF2). Benchmark latency, throughput, RAM và khả năng chống DoS trên môi trường production; tăng cost/rehash khi phần cứng và hướng dẫn thay đổi.

**Memory-hard không có nghĩa không thể crack.** Argon2id buộc attacker bỏ thêm tài nguyên bộ nhớ cho từng ứng viên; nếu password quá phổ biến, nó vẫn có thể bị đoán. Work factor tăng chi phí, không tạo entropy mới cho mật khẩu yếu.

### 6.2 Vì sao ví dụ Java dưới đây dùng PBKDF2?

`SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` là API chuẩn Java 17. Nó cho phép minh họa toàn bộ vòng đời salt/iterations/verifier **không cần thêm thư viện**. PBKDF2 có thể cần dùng trong môi trường yêu cầu triển khai được kiểm định/tuân thủ FIPS; nhưng nếu có thư viện Argon2id an toàn và chính sách cho phép, OWASP thường ưu tiên Argon2id cho hệ thống mới.

## 7. Thực hành 2: PBKDF2-HMAC-SHA256 đầy đủ trong Java 17

Ví dụ này dùng:

- Salt **16 byte mới**, sinh bằng `SecureRandom` cho từng bản ghi.
- `PBKDF2WithHmacSHA256` với **600.000 iterations** và derived hash dài **32 byte**.
- Chuỗi lưu `scheme$iterations$Base64(salt)$Base64(derived)` để thuật toán và cost không bị mất.
- Verify bằng **cùng salt/iterations** lưu trong record, sau đó so sánh byte với `MessageDigest.isEqual`.
- `PBEKeySpec.clearPassword()` và xóa mảng nhạy cảm mà ví dụ sở hữu.
- Giới hạn iterations khi đọc bản ghi để tránh xử lý input cấu hình cực lớn; con số **2 triệu** là chính sách demo, không phải tiêu chuẩn bắt buộc.

Tạo file **`Pbkdf2PasswordDemo.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class Pbkdf2PasswordDemo {
    private static final String SCHEME = "pbkdf2-sha256";
    private static final int ITERATIONS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int HASH_BYTES = 32;
    private static final SecureRandom RNG = new SecureRandom();

    private static byte[] derive(char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(
                password, salt, iterations, HASH_BYTES * 8);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    public static String register(char[] password) throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        RNG.nextBytes(salt);
        byte[] derived = derive(password, salt, ITERATIONS);
        try {
            return SCHEME + "$" + ITERATIONS + "$"
                    + Base64.getEncoder().encodeToString(salt) + "$"
                    + Base64.getEncoder().encodeToString(derived);
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    }

    public static boolean verify(char[] password, String stored)
            throws GeneralSecurityException {
        String[] parts = stored.split("\\$", -1);
        if (parts.length != 4 || !SCHEME.equals(parts[0])) {
            return false;
        }
        final int count;
        try {
            count = Integer.parseInt(parts[1]);
        } catch (NumberFormatException e) {
            return false;
        }
        if (count <= 0 || count > 2_000_000) {
            return false;
        }
        final byte[] salt;
        final byte[] expected;
        try {
            salt = Base64.getDecoder().decode(parts[2]);
            expected = Base64.getDecoder().decode(parts[3]);
        } catch (IllegalArgumentException e) {
            return false;
        }
        if (salt.length != SALT_BYTES || expected.length != HASH_BYTES) {
            return false;
        }
        byte[] actual = derive(password, salt, count);
        try {
            return MessageDigest.isEqual(expected, actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        char[] correct = "classroom-demo-only".toCharArray();
        char[] incorrect = "classroom-demo-wrong".toCharArray();
        try {
            String first = register(correct);
            String second = register(correct);
            String[] fields = first.split("\\$", -1);
            System.out.println("scheme: " + fields[0]);
            System.out.println("work factor: " + fields[1]);
            System.out.println("salt bytes: " +
                    Base64.getDecoder().decode(fields[2]).length);
            System.out.println("derived bytes: " +
                    Base64.getDecoder().decode(fields[3]).length);
            System.out.println("different salts: " +
                    !fields[2].equals(second.split("\\$", -1)[2]));
            System.out.println("correct password: " + verify(correct, first));
            System.out.println("wrong password: " + verify(incorrect, first));
        } finally {
            Arrays.fill(correct, '\0');
            Arrays.fill(incorrect, '\0');
        }
    }
}
```

Chạy:

```bash
javac --release 17 Pbkdf2PasswordDemo.java
java Pbkdf2PasswordDemo
```

Ví dụ đầu ra đã kiểm tra:

```text
scheme: pbkdf2-sha256
work factor: 600000
salt bytes: 16
derived bytes: 32
different salts: true
correct password: true
wrong password: false
```

Hai salt 128 bit sinh độc lập gần như chắc chắn khác nhau (xác suất trùng cực nhỏ nhưng không tuyệt đối bằng 0). Các dòng còn lại phản ánh format và verify. Chương trình không in raw password, salt hoặc derived hash ra console.

### 7.1 Giải thích luồng đăng ký

1. `register` sinh 16 byte salt bằng `SecureRandom.nextBytes` **mỗi lần tạo verifier**.
2. `PBEKeySpec(password, salt, ITERATIONS, HASH_BYTES * 8)` dùng tham số độ dài key theo **bit**, không theo byte: 256 bit chỉ là kích thước verifier, không tăng entropy của password.
3. `SecretKeyFactory` thực hiện PBKDF2 với HMAC-SHA256. Muốn dùng Argon2id cần thư viện phù hợp; không thể đổi tên thuật toán rồi hy vọng API Java có sẵn mọi KDF.
4. Bản ghi chứa scheme, cost, salt và kết quả. Nó là **password verifier**, không phải encrypted password có thể giải mã.

### 7.2 Giải thích luồng xác minh

1. `verify` tách format và kiểm scheme/iterations/byte lengths.
2. Nó dùng **salt và iterations của bản ghi cũ**, không sinh salt mới. Nếu sinh salt mới khi verify, password đúng cũng thường không khớp.
3. Dẫn xuất lại bằng `PBEKeySpec` rồi so sánh byte bằng `MessageDigest.isEqual`.
4. Trả `false` khi password sai; cần xử lý lỗi và các trường hợp tài khoản không tồn tại theo một chính sách chung ở tầng ứng dụng.

Giới hạn iterations trong demo là cách tránh bản ghi lỗi buộc xử lý một lượng công việc không kiểm soát. Production cần thêm giới hạn độ dài record/input, xác thực encoding, giới hạn request/concurrency và chính sách nâng version. **Đây là code hướng dẫn**, ứng dụng thật nên dùng password encoder được bảo trì và định dạng bản ghi chuẩn.

### 7.3 Password trong bộ nhớ

`PBEKeySpec` giữ bản sao password ở dạng `char[]` và `clearPassword()` xóa bản sao **bên trong nó**; caller vẫn phải xóa `char[]` khi dùng xong. `Arrays.fill` có thể giảm thời gian secret tồn tại trong mảng do ứng dụng quản lý nhưng không chứng minh mọi bản sao trong heap đã bị loại bỏ.

Các literal `"classroom-demo-only"` chỉ phục vụ demo tự chạy; sản phẩm thật **không hard-code password**, không tạo chuỗi `String` thừa và không ghi thông tin nhạy cảm vào log, APM, crash report hay URL. `String` bất biến khó xóa chủ động.

## 8. Lưu bản ghi verifier như thế nào để có thể nâng cấp?

Nếu chỉ lưu một chuỗi 32 byte, sau nhiều năm bạn không biết đó là SHA-256 hay PBKDF2 bao nhiêu vòng. Cần **version/algorithm/parameters** riêng trong bản ghi, chẳng hạn:

```text
{ scheme, version, work_factor, salt, derived_hash }
```

Đối với Argon2id phải lưu đủ `m, t, p`; với bcrypt lưu cost/format của thuật toán; với PBKDF2 cần thuật toán HMAC, số vòng, salt và độ dài kết quả. Có thể dùng **PHC string hoặc format của thư viện** thay vì tự định nghĩa.

Khi tăng cost, verifier cũ vẫn phải được xác minh đúng: đọc params từ record. Nếu user đăng nhập thành công và record có cost cũ, dùng password vừa nhập để **rehash với salt mới và cost mới**, cập nhật lưu trữ atomically; không cần giữ plaintext password lâu dài.

**Không đánh đồng “PBKDF2 của SHA-256 hash cũ” với PBKDF2 của password gốc.** Nếu hash nhanh cũ đã bị lộ, attacker có thể đoán nó offline; việc bọc thêm một lớp mà không đổi password không xóa được thiệt hại. Với hệ thống đang có SHA-256/password cũ, cần kế hoạch di trú:

1. Ngừng tạo verifier SHA-256 đơn mới.
2. Hỗ trợ kiểm tra bản ghi legacy trong thời gian di trú có kiểm soát.
3. Sau login đúng với password gốc, tạo verifier mới bằng KDF chuyên dụng và salt mới.
4. Với tài khoản không đăng nhập, yêu cầu đặt lại password theo chính sách.
5. Nếu nghi ngờ database đã rò rỉ, đánh giá vụ việc, thu hồi phiên và reset password khi cần. Rehash sau sự cố **không làm cho password cũ từng bị crack trở lại an toàn**.

## 9. Salt, pepper, mã hóa và HMAC: đừng nhầm vai trò

| Cơ chế | Bí mật? | Công dụng | Có thay được password KDF? |
| --- | --- | --- | --- |
| **Salt** | Không, lưu cùng record | Chống precomputation, phân biệt mỗi bản ghi | Không |
| **Pepper** | **Có**, giữ ngoài DB | Thêm rào cản nếu chỉ database bị lộ | Không |
| **Password KDF** | Password là bí mật | Làm mỗi phép đoán tốn CPU/RAM, tạo verifier | Đây là thành phần cần dùng |
| **AES encryption** | Phải giữ encryption key | Bảo mật dữ liệu **có thể giải mã** khi có key | Không phù hợp thay verifier thông thường |
| **HMAC** | Có key | Xác thực dữ liệu; có thể tham gia sơ đồ pepper đúng thiết kế | Không dùng đơn lẻ |

Pepper có thể nằm trong vault/HSM/secret manager độc lập với database. Nó **không thay thế salt hay cost**. Nếu attacker cũng lấy pepper, lớp phòng vệ này không còn; việc rotate pepper cần thiết kế vì không có plaintext password để tính lại tùy ý.

Không lưu plaintext password hay mã hóa để phục hồi password người dùng nếu mục tiêu chỉ là **xác minh khi login**. Mã hóa có khóa giải mã tạo nguy cơ lộ toàn bộ plaintext khi key bị đánh cắp; password hashing được thiết kế cho nhu cầu khác.

**Lưu ý trường hợp ngoại lệ:** một token sinh ngẫu nhiên có entropy cao, đủ dài có thể được xử lý theo threat model khác. Điều đó không hợp thức hóa SHA-256 một lần với mật khẩu con người có entropy thấp.

## 10. Tấn công online và offline cần phòng vệ khác nhau

| Đặc điểm | Online guessing | Offline guessing |
| --- | --- | --- |
| Nguồn dữ liệu attacker có | Endpoint login | Bản sao verifier/salt/params |
| Có gửi request tới hệ thống thật? | Có | Không |
| Rate limit/CAPTCHA/khóa tạm giúp được? | Có thể | Không ngăn các phép tính offline |
| MFA giúp giảm đăng nhập trái phép? | Có, theo thiết kế | Không làm hash offline chậm hơn |
| Hàng rào chính | Rate limiting, MFA, giám sát và chống enumeration | Salt + password KDF/cost + bảo vệ DB/pepper |

Một hệ thống nghiêm túc cần cả hai: mật khẩu mạnh/duy nhất, **blocklist password phổ biến/rò rỉ**, hỗ trợ password manager, bảo mật đường truyền TLS, giới hạn request, MFA/passkeys phù hợp và password KDF chuẩn.

Cần tránh **tiết lộ account tồn tại** qua thông báo lỗi và chênh lệch thời gian quá lớn; dùng chính sách lỗi login thống nhất. `MessageDigest.isEqual` hỗ trợ so sánh an toàn hơn, nhưng không bảo đảm **toàn bộ hàm login** có thời gian bất biến: vẫn còn truy vấn DB, parse record, tính KDF và các nhánh khác.

## 11. Chọn work factor như thế nào?

Cost quá thấp giúp attacker thử nhiều ứng viên; cost quá cao gây CPU/RAM saturation khi login đồng thời, thậm chí DoS. Một cách làm có căn cứ:

1. Chọn KDF chuyên dụng, ưu tiên Argon2id khi môi trường hỗ trợ; dùng cấu hình xuất phát từ tài liệu bảo mật cập nhật.
2. Benchmark **trên hạ tầng production tương đương**, đo p50/p95/p99 latency, CPU/RAM và lượng login song song. Với Argon2id, tính tổng RAM khi có nhiều request đang chạy.
3. Đặt ngân sách CPU/memory, hàng đợi/concurrency limit, rate limit và giới hạn độ dài input.
4. Lưu scheme/version/work factor trên từng bản ghi để tăng dần. Đừng để metadata không tin cậy yêu cầu hàng tỷ iterations.
5. Định kỳ tăng cost khi phần cứng thay đổi; nâng cấp verifier qua lần login hoặc quy trình reset password.

Không “giải quyết” latency bằng cách bỏ KDF rồi dùng SHA-256 một lần. Cần tối ưu kiến trúc xác minh, thông lượng và bảo vệ request.

### 11.1 Unicode và password normalization

Java nhận password qua `char[]`. Cách chuyển ký tự thành byte của thuật toán/provider và quy tắc Unicode phải tương thích giữa các lần đăng ký/xác minh, giữa các runtime/ngôn ngữ nếu dữ liệu được chuyển hệ thống.

- Không tự động lowercase, `trim()` hoặc cắt password trong im lặng.
- Nếu chọn Unicode normalization, quy định rõ form/version và dùng nhất quán.
- Lưu ý giới hạn **72 byte** của nhiều triển khai bcrypt, không nhầm “ký tự” với “byte” khi input có dấu tiếng Việt/emoji.
- Không dùng Base64/hex như một hình thức tăng độ an toàn: đó chỉ là encoding.

Trong sản phẩm nên chọn password encoder thư viện đã kiểm thử thay vì tự viết nhiều biến thể password hashing/migration không cần thiết.

## 12. Những nhận định sai thường gặp

- **“SHA-256 có 256 bit nên mật khẩu đã có 256-bit security.”** Sai. Đầu ra dài không tạo entropy cho password yếu.
- **“Thêm một salt là đủ.”** Sai. Salt chống bảng dựng sẵn, vẫn cần password KDF.
- **“Cứ SHA-256 lặp vài vòng là ngang Argon2id.”** Sai. Không tự chế sơ đồ; Argon2id có memory-hardness và cơ chế được nghiên cứu riêng.
- **“Hash là một chiều nên không ai lấy được password.”** Sai. Tấn công từ điển chỉ cần hash và candidate, không cần đảo hàm.
- **“Rate limit chặn brute force offline.”** Sai. Offline thử ngoài server.
- **“Nhiều dấu đặc biệt đảm bảo entropy cao.”** Sai. Mẫu người dùng có thể dễ đoán.
- **“Salt cần bí mật; pepper có thể lưu ngay trong DB.”** Ngược lại: salt được công khai, pepper phải được bảo vệ ngoài DB.
- **“Băm password hai lần theo hai thuật toán nhanh là an toàn.”** Không tạo ra cost hoặc memory-hardness đủ mạnh để bảo vệ password yếu.
- **“MFA khiến stored password hashes không cần bảo vệ.”** Sai. MFA là lớp bổ sung cho login; database leak vẫn nguy hiểm, đặc biệt do password reuse.
- **“Chuyển hash cũ sang format mới là xong sự cố.”** Sai. Password cũ có thể đã bị đoán; cần điều tra và reset/thu hồi phiên tùy mức độ.

## 13. Bài tập tự kiểm tra

**Câu 1.** Một PIN ngẫu nhiên đều 6 chữ số có bao nhiêu bit entropy trước khi băm SHA-256?  
**Đáp:** Khoảng **19,93 bit**, không phải 256 bit.

**Câu 2.** Vì sao attacker offline không bị hạn chế bởi CAPTCHA?  
**Đáp:** Họ tự tính verifier từ dữ liệu đã lộ, không gọi login endpoint.

**Câu 3.** Salt cho hai tài khoản cùng password khác nhau sẽ giải quyết điều gì?  
**Đáp:** Phân biệt bản ghi, giảm hiệu quả bảng dựng sẵn và việc tái sử dụng cùng hash; **không** ngăn attacker thử từng candidate với salt đã biết.

**Câu 4.** PBKDF2 khác SHA-256 một lần ở đâu?  
**Đáp:** PBKDF2 có salt và work factor `iterations` khiến mỗi lần thử tốn nhiều vòng HMAC. Nó không memory-hard như Argon2id.

**Câu 5.** Vì sao không sinh salt mới mỗi khi user đăng nhập để so sánh?  
**Đáp:** Xác minh phải dùng salt lưu từ lúc đăng ký, sau đó chạy lại KDF trên password được nhập. Salt mới dùng khi tạo **verifier mới/rehash**.

**Câu 6.** Pepper là gì?  
**Đáp:** Secret bổ sung phía server, giữ ngoài DB; không thay thế salt và password KDF.

**Câu 7.** Nếu verifier cũ dùng 20.000 vòng PBKDF2 và chính sách mới đòi 600.000 vòng, nên xử lý thế nào?  
**Đáp:** Xác minh đúng theo tham số cũ; khi user login thành công, rehash từ password vừa nhập với salt mới/cost mới và lưu record có metadata.

**Câu 8.** Trong một vụ lộ password hashes SHA-256, chỉ thay hash hiện có bằng `SHA-256(SHA-256(password))` có giải quyết vấn đề không?  
**Đáp:** Không. Vẫn thiếu scheme chuyên dụng và không khôi phục an toàn cho password có thể đã bị attacker tìm ra.

## Tóm tắt mô hình

```text
Mật khẩu do con người chọn: thường ít entropy
                 |
                 v
SHA-256 một lần: thử ứng viên rất rẻ
                 |
                 v
Nếu verifier lộ, attacker thử offline

Phòng vệ đúng hướng:
CSPRNG salt riêng + password KDF có cost
                 |
       +---------+-----------+
       |                     |
   Argon2id/scrypt       PBKDF2/bcrypt
   CPU + memory          cost theo vòng
       |                     |
       +---------+-----------+
                 |
                 v
Lưu {scheme/version/params/salt/hash}
                 |
                 v
Login: KDF với salt lưu sẵn + so sánh an toàn
                 |
                 v
Kết hợp rate limit, MFA và quản lý nâng cấp
```

**Độ dài của hash không làm cho password yếu trở nên khó đoán.** Muốn bảo vệ password verifier khi database bị đánh cắp, phải khiến **mỗi ứng viên** trở nên tốn tài nguyên để kiểm tra, thêm salt độc lập và điều chỉnh cost theo thời gian.

## Tài liệu tham khảo chính thức

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): Argon2id, scrypt, bcrypt, PBKDF2, salt/pepper và nâng cấp verifier.
- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): verifier chống offline attacks, salt và cost phù hợp.
- [Java 17 PBEKeySpec API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): `char[]`, salt, iterations, key length và `clearPassword()`.
- [Java 17 SecretKeyFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html): factory cho cơ chế dẫn xuất khóa.
- [Java 17 SecureRandom API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): sinh salt bằng bộ sinh ngẫu nhiên mật mã.
- [Java 17 MessageDigest API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 và `isEqual`.
