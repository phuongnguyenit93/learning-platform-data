# Dùng chứng thư PEM và áp dụng bundle cho máy chủ nhúng

> **Ngữ cảnh:** Spring Boot web-runtime → TLS và HTTP/2. Bài học dựa trên **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+** và tập trung vào cách dùng **chứng thư PEM (PEM-encoded X.509 certificate)** cùng private key để tạo **SSL bundle** rồi áp dụng cho máy chủ HTTP nhúng (Tomcat hoặc Reactor Netty; các container khác được phân biệt ở những chỗ có giới hạn). Ví dụ có thể chạy với Maven, OpenSSL và curl. Chứng thư tự ký trong lab chỉ dùng cho máy phát triển.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt **TLS**, **HTTPS**, **X.509 certificate**, **private key**, **CA/trust chain**, **PEM**, **PKCS#8**, **JKS/PKCS#12** và **SSL bundle**; không dùng lẫn các tên này.
2. Tạo một cặp private key/certificate PEM dành cho localhost, có **Subject Alternative Name (SAN)** phù hợp; phân biệt tự ký cho lab với chứng thư CA ký dùng trong production.
3. Cấu hình chính xác `spring.ssl.bundle.pem.<tên>.keystore.certificate`, `spring.ssl.bundle.pem.<tên>.keystore.private-key` và `server.ssl.bundle` để bật HTTPS trên máy chủ nhúng.
4. Chạy Spring Boot MVC + Tomcat bằng Java 17; xác minh certificate, hostname, trust, kết nối HTTPS bằng curl và OpenSSL thay vì chỉ dùng `-k`.
5. Hiểu cách dùng cùng cấu hình SSL bundle khi thay Spring MVC/Tomcat bằng Spring WebFlux/Reactor Netty, và bật **HTTP/2 over TLS** bằng `server.http2.enabled`.
6. Đưa private key ra khỏi JAR trong production; vận hành certificate chain, quyền truy cập, cấp phát certificate, xoay vòng chứng thư và **reload-on-update** ở các container được hỗ trợ.
7. Xác định đúng nguyên nhân các lỗi TLS điển hình: file sai, key không khớp, hostname mismatch, chứng thư hết hạn, thiếu intermediate, client không tin CA, cấu hình bundle sai, xung đột các property cũ và lỗi ALPN/HTTP2.

## 2. TLS hoạt động ở đâu trong Spring Boot?

HTTP là giao thức request/response. **HTTPS** là HTTP được vận chuyển qua một kết nối được bảo vệ bởi **TLS**. TLS giải quyết ba nhu cầu quan trọng:

- **Authentication:** client có thể kiểm chứng server sở hữu private key tương ứng certificate và certificate được tin cậy theo trust policy.
- **Confidentiality:** dữ liệu được mã hóa khi truyền qua kết nối; người đứng giữa không dễ đọc nội dung.
- **Integrity:** dữ liệu trao đổi được bảo vệ khỏi sửa đổi trái phép trên đường truyền theo các bảo đảm của giao thức.

TLS handshake diễn ra **trước** khi request đi vào controller của Spring. Máy chủ nhúng (Tomcat/Jetty/Undertow hoặc Reactor Netty tùy ứng dụng) tạo SSL/TLS engine, chọn certificate tương ứng, hoàn tất handshake rồi mới trao đổi HTTP.

~~~text
Client / browser / curl
    |
    |  TCP connect
    v
Embedded HTTP server :8443
    |
    |  TLS handshake:
    |    - ClientHello, SNI, ALPN, TLS versions/ciphers
    |    - server certificate chain
    |    - certificate validation + key agreement
    v
Encrypted TLS connection
    |
    |  HTTP/1.1 hoặc HTTP/2 request
    v
Spring MVC DispatcherServlet / WebFlux DispatcherHandler
    |
    v
Controller -> Service -> Response
~~~

**Một controller trả `200 OK` không chứng minh cấu hình TLS an toàn.** Có thể client đã bỏ qua kiểm tra certificate; hoặc TLS được terminate ở proxy thay vì tại Spring Boot. Phải xác định **điểm kết thúc TLS (TLS termination)** thực sự nằm ở đâu.

### Embedded server nào?

| Web stack | Starter phổ biến | Máy chủ nhúng mặc định | Điểm cần nhớ |
|---|---|---|---|
| Spring MVC (Servlet) | `spring-boot-starter-web` | Tomcat | Sử dụng `server.ssl.bundle` để cấu hình HTTPS connector. |
| Spring WebFlux (Reactive) | `spring-boot-starter-webflux` | Reactor Netty | Cũng dùng `server.ssl.bundle`; không phải tự tạo Netty `SslContext` chỉ để bật HTTPS. |
| MVC/WebFlux thay container | Jetty hoặc Undertow khi được cấu hình | Tùy dependency | Hỗ trợ TLS cơ bản, nhưng tính năng hot-reload/SNI/HTTP2 có khác biệt. |

Đừng mặc định thấy WebFlux dependency nghĩa là app chạy Reactor Netty: khi có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên ứng dụng Servlet/MVC. Kiểm tra actual web application type và server trong startup logs trước khi chẩn đoán TLS.

## 3. Certificate, private key, trust: ba vai trò khác nhau

### Server certificate và private key

**Certificate X.509** thường chứa public key, tên chủ thể, SAN, issuer, thời hạn, thuật toán ký và phần chữ ký của CA. Nó có thể phân phối công khai cho client trong TLS handshake.

**Private key** là bí mật của server. Nó tương ứng public key trong certificate và được dùng trong cơ chế xác thực TLS. Private key không được gửi cho client và không nên có mặt trong mã nguồn, git, image công khai hoặc application logs.

~~~text
Server identity:
  server.crt / fullchain.pem       [certificate hoặc certificate chain]
  server.key / privkey.pem         [private key tương ứng]

Client checks:
  certificate SAN matches requested host?
  certificate still valid?
  issuer chain trusted by client?
  signature and protocol requirements valid?
  server proves possession of corresponding key?
~~~

Nếu private key không khớp certificate, TLS server không thể cấu hình chính xác hoặc bắt tay thành công. Nếu certificate hợp lệ nhưng SAN không chứa hostname client truy cập, client đúng chuẩn sẽ từ chối hostname verification.

### CA, truststore và certificate chain

**CA (Certificate Authority)** ký certificate. Với chứng thư production, server thường trình bày certificate leaf của chính nó cộng các **intermediate certificates** cần thiết; client kiểm tra chuỗi tới một trust anchor mà client đã tin cậy. Tệp như `fullchain.pem` thường chứa leaf đứng trước intermediate(s). Không nên nhầm certificate chain phục vụ client với private key hay CA root bí mật.

**Truststore** là dữ liệu mà một bên sử dụng để **tin các chứng thư của đối tác**:

- Trong HTTPS thông thường, **server** có certificate và private key; **client** kiểm tra server qua trust roots. Server **không cần** truststore của CA client nếu không yêu cầu client certificate.
- Khi bật **mutual TLS (mTLS)**, server còn xác thực certificate của client, nên server cần cấu hình CA/certificate trust phù hợp để kiểm tra client. Client cũng phải có identity certificate/private key riêng.
- SSL bundle có thể mang cả identity material và trust material, nhưng **hai loại material phục vụ hai mục đích khác nhau**.

### PEM và PKCS#8

**PEM** mô tả cách mã hóa dữ liệu nhị phân (certificate, private key...) dưới dạng text Base64 có các dòng BEGIN/END. Một certificate thường bắt đầu bằng `-----BEGIN CERTIFICATE-----`. Một private key **PKCS#8** thường bắt đầu bằng `-----BEGIN PRIVATE KEY-----` hoặc `-----BEGIN ENCRYPTED PRIVATE KEY-----`.

Spring Boot khuyến nghị dùng private key PEM định dạng **PKCS#8** khi có thể. Một số key cũ theo PKCS#1 (RSA) hoặc SEC 1 (EC) có header khác và nên chuyển định dạng khi cần. PEM không phải một dạng certificate authority, và một file có đuôi `.pem` không tự đảm bảo chứa nội dung hợp lệ hay đúng loại.

### PEM so với Java KeyStore

| Khái niệm | PEM | JKS / PKCS#12 |
|---|---|---|
| Cách chứa | Các đoạn text certificate/key, thường tách file | Container keystore dạng nhị phân, có thể chứa key/cert/trust |
| Thường gặp | Kubernetes Secrets, Certbot/ACME, reverse proxy, container deployments | Java keystores, ứng dụng Java truyền thống |
| Spring Boot bundle | `spring.ssl.bundle.pem.*` | `spring.ssl.bundle.jks.*` |
| Áp dụng cho server nhúng | `server.ssl.bundle=<name>` | Cũng `server.ssl.bundle=<name>` |
| Điểm cần bảo vệ | Private key và quyền đọc file hoặc secret | Keystore và password/key material |
| Chuyển đổi | Không bắt buộc qua PKCS#12 khi dùng PEM bundle | Có thể dùng `keytool`/OpenSSL tùy nhu cầu |

**Không cần chuyển tất cả PEM certificate thành `.p12`** để bật HTTPS trong Spring Boot 3.3: PEM SSL bundles được hỗ trợ trực tiếp.

## 4. SSL bundle giải quyết vấn đề gì?

Từ Spring Boot 3.1, **SSL bundle** là một cấu hình được **đặt tên** gom những thông tin dùng để thiết lập TLS: server identity material (certificate/private key) hoặc client-side trust material, cùng các tùy chọn khi cần. Thay vì rải nhiều `server.ssl.key-store`, password và certificate property, bạn định nghĩa bundle dưới `spring.ssl.bundle.*` rồi **tham chiếu bằng tên** ở thành phần cần dùng.

Ví dụ ý tưởng:

~~~text
spring.ssl.bundle.pem.webserver  --> [certificate + private key]
                                     |
                                     v
server.ssl.bundle=webserver     --> Embedded Tomcat / Reactor Netty
                                     |
                                     v
HTTPS :8443
~~~

Tên `webserver` là **do người dùng đặt**, không phải magic keyword. Nếu định nghĩa `spring.ssl.bundle.pem.frontend.*` nhưng chọn `server.ssl.bundle=webserver`, Boot không tìm được bundle phù hợp. Nên dùng tên ngắn, dễ phân biệt server/client và nhất quán khi deploy.

### Các lớp cấu hình

| Phần | Ý nghĩa |
|---|---|
| `spring.ssl.bundle.pem.<name>.keystore.certificate` | Resource chứa server certificate hoặc chain ở PEM. |
| `spring.ssl.bundle.pem.<name>.keystore.private-key` | Resource chứa private key PEM khớp với certificate. |
| `spring.ssl.bundle.pem.<name>.truststore.certificate` | CA/certificate tin cậy (hữu ích với client-side TLS hoặc mTLS), không thay identity key. |
| `server.ssl.bundle` | Chỉ ra bundle được áp dụng cho **máy chủ HTTP nhúng**. |
| `server.port` | Cổng listener của server, ví dụ 8443. |
| `spring.ssl.bundle.pem.<name>.reload-on-update` | Theo dõi file material để reload với server hỗ trợ (Tomcat/Netty trong Boot 3.3). |
| `server.http2.enabled` | Bật HTTP/2; nếu HTTPS thì đàm phán h2 qua TLS/ALPN khi container/client hỗ trợ. |

Các property `spring.ssl.bundle.pem...` **chỉ định nghĩa bundle**. Chúng **không** khiến embedded server sử dụng bundle nếu chưa đặt `server.ssl.bundle` hoặc chưa có một consumer khác tham chiếu tên đó.

## 5. Lab: tạo certificate PEM dùng cho localhost

Lab dùng OpenSSL 1.1.1 hoặc 3.x có hỗ trợ `-addext`, Maven 3.x và Java 17+. Thực hiện trong một thư mục dự án test mới. **Không dùng certificate/key tự ký này cho production**.

### 5.1. Thư mục mẫu

~~~text
pem-ssl-demo/
  pom.xml
  src/
    main/
      java/
        example/
          pemserver/
            PemServerApplication.java
      resources/
        application.properties
        tls/
          localhost.crt
          localhost.key
~~~

Tạo sẵn `src/main/resources/tls/` trước khi chạy OpenSSL.

### 5.2. Sinh PKCS#8 RSA private key

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out src/main/resources/tls/localhost.key
~~~

`openssl genpkey` tạo private key PEM theo mã hóa PKCS#8, thường có header `BEGIN PRIVATE KEY`. Dùng RSA 2048 ở đây cho tương thích môi trường lab; production phải theo security policy hiện hành và vòng đời khóa của tổ chức. **Bảo vệ file private key**: trên Linux/macOS có thể đặt quyền đọc của owner bằng `chmod 600 src/main/resources/tls/localhost.key`. Trên Windows, dùng ACL/secret store thích hợp.

### 5.3. Tạo certificate tự ký có SAN

~~~bash
openssl req -new -x509 -sha256 -days 7 -key src/main/resources/tls/localhost.key -out src/main/resources/tls/localhost.crt -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
~~~

Lệnh tạo certificate self-signed có thời hạn **7 ngày kể từ lúc tạo**; SAN liệt kê cả DNS localhost và IP 127.0.0.1, nên có thể kiểm tra hai URL tương ứng. Số ngày và host ở đây chỉ phục vụ lab. Certificate **tự ký không được trình duyệt/curl tin cậy mặc định**, nên sẽ dùng `--cacert` khi thử nghiệm.

Đây **không phải** chứng thư được một CA công khai cấp. Một certificate tự ký có thể được client tin riêng khi cấu hình trust anchor, nhưng đừng lẫn việc “bắt tay thành công khi bỏ xác thực” với “chuỗi certificate đáng tin cậy”.

### 5.4. Kiểm tra PEM trước khi cấu hình Boot

~~~bash
openssl pkey -in src/main/resources/tls/localhost.key -check -noout
openssl x509 -in src/main/resources/tls/localhost.crt -noout -subject -issuer -dates -ext subjectAltName
~~~

Kỳ vọng các lệnh hoàn tất không lỗi; output certificate có subject liên quan `CN=localhost`, SAN `DNS:localhost`, `IP Address:127.0.0.1` và thời gian hiệu lực thực. Vì serial, thời điểm tạo và OpenSSL version khác nhau, **không có một stdout cố định toàn bộ**.

Kiểm tra public key được rút từ certificate và private key có tương ứng nhau bằng cách so SHA-256 của public-key DER:

~~~bash
openssl x509 -in src/main/resources/tls/localhost.crt -pubkey -noout | openssl pkey -pubin -outform DER | openssl dgst -sha256
openssl pkey -in src/main/resources/tls/localhost.key -pubout -outform DER | openssl dgst -sha256
~~~

Hai kết quả digest nên **bằng nhau**. Cách kiểm này không phụ thuộc thao tác tính RSA modulus (vốn không áp dụng cho mọi key algorithm). Nó kiểm tra public key match, **không thay thế** việc kiểm tra certificate chain, SAN và trust policy.

**Lưu ý bảo mật:** file key được để dưới `src/main/resources` chỉ để demo chạy độc lập; build JAR sẽ nhúng nó vào archive. Vì thế đừng commit file này lên git, phát tán JAR test hoặc xem nó là thiết kế triển khai production. Phần production phía dưới sẽ chuyển sang file mount ngoài artifact.

## 6. Dự án Spring Boot MVC + Tomcat có thể chạy

Dự án này dùng đúng **Spring Boot 3.3.13** và Java 17. Một phần khác của dòng 3.3 có thể được dùng nếu BOM/plugin tương thích. Chúng ta dùng Maven để người học có đầy đủ cấu hình thay vì yêu cầu một Gradle build đã tồn tại.

### 6.1. File pom.xml đầy đủ

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

    <groupId>example</groupId>
    <artifactId>pem-ssl-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>pem-ssl-demo</name>

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

`spring-boot-starter-web` tự đưa Tomcat vào trong cấu hình mặc định; **không cần** tạo WAR hoặc tự đăng ký Servlet connector chỉ để bật HTTPS trên một cổng.

### 6.2. File Java đầy đủ

Tạo `src/main/java/example/pemserver/PemServerApplication.java`:

~~~java
package example.pemserver;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PemServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(PemServerApplication.class, args);
    }

    @RestController
    static class HelloController {

        @GetMapping("/hello")
        public String hello() {
            return "TLS OK";
        }

        @GetMapping("/api/status")
        public ResponseEntity<Map<String, String>> status() {
            return ResponseEntity.ok(Map.of(
                    "service", "pem-ssl-demo",
                    "status", "ready"
            ));
        }
    }
}
~~~

Đây là một Java application class **đầy đủ** trong package `example.pemserver`, có nested `@RestController` được component scan phát hiện. `/hello` trả text `TLS OK`; `/api/status` trả JSON gồm hai key (thứ tự key trong JSON không được bảo đảm). Controller không biết private key, không gọi `SSLContext` thủ công; embedded server được Boot cấu hình trước khi request đến handler.

### 6.3. File application.properties đầy đủ

Tạo `src/main/resources/application.properties`:

~~~properties
# HTTPS listener của embedded web server
server.port=8443

# Định nghĩa bundle tên "webserver" từ PEM resources
spring.ssl.bundle.pem.webserver.keystore.certificate=classpath:tls/localhost.crt
spring.ssl.bundle.pem.webserver.keystore.private-key=classpath:tls/localhost.key

# Bắt embedded server áp dụng đúng bundle đã định nghĩa
server.ssl.bundle=webserver
~~~

Đây là **lõi của bài học**:

- `spring.ssl.bundle.pem.webserver...` = **khai báo bundle**.
- `server.ssl.bundle=webserver` = **áp dụng bundle cho HTTP server nhúng**.
- `server.port=8443` = cổng HTTPS mà bạn sẽ gọi.

Cả certificate và private key nằm trong classpath của JAR, nên đường resource trong demo bắt đầu bằng `classpath:tls/`. Tên property **khác** kiểu cũ `server.ssl.certificate-private-key`: trong bundle, thuộc tính PEM là `keystore.private-key`.

Không cần tự khai báo `server.ssl.enabled=true` cho demo khi `server.ssl.bundle` đã được cấu hình phù hợp; đừng dùng `server.ssl.enabled=false` rồi kỳ vọng HTTPS vẫn chạy.

### 6.4. Chạy ứng dụng và thử HTTPS

Từ gốc dự án, sau khi tạo files:

~~~bash
mvn spring-boot:run
~~~

Hoặc build executable JAR rồi chạy:

~~~bash
mvn clean package
java -jar target/pem-ssl-demo-0.0.1-SNAPSHOT.jar
~~~

Hai lựa chọn yêu cầu Maven/Java 17 đã cài và port 8443 chưa bị chiếm. Nếu server khởi động thành công, nó lắng nghe HTTPS trên port 8443. **Không phải** đồng thời mở HTTP plaintext port 8080 chỉ vì trước đây Spring Boot default dùng 8080.

Dùng curl và tin certificate tự ký **có chủ đích**:

~~~bash
curl --cacert src/main/resources/tls/localhost.crt -i https://localhost:8443/hello
curl --cacert src/main/resources/tls/localhost.crt -i https://127.0.0.1:8443/api/status
~~~

Kỳ vọng request thứ nhất có HTTP 200 và body đúng `TLS OK`. Request thứ hai có JSON gồm `service=pem-ssl-demo`, `status=ready`. Certificate chứa SAN cho cả localhost và 127.0.0.1 nên hostname validation có thể thành công nếu client tin đúng certificate, hiệu lực chưa hết và TLS stack chấp nhận thuật toán.

**Không dùng `curl -k` hoặc `--insecure` làm bước nghiệm thu:** chúng bỏ qua verification certificate/hostname. `-k` có thể hữu ích để tách nhanh lỗi trust khỏi lỗi transport trong môi trường lab, nhưng một kết nối thành công nhờ bỏ verification **không chứng minh server identity được xác thực**.

### 6.5. Kiểm tra HTTP plaintext bị từ chối

~~~bash
curl -v http://localhost:8443/hello
~~~

Đây là HTTP không mã hóa gửi tới cổng HTTPS; bạn nên thấy request không hoạt động đúng, ví dụ bị từ chối hoặc nhận phản hồi lỗi tùy connector, **không** nhận response HTTPS hợp lệ. Đừng xem mọi dạng lỗi từ curl là cùng một exception ổn định giữa các server versions.

Nếu gọi `http://localhost:8080/hello` khi chỉ có cấu hình trên, mặc định port 8080 không còn được Boot tạo như listener HTTP thứ hai. Spring Boot 3.3 **không** có một cấu hình application.properties duy nhất để đồng thời sinh một HTTP connector và một HTTPS connector cho cùng server; muốn cả hai phải cấu hình connector bổ sung bằng code/container hoặc dùng reverse proxy.

## 7. Kiểm tra riêng certificate và TLS handshake

Dùng OpenSSL kiểm tra kết nối tới embedded server:

~~~bash
openssl s_client -connect localhost:8443 -servername localhost -CAfile src/main/resources/tls/localhost.crt -verify_hostname localhost
~~~

Một handshake hợp lệ trong lab sẽ cho thông tin chain, phiên bản TLS, cipher và kết quả verify tương ứng; thường có `Verify return code: 0 (ok)` khi certificate được client tin và hostname đúng. Output thay đổi tùy OpenSSL/JDK/cipher, nên **không có transcript cố định** để sao chép. Có thể thêm `-verify_return_error` khi muốn OpenSSL dừng nếu verification thất bại.

Để biết chính xác server đang trình bày certificate nào:

~~~bash
openssl s_client -connect localhost:8443 -servername localhost -showcerts
~~~

Kiểm tra subject, SAN, thời hạn và chain. Nếu có nhiều certificate cho nhiều hostname thông qua SNI, `-servername` quan trọng để xác định bundle/certificate được chọn. Nếu bỏ SNI, server có thể trả default certificate thay vì certificate cho một virtual hostname.

### Phân biệt các bước kiểm tra

| Phép kiểm | Chứng minh điều gì? | Không chứng minh điều gì? |
|---|---|---|
| `openssl x509 -in file.crt -noout -text` | File parse được, có subject, SAN, validity/extensions | Server đã nạp đúng file hay client sẽ tin nó |
| Digest public key từ cert/key bằng nhau | Key và cert có cùng public key | CA chain/hostname và policy của client đúng |
| `curl --cacert cert ...` không lỗi verify | Theo trust policy của curl, TLS identity cho host được xác minh | Certificate được CA công khai tin hoặc toàn bộ security architecture an toàn |
| `curl -k ...` thành công | Tầng transport có thể bắt tay khi tắt verification | Bất kỳ bảo đảm nào về hostname/trust/issuer |
| `openssl s_client ... -servername` | Quan sát TLS handshake và certificate do server gửi | Spring controller/authorization sau handshake chắc chắn đúng |
| `curl --http2 ...` có h2 | Client và endpoint đã thương lượng HTTP/2 nếu curl hỗ trợ | Tất cả proxy hop/backend cũng đang chạy HTTP/2 |

Nếu certificate hết hạn, server đôi khi vẫn có thể start nhưng client sẽ từ chối tại bước xác thực. Kiểm tra cả startup logs **và** một TLS client thực tế.

## 8. Cách viết cùng cấu hình bằng application.yaml

Nếu dự án dùng YAML thay vì properties, cấu hình tương đương là:

~~~yaml
server:
  port: 8443
  ssl:
    bundle: webserver

spring:
  ssl:
    bundle:
      pem:
        webserver:
          keystore:
            certificate: "classpath:tls/localhost.crt"
            private-key: "classpath:tls/localhost.key"
~~~

Đừng đặt cùng một setting vào cả `application.properties` lẫn `application.yaml` rồi không rõ file nào được Boot load/ưu tiên. Trong ứng dụng thật, có thể cấu hình qua Spring profiles, environment variables hoặc configuration service; nhớ kiểm soát property precedence và **không log giá trị private-key PEM**.

### Tên bundle và environment variables

Tên PEM bundle như `webserver` là tên logic. Tài liệu Boot nêu rằng **khi cấu hình bundle qua environment variables, bundle name được chuyển thành lowercase**. Vì vậy nên đặt tên đơn giản/chữ thường nếu dựa vào environment variables hoặc Kubernetes config injection, rồi dùng đúng cùng tên trong `server.ssl.bundle`.

Nếu dùng cấu hình profile dev/prod, mỗi profile có thể trỏ `webserver` tới các certificate khác nhau; nguyên lý áp dụng vẫn là `server.ssl.bundle=webserver`.

## 9. Sử dụng PEM bên ngoài JAR trong production

Không nên đóng gói **private key production** vào JAR. Một mô hình triển khai phổ biến:

~~~text
app.jar                                 [artifact ứng dụng, không chứa key]
/etc/myapp/tls/fullchain.pem            [certificate leaf + intermediate(s)]
/etc/myapp/tls/privkey.pem              [private key, quyền đọc hạn chế]
~~~

`application-prod.properties` có thể viết:

~~~properties
server.port=8443
server.ssl.bundle=webserver

spring.ssl.bundle.pem.webserver.keystore.certificate=file:/etc/myapp/tls/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/etc/myapp/tls/privkey.pem
~~~

Khi triển khai Linux/Kubernetes, đường `file:/...` phải tồn tại **bên trong runtime container/host** nơi JVM chạy; đây không phải path trên máy lập trình. Certificate chain trong `fullchain.pem` cần đúng thứ tự/issuer theo công cụ cấp chứng thư; private key phải khớp public key của leaf certificate. Không đặt CA root private key trên máy chủ ứng dụng.

Trong Kubernetes, có thể dùng Secret volume đọc-only chứa certificate/key và cấu hình path trỏ tới mount. Giới hạn quyền đọc của process; tránh lưu key vào ConfigMap/Source Control. Trong môi trường cloud, cân nhắc secret manager/ACME automation/certificate manager phù hợp thay vì sao chép file bằng tay.

**Một lựa chọn khác** được Boot hỗ trợ là PEM inline hoặc giá trị Base64 có prefix `base64:` cho các property thích hợp. Điều này có thể hữu ích khi inject qua configuration/secret provider, nhưng cũng tăng rủi ro lộ nội dung qua logs, environment, debug tools hoặc cấu hình bị xuất. Không đưa private key raw vào issue, screenshot hay tài liệu công khai.

### Câu hỏi: có cần truststore trên server không?

Với HTTPS **server authentication một chiều**, server thường chỉ cần **identity** (certificate + private key). Client/browser có truststore/root store của riêng mình để kiểm tra server. Việc thêm `spring.ssl.bundle.pem.webserver.truststore.certificate` không tự khiến mọi client trên Internet tin certificate self-signed của bạn. Để client tin, phải có chain từ CA được client tin hoặc chủ động cài trust anchor phù hợp.

Server truststore có ý nghĩa rõ khi bạn bật **mTLS** để server xác thực certificate của client; xem mục 13.

## 10. Không trộn server.ssl.bundle với cấu hình SSL cũ

Spring Boot vẫn có các property cấu hình SSL kiểu truyền thống:

~~~properties
# Ví dụ đường cấu hình trực tiếp (CHỌN MỘT CÁCH, KHÔNG DÙNG CÙNG BUNDLE)
server.ssl.certificate=classpath:tls/localhost.crt
server.ssl.certificate-private-key=classpath:tls/localhost.key
~~~

Nhưng nếu đã dùng:

~~~properties
server.ssl.bundle=webserver
~~~

thì **không kết hợp** nó với các property certificate/private-key hoặc JKS keystore rời thuộc `server.ssl` như:

- `server.ssl.key-store` / `server.ssl.key-store-password`;
- `server.ssl.certificate` / `server.ssl.certificate-private-key`;
- `server.ssl.trust-certificate` theo mô hình trực tiếp.

Tài liệu Spring Boot 3.3 nêu rõ `server.ssl.bundle` **không thể kết hợp** với các lựa chọn JKS/PEM rời ở `server.ssl`. Đặc biệt, các property như `server.ssl.ciphers`, `server.ssl.enabled-protocols`, `server.ssl.protocol` **bị bỏ qua khi dùng bundle**; hãy đưa tùy chọn protocol/cipher vào cấu hình `spring.ssl.bundle.<type>.<name>.options` theo property metadata của đúng phiên bản Boot.

**Lỗi thường gặp:** copy một bài hướng dẫn cũ có `server.ssl.key-store` rồi thêm `server.ssl.bundle` lên cùng file. Khi đó không có một cấu hình đáng tin để ứng dụng dùng; phải xóa một nhánh, không “thử thêm” nhiều property hơn.

## 11. SslBundles API và tái sử dụng bundle trong ứng dụng

Spring Boot tự đăng ký bean `SslBundles` cho các bundle được khai báo qua `spring.ssl.bundle.*`. Mỗi bundle có tên và có thể được truy xuất để tạo TLS objects cho những client libraries có integration phù hợp.

Đoạn code **minh họa trong một Spring-managed component**:

~~~java
package example.pemserver;

import javax.net.ssl.SSLContext;

import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.stereotype.Component;

@Component
public class SslInspection {
    private final SslBundles bundles;

    public SslInspection(SslBundles bundles) {
        this.bundles = bundles;
    }

    public SSLContext contextForWebserver() {
        SslBundle bundle = bundles.getBundle("webserver");
        return bundle.createSslContext();
    }
}
~~~

Đây là **class Java đầy đủ** nếu thêm đúng file `SslInspection.java` vào ứng dụng ví dụ, nhưng method không được tự động gọi và không cần để server HTTPS hoạt động. Chỉ dùng khi một thư viện client hoặc custom integration thực sự cần đối tượng `SSLContext`.

Một `SslBundle` cung cấp các lớp API:

- `getStores()`: truy cập key store/trust store và thông tin cần thiết;
- `getManagers()`: key managers và trust managers;
- `createSslContext()`: tạo `SSLContext`;
- các options/protocol/key details khác phù hợp cấu hình.

**Không nhầm server identity bundle với client trust bundle.** Dùng một private key server cho outbound HTTP client không phải luôn đúng. Nếu ứng dụng cần gọi API bên ngoài và tin CA riêng của API đó, nên định nghĩa **bundle riêng cho outbound client**, chứa trust certificate cần thiết.

Ví dụ định nghĩa một trust bundle khác:

~~~properties
spring.ssl.bundle.pem.partnerclient.truststore.certificate=file:/etc/myapp/tls/partner-ca.pem
~~~

Sau đó, client integration phù hợp có thể tham chiếu `partnerclient` theo cơ chế của Spring Boot/HTTP client tương ứng. Đoạn này **chỉ khai báo**, không tự cấu hình mọi HTTP client tùy chỉnh đang chạy trong ứng dụng.

## 12. SSL bundle và Spring WebFlux / Reactor Netty

Với ứng dụng WebFlux, thay Maven starter web bằng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Đây là **đoạn dependency thay thế** ở một dự án khác, không thêm cùng starter MVC trong lab. Với embedded Reactor Netty mặc định, các property `server.port`, `spring.ssl.bundle.pem.webserver...` và `server.ssl.bundle=webserver` có cùng vai trò khai báo/apply identity của HTTPS server.

Một controller WebFlux đơn giản:

~~~java
package example.reactivepem;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {
    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("TLS OK");
    }
}
~~~

Class này **chưa phải cả ứng dụng runnable độc lập**; cần `@SpringBootApplication`, WebFlux starter và các certificate/properties như lab. Sự khác nhau nằm ở web stack/cơ chế HTTP xử lý sau TLS, không nằm ở cách định nghĩa bundle. Với Reactor Netty, SSL bundle được Boot áp vào server thông qua auto-configuration; bạn không phải tự tạo `HttpServer.secure(...)` khi chỉ cần một HTTPS connector mặc định.

**Quan trọng:** TLS handshake không biến application code blocking thành non-blocking. Nếu handler WebFlux gọi JDBC blocking hoặc file I/O đồng bộ trên event loop, khả năng chịu tải có thể vẫn kém dù HTTPS được cấu hình đúng. SSL và concurrency của reactive runtime là các vấn đề khác nhau.

## 13. mTLS: áp dụng trust certificate cho máy chủ nhúng

HTTPS một chiều: client kiểm tra server. **Mutual TLS (mTLS)**: server còn yêu cầu hoặc mong muốn certificate từ client. Trong Spring Boot 3.3 có thể cấu hình server trust material trong bundle và bật client-auth trên server.

Ví dụ **chỉ dành cho môi trường đã có CA cấp client certificates phù hợp**:

~~~properties
server.port=8443
server.ssl.bundle=webserver
server.ssl.client-auth=need

spring.ssl.bundle.pem.webserver.keystore.certificate=file:/etc/myapp/tls/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/etc/myapp/tls/privkey.pem
spring.ssl.bundle.pem.webserver.truststore.certificate=file:/etc/myapp/tls/client-ca.pem
~~~

- `keystore.certificate` + `keystore.private-key` = **danh tính của server**;
- `truststore.certificate` = CA/certificate dùng để **tin danh tính client**;
- `server.ssl.client-auth=need` = yêu cầu client certificate hợp lệ để bắt tay TLS;
- `server.ssl.client-auth=want` = có thể yêu cầu nhưng không bắt buộc; phải kiểm tra identity/authorization ở tầng ứng dụng nếu chính sách yêu cầu.

Không thay `need` bằng `want` với kỳ vọng bảo mật tương đương. Sau TLS client authentication, **authorization vẫn cần**: một certificate hợp lệ không tự động cấp mọi quyền ứng dụng. Tùy mô hình, map identity từ SAN/subject tới service account/role và kiểm soát revoke/rotation.

Với một client đã có identity certificate/key được CA của server tin, curl có thể gọi:

~~~bash
curl --cacert server-ca.pem --cert client.crt --key client.key https://api.example.test:8443/hello
~~~

Các file trong lệnh này đại diện **tài liệu PKI đã được cấp thật**; lệnh không chạy với cert localhost ở lab nếu chưa tạo CA/client certificates. Tùy client, key algorithm, certificate chain và TLS handshake settings, có thể cần cấu hình bổ sung. Kiểm tra rằng request không có client certificate được từ chối ở cấp handshake khi policy là `need`.

## 14. Bật HTTP/2 trên HTTPS server đã cấu hình bundle

**TLS và HTTP/2 liên quan nhưng không đồng nhất.** HTTPS chạy được không có nghĩa HTTP/2 được bật. Spring Boot cung cấp:

~~~properties
server.http2.enabled=true
~~~

Kết hợp với bundle trong lab:

~~~properties
server.port=8443
server.ssl.bundle=webserver
server.http2.enabled=true

spring.ssl.bundle.pem.webserver.keystore.certificate=classpath:tls/localhost.crt
spring.ssl.bundle.pem.webserver.keystore.private-key=classpath:tls/localhost.key
~~~

**HTTP/2 over TLS** thường được đàm phán qua extension **ALPN**. Client và server có thể lựa chọn `h2` hoặc quay về `http/1.1` tùy phiên bản TLS, stack và hỗ trợ ALPN. Trên Spring Boot 3.3, Tomcat 10.1.x và Reactor Netty hỗ trợ HTTP/2 trong cấu hình thích hợp; Jetty cần dependency HTTP/2 phù hợp.

### Kiểm tra HTTP/2 thực tế

~~~bash
curl -V
curl --http2 --cacert src/main/resources/tls/localhost.crt -v https://localhost:8443/hello
~~~

`curl -V` phải liệt kê hỗ trợ HTTP2; nếu không, bản curl đó không thực hiện được phép thử. Với verbose output, tìm thông tin ALPN và HTTP version thật sự được thương lượng. Khi hoạt động đúng, request có thể hiện `HTTP/2 200` hoặc output tương đương tùy curl version. Body vẫn là `TLS OK`.

Có thể kiểm tra ALPN bằng OpenSSL:

~~~bash
openssl s_client -connect localhost:8443 -servername localhost -CAfile src/main/resources/tls/localhost.crt -alpn h2,http/1.1
~~~

Nếu thương lượng thành công, thông tin về ALPN protocol được hiển thị. Không coi việc client gửi tùy chọn `-alpn h2` là bằng chứng server đã chấp nhận `h2`; phải xem **negotiated protocol**.

**Lưu ý proxy:** nếu nginx/ingress terminate TLS và nhận HTTP/2 từ browser nhưng kết nối đến Spring Boot bằng HTTP/1.1, client vẫn thấy h2 ở mặt ngoài. Điều này không chứng minh embedded backend của Spring Boot dùng HTTP/2. Hãy kiểm tra đúng hop cần đo.

### h2 khác h2c

- `h2`: HTTP/2 qua TLS, thường dùng với HTTPS và ALPN.
- `h2c`: HTTP/2 không TLS (cleartext), có thể dùng trong một số hop nội bộ với điều kiện stack/hạ tầng hỗ trợ.
- Bật `server.http2.enabled=true` khi SSL không bật có thể dẫn tới cấu hình h2c theo đặc tính server; không phải HTTPS.

Chính sách bảo mật của sản phẩm mới quyết định có chấp nhận h2c ở hop nội bộ hay phải mã hóa end-to-end. HTTP/2 **không tự giải quyết** xác thực certificate, rotation, client-auth, resource limits hay authorization.

## 15. HTTPS trực tiếp ở JVM hay TLS termination tại reverse proxy?

Hai kiến trúc phổ biến:

~~~text
A. TLS terminate tại Spring Boot:
Browser --HTTPS--> embedded Tomcat/Netty :8443
                      |
                      v
                    Controller

B. TLS terminate tại ingress:
Browser --HTTPS--> CDN/ingress/proxy :443
                      |
                      | HTTP nội bộ hoặc HTTPS re-encrypt
                      v
              Spring Boot :8080 / :8443
~~~

**Mô hình A:** Spring Boot cần identity certificate/private key/bundle trên máy chủ nhúng. JVM quản lý TLS listener và có thể dùng reload-on-update. Cần quản lý key file/quyền truy cập của ứng dụng.

**Mô hình B:** certificate cho domain public có thể do ingress/proxy quản lý. Spring Boot backend có thể chỉ nghe HTTP ở mạng tin cậy, nên **không nhất thiết cần server.ssl.bundle** cho kết nối client-facing. Nếu hop proxy → app cần TLS (mTLS nội bộ, zero-trust, compliance), thì cấu hình bundle tại backend vẫn cần.

Không kết luận app đã “HTTPS toàn tuyến” nếu chỉ thấy `https://` trên trình duyệt: phải biết sơ đồ các hop. Nếu proxy điền `X-Forwarded-Proto` hoặc chuẩn `Forwarded`, Spring Boot có cấu hình xử lý forwarded headers theo môi trường, nhưng **chỉ tin header từ proxy đã được kiểm soát**; không được chấp nhận chúng từ client tùy ý để quyết định URL redirect hoặc secure-cookie handling.

## 16. SNI: dùng nhiều certificate cho các hostname

SNI (*Server Name Indication*) cho phép client nêu server name trong ClientHello, giúp server chọn certificate cho hostname tương ứng. Spring Boot 3.3 có `server.ssl.server-name-bundles` cho các embedded servers hỗ trợ tính năng.

Giả sử đã có bundle mặc định `webserver` và bundle thứ hai `tenant2`, có thể khai báo:

~~~properties
server.port=8443
server.ssl.bundle=webserver

server.ssl.server-name-bundles[0].server-name=tenant2.example.test
server.ssl.server-name-bundles[0].bundle=tenant2
~~~

Đây là **đoạn cấu hình bổ sung**, yêu cầu bạn định nghĩa bundle `tenant2` và đặt certificate của nó đúng hostname. Nếu không, cấu hình không hoàn chỉnh. Trên Boot 3.3, hỗ trợ SNI bundle mappings phụ thuộc embedded server: Tomcat, Netty và Undertow hỗ trợ; Jetty có cơ chế SNI/container riêng, không cùng API cấu hình như trên.

Bundle mặc định `webserver` vẫn quan trọng cho các kết nối dùng default host hoặc không khớp mapping. Tạo SNI mapping không thay thế bước kiểm tra SAN/trust của từng certificate. Khi test, dùng đúng hostname và `openssl s_client -servername tenant2.example.test` với đường tới IP/service tương ứng.

## 17. Xoay vòng và reload certificate PEM

Certificate có thời hạn. Production phải có kế hoạch cấp phát, theo dõi expiry, gia hạn, triển khai material mới và xác nhận server đang trình bày đúng leaf certificate. **Spring Boot không tự đi xin/gia hạn certificate của Let’s Encrypt**; bạn cần ACME client/certificate manager hoặc quy trình PKI tương ứng.

Spring Boot 3.3 hỗ trợ **reloadable SSL bundles** với consumer tương thích; tài liệu chính thức nêu **Tomcat web server** và **Netty web server** là các thành phần tương thích với reload-on-update. Đây là giới hạn quan trọng: **không giả định Jetty hoặc Undertow nhận được cùng hot-reload behavior**.

Ví dụ cấu hình production với PEM files bên ngoài JAR:

~~~properties
server.port=8443
server.ssl.bundle=webserver

spring.ssl.bundle.pem.webserver.keystore.certificate=file:/etc/myapp/tls/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/etc/myapp/tls/privkey.pem
spring.ssl.bundle.pem.webserver.reload-on-update=true
~~~

Khi file certificate/private key thay đổi, file watcher kiểm tra material mới và bundle có thể được reload, từ đó server consumer tương thích áp dụng certificate mới. Có thể cấu hình khoảng chờ khi theo dõi file bằng `spring.ssl.bundle.watch.file.quiet-period`, giúp tránh reload giữa một đợt update nhiều file.

### Những rủi ro rotation cần xử lý

1. **Cert và key phải đồng bộ:** nếu cập nhật từng file một, trong chốc lát có thể có cặp không khớp. Dùng chiến lược atomic update / deployment transaction phù hợp, rồi kiểm tra reload.
2. **Chain phải đầy đủ:** dùng bundle của certificate leaf + intermediates thích hợp, không chỉ một leaf thiếu issuer.
3. **Quyền truy cập:** quá trình update có thể thay owner, permission, symlink hoặc mount; JVM cần tiếp tục đọc được material mới.
4. **Existing connections:** rotation không đồng nghĩa tất cả phiên TLS đang mở lập tức handshake lại. Kiểm tra behavior với kết nối mới, connection reuse và HTTP/2 lâu dài.
5. **Không giả định reload luôn thành công:** có thể lỗi parse, key mismatch, permission, watcher hoặc unsupported container. Theo dõi logs/metrics và dùng phép thử bên ngoài để xác nhận certificate mới.
6. **Giữ bí mật:** private key cũ vẫn có thể nằm trên backup, volume snapshot hoặc archive. Quy trình revoke/rotation phải cân nhắc phạm vi rò rỉ và secret disposal.

Với Certbot/Let’s Encrypt, file `/etc/letsencrypt/live/<domain>/fullchain.pem` và `privkey.pem` thường là symlinks đến bản trong `archive`. Tài liệu Boot cho biết file watcher theo dõi cả symlink targets phù hợp để phát hiện cập nhật; tuy vậy hãy kiểm thử trên đúng filesystem/container runtime đang triển khai.

Không bật `reload-on-update=true` trong lab dùng `classpath:tls/localhost.crt` nhúng trong JAR rồi kỳ vọng sửa file source trên máy sẽ làm JAR đang chạy tự đổi certificate. Reload hữu ích khi server đọc các **file vật lý** tại runtime.

## 18. Chẩn đoán lỗi TLS theo thứ tự

### 18.1. Không start được server: sai đường resource

**Dấu hiệu:** startup exception liên quan không tìm được certificate/private key hoặc không load được SSL material.

**Kiểm tra:**

- `classpath:tls/localhost.crt` có file trong `src/main/resources/tls/` và được đóng gói vào JAR chưa?
- File resource của executable JAR nằm ở `BOOT-INF/classes/tls/...` hay bị exclude bởi build?
- `file:/etc/myapp/tls/...` có thực sự tồn tại **bên trong container** không?
- File có permission cho user chạy JVM không?
- Tên bundle ở `server.ssl.bundle` có trùng `spring.ssl.bundle.pem.<name>` không?

Không dùng relative path tùy current working directory khi file thuộc classpath, vì môi trường IDE/Docker/production có thư mục làm việc khác nhau.

### 18.2. PEM key không đọc được

**Dấu hiệu:** exception khi parse private key, unsupported key format, invalid PEM header hoặc password.

**Nguyên nhân thường gặp:** file PKCS#1/SEC 1 thay vì PKCS#8; PEM bị cắt, encoding bị thay, private key được mã hóa nhưng password không cấu hình; file chứa certificate thay cho key.

Với key chưa mã hóa dạng cũ, có thể chuyển sang PKCS#8:

~~~bash
openssl pkcs8 -topk8 -nocrypt -in old-server.key -out server-pkcs8.key
~~~

Lệnh này tạo private key PKCS#8 **không mã hóa**, nên bảo vệ file bằng quyền truy cập/secret storage. Nếu production policy đòi encrypted private key, dùng khả năng/password cấu hình được hỗ trợ của Boot version hiện tại và secret manager; không dán password trực tiếp vào tài liệu dùng chung.

### 18.3. Certificate và private key không khớp

**Dấu hiệu:** lỗi khởi tạo TLS key material hoặc handshake.

Kiểm tra bằng hai digest public-key DER ở mục 5.4. Nếu không bằng nhau, đừng cố gắn nhầm cặp key/cert; lấy đúng key tương ứng từ quy trình PKI hoặc cấp certificate mới.

### 18.4. curl báo self-signed/unable to get local issuer

**Ý nghĩa:** client không thể xây chain tới CA đã tin, hoặc thiếu intermediate. Với demo self-signed, dùng `--cacert localhost.crt` để thêm trust theo cách có chủ đích. Production cần chain đúng và CA được tin; đừng “chữa” bằng cách bật `-k`.

Khi chain thiếu intermediate, server có thể start bình thường nhưng client xác minh thất bại. Kiểm tra `fullchain.pem`, thứ tự leaf/intermediate và truststore của client.

### 18.5. Hostname mismatch

**Dấu hiệu:** certificate không hợp lệ cho hostname hoặc IP URL đã gọi. Kiểm tra SAN:

~~~bash
openssl x509 -in src/main/resources/tls/localhost.crt -noout -ext subjectAltName
~~~

Nếu SAN chỉ có `DNS:localhost`, request đến `https://127.0.0.1` có thể fail. Không chỉ sửa CN; client hiện đại xác minh tên qua SAN. Certificate phải chứa DNS hoặc IP SAN thích hợp; URL public phải khớp đúng hostname đã cấp.

### 18.6. Certificate hết hạn hoặc chưa đến hiệu lực

~~~bash
openssl x509 -in src/main/resources/tls/localhost.crt -noout -dates
~~~

`notBefore` và `notAfter` phải phù hợp thời gian thật trên client/server; đồng hồ sai có thể dẫn đến validation error. Theo dõi expiry trước hạn, không đợi tới lúc production handshake lỗi mới phát hiện.

### 18.7. server.ssl.bundle xung đột config SSL cũ

Xóa các property certificate/key-store rời trong `server.ssl` nếu đã chọn bundle. Nhớ rằng `server.ssl.ciphers` và `server.ssl.enabled-protocols` không điều khiển bundle như bạn có thể mong đợi; xem bundle options của version thực đang dùng. Dùng `--debug`/condition logs có kiểm soát khi startup config không rõ, không bật debug lộ secrets trên môi trường công khai.

### 18.8. HTTP 8080 không hoạt động sau khi bật HTTPS

Bạn đã cấu hình một HTTPS connector trên `server.port=8443`. Boot không tự giữ plain HTTP ở cổng 8080. Đây thường là **hành vi đúng**, không phải lỗi. Nếu muốn redirect HTTP → HTTPS, cấu hình ở trusted proxy/ingress hoặc programmatically thêm HTTP connector khi kiến trúc yêu cầu.

### 18.9. HTTP/2 không được thương lượng

Kiểm tra lần lượt:

1. `server.http2.enabled=true` đã có trong effective config?
2. Đã dùng `https://` đúng port có TLS chưa?
3. curl có support HTTP2? Xem `curl -V`.
4. Trong verbose output, ALPN có thực sự chọn `h2` không?
5. Embedded server là Tomcat/Netty/Jetty gì? Jetty có dependency HTTP2/ALPN bổ sung không?
6. Có TLS-terminating proxy ở giữa khiến client h2 nhưng backend h1 không?
7. Có thể client/server fallback hợp lệ về HTTP/1.1; đừng chỉ nhìn body `TLS OK` rồi suy ra h2.

### 18.10. Reload certificate không có tác dụng

Kiểm tra: dùng file: resources ngoài JAR, reload-on-update đúng bundle, consumer là Tomcat/Netty trên Boot 3.3, file watcher nhận thay đổi (kể cả symlinks), certificate/key match, permissions và startup logs. Dùng **kết nối TLS mới** và `openssl s_client` kiểm tra certificate serial/expiry đang trình bày thay vì dựa vào browser giữ HTTP/2 connection cũ.

### 18.11. Proxy thành công nhưng app logs không thấy TLS

Có thể TLS đã terminate ở ingress. Phân biệt công cụ đang kiểm tra cổng nào và hop nào. Cấu hình `server.ssl.bundle` không phải yêu cầu bắt buộc của backend nếu mô hình proxy → backend dùng HTTP nội bộ được kiểm soát.

## 19. Bảo mật production: checklist bắt buộc

- **Tách identity và trust:** private key server là secret; certificate chain thường có thể công khai; truststore xác định CA đối tác đáng tin.
- **Quản lý vòng đời:** ai cấp cert, ai renew, khi nào expire, ai rotate, cách revoke, thông báo trước hạn và quy trình fallback.
- **Đúng hostname/SAN:** cấp cert theo DNS production, không dùng self-signed localhost hoặc wildcard quá rộng nếu không cần.
- **Cấu hình TLS hiện đại:** chọn versions/ciphers phù hợp policy/security baseline và khả năng hỗ trợ của clients; không bật protocol cũ chỉ để xử lý một client không tương thích mà thiếu phê duyệt.
- **Quyền truy cập key:** secret volume, filesystem ACL, user tối thiểu; không log/key dump, không commit git hoặc bake key vào container image.
- **Certificate chain và trust:** đầy đủ intermediates, tin đúng root/trust anchors, hạn chế trust CA không cần thiết.
- **mTLS khi cần:** cấu hình client-auth và client CA đúng; không coi mTLS thay thế app authorization hoặc resource-level access control.
- **Đừng dùng `--insecure` làm chuẩn kiểm thử:** acceptance test phải giữ xác thực hostname/chain.
- **Theo dõi runtime:** handshake failures theo loại, certificate expiry, số HTTPS connections, HTTP/2 negotiation và renewal/reload outcomes.
- **Kiến trúc multi-hop:** lập sơ đồ client → CDN → ingress → service; kiểm tra hop nào có TLS và ai sở hữu keys.
- **Deployment rotation:** cập nhật cert/key nhất quán, xác minh new connections và rollback khi reload lỗi.
- **Vấn đề bổ sung:** TLS bảo vệ dữ liệu trên đường truyền, không tự chống XSS, SQL injection, broken authorization hoặc credential theft trên endpoint.

## 20. Thử nghiệm và báo cáo kết quả

Một bài thực hành hoàn chỉnh nên lưu các thông tin sau:

~~~text
Runtime:
  Spring Boot: 3.3.x
  Java: 17+
  Embedded server: Tomcat (MVC) hoặc Reactor Netty (WebFlux)
  Port: 8443
  Source of key material: classpath (lab) hoặc mounted file (production)

Identity material:
  certificate subject
  SAN
  notBefore / notAfter
  issuer chain
  public-key match test result

TLS checks:
  openssl pkey -check passed
  curl --cacert https://localhost:8443/hello -> 200 TLS OK
  hostname/IP SAN verified
  no --insecure flag used for acceptance
  curl http://localhost:8443 -> not valid plaintext HTTP

HTTP/2 checks, if enabled:
  curl -V shows HTTP2 support
  ALPN negotiated protocol
  HTTP response version observed

Production/rotation checks, if applicable:
  externally mounted key and certificate
  access permissions
  refresh/reload policy
  new-handshake certificate serial/expiry
  no secret leaked in logs/artifact
~~~

**Đừng khẳng định số đo cụ thể chưa có bằng chứng.** Status 200 qua curl chứng minh endpoint reachable với certificate trust đã cấu hình; để nói “HTTP/2 đang bật”, phải thấy phiên bản HTTP thực tế. Để nói “rotation thành công”, phải so cert serial/fingerprint hoặc thời gian hiệu lực trên **connection mới**.

### Bài tập A – đổi tên bundle

Đổi `webserver` thành `frontend` tại mọi dòng `spring.ssl.bundle.pem.webserver...` và `server.ssl.bundle`. Khởi động lại và xác minh HTTPS. Nếu cố tình chỉ đổi một phía, dự đoán lỗi tham chiếu bundle rồi kiểm tra startup exception.

### Bài tập B – kiểm tra SAN

Tạo một certificate chỉ chứa `DNS:localhost`, gọi bằng IP và hostname bằng `--cacert`. Quan sát sự khác biệt. Trả lời vì sao CN không đủ cho hostname validation hiện đại.

### Bài tập C – chuyển classpath sang file mount

Đưa `localhost.crt` và `localhost.key` ra thư mục ngoài project, đổi property sang `file:/...` và chạy lại. Kiểm tra permission và không để private key nằm trong JAR production.

### Bài tập D – HTTP/2 trên TLS

Thêm `server.http2.enabled=true`, chạy `curl -V`, `curl --http2 -v --cacert ...` và ghi negotiated ALPN. Phân biệt negotiated h2 với request chỉ có option `--http2`.

### Bài tập E – rotation thử nghiệm

Chỉ trong local lab, dùng các file vật lý ngoài JAR và `reload-on-update=true` trên Tomcat/Netty. Cấp một certificate mới đúng SAN và key tương ứng, thay nhất quán, kiểm tra new handshakes và ghi timestamp/fingerprint. Chú ý việc cập nhật file không atomic có thể tạo khoảng ngắn cert/key mismatch.

### Bài tập F – sơ đồ TLS nhiều hop

Vẽ sơ đồ một hệ có browser → ingress HTTPS → Spring Boot HTTP nội bộ. Chỉ ra bundle ở đâu, ai giữ private key public domain và có cần TLS cho ingress → backend hay không. Nếu có mTLS nội bộ, cần identity/trust của những bên nào?

## 21. Câu hỏi ôn tập có đáp án

**1. Chỉ định nghĩa PEM SSL bundle trong `spring.ssl.bundle.pem.*` đã đủ bật HTTPS cho embedded server chưa?**  
Chưa. Cần thành phần áp dụng bundle, ví dụ `server.ssl.bundle=webserver`, cùng server port và certificate/key hợp lệ.

**2. PEM certificate và private key có phải một loại file?**  
Không. Certificate chứa public key và thông tin X.509 được công bố; private key là bí mật. Chúng có thể cùng được PEM-encode nhưng không cùng nội dung hoặc vai trò.

**3. Vì sao nên dùng PKCS#8?**  
Vì Spring Boot khuyến nghị private key PEM PKCS#8 để tăng khả năng tương thích; định dạng này thường có header `BEGIN PRIVATE KEY` (hoặc encrypted variant).

**4. Certificate tự ký của localhost có thể test mà không dùng curl -k không?**  
Có. Dùng `curl --cacert localhost.crt https://localhost:8443/hello` để client chủ động tin certificate cho lab, đồng thời vẫn kiểm tra hostname.

**5. `server.ssl.bundle` có được đi cùng `server.ssl.certificate-private-key` không?**  
Không. Khi dùng bundle, không trộn các discrete JKS/PEM properties dưới `server.ssl`.

**6. Server HTTPS bình thường có cần truststore của CA client không?**  
Không nhất thiết. Server chủ yếu cần identity certificate/key; trust certificate dành cho xác minh peer, nhất là mTLS.

**7. Nếu certificate SAN chỉ có localhost nhưng client truy cập 127.0.0.1, điều gì có thể xảy ra?**  
Hostname/IP verification fail. Cần SAN `IP:127.0.0.1` cho URL theo IP.

**8. Bật server.http2.enabled=true có bảo đảm client luôn dùng HTTP/2 không?**  
Không. Client, TLS ALPN, container/proxy và compatibility quyết định negotiated protocol. Phải kiểm tra response version và ALPN thực tế.

**9. Tại sao private key không nên nằm trong JAR production?**  
Vì JAR/image/logs/backup được sao chép và phân phối rộng hơn nơi secret được phép tồn tại. Nên dùng secret mount/secret management với quyền truy cập tối thiểu.

**10. Bundle reload-on-update hỗ trợ hot reload ở mọi embedded server trên Boot 3.3 chứ?**  
Không. Tài liệu Boot 3.3 nêu Tomcat và Netty là các web server consumers tương thích. Không suy đoán Jetty/Undertow có cùng behavior.

**11. Vì sao browser có thể truy cập HTTPS dù backend Spring Boot không cấu hình server.ssl.bundle?**  
Vì một proxy/ingress phía trước có thể terminate TLS rồi chuyển HTTP nội bộ. Kiểm tra kiến trúc từng hop.

**12. Client dùng curl -k và thấy HTTP 200 có phải chứng minh certificate chain hợp lệ không?**  
Không. `-k` bỏ qua verification; cần dùng CA/trust phù hợp, kiểm tra SAN, issuer và validity.

## 22. Tài liệu chuẩn và đường dẫn đọc thêm

- [Spring Boot 3.3 – SSL](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html): PEM/JKS SSL bundles, SslBundles API, reload-on-update và nguyên tắc trust material.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `server.ssl.bundle`, PEM/PKCS#8, SNI, HTTP/2, tương thích embedded containers và giới hạn cấu hình SSL rời.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): property names, defaults và bundle options theo phiên bản.
- [Spring Boot Blog – Securing Spring Boot Applications with SSL](https://spring.io/blog/2023/06/07/securing-spring-boot-applications-with-ssl/): động cơ thiết kế SSL bundles và áp dụng cho embedded servers/client connections.
- [OpenSSL – genpkey](https://docs.openssl.org/3.0/man1/openssl-genpkey/): tạo private key dạng PEM/PKCS#8.
- [OpenSSL – req](https://docs.openssl.org/3.0/man1/openssl-req/): tạo CSR hoặc certificate tự ký với SAN.
- [OpenSSL – s_client](https://docs.openssl.org/3.0/man1/openssl-s_client/): kiểm tra TLS handshake, SNI, ALPN và certificate chain.
- [RFC 8446 – TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): nền tảng TLS 1.3.
- [RFC 7301 – TLS Application-Layer Protocol Negotiation](https://www.rfc-editor.org/rfc/rfc7301): ALPN để thương lượng HTTP/2 over TLS.
- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 framing và giao thức.
