# 7.4. PBKDF2 qua `SecretKeyFactory` và `PBEKeySpec` trong Java 21

**PBKDF2** (*Password-Based Key Derivation Function 2*) biến một mật khẩu do người dùng chọn thành chuỗi byte dẫn xuất bằng cách kết hợp **salt**, **số vòng lặp** (*iteration count*) và một hàm giả ngẫu nhiên (*PRF*, thường là HMAC). Trong Java 21, có thể sử dụng PBKDF2-HMAC-SHA256 qua API chuẩn `SecretKeyFactory` và `PBEKeySpec` của JCA/JCE, không cần thêm dependency cho ví dụ cơ bản.

Đây là chủ đề thuộc **“7. Mật khẩu và dẫn xuất khóa”** trong module Java Advanced – Security & Cryptography. Trọng tâm là hiểu đúng các tham số, dùng API Java để dẫn xuất/kiểm tra mật khẩu, lưu bản ghi có thể xác minh về sau, chọn chi phí phù hợp, và nhận ra các giới hạn bảo mật của PBKDF2.

## Mục tiêu

Sau khi học xong, bạn có thể:

1. Giải thích `PBKDF2(P, S, c, dkLen)`, vai trò của **password**, **salt**, **iterations**, **PRF** và **derived-key length**.
2. Phân biệt **hash mật khẩu để xác minh đăng nhập** với **dẫn xuất khóa cho mã hóa**, và phân biệt salt với pepper.
3. Dùng `new PBEKeySpec(char[], byte[], int, int)` và `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` để tạo byte dẫn xuất.
4. Xây dựng bản ghi có phiên bản/thuật toán/cost/salt/hash, xác minh bằng cách dẫn xuất lại và so sánh an toàn.
5. Kiểm tra ví dụ Java 21 có kết quả chính xác, xử lý bộ nhớ chứa mật khẩu, tránh salt yếu và chọn tham số có cơ sở.
6. Giải thích khi nào PBKDF2 là lựa chọn phù hợp, khi nào cần cân nhắc Argon2id, và cách nâng cấp tham số mà không làm mất tài khoản.

## 1. Vấn đề PBKDF2 giải quyết

Một mật khẩu như `"my-password"` thường có entropy thấp hơn rất nhiều so với khóa ngẫu nhiên 256 bit. **Không nên** lưu mật khẩu bản rõ, không lưu bản mã có thể giải mã để đăng nhập, và không lưu trực tiếp `SHA-256(password)` như một password verifier: SHA-256 tính rất nhanh nên kẻ tấn công có bản sao database có thể thử rất nhiều ứng viên.

PBKDF2 tăng chi phí thử một mật khẩu bằng cách lặp lại PRF nhiều lần. Với cùng password và **cùng** salt/iterations/PRF/key length, kết quả là **xác định**; với salt khác, kết quả gần như chắc chắn khác.

```text
Password (P) --\
                +--> PBKDF2(PRF, iterations=c) --> Derived key (DK)
Random salt (S)-/                         |
                                         \--> lưu/verifier hoặc dùng làm key material
```

**PBKDF2 không tự “mã hóa mật khẩu”.** Đó là hàm dẫn xuất khóa; khi áp dụng để xác minh đăng nhập, ứng dụng lưu **giá trị dẫn xuất** và tham số, không lưu password. Người đăng nhập gửi mật khẩu ứng viên; server tính lại PBKDF2 với salt/cost được lưu rồi so sánh.

**Mật khẩu vẫn có thể bị đoán ngoại tuyến** nếu database hash bị lộ; PBKDF2 làm việc đoán tốn CPU hơn, nhưng không thay thế mật khẩu mạnh, MFA, kiểm soát truy cập, giám sát xâm nhập, giới hạn thử đăng nhập hoặc chống rò rỉ bí mật.

## 2. Năm thành phần đầu vào và đầu ra

Ký hiệu chuẩn:

```text
DK = PBKDF2(P, S, c, dkLen; PRF)
```

| Thành phần | Ý nghĩa | Ví dụ trong bài |
| --- | --- | --- |
| `P` | Password, dữ liệu bí mật người dùng biết. Với Java, API nhận `char[]`; quy tắc chuyển ký tự thành byte cần thống nhất khi liên thông hệ thống. | `char[] password` |
| `S` | Salt: byte ngẫu nhiên **riêng cho từng bản ghi**, không cần giữ bí mật. | `byte[16]` = 128 bit từ `SecureRandom` |
| `c` | Số lần lặp PBKDF2, **số nguyên dương**; tăng c làm mỗi lần đoán tốn thời gian hơn. | `600_000` vòng cho ví dụ lưu mật khẩu |
| `dkLen` | Độ dài đầu ra, **tính bằng byte trong công thức PBKDF2**. | 32 byte |
| `PRF` | Hàm giả ngẫu nhiên, thường là `HMAC-SHA256` hoặc `HMAC-SHA512`. | `HMAC-SHA256` |
| `DK` | Byte dẫn xuất có độ dài đã chọn. | `byte[32]` |

**Chi tiết rất dễ nhầm:** tham số `keyLength` trong constructor Java `PBEKeySpec(password, salt, iterationCount, keyLength)` có đơn vị **bit**, không phải byte. Muốn đầu ra 32 byte cần truyền **256**, chứ không phải 32.

Salt dài 16 byte được chọn mới cho **mỗi lần tạo hash/mỗi tài khoản** là lựa chọn thông dụng. Có thể lưu salt công khai cạnh hash; không cần “mã hóa salt” để tăng bảo mật. Salt giúp chống bảng tính trước và khiến hai người dùng cùng mật khẩu không có cùng bản ghi hash. Salt **không phải khóa bí mật** và không tự chặn thử mật khẩu yếu.

**Pepper** khác salt: pepper là bí mật cấp ứng dụng, thường lưu tách database (KMS/HSM hoặc secret manager). Pepper có thể bổ sung phòng vệ nhưng phải có kế hoạch rotate, mất khóa và khôi phục; pepper không thay được salt hay work factor.

## 3. PBKDF2 vận hành thế nào?

Với `PBKDF2WithHmacSHA256`, PRF là HMAC-SHA256 có output 32 byte. PBKDF2 tính các khối đầu ra bằng chuỗi PRF lặp lại và phép XOR.

Ở khối thứ `i` (đánh số từ 1), diễn đạt từ RFC 8018:

```text
U_1 = PRF(P, S || INT_32_BE(i))
U_2 = PRF(P, U_1)
U_3 = PRF(P, U_2)
...
U_c = PRF(P, U_(c-1))

T_i = U_1 XOR U_2 XOR ... XOR U_c
DK  = (T_1 || T_2 || ... ) lấy đúng dkLen byte
```

Trong đó `INT_32_BE(i)` là số khối biểu diễn bằng 4 byte big-endian; `||` là phép nối. Nếu cần 32 byte từ HMAC-SHA256, chỉ cần một khối; nếu cần 64 byte, sẽ có hai khối. Thời gian tính gần tỷ lệ với số vòng lặp và số khối đầu ra.

Một số tính chất quan trọng:

- Cùng `P, S, c, dkLen, PRF` phải cho cùng `DK` khi cách chuyển password thành byte giống nhau.
- Tăng `c` không làm mật khẩu tự có thêm entropy; mục đích là làm **mỗi lần thử** tốn thời gian hơn.
- Salt mới không làm password mạnh hơn, nhưng ngăn việc tái sử dụng kết quả dò tìm tiền tính cho mọi tài khoản.
- Sinh `DK` dài 256 bit không biến một mật khẩu có vài bit entropy thành khóa ngẫu nhiên có 256 bit entropy.
- PBKDF2 chủ yếu tốn CPU, **không memory-hard** như Argon2id; do đó không phải lựa chọn ưu tiên mặc định cho mọi hệ thống mật khẩu mới.

Thông thường **không tự triển khai** vòng lặp `U_i`/XOR trong ứng dụng Java. Dùng implementation JCA/JCE đã được kiểm thử, rồi tập trung thiết kế salt, cost, storage, so sánh và quản trị vòng đời.

## 4. API Java 21: `SecretKeyFactory` + `PBEKeySpec`

Các import chính:

```java
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.security.SecureRandom;
```

Luồng API cơ bản:

```java
char[] password = /* mật khẩu lấy từ input an toàn */;
byte[] salt = new byte[16];
new SecureRandom().nextBytes(salt);

PBEKeySpec spec = new PBEKeySpec(password, salt, 600_000, 256);
try {
    SecretKeyFactory factory =
            SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
    byte[] derived = factory.generateSecret(spec).getEncoded();
    // Dùng derived theo mục đích đã định; không log và xóa khi xong.
} finally {
    spec.clearPassword();
    // Caller còn trách nhiệm xử lý/xóa mảng password của chính mình.
}
```

**Đây là đoạn mã minh họa**, không phải file Java chạy độc lập: biến `password` phải lấy từ input thật và byte `derived` cần được quản lý trong scope thích hợp. Phần 5 và 6 có chương trình độc lập, biên dịch được.

Các thành phần:

- `PBEKeySpec` là đối tượng mô tả **password, salt, iteration count, key length**. Constructor kiểm tra salt không null/rỗng, count và key length dương; đối tượng **clone** password và salt để lưu nội bộ.
- `clearPassword()` xóa **bản sao password trong PBEKeySpec**, không xóa bản gốc do caller giữ. Khi không còn cần, caller phải `Arrays.fill(password, '\0')` trong `finally`. `getPassword()` trả bản sao; không nên gọi chỉ để kiểm tra hoặc log.
- `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` chọn implementation từ **security provider** có hỗ trợ tên thuật toán này. Tên này thuộc Java Security Standard Algorithm Names; SunJCE trong JDK 21 cung cấp implementation. Không phải mọi provider bên ngoài đều bắt buộc hỗ trợ.
- `generateSecret(spec)` tạo `SecretKey`. Với provider hỗ trợ xuất key material, `getEncoded()` trả mảng byte của khóa dẫn xuất (đối với demo PBKDF2). Provider có thể từ chối xuất khóa và trả `null`; code sản phẩm nên xử lý trường hợp đó.
- `getEncoded()` là byte nhạy cảm: không chuyển sang `String` để log, không trả về API response, và chỉ giữ trong RAM trong thời gian cần thiết.
- `NoSuchAlgorithmException` chỉ ra provider/runtime không cung cấp thuật toán; `InvalidKeySpecException` hoặc lỗi tham số liên quan mật khẩu/salt/cost cần được xử lý như lỗi cấu hình/triển khai, không đánh đồng với việc “user nhập sai password”.

**Chú ý Unicode và tính tương thích:** Javadoc của `PBEKeySpec` lưu ý các cơ chế password-based có thể sử dụng số bit khác nhau của ký tự; tài liệu provider còn có giới hạn riêng. Khi cần so khớp hash giữa Java, Node.js, Python hoặc giữa các provider, phải quy định rõ encoding/normalization và kiểm thử với mật khẩu **có dấu, emoji, ký tự kết hợp**; đừng mặc định hai nơi cùng truyền `"mật khẩu"` sẽ ra cùng byte đầu vào. Ví dụ deterministic ở phần tiếp theo dùng ASCII để không tạo giả định Unicode.

## 5. Thí nghiệm kiểm chứng: test vector PBKDF2-HMAC-SHA256

Ví dụ đầu tiên sử dụng password ASCII `password`, salt ASCII `salt`, output 256 bit và chỉ **1 hoặc 2 lần lặp** để tạo vector có thể kiểm tra từng byte. Chi phí này chỉ dành cho **kiểm thử chức năng**; tuyệt đối không sử dụng 1–2 iterations để lưu password người dùng.

Tạo file **`Pbkdf2Vector.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class Pbkdf2Vector {
    public static void main(String[] args) throws Exception {
        char[] password = "password".toCharArray();
        byte[] salt = "salt".getBytes(StandardCharsets.US_ASCII);
        try {
            for (int iterations : new int[] {1, 2}) {
                PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, 256);
                try {
                    byte[] derived = SecretKeyFactory
                            .getInstance("PBKDF2WithHmacSHA256")
                            .generateSecret(spec).getEncoded();
                    System.out.println(iterations + ": " +
                            HexFormat.of().formatHex(derived));
                    Arrays.fill(derived, (byte) 0);
                } finally {
                    spec.clearPassword();
                }
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Trong terminal đã dùng JDK 21 (hoặc compiler mới hơn hỗ trợ `--release 21`):

```text
javac -version
javac --release 21 -encoding UTF-8 Pbkdf2Vector.java
java Pbkdf2Vector
```

Stdout chính xác:

```text
1: 120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b
2: ae4d0c95af6b46d32d0adff928f06dd02a303f8ef3c251dfd6e2d85a95474c43
```

Bạn nên tự giải thích:

- Đầu vào chỉ khác **`iterations`**, nên output khác.
- Mỗi kết quả hexadecimal dài 64 ký tự = 32 byte = 256 bit.
- `HexFormat` dùng để **hiển thị kết quả thử nghiệm**; không có tác dụng làm PBKDF2 mạnh hơn.
- Code chỉ là vector chức năng; với mật khẩu thực, salt phải dài/ngẫu nhiên riêng cho từng bản ghi và count phải đủ lớn.

## 6. Ví dụ lưu và xác minh mật khẩu hoàn chỉnh

Mục tiêu: một API đăng ký tạo salt ngẫu nhiên và record lưu trữ; lúc đăng nhập, server đọc record rồi PBKDF2 lại mật khẩu ứng viên. Không có phép giải mã password.

Định dạng bản ghi sử dụng trong ví dụ:

```text
pbkdf2-sha256:600000:<salt-base64url>:<hash-base64url>
```

Trong đó `pbkdf2-sha256` xác định thuật toán, `600000` là work factor được dùng khi tạo, `salt` là 16 byte ngẫu nhiên mã hóa Base64URL và `hash` là 32 byte dẫn xuất mã hóa Base64URL. Ký tự `:` chỉ là delimiter do **ứng dụng này tự định nghĩa**, không phải format tiêu chuẩn chung cho mọi thư viện Java. Base64 dùng để lưu byte vào trường văn bản, **không phải mã hóa bí mật**.

Tạo file **`PasswordHashDemo.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordHashDemo {
    private static final String ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final String ID = "pbkdf2-sha256";
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;
    private static final int ROUNDS = 600_000;
    private static final int MAX_ROUNDS = 3_000_000;
    private static final SecureRandom RANDOM = new SecureRandom();

    static byte[] derive(char[] password, byte[] salt,
                         int iterations, int bits)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, bits);
        try {
            byte[] derived = SecretKeyFactory.getInstance(ALGORITHM)
                    .generateSecret(spec).getEncoded();
            if (derived == null || derived.length != bits / 8) {
                throw new GeneralSecurityException("PBKDF2 output unavailable");
            }
            return derived;
        } finally {
            spec.clearPassword();
        }
    }

    static String createRecord(char[] password)
            throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] derived = derive(password, salt, ROUNDS, KEY_BITS);
        try {
            Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
            return ID + ":" + ROUNDS + ":" +
                    encoder.encodeToString(salt) + ":" +
                    encoder.encodeToString(derived);
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    }

    static boolean verify(char[] candidate, String record)
            throws GeneralSecurityException {
        String[] fields = record.split(":", -1);
        if (fields.length != 4 || !ID.equals(fields[0])) {
            return false;
        }
        int iterations;
        byte[] salt;
        byte[] expected;
        try {
            iterations = Integer.parseInt(fields[1]);
            if (iterations < ROUNDS || iterations > MAX_ROUNDS) {
                return false;
            }
            Base64.Decoder decoder = Base64.getUrlDecoder();
            salt = decoder.decode(fields[2]);
            expected = decoder.decode(fields[3]);
        } catch (IllegalArgumentException e) {
            return false;
        }
        if (salt.length != SALT_BYTES || expected.length != KEY_BITS / 8) {
            Arrays.fill(expected, (byte) 0);
            return false;
        }
        try {
            byte[] actual = derive(candidate, salt, iterations, KEY_BITS);
            try {
                return MessageDigest.isEqual(actual, expected);
            } finally {
                Arrays.fill(actual, (byte) 0);
            }
        } finally {
            Arrays.fill(expected, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        // Chuỗi literal chỉ để demo; password thực lấy từ input an toàn.
        char[] registration = "correct horse battery staple".toCharArray();
        char[] correct = "correct horse battery staple".toCharArray();
        char[] wrong = "wrong password".toCharArray();
        try {
            String record = createRecord(registration);
            System.out.println("format: " + record.startsWith(ID + ":"));
            System.out.println("correct: " + verify(correct, record));
            System.out.println("wrong: " + verify(wrong, record));
        } finally {
            Arrays.fill(registration, '\0');
            Arrays.fill(correct, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

Biên dịch và chạy:

```text
javac --release 21 -encoding UTF-8 PasswordHashDemo.java
java PasswordHashDemo
```

Stdout chính xác:

```text
format: true
correct: true
wrong: false
```

Chương trình **không in record**, do salt ngẫu nhiên nên chuỗi record khác nhau giữa các lần chạy. Hai lần dẫn xuất trong `verify` dùng lại **đúng salt và cost đã lưu**, vì vậy mật khẩu đúng được chấp nhận. Mật khẩu sai dẫn tới byte khác và trả `false`.

### 6.1 Phân tích bảo vệ và giới hạn của từng dòng

**`RANDOM.nextBytes(salt)`** tạo một salt mới 16 byte; không dùng `Random`, timestamp, user ID hoặc password làm nguồn “ngẫu nhiên”. Nếu cần salt cho người dùng thứ hai, gọi lại `createRecord` để nhận salt mới.

**`ROUNDS = 600_000`** là mức tối thiểu mà hướng dẫn OWASP Password Storage hiện nêu cho **PBKDF2-HMAC-SHA256** (tại thời điểm biên soạn). Đây không phải hằng số “đúng mãi mãi” hoặc bảo đảm an toàn trong mọi hoàn cảnh. Thực tế cần benchmark p95/p99 dưới tải cao, cập nhật theo khuyến nghị mới và giới hạn năng lực máy chủ. `MAX_ROUNDS = 3_000_000` chỉ là trần bảo vệ parsing/CPU **ví dụ**; hệ thống thật định nghĩa chính sách tối thiểu/tối đa có quản trị, cân nhắc migration và chống DoS.

**`PBEKeySpec` và `clearPassword()`:** `PBEKeySpec` giữ bản clone của `char[]` nên gọi `clearPassword()` trong `finally` kể cả khi `generateSecret` lỗi. Bản `char[]` truyền vào từ API vẫn thuộc người gọi và phải được xóa riêng.

**`MessageDigest.isEqual(actual, expected)`** cung cấp cách so sánh hai mảng byte cho kiểm tra tag/digest, hữu ích để tránh tự viết vòng lặp dừng khi gặp byte khác. Ví dụ giới hạn kích thước hash về 32 byte trước khi so. Không suy ra toàn bộ endpoint sẽ có thời gian cố định: thời gian parsing, số vòng lặp, sự tồn tại của tài khoản và error path vẫn khác nhau.

**`Arrays.fill(derived, (byte) 0)`** dọn mảng derived do mã ứng dụng nắm giữ. Java/JVM có thể tạo các bản sao trong provider, garbage collector hoặc log bên ngoài; không thể hứa “đã xóa mọi bản sao của bí mật trong RAM”. Tránh tạo `String` không cần thiết chứa password. Đoạn mã demo vẫn dùng string literal để test dễ đọc, **không áp dụng literal đó cho mật khẩu production**.

**`verify` kiểm tra format và giới hạn iteration/độ dài** trước khi thực hiện PBKDF2 để tránh chấp nhận record sai cấu trúc hoặc cost bất thường. Với record lấy từ database tin cậy, vẫn cần giới hạn kích thước chuỗi trước khi split/decode; khi record có thể bị chỉnh, phải xử lý input không tin cậy và phân biệt lỗi dữ liệu với mật khẩu sai. Những lỗi infrastructure/provider nên được báo qua cơ chế lỗi nội bộ, không trả chi tiết crypto ra client.

**Giới hạn còn lại:** đoạn demo chưa xử lý password policy, rate limiting, MFA, session/token, truy vấn user ID, account lockout, logging an toàn, Unicode policy, pepper/KMS, benchmark chi phí, hay nâng cấp hash cũ. Chỉ dùng làm mô hình API + record format, không coi như hệ thống authentication hoàn chỉnh.

## 7. Lưu gì trong cơ sở dữ liệu?

Một bản ghi verifier nên chứa đủ thông tin để kiểm tra sau này:

| Trường | Ví dụ | Giải thích |
| --- | --- | --- |
| `scheme/version` | `pbkdf2-sha256` | Xác định cách dẫn xuất/encoding và phiên bản format. |
| `iterations` | `600000` | Phải lưu với từng record, vì chính sách work factor sẽ đổi theo thời gian. |
| `salt` | Base64URL 16 byte | Mỗi record một salt ngẫu nhiên; công khai được. |
| `derivedKey` | Base64URL 32 byte | Giá trị dùng để kiểm chứng mật khẩu, cần bảo vệ như password verifier. |
| `createdAt/rehashPolicy` (tùy hệ thống) | Thời điểm tạo, phiên bản cấu hình | Giúp quản trị và nâng cấp, không phải đầu vào bắt buộc của PBKDF2. |

**Không lưu** password bản rõ, một “mật khẩu mã hóa để giải mã”, hay secret pepper trong cùng bảng. Tránh log cả record hash: dù không phải password gốc, record chứa đủ đầu vào công khai để kẻ có bản sao thử đoán ngoại tuyến. Bảo vệ backup, snapshot, quyền truy cập DB, bí mật cấu hình và luồng đăng nhập.

Ở lần đăng nhập:

1. Tra bản ghi theo danh tính/ID đã được quy định.
2. Kiểm tra scheme/format/giới hạn trước khi tính toán.
3. Tạo `PBEKeySpec` từ **password ứng viên** với salt/iterations/keyLength của record.
4. Dẫn xuất lại bằng **đúng PRF**, so sánh bằng byte (không so hash qua String nếu có thể tránh).
5. Nếu hợp lệ và record có work factor thấp hơn chính sách mới, **rehash** bằng salt mới + cost mới, ghi cập nhật an toàn (ví dụ optimistic concurrency trong giao dịch) trước hoặc sau khi tạo session theo thiết kế.
6. Trả lỗi đăng nhập chung cho mật khẩu sai/ID không có, áp dụng rate limit và quan sát sự kiện an ninh; không tiết lộ chi tiết record.

**Migration từ cost thấp:** demo đặt `verify` từ chối count thấp hơn 600.000 vì cố ý áp dụng chính sách chặt cho dữ liệu mới. Nếu hệ thống có bản ghi cũ 100.000 vòng, luồng thực tế cần **bộ xác minh legacy được kiểm soát** rồi nâng lên 600.000 sau đăng nhập thành công; không dùng nguyên hàm `verify` của demo cho migration và vô tình khóa tài khoản cũ. Khi đổi thuật toán, cần dispatcher theo version trong record và kế hoạch reset/migrate nếu thuật toán cũ quá yếu.

## 8. Chọn iteration count và thuật toán

PBKDF2 có thể phù hợp khi hệ thống yêu cầu **implementation có sẵn trong JDK** hoặc một chế độ tuân thủ tiêu chuẩn cụ thể; với hệ thống lưu password mới, [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) ưu tiên **Argon2id** và xem PBKDF2-HMAC-SHA256 là lựa chọn cần cấu hình chi phí đủ cao (đặc biệt trong môi trường có ràng buộc FIPS).

| Thuật toán | Tính chất | Đề xuất sử dụng |
| --- | --- | --- |
| `SHA-256(password)` hoặc `MD5(password)` | Rất nhanh, thiếu work factor/salt hợp lý | **Không** dùng làm password verifier mới. |
| `PBKDF2WithHmacSHA1` | PBKDF2 với HMAC-SHA1; thường để tương thích legacy | Ưu tiên `PBKDF2WithHmacSHA256` cho thiết kế mới nếu cần PBKDF2. |
| `PBKDF2WithHmacSHA256` | Work factor CPU + salt; có qua `SecretKeyFactory` Java 21/SunJCE | Sử dụng khi điều kiện triển khai phù hợp, benchmark và tuân theo chính sách hiện hành. |
| `scrypt` | Hàm dẫn xuất có chi phí bộ nhớ; không phải API JDK `SecretKeyFactory` chuẩn chung | Cân nhắc khi cần memory-hard và thư viện được kiểm thử. |
| `Argon2id` | Memory-hard, có tham số bộ nhớ/time/parallelism | Phương án được OWASP ưu tiên cho hệ thống mật khẩu mới; cần implementation tin cậy bên ngoài JDK chuẩn. |

**Cách benchmark hợp lý:**

- Thực hiện trên **cấu hình production** (CPU, số worker, container quota, virtualized hardware), đo độ trễ PBKDF2 lúc ít tải và lúc có nhiều phiên đăng nhập đồng thời.
- Chọn cost theo hướng dẫn bảo mật mới nhất, ngân sách độ trễ và khả năng chống credential stuffing/DoS. Tăng iterations làm cả **client hợp lệ và attacker** tốn CPU; cần giới hạn tần suất, queue và resource budget.
- Đặt giới hạn **tối đa** cho iteration được đọc từ record/đầu vào ngoài để tránh kẻ tấn công ép một yêu cầu tiêu thụ CPU khổng lồ.
- Lưu iterations với record, tăng cost cho record mới; sau khi người dùng đăng nhập đúng, nâng cấp từng record khi cần.
- Dùng salt mới khi rehash, ghi nhận scheme version; không sửa iterations trên record cũ mà giữ nguyên hash, vì như vậy mật khẩu đúng sẽ không còn khớp.

**Mức cost không phải bảo mật độc lập:** kẻ có GPU/ASIC có thể thực hiện nhiều phép thử; mật khẩu yếu vẫn có rủi ro. PBKDF2 không thay được chính sách mật khẩu mạnh và biện pháp bảo vệ tài khoản.

## 9. PBKDF2 cho password verifier khác PBKDF2 cho khóa AES

`PBKDF2` trả về *key material* và có thể được dùng cho nhiều mục đích; thiết kế phải xác định rõ **mục đích nào** ngay từ đầu.

**A. Xác minh mật khẩu đăng nhập:** lưu `salt + iterations + derivedHash`. Khi đăng nhập, so sánh output; không bao giờ cần giải mã để lấy lại password. Một record verifier không nên được tái sử dụng trực tiếp làm khóa mã hóa dữ liệu người dùng.

**B. Dẫn xuất khóa từ passphrase để mã hóa:** ứng dụng cần salt, cost, độ dài phù hợp thuật toán mã hóa (ví dụ AES-256 dùng 32 byte) rồi tạo khóa từ byte dẫn xuất. Chỉ dẫn xuất khóa **chưa đủ**: phải dùng mã hóa xác thực như AES-GCM với nonce/IV riêng, không lặp IV với cùng khóa, lưu metadata cần thiết và quản lý lỗi xác thực, backup và thay đổi mật khẩu. Nếu dùng chung passphrase cho nhiều mục đích, tách miền khóa bằng cách dùng salt/context độc lập hoặc KDF/key hierarchy được thiết kế rõ; không dùng cùng derived bytes làm password verifier lẫn encryption key.

Ví dụ minh họa **không độc lập** (giả sử `derived` là byte[32] đã dẫn xuất đúng cách):

```java
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

// Chỉ là bước chuyển key material sang key AES; chưa thực hiện mã hóa.
SecretKey aesKey = new SecretKeySpec(derived, "AES");
```

**Đừng nhầm salt PBKDF2 với IV/nonce của AES-GCM.** Salt làm mỗi lần dẫn xuất password độc lập; IV/nonce của cipher đảm bảo các lần mã hóa an toàn với cùng key. Chúng cần quy tắc quản lý riêng. Nếu dữ liệu mã hóa buộc phải giải mã bằng cùng passphrase về sau, phải lưu salt/cost/IV/format đã dùng; đổi salt sẽ dẫn tới khóa khác trừ khi có migration/rewrap.

## 10. Vấn đề thường gặp và cách xử lý

| Triệu chứng hoặc lỗi | Nguyên nhân hay gặp | Cách kiểm tra |
| --- | --- | --- |
| `NoSuchAlgorithmException: PBKDF2WithHmacSHA256` | JRE/provider không cung cấp algorithm, môi trường chạy khác JDK mong đợi | Xem `java -version`, provider, tên thuật toán và JDK Providers Documentation cho bản đang chạy. |
| `InvalidKeySpecException` | Spec không hợp lệ hoặc provider không thể chuyển đổi | Kiểm tra loại `KeySpec`, cost, length và provider. |
| `IllegalArgumentException` ở `PBEKeySpec` | Salt rỗng, iterations không dương hoặc keyLength không dương | Đọc constructor docs, dùng salt không rỗng/cost dương/bit length đúng. |
| `getEncoded() == null` | Key không được provider xuất raw byte | Bắt rõ lỗi, không mặc định mọi `SecretKey` đều extractable. |
| Xác minh mật khẩu luôn sai | Salt/cost/PRF/encoding không đúng giữa tạo và verify; đổi format mà không version | Lưu đủ tham số, kiểm thử vector, kiểm tra normalization/Unicode. |
| Hai account cùng mật khẩu có cùng hash | Dùng chung salt, salt cố định, không sinh lại | Mỗi lần tạo record sinh salt mới bằng `SecureRandom`. |
| Hiệu năng đăng nhập kém khi tải cao | Cost lớn, nhiều request song song, thiếu rate limit/resource budget | Benchmark trên hạ tầng thực, giới hạn đồng thời và tần suất. |
| Bản ghi cũ không đăng nhập được sau khi tăng cost | Chỉ đổi iterations cấu hình mà không rehash; verifier chặn legacy | Dùng record version và migration sau xác minh thành công. |
| Test vector 1–2 vòng chạy đúng nhưng chưa an toàn | Vector chỉ kiểm tra **đúng thuật toán**, không kiểm tra work factor | Dùng policy cost cao, salt riêng và kiểm thử an ninh. |
| Log chứa password/hash/key | Vô tình chuyển char[]/byte[] thành String hoặc in debug | Loại bỏ logging bí mật, giới hạn truy cập debug và xóa mảng nhạy cảm khi dùng xong. |

Lưu ý thêm: `PBEKeySpec` nhận `char[]` nhưng API web thường nhận byte từ UTF-8 rồi framework chuyển thành `String`. Không thể xóa hoàn toàn String bất biến đã đi qua JVM; làm sạch `char[]` vẫn có giá trị nhưng không nên tuyên bố đã xóa hết bí mật. Khi cần kiểm thử đa hệ thống, **xác định chính sách chuẩn hóa trước khi tạo record** và duy trì nó qua mọi lần đăng nhập.

## 11. Bài tập thực hành và checklist

1. **Tham số:** vì sao `new PBEKeySpec(password, salt, 600_000, 32)` không có nghĩa là “hash 32 byte”? Hãy sửa thành key length đúng.
2. **Kiểm thử vector:** chạy `Pbkdf2Vector.java` và so đúng hai giá trị hexadecimal. Thay `iterations=2` thành 3 và giải thích vì sao output đổi dù password/salt không đổi.
3. **Đăng ký và đăng nhập:** chạy `PasswordHashDemo.java`; tự thêm một lần tạo record thứ hai từ cùng password, xác nhận salt của hai record khác nhau. Chỉ hiển thị boolean so sánh, tránh log bản ghi thật.
4. **Mô hình dữ liệu:** thiết kế schema lưu `scheme, cost, salt, hash` và chính sách migration từ 200.000 lên 600.000 iterations mà không vô hiệu hóa tài khoản cũ.
5. **Tính toán:** salt 16 byte có bao nhiêu bit? DK 256 bit có bao nhiêu byte? 32 byte hiển thị dạng hex cần bao nhiêu ký tự? Những kích thước này có ý nghĩa gì đối với bảo mật?
6. **Rà soát:** chỉ ra các lỗi trong mã giả sau: dùng cùng salt cho mọi user, `SHA-256(password)`, so sánh hash bằng `String.equals`, hardcode key, và chỉ thay iterationCount khi nâng cấp record.
7. **Tình huống production:** nếu 600.000 iterations mất nhiều thời gian dưới tải đăng nhập, bạn đo những chỉ số nào và thêm những biện pháp nào trước khi giảm work factor? Nếu chính sách khuyến nghị thay đổi sau một năm, bạn cập nhật record bằng cách nào?
8. **Tính tương thích:** kiểm tra mật khẩu tiếng Việt có dấu và ký tự Unicode kết hợp giữa hai môi trường JDK/provider; mô tả cách đảm bảo cùng byte input, cùng cost, salt, PRF và DK length.

**Tiêu chí hoàn thành:** bạn có thể giải thích rõ tại sao phải dùng `SecretKeyFactory` + `PBEKeySpec` với **salt ngẫu nhiên, work factor đủ lớn, key length tính bằng bit**, lưu các tham số cần thiết, xác minh lại an toàn, và biết khi nào phải thay PBKDF2 bằng cơ chế password hashing memory-hard.

## 12. Tài liệu đáng tin cậy để đối chiếu

- [Java SE 21 – `javax.crypto.SecretKeyFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKeyFactory.html): cách lấy instance, `generateSecret(KeySpec)`, provider và exception.
- [Java SE 21 – `javax.crypto.spec.PBEKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): constructor, đơn vị `keyLength`, clone password/salt, `clearPassword()` và lưu ý về password characters.
- [Java SE 21 – `java.security.SecureRandom`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html): nguồn ngẫu nhiên bảo mật để sinh salt.
- [Java SE 21 – Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): tên thuật toán `PBKDF2WithHmacSHA256`.
- [Java SE 21 – JDK Providers Documentation](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html): khả năng hỗ trợ `SecretKeyFactory` PBKDF2 trong SunJCE và các ghi chú provider.
- [RFC 8018 – PKCS #5: Password-Based Cryptography Specification v2.1](https://www.rfc-editor.org/rfc/rfc8018): công thức PBKDF2, salt và iteration count.
- [OWASP – Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): lựa chọn Argon2id/scrypt/PBKDF2, salt, pepper, chi phí và rehash.

