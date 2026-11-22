# 8.1 Khóa công khai, khóa riêng và quan hệ với mã hóa hoặc chữ ký số

## Mục tiêu học tập

Khi gặp một cặp khóa trong Java (`PublicKey` và `PrivateKey`), cần phân biệt được **ai sở hữu khóa, ai được biết khóa và khóa dùng cho phép toán gì**. Hai thao tác quan trọng nhưng phục vụ các mục tiêu khác nhau:

- **Mã hóa khóa công khai (public-key encryption):** người gửi mã hóa bằng **khóa công khai của người nhận**; người nhận giải mã bằng **khóa riêng tương ứng**. Mục tiêu chính là **tính bí mật**.
- **Chữ ký số (digital signature):** người ký tạo chữ ký bằng **khóa riêng của người ký**; người kiểm tra dùng **khóa công khai tương ứng** để xác minh. Mục tiêu là **tính toàn vẹn và xác thực nguồn gốc theo danh tính đã gắn với khóa**.

Dù đều dùng khóa bất đối xứng, **mã hóa không phải chữ ký**, còn **xác minh chữ ký không phải giải mã thông điệp**. Cụm từ “mã hóa bằng khóa riêng để ký” dễ gây hiểu nhầm và không mô tả đúng các scheme chữ ký hiện đại như RSA-PSS hoặc Ed25519.

Bài học nằm trong chủ đề **Khóa công khai**, tập trung vào vai trò hai loại khóa, quan hệ với mã hóa/chữ ký và cách dùng Java Security API. Các ví dụ chạy trên Java 17+.

## 1. Cặp khóa bất đối xứng thực chất là gì?

**Mật mã đối xứng** như AES sử dụng cùng một khóa bí mật (hoặc khóa có quan hệ trực tiếp) cho mã hóa/giải mã. **Mật mã bất đối xứng** sử dụng một **key pair** gồm:

- `public key`: được phép công bố, phân phối cho các bên cần mã hóa cho chủ sở hữu hoặc xác minh chữ ký của chủ sở hữu.
- `private key`: phải được chủ sở hữu bảo vệ, dùng cho thao tác cần chứng minh quyền kiểm soát khóa hoặc lấy lại bí mật trong scheme tương ứng.

Hai khóa được tạo cùng nhau và **liên hệ toán học**, nhưng trong một thuật toán an toàn với kích thước khóa phù hợp, việc biết public key **không đủ để tính private key trong thực tế**. “Khóa công khai” không có nghĩa có thể tin khóa đó thuộc về người bất kỳ tự xưng; **tính xác thực của liên kết giữa public key và danh tính** là một vấn đề riêng.

Ví dụ RSA dựa trên các tham số như modulus `n`, public exponent `e` và private exponent `d`; khó khăn tính toán liên quan đến cấu trúc RSA giúp bảo vệ private key. Với hệ mật dựa trên đường cong elliptic, cách xây dựng và phép toán khác RSA. Vì thế không nên tự áp dụng công thức hoặc thao tác RSA cho mọi cặp `PublicKey`/`PrivateKey`.

### 1.1 Khóa không tự nói lên mục đích

`PublicKey` và `PrivateKey` là **interface** của Java, không có nghĩa mọi khóa dùng được cho mọi engine:

| Thuật toán/cặp khóa | Mục đích thường gặp | Dịch vụ Java liên quan |
| --- | --- | --- |
| RSA | Mã hóa khóa/ngắn bằng RSA-OAEP; chữ ký với RSA-PSS hoặc scheme được cho phép | `Cipher`, `Signature` |
| Ed25519 | **Chữ ký số** EdDSA | `Signature` (`Ed25519`) |
| X25519 | **Thỏa thuận khóa** (key agreement), tạo bí mật chung rồi đưa qua KDF | `KeyAgreement` (`X25519`) |
| EC với ECDSA | Chữ ký số bằng thuật toán phù hợp | `Signature` (ví dụ `SHA256withECDSA`) |
| EC với ECDH | Thỏa thuận khóa, dùng khóa riêng bên mình và khóa công khai bên kia | `KeyAgreement` |

**Ed25519 không phải thuật toán mã hóa dữ liệu; X25519 không phải thuật toán chữ ký.** Đối với RSA, cùng kiểu khóa có thể hỗ trợ hai loại thao tác khi provider và chính sách cho phép, nhưng ứng dụng thực tế thường sử dụng **các cặp khóa riêng biệt cho mã hóa và ký** để quản lý mục đích, quyền và thời gian sống của khóa.

## 2. Quan hệ giữa public/private key và mã hóa

Giả sử **Alice** muốn gửi bí mật cho **Bob**. Bob tạo cặp khóa `(Bob.public, Bob.private)` và cung cấp public key **đã được xác thực thuộc về Bob** cho Alice.

```text
Alice (người gửi)                              Bob (người nhận)
-----------------                              ----------------
Thông điệp plaintext
        |
        | Encrypt(Bob.public, plaintext)
        v
   Ciphertext  ------------------------------->  Ciphertext
                                                      |
                                             Decrypt(Bob.private)
                                                      |
                                                      v
                                                   Plaintext
```

Với scheme mã hóa khóa công khai đúng và tham số phù hợp:

1. **Bên gửi không cần biết khóa riêng của Bob**; chỉ cần biết khóa công khai đúng của Bob.
2. **Chỉ Bob (hoặc bên nào đang nắm được private key tương ứng) mới có thể giải mã** trong mô hình an toàn của scheme.
3. Ai có được Bob.public cũng có thể tạo ciphertext gửi cho Bob. Vì vậy **mã hóa bằng khóa công khai của Bob không tự xác thực người gửi là Alice**.
4. Nếu kẻ tấn công thay Bob.public bằng khóa của mình, Alice có thể mã hóa cho kẻ tấn công. Cần xác minh nguồn gốc public key qua chứng chỉ, fingerprint đã đối chiếu, registry đáng tin hoặc một giao thức phân phối khóa được xác thực.

### 2.1 Mã hóa RSA phải dùng scheme an toàn

RSA là phép toán trên các số nguyên có cấu trúc toán học; **không dùng “raw RSA”**. Với JCA, ví dụ phổ biến là **RSAES-OAEP**:

```java
// Minh họa trong phương thức có xử lý ngoại lệ và tham số phù hợp:
Cipher cipher = Cipher.getInstance(
        "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
```

Chữ `ECB` trong tên transformation RSA của JCE là quy ước cú pháp lịch sử của engine, **không có nghĩa RSA đang mã hóa các khối AES theo ECB**. Scheme phải nêu **OAEP hash, MGF1 hash và label/PSource** bằng tham số phù hợp để hai bên tương thích. Đặc biệt đừng đoán rằng `OAEPWithSHA-256AndMGF1Padding` tự đặt mọi MGF1 digest thành SHA-256 trên mọi provider; ví dụ runnable bên dưới truyền `OAEPParameterSpec` rõ ràng.

**Giới hạn độ dài:** RSA-OAEP chỉ mã hóa plaintext ngắn. Với RSA modulus 2048 bit (`k = 256` byte) và OAEP dùng SHA-256 (`hLen = 32` byte), giới hạn thông điệp là:

\[
mLen \leq k - 2hLen - 2 = 256 - 64 - 2 = 190\ \text{byte}.
\]

Không thể dùng lời gọi RSA-OAEP để mã hóa nguyên file lớn theo cách chia thành nhiều “block RSA” tùy tiện. Thiết kế thực tế thường dùng **hybrid encryption**: sinh khóa AES ngẫu nhiên, mã hóa dữ liệu bằng **AES-GCM**, rồi bảo vệ khóa AES bằng một cơ chế mã hóa/đóng gói khóa bất đối xứng phù hợp (ví dụ RSA-OAEP trong hệ thống áp dụng RSA). Phía nhận dùng private key lấy lại khóa AES để giải mã dữ liệu. Phải quy định format, nonce, tag, key ID và các metadata được xác thực.

### 2.2 Mã hóa cần gì để an toàn ngoài key pair?

- Public key người nhận **phải đúng người nhận**; private key người nhận được bảo vệ.
- Phải lựa chọn **scheme và tham số** an toàn thay vì `Cipher.getInstance("RSA")` rồi để provider quyết định padding.
- Một bản mã của scheme mã hóa bất đối xứng **không đồng nghĩa bằng chứng ai đã gửi**; khi cần tính xác thực nguồn, phải thêm chữ ký/giao thức có xác thực.
- Nếu dùng AES-GCM trong hybrid encryption, phải bảo đảm nonce duy nhất cho mỗi khóa AES, xử lý authentication tag và ràng buộc context/AAD cần thiết.
- Encryption alone không cung cấp cơ chế **chống replay**: bản mã hợp lệ có thể bị gửi lại nếu protocol không theo dõi bản ghi/thứ tự/nonce ứng dụng.

## 3. Quan hệ giữa public/private key và chữ ký số

Lần này Alice muốn Bob biết thông điệp đúng là do **người giữ Alice.private** ký và nội dung không bị thay đổi.

```text
Alice (người ký)                                  Bob (người kiểm tra)
---------------                                  ---------------------
Thông điệp M
     |
     | Sign(Alice.private, M)
     v
Chữ ký S và M ------------------------------------> M, S
                                                     |
                                          Verify(Alice.public, M, S)
                                                     |
                                               true / false
```

Các bước quan trọng:

1. Alice sở hữu private key phù hợp với thuật toán chữ ký và tạo `signature` trên **dữ liệu chính xác** cần chứng thực.
2. Bob đã biết public key **được gắn đáng tin với danh tính Alice**, nhận thông điệp và chữ ký, rồi gọi `verify(public, message, signature)`.
3. Nếu kiểm tra thành công, chữ ký phù hợp với **public key được cung cấp** và các byte dữ liệu đã kiểm tra. Để kết luận “Alice đã ký”, Bob còn phải **xác thực public key thật sự thuộc Alice**.
4. Thay đổi message, context quan trọng hoặc chữ ký sẽ làm verification thất bại (với scheme an toàn và triển khai đúng).
5. Chữ ký số **không mã hóa thông điệp**. Bất cứ ai đọc được message vẫn đọc được nó, kể cả chữ ký hợp lệ.

Chữ ký cung cấp nền tảng cho **toàn vẹn**, **xác thực nguồn gốc**, và hỗ trợ **chống chối bỏ (non-repudiation)** khi quản trị khóa, định danh, chứng cứ và chính sách phù hợp. Nó **không tự** cung cấp tính bí mật, bảo đảm người ký là người nào ngoài danh tính đã xác thực, hay chống gửi lại thông điệp hợp lệ.

### 3.1 Vì sao ký không phải “mã hóa bằng khóa riêng”?

Cách nói “lấy private key mã hóa, lấy public key giải mã” là hình ảnh đơn giản hóa từ một số phép toán RSA và **sai cho chữ ký số hiện đại**:

- RSA-PSS là scheme **chữ ký**, có băm, encoding, salt và kiểm tra cấu trúc được xác định; API `Signature.sign()` tạo ra signature, `Signature.verify()` kiểm tra.
- `Ed25519` ký và xác minh bằng phép toán trên đường cong; **không có thao tác “giải mã chữ ký thành thông điệp”**.
- Phần lớn scheme chữ ký kiểm tra chữ ký dựa trên **message gốc hoặc digest được định nghĩa bởi scheme**; không dùng `Cipher` với `ENCRYPT_MODE` và private key thay cho `Signature`.

Trong Java hãy sử dụng đúng engine `Signature`; với RSA-PSS nên thống nhất digest, MGF1, salt length và trailer field, tránh phụ thuộc tham số mặc định của provider.

### 3.2 Mã hóa và chữ ký có thể dùng đồng thời

Khi Alice gửi bí mật **và** muốn Bob xác minh Alice, giao thức phải có cả bảo vệ **bí mật** và **xác thực nguồn**:

```text
Bí mật của Bob:        Encrypt(Bob.public, ...)
Danh tính của Alice:   Sign(Alice.private, dữ liệu/ngữ cảnh quy định)
```

Một giao thức tổng hợp phải nêu rõ **ký dữ liệu nào** (plaintext, ciphertext hoặc envelope), xử lý danh tính và metadata thế nào, thứ tự hoạt động, các trường AAD/signature, chống replay và cách thông báo lỗi. Không tự tùy tiện nối hai primitive rồi khẳng định có mọi thuộc tính an toàn. Các chuẩn triển khai như CMS/JWE/JWS/TLS có mô hình và chi tiết bảo mật riêng; chọn chuẩn thích hợp cho bài toán thay vì tạo protocol từ phỏng đoán.

## 4. So sánh trực tiếp hai thao tác

| Câu hỏi | Mã hóa bất đối xứng | Chữ ký số |
| --- | --- | --- |
| Mục tiêu | Giữ **bí mật** nội dung/khóa phiên | Chứng minh **tính toàn vẹn và nguồn gốc theo khóa đã xác thực** |
| Ai dùng public key và để làm gì? | **Người gửi** dùng public key **của người nhận** để mã hóa | **Người kiểm tra** dùng public key **của người ký** để verify |
| Ai dùng private key và để làm gì? | **Người nhận** dùng private key của mình để giải mã | **Người ký** dùng private key của mình để sign |
| Đầu ra | Ciphertext (và metadata cần thiết) | Signature (thường gửi cùng message) |
| Message có đọc được công khai? | Không, nếu scheme/khóa/format an toàn | Có, nếu message không được mã hóa riêng |
| Bảo đảm danh tính người gửi? | Không, chỉ vì ai cũng dùng được public key người nhận | Chỉ khi public key verifier được **gắn đáng tin với danh tính người ký** |
| Chống replay? | Không tự có | Không tự có |
| Java API | `Cipher` với scheme mã hóa như RSA-OAEP | `Signature` với scheme ký như RSA-PSS/Ed25519 |

**Câu nhớ nhanh:** *Mã hóa cho Bob thì dùng public key của Bob; ký với tư cách Alice thì dùng private key của Alice.* Khi nhận, Bob dùng **private key của Bob** để giải mã và **public key của Alice** để kiểm tra chữ ký.

## 5. Java 17: mô hình `KeyPair`, `PublicKey`, `PrivateKey`

Các API liên quan nằm trong `java.security`, `java.security.spec` và `javax.crypto`:

| API | Công dụng đúng |
| --- | --- |
| `KeyPairGenerator` | Tạo cặp khóa mới theo thuật toán (ví dụ `RSA`, `Ed25519`, `X25519`). |
| `KeyPair` | Giữ cặp khóa; `getPublic()` và `getPrivate()` trả các interface tương ứng. |
| `PublicKey` / `PrivateKey` | Đối tượng khóa cho `Cipher`, `Signature`, `KeyAgreement` tùy loại thuật toán. |
| `Cipher` | Mã hóa/giải mã theo transformation như `RSA/ECB/OAEPWithSHA-256AndMGF1Padding`. |
| `Signature` | `initSign(private)`, `update`, `sign`; hoặc `initVerify(public)`, `update`, `verify`. |
| `KeyAgreement` | Thỏa thuận bí mật chung, ví dụ với X25519 hoặc ECDH; **không giống encrypt/verify**. |
| `KeyFactory` | Tái tạo đối tượng khóa từ `KeySpec` như X.509 public key hoặc PKCS#8 private key. |
| `KeyStore` / KMS / HSM | Lưu trữ hoặc truy xuất khóa theo cơ chế đã được bảo vệ; có thể dùng private key **không xuất được**. |

`KeyPairGenerator.getInstance("RSA")` chỉ xác định thuật toán tạo cặp khóa. Muốn dùng cặp khóa ấy cho **mã hóa** thì gọi `Cipher` với RSA-OAEP; muốn dùng cho **chữ ký** thì gọi `Signature` với RSA-PSS. Không dùng `KeyPairGenerator` thay cho phép mã hóa/ký.

Có thể tạo một cặp RSA minh họa như sau:

```java
// Đoạn minh họa trong phương thức có xử lý checked exception:
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(2048);
KeyPair pair = generator.generateKeyPair();
PublicKey publicKey = pair.getPublic();
PrivateKey privateKey = pair.getPrivate();
```

Số bit RSA 2048 ở đây để bài thực hành nhanh và đầu ra dễ kiểm tra; hệ thống thực tế chọn kích thước khóa, vòng đời và bảo vệ khóa theo **chính sách bảo mật áp dụng** (chẳng hạn RSA 3072 khi yêu cầu độ an toàn dài hạn cao hơn). Không chỉ chọn bit length rồi bỏ qua scheme, provider và chu kỳ luân chuyển.

## 6. Ví dụ Java 17+ hoàn chỉnh: RSA-OAEP và RSA-PSS

Chương trình sau dùng **hai cặp RSA riêng biệt** để làm rõ hai vai trò:

- `recipient`: public key mã hóa, private key giải mã.
- `signer`: private key ký, public key xác minh.

Nó cũng thiết lập OAEP **SHA-256 + MGF1(SHA-256)** và PSS **SHA-256 + MGF1(SHA-256), salt 32 byte, trailer 1** một cách tường minh. Việc thiết lập tham số nhất quán giúp tránh sai khác do default của provider. Tạo file **`AsymmetricRolesDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class AsymmetricRolesDemo {
    private static final OAEPParameterSpec OAEP =
            new OAEPParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                    PSource.PSpecified.DEFAULT);

    private static final PSSParameterSpec PSS =
            new PSSParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                    32, 1);

    private static byte[] encryptFor(PublicKey recipient, byte[] data)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        cipher.init(Cipher.ENCRYPT_MODE, recipient, OAEP);
        return cipher.doFinal(data);
    }

    private static byte[] decryptWith(PrivateKey recipient, byte[] ciphertext)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        cipher.init(Cipher.DECRYPT_MODE, recipient, OAEP);
        return cipher.doFinal(ciphertext);
    }

    private static byte[] signWith(PrivateKey signer, byte[] data)
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance("RSASSA-PSS");
        signature.setParameter(PSS);
        signature.initSign(signer);
        signature.update(data);
        return signature.sign();
    }

    private static boolean verifyWith(
            PublicKey signer, byte[] data, byte[] signed)
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance("RSASSA-PSS");
        signature.setParameter(PSS);
        signature.initVerify(signer);
        signature.update(data);
        return signature.verify(signed);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair recipient = generator.generateKeyPair();
        KeyPair signer = generator.generateKeyPair();

        byte[] message = "Hello public-key crypto"
                .getBytes(StandardCharsets.UTF_8);

        byte[] encrypted = encryptFor(recipient.getPublic(), message);
        byte[] recovered = decryptWith(recipient.getPrivate(), encrypted);
        System.out.println("Decryption matches: " +
                Arrays.equals(message, recovered));

        byte[] signature = signWith(signer.getPrivate(), message);
        System.out.println("Signature valid: " +
                verifyWith(signer.getPublic(), message, signature));

        byte[] changed = message.clone();
        changed[0] ^= 1;
        System.out.println("Modified message valid: " +
                verifyWith(signer.getPublic(), changed, signature));

        System.out.println("RSA ciphertext bytes: " + encrypted.length);
        System.out.println("RSA signature bytes: " + signature.length);
    }
}
```

Biên dịch và chạy bằng JDK 17+ có provider hỗ trợ OAEP/PSS với tham số đã dùng:

```bash
javac --release 17 AsymmetricRolesDemo.java
java AsymmetricRolesDemo
```

**Stdout** (các byte ciphertext và chữ ký thay đổi giữa các lần chạy vì có ngẫu nhiên, nhưng các dòng sau vẫn như nhau):

```text
Decryption matches: true
Signature valid: true
Modified message valid: false
RSA ciphertext bytes: 256
RSA signature bytes: 256
```

Giải thích chi tiết:

1. `recipient.getPublic()` được truyền vào `Cipher.ENCRYPT_MODE`; **chỉ** `recipient.getPrivate()` tương ứng mới thực hiện được `Cipher.DECRYPT_MODE` của bản ghi trong demo.
2. `signer.getPrivate()` được truyền vào `Signature.initSign`, còn `signer.getPublic()` vào `Signature.initVerify`. Code không dùng `Cipher` để ký.
3. `Signature.update(message)` cung cấp **chính xác byte** của thông điệp cho scheme ký; PSS thực hiện hashing/encoding nội bộ theo bộ tham số đã chỉ định. Không cần tự băm thông điệp rồi đưa digest vào `update` như thể đó là message gốc.
4. Đổi 1 byte thông điệp khiến `verify()` trả `false`; nếu dùng **public key của cặp khác** cũng không được xem là chữ ký hợp lệ.
5. RSA-2048 có modulus dài 256 byte, nên RSA-OAEP tạo ciphertext **256 byte**, chữ ký RSA-PSS cũng dài **256 byte**. Kích thước này phụ thuộc modulus, **không** phụ thuộc độ dài message ngắn đã chọn.
6. Hai key pair là **riêng biệt** dù đều có thuật toán RSA. Ở production cần ràng buộc mỗi khóa với identity, purpose, key usage và metadata; không mặc định mọi RSA key được phép dùng cho mọi mục đích.
7. Tên `RSASSA-PSS` và transformation OAEP có thể yêu cầu provider phù hợp. Mã chạy được trên môi trường hỗ trợ các scheme/tham số đã yêu cầu; tên có trong danh mục chuẩn không có nghĩa mọi Java SE implementation hỗ trợ mọi tổ hợp. Hãy kiểm tra JDK/provider mục tiêu.

Đây là demo **in-memory**: chương trình sinh khóa mới mỗi lần chạy và không có bên giao tiếp qua mạng. Để đưa vào dịch vụ thực, cần một cơ chế phân phối public key có xác thực, kho khóa riêng an toàn, định dạng message/signature/ciphertext có phiên bản, tham số và xử lý lỗi rõ ràng.

## 7. Lưu public key, bảo vệ private key và kiểm tra danh tính

### 7.1 Public key có thể công khai nhưng phải xác thực

Một public key chỉ nói được rằng **khóa đó có quan hệ toán học với private key nào đó**, chưa tự chứng minh thuộc Alice hay Bob. Các cách xây dựng liên kết danh tính:

- **X.509 certificate**: chứng chỉ chứa public key và dữ liệu chủ thể, được issuer ký; bên kiểm tra phải xác thực chuỗi tin cậy, thời hạn, tên/định danh, key usage/extended key usage, thuật toán và chính sách thu hồi khi áp dụng.
- **Fingerprint hoặc public key pinning**: đối chiếu trước qua kênh đáng tin, chú ý quy trình cập nhật khóa.
- **Registry do ứng dụng quản lý đáng tin**: tra `key_id` cùng chủ sở hữu, trạng thái và purpose; không chọn khóa dựa trên ID do đầu vào chưa xác thực tự khai.

**Xác minh chữ ký thành công với khóa do attacker cung cấp** không chứng minh attacker là Alice. **Mã hóa với public key của attacker bị tráo** không bảo đảm chỉ Bob đọc được dữ liệu.

### 7.2 Encoding/format của khóa trong Java

Khi public/private key có thể xuất ra dạng byte, Java thường dùng:

- **X.509 SubjectPublicKeyInfo (SPKI)** cho public key, thường là `PublicKey.getFormat() == "X.509"`.
- **PKCS#8 PrivateKeyInfo** cho private key, thường là `PrivateKey.getFormat() == "PKCS#8"` nếu private key xuất được.

Ví dụ minh họa **bên trong phương thức** sau khi đã có `pair`:

```java
byte[] publicEncoded = pair.getPublic().getEncoded();
java.security.KeyFactory factory =
        java.security.KeyFactory.getInstance("RSA");
java.security.PublicKey publicAgain = factory.generatePublic(
        new java.security.spec.X509EncodedKeySpec(publicEncoded));
```

Không bao giờ coi việc một byte array có định dạng đúng là đã được **chứng thực danh tính**. Chuỗi PEM chỉ là cách đóng gói Base64/text; public key thường chia sẻ được, **private key không được đưa vào log, source code, repository hoặc API công khai**. Khóa riêng thuộc HSM/KMS có thể **không xuất được** (`getEncoded()` trả `null`), dù object key vẫn dùng được với provider thích hợp.

### 7.3 Quản lý vòng đời khóa

Thiết kế cần gồm: tạo khóa bằng RNG phù hợp, giới hạn quyền sử dụng private key, cách sao lưu/khôi phục an toàn, phân loại khóa ký và khóa giải mã, xoay khóa, lưu public key/chứng chỉ lịch sử để kiểm tra chữ ký cũ, thu hồi khóa khi có sự cố và ghi `key_id`/algorithm ID trong định dạng dữ liệu. Không hủy private key giải mã các ciphertext cũ khi vẫn cần đọc chúng; ngược lại, việc giữ private key cũ quá lâu cũng làm tăng rủi ro.

Khi keypair dùng để ký bị lộ, kẻ tấn công có thể tạo chữ ký mới; không thể chỉ chạy `verify` rồi suy ra chữ ký nào được phát hành trước khi khóa bị lộ nếu thiếu timestamp, audit log, revocation và chính sách tin cậy.

## 8. Kết nối với key agreement và hybrid encryption

Một cặp `PrivateKey`/`PublicKey` còn có thể dùng cho **key agreement**, không thuộc trực tiếp hai thao tác trên. Ví dụ X25519:

```text
Alice.private + Bob.public    ---> shared secret
Bob.private   + Alice.public  ---> cùng shared secret
```

Kết quả thỏa thuận được đưa qua **KDF phù hợp** để sinh key cho AEAD. Không xem shared secret thô là AES key ngay khi chưa được đặc tả. Một phép thỏa thuận khóa không xác thực public key của peer có thể chịu **man-in-the-middle**; cần chữ ký/chứng chỉ hoặc giao thức xác thực thích hợp. Trong Java, engine liên quan là `KeyAgreement`, không phải `Signature.verify` hoặc `Cipher.decrypt`.

Ba pattern thường gặp:

| Bài toán | Primitive chủ đạo | Đầu ra cần dùng |
| --- | --- | --- |
| Chỉ cần gửi một bí mật cho public key người nhận | Public-key encryption hoặc hybrid encryption có xác thực | Ciphertext người nhận giải mã được |
| Cần ai cũng kiểm tra nguồn gốc tài liệu | Digital signature | Message + signature + public key/chứng chỉ đáng tin |
| Hai bên lập kênh truyền bí mật | Authenticated key agreement + KDF + AEAD | Khóa phiên, ciphertext/tag và trạng thái giao thức |

**Không tự chọn một phép toán “đối xứng” tưởng tượng giữa public/private key cho mọi mục tiêu.** Các thuật toán khác nhau có chức năng, định dạng, bảo đảm an toàn và engine Java riêng.

## 9. Sai lầm thường gặp và cách sửa

| Nhận định/sự cố | Vấn đề | Cách sửa |
| --- | --- | --- |
| “Khóa công khai của Alice có thể dùng để giải mã mọi thứ Alice ký.” | Chữ ký số không phải ciphertext của message. | Dùng `Signature.verify(Alice.public, message, signature)`. |
| “Mã hóa bằng Bob.public tức là Alice đã chứng minh mình gửi.” | Bất kỳ ai biết Bob.public cũng mã hóa được cho Bob. | Thêm xác thực nguồn bằng scheme/giao thức phù hợp. |
| “Đã `verify` thành công thì message bí mật.” | Signature không bảo vệ confidentiality. | Mã hóa riêng nếu có dữ liệu cần giấu. |
| “Public key nào ghi tên Alice cũng dùng được.” | Khóa không tự ràng buộc danh tính. | Xác thực chứng chỉ/pinning/trust registry và key usage. |
| “Dùng `Cipher` với private key là đủ cho chữ ký RSA.” | Đã bỏ qua security scheme/padding và API chữ ký. | Dùng `Signature` với RSA-PSS hoặc scheme được phê duyệt. |
| “`Cipher.getInstance("RSA")` là RSA an toàn.” | Provider có thể áp padding mặc định không như mong muốn. | Yêu cầu RSA-OAEP và tham số hash/MGF1 rõ ràng. |
| “RSA mã hóa được dữ liệu dài bất kỳ.” | RSA-OAEP có giới hạn message phụ thuộc modulus/hash. | Dùng hybrid encryption để bảo vệ khóa AES, mã hóa payload bằng AEAD. |
| “Cùng cặp khóa nên dùng cho cả ký và giải mã cho tiện.” | Trộn mục đích/chu kỳ rủi ro và quyền truy cập. | Tách key pair khi triển khai production. |
| `InvalidKeyException` khi gọi `Cipher`/`Signature`. | Dùng sai loại public/private key, size hoặc key usage/provider. | Kiểm tra vai trò key, algorithm, chính sách key và tham số `init`. |
| `Signature.verify()` trả `false` | Message, public key, signature hoặc PSS params không khớp. | Kiểm tra byte encoding, bộ tham số và khóa nguồn đáng tin. |
| `BadPaddingException` khi giải mã OAEP | Ciphertext/key/OAEP params không hợp lệ. | Từ chối bản ghi; không thử lại bằng raw RSA hay padding yếu. |
| “Chữ ký đúng nên không thể gửi lại thông điệp đó.” | Chữ ký không chống replay. | Thêm nonce/sequence/timestamp/expiry gắn trong dữ liệu đã ký và trạng thái kiểm tra. |

## 10. Câu hỏi tự kiểm tra

**1. Alice muốn Bob là người duy nhất đọc được thông điệp. Alice dùng khóa nào?**  
Public key **đã xác thực của Bob** để mã hóa theo scheme phù hợp; Bob dùng private key của Bob để giải mã.

**2. Bob muốn xác minh thông điệp do Alice ký. Bob dùng khóa nào?**  
Public key **đã xác thực của Alice** cùng message và signature. Alice dùng private key của Alice để ký.

**3. Một signature hợp lệ có đảm bảo message không bị ai đọc được không?**  
Không. Chữ ký kiểm tra tính toàn vẹn và nguồn gốc theo key; cần mã hóa để có confidentiality.

**4. Có public key nhưng không biết chủ sở hữu thực thì có thể khẳng định người gửi là ai không?**  
Không. Phải xác thực **liên kết key → identity** qua cơ chế đáng tin.

**5. Vì sao RSA-OAEP không nên mã hóa trực tiếp file dài?**  
Giới hạn dữ liệu thấp (ví dụ RSA-2048 + OAEP SHA-256 tối đa **190 byte**). Sử dụng hybrid encryption/AEAD cho payload lớn.

**6. Ed25519 và X25519 có dùng thay nhau được không?**  
Không. Ed25519 là scheme chữ ký, X25519 là key agreement; tên gần giống nhưng loại phép toán và mục tiêu khác nhau.

**7. Nếu có cả chữ ký và mã hóa, phải dùng một cặp khóa hay hai?**  
Một giao thức có thể dùng nhiều thuật toán/khóa; thực hành quản lý khóa thường **tách key pair theo chức năng** và xác thực public key của cả bên gửi/bên nhận theo vai trò.

## Tài liệu chuẩn

- [Java SE 17 — `KeyPairGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html): tạo cặp khóa và tham số sinh khóa.
- [Java SE 17 — `Signature`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): `initSign`, `initVerify`, `update`, `sign`, `verify`.
- [Java SE 17 — `Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): mã hóa/giải mã, transformation và cách `init`.
- [Java SE 17 — `OAEPParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/OAEPParameterSpec.html): OAEP hash, MGF1 và PSource; không dựa vào default SHA-1.
- [Java SE 17 — `PSSParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html): digest, MGF, salt length và trailer field.
- [Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên `RSA`, `RSASSA-PSS`, `Ed25519`, `X25519` và phạm vi tên/triển khai.
- [RFC 8017 — PKCS #1: RSA Cryptography Specifications v2.2](https://www.rfc-editor.org/rfc/rfc8017): RSAES-OAEP, RSASSA-PSS và giới hạn độ dài message.
- [NIST — Glossary: Digital Signature](https://csrc.nist.gov/glossary/term/digital_signature): tính toàn vẹn/xác thực, hỗ trợ non-repudiation; không cung cấp confidentiality.
- [NIST — Glossary: Public Key](https://csrc.nist.gov/glossary/term/public_key): public key dùng để xác minh chữ ký, mã hóa khóa hoặc tham gia key agreement tùy scheme.

**Điều cần nhớ:** **Public key dùng cho thao tác mà người khác được phép thực hiện; private key dùng cho thao tác chỉ chủ sở hữu được quyền thực hiện.** Trong mã hóa là *encrypt với public key người nhận → decrypt với private key người nhận*; trong chữ ký là *sign với private key người ký → verify với public key người ký*. Hai quan hệ ấy phục vụ **mục tiêu bảo mật khác nhau**, nên phải đi kèm xác thực danh tính, scheme, tham số và quản lý khóa đúng.
