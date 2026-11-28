# SecureRandom trong Java

> **Chương:** Secure randomness  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. SecureRandom là gì và tại sao quan trọng?

**`java.security.SecureRandom`** là API của Java để tạo các giá trị **giả ngẫu nhiên phù hợp cho mục đích mật mã** (cryptographically secure pseudorandom numbers), dựa trên một bộ sinh số ngẫu nhiên mật mã (**CSPRNG**) do security provider cung cấp. Ứng dụng có thể dùng nó để sinh secret key, nonce, salt, token hoặc các bí mật nhất thời theo định dạng và độ dài phù hợp.

Ví dụ, hệ thống cần sinh khóa AES-256. Việc tạo 32 byte bằng `java.util.Random`, `Math.random()` hoặc một công thức từ đồng hồ có thể cho byte nhìn có vẻ không có quy luật, nhưng **không bảo đảm khó dự đoán với đối thủ**. Ngược lại, một cấu hình `SecureRandom` phù hợp dựa trên nguồn entropy đáng tin cậy và thuật toán CSPRNG được thiết kế để đối thủ không thể dự đoán đầu ra tiếp theo chỉ bằng quan sát đầu ra trước đó.

Trong module quản lý khóa, **chất lượng randomness là nền tảng của cả vòng đời khóa**. Khóa được sinh bằng nguồn dễ đoán vẫn là khóa yếu, cho dù sau đó được lưu trong KMS, sử dụng AES-GCM, xoay vòng đúng lịch hoặc kiểm toán đầy đủ. Các công cụ bảo vệ về sau **không thể bù cho việc khóa có entropy quá thấp ngay khi tạo**.

### Sau bài này, bạn cần phân biệt được

- **Randomness / entropy / CSPRNG / DRBG** và những đảm bảo thực tế của từng khái niệm.
- Khi nào dùng `SecureRandom`, `KeyGenerator`, `KeyPairGenerator`; vì sao không dùng `Random` cho bí mật.
- Cách sinh đúng **secret key, nonce, IV, salt, token và mã OTP** theo mục đích.
- Các rủi ro **seed yếu, nonce reuse, VM snapshot, provider, lưu log, giới hạn sử dụng khóa**.
- Vai trò của `SecureRandom` so với **KMS/HSM**, envelope encryption, kiểm soát truy cập và audit.

## 2. Từ entropy đến CSPRNG và DRBG

### 2.1. Randomness không chỉ là "trông có vẻ lộn xộn"

Một chuỗi byte như `A7 F2 91 ...` có thể nhìn rất ngẫu nhiên nhưng vẫn có thể bị suy ra nếu bộ sinh được khởi tạo từ một timestamp, một seed cố định hoặc một trạng thái đã bị lộ. Trong mật mã, hai thuộc tính đặc biệt quan trọng:

1. **Khó dự đoán (unpredictability):** người không biết trạng thái bí mật không thể thực tế đoán các byte chưa được sinh.
2. **Đủ entropy trong vật liệu khởi tạo:** trạng thái bí mật của bộ sinh phải có nguồn khó đoán thực sự, không phải được tạo chỉ từ thông tin công khai hoặc dễ thu thập.

**Entropy** mô tả mức bất định của một nguồn. Một chuỗi đầu ra dài 256 bit **không tự có 256 bit entropy** nếu nó được suy ra từ seed chỉ có vài lựa chọn. Ví dụ, khởi tạo bộ sinh từ một timestamp gần đúng chỉ thu hẹp bài toán tấn công xuống số timestamp ứng viên, bất kể đầu ra dài bao nhiêu byte.

### 2.2. CSPRNG và DRBG

**CSPRNG** là bộ sinh giả ngẫu nhiên đáp ứng các mục tiêu bảo mật như khó dự đoán đầu ra; **DRBG** (Deterministic Random Bit Generator) là một họ bộ sinh xác định về mặt thuật toán, có trạng thái nội bộ được khởi tạo từ entropy và có thể hỗ trợ reseed.

~~~text
Nguồn entropy đáng tin cậy (thường từ hệ điều hành)
                         |
                         v
             Khởi tạo trạng thái CSPRNG/DRBG
                         |
              Sinh luồng byte khó đoán
                         |
         +---------------+---------------+
         |               |               |
       Secret key       Salt         Token / nonce
~~~

**Deterministic** không có nghĩa là không an toàn: với trạng thái bí mật đủ mạnh và thuật toán được thiết kế phù hợp, DRBG có thể tạo rất nhiều byte khó dự đoán mà không phải lấy một byte entropy mới cho mỗi byte đầu ra. Nhưng nếu trạng thái bị rò rỉ, kết quả phụ thuộc vào thiết kế reseed, khả năng chống dự đoán ngược và đặc tính của provider.

**Java `SecureRandom` là API, không phải một thuật toán duy nhất.** Thuật toán thực tế có thể do hệ điều hành, JDK và provider quyết định. Những tên như `DRBG`, `NativePRNG` hay `SHA1PRNG` là tên cơ chế/provider từng môi trường cung cấp; không nên giả định mọi JDK/OS đều hỗ trợ cùng tên hoặc vận hành giống nhau.

### 2.3. CSPRNG không thay thế KDF

- **CSPRNG:** tạo vật liệu ngẫu nhiên mới khi cần sinh secret key, nonce, salt, token.
- **HKDF:** dẫn xuất các khóa khác nhau từ bí mật đầu vào đã có entropy thích hợp và thông tin ngữ cảnh.
- **PBKDF2/Argon2id:** biến password entropy thấp thành giá trị kiểm chứng hoặc khóa dẫn xuất có chi phí thử đoán cao hơn.

Không dùng password người dùng làm **seed tùy chỉnh** cho `SecureRandom` để thay PBKDF2/Argon2id. Cũng không dùng một key đã sinh làm nguồn cho nhiều purpose bằng cách tự nối chuỗi hay cộng/trừ số: nếu cần dẫn xuất khóa có tách miền, dùng KDF thích hợp.

## 3. SecureRandom khác Random, ThreadLocalRandom và UUID

| API/cơ chế | Mục đích thông thường | Dùng trực tiếp tạo khóa/token bí mật? | Nhận xét |
| --- | --- | --- | --- |
| `Math.random()` | Mô phỏng hoặc logic ngẫu nhiên không cần tính bảo mật | **Không** | Không đưa ra bảo đảm CSPRNG |
| `java.util.Random` | Thử nghiệm, dữ liệu giả, thuật toán thống kê không nhạy cảm | **Không** | Trạng thái/đầu ra có thể bị dự đoán |
| `ThreadLocalRandom` | Tạo số ngẫu nhiên hiệu năng cao theo luồng | **Không** | Không dành cho secret key, OTP, session secret |
| `SplittableRandom` | Mô phỏng song song, tách luồng random | **Không** | Không phải primitive mật mã |
| `SecureRandom` | Byte/giá trị khó đoán cho mục đích mật mã | **Có, với provider và chính sách phù hợp** | Phải chọn đúng độ dài và cách dùng |
| `UUID.randomUUID()` | ID UUID version 4 | Không nên xem là API tạo khóa/secret tổng quát | UUID v4 chỉ có 122 bit ngẫu nhiên, phần còn lại là bit định dạng |
| `KeyGenerator`, `KeyPairGenerator` | Sinh khóa thuật toán cụ thể | **Có, khi cấu hình đúng** | Dựa vào nguồn random của provider/`SecureRandom` phù hợp |

`UUID.randomUUID()` của JDK dùng nguồn giả ngẫu nhiên đủ mạnh cho mục đích UUID, nhưng một UUID **không tương đương token 256-bit**; nó còn phải đáp ứng quy tắc biểu diễn UUID. Dùng UUID cho ID là một việc; muốn secret token có độ dài bảo mật xác định, hãy sinh byte bằng `SecureRandom` rồi encode rõ ràng.

**Nguyên tắc:** không chọn API chỉ theo tên có chữ "random". Xác định mục tiêu cần **khó đoán**, **duy nhất** hay cả hai; chúng là hai yêu cầu khác nhau.

## 4. Tạo SecureRandom trong Java đúng cách

### 4.1. Cách sử dụng thông thường

Đối với ứng dụng Java phổ biến, một cách khởi đầu hợp lý là:

~~~java
import java.security.SecureRandom;

public final class RandomBytesExample {
    private static final SecureRandom RNG = new SecureRandom();

    public static byte[] newRandomBytes(int length) {
        if (length <= 0 || length > 4096) {
            throw new IllegalArgumentException("Invalid length");
        }
        byte[] result = new byte[length];
        RNG.nextBytes(result);
        return result;
    }
}
~~~

`new SecureRandom()` chọn một triển khai từ các security provider được cấu hình cho runtime. Trong một JDK/OS được cập nhật và cấu hình đúng, đó thường là điểm khởi đầu cho byte ngẫu nhiên mật mã. **Không cần tự tạo seed bằng `System.currentTimeMillis()`, PID, username hay giá trị hash của dữ liệu ứng dụng.**

`SecureRandom` có thể dùng lại qua nhiều lời gọi. API hỗ trợ dùng giữa các luồng; chi tiết đồng bộ/hiệu năng tùy provider. Nếu ứng dụng tạo lượng random lớn, hãy benchmark và xác minh cấu hình provider, **không tự ý thay bằng `ThreadLocalRandom` để "tăng tốc"**.

### 4.2. `SecureRandom.getInstanceStrong()` có luôn tốt hơn?

`SecureRandom.getInstanceStrong()` chọn một thuật toán được đánh dấu phù hợp trong cấu hình `securerandom.strongAlgorithms` của môi trường Java. Tùy JDK, hệ điều hành và provider, thao tác tạo/sinh random **có thể chờ nguồn entropy hoặc có đặc điểm hiệu năng khác**.

Nó **không phải quy tắc bắt buộc** cho mọi nonce, salt hoặc token, cũng không bảo đảm tự động "an toàn hơn mọi cách khác" trên mọi máy. Hãy dùng khi có **yêu cầu chính sách cụ thể**, đã đánh giá provider, thao tác có thể block và tác động tới độ trễ. Đối với luồng request lớn, một `new SecureRandom()` cấu hình đúng thường phù hợp hơn việc gọi `getInstanceStrong()` liên tục mà không đo lường.

### 4.3. DRBG có thể cấu hình rõ khi cần

Java 9+ hỗ trợ cơ chế DRBG qua các API liên quan đến `DrbgParameters` khi provider cung cấp. Một ví dụ về cách **yêu cầu** cấu hình (không bảo đảm mọi provider hỗ trợ chính xác cấu hình này):

~~~java
import java.security.DrbgParameters;
import java.security.SecureRandom;

public class DrbgExample {
    static SecureRandom createRng() throws Exception {
        return SecureRandom.getInstance(
                "DRBG",
                DrbgParameters.instantiation(
                        128, DrbgParameters.Capability.RESEED_ONLY, null));
    }
}
~~~

Chỉ định strength trong yêu cầu DRBG **không tạo entropy từ hư không** và không cho phép bỏ qua giới hạn của thuật toán/provider. Khi chọn provider hay chế độ FIPS, cần đối chiếu yêu cầu triển khai thực tế và thử nghiệm. Tránh gán thuật toán theo tên mà chưa biết nguồn entropy, giới hạn, khả năng reseed và trạng thái chứng nhận nếu chính sách đòi hỏi.

### 4.4. Không tự seed để tìm tính lặp lại trong production

~~~java
// KHÔNG dùng cho bí mật:
// SecureRandom rng = new SecureRandom("fixed-seed".getBytes(UTF_8));
// rng.setSeed(System.currentTimeMillis());
~~~

API `setSeed` của `SecureRandom` trong nhiều provider bổ sung dữ liệu seed vào trạng thái, nhưng **không thể coi đó là cách điều khiển tái lập kết quả ổn định giữa JDK/provider**; một số cách khởi tạo seed do ứng dụng cung cấp còn có thể làm giảm chất lượng đầu vào nếu cấu hình sai. Với mã cần test lặp lại, hãy **tách nguồn random bằng interface và truyền fake/deterministic generator chỉ trong test**, không làm yếu cách sinh khóa production.

## 5. Sinh secret key và cặp khóa bất đối xứng

### 5.1. AES-256

Ưu tiên `KeyGenerator` để sinh khóa đúng thuật toán và độ dài:

~~~java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public class GenerateAesKey {
    static SecretKey generateAes256(SecureRandom rng) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, rng);
        return generator.generateKey();
    }
}
~~~

Với khóa mới ngẫu nhiên 256 bit, nguồn ngẫu nhiên và provider phù hợp, khóa có mức entropy mục tiêu tương ứng với việc sinh khóa; **không suy từ độ dài một chuỗi Base64/hex** mà kết luận khóa mạnh. Nếu ứng dụng tự tạo byte, phải dùng `SecureRandom.nextBytes` với đúng kích thước và kiểu `SecretKeySpec`; không dùng password hoặc `random.nextLong()` để lấp đầy 32 byte theo cách dễ đoán.

**Sinh khóa an toàn chưa đủ:** khóa cần được cấp phát tới đúng workload, lưu trong vùng bảo vệ, giới hạn quyền encrypt/decrypt, có cryptoperiod, rotation và quy trình thu hồi/hủy. Tạo một khóa mạnh rồi ghi byte khóa vào `application.properties` hoặc log vẫn làm toàn bộ thiết kế mất an toàn.

### 5.2. Khóa RSA/ECC và chữ ký số

Đối với RSA, EC, Ed25519 hoặc cơ chế khác, nên dùng **`KeyPairGenerator` với thuật toán/độ mạnh được phê duyệt** hoặc dịch vụ KMS/HSM hỗ trợ, thay vì tự tính số nguyên tố/seed/khóa riêng.

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;

public class GenerateSigningKey {
    static KeyPair newRsaKeyPair(SecureRandom rng) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072, rng);
        return generator.generateKeyPair();
    }
}
~~~

`3072` bit ở đây chỉ là tham số minh họa; độ dài khóa và thuật toán phải được chọn theo **mức an toàn, chính sách/tiêu chuẩn đang áp dụng và yêu cầu tương thích**. Đối với chữ ký số, chỉ **private key** được phép ký; public key có thể phân phối nhưng **phải xác thực ràng buộc với danh tính** qua PKI hoặc kênh tin cậy.

Việc sinh private key bằng `SecureRandom` trong JVM **không đồng nghĩa private key được bảo vệ trong HSM**. Nếu chính sách yêu cầu khóa không xuất, thực hiện **generate key bên trong KMS/HSM** và chỉ gọi API ký/giải mã được cấp quyền.

## 6. Nonce và IV: ngẫu nhiên chưa đủ, phải xét tính duy nhất

Đối với nhiều chế độ AEAD, đặc biệt **AES-GCM** và **ChaCha20-Poly1305 (IETF)**, điều kiện an toàn quan trọng là **không mã hóa hai thông điệp bằng cùng cặp (key, nonce)**.

**Nonce không cần bí mật.** Nó có thể lưu kèm ciphertext. Nhưng nonce dùng lại dưới một khóa có thể gây phá vỡ nghiêm trọng tính bí mật và xác thực, kể cả khi nonce từng được tạo bởi CSPRNG rất tốt.

### 6.1. Ví dụ AES-GCM với nonce 96 bit

~~~java
import java.security.SecureRandom;

public class NonceExample {
    static byte[] newGcmNonce(SecureRandom rng) {
        byte[] nonce = new byte[12]; // 96 bit
        rng.nextBytes(nonce);
        return nonce;
    }
}
~~~

Đây là cách sinh nonce **ngẫu nhiên** cho **lượng mã hóa được kiểm soát**. Nó không chứng minh tuyệt đối rằng nonce sẽ không trùng khi số bản tin lớn hoặc có nhiều instance dùng chung một key. Xác suất ít nhất một va chạm của `q` nonce ngẫu nhiên đều 96 bit có xấp xỉ birthday bound:

\[
P(\text{collision}) \approx \frac{q(q-1)}{2^{97}}
\]

Công thức là gần đúng khi xác suất còn nhỏ và giả định các nonce được sinh độc lập, đồng đều. Khi số lần mã hóa tăng, **xác suất trùng tăng nhanh theo bình phương số lần sử dụng**. Vì vậy, chỉ dùng nonce ngẫu nhiên khi **hạn mức sử dụng khóa và mức rủi ro** cho phép; tuân thủ giới hạn của thuật toán, giao thức và thư viện.

### 6.2. Nonce theo counter ở hệ thống nhiều node

Nếu cần bảo đảm duy nhất nghiêm ngặt, có thể thiết kế nonce theo **bộ đếm/sequence number**, kết hợp phân vùng được cấp phát cho từng node hoặc khóa, theo đặc tả thuật toán/giao thức:

~~~text
Key ID = key-v7
    |
    +-- Node A: namespace A + counter tăng đơn điệu
    +-- Node B: namespace B + counter tăng đơn điệu
    +-- Node C: namespace C + counter tăng đơn điệu

Không node nào được tái sử dụng namespace/counter dưới cùng key.
~~~

Quy trình phải ngăn **counter reset sau restart, VM snapshot rollback, failover hoặc sao chép trạng thái**. Không được cho hai node clone cùng state rồi cùng mã hóa bằng một key và dải nonce giống nhau. Đừng tự phát minh quy tắc nonce cho TLS/SSH; thư viện giao thức chuẩn đã có cơ chế nonce/sequence number riêng.

### 6.3. Salt khác nonce thế nào?

| Thuộc tính | Salt cho password hashing/KDF | Nonce cho AEAD |
| --- | --- | --- |
| Cần bí mật? | Không | Không |
| Cần ngẫu nhiên? | Thường dùng salt ngẫu nhiên, riêng từng verifier/đối tượng | Có thể ngẫu nhiên hoặc counter tùy thuật toán/giao thức |
| Mục tiêu | Tách kết quả dẫn xuất, chống bảng băm tính trước | Bảo đảm mỗi phép mã hóa dưới cùng key dùng tham số khác |
| Khi trùng? | Có thể làm mất lợi ích phân biệt và chống tính trước cho các bản ghi trùng salt | **Rất nguy hiểm** nếu trùng với cùng key ở AES-GCM/ChaCha20-Poly1305 |
| Có lưu kèm dữ liệu? | Có | Có |

Không lấy kết quả `SecureRandom` rồi đổi nhãn từ salt thành nonce mà bỏ qua **quy tắc duy nhất theo từng key**.

## 7. Sinh token, mật mã đặt lại mật khẩu và OTP

### 7.1. Token bí mật khó đoán

Reset token, API token dạng bearer, mã mời bí mật hoặc session secret có thể dùng **32 byte từ CSPRNG**, sau đó mã hóa thành Base64url để truyền qua URL/header an toàn hơn:

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;

public class TokenGenerator {
    private static final SecureRandom RNG = new SecureRandom();

    static String newOpaqueToken() {
        byte[] random = new byte[32]; // 256 bit
        RNG.nextBytes(random);
        try {
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(random);
        } finally {
            Arrays.fill(random, (byte) 0);
        }
    }
}
~~~

Mã hóa Base64url **không thêm entropy** và **không phải mã hóa bảo mật**; nó chỉ chuyển byte thành văn bản. Với 32 byte lấy từ nguồn ngẫu nhiên mật mã tốt, token có tối đa 256 bit entropy trước khi encode.

Token cần được **giới hạn quyền, phạm vi và thời gian**. Trong kho dữ liệu, thường có thể lưu **hash của opaque token có entropy cao** thay vì lưu token dạng rõ, rồi so sánh an toàn khi nhận; khi tạo token mới nên hiển thị raw token cho người dùng **một lần**. Không áp dụng quy tắc SHA-256 dành cho token ngẫu nhiên có entropy cao sang **mật khẩu người dùng**: password vẫn cần Argon2id/PBKDF2/bcrypt/scrypt theo chính sách.

Token qua URL có thể lộ qua browser history, referrer, log hoặc hệ thống giám sát nếu luồng không được thiết kế kỹ. Với reset password, cần có **thời hạn ngắn, dùng một lần, ràng buộc đúng tài khoản và vô hiệu hóa sau sử dụng**. Không viết token vào access log hoặc debug trace.

### 7.2. Mã số ngắn (OTP)

Nếu cần tạo mã số 6 chữ số ngẫu nhiên cho một luồng xác minh, có thể dùng:

~~~java
int code = new SecureRandom().nextInt(1_000_000);
String sixDigits = String.format("%06d", code);
~~~

`nextInt(bound)` tạo giá trị trong khoảng `[0, bound)` và tránh sai lệch modulo khi triển khai đúng API. Tuy nhiên, một mã 6 chữ số chỉ có **1.000.000 khả năng (~20 bit)**, không phải một bí mật mạnh tương đương token 256-bit.

Vì vậy, phải thêm **giới hạn số lần thử, thời gian hết hạn ngắn, ràng buộc với một tài khoản/hành động và chống dùng lại**. Nếu dùng **TOTP/HOTP**, mã phải được tạo theo chuẩn HMAC/counter/time đã được quy định; không thay TOTP bằng một số random tùy ý rồi gọi đó là TOTP.

## 8. SecureRandom kết hợp với AEAD: ví dụ Java 17 đầy đủ

Ví dụ tiếp theo sinh **khóa AES-256** và **nonce AES-GCM 12 byte**, mã hóa bản tin có AAD, sau đó giải mã và xác minh tag. Nó dùng `SecureRandom` cho các giá trị phải được sinh ngẫu nhiên và `Cipher` cho thao tác AEAD. Bản mã phải lưu nonce, tag và metadata cần thiết; không lưu khóa AES dạng rõ cạnh bản mã.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class SecureRandomAeadDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    record Envelope(byte[] nonce, byte[] ciphertextAndTag) {}

    static SecretKey newAes256Key() throws Exception {
        KeyGenerator kg = KeyGenerator.getInstance("AES");
        kg.init(256, RNG);
        return kg.generateKey();
    }

    static Envelope encrypt(SecretKey key, byte[] plain, byte[] aad)
            throws Exception {
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return new Envelope(nonce, cipher.doFinal(plain));
    }

    static byte[] decrypt(SecretKey key, Envelope envelope, byte[] aad)
            throws Exception {
        if (envelope.nonce().length != NONCE_BYTES) {
            throw new IllegalArgumentException("Invalid nonce");
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, envelope.nonce()));
        cipher.updateAAD(aad);
        // Cipher.doFinal sẽ thất bại nếu ciphertext/tag/AAD bị sửa.
        return cipher.doFinal(envelope.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        // Mô phỏng đúng một phép mã hóa bằng một khóa mới.
        // Production cần quản lý nonce duy nhất cho mọi lần dùng key.
        SecretKey key = newAes256Key();
        byte[] aad = "tenant-42|record-1001|v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plain = "Du lieu mau".getBytes(StandardCharsets.UTF_8);

        Envelope envelope = encrypt(key, plain, aad);
        byte[] restored = decrypt(key, envelope, aad);
        System.out.println(new String(restored, StandardCharsets.UTF_8));
        // Không in khóa, nonce/key mapping hay plaintext thật ra log.
    }
}
~~~

**Những điểm phải bổ sung trước production:**

1. **Tính duy nhất của nonce:** demo tạo đúng một bản mã nên không biểu diễn giới hạn số lần dùng trên một key. Với nhiều bản mã, phải có chính sách nonce và hạn mức theo khóa; với nhiều node, cân nhắc counter/namespace hoặc **DEK riêng cho đối tượng**.
2. **AAD có định dạng rõ:** trong ví dụ chuỗi phân tách chỉ minh họa. Với metadata phức tạp, dùng encoding có trường/độ dài không mơ hồ và đối chiếu quyền tenant từ ngữ cảnh xác thực.
3. **Ciphertext format:** lưu algorithm version, key ID/version, nonce, ciphertext và tag; áp dụng kiểm tra kích thước/định dạng trước khi giải mã.
4. **KMS/HSM:** khóa thật cần lưu/phân phối/thu hồi phù hợp, ví dụ DEK được wrap bởi KEK của KMS, không đưa byte khóa rõ vào database.
5. **Lỗi xác thực:** không bỏ qua `AEADBadTagException`; từ chối bản tin bị sửa hoặc giải mã sai khóa/AAD.
6. **Bộ nhớ:** giảm vòng đời plaintext và DEK dạng rõ; không log, không để memory dump nhạy cảm lộ ngoài miền quản trị.

## 9. Vấn đề triển khai: seed yếu, container, snapshot, provider

### 9.1. Seed yếu và khởi động hệ thống

Mọi CSPRNG đều phụ thuộc chất lượng vật liệu khởi tạo. Trên môi trường máy chủ thông thường, JDK được cấu hình đúng sử dụng dịch vụ ngẫu nhiên của hệ điều hành; nhưng ở **thiết bị nhúng, hệ điều hành khởi động sớm, runtime cũ, môi trường ảo hóa hoặc cấu hình provider sai**, chất lượng nguồn entropy và cách khởi tạo cần được xem xét.

Không tự sửa bằng cách thêm `System.nanoTime()`, PID hoặc username vào seed rồi tin rằng đủ bảo mật. Thay vào đó, dùng **nguồn entropy và provider được kiểm soát**, cập nhật OS/JDK, tham chiếu tiêu chuẩn áp dụng và có cơ chế vận hành khi nguồn random không sẵn sàng.

### 9.2. Container/VM snapshot và nhân bản trạng thái

Khi snapshot một tiến trình có trạng thái CSPRNG rồi khôi phục thành hai bản sao, có nguy cơ **hai bản sao tiếp tục từ trạng thái tương tự**, tùy cơ chế provider, nguồn entropy và cách reseed. Rủi ro đặc biệt đáng chú ý nếu ứng dụng còn sao chép cả **secret key và bộ đếm nonce**.

Các biện pháp kiến trúc:

- Dùng runtime và hệ điều hành có cơ chế entropy/reseed phù hợp với ảo hóa.
- Kiểm tra chính sách reseed hoặc tái tạo trạng thái bí mật sau restore/fork khi kiến trúc yêu cầu.
- Không nhân bản **counter/namespace nonce** cho cùng một key.
- Với hệ thống phân tán, quản lý **key ID, instance identity và nonce allocation** độc lập; không dựa vào đồng hồ để tạo sự khác biệt.
- Kiểm thử hành vi khi failover, restore backup và tự động scale.

### 9.3. `getInstanceStrong()` gây trễ hoặc block

Một số cấu hình strong RNG dùng nguồn có thể có độ trễ hoặc chờ điều kiện hệ thống. Trong web API có thời hạn phản hồi ngắn, việc vô tình gọi strong RNG trên mọi request có thể gây gián đoạn. Thực hành tốt là **đo latency và thông số provider trên môi trường triển khai**, chọn thuật toán theo chính sách và thiết kế xử lý khi dịch vụ không đủ entropy/thao tác thất bại.

Không giảm bảo mật bằng cách fallback ngầm sang `Random` hay thời gian hệ thống chỉ để vượt lỗi. Khi không thể tạo khóa/token an toàn, thao tác nên **fail closed** theo thiết kế ứng dụng.

### 9.4. Đừng xem thống kê đầu ra là bằng chứng an toàn

Một tập byte qua kiểm tra phân bố đều hoặc nhìn có vẻ ngẫu nhiên **không chứng minh** bộ sinh không thể bị dự đoán. Cần tin vào **thuật toán đã được đánh giá, chất lượng entropy, provider, cấu hình, cập nhật hệ thống và kiểm thử tích hợp**. Các kiểm thử thống kê có vai trò trong đánh giá bộ sinh nhưng không thay thế phân tích mật mã.

## 10. SecureRandom trong KMS, HSM và envelope encryption

Trong **envelope encryption**, ứng dụng tạo hoặc nhận **DEK** để mã hóa dữ liệu bằng AES-GCM/ChaCha20-Poly1305, sau đó dùng **KEK** do KMS/HSM quản lý để bảo vệ DEK. Nguồn entropy tốt cần có tại nơi tạo khóa — đó có thể là **KMS/HSM**, không nhất thiết là tiến trình Java.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Java
    participant KMS as KMS/HSM
    participant DB as Kho bản mã
    App->>KMS: GenerateDataKey theo IAM policy
    KMS-->>App: DEK tạm thời + wrapped DEK
    App->>App: Sinh nonce thích hợp, mã hóa AEAD bằng DEK
    App->>DB: Lưu ciphertext + nonce/tag + wrapped DEK
    DB-->>App: Đọc bản mã khi được phép
    App->>KMS: Unwrap DEK theo quyền
    KMS-->>App: DEK nếu policy cho phép
    App->>App: Giải mã và xác minh AEAD tag
~~~

Ví dụ diễn tả **một mô hình API có thể gặp**; không phải mọi KMS đều hỗ trợ `GenerateDataKey` hoặc trả DEK dạng rõ giống nhau. Một số kiến trúc yêu cầu khóa không bao giờ rời HSM; một số lại dùng Java `SecureRandom` để sinh DEK và gọi KMS `WrapKey`/encrypt để bọc. Phải tuân theo khả năng API, mô hình đe dọa và ràng buộc lưu trữ khóa của nhà cung cấp cụ thể.

### Tách trách nhiệm

| Thành phần | Trách nhiệm chính |
| --- | --- |
| **SecureRandom / KeyGenerator** | Cung cấp byte/khóa khó đoán khi ứng dụng có quyền sinh vật liệu khóa |
| **Cipher / Signature / KDF** | Sử dụng khóa để mã hóa có xác thực, ký hoặc dẫn xuất theo thuật toán |
| **KMS/HSM** | Bảo vệ khóa, API mật mã, phân quyền, rotation và audit theo năng lực nhà cung cấp |
| **IAM / policy** | Xác định workload/người nào có quyền tạo, bọc, giải mã, ký, thu hồi hoặc xóa khóa |
| **Application authorization** | Đảm bảo người dùng/tenant được phép đọc/ghi đối tượng, độc lập với quyền KMS |
| **Audit/monitoring** | Theo dõi thao tác, phiên bản khóa, sự cố và thay đổi policy, không ghi raw key |

**Không coi "đã dùng SecureRandom" là đủ an toàn cho khóa.** CSPRNG chỉ giải quyết khâu tạo vật liệu; vòng đời còn gồm cấp phát, lưu giữ, sử dụng, kiểm soát nonce, xoay vòng, thu hồi, hủy và khả năng khôi phục bản mã cũ.

## 11. Tình huống thực tế: dịch vụ cấp API token đa vùng

Một nền tảng đa tenant cung cấp API token dạng bearer cho các đối tác. Dịch vụ tạo token triển khai ở nhiều vùng cloud và cần hỗ trợ vô hiệu hóa, kiểm toán.

**Thiết kế đề xuất:**

1. Mỗi lần cấp token, ứng dụng dùng CSPRNG đáng tin cậy để tạo **32 byte** ngẫu nhiên; encode Base64url thành một token có đủ độ dài bảo mật.
2. Chỉ gửi token qua kênh TLS đến người nhận đã được xác thực; không đưa token vào URL nếu có thể dùng header/kênh phù hợp.
3. Lưu **hash của token** cùng owner/tenant ID, scope, issuedAt, expiresAt, trạng thái thu hồi và bản ghi audit; không lưu raw token trong database nghiệp vụ nếu thiết kế cho phép hash-based lookup.
4. Khi API nhận token, tra và kiểm tra hash, quyền scope/tenant, thời hạn và trạng thái; bảo vệ khỏi replay/lạm dụng qua rate limit và giám sát.
5. Khi token bị nghi lộ, thu hồi bản ghi và cấp token mới. **Rotation không xóa ảnh hưởng của token đã bị lộ** nếu hệ thống vẫn chấp nhận token cũ.
6. Các vùng dùng `SecureRandom` theo runtime/provider thích hợp. Không sinh token từ **timestamp + region ID + counter dễ đoán** rồi tin rằng đã có 256 bit bảo mật.

**Hai ranh giới khác nhau:**

- **Khó đoán token** là nhiệm vụ của CSPRNG.
- **Không trùng token / quản trị bản ghi** cần quy trình quản lý định danh, kiểm tra collision hiếm gặp và chính sách lưu trữ.

Một token không cần mật mã bất đối xứng chỉ để khó đoán; nhưng nếu nền tảng chọn JWT có chữ ký, khi đó **private key ký và public key phân phối** trở thành một bài toán quản lý khóa khác. Hệ thống vẫn cần xử lý hạn dùng, quyền, thu hồi và audit.

## 12. Các lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `new Random()` hoặc `Math.random()` sinh AES key | Đầu ra có thể bị dự đoán | Dùng `KeyGenerator`/`SecureRandom` từ provider phù hợp |
| Lấy timestamp, PID, MAC address làm seed | Không có entropy đủ mạnh | Để OS/provider cung cấp entropy đáng tin cậy |
| Dùng seed cố định trong production để dễ debug | Có thể tạo chuỗi ngẫu nhiên dự đoán/lặp lại | Test bằng fake RNG; production dùng nguồn CSPRNG thực |
| Cho rằng mọi byte `SecureRandom` luôn duy nhất | Nonce có thể va chạm về xác suất | Chọn chiến lược uniqueness và hạn mức theo key |
| Dùng lại AES-GCM nonce cùng key | Có thể phá bí mật và xác thực | Nonce không lặp, quản lý counter/namespace hoặc DEK phạm vi nhỏ |
| Reset counter khi restart hoặc clone VM | Nhiều bản mã cùng (key, nonce) | Giữ counter bền vững, partition duy nhất, xử lý snapshot |
| Dùng `getInstanceStrong()` không kiểm tra vận hành | Có thể gây latency/block | Benchmark provider và chọn theo chính sách |
| Thay CSPRNG bằng `ThreadLocalRandom` để tăng throughput | Giảm bảo mật của secret | Tối ưu dựa trên benchmark an toàn và provider được duyệt |
| Dùng UUID cho secret đòi hỏi 256 bit | Độ dài hiệu dụng không đúng yêu cầu | Sinh byte với độ dài xác định, encode nếu cần |
| Sinh salt chung cho mọi tài khoản | Làm mất tính tách biệt password verifier | Salt ngẫu nhiên riêng từng verifier |
| Gọi token 6 chữ số là "khó đoán như 256-bit" | Dễ bị brute-force nếu không giới hạn thử | TTL ngắn, giới hạn thử, dùng một lần và ràng buộc tài khoản |
| In khóa, token, plaintext vào log để debug | Rò rỉ bí mật ngay cả khi sinh khóa đúng | Loại bỏ dữ liệu nhạy cảm khỏi log/trace/dump |
| Tự cài đặt DRBG hoặc thuật toán sinh số ngẫu nhiên | Rủi ro lỗi mật mã rất lớn | Dùng JDK/provider/KMS/HSM được đánh giá |
| Tin AES-256 mạnh đồng nghĩa password sinh khóa đủ mạnh | Password yếu vẫn bị đoán | Dùng Argon2id/PBKDF2 cho password, hoặc DEK ngẫu nhiên |

## 13. Checklist triển khai và kiểm toán

- [ ] Mọi secret key, nonce, salt và token được sinh bởi **API thích hợp với mục đích**, không dùng `Random` cho secret?
- [ ] JDK, OS, security provider được cập nhật và nguồn entropy có cấu hình/kiểm soát vận hành phù hợp?
- [ ] Có chính sách về thuật toán/provider hoặc DRBG được phê duyệt khi hệ thống phải tuân thủ tiêu chuẩn?
- [ ] Không tự đặt seed từ clock/PID/giá trị public hoặc dùng seed cố định trong production?
- [ ] Các key/secret có **độ dài bit và mục đích** đúng, được phân biệt với Base64/hex/UUID?
- [ ] AES-GCM/ChaCha20-Poly1305 có chiến lược **không trùng nonce dưới cùng key** kể cả ở hệ thống nhiều node?
- [ ] Có giới hạn số thông điệp theo key, quy trình cryptoperiod/rotation và xử lý khi gần giới hạn?
- [ ] Nonce allocator/counter có chịu được restart, autoscaling, restore và snapshot rollback?
- [ ] Password salt được sinh riêng; password hashing dùng Argon2id/PBKDF2/bcrypt/scrypt theo chính sách?
- [ ] OTP có TTL ngắn, giới hạn thử và chống dùng lại; token bearer có entropy đủ mạnh, scope và thu hồi?
- [ ] Các secret không bị lộ qua log, trace, telemetry, crash dump, source code hoặc backup?
- [ ] KMS/HSM có quyền tối thiểu, phân chia trách nhiệm và audit các thao tác nhạy cảm?
- [ ] Có thử nghiệm failover/restore và khả năng đọc dữ liệu được mã hóa trước key rotation?
- [ ] Khi random provider/entropy không sẵn sàng, ứng dụng thất bại an toàn thay vì fallback sang RNG yếu?

## 14. Câu hỏi tự kiểm tra

**1. Vì sao `Random` không phù hợp để sinh khóa AES dù nó tạo byte khác nhau?**  
Vì `Random` không cung cấp bảo đảm khó dự đoán trước đối thủ. Giá trị có vẻ hỗn loạn không đồng nghĩa có entropy đủ cao và an toàn mật mã.

**2. `new SecureRandom()` có cùng thuật toán trên mọi JDK không?**  
Không. Đây là API dùng các security provider; thuật toán và nguồn entropy cụ thể phụ thuộc runtime, hệ điều hành và cấu hình.

**3. `SecureRandom.getInstanceStrong()` có bắt buộc tốt hơn cho mọi request không?**  
Không. Nó chọn theo cấu hình strong algorithms và có thể ảnh hưởng latency/block; phải đánh giá yêu cầu bảo mật, hiệu năng và provider.

**4. Một nonce AES-GCM 96 bit được lấy ngẫu nhiên có chắc chắn không trùng không?**  
Không tuyệt đối. Nonce ngẫu nhiên có xác suất va chạm; khi lưu lượng lớn cần hạn mức và chiến lược uniqueness được chứng minh.

**5. Vì sao salt của password hashing được lưu công khai?**  
Vì salt không phải bí mật, mà dùng để tách kết quả và chống bảng hash tính sẵn. Password vẫn cần thuật toán hashing chuyên dụng và tham số chi phí phù hợp.

**6. Token Base64url dài 43 ký tự có chắc 256 bit entropy không?**  
Chỉ khi được encode từ **32 byte khó đoán thực sự**. Độ dài chuỗi không tạo thêm entropy; nếu đầu vào yếu, token vẫn yếu.

**7. Trong thiết kế envelope encryption, có cần `SecureRandom` của Java sinh mọi DEK không?**  
Không. KMS/HSM có thể sinh DEK bằng nguồn ngẫu nhiên riêng; Java dùng API KMS theo quyền. Điều quan trọng là nguồn tạo khóa đủ an toàn và vật liệu được quản lý đúng vòng đời.

**8. Sinh khóa bằng SecureRandom rồi lưu plaintext key vào log có an toàn không?**  
Không. CSPRNG chỉ giúp tạo khóa khó đoán; khi khóa lộ do lưu trữ/vận hành sai, độ mạnh của randomness không còn bảo vệ bí mật.

## Ghi nhớ

**`SecureRandom` là API tạo số giả ngẫu nhiên mật mã trong Java, dùng để sinh vật liệu bí mật khó dự đoán từ một provider và nguồn entropy phù hợp.** Nó khác `Random`/`ThreadLocalRandom` và không tự bảo đảm mọi giá trị sinh ra đều **duy nhất**. Với AES-GCM/ChaCha20-Poly1305, phải quản lý **cặp (key, nonce)**; với password, dùng salt ngẫu nhiên nhưng vẫn cần KDF phù hợp; với token/OTP, cần độ dài, TTL và kiểm soát quyền đúng mục đích. Kết hợp SecureRandom với **KeyGenerator, KMS/HSM, envelope encryption, cryptoperiod, rotation, thu hồi, phân quyền và audit** để bảo vệ khóa xuyên suốt từ lúc tạo đến khi hủy; đừng để nguồn random tốt bị vô hiệu bởi quản lý khóa sai.
