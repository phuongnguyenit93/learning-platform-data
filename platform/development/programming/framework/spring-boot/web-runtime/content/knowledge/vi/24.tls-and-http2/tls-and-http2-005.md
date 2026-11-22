# Client authentication và truststore khi yêu cầu mTLS trong Spring Boot

## 1. Bối cảnh và mục tiêu

**Mutual TLS (mTLS)** là HTTPS trong đó **cả server và client đều chứng minh danh tính bằng chứng chỉ X.509**. HTTPS thông thường yêu cầu client kiểm tra chứng chỉ của server; mTLS bổ sung yêu cầu **server kiểm tra chứng chỉ client** trong quá trình TLS handshake, trước khi request được chuyển đến Spring MVC Controller.

Bài này thuộc **Spring Boot - web-runtime**, nhóm **TLS và HTTP/2**. Ví dụ dựa trên **Spring Boot 3.3.x, Java 17+, embedded Tomcat và Spring MVC**, đồng thời nêu những khác biệt nếu ứng dụng là outbound HTTP client, chạy sau reverse proxy hoặc đi qua service mesh. Một CA tự tạo chỉ dành cho môi trường học tập được dùng để thực hành; không dùng chứng chỉ và mật khẩu demo cho production.

Kết thúc bài học, bạn có thể:
1. Giải thích chính xác **server keystore**, **server truststore**, **client keystore** và **client truststore**.
2. Chọn **server.ssl.client-auth: need/want/none** phù hợp, không nhầm TLS handshake với HTTP 401/403.
3. Cấu hình mTLS theo **PEM trực tiếp**, **PKCS12/JKS** hoặc **SSL bundle** mà không trộn lẫn các phương án.
4. Tự tạo CA, server certificate, client certificate, phân biệt **SAN**, **EKU**, chain, CA và private key.
5. Chạy một Spring Boot HTTPS server bắt buộc client certificate, kiểm tra thành công và thất bại bằng **curl/OpenSSL**.
6. Gửi client certificate từ ứng dụng Spring Boot khác bằng **RestClientSsl**.
7. Hiểu vai trò của Spring Security, proxy/ingress, SSL bundle rotation và HTTP/2 ALPN.
8. Lập checklist kiểm thử cả trường hợp có certificate đúng lẫn client không có certificate, sai CA, sai hostname và hết hạn.

## 2. mTLS diễn ra ở đâu trong vòng đời request?

### 2.1. HTTPS một chiều

~~~text
Client                                      HTTPS server
   |                                             |
   | --------- TLS ClientHello ----------------> |
   | <-------- Server certificate -------------- |
   |                                             |
   | Kiểm tra CA chain, SAN/hostname, thời hạn   |
   | và các chính sách tin cậy                   |
   |                                             |
   | ===== Kết nối TLS được chấp nhận =====      |
   | GET /api/ping                               |
   | ------------------------------------------> |
   | <--------------- HTTP response ------------ |
~~~

Server không nhất thiết biết danh tính của client sau HTTPS một chiều. Nếu API yêu cầu xác thực, nó thường cần bearer token, session, API key, OAuth2 hoặc một cơ chế ứng dụng khác.

### 2.2. Mutual TLS

~~~text
Client / Service A                          Server / Service B
    |                                               |
    | ------------ TLS ClientHello ----------------> |
    | <---- Server cert + CertificateRequest --------|
    |                                               |
    | A kiểm tra server cert, hostname, CA           |
    | A gửi client cert và proof of private key      |
    | ---------------------------------------------> |
    |                                               |
    |               B kiểm tra client cert/chain/CA  |
    |                                               |
    | ==== Handshake thành công nếu tin lẫn nhau ===  |
    | GET /api/ping                                 |
    | ---------------------------------------------> |
    | <---------------- HTTP response -------------- |
~~~

Sơ đồ là logic khái quát, không phải thứ tự đầy đủ của TLS 1.2 và TLS 1.3. Các bước xác thực chứng chỉ diễn ra ở **TLS layer**. Nếu client không có certificate mà connector yêu cầu **client-auth: need**, request thường bị từ chối **trước DispatcherServlet**. Vì thế một **@ControllerAdvice** không thể biến lỗi TLS handshake thành JSON 401 từ controller.

**Tầng TLS và tầng ứng dụng giải quyết hai câu hỏi khác nhau:**

- **TLS client authentication:** client có private key khớp certificate và được phát hành bởi trust anchor mà server chấp nhận không?
- **Authorization:** service/user đã được xác minh có quyền thực hiện thao tác trên resource không?

Một client pass mTLS **không tự động có quyền admin**. Server vẫn cần ánh xạ certificate identity sang principal và áp dụng role/scope/tenant authorization.

## 3. Keystore, truststore và hai chiều tin cậy

### 3.1. Ma trận vai trò

| Vật liệu | Bên sử dụng | Nội dung | Mục đích |
| --- | --- | --- | --- |
| **Server keystore** | Spring Boot server | Server private key + server leaf certificate/chain | Chứng minh danh tính server. |
| **Server truststore** | Spring Boot server | Client CA/CA chain được tin hoặc certificate được pin | Xác minh certificate do client gửi. |
| **Client keystore** | HTTP client | Client private key + client leaf certificate/chain | Chứng minh danh tính client. |
| **Client truststore** | HTTP client | CA cấp chứng chỉ server hoặc server certificate được tin | Xác minh server và kết hợp với hostname verification. |

**Keystore = danh tính của chính bên sở hữu; truststore = những danh tính/CA mà bên đó tin.** Keystore chứa private key cần bảo mật, truststore thường chứa certificate public. Một file **.crt** thường không chứa private key; file **.key** phải được giữ kín. File **.p12** có thể chứa private key, certificate và certificate chain tùy cách tạo.

Một tình huống phổ biến:

~~~text
CA cấp server.crt                  CA cấp client.crt
       |                                  |
server.crt + server.key          client.crt + client.key
       |                                  |
server keystore                  client keystore

server truststore  ---- tin CA đã cấp ----> client.crt
client truststore  ---- tin CA đã cấp ----> server.crt
~~~

Trong lab có thể dùng **cùng một CA** cấp cả hai certificate để dễ thao tác. Production có thể dùng **CA riêng cho server identity và client identity**, tránh mở rộng phạm vi tin cậy không cần thiết.

### 3.2. Certificate chain

~~~text
Trusted Root CA (có trong truststore)
      |
      +-- Intermediate CA
              |
              +-- Leaf certificate (client hoặc server)
~~~

Bên trình certificate thường gửi leaf và những intermediate cần thiết. Peer xác minh chain về trust anchor trong truststore; có thể thấy lỗi **PKIX path building failed**, **unknown_ca** hoặc **unable to get local issuer** nếu thiếu CA/chain phù hợp.

Không nhất thiết phải import **từng leaf** vào truststore. Tin CA giúp thay leaf cert dễ hơn, nhưng nếu CA cấp certificate cho nhiều workload thì **tất cả các workload đó có thể qua được bước kiểm tra chain**. Vì thế mTLS phải đi cùng certificate issuance policy và authorization phù hợp.

### 3.3. X.509 fields cần quan sát

- **Not Before / Not After:** khoảng thời gian hiệu lực; cert hết hạn hoặc chưa đến hiệu lực phải bị từ chối.
- **SAN (Subject Alternative Name):** server certificate cần DNS SAN/IP SAN khớp hostname/IP mà client thực sự truy cập. Chỉ dựa vào **CN** là cách kiểm tra tên server không còn phù hợp.
- **EKU (Extended Key Usage):** server leaf có thể cần **serverAuth**, client leaf cần **clientAuth**; EKU sai có thể làm TLS verify fail.
- **Key Usage:** leaf/CA có usage phù hợp (digitalSignature, keyCertSign…).
- **Basic Constraints:** CA certificate phải có CA:TRUE; leaf thông thường CA:FALSE.
- **Issuer, Subject, serial, public key:** hỗ trợ định danh và kiểm tra chính sách.
- **Revocation:** truststore chứa CA không tự chứng minh CRL/OCSP/revocation đang được thi hành; cần policy cụ thể.

Certificate hợp lệ theo chain chưa đủ để quyết định người gọi có quyền gọi mọi API hay không.

## 4. server.ssl.client-auth: none, want, need

| Cấu hình | Hành vi |
| --- | --- |
| **none** | Không yêu cầu client certificate; HTTPS một chiều. |
| **want** | Server **đề nghị** client trình certificate nhưng **không bắt buộc**. Client không có cert vẫn có thể thiết lập kết nối. |
| **need** | **Bắt buộc** client certificate; thiếu hoặc không tin cậy thường khiến TLS handshake thất bại. |

Trong Spring Boot 3.3, property chính là **server.ssl.client-auth**. Khi API cần mTLS trên **mọi request** đi qua embedded HTTPS connector, lựa chọn đúng thường là:

~~~yaml
server:
  ssl:
    client-auth: need
~~~

Cấu hình này **chưa đủ**. Server phải có **server private key + server certificate**, và có **trust material** để xác minh client. Spring Boot ghi rõ client authentication cần trust store.

**Không nhầm want với need.** Want phù hợp cho giai đoạn hỗ trợ cả client có/không có certificate hoặc policy phức tạp được thực thi ở ứng dụng; nếu bạn nói “connector này chỉ cho client có cert” nhưng dùng want thì chính sách chưa được enforce.

Không suy đoán rằng **client-auth: need** tự tạo danh tính trong Spring Security. Nó áp dụng ở connector; sau đó security filter/controller cần biết client identity thuộc workload nào và quyền ra sao.

## 5. Lab: tạo CA, server cert và client cert bằng OpenSSL

Các lệnh dưới đây dùng **OpenSSL 1.1.1+ hoặc 3.x** trên Linux/macOS/Git Bash/WSL. Với PowerShell, cần thay lệnh tạo file dạng here-document bằng cách ghi text tương ứng. Đây là lab cục bộ; không phát tán CA private key.

### 5.1. Tạo thư mục bảo vệ key

Chạy từ root project:

~~~bash
mkdir -p tls
umask 077
~~~

**umask 077** trên Unix hạn chế quyền file mới. Đặt **tls/** vào **.gitignore**, không commit private key hoặc đưa vào Docker image. CA private key chỉ dùng để ký chứng chỉ, không được mang vào container chạy server.

### 5.2. Tạo CA cho lab

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out tls/lab-ca.key

openssl req -new -x509 -sha256 -days 3 \
  -key tls/lab-ca.key \
  -out tls/lab-ca.crt \
  -subj "/CN=Study-mTLS-CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
~~~

- **lab-ca.crt:** public certificate của CA; dùng để cấu hình trust.
- **lab-ca.key:** private key bí mật, không đưa vào Spring Boot application.
- **3 ngày:** thời gian sống ngắn phục vụ lab, không phải policy production.

### 5.3. Tạo server key, CSR và server certificate có SAN

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out tls/server.key

openssl req -new \
  -key tls/server.key \
  -out tls/server.csr \
  -subj "/CN=localhost"
~~~

Tạo file **tls/server.ext**:

~~~text
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost,IP:127.0.0.1
~~~

Ký:

~~~bash
openssl x509 -req -sha256 -days 3 \
  -in tls/server.csr \
  -CA tls/lab-ca.crt \
  -CAkey tls/lab-ca.key \
  -CAcreateserial \
  -out tls/server.crt \
  -extfile tls/server.ext
~~~

Server private key ở **server.key**, certificate ở **server.crt**; SAN cho **localhost** và IP **127.0.0.1**. Vì vậy trong test mismatch, phải chọn hostname khác hai giá trị đó.

### 5.4. Tạo client certificate có EKU clientAuth

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out tls/client.key

openssl req -new \
  -key tls/client.key \
  -out tls/client.csr \
  -subj "/CN=demo-client"
~~~

Tạo **tls/client.ext**:

~~~text
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=clientAuth
~~~

Ký:

~~~bash
openssl x509 -req -sha256 -days 3 \
  -in tls/client.csr \
  -CA tls/lab-ca.crt \
  -CAkey tls/lab-ca.key \
  -CAcreateserial \
  -out tls/client.crt \
  -extfile tls/client.ext
~~~

**client.crt + client.key** là client identity. Server chỉ cần biết CA để xác minh client, không cần nắm **client.key**. Việc dùng CA lab chung không có nghĩa production nên phát cùng client certificate cho nhiều service.

### 5.5. Kiểm tra mục đích và hostname

~~~bash
openssl x509 -in tls/server.crt -noout -text
openssl x509 -in tls/client.crt -noout -text

openssl verify -CAfile tls/lab-ca.crt \
  -purpose sslserver -verify_hostname localhost tls/server.crt

openssl verify -CAfile tls/lab-ca.crt \
  -purpose sslclient tls/client.crt
~~~

Thông thường kết quả hai lệnh verify sẽ có **tls/server.crt: OK** và **tls/client.crt: OK**. Output cụ thể phụ thuộc phiên bản OpenSSL. Hãy đọc **SAN**, EKU, Issuer, validity và không in private key ra log.

## 6. Demo Spring Boot: cấu hình PEM và yêu cầu client certificate

### 6.1. Project

Khởi tạo Spring Boot Maven project với:
- Java 17, group **com.example**, artifact **mtls-server-demo**.
- Package **com.example.mtlsserver**.
- Dependencies **Spring Web** và **Spring Boot Starter Test**.
- Embedded Tomcat từ spring-boot-starter-web.

Cây file:

~~~text
mtls-server-demo/
  pom.xml
  mvnw
  mvnw.cmd
  tls/
    lab-ca.crt
    lab-ca.key
    server.crt
    server.key
    client.crt
    client.key
  src/main/java/com/example/mtlsserver/
    MtlsServerApplication.java
    SecurePingController.java
  src/main/resources/
    application.yml
~~~

**tls/** trong project chỉ để demo. Khi deploy, nên **mount certificate/private key ở đường dẫn bên ngoài JAR** với quyền tối thiểu, không dùng root CA private key trên application server.

### 6.2. pom.xml đầy đủ

~~~xml
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
    <artifactId>mtls-server-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

Version cố định để trình bày API của Spring Boot 3.3; dự án thật nên chọn phiên bản được duy trì và kiểm soát lỗ hổng bảo mật, không pin các thành phần Tomcat/SSL tách rời BOM tùy tiện.

### 6.3. Main class

**src/main/java/com/example/mtlsserver/MtlsServerApplication.java**

~~~java
package com.example.mtlsserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MtlsServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(MtlsServerApplication.class, args);
    }
}
~~~

### 6.4. application.yml dùng PEM trực tiếp

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: mtls-server-demo

server:
  port: 8443
  ssl:
    enabled: true
    certificate: "file:./tls/server.crt"
    certificate-private-key: "file:./tls/server.key"
    trust-certificate: "file:./tls/lab-ca.crt"
    client-auth: need
~~~

Ý nghĩa:

- **certificate** và **certificate-private-key** là **danh tính server**.
- **trust-certificate** là CA mà server dùng để xác minh **client cert**.
- **client-auth: need** bắt buộc client certificate trên inbound HTTPS connector.
- **file:./tls** phụ thuộc working directory. Chạy lệnh từ project root để path đúng.
- Port **8443** là HTTPS; ứng dụng không tự mở thêm HTTP 8080 hoặc HTTP→HTTPS redirect.

**Lưu ý:** Nếu certificate chain có intermediate, cần cung cấp chain đúng theo server/container. Demo CA ký trực tiếp leaf nên không có intermediate. Trong production, đọc kỹ chain và không chỉ chép leaf mà thiếu issuer.

### 6.5. Controller kiểm tra certificate phía client

**src/main/java/com/example/mtlsserver/SecurePingController.java**

~~~java
package com.example.mtlsserver;

import java.security.cert.X509Certificate;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class SecurePingController {
    @GetMapping("/ping")
    public Map<String, String> ping(HttpServletRequest request) {
        Object raw = request.getAttribute(
                "jakarta.servlet.request.X509Certificate");

        if (!(raw instanceof X509Certificate[] certs)
                || certs.length == 0) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED,
                    "A client certificate is required");
        }

        X509Certificate leaf = certs[0];
        return Map.of(
                "status", "ok",
                "clientSubject",
                leaf.getSubjectX500Principal().getName());
    }
}
~~~

**Jakarta Servlet 6.0** quy định attribute **jakarta.servlet.request.X509Certificate** là mảng **java.security.cert.X509Certificate[]** khi request HTTPS gắn với client certificate. Phần tử đầu tiên là leaf certificate của client. Controller hiển thị **clientSubject** để quan sát trong lab; không thực thi kiểm tra role/permission production.

Với **client-auth: need**, Tomcat đã xác minh certificate trong TLS layer trước khi request tới controller. Nếu không gửi cert, thường sẽ **không có HTTP 401 từ method**; handshake fail. Nhánh 401 nhằm phòng vệ nếu đường đi thay đổi hoặc thiếu cert attribute.

**Không dùng Subject CN như danh tính sản xuất duy nhất.** Một CA có thể cấp nhiều leaf có Subject trùng, hoặc Subject bị thay đổi khi rotate. Dùng profile phát hành certificate được kiểm soát, SAN/URI workload ID, issuer/serial/allowlist và Spring Security authorization phù hợp.

### 6.6. Chạy

Linux/macOS:

~~~bash
./mvnw clean package
java -jar target/mtls-server-demo-0.0.1-SNAPSHOT.jar
~~~

Windows CMD/PowerShell:

~~~text
mvnw.cmd clean package
java -jar target/mtls-server-demo-0.0.1-SNAPSHOT.jar
~~~

Chạy từ root project chứa **tls/**. Nếu không có wrapper dùng Maven cài sẵn với lệnh **mvn clean package**. HTTPS server sẽ lắng nghe trên **8443** theo cấu hình.

## 7. Positive và negative tests bằng curl

### 7.1. Trường hợp thành công

~~~bash
curl -i \
  --cacert tls/lab-ca.crt \
  --cert tls/client.crt \
  --key tls/client.key \
  https://localhost:8443/api/ping
~~~

- **--cacert**: client dùng để **tin và xác minh server**.
- **--cert, --key**: client trình certificate/private key cho server xác minh.
- URL dùng **localhost**, khớp DNS SAN trong server certificate.

Kỳ vọng **HTTP 200** và body JSON có:

~~~json
{"status":"ok","clientSubject":"CN=demo-client"}
~~~

**Thứ tự hai key JSON không được bảo đảm** do sử dụng Map.of. Status 200 và hai giá trị mới là phần cần quan sát.

### 7.2. Thiếu client cert

~~~bash
curl -v --cacert tls/lab-ca.crt \
  https://localhost:8443/api/ping
~~~

Khi **need** được thực thi, handshake thường thất bại vì client không trình certificate. Lỗi cụ thể có thể là **tlsv13 alert certificate required**, **bad certificate**, hoặc curl error code khác nhau theo TLS version/SSL backend. **Không kết luận phải nhận HTTP 403**: có thể chưa tồn tại request HTTP.

### 7.3. Client không tin server CA

~~~bash
curl -v \
  --cert tls/client.crt \
  --key tls/client.key \
  https://localhost:8443/api/ping
~~~

Nếu CA lab chưa nằm trong hệ thống trust mặc định của curl, kết nối thường fail ở bước **client kiểm tra certificate server**. Cách đúng là thêm **--cacert tls/lab-ca.crt**, **không dùng --insecure/-k** trong production.

### 7.4. Server không tin client CA

Tạo một CA khác, phát hành client leaf mới và thử với **--cert/--key** mới trong khi server vẫn chỉ trust lab-ca. Server phải từ chối certificate từ CA không được chấp nhận. Đây là lỗi **server truststore**, khác với thiếu **--cacert** ở client.

### 7.5. Kiểm tra handshake bằng OpenSSL

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -CAfile tls/lab-ca.crt \
  -cert tls/client.crt \
  -key tls/client.key \
  -verify_return_error
~~~

Quan sát server chain, TLS version, cipher suite và verify status. Nếu có **Verify return code: 0 (ok)** thì certificate verification đã thành công theo những kiểm tra của OpenSSL, **không tự chứng minh application authorization**. Dùng curl để kiểm tra HTTP status/body.

### 7.6. Test hostname mismatch

Server cert mẫu có SAN **DNS:localhost, IP:127.0.0.1**. Để thử hostname mismatch, truy cập qua một DNS khác trỏ tới server nhưng **không** nằm trong SAN; đừng dùng 127.0.0.1 cho bài test này vì IP đã được cho phép. Client đúng chuẩn sẽ không chấp nhận tên khác, dù CA được tin cậy.

### 7.7. Ma trận nghiệm thu

| Test | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Đúng CA và client cert | Trust server + trình client cert đúng | TLS pass, HTTP 200. |
| Không có client cert | Chỉ có --cacert | TLS fail với need. |
| Client cert CA lạ | Server truststore không có issuer | TLS fail. |
| Server CA lạ | Client truststore không có issuer | Client từ chối server. |
| Hostname sai | SAN không có DNS/IP mục tiêu | Client từ chối server. |
| Client cert hết hạn | Not After đã qua | Validation fail. |
| Sai EKU | Dùng serverAuth cert làm client | Có thể bị validation policy từ chối. |
| Cert đúng nhưng không có quyền | Client qua TLS, application deny | HTTP 403 theo policy. |
| Bypass gateway | Gọi backend không qua mTLS proxy | Phải bị chặn theo network/auth policy. |

**Điểm quan trọng:** Chỉ thấy HTTP 200 không chứng minh mTLS **bắt buộc**; cần test **không trình certificate** để phát hiện cấu hình want/none hoặc TLS termination đặt nhầm nơi.

## 8. Cách khác: PKCS12/JKS keystore và truststore

Spring Boot hỗ trợ key/trust material qua Java KeyStore. Đây là **phương án thay thế** cho PEM trực tiếp ở mục 6, không phải cấu hình bổ sung cùng lúc.

### 8.1. Tạo PKCS12 chứa server key và certificate

~~~bash
openssl pkcs12 -export \
  -name mtls-server \
  -inkey tls/server.key \
  -in tls/server.crt \
  -certfile tls/lab-ca.crt \
  -out tls/server.p12 \
  -passout pass:changeit
~~~

**server.p12** chứa private key, phải bảo vệ như **server.key**. Mật khẩu **changeit** chỉ dùng lab; production dùng secret manager, đừng hardcode vào Git hay log.

### 8.2. Tạo truststore cho client CA

~~~bash
keytool -importcert -noprompt \
  -alias lab-client-ca \
  -file tls/lab-ca.crt \
  -keystore tls/server-trust.p12 \
  -storetype PKCS12 \
  -storepass changeit

keytool -list -v \
  -keystore tls/server-trust.p12 \
  -storetype PKCS12 \
  -storepass changeit
~~~

Truststore chứa **trusted CA certificate**; không chứa **client private key**. Cấp quyền file phù hợp. Khi thay CA hoặc rotate leaf, quyết định policy trust phù hợp với số lượng workload được cấp cert.

### 8.3. Cấu hình server.ssl theo PKCS12

Thay toàn bộ phần SSL trong application.yml:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: "file:./tls/server.p12"
    key-store-type: PKCS12
    key-store-password: changeit
    key-alias: mtls-server
    trust-store: "file:./tls/server-trust.p12"
    trust-store-type: PKCS12
    trust-store-password: changeit
    client-auth: need
~~~

**key-store** giữ danh tính server; **trust-store** giữ CA xác minh client. Nếu gặp lỗi **Cannot recover key**, **Keystore was tampered with**, **alias not found**, kiểm tra password, type, PrivateKeyEntry, key alias và file path. Với private key password khác store password, cần cấu hình tương ứng.

## 9. Cách khác: SSL bundles của Spring Boot 3.3

SSL bundle là named set của identity/trust material, tiện cho việc cấu hình cùng một ứng dụng vừa là server vừa gọi downstream client. Spring Boot hỗ trợ **spring.ssl.bundle.pem** và **spring.ssl.bundle.jks**; named bundle được áp dụng cho web server qua **server.ssl.bundle**.

### 9.1. PEM bundle cho inbound server

Thay cấu hình PEM trực tiếp bằng:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        inbound-mtls:
          keystore:
            certificate: "file:./tls/server.crt"
            private-key: "file:./tls/server.key"
          truststore:
            certificate: "file:./tls/lab-ca.crt"

server:
  port: 8443
  ssl:
    bundle: inbound-mtls
    client-auth: need
~~~

**keystore của bundle** chứa server identity; **truststore của bundle** là client CA mà server tin; **server.ssl.client-auth** vẫn phải được đặt **need** nếu tất cả client phải trình cert.

**Không trộn server.ssl.bundle với các thuộc tính discrete server.ssl.key-store, server.ssl.certificate hay trust-certificate**. Tài liệu Spring Boot 3.3 nêu hai cách này không được dùng chung. Khi dùng bundle, cấu hình protocol/cipher có option riêng trong bundle; đừng tin rằng tất cả thuộc tính trực tiếp vẫn được áp dụng.

### 9.2. JKS/PKCS12 bundle

Nếu dùng file .p12 từ mục 8:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        inbound-mtls:
          key:
            alias: mtls-server
          keystore:
            location: "file:./tls/server.p12"
            password: changeit
            type: PKCS12
          truststore:
            location: "file:./tls/server-trust.p12"
            password: changeit
            type: PKCS12

server:
  port: 8443
  ssl:
    bundle: inbound-mtls
    client-auth: need
~~~

Đây là một **alternative riêng**. Không đồng thời đăng ký một PEM bundle cùng tên lẫn JKS bundle rồi suy đoán cái nào được dùng.

### 9.3. SSL bundle không phải CA service

SSL bundle quản lý cách nạp key/truststore, tạo SSLContext/KeyManager/TrustManager. Nó **không tự cấp phát, gia hạn, thu hồi, xác thực role hay ngăn spoof header**. Cần phối hợp PKI, secret management và security filter.

Spring Boot có cơ chế **reload-on-update** cho PEM bundle và một số consumer tương thích như Tomcat/Netty; không mặc định mọi outbound client hoặc mọi connection đang sống đều được reload ngay. Khi rotate cần test với implementation thực tế.

## 10. Khi Spring Boot là HTTP client gọi service cần mTLS

Phần **server.ssl.\*** chủ yếu cấu hình **inbound connector**. Nếu Spring Boot service A gọi service B qua HTTPS mTLS, **RestClient/WebClient của A không tự sử dụng server SSL identity**. A cần một **client keystore** của chính A và một **truststore** để xác minh B.

### 10.1. Outbound SSL bundle

Trong cấu hình ứng dụng gọi downstream:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        partner-outbound:
          keystore:
            certificate: "file:./tls/client.crt"
            private-key: "file:./tls/client.key"
          truststore:
            certificate: "file:./tls/lab-ca.crt"
~~~

**keystore** ở đây là client cert/key trình cho service B; **truststore** là CA xác minh server B. Trong hệ thật hai CA có thể khác nhau.

### 10.2. RestClientSsl trong Spring Boot 3.3

Ví dụ class hoàn chỉnh để đưa vào một Spring Boot 3.3 + Spring Web project **đã cấu hình bundle partner-outbound**:

~~~java
package com.example.mtlsserver;

import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PartnerClient {
    private final RestClient client;

    public PartnerClient(RestClient.Builder builder,
                         RestClientSsl ssl) {
        this.client = builder
                .baseUrl("https://localhost:8443")
                .apply(ssl.fromBundle("partner-outbound"))
                .build();
    }

    public String checkPartner() {
        return client.get()
                .uri("/api/ping")
                .retrieve()
                .body(String.class);
    }
}
~~~

Class này **biên dịch được** trong project nêu trên, nhưng không tự thực hiện outbound request nếu không có code gọi **checkPartner()**. Dùng local server làm downstream chỉ để thực hành. Spring Boot **3.3** có lớp **RestClientSsl** ở package **org.springframework.boot.autoconfigure.web.client**; kiểm tra package với major version khác.

Spring Boot cũng có **SslBundles** và **SslBundle.createSslContext()** nếu cần cấu hình SSLContext cho library khác. Tuy nhiên, khi có tích hợp sẵn của RestClient/WebClient, ưu tiên API framework hơn việc viết TrustManager tùy tiện.

**Không tạo “trust-all” TrustManager** hoặc HostnameVerifier luôn true để bỏ qua lỗi certificate. Cần sửa truststore, chain, SAN và certificate profile.

## 11. Authentication và authorization sau khi qua mTLS

### 11.1. “Trusted CA” không phải “Authorized client”

Nếu một CA phát hành client cert cho **service-a** và **service-b**, cả hai có thể pass TLS nếu server chỉ kiểm tra chain về CA đó. Nhưng service-a có thể được đọc dữ liệu, trong khi service-b không được xóa dữ liệu. Server vẫn phải phân quyền cụ thể:

~~~text
TLS handshake:
    client presents certificate
       -> validate signature, chain, validity, usage, trust CA
       -> connection accepted
                      |
                      v
Application security:
    verified certificate -> service principal
       -> lookup identity/roles/tenant
       -> authorize route and resource
       -> permit (2xx) or deny (403)
~~~

Trong production, dùng **Spring Security X.509 authentication** hoặc một lớp identity mapping được thiết kế, kết hợp **UserDetailsService**, custom authentication và policy phù hợp. Không tự grant ADMIN vì Subject CN bằng một chuỗi mà bên cấp phát không kiểm soát chặt chẽ.

### 11.2. Xác định danh tính tốt hơn CN

Các phương án có thể là **URI SAN** theo workload identity, SPIFFE ID, DNS SAN dành cho service, fingerprint/serial+issuer hoặc identity được CA cấp theo profile. Cần xem policy phát hành có bảo đảm không trùng danh tính và thay đổi khi revoke/rotate hay không. Quyền nên ràng buộc với principal được chuẩn hóa và được audit.

### 11.3. HTTP status không thay TLS alert

- **TLS handshake fail:** không có HTTP request hoàn tất; thường curl/OpenSSL báo TLS error.
- **401 Unauthorized:** kết nối đã qua TLS nhưng chưa có application authentication thích hợp.
- **403 Forbidden:** ứng dụng đã xác định principal nhưng deny quyền.
- **200 OK:** ứng dụng xử lý thành công; **không chứng minh mTLS bắt buộc** nếu chưa làm negative tests.

Không viết @ControllerAdvice để bắt lỗi handshake từ embedded Tomcat như exception controller thông thường.

## 12. Reverse proxy, API gateway, ingress và service mesh

### 12.1. Spring Boot terminate TLS trực tiếp

~~~text
Client -- mTLS --> Spring Boot embedded Tomcat
                     server.ssl.client-auth=need
                               |
                               v
                            Controller
~~~

Khi đó server.ssl settings kiểm soát chính TLS connector nhận request.

### 12.2. TLS kết thúc tại ingress

~~~text
Client -- mTLS --> Ingress/API Gateway -- HTTP/TLS --> Spring Boot
                          |
                          +-- verify client certificate
                          +-- map verified service identity
                          +-- forward trusted identity context
~~~

Khi HTTPS/mTLS **kết thúc ở proxy**, Spring Boot **không trực tiếp xác minh client certificate gốc**. Bật **server.ssl.client-auth=need** trong backend chỉ ảnh hưởng connector TLS của backend (nếu backend nhận TLS), không tự bảo vệ **client→ingress**. Muốn mTLS tại edge phải cấu hình ingress/gateway.

### 12.3. Certificate header có thể bị giả

Header như **X-Forwarded-Client-Cert** hoặc **X-SSL-Client-Cert** là **text do một hop gửi**, không tự chứng minh peer đã qua mTLS. Gateway cần **xóa/ghi đè header từ client ngoài**, chỉ truyền identity sau khi certificate được xác minh và kết nối backend được bảo vệ. Backend nên không thể bị gọi trực tiếp từ mạng công cộng để bypass gateway. Khi cần độ tin cậy cao, dùng identity assertion có xác thực/chữ ký, network policy hoặc mTLS thêm giữa gateway và backend.

### 12.4. Service mesh

Service mesh có thể enforce mTLS tại sidecar/proxy và truyền workload identity. App Spring Boot vẫn cần authorization theo tài nguyên và hiểu **peer TLS thực tế là sidecar hay client gốc**. Tránh cấu hình hai tầng mTLS trùng lặp chỉ vì tên gọi giống nhau mà không kiểm tra topology.

### 12.5. Actuator/management port

Nếu management server sử dụng port khác, có thể có **management.server.ssl** riêng. Đừng mặc định TLS/mTLS trên main port cũng áp dụng tương đương cho listener khác. Health checks, management routes, service-to-service ingress cần được phân vùng theo network policy và authentication thực sự.

## 13. mTLS và HTTP/2

mTLS là **xác thực và mã hóa ở lớp TLS**; HTTP/2 là giao thức HTTP được thương lượng thường qua **ALPN** trên HTTPS. Một kết nối có thể pass mTLS nhưng chạy HTTP/1.1; ngược lại thương lượng h2 không chứng minh client certificate đã được yêu cầu.

Bật HTTP/2 trong Spring Boot:

~~~yaml
server:
  http2:
    enabled: true
~~~

Đây là cấu hình **bổ sung** trên một server đã có SSL/mTLS. Java 17 và embedded Tomcat hiện đại hỗ trợ ALPN; client, proxy, protocol/cipher và connector quyết định HTTP/2 có được chọn không.

Thử:

~~~bash
curl -V
curl --http2 -v \
  --cacert tls/lab-ca.crt \
  --cert tls/client.crt \
  --key tls/client.key \
  https://localhost:8443/api/ping
~~~

**curl -V** cho biết binary có hỗ trợ HTTP/2 không. Nếu h2 được thương lượng, verbose/response thường thể hiện **HTTP/2** và ALPN h2. Nếu không, một request HTTP/1.1 vẫn có thể dùng mTLS đúng. Không thay CA/truststore khi lỗi thực ra là HTTP/2 negotiation.

Với TLS 1.2/TLS 1.3, kiểm tra enabled protocols/ciphers theo Java/container và security policy. Khi dùng SSL bundle, đặt options phù hợp trong bundle thay vì nghĩ mọi server.ssl.ciphers/protocol override chắc chắn có tác dụng.

## 14. Rotation, revocation và quản lý bí mật

### 14.1. Certificate lifecycle

Một hệ thống mTLS production cần:
1. Cấp cert riêng theo workload/service; không chia sẻ một private key cho tất cả service.
2. Giới hạn tuổi thọ certificate, SAN, EKU, CA path, thuật toán và quyền cấp phát.
3. Lưu private key trong secret manager/HSM/mounted secret an toàn; không trong Git, log hoặc JAR.
4. Theo dõi Not After và cảnh báo trước expiration.
5. Rotation client/server leaf theo lịch, phối hợp với connection pooling/keepalive.
6. Có playbook đổi CA/trust root và rollback khi rollout sai.
7. Thu hồi credential khi key lộ hoặc service không còn được phép hoạt động.
8. Giám sát TLS failures mà không log private key, token hay thông tin nhạy cảm quá mức.

### 14.2. Đổi CA không làm rớt traffic

Nếu đổi root hoặc intermediate CA, cách tiếp cận an toàn thường là **overlap trust** tạm thời:

~~~text
Bước 1: phân phối CA mới vào truststore bên xác minh
Bước 2: cấp và rollout leaf certificate mới
Bước 3: xác nhận tất cả client/server sử dụng chain mới
Bước 4: thu hồi/remove CA cũ theo lịch
~~~

Đừng xóa CA cũ khi còn workload đang dùng cert cũ; cũng không giữ vô hạn CA quá rộng vì sợ downtime.

### 14.3. Reload SSL bundle

Spring Boot có **reload-on-update** cho PEM bundle và một số consumer tương thích, tài liệu nêu Tomcat/Netty. Nhưng thay file cert/key không bảo đảm mọi kết nối cũ sẽ chuyển ngay: connection pooling, TLS session resumption, file watcher và từng HTTP client có hành vi riêng. Test rotation bằng kết nối mới và cũ; đừng mặc định outbound RestClient tự reload chỉ vì bundle được định nghĩa.

### 14.4. Revocation không tự bật khi import CA

Truststore chứa root CA không nhất thiết có nghĩa **CRL/OCSP** hoặc cơ chế revoke đã được enforce theo chính sách. Với môi trường bảo mật cao, dùng short-lived cert, certificate authority service và enforcement phù hợp, kết hợp authorization và thu hồi quyền ở tầng ứng dụng.

## 15. Chẩn đoán lỗi theo đúng tầng

| Triệu chứng | Tầng nghi ngờ | Cách xử lý |
| --- | --- | --- |
| **PKIX path building failed** tại Java client | Client không tin server CA/chain | Kiểm tra truststore outbound, issuer/intermediate, chain. |
| **unable to get local issuer certificate** tại curl | Thiếu --cacert hoặc chain server không đầy đủ | Dùng CA đúng, không dùng -k. |
| **certificate required / bad certificate** | Server yêu cầu mTLS nhưng client thiếu/sai cert | Cấp client cert/key đúng, xem client-auth need. |
| **unknown_ca** phía server | Server không tin CA cấp client | Sửa server truststore, chain, CA scope. |
| **No subject alternative DNS name** | Hostname/SAN sai | Cấp lại server cert đúng SAN; không tắt verify. |
| **certificate expired / not yet valid** | Ngày hiệu lực hoặc đồng hồ lệch | Rotate cert, đồng bộ clock. |
| **unsupported_certificate / wrong EKU** | Client cert sai usage | Dùng certificate có clientAuth và profile đúng. |
| **Keystore password incorrect** | Store/key password sai | Kiểm tra PKCS12 type, secret, file path. |
| **Cannot recover key / alias not found** | PrivateKeyEntry/alias sai | keytool -list -v, kiểm tra key alias. |
| **HTTP 401 sau TLS pass** | Chưa map được principal ở ứng dụng | Xem Spring Security/verified cert attribute. |
| **HTTP 403 sau TLS pass** | Principal không có quyền | Xem scope, role, tenant authorization. |
| **Client không cert vẫn thấy 200** | want/none hoặc proxy terminate TLS | Test đường kết nối thật và client-auth policy. |
| **HTTP/2 không chạy** | ALPN/client/proxy/config HTTP/2 | Dùng curl -V, --http2, xem protocol negotiation. |
| **Local pass, deploy fail** | Đường dẫn key/secret, trust CA, SAN/proxy khác | So artifact, runtime path, listener và CA chain. |

**Cách debug có thứ tự:** đầu tiên xác định **TLS kết thúc ở đâu**; sau đó kiểm tra server identity, client identity, trust material hai phía, SAN/EKU/validity, client-auth mode; cuối cùng mới xem Spring MVC/Spring Security authorization. Không sửa bừa HTTP controller khi request chưa tới đó.

Trong môi trường dev có thể bật TLS debug của JVM:

~~~bash
java -Djavax.net.debug=ssl,handshake \
  -jar target/mtls-server-demo-0.0.1-SNAPSHOT.jar
~~~

Log có thể chứa thông tin certificate và handshake rất chi tiết; chỉ bật tạm thời, tránh lộ dữ liệu vào hệ thống log công khai.

## 16. Kiểm thử nào thực sự chứng minh mTLS?

**MockMvc** kiểm tra controller/security logic với mock Servlet request, **không thực hiện TLS handshake thật**. Nó có thể giúp test cách ứng dụng map verified cert/role nếu giả lập attribute/principal, nhưng **không thể chứng minh server.ssl.client-auth=need, truststore, CA chain hoặc hostname verification**.

Muốn nghiệm thu mTLS cần **HTTP integration test với embedded HTTPS server thật**, hoặc chạy JAR và dùng curl/OpenSSL. Không chỉ test positive 200; phải bao gồm no-cert, wrong-CA, wrong-hostname và authorization deny.

Test bắt buộc theo vòng đời:

- **Build:** application.yml được load đúng profile; key/cert file có thể đọc được nhưng không nằm trong artifact công khai.
- **Handshake positive:** đúng client cert/key và trust server CA → TLS pass.
- **Handshake negative:** thiếu client cert hoặc sai CA → TLS fail với need.
- **Hostname negative:** server SAN không phù hợp → client verify fail.
- **Expiry/rotation:** cert cũ và mới chuyển giao có kiểm soát; cert bị thu hồi không còn được phép.
- **HTTP policy:** cert hợp lệ nhưng principal thiếu quyền nhận 403.
- **Proxy:** backend không bị bypass, header identity không spoof được.
- **HTTP/2:** ALPN kiểm tra riêng, không đánh đồng với client authentication.

## 17. Anti-pattern cần tránh

**1. Trust-all SSLContext hoặc curl --insecure để “fix” lỗi cert.** Điều này tắt một phần xác thực peer/hostname và tạo nguy cơ MITM. Sửa CA/chain/SAN chính xác.

**2. Đưa lab-ca.key lên server.** CA private key chỉ dùng để phát hành certificate; nếu bị lộ có thể cấp chứng chỉ giả được nhiều peer tin cậy.

**3. Dùng một client key cho nhiều service.** Khó audit/rotate/revoke từng workload, blast radius lớn.

**4. Tin mọi public CA cho clientAuth.** Truststore mở rộng không kiểm soát làm nhiều client đủ điều kiện qua TLS; cần client CA có scope rõ và application authorization.

**5. Bật client-auth: want nhưng tuyên bố mọi request được mTLS bảo vệ.** Client không certificate có thể vẫn đi vào ứng dụng.

**6. Cho mọi cert có Subject CN cụ thể được quyền admin.** Subject có thể trùng, bị cấp sai hoặc thiếu liên kết với principal policy. Cần identity mapping xác thực và RBAC/ABAC.

**7. Cho phép Internet tự gửi X-Forwarded-Client-Cert.** Header không được gateway bảo vệ có thể bị spoof, không thay thế TLS handshake.

**8. Bỏ qua outbound client settings.** server.ssl chỉ điều khiển inbound; ứng dụng gọi đối tác cần cấu hình certificate/trust của HTTP client riêng.

**9. Nhầm TLS fail với HTTP 401/403.** Khi handshake fail, @ControllerAdvice thường không thể trả JSON thông thường.

## 18. Bài tập vận dụng

### Bài 1 — Need so với Want

Chạy cùng cấu hình server, chỉ đổi **client-auth: need** thành **want** trong môi trường lab; dùng curl có và không có client certificate. Giải thích vì sao want không bảo đảm chặn client không cert, kể cả nếu một controller cụ thể tự kiểm tra attribute.

### Bài 2 — Hai truststore độc lập

Lần 1: gửi client cert đúng nhưng không cung cấp server CA cho curl. Lần 2: cung cấp server CA đúng nhưng gửi client cert từ CA lạ. Giải thích phía nào từ chối và vì sao.

### Bài 3 — SAN và EKU

Cấp server cert thiếu SAN localhost và test lỗi hostname; cấp client cert chỉ có EKU serverAuth và test làm client. Không dùng curl -k hoặc bỏ verify để qua bài.

### Bài 4 — Spring Boot outbound

Cấu hình **partner-outbound** SSL bundle và tạo PartnerClient. Test trước khi thêm keystore (chỉ có truststore), sau đó thêm client certificate/private key. Giải thích tại sao server.ssl.client-auth không tự làm RestClient trình certificate.

### Bài 5 — Reverse proxy

Vẽ sơ đồ ingress mTLS + Spring Boot HTTP backend. Mô tả chỗ nào xác minh certificate, cách truyền identity tin cậy và cách chặn request ngoài giả header hoặc bypass gateway.

## 19. Checklist trước khi deploy

- [ ] Đã biết **TLS terminate tại embedded server, proxy hay service mesh**.
- [ ] Connector yêu cầu mTLS thật sự có **client-auth: need**.
- [ ] Server có certificate/private key đúng, SAN khớp hostname và EKU serverAuth.
- [ ] Server có truststore cho **client CA**, không nhầm với server keystore.
- [ ] Client có certificate/private key riêng và truststore cho **server CA**.
- [ ] Certificate chain, issuer/intermediate, validity, EKU, Key Usage đều đúng.
- [ ] Chọn một trong **PEM direct**, **PKCS12 direct** hoặc **SSL bundle**, không trộn.
- [ ] Không có private key trong Git/JAR/log; dùng secret management và quyền file.
- [ ] Certificate trust dẫn tới identity mapping và **authorization**, không tự cấp mọi quyền.
- [ ] Không dùng trust-all, -k, hostname verification disabled.
- [ ] Có rotation/revocation/expiry alerts và playbook đổi CA.
- [ ] Negative tests no-cert, wrong-CA, hostname mismatch chạy với TLS runtime thật.
- [ ] Outbound RestClient/WebClient có SSL riêng nếu gọi API mTLS.
- [ ] Proxy/header trust boundary và bypass được kiểm thử.
- [ ] HTTP/2 và ALPN kiểm chứng riêng nếu cần h2.
- [ ] Management/Actuator port được bảo vệ theo chính sách tương ứng.

## 20. Câu hỏi tự kiểm tra

**1. Keystore và truststore khác nhau ở đâu?** Keystore chứa danh tính/private key của bên sở hữu; truststore chứa CA/cert mà bên đó chấp nhận khi xác minh peer.

**2. server.ssl.trust-store trên Spring Boot server thường dùng để tin ai trong mTLS?** Tin certificate do **client** gửi tới server, không phải để server giữ private key của mình.

**3. client-auth=want có nghĩa client cert bắt buộc không?** Không. **Need** mới bắt buộc ở connector.

**4. Không gửi client cert với need thì nhận HTTP 401?** Thường không: handshake fail trước controller. HTTP 401/403 thuộc application authentication/authorization sau TLS.

**5. Gửi client cert đúng nhưng thiếu server CA ở client có chạy được không?** Client vẫn có thể từ chối server certificate. Hai chiều trust phải đúng.

**6. Có client cert được CA tin nghĩa là được vào mọi endpoint?** Không. Còn cần ánh xạ danh tính và authorize.

**7. server.ssl.bundle có dùng đồng thời server.ssl.certificate/keystore được không?** Không theo cấu hình Spring Boot tương ứng; chọn một cách khai báo SSL key/trust material.

**8. server.ssl config có làm RestClient tự gửi cert không?** Không. Outbound client cần SSL bundle/SSLContext riêng.

**9. HTTP/2 có làm mất nhu cầu truststore không?** Không. ALPN là negotiation HTTP protocol; mTLS certificate validation thuộc TLS.

**10. Khi TLS dừng ở ingress, ai kiểm tra client cert?** Ingress/gateway; backend chỉ tin danh tính đã xác minh nếu đường truyền assertion được bảo vệ.

## 21. Tài liệu chính thức

- [Spring Boot 3.3 — SSL and SSL Bundles](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html): PEM/JKS bundles, keystore, truststore, reload semantics.
- [Spring Boot 3.3 — Embedded Web Servers / Configure SSL](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): server.ssl discrete properties, bundle và HTTPS connector.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): server.ssl.client-auth, key-store, trust-store, HTTP/2.
- [Spring Boot 3.3 — RestClientSsl Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientSsl.html): RestClient + SSL bundle.
- [Jakarta Servlet 6.0 Specification](https://jakarta.ee/specifications/servlet/6.0/jakarta-servlet-spec-6.0.html): X509Certificate request attribute.
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): authentication từ certificate và principal mapping.
- [OpenSSL Verification Options](https://docs.openssl.org/3.0/man1/openssl-verification-options/): certificate purpose, hostname và chain verification.

**Tóm lại:** mTLS đòi **mỗi bên có certificate/private key riêng và một tập CA/certificate tin cậy để xác minh bên kia**. Với Spring Boot server trực tiếp terminate TLS, cần **server identity + client trust material + server.ssl.client-auth=need**; với Spring Boot HTTP client, cần cấu hình outbound SSL độc lập. Hãy kiểm chứng cả handshake thành công và handshake thất bại, đồng thời phân quyền ở tầng ứng dụng; **HTTP 200 một mình không chứng minh hệ thống đã enforce mTLS**.