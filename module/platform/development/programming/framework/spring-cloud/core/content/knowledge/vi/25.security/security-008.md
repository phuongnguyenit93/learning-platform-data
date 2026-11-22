# Bảo vệ thông tin xác thực khi gọi nguồn cấu hình hoặc registry

## 1. Vì sao credential của Config Server và registry cần được bảo vệ riêng?

Một ứng dụng Spring Cloud thường phải xác thực với nhiều hệ thống bên ngoài ngay từ lúc khởi động:

- **Config Server** cung cấp cấu hình theo application, profile và label.
- **Service Registry** như Eureka hoặc Consul cho phép đăng ký instance và tìm các service khác.
- **Config backend** như Git hoặc Vault được chính Config Server dùng để lấy dữ liệu cấu hình.
- **Secret manager** như Vault cấp token, password hoặc certificate cho ứng dụng và các integration.

Các kết nối này thuộc những ranh giới tin cậy khác nhau. Credential của ứng dụng để đọc Config Server không phải credential mà Config Server dùng để đọc Git/Vault. Token để đọc Consul KV cũng không nhất thiết cần quyền đăng ký service hoặc deregister instance.

Nếu dùng một tài khoản dùng chung cho mọi service, lưu password trong application.yml, nhúng token vào URL hoặc ghi credential vào service metadata, một lần lộ secret có thể mở rộng quyền truy cập sang nhiều hệ thống. Secret cũng có thể bị sao chép vào log, image, build artifact, shell history hoặc hệ thống giám sát.

Bài học thuộc chương **Bảo mật** của **SPRING_CLOUD_CORE**. Mục tiêu là thiết kế cách cấp credential cho Config Client và Discovery Client, tách quyền giữa các luồng gọi, sử dụng secret ngoài artifact, bảo vệ kênh TLS, giới hạn quyền truy cập theo từng application và kiểm tra việc xoay vòng/revoke credential.

## 2. Phân biệt các luồng xác thực

Trước khi cấu hình, hãy xác định chính xác ai gọi ai và credential thuộc về thành phần nào.

| Luồng | Thành phần gọi | Thành phần nhận | Credential thường gặp |
| --- | --- | --- | --- |
| Lấy cấu hình | Config Client | Config Server | HTTP Basic, OAuth2 Bearer, client certificate |
| Tìm Config Server bằng discovery | Config Client | Eureka/Consul | Eureka Basic/mTLS hoặc Consul ACL token |
| Đăng ký và tra cứu service | Discovery Client | Service Registry | Consul ACL token, Eureka Basic/mTLS |
| Đọc key-value từ Consul | Consul Config Client | Consul KV API | Consul Config ACL token |
| Đọc secrets từ Vault | Spring Cloud Vault | Vault | Kubernetes auth, AppRole, cloud IAM hoặc Vault token |
| Lấy dữ liệu backend | Config Server | Git, Vault hoặc backend khác | Credential chỉ dành cho Config Server |

Có hai nguyên tắc cần giữ:

1. Credential của mỗi luồng chỉ có quyền cần thiết cho luồng đó.
2. Credential phải có sẵn từ một nguồn tin cậy trước khi ứng dụng cần dùng nó.

Đặc biệt, Config Client phải có credential trước khi gửi request đầu tiên tới Config Server. Không thể trông chờ Config Server trả về password cần thiết để chính Config Client đăng nhập vào Config Server đó. Thông tin dùng để thiết lập kết nối ban đầu phải đến từ local environment, mounted secret, workload identity hoặc một bootstrap trust source độc lập.

## 3. Không lưu secret trong source code hoặc image

Không commit các giá trị sau vào repository:

```yaml
spring:
  cloud:
    config:
      username: config-client
      password: real-password
    consul:
      discovery:
        acl-token: real-consul-token

eureka:
  client:
    serviceUrl:
      defaultZone: https://user:real-password@eureka.internal/eureka/
```

Không đặt credential trong Dockerfile ENV, build argument, file .env được commit, script khởi động, command-line argument hoặc URL được ghi vào log. Việc xóa secret khỏi file ở commit mới không loại bỏ nó khỏi Git history hoặc các artifact đã phát hành.

Thay vào đó, giữ trong file cấu hình chỉ các thông tin không nhạy cảm như hostname, port, scheme và tên property. Giá trị bí mật được cấp ở runtime qua một trong các nguồn:

- Environment variable do nền tảng triển khai inject.
- File secret được mount read-only vào container.
- Spring Cloud Vault hoặc secret manager tương đương.
- Workload identity hoặc machine identity do Kubernetes/cloud platform cấp.
- Certificate/key store được mount từ secret volume.

Environment variable thuận tiện nhưng không phải lúc nào cũng là nơi lưu secret tốt nhất: giá trị có thể xuất hiện trong process environment, công cụ chẩn đoán hoặc metadata của nền tảng. Với secret cần bảo vệ chặt, configuration tree từ mounted secret hoặc secret manager thường dễ kiểm soát hơn.

## 4. Dùng Spring Boot configuration tree cho secret được mount

Spring Boot hỗ trợ prefix configtree: để biến tên file trong một thư mục thành property name và nội dung file thành property value. Kubernetes Secrets và Docker Secrets có thể được mount thành các file như vậy.

Ví dụ volume /run/secrets/ chứa các file:

```text
/run/secrets/
  spring.cloud.config.username
  spring.cloud.config.password
  spring.cloud.consul.config.acl-token
  spring.cloud.consul.discovery.acl-token
```

Tên file có dấu chấm được ánh xạ thành property tương ứng. application.yml chỉ cần khai báo vị trí và endpoint không bí mật:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  cloud:
    config:
      uri: https://config.internal.example
    consul:
      scheme: https
      host: consul.internal.example
      port: 8501
```

Sau khi import, Spring Environment có các property spring.cloud.config.username, spring.cloud.config.password, spring.cloud.consul.config.acl-token và spring.cloud.consul.discovery.acl-token. Spring Cloud binding đọc các giá trị đó như những property thông thường.

Nếu thư mục secret bắt buộc phải tồn tại trong production, không thêm prefix optional:. Khi volume không được mount hoặc thiếu cấu hình cần thiết, ứng dụng nên fail lúc khởi động thay vì âm thầm chạy với một cấu hình không có bảo vệ. Chỉ dùng optional:configtree: cho môi trường mà secret volume thực sự có thể không tồn tại và việc tiếp tục khởi động là một quyết định có chủ đích.

Giới hạn quyền đọc thư mục và file cho user chạy ứng dụng. Mount volume read-only, không copy secret vào image layer, không ghi nội dung file ra log và không đưa file mount vào artifact backup không được bảo vệ.

### 4.1. Dùng environment variable khi nền tảng quản lý tốt vòng đời secret

Nếu nền tảng đã có cơ chế inject environment variable và giới hạn quyền đọc, có thể dùng placeholder:

```yaml
spring:
  cloud:
    config:
      uri: https://config.internal.example
      username: ${CONFIG_SERVER_USERNAME}
      password: ${CONFIG_SERVER_PASSWORD}
```

Với Consul:

```yaml
spring:
  cloud:
    consul:
      config:
        acl-token: ${CONSUL_CONFIG_ACL_TOKEN}
      discovery:
        acl-token: ${CONSUL_DISCOVERY_ACL_TOKEN}
```

Không đặt default value là một password mẫu hoặc token dùng chung. Khi credential bắt buộc mà không có, placeholder không được resolve nên startup báo lỗi sớm. Cần kiểm soát quyền đọc environment và tránh in toàn bộ process environment khi chẩn đoán.

## 5. Xác thực Config Client với Config Server bằng HTTP Basic

Spring Cloud Config Client hỗ trợ HTTP Basic. Có thể cấu hình URI, username và password riêng:

```yaml
spring:
  config:
    import: "configserver:"
  cloud:
    config:
      uri: https://config.internal.example
      username: ${CONFIG_SERVER_USERNAME}
      password: ${CONFIG_SERVER_PASSWORD}
```

spring.cloud.config.username và spring.cloud.config.password được dùng để tạo thông tin xác thực cho request. Các property này có thể đến từ environment variable hoặc configuration tree đã nạp trước đó.

Spring Cloud Config cũng hỗ trợ userinfo trong URI, nhưng URL có thể bị ghi vào access log, proxy log, exception, tracing span hoặc cấu hình chẩn đoán. Ưu tiên tách credential khỏi URL nếu client/version hỗ trợ property riêng. Nếu phải dùng URL có userinfo vì giới hạn của cơ chế tích hợp, hãy redaction URL ở mọi nơi có thể ghi log và giới hạn quyền đọc cấu hình.

Với Config Data import bắt buộc trong production, bỏ prefix optional:. Khi Config Server không thể truy cập hoặc credential không hợp lệ, startup cần thất bại để ứng dụng không chạy với cấu hình mặc định thiếu các giá trị bắt buộc. optional:configserver: chỉ phù hợp khi ứng dụng có thể tiếp tục hoạt động an toàn mà không có remote configuration.

### 5.1. OAuth2 Bearer token

Config Server có thể được bảo vệ bằng OAuth2 Resource Server và JWT Bearer token. Tuy nhiên, Config Client không tự động lấy OAuth2 token chỉ vì Config Server yêu cầu Bearer authentication.

Ứng dụng cần có cơ chế lấy token từ authorization server, chẳng hạn OAuth2 Client với client_credentials, rồi gắn token vào request Config Server. Có thể dùng custom request client/RestTemplate hoặc header property phù hợp với kiểu tích hợp của release đang dùng.

Ví dụ khi token được cấp sẵn từ secret manager:

```yaml
spring:
  cloud:
    config:
      uri: https://config.internal.example
      headers:
        Authorization: "Bearer ${CONFIG_SERVER_ACCESS_TOKEN}"
```

Đây là token tĩnh được inject ở startup. Nếu dùng token ngắn hạn cần tự động gia hạn, hãy tích hợp OAuth2 client manager hoặc custom request client có khả năng lấy và refresh token; đừng giả định một chuỗi Bearer trong cấu hình sẽ tự xoay vòng.

Không ghi header Authorization vào HTTP wire log. Token cần audience, scope và expiry phù hợp với Config Server. Không dùng access token có quyền rộng cho nhiều API khác nhau.

Nếu cấu hình nhiều Config Server URL, hãy kiểm tra giới hạn xác thực theo từng endpoint của phiên bản đang dùng. Tài liệu Config Client hiện hành chỉ hỗ trợ credential HTTP Basic riêng cho từng Config Server khi userinfo được nhúng trong từng URL của `spring.cloud.config.uri`; các cơ chế auth khác không có cùng khả năng per-server. Tránh giả định một bộ username/password sẽ tự được chọn đúng cho mọi URL trong danh sách.

## 6. Bảo vệ Config Server theo từng application

Chỉ yêu cầu người dùng đăng nhập chưa đủ nếu mọi client đã xác thực đều có thể đọc cấu hình của mọi application. Config Server phục vụ tài nguyên theo đường dẫn có dạng:

`/{application}/{profile}/{label}`

Nếu một service có thể đổi {application} trong URL và đọc được cấu hình của service khác, secret của các service sẽ bị lộ chéo.

Config Server nên áp dụng authorization policy để principal chỉ đọc được cấu hình thuộc application của mình. Ví dụ, principal/JWT claim inventory-service chỉ được truy cập đường dẫn /inventory-service/**; request /payment-service/** phải bị từ chối.

Có thể triển khai policy bằng Spring Security SecurityFilterChain hoặc RequestMatcher. Mô hình khái quát:

```java
import org.springframework.security.authorization.AuthorizationDecision;

.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/actuator/health").permitAll()
    .requestMatchers("/{application}/**").access((authentication, context) -> {
        String requestedApplication =
                context.getVariables().get("application");
        String principal = authentication.get().getName();

        return new AuthorizationDecision(
                principal.equals(requestedApplication)
        );
    })
    .anyRequest().authenticated()
)
```

Đây là đoạn minh họa phần authorization; cần đặt trong SecurityFilterChain hoàn chỉnh, kiểm tra matcher theo đúng context path và quy tắc URL của hệ thống. Với JWT, nên so sánh application ID với claim được issuer tin cậy phát hành, không lấy tên service tùy ý từ header do client tự gửi.

Credential nên là identity riêng của từng workload. Nếu inventory-service bị xâm nhập, identity của nó chỉ được đọc cấu hình inventory-service, không được dùng để tải secret của payment-service, user-service hoặc Config Server.

## 7. TLS và mutual TLS cho Config Server

HTTP Basic chỉ mã hóa password khi được truyền qua TLS. Không gửi credential hoặc cấu hình nhạy cảm qua HTTP thuần trên mạng không tin cậy.

Trong production:

- Dùng HTTPS cho Config Server.
- Xác minh hostname và certificate chain của server.
- Cấu hình trust store nếu server dùng CA nội bộ.
- Dùng mutual TLS (mTLS) khi cần xác thực workload bằng client certificate.
- Lưu private key và password của key store trong secret volume hoặc secret manager.
- Có quy trình gia hạn và thay certificate trước khi hết hạn.

Ví dụ Config Client dùng client certificate:

```yaml
spring:
  cloud:
    config:
      uri: https://config.internal.example
      tls:
        enabled: true
        key-store: /run/secrets/config-client.p12
        key-store-type: PKCS12
        key-store-password: ${CONFIG_CLIENT_KEYSTORE_PASSWORD}
        key-password: ${CONFIG_CLIENT_KEY_PASSWORD}
        trust-store: /run/secrets/config-server-truststore.p12
        trust-store-type: PKCS12
        trust-store-password: ${CONFIG_TRUSTSTORE_PASSWORD}
```

Tên property và cách cấu hình TLS phụ thuộc Spring Cloud Config Client version. Kiểm tra reference của release train đang dùng trước khi áp dụng. Không tắt xác minh certificate để xử lý lỗi CA; hãy cài CA đúng vào trust store hoặc sửa hostname/SAN của certificate.

TLS bảo vệ kênh truyền và xác thực peer theo certificate. Nó không thay thế authorization: client certificate vẫn cần được ánh xạ tới principal và quyền đọc cấu hình phù hợp.

## 8. Bảo vệ Consul ACL token cho Config và Discovery

Spring Cloud Consul có hai property riêng cho token:

- spring.cloud.consul.config.acl-token dùng cho thao tác đọc cấu hình từ Consul KV.
- spring.cloud.consul.discovery.acl-token dùng cho service discovery và các thao tác liên quan discovery.

Ví dụ:

```yaml
spring:
  cloud:
    consul:
      scheme: https
      host: consul.internal.example
      port: 8501
      config:
        acl-token: ${CONSUL_CONFIG_ACL_TOKEN}
      discovery:
        acl-token: ${CONSUL_DISCOVERY_ACL_TOKEN}
```

Không mặc định dùng một token có toàn quyền cho cả KV, catalog, service registration và các thao tác quản trị. Tạo policy riêng:

| Identity | Quyền cần có |
| --- | --- |
| Config reader | Chỉ đọc các prefix KV mà application cần |
| Discovery reader | Chỉ truy vấn catalog/service health cần thiết |
| Service registrar | Chỉ đăng ký, cập nhật và deregister service thuộc workload được phép |
| Consul operator | Quyền quản trị; không cấp cho ứng dụng thông thường |

Tách token config và discovery giúp thu hồi một quyền mà không nhất thiết làm hỏng luồng còn lại. Nếu một ứng dụng chỉ cần tra cứu service và không tự đăng ký, identity của nó không nên có quyền ghi catalog.

Consul property appendix công bố spring.cloud.consul.config.acl-token và spring.cloud.consul.discovery.acl-token. Hãy kiểm tra property metadata theo đúng phiên bản Spring Cloud Consul của ứng dụng, vì tên và cách bind property có thể thay đổi giữa release.

### 8.1. Tránh đưa token vào service metadata

Service registry metadata nên chứa thông tin định tuyến hoặc capability không nhạy cảm như zone, version, protocol hay tags. Không đưa ACL token, password, private key hoặc bearer token vào metadata để các consumer khác đọc được.

Consul ACL kiểm soát quyền đọc/ghi registry. Nếu metadata bị lộ, token nằm trong đó có thể bị sao chép và sử dụng ngoài workload ban đầu. Hãy giữ token trong secret manager và chỉ inject vào client được cấp quyền.

## 9. Xác thực Eureka bằng Basic Auth hoặc mTLS

Spring Cloud Netflix Eureka Client hỗ trợ HTTP Basic khi URL eureka.client.serviceUrl.defaultZone có userinfo. Ví dụ về hình dạng cấu hình:

```yaml
eureka:
  client:
    serviceUrl:
      defaultZone: https://${EUREKA_USERNAME}:${EUREKA_PASSWORD}@eureka.internal.example/eureka/
```

Các giá trị username/password phải được inject từ secret source. Eureka yêu cầu URL dạng này cho Basic Auth trong built-in client integration; vì vậy cần kiểm soát log, registry metadata, exception và Actuator output để URL không bị ghi ra ngoài.

Với nhu cầu xác thực phức tạp hơn, Spring Cloud Netflix cho phép cấu hình DiscoveryClientOptionalArgs và ClientFilter. Khi Eureka yêu cầu client certificate, cấu hình TLS có thể dùng key store và trust store:

```yaml
eureka:
  client:
    tls:
      enabled: true
      key-store: /run/secrets/eureka-client.p12
      key-store-type: PKCS12
      key-store-password: ${EUREKA_KEYSTORE_PASSWORD}
      key-password: ${EUREKA_KEY_PASSWORD}
      trust-store: /run/secrets/eureka-truststore.p12
      trust-store-type: PKCS12
      trust-store-password: ${EUREKA_TRUSTSTORE_PASSWORD}
```

Eureka có giới hạn: không hỗ trợ bộ Basic Auth credential riêng cho từng server URL; chỉ bộ credential đầu tiên được tìm thấy được sử dụng. Nếu kết nối tới nhiều Eureka server có identity khác nhau, không giả định rằng mỗi URL sẽ tự có một credential độc lập.

### 9.1. Discovery-first Config Server và credential trong metadata

Khi Config Client dùng discovery để tìm Config Server, Config Server có thể đăng ký user, password và configPath trong Eureka metadata để client biết cách truy cập endpoint được bảo vệ.

Cơ chế này tiện lợi nhưng biến registry thành nơi lưu thông tin xác thực. Bất kỳ client nào có quyền đọc metadata có thể có cơ hội đọc credential. Nếu buộc phải dùng:

- Giới hạn quyền đọc registry cho đúng workload.
- Dùng credential chỉ đọc cấu hình, không dùng tài khoản quản trị.
- Bảo vệ kênh truy cập registry bằng TLS/mTLS.
- Không ghi metadata map hoặc discovery response ra log.
- Xoay vòng credential và xác minh metadata cũ được thay thế.
- Cân nhắc dùng cơ chế auth khác không cần phân phối password qua metadata nếu integration/version hỗ trợ.

Không dùng service metadata như một secret store tổng quát.

## 10. Dùng Vault để cấp credential cho workload

Spring Cloud Vault có thể lấy secrets và cung cấp authentication cho ứng dụng. Các lựa chọn machine authentication thường phù hợp hơn việc nhúng một Vault root token tĩnh vào application.yml.

### 10.1. Kubernetes authentication

Khi ứng dụng chạy trong Kubernetes, Vault có thể xác thực bằng Service Account Token được mount trong pod. Cấu hình Spring Cloud Vault:

```yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: https://vault.internal.example
      authentication: KUBERNETES
      kubernetes:
        role: inventory-config-reader
```

Vault role nên gắn với Kubernetes service account và namespace cụ thể. Policy chỉ cho phép đọc secret path mà workload cần. Không dùng một Kubernetes service account chung cho mọi microservice nếu các service có quyền đọc secret khác nhau.

### 10.2. AppRole

AppRole dành cho machine authentication. Nó dùng Role ID và Secret ID; Secret ID cần được bảo vệ như một credential. Nếu dùng AppRole, cấp Secret ID theo cách có giới hạn TTL/usage, cân nhắc response wrapping và không ghi nó vào source control.

Ví dụ cấu hình tối thiểu về hình dạng:

```yaml
spring:
  cloud:
    vault:
      authentication: APPROLE
      app-role:
        role-id: ${VAULT_ROLE_ID}
        secret-id: ${VAULT_SECRET_ID}
```

Nếu có thể dùng Vault Agent Auto-Auth hoặc workload identity, hãy đánh giá lựa chọn đó để ứng dụng không phải quản lý static token dài hạn. Vault token cần TTL, renewal và revoke policy rõ ràng.

### 10.3. Phân biệt Vault token của Config Server và Config Client

Nếu Config Server dùng Vault làm backend, credential để Config Server truy cập Vault thuộc về Config Server. Config Client chỉ cần credential để gọi Config Server. Không gửi Vault root token hoặc token backend của Config Server tới từng microservice.

Credential để Config Server truy cập Vault phải được cấu hình ở chính môi trường chạy Config Server theo cơ chế authentication của backend Vault. Giữ credential backend tại server side và giới hạn policy của nó vào đúng secret path mà Config Server cần đọc.

## 11. Phân quyền theo nguyên tắc least privilege

Một credential tốt chỉ có quyền tối thiểu để workload hoàn thành nhiệm vụ.

| Thành phần | Quyền nên cấp | Quyền nên tránh |
| --- | --- | --- |
| Config Client của inventory-service | Đọc config path/profile của chính inventory | Đọc secret của mọi application |
| Consul discovery reader | Đọc catalog/service health cần thiết | Ghi policy, tạo token, quản trị agent |
| Consul service registrar | Register/deregister service của chính workload | Quản trị toàn bộ catalog |
| Eureka client | Đăng ký và truy vấn registry theo policy của server | Dùng tài khoản quản trị Eureka |
| Config Server | Đọc repository/config backend được cấu hình | Dùng Git/Vault admin credential không giới hạn |
| Vault workload role | Đọc các secret path được cấp cho service | Đọc toàn bộ secret engine hoặc revoke token của workload khác |

Tách identity theo service và theo môi trường. inventory-service-dev không nên dùng cùng credential với inventory-service-prod. Tài khoản của developer, CI pipeline, Config Server và runtime workload cũng nên khác nhau.

Khi một service bị xâm nhập, blast radius của credential bị lộ cần giới hạn trong dữ liệu và thao tác mà service đó thực sự cần.

## 12. Xử lý credential khi khởi động và refresh cấu hình

Spring Boot Config Data nạp cấu hình trong giai đoạn sớm của startup. Credential để gọi Config Server, Consul Config hoặc Vault phải có sẵn từ nguồn local/bootstrap trước khi remote property source được tải.

Không đặt duy nhất spring.cloud.config.password trong repository cấu hình do chính Config Server phục vụ. Ứng dụng chưa thể đăng nhập để lấy giá trị đó.

Với cấu hình có thể refresh:

- Không giả định mọi credential đều tự refresh chỉ vì một EnvironmentChangeEvent được phát ra.
- Kiểm tra integration có hỗ trợ cập nhật token, renew session hoặc rebuild HTTP client hay không.
- Nếu credential đã bị revoke, cần xác minh client cũ có bị loại bỏ và connection mới dùng credential mới.
- Đối với certificate/key store, cần có quy trình reload hoặc restart có kiểm soát tùy khả năng của HTTP client.
- Tránh refresh đồng thời hàng loạt workload nếu việc đó tạo spike request tới Config Server, Vault hoặc registry.

Với credential dùng cho bootstrap, rotation có thể cần rollout ứng dụng hoặc một bootstrap client có khả năng cập nhật credentials. Hãy kiểm thử toàn bộ vòng đời thay vì chỉ đổi giá trị trong secret store.

## 13. Không để credential rò rỉ qua log, trace hoặc Actuator

Một secret có thể không nằm trong file cấu hình nhưng vẫn lộ qua log và telemetry.

Các nguồn rò rỉ thường gặp:

- URI có userinfo, ví dụ https://user:password@host.
- HTTP Authorization header hoặc Consul ACL token header.
- Dump toàn bộ Environment, ConfigurationProperties hoặc object cấu hình.
- HTTP client wire logging, debug logging của thư viện registry/config client.
- Exception chứa request URI, header hoặc response body.
- Eureka metadata map chứa user và password.
- Actuator env, configprops, beans hoặc custom diagnostic endpoint.
- Trace/span attribute được thêm tự động từ URL hoặc request header.

Quy tắc vận hành:

1. Không log password, token, private key, certificate private material hoặc Authorization header.
2. Redact userinfo khỏi URL trước khi ghi log.
3. Không bật wire-level logging trong production nếu chưa có bộ lọc che secret đã được kiểm chứng.
4. Giới hạn quyền truy cập và network exposure của Actuator management endpoints.
5. Không gửi secret vào metric label hoặc trace tag; các giá trị này thường được lưu lâu và có thể được nhiều nhóm truy cập.
6. Khi debug, ghi status code, host, correlation ID và loại lỗi; không ghi request header hoặc secret.
7. Đặt retention và quyền truy cập log/trace theo mức nhạy cảm của hệ thống.

Actuator env và configprops có thể giúp chẩn đoán property binding, nhưng không nên mở rộng rãi. Dù framework có cơ chế sanitization, vẫn cần xác nhận cấu hình hiển thị giá trị và giới hạn quyền truy cập management endpoint.

## 14. Timeout, retry và fail-fast khi xác thực thất bại

Authentication failure khác với network outage:

- 401 Unauthorized thường cho biết thiếu hoặc sai credential.
- 403 Forbidden thường cho biết principal đã xác thực nhưng không có quyền.
- Timeout hoặc connection refused có thể là sự cố mạng/server.
- TLS handshake/certificate error có thể là lỗi trust chain, hostname hoặc client certificate.

Không retry vô hạn với credential sai. Retry liên tục có thể tạo tải không cần thiết và làm khó phát hiện sự cố. Với Config Client, chọn fail-fast khi remote config là bắt buộc; dùng retry/backoff hữu hạn cho lỗi tạm thời phù hợp.

Nếu cấu hình từ Config Server là bắt buộc để ứng dụng chạy đúng, không dùng optional:configserver: để che lỗi xác thực hoặc kết nối. Nếu remote config thật sự optional, hãy xác định rõ cấu hình mặc định đủ an toàn và ghi nhận cảnh báo khi remote source không được nạp.

Không coi 401 từ một Config Server là lý do để thử gửi cùng credential tới mọi URL khác. Khi có nhiều Config Server, mỗi endpoint phải thuộc cùng trust boundary hoặc có credential policy riêng được thiết kế rõ.

## 15. Kiểm thử bảo mật credential

Kiểm thử không chỉ xác nhận request thành công. Cần xác minh credential sai bị từ chối và không xuất hiện trong output.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Config Server nhận đúng Basic credential qua HTTPS | Config Client lấy được property source |
| Config Server nhận password sai | Request bị từ chối; startup fail nếu remote config bắt buộc |
| Principal inventory yêu cầu config payment | Server trả 403 hoặc từ chối theo policy |
| Consul Config token chỉ có quyền đọc prefix được cấp | Đọc prefix được phép thành công; prefix khác bị từ chối |
| Discovery token chỉ có quyền đọc catalog | Lookup hoạt động; thao tác đăng ký bị từ chối |
| Eureka client thiếu client certificate khi mTLS bắt buộc | TLS handshake thất bại |
| Secret file không được mount | Startup fail nếu configtree là nguồn bắt buộc |
| Credential được xoay vòng | Request mới dùng credential mới; credential cũ bị revoke theo kế hoạch |
| Bật debug log trong test | Không có password, token hoặc Authorization header trong log |
| Actuator diagnostic endpoint bị gọi bởi user không có quyền | Request bị từ chối |

Dùng mock server hoặc test container để kiểm tra status code và request headers. Secret trong test phải là giá trị giả lập; không sao chép credential production vào test fixture, CI variable dùng chung hoặc snapshot log.

## 16. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Config Client nhận 401 | Username/password sai, token hết hạn hoặc request thiếu Authorization header | Kiểm tra secret source và loại auth; không in giá trị credential |
| Config Client nhận 403 | Principal không có quyền đọc application/profile/label | Kiểm tra server authorization policy và mapping principal |
| Config Client không nhận được property từ server | Config import không được khai báo, server unavailable hoặc import bị optional | Kiểm tra spring.config.import, startup log đã redacted và fail-fast policy |
| Secret property là null | Config tree chưa mount, tên file sai hoặc import path sai | Kiểm tra file name/path và quyền đọc volume |
| Consul KV đọc được nhưng discovery lỗi | Token config và discovery khác nhau hoặc ACL policy thiếu quyền catalog | Kiểm tra hai ACL token/property riêng |
| Eureka trả 401 dù URL đúng | Credential bị encode sai, URL bị parse hoặc client đang dùng credential khác | Kiểm tra defaultZone, secret binding và URL redaction |
| Eureka mTLS handshake lỗi | Client key store, trust store, password hoặc certificate chain không đúng | Kiểm tra certificate validity, SAN, CA và keystore format |
| Credential bị lộ trong log | URL userinfo, header hoặc wire logging chưa được redact | Tắt logging nhạy cảm, thêm redaction và rotate secret đã lộ |
| Config Server trả config của service khác | Authorization chỉ xác thực nhưng không giới hạn {application} | Thêm per-application authorization policy |
| Đổi secret store nhưng client vẫn dùng token cũ | Client/session/connection không tự reload credential | Kiểm tra token renewal, client lifecycle và quy trình rollout |

## 17. Quy trình triển khai an toàn

1. Liệt kê các luồng kết nối: Config Server, registry, Config backend và Vault.
2. Gán identity riêng cho từng application và từng môi trường.
3. Cấp quyền read/register theo đúng chức năng, tách Config ACL và Discovery ACL.
4. Chọn cơ chế machine authentication phù hợp: Basic qua TLS, OAuth2, mTLS, Consul ACL hoặc Vault workload identity.
5. Đưa secret ra khỏi source code, image và build artifact.
6. Mount secret bằng configuration tree hoặc dùng secret manager/runtime identity.
7. Nạp bootstrap credential trước Config Data import.
8. Bật TLS và xác minh certificate; không tắt kiểm tra certificate để né lỗi.
9. Bảo vệ Config Server theo application path và giới hạn quyền đọc registry metadata.
10. Redact URL, header và property nhạy cảm khỏi log/trace/Actuator.
11. Kiểm thử 401, 403, TLS failure, missing secret, rotation và revoke.
12. Theo dõi expiry và thiết lập quy trình xoay vòng trước khi credential hết hạn.
13. Thu hồi credential cũ sau khi xác nhận toàn bộ workload đã chuyển sang credential mới.

## 18. Câu hỏi tự kiểm tra

1. Vì sao credential dùng để gọi Config Server phải có sẵn trước khi Config Client nạp remote configuration?
2. Credential của Config Client khác credential mà Config Server dùng để truy cập Git hoặc Vault như thế nào?
3. Vì sao không nên lưu password trong URI hoặc application.yml được đóng gói vào image?
4. configtree: ánh xạ tên file và nội dung file thành property ra sao?
5. Khi nào nên bỏ prefix optional: khỏi spring.config.import?
6. Consul Config ACL token khác Discovery ACL token ở mục đích nào?
7. Eureka hỗ trợ Basic Auth và mTLS theo cách nào? Giới hạn per-server credential là gì?
8. Vì sao Config Client không tự lấy OAuth2 token nếu chỉ bật Resource Server ở Config Server?
9. Vì sao cần giới hạn Config Server theo {application} thay vì chỉ yêu cầu authentication?
10. Tại sao không nên đưa token hoặc password vào service registry metadata?
11. Cần kiểm thử những gì khi xoay vòng và thu hồi credential?

## 19. Tài liệu tham khảo chính thức

- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html) — HTTP Basic, OAuth header/custom client, TLS, Config Data import, discovery-first lookup và credential của Config Client.
- [Spring Cloud Config — Security](https://docs.spring.io/spring-cloud-config/reference/server/security.html) — HTTP Basic, OAuth2/JWT, per-application access control và TLS/HTTPS.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — environment variable, configuration tree, configtree: và property placeholder.
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html) — spring.cloud.consul.config.acl-token, spring.cloud.consul.discovery.acl-token và TLS properties.
- [Spring Cloud Netflix — Eureka Client Authentication](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html) — Basic authentication, DiscoveryClientOptionalArgs, client certificate và trust store.
- [Spring Cloud Vault — Authentication Methods](https://docs.spring.io/spring-cloud-vault/reference/authentication.html) — Token, AppRole, Kubernetes và cloud workload authentication.
- [Spring Vault — Authentication](https://docs.spring.io/spring-vault/reference/vault/authentication.html) — token lifecycle, AppRole và Kubernetes authentication abstractions.

*Tài liệu tập trung vào credential của client khi gọi nguồn cấu hình và registry. Hãy cấp identity riêng cho từng workload, đưa secret vào runtime từ nguồn tin cậy, bảo vệ kênh TLS và kiểm thử cả việc từ chối, xoay vòng lẫn thu hồi credential.*
