# CertificateFactory

Trong Java Cryptography Architecture (JCA), **java.security.cert.CertificateFactory** là API dùng để đọc và chuyển dữ liệu chứng thư hoặc CRL đã được mã hóa thành các đối tượng Java có cấu trúc. Với kiểu **X.509**, ứng dụng có thể phân tích chứng thư số, tập chứng thư, certificate path và danh sách thu hồi chứng thư (CRL).

CertificateFactory giúp ứng dụng truy cập các trường như Subject, Issuer, serial number, thời hạn hiệu lực, Subject Alternative Name, Key Usage và public key. Tuy nhiên, phân tích được một chứng thư không có nghĩa chứng thư đó đáng tin cậy. Ứng dụng vẫn cần kiểm tra đường dẫn chứng thư, trust anchor, mục đích sử dụng, thời hạn, chính sách thu hồi và danh tính mà hệ thống mong đợi.

Bài học đặt CertificateFactory trong JCA, hướng dẫn đọc X.509/CRL, xử lý DER và PEM, tạo CertPath, xác minh PKIX, kiểm soát dữ liệu đầu vào và tích hợp với KeyStore hoặc TLS. Các ví dụ dùng Java 17.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc cần có khả năng:

- Giải thích vai trò của CertificateFactory trong JCA và phân biệt nó với KeyStore, Certificate, CertPathValidator và CertPathBuilder.
- Tạo instance bằng CertificateFactory.getInstance và hiểu cách provider cung cấp implementation.
- Đọc một X.509 certificate từ DER hoặc PEM đã giải mã.
- Đọc nhiều certificate và nhận biết thứ tự, tính đầy đủ của certificate chain.
- Phân tích CRL và hiểu các giới hạn của thao tác parse.
- Tạo hoặc đọc CertPath từ danh sách chứng thư và các encoding được hỗ trợ.
- Xác minh certificate path theo PKIX với trust anchor phù hợp.
- Phân biệt parsing, path validation, hostname verification và revocation checking.
- Xử lý certificate input không tin cậy với giới hạn kích thước và kiểm soát lỗi.
- Thiết kế kiểm thử cho chứng thư sai định dạng, sai chain, hết hạn, sai mục đích và CRL không hợp lệ.

Phạm vi chính là API CertificateFactory và các API X.509 liên quan. Bài không hướng dẫn phát hành chứng thư CA, tạo CSR hoặc thiết kế toàn bộ PKI. Những hoạt động đó có API và quy trình riêng.

## 2. CertificateFactory dùng để làm gì?

CertificateFactory chuyển dữ liệu đã mã hóa thành đối tượng đại diện cho cấu trúc chứng thư hoặc CRL. Với X.509, các đối tượng phổ biến gồm:

| Đầu vào | API | Đối tượng kết quả |
|---|---|---|
| Một certificate | generateCertificate(InputStream) | Certificate, thường là X509Certificate |
| Một tập certificate | generateCertificates(InputStream) | Collection of Certificate |
| Một CRL | generateCRL(InputStream) | CRL, thường là X509CRL |
| Một tập CRL | generateCRLs(InputStream) | Collection of CRL |
| Certificate path đã mã hóa | generateCertPath(InputStream, encoding) | CertPath |
| Danh sách certificate trong bộ nhớ | generateCertPath(List) | CertPath |

CertificateFactory không tạo key pair, không ký chứng thư, không cấp chứng thư và không quyết định trust policy. Nó đọc cấu trúc dữ liệu được cung cấp.

Ví dụ, khi đọc một certificate, ứng dụng có thể lấy:

- Subject và Issuer.
- Serial number.
- NotBefore và NotAfter.
- Subject Alternative Name.
- Key Usage và Extended Key Usage.
- Public key.
- Certificate signature algorithm.
- Extension và critical extension.

Các trường này là dữ liệu được chứng thư khai báo. Ứng dụng cần xác minh chữ ký, đường dẫn và chính sách trước khi dùng chúng làm căn cứ tin cậy.

## 3. CertificateFactory nằm ở đâu trong JCA?

JCA cung cấp API thống nhất cho nhiều dịch vụ mật mã. Ứng dụng gọi CertificateFactory; provider thực hiện việc phân tích dữ liệu theo loại certificate/CRL và encoding được hỗ trợ.

~~~~mermaid
flowchart TB
    APP[Ứng dụng Java]
    API[CertificateFactory]
    SPI[CertificateFactorySpi]
    P[Provider X.509]
    CERT[X509Certificate]
    CRL[X509CRL]
    PATH[CertPath]
    APP --> API
    API --> SPI
    SPI --> P
    P --> CERT
    P --> CRL
    P --> PATH
~~~~

Các thành phần liên quan:

| Thành phần | Vai trò |
|---|---|
| CertificateFactory | API facade để parse certificate, CRL và CertPath |
| CertificateFactorySpi | Hợp đồng triển khai dịch vụ của provider |
| Provider | Đăng ký thuật toán/loại certificate và implementation |
| Certificate | Lớp trừu tượng đại diện chứng thư |
| X509Certificate | API truy cập cấu trúc chứng thư X.509 |
| CRL | Lớp trừu tượng đại diện danh sách thu hồi |
| X509CRL | API truy cập CRL X.509 |
| CertPath | Một đường dẫn gồm các certificate có thứ tự |
| CertPathValidator | Xác minh đường dẫn theo policy, thường là PKIX |
| CertPathBuilder | Tìm đường dẫn từ target certificate tới trust anchor |
| TrustAnchor | Điểm tin cậy gốc do ứng dụng cấu hình |

CertificateFactory và CertPathValidator giải quyết hai công việc khác nhau. Factory đọc dữ liệu và tạo object. Validator kiểm tra đường dẫn chứng thư dựa trên trust anchor và các tham số PKIX.

## 4. Tạo CertificateFactory

Đối với X.509, tên loại phổ biến là **X.509**:

~~~~java
import java.security.cert.CertificateFactory;

public class CertificateFactorySetup {
    public static void main(String[] args) throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        System.out.println("Type: " + factory.getType());
        System.out.println("Provider: " + factory.getProvider().getName());
    }
}
~~~~

JCA tìm provider hỗ trợ loại certificate được yêu cầu. Nếu cần cố định provider, có thể dùng overload nhận tên hoặc đối tượng Provider, nhưng chỉ nên làm vậy khi hệ thống có yêu cầu triển khai rõ ràng và đã kiểm tra provider đó.

Không giả định mọi JDK hoặc môi trường runtime đều có cùng danh sách provider. Provider bên thứ ba, HSM hoặc thư viện bảo mật có thể bổ sung implementation. Kiểm tra provider trong môi trường triển khai thực tế.

### Liệt kê provider hỗ trợ CertificateFactory

~~~~java
import java.security.Provider;
import java.security.Security;

public class CertificateFactoryProviders {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            for (Provider.Service service : provider.getServices()) {
                if ("CertificateFactory".equalsIgnoreCase(service.getType())) {
                    System.out.println(
                            provider.getName() + ": " + service.getAlgorithm()
                    );
                }
            }
        }
    }
}
~~~~

Đối với X.509, provider phổ biến của JDK thường đăng ký service tên X.509. Nếu service không có, getInstance sẽ ném NoSuchAlgorithmException.

## 5. Đọc một X.509 certificate

CertificateFactory nhận InputStream chứa dữ liệu certificate được mã hóa. Ví dụ phổ biến là certificate dạng DER.

~~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public class ReadX509Certificate {
    public static X509Certificate read(Path path) throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        try (InputStream input = Files.newInputStream(path)) {
            Certificate certificate = factory.generateCertificate(input);

            if (!(certificate instanceof X509Certificate x509)) {
                throw new IllegalArgumentException(
                        "Input is not an X.509 certificate"
                );
            }

            return x509;
        }
    }

    public static void main(String[] args) throws Exception {
        X509Certificate certificate =
                read(Path.of("server.der"));

        System.out.println("Subject: "
                + certificate.getSubjectX500Principal());
        System.out.println("Issuer: "
                + certificate.getIssuerX500Principal());
        System.out.println("Serial: "
                + certificate.getSerialNumber());
        System.out.println("Valid from: "
                + certificate.getNotBefore());
        System.out.println("Valid until: "
                + certificate.getNotAfter());
        System.out.println("Public key algorithm: "
                + certificate.getPublicKey().getAlgorithm());
    }
}
~~~~

Một số lưu ý:

- Dùng try-with-resources để đóng stream.
- Kiểm tra kiểu đối tượng trả về nếu code cần X509Certificate.
- Không coi Subject hoặc Issuer là danh tính đã xác thực trước khi validate path.
- Không sử dụng public key lấy từ certificate chưa được xác minh để xác thực một thông điệp quan trọng.
- CertificateFactory chỉ phân tích dữ liệu; nó không kiểm tra certificate còn hạn hoặc có được CA tin cậy ký hay không.

### Kiểm tra thời hạn

X509Certificate cung cấp checkValidity:

~~~~java
import java.security.cert.X509Certificate;
import java.util.Date;

public class CertificateValidityCheck {
    public static void checkCurrentValidity(
            X509Certificate certificate
    ) throws Exception {
        certificate.checkValidity(new Date());
    }
}
~~~~

checkValidity chỉ kiểm tra ngày hiện tại nằm trong khoảng NotBefore và NotAfter. Nó không xác minh trust chain, hostname, revocation, Key Usage hoặc Extended Key Usage.

Nếu cần kiểm tra ở một thời điểm lịch sử, truyền Date tương ứng. Việc đánh giá chữ ký lịch sử còn cần timestamp tin cậy và policy xác minh tại thời điểm ký.

## 6. DER và PEM

Certificate X.509 thường được lưu ở hai dạng phổ biến:

| Dạng | Mô tả |
|---|---|
| DER | Encoding nhị phân ASN.1 Distinguished Encoding Rules |
| PEM | Văn bản Base64 bao quanh bởi marker BEGIN/END |

Ví dụ PEM:

~~~~text
-----BEGIN CERTIFICATE-----
MIID...
...phần Base64 của chứng thư...
-----END CERTIFICATE-----
~~~~

PEM là lớp bao văn bản chứa dữ liệu DER đã Base64. CertificateFactory làm việc với encoding certificate mà provider hỗ trợ. Để có tính liên thông rõ ràng, ứng dụng có thể loại bỏ marker PEM, giải mã Base64 thành DER rồi truyền DER bytes vào factory.

Không giả định mọi provider chấp nhận mọi biến thể PEM, nhiều PEM block, comment hoặc định dạng OpenSSL mở rộng theo cùng một cách. Nếu ứng dụng cần hỗ trợ các định dạng này, hãy định nghĩa grammar đầu vào và xử lý rõ ràng.

### Giải mã một PEM certificate

Ví dụ sau chỉ nhận đúng một PEM certificate, giới hạn kích thước file và giải mã Base64 tường minh:

~~~~java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Base64;

public class ReadPemCertificate {
    private static final long MAX_PEM_BYTES = 1024 * 1024;

    public static X509Certificate read(Path path) throws Exception {
        long size = Files.size(path);
        if (size <= 0 || size > MAX_PEM_BYTES) {
            throw new IllegalArgumentException("PEM size is outside policy");
        }

        String pem = Files.readString(path, StandardCharsets.US_ASCII);
        String begin = "-----BEGIN CERTIFICATE-----";
        String end = "-----END CERTIFICATE-----";

        String trimmed = pem.trim();
        if (!trimmed.startsWith(begin) || !trimmed.endsWith(end)) {
            throw new IllegalArgumentException("Expected one PEM certificate");
        }

        String base64 = trimmed.substring(
                begin.length(),
                trimmed.length() - end.length()
        ).replaceAll("\\s", "");

        byte[] der = Base64.getDecoder().decode(base64);

        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        try (ByteArrayInputStream input =
                     new ByteArrayInputStream(der)) {
            return (X509Certificate) factory.generateCertificate(input);
        }
    }
}
~~~~

Ví dụ cố ý chỉ nhận một block và không hỗ trợ PEM có comment hoặc nhiều certificate. Nếu cần đọc bundle, hãy tách từng block theo parser có giới hạn, xác nhận marker đúng cặp, giải mã riêng từng block và xử lý từng certificate.

Không dùng Base64 decoder kiểu MIME như một cách thay thế kiểm tra cấu trúc PEM nếu policy yêu cầu từ chối ký tự không hợp lệ. MIME decoder có thể bỏ qua một số ký tự ngoài bảng Base64; parser cần quy tắc chấp nhận rõ ràng.

## 7. Đọc nhiều certificate

Một file bundle có thể chứa nhiều certificate, ví dụ leaf certificate và intermediate CA. Có thể dùng generateCertificates:

~~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class ReadCertificateBundle {
    public static List<X509Certificate> read(Path path) throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        try (InputStream input = Files.newInputStream(path)) {
            Collection<? extends Certificate> parsed =
                    factory.generateCertificates(input);

            List<X509Certificate> certificates = new ArrayList<>();

            for (Certificate certificate : parsed) {
                if (!(certificate instanceof X509Certificate x509)) {
                    throw new IllegalArgumentException(
                            "Bundle contains a non-X.509 certificate"
                    );
                }
                certificates.add(x509);
            }

            return List.copyOf(certificates);
        }
    }
}
~~~~

generateCertificates đọc một collection theo các encoding collection mà provider hỗ trợ. Một số định dạng có thể là PKCS#7 certificate collection; hành vi đối với bundle PEM nối tiếp cần được kiểm tra trên provider thực tế. Nếu cần hỗ trợ một file PEM chứa nhiều block, parser có thể tách từng block và gọi generateCertificate cho từng DER object.

**Không coi thứ tự certificate trong một collection là đường dẫn tin cậy.** PKCS#7 certificate set có thể không có thứ tự chain. Ứng dụng cần xây dựng hoặc tìm CertPath bằng issuer/subject, chữ ký và các ràng buộc PKIX, sau đó xác minh với trust anchor.

Không lấy certificate đầu tiên trong bundle làm leaf một cách mù quáng. Xác định target certificate theo metadata hoặc selector, rồi xây dựng path.

## 8. Phân tích thông tin X.509

Sau khi parse thành X509Certificate, ứng dụng có thể đọc các extension phục vụ policy.

~~~~java
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;

public class InspectX509Certificate {
    public static void inspect(X509Certificate certificate)
            throws Exception {
        System.out.println("Subject: "
                + certificate.getSubjectX500Principal());
        System.out.println("Issuer: "
                + certificate.getIssuerX500Principal());
        System.out.println("Serial: "
                + certificate.getSerialNumber());
        System.out.println("Sig algorithm: "
                + certificate.getSigAlgName());
        System.out.println("Public key: "
                + certificate.getPublicKey().getAlgorithm());
        System.out.println("Basic constraints: "
                + certificate.getBasicConstraints());

        boolean[] keyUsage = certificate.getKeyUsage();
        if (keyUsage != null) {
            System.out.println("Key usage: "
                    + java.util.Arrays.toString(keyUsage));
        }

        List<String> extendedKeyUsage =
                certificate.getExtendedKeyUsage();
        System.out.println("Extended key usage: " + extendedKeyUsage);

        Collection<List<?>> sans =
                certificate.getSubjectAlternativeNames();
        System.out.println("Subject alternative names: " + sans);
    }
}
~~~~

Một số điểm cần hiểu:

- getBasicConstraints trả về giá trị âm nếu chứng thư không phải CA; giá trị không âm biểu thị CA và giới hạn path length nếu có.
- getKeyUsage trả về mảng bit theo thứ tự định nghĩa trong X.509. Không tự diễn giải bằng index tùy ý mà không đối chiếu API/specification.
- getExtendedKeyUsage có thể trả null nếu extension không tồn tại.
- getSubjectAlternativeNames có thể trả null nếu không có SAN.
- Critical extension không được ứng dụng bỏ qua nếu extension đó ảnh hưởng tới policy mà ứng dụng thực thi.

Không dùng Common Name để thay thế SAN trong các chính sách hostname hiện đại. Hostname verification nên dùng API verifier chuyên dụng theo chuẩn và theo giao thức.

## 9. CertificateFactory và CertPath

CertPath là một chuỗi certificate có thứ tự được dùng để xác minh từ target certificate tới trust anchor. Với đường dẫn PKIX, certificate của target thường đứng đầu danh sách, tiếp theo là issuer certificate; trust anchor không nằm trong CertPath.

Ví dụ đường dẫn:

~~~~text
Leaf certificate
    Issuer: Intermediate CA
        Issuer: Root CA (trust anchor)
~~~~

Một CertPath có thể được tạo từ danh sách certificate đã có:

~~~~java
import java.security.cert.CertPath;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.util.List;

public class CreateCertPath {
    public static CertPath create(List<? extends Certificate> chain)
            throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        return factory.generateCertPath(chain);
    }
}
~~~~

Danh sách phải được sắp theo đúng thứ tự path mà validator mong đợi. Không đưa trust anchor vào danh sách certificate path như một certificate trung gian thông thường. Nếu có nhiều candidate issuer hoặc chain không đầy đủ, dùng CertPathBuilder để tìm đường dẫn phù hợp.

### CertPath khác certificate collection

| Đặc điểm | Certificate collection | CertPath |
|---|---|---|
| Thứ tự | Có thể không mang ý nghĩa chain | Có thứ tự theo đường dẫn |
| Mục đích | Tập hợp certificate được đóng gói cùng nhau | Đường dẫn cần được validator kiểm tra |
| Trust anchor | Có thể có mặt như một certificate trong collection | Thường được cấu hình riêng trong PKIXParameters |
| API | generateCertificates | generateCertPath |
| Validation | Không tự xác minh chain | Được truyền cho CertPathValidator |

Parse được CertPath cũng chưa chứng minh path hợp lệ. Validator vẫn phải kiểm tra chữ ký, thời hạn, constraints, policy và revocation theo cấu hình.

## 10. Đọc CertPath từ encoding

CertificateFactory có thể đọc CertPath từ encoding được provider hỗ trợ. X.509 thường có các encoding như PkiPath và PKCS7.

~~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPath;
import java.security.cert.CertificateFactory;
import java.util.Iterator;

public class ReadEncodedCertPath {
    public static void listEncodings() throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        Iterator<String> encodings = factory.getCertPathEncodings();
        while (encodings.hasNext()) {
            System.out.println(encodings.next());
        }
    }

    public static CertPath read(Path path, String encoding)
            throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        try (InputStream input = Files.newInputStream(path)) {
            return factory.generateCertPath(input, encoding);
        }
    }
}
~~~~

Danh sách encoding được trả về theo provider. Không hard-code encoding nếu hệ thống cần chạy trên nhiều provider mà chưa xác nhận hỗ trợ. Kiểm tra encoding trước khi sử dụng và bắt CertificateException khi dữ liệu không phù hợp.

PKCS#7 certificate container có thể chứa một tập certificate, không nhất thiết là một chain đã được sắp thứ tự. PkiPath có cấu trúc đường dẫn; ứng dụng vẫn phải validate path theo trust anchor.

## 11. Parsing không phải là validation

Đây là ranh giới bảo mật quan trọng nhất khi sử dụng CertificateFactory.

~~~~mermaid
flowchart TD
    A[Bytes certificate không tin cậy]
    B[CertificateFactory parse]
    C[X509Certificate object]
    D[Kiểm tra certificate path]
    E[Kiểm tra trust anchor và policy]
    F[Hostname / identity verification]
    G[Revocation và thời hạn]
    H[Chấp nhận theo policy]
    X[Từ chối]
    A --> B --> C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    D --> X
    E --> X
    F --> X
    G --> X
~~~~

Parsing chỉ kiểm tra dữ liệu có thể được đọc theo cấu trúc certificate mà provider hiểu hay không. Nó không trả lời các câu hỏi:

- Chứng thư có được CA tin cậy ký không?
- Issuer certificate có đúng là issuer của certificate hiện tại không?
- Chứng thư có còn trong thời hạn không?
- CA có được phép phát hành loại certificate này không?
- Basic Constraints và path length có hợp lệ không?
- Key Usage và Extended Key Usage có đúng mục đích không?
- Certificate có bị thu hồi không?
- Subject/SAN có đại diện cho danh tính mà ứng dụng mong đợi không?

Không đưa certificate chưa validate vào trust store hoặc dùng public key của nó để xác minh chữ ký quan trọng.

## 12. Xác minh certificate path bằng PKIX

Java cung cấp CertPathValidator để xác minh CertPath theo một thuật toán validation. Với X.509, thuật toán phổ biến là PKIX.

Các thành phần chính:

- **CertPath:** đường dẫn certificate cần xác minh.
- **TrustAnchor:** CA hoặc public key được ứng dụng tin cậy độc lập.
- **PKIXParameters:** tham số validation, trust anchors, date, policy và revocation.
- **CertPathValidator:** thực hiện kiểm tra đường dẫn.
- **PKIXCertPathValidatorResult:** kết quả, gồm trust anchor và policy tree nếu có.

Trust anchor là cấu hình tin cậy của ứng dụng. Không tự lấy một root certificate từ bundle do bên gửi cung cấp rồi coi nó là trust anchor. Nếu bên gửi có thể tự chọn root, họ có thể tự tạo một CA và chứng thư hợp lệ theo CA đó.

### Ví dụ xác minh path

Ví dụ sau giả định ứng dụng đã có leaf certificate, intermediate certificate và root certificate lấy từ nguồn tin cậy độc lập. Root certificate được dùng làm trust anchor. Certificate path chỉ chứa leaf và intermediate.

~~~~java
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Date;
import java.util.List;
import java.util.Set;

public class ValidateCertificatePath {
    public static void validate(
            X509Certificate leaf,
            X509Certificate intermediate,
            X509Certificate trustedRoot
    ) throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        CertPath path = factory.generateCertPath(
                List.of(leaf, intermediate)
        );

        TrustAnchor trustAnchor = new TrustAnchor(trustedRoot, null);

        PKIXParameters parameters =
                new PKIXParameters(Set.of(trustAnchor));

        parameters.setDate(new Date());

        // Revocation is configured separately in the production example.
        parameters.setRevocationEnabled(false);

        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");

        validator.validate(path, parameters);
    }
}
~~~~

Ví dụ này minh họa path validation cho chữ ký certificate, thời hạn và các ràng buộc PKIX cơ bản. Nó chủ động tắt revocation checking để không phụ thuộc mạng hoặc nguồn CRL/OCSP trong ví dụ ngắn. Không sao chép thiết lập này cho production nếu policy yêu cầu kiểm tra thu hồi.

Sau khi path validation thành công, ứng dụng vẫn cần kiểm tra hostname hoặc service identity theo protocol. PKIX path validation không tự xác minh rằng certificate đại diện cho hostname trong URL.

### Thời điểm xác minh

PKIXParameters cho phép đặt thời điểm đánh giá:

~~~~java
parameters.setDate(java.util.Date.from(
        java.time.Instant.parse("2026-11-28T00:00:00Z")
));
~~~~

Dùng thời điểm hiện tại cho kết nối mới. Với chữ ký hoặc tài liệu lịch sử, thời điểm đánh giá có thể khác và cần bằng chứng timestamp tin cậy, trạng thái certificate tại thời điểm liên quan và policy lưu trữ dài hạn. Chỉ đặt Date lùi về quá khứ không tạo ra bằng chứng rằng chữ ký đã tồn tại tại thời điểm đó.

## 13. Xây dựng CertPath bằng CertPathBuilder

Khi có nhiều intermediate certificate hoặc nhiều candidate issuer, ứng dụng có thể dùng CertPathBuilder để tìm đường dẫn từ target certificate tới một trust anchor.

CertPathBuilder không tự biến mọi certificate trong bundle thành đáng tin cậy. Nó tìm một đường dẫn đáp ứng trust anchor và các tham số PKIX đã cấu hình.

~~~~java
import java.security.cert.CertPathBuilder;
import java.security.cert.CertStore;
import java.security.cert.CollectionCertStoreParameters;
import java.security.cert.PKIXBuilderParameters;
import java.security.cert.PKIXCertPathBuilderResult;
import java.security.cert.TrustAnchor;
import java.security.cert.X509CertSelector;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.Set;

public class BuildCertificatePath {
    public static PKIXCertPathBuilderResult build(
            X509Certificate target,
            X509Certificate trustedRoot,
            Collection<X509Certificate> candidateIntermediates
    ) throws Exception {
        X509CertSelector selector = new X509CertSelector();
        selector.setCertificate(target);

        PKIXBuilderParameters parameters =
                new PKIXBuilderParameters(
                        Set.of(new TrustAnchor(trustedRoot, null)),
                        selector
                );

        CertStore store = CertStore.getInstance(
                "Collection",
                new CollectionCertStoreParameters(candidateIntermediates)
        );

        parameters.addCertStore(store);

        CertPathBuilder builder = CertPathBuilder.getInstance("PKIX");
        return (PKIXCertPathBuilderResult) builder.build(parameters);
    }
}
~~~~

Trong production, cần cấu hình rõ revocation policy, thời điểm, policy constraints, maximum path length và nguồn certificate store. Nếu builder không tìm được path, kiểm tra candidate issuer, AKI/SKI, chữ ký, CA constraints, name constraints và trust anchor.

Không chấp nhận certificate chỉ vì Subject của issuer giống Issuer của target. Tên trùng nhau không chứng minh chữ ký hợp lệ hoặc certificate là đúng issuer.

## 14. Đọc CRL bằng CertificateFactory

CRL (Certificate Revocation List) là danh sách certificate bị CA thu hồi. X.509 CRL được đọc qua generateCRL:

~~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509CRL;

public class ReadX509Crl {
    public static X509CRL read(Path path) throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        try (InputStream input = Files.newInputStream(path)) {
            return (X509CRL) factory.generateCRL(input);
        }
    }

    public static void main(String[] args) throws Exception {
        X509CRL crl = read(Path.of("issuer.crl"));

        System.out.println("Issuer: " + crl.getIssuerX500Principal());
        System.out.println("This update: " + crl.getThisUpdate());
        System.out.println("Next update: " + crl.getNextUpdate());
        System.out.println("Revoked entries: "
                + (crl.getRevokedCertificates() == null
                    ? 0
                    : crl.getRevokedCertificates().size()));
    }
}
~~~~

CRL cũng là dữ liệu đầu vào có thể bị giả mạo. Parse thành công không chứng minh CRL do đúng CA phát hành. Cần xác minh chữ ký CRL bằng public key issuer phù hợp, kiểm tra issuer name, thời gian thisUpdate/nextUpdate, scope, CRL number, delta CRL và các extension liên quan.

### Đọc nhiều CRL

~~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CRL;
import java.security.cert.CertificateFactory;
import java.util.Collection;

public class ReadCrlCollection {
    public static Collection<? extends CRL> read(Path path)
            throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        try (InputStream input = Files.newInputStream(path)) {
            return factory.generateCRLs(input);
        }
    }
}
~~~~

Không chọn CRL đầu tiên trong collection rồi áp dụng cho mọi certificate. CRL có thể thuộc các issuer hoặc scope khác nhau. Cần xác định issuer, distribution point, issuing distribution point và phạm vi certificate mà CRL bao phủ.

## 15. Các trường quan trọng của CRL

| Trường | Ý nghĩa |
|---|---|
| Issuer | CA phát hành CRL |
| This Update | Thời điểm CRL có hiệu lực cập nhật |
| Next Update | Thời điểm dự kiến có CRL mới |
| Revoked Certificates | Các serial number bị thu hồi và metadata liên quan |
| CRL Number | Số thứ tự CRL |
| Authority Key Identifier | Gợi ý định danh khóa CA phát hành |
| Issuing Distribution Point | Xác định phạm vi CRL |
| Delta CRL Indicator | Cho biết CRL là delta CRL |
| Signature Algorithm | Thuật toán ký CRL |

CRL không phải chỉ là một danh sách serial number. Nếu chỉ tìm serial number trong một file CRL bất kỳ mà không kiểm tra issuer và scope, ứng dụng có thể kết luận sai trạng thái thu hồi.

Một CRL còn có thể không chứa certificate đã bị thu hồi vì CRL đó không bao phủ loại certificate hoặc distribution point tương ứng. Không thấy serial number trong một CRL không đủ để kết luận certificate còn hợp lệ.

## 16. Revocation checking với PKIXRevocationChecker

Để kiểm tra thu hồi trong path validation, Java cung cấp PKIXRevocationChecker. Checker có thể sử dụng CRL, OCSP hoặc cấu hình ưu tiên theo provider và môi trường.

~~~~java
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXParameters;
import java.security.cert.PKIXRevocationChecker;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.EnumSet;
import java.util.Set;

public class ValidateWithRevocation {
    public static void validate(
            CertPath path,
            X509Certificate trustedRoot
    ) throws Exception {
        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");

        PKIXParameters parameters =
                new PKIXParameters(
                        Set.of(new TrustAnchor(trustedRoot, null))
                );

        parameters.setRevocationEnabled(true);

        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();

        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS
        ));

        parameters.addCertPathChecker(checker);

        validator.validate(path, parameters);
    }
}
~~~~

Ví dụ yêu cầu PKIX thực hiện revocation checking và ưu tiên CRL. Việc lấy CRL/OCSP, cache, network access và fallback phụ thuộc provider, cấu hình hệ thống và dữ liệu certificate. Trong production, cần kiểm thử rõ trường hợp revoked, unknown, stale response, responder unavailable và certificate không có thông tin revocation.

Không bật SOFT_FAIL chỉ để ứng dụng tiếp tục chạy khi nguồn revocation không truy cập được. Soft fail có thể biến tình trạng không xác định thành chấp nhận; chỉ sử dụng khi threat model và policy cho phép, có audit và giới hạn cụ thể.

## 17. CertificateFactory và KeyStore

KeyStore lưu hoặc tham chiếu private key, secret key và certificate entry tùy loại keystore/provider. CertificateFactory parse certificate bytes. Hai API có thể được dùng cùng nhau nhưng không thay thế nhau.

Ví dụ, có thể parse một certificate từ file rồi thêm vào trust store sau khi xác minh nguồn gốc và quyết định trust:

~~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;

public class ImportCertificateToTrustStore {
    public static void importCertificate(
            Path certificateFile,
            Path trustStoreFile,
            char[] password,
            String alias
    ) throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        Certificate certificate;
        try (InputStream input = Files.newInputStream(certificateFile)) {
            certificate = factory.generateCertificate(input);
        }

        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        if (Files.exists(trustStoreFile)) {
            try (InputStream input = Files.newInputStream(trustStoreFile)) {
                trustStore.load(input, password);
            }
        } else {
            trustStore.load(null, password);
        }

        // Trust decision must be made before adding this entry.
        trustStore.setCertificateEntry(alias, certificate);

        try (var output = Files.newOutputStream(trustStoreFile)) {
            trustStore.store(output, password);
        }
    }
}
~~~~

Đoạn code chỉ minh họa thao tác lưu certificate entry. Nó không chứng minh certificate đáng tin cậy. Không import certificate do người dùng hoặc máy chủ tùy ý cung cấp vào trust store mà không có quy trình xác minh, phê duyệt và quản lý thay đổi.

Trust store chứa trust anchors hoặc certificate được ứng dụng tin cậy theo cấu hình. Một file certificate parse thành công không tự có quyền trở thành trust anchor.

## 18. CertificateFactory trong TLS và hostname verification

Trong TLS, peer gửi certificate chain để client xác minh. TLS provider thường tự dùng các thành phần X.509/PKIX để parse và validate certificate. Ứng dụng hiếm khi cần tự parse certificate từ socket TLS để quyết định trust.

Luồng xác minh HTTPS thường có các phần:

1. TLS provider parse certificate chain.
2. Xây dựng và validate certificate path tới trust anchor.
3. Kiểm tra thời hạn, constraints, key usage và policy.
4. Kiểm tra revocation theo policy.
5. Kiểm tra hostname/service identity.
6. Hoàn tất handshake nếu các điều kiện cần thiết đều đạt.

CertificateFactory có thể hữu ích để đọc certificate ngoài TLS, ví dụ certificate được tải từ endpoint quản trị, registry, file cấu hình hoặc bundle. Nhưng khi ứng dụng tự xây dựng trust logic, cần đảm bảo nó tương đương các kiểm soát mà TLS provider thường thực hiện.

Hostname verification là một bước riêng. PKIX path hợp lệ không có nghĩa certificate đại diện đúng hostname trong URL. Ngược lại, Subject hoặc SAN đúng hostname không làm certificate trở nên đáng tin cậy nếu chain không hợp lệ.

## 19. Xử lý certificate input không tin cậy

Certificate và CRL có thể đến từ file upload, API, message queue, repository hoặc endpoint bên ngoài. Parser xử lý ASN.1 có thể tiêu thụ CPU và bộ nhớ theo kích thước, cấu trúc và độ phức tạp đầu vào.

Các kiểm soát cần có:

- Giới hạn kích thước file và tổng kích thước bundle trước khi đọc toàn bộ vào memory.
- Giới hạn số certificate/CRL trong collection.
- Đặt timeout và giới hạn tài nguyên cho pipeline xử lý dữ liệu bên ngoài.
- Không ghi toàn bộ certificate hoặc private metadata nhạy cảm vào log.
- Bắt và phân loại CertificateException, CRLException, IOException và lỗi validation.
- Không coi lỗi parse là trạng thái “certificate không bị thu hồi” hoặc “certificate không tồn tại”.
- Không tự động import certificate chưa xác minh vào trust store.
- Giữ nguyên bytes gốc hoặc hash để audit khi có yêu cầu điều tra.

Không parse dữ liệu có kích thước không giới hạn bằng readAllBytes trong request thread. Với file lớn, cần kiểm tra size trước, giới hạn stream và kiểm soát tổng bộ nhớ.

### Kiểm tra giới hạn trước khi đọc

~~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class CertificateInputLimit {
    private static final long MAX_CERTIFICATE_BYTES = 1024 * 1024;

    public static void check(Path path) throws Exception {
        long size = Files.size(path);

        if (size <= 0 || size > MAX_CERTIFICATE_BYTES) {
            throw new IllegalArgumentException(
                    "Certificate input size is outside policy"
            );
        }
    }
}
~~~~

Giới hạn 1 MiB trong ví dụ là giá trị minh họa, không phải giới hạn phổ quát cho mọi certificate hoặc CRL. Hãy đặt giới hạn theo loại dữ liệu, CA policy và kích thước hợp lệ trong môi trường.

## 20. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| CertificateException khi parse | Bytes sai định dạng, PEM chưa decode hoặc dữ liệu bị cắt | Kiểm tra marker, Base64, DER và nguồn file |
| NoSuchAlgorithmException | Provider không có X.509 CertificateFactory | Kiểm tra provider và runtime |
| ClassCastException | Đầu vào không phải X509Certificate như code giả định | Kiểm tra certificate type và provider |
| generateCertificate chỉ đọc một certificate | Đầu vào là bundle nhiều certificate | Dùng generateCertificates hoặc parse từng PEM block |
| Chain validation thất bại | Thiếu intermediate, sai issuer hoặc sai thứ tự | Kiểm tra candidate issuer, AKI/SKI và path |
| PKIX path building failed | Trust anchor sai hoặc không có đường dẫn hợp lệ | Kiểm tra trust store, chain, constraints và thời hạn |
| CertificateExpiredException | Certificate hết hạn hoặc chưa có hiệu lực | Kiểm tra NotBefore/NotAfter và clock |
| CertificateRevokedException | Certificate bị thu hồi | Dừng sử dụng certificate theo policy và xử lý rotation |
| CRLException | CRL encoding không hợp lệ hoặc provider không parse được | Kiểm tra DER/PEM và CRL source |
| CRL parse thành công nhưng revocation không đúng | CRL sai issuer, stale hoặc không bao phủ certificate | Kiểm tra issuer, scope, update time, CRL number và distribution point |
| Hostname mismatch dù PKIX pass | SAN không chứa reference hostname | Kiểm tra hostname verification riêng |
| CertificateFactory đọc được nhưng TLS từ chối | Parse không đồng nghĩa trust validation | So sánh trust store, EKU, revocation, hostname và TLS policy |

### Quy trình điều tra

1. Xác định chính xác nguồn và encoding của certificate/CRL.
2. Ghi nhận kích thước, số lượng block và hash của bytes đầu vào.
3. Parse bằng CertificateFactory X.509.
4. Kiểm tra Subject, Issuer, serial, SAN, Basic Constraints, Key Usage và thời hạn.
5. Xác định issuer candidate và trust anchor từ nguồn tin cậy.
6. Tạo hoặc xây dựng CertPath.
7. Validate bằng PKIX với thời điểm và revocation policy phù hợp.
8. Kiểm tra hostname/service identity ở lớp protocol.
9. Kiểm tra provider, JDK version và trust store của môi trường thực tế.
10. Lưu kết quả và nguồn dữ liệu phục vụ audit mà không để lộ bí mật.

Không sửa lỗi bằng cách thêm certificate lạ vào trust store hoặc tắt revocation/hostname checking. Trước hết phải xác định lỗi nằm ở parsing, chain, trust, revocation hay identity.

## 21. Kiểm thử CertificateFactory

Một bộ test cần bao phủ các trường hợp hợp lệ và không hợp lệ:

| Ca kiểm thử | Đầu vào | Kết quả mong đợi |
|---|---|---|
| DER certificate hợp lệ | Một X.509 certificate DER | Parse thành công |
| PEM certificate hợp lệ | Một PEM block đúng cấu trúc | Decode và parse thành công |
| Base64 sai | PEM có ký tự không hợp lệ | Từ chối |
| DER bị cắt | Bytes thiếu phần cuối | Parse thất bại |
| Input rỗng | Stream 0 byte | Từ chối |
| File quá lớn | Vượt giới hạn ứng dụng | Từ chối trước khi parse |
| Nhiều certificate | Bundle có leaf và intermediate | Parse collection theo policy |
| Bundle sai block | PEM thiếu END marker | Từ chối |
| Non-X.509 object | Provider trả loại khác | Từ chối theo type policy |
| CertPath PkiPath | Encoding được provider hỗ trợ | Parse path |
| CertPath encoding lạ | Tên encoding không hỗ trợ | Từ chối |
| CRL DER hợp lệ | CRL đúng định dạng | Parse thành công |
| CRL sai chữ ký | CRL parse được nhưng chữ ký không đúng | Validation từ chối |
| Certificate hết hạn | NotAfter ở quá khứ | PKIX validation thất bại |
| Issuer không tin cậy | Chain không tới trust anchor | PKIX validation thất bại |
| Revoked certificate | Có trạng thái thu hồi hợp lệ | Revocation checking từ chối |
| Hostname sai | Path hợp lệ nhưng SAN sai tên | Hostname verification từ chối |

### Kiểm thử tích hợp

- Kiểm tra trên JDK và provider production.
- Kiểm tra certificate chain có nhiều intermediate.
- Kiểm tra cross-signed CA và nhiều candidate issuer.
- Kiểm tra CRL/OCSP unavailable, stale, revoked và unknown.
- Kiểm tra certificate có critical extension không được ứng dụng hỗ trợ.
- Kiểm tra trust anchor rotation.
- Kiểm tra certificate bundle chứa duplicate hoặc certificate không liên quan.
- Kiểm tra dữ liệu đầu vào lớn, nhiều block và ASN.1 bất thường.
- Kiểm tra hostname verification tách biệt với path validation.

Không dùng certificate test tự ký làm trust anchor trong production. Test trust store phải tách khỏi trust store thực và không được đóng gói nhầm vào artifact phát hành.

## 22. Tình huống thực tế

### Tình huống A: Đọc certificate của API đối tác

Một hệ thống tích hợp tải certificate từ cổng quản trị của đối tác để hiển thị Subject, Issuer, serial number và thời hạn. CertificateFactory giúp parse certificate để trình bày thông tin.

Nếu hệ thống muốn dùng public key đó để xác minh webhook, cần kiểm tra nguồn phân phối key, fingerprint hoặc certificate path, purpose và trạng thái thu hồi trước khi tin cậy. Parse được certificate chỉ phục vụ bước đọc cấu trúc.

### Tình huống B: Bundle chứa nhiều intermediate

Một server gửi leaf certificate và hai intermediate certificate. Ứng dụng parse collection rồi giả định phần tử đầu tiên là leaf và phần tử thứ hai là issuer.

Nếu bundle không có thứ tự, giả định này có thể tạo chain sai. Hệ thống cần xác định target certificate rõ ràng, dùng CertPathBuilder với trust anchor đã cấu hình và để PKIX xác minh đường dẫn.

### Tình huống C: CRL cũ vẫn parse được

Một file CRL có chữ ký hợp lệ nhưng NextUpdate đã qua. CertificateFactory vẫn có thể parse file thành X509CRL vì cấu trúc ASN.1 không nhất thiết bị lỗi.

Ứng dụng phải kiểm tra freshness và policy. Một CRL cũ không thể được coi là bằng chứng hiện tại rằng certificate chưa bị thu hồi.

### Tình huống D: Certificate hợp lệ nhưng sai hostname

Certificate có chain tới root CA được tin cậy, còn hạn và đúng EKU serverAuth. Tuy nhiên SAN chỉ chứa **admin.example.com**, trong khi client truy cập **api.example.com**.

PKIX path validation có thể thành công nhưng hostname verification phải thất bại. CertificateFactory không tự thực hiện phép so khớp hostname.

## 23. Các nguyên tắc an toàn cần giữ

- Dùng CertificateFactory X.509 để parse dữ liệu certificate/CRL.
- Giới hạn kích thước và số lượng object trước khi xử lý.
- Phân biệt DER, PEM và các encoding collection.
- Không giả định bundle certificate đã được sắp thứ tự thành chain.
- Không coi parse thành công là certificate đáng tin cậy.
- Chọn trust anchor từ cấu hình hoặc nguồn quản trị độc lập.
- Dùng CertPathValidator hoặc CertPathBuilder cho PKIX path.
- Cấu hình revocation policy phù hợp và xử lý stale/unknown rõ ràng.
- Xác minh hostname/service identity ở lớp protocol.
- Không import certificate không tin cậy vào trust store.
- Không tắt revocation hoặc hostname checking để làm mất lỗi.
- Không bỏ qua critical extension mà ứng dụng không hiểu.
- Theo dõi provider, JDK version và thay đổi trust store.
- Lưu audit evidence phù hợp nhưng tránh log dữ liệu nhạy cảm.
- Duy trì quy trình rotation và loại bỏ trust anchor có kiểm soát.

## 24. Câu hỏi tự kiểm tra

**1. CertificateFactory trong JCA dùng để làm gì?**

Parse dữ liệu certificate, CRL và CertPath đã mã hóa thành các đối tượng Java có cấu trúc.

**2. CertificateFactory có cấp hoặc ký certificate không?**

Không. Nó đọc certificate đã được tạo. Phát hành và ký certificate là công việc của CA và quy trình PKI.

**3. Tên factory phổ biến để đọc X.509 là gì?**

X.509.

**4. generateCertificate và generateCertificates khác nhau như thế nào?**

generateCertificate đọc một certificate; generateCertificates đọc một collection theo encoding mà provider hỗ trợ.

**5. CertificateFactory có xác minh certificate đáng tin cậy không?**

Không. Nó parse cấu trúc. Cần CertPathValidator và trust policy để xác minh path.

**6. DER và PEM khác nhau thế nào?**

DER là encoding ASN.1 nhị phân; PEM là Base64 có marker BEGIN/END bao quanh dữ liệu DER.

**7. Có nên giả định mọi provider đều parse được bundle PEM nối tiếp không?**

Không. Cần xác nhận định dạng và provider; có thể tách từng PEM block rồi decode riêng.

**8. Certificate collection có phải CertPath không?**

Không. Collection có thể không có thứ tự chain; CertPath biểu diễn đường dẫn certificate có thứ tự.

**9. Trust anchor có nằm trong CertPath không?**

Thông thường không. Trust anchor được cấu hình riêng trong PKIXParameters.

**10. CertPathValidator dùng thuật toán nào phổ biến cho X.509?**

PKIX.

**11. CertPathBuilder khác CertPathValidator thế nào?**

Builder tìm đường dẫn từ target tới trust anchor; Validator kiểm tra một đường dẫn đã có.

**12. Parse CRL thành công có chứng minh CRL hợp lệ không?**

Không. Cần xác minh chữ ký, issuer, freshness, scope và các extension liên quan.

**13. Không tìm thấy serial number trong một CRL có chứng minh certificate chưa bị thu hồi không?**

Không. CRL có thể không bao phủ issuer, scope hoặc loại certificate đó.

**14. checkValidity của X509Certificate kiểm tra điều gì?**

Kiểm tra thời điểm nằm trong khoảng NotBefore và NotAfter; không kiểm tra trust chain hay revocation.

**15. PKIX path hợp lệ có chứng minh hostname đúng không?**

Không. Hostname verification là bước identity check riêng.

**16. Có nên lấy root certificate từ bundle bên gửi và tự thêm làm trust anchor không?**

Không. Trust anchor phải đến từ nguồn tin cậy được quản trị độc lập.

**17. PKIXParameters có tự bật revocation theo mọi cấu hình không?**

Ứng dụng cần cấu hình và kiểm thử revocation policy rõ ràng, bao gồm PKIXRevocationChecker, CRL/OCSP và hành vi khi nguồn không sẵn sàng.

**18. Vì sao cần giới hạn kích thước certificate input?**

Dữ liệu không tin cậy có thể lớn hoặc được tạo có chủ đích để tiêu thụ bộ nhớ và CPU.

**19. CertificateFactory có thay thế KeyStore không?**

Không. Factory parse certificate; KeyStore lưu hoặc tham chiếu key và certificate entry theo provider/type.

**20. Certificate có SAN đúng nhưng chain không tin cậy thì có chấp nhận không?**

Không. Identity match không thay thế trust path validation.

## 25. Tài liệu tham khảo

- Java SE 17 API — java.security.cert.CertificateFactory: API parse certificate, CRL và CertPath.
- Java SE 17 API — X509Certificate, X509CRL, CertPath, CertPathValidator, CertPathBuilder, PKIXParameters và PKIXRevocationChecker.
- Java Cryptography Architecture (JCA) Reference Guide: provider và kiến trúc dịch vụ bảo mật.
- RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile.
- RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures.
- RFC 6960 — Online Certificate Status Protocol (OCSP).
- Tài liệu provider/JDK đang triển khai, đặc biệt về encoding được hỗ trợ, PKIX và revocation behavior.

