# Certificate validation trong Java

**Certificate validation** là quá trình xác minh một certificate X.509 có thể được chấp nhận cho một mục đích cụ thể hay không. Với TLS, ứng dụng cần xác minh certificate của peer, đường dẫn chữ ký tới một trust anchor đáng tin, thời hạn hiệu lực, tên máy chủ, mục đích sử dụng và các chính sách bảo mật liên quan.

Một certificate đọc được bằng keytool chưa chắc đã đáng tin. Việc kiểm tra một vài trường như Subject, Issuer hoặc Not After chỉ là bước xem thông tin. Validation đầy đủ còn phải xác minh chữ ký của từng certificate trong chain, CA constraints, hostname/SAN, Key Usage, Extended Key Usage và trạng thái thu hồi theo chính sách.

Một lệnh xem thông tin certificate:

~~~bash
keytool -printcert -v -file server.pem
~~~

Một chương trình Java có thể xác minh certificate path bằng PKIX:

~~~java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
validator.validate(certPath, pkixParameters);
~~~

Với kết nối HTTPS, Java TLS stack còn cần kiểm tra hostname. Không được coi việc PKIX path validation thành công là đủ để kết luận certificate phù hợp với hostname mà client đang truy cập.

## 1. Certificate validation giải quyết vấn đề gì?

Certificate X.509 gắn public key với một danh tính. Trong TLS, server gửi certificate để client xác minh danh tính server và thiết lập kênh bảo mật.

Validation cần trả lời các câu hỏi:

- Certificate có được ký bởi issuer hợp lệ không?
- Có xây dựng được đường dẫn từ leaf certificate tới trust anchor mà ứng dụng tin cậy không?
- Chữ ký trên từng certificate có hợp lệ không?
- Certificate hiện tại đã có hiệu lực và chưa hết hạn chưa?
- Certificate có đúng hostname hoặc IP mà client truy cập không?
- Certificate có được phép dùng cho TLS server hoặc TLS client không?
- Certificate có bị thu hồi không, nếu chính sách yêu cầu kiểm tra thu hồi?
- Thuật toán, kích thước khóa và extension có đáp ứng security policy không?

Ví dụ, một server có thể gửi certificate với Subject là CN=localhost và chữ ký đúng. Nhưng nếu client truy cập api.example.com, certificate chỉ có SAN DNS localhost thì vẫn phải bị từ chối. Chữ ký hợp lệ không sửa được hostname mismatch.

Certificate validation là một phần của bảo mật runtime vì nó quyết định peer nào được phép tham gia kết nối TLS và danh tính nào được ứng dụng chấp nhận.

## 2. Các thành phần trong certificate X.509

Một certificate thường có các trường quan trọng:

| Thành phần | Ý nghĩa |
|---|---|
| Subject | Danh tính của chủ thể sở hữu public key |
| Issuer | CA hoặc chủ thể đã ký certificate |
| Serial Number | Số định danh certificate trong phạm vi issuer |
| Not Before | Thời điểm certificate bắt đầu có hiệu lực |
| Not After | Thời điểm certificate hết hiệu lực |
| Subject Public Key Info | Public key và thuật toán |
| Signature Algorithm | Thuật toán ký certificate |
| Extensions | SAN, Key Usage, EKU, Basic Constraints, Name Constraints... |

Certificate không chứa private key. Private key phải được bảo vệ riêng trong keystore, HSM hoặc thiết bị quản lý khóa.

Các extension quyết định certificate được dùng trong ngữ cảnh nào. Một certificate CA phải có Basic Constraints phù hợp; một certificate TLS server thường có SAN chứa hostname và EKU serverAuth nếu EKU được chỉ định.

## 3. Certificate chain và trust anchor

Certificate chain liên kết certificate của endpoint tới một CA được tin cậy.

Một chain thường có dạng:

~~~text
TLS server certificate (leaf)
          |
          v
Intermediate CA certificate
          |
          v
Root CA certificate (trust anchor)
~~~

- **Leaf certificate:** certificate của server hoặc client đang được xác minh.
- **Intermediate CA:** CA trung gian ký leaf hoặc CA cấp dưới.
- **Root CA:** trust anchor được cấu hình tin cậy trong ứng dụng hoặc môi trường.

Trong CertPath thường đưa leaf và các intermediate certificate theo thứ tự tới issuer gần nhất. Trust anchor được truyền riêng cho PKIXParameters và thường không nằm trong CertPath cần validate.

Trust anchor không trở nên đáng tin chỉ vì certificate tự ký. Nó được tin cậy vì tổ chức hoặc người vận hành đã cài đặt và chấp nhận public key/certificate đó qua một quy trình tin cậy.

Certificate tự ký có thể dùng trong lab hoặc private PKI. Để được chấp nhận, client cần cấu hình trust anchor tương ứng. Không import một certificate không rõ nguồn gốc chỉ để bỏ lỗi TLS.

## 4. PKIX path building và path validation

Java hỗ trợ PKIX (Public Key Infrastructure using X.509) để xây dựng và xác minh certificate path.

Hai thao tác có liên quan nhưng khác nhau:

- **Path building:** tìm chuỗi certificate từ leaf tới một trust anchor dựa trên certificate sẵn có.
- **Path validation:** kiểm tra một chuỗi đã chọn có tuân thủ quy tắc PKIX hay không.

Java cung cấp:

- CertPathBuilder để xây dựng path.
- CertPathValidator để xác minh path đã có.
- PKIXBuilderParameters và PKIXParameters để cấu hình trust anchor và chính sách.
- CertificateFactory để đọc certificate hoặc tạo CertPath.

Trong ví dụ đơn giản, ta đã có leaf và root nên có thể tạo CertPath trực tiếp rồi gọi CertPathValidator. Trong hệ thống thật, chain có thể chứa intermediate certificate hoặc phải được xây dựng từ nhiều nguồn; khi đó dùng CertPathBuilder hoặc cung cấp CertStore chứa intermediate certificates.

Trong quá trình validation, PKIX kiểm tra các yếu tố như chữ ký, thời hạn, CA constraints, path length, name constraints, certificate policies và algorithm constraints theo cấu hình/provider.

## 5. Trust anchor và truststore

Trust anchor là điểm cuối được ứng dụng chấp nhận làm gốc tin cậy. Nó thường là root CA certificate, nhưng cũng có thể là một certificate được tin cậy trực tiếp theo chính sách.

Java dùng KeyStore để lưu certificate tin cậy. Một truststore có thể là PKCS12 hoặc JKS.

Liệt kê cacerts mặc định:

~~~bash
keytool -list -cacerts
~~~

Xem chi tiết:

~~~bash
keytool -list -cacerts -v
~~~

Liệt kê truststore riêng:

~~~bash
keytool -list -v -keystore truststore.p12 -storetype PKCS12
~~~

Nhập một root CA certificate vào truststore riêng:

~~~bash
keytool -importcert \
    -alias example-root \
    -file root-ca.pem \
    -keystore truststore.p12 \
    -storetype PKCS12
~~~

Trước khi xác nhận import, kiểm tra Subject, Issuer và SHA-256 fingerprint qua một kênh độc lập đáng tin cậy.

### Truststore mặc định của JSSE

Nếu không chỉ định truststore riêng, JSSE sử dụng cơ chế tìm truststore mặc định của JDK. Thông thường, nếu thuộc tính hệ thống javax.net.ssl.trustStore được đặt thì file đó được dùng; nếu không, JSSE tìm jssecacerts rồi cacerts trong thư mục security của Java home.

Có thể cấu hình truststore khi chạy ứng dụng:

~~~bash
java \
    -Djavax.net.ssl.trustStore=truststore.p12 \
    -Djavax.net.ssl.trustStoreType=PKCS12 \
    com.example.Client
~~~

Nếu cần password, dùng secret injection phù hợp với môi trường vận hành; tránh ghi password thật trực tiếp vào command line, source hoặc log.

Một truststore được chọn sai có thể khiến ứng dụng không tin CA cần thiết hoặc tin quá nhiều CA. Kiểm tra đúng truststore mà runtime thực sự đang sử dụng.

## 6. Kiểm tra validity period

Certificate có hai mốc thời gian:

- Not Before: thời điểm bắt đầu có hiệu lực.
- Not After: thời điểm hết hạn.

Trong Java:

~~~java
certificate.checkValidity();
~~~

Lệnh này ném CertificateNotYetValidException nếu chưa tới Not Before và CertificateExpiredException nếu đã qua Not After.

Có thể kiểm tra tại một thời điểm cụ thể:

~~~java
certificate.checkValidity(new Date());
~~~

Validity check không xác minh chữ ký issuer, hostname, trust anchor hay revocation. Nó chỉ kiểm tra khoảng thời gian hiệu lực.

Các lỗi thời gian thường gặp:

- Đồng hồ máy bị sai.
- Certificate được tạo với Not Before ở tương lai.
- Certificate đã hết hạn.
- Certificate chain có một intermediate hết hạn dù leaf vẫn còn hạn.
- Hệ thống có timezone hoặc đồng bộ thời gian sai.

Với production, bảo đảm hệ thống đồng bộ thời gian và có quy trình gia hạn certificate trước khi hết hạn.

## 7. Xác minh chữ ký và certificate path

Một certificate có thể được parse thành công nhưng chữ ký chưa chắc hợp lệ. Việc parse chỉ chứng minh dữ liệu có cấu trúc X.509 mà CertificateFactory hiểu được.

PKIX validation cần:

1. Leaf certificate.
2. Intermediate certificates nếu có.
3. Trust anchor được chấp nhận.
4. CertPath đúng thứ tự.
5. PKIXParameters và chính sách tương ứng.

Ví dụ ý tưởng:

~~~java
CertificateFactory factory = CertificateFactory.getInstance("X.509");
CertPath path = factory.generateCertPath(certificates);

PKIXParameters parameters = new PKIXParameters(trustAnchors);
CertPathValidator validator = CertPathValidator.getInstance("PKIX");

validator.validate(path, parameters);
~~~

Nếu chain không kết thúc ở trust anchor, chữ ký sai, certificate CA không có Basic Constraints phù hợp hoặc path policy không hợp lệ, validator sẽ ném CertPathValidatorException.

Không tự xác minh certificate bằng cách chỉ so sánh Issuer với Subject của certificate tiếp theo. Hai tên khớp nhau không chứng minh chữ ký hợp lệ.

## 8. Subject Alternative Name và hostname validation

Hostname validation là bước riêng với PKIX path validation.

Với HTTPS, client phải xác minh hostname URL khớp Subject Alternative Name (SAN) trong leaf certificate. SAN có thể chứa:

- DNS name.
- IP address.
- Email address.
- URI và các loại GeneralName khác.

Ví dụ SAN:

~~~text
DNS:api.example.com
DNS:api.internal.example.com
IP:192.0.2.10
~~~

Nếu client truy cập https://api.example.com, SAN phải chứa DNS name phù hợp. Nếu client truy cập bằng IP, certificate cần SAN dạng IP tương ứng. Không chỉ dựa vào Common Name (CN) vì client hiện đại sử dụng SAN cho hostname verification.

### Wildcard DNS name

Wildcard certificate như *.example.com thường chỉ khớp một label ở vị trí wildcard, ví dụ api.example.com; không mặc nhiên khớp a.b.example.com. Quy tắc chi tiết phụ thuộc hostname verifier và TLS client.

Không tự viết một bộ so khớp wildcard đơn giản cho production. Dùng hostname verification của JSSE hoặc HTTP client đáng tin cậy.

### HttpsURLConnection

HttpsURLConnection thực hiện hostname verification mặc định. Nếu chỉ thay SSLSocketFactory để dùng truststore riêng, đừng vô hiệu hóa HostnameVerifier mặc định.

### SSLSocket và endpoint identification

Với raw SSLSocket, cần cấu hình endpoint identification:

~~~java
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
~~~

Nếu bỏ qua bước này, ứng dụng có thể xác minh certificate path nhưng không xác minh certificate có thuộc hostname đang kết nối hay không.

## 9. Key Usage, Extended Key Usage và Basic Constraints

Certificate có thể hợp lệ về chữ ký và thời hạn nhưng không phù hợp mục đích sử dụng.

### Key Usage

Key Usage giới hạn cách dùng public key, ví dụ:

- digitalSignature.
- keyEncipherment.
- keyAgreement.
- keyCertSign.
- cRLSign.

Certificate CA thường cần keyCertSign nếu dùng để ký certificate khác. Certificate TLS server có thể cần digitalSignature hoặc key usage phù hợp với cipher suite/key exchange được dùng.

### Extended Key Usage (EKU)

EKU xác định mục đích sử dụng mở rộng, ví dụ:

| OID / tên | Mục đích |
|---|---|
| serverAuth | TLS server authentication |
| clientAuth | TLS client authentication |
| codeSigning | Ký mã |
| emailProtection | Bảo vệ email |
| timeStamping | Timestamp authority |

Nếu EKU có mặt, certificate cần cho phép mục đích sử dụng tương ứng. Nếu EKU không có, ý nghĩa phụ thuộc quy tắc PKI và chính sách áp dụng; không tự suy luận rằng certificate bị cấm mọi mục đích.

### Basic Constraints

Basic Constraints xác định certificate có phải CA hay không và có thể đặt path length constraint. Một intermediate CA không được vượt quá giới hạn path length đã khai báo.

PKIX validator kiểm tra CA constraints của certificate trong path. Trust anchor cần được quản lý và chấp nhận theo chính sách riêng.

## 10. Name Constraints và Certificate Policies

Một số CA giới hạn namespace hoặc loại certificate mà CA con được phép cấp.

**Name Constraints** có thể giới hạn DNS suffix, IP range, email domain hoặc namespace khác. Ví dụ một intermediate chỉ được cấp certificate cho host thuộc internal.example.com.

**Certificate Policies** mang OID mô tả chính sách cấp phát. Ứng dụng có thể yêu cầu một tập policy cụ thể thông qua PKIXParameters.

Không phải ứng dụng nào cũng cần tự cấu hình policy OID, nhưng hệ thống PKI doanh nghiệp hoặc lĩnh vực được quản lý có thể yêu cầu kiểm tra chính sách này.

PKIX validation cần được cấu hình phù hợp với certificate profile của CA. Một certificate được CA ký không có nghĩa nó phù hợp mọi mục đích hoặc mọi namespace.

## 11. Kiểm tra thu hồi certificate: CRL và OCSP

Certificate có thể bị thu hồi trước Not After, ví dụ private key bị lộ, danh tính thay đổi hoặc CA phát hiện cấp certificate sai.

Hai cơ chế phổ biến:

- **CRL (Certificate Revocation List):** danh sách serial number certificate đã bị thu hồi do CA phát hành.
- **OCSP (Online Certificate Status Protocol):** truy vấn trạng thái một certificate tới responder.

Validation có thể kiểm tra trạng thái thu hồi thông qua CRL/OCSP theo cấu hình PKIX provider, hệ thống và chính sách.

Trong Java, PKIXRevocationChecker cho phép cấu hình kiểm tra thu hồi:

~~~java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");

PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS));

parameters.addCertPathChecker(checker);
~~~

Đây là phần cấu hình minh họa; production cần xác định rõ nguồn CRL/OCSP, thời gian timeout, cache, fallback và cách xử lý khi responder không truy cập được.

Có hai chính sách thường gặp:

- **Fail closed:** không xác minh được trạng thái thu hồi thì từ chối kết nối.
- **Soft fail:** có thể tiếp tục trong một số trường hợp không truy cập được responder, tùy chính sách.

Soft fail cải thiện khả năng sẵn sàng nhưng có thể chấp nhận certificate mà trạng thái thu hồi chưa xác định. Không bật tùy chọn soft fail chỉ để tránh lỗi mạng mà chưa đánh giá rủi ro.

Revocation checking có thể gây phụ thuộc mạng và độ trễ. Thiết kế cần cân nhắc cache, responder availability và hành vi khi offline.

## 12. Algorithm constraints và security policy

Certificate validation còn chịu ảnh hưởng của thuật toán và kích thước khóa.

JDK có các security property như:

- jdk.certpath.disabledAlgorithms: thuật toán hoặc khóa bị hạn chế trong certificate path.
- jdk.tls.disabledAlgorithms: thuật toán bị hạn chế trong TLS handshake.

Các giới hạn có thể thay đổi theo phiên bản JDK và security configuration. Ví dụ, khóa quá ngắn hoặc chữ ký dùng thuật toán yếu có thể bị từ chối dù certificate vẫn có cấu trúc hợp lệ.

Không nên hạ thấp security property toàn cục chỉ để kết nối với một server cũ. Tìm certificate hoặc cấu hình TLS phù hợp, nâng cấp server và đánh giá ngoại lệ theo quy trình bảo mật.

## 13. Xác minh certificate trong Java bằng PKIX

Java cung cấp API tiêu chuẩn để đọc X.509 certificate và validate path.

Các lớp chính:

| API | Chức năng |
|---|---|
| CertificateFactory | Parse X.509 certificate và tạo CertPath |
| X509Certificate | Truy cập trường, extension và kiểm tra validity |
| TrustAnchor | Khai báo trust anchor |
| PKIXParameters | Cấu hình validation |
| CertPathValidator | Xác minh CertPath |
| CertPathBuilder | Tìm CertPath từ certificate có sẵn |
| CertStore | Cung cấp intermediate certificate hoặc CRL |
| PKIXRevocationChecker | Cấu hình revocation checking |

Một quy trình tối thiểu:

1. Đọc leaf và trust anchor.
2. Kiểm tra validity.
3. Tạo CertPath gồm leaf và intermediate certificates.
4. Tạo PKIXParameters với trust anchor.
5. Cấu hình revocation và policy theo yêu cầu.
6. Gọi CertPathValidator.
7. Kiểm tra hostname/SAN riêng.
8. Kiểm tra EKU/Key Usage theo mục đích.
9. Xử lý exception và ghi log không chứa secret.

## 14. Ví dụ Java 17+ chạy được: validate leaf certificate

Ví dụ này xác minh một certificate server do root CA demo ký. Nó kiểm tra PKIX path, thời hạn, SAN hostname và EKU serverAuth.

Chương trình nhận ba tham số:

- File leaf certificate.
- File root CA certificate.
- Hostname cần xác minh.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;
import java.util.Set;

public final class CertificateValidation {
    private static final String SERVER_AUTH = "1.3.6.1.5.5.7.3.1";

    private CertificateValidation() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: CertificateValidation <leaf.pem> <root.pem> <hostname>");
        }

        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        X509Certificate leaf = readCertificate(factory, Path.of(args[0]));
        X509Certificate root = readCertificate(factory, Path.of(args[1]));
        String hostname = args[2];

        leaf.checkValidity();
        root.checkValidity();
        if (root.getBasicConstraints() < 0) {
            throw new IllegalArgumentException(
                    "Trust anchor is not a CA certificate");
        }

        CertPath path = factory.generateCertPath(List.of(leaf));
        PKIXParameters parameters = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));

        // Demo only: production must configure revocation checking.
        parameters.setRevocationEnabled(false);

        CertPathValidator.getInstance("PKIX").validate(path, parameters);

        checkHostname(leaf, hostname);
        checkServerUsage(leaf);

        System.out.println("PKIX path: PASS");
        System.out.println("Leaf certificate validity: PASS");
        System.out.println("Hostname " + hostname + ": PASS");
        System.out.println("Extended Key Usage serverAuth: PASS");
    }

    private static X509Certificate readCertificate(
            CertificateFactory factory, Path file) throws Exception {
        try (InputStream input = Files.newInputStream(file)) {
            return (X509Certificate) factory.generateCertificate(input);
        }
    }

    private static void checkHostname(
            X509Certificate certificate, String hostname) throws Exception {
        Collection<List<?>> names = certificate.getSubjectAlternativeNames();
        if (names == null) {
            throw new IllegalArgumentException(
                    "Certificate has no Subject Alternative Name");
        }

        boolean matched = names.stream().anyMatch(name -> {
            Integer type = (Integer) name.get(0);
            String value = name.get(1).toString();
            return (type == 2 && hostname.equalsIgnoreCase(value))
                    || (type == 7 && hostname.equals(value));
        });

        if (!matched) {
            throw new IllegalArgumentException(
                    "Hostname does not match certificate SAN");
        }
    }

    private static void checkServerUsage(
            X509Certificate certificate) throws Exception {
        List<String> usages = certificate.getExtendedKeyUsage();
        if (usages != null && !usages.contains(SERVER_AUTH)) {
            throw new IllegalArgumentException(
                    "Certificate is not valid for TLS server use");
        }

        boolean[] keyUsage = certificate.getKeyUsage();
        if (keyUsage != null && keyUsage.length > 0
                && !(keyUsage[0]
                || (keyUsage.length > 2 && keyUsage[2])
                || (keyUsage.length > 4 && keyUsage[4]))) {
            throw new IllegalArgumentException(
                    "Key Usage does not permit TLS server signing/agreement");
        }
    }
}
~~~

Lưu thành CertificateValidation.java.

Lưu ý phạm vi ví dụ:

- CertPath chỉ gồm leaf vì lab dùng một root CA ký trực tiếp.
- Trust anchor được cung cấp riêng và phải được tin cậy qua kênh ngoài.
- Revocation checking được tắt rõ ràng để lab chạy offline; không dùng cấu hình này làm production policy.
- Hostname matching chỉ minh họa DNS/IP SAN exact match; không triển khai wildcard, IDN hoặc toàn bộ quy tắc HTTPS.
- Production HTTPS nên dùng hostname verification mặc định của JSSE/HTTP client thay vì tự viết matcher.

## 15. Tạo root CA và leaf certificate cho bài lab

Các lệnh sau tạo một root CA demo và certificate TLS server cho localhost. Chỉ dùng trong môi trường học tập; root CA demo không phải CA công cộng.

Tạo thư mục:

~~~bash
mkdir -p build
~~~

### Bước 1: tạo root CA

~~~bash
keytool -genkeypair \
    -alias root-ca \
    -keyalg RSA \
    -keysize 3072 \
    -dname "CN=Example Demo Root CA, O=Example, C=VN" \
    -ext BC=ca:true \
    -ext KU=keyCertSign,cRLSign \
    -validity 3650 \
    -keystore build/root-ca.p12 \
    -storetype PKCS12
~~~

keytool hỏi password. Giữ private key root CA được bảo vệ; trong lab có thể dùng một file keystore tạm.

Export public certificate:

~~~bash
keytool -exportcert -rfc \
    -alias root-ca \
    -keystore build/root-ca.p12 \
    -storetype PKCS12 \
    -file build/root-ca.pem
~~~

### Bước 2: tạo key pair server

~~~bash
keytool -genkeypair \
    -alias localhost \
    -keyalg RSA \
    -keysize 2048 \
    -dname "CN=localhost, O=Example, C=VN" \
    -ext SAN=dns:localhost,ip:127.0.0.1 \
    -validity 365 \
    -keystore build/server.p12 \
    -storetype PKCS12
~~~

### Bước 3: tạo CSR cho server

~~~bash
keytool -certreq \
    -alias localhost \
    -keystore build/server.p12 \
    -storetype PKCS12 \
    -file build/server.csr \
    -ext SAN=dns:localhost,ip:127.0.0.1 \
    -ext KU=digitalSignature,keyEncipherment \
    -ext EKU=serverAuth
~~~

CSR chứa public key và thông tin Subject; private key vẫn ở server.p12.

### Bước 4: CA ký CSR

~~~bash
keytool -gencert \
    -alias root-ca \
    -keystore build/root-ca.p12 \
    -storetype PKCS12 \
    -infile build/server.csr \
    -outfile build/server.pem \
    -rfc \
    -validity 365 \
    -ext SAN=dns:localhost,ip:127.0.0.1 \
    -ext KU=digitalSignature,keyEncipherment \
    -ext EKU=serverAuth
~~~

Đây là thao tác của CA demo. Trong production, CA thực hiện cấp certificate theo quy trình xác minh danh tính và chính sách.

### Bước 5: kiểm tra certificate

~~~bash
keytool -printcert -v -file build/server.pem
keytool -printcert -v -file build/root-ca.pem
~~~

Kiểm tra Issuer của leaf khớp Subject của root, SAN có localhost, EKU có serverAuth và validity phù hợp.

### Bước 6: biên dịch Java 17

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/CertificateValidation.java
~~~

Đặt file CertificateValidation.java vào src trước khi chạy lệnh.

### Bước 7: chạy validation

~~~bash
java -cp build/classes CertificateValidation \
    build/server.pem \
    build/root-ca.pem \
    localhost
~~~

Output đã xác minh với JDK 24.0.2:

~~~text
PKIX path: PASS
Leaf certificate validity: PASS
Hostname localhost: PASS
Extended Key Usage serverAuth: PASS
~~~

Kiểm tra hostname sai:

~~~bash
java -cp build/classes CertificateValidation \
    build/server.pem \
    build/root-ca.pem \
    wrong.example
~~~

Lệnh này phải thất bại với thông báo hostname không khớp SAN. Đây là negative test xác nhận chương trình không chỉ kiểm tra chữ ký và thời hạn.

## 16. Dùng truststore riêng với JSSE

Trong ứng dụng TLS thật, nên để JSSE thực hiện PKIX path validation qua TrustManagerFactory thay vì tự viết một TrustManager đơn giản.

Tạo truststore từ root CA đã xác minh:

~~~bash
keytool -importcert \
    -alias example-root \
    -file build/root-ca.pem \
    -keystore build/truststore.p12 \
    -storetype PKCS12
~~~

Đoạn Java tạo SSLContext từ truststore:

~~~java
KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(
        Path.of("build/truststore.p12"))) {
    trustStore.load(input, trustStorePassword);
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(null, tmf.getTrustManagers(), null);
~~~

Sau đó cấu hình SSLContext cho HTTP client hoặc HttpsURLConnection.

Với HttpsURLConnection:

~~~java
HttpsURLConnection connection =
        (HttpsURLConnection) url.openConnection();

connection.setSSLSocketFactory(sslContext.getSocketFactory());
~~~

Hostname verification mặc định của HttpsURLConnection vẫn cần được giữ nguyên. Không thay bằng HostnameVerifier luôn trả true.

Với Java HttpClient:

~~~java
HttpClient client = HttpClient.newBuilder()
        .sslContext(sslContext)
        .build();
~~~

Java HttpClient thực hiện xác minh endpoint theo cơ chế HTTPS mặc định. Nếu tùy chỉnh TLS, cần bảo đảm không vô tình vô hiệu hóa endpoint identification.

## 17. Custom TrustManager và lỗi trust-all

Một anti-pattern nguy hiểm là tạo TrustManager chấp nhận mọi certificate:

~~~java
// KHÔNG DÙNG TRONG ỨNG DỤNG THẬT
X509TrustManager trustAll = new X509TrustManager() {
    public void checkClientTrusted(X509Certificate[] chain, String authType) {
    }

    public void checkServerTrusted(X509Certificate[] chain, String authType) {
    }

    public X509Certificate[] getAcceptedIssuers() {
        return new X509Certificate[0];
    }
};
~~~

Các method rỗng làm cho certificate không được xác minh đúng cách. Kẻ tấn công có thể giả mạo server trong một cuộc tấn công man-in-the-middle nếu ứng dụng chấp nhận kết nối.

Không khắc phục lỗi SSL bằng cách:

- Chấp nhận mọi certificate.
- Tắt hostname verification.
- Bỏ qua lỗi certificate expired.
- Tắt kiểm tra chữ ký hoặc algorithm constraints.
- Import certificate lạ mà không xác minh fingerprint.

Nếu cần private CA, thêm đúng CA certificate vào truststore riêng và giữ nguyên PKIX cùng hostname verification.

Nếu cần custom TrustManager, ưu tiên delegate tới TrustManagerFactory chuẩn rồi bổ sung policy hẹp, có review và test. Không tự viết lại toàn bộ PKIX validation nếu không có yêu cầu rõ ràng.

## 18. Mutual TLS (mTLS)

Trong TLS thông thường, client xác minh certificate server. Với mutual TLS, server cũng yêu cầu client gửi certificate để xác minh danh tính client.

mTLS có hai phía:

- Client truststore chứa CA được dùng để xác minh server.
- Client keystore chứa private key và certificate chain của client.
- Server truststore chứa CA được dùng để xác minh client.
- Server keystore chứa private key và certificate chain của server.

Cấu hình SSLContext có thể nhận cả KeyManager và TrustManager:

~~~java
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(clientKeyStore, clientKeyPassword);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(serverTrustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
~~~

KeyManager chọn identity certificate/private key mà client trình bày. TrustManager xác minh certificate peer.

mTLS không có nghĩa mọi certificate được CA ký đều được phép truy cập mọi API. Ứng dụng vẫn cần kiểm tra identity, role, authorization và policy ở tầng ứng dụng.

## 19. Certificate pinning

Certificate hoặc public key pinning là kỹ thuật ứng dụng chỉ chấp nhận một fingerprint hoặc public key đã được cấu hình trước.

Pinning có thể giảm rủi ro khi truststore của thiết bị có CA không mong muốn, nhưng cũng tạo rủi ro vận hành:

- Certificate hoặc key rotation có thể làm ứng dụng mất kết nối.
- Pin bị lộ hoặc cấu hình sai có thể gây outage.
- Phải có kế hoạch backup pin và chuyển đổi.
- Pinning không thay thế hostname verification và PKIX validation.

Nếu dùng pinning, thường nên pin public key/SPKI hoặc tập pin có kế hoạch rotation thay vì chỉ pin một leaf certificate ngắn hạn. Cần quản lý pin mới/cũ, thời gian overlap và quy trình khôi phục.

Không tự triển khai pinning bằng cách so sánh một chuỗi Subject hoặc CN. Dùng fingerprint/SPKI có định dạng chuẩn và kiểm thử rotation.

## 20. Chẩn đoán lỗi certificate validation

### CertificateExpiredException

Leaf hoặc một certificate trong path đã hết hạn. Kiểm tra Not After, đồng hồ hệ thống và quy trình gia hạn.

### CertificateNotYetValidException

Thời điểm hiện tại sớm hơn Not Before. Kiểm tra đồng hồ, thời gian phát hành và timezone.

### CertPathValidatorException: Path does not chain with any of the trust anchors

Không xây dựng được path tới trust anchor. Kiểm tra truststore, root CA, intermediate certificate và đúng certificate chain.

### Signature does not verify

Certificate có chữ ký không hợp lệ hoặc chain bị sai. Kiểm tra nguồn certificate, issuer, nội dung file và chain do CA cung cấp.

### No subject alternative DNS name matching

Hostname client truy cập không khớp DNS SAN. Kiểm tra URL, SAN và cấu hình DNS. Không dùng cách tắt hostname verification để che lỗi.

### No subject alternative names present

Certificate thiếu SAN cần thiết cho hostname/IP hiện tại. Cấp lại certificate với SAN phù hợp.

### Extended key usage does not permit use

EKU không cho phép serverAuth hoặc clientAuth theo mục đích kết nối. Cấp certificate với profile đúng; không bỏ kiểm tra chỉ để kết nối thành công.

### Algorithm constraints check failed

Thuật toán hoặc kích thước khóa bị security policy từ chối. Nâng cấp certificate/key hoặc cấu hình server theo policy hiện hành.

### Revocation status unknown

Không lấy được CRL/OCSP hoặc không xác định được trạng thái thu hồi. Kiểm tra network, responder URL, cache, firewall và policy fail-open/fail-closed.

### Certificate revoked

Certificate đã bị CA thu hồi. Ngừng sử dụng và cấp lại certificate theo quy trình CA. Không thêm certificate bị thu hồi vào truststore.

### PKIX path building failed

Lỗi tổng quát khi xây dựng path. Đọc nguyên nhân sâu hơn trong cause chain, kiểm tra intermediate CA, trust anchor, validity, constraints và certificate policies.

## 21. Quy trình certificate validation trong production

Một quy trình kiểm tra server certificate có thể gồm:

1. Nhận leaf certificate và intermediate chain từ TLS peer.
2. Xây dựng certification path tới trust anchor được cấu hình.
3. Xác minh chữ ký và CA constraints theo PKIX.
4. Kiểm tra validity period của các certificate trong path.
5. Áp dụng algorithm constraints và certificate policies.
6. Kiểm tra revocation theo CRL/OCSP policy.
7. Kiểm tra SAN khớp hostname hoặc IP đang kết nối.
8. Kiểm tra EKU và Key Usage cho TLS server/client.
9. Chỉ thiết lập kết nối khi mọi điều kiện bắt buộc đạt.
10. Ghi log đủ thông tin chẩn đoán nhưng không ghi private key, password hoặc dữ liệu nhạy cảm.

Với client TLS, ưu tiên JSSE và HTTP client chuẩn. Chỉ tự xây dựng CertPathValidator khi ứng dụng cần kiểm tra certificate offline, audit hoặc áp dụng policy đặc thù.

## 22. Checklist vận hành

- [ ] Trust anchor được phân phối qua kênh đáng tin cậy.
- [ ] Truststore đúng với ứng dụng và môi trường.
- [ ] Certificate chain có leaf và intermediate cần thiết.
- [ ] Root CA được chấp nhận rõ ràng theo chính sách.
- [ ] Not Before/Not After hợp lệ.
- [ ] SAN khớp hostname/IP.
- [ ] Key Usage và EKU phù hợp.
- [ ] Basic Constraints và path length hợp lệ.
- [ ] Algorithm constraints đáp ứng chính sách.
- [ ] Revocation checking được cấu hình theo yêu cầu.
- [ ] Đồng hồ hệ thống được đồng bộ.
- [ ] Không có trust-all TrustManager.
- [ ] Không tắt hostname verification.
- [ ] Certificate rotation và truststore update có kế hoạch.
- [ ] Có test positive và negative cho expired, untrusted, wrong hostname và wrong EKU.
- [ ] Log không chứa private key hoặc password.

Certificate validation không chỉ là đọc một certificate hoặc kiểm tra ngày hết hạn. Một kết nối an toàn cần xác minh được chain tới trust anchor, đúng mục đích sử dụng, đúng hostname, còn hiệu lực và tuân thủ revocation/algorithm policy. Hãy để JSSE thực hiện validation chuẩn trong TLS, cấu hình truststore có kiểm soát và chỉ tự viết PKIX logic khi có nhu cầu cụ thể.

## Tài liệu tham khảo

- [Java Secure Socket Extension (JSSE) Reference Guide — Java SE 24](https://docs.oracle.com/en/java/javase/24/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Java Security Developer's Guide — PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/24/security/java-pki-programmers-guide.html)
- [CertPathValidator API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/cert/CertPathValidator.html)
- [PKIXParameters API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/cert/PKIXParameters.html)
- [X509Certificate API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/cert/X509Certificate.html)
