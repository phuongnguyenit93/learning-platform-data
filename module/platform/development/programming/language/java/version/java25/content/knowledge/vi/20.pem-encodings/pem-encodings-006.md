# Cấu hình preview và lựa chọn áp dụng theo yêu cầu provider và độ ổn định

## 1. Phạm vi và trạng thái hiện hành

PEM (Privacy-Enhanced Mail) là định dạng văn bản dùng để trao đổi dữ liệu mật mã như public key, private key, certificate và certificate revocation list (CRL). Một khối PEM chứa nhãn BEGIN/END cùng nội dung DER được biểu diễn bằng Base64. Quy tắc định dạng văn bản được mô tả trong RFC 7468; cấu trúc nhị phân có thể dựa trên X.509, PKCS #8 và RFC 5958.

Java bổ sung API chuẩn để encode/decode đối tượng mật mã sang PEM qua **JEP 470** trong Java 25. API gồm PEMEncoder, PEMDecoder và các kiểu dữ liệu hỗ trợ. Mục tiêu là giảm thao tác tự tách header, Base64 decode và chuyển DER bytes thành KeySpec hoặc đối tượng X.509 bằng tay.

Tại thời điểm biên soạn **27-11-2026**, PEM API vẫn là **preview** ở JDK 27 theo **JEP 538 — Third Preview**. Nó chưa phải API Java ổn định. Java 25 dùng JEP 470 (preview lần đầu), Java 26 dùng JEP 524 (preview lần hai), Java 27 dùng JEP 538 (preview lần ba). Mỗi release có thay đổi API; chương trình dùng preview phải biên dịch và chạy với đúng JDK release. [JEP 470](https://openjdk.org/jeps/470) · [JEP 524](https://openjdk.org/jeps/524) · [JEP 538](https://openjdk.org/jeps/538)

Bài thuộc chương **Mã hóa PEM** của module **JAVA_VERSION_JAVA25**, với đề bài **“Cấu hình preview và lựa chọn áp dụng theo yêu cầu provider và độ ổn định”**. Trọng tâm là bật preview đúng cách, hiểu phần việc của provider, lựa chọn giữa API JDK và thư viện ổn định, đồng thời tránh đưa private key hoặc dữ liệu tin cậy vào quy trình không phù hợp.

### Sau bài này, bạn có thể

1. Xác định trạng thái preview của PEM API theo từng JDK release.
2. Biên dịch và chạy đúng preview version.
3. Phân biệt trách nhiệm của PEM encoder/decoder với JCA Provider.
4. Chọn provider cho KeyFactory, CertificateFactory, SecretKeyFactory và Cipher.
5. Kiểm soát thuật toán, tham số và provider khi mã hóa private key.
6. Nhận biết giới hạn khi provider/HSM giữ private key không thể export.
7. Chọn API preview hoặc thư viện có độ ổn định phù hợp với yêu cầu triển khai.

## 2. PEM API giải quyết phần nào của quy trình?

Trước PEM API, ứng dụng thường phải tự tách nhãn PEM, bỏ dòng BEGIN/END, Base64 decode, sau đó chuyển DER bytes thành X509EncodedKeySpec, PKCS8EncodedKeySpec, X509Certificate hoặc đối tượng khác bằng JCA.

PEM API chuẩn hóa các bước này:

| Thành phần | Trách nhiệm |
| --- | --- |
| PEMDecoder | Đọc PEM text/stream và chuyển thành đối tượng mật mã hoặc biểu diễn PEM thô |
| PEMEncoder | Chuyển đối tượng mật mã sang PEM bytes hoặc String |
| DEREncodable (JDK 25/26) | Hợp đồng preview cho đối tượng có biểu diễn DER |
| BinaryEncodable (JDK 27) | Hợp đồng preview mới, diễn đạt rộng hơn về dữ liệu nhị phân có thể encode |
| PEMRecord (JDK 25) / PEM (JDK 26/27) | Giữ nhãn PEM và nội dung Base64 khi không giải mã thành kiểu mật mã chuyên biệt |
| EncryptedPrivateKeyInfo | Biểu diễn private key được mã hóa theo cấu trúc PKCS #8 |

PEM là **định dạng vận chuyển**. Nó không thay thế KeyStore, HSM, PKI, certificate path validation, quản lý vòng đời khóa hay chính sách phân quyền.

Đọc được một certificate từ PEM không có nghĩa certificate đó đáng tin. Ứng dụng vẫn phải kiểm tra chain, thời hạn, key usage, extended key usage, hostname/subject identity và trust anchors theo đúng ngữ cảnh.

## 3. Trạng thái API theo JDK release

| JDK | JEP | Tên/đặc điểm API chính | Trạng thái |
| --- | --- | --- | --- |
| Java 25 | JEP 470 | DEREncodable, PEMRecord, withFactory, encryptKey | Preview lần 1 |
| Java 26 | JEP 524 | PEMRecord đổi thành PEM; mở rộng đối tượng có thể mã hóa | Preview lần 2 |
| **Java 27** | **JEP 538** | **DEREncodable đổi thành BinaryEncodable; withFactory đổi thành withFactoriesOf; encryptKey đổi thành encrypt** | **Preview lần 3** |

Điểm quan trọng khi nâng cấp là **không dùng tên API của JDK 25 làm ví dụ hiện hành cho JDK 27**. Cần biên dịch lại bằng đúng release, đọc preview API docs tương ứng và chạy test tương thích với provider đang triển khai.

JDK 27 phát hành ngày 15-09-2026 và vẫn đánh dấu PEM Encodings of Cryptographic Objects là preview. Không nên kết luận tính năng đã final chỉ vì API đã trải qua ba vòng preview. [JDK 27 Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) · [JEP 538](https://openjdk.org/jeps/538)

## 4. Bật preview khi biên dịch và chạy

Preview feature phải được bật ở cả compiler lẫn runtime. Phiên bản preview gắn với một JDK release cụ thể.

### Nếu target Java 25

Dùng JDK 25 để biên dịch và chạy:

~~~bash
javac --enable-preview --release 25 -Xlint:preview PemExample.java
java --enable-preview PemExample
~~~

### Nếu target Java 27

Dùng JDK 27 để biên dịch và chạy:

~~~bash
javac --enable-preview --release 27 -Xlint:preview PemExample.java
java --enable-preview PemExample
~~~

Không biên dịch bằng preview Java 25 rồi chạy bytecode đó bằng preview Java 27. Preview APIs không có cam kết tương thích nhị phân giữa các release. Không thể dùng compiler JDK 27 để yêu cầu preview của JDK 25 bằng cách chỉ đổi --release; --enable-preview dành cho preview của release compiler hiện tại.

### Kiểm tra môi trường build

~~~bash
java -version
javac -version
~~~

Trong CI, bảo đảm hai lệnh dùng cùng JDK vendor/build. Nếu Maven hoặc Gradle fork compiler/runtime riêng, cấu hình preview cho cả compile task và test/runtime task; chỉ thêm compiler flag là chưa đủ.

## 5. API thay đổi: những tên không nên trộn giữa release

| Thành phần | Java 25 | Java 26 | Java 27 |
| --- | --- | --- | --- |
| Kiểu dữ liệu chung | DEREncodable | DEREncodable | BinaryEncodable |
| PEM thô | PEMRecord | PEM | PEM |
| Chọn provider cho factory trong decoder | withFactory(Provider) | withFactory(Provider) | withFactoriesOf(Provider) |
| Mã hóa private key có provider | EncryptedPrivateKeyInfo.encryptKey(...) | encryptKey(...) | EncryptedPrivateKeyInfo.encrypt(...) |

Java 27 đổi DEREncodable thành BinaryEncodable để thể hiện API hoạt động với biểu diễn nhị phân nói chung. PEMRecord đã được đổi thành PEM từ Java 26. Java 27 tiếp tục đổi withFactory thành withFactoriesOf và chuẩn hóa phương thức mã hóa thành EncryptedPrivateKeyInfo.encrypt.

Nếu code cần chạy trên Java 25 và Java 27, hãy duy trì source set hoặc adapter riêng theo release. Không cố tạo một đoạn source duy nhất bằng reflection để che mọi khác biệt preview; điều đó làm khó kiểm thử và dễ bỏ sót thay đổi ngữ nghĩa.

## 6. Ví dụ cơ bản với API hiện hành của Java 27

Ví dụ encode public key:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PEMEncoder;

public class PemPublicKeyExample {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair pair = generator.generateKeyPair();

        String publicPem = PEMEncoder.of().encodeToString(pair.getPublic());
        System.out.println(publicPem);
    }
}
~~~

Ví dụ decode public key:

~~~java
import java.security.PEMDecoder;
import java.security.PublicKey;

public class PemDecodeExample {
    public static PublicKey decodePublicKey(String pem) {
        return PEMDecoder.of().decode(pem, PublicKey.class);
    }
}
~~~

Đây là ví dụ API preview của JDK 27, cần compile/run với --enable-preview --release 27. Với Java 25, PEMEncoder và PEMDecoder cũng tồn tại nhưng generic type là DEREncodable và API surface có một số khác biệt.

Không in PEM private key vào log hoặc console trong ứng dụng thật. Ví dụ chỉ in public key; public key vẫn cần được bảo vệ tính toàn vẹn và gắn đúng danh tính/chính sách sử dụng.

## 7. Provider làm gì trong PEM API?

PEM text chỉ đóng vai trò bọc dữ liệu nhị phân bằng header/footer và Base64. Provider tham gia khi ứng dụng cần chuyển dữ liệu DER thành đối tượng mật mã hoặc thực hiện phép mã hóa/giải mã.

Các service JCA thường liên quan:

| JCA service | Dùng khi | Ví dụ |
| --- | --- | --- |
| KeyFactory | Tạo PublicKey/PrivateKey từ key spec | RSA, EC, Ed25519 |
| CertificateFactory | Tạo certificate hoặc CRL | X.509 |
| SecretKeyFactory | Tạo khóa PBE từ password | PBE algorithm |
| Cipher | Mã hóa/giải mã nội dung private key | PBE cipher |
| SecureRandom | Sinh tham số ngẫu nhiên khi mã hóa | Salt/nonce tùy thuật toán |

Không phải mọi provider đều có mọi service. Một provider có KeyFactory.RSA chưa chắc có CertificateFactory.X.509, SecretKeyFactory cho thuật toán PBE hoặc Cipher tương ứng.

Vì vậy, khi ứng dụng cần hỗ trợ nhiều loại PEM, hãy kiểm tra provider theo **loại dữ liệu và thuật toán thực tế**, không chỉ kiểm tra tên provider đã được cài vào JVM.

## 8. withFactoriesOf(Provider) trong Java 27 chọn những gì?

Trong Java 27, PEMDecoder.withFactoriesOf(provider) tạo một decoder mới, sử dụng provider được chỉ định khi lấy các implementation KeyFactory và CertificateFactory.

~~~java
import java.security.PEMDecoder;
import java.security.Provider;
import java.security.PublicKey;

public class ProviderBoundDecoder {
    static PublicKey decode(String pem, Provider factoryProvider) {
        return PEMDecoder.of()
                .withFactoriesOf(factoryProvider)
                .decode(pem, PublicKey.class);
    }
}
~~~

Provider được chọn chỉ áp dụng cho việc tạo cryptographic objects qua KeyFactory và CertificateFactory. Nó **không phải một công tắc chọn provider cho mọi thao tác mật mã trong toàn bộ PEM pipeline**.

Ví dụ, provider được truyền vào withFactoriesOf không đồng nghĩa PBE Cipher dùng để giải mã encrypted private key cũng bị pin vào cùng provider. withDecryption(password) chỉ cấu hình password; phương thức này không nhận tham số Provider.

### Hệ quả khi chọn provider

- Nếu provider không có KeyFactory cho thuật toán của key, decode key sẽ thất bại.
- Nếu provider không có CertificateFactory cho certificate type cần đọc, decode certificate sẽ thất bại.
- Nếu một ứng dụng đọc cả key và certificate, provider được chọn cần có các factory tương ứng cho cả luồng sử dụng.
- Nếu provider chỉ đáp ứng một loại object, cân nhắc dùng default provider selection cho decoder hoặc tách quy trình decode theo loại dữ liệu bằng thành phần phù hợp.

Đối chiếu API: [PEMDecoder Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html).

## 9. Kiểm tra provider có service cần thiết

Có thể kiểm tra trực tiếp bằng JCA trước khi chạy luồng PEM:

~~~java
import java.security.KeyFactory;
import java.security.Provider;
import java.security.cert.CertificateFactory;
import javax.crypto.Cipher;
import javax.crypto.SecretKeyFactory;

public class ProviderCapabilities {
    static void verify(Provider provider, String keyAlgorithm, String pbeAlgorithm)
            throws Exception {
        KeyFactory.getInstance(keyAlgorithm, provider);
        CertificateFactory.getInstance("X.509", provider);
        SecretKeyFactory.getInstance(pbeAlgorithm, provider);
        Cipher.getInstance(pbeAlgorithm, provider);
    }
}
~~~

Ví dụ này chủ động yêu cầu đủ bốn service. Trong ứng dụng thực tế, chỉ kiểm tra các service mà luồng cần dùng; không phải provider nào cũng phải hỗ trợ cả bốn.

Có thể xem provider đã đăng ký:

~~~java
import java.security.Provider;
import java.security.Security;

for (Provider provider : Security.getProviders()) {
    System.out.println(provider.getName() + " - " + provider.getVersionStr());
}
~~~

Kiểm tra service và thuật toán cụ thể quan trọng hơn việc provider xuất hiện trong danh sách. Provider có thể được cài đặt nhưng không có thuật toán, key size, curve hoặc chế độ mã hóa mà ứng dụng yêu cầu.

## 10. Giới hạn provider khi giải mã private key có mật khẩu

Trong Java 27:

~~~java
PEMDecoder decoder = PEMDecoder.of().withDecryption(password);
PrivateKey privateKey = decoder.decode(encryptedPem, PrivateKey.class);
~~~

Decoder được cấu hình để giải mã encrypted private key. Nó vẫn giải mã được PEM không mã hóa. Tuy nhiên, withDecryption không nhận Provider, vì vậy không thể dùng phương thức này để pin trực tiếp provider PBE cho thao tác decrypt.

Cần phân biệt hai lựa chọn:

1. withFactoriesOf(provider) điều khiển KeyFactory và CertificateFactory dùng để tạo đối tượng.
2. withDecryption(password) bật giải mã bằng password theo provider selection của runtime.

Nếu chính sách mật mã yêu cầu chỉ định rõ provider cho cả PBE SecretKeyFactory và Cipher, hãy dùng API EncryptedPrivateKeyInfo với provider được chỉ định hoặc một thư viện/provider integration có hỗ trợ explicit provider cho cả encrypt và decrypt.

### Vòng đời password

withDecryption(char[]) clone password và lưu bản sao trong decoder mới. Decoder là immutable và thread-safe, nhưng điều đó không có nghĩa password copy tự được xóa ngay sau một lần decode.

- Không tạo decoder đã cấu hình password rồi lưu vào singleton/global cache trong thời gian dài.
- Chỉ giữ password trong phạm vi cần thiết.
- Xóa mảng password phía caller bằng Arrays.fill(password, '\0') sau khi hoàn tất.
- Nhớ rằng thao tác đó chỉ xóa mảng gốc của caller; API đã clone một bản khác.
- Tránh đưa password vào command line, log, exception message hoặc system property.

## 11. Mã hóa private key: mặc định hay chỉ định provider?

### Cách gọn: dùng mặc định

Trong Java 27:

~~~java
char[] password = obtainPassword();

try {
    String encryptedPem = PEMEncoder.of()
            .withEncryption(password)
            .encodeToString(privateKey);
    storeSecurely(encryptedPem);
} finally {
    java.util.Arrays.fill(password, '\0');
}
~~~

withEncryption(password) dùng thuật toán mặc định được xác định bởi security property jdk.epkcs8.defaultAlgorithm và tham số mặc định của provider được chọn. Đây là lựa chọn ngắn gọn khi thuật toán mặc định phù hợp chính sách và provider selection mặc định được chấp nhận.

Trong Java 25, PEMEncoder.withEncryption chỉ cho phép encode PrivateKey bằng password. Java 27 hỗ trợ thêm KeyPair và PKCS8EncodedKeySpec trong encoder đã cấu hình encryption.

### Khi cần chỉ định thuật toán, parameters và provider

Java 27 cho phép tạo EncryptedPrivateKeyInfo trước, sau đó encode object đó thành PEM:

~~~java
import java.security.PEMEncoder;
import java.security.Provider;
import javax.crypto.EncryptedPrivateKeyInfo;
import java.security.PrivateKey;
import java.security.spec.AlgorithmParameterSpec;

static String encryptPrivateKey(
        PrivateKey privateKey,
        char[] password,
        String pbeAlgorithm,
        AlgorithmParameterSpec parameters,
        Provider encryptionProvider) {

    EncryptedPrivateKeyInfo encrypted =
            EncryptedPrivateKeyInfo.encrypt(
                    privateKey,
                    password,
                    pbeAlgorithm,
                    parameters,
                    encryptionProvider);

    return PEMEncoder.of().encodeToString(encrypted);
}
~~~

Provider ở overload này được dùng cho PBE SecretKeyFactory và Cipher. Khi parameters là null, provider áp dụng tham số mặc định của nó. Khi encryptionProvider là null, danh sách provider mặc định được dùng.

Chọn thuật toán và parameters dựa trên chính sách bảo mật, khả năng tương thích của hệ thống nhận và danh sách thuật toán provider hỗ trợ. Không sao chép một thuật toán PBE từ ví dụ mà chưa xác nhận provider triển khai nó.

### Java 25 tương ứng

Trong Java 25, overload chỉ định provider có tên encryptKey:

~~~java
EncryptedPrivateKeyInfo encrypted =
        EncryptedPrivateKeyInfo.encryptKey(
                privateKey,
                password,
                pbeAlgorithm,
                parameters,
                encryptionProvider);

String encryptedPem = PEMEncoder.of().encodeToString(encrypted);
~~~

Khi nâng lên Java 27, đổi sang EncryptedPrivateKeyInfo.encrypt(...) và API đầu vào tương ứng BinaryEncodable. Không dùng đồng thời tên method của hai release trong cùng source set.

## 12. Provider cho HSM và khóa không thể export

Một số provider, đặc biệt provider PKCS#11 kết nối HSM, trả về PrivateKey đại diện cho khóa nằm trong thiết bị. Khóa có thể được đánh dấu non-exportable; PrivateKey.getEncoded() có thể trả về null.

PEMEncoder cần một biểu diễn nhị phân của đối tượng. Nếu private key không thể export, việc encode nó thành PEM không phải thao tác được hỗ trợ và không nên tìm cách vượt qua chính sách non-exportable.

Trong kiến trúc HSM:

- Giữ private key trong HSM và dùng provider để ký/giải mã trực tiếp.
- Chỉ xuất public key hoặc certificate nếu policy cho phép.
- Lưu key reference/alias/identifier và metadata để ứng dụng tìm đúng key trong HSM.
- Không export private key chỉ để tiện cấu hình PEM.
- Kiểm tra khả năng serialize của provider trước khi thiết kế workflow backup/restore.

PEM phù hợp để trao đổi key material có thể export. Nó không thay thế cơ chế quản lý key handle, quyền sử dụng key và audit của HSM/KMS.

## 13. PEM, dữ liệu không hỗ trợ và giới hạn của parser

Trong Java 27, PEMDecoder trả về PEM khi nội dung không có class mật mã chuyên biệt tương ứng hoặc khi ứng dụng yêu cầu rõ PEM.class.

~~~java
import java.security.PEM;
import java.security.PEMDecoder;

PEM raw = PEMDecoder.of().decode(input, PEM.class);

System.out.println(raw.type());
System.out.println(raw.content().length);
~~~

PEM giữ nhãn type, Base64 content và optional leading data. Nó hữu ích khi cần lưu trữ hoặc định tuyến một PEM block mà ứng dụng chưa có kiểu Java chuyên biệt để biểu diễn.

Không xem PEM là bằng chứng dữ liệu hợp lệ. Việc có nhãn CERTIFICATE REQUEST, CMS hoặc PRIVATE KEY không chứng minh nội dung bên trong đúng ASN.1 schema hoặc được tin cậy. API raw PEM cũng không thay thế parser/validator chuyên biệt cho cấu trúc chưa được hỗ trợ.

Implementation có thể hỗ trợ thêm PEM types ngoài danh sách chuẩn được API mô tả. Nếu tích hợp nhiều vendor/provider, cần test những label và object types thực sự xuất hiện trong dữ liệu của hệ thống.

## 14. Chọn giữa JDK preview và thư viện ổn định

Quyết định không chỉ dựa trên số dòng code. Cần xét vòng đời API, provider support, thuật toán, loại PEM, yêu cầu compliance và khả năng nâng JDK.

| Tiêu chí | JDK PEM API preview | Thư viện PEM đã được phát hành ổn định |
| --- | --- | --- |
| Phụ thuộc | Có sẵn trong JDK, không cần thêm thư viện PEM riêng | Thêm dependency và theo dõi bản cập nhật |
| Độ ổn định API | Preview, có thể đổi hoặc bị loại bỏ | Phụ thuộc cam kết tương thích của thư viện/version |
| Provider | Có lựa chọn provider ở một số bước; phạm vi cụ thể theo API | Thường có API chọn provider cho key conversion và encryption/decryption |
| Loại PEM | Theo danh sách được JDK release hỗ trợ; loại khác có thể trả về raw PEM | Tùy thư viện và phiên bản, thường có nhiều cấu trúc PEM hơn |
| Tương thích runtime | Gắn với preview version của JDK | Có thể hỗ trợ nhiều JDK release |
| Hợp với | Prototype, thử nghiệm, module nội bộ kiểm soát được JDK | Hệ thống cần API ổn định, hỗ trợ nhiều runtime/provider |

### Khi nên thử JDK PEM API

- Ứng dụng kiểm soát được JDK release và có thể nâng cấp đồng bộ.
- PEM types nằm trong tập API hỗ trợ.
- Provider đáp ứng các factory và encryption algorithms cần thiết.
- Có test interoperability với hệ thống OpenSSL, PKI hoặc service đối tác.
- Nhóm chấp nhận việc source phải cập nhật khi preview thay đổi.

### Khi nên chọn thư viện ổn định

- Public API hoặc sản phẩm cần cam kết tương thích dài hạn.
- Ứng dụng phải chạy trên nhiều JDK release.
- Hệ thống cần provider-specific encryption/decryption hoặc loại PEM bổ sung.
- Chính sách compliance yêu cầu pin provider, thuật toán và tham số ở tất cả bước.
- Không thể chấp nhận thay đổi source khi chuyển JDK.

Một lựa chọn phổ biến là Bouncy Castle bcpkix, với PEMParser, JcaPEMKeyConverter và JcaPEMWriter. Với API hiện hành, dùng JcaPEMWriter; lớp PEMWriter cũ đã deprecated. JcaPEMKeyConverter cho phép chỉ định Provider khi chuyển key object sang JCA key. Luôn kiểm tra phiên bản thư viện, license, thuật toán và bản phân phối phù hợp với yêu cầu của tổ chức. [Bouncy Castle Java Documentation](https://www.bouncycastle.org/documentation/documentation-java/) · [JcaPEMKeyConverter 1.85](https://downloads.bouncycastle.org/java/docs/bcpkix-jdk14-javadoc/org/bouncycastle/openssl/jcajce/JcaPEMKeyConverter.html) · [JcaPEMWriter 1.79](https://downloads.bouncycastle.org/java/docs/bcpkix-jdk13-javadoc/org/bouncycastle/openssl/jcajce/JcaPEMWriter.html)

## 15. Đặt preview API sau một adapter

Nếu chọn thử nghiệm JDK PEM API trong ứng dụng, đừng để các kiểu preview lan khắp business layer. Tạo adapter nhỏ để cô lập dependency:

~~~java
public interface PemKeyCodec {
    String encodePublicKey(java.security.PublicKey key);
    java.security.PublicKey decodePublicKey(String pem);
}
~~~

Implementation dùng JDK 27 preview có thể dựa trên PEMEncoder/PEMDecoder; implementation khác có thể dùng thư viện ổn định. Business code chỉ phụ thuộc interface của ứng dụng.

Lợi ích:

- Khi JDK đổi BinaryEncodable hoặc tên method, chỉ adapter cần cập nhật.
- Có thể thay implementation nếu preview thay đổi hoặc bị loại bỏ.
- Test contract không phụ thuộc trực tiếp API preview.
- Có thể dùng provider khác nhau theo môi trường triển khai.

Adapter không biến preview API thành stable API. Nó chỉ giới hạn phạm vi thay đổi và giúp migration dễ kiểm soát.

## 16. Kiểm thử tương thích và interoperability

Một PEM round-trip thành công trong cùng JVM chưa đủ chứng minh dữ liệu tương thích với các hệ thống khác.

Bộ kiểm thử nên gồm:

1. Encode public key, decode lại bằng JDK API.
2. Encode certificate, decode lại và kiểm tra fingerprint.
3. Decode PEM được tạo từ OpenSSL hoặc hệ thống đối tác.
4. Encode PEM bằng ứng dụng rồi xác minh bằng OpenSSL/tool nhận.
5. Kiểm tra encrypted private key với đúng password và password sai.
6. Kiểm tra provider thiếu thuật toán hoặc không hỗ trợ key algorithm.
7. Kiểm tra PEM block không được hỗ trợ và raw PEM fallback.
8. Kiểm tra file chứa nhiều PEM blocks theo cách ứng dụng đọc từng block.
9. Kiểm tra certificate chain và trust validation riêng.
10. Chạy lại test trên JDK preview release mục tiêu và từng provider production.

### Xác minh khóa bằng thao tác mật mã

Sau khi decode private/public key, kiểm tra cặp khóa bằng một phép ký và xác minh chữ ký trên dữ liệu test. Điều này kiểm tra hai đối tượng có tương thích về mặt mật mã, thay vì chỉ so sánh chuỗi PEM hoặc tên thuật toán.

Với certificate, so sánh fingerprint và thực hiện path validation theo trust store của ứng dụng. Không coi parse thành công là certificate hợp lệ hoặc trusted.

## 17. Bảo vệ private key và file PEM

PEM là văn bản, vì vậy file private key có thể bị đọc bởi bất kỳ tiến trình/người dùng nào có quyền truy cập file.

- Hạn chế quyền đọc file private key và thư mục chứa key.
- Không commit private key vào Git hoặc đưa vào container image.
- Không log nội dung PEM, password hoặc encoded key bytes.
- Ưu tiên secret manager, KMS hoặc HSM cho key material có giá trị cao.
- Nếu buộc phải lưu private key dạng file, dùng encrypted PKCS #8 với thuật toán và parameters được policy chấp thuận.
- Dùng password đủ mạnh và quản lý password tách khỏi file key.
- Xóa password char arrays phía caller khi hoàn tất.
- Có quy trình rotation, revocation, backup và incident response.
- Bảo vệ certificate/private key metadata để tránh nhầm lẫn giữa môi trường dev, staging và production.

Mã hóa private key trong PEM chỉ bảo vệ dữ liệu lưu trữ ở một mức nhất định. Nó không thay thế quyền truy cập hệ thống file, quản lý secret, HSM hoặc quy trình kiểm soát sử dụng khóa.

## 18. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Compiler báo preview disabled | Chưa bật --enable-preview hoặc dùng sai JDK | Bật preview ở compile và runtime cùng release |
| NoSuchMethodError sau khi nâng JDK | Code dùng API preview cũ như withFactory hoặc encryptKey | Biên dịch lại và cập nhật theo JEP của release mới |
| Provider không tìm thấy KeyFactory | Provider thiếu service/algorithm cho key type | Kiểm tra KeyFactory.getInstance(algorithm, provider) |
| Decode certificate thất bại với provider đã chọn | Provider không có CertificateFactory.X.509 | Chọn provider phù hợp hoặc default provider selection |
| Private key encrypted nhưng decode trả EncryptedPrivateKeyInfo | Decoder chưa được cấu hình withDecryption | Cấu hình decoder với password hoặc xử lý EPKI riêng |
| Decrypt thất bại | Password sai, PBE algorithm/parameters không tương thích, provider thiếu service | Kiểm tra algorithm, parameters và provider; không log password |
| PEMEncoder không encode được private key | Key không exportable hoặc getEncoded() không có dữ liệu | Dùng key trực tiếp trong HSM/KMS thay vì export |
| PEM label lạ trả về PEM | JDK implementation không có class tương ứng | Dùng parser hỗ trợ type đó hoặc xử lý raw PEM có kiểm tra |
| PEM parse thành công nhưng TLS validation thất bại | Parse không đồng nghĩa trust/path validation | Kiểm tra certificate chain, trust anchor, hostname và validity |
| Password còn giữ lâu trong decoder | Decoder configured với password được cache lâu dài | Giới hạn vòng đời decoder, không lưu global |

## 19. Bài thực hành: chọn preview hay thư viện ổn định

### Bối cảnh

Một dịch vụ Java nhận certificate và private key từ hệ thống PKI nội bộ. Môi trường production dùng provider chuyên biệt; nhóm cần quyết định có chuyển từ parser PEM hiện tại sang JDK PEM API hay không.

### Nhiệm vụ

1. Xác nhận JDK release đang dùng và trạng thái preview của PEM API.
2. Tạo một nhánh thử nghiệm với JDK 27 và --enable-preview.
3. Decode một public key và một X.509 certificate bằng PEMDecoder.
4. Kiểm tra provider được chọn có KeyFactory và CertificateFactory cần thiết.
5. Thử withFactoriesOf(provider) và ghi lại trường hợp provider thiếu một service.
6. Encode private key bằng mặc định withEncryption(password).
7. Tạo một biến thể dùng EncryptedPrivateKeyInfo.encrypt(...) để chỉ định PBE algorithm, parameters và provider.
8. So sánh với thư viện ổn định như Bouncy Castle PEMParser và JcaPEMKeyConverter.
9. Kiểm thử round-trip với OpenSSL và hệ thống PKI đang tích hợp.
10. Xác minh certificate trust và chữ ký bằng JCA.
11. Đánh giá key exportability nếu provider kết nối HSM.
12. Đưa ra quyết định: dùng preview sau adapter, dùng thư viện ổn định hay giữ quy trình hiện tại.

### Câu hỏi tự đánh giá

1. Vì sao PEM API vẫn cần --enable-preview ở JDK 27?
2. JEP 470, JEP 524 và JEP 538 tương ứng những release nào?
3. Vì sao không dùng DEREncodable làm kiểu chung khi compile với JDK 27?
4. PEMRecord đã được đổi tên thành gì?
5. withFactoriesOf(provider) chọn những service JCA nào?
6. Provider truyền cho withFactoriesOf có tự động pin PBE Cipher không?
7. PEMEncoder.withEncryption(password) lấy thuật toán mặc định từ đâu?
8. Khi nào cần EncryptedPrivateKeyInfo.encrypt(...)?
9. Vì sao provider phải hỗ trợ cả SecretKeyFactory và Cipher cho PBE?
10. Vì sao một private key trong HSM có thể không encode được sang PEM?
11. Parse certificate thành công có chứng minh certificate trusted không?
12. Khi nào nên chọn thư viện ổn định thay vì PEM preview API?

## 20. Checklist quyết định áp dụng

- [ ] Đã xác định JDK release và đúng preview JEP tương ứng.
- [ ] Compiler/runtime đều bật preview cho cùng release.
- [ ] Không trộn API names giữa Java 25, 26 và 27.
- [ ] Đã xác định PEM types thực tế cần hỗ trợ.
- [ ] Provider có đúng KeyFactory và CertificateFactory.
- [ ] Provider có SecretKeyFactory và Cipher cho PBE algorithm nếu mã hóa private key.
- [ ] Đã hiểu withFactoriesOf không pin provider cho mọi bước mã hóa/giải mã.
- [ ] Thuật toán và parameters tương thích với hệ thống nhận PEM.
- [ ] HSM/KMS key có được phép export hay không đã được xác nhận.
- [ ] Private key, password và PEM contents không xuất hiện trong log.
- [ ] Có kiểm thử với OpenSSL hoặc hệ thống tích hợp thực tế.
- [ ] Certificate path validation và trust policy được kiểm tra riêng.
- [ ] Preview API được cô lập sau adapter nếu dùng thử.
- [ ] Có kế hoạch cập nhật source khi JEP thay đổi ở release kế tiếp.
- [ ] Nếu cần API ổn định, đã đánh giá thư viện PEM có version/support phù hợp.
- [ ] Có quy trình rotation, backup, revoke và xử lý sự cố khóa.

**Tiêu chí hoàn thành:** người học có thể bật đúng preview PEM API theo JDK release, xác định provider nào chịu trách nhiệm cho từng bước, chọn cấu hình encryption có provider rõ ràng khi cần, và đưa ra quyết định dùng preview hay thư viện ổn định dựa trên yêu cầu tương thích, compliance và vòng đời vận hành.

## 21. Tài liệu chính thức

- [JEP 470 — PEM Encodings of Cryptographic Objects (Preview)](https://openjdk.org/jeps/470): preview đầu tiên trong Java 25.
- [JEP 524 — PEM Encodings of Cryptographic Objects (Second Preview)](https://openjdk.org/jeps/524): thay đổi trong Java 26, bao gồm kiểu PEM.
- [JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538): preview thứ ba trong Java 27.
- [PEMDecoder — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html): decode, withFactoriesOf, withDecryption và provider scope.
- [PEMEncoder — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html): encode và withEncryption.
- [EncryptedPrivateKeyInfo — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html): encrypt, provider, parameters và giải mã PKCS #8.
- [BinaryEncodable — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html): kiểu dữ liệu chung mới của preview lần ba.
- [JDK 27 Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): xác nhận PEM API vẫn là preview trong JDK 27.
- [Java Cryptography Architecture Reference Guide — Java SE 25](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html): cách dùng PEM API và EncryptedPrivateKeyInfo trong JDK 25.
- [Bouncy Castle Java Documentation](https://www.bouncycastle.org/documentation/documentation-java/): tài liệu thư viện mật mã và các module PKIX/PEM.
- [RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468): định dạng PEM văn bản.

Khi học trong phạm vi Java 25, dùng JEP 470 và API docs Java SE 25. Khi đánh giá áp dụng hiện nay, đối chiếu JEP 538 và API docs Java SE 27. Cho đến khi PEM API trở thành permanent feature, cần coi mọi API preview là phụ thuộc có thể thay đổi và có kế hoạch thay thế hoặc nâng cấp rõ ràng.
