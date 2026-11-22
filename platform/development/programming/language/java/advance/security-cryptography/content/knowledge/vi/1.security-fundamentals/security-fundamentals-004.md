# 1.4 Phân biệt mã hóa, hàm băm, MAC, chữ ký số và mã hóa biểu diễn

Trong bảo mật Java, năm khái niệm thường cùng biến dữ liệu thành một chuỗi byte trông khó hiểu, nhưng giải quyết **những bài toán khác nhau**. Gọi chung tất cả là “mã hóa” dẫn tới các thiết kế nguy hiểm: dùng Base64 để giấu bí mật, dùng SHA-256 thay cơ chế xác thực, hoặc mã hóa dữ liệu mà không phát hiện được sửa đổi.

## 1. Mục tiêu và mô hình tư duy

Sau bài này, bạn cần trả lời được:

- Muốn **giữ bí mật** dữ liệu trước người không có quyền đọc thì dùng gì?
- Muốn tạo **dấu vân tay** của dữ liệu để kiểm tra thay đổi thì dùng gì, và khi nào dấu vân tay đó có thể tin cậy?
- Muốn biết thông điệp đến từ bên **cùng giữ một khóa bí mật** và chưa bị sửa thì dùng gì?
- Muốn cho một bên thứ ba dùng **khóa công khai** kiểm tra ai đã ký thì dùng gì?
- Muốn biến byte nhị phân thành chuỗi thuận tiện để lưu/truyền (Base64, hex, UTF-8) thì dùng gì?

Trước hết, phân biệt các mục tiêu an toàn:

| Mục tiêu | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Confidentiality – tính bí mật** | Người không có khóa có đọc được nội dung không? | Che thông tin khách hàng trong bản sao lưu |
| **Integrity – tính toàn vẹn** | Nội dung có bị thay đổi so với bản được chấp nhận không? | Phát hiện request bị sửa |
| **Authenticity – tính xác thực nguồn gốc** | Có bằng chứng thông điệp xuất phát từ chủ thể/khóa được tin cậy không? | Server xác thực webhook |
| **Public verifiability – xác minh công khai** | Người không biết khóa bí mật có thể kiểm tra bằng khóa công khai không? | Xác minh bản phát hành được nhà phát triển ký |
| **Representation – biểu diễn dữ liệu** | Cần chuyển dữ liệu sang dạng tương thích với kênh truyền/lưu trữ nào? | Đưa byte vào JSON dưới dạng Base64 |

**Quy tắc:** Đầu ra khó đọc **không có nghĩa** đầu ra được bảo vệ. Muốn chọn đúng kỹ thuật, hãy bắt đầu từ mục tiêu, đối tượng tấn công và ai được nắm khóa.

## 2. Bảng phân biệt năm kỹ thuật

| Kỹ thuật | Khóa và thao tác chính | Kết quả | Đảm bảo cốt lõi | Không tự đảm bảo |
| --- | --- | --- | --- | --- |
| **Mã hóa (encryption)** | Thường dùng khóa bí mật chung; cũng có mã hóa khóa công khai. `encrypt → decrypt` | Bản mã; người có khóa thích hợp khôi phục bản rõ | **Bí mật**; chế độ AEAD như AES-GCM còn xác thực và bảo vệ toàn vẹn dữ liệu đã mã hóa | Mã hóa đơn thuần không nhất thiết xác thực người gửi hoặc chống sửa đổi |
| **Hàm băm mật mã (cryptographic hash)** | **Không có khóa**; `hash(message)` | Digest dài cố định, không được thiết kế để đảo ngược | Dấu vân tay, hỗ trợ đối chiếu thay đổi và nhiều cấu trúc mật mã | Không bí mật, không chứng minh ai gửi, không chống kẻ tấn công tự thay dữ liệu rồi băm lại |
| **MAC (Message Authentication Code)** | Hai bên cùng giữ **khóa bí mật**; `MAC(key, message)` và `verify` | Thẻ xác thực/tag | **Toàn vẹn + xác thực theo khóa chia sẻ** | Không che nội dung, không cho bên thứ ba biết bên giữ khóa nào đã tạo MAC |
| **Chữ ký số (digital signature)** | **Khóa riêng** để ký; **khóa công khai** để xác minh | Chữ ký kèm thông điệp hoặc tham chiếu tới thông điệp | **Toàn vẹn + xác thực theo khóa ký**, bên thứ ba có thể kiểm tra nếu tin đúng khóa công khai | Không che nội dung; không tự chứng minh danh tính nếu khóa công khai chưa được gắn đáng tin với chủ thể |
| **Mã hóa biểu diễn (encoding)** | **Không có khóa bảo mật**; `encode ↔ decode` | Dạng byte/text khác, khôi phục được nếu biết chuẩn | Tương thích định dạng và truyền tải | **Không** bí mật, toàn vẹn hay xác thực |

Có hai điểm cần tách bạch:

1. **Hash khác MAC:** một digest SHA-256 không có bí mật. Ai cũng băm lại được dữ liệu bị sửa. HMAC-SHA256 thêm khóa bí mật vào một cấu trúc mật mã được thiết kế riêng.
2. **Mã hóa khác mã hóa có xác thực:** một thuật toán/chế độ chỉ cung cấp bí mật chưa chắc phát hiện sửa đổi. Với dữ liệu ứng dụng mới, thường ưu tiên **AEAD (Authenticated Encryption with Associated Data)**, ví dụ AES-GCM.

## 3. Mã hóa: bảo vệ nội dung cần giữ bí mật

### 3.1. Mã hóa đối xứng và bất đối xứng

**Mã hóa đối xứng** dùng cùng khóa bí mật (hoặc khóa liên hệ trực tiếp) để mã hóa và giải mã. Các ví dụ thực tế gồm AES-GCM, ChaCha20-Poly1305. Nó phù hợp để mã hóa phần dữ liệu lớn. Trong Java, `Cipher` của JCA/JCE hỗ trợ `AES/GCM/NoPadding`.

**Mã hóa bất đối xứng** có cặp khóa công khai/riêng. Ví dụ, một bên dùng khóa công khai của người nhận để bảo vệ một khóa phiên và người nhận dùng khóa riêng để mở. RSA-OAEP là ví dụ cho thao tác mã hóa khóa công khai, nhưng không phù hợp để mã hóa trực tiếp nội dung lớn. Hệ thống thường dùng **mã hóa lai (hybrid/envelope encryption)**: bảo vệ khóa phiên bằng kỹ thuật khóa công khai hoặc KMS, dùng AES-GCM để mã hóa payload. Cặp khóa dùng **ký** cũng thuộc mật mã bất đối xứng nhưng là **thao tác khác** với mã hóa.

Không suy ra “mã hóa bằng private key, giải mã bằng public key” là chữ ký số. Chữ ký dùng thuật toán và quy tắc ký/xác minh riêng, không phải phép đảo khóa của mã hóa.

### 3.2. Vì sao AES-GCM thường là lựa chọn phù hợp

Một lần mã hóa AES-GCM về mặt ý tưởng:

~~~text
Đầu vào:  khóa bí mật K, bản rõ P, nonce N, dữ liệu liên kết AAD
AES-GCM(K, N, P, AAD)  → ciphertext C và authentication tag T
AES-GCM-decrypt(K, N, C, AAD, T) → P hoặc lỗi xác thực
~~~

- **Ciphertext** che nội dung. **Tag** phát hiện sửa đổi ciphertext, tag hoặc AAD khi kiểm tra thành công với khóa đúng.
- **AAD (Associated Authenticated Data)** là dữ liệu **được xác thực nhưng không mã hóa**, ví dụ mã phiên bản giao thức, loại thông điệp, tenant ID, nếu những thông tin đó phải được ràng buộc vào ciphertext.
- **Nonce/IV không phải khóa và không cần giấu**, nhưng **tuyệt đối không dùng lại cùng nonce với cùng khóa** trong AES-GCM. Nonce trùng có thể làm mất cả tính bí mật lẫn khả năng xác thực. Mẫu phổ biến là nonce 96 bit (12 byte); với lưu lượng lớn phải thiết kế chiến lược cấp nonce bảo đảm duy nhất thay vì chỉ dựa vào xác suất không trùng.
- Khi lưu/truyền cần có đủ `version/keyId + nonce + ciphertext + tag` (và AAD hoặc cách tái tạo AAD chính xác). Các byte này có thể **được biểu diễn** bằng Base64; Base64 ở đây chỉ là lớp đóng gói.

**Sai lầm thường gặp:** chọn `AES/ECB/PKCS5Padding` (lộ mẫu dữ liệu) hoặc mã hóa với chế độ không xác thực rồi cho rằng “đã mã hóa thì không thể sửa”. Với hệ thống mới, dùng AEAD theo giao thức/thư viện đã được thẩm định thay vì tự ghép thuật toán.

### 3.3. Khóa cần vòng đời quản lý

Tạo khóa bằng nguồn ngẫu nhiên an toàn; lưu ở secret manager/KMS, không hard-code trong repository hay log. Xác định ai có quyền giải mã, cách xoay khóa, cách đọc bản mã cũ theo `keyId` và cách thu hồi. Khóa thử nghiệm sinh trong chương trình mẫu bên dưới **mất khi tiến trình kết thúc**, nên không dùng để lưu dữ liệu bền vững.

## 4. Hàm băm mật mã: dấu vân tay, không phải hộp khóa

Với `H = SHA-256`:

~~~text
m = "abc"
SHA-256(m) = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

SHA-256 nhận dữ liệu có độ dài tùy ý và trả **256 bit (32 byte)**. Chuỗi hex trên có 64 ký tự vì mỗi byte được biểu diễn bằng hai ký tự hex. Hàm băm mật mã tốt hướng tới các tính chất:

- **Preimage resistance:** biết digest, việc tìm một thông điệp có digest đó phải rất khó về mặt tính toán.
- **Second-preimage resistance:** biết một thông điệp, việc tìm thông điệp khác có cùng digest phải rất khó.
- **Collision resistance:** việc tìm **bất kỳ hai** thông điệp khác nhau có cùng digest phải rất khó. Va chạm về mặt toán học vẫn tồn tại vì không gian đầu vào lớn hơn không gian đầu ra.

Dùng hash để kiểm tra file có bị thay đổi **chỉ có ý nghĩa an toàn trước kẻ tấn công** nếu giá trị digest mong đợi đến từ kênh đáng tin. Nếu kẻ tấn công sửa cả file và digest đăng cùng chỗ, phép so khớp vẫn thành công. Digest tốt cho phát hiện hỏng file ngẫu nhiên, định danh nội dung và làm thành phần của nhiều giao thức; nó **không chứng minh nguồn gốc** khi đứng một mình.

**Hash không phải encryption:** không có khóa giải mã để “khôi phục hash”. Tấn công vét cạn/tra bảng vẫn có thể đoán giá trị đầu vào có ít khả năng, như mật khẩu yếu, dù SHA-256 không thể đảo ngược trực tiếp.

**Lưu mật khẩu:** không dùng SHA-256/MD5/SHA-1 trực tiếp, kể cả thêm một chuỗi salt bằng phép nối tự thiết kế. Dùng bộ dẫn xuất khóa/mật khẩu thích hợp như **Argon2id** (khi môi trường hỗ trợ), **scrypt** hoặc **PBKDF2** với tham số chi phí phù hợp và **salt riêng, ngẫu nhiên cho mỗi mật khẩu**. Đây là bài toán password hashing/KDF, khác kiểm tra checksum file. MD5 và SHA-1 cũng không còn phù hợp cho những ứng dụng yêu cầu chống va chạm như chữ ký số.

## 5. MAC: xác thực bằng bí mật chung

Một **MAC** nhận khóa bí mật `K` và thông điệp byte `M`, sinh tag `T = MAC(K, M)`. Bên nhận biết cùng khóa tính tag kỳ vọng và so sánh:

~~~text
Client giữ K                            Server giữ K
M + K → HMAC-SHA256 → tag             M nhận + K → HMAC-SHA256 → tag'
Gửi M và tag  ────────────────────→   So sánh tag và tag' → chấp nhận/từ chối
~~~

**HMAC-SHA256** là MAC dựa trên SHA-256 nhưng **không phải** `SHA-256(key + message)` do tự chế. Một số cách nối khóa vào hash có vấn đề như **length-extension attack**; hãy dùng `Mac.getInstance("HmacSHA256")`.

Điều kiện để MAC có ý nghĩa:

1. Khóa phải **bí mật, đủ mạnh và phân phối an toàn**; nếu khóa lộ, kẻ tấn công tạo tag hợp lệ.
2. Hai bên phải tính MAC trên **cùng byte chính xác**: quy ước UTF-8, thứ tự trường, canonicalization, đường dẫn HTTP, body, timestamp, số phiên bản. Hai JSON tương đương về ý nghĩa có thể khác byte và cho tag khác nhau.
3. So sánh tag bằng hàm chống rò rỉ thời gian theo chuẩn thư viện, ví dụ `MessageDigest.isEqual(...)` cho các byte tag có độ dài cố định; không dùng phép so sánh ngừng ngay ở byte khác đầu tiên.
4. **MAC không tự chống replay.** Một request có tag hợp lệ có thể bị phát lại nguyên vẹn. Giao thức cần ràng buộc thời gian, nonce/request ID, cửa sổ hiệu lực hoặc bộ lưu trạng thái chống dùng lại theo nhu cầu.

Vì **cả hai phía cùng giữ khóa**, một bên thứ ba không thể kết luận phía nào đã tạo MAC. Đây là khác biệt trọng yếu với chữ ký số: **MAC phù hợp xác thực giữa các bên chia sẻ bí mật; chữ ký phù hợp khi cần xác minh bằng khóa công khai**. MAC không giấu nội dung message.

## 6. Chữ ký số: ký bằng khóa riêng, kiểm tra bằng khóa công khai

Quy trình khái niệm:

~~~text
Người ký:
  M + privateKey → Sign → signature
  Gửi M + signature (+ thông tin nhận diện khóa)

Người kiểm tra:
  M + signature + trustedPublicKey → Verify → true/false
~~~

- **Khóa riêng (private key)** chỉ người được phép ký giữ. **Khóa công khai (public key)** có thể phân phối để kiểm tra.
- Chữ ký của một thông điệp phải **không còn hợp lệ** nếu thông điệp thay đổi, khi xác minh với khóa công khai đúng và thuật toán an toàn.
- **Ed25519** là thuật toán chữ ký hiện đại, được Java 17 hỗ trợ qua `Signature.getInstance("Ed25519")`. Các hệ thống khác còn dùng RSA-PSS hoặc ECDSA theo yêu cầu tương thích.
- Chữ ký số **không mã hóa thông điệp**. Bất cứ ai nhận bản rõ vẫn đọc được nó.
- Xác minh toán học chỉ nói chữ ký tương ứng với **một khóa**. Muốn nói “do công ty X ký”, cần **tin rằng khóa công khai thực sự thuộc công ty X** qua chứng chỉ/PKI, khóa được pin, registry được bảo vệ hoặc quy trình phân phối đáng tin.
- Mất khóa riêng, khóa bị đánh cắp, thu hồi chứng chỉ, thay đổi người sở hữu và thời điểm ký là các vấn đề quản trị **bên ngoài phép Verify**. “Không thể chối bỏ” (non-repudiation) là mục tiêu có điều kiện, **không phải kết luận pháp lý tự động** chỉ vì `verify == true`.

Ví dụ: phát hành file `app.jar` kèm chữ ký. Người dùng lấy **khóa công khai đã được tin cậy** để kiểm tra đúng file đó. Khác với HMAC, người dùng **không cần sở hữu khóa có khả năng tạo chữ ký**.

## 7. Encoding: biểu diễn để chuyển/lưu, không phải bảo mật

**Encoding** là quy tắc chuyển cách biểu diễn, ví dụ:

- **UTF-8:** biến chuỗi ký tự thành byte; phải thống nhất bộ mã khi cả hai bên tính hash/MAC/signature.
- **Base64:** chuyển byte nhị phân thành ký tự ASCII để đưa vào JSON, cấu hình hoặc văn bản. `"hello"` (UTF-8) → `aGVsbG8=`; ai cũng giải mã được.
- **Base64URL:** biến thể phù hợp với URL/token, dùng `-` và `_` thay một số ký tự; thông thường bỏ padding tùy giao thức. Chữ ký của JWT/JWS thường được **biểu diễn** bằng Base64URL, nhưng Base64URL không làm JWT được mã hóa.
- **Hex:** biểu diễn mỗi byte bằng hai chữ số hệ 16; digest SHA-256 thường hiển thị bằng hex.

Phân biệt rõ ba tầng:

~~~text
Thông điệp text  --UTF-8-->   byte gốc
byte gốc        --SHA-256-->  digest byte    --hex/Base64--> chuỗi có thể in
byte gốc        --AES-GCM-->  ciphertext     --Base64-->     chuỗi có thể gửi
byte gốc        --HMAC-->     tag            --Base64-->     chuỗi có thể gửi
~~~

Giải mã Base64 chỉ trả lại **byte đầu vào của Base64**. Nếu byte đó là ciphertext, vẫn phải có khóa và thuật toán phù hợp mới giải mã được ciphertext; nếu là digest, không có phép “giải băm”.

**Cách tự kiểm tra:** Nếu người lạ có thể giải mã chuỗi bằng công cụ web/local mà không cần khóa bí mật, chuỗi đó **không được bảo mật chỉ nhờ lớp encoding**.

## 8. Ví dụ Java 17+ chạy được: cùng dữ liệu, năm thao tác khác nhau

Ví dụ này dùng các API có sẵn trong JDK: `MessageDigest` (hash), `Mac` (MAC), `Cipher` với AES-GCM (mã hóa có xác thực), `Signature` với Ed25519 (chữ ký), và `Base64` (encoding). Nó tự tạo khóa thử nghiệm bằng nguồn ngẫu nhiên an toàn, nên **không hard-code khóa**.

Lưu nguyên chương trình thành **`CryptoPrimitivesDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import javax.crypto.*;
import javax.crypto.spec.*;

public class CryptoPrimitivesDemo {
    static final byte[] DATA = "hello".getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) throws Exception {
        // 1) Hash: bất cứ ai cũng có thể tính cùng digest.
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest("abc".getBytes(StandardCharsets.UTF_8));
        System.out.println("SHA-256(abc) = "
                + HexFormat.of().formatHex(digest));

        // 2) HMAC: hai bên cùng giữ một khóa bí mật.
        SecureRandom random = new SecureRandom();
        byte[] macKey = new byte[32];
        random.nextBytes(macKey);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(macKey, "HmacSHA256"));
        byte[] tag = mac.doFinal(DATA);
        System.out.println("HMAC valid = "
                + MessageDigest.isEqual(tag, mac.doFinal(DATA)));
        System.out.println("HMAC altered valid = "
                + MessageDigest.isEqual(tag, mac.doFinal(
                        "HELLO".getBytes(StandardCharsets.UTF_8))));

        // 3) AES-GCM: mã hóa + xác thực; dùng nonce mới cho mỗi lần mã hóa
        // với cùng khóa. AAD phải giống nhau khi mã hóa/giải mã.
        KeyGenerator aesKeys = KeyGenerator.getInstance("AES");
        aesKeys.init(128, random);
        SecretKey aesKey = aesKeys.generateKey();
        byte[] nonce = new byte[12];
        random.nextBytes(nonce);
        byte[] aad = "header:v1".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, aesKey,
                new GCMParameterSpec(128, nonce));
        encrypt.updateAAD(aad);
        byte[] ciphertextAndTag = encrypt.doFinal(DATA);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, aesKey,
                new GCMParameterSpec(128, nonce));
        decrypt.updateAAD(aad);
        System.out.println("AES-GCM restored = "
                + new String(decrypt.doFinal(ciphertextAndTag),
                        StandardCharsets.UTF_8));

        // 4) Ed25519: ký với private key, kiểm tra bằng public key.
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(DATA);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(DATA);
        System.out.println("Ed25519 valid = "
                + verifier.verify(signature));

        verifier.initVerify(pair.getPublic());
        verifier.update("HELLO".getBytes(StandardCharsets.UTF_8));
        System.out.println("Ed25519 altered valid = "
                + verifier.verify(signature));

        // 5) Base64: không cần khóa, ai cũng có thể encode/decode.
        String encoded = Base64.getEncoder().encodeToString(DATA);
        System.out.println("Base64 = " + encoded);
        System.out.println("Base64 decoded = "
                + new String(Base64.getDecoder().decode(encoded),
                        StandardCharsets.UTF_8));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac CryptoPrimitivesDemo.java
java CryptoPrimitivesDemo
~~~

**Stdout** (không phụ thuộc vào các khóa ngẫu nhiên vì chỉ in kết quả kiểm tra):

~~~text
SHA-256(abc) = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
HMAC valid = true
HMAC altered valid = false
AES-GCM restored = hello
Ed25519 valid = true
Ed25519 altered valid = false
Base64 = aGVsbG8=
Base64 decoded = hello
~~~

Giải thích những gì vừa quan sát:

1. Hash của `abc` cố định; nó không có khóa và **không thể nói ai đã tạo dữ liệu**.
2. HMAC hợp lệ với đúng message và khóa; thay `hello` thành `HELLO` làm sai tag. Lưu ý ví dụ dùng lại đối tượng `Mac` sau `doFinal` vì JCA reset nó về trạng thái đã khởi tạo.
3. AES-GCM khôi phục `hello` bằng đúng khóa, nonce và AAD. Nếu ciphertext/tag/AAD bị sửa, `doFinal` khi giải mã sẽ thất bại xác thực (thường là `AEADBadTagException`), không được bỏ qua lỗi để nhận plaintext.
4. Chữ ký Ed25519 hợp lệ cho message gốc, không hợp lệ cho message bị thay. Người kiểm tra chỉ cần **public key** đã tin cậy.
5. Base64 chuyển `hello` thành `aGVsbG8=` và ngược lại, hoàn toàn **không cần khóa**.

**Giới hạn mẫu:** Chương trình trình diễn primitive, không phải giao thức lưu trữ/trao đổi hoàn chỉnh. Trong sản phẩm thực tế cần lưu nonce và tag cùng ciphertext; truyền/tra khóa tin cậy; chọn định dạng thông điệp, giới hạn độ dài, xác thực danh tính và xử lý lỗi không làm lộ thông tin nhạy cảm.

## 9. Chọn kỹ thuật qua tình huống thực tế

| Bài toán | Nên chọn | Vì sao và điều kiện |
| --- | --- | --- |
| Lưu bản sao dữ liệu chứa bí mật | **AES-GCM / AEAD** với khóa do KMS/secret manager quản lý | Người không có khóa không đọc được; tag phát hiện sửa, nonce phải duy nhất theo khóa |
| Kiểm tra file tải xuống có đúng bản công bố không | **SHA-256** nếu digest nhận qua kênh đáng tin; **chữ ký số** nếu cần kiểm tra nhà phát hành | Hash riêng lẻ không cản người tấn công sửa cả file lẫn digest |
| Xác thực webhook giữa đối tác và server cùng giữ secret | **HMAC-SHA256** trên byte request được quy chuẩn | Bảo vệ toàn vẹn/xác thực theo secret; thêm timestamp, request ID hoặc nonce để chống replay |
| Phát hành bản cập nhật cho nhiều người độc lập xác minh | **Chữ ký số** (ví dụ Ed25519) | Ai có public key tin cậy đều xác minh được mà không có quyền ký |
| Biểu diễn byte chữ ký/tag trong JSON hoặc URL | **Base64/Base64URL hoặc hex** | Chỉ là định dạng; phải áp dụng kỹ thuật mật mã riêng ở tầng trước |
| Lưu bộ xác minh mật khẩu | **Argon2id/scrypt/PBKDF2** với salt riêng | Chống đoán mật khẩu ngoại tuyến tốt hơn hash nhanh trực tiếp |
| Gửi dữ liệu an toàn qua mạng | **TLS** do thư viện chuẩn triển khai | Giao thức kết hợp xác thực peer, trao đổi khóa và AEAD; không tự ghép hash/MAC/encryption thành “TLS riêng” |

Một hệ thống có thể cần **nhiều** kỹ thuật cùng lúc. Ví dụ đơn giản cho tài liệu bí mật có chữ ký:

~~~text
Tài liệu gốc → người phát hành ký → (tài liệu + chữ ký)
             → mã hóa bằng khóa người nhận → ciphertext
             → Base64 nếu cần JSON
Người nhận: Base64-decode → giải mã + kiểm tag → kiểm chữ ký
            bằng public key đáng tin → đọc tài liệu
~~~

Lớp nào chịu trách nhiệm nào? **Encryption/AEAD** giữ bí mật khi truyền/lưu; **signature** giúp xác minh tác giả đã ký; **Base64** đưa byte vào định dạng truyền tải. Trình tự và cấu trúc thực tế phải theo giao thức chuẩn để tránh lộ siêu dữ liệu, lỗi xác thực hoặc nhập nhằng đối tượng được ký.

**Góc nhìn TLS 1.3:** kết nối TLS dùng mật mã bất đối xứng và cơ chế xác thực chứng chỉ/chữ ký ở giai đoạn bắt tay, thỏa thuận bí mật phiên, rồi dùng mật mã đối xứng AEAD cho dữ liệu ứng dụng. Vì vậy “HTTPS dùng RSA để mã hóa mọi byte HTTP” không phải mô tả đúng của TLS hiện đại.

**Góc nhìn JWT:** Một token **JWS** thông thường có các phần header/payload/signature được biểu diễn bằng Base64URL; **payload vẫn có thể đọc được**, chữ ký chỉ bảo vệ tính xác thực/toàn vẹn trong phạm vi khóa và validation đúng. **JWE** mới là dạng token mã hóa. Ứng dụng phải cố định thuật toán được phép, xác minh đúng khóa và kiểm tra claims như `iss`, `aud`, `exp` theo ngữ cảnh; chỉ decode payload không phải xác thực token.

## 10. Những nhầm lẫn nguy hiểm và cách sửa

| Nhầm lẫn | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| “Base64/hex là mã hóa bảo mật” | Ai cũng decode được secret | Dùng encryption cho bí mật; Base64 chỉ để biểu diễn ciphertext |
| “Có SHA-256 của file là biết ai phát hành” | Kẻ tấn công thay cả file và digest | Lấy digest từ kênh tin cậy hoặc kiểm chữ ký số bằng public key đã xác thực |
| “Băm mật khẩu bằng SHA-256 là đủ” | Hash nhanh cho phép thử rất nhiều mật khẩu đoán được | Dùng password KDF phù hợp, salt riêng, tham số chi phí cập nhật |
| “HMAC dùng cùng hàm SHA-256 nên giống hash” | Bỏ sót khóa, dễ chấp nhận digest giả | Dùng cấu trúc HMAC chuẩn với khóa bí mật và xác minh tag |
| “Có HMAC thì ngăn request lặp lại” | Attacker replay request đã ký hợp lệ | Ràng buộc timestamp/nonce/request ID và thực thi chính sách chống lặp |
| “AES-GCM có nonce thì cứ dùng lại cũng được” | Nonce trùng cùng khóa có thể phá nghiêm trọng bảo mật | Bảo đảm nonce duy nhất theo khóa, thiết kế cấp phát theo tải |
| “Ciphertext luôn không thể sửa” | Chế độ mã hóa không xác thực có thể bị thay đổi có chủ đích | Ưu tiên AEAD, từ chối dữ liệu nếu tag không hợp lệ |
| “`verify(signature) == true` nghĩa là công ty X đã ký” | Chấp nhận khóa công khai do kẻ giả mạo cung cấp | Xác minh chuỗi tin cậy/danh tính hoặc pin key theo quy trình rõ ràng |
| “Chuỗi khác nhau mới là thông điệp khác nhau” | Nhầm text, Unicode normalization, JSON serialization, charset | Quy chuẩn chính xác **byte được hash/MAC/ký** và encoding trước khi tính |

**Phân biệt khi debug:** `BadPaddingException`/`AEADBadTagException` ở tầng giải mã không giống HMAC mismatch, signature verification false hay Base64 decode error. Cùng biểu hiện “không đọc được dữ liệu” nhưng nguyên nhân và cách xử lý khác: thiếu khóa, sai nonce/AAD, dữ liệu bị sửa, tag sai, không tin public key, hoặc chuỗi truyền tải sai định dạng. Không “sửa” bằng cách tắt xác thực hay thử thuật toán ngẫu nhiên.

## 11. Bài tập tự kiểm tra có đáp án

**Tình huống A:** API trả một chuỗi Base64 chứa số thẻ thanh toán; người dùng nào đọc response cũng giải mã được. Dữ liệu đã được giữ bí mật chưa?

**Đáp án:** Chưa. Base64 là biểu diễn thuận nghịch công khai. Cần kiểm soát quyền truy cập và, nếu phải mã hóa ở tầng dữ liệu, dùng cơ chế encryption phù hợp với quản lý khóa.

**Tình huống B:** Một trang tải phần mềm đăng cùng thư mục file `app.zip` và `SHA256SUMS`. Nếu trang bị chiếm quyền, hacker sửa cả hai, SHA-256 có phát hiện được không?

**Đáp án:** Không nhất thiết. Digest mới có thể hoàn toàn khớp file độc hại. Cần digest từ kênh tin cậy độc lập hoặc chữ ký số xác minh qua public key được tin cậy.

**Tình huống C:** Server A và B cùng giữ secret để kiểm webhook. Người C không có secret nhưng biết HMAC tag của một request cũ. C có thể tạo request mới tùy ý hợp lệ không? Có thể gửi lại request cũ không?

**Đáp án:** Không thể tạo MAC hợp lệ cho request mới nếu HMAC/khóa an toàn; **có thể replay nguyên request cũ** nếu giao thức không chống phát lại.

**Tình huống D:** Khách hàng cần xác minh thông báo cập nhật do nhà phát hành ký mà không được quyền tự tạo thông báo ký hợp lệ. Chọn HMAC hay chữ ký số?

**Đáp án:** Chữ ký số. Nhà phát hành giữ private key; khách hàng chỉ giữ public key đã được xác thực.

**Tình huống E:** Bạn mã hóa bằng AES-GCM, giữ nguyên khóa nhưng dùng cùng nonce 12 byte cho mọi bản ghi. Hệ thống có an toàn không?

**Đáp án:** Không. Quy tắc nonce duy nhất theo khóa đã bị vi phạm. Phải đổi thiết kế cấp nonce và đánh giá lại tính an toàn của dữ liệu đã mã hóa dưới khóa bị sử dụng sai.

## 12. Ghi nhớ để áp dụng trong Java

- **Cần bí mật:** `Cipher` với AEAD như `AES/GCM/NoPadding`, cộng quản lý khóa và nonce đúng.
- **Cần dấu vân tay:** `MessageDigest` với SHA-256/SHA-3; tính xác thực của digest mong đợi phải được bảo đảm **bởi nguồn đáng tin khác**.
- **Cần xác thực bằng khóa chia sẻ:** `Mac` với `HmacSHA256`; quy chuẩn byte, bảo vệ secret và chống replay ở tầng giao thức.
- **Cần xác minh bằng public key:** `Signature` với Ed25519/RSA-PSS/ECDSA theo hệ sinh thái; xác minh danh tính/chứng chỉ gắn với khóa công khai.
- **Cần chuyển byte thành text:** `Base64` hoặc `HexFormat`, và thống nhất `StandardCharsets.UTF_8` khi chuyển text sang byte.

Mỗi thao tác tạo ra một loại bằng chứng khác nhau. Khi thiết kế API, lưu trữ, cập nhật phần mềm hay giao tiếp mạng, hãy mô tả riêng: **dữ liệu nào được giữ bí mật, byte nào được xác thực, khóa nào được ai tin cậy, và ai có thể kiểm tra**. Trả lời được bốn câu đó giúp tránh hầu hết sự nhầm lẫn giữa encryption, hash, MAC, chữ ký số và encoding.
