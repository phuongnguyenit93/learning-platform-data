# Lựa chọn provider, thuật toán theo chính sách JDK hiện hành

## 1. Mục tiêu và bối cảnh

Java cung cấp các API mật mã chuẩn thông qua **Java Cryptography Architecture (JCA)** và **Java Cryptography Extension (JCE)**. Ứng dụng yêu cầu một dịch vụ như hash, ký số, mã hóa, MAC hoặc sinh số ngẫu nhiên; JDK tìm một implementation tương ứng trong các **Cryptographic Service Provider (CSP)** đã đăng ký.

Ví dụ:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
Signature signature = Signature.getInstance("Ed25519");
```

*Các lời gọi minh họa cần imports tương ứng và xử lý exception.*

Khi xây ứng dụng mật mã, có hai quyết định riêng:

- **Chọn thuật toán:** AES-GCM, ChaCha20-Poly1305, SHA-256, HmacSHA256, Ed25519, X25519, ML-KEM, v.v.
- **Chọn implementation/provider:** SunJCE, SunEC, SUN, SunRsaSign, SunJSSE, SunPKCS11 hoặc provider bên thứ ba.

Provider không làm một thuật toán yếu trở nên an toàn. Thuật toán tốt cũng không giúp ích nếu provider bắt buộc không được cài hoặc không đáp ứng policy trên môi trường triển khai.

Bài học thuộc module **Mật mã ứng dụng**, với đề bài **“Lựa chọn provider, thuật toán theo chính sách JDK hiện hành”**. Mốc tham chiếu cập nhật là **Oracle JDK 27**, phát hành ngày 15/09/2026. Những ví dụ API phổ thông nhắm Java 17+; phần hậu lượng tử ghi rõ yêu cầu JDK mới hơn. Nội dung chỉ tập trung vào API và chính sách còn hiệu lực.

Sau bài này, bạn có thể:

1. Hiểu engine class, provider, preference order và cách JCA tìm implementation.
2. Dùng standard algorithm names thay vì alias riêng của provider.
3. Biết khi nào để JCA chọn provider, khi nào cần chỉ định provider vì HSM/compliance.
4. Phân biệt thuật toán được cung cấp, thuật toán được policy cho phép và thuật toán phù hợp với threat model.
5. Đọc security properties của JDK và biết phạm vi của từng property.
6. Chọn đúng primitive: encryption, hash, MAC, signature, key agreement, KDF, password hashing và SecureRandom.
7. Tránh ECB, nonce reuse, hash mật khẩu một lượt, random không mật mã và tự thiết kế protocol.
8. Hiểu các dịch vụ ML-KEM/ML-DSA và TLS hybrid key exchange trong JDK 27.
9. Kiểm tra provider/algorithm trên đúng runtime thay vì suy đoán từ tên JDK.
10. Kiểm thử, vận hành và nâng cấp mật mã mà không bật lại thuật toán yếu.

## 2. JCA, JCE và Provider Architecture

JCA định nghĩa API cấp cao (*engine classes*). Provider chứa implementation cụ thể cho các engine đó.

| Engine/API | Mục đích | Ví dụ tên |
| --- | --- | --- |
| `MessageDigest` | Hash không khóa | `SHA-256`, `SHA3-256` |
| `Mac` | Message Authentication Code | `HmacSHA256` |
| `Cipher` | Mã hóa/giải mã | `AES/GCM/NoPadding`, `ChaCha20-Poly1305` |
| `Signature` | Ký và xác minh | `Ed25519`, `RSASSA-PSS`, `ML-DSA` |
| `SecureRandom` | Sinh dữ liệu ngẫu nhiên mật mã | `DRBG` |
| `KeyGenerator` | Tạo secret key | `AES`, `HmacSHA256` |
| `KeyPairGenerator` | Tạo public/private key pair | `RSA`, `Ed25519`, `X25519` |
| `KeyAgreement` | Thỏa thuận shared secret | `X25519`, `ECDH` |
| `KEM` | Encapsulation/decapsulation secret | `ML-KEM` |
| `KDF` | Dẫn xuất key | `HKDF-SHA256` |
| `KeyStore` | Lưu trữ key/certificate | `PKCS12` |
| `CertPathValidator` | Kiểm tra certificate path | `PKIX` |

Luồng cơ bản:

```text
Ứng dụng
   |
   | Cipher.getInstance("AES/GCM/NoPadding")
   v
JCA engine API
   |
   | tìm provider theo preference order
   v
Provider có service phù hợp
   |
   | khởi tạo với key + parameters
   v
Implementation thực hiện crypto operation
```

Nếu nhiều provider cùng hỗ trợ một thuật toán, lời gọi không chỉ định provider sẽ chọn implementation đầu tiên theo **provider preference order**. Vì vậy hai JDK vendor hoặc hai môi trường có thể dùng implementation khác nhau dù code giống nhau.

### 2.1. Provider thường gặp trong Oracle JDK 27

| Provider | Dịch vụ tiêu biểu |
| --- | --- |
| `SUN` | MessageDigest, SecureRandom, certificate/path, keystore, ML-DSA |
| `SunJCE` | Cipher, MAC, key generator, PBKDF2, HKDF, KEM |
| `SunEC` | Elliptic curve, EdDSA, XDH/X25519/X448, ECDH/ECDSA |
| `SunRsaSign` | RSA signature services |
| `SunJSSE` | TLS/DTLS |
| `SunPKCS11` | Bridge tới native PKCS#11 module, HSM hoặc smart card |
| `SunMSCAPI` | Tích hợp Windows crypto provider trên môi trường hỗ trợ |

Danh sách này là tham khảo theo Oracle JDK 27. Không giả định mọi JDK vendor đều có cùng provider, tên provider hoặc preference order.

`SunPKCS11` là **cầu nối**, không tự chứa toàn bộ thuật toán. Nó chuyển lời gọi JCA tới PKCS#11 module phía dưới. Thuật toán và trạng thái compliance phụ thuộc module/token được cấu hình.

## 3. Mặc định để JCA chọn provider

Với ứng dụng phổ thông, thường gọi:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
Signature signer = Signature.getInstance("Ed25519");
MessageDigest digest = MessageDigest.getInstance("SHA-256");
```

JCA tìm provider phù hợp theo thứ tự ưu tiên. Cách này tăng portability và cho phép runtime chọn implementation có tối ưu phần cứng/nền tảng.

Không nên gắn tên provider vào mọi lời gọi nếu không có yêu cầu:

```java
Cipher cipher = Cipher.getInstance(
        "AES/GCM/NoPadding", "SunJCE");
```

*Ví dụ chỉ để minh họa overload chỉ định provider; không phải default cho ứng dụng general-purpose.*

### 3.1. Khi nào phải chỉ định provider?

Có thể cần chỉ định khi:

- Policy bắt buộc dùng một cryptographic module đã được kiểm định.
- Private key phải ở HSM/smart card và không được export.
- Ứng dụng phải chạy với provider đã được tổ chức phê duyệt.
- Cần một native provider hoặc một implementation đã được kiểm thử cho môi trường cụ thể.

Ví dụ:

```java
Provider approved = Security.getProvider(configuredProviderName);
if (approved == null) {
    throw new IllegalStateException("Required provider is missing");
}
Signature signature = Signature.getInstance("Ed25519", approved);
```

*Snippet yêu cầu `configuredProviderName` đến từ cấu hình deployment đã được kiểm soát.*

Nếu provider cụ thể không có, JCA không tự fallback sang provider khác. Lời gọi có thể ném `NoSuchProviderException` hoặc `NoSuchAlgorithmException`.

**Compliance không chỉ là tên provider.** Cần xác minh exact module/version, certificate/validation status, approved mode, phần cứng, cấu hình và danh sách thuật toán được phép. Một provider có khả năng FIPS nhưng đang chạy ngoài approved mode không tự đáp ứng yêu cầu FIPS.

### 3.2. Provider order là trạng thái toàn JVM

`Security.getProviders()` trả các provider đã đăng ký theo preference order. `Security.insertProviderAt`/`addProvider` có thể thay đổi danh sách. Đây là cấu hình toàn process, ảnh hưởng nhiều lời gọi `getInstance`.

Không đổi provider order theo từng request. Cấu hình provider một lần trong startup, ghi lại JDK/provider versions và test toàn bộ ứng dụng trong cấu hình đó.

## 4. Khám phá provider và service đang dùng

Không đoán provider từ tên class. Kiểm tra object thực tế:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
System.out.println(digest.getProvider().getName());
System.out.println(digest.getAlgorithm());
```

*Snippet minh họa.*

Có thể xem các service mà provider công bố:

```java
for (Provider provider : Security.getProviders()) {
    for (Provider.Service service : provider.getServices()) {
        if ("Cipher".equals(service.getType())) {
            System.out.println(provider.getName()
                    + " -> " + service.getAlgorithm());
        }
    }
}
```

*Snippet minh họa; không nên dump toàn bộ service list vào log production thường xuyên.*

Lưu `ProviderInventoryDemo.java`:

```java
import java.security.MessageDigest;
import java.security.Provider;
import java.security.Security;
import javax.crypto.Cipher;

public class ProviderInventoryDemo {
    public static void main(String[] args) throws Exception {
        Provider[] providers = Security.getProviders();
        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        Cipher gcm = Cipher.getInstance("AES/GCM/NoPadding");

        System.out.println("providersFound = " +
                (providers.length > 0));
        System.out.println("sha256Name = " + sha.getAlgorithm());
        System.out.println("sha256ProviderRegistered = " +
                (Security.getProvider(
                        sha.getProvider().getName()) != null));
        System.out.println("aesGcmProviderRegistered = " +
                (Security.getProvider(
                        gcm.getProvider().getName()) != null));
    }
}
```

```bash
javac ProviderInventoryDemo.java
java ProviderInventoryDemo
```

Stdout:

```text
providersFound = true
sha256Name = SHA-256
sha256ProviderRegistered = true
aesGcmProviderRegistered = true
```

Tên provider cụ thể không được hard-code vì danh sách phụ thuộc runtime. Khi troubleshooting, ghi nhận provider thực tế, JDK vendor/build, OS, provider config và transformation đang dùng.

## 5. Standard algorithm names và cipher transformation

Java Security Standard Algorithm Names quy định tên thuật toán dùng với JCA. Tên chuẩn không phân biệt chữ hoa/thường, nhưng nên viết đúng spelling chuẩn để code dễ đọc và portable.

Ví dụ tên chuẩn:

- Digest: `SHA-256`, `SHA-384`, `SHA3-256`.
- MAC: `HmacSHA256`, `HmacSHA384`.
- Signature: `Ed25519`, `Ed448`, `RSASSA-PSS`, `SHA256withECDSA`, `ML-DSA`.
- Key agreement: `X25519`, `X448`, `ECDH`.
- KEM: `ML-KEM`.
- KDF: `HKDF-SHA256`, `HKDF-SHA384`, `HKDF-SHA512`.
- SecureRandom: `DRBG`.
- Keystore: `PKCS12`.

Provider có thể hỗ trợ alias khác nhau. Hãy ưu tiên standard name thay vì alias riêng của một implementation.

### 5.1. Cipher transformation phải ghi đầy đủ

`Cipher.getInstance` thường nhận transformation theo dạng:

```text
algorithm/mode/padding
```

Ví dụ:

```java
Cipher.getInstance("AES/GCM/NoPadding");
Cipher.getInstance("AES/CBC/PKCS5Padding");
```

*CBC chỉ nên xuất hiện trong bối cảnh tương thích có thiết kế authentication riêng.*

Không gọi `Cipher.getInstance("AES")` rồi dựa vào default mode. Default có thể phụ thuộc provider. Oracle JDK providers documentation nêu rằng SunJCE/SunPKCS11 có thể dùng ECB/PKCS5Padding làm default cho nhiều block cipher khi mode/padding bị bỏ qua.

**Không chọn ECB cho mã hóa nhiều block dữ liệu.** ECB làm lộ pattern của plaintext. Với ứng dụng mới, ưu tiên authenticated encryption như AES-GCM hoặc ChaCha20-Poly1305.

## 6. Chọn thuật toán theo mục đích

| Nhu cầu | Lựa chọn hiện hành thường gặp | Lưu ý |
| --- | --- | --- |
| Mã hóa đối xứng | `AES/GCM/NoPadding` hoặc `ChaCha20-Poly1305` | AEAD, nonce duy nhất theo key |
| Hash | `SHA-256`, `SHA-384`, `SHA3-256` | Hash không khóa không xác thực nguồn |
| Xác thực message | `HmacSHA256` hoặc `HmacSHA384` | Secret key phải được quản lý |
| Chữ ký số | `Ed25519`, `RSASSA-PSS`, `SHA256withECDSA` | Theo interoperability/policy |
| Key agreement | `X25519` hoặc `ECDH` | Cần xác thực peer và KDF |
| Dẫn xuất subkey | `HKDF-SHA256`/`HKDF-SHA384` | Input phải có entropy phù hợp |
| Mật khẩu | Password KDF như Argon2id/PBKDF2 theo policy | Salt riêng, work factor phù hợp |
| KEM hậu lượng tử | `ML-KEM` | Tạo shared secret, không mã hóa payload trực tiếp |
| Signature hậu lượng tử | `ML-DSA` | Peer/protocol cần hỗ trợ |
| Kết nối mạng | JSSE với `TLS`/`TLSv1.3` | Để TLS quản lý handshake và negotiation |

### 6.1. Hash, MAC và signature không thay thế nhau

- **Hash:** ai cũng có thể tính digest; không chứng minh ai tạo message.
- **HMAC:** dùng secret key để xác thực integrity và possession of key.
- **Digital signature:** private key ký, public key xác minh; phù hợp xác thực nguồn và kiểm tra độc lập.

Không dùng `SHA-256(message)` thay HMAC. Attacker có thể sửa message và tính lại hash công khai.

### 6.2. Password không phải random key

Không lưu password bằng `SHA-256(password)` một lượt. Password thường có entropy thấp và dễ bị dò offline. Dùng password hashing/KDF có salt ngẫu nhiên và work factor đủ cao theo policy, ví dụ Argon2id qua thư viện được kiểm định hoặc PBKDF2-HMAC-SHA-256 khi môi trường yêu cầu.

`HKDF` dùng để dẫn xuất key từ secret có entropy, không thay password hashing.

## 7. AEAD: AES-GCM và ChaCha20-Poly1305

AEAD (*Authenticated Encryption with Associated Data*) cung cấp confidentiality và integrity/authentication. AAD không bị mã hóa nhưng được bảo vệ toàn vẹn, phù hợp cho metadata như version, record type hoặc identifier không bí mật.

Hai lựa chọn phổ biến trên Oracle JDK 27:

- `AES/GCM/NoPadding`.
- `ChaCha20-Poly1305`.

**Không bao giờ tái sử dụng cùng nonce/IV với cùng AES-GCM key.** Nonce reuse có thể phá vỡ bảo mật và xác thực của GCM. 12 byte (96 bit) là IV size thông dụng; tag 128 bit là lựa chọn phổ biến. Hệ thống mã hóa số lượng lớn cần giới hạn key usage và thiết kế nonce uniqueness rõ ràng.

```text
Key + nonce unique + AAD + plaintext
                 |
                 v
           AEAD encryption
                 |
          ciphertext + tag
                 |
                 v
       decrypt với đúng key,
          nonce và AAD
                 |
        tag verification?
             /       \
           pass       fail
            |           |
        plaintext    reject
```

Lưu `AesGcmRoundTripDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmRoundTripDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, random);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[12];
        random.nextBytes(nonce);
        byte[] aad = "record-v1".getBytes(StandardCharsets.UTF_8);
        byte[] plain = "sensitive payload".getBytes(
                StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        encrypt.updateAAD(aad);
        byte[] ciphertext = encrypt.doFinal(plain);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(128, nonce));
        decrypt.updateAAD(aad);
        byte[] recovered = decrypt.doFinal(ciphertext);

        byte[] tampered = ciphertext.clone();
        tampered[0] ^= 1;
        boolean rejected = false;
        try {
            Cipher bad = Cipher.getInstance("AES/GCM/NoPadding");
            bad.init(Cipher.DECRYPT_MODE, key,
                    new GCMParameterSpec(128, nonce));
            bad.updateAAD(aad);
            bad.doFinal(tampered);
        } catch (AEADBadTagException expected) {
            rejected = true;
        }

        System.out.println("roundTrip = " +
                Arrays.equals(plain, recovered));
        System.out.println("tamperRejected = " + rejected);
        System.out.println("nonceBytes = " + nonce.length);
        System.out.println("tagBits = 128");
    }
}
```

```bash
javac AesGcmRoundTripDemo.java
java AesGcmRoundTripDemo
```

```text
roundTrip = true
tamperRejected = true
nonceBytes = 12
tagBits = 128
```

Đây là demo một lần mã hóa với key mới. Production cần thiết kế nonce uniqueness trên toàn bộ phạm vi sử dụng key: nhiều process, restart, distributed writers, giới hạn số lần mã hóa và key rotation.

### 7.1. ChaCha20-Poly1305

Lưu `ChaCha20Poly1305Demo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public class ChaCha20Poly1305Demo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256, random);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[12];
        random.nextBytes(nonce);
        byte[] aad = "header".getBytes(StandardCharsets.UTF_8);
        byte[] plain = "hello secure world".getBytes(
                StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("ChaCha20-Poly1305");
        encrypt.init(Cipher.ENCRYPT_MODE, key,
                new IvParameterSpec(nonce));
        encrypt.updateAAD(aad);
        byte[] ciphertext = encrypt.doFinal(plain);

        Cipher decrypt = Cipher.getInstance("ChaCha20-Poly1305");
        decrypt.init(Cipher.DECRYPT_MODE, key,
                new IvParameterSpec(nonce));
        decrypt.updateAAD(aad);
        byte[] recovered = decrypt.doFinal(ciphertext);

        byte[] tampered = ciphertext.clone();
        tampered[tampered.length - 1] ^= 1;
        boolean rejected = false;
        try {
            Cipher bad = Cipher.getInstance("ChaCha20-Poly1305");
            bad.init(Cipher.DECRYPT_MODE, key,
                    new IvParameterSpec(nonce));
            bad.updateAAD(aad);
            bad.doFinal(tampered);
        } catch (AEADBadTagException expected) {
            rejected = true;
        }

        System.out.println("roundTrip = " +
                Arrays.equals(plain, recovered));
        System.out.println("tamperRejected = " + rejected);
        System.out.println("nonceBytes = " + nonce.length);
    }
}
```

```bash
javac ChaCha20Poly1305Demo.java
java ChaCha20Poly1305Demo
```

```text
roundTrip = true
tamperRejected = true
nonceBytes = 12
```

ChaCha20-Poly1305 cũng yêu cầu nonce unique theo key. Việc lựa chọn giữa AES-GCM và ChaCha20-Poly1305 phụ thuộc phần cứng, protocol interoperability, provider và policy.

## 8. Hash và HMAC

### 8.1. SHA-256 digest

Lưu `Sha256DigestDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public class Sha256DigestDemo {
    public static void main(String[] args) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest("abc".getBytes(StandardCharsets.UTF_8));

        System.out.println("algorithm = SHA-256");
        System.out.println("digestBytes = " + digest.length);
        System.out.println("knownVector = " +
                HexFormat.of().formatHex(digest).equals(
                "ba7816bf8f01cfea414140de5dae2223" +
                "b00361a396177a9cb410ff61f20015ad"));
    }
}
```

```bash
javac Sha256DigestDemo.java
java Sha256DigestDemo
```

```text
algorithm = SHA-256
digestBytes = 32
knownVector = true
```

Digest không có secret key. Dùng cho checksum/fingerprint trong bối cảnh phù hợp; để xác thực message dùng HMAC hoặc signature.

### 8.2. HMAC-SHA-256

Lưu `HmacSha256Demo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public class HmacSha256Demo {
    public static void main(String[] args) throws Exception {
        SecretKey key = KeyGenerator.getInstance("HmacSHA256")
                .generateKey();
        byte[] message = "transfer:42".getBytes(
                StandardCharsets.UTF_8);

        Mac signer = Mac.getInstance("HmacSHA256");
        signer.init(key);
        byte[] tag = signer.doFinal(message);

        Mac verifier = Mac.getInstance("HmacSHA256");
        verifier.init(key);
        byte[] expected = verifier.doFinal(message);

        Mac wrong = Mac.getInstance("HmacSHA256");
        wrong.init(key);
        byte[] modified = wrong.doFinal(
                "transfer:43".getBytes(StandardCharsets.UTF_8));

        System.out.println("macBytes = " + tag.length);
        System.out.println("valid = " +
                MessageDigest.isEqual(tag, expected));
        System.out.println("modifiedMessageValid = " +
                MessageDigest.isEqual(tag, modified));
    }
}
```

```bash
javac HmacSha256Demo.java
java HmacSha256Demo
```

```text
macBytes = 32
valid = true
modifiedMessageValid = false
```

Production cần key management, rotation và key separation. Không dùng cùng một key tùy tiện cho AES encryption và HMAC. Dùng KDF/context để tạo subkey độc lập nếu protocol cần nhiều mục đích.

## 9. Chữ ký số: Ed25519 và RSA-PSS

Chọn signature dựa trên protocol, key lifecycle, interoperability, certificate ecosystem và compliance:

- **Ed25519:** chữ ký elliptic-curve hiện đại, ít tham số cấu hình.
- **RSASSA-PSS:** chữ ký RSA với padding PSS; phải thống nhất hash, MGF và salt length.
- **ECDSA:** vẫn có trong nhiều certificate/protocol; chọn curve/hash theo policy.
- **ML-DSA:** chữ ký hậu lượng tử được hỗ trợ trong JDK 27 provider hiện hành.

### 9.1. Ed25519

Lưu `Ed25519SignatureDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class Ed25519SignatureDemo {
    private static boolean verify(
            KeyPair pair, byte[] message, byte[] bytes)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        return verifier.verify(bytes);
    }

    public static void main(String[] args) throws Exception {
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        byte[] message = "document-v1".getBytes(
                StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        byte[] modified = "document-v2".getBytes(
                StandardCharsets.UTF_8);

        System.out.println("signatureBytes = " + signature.length);
        System.out.println("verified = " +
                verify(pair, message, signature));
        System.out.println("modifiedRejected = " +
                !verify(pair, modified, signature));
    }
}
```

```bash
javac Ed25519SignatureDemo.java
java Ed25519SignatureDemo
```

```text
signatureBytes = 64
verified = true
modifiedRejected = true
```

Private key phải được bảo vệ; public key phải được xác thực nguồn trước khi tin. Signature đúng về toán học với một public key không đáng tin **không** chứng minh danh tính người ký.

### 9.2. RSASSA-PSS

Lưu `RsaPssSignatureDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public class RsaPssSignatureDemo {
    private static final PSSParameterSpec PARAMS =
            new PSSParameterSpec("SHA-256", "MGF1",
                    MGF1ParameterSpec.SHA256, 32, 1);

    private static boolean verify(
            KeyPair pair, byte[] message, byte[] bytes)
            throws Exception {
        Signature verifier =
                Signature.getInstance("RSASSA-PSS");
        verifier.setParameter(PARAMS);
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        return verifier.verify(bytes);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        byte[] message = "signed-content".getBytes(
                StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.setParameter(PARAMS);
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        System.out.println("signatureBytes = " + signature.length);
        System.out.println("verified = " +
                verify(pair, message, signature));
    }
}
```

```bash
javac RsaPssSignatureDemo.java
java RsaPssSignatureDemo
```

```text
signatureBytes = 256
verified = true
```

RSA 2048 trong ví dụ chỉ minh họa API. Kích thước key thực tế phải theo policy, thời gian cần bảo vệ dữ liệu, certificate profile và đối tác. Không xem ngưỡng tối thiểu trong disabled-algorithm policy là khuyến nghị cho thiết kế mới.

## 10. Key agreement và KDF

`X25519` hoặc `ECDH` giúp hai bên tạo shared secret. Shared secret không nên được dùng trực tiếp như key cho mọi mục đích. Đưa nó qua KDF như HKDF với context phù hợp để tạo subkey riêng.

Lưu `X25519AgreementDemo.java`:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import javax.crypto.KeyAgreement;

public class X25519AgreementDemo {
    private static byte[] agree(
            java.security.PrivateKey own,
            java.security.PublicKey peer) throws Exception {
        KeyAgreement agreement =
                KeyAgreement.getInstance("X25519");
        agreement.init(own);
        agreement.doPhase(peer, true);
        return agreement.generateSecret();
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("X25519");
        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();

        byte[] aliceSecret = agree(
                alice.getPrivate(), bob.getPublic());
        byte[] bobSecret = agree(
                bob.getPrivate(), alice.getPublic());

        System.out.println("secretBytes = " + aliceSecret.length);
        System.out.println("sharedSecretEqual = " +
                MessageDigest.isEqual(aliceSecret, bobSecret));
    }
}
```

```bash
javac X25519AgreementDemo.java
java X25519AgreementDemo
```

```text
secretBytes = 32
sharedSecretEqual = true
```

Demo không xác thực public key của peer, không tự chống MITM và không ràng buộc protocol transcript. Protocol thực tế cần certificate/signature hoặc cơ chế xác thực phù hợp.

### 10.1. HKDF

HKDF dùng HMAC làm thành phần extract/expand để dẫn xuất key từ secret có entropy. Có thể tạo key riêng cho từng hướng truyền, từng protocol version hoặc từng mục đích.

Oracle JDK 27 SunJCE liệt kê `HKDF-SHA256`, `HKDF-SHA384` và `HKDF-SHA512`. Đây là capability theo JDK/provider; hãy kiểm tra runtime khác trước khi triển khai.

Không dùng HKDF để biến password yếu thành key an toàn. Password cần password KDF có work factor hoặc memory cost.

### 10.2. PBKDF2 khi policy yêu cầu

Java provider có thể cung cấp `PBKDF2WithHmacSHA256`. Luồng tổng quát:

```java
byte[] salt = new byte[16];
new SecureRandom().nextBytes(salt);

int iterations = configuredPasswordWorkFactor;
PBEKeySpec spec = new PBEKeySpec(
        passwordChars, salt, iterations, 256);

SecretKeyFactory factory =
        SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
byte[] derived = factory.generateSecret(spec).getEncoded();
spec.clearPassword();
```

*Snippet minh họa. `configuredPasswordWorkFactor` phải được chọn theo policy và benchmark; lưu salt, algorithm, parameters/version cùng password hash để có thể verify và migrate.*

Mỗi password cần salt riêng, ngẫu nhiên. Không hard-code salt, không dùng một iteration count cũ vĩnh viễn và không tự chế password hashing algorithm.

## 11. SecureRandom

Dùng `SecureRandom` cho key generation, nonce/IV, salt, token và challenge. Không dùng `java.util.Random` hoặc `ThreadLocalRandom` cho key/token/salt/nonce.

Lưu `SecureRandomSelectionDemo.java`:

```java
import java.security.SecureRandom;

public class SecureRandomSelectionDemo {
    public static void main(String[] args) {
        SecureRandom random = new SecureRandom();
        byte[] token = new byte[32];
        random.nextBytes(token);

        System.out.println("bytesGenerated = " + token.length);
        System.out.println("algorithmPresent = " +
                !random.getAlgorithm().isBlank());
        System.out.println("providerPresent = " +
                (random.getProvider() != null));
    }
}
```

```bash
javac SecureRandomSelectionDemo.java
java SecureRandomSelectionDemo
```

```text
bytesGenerated = 32
algorithmPresent = true
providerPresent = true
```

`new SecureRandom()` để runtime chọn implementation theo provider preference. `SecureRandom.getInstanceStrong()` lấy implementation theo security property `securerandom.strongAlgorithms`; nó có thể có latency/behavior khác. Chọn theo yêu cầu thực tế và test trên môi trường triển khai.

Không seed thủ công bằng timestamp, PID, chuỗi cố định hoặc số tự tạo. `SecureRandom` tự khởi tạo entropy; `setSeed` không phải cách “tăng độ ngẫu nhiên” bằng một giá trị đoán được.

## 12. Thuật toán hậu lượng tử trong JDK 27

Oracle JDK 27 provider documentation liệt kê:

- **ML-KEM** cho key encapsulation.
- **ML-DSA** cho chữ ký số.
- ML-KEM-512/768/1024 và ML-DSA-44/65/87.
- Các dịch vụ KEM/KDF liên quan để kết hợp với crypto đối xứng.

Các API này phụ thuộc JDK/provider. Không giả định Java 17 hoặc mọi JDK vendor đều hỗ trợ. Oracle/OpenJDK 24+ có ML-KEM và ML-DSA trong provider; JDK 27 tiếp tục hỗ trợ.

### 12.1. ML-KEM tạo shared secret, không mã hóa payload trực tiếp

ML-KEM encapsulation tạo một encapsulation và shared secret. Receiver decapsulate bằng private key để có cùng secret. Sau đó dùng KDF để dẫn xuất key, rồi AEAD để mã hóa dữ liệu.

```text
Receiver tạo ML-KEM key pair
          |
          | gửi public key
          v
Sender encapsulate(public key)
          |
          +--> encapsulation
          +--> shared secret
                    |
                    | KDF + context
                    v
                 AEAD key
                    |
                    v
               encrypt payload

Receiver decapsulate(private key, encapsulation)
          |
          v
      same shared secret
          |
          v
      same KDF + context
          |
          v
      AEAD decrypt + verify tag
```

Lưu `PostQuantumAlgorithmsDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.Signature;
import java.security.spec.NamedParameterSpec;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class PostQuantumAlgorithmsDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator kemGenerator =
                KeyPairGenerator.getInstance("ML-KEM");
        kemGenerator.initialize(
                new NamedParameterSpec("ML-KEM-768"));
        KeyPair recipient = kemGenerator.generateKeyPair();

        KEM kem = KEM.getInstance("ML-KEM");
        KEM.Encapsulated encapsulated =
                kem.newEncapsulator(recipient.getPublic())
                        .encapsulate();
        SecretKey recovered =
                kem.newDecapsulator(recipient.getPrivate())
                        .decapsulate(encapsulated.encapsulation());

        KeyPairGenerator signatureGenerator =
                KeyPairGenerator.getInstance("ML-DSA");
        signatureGenerator.initialize(
                new NamedParameterSpec("ML-DSA-65"));
        KeyPair signerPair = signatureGenerator.generateKeyPair();

        byte[] message = "post-quantum-demo".getBytes(
                StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("ML-DSA");
        signer.initSign(signerPair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("ML-DSA");
        verifier.initVerify(signerPair.getPublic());
        verifier.update(message);

        System.out.println("kemSecretMatches = " +
                MessageDigest.isEqual(
                        encapsulated.key().getEncoded(),
                        recovered.getEncoded()));
        System.out.println("mlKemEncapsulationBytes = " +
                encapsulated.encapsulation().length);
        System.out.println("mlDsaVerified = " +
                verifier.verify(signature));
    }
}
```

```bash
javac PostQuantumAlgorithmsDemo.java
java PostQuantumAlgorithmsDemo
```

Stdout trên Oracle/OpenJDK 24+ có hỗ trợ ML-KEM/ML-DSA:

```text
kemSecretMatches = true
mlKemEncapsulationBytes = 1088
mlDsaVerified = true
```

Kích thước encapsulation 1088 bytes trong ví dụ tương ứng ML-KEM-768. Demo chỉ kiểm tra API, không phải protocol production. Production còn cần xác thực public key, protocol framing, KDF context, key rotation, interoperability và xử lý lỗi.

### 12.2. TLS hybrid key exchange trong JDK 27

Oracle JDK 27 JSSE hỗ trợ post-quantum hybrid key exchange cho TLS 1.3. Named group `X25519MLKEM768` được ưu tiên mặc định; nếu peer hỗ trợ, handshake có thể dùng kết hợp X25519 và ML-KEM-768. Một số hybrid group khác có thể được bật theo cấu hình.

Ứng dụng dùng `javax.net.ssl` nên để JSSE xử lý handshake và negotiation. Không tự ghép X25519 + ML-KEM thành protocol transport riêng. JDK 27 cho phép tùy chỉnh named groups qua `jdk.tls.namedGroups` hoặc `SSLParameters.setNamedGroups`; chỉ thay đổi khi có lý do interoperability/policy và đã test cả hai phía.

## 13. TLS và security properties

Đối với giao tiếp mạng, dùng JSSE với `SSLContext`, `SSLSocket` hoặc `SSLEngine` và TLS hiện hành. Đừng tự chọn từng primitive rồi lắp thành protocol thay TLS.

### 13.1. Các security properties quan trọng

| Property | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| `jdk.crypto.disabledAlgorithms` | JCA/JCE services | Có thể chặn service/algorithm cụ thể |
| `jdk.certpath.disabledAlgorithms` | Certificate path | Giới hạn thuật toán/key khi kiểm tra certificate chain |
| `jdk.tls.disabledAlgorithms` | TLS/DTLS | Chặn protocol version, cipher suite, key exchange hoặc điều kiện key yếu |
| `jdk.tls.legacyAlgorithms` | TLS/DTLS negotiation | Thuật toán legacy thường chỉ được chọn khi không còn ứng viên khác |
| `jdk.tls.keyLimits` | TLS record protection | Giới hạn lượng dữ liệu dùng với một key/cipher trong TLS |

**Disabled khác legacy.** Một thuật toán trong `jdk.tls.disabledAlgorithms` bị cấm trong phạm vi policy tương ứng. Một thuật toán trong `jdk.tls.legacyAlgorithms` được đánh dấu là lựa chọn cuối khi không còn lựa chọn khác. Không diễn giải legacy list thành khuyến nghị dùng cho hệ thống mới.

Oracle JDK 27 liệt kê các TLS restrictions mặc định bao gồm SSLv3, TLSv1, TLSv1.1, DTLSv1.0, RC4, DES, MD5withRSA, 3DES, anonymous/NULL cipher suites và một số key exchange/signature/key-size conditions. CertPath policy cũng có điều kiện với MD2/MD5/SHA-1 trong một số ngữ cảnh và các key size thấp.

Các giá trị đó là policy của Oracle JDK 27, không phải quy tắc bất biến của mọi JDK vendor. File `<java-home>/conf/security/java.security` là nơi kiểm tra giá trị thực tế. JDK update có thể thay đổi danh sách.

### 13.2. Đọc policy runtime

`Security.getProperty` đọc security properties; chúng khác với system properties thông thường.

```java
String tlsDisabled =
        Security.getProperty("jdk.tls.disabledAlgorithms");
String certDisabled =
        Security.getProperty("jdk.certpath.disabledAlgorithms");
```

*Snippet minh họa.*

Không copy giá trị property từ blog cũ rồi áp vào production. Hãy kiểm tra đúng JDK vendor/build, security configuration và command line. Một số property chỉ được Oracle JSSE/provider cụ thể sử dụng; không bảo đảm mọi JDK implementation áp dụng giống nhau.

Lưu `CryptoPolicyInspectionDemo.java`:

```java
import java.security.Security;

public class CryptoPolicyInspectionDemo {
    public static void main(String[] args) {
        String[] names = {
            "jdk.crypto.disabledAlgorithms",
            "jdk.certpath.disabledAlgorithms",
            "jdk.tls.disabledAlgorithms",
            "jdk.tls.legacyAlgorithms",
            "securerandom.strongAlgorithms"
        };

        System.out.println("propertiesChecked = " + names.length);
        System.out.println("certPathPolicyPresent = " +
                (Security.getProperty(
                        "jdk.certpath.disabledAlgorithms") != null));
        System.out.println("tlsPolicyPresent = " +
                (Security.getProperty(
                        "jdk.tls.disabledAlgorithms") != null));
        System.out.println("tlsLegacyPolicyPresent = " +
                (Security.getProperty(
                        "jdk.tls.legacyAlgorithms") != null));
        System.out.println("strongRandomPolicyPresent = " +
                (Security.getProperty(
                        "securerandom.strongAlgorithms") != null));
    }
}
```

```bash
javac CryptoPolicyInspectionDemo.java
java CryptoPolicyInspectionDemo
```

Ví dụ kiểm tra sự tồn tại của property, không xác định một algorithm cụ thể có được phép hay không. `jdk.crypto.disabledAlgorithms` có thể không được đặt trong một số cấu hình mặc định; hãy đọc giá trị thật của runtime.

### 13.3. Kiểm tra TLS defaults

Oracle JDK cung cấp:

```bash
java -XshowSettings:security:tls -version
keytool -showinfo -tls
```

Output phản ánh runtime đang chạy. Đối chiếu với disabled-algorithm policy vì một cipher suite có thể được provider implement nhưng không được negotiation policy cho phép.

Nếu ứng dụng cần giới hạn bổ sung, `SSLParameters.setAlgorithmConstraints` cho phép đặt `AlgorithmConstraints` của ứng dụng. Đây là lớp bổ sung, không thay thế việc cập nhật JDK hoặc hiểu security properties.

## 14. Keystore và quản lý key

`KeyStore` là container lưu key/certificate, không phải thuật toán mã hóa payload.

Từ JDK 9, `PKCS12` là default/recommended keystore type. Oracle JDK 27 cảnh báo `JKS` và `JCEKS` sẽ bị loại bỏ trong tương lai vì dùng thuật toán cũ; tài liệu khuyến nghị migrate sang PKCS12.

Lưu `Pkcs12RoundTripDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.security.KeyStore;
import java.util.Arrays;

public class Pkcs12RoundTripDemo {
    public static void main(String[] args) throws Exception {
        char[] password = "demo-only-password".toCharArray();

        KeyStore original = KeyStore.getInstance("PKCS12");
        original.load(null, password);

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        original.store(bytes, password);

        KeyStore restored = KeyStore.getInstance("PKCS12");
        restored.load(new ByteArrayInputStream(bytes.toByteArray()),
                password);

        System.out.println("type = " + restored.getType());
        System.out.println("roundTrip = " +
                (restored.size() == original.size()));
        System.out.println("aliases = " + restored.size());

        Arrays.fill(password, (char) 0);
    }
}
```

```bash
javac Pkcs12RoundTripDemo.java
java Pkcs12RoundTripDemo
```

```text
type = PKCS12
roundTrip = true
aliases = 0
```

Demo dùng keystore rỗng để kiểm tra format. Production phải quản lý password/secret, quyền file, backup, rotation và certificate chain. Không ghi password vào source hoặc command-line logs.

### 14.1. Không nhầm keystore format với provider

`KeyStore.getInstance("PKCS12")` yêu cầu format PKCS12; JCA vẫn chọn provider hỗ trợ format đó. `KeyStore.getInstance("PKCS11")` có ý nghĩa khác: truy cập token/hardware qua PKCS#11 provider. Phân biệt file keystore với hardware keystore.

## 15. Availability không đồng nghĩa policy permission

Một lần `getInstance` thành công chỉ chứng minh JCA tìm được service. Nó chưa chứng minh:

- key size/type/curve phù hợp;
- parameters hợp lệ;
- security constraints cho phép;
- provider đang ở compliance mode cần thiết;
- peer/protocol hỗ trợ cùng thuật toán;
- certificate path hợp lệ;
- cipher suite được negotiation.

| Lỗi | Cần kiểm tra |
| --- | --- |
| `NoSuchAlgorithmException` | Standard name, provider service, JDK version |
| `NoSuchProviderException` | Provider đã cài/đăng ký và tên đúng chưa |
| `InvalidKeyException` | Key type/size/format có tương thích không |
| `InvalidAlgorithmParameterException` | IV, nonce, tag size, curve hoặc parameter spec |
| `AEADBadTagException` | Key/nonce/AAD/ciphertext có khớp? Tampering? |
| TLS handshake failure | Protocol/cipher/key exchange/certificate/peer policy |
| CertPath validation failure | Chain, validity, trust anchor, revocation, disabled constraints |

Không catch mọi exception rồi fallback sang thuật toán yếu hơn. Nếu AES-GCM thất bại vì nonce parameters sai, chuyển xuống ECB không sửa nguyên nhân và còn làm giảm bảo mật.

## 16. Những lựa chọn không nên dùng cho thiết kế mới

| Không nên dùng | Vấn đề | Hướng thay thế |
| --- | --- | --- |
| DES, RC4, 3DES | Legacy, bảo mật không còn phù hợp | AES-GCM hoặc ChaCha20-Poly1305 |
| AES/ECB | Làm lộ pattern plaintext | AEAD |
| CBC không authentication | Không tự bảo vệ integrity | AEAD; nếu legacy phải có design Encrypt-then-MAC đã review |
| MD5/SHA-1 cho signature mới | Không phù hợp yêu cầu collision resistance | SHA-256/SHA-384/SHA-3 và signature phù hợp |
| SHA-256(password) một lượt | Dò password offline nhanh | Password KDF có work factor |
| `new Random()` cho token/key | Không phải CSPRNG | `SecureRandom` |
| GCM nonce reuse | Phá vỡ AEAD security | Nonce unique per key, usage limits, rotation |
| Shared secret dùng trực tiếp cho mọi key | Thiếu key separation/context | KDF và subkey theo purpose |
| Tự ghép primitives thành protocol | Dễ thiếu authentication/replay defense | TLS hoặc protocol đã được review |

Một số thuật toán cũ vẫn có trong JDK để đọc dữ liệu legacy. Có mặt trong provider **không** có nghĩa được khuyến nghị hoặc policy cho phép ở mọi ngữ cảnh.

Không sửa `java.security` để bật lại MD5/SHA-1/DES/TLS cũ chỉ nhằm làm peer chưa cập nhật tiếp tục hoạt động. Hãy nâng cấp peer, certificate, protocol hoặc xây migration có thời hạn và được security team phê duyệt.

## 17. Hiệu năng, compatibility và vận hành

Khi chọn provider/algorithm, xem xét:

- JDK vendor/build và OS.
- Provider/service availability và preference order.
- Hardware acceleration, HSM, PKCS#11 và native provider.
- Compliance, FIPS validation và approved mode.
- Key type/size, storage, rotation, revocation.
- Peer interoperability và protocol versions.
- Disabled algorithm properties và key-size constraints.
- Throughput, latency, allocations, HSM round trips.
- Migration dữ liệu mã hóa/certificate cũ.

Không benchmark một thuật toán bằng một lần chạy trong `main`. Dùng JMH hoặc workload tích hợp, warmup và nhiều lần chạy; đo throughput, latency p95/p99 và allocation khi cần.

### 17.1. Khi nâng JDK

Bản JDK mới có thể thêm algorithm/service, đổi provider preference, siết security property, tắt protocol cũ hoặc thêm post-quantum key exchange. Sau khi nâng JDK, chạy regression tests cho decrypt dữ liệu cũ, signature verification, CertPath, TLS handshake, keystore load, HSM connectivity và interoperability.

### 17.2. Compatibility matrix tối thiểu

| Hạng mục | Ghi nhận |
| --- | --- |
| JDK | Vendor, major version, update/build |
| Provider | Tên, version, preference order, native module |
| Algorithm | Standard name, transformation, parameters |
| Key | Type, size, curve, origin, lifecycle |
| Policy | Security properties, FIPS mode, constraints |
| Peer | Protocol, signature schemes, named groups |
| Tests | Positive, negative, tampering, rotation, migration |

## 18. Chương trình kiểm tra availability phổ thông

Lưu `CurrentCryptoAvailabilityDemo.java`:

```java
import java.security.MessageDigest;
import java.security.Signature;
import javax.crypto.Cipher;

public class CurrentCryptoAvailabilityDemo {
    public static void main(String[] args) throws Exception {
        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        Cipher aesGcm = Cipher.getInstance("AES/GCM/NoPadding");
        Cipher chacha = Cipher.getInstance("ChaCha20-Poly1305");
        Signature ed = Signature.getInstance("Ed25519");

        System.out.println("sha256 = " + sha.getAlgorithm());
        System.out.println("aesGcm = " + aesGcm.getAlgorithm());
        System.out.println("chacha = " + chacha.getAlgorithm());
        System.out.println("ed25519 = " + ed.getAlgorithm());
        System.out.println("allResolved = true");
    }
}
```

```bash
javac CurrentCryptoAvailabilityDemo.java
java CurrentCryptoAvailabilityDemo
```

```text
sha256 = SHA-256
aesGcm = AES/GCM/NoPadding
chacha = ChaCha20-Poly1305
ed25519 = Ed25519
allResolved = true
```

Đây là availability smoke test. Trên runtime khác, một service có thể không có; hãy xử lý `NoSuchAlgorithmException` và chọn giải pháp theo policy đã thiết kế, không tự động downgrade.

## 19. Bài tập thực hành

**Bài 1 — Provider:** Chạy `ProviderInventoryDemo` trên hai JDK vendor. So sánh provider list và provider thực tế cho SHA-256/AES-GCM. Vì sao không nên hard-code SunJCE nếu không có policy?

**Bài 2 — Availability và policy:** `Cipher.getInstance("AES/GCM/NoPadding")` thành công. Nêu ba kiểm tra cần thiết trước khi kết luận operation production hợp lệ.

**Bài 3 — AEAD:** Sửa AAD trong `AesGcmRoundTripDemo` khi decrypt. Vì sao tag verification thất bại dù ciphertext không đổi?

**Bài 4 — Nonce:** Hai process cùng mã hóa bằng một key. Vì sao cần xem xét nonce collision/coordination, key usage limits và rotation?

**Bài 5 — HMAC:** Vì sao `MessageDigest.isEqual` phù hợp để so sánh tag hơn một vòng lặp dừng ngay ở byte khác đầu tiên?

**Bài 6 — Signature:** Ed25519 verify thành công nhưng public key đến từ nguồn không xác thực. Điều gì vẫn chưa được chứng minh?

**Bài 7 — Key agreement:** X25519 tạo cùng shared secret ở hai phía. Cần cơ chế nào để chống MITM và ràng buộc protocol context?

**Bài 8 — Policy:** Phân biệt `jdk.crypto.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms`, `jdk.tls.disabledAlgorithms` và `jdk.tls.legacyAlgorithms`.

**Bài 9 — Hậu lượng tử:** Vì sao ML-KEM output cần qua KDF rồi mới dùng làm key AES-GCM? ML-KEM có phải cipher mã hóa file không?

**Bài 10 — TLS 1.3:** Trên Oracle JDK 27, `X25519MLKEM768` được ưu tiên trong trường hợp nào? Vì sao không tự triển khai handshake?

**Bài 11 — FIPS:** Liệt kê thông tin cần xác minh trước khi tuyên bố ứng dụng đang chạy trong FIPS approved mode.

**Bài 12 — Migration:** Dịch vụ còn ciphertext AES-CBC cũ. Mô tả kế hoạch decrypt/migrate sang AEAD mà không dùng CBC cho dữ liệu mới.

## 20. Checklist trước khi release

- Mục đích là encryption, digest, MAC, signature, key agreement, KDF hay password storage?
- Tên thuật toán chuẩn và transformation đã ghi đầy đủ?
- Thuật toán phù hợp threat model và policy hiện hành?
- Provider thực tế đã được ghi nhận; có yêu cầu compliance/HSM/FIPS?
- Nếu pin provider, đã xác minh exact version, registration và approved mode?
- Key type/size/curve, generation, storage, rotation và revocation có rõ?
- Random values dùng `SecureRandom`, không seed bằng dữ liệu đoán được?
- AEAD nonce unique per key; tag và AAD được verify?
- Digest không bị dùng thay HMAC/signature/password KDF?
- Shared secret qua KDF với context và purpose-specific subkeys?
- Password hashing có salt riêng, work factor và migration policy?
- TLS dùng JSSE và policy phù hợp; không bật protocol/cipher cũ để né lỗi?
- Security properties được đọc từ JDK vendor/build đang triển khai?
- Có integration test với provider/HSM/PKCS#11 thật?
- Có test tampering, invalid parameters, wrong key, certificate expiry và policy rejection?
- Có test với peer/protocol/client version production?
- Nâng JDK đã test algorithms, providers, disabled properties và TLS negotiation?
- Có kế hoạch migration ciphertext, certificate, key store và signatures cũ?
- Không có key/password/token thật trong source, log hoặc test fixtures?

## 21. Tài liệu chính thức hiện hành

- Oracle Java SE 27 — JCA Reference Guide: https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html
- Oracle Java SE 27 — JDK Providers Documentation: https://docs.oracle.com/en/java/javase/27/security/oracle-providers.html
- Oracle Java SE 27 — Java Security Standard Algorithm Names: https://docs.oracle.com/en/java/javase/27/docs/specs/security/standard-names.html
- Oracle Java SE 27 — JSSE Reference Guide, disabled algorithms, TLS and hybrid key exchange: https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html
- Oracle Java SE 27 — Security Developer's Guide: https://docs.oracle.com/en/java/javase/27/security/index.html
- Oracle JDK 27 Release Notes, published 15 September 2026: https://www.oracle.com/java/technologies/javase/27-relnote-issues.html
- Oracle JDK 27 Significant Changes: https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html
- NIST FIPS 203 — ML-KEM: https://csrc.nist.gov/pubs/fips/203/final
- NIST FIPS 204 — ML-DSA: https://csrc.nist.gov/pubs/fips/204/final

**Ghi nhớ:** Provider là implementation; thuật toán là primitive; security properties là policy; protocol và key lifecycle quyết định cách kết hợp. Với ứng dụng phổ thông, dùng standard algorithm names và để JCA chọn provider. Chỉ pin provider khi có yêu cầu đã được xác minh. Với thiết kế mới, ưu tiên AEAD, SHA-2/SHA-3, HMAC, Ed25519/RSASSA-PSS hoặc lựa chọn phù hợp policy; dùng SecureRandom; bảo vệ nonce và key. Đọc runtime security properties thay vì copy danh sách cũ. Trên Oracle JDK 27, ML-KEM/ML-DSA và hybrid TLS key exchange là những khả năng hiện hành cần đưa vào kế hoạch interoperability và migration.