# Kiểm tra thẻ xác thực và xử lý dữ liệu bị sửa trong Java

Khi ứng dụng nhận ciphertext, message hoặc token từ mạng, database hay file, nó phải xác định **dữ liệu có còn nguyên vẹn và có được tạo bởi một bên nắm giữ khóa hợp lệ hay không** trước khi tin hoặc xử lý nội dung. Java có các API chuẩn cho việc này: **AEAD** qua `Cipher` (ví dụ `AES/GCM/NoPadding`), **HMAC** qua `Mac` và **chữ ký số** qua `Signature`.

Một **authentication tag** là giá trị mật mã dùng để phát hiện thay đổi đối với ciphertext và/hoặc dữ liệu liên quan. Khi tag không hợp lệ, ứng dụng phải **từ chối dữ liệu và không thực hiện side effect dựa trên plaintext đó**. Cần phân biệt tag mật mã này với bearer token hay mã xác thực đăng nhập ở tầng nghiệp vụ.

Bài thuộc chủ đề **Mật mã ứng dụng**, tập trung vào kiến thức còn được hỗ trợ: AES-GCM, AAD, `AEADBadTagException`, HMAC-SHA-256, so sánh an toàn bằng `MessageDigest.isEqual`, chữ ký Ed25519 trong JDK mới, nonce/IV, chống replay, quản lý khóa và format envelope. Các API nền tảng AES-GCM, `Mac`, `MessageDigest` và `Signature` có từ Java 8 hoặc sớm hơn; **Ed25519 có trong JDK từ Java 15**. Sáu chương trình Java 17+ độc lập đã được biên dịch và chạy kiểm tra trên JDK 24.

> **Nguyên tắc:** chỉ sử dụng plaintext sau khi thuật toán xác thực hoàn tất thành công.

## 1. Toàn vẹn, xác thực và bí mật

| Thuộc tính | Câu hỏi | Cơ chế thường dùng |
| --- | --- | --- |
| Confidentiality | Người không có quyền có đọc được nội dung không? | Mã hóa bằng khóa |
| Integrity | Nội dung có bị thay đổi không? | MAC, AEAD, chữ ký số |
| Authenticity | Dữ liệu có được tạo bởi bên sở hữu khóa hợp lệ không? | HMAC với shared key, chữ ký với private key |

**AES-GCM** vừa mã hóa plaintext vừa xác thực ciphertext và AAD. **HMAC** xác thực dữ liệu nhưng không mã hóa nó. **Chữ ký số** cho phép kiểm tra bằng public key rằng dữ liệu được ký bởi private key tương ứng; chữ ký không che giấu nội dung.

Một hàm hash không khóa như SHA-256 chỉ tạo fingerprint. Nếu attacker sửa message rồi tự tính lại SHA-256, hash mới vẫn khớp message đã sửa. Vì vậy **hash đơn thuần không phải message authentication code**. CRC/checksum hữu ích để phát hiện lỗi ngẫu nhiên, nhưng không chống người chủ động sửa dữ liệu vì họ có thể tính lại checksum.

## 2. Chọn AEAD, HMAC hay chữ ký số?

| Cơ chế | Java API | Xác thực gì? | Mã hóa nội dung? |
| --- | --- | --- | --- |
| AEAD (AES-GCM) | `Cipher` + `GCMParameterSpec` | Ciphertext, tag, nonce/IV và AAD | Có |
| HMAC | `Mac.getInstance("HmacSHA256")` | Message và tag bằng secret chia sẻ | Không |
| Chữ ký số | `Signature` | Message và signature bằng cặp private/public key | Không |

- Hai bên cùng sở hữu secret, cần cả bí mật lẫn toàn vẹn: chọn **AEAD**.
- Nội dung được phép đọc nhưng cần phát hiện sửa đổi: chọn **HMAC**.
- Một bên ký, nhiều bên xác minh bằng public key: chọn **chữ ký số**.
- Không tự ghép primitive theo phỏng đoán; dùng protocol/thư viện chuẩn đã được review.

Không gọi HMAC là chữ ký số: mọi bên có shared key đều có thể tạo HMAC hợp lệ. Không gọi GCM tag là xác thực người dùng: nó chỉ chứng minh dữ liệu khớp key và tham số tương ứng.

## 3. AEAD và authentication tag

AEAD là *Authenticated Encryption with Associated Data*. Một lần mã hóa nhận:
1. **Key** — khóa bí mật.
2. **Nonce** — giá trị phải duy nhất theo yêu cầu của thuật toán với cùng key.
3. **Plaintext** — nội dung được mã hóa và xác thực.
4. **AAD** — dữ liệu được xác thực nhưng không mã hóa.

Kết quả là ciphertext kèm tag. Khi giải mã, thuật toán xác minh tag; nếu ciphertext, AAD, nonce hoặc tag không khớp, authenticated decryption thất bại.

```text
Key + Nonce + Plaintext + AAD
              |
              v
        AEAD Encryption
              |
              v
     Ciphertext || Tag

Key + Nonce + AAD + Ciphertext || Tag
              |
              v
        AEAD Decryption
              |
       +------+------+
       |             |
       v             v
  Tag hợp lệ     Tag sai
       |             |
       v             v
  Plaintext       FAIL / REJECT
```

AAD thường ràng buộc metadata như version envelope, loại bản ghi, tenant ID hoặc record ID. AAD vẫn nhìn thấy được; tag bảo vệ tính toàn vẹn của nó. Nếu metadata thay đổi, tag verification phải thất bại.

Tag không chứng minh một người cụ thể gửi dữ liệu nếu nhiều hệ thống cùng sở hữu shared key. Bất kỳ bên nào có key đều có thể tạo tag hợp lệ. Nếu cần danh tính signer trong mô hình nhiều người xác minh, cân nhắc chữ ký số và quản lý public key đáng tin cậy.

## 4. AES-GCM và GCMParameterSpec

Transformation phổ biến:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
```

`AES` là block cipher; `GCM` là chế độ authenticated encryption; `NoPadding` là tên transformation chuẩn. GCM không dùng padding kiểu CBC/PKCS5.

GCM cần IV/nonce và độ dài tag. Java dùng:

```java
GCMParameterSpec params =
        new GCMParameterSpec(128, nonce);
```

- Tham số đầu là độ dài tag tính bằng **bit**; `128` tương ứng **16 byte**.
- Tham số thứ hai là IV/nonce bytes.
- **96-bit (12-byte) nonce** là độ dài thông dụng được khuyến nghị cho GCM.
- Nonce không cần bí mật; thường lưu/truyền kèm ciphertext để bên nhận giải mã.
- Với GCM, **không được lặp lại cùng cặp key + nonce** cho hai lần mã hóa khác nhau.

`GCMParameterSpec` có từ Java 7; dùng được trong Java 8+. Oracle JCA guide có ví dụ AES/GCM và yêu cầu AAD được cung cấp trước ciphertext. Xem [Java 8 JCA Guide](https://docs.oracle.com/javase/8/docs/technotes/guides/security/crypto/CryptoSpec.html) và [GCMParameterSpec Java 8](https://docs.oracle.com/javase/8/docs/api/javax/crypto/spec/GCMParameterSpec.html).

## 5. Nonce/IV: uniqueness là yêu cầu sống còn

Nonce **không phải password** và không cần giữ bí mật, nhưng phải đáp ứng uniqueness theo từng khóa:
- Không hardcode một IV rồi dùng lại với cùng key cho mọi bản ghi.
- Không dùng timestamp đơn thuần nếu nhiều tiến trình có thể tạo cùng thời điểm hoặc đồng hồ bị lùi.
- Không dùng counter chỉ trong RAM nếu restart có thể reset counter.
- Nếu nhiều node cùng key, phải phối hợp cách cấp nonce giữa các node.
- Với hệ thống lưu lượng cao, dùng nonce allocator có bảo đảm uniqueness (counter/prefix được quản lý bền vững), giới hạn số lần gọi và chính sách rotate key.
- Sinh nonce ngẫu nhiên bằng `SecureRandom` là pattern phổ biến cho workload được giới hạn, nhưng **randomness không biến uniqueness thành bảo đảm tuyệt đối**; phải đánh giá collision risk và giới hạn sử dụng key.

Ví dụ sinh nonce cho một lần mã hóa:

```java
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);
```

Đây là demo nguồn random mật mã, **không phải nonce allocator đầy đủ cho hệ thống phân tán/lưu lượng cao**. Mỗi lần mã hóa dưới cùng key phải nhận nonce mới theo policy đã thiết kế. Nếu không thể bảo đảm, dùng thư viện/dịch vụ quản lý key và nonce đã được review.

NIST SP 800-38D quy định uniqueness của IV GCM; RFC 5116 cũng nêu nonce phải duy nhất cho mỗi invocation với cùng key. Trang NIST ghi nhận SP 800-38D đang được lên kế hoạch sửa đổi, nên hệ thống tuân thủ chuẩn cần theo dõi policy/ấn bản hiện hành.

## 6. AAD: xác thực metadata, không che giấu metadata

AAD:
- Không được mã hóa; người nhận vẫn nhìn thấy.
- Được gắn với ciphertext bằng tag.
- Bên giải mã phải cung cấp **đúng từng byte AAD** như lúc mã hóa.
- Nếu AAD thay đổi, tag không còn hợp lệ.
- Phải có encoding không mơ hồ.

Ví dụ:

```java
byte[] aad = "v1|orders|order-42"
        .getBytes(StandardCharsets.UTF_8);
cipher.updateAAD(aad);
```

Nếu metadata có nhiều trường variable-length, không nối chuỗi bằng delimiter có thể xuất hiện trong dữ liệu. Dùng serialization canonical hoặc length-prefixed encoding. Cùng logical metadata phải tạo cùng dãy AAD bytes ở cả hai đầu.

Các trường phù hợp: version, tenant ID, record ID, loại nội dung, purpose/domain separator. Nếu cần ràng buộc user ID, lấy giá trị từ trusted context; tag không tự chứng minh identity của người đang request.

## 7. Thứ tự thao tác Cipher: AAD phải đi trước dữ liệu

Mã hóa:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.ENCRYPT_MODE, key,
        new GCMParameterSpec(128, nonce));
cipher.updateAAD(aad);
byte[] ciphertextAndTag = cipher.doFinal(plaintext);
```

Giải mã:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.DECRYPT_MODE, key,
        new GCMParameterSpec(128, nonce));
cipher.updateAAD(aad);
byte[] plaintext = cipher.doFinal(ciphertextAndTag);
```

Với GCM/CCM, **mọi AAD phải được đưa vào trước khi bắt đầu xử lý ciphertext** bằng `update`/`doFinal`. Gọi `updateAAD` sau khi xử lý ciphertext có thể gây `IllegalStateException`.

Trong JCE, output mã hóa từ `doFinal` chứa ciphertext và authentication tag nối tiếp nhau. Khi decrypt, truyền nguyên phần ciphertext+tag vào `doFinal`; provider kiểm tra tag.

**Không tự cắt tag rồi so sánh bằng `Arrays.equals`.** Việc xác minh phải do AEAD implementation thực hiện.

## 8. `AEADBadTagException` có nghĩa gì?

`javax.crypto.AEADBadTagException` được ném khi Cipher ở AEAD mode (như GCM/CCM) không thể xác minh authentication tag. Nó là subclass của `BadPaddingException` và có từ Java 7.

Nguyên nhân có thể gồm ciphertext bị sửa/cắt, tag bị sửa, AAD khác, nonce khác, dùng nhầm key/key version hoặc ghép nhầm tag giữa các record. Tag failure không tự chứng minh có tấn công; nó cho biết ứng dụng **không thể xác thực bộ input hiện tại**.

```java
try {
    byte[] plaintext = cipher.doFinal(ciphertextAndTag);
    // Chỉ sử dụng plaintext sau khi doFinal thành công.
} catch (AEADBadTagException ex) {
    // Từ chối bản ghi; không xử lý plaintext.
}
```

Method thật cần xử lý các lỗi mật mã khác như `GeneralSecurityException` và envelope malformed. Nếu catch `BadPaddingException` rộng hơn, đặt catch `AEADBadTagException` trước catch cha.
## 9. Chương trình 1 — AES-GCM round trip có AAD

Tệp `AesGcmRoundTripDemo.java`:

```java
import java.util.Arrays;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmRoundTripDemo {
    static byte[] aad(String recordId) {
        return ("v1|orders|" + recordId)
                .getBytes(StandardCharsets.UTF_8);
    }

    static byte[] encrypt(
            SecretKey key, byte[] nonce,
            byte[] associated, byte[] plaintext)
            throws GeneralSecurityException {
        Cipher cipher =
                Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(associated);
        return cipher.doFinal(plaintext);
    }

    static byte[] decrypt(
            SecretKey key, byte[] nonce,
            byte[] associated, byte[] sealed)
            throws GeneralSecurityException {
        Cipher cipher =
                Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(associated);
        return cipher.doFinal(sealed);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        byte[] plaintext =
                "amount=2500;currency=VND"
                        .getBytes(StandardCharsets.UTF_8);

        byte[] sealed = encrypt(
                key, nonce, aad("order-42"), plaintext);

        byte[] restored = decrypt(
                key, nonce, aad("order-42"), sealed);

        System.out.println(
                "roundtrip=" +
                Arrays.equals(plaintext, restored));
        System.out.println(
                "plaintext=" +
                new String(restored, StandardCharsets.UTF_8));
        System.out.println(
                "tag bytes=" + (sealed.length - plaintext.length));
        System.out.println("nonce bytes=" + nonce.length);
    }
}
```

```bash
javac -encoding UTF-8 AesGcmRoundTripDemo.java
java AesGcmRoundTripDemo
```

Đầu ra đã kiểm thử:

```text
roundtrip=true
plaintext=amount=2500;currency=VND
tag bytes=16
nonce bytes=12
```

Tag dài 16 byte là 128 bit; nonce dài 12 byte là 96 bit. Ví dụ sinh key mới và nonce ngẫu nhiên cho một lần chạy. Ứng dụng thật phải lưu/đọc key từ kho quản lý phù hợp và đảm bảo không tái sử dụng nonce với cùng key.

## 10. Chương trình 2 — phát hiện sửa ciphertext, tag, AAD, nonce và key

Tệp `AeadTamperDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AeadTamperDemo {
    static byte[] aad(String id) {
        return ("v1|" + id).getBytes(StandardCharsets.UTF_8);
    }

    static byte[] seal(
            SecretKey key, byte[] nonce,
            byte[] associated, byte[] plaintext) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(associated);
        return cipher.doFinal(plaintext);
    }

    static boolean accepted(
            SecretKey key, byte[] nonce,
            byte[] associated, byte[] sealed) throws Exception {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key,
                    new GCMParameterSpec(128, nonce));
            cipher.updateAAD(associated);
            cipher.doFinal(sealed);
            return true;
        } catch (AEADBadTagException ex) {
            return false;
        }
    }

    static byte[] flip(byte[] source, int index) {
        byte[] changed = source.clone();
        changed[index] ^= 1;
        return changed;
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();
        SecretKey otherKey = generator.generateKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        byte[] associated = aad("record-7");
        byte[] plaintext =
                "status=approved".getBytes(StandardCharsets.UTF_8);
        byte[] sealed = seal(key, nonce, associated, plaintext);

        System.out.println(
                "valid accepted=" +
                accepted(key, nonce, associated, sealed));
        System.out.println(
                "ciphertext tampered rejected=" +
                !accepted(key, nonce, associated, flip(sealed, 0)));
        System.out.println(
                "tag tampered rejected=" +
                !accepted(key, nonce, associated,
                        flip(sealed, sealed.length - 1)));
        System.out.println(
                "AAD tampered rejected=" +
                !accepted(key, nonce, aad("record-8"), sealed));
        System.out.println(
                "nonce tampered rejected=" +
                !accepted(key, flip(nonce, 0), associated, sealed));
        System.out.println(
                "wrong key rejected=" +
                !accepted(otherKey, nonce, associated, sealed));
    }
}
```

```bash
javac -encoding UTF-8 AeadTamperDemo.java
java AeadTamperDemo
```

```text
valid accepted=true
ciphertext tampered rejected=true
tag tampered rejected=true
AAD tampered rejected=true
nonce tampered rejected=true
wrong key rejected=true
```

Ví dụ lật một bit trong từng thành phần. Cả ciphertext lẫn tag đều được xác thực; AAD và nonce không cần mã hóa để được ràng buộc vào kết quả. Với wrong key, tag cũng không khớp.

Trong hệ thống thực, không nên trả về cho client chi tiết “sai key”, “sai tag”, “sai record ID” nếu điều đó giúp xây dựng oracle. Thường trả lỗi chung như **không thể xác thực dữ liệu**; log nội bộ chỉ ghi mã sự kiện/record ID đã làm sạch, không ghi key, plaintext hoặc tag nhạy cảm.

## 11. Plaintext chỉ được tin sau khi tag verification hoàn tất

Với lời gọi một lần `doFinal(ciphertextAndTag)`, ứng dụng chỉ nhận kết quả khi operation thành công. Nếu dùng API nhiều phần `update` + `doFinal`, tag chỉ được xác minh hoàn tất ở `doFinal`.

- Không gửi bytes plaintext tạm thời từ `update` sang business logic.
- Không parse JSON, ghi database, thực thi command hoặc tạo side effect trước khi tag hợp lệ.
- Buffer plaintext tạm thời đến khi `doFinal` thành công; nếu thất bại, discard toàn bộ.
- Với payload rất lớn, dùng cách spool/buffer an toàn hoặc thư viện authenticated streaming được thiết kế đúng.
- Nếu không thể giữ đủ dữ liệu trong RAM, chọn protocol/library có authenticated streaming rõ ràng; không tự cắt message thành chunks mà thiếu thiết kế chống reorder/truncate.

**Không xử lý phần plaintext nhận được trước khi tag sai.** Dữ liệu đó chưa được xác thực, dù trông như JSON hợp lệ.

## 12. Envelope: lưu nonce, ciphertext, tag và version

Một envelope tối thiểu:

```text
+---------+-------------+-------------------------+
| version | nonce (12B) | ciphertext || tag (16B+)|
+---------+-------------+-------------------------+
```

Hệ thống thực tế thường có thêm `keyId` để biết key version nào giải mã. Format nên xác định rõ magic/version, key ID, nonce, ciphertext kèm tag và metadata công khai.

Bên nhận cần:
1. Validate độ dài tối thiểu/tối đa và version trước khi cấp phát buffer lớn.
2. Tra key ID trong danh sách key version được phép.
3. Tạo AAD từ format và context tin cậy.
4. Giải mã và chờ tag verification thành công.
5. Chỉ sau đó mới chấp nhận plaintext và ghi nhận replay state nếu cần.

Các field quan trọng cần được xác thực bằng AAD. Key ID có thể cần đọc trước để chọn key, nhưng phải nằm trong allowlist/key store; tag phải ràng buộc key ID đó.

## 13. Chương trình 3 — kiểm tra envelope và dữ liệu bị cắt

Tệp `EnvelopeValidationDemo.java`:

```java
import java.util.Arrays;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class EnvelopeValidationDemo {
    static final int NONCE_BYTES = 12;
    static final int TAG_BYTES = 16;

    static byte[] join(byte[] nonce, byte[] sealed) {
        byte[] envelope =
                Arrays.copyOf(nonce, nonce.length + sealed.length);
        System.arraycopy(
                sealed, 0, envelope, nonce.length, sealed.length);
        return envelope;
    }

    static byte[] open(
            SecretKey key, byte[] envelope, byte[] associated)
            throws Exception {
        if (envelope == null
                || envelope.length < NONCE_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Malformed envelope");
        }

        byte[] nonce = Arrays.copyOfRange(
                envelope, 0, NONCE_BYTES);
        byte[] sealed = Arrays.copyOfRange(
                envelope, NONCE_BYTES, envelope.length);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(associated);
        return cipher.doFinal(sealed);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[NONCE_BYTES];
        new SecureRandom().nextBytes(nonce);
        byte[] associated =
                "v1|document-9".getBytes(StandardCharsets.UTF_8);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(associated);

        byte[] sealed = cipher.doFinal(
                "private document".getBytes(StandardCharsets.UTF_8));
        byte[] envelope = join(nonce, sealed);

        System.out.println(
                "valid envelope=" +
                new String(
                        open(key, envelope, associated),
                        StandardCharsets.UTF_8));

        try {
            open(key, Arrays.copyOf(envelope, 10), associated);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "truncated envelope rejected=true");
        }

        byte[] changed = envelope.clone();
        changed[changed.length - 1] ^= 1;

        try {
            open(key, changed, associated);
            System.out.println("tampered envelope accepted=true");
        } catch (AEADBadTagException ex) {
            System.out.println(
                    "tampered envelope rejected=true");
        }
    }
}
```

```bash
javac -encoding UTF-8 EnvelopeValidationDemo.java
java EnvelopeValidationDemo
```

```text
valid envelope=private document
truncated envelope rejected=true
tampered envelope rejected=true
```

Đây là format minh họa, không phải chuẩn serialization dùng chung cho mọi hệ thống. Code cố định nonce 12 byte và tag tối thiểu 16 byte theo cấu hình 128-bit. Ứng dụng thực phải thêm version/key ID và kiểm soát maximum envelope length trước khi tạo mảng; AAD cũng phải bao gồm các field cần chống sửa.
## 14. HMAC: xác thực dữ liệu không cần mã hóa

**HMAC** là MAC dựa trên hash và secret key được chia sẻ giữa bên tạo và bên kiểm tra. Java dùng `javax.crypto.Mac`:

```java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(secretKey);
byte[] tag = mac.doFinal(message);
```

HMAC-SHA-256 tạo tag **32 byte**. Bên nhận tính lại HMAC từ đúng message bytes bằng cùng secret key, sau đó so sánh tag nhận được. Nếu message hoặc tag bị sửa, kiểm tra thất bại.

HMAC phù hợp khi nội dung được phép đọc nhưng cần phát hiện sửa đổi. HMAC **không cung cấp confidentiality**; ai có shared key đều có thể tạo HMAC hợp lệ. Nếu cần nhiều bên xác minh nhưng không được ký thay nhau, chữ ký số phù hợp hơn.

Dùng `HmacSHA256` hoặc thuật toán HMAC hiện hành theo security policy. Tránh tự thiết kế MAC bằng `SHA256(key || message)`; dùng HMAC chuẩn.

## 15. So sánh HMAC tag bằng MessageDigest.isEqual

Không nên so sánh tag bí mật bằng `Arrays.equals` nếu có thể tạo timing side-channel. Dùng:

```java
boolean valid =
        MessageDigest.isEqual(expectedTag, receivedTag);
```

`MessageDigest.isEqual` là phép so sánh digest. Thời gian so sánh phụ thuộc độ dài đối số thứ nhất (với đối số thứ hai khác null và không rỗng), không phụ thuộc nội dung các byte của đối số thứ hai. Vì vậy tính `expectedTag` ở phía server, kiểm tra tag nhận vào không null và có độ dài chuẩn, đưa `expectedTag` làm đối số đầu và dùng `MessageDigest.isEqual(expectedTag, receivedTag)`. Không log tag hoặc secret key.

So sánh độ dài có thể thực hiện trước; độ dài tag là metadata công khai. Đừng dùng `MessageDigest.isEqual` để so sánh password thô hay thay thế password hashing.

Với AEAD, không tự trích tag rồi gọi `MessageDigest.isEqual`; hãy để `Cipher.doFinal` thực hiện authenticated decryption.
## 16. Chương trình 4 — HMAC-SHA-256 và phát hiện dữ liệu sửa

Tệp `HmacVerifyDemo.java`:

```java
import java.util.Arrays;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

public class HmacVerifyDemo {
    static byte[] calculate(
            SecretKey key, byte[] data) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        return mac.doFinal(data);
    }

    static boolean verify(
            SecretKey key, byte[] data, byte[] supplied)
            throws Exception {
        byte[] expected = calculate(key, data);
        return supplied != null
                && supplied.length == expected.length
                && MessageDigest.isEqual(expected, supplied);
    }

    static byte[] flip(byte[] source, int index) {
        byte[] changed = source.clone();
        changed[index] ^= 1;
        return changed;
    }

    public static void main(String[] args) throws Exception {
        byte[] rawKey = new byte[32];
        new SecureRandom().nextBytes(rawKey);
        SecretKey key =
                new SecretKeySpec(rawKey, "HmacSHA256");

        byte[] message =
                "user=alice|role=reader|expires=2030-01-01"
                        .getBytes(StandardCharsets.UTF_8);
        byte[] tag = calculate(key, message);

        System.out.println("tag bytes=" + tag.length);
        System.out.println("valid=" + verify(key, message, tag));
        System.out.println(
                "modified data accepted=" +
                verify(key, flip(message, 0), tag));
        System.out.println(
                "modified tag accepted=" +
                verify(key, message, flip(tag, 0)));
        System.out.println(
                "truncated tag accepted=" +
                verify(
                        key, message,
                        Arrays.copyOf(tag, tag.length - 1)));
    }
}
```

```bash
javac -encoding UTF-8 HmacVerifyDemo.java
java HmacVerifyDemo
```

```text
tag bytes=32
valid=true
modified data accepted=false
modified tag accepted=false
truncated tag accepted=false
```

Ví dụ tạo key ngẫu nhiên trong memory. Hệ thống thực cần key lifecycle rõ ràng: tạo key bằng KMS/KeyStore hoặc secret manager, phân phối an toàn, rotation, access control và tách key theo purpose. **Không tạo một key mới ở mỗi lần verify**, nếu không bên nhận không thể tính lại tag từ key đã dùng.
## 17. Canonical message: xác thực đúng toàn bộ trường

HMAC/AEAD chỉ xác thực chính xác byte sequence được đưa vào. Nếu ứng dụng có nhiều trường, cần serialization không mơ hồ.

Ví dụ nối chuỗi ngây thơ: field A=`"ab"`, field B=`"c"` tạo `"abc"`; field A=`"a"`, field B=`"bc"` cũng tạo `"abc"`. Hai record khác ý nghĩa nhưng cùng bytes sẽ không thể phân biệt.

Hãy dùng serialization canonical, field độ dài cố định hoặc prefix mỗi field bằng length. Ghi rõ charset, version, field order và cách chuẩn hóa Unicode. AAD/HMAC nên bao gồm version, record type, tenant, record ID và metadata ảnh hưởng đến cách diễn giải payload.

Với JSON, hai JSON text có thể khác whitespace/thứ tự field nhưng cùng ý nghĩa. Cần canonical JSON hoặc xác thực chính xác raw bytes theo protocol; đừng parse rồi serialize tùy ý ở hai đầu và kỳ vọng HMAC vẫn khớp.

## 18. Tách key theo mục đích

Nếu hệ thống cần cả HMAC lẫn AES-GCM, quản lý **key riêng theo purpose**:
- Key AES-GCM dùng cho authenticated encryption.
- Key HMAC dùng cho MAC độc lập.
- Không dùng cùng một mảng bytes cho cả hai thuật toán chỉ vì tiện.
- Nếu cần derive nhiều keys từ master secret, dùng KDF chuẩn như HKDF với context/purpose labels; không tự nối chuỗi/hash đơn giản để tạo key con.
- Lưu key ID/version để rotation và chọn đúng key khi verify.
- Khi key bị lộ, có quy trình revoke/rotate và xử lý dữ liệu cũ.

Không lưu key cạnh ciphertext/tag trong cùng file/database row mà không có lớp bảo vệ key riêng. Nếu attacker lấy được cả payload và key, tag không còn bảo vệ được nội dung trước attacker đó.

Với AEAD, thường không cần thêm HMAC thủ công cho cùng ciphertext; GCM đã xác thực ciphertext và AAD. Chỉ thêm cơ chế khác khi protocol yêu cầu rõ và có thiết kế được review.
## 19. Chữ ký số: xác minh bằng public key

Chữ ký số hữu ích khi bên tạo có **private key**, còn nhiều bên có thể xác minh bằng **public key**:
- Signer ký message bytes bằng private key.
- Verifier kiểm tra signature với public key đã tin cậy.
- Thay message hoặc signature sẽ khiến verify thất bại.
- Public key không cần bí mật, nhưng phải xác minh đúng danh tính/chứng thư/fingerprint trước khi tin.

Java dùng `java.security.Signature`: `initSign(privateKey)` để ký, `update(data)` đưa bytes vào, `sign()` tạo signature, `initVerify(publicKey)` chuẩn bị xác minh và `verify(signature)` trả true/false. Signature encoding sai có thể ném `SignatureException`.

Ed25519 có sẵn trong JDK hiện đại từ Java 15. Với Java 8, cần chọn thuật toán/provider hỗ trợ theo policy của hệ thống; không chép code Ed25519 rồi kỳ vọng JDK 8 mặc định chạy được.

Chữ ký số **không mã hóa nội dung**. Nó cũng không tự bảo đảm public key nhận được thuộc đúng người; trust chain/certificate pinning/key distribution vẫn phải được giải quyết.

## 20. Chương trình 5 — chữ ký Ed25519 phát hiện dữ liệu sửa

Tệp `SignatureVerifyDemo.java` (yêu cầu JDK 17+):

```java
import java.nio.charset.StandardCharsets;
import java.security.*;

public class SignatureVerifyDemo {
    static boolean verify(
            PublicKey key, byte[] data, byte[] signature)
            throws GeneralSecurityException {
        try {
            Signature verifier =
                    Signature.getInstance("Ed25519");
            verifier.initVerify(key);
            verifier.update(data);
            return verifier.verify(signature);
        } catch (SignatureException ex) {
            // Signature malformed/invalid: reject.
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPair pair =
                KeyPairGenerator.getInstance("Ed25519")
                        .generateKeyPair();

        byte[] data =
                "release=2026.11;artifact=app.jar"
                        .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(data);
        byte[] signature = signer.sign();

        System.out.println(
                "signature valid=" +
                verify(pair.getPublic(), data, signature));

        byte[] alteredData = data.clone();
        alteredData[0] ^= 1;
        System.out.println(
                "altered data valid=" +
                verify(pair.getPublic(), alteredData, signature));

        byte[] alteredSignature = signature.clone();
        alteredSignature[0] ^= 1;
        System.out.println(
                "altered signature valid=" +
                verify(pair.getPublic(), data, alteredSignature));
    }
}
```

```bash
javac -encoding UTF-8 SignatureVerifyDemo.java
java SignatureVerifyDemo
```

```text
signature valid=true
altered data valid=false
altered signature valid=false
```

Demo sinh key pair mới mỗi lần chạy, nên signature bytes thay đổi, nhưng ba kết quả boolean vẫn đúng. Trong production, public key phải đến từ trust store/certificate/key registry đáng tin. Không lấy public key ngay từ cùng request không được xác thực rồi kết luận chữ ký chứng minh danh tính người gửi.

Nếu chữ ký sai encoding, provider có thể ném `SignatureException` thay vì chỉ trả false. Cả hai tình huống đều phải reject; không catch rồi tiếp tục xử lý artifact.

## 21. Tag hợp lệ không tự chống replay

Attacker có thể ghi lại **một envelope hợp lệ** rồi gửi lại nhiều lần. Ciphertext, nonce, AAD và tag vẫn nguyên vẹn; AEAD sẽ xác minh thành công. Vì vậy **authentication không đồng nghĩa freshness**.

Để chống replay, protocol cần sequence number đơn điệu, request ID duy nhất, timestamp kèm cửa sổ chấp nhận, nonce nghiệp vụ hoặc idempotency key. Trường sequence/request ID phải được đưa vào AAD hoặc HMAC/signature để attacker không thể đổi nó mà tag vẫn hợp lệ.

Sau khi xác thực tag, ứng dụng phải **kiểm tra và ghi nhận replay state atomic** trước side effect. Nếu check và insert tách rời, hai request đồng thời có thể cùng vượt qua. Timestamp đơn lẻ không đủ: một request hợp lệ vẫn có thể gửi lại nhiều lần trong cửa sổ cho phép.

## 22. Chương trình 6 — tag đúng nhưng request replay bị từ chối

Tệp `AeadReplayDemo.java`:

```java
import java.util.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;

public class AeadReplayDemo {
    static byte[] aad(long sequence, String account) {
        byte[] accountBytes =
                account.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(
                        Long.BYTES + accountBytes.length)
                .putLong(sequence)
                .put(accountBytes)
                .array();
    }

    static byte[] seal(
            SecretKey key, byte[] nonce,
            byte[] associated, byte[] plaintext)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(associated);
        return cipher.doFinal(plaintext);
    }

    static byte[] open(
            SecretKey key, byte[] nonce,
            byte[] associated, byte[] sealed)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(associated);
        return cipher.doFinal(sealed);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        long sequence = 7;
        String account = "acct-12";

        byte[] sealed = seal(
                key, nonce, aad(sequence, account),
                "transfer=100".getBytes(StandardCharsets.UTF_8));

        Set<Long> acceptedSequences = new HashSet<>();

        byte[] first =
                open(key, nonce, aad(sequence, account), sealed);
        boolean firstAccepted = acceptedSequences.add(sequence);

        byte[] replay =
                open(key, nonce, aad(sequence, account), sealed);
        boolean replayAccepted = acceptedSequences.add(sequence);

        System.out.println("first tag valid=" + (first != null));
        System.out.println("first sequence accepted=" + firstAccepted);
        System.out.println("replayed tag still valid=" + (replay != null));
        System.out.println("replayed sequence accepted=" + replayAccepted);

        try {
            open(key, nonce, aad(sequence + 1, account), sealed);
            System.out.println("changed sequence accepted=true");
        } catch (AEADBadTagException ex) {
            System.out.println("changed sequence rejected=true");
        }
    }
}
```

```bash
javac -encoding UTF-8 AeadReplayDemo.java
java AeadReplayDemo
```

```text
first tag valid=true
first sequence accepted=true
replayed tag still valid=true
replayed sequence accepted=false
changed sequence rejected=true
```

Envelope gốc có tag hợp lệ và sequence 7 được chấp nhận lần đầu. Gửi lại nguyên envelope vẫn cho tag hợp lệ, vì dữ liệu chưa bị sửa; replay store nhận ra sequence 7 đã dùng và từ chối lần hai. Nếu attacker đổi sequence thành 8 nhưng giữ tag cũ, AAD khác nên verification thất bại.

`HashSet` chỉ minh họa logic một tiến trình. Ứng dụng thực cần replay store bền vững/atomic phù hợp với hệ thống phân tán; không để mỗi server node giữ một set riêng mà không đồng bộ.

## 23. Xử lý lỗi: fail closed và không tạo side effect

Khi xác thực thất bại:
1. Không dùng plaintext hoặc metadata chưa xác thực.
2. Không cập nhật database, số dư, quyền, trạng thái thanh toán hoặc file.
3. Không tự động bỏ tag rồi giải mã bằng chế độ không xác thực.
4. Không thử nhiều key/algorithm tùy ý cho đến khi một cách giải mã “ra text đẹp”.
5. Không trả plaintext một phần đã nhận trước khi xác minh xong.
6. Ghi log sự kiện tối thiểu: record ID đã làm sạch, key version, loại lỗi nội bộ, correlation ID.
7. Trả lỗi chung phù hợp API; tránh tiết lộ chi tiết cho phép xây oracle.
8. Áp rate limit khi endpoint verify có thể bị brute-force/DoS.
9. Có quy trình xử lý key rotation và dữ liệu được mã hóa bằng key version cũ.
10. Không log key, tag nhạy cảm hoặc plaintext.

**Fail closed** nghĩa là khi không thể chứng minh tính hợp lệ, ứng dụng không tiếp tục như thể dữ liệu hợp lệ. Không catch exception rồi return `new byte[0]` hoặc object mặc định; điều đó biến lỗi xác thực thành nghiệp vụ thành công giả.
## 24. Tránh chế độ mã hóa thiếu authentication

Các hệ thống cũ có thể dùng `AES/CBC/PKCS5Padding` để mã hóa. CBC **không tự cung cấp authentication tag**. Nếu dữ liệu bị sửa, decrypt có thể tạo bytes khác hoặc padding error; padding error không phải MAC đáng tin cậy.

Với code mới:
- Ưu tiên AEAD như **AES-GCM** hoặc thuật toán AEAD được platform/policy hỗ trợ.
- Không dùng AES-ECB cho dữ liệu ứng dụng.
- Không tự tạo tag bằng hash không khóa.
- Nếu phải tương thích CBC cũ, cần protocol encrypt-then-MAC đã được thiết kế đúng, key tách riêng, xác minh MAC trước decrypt và có review bảo mật.
- Không tự triển khai GCM, GHASH, Poly1305 hoặc constant-time primitive bằng Java code thông thường.

JDK hiện hành còn hỗ trợ `ChaCha20-Poly1305` trong provider/platform phù hợp (Java 11+); với môi trường Java 8, AES-GCM là lựa chọn JCA quen thuộc. Xác nhận algorithm/provider trên đúng runtime và tuân thủ policy/FIPS của tổ chức.

## 25. Quản lý key: tag đúng phụ thuộc key đúng

Key management thường khó hơn lời gọi `Cipher`:
- Tạo key bằng `KeyGenerator` hoặc KMS; không dùng password text làm AES key trực tiếp.
- Lưu key trong KMS/HSM/KeyStore hoặc secret manager được bảo vệ.
- Không hardcode key trong source, image, log, repository hoặc client app.
- Có key ID/version để decrypt dữ liệu cũ khi rotate.
- Giới hạn service/account nào được quyền dùng key.
- Tách key encryption, MAC, signing và purpose khác.
- Lập kế hoạch rotate, revoke và xử lý key compromise.
- Không sinh lại key ở mỗi process startup nếu cần đọc dữ liệu cũ.
- Không serialize object `SecretKey` tùy tiện để gửi qua network.
- Dùng `SecureRandom` cho vật liệu ngẫu nhiên theo đúng policy.

Ví dụ tạo key AES cho test:

```java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(128);
SecretKey key = generator.generateKey();
```

Đây là demo tạo key trong memory; production cần key persistence/rotation an toàn. `KeyGenerator` cho phép chỉ định key size rõ ràng thay vì phụ thuộc default provider. Không in `key.getEncoded()` ra log.

## 26. Phân biệt authentication tag, HMAC và chữ ký số

| Đặc điểm | AES-GCM tag | HMAC-SHA-256 | Ed25519 signature |
| --- | --- | --- | --- |
| Khóa | Shared symmetric key | Shared symmetric key | Private key ký, public key verify |
| Mã hóa plaintext | Có | Không | Không |
| Xác thực toàn vẹn | Có | Có | Có |
| Người chỉ có quyền verify có thể tạo tag mới? | Có nếu có shared key | Có nếu có shared key | Không nếu chỉ có public key |
| Phù hợp | Dữ liệu cần bí mật + integrity | Message đọc được + integrity | Artifact/message cần signer identity |
| Replay protection tự có? | Không | Không | Không |

Chữ ký số chỉ chứng minh signer sở hữu private key tương ứng; ứng dụng còn cần xác định public key được tin cậy cho artifact/identity nào, kiểm tra certificate/validity hoặc trust registry theo policy.

## 27. Dữ liệu sửa có thể đến từ đâu?

Không phải mọi tag failure đều do hacker. Nguồn lỗi thực tế: bit rot/storage lỗi; file bị truncate khi upload/download; gateway sửa nội dung; ghép nhầm nonce/tag giữa record; dùng sai key version sau rotation; AAD dựng từ metadata khác nhau; serialization khác charset/field order; race condition; attacker sửa có chủ ý; hoặc replay message cũ.

Điều tra:
1. Kiểm tra envelope length/version.
2. Xác nhận key ID/version và permission lookup.
3. So sánh AAD được dựng từ cùng trusted context.
4. Kiểm tra nonce có được lưu đúng bytes và không bị cắt.
5. Kiểm tra payload/tag có bị truncate khi transport.
6. Xác định record có bị replay hoặc lấy nhầm không.
7. Ghi nhận provider/JDK version và algorithm name.
8. Không log key, raw plaintext hoặc full sensitive payload.

Nếu nhiều record đồng loạt tag failure sau deployment, kiểm tra key rotation/serialization/config trước khi kết luận có tấn công.

## 28. Authentication không thay authorization

Tag hợp lệ chỉ xác nhận dữ liệu khớp với khóa đã dùng. Nó không tự chứng minh người gửi được phép thực hiện thao tác, user hiện tại là chủ tài khoản, role còn hiệu lực, giao dịch chưa xử lý, token chưa hết hạn/revoke hay dữ liệu phù hợp trạng thái database.

Sau khi tag hợp lệ, ứng dụng vẫn phải kiểm tra authorization, expiry/issuer/audience/purpose nếu payload là token, replay state, idempotency và business invariants.

**Authenticated bytes không tự trở thành authorized action.** Đừng để message có tag hợp lệ vượt qua kiểm tra quyền nghiệp vụ.

## 29. Kích thước, tag truncation và giới hạn input

Trước khi giải mã, validate envelope có tối thiểu nonce + tag; ciphertext không vượt giới hạn; version/key ID nằm trong tập hỗ trợ; tag length đúng; AAD fields có chiều dài hợp lệ; request body có giới hạn bytes; số lần verify thất bại và CPU/memory theo request được kiểm soát.

Với GCM, demo dùng **128-bit tag**. Không tự cắt tag để giảm payload; tag ngắn làm giảm khả năng chống forgery và có giới hạn theo chuẩn. Với HMAC-SHA-256, ví dụ dùng tag đầy đủ **32 byte**.

Không chỉ kiểm tra tag sau khi đã đọc payload khổng lồ vào memory. Hãy giới hạn encoded size, decoded size và timeout từ tầng transport.

## 30. Thread safety và lifecycle của Cipher/Mac/Signature

`Cipher`, `Mac` và `Signature` là các object có state: init, update, doFinal/verify thay đổi trạng thái. **Không chia sẻ cùng instance giữa request/thread đồng thời** nếu không có cơ chế ownership/đồng bộ được thiết kế rõ.

- Tạo Cipher mới cho mỗi operation hoặc pool có ownership/reset đúng.
- Gọi `init` lại với key/nonce/parameters đúng cho operation đó.
- Gửi AAD trước ciphertext.
- Không tái sử dụng GCM key+nonce pair.
- Không lưu mutable Cipher object vào static singleton rồi dùng đồng thời.
- Không dùng chung một Mac hoặc Signature instance cho nhiều request.

Một Cipher object reset sau `doFinal` không có nghĩa được phép dùng lại cùng nonce/key cho lần mã hóa GCM tiếp theo.

## 31. Kiểm thử tampering: các trường hợp cần có

Bộ test nên gồm plaintext round trip; thay một bit ciphertext; thay tag; thay nonce/IV; thay AAD/record ID; dùng sai key/key version; truncate envelope; thêm bytes bất hợp lệ; sai version/key ID; replay envelope hợp lệ; tag rỗng/sai độ dài; xác minh plaintext không được xử lý khi verify thất bại; xác minh lỗi không làm đổi database/state; key rotation; và nhiều request đồng thời.

Test tampering cần xác nhận **không được chấp nhận**, không cần hardcode ciphertext/tag cụ thể vì key và nonce có thể thay đổi. Assert output booleans/exception đúng loại và xác minh không có side effect.

## 32. Java 8 và JDK hiện hành

| API/khả năng | Java 8 | JDK hiện đại |
| --- | --- | --- |
| `Cipher` / AES-GCM trong Oracle JCA | Có | Có |
| `GCMParameterSpec` | Có (Java 7+) | Có |
| `AEADBadTagException` | Có (Java 7+) | Có |
| `Mac` / HmacSHA256 | Có | Có |
| `MessageDigest.isEqual` | Có | Có |
| `Signature` | Có | Có |
| `SecureRandom` / `KeyGenerator` | Có | Có |
| Ed25519 built-in JDK | Không | Có từ Java 15 |
| ChaCha20-Poly1305 built-in JDK | Không | Có từ Java 11 |

Các API cốt lõi để kiểm tra authentication tag/HMAC **không lỗi thời** và có sẵn trên Java 8. Ví dụ Ed25519 được đánh dấu JDK 15+; không đưa nó vào source cần compile trên Java 8 nếu không có provider tương thích.

Provider và policy có thể ảnh hưởng algorithm availability, key size và compliance. Kiểm tra runtime/provider thật của hệ thống; đừng suy ra mọi Java distribution đều cài cùng provider hoặc hỗ trợ mọi transformation ngoài danh sách bắt buộc.

## 33. Checklist code review

**Thuật toán:** cần confidentiality, integrity hay cả hai? Chọn AEAD/HMAC/signature đúng threat model? Tránh hash không khóa làm authentication?

**AEAD:** dùng AES-GCM/AEAD rõ ràng? Tag/nonce length đúng? Nonce unique per key kể cả đa node/restart? AAD trước ciphertext? AAD canonical? Tag verification xong trước khi xử lý plaintext? Tag failure không tạo side effect?

**HMAC/chữ ký:** HMAC key secret và tách purpose? Tag length đúng, so sánh bằng `MessageDigest.isEqual`? Public key xác minh có đáng tin? Algorithm/provider đúng runtime? Malformed signature/invalid tag được reject?

**Ứng dụng:** envelope có version/key ID/bounds? Key rotation/revoke/storage đã rõ? Replay protection/idempotency đã thiết kế? Authorization/business validation vẫn chạy sau verify? Log không chứa secret/tag/plaintext? Test tampering/truncation/wrong key/AAD/nonce/replay? Không chia sẻ mutable Cipher/Mac/Signature giữa threads?

## 34. Câu hỏi tự kiểm tra

**1. Authentication tag dùng để làm gì?** Kiểm tra toàn vẹn và xác thực dữ liệu theo key/thuật toán đã chọn.

**2. AES-GCM cung cấp thuộc tính nào?** Mã hóa plaintext và xác thực ciphertext cùng AAD.

**3. AAD có được mã hóa không?** Không; nó được xác thực nhưng vẫn công khai.

**4. Tag GCM 128 bit dài bao nhiêu byte?** 16 byte.

**5. Nonce GCM 96 bit dài bao nhiêu byte?** 12 byte.

**6. Có được reuse cùng key+nonce cho hai lần GCM encryption không?** Không; nonce phải unique theo key.

**7. `updateAAD` phải gọi lúc nào?** Sau init và trước khi bắt đầu xử lý ciphertext.

**8. Java ném exception nào khi GCM tag không hợp lệ?** `AEADBadTagException`.

**9. Có nên xử lý plaintext trước khi `doFinal` xác minh tag?** Không; output tạm thời chưa xác thực.

**10. HMAC có mã hóa message không?** Không; HMAC chỉ xác thực với shared secret.

**11. SHA-256(message) có thay HMAC được không?** Không; attacker tự tính lại hash sau khi sửa message.

**12. So sánh HMAC tag bằng API nào?** `MessageDigest.isEqual(expected, supplied)` sau khi kiểm tra độ dài.

**13. Chữ ký số khác HMAC ở đâu?** Private key ký, public key xác minh; người chỉ có public key không tạo chữ ký mới.

**14. Tag hợp lệ có chống replay không?** Không; cần sequence, request ID, replay store hoặc idempotency.

**15. Tag hợp lệ có chứng minh user được phép thanh toán không?** Không; authorization và business rules là bước riêng.

**16. Nonce có cần giữ bí mật không?** Không; uniqueness là yêu cầu quan trọng.

**17. Có nên dùng một Cipher object cho nhiều threads?** Không chia sẻ instance có state giữa operations đồng thời.

**18. Ed25519 có sẵn trong Java 8 không?** Không; JDK có built-in từ Java 15.

**19. HMAC-SHA-256 tag đầy đủ dài bao nhiêu?** 32 byte.

**20. Nếu tag sai, có nên trả plaintext rỗng rồi tiếp tục không?** Không; phải reject và không tạo side effect.

## 35. Tổng kết

- **AES-GCM là AEAD**: cung cấp confidentiality và xác thực ciphertext/AAD bằng tag.
- **`Cipher.doFinal` xác minh tag khi decrypt**; lỗi xác thực là `AEADBadTagException`.
- **AAD không bí mật nhưng được bảo vệ toàn vẹn**; dùng để ràng buộc version, record ID, tenant và metadata.
- **GCM nonce phải unique với mỗi key**; 96-bit nonce và 128-bit tag là cấu hình thông dụng. Random nonce vẫn cần quản lý collision risk/usage limits.
- **Không dùng plaintext trước khi tag verification thành công**; fail closed, không tạo side effect.
- **HMAC-SHA-256** xác thực message bằng shared secret nhưng không mã hóa; so sánh tag bằng `MessageDigest.isEqual`.
- **Chữ ký số** dùng private/public key; public key phải được xác thực theo trust policy.
- Tag hợp lệ **không chống replay, không cấp authorization và không chứng minh user identity** nếu key/trust model không gắn với danh tính đó.
- Quản lý key, nonce, version, replay state, bounds, logging và rotation quan trọng ngang lời gọi crypto API.
- AES-GCM, HMAC, `MessageDigest.isEqual` và `Signature` vẫn hiện hành; Ed25519/ChaCha20-Poly1305 có yêu cầu JDK mới hơn.

### Tài liệu chính thức và tiêu chuẩn

- [Oracle Java SE 26 — Cipher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html): AEAD, AAD ordering, tag append/verify và `AEADBadTagException`.
- [Oracle Java SE 8 — Cipher](https://docs.oracle.com/javase/8/docs/api/javax/crypto/Cipher.html): JCA AEAD/GCM, uniqueness của IV và `updateAAD`.
- [Oracle Java SE 8 — GCMParameterSpec](https://docs.oracle.com/javase/8/docs/api/javax/crypto/spec/GCMParameterSpec.html): IV và độ dài tag theo bit.
- [Oracle Java SE 26 — AEADBadTagException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/AEADBadTagException.html): exception khi AEAD tag không thể xác minh.
- [Oracle Java SE 26 — Mac](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Mac.html): HMAC, `init`, `doFinal` và thuật toán hỗ trợ.
- [Oracle Java SE 26 — MessageDigest](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/MessageDigest.html): `isEqual`.
- [Oracle Java SE 26 — Signature](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html): ký và xác minh chữ ký số.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): GCM, tag verification và uniqueness của IV; NIST ghi nhận publication đang được sửa đổi.
- [RFC 5116 — Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5116.html): AEAD inputs, AAD và nonce uniqueness.
- [RFC 9771 — Properties of AEAD Algorithms](https://www.rfc-editor.org/rfc/rfc9771.html): tính chất authenticated encryption hiện hành.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104.html): HMAC dựa trên hash và shared secret.
