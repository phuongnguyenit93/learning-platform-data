# Xác thực và TLS cho kết nối Pulsar

Khi Spring Cloud Stream dùng Apache Pulsar Binder, ứng dụng kết nối đến Pulsar qua Pulsar client do Spring for Apache Pulsar quản lý. Kết nối production cần bảo vệ cả hai khía cạnh: **xác thực danh tính** của client và **mã hóa đường truyền bằng TLS**. Sau khi xác thực, Pulsar còn dùng authorization để quyết định role đó được publish, consume hoặc quản trị tài nguyên nào.

Trong Spring Cloud Stream, function `Supplier`, `Function` hoặc `Consumer` làm việc với các binding; Pulsar Binder ánh xạ binding đến topic. Cấu hình kết nối Pulsar thường nằm dưới `spring.pulsar.client.*`, còn thao tác quản trị topic của binder dùng Pulsar Administration với cấu hình admin riêng. Cần cấu hình đúng cả client lẫn admin khi ứng dụng tự provision topic. Không đặt token, mật khẩu hoặc private key trực tiếp trong source code hay file cấu hình được commit.

## 1. Ba lớp bảo vệ của kết nối Pulsar

Ba khái niệm thường bị nhầm lẫn:

| Lớp | Câu hỏi cần trả lời | Cơ chế |
|---|---|---|
| TLS transport | Dữ liệu trên đường truyền có được mã hóa và xác minh máy chủ không? | TLS, CA certificate, hostname verification |
| Authentication | Client là ai? | Token/JWT, OAuth2, mTLS, Athenz, Basic hoặc plugin được hỗ trợ |
| Authorization | Role đã xác thực được phép làm gì? | Pulsar authorization, tenant/namespace/topic permissions |

TLS bảo vệ tính bí mật và toàn vẹn của dữ liệu khi truyền, đồng thời xác minh máy chủ theo certificate. Authentication gắn kết nối với một principal/role. Authorization kiểm tra quyền của role đó trên topic, namespace hoặc thao tác quản trị.

```text
Spring Cloud Stream application
          |
          v
Pulsar Binder
          |
          +---- PulsarClient ----------------------+
          |      pulsar+ssl://broker:6651          |
          |      TLS + authentication              |
          |                                         v
          |                                    Pulsar Broker
          |                                         |
          |                                  Authentication
          |                                         |
          |                                  Authorization / ACL
          |                                         |
          |                                  Topic / Subscription
          |
          +---- PulsarAdministration ---------------+
                 https://broker:8443                |
                 TLS + admin authentication         v
                                               Pulsar Admin API
```

Không nên coi việc kết nối thành công là bằng chứng authorization đã được thiết lập đúng. Một client có thể xác thực thành công nhưng vẫn bị từ chối khi publish hoặc consume vì thiếu quyền.

## 2. Pulsar Binder dùng cấu hình Spring Boot của Pulsar

Pulsar Binder được xây dựng trên Spring for Apache Pulsar. Khi binder có mặt trên classpath, ứng dụng Spring Boot có thể dùng các thuộc tính `spring.pulsar.*` để cấu hình client và administration. Các thuộc tính producer/consumer cấp binder hoặc cấp binding cũng được hỗ trợ để tùy chỉnh từng luồng.

Dependency binder trong Maven:

```xml
<dependency>
    <groupId>org.springframework.pulsar</groupId>
    <artifactId>spring-pulsar-spring-cloud-stream-binder</artifactId>
</dependency>
```

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.pulsar:spring-pulsar-spring-cloud-stream-binder'
}
```

Phiên bản dependency cần tương thích với Spring Boot và Spring Cloud Stream release train của ứng dụng. Dùng BOM hoặc dependency management của dự án để đồng bộ phiên bản; không tự ghép một bản Pulsar client khác với bản binder mà chưa kiểm tra tương thích.

Ví dụ binding:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder;processOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders.created
        processOrder-in-0:
          destination: persistent://acme/orders/orders.created
          group: order-processing
```

`destination` xác định topic logic mà binding sử dụng. Cấu hình xác thực và TLS cho Pulsar client được đặt ở `spring.pulsar.client`; cấu hình cho Pulsar Admin client được đặt ở `spring.pulsar.admin` trên Spring Boot mới. Tên property của Admin URL có thể khác ở release cũ, cần đối chiếu đúng BOM và property metadata của dự án.

## 3. Phân biệt địa chỉ Pulsar client và Pulsar Admin

Pulsar có hai giao diện kết nối thường dùng:

| Thành phần | Giao thức | URL ví dụ | Mục đích |
|---|---|---|---|
| Broker binary protocol | `pulsar://` hoặc `pulsar+ssl://` | `pulsar+ssl://pulsar.example.com:6651` | Producer và consumer gửi/nhận message |
| Admin HTTP API | `http://` hoặc `https://` | `https://pulsar.example.com:8443` | Quản lý tenant, namespace, topic, partition và permission |

`spring.pulsar.client.service-url` là URL cho Pulsar client. `spring.pulsar.admin.service-url` là URL cho Admin client trong Spring Boot hiện tại. Ở một số phiên bản Spring for Apache Pulsar cũ, property Admin URL dùng namespace `spring.pulsar.administration.service-url`. Không khai báo hai tên property theo phỏng đoán; kiểm tra property catalog của phiên bản đang dùng.

Ví dụ cấu hình URL với TLS:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.com:6651
    admin:
      service-url: https://pulsar.example.com:8443
```

Port `6651` và `8443` là các giá trị TLS thường gặp, nhưng có thể được thay đổi trong cluster. Luôn dùng URL, port và hostname do đội vận hành Pulsar cung cấp.

Nếu ứng dụng chỉ đọc/ghi topic đã được provision trước, có thể không cần gọi Admin API trong luồng khởi động. Nếu Pulsar Binder tự tạo topic hoặc partitioned topic, binder cần `PulsarAdministration`; khi đó Admin endpoint và quyền quản trị phải được cấu hình riêng.

## 4. TLS bảo vệ đường truyền như thế nào?

Khi client dùng `pulsar+ssl://`, dữ liệu giữa ứng dụng và broker được truyền qua TLS. Client kiểm tra certificate server bằng CA trust chain và hostname verification. Với Admin API, dùng `https://` để mã hóa HTTP request và response.

```text
Client                                  Broker
  |                                       |
  |---- ClientHello --------------------->|
  |<--- Server certificate ---------------|
  |                                       |
  |  Verify CA chain and hostname         |
  |                                       |
  |---- TLS handshake completes ----------|
  |                                       |
  |==== Encrypted Pulsar protocol ========|
```

TLS server authentication xác minh broker là máy chủ mà client dự định kết nối. Nếu dùng mutual TLS (mTLS), client còn gửi certificate của chính nó để broker xác thực danh tính client bằng certificate.

TLS không tự cấp quyền publish hoặc consume. Sau khi TLS handshake hoàn tất, Pulsar vẫn cần authentication và authorization theo cấu hình broker.

## 5. Không gửi token qua kết nối plaintext

Token/JWT là credential. Nếu gửi token qua kết nối plaintext, người có thể quan sát network traffic có thể lấy token và sử dụng nó cho đến khi token hết hạn hoặc bị thu hồi. Vì vậy, khi dùng token authentication, luôn bật TLS cho kết nối Pulsar.

Không dùng cấu hình production như:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar.example.com:6650
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_TOKEN}
```

Ví dụ trên chỉ minh họa vì sao token không nên được gửi qua URL plaintext. Cấu hình production dùng `pulsar+ssl://` cùng CA trust và xác minh hostname.

## 6. Cấu hình token/JWT authentication

Token authentication là lựa chọn phổ biến cho ứng dụng service-to-service. Pulsar client dùng plugin `AuthenticationToken`; token đại diện cho một principal/role đã được broker xác thực.

Ví dụ Spring Boot:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.com:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_CLIENT_TOKEN}
```

`PULSAR_CLIENT_TOKEN` được cung cấp từ secret store hoặc môi trường triển khai. Không đặt token thật trong Git, Docker image, log hoặc exception message.

Broker cần bật authentication provider tương ứng và cấu hình khóa xác minh token. Ví dụ với JWT asymmetric key:

```properties
authenticationEnabled=true
authenticationProviders=org.apache.pulsar.broker.authentication.AuthenticationProviderToken
tokenPublicKey=file:///etc/pulsar/keys/token-public.key
```

Tên property broker ở ví dụ trên thuộc `broker.conf` hoặc `standalone.conf`; giá trị khóa và provider phải khớp với cách cluster phát hành token. Với symmetric signing, broker dùng secret key thay vì public key. Private signing key chỉ được giữ ở hệ thống cấp token, không phân phối cho mọi ứng dụng.

## 7. OAuth2 authentication

Pulsar hỗ trợ OAuth2 access token. Client dùng plugin `AuthenticationOAuth2` để lấy access token từ authorization server theo thông tin issuer, credential và audience. Broker xác minh token theo provider và cấu hình tin cậy tương ứng.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.com:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.oauth2.AuthenticationOAuth2
        param:
          issuerUrl: ${PULSAR_OAUTH_ISSUER_URL}
          privateKey: ${PULSAR_OAUTH_PRIVATE_KEY_URI}
          audience: ${PULSAR_OAUTH_AUDIENCE}
          scope: ${PULSAR_OAUTH_SCOPE:}
```

Tên tham số plugin như `issuerUrl`, `privateKey` và `audience` phải đúng chữ hoa/chữ thường mà plugin yêu cầu. Spring Boot không áp dụng relaxed binding cho từng key trong map `authentication.param`. Ví dụ `issuer-url` hoặc `issuerurl` không tương đương `issuerUrl`.

Nếu đưa giá trị từ environment variable, hãy giữ key camelCase trong YAML rồi tham chiếu biến môi trường ở value, như ví dụ trên. Không đặt trực tiếp key `issuerUrl` thành tên biến môi trường vì quá trình chuyển đổi tên biến có thể làm mất chữ hoa giữa từ.

OAuth2 credential file hoặc private key phải được cấp quyền đọc tối thiểu cho process ứng dụng. Token được cấp có thời hạn; ứng dụng cần xử lý refresh và lỗi khi authorization server tạm thời không truy cập được.

## 8. Basic authentication và các plugin khác

Tùy cluster và plugin được cài đặt, Pulsar có thể hỗ trợ Basic, Athenz, SASL hoặc cơ chế authentication mở rộng. Ví dụ cấu hình Basic trong Spring Boot:

```yaml
spring:
  pulsar:
    client:
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationBasic
        param:
          userId: ${PULSAR_USER}
          password: ${PULSAR_PASSWORD}
```

Basic authentication không mã hóa credential. Chỉ dùng nó qua TLS và khi broker đã được cấu hình provider tương ứng. Không giả định mọi Pulsar cluster bật tất cả plugin; broker và client phải thống nhất plugin class cùng tham số.

Với Athenz, SASL hoặc plugin tùy chỉnh, tham số phải theo tài liệu plugin cụ thể. Không sao chép property của plugin OAuth2 sang plugin khác.

## 9. TLS bằng `PulsarClientBuilderCustomizer`

Spring Boot auto-configuration của Spring for Apache Pulsar cung cấp `PulsarClientBuilderCustomizer` để tùy chỉnh Pulsar client builder. Trong các phiên bản Spring for Apache Pulsar hiện hành, TLS/SSL không được biểu diễn đầy đủ bằng các property đơn giản; có thể cần customizer để cài CA certificate, client certificate, private key và chính sách xác minh.

Ví dụ chỉ bật TLS server authentication bằng CA trust:

```java
import org.apache.pulsar.spring.core.PulsarClientBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PulsarClientTlsConfiguration {

    @Bean
    PulsarClientBuilderCustomizer pulsarClientTlsCustomizer() {
        return clientBuilder -> clientBuilder
            .allowTlsInsecureConnection(false)
            .enableTlsHostnameVerification(true)
            .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt");
    }
}
```

Đường dẫn CA phải tồn tại trong filesystem của container/VM chạy ứng dụng. `allowTlsInsecureConnection(false)` yêu cầu kiểm tra certificate hợp lệ; `enableTlsHostnameVerification(true)` kiểm tra hostname trong certificate khớp hostname URL.

Không dùng `allowTlsInsecureConnection(true)` hoặc tắt hostname verification trong production để né lỗi certificate. Hãy sửa CA chain, SAN hoặc hostname của endpoint.

## 10. Cấu hình TLS cho Pulsar Admin client

Pulsar Binder có thể dùng `PulsarAdministration` để tạo topic, partition hoặc thực hiện thao tác quản trị khi binding khởi tạo. Admin client có builder customizer riêng: `PulsarAdminBuilderCustomizer`.

Ví dụ:

```java
import org.apache.pulsar.spring.core.PulsarAdminBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PulsarAdminTlsConfiguration {

    @Bean
    PulsarAdminBuilderCustomizer pulsarAdminTlsCustomizer() {
        return adminBuilder -> adminBuilder
            .allowTlsInsecureConnection(false)
            .enableTlsHostnameVerification(true)
            .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt");
    }
}
```

Client TLS customizer và Admin TLS customizer là hai cấu hình khác nhau. Nếu ứng dụng chỉ cấu hình client nhưng binder cần provision topic qua Admin API, thao tác quản trị có thể vẫn thất bại vì Admin client chưa được cấu hình HTTPS/trust/authentication.

Khi cluster dùng certificate khác nhau cho broker và admin endpoint, hãy dùng trust bundle phù hợp cho từng customizer. Không giả định cùng một CA hoặc certificate path luôn đúng với mọi cluster.

## 11. Mutual TLS (mTLS) bằng PEM certificate

mTLS yêu cầu cả hai phía xác minh certificate của nhau. Client cần trust CA của broker và gửi certificate/key của chính nó. Broker cần bật TLS, trust CA cấp certificate client và yêu cầu client certificate khi kết nối.

Ví dụ client customizer với PEM:

```java
@Bean
PulsarClientBuilderCustomizer pulsarClientMtlsCustomizer() {
    return clientBuilder -> clientBuilder
        .allowTlsInsecureConnection(false)
        .enableTlsHostnameVerification(true)
        .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt")
        .tlsCertificateFilePath("/etc/pulsar/tls/client.crt")
        .tlsKeyFilePath("/etc/pulsar/tls/client.key");
}
```

Admin client cũng cần certificate nếu Admin endpoint yêu cầu mTLS:

```java
@Bean
PulsarAdminBuilderCustomizer pulsarAdminMtlsCustomizer() {
    return adminBuilder -> adminBuilder
        .allowTlsInsecureConnection(false)
        .enableTlsHostnameVerification(true)
        .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt")
        .tlsCertificateFilePath("/etc/pulsar/tls/client.crt")
        .tlsKeyFilePath("/etc/pulsar/tls/client.key");
}
```

Certificate client phải được CA mà broker tin cậy ký và phải còn hiệu lực. Private key cần được bảo vệ như secret; không đưa vào source control hoặc image layer.

## 12. Cấu hình broker cho mTLS

Ở phía broker, cần bật authentication, chọn TLS authentication provider và cấu hình TLS listener/certificate. Ví dụ các thuộc tính chính trong `broker.conf`:

```properties
authenticationEnabled=true
authenticationProviders=org.apache.pulsar.broker.authentication.AuthenticationProviderTls

brokerServicePortTls=6651
webServicePortTls=8443

tlsTrustCertsFilePath=/etc/pulsar/tls/ca.crt
tlsCertificateFilePath=/etc/pulsar/tls/broker.crt
tlsKeyFilePath=/etc/pulsar/tls/broker.key

tlsRequireTrustedClientCertOnConnect=true
tlsAllowInsecureConnection=false
```

Tên port có thể khác theo cấu hình cluster. Với Pulsar Proxy, cần cấu hình TLS/authentication tương ứng ở proxy và thiết lập proxy role đúng theo hướng dẫn của Pulsar. Không cấu hình broker nhưng lại chỉ đổi URL client sang `pulsar+ssl://`; hai phía phải cùng bật TLS và thống nhất CA/certificate.

## 13. Phân biệt TLS server authentication và mTLS

| Đặc điểm | TLS server authentication | Mutual TLS |
|---|---|---|
| Client xác minh server certificate | Có | Có |
| Server xác minh client certificate | Không bắt buộc | Có |
| Client cần certificate riêng | Không bắt buộc | Có |
| Dùng token/OAuth2 kết hợp | Có | Có thể, tùy kiến trúc |
| Mục tiêu chính | Mã hóa đường truyền và xác minh broker | Thêm xác thực client bằng certificate |

Token hoặc OAuth2 có thể được dùng trên TLS thông thường. mTLS là một cách xác thực client; không đồng nghĩa với authorization. Sau khi certificate xác định role, broker vẫn cần policy để quyết định role đó được phép truy cập tài nguyên nào.

## 14. Cấu hình xác thực riêng cho Admin client

Khi binder tự provision topic, Admin client cần xác thực riêng. Spring Boot hiện hỗ trợ nhánh `spring.pulsar.admin.authentication`; không mặc định rằng cấu hình `spring.pulsar.client.authentication` tự động áp dụng cho Admin client.

Ví dụ token authentication cho cả hai client:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.com:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_RUNTIME_TOKEN}
    admin:
      service-url: https://pulsar.example.com:8443
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_PROVISIONER_TOKEN}
```

Ví dụ dùng hai token để tách quyền:

- `PULSAR_RUNTIME_TOKEN`: role chỉ có quyền consume input topic và produce output topic.
- `PULSAR_PROVISIONER_TOKEN`: role được phép tạo hoặc kiểm tra tài nguyên cần thiết trong namespace được giao.

Nếu tổ chức không cho ứng dụng tự tạo topic, pipeline hạ tầng có thể provision topic trước; runtime client khi đó chỉ cần quyền publish/consume. Tránh dùng superuser token cho mọi instance ứng dụng.

## 15. Authentication và authorization trên broker

Pulsar phân biệt authentication provider và authorization provider. Authentication xác định role token; authorization kiểm tra thao tác của role trên tài nguyên. Nếu chỉ bật authentication mà không bật authorization, role đã xác thực có thể có quyền rộng trên cluster theo cấu hình mặc định của broker.

Ví dụ bật authorization:

```properties
authenticationEnabled=true
authenticationProviders=org.apache.pulsar.broker.authentication.AuthenticationProviderToken
authorizationEnabled=true
superUserRoles=admin
```

Role `admin` được giữ cho tác vụ quản trị. Ứng dụng `order-stream` nên dùng role riêng và được cấp quyền trên namespace/topic cần thiết.

Với Pulsar, tên topic đầy đủ có dạng:

```text
persistent://tenant/namespace/topic
```

Quyền có thể được cấp ở namespace hoặc topic tùy phạm vi cần thiết. Cấp quyền ở namespace thuận tiện khi service cần nhiều topic trong cùng namespace; cấp ở topic giúp giới hạn hẹp hơn.

## 16. Cấp quyền produce và consume theo least privilege

Giả sử function xử lý đơn hàng:

```text
Input:  persistent://acme/orders/orders.created
Output: persistent://acme/orders/orders.enriched
Role:   order-stream
```

Role này cần consume input và produce output. Ví dụ cấp quyền ở namespace:

```bash
pulsar-admin namespaces grant-permission acme/orders \
  --role order-stream \
  --actions consume,produce
```

Nếu tách input và output ở namespace khác nhau, chỉ cấp `consume` trên namespace đầu vào và `produce` trên namespace đầu ra. Không cấp quyền quản trị tenant hoặc superuser cho role runtime chỉ vì ứng dụng cần publish/consume.

Ví dụ ma trận quyền:

| Role | Namespace/topic | Quyền cần thiết |
|---|---|---|
| `order-stream` | `acme/orders` | Consume input và produce output |
| `order-provisioner` | `acme/orders` | Tạo/kiểm tra topic theo quy trình provisioning |
| `platform-admin` | Cluster/tenant | Quản trị tenant, namespace, policy và permission |

Quyền thực tế cần được xác minh theo các thao tác binder thực hiện. Schema lookup, subscription administration hoặc topic provisioning có thể yêu cầu quyền bổ sung. Hãy bắt đầu với quyền tối thiểu, chạy integration test và chỉ cấp thêm quyền khi có lỗi authorization cụ thể.

## 17. Binder topic provisioning và quyền Admin API

Pulsar Binder có topic provisioner. Khi topic chưa tồn tại, binder có thể tạo topic cơ bản; với partitioned topic, binder dùng `PulsarAdministration` và Admin API. Do đó, cần phân biệt quyền của Pulsar client với quyền của Admin client:

| Thành phần | Tác vụ | Credential |
|---|---|---|
| `PulsarClient` | Publish/consume message | Runtime token hoặc certificate |
| `PulsarAdministration` | Tạo/kiểm tra tenant, namespace, topic, partition theo cấu hình | Admin/provisioning token hoặc certificate |

Nếu topic được tạo trước bằng IaC, runtime role có thể không cần quyền tạo topic. Nếu binder tự provision, Admin client cần quyền phù hợp trên namespace. Không giải quyết lỗi provisioning bằng cách biến runtime role thành superuser.

Trong Spring Cloud Stream, destination được khai báo trên binding:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders.created
        processOrder-out-0:
          destination: persistent://acme/orders/orders.enriched
```

Xác thực và TLS của client/Admin vẫn được cấu hình qua các Spring Pulsar client/admin properties và builder customizer tương ứng.

## 18. Mẫu cấu hình hoàn chỉnh cho token + TLS

Ví dụ ứng dụng dùng token authentication, TLS server verification và tách runtime token khỏi provisioning token:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.com:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_RUNTIME_TOKEN}
    admin:
      service-url: https://pulsar.example.com:8443
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_PROVISIONER_TOKEN}

  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders.created
          group: order-processing
        processOrder-out-0:
          destination: persistent://acme/orders/orders.enriched
```

Thêm `PulsarClientBuilderCustomizer` và `PulsarAdminBuilderCustomizer` để cấu hình CA trust, hostname verification và certificate nếu cần. Tên property Admin URL cần khớp phiên bản Spring Boot/Spring Pulsar của dự án.

## 19. Cấu hình TLS với customizer cho cả client và admin

Ví dụ một cấu hình Java gom hai customizer vào cùng class:

```java
import org.apache.pulsar.spring.core.PulsarAdminBuilderCustomizer;
import org.apache.pulsar.spring.core.PulsarClientBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PulsarTlsConfiguration {

    @Bean
    PulsarClientBuilderCustomizer pulsarClientTlsCustomizer() {
        return builder -> builder
            .allowTlsInsecureConnection(false)
            .enableTlsHostnameVerification(true)
            .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt");
    }

    @Bean
    PulsarAdminBuilderCustomizer pulsarAdminTlsCustomizer() {
        return builder -> builder
            .allowTlsInsecureConnection(false)
            .enableTlsHostnameVerification(true)
            .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt");
    }
}
```

Nếu dùng mTLS, bổ sung `tlsCertificateFilePath` và `tlsKeyFilePath` cho cả builder client/admin khi endpoint tương ứng yêu cầu client certificate. Đảm bảo file path tồn tại trong runtime container và private key có quyền đọc tối thiểu.

## 20. Quản lý secret và certificate

Token, OAuth credential, password, private key và client certificate là dữ liệu nhạy cảm. Một quy trình production nên:

- Lấy secret từ Vault, Kubernetes Secret, cloud secret manager hoặc secret injection của nền tảng.
- Tránh ghi credential vào Git, source code, Dockerfile, image layer hoặc file log.
- Không in token hay private key trong exception, debug log hoặc Actuator details.
- Dùng token có thời hạn và role hẹp.
- Lập lịch xoay token/certificate trước khi hết hạn.
- Theo dõi ngày hết hạn certificate và CA rotation.
- Thu hồi token/certificate khi service bị xóa hoặc có sự cố.
- Giới hạn quyền đọc file private key theo UID/GID của ứng dụng.
- Không mount private key vào container không cần truy cập Pulsar.

Với OAuth2, credential file cần được cấp phát an toàn và có thể thay thế khi rotation. Với JWT, private signing key thuộc hệ thống cấp token; broker chỉ cần material xác minh phù hợp. Với mTLS, private key client không được chia sẻ giữa các ứng dụng nếu cần phân biệt danh tính và khả năng thu hồi riêng.

## 21. Hostname verification và certificate SAN

Certificate server cần chứa Subject Alternative Name (SAN) khớp hostname mà client sử dụng trong URL. Ví dụ client kết nối `pulsar+ssl://pulsar.example.com:6651`, certificate cần có SAN phù hợp với `pulsar.example.com`.

Các lỗi phổ biến:

- Certificate chỉ có tên DNS nội bộ nhưng client kết nối bằng IP.
- Client dùng alias DNS không có trong SAN.
- Certificate hết hạn hoặc chưa có hiệu lực.
- CA trung gian bị thiếu trong trust chain.
- Client tin nhầm CA hoặc mount nhầm file certificate.
- Admin endpoint dùng certificate khác với broker endpoint.

Không tắt hostname verification để bỏ qua các lỗi này. Sửa certificate SAN, DNS hoặc URL để chúng khớp nhau.

## 22. Proxy và TLS termination

Một số cluster cho client kết nối qua Pulsar Proxy hoặc gateway. Khi đó cần phân biệt certificate và danh tính ở từng chặng:

```text
Application -- TLS/auth --> Pulsar Proxy -- TLS/auth --> Broker
```

Proxy xác thực client rồi dùng credential riêng để kết nối broker. Broker có thể cần `proxyRoles` và cấu hình forwarded original principal. Cả proxy role và original principal có thể cần quyền trên tài nguyên theo cấu hình authorization.

Nếu dùng mTLS qua proxy, certificate mà broker nhìn thấy có thể là certificate của proxy, không phải certificate gốc của client. Cấu hình proxy roles, original authentication data và authorization phải tuân theo hướng dẫn Pulsar; không tự đặt proxy role thành superuser để né lỗi.

## 23. Kiểm tra kết nối bằng Pulsar CLI

Trước khi debug Spring Cloud Stream, có thể dùng CLI với cùng endpoint, TLS và credential để tách lỗi hạ tầng khỏi lỗi cấu hình ứng dụng. Ví dụ token qua TLS:

```bash
pulsar-client --url pulsar+ssl://pulsar.example.com:6651 \
  --auth-plugin org.apache.pulsar.client.impl.auth.AuthenticationToken \
  --auth-params 'token:<TOKEN_FROM_SECRET_STORE>' \
  produce persistent://acme/orders/orders.created \
  -m '{"eventId":"evt-1","orderId":"order-1"}'
```

Không đưa token thật vào lịch sử shell hoặc command log dùng chung. Trong production, ưu tiên cấu hình CLI qua file client.conf được bảo vệ hoặc secret injection của môi trường quản trị.

Kiểm tra Admin API bằng `pulsar-admin` với HTTPS và authentication tương ứng. Nếu CLI không kết nối được bằng cùng certificate/role, lỗi có thể nằm ở cluster, network, TLS hoặc quyền chứ không phải Spring Cloud Stream.

## 24. Kiểm tra authorization bằng thao tác thực tế

Một bài test kết nối nên kiểm tra ít nhất:

1. Client mở được TLS connection đến broker.
2. Broker xác thực được token/certificate và trả về principal mong đợi.
3. Principal có quyền `produce` trên output topic.
4. Principal có quyền `consume` trên input topic/subscription.
5. Admin principal có quyền cần thiết nếu binder tự provision topic.
6. Schema lookup/registration hoạt động nếu ứng dụng dùng schema registry hoặc native Pulsar schema.
7. Role không có quyền truy cập topic/namespace ngoài phạm vi được cấp.

Kiểm thử negative case cũng quan trọng: dùng role chỉ có `consume` để thử publish và xác nhận broker từ chối; dùng role chỉ có `produce` để thử consume và xác nhận bị từ chối. Điều này xác nhận ACL thực sự có hiệu lực.

## 25. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Connection refused` | Sai host/port, broker TLS listener chưa bật hoặc network policy chặn | Kiểm tra service URL, port và listener broker |
| TLS handshake failure | CA sai, certificate hết hạn, protocol/cipher không tương thích | Kiểm tra certificate chain và TLS config hai phía |
| Hostname verification failed | URL hostname không khớp SAN | Sửa DNS/URL hoặc cấp certificate đúng SAN |
| Token authentication failed | Token hết hạn, sai signing key hoặc provider | Kiểm tra token issuer, key và broker auth provider |
| OAuth2 token request failed | Issuer URL, private key, audience hoặc clock sai | Kiểm tra OAuth credential và thời gian hệ thống |
| Plugin không nhận param | Sai tên key camelCase trong map | Dùng đúng tên tham số như `issuerUrl` |
| Client kết nối được nhưng publish bị từ chối | Role thiếu quyền `produce` | Cấp quyền tối thiểu trên output namespace/topic |
| Consume bị từ chối | Role thiếu quyền `consume` hoặc subscription policy | Kiểm tra namespace/topic permission và subscription |
| Binder startup fail khi tạo topic | Admin URL sai, Admin TLS/authentication thiếu hoặc role thiếu quyền | Cấu hình Admin client riêng và cấp quyền provisioning |
| Producer chạy nhưng topic provision fail | Runtime token có quyền publish nhưng Admin token không có quyền quản trị | Tách runtime identity và provisioner identity |
| Client TLS hoạt động nhưng Admin TLS lỗi | Chỉ có `PulsarClientBuilderCustomizer`, thiếu Admin customizer | Cấu hình `PulsarAdminBuilderCustomizer` |
| `401`/authentication error ở Admin API | Admin credential/provider không khớp | Kiểm tra `spring.pulsar.admin.authentication` |
| `403`/authorization error | Principal đã xác thực nhưng không có quyền | Kiểm tra role và ACL, không đổi sang superuser |
| Hoạt động qua proxy nhưng bị từ chối ở broker | Proxy role/original principal hoặc forwarded credentials sai | Kiểm tra `proxyRoles` và original principal flow |
| Chỉ lỗi sau khi rotate cert | Client/admin customizer vẫn dùng path hoặc cert cũ | Đồng bộ secret mount, trust bundle và restart/refresh theo thiết kế |

## 26. Kiểm thử tích hợp TLS và authentication

Nên có các kịch bản integration test với cluster Pulsar có cấu hình bảo mật tương tự production:

| Kịch bản | Thao tác | Kết quả cần xác minh |
|---|---|---|
| TLS server verification | Kết nối bằng CA đúng và hostname đúng | Handshake thành công |
| CA không tin cậy | Dùng CA sai | TLS handshake bị từ chối |
| Hostname không khớp | Dùng hostname không nằm trong SAN | Hostname verification thất bại |
| Token hợp lệ | Kết nối với token đúng | Broker xác thực principal |
| Token hết hạn/sai chữ ký | Dùng token không hợp lệ | Authentication bị từ chối |
| OAuth2 credential | Lấy token từ issuer hợp lệ | Client kết nối và refresh theo cấu hình |
| mTLS hợp lệ | Dùng client certificate được CA tin cậy cấp | Broker chấp nhận certificate |
| mTLS thiếu certificate | Không gửi client certificate khi broker yêu cầu | Handshake/authentication thất bại |
| Thiếu produce permission | Dùng role chỉ có consume | Publish bị từ chối |
| Thiếu consume permission | Dùng role chỉ có produce | Subscribe/consume bị từ chối |
| Admin client | Dùng credential provisioner | Admin API thực hiện được thao tác được cấp |
| Admin thiếu quyền | Dùng runtime role để tạo topic | Provisioning bị từ chối |
| Secret rotation | Thay token/certificate theo quy trình | Ứng dụng kết nối lại bằng credential mới |
| Proxy path | Kết nối qua proxy đã bật auth | Broker nhận đúng original principal và authorization |

Test unit của function không xác minh TLS handshake hoặc broker ACL. Các kịch bản này cần broker thực hoặc môi trường test Pulsar được cấu hình TLS/authentication/authorization tương ứng.

## 27. Checklist triển khai production

1. Xác định phiên bản Spring Boot, Spring Cloud Stream và Spring for Apache Pulsar tương thích.
2. Dùng `pulsar+ssl://` cho binary client endpoint và `https://` cho Admin endpoint.
3. Cấp CA trust bundle hợp lệ và giữ hostname verification bật.
4. Chọn authentication plugin phù hợp: token, OAuth2, mTLS hoặc plugin tổ chức hỗ trợ.
5. Bật broker authentication provider tương ứng.
6. Bật authorization và cấp role riêng cho service.
7. Cấp `consume` cho input và `produce` cho output; tránh superuser runtime.
8. Cấu hình Admin client riêng nếu binder tự provision topic.
9. Tách quyền runtime client khỏi quyền provisioner/admin.
10. Dùng secret manager hoặc secret injection để cấp token, password và private key.
11. Lập lịch token/certificate rotation và theo dõi thời hạn.
12. Kiểm tra SAN, CA chain, TLS port, Admin port và proxy path.
13. Kiểm thử positive/negative authorization, TLS failure và broker recovery.
14. Theo dõi authentication failure, authorization denial, reconnect và certificate expiry.

## 28. Tự kiểm tra

- [ ] Phân biệt TLS, authentication và authorization.
- [ ] Phân biệt Pulsar binary service URL với Admin HTTP URL.
- [ ] Cấu hình `spring.pulsar.client.service-url` dùng `pulsar+ssl://`.
- [ ] Cấu hình token plugin `AuthenticationToken`.
- [ ] Cấu hình OAuth2 plugin với đúng key camelCase như `issuerUrl`.
- [ ] Biết khi nào dùng `PulsarClientBuilderCustomizer` cho TLS.
- [ ] Cấu hình riêng `PulsarAdminBuilderCustomizer` khi Admin endpoint dùng TLS.
- [ ] Phân biệt TLS server authentication với mTLS.
- [ ] Bật broker authentication provider tương ứng.
- [ ] Bật authorization và cấp quyền produce/consume theo least privilege.
- [ ] Phân biệt runtime credential với Admin/provisioner credential.
- [ ] Không lưu token/private key trong source code hoặc log.
- [ ] Kiểm tra hostname verification, CA chain và certificate expiry.
- [ ] Thiết kế integration test cho TLS, authentication và ACL.

## Kết luận

Để bảo vệ Spring Cloud Stream Pulsar Binder, cấu hình TLS cho Pulsar client và Admin client, sau đó chọn authentication plugin như token/JWT, OAuth2 hoặc mTLS. Spring Boot cung cấp `spring.pulsar.client.*` và `spring.pulsar.admin.*`; TLS thường cần `PulsarClientBuilderCustomizer` và `PulsarAdminBuilderCustomizer` để cấu hình trust certificate, hostname verification và client certificate. Broker phải bật provider tương ứng, đồng thời bật authorization để giới hạn role theo topic/namespace. Runtime client chỉ cần quyền consume input và produce output; Admin client dùng danh tính riêng nếu binder tự provision. Bảo vệ secret, xác minh hostname, xoay token/certificate và kiểm thử cả trường hợp được phép lẫn bị từ chối là các bước cần có trước khi triển khai production.

## Tài liệu tham khảo

- Spring Cloud Stream — Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Spring Boot — Apache Pulsar Support: https://docs.spring.io/spring-boot/reference/messaging/pulsar.html
- Spring for Apache Pulsar — Pulsar Client and Authentication: https://pulsar.apache.org/pulsar-spring/reference/pulsar/pulsar-client.html
- Apache Pulsar 5.0 — Authentication using mTLS: https://pulsar.apache.org/docs/5.0.x/security-tls-authentication/
- Apache Pulsar 5.0 — Authentication using JWT: https://pulsar.apache.org/docs/5.0.x/security-jwt/
- Apache Pulsar 5.0 — Authentication using OAuth2: https://pulsar.apache.org/docs/5.0.x/security-oauth2/
- Apache Pulsar 5.0 — Authentication and Authorization: https://pulsar.apache.org/docs/5.0.x/security-authorization/
