# SSL bundle, keystore, truststore và cấu hình `spring.ssl.bundle.*`

## 1. Bài toán: nhiều kết nối TLS, nhiều loại chứng thư

Một dịch vụ Spring Boot có thể đồng thời:

- Nhận HTTPS từ API gateway hoặc ứng dụng khác.
- Gọi API đối tác bằng `RestClient` với CA riêng.
- Kết nối broker, database hoặc cache qua TLS.
- Dùng **mutual TLS (mTLS)** để chứng minh danh tính của workload với một hệ thống nội bộ.

Nếu mỗi HTTP client, driver và embedded server đều tự đọc một cặp đường dẫn certificate/private key khác nhau, cấu hình sẽ trở nên khó kiểm tra, khó thay đổi theo môi trường và dễ mắc lỗi khi xoay vòng chứng thư.

Spring Boot cung cấp **SSL bundle** để đặt tên cho một tập vật liệu mật mã và tùy chọn TLS, sau đó cho các thành phần được hỗ trợ **tham chiếu cùng một bundle theo tên**. Hai cách khai báo phổ biến là **PEM** và **JKS/PKCS12**, được đặt dưới `spring.ssl.bundle.*`.

Trong module **SPRING_BOOT_INTEGRATION**, việc này gắn với các ranh giới tích hợp thực tế: một HTTP adapter gọi sai truststore có thể không kết nối được; một consumer không xác thực được broker có thể dừng nhận sự kiện; một cơ chế tự động retry có thể khiến sự cố cấu hình TLS phát sinh thêm tải. Bài học tập trung vào **cách tổ chức và áp dụng SSL bundle** bên cạnh việc hiểu keystore, truststore, mTLS, cấu hình, kiểm thử và vận hành.

### Sau bài này, bạn có thể

1. Giải thích sự khác nhau giữa **keystore**, **truststore**, private key, CA certificate và SSL bundle.
2. Tạo bundle PEM và JKS/PKCS12 qua `spring.ssl.bundle.*`.
3. Dùng bundle làm danh tính HTTPS server, làm trust material hoặc client identity cho `RestClient`.
4. Hiểu khi nào bundle **không tự áp dụng** cho một JDBC, cache, broker hoặc thư viện HTTP khác.
5. Chẩn đoán lỗi thiếu CA, sai hostname, sai private key, file secret không đọc được và cấu hình trùng.
6. Thiết kế quy trình rotation, kiểm thử bằng TLS socket thật, bảo vệ khóa và theo dõi expiry.

> **Phạm vi phiên bản:** Ví dụ sử dụng Java 17+, Spring Boot **3.2–3.5** và Spring Framework tương thích. SSL bundles có từ Spring Boot 3.1; `RestClientSsl` dùng trong ví dụ có trong Spring Boot 3.2+. Một số package, property và API thay đổi ở Spring Boot 4; hãy đối chiếu tài liệu chính thức của phiên bản được triển khai. Đường dẫn và chứng thư trong ví dụ là giả định.

## 2. Từ certificate đến SSL bundle

Trước khi viết YAML, cần phân biệt những thành phần sau.

| Thành phần | Chứa gì? | Vai trò |
| --- | --- | --- |
| **Private key** | Khóa bí mật của một danh tính | Chứng minh sở hữu khóa; phải được bảo vệ nghiêm ngặt |
| **Leaf certificate** | Public key, SAN, thời hạn, issuer, chữ ký CA và thuộc tính sử dụng | Định danh server hoặc client |
| **Intermediate CA** | Certificate của CA trung gian | Giúp xây dựng đường tin cậy tới CA được chấp nhận |
| **Trust anchor** | Root/intermediate CA hoặc certificate được bên kiểm tra chủ động tin cậy | Điểm kết thúc đáng tin của đường kiểm tra PKIX |
| **Keystore** | Danh tính cục bộ: private key và certificate chain liên quan | Được trình khi một bên cần chứng minh danh tính mình |
| **Truststore** | Certificate/CA đáng tin cho phía đối diện | Xác minh certificate chain của bên được kết nối |
| **SSL bundle** | Key/trust material cùng tùy chọn TLS, được Spring Boot đặt tên | Cấu hình tập trung để thành phần có hỗ trợ tái sử dụng |

Một file PKCS12 (`.p12`, `.pfx`) có thể chứa private key, chain và cả certificate được tin cậy. Tuy nhiên **định dạng file không đồng nghĩa với vai trò**: keystore cho danh tính và truststore cho niềm tin là hai trách nhiệm khác nhau. Bundle giúp Spring Boot biết thành phần nào được dùng cho mỗi trách nhiệm đó.

```mermaid
flowchart TD
    A["spring.ssl.bundle.*"] --> B["SSL bundle có tên<br/>partner-client"]
    B --> C["Key material<br/>client certificate + private key"]
    B --> D["Trust material<br/>Partner CA"]
    B --> E["SSL options<br/>protocol/cipher nếu cấu hình"]
    C --> F["TLS client authentication (mTLS)"]
    D --> G["Xác minh server certificate chain"]
    E --> H["SSLContext / client được hỗ trợ"]
    F --> H
    G --> H
    H --> I["RestClient → Partner HTTPS"]
```

Một client HTTPS thông thường chỉ cần **trust material phù hợp** để xác minh server. Chỉ khi đối tác yêu cầu mTLS, client mới cần thêm certificate và private key của chính nó. Ngược lại, một Spring Boot HTTPS server cần **keystore** để trình danh tính của server; nếu server yêu cầu mTLS, cần thêm truststore để kiểm tra client.

## 3. Vì sao nên dùng bundle thay vì khai báo SSL ở từng nơi?

Không có bundle, một ứng dụng có thể có hàng loạt cấu hình khó truy vết:

```text
HTTPS server           → key-store=/etc/tls/server.p12
Partner HTTP client    → tự tạo SSLContext với /etc/tls/partner-ca.pem
Another HTTP client    → đọc trực tiếp cert khác từ filesystem
Cache client           → mỗi môi trường dùng một truststore riêng
```

Bundle cho phép đặt tên theo **vai trò kết nối**:

```text
public-api-server     → danh tính HTTPS server của ứng dụng
partner-orders-client → tin CA đối tác + certificate client nếu mTLS
internal-db-client    → CA và danh tính phục vụ DB nếu driver hỗ trợ
```

Lợi ích chính:

- **Tập trung và nhất quán:** không lặp lại đường dẫn/mật khẩu trong nhiều lớp cấu hình.
- **Định danh rõ:** tên bundle thể hiện đối tượng và trách nhiệm của kết nối.
- **Tách môi trường:** thay giá trị file, secret hoặc certificate theo local/staging/production mà ít thay Java code.
- **Áp dụng có kiểm soát:** server và client được hỗ trợ có thể tham chiếu bundle; không buộc thay mọi truststore JVM.
- **Dễ kiểm tra:** biết service đang tin CA nào, trình certificate nào, và thay đổi ảnh hưởng những endpoint nào.

Bundle **không phải** một CA, không tự ký chứng thư, không tự đảm bảo hostname verification của mọi third-party client và không tự bật TLS cho tất cả dependency.

## 4. Cấu trúc `spring.ssl.bundle.*`

Hai nhánh khai báo chủ yếu:

```yaml
spring:
  ssl:
    bundle:
      pem:
        my-pem-bundle:
          # keystore / truststore / options / reload-on-update...
      jks:
        my-jks-bundle:
          # key / keystore / truststore / options...
```

Các tên `my-pem-bundle` và `my-jks-bundle` là tên do ứng dụng định nghĩa. Khi một thành phần dùng bundle, nó tham chiếu **tên**, chẳng hạn `server.ssl.bundle: public-api-server`.

### 4.1. Bảng thuộc tính quan trọng

| Nhánh cấu hình | Thuộc tính tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| `spring.ssl.bundle.pem.<name>.keystore` | `certificate`, `private-key` | Certificate chain và private key bằng PEM |
| `spring.ssl.bundle.pem.<name>.truststore` | `certificate` | Certificate CA/trust material ở định dạng PEM |
| `spring.ssl.bundle.jks.<name>.keystore` | `location`, `password`, `type` | File keystore JKS/PKCS12 |
| `spring.ssl.bundle.jks.<name>.truststore` | `location`, `password`, `type` | File truststore JKS/PKCS12 |
| `spring.ssl.bundle.jks.<name>.key` | `alias`, `password` | Chọn key entry và mật khẩu key khi cần |
| `spring.ssl.bundle.<pem/jks>.<name>.options` | `enabled-protocols`, `ciphers` | Hạn chế protocol/cipher suites khi thành phần sử dụng hỗ trợ |

Một số bản Spring Boot còn hỗ trợ `reload-on-update` để theo dõi thay đổi file vật liệu SSL. Tính năng này **phụ thuộc consumer và loại server**; không mặc định mọi HTTP client, JDBC driver hoặc pool đang chạy sẽ tự thay SSL context khi file đổi. Phần 13 giải thích cách dùng thận trọng.

### 4.2. Phân biệt PEM với JKS/PKCS12

| Tiêu chí | PEM | JKS/PKCS12 |
| --- | --- | --- |
| Định dạng | Nội dung văn bản có `-----BEGIN CERTIFICATE-----` hoặc `-----BEGIN PRIVATE KEY-----` | Kho khóa/chứng thư dạng container; PKCS12 là lựa chọn phổ biến |
| Triển khai | Mount certificate, private key và CA thành file riêng | Mount file `.p12`/`.jks` và password |
| Kết hợp với secret manager | Dễ cấp phát từng file | Dễ cấp phát một container có password |
| Độ phức tạp | Cần ghép đúng certificate chain với private key | Cần đúng store type, store password, key alias/password |
| Khi xoay vòng | Thay cert/key/CA đúng cặp, kiểm tra reload | Thay cả file store hoặc entry theo quy trình |

PEM và PKCS12 **không mặc định có mức an toàn cao/thấp hơn nhau**. Điều quyết định là cách bảo vệ private key, phân quyền file, secret distribution, lifetime của certificate và cấu hình xác minh peer.

## 5. Cấu hình PEM: truststore chỉ chứa CA của đối tác

Giả sử `order-service` gọi `https://orders.partner.example` và đối tác sử dụng một CA nội bộ. Chúng ta cần **tin CA của server**, chưa cần client certificate.

```yaml
# src/main/resources/application.yml
spring:
  ssl:
    bundle:
      pem:
        partner-orders:
          truststore:
            certificate: file:/etc/order-service/tls/partner-ca-chain.pem

integration:
  partner:
    base-url: https://orders.partner.example
```

Ý nghĩa:

1. Bundle có tên `partner-orders`.
2. `truststore.certificate` trỏ tới CA/trust material đã được tổ chức xác minh.
3. Không có `keystore` vì đối tác hiện không yêu cầu mTLS.
4. File được mount từ hạ tầng triển khai thay vì đưa CA cứng vào source. Việc tin một CA nội bộ phải có quy trình xác nhận nguồn và quyền sở hữu.

Đường dẫn `file:` cần tồn tại **trong máy/container chạy ứng dụng**. Đường dẫn trên laptop người phát triển không tự xuất hiện trong pod Kubernetes. Nếu cấu hình `classpath:`, file được đóng gói trong JAR và muốn đổi phải cân nhắc chu kỳ build/deploy; với dữ liệu nhạy cảm, nên dùng secret deployment phù hợp.

### 5.1. Certificate CA khác certificate của server

Khi server trình chuỗi:

```text
Leaf: orders.partner.example
    ↓ signed by
Intermediate: Partner Issuing CA
    ↓ signed by
Root: Partner Root CA
```

Client nên tin các **trust anchors được quản lý**, thường là root hoặc CA được chỉ định, và server phải trình các intermediate cần thiết. Import certificate của một endpoint chưa xác thực vào truststore để “hết lỗi PKIX” là cách xử lý rủi ro. Trước khi thêm CA, cần xác minh fingerprint và nguồn phát hành qua kênh độc lập.

**Không giả định truststore tùy chỉnh tự động hợp nhất với truststore JVM mặc định.** Một bundle tin CA riêng có thể không tin CA công khai cho một endpoint khác. Tạo bundle theo ranh giới upstream thay vì ép mọi HTTPS client dùng chung một tập CA rộng.

### 5.2. TLS vẫn phải xác minh hostname

Bundle cung cấp trust material cho việc xác minh certificate chain. HTTP client còn phải so sánh **hostname thực sự gọi** với SAN trong certificate của server. Với URL `https://orders.partner.example`, certificate chứa SAN `DNS:billing.partner.example` **không hợp lệ** cho tên đích này dù cùng CA ký.

Không tắt hostname verification hay dùng trust-all `X509TrustManager`. Nếu gặp mismatch, sửa URL/certificate SAN hoặc điểm kết thúc TLS ở proxy/load balancer.

## 6. PEM cho mutual TLS: thêm danh tính client

Đối tác có thể yêu cầu mTLS: ngoài kiểm tra server, đối tác sẽ yêu cầu ứng dụng Spring Boot trình certificate của **client workload**.

```yaml
spring:
  ssl:
    bundle:
      pem:
        partner-orders:
          truststore:
            certificate: file:/etc/order-service/tls/partner-ca-chain.pem
          keystore:
            certificate: file:/etc/order-service/tls/order-service-client-chain.pem
            private-key: file:/etc/order-service/tls/order-service-client.key
```

Thay đổi chính so với mục 5 là nhánh `keystore`:

- `certificate`: certificate của client và chain cần gửi theo chính sách đối tác.
- `private-key`: private key tương ứng **của client**, chỉ có bên sở hữu workload được đọc.
- `truststore.certificate`: tiếp tục phục vụ kiểm tra **server**.

Client certificate phải còn hạn, có mục đích sử dụng khóa hợp lệ (ví dụ client authentication theo EKU khi yêu cầu), và được **server tin CA cấp**. Phía Spring Boot vẫn xác minh hostname server; mTLS không biến việc bỏ qua server authentication thành an toàn.

```mermaid
sequenceDiagram
    participant APP as Spring Boot RestClient
    participant PARTNER as Partner HTTPS server
    APP->>PARTNER: TLS ClientHello (SNI)
    PARTNER-->>APP: Server certificate chain
    Note over APP: Truststore kiểm tra CA và hostname trong SAN
    PARTNER-->>APP: CertificateRequest (mTLS)
    APP->>PARTNER: Client certificate chain + proof dùng private key
    Note over PARTNER: Truststore server kiểm tra client identity
    APP->>PARTNER: HTTP request sau handshake
    PARTNER-->>APP: HTTP response
```

Nếu server chỉ xác thực certificate client mà không phân quyền theo role/tenant/scope, danh tính hợp lệ có thể vẫn truy cập dữ liệu không được phép. **mTLS xác thực workload; authorization nghiệp vụ là trách nhiệm khác.**

## 7. Cấu hình JKS/PKCS12 bundle

Một số tổ chức phân phối private key và certificate chain dưới dạng PKCS12. Giả sử có:

```text
/etc/order-service/tls/order-service-client.p12
/etc/order-service/tls/partner-truststore.p12
```

Cấu hình:

```yaml
spring:
  ssl:
    bundle:
      jks:
        partner-orders:
          key:
            alias: order-service
            password: ${CLIENT_KEY_PASSWORD}
          keystore:
            location: file:/etc/order-service/tls/order-service-client.p12
            password: ${CLIENT_KEYSTORE_PASSWORD}
            type: PKCS12
          truststore:
            location: file:/etc/order-service/tls/partner-truststore.p12
            password: ${PARTNER_TRUSTSTORE_PASSWORD}
            type: PKCS12
```

Ở đây `jks` là tên **nhóm cấu hình** Spring Boot dành cho Java KeyStore style bundles. Thuộc tính `type: PKCS12` chỉ rõ định dạng container thực tế; không bắt buộc phải dùng định dạng JKS cũ.

Hai mức password không phải lúc nào cũng giống nhau:

- **Store password** dùng để mở/kiểm tra container.
- **Key password** dùng khi truy cập private key entry, nếu entry đặt password riêng.
- **Alias** chọn key entry trong keystore khi có nhiều certificate/key.

Khi keystore chỉ có một key entry, alias có thể không cần chỉ định. Khi key password trùng store password, có thể đơn giản hóa cấu hình nếu API/định dạng cho phép. Không đoán alias hoặc password: kiểm tra container bằng công cụ quản trị phù hợp.

### 7.1. Tạo truststore PKCS12 từ một CA được xác minh

Một lệnh minh họa:

```bash
keytool -importcert \
  -alias partner-root-ca \
  -file partner-root-ca.pem \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
```

Kiểm tra nội dung:

```bash
keytool -list -v \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
```

Nếu chỉ cần **truststore**, không phải tạo private key cho nó. Lệnh import trên chỉ thêm certificate đáng tin; không biến certificate công khai của CA thành danh tính client. Khi tạo **keystore cho mTLS**, private key phải xuất phát từ quy trình cấp phát danh tính được phê duyệt, không lưu vào repository.

**Lưu ý:** lệnh `keytool` có thể hỏi password và yêu cầu xác nhận trust. Xác minh fingerprint CA từ nguồn độc lập trước khi nhập. Không đặt password vào tham số command line hay CI log khi có thể dùng prompt hoặc secret mechanism an toàn.

### 7.2. PEM hay PKCS12?

Cả hai ví dụ dùng cùng tên bundle `partner-orders` vì thể hiện **hai phương án thay thế**, không phải hai cấu hình đồng thời trong một ứng dụng. Chọn một phương án rồi giữ cách quản lý secret nhất quán. Không định nghĩa cùng tên bundle ở cả `pem` và `jks` nếu không có nhu cầu đặc biệt và không hiểu cách framework xử lý trùng tên.

## 8. Sử dụng SSL bundle cho HTTPS server Spring Boot

Trong ví dụ này, chính ứng dụng Spring Boot là **server** trình certificate cho client. SSL bundle gồm private key và server certificate:

```yaml
spring:
  ssl:
    bundle:
      pem:
        public-api-server:
          keystore:
            certificate: file:/etc/order-service/tls/api-server-chain.pem
            private-key: file:/etc/order-service/tls/api-server.key

server:
  port: 8443
  ssl:
    bundle: public-api-server
```

Với embedded web server hỗ trợ, `server.ssl.bundle` tham chiếu bundle đã đặt tên và cho phép sử dụng material tương ứng khi tạo HTTPS listener. Certificate server phải có SAN khớp tên mà **các client sử dụng để kết nối** tới endpoint TLS đó. Nếu có ingress/proxy kết thúc TLS phía trước, cần xác định TLS thực sự terminate ở đâu; việc bật TLS của backend không tự cấu hình TLS phía ingress.

### 8.1. Server yêu cầu client certificate

Muốn server xác thực client bằng mTLS, bổ sung truststore chứa CA cấp certificate cho các client và chế độ client authentication:

```yaml
spring:
  ssl:
    bundle:
      pem:
        internal-api-server:
          keystore:
            certificate: file:/etc/order-service/tls/server-chain.pem
            private-key: file:/etc/order-service/tls/server.key
          truststore:
            certificate: file:/etc/order-service/tls/internal-client-ca.pem

server:
  port: 8443
  ssl:
    bundle: internal-api-server
    client-auth: need
```

`client-auth: need` yêu cầu client certificate theo khả năng embedded server. `want` có thể cho phép kết nối không trình certificate, nên không phù hợp nếu chính sách bắt buộc mọi client đều phải xác thực bằng mTLS. Mức **authorization** theo certificate principal và quy tắc API vẫn phải được thiết kế trong Spring Security hoặc lớp được ủy quyền.

### 8.2. Những cấu hình không nên trộn

Khi sử dụng `server.ssl.bundle`, hãy để **bundle sở hữu key/trust material**. Không đồng thời đưa nhiều cấu hình cũ như `server.ssl.key-store`, `server.ssl.key-store-password`, `server.ssl.certificate` vào cùng một server SSL config mà kỳ vọng framework tự chọn đúng. Ở các phiên bản Spring Boot, một số tổ hợp bị từ chối hoặc có thứ tự ưu tiên không như mong đợi; quy tắc rõ nhất là **dùng một cách cấu hình SSL cho một endpoint**.

## 9. Sử dụng bundle cho HTTP client đồng bộ `RestClient`

Ở chiều gọi HTTP, ứng dụng cần vừa có `baseUrl` đúng vừa sử dụng bundle `partner-orders`. Spring Boot 3.2+ cung cấp `RestClientSsl` để áp dụng một SSL bundle vào builder.

### 9.1. Cấu hình URL bằng `@ConfigurationProperties`

```yaml
integration:
  partner:
    base-url: https://orders.partner.example
```

```java
// PartnerProperties.java
package example.integration.partner;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integration.partner")
public record PartnerProperties(String baseUrl) {
}
```

Ở production, cần xác minh `baseUrl` không rỗng, có `https://`, host nằm trong danh sách được phép và không đến từ input người dùng tùy ý. Chỉ dùng truststore hợp lệ nhưng cho phép URL do request bên ngoài điều khiển có thể tạo rủi ro SSRF.

### 9.2. Tạo bean `RestClient` từ builder do Spring Boot cấu hình

```java
// PartnerRestClientConfiguration.java
package example.integration.partner;

import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerProperties.class)
public class PartnerRestClientConfiguration {

    @Bean("partnerRestClient")
    RestClient partnerRestClient(
            RestClient.Builder builder,
            RestClientSsl ssl,
            PartnerProperties properties) {

        return builder
                .baseUrl(properties.baseUrl())
                .apply(ssl.fromBundle("partner-orders"))
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
```

Những điểm cần chú ý:

1. `RestClient.Builder` được **Spring Boot inject**, giữ các `RestClientCustomizer` và integration phù hợp thay vì luôn tự gọi `RestClient.builder()`.
2. `RestClientSsl` lấy SSL bundle theo tên `partner-orders`, áp dụng certificate/trust material cho client.
3. Nếu bundle có keystore chứa client certificate/key, nó có thể được dùng khi đối tác yêu cầu mTLS.
4. `RestClient` xây dựng xong được sử dụng lại, tránh tạo client và SSL context mới cho từng HTTP request.

**Cẩn trọng về request factory:** `builder.apply(ssl.fromBundle(...))` có thể thay `ClientHttpRequestFactory` trước đó trên builder. Nếu ứng dụng còn yêu cầu connect/read timeout, proxy, connection pooling hoặc HTTP client đặc thù, cần xây cấu hình **kết hợp** với SSL qua API tương thích phiên bản và kiểm thử cả SSL lẫn timeout. Không giả định việc gọi `requestFactory(...)` trước/sau `ssl.fromBundle(...)` luôn giữ mọi thiết lập.

### 9.3. Adapter HTTP chỉ nên biết hợp đồng nghiệp vụ

```java
// PartnerOrdersClient.java
package example.integration.partner;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PartnerOrdersClient {

    private final RestClient restClient;

    public PartnerOrdersClient(
            @Qualifier("partnerRestClient") RestClient restClient) {
        this.restClient = restClient;
    }

    public PartnerOrderDto getOrder(String id) {
        PartnerOrderDto response = restClient.get()
                .uri("/v1/orders/{id}", id)
                .retrieve()
                .body(PartnerOrderDto.class);
        if (response == null) {
            throw new IllegalStateException(
                    "Partner API returned an empty response");
        }
        return response;
    }
}

record PartnerOrderDto(String id, String status) {
}
```

Adapter không tự load private key, không tự vô hiệu hóa hostname verification và không để business service biết cách tạo TLS context. Cấu hình danh tính/trust được quản lý tại ranh giới client. Khi lỗi kết nối, adapter cần phân loại lỗi TLS/cấu hình khác với lỗi HTTP 4xx/5xx và lỗi dữ liệu nghiệp vụ.

### 9.4. Nhiều đối tác nên có nhiều bundle

```yaml
spring:
  ssl:
    bundle:
      pem:
        partner-orders:
          truststore:
            certificate: file:/etc/tls/orders-ca.pem
        partner-shipping:
          truststore:
            certificate: file:/etc/tls/shipping-ca.pem
```

Hai upstream có thể có CA, certificate client, thời hạn và người phụ trách riêng. Tạo `RestClient` riêng theo upstream rồi gắn đúng bundle vào từng client. Không tái sử dụng một builder **có trạng thái thay đổi** để lần lượt đổi SSL bundle của các upstream nếu không kiểm soát cách clone/tiêm builder riêng.

## 10. Truy xuất `SslBundles` từ ứng dụng

Không phải mọi thành phần đều có thuộc tính `ssl.bundle` sẵn. Spring Boot cung cấp API để **lấy bundle theo tên**, từ đó ứng dụng có thể tích hợp với một thư viện nhận `SSLContext` hoặc key/trust manager.

```java
package example.integration.security;

import javax.net.ssl.SSLContext;
import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.stereotype.Component;

@Component
public class PartnerSslContextProvider {

    private final SslBundles sslBundles;

    public PartnerSslContextProvider(SslBundles sslBundles) {
        this.sslBundles = sslBundles;
    }

    public SSLContext createContext() {
        SslBundle bundle = sslBundles.getBundle("partner-orders");
        return bundle.createSslContext();
    }
}
```

Chỉ dùng đoạn này khi thư viện tích hợp **thật sự cần** `SSLContext`. Các client do Spring Boot hỗ trợ trực tiếp thường có cách gắn bundle thuận tiện hơn. Đừng tạo `SSLContext` mới cho mỗi message/request; cân nhắc quản lý lifecycle và khả năng rotation của client dùng context đó.

**Điểm quan trọng:** một `SSLContext` đúng CA chưa đủ để cam kết hostname verification. Một số thư viện yêu cầu cấu hình endpoint identification riêng ở socket/HTTP client. Khi dùng custom client, phải xác minh **cả chain và hostname**, không suy ra hostname verifier được bật từ việc `createSslContext()` thành công.

Tùy phiên bản, `SslBundle` còn cho phép truy cập `getStores()`, `getManagers()`, `getOptions()` để tích hợp sâu hơn. Đây là API cấp thấp: ưu tiên cơ chế bundle được Boot support sẵn để tránh phải tự quản lý `KeyManagerFactory`, `TrustManagerFactory` và rotation.

## 11. Bundle và các hệ thống tích hợp ngoài HTTP

Trong ứng dụng thực tế, keystore/truststore còn cần cho database, cache và broker. Cần phân biệt:

| Tích hợp | Cách xem xét bundle | Điều cần xác minh |
| --- | --- | --- |
| Embedded HTTPS server | `server.ssl.bundle` | TLS port, cert SAN, client-auth, server hỗ trợ |
| Spring Boot `RestClient` | `RestClientSsl` và builder được inject | Request factory, timeout, trust/hostname, client cert |
| `WebClient` | Cơ chế SSL dành cho reactive client theo Spring Boot/Netty version | SSL provider, connection pool, TLS context |
| Redis | Thuộc tính SSL/SSL bundle nếu starter và client được Boot hỗ trợ | Client driver, TLS endpoint, hostname/CA |
| JDBC / R2DBC | Driver-specific SSL properties hoặc cơ chế bundle được Boot hỗ trợ | PKIX, hostname, mTLS, URL mode và driver version |
| Kafka / RabbitMQ / Pulsar | Các thuộc tính driver/broker hoặc liên kết bundle nếu được hỗ trợ | Broker advertised hostname, TLS auth, trust/keystore riêng |
| Spring Integration | Cấu hình đúng connection factory/client nằm dưới adapter | Channel không tự biến kết nối thành TLS |

**Không có bảo đảm phổ quát** rằng khai báo `spring.ssl.bundle.pem.partner-orders` sẽ tự được sử dụng bởi mọi dependency. Mỗi client phải được chỉ rõ bundle, SSL context hoặc trust/key material bằng API mà **đúng phiên bản** thư viện hỗ trợ.

### 11.1. Ví dụ: PostgreSQL JDBC có cơ chế riêng

Một cấu hình PostgreSQL JDBC driver thường dùng:

```yaml
spring:
  datasource:
    url: "jdbc:postgresql://db.internal.example:5432/orders?sslmode=verify-full&sslrootcert=/etc/tls/db-root-ca.pem"
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Đây là cấu hình **driver PostgreSQL**, không phải bằng chứng rằng driver đọc `spring.ssl.bundle.*`. `verify-full` yêu cầu xác minh certificate chain và hostname theo semantics driver. Một driver khác có thể dùng truststore, connection property và tên SSL mode khác. Đừng dùng `sslmode=require` như cách thay thế tương đương `verify-full`.

### 11.2. Ví dụ: broker quảng bá nhiều hostname

Kafka/Pulsar có thể dùng bootstrap endpoint rồi nhận metadata chứa broker hostname khác. Bundle có CA đúng cho bootstrap **không bảo đảm** một broker khác có SAN đúng với tên mà client được chỉ dẫn kết nối.

Khi chỉ một số consumer/producers gặp TLS error:

- Ghi nhận **tên broker thực tế** trong log/metadata.
- Kiểm tra certificate SAN của từng endpoint/proxy.
- Xác định driver có bật hostname verification và dùng truststore nào.
- Sửa certificate/DNS/`advertised.listeners` theo kiến trúc cluster, không tắt xác minh.

### 11.3. Server SSL bundle và client SSL bundle độc lập

Một service vừa là HTTPS server vừa gọi API ra ngoài thường cần **hai bundle**. Danh tính TLS inbound không nên vô tình được gửi cho đối tác outbound. Truststore của đối tác cũng không nên trở thành danh sách CA được phép xác thực mọi client kết nối tới server nội bộ. Đặt tên bundle theo vai trò và kiểm soát quyền đọc private key.

## 12. Cấu hình TLS protocol, cipher và chính sách bảo mật

Trong một số môi trường, bộ phận bảo mật yêu cầu giới hạn phiên bản TLS được phép sử dụng. Các bundle hỗ trợ nhóm `options`:

```yaml
spring:
  ssl:
    bundle:
      pem:
        partner-orders:
          truststore:
            certificate: file:/etc/tls/partner-ca.pem
          options:
            enabled-protocols:
              - TLSv1.3
              - TLSv1.2
```

Ví dụ này chỉ minh họa **phạm vi cấu hình tùy chọn TLS**, không phải chính sách bắt buộc cho mọi hệ thống. Phiên bản JDK, SSL provider, server và client implementation quyết định protocol/cipher nào thực sự được hỗ trợ. Nếu partner chỉ hỗ trợ phiên bản quá cũ, phải đánh giá rủi ro và kế hoạch nâng cấp, không tùy tiện bật giao thức yếu.

Không cấu hình một danh sách cipher suite lấy từ máy khác mà không kiểm tra tên hỗ trợ của JVM/provider. Sau khi triển khai, kiểm tra handshake thực tế để xác nhận protocol/cipher đã được thương lượng như mong đợi.

### Hạn chế về 0-RTT, ALPN và HTTP/2

Một SSL bundle không tự quyết định toàn bộ hành vi HTTP/2, ALPN, connection reuse hay early data. Những khả năng này còn phụ thuộc HTTP server/client, TLS version và proxy. Nếu một API có hành vi thay đổi trạng thái, không suy ra TLS 1.3 làm việc phát lại request trở nên an toàn: **idempotency và chống replay nghiệp vụ** vẫn phải được thiết kế riêng.

## 13. Xoay vòng certificate, reload và vòng đời kết nối

Certificate hết hạn và key bị thu hồi có thể khiến toàn bộ kết nối tích hợp ngừng hoạt động. Vì vậy bundle phải đi cùng quy trình rotation.

### 13.1. Phân biệt thay file với thay SSL context

Giả sử file `/etc/tls/partner-ca.pem` được thay bằng CA mới trong khi ứng dụng đang chạy. Có ít nhất ba lớp trạng thái:

1. **File trên filesystem** đã thay đổi.
2. **SslBundle/SSLContext** mà ứng dụng sử dụng có thể vẫn đang giữ bản đã nạp trước đó.
3. **Socket/connection pool** có thể tiếp tục dùng kết nối TLS cũ, không có handshake mới tới khi kết nối được tạo lại.

Do đó **việc cập nhật file không bảo đảm mọi client nhận certificate mới ngay lập tức**. Spring Boot có khả năng reload bundle trong một số phiên bản/trường hợp được hỗ trợ, nhưng consumer phải biết sử dụng thay đổi đó. Đối với server hoặc HTTP client không hỗ trợ reload, cần triển khai lại/restart hoặc tái tạo client/connection pool theo quy trình.

### 13.2. `reload-on-update` khi phiên bản hỗ trợ

Ví dụ PEM bundle:

```yaml
spring:
  ssl:
    bundle:
      pem:
        public-api-server:
          reload-on-update: true
          keystore:
            certificate: file:/etc/order-service/tls/server-chain.pem
            private-key: file:/etc/order-service/tls/server.key

server:
  ssl:
    bundle: public-api-server
```

Đây là cấu hình minh họa **tính năng reload khi vật liệu file thay đổi** trong các phiên bản Boot có hỗ trợ. Phải kiểm tra:

- Loại embedded server/client có hỗ trợ cập nhật SSL material sau khi khởi tạo không.
- Cách file mount được thay (ghi đè file, atomic rename, symlink trong Kubernetes Secret, v.v.) có phát ra thay đổi mà cơ chế theo dõi phát hiện được không.
- Thời gian phát hiện thay đổi, hành vi session/kết nối hiện có, rollback và lỗi nếu certificate/key không khớp.
- Thuộc tính reload có sẵn **trong phiên bản đang dùng** hay không; đừng giả định mọi bản Boot 3.x có cùng tính năng.

Đối với mTLS, nên triển khai certificate chain và private key **thành một bộ nhất quán**, tránh khoảng thời gian tạm thời chứa cert mới nhưng key cũ.

### 13.3. Quy trình rotation thực tế

```mermaid
flowchart TD
    A["Kiểm kê cert/CA, SAN, EKU,<br/>expiry và bundle owners"] --> B["Cấp cert/key mới và xác minh nguồn"]
    B --> C["Chuẩn bị trust overlap nếu đổi CA"]
    C --> D["Phân phối cert/key tới staging"]
    D --> E["Test handshake server/client + mTLS"]
    E --> F["Rollout production theo nhóm"]
    F --> G["Giám sát handshake/timeout/error"]
    G --> H["Loại bỏ CA/cert cũ khi an toàn"]
```

Với đổi CA, nhiều hệ thống cần một khoảng thời gian cả CA cũ và mới cùng được trust để tránh gián đoạn. Cần giới hạn khoảng chuyển tiếp và thu hồi CA cũ theo chính sách sau khi mọi phía đã chuyển đổi. Với client certificate, đối tác phải tin được chain của certificate mới trước khi client bắt đầu trình nó.

**Không đưa private key vào log, email hoặc issue tracker** trong quá trình rotation. Việc debug nên tập trung vào fingerprint công khai, issuer, SAN, serial, hạn dùng, alias và chuỗi chứng thư đã che thông tin nhạy cảm.

## 14. Kiểm thử SSL bundle đúng cách

Một unit test mock `RestClient` có thể chứng minh adapter xử lý JSON và HTTP status, nhưng **không** chứng minh certificate chain hoặc hostname verification hoạt động. Bài kiểm thử TLS phải có **socket TLS thật** giữa client và server test.

### 14.1. Ma trận test cần có

| Tình huống | Kỳ vọng |
| --- | --- |
| CA được tin, server SAN đúng hostname, cert còn hạn | Handshake thành công |
| Server dùng CA khác truststore | Handshake thất bại với lỗi xác minh đường tin cậy |
| Server có CA đúng nhưng SAN sai | Handshake bị từ chối bởi hostname verification |
| Server certificate hết hạn/chưa hiệu lực | Kết nối bị từ chối |
| mTLS server yêu cầu client cert, client không trình | Handshake hoặc thiết lập kết nối thất bại |
| Client cert đúng nhưng private key sai | Không thể dùng danh tính mTLS đúng; lỗi cấu hình hoặc handshake |
| Client cert được server chấp nhận nhưng không đủ quyền API | TLS thành công; tầng ứng dụng trả 401/403 hoặc cơ chế phân quyền tương ứng |
| Bundle key/trust file không có trong container | Phát hiện lỗi cấu hình sớm, không tự fallback trust-all |
| Bundle được thay khi đang chạy | Xác minh rõ có/không reload theo server/client đang sử dụng |
| HTTP client áp dụng bundle sau khi cấu hình timeout | Xác minh cả TLS lẫn timeout được giữ đúng |

### 14.2. Tạo CA thử nghiệm tách biệt

Trong CI, có thể dùng một CA test và cấp leaf certificate cho `localhost`, hoặc sử dụng test server hỗ trợ TLS như WireMock/MockWebServer/embedded server. Đảm bảo certificate có SAN:

```text
DNS:localhost
IP Address:127.0.0.1
```

Sử dụng đúng tên/địa chỉ theo URL test. Không tắt hostname verification để “cho pass” test. Không sao chép key và certificate production vào test environment.

Mô hình:

```text
CA test (được CI quản lý)
  ├─ cấp certificate cho HTTPS stub server
  ├─ lưu public CA vào bundle test-client
  └─ nếu mTLS: cấp thêm client cert/key thử nghiệm

Spring Boot RestClient + test-client bundle
  → https://localhost:<random-port>
  → assert response hoặc assert TLS failure theo từng case
```

Khi kiểm thử nhiều instance, cần xem kết quả handshake từ **cùng network namespace, DNS và proxy path** với ứng dụng thật, vì certificate được trình ở load balancer/ingress có thể khác certificate của backend.

### 14.3. Phân biệt test HTTP và test TLS

- `MockRestServiceServer` phù hợp kiểm tra URL, method, header, body, error mapping; nó không thiết lập TLS socket tới server.
- HTTPS integration test xác nhận SSL bundle, trust chain, hostname và client certificate.
- Staging test xác nhận secret mount, DNS, proxy, CA/truststore và các cấu hình thực tế của môi trường triển khai.
- Failure/rotation test xác nhận ứng dụng xử lý certificate hết hạn, file missing, thay key và retry đúng.

## 15. Công cụ kiểm tra keystore, truststore và server certificate

Các lệnh sau chỉ để **chẩn đoán**, không thay thế xác minh kết nối thực từ ứng dụng.

### 15.1. Xem chứng thư PEM

```bash
openssl x509 \
  -in partner-server-leaf.pem \
  -noout -subject -issuer -dates -fingerprint -sha256 \
  -ext subjectAltName
```

Kiểm tra SAN, issuer, hạn dùng và SHA-256 fingerprint. Nếu file chứa nhiều certificate, `openssl x509` thông thường đọc certificate đầu tiên; cần kiểm tra cả chain bằng công cụ/script phù hợp khi xử lý nhiều entry.

### 15.2. Xem chain do server thực sự trình

```bash
openssl s_client \
  -connect orders.partner.example:443 \
  -servername orders.partner.example \
  -verify_hostname orders.partner.example \
  -CAfile partner-ca-chain.pem \
  -verify_return_error \
  -showcerts
```

Kết quả xác minh OpenSSL phụ thuộc CA file và tùy chọn mà bạn truyền. Nó không tự chứng minh JVM/HTTP client đang sử dụng **cùng truststore và hostname verifier**. Chạy từ cùng tuyến network/proxy với ứng dụng để tránh quan sát nhầm endpoint.

### 15.3. Xem PKCS12 store và alias

```bash
keytool -list -v \
  -keystore order-service-client.p12 \
  -storetype PKCS12
```

Đối chiếu alias, loại entry, certificate chain, validity và fingerprint. Không đặt password trong tham số dòng lệnh lưu ở CI log hoặc shell history; dùng prompt hay cơ chế secret an toàn.

### 15.4. Debug JSSE của Java

Khi lỗi chỉ xuất hiện ở Java:

```text
-Djavax.net.debug=ssl,handshake
-Djava.security.debug=certpath
```

Chỉ bật trong môi trường điều tra hoặc trong một khoảng thời gian giới hạn, vì log có thể rất lớn và chứa metadata nhạy cảm. Cần ghi thời gian lỗi, hostname đã gọi, bundle được tham chiếu và exception gốc.

## 16. Bảng lỗi điển hình và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
| --- | --- | --- |
| `Could not find SSL bundle` hoặc không tìm thấy bundle name | Tên tham chiếu khác tên khai báo hoặc profile không tải cấu hình | Kiểm tra `spring.ssl.bundle.*`, `server.ssl.bundle`/tên trong code, active profile |
| `FileNotFoundException`, `NoSuchFileException` với cert/key | File không tồn tại trong container hoặc path/mount sai | Kiểm tra `file:` location, quyền đọc và volume mount |
| `Keystore was tampered with, or password was incorrect` | Store password sai, định dạng store không đúng hoặc file hỏng | Kiểm tra type JKS/PKCS12 và password bằng công cụ quản trị |
| `Cannot recover key` / private key unavailable | Sai key password, alias hoặc key entry | Kiểm tra key alias, entry type, key password |
| `PKIX path building failed` | Thiếu trust anchor/intermediate hoặc truststore thực tế khác | Xem chain và truststore đang được client sử dụng |
| `No subject alternative DNS name matching` | URL hostname không khớp SAN | Sửa URL, DNS hoặc cấp certificate đúng SAN |
| `CertificateExpiredException` | Certificate quá hạn hoặc đồng hồ sai | Kiểm tra expiry, `notBefore`, clock và chain |
| `Received fatal alert: bad_certificate` | Bên kia từ chối certificate, thường gặp ở mTLS | Kiểm tra client cert/key, EKU, CA trust phía server, policy |
| `handshake_failure` | TLS version/cipher, cert chain, mTLS hoặc policy không tương thích | Xem log hai phía và protocol/cipher đã thương lượng |
| Chỉ một số instance lỗi sau rotation | Secret mount, truststore hoặc SSL context chưa được cập nhật đồng đều | Kiểm kê instance, file version và kế hoạch reload/restart |
| TLS ổn nhưng request bị 403 | Certificate xác thực thành công nhưng không được cấp quyền | Kiểm tra principal/role/tenant và authorization của API |
| Timeout sau khi áp dụng SSL bundle | Request factory hoặc pool/timeout bị thay trong cấu hình client | Kiểm tra thứ tự áp dụng SSL và factory settings, test timeout thật |

### Quy trình phân tích lỗi có hệ thống

1. Xác định **endpoint cuối** mà client thực sự gọi: hostname, port, protocol, proxy và đường lookup broker nếu có.
2. Xác định client đang sử dụng **bundle nào**, bundle ấy có key/trust material gì, file đã được mount chưa.
3. So sánh certificate trình trong handshake với SAN, issuer, validity và trust anchor của client.
4. Nếu mTLS, xác minh certificate/key của client được server chấp nhận, không chỉ client tin server.
5. Nếu lỗi sau rotation, xem reload/restart/connection pool và sự đồng nhất các instance.
6. Sau khi sửa, chạy integration test thật; không khắc phục bằng cách tắt verification.

## 17. Quản lý cấu hình theo môi trường và ranh giới tin cậy

Một cấu trúc dễ vận hành là dùng tên bundle ổn định, **thay nội dung/đường dẫn theo môi trường**:

```yaml
# application.yml
spring:
  ssl:
    bundle:
      pem:
        partner-orders:
          truststore:
            certificate: ${PARTNER_CA_LOCATION}
```

```text
# Ví dụ giá trị tại runtime, không commit credential:
PARTNER_CA_LOCATION=file:/etc/order-service/tls/partner-ca.pem
```

Với Spring Boot property binding, các placeholder trỏ tới biến môi trường hoặc nguồn cấu hình khác. Tên bundle `partner-orders` có thể giữ nguyên giữa local, staging và production, trong khi secret file được phân phối bởi hệ thống triển khai tương ứng.

### 17.1. Tên bundle cũng là một quyết định thiết kế

Đặt tên theo mục đích:

```text
public-api-server
partner-orders-client
partner-shipping-client
internal-mtls-client
```

Tránh một bundle như `all-trusted-cas` gom mọi CA nội bộ và ngoại vi không phân biệt phạm vi. Khi có nhiều ứng dụng/đối tác sử dụng cùng một CA, vẫn cần xác định ai có quyền thay trust material và thay đổi đó ảnh hưởng những kết nối nào.

### 17.2. Phân tách secret và quyền truy cập

- Private key chỉ cấp cho workload cần trình danh tính tương ứng.
- Truststore chứa certificate công khai, nhưng **quyết định tin CA** vẫn là quyết định bảo mật cần kiểm soát.
- Không để private key và password trong source control, image build dùng chung hay application logs.
- Hạn chế file permissions; chỉ process chạy ứng dụng được đọc key của nó.
- Dùng identity riêng cho môi trường và workload, tránh tái sử dụng key giữa staging/production.
- Định nghĩa chủ sở hữu và lịch rotation cho từng certificate/CA.

### 17.3. Quản lý nhiều ranh giới TLS

Một luồng có thể là:

```text
Client bên ngoài → API gateway → Spring Boot → Partner API
                            └──→ Kafka/DB/Redis
```

Mỗi mũi tên có thể là một **TLS hop khác nhau**, với client identity, server identity, truststore và chính sách mạng riêng. Bundle của embedded server không tự bảo vệ gateway → backend khi gateway terminate TLS theo cách khác; bundle `RestClient` cũng không cấu hình Kafka/DB. Kiểm kê tất cả hop có dữ liệu nhạy cảm.

## 18. Tình huống thực tế: cùng một CA nhưng hai loại lỗi khác nhau

**Bối cảnh:** `order-service` gọi `https://orders.partner.example` qua mTLS. Sau rotation:

- Instance A báo `PKIX path building failed`.
- Instance B báo `No subject alternative DNS name matching`.
- Instance C kết nối TLS thành công nhưng API trả 403.

**Phân tích:**

1. Instance A có thể chưa nhận CA/intermediate mới hoặc đang dùng SSL context cũ. Kiểm tra bundle được load thực tế và chain server.
2. Instance B tin chain nhưng certificate server được cấp cho **hostname khác**; phải sửa endpoint/SAN. Import thêm CA không sửa được lỗi hostname.
3. Instance C đã hoàn thành TLS nhưng certificate client có thể không được cấp role/scope cần thiết, hoặc token tầng ứng dụng thiếu quyền. Đây là lỗi authorization, không nên chữa bằng cách tắt mTLS.

**Kế hoạch xử lý:** đồng bộ lại vật liệu certificate và cấu hình của từng instance, xác minh SAN/chain bằng TLS test thật, kiểm tra principal/role của client, rồi rollout và theo dõi handshake errors cùng HTTP 4xx/5xx. Khi có retry ở HTTP adapter, cần tránh retry tự động vô hạn đối với PKIX/hostname/permission errors vì chúng là lỗi cấu hình hoặc phân quyền.

## 19. Checklist trước khi đưa SSL bundle vào production

1. **Tài sản:** biết ai sở hữu certificate, CA, private key, bundle name và expiry.
2. **Định dạng:** chọn PEM hoặc JKS/PKCS12 đúng với quy trình secret distribution; không khai báo hai bundle cùng tên không rõ mục đích.
3. **Vai trò:** keystore cho danh tính của chính ứng dụng; truststore cho CA/certificate bên đối diện.
4. **Định danh:** leaf certificate có SAN phù hợp hostname/IP mà peer dùng; không tắt hostname verification.
5. **mTLS:** kiểm tra cả hai phía tin CA phù hợp; private key khớp cert; server áp quyền nghiệp vụ độc lập.
6. **API Spring Boot:** endpoint có hỗ trợ dùng bundle hay phải cấu hình driver/client riêng; kiểm tra đúng version.
7. **Timeout và pooling:** việc áp dụng bundle không làm mất settings của HTTP request factory hoặc connection pool.
8. **Secret:** file mount, password/alias, quyền đọc, biến môi trường và chính sách không đưa key vào log.
9. **Kiểm thử:** chạy TLS socket thật với CA đúng/sai, SAN đúng/sai, cert hết hạn và mTLS khi dùng.
10. **Rotation:** triển khai trust overlap, reload/restart rõ ràng, kiểm tra cert mới trên mọi instance.
11. **Quan sát:** theo dõi handshake failures, TLS errors, expiry, connection timeout và ảnh hưởng đến consumer/outbox.

### Câu hỏi tự kiểm tra

**1.** Vì sao một bundle chỉ khai báo `truststore.certificate` vẫn đủ cho nhiều cuộc gọi HTTPS thông thường? Khi nào cần thêm `keystore.private-key`?

**2.** Điều gì khác nhau giữa việc Spring Boot dùng `server.ssl.bundle` và `RestClient` dùng `ssl.fromBundle(...)`?

**3.** Một file `.p12` có cả CA certificate và private key. Vì sao vẫn cần phân biệt vai trò keystore/truststore?

**4.** Client kết nối tới `https://payments.example` nhưng server trình chứng thư CA hợp lệ với SAN `DNS:reports.example`. Sửa truststore có đủ không?

**5.** Vì sao gọi `bundle.createSslContext()` không tự chứng minh một thư viện tùy biến đã bật hostname verification?

**6.** Vì sao thay file certificate trên Kubernetes Secret chưa chắc làm mọi connection hiện tại dùng certificate mới? Bạn sẽ kiểm chứng hỗ trợ reload thế nào?

**7.** Một service nhận HTTPS và gọi hai đối tác khác nhau qua mTLS. Bạn sẽ tổ chức bao nhiêu bundle và vì sao?

## Tài liệu tham khảo

- [Spring Boot 3.5 — SSL bundles](https://docs.spring.io/spring-boot/3.5/reference/features/ssl.html): cấu hình PEM/JKS, named bundle và vòng đời SSL.
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): cách dùng SSL bundle với REST client.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): tra tên và defaults của `spring.ssl.bundle.*` theo phiên bản.
- [Java 17 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): SSLContext, KeyManager, TrustManager, certificate path và TLS debug.

## Kết luận

Spring Boot SSL bundle cho phép quản lý **key material, trust material và tùy chọn TLS theo tên**, thay vì lặp lại cách tải certificate/private key trong từng kết nối. PEM phù hợp khi hạ tầng phân phối file certificate/key riêng; JKS/PKCS12 phù hợp khi quản lý keystore container và alias/password. Với HTTPS server, tham chiếu bundle qua `server.ssl.bundle`; với `RestClient`, dùng `RestClient.Builder` được Spring Boot cấu hình kết hợp `RestClientSsl`. Đối với database, cache và broker, cần kiểm tra cơ chế SSL của **đúng driver/client**. Một triển khai tốt phải xác minh chain và hostname, bảo vệ private key, kiểm thử bằng socket TLS thật, có kế hoạch xoay vòng và theo dõi lỗi kết nối. Nhờ đó các luồng tích hợp HTTP, cơ sở dữ liệu, cache và thông điệp duy trì được tính tin cậy khi cấu hình và certificate thay đổi.
