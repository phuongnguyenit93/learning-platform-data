# 3.7 Phân biệt salt, IV, nonce, challenge và token ngẫu nhiên

**Salt**, **initialization vector (IV)**, **nonce**, **challenge** và **token ngẫu nhiên** đều có thể chứa những byte do `SecureRandom` sinh ra, nhưng **không thể thay thế tùy ý**. Mỗi loại phục vụ một mục tiêu bảo mật khác nhau và có quy tắc riêng về tính duy nhất, khả năng dự đoán, giữ bí mật, phạm vi sử dụng và vòng đời.

Hiểu đúng các khái niệm giúp tránh những lỗi nghiêm trọng như tái sử dụng nonce trong AES-GCM, dùng chung salt cho mọi tài khoản, chấp nhận replay một challenge hoặc làm lộ bearer token.

## 1. So sánh nhanh năm khái niệm

| Giá trị | Mục đích chính | Thuộc tính bắt buộc | Có phải bí mật? | Ví dụ và nơi lưu |
| --- | --- | --- | --- | --- |
| **Salt** | Tách biệt kết quả dẫn xuất/mã băm mật khẩu giữa các bản ghi, dù mật khẩu giống nhau. | Riêng biệt cho từng mật khẩu/verifier; được cung cấp lại khi xác minh. | **Không.** | 16 byte ngẫu nhiên, lưu cùng bản ghi hash, thuật toán và cost. |
| **IV** (initialization vector) | Khởi tạo một lần mã hóa theo mode cụ thể. | **Phụ thuộc mode**: CBC cần IV khó dự đoán; nhiều mode dựa trên counter yêu cầu không lặp. | Thường **không**. | AES-CBC dùng IV 16 byte; lưu/truyền cùng ciphertext. |
| **Nonce** (number used once) | Đánh dấu một lần sử dụng khóa hoặc một thông điệp trong giao thức. | **Không lặp lại trong phạm vi được chỉ định**; với AES-GCM, tuyệt đối không lặp cùng key. | Tùy giao thức; GCM nonce thường **không**. | AES-GCM thường dùng nonce/IV 12 byte, đi cùng ciphertext. |
| **Challenge** | Buộc bên kia chứng minh sở hữu khóa/quyền đối với một thử thách **mới**; ngăn phát lại chứng cứ cũ. | Khó đoán, mới, giới hạn thời gian; gắn với user, phiên/hành động và thường dùng một lần. | Thường **không**. | Server sinh 32 byte; lưu trạng thái challenge, context, expiry, used. |
| **Random bearer token** | Cấp khả năng sử dụng phiên/quyền/khôi phục thông qua việc **sở hữu giá trị**. | Khó đoán với entropy cao; phải bảo vệ, giới hạn scope, hết hạn và thu hồi được. | **Có.** | 32 byte ngẫu nhiên cho session/reset/API token; server lưu verifier và metadata quyền. |

Các độ dài trên là **ví dụ thực hành**, không phải công thức áp dụng cho mọi hệ thống. IV/nonce phải đúng kích thước và quy tắc của **thuật toán, mode, protocol** đang dùng. Challenge và token cần entropy, vòng đời và giao thức tương ứng.

Một câu hỏi phân biệt nhanh: “Giá trị này dùng để **dẫn xuất mật khẩu**, **mã hóa**, **chống replay**, hay **mang quyền**?” Trả lời câu đó trước khi chọn cách sinh random.

## 2. Đừng nhầm uniqueness, unpredictability và secrecy

Ba thuộc tính khác nhau:

1. **Tính duy nhất (uniqueness):** giá trị không lặp trong phạm vi đã định. Bộ đếm tăng dần có thể duy nhất nếu quản lý đúng xuyên restart/đa node, nhưng dễ dự đoán.
2. **Tính khó dự đoán (unpredictability):** kẻ tấn công không thể tính giá trị mới trước khi nó xuất hiện. Challenge, secret token và IV CBC cần tính chất này trong ngữ cảnh thích hợp.
3. **Tính bí mật (secrecy):** người không được cấp quyền không được biết hoặc sử dụng giá trị. Bearer token phải được bảo vệ như một credential. Salt và IV/nonce trong các mode phổ biến thường đi kèm bản ghi/ciphertext mà không cần mã hóa riêng.

| Giá trị ví dụ | Duy nhất? | Khó dự đoán? | Bí mật? | Kết luận |
| --- | --- | --- | --- | --- |
| Bộ đếm 1, 2, 3 | Có thể có | Không | Không | Có thể làm nonce cho **một số giao thức** nếu bảo đảm không lặp; không tự động phù hợp CBC. |
| 12 byte sinh từ CSPRNG | Xác suất trùng rất nhỏ, không tuyệt đối bằng 0 | Có | Không mặc định | Có thể dùng cho AES-GCM khi tuân thủ giới hạn lượng bản mã/khóa. |
| 32 byte CSPRNG được gửi công khai | Xác suất trùng rất nhỏ | Có trước khi công bố | Không | Có thể làm challenge công khai; không còn là bearer secret. |
| 32 byte CSPRNG được giữ kín | Xác suất trùng rất nhỏ | Có | Có, nếu vận chuyển/lưu trữ đúng | Có thể là bearer token nhưng vẫn cần hạn dùng, scope và thu hồi. |

**Encoding không thêm entropy.** 32 byte ngẫu nhiên có tối đa 256 bit entropy dù được biểu diễn thành 43 ký tự Base64URL, 64 ký tự hex hay một kiểu chuỗi khác. Timestamp và ID tăng dần không tự trở thành giá trị bảo mật nhờ mã hóa Base64.

## 3. Salt: làm riêng kết quả dẫn xuất mật khẩu

### 3.1. Vì sao phải có salt?

Nếu Alice và Bob cùng đặt một mật khẩu và hệ thống chỉ băm bằng một hàm xác định, kết quả của hai bản ghi sẽ giống nhau. Việc dùng **salt khác nhau cho mỗi bản ghi** khiến đầu ra khác nhau, làm giảm khả năng dùng bảng hash tính trước và buộc kẻ tấn công xử lý từng verifier riêng.

~~~text
Alice: password + salt_A + cost -> PasswordKDF -> verifier_A
Bob:   password + salt_B + cost -> PasswordKDF -> verifier_B

Bản ghi Alice: {algorithm, parameters/cost, salt_A, verifier_A}
Khi đăng nhập: đọc salt_A, algorithm, cost; dẫn xuất lại rồi so sánh
~~~

- Sinh salt **mới** bằng CSPRNG khi tạo verifier mật khẩu mới; đổi mật khẩu cũng nên tạo salt mới.
- Salt **không cần giấu**. Lưu cùng verifier là bình thường và cần thiết để xác minh.
- Không dùng salt cố định/toàn cục, username hoặc timestamp thay cho salt đủ ngẫu nhiên.
- **Salt không thay thế password hashing/KDF chậm.** Dùng trực tiếp `SHA-256(password + salt)` vẫn tạo điều kiện thử mật khẩu quá nhanh. Nên dùng Argon2id, scrypt hoặc PBKDF2 với cấu hình phù hợp.
- **Pepper khác salt:** pepper là bí mật riêng, được giữ ngoài database mật khẩu (chẳng hạn trong secret manager/HSM), là lớp bảo vệ bổ sung chứ không thay salt.
- Thuật ngữ salt còn xuất hiện ở KDF như HKDF; tại đó phải áp dụng **quy tắc của KDF cụ thể**, không mặc định mọi salt đều là salt của mật khẩu.

### 3.2. Ví dụ Java 17+: cùng mật khẩu, hai salt

Tệp **`PasswordSaltDemo.java`** dùng `PBKDF2WithHmacSHA256` trong JDK để minh họa. Với ứng dụng mới, cân nhắc Argon2id bằng thư viện đáng tin nếu phù hợp; với PBKDF2, số vòng `600_000` minh họa mức OWASP khuyến nghị cho HMAC-SHA256 tại thời điểm tham khảo và cần được kiểm tra lại theo hướng dẫn/hiệu năng thực tế.

~~~java
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PasswordSaltDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int ITERATIONS = 600_000;

    private static byte[] randomSalt() {
        byte[] salt = new byte[16];
        RNG.nextBytes(salt);
        return salt;
    }

    private static byte[] derive(char[] password, byte[] salt) throws Exception {
        PBEKeySpec spec = new PBEKeySpec(password, salt, ITERATIONS, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "demo password only".toCharArray();
        try {
            byte[] salt1 = randomSalt();
            byte[] salt2 = randomSalt();
            byte[] verifier1 = derive(password, salt1);
            byte[] verifier2 = derive(password, salt2);

            System.out.println("Distinct salts: "
                    + !Arrays.equals(salt1, salt2));
            System.out.println("Distinct verifiers: "
                    + !MessageDigest.isEqual(verifier1, verifier2));
            System.out.println("Verification: " + MessageDigest.isEqual(
                    verifier1, derive(password, salt1)));
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

~~~bash
javac PasswordSaltDemo.java
java PasswordSaltDemo
~~~

Đầu ra điển hình (xác suất hai salt ngẫu nhiên 128 bit trùng nhau là cực nhỏ):

~~~text
Distinct salts: true
Distinct verifiers: true
Verification: true
~~~

Nhận xét: cùng mật khẩu được xác minh thành công với **salt đúng của bản ghi**, còn hai salt mới thường tạo verifier khác nhau. Khi lưu thực tế cần lưu cả algorithm, salt, cost, verifier; cần chính sách nâng cấp thông số khi đăng nhập và rate limit để chống đoán mật khẩu trực tuyến.

## 4. IV và nonce: phụ thuộc thuật toán/mode

### 4.1. IV có phải nonce không?

**IV** là tham số khởi tạo một phép mã hóa. **Nonce** nhấn mạnh rằng giá trị được dùng một lần trong phạm vi quy định. Trong **AES-GCM**, cùng một tham số thường được gọi là **IV** hoặc **nonce**: **không phải** hai giá trị riêng cần sinh cho mỗi bản mã.

| Mode | Cách dùng | Yêu cầu | Kích thước AES thường gặp |
| --- | --- | --- | --- |
| **CBC** | IV khởi tạo phép ghép khối. | Với IV thông thường, phải khó dự đoán và được sinh mới đúng cách. Không tự cung cấp xác thực bản mã. | **16 byte**, bằng kích thước khối AES. |
| **CTR** | Nonce/counter tạo dòng khóa để XOR với dữ liệu. | Không tái sử dụng cùng dãy counter block/keystream dưới một khóa; khả năng dự đoán của nonce có thể được chấp nhận. | Tùy thiết kế cấu trúc counter và giao thức. |
| **GCM** | IV/nonce tham gia xây dựng trạng thái CTR và xác thực AEAD. | **Không lặp cặp (AES key, nonce).** | **12 byte (96 bit)** là lựa chọn ưu tiên phổ biến. |

CBC/CTR không tự cung cấp xác thực; với dữ liệu ứng dụng mới, thường chọn một **AEAD** như AES-GCM khi phù hợp, dùng cả encryption và authentication đúng cách.

### 4.2. Vì sao không được tái sử dụng GCM nonce?

Nếu mã hóa hai plaintext khác nhau bằng **cùng khóa AES-GCM và cùng nonce**, tính bảo mật và bảo đảm xác thực của GCM có thể bị phá vỡ. Dù hai bản mã được tạo ở hai microservice hoặc hai lần chạy JVM, **chúng vẫn vi phạm nếu cùng key/nonce**.

Các chiến lược sinh nonce:

- **CSPRNG 96 bit:** đơn giản, thuận tiện, nhưng không bảo đảm tuyệt đối không va chạm; giới hạn số lần mã hóa trên cùng key và chính sách rotation phải được thiết kế theo tải và đặc tả.
- **Counter được quản lý:** có thể bảo đảm không lặp nếu lưu tiến độ bền vững và phối hợp nhiều process/node. Không reset counter khi khởi động lại mà vẫn dùng khóa cũ.
- **Phân chia không gian nonce:** cấp vùng nonce riêng cho từng node hoặc dùng cơ chế phối hợp tương đương, tránh trùng giữa các máy.

“Nonce không bí mật” **không có nghĩa** được tái sử dụng. Ngược lại, “random” **không có nghĩa** chắc chắn duy nhất. Hãy thiết kế quản lý nonce cho **cả vòng đời khóa**.

### 4.3. Envelope AES-GCM cần lưu gì?

~~~text
Key K           -> giữ trong keystore/KMS, không gắn vào bản mã dưới dạng thô
Nonce / IV      -> gửi cùng bản mã để giải mã, không cần giấu
Ciphertext      -> dữ liệu đã mã hóa
Authentication tag -> bằng chứng xác thực của phép GCM
AAD             -> metadata được xác thực nhưng không mã hóa, phải nhất quán

Envelope minh họa: nonce(12 byte) || ciphertext || tag(16 byte)
~~~

Trong Java, `Cipher.doFinal` với `AES/GCM/NoPadding` thường trả ciphertext có kèm authentication tag. Cả phía encrypt/decrypt phải dùng đúng nonce, key, tag length và AAD. Thay đổi AAD hoặc bản mã phải khiến xác thực thất bại.

### 4.4. Java 17+: GCM nonce mới cho phép mã hóa

Tệp **`GcmNonceDemo.java`** tạo một khóa AES ngẫu nhiên phục vụ ví dụ, sinh 12 byte nonce cho lần encrypt và ghép vào đầu envelope. Việc chỉ sinh một lần trong ví dụ không thay cho chiến lược chống trùng trên nhiều node và trong suốt vòng đời khóa thực tế.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class GcmNonceDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    static byte[] encrypt(
            SecretKey key, byte[] plaintext, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return ByteBuffer.allocate(nonce.length + ciphertextAndTag.length)
                .put(nonce).put(ciphertextAndTag).array();
    }

    static byte[] decrypt(
            SecretKey key, byte[] envelope, byte[] aad)
            throws GeneralSecurityException {
        if (envelope.length < NONCE_BYTES + TAG_BITS / 8) {
            throw new IllegalArgumentException("Envelope too short");
        }

        ByteBuffer input = ByteBuffer.wrap(envelope);
        byte[] nonce = new byte[NONCE_BYTES];
        input.get(nonce);
        byte[] ciphertextAndTag = new byte[input.remaining()];
        input.get(ciphertextAndTag);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyGenerator kg = KeyGenerator.getInstance("AES");
        kg.init(128);
        SecretKey key = kg.generateKey();

        byte[] aad = "record:v1".getBytes(StandardCharsets.UTF_8);
        byte[] envelope = encrypt(
                key, "Hello".getBytes(StandardCharsets.UTF_8), aad);

        System.out.println("Recovered: " + new String(
                decrypt(key, envelope, aad), StandardCharsets.UTF_8));
        System.out.println("Nonce bytes: " + NONCE_BYTES);

        envelope[envelope.length - 1] ^= 1;
        try {
            decrypt(key, envelope, aad);
            throw new AssertionError("Tampering undetected");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampering rejected: true");
        }
    }
}
~~~

~~~bash
javac GcmNonceDemo.java
java GcmNonceDemo
~~~

Stdout:

~~~text
Recovered: Hello
Nonce bytes: 12
Tampering rejected: true
~~~

Mã chạy chứng minh **nonce không cần bí mật** để giải mã, nhưng phải là nonce đúng của phép mã hóa. GCM từ chối bản mã/tag bị sửa thay vì trả plaintext không đáng tin cậy. Ví dụ chưa bao gồm version, key ID, kho khóa, khóa xoay vòng hoặc quản lý nonce cho tải lớn; đó là phần bắt buộc của thiết kế production.

### 4.5. Nonce trong ngữ cảnh khác

“Nonce” không phải kiểu dữ liệu có kích thước và chính sách chung. Trong một giao thức xác thực nó có thể là giá trị chống replay; trong giao thức chữ ký số có thể có nonce nội bộ nhạy cảm với yêu cầu riêng; trong Content Security Policy của web, nonce là giá trị gắn với **một HTTP response**. Đừng đem quy tắc “GCM nonce 12 byte công khai” áp vào mọi loại nonce.

## 5. Challenge: freshness và chống phát lại

Challenge là thử thách mới do server/bên xác minh đưa ra để yêu cầu client chứng minh có một bí mật/khóa. Challenge thường **công khai** vì client phải nhận nó để tạo chữ ký hoặc thông điệp xác thực.

### Ví dụ luồng xác thực bằng chữ ký

~~~text
1. Client yêu cầu xác thực/hành động
2. Server sinh challenge C mới từ CSPRNG
3. Server lưu {C hoặc hash(C), user, session, action, expiry, used=false}
4. Server gửi C cho client
5. Client ký thông điệp giao thức gồm C và context bằng private key
6. Client gửi chữ ký và định danh khóa
7. Server verify chữ ký bằng public key tin cậy,
   kiểm tra challenge đúng, context đúng, còn hạn, chưa dùng
8. Server đánh dấu consumed atomically rồi mới chấp nhận
~~~

**Chỉ gửi lại chính challenge không chứng minh được danh tính.** Phải có bằng chứng mật mã thật: chữ ký/MAC hoặc cơ chế đã được giao thức chuẩn định nghĩa.

Challenge an toàn cần:

- Được sinh mới, đủ khó đoán; ví dụ **32 byte `SecureRandom`** khi giao thức không đặt định dạng khác.
- **Ràng buộc user, phiên, origin, action, transaction** theo yêu cầu, để tránh chữ ký hợp lệ cho A bị dùng cho B.
- Có **thời hạn ngắn**, chỉ sử dụng một lần nếu giao thức yêu cầu.
- Được kiểm tra và tiêu thụ theo cách **atomic** để hai yêu cầu song song không cùng tái sử dụng được.
- Xác minh bằng khóa và thuật toán chính xác; không bỏ qua lỗi chữ ký hoặc chấp nhận challenge của hệ thống khác.

Trong WebAuthn, challenge chỉ là một thành phần cùng với kiểm tra RP ID, origin, authenticator data và các điều kiện chuyên biệt khác. Không thay giao thức WebAuthn bằng một bản tự chế chỉ kiểm tra challenge.

Challenge đôi khi **đồng thời là nonce** của giao thức (vì giá trị phải mới). Điều đó không biến nó thành IV mã hóa, cũng không làm challenge thành một bearer token.

## 6. Token ngẫu nhiên: giá trị mang quyền phải giữ bí mật

Một **opaque bearer token** là giá trị ngẫu nhiên không mang thông tin có thể suy ra trực tiếp. Server liên kết nó với trạng thái/quyền trong database/session store. **Ai sở hữu token hợp lệ có thể dùng quyền mà token đại diện**, nên token phải được bảo vệ.

Ví dụ: session token, password-reset token, email-verification token, API token. Mỗi loại có vòng đời và scope khác nhau; một token reset dùng một lần không thể được xử lý như session token dài hạn.

### Quy trình cấp và xác minh token

1. Server sinh **32 byte bằng CSPRNG** làm token bí mật mới; có thể biểu diễn bằng Base64URL không padding.
2. Server tạo bản ghi **quyền hạn, user, scope, expiry, trạng thái thu hồi**; nếu dùng một lần thì có `used`.
3. Thay vì lưu token thô, với token có entropy cao có thể lưu **`SHA-256(tokenBytes)`** làm verifier, giảm nguy cơ đọc lộ DB.
4. Khi client xuất trình token, server kiểm tra format, băm lại theo cùng biểu diễn byte, tìm/so sánh verifier, kiểm tra expiry/scope/revocation và chống dùng lại.
5. Server từ chối token sai, hết hạn hoặc đã thu hồi; thao tác một lần cần tiêu thụ trạng thái **atomic**.

**Vì sao có thể hash SHA-256 cho token nhưng không cho mật khẩu?** Mật khẩu do người chọn thường có entropy thấp, cần password KDF chậm để chống thử đoán. Một token 256 bit ngẫu nhiên có entropy cao, nên fast hash có thể phù hợp để lưu verifier; không được vì thế suy ra rằng mọi token đều có entropy cao (ví dụ token lấy từ ID/timestamp).

### Bảo vệ bearer token khi vận hành

- **Không log/tokenize toàn bộ giá trị** vào analytics, crash report hoặc URL query; dùng redaction và không in secret để debug.
- Dùng HTTPS; với session trên web, ưu tiên giải pháp framework tin cậy và cấu hình cookie `Secure`, `HttpOnly`, `SameSite` phù hợp.
- Đặt expiry phía server, quyền hẹp, revocation, rotation, rate limit; bảo vệ chống session fixation và CSRF theo kiến trúc.
- Nếu lưu hash token, server phải bảo đảm **không giữ token gốc trong cùng bản ghi**, và tránh so sánh byte bí mật bằng các hàm dễ gây rò timing; `MessageDigest.isEqual` là một lựa chọn phù hợp khi so sánh các digest.
- Token **có cấu trúc** như JWT ký số không tự động là opaque random token; cách xác thực JWT phụ thuộc chữ ký/claims/protocol, không chỉ entropy của chuỗi JWT.

Salt và challenge có thể công khai. **Bearer token đang còn hiệu lực thì không.**

## 7. Java 17+: sinh, encode và quan sát độ dài

`java.security.SecureRandom` là API chuẩn để sinh byte khó đoán phục vụ các trường hợp bảo mật. Kích thước và cách sử dụng do **mục đích** quyết định. Mã dưới đây chỉ minh họa khâu tạo dữ liệu; nó không thay phép dẫn xuất mật khẩu, mã hóa hay kiểm tra challenge/token.

Tệp **`RandomMaterialsDemo.java`**:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public class RandomMaterialsDemo {
    private static final SecureRandom RNG = new SecureRandom();

    private static byte[] bytes(int size) {
        byte[] result = new byte[size];
        RNG.nextBytes(result);
        return result;
    }

    private static int urlLength(byte[] value) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value)
                .length();
    }

    public static void main(String[] args) {
        byte[] salt = bytes(16);
        byte[] cbcIv = bytes(16);
        byte[] gcmNonce = bytes(12);
        byte[] challenge = bytes(32);
        byte[] token = bytes(32);

        System.out.printf("salt=%d bytes, %d chars%n",
                salt.length, urlLength(salt));
        System.out.printf("CBC IV=%d bytes, %d chars%n",
                cbcIv.length, urlLength(cbcIv));
        System.out.printf("GCM nonce=%d bytes, %d chars%n",
                gcmNonce.length, urlLength(gcmNonce));
        System.out.printf("challenge=%d bytes, %d chars%n",
                challenge.length, urlLength(challenge));
        System.out.printf("token=%d bytes, %d chars%n",
                token.length, urlLength(token));
    }
}
~~~

~~~bash
javac RandomMaterialsDemo.java
java RandomMaterialsDemo
~~~

Stdout chính xác (chỉ in độ dài, không in byte ngẫu nhiên):

~~~text
salt=16 bytes, 22 chars
CBC IV=16 bytes, 22 chars
GCM nonce=12 bytes, 16 chars
challenge=32 bytes, 43 chars
token=32 bytes, 43 chars
~~~

Điều cần chú ý:

1. `SecureRandom.nextBytes` khác `java.util.Random`, `Math.random()` hay timestamp seed; những nguồn thông thường không phù hợp sinh bí mật.
2. Base64URL là **encoding**, không phải encryption; biểu diễn 32 byte thành 43 ký tự không làm tăng entropy.
3. Challenge và token đều được ví dụ sinh 32 byte, nhưng **challenge dùng để xác minh proof mới**, còn **token phải được giữ kín**. Không được gộp logic xử lý chúng chỉ vì cùng kích thước.
4. 12 byte nonce GCM là lựa chọn phổ biến cho **một chế độ mã hóa nhất định**; không mặc định mọi nonce/challenge phải dài 12 byte.
5. Có thể dùng một `SecureRandom` dùng chung, nhưng từng chức năng phải có quản lý vòng đời và chính sách kiểm tra riêng.

## 8. Bốn kịch bản áp dụng: ai tạo, ai giữ, ai xác minh?

### Kịch bản A: đăng ký và xác thực mật khẩu

~~~text
Lần tạo verifier:
  người dùng chọn password
  server sinh salt mới
  PasswordKDF(password, salt, cost) -> verifier
  database lưu {algorithm, cost, salt, verifier}

Lần đăng nhập:
  server đọc chính salt/cost đã lưu
  PasswordKDF(passwordNhập, saltĐãLưu, costĐãLưu)
  server so sánh kết quả với verifier
~~~

Salt được **lưu lâu dài và dùng lại để kiểm tra cùng bản ghi**. Sinh salt mới mỗi lần đăng nhập sẽ làm kết quả không khớp.

### Kịch bản B: mã hóa một record bằng AES-GCM

~~~text
Encrypt với khóa K:
  cấp nonce N chưa sử dụng với K
  (K, N, plaintext, AAD) -> ciphertext + tag
  lưu {version, keyId, N, ciphertext, tag, AAD/context}

Decrypt:
  tìm đúng K; lấy N, ciphertext, tag, AAD/context
  xác thực tag rồi mới chấp nhận plaintext
~~~

Nonce đi cùng ciphertext, không được dùng lại với K. Nếu nhiều node dùng K, phải điều phối giá trị nonce hoặc chia không gian nonce an toàn.

### Kịch bản C: thử thách ký số chống replay

~~~text
Server sinh C mới, lưu user/session/action/expiry/used
Client ký C + context bằng khóa của mình
Server verify chữ ký và kiểm tra C chưa hết hạn/chưa dùng
Server tiêu thụ C atomically rồi cho phép hành động
~~~

Challenge thường công khai; **private key** mới là phần bí mật mà chữ ký chứng minh sở hữu.

### Kịch bản D: reset mật khẩu qua token

~~~text
Server sinh token T mới, hạn ngắn, dùng một lần
Server lưu hash(T) và {user, expiry, used=false}
Server phát T qua kênh reset được kiểm soát
Người dùng xuất trình T
Server kiểm tra hash, user, expiry, used
Server consume atomically, đổi password, thu hồi quyền liên quan
~~~

Token reset **không phải salt mật khẩu**. Salt được duy trì để xác minh một verifier; token reset là credential tạm thời, hết tác dụng sau khi sử dụng.

## 9. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng cùng salt cho mọi người dùng | Kết quả mật khẩu giống nhau có thể tương quan; suy yếu chống precomputation. | Salt mới, độc lập theo từng verifier. |
| Chỉ dùng `SHA-256(password + salt)` | Khó chống brute-force offline. | Dùng password KDF chuyên dụng có cost phù hợp. |
| Nghĩ IV/nonce phải bí mật nên tái sử dụng được | Bỏ qua quy tắc quan trọng của mode. | Lưu/truyền IV theo chuẩn, bảo đảm yêu cầu fresh/unique của mode. |
| Dùng cùng `(AES-GCM key, nonce)` hai lần | Có thể phá tính bí mật/xác thực. | Bảo đảm không trùng nonce theo vòng đời key, kể cả nhiều node. |
| Dùng bộ đếm dễ đoán làm IV CBC | Vi phạm yêu cầu khó dự đoán trong sử dụng CBC thông thường. | Sinh IV CBC ngẫu nhiên đúng kích thước, hoặc dùng mode phù hợp. |
| Dùng CBC/CTR mà không xác thực | Không phát hiện dữ liệu bị sửa đáng tin cậy. | Ưu tiên AEAD; nếu bắt buộc mode khác, kết hợp xác thực chuẩn. |
| Server gửi challenge rồi chỉ so sánh echo | Không chứng minh sở hữu khóa hoặc quyền. | Verify chữ ký/MAC và ngữ cảnh giao thức. |
| Challenge không expiry hoặc không one-time | Có thể replay lại proof. | Bind context, hạn dùng và tiêu thụ atomic. |
| Token tạo từ `Random`/timestamp/user ID | Dễ dự đoán, bị đoán/chiếm quyền. | CSPRNG + entropy đủ cao. |
| Đưa bearer token vào log/query string | Token bị lộ qua các hệ thống phụ trợ. | Giữ kín, HTTPS, cookie/header phù hợp, redact log. |
| Base64 dài nên “đủ entropy” | Đánh giá sai độ khó đoán. | Tính entropy của nguồn byte trước encoding. |
| Token random thì khỏi cần expiry/revoke | Token bị đánh cắp vẫn sử dụng được. | Scope hẹp, hết hạn, thu hồi, rotation và rate limit. |

## 10. Checklist thiết kế trước khi gọi `SecureRandom`

1. **Mục tiêu** là dẫn xuất mật khẩu, khởi tạo mã hóa, chống replay hay cấp quyền?
2. **Phạm vi uniqueness** là mỗi verifier, mỗi khóa, mỗi request hay mỗi token còn hiệu lực?
3. **Có cần khó đoán** không? Nonce dùng counter và challenge khó đoán có vai trò khác nhau.
4. **Có phải bí mật** không? Salt và IV phổ biến công khai; bearer token phải bảo vệ.
5. **Kích thước do ai quy định**? Mode/giao thức/entropy mục tiêu, không sử dụng một size cho mọi thứ.
6. **Cần lưu lại gì**? Salt + KDF parameters; nonce + ciphertext; challenge + context/status; token + scope/expiry/revocation.
7. **Thời hạn và tái sử dụng ra sao**? Salt dùng lại để verify; GCM nonce không tái dùng dưới cùng key; challenge thường one-time; token có vòng đời.
8. **Nhiều node và concurrency có thể gây lỗi nào**? Counter lặp, hai request cùng consume challenge/token, đổi khóa và version.
9. **Lộ giá trị gây hậu quả gì**? Lộ salt/nonce thường không trực tiếp cấp quyền, lộ bearer token có thể chiếm quyền.
10. **Đã dùng thư viện/giao thức chuẩn chưa**? Không tự chế một giao thức chỉ vì có CSPRNG và hash.

## 11. Tự kiểm tra (có đáp án)

**Câu 1.** Alice và Bob có cùng mật khẩu, dùng cùng password KDF nhưng salt khác nhau. Verifier có nhất thiết giống nhau không?

**Đáp án:** Không; với salt độc lập, verifier thông thường khác nhau, và đó là mục đích của salt. Xác minh phải dùng salt đã lưu của từng bản ghi.

**Câu 2.** Nonce GCM có thể công khai nên có thể dùng lại dưới cùng khóa không?

**Đáp án:** Không. Tính công khai và tính không lặp là hai yêu cầu độc lập; reuse nonce GCM có thể gây mất bảo mật nghiêm trọng.

**Câu 3.** Bộ đếm tăng dần có thể là nonce không?

**Đáp án:** Có trong giao thức/mode cho phép nonce dự đoán được, nếu quản lý để không lặp qua node/restart. Không thể tự suy rộng sang IV CBC hay mọi giao thức khác.

**Câu 4.** Client chỉ gửi lại challenge ngẫu nhiên mà server phát ra. Vậy đã chứng minh danh tính chưa?

**Đáp án:** Chưa. Cần chứng minh mật mã (ví dụ chữ ký) và server phải kiểm tra context, expiry, replay.

**Câu 5.** 32 byte random token sau khi Base64URL thành 43 ký tự có 344 bit entropy không?

**Đáp án:** Không. Entropy tối đa vẫn là 256 bit của 32 byte nguồn.

**Câu 6.** Salt và session token có thể lưu/truyền giống nhau không?

**Đáp án:** Không. Salt là tham số public của KDF, còn bearer token là secret credential; lộ bearer token có thể cấp quyền cho người lạ.

**Câu 7.** Vì sao hash SHA-256 có thể hợp lý khi lưu verifier của random token 256 bit nhưng không dùng trực tiếp cho password?

**Đáp án:** Token được sinh có entropy cao, gần như không thể đoán brute-force; mật khẩu con người thường có entropy thấp, cần password KDF chậm để chống tấn công offline.

## 12. Tài liệu tham khảo chính thức

- [Java 17 `SecureRandom` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html) — CSPRNG trong JCA.
- [Java 17 `Cipher` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html) — AES-GCM, AAD, tag và giải mã.
- [Java 17 `GCMParameterSpec` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html) — IV và độ dài tag GCM.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final) — đặc tả GCM và ràng buộc IV/nonce.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) — password KDF, salt và pepper.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — entropy và vòng đời session token.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) — reset token, expiry và one-time.
