# Cấu hình xác thực, SSL và thời gian chờ theo client

## 1. Vì sao mỗi HTTP client cần cấu hình riêng?

Trong **Spring Boot Integration**, một ứng dụng có thể gọi đồng thời nhiều hệ thống bên ngoài: REST API kiểm tra tồn kho, dịch vụ thanh toán, API vận chuyển, hệ thống danh tính hoặc các adapter kết nối broker và cơ sở dữ liệu. Đối với **HTTP đồng bộ**, mỗi lời gọi thường nằm trên đường xử lý mà người dùng hoặc một service khác đang chờ kết quả. Vì vậy, cấu hình HTTP client ảnh hưởng trực tiếp đến **an toàn thông tin, độ trễ và cách hệ thống phục hồi khi lỗi**.

Giả sử Order Service có hai dependency:

| Client | Hệ thống đích | Xác thực | Kết nối TLS | Connect timeout | Read timeout |
| --- | --- | --- | --- | --- | --- |
| `inventoryRestClient` | API tồn kho nội bộ | HTTP Basic theo hợp đồng nội bộ | Tin cậy CA nội bộ | 1 giây | 2 giây |
| `paymentRestClient` | API đối tác thanh toán | API key và định danh chứng chỉ client | CA đối tác + **mTLS** | 2 giây | 5 giây |

Các con số chỉ là **giả định để minh họa**; giá trị thực phải lấy từ độ trễ đo được, khả năng của đích và deadline toàn bộ nghiệp vụ. Hai dependency có hợp đồng và rủi ro khác nhau, nên dùng **hai bean RestClient độc lập** với cấu hình TLS, header xác thực, thời gian chờ và chính sách lỗi tương ứng.

Nếu tái sử dụng một client mặc định cho tất cả đích, rất dễ xảy ra các lỗi như gửi API key của Payment tới Inventory, tin cậy nhầm CA, hoặc dùng read timeout dài của một dịch vụ báo cáo cho thao tác giữ hàng trên đường request. Một thay đổi cấu hình chung có thể vô tình làm sai tất cả luồng tích hợp.

~~~mermaid
flowchart LR
    O["Order Service"] --> I["inventoryRestClient"]
    O --> P["paymentRestClient"]
    I --> A["TLS + Basic + timeout ngắn"]
    P --> B["mTLS + API key + timeout riêng"]
    A --> ID[("Inventory API")]
    B --> PD[("Payment API")]
~~~

Trong bài này dùng **Java 17+, Spring Boot 3.2+ và Spring Framework 6.1+** với `RestClient`. Chữ ký một số API thay đổi giữa các dòng phiên bản, nên cần chọn đúng version trong dự án. Các nguyên tắc vẫn áp dụng cho `RestTemplate` và `WebClient`, nhưng từng HTTP engine có cách cấu hình TLS, pool và timeout riêng.

## 2. Phân biệt xác thực HTTP, HTTPS và thời gian chờ

Ba lớp cấu hình giải quyết ba vấn đề khác nhau:

- **Authentication/authorization ở tầng HTTP**: chứng minh caller là ai, caller được phép thực hiện thao tác gì. Ví dụ `Authorization: Basic ...`, `Authorization: Bearer ...` hoặc `X-API-Key`.
- **TLS/SSL ở tầng truyền tải**: mã hóa kênh và xác minh danh tính endpoint thông qua certificate chain/hostname. **mTLS** còn yêu cầu client trình chứng chỉ của mình cho server. TLS không tự tạo quyền truy cập nghiệp vụ.
- **Timeout và giới hạn tài nguyên**: ngăn thread, socket hoặc pool bị chiếm quá lâu khi DNS, TCP, TLS, gửi request hoặc chờ response gặp vấn đề.

Hai chữ **SSL** thường xuất hiện trong tên thuộc tính và Java API, nhưng trong triển khai HTTPS hiện đại cơ chế được sử dụng là **TLS**. Không bật SSLv3 hay giao thức cũ để khắc phục lỗi handshake; phải sửa cấu hình chứng chỉ, protocol và trust chain đúng cách.

### 2.1. Các loại timeout không đồng nghĩa

| Loại | Phạm vi | Lỗi cần tránh |
| --- | --- | --- |
| **Connection timeout** | Giới hạn thời gian thiết lập kết nối mạng tới endpoint (theo HTTP engine). | Nhầm với thời gian chờ toàn bộ HTTP request. |
| **TLS handshake timeout** | Thời gian thương lượng TLS, có thể do engine/thiết lập riêng kiểm soát. | Giả định mọi thư viện đều dùng `connectTimeout` để chặn toàn bộ handshake. |
| **Connection pool acquisition timeout** | Chờ lấy connection từ pool khi pool đã đầy. | Chỉ đặt connect/read timeout nhưng vẫn có thể chờ pool quá lâu. |
| **Read/response timeout** | Giới hạn việc chờ phản hồi/đọc response theo semantics của request factory. | Nhầm là deadline tổng request, bao gồm mọi lần retry. |
| **Total operation deadline** | Ngân sách thời gian từ lúc bắt đầu nghiệp vụ đến khi cần kết quả cuối. | Cho nhiều attempt nối tiếp làm vượt hạn mà caller còn chờ. |
| **Retry backoff** | Thời gian nghỉ giữa các attempt hợp lệ. | Ngủ/chờ trong transaction đang giữ lock hoặc connection DB. |

Thông số timeout của các HTTP engine có thể khác nhau: chẳng hạn timeout đọc có thể áp cho mỗi lần đọc hay một lần nhận response, và DNS lookup không nhất thiết được bao phủ bởi TCP connection timeout. Đọc rõ tài liệu của **request factory/HTTP client implementation** đang chạy và kiểm thử bằng server cố ý trì hoãn.

## 3. Cấu hình thuộc tính theo từng đích

Đầu tiên, tách URL và timeout của mỗi client dưới prefix có ý nghĩa:

~~~yaml
# application.yml
app:
  http:
    inventory:
      base-url: https://inventory.internal.example
      connect-timeout: 1s
      read-timeout: 2s
    payment:
      base-url: https://api.payment.example
      connect-timeout: 2s
      read-timeout: 5s
    auth:
      inventory-username: ${INVENTORY_USERNAME}
      inventory-password: ${INVENTORY_PASSWORD}
      payment-api-key: ${PAYMENT_API_KEY}

spring:
  ssl:
    bundle:
      pem:
        inventory:
          truststore:
            certificate: classpath:tls/inventory-ca.pem
        payment:
          truststore:
            certificate: file:/run/secrets/payment-ca.pem
          keystore:
            certificate: file:/run/secrets/payment-client-chain.pem
            private-key: file:/run/secrets/payment-client-key.pem
~~~

Trong ví dụ:

1. `app.http.inventory` và `app.http.payment` xác định cấu hình nghiệp vụ cho từng HTTP client; Spring Boot không tự biết hai prefix tùy chỉnh này nếu chưa có bean đọc chúng.
2. `spring.ssl.bundle.pem.inventory` chứa **certificate tin cậy để xác minh server Inventory**. Nếu hệ thống dùng certificate do một CA công khai được JVM mặc định tin cậy, không nhất thiết phải thêm truststore riêng.
3. `spring.ssl.bundle.pem.payment` chứa **truststore cho server Payment** và **keystore chứa chứng chỉ/khóa riêng của client** để thực hiện mTLS khi đích yêu cầu.
4. Các file dưới `/run/secrets` đại diện cho đường dẫn do nền tảng triển khai mount vào container; cần cung cấp file thật, quyền chỉ đọc phù hợp và cơ chế rotation. Chứng chỉ CA công khai có thể đóng gói vào resources, nhưng **private key và mật khẩu không nên commit vào repository**.
5. Giá trị từ `${...}` ở phần mã nguồn YAML được sử dụng theo cú pháp property placeholder của Spring; lúc triển khai, các giá trị được lấy từ biến môi trường hoặc nguồn bí mật tương ứng. Nếu chưa có giá trị, ứng dụng nên **fail fast** lúc khởi tạo thay vì khởi chạy với chuỗi rỗng.

Không dùng chung API key và private key của Payment cho các dịch vụ khác. Nếu một tài khoản/tenant có credential riêng, chính sách tách client và lưu bí mật phải phản ánh ranh giới đó.

> **Lưu ý về truststore:** Khi chỉ định một tập CA tùy chỉnh, client có thể không còn sử dụng toàn bộ các root CA của JVM tùy cách tạo `SSLContext`. Cần kiểm tra trust chain thật của từng đích, nhất là khi dịch vụ chuyển từ CA nội bộ sang CA công khai.

## 4. Khai báo properties có kiểu thay vì đọc chuỗi rời rạc

Spring Boot có thể bind các chuỗi thời gian như `1s`, `500ms` hoặc `2m` về `Duration`. Dùng record để gom cấu hình:

~~~java
// HttpClientsProperties.java
package com.example.integration.http;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.http")
public record HttpClientsProperties(
        Endpoint inventory,
        Endpoint payment) {

    public record Endpoint(
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout) {}
}
~~~

Record giúp cấu hình có type cụ thể; có thể bổ sung `jakarta.validation` và `@Validated` để kiểm tra URL, duration phải dương và các field bắt buộc. Ví dụ như `@NotNull`/`@Positive` trên giá trị phù hợp giúp phát hiện cấu hình sai trước khi nhận traffic.

Không nhận `baseUrl` từ input của người dùng tại runtime; làm như vậy dễ phát sinh **SSRF** và chuyển tiếp header xác thực đến máy chủ ngoài dự kiến. Client gọi các hệ thống đích đã biết nên dùng URL được kiểm soát bởi cấu hình triển khai.

## 5. Hai RestClient với TLS và timeout độc lập

**Spring Boot SSL bundle** cung cấp `SslBundles` để lấy cấu hình truststore/keystore theo tên và tạo `SSLContext`. Ví dụ bên dưới dùng Java `HttpClient` cùng `JdkClientHttpRequestFactory`; mỗi client có request factory, SSL context và thời gian chờ riêng.

~~~java
// DownstreamHttpConfiguration.java
package com.example.integration.http;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(HttpClientsProperties.class)
public class DownstreamHttpConfiguration {

    @Bean("inventoryRestClient")
    RestClient inventoryRestClient(
            RestClient.Builder builder,
            HttpClientsProperties properties,
            SslBundles sslBundles,
            @Value("${app.http.auth.inventory-username}") String username,
            @Value("${app.http.auth.inventory-password}") String password) {

        return securedBuilder(
                    builder,
                    properties.inventory(),
                    sslBundles.getBundle("inventory"))
                .defaultHeaders(headers -> headers.setBasicAuth(username, password))
                .build();
    }

    @Bean("paymentRestClient")
    RestClient paymentRestClient(
            RestClient.Builder builder,
            HttpClientsProperties properties,
            SslBundles sslBundles,
            @Value("${app.http.auth.payment-api-key}") String apiKey) {

        return securedBuilder(
                    builder,
                    properties.payment(),
                    sslBundles.getBundle("payment"))
                .defaultHeader("X-API-Key", apiKey)
                .build();
    }

    private RestClient.Builder securedBuilder(
            RestClient.Builder builder,
            HttpClientsProperties.Endpoint endpoint,
            SslBundle bundle) {

        HttpClient jdkHttpClient = HttpClient.newBuilder()
                .connectTimeout(endpoint.connectTimeout())
                .sslContext(bundle.createSslContext())
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(jdkHttpClient);
        factory.setReadTimeout(endpoint.readTimeout());

        return builder.clone()
                .baseUrl(endpoint.baseUrl().toString())
                .requestFactory(factory);
    }
}
~~~

Những chi tiết đáng chú ý:

- `RestClient.Builder` là builder từ Spring Boot, cho phép giữ các customization phù hợp của ứng dụng. Dùng `clone()` trước khi cấu hình tránh làm thay đổi không chủ ý builder dùng cho nơi khác.
- `SslBundles.getBundle("inventory")` và `getBundle("payment")` chọn hai bộ thông tin TLS theo tên. `createSslContext()` tạo context từ trust/key material của bundle tương ứng.
- `HttpClient.newBuilder().connectTimeout(...)` giới hạn bước thiết lập kết nối. `JdkClientHttpRequestFactory.setReadTimeout(Duration)` cấu hình timeout phía request theo hỗ trợ của Spring Framework 6.1+. **Đây không phải một deadline bao trùm toàn bộ retries**.
- `followRedirects(HttpClient.Redirect.NEVER)` giảm nguy cơ tự đi theo `Location` tới hostname khác kèm credential; nếu nghiệp vụ cần redirect, phải có chính sách allowlist và kiểm tra header.
- `headers.setBasicAuth(...)` chỉ phù hợp nếu Inventory thực sự yêu cầu Basic. Basic **mã hóa Base64 chứ không mã hóa bí mật**; phải chạy trên HTTPS với server certificate được xác minh.
- `X-API-Key` là tên header do ví dụ giả định; header, token format và cách rotation phải theo hợp đồng API Payment. Một số đối tác yêu cầu `Authorization: Bearer` thay cho API key.
- `@Bean("inventoryRestClient")` và `@Bean("paymentRestClient")` có tên độc lập; tại điểm gọi cần dùng `@Qualifier` để tránh chọn nhầm client.

Để ví dụ tập trung vào xác thực/SSL/timeout, cấu hình trên dùng Java JDK HTTP engine, chưa tự kiểm soát các thông số chuyên sâu của **connection pool acquisition**, proxy hoặc HTTP/2 multiplexing. Với workload có lưu lượng lớn cần pool/connection leasing timeout chuyên biệt, xem xét Apache HttpClient 5 (qua `HttpComponentsClientHttpRequestFactory`) và cấu hình riêng toàn bộ pool, TLS và timeout. **Không trộn một phần cấu hình JDK client với Apache request factory rồi nghĩ các option sẽ được áp dụng qua lại**.

### 5.1. Nạp client đúng đích tại lớp nghiệp vụ

~~~java
// InventoryClient.java
package com.example.integration.inventory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {
    private final RestClient client;

    public InventoryClient(
            @Qualifier("inventoryRestClient") RestClient client) {
        this.client = client;
    }

    public StockReply stock(String sku) {
        StockReply reply = client.get()
                .uri(uri -> uri.path("/v1/stock/{sku}").build(sku))
                .retrieve()
                .body(StockReply.class);
        if (reply == null) {
            throw new IllegalStateException("Inventory returned no body");
        }
        return reply;
    }
}

record StockReply(String sku, int available) {}
~~~

~~~java
// PaymentClient.java
package com.example.integration.payment;

import java.math.BigDecimal;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PaymentClient {
    private final RestClient client;

    public PaymentClient(
            @Qualifier("paymentRestClient") RestClient client) {
        this.client = client;
    }

    public PaymentReply authorize(PaymentCommand command) {
        PaymentReply reply = client.post()
                .uri("/v1/authorizations")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Idempotency-Key", command.operationId())
                .body(command)
                .retrieve()
                .body(PaymentReply.class);
        if (reply == null) {
            throw new IllegalStateException("Payment returned no body");
        }
        return reply;
    }
}

record PaymentCommand(String operationId, BigDecimal amount) {}
record PaymentReply(String authorizationId, String status) {}
~~~

Mỗi class ở ví dụ nên đặt trong file/source package phù hợp, các DTO có thể là các class/record riêng nếu dùng ngoài package. Không ghép hai class `PaymentClient` và `InventoryClient` thành một client dùng chung header; bước wiring bằng `@Qualifier` là một phần của việc kiểm soát credential.

Hợp đồng Payment `Idempotency-Key` phải được **đối tác hỗ trợ**. Header không tự bảo đảm chống trùng: người gọi phải giữ cùng `operationId` khi retry cùng thao tác, đối tác phải ràng buộc ID với payload và lưu kết quả đủ lâu.

## 6. Những phương án xác thực HTTP thường dùng

| Phương án | Gửi như thế nào? | Trường hợp phù hợp | Điều cần kiểm soát |
| --- | --- | --- | --- |
| **Basic Authentication** | `Authorization: Basic base64(user:pass)` | API nội bộ/di sản có hợp đồng Basic. | Chỉ dùng HTTPS; bảo vệ mật khẩu và tránh gửi sang host khác. |
| **API key** | Header do đối tác chỉ định, ví dụ `X-API-Key`. | API đối tác dùng shared secret. | Phân quyền và rotation theo môi trường/tenant; tránh log key. |
| **OAuth2 Bearer token** | `Authorization: Bearer <access_token>`. | API được bảo vệ bằng OAuth2/OIDC. | Token scope/audience, expiry, cache, refresh, xử lý 401. |
| **mTLS** | Chứng chỉ client trong TLS handshake. | B2B, service-to-service yêu cầu định danh thiết bị/workload. | Certificate chain, private key, thời hạn và rotation. |
| **Request signature/HMAC** | Header chữ ký tạo từ payload và timestamp theo hợp đồng. | Đối tác yêu cầu chống sửa nội dung/chống replay ở tầng ứng dụng. | Canonicalization, clock skew, nonce, secret và phiên bản giao thức. |

Trong hệ thống thực, các cơ chế có thể được **kết hợp**: Payment yêu cầu mTLS **và** API key; một API khác yêu cầu mTLS **và** Bearer token. Không dùng certificate client mTLS làm bằng chứng duy nhất rằng caller được phép thực hiện mọi hành động; server vẫn phải áp authorization.

### 6.1. Bearer token động: gắn khi gửi request

Không đặt Bearer token sắp hết hạn vào `defaultHeader` tại thời điểm khởi tạo bean rồi dùng mãi. Nếu token có TTL ngắn, lấy token hợp lệ **trước từng request** thông qua một provider biết cache và làm mới an toàn:

~~~java
// Hợp đồng provider do thành phần OAuth2 client thực hiện.
public interface AccessTokenSource {
    String validAccessToken();
}

// Ví dụ cấu hình interceptor bên trong bean RestClient tương ứng:
return securedBuilder(builder, endpoint, sslBundle)
        .requestInterceptor((request, body, execution) -> {
            request.getHeaders().setBearerAuth(tokenSource.validAccessToken());
            return execution.execute(request, body);
        })
        .build();
~~~

Đoạn này là **mảnh cấu hình minh họa**; biến `tokenSource`, `builder`, `endpoint` và `sslBundle` phải được cung cấp bởi bean tương ứng. Có thể hiện thực `AccessTokenSource` bằng Spring Security OAuth2 Client với grant `client_credentials` nếu ứng dụng gọi máy–máy, dùng `OAuth2AuthorizedClientManager` hoặc API tương đương theo version đã chọn.

Provider phải:

1. Dùng token cache theo **client registration, principal/service identity và scope** đúng ngữ cảnh.
2. Làm mới hoặc xin token trước expiry (chừa clock skew); tránh nhiều thread đồng loạt xin token mới.
3. Không gửi token cho endpoint khác audience/scope và không cho token xuất hiện trong log/tracing.
4. Khi `401 Unauthorized`, kiểm tra nguyên nhân; nếu do token hết hạn, có thể **invalidating cache và thử lại có kiểm soát một lần** khi an toàn. `403 Forbidden` thường là lỗi quyền/scope, không nên được xử lý như token hết hạn.
5. Phân biệt lỗi máy chủ cấp token với lỗi API nghiệp vụ và áp timeout riêng cho token endpoint nếu nó cũng là một HTTP client.

Spring Security quản lý token giúp tránh tự viết toàn bộ vòng đời OAuth2. Với user-delegated token, không tráo token người dùng giữa các request/tenant; việc chọn principal và client registration phải theo ngữ cảnh bảo mật.

### 6.2. Không để credential vô tình rò qua redirect và log

Giới hạn host đích, chỉ cho HTTPS và xem lại chính sách redirect. Không log toàn bộ `Authorization`, `X-API-Key`, cookie hoặc client private key. Nếu cần HTTP wire logging khi chẩn đoán, hãy bật có kiểm soát trong môi trường an toàn và cấu hình mask header. Trace ID, operation ID, HTTP status và latency thường đủ để phân tích lỗi mà không cần ghi credential.

## 7. TLS, truststore, keystore và xác minh hostname

Trong HTTPS, client phải xác minh server certificate hợp lệ theo trust anchors:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant S as HTTPS Server
    C->>S: ClientHello, các phiên bản TLS hỗ trợ
    S-->>C: ServerHello và certificate chain
    C->>C: Kiểm tra chain, hiệu lực và hostname
    opt Server yêu cầu mTLS
        S-->>C: Yêu cầu chứng chỉ client
        C->>S: Client certificate và bằng chứng sở hữu private key
        S->>S: Xác minh client certificate và quyền
    end
    C->>S: HTTP request qua kênh TLS
    S-->>C: HTTP response qua kênh TLS
~~~

**Truststore** chứa certificate/CA mà client tin cậy để xác minh **server**. **Keystore** trong ví dụ chứa danh tính certificate và private key của **client** để mTLS. Mỗi loại có mục đích khác nhau:

- **Tin cậy server:** chain phải dẫn tới trust anchor phù hợp; tên host trong URL phải khớp **Subject Alternative Name (SAN)** của certificate. Nếu gọi `https://inventory.internal.example`, certificate chỉ dành cho một hostname khác sẽ không hợp lệ dù CA được tin cậy.
- **Chứng chỉ client mTLS:** server kiểm tra certificate và bên gọi chứng minh có private key tương ứng. Certificate có thể cần đúng Extended Key Usage, issuer và chính sách phía server.
- **Rotation:** thay certificate/CA hoặc private key cần kế hoạch overlap thời gian, kiểm tra tải lại cấu hình và restart bean/process nếu HTTP engine không tự reload SSL context. Không mặc định sửa file certificate trên volume sẽ làm mọi HTTP client đã tạo nhận certificate mới ngay lập tức.
- **Protocol/cipher:** dùng TLS 1.2/1.3 theo chính sách của tổ chức và hỗ trợ của server. Đừng hạ cấp bảo mật chỉ vì client gặp handshake failure.

**Tuyệt đối không khắc phục lỗi bằng TrustManager “trust all” hoặc tắt hostname verification.** Việc đó làm mất xác thực peer và mở đường cho tấn công trung gian. Đối với chứng chỉ tự ký trong môi trường phát triển, hãy thêm CA/certificate cần tin cậy vào truststore **riêng của môi trường thử nghiệm**.

### 7.1. PEM và JKS/PKCS12

Spring Boot hỗ trợ SSL bundles dạng **PEM** và **JKS**. Với certificate/key dạng PEM, ví dụ mục 3 phù hợp; với hệ thống lưu trust material trong JKS/PKCS12, có thể cấu hình bundle dạng JKS:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        legacy-partner:
          truststore:
            location: file:/run/secrets/legacy-truststore.p12
            password: ${LEGACY_TRUSTSTORE_PASSWORD}
            type: PKCS12
          keystore:
            location: file:/run/secrets/legacy-client.p12
            password: ${LEGACY_KEYSTORE_PASSWORD}
            type: PKCS12
~~~

Sau đó lấy `sslBundles.getBundle("legacy-partner")` tại đúng bean client. Trước khi dùng, xác minh file chứa chain/khóa đúng, mật khẩu, alias nếu cần và cách bundle đọc certificate. Không gộp mọi truststore của toàn hệ thống vào một cấu hình mặc định chỉ để một client kết nối được.

## 8. Timeout, deadline và ngân sách độ trễ

Giả sử endpoint Order có SLO phản hồi 3 giây ở phần lớn request. Nếu xử lý nội bộ và DB mất khoảng 600 ms, phần thời gian còn lại **không thể** dành toàn bộ cho mỗi dependency:

~~~text
Deadline request tổng:         3000 ms
  Kiểm tra/auth nội bộ:         150 ms
  Transaction Orders DB:       450 ms
  Gọi Inventory:              1200 ms
  Xử lý/mapping và dự phòng:    200 ms
  Dự phòng biến động:          1000 ms
~~~

Các số liệu minh họa; cần kiểm tra p95/p99, tính đồng thời và thứ tự thực tế. Nếu Inventory đọc trong 2 giây rồi Payment đọc thêm 5 giây **nối tiếp**, tổng thời gian có thể vượt deadline 3 giây dù từng client được cấu hình timeout “hợp lệ”.

Một nguyên tắc tốt là:

1. Đặt **connect timeout ngắn** theo điều kiện mạng thực tế; connect timeout kéo dài dễ giữ thread khi đích không thể kết nối.
2. Chọn **response/read timeout theo latency budget của thao tác cụ thể**, không chỉ theo giá trị mặc định của HTTP engine.
3. Với nhiều request nối tiếp hoặc retry, tính một **deadline từ đầu đến cuối**. Trước attempt mới phải kiểm tra thời gian còn lại.
4. Nếu có connection pool, tính thêm thời gian chờ lấy connection và giới hạn pool/số call đồng thời.
5. Đối với công việc có thể xử lý sau, đưa vào queue/worker có theo dõi trạng thái thay vì giữ request HTTP quá lâu.

**Không đánh đồng timeout với thất bại nghiệp vụ.** Ví dụ Payment đã ghi nhận một authorization nhưng phản hồi bị mất, client có thể thấy read timeout. Nếu thử lại bằng operation ID mới, có nguy cơ ghi nhận giao dịch trùng. Dùng idempotency key, API tra cứu trạng thái và reconciliation theo hợp đồng.

### 8.1. Timeout và transaction database

Không giữ transaction JPA/JDBC mở trong lúc gọi HTTP tới đối tác rồi chờ nhiều giây, trừ khi có lý do được thiết kế và đánh giá rất kỹ: connection và lock có thể bị chiếm lâu, trong khi rollback local DB **không** rollback được side effect ở hệ thống HTTP. Với luồng thanh toán kéo dài, dùng trạng thái `PENDING`, outbox/saga hoặc bước xác nhận riêng để tránh phụ thuộc vào transaction phân tán tưởng tượng.

## 9. Xử lý HTTP status, retry và lỗi xác thực

`RestClient.retrieve()` mặc định xử lý status 4xx/5xx bằng exception tương ứng. Không nên catch `Exception` rồi retry tất cả: authentication failure, dữ liệu sai và timeout sau side effect có ý nghĩa khác nhau.

| Tình huống | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| `401 Unauthorized` | Thiếu/sai credential, token hết hạn hoặc không hợp lệ. | Xác minh cấu hình; refresh token nếu phù hợp, giới hạn số lần thử. |
| `403 Forbidden` | Đã được xác thực nhưng không đủ quyền/scope hoặc bị chặn chính sách. | Sửa quyền/cấu hình với chủ sở hữu API; không retry mù. |
| `429 Too Many Requests` | Vượt quota phía đích. | Tôn trọng `Retry-After`, rate limit theo đích, retry budget và backoff. |
| `400`/`422` | Sai hợp đồng hoặc validation theo API. | Sửa payload; không retry dữ liệu y hệt. |
| `409 Conflict` | Xung đột nghiệp vụ/trạng thái. | Phân tích ý nghĩa theo contract và trạng thái idempotency. |
| `500`/`502`/`503` | Lỗi tạm thời hoặc đích không sẵn sàng. | Retry có giới hạn khi an toàn; circuit breaker và đối soát. |
| `SocketTimeoutException`/I/O timeout | Chậm response, network, proxy; không chắc đích đã xử lý chưa. | Kiểm tra idempotency/tra cứu trạng thái trước khi thử lại tác vụ có side effect. |
| `SSLHandshakeException` | Chain, hostname, protocol hoặc certificate client không khớp. | Khắc phục TLS; retry với cùng cấu hình sai thường vô ích. |

Muốn xử lý `429` tại client Payment, có thể dùng `onStatus` để đổi sang exception nghiệp vụ và giữ `Retry-After`:

~~~java
PaymentReply reply = client.post()
        .uri("/v1/authorizations")
        .body(command)
        .retrieve()
        .onStatus(
                code -> code.value() == 429,
                (request, response) -> {
                    String retryAfter =
                            response.getHeaders().getFirst("Retry-After");
                    throw new PaymentRateLimitedException(retryAfter);
                })
        .body(PaymentReply.class);
~~~

`PaymentRateLimitedException` là exception ứng dụng cần định nghĩa trong dự án; đoạn mã cho thấy vị trí xử lý status, không phải toàn bộ client hoàn chỉnh. `Retry-After` có thể là **số giây** hoặc **HTTP-date**, phải parse tương ứng, kiểm tra deadline và đặt ngưỡng chờ. Không tự coi mọi `429` là lỗi có thể retry tức thì.

**Retry phải đi qua cùng bộ giới hạn outbound**: nếu ứng dụng giới hạn 50 operation/giây nhưng mỗi operation có thể thử HTTP ba lần bên trong, tải thực tế có thể đạt 150 attempt/giây. Các lớp retry trong HTTP client, service và broker consumer phải phối hợp cùng retry budget để tránh retry storm.

## 10. Cấu hình theo client trong luồng Spring Integration

Spring Integration thường đặt HTTP client sau một `Gateway` hoặc `Service Activator`. Dù gọi REST bên trong `IntegrationFlow` hay trực tiếp từ service, vẫn nên tái sử dụng đúng các client chuyên biệt:

~~~mermaid
flowchart LR
    Q["Inbound HTTP / Broker"] --> C["MessageChannel"]
    C --> V["Validate + Transform"]
    V --> R{"Route theo đích"}
    R -->|Inventory| I["InventoryClient"]
    R -->|Payment| P["PaymentClient"]
    I --> IB["inventoryRestClient"]
    P --> PB["paymentRestClient"]
    IB --> D1[("Inventory")]
    PB --> D2[("Payment")]
~~~

Điều quan trọng không phải số lượng flow, mà là **credential và SSL context không thoát khỏi phạm vi client được phân công**. Khi có nhiều tên channel hoặc adapter, định nghĩa rõ contract request/reply, response timeout và cách chuyển lỗi trở lại flow.

Với `DirectChannel`, service handler thường chạy trong thread của sender; read timeout kéo dài trực tiếp làm chậm caller. Với `ExecutorChannel`, chuyển sang thread khác **không làm request trở thành bền vững** và không tự chuyển transaction/thread-local security context. Hãy cấu hình timeout, giới hạn concurrency, queue và xử lý lỗi tương ứng với kênh được dùng.

Nếu phải gọi Payment sau khi commit Order, cân nhắc outbox/queue thay vì thực hiện một lời gọi dài trong transaction Orders. Cả khi sử dụng broker như Kafka/RabbitMQ, duplicate delivery và trạng thái kết quả không chắc chắn vẫn cần idempotency key và phép đối soát.

## 11. Kiểm thử cấu hình xác thực, TLS và timeout

Mỗi RestClient nên có bộ test riêng vì hai cấu hình bảo mật độc lập. Nên kiểm thử cả **đường thành công** và **các trường hợp bị từ chối**:

| Kiểm thử | Điều cần xác minh |
| --- | --- |
| Inventory gửi Basic Auth | Header hợp lệ chỉ đến host Inventory; secret được che trong log. |
| Payment gửi API key + mTLS | Header đúng, client xuất trình chứng chỉ đúng, server chấp nhận chain. |
| Server certificate ký bởi CA khác | TLS handshake thất bại theo chính sách truststore, không tự bỏ qua xác minh. |
| Certificate đúng CA nhưng hostname/SAN sai | Kết nối bị từ chối do hostname verification. |
| Chứng chỉ mTLS thiếu/hết hạn/sai key | Kết nối bị từ chối, có tín hiệu quan sát phù hợp. |
| Inventory chậm hơn read timeout | Client chấm dứt chờ theo request factory; caller nhận lỗi được phân loại. |
| Connection không thiết lập được | Connect timeout có giới hạn, không giữ thread vô hạn. |
| Payment trả 401/403 | Không retry vô hạn và không gửi lại với credential của client khác. |
| Payment trả 429 + Retry-After | Retry tôn trọng hạn mức và deadline, không tạo burst. |
| Payment timeout sau khi đã commit | Giữ nguyên operation ID/idempotency key; tra cứu trạng thái trước thao tác mới. |
| Client bị redirect sang host lạ | Không tự chuyển tiếp header xác thực. |
| Hai client chạy song song | Timeout, truststore và thông tin đăng nhập của từng client không bị dùng chéo. |

Có thể dùng `MockRestServiceServer` để kiểm tra header, URI, body và mapping HTTP status trong các trường hợp phù hợp. **Mock request-response ở tầng RestClient không tự kiểm chứng TLS handshake hoặc timeout mạng thật**; phần này cần HTTPS test server (có chứng chỉ và hành vi trì hoãn được cấu hình), ví dụ embedded server hoặc sandbox, cùng truststore/keystore thử nghiệm.

Một chiến lược đáng tin cậy là tạo bộ test HTTPS riêng có: CA đáng tin, CA không đáng tin, certificate SAN sai, server yêu cầu client certificate và server cố ý delay response. Thử cả việc hết thời gian chờ kết nối và đọc, rồi xác minh chính xác client nào bị ảnh hưởng. Certificate/key thử nghiệm nên có vòng đời riêng và không chứa thông tin production.

### 11.1. Quan sát và chẩn đoán lỗi

Ghi metric theo tên đích và operation, không theo URL chứa ID động có cardinality cao:

- HTTP request rate, error rate, latency p50/p95/p99, timeout, số lần retry và số request đang chờ.
- Tỷ lệ 401/403, 429, lỗi TLS handshake và sự cố certificate sắp hết hạn.
- Connection pool usage và thời gian chờ lấy connection nếu engine có pool đo được.
- End-to-end deadline miss, circuit breaker state, số thao tác chờ đối soát do kết quả không chắc chắn.

Khi có lỗi TLS, ưu tiên xác minh endpoint, DNS, chain và SAN bằng công cụ kiểm tra certificate đáng tin cậy. Có thể bật log TLS handshake trong môi trường kiểm soát để chẩn đoán, nhưng tránh giữ verbose SSL logging ở production lâu dài vì log có thể lớn và chứa metadata nhạy cảm. Không in private key, token hay request body chứa dữ liệu thanh toán.

## 12. Checklist thiết kế HTTP client theo đích

- [ ] Mỗi hệ thống đích có client bean, URL, credential, SSL bundle và timeout được định danh rõ.
- [ ] Xác thực HTTP phù hợp hợp đồng API: Basic/API key/Bearer; token động có cache/refresh/expiry hợp lý.
- [ ] HTTPS xác minh đầy đủ chain và hostname, mTLS có certificate/key đúng và kế hoạch rotation; không có bypass trust-all.
- [ ] Timeout của connection, response, pool acquisition và deadline tổng được kiểm tra theo HTTP engine thực tế.
- [ ] Lời gọi có side effect dùng idempotency key, trạng thái nghiệp vụ và đối soát khi không rõ kết quả.
- [ ] Retry, rate limiter, bulkhead/circuit breaker và điều phối broker không phát vượt năng lực đích.
- [ ] Test xác thực, lỗi TLS, timeout và redirect bằng các client riêng; có quan sát mà không lộ secret.
- [ ] Các khóa bí mật được cung cấp qua cơ chế bí mật an toàn, phân quyền tối thiểu, có kiểm soát phiên bản và rotation.

**Cấu hình xác thực, SSL và thời gian chờ theo client** là cách thể hiện rõ ranh giới giữa các dependency trong Spring Boot Integration. Một `RestClient` dành riêng cho Inventory và một `RestClient` dành riêng cho Payment giúp thực thi đúng hợp đồng bảo mật và deadline của từng hệ thống. Khi kết hợp với phân loại lỗi, giới hạn retry, idempotency, transaction phù hợp và kiểm thử TLS thực tế, các luồng tích hợp HTTP đồng bộ sẽ dễ chẩn đoán và phục hồi hơn trước những lỗi mạng hoặc lỗi đối tác.
