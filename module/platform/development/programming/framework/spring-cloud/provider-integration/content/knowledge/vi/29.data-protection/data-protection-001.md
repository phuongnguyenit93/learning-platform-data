# TLS, xác minh chứng chỉ và kết nối qua proxy

Spring Boot thường gọi dịch vụ managed qua HTTPS: Azure App Configuration, Azure Key Vault, AWS S3, Google Cloud Storage hoặc API nội bộ. HTTPS bảo vệ dữ liệu trên đường truyền, nhưng ứng dụng chỉ được bảo vệ đúng khi **xác minh chứng chỉ máy chủ**, dùng đúng trust material, xử lý proxy có chủ đích và kiểm thử cả đường kết nối thực tế.

Trong Java, TLS được thực thi bởi JSSE hoặc TLS stack của HTTP client. Spring Boot cung cấp **SSL bundles** để quản lý truststore/keystore và áp dụng chúng cho một số client được auto-configure. Tuy nhiên, AWS SDK, Azure SDK và Google Cloud client libraries có các HTTP transport và cách cấu hình proxy riêng. Vì vậy, một cấu hình TLS/proxy trong Spring không tự động áp dụng cho mọi client trong ứng dụng.

Bài học thuộc chương **Bảo vệ dữ liệu** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud, bao gồm danh tính/quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử và đánh giá khác biệt giữa cloud provider. Mục tiêu của bài là thiết lập kết nối TLS đáng tin cậy, xác minh chứng chỉ, cấu hình proxy theo từng transport và chẩn đoán lỗi mà không tắt cơ chế bảo vệ.

## 1. Mục tiêu và tình huống thực tế

Giả sử `order-service` cần:

- Gọi `https://payments.example.com` để xử lý giao dịch.
- Gọi Azure Key Vault để lấy secret.
- Gọi Amazon S3 hoặc Google Cloud Storage để đọc tài liệu.
- Đi qua proxy doanh nghiệp ở mạng nội bộ.
- Kết nối tới một API đối tác yêu cầu **mutual TLS (mTLS)**.

Sau bài học, bạn có thể:

1. Phân biệt TLS, chứng chỉ máy chủ, truststore, keystore và mTLS.
2. Giải thích quá trình xác minh certificate chain, hostname và thời hạn chứng chỉ.
3. Tạo truststore PKCS12/JKS và cấu hình Spring Boot SSL bundle bằng JKS hoặc PEM.
4. Áp dụng SSL bundle cho `RestClient`/`WebClient` và truyền `SSLContext` tới SDK nếu transport hỗ trợ.
5. Phân biệt HTTP forward proxy, HTTPS CONNECT tunnel và TLS inspection proxy.
6. Cấu hình proxy khác nhau cho Azure SDK, AWS SDK for Java 2.x và Google Cloud Java client libraries.
7. Kiểm thử TLS thành công/thất bại, xác minh proxy, xử lý certificate rotation và đọc log handshake.

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["HTTP client / cloud SDK transport"]
    B --> C["Proxy nếu có"]
    C --> D["TLS handshake với endpoint"]
    D --> E["Nhận certificate chain"]
    E --> F["Truststore: CA có được tin cậy?"]
    F --> G["Hostname/SAN có khớp?"]
    G --> H["TLS session được thiết lập"]
    H --> I["HTTP request / gRPC RPC"]
    F -->|Không| X["Handshake thất bại"]
    G -->|Không| X
~~~

**Điểm quan trọng:** proxy chỉ quyết định đường đi của request. TLS vẫn phải xác minh danh tính của endpoint theo đúng chính sách tin cậy.

## 2. TLS bảo vệ điều gì?

TLS (Transport Layer Security) cung cấp ba thuộc tính chính cho kết nối:

- **Confidentiality:** mã hóa dữ liệu trao đổi để người nghe lén không đọc được nội dung.
- **Integrity:** phát hiện dữ liệu bị thay đổi trên đường truyền.
- **Authentication:** xác minh máy chủ bằng chứng chỉ; với mTLS, máy chủ cũng xác minh client.

HTTPS là HTTP chạy trên TLS. Các dịch vụ cloud thường yêu cầu HTTPS và các phiên bản TLS hiện đại. Ví dụ, AWS SDK for Java 2.x yêu cầu JDK hỗ trợ tối thiểu TLS 1.2 và khuyến nghị TLS 1.3.

### 2.1. Server authentication

Khi Java client kết nối tới `api.partner.example`:

1. Client gửi ClientHello, gồm các phiên bản TLS, cipher suites và thông tin cần thiết để thương lượng.
2. Server phản hồi và gửi certificate chain.
3. Client kiểm tra chứng chỉ có thể xây dựng đường tin cậy tới CA nằm trong truststore.
4. Client kiểm tra thời hạn, mục đích sử dụng, chữ ký và các ràng buộc của certificate.
5. Client xác minh hostname URL khớp Subject Alternative Name (SAN) của chứng chỉ.
6. Hai bên hoàn tất handshake và tạo khóa phiên để mã hóa dữ liệu.

Nếu certificate chain hợp lệ nhưng SAN không chứa hostname đang gọi, kết nối vẫn phải thất bại. Không được bỏ qua hostname verification chỉ để kết nối thành công.

### 2.2. Certificate chain

Một chain điển hình:

~~~text
Server certificate (leaf)
       |
       v
Intermediate CA certificate
       |
       v
Root CA certificate (trust anchor)
       |
       v
Client truststore
~~~

Server thường gửi leaf certificate và các intermediate cần thiết. Client đã có root CA đáng tin cậy trong truststore để xác minh chuỗi. Nếu server thiếu intermediate hoặc client không có trust anchor cần thiết, handshake có thể báo `PKIX path building failed`.

Không nên chỉ import leaf certificate của một server vào truststore như cách chữa tạm thời. Thông thường, hãy tin cậy **CA root hoặc intermediate được tổ chức phê duyệt**. Pinning leaf certificate là một chiến lược riêng, cần kế hoạch thay thế certificate và rollback.

### 2.3. SAN, hostname và SNI

Ba khái niệm thường bị nhầm:

| Khái niệm | Vai trò |
| --- | --- |
| **SAN (Subject Alternative Name)** | Danh sách DNS/IP mà chứng chỉ được cấp cho |
| **Hostname verification** | So sánh hostname trong URL với SAN của certificate |
| **SNI (Server Name Indication)** | Client báo tên host trong handshake để server chọn certificate phù hợp |

Nếu gọi endpoint bằng IP nhưng certificate chỉ có SAN dạng DNS, xác minh hostname có thể thất bại. Nếu proxy hoặc load balancer làm sai SNI, server có thể trả certificate của virtual host khác.

Không dùng địa chỉ IP thay hostname khi endpoint được thiết kế để xác minh theo DNS, trừ khi chứng chỉ có IP SAN hợp lệ.

## 3. Truststore và keystore: hai vai trò khác nhau

| Thành phần | Chứa gì? | Dùng để làm gì? |
| --- | --- | --- |
| **Truststore** | Certificate của CA được tin cậy | Xác minh certificate của server/peer |
| **Keystore** | Private key và certificate chain của chính ứng dụng | Chứng minh danh tính client hoặc server trong mTLS |
| **Certificate chain** | Leaf và intermediate certificate | Cho peer xây dựng đường tin cậy |
| **Private key** | Khóa riêng tương ứng với certificate | Chứng minh sở hữu khóa; phải giữ bí mật |

Khi ứng dụng chỉ gọi HTTPS API thông thường, thường cần **truststore**, không cần client keystore. Khi đối tác yêu cầu mTLS, client cần **keystore** chứa certificate và private key của ứng dụng; đồng thời vẫn cần truststore để xác minh server.

### 3.1. Kết nối HTTPS một chiều

~~~text
Spring Boot client
  - Truststore: CA ký certificate của server
  - Không cần client certificate
          |
          | TLS: xác minh server
          v
HTTPS server
  - Certificate + private key của server
~~~

### 3.2. Kết nối mutual TLS

~~~text
Spring Boot client                         Partner server
  Keystore: client cert + private key        Truststore: CA ký client cert
  Truststore: CA ký server cert              Keystore: server cert + key
            |                                          |
            |---- Client xác minh server ------------>|
            |<--- Server yêu cầu client certificate --|
            |---- Client gửi certificate chain ------>|
            |<--- Server xác minh client --------------|
            |=========== TLS session ==================|
~~~

Không gửi private key trong TLS handshake. Client gửi certificate và tạo chữ ký handshake bằng private key để chứng minh mình sở hữu khóa tương ứng.

## 4. Tạo và kiểm tra truststore bằng keytool

Java cung cấp công cụ `keytool` để quản lý certificate và keystore. Ví dụ doanh nghiệp có CA nội bộ `corp-root-ca.pem` được dùng để ký certificate của proxy TLS inspection hoặc API nội bộ.

### 4.1. Xác minh certificate trước khi import

Xem thông tin certificate:

~~~bash
keytool -printcert -file corp-root-ca.pem
~~~

Hoặc OpenSSL:

~~~bash
openssl x509 -in corp-root-ca.pem -noout -subject -issuer -dates -fingerprint -sha256
~~~

Đối chiếu fingerprint với một kênh đáng tin cậy do CA/security team cung cấp. Không import một certificate chỉ vì nó xuất hiện trong lỗi handshake hoặc do một người gửi qua kênh chưa xác minh.

### 4.2. Tạo PKCS12 truststore

~~~bash
keytool -importcert \
  -alias corp-root-ca \
  -file corp-root-ca.pem \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
~~~

`keytool` sẽ yêu cầu password nếu chưa truyền. Không đặt password thật trên command line, trong script commit hoặc shell history. Xác minh nội dung:

~~~bash
keytool -list -v \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
~~~

Trong production, truststore nên được mount từ secret/configuration management hoặc đóng gói theo quy trình kiểm soát. Không đưa private key hoặc password vào Git. Certificate CA công khai không phải private key, nhưng vẫn cần xác minh nguồn và quản lý thay đổi.

### 4.3. Tạo keystore cho client mTLS

Nếu đã nhận certificate client từ CA, cần một keystore chứa **private key do client sở hữu** cùng certificate chain tương ứng. Quy trình thường gồm:

1. Sinh key pair và CSR trong keystore hoặc HSM.
2. Gửi CSR tới CA/đối tác theo quy trình.
3. Nhận certificate reply và intermediate chain.
4. Import certificate chain vào đúng alias chứa private key.
5. Kiểm tra alias, thời hạn, SAN/subject và key usage.

Ví dụ sinh key pair trong PKCS12 (chỉ dùng cho môi trường thử nghiệm):

~~~bash
keytool -genkeypair \
  -alias checkout-client \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -keystore checkout-client.p12 \
  -storetype PKCS12
~~~

Trong môi trường thực tế, chọn thuật toán/độ dài khóa theo tiêu chuẩn CA và chính sách tổ chức. Không dùng certificate tự ký trong production trừ khi mô hình trust đã được phê duyệt rõ.

## 5. Cấu hình Spring Boot SSL bundles

Spring Boot hỗ trợ **SSL bundles** để gom trust material, key material, protocol và các tùy chọn TLS dưới một tên. Một bundle có thể dùng cho server hoặc client; client HTTPS thông thường cần truststore, còn mTLS cần thêm client keystore.

### 5.1. Truststore JKS/PKCS12 cho outbound HTTPS

Ví dụ `application.yml`:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        partner-api:
          truststore:
            location: "file:/run/secrets/partner-truststore.p12"
            password: "${PARTNER_TRUSTSTORE_PASSWORD}"
            type: PKCS12
~~~

- `partner-api` là tên bundle do ứng dụng chọn.
- `location` là file truststore được mount tại runtime.
- `password` lấy từ secret management; không commit giá trị thật.
- `type: PKCS12` xác định loại keystore.

Không cần khai báo keystore nếu client không sử dụng mTLS. Khi cấu hình custom truststore, kiểm tra nó có chứa **tất cả CA cần thiết** cho endpoint mà client gọi. Một truststore riêng chỉ có CA nội bộ có thể làm các public endpoint khác không còn được tin cậy nếu client chỉ sử dụng truststore đó.

### 5.2. PEM truststore

Nếu hệ thống quản lý certificate ở dạng PEM:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        partner-api:
          truststore:
            certificate: "file:/run/secrets/partner-ca-chain.pem"
~~~

Spring Boot cũng có thể nhận PEM content trực tiếp hoặc resource location. Với file được mount, dùng URI rõ ràng như `file:/run/secrets/...`. Không nhầm certificate public với private key.

### 5.3. Outbound mTLS bằng bundle JKS/PKCS12

Nếu đối tác yêu cầu client certificate:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        partner-mtls:
          key:
            alias: checkout-client
          keystore:
            location: "file:/run/secrets/checkout-client.p12"
            password: "${CLIENT_KEYSTORE_PASSWORD}"
            type: PKCS12
          truststore:
            location: "file:/run/secrets/partner-truststore.p12"
            password: "${PARTNER_TRUSTSTORE_PASSWORD}"
            type: PKCS12
~~~

Bundle có hai vai trò:

- `keystore`: certificate và private key của client gửi cho đối tác.
- `truststore`: CA dùng để xác minh certificate của đối tác.

Private key phải được bảo vệ bằng secret management hoặc HSM phù hợp. Không mount private key vào một thư mục có quyền đọc rộng.

### 5.4. Cấu hình server yêu cầu client certificate

Khi chính Spring Boot là server và yêu cầu client mTLS, cấu hình server bundle chứa certificate/private key của server và truststore CA cấp client certificate:

~~~yaml
server:
  port: 8443
  ssl:
    bundle: inbound-mtls
    client-auth: need

spring:
  ssl:
    bundle:
      jks:
        inbound-mtls:
          key:
            alias: checkout-server
          keystore:
            location: "file:/run/secrets/server-keystore.p12"
            password: "${SERVER_KEYSTORE_PASSWORD}"
            type: PKCS12
          truststore:
            location: "file:/run/secrets/client-ca-truststore.p12"
            password: "${CLIENT_CA_TRUSTSTORE_PASSWORD}"
            type: PKCS12
~~~

`client-auth: need` yêu cầu client cung cấp certificate hợp lệ. Giá trị `want` có thể yêu cầu client certificate nhưng cho phép không gửi; `none` không yêu cầu client certificate. Cần kiểm tra chính sách authorization ở tầng ứng dụng sau khi TLS xác minh danh tính certificate; mTLS không tự động cấp quyền nghiệp vụ.

## 6. Áp dụng SSL bundle cho Spring REST clients

### 6.1. RestClient trong Spring Boot 3.5

Spring Boot cung cấp `RestClientSsl` để áp dụng bundle đã khai báo:

~~~java
package com.example.checkout;

import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class PartnerHttpConfiguration {

    @Bean
    RestClient partnerRestClient(
            RestClient.Builder builder,
            RestClientSsl ssl) {
        return builder
                .baseUrl("https://payments.example.com")
                .apply(ssl.fromBundle("partner-api"))
                .build();
    }
}
~~~

`RestClientSsl.fromBundle("partner-api")` gắn trust material của bundle vào `ClientHttpRequestFactory`. Với bundle `partner-mtls`, client có thể gửi client certificate nếu transport và cấu hình hỗ trợ.

Lưu ý: áp dụng SSL bundle có thể thay thế `ClientHttpRequestFactory` đã cấu hình trước đó. Nếu cần kết hợp proxy, timeout và SSL, hãy cấu hình một request factory phù hợp thay vì giả định tất cả customizer cũ tự được giữ lại.

### 6.2. WebClient

Với `WebClient`, Spring Boot có `WebClientSsl` để áp dụng bundle cho connector:

~~~java
package com.example.checkout;

import org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class PartnerWebClientConfiguration {

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            WebClientSsl ssl) {
        return builder
                .baseUrl("https://payments.example.com")
                .apply(ssl.fromBundle("partner-api"))
                .build();
    }
}
~~~

API import/package và connector cụ thể phụ thuộc phiên bản Spring Boot. Nếu dùng WebClient tự tạo bằng `WebClient.create()`, các auto-configuration/customizer của Spring Boot không tự áp dụng; cần cấu hình `ClientHttpConnector` tương ứng.

### 6.3. Dùng SSL bundle với client SDK tùy chỉnh

Spring Boot auto-configure bean `SslBundles`. Có thể lấy `SSLContext` từ bundle để truyền cho SDK/HTTP transport có hỗ trợ:

~~~java
import javax.net.ssl.SSLContext;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.stereotype.Component;

@Component
public class PartnerTlsContext {
    private final SSLContext sslContext;

    public PartnerTlsContext(SslBundles sslBundles) {
        this.sslContext = sslBundles.getBundle("partner-api").createSslContext();
    }

    public SSLContext sslContext() {
        return sslContext;
    }
}
~~~

Không phải SDK nào cũng nhận `SSLContext` trực tiếp. Một số SDK yêu cầu cấu hình qua Netty, Apache HttpClient, gRPC channel hoặc transport native riêng. Hãy kiểm tra builder của **đúng HTTP client implementation** mà SDK đang dùng.

**SSL bundle không phải cấu hình toàn cục cho mọi thư viện.** Nó chỉ được dùng ở những nơi bạn áp dụng bundle hoặc truyền các SSL object vào transport tương ứng.

## 7. TLS và proxy: hiểu đường đi của kết nối

Một proxy doanh nghiệp thường là **forward proxy**. Client gửi request tới proxy; proxy kết nối tới host đích theo chính sách mạng.

### 7.1. HTTP CONNECT tunnel

Với HTTPS qua HTTP proxy, client thường yêu cầu proxy tạo tunnel:

~~~text
Client -> Proxy: CONNECT payments.example.com:443
Proxy -> Client: 200 Connection Established
Client <====== TLS handshake trực tiếp với payments.example.com ======>
Client <================ HTTPS request/response =====================>
~~~

Proxy nhìn thấy hostname/port và metadata mạng, nhưng trong tunnel CONNECT thông thường, nội dung TLS được mã hóa end-to-end giữa client và server.

### 7.2. HTTPS proxy

Nếu endpoint proxy dùng HTTPS, client thiết lập TLS tới **proxy** trước. Sau đó có thể tạo tunnel TLS tới server đích. Cần phân biệt:

- Certificate của proxy: xác minh kết nối TLS tới proxy nếu proxy dùng HTTPS.
- Certificate của origin: xác minh server đích bên trong tunnel.
- Proxy authentication: xác thực client với proxy, ví dụ username/password hoặc cơ chế doanh nghiệp.

Proxy authentication và server certificate validation là hai bước khác nhau.

### 7.3. TLS inspection proxy

Một số proxy doanh nghiệp giải mã rồi mã hóa lại TLS. Khi đó:

~~~text
Client --TLS--> Corporate proxy --TLS--> Origin server
        cert do corporate CA ký
~~~

Client nhìn thấy certificate do CA nội bộ cấp cho hostname đích. Để kết nối thành công, ứng dụng cần trust CA inspection đã được security team phê duyệt.

Đây là một quyết định tin cậy quan trọng: proxy có thể đọc nội dung request/response trong phạm vi inspection. Không tự cài CA nhận được từ lỗi handshake; xác minh fingerprint và phạm vi áp dụng trước khi trust.

### 7.4. Proxy không thay thế TLS

| Thành phần | Trách nhiệm |
| --- | --- |
| Proxy | Định tuyến, kiểm soát outbound, có thể yêu cầu proxy authentication |
| TLS | Mã hóa và xác minh endpoint |
| Truststore | Xác định CA mà client chấp nhận |
| Hostname verification | Đảm bảo certificate thuộc đúng host đang gọi |
| mTLS | Xác minh cả client và server bằng certificate |

Không tắt TLS verification để proxy có thể chuyển tiếp request. Nếu proxy inspection là yêu cầu hợp lệ, cài trust anchor đúng cách và tiếp tục xác minh hostname.

## 8. Cấu hình proxy trong Java

### 8.1. Java system properties

Một số Java HTTP clients sử dụng system properties:

~~~bash
java \
  -Dhttps.proxyHost=proxy.corp.example \
  -Dhttps.proxyPort=8080 \
  -Dhttp.nonProxyHosts="localhost|127.*|*.svc.cluster.local" \
  -Djavax.net.ssl.trustStore=/run/secrets/corp-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar order-service.jar
~~~

Các thuộc tính thường gặp:

| Property | Ý nghĩa |
| --- | --- |
| `http.proxyHost`, `http.proxyPort` | Proxy cho HTTP |
| `https.proxyHost`, `https.proxyPort` | Proxy cho HTTPS trong các client hỗ trợ |
| `http.nonProxyHosts` | Danh sách host đi trực tiếp |
| `javax.net.ssl.trustStore` | Truststore mặc định cho JSSE |
| `javax.net.ssl.trustStorePassword` | Password truststore |
| `javax.net.ssl.keyStore` | Keystore mặc định cho JSSE |
| `javax.net.ssl.keyStorePassword` | Password keystore |

System properties là cấu hình **JVM-wide** cho các client dùng JSSE/default proxy behavior. Nếu ứng dụng có nhiều SDK với transport khác nhau, cấu hình global có thể không được áp dụng hoặc có thể ảnh hưởng tới client không mong muốn. Ưu tiên cấu hình per-client khi cần các chính sách khác nhau.

### 8.2. Environment variables

Một số SDK/client hỗ trợ:

~~~bash
export HTTP_PROXY="http://proxy.corp.example:8080"
export HTTPS_PROXY="http://proxy.corp.example:8080"
export NO_PROXY="localhost,127.0.0.1,.svc.cluster.local"
~~~

Quy tắc đọc proxy environment variables **không giống nhau ở mọi SDK**. Ví dụ Azure SDK for Java có thứ tự đọc riêng; AWS SDK for Java 2.x và Google Cloud Java libraries cũng có ma trận hỗ trợ theo HTTP transport.

Không giả định rằng đặt `HTTPS_PROXY` sẽ cấu hình được mọi thư viện trong cùng JVM. Hãy xác minh bằng một request test cho từng SDK.

### 8.3. Proxy authentication

Nếu proxy yêu cầu username/password, không nhúng credential vào URL:

~~~text
Không nên:
https://user:password@proxy.corp.example:8080
~~~

Thay vào đó, lấy credential từ secret manager và cấu hình theo builder/client hỗ trợ proxy authentication. Không log proxy URL có userinfo, header `Proxy-Authorization` hoặc biến môi trường proxy đã chứa password.

### 8.4. Non-proxy hosts

Các endpoint nội bộ có thể đi trực tiếp:

~~~text
localhost
127.0.0.1
*.svc.cluster.local
metadata.google.internal
~~~

`NO_PROXY` và `http.nonProxyHosts` có quy tắc wildcard/phân tách khác nhau theo client. AWS SDK for Java 2.x có hành vi khác nhau giữa Apache, Netty, URLConnection và CRT-based clients; Azure và Google cũng có cách cấu hình riêng. Kiểm tra tài liệu transport đang sử dụng thay vì sao chép một chuỗi wildcard cho mọi SDK.

## 9. Cấu hình proxy theo từng cloud provider

### 9.1. Azure SDK for Java

Azure SDK for Java hỗ trợ cấu hình proxy qua:

- Environment/global Configuration.
- Một `Configuration` riêng cho HTTP client.
- `ProxyOptions` cấu hình tường minh trên client builder.

Ví dụ Netty HTTP client với proxy có authentication:

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.ProxyOptions;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import java.net.InetSocketAddress;

HttpClient azureHttpClient = new NettyAsyncHttpClientBuilder()
        .proxy(new ProxyOptions(
                ProxyOptions.Type.HTTP,
                new InetSocketAddress("proxy.corp.example", 8080))
                .setCredentials(proxyUsername, proxyPassword))
        .build();
~~~

Sau đó truyền `azureHttpClient` vào builder của service client Azure có hỗ trợ `httpClient(...)` hoặc `httpClient` option tương ứng. Ví dụ, các client builder từ Azure Core thường có thể nhận một `HttpClient` đã cấu hình.

Azure SDK builder có thể đọc environment proxy theo quy tắc riêng. Tài liệu Microsoft lưu ý việc dùng ngầm `HTTP_PROXY`/`HTTPS_PROXY` phụ thuộc cấu hình Java proxy/system configuration. Nếu cần proxy riêng cho một client, truyền `ProxyOptions` tường minh giúp giới hạn phạm vi hơn.

Nếu muốn không đọc proxy environment/global configuration, Azure HTTP client builder có thể dùng `Configuration.NONE`; hãy chỉ làm vậy khi endpoint có đường mạng trực tiếp được cho phép.

### 9.2. AWS SDK for Java 2.x

AWS SDK for Java 2.x cho phép cấu hình proxy ở HTTP client builder:

~~~java
import java.net.URI;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.http.apache.ProxyConfiguration;
import software.amazon.awssdk.services.s3.S3Client;

var proxy = ProxyConfiguration.builder()
        .endpoint(URI.create("http://proxy.corp.example:8080"))
        .username(proxyUsername)
        .password(proxyPassword)
        .addNonProxyHost("localhost")
        .build();

var httpClient = ApacheHttpClient.builder()
        .proxyConfiguration(proxy)
        .build();

S3Client s3 = S3Client.builder()
        .httpClient(httpClient)
        .build();
~~~

Proxy settings cũng có thể đến từ JVM system properties và environment variables. **Khả năng hỗ trợ HTTPS proxy properties phụ thuộc loại HTTP client**: AWS docs nêu Apache/URLConnection, Netty và CRT có các ma trận hỗ trợ khác nhau. Kiểm tra chính xác `ApacheHttpClient`, `NettyNioAsyncHttpClient` hoặc `AwsCrtAsyncHttpClient` đang dùng.

TLS cũng có khác biệt: AWS SDK dùng JSSE với một số HTTP clients, nhưng AWS CRT có TLS stack riêng. Các system properties như `jdk.tls.client.protocols` và `javax.net.debug` không có tác dụng giống nhau với CRT. Không kết luận toàn bộ AWS SDK đang dùng JSSE chỉ vì ứng dụng chạy trên JVM.

### 9.3. Google Cloud Java client libraries

Google Cloud Java client libraries dùng HTTPS và gRPC. Tài liệu Google nêu proxy có thể cấu hình bằng Java system properties `https.proxyHost`/`https.proxyPort`; HTTP clients có thể dùng `http.proxyHost`.

Với HTTP transport cần proxy authentication tùy chỉnh, có thể tạo `HttpTransportFactory` và truyền vào `GoogleCredentials`. Ví dụ kiến trúc:

~~~java
HttpTransportFactory transportFactory = createAuthenticatedProxyTransport(
        proxyHost, proxyPort, proxyUsername, proxyPassword);

GoogleCredentials credentials =
        GoogleCredentials.getApplicationDefault(transportFactory);
~~~

Phần `createAuthenticatedProxyTransport` cần cấu hình Apache HTTP transport với proxy route planner và credentials provider theo hướng dẫn Google. Không đưa proxy password trực tiếp vào source code.

Với gRPC custom proxy, Google Cloud docs hướng dẫn cung cấp `ProxyDetector` cho `ManagedChannelBuilder` và tạo `HttpConnectProxiedSocketAddress`. Vì gRPC transport khác HTTP/REST, việc đặt `HTTPS_PROXY` không bảo đảm tất cả client gRPC dùng proxy authentication theo cùng cách.

### 9.4. So sánh nhanh

| Provider | Proxy cấu hình ở đâu? | Điểm cần lưu ý |
| --- | --- | --- |
| **Azure SDK for Java** | Environment/Configuration hoặc `ProxyOptions` trên HTTP client | Proxy gắn với từng `HttpClient`; có thể dùng Netty, OkHttp hoặc JDK |
| **AWS SDK for Java 2.x** | Per-client `ProxyConfiguration`, JVM properties hoặc env | Hành vi khác theo Apache/URLConnection/Netty/CRT; CRT có TLS stack riêng |
| **Google Cloud Java** | Java proxy properties; custom `HttpTransportFactory` hoặc gRPC `ProxyDetector` | HTTP và gRPC cần cấu hình transport tương ứng |
| **Spring RestClient/WebClient** | Request factory/connector và SSL bundle | Không tự cấu hình proxy cho các cloud SDK độc lập |

## 10. Kết hợp proxy và SSL bundle trong một client

Một client có thể cần đồng thời:

- TLS truststore để xác minh server.
- Client keystore nếu mTLS.
- Proxy route và proxy authentication.
- Connect/read timeout.
- Danh sách host được phép đi trực tiếp.

Không phải API builder nào cũng nhận cả `SSLContext` và proxy trong cùng một cấu hình. Khi cần, hãy tạo đúng HTTP client implementation rồi truyền nó vào Spring hoặc SDK.

Ví dụ dùng JDK HttpClient cho Spring `RestClient`, lấy SSLContext từ bundle và đặt proxy:

~~~java
package com.example.checkout;

import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.http.HttpClient;
import java.time.Duration;
import javax.net.ssl.SSLContext;

import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class ProxiedPartnerClientConfiguration {

    @Bean
    RestClient partnerRestClient(
            RestClient.Builder builder,
            SslBundles sslBundles) {
        SSLContext sslContext =
                sslBundles.getBundle("partner-api").createSslContext();

        HttpClient jdkClient = HttpClient.newBuilder()
                .sslContext(sslContext)
                .proxy(ProxySelector.of(
                        new InetSocketAddress("proxy.corp.example", 8080)))
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        return builder
                .baseUrl("https://payments.example.com")
                .requestFactory(new JdkClientHttpRequestFactory(jdkClient))
                .build();
    }
}
~~~

Ví dụ trên dùng proxy không authentication để tập trung vào việc kết hợp SSL context và proxy. Nếu proxy yêu cầu authentication, JDK HttpClient cần `Authenticator` phù hợp và chính sách xử lý credential riêng; không nên tự đặt header proxy thủ công vào request gửi tới origin.

Với một SDK cloud, hãy dùng HTTP transport builder mà SDK hỗ trợ. Không lấy `RestClient` proxy config làm bằng chứng AWS/Azure/GCP client đã đi qua cùng proxy.

## 11. Kiểm tra kết nối TLS và proxy

### 11.1. Dùng OpenSSL kiểm tra server certificate

Từ môi trường có OpenSSL:

~~~bash
openssl s_client \
  -connect payments.example.com:443 \
  -servername payments.example.com \
  -showcerts \
  -verify_return_error
~~~

Các tùy chọn:

- `-connect`: host và port cần kết nối.
- `-servername`: gửi SNI đúng hostname.
- `-showcerts`: in chain server gửi về.
- `-verify_return_error`: làm command thất bại nếu xác minh chain gặp lỗi.

Kiểm tra qua HTTP CONNECT proxy:

~~~bash
openssl s_client \
  -proxy proxy.corp.example:8080 \
  -connect payments.example.com:443 \
  -servername payments.example.com \
  -showcerts \
  -verify_return_error
~~~

Nếu dùng TLS inspection, certificate leaf có thể do corporate CA ký. Kiểm tra issuer và fingerprint, rồi xác minh CA đó qua kênh bảo mật trước khi import.

### 11.2. Kiểm tra certificate fields

Sau khi lưu leaf certificate ra file:

~~~bash
openssl x509 -in server-leaf.pem -noout -subject -issuer -dates -ext subjectAltName
~~~

Xác minh:

- SAN có hostname cần gọi không?
- Certificate còn hiệu lực không?
- Issuer có đúng CA dự kiến không?
- Certificate chain có intermediate cần thiết không?
- Key usage/Extended Key Usage có phù hợp mục đích server/client không?

### 11.3. Kiểm tra Java truststore

~~~bash
keytool -list -v \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
~~~

Đối chiếu alias, subject, issuer, serial number và thời hạn. Nếu certificate không có trong truststore nhưng Java vẫn thành công, client có thể đang dùng truststore mặc định hoặc một transport khác. Xác minh client đang sử dụng bundle nào.

### 11.4. Bật TLS handshake debug trong Java

Chạy JVM với:

~~~bash
java -Djavax.net.debug=ssl:handshake -jar order-service.jar
~~~

Log có thể cho thấy protocol, certificate và bước handshake thất bại. Chỉ bật trong môi trường dev/test có kiểm soát vì log rất lớn và có thể để lộ metadata kết nối. Đặt JVM property **trước** `-jar`; không đặt sau tên jar như một application argument.

AWS CRT dùng TLS stack riêng nên JSSE debug property có thể không hiển thị handshake của CRT. Với client native/SDK khác, dùng logging/diagnostic của đúng transport.

## 12. Kiểm thử TLS và proxy

Một bài test chỉ gọi endpoint public thành công chưa đủ chứng minh mọi nhánh bảo vệ. Nên tách test certificate trust, hostname verification, proxy routing và cloud SDK transport.

### 12.1. Unit test cấu hình SSL bundle

Kiểm tra cấu hình bundle được nạp và có thể tạo `SSLContext`:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;

import javax.net.ssl.SSLContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PartnerSslBundleTest {

    @Autowired
    SslBundles sslBundles;

    @Test
    void loadsPartnerSslBundle() {
        SSLContext context =
                sslBundles.getBundle("partner-api").createSslContext();

        assertThat(context).isNotNull();
        assertThat(context.getProtocol()).isNotBlank();
    }
}
~~~

Test này xác minh cấu hình material được đọc và tạo được SSLContext. Nó không chứng minh server certificate thật khớp hostname hoặc proxy có thể tạo tunnel.

### 12.2. Integration test với TLS test server

Tạo local test server dùng certificate do CA test ký:

| Test | Cấu hình | Kết quả mong đợi |
| --- | --- | --- |
| CA hợp lệ, hostname đúng | Truststore có test CA; URL khớp SAN | TLS handshake thành công |
| CA không được trust | Truststore không có CA ký server | Handshake thất bại |
| Hostname không khớp SAN | Kết nối bằng host khác certificate | Hostname verification thất bại |
| Certificate hết hạn | Dùng certificate test expired | Handshake thất bại |
| mTLS thiếu client cert | Server yêu cầu client certificate | Handshake bị từ chối |
| mTLS certificate không được trust | Client cert do CA khác ký | Server từ chối client |
| Proxy từ chối CONNECT | Proxy trả 403/407 | Client báo lỗi proxy, không phải lỗi certificate origin |

Dùng test certificate và CA riêng, không đưa CA test vào truststore production.

### 12.3. Integration test proxy

Có thể dùng proxy mock hoặc proxy test trong container để kiểm tra:

1. Client gửi CONNECT tới đúng hostname/port.
2. Host trong `NO_PROXY` đi trực tiếp theo đúng cấu hình.
3. Proxy authentication thành công và thất bại được phân biệt.
4. HTTPS origin certificate vẫn được xác minh sau khi tunnel được tạo.
5. TLS inspection test dùng CA giả lập riêng và không ảnh hưởng truststore production.

### 12.4. Kiểm thử từng cloud SDK

| SDK | Test nên có |
| --- | --- |
| Azure SDK | Tạo `HttpClient` với `ProxyOptions`, gọi một endpoint dev, xác minh request đi qua proxy |
| AWS SDK v2 | Cấu hình `ProxyConfiguration` trên đúng HTTP client implementation, kiểm tra `NO_PROXY` |
| Google Cloud HTTP client | Dùng `HttpTransportFactory` tùy chỉnh và test proxy authentication |
| Google Cloud gRPC | Cấu hình `ProxyDetector` và xác minh CONNECT tunnel |
| Spring RestClient/WebClient | Áp dụng SSL bundle, kiểm tra trust/hostname và request factory/connector |

Không dùng credential production trong test proxy. Ghi nhận host, port, loại transport và correlation ID, nhưng không log proxy password, Authorization header hoặc private key.

## 13. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `PKIX path building failed` | Truststore thiếu root/intermediate CA hoặc server thiếu chain | Kiểm tra chain và CA trust anchor |
| `unable to find valid certification path` | Client không tin CA ký server | Kiểm tra truststore thực tế của HTTP client |
| `No subject alternative DNS name matching` | Hostname URL không khớp SAN | Dùng đúng hostname hoặc yêu cầu certificate đúng SAN |
| `certificate expired` / `not yet valid` | Certificate hết hạn hoặc đồng hồ sai | Kiểm tra thời hạn và đồng bộ clock |
| `handshake_failure` | Protocol/cipher, mTLS, EKU hoặc certificate không tương thích | Bật handshake debug ở dev và kiểm tra policy hai phía |
| `bad_certificate` | Peer từ chối client certificate hoặc chain | Kiểm tra keystore, alias, chain và CA mà server trust |
| HTTP 407 | Proxy yêu cầu authentication | Cấu hình proxy credentials trên transport |
| HTTP 403 khi CONNECT | Proxy không cho phép hostname/port | Kiểm tra policy proxy, allowlist và port |
| `Connection refused` tới proxy | Proxy host/port sai hoặc không truy cập được | Kiểm tra DNS, route, firewall và listener |
| Chỉ Azure SDK đi proxy, AWS không đi | SDK đọc proxy theo cơ chế riêng | Cấu hình đúng client builder cho từng SDK |
| Spring RestClient thành công, GCP gRPC thất bại | HTTP/gRPC dùng transport khác | Cấu hình `ProxyDetector` hoặc channel builder |
| TLS inspection gây lỗi certificate | JVM không trust corporate CA hoặc hostname/SAN không khớp | Xác minh CA inspection, import trust anchor được phê duyệt |
| Đổi truststore nhưng app không nhận | Client đã tạo và giữ SSLContext cũ | Tạo lại client/connection pool hoặc restart có kiểm soát |
| AWS CRT không có JSSE debug | CRT dùng TLS stack riêng | Dùng diagnostic của CRT/transport phù hợp |

**Không chữa lỗi bằng cách tắt xác minh certificate.** Các cách như `TrustAllStrategy`, `NoopHostnameVerifier`, `InsecureTrustManagerFactory` hoặc cấu hình bỏ qua hostname verification khiến client chấp nhận server giả mạo và mở đường cho man-in-the-middle.

## 14. Vòng đời certificate và trust material

Certificate có ngày hết hạn; CA nội bộ có thể được thay; proxy inspection có thể đổi root; client mTLS cần certificate mới. Ứng dụng phải có quy trình cập nhật truststore/keystore.

### 14.1. Rotation CA theo overlap

Khi thay root CA:

1. Xác minh root CA mới và fingerprint qua kênh tin cậy.
2. Phát hành truststore chứa **cả CA cũ và CA mới**.
3. Triển khai truststore mới đến ứng dụng và tạo lại client/SSLContext nếu cần.
4. Xác minh kết nối với certificate chain mới ở tất cả instance.
5. Chuyển server/proxy sang chain mới.
6. Sau khi mọi client đã cập nhật, loại CA cũ khỏi truststore theo kế hoạch.

Không xóa CA cũ trước khi các endpoint đang phục vụ đã chuyển certificate; nếu không, có thể gây outage.

### 14.2. Reload SSL bundles

Spring Boot hỗ trợ `reload-on-update` cho một số SSL bundles dựa trên PEM. Tài liệu hiện hành nêu các consumer tương thích gồm embedded Tomcat và Netty web server. Đây không phải bảo đảm rằng mọi `RestClient`, cloud SDK, HTTP pool hoặc gRPC channel tự cập nhật.

Khi dùng SSL bundle với file watcher, cần:

- Lưu certificate/key ở file path được phép theo dõi.
- Cập nhật file theo cách atomic hoặc bảo đảm file chain/key đồng bộ.
- Chỉ sử dụng consumer có hỗ trợ reload.
- Với client SDK, tạo lại client/SSLContext nếu transport không hỗ trợ reload.
- Kiểm thử cả trạng thái trước và sau rotation.

### 14.3. Quản lý private key

Private key trong keystore phải được bảo vệ như secret:

- Lưu trong Key Vault/HSM hoặc secret manager phù hợp khi kiến trúc cho phép.
- Giới hạn quyền đọc file mount và quyền truy cập container.
- Không log password, PEM private key hoặc nội dung keystore.
- Hạn chế export key nếu có thể dùng HSM/non-exportable key.
- Theo dõi thời hạn certificate và owner chịu trách nhiệm gia hạn.

## 15. Quyết định cấu hình theo tình huống

| Tình huống | Trust material | Proxy | Cách áp dụng |
| --- | --- | --- | --- |
| Gọi public cloud API bằng HTTPS | JVM public CA trust hoặc SSL bundle mặc định | Không có | HTTP client mặc định đã hỗ trợ TLS |
| API nội bộ dùng CA doanh nghiệp | Truststore chứa corporate root/intermediate đã xác minh | Có thể qua proxy | SSL bundle riêng cho API nội bộ |
| Proxy TLS inspection | Truststore chứa corporate inspection CA được phê duyệt | Corporate proxy | Giữ hostname verification và kiểm soát phạm vi trust |
| Đối tác yêu cầu mTLS | Keystore client cert/private key + truststore server CA | Tùy network | SSL bundle mTLS và client transport hỗ trợ |
| Azure SDK qua proxy | Trust material của Azure endpoint và proxy nếu cần | `ProxyOptions` hoặc Configuration | Cấu hình Azure HTTP client riêng |
| AWS SDK v2 qua proxy | Trust material theo HTTP client/TLS stack | `ProxyConfiguration` | Chọn đúng Apache/Netty/CRT |
| Google Cloud REST/gRPC | Trust material theo transport | Java proxy properties, custom HTTP factory hoặc gRPC ProxyDetector | Cấu hình riêng HTTP và gRPC |

## 16. Bài tập thực hành tổng hợp

`shipping-service` gọi API đối tác qua mạng doanh nghiệp:

- API `https://api.shipping.example` dùng certificate do CA đối tác cấp.
- Proxy `proxy.corp.example:8080` yêu cầu authentication.
- Đối tác yêu cầu mTLS với client certificate riêng.
- Ứng dụng đồng thời gọi Azure Key Vault và Google Cloud Storage.
- Certificate client sẽ hết hạn trong 45 ngày.

**Nhiệm vụ:**

1. Tạo truststore chứa CA ký server certificate của đối tác.
2. Tạo keystore chứa client certificate và private key theo quy trình CA.
3. Cấu hình SSL bundle `shipping-mtls`.
4. Áp dụng bundle cho `RestClient` và cấu hình proxy trong request factory phù hợp.
5. Cấu hình proxy riêng cho Azure SDK và Google Cloud HTTP/gRPC transport.
6. Viết integration test cho CA không trust, hostname mismatch, thiếu client certificate và proxy 407.
7. Lập kế hoạch rotation certificate theo overlap, tạo client mới và xác minh trước khi thu hồi certificate cũ.

**Câu hỏi tự đánh giá:**

- Vì sao truststore và keystore không thể thay thế cho nhau?
- Một certificate chain hợp lệ nhưng SAN không chứa hostname có được chấp nhận không?
- Proxy CONNECT thông thường có giải mã payload HTTPS không?
- TLS inspection proxy cần được tin cậy như thế nào?
- Vì sao SSL bundle của Spring Boot không tự áp dụng cho AWS CRT hoặc Google Cloud gRPC?
- Khi đổi truststore file, vì sao HTTP client đang chạy có thể vẫn dùng trust material cũ?
- Vì sao nên triển khai CA mới trước khi server chuyển sang certificate chain mới?

**Đáp án định hướng:** truststore xác minh peer, keystore chứng minh danh tính của ứng dụng; hostname phải khớp SAN; CONNECT tạo tunnel, TLS inspection có thể giải mã và mã hóa lại; SDK dùng transport riêng; client thường giữ SSLContext khi khởi tạo; CA overlap tránh khoảng trống tin cậy.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot – SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): JKS/PKCS12, PEM, truststore, keystore, SSLContext và reload.
- [Spring Boot 3.5 – RestClient SSL API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientSsl.html): áp dụng SSL bundle vào RestClient.
- [Spring Boot – Calling REST services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestClient/WebClient và SSL bundle support.
- [Oracle – JSSE Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html): truststore, keystore và TLS properties.
- [Oracle – keytool](https://docs.oracle.com/en/java/javase/23/docs/specs/man/keytool.html): import certificate, kiểm tra fingerprint và quản lý keystore.
- [Microsoft Learn – Configure proxies in Azure SDK for Java](https://learn.microsoft.com/en-us/azure/developer/java/sdk/proxying): environment, Configuration và ProxyOptions.
- [Microsoft Learn – HTTP clients and pipelines in Azure SDK for Java](https://learn.microsoft.com/en-us/azure/developer/java/sdk/http-client-pipeline): Netty, OkHttp, JDK HTTP client và transport.
- [AWS – Working with TLS in SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/security-java-tls.html): TLS versions, JSSE và AWS CRT.
- [AWS – Configure HTTP proxies in SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-config-proxy-support.html): ProxyConfiguration, system properties, environment và non-proxy hosts.
- [Google Cloud – Configure a proxy for Java](https://docs.cloud.google.com/java/docs/configuring-a-proxy?hl=en): HTTPS, HTTP transport và gRPC ProxyDetector.

**Ghi nhớ:** TLS chỉ an toàn khi client xác minh đúng certificate chain và hostname; proxy chỉ an toàn khi trust boundary được hiểu rõ; SSL bundle chỉ có hiệu lực với client/transport đã được áp dụng. Với ứng dụng Spring Cloud tích hợp nhiều provider, hãy kiểm thử từng HTTP/gRPC transport và lên kế hoạch rotation trust material trước khi certificate hết hạn.
