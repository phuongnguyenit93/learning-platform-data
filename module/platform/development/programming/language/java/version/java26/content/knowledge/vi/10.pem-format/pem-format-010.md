# Giải mã định dạng khác với kiểm tra độ tin cậy chứng thư

Một file `server-chain.pem` có thể được giải mã thành các đối tượng `X509Certificate` mà không phát sinh lỗi. Điều đó chỉ cho biết dữ liệu có cú pháp và cấu trúc mà bộ phân tích hiểu được. Nó chưa chứng minh chứng thư được một CA đáng tin cậy cấp, chuỗi chứng thư dẫn tới trust anchor được ứng dụng chấp nhận, chứng thư chưa bị thu hồi, hoặc chứng thư phù hợp với tên máy chủ đang kết nối.

Trong Java, hãy tách rõ hai việc: **đọc PEM để lấy đối tượng mật mã** và **xác minh chứng thư theo chính sách tin cậy của ứng dụng**. `PEMDecoder` là API mới để chuyển PEM thành đối tượng Java; `CertificateFactory`, `CertPathBuilder`, `CertPathValidator` và `KeyStore` cung cấp các API chuẩn để đọc chứng thư và kiểm tra chuỗi tin cậy. Các API kiểm tra trust đã ổn định từ lâu; PEM API chỉ trở thành API chính thức trong JDK 28.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích PEM là định dạng bao ngoài dữ liệu nhị phân bằng Base64 và nhãn loại nội dung.
- Nhận biết các PEM label phổ biến và cấu trúc ASN.1 mà chúng đại diện.
- Dùng `PEMDecoder` trong Java 26 preview và biết thay đổi API ở Java 27, JDK 28.
- Dùng `CertificateFactory` để đọc X.509 certificate mà không phụ thuộc preview API.
- Phân biệt parse certificate, kiểm tra chữ ký, kiểm tra thời hạn và xác minh certification path.
- Dùng trust anchor và PKIX để xây dựng, xác minh chuỗi chứng thư; hiểu vai trò của OCSP, CRL và hostname verification.

## 1. PEM là định dạng vận chuyển, không phải một loại chứng thư

PEM (Privacy-Enhanced Mail) là cách biểu diễn dữ liệu nhị phân dưới dạng văn bản. Một khối PEM thông thường gồm:

1. Dòng mở đầu `-----BEGIN LABEL-----`.
2. Nội dung nhị phân được mã hóa Base64, thường chia thành nhiều dòng.
3. Dòng kết thúc `-----END LABEL-----` có cùng label.

Ví dụ về một certificate:

```text
-----BEGIN CERTIFICATE-----
MIIB...phần dữ liệu Base64...
...các dòng Base64 tiếp theo...
-----END CERTIFICATE-----
```

Nội dung sau khi giải mã Base64 là cấu trúc ASN.1 được mã hóa theo BER hoặc DER tùy loại dữ liệu và tiêu chuẩn áp dụng. PEM không phải thuật toán mã hóa và không tự bảo vệ tính bí mật. Một file `PRIVATE KEY` thông thường chỉ được Base64-encode; ai đọc được file có thể lấy khóa riêng. Với khóa riêng cần bảo vệ bằng mật khẩu, định dạng thường gặp là `ENCRYPTED PRIVATE KEY` theo PKCS #8.

RFC 7468 quy định cách biểu diễn văn bản cho nhiều cấu trúc PKIX, PKCS và CMS. Nhãn trong header cho biết loại cấu trúc được mong đợi; nó không phải bằng chứng rằng dữ liệu đúng, hợp lệ hoặc đáng tin cậy. Một parser cần kiểm tra nội dung thật sự phù hợp với cấu trúc được khai báo.

## 2. Nhận biết label và cấu trúc bên trong

| PEM label | Nội dung nhị phân thường tương ứng | Kết quả hoặc mục đích |
|---|---|---|
| `CERTIFICATE` | X.509 `Certificate` | Chứng thư X.509; có thể đọc thành `X509Certificate` |
| `PUBLIC KEY` | SubjectPublicKeyInfo theo X.509 | Khóa công khai; có thể đọc thành `PublicKey` hoặc `X509EncodedKeySpec` |
| `PRIVATE KEY` | PKCS #8 `PrivateKeyInfo` hoặc `OneAsymmetricKey` | Khóa riêng không mã hóa; có thể đọc thành `PrivateKey` hoặc `PKCS8EncodedKeySpec` |
| `ENCRYPTED PRIVATE KEY` | PKCS #8 `EncryptedPrivateKeyInfo` | Khóa riêng PKCS #8 đã được mã hóa; cần mật khẩu hoặc khóa giải mã |
| `X509 CRL` | X.509 `CertificateList` | Danh sách chứng thư bị thu hồi; có thể đọc thành `X509CRL` |
| `CERTIFICATE REQUEST` | PKCS #10 CertificationRequest | CSR do chủ khóa gửi CA để xin cấp chứng thư; chưa phải certificate |
| `PKCS7` hoặc `CMS` | SignedData/CMS container | Có thể chứa nhiều certificate hoặc CRL; phải hiểu mục đích và trường dữ liệu bên trong |

Không suy ra loại dữ liệu chỉ từ tên file như `.pem`, `.crt`, `.key` hoặc `.cer`; hãy đọc label và kiểm tra nội dung. Các label như `RSA PRIVATE KEY`, `EC PRIVATE KEY`, `OPENSSH PRIVATE KEY` hoặc `TRUSTED CERTIFICATE` có thể xuất hiện trong hệ thống thực tế nhưng không đồng nghĩa với các cấu trúc chuẩn `PRIVATE KEY` hoặc `PUBLIC KEY` ở bảng trên. Khả năng đọc chúng phụ thuộc định dạng, provider và implementation. Không giả định mọi JDK hoặc provider đều hỗ trợ cùng một bộ label.

Đặc biệt:

- `CERTIFICATE REQUEST` là yêu cầu cấp chứng thư. Nó không thể được đưa vào trust store như một CA certificate.
- `PUBLIC KEY` không phải certificate. Nó không chứa chuỗi issuer, thời hạn và các extension của X.509 certificate.
- `ENCRYPTED PRIVATE KEY` không được giải mã chỉ bằng Base64. Cần xử lý mã hóa PKCS #8 và mật khẩu đúng.
- `PKCS7`/`CMS` là container. Việc trích xuất certificate từ container không có nghĩa chữ ký CMS hoặc các nội dung khác đã được xác minh.

## 3. PEM API của JDK và trạng thái theo phiên bản

Java bổ sung API PEM trong package `java.security` để chuyển đổi giữa PEM text và các đối tượng mật mã có biểu diễn nhị phân tiêu chuẩn:

| Phiên bản | JEP | Trạng thái | Thay đổi chính |
|---|---|---|---|
| Java 25 | JEP 470 | Preview lần 1 | Giới thiệu `PEMDecoder`, `PEMEncoder` và kiểu biểu diễn PEM |
| Java 26 | JEP 524 | Preview lần 2 | Điều chỉnh API; dùng `DEREncodable` và `PEMRecord` |
| Java 27 | JEP 538 | Preview lần 3 | Đổi `DEREncodable` thành `BinaryEncodable`, `PEMRecord` thành `PEM`; đổi `withFactory` thành `withFactoriesOf`; bổ sung `CryptoException` |
| JDK 28 | JEP 542 | Final | Chuẩn hóa API PEM sau ba lần preview |

Tại ngày 27-11-2026, Java 27 là bản feature release mới nhất đã GA; PEM API trong JDK 27 vẫn là preview và cần bật `--enable-preview`. JEP 542 đã hoàn tất để đưa API vào JDK 28 dưới dạng chính thức, nhưng JDK 28 vẫn là Early Access tại thời điểm này. Có thể dùng JDK 28 EA để thử nghiệm API final, nhưng chưa coi EA build là runtime production GA.

### Đọc certificate bằng PEMDecoder trong Java 26

Ví dụ này dùng API preview lần thứ hai của Java 26:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.cert.X509Certificate;

public class ReadPemCertificate {
    public static void main(String[] args) throws IOException {
        String pemText = Files.readString(
                Path.of("server-cert.pem"), StandardCharsets.UTF_8);

        X509Certificate certificate = PEMDecoder.of()
                .decode(pemText, X509Certificate.class);

        System.out.println(certificate.getSubjectX500Principal());
        System.out.println(certificate.getIssuerX500Principal());
        System.out.println(certificate.getNotAfter());
    }
}
```

Biên dịch và chạy bằng chính JDK 26:

```bash
javac --release 26 --enable-preview -Xlint:preview ReadPemCertificate.java
java --enable-preview ReadPemCertificate
```

`decode(pemText, X509Certificate.class)` yêu cầu decoder trả về đúng kiểu certificate. Nếu label hoặc nội dung không tương thích, quá trình decode có thể thất bại. Việc in subject, issuer và ngày hết hạn chỉ là đọc trường dữ liệu; nó không xác minh trust.

Trong Java 26, `PEMDecoder` còn có thể trả về `X509CRL`, `PublicKey`, `PrivateKey`, `KeyPair` trong trường hợp định dạng chứa cả khóa công khai và riêng, `PKCS8EncodedKeySpec`, `X509EncodedKeySpec`, `EncryptedPrivateKeyInfo` hoặc `PEMRecord` cho các loại chưa có lớp Java tương ứng. Danh sách thực tế còn phụ thuộc implementation; tài liệu API của đúng JDK và provider là căn cứ để xác nhận.

### Thay đổi từ Java 26 sang Java 27 và JDK 28

- Java 26 dùng marker interface preview `DEREncodable` và kiểu `PEMRecord` để giữ nội dung PEM chưa ánh xạ thành đối tượng mật mã.
- Java 27 dùng `BinaryEncodable` và lớp `PEM`. `PEM` có thể giữ label, Base64 content và dữ liệu xuất hiện trước header.
- Java 26 đặt provider bằng `withFactory(Provider)`; Java 27 đổi thành `withFactoriesOf(Provider)` vì cả `KeyFactory` và `CertificateFactory` được lấy từ provider đó.
- Java 27 dùng `CryptoException` cho lỗi xử lý mật mã và có thể giải mã khóa riêng đã mã hóa bằng `withDecryption(char[])`.
- JDK 28 final hóa API theo JEP 542. Khi chuyển sang JDK 28 GA, dùng API final trong tài liệu của chính release đó và bỏ `--enable-preview` cho phần PEM.

Ví dụ Java 27 có thể dùng cùng lời gọi `decode(String, X509Certificate.class)`, nhưng phải biên dịch và chạy bằng JDK 27 với `--enable-preview`. Không lấy mã nhị phân hoặc API preview từ JDK 26 rồi giả định chúng tương thích với JDK 27; hai lần preview có thay đổi tên kiểu và một số phương thức.

## 4. Dùng API ổn định để đọc X.509 certificate

Không cần PEM preview API chỉ để đọc một certificate X.509. `CertificateFactory` là API chính thức từ các phiên bản Java cũ và vẫn được hỗ trợ. Với `X.509`, factory đọc được certificate DER hoặc Base64 PEM có header `BEGIN CERTIFICATE` và footer `END CERTIFICATE`.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public class ReadCertificateStable {
    static X509Certificate readCertificate(Path file)
            throws IOException, CertificateException {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");

        try (InputStream input = Files.newInputStream(file)) {
            return (X509Certificate) factory.generateCertificate(input);
        }
    }
}
```

Đọc nhiều certificate trong một file bundle:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.Certificate;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Collection;

static Collection<? extends Certificate> readCertificates(Path bundle)
        throws IOException, CertificateException {
    CertificateFactory factory = CertificateFactory.getInstance("X.509");
    try (InputStream input = Files.newInputStream(bundle)) {
        return factory.generateCertificates(input);
    }
}
```

`generateCertificates` có thể đọc chuỗi certificate được mã hóa theo các dạng được factory hỗ trợ và PKCS #7 SignedData chỉ chứa certificate. Tài liệu `CertificateFactory` nói rõ chữ ký và nội dung khác của PKCS #7 bị bỏ qua khi chỉ trích xuất certificate. Do đó, parse bundle thành công vẫn không xác nhận chữ ký của CMS, chuỗi issuer hoặc trust anchor.

Không dùng `InputStream.available()` làm điều kiện để quyết định còn dữ liệu hay không; đó không phải phép đo tổng số byte còn lại đáng tin cậy cho mọi stream. Dùng `generateCertificates` cho bundle hoặc xử lý stream theo hợp đồng của API.

## 5. Đọc PEM thành công không có nghĩa certificate đáng tin cậy

Một certificate có thể parse đúng nhưng vẫn không được chấp nhận. Ví dụ:

- Chữ ký của certificate không xác minh được bằng khóa của issuer.
- Issuer không dẫn tới một CA mà ứng dụng tin cậy.
- Certificate đã hết hạn hoặc chưa tới ngày hiệu lực.
- CA certificate vi phạm `BasicConstraints`, `pathLenConstraint`, `KeyUsage` hoặc chính sách của path.
- Certificate đã bị thu hồi theo CRL hoặc OCSP.
- Certificate được cấp cho một tên DNS/IP khác với endpoint ứng dụng đang kết nối.
- Extended Key Usage không cho phép mục đích sử dụng, ví dụ certificate không được cấp cho TLS server authentication.

Các phép kiểm tra đơn lẻ cũng không thay thế path validation:

| Phép kiểm tra | Xác nhận điều gì | Không xác nhận điều gì |
|---|---|---|
| `PEMDecoder.decode(...)` hoặc `CertificateFactory.generateCertificate(...)` | Nội dung PEM/DER được parse thành certificate object | Certificate được cấp bởi CA đáng tin cậy |
| `X509Certificate.checkValidity()` | Thời điểm hiện tại nằm trong `notBefore` và `notAfter` | Chữ ký, issuer chain, revocation hoặc hostname |
| `X509Certificate.verify(issuerPublicKey)` | Chữ ký trên certificate khớp với khóa công khai được cung cấp | Khóa đó thuộc trust anchor được ứng dụng chấp nhận hay không |
| `CertPathValidator` với PKIX trust anchors | Chuỗi chứng thư và các ràng buộc PKIX có hợp lệ theo chính sách đầu vào hay không | Tự động xác minh DNS/IP endpoint trong mọi ngữ cảnh |
| TLS endpoint identification | Tên endpoint có khớp danh tính trong certificate theo quy tắc TLS hay không | Thay thế việc thiết lập trust anchors hoặc kiểm tra revocation |

Đừng nhầm một certificate tự ký (self-signed) với một certificate đáng tin. Tự ký chỉ nói rằng chữ ký của certificate được tạo bởi khóa tương ứng với public key của chính certificate đó. Ứng dụng chỉ tin certificate này khi trust policy của ứng dụng đã chủ động cấu hình nó làm trust anchor.

## 6. Xây dựng và xác minh chuỗi tin cậy bằng PKIX

Để xác minh certificate, ứng dụng cần ít nhất:

1. **Target certificate:** certificate của thực thể cần xác minh, ví dụ certificate máy chủ.
2. **Intermediate certificates:** các CA trung gian giúp nối target certificate tới trust anchor.
3. **Trust anchors:** các CA mà ứng dụng đã tin cậy từ một nguồn cấu hình đáng tin cậy, thường được lưu trong `KeyStore`.
4. **Chính sách kiểm tra:** thời điểm xác minh, mục đích sử dụng, revocation, certificate policies và các giới hạn theo ứng dụng.

Một certificate bundle được gửi từ server thường chứa leaf certificate và một số intermediate certificates. Root CA có thể không được gửi kèm; ngay cả khi bundle có root, không được tự động tin root đó. Trust anchor phải đến từ trust store hoặc cấu hình tin cậy do ứng dụng quản lý.

### Dùng CertPathBuilder để tìm đường dẫn tới trust anchor

Khi đã có target certificate và tập intermediate candidates, `CertPathBuilder` có thể tìm đường dẫn PKIX tới một trust anchor trong `KeyStore`. Ví dụ dưới đây giả định `trustStore` đã được nạp từ cấu hình tin cậy của ứng dụng; `leaf` là certificate máy chủ đã parse và `presentedCertificates` là các certificate lấy từ bundle PEM.

```java
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.cert.CertPathBuilder;
import java.security.cert.CertStore;
import java.security.cert.CollectionCertStoreParameters;
import java.security.cert.PKIXBuilderParameters;
import java.security.cert.PKIXCertPathBuilderResult;
import java.security.cert.X509CertSelector;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

static PKIXCertPathBuilderResult buildTrustedPath(
        X509Certificate leaf,
        Collection<X509Certificate> presentedCertificates,
        KeyStore trustStore) throws GeneralSecurityException {

    X509CertSelector target = new X509CertSelector();
    target.setCertificate(leaf);

    PKIXBuilderParameters parameters =
            new PKIXBuilderParameters(trustStore, target);

    Set<X509Certificate> candidates = new LinkedHashSet<>(presentedCertificates);
    candidates.add(leaf);

    CertStore certificateStore = CertStore.getInstance(
            "Collection",
            new CollectionCertStoreParameters(candidates));
    parameters.addCertStore(certificateStore);

    // Revocation checking được bật mặc định; có thể cấu hình PKIXRevocationChecker.
    parameters.setRevocationEnabled(true);

    CertPathBuilder builder = CertPathBuilder.getInstance("PKIX");
    return (PKIXCertPathBuilderResult) builder.build(parameters);
}
```

`PKIXBuilderParameters` lấy các trust anchors từ trusted certificate entries của `trustStore`. `CertStore` chỉ cung cấp các certificate ứng viên để builder tìm issuer/intermediate. Nếu không tìm được đường dẫn tới một trust anchor hợp lệ, `build()` ném `CertPathBuilderException` hoặc lỗi kiểm tra tham số liên quan. Việc có một root certificate trong file PEM đầu vào không làm root đó trở thành trust anchor.

Nếu ứng dụng đã biết chính xác thứ tự chuỗi certificate, có thể tạo `CertPath` bằng `CertificateFactory.generateCertPath(List)` và gọi `CertPathValidator.getInstance("PKIX").validate(path, parameters)`. Với X.509, thứ tự path thường bắt đầu từ target/leaf và đi lên intermediate; trust anchor được cung cấp riêng trong `PKIXParameters` và không phải phần tử cuối của `CertPath`.

`CertPathBuilder` và `CertPathValidator` kiểm tra chữ ký, thời hạn, ràng buộc CA, path length, policy và các quy tắc PKIX liên quan theo trust anchors cùng parameters được cung cấp. Chúng không thể tự quyết định CA nào nên được ứng dụng tin cậy; lựa chọn trust anchor là chính sách của relying party.

## 7. Revocation: giải mã CRL không phải kiểm tra trạng thái thu hồi

PEM label `X509 CRL` có thể được giải mã thành `X509CRL`. Điều đó chỉ tạo đối tượng biểu diễn danh sách thu hồi. Ứng dụng vẫn phải xác minh CRL, kiểm tra issuer, chữ ký, thời hạn và dùng dữ liệu đó trong quy trình kiểm tra revocation.

PKIX hỗ trợ kiểm tra thu hồi bằng:

- **OCSP:** truy vấn trạng thái certificate qua dịch vụ Online Certificate Status Protocol.
- **CRL:** đối chiếu serial number với Certificate Revocation List được CA phát hành.

`PKIXParameters` bật revocation checking theo mặc định. Provider PKIX của JDK có cơ chế mặc định riêng; `PKIXRevocationChecker` cho phép ứng dụng cấu hình rõ OCSP/CRL, địa chỉ OCSP responder và lựa chọn như ưu tiên CRL hoặc không fallback. Nếu môi trường yêu cầu fail-closed, phải xác định hành vi khi không truy cập được OCSP/CRL; đừng âm thầm tắt revocation chỉ để làm cho validation thành công.

Nếu chỉ parse một CRL từ PEM nhưng không đưa nó vào quy trình PKIX hoặc không cấu hình nguồn revocation, ứng dụng chưa thể kết luận certificate còn hiệu lực về mặt thu hồi.

## 8. Hostname và mục đích sử dụng là kiểm tra riêng

PKIX path validation xác minh đường dẫn chứng thư tới trust anchor, nhưng việc kết nối tới `api.example.com` còn cần kiểm tra certificate có danh tính DNS/IP tương ứng hay không. Với TLS cho HTTPS, dùng client TLS/HTTP chuẩn có endpoint identification được bật theo chế độ HTTPS; không thay hostname verification bằng việc chỉ gọi `CertPathBuilder` thành công.

Ngoài ra, certificate cần phù hợp với mục đích sử dụng:

- TLS server thường cần EKU `serverAuth` nếu certificate có EKU extension.
- TLS client thường cần EKU `clientAuth` nếu certificate có EKU extension.
- `KeyUsage`, `BasicConstraints`, name constraints và policy OID phải phù hợp với vai trò của certificate trong chuỗi.
- Ứng dụng ký dữ liệu hoặc xác thực danh tính có thể cần kiểm tra policy và extension bổ sung riêng.

Không dùng một certificate hợp lệ về PKIX cho mọi giao thức hoặc mục đích. Trust là quyết định theo ngữ cảnh sử dụng, không chỉ là kết quả parse hoặc chữ ký hợp lệ.

## 9. Khóa riêng: decode đúng cấu trúc và bảo vệ bí mật

Đối với khóa riêng, cần phân biệt cấu trúc và cách bảo vệ:

- `PRIVATE KEY` là PKCS #8 không mã hóa. Có thể đọc thành `PrivateKey` nếu algorithm/provider hỗ trợ.
- `ENCRYPTED PRIVATE KEY` là PKCS #8 đã mã hóa. Phải giải mã bằng mật khẩu phù hợp.
- `PUBLIC KEY` là SubjectPublicKeyInfo; không thể dùng nó làm khóa riêng.
- `CERTIFICATE` chứa public key trong certificate nhưng không chứa private key.

Với Java 26 preview, có thể giải mã khóa PKCS #8 được mã hóa bằng decoder cấu hình `withDecryption(char[])`:

```java
import java.security.PEMDecoder;
import java.security.PrivateKey;
import java.util.Arrays;

char[] password = obtainPasswordFromSecretStore();
try {
    PEMDecoder decoder = PEMDecoder.of().withDecryption(password);
    PrivateKey privateKey = decoder.decode(encryptedPrivateKeyPem,
            PrivateKey.class);

    // Sử dụng privateKey trong phạm vi cần thiết.
} finally {
    Arrays.fill(password, '\0');
}
```

API decoder sao chép password khi cấu hình, nhưng ứng dụng vẫn nên xóa mảng mật khẩu gốc sau khi sử dụng. Không ghi private key, password hoặc nội dung PEM nhạy cảm vào log, exception message, telemetry hay source control. Bảo vệ file bằng quyền truy cập hệ thống, secret manager hoặc HSM/KMS phù hợp; xóa mảng `char[]` không thể bảo đảm xóa mọi bản sao trong bộ nhớ.

Nếu dùng PEM API preview trên JDK 27, kiểu lỗi giải mã mật mã và tên phương thức provider đã thay đổi so với Java 26. Đọc tài liệu của JDK cụ thể; không giả định mã preview có cùng API surface qua các release.

## 10. Những nhầm lẫn và lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `PEMDecoder` không có trong JDK mục tiêu | JDK quá cũ hoặc đang dùng JDK chưa cung cấp API | Kiểm tra `java --version`, `javac --version` và API của release |
| `IllegalArgumentException` hoặc `CertificateException` khi decode | Header/footer không khớp, Base64 sai hoặc nội dung ASN.1 không hợp lệ | Kiểm tra label, dữ liệu, encoding và tính toàn vẹn file |
| `ClassCastException` khi dùng `decode(..., X509Certificate.class)` | Label không đại diện cho certificate hoặc kiểu yêu cầu không khớp nội dung | Dùng đúng class theo PEM type; xử lý loại không hỗ trợ riêng |
| Decode thành công nhưng PKIX builder thất bại | Không có trust anchor phù hợp, thiếu intermediate, chữ ký/path constraints không hợp lệ hoặc certificate hết hạn | Kiểm tra trust store, chain candidates, thời hạn và lỗi `CertPathBuilderException` |
| Certificate hợp lệ theo PKIX nhưng HTTPS vẫn thất bại | Hostname không khớp SAN, EKU/KeyUsage không phù hợp hoặc TLS policy từ chối | Bật endpoint identification và kiểm tra mục đích sử dụng |
| Khóa `ENCRYPTED PRIVATE KEY` không giải mã được | Sai password, thuật toán mã hóa không được provider hỗ trợ hoặc dữ liệu hỏng | Kiểm tra nguồn secret, provider và định dạng PKCS #8 |
| `CERTIFICATE REQUEST` không dùng được làm trust anchor | CSR không phải certificate | Gửi CSR tới CA; chỉ dùng certificate được CA phát hành sau khi kiểm tra |
| Có `X509 CRL` nhưng certificate vẫn chưa được kiểm tra thu hồi | CRL mới chỉ được parse, chưa được tích hợp vào PKIX revocation checking | Cấu hình OCSP/CRL checker và chính sách fail-open/fail-closed rõ ràng |

## 11. Quy trình kiểm tra trước khi chấp nhận certificate

1. Đọc file từ nguồn có kiểm soát; giới hạn kích thước đầu vào và từ chối file bị cắt cụt.
2. Kiểm tra label và decode đúng loại dữ liệu; không suy đoán dựa trên phần mở rộng file.
3. Parse thành `X509Certificate` hoặc đối tượng mật mã tương ứng.
4. Lấy trust anchors từ trust store đã được quản trị; không tự tin mọi certificate được gửi kèm.
5. Xây dựng và xác minh certification path bằng PKIX.
6. Thực hiện revocation checking theo chính sách OCSP/CRL của ứng dụng.
7. Xác minh hostname/SAN, EKU, KeyUsage và các điều kiện riêng của giao thức.
8. Chỉ sau khi các kiểm tra bắt buộc đều đạt mới dùng certificate cho TLS, xác thực hoặc ký/xác minh theo mục đích đã định.

## 12. Bài tập thực hành

Một dịch vụ HTTPS cung cấp ba file: `leaf.pem`, `intermediates.pem` và `root-ca.pem`. File `leaf.pem` parse thành công bằng `CertificateFactory`. Hãy thiết kế quy trình để quyết định certificate có được ứng dụng tin cậy hay không.

**Yêu cầu:**

1. Giải thích cấu trúc của label `CERTIFICATE` và dữ liệu Base64 bên trong.
2. Đọc `leaf.pem` bằng `CertificateFactory.getInstance("X.509")`.
3. Đọc bundle `intermediates.pem` bằng `generateCertificates` và chỉ ra vì sao collection trả về không tự có thứ tự tin cậy.
4. Tạo trust store từ CA đã được tổ chức phê duyệt; không tự thêm `root-ca.pem` nhận từ cùng nguồn không đáng tin vào trust store.
5. Dùng `PKIXBuilderParameters`, `CertStore` và `CertPathBuilder` để tìm đường dẫn từ leaf tới trust anchor.
6. Kiểm tra revocation qua OCSP/CRL theo chính sách và giải thích vì sao chỉ parse `X509CRL` chưa đủ.
7. Xác minh SAN có DNS/IP khớp endpoint và EKU/KeyUsage phù hợp TLS server.
8. Chạy thêm ví dụ `PEMDecoder` trên JDK 26 với `--enable-preview`; phân biệt phần decode với phần trust validation.

**Kết quả mong đợi:**

- Người học phân biệt được PEM text, Base64, DER và X.509 certificate.
- `CertificateFactory` parse thành công chỉ chứng minh dữ liệu đọc được.
- Trust anchors đến từ trust store do ứng dụng quản lý; root certificate trong bundle không tự trở thành trusted.
- PKIX builder xác minh được path theo trust anchors và policy đã cấu hình.
- Revocation, hostname và mục đích sử dụng được kiểm tra theo các bước riêng.
- Người học nhận biết PEM API ở Java 26/27 là preview và JEP 542 final hóa API trong JDK 28.

## Tài liệu tham khảo

- [RFC 7468: Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468.html): cấu trúc PEM, label `CERTIFICATE`, PKCS #8, CRL và CSR.
- [RFC 5280: Internet X.509 Public Key Infrastructure Certificate and Certificate Revocation List Profile](https://www.rfc-editor.org/rfc/rfc5280.html): certification path validation, trust anchor và CRL.
- [JEP 524: PEM Encodings of Cryptographic Objects (Second Preview)](https://openjdk.org/jeps/524): API PEM preview trong Java 26.
- [PEMDecoder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMDecoder.html) và [PEMEncoder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMEncoder.html): API preview lần thứ hai và các loại dữ liệu hỗ trợ.
- [JEP 538: PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538): thay đổi API trong Java 27.
- [PEMDecoder — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html), [PEM — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEM.html) và [BinaryEncodable — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html): kiểu dữ liệu và cách decode trong preview lần thứ ba.
- [JEP 542: PEM Encodings of Cryptographic Objects](https://openjdk.org/jeps/542): final hóa API PEM trong JDK 28.
- [CertificateFactory — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertificateFactory.html): parse X.509 certificate, bundle và CRL bằng API ổn định.
- [PKIXParameters — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXParameters.html): cấu hình trust anchors, thời điểm và chính sách xác minh path.
- [PKIXRevocationChecker — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): cấu hình kiểm tra trạng thái thu hồi bằng OCSP và CRL.
- [JCA Reference Guide — Java SE 27](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html): kiến trúc provider, certificate factory và API mật mã Java hiện hành.
- [Oracle Java Downloads](https://www.oracle.com/java/technologies/downloads/) và [JDK Release Timeline](https://ops.java/releases/?lang=en): kiểm tra JDK GA, LTS và Early Access theo thời điểm nâng cấp.
