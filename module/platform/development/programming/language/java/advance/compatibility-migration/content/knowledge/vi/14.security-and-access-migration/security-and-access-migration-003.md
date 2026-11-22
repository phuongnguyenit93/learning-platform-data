# Truststore, chứng chỉ gốc và chuỗi chứng chỉ máy chủ

Khi nâng cấp JDK, một ứng dụng Java từng kết nối HTTPS bình thường có thể đột ngột gặp lỗi `SSLHandshakeException`, `PKIX path building failed` hoặc `certificate_unknown`. Các lỗi này không nhất thiết cho thấy mã nghiệp vụ thay đổi. Chúng có thể phát sinh vì **truststore của runtime mới khác runtime cũ**, root CA không còn được tin cậy, máy chủ không gửi đủ intermediate certificates, certificate đã hết hạn, hostname không khớp, hoặc chính sách bảo mật của JDK mới từ chối thuật toán mật mã cũ.

Hiểu đúng **truststore**, **root CA** và **server certificate chain** giúp phân biệt lỗi thuộc về cấu hình Java client, máy chủ TLS, hệ thống PKI hay đường mạng trung gian. Trong quá trình **Java Advance Compatibility Migration**, việc khắc phục phải giữ nguyên mục tiêu bảo mật: xác thực server đúng danh tính, kiểm tra đường chứng chỉ hợp lệ và không vô hiệu hóa việc kiểm tra chỉ để request trả về thành công.

Bài học này giải thích các khái niệm, cấu trúc PKIX/JSSE, cách khảo sát bằng `keytool` và `openssl`, thiết lập truststore riêng, xử lý mTLS và quy trình xác minh khi đổi phiên bản JDK.

## 1. Vì sao cùng một endpoint chạy trên JDK cũ nhưng lỗi trên JDK mới?

Giả sử một Java service kết nối:

~~~text
Java application
       |
       | HTTPS
       v
https://inventory.internal.example:8443
       |
       v
TLS terminator / application server
~~~

Ở JDK 8, hệ thống chạy bình thường. Khi chuyển sang image JDK 17, client báo:

~~~text
javax.net.ssl.SSLHandshakeException:
    PKIX path building failed:
    sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
~~~

Đây là dấu hiệu Java chưa tìm được **đường chứng chỉ tin cậy phù hợp** từ server certificate đến trust anchor mà client chấp nhận. Nguyên nhân cụ thể có thể là:

- Runtime cũ đã được thêm private root CA của doanh nghiệp, image JDK mới chưa có.
- Java app đọc truststore khác do đường dẫn, JVM property hoặc container mount thay đổi.
- Server chỉ gửi leaf certificate, bỏ thiếu intermediate CA.
- TLS inspection proxy cấp lại certificate theo một enterprise CA mà client chưa tin.
- Load balancer trả certificate chain khác nhau theo SNI hoặc backend node.
- Một certificate trong chain đã hết hạn hoặc không phù hợp constraints.
- JDK mới áp dụng chính sách key/signature algorithm mạnh hơn.

Không nên sửa bằng cách chấp nhận mọi certificate. Trước tiên phải xác định **server thực sự gửi gì** và **Java client thực sự tin gì**.

## 2. Các khái niệm cơ bản

| Thuật ngữ | Diễn giải |
|---|---|
| Leaf / end-entity / server certificate | Chứng chỉ xác nhận danh tính một server hoặc TLS endpoint |
| Intermediate CA certificate | Chứng chỉ của CA trung gian được một CA cấp cao hơn ký |
| Root CA certificate | Thường là chứng chỉ CA tự ký ở đỉnh của hệ PKI |
| Certificate chain | Dãy chứng chỉ tạo liên kết xác thực từ leaf tới CA cao hơn |
| Trust anchor | Chứng chỉ CA hoặc điểm tin cậy được validator chủ động chấp nhận |
| Truststore | Nguồn trust anchors mà một TrustManager có thể sử dụng |
| Keystore | Kho khóa/chứng chỉ; thường dùng chứa private key và identity certificate |
| JSSE | Java Secure Socket Extension, cơ chế TLS/SSL của Java |
| PKIX | Mô hình xây dựng và xác thực đường chứng chỉ X.509 |
| TrustManager | Thành phần phía Java kiểm tra certificate được peer trình |
| KeyManager | Thành phần lựa chọn certificate/private key của bên Java khi cần trình danh tính |
| Hostname verification | Kiểm tra certificate có đại diện cho hostname/IP mà client gọi không |

**Truststore không có nghĩa chứa tất cả leaf certificates mà ứng dụng từng gặp.** Trường hợp thông thường, truststore chứa các root CA đã được phê duyệt hoặc trust anchors khác theo policy. Server cung cấp leaf và intermediate để client dựng đường tới một anchor đó.

**Root CA không phải luôn là trust anchor duy nhất có thể cấu hình.** Một CA intermediate được chọn làm trust anchor riêng trong một phạm vi tin cậy nhất định cũng là khả năng kỹ thuật; tuy nhiên lựa chọn đó phải theo chính sách của hệ thống PKI và không được thực hiện tùy tiện để né lỗi.

**Keystore và truststore khác về vai trò** dù đều có thể được biểu diễn bằng `JKS` hoặc `PKCS12`. Keystore identity thường chứa private key; truststore chứa public trust material. Nếu client chỉ cần xác thực server qua HTTPS một chiều thì thường không cần client private key.

## 3. Chuỗi chứng chỉ hoạt động như thế nào?

Một chain cơ bản:

~~~text
                Java client
              +------------------+
              |  Truststore      |
              |  Root CA (R)     |   <- Trust anchor đã phê duyệt
              +------------------+
                        ^
                        | Intermediate được Root ký
                        |
              +------------------+
              | Intermediate CA  |
              |       (I)        |
              +------------------+
                        ^
                        | Leaf được Intermediate ký
                        |
              +------------------+
              | Server cert (S)  |
              | SAN: api.example |
              +------------------+
                        ^
                        |
                 TLS server gửi
                 [ S, I ] thường
~~~

Khi thiết lập kết nối TLS, server thường gửi **leaf certificate kèm các intermediate certificates cần thiết**. Server không bắt buộc gửi root certificate; việc server gửi một root không khiến root đó được client tin cậy. Sự tin cậy phải bắt nguồn từ cấu hình của client.

Để có path hợp lệ, bên xác thực cần chứng minh được liên hệ chữ ký giữa các certificate; đồng thời phải kiểm tra validity, CA constraints, key usage, chính sách thuật toán và những quy tắc PKIX liên quan.

Ví dụ thiếu intermediate:

~~~text
Server cung cấp:      [Leaf S]
Client truststore:    [Root R]
Mắt xích còn thiếu:   [Intermediate I]

S -> I -> R không dựng được nếu client không có I
~~~

Một vài môi trường có cache hoặc cơ chế tìm intermediate qua AIA, nhưng **không được mặc định Java luôn tải intermediate tự động từ URL ghi trong certificate**. Server phải được cấu hình chain đầy đủ tương ứng với deployment.

### 3.1. Certificate chain không phải một danh sách bất kỳ

Một máy chủ có thể gửi nhiều certificates nhưng chưa chắc tất cả tạo thành đường tin cậy. Có thể có intermediate sai issuer, certificate hết hạn, chain theo cross-sign khác với trust anchors của Java, hoặc extension không phù hợp. Không thể chỉ đếm số certificate và kết luận chain hợp lệ.

### 3.2. Cross-signed certificate

Một intermediate hoặc root có thể xuất hiện trong nhiều đường chứng chỉ vì được cross-sign. Tùy tập anchors và path-building policy, Java có thể chọn đường khác với OpenSSL hoặc một trình duyệt. Khi điều tra, cần lưu subject, issuer, serial, SKI/AKI và fingerprint, thay vì dựa vào subject name đơn thuần.

## 4. Phân biệt trust validation, hostname verification và TLS negotiation

Ba nhóm kiểm tra này khác nhau:

1. **PKIX/trust validation:** Chứng chỉ có đường tin cậy tới trust anchor hợp lệ không?
2. **Hostname verification:** Chứng chỉ đó có phù hợp endpoint name mà client yêu cầu không?
3. **TLS negotiation:** Hai phía có thỏa thuận được phiên bản TLS, cipher suite, key exchange và signature scheme không?

Bên cạnh đó, HTTPS response hoặc business authorization là các lớp kiểm tra khác sau khi TLS được thiết lập.

~~~text
Java client
   |
   | DNS / TCP / Proxy / SNI
   v
TLS endpoint
   |
   | TLS handshake, certificate chain
   v
JSSE TrustManager + PKIX
   |
   | Xây path, xác minh chữ ký, constraints, policy
   v
Endpoint identity check
   |
   | So khớp DNS/IP với SAN
   v
HTTP request / response
~~~

Đây là mô hình logic, không phải thứ tự chính xác của mọi implementation trong TLS 1.2/1.3.

**Thêm root CA không chữa được hostname mismatch.** Đổi hostname cũng không làm certificate hết hạn trở nên hợp lệ. Hạ security policy không làm một private CA không được phê duyệt trở nên đáng tin. Cần chẩn đoán đúng lớp lỗi.

## 5. Java lấy truststore mặc định ở đâu?

Trong một JDK thường gặp với SunJSSE, truststore mặc định liên quan các đường dẫn:

~~~text
<JAVA_HOME>/lib/security/jssecacerts
<JAVA_HOME>/lib/security/cacerts
~~~

Thông thường `jssecacerts` có thể được ưu tiên nếu tồn tại, sau đó `cacerts`. Đây là hành vi của môi trường/provider cụ thể, không nên khái quát rằng mọi vendor và SSL provider xử lý hoàn toàn giống nhau.

Các nguồn trust material có thể khác nhau:

- Default `cacerts` được đóng gói cùng JDK image.
- `jssecacerts` được platform bổ sung.
- File chỉ định bằng `javax.net.ssl.trustStore`.
- Trust material do ứng dụng nạp programmatically vào `SSLContext`.
- Provider PKCS#11, HSM hoặc nền tảng quản lý certificate chuyên dụng.
- Trust configuration riêng của framework, HTTP client, JDBC driver hoặc application server.

JDK runtime trong container có thể dùng tập CA khác với Java trên laptop hoặc Windows/Linux host. **Kho CA của hệ điều hành không tự động đồng nghĩa với `cacerts` của mọi Java distribution.** Một số vendor/image có cơ chế đồng bộ, nhưng phải kiểm tra thực tế.

### 5.1. Kiểm tra Java executable đang chạy

~~~bash
java -version
~~~

Lệnh trên chỉ cho biết `java` trong môi trường shell đó. Nếu hệ thống chạy bằng systemd, Docker, Kubernetes hoặc Gradle Test task, hãy xác định JVM executable của process cụ thể. `JAVA_HOME` trong terminal có thể không phải runtime của service đang lỗi.

### 5.2. Xem truststore mặc định

~~~bash
keytool -list -cacerts
~~~

Với thông tin chi tiết:

~~~bash
keytool -list -v -cacerts
~~~

Nếu dùng file riêng:

~~~bash
keytool -list -v \
  -keystore /opt/app/config/client-truststore.p12 \
  -storetype PKCS12
~~~

Lệnh có thể yêu cầu password. Không ghi password vào log, repository, CI output hoặc tài liệu công khai.

### 5.3. JKS và PKCS12

Nhiều hệ thống cũ dùng `JKS`; các JDK hiện đại sử dụng `PKCS12` làm default keystore type trong nhiều ngữ cảnh. **Không được đoán loại store chỉ từ extension** hoặc assume file `cacerts` của mọi vendor luôn có một định dạng duy nhất. Xác minh file thực tế và cấu hình `-storetype` hoặc `javax.net.ssl.trustStoreType`.

## 6. Truststore riêng không tự hợp nhất với cacerts

Giả sử ứng dụng gọi:

~~~text
1. https://billing.internal.example  (private enterprise CA)
2. https://public-payments.example   (public CA)
~~~

Nếu application tạo custom SSLContext chỉ tin enterprise root, endpoint nội bộ có thể thành công nhưng public endpoint sẽ thất bại dù public CA nằm trong default JDK `cacerts`.

| Cấu hình | Có thể tin | Rủi ro |
|---|---|---|
| Default JDK cacerts | Các public roots đi kèm runtime | Thường không bao gồm private enterprise root |
| Truststore riêng chỉ chứa private root | Dịch vụ cấp bởi private CA | Mất khả năng tin public CA nếu thay thế default |
| Truststore quản lý gồm roots phù hợp | Các trust domains được phê duyệt | Cần cập nhật CA và audit rõ ràng |
| SSLContext riêng cho từng integration | Tách chính sách tin cậy theo đối tác | Cần cấu hình/kiểm thử chính xác |

**Cấu hình custom truststore thường thay thế tập trust anchors của TrustManager tương ứng; không nên mặc định nó cộng thêm vào `cacerts`.** Nếu cần cả private và public roots, hãy thiết kế tập CA được phê duyệt hoặc dùng SSL contexts riêng, có ranh giới và kiểm soát rõ ràng.

Không nên copy nguyên một `cacerts` từ JDK cũ sang image mới để giữ “mọi thứ như cũ”. Một bản JDK mới có thể đã bỏ những CA không còn an toàn hoặc cập nhật policy nhằm giảm rủi ro.

## 7. Các kiểm tra đối với chứng chỉ X.509

### 7.1. Thời hạn hiệu lực

Certificate có `Not Before` và `Not After`. Một leaf hoặc intermediate certificate chưa đến ngày hiệu lực hoặc đã hết hạn có thể bị từ chối. Đồng hồ hệ thống/VM/container sai cũng có thể gây lỗi `CertificateNotYetValidException` hoặc `CertificateExpiredException`.

### 7.2. Chữ ký và path building

Client phải xác minh chữ ký của leaf bằng public key issuer, kiểm tra intermediate tương tự cho đến trust anchor. Subject/issuer names hỗ trợ tìm ứng viên nhưng không thay thế cryptographic signature validation.

### 7.3. BasicConstraints và KeyUsage

Certificate dùng làm CA phải đáp ứng constraints cho phép ký chứng chỉ, chẳng hạn `BasicConstraints CA=true` và `keyCertSign` khi extension liên quan hiện diện/được yêu cầu. Path length constraints cũng có thể giới hạn độ sâu CA.

### 7.4. ExtendedKeyUsage

Nếu certificate khai báo Extended Key Usage, mục đích cần phù hợp: leaf của TLS server thường dùng `serverAuth`; certificate của mTLS client có thể cần `clientAuth`. Không thể tự dùng một certificate ký cho mục đích khác chỉ vì chain tới root hợp lệ.

### 7.5. Signature algorithms và key sizes

JDK có các chính sách mật mã khiến chain dùng signature/hash yếu hoặc key size không phù hợp bị từ chối. Điều kiện cụ thể phụ thuộc JDK version/vendor, provider và chính sách bảo mật, không nên quy mọi SHA-1 certificate vào cùng một tình huống.

### 7.6. Revocation

CRL và OCSP có thể được dùng để kiểm tra việc thu hồi chứng chỉ. Khả năng, mặc định và enforcement phụ thuộc JSSE/PKIX configuration. Không mặc định Java và trình duyệt dùng cùng cơ chế revocation. Cũng không tắt revocation checking để né lỗi hạ tầng mà không xem xét yêu cầu bảo mật.

## 8. Hostname verification: root đáng tin vẫn chưa đủ

Giả sử leaf certificate có Subject Alternative Name:

~~~text
DNS: billing.internal.example
~~~

Nhưng Java client gọi:

~~~text
https://inventory.internal.example
~~~

Chain có thể hoàn toàn hợp lệ và root được truststore tin cậy, nhưng hostname verification vẫn thất bại.

Các trường hợp cần xem:

- DNS hostname trong URL phải khớp SAN DNS theo quy tắc của HTTPS client.
- Nếu client kết nối bằng IP literal, cần SAN loại IP phù hợp.
- Wildcard certificate có phạm vi nhất định, không tự khớp vô hạn các cấp subdomain.
- Không nên dựa vào Common Name (CN) làm giải pháp thay thế SAN; behavior fallback khác nhau giữa thư viện/JDK.
- SNI có thể khiến reverse proxy trả certificate khác khi một IP phục vụ nhiều hostname.

Ví dụ lỗi:

~~~text
javax.net.ssl.SSLHandshakeException:
No subject alternative DNS name matching
inventory.internal.example found
~~~

Hướng sửa là cấp certificate có SAN đúng, gọi đúng hostname hoặc sửa gateway/SNI. **Không sửa bằng cách tắt HostnameVerifier**, vì như vậy kết nối không còn xác thực đúng danh tính server.

## 9. Tác động thường gặp của nâng JDK

### 9.1. Tập root CA thay đổi

Một JDK release hoặc container image mới có thể thêm, bỏ hoặc cập nhật trust anchors. Root nội bộ mà team đã import thủ công vào JDK cũ không tự xuất hiện trong image mới.

### 9.2. Chính sách thuật toán thay đổi

Trong cấu hình Java security có các properties như:

~~~text
jdk.certpath.disabledAlgorithms
jdk.tls.disabledAlgorithms
~~~

Chúng có thể ảnh hưởng việc chấp nhận chứng chỉ hoặc đàm phán TLS. Nếu có lỗi `Algorithm constraints check failed`, cần tìm certificate/key/signature vi phạm và thay cấu hình server hoặc certificate chain. **Không vô hiệu hóa toàn bộ disabled algorithms** để vượt qua lỗi.

### 9.3. TLS version và cipher policy thay đổi

Server cũ chỉ hỗ trợ protocol/cipher yếu có thể bị JDK mới từ chối dù certificate chain vẫn hợp lệ. Đây là lỗi negotiation, không nhất thiết là lỗi root CA.

### 9.4. Runtime image và security provider khác

JDK vendor, patch level, JSSE/PKCS#11 provider, FIPS policy hoặc custom runtime image có thể ảnh hưởng truststore loading và thuật toán được chấp nhận. Phải ghi nhận **Java vendor/version, security properties, provider, truststore path và file content**.

### 9.5. Framework tạo SSLContext riêng

Một HTTP client, gRPC client, JDBC driver hoặc application server có thể tự dùng trust configuration riêng thay vì default JSSE properties. Chỉ đổi `-Djavax.net.ssl.trustStore` chưa chắc tác động tới nó.

## 10. Những lỗi TLS phổ biến và cách phân biệt

| Dấu hiệu | Nguyên nhân có thể | Ưu tiên kiểm tra |
|---|---|---|
| `PKIX path building failed` / `unable to find valid certification path` | Không xây được đường tới trust anchor theo cấu hình/policy | Truststore thật, CA, intermediate chain, proxy |
| `PKIX path validation failed` | Đường được xem xét nhưng không đạt quy tắc xác thực | Validity, key usage, constraints, revocation |
| `CertificateExpiredException` | Một certificate cần thiết đã hết hạn | Leaf/intermediate dates và đồng hồ |
| `CertificateNotYetValidException` | Certificate chưa bắt đầu hiệu lực hoặc clock sai | Time sync, validity |
| `No subject alternative ... matching` | Hostname không khớp chứng chỉ | SAN, URL, DNS, SNI |
| `Algorithm constraints check failed` | Key/signature/policy không tương thích | Security properties và chain |
| `handshake_failure` / `protocol_version` | TLS version/cipher/key exchange không thỏa | Server/client TLS capabilities |
| `Received fatal alert: bad_certificate` | Peer từ chối certificate, thường cần xem mTLS | Server logs, client identity chain |
| `trustAnchors parameter must be non-empty` | Trust anchors usable rỗng trong cấu hình | Store path/type/content và custom TrustManager |
| `Keystore was tampered with, or password was incorrect` | Password/type/file không phù hợp | Store validity và secret |
| Chỉ lỗi trong container | Image, truststore mount hoặc proxy khác local | Process environment và endpoint chain |

Một lỗi `SSLHandshakeException` có thể bọc nhiều nguyên nhân khác nhau. Đọc `Caused by` và debug logs, không chỉ search một thông báo rồi áp dụng lệnh import certificate từ Internet.

## 11. Quan sát certificate chain trên server bằng OpenSSL

Trong môi trường có OpenSSL:

~~~bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -showcerts
~~~

Lưu ý:

- `-connect` chỉ định endpoint và port.
- `-servername` gửi TLS SNI; rất quan trọng khi server dùng virtual hosts.
- `-showcerts` hiển thị các certificate peer gửi trong handshake.
- Phải kiểm tra subject, issuer, SAN, dates và intermediate certificates.
- Lệnh trả certificate data không đồng nghĩa nó xác thực hostname và PKIX theo cùng chính sách của Java.
- Một môi trường dùng proxy có thể trình certificate khác với endpoint public.

Với leaf certificate đã lưu dưới dạng PEM:

~~~bash
openssl x509 -in server-leaf.pem \
  -noout -subject -issuer -dates -fingerprint -sha256
~~~

Để xem extension chi tiết:

~~~bash
openssl x509 -in server-leaf.pem -noout -text
~~~

Fingerprint SHA-256 giúp đối chiếu identity của certificate đã nhận. **Không dùng việc nhìn thấy fingerprint qua chính kết nối nghi ngờ làm bằng chứng tin cậy**; với trust anchor mới, cần đối chiếu bằng nguồn PKI đáng tin cậy và kênh độc lập.

### 11.1. Dùng keytool để nhìn endpoint

Một số bản JDK hỗ trợ:

~~~bash
keytool -printcert \
  -sslserver api.example.com:443 \
  -rfc
~~~

Lệnh này hữu ích để quan sát certificates từ endpoint bằng công cụ JDK. Tuy nhiên, không thay thế việc thử kết nối bằng ứng dụng và SSLContext thực tế.

### 11.2. Kết quả OpenSSL và Java có thể khác nhau

OpenSSL có thể dùng OS CA store, chính sách và path builder khác với Java. Ngoài ra, không phải mọi lệnh OpenSSL mặc định đều thực hiện hostname verification. Một lệnh OpenSSL thành công không đủ chứng minh Java client sẽ thành công.

## 12. Kiểm tra chính truststore mà Java sử dụng

Trong đợt migration, cần trả lời đúng các câu hỏi:

1. Process đang chạy Java executable nào?
2. Truststore file cụ thể nào được nạp?
3. File đó có tồn tại trong container/VM và process có quyền đọc không?
4. Store type là `PKCS12`, `JKS` hay provider khác?
5. Truststore có trust anchors được phê duyệt nào?
6. Fingerprints của các CA có đúng với chính sách PKI không?
7. Java app có custom `SSLContext` hoặc framework trust bundle nào không?
8. Có proxy, service mesh hoặc TLS terminator cấp lại certificate không?
9. Client đang kết nối với hostname/SNI nào?
10. Test local có chạy cùng Java image/truststore như production không?

Ví dụ kiểm tra một store có alias `company-root-ca`:

~~~bash
keytool -list -v \
  -keystore /opt/app/config/client-truststore.p12 \
  -storetype PKCS12 \
  -alias company-root-ca
~~~

Tên alias chỉ là tên quản trị, không quyết định tính hợp lệ của chữ ký. Khi kiểm tra, cần đối chiếu certificate fingerprint và mục đích CA.

Nếu property `javax.net.ssl.trustStore` trỏ tới đường dẫn không tồn tại, hành vi cụ thể có thể phụ thuộc JSSE/provider và cách khởi tạo context. Đừng mặc định nó sẽ fallback an toàn về `cacerts`. Kiểm tra log, sự tồn tại file và việc trust manager thực sự đã nạp bao nhiêu anchors.

## 13. Tạo truststore riêng để tin private CA

Nếu endpoint nội bộ dùng CA doanh nghiệp và client cần tin CA đó, hãy nhận root/intermediate trust anchor được phê duyệt từ **hệ thống PKI của tổ chức**.

Ví dụ import certificate CA vào truststore PKCS12 riêng:

~~~bash
keytool -importcert \
  -alias company-root-ca \
  -file company-root-ca.pem \
  -keystore client-truststore.p12 \
  -storetype PKCS12
~~~

Khi chạy, keytool thường yêu cầu password và/hoặc xác nhận tin certificate. Không sử dụng `-noprompt` để bỏ qua xác minh nguồn certificate nếu chưa có quy trình tự động được kiểm soát.

Đọc lại store:

~~~bash
keytool -list -v \
  -keystore client-truststore.p12 \
  -storetype PKCS12 \
  -alias company-root-ca
~~~

Những điều cần làm trước khi đưa vào production:

- Đối chiếu SHA-256 fingerprint với nguồn độc lập, đáng tin.
- Xác định CA owner và phạm vi được phép cấp certificate.
- Kiểm tra validity và các CA constraints.
- Quản lý file qua configuration management hoặc image/version được phê duyệt.
- Thiết lập quy trình rotation, rollback và audit.
- Chỉ cấp quyền đọc cần thiết cho process Java.
- Không sao chép private keys vào client truststore một cách vô cớ.

### 13.1. Nên import root hay intermediate?

Thông thường server cần gửi intermediate, còn truststore chứa trust anchor như root CA đã phê duyệt. Có thể có thiết kế tin intermediate như anchor riêng, nhưng đó là thay đổi trust boundary có chủ đích, không phải mẹo chữa mọi PKIX error.

### 13.2. Vì sao không import leaf server certificate tùy tiện?

Import leaf có thể làm một kết nối qua được nhưng gặp khó khi leaf renew hoặc rotate, có thể che cấu hình server thiếu intermediate, và có nguy cơ tin nhầm certificate lấy từ đường truyền không được xác thực. Certificate/public-key pinning chỉ phù hợp nếu dự án thiết kế và quản lý rotation rõ ràng.

### 13.3. Vì sao không sửa trực tiếp cacerts của JDK một cách thủ công?

Thao tác thêm CA trực tiếp vào JDK image có thể mất khi upgrade, ảnh hưởng nhiều ứng dụng dùng chung runtime, khó audit và không tái lập ở CI/production. Có môi trường chủ trương quản lý roots ở cấp platform image; khi ấy phải đảm bảo image được quản trị theo version và quy trình change control rõ ràng.

## 14. Dùng JVM system properties để chỉ định truststore

Trong nhiều ứng dụng dựa vào JSSE defaults, có thể cấu hình:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/opt/app/config/client-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar app.jar
~~~

Property `javax.net.ssl.trustStorePassword` tồn tại để cung cấp password cho store khi cần. Tuy nhiên, **đưa password thật lên command line có thể bị lộ qua process listing, shell history hoặc logs**. Nên chọn giải pháp secret handling của platform phù hợp, chẳng hạn cấu hình programmatic hoặc secret management và lifecycle được bảo vệ.

Ví dụ các tên property, không phải lệnh triển khai có secret thật:

~~~text
javax.net.ssl.trustStore=/opt/app/config/client-truststore.p12
javax.net.ssl.trustStoreType=PKCS12
javax.net.ssl.trustStorePassword=<supplied securely>
~~~

Không mặc định mọi HTTP library đều sử dụng các property này. Nếu ứng dụng tạo custom trust managers hoặc framework-specific SSL configuration, cần sửa đúng điểm cấu hình đó.

## 15. Ví dụ Java tạo SSLContext từ PKCS12 truststore

Đôi khi ứng dụng muốn một outbound client sử dụng trust anchors riêng, tách khỏi default JSSE context. Ví dụ:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class ClientTlsConfiguration {

    private ClientTlsConfiguration() {
    }

    public static SSLContext createContext(
            Path truststorePath, char[] password) throws Exception {

        KeyStore truststore = KeyStore.getInstance("PKCS12");

        try (InputStream input = Files.newInputStream(truststorePath)) {
            truststore.load(input, password);
        }

        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());

        factory.init(truststore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, factory.getTrustManagers(), null);

        return context;
    }
}
~~~

Các bước:

1. `KeyStore` đọc PKCS12 store.
2. `TrustManagerFactory` tạo trust managers từ anchors trong store.
3. `SSLContext` được cấu hình với các trust managers đó.
4. `null` cho tham số KeyManager nghĩa ví dụ chưa cung cấp client identity, nên chưa phải cấu hình mTLS client.
5. Context này **không tự cộng thêm default cacerts**.
6. Việc context được tạo thành công chưa chứng minh endpoint certificate và hostname sẽ hợp lệ.

Nếu password được giữ trong `char[]`, có thể xóa nội dung mảng sau khi khởi tạo khi phù hợp lifecycle, nhưng không nên khẳng định giải pháp đó bảo đảm mọi bản sao secret trong memory đều bị xóa.

### 15.1. Dùng với Java HttpClient từ Java 11

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import javax.net.ssl.SSLContext;

public final class TlsClientExample {

    public static void main(String[] args) throws Exception {
        String path = System.getenv("CLIENT_TRUSTSTORE_PATH");
        String password = System.getenv("CLIENT_TRUSTSTORE_PASSWORD");

        if (path == null || password == null) {
            throw new IllegalStateException("Missing TLS configuration");
        }

        SSLContext context = ClientTlsConfiguration.createContext(
                Path.of(path), password.toCharArray());

        HttpClient client = HttpClient.newBuilder()
                .sslContext(context)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.internal.example/health"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        System.out.println(response.statusCode());
    }
}
~~~

Đây là ví dụ để hiểu API; production cần nguồn secrets phù hợp, timeout, error handling, monitoring và các biện pháp bảo vệ endpoint theo yêu cầu thực tế. Environment variables được dùng đơn giản hóa minh họa, không phải giải pháp bảo mật tối ưu cho mọi môi trường.

**Không viết một `X509TrustManager` chấp nhận mọi chain** để làm cho ví dụ chạy được. Nếu ứng dụng đang lỗi PKIX, cần tìm nguyên nhân trust/path validation.

## 16. mTLS: truststore và keystore ở hai phía

Trong **mutual TLS (mTLS)**, server cũng yêu cầu client xuất trình chứng chỉ. Vì thế có ít nhất hai luồng xác thực:

~~~text
Java client                               TLS server
-----------                               ----------

Client truststore   -- trust server CA --> Server identity cert
                                              + private key

Client identity cert + private key         Server truststore
                    -- trust client CA -->   validates client cert
~~~

| Bên | Store | Vai trò |
|---|---|---|
| Java client | Truststore | Tin CA phát hành chứng chỉ server |
| Java client | Identity keystore | Trình client certificate và private key |
| TLS server | Identity keystore | Trình server certificate và private key |
| TLS server | Truststore | Tin CA phát hành chứng chỉ client |

Nếu server từ chối client cert với `bad_certificate`, sửa **client truststore** chưa chắc có tác dụng: client truststore dùng để xác thực server, còn server truststore mới quyết định tin client cert.

Cần xác định peer nào từ chối, certificate chain của peer đó, KeyUsage/EKU, validity và algorithm policy. Không tự giả định mọi PKIX error đều xảy ra ở bên Java client.

Private key của identity keystore phải được bảo vệ bằng quyền truy cập, secret management và quy trình rotation. Root CA certificate công khai có thể được phân phối rộng hơn nhưng việc **tin** root phải được kiểm soát.

## 17. Chỉnh server để gửi đủ intermediate certificates

Khi server chain thiếu intermediate, hướng sửa hợp lý thường nằm ở **server hoặc TLS terminator**, không phải yêu cầu mọi Java client import leaf.

Các yêu cầu cơ bản:

- Trình leaf certificate đúng với hostname được phục vụ.
- Gửi các intermediate certificates cần thiết.
- Dùng private key khớp leaf.
- Không đưa root private key vào TLS deployment.
- Bảo đảm SAN, validity, EKU và key usage đúng.
- Cấu hình TLS protocols/ciphers tương thích policy.
- Cung cấp chain nhất quán trên các node và availability zones.
- Có kế hoạch gia hạn/rotation trước khi hết hạn.

Một số server product dùng khái niệm file `fullchain.pem` chứa leaf + intermediate. Tên và định dạng cụ thể tùy server; phải đọc tài liệu triển khai và kiểm tra chain thực tế đã được gửi bằng `openssl s_client -showcerts` hoặc công cụ tương đương.

### 17.1. SNI và load balancer

Nếu nhiều virtual hosts dùng chung IP, SNI quyết định certificate được chọn. Kết nối không gửi SNI hoặc gửi tên khác có thể nhận default certificate không khớp. Khi điều tra cần dùng hostname mà Java client thật sự gọi, không chỉ kết nối IP trực tiếp.

### 17.2. Gateway và service mesh

Nếu TLS terminate ở ingress/gateway/sidecar, certificate có thể không nằm trong ứng dụng backend. Cần xác định TLS termination point, certificate rotation controller và nơi cấu hình chain thực tế.

## 18. Proxy và TLS inspection trong doanh nghiệp

Một outbound proxy có thể tái ký server certificate dưới enterprise CA trong mô hình TLS inspection:

~~~text
Java client
   |
   | TLS tới certificate do corporate proxy cấp
   v
Corporate TLS inspection proxy
   |
   | TLS riêng tới public destination
   v
Internet HTTPS endpoint
~~~

Java có thể thấy chain khác hoàn toàn với trình duyệt hoặc lệnh OpenSSL chạy trên laptop không dùng proxy.

Khi đó:

- Truststore của client cần tin enterprise CA theo chính sách tổ chức.
- Certificate do proxy trình phải có SAN đúng hostname.
- Proxy phải có quy trình riêng để xác thực server upstream.
- Trust anchor của proxy làm mở rộng phạm vi quyền cấp certificate nên cần audit.
- Debug phải được thực hiện trong đúng network path và runtime environment.

Không nên giải quyết TLS inspection bằng cách tắt hostname check hoặc trust-all. Nếu proxy được công ty quản trị, certificate và CA phải được cung cấp qua kênh quản lý tin cậy.

## 19. Chứng chỉ quay vòng: leaf, intermediate và root

Nâng cấp JDK có thể trùng với việc certificate rotation:

- Gia hạn leaf.
- Chuyển sang intermediate CA mới.
- Thay root hoặc đổi đường cross-sign.
- Root cũ bị loại khỏi truststore.
- Thuật toán chữ ký được nâng cấp.
- Internal PKI thay cấu hình SAN/EKU.
- mTLS client certificates được cấp lại.

Một quy trình rotation cần cân nhắc:

1. Lập inventory endpoint, chain hiện tại, CA chủ sở hữu và hạn dùng.
2. Chuẩn bị trust anchors mới và phân phối theo policy trước khi đổi chain nếu cần.
3. Xác minh cả JDK cũ và JDK mới trong thời gian hỗ trợ chồng lấn.
4. Triển khai server certificate/chain mới theo kế hoạch.
5. Kiểm tra từng load balancer node và hostname/SNI.
6. Theo dõi handshake errors, mTLS alerts và latency.
7. Chỉ xóa trust anchors cũ khi không còn consumer.
8. Lưu evidence và kế hoạch rollback.

Không dựa vào việc thêm từng leaf certificate vào truststore của mọi client mỗi lần renew. Cách đó làm chi phí vận hành tăng và dễ bỏ sót node.

## 20. Debug JSSE và certificate path validation

Có thể bật JSSE debug để quan sát trust manager và handshake:

~~~bash
java \
  -Djavax.net.debug=ssl,handshake,trustmanager \
  -jar app.jar
~~~

Có thể xem thêm hoạt động chứng thực đường chứng chỉ:

~~~bash
java \
  -Djava.security.debug=certpath \
  -jar app.jar
~~~

Debug output phụ thuộc JDK/provider/options. Log có thể tiết lộ tên endpoint, certificate details hoặc thông tin nhạy cảm; chỉ bật có kiểm soát, lưu trong thời gian cần thiết và giới hạn truy cập.

Quy trình đọc lỗi:

1. Ghi chính xác JDK version, vendor và JVM flags.
2. Xác định truststore mà TrustManager đã nạp.
3. Quan sát chain server trình qua đúng SNI/hostname/proxy.
4. Kiểm tra leaf issuer và intermediates.
5. Kiểm tra root CA/trust anchor trong store.
6. Đọc lỗi validity, CA constraints, algorithm policies và revocation.
7. Tách riêng hostname mismatch khỏi trust path failure.
8. Với mTLS, xác định chiều xác thực bị từ chối.
9. Chạy lại đúng client dưới runtime đích sau khi sửa.

**OpenSSL thành công không thay thế test Java.** Java có thể dùng store, provider, algorithm restrictions, SNI hoặc hostname rules khác; ngược lại OpenSSL thiếu tham số verify phù hợp có thể đưa ra kết luận không tương đương.

## 21. Các tình huống migration điển hình

### A. Public HTTPS thành công nhưng private endpoint bị PKIX lỗi

**Khả năng:** JDK mới có public roots nhưng không có enterprise root CA từng được thêm thủ công vào JDK cũ.

**Khắc phục:** xác minh certificate fingerprint của root qua PKI team, tạo/phân phối truststore phù hợp, kiểm tra đường dẫn và đọc lại truststore trong cùng image đang chạy.

### B. Có root CA nhưng vẫn không xây được chain

**Khả năng:** server không gửi intermediate, chain sai hoặc path builder không có dữ liệu cần thiết.

**Khắc phục:** kiểm tra `openssl s_client -showcerts` và sửa TLS server/gateway để gửi intermediate đúng. Không mặc định import leaf.

### C. Lỗi khi truy cập bằng IP thay vì DNS

**Khả năng:** leaf có DNS SAN nhưng không có IP SAN hoặc client gọi hostname khác với certificate.

**Khắc phục:** dùng đúng DNS endpoint hoặc cấp certificate với SAN theo nhu cầu. Không tắt hostname verification.

### D. JDK mới báo thuật toán không hợp lệ

**Khả năng:** key size/signature algorithm hoặc policy path validation khác baseline.

**Khắc phục:** thay certificate/chain/cipher phù hợp chính sách. Không làm yếu toàn bộ JVM security settings.

### E. App chỉ tin private CA và mất khả năng gọi public gateway

**Khả năng:** custom TrustManager sử dụng store chỉ chứa private root, thay hoàn toàn default roots.

**Khắc phục:** phân tách SSLContexts theo integration hoặc xây tập anchors phù hợp và đã được phê duyệt.

### F. mTLS gặp `bad_certificate` khi server xác thực client

**Khả năng:** server-side truststore không tin client CA, client gửi chain thiếu, cert sai EKU hoặc hết hạn.

**Khắc phục:** điều tra server logs và cả client identity keystore/server truststore. Không chỉ thêm CA vào client truststore.

### G. Chỉ lỗi ở production container

**Khả năng:** image/truststore mount, proxy, SNI, runtime JDK hoặc outbound routing khác local/CI.

**Khắc phục:** so sánh file hashes, CA aliases, process JVM flags và certificate chain quan sát từ chính production network path.

## 22. Quy trình thực hiện migration có kiểm soát

### Bước 1: Kiểm kê kết nối TLS

Liệt kê outbound HTTPS, gRPC, JDBC over TLS, Kafka, AMQP, LDAP/LDAPS, service mesh, proxy và mTLS. Xác định client library nào sử dụng default JSSE, library nào có truststore riêng.

### Bước 2: Chụp baseline

Lưu JDK distribution/version, truststore path/type/fingerprints, certificate chain endpoints, SAN/validity, proxy settings và test results. Không lưu private keys hay passwords trong báo cáo.

### Bước 3: So sánh chính sách trước/sau nâng JDK

Xác định khác biệt của CA roots, `java.security` policies, enabled TLS protocols/ciphers, security providers và JDK image. Tránh thay nhiều biến cùng lúc nếu có thể.

### Bước 4: Chẩn đoán đúng vị trí

| Lỗi gốc | Nơi sửa ưu tiên |
|---|---|
| Thiếu intermediate | TLS server, gateway hoặc load balancer |
| Thiếu private trust anchor được phê duyệt | Java client truststore / platform CA distribution |
| Hostname/SAN mismatch | Certificate issuance hoặc URL/SNI |
| Certificate hết hạn | PKI certificate renewal |
| Algorithm yếu | CA/server TLS configuration |
| Truststore file/type sai | Application/container deployment config |
| mTLS client identity sai | Client keystore và server-side trust |
| Corporate proxy CA chưa tin | Enterprise PKI policy và client trust config |

### Bước 5: Kiểm thử dưới đúng runtime

Chạy Java client trong image/container/VM mục tiêu và qua đúng DNS/proxy/load balancer. Test endpoint thành công lẫn trường hợp sai SAN, chain thiếu và certificate rotation trong môi trường kiểm thử phù hợp.

### Bước 6: Triển khai và quan sát

Theo dõi `SSLHandshakeException`, TLS alerts, HTTP errors, connection retries, latency và ảnh hưởng nghiệp vụ. Đảm bảo rollback trong thời gian có cả chains/trust anchors cần thiết.

### Bước 7: Dọn workaround, ghi nhận ownership

Loại bỏ temporary trust entries, flags và cấu hình không còn dùng. Giao rõ CA owner, lịch rotation, nơi lưu truststore, quy trình deploy và contact khi certificate gần hết hạn.

## 23. Những anti-pattern cần tránh

### 23.1. Trust-all TrustManager

Một TrustManager bỏ trống `checkServerTrusted` hoặc chấp nhận mọi chain làm mất kiểm tra danh tính certificate. Nó có thể khiến request “chạy” nhưng làm tăng rủi ro man-in-the-middle và hoàn toàn không chứng minh TLS được cấu hình đúng.

### 23.2. HostnameVerifier luôn trả true

Vô hiệu hóa kiểm tra hostname làm client có thể chấp nhận certificate của endpoint khác. Đây không phải cách khắc phục `No subject alternative DNS name matching ...` an toàn.

### 23.3. Import certificate từ endpoint mà không xác minh nguồn

Nếu kết nối đã bị can thiệp, việc sao chép certificate do endpoint đó trình rồi tin trực tiếp có thể đưa certificate giả vào truststore. CA phải được xác minh qua kênh PKI độc lập.

### 23.4. Copy toàn bộ cacerts cũ sang JDK mới

Điều này có thể giữ root đã bị thu hồi tin cậy hoặc không tuân chính sách mới. Hãy quản lý CA chính xác thay vì vô hiệu hóa những cải tiến bảo mật đi kèm JDK.

### 23.5. Bỏ hết disabledAlgorithms

Không nên làm yếu thuật toán cho toàn JVM chỉ để kết nối với một server lỗi thời. Sửa certificate/key/TLS configuration theo policy.

### 23.6. Hard-code password hoặc private keys

Không lưu secrets trong Java source, Git, command logs hoặc ảnh chụp màn hình. Truststore public certificates và identity keystore private keys có mức nhạy cảm khác nhau, nhưng cả hai cần chính sách quản lý file phù hợp.

### 23.7. Kiểm thử bằng trình duyệt rồi kết luận Java ổn

Trình duyệt có thể dùng OS trust roots hoặc cache intermediate khác; Java có cacerts và provider riêng. Cần test bằng đúng Java client/runtime dự kiến.

## 24. Ma trận kiểm thử gợi ý

| Kịch bản | Kết quả mong đợi |
|---|---|
| HTTPS public endpoint có chain hợp lệ | Java client tin theo public roots được phê duyệt |
| Endpoint enterprise PKI | Java client tin CA nội bộ được phê duyệt |
| Server thiếu intermediate | Phát hiện lỗi và sửa chain tại server |
| Certificate SAN sai | Client từ chối đúng |
| Leaf hết hạn | Client từ chối đúng |
| Key/signature yếu | Bị từ chối theo security policy |
| Kết nối qua corporate proxy | Trust policy doanh nghiệp và SAN được kiểm tra |
| mTLS với client certificate hợp lệ | Hai chiều xác thực thành công |
| mTLS với client certificate không hợp lệ | Server từ chối |
| Server certificate rotation | Client tiếp tục hoạt động theo kế hoạch trust overlap |
| Load balancer failover | Các backend cung cấp chain đúng |
| Container thiếu truststore mount | Cấu hình lỗi được phát hiện, không trust-all hoặc fallback thiếu kiểm soát |

Bảng kết quả nên lưu PASS, FAIL, BLOCKED hoặc NOT RUN, kèm thời gian test, JDK image, endpoint, fingerprint và log liên quan. Không điền PASS chỉ vì ứng dụng start thành công mà chưa thực hiện TLS request.

## 25. Những nguyên tắc cần nhớ

- **Truststore là tập trust anchors mà client sử dụng**, không phải toàn bộ certificate chain của server.
- **Root CA và intermediate CA có vai trò khác nhau.** Root thường ở client truststore; server nên gửi leaf và intermediates cần thiết.
- **Server gửi root không làm root đáng tin.** Trust phải đến từ client policy.
- **PKIX path validation, hostname verification và TLS negotiation độc lập về ý nghĩa.** Cần đọc lỗi đúng giai đoạn.
- **JDK upgrade có thể làm thay tập root, algorithm policy, provider và runtime image.** Không kết luận từ build xanh.
- **Custom truststore có thể thay thế default cacerts.** Phải cân nhắc public/private trust domains.
- **mTLS có cả client identity keystore và truststore phía server.** Phân biệt chiều xác thực.
- **Thiếu intermediate thường nên sửa ở server/gateway**, không dùng import leaf cho tất cả clients như workaround.
- **Không trust-all hoặc tắt hostname verification.** Đó là bỏ hàng rào an toàn, không phải sửa lỗi TLS.
- **Xác minh CA fingerprint qua nguồn đáng tin cậy** trước khi thêm trust anchor.
- **Debug phải chạy trong đúng network/runtime context**, kể cả proxy, SNI và container.
- **Certificate lifecycle cần owner, rotation và rollback.** Tin cậy không phải cấu hình làm một lần rồi quên.

Trong Java Advance Compatibility Migration, khả năng kết nối TLS không thể được đánh giá chỉ bằng việc ứng dụng biên dịch được với JDK mới. Cần kiểm chứng chuỗi chứng chỉ máy chủ, trust anchors của Java, hostname, cryptographic policy và đường kết nối thực tế. Một quá trình migration bền vững phải **giữ cơ chế kiểm tra TLS chặt chẽ**, sửa lỗi đúng phía server/client và cung cấp trust material qua quy trình quản trị đáng tin cậy, thay vì đổi lấy tính tương thích bằng cách tắt xác thực bảo mật.
