# Chẩn đoán lỗi không xây dựng được chuỗi tin cậy (PKIX) trong Java 10+

## 1. Tình huống và mục tiêu

Ứng dụng Java gọi một HTTPS API, kết nối tới hệ thống nội bộ, dịch vụ thanh toán, registry, Kafka TLS hoặc database dùng TLS. Một ngày, giao tiếp thất bại và log có dạng:

~~~text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed:
  sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
~~~

Thông báo này thường có nghĩa **Java không xây dựng được một đường chứng chỉ hợp lệ từ chứng chỉ phía đối tác tới một điểm tin cậy (trust anchor)** trong cấu hình kiểm tra hiện tại. Nó **không tự động chứng minh máy chủ giả mạo, chứng chỉ đã hết hạn, hay chỉ thiếu một root CA**. Cần xem chính xác **phía nào đang xác thực ai**, **chuỗi chứng chỉ nào được gửi**, **truststore và chính sách nào JVM đang dùng**, rồi mới xác định nguyên nhân.

Bài thuộc nhóm **Chứng thư gốc**, module **Java 10**. Các cơ chế chính được trình bày theo **JSSE (Java Secure Socket Extension), PKIX, X.509 và JDK hiện đại** như JDK 17, JDK 21, JDK 25; chỉ sử dụng những kiến thức vẫn được hỗ trợ và khuyến nghị ngày nay.

Sau bài học, bạn sẽ:
1. Phân biệt **server certificate (leaf)**, **intermediate CA**, **root CA** và **trust anchor**.
2. Hiểu bước **certificate path building** và **certificate path validation** trong TLS.
3. Đọc nguyên nhân trong `SSLHandshakeException`, `CertPathBuilderException`, `CertPathValidatorException`.
4. Xác định JVM **thực sự dùng truststore nào**; tránh nhầm truststore với keystore.
5. Kiểm tra chain mà endpoint hoặc proxy đang trình bày, gồm **SNI** và intermediate certificates.
6. Sử dụng `keytool`, OpenSSL, `javax.net.debug` và `java.security.debug=certpath` có kiểm soát.
7. Phân biệt thiếu CA, thiếu intermediate, cấu hình truststore sai, lỗi thời gian, thuật toán bị hạn chế, revocation và hostname mismatch.
8. Khắc phục bằng **chuỗi đầy đủ và trust anchors đã xác minh**, không tắt xác thực TLS.
9. Viết/chạy một chương trình **Java 17+ độc lập**, có stdout mẫu xác định, cùng tùy chọn chẩn đoán kết nối HTTPS thực.
10. Xây dựng checklist an toàn cho production, container, CI, proxy và mutual TLS.

**Nguyên tắc vàng:** Không “sửa” lỗi PKIX bằng một `TrustManager` luôn trả thành công, tắt hostname verification, hoặc tin mọi chứng chỉ. Làm vậy xóa lớp bảo vệ chống giả mạo của TLS.

## 2. Mô hình tin cậy: leaf → intermediate → root

Một hệ thống chứng chỉ X.509 điển hình có các thành phần:

~~~text
                  ROOT CA (trust anchor)
                  được client tin cậy
                           │
                    ký chứng chỉ cho
                           ▼
                     INTERMEDIATE CA
                           │
                    ký chứng chỉ cho
                           ▼
                 LEAF / SERVER CERT
                Subject/SAN: api.example
                           │
                  server gửi cho client
                           ▼
                    Java TLS client
~~~

Phân biệt:
- **Leaf/end-entity certificate:** đại diện cho server (hoặc client trong mTLS), chứa public key, thông tin chủ thể, SAN, thời hạn, EKU và chữ ký của CA.
- **Intermediate CA:** CA trung gian ký leaf hoặc một intermediate khác; có `BasicConstraints CA=true` và những điều kiện thích hợp.
- **Root CA:** thường là chứng chỉ tự ký của tổ chức cấp chứng chỉ gốc; được đưa vào kho tin cậy của client thông qua một quyết định tin cậy độc lập.
- **Trust anchor:** đầu mút tin cậy mà PKIX sử dụng. Thường là một trusted root certificate, nhưng khái niệm tổng quát là một CA/public key được cấu hình làm điểm bắt đầu tin cậy; không nhất thiết phải là self-signed root xuất hiện trong TLS handshake.
- **Truststore:** nơi client hoặc server lưu các trusted certificates/anchors để xác minh đối tác, thường được JSSE tải qua `TrustManagerFactory`.
- **Keystore chứa private key:** nơi chủ thể TLS lưu private key và certificate chain dùng để **chứng minh danh tính của chính mình**.

### Phía server cần gửi gì?

Với một HTTPS server phổ biến, server thường gửi:
1. **Leaf certificate** của hostname được yêu cầu.
2. **Intermediate certificates cần thiết**, theo chain phù hợp.

Nó **thường không cần gửi root certificate** vì root phải được client tin cậy sẵn. Chỉ gửi root tự ký từ server **không làm client tự nhiên tin root ấy**.

Một chain sai điển hình:

~~~text
Server gửi:
    Leaf(api.example)
    [không gửi Intermediate CA]

Java client có:
    Trusted Root CA

Kết quả có thể:
    Không tìm được đường từ Leaf tới Root
    → PKIX path building failed
~~~

**Lưu ý:** Một số client có thể đã có intermediate trong kho riêng hoặc tìm được certificate qua cơ chế khác. Vì vậy cùng server có thể chạy được trên trình duyệt A nhưng lỗi trong Java B. Không nên dựa vào việc trình duyệt mở được trang để khẳng định server chain đúng.

### Path building và path validation khác nhau

**Path building:** tìm một chuỗi certificate từ leaf đến trust anchor khả dụng, dùng các certificate được server gửi, kho certificate bổ sung và các nguồn mà implementation/configuration hỗ trợ.

**Path validation:** kiểm tra chuỗi tìm được có thỏa mãn yêu cầu PKIX không, ví dụ:
- Chữ ký từng certificate và quan hệ issuer;
- Khoảng hiệu lực `notBefore`/`notAfter`;
- Basic Constraints/Key Usage/EKU và path length;
- Thuật toán, key size theo security policy của JDK;
- Tên, chính sách và ràng buộc khác;
- Revocation/OCSP/CRL **khi được cấu hình hoặc chính sách yêu cầu**.

Sau đó, đối với HTTPS, **hostname identity verification** còn phải xác nhận tên host thực sự được truy cập khớp danh tính trong chứng chỉ (thường SAN DNS/IP). Một chain xây dựng hợp lệ **không đồng nghĩa tên server cũng đúng**.

## 3. Nhận diện đúng nhóm lỗi trong exception chain

Đừng chỉ tìm đoạn chữ `PKIX`. Hãy giữ **full stack trace và toàn bộ các `Caused by`**.

| Tín hiệu | Nhóm nguyên nhân nên điều tra | Không được kết luận ngay |
| --- | --- | --- |
| `PKIX path building failed` | Thiếu đường đến trust anchor hoặc constraint khiến không xây dựng được path | Chắc chắn thiếu root trong cacerts |
| `unable to find valid certification path to requested target` | Builder không tìm được đường hợp lệ | Chắc chắn server hết hạn |
| `PKIX path validation failed` | Một đường đã được xem xét nhưng không vượt validation | Chắc chắn chỉ thiếu intermediate |
| `trustAnchors parameter must be non-empty` | Không có trust anchors dùng được, kho trống/sai cấu hình | Phải tắt TLS |
| `CertificateExpiredException` | Certificate hết hạn ở ngày kiểm tra | Root chưa import |
| `CertificateNotYetValidException` | Certificate chưa đến ngày hiệu lực hoặc đồng hồ sai | Cần import leaf |
| `Algorithm constraints check failed` | Thuật toán/key size bị chính sách JDK chặn | Cần hạ bảo mật toàn JVM |
| `No subject alternative DNS name matching ...` | Hostname mismatch | Lỗi root CA chắc chắn |
| `Certificate has been revoked` | Chứng chỉ bị thu hồi theo chính sách kiểm tra | Chỉ cần thêm CA |
| `Could not determine revocation status` | Vấn đề tìm/kiểm tra OCSP/CRL khi revocation checking có hiệu lực | Chắc chắn certificate bị thu hồi |
| `Received fatal alert: bad_certificate` | Đối tác từ chối certificate, thường cần kiểm tra hướng mTLS | Chính Java client đang thiếu root |
| `Received fatal alert: unknown_ca` | Phía nhận không tin CA của chứng chỉ đối tác, tùy handshake direction | Cần import CA vào phía client một cách máy móc |

**Chú ý:** Các chuỗi exception cụ thể có thể khác theo JDK build, provider, TLS version và thư viện HTTP. Không viết parser production chỉ dựa vào một thông báo tiếng Anh duy nhất.

### Đọc từ ngoài vào trong

Ví dụ:

~~~text
java.net.ConnectException: ...
  Caused by: javax.net.ssl.SSLHandshakeException: ...
    Caused by: sun.security.validator.ValidatorException: ...
      Caused by: sun.security.provider.certpath.SunCertPathBuilderException:
        unable to find valid certification path to requested target
~~~

Lớp ngoài có thể do HTTP client bọc lại; **root cause** sâu hơn mới gợi ý path-building problem. Ngược lại, `SSLHandshakeException` không phải lúc nào cũng liên quan PKIX: protocol mismatch, TLS alert, SNI, network middlebox và client-auth đều có thể làm handshake thất bại.

## 4. Bước 1: xác định chính xác hai đầu TLS

Trước khi nhập bất kỳ chứng chỉ nào, hãy trả lời:
- **Ứng dụng Java đóng vai client hay server?**
- Java đang gọi **host, port, URL, proxy** nào?
- TLS được chấm dứt ở server đích, reverse proxy, service mesh, ingress hay corporate TLS-inspection gateway?
- Có **mTLS** yêu cầu client certificate hay không?
- Lỗi xuất hiện ở mọi environment hay chỉ container/CI/production?
- Cùng một service chạy trên JDK/build nào? Có load-balancer nhiều backend không?
- Kết nối lỗi qua **hostname** hay gọi trực tiếp địa chỉ IP?
- Có dùng custom `SSLContext`, `TrustManagerFactory`, Netty/OpenSSL provider hoặc thư viện HTTP tự nạp trust material không?

### Client xác minh server (HTTPS thông thường)

~~~text
Java HTTPS client  ──TLS──> Server
       │                    │
       └── dùng TRUSTSTORE  ◄┘ server leaf + intermediate
           để đánh giá chain
~~~

Nếu Java báo `PKIX path building failed` khi gọi HTTPS, thường bắt đầu điều tra ở **truststore phía Java client**, **certificate chain do server trình bày**, và các security constraints.

### Server xác minh client (mutual TLS)

~~~text
Java client                  Java/server gateway
    │                              │
    ├─ gửi client certificate ────>│
    │                              └─ dùng server truststore để tin client CA
    └─ dùng client truststore để tin server CA
~~~

Nếu **server** từ chối client certificate, sửa **truststore phía server/gateway** hoặc chain của **client certificate**, không chỉ nhập certificate vào Java client rồi hi vọng hết lỗi.

**KeyStore không phải TrustStore**: `javax.net.ssl.keyStore` thông thường quản lý credentials/private key của bản thân, còn `javax.net.ssl.trustStore` quản lý certificates được tin. Cả hai có thể dùng API `KeyStore` về cấu trúc, nhưng **vai trò TLS khác nhau**.

## 5. Bước 2: xác định Java thực sự dùng truststore nào

Trong SunJSSE khi dùng **default TrustManagerFactory** và không tự tạo trust manager tùy chỉnh, nguồn trust material được chọn theo thứ tự:

1. Nếu có system property **`javax.net.ssl.trustStore`**, sử dụng tệp được chỉ định và các tùy chọn `trustStoreType`/`trustStorePassword` tương ứng.
2. Nếu property đó **không được đặt**, ưu tiên **`java.home/lib/security/jssecacerts`** nếu có.
3. Nếu không có `jssecacerts`, dùng **`java.home/lib/security/cacerts`** nếu có.
4. Nếu không có truststore phù hợp, SunJSSE có thể khởi tạo trust material rỗng.

**Bẫy đặc biệt:** Nếu `javax.net.ssl.trustStore` **được đặt nhưng trỏ tới file không tồn tại**, SunJSSE có thể dùng **truststore rỗng**, **không tự fallback sang cacerts**. Một lỗi gõ sai path có thể khiến hàng trăm HTTPS destinations ngừng hoạt động.

Đây là **hành vi SunJSSE reference implementation** theo tài liệu JDK 25, không được bảo đảm áp dụng nguyên xi cho mọi provider hoặc một `SSLContext` được ứng dụng tự khởi tạo.

### JDK nào mới là JDK đang chạy?

`java -version` trong terminal có thể khác:
- JRE/JDK được embedded trong app server;
- Runtime nằm trong container image;
- Gradle/Maven toolchain;
- IDE launcher;
- JVM chạy bởi service manager;
- Một image distroless không có `keytool`.

Muốn biết trong chính ứng dụng, có thể đọc `System.getProperty("java.home")` và `System.getProperty("java.version")`. Đừng sửa `cacerts` của JDK A nếu process đang dùng JDK B.

### Vấn đề truststore tùy chỉnh chỉ chứa CA nội bộ

Khi chỉ định:

~~~bash
-Djavax.net.ssl.trustStore=/secure/app-truststore.p12
~~~

JSSE **không mặc định gộp** tệp này với toàn bộ public CAs từ `cacerts`. Nếu tệp chỉ có CA của một hệ thống nội bộ, những HTTPS destinations khác dùng CA công cộng có thể thất bại.

**Hướng vận hành:** quản lý truststore theo nguyên tắc tối thiểu, giữ đúng các trust anchors cần thiết cho những destinations ứng dụng thật sự gọi. Nếu cần cả public và private trust roots, phải xây dựng trust material hoặc `SSLContext` để có cả hai **một cách có chủ đích và có kiểm chứng**.

### Những vấn đề thường làm kho trust sai

- Path tương đối nhưng working directory khác nhau;
- Kubernetes volume/Secret không được mount đúng;
- Symlink `cacerts` trỏ đến file của distro khác;
- Password/type sai hoặc không thể mở kho;
- Certificate nằm trong keystore chứ không phải truststore;
- Imported vào JDK khác hoặc image layer bị thay khi redeploy;
- `jssecacerts` tồn tại và ưu tiên cao hơn `cacerts`;
- Ứng dụng tự xây `SSLContext`, bỏ qua system properties mặc định.

## 6. Bước 3: kiểm tra certificate chain thực sự được trình bày

Có nhiều cách quan sát, nên dùng nhiều nguồn đối chiếu.

### 6.1. Dùng OpenSSL quan sát endpoint

Ví dụ với hostname giả định **`api.example.org`**:

~~~bash
openssl s_client -connect api.example.org:443 -servername api.example.org -showcerts
~~~

Các tùy chọn:
- `-connect`: host và port được kết nối.
- `-servername`: gửi **SNI** để server chọn đúng virtual host certificate.
- `-showcerts`: in các certificate server gửi trong TLS handshake.

**Quan trọng:** Lệnh `s_client` in chain không chứng minh Java tin chain đó. OpenSSL thường dùng kho CA của hệ điều hành hoặc đường dẫn cấu hình khác, không phải truststore Java. Một handshake có thể hoàn tất trong khi verify result vẫn báo lỗi, tùy flags và chính sách OpenSSL. Không dùng việc “OpenSSL kết nối được” thay cho kiểm tra JSSE trust path.

Nếu muốn OpenSSL **dừng khi xác thực certificate thất bại** trong một test có CA file xác minh riêng:

~~~bash
openssl s_client -connect api.example.org:443 -servername api.example.org -CAfile trusted-roots.pem -verify_return_error
~~~

Lệnh này chỉ có ý nghĩa nếu **`trusted-roots.pem`** là tệp CA do bạn quản lý và đã kiểm tra nguồn/fingerprint. Nó vẫn **không đại diện hoàn toàn cho chính sách Java**.

### 6.2. Dùng `keytool` lấy certificate từ TLS server

Trên một JDK có `keytool`:

~~~bash
keytool -printcert -sslserver api.example.org:443 -v
~~~

Điều này cho phép quan sát certificate được phía server trình bày, subject, issuer, fingerprint, validity, extensions. Với một certificate file có sẵn:

~~~bash
keytool -printcert -file server-leaf.pem -v
~~~

**Các lệnh trên để xem**, không nhập certificate vào kho tin cậy. Nếu bạn chưa có file `server-leaf.pem`, nó phải được lấy từ nguồn được kiểm soát; đừng lấy file bất kỳ rồi tin.

### 6.3. Cần đối chiếu trường nào?

| Trường X.509 | Cách dùng để chẩn đoán |
| --- | --- |
| **Subject** | Chủ thể của certificate |
| **Issuer** | CA đã ký certificate; hỗ trợ nối chuỗi |
| **Subject Alternative Name (SAN)** | Tên DNS/IP được certificate xác nhận |
| **Validity** | `notBefore`, `notAfter`; đối chiếu thời gian hệ thống |
| **Basic Constraints** | Intermediate/root phải được phép làm CA |
| **Key Usage / Extended Key Usage** | Certificate có phù hợp TLS server/client authentication không |
| **Authority Key Identifier (AKI)** | Gợi ý CA phát hành/khớp với SKI |
| **Subject Key Identifier (SKI)** | Giúp phân biệt CA có subject tương tự |
| **Signature Algorithm / Public Key** | Đánh giá thuật toán/key strength và chính sách hiện hành |
| **SHA-256 fingerprint** | So với fingerprint đáng tin từ CA hoặc quản trị viên |

**Tên issuer trùng với subject của CA chưa đủ bảo đảm chuỗi đúng.** Cần public-key/signature verification, extensions, chain constraints và trust anchor. Có thể tồn tại nhiều certificates cùng subject hoặc các đường cross-signing khác nhau.

### 6.4. Vì sao cùng hostname có nhiều chain?

- Load balancer dùng các backends có cấu hình khác nhau;
- Reverse proxy/server gửi thiếu intermediate;
- CA rollover hoặc cross-signing;
- SNI chọn certificate khác khi dùng IP hoặc host alias;
- TLS-inspection proxy chèn certificate mới;
- CDN/edge thay certificate theo khu vực;
- Server vừa deploy certificate nhưng một node chưa cập nhật.

Một `openssl s_client` chạy từ laptop của bạn có thể đi tới endpoint khác với JVM trong pod. **Test từ cùng network path/environment**, chọn đúng hostname và proxy, trước khi kết luận.

## 7. Bước 4: bật JSSE và PKIX debug an toàn

Khi cần xác định Java đã nạp kho nào và đang xét chain nào, dùng các system properties đã được tài liệu hóa.

### 7.1. JSSE: handshake và trust manager

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar app.jar
~~~

Mục đích:
- Quan sát các bước TLS handshake;
- Xem TrustManager được khởi tạo và truststore đã nạp;
- Đọc certificate chain phía server và các quyết định của JSSE.

**Không mặc định dùng `-Djavax.net.debug=all` trong production**. Output có thể rất lớn, tốn CPU/I/O và chứa thông tin nội bộ về certificates, server names và handshake. Hạn chế phạm vi log, quyền truy cập và thời gian bật. Các tùy chọn như `data`, `packet` hoặc `plaintext` có thể in dữ liệu nhạy cảm ở mức thấp — không bật tùy tiện.

### 7.2. Security provider: PKIX path builder/validator

~~~bash
java -Djava.security.debug=certpath -jar app.jar
~~~

Thuộc tính này hỗ trợ debug việc xây dựng và xác minh certification path, thường giúp nhận diện nguyên nhân như:
- Không tìm thấy issuer certificate phù hợp;
- Không đến được trusted anchor;
- Constraint bị từ chối;
- Invalid/expired certificate;
- Các bước PKIX path discovery không thành công.

Có thể kết hợp nếu cần chẩn đoán có kiểm soát:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -Djava.security.debug=certpath -jar app.jar
~~~

**Đừng hiểu log ở trên là output bất biến**: định dạng, tên logger và nội dung có thể khác theo JDK/provider. Hãy tìm **trustStore path**, danh sách trusted certs, certificate subject/issuer, GC? Không: đây là **TLS/PKIX**, hoàn toàn khác GC.

### 7.3. Debug không thay việc quản lý trust

Debug chỉ giúp nhìn dữ liệu, **không tự sửa lỗi**. Kể cả log hiển thị nhiều root CA được nạp, vẫn phải kiểm tra **đúng root chain của endpoint** có mặt và hợp lệ theo security policy hay không.

Khi lưu log cho incident:
- Ghi lại **JDK build**, hostname/port, request time;
- Thu log chỉ quanh một lần handshake lỗi;
- Loại trừ hoặc bảo vệ secrets;
- Giữ full causal chain từ application error;
- Phân loại kết luận thành **đã xác nhận** và **cần kiểm tra**.

## 8. Bước 5: kiểm tra truststore bằng `keytool`

### 8.1. Xem kho CA mặc định của JDK đang dùng

~~~bash
keytool -list -cacerts
~~~

Nếu cần chi tiết certificate:

~~~bash
keytool -list -v -cacerts
~~~

**`-cacerts`** là tùy chọn được hỗ trợ; nó truy cập kho CA mặc định của **JDK sở hữu `keytool` đang chạy**. Hãy dùng `keytool` từ **cùng JDK với JVM đích**. Trên một số bản phân phối, `cacerts` có thể được quản lý hoặc symlink từ truststore hệ điều hành; không giả định nội dung giống nhau giữa tất cả vendors.

### 8.2. Xem kho ứng dụng

~~~bash
keytool -list -v -keystore /secure/app-truststore.p12 -storetype PKCS12
~~~

Nếu kho được bảo vệ, `keytool` có thể yêu cầu password. Không ghi password thật vào tài liệu, source, shell history hoặc command line. Nơi cất credential phải tuân thủ chính sách tổ chức.

Khi chỉ kiểm tra một alias:

~~~bash
keytool -list -v -keystore /secure/app-truststore.p12 -storetype PKCS12 -alias org-root-ca
~~~

Đối chiếu:
- **Alias** của trusted CA;
- **Entry type** (thường `trustedCertEntry` cho trust anchor);
- **Subject, issuer, validity**;
- **SHA-256 fingerprint** với bản công bố qua kênh đáng tin;
- **BasicConstraints** và chain phù hợp;
- Cả những trust anchors khác mà ứng dụng cần khi kết nối ra ngoài.

### 8.3. Đừng vội nhập leaf certificate

Nếu server certificate thay hằng năm hoặc thay theo môi trường, import **leaf** làm trusted entry có thể khiến hệ thống phụ thuộc vào chính leaf cụ thể và lại lỗi lúc rotation. Ngoài ra, tin leaf của một endpoint mà không xác định ownership/fingerprint có thể tạo rủi ro MITM.

**Thông thường ưu tiên:**
1. Sửa server để gửi **đúng leaf + intermediate chain**.
2. Nếu tổ chức thực sự sử dụng **private CA**, phân phối **đúng CA/root certificate được xác minh** tới những clients cần tin.
3. Chỉ dùng certificate pinning hoặc tin một leaf cụ thể theo một cơ chế được thiết kế riêng, có kế hoạch rotation và risk review.

**Đừng nhập certificate chỉ vì nó xuất hiện trong kết nối đang lỗi**, vì có thể bạn đang thấy chain do proxy/tấn công/định tuyến sai.

## 9. Các nguyên nhân chính và hướng xử lý đúng

### 9.1. Thiếu root CA tin cậy

Ví dụ server dùng CA nội bộ `Org Root CA`, còn Java client chỉ có public CAs.

~~~text
Java truststore: public roots
Server chain: leaf ← Org Intermediate ← Org Root
Org Root chưa được cho phép tin
→ không có trust anchor phù hợp
~~~

**Cách xử lý:**
- Xác minh CA chain bằng kênh nội bộ đáng tin;
- So SHA-256 fingerprint với CA owner;
- Đưa CA thích hợp vào application truststore hoặc trust configuration đã phê duyệt;
- Khởi động lại/refresh `SSLContext` theo cách ứng dụng hỗ trợ;
- Test lại endpoint và các HTTPS destinations khác.

**Không sửa bằng `TrustManager` trả true cho mọi certificate**.

### 9.2. Server gửi thiếu intermediate

Client đã tin root, nhưng server chỉ gửi leaf, không có intermediate. Một số client xây dựng được chain bằng cache/AIA, nhưng không thể dựa vào hành vi ấy ở mọi Java runtime.

**Khắc phục ưu tiên từ phía server:** cấu hình server/reverse proxy/CDN gửi **leaf + intermediate(s)** đúng thứ tự và đúng CA path. Thường không cần gửi root tự ký.

Không xem việc import intermediate vào **mọi client** là thay thế bền vững cho server chain bị thiếu, trừ khi đó là thiết kế trust có chủ đích.

### 9.3. Java dùng nhầm truststore hoặc tệp rỗng

Ví dụ:
- JVM dùng `/opt/app/conf/truststore.p12` nhưng bạn import CA vào `$JAVA_HOME/lib/security/cacerts`;
- Property trustStore bị gõ nhầm path và SunJSSE nhận kho rỗng;
- Có `jssecacerts` làm kho mặc định khác `cacerts`;
- Secret volume chưa mount đúng;
- Docker image trong production không giống image local.

**Khắc phục:** đọc JSSE debug/VM properties, xác định đúng process, path, store type, password, quyền và nội dung trust anchors; sửa deployment và xác minh sau restart.

### 9.4. TLS interception / proxy nội bộ

Một enterprise gateway có thể **chấm dứt TLS và ký lại server certificate** bằng private enterprise CA. Browser có thể tin enterprise CA do OS được quản lý, còn JDK container chưa có.

**Khắc phục:** xác minh proxy này là thành phần hợp lệ được tổ chức phê duyệt, lấy CA certificate qua kênh tin cậy, cấu hình trust đúng phạm vi. Nếu proxy không được mong đợi, điều tra mạng và bảo mật — không nhập certificate nghi ngờ chỉ để kết nối thành công.

### 9.5. Sai hostname/SAN hoặc SNI

Ví dụ gọi `https://10.0.0.10/` trong khi certificate chỉ có SAN `api.example.org`. Hoặc không gửi SNI nên load balancer trả certificate của virtual host khác.

**Khắc phục:** gọi hostname đúng được SAN bao phủ; dùng SNI đúng; cấu hình server certificate phù hợp. **Đừng tắt hostname verification.** Lỗi này có thể xảy ra dù PKIX path đã hợp lệ.

### 9.6. Chứng chỉ hết hạn, chưa hiệu lực hoặc đồng hồ sai

Kiểm tra `notBefore`/`notAfter` ở **leaf và CA certificates**; kiểm tra thời gian của client/server. Chứng chỉ mới triển khai nhưng clock lệch vẫn có thể bị coi là chưa hiệu lực.

**Khắc phục:** renew/reissue certificates, đồng bộ clock, deploy chain đúng. Đừng thay đổi clock JVM bằng các mẹo không an toàn để bỏ qua validity.

### 9.7. Thuật toán/key size bị JDK chặn

JDK mới có security policies từ file `java.security`, ví dụ:
- `jdk.certpath.disabledAlgorithms`;
- `jdk.tls.disabledAlgorithms`.

Một certificate chain dùng thuật toán yếu hoặc key quá ngắn có thể bị từ chối dù CA đã có trong truststore.

**Khắc phục:** cấp lại certificate/CA bằng thuật toán và kích thước khóa được hỗ trợ theo chính sách hiện hành, nâng cấp server/client configuration. **Không hạ chính sách mã hóa toàn cục** chỉ để phục hồi một endpoint mà chưa đánh giá rủi ro.

### 9.8. Revocation checking

Nếu môi trường đã bật hoặc yêu cầu kiểm tra **OCSP/CRL**, PKIX validation có thể thất bại vì:
- Certificate thực sự bị revoked;
- OCSP responder/CRL endpoint không truy cập được;
- Proxy/firewall/DNS ngăn truy vấn;
- Dữ liệu trạng thái quá hạn;
- Chính sách fail-open/fail-closed khác nhau.

**Khắc phục:** xem log certpath/OCSP, xác minh thực trạng thu hồi và khả năng truy cập endpoint theo chính sách. **Không tắt revocation checking một cách mặc định.**

### 9.9. CA rollover, cross-signing và chain khác nhau

Một CA có thể đổi intermediate, root hoặc ký chéo. Server có thể gửi chain đi tới một root được browser tin nhưng không nằm trong Java truststore của một JDK cũ.

**Khắc phục:** đối chiếu trust anchor thực, issuer/AKI/SKI, CA rollover plan và phiên bản JDK được hỗ trợ. Tránh import ngẫu nhiên nhiều cross-signed certs mà không biết chúng dẫn tới trust anchor nào.

### 9.10. Mutual TLS bị chẩn đoán nhầm phía

Trong mTLS, có **hai hướng xác thực**. Client có thể tin server nhưng server không tin client CA, hoặc ngược lại.

**Khắc phục:** xác định peer phát ra alert, truststore của phía đó, certificate chain của phía còn lại và EKU `clientAuth`/`serverAuth` thích hợp. Một `bad_certificate` không chứng minh phải sửa public CA truststore của Java client.

## 10. Quy trình sửa an toàn cho private CA

Giả sử một hệ thống nội bộ dùng **Org Root CA** thực sự do tổ chức quản lý. Người vận hành đã nhận file `org-root-ca.pem` từ **kênh đáng tin** và đối chiếu fingerprint độc lập.

### 10.1. Kiểm tra certificate trước khi tin

~~~bash
keytool -printcert -file org-root-ca.pem -v
~~~

Xác nhận:
- Subject và issuer;
- `BasicConstraints CA=true`;
- Thời hạn;
- SHA-256 fingerprint với tài liệu của CA owner;
- Mục đích và phạm vi tin cậy.

**Không đưa vào truststore một file được tải ngẫu nhiên từ chính endpoint đang bị lỗi** mà chưa xác minh. Nhập CA tạo quyền tin cậy cho những certificates CA đó phát hành.

### 10.2. Tạo truststore riêng cho ứng dụng

Ví dụ tạo file **PKCS12** dành riêng cho ứng dụng:

~~~bash
keytool -importcert -alias org-root-ca -file org-root-ca.pem -keystore app-truststore.p12 -storetype PKCS12
~~~

`keytool` có thể hỏi password và xác nhận tin cậy. **Đừng tự động bỏ prompt bằng `-noprompt`** khi chưa có quy trình xác minh fingerprints.

Kiểm tra kết quả:

~~~bash
keytool -list -v -keystore app-truststore.p12 -storetype PKCS12 -alias org-root-ca
~~~

**Lưu ý giới hạn:** Truststore mới được tạo từ đầu ở bước này **chỉ chứa entries đã được bạn đưa vào**, không mặc định kế thừa toàn bộ public CAs từ `cacerts`. Nếu ứng dụng còn gọi các dịch vụ công cộng, cần thiết kế trust material đáp ứng **cả những roots đã được phê duyệt khác** mà ứng dụng cần.

### 10.3. Cho Java sử dụng truststore đó

Ví dụ cú pháp khởi động:

~~~bash
java -Djavax.net.ssl.trustStore=/secure/app-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -jar app.jar
~~~

Cần cung cấp password/credential nếu runtime/protection policy đòi hỏi, theo cơ chế bảo mật của hệ thống. **Không đưa password thật vào source, container image, public logs hay command history**. Nếu hệ thống dùng custom `SSLContext`, phải sửa cách tạo `TrustManagerFactory` tương ứng; system properties có thể không được nó sử dụng.

### 10.4. Test lại và bảo đảm không có regression

- Restart hoặc refresh TLS context theo cách ứng dụng cho phép;
- Bật JSSE debug tạm để xác nhận tệp đã được nạp;
- Kiểm tra kết nối tới service nội bộ đã sửa;
- Test các HTTPS destinations khác mà ứng dụng cần;
- Ghi log exception chain thực;
- Xác nhận hostname verification, TLS protocol restrictions và revocation policy vẫn có hiệu lực;
- Giữ quy trình certificate rotation/expiry monitoring.

**Không sửa trực tiếp `cacerts` toàn cục của JDK nếu không có lý do quản trị rõ ràng.** Một truststore riêng quản lý theo deployment thường dễ kiểm soát quyền và rollback hơn. Khi cập nhật base image JDK, mọi thay đổi thủ công vào JDK cũ còn có nguy cơ bị mất.

## 11. Phân biệt lỗi path builder với hostname verification

Đây là chỗ thường bị nhầm.

### Case A: chain không thể đến root được tin

~~~text
Server leaf → Intermediate A → Root B
Java trust anchors: Root C
Result: no acceptable trust anchor
→ PKIX path building failure có thể xảy ra
~~~

Ở đây chưa cần tranh luận SAN. Vấn đề đầu tiên là đường tin cậy.

### Case B: chain có trust anchor nhưng hostname sai

~~~text
Server certificate chain: hợp lệ tới Root A
Requested URL: https://api.example.org/
Certificate SAN: other.example.org
Result: hostname identity mismatch
~~~

**Nhập Root A một lần nữa không sửa hostname mismatch.** Phải cấp đúng certificate hoặc dùng đúng hostname.

### Case C: chain được tìm thấy nhưng thuật toán bị cấm

~~~text
Root CA: được tin
Intermediate/leaf: dùng thuật toán bị security policy từ chối
Result: path validation/build bị từ chối
~~~

**Root được tin không miễn trừ mọi kiểm tra an toàn**. Tên chính xác của exception phụ thuộc validator/builder và thời điểm constraint được kiểm tra.

### Case D: certificate chain đúng nhưng backend trả certificate khác

Nếu một server có nhiều hostnames, test bằng IP không SNI có thể lấy default certificate, còn Java client kết nối bằng hostname có SNI nhận certificate đúng, hoặc ngược lại.

**Luôn kiểm tra đúng hostname, port, SNI và network path** thay vì so sánh những endpoints khác nhau.

## 12. Chẩn đoán trong container, CI, proxy và cloud

### Container image có `cacerts` khác host

Image Java có thể đi kèm CA bundle khác host, có symlinks hoặc cơ chế đồng bộ CAs của distro. **Cập nhật truststore của host không tự đảm bảo Java container đã nhận CA mới**.

Xác minh ở chính container:
- `java.home` và JDK build;
- Path truststore;
- Secret/config volume mount;
- Danh sách aliases và fingerprint của trust anchors;
- Network/proxy egress của container.

### CI runner khác máy developer

CI có thể dùng:
- Image JDK cũ;
- Corporate MITM proxy;
- Thiếu CA bundle nội bộ;
- Variables `JAVA_TOOL_OPTIONS` khác;
- Một truststore tùy chỉnh rỗng do Secret chưa được inject.

**Không copy toàn bộ truststore cá nhân vào CI**. Phân phối CA được phê duyệt qua secret/config management và giữ quy trình rotation.

### HTTP client có SSLContext riêng

Một ứng dụng dùng Apache HttpClient, OkHttp, Netty, Reactor Netty hoặc thư viện riêng có thể thiết lập TLS provider/trust manager khác default JSSE.

**Vì vậy:** `-Djavax.net.ssl.trustStore` không bảo đảm có tác dụng nếu thư viện đã nhận một `SSLContext` hoặc `TrustManager` tùy chỉnh. Phải xem code/config thực, không chỉ thêm system property.

### Hệ thống nhiều endpoints

Nếu lỗi chỉ với một hostname hoặc một node load balancer:
- Đối chiếu fingerprint và chain ở từng backend;
- Kiểm tra deploy certificate/chain đồng nhất;
- Xem DNS, resolver, proxy, SNI và TLS termination;
- Ghi hostname/port/remote endpoint tương ứng lúc lỗi.

Một endpoint đúng **không chứng minh tất cả backend đúng**.

## 13. Chương trình Java 17+ độc lập: phân loại tín hiệu PKIX

Ví dụ sau có **hai chế độ**:
1. Mặc định dùng dữ liệu lỗi **giả lập** để phân loại 7 trường hợp. Stdout **cố định**, không cần mạng hay chứng chỉ thật.
2. Truyền một HTTPS URL làm đối số để **thử kết nối bằng Java HttpClient** với trust configuration của JVM đó, rồi in kết quả hoặc exception cause chain. Phần này **phụ thuộc môi trường**, không có stdout cố định.

Đây là công cụ **gợi ý nhóm điều tra**, không phải trình xác minh PKIX đầy đủ. Nó **không bypass TLS**, không thay truststore và không nhập CA nào.

Tạo file **PkixTrustChainDiagnosisDemo.java**:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Locale;

public class PkixTrustChainDiagnosisDemo {

    record Example(String label, String message) {}

    static String classify(String message) {
        String s = message.toLowerCase(Locale.ROOT);

        if (s.contains("trustanchors parameter must be non-empty")) {
            return "EMPTY_TRUST_ANCHORS";
        }
        if (s.contains("certificate has been revoked")) {
            return "REVOKED_CERTIFICATE";
        }
        if (s.contains("algorithm constraints check failed")) {
            return "ALGORITHM_POLICY";
        }
        if (s.contains("no subject alternative dns name matching")) {
            return "HOSTNAME_MISMATCH";
        }
        if (s.contains("validity check failed")
                || s.contains("certificateexpiredexception")
                || s.contains("certificatenotyetvalidexception")) {
            return "CERTIFICATE_VALIDITY";
        }
        if (s.contains("pkix path building failed")
                || s.contains("unable to find valid certification path")) {
            return "PATH_BUILDING_FAILURE";
        }
        return "NEEDS_MORE_EVIDENCE";
    }

    static void showSamples() {
        List<Example> examples = List.of(
            new Example("no trusted path",
                    "SSLHandshakeException: PKIX path building failed: "
                    + "unable to find valid certification path"),
            new Example("empty anchors",
                    "InvalidAlgorithmParameterException: "
                    + "trustAnchors parameter must be non-empty"),
            new Example("expired",
                    "CertPathValidatorException: validity check failed"),
            new Example("hostname",
                    "SSLHandshakeException: No subject alternative DNS "
                    + "name matching api.example.org found"),
            new Example("algorithm",
                    "CertPathValidatorException: "
                    + "Algorithm constraints check failed"),
            new Example("revoked",
                    "CertPathValidatorException: "
                    + "Certificate has been revoked"),
            new Example("other failure",
                    "SSLException: connection closed unexpectedly")
        );

        for (Example e : examples) {
            System.out.println(e.label() + " -> "
                    + classify(e.message()));
        }
    }

    static void probeHttps(String url) {
        System.out.println("=== Live HTTPS probe ===");
        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("java.home="
                + System.getProperty("java.home"));

        String configuredStore =
                System.getProperty("javax.net.ssl.trustStore");
        System.out.println("trustStore property="
                + (configuredStore == null ? "(default)" : configuredStore));

        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .build();

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(10))
                    .GET()
                    .build();

            HttpResponse<Void> response = client.send(
                    request, HttpResponse.BodyHandlers.discarding());

            System.out.println("HTTP status=" + response.statusCode());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.out.println("interrupted");
        } catch (IOException | IllegalArgumentException e) {
            Throwable current = e;
            int level = 0;
            while (current != null && level < 8) {
                String description = current.getClass().getSimpleName()
                        + ": " + current.getMessage();

                System.out.println("cause[" + level + "]=" + description);
                System.out.println("category[" + level + "]="
                        + classify(description));

                current = current.getCause();
                level++;
            }
        }
    }

    public static void main(String[] args) {
        showSamples();

        if (args.length > 0) {
            probeHttps(args[0]);
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 PkixTrustChainDiagnosisDemo.java
java PkixTrustChainDiagnosisDemo
~~~

**Stdout chính xác khi không truyền URL:**

~~~text
no trusted path -> PATH_BUILDING_FAILURE
empty anchors -> EMPTY_TRUST_ANCHORS
expired -> CERTIFICATE_VALIDITY
hostname -> HOSTNAME_MISMATCH
algorithm -> ALGORITHM_POLICY
revoked -> REVOKED_CERTIFICATE
other failure -> NEEDS_MORE_EVIDENCE
~~~

### Giải thích ví dụ

- `PATH_BUILDING_FAILURE` yêu cầu điều tra **server chain và trust anchors**, chưa tự xác định thiếu root hay intermediate.
- `EMPTY_TRUST_ANCHORS` gợi ý kiểm tra kho trống/sai path/khởi tạo trust manager.
- `CERTIFICATE_VALIDITY` gợi ý validity và đồng hồ.
- `HOSTNAME_MISMATCH` là vấn đề hostname/SAN, không nên giải quyết bằng cách tắt hostname verification.
- `ALGORITHM_POLICY` yêu cầu xem certificate algorithm/key size và JDK security properties.
- `REVOKED_CERTIFICATE` là sự cố nghiêm trọng, phải xử lý cấp phát lại/cert rotation theo quy trình.
- `NEEDS_MORE_EVIDENCE` nhắc rằng không có đủ bằng chứng để kết luận.

Chương trình phân loại dựa trên **text patterns của bộ mẫu**, không suy ra kết quả kiểm tra PKIX thực sự. Khi chạy live, phải dùng exception cause chain và debug của JVM để điều tra.

### Chạy thử HTTPS thật (phụ thuộc môi trường)

~~~bash
java PkixTrustChainDiagnosisDemo https://www.example.com/
~~~

Phần đầu vẫn là bảy dòng mẫu. Phần thêm có thể là HTTP status hợp lệ hoặc một chuỗi lỗi mạng/TLS, tùy DNS, firewall, proxy, JDK và truststore. Chương trình **không cam kết trả HTTP 200** và không có stdout cố định cho probe live.

Muốn bật JSSE và PKIX debug cho chính probe này:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -Djava.security.debug=certpath PkixTrustChainDiagnosisDemo https://www.example.com/
~~~

**Giới hạn khi dùng live probe:** Chỉ kết nối tới những endpoints bạn được phép kiểm tra. Debug có thể in certificate metadata hoặc thông tin mạng nội bộ; không chia sẻ nguyên log lên kênh công khai. Chương trình dùng default `HttpClient` TLS context của process; nếu ứng dụng chính sử dụng custom trust manager/proxy, kết quả live probe **có thể khác**.

## 14. Ma trận quyết định chẩn đoán

| Quan sát có bằng chứng | Giả thuyết ưu tiên | Kiểm tra trước | Sửa ở đâu |
| --- | --- | --- | --- |
| Builder không tìm ra path, truststore thiếu CA nội bộ | Thiếu trust anchor | CA fingerprint, truststore được nạp | Trust config phía xác thực |
| Root được tin nhưng server thiếu intermediate | Incomplete server chain | `s_client -showcerts`, AKI/SKI/issuer | Server/ingress/CDN gửi đủ intermediates |
| `trustAnchors ... non-empty` | Kho rỗng/không nạp được | JSSE debug, path/type/password | JVM deployment/truststore |
| Dùng nhầm JDK `cacerts` | Runtime khác shell | `java.home`, JDK/container image | Runtime config |
| Browser chạy, Java lỗi | Kho trust khác nhau hoặc Java constraints | Browser/OS trust vs JSSE trust | Phân tích và cập nhật đúng nơi |
| Chỉ sai một pod/node | Truststore mount/chain khác | Version, Secret, backend cert chain | Image/Secret/server deployment |
| `No subject alternative DNS name matching` | Hostname/SNI sai | URL, SAN, virtual host | Server certificate hoặc endpoint name |
| `Algorithm constraints check failed` | Certificate/key yếu | Certificate signature/key, security policy | Renew/reissue và cập nhật cryptography |
| Certificate expired/not yet valid | Validity/clock | notBefore/notAfter và time sync | CA/server/system time |
| Revocation error | Revoked/status unavailable | OCSP/CRL, policy, egress | CA/PKI/network theo policy |
| TLS proxy ký lại cert | Private proxy CA | Proxy ownership/fingerprint | Managed trust distribution |
| mTLS server báo unknown_ca | Server không tin client CA | Alert direction, client chain | Server truststore/client chain |

**Không chuyển trực tiếp từ “PKIX path building failed” sang “import mọi CA vào cacerts”**. Trước tiên phân loại tại đúng phía và đúng trust material.

## 15. Những việc tuyệt đối không nên làm

### 15.1. Không dùng TrustManager tin mọi certificate

Các ví dụ trên mạng đôi khi triển khai `X509TrustManager` với `checkServerTrusted` rỗng hoặc `checkClientTrusted` rỗng. Điều đó **vô hiệu hóa xác minh danh tính qua certificate chain** và mở đường cho man-in-the-middle attacks.

**Không sử dụng trong production, cũng không nên biến thành thói quen của môi trường test.** Nếu cần test một private CA, hãy tạo CA/test truststore rõ ràng.

### 15.2. Không tắt hostname verification

Các tùy chọn bỏ qua SAN/hostname hoặc trả `true` cho mọi hostname làm client không phân biệt endpoint hợp lệ với endpoint giả mạo.

**Hướng đúng:** cấu hình certificate chứa SAN phù hợp hoặc gọi đúng hostname.

### 15.3. Không import certificate chưa xác minh

Một certificate thấy được từ mạng có thể là của **proxy không mong đợi**, MITM hoặc endpoint khác do DNS/SNI. Chỉ thêm trust anchor từ kênh đáng tin, sau khi đối chiếu fingerprint và ownership.

### 15.4. Không sửa `cacerts` toàn cục vô kiểm soát

Kho tin cậy toàn JVM có thể ảnh hưởng nhiều ứng dụng. Một CA được thêm vào có thể được tin cho nhiều hostname do CA phát hành, không chỉ một service. Dùng application-specific trust material và quản trị change/rollback.

### 15.5. Không hạ chính sách `disabledAlgorithms` tùy tiện

Nếu path bị từ chối vì chữ ký/key size yếu, giải pháp bền vững là **cấp lại certificate** với thuật toán được hỗ trợ theo chính sách cập nhật. Nới lỏng policy toàn JVM có thể làm phát sinh rủi ro cho những endpoints khác.

### 15.6. Không coi browser, curl và OpenSSL là bản sao của JSSE

Chúng có thể dùng trust stores, caches, proxies, validation policies và SNI khác nhau. Một kết quả thành công từ công cụ khác **chỉ là bằng chứng bổ sung**, không thay được test Java process thực.

### 15.7. Không bỏ qua log về expiry/revocation

Một certificate thật sự revoked hoặc hết hạn không nên được “chữa” bằng cách thêm vào kho tin cậy. CA phải phát hành certificate mới và tổ chức phải làm theo quy trình rotation.

## 16. Quy trình production theo thứ tự an toàn

**Giai đoạn 1 — Xác định phạm vi**
1. Ghi thời điểm lỗi, JDK build, endpoint hostname/port, proxy và network path.
2. Xác định Java là client hay server; có mTLS không?
3. Giữ full exception chain; phân loại path-building, validation, hostname hay TLS protocol.
4. Khoanh vùng pods/servers/environments bị ảnh hưởng.

**Giai đoạn 2 — Thu bằng chứng**
5. Dùng JSSE debug ngắn hạn: `ssl,handshake,trustmanager`.
6. Dùng `java.security.debug=certpath` nếu cần phân tích PKIX.
7. Ghi `java.home`, truststore property và actual truststore path/type.
8. Dùng `keytool -list` với kho **đúng process/JDK**, kiểm tra trust anchors.
9. Lấy server chain từ **cùng network path**, đúng SNI/hostname/port.
10. Đối chiếu subject, issuer, AKI/SKI, SAN, validity, fingerprints.
11. Kiểm tra revocation và security constraints nếu exception liên quan.

**Giai đoạn 3 — Xử lý nguyên nhân**
12. Nếu thiếu intermediate: sửa chain ở server/ingress.
13. Nếu thiếu private CA: xác minh và phân phối CA có kiểm soát.
14. Nếu sai truststore: sửa path/type/mount/SSLContext.
15. Nếu hostname mismatch: sửa certificate SAN hoặc endpoint.
16. Nếu expiry/weak algorithm/revocation: xử lý certificate/PKI đúng chính sách.
17. Nếu mTLS: xử lý ở đúng phía xác thực client/server.

**Giai đoạn 4 — Xác minh và rollback**
18. Chạy lại kết nối Java với trust configuration thực.
19. Kiểm tra hostname verification và PKIX constraints vẫn bật.
20. Test cả những outbound HTTPS destinations khác.
21. Kiểm tra rollout trên mọi pod/backend và các môi trường cần thiết.
22. Ghi nhận certificate expiry/rotation và monitoring.
23. Có rollback của Secret/truststore/ingress changes nếu regression.
24. Tắt debug verbose sau khi hoàn tất; bảo vệ log đã thu.

## 17. Những câu hỏi thường gặp

**1. PKIX path building failed có luôn là thiếu root CA?**  
Không. Có thể thiếu intermediate, sai truststore, truststore rỗng, chain constraint không phù hợp hoặc một số nguyên nhân khác.

**2. Chứng chỉ server được trình duyệt tin, tại sao Java báo lỗi?**  
Browser và Java có thể dùng root stores khác nhau; browser có thể cache/fetch intermediate, còn Java dùng JSSE truststore cụ thể và JDK policies riêng.

**3. Server phải gửi root certificate không?**  
Thông thường server gửi leaf và intermediate(s); root thường đã ở phía client. Gửi root không tự làm client tin root.

**4. Cần import leaf hay root/intermediate?**  
Ưu tiên sửa server chain và chỉ import **CA/trust anchor được tổ chức phê duyệt** vào trust material thích hợp. Import leaf có thể gây vấn đề certificate rotation và tăng rủi ro nếu không xác minh kỹ.

**5. `javax.net.ssl.trustStore` đặt sai path thì JVM có tự fallback sang `cacerts` không?**  
Trong SunJSSE reference implementation, nếu property được đặt mà file không tồn tại, trust material có thể trở thành **rỗng**, không fallback như khi property không được đặt.

**6. Tại sao có cả `jssecacerts` và `cacerts`?**  
SunJSSE có cơ chế ưu tiên `jssecacerts` khi không đặt trustStore property, rồi mới xét `cacerts`. Điều này cho phép một kho tin cậy riêng cho JSSE.

**7. Import CA vào `cacerts` nhưng Java vẫn lỗi?**  
Có thể đang sửa JDK khác, JSSE dùng `jssecacerts`/custom truststore, app có custom SSLContext hoặc server chain vẫn sai. Cần debug actual process.

**8. `keytool -printcert -sslserver` có xác nhận Java tin server không?**  
Không. Nó giúp xem certificate từ endpoint; path validation thực phụ thuộc trust material/policy của JVM ứng dụng.

**9. Tại sao OpenSSL thành công mà Java thất bại?**  
Có thể khác CA store, SNI, proxy, algorithms hoặc network path. Phải test Java truststore đúng.

**10. Lỗi No subject alternative DNS name matching có phải thiếu root?**  
Không nhất thiết. Đây là vấn đề hostname identity; import thêm root không sửa SAN.

**11. Nếu certificate hết hạn, có nên import nó vào truststore?**  
Không. Cần renew/rotate và dùng certificate hợp lệ.

**12. Thuật toán bị cấm có được khắc phục bằng trust all không?**  
Không an toàn. Phải dùng thuật toán/key size được chính sách hiện hành chấp nhận.

**13. Có nên bật `javax.net.debug=all` trên production lâu dài?**  
Không. Debug có thể rất nhiều và chứa thông tin nhạy cảm; dùng tags cần thiết trong thời gian ngắn.

**14. Revocation error có nghĩa certificate chắc chắn bị revoked không?**  
Không. Phân biệt “revoked” với “unable to determine revocation status”; điều tra OCSP/CRL và policy.

**15. Trong mTLS, server báo unknown_ca thì sửa truststore nào?**  
Phải xem alert direction; thường cần kiểm tra **trust anchors của phía đang xác minh certificate đối tác**, có thể là server đang xác minh client CA.

**16. Tại sao đổi JDK làm xuất hiện lỗi PKIX?**  
Bản JDK mới có thể khác danh sách root CAs hoặc các ràng buộc thuật toán, trong khi bản cũ đã tin một CA/chain khác. Cần đọc release notes/security properties và kiểm chứng root.

**17. Tại sao chỉ một backend load balancer lỗi?**  
Các backend có thể triển khai certificate/intermediate chain khác nhau. Phải kiểm tra từng đường kết nối thực.

**18. Có thể dùng certificate pinning thay thế truststore không?**  
Đó là cơ chế thiết kế riêng với yêu cầu quản lý vòng đời, rotation và threat model; không phải mẹo ngắn để bỏ qua PKIX.

**19. Có cần restart sau khi đổi truststore không?**  
Phụ thuộc cách ứng dụng tạo và cache `SSLContext`/`TrustManager`. Đừng giả định JSSE tự hot-reload mọi tệp; restart/refresh theo cơ chế được hỗ trợ rồi test.

**20. Làm sao biết đã sửa đúng nguyên nhân?**  
Kết nối Java thành công với chain/hostname/policy đúng, không có trust-all, các destinations khác vẫn hoạt động, và logs cho thấy truststore/CA thực được nạp.

## 18. Tổng kết

- Lỗi **`PKIX path building failed`** nghĩa Java không dựng được **đường chứng chỉ hợp lệ tới trust anchor** theo dữ liệu/cấu hình hiện tại; **không tự kết luận** là thiếu root CA.
- Phân biệt **leaf, intermediate, root CA** và **trust anchor**. Server thường gửi **leaf + intermediate**, client giữ **root/trust anchors** đáng tin.
- Kiểm tra **truststore của đúng JVM process**, nhất là `javax.net.ssl.trustStore`, `jssecacerts` và `cacerts`. Một file path sai có thể tạo trust material rỗng.
- Dùng `openssl s_client` với SNI hoặc `keytool -printcert -sslserver` để quan sát server chain, nhưng **không dùng chúng thay chứng minh JSSE trust**.
- Dùng `-Djavax.net.debug=ssl,handshake,trustmanager` và `-Djava.security.debug=certpath` có kiểm soát.
- Phân biệt thiếu CA/intermediate, hostname mismatch, expiry, thuật toán bị hạn chế, revocation, proxy TLS inspection và **mTLS direction**.
- **Sửa nguyên nhân thật**: hoàn chỉnh server chain, phân phối CA đã xác minh, sửa truststore/mount/SSLContext, cấp lại certificate đúng SAN và thuật toán.
- **Không tắt TLS verification hoặc import certificate không xác minh**. Dùng truststore riêng, có kiểm soát thay đổi, monitoring certificate rotation và rollback.

**Nguồn tài liệu chính thức, còn áp dụng:**
- [Oracle Java SE 25 — Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html).
- [Oracle Java SE 25 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/25/security/java-pki-programmers-guide.html).
- [Oracle Java SE 25 — keytool Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html).
- [Oracle Java SE 25 — java.security.debug system property](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/doc-files/debug-system-property.html).
- [Oracle Java SE 25 — Security Properties File, algorithm restrictions](https://docs.oracle.com/en/java/javase/25/security/security-properties-file.html).
- [IETF RFC 5280 — PKIX Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280).
- [IETF RFC 6125 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc6125).
