# Giới hạn provider và thuật toán được hỗ trợ

PEM là định dạng văn bản đóng gói dữ liệu nhị phân như chứng chỉ, khóa công khai và khóa riêng. Một PEM hợp lệ về cú pháp chưa chắc có thể được Java chuyển thành đối tượng khóa hoặc dùng trong thao tác mật mã. Việc đó còn phụ thuộc vào loại dữ liệu DER bên trong, thuật toán và key format, các dịch vụ mà provider cung cấp, tham số của khóa, chính sách bảo mật và cấu hình runtime.

Java Cryptography Architecture (JCA) tách API mật mã khỏi phần triển khai. Ứng dụng yêu cầu một dịch vụ như KeyFactory, Signature, Cipher hoặc CertificateFactory; provider cung cấp implementation cụ thể. Vì vậy, khi xử lý PEM, cần kiểm tra lần lượt: provider nào đang được cài đặt, provider nào có dịch vụ cần dùng, thuật toán có được triển khai cho dịch vụ đó không, và thao tác thật với khóa/parameters có thành công trong môi trường triển khai không.

Bài này dùng Java 26 làm mốc thực hành. JCA và các engine class là API Java SE ổn định; riêng PEMDecoder và PEMEncoder trong JDK 26 vẫn là preview. JDK 27 tiếp tục preview với API đã thay đổi, còn JEP 542 hoàn tất thiết kế PEM cho nhánh JDK 28. Không nên xem API preview của JDK 26 là hợp đồng tương thích lâu dài.

## 1. Phân biệt provider, service và algorithm

Ba khái niệm thường bị nhầm lẫn:

- **Provider** là thành phần cung cấp một hoặc nhiều implementation bảo mật. Provider có tên, phiên bản và danh sách service.
- **Service** là loại công việc mật mã mà provider thực hiện, ví dụ MessageDigest, Signature, Cipher, KeyFactory, KeyPairGenerator, KeyStore, CertificateFactory hoặc SSLContext.
- **Algorithm** là thuật toán cụ thể được đăng ký cho một service, ví dụ SHA-256 cho MessageDigest, RSA cho KeyFactory, AES/GCM/NoPadding cho Cipher hoặc TLSv1.3 cho SSLContext.

Một thuật toán chỉ có ý nghĩa khi đi cùng service. Ví dụ:

| Service | Ví dụ algorithm | Mục đích |
|---|---|---|
| MessageDigest | SHA-256 | Tạo giá trị băm |
| Signature | SHA256withRSA, Ed25519, RSASSA-PSS | Ký và xác minh chữ ký |
| Cipher | AES/GCM/NoPadding | Mã hóa và giải mã dữ liệu |
| KeyFactory | RSA, EC, Ed25519 | Chuyển đổi khóa giữa KeySpec và đối tượng Key |
| KeyPairGenerator | RSA, EC, Ed25519 | Tạo cặp khóa |
| CertificateFactory | X.509 | Đọc chứng chỉ và CRL |
| CertPathValidator | PKIX | Kiểm tra chuỗi chứng chỉ |
| KeyStore | PKCS12 | Đọc và lưu khóa, chứng chỉ |
| SSLContext | TLS, TLSv1.3 | Tạo cấu hình kết nối TLS |

Không thể suy ra một provider hỗ trợ mọi service chỉ vì nó có tên trong danh sách provider. Cũng không thể suy ra thuật toán dùng được chỉ vì một service khác hỗ trợ cùng tên thuật toán. Ví dụ, KeyFactory hỗ trợ RSA không tự động chứng minh Cipher hoặc Signature của provider đó cũng hỗ trợ mọi biến thể RSA.

## 2. Provider mặc định thay đổi theo runtime

Oracle JDK 26 phân phối các implementation mật mã qua nhiều provider. Những tên thường gặp gồm SUN, SunRsaSign, SunJCE và SunJSSE. Các module riêng có thể cung cấp SunEC, SunPKCS11, SunMSCAPI; một số nền tảng có provider hệ điều hành riêng.

| Provider thường gặp | Nhóm chức năng |
|---|---|
| SUN | MessageDigest, CertificateFactory, CertPath, KeyStore và một số dịch vụ nền tảng |
| SunRsaSign | RSA, RSASSA-PSS, chữ ký và quản lý khóa RSA |
| SunJCE | Cipher, Mac, KeyAgreement, SecretKeyFactory và các dịch vụ JCE |
| SunJSSE | SSLContext, KeyManagerFactory, TrustManagerFactory và TLS |
| SunEC | Thuật toán elliptic curve và các dịch vụ khóa/chữ ký liên quan |
| SunPKCS11 | Cầu nối JCA/JCE tới thư viện PKCS#11, smart card hoặc HSM |
| SunMSCAPI | Tích hợp với kho mật mã của Windows khi module tương ứng có mặt |

Đây là định hướng để đọc tài liệu, không phải danh sách cứng mà ứng dụng được phép giả định. Provider có thể không có trong một runtime image rút gọn, module tùy chọn có thể không được đưa vào image, hệ điều hành có thể cung cấp implementation khác, và nhà cung cấp JDK khác có thể dùng tên provider khác.

SunPKCS11 cũng cần hiểu đúng: bản thân provider này không chứa toàn bộ thuật toán. Nó chuyển tiếp yêu cầu tới native PKCS#11 library và token được cấu hình. Vì vậy, việc thấy SunPKCS11 trong danh sách chưa chứng minh HSM đã kết nối, đã đăng nhập hoặc có mechanism phù hợp cho khóa cần dùng.

## 3. Liệt kê provider và service ngay trong JVM

Đừng dựa vào một bảng thuật toán chép từ máy phát triển. Hãy truy vấn runtime thực tế đang chạy ứng dụng.

Tạo file ProviderInventory.java:

~~~java
import java.security.Provider;
import java.security.Security;
import java.util.Comparator;

public class ProviderInventory {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.printf(
                "%s | version=%s | %s%n",
                provider.getName(),
                provider.getVersionStr(),
                provider.getInfo()
            );

            provider.getServices().stream()
                .sorted(
                    Comparator.comparing(Provider.Service::getType)
                        .thenComparing(Provider.Service::getAlgorithm)
                )
                .forEach(service -> System.out.printf(
                    "  %-24s %s%n",
                    service.getType(),
                    service.getAlgorithm()
                ));
        }
    }
}
~~~

Biên dịch và chạy bằng JDK mục tiêu:

~~~sh
javac ProviderInventory.java
java ProviderInventory
~~~

Security.getProviders() trả về các provider đã đăng ký theo thứ tự ưu tiên. Provider.getServices() trả về tập service mà provider công bố. Mỗi Provider.Service cho biết service type, algorithm và implementation class.

Để xem các tên thuật toán đã đăng ký cho một service, có thể dùng:

~~~java
import java.security.Security;

System.out.println(Security.getAlgorithms("Signature"));
System.out.println(Security.getAlgorithms("MessageDigest"));
System.out.println(Security.getAlgorithms("Cipher"));
~~~

Security.getAlgorithms(serviceName) trả về tập tên algorithm/type mà các provider đang cài đặt cung cấp cho service đó. Tập này hữu ích để khám phá, nhưng chưa chứng minh một phép toán cụ thể sẽ khởi tạo thành công với key, parameters và chính sách bảo mật đang dùng.

## 4. Kiểm tra provider nào cung cấp một dịch vụ cụ thể

Provider.getService(type, algorithm) cho phép truy vấn một implementation cụ thể:

~~~java
import java.security.Provider;
import java.security.Security;

public class FindService {
    public static void main(String[] args) {
        String type = "Cipher";
        String algorithm = "AES/GCM/NoPadding";

        for (Provider provider : Security.getProviders()) {
            Provider.Service service =
                provider.getService(type, algorithm);

            if (service != null) {
                System.out.printf(
                    "%s provides %s: %s%n",
                    provider.getName(),
                    type,
                    service.getAlgorithm()
                );
            }
        }
    }
}
~~~

Tên algorithm không phân biệt chữ hoa/chữ thường trong API JCA. Tuy nhiên, nên dùng tên chuẩn trong Java Security Standard Algorithm Names thay vì dựa vào alias riêng của một provider. Không phải provider nào cũng đăng ký cùng một alias.

Có thể kiểm tra theo bộ lọc của Security.getProviders:

~~~java
Provider[] providers =
    Security.getProviders("Signature.SHA256withRSA");
~~~

Bộ lọc này trả về các provider có service và algorithm phù hợp, theo thứ tự ưu tiên. Nếu kết quả null, không có provider đã đăng ký nào đáp ứng tiêu chí đó trong runtime hiện tại.

## 5. Xác nhận bằng getInstance và provider thực tế được chọn

Cách kiểm tra có ý nghĩa nhất là yêu cầu chính engine class mà ứng dụng sẽ sử dụng. Nếu không truyền provider, JCA tìm implementation theo thứ tự ưu tiên đã đăng ký.

~~~java
import java.security.MessageDigest;
import java.security.Signature;
import javax.crypto.Cipher;

public class EngineCheck {
    public static void main(String[] args) throws Exception {
        MessageDigest digest =
            MessageDigest.getInstance("SHA-256");

        Signature signature =
            Signature.getInstance("SHA256withRSA");

        Cipher cipher =
            Cipher.getInstance("AES/GCM/NoPadding");

        System.out.println(
            "MessageDigest provider: " +
            digest.getProvider().getName()
        );
        System.out.println(
            "Signature provider: " +
            signature.getProvider().getName()
        );
        System.out.println(
            "Cipher provider: " +
            cipher.getProvider().getName()
        );
    }
}
~~~

Một lần getInstance thành công xác nhận runtime đã tìm được implementation cho service/algorithm được yêu cầu. Provider được chọn có thể khác nhau giữa các engine. Ví dụ, KeyFactory có thể đến từ một provider, Signature đến từ provider khác và Cipher đến từ provider thứ ba.

Với Cipher, hãy ghi đầy đủ transformation theo dạng algorithm/mode/padding, ví dụ AES/GCM/NoPadding. Không dựa vào mode hoặc padding mặc định của provider vì các mặc định có thể khác nhau. Tránh ECB khi mã hóa nhiều block dữ liệu; với GCM, phải bảo đảm nonce không bị dùng lại dưới cùng một khóa và xác minh authentication tag khi giải mã.

Khi getInstance thất bại với NoSuchAlgorithmException, runtime không tìm thấy implementation phù hợp cho service/algorithm đó. Khi gọi getInstance với tên provider mà provider chưa được đăng ký, có thể gặp NoSuchProviderException. Khi provider tồn tại nhưng thiếu service cần thiết, thao tác cũng thất bại.

Việc tạo engine object chưa chắc đã đủ để dùng thành công. Một số engine cần init với khóa, IV, AlgorithmParameterSpec, certificate chain, token login hoặc thiết bị phần cứng. Hãy kiểm tra bằng một thao tác thực tế có kiểm soát trong môi trường test.

## 6. Hỗ trợ thuật toán không đồng nghĩa được phép sử dụng

Có ba lớp kiểm tra độc lập:

1. Provider có đăng ký service/algorithm không?
2. Implementation có xử lý được key, key size, parameters và format đang dùng không?
3. Chính sách bảo mật của runtime có cho phép dùng thuật toán đó trong ngữ cảnh cụ thể không?

Một thuật toán có thể xuất hiện trong Security.getAlgorithms nhưng vẫn bị chặn khi xác minh chứng chỉ hoặc thương lượng TLS. Ngược lại, Cipher có thể tạo được engine object nhưng init thất bại vì key length hoặc parameter không được provider hỗ trợ.

Oracle JDK dùng các security property trong file java.security để giới hạn thuật toán trong các ngữ cảnh khác nhau:

| Security property | Phạm vi chính |
|---|---|
| jdk.crypto.disabledAlgorithms | Chặn service/algorithm ở tầng JCA/JCE theo tên service và algorithm |
| jdk.tls.disabledAlgorithms | Hạn chế protocol, cipher suite, key size, signature scheme và thành phần trong TLS/DTLS |
| jdk.certpath.disabledAlgorithms | Hạn chế thuật toán và kích thước khóa trong quá trình xây dựng/kiểm tra certification path |
| jdk.jar.disabledAlgorithms | Hạn chế thuật toán dùng trong xác minh chữ ký JAR |
| jdk.security.legacyAlgorithms | Đánh dấu thuật toán cũ theo các quy tắc của công cụ/chức năng bảo mật liên quan |

Có thể đọc giá trị hiện tại của một số property:

~~~java
import java.security.Security;

System.out.println(
    Security.getProperty("jdk.crypto.disabledAlgorithms")
);
System.out.println(
    Security.getProperty("jdk.tls.disabledAlgorithms")
);
System.out.println(
    Security.getProperty("jdk.certpath.disabledAlgorithms")
);
System.out.println(
    Security.getProperty("jdk.jar.disabledAlgorithms")
);
~~~

Các property này là cấu hình của implementation. Tên, giá trị mặc định và cách áp dụng có thể khác giữa các nhà cung cấp JDK; không giả định mọi runtime đều xử lý chúng giống Oracle JDK. Với ứng dụng cần tuân thủ chính sách tổ chức, hãy kiểm tra tài liệu của đúng JDK và provider đang triển khai.

Không gỡ thuật toán khỏi disabledAlgorithms chỉ để làm cho một PEM cũ hoặc một kết nối TLS cũ hoạt động. Nếu chứng chỉ hoặc khóa dùng thuật toán không còn được chấp nhận, cần thay chứng chỉ/khóa hoặc cập nhật đầu bên kia theo chuẩn bảo mật hiện hành.

## 7. Kiểm tra giới hạn key size và tham số

Cipher.getMaxAllowedKeyLength(algorithm) cho biết giới hạn độ dài khóa được phép theo jurisdiction policy hiện tại:

~~~java
import javax.crypto.Cipher;

int maxAesBits =
    Cipher.getMaxAllowedKeyLength("AES");

System.out.println("Maximum AES key length: " + maxAesBits);
~~~

Trong Oracle JDK hiện đại, cấu hình mặc định cho phép các thuật toán có độ mạnh không bị giới hạn bởi bộ policy giới hạn cũ. Tuy nhiên, tổ chức hoặc môi trường triển khai có thể cấu hình jurisdiction policy khác theo yêu cầu pháp lý. Kết quả từ getMaxAllowedKeyLength chỉ nói về giới hạn policy của Cipher; nó không xác nhận provider, token hay thuật toán cụ thể có thể thực hiện mọi key size.

Ngoài key size, cần kiểm tra:

- Loại khóa: RSA, EC, Ed25519, X25519 hoặc loại khác.
- Key format: PKCS#8 cho private key, X.509 SubjectPublicKeyInfo cho public key, X.509 cho certificate.
- Thuật toán và tham số: ví dụ RSASSA-PSS cần PSSParameterSpec phù hợp; AES-GCM cần GCMParameterSpec với nonce và tag length phù hợp.
- Đường cong elliptic hoặc named group mà provider hỗ trợ.
- Provider có thể thao tác với khóa phần cứng hay không.
- Key có export được hay không; khóa trong HSM thường có thể là non-exportable.

Đừng nhầm việc provider hỗ trợ RSA với việc nó chấp nhận mọi kích thước RSA hoặc mọi loại key encoding. Tương tự, hỗ trợ EC không có nghĩa mọi named curve đều được phép trong TLS hoặc được provider triển khai.

## 8. Giới hạn provider khi giải mã PEM trong JDK 26

Trong JDK 26, PEMDecoder là preview API thuộc JEP 524 (Second Preview). PEMDecoder.of() có thể giải mã các loại PEM được hỗ trợ thành đối tượng như X509Certificate, X509CRL, PublicKey, PrivateKey hoặc EncryptedPrivateKeyInfo. Với khóa, lớp đối tượng được tạo còn phụ thuộc thuật toán và KeyFactory có sẵn.

PEM header xác định loại cấu trúc được đóng gói, không tự xác định provider hay bảo đảm thuật toán có thể dùng được. Ví dụ, PRIVATE KEY thường mang private key theo PKCS#8; PUBLIC KEY mang public key theo SubjectPublicKeyInfo của X.509; CERTIFICATE chứa chứng chỉ X.509; ENCRYPTED PRIVATE KEY chứa cấu trúc EncryptedPrivateKeyInfo. Decoder có thể nhận diện cấu trúc, nhưng việc tạo PrivateKey/PublicKey vẫn cần KeyFactory phù hợp với thuật toán bên trong. Đọc được certificate cũng không đồng nghĩa chữ ký trên certificate chain được policy chấp nhận.

Ví dụ giải mã private key PKCS#8:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PrivateKey;

public class DecodePrivateKey {
    public static void main(String[] args) throws Exception {
        String pem = Files.readString(
            Path.of("private-key.pem")
        );

        PrivateKey key =
            PEMDecoder.of().decode(pem, PrivateKey.class);

        System.out.println("Algorithm: " + key.getAlgorithm());
        System.out.println("Format: " + key.getFormat());
    }
}
~~~

Biên dịch và chạy bằng JDK 26:

~~~sh
javac --enable-preview --release 26 DecodePrivateKey.java
java --enable-preview DecodePrivateKey
~~~

PEMDecoder là preview, vì vậy phải bật preview ở cả compiler và JVM. Đây là API Java SE preview trong java.base, không cần thêm module provider riêng.

### 8.1. Chọn provider cho KeyFactory và CertificateFactory

JDK 26 cung cấp withFactory(Provider) để cấu hình PEMDecoder dùng provider được chỉ định khi lấy KeyFactory và CertificateFactory:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PrivateKey;
import java.security.Provider;
import java.security.Security;

public class DecodeWithProvider {
    public static void main(String[] args) throws Exception {
        Provider provider =
            Security.getProvider("MyCryptoProvider");

        if (provider == null) {
            throw new IllegalStateException(
                "Required provider is not installed"
            );
        }

        String pem = Files.readString(
            Path.of("private-key.pem")
        );

        PEMDecoder decoder =
            PEMDecoder.of().withFactory(provider);

        PrivateKey key =
            decoder.decode(pem, PrivateKey.class);

        System.out.println(key.getAlgorithm());
    }
}
~~~

Thay MyCryptoProvider bằng tên provider thực tế được cấu hình trong môi trường. Ví dụ này chỉ có ý nghĩa khi provider đó có KeyFactory cho thuật toán của private key. Nếu cần giải mã certificate bằng cùng decoder, provider cũng phải cung cấp CertificateFactory X.509 phù hợp.

Điểm cần nhớ: withFactory trong JDK 26 chỉ cấu hình KeyFactory và CertificateFactory mà PEMDecoder sử dụng để tạo đối tượng khóa/chứng chỉ. Không suy ra rằng mọi thao tác Signature, Cipher, Mac, KeyAgreement hoặc SSLContext về sau đều tự động dùng cùng provider. Hãy lấy engine object cho từng thao tác và kiểm tra provider được chọn riêng.

### 8.2. Khóa PEM được mã hóa

Với PEM loại ENCRYPTED PRIVATE KEY, decoder chưa cấu hình giải mã trả về EncryptedPrivateKeyInfo. Khi cấu hình password bằng withDecryption(char[]), decoder có thể giải mã nội dung khóa theo cơ chế được hỗ trợ:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PrivateKey;

char[] password = readPasswordFromSecretStore();

String pem = Files.readString(
    Path.of("encrypted-private-key.pem")
);

PEMDecoder decoder =
    PEMDecoder.of().withDecryption(password);

PrivateKey key =
    decoder.decode(pem, PrivateKey.class);
~~~

Đây là ví dụ về API preview của JDK 26. Không ghi password vào source code, command line, log hoặc file cấu hình được commit. Xóa nội dung mảng password sau khi dùng khi có thể; việc này giảm thời gian giữ bí mật trong heap nhưng không bảo đảm JVM đã xóa mọi bản sao nội bộ.

Cần phân biệt hai loại lỗi: lỗi giải mã PEM/DER và lỗi do provider không hỗ trợ thuật toán hoặc parameters của khóa. Nếu sai password, thuật toán mã hóa khóa không được hỗ trợ hoặc provider thiếu service, quá trình giải mã có thể thất bại. Không thử lần lượt nhiều provider hoặc thuật toán yếu hơn một cách tự động để né lỗi; hãy xác định đúng định dạng và chính sách mã hóa của nguồn PEM.

## 9. PEM API thay đổi theo JDK: không dùng nhầm preview cũ

PEM API là phần mới của JDK, nhưng trạng thái và tên API đã thay đổi qua các bản phát hành:

| JDK | JEP | Trạng thái | Điểm cần chú ý |
|---|---|---|---|
| JDK 25 | JEP 470 | Preview lần đầu | Thiết kế API PEM ban đầu |
| JDK 26 | JEP 524 | Preview lần thứ hai | Dùng DEREncodable, withFactory(Provider) |
| JDK 27 | JEP 538 | Preview lần thứ ba | Đổi DEREncodable thành BinaryEncodable; withFactory đổi thành withFactoriesOf |
| JDK 28 development | JEP 542 | Final API đã hoàn tất trong nhánh phát triển | JDK 28 chưa GA tại ngày 27-11-2026 |

Các thay đổi này có ý nghĩa trực tiếp khi nâng cấp. Source code dùng withFactory của JDK 26 không thể được giả định là biên dịch nguyên trạng với API JDK 27. Class file đã biên dịch bằng preview của JDK 26 cũng không phải binary tương thích để mang sang JDK 27.

Với JDK 27, PEM API vẫn cần preview flag và dùng tên API mới theo JEP 538. Với JDK 28 đã phát hành, dùng API final theo JEP 542 và không bật preview cho PEM. Trước khi nâng cấp, hãy biên dịch lại bằng đúng JDK đích và kiểm tra Javadoc của phiên bản đó.

## 10. Provider cho HSM, PKCS#11 và môi trường tuân thủ

Khi khóa riêng nằm trong HSM hoặc smart card, ứng dụng thường không nên xuất private key ra file PEM. SunPKCS11 kết nối JCA với native PKCS#11 library; token có thể chỉ cho phép ký hoặc giải mã bằng handle của khóa, không cho phép lấy raw private key bytes.

Quy trình triển khai cần xác minh:

1. Module jdk.crypto.cryptoki có trong runtime image.
2. Native PKCS#11 library và file cấu hình đúng với thiết bị.
3. Provider được configure và đăng ký thành công.
4. Token đã được nhận diện và đăng nhập theo cơ chế được phê duyệt.
5. Provider cung cấp đúng service và algorithm cần dùng.
6. Key object trên token có quyền sử dụng cho thao tác tương ứng.
7. Ứng dụng gọi getInstance và init với khóa thật trong môi trường tích hợp.

Không nhầm PEM import với HSM key reference. PEM thường chứa vật liệu khóa có thể xuất dưới dạng PKCS#8 hoặc public key X.509; HSM có thể chỉ cung cấp một đối tượng khóa không export được. Trong trường hợp đó, ứng dụng giữ tham chiếu PrivateKey do provider trả về và dùng Signature hoặc Cipher thông qua provider, thay vì cố encode private key thành PEM.

Với yêu cầu FIPS hoặc chứng nhận tương tự, cần sử dụng đúng provider, phiên bản, cấu hình và môi trường đã được tổ chức chứng nhận. Chỉ truyền tên provider vào getInstance không tự biến runtime thành môi trường tuân thủ. Phải kiểm tra tài liệu chứng nhận, chế độ hoạt động, thứ tự provider và các service được phép dùng.

## 11. Vì sao không nên chỉ định provider cố định trong ứng dụng phổ thông?

Mẫu sau thường không phù hợp với ứng dụng Java đa nền tảng:

~~~java
Cipher cipher =
    Cipher.getInstance("AES/GCM/NoPadding", "SunJCE");
~~~

Nó gắn code vào tên provider cụ thể. Provider đó có thể không tồn tại trên một JDK khác, hoặc runtime có provider phần cứng/OS được ưu tiên hơn. Oracle khuyến nghị ứng dụng thông thường gọi getInstance(algorithm) để JCA lựa chọn provider theo thứ tự ưu tiên.

Mẫu phổ thông:

~~~java
Cipher cipher =
    Cipher.getInstance("AES/GCM/NoPadding");

System.out.println(
    cipher.getProvider().getName()
);
~~~

Chỉ yêu cầu provider cụ thể khi có lý do triển khai rõ ràng, chẳng hạn bắt buộc dùng HSM, provider được chứng nhận, hoặc cần một implementation có tính năng mà provider mặc định không cung cấp. Khi đó, hãy coi provider là dependency của môi trường, kiểm tra sự hiện diện lúc khởi động và kiểm thử tích hợp trên đúng hệ thống triển khai.

Không thay đổi thứ tự provider toàn JVM một cách tùy tiện bằng Security.insertProviderAt hoặc Security.removeProvider. Việc này có thể ảnh hưởng đến nhiều engine khác, TLS, xác minh chứng chỉ và thư viện phụ thuộc trong cùng tiến trình.

## 12. Phân biệt hỗ trợ mật mã với khả năng thương lượng TLS

Một provider có thể hỗ trợ Cipher AES/GCM/NoPadding nhưng điều đó không chứng minh một TLS connection sẽ thương lượng được cipher suite dùng AES-GCM. TLS còn phụ thuộc protocol version, cipher suite, key exchange group, signature scheme, chứng chỉ, peer và các security property.

Ví dụ kiểm tra TLS implementation:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

SSLContext context = SSLContext.getInstance("TLS");

System.out.println(
    "SSLContext provider: " +
    context.getProvider().getName()
);

SSLParameters supported =
    context.getSupportedSSLParameters();

for (String protocol : supported.getProtocols()) {
    System.out.println("Supported protocol: " + protocol);
}

for (String suite : supported.getCipherSuites()) {
    System.out.println("Supported cipher suite: " + suite);
}
~~~

Danh sách supported chỉ là những lựa chọn implementation có thể hỗ trợ. Default SSLParameters và chính sách disabledAlgorithms quyết định tập được bật hoặc được phép thương lượng. Server và client còn phải có giao điểm về protocol, cipher suite, key exchange và signature scheme.

Khi chẩn đoán lỗi TLS, kiểm tra riêng:
- SSLContext provider và protocol.
- Cipher suites được hỗ trợ và được bật.
- jdk.tls.disabledAlgorithms.
- Certificate chain và jdk.certpath.disabledAlgorithms.
- Key type, key size, signature algorithm và named group.
- Khả năng tương thích của peer và thiết bị trung gian.

Không khắc phục lỗi TLS bằng cách bật lại SSLv3, TLS 1.0, RC4 hoặc cipher suite yếu. Hãy nâng cấp chứng chỉ, key hoặc cấu hình peer để dùng giao thức và thuật toán được chấp nhận.

## 13. Các lỗi thường gặp khi kiểm tra provider và algorithm

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| NoSuchAlgorithmException | Không provider nào đăng ký service/algorithm đó | Liệt kê Security.getProviders và Provider.getServices |
| NoSuchProviderException | Tên provider được chỉ định chưa đăng ký hoặc không có | Kiểm tra Security.getProvider và cấu hình provider |
| getInstance thành công nhưng init thất bại | Key size, format, parameter hoặc token không phù hợp | Kiểm tra loại khóa, spec, key size và thông tin provider |
| PEM đọc được nhưng không tạo được PrivateKey | KeyFactory không hỗ trợ thuật toán hoặc key encoding không tương thích | Kiểm tra PEM type, KeyFactory algorithm và PKCS#8 |
| Đọc được certificate nhưng TLS handshake thất bại | CertPath/TLS policy, key usage, signature scheme hoặc cipher suite bị từ chối | Kiểm tra disabledAlgorithms và log TLS |
| Provider có Cipher nhưng không có KeyFactory | Provider chỉ triển khai một phần service | Kiểm tra riêng từng service cần cho luồng xử lý |
| HSM xuất hiện nhưng ký thất bại | Token chưa login, key không có quyền ký hoặc mechanism không được hỗ trợ | Kiểm tra PKCS#11 token và ProviderException |
| AES key length bị từ chối | Policy giới hạn hoặc provider không hỗ trợ key size đó | Kiểm tra getMaxAllowedKeyLength và tài liệu provider |
| JDK 26 code PEM không biên dịch trên JDK 27 | API preview đã đổi tên hoặc kiểu | Đọc Javadoc đúng JDK, cập nhật withFactory/withFactoriesOf |
| Nghĩ algorithm được liệt kê là an toàn | Provider có thể còn đăng ký thuật toán legacy | Kiểm tra policy và chuẩn bảo mật hiện hành, không chỉ danh sách service |

## 14. Checklist kiểm tra trước khi triển khai

- [ ] Ghi nhận chính xác vendor, version và build của JDK chạy ứng dụng.
- [ ] Liệt kê provider đang cài và thứ tự ưu tiên trên môi trường triển khai.
- [ ] Xác nhận module tùy chọn như SunEC, SunPKCS11 hoặc SunMSCAPI có trong runtime khi cần.
- [ ] Dùng tên chuẩn của service và algorithm.
- [ ] Kiểm tra Provider.Service cho từng service cần thiết, không suy luận chéo giữa các engine.
- [ ] Gọi getInstance và ghi nhận provider thực tế được chọn.
- [ ] Thử init với key, key size và parameters thực tế trong môi trường test.
- [ ] Kiểm tra disabledAlgorithms và policy key size của đúng runtime.
- [ ] Với PEM, xác định đúng PEM label và binary key format.
- [ ] Với HSM, xác minh token, mechanism, quyền khóa và khả năng export.
- [ ] Với TLS, kiểm tra protocol, cipher suite, signature scheme, named group và CertPath policy riêng.
- [ ] Chỉ pin provider khi có yêu cầu HSM, chứng nhận hoặc hợp đồng triển khai cụ thể.
- [ ] Kiểm tra trạng thái preview của PEM API theo JDK; không tái sử dụng class file preview từ bản phát hành khác.
- [ ] Không nới lỏng policy để tiếp tục dùng thuật toán yếu hoặc đã bị hạn chế.

## Tài liệu tham khảo

- [Java SE 26 — Security Developer's Guide](https://docs.oracle.com/en/java/javase/26/security/): tổng quan JCA, provider, thuật toán và bảo mật nền tảng.
- [Java SE 26 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): provider tích hợp, service, thuật toán, key size và cấu hình theo nền tảng.
- [Java SE 26 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html): cách JCA tìm và chọn provider, đăng ký provider và sử dụng engine class.
- [Java SE 26 — Security API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Security.html): getProviders, getAlgorithms, getProperty và quản lý provider.
- [Java SE 26 — Provider API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Provider.html): Provider.Service, getServices và getService.
- [Java SE 26 — PEMDecoder API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMDecoder.html): PEM decoding, withFactory và withDecryption trong preview lần hai.
- [JEP 524 — PEM Encodings of Cryptographic Objects (Second Preview)](https://openjdk.org/jeps/524): trạng thái PEM API trong JDK 26.
- [JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538): thay đổi API trong JDK 27.
- [JEP 542 — PEM Encodings of Cryptographic Objects](https://openjdk.org/jeps/542): API PEM được hoàn tất cho nhánh JDK 28.
- [Java SE 26 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html): TLS provider, protocol, cipher suite và algorithm constraints.
- [Disabling and Restricting Cryptographic Algorithms in the JDK](https://ops.java/security/articles/disabling-crypto-algorithms/): ý nghĩa của các security property dùng để giới hạn thuật toán.

