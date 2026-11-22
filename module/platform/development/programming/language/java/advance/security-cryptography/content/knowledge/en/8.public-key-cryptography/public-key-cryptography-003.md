# 8.3 RSA, EC, EdDSA và XDH: phân biệt mục đích của từng họ thuật toán

## Mục tiêu

Sau bài này, bạn sẽ phân biệt **mã hóa khóa công khai**, **chữ ký số** và **thỏa thuận khóa**; biết RSA, EC, EdDSA và XDH cung cấp chức năng gì; chọn đúng engine của Java Cryptography Architecture (JCA/JCE) như `Cipher`, `Signature` và `KeyAgreement`; sử dụng tên thuật toán/curve đúng trong Java 17+; và hiểu vì sao không được lấy khóa hoặc kết quả của một họ để thay thế tùy tiện cho họ khác.

Bốn tên **không cùng cấp độ trừu tượng**: `RSA` là một họ thuật toán dùng cho mã hóa hoặc chữ ký tùy scheme; `EC` là tên tổng quát của **kiểu khóa đường cong elliptic cổ điển** dùng trong ECDSA/ECDH; `EdDSA` là một **họ chữ ký số**; còn `XDH` là một **họ thỏa thuận khóa Diffie–Hellman** dùng đường cong dạng Montgomery. Nhầm lẫn này là nguyên nhân của nhiều lỗi `NoSuchAlgorithmException`, `InvalidKeyException` và thiết kế giao thức thiếu bước xác thực.

## 1. Trước tiên: ba nhiệm vụ của mật mã khóa công khai

Hệ mật mã bất đối xứng dùng **public key** (có thể phân phối) và **private key** (phải bảo vệ). Dù đều có cặp khóa, ba thao tác sau hoàn toàn khác nhau:

| Mục đích | Thao tác | Khóa/giá trị đi vào | Đầu ra | Bảo đảm được thiết kế để cung cấp |
| --- | --- | --- | --- | --- |
| **Mã hóa khóa công khai** | Người gửi mã hóa bằng public key của bên nhận; bên nhận giải mã bằng private key | Public/private key tương ứng, plaintext | Ciphertext | Chỉ chủ private key đúng có thể đọc; cần scheme mã hóa an toàn |
| **Chữ ký số** | Người ký dùng private key tạo chữ ký; bất kỳ bên tin cậy public key có thể verify | Private/public key, thông điệp | Signature bytes và kết quả verify | Tính toàn vẹn và sự xác thực của người sở hữu private key |
| **Thỏa thuận khóa** | Hai bên dùng private key của mình và public key của đối phương để tính shared secret | Hai cặp khóa được tạo phù hợp | Hai bên nhận cùng shared secret | Cơ sở để tạo khóa phiên; **chưa tự xác thực danh tính hoặc mã hóa dữ liệu** |

`Signature` không phải là phép “mã hóa dữ liệu bằng private key”; ngược lại, RSA-OAEP không phải chữ ký. `KeyAgreement` không có API “ký” và cũng không biến thông điệp thành ciphertext. Một public key chỉ có giá trị bảo mật khi **được gắn đúng với danh tính của bên còn lại** (certificate, pinning, trust store, chữ ký bắt tay, hoặc kênh xác thực thích hợp).

### Bảng chọn nhanh RSA, EC, EdDSA, XDH

| Họ / tên | Vai trò tiêu biểu | Java engine | Tên Java thông dụng | Không nên hiểu thành |
| --- | --- | --- | --- | --- |
| **RSA** | Mã hóa khóa/dữ liệu nhỏ qua **RSA-OAEP**; chữ ký **RSA-PSS** | `Cipher`, `Signature` | `RSA` cho `KeyPairGenerator`; `RSA/ECB/OAEPPadding`; `RSASSA-PSS` | “RSA” mặc nhiên chỉ là mã hóa, hoặc chữ ký là decrypt |
| **EC** | **ECDSA** (chữ ký) và **ECDH** (thỏa thuận khóa) trên các đường cong EC phù hợp | `Signature`, `KeyAgreement` | `EC`, `SHA256withECDSA`, `ECDH`, `secp256r1` | Một thuật toán tên `EC` làm mọi việc |
| **EdDSA** | Chữ ký số hiện đại | `Signature` | `Ed25519`, `Ed448`; dạng tổng quát `EdDSA` | Khóa mã hóa hay khóa `KeyAgreement` |
| **XDH** | Thỏa thuận khóa DH hiện đại | `KeyAgreement` | `X25519`, `X448`; dạng tổng quát `XDH` | Thuật toán ký số hoặc hàm mã hóa `Cipher` |

Tên trong bảng thuộc các engine khác nhau: `KeyPairGenerator.getInstance("EC")` tạo khóa, `Signature.getInstance("SHA256withECDSA")` dùng khóa EC để ký, còn `KeyAgreement.getInstance("ECDH")` dùng khóa EC để thỏa thuận. Java không có một lệnh `getInstance("EC")` chung dùng cho mọi thao tác.

## 2. RSA: một họ có thể dùng cả mã hóa lẫn chữ ký

### 2.1 RSA-OAEP: mã hóa cho người giữ private key

RSA công khai một modulus `n` và số mũ công khai `e`; private key chứa các thông số bí mật cần thiết. Các phép toán RSA nguyên thủy không đủ an toàn khi sử dụng trực tiếp. Khi cần **mã hóa bằng RSA** trong ứng dụng hiện đại, chọn scheme có padding an toàn như **RSAES-OAEP** và chỉ dùng nó để mã hóa **nội dung nhỏ hoặc khóa phiên**, sau đó mã hóa dữ liệu lớn bằng AEAD như AES-GCM.

Cặp tên Java ví dụ:

```java
Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
OAEPParameterSpec params = new OAEPParameterSpec(
        "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
        PSource.PSpecified.DEFAULT);
cipher.init(Cipher.ENCRYPT_MODE, recipientPublicKey, params);
byte[] ciphertext = cipher.doFinal(plaintext);
```

Đây là **snippet minh họa nằm trong phương thức**, chưa phải chương trình độc lập. Nó giả định có `recipientPublicKey` và `plaintext`, và phải xử lý ngoại lệ từ `Cipher.getInstance`/`init`/`doFinal`. Trong Java, chuỗi `RSA/ECB/OAEPPadding` có từ `ECB` vì cú pháp transformation lịch sử; đây **không phải lời khuyên dùng ECB mode của AES**. Quan trọng là **OAEP** và các tham số digest/MGF.

**Tránh sự mơ hồ tham số OAEP**: chỉ ghi `OAEPWithSHA-256AndMGF1Padding` trong transformation nhưng không kiểm soát MGF1 digest có thể làm các môi trường không tương thích. Khai báo `OAEPParameterSpec` rõ ràng (trong ví dụ, digest chính SHA-256 và digest MGF1 cũng SHA-256), rồi thống nhất đúng bộ tham số với bên nhận.

RSA-OAEP giới hạn số byte plaintext: với modulus dài `k` byte và digest dài `hLen` byte, giới hạn là **`k - 2*hLen - 2`**. RSA 2048 bit dùng SHA-256 cho `k=256` và `hLen=32`, nên tối đa **190 byte** mỗi thao tác OAEP. **Không** chia tệp thành nhiều khối rồi tự mã hóa từng khối RSA. Thay vào đó, sinh một khóa AES ngẫu nhiên, mã hóa dữ liệu bằng AES-GCM và dùng RSA-OAEP bảo vệ khóa AES trong envelope có format rõ ràng.

### 2.2 RSA-PSS: chữ ký số

Để ký, dùng engine `Signature` với scheme **RSASSA-PSS**, tham số được khai báo rõ. Ví dụ dùng hash SHA-256, MGF1 với SHA-256, salt dài 32 byte và trailer field 1:

```java
PSSParameterSpec pss = new PSSParameterSpec(
        "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);
Signature signer = Signature.getInstance("RSASSA-PSS");
signer.setParameter(pss);
signer.initSign(privateSigningKey);
signer.update(message);
byte[] signature = signer.sign();
```

Đây cũng chỉ là **snippet**: phải cung cấp private key ký, byte thông điệp, import các class liên quan và xử lý ngoại lệ. Ở phía verify, dùng `initVerify(publicSigningKey)`, cùng bộ tham số PSS và `verify(signature)`. Nếu digest, MGF1 digest, salt length hoặc scheme không thống nhất, xác minh có thể thất bại.

`SHA256withRSA` là tên chữ ký RSA với scheme **PKCS#1 v1.5**, khác **`RSASSA-PSS`**. Có thể vẫn phải xác minh chữ ký cũ tương thích, nhưng khi thiết kế mới và hai phía hỗ trợ, RSA-PSS thường được ưu tiên. **Không** dùng `Cipher.DECRYPT_MODE` để “xác minh chữ ký RSA” hoặc `Cipher.ENCRYPT_MODE` với private key để thay cho `Signature`.

RSA **không phải** một cơ chế `KeyAgreement`/Diffie–Hellman. Trong kiến trúc bảo mật hiện đại, RSA thường dùng cho xác thực/chữ ký hoặc bảo vệ khóa theo giao thức thích hợp; thỏa thuận khóa có forward secrecy được đảm nhiệm bởi các cơ chế DH khác.

### 2.3 Kích thước khóa và phân tách mục đích

RSA modulus **2048 bit** là kích thước thường thấy làm mức tối thiểu cho nhiều hệ thống hiện có; yêu cầu thực tế có thể cao hơn theo tuổi thọ dữ liệu và chính sách. Độ dài modulus, thuật toán băm, scheme padding, entropy sinh khóa và khả năng provider đều quan trọng. Trong production nên dùng **các cặp khóa RSA khác nhau** cho **mã hóa** và **chữ ký** nếu hệ thống cần cả hai, để chính sách, quyền truy cập và vòng đời khóa được phân tách rõ.

## 3. EC: kiểu khóa elliptic curve, dùng cho ECDSA hoặc ECDH

`EC` trong `KeyPairGenerator.getInstance("EC")` biểu thị khả năng tạo khóa trên một **đường cong EC**. Bạn phải xác định **named curve** phù hợp, ví dụ:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
generator.initialize(new ECGenParameterSpec("secp256r1"));
KeyPair pair = generator.generateKeyPair();
```

Đây là snippet; cần import `java.security.KeyPairGenerator`, `java.security.KeyPair` và `java.security.spec.ECGenParameterSpec`. `secp256r1` còn thường gọi là **NIST P-256**; `secp384r1` tương ứng P-384. Provider có thể có tập đường cong được hỗ trợ khác nhau; không giả định một đường cong bất kỳ đều sẵn có.

### 3.1 ECDSA: chữ ký bằng khóa EC

Với cặp khóa EC trên P-256, một lựa chọn thường dùng là:

```java
Signature signature = Signature.getInstance("SHA256withECDSA");
signature.initSign(signingPrivateKey);
signature.update(message);
byte[] signed = signature.sign();
```

Tên `SHA256withECDSA` mô tả **ECDSA** với digest **SHA-256**. Chữ ký ECDSA có các thành phần toán học `r` và `s`; định dạng byte mà hệ thống trao đổi phải được thống nhất. Java `SHA256withECDSA` thông thường trả chữ ký ASN.1 DER; một số giao thức như JOSE yêu cầu **P1363 raw r||s** và không thể sử dụng byte DER trực tiếp mà không chuyển đúng. Java cũng có tên dạng `SHA256withECDSAinP1363Format` khi provider hỗ trợ.

ECDSA phụ thuộc rất mạnh vào tính đúng của **nonce bí mật dùng cho mỗi chữ ký**. Nonce lặp lại hoặc thiên lệch có thể làm lộ private key. Để provider JCA xử lý cơ chế ký và nguồn ngẫu nhiên; **không tự lập trình công thức ECDSA** hoặc tái sử dụng giá trị nonce.

### 3.2 ECDH: thỏa thuận shared secret bằng khóa EC

Cũng với khóa loại `EC` nhưng sử dụng engine khác:

```java
KeyAgreement agreement = KeyAgreement.getInstance("ECDH");
agreement.init(alicePrivateKey);
agreement.doPhase(bobPublicKey, true);
byte[] sharedSecret = agreement.generateSecret();
```

Đây là snippet, cần các biến khóa đúng loại/đúng curve và import `javax.crypto.KeyAgreement`. Bên Bob có thể tính giá trị bằng `bobPrivateKey` và `alicePublicKey`: hai phía nhận **cùng shared secret** nếu khóa và các tham số tương thích.

**ECDH không tạo chữ ký, không mã hóa dữ liệu và không tự xác thực danh tính đối phương.** Nếu attacker thay public key trong trao đổi, họ có thể thực hiện man-in-the-middle. Cần chứng thực public key (certificate, chữ ký trong protocol, khóa đã ghim hoặc hệ thống danh tính được tin cậy). **Không** đưa raw ECDH output trực tiếp vào `SecretKeySpec("AES")` mà không có cơ chế dẫn xuất khóa và ràng buộc context; dùng **HKDF** hay KDF phù hợp để tạo khóa phiên.

Dùng một cặp khóa EC để minh họa hai engine trong bài học là có thể về mặt API, nhưng production nên **phân tách khóa ký và khóa thỏa thuận** theo mục đích, nhất là khi chính sách/certificate phân biệt `digitalSignature` và `keyAgreement`.

## 4. EdDSA: chuyên dùng cho chữ ký số

**EdDSA (Edwards-curve Digital Signature Algorithm)** là một họ chữ ký số; những biến thể nổi bật:

- **Ed25519**: chữ ký số trên curve Edwards25519, phổ biến cho chữ ký ứng dụng, khóa danh tính, chứng thực cấu hình.
- **Ed448**: một lựa chọn khác, kích thước và đặc tính bảo mật khác; mức hỗ trợ tùy provider.
- Java 17 hỗ trợ tên `EdDSA` tổng quát và những tên cụ thể như `Ed25519` và `Ed448` trong các engine thích hợp. Chọn tên **cụ thể** khi một giao thức quy định rõ biến thể.

Cách ký/verify Java:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
KeyPair keys = generator.generateKeyPair();

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(keys.getPrivate());
signer.update(message);
byte[] signature = signer.sign();

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(keys.getPublic());
verifier.update(message);
boolean valid = verifier.verify(signature);
```

Đây là snippet trong một phương thức có các imports/ngoại lệ thích hợp. Với Ed25519, chữ ký chuẩn dài **64 byte**. Một đặc tính của biến thể Ed25519 chuẩn là quá trình ký **xác định (deterministic)** từ khóa và thông điệp theo thuật toán; điểm này khác yêu cầu nonce khó đoán của ECDSA thông thường. Tuy vậy, private key, nguồn ngẫu nhiên ban đầu khi sinh khóa và kiểm soát implementation vẫn phải được bảo vệ nghiêm ngặt.

**EdDSA không cung cấp `Cipher` hoặc `KeyAgreement`.** Lệnh `Signature.getInstance("Ed25519")` là đúng; `KeyAgreement.getInstance("Ed25519")` không phải cách tạo shared secret, cũng không được gửi public key Ed25519 vào `KeyAgreement.getInstance("X25519")` và giả sử hai loại khóa tương đương.

Ed25519 và X25519 đều liên quan đến đường cong 25519 ở những biểu diễn/toán học khác nhau, nhưng có **mục đích, thuật toán, format key và ràng buộc bảo mật khác nhau**. Có những phép chuyển đổi trong một số giao thức/chuyên thư viện, song **không phải quy tắc JCA portable** và không phải lý do để dùng chung cùng vật liệu khóa. Hãy sinh **khóa Ed25519 cho ký** và **khóa X25519 cho DH** độc lập.

## 5. XDH: chuyên dùng cho thỏa thuận khóa

**XDH** là tên họ DH với các biến thể **X25519** và **X448**, dựa trên RFC 7748. Đây là kỹ thuật để hai bên tính shared secret từ private key của mình và public key đối tác:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
KeyPair alice = generator.generateKeyPair();
KeyPair bob = generator.generateKeyPair();

KeyAgreement ka = KeyAgreement.getInstance("X25519");
ka.init(alice.getPrivate());
ka.doPhase(bob.getPublic(), true);
byte[] secretA = ka.generateSecret();
```

Đây là đoạn minh họa bên trong phương thức; Bob thực hiện tương ứng bằng private key của Bob + public key của Alice để thu shared secret giống nhau. `XDH` cũng là tên thuật toán tổng quát, có thể chọn tham số bằng `NamedParameterSpec.X25519` khi provider hỗ trợ; dùng tên `X25519` tường minh thường đơn giản hơn nếu giao thức quy định sẵn. X25519 tạo shared secret **32 byte**, nhưng **32 byte raw secret đó chưa phải khóa AES ứng dụng**.

### Từ shared secret tới khóa phiên

Trong một protocol hợp lý, hai bên:

1. Sinh hai cặp khóa DH phù hợp, ví dụ **ephemeral X25519** cho mỗi phiên.
2. Trao đổi public key qua một thông điệp bắt tay được **xác thực** (certificate/Ed25519/RSA-PSS/ECDSA hoặc cơ chế đáng tin phù hợp). Dùng đúng public key phía đối tác, kiểm tra key format và thông số.
3. Tính raw secret bằng `KeyAgreement`; nếu implementation từ chối public key yếu hoặc cho kết quả không hợp lệ, **fail closed**. RFC 7748 có trường hợp đầu ra toàn zero khi gặp input bậc nhỏ; nhiều provider kiểm tra và ném ngoại lệ, nhưng ứng dụng không nên giả định mọi provider đều giống nhau.
4. Dẫn xuất khóa qua **HKDF** với salt/info và ngữ cảnh phiên đúng format, có thể ràng buộc cả transcript, vai trò hai phía và protocol version.
5. Sử dụng khóa phiên dẫn xuất trong **AEAD** như AES-GCM/ChaCha20-Poly1305 với nonce duy nhất, và xóa/cô lập secret trung gian trong mức khả thi.

Lưu ý: Các bước `HKDF-Extract(secret)` và `HKDF-Expand(info, length)` ở đây là **mô tả quy trình**, không phải method có sẵn tên đó trong API chuẩn Java 17. Dùng một thư viện HKDF đã kiểm thử, hoặc implementation được đánh giá riêng; không tự thay KDF bằng cách cắt 16 byte đầu raw shared secret.

**X25519 không tự chứng minh đối phương là ai.** Nếu cả hai public key có thể bị thay trên đường truyền, hai bên có thể cùng tạo shared secret với attacker thay vì với nhau. Chữ ký số, certificate hoặc xác thực bắt tay là một phần khác bắt buộc của giao thức.

### Forward secrecy là đặc tính của giao thức, không chỉ tên thuật toán

Với DH **ephemeral** và khóa tạm được xóa sau khi hoàn tất, nếu khóa danh tính lâu dài bị lộ về sau thì dữ liệu phiên cũ có thể vẫn được bảo vệ theo các giả định của protocol. Điều này phụ thuộc thiết kế giao thức đầy đủ, cách xác thực, quản lý transcript, dẫn xuất khóa và việc xóa secret; chỉ dùng `X25519` trong một ứng dụng **không tự đảm bảo forward secrecy**.

## 6. Chương trình Java 17 chạy được: minh họa cả bốn họ

Chương trình dưới đây dùng **mỗi engine đúng mục đích**. Nó sinh các cặp RSA khác nhau cho **mã hóa** và **ký**, sinh khóa EC riêng cho **ECDSA** và **ECDH**, rồi tạo thêm cặp Ed25519 và hai cặp X25519. Mã minh họa các khả năng của API JCA/JCE; **không** xây dựng một giao thức mạng hoặc hệ thống lưu trữ khóa production.

Tạo tệp **`KeyFamilyDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class KeyFamilyDemo {
    private static final byte[] MESSAGE =
            "Java public-key roles".getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) throws Exception {
        KeyPairGenerator rsaGenerator = KeyPairGenerator.getInstance("RSA");
        rsaGenerator.initialize(2048);
        KeyPair rsaEncryption = rsaGenerator.generateKeyPair();
        KeyPair rsaSigning = rsaGenerator.generateKeyPair();

        OAEPParameterSpec oaep = new OAEPParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                PSource.PSpecified.DEFAULT);
        Cipher rsaEncrypt = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsaEncrypt.init(Cipher.ENCRYPT_MODE, rsaEncryption.getPublic(), oaep);
        byte[] wrappedMessage = rsaEncrypt.doFinal(MESSAGE);
        Cipher rsaDecrypt = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsaDecrypt.init(Cipher.DECRYPT_MODE, rsaEncryption.getPrivate(), oaep);
        System.out.println("RSA-OAEP decrypt: "
                + Arrays.equals(MESSAGE, rsaDecrypt.doFinal(wrappedMessage)));

        PSSParameterSpec pssParams = new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);
        System.out.println("RSA-PSS verify: "
                + signAndVerify("RSASSA-PSS", rsaSigning, pssParams));

        KeyPairGenerator ecGenerator = KeyPairGenerator.getInstance("EC");
        ecGenerator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair ecSigning = ecGenerator.generateKeyPair();
        KeyPair ecAlice = ecGenerator.generateKeyPair();
        KeyPair ecBob = ecGenerator.generateKeyPair();
        System.out.println("ECDSA verify: "
                + signAndVerify("SHA256withECDSA", ecSigning, null));
        System.out.println("ECDH shared secret matches: "
                + sameSecret("ECDH", ecAlice, ecBob));

        KeyPairGenerator edGenerator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair edSigning = edGenerator.generateKeyPair();
        System.out.println("Ed25519 verify: "
                + signAndVerify("Ed25519", edSigning, null));

        KeyPairGenerator xGenerator = KeyPairGenerator.getInstance("X25519");
        KeyPair xAlice = xGenerator.generateKeyPair();
        KeyPair xBob = xGenerator.generateKeyPair();
        System.out.println("X25519 shared secret matches: "
                + sameSecret("X25519", xAlice, xBob));
    }

    private static boolean signAndVerify(
            String algorithm, KeyPair keyPair, PSSParameterSpec pss)
            throws Exception {
        Signature signer = Signature.getInstance(algorithm);
        if (pss != null) {
            signer.setParameter(pss);
        }
        signer.initSign(keyPair.getPrivate());
        signer.update(MESSAGE);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance(algorithm);
        if (pss != null) {
            verifier.setParameter(pss);
        }
        verifier.initVerify(keyPair.getPublic());
        verifier.update(MESSAGE);
        boolean original = verifier.verify(signature);

        verifier.initVerify(keyPair.getPublic());
        if (pss != null) {
            verifier.setParameter(pss);
        }
        verifier.update("modified".getBytes(StandardCharsets.UTF_8));
        boolean modified = verifier.verify(signature);
        return original && !modified;
    }

    private static boolean sameSecret(
            String algorithm, KeyPair alice, KeyPair bob) throws Exception {
        KeyAgreement agreementA = KeyAgreement.getInstance(algorithm);
        agreementA.init(alice.getPrivate());
        agreementA.doPhase(bob.getPublic(), true);
        byte[] a = agreementA.generateSecret();

        KeyAgreement agreementB = KeyAgreement.getInstance(algorithm);
        agreementB.init(bob.getPrivate());
        agreementB.doPhase(alice.getPublic(), true);
        byte[] b = agreementB.generateSecret();

        boolean same = MessageDigest.isEqual(a, b);
        Arrays.fill(a, (byte) 0);
        Arrays.fill(b, (byte) 0);
        return same;
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 KeyFamilyDemo.java
java KeyFamilyDemo
```

Đầu ra **trên môi trường Java 17+ có provider hỗ trợ các dịch vụ được yêu cầu**:

```text
RSA-OAEP decrypt: true
RSA-PSS verify: true
ECDSA verify: true
ECDH shared secret matches: true
Ed25519 verify: true
X25519 shared secret matches: true
```

**Ý nghĩa từng dòng:**

- `RSA-OAEP decrypt: true`: public RSA dành cho mã hóa, private RSA cùng cặp giải mã được **thông điệp ngắn**. OAEP có SHA-256/MGF1 SHA-256 được chỉ định rõ.
- `RSA-PSS verify: true`: chữ ký RSA-PSS xác minh bằng public signing key; helper còn kiểm tra chữ ký này **không** hợp lệ cho thông điệp `"modified"`.
- `ECDSA verify: true`: khóa EC trên `secp256r1` tạo/kiểm chứng chữ ký ECDSA-SHA256; helper cũng thử phát hiện thông điệp bị đổi.
- `ECDH shared secret matches: true`: Alice/Bob dùng private key của mình và public key đối tác trên cùng loại curve, tạo shared secret trùng nhau.
- `Ed25519 verify: true`: một cặp khóa chuyên ký/verify Ed25519 và kiểm thử tampering.
- `X25519 shared secret matches: true`: hai cặp X25519 sinh secret giống nhau khi DH thành công.

Các giá trị ngẫu nhiên (key, ciphertext OAEP, chữ ký RSA-PSS/ECDSA, DH raw secret) **khác nhau giữa các lần chạy**; chương trình không in chúng ra. Các dòng `true` là kiểm tra tính đúng đắn, **không chứng minh public key của đối tác đã được xác thực hoặc giao thức có bảo mật toàn diện**.

**Lưu ý về code:** `sameSecret` so sánh hai secret để phục vụ test, sau đó cố gắng ghi đè hai mảng byte cục bộ. Java và provider có thể giữ các bản sao trong bộ nhớ không thể xóa bằng thao tác này. Production phải dẫn xuất khóa phiên với HKDF và có vòng đời secret phù hợp; không đưa raw DH output thẳng vào AES. RSA-OAEP demo mã hóa trực tiếp một thông điệp nhỏ cho dễ quan sát; dữ liệu dài nên dùng mã hóa lai.

## 7. Chọn cơ chế theo bài toán thực tế

| Bài toán | Nên xem xét | Vì sao |
| --- | --- | --- |
| Ký file cấu hình, bản phát hành hoặc thông điệp | Ed25519, ECDSA hoặc RSA-PSS theo hệ sinh thái và chuẩn giao thức | Người nhận verify bằng public key; có thể quản lý trust chain |
| Mã hóa một AES content key cho người nhận có RSA public key | RSA-OAEP + AES-GCM theo format định nghĩa | RSA bảo vệ khóa ngắn, AEAD bảo vệ dữ liệu lớn |
| Hai bên tạo khóa phiên khi bắt tay | X25519 hoặc ECDH + HKDF + xác thực public keys | DH đồng ý secret, HKDF dẫn xuất khóa và cơ chế xác thực ngăn MITM |
| Cần kết hợp khóa danh tính ký và khóa phiên DH | Ed25519 cho signature và X25519 cho DH, hoặc RSA-PSS/ECDSA + ECDH | Chọn từng thuật toán theo vai trò, không dùng một loại khóa làm tất cả |
| Dùng certificate EC đang có | Kiểm tra key usage và thuật toán hỗ trợ của certificate | Certificate ECDSA không mặc nhiên dùng được để làm ECDH |
| TLS cho web/app | Dùng JSSE/TLS stack đã kiểm thử | TLS tự quản lý bắt tay, chứng thực, DH, KDF và AEAD; tránh tự chế giao thức |

**Ví dụ sơ đồ bắt tay (mô hình khái niệm):**

```text
Alice tạo X25519 ephemeral A               Bob tạo X25519 ephemeral B
         |                                              |
         +---- public(A), ngữ cảnh ---->                 |
         |                 <---- public(B), chứng thực --+
         |                                              |
 DH(privateA, publicB)                       DH(privateB, publicA)
         |                                              |
         +---- cùng raw DH secret khi hợp lệ ------------+
         |                                              |
 HKDF(secret, transcript, roles)              HKDF(secret, transcript, roles)
         |                                              |
       khóa phiên AEAD, nonce theo giao thức + kiểm tra xác thực
```

Sơ đồ cố tình lược bỏ chi tiết của TLS/HPKE. Điều **không được lược bỏ** trong triển khai thật là cách **xác thực** các ephemeral public keys và transcript, ngăn downgrade/replay, giới hạn thuật toán, kiểm tra giá trị đầu vào và dẫn xuất key/nonce tách biệt theo chiều gửi/nhận.

## 8. Các tên JCA và định dạng khóa dễ nhầm

### Engine và tên thuật toán

| Java API | Tên đề xuất | Dùng để làm gì |
| --- | --- | --- |
| `KeyPairGenerator.getInstance(...)` | `RSA`, `EC`, `Ed25519`, `X25519` | Sinh đúng kiểu cặp khóa |
| `Cipher.getInstance(...)` | `RSA/ECB/OAEPPadding` | RSA-OAEP mã hóa/giải mã đầu vào nhỏ |
| `Signature.getInstance(...)` | `RSASSA-PSS`, `SHA256withECDSA`, `Ed25519` | Ký/xác minh |
| `KeyAgreement.getInstance(...)` | `ECDH`, `X25519` | Thỏa thuận raw secret |
| `KeyFactory.getInstance(...)` | `RSA`, `EC`, `Ed25519`, `X25519` | Tạo lại đối tượng khóa từ encoding/spec phù hợp |

`getInstance` tạo engine theo **service type + algorithm name**, chọn provider hiện tại; provider nào có dịch vụ cụ thể cần thử đúng trên môi trường sẽ triển khai. `Security.getAlgorithms("Signature")` và `Security.getAlgorithms("KeyAgreement")` giúp khám phá tên đã đăng ký, nhưng không đủ để chứng minh **khóa/curve/params** của hệ thống được chấp nhận.

### X.509 và PKCS#8 không phải tên thuật toán ký

Một public key được xuất dưới dạng SubjectPublicKeyInfo thường được xử lý bằng `X509EncodedKeySpec`; private key `PrivateKeyInfo` thường dùng `PKCS8EncodedKeySpec`. Các thuật ngữ **X.509** và **PKCS#8** ở đây là *định dạng dữ liệu khóa*, còn **RSA**, **EC**, **Ed25519**, **X25519** là *thuật toán/kiểu khóa*. Chuỗi PEM có các dòng `-----BEGIN PUBLIC KEY-----` hoặc `-----BEGIN PRIVATE KEY-----` thường chỉ bọc Base64 quanh DER; phải decode, xác nhận đúng format rồi dùng `KeyFactory` với kiểu thuật toán phù hợp.

Không nhầm `X509EncodedKeySpec` với **chứng chỉ X.509**: public-key object chứa khóa, chứng chỉ còn có danh tính, tổ chức phát hành, thời hạn và chữ ký chứng thực. Import public key từ một file không tự biến nó thành danh tính đáng tin.

Không tự lấy `getEncoded()` của HSM/keystore key rồi ghi vào log: nhiều private key bảo vệ bằng hardware/keystore không thể xuất byte (`getEncoded()` có thể trả `null`), và đây là tính năng bảo mật mong muốn. Để kiểm tra khóa hỗ trợ gì, dùng JCA đúng engine và xác minh `KeyUsage`/chính sách thay vì chỉ đọc `key.getAlgorithm()`.

### Sai tên thường gặp

- `Signature.getInstance("RSA")`: muốn ký theo RSA hãy chọn scheme **`RSASSA-PSS`** (và PSS parameters), hoặc một tên chữ ký cụ thể mà protocol yêu cầu.
- `Cipher.getInstance("EC")`, `Cipher.getInstance("Ed25519")`, `Cipher.getInstance("X25519")`: không phải những cách biểu diễn hợp lệ để có mã hóa ứng dụng bằng các loại khóa đó.
- `Signature.getInstance("X25519")`: X25519 phục vụ DH, không có chữ ký X25519.
- `KeyAgreement.getInstance("Ed25519")`: Ed25519 phục vụ chữ ký, không có DH tên Ed25519.
- `Signature.getInstance("ECDH")`: ECDH là thỏa thuận khóa, không có chữ ký ECDH.
- Đưa cặp khóa Ed25519 vào `KeyAgreement("X25519")` hoặc cặp X25519 vào `Signature("Ed25519")`: sai key type, thường ném `InvalidKeyException`.
- So các byte signature ECDSA ở hai lần ký để kết luận thuật toán lỗi: ECDSA thường có randomness nên có thể khác; hãy dùng **`verify`**.
- `SHA256withRSA` và `RSASSA-PSS` là các scheme chữ ký khác nhau, không thể hoán đổi khi verify nếu metadata/protocol không chỉ rõ.

## 9. Kiểm tra khả năng hỗ trợ và xử lý lỗi theo đúng lớp

Một cách kiểm tra ý nghĩa hơn việc chỉ đọc danh sách tên là chạy thử **cùng API, curve và bộ tham số** ứng dụng sẽ sử dụng:

1. Tạo đúng `KeyPairGenerator` theo thuật toán và curve: RSA modulus, `ECGenParameterSpec("secp256r1")` hoặc `Ed25519`/`X25519`.
2. Kiểm tra `getInstance` của **đúng engine**: `Cipher`, `Signature` hay `KeyAgreement`.
3. Chạy đầy đủ `init` và phép tính: RSA encrypt/decrypt; signature sign/verify cả đúng lẫn sai message; ECDH/X25519 hai chiều và so shared secret.
4. Kiểm tra khớp với policy: provider/HSM, key usage, key ID, param OAEP/PSS, encoding, curve, quyền sử dụng khóa.
5. Tách lỗi cấu hình khỏi lỗi verify hoặc input không hợp lệ; không fallback yếu một cách ngầm định.

| Biểu hiện | Nguyên nhân nên kiểm tra |
| --- | --- |
| `NoSuchAlgorithmException` | Engine/algorithm name không được provider hỗ trợ (vd. gọi `Signature("X25519")`); kiểm tra tên chuẩn và provider |
| `NoSuchPaddingException` từ `Cipher.getInstance` | Transformation không được cung cấp; kiểm tra đúng OAEP padding và provider |
| `InvalidKeyException` khi `initSign/initVerify/init/doPhase` | Key không đúng loại, sai đường cong, thiếu quyền HSM, public key bị reject |
| `InvalidAlgorithmParameterException` | Spec đường cong/OAEP/PSS không được chấp nhận hoặc không khớp policy |
| `SignatureException` hoặc `verify == false` | Đầu vào, chữ ký, kiểu mã hóa, thuật toán, params hoặc public key không phù hợp; chữ ký giả mạo cũng có thể gây ra kết quả tương tự |
| `BadPaddingException` / `IllegalBlockSizeException` khi RSA-OAEP | Ciphertext lỗi/sai khóa/sai tham số hoặc input vượt giới hạn; không tiết lộ chi tiết cho client |
| ECDH/X25519 cho secret khác nhau | Không đúng private/public peers, curve/format bị đổi hoặc lỗi implementation; từ chối phiên |
| `KeyFactory` không đọc được public/private key | Sai format X.509/PKCS#8, sai algorithm OID, thông số hoặc provider |

**Không công bố cho client những thông tin nội bộ có thể làm lộ khóa hoặc tạo oracle.** Tại ranh giới API, áp dụng thông báo lỗi chung đối với giải mã/chữ ký không hợp lệ, kết hợp logging nội bộ có kiểm soát. Nếu một thuật toán được giao thức yêu cầu nhưng provider không hỗ trợ, nên xử lý như lỗi cấu hình hoặc fail fast; không tự chuyển RSA-OAEP thành RSA raw, hoặc chuyển XDH thành một khóa mặc định.

## 10. Quản lý khóa và lựa chọn dài hạn

- **Tách khóa theo mục đích**: khóa chữ ký khác khóa giải mã; khóa danh tính dài hạn khác khóa thỏa thuận tạm thời. Áp dụng key usage đúng trong certificate, key store và quyền KMS/HSM.
- **Tạo khóa bằng nguồn ngẫu nhiên mật mã** và provider tin cậy. Không tạo private key bằng mật khẩu hay từ các byte đoán được. Không sao chép khóa chỉ vì chúng có cùng độ dài.
- **Ràng buộc danh tính public key**: public key không phải secret, nhưng việc kẻ tấn công thay thế public key vẫn phá vỡ bảo mật của mã hóa, chữ ký hoặc DH nếu không xác thực được nguồn.
- **Chọn scheme và tham số rõ ràng**: RSA-PSS cần MGF1/salt/digest, RSA-OAEP cần digest và MGF1, EC cần named curve, XDH cần đúng X25519/X448, EdDSA cần đúng Ed25519/Ed448.
- **Dẫn xuất session key từ DH**: dùng KDF và protocol context, không cắt raw shared secret tùy tiện. Chống replay, downgrade, xác thực transcript, dùng AEAD và nonce duy nhất.
- **Kiểm tra hệ sinh thái**: khả năng tương thích của TLS, certificate, JOSE/JWT, định dạng chữ ký DER/P1363, nền tảng HSM/FIPS hay thư viện đối tác có thể buộc chọn thuật toán khác nhau.
- **Không đánh đồng kích thước byte public key/signature với mức bảo mật**: RSA-2048, P-256, Ed25519, X25519 có cấu trúc và chi phí toán học rất khác nhau; tuân theo chuẩn/chính sách để chọn mức bảo mật cần thiết.
- **Đánh giá vòng đời thuật toán**: RSA/ECC cổ điển không cung cấp an toàn hậu lượng tử. Nếu yêu cầu bảo mật dữ liệu dài hạn hoặc hệ thống hướng tới chuẩn hậu lượng tử, tham khảo lựa chọn được chuẩn hóa như KEM/chữ ký hậu lượng tử trong giao thức phù hợp; không tự trộn khóa/thuật toán ngoài một protocol được đánh giá.

## 11. Bài thực hành

1. Trong `KeyFamilyDemo.java`, chỉ ra dòng nào dùng `Cipher`, dòng nào dùng `Signature` và dòng nào dùng `KeyAgreement`. Vì sao `X25519` không thể thay thế trực tiếp cho `Ed25519`?
2. Thay `SHA256withECDSA` bằng `Ed25519` nhưng vẫn dùng một khóa `EC` cho `Signature.initSign`. Dự đoán và kiểm tra loại lỗi, rồi giải thích key type nào bị sai.
3. Xây dựng bảng policy: ứng dụng cần **ký file cấu hình**, **thỏa thuận khóa phiên**, **mã hóa file lớn**, **bảo vệ AES content key bằng RSA**. Với mỗi yêu cầu, chọn đúng scheme, engine và cách quản lý key.
4. Tại sao RSA-OAEP dùng modulus 2048 bit và SHA-256 không mã hóa tùy ý 1 MiB plaintext trong một lần? Hãy tính giới hạn 190 byte bằng công thức `k - 2*hLen - 2`.
5. Nếu raw secret ECDH và X25519 trùng nhau giữa hai phía, có thể kết luận họ đang trao đổi với đúng đối tác chưa? Đề xuất cách xác thực transcript/public key.
6. Thêm cơ chế lưu và nạp public key được tin cậy theo `X509EncodedKeySpec`. Phân biệt raw public key từ file với chứng chỉ X.509 có chuỗi tin cậy.
7. Kiểm tra khả năng hỗ trợ `RSASSA-PSS`, `Ed25519` và `X25519` trên JVM/provider triển khai. Ghi Java version, provider, params và kết quả các phép thử, **không ghi private key**.

## Tài liệu tham khảo

- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên chuẩn `RSA`, `EC`, `RSASSA-PSS`, `EdDSA`, `Ed25519`, `XDH`, `X25519` và service types.
- [Java SE 17 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): JCA provider, `KeyPairGenerator`, `Signature`, `KeyAgreement` và `Cipher`.
- [Java SE 17 — `Signature`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): ký và xác minh với RSA-PSS, ECDSA, EdDSA.
- [Java SE 17 — `KeyAgreement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html): giao thức thỏa thuận khóa và cách dùng `doPhase`/`generateSecret`.
- [Java SE 17 — `OAEPParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/OAEPParameterSpec.html): thông số OAEP và MGF1.
- [Java SE 17 — `PSSParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html): digest, MGF, salt length, trailer field.
- [RFC 8017 — PKCS #1 v2.2](https://www.rfc-editor.org/rfc/rfc8017): RSAES-OAEP và RSASSA-PSS.
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): Ed25519/Ed448.
- [RFC 7748 — Elliptic Curves for Security](https://www.rfc-editor.org/rfc/rfc7748): X25519/X448 và vấn đề đầu ra all-zero.
- [RFC 5869 — HKDF](https://www.rfc-editor.org/rfc/rfc5869): dẫn xuất khóa từ shared secret.
