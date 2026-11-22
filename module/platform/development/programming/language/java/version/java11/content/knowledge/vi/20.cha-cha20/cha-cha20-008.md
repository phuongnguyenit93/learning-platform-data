# Phân biệt cấu hình ChaCha20 thuần với chế độ AEAD trong Java 11

**Chủ đề cha:** ChaCha20  
**Bài học:** Phân biệt cấu hình ChaCha20 thuần với chế độ AEAD  
**Phạm vi:** Java 11, JCA/JCE `Cipher`, `ChaCha20ParameterSpec`, `IvParameterSpec`, `updateAAD`, `AEADBadTagException`, nonce, counter, authentication tag, định dạng message và kiểm thử chuẩn RFC 8439. Bài chỉ trình bày **kiến thức vẫn còn áp dụng đến hiện nay**, không hướng dẫn sử dụng các thuật toán lỗi thời hoặc cách bảo vệ dữ liệu thiếu xác thực như một lựa chọn mặc định.

Trong Java 11, `ChaCha20` và `ChaCha20-Poly1305` là **hai transformation khác nhau**. Cả hai dùng khóa 256 bit và nonce IETF 96 bit; tuy nhiên, cách khởi tạo, loại dữ liệu trả về và bảo đảm bảo mật khác nhau đáng kể:

- **ChaCha20 thuần** là stream cipher: XOR keystream với plaintext. Nó hỗ trợ mã hóa và giải mã nhưng **không phát hiện ciphertext bị sửa**; không có tag và không hỗ trợ AAD.
- **ChaCha20-Poly1305** là **AEAD — Authenticated Encryption with Associated Data**: bảo vệ cả tính bí mật lẫn tính toàn vẹn của ciphertext và AAD, dùng thẻ xác thực Poly1305 dài **128 bit = 16 byte**. Giải mã sai tag sẽ bị từ chối.

**Hướng dẫn cho code mới:** nếu cần mã hóa một thông điệp, bản ghi, dữ liệu truyền qua mạng hoặc file và cần phát hiện chỉnh sửa, ưu tiên `ChaCha20-Poly1305` (hoặc một AEAD được phê duyệt khác) trong một giao thức đã được thiết kế/đánh giá. ChaCha20 thuần chỉ là primitive hữu ích khi được một protocol hoàn chỉnh dùng cùng cơ chế xác thực độc lập đã được rà soát; đừng triển khai raw mode đơn lẻ như “secure message encryption”.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt stream cipher chỉ bảo vệ **confidentiality** với AEAD bảo vệ **confidentiality + integrity**.
2. Khởi tạo Java 11 đúng: `Cipher.getInstance("ChaCha20")` cùng `ChaCha20ParameterSpec(nonce, counter)`; `Cipher.getInstance("ChaCha20-Poly1305")` cùng `IvParameterSpec(nonce)`.
3. Hiểu nonce 12 byte, key 32 byte, counter khởi đầu của raw stream và counter được quản lý nội bộ trong AEAD.
4. Nhận biết raw ciphertext dài bằng plaintext, còn AEAD ciphertext kèm **16-byte tag**.
5. Đưa dữ liệu AAD vào `cipher.updateAAD(...)` **trước** payload để xác thực thông tin header mà không mã hóa nó.
6. Xử lý `AEADBadTagException` trên decrypt và không công bố plaintext trước khi xác minh tag hoàn tất.
7. Thiết kế nonce **không lặp với cùng key** và hiểu nguy cơ khi nhiều thread/instance hoặc restart hệ thống.
8. So sánh byte của RFC 8439 known-answer tests cho ChaCha20 thuần và ChaCha20-Poly1305.
9. Tự đóng gói envelope gồm version, nonce, ciphertext, tag và từ chối dữ liệu sai định dạng hoặc bị sửa.
10. Kiểm tra các trường hợp sai spec, nonce sai kích thước, AAD sai, ciphertext/tag bị flip bit và message bị cắt cụt.

## 2. Bảng so sánh kỹ thuật

| Đặc điểm | ChaCha20 thuần | ChaCha20-Poly1305 (AEAD) |
|---|---|---|
| `Cipher` transformation | `"ChaCha20"` | `"ChaCha20-Poly1305"` |
| Nền tảng mật mã | ChaCha20 stream cipher | ChaCha20 + one-time Poly1305 authenticator |
| Key | 32 byte (256 bit) | 32 byte (256 bit) |
| Nonce biến thể IETF | 12 byte (96 bit) | 12 byte (96 bit) |
| `AlgorithmParameterSpec` | `ChaCha20ParameterSpec` | `IvParameterSpec` |
| Caller truyền counter | Có, `int initialCounter` | Không; AEAD dùng counter theo công thức RFC |
| `updateAAD` | Không hỗ trợ | Có, trước dữ liệu |
| Mã hóa `n` byte | Output `n` byte | Output `n+16` byte (ciphertext + tag) |
| Xác minh sửa ciphertext | **Không** | **Có**, qua tag |
| Giải mã sai key/nonce | Có thể cho byte rác nhưng không báo integrity error | Không xác thực được và ném lỗi |
| Tag authentication | Không có | Poly1305 tag 16 byte |
| Vai trò khi xây protocol | Primitive, không phải message AEAD độc lập | AEAD chuẩn, cần nonce/key/protocol đúng |
| API Java 11 | Có từ JEP 329 | Có từ JEP 329 |

Cùng key loại `ChaCha20` không có nghĩa có thể đổi tên transformation tại runtime mà giữ nguyên toàn bộ tham số. Hai mode **không tương thích về cấu hình** và không dùng thay cho nhau khi giao thức đã quy định một mode cụ thể.

## 3. Vì sao ChaCha20 thuần không bảo đảm integrity?

ChaCha20 là stream cipher. Với plaintext `P`, keystream `S` sinh từ key, nonce và counter, ciphertext là:

```text
Encrypt: C = P XOR S
Decrypt: P = C XOR S
```

Nếu một người sửa ciphertext thành `C' = C XOR Δ`, bản rõ sau decrypt là:

```text
P' = C' XOR S
   = (P XOR S XOR Δ) XOR S
   = P XOR Δ
```

Một bit bị flip ở ciphertext sẽ làm flip bit tương ứng của plaintext mà không có cơ chế nhận diện từ chính stream cipher. Vì thế một request chứa `role=user`, `amount=...`, transaction status hoặc dữ liệu có cấu trúc không được coi là đáng tin nếu chỉ giải mã bằng raw ChaCha20. Kể cả khi byte đầu ra có vẻ là JSON/UTF-8 hợp lệ, điều đó **không chứng minh nó là nội dung người gửi đã tạo**.

ChaCha20 thuần cũng không có padding hoặc tag; với byte array `plaintext.length == n`, kết quả `doFinal` có `length == n`. Nếu cần biết dữ liệu bị sửa, không thể chỉ kiểm tra “giải mã có ra chữ hay không”. Hãy sử dụng một chế độ AEAD có xác thực.

### 3.1 Raw ChaCha20 có counter

`ChaCha20ParameterSpec` của Java 11 chứa nonce 12 byte và initial counter kiểu `int`. Counter là **vị trí block trong keystream**, không phải message ID hay nonce thay thế. Mỗi block ChaCha20 sinh 64 byte. Một message dài nhiều block tiêu thụ các counter liên tiếp; không được cố reuse những dải keystream bị chồng lấp bằng cách chỉ thay counter đầu cho message khác.

Đoạn minh họa raw mode, chưa phải chương trình độc lập (biến `secretKey` và `plaintext` cần được chuẩn bị):

```java
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);

Cipher raw = Cipher.getInstance("ChaCha20");
raw.init(Cipher.ENCRYPT_MODE, secretKey,
        new ChaCha20ParameterSpec(nonce, 1));
byte[] ciphertext = raw.doFinal(plaintext);
```

Cần import `SecureRandom`, `Cipher` và `ChaCha20ParameterSpec`. Khi decrypt, phải dùng cùng key, nonce và initial counter. Counter 1 được dùng để khớp vector mã hóa của RFC 8439; không có quy tắc “mọi luồng dữ liệu đều được tự ý dùng lại nonce, chỉ cần đổi counter”.

## 4. AEAD: ChaCha20-Poly1305 xác thực cái gì?

ChaCha20-Poly1305 là một cấu trúc **Authenticated Encryption with Associated Data**. Nó mã hóa plaintext bằng ChaCha20, dùng Poly1305 để xác thực ciphertext và AAD, cho output theo dạng:

```text
Input:
    key = 32 byte
    nonce = 12 byte
    plaintext = n byte
    AAD = bytes của metadata (có thể rỗng)

Encrypt:
    ChaCha20-Poly1305(key, nonce, plaintext, AAD)

Output:
    ciphertext (n byte) || authentication tag (16 byte)
```

**AAD — Additional Authenticated Data** có thể gồm protocol version, message type, sequence number, tenant ID đã xác minh, content type, key ID, record metadata hoặc phần header cần bảo vệ nhưng không muốn mã hóa. AAD được **xác thực, không được mã hóa**. Nếu một trường metadata nhạy cảm cần được giữ bí mật, không đặt nó ở AAD công khai như thể AAD là ciphertext.

Để decrypt thành công, hai phía phải đưa vào **đúng cùng một dãy byte AAD theo đúng thứ tự**. Một thay đổi ở AAD hoặc ciphertext/tag làm tag không khớp. `Cipher.doFinal(...)` ở chế độ decrypt sẽ ném `AEADBadTagException` khi kiểm tra thất bại. Không dùng plaintext của lần decrypt đó để parse, ghi file chính thức hoặc cập nhật nghiệp vụ.

### 4.1 Counter trong AEAD không do ứng dụng tự đặt

RFC 8439 dành ChaCha20 block counter **0** để tạo one-time Poly1305 key. Mã hóa nội dung dùng block counter **1** và tiếp tục tăng theo kích thước message. Những bước này thuộc **định nghĩa ChaCha20-Poly1305**, không phải parameter mà caller được phép tùy ý truyền.

Do đó Java 11 yêu cầu:

```java
Cipher aead = Cipher.getInstance("ChaCha20-Poly1305");
aead.init(Cipher.ENCRYPT_MODE, secretKey,
        new IvParameterSpec(nonce12));
aead.updateAAD(metadata);
byte[] ciphertextAndTag = aead.doFinal(plaintext);
```

Đây là trích đoạn; cần import `Cipher` và `IvParameterSpec`, đồng thời khai báo key 256-bit, nonce 12 byte, metadata/byte array. **Không** dùng `ChaCha20ParameterSpec` cho AEAD. Nếu cố truyền kiểu đó, SunJCE báo `InvalidAlgorithmParameterException`.

Chế độ AEAD có tag **128 bit cố định** theo construction này. Không tự cắt tag còn 8 byte để tiết kiệm bandwidth, cũng không coi 16 byte tag là nơi chứa nonce. Tag và nonce là hai phần khác nhau của wire format.

### 4.2 AAD phải được đưa vào trước payload

`Cipher.updateAAD(...)` phải hoàn thành trước khi bắt đầu `update(...)` hoặc `doFinal(...)` với dữ liệu cần mã hóa/giải mã:

```java
Cipher encrypt = Cipher.getInstance("ChaCha20-Poly1305");
encrypt.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
encrypt.updateAAD(versionAndType);
encrypt.updateAAD(verifiedTenantContext);
byte[] output = encrypt.doFinal(plaintext);
```

Hai lời gọi `updateAAD` trên đây nối bytes của AAD theo đúng thứ tự. Phía decrypt phải dùng cùng thứ tự và đúng encoding. Đừng ghép metadata bằng chuỗi tùy ý giữa nhiều bên không thống nhất charset, dấu phân cách, length prefix, hay cách chuẩn hóa Unicode; khác **một byte** cũng có thể làm thất bại xác thực.

## 5. Các API Java 11 cần biết

| Vai trò | Cách gọi |
|---|---|
| Tạo key 256-bit | `KeyGenerator.getInstance("ChaCha20")`, `init(256)`, `generateKey()` |
| Nhập key raw đã được quản lý an toàn | `new SecretKeySpec(keyBytes, "ChaCha20")` |
| Chọn stream cipher | `Cipher.getInstance("ChaCha20")` |
| Chọn AEAD | `Cipher.getInstance("ChaCha20-Poly1305")` |
| Raw parameter | `new ChaCha20ParameterSpec(nonce12, counter)` |
| AEAD parameter | `new IvParameterSpec(nonce12)` |
| Chọn encrypt | `cipher.init(Cipher.ENCRYPT_MODE, key, params)` |
| Chọn decrypt | `cipher.init(Cipher.DECRYPT_MODE, key, params)` |
| Xác thực metadata | `cipher.updateAAD(aad)` — chỉ AEAD |
| Hoàn tất mã hóa/giải mã | `cipher.doFinal(data)` |
| Sai xác thực AEAD | `AEADBadTagException` |
| Nonce ngẫu nhiên | `SecureRandom.nextBytes(nonce12)` |

**Cấu hình giống nhau:** cả hai dùng key ChaCha20 256 bit, nonce IETF 12 byte.  
**Cấu hình khác nhau:** raw nhận `ChaCha20ParameterSpec` + counter, AEAD nhận `IvParameterSpec`; raw không có tag/AAD, AEAD có.

Các transformation này có trong JDK 11 từ **JEP 329** với SunJCE; một runtime/provider khác có thể không triển khai đầy đủ hoặc dùng loại lỗi provider-specific. Khi triển khai, chọn provider được hỗ trợ theo policy, dùng `getInstance(...)` và kiểm chứng bằng test vectors, không tự đoán từ tên hệ điều hành.

## 6. Ví dụ Java 11 số 1 — raw không phát hiện tamper, AEAD có

Demo đầu tiên sinh key với `KeyGenerator` và **hai nonce độc lập** từ `SecureRandom`: một cho raw, một cho AEAD. Nó mã hóa cùng một plaintext tiếng Việt; thử round-trip và cố tình flip một byte ciphertext. Ở raw, kết quả decrypt bị đổi mà không có authentication exception. Ở AEAD, việc thay ciphertext hoặc AAD bị từ chối.

Lưu thành **`ChaChaModesDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.IvParameterSpec;

public class ChaChaModesDemo {
    static byte[] nonce() {
        byte[] bytes = new byte[12];
        new SecureRandom().nextBytes(bytes);
        return bytes;
    }

    static byte[] raw(int operation, SecretKey key,
                      byte[] nonce, byte[] message) throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20");
        cipher.init(operation, key, new ChaCha20ParameterSpec(nonce, 1));
        return cipher.doFinal(message);
    }

    static byte[] aead(int operation, SecretKey key, byte[] nonce,
                       byte[] aad, byte[] data) throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(operation, key, new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(data);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256);
        SecretKey key = generator.generateKey();

        byte[] plaintext = "Xin chào ChaCha20!".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "record-type=v1".getBytes(StandardCharsets.UTF_8);
        byte[] rawNonce = nonce();
        byte[] aeadNonce = nonce();

        byte[] rawCiphertext = raw(Cipher.ENCRYPT_MODE, key,
                rawNonce, plaintext);
        byte[] rawRoundTrip = raw(Cipher.DECRYPT_MODE, key,
                rawNonce, rawCiphertext);

        System.out.println("key-bytes=" + key.getEncoded().length);
        System.out.println("nonce-bytes=" + aeadNonce.length);
        System.out.println("raw-same-length="
                + (rawCiphertext.length == plaintext.length));
        System.out.println("raw-roundtrip="
                + Arrays.equals(rawRoundTrip, plaintext));

        byte[] modified = rawCiphertext.clone();
        modified[0] ^= 1;
        byte[] unchecked = raw(Cipher.DECRYPT_MODE, key, rawNonce, modified);
        System.out.println("raw-tampering-goes-undetected="
                + !Arrays.equals(unchecked, plaintext));

        byte[] sealed = aead(Cipher.ENCRYPT_MODE, key, aeadNonce,
                aad, plaintext);
        byte[] opened = aead(Cipher.DECRYPT_MODE, key, aeadNonce,
                aad, sealed);
        System.out.println("aead-extra-tag-bytes="
                + (sealed.length - plaintext.length));
        System.out.println("aead-roundtrip="
                + Arrays.equals(opened, plaintext));

        byte[] modifiedAead = sealed.clone();
        modifiedAead[0] ^= 1;
        try {
            aead(Cipher.DECRYPT_MODE, key, aeadNonce, aad, modifiedAead);
            throw new AssertionError("Tampered AEAD accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("aead-tampering-rejected=true");
        }

        byte[] wrongAad = "record-type=v2".getBytes(StandardCharsets.UTF_8);
        try {
            aead(Cipher.DECRYPT_MODE, key, aeadNonce, wrongAad, sealed);
            throw new AssertionError("Wrong AAD accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("wrong-aad-rejected=true");
        }
    }
}
```

Chạy:

```bash
javac --release 11 -encoding UTF-8 ChaChaModesDemo.java
java ChaChaModesDemo
```

**Stdout đã kiểm chứng (key và nonce thay đổi qua mỗi lần chạy nhưng các kết luận vẫn ổn định):**

```text
key-bytes=32
nonce-bytes=12
raw-same-length=true
raw-roundtrip=true
raw-tampering-goes-undetected=true
aead-extra-tag-bytes=16
aead-roundtrip=true
aead-tampering-rejected=true
wrong-aad-rejected=true
```

**Đọc kết quả:**

1. `key-bytes=32` và `nonce-bytes=12` xác nhận tham số đúng kích thước.
2. `raw-same-length=true`: stream cipher không thêm authentication tag.
3. `raw-roundtrip=true` chứng minh biến thể raw mã hóa/giải mã đối xứng với cùng key/nonce/counter, **không** chứng minh chống sửa dữ liệu.
4. `raw-tampering-goes-undetected=true`: sửa bit ciphertext rồi decrypt làm thay đổi plaintext, nhưng raw Cipher **không** báo thiếu integrity.
5. `aead-extra-tag-bytes=16`: AEAD thêm tag 16 byte.
6. `aead-roundtrip=true`: đúng key/nonce/AAD/tag sẽ cho lại plaintext.
7. `aead-tampering-rejected=true`: ciphertext bị chỉnh sửa khiến xác thực thất bại.
8. `wrong-aad-rejected=true`: AAD khác với lúc encrypt cũng khiến xác thực thất bại; đây là cơ chế bảo vệ header và metadata.

**Lưu ý:** Demo chỉ in độ dài và kết quả boolean, không in raw key hay private material. Các phương thức tạo `Cipher` mới cho mỗi phép encrypt/decrypt, không share mutable `Cipher` giữa nhiều thread.

## 7. Ví dụ Java 11 số 2 — vector chính thức RFC 8439

Round-trip test không đủ để chứng minh implementation đúng chuẩn: hai thao tác encrypt/decrypt cùng sai định dạng vẫn có thể đảo được cho nhau. Vì vậy cần **known-answer test** với key, nonce, AAD và ciphertext/tag đã được RFC công bố.

### 7.1 Raw ChaCha20, RFC 8439 mục 2.4.2

- Key 32 byte: `00 01 02 ... 1f`.
- Nonce 12 byte: `000000000000004a00000000`.
- Initial counter: `1`.
- Plaintext ASCII dài 114 byte bắt đầu bằng `Ladies and Gentlemen...`.
- Ciphertext đúng bằng expected hex từ RFC 8439.

### 7.2 AEAD ChaCha20-Poly1305, RFC 8439 mục 2.8.2

- Key 32 byte: `80 81 82 ... 9f`.
- Nonce: `070000004041424344454647`.
- AAD: `50515253c0c1c2c3c4c5c6c7`.
- Plaintext tương tự, dài 114 byte.
- Expected output gồm ciphertext 114 byte nối tag `1ae10b594f09e26a7e902ecbd0600691` (16 byte).

Bộ dữ liệu này **công khai** vì là test vector; **không bao giờ dùng key và nonce hardcoded từ vector để mã hóa nội dung thật**.

Lưu file **`Rfc8439ChaChaVectorsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class Rfc8439ChaChaVectorsDemo {
    static byte[] hex(String value) {
        String s = value.replaceAll("\\s+", "");
        if ((s.length() & 1) != 0) throw new IllegalArgumentException("Odd hex");
        byte[] data = new byte[s.length() / 2];
        for (int i = 0; i < data.length; i++) {
            data[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        }
        return data;
    }

    static void checkRaw(byte[] plaintext) throws Exception {
        byte[] key = hex(
                "000102030405060708090a0b0c0d0e0f"
              + "101112131415161718191a1b1c1d1e1f");
        byte[] nonce = hex("000000000000004a00000000");
        byte[] expected = hex(
                "6e2e359a2568f98041ba0728dd0d6981"
              + "e97e7aec1d4360c20a27afccfd9fae0b"
              + "f91b65c5524733ab8f593dabcd62b357"
              + "1639d624e65152ab8f530c359f0861d8"
              + "07ca0dbf500d6a6156a38e088a22b65e"
              + "52bc514d16ccf806818ce91ab7793736"
              + "5af90bbf74a35be6b40b8eedf2785e42"
              + "874d");

        SecretKeySpec secret = new SecretKeySpec(key, "ChaCha20");
        Cipher cipher = Cipher.getInstance("ChaCha20");
        cipher.init(Cipher.ENCRYPT_MODE, secret,
                new ChaCha20ParameterSpec(nonce, 1));
        byte[] actual = cipher.doFinal(plaintext);
        boolean matches = Arrays.equals(expected, actual);
        System.out.println("rfc8439-raw-vector=" + matches);
        if (!matches) throw new AssertionError("RFC 8439 section 2.4.2 mismatch");
    }

    static void checkAead(byte[] plaintext) throws Exception {
        byte[] key = hex(
                "808182838485868788898a8b8c8d8e8f"
              + "909192939495969798999a9b9c9d9e9f");
        byte[] nonce = hex("070000004041424344454647");
        byte[] aad = hex("50515253c0c1c2c3c4c5c6c7");
        byte[] expectedCiphertext = hex(
                "d31a8d34648e60db7b86afbc53ef7ec2"
              + "a4aded51296e08fea9e2b5a736ee62d6"
              + "3dbea45e8ca9671282fafb69da92728b"
              + "1a71de0a9e060b2905d6a5b67ecd3b36"
              + "92ddbd7f2d778b8c9803aee328091b58"
              + "fab324e4fad675945585808b4831d7bc"
              + "3ff4def08e4b7a9de576d26586cec64b"
              + "6116");
        byte[] expectedTag = hex("1ae10b594f09e26a7e902ecbd0600691");
        byte[] expected = new byte[expectedCiphertext.length + expectedTag.length];
        System.arraycopy(expectedCiphertext, 0, expected, 0,
                expectedCiphertext.length);
        System.arraycopy(expectedTag, 0, expected,
                expectedCiphertext.length, expectedTag.length);

        SecretKeySpec secret = new SecretKeySpec(key, "ChaCha20");
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.ENCRYPT_MODE, secret, new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        byte[] actual = cipher.doFinal(plaintext);
        boolean matches = Arrays.equals(expected, actual);
        System.out.println("rfc8439-aead-vector=" + matches);
        System.out.println("rfc8439-aead-tag-at-end="
                + Arrays.equals(expectedTag,
                        Arrays.copyOfRange(actual, plaintext.length,
                                actual.length)));
        if (!matches) throw new AssertionError("RFC 8439 section 2.8.2 mismatch");

        Cipher decrypt = Cipher.getInstance("ChaCha20-Poly1305");
        decrypt.init(Cipher.DECRYPT_MODE, secret, new IvParameterSpec(nonce));
        decrypt.updateAAD(aad);
        byte[] opened = decrypt.doFinal(actual);
        System.out.println("rfc8439-aead-decryption="
                + Arrays.equals(plaintext, opened));
    }

    public static void main(String[] args) throws Exception {
        byte[] plaintext = (
                "Ladies and Gentlemen of the class of '99: "
                + "If I could offer you only one tip for the future, "
                + "sunscreen would be it.").getBytes(StandardCharsets.US_ASCII);
        System.out.println("plaintext-bytes=" + plaintext.length);
        checkRaw(plaintext);
        checkAead(plaintext);
    }
}
```

```bash
javac --release 11 -encoding UTF-8 Rfc8439ChaChaVectorsDemo.java
java Rfc8439ChaChaVectorsDemo
```

```text
plaintext-bytes=114
rfc8439-raw-vector=true
rfc8439-aead-vector=true
rfc8439-aead-tag-at-end=true
rfc8439-aead-decryption=true
```

Phân tích: `rfc8439-raw-vector=true` chứng minh raw ChaCha20 với counter 1 cho đúng ciphertext RFC. `rfc8439-aead-vector=true` kiểm tra **toàn bộ** ciphertext+tag, không chỉ độ dài. `rfc8439-aead-tag-at-end=true` chứng minh tag được nối **cuối output**. `rfc8439-aead-decryption=true` kiểm tra decrypt cùng AAD đúng được plaintext gốc. Khi tương tác giữa Java/Go/Rust/OpenSSL, những vector này giúp phát hiện lỗi nonce/counter/endianness/tag layout.

**Phiên bản tài liệu:** RFC 8439 thay thế RFC 7539 và hợp nhất các errata; dùng RFC 8439 làm tham chiếu đang áp dụng. JEP 329 của Java 11 có thể nêu RFC 7539 vì bối cảnh thời điểm bổ sung tính năng, nhưng cách thực hành hiện tại nên kiểm thử với RFC 8439.

## 8. Ví dụ Java 11 số 3 — AEAD envelope có version, nonce, tag

Receiver thường nhận một `byte[]` từ file hoặc mạng, không có nonce trong API parameter riêng. Cần một định dạng truyền có cấu trúc và **phải bind header vào AAD** khi header có ý nghĩa bảo mật.

Ví dụ minh họa format:

```text
offset      0          1               13                  N
            | version | nonce 12 byte | ciphertext n byte | tag 16 byte |
```

Tổng kích thước: `plaintext.length + 1 + 12 + 16 = n + 29` byte. Format này đủ cho bài tập **một record**, chưa phải protocol production có key ID, sequence number, quota, negotiation và replay tracking.

Chương trình:

- Seal với nonce **mới** từ `SecureRandom` cho từng message.
- Dùng version 1 và đưa byte version vào `updateAAD` để bảo vệ chính header này; thêm AAD metadata `tenant=42;record=v1`.
- Giữ nguyên 16-byte tag ở cuối ciphertext.
- Open kiểm tra độ dài tối thiểu, version, tách đúng nonce và ciphertext+tag, dùng cùng AAD.
- Từ chối message sai tag, đổi nonce, đổi AAD, đổi version hoặc bị cắt ngắn.

Lưu file **`ChaChaEnvelopeDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public class ChaChaEnvelopeDemo {
    private static final byte VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BYTES = 16;
    private static final SecureRandom RANDOM = new SecureRandom();

    public static byte[] seal(SecretKey key, byte[] aad,
                              byte[] plaintext) throws Exception {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
        cipher.updateAAD(new byte[]{VERSION});
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        byte[] envelope = new byte[1 + NONCE_BYTES
                + ciphertextAndTag.length];
        envelope[0] = VERSION;
        System.arraycopy(nonce, 0, envelope, 1, NONCE_BYTES);
        System.arraycopy(ciphertextAndTag, 0, envelope,
                1 + NONCE_BYTES, ciphertextAndTag.length);
        return envelope;
    }

    public static byte[] open(SecretKey key, byte[] aad, byte[] envelope)
            throws Exception {
        if (envelope.length < 1 + NONCE_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Truncated envelope");
        }
        if (envelope[0] != VERSION) {
            throw new IllegalArgumentException("Unsupported envelope version");
        }
        byte[] nonce = Arrays.copyOfRange(
                envelope, 1, 1 + NONCE_BYTES);
        byte[] ciphertextAndTag = Arrays.copyOfRange(
                envelope, 1 + NONCE_BYTES, envelope.length);

        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(nonce));
        cipher.updateAAD(new byte[]{VERSION});
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256);
        SecretKey key = generator.generateKey();
        byte[] aad = "tenant=42;record=v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] message = "Bản ghi bí mật".getBytes(StandardCharsets.UTF_8);

        byte[] envelope = seal(key, aad, message);
        byte[] recovered = open(key, aad, envelope);
        System.out.println("version=" + envelope[0]);
        System.out.println("header-bytes=" + (1 + NONCE_BYTES));
        System.out.println("tag-bytes=" + TAG_BYTES);
        System.out.println("envelope-overhead="
                + (envelope.length - message.length));
        System.out.println("roundtrip="
                + Arrays.equals(message, recovered));

        byte[] badTag = envelope.clone();
        badTag[badTag.length - 1] ^= 1;
        try {
            open(key, aad, badTag);
            throw new AssertionError("Bad tag unexpectedly accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("bad-tag-rejected=true");
        }

        byte[] badNonce = envelope.clone();
        badNonce[1] ^= 1;
        try {
            open(key, aad, badNonce);
            throw new AssertionError("Bad nonce unexpectedly accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("changed-nonce-rejected=true");
        }

        try {
            open(key, "tenant=43;record=v1"
                    .getBytes(StandardCharsets.UTF_8), envelope);
            throw new AssertionError("Bad AAD unexpectedly accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("changed-aad-rejected=true");
        }

        byte[] badVersion = envelope.clone();
        badVersion[0] = 2;
        try {
            open(key, aad, badVersion);
            throw new AssertionError("Unsupported version accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("bad-version-rejected=true");
        }

        try {
            open(key, aad, Arrays.copyOf(envelope, 10));
            throw new AssertionError("Truncation accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("truncated-rejected=true");
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 ChaChaEnvelopeDemo.java
java ChaChaEnvelopeDemo
```

```text
version=1
header-bytes=13
tag-bytes=16
envelope-overhead=29
roundtrip=true
bad-tag-rejected=true
changed-nonce-rejected=true
changed-aad-rejected=true
bad-version-rejected=true
truncated-rejected=true
```

**Ý nghĩa và ranh giới của ví dụ:**

1. `header-bytes=13` = version 1 byte và nonce 12 byte; nonce là thông tin public, **không phải khóa**.
2. `envelope-overhead=29` = 1 + 12 + 16 byte; tag 16 byte ở cuối.
3. `roundtrip=true` là phép giải mã xác thực đúng.
4. `bad-tag-rejected=true` và `changed-nonce-rejected=true` xác nhận tag buộc ciphertext vào đúng nonce.
5. `changed-aad-rejected=true` cho thấy tag cũng gắn vào metadata đã cung cấp.
6. `bad-version-rejected=true` cho thấy protocol không diễn giải mù một version lạ hoặc âm thầm downgrade.
7. `truncated-rejected=true`: parse tối thiểu được kiểm tra trước khi gửi dữ liệu cho Cipher.
8. Ở hệ thống thật, giới hạn độ dài lớn nhất trước khi cấp phát; nếu decode từ external input, tránh trust metadata do client tự khai để quyết định quyền tenant. **AAD được authenticated dưới key nhưng quyền truy cập vẫn phải do application kiểm tra.**

Envelope demo **không tự chống replay**. Một attacker phát lại nguyên version/nonce/ciphertext/tag vẫn có thể qua kiểm tra mật mã nếu key và AAD đúng; protocol phải có sequence number, timestamp/window hoặc message ID và lưu trạng thái đã xử lý nếu replay gây hại.

## 9. Ví dụ Java 11 số 4 — kiểm tra sai parameter spec

Dù nonce và key có cùng kích thước, raw mode và AEAD nhận **loại parameter khác nhau**. Ví dụ này kiểm chứng bằng các trường hợp âm tính; key là dãy byte test công khai, không phải secret production. Raw và AEAD được cấp **hai nonce khác nhau** để tránh lặp cùng key+nonce giữa hai mode.

Lưu file **`ChaChaParameterRulesDemo.java`**:

```java
import java.security.InvalidAlgorithmParameterException;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class ChaChaParameterRulesDemo {
    public static void main(String[] args) throws Exception {
        byte[] bytes = new byte[32];
        for (int i = 0; i < bytes.length; i++) {
            bytes[i] = (byte) (i + 1);
        }
        SecretKeySpec key = new SecretKeySpec(bytes, "ChaCha20");
        byte[] nonce = new byte[12];
        byte[] differentNonce = new byte[12];
        for (int i = 0; i < nonce.length; i++) {
            nonce[i] = (byte) (10 + i);
            differentNonce[i] = (byte) (30 + i);
        }

        try {
            new ChaCha20ParameterSpec(new byte[11], 1);
            throw new AssertionError("Invalid raw nonce length was accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("raw-nonce-11-rejected=true");
        }

        try {
            Cipher.getInstance("ChaCha20").init(
                    Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
            throw new AssertionError("Wrong raw parameters accepted");
        } catch (InvalidAlgorithmParameterException expected) {
            System.out.println("raw-ivspec-rejected=true");
        }

        try {
            Cipher.getInstance("ChaCha20-Poly1305").init(
                    Cipher.ENCRYPT_MODE, key,
                    new ChaCha20ParameterSpec(differentNonce, 1));
            throw new AssertionError("Wrong AEAD parameters accepted");
        } catch (InvalidAlgorithmParameterException expected) {
            System.out.println("aead-counter-spec-rejected=true");
        }

        try {
            Cipher.getInstance("ChaCha20-Poly1305").init(
                    Cipher.ENCRYPT_MODE, key, new IvParameterSpec(new byte[8]));
            throw new AssertionError("Short AEAD nonce accepted");
        } catch (InvalidAlgorithmParameterException expected) {
            System.out.println("aead-nonce-8-rejected=true");
        }

        Cipher raw = Cipher.getInstance("ChaCha20");
        raw.init(Cipher.ENCRYPT_MODE, key, new ChaCha20ParameterSpec(nonce, 1));
        try {
            raw.updateAAD(new byte[]{1});
            throw new AssertionError("Raw ChaCha20 accepted AAD");
        } catch (IllegalStateException expected) {
            System.out.println("raw-aad-not-supported=true");
        }

        byte[] message = new byte[100];
        Arrays.fill(message, (byte) 42);
        byte[] ciphertext = raw.doFinal(message);
        System.out.println("raw-length-unchanged="
                + (ciphertext.length == message.length));

        Cipher aead = Cipher.getInstance("ChaCha20-Poly1305");
        aead.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(differentNonce));
        aead.updateAAD(new byte[]{1});
        byte[] sealed = aead.doFinal(message);
        System.out.println("aead-length-plus-16="
                + (sealed.length == message.length + 16));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 ChaChaParameterRulesDemo.java
java ChaChaParameterRulesDemo
```

```text
raw-nonce-11-rejected=true
raw-ivspec-rejected=true
aead-counter-spec-rejected=true
aead-nonce-8-rejected=true
raw-aad-not-supported=true
raw-length-unchanged=true
aead-length-plus-16=true
```

- `raw-nonce-11-rejected`: `ChaCha20ParameterSpec` yêu cầu nonce đúng 12 byte.
- `raw-ivspec-rejected`: raw mode không dùng `IvParameterSpec`.
- `aead-counter-spec-rejected`: AEAD không dùng `ChaCha20ParameterSpec`.
- `aead-nonce-8-rejected`: AEAD IETF này yêu cầu 12-byte nonce.
- `raw-aad-not-supported`: ChaCha20 thuần không có AAD.
- `raw-length-unchanged`, `aead-length-plus-16`: khác biệt format.
- Test tạo **Cipher mới** cho từng lần khởi tạo sai, tránh trạng thái Cipher sau lỗi init làm ảnh hưởng kết quả về sau.

**Đừng tự động fallback sang raw** nếu AEAD ném lỗi tham số hoặc sai tag. Đây là lỗi cấu hình/giao thức cần sửa chứ không phải dấu hiệu “server muốn mã hóa yếu hơn”.

## 10. Quản lý nonce đúng cách

**Yêu cầu quan trọng nhất khi encrypt:** không được tái sử dụng **cùng cặp (key, nonce)** cho hai lần mã hóa. Điều này đúng với cả ChaCha20 thuần và AEAD.

### 10.1 Hậu quả trên raw ChaCha20

Nếu hai plaintext dùng cùng key/nonce và cùng dải counter, keystream `S` lặp lại:

```text
C1 = P1 XOR S
C2 = P2 XOR S
C1 XOR C2 = P1 XOR P2
```

Attacker có thể khai thác quan hệ giữa hai bản rõ, nhất là khi có nội dung đoán được. “Tăng counter từ 1 lên 2” không phải giải pháp nonce chung: message dài nhiều block có thể làm các dải counter chồng nhau, và mọi sender phải nhất quán về dải đã sử dụng.

### 10.2 Hậu quả trên ChaCha20-Poly1305

Với AEAD, reuse key+nonce còn lặp **one-time Poly1305 key**, đe dọa cả confidentiality và integrity. Không được coi việc thay AAD hoặc version là cách để tái sử dụng nonce an toàn. Key khác có thể có namespace nonce riêng, nhưng cùng một key còn tồn tại thì nonce phải không trùng.

Một số lựa chọn phù hợp tùy hệ thống:

| Cách cấp nonce | Khi nào hữu ích | Điều cần bảo vệ |
|---|---|---|
| `SecureRandom` sinh 12 byte | Số encryption mỗi key được giới hạn và chấp nhận xác suất collision rất nhỏ | Nguy cơ collision tích lũy theo birthday bound; rotation và quota |
| Counter 96 bit duy nhất theo key | Protocol có state bền vững và đủ chặt | Không reset/rollback khi crash, backup restore hoặc restart |
| Prefix được cấp độc quyền cho node + counter | Nhiều worker/instance cùng key theo protocol đã thiết kế | Prefix không trùng, counter tăng atomic, xử lý node ID/snapshot |
| Nonce do service trung tâm cấp phát | Muốn một đơn vị kiểm soát uniqueness | Độ bền, cấp phát trùng hoặc timeout, idempotency, phân quyền |

`SecureRandom` là lựa chọn thích hợp cho các demo ở đây và ứng dụng với ngân sách message/key được kiểm soát, nhưng **không bảo đảm tuyệt đối không bao giờ trùng**. Với hàng tỷ bản ghi hoặc nhiều instance cùng key, cần ước lượng rủi ro collision và có thể ưu tiên bộ đếm được quản lý đúng, phân chia không gian nonce, key rotation.

**Không dùng `new Random()`, thời gian hệ thống độ phân giải thấp, ID tiến trình hoặc UUID bị cắt tùy tiện** làm phương án uniqueness không kiểm chứng. Hệ thống multi-thread phải phân phối nonce an toàn ở đúng phạm vi key; nhiều instance sinh riêng counter bắt đầu 0 với cùng key là một lỗi nguy hiểm.

### 10.3 Counter 32 bit và giới hạn mỗi message

IETF ChaCha20 có 64-byte block và 32-bit block counter; AEAD dùng block 0 tạo Poly1305 key và mã hóa từ counter 1. Vì vậy một nonce không thể mã hóa dữ liệu dài vô hạn mà không gặp tràn counter. Với file lớn hoặc stream dài, thiết kế record có giới hạn byte, **mỗi record nonce mới**, gắn sequence number và length vào AAD.

Không truyền hàng GB dữ liệu trong một lệnh `doFinal` nếu không phù hợp bộ nhớ/quota. Dùng record AEAD độc lập hoặc thư viện streaming AEAD đã được đánh giá để có framing, nonce, tag và error handling đúng.

## 11. Tag validation và xử lý streaming

### 11.1 Không đưa plaintext chưa xác thực vào nghiệp vụ

Khi decrypt AEAD theo các chunk bằng `update(...)` rồi `doFinal(...)`, một số provider có thể đẩy ra plaintext tạm **trước khi tag được xác minh**. Không được truyền plaintext đó tới database, gửi cho người dùng, giải nén không kiểm soát, parse có side effect hoặc ghi file công khai cho tới khi `doFinal` xác nhận tag thành công.

Một luồng xử lý an toàn:

```text
Nhận message frame có giới hạn kích thước
          |
Parse version, nonce, ciphertext+tag
          |
Lấy key theo policy đã xác minh
          |
Tạo AAD đúng bytes, đúng thứ tự
          |
Cipher.init(DECRYPT_MODE)
          |
Cipher.updateAAD(...)
          |
Cipher.doFinal(...) và xác thực tag
          |
Kiểm tra schema, authorization, replay
          |
Chỉ lúc này mới commit dữ liệu
```

Nếu payload lớn, ứng dụng có thể ghi vào vùng **tạm cô lập**, không được dùng như file đã xác thực, sau đó xóa khi tag sai hoặc chỉ atomically move/commit khi xác thực và validation thành công (nếu filesystem hỗ trợ). Với record nhỏ, giữ plaintext tới khi xác minh tag là đơn giản hơn.

### 11.2 Sai tag có nghĩa gì?

`AEADBadTagException` có thể xuất hiện khi:

- Ciphertext hoặc tag bị sửa/mất byte.
- Nonce nhận sai, key sai hoặc key rotation không khớp.
- AAD khác bytes/thứ tự/charset/metadata.
- Message bị cắt cụt hoặc frame/format parser sai.
- Giao thức không thống nhất cách phân tách AAD, ciphertext và tag.

Không khẳng định mọi bad tag đều do attacker: lỗi cấu hình hoặc serialize cũng gây tương tự. Tuy nhiên **đừng giải mã lại bằng raw ChaCha20 để lấy “tạm dữ liệu”**; phải từ chối message, ghi nhận lỗi ở mức phù hợp và giữ kín key. Tránh công khai khác biệt quá chi tiết giữa các lỗi cho request từ nguồn không tin cậy.

### 11.3 AAD là authenticated, không phải authorized

Giả sử AAD chứa `tenant=42` nhưng caller chưa xác thực danh tính và cứ chọn key theo tenant do client cung cấp. Việc tag hợp lệ dưới một key không tự chứng minh caller có quyền vào tenant đó. Cần chính sách xác thực client, key isolation, quyền giải mã và context từ server được xác nhận. Bind metadata vào AAD **bảo vệ không bị thay đổi**, còn **authorization** là một bước riêng.

## 12. Khác biệt về replay và thứ tự bản ghi

AEAD xác thực một message nhưng **không chống replay tự động**. Một attacker có thể phát lại nguyên envelope cũ với đúng tag. Giải mã vẫn có thể thành công nếu server dùng cùng key/nonce/AAD. Nếu replay gây tác động nghiệp vụ (thanh toán, thay đổi quyền, yêu cầu ghi dữ liệu), protocol phải kiểm tra sequence number, nonce đã thấy, message ID hoặc replay window.

Để kiểm soát thứ tự, đưa sequence number vào AAD theo encoding đã thống nhất và kiểm tra state trên server. Không chỉ so sánh timestamp khi máy khách có thể tùy ý chỉnh đồng hồ, hoặc giả định TCP luôn bảo vệ thứ tự của message nếu bạn có nhiều kết nối, queue/retry hoặc xử lý phân tán.

Nếu cần chống cross-protocol misuse, phân tách key theo purpose/role/direction (client→server, server→client), record type và version trong key schedule. AAD là một lớp bind thêm, không thay thế nguyên tắc dùng key đúng mục đích.

## 13. Khi nào chọn ChaCha20-Poly1305 hay AES-GCM?

`AES/GCM/NoPadding` và `ChaCha20-Poly1305` đều là lựa chọn AEAD phổ biến; cả hai cần thiết kế nonce/key đúng. Không có khẳng định tốc độ nào đúng trên mọi CPU: AES có thể được tăng tốc bằng phần cứng, ChaCha20 có ưu điểm trong một số môi trường phần mềm, nhưng phải đo trên workload/provider thực.

| Tiêu chí | Điều cần xác minh |
|---|---|
| Hợp đồng wire protocol | Hai phía có hỗ trợ cùng algorithm/tag/AAD/nonce format không? |
| Provider/JDK | SunJCE/nhà cung cấp khác có triển khai transformation và qua RFC KAT không? |
| Hardware & performance | Latency/throughput thực với kích thước message cần xử lý |
| Policy & tuân thủ | Môi trường FIPS hoặc quy định nội bộ có phê duyệt mode không? |
| Nonce uniqueness | Có cơ chế không trùng xuyên thread, process, restart, backup không? |
| Key distribution | Key có được phân phối qua kênh xác thực, phân quyền và rotation chưa? |
| Output format | Giữ nguyên tag, versioning, nonce và sequence đúng chuẩn chưa? |
| Error handling | Xử lý bad tag, input lớn, malformed record, timeout/replay an toàn chưa? |

Bản thân việc Java 11 có `Cipher.getInstance("ChaCha20-Poly1305")` **không** có nghĩa mọi `HttpClient` request qua HTTPS sẽ dùng TLS cipher suite ChaCha20-Poly1305. **JCE application encryption** khác với **JSSE TLS handshake/cipher suite negotiation**. Với dữ liệu truyền qua mạng, dùng TLS stack tiêu chuẩn, không viết lại TLS bằng một envelope tùy ý.

## 14. Ma trận kiểm thử đầy đủ

| Kiểm thử | Thiết lập | Kết quả mong đợi |
|---|---|---|
| Raw round-trip | Đúng key/nonce/counter | Plaintext khớp |
| Raw output length | `n` byte input | `n` byte output |
| Raw ciphertext bitflip | Đổi một bit bản mã | Plaintext bị sửa, không có authentication exception |
| AEAD round-trip | Đúng key, nonce, AAD | Plaintext khớp |
| AEAD output length | `n` byte input | `n+16` byte |
| AEAD ciphertext bitflip | Đổi một byte ciphertext | `AEADBadTagException` |
| AEAD tag bitflip | Đổi byte cuối tag | `AEADBadTagException` |
| AEAD wrong nonce | Đổi nonce trong envelope | Decrypt thất bại |
| AEAD wrong AAD | Đổi context bytes | Decrypt thất bại |
| AEAD wrong key | Dùng key 256 bit khác | Decrypt thất bại |
| Raw nonce không đủ | `ChaCha20ParameterSpec(new byte[11],...)` | `IllegalArgumentException` |
| Raw wrong spec | `IvParameterSpec` đưa cho ChaCha20 | Bị từ chối |
| AEAD wrong spec | `ChaCha20ParameterSpec` đưa cho AEAD | Bị từ chối |
| AEAD nonce 8 byte | `IvParameterSpec(new byte[8])` | Bị từ chối |
| Raw AAD | Gọi `updateAAD` trên raw | Không được hỗ trợ |
| RFC 8439 raw `2.4.2` | Known-answer vector | Byte ciphertext đúng |
| RFC 8439 AEAD `2.8.2` | Known-answer vector | Ciphertext và tag đúng |
| Format truncated | Bỏ nonce/tag hoặc message quá ngắn | Từ chối, không commit plaintext |
| Version lạ | Header không được hỗ trợ | Từ chối, không downgrade |
| Key/nonce reuse | Hai encryption dưới cùng key+nonce | Test property/policy phải phát hiện/không cấp phép |
| Multi-thread | Concurrent encryption | Nonce manager không cấp trùng; không share Cipher |
| Restart recovery | Khôi phục snapshot cũ | Không reset nonce counter với key cũ |
| Replay | Gửi lại envelope hợp lệ | Protocol application từ chối trùng |
| Dữ liệu cực lớn | Input vượt quota | Từ chối sớm, không OOM |
| Streaming decryption | Cipher có thể tạo byte trước khi verify tag | Không phát hành plaintext cho đến `doFinal` thành công |

**Không chỉ test encrypt-decrypt.** Hai phép toán cùng sai cách nối tag hoặc cùng sai counter vẫn có thể tự round-trip nhưng không tương thích protocol khác. RFC known-answer vectors cung cấp oracle độc lập để kiểm tra chính xác bytes.

## 15. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao nguy hiểm/sai | Hướng đúng |
|---|---|---|
| Dùng raw ChaCha20 như authenticated message encryption | Không phát hiện ciphertext bị sửa | Dùng ChaCha20-Poly1305 hoặc AEAD chuẩn |
| Dùng `IvParameterSpec` với raw | Thiếu counter và sai type | Dùng `ChaCha20ParameterSpec` |
| Dùng `ChaCha20ParameterSpec` với AEAD | AEAD không nhận counter caller | Dùng `IvParameterSpec` |
| Tự đặt counter cho AEAD | Trái construction RFC | Để provider quản lý |
| Gọi `updateAAD` trên raw | Stream không có AAD | Chọn AEAD nếu cần xác thực metadata |
| AAD đưa vào sau khi bắt đầu dữ liệu | Sai thứ tự state | Cung cấp toàn bộ AAD trước payload |
| Bỏ tag khi serialize | Decrypt không thể xác thực | Giữ đủ 16-byte tag |
| Đưa nonce vào chỗ tag hoặc ngược lại | Format sai, tag không match | Xác định envelope rõ ràng |
| Nonce tái sử dụng với cùng key | Hỏng confidentiality/integrity | Cấp nonce duy nhất mỗi encryption |
| Sinh nonce bằng `Random`/timestamp thấp | Có nguy cơ va chạm | `SecureRandom` hoặc counter bền vững |
| “Sửa” nonce reuse bằng đổi AAD | Vẫn dùng lại Poly1305 key | Đổi nonce và quản lý uniqueness |
| Trộn raw/AEAD trong cùng protocol mà không version | Decoder có thể hiểu sai | Algorithm/version authenticated |
| Không kiểm tra type/length/key | Exception hoặc thông điệp sai | Validate bytes và key policy |
| Giải mã lại raw khi AEAD bad tag | Hạ cấp bảo mật | Từ chối message, không fallback |
| Công bố plaintext từ `update` trước tag | Dữ liệu giả có thể gây side effect | Chờ `doFinal` verify |
| Nghĩ AEAD chống replay | Tag cũ vẫn đúng | Sequence/message ID/replay window |
| Coi AAD là bí mật | Metadata vẫn lộ | Mã hóa phần nhạy cảm |
| Coi AAD là bằng chứng phân quyền | Caller có thể chọn metadata sai | Authn/authz và key isolation riêng |
| Dùng sample key/nonce của RFC cho production | Dữ liệu test là công khai | Key/nonce an toàn ở runtime |
| Log raw secret key/plaintext tùy tiện | Lộ dữ liệu | Redact/scope logs |
| Tự viết Poly1305 hoặc mode AEAD | Dễ sai nonce/counter/tag/padding | Dùng transformation có sẵn |
| Dùng RFC 7539 mà bỏ bản thay thế RFC 8439 | Bỏ lỡ errata/cập nhật | Dùng RFC 8439 làm tham chiếu hiện tại |
| Nghĩ có JCE AEAD thì TLS luôn dùng cùng cipher suite | JCE và JSSE khác tầng | Cấu hình/kiểm thử TLS độc lập |

## 16. Bài tập có đáp án

**Bài 1 — chọn mode.** Một hệ thống cần mã hóa thông điệp chuyển khoản và phát hiện người sửa dữ liệu. Nên dùng raw ChaCha20 hay ChaCha20-Poly1305?  
**Đáp án:** AEAD `ChaCha20-Poly1305` hoặc AEAD chuẩn khác. Raw ChaCha20 một mình không kiểm tra integrity.

**Bài 2 — Java param.** Viết lời gọi đúng khởi tạo raw ChaCha20 trên Java 11.  
**Đáp án:** `Cipher.getInstance("ChaCha20")`; `init(ENCRYPT_MODE, key, new ChaCha20ParameterSpec(nonce12, initialCounter))`.

**Bài 3 — AEAD param.** Dùng `ChaCha20ParameterSpec(nonce,1)` cho `"ChaCha20-Poly1305"` có đúng không?  
**Đáp án:** không. Dùng `IvParameterSpec(nonce12)`; AEAD tự quản lý counter.

**Bài 4 — AAD.** Metadata `tenant=42;version=1` cần được xác thực nhưng không cần bí mật. Đưa vào đâu?  
**Đáp án:** `updateAAD` ở encrypt và decrypt, cùng bytes/thứ tự, trước payload; đồng thời vẫn phải kiểm tra quyền tenant bằng authz riêng.

**Bài 5 — output.** Mã hóa `100` byte bằng AEAD, không có envelope, `doFinal` trả bao nhiêu?  
**Đáp án:** `116` byte, gồm ciphertext 100 byte và tag 16 byte. Nếu tự thêm version 1 byte, nonce 12 byte thì envelope `129` byte.

**Bài 6 — sửa ciphertext.** Một bit raw ciphertext bị đổi. Cipher decrypt báo lỗi không?  
**Đáp án:** có thể không báo và plaintext bị đổi tương ứng. AEAD phát hiện qua tag và từ chối.

**Bài 7 — sai AAD.** AAD bên encrypt là `type=A`, bên decrypt là `type=B`. Có lấy được plaintext hợp lệ không?  
**Đáp án:** không, tag verification thất bại trừ các trường hợp xác thực bị phá mà mô hình bảo mật không kỳ vọng.

**Bài 8 — nonce.** Hai request cùng key sử dụng chung nonce nhưng khác AAD. Có được không?  
**Đáp án:** không. AAD khác không làm reuse key+nonce trở nên an toàn.

**Bài 9 — streaming.** Decrypt AEAD theo chunk và `update` trả byte trước tag. Có được cập nhật DB ngay không?  
**Đáp án:** không. Chỉ công bố/commit sau `doFinal` thành công.

**Bài 10 — replay.** Một envelope đúng tag bị phát lại hai lần. AEAD có tự từ chối bản thứ hai không?  
**Đáp án:** không. Protocol phải quản lý sequence/nonce/message ID, replay window và state.

**Bài 11 — RFC.** Tại sao cần vector RFC 8439 nếu demo round-trip đã PASS?  
**Đáp án:** test vector xác minh byte đầu ra độc lập, phát hiện sai counter, AAD, tag và serialization.

**Bài 12 — key management.** Key mới có nghĩa dùng lại nonce cũ luôn hợp lệ không?  
**Đáp án:** uniqueness áp dụng cho mỗi key, nhưng key rotation và namespace nonce phải đúng protocol; tránh vô tình phục hồi **key cũ** với counter/nonce đã dùng trước đó.

**Bài 13 — payload dài.** Có nên mã hóa cả một stream không giới hạn bằng một nonce AEAD không?  
**Đáp án:** không. Counter hữu hạn; dùng record có giới hạn, nonce mới và tag riêng, cùng protocol streaming có đánh giá.

**Bài 14 — mật mã và TLS.** API `ChaCha20-Poly1305` trong `Cipher` có tự bật TLS cipher suite cùng tên cho HttpClient không?  
**Đáp án:** không. JCE application encryption và JSSE TLS negotiation là hai lớp khác nhau.

## 17. Tài liệu kỹ thuật còn áp dụng

- [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439): raw stream cipher, Poly1305, AEAD, AAD, tag 128-bit và các known-answer vectors.
- [JEP 329 — ChaCha20 and Poly1305 Cryptographic Algorithms](https://openjdk.org/jeps/329): tính năng bổ sung vào JDK 11.
- [Java SE 11 — ChaCha20ParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html): nonce 12 byte và initial counter kiểu int cho raw.
- [Java SE 11 — IvParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html): tham số nonce cho AEAD.
- [Java SE 11 — Cipher](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html): `init`, `update`, `updateAAD`, `doFinal`.
- [Java SE 11 — AEADBadTagException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/AEADBadTagException.html): xử lý authentication failure.
- [Java SE 11 — JDK Providers](https://docs.oracle.com/en/java/javase/11/security/oracle-providers.html): transformations do SunJCE hỗ trợ.
- [Java SE 11 — Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html): `ChaCha20`, `ChaCha20-Poly1305`.
- [Java SE 11 — KeyGenerator](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/KeyGenerator.html): tạo secret key.
- [Java SE 11 — SecureRandom](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/SecureRandom.html): sinh nonce ngẫu nhiên bảo mật.

**Kết luận:** Java 11 hỗ trợ **hai cấu hình ChaCha20 không được nhầm lẫn**. `ChaCha20` thuần yêu cầu `ChaCha20ParameterSpec` có counter, tạo ciphertext không có tag và **không xác thực**. `ChaCha20-Poly1305` yêu cầu `IvParameterSpec` chứa nonce, hỗ trợ AAD và thêm tag 16 byte; mọi dữ liệu nhận về chỉ được tin cậy sau khi tag đã xác minh thành công. Dù chọn AEAD đúng, bảo mật còn phụ thuộc **nonce không lặp, phân phối/đổi key, chống replay, xử lý lỗi và cách bind metadata**, không chỉ một lời gọi `Cipher.doFinal`.