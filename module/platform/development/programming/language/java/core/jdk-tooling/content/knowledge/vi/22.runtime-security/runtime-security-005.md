# Mật mã được hỗ trợ trong Java

## Mục tiêu

Sau bài này, bạn có thể hiểu các nhóm dịch vụ mật mã mà Java cung cấp; phân biệt API, thuật toán và provider; tra cứu thuật toán được hỗ trợ trong một JDK cụ thể; chọn đúng tên chuẩn cho Cipher, MessageDigest, Signature, Mac, KeyAgreement, KDF và KEM; hiểu khác biệt giữa thuật toán có sẵn và thuật toán phù hợp về bảo mật; sử dụng AES-GCM trong một chương trình Java hoàn chỉnh; kiểm tra provider, TLS và security properties; và lập kế hoạch kiểm thử mật mã khi nâng cấp JDK hoặc triển khai trên nhiều nền tảng.

## 1. "Mật mã được hỗ trợ" có nghĩa là gì?

Java không cung cấp một hàm mật mã duy nhất. Nền tảng có một tập API bảo mật và nhiều implementation có thể được cài đặt thông qua **Cryptographic Service Provider (provider)**.

Khi nói một thuật toán được Java hỗ trợ, cần phân biệt ít nhất bốn ý:

1. **Tên chuẩn:** Java định nghĩa tên để ứng dụng yêu cầu dịch vụ, ví dụ AES, SHA-256, SHA256withRSA hoặc TLSv1.3.
2. **API/engine:** lớp Java cung cấp thao tác, ví dụ Cipher, MessageDigest, Signature, Mac, KeyPairGenerator hoặc SSLContext.
3. **Provider:** implementation thực tế cung cấp thuật toán đó, ví dụ SunJCE, SUN, SunRsaSign, SunEC hoặc SunJSSE.
4. **Chính sách runtime:** thuật toán có thể có implementation nhưng bị giới hạn hoặc vô hiệu hóa bởi security properties, key size, protocol configuration, provider configuration hoặc chính sách của tổ chức.

Vì vậy, tên thuật toán có trong tài liệu không có nghĩa mọi JDK, mọi provider hoặc mọi cấu hình đều cho phép dùng nó. Một provider bên thứ ba cũng không bắt buộc phải hỗ trợ toàn bộ thuật toán mà Java SE yêu cầu implementation Java SE hỗ trợ.

Bài này dùng JDK 26 làm mốc tham chiếu cho danh sách provider và các thuật toán mới. Ví dụ thực hành AES-GCM tương thích JDK 17 trở lên.

## 2. Java Cryptography Architecture (JCA) và provider

**Java Cryptography Architecture (JCA)** là kiến trúc API và provider của Java để ứng dụng sử dụng dịch vụ bảo mật mà không phải tự cài đặt thuật toán. Java Cryptography Extension (JCE), từng được phân phối riêng trong các phiên bản Java cũ, hiện là một phần của JCA/JDK.

JCA có ba nguyên tắc chính:

- **Implementation independence:** ứng dụng gọi API chuẩn; provider thực hiện thuật toán.
- **Interoperability:** ứng dụng không nhất thiết phải phụ thuộc vào một implementation cụ thể; key và chữ ký có thể trao đổi giữa các provider tương thích.
- **Algorithm extensibility:** có thể cài provider bổ sung để cung cấp thuật toán hoặc phần cứng mật mã mà JDK mặc định không có.

### Engine class

Engine class là API cấp cao đại diện cho một loại dịch vụ mật mã. Một số engine thường gặp:

| Engine/API | Nhiệm vụ |
|---|---|
| SecureRandom | Sinh số ngẫu nhiên mật mã |
| MessageDigest | Tính hash/digest |
| Cipher | Mã hóa và giải mã |
| Mac | Tạo và xác minh Message Authentication Code |
| Signature | Ký số và xác minh chữ ký |
| KeyPairGenerator | Tạo cặp public/private key |
| KeyGenerator | Tạo secret key |
| KeyAgreement | Thỏa thuận shared secret |
| KEM | Đóng gói/giải đóng gói shared secret bằng cơ chế key encapsulation |
| KDF | Dẫn xuất key từ input keying material |
| KeyFactory | Chuyển đổi key và key specification |
| SecretKeyFactory | Chuyển đổi secret key và key specification |
| KeyStore | Quản lý key và certificate |
| CertificateFactory | Đọc certificate và CRL |
| CertPathBuilder / CertPathValidator | Xây dựng và xác minh certificate path |
| SSLContext | Cấu hình dịch vụ TLS/DTLS |

Mỗi engine gọi factory method getInstance để yêu cầu một thuật toán. JCA tìm provider có implementation phù hợp rồi trả về object engine.

Ví dụ:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
Signature signature = Signature.getInstance("SHA256withRSA");
~~~

Tên thuật toán được truyền vào getInstance là tên chuẩn hoặc alias mà provider hỗ trợ. Nên ưu tiên tên chuẩn trong Java Security Standard Algorithm Names để giảm khác biệt giữa các provider.

### Provider là gì?

Provider là một implementation đăng ký các dịch vụ và thuật toán với JCA. JDK thường có nhiều provider vì mỗi provider phụ trách một nhóm chức năng hoặc kết nối tới một nền tảng khác nhau.

| Provider thường gặp | Vai trò chính |
|---|---|
| SUN | Digest, SecureRandom, certificate/path services và một số signature/key services |
| SunRsaSign | RSA và RSASSA-PSS |
| SunJCE | Cipher, MAC, key generation, key agreement, KDF/KEM và password-based crypto |
| SunEC | Elliptic curve và Edwards-curve services |
| SunJSSE | TLS/DTLS, KeyManagerFactory và TrustManagerFactory |
| SunPKCS11 | Cầu nối tới thư viện PKCS#11, HSM và smart card đã cấu hình |
| SunMSCAPI | Cầu nối tới Windows cryptographic services và certificate/key stores |
| Apple | Tích hợp dịch vụ mật mã của nền tảng Apple trong JDK có hỗ trợ |
| Provider bên thứ ba | Thuật toán bổ sung, HSM, FIPS-validated module hoặc implementation chuyên biệt |

Không nên mặc định provider nào cũng có mặt trên mọi Java runtime. Ví dụ, SunMSCAPI phụ thuộc Windows; SunPKCS11 cần native PKCS#11 library và cấu hình token; provider bên thứ ba phải được cài và đăng ký.

### Cách JCA chọn provider

Nếu gọi:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

JCA tìm trong các provider đã đăng ký theo thứ tự ưu tiên và chọn provider có dịch vụ phù hợp.

Có thể yêu cầu provider cụ thể:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding", "SunJCE");
~~~

Ứng dụng thông thường nên để JCA chọn provider. Chỉ chỉ định provider khi có yêu cầu rõ ràng, chẳng hạn phải dùng HSM, token, provider đã được đánh giá/chứng nhận hoặc một cấu hình tương thích cụ thể. Gắn cứng tên provider làm ứng dụng phụ thuộc vào một runtime implementation và có thể ngăn việc dùng phần cứng tăng tốc khác.

## 3. Các nhóm thuật toán mật mã trong Java

### Hash/message digest

Hash nhận dữ liệu có độ dài bất kỳ và tạo digest có độ dài cố định. Hash không dùng secret key.

Một số tên chuẩn:

- SHA-256
- SHA-384
- SHA-512
- SHA3-256
- SHA3-384
- SHA3-512

Dùng MessageDigest:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] hash = digest.digest(data);
~~~

Hash phù hợp để kiểm tra tính toàn vẹn khi giá trị digest được bảo vệ hoặc so sánh qua một kênh đáng tin. Hash đơn thuần không xác thực người gửi: kẻ tấn công có thể sửa cả dữ liệu lẫn hash nếu không có cơ chế bảo vệ.

Không dùng MD5 hoặc SHA-1 cho thiết kế mới cần chống va chạm. Việc một JDK vẫn liệt kê một thuật toán cũ để tương thích không có nghĩa thuật toán đó còn phù hợp với mục đích bảo mật hiện nay.

### Mã hóa đối xứng

Mã hóa đối xứng dùng cùng secret key để mã hóa và giải mã. Java thường dùng Cipher với AES hoặc ChaCha20-Poly1305.

Một số transformation:

| Transformation | Ý nghĩa |
|---|---|
| AES/GCM/NoPadding | AES ở chế độ Galois/Counter Mode, có xác thực |
| AES/CBC/PKCS5Padding | AES-CBC với padding; cần MAC riêng và quy trình xác thực đúng |
| ChaCha20-Poly1305 | Mã hóa xác thực kết hợp ChaCha20 và Poly1305 |

Với dữ liệu ứng dụng mới, ưu tiên chế độ authenticated encryption như AES-GCM hoặc ChaCha20-Poly1305 khi các bên hỗ trợ. Chế độ này vừa mã hóa vừa phát hiện dữ liệu bị sửa.

Không dùng AES/ECB cho dữ liệu nhiều block. ECB làm lộ cấu trúc lặp của plaintext. Không gọi Cipher chỉ với tên AES rồi dựa vào mode/padding mặc định: mặc định có thể khác giữa provider. Luôn chỉ định đầy đủ algorithm/mode/padding.

### MAC (Message Authentication Code)

MAC dùng secret key chung để tạo mã xác thực thông điệp. Bên nhận có cùng key có thể xác minh dữ liệu có bị thay đổi hay không và có được tạo bởi bên nắm giữ key hay không.

Tên thường gặp:

- HmacSHA256
- HmacSHA384
- HmacSHA512

Dùng Mac:

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(secretKey);
byte[] tag = mac.doFinal(message);
~~~

MAC phù hợp khi các bên chia sẻ secret. Không thể dùng MAC để chứng minh danh tính công khai cho bên thứ ba vì mọi bên có cùng key đều có thể tạo tag hợp lệ.

### Chữ ký số

Chữ ký số dùng private key để ký và public key để xác minh. Nó hỗ trợ xác thực nguồn gốc và tính toàn vẹn của dữ liệu.

Tên thuật toán thường gặp:

- SHA256withRSA
- RSASSA-PSS
- SHA256withECDSA
- SHA384withECDSA
- Ed25519 / Ed448
- ML-DSA trong các provider JDK 26 có hỗ trợ

Dùng Signature:

~~~java
Signature signer = Signature.getInstance("SHA256withRSA");
signer.initSign(privateKey);
signer.update(message);
byte[] signed = signer.sign();
~~~

Bên nhận tạo Signature cùng thuật toán, gọi initVerify(publicKey), update(message) và verify(signed).

Hash, MAC và chữ ký không thay thế nhau. Hash không có secret; MAC dùng secret chung; chữ ký dùng private/public key.

### Key generation và key agreement

Các engine thường dùng:

- KeyPairGenerator: tạo cặp khóa RSA, EC, EdDSA, X25519 hoặc thuật toán khác mà provider hỗ trợ.
- KeyGenerator: tạo secret key như AES hoặc ChaCha20.
- KeyAgreement: hai bên dùng private/public key để cùng tạo shared secret, ví dụ ECDH hoặc X25519.
- KeyFactory: chuyển key encoding thành Java key object và ngược lại.

Tên thuật toán phổ biến gồm RSA, EC, Ed25519, X25519, DiffieHellman và ECDH. Kích thước key, curve và parameter phải phù hợp policy và khả năng tương thích của các bên.

### KDF và KEM

KDF (Key Derivation Function) dẫn xuất key từ input keying material và context. Ví dụ tên trong JDK 26 provider là HKDF-SHA256, HKDF-SHA384 và HKDF-SHA512. Với password, PBKDF2WithHmacSHA256 là một tên SecretKeyFactory phổ biến.

KEM (Key Encapsulation Mechanism) cho phép bên gửi đóng gói một shared secret để bên nhận giải đóng gói bằng private key. Nó là một building block cho giao thức thiết lập khóa, không phải API mã hóa file thay thế Cipher.

JDK 26 provider có hỗ trợ các thuật toán hậu lượng tử:

- ML-KEM-512, ML-KEM-768 và ML-KEM-1024 trong SunJCE.
- ML-DSA-44, ML-DSA-65 và ML-DSA-87 trong SUN.
- HKDF-SHA256/384/512 trong SunJCE.

ML-KEM là thuật toán key encapsulation theo FIPS 203; ML-DSA là chữ ký số theo FIPS 204. Đây là hỗ trợ của các provider JDK 26 cụ thể, không nên giả định có trong mọi JDK cũ hoặc mọi provider bên thứ ba. Khi dùng trong hệ thống thực tế, cần kiểm tra API, provider, format key, interoperability và protocol hỗ trợ ở cả hai đầu.

## 4. Một số thuật toán Java SE yêu cầu implementation hỗ trợ

Java Security Standard Algorithm Names quy định các tên chuẩn và một tập thuật toán mà implementation Java SE phải hỗ trợ. Đây là yêu cầu tương thích nền tảng; nó không phải bảng xếp hạng độ mạnh bảo mật.

Một số ví dụ đáng chú ý trong Java SE 26:

| Dịch vụ | Một số tên/biến thể được yêu cầu |
|---|---|
| Cipher | AES/GCM/NoPadding, ChaCha20-Poly1305, một số AES-CBC/ECB và RSA-OAEP transformations |
| MessageDigest | SHA-1, SHA-256, SHA-384 |
| Mac | HmacSHA1, HmacSHA256 |
| KeyGenerator | AES 128/256, ChaCha20, HmacSHA1, HmacSHA256 |
| KeyAgreement | DiffieHellman, ECDH với secp256r1/secp384r1, X25519 |
| Signature | SHA256withRSA, SHA384withRSA, SHA256withECDSA, SHA384withECDSA, RSASSA-PSS |
| SecretKeyFactory | PBKDF2WithHmacSHA256 |
| SSLContext | TLSv1.2, TLSv1.3 |
| KeyStore | PKCS12 |

Danh sách đầy đủ có thêm service, parameter, key size, curve và encoding. Không nên chép bảng này thành một cấu hình bảo mật cố định: yêu cầu implementation hỗ trợ không đồng nghĩa thuật toán nào cũng nên dùng.

JDK 26 có các provider hỗ trợ nhiều thuật toán hơn mức tối thiểu Java SE, bao gồm SHA-3, EdDSA, ML-DSA, ML-KEM và HKDF. Danh sách cụ thể phụ thuộc provider và phiên bản JDK.

## 5. Thuật toán có sẵn không đồng nghĩa thuật toán an toàn

Một JDK có thể vẫn cung cấp thuật toán cũ để đọc dữ liệu hoặc duy trì tương thích. Việc getInstance thành công chỉ cho biết provider tìm được implementation; nó không xác nhận thuật toán phù hợp với mục tiêu bảo mật.

| Thuật toán/chế độ | Cách nhìn khi thiết kế mới |
|---|---|
| AES-GCM | Lựa chọn authenticated encryption phổ biến; quản lý nonce đúng |
| ChaCha20-Poly1305 | AEAD phù hợp khi các bên hỗ trợ |
| AES-ECB | Tránh với dữ liệu nhiều block |
| AES-CBC | Chỉ dùng khi có quy trình padding và authentication an toàn; không tự coi ciphertext là đã xác thực |
| RSA-OAEP | Dùng khi cần RSA encryption; không dùng RSA raw |
| RSASSA-PSS | Chữ ký RSA có padding ngẫu nhiên, thường ưu tiên hơn PKCS#1 v1.5 cho thiết kế mới nếu hệ thống hỗ trợ |
| SHA-256/SHA-384/SHA-512 | Hash hiện đại cho nhiều mục đích |
| SHA-1/MD5 | Không dùng cho chữ ký/hash mới cần chống va chạm |
| DES/3DES/RC4 | Thuật toán cũ; tránh cho thiết kế mới |
| HmacSHA256 | MAC phổ biến khi các bên chia sẻ secret |
| PBKDF2WithHmacSHA256 | Password-based key derivation; cần salt riêng và cost phù hợp |

Một số nguyên tắc:

- Không tự thiết kế thuật toán, mode hoặc protocol mật mã.
- Không dùng hash nhanh như SHA-256 trực tiếp để lưu password. Dùng password KDF với salt ngẫu nhiên và cost được điều chỉnh; cân nhắc thuật toán password hashing chuyên dụng qua provider đã được đánh giá nếu chính sách yêu cầu.
- Không dùng Base64 như mã hóa; Base64 chỉ là encoding.
- Không dùng Random để tạo key, nonce hoặc token bảo mật; dùng SecureRandom.
- Không hard-code key trong source, config công khai hoặc log.
- Quản lý key lifecycle: tạo, phân phối, lưu, rotation, backup, thu hồi và xóa.
- Ưu tiên thư viện/protocol cấp cao như JSSE/TLS thay vì tự ghép Cipher và KeyAgreement thành protocol riêng.

## 6. Cách tra cứu thuật toán trên runtime đang chạy

Tài liệu JDK mô tả khả năng của một phiên bản/provider; ứng dụng vẫn cần kiểm tra runtime thực tế.

### Liệt kê provider

Chương trình sau liệt kê provider đã đăng ký và số dịch vụ mà mỗi provider công bố:

~~~java
import java.security.Provider;
import java.security.Security;

public class ProviderInventory {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println(
                    provider.getName() + " " + provider.getVersionStr()
                    + " services=" + provider.getServices().size());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ProviderInventory.java
java ProviderInventory
~~~

Tên, phiên bản và số service phụ thuộc JDK vendor, phiên bản, OS, provider đã cài và cấu hình runtime. Không nên đưa một output cố định vào test nếu môi trường hỗ trợ nhiều provider khác nhau.

### Liệt kê thuật toán theo provider

Có thể mở rộng chương trình để xem các service mà provider đăng ký:

~~~java
import java.security.Provider;
import java.security.Security;

public class AlgorithmInventory {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            for (Provider.Service service : provider.getServices()) {
                System.out.printf(
                        "%s | %s | %s%n",
                        provider.getName(),
                        service.getType(),
                        service.getAlgorithm());
            }
        }
    }
}
~~~

Lệnh chạy tương tự:

~~~bash
javac --release 17 AlgorithmInventory.java
java AlgorithmInventory
~~~

Output có thể dài và thay đổi theo runtime. Provider có thể đăng ký alias; vì vậy danh sách service là công cụ chẩn đoán, không phải bằng chứng đầy đủ rằng mọi transformation hoặc key parameter đều hoạt động.

### Kiểm tra một transformation cụ thể

Cách đơn giản nhất là yêu cầu đúng engine/algorithm mà ứng dụng định dùng:

~~~java
Cipher.getInstance("AES/GCM/NoPadding");
~~~

Nếu không có implementation phù hợp, API có thể ném NoSuchAlgorithmException hoặc NoSuchPaddingException. Việc lấy được object chưa chứng minh key size, parameter, mode, certificate hoặc policy của môi trường đều hợp lệ. Cần khởi tạo và chạy một test thực tế với key/parameter dự kiến.

### Dùng lệnh java để xem security configuration

JDK 26 hỗ trợ:

~~~bash
java -XshowSettings:security:providers -version
java -XshowSettings:security:tls -version
java -XshowSettings:security:properties -version
~~~

- security:providers hiển thị provider được cấu hình tĩnh.
- security:tls hiển thị thông tin TLS liên quan.
- security:properties hiển thị security properties.

Các lệnh này hữu ích khi so sánh môi trường local, CI và production. Provider có thể được thêm động khi ứng dụng chạy; khi đó hãy kiểm tra bằng Security.getProviders() trong chính JVM của ứng dụng.

## 7. Ví dụ hoàn chỉnh: mã hóa và giải mã AES-GCM

Ví dụ sau tạo AES key ngẫu nhiên, tạo nonce 96-bit bằng SecureRandom, mã hóa dữ liệu với AES-GCM rồi giải mã để xác nhận plaintext được khôi phục.

File SupportedCryptoDemo.java:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class SupportedCryptoDemo {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int NONCE_LENGTH = 12;
    private static final int TAG_LENGTH_BITS = 128;

    public static void main(String[] args) throws GeneralSecurityException {
        byte[] plaintext = "Java security".getBytes(StandardCharsets.UTF_8);

        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(256, new SecureRandom());
        SecretKey key = keyGenerator.generateKey();

        byte[] nonce = new byte[NONCE_LENGTH];
        new SecureRandom().nextBytes(nonce);

        Cipher encryptor = Cipher.getInstance(TRANSFORMATION);
        encryptor.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_LENGTH_BITS, nonce));
        byte[] ciphertext = encryptor.doFinal(plaintext);

        Cipher decryptor = Cipher.getInstance(TRANSFORMATION);
        decryptor.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_LENGTH_BITS, nonce));
        byte[] recovered = decryptor.doFinal(ciphertext);

        System.out.println("algorithm=" + encryptor.getAlgorithm());
        System.out.println("plaintext="
                + new String(recovered, StandardCharsets.UTF_8));
        System.out.println("verified=" + Arrays.equals(plaintext, recovered));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 SupportedCryptoDemo.java
java SupportedCryptoDemo
~~~

Output chính xác:

~~~text
algorithm=AES/GCM/NoPadding
plaintext=Java security
verified=true
~~~

### Giải thích

1. KeyGenerator tạo AES secret key 256-bit.
2. SecureRandom tạo nonce 12 byte (96-bit).
3. Cipher được yêu cầu transformation đầy đủ AES/GCM/NoPadding.
4. GCMParameterSpec đặt authentication tag length là 128-bit và cung cấp nonce.
5. doFinal mã hóa plaintext và gắn authentication tag vào ciphertext.
6. Cipher giải mã dùng cùng key và nonce; nếu ciphertext hoặc tag bị sửa, thao tác giải mã thất bại với lỗi xác thực, thường là AEADBadTagException.
7. Arrays.equals xác nhận plaintext sau giải mã trùng với dữ liệu ban đầu.

### Quy tắc bắt buộc với nonce GCM

Không bao giờ tái sử dụng cùng nonce với cùng key cho hai lần mã hóa GCM. Việc lặp nonce có thể làm lộ quan hệ giữa plaintext và phá vỡ bảo đảm xác thực của GCM.

Trong ví dụ, nonce được tạo ngẫu nhiên để minh họa. Hệ thống mã hóa nhiều dữ liệu dưới cùng một key cần thiết kế nonce generation/uniqueness theo giới hạn khối lượng, lưu trữ và phân phối của hệ thống. Lưu nonce cùng ciphertext thường là bình thường; nonce không cần bí mật nhưng phải được quản lý đúng.

Ví dụ chỉ để học API. Ứng dụng thật còn cần lưu key an toàn, gắn metadata/AAD khi phù hợp, version hóa format ciphertext, rotation key và kiểm soát truy cập.

## 8. Phân biệt các API theo mục tiêu

Chọn engine theo mục tiêu bảo mật:

| Nhu cầu | API phù hợp | Ví dụ |
|---|---|---|
| Tạo fingerprint dữ liệu | MessageDigest | SHA-256 |
| Xác thực message giữa các bên chia sẻ key | Mac | HmacSHA256 |
| Mã hóa dữ liệu có xác thực | Cipher | AES/GCM/NoPadding |
| Ký và xác minh dữ liệu | Signature | SHA256withRSA, Ed25519 |
| Sinh key đối xứng | KeyGenerator | AES |
| Sinh cặp khóa | KeyPairGenerator | RSA, EC, Ed25519 |
| Trao đổi shared secret | KeyAgreement | ECDH, X25519 |
| Dẫn xuất key từ input keying material | KDF | HKDF-SHA256 |
| Mã hóa key encapsulation | KEM | ML-KEM |
| Tạo số ngẫu nhiên mật mã | SecureRandom | DRBG |
| Giao tiếp mạng bảo mật | JSSE/SSLContext | TLSv1.2, TLSv1.3 |
| Quản lý key/certificate | KeyStore | PKCS12 |
| Xác minh certificate chain | CertPathValidator | PKIX |

Nếu cần truyền dữ liệu qua mạng, thông thường nên dùng TLS với JSSE và certificate validation đúng thay vì tự xây dựng một giao thức mã hóa từ Cipher, Signature và KeyAgreement.

## 9. TLS và các thuật toán bảo mật của runtime

TLS là giao thức bảo vệ kết nối mạng. Trong Java, JSSE cung cấp SSLContext, SSLSocket, SSLEngine, TrustManagerFactory và KeyManagerFactory. JSSE cũng sử dụng JCA provider cho một số thuật toán mật mã nền.

Trong Java SE 26, TLSv1.2 và TLSv1.3 là các SSLContext algorithm names mà Java SE implementation phải hỗ trợ. Provider SunJSSE có các implementation này. TLS 1.0 và TLS 1.1 đã cũ và bị tắt mặc định trong JDK 26.

Một số TLS 1.3 cipher suites thường gặp:

- TLS_AES_128_GCM_SHA256
- TLS_AES_256_GCM_SHA384
- TLS_CHACHA20_POLY1305_SHA256

Lưu ý: tên cipher transformation của Cipher như AES/GCM/NoPadding khác tên TLS cipher suite. TLS tự thương lượng protocol, key exchange, signature scheme và cipher suite theo cấu hình hai đầu.

Danh sách cipher suites được implementation biết tới không đồng nghĩa mọi suite đều được bật mặc định. Security property jdk.tls.disabledAlgorithms và cấu hình TLS có thể loại bỏ protocol, key size hoặc cipher suite.

Không bật lại SSLv3, TLS 1.0, TLS 1.1 hoặc thuật toán yếu chỉ để làm cho một peer cũ kết nối được. Hãy nâng cấp peer hoặc có ngoại lệ tương thích được phê duyệt và giới hạn phạm vi.

## 10. Security properties và thuật toán bị hạn chế

JDK có các security properties để kiểm soát thuật toán và protocol. Một số property quan trọng:

| Property | Phạm vi |
|---|---|
| jdk.tls.disabledAlgorithms | Hạn chế protocol, cipher suite, key size hoặc thuật toán trong TLS |
| jdk.certpath.disabledAlgorithms | Hạn chế thuật toán và key trong certificate path validation |
| jdk.jar.disabledAlgorithms | Hạn chế thuật toán dùng để xác minh chữ ký JAR |
| jdk.security.legacyAlgorithms | Phân loại thuật toán legacy trong một số hoạt động bảo mật |
| crypto.policy | Cấu hình giới hạn độ mạnh mật mã theo policy của JDK |

Security properties thường được đặt trong file java.security dưới thư mục conf/security của Java home hoặc cấu hình bổ sung được runtime nạp. Một số có thể được đọc qua Security.getProperty.

Không xóa thuật toán khỏi disabledAlgorithms chỉ để làm cho chương trình chạy. Nếu cần hỗ trợ dữ liệu cũ, hãy tách quy trình đọc/migration legacy khỏi việc tạo dữ liệu mới, ghi rõ phạm vi, thời hạn và policy phê duyệt.

Key size được phép cũng phụ thuộc provider, runtime, policy và thuật toán. Đừng suy luận rằng key 256-bit luôn được hỗ trợ ở mọi nơi hoặc mọi key 2048-bit đều đủ an toàn cho mọi thuật toán.

## 11. Kiểm tra tính tương thích giữa môi trường

Khi phát triển ứng dụng sử dụng mật mã, hãy kiểm tra trên đúng runtime sẽ triển khai:

- JDK vendor và phiên bản đầy đủ.
- Hệ điều hành và kiến trúc CPU.
- Danh sách provider và thứ tự ưu tiên.
- Provider bên thứ ba, HSM hoặc PKCS#11 configuration.
- Security properties và crypto policy.
- Key size, curve, mode, padding và algorithm parameters.
- TLS protocol, cipher suite và certificate chain.
- Khả năng trao đổi key/ciphertext/signature với hệ thống khác.

Một thuật toán có thể tồn tại ở JDK 26 nhưng không có ở JDK 17. Một provider có thể có trên Windows nhưng không có trên Linux. Một HSM có thể chỉ hỗ trợ một tập cipher/signature và key size riêng.

Đối với hệ thống phân tán, hãy kiểm tra interoperability giữa các provider và phiên bản JDK. Đừng chỉ test encrypt/decrypt trong cùng một JVM; cần kiểm tra dữ liệu được tạo bởi một implementation có thể được implementation bên kia đọc/xác minh theo cùng chuẩn.

## 12. Lỗi thường gặp và cách xử lý

### NoSuchAlgorithmException

**Dấu hiệu:** getInstance báo không tìm thấy thuật toán.

**Nguyên nhân:** tên sai, provider không có service, provider chưa đăng ký hoặc runtime không hỗ trợ algorithm.

**Cách xử lý:** kiểm tra tên chuẩn trong Java Security Standard Algorithm Names; liệt kê provider/services; xác minh JDK version và cài provider cần thiết.

### NoSuchPaddingException

**Dấu hiệu:** Cipher transformation có algorithm nhưng padding không được hỗ trợ.

**Nguyên nhân:** transformation sai hoặc provider không có mode/padding được yêu cầu.

**Cách xử lý:** dùng transformation đầy đủ đã được provider công bố; kiểm tra đúng tên mode và padding; test trên runtime mục tiêu.

### InvalidKeyException hoặc InvalidAlgorithmParameterException

**Dấu hiệu:** key size, key type, curve, IV, nonce hoặc parameter không hợp lệ.

**Nguyên nhân:** key không tương thích với algorithm, key size vượt policy hoặc parameter thiếu/sai.

**Cách xử lý:** xác minh key algorithm, key size và parameter spec; kiểm tra provider và crypto policy; tạo key bằng engine phù hợp.

### AEADBadTagException

**Dấu hiệu:** AES-GCM hoặc ChaCha20-Poly1305 không giải mã được dữ liệu.

**Nguyên nhân:** ciphertext, tag, key, nonce hoặc AAD không khớp; dữ liệu có thể đã bị sửa.

**Cách xử lý:** kiểm tra format và metadata; xác nhận đúng key/nonce/AAD; coi lỗi xác thực là dữ liệu không đáng tin và không trả plaintext một phần cho ứng dụng.

### Thuật toán có trong JDK nhưng không được dùng

**Dấu hiệu:** provider liệt kê thuật toán nhưng getInstance/init/handshake vẫn thất bại.

**Nguyên nhân:** thuật toán bị security property vô hiệu hóa, key size không hợp lệ, transformation thiếu mode/padding hoặc provider không hỗ trợ parameter cụ thể.

**Cách xử lý:** đọc security properties, kiểm tra provider service và khởi tạo engine với đúng parameters; chạy test trong cùng runtime/configuration với production.

### TLS handshake failure hoặc no cipher suites in common

**Dấu hiệu:** hai bên không hoàn thành TLS handshake.

**Nguyên nhân:** protocol, cipher suite, signature scheme, named group, certificate/key type hoặc trust chain không giao nhau.

**Cách xử lý:** kiểm tra cấu hình TLS của cả hai đầu; xem java -XshowSettings:security:tls; xác minh certificate, hostname, provider và disabled algorithms. Không hạ policy bảo mật một cách rộng rãi.

### Khác biệt provider giữa các máy

**Dấu hiệu:** ứng dụng chạy trên máy developer nhưng lỗi trong container/server.

**Nguyên nhân:** JDK vendor/version, OS provider, third-party provider hoặc native library khác nhau.

**Cách xử lý:** ghi lại runtime/provider inventory trong chẩn đoán; khóa JDK toolchain; cài và cấu hình provider/native dependency theo tài liệu chính thức; thêm integration test trên môi trường đích.

## 13. Checklist lựa chọn và kiểm tra thuật toán

- [ ] Xác định mục tiêu: hash, MAC, encryption, signature, key agreement, KDF, KEM hay TLS.
- [ ] Chọn engine API đúng với mục tiêu.
- [ ] Dùng tên chuẩn trong Java Security Standard Algorithm Names.
- [ ] Kiểm tra JDK version và provider thực tế.
- [ ] Chọn mode/padding tường minh cho Cipher.
- [ ] Ưu tiên authenticated encryption cho dữ liệu mới.
- [ ] Không tái sử dụng nonce với cùng key trong AEAD.
- [ ] Dùng SecureRandom cho key, nonce và token.
- [ ] Dùng password KDF cho password, không dùng hash nhanh đơn lẻ.
- [ ] Không dùng thuật toán yếu chỉ vì JDK vẫn liệt kê nó.
- [ ] Kiểm tra security properties, key size và crypto policy.
- [ ] Kiểm tra certificate, key format và interoperability.
- [ ] Kiểm thử trên đúng JDK/OS/provider của production.
- [ ] Quản lý key storage, rotation, backup, revocation và secret access.
- [ ] Dùng TLS/JSSE cho giao tiếp mạng thay vì tự xây protocol.
- [ ] Đánh giá provider/HSM/FIPS requirements với đội bảo mật khi có yêu cầu tuân thủ.

## 14. Tài liệu tham khảo chính thức

- [Java Cryptography Architecture (JCA) Reference Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html) — engine classes, provider architecture, SecureRandom, Cipher, Signature, Mac và key management.
- [Java Security Standard Algorithm Names — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html) — tên chuẩn cho cipher, digest, MAC, key, signature, KDF, KEM, TLS và thuật toán Java SE yêu cầu implementation hỗ trợ.
- [JDK Providers Documentation — Java SE 26](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html) — thuật toán cụ thể trong SUN, SunJCE, SunRsaSign, SunJSSE, SunEC, SunPKCS11 và provider nền tảng.
- [Java Security Developer's Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/security/) — cấu hình security properties, provider, PKCS#11, JSSE, PKI và các công cụ bảo mật.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — tùy chọn -XshowSettings:security:providers, security:tls và security:properties.
- [FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard](https://csrc.nist.gov/pubs/fips/203/final) — tiêu chuẩn ML-KEM.
- [FIPS 204: Module-Lattice-Based Digital Signature Standard](https://csrc.nist.gov/pubs/fips/204/final) — tiêu chuẩn ML-DSA.

Java cung cấp nhiều thuật toán mật mã qua JCA và các provider. Hãy chọn đúng engine, tên chuẩn, mode và provider; kiểm tra khả năng thật trên runtime mục tiêu; và đánh giá độ mạnh cũng như chính sách bảo mật độc lập với việc thuật toán có được liệt kê hay không.
