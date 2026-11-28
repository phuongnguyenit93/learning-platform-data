# Không dùng Math.random cho security

> **Chương:** Secure randomness  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Vấn đề: “ngẫu nhiên” chưa chắc đã “an toàn”

Khi viết Java, lập trình viên có thể dùng `Math.random()` để chọn một phần tử bất kỳ, sinh màu ngẫu nhiên hoặc mô phỏng một lần tung xúc xắc. Tuy nhiên, **không được dùng `Math.random()` để tạo những giá trị mà tính bảo mật phụ thuộc vào việc kẻ tấn công không thể đoán được**.

Ví dụ có vấn đề:

~~~java
// KHÔNG DÙNG CHO SECURITY:
int otp = (int) (Math.random() * 1_000_000);
String resetCode = Long.toHexString((long) (Math.random() * Long.MAX_VALUE));
~~~

Hai đoạn code tạo ra các giá trị nhìn có vẻ thay đổi qua mỗi lần chạy, nhưng `Math.random()` **không có hợp đồng bảo mật của một bộ sinh ngẫu nhiên mật mã (CSPRNG)**. Nếu đầu ra hoặc trạng thái của bộ sinh bị dự đoán trong một tình huống cụ thể, các giá trị được tạo có thể không còn là bí mật.

**Quy tắc chính:** 

- Dùng **`java.security.SecureRandom`** hoặc **API sinh khóa mật mã phù hợp** như `KeyGenerator`, `KeyPairGenerator` để tạo bí mật.
- Dùng **`Math.random()`**, `java.util.Random`, `ThreadLocalRandom` cho mô phỏng, phân bổ ngẫu nhiên không nhạy cảm và những công việc **không cần khả năng chống dự đoán**.
- Không nhầm **khó dự đoán**, **không trùng lặp** và **được phép dùng trong giao thức**: mỗi thuộc tính có yêu cầu riêng.

Bài học này đặt quy tắc trên vào bối cảnh quản lý khóa: **tạo khóa, lưu khóa, sử dụng, xoay vòng, thu hồi, hủy, KMS/HSM, envelope encryption, IAM và kiểm toán**. Một khóa được sinh kém ngẫu nhiên có thể làm mất ý nghĩa của những lớp bảo vệ phía sau.

## 2. `Math.random()` tạo ra gì?

Trong Java, `Math.random()` trả về một số kiểu `double` giả ngẫu nhiên, không âm và **nhỏ hơn 1.0**. Nó rất tiện cho logic như:

~~~java
double x = Math.random();             // 0.0 <= x < 1.0
int dice = 1 + (int) (Math.random() * 6); // Mô phỏng xúc xắc
~~~

Một **PRNG (pseudorandom number generator)** sinh đầu ra từ trạng thái nội bộ theo quy tắc xác định. Có nhiều PRNG phù hợp cho mô phỏng, nhưng không được thiết kế để đối đầu với kẻ tấn công quan sát, suy đoán hay tìm cách khôi phục trạng thái.

**CSPRNG (cryptographically secure PRNG)** là loại PRNG được thiết kế để, với giả định về thuật toán, seed, trạng thái và môi trường triển khai, kẻ tấn công không có khả năng thực tế dự đoán đầu ra chưa được sinh.

| Thuộc tính | `Math.random()` | `SecureRandom` được cấu hình phù hợp |
| --- | --- | --- |
| Mục tiêu API | Số giả ngẫu nhiên tiện dụng | Vật liệu ngẫu nhiên phục vụ mật mã |
| Kết quả trực tiếp | `double` trong khoảng [0, 1) | Byte, số nguyên hoặc giá trị từ provider mật mã |
| Bảo đảm chống dự đoán theo hợp đồng bảo mật | **Không** | **Có mục tiêu bảo mật mật mã**, phụ thuộc thuật toán/provider/entropy |
| Dùng cho secret key, bearer token, reset token | **Không** | Có, với đúng kích thước và quy trình |
| Dùng cho xúc xắc mô phỏng, UI không nhạy cảm | Có | Có thể nhưng không cần thiết |
| Đảm bảo tuyệt đối không bao giờ trùng giá trị | **Không** | **Cũng không**; phải thiết kế uniqueness riêng |

Điểm quan trọng là **không có bảo đảm mật mã**, chứ không phải “mọi lần gọi `Math.random()` đều lập tức có thể bị tấn công”. Mức độ khai thác phụ thuộc triển khai và cách hệ thống sử dụng đầu ra; nhưng một API không cam kết khả năng chống dự đoán **không đáp ứng điều kiện thiết kế secret**.

### 2.1. Vì sao “thêm nhiều chữ số” không giúp?

~~~java
// KHÔNG AN TOÀN: ghép nhiều kết quả Math.random không
// biến bộ sinh không-mật-mã thành CSPRNG.
String candidate = Math.random() + "-" + Math.random()
        + "-" + System.currentTimeMillis();
~~~

Thêm timestamp, PID, username, địa chỉ IP hoặc ghép nhiều output **không tự thêm entropy bí mật đáng tin cậy**. Nếu những thành phần đó công khai hoặc dễ đoán, attacker có thể thu hẹp không gian tìm kiếm. Một chuỗi có 64 ký tự **không mặc nhiên có 256 bit entropy**.

**Entropy** là mức độ bất định của nguồn bí mật. Chiều dài biểu diễn, Base64, hex hoặc hàm băm **không tạo entropy từ đầu vào đã yếu**. Ví dụ, băm `SHA-256(Math.random() + timestamp)` cho ra 256 bit đầu ra, nhưng không thể lấy con số 256 đó làm mức bảo mật của secret.

## 3. Điều gì có thể xảy ra khi dùng `Math.random()` cho bảo mật?

### 3.1. Đoán được token hoặc mã đặt lại mật khẩu

Một token đặt lại mật khẩu là **bearer secret**: ai sở hữu nó có thể thực hiện thao tác nhạy cảm trong giới hạn quyền và thời gian của token. Nếu token có thể bị dự đoán, attacker có thể thử token của nạn nhân mà không cần chiếm hộp thư hoặc biết mật khẩu.

~~~mermaid
flowchart TD
    A[Ứng dụng tạo reset token] --> B{Nguồn randomness}
    B -->|Math.random / Random| C[Không có bảo đảm chống dự đoán]
    B -->|SecureRandom phù hợp| D[Token khó đoán đủ độ dài]
    C --> E[Nguy cơ attacker dự đoán hoặc thử giá trị]
    D --> F[TTL, một lần dùng, ràng buộc tài khoản, rate limit]
    E --> G[Rủi ro chiếm tài khoản]
    F --> H[Giảm rủi ro chiếm tài khoản]
~~~

Ngay cả token khó đoán cũng cần **hết hạn, giới hạn phạm vi, dùng một lần, kiểm tra chủ sở hữu và bảo vệ đường truyền**. CSPRNG chỉ giải quyết khâu khó đoán, không tự bổ sung authorization hay chống replay.

### 3.2. Khóa mã hóa có entropy thấp

Nếu ứng dụng lấp đầy 32 byte “khóa AES-256” bằng một PRNG dễ đoán hoặc từ timestamp:

- Kích thước **256 bit** của mảng byte không chứng minh khóa có **256 bit entropy**.
- Kẻ tấn công có thể tìm kiếm trong một tập khóa ứng viên nhỏ hơn rất nhiều nếu biết được cách tạo hoặc seed.
- Dữ liệu vẫn được AES-GCM mã hóa đúng thuật toán nhưng **tính bí mật của khóa nguồn đã yếu**.

Không thể khắc phục bằng cách cất khóa yếu đó vào kho an toàn sau khi đã tạo. **Phải sinh khóa đủ mạnh ngay từ đầu**, rồi mới cấp phát, lưu trữ, sử dụng, xoay vòng và hủy.

### 3.3. Mã OTP ngắn và nguy cơ thử đoán

Một OTP 6 chữ số có đúng **1.000.000 khả năng**, tương đương khoảng **19,93 bit** nếu phân phối đều. Ngay cả được tạo bằng CSPRNG, một mã như vậy **không thể thay thế secret 256 bit**.

Lỗi phổ biến gồm dùng nguồn ngẫu nhiên không phù hợp **và** quên giới hạn số lần thử. Với mã ngắn, cần kiểm soát TTL, số lần nhập, tốc độ, ràng buộc tài khoản/hành động và trạng thái đã sử dụng.

### 3.4. Rủi ro phát lại trạng thái và nhân bản môi trường

Trong các hệ thống ảo hóa, container hoặc restore từ snapshot, việc nhân bản trạng thái ngẫu nhiên hoặc bộ đếm có thể dẫn đến việc tái sử dụng giá trị ở các instance. Với các PRNG không mật mã, khả năng dự đoán còn có thể làm vấn đề nghiêm trọng hơn.

Đừng xem việc chạy ở nhiều node hoặc thêm `nodeId` là giải pháp cho mọi bí mật. **Randomness, cấp phát phạm vi nonce, khôi phục trạng thái và vòng đời khóa** cần được thiết kế đồng bộ.

## 4. Chọn API Java theo mục đích

| Mục đích | API gợi ý | Lý do |
| --- | --- | --- |
| Mô phỏng xác suất, game không dùng tài sản thật, dữ liệu demo | `Math.random()`, `Random` | Không yêu cầu bí mật khó đoán |
| Chọn phần tử thử nghiệm hoặc phân bổ công việc không nhạy cảm | `ThreadLocalRandom` | Phù hợp logic hiệu năng cao, không mang bảo đảm mật mã |
| Sinh 32 byte bearer token hoặc reset token | `SecureRandom.nextBytes()` | Cần token khó đoán |
| Mã OTP ngẫu nhiên 6 chữ số | `SecureRandom.nextInt(bound)` | Tránh dùng PRNG không mật mã; kết hợp giới hạn thử |
| Sinh AES-256 DEK | `KeyGenerator("AES")` cùng nguồn random phù hợp, hoặc API KMS | Đúng độ dài và kiểu khóa |
| Sinh cặp khóa RSA/EC/Ed25519 | `KeyPairGenerator` hoặc KMS/HSM | Thuật toán và policy của khóa |
| Sinh salt cho Argon2id/PBKDF2 | `SecureRandom.nextBytes()` hoặc thư viện hashing | Salt riêng cho từng verifier; không cần giữ bí mật |
| Nonce AES-GCM / ChaCha20-Poly1305 | Cơ chế nonce của giao thức/thư viện; random hoặc counter đúng quy tắc | **Tính duy nhất theo key** là điều kiện then chốt |
| ID UUID v4 | `UUID.randomUUID()` | ID ngẫu nhiên có cấu trúc; không tự xem là secret 256-bit |

**`java.util.Random` và `ThreadLocalRandom` không phù hợp cho tạo bí mật.** `UUID.randomUUID()` của Java dùng nguồn ngẫu nhiên mật mã cho UUID version 4, nhưng UUID v4 có **122 bit ngẫu nhiên** do một số bit dành cho cấu trúc phiên bản/biến thể. Nó không phải API sinh khóa AES-256 hoặc secret token có yêu cầu entropy 256 bit.

## 5. Cách dùng `SecureRandom` trong Java 17

`java.security.SecureRandom` trừu tượng hóa bộ sinh ngẫu nhiên mật mã do security provider cung cấp. Ở hệ thống sử dụng JDK/OS được cập nhật và cấu hình đúng, `new SecureRandom()` là điểm khởi đầu phổ biến. Không cần tự tạo seed từ đồng hồ:

~~~java
import java.security.SecureRandom;

public final class SecureRandomBasics {
    private static final SecureRandom RNG = new SecureRandom();

    public static byte[] randomBytes(int length) {
        if (length < 1 || length > 4096) {
            throw new IllegalArgumentException("Unsupported length");
        }
        byte[] bytes = new byte[length];
        RNG.nextBytes(bytes);
        return bytes;
    }
}
~~~

**Không có một “thuật toán SecureRandom duy nhất” trên mọi Java runtime.** Provider, nguồn entropy, cách khởi tạo, reseed và hành vi hiệu năng phụ thuộc JDK, hệ điều hành và cấu hình bảo mật. Nếu môi trường cần FIPS hoặc policy cụ thể, phải đánh giá **provider/thuật toán được phê duyệt** và kiểm thử vận hành.

### 5.1. `getInstanceStrong()` không phải lựa chọn mặc định cho mọi request

`SecureRandom.getInstanceStrong()` lấy một triển khai từ danh sách strong algorithms của runtime. Tùy hệ điều hành/provider, việc khởi tạo hoặc sinh đầu ra có thể có **độ trễ hoặc khả năng chờ nguồn entropy**. Nó không tự bảo đảm tốt hơn trong mọi trường hợp và không nên gọi trên từng request mà chưa benchmark.

Nếu không có yêu cầu đặc biệt, dùng `SecureRandom` theo cấu hình JDK được phê duyệt thường hợp lý hơn. **Không fallback sang `Math.random()` khi `SecureRandom` lỗi**, vì đó là biến lỗi hạ tầng thành lỗ hổng tạo secret. Cần fail closed hoặc xử lý lỗi theo thiết kế.

### 5.2. Không cố tự “tăng entropy” bằng seed tự chế

~~~java
// KHÔNG nên dùng để làm nguồn bảo mật:
// rng.setSeed(System.currentTimeMillis());
// byte[] seed = (hostname + processId).getBytes(UTF_8);
// SecureRandom rng = new SecureRandom(seed);
~~~

`setSeed` có thể bổ sung seed theo cách của provider; nó **không thay thế nguồn entropy đáng tin**. Cung cấp seed từ timestamp/PID/hostname không chứng minh hệ thống an toàn hơn, thậm chí dẫn tới sai lầm về chất lượng seed và tính tương thích. Không dùng kỹ thuật seed cố định trong production để làm kết quả “dễ debug”.

Với kiểm thử cần kết quả lặp lại, tạo **test double hoặc nguồn dữ liệu cố định trong test**, giữ tách biệt khỏi đường sinh secret ở production.

## 6. Ví dụ Java 17: token, OTP, salt và AES key

Đoạn code sau minh họa **bốn nhu cầu khác nhau**, cùng dùng nguồn randomness mật mã. Mỗi thứ có quy tắc sử dụng và quản lý riêng.

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.Locale;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class SecurityRandomDemo {
    private static final SecureRandom RNG = new SecureRandom();

    private SecurityRandomDemo() {}

    // Bearer token 32 byte = tối đa 256 bit entropy,
    // nếu RNG được cung cấp entropy/chính sách phù hợp.
    public static String newBearerToken() {
        byte[] raw = new byte[32];
        RNG.nextBytes(raw);
        try {
            return Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(raw);
        } finally {
            Arrays.fill(raw, (byte) 0);
        }
    }

    // Mã OTP ngẫu nhiên: 6 chữ số, KHÔNG phải 256-bit secret.
    public static String newOtp6() {
        int value = RNG.nextInt(1_000_000);
        return String.format(Locale.ROOT, "%06d", value);
    }

    // Salt không cần bí mật nhưng nên độc lập cho từng verifier.
    public static byte[] newPasswordSalt() {
        byte[] salt = new byte[16];
        RNG.nextBytes(salt);
        return salt;
    }

    // Ưu tiên KeyGenerator cho khóa AES.
    public static SecretKey newAes256Key() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    public static void main(String[] args) throws Exception {
        String bearer = newBearerToken();
        String otp = newOtp6();
        byte[] salt = newPasswordSalt();
        SecretKey aesKey = newAes256Key();

        // Demo chỉ in metadata, KHÔNG in giá trị bí mật.
        System.out.println("Bearer token characters: " + bearer.length());
        System.out.println("OTP digits: " + otp.length());
        System.out.println("Salt bytes: " + salt.length);
        System.out.println("AES key algorithm: " + aesKey.getAlgorithm());
        Arrays.fill(salt, (byte) 0);
        // Bảo vệ AES key/token theo lifecycle; không ghi vào log.
    }
}
~~~

Đoạn code có ý nghĩa minh họa. Ở production:

1. **Token:** chỉ hiển thị giá trị dạng rõ cho bên được cấp đúng lúc cần; có thể lưu **hash của token có entropy cao** thay vì raw token, cùng trạng thái thu hồi, TTL, tenant và scope.
2. **OTP:** lưu trạng thái/ràng buộc với tài khoản hoặc giao dịch; giới hạn số lần nhập, TTL và chỉ dùng một lần. `nextInt(bound)` tránh lỗi ánh xạ modulo nếu dùng đúng API.
3. **Salt:** lưu cùng verifier do Argon2id/PBKDF2 tạo ra. Salt **không phải password và không cần KMS** chỉ để giữ bí mật.
4. **AES key:** bảo vệ bằng keystore/KMS/HSM hoặc cơ chế envelope encryption; tránh lưu raw key trong source, config, DB, log hay crash dump.
5. **Bộ nhớ:** `Arrays.fill` chỉ xóa một số bản sao byte do mã nguồn nắm giữ. Không bảo đảm mọi bản sao của secret trong JVM đã được xóa ngay; `String` cũng không thể xóa byte nội bộ một cách chắc chắn.

### Token được lưu thế nào?

Một token sinh từ 32 byte CSPRNG có thể được lưu ở dạng **SHA-256 của token** để tra cứu thay vì lưu raw token, vì token có entropy cao. Khi kiểm tra token theo dữ liệu hash, cần dùng mã hóa byte nhất quán, xử lý so sánh theo chính sách an toàn và kiểm tra tài khoản/quyền/hạn dùng.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public final class TokenDigest {
    private TokenDigest() {}

    public static byte[] sha256OfOpaqueToken(String token)
            throws Exception {
        return MessageDigest.getInstance("SHA-256")
                .digest(token.getBytes(StandardCharsets.US_ASCII));
    }
}
~~~

**Không áp dụng cùng logic “SHA-256 đủ nhanh” cho mật khẩu do con người đặt.** Mật khẩu có entropy thấp nên cần **Argon2id, scrypt, bcrypt hoặc PBKDF2** với salt và chi phí theo chính sách. Opaque token 256-bit được tạo bằng CSPRNG và mật khẩu người dùng là **hai lớp bí mật khác nhau**.

## 7. `Math.random()` sai như thế nào trong các trường hợp phổ biến?

### 7.1. Session token và reset token

~~~java
// KHÔNG AN TOÀN: dữ liệu xác thực phụ thuộc Math.random.
String resetToken = Long.toString((long) (Math.random() * Long.MAX_VALUE));

// NÊN DÙNG: hàm sinh từ SecureRandom với ít nhất độ dài đã quy định.
String secureResetToken = SecurityRandomDemo.newBearerToken();
~~~

Sau khi sinh token an toàn, hệ thống vẫn phải **ràng buộc token với đúng tài khoản và hành động**, dùng qua TLS, hạn chế log, đặt thời gian hết hạn, xử lý một lần và chống đoán trực tuyến.

### 7.2. Mật khẩu khởi tạo cho người dùng

Không tạo password mặc định bằng cách ghép `Math.random()`, ngày sinh, username và mã khách hàng. Tốt hơn là **luồng kích hoạt/đặt mật khẩu bằng token ngẫu nhiên mật mã có TTL ngắn**, buộc người dùng chọn mật khẩu và lưu password verifier được hash đúng cách.

Nếu thực sự cần cấp secret khởi tạo, dùng CSPRNG và chính sách bàn giao an toàn; **không gửi password cố định cho nhiều người** hoặc đưa password vào log quản trị.

### 7.3. API key và secret dùng ký HMAC

Secret key của HMAC phải là byte có entropy phù hợp với thuật toán/chính sách. Đừng ghép thời gian với `Math.random()`, rồi dùng chuỗi đó làm `HmacSHA256` key. Bảo vệ API secret trong secret store/KMS/HSM theo khả năng, phân quyền chỉ bên ký/kiểm tra cần thiết và có kế hoạch rotation.

### 7.4. Nonce/IV của AEAD

Với **AES-GCM** và **ChaCha20-Poly1305 IETF**, lỗi then chốt là **mã hóa lại bằng cùng cặp (key, nonce)**, không chỉ là nonce “không đủ khó đoán”.

Nonce có thể **công khai và dự đoán được**, nếu thuật toán/giao thức cho phép và hệ thống **bảo đảm không trùng theo key**. Sinh nonce bằng `SecureRandom` là một chiến lược ngẫu nhiên, không phải chứng minh tính duy nhất tuyệt đối. Không dùng `Math.random()` làm nonce allocator; nhưng cũng không nghĩ rằng chỉ đổi sang `SecureRandom` là đã giải quyết mọi vấn đề nonce.

### 7.5. Salt của PBKDF2/Argon2id

Salt **không cần bí mật**; mục tiêu là đủ độc lập và thường ngẫu nhiên **cho mỗi verifier**. Sinh salt bằng `SecureRandom` hoặc API thư viện giúp tránh các giá trị lặp/có cấu trúc yếu. Tuy nhiên, **salt ngẫu nhiên không thay một thuật toán password hashing đủ chi phí**. `SHA-256(password + salt)` vẫn quá nhanh khi dùng trực tiếp để lưu verifier đăng nhập.

## 8. Unpredictability khác uniqueness và entropy

Ba thuật ngữ thường bị đánh đồng:

| Khái niệm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Unpredictability** | Attacker khó đoán secret trước khi được cấp | Bearer token, private key, HMAC key |
| **Uniqueness** | Không sử dụng lại giá trị trong phạm vi đã quy định | AEAD nonce theo mỗi khóa; transaction ID |
| **Entropy** | Mức bất định thực của nguồn sinh bí mật | Seed/DRBG cho key và token |

Một bộ đếm có thể **duy nhất nhưng dự đoán được**; phù hợp làm nonce trong giao thức cho phép, nhưng **không phù hợp làm bearer token**. Một chuỗi CSPRNG có thể **khó đoán nhưng vẫn có xác suất trùng**; phù hợp tạo secret khi độ dài và chính sách đủ mạnh, nhưng **không tự bảo đảm nonce không lặp** ở quy mô lớn.

### 8.1. Xác suất trùng nonce ngẫu nhiên

Giả sử các nonce 96 bit được sinh độc lập, đồng đều và `q` lần mã hóa diễn ra **dưới cùng một key**, xác suất có ít nhất một cặp trùng có xấp xỉ khi xác suất còn nhỏ:

\[
P(\text{collision}) \approx \frac{q(q-1)}{2^{97}}.
\]

Xác suất tăng xấp xỉ theo **bình phương số lần dùng khóa**. Vì vậy, yêu cầu an toàn phải kết hợp **nonce strategy, giới hạn lượng bản tin mỗi key, cryptoperiod và rotation**, không đơn thuần kiểm tra RNG có tên là `SecureRandom`.

### 8.2. Counter hoặc namespace trong hệ thống phân tán

Một chiến lược là phân vùng nonce bằng **namespace duy nhất cho từng node** cộng một **counter không lặp**. Cần:

- Cấp phát namespace không chồng lấn dưới cùng key.
- Ngăn counter reset sau restart, failover, rollback hoặc phục hồi snapshot.
- Không copy **cùng key + cùng counter/namespace** sang nhiều worker.
- Kiểm soát tràn counter và thay khóa theo chính sách.
- Đảm bảo định dạng nonce tương thích với chế độ mã hóa và thư viện đang dùng.

Trong TLS/SSH/IPsec, để **thư viện giao thức chuẩn** quản lý nonce/sequence number; đừng tự phát minh công thức nonce bên ngoài đặc tả.

## 9. SecureRandom, DRBG, provider và môi trường triển khai

### 9.1. SecureRandom là API, không phải phép màu

**DRBG (Deterministic Random Bit Generator)** sử dụng thuật toán và trạng thái nội bộ đã được khởi tạo bằng entropy để tạo ra byte khó dự đoán. `SecureRandom` có thể được cung cấp bởi những provider khác nhau, với các cơ chế tạo seed và reseed khác nhau.

~~~mermaid
flowchart TD
    OS[Nguồn entropy của hệ điều hành / thiết bị tin cậy] --> RNG[CSPRNG / DRBG của provider]
    RNG --> K[KeyGenerator / KeyPairGenerator]
    RNG --> T[Bearer token / OTP]
    RNG --> S[Salt / random nonce]
    K --> Lifecycle[Key lifecycle: dùng, rotation, thu hồi, hủy]
    T --> Lifecycle
    S --> Lifecycle
    IAM[IAM / KMS-HSM policy] --> Lifecycle
    Audit[Kiểm toán] --> Lifecycle
~~~

Để đạt mức bảo vệ mong muốn, cần JDK/OS được cập nhật, provider đáng tin, nguồn entropy đủ chất lượng và cơ chế vận hành khi RNG không sẵn sàng. Nếu có chính sách FIPS, phải xác minh **module mật mã và chế độ vận hành thực tế**, không chỉ dựa vào tên phương thức Java.

### 9.2. Snapshot, fork, container và autoscaling

Trong một số môi trường, việc sao chép trạng thái trước khi CSPRNG được reseed có thể tạo nguy cơ đầu ra trùng hoặc có tương quan, tùy provider và nền tảng. Rủi ro rõ hơn khi **khóa và counter nonce** cũng bị clone.

Không nên tự lấy timestamp để “phân biệt” các bản sao. Hãy dùng OS/JDK có cơ chế entropy phù hợp, kiểm tra hướng dẫn provider, đảm bảo quy trình khôi phục/reseed khi được yêu cầu và **tách miền nonce hoặc đổi khóa** trong những tình huống phục hồi có rủi ro.

### 9.3. Kiểm thử randomness

Việc thống kê thấy các giá trị phân bố đều **không chứng minh CSPRNG an toàn**. Một PRNG có thể vượt qua một số kiểm thử thống kê nhưng vẫn dễ dự đoán trạng thái. Với secret, dựa vào **thuật toán/provider được đánh giá, nguồn entropy, chính sách và kiểm thử tích hợp**.

Không viết test yêu cầu `SecureRandom` luôn tạo ra kết quả khác nhau tuyệt đối sau 100 lần gọi; đây không phải bảo đảm API. Thay vào đó, kiểm tra **độ dài, định dạng, đường xử lý lỗi, chính sách key/nonce, quyền truy cập và khả năng khôi phục**.

## 10. Liên hệ với KMS/HSM và vòng đời khóa

Trong hệ thống doanh nghiệp, **KMS/HSM** thường là nơi tạo hoặc bảo vệ các khóa có độ nhạy cao. Không phải lúc nào ứng dụng Java cũng cần trực tiếp tạo mọi DEK hay private key:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Java
    participant KMS as KMS / HSM
    participant DB as Kho dữ liệu
    App->>KMS: Xin sinh/bảo vệ DEK theo IAM policy
    KMS-->>App: Vật liệu DEK được phép + wrapped DEK
    App->>App: AEAD mã hóa dữ liệu với nonce đúng quy tắc
    App->>DB: Lưu ciphertext + nonce/tag + wrapped DEK
    DB-->>App: Trả payload mã hóa khi đọc
    App->>KMS: Unwrap DEK theo quyền
    KMS-->>App: DEK nếu policy cho phép
    App->>App: Xác minh AEAD tag và giải mã
~~~

Sơ đồ là **một kiến trúc envelope encryption điển hình**, không phải hợp đồng API chung của mọi KMS. Có dịch vụ cho phép tạo DEK và trả raw DEK tạm thời, dịch vụ khác yêu cầu mật mã diễn ra trong vùng HSM; một số hỗ trợ thuật toán hoặc key export khác nhau.

| Khâu | SecureRandom / Java | KMS/HSM / chính sách |
| --- | --- | --- |
| **Sinh** | `KeyGenerator`/`KeyPairGenerator` với CSPRNG hoặc gọi dịch vụ | Sinh bên trong ranh giới an toàn khi policy yêu cầu |
| **Cấp phát** | Chuyển khóa theo giao thức/SDK phù hợp | IAM cho đúng workload, tenant và purpose |
| **Lưu trữ** | Hạn chế raw key trong RAM/log/config | Bảo vệ KEK/private key, backup và quyền xuất |
| **Sử dụng** | Cipher/Signature/HMAC, nonce và AAD đúng | Quyền `Encrypt`, `Decrypt`, `Sign`, audit |
| **Xoay vòng** | Cập nhật key ID/version và nonce scope | Chính sách cryptoperiod, rewrap/re-encrypt khi cần |
| **Thu hồi/hủy** | Ngừng sử dụng key/token, xử lý cache/phiên | Thu hồi quyền và hủy theo retention/backup policy |
| **Kiểm toán** | Event ID, version, verdict; không log secret | Theo dõi sử dụng khóa và thay đổi policy |

Một khóa AES tạo bằng `SecureRandom` đúng cách **vẫn có thể bị lộ** nếu ứng dụng hard-code vào file cấu hình, in vào trace hoặc cấp quyền `Decrypt` quá rộng. Ngược lại, HSM/KMS **không sửa được một key yếu đã bị tạo từ `Math.random()`**. Bảo vệ cần đủ cả nguồn randomness **và** vòng đời khóa.

## 11. Tình huống thực tế: dịch vụ đặt lại mật khẩu

Một nền tảng có hàng triệu người dùng cho phép gửi email đặt lại mật khẩu. Nhóm phát triển phát hiện một hàm cũ sử dụng:

~~~java
// Mẫu sai để minh họa; không giữ trong production.
String resetToken = Long.toString((long) (Math.random() * Long.MAX_VALUE));
~~~

**Phương án cải thiện:**

1. Đổi sang token ngẫu nhiên từ **32 byte `SecureRandom`** và encode Base64url.
2. Sinh token mới **cho từng lần yêu cầu**, ràng buộc với `accountId`, mục đích `RESET_PASSWORD`, thời gian hết hạn và định danh request.
3. Chỉ gửi token đến kênh khôi phục đã được xác minh; không tiết lộ tài khoản có tồn tại hay không qua thông báo công khai.
4. Lưu **digest của token có entropy cao** và metadata, giới hạn quyền đọc bảng token. Không ghi raw token vào log, analytics hoặc URL history không được kiểm soát.
5. Khi người dùng đưa token trở lại, kiểm tra digest, mục đích, tài khoản, TTL, trạng thái **chưa dùng**, số lần thử và chính sách bảo mật; đánh dấu đã dùng theo thao tác nguyên tử để tránh race condition.
6. Cho người dùng đặt mật khẩu mới, lưu **Argon2id/PBKDF2/bcrypt/scrypt verifier** theo chính sách và salt riêng; cân nhắc thu hồi phiên đăng nhập cũ.
7. Theo dõi số lượng yêu cầu reset, kết quả, sự kiện bất thường; bảo vệ log và cơ chế gửi email trước abuse.

**Nếu token cũ có khả năng bị dự đoán**, chỉ sửa hàm sinh mới là chưa đủ: cần xem có token đang còn hiệu lực hay không, cân nhắc vô hiệu hóa token cũ và điều tra các lần reset bất thường. Đây là một **sự cố liên quan secret lifecycle**, không phải lỗi định dạng số ngẫu nhiên đơn thuần.

### Vì sao một bước “SHA-256 trên Math.random” không phải bản vá?

Hashing không làm tăng entropy. Nếu số trạng thái đầu vào dễ đoán, attacker vẫn có thể băm những ứng viên tương tự để thử. **Bản vá đúng là thay nguồn sinh secret bằng CSPRNG** và kiểm tra lại độ dài, luồng xác thực, quyền và thời hạn.

## 12. Những lỗi thường gặp

| Sai lầm | Rủi ro | Cách xử lý đúng |
| --- | --- | --- |
| Dùng `Math.random()` tạo reset token/API secret | Không có bảo đảm khó dự đoán | `SecureRandom.nextBytes()` đủ độ dài và TTL/scope |
| Ghép timestamp, PID, username rồi hash SHA-256 | Không tạo entropy thật từ dữ liệu dễ đoán | Dùng nguồn entropy tin cậy qua CSPRNG |
| Dùng `Random` cho khóa AES-256 | Key byte dài nhưng độ khó đoán không được bảo đảm | `KeyGenerator`/KMS/HSM phù hợp |
| Cho rằng SecureRandom luôn tạo giá trị duy nhất | Nonce/token vẫn có thể trùng về mặt xác suất | Thiết kế uniqueness theo key và kiểm tra collision khi cần |
| Dùng lại nonce AES-GCM dưới cùng key | Có thể phá bí mật và xác thực | Nonce allocator, limit per key, rotation |
| Sinh salt chung cho mọi mật khẩu | Mất lợi ích tách verifier, dễ tính bảng dùng chung | Salt ngẫu nhiên riêng mỗi verifier |
| Dùng OTP 6 chữ số nhưng không giới hạn thử | Dễ brute-force trực tuyến | TTL, rate limit, dùng một lần, ràng buộc giao dịch |
| Lấy đầu ra Base64 dài và kết luận 256 bit entropy | Nhầm độ dài biểu diễn với bảo mật | Chỉ đếm entropy dựa trên nguồn và số byte được sinh |
| Fallback từ SecureRandom sang Math.random khi lỗi | Bypass bảo mật khó phát hiện | Fail closed và xử lý lỗi provider |
| Dùng `getInstanceStrong()` mọi request mà không đo | Có thể tăng latency/chờ nguồn entropy | Chọn RNG theo provider và chính sách đã benchmark |
| Seed cố định trong production để tái hiện bug | Có thể tạo bí mật lặp/dễ dự đoán | Deterministic fake RNG chỉ trong môi trường test |
| Clone VM với key + counter nonce giống nhau | Các node tái sử dụng cùng (key, nonce) | Tách namespace, reseed/rotate khi cần, kiểm thử restore |
| Ghi key, reset token, plaintext vào log | Secret lộ dù RNG tốt | Log metadata tối thiểu, kiểm soát trace/dump |
| KMS sinh key tốt nhưng IAM cấp Decrypt quá rộng | Người không được phép vẫn giải mã | Least privilege, tách quyền và audit |

## 13. Checklist cho kỹ sư Java và bảo mật

- [ ] Tất cả nơi sinh **key, token, salt, nonce, OTP** đã được rà soát để loại `Math.random()`, `Random`, `ThreadLocalRandom` khỏi secret path?
- [ ] Dùng `SecureRandom`/`KeyGenerator`/`KeyPairGenerator` hoặc API KMS/HSM đúng thuật toán?
- [ ] Provider/JDK/OS có chính sách entropy, reseed và bảo trì phù hợp môi trường?
- [ ] Không dùng timestamp, PID, hostname hoặc seed cố định làm nguồn bí mật?
- [ ] Token bearer có đủ entropy, scope, TTL, one-time semantics khi cần và cơ chế thu hồi?
- [ ] OTP ngắn có giới hạn số lần thử, hết hạn, ràng buộc tài khoản và chống phát lại?
- [ ] Password dùng thuật toán hashing chuyên dụng với salt riêng, không chỉ SHA-256/password?
- [ ] AES-GCM/ChaCha20-Poly1305 có chiến lược **không trùng (key, nonce)** tại mọi node/instance?
- [ ] Nếu random nonce, đã đánh giá collision bound và giới hạn bản tin mỗi key?
- [ ] Nếu counter nonce, đã kiểm thử restart, autoscaling, failover và snapshot rollback?
- [ ] Không lưu raw key, token, password, pepper, DEK hoặc plaintext vào log, config hay trace?
- [ ] KMS/HSM phân quyền theo workload và purpose, audit thao tác nhạy cảm, có kế hoạch rotation/retention/hủy?
- [ ] Dữ liệu đã mã hóa có metadata key ID/version, khả năng rewrap/re-encrypt và khôi phục khi rotation?
- [ ] Có quy trình khi CSPRNG/provider không hoạt động, **không tự downgrade sang RNG yếu**?
- [ ] Đã kiểm tra tests về định dạng, độ dài, khả năng xử lý lỗi và quyền, thay vì coi thống kê ngẫu nhiên là đủ?

## 14. Câu hỏi tự kiểm tra

**1. Vì sao `Math.random()` không dùng cho sinh khóa dù nó tạo ra số khác nhau mỗi lần?**  
Vì khác nhau không đồng nghĩa **khó dự đoán với đối thủ**. API không cam kết tính an toàn của CSPRNG.

**2. Hash kết quả `Math.random()` bằng SHA-256 có biến nó thành token 256-bit an toàn không?**  
Không. Hash không tạo entropy mới từ nguồn dễ đoán; độ dài digest không xác định độ mạnh bí mật.

**3. Có phải `SecureRandom` luôn bảo đảm nonce không trùng không?**  
Không. Với nonce ngẫu nhiên vẫn có xác suất va chạm. AES-GCM/ChaCha20-Poly1305 cần quy tắc duy nhất theo key.

**4. Vì sao mã OTP 6 chữ số không đủ thay thế bearer token 256-bit dù tạo bằng CSPRNG?**  
Vì chỉ có một triệu khả năng, xấp xỉ 20 bit. Cần TTL, giới hạn thử và dùng một lần; bearer token có thể có entropy lớn hơn rất nhiều.

**5. Salt trong PBKDF2 có phải secret và phải lưu trong HSM không?**  
Không. Salt thường được lưu cùng verifier. Nếu dùng pepper, đó mới là một bí mật cần quản lý tách biệt.

**6. `SecureRandom.getInstanceStrong()` có luôn là lựa chọn nhanh nhất và tốt nhất không?**  
Không. Nó phụ thuộc danh sách strong algorithms, provider và nguồn entropy; có thể có chi phí hoặc block nên cần đánh giá trên môi trường thực.

**7. Nếu KMS đã lưu key, có thể sinh key từ `Math.random()` rồi gửi vào KMS không?**  
Không nên. KMS không tạo lại entropy đã thiếu trong key nguồn. Hãy sinh key an toàn từ JDK/provider hoặc để KMS/HSM sinh theo policy.

**8. Nếu reset token cũ sinh yếu vẫn còn hiệu lực, chỉ sửa generator mới đã đủ chưa?**  
Chưa. Cần đánh giá và có thể vô hiệu hóa token cũ, rà soát log/sự kiện bất thường và quy trình ứng phó.

## Ghi nhớ

**Không dùng `Math.random()` cho security vì API không bảo đảm tạo đầu ra khó dự đoán trước kẻ tấn công.** Để tạo key, session secret, reset token, API key, salt hoặc giá trị mật mã khác trong Java, dùng **`SecureRandom`/API tạo khóa hoặc KMS/HSM được cấu hình phù hợp**, không tự ghép timestamp rồi hash. Nhưng CSPRNG **không tự giải quyết tính duy nhất của nonce, chống replay, phân quyền, lưu giữ và thu hồi**. Một thiết kế hoàn chỉnh phải kết hợp randomness tốt với **AEAD/KDF đúng mục đích, key lifecycle, envelope encryption, IAM, cryptoperiod, rotation, kiểm toán và kế hoạch xử lý sự cố**.
