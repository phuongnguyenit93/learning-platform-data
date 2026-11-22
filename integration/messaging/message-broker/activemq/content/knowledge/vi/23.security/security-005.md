# TLS, mTLS, keystore, truststore và kiểm tra danh tính máy chủ

## 1. Mục tiêu bảo mật của một kết nối JMS

Một Java producer gửi **OrderPaid** tới ActiveMQ Artemis qua mạng. Không có TLS, lưu lượng TCP có thể bị đọc hoặc thay đổi trên đường truyền; nếu client kết nối nhầm broker do DNS/proxy sai, dữ liệu nghiệp vụ có thể bị gửi đến đích không đáng tin. Bật TLS là cần thiết nhưng chưa đủ: client phải **xác thực chứng chỉ máy chủ và tên đích**, còn broker phải áp dụng **quyền JMS destination** đúng cho kết nối đã xác thực.

Ba câu hỏi độc lập:

1. **Mã hóa và toàn vẹn**: các byte trao đổi giữa Java client và broker có được bảo vệ bằng TLS không?
2. **Danh tính đầu xa**: client có thực sự đang nói chuyện với broker mang tên trong URL, với chứng chỉ do CA đáng tin cấp không? Khi dùng mTLS, broker có xác thực chứng chỉ client không?
3. **Quyền nghiệp vụ**: principal đã xác thực có quyền **send** vào queue, **consume** từ queue/topic hoặc tạo address/queue hay không?

~~~mermaid
sequenceDiagram
    participant C as Java JMS client
    participant B as ActiveMQ broker
    participant PKI as CA / Trust anchor
    C->>B: TLS ClientHello (SNI nếu phù hợp)
    B-->>C: Server certificate + chain
    C->>PKI: Kiểm tra CA, validity, EKU, SAN/hostname
    Note over C: Server identity sai: dừng handshake
    opt mTLS
        B->>C: Yêu cầu client certificate
        C-->>B: Client certificate và proof of private key
        B->>B: Xác minh chain/clientAuth
    end
    C->>B: JMS protocol và thông tin authentication
    B->>B: Authorization theo address/queue/role
    B-->>C: Chấp nhận hoặc từ chối thao tác JMS
~~~

Bài thuộc chương **Bảo mật** của module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**. Trọng tâm là cách triển khai và kiểm chứng **TLS/mTLS trên ActiveMQ Artemis và Classic**, sử dụng đúng **keystore/truststore**, **hostname verification**, và ngăn những cấu hình làm TLS chỉ còn là mã hóa mà không xác minh danh tính.

## 2. TLS một chiều và mTLS: ai chứng minh danh tính cho ai?

| Cơ chế | Client kiểm tra broker | Broker kiểm tra chứng chỉ client | Có tự cấp quyền gửi/nhận JMS? |
| --- | --- | --- | --- |
| TCP không TLS | Không | Không | Không; có thể còn JMS authentication nhưng đường truyền không mã hóa |
| **TLS một chiều** | Có: chain CA, SAN, validity, EKU | Không yêu cầu client certificate | **Không** |
| **mTLS** | Có: server certificate và SAN | Có: chain CA và mục đích **clientAuth** | **Không tự động**; cần ánh xạ identity và authorization |
| TLS qua proxy/LB | Phụ thuộc termination và kiểm tra từng hop | Phụ thuộc proxy/backend | Vẫn phải quản lý quyền broker |

**TLS một chiều**: broker có **private key + certificate chain**; client có **trust anchor** để kiểm tra certificate broker. Client vẫn có thể gửi **username/password** trong JMS authentication, nhưng chỉ qua kênh TLS đã được xác minh.

**mTLS**: ngoài những điều trên, client có **private key + client certificate**, còn broker có **truststore** tin CA ký client certificate và bật yêu cầu client authentication. Client chứng minh sở hữu private key trong handshake; private key không được gửi qua TCP.

**Không đồng nhất mTLS với JMS authorization.** Artemis bật **needClientAuth=true** giúp yêu cầu chứng chỉ TLS client, nhưng cách ánh xạ subject DN/cert identity thành user/role phụ thuộc cơ chế authentication/JAAS/security manager của broker. Vẫn yêu cầu JMS username/password cùng mTLS là một lựa chọn hợp lệ khi chính sách yêu cầu hai lớp.

## 3. Keystore, truststore và private key: tránh đảo vai trò

**Keystore** chứa private key cùng certificate/chain để một endpoint **chứng minh danh tính của chính nó**. **Truststore** chứa certificate CA hoặc trust anchors dùng để **xác minh đầu xa**, không chứa private key của đầu xa.

| Thành phần | TLS một chiều | mTLS |
| --- | --- | --- |
| Broker keystore | Broker private key + server cert + chain | **Giống TLS một chiều** |
| Broker truststore | Không bắt buộc cho client certificate | CA/trust anchors của **client certificates** |
| Client keystore | Không cần client certificate | Client private key + client cert + chain |
| Client truststore | CA/trust anchors của **server certificate** | **Giống TLS một chiều** |
| JMS username/password | Theo policy authentication của broker | Theo policy auth và certificate mapping |
| Authorization role | Phải xét riêng | Phải xét riêng |

Định dạng phổ biến: **PKCS#12 (.p12/.pfx)** và **JKS (.jks)**. PKCS#12 là lựa chọn thuận tiện trong lab Java hiện đại khi ghi rõ **keyStoreType=PKCS12** và **trustStoreType=PKCS12**; đuôi file không thay việc xác minh type thực tế.

**Không nên làm những việc sau:**

- Đặt **CA private key** vào broker/client runtime. CA private key chỉ dùng trong quy trình cấp chứng chỉ bảo mật.
- Chép private key của broker vào client truststore để “tin broker”.
- Bật trust-all hoặc tắt hostname verification để khắc phục lỗi kết nối.
- Commit keystore, password, private key hoặc secret thật lên Git.
- Dùng một client certificate chung cho mọi service nếu cần truy vết, thu hồi và phân quyền riêng.

### Chuỗi chứng chỉ

~~~text
Root CA (trust anchor trong client truststore)
   └── Intermediate CA (nếu PKI có trung gian)
        └── Broker leaf certificate
             SAN: DNS broker.example.internal / localhost
             EKU: serverAuth
             Private key: chỉ broker giữ
~~~

Client xác minh chữ ký theo chain về CA đáng tin, thời hạn và các ràng buộc certificate liên quan. Trong PKI có intermediate CA, server thường phải trình bày chain thích hợp; thiếu intermediate thường làm handshake thất bại dù client có root CA.

## 4. Kiểm tra danh tính máy chủ: CA hợp lệ vẫn có thể sai broker

Ví dụ:

~~~text
JMS URL: tcp://orders-broker.example.internal:61617
Certificate do CA tin cậy cấp cho:
    SAN = DNS:payments-broker.example.internal
~~~

Certificate có chữ ký CA hợp lệ nhưng **không đại diện cho orders-broker**. Client phải từ chối nếu hostname verification được thực thi đúng.

Cần kiểm tra:

1. **Đúng SAN DNS/IP** với hostname/IP trong URL. Không chỉ xem Subject CN.
2. **Đúng certificate chain** tới trust anchor được phép.
3. Certificate còn hạn, thuật toán và key usage/EKU phù hợp **serverAuth**.
4. **DNS alias/load balancer/failover hostname** phải khớp SAN của certificate endpoint thực sự trình bày.
5. **SNI, DNS resolution và proxy termination** phù hợp khi nhiều endpoint dùng một listener TLS.

Với URL **tcp://127.0.0.1:61617**, certificate cần **IP:127.0.0.1** trong SAN để kiểm tra theo IP. Chỉ có **DNS:localhost** không đủ cho kết nối IP literal. Với URL **tcp://localhost:61617**, cần **DNS:localhost**.

### Trust-all và verifyHost=false là nguy hiểm

Chỉ xác nhận certificate được một CA đáng tin cấp **không đủ để biết đang kết nối đúng broker**. Nếu bỏ kiểm tra tên, certificate hợp lệ cấp cho dịch vụ khác trong cùng CA có thể bị dùng để giả mạo endpoint trong một đường tấn công phù hợp.

- Bật **hostname verification ở client** và kiểm chứng bằng negative test.
- Không dùng **TrustManager** chấp nhận mọi certificate hoặc **HostnameVerifier** luôn true.
- Không dùng **verifyHost=false** trong production.
- Khi gặp **PKIX path building failed**, sửa chain/truststore/CA, không tắt verification.
- Khi gặp **No subject alternative names matching**, sửa URL DNS/IP hoặc cấp lại certificate đúng SAN.

Trong Artemis Netty connector, **verifyHost=true** giúp yêu cầu kiểm tra tên broker. Client Classic có cấu hình hostname verification theo transport/phiên bản khác nhau; phải xác minh hành vi thực tế, không mặc định chỉ có **ssl://** là tự kiểm tra SAN đúng trên mọi release.


## 5. Lab PKI: tạo CA, server certificate và client certificate

Thực hành dùng **PowerShell**, **OpenSSL 1.1.1+/3.x** và **JDK keytool**. Các file chỉ dành cho **lab cục bộ**, không dùng CA này để cấp certificate production.

### 5.1. Tạo CA cho lab

~~~powershell
New-Item -ItemType Directory -Force ".\tls-lab" | Out-Null
Set-Location ".\tls-lab"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out ca.key
openssl req -x509 -new -sha256 -days 365 -key ca.key -subj "/CN=Messaging Lab CA" -out ca.crt -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"
~~~

**ca.key là private key quan trọng nhất của lab**. Không copy nó vào broker image hoặc commit repository. CA production cần PKI/HSM và quy trình phát hành, rotation, thu hồi riêng.

### 5.2. Certificate broker với SAN và serverAuth

~~~powershell
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out broker.key
openssl req -new -sha256 -key broker.key -subj "/CN=broker.example.internal" -out broker.csr

@'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:broker.example.internal,DNS:localhost,IP:127.0.0.1
'@ | Set-Content -Encoding ascii ".\broker.ext"

openssl x509 -req -in broker.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out broker.crt -days 30 -sha256 -extfile broker.ext
~~~

Trong lab, SAN có cả **DNS:localhost** và **IP:127.0.0.1** để thử hai URL. Trong production, SAN chỉ chứa các tên endpoint cần thiết và được quản lý; không thêm SAN rộng vì tiện. Dùng certificate riêng khi các broker cần danh tính độc lập.

### 5.3. Client certificate cho mTLS với clientAuth

~~~powershell
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out client.key
openssl req -new -sha256 -key client.key -subj "/CN=inventory-worker" -out client.csr

@'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=clientAuth
subjectAltName=DNS:inventory-worker
'@ | Set-Content -Encoding ascii ".\client.ext"

openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 30 -sha256 -extfile client.ext
~~~

Client certificate dùng **clientAuth**, không cần SAN khớp broker. **CN=inventory-worker** chưa tự tạo role JMS; phải có certificate-auth mapping/security manager hoặc kết hợp JMS authentication theo chính sách.

### 5.4. Xuất PKCS#12 và tạo truststores

Password chỉ phục vụ lab; không dùng giá trị ví dụ cho môi trường thật:

~~~powershell
$env:BROKER_KEYSTORE_PASS = "lab-only-broker-pass"
$env:CLIENT_KEYSTORE_PASS = "lab-only-client-pass"
$env:TLS_TRUSTSTORE_PASS = "lab-only-trust-pass"

openssl pkcs12 -export -inkey broker.key -in broker.crt -certfile ca.crt -name broker -out broker-keystore.p12 -passout env:BROKER_KEYSTORE_PASS
openssl pkcs12 -export -inkey client.key -in client.crt -certfile ca.crt -name inventory-worker -out client-keystore.p12 -passout env:CLIENT_KEYSTORE_PASS

keytool -importcert -noprompt -alias lab-ca -file ca.crt -keystore broker-truststore.p12 -storetype PKCS12 -storepass "$env:TLS_TRUSTSTORE_PASS"
keytool -importcert -noprompt -alias lab-ca -file ca.crt -keystore client-truststore.p12 -storetype PKCS12 -storepass "$env:TLS_TRUSTSTORE_PASS"
~~~

| File | Nơi dùng | Nội dung |
| --- | --- | --- |
| **broker-keystore.p12** | Broker TLS acceptor | Broker private key và server certificate chain |
| **broker-truststore.p12** | Broker khi mTLS | CA chấp nhận client certificate |
| **client-keystore.p12** | Java client khi mTLS | Client private key và client cert chain |
| **client-truststore.p12** | Java client cả TLS/mTLS | CA chấp nhận broker certificate |
| **ca.crt** | Verify/trust distribution | Public CA certificate |
| **ca.key**, **broker.key**, **client.key** | Nơi cấp certificate có bảo vệ | Private keys; không đưa vào image/Git |

**Trong Docker**, keystore/truststore path ở broker.xml phải tồn tại **bên trong container broker**. Đường dẫn trên máy host không tự biến thành container path. Mount secrets theo quyền tối thiểu; client ở container khác phải được mount truststore/keystore tương ứng riêng. Không đặt CA private key lên broker.

### 5.5. Kiểm tra certificate/keystore

~~~powershell
openssl verify -CAfile ca.crt -purpose sslserver -verify_hostname broker.example.internal broker.crt
openssl verify -CAfile ca.crt -purpose sslserver -verify_ip 127.0.0.1 broker.crt
openssl verify -CAfile ca.crt -purpose sslclient client.crt

openssl x509 -in broker.crt -noout -text
openssl x509 -in client.crt -noout -text

keytool -list -v -keystore broker-keystore.p12 -storetype PKCS12 -storepass "$env:BROKER_KEYSTORE_PASS"
keytool -list -v -keystore client-truststore.p12 -storetype PKCS12 -storepass "$env:TLS_TRUSTSTORE_PASS"
~~~

Các lệnh verify phải thành công với cert phù hợp. Xem **Subject Alternative Name, Extended Key Usage, Not Before/Not After, issuer**, và kiểm tra broker-keystore có **PrivateKeyEntry**, truststore có **trustedCertEntry**.

Negative test certificate:

~~~powershell
openssl verify -CAfile ca.crt -purpose sslserver -verify_hostname wrong.example.internal broker.crt
~~~

Lệnh này phải thất bại vì hostname mismatch. Tuy nhiên, phép verify offline **chưa chứng minh JMS client đang bật hostname verification**; cần negative test kết nối trực tiếp ở mục sau.

### 5.6. Trust anchor, chain và thu hồi

Một truststore chứa CA public certificate giúp xây chain. Nó không tự bảo đảm Java/provider đã bật revocation check **CRL/OCSP**; phải thiết kế và kiểm chứng theo PKI/tầng TLS cụ thể.

Khi certificate client bị lộ:

- Thu hồi/đổi client certificate và private key theo quy trình PKI.
- Nếu broker tin cả CA ký nhiều clients, gỡ một user ở authorization mapping có thể cần thiết; xóa toàn CA ảnh hưởng mọi client dùng CA đó.
- Không chỉ thay JMS password nếu key/certificate vẫn còn quyền truy cập theo mô hình cert-based auth.
- Theo dõi expiry và rotation trước hạn để tránh outage đồng loạt.


## 6. Cấu hình TLS một chiều và mTLS ở Artemis broker

Artemis dùng **Netty acceptor** để lắng nghe các kết nối JMS/Core/AMQP tùy cấu hình. Trong **broker.xml**, tùy chọn **sslEnabled=true** bật TLS trên acceptor; broker cần **keyStorePath**, **keyStorePassword** và đúng **keyStoreType**.

### 6.1. Acceptor TLS một chiều

Đoạn sau nằm bên trong phần **acceptors** của broker.xml hiện có, không phải toàn bộ file:

~~~xml
<acceptor name="secure-oneway">tcp://0.0.0.0:61617?sslEnabled=true;keyStorePath=/run/secrets/mq/broker-keystore.p12;keyStorePassword=lab-only-broker-pass;keyStoreType=PKCS12</acceptor>
~~~

Đây là **giá trị mật khẩu lab được viết trực tiếp để minh họa**, tuyệt đối không làm vậy ở production. Dùng secret injection/credential store, quyền OS và cơ chế cấu hình hỗ trợ của release thực tế. Nếu nhận chứng chỉ từ PKI production, path trong ví dụ phải được thay bằng file certificate đúng của broker.

Ý nghĩa:

- **0.0.0.0** là địa chỉ bind server, **không phải tên mà client dùng để xác minh danh tính**.
- **61617** là cổng TLS của lab; dùng cổng tùy quy hoạch, firewall và container port mapping.
- **sslEnabled=true** yêu cầu handshake TLS thay vì protocol JMS plaintext.
- **keyStorePath** trỏ tới file PKCS#12 **có private key** của broker.
- **keyStoreType=PKCS12** khai báo type; password phải mở được store/key theo cấu hình.
- Không cấu hình **needClientAuth=true** trong acceptor này, nên nó **không bắt buộc** client certificate.

**TLS ở đây không thay thế JMS authentication**. Broker vẫn phải xác thực user và thực thi permission gửi/nhận theo security manager/JAAS/các role của hệ thống.

### 6.2. Acceptor mTLS

Bật yêu cầu client certificate và truststore ở broker:

~~~xml
<acceptor name="secure-mtls">tcp://0.0.0.0:61618?sslEnabled=true;keyStorePath=/run/secrets/mq/broker-keystore.p12;keyStorePassword=lab-only-broker-pass;keyStoreType=PKCS12;trustStorePath=/run/secrets/mq/broker-truststore.p12;trustStorePassword=lab-only-trust-pass;trustStoreType=PKCS12;needClientAuth=true</acceptor>
~~~

**needClientAuth=true** yêu cầu client gửi certificate hợp lệ được broker trust. Nếu client không có cert hoặc không chứng minh được chain, kết nối TLS phải thất bại; **wantClientAuth=true** chỉ yêu cầu nếu có nhưng không bảo đảm bắt buộc nên không thay cho cấu hình mTLS bắt buộc.

Với certificate client có **clientAuth**, broker truststore tin CA ký client cert và xác minh chain theo TLS stack. **Tên CN/SAN của client không tự động trở thành quyền send/consume**. Để certificate xác định principal trong Artemis cần cấu hình authentication/certificate DN mapping cụ thể trong security subsystem; với lab này vẫn dùng JMS user/password để có một lớp authentication rõ ràng bên trên mTLS.

### 6.3. Tránh cấu hình TLS “nửa chừng”

| Sai sót | Hệ quả | Sửa thế nào |
| --- | --- | --- |
| Chỉ đặt **sslEnabled=true**, không có broker private key | Handshake không tạo được server identity | Broker keystore chứa PrivateKeyEntry và chain |
| Truststore client chứa CA sai | Client không tin server | Import đúng issuing CA/trust anchor |
| Bật needClientAuth nhưng không cấu hình truststore broker | Không xác minh được client theo policy hoặc dùng default trust ngoài ý muốn | Truststore broker cụ thể chứa CA client được phép |
| Dùng wantClientAuth thay vì needClientAuth | Client không cert vẫn có thể nối | Dùng needClientAuth=true nếu bắt buộc |
| Expose cả cổng TLS và plaintext cho toàn mạng | Ứng dụng có thể đi đường không TLS | Giới hạn plaintext vào môi trường/đường quản trị được phép, ưu tiên TLS cho mọi truy cập mạng |
| Đặt private key trong container image | Mất bí mật khóa, khó rotation | Mount secrets chỉ đọc, bảo vệ OS permissions |
| Cho mọi cert do CA ký vào cùng role admin | Một client cert bị lộ có quá nhiều quyền | Principal mapping và least-privilege JMS authorization |

Một TLS listener có thể cấu hình thêm **TLS protocols/cipher suites** theo phiên bản Artemis/JDK. Ưu tiên **TLS 1.2/1.3** và bộ mã hiện đại theo chuẩn tổ chức; không sao chép cứng một cipher list từ máy khác vì JDK/provider có tập cipher khác và có thể làm tất cả handshake thất bại. Không mở **TLS 1.0/1.1** để chữa lỗi client quá cũ; nâng client.

### 6.4. Đường đi qua load balancer hoặc proxy

~~~text
Client ──TLS──> Proxy/LB ──TCP hoặc TLS──> Artemis broker
~~~

Nếu proxy **terminate TLS**, nó là endpoint trình bày certificate mà client kiểm tra. Giữa proxy và broker phải có policy rõ: mạng tin cậy riêng hay TLS riêng (nên mã hóa và xác minh danh tính từng hop với dữ liệu nhạy cảm). **mTLS ở client–proxy không tự trở thành mTLS ở proxy–broker**. Nếu cần broker biết identity client, phải có thiết kế delegation/certificate forwarding đáng tin cậy, không tin bừa một header do client gửi.

Với nhiều broker sau LB, certificate của **mọi endpoint mà client có thể kết nối trực tiếp khi failover** phải hợp lệ cho hostname dùng trong URI tương ứng. Nếu URL dùng DNS alias LB, endpoint được TLS kiểm tra phải trình bày certificate có SAN hợp lệ cho alias đó.

## 7. Java/JMS Artemis: bật verifyHost và truststore trước khi kết nối

Ví dụ dùng **JDK 17+**, **Jakarta Messaging**, dependency **org.apache.activemq:artemis-jakarta-client** tương thích broker. Thực hành trên cổng **61617 cho TLS một chiều** hoặc **61618 cho mTLS**. Client cần:

- **TLS một chiều**: client truststore để tin CA broker, **verifyHost=true**.
- **mTLS**: thêm client keystore và private key; broker cũng cần needClientAuth=true + broker truststore.
- **JMS authentication**: user/password nếu broker yêu cầu. Certificate validation không tự xác nhận quyền gửi JMS.

### 7.1. Maven tối giản

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab.messaging</groupId>
    <artifactId>artemis-tls-client-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.42.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Bản client dùng để minh họa API; khi đưa vào hệ thống cần chọn một bản Artemis/JDK có tương thích và hỗ trợ bảo mật. Đừng gắn client **javax.jms** của ActiveMQ Classic 5.x vào project đang import **jakarta.jms**.

### 7.2. Cấu hình JSSE default SSLContext an toàn

Để tránh nhúng **truststorePassword/keyStorePassword** trực tiếp vào URI được log, ví dụ này đặt JVM JSSE properties **trước khi TLS context được khởi tạo**, rồi chọn **useDefaultSslContext=true** trên Artemis connector. Tên host/cổng được lấy từ **BROKER_HOST/BROKER_PORT**; mTLS bật qua **TLS_MODE=mtls**.

Tạo **src/main/java/SecureJmsProbe.java**:

~~~java
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Locale;
import java.util.Objects;
import java.util.UUID;

public final class SecureJmsProbe {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault(
                "BROKER_HOST", "localhost");
        String port = System.getenv().getOrDefault(
                "BROKER_PORT", "61617");
        String mode = System.getenv().getOrDefault(
                "TLS_MODE", "tls").toLowerCase(Locale.ROOT);

        if (!mode.equals("tls") && !mode.equals("mtls")) {
            throw new IllegalArgumentException(
                    "TLS_MODE must be tls or mtls");
        }

        // Set trước khi JSSE default SSLContext được init.
        System.setProperty("javax.net.ssl.trustStore",
                required("TLS_TRUSTSTORE"));
        System.setProperty("javax.net.ssl.trustStorePassword",
                required("TLS_TRUSTSTORE_PASS"));
        System.setProperty("javax.net.ssl.trustStoreType", "PKCS12");

        if (mode.equals("mtls")) {
            System.setProperty("javax.net.ssl.keyStore",
                    required("TLS_KEYSTORE"));
            System.setProperty("javax.net.ssl.keyStorePassword",
                    required("TLS_KEYSTORE_PASS"));
            System.setProperty("javax.net.ssl.keyStoreType", "PKCS12");
        }

        // Semicolon-separated Netty connector parameters của Artemis.
        String url = "tcp://" + host + ":" + port
                + "?sslEnabled=true"
                + ";verifyHost=true"
                + ";useDefaultSslContext=true";

        String brokerUser = required("BROKER_USER");
        String brokerPassword = required("BROKER_PASSWORD");

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        try (JMSContext jms = factory.createContext(
                brokerUser, brokerPassword)) {
            Queue queue = jms.createQueue("lab.secure.orders");
            String eventId = "tls-probe-" + UUID.randomUUID();

            jms.createProducer().send(
                    queue, "OrderPaid:" + eventId);

            System.out.println(
                    "TLS identity verified; JMS send succeeded; eventId="
                    + eventId + ", mode=" + mode);
        }
    }

    private static String required(String name) {
        return Objects.requireNonNull(
                System.getenv(name), "Missing environment: " + name);
    }
}
~~~

**Ý nghĩa các tham số:**

- **sslEnabled=true** yêu cầu Artemis client bắt tay TLS trên kết nối.
- **verifyHost=true** yêu cầu kiểm tra hostname/IP server theo endpoint đã cấu hình.
- **useDefaultSslContext=true** cho phép Netty connector dùng **SSLContext.getDefault()**, trong đó JSSE properties vừa được thiết lập cung cấp truststore và, khi mTLS, client keystore.
- **TLS_MODE=tls** không thiết lập client keystore. Broker acceptor TLS một chiều phải **không yêu cầu client certificate**.
- **TLS_MODE=mtls** cấu hình cả client keystore. Broker acceptor mTLS phải bật **needClientAuth=true** và trust CA client.

**Lưu ý quan trọng:** JSSE default context có thể được cache ngay từ lần sử dụng đầu tiên trong JVM. Ví dụ là một **CLI process riêng** và đặt system properties trước khi xây factory; trong Spring Boot hoặc JVM sống lâu, nên thiết lập từ startup/secret configuration trước khi SSLContext được dùng, hoặc tạo SSLContext riêng theo API client phù hợp. **Không thay JSSE system properties giữa chừng trong JVM có nhiều JMS consumers rồi mong mọi connection cập nhật tự động.**

Bài demo dùng JMS username/password để tách **TLS identity** khỏi **JMS principal**. Nếu broker đã được cấu hình certificate-only authentication thật sự, logic tạo context và mapping phải được điều chỉnh tương ứng; không tự suy certificate là đủ quyền khi security manager vẫn đang yêu cầu credentials.

### 7.3. Chạy thử TLS một chiều

Sau khi broker acceptor **61617** đang hoạt động, copy/trỏ client-truststore.p12 đến vị trí Java process đọc được. Trên PowerShell trong Maven project:

~~~powershell
$env:BROKER_HOST = "localhost"
$env:BROKER_PORT = "61617"
$env:BROKER_USER = "artemis_app"
$env:BROKER_PASSWORD = "<your-jms-password>"
$env:TLS_MODE = "tls"
$env:TLS_TRUSTSTORE = "C:/lab/activemq-tls/client-truststore.p12"
$env:TLS_TRUSTSTORE_PASS = "lab-only-trust-pass"

mvn -q compile exec:java "-Dexec.mainClass=SecureJmsProbe"
~~~

Đây là đường dẫn file **ví dụ**: nếu theo mục 5 tạo trong thư mục **tls-lab**, hãy dùng **đường dẫn tuyệt đối thực tế** tới file đó. Không cần client-keystore ở chế độ TLS một chiều.

Kỳ vọng: TLS handshake thành công vì **SAN có DNS:localhost** và client trust CA; sau đó **JMS send** chỉ thành công nếu user có quyền send vào queue **lab.secure.orders** và queue đã tồn tại hoặc broker cho phép tạo. Một lỗi authorization sau TLS **không có nghĩa TLS handshake thất bại**.

### 7.4. Chạy mTLS

Đổi sang cổng acceptor mTLS **61618**, thêm client-keystore và password:

~~~powershell
$env:BROKER_PORT = "61618"
$env:TLS_MODE = "mtls"
$env:TLS_KEYSTORE = "C:/lab/activemq-tls/client-keystore.p12"
$env:TLS_KEYSTORE_PASS = "lab-only-client-pass"

mvn -q compile exec:java "-Dexec.mainClass=SecureJmsProbe"
~~~

Nếu broker cần client cert và trust đúng CA, kết nối mTLS có thể thành công. Tuy nhiên **broker JMS authorization vẫn phải cấp đúng quyền** cho principal. Khi thử client mTLS thiếu keystore, phải khởi tạo **một tiến trình Java mới** (không giữ SSLContext cũ) để chắc chắn test đúng việc thiếu certificate.

### 7.5. Spring Boot JMS dùng cùng nguyên tắc

Spring Boot với Artemis có thể đặt broker URL TLS trong cấu hình ứng dụng:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: "tcp://localhost:61617?sslEnabled=true;verifyHost=true;useDefaultSslContext=true"
~~~

Ví dụ chỉ mô tả phần URL; user/password dùng environment hoặc secret theo quy ước Spring Boot. Nếu chạy trong container, **localhost** sẽ là container đó chứ không phải broker khác. Hostname thực tế phải khớp SAN của endpoint.

Với Spring JMS **@JmsListener**, connection factory được Spring quản lý, nhưng TLS verification vẫn thuộc **JMS provider/JSSE**. **@JmsListener không tự bật mTLS**, và trạng thái container **isRunning()** không chứng minh TLS handshake đã thành công; cần kiểm tra log handshake và consumer count tại broker.


## 8. ActiveMQ Classic: SSL Transport khác Netty TLS của Artemis

ActiveMQ Classic 5.x sử dụng **SSL Transport** với URL thường có dạng **ssl://**, trong khi Artemis ở ví dụ dùng **tcp://** cộng Netty option **sslEnabled=true**. Không hoán đổi hai URI hoặc thuộc tính SSL của hai broker.

### 8.1. Broker Classic: sslContext và SSL connector

Các đoạn sau đặt **trong broker element của activemq.xml hiện hữu**, không phải file cấu hình hoàn chỉnh. Classic thường dùng Spring/XBean SSL context:

~~~xml
<sslContext>
    <sslContext
        keyStore="file:/run/secrets/mq/broker-keystore.p12"
        keyStorePassword="lab-only-broker-pass"
        keyStoreType="PKCS12"
        trustStore="file:/run/secrets/mq/broker-truststore.p12"
        trustStorePassword="lab-only-trust-pass"
        trustStoreType="PKCS12"/>
</sslContext>
~~~

Định nghĩa connector trong **transportConnectors**:

~~~xml
<transportConnector name="ssl-mtls"
    uri="ssl://0.0.0.0:61619?needClientAuth=true"/>
~~~

**Giá trị mật khẩu chỉ dành cho lab.** Đường dẫn kiểu **file:** và cú pháp **sslContext** thuộc cấu hình Classic/XBean, không giống **keyStorePath** trong Artemis Netty URI. Chọn đúng phiên bản schema/Classic; nếu broker cũ không hỗ trợ store type hoặc thuật toán PKCS#12 tạo ra, cần nâng phiên bản hoặc tạo store tương thích, không tắt TLS verification.

Với TLS một chiều, dùng connector SSL không bắt buộc client certificate. Với mTLS, **needClientAuth=true** yêu cầu cert client mà server trust; **wantClientAuth** không thay thế được chính sách bắt buộc.

### 8.2. Client Classic với javax.jms

Ví dụ đoạn method trong một project Classic 5.x dùng **ActiveMQSslConnectionFactory** và **javax.jms**; code dùng **try/finally** để tương thích JMS API cũ:

~~~java
import javax.jms.Connection;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import org.apache.activemq.ActiveMQSslConnectionFactory;

public void sendClassicTls(
        String brokerUser, String brokerPassword,
        String trustStore, String trustStorePass,
        String keyStore, String keyStorePass) throws Exception {

    ActiveMQSslConnectionFactory factory =
            new ActiveMQSslConnectionFactory(
                    "ssl://broker.example.internal:61619");
    factory.setTrustStore(trustStore);
    factory.setTrustStorePassword(trustStorePass);

    // Bỏ qua client keystore nếu server chỉ yêu cầu TLS một chiều.
    if (keyStore != null) {
        factory.setKeyStore(keyStore);
        factory.setKeyStorePassword(keyStorePass);
    }

    Connection connection =
            factory.createConnection(brokerUser, brokerPassword);
    try {
        connection.start();
        Session session = connection.createSession(
                false, Session.AUTO_ACKNOWLEDGE);
        try {
            Queue queue = session.createQueue("lab.secure.orders");
            MessageProducer producer = session.createProducer(queue);
            try {
                producer.send(
                        session.createTextMessage("OrderPaid:classic-lab"));
            } finally {
                producer.close();
            }
        } finally {
            session.close();
        }
    } finally {
        connection.close();
    }
}
~~~

Keystore type, JSSE defaults và endpoint verification cần được xác minh **trên đúng Classic client/JDK release**. Đoạn trên minh họa cấu hình truststore/keyStore, **không tự chứng minh hostname verification đã bật**.

### 8.3. Hostname verification của Classic là tiêu chí bắt buộc

Không suy từ URI **ssl://** rằng client Classic đã so khớp SAN ở mọi phiên bản:

1. Kiểm tra tùy chọn **hostname verification/endpoint identification** của transport đúng bản đang dùng.
2. Bật cơ chế đó qua cấu hình được client hỗ trợ.
3. Tạo negative test với hostname **không có trong SAN** nhưng vẫn resolve tới đúng IP broker.
4. Xác minh JMS client **từ chối** kết nối do sai danh tính.
5. Nếu bản client không thể kiểm tra hostname đáng tin cậy, nâng client/transport hoặc dùng tầng TLS có endpoint verification được kiểm chứng; không chấp nhận bỏ qua SAN trong production.

SSL context của **broker** chứng minh broker có private key và certificate. **Chỉ client** có thông tin hostname mà nó định kết nối, nên broker không thể thay client thực hiện phép so khớp server hostname.

## 9. Phép thử thực tế: TLS handshake khác quyền JMS

OpenSSL giúp xác minh một số tính chất handshake; sau đó phải kiểm tra bằng **chính JMS client**. Trên broker Artemis một chiều cổng 61617:

~~~powershell
"" | openssl s_client -connect 127.0.0.1:61617 -servername localhost -CAfile ca.crt -verify_hostname localhost -verify_return_error -brief
"" | openssl s_client -connect 127.0.0.1:61617 -CAfile ca.crt -verify_ip 127.0.0.1 -verify_return_error -brief
~~~

Trên acceptor mTLS cổng 61618:

~~~powershell
"" | openssl s_client -connect 127.0.0.1:61618 -servername localhost -cert client.crt -key client.key -CAfile ca.crt -verify_hostname localhost -verify_return_error -brief
~~~

Các phép thử này chỉ kiểm tra TLS, **không phải JMS authentication hoặc authorization**. Vì OpenSSL s_client không nói giao thức JMS, server có thể đóng kết nối sau handshake; hãy xem kết quả TLS verification và broker log. Với một số TLS phiên bản, lỗi thiếu client cert có thể xuất hiện muộn trong luồng trao đổi; kiểm tra thêm bằng JMS client ở mục 7.

### Ma trận test cần chạy

| Test | Cách gây lỗi có kiểm soát | Kết quả bắt buộc |
| --- | --- | --- |
| CA tin cậy, SAN đúng | Client dùng đúng truststore/hostname | TLS handshake thành công |
| CA không tin cậy | Truststore không có CA ký broker | Lỗi PKIX/unknown CA, không gửi JMS |
| **SAN sai** | URL host khác SAN, nhưng DNS vẫn trỏ tới IP broker | **Client từ chối do hostname mismatch** |
| Broker cert hết hạn | Dùng leaf đã hết validity trong lab | TLS từ chối theo validation |
| Không có client cert tới mTLS port | TLS_MODE=tls vào 61618 | Kết nối phải thất bại |
| Client cert do CA khác ký | Broker không trust CA đó | Handshake client-auth thất bại |
| Client cert chỉ có serverAuth | Sai EKU đối với clientAuth | Bị từ chối theo validation policy |
| TLS mTLS đúng, user không được send | JMS role không cho destination | TLS thành công nhưng JMS send bị từ chối |
| TLS đúng, password JMS sai | Broker auth từ chối user | Lỗi authentication **sau TLS** |
| Client plaintext vào TLS port | Không bật SSL ở client | Handshake/protocol thất bại |

**Cách test SAN sai cho có giá trị:** trong lab, tạo DNS/hosts mapping **wrong.example.internal → 127.0.0.1**, sau đó dùng **BROKER_HOST=wrong.example.internal** với Java **SecureJmsProbe**. DNS phải resolve và TCP phải tới đúng broker; nếu DNS không resolve thì chưa kiểm chứng được hostname verification.

~~~powershell
$env:BROKER_HOST = "wrong.example.internal"
$env:BROKER_PORT = "61617"
$env:TLS_MODE = "tls"
mvn -q compile exec:java "-Dexec.mainClass=SecureJmsProbe"
~~~

**PASS của negative test** nghĩa là JMS client bị từ chối **vì SAN mismatch**, không phải “không có message” hay “hostname không resolve”. Không chuyển **verifyHost=true** thành false để “sửa” bài test.

### Phân loại lỗi theo tầng

| Biểu hiện | Tầng | Kiểm tra |
| --- | --- | --- |
| Connection refused/timeout | TCP | Host/port, firewall, broker bind, Docker mapping |
| Connection closed/packet lỗi ngay | Protocol | Plaintext vào TLS port hoặc ngược lại |
| PKIX path building failed | Trust | CA, intermediate chain, truststore, default JSSE context |
| No subject alternative names matching | Identity | Host trong URL so với DNS/IP SAN |
| Certificate expired/not yet valid | PKI | Certificate rotation, đồng hồ hai đầu |
| Certificate required / bad certificate | mTLS | Client keystore, EKU clientAuth, broker truststore |
| Keystore password incorrect | Local file | File, type, password, PrivateKeyEntry |
| JMS user not authorized | JMS authorization | User/role/destination permission |
| Lỗi sau failover | Recovery | Reconnect, SSLContext cache, transaction outcome |

Để debug sâu trên JVM, **javax.net.debug=ssl,handshake,trustmanager** có thể ghi handshake; **java.security.debug=certpath** cung cấp thêm chi tiết kiểm tra chain trong môi trường hỗ trợ. Chỉ bật tại lab hoặc tạm thời theo quy trình bảo mật, vì log có thể lộ metadata nhạy cảm và tạo lượng dữ liệu lớn.

## 10. Luân chuyển chứng chỉ và SSLContext đang chạy

Thay file keystore/truststore trên đĩa **không đồng nghĩa một JVM sống lâu sẽ tự reload nó**. JSSE default SSLContext hoặc custom context có thể đã cache KeyManager/TrustManager, và JMS Connection/Session có thể dùng TLS session cũ.

~~~text
JVM SSLContext
    └── KeyManager / TrustManager từ file cũ
         └── TLS sockets hiện hữu
              └── JMS Connection / Session / Consumer
~~~

DMLC của Spring có thể tự reconnect, nhưng nếu ConnectionFactory còn dùng SSLContext chứa key material cũ, reconnect **vẫn có thể thất bại sau rotation**.

Quy trình gợi ý:

1. Cấp certificate mới với SAN/EKU đúng, private key mới khi cần.
2. Nếu đổi CA, phân phối truststore tin **cả CA cũ và mới** trong cửa sổ chuyển đổi có kiểm soát.
3. Mount secrets mới tại broker/client, kiểm tra file permissions và certificate chain.
4. Reload hoặc restart **đúng tài nguyên SSLContext/acceptor/connection factory** theo khả năng đã kiểm chứng của release; không giả định thay file tự có hiệu lực.
5. Canary kết nối mới: kiểm tra TLS, mTLS, hostname mismatch, JMS send/consume.
6. Sau khi tất cả endpoint đã chuyển, loại trust anchor cũ theo chính sách; tránh tin CA cũ mãi.
7. Quan sát consumer count, reconnect failures, expiry dates, queue backlog và TLS errors.

**Không xoay CA/keystore của mọi broker và consumer đồng thời** nếu deployment cần rolling restart. Thiếu giai đoạn overlap trust có thể gây outage toàn cụm. Đồng thời, nếu private key bị nghi lộ, rotation có thể cần thu hồi khẩn, tách identity và hạn chế quyền chứ không chỉ đợi ngày hết hạn.


## 11. Quyền JMS và danh tính certificate phải được ràng buộc đúng

Một certificate được CA tin cậy cấp chứng minh một số thuộc tính identity của đầu kết nối. **Nó không tự cho phép đọc queue bất kỳ**. Artemis và Classic vẫn có security policy kiểm tra identity/principal và permissions đối với mỗi destination.

### Ba tầng phân quyền

~~~text
TLS server identity:
    Client kiểm tra broker SAN + trust chain

mTLS client identity:
    Broker kiểm tra client cert + clientAuth + trust chain

JMS security identity:
    Broker chọn principal rồi kiểm tra role:
      send / consume / createDurableQueue / createAddress / manage ...
~~~

Với Artemis, security manager và cơ chế authentication (ví dụ JAAS module phù hợp để nhận certificate identity) phải được cấu hình **tường minh** nếu muốn certificate subject DN xác định user/role. Nếu vẫn bật JMS username/password, bạn đang có **hai thông tin danh tính** cần được quản lý nhất quán.

Ví dụ:

| Client | Certificate identity | Role mong muốn | Quyền |
| --- | --- | --- | --- |
| order-producer | CN=order-producer | order-publisher | Send đến **orders.in**, không consume |
| inventory-worker | CN=inventory-worker | inventory-consumer | Consume **orders.in**, không quản trị broker |
| audit-consumer | CN=audit-consumer | audit-reader | Chỉ consume queue/subscription Audit |
| broker-operator | Certificate/admin identity được quản lý riêng | broker-admin | Quản trị có audit, không dùng cho worker bình thường |

Đây là **thiết kế vai trò minh họa**, không phải XML configuration đầy đủ cho Artemis security manager. Cấu hình actual principal/certificate DN mapping tùy release và hệ thống xác thực. **Đừng dùng một CA truststore rất rộng rồi coi mọi chứng chỉ do CA đó ký là user admin.**

### TLS principal không đồng nghĩa application tenant

Một client được broker chứng thực mTLS có thể vẫn gửi message với property **tenantId** sai. Không dựa vào certificate handshake để khẳng định payload/tenant authorization đã chính xác. Dùng destination permissions, tách queue/address khi cần và kiểm tra tenant/business domain tại ứng dụng.

### Chứng chỉ riêng cho mỗi service

Mỗi service nên có certificate/key riêng khi cần quản lý quyền và rotation riêng. Không dùng chung **inventory-worker.p12** cho tất cả replica thuộc những hệ thống nghiệp vụ khác nhau chỉ để tiết kiệm thao tác: khi một key lộ, mọi service dùng key đó đều bị ảnh hưởng.

## 12. Vận hành TLS và mTLS trong cluster, Docker, Spring JMS

### 12.1. Tên kết nối và danh tính broker trong HA/failover

Với cụm Artemis/Classic có nhiều broker, client có thể thử kết nối các endpoint khác nhau. Mỗi địa chỉ mà client dùng để kết nối phải được xét SAN theo danh tính đã cấu hình:

~~~text
tcp://broker-a.internal:61617 → cert có DNS:broker-a.internal
tcp://broker-b.internal:61617 → cert có DNS:broker-b.internal
tcp://mq.service.internal:61617 → endpoint TLS có DNS:mq.service.internal
~~~

Nếu traffic qua LB terminate TLS, client kiểm tra cert của LB. Nếu transport đi thẳng từng broker sau failover, client phải kiểm tra cert của **broker đó** chứ không tái sử dụng kết quả tin cậy của endpoint trước. Không bỏ hostname verification chỉ vì chuyển sang HA.

Broker-to-broker connectors cũng cần CA/truststore, server identity verification và mTLS theo threat model; đừng chỉ mã hóa client-to-broker rồi để replication/cluster traffic plaintext qua mạng không tin cậy.

### 12.2. Secret và file-system access

- Keystore chứa private key: mount **read-only**, quyền OS chỉ cho user/container có nhu cầu.
- Truststore chứa CA public cert: vẫn quản lý integrity, vì sửa truststore có thể thay đổi ai được tin cậy.
- Không build keystore/keys vào Docker image hoặc lưu mật khẩu trong Git.
- Không ghi password vào URL log hoặc exception trace. Artemis URI có thể chứa SSL passwords nếu truyền trực tiếp; ví dụ Java ưu tiên JSSE property/secret thay vì đưa password vào URL.
- Với Kubernetes, dùng secret volume/CSI hoặc secret manager theo policy, kết hợp restart/reload được kiểm chứng.
- Bảo vệ **client-keystore.p12** của worker tương tự bảo vệ một credential có thể kết nối broker.
- Không đặt **TLS_TRUSTSTORE_PASS** của lab vào production, và không để private key sinh bằng OpenSSL lab không mã hóa trên thư mục shared.

**System.setProperty("javax.net.ssl.*")** trong Java ví dụ có phạm vi **toàn JVM**. Một app dùng nhiều TLS destinations có thể vô tình tác động HTTP clients/DB/LDAP khác nếu đổi default truststore. Với service lớn, ưu tiên cấu hình SSLContext riêng hoặc cơ chế TLS settings của ConnectionFactory có phạm vi rõ, cùng secret lifecycle chuẩn; không đổi system properties sau khi SSLContext đã được tạo.

### 12.3. Bảo mật giao thức và hiệu năng

TLS handshake tiêu thụ CPU, nhưng vẫn phải bảo vệ đường truyền. Tối ưu bằng connection reuse/pooling phù hợp và đo throughput thực tế, **không tắt verification**. Với JVM hiện đại, chọn TLS 1.2/1.3, thuật toán/cipher suite theo policy và cập nhật bản vá JDK/broker.

**Không dùng STARTTLS/HTTP HTTPS như phép thay thế không phù hợp** cho cổng JMS Core/OpenWire/AMQP TLS: protocol application sau TLS vẫn phải đúng client và acceptor tương ứng. OpenSSL s_client chỉ kiểm tra handshake, không thể gửi message JMS chỉ vì TLS thành công.

## 13. Thực hành kiểm chứng và câu hỏi phân tích

### Thực hành A — TLS một chiều với broker identity hợp lệ

Cấu hình Artemis acceptor **61617**; dùng broker keystore và Java client truststore. Chạy **SecureJmsProbe** với **BROKER_HOST=localhost**, **TLS_MODE=tls**. Xác nhận:

- TLS handshake có server certificate đúng SAN.
- Client validate chain tới CA đã tin.
- JMS send được chấp nhận **chỉ khi** user được cấp quyền destination.
- Không cần client keystore nếu broker không yêu cầu mTLS.

### Thực hành B — mTLS bắt buộc

Cấu hình acceptor **61618** và **needClientAuth=true**, broker truststore chứa CA ký client cert. Chạy Java với **TLS_MODE=mtls**, client-keystore đúng. Sau đó chạy **TLS_MODE=tls** vào chính port 61618.

**PASS**: trường hợp có cert hợp lệ tiếp tục đến JMS auth/authorization; trường hợp thiếu cert không được kết nối thành công.

### Thực hành C — Đúng CA nhưng sai tên broker

Dùng DNS alias **wrong.example.internal** trỏ tới cùng IP broker lab, trong khi SAN chỉ có **broker.example.internal, localhost, 127.0.0.1**. Chạy client với **verifyHost=true**. Ghi lại lỗi hostname mismatch; không cho phép dùng verifyHost=false.

**Điểm cần lý giải:** certificate chain đúng **không đủ** để xác minh broker identity; SAN phải khớp endpoint trong URL.

### Thực hành D — Đúng TLS nhưng sai quyền JMS

Dùng mTLS và JMS user hợp lệ nhưng thiếu quyền send **lab.secure.orders**. Chứng minh TLS có thể handshake thành công, còn thao tác JMS gửi bị broker từ chối. Kiểm tra broker security logs mà không ghi private key/password vào output.

### Thực hành E — Đổi client certificate và truststore khi hệ thống đang chạy

Tạo certificate mới có EKU clientAuth và một CA thử nghiệm khác. Dùng kế hoạch rotation có hai trust anchors trong cửa sổ chuyển đổi, restart/reload đúng SSLContext/acceptor. Kiểm chứng certificate cũ/mới trong giai đoạn overlap và sự từ chối sau khi gỡ trust CA cũ. Không thử trên production hoặc xóa keys/volumes của broker dữ liệu thật.

### Thực hành F — Failover không được tắt xác minh danh tính

Chuẩn bị hai broker/endpoints test với SAN riêng, có thể dùng CA chung. Cho client chuyển endpoint khi một broker mất kết nối. Ghi nhận mỗi lần TLS handshake kiểm tra hostname tương ứng, không dùng một certificate không đúng SAN chỉ vì các broker chung cluster.

## 14. Checklist nghiệm thu cấu hình TLS/mTLS cho ActiveMQ

| Câu hỏi | Kết quả bắt buộc |
| --- | --- |
| Broker có private key và certificate chain đúng? | Broker keystore chứa PrivateKeyEntry, EKU serverAuth |
| Client tin đúng CA của broker? | Truststore chọn lọc CA, chain kiểm chứng thành công |
| URL host có khớp SAN? | **Hostname verification được bật và negative test SAN sai thất bại** |
| Kết nối bằng IP literal có đúng? | Chứng chỉ có IP SAN tương ứng; không chỉ DNS SAN |
| mTLS có bắt buộc client cert? | needClientAuth=true; test thiếu cert thất bại |
| Broker tin đúng issuing CA client? | Broker truststore phù hợp, client cert có clientAuth |
| Cert có tự cho quyền JMS không? | Không; principal mapping + authorization vẫn được kiểm tra |
| Keystore/truststore type có đúng? | PKCS12/JKS và password được kiểm chứng |
| TLS endpoint sau LB/failover có được xác minh? | Cert SAN phù hợp endpoint thực tế ở từng hop |
| Còn listener plaintext không mong muốn? | Firewall và cấu hình loại trừ đường bypass |
| Secret có an toàn? | Key/password không nằm trong Git, image, logs |
| Rotation có test reload hay restart? | SSLContext/ConnectionFactory dùng material mới, có overlap trust |
| Classic/Artemis có bị lẫn config? | ssl:// Classic khác tcp://...?sslEnabled=true của Artemis |
| Có kiểm thử trước khi triển khai? | Cả positive và negative tests TLS, mTLS, hostname và JMS role |

**Kết luận:** TLS chỉ đáng tin khi client **xác minh được đúng broker**, không chỉ mã hóa kết nối. **Keystore** chứa danh tính và private key của chính endpoint; **truststore** chứa CA/trust anchors để kiểm tra bên kia; **mTLS** bổ sung xác thực chứng chỉ client nhưng **không tự tạo quyền JMS**. Trên ActiveMQ Artemis và Classic, cần triển khai đúng SSL transport, bật/kiểm chứng hostname verification, cấp SAN/EKU chuẩn, giữ secrets an toàn và thử các trường hợp sai CA, sai SAN, thiếu client cert. Một kết nối JMS bảo mật phải **chấp nhận đúng endpoint, từ chối endpoint giả và chỉ cho phép các thao tác đã được phân quyền**.
