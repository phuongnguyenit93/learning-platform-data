# Triển khai HTTPS với SSL bundle và kiểm chứng HTTP/2

## 1. Mục tiêu và tiêu chí hoàn tất

Đây là bài **Thực hành tổng hợp** trong module **Spring Boot - web-runtime**. Nhiệm vụ là chạy **Spring Boot 3.3.13, Java 17, embedded Tomcat 10.1** qua HTTPS bằng **named SSL bundle**, rồi kiểm chứng rằng request thực sự sử dụng **HTTP/2 (h2) qua TLS**.

Hai suy luận rất phổ biến nhưng sai:
- **server.http2.enabled=true** không bảo đảm mọi client hoặc reverse proxy đang dùng HTTP/2. Đó là yêu cầu bật khả năng trên server. Kết quả cuối cùng còn phụ thuộc TLS, ALPN, client và đường đi request.
- Client gọi URL HTTPS thành công không chứng minh Spring Boot đang terminate TLS. Một Ingress hoặc Load Balancer có thể terminate HTTPS và chuyển tiếp HTTP/1.1 cleartext tới Tomcat.

Bài học yêu cầu ba lớp bằng chứng độc lập:
1. **TLS identity đúng**: certificate chain được CA tin cậy xác thực, SAN đúng hostname, certificate còn hạn. Không dùng trust-all hoặc curl -k để cho test qua.
2. **Giao thức đúng**: ALPN thực sự chọn **h2** và client nhận **HTTP/2**, không chỉ có flag cấu hình.
3. **Nghiệp vụ đúng**: endpoint trả HTTP 200/body mong đợi, Spring Boot/Pod ready, TLS key được mount ngoài JAR, có kiểm thử rotation/failure.

Bạn sẽ thực hành tạo CA/certificate localhost, cấu hình **spring.ssl.bundle.pem**, chạy curl/OpenSSL/Java HttpClient, viết integration test real-port, build Docker image không nhúng private key, triển khai Kubernetes bằng TLS Secret và chẩn đoán fallback HTTP/1.1.

**Phạm vi:** Spring Boot 3.3.13, Spring MVC (Servlet), Tomcat 10.1, Java 17+. Chứng chỉ do bài tạo **chỉ dành cho localhost hoặc môi trường lab được phép**. Với production phải dùng PKI/CA và security policy của tổ chức.

## 2. HTTPS, TLS, ALPN và HTTP/2 khác nhau ở đâu?

~~~text
Client
   |
   | TCP connect đến localhost:8443
   v
TLS handshake
   |-- Kiểm chain CA, expiry, SAN/hostname
   |-- Thỏa thuận TLS version và cipher
   |-- ALPN: client đề nghị h2, http/1.1
   |-- Server chọn h2 nếu hai bên cùng hỗ trợ
   v
HTTP/2 framing: streams, headers, flow control
   |
   v
Embedded Tomcat HTTP/2 support (Java 17)
   |
   v
DispatcherServlet / Controller
   |
   v
HTTP 200 + body secure-ok
~~~

**TLS** mã hóa và xác thực một kết nối giữa TLS peers; **HTTP/2** là giao thức ứng dụng chạy qua kết nối. HTTP/2 sử dụng binary frames, multiplex nhiều streams trên cùng TCP connection, HPACK và stream flow control. Không có quan hệ “bật HTTP/2 thì TLS tự bật”.

| Protocol | Có TLS trên hop đó? | Ví dụ |
| --- | --- | --- |
| **HTTP/1.1** | Có thể có (HTTPS) hoặc không | Một HTTPS client không negotiate h2 |
| **h2** | Có; HTTP/2 over TLS | Client/embedded Tomcat dùng ALPN h2 |
| **h2c** | Không; HTTP/2 cleartext | Hop nội bộ qua proxy nếu đã được bảo vệ mạng |

Theo **Spring Boot 3.3**, **server.http2.enabled=true** hỗ trợ cả h2 và h2c trên web servers phù hợp. Khi server SSL bật, HTTP/2 chạy h2 qua TLS; khi SSL tắt có thể dùng h2c. Java 17 có JSSE ALPN support; Tomcat 10.1 hỗ trợ h2 mà **không bắt buộc phải thêm tomcat-native** trong bài lab này.

### 2.1. HTTPS và HTTP/2 không đồng nghĩa TLS 1.3

HTTP/2 over TLS có thể dùng TLS 1.2 hoặc 1.3 với các cipher/protocol thỏa chính sách. Nói “HTTP/2 bắt buộc TLS 1.3” là sai. Java 17 thường có TLS 1.3 nhưng ALPN negotiation và certificate verification vẫn phải được quan sát.

### 2.2. Bật h2 không giải quyết tất cả nghẽn

HTTP/2 giảm overhead của nhiều request và multiplex streams, nhưng JDBC blocking, Tomcat threads, database pool, request timeouts, TCP congestion, header limits và memory vẫn hữu hạn. Một kết nối HTTP/2 có thể có nhiều streams; **connection count không bằng số request đồng thời**.

## 3. Topology: xác định chính xác nơi terminate TLS

~~~text
A. HTTPS trực tiếp
Client -- h2/TLS --> Tomcat HTTPS 8443
                     (server.ssl.bundle=web)

B. HTTPS ở Ingress
Client -- h2/TLS --> Ingress -- HTTP/1.1 --> Tomcat HTTP 8080

C. TLS re-encryption
Client -- h2/TLS --> Ingress -- TLS/h2 hoặc TLS/h1 --> Tomcat HTTPS

D. TLS passthrough
Client -- TLS/h2 --> TCP Load Balancer --> Tomcat HTTPS
                     (LB không decrypt TLS)
~~~

Bài **thực hành A** nên kết quả curl/Java thật sự phản ánh TLS và HTTP/2 tại embedded Tomcat. Với B, browser thấy HTTP/2 ở public domain **không chứng minh backend Tomcat chạy h2**. Với C, có **hai TLS handshakes**, mỗi handshake negotiate ALPN độc lập. Với D, TLS tới thẳng Tomcat dù qua một LB TCP.

Khi báo cáo một lần kiểm thử, phải ghi:
- URL và địa chỉ endpoint đã gọi.
- TLS được terminate ở proxy hay application.
- Certificate/CA dùng xác minh hop nào.
- ALPN được chọn bởi TLS peer nào.
- Protocol của request ở client-facing và backend-facing hops.

Đừng coi **X-Forwarded-Proto: https** là bằng chứng một hop backend được mã hóa. Header đó chỉ mô tả thông tin proxy chuyển tiếp nếu đến từ trusted proxy; attacker có thể tự gửi nếu ingress không sanitize.

## 4. SSL bundle: PEM, JKS/PKCS12, tên và phạm vi

Spring Boot 3.3 hỗ trợ **named SSL bundles**. Một bundle chứa key material, trust material và các options cần thiết cho TLS:
- **spring.ssl.bundle.pem.<name>**: PEM certificate, private key, trust certificates.
- **spring.ssl.bundle.jks.<name>**: JKS hoặc PKCS12 key/trust stores.
- **server.ssl.bundle: <name>**: áp bundle đã đặt tên cho embedded server.
- **SslBundles**: bean API để consumer/integration truy xuất named bundles.
- **spring.ssl.bundle.<type>.<name>.options**: TLS options của bundle.

Ví dụ PEM bundle tên **web**:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        web:
          keystore:
            certificate: "file:./tls/server.crt"
            private-key: "file:./tls/server-pkcs8.key"

server:
  port: 8443
  ssl:
    bundle: web
~~~

Đây là chứng chỉ và private key **server dùng để trình danh tính**. Client cần **tin CA ký cert server** (hoặc một trust anchor phù hợp) để hoàn tất verification. **Truststore phía server** không thay thế server private key; nó được dùng khi server cần kiểm certificate của peer, ví dụ mTLS.

### 4.1. Không trộn bundle với discrete server.ssl.*

Nếu đã dùng **server.ssl.bundle**, không khai báo cùng lúc các discrete **server.ssl.key-store**, **server.ssl.certificate** hay **server.ssl.certificate-private-key** để chọn hai nguồn key material. Theo tài liệu Boot 3.3, **server.ssl.ciphers**, **server.ssl.enabled-protocols** và **server.ssl.protocol** bị bỏ qua khi dùng bundle; cần đưa TLS options vào **spring.ssl.bundle...options** tương ứng.

Không chọn tên bundle tùy tiện giữa nhiều môi trường: **server.ssl.bundle: web** phải khớp **spring.ssl.bundle.pem.web** hoặc nhánh JKS được cấu hình. Tài liệu Boot lưu ý bundle names qua environment variable được chuẩn hóa thành **lowercase**.

### 4.2. PEM, keystore, certificate chain

Ba tệp chính cho bài lab:
- **tls/ca.crt**: certificate CA thử nghiệm; **client** dùng làm trust anchor.
- **tls/server.crt**: certificate leaf với SAN localhost và 127.0.0.1; **server** gửi.
- **tls/server-pkcs8.key**: private key server ở định dạng PKCS#8; **server** giữ kín.

**tls/ca.key** là private key của CA để ký certificates. Nó **không được mount vào Spring Boot**. Với public PKI, server thường phải trình đủ intermediate chain đúng thứ tự; client có root trust store của mình.

## 5. Tạo local CA và certificate hợp lệ cho localhost

Chạy trên Linux/macOS/WSL có OpenSSL. Tạo files trước Maven tests; tất cả lệnh chạy tại **root thư mục https-h2-lab**.

### 5.1. Local CA, chỉ dùng lab

~~~bash
mkdir -p tls

openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 10 \
  -keyout tls/ca.key -out tls/ca.crt \
  -subj "/CN=Local HTTPS H2 Demo CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
~~~

Dùng private key **không mã hóa chỉ vì tính tiện lợi của lab**; production phải quản lý private CA key và server key theo PKI/secret-management policy. CA demo này không phải public CA và không nên cài trust toàn máy.

### 5.2. Tạo server key và CSR

~~~bash
openssl req -newkey rsa:3072 -nodes -sha256 \
  -keyout tls/server.key \
  -out tls/server.csr \
  -subj "/CN=localhost"
~~~

CN không đủ để bảo đảm hostname verification. Cần thêm **SAN** để client đối chiếu hostname/IP.

### 5.3. Khai báo SAN và key usage

~~~bash
cat > tls/server.ext <<'EOF'
subjectAltName=DNS:localhost,IP:127.0.0.1
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EOF
~~~

Giải thích:
- **DNS:localhost**: URL https://localhost:8443.
- **IP:127.0.0.1**: URL https://127.0.0.1:8443.
- **CA:FALSE**: certificate leaf không dùng làm CA.
- **serverAuth**: chứng chỉ được dùng cho server authentication.

Không lấy một certificate có SAN localhost để phục vụ api.example.com; TLS hostname validation phải thất bại với host ngoài SAN.

### 5.4. Ký và chuyển private key sang PKCS#8

~~~bash
openssl x509 -req -in tls/server.csr \
  -CA tls/ca.crt -CAkey tls/ca.key -CAcreateserial \
  -out tls/server.crt -days 7 -sha256 \
  -extfile tls/server.ext

openssl pkcs8 -topk8 -nocrypt \
  -in tls/server.key \
  -out tls/server-pkcs8.key

chmod 600 tls/ca.key tls/server.key tls/server-pkcs8.key
~~~

PEM PKCS#8 thường có header **BEGIN PRIVATE KEY**. Nếu native OpenSSL tạo PKCS#1 **BEGIN RSA PRIVATE KEY**, bước chuyển sang PKCS#8 giúp tránh phụ thuộc format/cách parse key trong các bản thư viện.

### 5.5. Chứng minh certificate đúng trước khi chạy JVM

~~~bash
openssl verify -CAfile tls/ca.crt \
  -verify_hostname localhost tls/server.crt

openssl x509 -in tls/server.crt -noout \
  -subject -issuer -dates -ext subjectAltName

openssl pkey -in tls/server-pkcs8.key -noout -check
~~~

Với certificate vừa tạo thành công, **openssl verify** trả kết quả kết thúc bằng **OK**, SAN có DNS:localhost và IP:127.0.0.1. Các giá trị notBefore, notAfter, serial, fingerprint thay đổi theo thời điểm tạo; không đưa stdout động thành snapshot cố định.

Tạo **.gitignore**:

~~~gitignore
tls/*.key
tls/*.p12
tls/*.srl
tls/*.csr
target/
~~~

Certificate public không phải private key, nhưng cả bộ demo không nên tái sử dụng cho môi trường thật. Không commit **tls/ca.key**, **tls/server.key**, **tls/server-pkcs8.key**.

## 6. Dự án Maven và cấu trúc thư mục

~~~text
https-h2-lab/
├── pom.xml
├── Dockerfile
├── k8s.yaml
├── Http2Proof.java
├── tls/
│   ├── ca.crt
│   ├── ca.key
│   ├── server.crt
│   ├── server.key
│   ├── server-pkcs8.key
│   └── server.ext
└── src/
    ├── main/
    │   ├── java/com/example/httpsdemo/HttpsDemoApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/httpsdemo/HttpsHttp2Test.java
~~~

Certificate/key không nằm trong **src/main/resources**; dùng external filesystem để thay key mà không cần build lại JAR. Tệp SSL trong source package không được dùng làm repository secrets.

Tạo **pom.xml**:

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
    <artifactId>https-h2-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

**spring-boot-starter-web** dùng Spring MVC + embedded Tomcat 10.1 trong Boot 3.3. Java 17 hỗ trợ ALPN. **spring-boot-starter-actuator** tạo health probes phục vụ deploy; **spring-boot-starter-test** cung cấp JUnit Jupiter và Spring Boot integration tests. Bài không yêu cầu tự thêm Tomcat Native, Netty hoặc Jetty HTTP2 modules.

## 7. application.yml: bundle web, port 8443, HTTP/2 enabled

Tạo **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8443
  ssl:
    bundle: web
  http2:
    enabled: true
  shutdown: graceful

spring:
  ssl:
    bundle:
      pem:
        web:
          keystore:
            certificate: "${TLS_CERT_LOCATION:file:./tls/server.crt}"
            private-key: "${TLS_KEY_LOCATION:file:./tls/server-pkcs8.key}"
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
  endpoints:
    web:
      exposure:
        include: health
~~~

**Ý nghĩa từng property:**
- **server.port=8443:** Tomcat nghe TLS HTTPS tại port 8443.
- **server.ssl.bundle=web:** chọn PEM bundle đã khai báo ở spring.ssl.bundle.pem.web.
- **server.http2.enabled=true:** bật khả năng negotiate h2 qua TLS.
- **certificate/private-key:** lấy từ env **TLS_CERT_LOCATION/TLS_KEY_LOCATION** nếu có, nếu không đọc các tệp **file:./tls/server.crt** và **file:./tls/server-pkcs8.key** ở root lab.
- **server.shutdown=graceful:** cho HTTP in-flight requests cơ hội hoàn tất khi dừng, không trực tiếp quyết định h2.
- **probes.enabled / add-additional-paths:** expose **/readyz** và **/livez** trên **cùng port HTTPS của app**.
- **management.endpoints...include=health:** không công khai Actuator env, heapdump, shutdown hoặc beans.

Nếu profile/command-line override server.ssl.bundle sai, app thường không khởi động TLS chứ không nên silent fallback HTTP. Kiểm effective property values bằng workflow vận hành nội bộ, **không bật /actuator/env công khai** để debug secrets.

### 7.1. Dùng file: chứ không classpath:

**classpath:** phù hợp resources tĩnh đóng cùng JAR nhưng có nguy cơ bake private key vào artifact. **file:** trỏ tệp ngoài image/JAR, phù hợp Docker bind mount, Kubernetes Secret và cert rotation. Với app chạy ở working directory khác, dùng absolute URI như **file:/etc/tls/tls.crt**.

### 7.2. HTTPS không tự mở HTTP 8080

Khi cấu hình SSL của embedded server trên 8443, không mặc nhiên có thêm plain HTTP 8080 hoặc redirect. Muốn hỗ trợ cả HTTP và HTTPS trong cùng Boot instance phải cấu hình thêm connector bằng Java; còn production thường xử lý HTTP→HTTPS redirect ở trusted Ingress/LB. Không gửi cleartext HTTP vào 8443 rồi mong 301.

## 8. Java 17 Spring MVC controller chạy được

Tệp **src/main/java/com/example/httpsdemo/HttpsDemoApplication.java**:

~~~java
package com.example.httpsdemo;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpsDemoApplication.class, args);
    }
}

@RestController
class TransportController {

    @GetMapping(
        path = "/api/hello",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String hello() {
        return "secure-ok";
    }

    @GetMapping("/api/transport")
    Map<String, Object> transport(HttpServletRequest request) {
        return Map.of(
            "scheme", request.getScheme(),
            "secure", request.isSecure(),
            "protocol", request.getProtocol(),
            "serverPort", request.getServerPort()
        );
    }
}
~~~

**/api/hello** phục vụ response text chính xác **secure-ok** (không thêm newline). **/api/transport** cung cấp quan sát về HTTP request **theo góc nhìn Tomcat**:
- **scheme** thường là **https** khi client trực tiếp kết nối TLS tới Tomcat.
- **secure** thường là **true**.
- **protocol** thường thể hiện **HTTP/2.0** nếu Tomcat xử lý request trên h2, hoặc **HTTP/1.1** nếu client fallback.
- **serverPort** là 8443 khi không có reverse proxy/forwarded headers thay đổi scheme/port perception.

Không xem Servlet request.getProtocol là bằng chứng duy nhất về certificate trust: client có thể gửi request sau khi tắt verification. Tương tự, khi có proxy terminate TLS, các values này chỉ phản ánh **backend hop** và forwarded headers được trust/configure.

## 9. Maven/JAR local và kiểm HTTPS cơ bản

Sau khi tạo PEM ở phần 5:

~~~bash
mvn test
mvn package
java -jar target/https-h2-lab-1.0.0.jar
~~~

Test suite khởi động real HTTPS Tomcat ở random port; **file cert phải tồn tại trước mvn test**. Nếu cert/key không đúng, fail startup là tín hiệu đúng; không tắt SSL để bỏ qua test.

Mở terminal thứ hai:

~~~bash
curl -v --cacert tls/ca.crt \
  https://localhost:8443/api/hello

curl -sS --cacert tls/ca.crt \
  https://localhost:8443/api/transport
~~~

Với TLS hợp lệ, request /api/hello trả **HTTP 200**, body **secure-ok**. Response /api/transport là JSON; thứ tự JSON fields có thể thay đổi. Đường dẫn CA trong curl buộc client tin CA thử nghiệm **cho kết nối này**, đồng thời vẫn kiểm hostname trong SAN.

### 9.1. Vì sao không dùng curl -k?

~~~bash
# KHÔNG dùng làm bằng chứng identity thành công:
curl -k https://localhost:8443/api/hello
~~~

**-k/--insecure** tắt kiểm certificate chain/hostname. Request vẫn có thể chạy h2/200 dù bị MITM hoặc cert sai. Dùng **--cacert tls/ca.crt**, OS/browser trust store đúng chuẩn, hoặc cấu hình CA theo quản trị tổ chức.

### 9.2. So sánh TLS HTTP/1.1

~~~bash
curl -i --http1.1 --cacert tls/ca.crt \
  https://localhost:8443/api/hello
~~~

Ở lab mặc định, HTTP/1.1 qua TLS vẫn có thể trả **200 secure-ok**. Đây là phép đối chứng quan trọng: HTTPS 200 **không tương đương** HTTP/2.

## 10. Chứng minh h2 bằng curl, không tin chỉ flag

Kiểm curl có HTTP/2 feature:

~~~bash
curl -V
~~~

Nếu build không có **HTTP2**, việc chạy **curl --http2** có thể báo unsupported. Khi đó dùng Java HttpClient proof ở phần 12. Không kết luận server sai chỉ vì một client binary thiếu hỗ trợ h2.

Dùng curl:

~~~bash
curl --http2 -v --cacert tls/ca.crt \
  https://localhost:8443/api/hello
~~~

Trong verbose TLS log, tìm:
1. Client ALPN offer **h2** và http/1.1.
2. Server ALPN accepted **h2**.
3. HTTP response phiên bản **HTTP/2** với status 200.
4. Certificate chain và hostname được xác minh thành công.

Dòng log chính xác có thể khác giữa curl/OpenSSL/Schannel versions, nên không snapshot toàn bộ output -v.

**Kiểm ngắn bằng write-out:**

~~~bash
curl -sS --http2 --cacert tls/ca.crt \
  -o /dev/null \
  -w 'http_version=%{http_version} http_code=%{http_code}\n' \
  https://localhost:8443/api/hello
~~~

Expected stdout khi thực sự negotiated h2 và response OK:

~~~text
http_version=2 http_code=200
~~~

Nếu thấy **http_version=1.1**, HTTPS có thể hoàn toàn đúng nhưng h2 chưa được chọn. Xem **server.http2.enabled**, client HTTP2 feature, ALPN, TLS termination/proxy path hoặc TLS compatibility. Dùng cờ **--http2** tự nó không chứng minh server đã chấp nhận h2.

## 11. OpenSSL s_client kiểm TLS + ALPN, khác HTTP request

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -alpn h2,http/1.1 \
  -CAfile tls/ca.crt \
  -verify_return_error < /dev/null
~~~

Với TLS/ALPN đúng, tìm:
- **ALPN protocol: h2**
- **Verify return code: 0 (ok)**
- TLS protocol/cipher phù hợp policy.

**-servername localhost** kích hoạt SNI để server chọn certificate theo hostname khi có nhiều bundles. **-CAfile** xác thực chain với CA demo. **-verify_return_error** làm các lỗi xác minh có ảnh hưởng tới kết nối.

**Giới hạn của s_client:** nó chỉ kiểm TLS handshake/ALPN, **không phải một HTTP/2 client gửi frames**. Cần bổ sung curl hoặc Java HttpClient để xác nhận HTTP/2 response thực tế.

### 11.1. Phân biệt HTTP plain gửi vào TLS port

~~~bash
curl -v http://localhost:8443/api/hello
~~~

Đây là request **sai scheme**. Kết nối thường lỗi protocol/network hoặc nhận phản hồi lỗi từ connector; không mong server tự chuyển thành HTTPS 301/302. HTTP→HTTPS redirect là một policy ở HTTP listener/Ingress riêng.

### 11.2. TLS cert đúng không có nghĩa h2 đúng

Một client có thể xác thực certificate thành công nhưng ALPN chọn HTTP/1.1. Ngược lại, client dùng curl -k có thể negotiate h2 với một server có certificate không hợp lệ. **Cần kiểm cả hai**, không chọn một.

## 12. Java 17 HttpClient độc lập: kiểm response.version()

JDK **java.net.http.HttpClient** hỗ trợ HTTP/2. Builder **.version(HTTP_2)** chỉ biểu thị **preferred protocol** và có thể fallback HTTP/1.1 khi có proxy/limitations. **HttpResponse.version()** mới cho biết thực tế.

Tạo file độc lập **Http2Proof.java** tại root project:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.time.Duration;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class Http2Proof {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                "Usage: java Http2Proof <ca.crt> <https-url>"
            );
            System.exit(2);
        }

        Certificate ca;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            ca = CertificateFactory.getInstance("X.509")
                .generateCertificate(in);
        }

        KeyStore trust = KeyStore.getInstance("PKCS12");
        trust.load(null, null);
        trust.setCertificateEntry("demo-ca", ca);

        TrustManagerFactory tmf =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        tmf.init(trust);

        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(null, tmf.getTrustManagers(), new SecureRandom());

        HttpClient client = HttpClient.newBuilder()
            .sslContext(ssl)
            .version(HttpClient.Version.HTTP_2)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

        HttpRequest request = HttpRequest.newBuilder(
            URI.create(args[1])
        ).timeout(Duration.ofSeconds(10)).GET().build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("status=" + response.statusCode());
        System.out.println("version=" + response.version());
        System.out.println("body=" + response.body());

        if (response.statusCode() != 200
                || response.version() != HttpClient.Version.HTTP_2
                || !"secure-ok".equals(response.body())) {
            throw new IllegalStateException(
                "Verified TLS HTTP/2 request failed"
            );
        }
    }
}
~~~

Biên dịch/chạy Java 17:

~~~bash
javac Http2Proof.java
java Http2Proof tls/ca.crt \
  https://localhost:8443/api/hello
~~~

Expected stdout khi lab vận hành đúng:

~~~text
status=200
version=HTTP_2
body=secure-ok
~~~

Chương trình dùng **CertificateFactory X.509**, một KeyStore chỉ chứa CA thử nghiệm, **TrustManagerFactory** và **SSLContext** riêng. **Không** tạo trust-all TrustManager, không tắt hostname verification; JDK HttpClient mặc định kiểm hostname cho HTTPS. Nếu CA/hostname sai, phải nhận SSLHandshakeException hoặc validation failure, không tự bypass.

Nếu response version là **HTTP_1_1**, chương trình sẽ fail mặc dù HTTP 200; như vậy yêu cầu kiểm HTTP/2 không bị đánh tráo bằng kết quả HTTP/1.1 qua TLS.

## 13. Integration test @SpringBootTest(RANDOM_PORT) cho HTTP/2 thật

Tạo file **src/test/java/com/example/httpsdemo/HttpsHttp2Test.java**:

~~~java
package com.example.httpsdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.time.Duration;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class HttpsHttp2Test {

    @LocalServerPort
    int port;

    @Test
    void negotiatesVerifiedH2OverRealTomcat() throws Exception {
        Certificate ca;
        try (InputStream in = Files.newInputStream(
                Path.of("tls/ca.crt"))) {
            ca = CertificateFactory.getInstance("X.509")
                .generateCertificate(in);
        }

        KeyStore trust = KeyStore.getInstance("PKCS12");
        trust.load(null, null);
        trust.setCertificateEntry("demo-ca", ca);

        TrustManagerFactory tmf =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        tmf.init(trust);

        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(null, tmf.getTrustManagers(), new SecureRandom());

        HttpClient client = HttpClient.newBuilder()
            .sslContext(ssl)
            .version(HttpClient.Version.HTTP_2)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

        HttpRequest request = HttpRequest.newBuilder(
            URI.create("https://localhost:" + port + "/api/hello")
        ).timeout(Duration.ofSeconds(10)).GET().build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, response.statusCode());
        assertEquals(HttpClient.Version.HTTP_2, response.version());
        assertEquals("secure-ok", response.body());
    }
}
~~~

**Đây là integration test thật**: Spring Boot khởi động embedded Tomcat HTTPS trên random port, load PEM bundle từ files, Java client xác thực CA/hostname rồi kiểm ALPN HTTP/2 response và body.

**MockMvc không đủ** cho mục tiêu này vì MockMvc không chạy HTTP connector network/TLS/ALPN thật. Chỉ unit-test Controller không chứng minh HTTPS.

**Tiền đề của test:** tệp **tls/ca.crt**, **tls/server.crt**, **tls/server-pkcs8.key** đã được tạo trước khi chạy Maven, và working directory là root project. Trong CI, tạo chứng chỉ ephemeral trong test setup; không commit private keys. Nếu CI khác working directory, override absolute file URIs và đường dẫn CA tương ứng.

## 14. Phương án thay thế: JKS/PKCS12 SSL bundle

Một hệ thống enterprise có thể cung cấp **PKCS12** chứa certificate chain và private key thay vì PEM. Tạo .p12 cho lab:

~~~bash
openssl pkcs12 -export \
  -in tls/server.crt \
  -inkey tls/server-pkcs8.key \
  -certfile tls/ca.crt \
  -name demo-server \
  -out tls/server.p12 \
  -passout pass:changeit
~~~

**Thay thế hoàn toàn** nhánh PEM của application.yml bằng cấu hình JKS/PKCS12:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        web:
          key:
            alias: demo-server
          keystore:
            location: "file:./tls/server.p12"
            password: "changeit"
            type: PKCS12

server:
  port: 8443
  ssl:
    bundle: web
  http2:
    enabled: true
~~~

Đây là một **biến thể hoàn chỉnh thay cho PEM**, không phải block thêm vào cùng lúc. Password **changeit** chỉ dùng lab; production phải truyền qua secret-management, không commit plaintext. **.p12 có private key**, không coi nó là file public như .crt.

Kiểm nội dung:

~~~bash
keytool -list -v \
  -keystore tls/server.p12 \
  -storetype PKCS12 \
  -storepass changeit
~~~

Kiểm alias **demo-server**, chain/expiry/SAN. Nếu alias/password sai, Boot có thể không lấy được private key và web server fail startup.

## 15. Docker image non-root, không bake private key

Tạo **Dockerfile**:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
COPY target/https-h2-lab-1.0.0.jar /app/app.jar
USER 10001:10001
EXPOSE 8443
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Không COPY tls/** vào image: private CA/server key phải nằm ngoài artifact. Khi deploy, mount key/cert read-only ở **/etc/tls** và đặt environment paths tương ứng. **USER 10001:10001** tránh chạy Java bằng root; process phải có quyền đọc file key và một writable temp directory cho Tomcat/JDK.

Build:

~~~bash
mvn package
docker build -t https-h2-lab:1.0.0 .
~~~

Với Docker local, có thể mount một thư mục **docker-tls** chỉ chứa server.crt/server-pkcs8.key (không chứa ca.key), đã cấp quyền đọc cho UID 10001:

~~~bash
docker run --rm --name https-h2-lab \
  -p 127.0.0.1:8443:8443 \
  -v "$(pwd)/docker-tls:/etc/tls:ro" \
  -e TLS_CERT_LOCATION="file:/etc/tls/server.crt" \
  -e TLS_KEY_LOCATION="file:/etc/tls/server-pkcs8.key" \
  https-h2-lab:1.0.0
~~~

**Điểm permission dễ lỗi:** file host chmod 0600 thuộc UID của developer có thể **không đọc được bởi container UID 10001**. Cần chuẩn bị mount ownership/group ACL thích hợp, không chạy root hoặc chmod 777 private key. Trong Kubernetes, dùng Secret volume và fsGroup theo policy.

Nếu bật Docker **--read-only**, cần cung cấp **--tmpfs /tmp** hoặc volume writable cho Tomcat/JDK; SSL cert mount vẫn phải **:ro**.

## 16. Kubernetes TLS Secret và HTTPS health probes

Với kind cluster trong lab:
1. Build Docker image.
2. Load image vào kind.
3. Tạo Secret loại **kubernetes.io/tls** với tls.crt/tls.key.
4. Deploy các Pod chạy UID 10001, rootfs read-only, key mount read-only, scratch emptyDir.
5. Port-forward service 8443 và dùng curl/Java client xác minh h2.

~~~bash
docker build -t https-h2-lab:1.0.0 .
kind load docker-image https-h2-lab:1.0.0

kubectl create secret tls https-h2-local-tls \
  --cert=tls/server.crt \
  --key=tls/server-pkcs8.key
~~~

Kubernetes Secret **không phải CA key store**. Không bao giờ đưa **ca.key** vào Pod. Secret nên có namespace/RBAC và encryption-at-rest theo policy; mặc định Kubernetes Secret không thay thế KMS/PKI hoàn chỉnh.

Tạo **k8s.yaml**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: https-h2-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: https-h2-lab
  template:
    metadata:
      labels:
        app: https-h2-lab
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: web
          image: https-h2-lab:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: https
              containerPort: 8443
          env:
            - name: TLS_CERT_LOCATION
              value: "file:/etc/tls/tls.crt"
            - name: TLS_KEY_LOCATION
              value: "file:/etc/tls/tls.key"
            - name: JAVA_TOOL_OPTIONS
              value: "-Djava.io.tmpdir=/tmp"
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tls-keypair
              mountPath: /etc/tls
              readOnly: true
            - name: scratch
              mountPath: /tmp
          startupProbe:
            httpGet:
              scheme: HTTPS
              path: /livez
              port: https
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              scheme: HTTPS
              path: /readyz
              port: https
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              scheme: HTTPS
              path: /livez
              port: https
            periodSeconds: 10
            timeoutSeconds: 2
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
      volumes:
        - name: tls-keypair
          secret:
            secretName: https-h2-local-tls
            defaultMode: 0440
        - name: scratch
          emptyDir:
            sizeLimit: 64Mi
---
apiVersion: v1
kind: Service
metadata:
  name: https-h2-lab
spec:
  type: ClusterIP
  selector:
    app: https-h2-lab
  ports:
    - name: https
      port: 8443
      targetPort: https
~~~

**Lý do manifest này phù hợp mục tiêu:**
- TLS key nằm ở **Secret read-only mount**, không nằm trong Docker image.
- **runAsNonRoot, UID/GID/fsGroup** giảm đặc quyền; kiểm quyền đọc tls.key trong Pod thật, vì Secret volume group/mode behavior có thể bị ảnh hưởng bởi policy/driver.
- **readOnlyRootFilesystem=true** kết hợp **emptyDir /tmp** cho Tomcat/JDK scratch.
- **HTTPS startup/liveness/readiness** trên chính port 8443, không dùng HTTP probe vào HTTPS port.
- **Service ClusterIP** chỉ định tuyến TCP, không tự terminate TLS.
- **replicas=2** là ví dụ; zero-downtime rollout cần rolling strategy và capacity đủ, không được suy ra chỉ từ số replicas.

**Cảnh báo rất quan trọng:** kubelet **HTTPS httpGet probes không thực hiện certificate verification**. Readiness 200 chứng minh ứng dụng đáp ứng health probe, **không** chứng minh CA/SAN hợp lệ và **không** chứng minh ALPN h2. Vẫn phải dùng curl --cacert, openssl -verify_return_error hoặc Java trust CA.

Apply/check:

~~~bash
kubectl apply -f k8s.yaml
kubectl rollout status deployment/https-h2-lab
kubectl get pods -l app=https-h2-lab
kubectl logs deployment/https-h2-lab
kubectl port-forward service/https-h2-lab 8443:8443
~~~

Trong terminal khác:

~~~bash
curl -sS --http2 --cacert tls/ca.crt \
  -o /dev/null \
  -w 'http_version=%{http_version} http_code=%{http_code}\n' \
  https://localhost:8443/api/hello

java Http2Proof tls/ca.crt \
  https://localhost:8443/api/hello
~~~

Port-forward chuyển TCP nên TLS vẫn được terminate ở Tomcat. Nếu cần kiểm qua public Ingress, đặt thêm phép đo ở edge và backend; không tự giả định cả hai hops chạy h2.

## 17. Certificate rotation và SSL bundle reload

Spring Boot 3.3 có tính năng **reload-on-update** cho PEM SSL bundles khi file thay đổi, với các consumers tương thích gồm **Tomcat** và **Netty web server** theo tài liệu. Ví dụ cấu hình tùy chọn:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        web:
          reload-on-update: true
          keystore:
            certificate: "file:/etc/tls/tls.crt"
            private-key: "file:/etc/tls/tls.key"
~~~

Đây là **fragment**, không phải application.yml hoàn chỉnh; còn cần server.ssl.bundle, port và HTTP2 config.

Không coi **Secret thay đổi** là đủ bảo đảm certificate mới được phục vụ:
- Projected Kubernetes Secret volumes thường cập nhật bằng atomic symlink replacement; file watcher phải tương thích cơ chế mount thực tế.
- **subPath mounts** không tự nhận Secret updates như projected Secret volume thông thường.
- Certificate và key phải được thay đồng bộ, không để mismatch trong lúc reload.
- Một số consumers chưa hỗ trợ reload; Tomcat/Netty support phải kiểm theo phiên bản.
- Existing TLS connections có thể vẫn sử dụng certificate/session cũ; cần mở **fresh TLS handshake** khi chứng minh rotation.
- **Rolling restart** theo Secret version là phương án dễ đo, nhưng cần replicas, readiness, grace period và drain.

Có thể kiểm fingerprint cert trước/sau bằng OpenSSL trong một test script có kiểm certificate chain/SNI, không đưa private key vào logs. Theo dõi certificate **notAfter** và cảnh báo trước khi hết hạn.

## 18. SNI, mTLS và truststore: các mở rộng không nên nhầm

**SNI (Server Name Indication)** giúp server chọn certificate theo hostname mà client gửi trong TLS handshake. Spring Boot 3.3 có **server.ssl.server-name-bundles** cho web servers tương thích. Fragment:

~~~yaml
server:
  port: 8443
  ssl:
    bundle: web
    server-name-bundles:
      - server-name: api1.example.test
        bundle: web-api1
      - server-name: api2.example.test
        bundle: web-api2
  http2:
    enabled: true
~~~

Chỉ dùng khi đã có các bundles **web-api1/web-api2** với certificate SAN đúng; không dùng cert localhost cho domain trên. OpenSSL **-servername** cho phép thử lựa chọn SNI.

**mTLS** là TLS có **client certificate authentication**: server cần trust CA của client và policy như **server.ssl.client-auth=need** khi cấu hình tương thích. **mTLS không bắt buộc để dùng h2**. Nếu bật client-auth=need mà curl/Java client không trình certificate/key, handshake có thể fail trước Controller. Đừng nhầm client-auth failure với ALPN h2 issue.

**HTTPS chỉ xác thực server** trong lab; nó **không tự đăng nhập người dùng hoặc kiểm authorization**. API production vẫn cần Spring Security/session/OAuth2/JWT theo mô hình.

## 19. HTTP/2 qua Ingress, proxy và h2c

Ví dụ public browser thấy HTTP/2:

~~~text
Browser -- h2/TLS --> nginx/Ingress -- HTTP/1.1 --> Tomcat
~~~

Không phải lỗi nếu kiến trúc chủ đích terminate h2 tại ingress. Khi đó Servlet **request.getProtocol()** có thể trả **HTTP/1.1**. Để chứng minh Tomcat cũng dùng h2, phải thiết kế proxy upstream h2/h2c hoặc TLS passthrough/re-encryption theo khả năng của gateway và kiểm hop backend thật.

Một kiến trúc khác:

~~~text
Client -- TLS/h2 --> Ingress -- h2c/TCP --> Tomcat h2c
~~~

Ở hop ingress→Tomcat, **h2c không được mã hóa**, nên chỉ dùng trong mạng tin cậy/policy thích hợp; đừng mô tả nó là “TLS end-to-end”. Spring Boot 3.3 hỗ trợ h2c khi server SSL tắt và HTTP2 bật, nhưng ingress phải được cấu hình h2c upstream tương ứng.

**Forwarded headers:** khi proxy terminate TLS, ứng dụng có thể thấy scheme http và tạo redirect/cookie sai nếu không cấu hình forwarding đúng. Dùng **server.forward-headers-strategy** phù hợp trusted proxy và sanitize X-Forwarded-* tại edge. Không nhận untrusted forwarding headers từ bất kỳ client nào.

Một chain client→CDN→Ingress→Tomcat có thể có nhiều TLS sessions, mỗi session ALPN riêng. Curl tới public domain chỉ xác minh client-facing hop, không suy ra backend.

## 20. Troubleshooting SSL bundle và HTTP/2

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Không tìm được bundle web | Tên server.ssl.bundle sai, profile/env binding | Kiểm spring.ssl.bundle.pem.web và effective config |
| Certificate file not found | Đường dẫn file: sai, mount/Secret thiếu | Kiểm path, UID, kubectl logs |
| Cannot parse private key | PEM PKCS#1/SEC1, encrypted key hoặc file lỗi | Convert PKCS#8, openssl pkey |
| Private key mismatch | Cert và key khác cặp | Xác minh public key bằng OpenSSL |
| SSLHandshakeException PKIX path | Client không tin CA hoặc chain thiếu | curl --cacert, Java truststore |
| Hostname mismatch | SAN không khớp URL/SNI | openssl x509 -ext subjectAltName |
| Certificate expired/not yet valid | Time/certificate lifecycle sai | openssl x509 -dates, NTP |
| Curl -k OK nhưng CA verify fail | Certificate trust/hostname vẫn sai | Không tắt verify, sửa CA/cert |
| HTTPS 200 nhưng HTTP/1.1 | H2 không negotiate, client thiếu HTTP2, proxy | curl -V, ALPN, response.version() |
| s_client ALPN h2 nhưng Java HTTP1.1 | Proxy route/client constraints khác | Gọi direct endpoint, logs và trust config |
| Spring getProtocol() HTTP/1.1 dù browser h2 | Ingress terminate client-facing h2 | Kiểm upstream protocol từng hop |
| HTTP plain vào 8443 lỗi | Sai scheme với TLS port | Sử dụng https:// |
| TLS started nhưng port 8080 đóng | Chỉ có HTTPS connector 8443 | Check server.port và LB routing |
| Kubernetes HTTPS readiness pass, curl verify fail | Probe không verify cert | Dùng CA-aware external tests |
| K8s Pod CrashLoopBackOff | Secret permissions, missing /tmp, key path | Describe/logs, fsGroup, readOnlyRoot |
| Secret updated, old certificate vẫn được trình | File watcher/reload chưa chạy; TLS connections cũ | Fresh handshake, rollout/cert fingerprint |
| Client-auth handshake failure | mTLS bật nhưng client không có cert | Kiểm server.ssl.client-auth và trust CA |
| ALPN không thấy h2 | SSL disabled, Boot setting, proxy, JDK/TLS mismatch | Kiểm enable, s_client, Tomcat version |
| HTTP2 streams reset khi load | Timeouts, stream cap, memory, proxy settings | Metrics, load test có quyền |
| Một hostname lỗi, hostname khác chạy | SNI/SAN/bundle mapping | openssl -servername, SAN đúng |

### 20.1. Runbook 10 bước

1. Ghi URL, port, DNS/SNI và TLS topology của request.
2. Kiểm embedded Tomcat có start được và đọc đúng PEM bundle không.
3. Kiểm certificate chain, SAN, expiry và private key format.
4. Dùng **openssl verify -verify_hostname localhost** với CA demo.
5. Dùng **openssl s_client -servername localhost -alpn h2,http/1.1 -CAfile**.
6. Dùng **curl --http2 --cacert** và kiểm http_version.
7. Dùng **Java Http2Proof** kiểm response.version() và body.
8. Dùng /api/transport hỗ trợ kiểm protocol từ góc nhìn Tomcat.
9. Nếu đi qua LB/Ingress, kiểm protocol/security của từng hop.
10. Sau rotation, so certificate mới qua **fresh handshake** rồi chạy lại integration/regression tests.

**Không sửa lỗi bằng cách cho phép trust-all hoặc SSL disabled ở production.** Đó là thay đổi bảo mật nguy hiểm, không phải fix hợp lệ.

### 20.2. Debug TLS cần giữ bí mật

Có thể bật **-Djavax.net.debug=ssl,handshake** có kiểm soát trên staging để xem TLS handshakes, nhưng logs rất dài và có thông tin cấu trúc deployment/certificate. Không ghi private key, password keystore, Authorization hay Cookie vào logs. Không public Actuator env/heapdump chỉ vì muốn debug.

## 21. Kiểm thử âm và matrix acceptance

| Test | Cách gây tình huống trong lab | Kết quả hợp lý |
| --- | --- | --- |
| Local CA đúng + hostname đúng | curl --cacert ca.crt https://localhost | 200, verified TLS |
| Client không trust CA | Không cung cấp CA demo nếu chưa được trust | TLS validation thất bại |
| Sai SAN | Gọi hostname không nằm trong SAN | Hostname verification fail |
| Cert hết hạn | Dùng test certificate expired được kiểm soát | TLS verification fail |
| Server private key sai | Bundle trỏ key không khớp cert | Startup/reload fail |
| PEM path sai | Trỏ tệp không có | Startup fail, logs có lỗi material |
| HTTP plain trên 8443 | curl http://localhost:8443 | Protocol error/connection close |
| HTTPS HTTP/1.1 | curl --http1.1 --cacert | 200, h1 nếu server cho phép |
| HTTPS HTTP/2 | curl --http2 --cacert | 200, http_version=2 |
| ALPN chỉ offer http/1.1 | s_client -alpn http/1.1 | Không chứng minh h2 |
| Client không có HTTP2 | curl -V thiếu HTTP2 | Không dùng curl đó làm h2 proof |
| Java client fallback | Tắt h2 server trong môi trường test riêng | response.version có thể HTTP_1_1 |
| Public edge h2, upstream h1 | Ingress terminate TLS | Báo đúng mỗi hop |
| Kubernetes readiness HTTPS pass | Kubelet probe | Không phải certificate validation |
| Rotate Secret | New Secret + reload/rolling restart | New handshake trình cert mới |
| TLS disabled khi cần | server.ssl.bundle bị gỡ | Không được coi là success |

Test phải chạy trong môi trường được phép, không thay cert production để “kiểm âm”. Với HTTPS, lỗi TLS xảy ra **trước HTTP**, không kỳ vọng một response 400/401 JSON khi handshake bị từ chối.

## 22. Operational security và performance

Các điều kiện vận hành:
- Certificate phải từ CA được trust, SAN khớp domain, chain đủ, không hết hạn.
- Private key phải lưu ở Secret/KMS/PKI, có access restriction và rotation policy.
- Không đặt CA private key hoặc TLS server key vào image/JAR/Git.
- Sử dụng TLS versions/ciphers theo chuẩn tổ chức; giữ Java/Boot/Tomcat patches hiện hành.
- Tách HTTPS termination architecture với user authentication/authorization.
- Khi external HTTP 80 tồn tại, dùng HTTPS redirect/HSTS phù hợp và kiểm cookie Secure/HttpOnly/SameSite.
- Giám sát TLS handshake failures, ALPN negotiated versions, certificate expiration, 4xx/5xx và client errors.
- HTTP/2 stream limits, header compression, buffer size, request deadlines và Tomcat workers vẫn cần capacity planning.
- Đừng benchmark h2/h1 bằng một request đơn lẻ trên localhost rồi kết luận throughput production.
- Tải cao có thể thấy RST_STREAM/GOAWAY dù TLS đúng; xác minh proxy/HTTP2 SETTINGS, flow-control, timeouts và concurrency.
- Không dùng h2c cleartext ngoài mạng được cấp phép/chính sách mã hóa của tổ chức.
- Test HTTP2 qua real server, không chỉ MockMvc.

**Không tự giả định HTTP/2 luôn nhanh hơn**: so sánh h1 keep-alive với h2 multiplex dưới cùng TLS trust, warm connections, concurrency, response sizes và workload; quan sát p95/p99, CPU/GC/memory và lỗi.

## 23. Câu hỏi ôn tập có đáp án

**1.** server.ssl.bundle=web có tự tạo certificate không?  
**Đáp án:** Không. Nó chọn bundle đã khai báo với key material hợp lệ.

**2.** Namespace PEM bundle trong Spring Boot 3.3 là gì?  
**Đáp án:** spring.ssl.bundle.pem.<name>.

**3.** Bật server.http2.enabled=true có buộc mọi client dùng h2?  
**Đáp án:** Không. Client, ALPN, TLS và proxy có thể chọn HTTP/1.1.

**4.** h2c có phải HTTP/2 qua TLS không?  
**Đáp án:** Không. h2c là HTTP/2 cleartext.

**5.** Java 17 có cần libtcnative để Tomcat 10.1 chạy h2 qua TLS?  
**Đáp án:** Không bắt buộc, Java 17 hỗ trợ ALPN.

**6.** Có bắt buộc dùng TLS 1.3 để có HTTP/2 không?  
**Đáp án:** Không. TLS 1.2 cũng có thể được dùng với requirements phù hợp.

**7.** Tại sao Certificate CN=localhost nhưng thiếu SAN có thể không được trust?  
**Đáp án:** Hostname verification hiện đại dựa vào SAN.

**8.** curl --http2 đủ bằng chứng h2?  
**Đáp án:** Không. Cần http_version=2 hoặc HTTP/2 response thực.

**9.** openssl s_client -alpn h2 kiểm điều gì?  
**Đáp án:** TLS handshake và negotiated ALPN, không tự gửi/nhận HTTP/2 frames.

**10.** Java HttpClient version(HTTP_2) là bảo đảm?  
**Đáp án:** Không. response.version() có thể là HTTP_1_1 khi fallback.

**11.** curl -k trả 200 có chứng minh CA/hostname hợp lệ?  
**Đáp án:** Không, vì bỏ qua verification.

**12.** Vì sao không đưa ca.key vào Kubernetes Pod?  
**Đáp án:** Đó là CA private signing key, không cần để server phục vụ TLS.

**13.** Keystore và truststore khác nhau chỗ nào?  
**Đáp án:** Keystore chứa identity certificate/private key, truststore chứa CA/cert dùng kiểm đối tác.

**14.** HTTPS listener 8443 có tự mở HTTP 8080 để redirect không?  
**Đáp án:** Không. Cần connector/proxy riêng.

**15.** Kubelet HTTPS readiness probe có xác minh CA/SAN không?  
**Đáp án:** Không, HTTPS httpGet probe bỏ qua xác minh chứng chỉ.

**16.** Browser public domain báo h2, backend Java getProtocol() h1 có phải bug?  
**Đáp án:** Không nhất thiết; Ingress có thể terminate h2 và proxy upstream h1.

**17.** Một TLS connection giữa Ingress và Pod có tự dùng cùng ALPN với browser không?  
**Đáp án:** Không, mỗi TLS hop handshake riêng.

**18.** Secret volume được cập nhật có bảo đảm Tomcat đã reload certificate không?  
**Đáp án:** Không. Cần watcher/consumer support hoặc rollout và kiểm new connection.

**19.** mTLS có cần để HTTP/2 chạy không?  
**Đáp án:** Không, mTLS là client certificate authentication.

**20.** Vì sao nên dùng @SpringBootTest(RANDOM_PORT) thay MockMvc để test h2?  
**Đáp án:** Cần Tomcat/TLS/ALPN chạy trên real socket.

**21.** PKCS12 .p12 có chứa private key không?  
**Đáp án:** Có thể có; phải bảo vệ như một secret.

**22.** Bật TLS giúp chống mọi lỗ hổng XSS/CSRF/authorization không?  
**Đáp án:** Không. TLS bảo vệ transport, application security vẫn cần thiết.

## 24. Checklist triển khai

- [ ] Đã xác định đúng TLS termination topology và protocol từng hop.
- [ ] Có certificate chain hợp lệ, SAN đúng URL, còn hạn.
- [ ] Có PKCS#8 PEM hoặc PKCS12 private key khớp certificate.
- [ ] Bundle **spring.ssl.bundle.pem.web** hoặc **jks.web** đã khai báo.
- [ ] **server.ssl.bundle=web** và không trộn discrete SSL key properties.
- [ ] **server.http2.enabled=true** tại HTTPS web server cần kiểm.
- [ ] Port HTTPS 8443 lắng nghe; HTTP plain không bị nhầm port.
- [ ] Local curl dùng **--cacert tls/ca.crt**, không **-k**.
- [ ] OpenSSL ALPN selected **h2**, verification code **0**.
- [ ] curl http_version **2**, HTTP status **200**.
- [ ] Java HttpClient **response.version()==HTTP_2** và body **secure-ok**.
- [ ] JUnit @SpringBootTest(RANDOM_PORT) chứng minh TLS/ALPN thực.
- [ ] Nếu có Ingress, đã kiểm cả public edge và backend hop.
- [ ] Docker image không bake private key, chạy non-root.
- [ ] Kubernetes TLS Secret mount read-only với quyền file hợp lệ.
- [ ] Readonly rootfs có writable temp cho Tomcat nếu cần.
- [ ] Readiness HTTPS không được dùng làm trust/ALPN proof.
- [ ] Có certificate expiry monitoring và rotation test với fresh connections.
- [ ] Có rollback khi cert/reload lỗi, không fallback cleartext.
- [ ] TLS debug không lộ keys, tokens hoặc thông tin nhạy cảm.
- [ ] Đã test lỗi CA, SAN, key mismatch, fallback HTTP1.1 và proxy topology.
- [ ] Đã đối chiếu config với đúng Spring Boot/Tomcat/JDK versions.

## 25. Kết luận

**SSL bundle** giúp tách certificate/private key ra khỏi mã nguồn và gắn key material có tên cho embedded web server Spring Boot. Với **Spring Boot 3.3.13 + Tomcat 10.1 + Java 17**, thiết lập **server.ssl.bundle=web** và **server.http2.enabled=true** cho phép HTTPS negotiate **h2** bằng ALPN. Nhưng một cờ bật tính năng không phải bằng chứng giao thức thực tế.

Hoàn tất bài thực hành khi **CA và SAN/hostname verify thành công**, **ALPN chọn h2**, **curl/Java HttpClient thực sự báo HTTP/2**, **real-port JUnit test pass**, và deployment đọc key từ external Secret mà không công bố private key. Nếu có Ingress, báo rõ protocol theo từng hop; nếu có rotation, kiểm bằng fresh TLS handshake.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 — SSL bundles, PEM/JKS and reload-on-update: https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
- Spring Boot 3.3.13 — Embedded Web Servers, SSL bundles and HTTP/2 over h2/h2c: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3.13 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Actuator Kubernetes readiness/liveness: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Apache Tomcat 10.1 — HTTP Connector/TLS/HTTP2: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
- Oracle Java 17 — HttpClient protocol selection: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java 17 — HttpResponse.version: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- OpenSSL — s_client, verification and ALPN: https://docs.openssl.org/3.0/man1/openssl-s_client/
- OpenSSL — x509 and certificate verification: https://docs.openssl.org/3.0/man1/openssl-x509/
- curl — --http2, --cacert and --write-out: https://curl.se/docs/manpage.html
- Kubernetes — Secrets and TLS keys: https://kubernetes.io/docs/concepts/configuration/secret/
- Kubernetes — HTTPS probes skip certificate verification: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- Kubernetes — Security context and runAsNonRoot: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- RFC 9113 — HTTP/2: https://www.rfc-editor.org/rfc/rfc9113
- RFC 7301 — TLS Application-Layer Protocol Negotiation: https://www.rfc-editor.org/rfc/rfc7301
