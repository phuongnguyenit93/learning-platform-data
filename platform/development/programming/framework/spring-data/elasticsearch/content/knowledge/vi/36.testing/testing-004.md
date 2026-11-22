# Cấp cấu hình động, chứng chỉ và thông tin xác thực cho kiểm thử

Kiểm thử tích hợp Spring Data Elasticsearch thường cần biết địa chỉ Elasticsearch, cổng được cấp động, tài khoản truy cập và chứng chỉ TLS. Nếu các giá trị này được cố định trong `application.yml`, test dễ phụ thuộc vào máy phát triển, khó chạy song song và có nguy cơ sử dụng nhầm credential của môi trường thật.

Một thiết kế test tốt cần tách ba nhóm dữ liệu:

- **Cấu hình kết nối động**: URI, host, port, index prefix và các tham số được cấp khi container hoặc test environment khởi động.
- **Chứng chỉ**: CA certificate mà client tin cậy, và client certificate/private key nếu hệ thống dùng mutual TLS.
- **Thông tin xác thực**: username/password hoặc API key dành riêng cho test, có quyền tối thiểu.

Spring Boot và Spring Data Elasticsearch hỗ trợ nhiều cách đưa cấu hình vào application context. Với Testcontainers, `@DynamicPropertySource` là cách phổ biến để đăng ký endpoint được cấp động trước khi Spring tạo Elasticsearch client. Khi cần kiểm thử TLS và authorization thực sự, phải dùng một Elasticsearch test instance được cấu hình bảo mật; một container test không bật security không thể chứng minh các luồng xác thực và certificate validation hoạt động đúng.

## 1. Vì sao cấu hình kiểm thử cần được cấp động?

Một test Elasticsearch có thể chạy trên nhiều môi trường:

- Máy lập trình viên với Docker local.
- CI runner có port được Docker cấp ngẫu nhiên.
- Testcontainers với container mới cho mỗi test suite.
- Môi trường integration dùng Elasticsearch được quản lý riêng.
- Test bảo mật cần HTTPS, CA certificate và user/API key riêng.

Nếu cố định `localhost:9200`, test có thể xung đột với một Elasticsearch khác đang chạy trên máy. Nếu cố định port, nhiều test suite chạy đồng thời có thể tranh cổng. Nếu cố định mật khẩu trong source, credential có thể bị commit hoặc dùng lại ngoài môi trường test.

Cấu hình động cho phép test lấy thông tin kết nối sau khi tài nguyên test được khởi động:

~~~text
Test starts
   |
   v
Start Elasticsearch container / test service
   |
   v
Resolve host, mapped port, URI, credentials and CA
   |
   v
Register dynamic Spring properties
   |
   v
Create Spring ApplicationContext and Elasticsearch client
   |
   v
Run repository / operations tests
   |
   v
Close client and test resources
~~~

Điểm quan trọng là property phải được đăng ký trước khi Spring khởi tạo bean phụ thuộc vào nó. Nếu Elasticsearch client đã được tạo với endpoint cũ, đổi một biến Java sau đó không tự cấu hình lại client hiện tại.

## 2. Các nguồn cấu hình trong Spring test

Có nhiều cách đưa property vào test:

| Cách | Phù hợp khi | Đặc điểm |
|---|---|---|
| `application-test.yml` | Giá trị ổn định, không bí mật | Dễ đọc và dùng chung |
| `@TestPropertySource` | Override một vài property trong test class | Giá trị tĩnh |
| `@SpringBootTest(properties = ... )` | Test cần cấu hình nhỏ ngay tại annotation | Giá trị tĩnh, phạm vi test |
| `@DynamicPropertySource` | URI/port/secret được tạo khi test khởi động | Đăng ký supplier động |
| `@ServiceConnection` | Testcontainers được Spring Boot hỗ trợ service connection | Tự kết nối một số service được nhận diện |
| Environment variable / secret store | CI hoặc môi trường test dùng secret bên ngoài | Tách secret khỏi source |

Với endpoint có mapped port thay đổi mỗi lần chạy, `@DynamicPropertySource` thường phù hợp hơn file YAML cố định.

`@ServiceConnection` có thể giảm boilerplate khi phiên bản Spring Boot và Testcontainers module hỗ trợ loại service đó. Khi cần đăng ký property tùy chỉnh như CA path, API key, index prefix hoặc URI HTTPS, `@DynamicPropertySource` vẫn hữu ích.

Không nên đăng ký cùng một property ở nhiều nơi mà không có chủ đích. Khi nhiều nguồn cấu hình cùng tồn tại, cần biết nguồn nào đang override giá trị cuối cùng.

## 3. Đăng ký endpoint Testcontainers bằng @DynamicPropertySource

Ví dụ với Elasticsearch Testcontainers cho integration test cơ bản:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class ProductSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    "docker.elastic.co/elasticsearch/elasticsearch:8.15.0"
            );

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry
    ) {
        registry.add(
                "spring.elasticsearch.uris",
                elasticsearch::getHttpHostAddress
        );
    }

    @Test
    void applicationContextStarts() {
        // Exercise repository or ElasticsearchOperations here.
    }
}
~~~

Ví dụ pin image version để test có hành vi lặp lại. Hãy chọn version tương thích với Spring Data Elasticsearch và Elasticsearch Java API Client mà dự án đang dùng; không dùng tag thay đổi theo thời gian như `latest` cho CI ổn định.

`getHttpHostAddress()` trả về địa chỉ HTTP của container cùng mapped port. Test không cần giả định Elasticsearch luôn chạy trên port 9200 của host.

Các điểm cần nhớ:

- Container được khai báo `static` để có thể dùng trong static method `@DynamicPropertySource`.
- Supplier `elasticsearch::getHttpHostAddress` được gọi khi property được resolve.
- Property phải được đăng ký trước lúc Spring tạo Elasticsearch client.
- Container và Spring context phải có lifecycle phù hợp; không dừng container trong khi context còn dùng client.
- Nếu test cần một endpoint HTTPS, hãy đăng ký URI HTTPS và cấu hình trust certificate tương ứng.

Testcontainers Elasticsearch module và image có thể cấu hình security khác nhau theo version. Nhiều cấu hình test đơn giản chạy HTTP không xác thực để giảm thời gian khởi động. Điều đó phù hợp cho test mapping/query cơ bản nhưng không xác minh được TLS, password, API key hoặc role authorization.

## 4. Tách property kiểm thử khỏi cấu hình mặc định

Có thể đặt các giá trị không nhạy cảm vào `src/test/resources/application-test.yml`:

~~~yaml
app:
  elasticsearch:
    index-prefix: test-products
    connect-timeout: 2s
    socket-timeout: 5s
~~~

Với test dùng profile:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ProductRepositoryIntegrationTest {
}
~~~

Endpoint động vẫn có thể được override bởi `@DynamicPropertySource`. Không ghi URI container được cấp ngẫu nhiên vào file YAML vì mỗi lần chạy có thể có port khác.

`@TestPropertySource` phù hợp cho giá trị tĩnh:

~~~java
@SpringBootTest
@TestPropertySource(properties = {
        "app.elasticsearch.index-prefix=it-products",
        "app.elasticsearch.request-timeout=3s"
})
class ProductSearchTest {
}
~~~

Nếu dùng custom property để cấu hình nhiều Elasticsearch client, nên gom vào `@ConfigurationProperties` thay vì rải nhiều `@Value`:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.elasticsearch")
public record TestElasticsearchProperties(
        String uri,
        String username,
        String password,
        String apiKey,
        String caCertificate,
        Duration connectTimeout,
        String indexPrefix
) {
}
~~~

Đây là ví dụ cấu trúc property. Chỉ một trong các phương thức xác thực như Basic Auth hoặc API key nên được chọn cho mỗi client, trừ khi cấu hình Elasticsearch có chủ đích yêu cầu cơ chế kết hợp.

## 5. Cấp username/password động cho test

Với test instance bật Basic Authentication, có thể đăng ký user/password từ test fixture hoặc secret store:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "app.elasticsearch.uri",
            () -> securedElasticsearchUri()
    );
    registry.add(
            "app.elasticsearch.username",
            () -> "test_search_user"
    );
    registry.add(
            "app.elasticsearch.password",
            () -> testPassword()
    );
}
~~~

`testPassword()` nên đọc secret từ nguồn test được quản lý, hoặc lấy từ container fixture đã khởi tạo. Không dùng password production và không commit credential thật vào repository.

Nếu dùng Spring Boot auto-configuration, các property chuẩn thường có dạng:

~~~yaml
spring:
  elasticsearch:
    uris: https://localhost:9200
    username: test_search_user
    password: test-only-password
~~~

Tên và khả năng hỗ trợ property phụ thuộc Spring Boot version. Nếu test dùng custom Elasticsearch client hoặc Spring Data `ClientConfiguration`, có thể dùng prefix riêng `app.elasticsearch` rồi truyền giá trị vào client factory.

Không đặt cả Basic Auth và API key cùng lúc trong một cấu hình client nếu code không xác định rõ cơ chế được ưu tiên. Tránh tạo hành vi xác thực khác nhau giữa local và CI do property cũ còn sót.

## 6. API key dành riêng cho kiểm thử

Elasticsearch API key có thể giới hạn quyền cho một workload test. Ví dụ search integration test chỉ cần đọc index `test-products-*`; test writer cần quyền ghi trên index riêng.

Một API key được tạo bởi test setup hoặc một bước provisioning riêng có thể được cung cấp cho client qua property:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add("app.elasticsearch.uri", RowTestEnvironment::uri);
    registry.add("app.elasticsearch.api-key", RowTestEnvironment::encodedApiKey);
}
~~~

Elasticsearch REST API dùng header:

~~~http
Authorization: ApiKey BASE64_ENCODED_ID_AND_KEY
~~~

Khi API tạo key trả về trường `encoded`, đó là giá trị được thiết kế để gửi trong header Authorization. Không tự nối ID và secret theo cách tùy ý nếu response đã cung cấp giá trị encoded.

Một số nguyên tắc:

- Mỗi test suite hoặc test role dùng key riêng.
- Chỉ cấp quyền trên index test cần thiết.
- Không dùng API key quản trị cluster để chạy repository test.
- Thu hồi key sau test nếu key được tạo trên cluster dùng chung.
- Không in key hoặc Authorization header vào log khi test thất bại.
- Không lưu key vào artifact CI hoặc report công khai.

Nếu test chạy với container dùng một user quản trị đơn giản, điều đó không thay thế kiểm thử role/API key. Nên có một suite bảo mật riêng để xác nhận quyền đọc, ghi và hành động bị từ chối.

## 7. Phân biệt HTTP TLS và transport TLS

Elasticsearch có hai kênh TLS khác nhau:

| Kênh | Mục đích | Spring Data client có dùng trực tiếp không? |
|---|---|---|
| HTTP layer TLS | Bảo vệ REST API giữa ứng dụng và Elasticsearch | Có |
| Transport layer TLS | Bảo vệ giao tiếp node-to-node trong cluster | Không trực tiếp |

Spring Data Elasticsearch giao tiếp với cluster qua HTTP REST client. Vì vậy, client test cần tin cậy chứng chỉ của **HTTP endpoint**.

Transport TLS vẫn có thể cần để cluster security hoạt động đúng, đặc biệt khi triển khai nhiều node. Nhưng certificate cho transport layer không tự động là trust certificate mà ứng dụng Java cần để gọi REST API.

Khi kiểm thử kết nối ứng dụng, hãy lấy CA certificate dùng để ký HTTP server certificate. Không lấy nhầm certificate node transport hoặc certificate của một endpoint khác.

## 8. CA certificate và server certificate

Trong HTTPS, Elasticsearch gửi server certificate cho client. Client cần kiểm tra:

1. Certificate còn hiệu lực.
2. Certificate được ký bởi CA mà client tin cậy.
3. Hostname/IP trong URI khớp với Subject Alternative Name (SAN) của certificate.
4. Certificate chain đầy đủ và phù hợp.
5. TLS protocol/cipher được hai bên hỗ trợ.

Trong môi trường test, có thể tạo một CA riêng và dùng CA đó ký server certificate cho Elasticsearch test node.

Sơ đồ:

~~~text
Test CA
   |
   +---- signs ----> Elasticsearch HTTP server certificate
                           |
                           v
                 HTTPS endpoint: es-test.local
                           |
                           v
                 Java client trusts Test CA
~~~

Client thường chỉ cần trust CA certificate. Không cần đưa private key của server vào ứng dụng test.

Không dùng certificate/private key production cho test. Cũng không tắt certificate validation chỉ để test chạy được; điều đó che giấu lỗi cấu hình TLS và tạo thói quen không an toàn.

## 9. Hostname và SAN phải khớp endpoint

Một lỗi thường gặp là certificate hợp lệ nhưng hostname không khớp.

Ví dụ certificate có SAN:

~~~text
DNS: es-test.internal
DNS: elasticsearch
~~~

Nhưng test lại kết nối tới:

~~~text
https://localhost:39217
~~~

Client có thể từ chối certificate vì `localhost` không nằm trong SAN, dù CA đã được trust.

Cách giải quyết:

- Tạo certificate có SAN khớp hostname mà test dùng.
- Dùng hostname/container network alias nằm trong SAN.
- Nếu dùng mapped port trên host, đưa hostname/IP tương ứng vào SAN theo cách phù hợp.
- Giữ hostname verification bật.

Không dùng `NoopHostnameVerifier` hoặc tắt endpoint identification để né lỗi. Một test TLS chỉ có ý nghĩa khi kiểm tra đúng hostname như ứng dụng production sẽ sử dụng.

## 10. Tạo truststore từ CA certificate

Java có thể dùng truststore chứa CA certificate để xác minh Elasticsearch server.

Ví dụ tạo truststore PKCS12 bằng keytool:

~~~bash
keytool -importcert \
  -alias elasticsearch-test-ca \
  -file test-ca.crt \
  -keystore elasticsearch-test-truststore.p12 \
  -storetype PKCS12
~~~

Lệnh sẽ yêu cầu mật khẩu truststore. Trong CI, mật khẩu nên được cấp qua secret variable hoặc test setup, không ghi vào command history dùng chung hoặc log công khai.

Có thể đặt truststore path trong cấu hình test:

~~~yaml
app:
  elasticsearch:
    ca-certificate: classpath:certs/test-ca.crt
    truststore: file:/workspace/test-certs/elasticsearch-test-truststore.p12
~~~

Nếu chỉ cần trust một CA certificate, client có thể tạo SSL context trực tiếp từ certificate thay vì phải tạo truststore file. Cách này thuận tiện khi Testcontainers sinh certificate vào thư mục tạm.

Không đưa private key của CA vào truststore client. Truststore chứa certificate được tin cậy; keystore chứa private key/certificate identity mà client cần trình ra khi mutual TLS.

## 11. Tạo SSLContext từ CA certificate trong Java

Có thể đọc CA certificate và xây dựng `SSLContext` mà không thay đổi truststore JVM toàn cục:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class TestSslContexts {

    private TestSslContexts() {
    }

    public static SSLContext trustCertificate(Path caCertificate)
            throws Exception {

        CertificateFactory certificateFactory =
                CertificateFactory.getInstance("X.509");

        Certificate ca;
        try (InputStream input = Files.newInputStream(caCertificate)) {
            ca = certificateFactory.generateCertificate(input);
        }

        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        trustStore.load(null, null);
        trustStore.setCertificateEntry("elasticsearch-test-ca", ca);

        TrustManagerFactory trustManagerFactory =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm()
                );
        trustManagerFactory.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
                null,
                trustManagerFactory.getTrustManagers(),
                null
        );

        return sslContext;
    }
}
~~~

Đoạn code:

- Parse CA certificate theo chuẩn X.509.
- Tạo truststore chỉ trong bộ nhớ.
- Thêm CA certificate vào truststore.
- Tạo TrustManager từ truststore.
- Khởi tạo SSL context dùng TLS.

SSL context này vẫn xác minh certificate chain. Hostname verification phải tiếp tục được bật ở HTTP client.

Không tạo `TrustManager` luôn trả về trusted hoặc dùng `SSLContext` chấp nhận mọi certificate. Những cách đó khiến test không còn kiểm tra được danh tính server.

## 12. Cấu hình Spring Data Elasticsearch client dùng SSLContext

Với các phiên bản Spring Data Elasticsearch dùng `ClientConfiguration`, có thể truyền SSL context vào client configuration:

~~~java
import javax.net.ssl.SSLContext;

import org.springframework.data.elasticsearch.client.ClientConfiguration;

ClientConfiguration clientConfiguration(
        String hostAndPort,
        String username,
        String password,
        SSLContext sslContext
) {
    return ClientConfiguration.builder()
            .connectedTo(hostAndPort)
            .usingSsl(sslContext)
            .withBasicAuth(username, password)
            .build();
}
~~~

`hostAndPort` có dạng `hostname:port`; scheme HTTPS được chọn khi cấu hình SSL. Kiểu builder và cách tích hợp với Elasticsearch Java API Client có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy đặt đoạn cấu hình vào `ElasticsearchConfiguration` hoặc client factory phù hợp với dependency của dự án.

Nếu dùng Spring Boot SSL Bundles, có thể khai báo CA certificate trong bundle và lấy SSL context từ `SslBundles`:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        elasticsearch-test:
          truststore:
            certificate: classpath:certs/test-ca.crt
~~~

Ví dụ lấy context:

~~~java
import org.springframework.boot.ssl.SslBundles;

SSLContext sslContext =
        sslBundles.getBundle("elasticsearch-test").createSslContext();
~~~

Sau đó truyền SSL context vào cấu hình Elasticsearch client. Cách khai báo bundle và property tích hợp trực tiếp với Elasticsearch auto-configuration phụ thuộc Spring Boot version; nếu không có property tích hợp tương ứng, dùng custom client configuration như ví dụ trên.

## 13. Basic Authentication và API key không thay thế TLS

Basic Authentication và API key là thông tin xác thực ở tầng HTTP. TLS bảo vệ kênh truyền và xác minh server.

Không gửi username/password hoặc API key qua HTTP không mã hóa trên network không tin cậy. Base64 trong Basic Auth hoặc API key header không phải mã hóa; TLS mới bảo vệ credential khi truyền.

Các lựa chọn:

| Cơ chế | Client gửi | Khi phù hợp |
|---|---|---|
| Basic Auth | Username/password trong Authorization header | Test user đơn giản, service identity |
| API key | Encoded API key trong Authorization header | Role hẹp, credential có thể thu hồi riêng |
| Mutual TLS | Client certificate và private key trong TLS handshake | Môi trường yêu cầu client identity bằng certificate |
| Kết hợp TLS với Basic/API key | HTTPS + một cơ chế auth | Phổ biến cho service-to-service |

Nếu test chỉ dùng HTTP không security, không thể kết luận rằng authentication hoặc TLS production đã được cấu hình đúng.

## 14. Mutual TLS và client certificate

Trong mutual TLS (mTLS), client cũng trình certificate để server xác minh danh tính client. Đây là một lớp khác với việc client trust server certificate.

Cần phân biệt:

- **Truststore**: CA certificate mà client tin cậy khi xác minh server.
- **Keystore**: client certificate và private key mà client dùng để chứng minh danh tính.
- **Server trust configuration**: CA mà Elasticsearch tin cậy để xác minh client certificate.

Trong Elasticsearch, certificate-based client authentication thường cần cấu hình PKI realm và trust chain phù hợp. Chỉ bật HTTPS không có nghĩa Elasticsearch tự động dùng client certificate làm user identity.

Ví dụ cấu trúc cấu hình client cần cả truststore và key material:

~~~java
SSLContext sslContext = buildSslContext(
        serverCaCertificate,
        clientCertificate,
        clientPrivateKey
);
~~~

`buildSslContext(...)` ở đây là hàm minh họa. Cách nạp certificate/private key phụ thuộc định dạng PEM/PKCS12 và API TLS client đang dùng. Không đặt private key client vào truststore; hãy giữ nó trong keystore hoặc secret mount chỉ test process được đọc.

Nếu production không dùng mTLS, không cần thêm mTLS chỉ để test repository query. Nên có suite riêng cho mTLS khi ứng dụng thực sự dựa vào cơ chế đó.

## 15. Cấu hình dynamic cho secured Elasticsearch test instance

Một secured test environment cần cung cấp ít nhất:

- HTTPS URI và mapped port.
- Username/password hoặc API key test.
- CA certificate path hoặc SSL bundle.
- Hostname khớp SAN.
- Role phù hợp với test.
- Thời gian sống certificate đủ cho toàn bộ test run.

Có thể đăng ký property:

~~~java
@DynamicPropertySource
static void securedElasticsearchProperties(
        DynamicPropertyRegistry registry
) {
    registry.add(
            "app.elasticsearch.uri",
            SecuredElasticsearchTestEnvironment::httpsUri
    );
    registry.add(
            "app.elasticsearch.username",
            () -> "test_search_user"
    );
    registry.add(
            "app.elasticsearch.password",
            SecuredElasticsearchTestEnvironment::password
    );
    registry.add(
            "app.elasticsearch.ca-certificate",
            SecuredElasticsearchTestEnvironment::caCertificatePath
    );
}
~~~

`SecuredElasticsearchTestEnvironment` đại diện cho fixture quản lý container/certificate của dự án. Fixture cần khởi động Elasticsearch với HTTP TLS và security đã cấu hình trước khi Spring context tạo client.

Không nên chỉ thêm biến `ELASTIC_PASSWORD` rồi giả định HTTP TLS, CA trust và role đã được thiết lập đầy đủ. Security setting và certificate file phải tương thích với đúng phiên bản Elasticsearch image.

Với test container bảo mật, nên dùng một Docker image hoặc Compose fixture có cấu hình versioned, certificate test và user/role test được tạo rõ ràng. Điều đó dễ lặp lại hơn việc thay đổi nhiều setting bằng script tùy hứng ở mỗi test class.

## 16. Phân biệt test không security và test security

Nên chia test theo mục tiêu:

| Nhóm test | Elasticsearch setup | Điều cần xác nhận |
|---|---|---|
| Mapping/repository integration | Container HTTP đơn giản | Query, mapping, converter, repository |
| TLS integration | HTTPS với test CA | Trust chain, hostname, protocol |
| Authentication integration | HTTPS + test user/API key | Credential hợp lệ và không hợp lệ |
| Authorization integration | Role read/write/admin khác nhau | Quyền cho phép và từ chối |
| mTLS integration | HTTPS + client certificate | Server xác minh client identity |
| Production smoke test | Test/staging environment gần production | Cấu hình thực tế và secret injection |

Không cần bật toàn bộ security cho mọi unit test. Tách suite giúp test thông thường chạy nhanh trong khi vẫn có kiểm tra chuyên biệt cho TLS và authorization.

## 17. Test quyền đọc và ghi bằng credential khác nhau

Có thể cấp hai test identity:

- `test_search_user`: chỉ có quyền read trên index test.
- `test_writer_user`: có quyền write trên index test.
- `test_index_admin`: chỉ dùng trong suite kiểm thử migration/admin.

Kịch bản:

~~~text
Search credential
   ├── Search products-test: allowed
   ├── Index document: denied
   └── Delete index: denied

Writer credential
   ├── Index/update document: allowed
   ├── Search: only if read was granted
   └── Delete index: denied

Index admin credential
   ├── Create test index: allowed
   ├── Update mapping: allowed
   └── Access production index: denied
~~~

Một test nên xác nhận cả success và failure:

~~~java
@Test
void searchCredentialCanReadButCannotWrite() {
    // Search bằng test_search_user phải thành công.
    // Thử index document bằng cùng credential phải bị 403.
}
~~~

Đoạn trên mô tả kịch bản. Trong implementation, có thể dùng hai client bean hoặc khởi tạo client riêng theo credential để kiểm tra quyền thật ở Elasticsearch.

Không dùng credential admin để chạy toàn bộ test rồi chỉ kiểm tra Spring Security endpoint. Cách đó không kiểm tra Elasticsearch role.

## 18. Test certificate lỗi và credential sai

Các trường hợp negative test quan trọng:

| Trường hợp | Kết quả mong đợi |
|---|---|
| CA đúng, hostname đúng, credential đúng | TLS handshake và request thành công |
| CA không được trust | TLS handshake thất bại |
| Certificate hết hạn | Client từ chối certificate |
| Hostname không khớp SAN | Hostname verification thất bại |
| Username/password sai | HTTP 401 |
| API key hết hạn hoặc bị thu hồi | Request bị từ chối |
| User không có quyền index | HTTP 403 hoặc lỗi authorization tương ứng |
| Search user gọi write API | Bị từ chối |
| Writer gọi delete index | Bị từ chối nếu role không có quyền |

Không chỉ kiểm tra exception chung chung. Nếu có thể, xác nhận nguyên nhân ở tầng phù hợp: SSL handshake, hostname verification, authentication hay authorization.

Negative test nên dùng test endpoint và credential riêng, tránh vô tình khóa hoặc thu hồi credential của môi trường dùng chung.

## 19. Quản lý certificate và secret trong CI

CI cần có cách cung cấp certificate và credential mà không đưa chúng vào source control.

Một quy trình phù hợp:

1. Tạo test CA và server certificate ngắn hạn cho mỗi test run hoặc dùng fixture test chuyên biệt.
2. Lưu file certificate ở thư mục tạm của job hoặc mount read-only vào container.
3. Cấp test password/API key từ secret store hoặc tạo mới trong test setup.
4. Đăng ký URI, credentials và CA path bằng dynamic properties.
5. Chạy integration/security tests.
6. Đóng container, client và xóa thư mục certificate tạm.
7. Thu hồi API key nếu dùng cluster dùng chung.
8. Không upload private key, password hoặc API key vào test report/artifact.

Nếu certificate được dùng lại giữa nhiều job, cần có quy trình rotation và thời hạn ngắn. Không dùng một CA private key lâu dài trong repository để ký certificate tùy ý cho mọi test.

Với certificate fixture đã commit, chỉ commit certificate công khai dành riêng cho test. Private key test vẫn cần được kiểm soát; không dùng private key có thể cấp quyền truy cập môi trường thật.

## 20. Không thay đổi truststore JVM toàn cục trong từng test

Có thể cấu hình JVM bằng system property:

~~~text
-Djavax.net.ssl.trustStore=...
-Djavax.net.ssl.trustStorePassword=...
~~~

Cách này ảnh hưởng tới TLS client dùng default JVM trust manager trong process. Khi test suite chạy song song hoặc có nhiều client tới endpoint khác nhau, thay đổi global property có thể gây side effect khó đoán.

Ưu tiên tạo SSL context riêng cho Elasticsearch client:

~~~java
SSLContext elasticsearchSslContext =
        TestSslContexts.trustCertificate(caPath);
~~~

Sau đó gắn SSL context vào client configuration dành riêng cho test.

Nếu bắt buộc dùng JVM truststore, hãy cấu hình từ đầu process, không thay đổi qua lại giữa test method. Đảm bảo test process không dùng chung JVM với workload khác cần truststore khác.

## 21. Dùng @ServiceConnection khi phù hợp

Spring Boot hỗ trợ `@ServiceConnection` cho một số Testcontainers service. Khi container được nhận diện, Boot có thể tự tạo connection details và dùng chúng để cấu hình auto-configuration tương ứng.

Ví dụ hình thức:

~~~java
@Testcontainers
@SpringBootTest
class ProductRepositoryTest {

    @Container
    @ServiceConnection
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    "docker.elastic.co/elasticsearch/elasticsearch:8.15.0"
            );
}
~~~

Khả năng hỗ trợ và loại connection details phụ thuộc phiên bản Spring Boot và Testcontainers module. Kiểm tra dependency trước khi sử dụng.

`@ServiceConnection` hữu ích cho endpoint cơ bản. Khi cần tùy chỉnh username/password, API key, CA path, SSL bundle hoặc index prefix, có thể bổ sung `@DynamicPropertySource` cho các property còn thiếu.

Không đăng ký cùng một URI ở cả service connection và dynamic property với hai giá trị khác nhau. Hãy chọn một nguồn authoritative cho mỗi property.

## 22. Dùng DynamicPropertySource với Spring Data client tùy chỉnh

Nếu ứng dụng có cấu hình client riêng, hãy để dynamic property cung cấp dữ liệu và để bean configuration xây client.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchTestClientProperties(
        String hostAndPort,
        String username,
        String password,
        String caCertificate
) {
}
~~~

Đăng ký giá trị trong test:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "app.elasticsearch.host-and-port",
            SecuredElasticsearchTestEnvironment::hostAndPort
    );
    registry.add(
            "app.elasticsearch.username",
            () -> "test_writer"
    );
    registry.add(
            "app.elasticsearch.password",
            SecuredElasticsearchTestEnvironment::password
    );
    registry.add(
            "app.elasticsearch.ca-certificate",
            SecuredElasticsearchTestEnvironment::caCertificatePath
    );
}
~~~

Client configuration đọc property và tạo SSL context:

~~~java
@Bean
ClientConfiguration elasticsearchClientConfiguration(
        ElasticsearchTestClientProperties properties
) throws Exception {

    SSLContext sslContext = TestSslContexts.trustCertificate(
            Path.of(properties.caCertificate())
    );

    return ClientConfiguration.builder()
            .connectedTo(properties.hostAndPort())
            .usingSsl(sslContext)
            .withBasicAuth(
                    properties.username(),
                    properties.password()
            )
            .build();
}
~~~

Đây là mẫu cấu trúc cho cấu hình client Spring Data. Trong ứng dụng thực tế, đặt bean ở configuration class phù hợp với phiên bản Spring Data Elasticsearch đang dùng và tránh tạo nhiều client nếu chỉ cần một connection.

`@DynamicPropertySource` đăng ký property trong quá trình dựng test context; nó không tự tạo certificate, user hoặc role. Fixture phải chuẩn bị các tài nguyên đó trước khi supplier được gọi.

## 23. Dọn dẹp client và tài nguyên test

Khi test hoàn tất, cần đóng tài nguyên:

- Elasticsearch container.
- Elasticsearch client/transport.
- HTTP low-level client nếu ứng dụng tự tạo.
- PIT hoặc scroll context nếu test tạo ra.
- Temporary certificate và keystore.
- API key được tạo trên cluster dùng chung.
- Index test nếu container không bị hủy.

Nếu dùng Spring context cache, container phải tồn tại đủ lâu cho các test context đang tái sử dụng. Dừng container quá sớm có thể khiến test khác dùng lại context nhưng client trỏ vào endpoint đã chết.

Có thể dùng JUnit lifecycle hoặc Testcontainers lifecycle để quản lý container. Với tài nguyên tạo bằng code như API key và index, dùng cleanup trong `@AfterAll` hoặc fixture quản lý vòng đời tương ứng.

Không xóa index dùng chung ngoài prefix dành riêng cho test. Nên tạo index có tên phân biệt như `it-products-<run-id>` để tránh tác động test khác.

## 24. Các lỗi thường gặp

### Cố định localhost:9200

CI có thể cấp mapped port khác hoặc container không bind vào port cố định. Lấy URI từ Testcontainers rồi đăng ký bằng `@DynamicPropertySource`.

### Đăng ký property sau khi client đã khởi tạo

Spring client có thể giữ endpoint cũ. Đăng ký dynamic property trước khi ApplicationContext tạo bean client.

### Nghĩ container test mặc định kiểm tra TLS

Container đơn giản có thể chạy HTTP và tắt security. Dùng suite secured riêng để xác nhận certificate, authentication và authorization.

### Trust mọi certificate

Cách này làm test vượt qua cả certificate không đáng tin. Trust CA test cụ thể và giữ hostname verification.

### Certificate không có SAN phù hợp

CA có thể đúng nhưng hostname/IP trong URI không khớp SAN. Dùng endpoint và SAN nhất quán.

### Nhầm HTTP TLS với transport TLS

Ứng dụng Spring Data dùng HTTP REST endpoint. Trust certificate đúng cho HTTP layer.

### Commit password hoặc API key

Credential có thể bị lộ qua Git, log và CI artifact. Dùng secret injection hoặc tạo credential test mới theo lifecycle.

### Dùng admin user cho mọi test

Test mapping/query có thể cần quyền rộng, nhưng test authorization cần identity có role thực tế. Tách test credentials theo nhiệm vụ.

### Chỉ kiểm tra request thành công

Không phát hiện role quá rộng hoặc TLS validation bị tắt. Thêm negative test cho sai CA, hostname, password và privilege.

### Thay đổi JVM truststore giữa các test

Global SSL properties ảnh hưởng các client khác và test chạy song song. Ưu tiên SSL context riêng cho Elasticsearch client.

### Dừng container khi Spring context còn dùng

Context cache có thể giữ client trỏ vào container đã dừng. Đồng bộ lifecycle giữa container và test context.

### Dùng certificate hoặc secret production trong test

Test log, report và artifact có thể làm lộ credential. Chỉ dùng CA, key và credential riêng cho test.

## 25. Quy trình triển khai

Khi cấp cấu hình động, certificate và credential cho Spring Data Elasticsearch tests:

1. Chọn loại test: repository integration, TLS, authentication, authorization hay mTLS.
2. Chọn Elasticsearch image/version tương thích và pin version.
3. Khởi động container hoặc test service trước khi Spring tạo context.
4. Lấy URI/host/port từ fixture thay vì hard-code.
5. Đăng ký endpoint và custom properties bằng `@DynamicPropertySource` hoặc `@ServiceConnection` phù hợp.
6. Tạo user/API key test với quyền tối thiểu.
7. Cấp CA certificate để client xác minh HTTPS server.
8. Đảm bảo hostname trong URI khớp SAN của server certificate.
9. Nếu dùng mTLS, cấp client certificate/private key và cấu hình server trust/PKI realm riêng.
10. Tạo SSL context riêng cho Elasticsearch client.
11. Chạy test positive và negative cho TLS, authentication và authorization.
12. Không dùng trust-all, không tắt hostname verification và không dùng credential production.
13. Dùng index prefix riêng cho test.
14. Đóng client/container, xóa file tạm và thu hồi API key khi cần.
15. Theo dõi log nhưng không in credential, private key hoặc Authorization header.

## Tài liệu tham khảo

- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Boot — Testcontainers and service connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot — SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Data Elasticsearch — Client configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Testcontainers — Elasticsearch module](https://java.testcontainers.org/modules/elasticsearch/)
- [Elasticsearch — Encrypt HTTP client communications](https://www.elastic.co/guide/en/elasticsearch/reference/current/configuring-stack-security.html)
- [Elasticsearch — API key authentication](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-create-api-key.html)
- [Elasticsearch — PKI realm](https://www.elastic.co/guide/en/elasticsearch/reference/current/pki-realm.html)
- [Java — SSLContext API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLContext.html)

## Kết luận

Kiểm thử Spring Data Elasticsearch nên nhận endpoint, port, credential và certificate từ fixture hoặc secret source tại thời điểm khởi động. Dùng `@DynamicPropertySource` để đăng ký URI và giá trị động trước khi Spring tạo client; dùng `@ServiceConnection` khi phiên bản Boot/Testcontainers hỗ trợ. Với HTTPS, client phải trust CA đúng và xác minh hostname theo SAN; với mTLS, cần thêm client certificate/private key và cấu hình server tương ứng. Tách test không security khỏi suite TLS/authentication/authorization, dùng user/API key test có quyền tối thiểu, không tắt certificate validation và không đưa secret production vào source, log hoặc artifact.
