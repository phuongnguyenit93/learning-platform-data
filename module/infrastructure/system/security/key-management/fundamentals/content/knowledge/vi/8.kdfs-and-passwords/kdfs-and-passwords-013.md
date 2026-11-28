# Xóa secret trung gian khỏi memory: Giảm thời gian tồn tại của key material

Một dịch vụ Java nhận mật khẩu, thực hiện KDF để tạo khóa, sau đó dùng khóa đó mã hóa dữ liệu bằng AES-GCM. Dịch vụ đã lưu bản mã an toàn, không ghi khóa vào database và đã hoàn tất tác vụ. Nhưng **mật khẩu, input keying material, khóa trung gian và những bản sao của chúng có thể vẫn còn trong bộ nhớ tiến trình**. Nếu ứng dụng bị đọc bộ nhớ, xuất heap dump hoặc ghi lại secret trong diagnostic log, bảo vệ ở tầng lưu trữ không còn đủ.

**Xóa secret trung gian khỏi memory** là thực hành **giới hạn thời gian sống của dữ liệu bí mật** và **xóa những vùng nhớ có thể kiểm soát ngay khi không còn cần sử dụng**. Trong Java, việc ghi đè các mảng **byte[]** hoặc **char[]** bằng số 0 là một biện pháp *best effort*, **không phải cam kết rằng toàn bộ bản sao đã biến mất khỏi heap, native memory, register, swap hoặc hệ thống ghi log**.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, nguyên tắc này gắn với vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy**. Khi thiết kế với KDF, mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM và envelope encryption, cần xác định đâu là key material thực sự, ai được phép sử dụng và secret có thể đi qua những miền bộ nhớ nào.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện secret gốc, secret trung gian và bản sao nhạy cảm trong một luồng KDF hoặc giải mã.
2. Giải thích giới hạn của **garbage collection (GC)**, **Arrays.fill**, **String**, **SecretKeySpec** và **PBEKeySpec.clearPassword**.
3. Viết mã Java có **phạm vi sống ngắn**, xử lý ngoại lệ bằng **try/finally** và xóa các byte/char do mình sở hữu.
4. Phân biệt xóa bộ nhớ trong tiến trình với **crypto-erasure**, hủy khóa trong KMS/HSM và thu hồi quyền truy cập.
5. Thiết kế các lớp phòng vệ cho heap dump, crash dump, swap, buffer pool, cache, log và quyền gọi API mật mã.
6. Đánh giá một quy trình KDF/HKDF hoặc envelope encryption để giảm nơi xuất hiện key material bản rõ.

## 2. Secret trung gian là gì?

Không chỉ private key hoặc mật khẩu mới cần bảo vệ. Những byte tồn tại **giữa các bước** của một giao thức cũng có thể đủ để kẻ tấn công giải mã dữ liệu hoặc tạo giá trị xác thực giả.

| Thành phần | Ví dụ | Mức độ nhạy cảm và thời gian sống |
|---|---|---|
| **Mật khẩu đầu vào** | char[] nhận từ giao diện đăng nhập | Bí mật; giữ ngắn nhất có thể cho password hashing và xác thực |
| **IKM – Input Keying Material** | Shared secret ECDH hoặc seed ngẫu nhiên từ KMS | Bí mật; chỉ các bước được cấp phép mới được xử lý |
| **PRK – Pseudorandom Key** | Đầu ra của HKDF-Extract | Key material trung gian; nên hủy bản sao ứng dụng sau khi Expand |
| **OKM – Output Keying Material** | AES key hoặc HMAC key từ HKDF-Expand | Khóa dẫn xuất; vòng đời phụ thuộc tác vụ và policy |
| **DEK bản rõ** | Khóa AES được KMS trả tạm thời | Bí mật; tránh lưu lâu và không log |
| **Khóa phiên/tạm thời** | Secret từ ECDH hoặc khóa AEAD một phiên | Bí mật; xóa sau khi phiên kết thúc theo giao thức |
| **Private-key material** | RSA private exponent, EC scalar, Ed25519 seed | Bí mật; ưu tiên không cho ứng dụng xuất byte thô |
| **Plaintext nhạy cảm** | Hồ sơ khách hàng sau giải mã | Không phải key material nhưng vẫn có giá trị cao với đối thủ đọc memory |
| **Salt, nonce, key ID** | Salt HKDF, IV GCM, key version | Thông thường không cần giữ bí mật; vẫn cần chính xác và bảo vệ tính toàn vẹn |
| **Wrapped DEK** | DEK được mã hóa bằng KEK | Key material đã được bảo vệ; không thể coi là hoàn toàn vô hại |

**Không phải dữ liệu nào xuất hiện trong phép toán mật mã cũng cần zeroize**. Salt, nonce và public key thông thường có thể công khai. Tập trung vào **bí mật đầu vào, khóa phát sinh, những bản sao chứa plaintext và các buffer trung gian nhạy cảm**; việc xóa metadata công khai không giúp giải quyết nguy cơ chính.

### 2.1. Một luồng HKDF có thể tạo nhiều bản sao

~~~mermaid
flowchart TD
    I["IKM / shared secret"] --> E["HKDF-Extract"]
    S["Salt (thường không bí mật)"] --> E
    E --> P["PRK (bí mật)"]
    P --> X["HKDF-Expand với info"]
    X --> K1["OKM cho AES-GCM"]
    X --> K2["OKM cho HMAC"]
    K1 --> A["JCA Cipher / SecretKeySpec"]
    K2 --> M["JCA Mac / SecretKeySpec"]
    A --> C["Ciphertext + tag"]
    M --> T["MAC tag"]
    I -.-> Z["Xóa bản sao mình kiểm soát khi hết nhu cầu"]
    P -.-> Z
    K1 -.-> Z
    K2 -.-> Z
~~~

Trong luồng này, **PRK** nên tồn tại đủ lâu để dẫn xuất các khóa con được yêu cầu, rồi được xóa khỏi mảng do ứng dụng quản lý. Các **OKM** được xóa sau khi hoàn thành thao tác dùng khóa. Nhưng một provider Java có thể **sao chép key bytes vào cấu trúc riêng**, nên việc xóa mảng gốc không chứng minh được toàn bộ key material trong tiến trình đã bị hủy.

## 3. Mô hình đe dọa: Xóa memory bảo vệ trước điều gì?

| Nguy cơ | Zeroization hỗ trợ tới đâu? | Phòng vệ bổ sung |
|---|---|---|
| **Đọc heap dump sau khi tác vụ kết thúc** | Có thể giảm số bản sao còn tìm được nếu đã ghi đè được vùng nhớ | Tắt/giới hạn heap dump production, phân quyền và bảo vệ dump |
| **Crash dump chứa secret** | Giảm cơ hội secret còn trong vùng kiểm soát, không chắc chắn | Kiểm soát crash/core dump, mã hóa nơi lưu và retention |
| **Quét heap trong lúc khóa còn được dùng** | Không chặn được vì secret phải có mặt cho thao tác | Giảm scope, IAM, cô lập tiến trình và hạn chế exposure |
| **Đọc native/off-heap memory** | Arrays.fill trên Java heap không tác động vùng native khác | Buffer có cơ chế hủy chuyên biệt, provider/HSM phù hợp |
| **Secret bị ghi vào log/trace** | Xóa RAM không thu hồi được bản đã log | Redaction, secret scanning, policy log và hạn chế telemetry |
| **Snapshot/swap/page file** | Không đảm bảo bản sao đã ghi xuống đĩa được xóa | Cấu hình OS/hypervisor phù hợp, mã hóa swap/disk, hardening |
| **Tài khoản có quyền KMS Decrypt/Sign** | Không ngăn được thao tác API hợp lệ nhưng bị lạm dụng | Least privilege, workload identity, kiểm soát purpose, audit |
| **Khóa đã bị sao chép ra ngoài trước khi xóa** | Không thu hồi được bản sao đối thủ đã giữ | Rotate, re-encrypt, revoke và ứng phó sự cố |

**Mục tiêu hợp lý:** giảm số bản sao secret, giảm thời gian có thể bị phát hiện khi thu thập memory *sau* tác vụ, và giảm hệ quả của lỗi vận hành. **Không phải mục tiêu có thể bảo đảm chỉ bằng Java:** ngăn một đối thủ toàn quyền đọc bộ nhớ của tiến trình đang hoạt động hoặc bảo đảm không còn bất kỳ bản sao nào trong hệ thống.

## 4. Vì sao GC không đồng nghĩa xóa secret?

**Garbage collector** quản lý bộ nhớ của các object không còn được tham chiếu. Nó **không đưa ra hợp đồng bảo mật** rằng các byte của object bị thu hồi sẽ được ghi đè ngay lập tức, cũng không hứa tất cả bản sao phát sinh do di chuyển/biên dịch tối ưu đã được xóa.

~~~text
Object chứa DEK được tạo
        |
DEK được đưa vào API Cipher hoặc SecretKeySpec
        |
Object ban đầu hết reference
        |
GC có thể thu hồi vùng nhớ khi thích hợp
        |
KHÔNG có bảo đảm tất cả bản sao key bytes được zeroize
~~~

Gọi **System.gc()** không phải phương pháp xóa khóa. Nó chỉ là yêu cầu gợi ý cho runtime và không cung cấp kiểm chứng nào về zeroization của key material. Việc gán **secret = null** chỉ bỏ một tham chiếu; bản thân thao tác ấy không ghi đè dữ liệu.

### 4.1. String là lựa chọn rủi ro cho secret

**String** bất biến (*immutable*) theo API Java: ứng dụng không có thao tác sửa các byte/ký tự bên trong nó theo cách được bảo đảm. Một mật khẩu bị biến thành String có thể tồn tại trong heap cho đến khi GC và có thể xuất hiện ở bản sao hoặc diagnostic.

Không nên:

~~~java
String password = request.getParameter("password");
byte[] secret = password.getBytes(java.nio.charset.StandardCharsets.UTF_8);
// Không có cách tin cậy để xóa password String đã tạo.
~~~

Ở các API không tránh được String (ví dụ một số giao diện framework), phải **ghi nhận giới hạn bảo mật**, tránh nhân bản, log, cache, đưa vào exception và rút ngắn thời gian sống. Đối với dữ liệu nhập mật khẩu mà API cho phép, ưu tiên **char[]** hoặc vùng byte có thể ghi đè và tránh chuyển qua String.

### 4.2. byte[] và char[] tốt hơn ở điểm nào?

Với một mảng do ứng dụng trực tiếp sở hữu:

~~~java
byte[] intermediateSecret = obtainSecretBytes();
try {
    useSecret(intermediateSecret);
} finally {
    java.util.Arrays.fill(intermediateSecret, (byte) 0);
}
~~~

**Arrays.fill** ghi đè **những phần tử của chính mảng đó**, tạo điều kiện xóa sớm hơn thời điểm GC. Tuy nhiên:

1. Mảng có thể đã được **copy**, chuyển thành String, bao trong object khác hoặc lưu vào buffer khác.
2. Compiler/JIT, runtime, provider và cơ chế thu gom bộ nhớ **không cam kết bảo mật zeroization xuyên mọi bản sao**; không coi thao tác thông thường là secure erase đã được chứng minh.
3. Nếu đã truyền secret vào API, việc xóa mảng của ứng dụng **không nhất thiết xóa bản sao bên trong thư viện**.
4. Trong lúc thực hiện phép toán, dữ liệu vẫn có thể tồn tại ở register, stack frame, native memory hoặc nơi khác.
5. Một thread khác có thể đã đọc, snapshot hoặc giữ bản sao trước khi xóa.

Vì vậy cần kết hợp **sở hữu dữ liệu rõ ràng, hạn chế sao chép, try/finally, thư viện bảo vệ secret phù hợp và chính sách môi trường**.

## 5. Những API Java dễ tạo bản sao bí mật

| Cấu trúc/API | Điều nên biết | Cách giảm rủi ro |
|---|---|---|
| **byte[]** | Có thể sửa bằng Arrays.fill; reference và alias vẫn cần kiểm soát | Cố gắng chỉ một owner; xóa trong finally |
| **char[]** | Có thể ghi đè mật khẩu sau sử dụng | Đừng chuyển không cần thiết sang String |
| **String** | Bất biến; không có API xóa nội dung đáng tin cậy | Tránh dùng cho secret nếu API cho phép |
| **SecretKeySpec** | Có thể giữ bản sao key bytes bên trong object; xóa mảng truyền vào không đồng nghĩa xóa object | Giới hạn scope, dùng provider có cơ chế quản lý/hủy khóa rõ ràng |
| **Key.getEncoded()** | Có thể trả về **bản sao key material** nếu key được phép export | Hạn chế gọi; xóa byte[] trả về khi hết sử dụng |
| **PBEKeySpec** | Có thể sở hữu bản sao mật khẩu riêng; hỗ trợ **clearPassword()** | Gọi clearPassword trong finally và xóa mảng password do caller sở hữu |
| **SecretKeyFactory/Signature/Mac/Cipher** | Provider có thể giữ state hoặc sao chép khóa trong heap/native | Tuân thủ provider contract; không giả định hủy mảng gốc sẽ hủy state |
| **ByteBuffer (heap/direct)** | Có thể có backing memory, slice hoặc vùng native; zeroize không đồng nghĩa mọi view/copy được xóa | Sở hữu vùng nhớ rõ ràng; dùng API cleanup của thư viện/native phù hợp |
| **ByteArrayOutputStream** | Tạo buffer bên trong rồi có thể copy khi toByteArray() | Không dùng bừa để tích lũy secret; nếu bắt buộc, đánh giá vùng nhớ nội bộ |
| **ThreadLocal, pool, cache** | Reference sống lâu hoặc buffer được tái sử dụng | Không cache secret ngoài yêu cầu; xóa entry, wipe vùng dùng xong |
| **JNI/native/OpenSSL binding** | Secret có thể nằm ngoài Java heap và bị sao chép | Dùng secure-memory API được hỗ trợ, quản lý vòng đời native chính xác |

### 5.1. PBEKeySpec.clearPassword giải quyết một phần

**PBEKeySpec** dùng trong một số API PBKDF2. Nếu caller tạo char[] mật khẩu, constructor có thể tạo **bản sao** để lưu ở object spec. **clearPassword()** giúp xóa bản sao do spec quản lý, nhưng **không tự xóa char[] của caller**, không xóa bản sao của thư viện khác và không xử lý mọi dạng secret ngoài memory.

~~~java
char[] password = readPasswordAsChars();
javax.crypto.spec.PBEKeySpec spec = null;
try {
    spec = new javax.crypto.spec.PBEKeySpec(
            password, publicSalt, configuredIterations, 256);
    // Chỉ dùng cơ chế/password KDF theo policy của hệ thống.
    consumePasswordSpec(spec);
} finally {
    if (spec != null) {
        spec.clearPassword();
    }
    java.util.Arrays.fill(password, '\0');
}
~~~

Đây là **đoạn pseudocode Java có các hàm và biến ứng dụng giả định**, không phải chương trình độc lập. **publicSalt** không cần zeroize vì nó thông thường không bí mật; còn derived password key/verifier cần được quản lý theo mục đích sử dụng. Với password storage nên ưu tiên **Argon2id** khi nền tảng/chính sách phù hợp, hoặc scrypt/PBKDF2 theo yêu cầu; **HKDF không thay thế password hashing có work factor**.

### 5.2. Destroyable có phải giải pháp chung?

Một số đối tượng key/provider hỗ trợ giao diện hoặc phương thức **destroy()** theo contract riêng. Việc nó có được gọi, được hỗ trợ và thực sự xóa những bản sao nào **phụ thuộc implementation/provider**. Không coi mọi **SecretKey**, **PrivateKey** hoặc **SecretKeySpec** là một secure-memory object chỉ vì interface cung cấp phương thức liên quan đến hủy khóa.

Với yêu cầu assurance cao, cần **đọc contract, đánh giá implementation, kiểm thử hành vi phù hợp** và cân nhắc giữ secret trong HSM hoặc môi trường cô lập nơi ứng dụng chỉ dùng **key handle**.

## 6. Mẫu Java 17: Xóa IKM, PRK và OKM bằng try/finally

Ví dụ sau tạo **IKM** ngẫu nhiên, dùng **HKDF-HMAC-SHA-256** để dẫn xuất một khóa AES-256, rồi thực hiện một phép mã hóa AES-GCM duy nhất. Sau đó các mảng chứa secret do ứng dụng sở hữu được ghi đè trong **finally**, kể cả khi thao tác gặp lỗi.

**Giới hạn quan trọng:** đây là **best-effort cleanup**, không phải một cơ chế **secure zeroization được chứng minh** trong JVM. Mac, Cipher và SecretKeySpec có thể có state/bản sao riêng mà ứng dụng không xóa được bằng các lệnh Arrays.fill ở ví dụ.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class IntermediateSecretCleanupDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String HMAC_ALG = "HmacSHA256";
    private static final int HASH_LEN = 32;

    private static void wipe(byte[] bytes) {
        if (bytes != null) {
            Arrays.fill(bytes, (byte) 0);
        }
    }

    // HKDF-Extract của RFC 5869.
    private static byte[] extract(byte[] salt, byte[] ikm)
            throws Exception {
        Mac hmac = Mac.getInstance(HMAC_ALG);
        hmac.init(new SecretKeySpec(salt, HMAC_ALG));
        return hmac.doFinal(ikm);
    }

    // HKDF-Expand; ví dụ chỉ cần một block tối đa 32 byte.
    private static byte[] expandOneBlock(
            byte[] prk, byte[] info, int length) throws Exception {
        if (length <= 0 || length > HASH_LEN) {
            throw new IllegalArgumentException("Expected 1..32 bytes");
        }
        Mac hmac = Mac.getInstance(HMAC_ALG);
        hmac.init(new SecretKeySpec(prk, HMAC_ALG));
        hmac.update(info);
        hmac.update((byte) 1); // T(1) = HMAC(PRK, info || 0x01)
        byte[] block = hmac.doFinal();
        try {
            return Arrays.copyOf(block, length);
        } finally {
            wipe(block);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] ikm = new byte[32];
        byte[] salt = new byte[32]; // Salt HKDF thường không bí mật
        RANDOM.nextBytes(ikm);
        RANDOM.nextBytes(salt);

        byte[] prk = null;
        byte[] aesKeyBytes = null;
        byte[] plaintext = null;
        byte[] recovered = null;
        byte[] ciphertextWithTag = null;

        try {
            prk = extract(salt, ikm);
            byte[] info = "app-v1/tenant-42/DATA_ENCRYPTION/AES-256-GCM"
                    .getBytes(StandardCharsets.UTF_8);
            aesKeyBytes = expandOneBlock(prk, info, 32);

            // IKM không còn cần cho Expand; PRK cũng có thể xóa
            // sau khi đã dẫn xuất hết các khóa con được yêu cầu.
            wipe(ikm);
            wipe(prk);

            byte[] nonce = new byte[12];
            RANDOM.nextBytes(nonce); // Một lần encrypt trong demo
            plaintext = "demo-only".getBytes(StandardCharsets.UTF_8);

            Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
            encryptor.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(aesKeyBytes, "AES"),
                    new GCMParameterSpec(128, nonce));
            ciphertextWithTag = encryptor.doFinal(plaintext);

            Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
            decryptor.init(Cipher.DECRYPT_MODE,
                    new SecretKeySpec(aesKeyBytes, "AES"),
                    new GCMParameterSpec(128, nonce));
            recovered = decryptor.doFinal(ciphertextWithTag);

            System.out.println("Round trip valid: "
                    + MessageDigest.isEqual(plaintext, recovered));
            // Không in IKM, PRK, OKM hoặc plaintext thật ra log.
        } finally {
            wipe(ikm);
            wipe(prk);
            wipe(aesKeyBytes);
            wipe(plaintext);
            wipe(recovered);
            // Bản mã thường không cần xóa vì không phải plaintext.
            // Xóa ciphertext nếu chính sách dữ liệu yêu cầu.
        }
    }
}
~~~

Lưu thành **IntermediateSecretCleanupDemo.java**, chạy với **JDK 17+**:

~~~bash
javac IntermediateSecretCleanupDemo.java
java IntermediateSecretCleanupDemo
~~~

Kết quả mong đợi:

~~~text
Round trip valid: true
~~~

### 6.1. Các điểm đáng chú ý trong mã

1. **IKM, PRK và OKM có biến riêng:** dễ nhìn thấy khi nào chúng không còn cần thiết.
2. **finally chạy cả khi lỗi:** một exception ở Cipher hoặc HKDF không bỏ qua việc ghi đè các mảng đang được sở hữu.
3. **Xóa sớm IKM và PRK:** không phải chờ toàn bộ tác vụ mã hóa kết thúc mới xóa mọi secret.
4. **Không in key material:** chỉ in boolean minh họa; trong vận hành còn phải tránh log secret ở exception, trace, debug và metrics tag.
5. **Bản sao từ API:** hàm **Arrays.copyOf** tạo một OKM riêng; hàm xóa **block** trung gian. **SecretKeySpec** có thể lưu bản sao khóa khác; cleanup tại đây không bảo đảm xóa bản sao đó.
6. **Không chứng minh erasure toàn cục:** kết quả **Round trip valid: true** chỉ chứng minh giải mã thành công, **không phải kiểm thử an ninh rằng memory đã sạch**.
7. **Giới hạn nonce:** demo mã hóa một lần; với AES-GCM production, nonce phải duy nhất trong phạm vi **cùng khóa** và phải quản lý tổng số lần mã hóa theo key.
8. **Info HKDF:** demo dùng chuỗi cố định chỉ để dễ đọc. Một hệ thống nhiều tenant cần encoding **không nhập nhằng, có version và lấy tenant/purpose từ ngữ cảnh đã xác thực**.

**Không nên đưa mã tự triển khai HKDF này vào production mà không đánh giá.** Hãy ưu tiên thư viện/provider HKDF đã được kiểm chứng, có test vectors của RFC 5869 và contract xử lý key material rõ ràng.

## 7. Xóa mật khẩu: char[], KDF và password verifier

Luồng xử lý mật khẩu khác với luồng KDF từ một secret ngẫu nhiên. **Mật khẩu thường có entropy thấp**, nên khi lưu mật khẩu đăng nhập cần dùng **Argon2id**, scrypt hoặc PBKDF2 theo chính sách, với salt riêng cho mỗi verifier và work factor phù hợp.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Auth service
    participant K as Password KDF
    participant DB as User database
    U->>A: Nhập mật khẩu qua kênh được bảo vệ
    A->>A: Nhận vào buffer có thể xóa nếu API cho phép
    A->>K: Password + salt + parameters
    K-->>A: Password verifier
    A->>DB: Lưu verifier + salt + parameters + version
    A->>A: Xóa password buffer do mình sở hữu trong finally
    Note over A,K: Provider có thể còn bản sao; phải quản lý theo contract
~~~

### 7.1. Điều nên tránh

- Giữ mật khẩu trong **String static**, session cache, debug log hoặc exception message.
- Ghi raw password hoặc derived secret vào request tracing và error telemetry.
- Trả về mật khẩu hoặc key material trong response API.
- Xem việc gọi **spec.clearPassword()** là đủ dù char[] caller vẫn còn.
- Chuyển mật khẩu qua nhiều lần **getBytes()**, StringBuilder/StringWriter hay serialize JSON mà không đánh giá bản sao.
- Dùng HKDF trực tiếp như giải pháp thay thế password hashing có chi phí tính toán chủ đích.

### 7.2. Salt, pepper và derived secret

**Salt** của password hashing thường là giá trị công khai, ngẫu nhiên, riêng từng mật khẩu. Nó cần được lưu cùng verifier; không xóa salt khiến verifier không thể kiểm tra lại.

**Pepper** là secret bổ sung có thể được quản lý bằng KMS/HSM tùy kiến trúc, không thay thế salt. Nếu pepper được sử dụng, phải có policy lưu trữ, rotation, phục hồi và xử lý sự cố riêng. Việc xóa buffer pepper sau mỗi lần sử dụng không tự thay thế cơ chế bảo vệ secret gốc.

Đối với derived verifier/hash được lưu ở database, việc **không xóa** kết quả là có chủ đích, vì nó cần được sử dụng để đối chiếu lần đăng nhập sau. Nhưng các **bản sao không cần thiết** của password, secret trung gian, pepper và thông điệp nhạy cảm nên được loại bỏ khỏi memory theo khả năng.

## 8. KMS/HSM và envelope encryption có thể giảm secret trong RAM như thế nào?

### 8.1. Hai mô hình quản lý DEK

| Mô hình | Nơi có plaintext DEK | Hệ quả với xóa memory |
|---|---|---|
| **Ứng dụng gọi GenerateDataKey rồi tự AES-GCM** | KMS/ứng dụng theo contract; ứng dụng có thể nhận DEK bản rõ | Phải giảm lifetime, tránh log, xóa buffer/derived key trong ứng dụng |
| **KMS/HSM thực hiện cryptographic operation bằng key handle** | Key material có thể ở trong ranh giới KMS/HSM, không xuất ra JVM | Giảm key exposure trong tiến trình ứng dụng; vẫn phải bảo vệ plaintext payload và quyền API |

**Non-exportable key** giúp giảm khả năng ứng dụng lấy byte thô của private key hoặc KEK. Nhưng nếu workload có quyền **Decrypt/Unwrap** trả plaintext DEK cho ứng dụng, DEK vẫn xuất hiện trong memory của workload. Nếu KMS trả plaintext khách hàng sau phép **Decrypt**, chính **plaintext ấy** vẫn phải được bảo vệ.

### 8.2. Không nhầm xóa memory với hủy khóa

**Xóa một mảng DEK trong Java** là xóa một bản sao đang nằm trong tiến trình. **Disable key trong KMS** là thay đổi khả năng sử dụng qua dịch vụ đó. **Destroy key material** là xử lý vòng đời khóa theo chính sách của HSM/KMS. **Crypto-erasure** nhằm làm dữ liệu đã mã hóa trở nên không thể khôi phục bằng cách hủy material cần thiết, nhưng chỉ có ý nghĩa nếu không còn bản sao khóa/đường phục hồi khác.

~~~text
Arrays.fill(localDek)          -> cố xóa một mảng local
KMS DisableKey                -> chặn/giới hạn API sử dụng key
KMS scheduled key deletion    -> quy trình hủy theo nhà cung cấp
Crypto-erasure                -> yêu cầu không còn khả năng phục hồi
                                 khóa cần thiết cho ciphertext
~~~

Những thao tác trên **không tương đương**. Việc giữ **root secret** có thể tái dẫn xuất DEK đã xóa cũng khiến “xóa derived DEK để hủy dữ liệu” chưa chắc đạt crypto-erasure.

### 8.3. Key rotation và bản sao đã cache

Giả sử một hệ thống rotate **KEK-v3 → KEK-v4**. Các DEK đã unwrap bằng v3 và đang nằm trong JVM không tự biến mất vì KMS đã đổi alias sang v4. Dịch vụ cần có **TTL, phạm vi cache, cơ chế invalidation, xử lý workload đang chạy và audit**.

Nếu DEK bị lộ, chỉ **rewrap DEK bằng KEK mới** không làm DEK đã lộ an toàn trở lại; phải cân nhắc **thay DEK và re-encrypt dữ liệu**. Nếu root/PRK của cây HKDF bị lộ, đổi **info label** mà giữ nguyên secret gốc cũng không khắc phục được sự cố.

## 9. Thiết kế giảm secret lifetime theo từng lớp

~~~mermaid
flowchart TD
    A["Nhận secret theo kênh/identity tin cậy"] --> B["Giữ ở vùng nhớ tối thiểu cần thiết"]
    B --> C["Dẫn xuất hoặc thực hiện phép mật mã"]
    C --> D["Hủy sớm bản sao trung gian đã hết vai trò"]
    D --> E["Hoàn thành output được phép"]
    E --> F["Xóa local buffer trong finally/cleanup API"]
    F --> G["Giải phóng reference, không cache/không log"]
    G --> H["Giám sát và kiểm soát dump, backup, quyền truy cập"]
~~~

### 9.1. Lớp ứng dụng

1. **Sở hữu buffer rõ ràng:** quy định hàm nào tạo, nhận bản sao và chịu trách nhiệm xóa. Không xóa một mảng mà caller vẫn cần hoặc một mảng được chia sẻ giữa thread.
2. **Phạm vi sống ngắn:** tạo byte[] khi gần cần sử dụng, xóa ngay sau khi hoàn tất; tránh field/static/cache không cần thiết.
3. **Dùng try/finally:** không đặt cleanup chỉ sau dòng thành công vì exception có thể khiến mã bỏ qua cleanup.
4. **Giảm bản sao:** tránh String, Base64 của secret, toString(), JSON serialize, deep copy và debug serializer không cần thiết.
5. **Không xuất khóa nếu không cần:** dùng key handle/API của provider có policy phù hợp.
6. **Tách secret với metadata:** chỉ log key ID, version, operation, actor và kết quả, không log raw material.

### 9.2. Lớp thư viện và JVM

- Hiểu **contract của SecretKeySpec, PBEKeySpec, Mac, Cipher, KeyStore và native provider**; các lớp có thể sao chép bí mật hoặc giữ state.
- Không giả định **close()** của mọi object đồng nghĩa khóa đã zeroize.
- Với công việc có assurance cao, xem xét **provider/native secure memory** có cơ chế wipe được tài liệu hóa, nhưng cần đánh giá giới hạn của heap, register, native copy và failover.
- Không tin rằng một **unit test đọc lại mảng toàn số 0** chứng minh heap dump hoặc native memory không còn secret.
- Những thao tác như tắt mọi GC hoặc gọi System.gc liên tục không phải giải pháp hủy bí mật.

### 9.3. Lớp hệ điều hành và vận hành

- Giới hạn **heap dump, crash dump/core dump**, quyền thu thập diagnostic và quyền tải dump từ môi trường production.
- Kiểm soát **swap/page file**, container/VM snapshot, backup, memory telemetry và quyền quản trị máy chủ.
- Đặt **retention, encryption at rest và access control** cho mọi artifact chẩn đoán có thể chứa secret.
- Giảm khả năng tiếp cận tiến trình bằng hardening, phân tách workload, least privilege và security monitoring.
- Không đưa credential/key vào command-line arguments hoặc biến môi trường nếu không đánh giá cách runtime, platform và công cụ quan sát có thể phơi bày chúng. Một số môi trường buộc dùng env vars; khi đó phải quản lý quyền và hạn chế log/dump.

**Memory locking** hoặc secure allocator có thể giảm một số nguy cơ paging, nhưng không phải “phép màu”: cần giới hạn hệ điều hành, đặc quyền, khả năng portable và bảo đảm cleanup của implementation. Không tự viết cơ chế native để thay thế một provider đã được kiểm chứng nếu chưa có đánh giá an ninh.

## 10. Các lỗi thường gặp và biện pháp

| Sai lầm | Vì sao không an toàn | Hướng xử lý |
|---|---|---|
| **secret = null** rồi kết luận đã xóa | Chỉ mất reference, dữ liệu vẫn có thể còn trong memory | Xóa buffer do mình quản lý, giảm copies và lifetime |
| Gọi **System.gc()** để “hủy khóa” | GC không hứa zeroize toàn bộ bản sao | try/finally, API cleanup và môi trường bảo vệ |
| Đổi byte[] thành **String** rồi cố wipe mảng | String vẫn có thể chứa secret | Tránh String khi có thể, quản lý API nhập liệu |
| Chỉ wipe mảng gốc sau **SecretKeySpec** | Provider/object có thể có bản sao key bytes | Giới hạn scope, contract provider, key handle |
| **clearPassword()** nhưng không wipe char[] đầu vào | Caller vẫn giữ bản sao mật khẩu | Xóa cả spec và caller buffer theo ownership |
| Wipe trước khi thao tác async hoàn tất | Thread/callback có thể cần dữ liệu đã bị ghi đè | Thiết kế ownership và lifetime theo async completion |
| Đưa secret vào cache/ThreadLocal lâu dài | Tăng thời gian và vị trí key exposure | TTL chặt, invalidation, tránh cache nếu không cần |
| Đưa secret vào log, exception hoặc debug | Bản sao tồn tại ngoài process, không thể sửa bằng Arrays.fill | Redact, hạn chế telemetry và kiểm toán |
| Cho phép dump production không kiểm soát | Dump có thể chứa key/plaintext | Kiểm soát quyền và retention artifact |
| Nhầm xóa local DEK với crypto-erasure | Root/KEK/bản sao khác vẫn phục hồi được dữ liệu | Thiết kế hủy theo toàn bộ đường khôi phục |
| Đổi KEK nhưng giữ DEK đã lộ | Rewrap không thu hồi plaintext DEK bị lộ | Rotate DEK, đánh giá re-encrypt và sự cố |
| Tin **HSM non-exportable** là đã chặn mọi rủi ro | Workload có quyền Sign/Decrypt vẫn lạm dụng API được | IAM, key policy, audit, hạn mức, xác thực nghiệp vụ |
| Tự code “secure zeroization” bằng mẹo reflection/unsafe | Không bảo đảm portable, dễ làm hỏng runtime/GC | API/provider được hỗ trợ, threat model và đánh giá |

## 11. Tình huống thực tế: Dịch vụ giải mã dữ liệu theo yêu cầu

Giả sử **Customer Service** lưu hồ sơ bằng **AES-GCM**; mỗi bản ghi có **wrapped DEK, nonce, authentication tag, key version và AAD**. KEK được quản lý trong KMS. Một request hợp lệ cần đọc hồ sơ của tenant cụ thể.

**Luồng đề xuất:**

1. **Xác thực và phân quyền:** từ workload identity và thông tin người dùng đã xác thực, dịch vụ kiểm tra tenant, record ID, mục đích đọc và key policy trước khi gọi KMS.
2. **Resolve key reference:** lấy wrapped DEK và metadata đã kiểm tra, gọi KMS Decrypt/Unwrap đúng KEK version và encryption context nếu hệ thống có yêu cầu.
3. **Nhận DEK trong scope hẹp:** nếu KMS trả DEK bản rõ, lưu trong buffer được quản lý có vòng đời ngắn; không đưa vào ThreadLocal lâu dài hoặc log.
4. **AES-GCM Verify/Decrypt:** cung cấp đúng nonce, ciphertext/tag và AAD tái dựng từ ngữ cảnh tin cậy; chỉ sử dụng plaintext **sau khi xác thực tag thành công**.
5. **Xử lý nghiệp vụ và cleanup:** kết thúc xử lý plaintext trong phạm vi cần thiết, xóa những byte[] do ứng dụng sở hữu trong finally; ghi nhận những bản sao do framework/provider có thể sinh.
6. **Audit:** ghi principal, operation, tenant, key ID/version, request ID và kết quả mà không ghi key material hay nội dung hồ sơ.
7. **Vận hành:** hạn chế dump/diagnostic, bảo vệ trace/log/backup; xác định cách thu hồi quyền và hủy cache khi sự cố xảy ra.

Trong luồng này, **xóa local DEK** là một lớp giảm rủi ro. Các lớp còn lại gồm **KMS policy, IAM, data authorization, AES-GCM authentication, audit, rotation và vận hành an toàn**. Nếu một service có quyền Decrypt bị chiếm khi đang chạy, zeroization sau tác vụ có thể không ngăn việc nó yêu cầu giải mã dữ liệu khác.

### 11.1. Lựa chọn kiến trúc để giảm lượng secret chảy qua ứng dụng

Nếu yêu cầu tránh đưa raw DEK vào JVM là rất cao, hãy đánh giá **mô hình gọi phép toán mật mã trong ranh giới KMS/HSM** hoặc một crypto service cô lập, nếu nhà cung cấp hỗ trợ và hiệu năng/chi phí phù hợp. Khi ấy ứng dụng vẫn phải bảo vệ plaintext nghiệp vụ, danh tính caller và các API có thể bị lạm dụng.

Việc chọn giữa **local crypto với DEK tạm thời** và **remote crypto operation qua key handle** phải cân bằng kích thước dữ liệu, độ trễ, chi phí, khả năng retry, quy định nội bộ, mức độ nhạy cảm và threat model. Không thể khẳng định một mô hình luôn tối ưu cho mọi hệ thống.

## 12. Checklist review secret lifetime

1. **Inventory:** đã liệt kê mọi secret, IKM, PRK, OKM, DEK, HMAC key, password, private key và plaintext nhạy cảm chưa?
2. **Ownership:** hàm, thread, module hoặc provider nào sở hữu buffer và chịu trách nhiệm cleanup?
3. **Bản sao:** secret có bị chuyển sang String, toByteArray, getEncoded, Base64, serialization, native memory, pool hoặc log không?
4. **Thời điểm xóa:** có xóa bản sao trung gian ngay sau khi hết nhu cầu, kể cả khi exception xảy ra?
5. **Async:** có bảo đảm không wipe trước khi consumer bất đồng bộ sử dụng xong?
6. **API contract:** thư viện/KMS/HSM có thực hiện copy, có hỗ trợ cleanup/destroy đúng nghĩa và giới hạn nào?
7. **Password handling:** có tránh String nếu được, clear PBEKeySpec và char[] caller, dùng password hashing thích hợp?
8. **KDF:** root/IKM/PRK/OKM được dùng và loại bỏ đúng lúc; domain separation có version và context đáng tin?
9. **Encryption:** AES-GCM có nonce duy nhất theo DEK, AAD đúng, tag được xác minh; plaintext được giữ ngắn?
10. **Key hierarchy:** xoay/hủy root, KEK, DEK có tác động thế nào đến derived keys, cache và backup?
11. **Runtime/OS:** heap dump, core dump, swap, snapshot, diagnostic và telemetry đã được hạn chế/phân quyền?
12. **Incident response:** nếu key material nghi bị lộ, có kế hoạch rotate, revoke, re-encrypt và kiểm tra dữ liệu bị ảnh hưởng?

### Câu hỏi tự kiểm tra

**Câu 1.** Sau khi sử dụng DEK, gán **dek = null** rồi gọi System.gc(). Có thể kết luận DEK đã bị xóa hoàn toàn khỏi memory không?

**Trả lời:** **Không.** Đây không phải hợp đồng secure erase; object hoặc bản sao có thể còn trong heap/native/provider. Cần quản lý buffer, xóa best effort và giảm exposure bằng nhiều lớp.

**Câu 2.** Vì sao char[] thường được ưu tiên hơn String để nhận mật khẩu trong Java khi API cho phép?

**Trả lời:** Có thể ghi đè từng phần tử của char[] khi không còn cần, còn String bất biến và không có API xóa nội dung được bảo đảm. Dù vậy, char[] không loại trừ bản sao hoặc rủi ro dump.

**Câu 3.** **PBEKeySpec.clearPassword()** có tự xóa char[] đã truyền vào constructor không?

**Trả lời:** **Không nên giả định.** PBEKeySpec có thể giữ bản sao riêng; caller vẫn phải xóa char[] do mình sở hữu và quản lý các bản sao khác.

**Câu 4.** Xóa mảng **prk** sau HKDF-Expand có tự xóa khóa nằm trong SecretKeySpec và Mac không?

**Trả lời:** **Không có bảo đảm.** Provider/object có thể giữ key material riêng. Việc xóa prk giúp giảm lifetime của mảng caller, không chứng minh mọi bản sao đã bị hủy.

**Câu 5.** Nếu một DEK đã từng bị lộ và được lưu lại bởi đối thủ, xóa DEK khỏi JVM và rewrap cùng DEK bằng KEK mới có khôi phục bí mật không?

**Trả lời:** **Không.** Đối thủ vẫn có DEK đã lộ. Cần đánh giá thay DEK, re-encrypt dữ liệu và ứng phó sự cố theo phạm vi ảnh hưởng.

**Câu 6.** Khi private key trong HSM không xuất được, liệu workload có quyền Decrypt quá rộng còn là nguy cơ không?

**Trả lời:** **Có.** Workload có thể yêu cầu HSM thực hiện phép giải mã. Cần IAM, key policy, kiểm tra nghiệp vụ và audit ngoài việc bảo vệ byte khóa.

**Câu 7.** Xóa derived key của record khi root secret và context vẫn còn có đạt crypto-erasure độc lập cho record không?

**Trả lời:** **Chưa chắc.** Nếu có thể tái dẫn xuất derived key từ root và context, khóa có thể được phục hồi. Kiến trúc cần bảo đảm material cần thiết thực sự không còn đường phục hồi.

**Câu 8.** Kết quả unit test cho thấy byte[] sau Arrays.fill toàn số 0. Có thể tuyên bố không còn secret trong heap dump không?

**Trả lời:** **Không.** Test chỉ quan sát chính mảng ấy. Secret có thể nằm ở String, mảng khác, provider, native heap, snapshot hoặc log.

**Điểm cốt lõi:** **Xóa secret trung gian khỏi memory** là thực hành **giảm phạm vi và thời gian tồn tại của key material**, không phải phép hủy dữ liệu tuyệt đối trong Java. Hãy sở hữu buffer rõ ràng, hạn chế sao chép, dùng **try/finally** để xóa các mảng có thể kiểm soát, ưu tiên **KMS/HSM và key handle** khi phù hợp, đồng thời bảo vệ hệ điều hành, log, quyền API và toàn bộ vòng đời khóa. Chỉ khi các lớp này phối hợp, nguy cơ secret bị thu thập từ bộ nhớ mới được giảm một cách có ý nghĩa.
