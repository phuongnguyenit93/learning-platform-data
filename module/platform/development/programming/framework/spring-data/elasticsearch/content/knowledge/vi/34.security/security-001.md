# Bảo vệ kết nối HTTPS và xác minh chứng chỉ

Spring Data Elasticsearch giao tiếp với Elasticsearch thông qua HTTP client. Khi cluster bật TLS, ứng dụng phải kết nối bằng HTTPS và xác minh được chứng chỉ máy chủ. HTTPS mã hóa dữ liệu trên đường truyền, còn certificate validation giúp ứng dụng biết mình đang kết nối đúng máy chủ được tin cậy.

Chỉ đổi URL từ http thành https chưa đủ nếu JVM không tin CA đã ký chứng chỉ Elasticsearch, chứng chỉ hết hạn, hostname không khớp Subject Alternative Name (SAN), hoặc chuỗi chứng chỉ bị thiếu. Tắt xác minh hostname hay dùng trust-all SSLContext có thể làm kết nối chạy được trong lúc thử nghiệm nhưng khiến ứng dụng dễ bị giả mạo máy chủ và tấn công man-in-the-middle.

Bài này giải thích TLS, trust chain, hostname verification, cách chuẩn bị CA/truststore, cấu hình Spring Data Elasticsearch và Elasticsearch Java API Client, mutual TLS (mTLS), quản lý certificate rotation, kiểm tra kết nối và xử lý lỗi thường gặp.

## 1. HTTPS bảo vệ điều gì?

HTTP gửi request và response dưới dạng không được mã hóa ở tầng transport. Nếu kết nối đi qua mạng không tin cậy, người có khả năng quan sát hoặc can thiệp lưu lượng có thể đọc dữ liệu hoặc thay đổi nội dung truyền đi.

HTTPS sử dụng TLS để cung cấp các thuộc tính chính:

- **Confidentiality**: mã hóa nội dung trao đổi để bên thứ ba không đọc được dữ liệu trên đường truyền.
- **Integrity**: phát hiện dữ liệu bị thay đổi trong quá trình truyền.
- **Server authentication**: xác minh máy chủ dựa trên chứng chỉ và chuỗi CA được client tin cậy.
- **Client authentication (tùy chọn)**: với mutual TLS, máy chủ cũng yêu cầu client trình chứng chỉ để xác thực danh tính ứng dụng.

Trong ứng dụng Spring Data Elasticsearch, các dữ liệu có thể đi qua kết nối gồm:

- Document được index hoặc update.
- Query, filter và aggregation.
- Username/password hoặc API key trong HTTP headers.
- Kết quả search, metadata và lỗi.
- Thông tin quản trị nếu ứng dụng được cấp quyền tương ứng.

HTTPS bảo vệ dữ liệu trên đường truyền. Nó không thay thế authentication, authorization, role-based access control, network segmentation hoặc mã hóa dữ liệu lưu trên disk.

## 2. TLS handshake và certificate chain

Khi client mở kết nối HTTPS, TLS handshake diễn ra trước khi HTTP request được gửi.

Luồng đơn giản:

~~~text
Spring Data Elasticsearch application
              |
              | 1. ClientHello
              v
       Elasticsearch endpoint
              |
              | 2. Server certificate chain
              v
     JVM certificate validation
              |
              | 3. Hostname verification
              v
       TLS session established
              |
              | 4. Encrypted HTTP request
              v
          Elasticsearch
~~~

Client kiểm tra các thông tin quan trọng:

1. Chứng chỉ có còn trong thời hạn hiệu lực không.
2. Chuỗi chứng chỉ có nối được tới một trust anchor mà client tin cậy không.
3. Chữ ký và thuật toán của chứng chỉ có hợp lệ không.
4. Chứng chỉ có phù hợp mục đích sử dụng cho server authentication không.
5. Hostname trong URL có khớp SAN của chứng chỉ không.
6. Phiên bản TLS và bộ mã hóa có được hai bên hỗ trợ không.

Nếu một bước xác minh thất bại, client nên từ chối handshake. Không nên biến lỗi xác minh thành kết nối không kiểm tra chứng chỉ.

### 2.1. Certificate chain

Một certificate chain thường có cấu trúc:

~~~text
Root CA
   |
   +-- Intermediate CA
           |
           +-- Elasticsearch server certificate
~~~

Server certificate thường được ký bởi intermediate CA. Intermediate CA được ký bởi root CA. Client thường lưu root CA hoặc CA nội bộ đáng tin trong truststore; server cần gửi đủ intermediate certificate để client xây dựng chain.

Các khái niệm:

- **Leaf/server certificate**: chứng chỉ đại diện cho hostname của Elasticsearch.
- **Intermediate CA**: CA trung gian ký chứng chỉ server hoặc CA cấp dưới.
- **Root CA**: trust anchor mà client tin cậy.
- **Truststore**: nơi client lưu CA/chứng chỉ dùng để xác minh server.
- **Keystore**: nơi ứng dụng lưu private key và certificate của chính nó khi cần client authentication.

Không nhầm truststore với keystore. Truststore trả lời câu hỏi “ứng dụng tin cậy CA nào?”. Keystore trả lời câu hỏi “ứng dụng có private key/certificate nào để trình cho bên kia?”.

### 2.2. Self-signed certificate và CA nội bộ

Trong môi trường development, Elasticsearch có thể dùng certificate tự ký hoặc certificate do CA nội bộ cấp. JVM không tự động tin một CA tùy chỉnh chỉ vì certificate được server gửi trong handshake.

Có hai cách phổ biến:

- Import CA certificate vào truststore mà ứng dụng sử dụng.
- Dùng một truststore được nền tảng hoặc tổ chức quản lý và phân phối cho ứng dụng.

Ưu tiên tin cậy CA đã phát hành certificate, thay vì tin cậy leaf certificate nếu hạ tầng có thể cấp lại certificate định kỳ. Với certificate tự ký, chính certificate đó có thể đóng vai trò trust anchor, nhưng phải quản lý fingerprint và rotation cẩn thận.

Không tải certificate qua một kết nối không xác thực rồi tin nó ngay mà không xác minh nguồn/fingerprint qua kênh tin cậy.

## 3. Hostname verification và Subject Alternative Name

Certificate chain hợp lệ vẫn chưa đủ. Client phải xác minh rằng certificate được phát hành cho hostname mà ứng dụng đang kết nối.

Ví dụ ứng dụng gọi:

~~~text
https://es-prod.internal.example:9200
~~~

Certificate server phải chứa hostname phù hợp trong Subject Alternative Name, ví dụ:

~~~text
DNS:es-prod.internal.example
~~~

Nếu ứng dụng gọi bằng IP:

~~~text
https://10.20.30.40:9200
~~~

Certificate cần SAN kiểu IP tương ứng, ví dụ:

~~~text
IP Address:10.20.30.40
~~~

SAN là nơi tiêu chuẩn hiện đại dùng để kiểm tra DNS name và IP address. Không nên dựa vào Common Name (CN) cũ để thay thế SAN.

Lỗi hostname mismatch có thể xảy ra khi:

- Certificate chỉ có SAN cho tên DNS nhưng ứng dụng kết nối bằng IP.
- Ứng dụng dùng alias khác với hostname trong certificate.
- Load balancer/proxy trả certificate của endpoint khác.
- Certificate được tạo trước khi DNS endpoint hiện tại tồn tại.
- Ứng dụng kết nối tới node trực tiếp trong khi certificate chỉ có SAN của load balancer.

Giải pháp đúng là cấp certificate có SAN bao gồm các hostname/IP mà client thực sự sử dụng, hoặc thay URL để dùng hostname đã có trong SAN. Không tắt hostname verification để bỏ qua mismatch.

### 3.1. SNI

Server Name Indication (SNI) cho phép client gửi hostname trong TLS ClientHello. Một proxy hoặc load balancer có thể dùng SNI để chọn certificate phù hợp khi nhiều hostname cùng chia sẻ một địa chỉ IP.

Nếu client kết nối bằng IP, server có thể không chọn được certificate theo hostname dự kiến. Dùng DNS hostname đúng với certificate và cấu hình SNI của endpoint.

## 4. Xác định endpoint Elasticsearch dùng HTTPS

Ứng dụng cần dùng HTTPS endpoint:

~~~text
https://elasticsearch.example.internal:9200
~~~

Nếu cluster chỉ bật HTTP, client HTTPS sẽ không thể handshake. Nếu cluster bật TLS nhưng client vẫn gọi HTTP, kết nối có thể bị từ chối hoặc trả lỗi giao thức.

Kiểm tra các thành phần:

- Elasticsearch HTTP TLS đã được bật.
- Certificate và private key server được cấu hình đúng.
- Server gửi đủ certificate chain cần thiết.
- Port và proxy endpoint đúng.
- DNS resolve tới đúng máy chủ.
- Network policy cho phép ứng dụng tới cổng HTTPS.
- URL trong Spring configuration dùng scheme https.

Với Elasticsearch self-managed, cấu hình TLS HTTP thường nằm trong cấu hình node, ví dụ các thiết lập xpack.security.http.ssl.*. Tên setting và cách cung cấp certificate phụ thuộc phiên bản Elasticsearch và cách triển khai. Hãy dùng tài liệu bảo mật của đúng version cluster.

Managed Elasticsearch service có thể đã bật HTTPS mặc định và cung cấp CA hoặc hướng dẫn trust cụ thể. Khi đó, dùng endpoint và CA do nhà cung cấp công bố qua kênh quản trị tin cậy.

## 5. Chuẩn bị truststore cho JVM

Nếu Elasticsearch dùng CA không nằm trong truststore mặc định của JVM, ứng dụng cần truststore chứa CA phù hợp.

Ví dụ tổ chức cung cấp file CA:

~~~text
config/
  certs/
    elasticsearch-root-ca.crt
~~~

Có thể tạo PKCS12 truststore bằng keytool:

~~~bash
keytool -importcert \
  -alias elasticsearch-root-ca \
  -file config/certs/elasticsearch-root-ca.crt \
  -keystore config/certs/elasticsearch-truststore.p12 \
  -storetype PKCS12
~~~

keytool sẽ hỏi mật khẩu truststore và xác nhận có tin certificate hay không. Trước khi import, xác minh fingerprint của CA qua kênh đáng tin cậy:

~~~bash
keytool -printcert -file config/certs/elasticsearch-root-ca.crt
~~~

Liệt kê nội dung truststore:

~~~bash
keytool -list \
  -v \
  -keystore config/certs/elasticsearch-truststore.p12 \
  -storetype PKCS12
~~~

Các lưu ý:

- Dùng CA certificate đúng môi trường.
- Không đưa private key của server vào truststore client.
- Bảo vệ file truststore và mật khẩu.
- Không commit mật khẩu thật vào Git.
- Không copy truststore production vào image public hoặc artifact không kiểm soát.
- Kiểm tra truststore có chứa đúng alias và CA chain cần thiết.

### 5.1. Dùng PEM hay PKCS12?

PEM là định dạng văn bản thường dùng cho certificate và key. PKCS12 là container nhị phân có thể chứa certificate và private key.

Một số API client nhận trực tiếp SSLContext, một số API hoặc công cụ cho phép cấu hình PEM. Cách Spring Boot/Spring Data hỗ trợ phụ thuộc version và HTTP client được sử dụng.

Nếu API cấu hình của ứng dụng cần Java KeyStore, PKCS12 thường là lựa chọn thực tế. Có thể dùng keytool để import CA PEM vào truststore PKCS12 như ví dụ trên.

### 5.2. Truststore JVM mặc định và truststore riêng

Có thể cài CA vào truststore JVM mặc định, nhưng cách này ảnh hưởng mọi ứng dụng chạy bằng JRE đó và khó kiểm soát khi nhiều service cần CA khác nhau.

Truststore riêng cho Elasticsearch giúp:

- Chỉ ứng dụng này tin CA được chỉ định.
- Rotation có thể triển khai độc lập.
- Không thay đổi trust của các kết nối TLS khác.
- Dễ quản lý trong container hoặc secret mount.

Nếu dùng truststore riêng, cần chắc chắn client Elasticsearch thực sự sử dụng SSLContext được tạo từ truststore đó.

## 6. Tạo SSLContext với truststore trong Java

Java SSLContext có thể được tạo từ truststore chứa CA.

Ví dụ:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class ElasticsearchSslContexts {

    private ElasticsearchSslContexts() {
    }

    public static SSLContext fromTrustStore(
            Path trustStorePath,
            char[] trustStorePassword) throws Exception {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");

        try (InputStream input =
                 Files.newInputStream(trustStorePath)) {
            trustStore.load(input, trustStorePassword);
        }

        TrustManagerFactory trustManagerFactory =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );

        trustManagerFactory.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
            null,
            trustManagerFactory.getTrustManagers(),
            new SecureRandom()
        );

        return sslContext;
    }
}
~~~

Giải thích:

- KeyStore đọc file truststore.
- TrustManagerFactory tạo trust managers từ CA đã lưu.
- SSLContext sử dụng trust managers để xác minh certificate server.
- Không truyền custom HostnameVerifier ở đây; hostname verification cần tiếp tục được bật ở HTTP client.

Mẫu trên không nạp client certificate. Nó chỉ cấu hình trust phía client để xác minh server.

Trong ứng dụng thực tế, không hard-code password trong source. Đọc từ secret manager hoặc environment được bảo vệ, chuyển thành char array khi có thể và không log giá trị.

## 7. Cấu hình Spring Data Elasticsearch imperative client

Spring Data Elasticsearch cung cấp ClientConfiguration để cấu hình endpoint, TLS và authentication. Cách cấu hình cụ thể phụ thuộc phiên bản Spring Data Elasticsearch và client transport được sử dụng.

Ví dụ theo API ClientConfiguration phổ biến trong Spring Data Elasticsearch 5.x:

~~~java
import javax.net.ssl.SSLContext;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchClientConfig
        extends ElasticsearchConfiguration {

    private final SSLContext sslContext;

    public ElasticsearchClientConfig(SSLContext sslContext) {
        this.sslContext = sslContext;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("es-prod.internal.example:9200")
            .usingSsl(sslContext)
            .withBasicAuth(
                System.getenv("ES_USERNAME"),
                System.getenv("ES_PASSWORD")
            )
            .build();
    }
}
~~~

Ý nghĩa:

- connectedTo nhận host và port, không chứa scheme trong cách dùng phổ biến của ClientConfiguration.
- usingSsl(sslContext) bật TLS với trust configuration đã chuẩn bị.
- withBasicAuth thêm HTTP Basic Authentication.
- Spring Data tạo client/transport dựa trên cấu hình.

Tên package, superclass, method và overload có thể thay đổi giữa các minor version. Kiểm tra Javadoc của ClientConfiguration, ElasticsearchConfiguration và dependency thực tế trước khi áp dụng.

Nếu dùng API cấu hình khác hoặc Spring Boot auto-configuration, không đăng ký thêm một client thứ hai mà không hiểu client nào được repository/Operations sử dụng. Đảm bảo repository và ElasticsearchOperations cùng dùng client có TLS đúng.

### 7.1. Dùng default JVM trust

Nếu certificate được ký bởi CA đã có trong truststore JVM mặc định, có thể cấu hình TLS mà không tự tạo truststore:

~~~java
ClientConfiguration.builder()
    .connectedTo("es-prod.internal.example:9200")
    .usingSsl()
    .build();
~~~

Cách này dùng trust configuration mặc định của runtime/client. Nó vẫn phải xác minh certificate chain và hostname. Không dùng usingSsl() như bằng chứng rằng mọi CA đều được tin cậy.

### 7.2. Cấu hình endpoint qua properties

Có thể đưa hostname, port và thông tin kết nối ra configuration:

~~~yaml
app:
  elasticsearch:
    host: es-prod.internal.example
    port: 9200
    tls:
      enabled: true
      trust-store: /run/secrets/elasticsearch-truststore.p12
~~~

Mật khẩu truststore, username và password nên được cấp qua secret manager hoặc biến môi trường được quản lý. Không lưu secret production trong YAML được commit.

Nếu Spring Boot auto-configuration được dùng, hãy kiểm tra đúng phiên bản Boot đang chạy hỗ trợ những property TLS nào. Không giả định một property SSL bundle hoặc truststore path có cùng tên ở mọi version.

## 8. Dùng Elasticsearch Java API Client trực tiếp

Nếu ứng dụng tự tạo Elasticsearch Java API Client thay vì dùng client do Spring Data cấu hình, phải đảm bảo HTTP transport cũng được cấu hình TLS.

Elasticsearch Java API Client dùng transport ở tầng dưới. Cấu hình SSLContext cần được truyền vào HTTP client/transport tương ứng của phiên bản client.

Một cách tiếp cận là tạo RestClient low-level với SSLContext, sau đó bọc bằng Elasticsearch transport. API chi tiết phụ thuộc Elasticsearch Java client version và Apache HttpClient integration mà dependency sử dụng.

Mẫu kiến trúc:

~~~text
Truststore
   |
   v
TrustManagerFactory
   |
   v
SSLContext
   |
   v
HTTP low-level client
   |
   v
RestClientTransport
   |
   v
ElasticsearchClient
~~~

Không tạo ElasticsearchClient mặc định qua một builder rồi cho rằng client đó tự dùng SSLContext từ Spring Data configuration. Nếu có hai client bean, hãy đặt tên rõ và đảm bảo mỗi service inject đúng client.

Khi dùng Spring Data Elasticsearch, ưu tiên client/transport do cấu hình Spring Data quản lý để tránh hai bộ connection pool, TLS setting và lifecycle không đồng nhất.

## 9. Cấu hình truststore qua JVM system properties

Một cách khác là cấu hình truststore cho toàn bộ JVM:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/run/secrets/elasticsearch-truststore.p12 \
  -Djavax.net.ssl.trustStorePassword="$ES_TRUSTSTORE_PASSWORD" \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar application.jar
~~~

Các thuộc tính này tác động đến default JSSE trust configuration của JVM. Chúng có thể ảnh hưởng những kết nối TLS khác trong cùng process, không chỉ Elasticsearch.

Ưu điểm là cấu hình đơn giản nếu toàn bộ ứng dụng tin cùng một tập CA. Nhược điểm là scope rộng và khó cô lập. Với ứng dụng kết nối nhiều hệ thống có trust policy khác nhau, SSLContext riêng thường rõ ràng hơn.

Không đưa password trực tiếp vào command line nếu môi trường có thể hiển thị process arguments cho người dùng khác. Ưu tiên secret injection phù hợp với nền tảng triển khai.

## 10. Mutual TLS (mTLS)

Trong TLS một chiều thông thường, client xác minh certificate server. Với mutual TLS, server cũng yêu cầu client trình certificate để xác thực ứng dụng.

Luồng:

~~~text
Client                                    Elasticsearch
  |                                             |
  |----------- ClientHello ------------------->|
  |<---------- Server certificate -------------|
  |----------- Verify server ----------------->|
  |<---------- CertificateRequest -------------|
  |----------- Client certificate ------------>|
  |----------- CertificateVerify ------------->|
  |<---------- Handshake complete -------------|
  |                                             |
  |========== Encrypted HTTP requests =========>|
~~~

mTLS thường được dùng khi:

- Cluster yêu cầu client certificate.
- Mạng nội bộ cần xác thực workload bằng certificate.
- Hệ thống không muốn chỉ dựa vào username/password hoặc API key.
- Có chính sách zero-trust giữa service và Elasticsearch.

mTLS không tự động thay thế authorization. Cluster vẫn cần xác định client certificate thuộc identity nào và gán quyền tương ứng theo cơ chế security của deployment.

### 10.1. Keystore chứa client certificate và private key

Ứng dụng cần keystore có client certificate cùng private key. Ví dụ file PKCS12:

~~~text
/run/secrets/es-client-keystore.p12
~~~

Đồng thời ứng dụng vẫn cần truststore chứa CA dùng để xác minh server.

Không dùng truststore server CA làm nơi lưu private key client. Hai loại vật liệu có mục đích và quyền truy cập khác nhau.

### 10.2. Tạo SSLContext cho mTLS

Ví dụ tạo SSLContext từ truststore và client keystore:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class MutualTlsContextFactory {

    private MutualTlsContextFactory() {
    }

    public static SSLContext create(
            Path trustStorePath,
            char[] trustStorePassword,
            Path keyStorePath,
            char[] keyStorePassword) throws Exception {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        try (InputStream input =
                 Files.newInputStream(trustStorePath)) {
            trustStore.load(input, trustStorePassword);
        }

        TrustManagerFactory trustManagers =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        trustManagers.init(trustStore);

        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        try (InputStream input =
                 Files.newInputStream(keyStorePath)) {
            keyStore.load(input, keyStorePassword);
        }

        KeyManagerFactory keyManagers =
            KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm()
            );
        keyManagers.init(keyStore, keyStorePassword);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
            keyManagers.getKeyManagers(),
            trustManagers.getTrustManagers(),
            new SecureRandom()
        );

        return sslContext;
    }
}
~~~

SSLContext này có cả:

- Trust managers để xác minh Elasticsearch server.
- Key managers để trình client certificate khi server yêu cầu.

Client certificate phải có mục đích sử dụng phù hợp, private key phải được bảo vệ và Elasticsearch phải được cấu hình trust CA phát hành certificate client.

Không bật mTLS ở client một mình rồi mong server tự chấp nhận. Hai phía phải cấu hình trust và certificate policy tương ứng.

## 11. Authentication khác certificate validation

Một kết nối HTTPS có thể xác minh certificate thành công nhưng request vẫn bị từ chối vì thiếu authentication hoặc authorization.

| Lớp bảo vệ | Câu hỏi |
|---|---|
| TLS encryption | Dữ liệu có được mã hóa trên đường truyền không? |
| Server certificate validation | Client có tin đúng máy chủ không? |
| Hostname verification | Certificate có thuộc hostname đang gọi không? |
| Client certificate (mTLS) | Client có trình certificate được server tin không? |
| HTTP authentication | Request được gửi bởi identity nào? |
| Authorization/RBAC | Identity đó được phép làm gì? |

Ví dụ ứng dụng có thể dùng Basic Authentication:

~~~java
.withBasicAuth(username, password)
~~~

Hoặc API key theo cơ chế hỗ trợ của Elasticsearch/client version.

Basic Authentication không tự mã hóa password. Chỉ gửi credentials qua HTTPS đã xác minh certificate. Không log Authorization header hoặc secret trong request.

Với mTLS, certificate xác thực client ở TLS layer. HTTP authentication hoặc role mapping vẫn có thể cần thiết tùy chính sách cluster.

## 12. Certificate expiry và rotation

Certificate có thời hạn. Khi certificate hết hạn, TLS handshake có thể thất bại và ứng dụng không thể kết nối Elasticsearch.

Rotation cần được thiết kế trước:

1. Tạo CA/certificate mới theo quy trình quản trị.
2. Cập nhật truststore để ứng dụng tin CA mới, có thể giữ CA cũ trong giai đoạn chuyển tiếp.
3. Triển khai truststore mới tới ứng dụng.
4. Xác nhận các instance đã nạp truststore mới.
5. Thay server certificate trên Elasticsearch/proxy.
6. Kiểm tra kết nối từ mọi application instance.
7. Sau khi không còn server dùng CA cũ, loại bỏ CA cũ theo chính sách.

Nếu dùng client certificate cho mTLS, cần rotation cả client keystore và server trust policy.

### 12.1. Tránh downtime khi đổi CA

Nếu thay CA đột ngột, client chưa được cập nhật truststore có thể mất kết nối. Một giai đoạn overlap có thể giúp:

~~~text
Truststore cũ:       [CA-old]
Truststore chuyển:   [CA-old, CA-new]
Server certificate: [CA-old] -> [CA-new]
Truststore cuối:     [CA-new]
~~~

Đây là quy trình khái quát. Thứ tự thực tế phải phù hợp với hạ tầng, certificate chain, khả năng reload truststore và chính sách của tổ chức.

### 12.2. SSLContext có reload truststore tự động không?

Không nên giả định SSLContext đã tạo sẽ tự đọc lại file truststore khi file thay đổi. Thông thường, trust managers được khởi tạo từ nội dung truststore tại thời điểm tạo SSLContext.

Tùy HTTP client và Spring Data version, cần tạo lại SSLContext/client hoặc restart ứng dụng để nạp truststore mới. Một số nền tảng có cơ chế reload riêng; hãy xác nhận trước khi dựa vào nó trong rotation.

Thiết kế deployment để có thể thay client connection pool an toàn hoặc rolling restart các instance khi cần nạp certificate mới.

## 13. TLS version và cipher suites

TLS có nhiều phiên bản. Nên sử dụng phiên bản hiện đại được cả JVM và Elasticsearch hỗ trợ, theo chính sách bảo mật của tổ chức. Tránh bật các giao thức cũ đã bị loại bỏ hoặc không còn an toàn.

Một số yếu tố cần kiểm tra:

- Phiên bản JDK.
- Phiên bản Elasticsearch.
- TLS protocols được server bật.
- Cipher suites được client/server hỗ trợ chung.
- Thuật toán và độ dài khóa certificate.
- Chính sách FIPS hoặc crypto provider nếu môi trường yêu cầu.

Không tự cấu hình cipher suite quá hẹp nếu chưa kiểm tra tương thích với JDK, OS và Elasticsearch. Nếu handshake lỗi sau nâng cấp JDK hoặc cluster, xem TLS debug log để xác định protocol/cipher mismatch.

## 14. Kiểm tra kết nối trước khi chạy ứng dụng

Có thể kiểm tra TLS độc lập với Spring Data để khoanh vùng lỗi.

### 14.1. openssl s_client

~~~bash
openssl s_client \
  -connect es-prod.internal.example:9200 \
  -servername es-prod.internal.example \
  -CAfile elasticsearch-root-ca.crt \
  -verify_return_error
~~~

Lệnh này giúp xem certificate chain, SAN, issuer, thời hạn và kết quả verify. -servername gửi SNI. -CAfile chỉ định CA dùng để xác minh.

Nếu endpoint dùng mTLS, có thể cần thêm client certificate và private key theo cú pháp openssl phù hợp với file đang có.

### 14.2. curl với CA certificate

~~~bash
curl \
  --cacert elasticsearch-root-ca.crt \
  -u "$ES_USERNAME:$ES_PASSWORD" \
  https://es-prod.internal.example:9200/
~~~

Không dùng -k hoặc --insecure trong kiểm tra production. Tùy chọn này tắt xác minh certificate và hostname, che giấu chính vấn đề cần giải quyết.

Nếu curl thành công nhưng Java thất bại, so sánh CA store, hostname, TLS protocol, proxy và client configuration. curl có thể dùng trust store hệ điều hành khác với truststore JVM.

### 14.3. keytool

Kiểm tra certificate:

~~~bash
keytool -printcert -file elasticsearch-root-ca.crt
~~~

Kiểm tra truststore:

~~~bash
keytool -list -v \
  -keystore elasticsearch-truststore.p12 \
  -storetype PKCS12
~~~

Các công cụ trên giúp xác nhận file và chain. Chúng không chứng minh Spring Data đang sử dụng đúng file truststore; cần kiểm tra cấu hình runtime.

## 15. Bật TLS handshake debug trong JVM

Khi cần chẩn đoán lỗi TLS từ Java, có thể bật debug tạm thời:

~~~bash
java \
  -Djavax.net.debug=ssl,handshake,trustmanager \
  -jar application.jar
~~~

Log có thể chứa thông tin chi tiết về handshake, certificate chain, trust manager và protocol negotiation. Chỉ bật trong môi trường kiểm soát và tắt sau khi điều tra vì output lớn và có thể tiết lộ metadata nội bộ.

Không gửi log TLS thô lên nơi công khai nếu chứa hostname nội bộ, certificate metadata hoặc thông tin vận hành nhạy cảm.

## 16. Những lỗi HTTPS thường gặp

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| PKIX path building failed | JVM không xây dựng được chain tới CA tin cậy | Kiểm tra CA, intermediate và truststore |
| unable to find valid certification path | Truststore thiếu CA hoặc client dùng truststore khác | Xác nhận SSLContext/runtime truststore |
| No subject alternative DNS name matching | Hostname URL không có trong SAN | Dùng hostname đúng hoặc cấp certificate SAN phù hợp |
| No subject alternative names matching IP address | Kết nối bằng IP nhưng certificate không có IP SAN | Dùng DNS SAN hoặc cấp IP SAN |
| CertificateExpiredException | Certificate hết hạn | Rotation certificate |
| NotYetValidException | Certificate chưa có hiệu lực hoặc clock lệch | Kiểm tra thời hạn và đồng bộ thời gian |
| handshake_failure | Protocol, cipher, client cert hoặc server policy không khớp | Kiểm tra TLS debug và server log |
| bad_certificate | Server không chấp nhận client certificate hoặc chain | Kiểm tra mTLS, client keystore và CA trust |
| HTTP 401 | TLS đã kết nối nhưng thiếu/sai authentication | Kiểm tra credentials/API key |
| HTTP 403 | Identity xác thực được nhưng không đủ quyền | Kiểm tra role/privileges |
| Connection refused | Sai host/port hoặc service không lắng nghe | Kiểm tra endpoint và network |
| HTTP plaintext sent to HTTPS port | Client dùng http:// với cổng TLS | Đổi sang HTTPS và cấu hình TLS |
| Unsupported or unrecognized SSL message | Nhầm HTTP/HTTPS hoặc proxy route sai | Kiểm tra scheme và endpoint |
| Certificate chain incomplete | Server thiếu intermediate certificate | Cấu hình server gửi full chain |

### 16.1. Phân biệt lỗi TLS với lỗi Elasticsearch

Nếu TLS handshake thành công, client có thể tiếp tục nhận HTTP response:

- 401: authentication.
- 403: authorization.
- 404: resource/index/path.
- 429: throttling hoặc quá tải.
- 5xx: lỗi server/proxy.

Không xử lý tất cả lỗi kết nối như lỗi certificate. Xác định tầng thất bại trước khi thay đổi cấu hình.

## 17. Vì sao không dùng trust-all hoặc tắt hostname verification?

Một số đoạn code trên Internet tạo TrustManager chấp nhận mọi certificate hoặc hostname verifier luôn trả true. Chúng bỏ qua chính cơ chế xác minh danh tính máy chủ.

Hệ quả:

- Kẻ tấn công có thể dựng server giả và được client chấp nhận.
- Traffic mã hóa nhưng có thể được mã hóa tới sai máy chủ.
- Credentials, query và document có thể bị đánh cắp.
- Ứng dụng mất khả năng phát hiện certificate bị thay thế.
- Lỗi cấu hình production bị che giấu.

TLS encryption mà không xác minh peer không bảo đảm client đang nói chuyện với Elasticsearch thật.

Không dùng các giải pháp sau trong production:

- TrustManager chấp nhận mọi X509Certificate.
- HostnameVerifier luôn trả true.
- Tùy chọn curl -k để bỏ qua kiểm tra.
- Tắt certificate validation bằng system property.
- Import một certificate không xác minh nguồn/fingerprint.
- Dùng HTTP plaintext qua mạng không tin cậy.

Nếu development dùng self-signed certificate, tạo CA development riêng, ký certificate có SAN phù hợp và import CA đó vào truststore development.

## 18. Quản lý secrets và certificate trong môi trường triển khai

Các giá trị nhạy cảm gồm:

- Truststore password.
- Client keystore password.
- Client private key.
- Elasticsearch username/password.
- API key.
- Certificate private material.

Nguyên tắc:

- Dùng secret manager hoặc secret mount của nền tảng.
- Phân quyền đọc file truststore/keystore ở mức tối thiểu.
- Không commit password/private key vào repository.
- Không đưa secret vào Docker image layer.
- Không log Authorization header, password hoặc private key.
- Không truyền secret qua query parameter.
- Luân chuyển credentials và certificate theo chính sách.
- Dùng identity riêng cho từng service.
- Tách trust policy development, staging và production.

CA certificate công khai hoặc certificate chain có thể không bí mật, nhưng vẫn cần đảm bảo tính toàn vẹn và nguồn phân phối đáng tin. Private key luôn phải được bảo vệ.

## 19. HTTPS cho reactive Elasticsearch client

Reactive Spring Data Elasticsearch dùng reactive HTTP client stack. TLS vẫn cần thực hiện cùng các kiểm tra:

- Endpoint dùng HTTPS.
- Truststore chứa CA phù hợp.
- Hostname verification được bật.
- mTLS được cấu hình nếu server yêu cầu.
- Authentication/authorization được cấu hình riêng.

Không lấy SSLContext của imperative client rồi giả định reactive client tự sử dụng nó. Reactive và imperative có thể dùng transport/client configuration khác nhau, tùy Spring Data Elasticsearch version.

Khi cấu hình reactive client, kiểm tra API của ReactiveElasticsearchConfiguration, ReactiveRestClients hoặc cơ chế client configuration mà dependency hiện tại expose. Xác nhận trust manager và hostname verifier thực sự được truyền tới reactive HTTP client.

Nếu ứng dụng có cả reactive và imperative repository/template, kiểm tra cả hai đường kết nối độc lập. Một client có TLS đúng không bảo đảm client còn lại cũng đúng.

## 20. Kiểm thử TLS trong ứng dụng

Nên chia kiểm thử thành các lớp:

### 20.1. Kiểm tra certificate và endpoint

- Xác minh certificate chain bằng CA tin cậy.
- Xác minh SAN khớp hostname.
- Kiểm tra certificate validity.
- Kiểm tra server gửi đủ intermediate certificate.
- Kiểm tra endpoint và SNI.

### 20.2. Integration test với TLS

Dùng Elasticsearch test instance được cấu hình HTTPS hoặc môi trường test có certificate CA riêng.

Kiểm tra:

- Ứng dụng kết nối bằng HTTPS.
- Truststore đúng được sử dụng.
- Certificate hợp lệ cho hostname.
- Certificate không tin cậy bị từ chối.
- Hostname mismatch bị từ chối.
- Authentication sai trả 401.
- Identity thiếu quyền trả 403.
- mTLS client certificate được gửi nếu cấu hình yêu cầu.

Không viết test chỉ xác nhận request thành công với trust-all manager. Test đó không xác minh được certificate validation.

### 20.3. Kiểm tra certificate rotation

Có thể kiểm thử quy trình overlap CA:

1. Chạy server với certificate CA cũ.
2. Cập nhật truststore test để chứa CA cũ và mới.
3. Chuyển server sang certificate CA mới.
4. Xác nhận client tiếp tục kết nối.
5. Loại CA cũ và xác nhận certificate mới vẫn được tin.

Nếu client không hỗ trợ reload SSLContext, test cần mô phỏng cách ứng dụng tạo lại client hoặc rolling restart.

## 21. Quy trình triển khai HTTPS cho Spring Data Elasticsearch

Một quy trình triển khai có thể đi theo các bước:

1. Xác nhận Elasticsearch endpoint đang phục vụ HTTPS.
2. Lấy CA certificate từ nguồn quản trị đáng tin cậy.
3. Kiểm tra fingerprint và certificate chain.
4. Xác nhận SAN có hostname/IP mà ứng dụng sử dụng.
5. Tạo truststore riêng hoặc chọn truststore JVM phù hợp.
6. Tạo SSLContext với TrustManagerFactory.
7. Cấu hình Spring Data ClientConfiguration hoặc client transport sử dụng SSLContext.
8. Cấu hình authentication riêng bằng Basic Auth, API key hoặc mTLS theo chính sách.
9. Bảo vệ truststore password và private key bằng secret management.
10. Kiểm tra bằng openssl/curl với certificate verification bật.
11. Chạy integration test qua chính client mà repository/Operations sử dụng.
12. Kiểm tra lỗi 401/403 riêng với lỗi TLS.
13. Thiết lập theo dõi certificate expiry và kế hoạch rotation.
14. Lặp lại cấu hình cho reactive client nếu ứng dụng có reactive stack.

Không xem việc mở được TCP socket hoặc nhận HTTP response là bằng chứng TLS được xác minh đúng. Kiểm tra phải bao gồm certificate chain và hostname.

## 22. Checklist vận hành

| Hạng mục | Trạng thái mong muốn |
|---|---|
| URL kết nối | HTTPS |
| Certificate server | Hợp lệ, chưa hết hạn |
| Certificate chain | Đủ intermediate và nối tới CA tin cậy |
| SAN | Khớp hostname/IP trong URL |
| Hostname verification | Bật |
| TLS protocol | Phiên bản được hỗ trợ và cho phép |
| Truststore | Đúng môi trường, có CA tin cậy |
| Private key | Được bảo vệ, không commit |
| Basic Auth/API key | Lưu trong secret manager |
| mTLS | Client cert và server trust được cấu hình hai phía nếu bắt buộc |
| Logs | Không chứa credentials/private key |
| Certificate rotation | Có overlap và quy trình triển khai |
| Imperative client | Đã kiểm tra TLS |
| Reactive client | Đã kiểm tra riêng nếu sử dụng |
| Integration test | Từ chối untrusted certificate và hostname mismatch |

## 23. Bảng tra cứu nhanh

| Nhu cầu | Cách làm |
|---|---|
| Mã hóa kết nối | Dùng HTTPS/TLS |
| Tin CA nội bộ | Tạo truststore chứa CA |
| Kiểm tra hostname | Certificate có SAN khớp URL |
| Dùng truststore PKCS12 | keytool import CA và Java KeyStore API |
| Cấu hình SSLContext | TrustManagerFactory + SSLContext |
| Cấu hình Spring Data | ClientConfiguration.usingSsl(sslContext) theo version |
| Dùng JVM trust mặc định | usingSsl() nếu CA đã được runtime tin cậy |
| Xác thực HTTP | Basic Auth hoặc API key qua HTTPS |
| Xác thực client certificate | mTLS với key managers và client keystore |
| Kiểm tra TLS endpoint | openssl s_client |
| Kiểm tra HTTP với CA | curl --cacert |
| Xem certificate | keytool -printcert |
| Kiểm tra truststore | keytool -list |
| Debug handshake Java | javax.net.debug tạm thời |
| Thay CA an toàn | Truststore overlap và rotation có kiểm soát |
| Tránh MITM | Không dùng trust-all hoặc tắt hostname verification |

HTTPS bảo vệ kết nối Spring Data Elasticsearch khi TLS được cấu hình đúng ở cả server và client. Ứng dụng cần tin cậy CA phù hợp, xác minh certificate chain và hostname SAN, dùng HTTPS endpoint và giữ hostname verification bật. Truststore chứa CA mà client tin cậy; keystore chứa client private key/certificate khi cần mTLS. Hãy cấu hình SSLContext vào đúng imperative hoặc reactive client đang được sử dụng, tách certificate validation khỏi HTTP authentication/authorization, quản lý secrets và certificate rotation có kế hoạch, rồi kiểm thử cả trường hợp certificate hợp lệ lẫn certificate không tin cậy hoặc hostname mismatch.

