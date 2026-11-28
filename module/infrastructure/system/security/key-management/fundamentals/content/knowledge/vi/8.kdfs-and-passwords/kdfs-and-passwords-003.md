# PBKDF2

> **Chương:** KDF và mật khẩu  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. PBKDF2 là gì?

**PBKDF2 (Password-Based Key Derivation Function 2)** là một **hàm dẫn xuất khóa từ mật khẩu** (password-based key derivation function) được chuẩn hóa trong họ **PKCS #5 / RFC 8018**. PBKDF2 biến mật khẩu hoặc passphrase cùng một **salt** và **số vòng lặp** thành một chuỗi byte có độ dài mong muốn.

PBKDF2 giải quyết bài toán: **mật khẩu do con người chọn thường dễ đoán**, không thích hợp để dùng trực tiếp làm khóa AES hay làm giá trị kiểm chứng đăng nhập. Thay vì băm một lần thật nhanh bằng SHA-256, PBKDF2 thực hiện nhiều phép tính dựa trên **PRF (pseudorandom function)**, thường là HMAC-SHA-256, để tăng chi phí kiểm tra từng mật khẩu ứng viên.

Ví dụ:

~~~text
Input:
  password  = mật khẩu do người dùng nhập
  salt      = 16 byte ngẫu nhiên, riêng cho bản ghi
  iterations = chi phí lặp theo chính sách
  dkLen     = 32 byte
  PRF       = HMAC-SHA-256

Output:
  derivedKey = PBKDF2(password, salt, iterations, dkLen, PRF)
~~~

**PBKDF2 không tạo thêm entropy cho mật khẩu yếu.** Nó chỉ làm mỗi lần thử đoán trở nên tốn tài nguyên hơn. Nếu mật khẩu là `123456`, kẻ tấn công vẫn có thể thử đúng ứng viên đó; số vòng lặp quyết định chi phí của lần thử, chứ không biến một mật khẩu yếu thành bí mật có độ ngẫu nhiên tương đương khóa 256 bit.

PBKDF2 có hai cách sử dụng phổ biến nhưng **không được đánh đồng**:

1. **Password verifier:** dẫn xuất giá trị lưu trong hệ thống xác thực để kiểm tra mật khẩu khi đăng nhập.
2. **Password-based encryption:** dẫn xuất khóa đối xứng từ passphrase để mã hóa hoặc mở khóa dữ liệu.

Trong cả hai, công tác **quản lý khóa** bao gồm tham số KDF, quyền truy cập dữ liệu, chính sách thay đổi/thu hồi, lưu giữ, kiểm toán và phương án phục hồi. PBKDF2 là **một thành phần**, không phải toàn bộ hệ thống bảo vệ bí mật.

## 2. Các thành phần đầu vào và đầu ra

PBKDF2 thường được ký hiệu:

\[
DK = \operatorname{PBKDF2}(P,\ S,\ c,\ dkLen,\ PRF)
\]

| Thành phần | Ý nghĩa | Quy tắc thực hành |
| --- | --- | --- |
| `P` — password | Mật khẩu/passphrase làm nguồn đầu vào | Giữ bí mật; tránh log và giữ ở dạng rõ lâu hơn cần thiết |
| `S` — salt | Chuỗi byte bổ sung vào quá trình dẫn xuất | Sinh bằng CSPRNG, riêng cho mỗi verifier hoặc đối tượng được bảo vệ; **không cần giữ bí mật** |
| `c` — iteration count | Số lần lặp PRF cho mỗi khối đầu ra | Số nguyên dương; chọn theo yêu cầu bảo mật và benchmark; lưu cùng dữ liệu |
| `dkLen` | Độ dài khóa dẫn xuất cần lấy | Ví dụ 32 byte nếu cần khóa AES-256; phải thống nhất khi xác minh |
| `PRF` | Hàm giả ngẫu nhiên bên trong | Thường HMAC-SHA-256; thuật toán phải được ghi rõ để tương thích |
| `DK` — derived key | Chuỗi byte kết quả | Có thể là password verifier hoặc khóa mã hóa tùy mục đích; **không dùng lại tùy tiện cho nhiều mục đích** |

### 2.1. Salt không phải secret key

Salt chủ yếu giúp:

- Cùng một mật khẩu ở hai tài khoản cho **hai kết quả khác nhau** khi salt khác.
- Làm các bảng băm tính trước dùng chung (rainbow tables) khó áp dụng hàng loạt.
- Buộc kẻ tấn công, sau khi lấy được verifier, phải tính toán theo salt của từng mục tiêu.

Salt có thể lưu công khai cùng verifier hoặc ciphertext. Nó **không thay thế tính mạnh của mật khẩu, số vòng lặp hay pepper**. Không dùng username, thời gian, một hằng số chung hoặc bộ đếm reset để giả làm salt ngẫu nhiên cho password hashing; dùng `SecureRandom` hoặc API sinh salt của thư viện.

### 2.2. Iterations không phải thời hạn sử dụng khóa

Số lần lặp **`c`** là chi phí **cho một phép dẫn xuất**, không phải số lần người dùng được đăng nhập, số lượt dùng key hay cryptoperiod. Cryptoperiod đặt giới hạn thời gian sử dụng khóa; iteration count chỉ quyết định lượng tính toán của PBKDF2.

Tăng `c` làm **cả hệ thống xác thực lẫn kẻ tấn công** phải tính nhiều hơn. Do đó chọn tham số quá cao mà không có rate limit và giới hạn tài nguyên có thể khiến login bị quá tải hoặc bị lợi dụng để tấn công từ chối dịch vụ.

## 3. PBKDF2 hoạt động như thế nào?

PBKDF2 xây dựng trên PRF, điển hình là `HMAC-SHA-256`. Với mỗi khối đầu ra `T_i`, thuật toán tính một chuỗi các giá trị:

\[
\begin{aligned}
U_1 &= \operatorname{PRF}(P,\ S \parallel \operatorname{INT}_{32\mathrm{BE}}(i))\\
U_j &= \operatorname{PRF}(P,\ U_{j-1}),\qquad 2 \le j \le c\\
T_i &= U_1 \oplus U_2 \oplus \cdots \oplus U_c
\end{aligned}
\]

Trong đó:

- `S || INT_32_BE(i)` nghĩa là nối salt với số thứ tự khối `i` mã hóa thành 4 byte big-endian.
- `⊕` là XOR từng byte.
- Các khối `T_1`, `T_2`... được ghép lại và cắt tới `dkLen` byte.
- Với HMAC-SHA-256, mỗi khối `T_i` dài 32 byte; nếu yêu cầu 32 byte đầu ra thì chỉ cần một khối.

~~~mermaid
flowchart TD
    P[Password P] --> H[HMAC dùng P làm khóa PRF]
    S[Salt S] --> U1[U1 = PRF/P, S + blockIndex]
    H --> U1
    U1 --> U2[U2 = PRF/P, U1]
    U2 --> UC[Lặp tới Uc]
    U1 --> XOR[XOR U1 ... Uc]
    U2 --> XOR
    UC --> XOR
    XOR --> T[Khối T_i]
    T --> DK[Ghép khối, lấy dkLen byte]
~~~

Sơ đồ minh họa một khối; nếu `dkLen` lớn hơn độ dài đầu ra của PRF, PBKDF2 tiếp tục với `i = 2, 3...`.

**Không tự hiện thực vòng HMAC/XOR để đưa vào production.** Dùng thư viện KDF được duy trì và kiểm thử bằng các test vector/chuẩn tương thích. Chỉ một lỗi ở encoding password, bộ đếm khối, chiều dài hoặc lựa chọn PRF cũng có thể tạo ra khóa khác, khiến hệ thống không giải mã được dữ liệu cũ.

### Vì sao số vòng lặp làm chậm việc đoán?

Với `c = 1`, phép dẫn xuất gần với một bước PRF theo mỗi khối. Khi `c` tăng, việc kiểm tra từng password ứng viên buộc thực hiện thêm nhiều phép HMAC. Kẻ tấn công có thể chạy song song nhiều ứng viên bằng GPU/ASIC; **PBKDF2 không được thiết kế là memory-hard** nên không chống tối ưu phần cứng song song giống các hàm password hashing chuyên dụng tiêu thụ nhiều RAM.

Vì vậy, trong hệ thống mới mà thư viện và yêu cầu tuân thủ cho phép, thường nên **ưu tiên Argon2id**. PBKDF2 vẫn quan trọng đối với tính tương thích, các môi trường có yêu cầu tiêu chuẩn cụ thể và những hệ thống đã đầu tư vào chính sách KDF/kiểm toán.

## 4. Phân biệt PBKDF2 với SHA, HMAC, HKDF và Argon2id

| Cơ chế | Đầu vào chính | Dùng để làm gì? | Có phù hợp để lưu password trực tiếp? |
| --- | --- | --- | --- |
| **SHA-256** | Thông điệp | Hash tổng quát, thành phần mật mã | **Không**: quá nhanh khi dùng trực tiếp |
| **HMAC-SHA-256** | Secret key + thông điệp | MAC/xác thực thông điệp; PRF bên trong KDF | Không phải một quy trình password hashing hoàn chỉnh |
| **PBKDF2-HMAC-SHA-256** | Password + salt + iterations | Password verifier hoặc dẫn xuất khóa từ password | **Có**, với tham số và kiểm soát phù hợp |
| **Argon2id** | Password + salt + memory/time/parallelism | Password hashing hiện đại, memory-hard | Thường được ưu tiên cho hệ thống mới |
| **scrypt** | Password + salt + tham số memory/CPU | Password hashing, password-based KDF | Có, với tham số phù hợp |
| **bcrypt** | Password + salt + cost | Password verifier | Có, lưu ý giới hạn độ dài byte của mật khẩu theo triển khai |
| **HKDF** | Bí mật khóa có entropy cao/IKM + salt/info | Dẫn xuất nhiều khóa theo ngữ cảnh từ vật liệu khóa | **Không** thay PBKDF2/Argon2id cho password yếu |

**HMAC có thể là PRF bên trong PBKDF2**, nhưng gọi HMAC một lần trên mật khẩu không có nghĩa đã dùng PBKDF2. **HKDF** phù hợp khi đầu vào đã là bí mật có đủ entropy, ví dụ bí mật từ thỏa thuận (EC)DHE, và cần tách thành nhiều khóa; HKDF không thay việc làm chậm đoán mật khẩu.

### PBKDF2 không phải thuật toán mã hóa

PBKDF2 tạo byte khóa; nó **không có ciphertext, authentication tag hay thao tác giải mã**. Để mã hóa file bằng mật khẩu, ứng dụng cần:

1. Dẫn xuất **khóa AES** từ password bằng PBKDF2.
2. Mã hóa file bằng **AEAD** như AES-GCM với nonce duy nhất.
3. Lưu salt, thông số PBKDF2, nonce, ciphertext, tag và định dạng phiên bản.

Không được dùng một kết quả PBKDF2 vừa làm **password verifier công khai trong database**, vừa làm **khóa AES bí mật**: ai có verifier đó có thể đã có chính byte khóa để giải mã. Hãy **tách mục đích, salt/context và vật liệu đầu ra**, đồng thời đánh giá mô hình bảo vệ kỹ càng.

## 5. Dùng PBKDF2 để lưu password verifier

### 5.1. Đăng ký hoặc thay mật khẩu

~~~mermaid
flowchart TD
    P[Người dùng cung cấp password qua TLS] --> V[Chính sách password / input validation]
    V --> S[Tạo salt ngẫu nhiên riêng]
    S --> K[PBKDF2 với PRF, iterations, dkLen]
    K --> R[Verifier + algorithm + params + salt]
    R --> DB[(Kho xác thực)]
    K -.-> N[Không lưu plaintext password]
~~~

Ví dụ một bản ghi có cấu trúc **minh họa**:

~~~text
algorithm = PBKDF2-HMAC-SHA256
version = 1
iterations = <approved-cost>
salt = <base64-16-random-bytes>
dkLen = 32
verifier = <base64-derived-bytes>
~~~

**Không coi `verifier` là khóa có thể dùng cho mục đích khác**; nó là dữ liệu nhạy cảm vì cho phép kẻ tấn công tiến hành thử đoán ngoại tuyến nếu database bị lộ. Cần phân quyền, mã hóa kho lưu trữ khi phù hợp và giảm sao chép vào log/backup.

### 5.2. Xác minh khi đăng nhập

Ứng dụng tìm bản ghi của người dùng, đọc đúng `PRF`, `iterations`, `salt`, `dkLen`, rồi dẫn xuất từ password ứng viên. Sau đó so sánh với verifier đã lưu bằng cơ chế so sánh an toàn, chỉ cấp phiên đăng nhập sau khi toàn bộ xác thực và chính sách bổ sung đạt yêu cầu.

~~~text
candidatePassword
       |
       +--> PBKDF2(candidatePassword, storedSalt, storedParams)
       |                         |
       |                         v
       +------------------> candidateVerifier
                                 |
                   So sánh với storedVerifier
                                 |
                       true / false
~~~

Không cần và cũng không thể **giải mã** password verifier để lấy lại mật khẩu gốc. Nếu người dùng quên mật khẩu, quy trình an toàn là **reset** sau xác thực danh tính theo chính sách, không phải khôi phục password từ hash.

### 5.3. Tính hiện hành của tham số

Mỗi bản ghi nên mang thông tin phiên bản/thuật toán/chi phí để có thể xác minh password cũ và **nâng cấp sau lần đăng nhập hợp lệ**:

- Nếu `iterations` thấp hơn chính sách mới, rehash bằng password vừa xác minh và salt mới.
- Nếu đổi từ PBKDF2 sang Argon2id, dùng nhánh xác minh cũ đã kiểm soát, sau đó ghi verifier mới.
- Không đổi trường `iterations` của verifier cũ mà **không tính lại** giá trị dẫn xuất; làm vậy sẽ khiến người dùng không đăng nhập được.

Khi tham số KDF do dữ liệu lưu trữ quyết định, phải **giới hạn mức tối đa** để một bản ghi lỗi hoặc bị sửa không buộc server tính hàng tỷ vòng.

## 6. Ví dụ Java 17: PBKDF2-HMAC-SHA-256 cho password verifier

JDK 17 cung cấp `PBKDF2WithHmacSHA256` qua `SecretKeyFactory`, với `PBEKeySpec` biểu diễn password, salt, số vòng và độ dài đầu ra. Ví dụ sau minh họa tạo verifier và xác minh, lưu phiên bản và tham số, kiểm tra đầu vào và so sánh byte bằng `MessageDigest.isEqual`.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class Pbkdf2PasswordVerifier {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;

    // Giá trị minh họa; lựa chọn thực tế cần benchmark/chính sách hiện hành.
    private static final int CURRENT_ITERATIONS = 600_000;
    private static final int MAX_ACCEPTED_ITERATIONS = 5_000_000;

    private static byte[] derive(char[] password, byte[] salt, int rounds)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, rounds, KEY_BITS);
        try {
            return SecretKeyFactory.getInstance(ALGORITHM)
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    // Định dạng minh họa: pbkdf2-sha256$v1$rounds$salt$verifier
    static String create(char[] password) throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] verifier = derive(password, salt, CURRENT_ITERATIONS);
        try {
            return "pbkdf2-sha256$v1$" + CURRENT_ITERATIONS + "$"
                    + Base64.getEncoder().encodeToString(salt) + "$"
                    + Base64.getEncoder().encodeToString(verifier);
        } finally {
            Arrays.fill(verifier, (byte) 0);
        }
    }

    static boolean verify(char[] candidate, String stored)
            throws GeneralSecurityException {
        if (stored == null || stored.length() > 256) {
            return false;
        }
        String[] parts = stored.split("\\$", -1);
        if (parts.length != 5
                || !"pbkdf2-sha256".equals(parts[0])
                || !"v1".equals(parts[1])) {
            return false;
        }

        final int rounds;
        final byte[] salt;
        final byte[] expected;
        try {
            rounds = Integer.parseInt(parts[2]);
            if (rounds < 1 || rounds > MAX_ACCEPTED_ITERATIONS) {
                return false;
            }
            salt = Base64.getDecoder().decode(parts[3]);
            expected = Base64.getDecoder().decode(parts[4]);
            if (salt.length != SALT_BYTES || expected.length != KEY_BITS / 8) {
                return false;
            }
        } catch (IllegalArgumentException invalidRecord) {
            return false;
        }

        byte[] actual = derive(candidate, salt, rounds);
        try {
            return MessageDigest.isEqual(expected, actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "demo-only-password".toCharArray();
        char[] incorrect = "not-the-password".toCharArray();
        try {
            String record = create(password);
            System.out.println("Correct: " + verify(password, record));
            System.out.println("Incorrect: " + verify(incorrect, record));
            // Không log password, pepper hay verifier thực.
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(incorrect, '\0');
        }
    }
}
~~~

**Lưu ý:** code minh họa API, **không phải dịch vụ xác thực production hoàn chỉnh**. Chưa có chống brute-force trực tuyến, username enumeration, MFA, reset password, pepper, backpressure, transactional rehash hay kiểm soát toàn bộ vòng đời bộ nhớ. Đoạn `char[]` cho phép xóa một số bản sao do mã nguồn nắm giữ; chuỗi literal demo và nội bộ runtime Java vẫn có thể tạo bản sao không thể xóa hoàn toàn.

Đặc biệt, cách biến đổi **password ký tự thành byte** trong API password-based KDF phải được kiểm thử giữa các provider/hệ thống trước khi chuyển dữ liệu. Với password Unicode, cần chính sách encoding/normalization rõ ràng và tương thích; **không thay cách chuẩn hóa trong hệ thống đang chạy mà không có lộ trình chuyển đổi**.

## 7. Dùng PBKDF2 để dẫn xuất khóa mã hóa AES-GCM

Một ứng dụng sao lưu file bằng **passphrase người dùng** có thể dùng PBKDF2 để dẫn xuất **khóa AES-256**, rồi mã hóa bằng AES-GCM. Trong ví dụ dưới đây, **mỗi file có salt mới**, do đó mỗi lần mã hóa tạo khóa mới từ password và salt; đồng thời sinh IV/nonce 12 byte mới cho AES-GCM.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant App as Ứng dụng
    participant Store as Kho ciphertext
    U->>App: Nhập passphrase
    App->>App: Tạo salt mới và nonce mới
    App->>App: PBKDF2(passphrase, salt, cost) -> AES key
    App->>App: AES-GCM(key, nonce, plaintext, AAD)
    App->>Store: Lưu version, salt, cost, nonce, ciphertext + tag
    Store-->>App: Đọc payload để giải mã
    U->>App: Nhập lại passphrase
    App->>App: Dẫn xuất lại đúng AES key bằng params cũ
    App->>App: AES-GCM Open + kiểm tra tag và AAD
~~~

Các trường `salt`, `iterations`, `nonce` và phiên bản định dạng **không cần giữ bí mật**, nhưng cần có quy tắc **xác thực metadata**. Nếu attacker sửa tham số có chủ ý, hệ thống không được âm thầm hạ mức an toàn hoặc làm phát sinh workload quá lớn.

Ví dụ Java 17 bên dưới dùng lớp `PBEKeySpec`, `SecretKeySpec`, `GCMParameterSpec` và `Cipher`. Mỗi đối tượng trả về lưu salt, số vòng và nonce; AAD chứa metadata ở dạng nhị phân cố định để chống tráo đổi ngữ cảnh sau khi khóa đã được dẫn xuất:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

public class Pbkdf2FileEncryptionDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int SALT_BYTES = 16;
    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int ROUNDS = 600_000; // Chỉ minh họa.

    record Encrypted(int rounds, byte[] salt, byte[] iv,
                     byte[] ciphertextAndTag) {}

    private static byte[] keyFromPassword(
            char[] password, byte[] salt, int rounds) throws Exception {
        PBEKeySpec spec = new PBEKeySpec(password, salt, rounds, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    // AAD gắn định dạng + tham số vào bản mã, không mã hóa chúng.
    private static byte[] metadata(int rounds, byte[] salt, byte[] iv) {
        return ByteBuffer.allocate(1 + 4 + SALT_BYTES + IV_BYTES)
                .put((byte) 1).putInt(rounds).put(salt).put(iv).array();
    }

    static Encrypted encrypt(char[] password, byte[] plaintext)
            throws Exception {
        byte[] salt = new byte[SALT_BYTES];
        byte[] iv = new byte[IV_BYTES];
        RANDOM.nextBytes(salt);
        RANDOM.nextBytes(iv);

        byte[] rawKey = keyFromPassword(password, salt, ROUNDS);
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(rawKey, "AES"),
                    new GCMParameterSpec(TAG_BITS, iv));
            cipher.updateAAD(metadata(ROUNDS, salt, iv));
            byte[] encrypted = cipher.doFinal(plaintext);
            return new Encrypted(ROUNDS, salt, iv, encrypted);
        } finally {
            Arrays.fill(rawKey, (byte) 0);
        }
    }

    static byte[] decrypt(char[] password, Encrypted data)
            throws Exception {
        // Chặn metadata lỗi/chi phí vượt chính sách trước khi chạy KDF.
        if (data.salt().length != SALT_BYTES
                || data.iv().length != IV_BYTES
                || data.rounds() < 1 || data.rounds() > 5_000_000) {
            throw new IllegalArgumentException("Unsupported envelope");
        }
        byte[] rawKey = keyFromPassword(
                password, data.salt(), data.rounds());
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,
                    new SecretKeySpec(rawKey, "AES"),
                    new GCMParameterSpec(TAG_BITS, data.iv()));
            cipher.updateAAD(
                    metadata(data.rounds(), data.salt(), data.iv()));
            // Sai passphrase / ciphertext / tag / AAD -> lỗi xác thực.
            return cipher.doFinal(data.ciphertextAndTag());
        } finally {
            Arrays.fill(rawKey, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        char[] passphrase = "demo-passphrase-not-real".toCharArray();
        try {
            Encrypted file = encrypt(passphrase,
                    "File demo".getBytes(StandardCharsets.UTF_8));
            byte[] restored = decrypt(passphrase, file);
            System.out.println(new String(restored, StandardCharsets.UTF_8));
        } finally {
            Arrays.fill(passphrase, '\0');
        }
    }
}
~~~

**Giới hạn của ví dụ mã hóa:**

- Payload `Encrypted` là cấu trúc trong bộ nhớ, không phải định dạng file hoàn chỉnh. Khi lưu/truyền cần **serialize có version và giới hạn kích thước**, kiểm tra đầu vào, lưu ciphertext/tag đầy đủ và dùng cùng cách encode hai chiều.
- Với AES-GCM, **không bao giờ mã hóa hai lần dưới cùng cặp (key, nonce)**. Ví dụ tạo salt mới để có khóa mới mỗi đối tượng và tạo nonce mới; hệ thống thực cần chính sách tính duy nhất nonce xuyên instance/restart và hạn mức sử dụng khóa.
- **Sai passphrase** thường xuất hiện giống lỗi xác thực GCM; không công bố chi tiết nội bộ có thể tạo oracle. Cần thông báo lỗi an toàn và giới hạn số lượt thử khi có endpoint giải mã.
- Mặc dù metadata nằm trong AAD, độ dài và số vòng vẫn phải **kiểm tra trước** khi chạy PBKDF2. Không bao giờ để dữ liệu chưa tin cậy buộc hệ thống thực hiện công việc không giới hạn.
- File được mã hóa bằng password **vẫn có thể bị thử đoán ngoại tuyến** nếu attacker lấy ciphertext, salt và tag. Hãy dùng passphrase đủ mạnh; PBKDF2 không tạo ra entropy mới.
- Nếu mất passphrase mà không có cơ chế **recovery/escrow** được thiết kế trước, dữ liệu có thể không khôi phục được. Không lưu passphrase rõ trong log/config để “dễ phục hồi”.
- Nếu muốn mã hóa số lượng lớn dữ liệu server-side, thường hợp lý hơn khi dùng **DEK ngẫu nhiên + KMS bảo vệ KEK**, thay vì dùng một password con người làm nguồn khóa cho mọi bản ghi.

## 8. Tham số PBKDF2, hiệu năng và giới hạn bảo mật

**Không có một con số iterations duy nhất áp dụng tốt cho mọi hệ thống và mọi thời điểm.** Phương án lựa chọn phải xét chính sách/tiêu chuẩn đang áp dụng, khả năng tính toán máy chủ, nhu cầu đáp ứng, tải cao điểm và sức chịu đựng trước tấn công.

| Tiêu chí | Câu hỏi thiết kế | Thực hành |
| --- | --- | --- |
| **PRF** | SHA-256, SHA-512 hay cấu hình theo chuẩn? | Ghi rõ tên và kiểm thử tương thích với provider |
| **Iterations** | Mỗi lần đăng nhập chịu bao nhiêu chi phí? | Benchmark trên môi trường gần production; lưu version và cho phép rehash |
| **Salt** | Có đủ ngẫu nhiên, độc lập và riêng cho từng verifier không? | CSPRNG; 16 byte là ví dụ thông dụng, đối chiếu thư viện/chính sách |
| **Derived length** | Cần bao nhiêu byte cho mục đích cụ thể? | Ví dụ 32 byte cho khóa AES-256; tránh nhầm bit và byte |
| **Unicode** | Password được mã hóa/thực thi nhất quán không? | Xác định chính sách nhập/normalization, kiểm thử đa phiên bản |
| **DoS** | Input, record, rounds có thể bị thao túng không? | Giới hạn độ dài, iterations, số phiên tính KDF đồng thời |
| **Online guessing** | Có brute-force qua login API không? | Rate limit, giám sát, MFA/passkey khi thích hợp |
| **Offline guessing** | Nếu database/ciphertext lộ, mật khẩu có đủ mạnh không? | Password mạnh, KDF đủ chi phí, pepper nếu thiết kế cho phép |
| **Compliance** | Có yêu cầu FIPS hoặc quy định ngành không? | Kiểm tra thuật toán, provider và cấu hình **được phê duyệt trong môi trường cụ thể** |

Các giá trị `600_000` và `5_000_000` trong code là **minh họa**, không phải cam kết đáp ứng tiêu chuẩn bất kỳ. Tham số bảo mật có thể thay đổi theo năm và môi trường; cần lấy từ chính sách bảo mật hiện hành và đo hiệu năng thực tế.

### PBKDF2 có hạn chế gì trước GPU?

HMAC có thể được thực thi rất hiệu quả trên phần cứng song song. Tăng vòng lặp buộc attacker làm nhiều việc hơn nhưng không gây áp lực bộ nhớ lớn. **Argon2id** và **scrypt** bổ sung chi phí bộ nhớ, thường hữu ích khi đối thủ có khả năng chạy nhiều ứng viên song song.

Đối với hệ thống mới, nếu không bị giới hạn bởi quy định hoặc khả năng thư viện, **Argon2id thường là lựa chọn ưu tiên cho password hashing**. Nếu phải dùng PBKDF2, cần parameter tuning cẩn thận và kiểm soát xác thực trực tuyến nhiều lớp.

## 9. PBKDF2 liên quan KMS/HSM, pepper và envelope encryption thế nào?

PBKDF2 xử lý **đầu vào là password/passphrase**. KMS/HSM thường quản lý **khóa mật mã có entropy cao**, chính sách sử dụng và hoạt động ký/giải mã/bọc khóa. Hai nhóm chức năng bổ sung cho nhau nhưng **không tự thay thế nhau**.

### 9.1. Pepper trong password hashing

**Pepper** là bí mật bổ sung (khác salt) được lưu ngoài database verifier, ví dụ secret manager hoặc KMS/HSM khi phù hợp. Thiết kế có thể sử dụng một bước MAC có khóa hay sơ đồ được đánh giá để kết hợp bí mật đó, nhưng phải xác định rõ mục đích, tương thích và khả năng rotation.

| Đặc tính | Salt PBKDF2 | Pepper |
| --- | --- | --- |
| Có bí mật? | Không | Có |
| Có nên lưu cùng verifier? | Có thể | Không |
| Có riêng từng tài khoản? | Thường có | Thường do ứng dụng/miền bảo mật quản lý |
| Có vai trò chống bảng hash dùng chung? | Có | Có thể nâng chi phí khi chỉ database lộ |
| Ai cấp quyền? | Kho dữ liệu xác thực | IAM/KMS/secret store tùy kiến trúc |

**Pepper không thay thế salt, iterations, passphrase mạnh hoặc rate limiting.** Nếu KMS/HSM cung cấp API HMAC, có thể xây dựng kiến trúc sử dụng pepper mà không xuất raw pepper khỏi vùng bảo vệ, tùy nhà cung cấp. Không giả định mọi KMS hỗ trợ trực tiếp PBKDF2/Argon2id.

### 9.2. Password-derived key và DEK/KEK

Hệ thống lưu trữ dữ liệu nhạy cảm thường sinh **DEK (Data Encryption Key)** ngẫu nhiên, mã hóa bằng AES-GCM rồi dùng **KEK (Key Encryption Key)** do KMS quản lý để bọc DEK. Đây là **envelope encryption**.

Trong một ứng dụng mã hóa file bằng passphrase, PBKDF2 có thể dẫn xuất **password-derived KEK** để bọc một DEK ngẫu nhiên. Cách này giúp **thay passphrase bằng cách rewrap DEK** mà không nhất thiết mã hóa lại toàn file, nếu format và giao thức đã được thiết kế đúng. Nhưng **mật khẩu yếu vẫn cho phép thử đoán ngoại tuyến đối với wrapped DEK**; dùng DEK ngẫu nhiên không tự sửa được điều đó.

~~~mermaid
flowchart LR
    P[Passphrase] --> KDF[PBKDF2 + salt + iterations]
    KDF --> PKEK[Password-derived wrapping key]
    DEK[DEK ngẫu nhiên] --> AEAD[AEAD mã hóa nội dung]
    AEAD --> CT[(Ciphertext + tag)]
    DEK --> Wrap[AEAD/key wrap được phê duyệt]
    PKEK --> Wrap
    Wrap --> WDEK[(Wrapped DEK + KDF metadata)]
    IAM[Quyền, audit và recovery policy] --> CT
    IAM --> WDEK
~~~

**Không gửi khóa AES/DEK dạng rõ vào log, cơ sở dữ liệu ứng dụng hoặc email.** Nếu dùng KMS, xác minh quyền `Encrypt/Decrypt/GenerateDataKey/Sign` theo API hỗ trợ, tách quyền quản trị với quyền sử dụng khóa và audit các thao tác nhạy cảm.

## 10. Vòng đời, rotation và migration của PBKDF2

PBKDF2 liên quan đến vòng đời bảo vệ password và khóa, nhưng từng trường hợp có cách nâng cấp khác nhau.

### 10.1. Nâng cấp password verifier

Khi phát hiện `iterations` cũ không còn đủ mạnh hoặc muốn chuyển PBKDF2 sang Argon2id:

1. Giữ khả năng **đọc metadata và xác minh các bản ghi cũ** trong nhánh có kiểm soát.
2. Khi người dùng đăng nhập thành công, dùng password **vừa được cung cấp** để tạo verifier mới với salt và tham số mới.
3. Cập nhật bản ghi nhất quán, xóa vật liệu tạm trong khả năng runtime và audit kết quả.
4. Với tài khoản không hoạt động lâu hoặc trong sự cố rò rỉ, thực hiện **reset password** theo chính sách.
5. Khi hết phụ thuộc, loại bỏ thuật toán cũ khỏi luồng xác minh.

**Không thể thường xuyên nâng verifier cũ mà không biết password gốc**: từ DK cũ không suy ngược được password để tính PBKDF2 mới theo salt mới. Đừng tăng riêng trường iterations trong database và coi như hash đã mạnh hơn.

### 10.2. Thay password của file mã hóa

Nếu mật khẩu trực tiếp dẫn xuất DEK trong mô hình đơn giản, thay password có thể đòi hỏi **giải mã rồi mã hóa lại dữ liệu** bằng khóa mới. Nếu thiết kế sử dụng DEK ngẫu nhiên riêng và khóa từ PBKDF2 để **bọc DEK**, có thể **rewrap** bằng khóa dẫn xuất từ password mới khi còn quyền lấy DEK.

Lưu **version của KDF, PRF, salt, iterations, dkLen và cơ chế bọc** trong metadata có xác thực; cần diễn tập khôi phục backup cũ trước khi vô hiệu hóa đường dẫn cũ. Nếu làm mất passphrase và không có recovery path, không có kỹ thuật "đảo PBKDF2" để khôi phục bí mật.

### 10.3. Khi database hoặc pepper bị lộ

- **Lộ verifier và salt:** đối thủ có thể thử đoán password ngoại tuyến; cần đánh giá mức mạnh, tham số, phạm vi tài khoản, phát hiện lạm dụng và chính sách reset.
- **Lộ pepper:** phải đánh giá thiết kế cách dùng pepper, khả năng xác minh verifier cũ, kế hoạch chuyển secret và thông báo sự cố; không chỉ đổi tên key alias.
- **Lộ file mã hóa theo passphrase:** attacker có thể thử đoán offline; phải xử lý rủi ro password yếu và các bản sao ciphertext đã bị thu thập.
- **Lộ DEK/KEK:** không phải chỉ tăng số vòng PBKDF2 là đủ; cần thu hồi quyền, chuyển khóa và re-encrypt/rewrap theo phạm vi lộ.

Mỗi lần thay chính sách nên ghi **ai phê duyệt, phiên bản cấu hình, dữ liệu/phần mềm chịu ảnh hưởng, lịch triển khai và kết quả kiểm tra backup**.

## 11. Lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng một lần SHA-256(password) thay PBKDF2 | Đoán mật khẩu ngoại tuyến nhanh | Dùng password hashing chuyên dụng với salt/chi phí phù hợp |
| Dùng salt cố định hoặc username làm salt | Cùng password có thể cho kết quả giống nhau; dễ dùng bảng tính trước | Salt ngẫu nhiên riêng bằng CSPRNG |
| Nghĩ rằng PBKDF2 biến password yếu thành khóa 256-bit không thể đoán | Đánh giá sai entropy nguồn | Yêu cầu passphrase mạnh và bảo vệ nhiều lớp |
| Đánh đồng iteration count với cryptoperiod | Khóa tồn tại/được dùng sai thời hạn | Quản lý vòng đời riêng, tham số KDF riêng |
| Dùng một DK vừa làm verifier vừa làm khóa AES | Lộ verifier có thể làm lộ khóa dữ liệu | Tách mục đích, ngữ cảnh/salt và vật liệu khóa |
| Không ghi PRF, iterations, salt, dkLen | Không thể xác minh/giải mã sau nâng cấp | Lưu metadata định dạng có version |
| Chấp nhận rounds cực lớn từ record/file không tin cậy | CPU DoS | Giới hạn tham số trước khi chạy KDF |
| Coi KDF là thuật toán mã hóa | Không có confidentiality/tag | Kết hợp AEAD và quản lý nonce/AAD |
| AES-GCM tái dùng nonce dưới cùng DK | Có thể phá bí mật và xác thực | Bảo đảm duy nhất (key, nonce), kiểm soát counter/rotation |
| Dùng password hash làm HMAC key hoặc JWT signing key | Một bí mật bị dùng sai mục đích; mở rộng phạm vi ảnh hưởng | Dùng secret key ngẫu nhiên riêng, quản lý bằng KMS/HSM |
| Thay iterations nhưng không rehash | Người dùng bị khóa khỏi tài khoản | Rehash từ password hợp lệ hoặc reset |
| Không giới hạn login rate | Tấn công online brute-force và DoS | Rate limiting, MFA, phát hiện bất thường |
| Tùy ý chuẩn hóa Unicode khi nâng cấp | Cùng password người dùng không còn tạo cùng DK | Chốt chính sách encoding/normalization và kiểm thử migration |
| Ghi password, DK hoặc pepper vào log | Rò rỉ bí mật ngoài kho chính | Chặn log nhạy cảm, kiểm soát dump/trace |

## 12. Tình huống thực tế: hệ thống vừa xác thực người dùng vừa lưu backup mã hóa

Một nền tảng quản lý tài liệu có hai nhu cầu:

1. Người dùng **đăng nhập bằng mật khẩu**.
2. Người dùng có thể **xuất bản sao lưu được bảo vệ bằng passphrase riêng**.

Nếu cả hai nghiệp vụ dùng PBKDF2, đó vẫn là **hai miền bảo mật khác nhau**.

**Đối với đăng nhập:** hệ thống lưu verifier `PBKDF2-HMAC-SHA256` theo salt riêng và tham số hiện hành. Khi người dùng gửi password qua TLS, server tính lại giá trị để so sánh, kiểm tra MFA/trạng thái tài khoản và cấp session nếu được phép. Không lấy verifier lưu sẵn làm secret key để mã hóa dữ liệu.

**Đối với backup:** ứng dụng sinh salt mới cho mỗi file, dẫn xuất khóa từ **passphrase backup** (khuyến khích phân biệt với password đăng nhập) và mã hóa file bằng AES-GCM với nonce riêng. Metadata nêu rõ phiên bản định dạng, PRF, iterations, salt và nonce để khôi phục. Nếu mất passphrase, kế hoạch recovery phải được xác định từ trước.

**Đối với dữ liệu ứng dụng lưu trên server:** các DEK ngẫu nhiên có thể được bọc bằng KEK trong KMS/HSM; không phụ thuộc một password người dùng để giải mã mọi bản ghi. Khi một người dùng bị khóa tài khoản, hệ thống vẫn cần tuân thủ chính sách retention/khôi phục dữ liệu nghiệp vụ mà không phát tán password gốc.

**Khi database verifier bị lộ:** tăng iterations cho bản ghi mới và dời dần người dùng cũ sang verifier mạnh hơn chỉ giải quyết **rủi ro tương lai**. Các verifier cũ đã bị lấy vẫn có thể bị tấn công ngoại tuyến; cần phân tích tác động và thực hiện quy trình ứng phó sự cố.

**Khi backup mã hóa bị đánh cắp:** đối thủ có thể dùng salt và ciphertext để thử passphrase offline. AES-GCM có xác thực không giúp che giấu việc passphrase đúng/sai khỏi attacker có dữ liệu; KDF chỉ tăng chi phí thử mỗi ứng viên.

## 13. Checklist triển khai PBKDF2

- [ ] Đã xác định PBKDF2 dùng để tạo **password verifier** hay **khóa mã hóa**?
- [ ] PRF được chỉ rõ (ví dụ HMAC-SHA-256), độ dài DK đúng đơn vị bit/byte?
- [ ] Sinh **salt ngẫu nhiên riêng** bằng CSPRNG cho từng bản ghi/file cần thiết?
- [ ] Có phiên bản định dạng, salt, iterations, PRF và dkLen đủ để xác minh/giải mã cũ?
- [ ] Iterations được lựa chọn theo chính sách hiện hành và đo hiệu năng tải cao điểm?
- [ ] Có giới hạn rounds và kích thước input để tránh KDF DoS?
- [ ] Không dùng PBKDF2 thay AES-GCM/ChaCha20-Poly1305 hay dùng DK cho nhiều mục đích?
- [ ] Với AES-GCM, nonce duy nhất theo key; metadata/AAD được bảo vệ và xác minh?
- [ ] Password không bị ghi log; password/copy/derived key được loại bỏ sớm trong khả năng của runtime?
- [ ] Có chính sách Unicode và kiểm thử tương thích JDK/provider/library?
- [ ] Hệ thống login có rate limiting, chống enumeration, MFA/passkey khi cần?
- [ ] Có lộ trình rehash sau đăng nhập, nâng thuật toán hoặc reset password?
- [ ] Nếu dùng pepper, nó nằm ngoài database và có IAM/KMS/rotation/audit đúng quy trình?
- [ ] Các DEK/KEK và khóa HMAC/chữ ký số khác không bị dùng lẫn với password verifier?
- [ ] Đã diễn tập giải mã backup cũ, khôi phục khi rotation và xử lý sự cố lộ password/key?

## 14. Câu hỏi tự kiểm tra

**1. PBKDF2 có phải thuật toán mã hóa không?**  
Không. PBKDF2 là KDF từ mật khẩu; muốn mã hóa dữ liệu cần thuật toán như AES-GCM với key/nonce/AAD phù hợp.

**2. Vì sao PBKDF2 cần salt nếu salt không bí mật?**  
Salt tạo sự khác biệt giữa các bản ghi, ngăn dùng chung bảng hash tính trước và giảm khả năng nhận biết nhiều người có cùng mật khẩu. Nó không tự ngăn thử đoán riêng từng bản ghi.

**3. Iterations càng lớn có luôn tốt hơn không?**  
Không đơn giản. Tăng iterations làm chậm đoán offline nhưng cũng tăng thời gian xác minh và nguy cơ CPU DoS. Cần chọn theo chính sách, tải và benchmark.

**4. Nếu PBKDF2 tạo ra 32 byte thì có thể coi password đầu vào mạnh như AES-256 không?**  
Không. Độ khó đoán của khóa dẫn xuất vẫn bị giới hạn bởi entropy của password và khả năng đoán offline, dù đầu ra dài 256 bit.

**5. PBKDF2 khác HKDF như thế nào?**  
PBKDF2 được thiết kế cho password có entropy thấp và có chi phí lặp; HKDF thường dẫn xuất khóa từ vật liệu khóa đã có entropy cao với mục tiêu tách ngữ cảnh/khóa.

**6. Khi đổi 600.000 lên số vòng lớn hơn, có được sửa trường iterations trong DB không?**  
Không. Phải tính lại verifier từ password ứng viên đúng và salt/tham số mới, thường sau lần đăng nhập hợp lệ.

**7. Vì sao không dùng cùng output PBKDF2 làm password verifier và khóa AES?**  
Vì verifier lưu ở nơi có thể lộ; nếu cũng là raw AES key, người lấy được verifier có thể giải mã dữ liệu. Phải tách khóa theo mục đích.

**8. PBKDF2 có tự bảo vệ trước máy có GPU mạnh bằng Argon2id không?**  
Không. PBKDF2 chủ yếu tăng chi phí tính toán; nó không memory-hard như Argon2id. Lựa chọn dựa vào thư viện, rủi ro và yêu cầu tuân thủ.

## Ghi nhớ

**PBKDF2 là hàm dẫn xuất khóa từ mật khẩu, dùng salt và số vòng lặp PRF (thường HMAC-SHA-256) để tăng chi phí thử đoán từng password.** PBKDF2 có thể tạo **password verifier** hoặc **khóa cho mã hóa dựa trên passphrase**, nhưng không tự mã hóa dữ liệu, không tạo thêm entropy và không thay thế quản lý khóa. Thiết kế an toàn phải bảo đảm **salt riêng, tham số được lưu và giới hạn, tách mục đích sử dụng, AEAD đúng cách, kiểm soát quyền, bảo vệ pepper nếu có, chiến lược rehash/rotation và khả năng khôi phục**. Khi phù hợp, hãy cân nhắc **Argon2id** cho password hashing mới; dùng **KMS/HSM và envelope encryption** để quản lý DEK/KEK có entropy cao trong hệ thống bảo vệ dữ liệu.
