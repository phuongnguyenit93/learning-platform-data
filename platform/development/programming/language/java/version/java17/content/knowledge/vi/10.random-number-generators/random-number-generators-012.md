# Phân biệt PRNG mô phỏng với SecureRandom cho mục đích bảo mật (Java 17)

Java cung cấp nhiều cách sinh số giả ngẫu nhiên: `Random`, `SplittableRandom`, `ThreadLocalRandom` và các thuật toán qua `RandomGeneratorFactory`. Chúng hữu ích cho mô phỏng, kiểm thử, trò chơi hoặc chọn mẫu. Tuy nhiên, khi cần tạo token đặt lại mật khẩu, mã xác thực, nonce hoặc khóa mã hóa, yêu cầu quan trọng nhất là **kẻ tấn công không thể dự đoán giá trị tiếp theo**.

Đó là lý do Java có `SecureRandom`. Cả PRNG mô phỏng lẫn `SecureRandom` đều có thể sử dụng thuật toán xác định bên trong, nhưng chúng được thiết kế và khởi tạo cho **mục tiêu khác nhau**:

- PRNG mô phỏng ưu tiên tốc độ, tính tái lập và đặc tính thống kê phù hợp cho tính toán.
- `SecureRandom` hướng tới khả năng chống dự đoán trước đối thủ, dựa vào entropy và cơ chế bảo mật của provider.

Không nên chọn bộ sinh chỉ vì tên có chữ “random”. Hãy xác định trước dữ liệu đó có cần tái lập hay cần khó dự đoán, rồi chọn API phù hợp.

## 1. Phân biệt theo mục đích sử dụng

| Tiêu chí | PRNG mô phỏng | `SecureRandom` |
| --- | --- | --- |
| Mục tiêu | Sinh dãy số có đặc tính thống kê phù hợp, thường nhanh và tái lập được | Sinh giá trị khó dự đoán trong bối cảnh bảo mật |
| Seed | Có thể đặt seed cố định để lặp lại kết quả | Được khởi tạo và quản lý bằng nguồn entropy phù hợp; không tự đặt seed dễ đoán |
| Tái lập | Là tính năng hữu ích cho test và mô phỏng | Không nên thiết kế để tái tạo token/secret bằng seed công khai hoặc cố định |
| Trạng thái nội bộ | Nếu biết thuật toán và state có thể dự đoán dãy tiếp theo | Được thiết kế để hạn chế khả năng dự đoán state/output trước đối thủ |
| Hiệu năng | Thường rất nhanh; một số loại tối ưu cho song song | Có chi phí bảo mật và provider riêng; hiệu năng tùy implementation |
| Ví dụ API | `Random`, `SplittableRandom`, `ThreadLocalRandom`, `RandomGenerator` | `SecureRandom` |
| Dùng cho | Mô phỏng, test, sampling, game không liên quan đến bí mật | Token, nonce khó đoán, salt ngẫu nhiên, khóa và dữ liệu bảo mật |

**Quy tắc thực tế:** nếu giá trị được dùng để cấp quyền, xác thực danh tính, bảo vệ phiên đăng nhập hoặc giữ bí mật, hãy dùng `SecureRandom` hoặc API mật mã cấp cao được thiết kế cho mục đích đó. Không dùng `Random` hay `Math.random()` cho các mục đích này.

## 2. PRNG mô phỏng: xác định và tái lập

PRNG (*Pseudo-Random Number Generator*) tạo dãy giá trị từ trạng thái nội bộ bằng thuật toán xác định. Mô hình khái quát:

\[
S_{n+1}=f(S_n), \qquad X_n=g(S_n)
\]

Trong đó `S` là state, `f` là quy tắc cập nhật trạng thái, `g` tạo giá trị đầu ra `X`. Seed khởi tạo trạng thái ban đầu.

Với cùng thuật toán, cùng seed và cùng trình tự gọi, PRNG mô phỏng có thể tạo lại cùng dãy. Đây là ưu điểm lớn trong kiểm thử:

```java
import java.util.Random;

public class SimulationDemo {
    static int[] simulate(long seed, int count) {
        Random random = new Random(seed);
        int[] results = new int[count];

        for (int i = 0; i < count; i++) {
            results[i] = random.nextInt(6) + 1;
        }
        return results;
    }

    public static void main(String[] args) {
        int[] first = simulate(2026L, 10);
        int[] second = simulate(2026L, 10);

        System.out.println(java.util.Arrays.toString(first));
        System.out.println(java.util.Arrays.equals(first, second));
    }
}
```

Hai lần mô phỏng khởi tạo `Random` với seed `2026` và thực hiện cùng trình tự gọi. Vì vậy, chúng tạo cùng kết quả. Khi phát hiện lỗi trong một lần chạy, bạn có thể lưu seed để tái hiện kịch bản.

### 2.1. Vì sao tính tái lập không phù hợp với token bảo mật?

Giả sử ứng dụng tạo mã đặt lại mật khẩu bằng:

```java
Random random = new Random(12345L);
int resetCode = random.nextInt(1_000_000);
```

Mọi lần khởi động ứng dụng với seed cố định có thể tạo lại cùng dãy. Người biết seed, thuật toán và số lần gọi có thể tính trước mã tiếp theo.

Ngay cả khi seed được lấy từ thời gian:

```java
Random random = new Random(System.currentTimeMillis());
```

thời gian khởi tạo thường nằm trong một khoảng có thể suy đoán. Nếu kẻ tấn công biết khoảng thời gian token được tạo, họ có thể thử các seed khả dĩ. Seed dựa trên ID người dùng, số thứ tự, timestamp hoặc dữ liệu công khai cũng không tạo ra bí mật.

Một PRNG có thể vượt qua một số kiểm tra thống kê nhưng vẫn dễ dự đoán. **Chất lượng thống kê và tính an toàn mật mã là hai thuộc tính khác nhau.**

### 2.2. Các API phổ thông không phải CSPRNG

- `Random` là PRNG truyền thống, phù hợp cho nhiều bài toán phổ thông và test có seed.
- `SplittableRandom` hỗ trợ chia tách generator cho mô phỏng hoặc xử lý song song; nó không được thiết kế để chống dự đoán.
- `ThreadLocalRandom` giảm tranh chấp khi nhiều thread cần số giả ngẫu nhiên; gắn với thread không làm nó trở thành bộ sinh bảo mật.
- `Math.random()` cung cấp số giả ngẫu nhiên tiện dụng, không phải API để tạo bí mật.
- `RandomGenerator` trong Java 17 là interface chung cho nhiều generator. Việc một đối tượng có kiểu `RandomGenerator` **không tự chứng minh** rằng thuật toán phía sau an toàn mật mã.

## 3. SecureRandom: bộ sinh số ngẫu nhiên cho bảo mật

`java.security.SecureRandom` là API Java dùng để tạo dữ liệu giả ngẫu nhiên có đặc tính phù hợp cho các ứng dụng bảo mật. Nó thường được mô tả là bộ sinh số giả ngẫu nhiên mật mã (*Cryptographically Secure Pseudo-Random Number Generator — CSPRNG*).

Một CSPRNG vẫn có trạng thái và thuật toán xác định. Điểm khác biệt là thiết kế nhằm làm cho đầu ra khó dự đoán nếu đối thủ không biết state bí mật, đồng thời có cơ chế khởi tạo/cập nhật state dựa trên entropy phù hợp.

Nguồn entropy có thể đến từ hệ điều hành hoặc provider mật mã. Cách thu thập, lưu state, reseed và thuật toán cụ thể phụ thuộc implementation. Ứng dụng thông thường nên dùng API chuẩn và để provider quản lý cơ chế này, thay vì tự viết thuật toán hoặc tự tạo seed.

### 3.1. Tạo SecureRandom theo cách thông dụng

```java
import java.security.SecureRandom;

public class SecureRandomDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();

        byte[] randomBytes = new byte[16];
        secureRandom.nextBytes(randomBytes);

        for (byte value : randomBytes) {
            System.out.printf("%02x", value & 0xff);
        }
        System.out.println();
    }
}
```

`new SecureRandom()` yêu cầu provider mặc định cung cấp một bộ sinh bảo mật. Bộ sinh được tự khởi tạo theo cơ chế của implementation. Với ứng dụng thông thường, đây là điểm bắt đầu phù hợp.

Không nên tự viết một PRNG, tự lấy thời gian làm seed hoặc đặt một seed cố định cho `SecureRandom` rồi cho rằng kết quả sẽ an toàn hơn.

### 3.2. Không cần tự seed bằng dữ liệu dễ đoán

Tránh:

```java
SecureRandom random = new SecureRandom();
random.setSeed(System.currentTimeMillis()); // Không làm nguồn entropy trở nên an toàn.
```

`setSeed` không phải cách “bật chế độ bảo mật”. Với `SecureRandom`, lời gọi này bổ sung dữ liệu seed vào trạng thái theo quy tắc implementation; nó không biến một giá trị thời gian dễ đoán thành entropy bí mật. Nếu gọi trước khi bộ sinh tự khởi tạo, việc tự cung cấp seed yếu có thể ảnh hưởng đến mức an toàn tùy implementation.

Trong ứng dụng bình thường:

- Để provider tự khởi tạo `SecureRandom`.
- Không seed bằng timestamp, counter, ID người dùng hoặc chuỗi cố định.
- Không công khai state hay dữ liệu seed bí mật.
- Không tự tái sử dụng cùng một seed cố định giữa các môi trường.

Nếu một hệ thống có yêu cầu quản lý entropy đặc biệt, cần thiết kế theo hướng dẫn của provider và nền tảng triển khai, không suy diễn từ ví dụ PRNG mô phỏng.

## 4. Tạo token khó đoán bằng SecureRandom

Token đặt lại mật khẩu, token xác thực hoặc khóa phiên cần có đủ độ dài và không thể đoán thực tế. Một cách thông dụng là sinh byte ngẫu nhiên rồi mã hóa thành chuỗi an toàn cho URL.

```java
import java.security.SecureRandom;
import java.util.Base64;

public class TokenGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String createToken() {
        byte[] bytes = new byte[32]; // 32 byte = 256 bit
        RANDOM.nextBytes(bytes);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static void main(String[] args) {
        System.out.println(createToken());
    }
}
```

Ở đây:

1. `nextBytes` điền các byte bằng dữ liệu từ `SecureRandom`.
2. 32 byte tương ứng 256 bit dữ liệu ngẫu nhiên trước khi mã hóa.
3. Base64 URL-safe chuyển byte thành chuỗi có thể dùng trong URL mà không chứa các ký tự dấu `+` hoặc `/`.
4. `withoutPadding()` bỏ phần padding ở cuối chuỗi.

Mã hóa Base64 **không tăng entropy**; nó chỉ đổi cách biểu diễn. Mức khó đoán đến từ byte được sinh ra, độ dài token và chất lượng của nguồn ngẫu nhiên.

### 4.1. Token cần được quản lý đúng vòng đời

Một token đủ ngẫu nhiên vẫn có thể bị lạm dụng nếu ứng dụng quản lý sai. Với token xác thực hoặc đặt lại mật khẩu, thường cần:

- Hết hạn sau khoảng thời gian ngắn phù hợp với nghiệp vụ.
- Chỉ dùng một lần và vô hiệu hóa sau khi sử dụng.
- Gắn với đúng tài khoản, mục đích và phiên giao dịch.
- Không ghi token đầy đủ vào log, URL analytics hoặc thông báo lỗi.
- Giới hạn số lần thử và tốc độ yêu cầu.
- Truyền qua kênh bảo mật như HTTPS.
- Khi lưu ở server, cân nhắc chỉ lưu hash của token để giảm tác động nếu cơ sở dữ liệu bị lộ.

`SecureRandom` giải quyết phần **tạo giá trị khó đoán**. Nó không thay thế kiểm soát truy cập, hết hạn, rate limit hoặc bảo vệ nơi lưu token.

## 5. Sinh số nguyên trong khoảng mà không gây modulo bias

Một lỗi phổ biến là lấy số ngẫu nhiên rồi dùng toán tử modulo:

```java
int code = random.nextInt() % 1_000_000;
```

Cách này có hai vấn đề:

1. Kết quả có thể âm.
2. Nếu số lượng giá trị đầu vào không chia hết cho bound, các phần dư không có xác suất bằng nhau (*modulo bias*).

Với `SecureRandom`, dùng phương thức có bound:

```java
SecureRandom random = new SecureRandom();

int value = random.nextInt(1_000_000); // 0 đến 999999
```

API giới hạn của generator thực hiện việc chọn giá trị theo cách tránh modulo bias thông thường. Nếu muốn tạo mã 6 chữ số:

```java
import java.security.SecureRandom;
import java.util.Locale;

public class OtpGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    static String createOtp() {
        int value = RANDOM.nextInt(1_000_000);
        return String.format(Locale.ROOT, "%06d", value);
    }
}
```

Định dạng `%06d` giữ các số 0 ở đầu để mã luôn có sáu chữ số.

**Mã OTP sáu chữ số chỉ có một triệu khả năng**, tương đương chưa đến 20 bit entropy. Dù dùng `SecureRandom`, nó vẫn cần thời hạn ngắn, giới hạn số lần thử, chống dò hàng loạt và gắn với đúng giao dịch/tài khoản. Với yêu cầu bảo mật cao hơn, cần chọn độ dài và quy trình xác thực theo mô hình đe dọa.

## 6. SecureRandom dùng cho salt, nonce và khóa

Các mục đích mật mã khác nhau có yêu cầu khác nhau. `SecureRandom` có thể cung cấp byte ngẫu nhiên, nhưng việc sử dụng đúng còn phụ thuộc giao thức hoặc thuật toán mật mã.

### 6.1. Salt cho lưu trữ mật khẩu

Salt là dữ liệu ngẫu nhiên riêng cho mỗi mật khẩu được băm. Salt thường không cần bí mật, nhưng cần đủ duy nhất và được tạo bằng nguồn ngẫu nhiên phù hợp:

```java
import java.security.SecureRandom;
import java.util.HexFormat;

public class SaltDemo {
    public static void main(String[] args) {
        SecureRandom random = new SecureRandom();
        byte[] salt = new byte[16];
        random.nextBytes(salt);

        System.out.println(HexFormat.of().formatHex(salt));
    }
}
```

Đoạn code chỉ tạo salt. Trong hệ thống xác thực thật:

- Không lưu mật khẩu dạng rõ hoặc chỉ hash bằng SHA-256 thông thường.
- Dùng password hashing/KDF chuyên dụng có salt, cost/work factor và cấu hình phù hợp, chẳng hạn PBKDF2, scrypt, bcrypt hoặc Argon2 theo tiêu chuẩn và thư viện được lựa chọn.
- Lưu salt cùng dữ liệu hash và tham số cần thiết để xác minh.
- Không tái sử dụng cùng một salt cho mọi người dùng.

`SecureRandom` tạo nguồn byte phù hợp; nó không tự thực hiện password hashing.

### 6.2. Nonce

Nonce là giá trị dùng một lần (*number used once*) trong một giao thức. Một số giao thức yêu cầu nonce khó đoán; một số yêu cầu nonce chỉ cần **không lặp lại** trong phạm vi khóa hoặc phiên.

Nếu đặc tả yêu cầu nonce ngẫu nhiên/khó đoán, có thể tạo byte bằng `SecureRandom`. Nếu đặc tả chỉ yêu cầu tính duy nhất, phải bảo đảm uniqueness theo cách giao thức quy định; không mặc định một giá trị random là đủ để ngăn trùng lặp tuyệt đối.

Với các chế độ mã hóa như GCM, nonce/IV phải tuân thủ yêu cầu của thuật toán và không được tái sử dụng dưới cùng một khóa theo quy tắc của chế độ đó. Hãy theo hướng dẫn của API mật mã và giao thức, không tự đặt kích thước hoặc cách tạo nonce chỉ theo ví dụ chung.

### 6.3. Tạo khóa bằng KeyGenerator

Khi tạo khóa đối xứng, nên dùng API cấp cao `KeyGenerator` thay vì tự cắt byte và tự gán ý nghĩa cho khóa:

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public class AesKeyDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(256, random);

        SecretKey key = keyGenerator.generateKey();
        System.out.println(key.getAlgorithm());
        System.out.println(key.getEncoded().length * 8);
    }
}
```

Ví dụ yêu cầu khóa AES 256 bit. Thuật toán, kích thước khóa và provider cần phù hợp với chính sách mật mã và môi trường triển khai. Trong ứng dụng thực tế, không in hoặc ghi byte khóa ra log; quản lý khóa bằng hệ thống quản lý bí mật/KMS phù hợp.

## 7. Provider và thuật toán của SecureRandom

`SecureRandom` là API, còn thuật toán cụ thể do **provider** cung cấp. Provider là thành phần triển khai dịch vụ bảo mật trong kiến trúc Java Cryptography Architecture (JCA).

Có thể xem thông tin implementation:

```java
import java.security.SecureRandom;

public class SecureRandomInfo {
    public static void main(String[] args) {
        SecureRandom random = new SecureRandom();

        System.out.println("Algorithm: " + random.getAlgorithm());
        System.out.println("Provider: " + random.getProvider().getName());
        System.out.println("Parameters: " + random.getParameters());
    }
}
```

Tên thuật toán và provider thực tế phụ thuộc JDK, cấu hình bảo mật, hệ điều hành và provider được cài đặt. Vì vậy, không nên hard-code giả định rằng mọi máy Java 17 đều dùng cùng một thuật toán mặc định.

### 7.1. Chọn thuật toán tường minh khi có yêu cầu triển khai

Nếu ứng dụng cần chọn một thuật toán được provider hỗ trợ, có thể yêu cầu bằng tên:

```java
import java.security.SecureRandom;

public class NamedSecureRandom {
    public static void main(String[] args) throws Exception {
        SecureRandom random = SecureRandom.getInstance("DRBG");
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
    }
}
```

`DRBG` là một họ *Deterministic Random Bit Generator* được chuẩn hóa cho mục đích mật mã. Java có hỗ trợ API tham số DRBG từ các phiên bản hiện đại; JDK 17 cung cấp triển khai DRBG trong provider chuẩn phổ biến. Tuy nhiên, việc thuật toán có sẵn và các tham số hỗ trợ vẫn phụ thuộc provider/runtime cụ thể. Nếu chọn tên tường minh, cần kiểm tra trên đúng môi trường triển khai và xử lý `NoSuchAlgorithmException`.

Với nhu cầu phổ thông, `new SecureRandom()` thường đơn giản hơn và để JCA chọn implementation mặc định.

### 7.2. getInstanceStrong() không phải lựa chọn mặc định cho mọi ứng dụng

Java cung cấp:

```java
SecureRandom random = SecureRandom.getInstanceStrong();
```

Phương thức này chọn implementation được cấu hình là mạnh theo thuộc tính bảo mật `securerandom.strongAlgorithms`. Tùy provider và nguồn entropy, việc khởi tạo hoặc sinh dữ liệu có thể có đặc tính hiệu năng/blocking khác với `new SecureRandom()`.

Không nên suy luận rằng `getInstanceStrong()` luôn cần thiết hoặc luôn nhanh/an toàn hơn implementation mặc định trong mọi tình huống. Hãy dùng khi có yêu cầu cụ thể, kiểm tra cấu hình provider và đo đặc tính vận hành trong môi trường thực tế. Với đa số ứng dụng, `new SecureRandom()` là lựa chọn phù hợp.

## 8. Quan hệ giữa SecureRandom và RandomGenerator trong Java 17

Java 17 bổ sung gói `java.util.random` với interface `RandomGenerator` và factory cho các thuật toán PRNG. `Random` triển khai `RandomGenerator`; `SecureRandom` kế thừa `Random`, vì vậy cũng có thể được sử dụng qua API chung đó.

Điều này **không có nghĩa mọi RandomGenerator đều an toàn mật mã**.

Ví dụ một hàm mô phỏng:

```java
import java.util.random.RandomGenerator;

static int rollDice(RandomGenerator random) {
    return random.nextInt(6) + 1;
}
```

Hàm này chỉ cần một nguồn số giả ngẫu nhiên. Có thể truyền generator mô phỏng có seed cố định để kiểm thử.

Nhưng với một hàm tạo token bảo mật, nên thể hiện yêu cầu bằng kiểu cụ thể:

```java
import java.security.SecureRandom;
import java.util.Base64;

static String createResetToken(SecureRandom secureRandom) {
    byte[] bytes = new byte[32];
    secureRandom.nextBytes(bytes);
    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
}
```

Việc nhận `SecureRandom` làm rõ ý định của API và hạn chế việc vô tình truyền một PRNG mô phỏng. Với hệ thống lớn, có thể định nghĩa một abstraction riêng như `SecureTokenGenerator` để kiểm soát rõ ràng nguồn token.

## 9. Thread safety và chia sẻ SecureRandom

`SecureRandom` được thiết kế để có thể dùng an toàn từ nhiều thread. Tuy nhiên, trong ứng dụng có tải cao, đặc tính hiệu năng phụ thuộc provider và cách đồng bộ nội bộ.

Một cách đơn giản là giữ một instance được quản lý trong vòng đời ứng dụng:

```java
public final class SecurityRandoms {
    private static final SecureRandom INSTANCE = new SecureRandom();

    private SecurityRandoms() {
    }

    public static SecureRandom get() {
        return INSTANCE;
    }
}
```

Không cần tạo một `SecureRandom` mới cho mỗi byte hoặc mỗi request nếu không có lý do rõ ràng. Tạo lại liên tục có thể làm tăng chi phí khởi tạo và tương tác với nguồn entropy/provider.

Nếu cần tối ưu trong môi trường nhiều thread, hãy đo hiệu năng và tuân theo tài liệu provider. Không tự chuyển sang `Random` hoặc `ThreadLocalRandom` chỉ vì chúng nhanh hơn; làm vậy có thể phá vỡ yêu cầu bảo mật.

Với PRNG mô phỏng, `SplittableRandom` có thể được chia tách để mỗi tác vụ dùng một instance riêng. Quy tắc đó là để quản lý state và hiệu năng; không thay thế `SecureRandom` trong mục tiêu chống dự đoán.

## 10. Kiểm thử code bảo mật mà vẫn kiểm soát được kết quả

Một điểm khác biệt trong thiết kế test:

- Với mô phỏng, dùng seed cố định là cách tốt để tạo kết quả ổn định.
- Với token bảo mật, không nên cố định seed của `SecureRandom` trong production hoặc hạ cấp sang `Random` chỉ để test dễ lặp lại.

Bạn có thể tách **logic xử lý token** khỏi **nguồn sinh token**:

```java
import java.security.SecureRandom;
import java.util.Base64;

public class ResetTokenService {
    private final SecureRandom random;

    public ResetTokenService(SecureRandom random) {
        this.random = random;
    }

    public String createToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
```

Trong kiểm thử, có thể kiểm tra các thuộc tính không phụ thuộc vào một chuỗi token cụ thể:

- Token có định dạng URL-safe.
- Độ dài byte ngẫu nhiên được yêu cầu.
- Token được gắn với đúng tài khoản và thời hạn.
- Token dùng một lần và bị vô hiệu hóa sau khi sử dụng.
- Các đường đi lỗi và giới hạn số lần thử hoạt động đúng.

Không cần assert rằng lần chạy nào cũng tạo ra một chuỗi token cố định. Với phần logic thuần cần kết quả xác định, hãy tách nó thành hàm riêng và kiểm thử độc lập.

## 11. Những sai lầm cần tránh

**Dùng `Random` để tạo reset token hoặc session ID.**  
`Random` phục vụ mục đích giả ngẫu nhiên phổ thông, không chống dự đoán mật mã. Dùng `SecureRandom`.

**Seed `Random` bằng timestamp rồi coi là bí mật.**  
Thời gian và các dữ liệu công khai có thể được đoán trong một khoảng. Seed không tự tạo entropy.

**Gọi `setSeed` với một số cố định trên SecureRandom.**  
Không làm generator mạnh hơn. Việc bổ sung seed yếu có thể làm sai giả định bảo mật của ứng dụng.

**Dùng `random.nextInt() % bound` để tạo OTP.**  
Có thể tạo giá trị âm và phân phối lệch. Dùng `nextInt(bound)`.

**Cho rằng tên interface `RandomGenerator` đồng nghĩa an toàn mật mã.**  
Interface chỉ chuẩn hóa cách gọi; phải biết implementation cụ thể và mục đích thiết kế.

**Cho rằng token Base64 dài thì chắc chắn an toàn.**  
Base64 chỉ mã hóa biểu diễn. Entropy đến từ byte gốc, thuật toán và độ dài nguồn ngẫu nhiên.

**Dùng một OTP sáu chữ số mà không giới hạn số lần thử.**  
Không gian một triệu giá trị có thể bị dò nếu không có rate limit, hết hạn và kiểm soát dùng một lần.

**Tự sinh khóa bằng `Random` rồi dùng trong thuật toán mã hóa.**  
Dùng `KeyGenerator` hoặc API quản lý khóa thích hợp, dựa trên nguồn ngẫu nhiên bảo mật.

**Coi nonce ngẫu nhiên luôn bảo đảm không trùng.**  
Ngẫu nhiên không đồng nghĩa uniqueness tuyệt đối. Tuân thủ yêu cầu nonce/IV của giao thức và thuật toán.

## 12. Bảng quyết định nhanh

| Câu hỏi | Lựa chọn |
| --- | --- |
| Cần cùng kết quả mỗi lần chạy test mô phỏng? | PRNG với seed cố định, ví dụ `Random(seed)` hoặc generator xác định qua factory. |
| Cần sinh dữ liệu ngẫu nhiên cho benchmark/sampling? | PRNG phù hợp với yêu cầu thống kê và hiệu năng. |
| Cần tạo token reset mật khẩu hoặc session secret? | `SecureRandom`. |
| Cần tạo nonce hoặc salt bằng byte ngẫu nhiên? | `SecureRandom`, đồng thời tuân thủ quy tắc của giao thức/KDF. |
| Cần tạo khóa AES? | `KeyGenerator` với nguồn `SecureRandom` hoặc API quản lý khóa phù hợp. |
| Cần số giả ngẫu nhiên trong ứng dụng nhiều thread? | `ThreadLocalRandom` hoặc generator được chia tách, nếu không phải dữ liệu bảo mật. |
| Cần chọn thuật toán PRNG bằng cấu hình trên Java 17? | `RandomGeneratorFactory`; xác nhận implementation có trên runtime đích. |

## 13. Câu hỏi tự kiểm tra

**1. Vì sao PRNG mô phỏng có thể tái lập kết quả?**  
Vì thuật toán xác định trạng thái tiếp theo từ state hiện tại; cùng seed và cùng trình tự lời gọi tạo lại cùng dãy.

**2. Một PRNG có phân phối thống kê tốt có chắc an toàn mật mã không?**  
Không. Chất lượng thống kê không chứng minh khả năng chống dự đoán trước đối thủ.

**3. Vì sao không dùng `new Random(System.currentTimeMillis())` để tạo token?**  
Thời gian có thể đoán trong một khoảng, và thuật toán `Random` không được thiết kế để chống dự đoán.

**4. `SecureRandom` có phải true random không?**  
Không nhất thiết. Nó là API cho bộ sinh giả ngẫu nhiên mật mã, dựa trên state và cơ chế entropy/provider.

**5. Có cần tự seed `SecureRandom` bằng timestamp không?**  
Không. Hãy để provider tự khởi tạo theo cơ chế phù hợp; timestamp không phải entropy bí mật đáng tin cậy.

**6. Vì sao nên dùng `nextInt(bound)` thay cho modulo?**  
Phương thức có bound tránh modulo bias và trả giá trị trong phạm vi yêu cầu.

**7. `RandomGenerator` trong Java 17 có nghĩa là CSPRNG không?**  
Không. Đây là interface chung; cần xem implementation và yêu cầu bảo mật.

**8. Có nên dùng `SecureRandom` cho mọi mô phỏng không?**  
Không cần thiết. PRNG mô phỏng thường nhanh hơn và hỗ trợ tái lập; dùng đúng công cụ theo mục đích.

**9. Tạo token 32 byte rồi Base64 có làm tăng độ ngẫu nhiên không?**  
Không. Base64 chỉ đổi biểu diễn; nguồn byte có 256 bit trước mã hóa nếu generator cung cấp đủ chất lượng.

**10. Tạo OTP sáu chữ số bằng SecureRandom đã đủ bảo vệ OTP chưa?**  
Chưa. Còn cần thời hạn, giới hạn số lần thử, dùng một lần, ràng buộc tài khoản/giao dịch và bảo vệ kênh truyền.

## Tài liệu tham khảo chính thức

- [Java SE 17 API — `SecureRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): bộ sinh số giả ngẫu nhiên mật mã, seed, provider và các phương thức tạo byte.
- [Java SE 17 API — `Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): PRNG truyền thống và tính tái lập.
- [Java SE 17 API — `RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): interface generator trong Java 17.
- [Java SE 17 API — `RandomGeneratorFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): chọn implementation PRNG qua factory.
- [Java SE 17 API — `SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): generator có thể chia tách cho tính toán song song.
- [Java SE 17 API — `ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): generator gắn với thread.
- [Java SE 17 API — `KeyGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): API tạo khóa mật mã.
- [JEP 273 — DRBG-Based SecureRandom Implementations](https://openjdk.org/jeps/273): hỗ trợ các cơ chế DRBG trong Java.
- [Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): provider, thuật toán và kiến trúc dịch vụ mật mã của Java.
