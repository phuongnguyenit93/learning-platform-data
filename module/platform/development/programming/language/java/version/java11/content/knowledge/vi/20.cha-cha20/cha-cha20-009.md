# Java 11 — AEADBadTagException và lỗi dữ liệu bị sửa

**Chủ đề:** Java 11 → ChaCha20. Bài học giải thích `javax.crypto.AEADBadTagException` khi giải mã với `ChaCha20-Poly1305`: vì sao tag xác thực có thể không khớp, cách phân biệt lỗi dữ liệu bị sửa với key/nonce/AAD sai, và cách **từ chối dữ liệu chưa được xác thực**. Chỉ dùng kiến thức còn áp dụng hiện nay và API có trên JDK 11, không chuyển sang cipher cũ không có cơ chế kiểm tra tính toàn vẹn.

**Mục tiêu:** Hiểu cấu trúc AEAD, sử dụng `Cipher.getInstance("ChaCha20-Poly1305")`, `IvParameterSpec` và `updateAAD` đúng cách, xử lý `AEADBadTagException` an toàn, chạy hai ví dụ độc lập đã kiểm thử bằng `javac --release 11`, biết thiết kế wire format, nonce uniqueness, replay protection, các bài kiểm thử sửa một bit và hướng chẩn đoán production.

## 1. ChaCha20 và ChaCha20-Poly1305 khác nhau

`ChaCha20` là stream cipher, mã hóa plaintext thành ciphertext bằng keystream. **Một mình ChaCha20 không chứng minh rằng ciphertext không bị thay đổi.** Nếu attacker thay một phần ciphertext, plaintext giải mã có thể bị sửa mà không có cơ chế kiểm chứng đi kèm.

`ChaCha20-Poly1305` bổ sung **Poly1305 authenticator** và trở thành thuật toán **AEAD — Authenticated Encryption with Associated Data**. AEAD bảo vệ cả tính bí mật của plaintext lẫn tính toàn vẹn/xác thực **theo một secret key** của ciphertext và AAD.

~~~text
ENCRYPT:
key (32B) + nonce (12B) + plaintext + AAD
                 |
                 v
         ChaCha20-Poly1305
                 |
                 v
           ciphertext || tag (16B)

DECRYPT:
key + nonce + AAD + ciphertext || tag
                 |
                 v
          Verify authentication
           /                 \
       valid                invalid
         |                     |
     plaintext          AEADBadTagException
         |                     |
    parse/use data        REJECT; no plaintext
~~~

| Thành phần | Kích thước | Bí mật? | Vai trò |
| --- | --- | --- | --- |
| ChaCha20 key | **32 byte / 256 bit** | Có | Bảo vệ toàn bộ operation. |
| Nonce/IV | **12 byte / 96 bit** | Không | Phải **không lặp** khi encrypt bằng cùng key. |
| AAD | Tùy giao thức | Không được mã hóa | Bảo vệ metadata trước việc thay đổi. |
| Ciphertext | Bằng độ dài plaintext | Không nhất thiết | Nội dung đã mã hóa. |
| Poly1305 tag | **16 byte / 128 bit** | Không cần giấu | Chứng minh input khớp key/nonce/AAD và bản mã. |
| `Cipher.doFinal(plaintext)` | `plaintext.length + 16` | Ciphertext không phải secret key | Trả **ciphertext nối tag** trong chế độ AEAD này. |

**Ghi nhớ:** Tag không phải nonce, nonce không phải key. Với Java 11 và IETF ChaCha20-Poly1305, encrypt sinh `ciphertext || tag`; decrypt cần nhận **cả ciphertext lẫn 16 byte tag** trong đầu vào `doFinal`.

### 1.1. AAD khác plaintext thế nào?

AAD có thể chứa version, tenant ID, record ID, role, sequence hoặc direction. Nó **không được mã hóa**; kẻ quan sát có thể thấy nếu AAD được truyền cùng message. Nhưng nếu thay AAD đã dùng để encrypt, phép kiểm tag ở phía nhận sẽ thất bại.

Ví dụ:

~~~java
byte[] aad = "tenant=alpha;v=1;record=42"
    .getBytes(StandardCharsets.UTF_8);
cipher.updateAAD(aad);
~~~

Đây là **đoạn minh họa**, `cipher` đã được init, cần import `StandardCharsets`. Phía encrypt và decrypt phải dùng **đúng từng byte** AAD, không chỉ cùng “ý nghĩa” trừu tượng.

## 2. `AEADBadTagException` là gì?

Java 11 định nghĩa `AEADBadTagException` khi một `Cipher` hoạt động ở mode AEAD **không xác minh được authentication tag**. Quan hệ kế thừa:

~~~text
java.lang.Exception
  └── java.security.GeneralSecurityException
      └── javax.crypto.BadPaddingException
          └── javax.crypto.AEADBadTagException
~~~

Tên superclass `BadPaddingException` là thiết kế kế thừa của JCE; **ChaCha20-Poly1305 không dùng PKCS padding**. Vì vậy, không nên báo “padding sai” như lời giải thích chắc chắn cho trường hợp này.

Trong mã Java 11:

~~~java
try {
    byte[] plaintext = cipher.doFinal(ciphertextWithTag);
    // Chỉ dùng plaintext sau khi doFinal hoàn tất thành công.
} catch (AEADBadTagException failure) {
    throw new SecurityException("Authenticated decryption failed", failure);
}
~~~

Đây là **đoạn minh họa**; `cipher` đã được init đúng `Cipher.DECRYPT_MODE` với key/nonce, AAD được đặt trước khi cung cấp ciphertext. Nếu muốn bắt riêng lỗi này, đặt `catch (AEADBadTagException ...)` trước các catch `BadPaddingException` hoặc `GeneralSecurityException`.

**Exception chứng minh điều gì?** Bộ giá trị đang dùng để decrypt gồm key, nonce, AAD và ciphertext/tag **không tạo thành một message được xác thực hợp lệ**. Nó **không** cho biết nguyên nhân duy nhất và **không phải bằng chứng tự động rằng có hacker**.

## 3. Những nguyên nhân thường gặp

| Thay đổi hoặc sự cố | Lý do tag fail |
| --- | --- |
| Một bit của ciphertext bị sửa | Poly1305 tag gốc không còn phù hợp với ciphertext mới. |
| Một bit của 16-byte tag bị đổi | Giá trị tag nhận được khác tag tính lại. |
| Nonce nhận khác nonce đã encrypt | Keystream và tag phụ thuộc nonce. |
| Key sai nhưng vẫn dài đủ 32 byte | Kiểm tag với secret key khác. |
| `keyId` sai hoặc KDF label/context khác | Chọn key không tương ứng với ciphertext. |
| AAD khác bytes | Tên tenant/version/record, thứ tự field, UTF-8, case hay separator không khớp. |
| Body bị cắt khi truyền/lưu | Mất một phần ciphertext hoặc tag; xác thực thất bại. |
| Decode Base64/hex sai hoặc đảo offset | Dãy byte đem decrypt không đúng định dạng. |
| Dùng transformation sai | Một bên mã hóa bằng format/thuật toán khác. |
| Protocol đổi version nhưng không migrate | Bên nhận tái tạo AAD/wire format khác bên gửi. |

**Không phải mọi trường hợp trên đều ném đúng một exception class.** Chẳng hạn key không đủ 32 byte có thể bị `InvalidKeyException` ngay tại `Cipher.init`; nonce không đủ 12 byte có thể bị `InvalidAlgorithmParameterException`; Base64 không hợp lệ có thể ném `IllegalArgumentException` **trước decrypt**. Truncated payload có thể bị reject ngay bởi parser length check, trước khi đến `doFinal`.

Một application error contract hợp lý tách:

~~~text
INVALID_FORMAT
KEY_OR_CONFIG_ERROR
IO_OR_TRANSPORT_ERROR
AUTHENTICATION_FAILED
VALIDATED_BUT_INVALID_SCHEMA
REPLAY_OR_BUSINESS_RULE
~~~

Đừng tự động chuyển tất cả thành “tag bị sửa bởi attacker”; operator cần đủ metadata an toàn để điều tra cả bug serializer, key rotation và lỗi storage/network.

## 4. API Java 11: chọn đúng Cipher và spec

JDK 11 có ChaCha20 và ChaCha20-Poly1305 theo JEP 329. Chúng có **parameter spec khác nhau**:

| Transformation | Mục đích | Tham số Java 11 |
| --- | --- | --- |
| `Cipher.getInstance("ChaCha20")` | Stream cipher thuần, không tích hợp tag. | `ChaCha20ParameterSpec(nonce, counter)` |
| `Cipher.getInstance("ChaCha20-Poly1305")` | AEAD, mã hóa + xác thực. | `IvParameterSpec(nonce12)` |
| `Cipher.getInstance("AES/GCM/NoPadding")` | AEAD khác, dựa trên AES/GCM. | `GCMParameterSpec` theo hợp đồng AES/GCM. |

**Đúng cho ChaCha20-Poly1305:**

~~~java
Cipher c = Cipher.getInstance("ChaCha20-Poly1305");
c.init(Cipher.DECRYPT_MODE,
    new SecretKeySpec(keyBytes, "ChaCha20"),
    new IvParameterSpec(nonceBytes));
c.updateAAD(aadBytes);
byte[] plain = c.doFinal(ciphertextAndTag);
~~~

Đây là **đoạn minh họa** với key 32 byte, nonce 12 byte và các mảng đã validate. `SecretKeySpec` chỉ đóng gói key bytes, **không làm mật khẩu yếu trở nên an toàn**. Nếu tạo key từ password, phải dùng password KDF phù hợp; production thường dùng KMS/keystore hoặc key từ authenticated key exchange.

**Không dùng** `ChaCha20ParameterSpec(nonce, 1)` cho `ChaCha20-Poly1305`. Spec đó dành cho ChaCha20 thuần, có counter tùy chỉnh. ChaCha20-Poly1305 sử dụng cấu trúc counter theo RFC 8439, không yêu cầu caller tự chọn giá trị counter qua `ChaCha20ParameterSpec`.

### 4.1. Thứ tự các lệnh là một phần của contract

~~~text
Cipher.getInstance → init(mode,key,nonce) → updateAAD(aad) → update/doFinal(data)
~~~

Với AEAD, truyền AAD **trước dữ liệu được encrypt/decrypt**. Gọi `updateAAD` sau `update` hoặc sau `doFinal` trong cùng operation có thể tạo `IllegalStateException`. Mỗi operation nên có `Cipher` riêng, không chia sẻ mutable instance giữa các threads.

## 5. Ví dụ Java 11 hoàn chỉnh: phát hiện sáu dạng lỗi

Chương trình dùng `SecureRandom` tạo một key 32 byte và nonce 12 byte mới, encrypt **một lần**, rồi thử decrypt đúng và với các input sai. Việc decrypt nhiều lần ở đây không phải nonce reuse trong **encrypt**.

**Tệp: `ChaChaBadTagDemo.java`**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class ChaChaBadTagDemo {
    private static final String ALGORITHM = "ChaCha20-Poly1305";
    private ChaChaBadTagDemo() {}

    static byte[] encrypt(byte[] key, byte[] nonce,
                          byte[] aad, byte[] plain)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(ALGORITHM);
        cipher.init(Cipher.ENCRYPT_MODE,
            new SecretKeySpec(key, "ChaCha20"),
            new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plain);
    }

    static byte[] decrypt(byte[] key, byte[] nonce,
                          byte[] aad, byte[] encrypted)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(ALGORITHM);
        cipher.init(Cipher.DECRYPT_MODE,
            new SecretKeySpec(key, "ChaCha20"),
            new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(encrypted);
    }

    static String result(byte[] key, byte[] nonce, byte[] aad,
                         byte[] encrypted)
            throws GeneralSecurityException {
        try {
            decrypt(key, nonce, aad, encrypted);
            return "UNEXPECTED_ACCEPT";
        } catch (AEADBadTagException invalid) {
            return "REJECTED";
        }
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        byte[] key = new byte[32];
        byte[] nonce = new byte[12];
        random.nextBytes(key);
        random.nextBytes(nonce);
        byte[] aad = "order:v1:42".getBytes(StandardCharsets.UTF_8);
        byte[] plain = "Xin chào Java 11"
            .getBytes(StandardCharsets.UTF_8);

        byte[] encrypted = encrypt(key, nonce, aad, plain);
        byte[] restored = decrypt(key, nonce, aad, encrypted);
        if (!Arrays.equals(plain, restored)) {
            throw new AssertionError("Round-trip mismatch");
        }

        byte[] wrongCiphertext = encrypted.clone();
        wrongCiphertext[0] ^= 1;
        byte[] wrongTag = encrypted.clone();
        wrongTag[wrongTag.length - 1] ^= 1;
        byte[] wrongAad = aad.clone();
        wrongAad[0] ^= 1;
        byte[] wrongNonce = nonce.clone();
        wrongNonce[0] ^= 1;
        byte[] wrongKey = key.clone();
        wrongKey[0] ^= 1;
        byte[] truncated = Arrays.copyOf(encrypted,
            encrypted.length - 1);

        System.out.println("plain.bytes=" + plain.length);
        System.out.println("ciphertext_plus_tag.bytes=" +
            encrypted.length);
        System.out.println("roundtrip=" +
            new String(restored, StandardCharsets.UTF_8));
        System.out.println("tampered.ciphertext=" +
            result(key, nonce, aad, wrongCiphertext));
        System.out.println("tampered.tag=" +
            result(key, nonce, aad, wrongTag));
        System.out.println("wrong.aad=" +
            result(key, nonce, wrongAad, encrypted));
        System.out.println("wrong.nonce=" +
            result(key, wrongNonce, aad, encrypted));
        System.out.println("wrong.key=" +
            result(wrongKey, nonce, aad, encrypted));
        System.out.println("truncated=" +
            result(key, nonce, aad, truncated));

        Arrays.fill(key, (byte) 0);
        Arrays.fill(restored, (byte) 0);
        Arrays.fill(plain, (byte) 0);
    }
}
~~~

**Biên dịch và chạy Java 11:**

~~~bash
javac --release 11 -encoding UTF-8 ChaChaBadTagDemo.java
java ChaChaBadTagDemo
~~~

**Stdout đã kiểm chứng chính xác:**

~~~text
plain.bytes=17
ciphertext_plus_tag.bytes=33
roundtrip=Xin chào Java 11
tampered.ciphertext=REJECTED
tampered.tag=REJECTED
wrong.aad=REJECTED
wrong.nonce=REJECTED
wrong.key=REJECTED
truncated=REJECTED
~~~

**Giải thích kết quả:**

1. `"Xin chào Java 11"` mã hóa thành **17 byte UTF-8** (chữ `à` chiếm hai byte); không lấy `String.length()` để đo số byte.
2. Output encrypt là `17 ciphertext bytes + 16 tag bytes = 33 bytes`.
3. `encrypt` chỉ gọi một lần với cặp key/nonce. Sau đó `decrypt` có thể được thử với các biến thể khác nhau để xác nhận rejection.
4. Sửa `encrypted[0]` làm sai ciphertext; sửa byte cuối làm sai tag.
5. `wrongAad` khác một byte dù encrypted bytes không hề thay đổi; kết quả vẫn `REJECTED`.
6. `wrongNonce` và `wrongKey` đều đúng length nhưng giá trị sai, do đó xác thực không thành công.
7. `truncated` cắt một byte cuối của tag, khiến message không khớp đầu vào encrypt.
8. Hàm `result` in `UNEXPECTED_ACCEPT` nếu input sai vẫn được chấp nhận; test/CI nên **assert điều này không bao giờ xảy ra** trong các case đã xây. Không coi nó là cách API production trả lỗi.
9. `Arrays.fill` nhằm giảm thời gian tồn tại một số mảng nhạy cảm do demo sở hữu, nhưng không bảo đảm xóa các bản sao khác trong JCA/JVM. Không in secret key, nonce hoặc raw session material trong log.

Hai lời gọi dùng `SecretKeySpec(key, "ChaCha20")` nhưng transformation là `"ChaCha20-Poly1305"`; điều đó hợp lệ trong JDK 11. Khi decrypt thất bại, **không** tìm cách phục hồi plaintext từ exception.

## 6. Thiết kế một API decrypt có fail-closed semantics

Một phương thức an toàn nên **validate độ dài trước**, dùng AEAD đúng cách và chỉ trả dữ liệu khi `doFinal` thành công:

~~~java
static byte[] decryptOrReject(byte[] key, byte[] nonce,
        byte[] aad, byte[] encrypted) throws GeneralSecurityException {
    if (key == null || key.length != 32 ||
        nonce == null || nonce.length != 12 ||
        encrypted == null || encrypted.length < 16 ||
        aad == null) {
        throw new IllegalArgumentException("Invalid AEAD record");
    }

    try {
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.DECRYPT_MODE,
            new SecretKeySpec(key, "ChaCha20"),
            new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(encrypted);
    } catch (AEADBadTagException invalid) {
        throw new SecurityException("Authentication failed", invalid);
    }
}
~~~

Đây là **method minh họa**, không phải file độc lập; cần import `GeneralSecurityException`, `Cipher`, `IvParameterSpec`, `SecretKeySpec`, `AEADBadTagException`. Ngoài minimum length, production phải kiểm **maximum record bytes**, allowed version/key ID và application context trước khi cấp phát/giải mã.

**Fail-closed có nghĩa:**

- Không trả, log hay parse plaintext khi tag chưa được xác thực.
- Không ghi dữ liệu nghiệp vụ vào DB, không gửi event và không publish file kết quả trước khi biết tag hợp lệ.
- Không bắt exception rồi trả `new byte[0]` để ngụy trang thành dữ liệu rỗng hợp lệ.
- Không retry bằng `ChaCha20` thuần hoặc bỏ AAD/tag để “đọc bằng mọi giá”.
- Không gửi stack trace/chi tiết nội bộ về key selection cho remote client.
- Nếu decrypt file vào staging, phải cleanup khi tag fail và chỉ publish sau verify.

**Cảnh báo với streaming:** Một số API/provider có thể trả plaintext tạm trong quá trình `Cipher.update` trước khi `doFinal` xác thực tag. Không để output trung gian đó đến consumer tin cậy hoặc trở thành file chính thức. Nếu message rất lớn, cần vùng staging được bảo vệ hoặc protocol AEAD theo từng record có tag riêng và chống mất/reorder record.

## 7. Nonce uniqueness: không được sửa lỗi sai bằng cách bỏ nonce

ChaCha20-Poly1305 dùng **12-byte nonce** và nonce có thể truyền công khai. Điều kiện không thể bỏ qua: với **một key cố định**, mỗi lần **ENCRYPT** một message mới phải dùng nonce **khác**.

Tái sử dụng cùng `(key, nonce)` cho hai plaintext khác nhau có thể làm lộ quan hệ giữa plaintexts và phá cơ chế xác thực. `AEADBadTagException` **không** phát hiện tất cả lỗi nonce reuse; hai bản mã được tạo sai với cùng nonce vẫn có thể decrypt thành công với tag đúng.

**Các chiến lược:**

- Key chỉ dùng cho một số lượng record được kiểm soát: nonce 96 bit sinh bằng `SecureRandom` mới mỗi lần có thể phù hợp khi đã đánh giá rủi ro birthday collision.
- Khối lượng lớn, nhiều process/node cùng key: phân vùng nonce theo sender ID và counter, hoặc cấp phát sequence bền vững/đồng bộ có đảm bảo uniqueness.
- Khi khởi động lại hoặc rollback, không reset counter dưới **cùng key**.
- Không dùng `java.util.Random`, timestamp đơn thuần, ID trùng hoặc một nonce cố định trong production.
- Key rotation và hạn mức bản mã theo key là phần của key-management policy.
- Phải kiểm “nonce unique per encryption” **độc lập** với test tag tampering.

**Decrypt cùng một encrypted record nhiều lần** không tự là encrypt mới, nhưng có thể vi phạm **anti-replay policy** ở tầng ứng dụng. AEAD chỉ xác thực nội dung theo key, không nhớ lịch sử message.

## 8. AAD byte-exact và những lỗi canonicalization

AAD giúp gắn bản mã vào đúng context, ví dụ:

~~~text
protocol=invoice-v1;tenant=shop-a;record=123;direction=server-to-client
~~~

Nếu encrypt dùng chuỗi trên nhưng decrypt đảo thứ tự các trường, thay charset hoặc thay chữ hoa/thường, tag không còn match. Cả hai phía phải thống nhất **định dạng byte**, không chỉ parse ra object giống nhau.

| Lỗi | Vì sao xác thực fail | Cách khắc phục |
| --- | --- | --- |
| Java bên gửi UTF-8, bên nhận charset mặc định khác | Bytes AAD khác. | Dùng `StandardCharsets.UTF_8` rõ ràng. |
| JSON serialize field order khác | Raw AAD không giống từng byte. | Canonical encoding hoặc dùng raw original bytes. |
| Cộng field bằng delimiter mà input chứa delimiter | Parse mơ hồ/đổi dữ liệu. | Length-prefix, escape hoặc binary serialization đúng chuẩn. |
| Header version không được đưa vào AAD | Có nguy cơ đổi ngữ nghĩa mà tag không bảo vệ. | Bind version/algorithm/context theo protocol. |
| Server tự đổi tenant ID sau khi decrypt | Có thể dẫn đến cross-tenant mixup. | Compare AAD với trusted session/authorization context. |
| Cố decrypt không AAD khi fail | Bỏ cơ chế binding metadata. | Sửa logic tạo AAD; không downgrade. |

**AAD không mã hóa dữ liệu.** Không đưa một bí mật vào AAD vì nghĩ tag sẽ giấu nó; nếu cần bí mật, để trong plaintext đã mã hóa. AAD nên chứa metadata cần bảo vệ tính toàn vẹn, đồng thời được so sánh với identity/context tin cậy.

## 9. Envelope và phân biệt format error với tag error

Một format ứng dụng có thể được thiết kế như:

~~~text
magic(4B) | version(1B) | keyId(2B) | nonce(12B) | ciphertext(NB) | tag(16B)
~~~

Đây chỉ là **ví dụ cấu trúc**, không phải giao thức Java bắt buộc. Bản ghi nhỏ nhất với plaintext rỗng là **35 byte** (4+1+2+12+16). Header `magic/version/keyId` cần được xác thực bằng AAD (hoặc cơ chế khác đã thiết kế), vì attacker có thể sửa header được truyền công khai.

Quy trình nhận:

1. Kiểm chiều dài min/max và decoder (binary/Base64), không decode thành String UTF-8 tùy tiện.
2. Kiểm magic, version và key ID thuộc danh sách cho phép.
3. Parse đúng **12 byte nonce** và phần còn lại gồm ciphertext+tag **ít nhất 16 byte**.
4. Chọn key theo key ID đã kiểm policy, đồng thời xác định tenant/role/context độc lập.
5. Dùng **đúng byte header** và metadata cần thiết làm AAD.
6. Init Cipher, gọi `doFinal`; nếu tag fail, reject ngay.
7. Chỉ sau thành công mới parse schema, kiểm authorization và replay state, rồi commit.

Ví dụ parse, **không phải chương trình độc lập**:

~~~java
if (packet.length < 35 || packet.length > MAX_PACKET_BYTES) {
    throw new IOException("Invalid record size");
}
byte[] header = Arrays.copyOfRange(packet, 0, 7);
validateHeaderAndKeyId(header);
byte[] nonce = Arrays.copyOfRange(packet, 7, 19);
byte[] ciphertextAndTag =
    Arrays.copyOfRange(packet, 19, packet.length);

SecretKeySpec key = lookupAllowedKey(header);
Cipher decryptor = Cipher.getInstance("ChaCha20-Poly1305");
decryptor.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(nonce));
decryptor.updateAAD(header);
byte[] plaintext = decryptor.doFinal(ciphertextAndTag);
~~~

`packet`, `MAX_PACKET_BYTES`, `validateHeaderAndKeyId` và `lookupAllowedKey` do ứng dụng định nghĩa. Mã cần các import liên quan. `keyId` trong header là untrusted cho đến khi policy và tag được kiểm; không dùng nó làm bằng chứng về danh tính của người gửi.

**Đừng tạo “AEADBadTagException giả” khi parse Base64 thất bại.** Đó là lỗi format; với caller bên ngoài có thể vẫn trả một thông báo tổng quát để không tạo oracle, còn logs nội bộ cần phân loại chính xác nhưng không lộ secret.

## 10. RFC 8439: test vector độc lập, không chỉ round-trip

Round-trip dùng cùng provider có thể pass dù cả hai chiều cùng áp dụng một cách encode sai. **Known-answer test** với giá trị công khai theo RFC 8439 (mục 2.8.2) kiểm cả ciphertext **và tag** chính xác.

Key trong vector dài 32 byte (`80..9f`), nonce 12 byte `070000004041424344454647`, AAD `50515253c0c1c2c3c4c5c6c7`. Scalar/key ở đây là **test data công khai**, tuyệt đối không dùng cho production.

**Tệp: `ChaChaRfc8439Vector.java`**

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class ChaChaRfc8439Vector {
    private ChaChaRfc8439Vector() {}

    static byte[] fromHex(String hex) {
        if ((hex.length() & 1) != 0) throw new IllegalArgumentException();
        byte[] out = new byte[hex.length() / 2];
        for (int i = 0; i < out.length; i++) {
            int hi = Character.digit(hex.charAt(i * 2), 16);
            int lo = Character.digit(hex.charAt(i * 2 + 1), 16);
            if (hi < 0 || lo < 0) throw new IllegalArgumentException();
            out[i] = (byte) ((hi << 4) | lo);
        }
        return out;
    }

    public static void main(String[] args) throws Exception {
        byte[] key = fromHex(
            "808182838485868788898a8b8c8d8e8f" +
            "909192939495969798999a9b9c9d9e9f");
        byte[] nonce = fromHex("070000004041424344454647");
        byte[] aad = fromHex("50515253c0c1c2c3c4c5c6c7");
        byte[] plain = ("Ladies and Gentlemen of the class of '99: " +
            "If I could offer you only one tip for the future, " +
            "sunscreen would be it.").getBytes(StandardCharsets.US_ASCII);
        byte[] expected = fromHex(
            "d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d6" +
            "3dbea45e8ca9671282fafb69da92728b1a71de0a9e060b2905d6a5b67ecd3b36" +
            "92ddbd7f2d778b8c9803aee328091b58fab324e4fad675945585808b4831d7bc3" +
            "ff4def08e4b7a9de576d26586cec64b6116" +
            "1ae10b594f09e26a7e902ecbd0600691");
        SecretKeySpec secret = new SecretKeySpec(key, "ChaCha20");
        Cipher enc = Cipher.getInstance("ChaCha20-Poly1305");
        enc.init(Cipher.ENCRYPT_MODE, secret, new IvParameterSpec(nonce));
        enc.updateAAD(aad);
        byte[] actual = enc.doFinal(plain);

        if (!Arrays.equals(actual, expected))
            throw new AssertionError("RFC 8439 vector mismatch");

        Cipher dec = Cipher.getInstance("ChaCha20-Poly1305");
        dec.init(Cipher.DECRYPT_MODE, secret, new IvParameterSpec(nonce));
        dec.updateAAD(aad);
        if (!Arrays.equals(plain, dec.doFinal(actual)))
            throw new AssertionError("Round trip mismatch");

        Cipher wrong = Cipher.getInstance("ChaCha20-Poly1305");
        wrong.init(Cipher.DECRYPT_MODE, secret, new IvParameterSpec(nonce));
        wrong.updateAAD(new byte[] {1});
        boolean rejected = false;
        try {
            wrong.doFinal(actual);
        } catch (AEADBadTagException expectedFailure) {
            rejected = true;
        }
        if (!rejected) throw new AssertionError("Invalid AAD accepted");
        System.out.println("rfc8439.aead.vector=true");
        System.out.println("rfc8439.aead.decrypt=true");
        System.out.println("rfc8439.wrong.aad.rejected=true");
    }
}
~~~

Chạy trên Java 11:

~~~bash
javac --release 11 -encoding UTF-8 ChaChaRfc8439Vector.java
java ChaChaRfc8439Vector
~~~

**Stdout đã được kiểm chứng:**

~~~text
rfc8439.aead.vector=true
rfc8439.aead.decrypt=true
rfc8439.wrong.aad.rejected=true
~~~

Chương trình đã được biên dịch với `javac --release 11` và chạy thành công với provider hỗ trợ thuật toán. Nó khớp từng byte của ciphertext + tag được RFC 8439 công bố. Không in raw secret của production để tạo expected stdout.

## 11. Kiểm thử tự động với JUnit Jupiter

Bộ test sau dùng **JUnit Jupiter 5.x** tương thích Java 11, nằm cùng package với `ChaChaBadTagDemo.java`. JUnit cần cấu hình dependency/test runner Maven hoặc Gradle; **không có sẵn trong JDK**.

**Tệp: `ChaChaBadTagDemoTest.java`**

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ChaChaBadTagDemoTest {
    private static byte[] key() {
        byte[] k = new byte[32];
        Arrays.fill(k, (byte) 7); // Chỉ dùng cho test.
        return k;
    }

    private static byte[] nonce() {
        byte[] n = new byte[12];
        Arrays.fill(n, (byte) 9); // Chỉ dùng cho test.
        return n;
    }

    @Test
    void correctParametersRoundTrip() throws Exception {
        byte[] aad = "header-v1".getBytes(StandardCharsets.UTF_8);
        byte[] plain = "Xin chào".getBytes(StandardCharsets.UTF_8);
        byte[] encrypted = ChaChaBadTagDemo.encrypt(
            key(), nonce(), aad, plain);
        assertArrayEquals(plain, ChaChaBadTagDemo.decrypt(
            key(), nonce(), aad, encrypted));
        assertEquals(plain.length + 16, encrypted.length);
    }

    @Test
    void modifiedTagIsRejected() throws Exception {
        byte[] aad = new byte[] {1, 2};
        byte[] encrypted = ChaChaBadTagDemo.encrypt(
            key(), nonce(), aad, new byte[] {11, 22, 33});
        encrypted[encrypted.length - 1] ^= 1;
        assertThrows(AEADBadTagException.class,
            () -> ChaChaBadTagDemo.decrypt(
                key(), nonce(), aad, encrypted));
    }

    @Test
    void changedAadIsRejected() throws Exception {
        byte[] encrypted = ChaChaBadTagDemo.encrypt(
            key(), nonce(), new byte[] {1}, new byte[] {99});
        assertThrows(AEADBadTagException.class,
            () -> ChaChaBadTagDemo.decrypt(
                key(), nonce(), new byte[] {2}, encrypted));
    }

    @Test
    void truncatedTagIsRejected() throws Exception {
        byte[] encrypted = ChaChaBadTagDemo.encrypt(
            key(), nonce(), new byte[0], new byte[] {10, 20, 30});
        byte[] cut = Arrays.copyOf(encrypted, encrypted.length - 1);
        assertThrows(AEADBadTagException.class,
            () -> ChaChaBadTagDemo.decrypt(
                key(), nonce(), new byte[0], cut));
    }
}
~~~

Test dùng key/nonce cố định **chỉ trong môi trường test**, không được lặp lại cách này với key thật trong nhiều lần encrypt production. Để kiểm đúng tính an toàn của hệ thống, cần thêm các case: short key, short nonce, wrong key ID, record vượt max length, wrong version, replay message, ciphertext tag bị cắt, JSON schema sai sau decrypt và key rotation.

Một số provider có thể báo lỗi format/tham số khác nhau đối với đầu vào quá ngắn hoặc không hợp lệ. Các test ở trên cố tình dùng ciphertext đủ dài để kiểm trọng tâm `AEADBadTagException`.

## 12. Streaming và giao dịch: tag ở cuối, không commit sớm

Một message AEAD có tag nằm cuối. Khi decrypt dữ liệu rất lớn, **không mặc định plaintext do `Cipher.update` phát ra là an toàn để dùng trước `doFinal`**. Provider có thể buffer hoặc phát data ở các thời điểm khác nhau; hợp đồng an toàn của ứng dụng là **chỉ chấp nhận sau khi tag được xác minh thành công**.

Mô hình:

~~~text
RECEIVE_ENCRYPTED
   |
   v
VALIDATE_FORMAT_AND_LIMITS
   |
   v
DECRYPT_TO_PRIVATE_STAGING
   |                    \
   |                     +-- ERROR / TAG FAIL → CLEANUP, REJECT
   v
TAG_VERIFIED
   |
   v
SCHEMA / AUTHORIZATION / REPLAY CHECK
   |
   v
ATOMIC_OR_CONTROLLED_PUBLISH
   |
   v
COMPLETED
~~~

Với file nhạy cảm, staging cần quyền tối thiểu, không index/chia sẻ tự động, có cleanup kể cả khi bị interrupt. Nếu tag fail, xóa file tạm, không rename sang file chính và không cho consumer thấy dữ liệu có thể đã được ghi một phần.

Nếu cần xử lý realtime, thiết kế **AEAD theo từng record/chunk** với nonce riêng và AAD chứa sequence/record type; chỉ publish record sau khi **tag của record đó** pass. Tuy nhiên các record tag hợp lệ không tự chứng minh toàn luồng không bị cắt, mất/reorder/duplicate. Cần final marker, authenticated total length, transcript/final commitment hoặc chính sách protocol tương đương.

## 13. Anti-replay và context binding

Nếu attacker lấy một encrypted message hợp lệ và gửi lại **nguyên vẹn**, `Cipher.doFinal` có thể thành công lần nữa: tag không nói message đã xử lý bao nhiêu lần. Nonce uniqueness là yêu cầu của **encryption**, không tự là replay protection của **decryption**.

Nếu ứng dụng cần chống replay:

- Đưa session ID/sequence/direction/version vào AAD.
- Duy trì seen-set, high-water mark hoặc replay window phù hợp với tính thứ tự và số connection.
- Kiểm trạng thái replay trong transaction/commit có atomicity, nếu nhiều worker có thể xử lý cùng message.
- Không dùng timestamp làm cơ chế duy nhất mà không giải quyết clock skew và replay window.
- Rotate keys/session và xử lý restart/recovery sao cho sequence không bị lặp ngoài ý muốn.

**Tag hợp lệ cũng không đồng nghĩa sender đã được xác thực danh tính riêng.** Nếu hai service chia sẻ cùng secret key, tag chỉ chứng minh một phía sở hữu key. Cần authentication, authorization, key scope và provenance theo threat model.

## 14. Lỗi thực tế: phân loại, log và cảnh báo

Một pipeline hợp lý gồm:

~~~text
Transport / decode / parse envelope
   +-- malformed base64 / size  ------> FORMAT_ERROR
   +-- incomplete read / disk I/O ----> IO_ERROR
   +-- wrong key length/provider -----> KEY_CONFIG_ERROR
   |
   v
Cipher.init / updateAAD / doFinal
   +-- cannot verify tag -----------> AUTHENTICATION_FAILED
   |
   v
Authenticated plaintext
   +-- invalid JSON/schema ---------> SCHEMA_ERROR
   +-- replay / unauthorized --------> BUSINESS_SECURITY_ERROR
   |
   v
ACCEPT
~~~

Khi `AEADBadTagException` tăng đột biến sau một deploy, điều tra **cả lỗi phần mềm lẫn tấn công**: version serialization, thứ tự AAD, charset, key IDs/rotation, nonce handling, database migration, file corruption, network truncation. Không tự công bố “dữ liệu bị hacker sửa” dựa duy nhất vào exception.

**Logging an toàn** có thể gồm algorithm, format version, route, bytes, mã lỗi, JDK/provider, correlation ID, và keyId đã được lọc. Tránh in secret key, raw plaintext, raw sensitive AAD, credentials hay nội dung exception của provider ra API công cộng. Giữ lỗi của client tương đối đồng nhất để không tạo decryption oracle, nhưng operator vẫn có category an toàn.

Phân biệt exception:

| Exception | Diễn giải thường gặp | Phản ứng |
| --- | --- | --- |
| `AEADBadTagException` | Authentication tag không xác minh được. | Reject, không trả plaintext. |
| `BadPaddingException` | Lớp cha, còn có lỗi mode khác. | Catch sau subtype nếu cần. |
| `InvalidKeyException` | Key sai length/type/provider. | Kiểm cấu hình, không retry mù quáng. |
| `InvalidAlgorithmParameterException` | Nonce/spec sai. | Sửa wire/config; không đoán nonce. |
| `NoSuchAlgorithmException` | Transformation/provider không khả dụng. | Fail deployment/config. |
| `IllegalStateException` | Sai thứ tự lifecycle/cipher reuse. | Sửa code. |
| `IOException` | Dữ liệu đến thiếu hoặc lỗi storage/network. | Phân loại riêng, cleanup. |
| `IllegalArgumentException` | Base64 hoặc envelope sai format. | Từ chối input có giới hạn. |

## 15. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Dùng `ChaCha20` thuần cho message cần integrity | Không kiểm tampering. | Dùng `ChaCha20-Poly1305`. |
| Dùng `ChaCha20ParameterSpec` cho AEAD | Spec sai. | `IvParameterSpec` 12-byte nonce. |
| Nhầm nonce 12 byte với tag 16 byte | Sai offset và bad tag. | Quy định wire format rõ ràng. |
| Chỉ truyền ciphertext mà không truyền tag | Không thể xác thực. | Truyền `ciphertext || tag`. |
| Gọi `updateAAD` sau `update` | Vi phạm thứ tự AEAD. | Cập nhật AAD trước body. |
| Gọi `new String(ciphertext, UTF_8)` rồi serialize | Có thể hỏng binary. | Dùng byte[]/Base64 đúng schema. |
| AAD không canonical | Sai bytes ở hai phía. | Charset/format/byte order cố định. |
| Bỏ AAD khi tag fail | Bỏ binding context, tăng rủi ro tấn công. | Sửa chuẩn AAD chứ không downgrade. |
| Reuse (key, nonce) nhiều lần encrypt | Phá tính an toàn nghiêm trọng. | Cấp nonce unique, rotate key. |
| Dùng password trực tiếp làm key | Key có entropy thấp. | KDF mật khẩu hoặc KMS. |
| Đưa plaintext trước xác thực tới DB | Side effect không rollback được. | Staging/verify trước commit. |
| Tag pass = chống replay | Bản mã hợp lệ có thể phát lại. | Session/sequence replay policy. |
| Catch `AEADBadTagException` rồi trả dữ liệu rỗng | Che auth failure. | Trả trạng thái lỗi, fail closed. |
| Kết luận chắc chắn có attacker | Bug key/AAD/format cũng gây fail. | Điều tra đa nguyên nhân. |
| Chỉ test round-trip | Có thể bỏ sót sai RFC format. | Thêm known-answer vector. |
| Log secret, nonce và raw AAD | Rò dữ liệu hoặc hỗ trợ tấn công. | Safe telemetry. |
| Bỏ qua provider differences | Triển khai đích có thể không hỗ trợ. | Test Java/runtime thực tế. |

## 16. Bài tập áp dụng

**Bài 1 — kích thước:** Một plaintext dài 100 byte được encrypt bằng ChaCha20-Poly1305. `doFinal` trả bao nhiêu byte? **Đáp án:** 116 byte (`100 ciphertext + 16 tag`). Nonce 12 byte được lưu riêng nếu protocol yêu cầu.

**Bài 2 — bị sửa bit:** Chạy `ChaChaBadTagDemo.java`, đảo một bit khác của ciphertext. Kiểm chương trình luôn không chấp nhận plaintext (case đã xây có xác suất giả mạo tag cực thấp).

**Bài 3 — AAD:** Encrypt với `tenant=alpha` và decrypt với `tenant=beta`. Tại sao không được bỏ AAD để “sửa lỗi”? Thiết kế metadata binding cho tenant/record ID.

**Bài 4 — lỗi key:** Key 31 byte làm `Cipher.init` thất bại; phân biệt nó với key 32 byte sai nhưng `doFinal` báo tag mismatch.

**Bài 5 — tag bị cắt:** Một encrypted body chứa plaintext 0 byte nhưng có tag 16 byte. Nếu bị cắt thành 15 byte, tầng nào nên reject: parser hay Cipher? Nêu lợi ích của length validation sớm.

**Bài 6 — nonce reuse:** Vì sao dùng cùng (key,nonce) để encrypt hai plaintext là lỗi nghiêm trọng dù cả hai decrypt có thể hợp lệ? Đề xuất nonce allocator cho hệ thống có nhiều node.

**Bài 7 — RFC:** Chạy `ChaChaRfc8439Vector.java`, sửa một byte expected tag để phép so sánh thất bại, sau đó khôi phục test vector chuẩn.

**Bài 8 — replay:** Gửi lại message cũ với nonce/ciphertext/tag giữ nguyên. Vì sao `doFinal` vẫn có thể thành công? Thiết kế seen-sequence window.

**Bài 9 — streaming:** Khi decrypt file lớn, tag fail ở cuối nhưng vài KB plaintext đã ghi DB. Sửa pipeline để commit chỉ sau khi verified; nói rõ nơi lưu staging an toàn.

**Bài 10 — base64:** Tạo envelope binary có header/version/keyId/nonce/ciphertext/tag, encode Base64, decode lại và xác minh AAD byte-for-byte.

**Bài 11 — exception:** Thiết kế service trả một lỗi chung cho client khi decrypt fail, nhưng log nội bộ phân biệt FORMAT, IO, KEY_CONFIG và AUTH_FAILURE mà không tiết lộ secret.

**Bài 12 — versioning:** Nâng format từ v1 sang v2 thay đổi AAD. Làm thế nào để duy trì khả năng đọc bản cũ mà không tự động downgrade một ciphertext mới?

## 17. Checklist triển khai

1. Sử dụng `"ChaCha20-Poly1305"`, **không** dùng `"ChaCha20"` thuần cho message cần xác thực.
2. Key đủ 32 byte từ nguồn đáng tin, nonce 12 byte **unique per key per encryption**.
3. Tag 16 byte còn đầy đủ khi decrypt; parse envelope với min/max length.
4. `IvParameterSpec` đúng, `updateAAD` trước body, `doFinal` kiểm tag.
5. AAD canonical và bind đúng version, tenant, direction, record/session theo threat model.
6. Không publish plaintext nếu tag fail, kể cả từ `update` khi streaming.
7. Tách FORMAT/IO/CONFIG/AUTH/SCHEMA errors; không coi `AEADBadTagException` là bằng chứng duy nhất về xâm nhập.
8. Chống replay riêng bằng sequence/session và state phù hợp.
9. Staging/file cleanup và atomic/controlled publish khi xử lý tài liệu lớn.
10. Không log raw keys/plaintext/sensitive AAD; giữ telemetry có giới hạn.
11. Có test sửa ciphertext/tag/AAD/nonce/key, test truncated input và RFC 8439 vector.
12. Runtime thực sự có provider `ChaCha20-Poly1305` hỗ trợ, code target Java 11 được build/test trên CI.
13. Key rotation, nonce allocator, KDF/keystore và authorization có chính sách rõ ràng.
14. Không downgrade sang cipher không xác thực chỉ để giải mã dữ liệu lỗi.

## 18. Nguồn và ghi nhớ

- [Java SE 11 — AEADBadTagException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/AEADBadTagException.html): lý do lỗi xác thực tag, quan hệ kế thừa với `BadPaddingException`.
- [Java SE 11 — Cipher](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html): `getInstance`, `init`, `updateAAD`, `doFinal`, nonce requirements.
- [Java SE 11 — IvParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html): dùng nonce cho AEAD.
- [Java SE 11 — ChaCha20ParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html): tham số của ChaCha20 **không phải** ChaCha20-Poly1305.
- [Java Security Standard Algorithm Names — Java 11](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html): tên transformation chuẩn.
- [JEP 329 — ChaCha20 and Poly1305 Cryptographic Algorithms](https://openjdk.org/jeps/329): thuật toán được đưa vào JDK 11.
- [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439): 256-bit key, 96-bit nonce, 128-bit tag, vector AEAD mục 2.8.2.
- [RFC 5116 — Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5116.html): khái niệm AEAD, AAD và nonce.

**Tổng kết:** `AEADBadTagException` có nghĩa **các byte đang giải mã không xác thực được với key/nonce/AAD/tag hiện tại**. Nó không nói cụ thể byte nào bị sửa hoặc ai gây ra lỗi. Trong Java 11, dùng **key 32B, nonce 12B, tag 16B**, `ChaCha20-Poly1305` với `IvParameterSpec`, AAD byte-exact và `doFinal`. **Luôn fail closed**, không phát tán plaintext khi tag fail, không reuse nonce cho encrypt cùng key, không bỏ tag/AAD và không xem tag hợp lệ là thay thế cho authorization hay chống replay.