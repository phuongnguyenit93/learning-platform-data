# 9.3. Phân biệt ký bằng khóa riêng với mã hóa bằng khóa công khai

**Chữ ký số** và **mã hóa khóa công khai** đều thuộc mật mã bất đối xứng, nhưng giải quyết **hai vấn đề khác nhau**. Chữ ký số dùng **khóa riêng của người ký** để tạo chữ ký, rồi dùng **khóa công khai của chính người ký** để kiểm tra nguồn gốc và tính toàn vẹn. Mã hóa khóa công khai dùng **khóa công khai của người nhận** để mã hóa, rồi dùng **khóa riêng của người nhận** để giải mã nhằm giữ bí mật nội dung.

Trong Java 21, hai tác vụ này cũng có **API, thuật toán và yêu cầu tham số riêng**: `java.security.Signature` dành cho ký/xác minh, còn `javax.crypto.Cipher` có thể thực hiện mã hóa/giải mã RSA-OAEP. Bài học tập trung vào cách tư duy đúng, tránh nhầm “ký là mã hóa bằng private key”, và cách áp dụng an toàn trong giao thức thật.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Trả lời dứt khoát: **ai dùng khóa nào, để làm gì, và ai xác minh/giải mã được**.
2. Giải thích vì sao chữ ký số bảo vệ **nguồn gốc và toàn vẹn** nhưng không che giấu thông điệp; và vì sao mã hóa bằng public key của người nhận **không tự chứng minh danh tính người gửi**.
3. Phân biệt `Signature`, `Cipher`, `KeyPairGenerator`, `PublicKey` và `PrivateKey` trong Java 21; nhận ra Ed25519, RSA-PSS và RSA-OAEP là **những scheme khác nhau**.
4. Biên dịch/chạy các chương trình Java 21 minh họa: ký Ed25519 → xác minh, sửa message → signature fail; mã hóa RSA-OAEP → giải mã, người thứ ba vẫn có thể mã hóa bằng public key; ký RSA-PSS với tham số tường minh.
5. Chọn phương án khi ứng dụng cần **bí mật**, **chống sửa đổi**, **chứng minh người ký** hoặc **đồng thời cả hai**.
6. Tránh sai lầm trong quản lý khóa, chứng thư/public-key trust, padding, dữ liệu được ký, kích thước message, chống phát lại và mã hóa lai.

## 1. Bốn khóa cần phân biệt trong tình huống Alice gửi cho Bob

Giả sử Alice gửi tài liệu cho Bob:

- **Alice** có cặp khóa ký `(sk_A, pk_A)`: `sk_A` là private key chỉ Alice được quyền sử dụng; `pk_A` là public key tương ứng mà Bob phải xác thực nguồn.
- **Bob** có cặp khóa mã hóa `(sk_B, pk_B)`: `sk_B` là private key chỉ Bob giữ; `pk_B` là public key mà Alice cần xác thực là của Bob.

Chữ ký:

```text
Alice: signature = Sign(sk_A, message)
Alice → Bob: message, signature
Bob: Verify(pk_A, message, signature) → true / false
```

Mã hóa khóa công khai:

```text
Alice: ciphertext = Encrypt(pk_B, message)
Alice → Bob: ciphertext
Bob: message = Decrypt(sk_B, ciphertext)
```

**Hai mũi tên không đối xứng về mục đích:** public key để **xác minh chữ ký** phải thuộc *người ký*; public key để **mã hóa bảo mật** phải thuộc *người nhận*. Cả hai đều mang tên “public key”, nhưng không phải cùng một khóa, cùng thuật toán, hoặc cùng quyền sử dụng.

| Câu hỏi | Chữ ký số | Mã hóa khóa công khai |
| --- | --- | --- |
| Mục tiêu chính | Xác minh thông điệp do bên nắm signing private key tạo ra và chưa bị sửa | Giữ kín nội dung với người không có decryption private key phù hợp |
| Bên tạo | **Người ký**, dùng **private key của người ký** | **Người gửi**, dùng **public key của người nhận** |
| Bên kiểm tra/khôi phục | Người xác minh, dùng **public key của người ký** | **Người nhận**, dùng **private key của người nhận** |
| Dữ liệu truyền | Message (có thể đọc được) + chữ ký | Ciphertext (và metadata/khóa bọc cần thiết nếu mã hóa lai) |
| Kết quả API | `Signature.sign()` → bytes chữ ký; `verify()` → boolean | `Cipher.doFinal()` → ciphertext hoặc plaintext |
| Người khác có public key | Có thể kiểm tra chữ ký, **không thể tạo chữ ký hợp lệ nếu thiếu private key** | Có thể **tự mã hóa** dữ liệu gửi cho người nhận, nhưng không giải mã ciphertext đã nhận nếu thiếu private key |
| Chỉ riêng cơ chế đó có giữ bí mật? | **Không** | Có, nếu dùng scheme/cấu hình an toàn và quản lý khóa đúng |
| Chỉ riêng cơ chế đó có chứng minh người gửi? | Có điều kiện: cần xác minh public key thực sự thuộc người ký | **Không**; bất kỳ ai biết public key đều mã hóa được |
| Tự chống replay không? | **Không** | **Không** |

> Câu nhớ nhanh: **Ký = private key người ký → public key người ký kiểm tra. Mã hóa = public key người nhận → private key người nhận giải mã.**

## 2. Vì sao chữ ký số không phải là “mã hóa bằng private key”?

Bạn có thể gặp lời giải thích cổ điển: *“RSA ký bằng cách mã hóa hash bằng khóa riêng, người nhận giải mã hash bằng khóa công khai.”* Đây là phép ví von dễ nhớ về RSA toán học thô, nhưng **không phải định nghĩa đúng và không phải cách lập trình mật mã an toàn**.

### 2.1 Hai primitive/scheme có thiết kế khác nhau

- **RSA encryption** sử dụng scheme mã hóa như **RSAES-OAEP**. Mục tiêu là tính bí mật của bản rõ; gồm quy tắc đệm, hàm hash/MGF và xử lý lỗi riêng.
- **RSA signature** sử dụng scheme ký như **RSASSA-PSS** hoặc, để tương thích chuẩn/hệ thống hiện hữu, **RSASSA-PKCS1-v1_5**. Mục tiêu là tạo cấu trúc chữ ký có thể xác minh công khai và chống giả mạo.
- Ngay cả khi hai scheme cùng sử dụng nền tảng toán học RSA, **OAEP khác PSS**; không thể chuyển `Cipher` sang `ENCRYPT_MODE` bằng private key rồi coi kết quả là chữ ký RSA-PSS hợp lệ.
- **Ed25519/ECDSA** là thuật toán **chữ ký**; không có thao tác “mã hóa bằng public key Ed25519” tương đương. **X25519/ECDH** là cơ chế trao đổi/thỏa thuận khóa, không phải chữ ký hay mã hóa thông điệp độc lập.

**Do đó:** sử dụng `Signature` để ký/xác minh; sử dụng scheme mã hóa được thiết kế cho confidentiality. Không dùng raw RSA (`NoPadding`), “private-key encryption” hoặc tự xây padding/khối toán học RSA để tạo chữ ký.

### 2.2 “Có thể xác minh” khác “có thể đọc nội dung”

Một chữ ký số được gửi cùng message; public key chỉ giúp người nhận xác định chữ ký có hợp lệ đối với **đúng bytes message** hay không. Chữ ký không làm message trở nên bí mật: kẻ nghe lén vẫn thấy message nếu message được gửi bản rõ.

Ngược lại, RSA-OAEP ciphertext được tạo bằng public key của Bob, nhưng vì public key đó công khai, **cả Alice, Carol và một kẻ tấn công đều có thể mã hóa một thông điệp để gửi Bob**. Bob giải mã được không có nghĩa là thông điệp đến từ Alice.

### 2.3 Ví dụ tài liệu cần ký nhưng không cần mã hóa

Một nhà phát hành công khai file cài đặt và chữ ký đi kèm. Ai cũng được phép tải file và có thể đọc nội dung, nhưng chỉ chấp nhận nếu chữ ký đúng và public key được xác nhận là của nhà phát hành. Ở đây cần **authenticity/integrity**, không yêu cầu confidentiality của file công khai.

Ngược lại, thông điệp chứa thông tin cá nhân chỉ dành cho Bob cần **confidentiality**, và nếu Bob phải xác minh thực sự Alice gửi, nên thêm chữ ký hoặc cơ chế xác thực người gửi phù hợp.

## 3. Điều kiện tin cậy của public key

Giả sử attacker thay `pk_A` bằng public key của chính mình và tự ký một message giả. Nếu Bob tin nhầm public key đó là của Alice, lệnh `verify()` vẫn trả `true` — **chữ ký đúng về toán học nhưng danh tính bị giả**.

Do đó một hệ thống phải có cách **ràng buộc public key với danh tính/chủ thể đáng tin**:

- Chứng thư X.509 và kiểm tra chuỗi tin cậy, tên đích/danh tính, hiệu lực, key usage và chính sách thu hồi phù hợp.
- Một public key được phân phối qua kênh đã xác thực, hoặc key fingerprint được kiểm tra qua kênh độc lập.
- Registry khóa tin cậy theo `keyId`, tenant, principal, issuer, thuật toán và phiên bản, có vòng đời rotate/revoke.
- Với mã hóa, Alice cũng phải xác minh `pk_B` thật sự của Bob. Nếu attacker tráo thành public key của attacker, Alice sẽ mã hóa **cho attacker**, làm mất bí mật trước khi Bob nhận được.

**Private key** cần giữ bí mật; lưu trong keystore, KMS hoặc HSM theo yêu cầu, hạn chế quyền sign/decrypt riêng, kiểm toán sử dụng. Không đặt private key trong Git, source code, log hoặc trả ra API. Chỉ có public key mà không xác minh nguồn **không đủ** để thiết lập tin cậy.

**Chống chối bỏ** thường được nhắc như một lợi ích của chữ ký số, nhưng là thuộc tính có điều kiện: bảo vệ private key, xác định người sở hữu và chính sách/biên bản nghiệp vụ mới giúp quy kết trách nhiệm. Một byte signature hợp lệ đơn lẻ không tự tạo thành bằng chứng pháp lý tuyệt đối.

## 4. API nào của Java 21 dùng cho từng việc?

| API / tên thuật toán | Vai trò đúng | Đầu vào khóa |
| --- | --- | --- |
| `KeyPairGenerator.getInstance("Ed25519")` | Sinh key pair phục vụ chữ ký Ed25519 | Không có key sẵn; sinh cặp mới |
| `Signature.getInstance("Ed25519")` | Ký và xác minh Ed25519 | `initSign(PrivateKey)` / `initVerify(PublicKey)` |
| `KeyPairGenerator.getInstance("RSA")` | Sinh cặp khóa RSA | Kích thước phù hợp như 3072 bit trong ví dụ |
| `Signature.getInstance("RSASSA-PSS")` | Ký và xác minh RSA-PSS | Private key người ký / public key người ký, cùng tham số PSS |
| `Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding")` | RSA-OAEP mã hóa một payload nhỏ / khóa phiên | `ENCRYPT_MODE` với public key người nhận; `DECRYPT_MODE` với private key người nhận |
| `OAEPParameterSpec`, `MGF1ParameterSpec` | Chỉ định hash, MGF và parameter cho OAEP | Cùng cấu hình hai đầu |
| `PSSParameterSpec` | Chỉ định digest, MGF1, độ dài salt và trailer cho PSS | Cùng cấu hình hai đầu |

Các thuật toán này được hỗ trợ bởi các provider của Oracle/OpenJDK 21 thông dụng như **SunEC**, **SunRsaSign**, **SunJCE**. Provider khác, HSM hoặc môi trường ràng buộc FIPS có thể có tập thuật toán/chính sách khác; luôn kiểm tra trên runtime mục tiêu. “Có API `Signature`” không có nghĩa provider hỗ trợ bất cứ scheme nào bạn gõ vào.

**Đọc transformation RSA đúng:** chữ “`ECB`” trong tên transformation RSA `RSA/ECB/OAEPWithSHA-256AndMGF1Padding` chủ yếu là thành phần cú pháp theo cách đặt tên của một số provider; **đừng nhầm với AES-ECB**, một mode mã hóa khối không nên dùng cho dữ liệu nhạy cảm. Với RSA, cần đặc biệt chú ý **OAEP padding** và tham số MGF1.

## 5. Thực hành Java 21: Ed25519 ký, RSA-OAEP mã hóa

Đoạn demo tạo **hai cặp khóa riêng biệt**:

- `senderKeys` dùng cho **chữ ký Ed25519** của Alice. Cặp khóa Ed25519 không dùng để RSA-encrypt.
- `recipientKeys` dùng cho **mã hóa RSA-OAEP** gửi Bob. Ví dụ chỉ mã hóa một message ngắn, không phải file lớn.

Đây là chương trình độc lập, không yêu cầu thư viện ngoài JDK chuẩn 21. Tạo file **`SignVsEncryptDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public class SignVsEncryptDemo {
    // Explicit OAEP: hash SHA-256 va MGF1-SHA256 o ca hai dau.
    private static final OAEPParameterSpec OAEP_SHA256 =
            new OAEPParameterSpec("SHA-256", "MGF1",
                    MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT);

    public static void main(String[] args) throws Exception {
        byte[] message = "Transfer 100".getBytes(StandardCharsets.UTF_8);
        byte[] altered = "Transfer 900".getBytes(StandardCharsets.UTF_8);

        // 1) Ed25519: nguoi ky dung private key.
        KeyPair senderKeys = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(senderKeys.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(senderKeys.getPublic());
        verifier.update(message);
        System.out.println("signature valid: " + verifier.verify(signature));

        verifier.initVerify(senderKeys.getPublic());
        verifier.update(altered);
        System.out.println("altered message valid: " +
                verifier.verify(signature));

        // 2) RSA-OAEP: nguoi gui dung public key cua nguoi nhan.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair recipientKeys = generator.generateKeyPair();

        Cipher encryptor =
                Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        encryptor.init(Cipher.ENCRYPT_MODE,
                recipientKeys.getPublic(), OAEP_SHA256);
        byte[] ciphertext = encryptor.doFinal(message);

        Cipher decryptor =
                Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        decryptor.init(Cipher.DECRYPT_MODE,
                recipientKeys.getPrivate(), OAEP_SHA256);
        byte[] recovered = decryptor.doFinal(ciphertext);
        System.out.println("decryption restored original: " +
                Arrays.equals(message, recovered));

        // Bat ky ai co public key cua Bob deu co the ma hoa gui Bob.
        encryptor.init(Cipher.ENCRYPT_MODE,
                recipientKeys.getPublic(), OAEP_SHA256);
        byte[] outsiderCiphertext = encryptor.doFinal(altered);
        decryptor.init(Cipher.DECRYPT_MODE,
                recipientKeys.getPrivate(), OAEP_SHA256);
        System.out.println("outsider can encrypt: " +
                Arrays.equals(altered, decryptor.doFinal(outsiderCiphertext)));
    }
}
```

Biên dịch/chạy trên JDK 21, hoặc compiler hỗ trợ `--release 21` với runtime đủ mới:

```text
java -version
javac -version
mkdir out
javac --release 21 -encoding UTF-8 -d out SignVsEncryptDemo.java
java -cp out SignVsEncryptDemo
```

Stdout:

```text
signature valid: true
altered message valid: false
decryption restored original: true
outsider can encrypt: true
```

Giải thích từng dòng:

1. **`signature valid: true`**: `signer.initSign(senderKeys.getPrivate())` tạo chữ ký cho đúng bytes `message`; `verifier.initVerify(senderKeys.getPublic())` dùng public key **của người ký** để xác minh.
2. **`altered message valid: false`**: thay “100” bằng “900” nhưng giữ chữ ký ban đầu làm xác minh thất bại. Đây là minh họa **tính toàn vẹn và xác thực bằng chữ ký**, không phải phát hiện nhờ mã hóa.
3. **`decryption restored original: true`**: Bob dùng **private key của Bob** và đúng `OAEPParameterSpec` để giải mã ciphertext được tạo bằng public key của Bob.
4. **`outsider can encrypt: true`**: bất kỳ bên thứ ba nào có public key của Bob đều có thể mã hóa message khác cho Bob. Vì vậy việc Bob giải mã thành công **không chứng minh người gửi là Alice**.

Chương trình sinh khóa và ciphertext ngẫu nhiên trong mỗi lần chạy, nhưng không in các giá trị ngẫu nhiên nên các dòng output luôn có thể dự đoán khi provider hỗ trợ thuật toán. Public key được lấy từ cùng một cặp khóa trong demo, nên chương trình **chưa kiểm thử** vấn đề phân phối hoặc xác thực public key trên mạng.

### 5.1 Lưu ý quan trọng về các tham số OAEP

Code truyền **tường minh** `OAEPParameterSpec("SHA-256", "MGF1", MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT)`. Đây là cách làm rõ **hash OAEP** và **hash dùng trong MGF1** đều là SHA-256; không mặc định rằng chuỗi tên `OAEPWithSHA-256AndMGF1Padding` buộc mọi provider tự chọn cùng một MGF digest nếu không được cấu hình. Hai đầu mã hóa và giải mã phải dùng cấu hình tương thích.

Đừng dùng `RSA/ECB/NoPadding`, “RSA thô”, hoặc tùy tiện thay OAEP bằng padding lỗi thời. Nếu ciphertext, khóa hoặc tham số sai, giải mã có thể ném `BadPaddingException` hay exception liên quan; xử lý lỗi nội bộ đồng nhất, tránh tạo **decryption oracle** qua response, thời gian hoặc log.

Với RSA-OAEP, **kích thước plaintext giới hạn bởi modulus và hash**. Theo PKCS #1, giới hạn tối đa là:

```text
messageLength <= k - 2*hLen - 2
k    = do dai RSA modulus tinh bang byte
hLen = so byte cua OAEP hash (SHA-256 = 32)
```

RSA 3072 bit có `k = 384` byte; với SHA-256, tối đa **384 - 64 - 2 = 318 byte**. Đây là giới hạn của scheme, không phải “độ dài file có thể mã hóa”. Để mã hóa file hoặc message dài, dùng **mã hóa lai** (xem phần 8).

## 6. Cùng họ RSA nhưng scheme ký riêng: RSA-PSS

Nếu ứng dụng dùng **RSA cho chữ ký** thay vì Ed25519, hãy chọn `Signature.getInstance("RSASSA-PSS")` và chỉ định `PSSParameterSpec`. Việc cả RSA-PSS lẫn RSA-OAEP cùng có tên RSA **không biến hai thao tác thành một**.

Tạo file **`RsaPssSignatureDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public class RsaPssSignatureDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair pair = generator.generateKeyPair();
        byte[] message = "Order 123".getBytes(StandardCharsets.UTF_8);

        // Digest SHA-256, MGF1 SHA-256, salt 32 byte, trailerField=1.
        PSSParameterSpec params = new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.setParameter(params);
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] tag = signer.sign();

        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.setParameter(params);
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        System.out.println("RSA-PSS valid: " + verifier.verify(tag));
    }
}
```

```text
javac --release 21 -encoding UTF-8 RsaPssSignatureDemo.java
java RsaPssSignatureDemo
```

Stdout:

```text
RSA-PSS valid: true
```

Trong ví dụ, `Signature` tự xử lý băm và encoding theo scheme RSA-PSS, sau đó xác minh bằng public key. Bạn **không** viết `Cipher.init(ENCRYPT_MODE, privateKey)` để thay thế. Đối với RSA-PSS, cả hai đầu phải tương thích ở **digest, MGF, salt length, trailer field** và scheme đã chọn. Nếu muốn chữ ký tương thích hệ thống khác, phải quy định parameter và định dạng chữ ký rõ ràng.

*Ghi nhớ:* không nhất thiết một cặp RSA dùng cho cả ký và mã hóa. Thực hành tốt là **tách khóa theo mục đích**, giới hạn quyền private key, quản lý rotation và chọn scheme phù hợp với chính sách. Chứng thư X.509 còn có thuộc tính `keyUsage` hoặc `extendedKeyUsage` để kiểm soát cách sử dụng khóa trong bối cảnh liên quan.

## 7. Khi nào cần ký, khi nào cần mã hóa?

| Tình huống | Cần gì? | Lý do |
| --- | --- | --- |
| Nhà phát hành công khai bản cập nhật và chữ ký | **Chữ ký số** | File được phép công khai, người tải cần biết file chưa bị sửa và đúng nhà phát hành |
| Gửi bí mật cho một người nhận đã có public key đáng tin | **Mã hóa khóa công khai / hybrid encryption** | Người khác không đọc được nội dung khi thiếu private key của người nhận |
| Lệnh giao dịch vừa nhạy cảm vừa cần chứng minh người ký | **Ký + mã hóa hoặc kênh bảo vệ được xác thực** | Cần cả nguồn gốc/toàn vẹn lẫn confidentiality |
| Chứng minh ai chấp thuận một văn bản dùng để kiểm toán | **Chữ ký số + ràng buộc danh tính, thời gian, hồ sơ phê duyệt** | Mã hóa chỉ che giấu, không chứng minh người ký |
| Giao tiếp HTTPS API có TLS và xác thực client | **TLS + cơ chế xác thực ứng dụng đúng yêu cầu** | TLS có chức năng bảo vệ kênh; chữ ký message-level là quyết định bổ sung tùy threat model |
| Mã hóa một tập tin lớn | **AES-GCM với khóa phiên + cơ chế bọc/thỏa thuận khóa** | RSA-OAEP không mã hóa trực tiếp file lớn |
| Chữ ký hợp lệ bị phát lại gây thao tác trùng | **Ràng buộc nonce, timestamp, request ID và replay state** | Ký đúng không có nghĩa là yêu cầu mới |

**Không có cơ chế duy nhất tự đáp ứng mọi mục tiêu.** Lựa chọn phải xuất phát từ thuộc tính bảo mật và threat model: ai có thể đọc, ai có thể gửi, ai được phép xác minh và ai được phép mở dữ liệu.

### 7.1 Chữ ký và MAC/HMAC có giống nhau không?

Cả chữ ký số và MAC có thể kiểm tra integrity/authenticity theo giả định về khóa, nhưng:

- **MAC/HMAC** dùng **khóa bí mật đối xứng**: các bên cùng biết khóa đều có thể tạo tag. Không có kiểm chứng công khai tương tự chữ ký số; phân định trách nhiệm giữa hai bên giữ cùng khóa rất khác.
- **Chữ ký số** dùng **private key để ký**, **public key để xác minh**. Người xác minh thường không có khả năng tạo chữ ký hợp lệ; nó hữu ích khi nhiều người cần xác minh nhưng chỉ một chủ thể được quyền ký.
- **Mã hóa public key** che giấu message với người không có decryption private key; bản thân nó không làm được công việc của chữ ký hoặc HMAC.

## 8. Nếu vừa cần bí mật vừa cần xác thực người gửi: thiết kế envelope

Giả sử Alice phải gửi cho Bob một đơn hàng bí mật và Bob cần kiểm tra chính Alice đã phát hành nó. Thiết kế thường gồm:

1. Alice tạo payload có **phiên bản giao thức, senderId, recipientId, requestId, thời gian, nội dung**; thống nhất quy tắc serialize/canonicalize.
2. Alice dùng **signing private key của Alice** ký các bytes đã thống nhất. Chữ ký phải bao phủ dữ liệu ảnh hưởng đến ý nghĩa giao dịch và ngữ cảnh.
3. Tạo một **session key ngẫu nhiên** cho **AES-GCM**, mã hóa payload và signature bằng AES-GCM với nonce/IV riêng, AAD phù hợp. Đây là bước bảo vệ bí mật và tính toàn vẹn của ciphertext.
4. Dùng **public key mã hóa của Bob** và RSA-OAEP để **bọc session key** (không bọc cả file lớn), hoặc dùng cơ chế KEM/HPKE được triển khai theo chuẩn. Gửi envelope gồm metadata, wrapped key, nonce, ciphertext và GCM tag.
5. Bob dùng **decryption private key của Bob** mở session key, giải mã/kiểm tra AEAD tag, lấy message và signature.
6. Bob lấy **signing public key đáng tin của Alice**, xác minh signature rồi mới xử lý nghiệp vụ. Nếu giao dịch không được phép lặp, thêm **anti-replay state/idempotency**.

```text
Alice                                 Bob
------                                ------
Sign(sk_A, payload)                   trust(pk_A)
  |                                      ^
  v                                      |
payload + signature                  Verify(pk_A, payload, signature)
  |                                      ^
Encrypt_AES_GCM(random sessionKey)       |
  |                                      |
Wrap_RSA_OAEP(pk_B, sessionKey)          |
  |                                      |
  +------------ envelope ------------> Unwrap(sk_B), AES-GCM decrypt
```

Đây là **sơ đồ kiến trúc**, không phải đặc tả protocol hoặc mã độc lập để tự triển khai. Thực tế cần xác định chính xác AAD, version, key ID, canonical bytes, quy tắc nonce/IV, các phản hồi lỗi và biện pháp chống replay. Đặc biệt **AES-GCM IV/nonce không được tái sử dụng với cùng khóa**. Khi dùng thư viện/giao thức chuẩn có sẵn, thường an toàn hơn tự sáng tạo một envelope mới.

Các lựa chọn như **X25519** cung cấp *key agreement*, không phải phép “mã hóa bằng public key” trực tiếp; khóa chia sẻ sau đó cần KDF và AEAD. **HPKE** là một thiết kế chuẩn tích hợp các bước KEM/KDF/AEAD. Việc chọn RSA-OAEP, HPKE hay TLS còn tùy giao thức, khả năng tương thích và chính sách hệ thống.

### 8.1 Ký trước hay sau khi mã hóa?

Ký plaintext rồi mã hóa cả message + signature, hoặc ký một envelope chứa ciphertext và metadata, đều có những ràng buộc về danh tính, thông tin lộ ra, phạm vi người xác minh và khả năng chuyển tiếp. Không có một quy tắc “ký trước/mã hóa sau” đúng cho mọi giao thức.

Khi đánh giá, hỏi rõ: **ai cần kiểm tra chữ ký và ở bước nào**, metadata nào phải được ký/AAD-protect, liệu người nhận có thể chuyển signature sang ngữ cảnh khác, liệu người ký có đang bị biến thành signing oracle, và liệu chữ ký được kiểm tra **trước khi có tác động nghiệp vụ**. Nếu dùng chuẩn có sẵn như CMS/JWS/JWE, hãy tuân thủ đúng profile và quy tắc xử lý của chuẩn thay vì tự ghép một thứ tự tùy ý.

## 9. Tính đúng đắn phụ thuộc vào bytes và ngữ cảnh được ký

Chữ ký xác minh **chuỗi byte**, không “ý định con người”. Ví dụ JSON:

```json
{"amount":100,"currency":"VND"}
```

và

```json
{ "currency": "VND", "amount": 100 }
```

Có thể biểu diễn cùng dữ liệu logic nhưng **khác bytes UTF-8**; nếu hệ thống ký bytes của chuỗi JSON, signature của phiên bản đầu **không** tự áp dụng cho phiên bản sau. Nếu có canonicalization, cả bên ký và bên xác minh phải thống nhất một đặc tả rõ ràng.

Khi ký một request, nên xác định phạm vi bao gồm:

- Version và loại message để ngăn nhầm protocol/thuật toán (*domain separation*).
- Principal/sender, intended recipient/audience, tenant/keyId/issuer nếu liên quan.
- HTTP method, URL/path/query/headers có ý nghĩa hoặc định danh nghiệp vụ.
- Body bytes hoặc canonical representation đúng thỏa thuận.
- Thời gian và nonce/requestId/sequence nếu giao thức cần hạn sử dụng và chống phát lại.

**Chữ ký đúng có thể bị replay nguyên gói.** Attacker không cần giả chữ ký: chỉ cần thu lại message + signature rồi gửi lần nữa. Chống replay là trách nhiệm riêng của giao thức, ví dụ lưu nonce/requestId đã xử lý trong phạm vi principal/khóa, thực hiện check-and-claim atomic và kiểm tra thời gian được ký. **Mã hóa** cũng không tự loại bỏ ciphertext cũ khi người nhận giải mã lần thứ hai.

## 10. Phân biệt khóa, algorithm, format và chứng thư trong thực tế

### 10.1 Khóa và thuật toán phải phù hợp mục đích

Một đối tượng `PrivateKey` có thể đại diện Ed25519, RSA hoặc EC tùy `getAlgorithm()` và provider; nó không có nghĩa mọi `Signature`/`Cipher` chấp nhận khóa đó.

- **Ed25519**: chủ yếu để ký/xác minh; không dùng public key Ed25519 để RSA-OAEP encrypt.
- **RSA**: có các scheme ký (RSA-PSS, RSA PKCS#1 v1.5 signature) và scheme mã hóa (RSA-OAEP). Cần định nghĩa rõ kiểu khóa/cặp khóa dành riêng cho vai trò.
- **X25519/ECDH**: thỏa thuận bí mật chung; không ký và không xuất trực tiếp bản mã.
- **AES-GCM**: mã hóa đối xứng có xác thực, dùng `SecretKey` và IV/nonce; không dùng `PublicKey`/`PrivateKey`.

Trong một ứng dụng có nhiều key, map `keyId` → thuật toán → mục đích → danh tính → public-key trust. Không cho phép request tự tuyên bố thuật toán rồi hệ thống tin theo vô điều kiện. Phải pin/allowlist những scheme và parameter được phép cho đúng loại message.

### 10.2 Key encoding không phải encryption

Public key có thể xuất dưới dạng **X.509 SubjectPublicKeyInfo** (`getEncoded()` với `X.509`), còn private key có thể ở dạng **PKCS#8** (`getEncoded()` với `PKCS#8`) tùy provider và khả năng xuất khóa. Đây là **định dạng serialize**, không tự động mã hóa hoặc kiểm tra người sở hữu; file PKCS#8 chứa private key không được mã hóa có thể làm lộ bí mật. Khi xuất private key bắt buộc bảo vệ bằng cơ chế phù hợp, tốt hơn dùng key store/HSM/KMS nếu có.

**Chứng thư số X.509** chứa public key cùng thông tin nhận dạng/chữ ký CA; không phải bản thân public key là chứng thư hợp lệ. Cần validate chain, trust anchors, key usage và bối cảnh (ví dụ hostname hoặc signer identity). Có thể gặp tình huống public key khớp về toán học nhưng certificate đã hết hạn, bị thu hồi hoặc không đúng mục đích sử dụng.

### 10.3 Tách khóa và quyền

Một hệ thống có thể dùng key pair riêng cho **ký yêu cầu** và **giải mã tài liệu**. Điều này cho phép:

- Thu hồi/rotate signing key mà không ảnh hưởng tài liệu đã mã hóa bằng key giải mã.
- Giới hạn quyền KMS/HSM: dịch vụ ký không có quyền decrypt dữ liệu khách hàng, dịch vụ decrypt không có quyền ký thay tổ chức.
- Áp chính sách thời hạn, sử dụng key, kiểm toán và backup/khôi phục cho từng mục tiêu.
- Tránh thiết kế phụ thuộc một key pair đa mục đích mà policy provider hoặc certificate không hỗ trợ.

## 11. Sai lầm thường gặp và cách sửa

| Nhầm lẫn | Vì sao sai | Cách nghĩ/cách làm đúng |
| --- | --- | --- |
| “Ký bằng khóa riêng = mã hóa dữ liệu bằng private key” | Scheme ký và scheme mã hóa có encoding, kiểm tra, padding, mục tiêu khác nhau | `Signature.initSign`/`initVerify` cho signature; RSA-OAEP/AEAD cho encryption |
| “Có public key là xác minh được Alice” | Attacker có thể tráo public key | Xác minh key ownership qua cert/registry/fingerprint đáng tin |
| “Bob giải mã được nên Alice chắc đã gửi” | Ai có `pk_B` đều mã hóa được | Xác thực người gửi riêng bằng chữ ký hoặc cơ chế tương đương |
| “Chữ ký làm người khác không đọc nội dung” | Message thường gửi bản rõ kèm chữ ký | Thêm encryption khi cần confidentiality |
| “RSA-OAEP mã hóa trực tiếp file lớn” | RSA có giới hạn kích thước plaintext và tốn chi phí | Hybrid encryption với AES-GCM + key encapsulation/wrapping |
| “RSA-PSS cũng chỉ là đổi mode của RSA Cipher” | Ký và mã hóa là scheme khác nhau | Dùng `Signature` và `Cipher` đúng API và parameters |
| “Ed25519 public key có thể dùng để encrypt” | Ed25519 là signature algorithm | Chọn cơ chế encryption/KEM/HPKE thích hợp, key riêng |
| “Bất kỳ chữ ký hợp lệ đều là request mới” | Replay nguyên message giữ nguyên chữ ký | Signed nonce/timestamp/requestId + kiểm tra trạng thái |
| “Cùng text JSON thì luôn cùng signature” | Serialization/bytes có thể khác | Ký đúng bytes hoặc quy định canonical form |
| “Chỉ cần dùng `SHA256withRSA` hay `RSASSA-PSS` không cần xem policy” | Scheme, parameters, provider, certificate key usage phải thống nhất | Chọn chuẩn, tường minh params và kiểm tra end-to-end |
| “Dùng RSA/NoPadding để hiểu cơ chế rồi đưa production” | Raw RSA không có scheme bảo vệ an toàn | Dùng OAEP/PSS được chuẩn hóa, thư viện được kiểm thử |
| “Đã dùng TLS thì không bao giờ cần chữ ký message” | TLS bảo vệ kênh theo session; có hệ thống cần kiểm toán/ủy quyền message nhiều chặng | Phân tích threat model, ràng buộc chữ ký với thao tác khi cần |

## 12. Gợi ý tự kiểm tra

1. **Hai cặp khóa:** Alice ký file để Bob xác minh. Chỉ rõ khóa nào được dùng để `sign()` và khóa nào được dùng để `verify()`. Nếu Carol có public key của Alice thì Carol có đọc được file gốc gửi kèm chữ ký không? Carol có tự tạo signature mới hợp lệ được không?
2. **Mã hóa:** Alice muốn Bob là người duy nhất đọc được message. Alice dùng public key của ai? Bob dùng private key của ai? Nếu Carol có public key của Bob, Carol có gửi ciphertext riêng để Bob giải mã được không?
3. **Mô hình hóa:** giải thích vì sao `Sign(sk_A, m)` và `Encrypt(pk_B, m)` không thể gộp thành “một phép mã hóa đảo chiều” dù đều thuộc asymmetric cryptography.
4. **Java lab:** chạy `SignVsEncryptDemo.java` với `--release 21` và giải thích bốn dòng stdout. Đổi `altered` về bằng `message` rồi giải thích vì sao phép verify sẽ trả `true`.
5. **RSA:** chạy `RsaPssSignatureDemo.java`, chỉ rõ `PSSParameterSpec` làm gì và tại sao `OAEPParameterSpec` không phải parameter cho signature PSS.
6. **Payload lớn:** tính kích thước plaintext tối đa với RSA-OAEP 3072 bit, SHA-256 (đáp án 318 byte). Lập sơ đồ mã hóa lai để gửi file 10 MB mà không mã hóa cả file trực tiếp bằng RSA.
7. **Public-key substitution:** vẽ kịch bản attacker thay public key Alice tại Bob rồi ký dữ liệu giả. Nêu cách PKI hoặc fingerprint độc lập ngăn attack này.
8. **Ứng dụng hóa:** một API thanh toán cần nội dung không lộ, biết ai tạo lệnh và không trừ tiền hai lần. Nêu từng thuộc tính cần cơ chế nào: confidentiality, signature/authentication, anti-replay và idempotency.
9. **Code review:** gặp `Cipher.getInstance("RSA/ECB/NoPadding")` và `cipher.init(ENCRYPT_MODE, privateKey)` dùng để “ký”. Trình bày vấn đề và thay bằng `Signature` với scheme ký chuẩn.
10. **Trust & lifecycle:** phân biệt việc “signature verify trả true” với kết luận “đúng tổ chức cần tin đã ký” khi chứng thư hết hạn, key bị thu hồi hoặc public key không được xác thực.

Bạn hoàn thành bài khi có thể trả lời được ngay ba câu hỏi: **(1) Dữ liệu cần bí mật hay cần xác thực? (2) Khóa công khai này thuộc người ký hay người nhận? (3) Java API và cryptographic scheme nào phù hợp với mục tiêu đó?**

## Tài liệu tham khảo chính thức

- [Java SE 21 — `java.security.Signature`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html): `initSign`, `initVerify`, `update`, `sign` và `verify`.
- [Java SE 21 — `javax.crypto.Cipher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): `ENCRYPT_MODE`, `DECRYPT_MODE`, transformation và `doFinal`.
- [Java SE 21 — `OAEPParameterSpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/OAEPParameterSpec.html): OAEP, MGF, PSource.
- [Java SE 21 — `PSSParameterSpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/PSSParameterSpec.html): tham số RSASSA-PSS.
- [Java SE 21 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): Ed25519, RSASSA-PSS và tên transformation RSA.
- [Java 21 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html): phạm vi hỗ trợ SunEC/SunRsaSign/SunJCE.
- [RFC 8017 — PKCS #1 v2.2](https://www.rfc-editor.org/rfc/rfc8017): phân biệt RSAES-OAEP và RSASSA-PSS, điều kiện và độ dài message.
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): Ed25519 và Ed448.
- [NIST CSRC — Digital Signature](https://csrc.nist.gov/glossary/term/digital_signature): khái niệm, mục tiêu xác thực/toàn vẹn và giới hạn confidentiality.
