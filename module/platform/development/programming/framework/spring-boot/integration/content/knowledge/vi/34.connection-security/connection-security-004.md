# mTLS và xác thực hai chiều giữa các dịch vụ

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức tích hợp qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration. Một service nhận đơn hàng có thể gọi Inventory API, truy vấn PostgreSQL, sử dụng Redis và phát sự kiện sang Kafka. Mỗi kết nối đều cần bảo vệ dữ liệu, nhưng với những luồng nhạy cảm, chỉ mã hóa đường truyền chưa đủ: **service nhận request cũng cần xác minh service đang gọi là ai**.

**Mutual TLS (mTLS)** là cơ chế xác thực **hai chiều bằng chứng chỉ X.509 trong quá trình bắt tay TLS**. Với TLS thông thường, client xác minh chứng chỉ của server. Với mTLS, server còn yêu cầu và xác minh **chứng chỉ của client**. Sau khi bắt tay thành công, các bên thiết lập kênh TLS được mã hóa; ứng dụng tiếp tục thực thi chính sách **authorization** riêng.

Bài thuộc chương **Bảo mật kết nối**, tập trung vào **mTLS và xác thực hai chiều giữa các dịch vụ**, với ví dụ Spring Boot inbound server, `RestClient`, `WebClient`, chứng chỉ PKI, SSL bundles và các ranh giới tích hợp SQL/cache/broker. Trọng tâm không chỉ là “HTTPS chạy được”, mà còn là cấu hình nhất quán, hợp đồng identity, luân chuyển chứng chỉ, phân loại lỗi, kiểm thử và observability.

Sau bài học, bạn có thể:

1. Phân biệt TLS mã hóa, server authentication, mutual authentication và application authorization.
2. Hiểu private key, certificate chain, CA trust, SAN, EKU, keystore và truststore.
3. Bật `server.ssl.client-auth=need` và cấu hình SSL bundle cho một Spring Boot service.
4. Tạo outbound mTLS client bằng `RestClient` hoặc `WebClient` mà không tắt hostname verification.
5. Hiểu mTLS tại load balancer/service mesh và nguy cơ tin giả header forwarded identity.
6. Thiết kế chính sách danh tính, expiry/rotation, secrets, observability và failure handling.
7. Kiểm thử cả trường hợp handshake thành công và bị từ chối: không có client cert, sai CA, sai host, hết hạn.
8. Tách mTLS transport security khỏi retry, idempotency và transaction của luồng tích hợp.

> **Ranh giới:** mTLS xác minh peer qua chứng chỉ trong một **kết nối TLS**, không tự xác thực người dùng cuối, không cấp quyền truy cập nghiệp vụ, không chống phát lại một yêu cầu đã được gửi hợp lệ và không thay thế transaction/outbox.

## 1. Vì sao HTTPS thông thường chưa đủ?

Giả sử Order Service gọi Inventory Service:

~~~text
Order Service  ── HTTPS ──>  Inventory Service
    client                      server
~~~

Với HTTPS một chiều, Order Service xác minh tên miền và certificate chain của Inventory Service. Inventory Service có thể chỉ thấy IP của caller và một bearer token; nếu token bị lộ hoặc network policy chưa chặt, kẻ khác có thể cố gọi endpoint.

Với mTLS:

~~~text
Order Service  ══ mTLS ══>  Inventory Service
 client certificate            server certificate
  + private key                 + private key
  verifies server              verifies client
~~~

Bên gọi phải chứng minh quyền sở hữu **private key** tương ứng với client certificate trong handshake; server xác minh chain và chính sách chứng chỉ. Client đồng thời kiểm tra server certificate và hostname.

### 1.1. Những mục tiêu bảo mật khác nhau

| Cơ chế | Cung cấp | Không tự bảo đảm |
| --- | --- | --- |
| TLS/HTTPS | Mã hóa và tính toàn vẹn trên kết nối; xác thực server khi cấu hình đúng | Identity của client |
| mTLS | Xác thực cả client và server bằng certificate chain/private key | Quyền nghiệp vụ của caller |
| OAuth2/JWT | Claims, scope, audience và cơ chế ủy quyền theo token | An toàn transport nếu TLS bị bỏ |
| NetworkPolicy/Firewall | Giới hạn nguồn và đích có thể kết nối | Identity mật mã của service |
| Signed request/message | Có thể xác thực nội dung ở mức message theo scheme | Tự động cấu hình TLS/transport |
| Idempotency key | Hạn chế xử lý trùng một nghiệp vụ theo contract | Xác thực peer hoặc mã hóa |
| Authorization policy | Cho phép service identity thực hiện hành động xác định | Mã hóa và handshake TLS |

**mTLS và OAuth2 có thể bổ sung cho nhau.** Ví dụ certificate chứng minh caller là `order-service`, còn token có `aud=inventory-api` và `scope=inventory:reserve`. Server cần kiểm tra cả certificate identity, token validity, audience và quyền truy cập tài nguyên khi hợp đồng yêu cầu.

## 2. Handshake mTLS hoạt động thế nào?

~~~mermaid
sequenceDiagram
    participant C as Order Service (client)
    participant S as Inventory Service (server)
    C->>S: ClientHello + SNI + TLS options
    S-->>C: ServerHello + server certificate chain
    C->>C: Validate CA chain, SAN/hostname, validity, EKU
    S-->>C: CertificateRequest (yêu cầu client cert)
    C->>S: Client certificate chain + proof of private key
    S->>S: Validate client CA chain, validity, EKU, identity policy
    C->>S: Finished / handshake confirmation
    S-->>C: Finished / handshake confirmation
    Note over C,S: Kênh TLS được thiết lập
    C->>S: HTTPS request (payload nghiệp vụ)
    S->>S: Application authentication + authorization
    S-->>C: HTTPS response
~~~

Sơ đồ cố ý giản lược chi tiết message order của TLS 1.2/1.3. Trong TLS 1.3, những thông điệp certificate/Finished có cách sắp xếp và mã hóa khác TLS 1.2; ý nghĩa chính vẫn là **mỗi phía xác minh danh tính của peer** theo chuỗi tin cậy phù hợp trước khi chấp nhận ứng dụng trao đổi.

### 2.1. Nếu client không gửi certificate?

Khi server yêu cầu client certificate với chính sách bắt buộc, TLS handshake sẽ thất bại **trước khi request vào Controller**. Bạn có thể thấy SSLHandshakeException, TLS alert hoặc connection reset ở phía client; thường **không có HTTP 401 từ controller** vì kết nối chưa đạt tới HTTP layer.

Đây là lý do cần phân biệt:

- **TLS handshake failure:** chứng chỉ, CA, SAN, protocol, key và trust.
- **HTTP 401:** ứng dụng chưa xác thực được request/token khi TLS đã thành công.
- **HTTP 403:** ứng dụng xác thực được nhưng không cho phép hành động.
- **HTTP 404/409/422:** lỗi HTTP/nghiệp vụ không mặc nhiên là lỗi mTLS.

## 3. PKI và các khái niệm bắt buộc

Một kiến trúc mTLS thường dùng **private CA/PKI nội bộ** hoặc nền tảng identity như workload certificates. Một certificate có public key và thông tin danh tính; **private key phải được giữ bí mật** tại workload sở hữu.

| Khái niệm | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Private key | Khóa bí mật chứng minh sở hữu certificate | Không commit vào Git, không log, kiểm soát quyền đọc |
| Leaf certificate | Chứng chỉ của client/server cụ thể | Có SAN, thời hạn và Key Usage/EKU |
| Intermediate CA | CA trung gian ký chứng chỉ workload | Bên gửi thường trình chain cần thiết |
| Root CA / trust anchor | Mốc tin cậy được cấu hình ở peer | Phải do tổ chức kiểm soát và rotate có kế hoạch |
| Certificate chain | Đường ký từ leaf đến trusted CA | Thiếu intermediate dễ gây PKIX path errors |
| Keystore | Container giữ private key + certificate chain (có thể thêm entry khác) | JKS/PKCS12 hoặc PEM files |
| Truststore | Container giữ các certificate/CA mà process tin cậy | Không chứa private key của bên đối tác |
| SAN | Subject Alternative Name: DNS/IP/URI identities | Đặc biệt quan trọng cho server hostname |
| EKU | Extended Key Usage | Server auth và client auth khác mục đích |
| CSR | Certificate Signing Request | Dùng xin CA phát hành cert, không phải private key |
| SNI | Server Name Indication ở TLS ClientHello | Để server/gateway chọn certificate phù hợp |

### 3.1. Keystore và truststore ở hai chiều

Mô hình Order Service gọi Inventory Service:

~~~mermaid
flowchart TB
    subgraph C["Order Service — client"]
      CK["Keystore: order-client key + cert chain"]
      CT["Truststore: CA ký inventory-server"]
    end
    subgraph S["Inventory Service — server"]
      SK["Keystore: inventory-server key + cert chain"]
      ST["Truststore: CA ký order-client"]
    end
    CT -. "xác minh server chain" .-> SK
    ST -. "xác minh client chain" .-> CK
~~~

**Không tráo vai trò:**

- Keystore của Order Service chứa **key/cert của chính Order Service**.
- Truststore của Order Service chứa **CA đáng tin để xác minh Inventory Service**.
- Keystore của Inventory Service chứa **key/cert của Inventory Service**.
- Truststore của Inventory Service chứa **CA đáng tin để xác minh Order Service**.

Một keystore có thể về mặt kỹ thuật chứa cả trusted cert entries, nhưng về thiết kế vẫn nên phân tách rõ **tài liệu riêng tư** và **trust anchors**.

### 3.2. SAN và tên endpoint

Nếu client gọi `https://inventory.internal:8443`, chứng chỉ server phải có DNS SAN phù hợp với `inventory.internal`. Nếu gọi bằng IP, certificate cần IP SAN tương ứng; chỉ có `CN=inventory.internal` thường không đáp ứng hostname verification hiện đại.

Ví dụ:

~~~text
Subject: CN=inventory.internal
SAN:
  DNS: inventory.internal
  DNS: inventory.svc.cluster.local
EKU: TLS Web Server Authentication (serverAuth)
~~~

Client certificate có thể mang danh tính workload qua URI SAN hoặc DNS SAN tùy PKI/mesh policy, ví dụ:

~~~text
URI SAN: spiffe://corp.example/ns/orders/sa/order-service
EKU: TLS Web Client Authentication (clientAuth)
~~~

**Quan trọng:** một URI SAN có dạng SPIFFE **không tự động trở thành authenticated application principal** trong Spring Boot. Phải có verifier/identity mapping và policy tin cậy phù hợp. Không coi bất kỳ text nào trong subject hoặc SAN là danh tính hợp lệ nếu CA có thể cấp nó không đúng quy tắc.

### 3.3. Certificate được tin cậy chưa đủ để cấp quyền

Tin được root CA chỉ chứng minh chứng chỉ được CA chấp nhận. Nếu CA cấp certificate cho cả `billing-service` và `order-service`, Inventory API cần xác minh **service identity** nào được phép gọi `POST /reservations`.

Một chính sách khả dụng:

~~~text
Authenticated peer identity: order-service
Allowed operation: inventory.reserve
Allowed environment: production
Allowed target: inventory-service
Decision: ALLOW

Authenticated peer identity: reporting-service
Allowed operation: inventory.reserve
Decision: DENY
~~~

Chính sách này có thể ở application, API gateway hoặc service mesh, nhưng phải được **thực thi và kiểm thử**, không chỉ ghi trên sơ đồ kiến trúc.

## 4. Cấu hình TLS/mTLS inbound trong Spring Boot

Spring Boot 3.1+ có **SSL bundles** để gom cấu hình key/trust material dùng cho nhiều kết nối. Các tên package Java và một số integration APIs thay đổi theo dòng Boot, vì vậy nên dùng BOM/guide đúng version đang chạy.

Ví dụ Inventory Service nhận HTTPS mTLS trên cổng 8443 với **PKCS#12**:

~~~yaml
# application.yml — Inventory Service
server:
  port: 8443
  ssl:
    enabled: true
    bundle: inventory-server
    client-auth: need

spring:
  ssl:
    bundle:
      jks:
        inventory-server:
          key:
            alias: inventory-server
          keystore:
            location: ${INVENTORY_KEYSTORE_LOCATION}
            password: ${INVENTORY_KEYSTORE_PASSWORD}
            type: PKCS12
          truststore:
            location: ${CLIENT_CA_TRUSTSTORE_LOCATION}
            password: ${CLIENT_CA_TRUSTSTORE_PASSWORD}
            type: PKCS12
~~~

Đây là cấu hình có chủ đích:

1. `server.ssl.enabled=true` bật TLS cho embedded server.
2. `server.ssl.bundle=inventory-server` chọn SSL bundle chứa **server identity** và CA tin cậy của clients.
3. `server.ssl.client-auth=need` yêu cầu client certificate bắt buộc.
4. `key.alias` xác định private key entry (khi keystore chứa nhiều entries).
5. `keystore` giữ private key và certificate chain của Inventory Service.
6. `truststore` chứa CA tin cậy được phép ký client certificates theo PKI policy.

Giá trị `*_LOCATION` nên là URI resource được Spring hỗ trợ như `file:/...` hoặc một dạng classpath dành cho test. Ở production, không để private key nằm trong artifact công khai và không hardcode passwords. Nếu private key có password riêng, Spring Boot SSL bundle có cấu hình `key.password` phù hợp để khai báo tách biệt.

**Lưu ý tương thích:** Cấu hình `spring.ssl.bundle.jks.*` và `server.ssl.bundle` dành cho những dòng Boot có SSL bundles. Nếu đang ở Boot cũ hơn, có thể cần `server.ssl.key-store`/`server.ssl.trust-store` và những thuộc tính tương ứng; **không** trộn đồng thời cấu hình keystore legacy với `server.ssl.bundle` trên cùng embedded server mà chưa xác minh tính tương thích.

### 4.1. need, want và none khác nhau

| Giá trị `server.ssl.client-auth` | Hành vi | Có phù hợp mTLS bắt buộc? |
| --- | --- | --- |
| `none` | Không yêu cầu client certificate | Không |
| `want` | Có thể yêu cầu certificate nhưng cho phép client không cung cấp | Không đủ nếu chính sách yêu cầu mọi client có cert |
| `need` | Client phải xuất trình certificate hợp lệ để handshake thành công | Có, nếu trust/identity policy đúng |

`want` phù hợp cho một số kịch bản chuyển đổi nhưng không nên coi là kiểm soát mTLS bắt buộc; các request không có certificate có thể vẫn tới application. Với `need`, client không có cert hợp lệ bị từ chối ở tầng TLS.

### 4.2. PEM thay vì PKCS12

Một số môi trường Kubernetes/secret management cấp **PEM certificate + private key** thay vì file PKCS12. Spring Boot SSL bundles hỗ trợ cấu hình PEM ở các dòng phù hợp:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-server:
          keystore:
            certificate: ${SERVER_CERT_LOCATION}
            private-key: ${SERVER_KEY_LOCATION}
          truststore:
            certificate: ${CLIENT_CA_CERT_LOCATION}
server:
  ssl:
    bundle: inventory-server
    client-auth: need
~~~

Ba giá trị này là **đường dẫn resource hoặc nội dung được hỗ trợ bởi phiên bản Boot**, không nên coi mọi path string đều có cùng ngữ nghĩa. Ví dụ sản xuất có thể mount secret vào `file:/etc/ssl/...` với permissions chặt. Chọn **một** cấu hình PEM hoặc JKS/PKCS12 cho bundle, không khai báo cả hai dưới cùng tên rồi kỳ vọng Boot tự đoán.

### 4.3. TLS versions và cipher suites

Trong production nên sử dụng TLS **1.2/1.3** theo chính sách tổ chức và runtime. Một cấu hình server có thể giới hạn:

~~~yaml
server:
  ssl:
    enabled: true
    enabled-protocols: TLSv1.3,TLSv1.2
    client-auth: need
~~~

Các ciphers, signature algorithms và protocol thực có thể khác nhau giữa JDK, server container và TLS provider. Không copy một danh sách cipher cũ từ tài liệu không phù hợp JDK mới. Kiểm thử cả positive/negative handshakes và tuân theo chính sách crypto của doanh nghiệp.

## 5. Cấu hình outbound mTLS cho RestClient

Trong mô hình Order Service → Inventory Service, Order Service phải:

- Tin được **Inventory Server certificate chain**.
- Trình **client certificate/private key của Order Service** khi server yêu cầu.
- Kiểm tra hostname `inventory.internal` khớp SAN.
- Giữ SNI, TLS versions và connection pooling đúng cấu hình client.

Tạo một SSL bundle riêng ở **client application**:

~~~yaml
# Order Service application.yml
spring:
  ssl:
    bundle:
      jks:
        inventory-client:
          key:
            alias: order-client
          keystore:
            location: ${ORDER_CLIENT_KEYSTORE_LOCATION}
            password: ${ORDER_CLIENT_KEYSTORE_PASSWORD}
            type: PKCS12
          truststore:
            location: ${INVENTORY_SERVER_CA_TRUSTSTORE_LOCATION}
            password: ${INVENTORY_SERVER_CA_TRUSTSTORE_PASSWORD}
            type: PKCS12

integrations:
  inventory:
    base-url: ${INVENTORY_BASE_URL:https://inventory.internal:8443}
~~~

Với **Spring Boot 3.2–3.x**, Boot cung cấp tiện ích `RestClientSsl` để áp dụng SSL bundle cho một `RestClient.Builder` do Boot quản lý.

~~~java
// Ví dụ API cho Spring Boot 3.2–3.x.
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpClientConfiguration {

    @Bean
    RestClient inventoryRestClient(
            RestClient.Builder bootBuilder,
            RestClientSsl restClientSsl,
            @Value("${integrations.inventory.base-url}")
            String baseUrl) {

        return bootBuilder
                .baseUrl(baseUrl)
                .apply(restClientSsl.fromBundle("inventory-client"))
                .build();
    }
}
~~~

**Cần đối chiếu imports và class location nếu dùng Boot 4.x**, vì một số package auto-configuration đã được tổ chức lại. Cơ chế cốt lõi không đổi: dùng **builder/SSL bundle được Boot quản lý**, rồi áp cấu hình client key/trust lên transport.

Trên `RestClient` tạo từ builder:

~~~java
import org.springframework.web.client.RestClient;
import org.springframework.stereotype.Component;

@Component
public class InventoryGateway {

    private final RestClient inventoryRestClient;

    public InventoryGateway(RestClient inventoryRestClient) {
        this.inventoryRestClient = inventoryRestClient;
    }

    public InventoryResponse reserve(
            InventoryRequest request) {

        return inventoryRestClient.post()
                .uri("/v1/reservations")
                .body(request)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

`InventoryRequest` và `InventoryResponse` là DTO contract của downstream, chưa được định nghĩa trong snippet vì bài tập trung mTLS. Trong ứng dụng thực, cần đặt timeout, response validation, lỗi HTTP 4xx/5xx, idempotency key và observation. Có thể dùng `@HttpExchange` + `HttpServiceProxyFactory` thay direct `RestClient`: **TLS nằm ở RestClient/HTTP transport bên dưới proxy**, không nằm ở annotation của interface.

### 5.1. Không được “sửa” lỗi TLS bằng trust-all

Những cách dưới đây làm mất bảo đảm mTLS và **không được dùng production**:

- TrustManager chấp nhận mọi X.509 certificate.
- HostnameVerifier luôn trả `true`.
- Tắt xác minh hostname để gọi server bằng IP sai SAN.
- Sử dụng một truststore chứa tất cả CA không kiểm soát và coi mọi leaf cert đều được cấp quyền.
- Lấy client certificate từ header HTTP tự do mà không có TLS chain đã xác minh.

Nếu hostname sai, cấp lại certificate đúng SAN hoặc đổi endpoint sang DNS trong certificate. Nếu CA không tin cậy, cài đúng CA chain/trust anchor và kiểm tra tính hợp lệ. Không bỏ bước xác minh.

### 5.2. SSL bundle không tự cấu hình các client khác

Chỉ tạo `spring.ssl.bundle.jks.inventory-client` **chưa đủ** để mọi `RestClient`/`WebClient` trong ứng dụng tự dùng nó. Phải **áp dụng bundle vào client hoặc message sender cụ thể** qua API được phiên bản Boot/transport hỗ trợ.

Điều này giúp tránh lỗi bảo mật khi nhiều downstream cần **client identity khác nhau**. Ví dụ Payment client nên dùng certificate riêng, không dùng credential Inventory client. Áp dụng một SSLContext global cho toàn JVM rất dễ làm sai scope và gây rò danh tính giữa các dịch vụ.

## 6. WebClient và mTLS qua Reactor Netty

`WebClient` thường được sử dụng trong các ứng dụng WebFlux hoặc luồng reactive. TLS nằm ở **HTTP connector** (ví dụ Reactor Netty), không nằm ở `Mono`/`Flux` hoặc `@GetExchange`.

Một phương án minh họa với Spring Boot `SslBundles` và Reactor Netty/Netty SSL context:

~~~java
// Ví dụ Reactor Netty; kiểm tra signatures theo version.
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import java.util.function.Consumer;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLException;
import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class InventoryWebClientConfiguration {

    @Bean
    WebClient inventoryWebClient(
            WebClient.Builder bootBuilder,
            SslBundles sslBundles) throws SSLException {

        SslBundle bundle = sslBundles.getBundle("inventory-client");

        SslContext context = SslContextBuilder.forClient()
                .keyManager(
                        bundle.getManagers().getKeyManagerFactory())
                .trustManager(
                        bundle.getManagers().getTrustManagerFactory())
                .build();

        HttpClient httpClient = HttpClient.create()
                .secure(spec -> spec
                        .sslContext(context)
                        .handlerConfigurator(handler -> {
                            SSLParameters parameters =
                                    handler.engine().getSSLParameters();
                            parameters.setEndpointIdentificationAlgorithm(
                                    "HTTPS");
                            handler.engine().setSSLParameters(parameters);
                        }));

        return bootBuilder
                .baseUrl("https://inventory.internal:8443")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

Đoạn code thể hiện nguyên tắc **client key material + trusted CA + hostname verification** và dùng `WebClient.Builder` được Boot inject. Tùy Spring Boot 3.x/4.x, Reactor Netty/Netty và SSL bundle API có thể khác; cần đối chiếu signature trước khi chạy.

**Chú ý hostname verification:** một số phiên bản/đường cấu hình Reactor Netty có mặc định hostname verification khi dùng secure client, nhưng khi thay SSL context hoặc handler tùy chỉnh cần kiểm chứng rằng `HTTPS endpoint identification` vẫn được bật. Không assume custom `SslContext` luôn kế thừa chính sách xác minh tên.

Việc dựng connector thủ công có thể làm thay đổi connection pool/shared resources/observation mà builder mặc định dùng; phải test hành vi thực. Nếu phiên bản Boot có tiện ích apply bundle trực tiếp cho `WebClient`, ưu tiên tiện ích đó để giảm nguy cơ tự cấu hình TLS sai.

### 6.1. Reactive không thay đổi ý nghĩa mTLS

~~~java
import reactor.core.publisher.Mono;

public Mono<InventoryResponse> reserve(
        WebClient inventoryWebClient,
        InventoryRequest request) {

    return inventoryWebClient.post()
            .uri("/v1/reservations")
            .bodyValue(request)
            .retrieve()
            .bodyToMono(InventoryResponse.class);
}
~~~

Handshake TLS thường xảy ra khi kết nối được thiết lập trong lúc subscribe. Kết nối HTTPS có thể được **reuse** trong pool nên không phải mỗi HTTP request đều handshake mới. Không dùng “số lần TLS handshake” làm “số request” và không giả định một client certificate mới sẽ xuất hiện trên kết nối đang mở nếu cấu hình được đổi giữa chừng.

## 7. Tạo chứng chỉ demo trong môi trường phát triển

Để hiểu cấu hình key/trust, có thể tạo hai **self-signed certificates chỉ cho local test** và thiết lập truststore tương ứng. Đây **không phải PKI production**, không được commit private keys/passwords và không dùng các tên/secret demo ở môi trường thật.

Các lệnh sau sử dụng `keytool` có sẵn trong JDK. Chạy trong một thư mục test riêng do bạn kiểm soát.

### 7.1. Server key/certificate

~~~bash
keytool -genkeypair \
  -alias inventory-server \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore inventory-server.p12 \
  -storepass changeit \
  -dname "CN=inventory.internal" \
  -ext "SAN=dns:inventory.internal,dns:localhost" \
  -ext "EKU=serverAuth"

keytool -exportcert \
  -alias inventory-server \
  -keystore inventory-server.p12 \
  -storepass changeit \
  -rfc -file inventory-server.crt
~~~

### 7.2. Client key/certificate

~~~bash
keytool -genkeypair \
  -alias order-client \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore order-client.p12 \
  -storepass changeit \
  -dname "CN=order-service" \
  -ext "EKU=clientAuth"

keytool -exportcert \
  -alias order-client \
  -keystore order-client.p12 \
  -storepass changeit \
  -rfc -file order-client.crt
~~~

### 7.3. Tạo truststore theo hai chiều

Inventory Service tin certificate client thử nghiệm:

~~~bash
keytool -importcert -noprompt \
  -alias order-client \
  -file order-client.crt \
  -storetype PKCS12 \
  -keystore inventory-truststore.p12 \
  -storepass changeit
~~~

Order Service tin certificate server thử nghiệm:

~~~bash
keytool -importcert -noprompt \
  -alias inventory-server \
  -file inventory-server.crt \
  -storetype PKCS12 \
  -keystore order-truststore.p12 \
  -storepass changeit
~~~

Kết quả local demo:

| Ứng dụng | Keystore | Truststore |
| --- | --- | --- |
| Inventory Service | `inventory-server.p12` | `inventory-truststore.p12` |
| Order Service | `order-client.p12` | `order-truststore.p12` |

Trong production, nên dùng **CA cấp workload certificates**, giới hạn vai trò CA và áp policy danh tính. Import trực tiếp một self-signed leaf cert vào truststore như ví dụ trên chỉ nhằm xác minh cơ chế trong lab; nó gây khó cho rotation và không tương đương trust model của hệ thống PKI có version và chain.

**An toàn:** `changeit` ở ví dụ là password test công khai, không phải secret phù hợp production. Các file private key phải được giữ ngoài repository, ngoài artifact phát hành và giới hạn file permissions.

### 7.4. Khi dùng PKI thật

Một quy trình certificate issuance đáng tin cậy thường gồm:

1. Workload/gateway sinh keypair hoặc dùng cơ chế key provisioning được quản trị.
2. Tạo CSR có SAN và EKU đúng danh tính.
3. CA xác minh service identity/quyền xin chứng chỉ trước khi ký.
4. Workload nhận certificate chain và trust bundle tương ứng.
5. Triển khai cert/key bằng secret delivery có kiểm soát.
6. Tự động/định kỳ rotate trước hạn và giám sát failures.
7. Thu hồi/chặn certificate bị lộ, hoặc rút ngắn validity để giảm thời gian rủi ro.

CA không nên ký mọi CSR tùy ý chỉ vì requester truy cập được API CA. Danh tính workload phải gắn với provisioning/authorization thực, ví dụ service account, namespace và policy phù hợp nền tảng.

## 8. Kiểm thử handshake thật với curl và OpenSSL

Bài test mTLS nên gồm **cả thành công và bị từ chối**. Đừng chỉ kiểm tra endpoint trả HTTP 200 bằng client được cấu hình trust-all.

Giả sử Inventory Service đang chạy ở `https://inventory.internal:8443` và DNS name có trong server SAN.

### 8.1. Client có chứng chỉ hợp lệ

Nếu đã có PEM client key/cert do test CA cấp:

~~~bash
curl --verbose \
  --cacert inventory-server.crt \
  --cert order-client.crt \
  --key order-client.key \
  https://inventory.internal:8443/actuator/health
~~~

Nếu dùng PKCS12 từ `keytool`, có thể dùng phương thức `--cert-type P12` và `--cert inventory-client.p12:...` tùy build/libcurl, hoặc chuyển đổi an toàn sang PEM cho test. Ví dụ trên giả định file `order-client.key` **thực sự tồn tại**; lệnh `keytool -exportcert` ở mục 7 chỉ xuất **public certificate**, không xuất private key. Không nhầm `.crt` với `.key`.

### 8.2. Client không có chứng chỉ

~~~bash
curl --verbose \
  --cacert inventory-server.crt \
  https://inventory.internal:8443/actuator/health
~~~

Khi server thực sự dùng `client-auth: need` và truy cập **trực tiếp TLS endpoint đó**, handshake phải bị từ chối hoặc request không thể hoàn thành bình thường vì thiếu client certificate.

### 8.3. Kiểm tra chain và SNI bằng OpenSSL

~~~bash
openssl s_client \
  -connect inventory.internal:8443 \
  -servername inventory.internal \
  -CAfile inventory-server.crt \
  -cert order-client.crt \
  -key order-client.key \
  -verify_return_error
~~~

`openssl s_client` cho biết chain, issuer, subject, verify result và TLS version. Không đồng nghĩa authorization ở application đã pass. Nếu chỉ kết nối thành công nhưng application trả HTTP 403, hãy chuyển sang kiểm tra **identity mapping/quyền** thay vì cố “sửa” CA.

### 8.4. Test sai tên host

Thử gọi server bằng một hostname **không có trong SAN** và giữ hostname verification bật. Client phải từ chối certificate, dù certificate được CA ký hợp lệ. Đây là kiểm thử quan trọng để phát hiện cấu hình trust-all hoặc HostnameVerifier bị vô hiệu hóa.

Nếu test truy cập qua `localhost` trong khi cert chỉ có `inventory.internal`, kết quả hostname mismatch là **đúng**. Giải pháp là cấu hình SAN test bao gồm `localhost` hoặc dùng DNS name đúng, không bỏ xác minh hostname.

## 9. Application authorization sau TLS

Thành công của handshake có thể đưa request tới Spring MVC/Servlet hoặc WebFlux, nhưng ứng dụng vẫn phải xác định **peer identity** và quyết định quyền.

Một mô hình chính sách:

~~~text
TLS:
  - Verify certificate chain issued by approved internal CA
  - Verify client certificate validity and EKU
  - Extract trusted peer identity from validated certificate

Application:
  - Map identity to service principal
  - Check access to endpoint / operation / tenant
  - Validate OAuth2 token when contract requires
  - Audit decision without logging private key or raw credentials
~~~

### 9.1. Spring Security X.509

Spring Security có hỗ trợ X.509 client certificate authentication trong servlet stack khi **TLS endpoint cung cấp certificate chain đã được xác minh** tới ứng dụng. Đây là bước *chuyển peer certificate thành application principal*, không thay thế cấu hình `server.ssl.client-auth=need`.

Ví dụ **định hướng**, không phải một cấu hình production đầy đủ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class InventorySecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/internal/reservations/**")
                    .hasAuthority("INVENTORY_RESERVE")
                .anyRequest().authenticated())
            .x509(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Ví dụ này giả định có Spring Security web starter và **cơ chế UserDetailsService/identity mapping** được cấu hình để gán đúng `INVENTORY_RESERVE` cho client certificate identity. Nếu chỉ bật `.x509()` mà không có trusted principal mapping, có thể gặp lỗi login hoặc ánh xạ quyền sai.

**Không mặc định lấy CN subject làm principal duy nhất** cho production đa tenant/nhiều CA: cùng CN có thể được cấp ở những ngữ cảnh khác nhau. Ưu tiên ánh xạ SAN/URI hoặc certificate identity theo PKI policy, trusted issuer, môi trường và các ràng buộc cần thiết. Nếu dùng SPIFFE/SVID, cần component thực sự xác minh SPIFFE identity, không chỉ parse string từ certificate.

### 9.2. Server.ssl.client-auth không thay Spring Security

Một endpoint có thể ở các trạng thái:

| TLS handshake | Principal/authorization | Kết quả |
| --- | --- | --- |
| Fail | Không có HTTP request hợp lệ | TLS alert/connection error |
| Pass | Không có mapping/authentication phù hợp | HTTP 401 hoặc auth failure |
| Pass | Xác thực nhưng thiếu quyền | HTTP 403 |
| Pass | Identity có quyền, payload đúng | 2xx theo contract |
| Pass | Identity có quyền, payload sai | 4xx nghiệp vụ |
| Pass | Identity có quyền, downstream outage | 5xx hoặc lỗi thích hợp |

Không chuyển TLS failure thành một HTTP 403 “bằng Java controller” vì handshake đã thất bại trước ứng dụng xử lý HTTP.

## 10. mTLS qua reverse proxy, ingress và service mesh

Trong Kubernetes/service mesh, TLS có thể kết thúc ở **load balancer, ingress proxy hoặc sidecar** thay vì trực tiếp trong JVM.

~~~mermaid
flowchart LR
    A["Order Service"] --> B["Order Sidecar"]
    B == "mTLS giữa proxies" ==> C["Inventory Sidecar"]
    C --> D["Inventory Application"]
    E["Mesh identity policy"] -.-> B
    E -.-> C
    C -.-> F["Peer identity / authorization policy"]
~~~

Trong kiến trúc này, ứng dụng JVM có thể nhận kết nối **HTTP plain-text từ localhost/sidecar** trong khi đường truyền giữa workloads được bảo vệ bởi mTLS ở proxy. `server.ssl.client-auth=need` có thể không được bật trong JVM, **nhưng việc đó chỉ hợp lý khi trust boundary đến sidecar được kiểm soát chặt**.

### 10.1. Hỏi đúng câu hỏi: TLS kết thúc ở đâu?

Một request đi qua nhiều hop:

~~~text
Client -> Ingress -> Gateway -> Service Mesh Sidecar -> JVM
~~~

Để biết mTLS thật sự có hiệu lực, phải trả lời:

1. Mỗi hop có TLS hay không?
2. Hop nào kiểm chứng **client certificate**?
3. Certificate chứa identity nào, do CA nào cấp?
4. Hop nào áp dụng authorization policy?
5. Hop từ proxy vào JVM có thể bị một workload khác truy cập trực tiếp không?
6. Có network policy/loopback/Unix domain socket bảo vệ hop không mã hóa không?
7. Ứng dụng có tin headers forwarded identity từ bất kỳ client nào không?

Một ingress chỉ kiểm tra certificate **ở rìa** không chứng minh mTLS giữa tất cả các service nội bộ. Cần xác định chính sách cho từng hop và mục tiêu threat model.

### 10.2. Header forwarded client identity có thể bị giả mạo

Một gateway có thể gửi header như `X-Client-Cert` hoặc `X-Forwarded-Client-Cert` sau khi xác minh peer. Ứng dụng **không được tin** header đó chỉ vì nó có mặt trong HTTP request.

Nếu cho phép user trực tiếp gửi `X-Forwarded-Client-Cert: CN=order-service`, họ có thể mạo danh. Chỉ tin forwarded identity khi:

- Ingress/gateway đáng tin đã **xác minh certificate chain** và identity.
- Gateway **xóa header do client gửi rồi tự đặt lại**.
- Hop từ gateway tới app được bảo vệ hoặc chỉ gateway có thể gọi.
- Application biết rõ **trusted proxy chain** và chính sách chuyển tiếp.
- Có test negative bypass gateway/header spoofing.

Nếu cần end-to-end mTLS trực tiếp giữa JVMs, đừng terminate TLS ở proxy rồi cho rằng ứng dụng tự thấy peer certificate. Khi terminate ở gateway, Servlet request có thể không có chứng chỉ thật của TLS peer ban đầu.

### 10.3. Mesh mTLS không tự thay quyền dữ liệu

Service mesh có thể cung cấp workload identity (ví dụ SPIFFE), service-to-service authentication và policy. Nhưng truy cập `GET /orders/{id}` còn phụ thuộc user/tenant ownership. Việc một service được phép gọi API **không cho phép đọc mọi tài nguyên**.

Ứng dụng vẫn cần authorization theo user, business scope, tenant hoặc resource, và nên xác minh token delegation nếu request thay mặt người dùng cuối.

## 11. Database, cache và message broker có TLS riêng

Bài tập trung **mTLS giữa các dịch vụ**, nhưng module tích hợp còn có các kết nối ngoài HTTP. Không suy từ cấu hình `server.ssl.bundle` rằng JDBC/Redis/Kafka đã an toàn.

| Tầng tích hợp | Cơ chế TLS/mTLS | Cần kiểm tra |
| --- | --- | --- |
| HTTP inbound Spring Boot | Embedded server TLS + client auth | Server bundle, client CA, `need` |
| RestClient outbound | HTTP transport SSL context/bundle | Client key, server trust, hostname SAN |
| WebClient outbound | Reactor Netty/HTTP connector SSL | mTLS context, hostname verification |
| Kafka producer/consumer | Kafka client `security.protocol=SSL` hoặc SASL_SSL và các SSL properties | Broker trust, optional client cert, hostname identification |
| RabbitMQ/AMQP | AMQP client SSL options/factory | Broker trust, client cert nếu broker yêu cầu |
| PostgreSQL JDBC | Driver SSL modes, key/cert/trust config | Server verification, client cert config, connection URL |
| Redis | Driver TLS config và optional client cert | TLS endpoint, CA, certificate credentials |
| Spring Integration adapters | Dựa vào transport factory/client của adapter | Không tự thừa hưởng mọi server.ssl setting |

Các giá trị cấu hình chính xác **phụ thuộc client library, vendor và phiên bản**. Phải thiết lập và kiểm thử **riêng trên mỗi connector**.

### 11.1. Kafka mTLS ví dụ ở mức ý tưởng

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      security.protocol: SSL
      ssl.truststore.location: ${KAFKA_TRUSTSTORE_PATH}
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
      ssl.keystore.location: ${KAFKA_KEYSTORE_PATH}
      ssl.keystore.password: ${KAFKA_KEYSTORE_PASSWORD}
      ssl.keystore.type: PKCS12
~~~

Ví dụ này chỉ thể hiện thuộc tính cơ bản của Kafka client. Đường dẫn Kafka SSL thường là filesystem paths theo Kafka client implementation, **không nhất thiết là Spring resource URI**. Kafka broker phải yêu cầu/vet client cert theo chính sách riêng; chỉ `security.protocol=SSL` ở client không chứng minh broker đã bật client authentication. Phải kiểm tra broker config và ACLs cho principal được ánh xạ.

### 11.2. PostgreSQL mTLS không phải HTTP mTLS

PostgreSQL JDBC có tham số như `sslmode=verify-full`, certificate trust/root và client cert/key theo driver/connection settings. Trong đó:

- `verify-full` kiểm tra server cert và hostname.
- `verify-ca` kiểm tra CA chain nhưng không tương đương hostname verification đầy đủ.
- Client cert chỉ có hiệu lực nếu PostgreSQL server yêu cầu và client cung cấp đúng format/identity.
- Quyền SQL vẫn do database authentication/roles/GRANT kiểm soát.

Đừng dùng `sslmode=require` và mặc định rằng server identity đã được kiểm chứng theo yêu cầu production; cần xem ý nghĩa chính xác của driver và sử dụng mode kiểm tra hostname khi cần.

### 11.3. Redis và RabbitMQ

Redis TLS/RabbitMQ TLS giúp mã hóa kênh và có thể yêu cầu client certificates nếu server/driver hỗ trợ. Nhưng Redis ACL hoặc RabbitMQ user/permissions vẫn có vai trò authorization; mTLS certificate identity có thể cần mapping riêng.

Tất cả adapter của Spring Integration nên dùng transport client đã được cấu hình đúng TLS. Ví dụ HTTP outbound gateway qua RestClient, AMQP outbound adapter qua RabbitTemplate hoặc Kafka outbound adapter qua Kafka client — không có một property `mTLS=true` chung cho toàn bộ Spring Integration.

## 12. Quản lý secret và rotation

Certificates là credentials có hạn sử dụng. Một triển khai mTLS production phải có **vòng đời certificate** chứ không chỉ file cấu hình.

### 12.1. Những điều nên làm

- Cấp certificate ngắn hạn và tự động rotate khi có thể.
- Tách CA/trust bundle giữa môi trường production, staging và dev theo chính sách.
- Không commit private key, PKCS12, password hoặc PEM chứa key vào Git.
- Mount secret vào filesystem/volume có quyền đọc tối thiểu hoặc dùng secret delivery được quản trị.
- Giới hạn người/process có quyền export private key; cân nhắc HSM/KMS nếu yêu cầu.
- Đảm bảo app container chỉ đọc trust/key material nó cần.
- Có dashboard cảnh báo certificate sắp hết hạn.
- Có procedure revoke/reissue nếu private key bị lộ.
- Audit ai cấp/đổi certificate và khi nào application nạp key mới.

### 12.2. Rotate không gây gián đoạn

Một cách luân chuyển CA an toàn:

~~~mermaid
flowchart LR
    A["Old CA đang tin"] --> B["Bổ sung new CA vào trust bundles"]
    B --> C["Phát hành cert mới bởi new CA"]
    C --> D["Rolling restart/reload workloads"]
    D --> E["Xác minh handshakes thành công"]
    E --> F["Loại old CA sau migration window"]
~~~

Điều kiện: tất cả clients/servers liên quan cần chấp nhận new chain **trước khi** cert mới xuất hiện; sau đó đợi đủ thời gian để những workload cũ hết sử dụng old chain.

**Không giả định một file key/trust được cập nhật trên disk là mọi TLS connection sẽ tự dùng ngay**. Một số Spring Boot SSL bundle/embedded server integrations hỗ trợ reload trong điều kiện cụ thể, nhưng HTTP client connection pools, custom SSLContext, Reactor Netty và các phiên bản Boot có thể cần explicit restart/rebuild để dùng cert mới.

Bài test rotation phải xác minh:

1. Kết nối mới dùng certificate mới.
2. Connection cũ không kéo dài vượt chính sách vận hành.
3. Trust chain mới được tất cả peers chấp nhận.
4. Authorization policy vẫn map đúng identity.
5. Quá trình rollback cert/CA có cửa sổ an toàn.

### 12.3. Certificate expiry và clock skew

Kiểm tra `NotBefore` và `NotAfter` dựa trên đồng hồ hệ thống. Clock lệch nhiều có thể tạo lỗi “not yet valid” dù cert mới cấp chính xác. Container/VM nodes cần đồng bộ thời gian. Monitor nên cảnh báo trước expiry theo ngày và mức độ quan trọng, không đợi lúc handshake bắt đầu thất bại.

## 13. Giám sát handshake và bảo mật kết nối

Micrometer/Actuator có thể giúp quan sát các tầng HTTP, nhưng **không phải mọi TLS handshake failure đều tạo HTTP server observation** vì lỗi có thể xảy ra trước khi HTTP request được tạo.

Cần kết hợp:

| Nguồn tín hiệu | Thông tin |
| --- | --- |
| Embedded server/TLS provider logs | Handshake alerts, certificate errors |
| Proxy/load balancer/mesh metrics | TLS handshake success/failure, peer identity, policy denies |
| HTTP client metrics | Request latency, connect/timeout errors |
| Spring Security audit | Authenticated principal, authorization decision |
| Certificate inventory | Certificate expiry, issuer, SAN và chain version |
| Business metrics | Order sync success, retry, DLQ, outbox lag |
| JVM/connection pool | Threads, connection use, resource saturation |

**Không log private keys, session secrets, toàn bộ bearer token, full client certificate trong request log hoặc raw handshake secrets**. Nếu cần audit, lưu certificate fingerprint/serial/issuer hoặc workload identity với kiểm soát quyền truy cập và retention phù hợp. Fingerprint/serial không nên dùng làm metric labels vì cardinality cao.

### 13.1. Phân biệt lỗi mTLS với lỗi nghiệp vụ

~~~text
Connection failed before HTTP:
    TLS handshake/certificate/protocol issue

HTTP 401/403 after TLS:
    authentication/authorization issue

HTTP 429/503 or timeout:
    rate limit/downstream availability issue

HTTP 2xx but business rejected:
    payload/contract/business status issue

HTTP 2xx and business applied:
    verify persistence/outbox/downstream ack as needed
~~~

Khi mTLS lỗi, tăng `retryCount` liên tục thường không giúp nếu certificate hết hạn hoặc CA chưa được tin. Đó là **lỗi cấu hình/vận hành** cần fail fast, cảnh báo và sửa certificate/trust. Chỉ thử lại có giới hạn khi lỗi kết nối tạm thời và deadline nghiệp vụ cho phép.

### 13.2. Metric labels có cardinality thấp

Các tag thích hợp: `downstream=inventory`, `transport=https`, `result=success/error`, `environment=prod`. Không thêm client IP động, certificate serial, user ID hoặc request ID vào metrics labels.

Một dashboard phù hợp có thể đặt các panel:

- Outbound TLS/connection error rate theo downstream.
- HTTP client p95 latency, timeout và 5xx.
- Proxy mTLS handshake failures/policy denies.
- Certificate expiry nearest threshold.
- Retry/DLQ count và business integration lag.
- Deployment/rotation timeline để liên hệ sự cố với thay đổi certificate.

Không suy ra “mTLS tốt” chỉ vì HTTP `/actuator/health` trả UP. Health check có thể dùng một caller đặc biệt không đại diện cho tất cả service identities.

## 14. Kiểm thử mTLS end-to-end và negative cases

Một unit test mock `RestClient` không thể chứng minh SSLContext thực sự xuất trình client certificate. Cần ít nhất một **integration test dùng TLS thật**, có server yêu cầu client auth.

### 14.1. Ma trận kiểm thử

| Trường hợp | Kỳ vọng |
| --- | --- |
| Client cert đúng CA, còn hạn, EKU hợp lệ | Handshake thành công |
| Không có client cert | Handshake bị từ chối nếu server `need` |
| Client cert sai CA | Handshake bị từ chối |
| Client cert quá hạn/chưa hiệu lực | Handshake bị từ chối |
| Server cert không có SAN đúng host | Client từ chối hostname verification |
| Server cert sai/untrusted CA | Client từ chối chain |
| Server thiếu intermediate chain | Client có thể từ chối PKIX path |
| Client có cert đúng nhưng không có application permission | Handshake pass, HTTP 403 |
| Expired/invalid JWT khi contract cần token | Handshake có thể pass, application auth fail |
| TLS protocol/cipher không tương thích | Handshake fail rõ, không tự downgrade insecure |
| Rotation new CA/new cert | Có cửa sổ tin cậy và rollout không gián đoạn |
| Hai service cùng CA nhưng identity khác | Chỉ identity được policy cho phép |
| Header X-Client-Cert do caller tự đặt | Không được coi là identity nếu không qua trusted proxy |

### 14.2. Ví dụ tích hợp Spring Boot

Với một `@SpringBootTest(webEnvironment=RANDOM_PORT)`, cấu hình test có thể bật:

~~~yaml
server:
  ssl:
    bundle: inventory-server
    client-auth: need

spring:
  ssl:
    bundle:
      jks:
        inventory-server:
          keystore:
            location: file:/tmp/test-certs/inventory-server.p12
            password: changeit
            type: PKCS12
          truststore:
            location: file:/tmp/test-certs/inventory-truststore.p12
            password: changeit
            type: PKCS12
~~~

Đây là **test fixture**, không dùng file `/tmp/test-certs` cố định trên CI thật nếu chưa provisioning. Có thể dùng temp directory/test resources bảo mật và dynamic properties, rồi tạo RestClient với bundle `inventory-client` từ test. Assertions phải chứng minh:

1. Kết nối với valid client certificate đến được controller.
2. Kết nối không có client certificate thất bại ở TLS.
3. CA không tin cậy hoặc hostname sai bị từ chối.
4. Một certificate hợp lệ nhưng principal không có quyền bị HTTP 403.
5. Không có test nào cài trust-all manager hoặc disable hostname verification.

Lưu ý `RANDOM_PORT` chỉ thay port, **không vô hiệu hóa TLS**. Nếu test gọi bằng `localhost`, certificate phải có `DNS:localhost` hoặc IP SAN tương ứng theo URL.

### 14.3. Test từ phía service mesh/proxy

Khi TLS kết thúc ở proxy, integration test của ứng dụng JVM **không đủ**. Cần:

- Kiểm tra policy của mesh yêu cầu mTLS giữa hai workloads.
- Test gọi từ workload không có identity hoặc identity không được phép.
- Test đường bypass sidecar/gateway và header injection.
- Test end-to-end application authorization với forwarded identity đáng tin.
- Thử thay đổi workload certificate và CA theo rollout plan.
- Quan sát certificate/handshake metrics ở proxy, không chỉ ở JVM.

Một test trả HTTP 200 đi qua gateway nhưng bỏ qua client auth ở ingress **không chứng minh** hệ thống mTLS đúng.

## 15. Phân tích lỗi và cách khắc phục

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `PKIX path building failed` | Server/client CA chưa được tin hoặc thiếu intermediate | Kiểm tra chain, truststore, CA rotation |
| `bad_certificate` | Peer từ chối certificate theo trust/usage/policy | Kiểm tra issuer, EKU, validity, key match |
| `certificate_required` / handshake failure | Server yêu cầu client cert nhưng client không gửi | Kiểm tra client keystore, alias, key password |
| `No subject alternative DNS name matching` | URL host không có trong server SAN | Cấp lại cert SAN đúng hoặc đổi DNS name |
| `No name matching ... found` | Hostname verification fail | Không disable verification |
| `keystore password was incorrect` | Sai password hoặc format | Kiểm tra env/PKCS12/JKS type |
| `Cannot recover key` | Key password sai hoặc key entry hỏng | Kiểm tra `key.password` và alias |
| `No available certificate or key corresponds to SSL cipher suites` | Keypair/algorithm/alias không phù hợp | Kiểm tra key/cert match, TLS version/ciphers |
| `handshake_failure` | Có thể do protocol/cipher/cert/trust | Xem TLS logs/openssl, không đoán |
| `HTTP 403` sau TLS success | Service principal thiếu quyền | Kiểm tra application/mesh policy |
| Môi trường test OK, prod fail | Khác hostname/CA/keystore/JDK/ingress | So sánh SAN, bundles, routing và secrets |
| Sau rotation một số pods fail | Các node còn CA/cert cũ hoặc pool chưa reload | Kiểm tra cert serial/version và restart policy |
| mTLS ở mesh nhưng JVM không thấy X509 cert | TLS terminate ở sidecar | Dùng trusted proxy identity hoặc passthrough |
| Giả mạo X-Client-Cert thành công | Trust header từ caller | Strip/rewrite tại trusted proxy, bảo vệ hop |
| Kafka/Redis/JDBC vẫn không có TLS | Chỉ cấu hình server.ssl | Cấu hình TLS từng connector |

### 15.1. Runbook chẩn đoán có thứ tự

1. Xác định chính xác **hop TLS lỗi**: client→ingress, sidecar→sidecar hay JVM→JVM.
2. Xác nhận endpoint DNS/port, SNI và TLS version; không log secrets.
3. Kiểm tra server certificate: chain, issuer, SAN, EKU, NotBefore/NotAfter.
4. Kiểm tra client certificate/key: đã gửi chưa, alias/key password, EKU.
5. Kiểm tra truststores mỗi phía chứa đúng CA, không bị stale.
6. Kiểm tra app property `client-auth=need` có thực sự áp trên **server nhận kết nối**.
7. Với handshake pass, chuyển sang kiểm tra Spring Security/mesh authorization.
8. Kiểm tra reverse proxy forwarded identity và nguy cơ bypass.
9. Thử với negative-case test, xác minh cấu hình đã sửa không biến thành trust-all.
10. Kiểm tra timeout, retry, outbox backlog và những request đã có side effect trong lúc sự cố.

**Không dùng SSL debug verbose trên production lâu dài** nếu logs có thể lộ thông tin certificate/session; bật tạm thời theo incident procedure và redaction policy. Java TLS debug `javax.net.debug=ssl,handshake` hữu ích trong môi trường kiểm soát, nhưng đầu ra phải được bảo vệ.

## 16. mTLS không thay xử lý lỗi, giao dịch và idempotency

Một kết nối mTLS có thể bảo vệ việc Order Service gọi Payment Service, nhưng **không** đảm bảo request POST chỉ được áp dụng một lần.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant P as Payment Service (mTLS)
    participant D as SQL Database
    O->>P: HTTPS/mTLS POST pay(orderId)
    P->>D: COMMIT payment
    Note over P,O: Response bị mất do timeout
    O->>O: Không biết payment đã commit chưa
    O->>P: Retry cùng operationId
    P->>D: Check idempotency key
    P-->>O: Trả kết quả đã ghi nhận
~~~

Để an toàn:

- Dùng operation ID/idempotency key ổn định theo business event, không dùng certificate serial hay TLS session ID.
- Phân biệt lỗi TLS cấu hình (không retry nhanh vô hạn) với HTTP 503 tạm thời và business rejection.
- Cần đối soát khi timeout **sau khi** remote side có thể đã thực thi.
- Nếu ghi SQL rồi gửi HTTP/broker, dùng transactional outbox hoặc saga/reconciliation theo yêu cầu.
- Tránh giữ transaction SQL mở lâu để chờ HTTP mTLS handshake/remote response.
- Thiết kế logs/audit để nối business operation với downstream outcome mà không lộ dữ liệu nhạy cảm.

mTLS bảo vệ **kênh và peer identity**, còn exactly-once processing, transaction consistency và audit trail phải được xử lý ở application/data architecture.

## 17. Checklist triển khai mTLS giữa các dịch vụ

- [ ] Xác định chính xác các hop phải mTLS và điểm kết thúc TLS (JVM/gateway/mesh).
- [ ] Có PKI/CA ownership rõ và quy tắc cấp identity của từng workload.
- [ ] Private key được giữ bí mật; cert chain, SAN và EKU đúng vai trò server/client.
- [ ] Server có keystore identity và truststore CA của clients; bật `client-auth=need` nếu mTLS bắt buộc.
- [ ] Client có key/cert identity và truststore CA của server; bật hostname verification.
- [ ] Chọn đúng Spring Boot SSL bundles/transport API theo phiên bản, không pha cấu hình legacy tùy tiện.
- [ ] Không dùng trust-all TrustManager, tắt hostname verifier hay chấp nhận mọi proxy identity header.
- [ ] Có application/mesh authorization policy, không chỉ kiểm tra cùng một CA.
- [ ] Nếu dùng OAuth2/JWT, có audience/scope/expiry và không coi mTLS thay user auth.
- [ ] Kafka/RabbitMQ/JDBC/Redis connectors được cấu hình TLS riêng khi cần.
- [ ] Có certificate issuance, rotation, expiry alert, revoke và rollback plan.
- [ ] Connection pools/reload behavior được kiểm chứng sau rotation.
- [ ] Có test TLS positive/negative, identity permissions, hostname/SAN, CA trust và proxy spoofing.
- [ ] Có metrics handshake/authorization/HTTP errors, logs có redaction, business retry/backlog.
- [ ] Retry/idempotency/transaction của nghiệp vụ được thiết kế độc lập với mTLS.

**Ghi nhớ:** mTLS tạo một kênh truyền được mã hóa và xác thực **hai đầu kết nối**, nhưng chỉ thực sự đáng tin khi certificate được cấp đúng danh tính, chain và hostname được xác minh, private key được bảo vệ, và quyền ứng dụng được áp dụng rõ ràng. Với Spring Boot, SSL bundles giúp quản lý key/trust material; inbound server dùng `server.ssl.client-auth=need`, outbound clients phải gắn bundle vào transport đúng cách. Hệ thống tích hợp production còn cần **rotation, kiểm thử negative cases, observability, retry và idempotency**.

## Tài liệu tham khảo

- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): SSL bundles, JKS/PKCS12/PEM và tích hợp TLS.
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/reference/web/servlet.html): cấu hình server SSL và client authentication.
- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestClient/WebClient builders và customizations.
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): tạo principal/authorization từ client certificate.
- [Java JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TrustManager, KeyManager, keystore, certificate verification và TLS.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): giao thức TLS 1.3 và certificate-based authentication.
- [RFC 5280 — PKI Certificate Profile](https://www.rfc-editor.org/rfc/rfc5280): X.509, certificate paths, extensions và constraints.
- [SPIFFE — Workload Identity](https://spiffe.io/docs/latest/spiffe-about/overview/): khái niệm workload identity/SVID trong service-to-service security.
- [Reactor Netty — HTTP Client SSL](https://projectreactor.io/docs/netty/release/reference/http-client.html#_ssl_and_tls): TLS/SSL cho reactive HTTP client.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS policy, cipher suites và an toàn cấu hình.
