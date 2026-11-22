# Trust anchor trong Java và PKIX

Trust anchor là điểm tin cậy được một ứng dụng hoặc hệ thống lựa chọn trước khi xác minh chứng thư số X.509. Khi một máy chủ gửi certificate cho client trong TLS, client cần xác định certificate đó được ký bởi CA nào, các certificate trung gian có nối thành một đường dẫn hợp lệ hay không và đường dẫn có kết thúc tại một CA mà client chấp nhận hay không.

Trong Java, trust anchor được biểu diễn trực tiếp bằng lớp `java.security.cert.TrustAnchor`. Lớp này được dùng cùng `PKIXParameters` và `CertPathValidator` để xác minh certification path. Với TLS, trust material thường được lưu trong một `KeyStore` và được nạp vào `TrustManagerFactory` để tạo trust manager cho `SSLContext`.

## 1. Trust anchor là gì?

Trust anchor, còn gọi là *most-trusted CA*, là CA mà bên xác minh quyết định tin cậy để làm điểm bắt đầu cho việc kiểm tra một certification path. Thông tin cốt lõi của anchor gồm:

- Tên CA (distinguished name).
- Public key của CA.
- Các giới hạn áp dụng cho những path được xác minh bằng public key đó, nếu có.

Trong mô hình PKI phổ biến, trust anchor thường được biểu diễn bằng certificate của root CA. Tuy nhiên, về mặt PKIX, trust anchor là đầu vào của thuật toán xác minh; nó có thể được cung cấp bằng một X.509 certificate đã được tin cậy hoặc bằng cặp tên CA và public key.

Điểm cần hiểu rõ: một certificate tự ký (self-signed) không tự trở thành đáng tin. Bất kỳ ai cũng có thể tự tạo một certificate có Subject DN giống tên một CA nổi tiếng. Niềm tin vào public key của CA phải đến từ một kênh đáng tin cậy và một quyết định chính sách cục bộ, chẳng hạn bộ root CA đã được hệ điều hành/JDK quản lý hoặc certificate đã được quản trị viên xác minh fingerprint rồi cài vào truststore.

### 1.1. Các vai trò trong certificate hierarchy

Một chuỗi chứng thư điển hình có ba vai trò:

| Thành phần | Vai trò |
|---|---|
| Root CA | CA ở cấp cao nhất trong hierarchy; thường tự ký và được phân phối như trust anchor |
| Intermediate CA | CA được CA cấp trên ký; dùng để phát hành certificate cho CA hoặc end entity khác |
| Leaf / end-entity certificate | Certificate của server, client, người dùng hoặc ứng dụng cần xác minh |

Ví dụ đường dẫn:

~~~text
Trust anchor: Example Root CA
        |
        | ký
        v
Intermediate CA
        |
        | ký
        v
Leaf certificate: api.example.test
~~~

Client không tin cậy leaf certificate chỉ vì server gửi nó. Client kiểm tra chữ ký của leaf bằng public key của intermediate, kiểm tra tiếp intermediate theo CA phía trên, rồi xác minh rằng path kết thúc ở một trust anchor được client chấp nhận.

Trust anchor không nhất thiết phải là root CA công khai toàn cầu. Một tổ chức có thể chọn CA nội bộ hoặc intermediate CA làm anchor cho một ứng dụng hay một miền sử dụng cụ thể. Việc chọn anchor là quyết định chính sách; hai ứng dụng khác nhau có thể sử dụng hai tập trust anchor khác nhau.

### 1.2. Trust anchor khác certificate chain và truststore

Ba khái niệm thường bị nhầm:

| Khái niệm | Ý nghĩa |
|---|---|
| Trust anchor | Điểm tin cậy được đưa vào thuật toán PKIX |
| Certification path / certificate chain | Các certificate nối từ certificate đích về phía CA phát hành |
| Truststore | Kho lưu trữ certificate được ứng dụng dùng làm nguồn trust material; thường là một file KeyStore |

Truststore là nơi chứa dữ liệu. Trust anchor là vai trò của một CA trong quyết định xác minh. Khi Java tạo `PKIXParameters` từ một `KeyStore`, các trusted certificate entry trong store được dùng làm tập most-trusted CA cho quá trình PKIX.

Một truststore không cần chứa private key của CA. Để xác minh chữ ký certificate, ứng dụng chỉ cần public key và thông tin trust đã được xác nhận. Private key của root CA phải được bảo vệ riêng, thường offline hoặc trong HSM.

## 2. Trust anchor tham gia xác minh PKIX như thế nào?

PKIX (Public Key Infrastructure using X.509) xác minh rằng certificate đích được liên kết hợp lệ với public key của một CA mà bên kiểm tra tin cậy.

Quy trình tổng quát:

1. Ứng dụng nhận certificate đích và các certificate trung gian cần thiết.
2. Xác định một hoặc nhiều trust anchor phù hợp với chính sách.
3. Xây dựng certification path từ certificate đích về CA phát hành.
4. Kiểm tra chữ ký, quan hệ issuer/subject, thời hạn, constraints, key usage và các quy tắc PKIX liên quan.
5. Kiểm tra trạng thái thu hồi nếu revocation checking được bật và cấu hình.
6. Trả kết quả hợp lệ hoặc ném exception nếu path không thỏa điều kiện.

Một số kiểm tra thường gặp trong quá trình xác minh:

- Chữ ký trên từng certificate phải xác minh được bằng public key của issuer tương ứng.
- Issuer của certificate con phải khớp với Subject của certificate cấp trên.
- Certificate trong path phải còn hiệu lực tại thời điểm kiểm tra.
- CA certificate phải có Basic Constraints và Key Usage phù hợp với vai trò ký certificate.
- Certificate policies, path length và name constraints được áp dụng theo cấu hình và khả năng hỗ trợ của provider.
- Certificate không được xuất hiện lặp lại trong một path.
- Trạng thái thu hồi được kiểm tra theo cơ chế CRL hoặc OCSP nếu được bật.

### 2.1. Trust anchor không nằm trong CertPath

Đối với X.509, danh sách certificate trong `CertPath` thường được sắp từ certificate đích lên certificate được CA tin cậy phát hành. Certificate đại diện cho trust anchor không được đưa vào danh sách path; nó được truyền riêng qua `PKIXParameters`.

Ví dụ, nếu root CA trực tiếp ký leaf certificate:

~~~text
TrustAnchor: Root CA
CertPath:
  1. Leaf certificate
~~~

Nếu có intermediate:

~~~text
TrustAnchor: Root CA
CertPath:
  1. Leaf certificate
  2. Intermediate CA certificate
~~~

Đừng thêm certificate của root anchor vào cuối `CertPath` chỉ vì nó xuất hiện trong file chain do server gửi. Root anchor được cung cấp riêng trong tập trust anchors.

### 2.2. CertPathBuilder và CertPathValidator

Hai API có nhiệm vụ khác nhau:

| API | Nhiệm vụ |
|---|---|
| `CertPathBuilder` | Tìm hoặc xây dựng một certification path từ certificate đích, trust anchors và nguồn certificate |
| `CertPathValidator` | Xác minh một `CertPath` đã có với tập tham số PKIX |

Nếu ứng dụng đã có danh sách certificate theo đúng thứ tự, có thể tạo `CertPath` bằng `CertificateFactory` rồi dùng `CertPathValidator`.

Nếu ứng dụng chỉ biết certificate đích và cần tìm intermediate certificate từ nhiều nguồn, dùng `CertPathBuilder` cùng `PKIXBuilderParameters` và `CertStore`.

## 3. Các lớp Java quan trọng

### 3.1. java.security.cert.TrustAnchor

`TrustAnchor` đại diện cho CA đáng tin nhất trong một path. Có ba constructor chính:

~~~java
new TrustAnchor(X509Certificate trustedCert, byte[] nameConstraints);

new TrustAnchor(
        X500Principal caPrincipal,
        PublicKey pubKey,
        byte[] nameConstraints);

new TrustAnchor(
        String caName,
        PublicKey pubKey,
        byte[] nameConstraints);
~~~

Cách thường dùng là truyền certificate CA đã được xác minh:

~~~java
TrustAnchor anchor = new TrustAnchor(rootCertificate, null);
~~~

Tham số `nameConstraints` là dữ liệu ASN.1 DER của NameConstraints extension bổ sung. Khả năng hỗ trợ tham số này phụ thuộc provider; tài liệu Oracle JDK 21 cho biết implementation PKIX của SUN provider không hỗ trợ tham số name constraints của `TrustAnchor` và có thể ném `InvalidAlgorithmParameterException` nếu truyền giá trị này. Vì vậy, không nên giả định mọi provider xử lý giống nhau.

### 3.2. PKIXParameters

`PKIXParameters` chứa tập trust anchor và các tham số dùng trong thuật toán xác minh PKIX.

Có thể khởi tạo từ một tập `TrustAnchor`:

~~~java
Set<TrustAnchor> anchors = Set.of(anchor);
PKIXParameters parameters = new PKIXParameters(anchors);
~~~

Hoặc từ `KeyStore` chứa các trusted certificate entry:

~~~java
PKIXParameters parameters = new PKIXParameters(trustStore);
~~~

Một số thuộc tính quan trọng:

| Phương thức | Mục đích |
|---|---|
| `getTrustAnchors()` / `setTrustAnchors(...)` | Đọc hoặc thay đổi tập trust anchor |
| `setDate(...)` | Chỉ định thời điểm dùng để kiểm tra validity |
| `setRevocationEnabled(...)` | Bật/tắt kiểm tra thu hồi |
| `setInitialPolicies(...)` | Đặt tập certificate policy OID được chấp nhận |
| `setCertStores(...)` | Cung cấp nguồn certificate/CRL cho provider |
| `setTargetCertConstraints(...)` | Giới hạn certificate đích |

Revocation checking được bật mặc định trong `PKIXParameters`. Nếu tắt, ứng dụng sẽ không phát hiện certificate đã bị thu hồi qua cơ chế kiểm tra đó. Chỉ tắt trong fixture hoặc tình huống có chính sách riêng đã được đánh giá; môi trường thật cần cấu hình CRL/OCSP phù hợp.

### 3.3. CertPathValidator

`CertPathValidator` thực hiện xác minh:

~~~java
CertPathValidator validator =
        CertPathValidator.getInstance("PKIX");

CertPathValidatorResult result =
        validator.validate(certPath, parameters);
~~~

Mọi Java platform implementation đều phải hỗ trợ thuật toán `PKIX`. Nếu path không hợp lệ, `validate` ném `CertPathValidatorException`. Exception cung cấp thông tin về lỗi và index certificate gây lỗi nếu provider xác định được.

### 3.4. TrustManagerFactory và SSLContext

Trong TLS, thường không tự gọi `CertPathValidator` cho từng socket. JSSE tạo trust manager để xác minh certificate của peer:

~~~java
TrustManagerFactory tmf =
        TrustManagerFactory.getInstance("PKIX");

tmf.init(trustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, tmf.getTrustManagers(), null);
~~~

`TrustManagerFactory` nhận trust material từ `KeyStore` và tạo một hoặc nhiều `TrustManager`. `SSLContext` sử dụng trust manager đó khi thực hiện TLS handshake.

Khi dùng `TrustManagerFactory.init(KeyStore)` trong SunJSSE, các PKIX parameter mặc định được dùng nhưng revocation checking bị tắt. Nếu cần kiểm tra thu hồi, phải cấu hình cơ chế phù hợp, ví dụ dùng `CertPathTrustManagerParameters` với `PKIXBuilderParameters` đã bật revocation và có nguồn CRL/OCSP.

## 4. Truststore, keystore và cacerts

### 4.1. Keystore và truststore là vai trò, không phải định dạng file

Cả keystore và truststore đều có thể là `KeyStore` với các entry như:

| Entry type | Nội dung | Công dụng |
|---|---|---|
| `PrivateKeyEntry` | Private key và certificate chain tương ứng | Chứng minh danh tính của chính ứng dụng/server |
| `TrustedCertificateEntry` | Một certificate được ứng dụng tin cậy | Cung cấp trust anchor hoặc trust material để xác minh peer |
| `SecretKeyEntry` | Secret key đối xứng | Mã hóa/giải mã dữ liệu |

Một keystore thường chứa private key và certificate của chính ứng dụng. Truststore thường chứa các trusted certificate entry của CA mà ứng dụng chấp nhận. Cùng một file có thể chứa nhiều loại entry, nhưng tách riêng hai vai trò thường dễ quản lý và giảm rủi ro.

### 4.2. cacerts của JDK

JDK cung cấp truststore tên `cacerts` trong thư mục:

~~~text
JAVA_HOME/lib/security/cacerts
~~~

Store này chứa một tập root CA mặc định. Có thể liệt kê bằng:

~~~bash
keytool -list -cacerts
~~~

Không nên coi mọi certificate có sẵn trong `cacerts` là phù hợp cho mọi ứng dụng. Quản trị viên cần kiểm tra và duy trì tập CA mà tổ chức thực sự tin cậy.

### 4.3. JSSE chọn truststore mặc định như thế nào?

Trong implementation SunJSSE của Oracle JDK, khi tạo default trust manager mà không truyền KeyStore, thứ tự tìm trust material là:

1. Nếu có system property `javax.net.ssl.trustStore`, dùng file được chỉ định.
2. Nếu property không được đặt, tìm `JAVA_HOME/lib/security/jssecacerts`.
3. Nếu không có `jssecacerts`, tìm `JAVA_HOME/lib/security/cacerts`.
4. Nếu không tìm được store nào, không có truststore mặc định.

Một trường hợp dễ gây lỗi: nếu `javax.net.ssl.trustStore` đã được đặt nhưng đường dẫn chỉ tới file không tồn tại, SunJSSE tạo trust manager với keystore rỗng. Ứng dụng có thể báo `PKIX path building failed` dù JDK vẫn có `cacerts`.

Các system property thường dùng:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/opt/app/conf/truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=changeit \
  -jar app.jar
~~~

Ví dụ trên chỉ minh họa cách cấu hình. Không đưa mật khẩu thật vào command line hoặc log CI; dùng secret manager, protected file, console prompt hoặc cơ chế credential phù hợp môi trường triển khai.

Một truststore tùy chỉnh thường thay thế nguồn trust mặc định của SSLContext đó. Nếu ứng dụng cần đồng thời tin CA công khai và CA nội bộ, phải chủ động xây dựng truststore chứa cả hai tập hoặc triển khai cơ chế kết hợp trust manager đã được kiểm thử.

## 5. Thêm một trust anchor bằng keytool

`keytool` quản lý key pair, certificate và keystore. Khi thêm root CA vào truststore, chỉ import certificate chứa public key; không import private key của CA.

### 5.1. Kiểm tra certificate trước khi tin cậy

Giả sử nhận được file `company-root.cer` từ bộ phận bảo mật hoặc CA:

~~~bash
keytool -printcert -file company-root.cer -v
~~~

Kiểm tra Subject, Issuer, thời hạn và SHA-256 fingerprint. So sánh fingerprint với giá trị nhận qua một kênh độc lập, đáng tin cậy (chẳng hạn portal CA chính thức hoặc người quản trị được xác thực).

Việc certificate tự ký và có tên Subject giống CA mong đợi không đủ để xác minh tính xác thực của public key.

### 5.2. Import vào truststore riêng

~~~bash
keytool -importcert \
  -alias company-root \
  -file company-root.cer \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

Khi keytool hiển thị certificate và hỏi có tin cậy hay không, chỉ xác nhận sau khi fingerprint đã được kiểm tra. Không dùng `-noprompt` để bỏ qua bước xác nhận nếu chưa có quy trình kiểm tra fingerprint tự động đáng tin cậy.

Kiểm tra entry sau khi import:

~~~bash
keytool -list -v \
  -alias company-root \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

Entry root CA cần là `trustedCertEntry`. Truststore không cần chứa private key của root CA.

### 5.3. Import vào cacerts

Nếu tổ chức quyết định CA nội bộ phải được tin cậy rộng trên JDK, quản trị viên có thể thêm certificate vào `cacerts`:

~~~bash
keytool -importcert \
  -alias company-root \
  -file company-root.cer \
  -cacerts
~~~

Đây là thay đổi ảnh hưởng tới nhiều ứng dụng dùng JDK đó. Thường nên ưu tiên truststore riêng cho từng ứng dụng hoặc nhóm ứng dụng để giới hạn phạm vi trust. Chỉ sửa `cacerts` khi chính sách vận hành yêu cầu và có quy trình quản lý thay đổi.

## 6. Thực hành: tạo CA, ký leaf certificate và xác minh path

Thực hành này tạo một root CA dùng riêng cho môi trường lab, ký một leaf certificate có SAN DNS, rồi xác minh leaf bằng Java PKIX. Không dùng CA lab hoặc private key demo để phát hành certificate thật.

### 6.1. Tạo root CA

Tạo keystore PKCS12 chứa private key của CA và certificate tự ký có quyền ký certificate:

~~~bash
keytool -genkeypair \
  -alias root \
  -dname "CN=Example Test Root CA,O=Example,C=US" \
  -ext bc=ca:true \
  -ext ku=keyCertSign,cRLSign \
  -keyalg RSA \
  -keysize 2048 \
  -sigalg SHA256withRSA \
  -validity 3650 \
  -keystore root.p12 \
  -storetype PKCS12
~~~

Keytool sẽ yêu cầu mật khẩu. Trong thực tế, bảo vệ private key của root CA chặt chẽ và không đặt keystore root CA trên máy chủ ứng dụng.

Xuất public certificate:

~~~bash
keytool -exportcert \
  -alias root \
  -keystore root.p12 \
  -storetype PKCS12 \
  -file root.cer
~~~

Kiểm tra certificate và fingerprint:

~~~bash
keytool -printcert -file root.cer -v
~~~

### 6.2. Tạo key pair và CSR cho server

Tạo keystore chứa private key của server:

~~~bash
keytool -genkeypair \
  -alias service \
  -dname "CN=service.example.test" \
  -keyalg RSA \
  -keysize 2048 \
  -sigalg SHA256withRSA \
  -validity 365 \
  -keystore service.p12 \
  -storetype PKCS12
~~~

Tạo Certificate Signing Request:

~~~bash
keytool -certreq \
  -alias service \
  -keystore service.p12 \
  -storetype PKCS12 \
  -file service.csr
~~~

### 6.3. Dùng root CA ký certificate cho server

~~~bash
keytool -gencert \
  -alias root \
  -keystore root.p12 \
  -storetype PKCS12 \
  -infile service.csr \
  -outfile service-signed.pem \
  -rfc \
  -validity 90 \
  -ext bc=ca:false \
  -ext ku=digitalSignature,keyEncipherment \
  -ext eku=serverAuth \
  -ext san=dns:service.example.test
~~~

Certificate leaf được cấp có SAN DNS, EKU serverAuth và không có quyền ký CA.

Import certificate root vào keystore của server để keytool có thể xây dựng chain khi nhận certificate reply:

~~~bash
keytool -importcert \
  -alias example-root \
  -file root.cer \
  -keystore service.p12 \
  -storetype PKCS12
~~~

Sau đó import certificate đã được CA ký vào đúng alias giữ private key:

~~~bash
keytool -importcert \
  -alias service \
  -file service-signed.pem \
  -keystore service.p12 \
  -storetype PKCS12
~~~

Keytool ghép certificate reply với private key đã có và cập nhật chain của entry `service`. Kiểm tra chain:

~~~bash
keytool -list -v \
  -alias service \
  -keystore service.p12 \
  -storetype PKCS12
~~~

### 6.4. Tạo truststore chỉ chứa root CA

Tạo một truststore riêng cho client:

~~~bash
keytool -importcert \
  -alias example-root \
  -file root.cer \
  -keystore truststore.p12 \
  -storetype PKCS12
~~~

Xác minh fingerprint trước khi chấp nhận import. Kiểm tra lại:

~~~bash
keytool -list -v \
  -keystore truststore.p12 \
  -storetype PKCS12
~~~

Trong truststore chỉ có public certificate của CA. Private key root vẫn nằm trong keystore của CA và không được phân phối cho client.

Xuất leaf certificate để đưa vào ví dụ Java:

~~~bash
keytool -exportcert \
  -alias service \
  -keystore service.p12 \
  -storetype PKCS12 \
  -file service.cer
~~~

## 7. Chương trình Java 17+ xác minh bằng TrustAnchor

Tạo file `TrustAnchorDemo.java`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Set;

public final class TrustAnchorDemo {
    public static void main(String[] args) throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        X509Certificate root;
        try (var input = Files.newInputStream(Path.of(args[0]))) {
            root = (X509Certificate) factory.generateCertificate(input);
        }

        X509Certificate leaf;
        try (var input = Files.newInputStream(Path.of(args[1]))) {
            leaf = (X509Certificate) factory.generateCertificate(input);
        }

        // X.509 CertPath starts with the target; the trust anchor is separate.
        CertPath path = factory.generateCertPath(List.of(leaf));
        TrustAnchor anchor = new TrustAnchor(root, null);

        PKIXParameters parameters =
                new PKIXParameters(Set.of(anchor));

        // This isolated demo has no CRL/OCSP source.
        // Production validation should configure revocation checking.
        parameters.setRevocationEnabled(false);

        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");

        PKIXCertPathValidatorResult result =
                (PKIXCertPathValidatorResult)
                        validator.validate(path, parameters);

        System.out.println("Trust anchor: "
                + root.getSubjectX500Principal().getName());
        System.out.println("Validated target: "
                + leaf.getSubjectX500Principal().getName());
        System.out.println("Public key algorithm: "
                + result.getPublicKey().getAlgorithm());
        System.out.println("Certificate path length: "
                + path.getCertificates().size());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa `TrustAnchorDemo.java`, `root.cer` và `service.cer`:

~~~bash
javac --release 17 TrustAnchorDemo.java
java TrustAnchorDemo root.cer service.cer
~~~

Stdout chính xác của fixture đã tạo ở phần trước:

~~~text
Trust anchor: CN=Example Test Root CA,O=Example,C=US
Validated target: CN=service.example.test
Public key algorithm: RSA
Certificate path length: 1
~~~

Ví dụ này chứng minh leaf certificate được xác minh bằng root CA được truyền riêng dưới dạng `TrustAnchor`. Path chỉ có một certificate leaf; root CA không nằm trong `CertPath`.

Trong chuỗi có intermediate CA, đưa leaf trước, sau đó là intermediate certificate theo thứ tự issuer. Root anchor vẫn được truyền riêng. Nếu path chưa được dựng sẵn, hãy dùng `CertPathBuilder` thay vì tự giả định rằng danh sách certificate bất kỳ đã tạo thành path hợp lệ.

### 7.1. Dùng KeyStore làm nguồn trust anchor

Thay vì tạo `TrustAnchor` trực tiếp, có thể nạp truststore chứa trusted certificate entry:

~~~java
KeyStore anchors = KeyStore.getInstance("PKCS12");
try (var input = Files.newInputStream(Path.of("truststore.p12"))) {
    anchors.load(input, password);
}

PKIXParameters parameters = new PKIXParameters(anchors);
~~~

Các trusted certificate entry trong `KeyStore` được dùng làm most-trusted CA. Trong chương trình thật, lấy password từ console hoặc secret provider và đóng/giải phóng tài nguyên đúng cách.

## 8. Dùng truststore trong JSSE/TLS

Một client TLS thường dùng truststore để tạo trust manager:

~~~java
KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (var input = Files.newInputStream(Path.of("truststore.p12"))) {
    trustStore.load(input, password);
}

TrustManagerFactory tmf =
        TrustManagerFactory.getInstance("PKIX");
tmf.init(trustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, tmf.getTrustManagers(), null);
~~~

`TrustManagerFactory` dùng trusted certificate entry trong store để tạo trust manager. Khi client thực hiện TLS handshake, trust manager đánh giá certificate chain do peer gửi dựa trên trust material và chính sách PKIX.

Có thể dùng `SSLContext` để tạo socket factory hoặc HTTP client. Đảm bảo ứng dụng sử dụng đúng context đã được khởi tạo với trust manager mong muốn.

### 8.1. Path validation không thay thế hostname verification

Xác minh certificate path trả lời câu hỏi: certificate có được phát hành qua một CA chain kết thúc ở anchor mà ứng dụng tin cậy hay không?

Hostname verification trả lời câu hỏi khác: certificate đích có xác thực đúng hostname mà ứng dụng định kết nối hay không?

Một certificate có chain hợp lệ vẫn có thể thuộc về hostname khác. HTTPS yêu cầu endpoint identification; `HttpsURLConnection` thực hiện hostname verification mặc định. Với raw `SSLSocket` hoặc `SSLEngine`, ứng dụng phải bật endpoint identification hoặc tự xác minh danh tính peer.

Ví dụ với `SSLSocket`:

~~~java
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
socket.startHandshake();
~~~

Không bỏ qua hostname verification và không dùng trust-all `X509TrustManager` trong production. Cách làm đó biến mọi certificate thành có thể chấp nhận và loại bỏ ý nghĩa của trust anchor.

## 9. Revocation, thời hạn và chính sách trust

### 9.1. Certificate hết hạn hoặc bị thu hồi

Trust anchor hợp lệ không khiến mọi certificate do CA đó ký luôn được chấp nhận. Certificate đích và intermediate vẫn phải thỏa các điều kiện path validation như validity, signature và constraints.

Certificate có thể bị thu hồi trước ngày hết hạn. PKIX hỗ trợ kiểm tra trạng thái bằng CRL hoặc OCSP, nhưng phải cấu hình cơ chế và nguồn dữ liệu tương ứng.

- CRL là danh sách certificate bị thu hồi do CA phát hành.
- OCSP cho phép hỏi trạng thái certificate qua responder.
- OCSP stapling cho phép server gửi kèm phản hồi trạng thái trong TLS.

Trong Java, có thể bật revocation trên `PKIXParameters` hoặc dùng `PKIXRevocationChecker` để cấu hình chi tiết. Với SunJSSE, `TrustManagerFactory.init(KeyStore)` mặc định tắt revocation checking; muốn bật cần cấu hình theo hướng dẫn JSSE của JDK đang triển khai.

### 9.2. Một trust anchor có thể bị giới hạn

Không nên hiểu việc tin một root CA là chấp nhận mọi certificate mà CA đó có thể phát hành trong mọi ứng dụng. Chính sách có thể giới hạn:

- Certificate policy OID được chấp nhận.
- Tên DNS hoặc namespace được phép.
- Loại mục đích sử dụng qua Key Usage và Extended Key Usage.
- Thuật toán chữ ký và kích thước key được phép.
- Thời gian hiệu lực và trạng thái thu hồi.
- Những intermediate CA được phép xuất hiện trong path.

PKIX có các tham số policy và constraints; một ứng dụng có thể dùng tập trust anchor riêng để giới hạn phạm vi tin cậy cho dịch vụ đó.

### 9.3. Trust anchor rotation

Khi CA sắp hết hạn hoặc được thay thế, hãy lập kế hoạch chuyển đổi:

1. Xác minh root CA mới qua kênh độc lập.
2. Phân phối root mới tới truststore của client trước khi server chuyển certificate.
3. Trong giai đoạn chuyển tiếp, giữ cả anchor cũ và mới nếu chính sách cho phép.
4. Thay certificate leaf/intermediate và kiểm thử path trên tất cả runtime target.
5. Theo dõi client đã cập nhật; chỉ xóa anchor cũ khi không còn path hợp lệ nào phụ thuộc vào nó.
6. Lưu fingerprint, thời điểm thêm/xóa và người phê duyệt thay đổi.

Không thay thế truststore toàn cục trên máy production bằng một file không được kiểm tra. Không xóa root cũ trước khi client đã nhận root mới.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `PKIX path building failed` | Không tìm thấy path tới trust anchor | Kiểm tra truststore, root/intermediate và certificate server gửi |
| `unable to find valid certification path` | Root CA chưa được tin cậy hoặc thiếu intermediate | Xem chain bằng `keytool -list -v` và kiểm tra tập anchor |
| `No subject alternative DNS name matching...` | Hostname không khớp SAN | Kiểm tra DNS/IP SAN và hostname client đang kết nối |
| Certificate bị báo expired hoặc not yet valid | Thời gian hệ thống sai hoặc certificate hết hạn | Kiểm tra thời gian máy, `Not Before` và `Not After` |
| Import certificate nhưng vẫn không trust | Import nhầm vào keystore của server thay vì truststore của client | Xác định `javax.net.ssl.trustStore` hoặc KeyStore truyền vào TrustManagerFactory |
| Root certificate bị từ chối khi import | Fingerprint không được xác minh hoặc chain không dựng được | Kiểm tra fingerprint qua kênh độc lập và CA chain |
| Có `trustStore` property nhưng vẫn báo không tìm thấy CA | Đường dẫn file sai hoặc file không tồn tại | Kiểm tra chính xác path, type và quyền đọc; SunJSSE có thể dùng store rỗng |
| Client không phát hiện certificate đã bị thu hồi | Revocation checking chưa bật hoặc không có CRL/OCSP source | Kiểm tra PKIX parameters và cấu hình responder/distribution point |
| Certificate chain hợp lệ nhưng TLS vẫn thất bại | Lỗi protocol, cipher, EKU, hostname hoặc policy | Xem exception gốc và bật JSSE debug trong môi trường kiểm thử |
| Một app tin CA nhưng app khác không tin | Mỗi app dùng truststore hoặc SSLContext khác nhau | Kiểm tra system property và TrustManagerFactory của từng app |

## 11. Checklist quản lý trust anchor

- [ ] Chỉ chọn CA mà tổ chức đã xác minh và phê duyệt.
- [ ] Kiểm tra SHA-256 fingerprint qua kênh độc lập trước khi import.
- [ ] Dùng truststore riêng cho ứng dụng khi cần giới hạn phạm vi tin cậy.
- [ ] Không phân phối private key của root CA cho ứng dụng client.
- [ ] Kiểm tra Subject, Issuer, Basic Constraints, Key Usage, SAN và thời hạn certificate.
- [ ] Bảo đảm intermediate certificate cần thiết có sẵn để xây dựng path.
- [ ] Tách path validation, revocation checking và hostname verification thành các bước kiểm soát rõ ràng.
- [ ] Không dùng trust-all trust manager hoặc tắt hostname verification.
- [ ] Lưu lại fingerprint, alias, nguồn phát hành và lịch sử thay đổi truststore.
- [ ] Lập kế hoạch rotation trước khi CA hoặc certificate hết hạn.
- [ ] Kiểm thử lại trên đúng JDK/provider và cấu hình runtime production.

## 12. Ghi nhớ

Trust anchor là CA được chọn làm điểm tin cậy cho quá trình xác minh certification path. Java biểu diễn nó bằng `TrustAnchor`; `PKIXParameters` mang tập anchor và chính sách xác minh; `CertPathValidator` kiểm tra path. Trong TLS, trust material thường được lưu trong truststore và nạp qua `TrustManagerFactory` vào `SSLContext`.

Niềm tin không đến từ việc certificate tự ký hay có tên giống CA mong muốn. Nó đến từ quyết định trust được xác minh và quản lý an toàn. Luôn kiểm tra fingerprint trước khi import, bảo vệ private key CA, quản lý revocation và thực hiện hostname verification riêng khi kết nối TLS.

Tài liệu tham khảo:

- [RFC 5280 — Internet X.509 Public Key Infrastructure: Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html)
- [TrustAnchor API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/TrustAnchor.html)
- [CertPathValidator API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathValidator.html)
- [Java PKI Programmer's Guide — Java SE 21](https://docs.oracle.com/en/java/javase/21/security/java-pki-programmers-guide.html)
- [JSSE Reference Guide — Java SE 21](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html)
- [The keytool Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)