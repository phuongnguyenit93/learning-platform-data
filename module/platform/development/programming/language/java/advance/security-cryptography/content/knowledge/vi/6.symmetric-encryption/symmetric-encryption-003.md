# 6.3 Tạo khóa AES bằng KeyGenerator và dựng khóa từ vật liệu hợp lệ

## 1. Bản chất khóa AES

AES là thuật toán mã hóa **đối xứng**: bên mã hóa và giải mã cần cùng khóa bí mật. Trong JCA/JCE, khóa AES thường được đại diện bởi giao diện `javax.crypto.SecretKey` và được cung cấp cho `Cipher.init(...)`.

| AES | Độ dài tính bằng bit | Raw key bytes |
| --- | ---: | ---: |
| AES-128 | 128 bit | 16 byte |
| AES-192 | 192 bit | 24 byte |
| AES-256 | 256 bit | 32 byte |

AES luôn có kích thước **block 128 bit**, bất kể dùng AES-128/192/256. Độ dài key cũng khác IV/nonce (AES-GCM thường dùng IV 12 byte) và authentication tag (thường là 128 bit). **Key phải bí mật**, IV không cần bí mật nhưng **không được lặp khi mã hóa với cùng một key**.

Phân biệt ba đầu vào:

1. **Cần tạo khóa mới ngẫu nhiên:** dùng `KeyGenerator`.
2. **Đã có đúng raw AES key từ nguồn an toàn:** kiểm tra 16/24/32 byte rồi dựng `SecretKeySpec`.
3. **Chỉ có password hoặc master secret:** phải thực hiện **key derivation** thích hợp, không bọc trực tiếp byte của password thành key.

Chiều dài đúng mới chỉ chứng minh key có hình dạng hợp lệ. Mảng 32 byte toàn số 0 hoặc một password dễ đoán không bảo mật chỉ vì dài 32 byte.

## 2. Sinh khóa AES mới với KeyGenerator

`KeyGenerator` là engine của JCA để tạo khóa bí mật. Đoạn mã minh họa nằm trong một phương thức Java:

```java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, new SecureRandom());
SecretKey aesKey = generator.generateKey();
```

Các import cần có: `javax.crypto.KeyGenerator`, `javax.crypto.SecretKey` và `java.security.SecureRandom`. Chương trình hoàn chỉnh ở phần 5 có đầy đủ mã nguồn.

- `getInstance("AES")` chọn engine/provider cung cấp AES; `NoSuchAlgorithmException` xảy ra nếu runtime không hỗ trợ.
- `init(256, random)` thiết lập **256 bit**, không phải 256 byte. AES có các độ dài khóa hợp lệ 128/192/256 bit; provider có thể áp dụng hạn chế riêng.
- `SecureRandom` tạo randomness dành cho mật mã. Không dùng `java.util.Random`, `Math.random()` hay seed cố định để cố tạo khóa tái lập.
- `generateKey()` trả `SecretKey` mới; không tự tạo IV cho từng bản ghi và không tự lưu key để dùng lại sau restart.
- Hãy `init` tường minh để tránh phụ thuộc lựa chọn kích thước mặc định của provider. Overload `init(int)` có thể sử dụng RNG do provider chọn, nhưng overload có `SecureRandom` làm rõ nguồn sinh.

Sai: `new SecretKeySpec(new byte[32], "AES")` vì `new byte[32]` toàn **zero**. Nếu giao thức riêng buộc phải tạo raw bytes, có thể dùng `SecureRandom.nextBytes(raw)` với đúng 16/24/32 byte; với JCA thông thường, `KeyGenerator` dễ đọc và bảo trì hơn.

## 3. Dựng khóa từ raw key hợp lệ bằng SecretKeySpec

Giả sử ứng dụng đã nhận raw key bytes từ một kho khóa hay giao thức được xác thực. Hãy kiểm tra trước khi dựng khóa:

```java
// Đoạn minh họa; raw là byte[] nguồn tin cậy.
if (raw == null ||
        (raw.length != 16 && raw.length != 24 && raw.length != 32)) {
    throw new IllegalArgumentException("Invalid AES key length");
}
SecretKey key = new SecretKeySpec(raw, "AES");
```

`SecretKeySpec` **sao chép** các key bytes và gắn tên thuật toán. Nó **không tự sinh randomness, không dẫn xuất key và không đánh giá entropy**. Constructor có thể chấp nhận nguyên liệu có độ dài không tương thích với AES; `Cipher.init` mới có thể ném `InvalidKeyException`. Vì thế phải validate length ở ranh giới nhận dữ liệu và xử lý cả lỗi provider.

**Encoding khác raw bytes:**

- Raw AES-256 key có **32 byte**; dạng **hex dài 64 ký tự** vì mỗi byte chiếm hai ký tự.
- Base64 của 32 byte thường có **44 ký tự**, kể cả padding `=`. Hex/Base64 **chỉ là biểu diễn**, không mã hóa bảo mật.
- Nhập từ hệ thống bên ngoài: `Base64.getDecoder().decode(base64Key)` hoặc `HexFormat.of().parseHex(hexKey)` (Java 17+), rồi validate **độ dài mảng đã decode**.
- Không gọi `base64Key.getBytes(UTF_8)` để tạo AES key: đó là bytes của **chữ mã hóa**, không phải raw key.

Mã minh họa decode Base64 (không phải chương trình độc lập, vì `base64Key` do caller cung cấp):

```java
byte[] raw = java.util.Base64.getDecoder().decode(base64Key);
try {
    if (raw.length != 16 && raw.length != 24 && raw.length != 32) {
        throw new IllegalArgumentException("Wrong AES key size");
    }
    SecretKey imported = new SecretKeySpec(raw, "AES");
    // Dung imported trong pham vi can thiet.
} finally {
    java.util.Arrays.fill(raw, (byte) 0);
}
```

Chỉ nhập raw key nếu đã xác thực **nguồn, định dạng, quyền dùng và bảo mật kênh truyền**. Không ghi log raw key hay chuỗi Base64/hex của nó. Một số khóa do HSM/PKCS#11/KMS hoặc provider đặc biệt quản lý **không export được**, `SecretKey.getEncoded()` có thể trả `null`. Với loại khóa đó, dùng trực tiếp `SecretKey`/key handle và provider tương thích, không cố dựng `SecretKeySpec`.

**Giới hạn xóa bộ nhớ:** `SecretKeySpec` giữ bản sao key bytes; `Arrays.fill(raw, 0)` chỉ xóa mảng `raw` của ứng dụng, không bảo đảm xóa bản sao trong key object hoặc provider. `String` immutable khó làm sạch hơn mảng; hạn chế xuất/copy key, giữ thời gian sống ngắn và dùng KMS/HSM khi chính sách yêu cầu.

## 4. Password chưa phải AES key: cần một KDF

Sai lầm quen thuộc là lấy bytes UTF-8 của password đủ 16/32 byte rồi tạo `SecretKeySpec`. Một password dễ đoán như `"1234567890123456"` vẫn dễ bị brute force dù có **16 byte**. Một phép `SHA-256(password)` trực tiếp cũng chưa phải password KDF phù hợp: hàm băm nhanh cho phép thử nhiều mật khẩu offline.

Trong Java 17+, `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` cùng `PBEKeySpec` hỗ trợ dẫn xuất khóa từ password:

```text
password (char[]) -----+
                       +-- PBKDF2-HMAC-SHA256(salt, iterations, 256 bits)
random salt (16B+) ----+                         |
                                                 v
                                        32 raw key bytes
                                                 |
                                                 v
                                      SecretKeySpec(raw, "AES")
```

- **Salt** ngẫu nhiên, ví dụ 16 byte từ `SecureRandom`; không cần bí mật, nhưng phải lưu lại để có thể tái tạo cùng key khi giải mã. Salt mới với cùng password ⇒ key mới.
- **Iterations** làm tăng chi phí thử password. Giá trị `210_000` trong chương trình là minh họa API; cần điều chỉnh theo threat model, hiệu năng và chính sách cập nhật, không coi là hằng số được khuyến nghị vĩnh viễn.
- `PBEKeySpec(password, salt, iterations, 256)` yêu cầu **256 bit**, tạo 32 byte. Hai lần derive cùng password/salt/iterations/algorithm/length cho cùng key.
- Lưu **version, tên KDF, salt, iteration count và output length** với định dạng bản ghi. Nếu thay tham số rồi cố giải mã ciphertext cũ, key tái tạo sẽ khác.
- Dùng `char[]` thay vì giữ password lâu trong `String` khi ứng dụng cho phép; `PBEKeySpec.clearPassword()` và `Arrays.fill(...)` làm sạch các mảng có thể kiểm soát, nhưng không bảo đảm mọi bản sao nội bộ đã bị xóa.

Các thư viện hiện đại có thể hỗ trợ KDF tốn bộ nhớ như **Argon2id** theo chính sách; Java SE JCA không bảo đảm sẵn tên thuật toán này. Với master secret ngẫu nhiên cần tạo nhiều key con, dùng KDF/context separation theo giao thức thích hợp (chẳng hạn HKDF), không tự dùng byte của password hoặc một phép hash nhanh làm giải pháp chung.

## 5. Ví dụ chạy được: KeyGenerator, SecretKeySpec và AES-GCM

Lưu thành **`AesKeySourcesDemo.java`**, Java 17+. Chương trình tạo AES-256 key, **chỉ vì mục đích giáo dục** lấy raw bytes qua `getEncoded()`, dựng một `SecretKeySpec` từ chính raw bytes đó, rồi mã hóa bằng key gốc và giải mã bằng key nhập lại.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
public class AesKeySourcesDemo {
    static SecretKey fromRawAesKey(byte[] raw) {
        if (raw == null || (raw.length != 16 && raw.length != 24 && raw.length != 32)) {
            throw new IllegalArgumentException("AES key must be 16, 24, or 32 bytes");
        }
        return new SecretKeySpec(raw, "AES");
    }
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, random);
        SecretKey generated = generator.generateKey();
        byte[] raw = generated.getEncoded();
        if (raw == null) throw new IllegalStateException("Key is not exportable");
        try {
            SecretKey imported = fromRawAesKey(raw);
            System.out.println("generatedBits=" + raw.length * 8);
            System.out.println("algorithm=" + imported.getAlgorithm());
            System.out.println("sameMaterial=" + MessageDigest.isEqual(raw, imported.getEncoded()));
            try {
                fromRawAesKey(new byte[17]);
                System.out.println("invalidLengthRejected=false");
            } catch (IllegalArgumentException expected) {
                System.out.println("invalidLengthRejected=true");
            }
            byte[] iv = new byte[12];
            random.nextBytes(iv);
            byte[] aad = "record:7".getBytes(StandardCharsets.UTF_8);
            byte[] message = "Hello AES".getBytes(StandardCharsets.UTF_8);
            Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
            encrypt.init(Cipher.ENCRYPT_MODE, generated, new GCMParameterSpec(128, iv));
            encrypt.updateAAD(aad);
            byte[] ciphertextAndTag = encrypt.doFinal(message);
            Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
            decrypt.init(Cipher.DECRYPT_MODE, imported, new GCMParameterSpec(128, iv));
            decrypt.updateAAD(aad);
            byte[] recovered = decrypt.doFinal(ciphertextAndTag);
            System.out.println("roundTrip=" + Arrays.equals(message, recovered));
        } finally {
            Arrays.fill(raw, (byte) 0);
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AesKeySourcesDemo.java
java AesKeySourcesDemo
```

```text
generatedBits=256
algorithm=AES
sameMaterial=true
invalidLengthRejected=true
roundTrip=true
```

Đầu ra ổn định dù key và IV ngẫu nhiên vì không in bytes bí mật. `sameMaterial=true` chứng minh bản sao raw key giống key gốc; `roundTrip=true` chứng minh cùng key/IV/AAD có thể mã hóa và giải mã đúng. **Không** chứng minh nguồn bên ngoài tin cậy, quyền truy cập hay lưu khóa đã an toàn.

`AES/GCM/NoPadding` là transformation được chỉ rõ; `Cipher.getInstance("AES")` ngắn gọn có thể để provider chọn mode/padding mặc định không mong muốn (chẳng hạn ECB). Với AES-GCM, nonce thường 12 byte và tag thường 128 bit; `GCMParameterSpec(128, iv)` dùng **128 bit cho tag**, không phải kích thước key. Khi mã hóa bản ghi **mới dưới cùng key**, phải chọn **IV mới không trùng** và gọi `Cipher.init` lại. Không được lấy việc engine reset sau `doFinal` làm lý do tái sử dụng cặp key+IV.

## 6. Ví dụ chạy được: tạo raw AES key từ password bằng PBKDF2

Lưu thành **`PasswordDerivedAesDemo.java`**. Password trong code chỉ phục vụ demo chạy độc lập, không hardcode như vậy trong ứng dụng thật.

```java
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;
public class PasswordDerivedAesDemo {
    private static final int ITERATIONS = 210_000;
    private static final int KEY_BITS = 256;
    private static byte[] deriveRawKey(char[] password, byte[] salt) throws Exception {
        if (salt == null || salt.length < 16) {
            throw new IllegalArgumentException("Salt must be >= 16 bytes");
        }
        PBEKeySpec spec = new PBEKeySpec(password, salt, ITERATIONS, KEY_BITS);
        try {
            SecretKeyFactory factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
            byte[] derived = factory.generateSecret(spec).getEncoded();
            if (derived == null || derived.length != 32) {
                throw new IllegalStateException("Expected 256 bits of derived key material");
            }
            return derived;
        } finally {
            spec.clearPassword();
        }
    }
    public static void main(String[] args) throws Exception {
        char[] password = "example-password".toCharArray();
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        byte[] first = null;
        byte[] second = null;
        byte[] changedSalt = null;
        try {
            first = deriveRawKey(password, salt);
            second = deriveRawKey(password, salt);
            salt[0] ^= 1;
            changedSalt = deriveRawKey(password, salt);
            SecretKey aesKey = new SecretKeySpec(first, "AES");
            System.out.println("keyBits=" + first.length * 8);
            System.out.println("algorithm=" + aesKey.getAlgorithm());
            System.out.println("sameInputsSameKey=" + MessageDigest.isEqual(first, second));
            System.out.println("changedSaltChangesKey=" + !MessageDigest.isEqual(first, changedSalt));
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(salt, (byte) 0);
            if (first != null) Arrays.fill(first, (byte) 0);
            if (second != null) Arrays.fill(second, (byte) 0);
            if (changedSalt != null) Arrays.fill(changedSalt, (byte) 0);
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PasswordDerivedAesDemo.java
java PasswordDerivedAesDemo
```

```text
keyBits=256
algorithm=AES
sameInputsSameKey=true
changedSaltChangesKey=true
```

Cùng password + salt + iterations + KDF + output length sẽ tái tạo **cùng raw AES key**. Nếu khi giải mã dữ liệu cũ lại sinh salt mới, không còn cùng key. Khi đổi password, ứng dụng cần thiết kế re-encryption hoặc re-wrapping đúng giao thức; bản mã cũ không tự giải mã bằng key mới.

## 7. Khóa được lưu trữ hoặc quản lý ở đâu?

| Nguồn | Hành động đúng |
| --- | --- |
| Sinh khóa ngẫu nhiên trong process | Dùng `SecretKey` trực tiếp; cần chiến lược lưu/khôi phục nếu phải giải mã sau restart |
| Raw AES key đã được cấp an toàn | Decode (nếu có), validate 16/24/32 byte, tạo `SecretKeySpec` |
| Password | KDF salt/cost phù hợp, lưu tham số để có thể tái tạo |
| Java `KeyStore`, HSM hoặc PKCS#11 | Dùng `SecretKey` hay key handle qua provider; không giả định export được |
| Cloud KMS | Tuân thủ API, key ID/permissions và chính sách không xuất raw key |
| Master secret entropy cao | Tách khóa theo ngữ cảnh và mục đích bằng KDF của giao thức |

`KeyStore` là **API** quản lý key entries; mức bảo vệ phụ thuộc loại store và provider (ví dụ PKCS12, PKCS11), không mặc nhiên là HSM. Tách quyền **dùng key** khỏi quyền **xuất raw key**. Khi xoay khóa, lưu **key ID/version** cùng metadata bản mã; dữ liệu mã hóa bằng key cũ thường cần key cũ hoặc quy trình re-encrypt/rewrap có kiểm soát.

Một bản ghi AES-GCM cần có đủ **key ID, IV, ciphertext+tag, AAD (hoặc quy tắc tạo AAD)** và version định dạng. Nếu nguồn là password, bổ sung **KDF algorithm/salt/iterations/output bits**. Không lưu raw key như metadata ở nơi người đọc ciphertext có thể xem được.

## 8. Lỗi thường gặp và cách tránh

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | Provider thiếu thuật toán AES hoặc PBKDF2 | Xác minh tên và provider/runtime |
| `InvalidParameterException` tại `KeyGenerator.init` | Độ dài key không phù hợp/chính sách hạn chế | Chọn 128/192/256 bit được hỗ trợ |
| `IllegalArgumentException` khi import | Base64/hex sai hoặc raw key length sai | Decode đúng định dạng, kiểm tra **số byte** |
| `InvalidKeyException` tại `Cipher.init` | SecretKey không hợp lệ cho thuật toán/provider | Xác minh key algorithm, size, provider |
| `InvalidAlgorithmParameterException` | Tham số IV/tag/mode sai | Xác minh transformation và `GCMParameterSpec` |
| `AEADBadTagException` khi giải mã | Key, IV, AAD hoặc ciphertext/tag sai | Từ chối bản ghi, không dùng plaintext chưa xác thực |
| `getEncoded() == null` | Key không export được | Dùng trực tiếp key handle và provider hỗ trợ |
| Mất quyền giải mã sau restart | Không lưu đúng key/version/salt/IV | Thiết kế key management và metadata trước khi mã hóa |

Không chia sẻ cùng một `Cipher` đang xử lý giữa nhiều thread/request. Đừng log bí mật hoặc trả lỗi nội bộ quá chi tiết cho người ngoài; khi GCM xác thực thất bại thì loại bỏ plaintext chưa được xác thực.

### Checklist trước khi đưa vào ứng dụng

- Khóa mới do `KeyGenerator`/CSPRNG sinh, hoặc raw key đã xác thực nguồn và có chiều dài hợp lệ.
- Password luôn đi qua KDF với salt và cost; có chiến lược lưu/khôi phục tham số.
- `Cipher` dùng transformation xác định rõ, ví dụ `AES/GCM/NoPadding`; IV duy nhất trong phạm vi mỗi key mã hóa.
- Có key ID/version, chính sách lưu giữ, sao lưu, giới hạn quyền và rotation.
- Không hardcode, log, export vô cớ hoặc lưu raw key chung nơi có ciphertext.
- Có test key length sai, PBKDF2 cùng/khác salt, AES-GCM round-trip và GCM tag bị thay đổi.

## 9. Tự kiểm tra

1. AES-128/192/256 có bao nhiêu raw key bytes? **16/24/32**.
2. Tham số `256` của `KeyGenerator.init(256)` là bit hay byte? **Bit**.
3. `SecretKeySpec` có tăng entropy hoặc tự sinh key không? **Không**.
4. Chuỗi 64 ký tự hex của AES-256 cần decode thành bao nhiêu raw bytes? **32**.
5. Password 16 ký tự được dùng trực tiếp làm AES-128 key có an toàn không? **Không bảo đảm**; cần KDF thích hợp.
6. Vì sao phải lưu PBKDF2 salt? Để **dẫn xuất lại cùng key** khi giải mã, ngoài các tham số khác.
7. GCM có được tái dùng IV khi vẫn dùng cùng key không? **Không**.
8. `getEncoded()==null` có nghĩa gì? Key có thể **không export được**, cần provider/handle tương thích.
9. Xóa mảng `raw` có xóa bản sao trong `SecretKeySpec` không? **Không**.
10. Key mới có tự giải mã ciphertext của key cũ không? **Không**; cần version/key cũ hoặc quy trình di chuyển dữ liệu.

## Tài liệu Java SE 21

- [KeyGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyGenerator.html)
- [SecretKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKey.html)
- [SecretKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html)
- [SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html)
- [SecretKeyFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKeyFactory.html)
- [PBEKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html)
- [Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [GCMParameterSpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html)
- [KeyStore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html)
