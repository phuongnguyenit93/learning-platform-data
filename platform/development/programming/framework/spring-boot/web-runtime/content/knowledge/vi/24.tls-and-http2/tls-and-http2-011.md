# Kiểm tra handshake, hostname, truststore và lỗi chuỗi chứng thư

## 1. Một kết nối HTTPS thành công phải vượt qua những kiểm tra nào?

Trong **Spring Boot - web-runtime**, HTTPS dựa vào TLS để mã hóa kết nối, xác thực đầu bên kia và bảo đảm tính toàn vẹn của dữ liệu truyền. Khi một ứng dụng Java gọi API HTTPS hoặc khi trình duyệt kết nối tới server Spring Boot, **TCP kết nối được không có nghĩa TLS đã hợp lệ**; TLS hợp lệ cũng chưa có nghĩa API trả HTTP 200.

Các câu hỏi cần phân biệt:

1. **DNS/TCP:** Host được giải quyết về địa chỉ nào? Cổng 443/8443 có nhận kết nối không? Có proxy, gateway hoặc TLS termination nào ở giữa?
2. **TLS negotiation/handshake:** Hai phía có thống nhất phiên bản TLS, cipher suite, các tham số mật mã và (nếu có) ALPN không? Server có chứng minh sở hữu khóa riêng của chứng thư đã gửi không?
3. **Trust/PKIX:** Client có thể xây dựng và xác minh đường chứng thư từ **leaf → intermediate CA → trusted root/trust anchor** theo chính sách của nó không?
4. **Hostname verification:** Chứng thư thực sự có hợp lệ **cho hostname hoặc IP mà client đang yêu cầu** không, đặc biệt trong Subject Alternative Name (SAN)?
5. **HTTP:** Sau khi TLS được chấp nhận, request HTTP/1.1 hoặc HTTP/2 có được xử lý thành công không? Mã 401/403/404/500 thuộc tầng HTTP, không tự chứng minh TLS handshake sai.

Ví dụ:

~~~text
Client Java/Browser                         Server / TLS termination
     |                                            |
     | DNS -> TCP connect                         |
     |------------------------------------------->|
     | ClientHello (+ SNI, ALPN)                   |
     |------------------------------------------->|
     | ServerHello, TLS parameters                 |
     |<-------------------------------------------|
     | Certificate: leaf + intermediates          |
     |<-------------------------------------------|
     | Verify chain, validity, hostname, key usage|
     | ... TLS key confirmation / Finished ...     |
     |<------------------------------------------>|
     | HTTP request (bên trong TLS)                |
     |------------------------------------------->|
     | HTTP response (200, 401, 500, ...)         |
     |<-------------------------------------------|
~~~

Sơ đồ chỉ minh họa luồng ý nghĩa. **TLS 1.3 và TLS 1.2 có cấu trúc handshake khác nhau**; trong TLS 1.3, nhiều handshake message sau ServerHello đã được mã hóa. Không diễn giải sơ đồ là thứ tự byte áp dụng cho mọi phiên bản.

**Kết luận nền tảng:** lỗi PKIX không phải lỗi DNS, lỗi hostname không phải cứ thêm CA vào truststore là sửa được, và HTTP/2 không có một “bộ chứng thư riêng” tách khỏi TLS.

## 2. Bốn khái niệm thường bị gọi chung là “chứng chỉ SSL”

| Khái niệm | Chức năng | Ai sở hữu/kiểm tra? |
| --- | --- | --- |
| **Leaf/server certificate** | Khẳng định khóa công khai gắn với danh tính dịch vụ; SAN ghi tên/IP hợp lệ | Server trình bày; client kiểm tra |
| **Intermediate CA certificate** | Nối chữ ký từ leaf lên CA cấp trên | Server thường gửi intermediate; client dùng để dựng chain |
| **Root CA / trust anchor** | Điểm kết thúc được client **chủ động tin cậy** | Truststore của client; root thường không cần được server gửi |
| **Private key của server** | Chứng minh sở hữu khóa tương ứng leaf; dùng trong quá trình xác thực TLS | Chỉ server/TLS terminator giữ, không được để trong truststore client |

Ví dụ một chain hợp lệ:

~~~text
api.example.test  (leaf; SAN DNS:api.example.test)
       |
       | signed by
       v
Example Intermediate CA  (CA=true)
       |
       | signed by
       v
Example Root CA  (đã được client tin trong truststore)
~~~

Chuỗi chữ ký hợp lệ chưa đủ. Client còn phải xem **thời hạn hiệu lực**, **hostname**, key usage / extended key usage (thường cần **serverAuth**), giới hạn CA, thuật toán được phép và chính sách thu hồi chứng thư theo cấu hình.

**Keystore khác truststore:**
- **Server keystore:** thường chứa **private key + server certificate chain** để server xuất trình với client.
- **Client truststore:** chứa **các chứng thư/CA được tin cậy** để xác minh chứng thư server; thường **không chứa private key**.
- Trong **mutual TLS (mTLS)**, client cũng có keystore chứa private key + client cert, còn server có truststore để xác minh client cert. Hai chiều vẫn có trách nhiệm riêng.

Có thể dùng định dạng **PKCS12 (.p12/.pfx)** hoặc **JKS**, nhưng định dạng file không tự quyết định nó là keystore hay truststore. Nội dung và cách ứng dụng sử dụng mới là điều quan trọng.

## 3. TLS handshake và vị trí của xác thực chứng thư

Một client TLS thường gửi **ClientHello** gồm các phiên bản/cipher suite có thể hỗ trợ, phần mở rộng **SNI** cho hostname và có thể có **ALPN** để thương lượng HTTP/2 (h2) hay HTTP/1.1. Server chọn cấu hình chung, gửi chứng thư thích hợp; client xác minh trước khi tin cậy kết nối.

Các pha cần nhận diện:

1. **Kết nối mạng:** resolve hostname, kết nối TCP tới đích; thất bại ở đây thường là UnknownHostException, ConnectException, timeout, refused.
2. **Thương lượng TLS:** ClientHello/ServerHello; lỗi không có phiên bản/cipher chung, policy mật mã, hoặc SNI routing có thể tạo handshake_failure, protocol_version hoặc lỗi khác.
3. **Xác minh danh tính server:** kiểm tra chữ ký/chain/trust anchor, hạn chứng thư, SAN và các ràng buộc cần thiết. Sai ở đây có thể tạo **SSLHandshakeException**; thông điệp gốc xác định lỗi cụ thể.
4. **Hoàn tất handshake:** trao đổi thông điệp xác nhận khóa, chuyển sang kênh mã hóa ứng dụng. Chỉ sau đó client bình thường mới gửi HTTP request.
5. **HTTP và ALPN:** nếu cả hai hỗ trợ và cấu hình HTTP/2, ALPN có thể chọn **h2**; nếu không có thể dùng HTTP/1.1. Lỗi HTTP như 404 hoặc 502 phải phân tích ở tầng API/proxy, không sửa bằng truststore.

**SNI (Server Name Indication)** rất quan trọng khi nhiều hostname dùng chung một IP: server hoặc load balancer có thể chọn chứng thư theo SNI. Truy cập bằng IP hoặc dùng lệnh OpenSSL không đặt SNI có thể khiến bạn thấy **default certificate khác** với website cần kiểm tra.

**ALPN không thay cho certificate verification.** Server trả ALPN h2 không chứng minh leaf có SAN đúng hoặc root được trust. Ngược lại, handshake TLS đã thành công nhưng ALPN chỉ chọn http/1.1 chưa phải sự cố chứng thư; hãy kiểm tra cấu hình HTTP/2 riêng.

## 4. Hostname verification: SAN phải khớp đúng nơi client gọi

### 4.1. Hostname lấy từ đâu?

Khi Java gọi **https://api.example.test/orders**, hostname cần kiểm tra là **api.example.test**. Khi client gọi **https://10.20.0.15/orders**, đó là **IP address** cần đối chiếu với chứng thư; không được coi tên DNS trong certificate là đủ chỉ vì DNS đó có thể trỏ đến cùng IP.

Trong chứng thư hiện đại, danh tính server được liệt kê tại **Subject Alternative Name**:
- **DNS:api.example.test** → đúng cho tên DNS đó.
- **DNS:*.example.test** → chỉ khớp theo quy tắc wildcard giới hạn; không phải mọi subdomain nhiều cấp.
- **IP Address:10.20.0.15** → danh tính cho IP đó; một DNS SAN có chuỗi số IP không thay thế IP SAN đúng kiểu.

**Common Name (CN)** trong Subject không nên là cơ sở duy nhất. Với nhiều TLS client hiện đại, **SAN** là nguồn xác định hostname; certificate có CN đúng nhưng SAN thiếu/sai vẫn có thể bị từ chối.

Ví dụ minh họa:

| URL client gọi | SAN của leaf | Kết quả danh tính |
| --- | --- | --- |
| https://api.example.test | DNS:api.example.test | Khớp |
| https://api.example.test | DNS:shop.example.test | Không khớp |
| https://a.example.test | DNS:*.example.test | Có thể khớp theo wildcard hợp lệ |
| https://a.b.example.test | DNS:*.example.test | Wildcard một nhãn không bao phủ hai cấp |
| https://10.20.0.15 | DNS:api.example.test | Không khớp IP |
| https://10.20.0.15 | IP Address:10.20.0.15 | Khớp IP |

Từ **“có thể”** trong bảng có nghĩa vẫn phải vượt qua chain, thời hạn, thuật toán và các kiểm tra khác. Hostname khớp chưa đảm bảo TLS thành công.

### 4.2. Triệu chứng Java thường gặp

Trong Java 17, lỗi hostname có thể được bọc trong:

~~~text
javax.net.ssl.SSLHandshakeException:
  No subject alternative DNS name matching api.example.test found
~~~

hoặc một biến thể liên quan **No subject alternative names matching IP address ... found**, tùy kết nối và JDK. Đây là **mẫu lỗi minh họa**, không cố định từng ký tự cho mọi runtime.

Nếu chain đã trust nhưng hostname vẫn sai, **thêm certificate vào truststore không sửa lỗi SAN**. Sửa hostname gọi trong URL hoặc cấp lại chứng thư với SAN đúng. Không tắt hostname verification trên production.

### 4.3. Kiểm tra IP backend nhưng vẫn giữ hostname thật

Nếu muốn kết nối tới một IP cụ thể mà vẫn kiểm tra server theo tên **api.example.test**, dùng **curl --resolve** để giữ hostname trong URL:

~~~bash
curl -v --resolve api.example.test:443:10.20.0.15 \
  https://api.example.test/health
~~~

Lệnh trên là **mẫu**: thay hostname/IP/endpoint bằng hệ thống của bạn. Curl kết nối IP đã định nhưng vẫn dùng hostname URL để tạo SNI và xác minh certificate. Nếu truy cập **https://10.20.0.15/** trực tiếp, client thường dùng IP làm danh tính cần xác minh, có thể báo mismatch dù cùng một backend.

Nếu môi trường dùng HTTP proxy, DNS routing và TLS termination có thể chịu ảnh hưởng proxy; xác nhận đường đi thực tế trước khi kết luận backend cung cấp sai certificate.

## 5. Truststore và PKIX: chứng thư được tin như thế nào?

Java thường dùng **JSSE (Java Secure Socket Extension)** cùng **TrustManager** để xác minh đường chứng thư. TrustManager cần tìm một **đường hợp lệ tới trust anchor** mà JVM/client đang tin.

Các tình huống khác nhau:

**A. CA root chưa được trust:** server gửi leaf + intermediate hợp lệ nhưng Java client không có root tương ứng trong truststore đang dùng. Kết quả có thể là:

~~~text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed:
  sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
~~~

**B. Server thiếu intermediate:** root có thể đã có trong truststore, nhưng server chỉ gửi leaf; client thiếu intermediate để nối chain. Một số browser có thể có intermediate trong cache hoặc cơ chế tìm bổ sung, còn Java client có thể thất bại. **Không kết luận chỉ vì browser mở được thì server đã gửi chain đầy đủ**.

**C. CA được trust nhưng certificate hết hạn, chưa đến ngày hiệu lực hoặc bị giới hạn thuật toán:** vẫn không hợp lệ. Lỗi có thể nhắc **validity check failed**, **NotAfter**, **NotBefore**, **Algorithm constraints check failed**, v.v. Hãy kiểm tra đồng hồ hệ thống/NTP, chain và chính sách JDK.

**D. Chain hợp lệ nhưng hostname sai:** lỗi SAN/hostname, không nên khắc phục bằng cách import root mới.

**E. Client đang dùng một truststore khác mong đợi:** ứng dụng có cấu hình **javax.net.ssl.trustStore**, SSLContext custom, SSL bundle, truststore của container image hoặc HTTP client library riêng. Import CA vào JDK của máy build có thể không tác động JVM đang chạy trong container production.

### 5.1. Điểm cần nhớ về root và intermediate

Server thường gửi **leaf trước rồi các intermediate** cần thiết, **không bắt buộc gửi root**. Client phải có trust anchor phù hợp. Việc gửi root từ server không biến root thành đáng tin: **niềm tin nằm ở truststore phía client**.

Khi thiếu intermediate, cách sửa ưu tiên là **cấu hình server/TLS terminator phát đúng full chain**, không bắt mọi client “tin leaf” để lách lỗi. Nếu private CA nội bộ không được trust, quản trị viên có thể phân phối **CA certificate đã xác thực** qua truststore thích hợp của client.

### 5.2. Đừng sửa nhầm truststore

Trên nhiều JDK, truststore mặc định nằm gần **$JAVA_HOME/lib/security/cacerts**. Nhưng JVM/runtime thực tế có thể khác đường dẫn từ shell, khác vendor hoặc có property override. Dùng:

~~~bash
java -version
keytool -list -cacerts
~~~

để xác định phiên bản Java và xem truststore của **keytool được gọi**; lệnh keytool có thể yêu cầu password. Với app chạy trong container, các lệnh cần thực thi trong **đúng image/JDK/container** hoặc kiểm tra cấu hình JVM thực, không chỉ trên laptop.

Dấu hiệu cần đọc từ cấu hình JVM:

~~~text
-Djavax.net.ssl.trustStore=/path/to/client-truststore.p12
-Djavax.net.ssl.trustStorePassword=...
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Đây là **mẫu tên system properties**, dấu ba chấm không phải giá trị cấu hình dùng để chạy. Không đưa password vào log. **Đặt trustStore custom có thể thay thế tập CA tin cậy mặc định** cho SSLContext dùng JSSE mặc định, khiến endpoint public trước đó hợp lệ lại báo PKIX. Nếu chỉ một HTTP client cần CA riêng, ưu tiên cấu hình trust theo client/SSL bundle thay vì sửa global cacerts.

## 6. Công cụ kiểm tra theo thứ tự từ ngoài vào trong

Khi gặp lỗi HTTPS, bắt đầu bằng **đúng URL/host/port, từ đúng máy và mạng mà ứng dụng gặp sự cố**, rồi kiểm tra từng lớp. Không thay truststore ngay khi nhìn thấy chữ SSLHandshakeException.

### 6.1. curl: kiểm tra đường đi và trạng thái HTTP

~~~bash
curl -v --connect-timeout 5 --max-time 15 \
  https://api.example.test/health
~~~

Đây là lệnh **mẫu**; thay endpoint theo hệ thống bạn kiểm soát. Dòng quan sát có thể cho biết:
- DNS đã chọn địa chỉ nào, có đi qua proxy không.
- TLS phiên bản nào được dùng, server certificate có hợp lệ không.
- SNI/ALPN và HTTP version mà curl hỗ trợ/đã thương lượng.
- Sau TLS có HTTP status nào.

Nếu curl báo **SSL certificate problem**, cần kiểm tra chain/trust/hostname. Nếu curl trả **HTTP 401**, handshake có thể đã thành công rồi; vấn đề tiếp theo là xác thực API chứ không phải thêm root CA.

**Curl sử dụng trust source và TLS backend tùy bản build/hệ điều hành**, không nhất thiết trùng với Java truststore. Curl thành công và Java thất bại **không đủ để kết luận Java có lỗi**; phải so sánh trust roots, proxy và hostname thực.

### 6.2. OpenSSL s_client: xem certificate server đang gửi

~~~bash
openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -showcerts \
  -verify_hostname api.example.test \
  -verify_return_error < /dev/null
~~~

Trên Linux/macOS, **/dev/null** giúp đóng stdin sau khi handshake để lệnh không chờ tương tác; trên Windows PowerShell, bỏ redirection kiểu POSIX và kết thúc chương trình theo tương tác của phiên bản OpenSSL được cài.

Ý nghĩa:
- **-connect**: IP/host và port muốn mở TCP.
- **-servername**: đặt SNI; tránh kiểm tra nhầm default certificate của virtual host.
- **-showcerts**: in danh sách certificate mà peer **đã gửi**, không tự chứng minh chain đáng tin.
- **-verify_hostname**: yêu cầu kiểm tra DNS hostname; với kết nối IP, sử dụng cơ chế kiểm tra IP phù hợp như **-verify_ip**.
- **-verify_return_error**: kết thúc với lỗi xác minh thay vì cứ tiếp tục diagnostic session sau một số verification errors.

Trong các bản OpenSSL hỗ trợ, **Verify return code: 0 (ok)** khi dùng các tùy chọn xác minh và trust store phù hợp cho biết verification đạt theo **OpenSSL đang chạy**, không bảo đảm Java cũng dùng cùng CA/policy. Đừng chỉ nhìn dòng “CONNECTED” hoặc “Certificate chain” rồi tuyên bố thành công.

Khi dùng private CA đã kiểm tra, thêm **-CAfile /path/to/ca.pem** để OpenSSL dùng bộ trust anchors phù hợp. Đường dẫn là ví dụ; không tự lấy certificate bất kỳ từ server rồi coi nó là CA tin cậy.

### 6.3. OpenSSL x509: đọc leaf và SAN

Khi bạn đã có một file leaf certificate đáng tin về nguồn gốc, ví dụ **leaf.pem**, dùng:

~~~bash
openssl x509 -in leaf.pem -noout -subject -issuer -dates -ext subjectAltName
openssl x509 -in leaf.pem -noout -text
openssl x509 -in leaf.pem -noout -fingerprint -sha256
~~~

Tập trung vào:
- **Subject Alternative Name:** DNS/IP phải khớp hostname client đang dùng.
- **Not Before/Not After:** thời gian hiệu lực so với đồng hồ hệ thống.
- **Issuer:** ai ký leaf; cần intermediate nào.
- **Basic Constraints, Key Usage, Extended Key Usage:** đúng vai trò leaf/server.
- **SHA-256 fingerprint:** dùng để so sánh chứng thư với nguồn đáng tin khác; fingerprint không thay kiểm tra chain.

**Không** dùng một Subject CN trông đúng để bỏ qua SAN.

### 6.4. OpenSSL verify: kiểm tra chain từ file

Giả sử có ba file **leaf.pem**, **intermediates.pem** và **root-ca.pem**, với root đã xác minh từ kênh tin cậy:

~~~bash
openssl verify \
  -CAfile root-ca.pem \
  -untrusted intermediates.pem \
  -verify_hostname api.example.test \
  leaf.pem
~~~

Đây là **mẫu trên các file đã có**, không phải lệnh tự tạo file. **-untrusted** cung cấp chứng thư trung gian để dựng chain, **không biến chúng thành trust anchors**. **-CAfile** chỉ rõ root/CA được tin trong phép thử. Nếu thành công, OpenSSL có thể in **leaf.pem: OK**, nhưng kết quả còn phụ thuộc chính sách và phiên bản OpenSSL.

Nếu verify báo **unable to get local issuer certificate**, xem server có thiếu intermediate, root có đúng không, và liệu file -untrusted đã chứa phần cần thiết chưa. Không tự import leaf thành trusted root để khiến lệnh xanh.

### 6.5. keytool: nhìn certificate và truststore theo góc Java

Để xem certificate tại một server:

~~~bash
keytool -printcert -sslserver api.example.test:443 -v
~~~

Lệnh này chủ yếu để **in thông tin chứng thư**, không đồng nghĩa đã xác nhận đường tin cậy/hostname như một HTTP client thực. Muốn xem file:

~~~bash
keytool -printcert -file leaf.pem -v
~~~

Muốn xem nội dung truststore bạn chỉ định:

~~~bash
keytool -list -v -keystore client-truststore.p12 -storetype PKCS12
~~~

Lệnh cuối sẽ yêu cầu password; đường dẫn là ví dụ. Hãy so sánh **CA/fingerprint được tin** với server chain thực, không nhập nhầm private key.

## 7. Lab Spring Boot HTTPS tự tạo: kiểm chứng được cả trust và hostname

Lab này chạy local, **không cần domain hoặc chứng thư công khai**, dùng JDK 17, Maven và OpenSSL/curl để quan sát TLS trên **https://localhost:8443/ping**. Nó cố ý tạo một **self-signed certificate chỉ có DNS SAN:localhost**, không có IP SAN, để mô phỏng được hai lỗi độc lập:
- **Không trust CA/certificate:** Java/curl mặc định có thể từ chối self-signed certificate.
- **Trust đã cấu hình nhưng hostname sai:** truy cập bằng **https://127.0.0.1:8443/ping** sẽ không khớp DNS SAN:localhost.

Đây là lab giáo dục. **Không đưa self-signed certificate, password mẫu hoặc truststore demo này vào production.**

### 7.1. Cây dự án

~~~text
tls-handshake-lab/
├── pom.xml
├── certs/
│   ├── dev-server.p12
│   ├── dev-server.pem
│   └── lab-truststore.p12
├── TlsProbe.java
└── src/main/
    ├── java/com/example/tls/
    │   └── TlsLabApplication.java
    └── resources/application.yml
~~~

Ba file trong certs/** được tạo bằng các lệnh bên dưới, **không có sẵn trong source**. Không commit file private key hoặc password của môi trường thật. **TlsProbe.java** là client Java 17 nằm ở thư mục gốc để có thể chạy bằng javac/java độc lập.

### 7.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>tls-handshake-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. Tạo self-signed certificate có SAN localhost

Mở terminal ở thư mục **tls-handshake-lab/**. Tạo thư mục:

~~~bash
mkdir -p certs
~~~

Trên PowerShell có thể dùng **New-Item -ItemType Directory -Force certs**. Sau đó dùng **keytool của JDK 17+**:

~~~bash
keytool -genkeypair \
  -alias lab-server \
  -keyalg RSA -keysize 2048 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore certs/dev-server.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=localhost, OU=Lab, O=Demo, C=VN" \
  -ext "SAN=dns:localhost"
~~~

Các dấu **\** cuối dòng là cách nối dòng trong shell Linux/macOS; trên Windows PowerShell hãy đặt lệnh trên **một dòng** hoặc dùng cú pháp continuation của PowerShell. Password **changeit** chỉ là giá trị demo, **không dùng production**.

Lệnh tạo **private key + chứng thư self-signed** bên trong PKCS12. Kiểm tra SAN:

~~~bash
keytool -list -v \
  -keystore certs/dev-server.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -alias lab-server
~~~

Cần thấy **SubjectAlternativeName** với **DNSName: localhost**. Vì lệnh chỉ khai báo DNS SAN, **không có IP SAN:127.0.0.1**.

Xuất **public certificate** (không chứa private key) để curl/OpenSSL tin trong lab:

~~~bash
keytool -exportcert -rfc \
  -alias lab-server \
  -keystore certs/dev-server.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -file certs/dev-server.pem
~~~

**dev-server.p12 chứa private key**, còn **dev-server.pem** ở bước export này chỉ có chứng thư công khai. Không nhầm với fullchain.pem của CA công khai.

### 7.4. Cấu hình HTTPS server trong Spring Boot

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:./certs/dev-server.p12
    key-store-type: PKCS12
    key-store-password: changeit
    key-alias: lab-server
  http2:
    enabled: true
~~~

Tài liệu này dùng **server.ssl.key-store** kiểu **file:** để Spring Boot đọc file ngoài JAR. Vị trí **./certs** là relative path theo working directory của tiến trình. Chạy **java -jar** từ thư mục dự án hoặc override đường dẫn khi deploy, nếu không server có thể không tìm thấy keystore.

**server.http2.enabled: true** để trình diễn khả năng đàm phán HTTP/2. TLS/ALPN và HTTP/2 chỉ hoạt động theo năng lực của embedded server, JDK và client; **không cố định HTTP/2 là protocol luôn được chọn**.

Trong production, không lưu password dưới dạng literal trong YAML đóng gói. Dùng secret store/environment với quyền hạn phù hợp và cân nhắc SSL bundles của Spring Boot.

### 7.5. Java server Spring Boot

**src/main/java/com/example/tls/TlsLabApplication.java**:

~~~java
package com.example.tls;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TlsLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TlsLabApplication.class, args);
    }
}

@RestController
class PingController {

    @GetMapping(path = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    String ping() {
        return "TLS OK\n";
    }
}
~~~

Đây là file Java đầy đủ. Nếu cấu hình keystore sai path/password hoặc key alias không có, **server có thể thất bại ở startup**, trước khi có request HTTPS. Đó là lỗi **server key material**, không phải lỗi truststore của client.

### 7.6. Build và chạy Spring Boot server

~~~bash
mvn package
java -jar target/tls-handshake-lab-1.0.0.jar
~~~

Chạy trong terminal thứ nhất, đứng ở root dự án. Khi server bắt đầu lắng nghe **8443**, dùng terminal khác thử:

~~~bash
curl -v https://localhost:8443/ping
~~~

**Kết quả dự kiến:** curl thường từ chối chứng thư self-signed **chưa được trust**. Thông điệp lỗi cụ thể khác nhau theo OS/curl/TLS backend; không ép chính xác stdout.

Thêm CA file tin riêng cho phép thử bằng public certificate vừa xuất:

~~~bash
curl -v --cacert certs/dev-server.pem \
  https://localhost:8443/ping
~~~

Khi hệ thống lab hoạt động đúng và curl dùng đúng PEM, **body** kỳ vọng:

~~~text
TLS OK
~~~

Lệnh này **không tắt certificate verification**: curl xác minh dựa trên file certificate mà ta đã **chủ động trust cho mục đích lab** và vẫn kiểm tra hostname **localhost**.

### 7.7. Tạo lỗi hostname mismatch mà không phá trust

Sau khi đã dùng cùng **--cacert**, cố tình gọi địa chỉ IP:

~~~bash
curl -v --cacert certs/dev-server.pem \
  https://127.0.0.1:8443/ping
~~~

**Kết quả dự kiến:** TLS client từ chối vì chứng thư **chỉ có DNS SAN:localhost, không có IP SAN:127.0.0.1**. Root/leaf đã được tin ở lab, nhưng **điều kiện hostname/IP thất bại**. Bạn không thể “sửa bằng cách import lại certificate”; cần dùng URL **localhost** hoặc cấp chứng thư mới có **IP SAN** phù hợp khi thật sự yêu cầu truy cập theo IP.

Có thể kiểm tra qua OpenSSL với ý nghĩa tương đương:

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername localhost \
  -CAfile certs/dev-server.pem \
  -verify_ip 127.0.0.1 \
  -verify_return_error < /dev/null
~~~

**-verify_ip** yêu cầu kiểm tra IP, không được lẫn với **-verify_hostname** dành cho tên DNS. **-servername localhost** cố định SNI lab; trong production hãy phân biệt SNI, địa chỉ TCP và hostname thực của URL.

### 7.8. Xác minh đúng local lab bằng s_client, kể cả ALPN

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -CAfile certs/dev-server.pem \
  -verify_hostname localhost \
  -verify_return_error \
  -showcerts \
  -alpn h2,http/1.1 < /dev/null
~~~

**Khi thành công**, OpenSSL có thể báo:

~~~text
Verify return code: 0 (ok)
~~~

Phần đầu ra còn có TLS version, cipher và ALPN protocol nếu thương lượng được. **ALPN protocol: h2** nghĩa là đường TLS đã chọn HTTP/2; nếu chỉ chọn http/1.1, chứng thư vẫn có thể hoàn toàn hợp lệ. Vì OpenSSL s_client chỉ test TLS/ALPN, nó **không phải HTTP/2 client đầy đủ**; muốn kiểm tra HTTP response, dùng curl có build hỗ trợ HTTP/2 hoặc Java HttpClient.

Với curl hỗ trợ HTTP/2:

~~~bash
curl -v --http2 --cacert certs/dev-server.pem \
  https://localhost:8443/ping
~~~

Nếu curl build không có hỗ trợ HTTP/2, tùy chọn --http2 có thể bị từ chối; đó **không phải lỗi chứng thư**.

## 8. Lab Java 17: truststore và hostname được kiểm tra tách biệt

### 8.1. Java HttpClient độc lập, không cần Maven

Tạo **TlsProbe.java** ở root dự án:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class TlsProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java TlsProbe https://host:port/path");
            System.exit(2);
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .version(HttpClient.Version.HTTP_2)
                .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(args[0]))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        System.out.println("status=" + response.statusCode());
        System.out.println("body=" + response.body().strip());
    }
}
~~~

Đây là **chương trình Java 17 độc lập**. Nó dùng trust policy mặc định của JDK/truststore đã cấu hình và **không** có hack trust-all, hostnameVerifier giả hoặc cấu hình bỏ kiểm tra chứng thư. **HttpClient.Version.HTTP_2** là ưu tiên giao thức, không bảo đảm ALPN chọn h2; mã chỉ in status và body để stdout ổn định.

Biên dịch:

~~~bash
javac -encoding UTF-8 TlsProbe.java
~~~

Thử chưa có truststore lab:

~~~bash
java TlsProbe https://localhost:8443/ping
~~~

**Dự kiến:** JDK sẽ từ chối self-signed certificate trong lab nếu nó chưa được trust; stack trace có thể nhắc **SSLHandshakeException / PKIX path building failed**. Nếu runtime đã được cấu hình trust CA lab từ trước, kết quả có thể khác.

### 8.2. Tạo truststore riêng chỉ dành cho lab

Dùng certificate công khai đã xuất ở phần 7:

~~~bash
keytool -importcert \
  -alias lab-server-trusted \
  -file certs/dev-server.pem \
  -keystore certs/lab-truststore.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -noprompt
~~~

**-noprompt chỉ phù hợp ở lab**, nơi certificate do chính ta tạo và biết nguồn. Trong production, phải **xác minh CA/fingerprint bằng kênh độc lập** và không tự động trust một certificate lấy từ kết nối đang thất bại. File truststore ở đây chứa certificate được trust, không cần server private key.

Kiểm tra alias:

~~~bash
keytool -list -v \
  -keystore certs/lab-truststore.p12 \
  -storetype PKCS12 \
  -storepass changeit
~~~

Chạy Java với **truststore đúng**:

~~~bash
java \
  -Djavax.net.ssl.trustStore=certs/lab-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=changeit \
  TlsProbe https://localhost:8443/ping
~~~

Các flag -D phải đặt **trước tên class**. Trên Linux/macOS, dấu \ cuối dòng là ký hiệu nối dòng; trong PowerShell có thể viết trên **một dòng**.

**Stdout chính xác khi server demo chạy, đã kết nối hợp lệ:**

~~~text
status=200
body=TLS OK
~~~

Server có thể đàm phán HTTP/2 hoặc HTTP/1.1; kết quả body/status không phụ thuộc điều đó. Nếu app chạy từ working directory khác, đường dẫn truststore tương đối có thể sai; hãy dùng path tuyệt đối để chẩn đoán.

### 8.3. Vẫn lỗi khi hostname sai dù đã trust

Chạy cùng truststore nhưng đổi URL sang IP:

~~~bash
java \
  -Djavax.net.ssl.trustStore=certs/lab-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=changeit \
  TlsProbe https://127.0.0.1:8443/ping
~~~

**Dự kiến:** báo lỗi TLS/hostname vì certificate không có **IP SAN:127.0.0.1**. Đây là bằng chứng rõ ràng hai kiểm tra tách biệt:

- **Trust được cấu hình đúng:** leaf được chấp nhận làm trust anchor của lab.
- **Hostname không khớp:** Java vẫn phải từ chối URL dùng IP không nằm trong SAN.

**Không sửa bằng cách tắt hostname verification.** Thay URL đúng hostname hoặc tái cấp certificate chứa SAN hợp lệ.

### 8.4. Khi nào truststore riêng gây thêm lỗi?

Đặt **javax.net.ssl.trustStore** cho default SSLContext của JVM thường khiến client dùng **trust anchors của store đó** thay vì tự động cộng vào toàn bộ CA mặc định. Một file chỉ chứa lab certificate có thể khiến gọi **https://public.example** qua cùng client bắt đầu lỗi PKIX.

Trong ứng dụng Spring Boot gọi nhiều upstream, nên cấu hình **SSLContext hoặc SSL bundle riêng cho client cần CA nội bộ**, tránh sửa toàn bộ global trust policy khi không cần. Trong production, không đưa password thật vào shell history hay startup logs; sử dụng secret injection theo chính sách hệ thống.

## 9. Spring Boot 3.3: SSL bundle, server keystore và client truststore

### 9.1. SSL bundle cho server (private key + cert chain)

Spring Boot 3.3 hỗ trợ **spring.ssl.bundle** để khai báo named SSL materials. Ví dụ tham khảo dùng PEM từ một hệ thống phát hành chứng thư nội bộ, giả sử file đã tồn tại và được cấp đúng quyền:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        web-server:
          keystore:
            certificate: "file:/etc/app/tls/fullchain.pem"
            private-key: "file:/etc/app/tls/server-key.pem"
server:
  port: 8443
  ssl:
    bundle: web-server
~~~

Đây là **cấu hình triển khai minh họa**, không phải ví dụ local lab với file tạo ở phần 7. **fullchain.pem** ở đây cần chứa leaf và intermediate phù hợp; private key phải tương ứng leaf và chỉ cho process được quyền đọc. Spring Boot không tự lấy/renew chứng thư của CA; certificate rotation phải do hệ thống riêng quản lý.

**Server keystore cần private key** để xác thực máy chủ; chỉ cấu hình truststore bên server mà không có server key/cert không đủ để bật HTTPS.

### 9.2. SSL bundle cho client (truststore CA riêng)

Nếu một client của Spring Boot chỉ truy cập upstream nội bộ có CA được doanh nghiệp tin cậy, cấu hình riêng:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        internal-ca:
          truststore:
            location: "file:/etc/app/tls/internal-ca-truststore.p12"
            password: "provided-by-secret-system"
            type: PKCS12
~~~

**provided-by-secret-system** là chuỗi minh họa cấu trúc, **không phải mật khẩu thật**; trong production dùng secret injection thay vì literal. Đặt file từ CA quản trị và kiểm tra chain/fingerprint. Nếu client này còn cần kết nối public CA, phải thiết kế bộ trust phù hợp; đừng mặc định truststore riêng sẽ tự cộng hết CA hệ thống.

Trong **Spring Boot 3.3**, **RestClientSsl** cho phép áp bundle lên RestClient.Builder:

~~~java
// Fragment đặt trong @Configuration; không phải chương trình độc lập.
@Bean
RestClient internalRestClient(RestClient.Builder builder, RestClientSsl ssl) {
    return builder.baseUrl("https://internal-api.example.test")
            .apply(ssl.fromBundle("internal-ca"))
            .build();
}
~~~

Cần import **org.springframework.boot.autoconfigure.web.client.RestClientSsl**, **org.springframework.web.client.RestClient** và **@Bean**, đặt trong lớp cấu hình. **Tên bundle phải khớp** cấu hình. Cách này giới hạn CA riêng cho client cụ thể tốt hơn so với tắt certificate verification toàn ứng dụng.

Spring Boot cũng cung cấp cơ chế ứng dụng SSL bundles cho WebClient, RestTemplate và các thành phần hỗ trợ, nhưng **API cụ thể phụ thuộc phiên bản Boot và client connector**. Nếu dùng Reactor Netty/WebFlux, không bê cấu hình JDK HttpClient hoặc Tomcat sang Netty một cách máy móc.

### 9.3. TLS termination tại ingress/load balancer

Trong Kubernetes hoặc hạ tầng doanh nghiệp, TLS có thể được terminate ở:
- Ingress/Reverse proxy (client → ingress TLS; ingress → Spring Boot có thể HTTP hoặc HTTPS khác);
- Service mesh sidecar;
- Chính embedded Tomcat/Netty;
- Gateway trung gian có HTTPS inspection.

Khi certificate người dùng nhìn thấy nằm ở ingress, **đổi server.ssl.key-store của Spring Boot không làm certificate public của ingress đổi**. Phải xác định **hops** thực tế và kiểm tra đúng điểm terminate; mỗi hop TLS có thể dùng một CA, hostname, SNI và truststore khác nhau.

## 10. Bốn mẫu lỗi cần tách rõ

### 10.1. SSLHandshakeException: PKIX path building failed

**Ý nghĩa:** client không dựng được đường chứng thư hợp lệ đến trust anchor theo chính sách đang dùng.

Khả năng:
- CA root không trong truststore.
- Server/TLS proxy thiếu intermediate.
- Client chạy JDK/container image với cacerts cũ/khác.
- Corporate HTTPS inspection thay leaf bằng cert do private CA ký mà Java không trust.
- Ứng dụng dùng custom truststore/SSL bundle không chứa CA cần thiết.

Cách làm:
1. Xác nhận đúng URL/SNI/port/proxy.
2. Lấy chain với **openssl s_client -showcerts -servername**.
3. Xem Issuer/Subject/SAN/timestamp, verify với trust anchor đã biết.
4. Kiểm tra JVM/container đang dùng truststore nào.
5. Nếu server thiếu intermediate, sửa full chain trên server/ingress. Nếu CA nội bộ hợp lệ nhưng chưa trust, nhập **CA đã xác minh** vào store của **client cần dùng**.

Không chữa bằng **curl -k**, **trustAllCertificates**, **HostnameVerifier luôn true** hay nới global policy một cách tùy tiện.

### 10.2. Hostname mismatch / No subject alternative name

**Ý nghĩa:** certificate được trình bày không chứa hostname/IP chính xác mà client đang yêu cầu.

Các nguyên nhân:
- URL dùng IP thay vì DNS name có trong SAN.
- Cert cấp cho domain khác.
- SNI không gửi hoặc gửi sai, làm load balancer trả default certificate.
- Chứng thư đã được rotate trên một replica nhưng không phải tất cả.

**Sửa:** kiểm tra certificate/SAN theo đúng SNI, route và cấp lại/cấu hình đúng chứng thư. **Import CA không làm SAN đổi**.

### 10.3. Certificate expired / not yet valid

**Ý nghĩa:** certificate không nằm trong khoảng NotBefore/NotAfter hoặc client/server clock không đúng. Xem cả **leaf và intermediates**.

**Sửa:** kiểm tra UTC/NTP và cấp/triển khai chain mới đúng hạn. Nếu chỉ browser cache phiên cũ hoặc node rollout chưa hoàn tất, kiểm tra toàn bộ endpoints/replicas bằng SNI/IP riêng. Không tắt date validation.

### 10.4. handshake_failure / protocol_version / bad_certificate

Thông báo rộng hơn, **không tự kết luận** do root CA. Có thể do:
- Không có TLS version/cipher/signature algorithm chung.
- SNI hoặc ALPN policy của proxy.
- Keystore server không có private key/certificate đúng hoặc key usage không hợp lệ.
- mTLS yêu cầu client certificate nhưng client không gửi, hoặc server không trust client CA.
- Client gửi certificate sai mục đích hoặc chain client không đầy đủ.

Cần xem **cả client và server TLS logs**, đặc biệt nơi phát alert. Với mTLS, client keystore dùng certificate + private key của client; server truststore dùng CA tin client. Tránh sửa nhầm client truststore khi thực chất **server đang từ chối client certificate**.

## 11. JSSE debug và quy trình chẩn đoán có kiểm soát

### 11.1. Java TLS debug flags

Khi chạy lab hoặc trong môi trường chẩn đoán được bảo vệ:

~~~bash
java \
  -Djavax.net.debug=ssl,handshake,trustmanager \
  -Djava.security.debug=certpath \
  TlsProbe https://localhost:8443/ping
~~~

Đây là **lệnh diagnostic**: Java có thể phát nhiều log qua stderr cho handshake, trust manager và path building. Có thể thêm **-Djavax.net.ssl.trustStore...** như ở phần 8 nếu cần. Không coi việc thấy Certificate message trong log là bằng chứng certificate đã verify thành công; hãy tìm lỗi gốc/điều kiện xác minh.

**Cảnh báo bảo mật:** debug TLS có thể phơi metadata chứng thư, hostname và chi tiết phiên; các tùy chọn data/packet/plaintext có rủi ro lộ thông tin hơn. Chỉ bật tạm thời, bảo vệ file log, tắt sau khi hoàn tất và không đưa secret vào báo cáo công khai.

### 11.2. Checklist theo thứ tự chính xác

1. **Chọn một URL lỗi cụ thể**, ghi thời gian, host, port, scheme, môi trường và lỗi gốc (caused by).
2. **Kiểm tra network:** DNS, TCP, proxy, ingress và endpoint thực tế.
3. **Kiểm tra TLS server certificate** bằng s_client với **-servername đúng**; không quên virtual hosting.
4. **Kiểm tra hostname/IP:** SAN của leaf so với URL thực; với IP yêu cầu IP SAN.
5. **Kiểm tra chain:** leaf/intermediates server gửi; dựng đường lên root được tin; kiểm tra ngày, EKU, KeyUsage, policy.
6. **Kiểm tra Java truststore thật** của đúng JDK/container/client; xem JVM properties và SSL bundle/custom SSLContext.
7. **Kiểm tra mTLS** nếu server yêu cầu client cert; xác định ai kiểm tra cert của ai.
8. **Kiểm tra HTTP/2 ALPN** sau khi TLS hợp lệ; phân biệt việc không chọn h2 với handshake failure.
9. **Áp sửa đúng tầng:** bổ sung missing intermediate trên server, cập nhật root CA hợp lệ ở client, cấp lại SAN đúng, thay cert hết hạn, hoặc sửa proxy route.
10. **Kiểm tra lại từ ứng dụng Java thật**, không chỉ trình duyệt/curl; giữ hostname verification, trust validation bật.

Với ứng dụng nhiều instance, làm phép thử theo từng IP nhưng vẫn giữ **hostname SNI và xác minh hostname** (ví dụ curl --resolve), tránh suy luận từ một replica duy nhất.

## 12. Bảng chẩn đoán nhanh

| Triệu chứng | Tầng gần nhất | Điều cần phân biệt |
| --- | --- | --- |
| Connection refused / timed out | TCP/network | Port, firewall, proxy, service readiness |
| UnknownHostException | DNS | Hostname, resolver, network |
| SSLHandshakeException + PKIX path building failed | Certificate chain/trust | Missing intermediate vs root CA thiếu vs custom truststore |
| No subject alternative DNS name matching ... | Hostname | URL/SAN/SNI/default cert |
| No subject alternative names matching IP address ... | Hostname IP | Cần IP SAN hoặc URL DNS hợp lệ |
| CertificateExpiredException | Validity | Leaf/intermediate và clock/NTP |
| Received fatal alert: bad_certificate | TLS/mTLS hoặc certificate policy | Ai phát alert, cert của chiều nào bị từ chối |
| Received fatal alert: protocol_version | TLS negotiation | Client/server version, policy |
| TLS handshake OK, HTTP 401/403 | HTTP authentication/authorization | Credential, roles, request context |
| TLS OK, HTTP 404 | Routing | URL/context path/controller/ingress |
| TLS OK, HTTP 502 | Gateway/upstream | Hop nào thất bại; có TLS riêng gateway → app? |
| TLS OK nhưng không có h2 | HTTP/2 ALPN/runtime | Client ALPN, server.http2.enabled, TLS termination |
| Browser mở được, Java báo PKIX | Trust sources có thể khác | JDK truststore vs OS/browser, missing intermediate, corporate proxy |
| Chỉ một Pod/host lỗi | Cert/config rollout | Keystore/chain/CA/cert expiry khác nhau giữa replica |

**Quy tắc:** luôn đọc **root cause** của stack trace, không chỉ exception ở lớp trên cùng. Một lỗi IOException có thể bọc SSLHandshakeException; một lỗi HTTP 502 ở ingress có thể che lỗi TLS tới upstream.

## 13. Sai lầm thường gặp và hậu quả bảo mật

**Sai lầm 1 — Dùng curl -k như bản sửa production.** Cờ -k/--insecure tắt kiểm tra chứng thư phía curl; nó chỉ có thể là phép phân lập tạm thời trong môi trường được kiểm soát. Dùng lâu dài khiến client dễ bị MITM.

**Sai lầm 2 — Trust tất cả certificate trong Java.** Tạo TrustManager luôn trả thành công hoặc HostnameVerifier luôn true phá hủy mục tiêu xác thực server. Không đưa mẫu này vào code thật.

**Sai lầm 3 — Import leaf bất kỳ vừa lấy từ server vào cacerts.** Người kiểm tra có thể đang kết nối tới server giả mạo. Chỉ trust CA/cert sau khi xác minh **fingerprint và nguồn gốc bằng kênh độc lập**; ưu tiên truststore dành riêng cho endpoint.

**Sai lầm 4 — Cho rằng server phải gửi root.** Root là trust anchor của client; server thường gửi leaf + intermediates. Thiếu intermediate mới là nguyên nhân quan trọng phải xem.

**Sai lầm 5 — Cho rằng CN đúng là đủ.** SAN hiện là nguồn danh tính chính. URL theo IP cần IP SAN; thêm root không sửa mismatch.

**Sai lầm 6 — Không đặt SNI khi test nhiều domain chung IP.** Bạn có thể nhận cert default rồi kết luận sai server. Dùng s_client -servername hoặc curl URL hostname + --resolve.

**Sai lầm 7 — Sửa truststore trên laptop thay vì container đang lỗi.** JDK image và JVM properties thực mới quyết định Java trust policy.

**Sai lầm 8 — Nhầm key store với trust store.** Server cần private key cho HTTPS; client cần trust anchors để xác thực server; mTLS thêm chiều client cert khác.

**Sai lầm 9 — Nhầm HTTP/2 handshake với PKIX.** ALPN chọn HTTP application protocol nhưng không thay xác minh chain; HTTP/2 không sửa được lỗi CA.

**Sai lầm 10 — Đọc log debug TLS rồi chia sẻ không kiểm soát.** Metadata hoặc dữ liệu chẩn đoán có thể nhạy cảm; hạn chế bật, lưu và phát tán.

## 14. Bài tập thực hành

**Bài 1.** Curl đã trust dev-server.pem và gọi **https://localhost:8443/ping** trả 200, nhưng **https://127.0.0.1:8443/ping** bị từ chối. Vì sao?

**Đáp án:** Certificate chỉ có DNS SAN:localhost, không có IP SAN:127.0.0.1. Đây là **hostname/IP validation**, không phải thiếu trust anchor.

**Bài 2.** Java báo PKIX path building failed, browser mở cùng URL được. Có thể kết luận root CA của website đã sai không?

**Đáp án:** Không. Java và browser có thể dùng trust store/chain caching khác nhau; server có thể thiếu intermediate hoặc JVM dùng JDK/custom truststore khác. Cần quan sát SNI/chain/truststore Java thật.

**Bài 3.** Server gửi leaf và root nhưng bỏ intermediate. Root đã được Java trust, vì sao client vẫn có thể lỗi?

**Đáp án:** Không có certificate trung gian cần thiết để chứng minh chữ ký leaf lên root. Sửa server phát đúng intermediate/full chain (hoặc cơ chế provisioning chain tin cậy thích hợp); root gửi kèm không làm thay truststore.

**Bài 4.** Import private CA vào truststore giúp Java kết nối tới host A nhưng host B vẫn báo No subject alternative DNS name matching. Có nên import thêm root?

**Đáp án:** Không theo mặc định. Hostname B không có trong SAN của certificate đang xuất trình; kiểm tra URL/SNI/certificate đúng host, cấp lại nếu cần.

**Bài 5.** Java dùng **-Djavax.net.ssl.trustStore=lab-truststore.p12** có một leaf lab, rồi gọi public API báo PKIX. Vì sao?

**Đáp án:** Với default SSLContext JSSE, custom truststore có thể thay tập root mặc định, nên public CA không còn trong nguồn trust được dùng. Hãy cấu hình riêng cho client nội bộ hoặc xây trust policy có chủ đích.

**Bài 6.** Browser thấy HTTP 401 từ HTTPS endpoint. TLS handshake có chắc lỗi không?

**Đáp án:** HTTP 401 nghĩa là có response ở tầng HTTP sau một kênh truyền; nếu chính browser kết nối HTTPS trực tiếp và không có thông báo proxy đặc biệt, handshake tới endpoint trả response đã diễn ra, còn 401 cần kiểm tra credential/authorization.

**Bài 7.** openssl s_client không có -servername cho một IP chạy nhiều virtual hosts. Kết quả có đáng tin để kết luận chứng thư của api.example.test bị sai không?

**Đáp án:** Chưa. Có thể server trả default certificate. Gửi SNI đúng và kiểm tra theo URL hostname thực tế.

**Bài 8.** TLS kết nối được nhưng ALPN là http/1.1 dù mong h2. Có nên sửa truststore?

**Đáp án:** Không nếu chain/hostname đã hợp lệ. Kiểm tra server.http2.enabled, ALPN support, JDK/connector và proxy/TLS terminator.

**Bài 9.** Lỗi bad_certificate xảy ra khi server yêu cầu mutual TLS. Cần kiểm tra certificate ở chiều nào?

**Đáp án:** Có thể là certificate **client gửi cho server**; xác định peer phát alert và xem server truststore, client keystore, EKU/clientAuth và chain ở chiều đó.

**Bài 10.** Vì sao không nên gửi stdout đầy đủ của javax.net.debug cho bên ngoài?

**Đáp án:** Debug có thể tiết lộ hostname, chứng thư, thông tin phiên hoặc dữ liệu nhạy cảm tùy flags; cần mask/giới hạn quyền và chỉ thu thập cần thiết.

## 15. Kết luận và checklist

**TLS handshake** là quá trình thiết lập kết nối bảo mật; **certificate chain/truststore** quyết định có tin khóa công khai của server không; **hostname verification** bảo đảm chứng thư ấy dành cho đúng host/IP đang truy cập. Chúng là những kiểm tra **cùng cần đạt**, không phải các tên gọi thay thế nhau.

Trước khi sửa lỗi HTTPS trong Spring Boot/Java:
- Xác định đúng **URL → DNS/IP → proxy/ingress → port**.
- Quan sát **SNI và certificate thực tế** mà server gửi.
- Kiểm tra **SAN, NotBefore/NotAfter, leaf/intermediate/root, EKU và thuật toán**.
- Kiểm tra **truststore của đúng JVM/container**; không dùng trust-all.
- Nếu thiếu intermediate, **sửa server full chain**; nếu private CA hợp lệ, **provision trust anchor** vào client đúng phạm vi.
- Nếu SAN sai, sửa **hostname/route/certificate**, không import CA vô tội vạ.
- Nếu server yêu cầu mTLS, phân biệt **client key material** và **server trust material**.
- Sau khi TLS đúng, mới kiểm tra **ALPN HTTP/2** và HTTP status.
- Thử lại từ **Java client thật**; không suy luận chỉ từ curl/browser.
- Bảo vệ private key và logs; không đưa mật khẩu demo/truststore lab lên production.

## Tài liệu tham khảo chính thức

- RFC 8446 — TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446
- Oracle Java 17 — keytool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- Oracle — Java Secure Socket Extension Reference Guide: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
- Spring Boot 3.3 — SSL bundles: https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
- Spring Boot 3.3 — RestClientSsl: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientSsl.html
- Spring Boot 3.3 — Embedded Web Servers and HTTP/2: https://docs.spring.io/spring-boot/3.3/reference/how-to/webserver.html
- OpenSSL s_client: https://docs.openssl.org/master/man1/openssl-s_client/
- OpenSSL verify: https://docs.openssl.org/master/man1/openssl-verify/
