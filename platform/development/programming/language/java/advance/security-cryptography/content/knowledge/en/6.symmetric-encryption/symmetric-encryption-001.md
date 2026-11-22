# 6.1 Block cipher, stream cipher, mode và padding

## 1. Vì sao cần phân biệt bốn khái niệm?

**Mã hóa đối xứng** sử dụng khóa bí mật để mã hóa và giải mã. Tuy nhiên, **thuật toán nguyên thủy**, **mode**, **padding** và **xác thực** không phải một thứ. Chọn khóa AES dài 256 bit chưa quyết định cách ứng dụng xử lý một file nhiều megabyte hoặc biết ciphertext có bị sửa hay không.

Bài này tạo nền tảng cho chương: nhận diện AES là block cipher, ChaCha20 là stream cipher, hiểu mode của AES và khi nào cần padding, rồi phân biệt mã hóa thuần với mã hóa có xác thực (AEAD). Những bài tiếp theo sẽ chuyên sâu vào transformation/provider, key management, chu trình Cipher, ECB/CBC/CTR, GCM và ChaCha20. Các ví dụ ở đây tập trung **hình thái dữ liệu và nguyên tắc lựa chọn** thay vì lặp lại triển khai chuyên sâu của từng mode.

Mục tiêu sau bài:

1. Giải thích AES có block 128 bit dù key có thể là 128/192/256 bit.
2. Mô tả stream cipher sinh keystream và XOR với dữ liệu, cùng hậu quả của việc tái sử dụng keystream.
3. Nêu ý nghĩa và khác biệt của ECB, CBC, CTR, GCM trong cách dùng AES nhiều block.
4. Tính đúng số byte padding CBC và phân biệt padding với authentication tag.
5. Phân biệt key, IV/nonce, counter, AAD, tag và biết khi nào cần AEAD.
6. Dự đoán kết quả demo Java 17+ cho block cipher với input không tròn block và stream cipher với input 17 byte.

## 2. Block cipher: mã hóa từng khối có kích thước cố định

**Block cipher** biến đổi một khối plaintext có độ dài xác định thành một khối ciphertext cùng độ dài theo khóa bí mật:

```text
EncryptBlock(K, P) -> C
DecryptBlock(K, C) -> P
```

**AES** có block size cố định **128 bit = 16 byte**. Ba biến thể thường dùng chỉ khác **kích thước khóa**:

| Tên AES | Khóa | Block AES |
| --- | ---: | ---: |
| AES-128 | 128 bit = 16 byte | 128 bit = 16 byte |
| AES-192 | 192 bit = 24 byte | 128 bit = 16 byte |
| AES-256 | 256 bit = 32 byte | 128 bit = 16 byte |

Vì vậy “AES-256” **không** có nghĩa AES xử lý một block 32 byte. Nếu plaintext có 11 byte, phép mã hóa một block thô không tự biết thêm hoặc ghép dữ liệu ra sao. Nếu plaintext là file 1 GB, thuật toán block cơ sở cũng không tự định nghĩa thứ tự và quan hệ giữa các block.

Để xử lý thông điệp dài cần một **mode of operation**. Một số mode dùng IV/nonce, một số dùng padding; những quyết định này ảnh hưởng trực tiếp đến bảo mật.

### Vì sao không mã hóa độc lập từng block?

Nếu cùng khóa AES được dùng cho cùng block plaintext thì đầu ra của phép mã hóa block cơ sở giống nhau. Nếu toàn bộ thông điệp được chia thành các block rồi mã hóa độc lập theo ECB, hai block plaintext bằng nhau sẽ tạo hai block ciphertext bằng nhau. Kẻ quan sát có thể phát hiện mẫu lặp dù không đọc được byte plaintext. **Tăng độ dài khóa không loại bỏ lỗi lộ mẫu của ECB.**

## 3. Stream cipher: luồng khóa và phép XOR

**Stream cipher** sinh ra một chuỗi byte giả ngẫu nhiên mật mã (keystream) từ khóa và các tham số, rồi XOR với plaintext:

```text
keystream = Stream(K, nonce, counter, ...)
C = P XOR keystream
P = C XOR keystream
```

Vì xử lý theo byte/luồng, plaintext 17 byte thường tạo 17 byte ciphertext, **không cần đệm cho đủ block AES 16 byte**.

**ChaCha20** là một stream cipher hiện đại: biến thể IETF dùng **khóa 256 bit**, **nonce 96 bit** và bộ đếm block. ChaCha20 thuần chỉ mã hóa; **ChaCha20-Poly1305** thêm Poly1305 để có xác thực AEAD. Hai tên này không được sử dụng thay thế cho nhau.

Nguy cơ nguy hiểm nhất ở mode dựa trên keystream là dùng lại cùng vùng keystream. Nếu hai plaintext khác nhau cùng XOR với `S`:

```text
C1 = P1 XOR S
C2 = P2 XOR S
=> C1 XOR C2 = P1 XOR P2
```

Kẻ quan sát có thể suy ra quan hệ giữa hai plaintext, và từ một phần plaintext đã biết có thể suy ra phần còn lại. Do đó, với stream cipher và AES-CTR, **nonce/counter phải được quản lý để không tái dùng vùng keystream dưới cùng khóa**. Không dùng IV/counter mặc định là toàn 0 lặp lại cho các message.

**Cảnh báo:** stream cipher có thể được giải mã thành công ngay cả khi ciphertext bị sửa một bit. Muốn chống sửa đổi, cần cơ chế xác thực như AEAD hoặc sơ đồ được thiết kế an toàn; không xem phép giải mã thành công là kiểm tra toàn vẹn.

## 4. Mode: cách sử dụng AES cho một thông điệp

Một **mode** xác định cách phối hợp nhiều block và các tham số như IV/counter, chứ không làm thay đổi kích thước block AES. Bảng so sánh chỉ nêu đặc điểm nền tảng:

| Mode | Cách xử lý | IV/nonce | Padding | Có authentication tag sẵn? |
| --- | --- | --- | --- | --- |
| ECB | Mỗi block độc lập | Không | Có nếu không tròn block | **Không** |
| CBC | Chaining với ciphertext block trước | IV mới, khó dự đoán cho encryption | Thường dùng PKCS5Padding | **Không** |
| CTR | Mã hóa counter block thành keystream rồi XOR | Counter block không trùng dưới cùng khóa | Không | **Không** |
| GCM | Counter mode kết hợp cơ chế xác thực GCM | IV/nonce duy nhất mỗi lần encrypt theo khóa | Không | **Có** |

**ECB:** đơn giản để minh họa một phép mã hóa block nhưng làm lộ các block plaintext lặp. **Không chọn ECB để mã hóa dữ liệu ứng dụng.**

**CBC:** dùng IV (với AES thường là 16 byte) và nối trạng thái các block, khắc phục lộ mẫu theo cách của ECB khi IV phù hợp. Tuy nhiên, CBC thuần **không xác thực dữ liệu**. Sửa IV/ciphertext có thể tác động đến plaintext; lộ lỗi padding có thể tạo padding oracle. Nếu bắt buộc dùng CBC legacy, cần cơ chế xác thực đúng như Encrypt-then-MAC và kiểm MAC **trước** khi giải mã.

**CTR:** lấy keystream từ các counter block; ciphertext dài bằng plaintext. Nếu counter block lặp dưới cùng khóa, keystream lặp và an toàn bị phá vỡ. CTR không tự phát hiện bit-flipping.

**GCM:** một chế độ **AEAD (Authenticated Encryption with Associated Data)**, bảo vệ bí mật và kiểm tra toàn vẹn/xác thực bằng **authentication tag**. Trong Java thường dùng `AES/GCM/NoPadding`, nonce 12 byte và tag 128 bit, với yêu cầu tuyệt đối **không lặp nonce khi mã hóa cùng khóa**. GCM không tự quản lý key, quyền nghiệp vụ hay chống phát lại một packet hợp lệ.

Điểm phân định: ECB/CBC/CTR giúp hiểu cơ chế mode và rủi ro của **encryption-only**; AES-GCM minh họa lựa chọn AEAD thường phù hợp hơn cho dữ liệu mới. Phân tích tấn công CBC/CTR và HMAC Encrypt-then-MAC được học sâu ở bài 6.5.

## 5. Padding chỉ xử lý độ dài, không phải xác thực

Một số mode block như ECB/CBC cần plaintext có độ dài bội số 16 byte nếu dùng `NoPadding`. `PKCS5Padding` trong Java JCE dùng quy tắc đệm block kiểu PKCS#7 tương thích AES: thêm `n` byte, mỗi byte có giá trị `n`. Nếu plaintext đã tròn block, thêm **cả một block padding** để có cách bỏ padding không mơ hồ.

| Plaintext | Padding thêm với AES/CBC/PKCS5Padding | Ciphertext |
| ---: | ---: | ---: |
| 0 byte | 16 byte | 16 byte |
| 1 byte | 15 byte | 16 byte |
| 11 byte | 5 byte | 16 byte |
| 15 byte | 1 byte | 16 byte |
| 16 byte | 16 byte | 32 byte |
| 17 byte | 15 byte | 32 byte |

Với 11 byte input, padding năm byte có giá trị hex `05 05 05 05 05`. Với 16 byte, thêm nguyên 16 byte có giá trị `10`. **Padding hợp lệ không chứng minh ciphertext chưa bị sửa**; người tấn công có thể tác động vào CBC ngay cả khi thao tác giải mã không báo exception.

**NoPadding có các nghĩa thực tế khác nhau:**

- `AES/ECB/NoPadding` và `AES/CBC/NoPadding` cần input bội số 16 byte; phần cuối không đủ block có thể ném `IllegalBlockSizeException`.
- `AES/CTR/NoPadding` dùng keystream và mã hóa được plaintext 17 byte thành 17 byte.
- `AES/GCM/NoPadding` không đệm block nhưng **vẫn tạo tag xác thực**; tag 128 bit thêm 16 byte vào output ciphertext.
- ChaCha20/ChaCha20-Poly1305 không cần PKCS block padding; biến thể AEAD có tag riêng.

**Padding, Base64 và tag là ba việc khác nhau.** Base64/hex chỉ là biểu diễn binary dưới dạng ký tự. Tag/MAC kiểm tính xác thực theo khóa, không phải ký tự được thêm để ciphertext có độ dài tròn block.

## 6. Key, IV/nonce, counter, AAD và tag

| Thành phần | Vai trò | Bí mật hay công khai? |
| --- | --- | --- |
| **Key** | Bí mật chi phối mã hóa/giải mã, tag | Phải giữ bí mật; sinh từ CSPRNG/KeyGenerator hoặc KMS/keystore; có rotation |
| **IV/nonce** | Tham số phân biệt lần mã hóa/trạng thái mode | Thường công khai; CBC cần IV mới khó đoán, GCM/ChaCha20 cần không lặp dưới cùng khóa |
| **Counter** | Chọn khối keystream tiếp theo trong CTR/ChaCha20 | Không cần bí mật nhưng không được tái dùng cùng vùng dưới một khóa |
| **AAD** | Metadata được xác thực nhưng không mã hóa | Có thể công khai; phía giải mã phải có **cùng byte** và đúng thứ tự |
| **Tag** | Giá trị xác thực ciphertext và AAD | Có thể công khai; tag sai thì **không được chấp nhận plaintext** |

Một bản ghi GCM có thể lưu `version || keyId || nonce || ciphertext || tag`; **không** lưu raw key cạnh ciphertext. Key ID chỉ giúp chọn khóa, không phải secret. Khi giải mã, cần đúng key/nonce/AAD/tag, và phải xác minh tag thành công trước khi sử dụng plaintext hoặc kích hoạt side effect.

GCM tag hợp lệ **không tự chống replay**: nếu một thông điệp đã được xác thực bị phát lại nguyên vẹn, phép kiểm tra tag vẫn có thể thành công. Chống replay cần sequence/expiry/request ID cùng trạng thái nghiệp vụ riêng.

## 7. Java 17+: kiểm tra sự khác nhau của block và stream

Ví dụ độc lập **chỉ minh họa kích thước**, **không dùng ECB làm cơ chế lưu dữ liệu thực tế**. Chương trình kiểm tra AES xử lý đúng một block 16 byte, từ chối plaintext 17 byte khi chọn NoPadding, và kiểm tra ChaCha20 mã hóa/giải mã 17 byte mà không cần padding.

Lưu tệp **`BlockVsStreamDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.IllegalBlockSizeException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class BlockVsStreamDemo {
    public static void main(String[] args) throws Exception {
        KeyGenerator aesKeys = KeyGenerator.getInstance("AES");
        aesKeys.init(128);
        SecretKey aes = aesKeys.generateKey();
        byte[] block = "0123456789abcdef"
                .getBytes(StandardCharsets.US_ASCII);

        // ECB here only demonstrates one raw AES block.
        Cipher ecb = Cipher.getInstance("AES/ECB/NoPadding");
        ecb.init(Cipher.ENCRYPT_MODE, aes);
        System.out.println("AES block bytes: " + block.length);
        System.out.println("AES one-block output: " + ecb.doFinal(block).length);

        boolean rejected = false;
        try {
            ecb.doFinal("seventeen-byte-xx"
                    .getBytes(StandardCharsets.US_ASCII));
        } catch (IllegalBlockSizeException expected) {
            rejected = true;
        }
        System.out.println("AES incomplete block rejected: " + rejected);

        SecureRandom rng = new SecureRandom();
        byte[] rawKey = new byte[32];
        byte[] nonce = new byte[12];
        rng.nextBytes(rawKey);
        rng.nextBytes(nonce);
        SecretKey chacha = new SecretKeySpec(rawKey, "ChaCha20");
        ChaCha20ParameterSpec params =
                new ChaCha20ParameterSpec(nonce, 1);
        byte[] message = "1234567890abcdefg"
                .getBytes(StandardCharsets.US_ASCII);

        Cipher enc = Cipher.getInstance("ChaCha20");
        enc.init(Cipher.ENCRYPT_MODE, chacha, params);
        byte[] ciphertext = enc.doFinal(message);

        Cipher dec = Cipher.getInstance("ChaCha20");
        dec.init(Cipher.DECRYPT_MODE, chacha, params);
        byte[] recovered = dec.doFinal(ciphertext);

        System.out.println("Stream input bytes: " + message.length);
        System.out.println("ChaCha20 ciphertext bytes: " + ciphertext.length);
        System.out.println("Stream round-trip: "
                + Arrays.equals(message, recovered));
        Arrays.fill(rawKey, (byte) 0);
    }
}
```

Chạy bằng JDK 17+ có provider hỗ trợ AES và ChaCha20:

```bash
javac --release 17 BlockVsStreamDemo.java
java BlockVsStreamDemo
```

Stdout kiểm chứng bằng các lệnh JDK tương đương:

```text
AES block bytes: 16
AES one-block output: 16
AES incomplete block rejected: true
Stream input bytes: 17
ChaCha20 ciphertext bytes: 17
Stream round-trip: true
```

**Đọc kết quả:** AES/ECB/NoPadding không nhận một thông điệp 17 byte chưa được xử lý độ dài, còn ChaCha20 thuần tạo một keystream có đúng 17 byte để XOR với message. Key và nonce được sinh ngẫu nhiên, vì vậy ciphertext thật thay đổi nhưng các dòng độ dài và round-trip ổn định. ChaCha20 thuần ở đây **không xác thực ciphertext**; không dùng demo như encryption scheme production. `Arrays.fill` chỉ xóa buffer gốc chứ không chắc xóa bản sao trong `SecretKeySpec` hay provider.

## 8. Sơ đồ quyết định và lỗi thường gặp

**Nếu đang thiết kế tính năng mã hóa mới:** xác định trước cần chỉ bí mật hay cả toàn vẹn, phạm vi quản lý khóa, nonce và rủi ro sửa dữ liệu. Với nhiều ứng dụng, hãy chọn một AEAD chuẩn như AES-GCM hoặc ChaCha20-Poly1305, rồi xác định version/key ID/nonce/tag/AAD và kiểm thử tamper/round-trip. Không tự ghép mode và hash công khai để tạo cơ chế xác thực.

**Nếu đang đọc dữ liệu legacy:** kiểm tra chính xác mode/padding/IV/khóa/format đã dùng, không đoán provider mặc định từ `Cipher.getAlgorithm()`. Không thể chuyển ciphertext ECB/CBC cũ sang GCM bằng việc chỉ thay tên transformation ở reader. Cần chiến lược tương thích và migration có xác thực.

Các sai lầm cần nhận diện:

1. AES-256 có block 256 bit: **sai**, block AES luôn 128 bit.
2. ECB tự che mẫu dữ liệu khi dùng khóa mạnh: **sai**.
3. CBC/CTR giải mã được nghĩa là bản mã không bị sửa: **sai**.
4. NoPadding đồng nghĩa không có tag: **sai** với GCM.
5. Dùng lại IV/nonce/counter dưới cùng key không nguy hiểm: **sai**, đặc biệt đối với GCM và stream cipher.
6. AAD là dữ liệu đã được mã hóa: **sai**, AAD chỉ được xác thực.
7. Tag hợp lệ đồng nghĩa người dùng có quyền: **sai**, authorization độc lập.
8. Dùng `Cipher.getInstance("AES")` luôn cho GCM: **sai**, mode/padding mặc định phụ thuộc provider.

### Câu hỏi tự kiểm tra

1. AES-256 có kích thước khóa và block lần lượt bao nhiêu byte; vì sao?
2. Stream cipher xử lý 17 byte khác một phép AES block thô như thế nào?
3. Vì sao ECB lộ mẫu lặp dù khóa dài hơn?
4. Với CBC/PKCS5Padding, plaintext 16 byte vì sao tạo ciphertext 32 byte?
5. Điều gì xảy ra khi CTR hoặc ChaCha20 tái sử dụng cùng vùng keystream?
6. Vì sao GCM NoPadding vẫn có authentication tag, và tag sai phải dẫn tới hành vi gì?
7. Key, nonce, AAD và tag khác nhau về tính bí mật và khả năng xác thực ra sao?
8. Tại sao AEAD không tự chặn replay, phân quyền hoặc quản lý vòng đời khóa?

## Tài liệu tham khảo

- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformation, padding và AEAD.
- [Java SE 17 — ChaCha20ParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html): nonce/counter.
- [Java SE 17 — Java Cryptography Architecture](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): thuật toán và provider.
- [NIST SP 800-38A](https://csrc.nist.gov/pubs/sp/800/38/a/final): ECB, CBC, CTR.
- [NIST SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final): GCM và giới hạn nonce/tag.
- [RFC 8439](https://www.rfc-editor.org/rfc/rfc8439.html): ChaCha20 và ChaCha20-Poly1305.

**Kết luận:** block cipher mô tả primitive xử lý khối, stream cipher dùng keystream, mode định nghĩa cách mã hóa thông điệp, padding giải quyết độ dài ở những mode cần block. **Cần xác thực dữ liệu khi ciphertext có thể bị sửa**, không chỉ giải mã ra byte.