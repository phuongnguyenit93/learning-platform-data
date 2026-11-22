# CA gốc, chuỗi chứng thư và điểm neo tin cậy (Java 10+)

## 1. Mục tiêu bài học

Khi một ứng dụng Java kết nối bằng **HTTPS/TLS** đến dịch vụ khác, máy chủ thường gửi một **chứng thư X.509 của chính máy chủ** và một số **chứng thư CA trung gian**. Java không tin máy chủ chỉ vì những chứng thư đó được gửi qua mạng hoặc vì chúng có chữ ký số. JVM cần tìm được **đường chứng nhận (*certification path*) hợp lệ** dẫn đến **điểm neo tin cậy (*trust anchor*)** mà ứng dụng đã chấp nhận từ trước.

Ba khái niệm chủ đạo:

- **Root CA / CA gốc:** một Certification Authority ở đỉnh của một hệ phân cấp PKI. Chứng thư root thường **tự ký** (*self-signed*) và giữ khóa công khai của CA gốc.
- **Certificate chain / chuỗi chứng thư:** các chứng thư có quan hệ issuer–subject, chữ ký và các ràng buộc, ví dụ **server → intermediate CA → root CA**.
- **Trust anchor / điểm neo tin cậy:** một **quyết định tin cậy cục bộ**, thường biểu diễn bằng chứng thư CA tin cậy hoặc danh tính CA + public key trong cấu hình trình xác thực. Trust anchor **không nhất thiết là một chứng thư tự ký**.

**Kết luận quan trọng:** *Có chuỗi chứng thư được ký đúng không đồng nghĩa có điểm neo được tin cậy; chứng thư tự ký không tự biến thành trusted; và path validation không thay thế việc kiểm tra hostname của HTTPS.*

Bài giải thích cơ chế PKIX/X.509, truststore của Java, thuật toán kiểm tra chuỗi và ví dụ Java 17+ chạy độc lập bằng JDK `keytool`. Nội dung giữ lại những kiến thức **còn phù hợp với Java hiện đại**, đặc biệt Java SE 26, không hướng dẫn tắt certificate validation hay bật các giao thức TLS legacy.

## 2. Mô hình ba tầng của một hệ PKI

Một ví dụ dễ hình dung:

~~~text
          Trust store / policy của Java client
                      |
                      v
             [Trust anchor: ROOT CA]
              Subject: Demo Root CA
              Public key: K_ROOT
                      |
                 ký / cấp cho
                      v
              [INTERMEDIATE CA]
              Issuer: Demo Root CA
              Subject: Demo Intermediate CA
              Public key: K_INTERMEDIATE
                      |
                 ký / cấp cho
                      v
              [SERVER CERTIFICATE]
              Issuer: Demo Intermediate CA
              Subject: api.example.test
              SAN: DNS:api.example.test
              Public key: K_SERVER
                      |
                      v
       TLS server chứng minh có private key tương ứng
~~~

Trong sơ đồ, **server không sở hữu private key của Root CA**. Root CA sử dụng private key của mình để ký chứng thư của intermediate. Intermediate dùng private key của nó để ký chứng thư server. Server giữ private key tương ứng với **public key trong leaf certificate** để tham gia xác thực TLS.

Các chứng thư chủ yếu chứa **public key**, danh tính, thời hạn, chính sách, extensions và chữ ký của bên cấp. **Không gửi private key của CA hoặc server trong certificate chain**.

### Những vai trò khác nhau

| Thành phần | Vai trò | Thường nằm ở đâu? |
| --- | --- | --- |
| Root CA certificate | Biểu diễn CA gốc và public key của nó | Truststore hoặc nguồn tin cậy cục bộ; không nhất thiết được server gửi |
| Intermediate CA certificate | Nối chuỗi chữ ký từ leaf đến root | Server có thể gửi; cũng có thể được tìm từ nguồn khác theo cơ chế path building |
| Leaf/end-entity certificate | Nhận diện dịch vụ/người dùng cụ thể | Server gửi trong TLS Certificate message hoặc client gửi trong mTLS |
| Private key của server | Chứng minh quyền sử dụng danh tính gắn với leaf certificate | Keystore/HSM/secret store phía server; **không** công khai |
| Trust anchor | Điểm dừng của quyết định tin cậy khi PKIX validation | Truststore/cấu hình `PKIXParameters`/trust manager |
| TrustManager | Đánh giá peer certificate chain theo trust policy | JSSE phía Java client/server |
| KeyManager | Chọn khóa/chứng thư **của chính phía mình** | JSSE khi client/server trình chứng thư của mình |

**Keystore và truststore** cùng có thể dùng API `KeyStore`, nhưng **chức năng vận hành khác nhau**: keystore phía server thường quản lý private key + certificate chain; truststore phía client chứa các certificate entries được tin để xây dựng trust anchors.

## 3. Root CA là gì và tại sao thường tự ký?

Root CA là **đầu mối cấp cao** trong một hệ CA phân cấp. Trong một root certificate tự ký thường có:

~~~text
Subject = CN=Example Root CA
Issuer  = CN=Example Root CA
Public key = K_ROOT
Signature được tạo bởi private key tương ứng với K_ROOT
Basic Constraints = CA:TRUE
Key Usage có thể bao gồm keyCertSign, cRLSign
~~~

**Self-issued** nghĩa là tên `Subject` và `Issuer` bằng nhau; **self-signed** còn cần chữ ký thực sự kiểm chứng được bằng public key được chứa trong chứng thư. Do đó:

~~~java
boolean selfIssued = root.getSubjectX500Principal()
        .equals(root.getIssuerX500Principal());
root.verify(root.getPublicKey()); // kiểm tra chữ ký tự ký
~~~

Hai câu lệnh này có thể kiểm tra tính **self-issued/self-signature** của một certificate được đọc vào.

**Nhưng vẫn chưa chứng minh root đáng tin.** Kẻ tấn công có thể tự tạo một certificate tự ký hoàn toàn hợp lệ về toán học. Điều làm root trở thành điểm tin cậy là **ứng dụng/OS/JDK/tổ chức đã chấp nhận public key đó bằng một kênh hoặc chính sách tin cậy độc lập**.

Với public CA, danh sách tin cậy thường được duy trì qua chương trình root CA và các bản cập nhật phần mềm. Với private PKI nội bộ, quản trị viên phân phối root public certificate theo cơ chế đáng tin và kiểm tra fingerprint từ nguồn độc lập.

### Vì sao Root CA thường không trực tiếp ký từng server?

Sử dụng intermediate CAs giúp tổ chức:

- Giữ root private key trong môi trường bảo vệ mạnh hơn, ít phải dùng.
- Phân quyền cấp chứng thư cho các intermediate riêng.
- Hạn chế phạm vi hoạt động/loại chứng thư qua `BasicConstraints`, `keyUsage`, `nameConstraints` và policies.
- Xoay vòng intermediate mà không nhất thiết thay mọi root ở client.
- Thu hồi hoặc thay intermediate trong các tình huống cần thiết.

Root CA **có thể** trực tiếp ký end-entity certificates về mặt mô hình, nhưng trong Web PKI thông dụng, việc dùng intermediates giúp vận hành và bảo vệ khóa tốt hơn.

## 4. Trust anchor không đồng nghĩa root certificate tự ký

Theo API Java SE 26, `java.security.cert.TrustAnchor` đại diện một **most-trusted CA** dùng để xác thực chứng thư X.509. Nó có thể được cấu hình bằng:

~~~java
new TrustAnchor(x509TrustedCertificate, null);
~~~

hoặc bằng **CA distinguished name + public key**:

~~~java
new TrustAnchor(caPrincipal, caPublicKey, null);
~~~

Các constructor này là **mảnh mã minh họa**, không phải chương trình độc lập.

Từ đó có ba kết luận:

1. Trust anchor có thể được biểu diễn bằng **một X.509 certificate** hoặc trực tiếp bởi **CA name và public key**.
2. Trust anchor **không bắt buộc** là một certificate tự ký; một CA trung gian cũng có thể được một ứng dụng chọn làm trust anchor nếu chính sách yêu cầu.
3. **Tin cậy là đầu vào của quá trình validation**, không phải thứ được suy ra chỉ từ khả năng một chứng thư tự xác thực chữ ký của nó.

**Cảnh báo bảo mật:** đưa một intermediate CA hoặc leaf certificate vào truststore dưới dạng trusted certificate entry sẽ thay đổi ranh giới tin cậy. Đừng làm vậy tùy tiện chỉ để sửa lỗi TLS, vì có thể bỏ qua các kiểm tra/quan hệ mà bạn tưởng đang được áp dụng như khi đi đầy đủ chuỗi đến root. Xác định đúng CA và phạm vi tin cậy trước khi import.

### Chứng thư của trust anchor có cần nằm trong CertPath không?

**Không.** Theo `CertPath` Javadoc của Java SE 26, khi biểu diễn đường X.509 theo quy ước, danh sách certificate bắt đầu ở **target/leaf** và đi về một certificate do trust anchor cấp; **chính trust anchor không nằm trong danh sách CertPath**.

Ví dụ:

~~~text
CertPath certificates = [leaf, intermediate]
TrustAnchor           = root

PKIX validation:
  leaf -> intermediate -> (root public key từ TrustAnchor)
~~~

Một TLS server đôi khi gửi cả root certificate, nhưng Java **không vì server gửi root mà tự tin root đó**. Trust anchor phải đến từ **cấu hình tin cậy** của client.

## 5. Chứng thư trung gian nối chuỗi như thế nào?

Giả sử:

~~~text
Leaf:
  Subject = api.example.test
  Issuer  = Demo Intermediate CA
  Chữ ký bởi private key của Intermediate

Intermediate:
  Subject = Demo Intermediate CA
  Issuer  = Demo Root CA
  Chữ ký bởi private key của Root

Root:
  Subject = Demo Root CA
  Issuer  = Demo Root CA
  Public key đã được client tin cậy
~~~

Để kiểm tra các chữ ký bằng Java:

~~~java
leaf.verify(intermediate.getPublicKey());
intermediate.verify(root.getPublicKey());
~~~

**Điều này chỉ kiểm tra chữ ký của hai chứng thư** bằng các khóa công khai được cung cấp. Nó **chưa tự chứng minh**:

- Hai bên CA thực sự là trusted anchors.
- Chứng thư đang trong thời hạn.
- Intermediate được phép cấp chứng thư (`BasicConstraints`, `keyUsage`, `pathLenConstraint`).
- Chứng thư đã bị thu hồi hay chưa.
- Thuật toán và độ dài khóa đáp ứng security policies hiện hành.
- Leaf dùng đúng mục đích TLS server.
- DNS hostname thực sự khớp SAN.

Đó là lý do dùng **PKIX path validation** thay vì tự viết vài lần `verify` rồi chấp nhận kết nối.

### Subject và Issuer bằng nhau đã đủ nối chuỗi?

Không. Tên `Issuer` của leaf phải liên quan đến `Subject` của intermediate, **nhưng chữ ký cũng phải kiểm chứng được bằng public key chính xác** và các ràng buộc X.509 phải hợp lệ. Hai CA có thể có tên DN tương tự/trùng nhưng **khóa khác nhau**, ví dụ khi xoay khóa hoặc cross-signing.

Các extensions `Subject Key Identifier` (SKI) và `Authority Key Identifier` (AKI) hỗ trợ nhận diện/candidate selection. Chúng **không thay thế việc kiểm tra chữ ký số và chính sách PKIX**.

## 6. Chuỗi chứng thư: từ nhận diện đến tin cậy

Một certification path được xây dựng/kiểm tra qua các nhóm điều kiện chủ yếu:

1. **Target certificate** được lựa chọn đúng để xác thực service/client mong muốn.
2. **Issuer chain** liên tục về tên và khóa phù hợp; chữ ký từng certificate hợp lệ.
3. **Validity interval** của các certificate trong path được xét tại thời điểm validation.
4. **CA role và hạn chế cấp**: `BasicConstraints: CA:TRUE`, `keyCertSign`, path length, name constraints, policies.
5. **Signature/public key algorithms** không bị policy của JDK từ chối (ví dụ qua `jdk.certpath.disabledAlgorithms`).
6. **Revocation** được kiểm tra nếu đúng chính sách/cấu hình; có thể dùng OCSP/CRL theo khả năng.
7. **Kết thúc tại TrustAnchor được chấp nhận**.
8. Với **HTTPS**, còn phải kiểm tra **DNS/IP identity** đúng endpoint mong muốn; việc chỉ tìm được CA đáng tin **không có nghĩa hostname đã khớp**.

### Validating khác building

- **CertPathValidator**: kiểm tra một **đường chứng thư đã được cung cấp**. Nếu thiếu intermediate trong danh sách, `CertPathValidator` thường không tự quyết định tìm thêm intermediate cho bạn.
- **CertPathBuilder**: có thể **tìm và xây dựng** một path hợp lệ từ nguồn chứng thư (`CertStore`, nguồn provider cấu hình, v.v.) tới trust anchors.
- **TrustManager trong JSSE**: nhận peer certificate chain chưa đầy đủ hoặc đầy đủ và thực hiện xây/kiểm tra theo chính sách/provider và các nguồn hỗ trợ.

**Không nên trông đợi client Java luôn tự tải intermediate từ đường AIA URL** trong mọi JDK và mọi cấu hình mạng. Server được cấu hình đúng nên gửi **leaf và các intermediates cần thiết** theo thứ tự hợp lý, thay vì trông cậy client tự sửa một chuỗi thiếu.

## 7. Các extension X.509 cần biết

| Extension | Ý nghĩa | Rủi ro khi sai |
| --- | --- | --- |
| `BasicConstraints` | Phân biệt CA với end-entity, có thể giới hạn độ sâu CA | Intermediate không được phép ký chứng thư |
| `KeyUsage` | Mục đích sử dụng public key: `keyCertSign`, `digitalSignature`, v.v. | Khóa được dùng trái mục đích |
| `ExtendedKeyUsage` (EKU) | Mục đích mở rộng, ví dụ `serverAuth` hoặc `clientAuth` | Leaf không phù hợp mục đích TLS |
| `SubjectAlternativeName` (SAN) | Danh tính DNS/IP của endpoint | Hostname/IP không khớp |
| `NameConstraints` | Giới hạn tên mà CA được phép cấp | Path có tên ngoài phạm vi |
| `CertificatePolicies` | Các chính sách cấp/xác thực | Không thỏa chính sách yêu cầu |
| `AuthorityKeyIdentifier` / `SubjectKeyIdentifier` | Hỗ trợ liên kết issuer/public key | Chọn sai intermediate candidate |
| `CRLDistributionPoints` / `AuthorityInfoAccess` | Điểm truy cập thông tin thu hồi/issuer | Có thể không lấy được dữ liệu kiểm tra |

**Một intermediate CA** cần `BasicConstraints CA:TRUE`, và nếu `KeyUsage` hiện diện phải cho phép `keyCertSign` để có thể ký certificates. Với intermediate `pathLenConstraint=0`, nó thường chỉ được cấp **end-entity** mà không thêm một intermediate CA **không self-issued** ở dưới. Đây là giới hạn path length theo RFC 5280, không đơn thuần là “số certificate tối đa” kể cả root/leaf.

**Một server leaf** thông thường có `BasicConstraints CA:FALSE`, SAN chứa đúng tên dịch vụ và EKU `serverAuth` theo cấu hình cấp chứng thư. Không dùng certificate chỉ có `clientAuth` để xác thực TLS server.

## 8. Truststore và keystore trong Java

**`KeyStore`** là API biểu diễn kho khóa/chứng thư; **truststore** là cách sử dụng KeyStore để cung cấp những trusted certificate entries cho TrustManager.

| Kho | Chứa gì? | Dùng cho |
| --- | --- | --- |
| Server keystore | Private key + chain tương ứng, có thể có thêm certificates | Server trình chứng thư và chứng minh sở hữu private key |
| Client keystore (mTLS) | Private key + chain của client | Client tự xác thực với server |
| Client truststore | Các certificates/CA mà client đã tin cậy | Client kiểm tra server certificate path |
| Server truststore (mTLS) | Các CA/certificates được chấp nhận cho client auth | Server kiểm tra client certificate path |
| `cacerts` của JDK | Tập root/trust certificates theo distribution/release | Nguồn mặc định của SunJSSE nếu không override |

**Không lẫn `javax.net.ssl.keyStore` với `javax.net.ssl.trustStore`.** Cái đầu là thông tin nhận diện/khóa của **chính mình**; cái sau là danh sách **bên kia được tin cậy**.

### Default truststore lookup trong SunJSSE

Theo JSSE Security Developer's Guide Java SE 26, khi không đặt `javax.net.ssl.trustStore`:

1. Nếu tồn tại `<java-home>/lib/security/jssecacerts` thì dùng file này.
2. Nếu không, dùng `<java-home>/lib/security/cacerts`.
3. Nếu không có nguồn phù hợp, kết quả có thể là truststore rỗng, tùy cách khởi tạo/provider.

Nếu **đã đặt `javax.net.ssl.trustStore`** nhưng file chỉ định **không tồn tại**, implementation SunJSSE không tự quay về `cacerts` thông thường: cấu hình tin cậy có thể bị **rỗng** và mọi kết nối CA-based gặp lỗi.

**Không tự giả định các Java distributions có cùng nội dung `cacerts`.** Nhà cung cấp/JDK build, OS packaging và chính sách cập nhật có thể khác. Một số môi trường container thay file/symlink hoặc đồng bộ với certificate bundle của OS theo cách riêng.

### Mặc định loại keystore

Từ **JDK 9**, loại `KeyStore` mặc định là **PKCS12**, nhưng file đang tồn tại có thể dùng format khác tùy distribution và lịch sử. `KeyStore.getDefaultType()` cho kiểu JVM mặc định; không dựa vào phần mở rộng `.jks` hay `.p12` để tự suy format.

## 9. Java 10 và JEP 319 Root Certificates

Một thay đổi có liên quan trực tiếp trong **Java 10** là **JEP 319 — Root Certificates**: cung cấp tập root Certification Authority certificates cho JDK OpenJDK, tránh tình trạng một số OpenJDK builds trước đó có `cacerts` rỗng khiến TLS không xây được trust path với public services.

**Diễn giải đúng ngày nay:**

- Một JDK hiện đại thường có danh sách CA gốc tin cậy trong `cacerts`.
- **Danh sách, thuật toán được phép và distrust policies luôn có thể thay đổi theo release/security updates.**
- Không được suy rằng “đã có JEP 319 nên mọi self-signed certificate sẽ được chấp nhận”.
- Không được “import đại một root” để sửa `PKIX path building failed` mà chưa xác minh nguồn và fingerprint.
- **Không hard-code số lượng root certificates** trong tài liệu kiểm thử. Nội dung có thể thay đổi theo runtime, vendor, distribution và bản vá bảo mật.

Tài liệu JDK 26 có cả chính sách **distrust một số CA cho TLS certificates phát hành sau một mốc ngày nhất định**. Đây là ví dụ cho thấy **file chứa một certificate không bảo đảm mọi chain anchored ở nó vẫn được chấp nhận trong mọi trường hợp**; còn phải xét chính sách SunJSSE, ngày cấp và loại usage.

## 10. Hostname verification là một điều kiện khác với path validation

Giả sử client kết nối tới:

~~~text
https://payments.example.test
~~~

Nhưng server gửi một leaf được CA đáng tin cấp cho:

~~~text
DNS:mail.example.test
~~~

Chữ ký và path CA có thể đúng, nhưng nó **không phải chứng thư phù hợp với hostname payments.example.test**. Nếu bỏ qua kiểm tra endpoint identity, client có thể chấp nhận chứng thư của một dịch vụ khác.

**Với HTTPS:** phải xác nhận danh tính DNS/IP trong certificate **SubjectAlternativeName (SAN)** khớp địa chỉ đích theo quy tắc endpoint identification thích hợp. **Common Name (CN)** không nên là cơ chế chính để thiết kế chứng thư server hiện đại.

- `HttpsURLConnection` và `java.net.http.HttpClient` trong cấu hình chuẩn có cơ chế xác minh hostname theo HTTPS.
- Nếu dùng `SSLSocket`/`SSLEngine` trực tiếp, hãy cấu hình phù hợp, ví dụ:

~~~java
SSLParameters params = sslSocket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
sslSocket.setSSLParameters(params);
~~~

Đây là **mảnh mã minh họa** với `sslSocket` đã được tạo, không phải chương trình độc lập. Endpoint identification trên `X509ExtendedTrustManager` có thể được áp dụng trong TLS handshake theo tham số socket/engine.

**Không thay bằng một `X509TrustManager` luôn trả thành công, `HostnameVerifier` luôn trả `true` hay một SSLContext “trust all”**. Những cách này phá vỡ một hoặc nhiều điều kiện xác thực peer, tạo nguy cơ man-in-the-middle.

**Cần phân biệt ba điều kiện:**

1. **Certificate path trusted?** (root/anchor và PKIX)
2. **Leaf certificate intended for server authentication?** (EKU, KU, algorithm/policies)
3. **Leaf identifies expected hostname?** (SAN/endpoint identity)

Chúng bổ trợ nhau; điều kiện 1 không thay thế điều kiện 3.

## 11. Revocation: OCSP/CRL không mặc nhiên được bật trong mọi client

Một chứng thư có thể được cấp hợp lệ rồi **bị thu hồi** trước ngày `NotAfter`, ví dụ do private key lộ.

Hai cơ chế thường gặp:

- **CRL** (Certificate Revocation List): danh sách chứng thư bị thu hồi do CA công bố.
- **OCSP** (Online Certificate Status Protocol): truy vấn/nhận trạng thái từ hệ thống hỗ trợ theo chính sách.

Trong Oracle **Java SE 26 Security Developer's Guide**, khi SunJSSE PKIX `TrustManagerFactory` khởi tạo bằng `init(KeyStore)`, **revocation checking bị tắt trong các default PKIX parameters**, có thể bật theo chính sách với các cơ chế và properties phù hợp. Khởi tạo bằng `CertPathTrustManagerParameters`/PKIX parameters là một đường có điều khiển khác.

**Không nói “Java tự luôn kiểm tra OCSP cho mọi TLS connection”.** Cấu hình thực tế phụ thuộc PKIX params, provider, JSSE security properties, khả năng truy xuất CRL/OCSP và chính sách fail-open/fail-closed của ứng dụng.

Trong ví dụ lab bên dưới, ta **tắt kiểm tra revocation rõ ràng** để việc chạy offline có kết quả xác định:

~~~java
params.setRevocationEnabled(false);
~~~

**Đây chỉ là thiết lập phục vụ lab.** Trong hệ thống production, cần có chính sách revocation, CA lifecycle và xử lý lỗi mạng phù hợp yêu cầu an toàn, không sao chép thao tác tắt kiểm tra này một cách máy móc.

## 12. Thuật toán và giới hạn tin cậy hiện hành

Dù chuỗi có chữ ký số hợp lệ theo phép `certificate.verify(publicKey)`, thuật toán cryptographic vẫn có thể bị JDK từ chối nếu không đáp ứng chính sách:

- `jdk.certpath.disabledAlgorithms`: giới hạn algorithm/key size cho certification path validation.
- `jdk.tls.disabledAlgorithms`: giới hạn cho giao thức/cơ chế/thuật toán TLS theo chính sách JDK.
- Các chính sách **CA distrust** có thể áp dụng theo anchor, ngày cấp và loại chứng thư.

**Không kích hoạt lại các thuật toán legacy yếu** như các cặp chữ ký/hàm băm không còn phù hợp chỉ để “sửa” certificate path validation. Hãy cấp phát lại chứng thư bằng thuật toán/độ dài khóa và CA chain phù hợp hiện hành.

**Độ dài khóa trong lab** là RSA 2048 với SHA256withRSA. Mục đích chỉ là tính tương thích và tái tạo nhanh trên JDK 24. Production cần chọn thuật toán/độ dài khóa theo chính sách bảo mật, vòng đời certificate và yêu cầu của hệ thống; có thể dùng ECDSA hoặc RSA key size lớn hơn tùy môi trường.

## 13. Lab an toàn: tạo Root → Intermediate → Server bằng `keytool`

Mục tiêu lab: tạo **một chuỗi tự quản lý trong thư mục riêng**, không chạm vào truststore mặc định của máy và không truy cập mạng. Sau đó kiểm tra:

- Root tự ký nhưng **chỉ được tin khi đưa vào `TrustAnchor`**.
- Intermediate ký leaf và root ký intermediate.
- Với đúng root anchor, path được PKIX validator chấp nhận.
- Đổi sang root khác, path bị từ chối.
- Bỏ intermediate khỏi path, validator không tự “điền vào” và path bị từ chối.
- Chứng thư leaf có SAN, nhưng việc **đọc SAN trong mã không thay cho hostname verification trong TLS**.

### Môi trường và mật khẩu

Yêu cầu **JDK 17+** có `keytool`, `javac` và `java` trong `PATH`. Mở một **thư mục lab rỗng, không dùng chung với dữ liệu sản xuất**.

Ở các câu lệnh phía dưới, mật khẩu `changeit123` **chỉ dành cho ví dụ local**. **Không đặt password thật trên command line** vì shell history/process inspection có thể làm lộ; production nên dùng công cụ quản lý bí mật, prompting hoặc hệ thống khóa an toàn.

Các lệnh được viết **một lệnh trên một dòng**, chạy được trong bash/zsh/PowerShell khi đường dẫn là tên file hiện tại.

### Bước A — Root CA

~~~bash
keytool -genkeypair -alias root -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -dname "CN=Demo Root CA, O=Local Lab" -ext "BC:critical=ca:true,pathlen:1" -ext "KU:critical=keyCertSign,cRLSign" -keystore root.p12 -storetype PKCS12 -storepass changeit123 -keypass changeit123 -noprompt
keytool -exportcert -alias root -rfc -file root.pem -keystore root.p12 -storepass changeit123
~~~

`root.p12` chứa **private key** của CA thử nghiệm; `root.pem` là **public certificate** có thể được đọc mà không tiết lộ private key.

### Bước B — Intermediate CA

~~~bash
keytool -genkeypair -alias intermediate -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -dname "CN=Demo Intermediate CA, O=Local Lab" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -keystore intermediate.p12 -storetype PKCS12 -storepass changeit123 -keypass changeit123 -noprompt
keytool -certreq -alias intermediate -file intermediate.csr -keystore intermediate.p12 -storepass changeit123
keytool -gencert -alias root -infile intermediate.csr -outfile intermediate.pem -rfc -validity 180 -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -keystore root.p12 -storepass changeit123
~~~

`intermediate.csr` là certificate signing request từ intermediate key pair. Lệnh `-gencert -alias root` ký intermediate certificate bằng **root private key**.

Trong lab, `intermediate.p12` đang giữ **key pair và self-signed certificate khởi tạo từ `genkeypair`**; `intermediate.pem` là certificate được root cấp cho cùng intermediate public key. Lệnh ký leaf ở bước sau dùng **intermediate private key**; chương trình PKIX dùng **intermediate.pem được root ký** để xây đường tin cậy. Trong một server/CA triển khai thật cần quản lý **certificate chain trong keystore** đúng với private key và mục đích sử dụng.

### Bước C — Leaf/server certificate

~~~bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -dname "CN=api.example.test, O=Local Lab" -keystore server.p12 -storetype PKCS12 -storepass changeit123 -keypass changeit123 -noprompt
keytool -certreq -alias server -file leaf.csr -keystore server.p12 -storepass changeit123
keytool -gencert -alias intermediate -infile leaf.csr -outfile leaf.pem -rfc -validity 90 -ext "BC:critical=ca:false" -ext "KU:critical=digitalSignature" -ext "EKU=serverAuth" -ext "SAN=dns:api.example.test" -keystore intermediate.p12 -storepass changeit123
~~~

`leaf.pem` có public key của server, issuer **Demo Intermediate CA**, EKU server authentication và DNS SAN `api.example.test`. Đây là một tên **ví dụ**, không có server mạng thực nào trong lab.

### Bước D — CA gốc không liên quan

~~~bash
keytool -genkeypair -alias wrongroot -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -dname "CN=Unrelated Root CA, O=Local Lab" -ext "BC:critical=ca:true,pathlen:1" -ext "KU:critical=keyCertSign,cRLSign" -keystore other.p12 -storetype PKCS12 -storepass changeit123 -keypass changeit123 -noprompt
keytool -exportcert -alias wrongroot -rfc -file other.pem -keystore other.p12 -storepass changeit123
~~~

CA này cũng có certificate tự ký hợp lệ, nhưng public key **khác** root đã cấp chuỗi. Nó là minh họa cho câu: **“một root tự ký hợp lệ không thể thay root mà chain thực sự tin cậy”**.

### Bước E — xem chứng thư, nhưng chưa tự kết luận tin cậy

~~~bash
keytool -printcert -file root.pem -v
keytool -printcert -file intermediate.pem -v
keytool -printcert -file leaf.pem -v
~~~

Tìm `Owner/Subject`, `Issuer`, SHA-256 fingerprint, `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage` và `SubjectAlternativeName`. Đối chiếu issuer–subject và các extension. **Không dùng một fingerprint do chính tệp cần kiểm tra cung cấp làm “nguồn xác minh độc lập”**: trong thực tế phải so fingerprint với nguồn đáng tin ngoài kênh đang bị nghi ngờ.

## 14. Chương trình Java 17+ độc lập: `PkixTrustAnchorDemo.java`

Lưu cùng thư mục với các tệp `root.pem`, `intermediate.pem`, `leaf.pem` và `other.pem` đã tạo.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Set;

public final class PkixTrustAnchorDemo {

    static X509Certificate read(CertificateFactory cf, String name)
            throws Exception {
        try (InputStream in = Files.newInputStream(Path.of(name))) {
            return (X509Certificate) cf.generateCertificate(in);
        }
    }

    static boolean validates(
            CertPathValidator validator,
            CertificateFactory cf,
            X509Certificate root,
            List<X509Certificate> untrusted) throws Exception {

        CertPath path = cf.generateCertPath(untrusted);

        // Điểm neo tin cậy là INPUT của phép xác thực.
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));

        // CHỈ trong lab offline để kết quả có thể tái lập:
        // Production phải quyết định chính sách revocation.
        params.setRevocationEnabled(false);

        try {
            validator.validate(path, params);
            return true;
        } catch (CertPathValidatorException exception) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        CertificateFactory cf =
                CertificateFactory.getInstance("X.509");

        X509Certificate root = read(cf, args[0]);
        X509Certificate intermediate = read(cf, args[1]);
        X509Certificate leaf = read(cf, args[2]);
        X509Certificate wrong = read(cf, args[3]);

        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");

        // Chữ ký số đúng nhưng CHƯA phải kết luận trusted.
        root.verify(root.getPublicKey());
        intermediate.verify(root.getPublicKey());
        leaf.verify(intermediate.getPublicKey());

        System.out.println("rootSelfSigned="
                + root.getSubjectX500Principal()
                        .equals(root.getIssuerX500Principal()));

        System.out.println("intermediateCa="
                + (intermediate.getBasicConstraints() >= 0));

        System.out.println("leafIsCa="
                + (leaf.getBasicConstraints() >= 0));

        // CertPath không chứa root TrustAnchor.
        System.out.println("pathWithoutRootSize="
                + cf.generateCertPath(
                        List.of(leaf, intermediate))
                        .getCertificates().size());

        System.out.println("trustedPathAccepted="
                + validates(validator, cf, root,
                        List.of(leaf, intermediate)));

        System.out.println("wrongRootAccepted="
                + validates(validator, cf, wrong,
                        List.of(leaf, intermediate)));

        System.out.println("missingIntermediateAccepted="
                + validates(validator, cf, root,
                        List.of(leaf)));

        // Chỉ ĐỌC SAN, không phải HTTPS hostname verification.
        System.out.println("dnsSanPresent="
                + leaf.getSubjectAlternativeNames()
                        .stream()
                        .anyMatch(item ->
                                Integer.valueOf(2).equals(item.get(0))
                                && "api.example.test".equals(item.get(1))));
    }
}
~~~

**Biên dịch:**

~~~bash
javac PkixTrustAnchorDemo.java
~~~

**Chạy:**

~~~bash
java PkixTrustAnchorDemo root.pem intermediate.pem leaf.pem other.pem
~~~

**`stdout` đã kiểm thử trên HotSpot JDK 24.0.2:**

~~~text
rootSelfSigned=true
intermediateCa=true
leafIsCa=false
pathWithoutRootSize=2
trustedPathAccepted=true
wrongRootAccepted=false
missingIntermediateAccepted=false
dnsSanPresent=true
~~~

Bài test đã dùng các lệnh `keytool` ở trên để tạo đủ bốn chứng thư, rồi biên dịch và thực thi chương trình. **Đây là kết quả từ lab thực tế**, không phải kết quả phỏng đoán dựa trên tên file.

### Giải thích từng kết quả

1. **`rootSelfSigned=true`**: trước đó `root.verify(root.getPublicKey())` đã thành công và DN subject/issuer bằng nhau. Điều đó kiểm chứng **self-signature**, không tự chứng minh root đáng tin.
2. **`intermediateCa=true`**: `getBasicConstraints() >= 0` cho biết đây là CA certificate.
3. **`leafIsCa=false`**: leaf không có quyền CA theo `BasicConstraints`.
4. **`pathWithoutRootSize=2`**: `CertPath` gồm **leaf và intermediate**, root được đưa vào riêng dưới dạng `TrustAnchor`.
5. **`trustedPathAccepted=true`**: PKIX chấp nhận path dựa vào đúng root, các chữ ký và ràng buộc.
6. **`wrongRootAccepted=false`**: có root khác tự ký không giúp chuỗi này tin cậy.
7. **`missingIntermediateAccepted=false`**: chỉ đưa leaf vào `CertPathValidator` với root anchor không tạo lại intermediate tự động.
8. **`dnsSanPresent=true`**: chứng thư leaf chứa SAN `api.example.test`; phép đọc SAN **không phải** việc kiểm tra kết nối TLS đang hướng đến hostname nào.

### Vì sao lab không phải full HTTPS connection test?

Không có socket, `SSLEngine` hoặc `HttpsURLConnection` trong ví dụ. Nó chỉ kiểm tra **PKIX certification path**, không thực hiện TLS handshake, không kiểm tra server sở hữu private key tại runtime và không thực thi **hostname verification**.

Đây là chủ đích để tách các lớp trách nhiệm. Khi đưa vào ứng dụng HTTPS thật, hãy để JSSE/HTTP client được cấu hình đúng thực hiện **đầy đủ cả TLS, trust management và endpoint identification**.

### Vì sao lab tắt revocation?

Root/intermediate/leaf local không có OCSP responder hoặc CRL distribution point có thể truy cập. `params.setRevocationEnabled(false)` làm phép thử path không phụ thuộc mạng; **không phải mẫu security policy production**.

### Khi lab hết hạn

Các certificates local có `-validity` giới hạn ngày. Khi chạy lại sau hạn, PKIX có thể từ chối vì chứng thư hết hạn. Hãy **tạo lại lab certificates**, không tắt validity checks.

## 15. `PKIXParameters` và `TrustAnchor` trong ứng dụng thực

Java Certification Path API hỗ trợ:

- `CertificateFactory.getInstance("X.509")`: đọc `X509Certificate` và tạo `CertPath`.
- `CertPathValidator.getInstance("PKIX")`: kiểm tra path đã cung cấp.
- `CertPathBuilder.getInstance("PKIX")`: tìm/xây path từ mục tiêu đến trust anchors.
- `PKIXParameters`: trust anchors, ngày validation, revocation options, policy checkers.
- `PKIXBuilderParameters`: thêm constraints để tìm target và max path length.
- `TrustAnchor`: CA được xác định là điểm tin cậy.
- `X509CertSelector`: chọn certificate mục tiêu theo subject/SAN/tiêu chí khác.
- `CertStore`: nguồn candidate certificates/CRLs theo provider.

Ví dụ khái niệm khi ứng dụng có một truststore riêng:

~~~java
KeyStore store = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("trust.p12"))) {
    store.load(in, password);
}
PKIXParameters params = new PKIXParameters(store);
~~~

Đây là **mảnh code minh họa**, các import và `password` cần được cung cấp phù hợp. `PKIXParameters(KeyStore)` sử dụng trusted certificate entries của KeyStore làm nguồn trust anchors.

**Không chọn `PKIXBuilderParameters` khi chỉ muốn validate một path sẵn có** nếu không cần xây path; ngược lại, đừng mong validator tự tìm intermediate ngoài path được cung cấp.

## 16. Cấu hình truststore của Java mà không phá root store hệ thống

### Kiểm tra các trusted roots sẵn có

~~~bash
keytool -list -cacerts
~~~

Lệnh xem danh sách trusted certificates trong `cacerts` của JDK tương ứng với `keytool` đang chạy. Nội dung có thể khác nhau giữa builds và cập nhật security.

Muốn xem một certificate trong file:

~~~bash
keytool -printcert -v -file root.pem
~~~

**Trước khi import bất kỳ CA nào vào truststore, so SHA-256 fingerprint với nguồn đáng tin độc lập.** Không tin một chứng thư từ email, log hoặc TLS endpoint không xác thực chỉ vì nó có tên “Root CA”.

### Tạo truststore riêng cho lab

Sau khi xác định đúng certificate, dùng:

~~~bash
keytool -importcert -alias demo-root -file root.pem -keystore demo-trust.p12 -storetype PKCS12 -storepass changeit123 -noprompt
keytool -list -v -keystore demo-trust.p12 -storepass changeit123
~~~

**Chỉ làm trong lab:** không import CA thử nghiệm này vào `cacerts` hệ thống, không dùng truststore thử nghiệm trong production. Với CA thật, `-noprompt` bỏ bước xác nhận tương tác nên chỉ sử dụng sau khi đã verify fingerprint.

### Dùng một truststore riêng trong ứng dụng

Ví dụ:

~~~bash
java -Djavax.net.ssl.trustStore=demo-trust.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -jar app.jar
~~~

**Điều cần cảnh báo:** một truststore riêng thường **thay thế tập trusted certificates mặc định** cho Default SSLContext/TrustManager của SunJSSE, **không tự bổ sung** root của bạn vào `cacerts`. Nếu file chỉ có một CA nội bộ, nhiều public HTTPS endpoints trước đó được tin cậy có thể bị từ chối.

Nếu ứng dụng vừa cần public CAs vừa cần private CA, hãy cấu hình trust material có cả những anchors **thực sự được cho phép**, hoặc xây custom TrustManager theo cách **giữ nguyên các kiểm tra PKIX/hostname**. Không tạo một `trustAll` manager.

**Không ghi password nhạy cảm trên command line trong production.** Đây là demo; dùng secret delivery được bảo vệ và cấu hình phù hợp.

## 17. Sai lầm “server gửi root nên client phải tin”

Một server có thể gửi:

~~~text
Certificate message:
  leaf
  intermediate
  root (tùy server, thường không cần)
~~~

Nhưng nếu Java client không cấu hình root/anchor này là trusted, việc server gửi kèm root **không làm kết nối thành đáng tin**. Nếu tin được mọi root mà server tự gửi, bất kỳ attacker cũng có thể tạo CA giả rồi giả mạo một website.

**Ranh giới tin cậy được quyết định ở client**, không phải bởi server.

Vì vậy nhiều TLS servers được cấu hình gửi **leaf + intermediates**, không cần gửi root. Client có thể có root sẵn trong truststore hoặc được quản lý bằng policy riêng.

### Alternate paths và cross-signing

Một intermediate có thể được **cross-signed** bởi các CAs khác nhau, sinh ra nhiều đường chứng thư tiềm năng. Path builder có thể chọn đường đến một trong các trusted anchors dựa vào chứng thư có sẵn, policies và algorithm constraints.

Ví dụ:

~~~text
             Root A (trusted?)      Root B (trusted?)
                  |                      |
            ký Intermediate X      ký Intermediate X
                  \                      /
                        Leaf server
~~~

Hai intermediate certificates có thể có cùng subject/public key nhưng **issuer/signature khác**, cho phép đường xác thực đến Root A hoặc Root B. Không nên suy rằng một chuỗi “chỉ có duy nhất một đường” từ tên file PEM hoặc thứ tự server gửi.

Nếu một root bị distrust trên JDK mới, một alternate path khác chỉ khả thi khi thật sự có chain hợp lệ tới một root khác và thỏa chính sách. **Không tự xóa distrust policies** để ép tin root cũ.

## 18. Những lỗi PKIX/TLS thường gặp và cách đọc

### `PKIX path building failed`

Thông báo điển hình:

~~~text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed: ...
~~~

Điều đó thường có nghĩa Java **không tìm được đường chứng thư hợp lệ** tới trust anchor được chấp nhận theo policy/available certificates. Các nguyên nhân có thể:

- Root CA không có trong truststore của JVM đang chạy.
- Server thiếu intermediate và client không có cách tìm.
- Truststore path sai hoặc file không tồn tại.
- Java đang dùng một JDK/container image khác với JVM mà bạn vừa sửa `cacerts`.
- Chứng thư hết hạn/chưa hiệu lực, thuật toán/key bị từ chối hoặc constraints không hợp lệ.
- Root bị distrust theo chính sách JDK hoặc certificate type/usage không hợp lệ.

**Không nên giải quyết bằng cách tắt hết SSL validation.**

### `SunCertPathBuilderException: unable to find valid certification path`

Đây là một thông điệp thường thấy trong SunPKIX path building, nhưng **không cho biết chắc chắn thiếu root**. Có thể bị thiếu intermediate, truststore trống hoặc constraints từ chối mọi đường khả thi.

### `No subject alternative DNS name matching ...`

Đây là vấn đề **hostname/endpoint identity**, không phải tự động là thiếu root. Nếu certificate được cấp cho `api1.example.test` nhưng client kết nối `api2.example.test`, cần cấp/cấu hình certificate có SAN đúng tên hoặc sử dụng endpoint đúng.

**Không sửa bằng cách import thêm CA**, vì import CA không khiến một SAN sai trở thành đúng.

### Chứng thư hết hạn

Nếu `NotAfter` của leaf/intermediate đã qua hoặc `NotBefore` chưa đến, PKIX có thể từ chối. Kiểm tra clock của hệ thống và thời hạn/cert renewals. **Không tắt kiểm tra thời gian** để hợp thức hóa certificate quá hạn.

### `Algorithm constraints check failed`

Một certificate có thể có chữ ký hợp lệ nhưng dùng thuật toán hoặc khóa bị `jdk.certpath.disabledAlgorithms` từ chối. Giải pháp phù hợp là **cấp lại certificate bằng thuật toán được chấp nhận**, không tự gỡ toàn bộ chính sách bảo mật.

### Root certificate tồn tại nhưng vẫn bị từ chối

Cần xét **provider/CA distrust policies**, certificate issuance date, usage và các path constraints. Nội dung file `cacerts` chỉ là **một phần** trong quyết định tin cậy của Java SE hiện hành.

## 19. Quy trình chẩn đoán TLS trong container hoặc server Java

Khi ứng dụng báo lỗi certificate path:

1. **Xác định JVM thực sự chạy**: vendor, build, `java.home`, container image và runtime arguments.
2. **Kiểm tra endpoint đúng hostname**: DNS name/IP và SAN của leaf; phân biệt lỗi hostname với lỗi trust path.
3. **Xem certificates server trình**: leaf và intermediates, issuer/subject, validity, extensions, signature/public keys.
4. **Xem truststore đang dùng**: `javax.net.ssl.trustStore` có được đặt không, path có tồn tại và accessible không, loại store có đúng không.
5. **Nếu dùng default**: xác định `jssecacerts` hay `cacerts` và JDK distribution thực tế.
6. **Đối chiếu root fingerprint** với nguồn tin cậy, không chỉ tên CA.
7. **Kiểm tra tính liên tục của chain** và các intermediate có được gửi/khả dụng không.
8. **Kiểm tra algorithm constraints, BasicConstraints, EKU, SAN và security properties**.
9. **Kiểm tra revocation policy** nếu được bật; không bỏ qua lỗi do OCSP/CRL unreachable một cách vô thức.
10. **Phân biệt path building với path validation**, dùng công cụ thích hợp.
11. **Giữ bằng chứng**: thời điểm, certificate fingerprints, phiên bản JDK, JSSE/debug logs.
12. **Sửa tại nguồn đúng**: server gửi chain đầy đủ; client tin đúng CA; leaf cấp đúng hostname; thay certificate/algorithm đã yếu.
13. **Không dùng trust-all code** kể cả để “xác minh nhanh production đã lên mạng”.
14. **Kiểm thử lại** với cùng runtime/container image và hostname thực tế.

### Công cụ gợi ý

~~~bash
keytool -list -cacerts
keytool -printcert -file server.pem -v
keytool -printcert -sslserver api.example.test:443 -rfc
~~~

Lệnh cuối **có truy cập mạng đến server** nếu hostname/port thực sự tồn tại; vì vậy chỉ dùng khi bạn có quyền kết nối và nguồn phù hợp. Đây là ví dụ công cụ chẩn đoán, **không được coi việc `-printcert -sslserver` hiển thị một chain là đã validate được trust**.

Có thể bật JSSE debugging trên một JVM được phép kiểm tra:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar app.jar
~~~

**Không bật debug trong production thời gian dài**: logs có thể chứa metadata của peer/handshakes và gây overhead, cần bảo vệ/chỉnh thời gian lưu. Các debug options và cách in phụ thuộc JDK provider.

## 20. Phân biệt trust CA và certificate pinning

**CA trust**: client chấp nhận một hay nhiều CAs và kiểm tra leaf đi theo policy tới một anchor hợp lệ. Cách này phù hợp với việc tự động cấp lại server certificates mà không thay đổi client nếu chúng tiếp tục được cấp bởi CA đã tin.

**Certificate/public-key pinning**: ứng dụng ràng buộc thêm certificate hoặc public key cụ thể, một chính sách khác và có nguy cơ gây outage khi xoay khóa/chứng thư.

Pinning **không thay thế** PKIX/hostname verification theo cách tự động; nếu sử dụng, cần quy hoạch rotation, backup pins hoặc policy fallback có kiểm soát, xử lý compromised key và vòng đời vận hành. Không hard-code fingerprint leaf thiếu chiến lược cập nhật rồi gọi đó là “cách duy nhất bảo mật”.

**Không cần pinning cho mọi dịch vụ HTTPS.** Trước hết phải thiết lập trust anchors và endpoint identification đúng.

## 21. mTLS: trust anchor có thể nằm ở cả hai phía

Trong **mutual TLS (mTLS)**, không chỉ server trình chứng thư; **client cũng có thể phải trình certificate chain của mình**.

- **Client** dùng truststore để kiểm tra server (cùng hostname server phù hợp).
- **Server** dùng truststore/policy riêng để kiểm tra client CA chain và mục đích `clientAuth`, cùng các quy tắc xác thực/ủy quyền ứng dụng.
- Mỗi phía dùng keystore/private key của **chính mình** để chứng minh danh tính.

Cùng một root CA public certificate có thể được hai phía chọn tin hoặc mỗi phía chọn các anchors khác nhau. **Chấp nhận client certificate không có nghĩa ứng dụng tự biết client được phép làm tất cả mọi việc**: authentication và authorization là các bước riêng.

**Không nhập private key của root CA vào truststore client** để xác thực chain. Truststore cần thông tin công khai của trusted CA, không cần và không nên chứa CA private key.

## 22. Bài tập tự kiểm tra

### Câu 1 — root tự ký

Một người lạ gửi file `my-root.pem` có subject=issuer và chữ ký tự ký hợp lệ. Java có nên tự tin nó không?

**Đáp án:** Không. Self-signature chỉ chứng minh tính nhất quán chữ ký với public key của certificate. Cần quyết định trust từ kênh độc lập.

### Câu 2 — root trong CertPath

Danh sách path có `[leaf, intermediate]`, root ở `PKIXParameters`. Có thiếu root trong path không?

**Đáp án:** Không. Theo quy ước Java X.509 `CertPath`, trust anchor thường ở ngoài path.

### Câu 3 — wrong root

Root B tự ký nhưng leaf được Intermediate A ký và Intermediate A được Root A ký. Client chỉ tin Root B. Đường A có tự hợp lệ không?

**Đáp án:** Không. Phải có path hợp lệ đến trust anchor B theo chính sách, không chỉ một certificate root B bất kỳ.

### Câu 4 — thiếu intermediate

`CertPathValidator` nhận chỉ leaf và root anchor, trong khi leaf được intermediate ký. Validator có tự tìm intermediate trên mạng không?

**Đáp án:** Không theo hợp đồng của validator đã cho một path cụ thể. Cần có intermediate trong path; sử dụng path builder và nguồn certificate nếu muốn tìm.

### Câu 5 — SAN hostname

Chuỗi từ root đáng tin tới leaf hợp lệ, nhưng SAN chỉ có `mail.example.test` và client kết nối `payments.example.test`. Có đúng HTTPS identity không?

**Đáp án:** Không. Trust chain valid và hostname match là hai kiểm tra khác nhau.

### Câu 6 — EKU

Leaf chỉ có `clientAuth` nhưng được dùng làm server certificate. Có được chấp nhận bất kể EKU không?

**Đáp án:** Không nên; TLS server authentication phải kiểm tra mục đích sử dụng phù hợp, cùng các constraints khác.

### Câu 7 — BasicConstraints

Một intermediate thiếu `CA:TRUE` có thể cấp certificate cho server trong PKIX chain không?

**Đáp án:** Không được xem là một CA hợp lệ nếu path validation yêu cầu intermediate CA role.

### Câu 8 — truststore riêng

Ứng dụng đặt `-Djavax.net.ssl.trustStore=private.p12` chỉ chứa CA nội bộ. Có tự động giữ nguyên toàn bộ public roots trong `cacerts` không?

**Đáp án:** Không với default SunJSSE trust manager; cần chuẩn bị/khởi tạo trusted material có chủ đích.

### Câu 9 — truststore file sai

Đặt `javax.net.ssl.trustStore` trỏ vào file không tồn tại có tự quay về `cacerts` không?

**Đáp án:** Không nên trông chờ fallback; SunJSSE có thể tạo truststore rỗng khi override file không tồn tại.

### Câu 10 — Java 10 JEP 319

JEP 319 có nghĩa bất kỳ self-signed certificate nào đều được tin?

**Đáp án:** Không. Nó cung cấp root CA certificates trong tập được chấp nhận của OpenJDK; chính sách trust vẫn do client/JDK và cập nhật bảo mật quyết định.

### Câu 11 — PKIX và `verify`

Gọi `leaf.verify(intermediatePublicKey)` thành công có đủ kết luận TLS server đáng tin?

**Đáp án:** Không. Còn issuer chain, root anchor, validity, CA usage, constraints, algorithms, revocation policy và endpoint identity.

### Câu 12 — revocation

Java có tự bật OCSP cho mọi `TrustManagerFactory.init(KeyStore)` không?

**Đáp án:** Không. Oracle Security Developer's Guide mô tả revocation checking bị tắt trong đường khởi tạo PKIX mặc định đó; production cần cấu hình chính sách phù hợp.

### Câu 13 — key pair

Certificate chain có chứa private key của root hoặc server không?

**Đáp án:** Không. Chứng thư công khai chứa public keys và dữ liệu cấp phát; private keys phải được bảo vệ riêng.

### Câu 14 — cross-signing

Một intermediate cùng public key nhưng có hai certificates do hai roots khác nhau cấp. Path builder có thể thử hai đường khác nhau không?

**Đáp án:** Có nếu các certificates và trust anchors được cung cấp/phát hiện hợp lệ, các constraints được thỏa và provider hỗ trợ.

### Câu 15 — status `PKIX path building failed`

Có thể khẳng định “chỉ thiếu root trong cacerts” từ message đó không?

**Đáp án:** Không. Có thể thiếu intermediate, truststore sai, algorithms bị cấm, certificate hết hạn hoặc constraints/policy không thỏa.

### Câu 16 — server gửi root

Server gửi thêm root self-signed trong TLS certificate chain. Client có bắt buộc tin root đó không?

**Đáp án:** Không. Quyết định trust anchor phải đến từ cấu hình tin cậy phía client.

### Câu 17 — trust anchor ngoài path

Vì sao `pathWithoutRootSize=2` trong demo nhưng `trustedPathAccepted=true`?

**Đáp án:** Root được đưa riêng vào `PKIXParameters` dưới dạng `TrustAnchor`; validator kiểm tra path leaf → intermediate tới public key của anchor.

### Câu 18 — SAN trong demo

`dnsSanPresent=true` có chứng minh một HTTPS connection đã xác minh hostname không?

**Đáp án:** Không. Chương trình chỉ đọc certificate SAN; không có socket/TLS handshake/endpoint identification.

## 23. Checklist triển khai an toàn

- [ ] Xác định chính xác root/intermediate/leaf và các vai trò của chúng.
- [ ] Root public key được chấp nhận từ **nguồn tin cậy độc lập**.
- [ ] Không chấp nhận một root chỉ vì nó tự ký hợp lệ.
- [ ] Server gửi leaf + intermediate chain phù hợp.
- [ ] Không yêu cầu server gửi root để buộc client tin cậy.
- [ ] CA intermediates có `BasicConstraints`, `keyUsage` và path length hợp lệ.
- [ ] Leaf có SAN hostname/IP đúng và EKU/KU tương ứng TLS server.
- [ ] Xem xét validity, algorithm constraints và revocation policy.
- [ ] Không nhầm certificate path validation với HTTPS endpoint identification.
- [ ] Xác định truststore đang được process Java thực sự sử dụng.
- [ ] Kiểm tra `javax.net.ssl.trustStore` và file tồn tại/đọc được trước khi deploy.
- [ ] Không import root lạ chỉ để dập lỗi TLS.
- [ ] Không sửa `cacerts` system-wide một cách tùy tiện; cân nhắc truststore riêng có kiểm soát.
- [ ] Bảo vệ CA/server private keys, không đưa vào truststore client.
- [ ] Không tắt PKIX, hostname verification hoặc algorithm restrictions.
- [ ] Đặt quy trình certificate rotation, cập nhật root store và caDistrustPolicies.
- [ ] Kiểm tra chain từ container/JDK build thật vì truststore khác nhau giữa distributions.
- [ ] Thu thập log ở mức vừa đủ, không lộ secrets và không bật debug vô thời hạn.
- [ ] Kiểm thử lại khi nâng JDK, xoay CA, đổi ingress/service mesh hoặc cập nhật certificate.

## 24. Tổng kết và tài liệu chính thức

**Root CA** là một CA ở đỉnh hệ phân cấp; chứng thư root thường tự ký nhưng **self-signed không có nghĩa trusted**. **Certificate chain** nối leaf qua các intermediates bằng chữ ký và constraints. **Trust anchor** là public key/CA certificate đã được client chấp nhận cục bộ và là điểm dừng của PKIX path validation; Java `CertPath` thường **không chứa trust anchor**.

Trong Java hiện hành, sử dụng **JSSE/PKIX TrustManager**, cấu hình đúng `cacerts`/truststore, kiểm tra **SAN hostname** và chính sách thu hồi/algorithms, không vô hiệu hóa xác thực TLS. **Java 10 JEP 319** bổ sung tập root certificates cho OpenJDK; tập đó và distrust policies tiếp tục được cập nhật theo bản JDK.

### Nguồn tham khảo chính thức còn phù hợp

1. [Oracle Java SE 26 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/26/security/java-pki-programmers-guide.html): certification path, PKIX validation, building, TrustAnchor và certificate policies.
2. [Oracle Java SE 26 — Security Developer's Guide](https://docs.oracle.com/en/java/javase/26/security/security-developer-guide.pdf): JSSE, trust manager, default truststore lookup, PKIX revocation behavior.
3. [Java SE 26 — `TrustAnchor` Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/TrustAnchor.html): trust anchor từ certificate hoặc CA principal/public key.
4. [Java SE 26 — `CertPath` Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertPath.html): chuỗi từ target đến issuer do anchor cấp và không gồm anchor.
5. [Java SE 26 — `PKIXBuilderParameters` Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXBuilderParameters.html): root trusted entries, building path và target constraints.
6. [Java SE 26 — `X509ExtendedTrustManager` Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): path trust và endpoint identification qua socket/engine.
7. [Oracle JDK 10 Release Notes — JEP 319 Root Certificates](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): nguồn gốc tập root certificates bổ sung ở Java 10.
8. [OpenJDK — `keytool` manual](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/keytool.md): tạo certificate, export, xem fingerprint và `-cacerts`.
9. [Oracle JDK 26 Release Notes — CA distrust policies](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): ví dụ cập nhật trust policy theo CA và thời điểm cấp certificate.
10. [RFC 5280 — X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): quy tắc BasicConstraints, extensions, certification path validation.
