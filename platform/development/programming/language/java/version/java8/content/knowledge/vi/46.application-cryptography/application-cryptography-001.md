# AES-GCM và mã hóa có xác thực trong Java 8+

> **Chủ đề cha:** Mật mã ứng dụng. AES-GCM (*Advanced Encryption Standard in Galois/Counter Mode*) là chế độ **Authenticated Encryption with Associated Data (AEAD)**: vừa mã hóa dữ liệu để giữ bí mật, vừa xác thực ciphertext và metadata liên quan để phát hiện sửa đổi. Trong Java, API chuẩn là `Cipher` với transformation `AES/GCM/NoPadding`, `GCMParameterSpec`, `SecretKey` và `SecureRandom`. Bài tập trung vào cách sử dụng hiện hành, với các nguyên tắc nonce, tag và quản lý khóa quan trọng hơn vài dòng code gọi cipher.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác biệt giữa **confidentiality**, **integrity** và **authentication**, và vì sao chỉ mã hóa không tự bảo vệ tính toàn vẹn.
2. Hiểu AES-GCM là AEAD: ciphertext được mã hóa và xác thực; AAD được xác thực nhưng vẫn để dạng rõ.
3. Chọn transformation `AES/GCM/NoPadding` và hiểu vì sao GCM không dùng padding kiểu CBC.
4. Dùng khóa AES 128/256-bit, nonce/IV 96-bit và authentication tag 128-bit trong `GCMParameterSpec`.
5. Tuân thủ quy tắc **không tái sử dụng cùng cặp key + nonce khi mã hóa**.
6. Dùng `SecureRandom` để tạo nonce, và hiểu khi nào hệ thống nhiều máy/nhiều tiến trình cần nonce duy nhất theo bộ đếm hoặc giao thức.
7. Gắn metadata vào AAD để ngăn việc chuyển ciphertext sang tenant, record hoặc mục đích khác.
8. Giải mã bằng cùng key, nonce, tag và AAD; xử lý `AEADBadTagException` khi xác thực thất bại.
9. Quản lý key bằng secret manager/KMS, xoay vòng khóa và lưu envelope có version/key ID.
10. Tránh lộ plaintext chưa được xác thực, replay, dùng chung `Cipher` giữa threads và xử lý file lớn bằng một GCM message khổng lồ.
11. Chạy chương trình Java 8 đầy đủ: round-trip, sửa ciphertext/tag/nonce/AAD, sai key và plaintext rỗng đều được kiểm thử.

## 2. Vì sao mã hóa thôi chưa đủ?

Giả sử ứng dụng mã hóa một bản ghi thanh toán. Mã hóa giúp người không có key không đọc được nội dung. Nhưng nếu ứng dụng không xác thực dữ liệu, kẻ tấn công có thể sửa ciphertext hoặc metadata trên đường truyền/lưu trữ. Một thiết kế mật mã ứng dụng cần ít nhất hai thuộc tính:

- **Confidentiality:** người không có key không đọc được plaintext.
- **Integrity/authenticity:** thay đổi dữ liệu được phát hiện; chỉ bên có secret key mới có thể tạo ciphertext/tag hợp lệ.

AES-GCM cung cấp hai thuộc tính đó trong một thao tác AEAD. Nó tạo ciphertext và authentication tag. Khi giải mã, tag được kiểm tra; nếu dữ liệu, AAD, nonce hoặc key không đúng, thao tác hoàn tất thất bại.

### 2.1. AEAD và AAD là gì?

AEAD cho phép bảo vệ hai loại input:

| Thành phần | Mã hóa? | Xác thực? | Ví dụ |
| --- | --- | --- | --- |
| Plaintext | Có | Có | Nội dung đơn hàng, token, payload |
| Additional Authenticated Data (AAD) | Không | Có | Tenant ID, record ID, version |
| Nonce/IV | Không | Là tham số của phép AEAD | 96-bit nonce |
| Authentication tag | Không phải plaintext | Dùng để xác minh | Tag 128-bit gắn với ciphertext |

AAD hữu ích khi metadata cần đọc được để định tuyến nhưng không được phép bị thay đổi. Ví dụ server cần biết tenant hoặc phiên bản format trước khi giải mã; đưa các trường này vào AAD sẽ khiến sửa chúng làm tag kiểm tra thất bại.

**AAD không bí mật.** Đừng đặt password, private key hoặc dữ liệu cần mã hóa vào AAD. AAD phải được cung cấp **đúng cùng bytes và đúng thứ tự** khi decrypt; chỉ thay một trường cũng khiến xác thực không thành công.

### 2.2. AES-GCM không phải chữ ký số

AES-GCM dùng **khóa bí mật đối xứng**. Bên nào có cùng key đều có thể mã hóa và tạo tag hợp lệ. Tag xác nhận dữ liệu được tạo bởi một bên có key, nhưng không chứng minh danh tính cá nhân cụ thể và không tạo tính không thể chối bỏ (*non-repudiation*). Nếu cần chữ ký có thể xác minh công khai, dùng chữ ký số với cặp khóa bất đối xứng theo thiết kế phù hợp.

GCM cũng **không tự ngăn replay**: một ciphertext hợp lệ có thể được gửi lại nguyên vẹn. Nếu nghiệp vụ cần chống phát lại, xác thực sequence number, expiry hoặc transaction ID trong AAD **và** kiểm tra trạng thái replay ở ứng dụng.

## 3. Tham số AES-GCM cần chọn

### 3.1. Transformation: `AES/GCM/NoPadding`

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
```

Tên transformation gồm AES (block cipher), GCM (mode có xác thực) và NoPadding (không dùng padding block kiểu CBC). Luôn chỉ định đầy đủ transformation; tránh `Cipher.getInstance("AES")` rồi phụ thuộc default mode/padding của provider. JCA chuẩn yêu cầu implementation Java hỗ trợ `AES/GCM/NoPadding`; vẫn nên kiểm tra provider/runtime thực tế trong môi trường triển khai.

### 3.2. AES key: 128 hoặc 256 bit

AES hỗ trợ khóa 128, 192 và 256 bit theo chuẩn; các transformation JCA chuẩn nêu rõ hỗ trợ AES-GCM với key 128 và 256 bit. Ví dụ bài dùng **AES-128** để tương thích rộng với Java 8 và policy cũ hơn. AES-128 vẫn là lựa chọn chuẩn mạnh; AES-256 có thể được chọn khi yêu cầu bảo mật/chính sách hệ thống đòi hỏi.

Sinh key bằng `KeyGenerator` và nguồn ngẫu nhiên an toàn:

```java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(128, new SecureRandom());
SecretKey key = generator.generateKey();
```

Không dùng `new SecretKeySpec(password.getBytes(...),"AES")` để biến password tùy ý thành key. Password cần một password-based KDF với salt và work factor thích hợp; với hệ thống production, ưu tiên key được tạo/quản lý bởi KMS/HSM hoặc secret manager. Không hard-code, commit, log hay gửi key cùng ciphertext.

### 3.3. Nonce/IV: 12 bytes (96 bits)

GCM dùng IV/nonce. NIST khuyến nghị implementation hỗ trợ IV 96-bit để tăng tính tương thích, hiệu quả và đơn giản. Trong Java, dùng mảng **12 bytes**:

```java
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);
```

Nonce không phải key, không cần giữ bí mật và thường được lưu cùng ciphertext. Nhưng với **cùng một key**, nonce phải duy nhất cho mỗi lần encrypt. Đây là điều kiện bảo mật cốt lõi của GCM.

### 3.4. Authentication tag: 128 bits

`GCMParameterSpec` nhận độ dài tag theo **bit**, không phải byte:

```java
GCMParameterSpec parameters = new GCMParameterSpec(128, nonce);
```

128 bits = 16 bytes. `Cipher.doFinal` khi encrypt trả về ciphertext có tag được nối ở cuối. Khi decrypt, truyền cả phần ciphertext **và tag** vào `doFinal`; provider xác minh tag trước khi kết luận giải mã thành công.

**Chọn tag 128-bit** cho ứng dụng mới. Tránh cắt ngắn tag để tiết kiệm vài bytes. NIST đã công bố quyết định sửa SP 800-38D theo hướng loại bỏ các tag ngắn hơn 96 bits; publication chính vẫn có planning note về việc sửa đổi, nên môi trường cần FIPS/compliance phải kiểm tra phiên bản hướng dẫn đã được phê duyệt áp dụng.

## 4. Quy tắc quan trọng nhất: không lặp key + nonce

Với AES-GCM, **không bao giờ encrypt hai plaintext khác nhau bằng cùng cặp (key, nonce)**. Lặp nonce dưới cùng key có thể làm suy yếu nghiêm trọng confidentiality và authentication, tạo điều kiện cho tấn công khôi phục thông tin hoặc giả mạo tag. Đây là điều kiện an toàn của mode.

### 4.1. Nonce không cần bí mật, nhưng phải duy nhất theo key

- Có thể lưu nonce cùng ciphertext.
- Khi decrypt, phải sử dụng lại **nonce gốc** của ciphertext đó.
- Khi encrypt message mới bằng cùng key, phải cấp một nonce **chưa từng dùng với key ấy**.
- Không tái sử dụng nonce mặc định như toàn zero, timestamp đơn thuần hoặc counter bị reset sau restart/restore.

**Không nhầm yêu cầu encrypt và decrypt:** decrypt một ciphertext dùng lại nonce của message gốc là bắt buộc. Điều bị cấm là dùng lại cặp key/nonce cho **một lần encrypt khác**.

### 4.2. SecureRandom và giới hạn xác suất va chạm

Một nonce ngẫu nhiên 96-bit được tạo bằng `SecureRandom` là cách phổ biến cho ứng dụng có số lượng encrypt được kiểm soát. Nhưng ngẫu nhiên **không tạo ra bảo đảm tuyệt đối không trùng**: càng nhiều lần sinh dưới cùng key, xác suất va chạm birthday càng tăng. Đặt ngân sách sử dụng theo key và tuân thủ giới hạn của tiêu chuẩn/profile áp dụng.

Trong hệ thống nhiều node, nhiều tiến trình, khối lượng lớn hoặc cần uniqueness có thể kiểm chứng, cân nhắc IV deterministic theo giao thức đã được đánh giá, ví dụ phần cố định phân vùng theo node/session cộng với invocation counter tăng đơn điệu. Bộ đếm phải:
- Được cấp phát không trùng trên tất cả tiến trình cùng key;
- Không quay lại giá trị cũ sau restart/restore backup;
- Không bị race khi nhiều worker encrypt đồng thời;
- Không reset khi key vẫn được giữ nguyên;
- Dừng hoặc rotate key trước khi hết không gian counter.

Không tự ghép hostname + timestamp + counter mà chưa phân tích va chạm, clone/restore, nhiều datacenter và rotation. Nếu không kiểm soát được vòng đời IV, dùng giao thức/kho khóa có quản lý nonce phù hợp.

### 4.3. NIST guidance hiện hành cần đọc cùng profile

NIST SP 800-38D (GCM/GMAC) vẫn là tài liệu nền tảng, nhưng NIST công bố ngày 05-03-2024 quyết định sửa đổi publication, trong đó có đề xuất bỏ hỗ trợ tag ngắn hơn 96 bits và làm rõ cách dựng IV. Hướng dẫn triển khai FIPS 140-3 của NIST/CCCS được cập nhật ngày 09-04-2026 có phần riêng về tính duy nhất của cặp key/IV và các kịch bản sinh IV.

Không lấy một giới hạn cho **một kịch bản validation cụ thể** rồi áp dụng máy móc cho mọi hệ thống. Nếu sản phẩm cần FIPS 140-3, TLS/IPsec hoặc compliance khác, phải theo đúng protocol, module, giới hạn invocation và quy trình key/IV restoration được yêu cầu. Với bài thực hành, dùng nonce 96-bit và tag 128-bit, không tái sử dụng key/nonce.

## 5. AAD: xác thực metadata mà không mã hóa

Giả sử ciphertext được lưu trong database. Các cột tenant, record ID và version được giữ dạng rõ để tìm kiếm/định tuyến. Nếu attacker chuyển ciphertext của record A sang record B, cần xác thực **ngữ cảnh** ứng dụng chứ không chỉ payload.

```java
byte[] aad = (
    "v1|key=orders-key-2026|tenant=42|record=order-123"
).getBytes(StandardCharsets.UTF_8);
```

Khi encrypt, gọi `cipher.updateAAD(aad)` **sau init và trước khi xử lý ciphertext**. Khi decrypt, dựng đúng chuỗi canonical đó và gọi updateAAD trước `doFinal`.

AAD có thể gồm format version, key ID (identifier công khai, không phải key), tenant/account ID, record ID, loại message, sequence number hoặc context nghiệp vụ. Chỉ đưa trường cần xác thực và thống nhất encoding/thứ tự/separator. Với format phức tạp, dùng encoding nhị phân có length-prefix hoặc serialization chuẩn. AAD không bí mật nên không dùng để che metadata.

## 6. Java 8 JCA: encrypt và decrypt

Quy trình encryption:

1. Lấy key AES từ nguồn quản lý khóa.
2. Tạo nonce mới theo chính sách uniqueness của key.
3. Tạo `Cipher` với `AES/GCM/NoPadding`.
4. Khởi tạo `ENCRYPT_MODE` bằng key và `GCMParameterSpec(128,nonce)`.
5. Cung cấp AAD trước dữ liệu.
6. Gọi `doFinal(plaintext)` để nhận ciphertext + tag.
7. Lưu version, key ID, nonce và ciphertext/tag.

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(
        Cipher.ENCRYPT_MODE,
        key,
        new GCMParameterSpec(128, nonce));
cipher.updateAAD(aad);
byte[] ciphertextAndTag = cipher.doFinal(plaintext);
```

Decryption dùng **nonce gốc** và cùng AAD:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(
        Cipher.DECRYPT_MODE,
        key,
        new GCMParameterSpec(128, nonce));
cipher.updateAAD(aad);
byte[] plaintext = cipher.doFinal(ciphertextAndTag);
```

### 6.1. Tag được nối vào ciphertext

Với `doFinal` một lần, output encrypt là:

```text
ciphertextAndTag = encryptedBytes || authenticationTag
```

Nếu tag 128-bit, output dài hơn plaintext đúng **16 bytes** (không tính nonce/AAD/header). Khi decrypt, không tự cắt bỏ tag trước khi gọi `doFinal`. API cần nhận cả chuỗi để kiểm tra xác thực.

### 6.2. `updateAAD` phải chạy trước ciphertext

JCA yêu cầu cung cấp tất cả AAD trước các lời gọi `update`/`doFinal` xử lý ciphertext trong GCM. Đừng gửi một phần ciphertext rồi mới gọi `updateAAD`; thứ tự sai có thể ném `IllegalStateException` hoặc không được provider chấp nhận.

### 6.3. Mỗi operation dùng Cipher đã init với nonce đúng

Không chia sẻ cùng một object `Cipher` cho nhiều thread encrypt/decrypt đồng thời. `Cipher` là stateful: mode, key, IV, AAD và dữ liệu đã xử lý đều thuộc một operation. Tạo/init cipher riêng cho mỗi operation. Không dùng lại IV cho operation encrypt mới chỉ vì object Cipher đã được reset.

## 7. Authentication failure: xử lý `AEADBadTagException`

Khi ciphertext, tag, nonce, AAD hoặc key không khớp, provider không xác minh được tag. Java ném `AEADBadTagException` (là subclass của `BadPaddingException`).

```java
try {
    byte[] plaintext = cipher.doFinal(ciphertextAndTag);
    // Chỉ dùng plaintext sau khi doFinal thành công.
} catch (AEADBadTagException invalidTag) {
    // Từ chối message: không parse, lưu hoặc thực hiện nghiệp vụ.
}
```

**Không coi dữ liệu giải mã trước khi xác thực là dữ liệu đáng tin.** Với thao tác một lần `doFinal`, chỉ trả plaintext khi tag hợp lệ. Với API multi-part, `Cipher.update` trong lúc decrypt có thể tạo output trước khi tag cuối được xác minh; không gửi/ghi/parse output đó như dữ liệu đã xác thực trước khi `doFinal` thành công. Với file lớn, dùng record/chunk độc lập hoặc staging tạm rồi commit sau khi tag đã được kiểm tra.

Ở biên network/API, thường nên trả một lỗi chung cho “message không hợp lệ” thay vì để attacker phân biệt chi tiết sai key, sai tag hay AAD. Không log plaintext, key, raw secret hoặc nội dung nhạy cảm khi xác thực thất bại.


```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmDemo {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int KEY_BITS = 128;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;

    static final class Envelope {
        final byte[] nonce;
        final byte[] ciphertextAndTag;

        Envelope(byte[] nonce, byte[] ciphertextAndTag) {
            this.nonce = nonce.clone();
            this.ciphertextAndTag = ciphertextAndTag.clone();
        }
    }

    private static SecretKey newKey(SecureRandom random)
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(KEY_BITS, random);
        return generator.generateKey();
    }

    private static Envelope encrypt(SecretKey key, byte[] plaintext,
                                    byte[] aad, SecureRandom random)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        GCMParameterSpec parameters =
                new GCMParameterSpec(TAG_BITS, nonce);
        cipher.init(Cipher.ENCRYPT_MODE, key, parameters);
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new Envelope(nonce, ciphertextAndTag);
    }

    private static byte[] decrypt(SecretKey key, Envelope envelope,
                                  byte[] aad)
            throws GeneralSecurityException {
        if (envelope.nonce.length != NONCE_BYTES) {
            throw new IllegalArgumentException("Invalid GCM nonce length");
        }
        if (envelope.ciphertextAndTag.length < TAG_BYTES) {
            throw new IllegalArgumentException("Missing GCM tag");
        }

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        GCMParameterSpec parameters =
                new GCMParameterSpec(TAG_BITS, envelope.nonce);
        cipher.init(Cipher.DECRYPT_MODE, key, parameters);
        cipher.updateAAD(aad);
        return cipher.doFinal(envelope.ciphertextAndTag);
    }

    private static boolean rejects(SecretKey key, Envelope envelope,
                                    byte[] aad)
            throws GeneralSecurityException {
        try {
            decrypt(key, envelope, aad);
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        SecretKey key = newKey(random);
        SecretKey otherKey = newKey(random);

        String text = "Đơn hàng 123: tổng tiền 1.250.000 VND";
        byte[] plaintext = text.getBytes(StandardCharsets.UTF_8);
        byte[] aad = ("v1|key=demo-key-1|tenant=42|record=order-123")
                .getBytes(StandardCharsets.UTF_8);

        Envelope message = encrypt(key, plaintext, aad, random);
        byte[] recovered = decrypt(key, message, aad);
        boolean roundTrip = Arrays.equals(plaintext, recovered);
        boolean tagAppended = message.ciphertextAndTag.length
                == plaintext.length + TAG_BYTES;

        byte[] changedCiphertext = message.ciphertextAndTag.clone();
        changedCiphertext[0] ^= 1;
        Envelope tamperedMessage =
                new Envelope(message.nonce, changedCiphertext);

        byte[] changedTag = message.ciphertextAndTag.clone();
        changedTag[changedTag.length - 1] ^= 1;
        Envelope tamperedTag =
                new Envelope(message.nonce, changedTag);

        byte[] changedNonce = message.nonce.clone();
        changedNonce[0] ^= 1;
        Envelope wrongNonce =
                new Envelope(changedNonce, message.ciphertextAndTag);

        byte[] changedAad =
                "v1|key=demo-key-1|tenant=42|record=order-999"
                        .getBytes(StandardCharsets.UTF_8);

        boolean tamperedCiphertextRejected =
                rejects(key, tamperedMessage, aad);
        boolean tamperedTagRejected = rejects(key, tamperedTag, aad);
        boolean changedNonceRejected = rejects(key, wrongNonce, aad);
        boolean changedAadRejected = rejects(key, message, changedAad);
        boolean wrongKeyRejected = rejects(otherKey, message, aad);

        Envelope empty = encrypt(key, new byte[0], aad, random);
        byte[] emptyRecovered = decrypt(key, empty, aad);
        boolean emptyRoundTrip = emptyRecovered.length == 0
                && empty.ciphertextAndTag.length == TAG_BYTES;

        System.out.println("Transformation: " + TRANSFORMATION);
        System.out.println("AES key bits: " + KEY_BITS);
        System.out.println("Nonce bytes: " + NONCE_BYTES);
        System.out.println("Tag bits: " + TAG_BITS);
        System.out.println("Round trip: " + roundTrip);
        System.out.println("Ciphertext includes tag: " + tagAppended);
        System.out.println("Tampered ciphertext rejected: "
                + tamperedCiphertextRejected);
        System.out.println("Tampered tag rejected: " + tamperedTagRejected);
        System.out.println("Changed nonce rejected: " + changedNonceRejected);
        System.out.println("Changed AAD rejected: " + changedAadRejected);
        System.out.println("Wrong key rejected: " + wrongKeyRejected);
        System.out.println("Empty plaintext round trip: " + emptyRoundTrip);

        if (!roundTrip || !tagAppended || !tamperedCiphertextRejected
                || !tamperedTagRejected || !changedNonceRejected
                || !changedAadRejected || !wrongKeyRejected
                || !emptyRoundTrip) {
            throw new AssertionError("AES-GCM verification failed");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch bằng JDK 17+ với API Java 8, hoặc dùng compiler JDK 8:

```bash
javac --release 8 AesGcmDemo.java
java AesGcmDemo
```

**Stdout đã chạy và kiểm chứng trên OpenJDK 24:**


```text
Transformation: AES/GCM/NoPadding
AES key bits: 128
Nonce bytes: 12
Tag bits: 128
Round trip: true
Ciphertext includes tag: true
Tampered ciphertext rejected: true
Tampered tag rejected: true
Changed nonce rejected: true
Changed AAD rejected: true
Wrong key rejected: true
Empty plaintext round trip: true
Checks passed.
```

### 8.1. Đọc kết quả

- `Round trip: true` chứng minh decrypt với đúng key, nonce và AAD trả lại đúng bytes plaintext ban đầu.
- `Ciphertext includes tag: true` xác nhận output dài hơn plaintext 16 bytes vì tag 128-bit được gắn ở cuối.
- Khi sửa một bit ciphertext, tag, nonce hoặc AAD, `doFinal` không chấp nhận message.
- Dùng key khác cũng làm authentication thất bại; không có plaintext hợp lệ được trả về.
- Plaintext rỗng vẫn được xác thực: ciphertext output lúc này chỉ có tag 16 bytes.
- `Checks passed` chỉ in sau khi mọi điều kiện đều đúng; chương trình dùng `AssertionError` chủ động nên không cần JVM flag `-ea`.

**Giới hạn của demo:** key được tạo trong bộ nhớ để minh họa. Ứng dụng thật phải lấy key từ hệ thống quản lý khóa, lưu nonce cùng ciphertext và có chính sách duy nhất nonce theo key trên toàn hệ thống. Class `Envelope` là cấu trúc truyền dữ liệu trong demo; format lưu trữ production cần version, key ID, giới hạn độ dài và serialization có kiểm tra.

## 9. Lưu trữ ciphertext: envelope cần có gì?

Một record mã hóa thường phải lưu cả tham số công khai cần cho decrypt. Một format đơn giản có thể gồm:

```text
+----------------+------------------+------------------+-----------------------+
| format version | key identifier   | 12-byte nonce    | ciphertext || tag     |
+----------------+------------------+------------------+-----------------------+
                         \_________ AAD context _________/
```

- **Version:** cho phép thay đổi format hoặc thuật toán có kiểm soát.
- **Key ID:** định tuyến đến key hiện hành hoặc key cũ trong quá trình rotation; đây là identifier, không phải secret.
- **Nonce:** bắt buộc để decrypt; không phải dữ liệu bí mật.
- **Ciphertext + tag:** dữ liệu đã mã hóa và tag gắn cuối theo JCA.
- **AAD:** có thể bind version, key ID, tenant và record ID; phải được tái tạo chính xác khi decrypt.

Không lưu key cạnh ciphertext trong cùng bảng/file mà mọi người đọc được. Không log plaintext/key. Nếu dùng Base64 để vận chuyển bytes qua JSON, Base64 chỉ là encoding, **không phải mã hóa**.

### 9.1. Version và key ID nên được xác thực

Nếu version/key ID nằm ngoài ciphertext, kẻ tấn công có thể sửa chúng để gây chọn sai thuật toán hoặc key. Bind các trường quan trọng vào AAD để thay đổi bị phát hiện. Trước khi chọn key, parser vẫn phải kiểm tra version và key ID thuộc allowlist/registry; AAD không thay thế validation cấu trúc.

### 9.2. Key rotation

Một hệ thống có thể có key hiện hành để encrypt record mới, một hoặc nhiều key cũ chỉ dùng decrypt record đã lưu, key ID công khai trong envelope để chọn đúng key và kế hoạch re-encrypt dữ liệu cũ hoặc thời hạn ngừng key. Khi rotate key, mỗi key vẫn phải duy trì uniqueness nonce của riêng nó. Nếu key bị lộ, cần revoke/rotate, đánh giá dữ liệu bị ảnh hưởng và xử lý record theo policy.

## 10. Các lỗi bảo mật và lỗi triển khai thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Dùng cùng key + nonce cho hai lần encrypt | Phá vỡ giả định an toàn của GCM | Đảm bảo nonce unique theo từng key |
| Dùng IV cố định hoặc zero | Mọi message dưới cùng key lặp IV | Sinh/allocate IV đúng protocol |
| Dùng `Random` hoặc timestamp đơn thuần | Nguồn ngẫu nhiên/uniqueness không đủ | `SecureRandom` hoặc counter protocol |
| Nghĩ nonce phải được mã hóa | Không cần; nonce là tham số công khai | Lưu nonce cạnh ciphertext |
| Nghĩ nonce ngẫu nhiên chắc chắn không trùng | Có xác suất birthday collision | Giới hạn usage/key hoặc unique allocation |
| Dùng `AES/ECB` hay CBC không có xác thực | Không có AEAD integrity | Dùng mode AEAD chuẩn như AES-GCM |
| Tự ghép AES + hash/MAC theo ý mình | Dễ sai thứ tự/encoding/verify | Dùng JCA AEAD API chuẩn |
| Dùng tag ngắn để tiết kiệm bytes | Giảm sức mạnh xác thực, có thể trái profile | Dùng tag 128-bit |
| Quên `updateAAD` khi decrypt | Tag không khớp | Dùng đúng AAD đã encrypt |
| Gọi `updateAAD` sau khi xử lý ciphertext | Sai state/vi phạm thứ tự AEAD | Cung cấp AAD trước update/doFinal |
| Dùng `Cipher` chung cho nhiều thread | State/nonce/AAD có thể lẫn | Cipher riêng mỗi operation |
| Tin output từ decrypt update trước tag cuối | Plaintext chưa xác thực có thể bị dùng | Chỉ commit sau doFinal thành công |
| Chỉ kiểm tra ciphertext length | Không chứng minh message hợp lệ | Luôn xác minh tag |
| Cho exception khác nhau tiết lộ key/AAD nào sai | Tạo oracle cho attacker | Lỗi bên ngoài chung, log an toàn |
| Đưa password thô thành AES key | Entropy/độ dài không đạt | KDF có salt/work factor hoặc KMS |
| Hard-code key trong source | Lộ qua repo/build/log | Secret manager/KMS/HSM |
| Lưu key cùng ciphertext | Attacker lấy cả hai | Tách quyền truy cập và storage |
| Nghĩ AEAD tự ngăn replay | Message hợp lệ vẫn có thể gửi lại | Sequence/expiry/replay state |
| Nghĩ GCM che độ dài message | Length vẫn quan sát được | Padding ở tầng protocol nếu cần |
| Mã hóa file lớn trong một mảng | OOM/giới hạn invocation | Chunk/record AEAD có nonce riêng |
| Tự phát minh counter IV nhiều node | Collision khi restart/clone/scale | Protocol/allocator được đánh giá |

## 11. File lớn và mã hóa theo chunk

Không nên nạp file nhiều GB vào một `byte[]` chỉ để gọi `doFinal` một lần. GCM có giới hạn kích thước cho mỗi invocation và giữ toàn bộ plaintext/ciphertext trong RAM không mở rộng tốt.

Với file lớn, thiết kế **mỗi chunk như một record AEAD độc lập**:
1. Chia input thành chunks có kích thước giới hạn.
2. Mỗi chunk dùng nonce **không trùng dưới cùng key**; không tái sử dụng nonce chỉ vì sequence number giống giữa các file.
3. Bind file ID, chunk index, version và trạng thái final vào AAD.
4. Ghi ciphertext/tag của chunk cùng metadata cần thiết.
5. Khi decrypt, xác minh tag của từng chunk trước khi phát dữ liệu đã xác thực.
6. Dùng manifest/tổng số chunks/total length được xác thực để phát hiện thiếu, lặp, đổi thứ tự hoặc cắt cụt file.

Có thể derive nonce từ nonce-prefix duy nhất cho file/session cộng với counter chunk, nhưng prefix phải được cấp unique theo key và counter không reset. Đây là **protocol design**, không chỉ nối bytes cho tiện; phải review collision, resume và retry. Sequence/index trong AAD giúp phát hiện đặt chunk vào vị trí sai.

Không phát plaintext từ `Cipher.update` ra file đích cuối trước khi xác minh tag cuối của chunk. Dùng staging tạm rồi commit chunk sau khi `doFinal` thành công. Nếu cần atomicity cho cả file, còn phải kiểm tra manifest và toàn bộ chunks trước khi đánh dấu file hoàn chỉnh.

## 12. Replay, ordering và ngữ cảnh ứng dụng

GCM xác thực tính toàn vẹn của **một message**, không đảm bảo message đó mới hoặc được gửi đúng thứ tự. Kẻ tấn công có thể ghi lại envelope hợp lệ rồi gửi lần nữa; tag vẫn đúng.

Nếu chống replay là yêu cầu:
- Gắn message ID/sequence number/epoch vào AAD;
- Kiểm tra sequence/ID đã dùng trong store có đồng bộ và retention phù hợp;
- Xác thực expiry hoặc session context;
- Thực hiện cập nhật replay state cùng transaction nghiệp vụ;
- Không dựa vào timestamp đơn độc nếu clock skew có thể bị điều khiển.

AAD chỉ đảm bảo trường sequence không bị sửa mà không phát hiện; **ứng dụng vẫn phải từ chối sequence đã xử lý**. Tag hợp lệ không thay thế business-level deduplication.

## 13. Quản lý khóa trong production

### 13.1. Tạo và lưu khóa

Dùng `KeyGenerator`/KMS để sinh key ngẫu nhiên, không tự chọn chuỗi dễ đoán. Key cần identifier và thuật toán/độ dài rõ ràng, quyền truy cập tối thiểu, rotation/revoke/backup policy, audit và quy tắc không xuất key thô nếu KMS có thể encrypt/decrypt trực tiếp.

### 13.2. Password không phải key

Nếu ứng dụng buộc phải dùng password do người dùng nhập, không lấy bytes của password làm AES key. Dùng password-based key derivation với salt ngẫu nhiên và work factor đã được đánh giá; lưu salt/parameters cạnh ciphertext. Khi có thể, sử dụng cơ chế quản lý secret/credential chuyên dụng.

### 13.3. Key separation

Không dùng một AES key cho nhiều mục đích không liên quan chỉ vì “cùng là bí mật”. Dùng key riêng theo purpose/protocol hoặc KDF có context separation theo thiết kế chuẩn. AAD có thể bind key ID/purpose để tránh nhầm record, nhưng không thay thế key separation.

## 14. Giới hạn và cách kiểm thử

| Test | Kết quả mong đợi |
| --- | --- |
| Encrypt rồi decrypt với cùng key/nonce/AAD | Plaintext giống từng byte |
| Thay một bit ciphertext | Authentication fail |
| Thay một bit tag | Authentication fail |
| Thay nonce | Authentication fail |
| Thay AAD (tenant/record/version) | Authentication fail |
| Dùng key khác | Authentication fail |
| Plaintext rỗng | Vẫn có tag hợp lệ và decrypt về rỗng |
| Binary chứa byte 0 và mọi giá trị byte | Round-trip chính xác |
| Nhiều lần encrypt cùng key | Nonce allocator không lặp |
| Restart/restore nhiều node | Không reset counter/nonce namespace |
| Record từ tenant khác | AAD context không cho phép hoán đổi |
| Message bị replay | Application-level sequence/ID từ chối |
| Ciphertext bị truncate | Tag verification fail |
| Key rotation | Record cũ chọn key đúng, record mới dùng key mới |
| Input quá lớn | Giới hạn kích thước/streaming policy hoạt động |

Trong hệ thống cần compliance, dùng test vectors chính thức và kiểm tra provider/module đã được đánh giá phù hợp. Một demo round-trip thành công **không chứng minh** triển khai đạt FIPS, an toàn nonce trên cluster hay quản lý key đúng.

## 15. Java 8 và các lựa chọn phiên bản

Các thành phần trong chương trình thực hành có sẵn từ Java 8: `Cipher` và `AES/GCM/NoPadding`; `GCMParameterSpec`; `AEADBadTagException`; `KeyGenerator`, `SecretKey`, `SecureRandom`; `StandardCharsets.UTF_8`.

Không cần thư viện mật mã ngoài cho ví dụ cơ bản. Trong production, có thể dùng KMS/secret manager/provider được phê duyệt để quản lý key; đó là phần hạ tầng bổ sung, không thay đổi hợp đồng AEAD của GCM.

AES-GCM là mode hiện hành, nhưng yêu cầu về tag, IV construction, key size, usage limits và provider validation phụ thuộc tiêu chuẩn/profile triển khai. Không sao chép cấu hình cũ chỉ vì code vẫn compile; xem JDK/provider và profile bảo mật tổ chức đang yêu cầu.

## 16. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — Cipher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html): transformation, AEAD, thứ tự AAD, tag được nối/xác minh và `AEADBadTagException`.
- [Oracle Java SE 26 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): IV và độ dài authentication tag theo bit.
- [Oracle Java SE 8 — Cipher](https://docs.oracle.com/javase/8/docs/api/javax/crypto/Cipher.html): AES-GCM, AAD và yêu cầu không lặp IV với cùng key trong Java 8.
- [Oracle Java SE 8 — AEADBadTagException](https://docs.oracle.com/javase/8/docs/api/javax/crypto/AEADBadTagException.html): exception khi tag không xác minh được.
- [Oracle Java 8 JCA Reference Guide — AES with GCM](https://docs.oracle.com/javase/8/docs/technotes/guides/security/crypto/CryptoSpec.html): ví dụ encrypt/decrypt GCM và quy tắc AAD/IV.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): đặc tả GCM, IV uniqueness và AEAD; trang NIST hiện ghi publication đang được sửa đổi.
- [NIST — Decision to revise SP 800-38D](https://www.nist.gov/news-events/news/2024/03/nist-revise-special-publication-800-38d-galoiscounter-mode-gcm-and-gmac): kế hoạch cập nhật tag/IV và tham chiếu.
- [NIST FIPS 140-3 Implementation Guidance, C.H](https://csrc.nist.gov/csrc/media/Projects/cryptographic-module-validation-program/documents/fips%20140-3/FIPS%20140-3%20IG.pdf): hướng dẫn hiện hành về uniqueness của key/IV cho validation.

**Ghi nhớ:** AES-GCM cung cấp bí mật và xác thực trong cùng một AEAD operation. Chọn `AES/GCM/NoPadding`, key được quản lý an toàn, nonce 96-bit **không bao giờ lặp dưới cùng key**, tag 128-bit và AAD canonical. Chỉ dùng plaintext sau khi `doFinal` xác minh tag thành công. Xử lý key lifecycle, replay, nonce allocation đa node và format lưu trữ như các phần của cùng một thiết kế bảo mật.
