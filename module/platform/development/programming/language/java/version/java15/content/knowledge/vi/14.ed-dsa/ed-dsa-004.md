# EdDSA: Phân biệt chữ ký số, trao đổi khóa và mã hóa trong Java 15+

## 1. Bài toán và mục tiêu

Khi một ứng dụng Java cần trao đổi thông điệp an toàn, ba yêu cầu thường bị nhầm lẫn:

1. **Ai thực sự tạo hoặc phê duyệt thông điệp, và nội dung có bị thay đổi không?** Đây là bài toán **chữ ký số (digital signature)**.
2. **Hai bên ở hai máy khác nhau làm thế nào thống nhất một bí mật chung qua kênh công khai?** Đây là bài toán **thỏa thuận/trao đổi khóa (key agreement)**.
3. **Làm sao ngăn người nghe lén đọc nội dung, đồng thời phát hiện bản mã bị sửa?** Đây là bài toán **mã hóa có xác thực (authenticated encryption)**.

**EdDSA** (Edwards-Curve Digital Signature Algorithm) giải quyết **bài toán 1**, không tự giải quyết bài toán 2 hoặc 3. Java 15 giới thiệu hỗ trợ EdDSA chuẩn (JEP 339), gồm **Ed25519** và **Ed448**, qua Java Cryptography Architecture (JCA). Hỗ trợ này vẫn được sử dụng trong Java hiện hành.

Đối với hai bài toán còn lại, ví dụ Java thường dùng **X25519/X448 (XDH)** để thỏa thuận bí mật chung, **HKDF** để dẫn xuất khóa phù hợp và **AES-GCM** để mã hóa/bảo vệ tính toàn vẹn của dữ liệu. XDH đã có trong Java từ trước Java 15; nó **khác** EdDSA dù tên Ed25519 và X25519 gợi liên hệ về họ đường cong.

Mục tiêu sau khi học:

- Phân biệt chính xác đầu vào, đầu ra, loại khóa và thuộc tính bảo mật của chữ ký, key agreement và mã hóa.
- Tạo/xác minh chữ ký **Ed25519** bằng `KeyPairGenerator` và `Signature`.
- Thỏa thuận bí mật **X25519** bằng `KeyAgreement`; hiểu vì sao phải dẫn xuất khóa qua KDF và vì sao cần xác thực khóa công khai.
- Mã hóa/giải mã bằng `AES/GCM/NoPadding`, dùng nonce và AAD đúng vai trò.
- Chạy chương trình Java 15 độc lập minh họa cả ba chức năng và phát hiện hai kiểu sửa dữ liệu.
- Tránh nhầm lẫn nguy hiểm như “ký là mã hóa”, “X25519 tự xác thực đối tác”, “có shared secret là đủ an toàn” hoặc “có tag nghĩa là chống được replay”.

**Giới hạn:** Chương trình ở đây là bài minh họa API mật mã trong cùng một tiến trình, **không phải giao thức truyền thông có xác thực hoàn chỉnh**. Với kết nối mạng sản xuất, ưu tiên TLS 1.3 hoặc một giao thức được đánh giá bảo mật và thư viện triển khai uy tín thay vì tự thiết kế protocol.

## 2. Bảng phân biệt nhanh

| Thuộc tính | Chữ ký số | Thỏa thuận khóa | Mã hóa có xác thực |
| --- | --- | --- | --- |
| Câu hỏi | “Ai đã ký, và dữ liệu có bị sửa?” | “Hai bên thống nhất bí mật nào?” | “Ai có khóa mới đọc được, và bản mã có nguyên vẹn?” |
| Ví dụ thuật toán | **Ed25519, Ed448** (EdDSA) | **X25519, X448** (XDH) | **AES-GCM** |
| Java API chính | `java.security.Signature` | `javax.crypto.KeyAgreement` | `javax.crypto.Cipher` |
| Loại khóa | Cặp **private/public ký số** | Mỗi bên có cặp **private/public trao đổi khóa** | **Khóa bí mật đối xứng** |
| Đầu ra | Chữ ký; xác minh trả true/false hoặc báo lỗi | Shared secret bytes; thường đưa qua KDF | Ciphertext + authentication tag |
| Chống đọc trộm? | **Không** | **Không**, bản thân nó chưa mã hóa thông điệp | **Có**, với khóa an toàn và nonce đúng |
| Xác minh thay đổi dữ liệu? | **Có**, đối với dữ liệu đã ký và khóa tin cậy | **Không** | **Có**, đối với ciphertext và AAD dưới khóa hợp lệ |
| Tự xác thực danh tính bên kia? | Chỉ khi **public verification key** được gắn đúng với danh tính tin cậy | **Không**, XDH đơn thuần dễ bị man-in-the-middle | **Không**, tag chứng minh biết khóa, không tự xác nhận danh tính ngoài protocol |

**HKDF (HMAC-based Extract-and-Expand Key Derivation Function)** là một bước **dẫn xuất khóa**, không phải thuật toán chữ ký hay mã hóa. Nó biến đầu vào bí mật của XDH thành khóa đối xứng có chiều dài và mục đích xác định, với `salt` và `info` phù hợp; nhưng HKDF **không xác thực đối tác**.

Nhớ theo luồng:

```text
Ed25519 private key + message
            |
            v
        Signature.sign() ---> signature
            |
Ed25519 public key + message + signature ---> Signature.verify()

Alice X25519 private + Bob X25519 public -----+
                                               |--> shared secret
Bob X25519 private + Alice X25519 public -----+
                                               |
                                               v
                                         HKDF (salt, info)
                                               |
                                               v
                                            AES key
                                               |
plaintext + AES key + unique nonce + AAD --> AES-GCM encrypt
                                               |
                                               v
                                        ciphertext + tag
                                               |
AES key + same nonce + AAD + ciphertext + tag --> AES-GCM decrypt
```

Trong sơ đồ, hai phép tính X25519 tạo ra **cùng giá trị bí mật** nếu đầu vào và khóa phù hợp. Alice và Bob không gửi private key và cũng không truyền trực tiếp shared secret qua mạng. Public key, salt và nonce thường có thể truyền công khai, nhưng **public key phải được xác thực** nếu cần chống kẻ tấn công đứng giữa.

## 3. EdDSA/Ed25519: ký và xác minh, không phải mã hóa

### 3.1. Mô hình bảo mật của chữ ký số

- Alice giữ **private signing key**, không tiết lộ khóa này.
- Alice ký đúng một chuỗi byte `message` bằng `Signature.sign()`, thu `signature`.
- Bob nhận `message`, `signature` và sử dụng **public verification key** của Alice để gọi `Signature.verify(...)`.
- Nếu dữ liệu bị sửa hoặc chữ ký không đúng với khóa, quá trình xác minh thất bại. Tuy nhiên “xác minh toán học thành công” **không tự chứng minh public key thật sự của Alice**; Bob phải tin cậy việc gắn khóa đó với danh tính qua chứng thư, public key pinning, danh bạ khóa được xác thực hoặc cơ chế phù hợp.

Một chữ ký Ed25519 **không che giấu nội dung thông điệp**. Người không có khóa riêng vẫn có thể đọc `message` nếu thông điệp truyền dạng rõ. Chữ ký giải quyết **tính toàn vẹn và tính xác thực theo khóa**, không cung cấp **bí mật nội dung (confidentiality)**.

Cần phân biệt hai tuyên bố:
- “Dữ liệu được xác minh bằng public key P”: kết luận mật mã sau khi `verify` thành công.
- “Dữ liệu chắc chắn đến từ đúng cá nhân/tổ chức X”: còn cần cơ chế **tin cậy và quản lý khóa P ↔ X**. Chữ ký tự thân không đưa ra kết luận pháp lý tuyệt đối về không thể chối bỏ.

### 3.2. API chuẩn từ Java 15

```java
KeyPair signingKeys = KeyPairGenerator.getInstance("Ed25519")
        .generateKeyPair();

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(signingKeys.getPrivate());
signer.update(messageBytes);
byte[] signature = signer.sign();

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(signingKeys.getPublic());
verifier.update(messageBytes);
boolean valid = verifier.verify(signature);
```

Đây là **đoạn nằm trong một phương thức** đã import JCA và có `byte[] messageBytes`; chương trình hoàn chỉnh nằm ở mục 7.

Trong Java SE:
- `KeyPairGenerator.getInstance("Ed25519")` tạo cặp khóa Ed25519 (khác với cặp khóa X25519).
- `Signature.getInstance("Ed25519")` lấy triển khai chữ ký thích hợp từ provider.
- `initSign(privateKey)` / `initVerify(publicKey)` chọn vai trò; `update(...)` nạp **chính xác byte cần ký/kiểm tra**.
- `sign()` tạo chữ ký; `verify(signature)` cho biết chữ ký có đúng với dữ liệu và public key không.
- Có thể chọn Ed448 qua tên thuật toán **`Ed448`** khi provider hỗ trợ và chính sách ứng dụng yêu cầu. `EdDSA` là tên họ thuật toán; dùng tên cụ thể `Ed25519` hoặc `Ed448` giúp tránh nhầm tham số.

**Không tự băm bằng SHA-256 rồi gọi Ed25519 để “thêm độ an toàn”.** Ed25519 tiêu chuẩn có quy tắc hash nội bộ theo RFC 8032. Nếu protocol thật sự yêu cầu biến thể prehash/context, phải chọn đúng biến thể/tham số theo quy tắc giao thức; tự thay byte message bằng digest sẽ đổi **thông điệp được ký**, không mặc nhiên tương đương Ed25519ph. Không dùng tên tưởng tượng như `SHA256withEd25519` thay cho tên chuẩn.

### 3.3. Ký thông điệp không thay thế xác thực phiên làm việc

Nếu Alice ký một thông điệp chung nhưng Bob không xác thực chính public key X25519 mà họ đang dùng để trao đổi khóa, kẻ tấn công vẫn có thể thay public key X25519 trong quá trình bắt tay. Muốn dùng EdDSA để **xác thực key exchange**, phải ký và kiểm tra đúng **handshake transcript**: thuật toán/protocol version, danh tính, thứ tự vai trò, các public XDH keys, context và những tham số quan trọng. Cần định dạng transcript rõ ràng, tránh nối chuỗi mơ hồ, và bảo vệ chống replay theo protocol.

Đừng kết luận “có một chữ ký ở đâu đó” thì key exchange đã an toàn.

## 4. XDH/X25519: thỏa thuận khóa khác EdDSA

**X25519** là một phép thỏa thuận khóa Diffie–Hellman được đặc tả trong **RFC 7748**, được Java cung cấp qua XDH/JCA (JEP 324). Nó **không** tạo chữ ký và **không** mã hóa payload trực tiếp.

Mỗi bên cần một cặp khóa X25519:

```java
KeyPair alice = KeyPairGenerator.getInstance("X25519")
        .generateKeyPair();
KeyPair bob = KeyPairGenerator.getInstance("X25519")
        .generateKeyPair();

KeyAgreement a = KeyAgreement.getInstance("X25519");
a.init(alice.getPrivate());
a.doPhase(bob.getPublic(), true);
byte[] aliceSecret = a.generateSecret();

KeyAgreement b = KeyAgreement.getInstance("X25519");
b.init(bob.getPrivate());
b.doPhase(alice.getPublic(), true);
byte[] bobSecret = b.generateSecret();
```

Hai phía hợp lệ thu được cùng giá trị shared secret. Trong một giao thức, mỗi bên **chỉ trao đổi public key** qua mạng; private key được giữ nội bộ. `KeyAgreement.generateSecret()` xuất bytes của bí mật, **chưa phải quy trình mã hóa dữ liệu**.

**Không sử dụng trực tiếp shared secret làm khóa AES trong một thiết kế mới.** Hãy dùng một KDF đã được chuẩn hóa như HKDF để tách mục đích khóa, chiều dài, ngữ cảnh giao thức, nhánh truyền hai chiều và các ràng buộc cần thiết. Một shared secret cần được xác thực nguồn gốc trước khi tin tưởng giao tiếp.

### 4.1. Ed25519 không phải X25519

Tên có cùng số “25519” nhưng khác chức năng và kiểu khóa:

| Tên | Mục đích | Java nên gọi |
| --- | --- | --- |
| `Ed25519` | Chữ ký số EdDSA | `Signature.getInstance("Ed25519")`, `KeyPairGenerator.getInstance("Ed25519")` |
| `Ed448` | Chữ ký số EdDSA | `Signature.getInstance("Ed448")` |
| `X25519` | Key agreement XDH | `KeyAgreement.getInstance("X25519")`, `KeyPairGenerator.getInstance("X25519")` |
| `X448` | Key agreement XDH | `KeyAgreement.getInstance("X448")` |

Ed25519 sử dụng biểu diễn Edwards của họ đường cong liên quan Curve25519; X25519 sử dụng cơ chế Montgomery cho Diffie–Hellman. **Không coi khóa Ed25519 là đối tượng `PrivateKey`/`PublicKey` có thể truyền thẳng cho `KeyAgreement.getInstance("X25519")`** và không tự chuyển đổi khóa bằng thao tác byte tùy tiện. Nếu một giao thức có quy tắc chuyển đổi chuyên biệt, đó là vấn đề thiết kế riêng đã được chuẩn hóa/đánh giá; với JCA và ứng dụng thông thường, hãy tạo **các cặp khóa riêng theo đúng mục đích**.

### 4.2. XDH đơn thuần không chống man-in-the-middle

Một kẻ tấn công đứng giữa có thể thay public X25519 của Alice/Bob bằng public key của hắn, dẫn đến Alice và Bob lần lượt thống nhất shared secret với **kẻ tấn công**, không phải với nhau. Cả hai phép tính `generateSecret()` tại mỗi kết nối vẫn có thể thành công; không xuất hiện một ngoại lệ tự động chỉ ra danh tính sai.

Để triển khai thật:
- Dùng protocol xác thực như **TLS 1.3**, hoặc giao thức đã phân tích bảo mật.
- Nếu cần xác thực bằng EdDSA, tin cậy public signing key bằng một cơ chế độc lập và ký/kiểm tra toàn bộ transcript thỏa thuận khóa.
- Dùng khóa trao đổi ephemeral và các bước xác thực theo protocol khi cần forward secrecy; xóa/giới hạn vòng đời khóa bí mật theo khả năng công nghệ.
- Đừng gửi private key, shared secret hoặc AES key trong request, log, telemetry hay storage không được bảo vệ.

## 5. HKDF: biến shared secret thành khóa đối xứng

**HKDF** theo RFC 5869 gồm hai bước:

1. **Extract:** `PRK = HMAC-SHA256(salt, sharedSecret)`.
2. **Expand:** sinh khóa từ `PRK` cùng `info` và bộ đếm; ví dụ 32 byte đầu tiên là `HMAC-SHA256(PRK, info || 0x01)`.

Ở đây:
- **`sharedSecret`** là đầu ra X25519, không lộ cho đối tác thứ ba.
- **`salt`** là giá trị công khai (trong demo là 32 byte ngẫu nhiên), được hai bên thống nhất và truyền cùng metadata khi cần; không cần giữ bí mật nhưng không được để hai phía dùng salt khác nhau cho cùng phiên.
- **`info`** mô tả mục đích/phiên bản/giao thức hoặc chiều truyền, giúp *domain separation*. Trong hệ thống thực, cần thiết kế cách mã hóa bối cảnh và transcript chặt chẽ, đồng nhất giữa hai phía.
- **Khóa đầu ra** có độ dài tương ứng thuật toán mã hóa, ví dụ 32 byte cho AES-256.

Với Java 15, có thể thực hiện HKDF-SHA256 bằng `javax.crypto.Mac` (HmacSHA256). Chương trình đầy đủ ở mục 7 minh họa **đúng một block 32 byte** của bước Expand; nó **không** phải thư viện HKDF tổng quát cho mọi độ dài. Trong hệ thống sản xuất, nên ưu tiên KDF trong thư viện mật mã/giao thức được kiểm tra kỹ, không tự sao chép một snippet nhỏ rồi coi là protocol hoàn chỉnh.

**HKDF không làm một shared secret bị man-in-the-middle trở thành an toàn.** Nếu X25519 không được xác thực, dẫn xuất khóa chính xác đến đâu thì kẻ tấn công cũng có thể có khóa riêng trên mỗi liên kết do hắn thay thế.

## 6. AES-GCM: mã hóa có xác thực, không phải chữ ký số

Sau khi có khóa AES phù hợp, **`Cipher.getInstance("AES/GCM/NoPadding")`** giúp bảo vệ nội dung bằng một thuật toán AEAD (*Authenticated Encryption with Associated Data*).

Đầu vào chính:

- **Secret key:** khóa AES đối xứng, ví dụ 256 bit được dẫn xuất qua HKDF.
- **Nonce/IV:** trong demo là 12 byte (96 bit) được tạo bằng `SecureRandom`; **phải không trùng đối với cùng khóa**. Reuse nonce trong AES-GCM có thể phá hủy bí mật và tính toàn vẹn.
- **Plaintext:** bytes cần bí mật hóa.
- **AAD:** bytes không mã hóa nhưng được xác thực cùng ciphertext; ví dụ protocol version, loại bản tin hoặc mã định danh ngữ cảnh.
- **Tag:** authentication tag (demo là 128 bit) thường được provider ghép vào đầu ra của `doFinal`.

Đầu ra:

```text
AES-GCM Encrypt(key, nonce, AAD, plaintext)
               |
               v
        ciphertext + tag

AES-GCM Decrypt(key, same nonce, same AAD, ciphertext + tag)
               |
               +--> plaintext nếu tag hợp lệ
               |
               +--> lỗi xác thực nếu ciphertext/tag/AAD bị sửa
```

Dùng `GCMParameterSpec(128, nonce)` để chỉ định tag 128 bit và nonce; gọi `cipher.updateAAD(aad)` **trước** khi xử lý dữ liệu. Khi giải mã thất bại kiểm tra tag, **không sử dụng plaintext chưa xác thực** và không coi ngoại lệ thành thông điệp rỗng hợp lệ.

**Một tag GCM không đồng nghĩa chữ ký số.** Bất kỳ bên nào có cùng khóa AES đều có thể tạo tag hợp lệ; nó không chỉ ra danh tính ai trong số những bên biết khóa đã gửi dữ liệu. GCM cũng **không tự ngăn replay**: attacker có thể gửi lại một ciphertext + nonce + tag nguyên vẹn. Để chống phát lại cần sequence number, session state, nonce policy hoặc giao thức thích hợp.

**Nonce và salt không phải secret**, nhưng cần truyền đúng cùng thông điệp và ràng buộc vào protocol. Không dùng nonce cố định cho nhiều lần mã hóa dưới cùng AES key; không đổi sang `AES/ECB` hoặc mã hóa không có bảo vệ integrity chỉ để “đơn giản hóa”.

## 7. Chương trình Java 15 đầy đủ: ba vai trò và hai bài kiểm tra sửa dữ liệu

Chương trình chạy **trong một tiến trình** để minh họa Alice và Bob; không thiết lập một mạng có xác thực. Chúng ta:

1. Tạo cặp ký Ed25519, ký một thông điệp và xác minh; sửa thông điệp rồi xác minh lại.
2. Tạo **hai cặp khóa X25519 độc lập**, thực hiện agreement theo hai chiều và đối chiếu shared secret.
3. Dùng HKDF-SHA256 với một salt chung và info cố định để tạo khóa AES-256 ở hai phía.
4. Mã hóa bằng AES-GCM với nonce 12 byte ngẫu nhiên và AAD; giải mã bằng khóa của phía nhận.
5. Lật một bit trong ciphertext+tag và xác nhận quá trình giải mã **từ chối** dữ liệu bị sửa.

Lưu tệp đúng tên **`CryptoRolesDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class CryptoRolesDemo {
    public static void main(String[] args) throws Exception {
        byte[] message = "Thong diep mau".getBytes(StandardCharsets.UTF_8);
        KeyPair signingKeys = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(signingKeys.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(signingKeys.getPublic());
        verifier.update(message);
        System.out.println("signature valid: " + verifier.verify(signature));

        verifier.initVerify(signingKeys.getPublic());
        verifier.update("Thong diep da sua".getBytes(StandardCharsets.UTF_8));
        System.out.println("modified message accepted: "
                + verifier.verify(signature));

        KeyPair alice = KeyPairGenerator.getInstance("X25519")
                .generateKeyPair();
        KeyPair bob = KeyPairGenerator.getInstance("X25519")
                .generateKeyPair();
        byte[] aliceSecret = agree(alice.getPrivate(), bob.getPublic());
        byte[] bobSecret = agree(bob.getPrivate(), alice.getPublic());

        System.out.println("X25519 secrets match: "
                + MessageDigest.isEqual(aliceSecret, bobSecret));

        byte[] salt = new byte[32];
        SecureRandom random = new SecureRandom();
        random.nextBytes(salt);
        byte[] aliceAes = hkdfAes256(aliceSecret, salt);
        byte[] bobAes = hkdfAes256(bobSecret, salt);
        System.out.println("HKDF keys match: "
                + MessageDigest.isEqual(aliceAes, bobAes));

        byte[] nonce = new byte[12];
        random.nextBytes(nonce);
        byte[] aad = "demo-v1".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Hello, Java 15".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE,
                new SecretKeySpec(aliceAes, "AES"),
                new GCMParameterSpec(128, nonce));
        encrypt.updateAAD(aad);
        byte[] ciphertextAndTag = encrypt.doFinal(plaintext);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE,
                new SecretKeySpec(bobAes, "AES"),
                new GCMParameterSpec(128, nonce));
        decrypt.updateAAD(aad);
        byte[] recovered = decrypt.doFinal(ciphertextAndTag);
        System.out.println("decrypted: "
                + new String(recovered, StandardCharsets.UTF_8));

        byte[] modified = ciphertextAndTag.clone();
        modified[modified.length - 1] ^= 1;
        Cipher reject = Cipher.getInstance("AES/GCM/NoPadding");
        reject.init(Cipher.DECRYPT_MODE,
                new SecretKeySpec(bobAes, "AES"),
                new GCMParameterSpec(128, nonce));
        reject.updateAAD(aad);
        try {
            reject.doFinal(modified);
            System.out.println("modified ciphertext rejected: false");
        } catch (AEADBadTagException expected) {
            System.out.println("modified ciphertext rejected: true");
        }

        Arrays.fill(aliceSecret, (byte) 0);
        Arrays.fill(bobSecret, (byte) 0);
        Arrays.fill(aliceAes, (byte) 0);
        Arrays.fill(bobAes, (byte) 0);
    }

    private static byte[] agree(PrivateKey own, PublicKey peer)
            throws GeneralSecurityException {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(own);
        agreement.doPhase(peer, true);
        return agreement.generateSecret();
    }

    // HKDF-SHA256 (RFC 5869), mot block Expand 32 byte.
    private static byte[] hkdfAes256(byte[] ikm, byte[] salt)
            throws GeneralSecurityException {
        Mac hmac = Mac.getInstance("HmacSHA256");
        hmac.init(new SecretKeySpec(salt, "HmacSHA256"));
        byte[] prk = hmac.doFinal(ikm);
        try {
            hmac.init(new SecretKeySpec(prk, "HmacSHA256"));
            hmac.update("lesson-x25519-aesgcm-v1"
                    .getBytes(StandardCharsets.UTF_8));
            hmac.update((byte) 1);
            return hmac.doFinal();
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }
}
```

Biên dịch và chạy với một JDK có hỗ trợ đích Java 15:

```bash
javac --release 15 CryptoRolesDemo.java
java CryptoRolesDemo
```

**Stdout chính xác** (đã kiểm tra trên JDK hiện đại, chương trình biên dịch bằng `javac --release 15`):

```text
signature valid: true
modified message accepted: false
X25519 secrets match: true
HKDF keys match: true
decrypted: Hello, Java 15
modified ciphertext rejected: true
```

### Giải thích output

- `signature valid: true`: chữ ký đúng với byte `"Thong diep mau"` và public Ed25519 tương ứng.
- `modified message accepted: false`: khi dùng chữ ký cũ trên `"Thong diep da sua"`, xác minh trả `false`. Đây là phép kiểm tính toàn vẹn của **thông điệp đã ký**, không phải phép giải mã.
- `X25519 secrets match: true`: hai bên tính được cùng shared secret từ private key của mình và public key của bên kia. **Chưa có bảo đảm danh tính** của bên nhận trong demo.
- `HKDF keys match: true`: cùng shared secret, salt và info sinh cùng 32 byte khóa AES.
- `decrypted: Hello, Java 15`: AES-GCM khôi phục plaintext khi dùng đúng key, nonce, AAD và ciphertext+tag.
- `modified ciphertext rejected: true`: thay một bit của ciphertext+tag làm kiểm tra xác thực GCM thất bại; trong JDK/provider của demo, nhận `AEADBadTagException`.

**Vì sao output ổn định dù khóa ngẫu nhiên?** Chương trình không in private key, shared secret, signature, AES key, salt, nonce hay ciphertext. Các bytes ngẫu nhiên thay đổi mỗi lần chạy, nhưng các kiểm tra đúng/sai và plaintext recovered vẫn có kết quả xác định.

**Cần có provider phù hợp:** JDK được dùng để thử có các thuật toán Ed25519, X25519, HmacSHA256 và AES/GCM/NoPadding. Các triển khai Java khác có thể có chính sách/provider khác nhau; với môi trường triển khai thực tế, kiểm tra các thuật toán được provider cấu hình hỗ trợ. Không coi `NoSuchAlgorithmException` là lý do để tự đổi sang thuật toán yếu hơn.

### 7.1. HKDF trong demo dùng một block, không phải hàm HKDF tổng quát

Trong `hkdfAes256(...)`:

```text
PRK    = HMAC-SHA256(salt, ikm)
AESKey = HMAC-SHA256(PRK, UTF8("lesson-x25519-aesgcm-v1") || 0x01)
```

Đầu ra HMAC-SHA256 dài 32 byte, đúng chiều dài khóa AES-256 đang sử dụng. Nếu một hệ thống cần nhiều khóa, nhiều chiều truyền hoặc chiều dài khác, phải thực hiện đầy đủ quy tắc HKDF-Expand của RFC 5869 (nhiều block, counter) và domain separation của protocol; **không sửa qua loa một ký tự counter rồi dùng chung tất cả khóa**.

Việc gọi `Arrays.fill(...)` trong ví dụ chỉ là nỗ lực xóa các mảng byte mà mã nắm quyền truy cập. Nó **không bảo đảm** xóa mọi bản sao key trong JVM, đối tượng `KeyPair`, provider hoặc bộ nhớ hệ thống. Mã thật cần chính sách lưu, vòng đời và hủy khóa theo thư viện/thiết bị đang dùng.

## 8. Khi ghép ba cơ chế thành giao thức thực tế

Một giao thức ứng dụng tự thiết kế cần trả lời thêm những câu hỏi mà chương trình ở mục 7 **chưa** giải quyết:

| Câu hỏi | Vì sao quan trọng? | Cách tiếp cận |
| --- | --- | --- |
| Public Ed25519 của Alice đáng tin bằng cách nào? | Nếu attacker thay khóa xác minh, chữ ký của attacker cũng có thể “verify true” | PKI/chứng thư xác thực, pinning, key registry được bảo vệ |
| Public X25519 nào thực sự thuộc phiên Alice ↔ Bob? | X25519 thu shared secret nhưng không xác thực peer | Ký/xác minh transcript hoặc dùng giao thức AKE có xác thực |
| Có phân biệt role, protocol version và thuật toán đã thương lượng không? | Tránh tráo vai trò, context confusion, downgrade | Transcript có version, identities, algorithm IDs, cả hai XDH public keys và dữ liệu ngẫu nhiên phù hợp |
| Khi nào khóa AES đổi? | Giới hạn tác động nếu khóa lộ hoặc gần giới hạn nonce | KDF phân tách chiều và phiên, rekey/rotate theo protocol |
| Nonce GCM được quản lý ra sao? | Reuse nonce với cùng key nguy hiểm nghiêm trọng | Bộ đếm/thiết kế nonce được chứng minh không trùng; tránh để nhiều worker dùng trùng cặp key+nonce |
| Nếu kẻ xấu phát lại ciphertext cũ thì sao? | GCM tag của bản mã cũ vẫn có thể hợp lệ | Sequence number, replay window, session state, thời gian hoặc protocol-level replay checks |
| Metadata nào không bí mật nhưng phải bảo vệ? | Thay header/cấu hình phiên có thể thay ý nghĩa dữ liệu | Dùng `updateAAD(...)` và/hoặc ký transcript theo format xác định |
| Key material trao qua mạng ở định dạng nào? | Raw bytes, public key encoded, protocol framing khác nhau | Chuẩn hóa encoding và parse; `PublicKey.getEncoded()` theo JCA thường dùng X.509 SubjectPublicKeyInfo chứ không mặc định là raw 32 bytes |

### Ví dụ mô hình bắt tay có xác thực (mức thiết kế)

Giả sử Alice và Bob đã có cách **tin cậy Ed25519 identity public keys**. Một mô hình đơn giản để suy nghĩ về cách kết hợp:

```text
Alice sinh X25519 ephemeral keypair A
Bob   sinh X25519 ephemeral keypair B

Xây dựng transcript rõ độ dài/trường:
  protocol-id, version, role Alice/Bob,
  identity IDs, A.public, B.public,
  nonce/algorithm negotiation

Alice ký transcript bằng Ed25519 identity private key
Bob kiểm chữ ký bằng Ed25519 identity public key đã tin cậy
(Nếu cần xác thực hai chiều, Bob cũng ký và Alice xác minh.)

Hai phía thực hiện X25519 A.private x B.public / B.private x A.public
Dẫn xuất AES keys bằng HKDF, ràng buộc transcript/protocol/chiều truyền
Mã hóa payload bằng AES-GCM với nonce không trùng; AAD ràng buộc metadata
Theo dõi sequence number, chống replay và xử lý lỗi xác thực
```

**Đây là bản phác thảo kiến trúc, không phải đặc tả giao thức đã được kiểm chứng.** Từng giao thức thực phải quy định chặt chẽ thứ tự bước, điều kiện xác minh, cách encode không mơ hồ, cơ chế chống downgrade, xử lý lỗi, giới hạn nonce và tính chất forward secrecy. Nếu dùng cho HTTP hoặc kết nối client–server, **TLS 1.3** đã giải quyết nhiều khía cạnh này ở mức giao thức; không nên viết một “TLS tự chế” từ các primitive JCA riêng lẻ.

**Forward secrecy** không tự xuất hiện chỉ vì thấy chữ “X25519”. Nó đòi hỏi cách dùng khóa ephemeral, xác thực phiên và xóa/giới hạn vòng đời private ephemeral đúng protocol. Ed25519/X25519 cũng không được coi là thuật toán **kháng máy tính lượng tử**; nếu bài toán có yêu cầu hậu lượng tử, phải đánh giá giao thức/thuật toán được hỗ trợ phù hợp trong môi trường hiện tại.

## 9. Các lỗi nhầm lẫn phổ biến

1. **“EdDSA mã hóa plaintext bằng private key.”** Sai. EdDSA tạo chữ ký; dữ liệu gốc vẫn có thể đọc nếu không được mã hóa bằng cơ chế khác.
2. **“Verify true nghĩa là chắc chắn đúng người gửi.”** Chưa đủ. Public verification key phải được xác thực/gắn với danh tính kỳ vọng.
3. **“X25519 là Ed25519 chỉ khác tên API.”** Sai. Mục đích, loại key và phép toán khác nhau. Hãy tạo cặp khóa riêng theo đúng algorithm.
4. **“Shared secret chính là thông điệp đã được mã hóa.”** Sai. Shared secret là đầu vào để dẫn xuất khóa; nó không bảo vệ payload nếu không có mã hóa riêng.
5. **“X25519 tự chống man-in-the-middle.”** Sai. Public keys không được xác thực có thể bị tráo.
6. **“HMAC-SHA256/HKDF tự xác thực đối tác.”** Sai. KDF chỉ biến đổi secret/keying material; không ràng buộc danh tính tin cậy nếu protocol không thiết kế điều đó.
7. **“Dùng shared secret trực tiếp làm AES key cho tiện.”** Không nên làm trong thiết kế mới; hãy dùng KDF theo protocol để tách khóa, mục đích, chiều truyền và ngữ cảnh.
8. **“AES-GCM chỉ cần key, dùng nonce cố định được.”** Sai. **Không reuse cặp (key, nonce)**.
9. **“GCM tag là chữ ký số của người gửi.”** Sai. Bất cứ bên nào giữ cùng symmetric key cũng có thể tạo tag hợp lệ.
10. **“Mã hóa GCM đã tự chống phát lại.”** Sai. Ciphertext hợp lệ có thể bị gửi lại; cần replay protection ở mức giao thức.
11. **“Có thể giải mã rồi bỏ qua AEADBadTagException.”** Sai. Nếu xác thực tag thất bại, dữ liệu không đáng tin, không được dùng như plaintext hợp lệ.
12. **“Cứ `Base64` một thông điệp là đã được mã hóa.”** Sai. Base64 là encoding, không giấu thông tin và không tạo xác thực.
13. **“Có thể ký riêng khóa X25519 công khai mà không cần thêm metadata.”** Chưa đủ cho mọi protocol. Cần ràng buộc cả hai key, role, version và ngữ cảnh; tránh key swap hoặc downgrade.
14. **“Chỉ cần dùng JCA primitives là protocol tự an toàn.”** Sai. JCA cung cấp các thuật toán đúng chức năng, còn tính an toàn của phiên còn tùy xác thực, KDF, nonce, transcript, replay, vòng đời khóa, và implement.
15. **“Có thể log tất cả secrets để dễ debug.”** Sai. Giữ private signing keys, private XDH keys, derived keys và shared secrets khỏi log/telemetry; chỉ log trạng thái kiểm thử hoặc metadata không nhạy cảm được cho phép.

## 10. Checklist chọn API đúng

Khi thiết kế một chức năng cần bảo mật:

1. **Cần chứng minh nguồn gốc và phát hiện sửa dữ liệu?** Chọn `Signature.getInstance("Ed25519")` (hoặc Ed448 theo yêu cầu), quản lý signing private key và trusted verifying public key.
2. **Cần đồng thuận bí mật giữa hai bên?** Chọn `KeyPairGenerator.getInstance("X25519")` và `KeyAgreement.getInstance("X25519")`, với cơ chế xác thực peer/public key thích hợp.
3. **Cần khóa AES từ shared secret?** Dẫn xuất qua HKDF và thống nhất salt/info, context và định dạng dữ liệu giữa hai phía.
4. **Cần giữ bí mật plaintext và phát hiện sửa bản mã?** Chọn AEAD như `Cipher.getInstance("AES/GCM/NoPadding")`, chọn key/nonce/tag và AAD đúng contract; bảo đảm nonce độc nhất cho từng key.
5. **Cần giao thức end-to-end?** Xem xét TLS 1.3 hoặc thiết kế được kiểm toán; đảm bảo xác thực bắt tay, format transcript, anti-replay, key separation và error handling.
6. **Đang lưu/đưa key qua mạng?** Dùng encoding và cấu trúc chuẩn; tuyệt đối không gửi private keys và không xem public key “công khai” là “đã được xác thực”.
7. **Cần kiểm thử?** Test chữ ký hợp lệ và thông điệp sửa; XDH hai bên thu secret giống nhau; KDF hai bên thu key giống nhau; GCM decrypt đúng, ciphertext hoặc AAD sửa bị từ chối; test cả trường hợp peer key bị tráo và nonce trùng ở mức protocol.

Không thay đổi cơ chế chữ ký thành mã hóa, hoặc biến một API thành chức năng khác chỉ vì các thuật toán đều dùng toán học đường cong elliptic.

## 11. Tự kiểm tra có đáp án

**Câu 1.** Alice ký một file bằng Ed25519 rồi gửi cả file và chữ ký qua Internet. Người nghe lén có đọc nội dung file được không?

**Đáp án:** **Có**, nếu file không được mã hóa. Ed25519 cho Bob kiểm tra tính xác thực theo public key đáng tin và tính toàn vẹn file, nhưng không che giấu bytes file.

**Câu 2.** Alice và Bob dùng X25519, hai bên cùng tính ra một shared secret. Điều đó đã chứng minh họ thực sự đang nói chuyện với nhau chưa?

**Đáp án:** **Chưa**. X25519 thu secret giữa cặp key được cung cấp; nếu attacker tráo public key, hai phía có thể kết nối với attacker. Cần xác thực peer key/handshake.

**Câu 3.** Vì sao cần HKDF sau X25519?

**Đáp án:** Dẫn xuất từ shared secret ra một hoặc nhiều khóa có độ dài/mục đích/ngữ cảnh xác định và tách vai trò bằng `salt`/`info`. HKDF không thay được xác thực khóa công khai.

**Câu 4.** `Signature.getInstance("Ed25519")` có dùng với một keypair tạo bởi `KeyPairGenerator.getInstance("X25519")` không?

**Đáp án:** **Không**. Đây là hai loại key và hai thuật toán khác mục đích. Dùng Ed25519 keypair cho ký số; X25519 keypair cho key agreement.

**Câu 5.** Có thể dùng một nonce GCM cố định cho mọi lần mã hóa khi key giống nhau không?

**Đáp án:** **Không**. Reuse nonce trong AES-GCM với cùng key là lỗi bảo mật nghiêm trọng; cần nonce strategy bảo đảm độc nhất theo key.

**Câu 6.** Một bản tin AES-GCM giải mã và xác thực tag thành công. Điều đó có tự chứng minh Bob nhận đúng **người gửi có danh tính Alice** không?

**Đáp án:** **Không** nếu chưa có xác thực phiên. Tag chứng minh bên tạo có khóa tương ứng, không chỉ đích danh ai trong các bên có cùng khóa. Phải xác thực key exchange/identity.

**Câu 7.** Kẻ tấn công gửi lại nguyên ciphertext, nonce, tag và AAD từng hợp lệ. AES-GCM tự phát hiện replay không?

**Đáp án:** **Không**. Tag vẫn có thể hợp lệ. Replay cần được phát hiện bằng sequence number, session state hoặc cơ chế của protocol.

**Câu 8.** Trong chương trình demo, nếu sửa message trước khi gọi `Signature.verify` và giữ signature cũ, kết quả là gì?

**Đáp án:** `false` (với dữ liệu sửa đúng như chương trình). Nếu sửa ciphertext+tag trước AES-GCM decrypt, provider trong bài thử ném `AEADBadTagException`.

**Tiêu chí hoàn thành:** Bạn có thể giải thích vai trò riêng của **EdDSA chữ ký**, **XDH trao đổi khóa**, **HKDF dẫn xuất khóa** và **AES-GCM mã hóa có xác thực**; không dùng sai khóa hoặc API; nhận diện rõ các vấn đề còn thiếu là **trust, MITM, nonce, replay và giao thức**.

## 12. Tài liệu chính thức và chuẩn còn giá trị

- [OpenJDK JEP 339 – Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): EdDSA trong Java 15, Ed25519/Ed448 và phạm vi API.
- [OpenJDK JEP 324 – Key Agreement with Curve25519 and Curve448](https://openjdk.org/jeps/324): X25519/X448 cho XDH, khác chữ ký.
- [Java SE 15 – Standard Algorithm Names](https://docs.oracle.com/en/java/javase/15/docs/specs/security/standard-names.html): tên `Signature`, `KeyPairGenerator`, `KeyAgreement`, `Cipher` và `Mac`.
- [Java SE 15 – JDK Providers Documentation](https://docs.oracle.com/en/java/javase/15/security/oracle-providers.html): các triển khai và tham số EdDSA/XDH trong provider tích hợp.
- [Java SE 25 – Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): đối chiếu tên thuật toán vẫn được tài liệu hóa trong Java hiện đại.
- [Java SE 25 – `java.security.Signature`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): cách ký/xác minh và xử lý trạng thái `Signature`.
- [Java SE 25 – `javax.crypto.KeyAgreement`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KeyAgreement.html): `init`, `doPhase`, `generateSecret`.
- [Java SE 25 – `javax.crypto.Cipher`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/Cipher.html): AES-GCM, AAD, `doFinal` và yêu cầu nonce.
- [RFC 8032 – Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): định nghĩa Ed25519 và Ed448.
- [RFC 7748 – Elliptic Curves for Security](https://www.rfc-editor.org/rfc/rfc7748): X25519, X448 và trao đổi khóa.
- [RFC 5869 – HKDF](https://www.rfc-editor.org/rfc/rfc5869): quy tắc Extract/Expand với salt và info.
- [NIST SP 800-38D – Galois/Counter Mode (GCM)](https://csrc.nist.gov/pubs/sp/800/38/d/final): chế độ GCM và yêu cầu an toàn khi chọn IV.

**Ghi nhớ:** **EdDSA ký dữ liệu; XDH thỏa thuận shared secret; HKDF biến bí mật thành khóa; AES-GCM mã hóa và xác thực bản mã.** Chúng có thể được kết hợp, nhưng không thay thế lẫn nhau. Để một kết nối thực sự an toàn cần thêm **trust đối với public key, xác thực handshake, quản lý nonce/khóa và chống replay**.