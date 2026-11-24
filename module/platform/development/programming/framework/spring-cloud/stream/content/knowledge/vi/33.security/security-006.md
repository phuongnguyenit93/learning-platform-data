# Quản lý mật khẩu, khóa và chứng chỉ bằng cấu hình bên ngoài

Ứng dụng Spring Cloud Stream thường phải kết nối tới Kafka, RabbitMQ hoặc Pulsar bằng tài khoản dịch vụ, token, chứng chỉ TLS và khóa riêng. Những thông tin này thay đổi theo môi trường và có vòng đời riêng: mật khẩu có thể hết hạn, token có thể bị thu hồi, chứng chỉ có ngày hết hạn và khóa riêng cần được thay khi nghi ngờ bị lộ.

Không nên đóng gói các giá trị đó trong mã nguồn, file cấu hình nằm trong JAR hoặc Docker image. Spring Boot cho phép nạp cấu hình từ biến môi trường, file bên ngoài, volume mount và các hệ thống quản lý secret. Spring Cloud Stream chuyển các thuộc tính đó tới binder và client tương ứng. Bài học này trình bày cách tách cấu hình khỏi bí mật, đưa mật khẩu/khóa/chứng chỉ vào runtime, bảo vệ kết nối tới ba broker và tổ chức thay vòng thông tin xác thực mà không làm gián đoạn luồng sự kiện ngoài kế hoạch.

## 1. Phân biệt cấu hình thông thường và bí mật

Một ứng dụng cần nhiều loại thông tin để kết nối broker. Không phải mọi giá trị đều cần được bảo vệ như password, nhưng tất cả phải được quản lý đúng phạm vi.

| Loại dữ liệu | Ví dụ | Mức độ bảo vệ |
|---|---|---|
| Cấu hình kết nối | Host, port, topic, exchange, namespace | Thông thường; vẫn có thể là thông tin nội bộ |
| Tài khoản dịch vụ | Username, client ID, principal | Hạn chế truy cập theo môi trường |
| Mật khẩu và token | RabbitMQ password, SASL password, Pulsar token, Vault token | Bí mật; chỉ cấp cho workload cần dùng |
| Chứng chỉ công khai | CA certificate, client certificate, certificate chain | Không nhất thiết là bí mật, nhưng cần bảo vệ tính toàn vẹn và nguồn tin cậy |
| Khóa riêng | PEM private key, private key trong keystore | Bí mật có mức độ nhạy cảm cao |
| Mật khẩu keystore | Store password, key password | Bí mật; quản lý độc lập với file keystore |
| Truststore | Danh sách CA/certificate được tin cậy | Không nhất thiết là bí mật; thay đổi trust anchor có thể thay đổi miền tin cậy |

Một certificate thường chứa public key, danh tính và chữ ký của CA. Nó có thể được phân phối công khai. Private key tương ứng phải được giữ kín vì người sở hữu khóa có thể chứng minh danh tính hoặc giải mã dữ liệu tùy giao thức. Truststore chứa CA hoặc certificate mà client chấp nhận; keystore thường chứa certificate cùng private key của chính client hoặc server.

Cần phân biệt ba mục tiêu:

- **Authentication** xác minh ứng dụng hoặc người dùng là ai.
- **Authorization** quyết định danh tính đó được phép đọc topic, ghi exchange, tạo subscription hay quản lý tài nguyên nào.
- **Transport security** bảo vệ dữ liệu khi truyền qua mạng và xác minh endpoint qua TLS.

Có password đúng không đồng nghĩa ứng dụng đã được cấp quyền publish. TLS mã hóa kết nối cũng không thay thế ACL hoặc policy của broker.

## 2. Vì sao không lưu secret trong application.yml hoặc mã nguồn?

Ví dụ sau không phù hợp cho repository dùng chung:

~~~yaml
spring:
  rabbitmq:
    host: rabbit.internal
    username: order-service
    password: my-production-password
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            sasl.jaas.config: org.apache.kafka.common.security.plain.PlainLoginModule required username="app" password="my-secret";
~~~

Nếu commit file này, secret có thể xuất hiện trong Git history, bản build, cache CI, artifact registry, image layer, log hoặc bản sao lưu. Xóa dòng password ở commit sau không xóa được giá trị đã lưu trong lịch sử.

Các cách sau cũng không biến secret thành an toàn:

- Mã hóa password bằng Base64; Base64 chỉ là encoding.
- Đưa password vào hằng số Java hoặc biến static.
- Đổi tên file thành .secret nhưng vẫn commit vào Git.
- Đặt password trong Dockerfile bằng ARG/ENV rồi build image.
- Truyền password bằng command-line argument nếu có thể xuất hiện trong process list hoặc log.
- Dùng cùng một tài khoản và password cho development, staging và production.
- Ghi password, token, JAAS string hoặc private key vào log khi debug.

File cấu hình đóng gói trong ứng dụng nên chứa tên thuộc tính, địa chỉ tài nguyên và đường dẫn tới file certificate. Giá trị bí mật được cung cấp ở runtime từ secret store hoặc volume được cấp quyền.

## 3. Spring Boot nạp cấu hình bên ngoài như thế nào?

Spring Boot xây dựng một Spring Environment từ nhiều PropertySource. Các nguồn phổ biến gồm:

- Giá trị mặc định do ứng dụng cung cấp.
- File application.properties hoặc application.yml trong classpath.
- File cấu hình bên ngoài JAR.
- Biến môi trường của tiến trình.
- Java system properties.
- JSON cấu hình qua SPRING_APPLICATION_JSON.
- Tham số dòng lệnh.
- Cấu hình được import từ file, config tree hoặc hệ thống ngoài như Vault.

Các nguồn có thứ tự ưu tiên. Nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị ở nguồn thấp hơn. Điều này cho phép cùng một artifact chạy ở nhiều môi trường, nhưng cũng có thể khiến giá trị secret bị ghi đè ngoài ý muốn.

Ví dụ file trong JAR có thể đặt địa chỉ broker mặc định cho local development. Khi deploy, biến môi trường hoặc cấu hình ngoài cung cấp endpoint production. Với secret, nên kiểm soát chặt nguồn được phép ghi đè và không dùng tham số dòng lệnh làm kênh phân phối password.

Có thể cấu hình đường dẫn file bên ngoài bằng SPRING_CONFIG_ADDITIONAL_LOCATION hoặc khai báo spring.config.import. Nếu dùng spring.config.location, cần nhớ thuộc tính này thay thế các vị trí tìm cấu hình mặc định; spring.config.additional-location bổ sung vị trí mới mà vẫn giữ các vị trí mặc định.

Không nên đặt giá trị production trong profile mặc định. Profile chỉ chọn tập cấu hình; nó không phải secret manager. Secret vẫn phải đến từ nguồn được bảo vệ.

## 4. Dùng config tree để đọc secret từ file được mount

Một cách phù hợp cho container là mount mỗi secret thành một file riêng. Spring Boot hỗ trợ prefix **configtree:** để chuyển tên file thành tên property và nội dung file thành giá trị property.

Ví dụ runtime mount thư mục:

~~~text
/run/secrets/
  spring.rabbitmq.username
  spring.rabbitmq.password
  spring.cloud.stream.kafka.binder.configuration.sasl.jaas.config
  spring.cloud.stream.kafka.binder.configuration.ssl.truststore.password
  spring.pulsar.client.authentication.param.token
~~~

File có tên **spring.rabbitmq.password** tạo property cùng tên; nội dung file là password. Tương tự, file có tên **spring.pulsar.client.authentication.param.token** tạo property token cho Pulsar client.

Khai báo import trong application.yml:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  application:
    name: order-stream
~~~

Các file trong thư mục được đưa vào Spring Environment. Có thể truy cập chúng như các property thông thường bằng @Value, Environment hoặc @ConfigurationProperties. Config tree hỗ trợ giá trị String và byte[] tùy nội dung mong đợi.

Tên thư mục và file bên dưới config tree tạo thành property name. Có thể dùng tên file chứa dấu chấm để biểu diễn property phân cấp. Nếu một secret cần thiết cho kết nối production bị thiếu, nên để ứng dụng fail khi khởi động thay vì âm thầm dùng tài khoản mặc định. Chỉ thêm prefix optional: khi việc thiếu thư mục đó thực sự được chấp nhận.

### Cấu hình không bí mật và secret file

File application.yml có thể chứa các thuộc tính không nhạy cảm:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  cloud:
    stream:
      kafka:
        binder:
          brokers: kafka.prod.internal:9093
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            ssl.truststore.location: /run/messaging-certs/kafka-truststore.p12
            ssl.truststore.type: PKCS12
  rabbitmq:
    addresses: amqps://rabbit.prod.internal:5671
    ssl:
      enabled: true
      trust-store: /run/messaging-certs/rabbit-truststore.p12
      trust-store-type: PKCS12
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.prod.internal:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
~~~

Secret file trong /run/secrets cung cấp password, JAAS config và token. Certificate/keystore được mount read-only ở /run/messaging-certs. Đường dẫn file có thể nằm trong application.yml vì đường dẫn không phải private key hay password; nội dung file nhạy cảm vẫn được quản lý riêng.

Khi mount file, nên giới hạn quyền đọc cho user chạy ứng dụng. Không mount toàn bộ thư mục secret vào mọi container trong Pod nếu container đó không cần truy cập. Nếu nền tảng hỗ trợ volume read-only, hãy dùng chế độ đó cho certificate và secret file.

## 5. Biến môi trường và giới hạn khi dùng cho secret

Biến môi trường là cách phổ biến để đưa cấu hình vào container. Ví dụ:

~~~text
SPRING_RABBITMQ_USERNAME=order-service
SPRING_RABBITMQ_PASSWORD=<secret-from-platform>
SPRING_CLOUD_STREAM_KAFKA_BINDER_BROKERS=kafka.prod.internal:9093
~~~

Spring Boot chuyển tên biến môi trường sang dạng property. Cách này phù hợp với nhiều cấu hình và một số secret đơn giản. Tuy nhiên, biến môi trường có thể xuất hiện trong thông tin chẩn đoán tiến trình, cấu hình container, dump hoặc công cụ quản trị có quyền đọc môi trường. Hãy đánh giá threat model của nền tảng trước khi dùng nó cho private key hoặc token có quyền rộng.

Tên biến môi trường không giữ nguyên mọi dấu chấm, dấu gạch ngang và chữ hoa/thường trong tên property. Với một số thuộc tính có tên nhạy cảm về chữ hoa/thường, cần giữ tên property chính xác trong YAML rồi tham chiếu biến môi trường làm giá trị.

Ví dụ Pulsar OAuth2 yêu cầu tên parameter chính xác là **issuerUrl**:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Với config tree, mount secret thành file có tên chính xác **spring.pulsar.client.authentication.param.issuerUrl** và nội dung là issuer URL. Nếu dùng biến môi trường, hãy giữ property camel-case trong YAML rồi tham chiếu biến môi trường làm giá trị; không để Spring Boot tự suy ra issuerUrl từ một biến môi trường đã bị chuyển thành issuerurl. Tài liệu Spring Pulsar yêu cầu tên dưới authentication.param khớp chính xác với tên plugin quy định.

Không truyền password qua command line nếu có lựa chọn khác. Command line thường có thể được đọc từ process metadata hoặc log của hệ thống triển khai. Ưu tiên secret manager, config tree hoặc cơ chế workload identity.

## 6. Dùng Kubernetes Secret và Docker Secret

Kubernetes có thể mount Secret vào Pod dưới dạng volume hoặc đưa vào environment variable. Với volume mount, mỗi key của Secret trở thành một file. Kết hợp với configtree, ứng dụng có thể đọc các file đó như property.

Ví dụ manifest minh họa cấu trúc, không chứa giá trị secret:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-stream
spec:
  containers:
    - name: app
      image: registry.example/order-stream:1.0
      volumeMounts:
        - name: messaging-secrets
          mountPath: /run/secrets
          readOnly: true
        - name: messaging-certs
          mountPath: /run/messaging-certs
          readOnly: true
  volumes:
    - name: messaging-secrets
      secret:
        secretName: order-stream-messaging
    - name: messaging-certs
      secret:
        secretName: order-stream-certificates
~~~

Khi volume được mount, application.yml import config tree tại /run/secrets. Các file certificate/keystore được đọc theo đường dẫn đã khai báo. Không đưa nội dung Secret vào manifest công khai, Git hoặc image.

Kubernetes Secret object không tự động đồng nghĩa dữ liệu được mã hóa an toàn ở mọi lớp. Base64 trong manifest chỉ là biểu diễn. Cần cấu hình encryption at rest cho datastore của cluster, RBAC giới hạn ai được đọc Secret, audit access và giới hạn Pod/service account nào được mount secret. Với yêu cầu cao hơn, có thể dùng external secret store hoặc Secrets Store CSI Driver để lấy secret từ hệ thống quản lý chuyên dụng.

Docker Swarm Secret cũng có thể được mount thành file trong container. Spring Boot configtree có thể đọc thư mục đó theo cùng cách. Dù dùng nền tảng nào, cần kiểm tra quyền đọc, vòng đời file và cách cập nhật secret khi thay phiên bản.

## 7. Dùng Spring Cloud Vault làm nguồn cấu hình bí mật

HashiCorp Vault có thể lưu password, token, certificate metadata hoặc tạo credential có thời hạn. Spring Cloud Vault tích hợp với Spring Boot ConfigData API, đưa dữ liệu Vault vào Spring Environment như một PropertySource.

Thêm dependency Spring Cloud Vault Config phù hợp với release train của ứng dụng. Ví dụ cấu hình:

~~~yaml
spring:
  application:
    name: order-stream
  config:
    import: "vault://"
  cloud:
    vault:
      uri: https://vault.internal:8200
      authentication: KUBERNETES
      kubernetes:
        role: order-stream
~~~

Trong môi trường Kubernetes, ứng dụng có thể xác thực với Vault bằng Kubernetes service account identity. Không đặt root token hoặc token có quyền quản trị trong application.yml. Chính sách Vault nên chỉ cho workload đọc đúng path và key mà nó cần.

Theo cấu hình mặc định, Spring Cloud Vault có thể mount KV path dựa trên tên ứng dụng, ví dụ secret/order-stream, và thêm context theo profile đang kích hoạt. Có thể khai báo contextual location nếu muốn chỉ đọc một path cụ thể:

~~~yaml
spring:
  config:
    import: "vault:///secret/messaging/order-stream"
~~~

Các key trong Vault có thể đặt theo tên property Spring, ví dụ:

~~~text
spring.rabbitmq.username
spring.rabbitmq.password
spring.cloud.stream.kafka.binder.configuration.sasl.jaas.config
spring.pulsar.client.authentication.param.token
~~~

Khi Vault đã nạp các key đó vào Environment, binder và Spring Boot auto-configuration đọc chúng như các property khác. Thứ tự property source vẫn quan trọng: không để một giá trị trong application profile hoặc biến môi trường ghi đè secret từ Vault ngoài chủ đích.

Spring Cloud Vault hỗ trợ nhiều kiểu xác thực và secret backend. Với dynamic secret có lease, Spring Cloud Vault quản lý lifecycle như renewal, rotation khi lease hết hạn và revocation khi ứng dụng shutdown theo cơ chế backend hỗ trợ. Static token không được tự gia hạn hoặc thu hồi theo lease như credential động.

**Nạp secret mới vào Environment không tự bảo đảm binder client hiện có được tạo lại.** Kafka producer/consumer, Rabbit connection factory và Pulsar client thường được khởi tạo từ cấu hình tại thời điểm tạo. Khi password, token hoặc certificate thay đổi, phải có kế hoạch để client reconnect hoặc được tạo lại bằng cấu hình mới. Kiểm thử chính xác hành vi của phiên bản binder và cơ chế refresh đang dùng; không giả định mọi client tự động đọc lại Environment.

## 8. Quản lý Kafka username, password và SASL

Kafka Binder nhận các thuộc tính bảo mật chung qua **spring.cloud.stream.kafka.binder.configuration**. Đây là map thuộc tính client được truyền cho producer và consumer do binder tạo. Vì được dùng chung, thích hợp đặt các thuộc tính như security.protocol, SASL mechanism và TLS trust material. Nếu có nhiều Kafka cluster, mỗi named binder có thể có cấu hình xác thực riêng.

Ví dụ SASL/SCRAM qua TLS:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: kafka.prod.internal:9093
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: <LOAD_FROM_SECRET_PROPERTY>
            ssl.truststore.location: /run/messaging-certs/kafka-truststore.p12
            ssl.truststore.type: PKCS12
            ssl.truststore.password: <LOAD_FROM_SECRET_PROPERTY>
~~~

Trong môi trường thực tế, sasl.jaas.config và ssl.truststore.password phải đến từ secret store hoặc file được mount. Ví dụ JAAS value có thể được tạo theo dạng:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required username="order-stream" password="<secret>";
~~~

Không ghi value này vào Git. Kafka client hỗ trợ các cơ chế SASL như PLAIN, SCRAM và GSSAPI tùy broker/client. Chọn cơ chế theo cấu hình broker và chính sách tổ chức. Với SASL_SSL, SASL xác thực client và TLS mã hóa/kiểm tra broker certificate.

Nếu dùng Kerberos, Spring Cloud Stream có thể đọc JAAS configuration file qua system property java.security.auth.login.config hoặc dùng các thuộc tính Spring Boot dưới kafka.binder.jaas. Không trộn JAAS file với cơ chế Spring Boot JAAS properties trong cùng ứng dụng; tài liệu binder nêu rằng khi system property java.security.auth.login.config tồn tại, cấu hình JAAS bằng Spring Boot bị bỏ qua.

### TLS một chiều và mutual TLS

Với TLS một chiều, client cần tin cậy CA ký certificate của broker. Kafka client có thể dùng truststore:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            security.protocol: SSL
            ssl.truststore.location: /run/messaging-certs/kafka-truststore.p12
            ssl.truststore.type: PKCS12
            ssl.truststore.password: <LOAD_FROM_SECRET_PROPERTY>
~~~

Với mutual TLS, broker cũng yêu cầu certificate client. Khi đó cấu hình thêm keystore chứa client certificate và private key:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            security.protocol: SSL
            ssl.truststore.location: /run/messaging-certs/kafka-truststore.p12
            ssl.truststore.type: PKCS12
            ssl.truststore.password: <LOAD_FROM_SECRET_PROPERTY>
            ssl.keystore.location: /run/messaging-certs/kafka-client.p12
            ssl.keystore.type: PKCS12
            ssl.keystore.password: <LOAD_FROM_SECRET_PROPERTY>
            ssl.key.password: <LOAD_FROM_SECRET_PROPERTY>
~~~

Truststore chứa CA/certificate mà client tin cậy. Keystore chứa certificate và private key client. Mật khẩu keystore và key password có thể khác nhau; không giả định một password bảo vệ tất cả material. Kafka hỗ trợ PEM ở các phiên bản client hiện đại với các giới hạn định dạng cụ thể; kiểm tra phiên bản kafka-clients và định dạng key/certificate trước khi chuyển từ PKCS12/JKS sang PEM.

Nếu Kafka app có nhiều binder instance kết nối các cluster khác nhau, hãy đặt JAAS config và trust material đúng phạm vi binder. Cấu hình SASL JAAS riêng có thể được đặt bằng sasl.jaas.config cho từng cluster; không dùng chung credential nếu hai cluster có danh tính và policy khác nhau.

Trong môi trường bảo mật, topic, partition và ACL thường được provision bởi đội hạ tầng. Không cấp quyền admin cho consumer chỉ để binder tự tạo topic. Cấp quyền tối thiểu theo nhu cầu read/write và group.

## 9. Quản lý RabbitMQ username, password và TLS

RabbitMQ Binder mặc định sử dụng Spring Boot ConnectionFactory. Vì vậy, các thuộc tính kết nối và SSL thường dùng prefix **spring.rabbitmq**. Đây là điểm khác Kafka: ứng dụng không cần tự tạo connection factory riêng cho binder trong trường hợp thông thường.

Ví dụ:

~~~yaml
spring:
  rabbitmq:
    host: rabbit.prod.internal
    port: 5671
    username: <LOAD_FROM_SECRET_PROPERTY>
    password: <LOAD_FROM_SECRET_PROPERTY>
    virtual-host: /orders
    ssl:
      enabled: true
      trust-store: /run/messaging-certs/rabbit-truststore.p12
      trust-store-type: PKCS12
      trust-store-password: <LOAD_FROM_SECRET_PROPERTY>
      validate-server-certificate: true
      verify-hostname: true
~~~

Nếu broker yêu cầu mutual TLS, bổ sung client keystore:

~~~yaml
spring:
  rabbitmq:
    ssl:
      key-store: /run/messaging-certs/rabbit-client.p12
      key-store-type: PKCS12
      key-store-password: <LOAD_FROM_SECRET_PROPERTY>
      trust-store: /run/messaging-certs/rabbit-truststore.p12
      trust-store-type: PKCS12
      trust-store-password: <LOAD_FROM_SECRET_PROPERTY>
~~~

Các placeholder trong ví dụ biểu thị property được cấp từ secret store hoặc config tree. Không lưu giá trị thật vào YAML. Spring Boot hỗ trợ SSL bundle cho một số kết nối được auto-configure; có thể dùng bundle nếu phiên bản Spring Boot và Spring AMQP đang dùng hỗ trợ đúng loại kết nối. Khi dùng cấu hình trực tiếp của RabbitMQ, kiểm tra các thuộc tính SSL của Spring Boot tương ứng với release train.

Không tắt certificate validation hoặc hostname verification để “sửa nhanh” lỗi TLS. Khi handshake thất bại, kiểm tra CA chain, SAN của certificate, hostname broker, thời gian hệ thống, loại keystore và password. Tắt xác minh hostname có thể khiến client chấp nhận endpoint giả mạo dù dữ liệu đã được mã hóa.

RabbitMQ username/password xác định principal. Quyền trên virtual host, exchange và queue vẫn được broker kiểm soát bằng permission. Dùng user riêng cho từng ứng dụng và cấp quyền configure/write/read tối thiểu. Không dùng guest/guest trong môi trường production.

## 10. Quản lý token, chứng chỉ và khóa của Pulsar

Pulsar Spring Boot Starter tự cấu hình PulsarClient. Pulsar Binder sử dụng các thành phần của Spring for Apache Pulsar, vì vậy các thuộc tính Spring Boot dưới **spring.pulsar.client** có thể được dùng cho binder.

Ví dụ token authentication:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.prod.internal:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: <LOAD_FROM_SECRET_PROPERTY>
~~~

Token cần được lấy từ secret store. Với OAuth2, tên parameter như issuerUrl phải giữ đúng chữ hoa/thường theo plugin. Không đưa private key OAuth2 vào file cấu hình đã commit; dùng file mount hoặc secret provider theo cơ chế plugin hỗ trợ.

### TLS với PEM và customizer

Spring Boot auto-configuration hiện chưa cung cấp toàn bộ thuộc tính TLS cho Pulsar client theo cách giống Kafka hoặc RabbitMQ. Có thể dùng **PulsarClientBuilderCustomizer** để cấu hình TLS trên client builder. Pulsar hỗ trợ PEM và JKS.

Ví dụ mutual TLS với PEM files được mount:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.pulsar.core.PulsarClientBuilderCustomizer;

@Configuration
public class PulsarTlsConfiguration {

    @Bean
    PulsarClientBuilderCustomizer pulsarClientTlsCustomizer() {
        return builder -> {
            builder.allowTlsInsecureConnection(false);
            builder.enableTlsHostnameVerification(true);
            builder.tlsTrustCertsFilePath(
                "/run/messaging-certs/pulsar-ca.pem"
            );
            builder.tlsCertificateFilePath(
                "/run/messaging-certs/pulsar-client.crt"
            );
            builder.tlsKeyFilePath(
                "/run/messaging-certs/pulsar-client.key"
            );
        };
    }
}
~~~

Đường dẫn trong ví dụ trỏ tới file được mount bên ngoài container. Không đóng gói private key vào classpath hoặc JAR. Chỉ cấp quyền đọc cho user chạy ứng dụng. Nếu chỉ cần xác minh server certificate, có thể cấu hình trust CA và không cung cấp client certificate/private key; nếu broker yêu cầu mTLS, cần certificate/key của client.

Nếu binder dùng PulsarAdmin để provision topic, cần cấu hình TLS và authentication cho admin client tương ứng bằng **PulsarAdminBuilderCustomizer**. Chỉ cấu hình PulsarClientBuilderCustomizer có thể chưa đủ cho đường admin. Cả broker URL và admin URL phải dùng scheme/port TLS phù hợp, thường là pulsar+ssl:// cho client và https:// cho admin.

Không bật allowTlsInsecureConnection hoặc tắt hostname verification trong production. Các tùy chọn đó có thể hữu ích trong một test cục bộ với certificate tự ký, nhưng làm suy yếu xác minh danh tính broker.

## 11. Phân biệt truststore, keystore và certificate chain

Các tên gọi dễ bị nhầm lẫn:

| Thành phần | Chứa gì? | Dùng để làm gì? |
|---|---|---|
| CA certificate | Public certificate của CA | Xác minh certificate do CA đó ký |
| Server certificate | Public certificate của broker | Xác minh broker là endpoint dự kiến |
| Client certificate | Public certificate của ứng dụng | Trình bày danh tính ứng dụng trong mTLS |
| Private key | Khóa riêng tương ứng certificate | Chứng minh quyền sở hữu certificate |
| Truststore | CA/certificate mà client tin cậy | Xác minh server hoặc peer |
| Keystore | Private key và certificate của client/server | Cung cấp danh tính TLS |
| Certificate chain | Leaf certificate cùng intermediate CA | Cho peer xây dựng chuỗi tin cậy |

Truststore không phải nơi lưu password broker. Keystore không phải bản sao của truststore. Nếu client chỉ xác minh server, thường chỉ cần truststore. Nếu broker yêu cầu mutual TLS, client cần thêm keystore hoặc PEM certificate/private key.

Private key cần được bảo vệ chặt hơn certificate công khai. Không gửi private key qua email, ticket, chat hoặc log. Không dùng cùng một client key cho mọi môi trường. Nên cấp certificate riêng cho workload hoặc nhóm workload có cùng ranh giới tin cậy.

## 12. Tổ chức thư mục secret và certificate khi deploy

Có thể tách file secret dạng text và file key/certificate thành hai volume:

~~~text
/run/secrets/
  spring.rabbitmq.username
  spring.rabbitmq.password
  spring.cloud.stream.kafka.binder.configuration.sasl.jaas.config
  spring.cloud.stream.kafka.binder.configuration.ssl.truststore.password
  spring.pulsar.client.authentication.param.token

/run/messaging-certs/
  kafka-truststore.p12
  kafka-client.p12
  rabbit-truststore.p12
  rabbit-client.p12
  pulsar-ca.pem
  pulsar-client.crt
  pulsar-client.key
~~~

Spring config tree đọc nội dung file trong /run/secrets thành property. Binder đọc certificate/keystore từ đường dẫn trong /run/messaging-certs. Đây là hai cách phân phối khác nhau: config tree chuyển nội dung file thành giá trị property; file certificate cần được giữ nguyên như file để thư viện TLS đọc.

Khi deploy:

- Mount secret và certificate read-only.
- Giới hạn file permission và user/group được đọc.
- Không mount secret vào container sidecar không cần dùng.
- Không đưa secret vào image layer hoặc build arg.
- Dùng volume/secret manager có thể cập nhật phiên bản.
- Đặt tên secret theo ứng dụng, môi trường và broker cluster.
- Tách credential Kafka, RabbitMQ và Pulsar.
- Theo dõi ngày hết hạn certificate và thời hạn token.

Không cần đưa toàn bộ secret của cluster vào cùng một file cấu hình lớn. Một file riêng cho mỗi key giúp kiểm soát quyền, audit và thay phiên bản rõ hơn.

## 13. Quản lý nhiều binder và nhiều cluster

Một Spring Cloud Stream application có thể chứa Kafka, RabbitMQ và Pulsar binder cùng lúc. Cũng có thể kết nối hai Kafka cluster khác nhau bằng named binder. Mỗi cluster có thể yêu cầu username, password, JAAS config, CA và client certificate khác nhau.

Ví dụ named Kafka binders:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafkaOrders:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-orders.internal:9093
                      configuration:
                        security.protocol: SASL_SSL
                        sasl.mechanism: SCRAM-SHA-512
                        sasl.jaas.config: <ORDERS_CLUSTER_SECRET>
                        ssl.truststore.location: /run/certs/orders-trust.p12
                        ssl.truststore.password: <ORDERS_TRUST_SECRET>
        kafkaAudit:
          type: kafka
          default-candidate: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-audit.internal:9093
                      configuration:
                        security.protocol: SASL_SSL
                        sasl.mechanism: SCRAM-SHA-512
                        sasl.jaas.config: <AUDIT_CLUSTER_SECRET>
                        ssl.truststore.location: /run/certs/audit-trust.p12
                        ssl.truststore.password: <AUDIT_TRUST_SECRET>
~~~

Mỗi binder cần secret riêng được cấp cho đúng workload. Khi dùng explicit binder configuration, cần khai báo mọi binder mà ứng dụng sử dụng; không giả định binder mặc định sẽ được tự cấu hình như khi chỉ có một implementation trên classpath.

Không dùng một JAAS config chung cho nhiều cluster chỉ vì cơ chế SASL giống nhau. Principal, username/password, truststore và quyền truy cập có thể khác. Hãy kiểm tra đúng property source của từng binder instance, tránh trường hợp binder audit vô tình kế thừa credential của binder orders.

## 14. Quản lý secret bằng @ConfigurationProperties

Với cấu hình ứng dụng riêng, có thể gom thuộc tính vào một record hoặc class có @ConfigurationProperties. Cách này giúp kiểm tra cấu hình bắt buộc và giảm việc gọi Environment rải rác.

Ví dụ chỉ quản lý tên alias và đường dẫn file, còn password vẫn được nạp từ nguồn bên ngoài:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.messaging.tls")
public record MessagingTlsProperties(
    String kafkaTrustStore,
    String rabbitTrustStore,
    String pulsarCaCertificate
) {
}
~~~

Đăng ký bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties. Các giá trị này không nhất thiết là secret nếu chúng chỉ là path. Không tạo một class chứa mọi password rồi log toàn bộ object khi debug.

Nếu cần bind secret vào bean, giữ scope và vòng đời tối thiểu, không expose getter qua API không cần thiết, không đưa vào toString, record log hoặc exception message. Dữ liệu trong Spring Environment vẫn tồn tại trong memory của tiến trình; externalization giúp kiểm soát phân phối và vòng đời, không có nghĩa secret không còn trong memory.

## 15. Thay mật khẩu và token có kế hoạch

Thay secret cần phối hợp broker, secret store và ứng dụng. Nếu đổi password ngay trên broker trong khi mọi instance vẫn dùng password cũ, kết nối mới có thể thất bại. Nếu xóa user cũ trước khi mọi instance chuyển sang user mới, luồng có thể bị gián đoạn.

Một quy trình thay credential an toàn:

1. Tạo user hoặc credential mới trên broker với quyền tối thiểu cần thiết.
2. Kiểm tra quyền đọc/ghi topic, exchange, queue hoặc namespace.
3. Lưu credential mới vào secret manager dưới một version mới.
4. Cập nhật cấu hình triển khai để workload đọc version mới.
5. Khởi tạo lại hoặc reconnect client theo cơ chế đã kiểm thử.
6. Xác minh consumer group/subscription hoạt động và producer publish được.
7. Theo dõi lỗi authentication, reconnect, lag và DLQ.
8. Thu hồi credential cũ sau khi mọi instance đã chuyển thành công.

Với token có TTL, cần biết thời điểm hết hạn và cách cấp token mới. Không dùng token không hết hạn cho workload dài hạn nếu nền tảng hỗ trợ token ngắn hạn hoặc workload identity.

Không thay credential đồng thời ở nhiều broker mà không có khả năng rollback. Có thể triển khai từng broker hoặc từng nhóm instance để giới hạn ảnh hưởng.

## 16. Thay certificate và private key

Certificate TLS có ngày bắt đầu và ngày hết hạn. Một certificate hết hạn có thể khiến client không thiết lập được TLS connection dù username/password vẫn đúng.

Một quy trình thay CA/certificate thường gồm:

1. Cấp CA hoặc certificate mới và xác minh hostname/SAN, chain, thời hạn và key usage.
2. Cập nhật truststore của client để tin cậy cả CA cũ và CA mới trong giai đoạn chuyển tiếp nếu cần.
3. Cập nhật broker certificate hoặc client certificate theo kế hoạch.
4. Mount keystore/PEM file mới vào workload.
5. Tạo lại TLS client/connection theo cơ chế binder hỗ trợ.
6. Xác minh handshake và hostname verification.
7. Khi mọi client đã chuyển, loại CA cũ khỏi truststore.
8. Thu hồi certificate/key cũ theo policy.

Nếu thay server certificate nhưng client chưa tin CA mới, handshake sẽ thất bại. Nếu xóa CA cũ quá sớm, những broker hoặc instance chưa được cập nhật có thể mất kết nối. Giai đoạn overlap giúp chuyển đổi có kiểm soát.

Private key mới nên được tạo trong HSM hoặc hệ thống quản lý key nếu yêu cầu bảo mật cao. Không cần xuất private key ra file nếu thư viện và hạ tầng hỗ trợ sử dụng key từ HSM/PKCS#11. Nếu dùng file PEM/PKCS12, giới hạn quyền đọc và tránh tạo bản sao không cần thiết.

## 17. Secret rotation không đồng nghĩa tự động refresh binder

Spring Environment có thể nhận giá trị mới từ config tree hoặc Vault, nhưng một số thành phần chỉ đọc property lúc được tạo. Ví dụ:

- Kafka producer/consumer có thể đã được tạo từ cấu hình SSL/SASL ban đầu.
- Rabbit ConnectionFactory có thể đang giữ connection đã xác thực bằng password cũ.
- PulsarClient có thể đang giữ authentication object và TLS context được tạo từ file cũ.

Vì vậy, phải kiểm tra xem phiên bản framework/client có hỗ trợ reload material và reconnect hay không. Spring Boot SSL bundles có cơ chế reload khi file thay đổi, nhưng chỉ các consumer SSL tương thích với reloadable bundle mới tự áp dụng. Không giả định Kafka Binder, Rabbit connection factory hoặc Pulsar client tự động reload chỉ vì file đã được thay.

Nếu client không hỗ trợ reload an toàn, triển khai rolling restart hoặc recreate client/container theo cách framework hỗ trợ. Trong rolling restart, giữ đủ số instance/partition consumer để tránh mất năng lực xử lý. Với producer, xác minh publish error rate và confirm sau khi instance khởi động lại.

Với Vault dynamic credentials, lease renewal giúp secret còn hiệu lực; việc thay credential trong client vẫn cần được hỗ trợ hoặc kích hoạt bởi ứng dụng. Hãy thử nghiệm vòng đời thực tế: secret được đổi, connection cũ bị đóng, client mới xác thực bằng secret mới và message flow tiếp tục.

## 18. Kiểm tra certificate, key và cấu hình trước khi deploy

Các lỗi phổ biến có thể phát hiện trước khi rollout:

| Kiểm tra | Điều cần xác minh |
|---|---|
| Certificate validity | Not Before/Not After còn hiệu lực |
| Hostname/SAN | Tên broker khớp certificate |
| Certificate chain | Intermediate và root CA đầy đủ |
| Truststore | Có CA ký certificate broker |
| Keystore | Có private key cùng certificate phù hợp |
| Key password | Đúng với private key hoặc store |
| Store type | PKCS12/JKS/PEM phù hợp client |
| File permission | User chạy app đọc được, user khác không đọc được |
| Broker ACL | Principal có đúng quyền |
| Token/password TTL | Còn thời gian sống đủ cho rollout |
| Clock synchronization | Đồng hồ host/container đồng bộ để xác minh thời hạn certificate/token |

Có thể dùng keytool để xem metadata keystore:

~~~bash
keytool -list -v -keystore /run/messaging-certs/kafka-client.p12 -storetype PKCS12
~~~

Lệnh sẽ yêu cầu store password nếu cần. Không đưa password vào command line hoặc script đã commit. Với PEM, dùng công cụ OpenSSL để kiểm tra certificate, private key và chain; tránh in private key ra terminal log hoặc CI artifact.

Không chỉ kiểm tra file tồn tại. Certificate có thể tồn tại nhưng hết hạn, SAN không khớp, chain thiếu intermediate hoặc private key không khớp certificate.

## 19. Bảo vệ secret trong log, Actuator và chẩn đoán

Khi lỗi kết nối broker, log nên có thông tin đủ để chẩn đoán nhưng không chứa giá trị bí mật.

Có thể ghi:

- Broker host/port hoặc alias đã được cấu hình.
- Binder type và binding name.
- Loại lỗi authentication/TLS.
- Certificate subject/issuer và thời hạn nếu được phép.
- Secret version hoặc credential identifier không nhạy cảm.
- Thời điểm reconnect và số lần thử.

Không ghi:

- Password, token, JAAS string.
- Private key hoặc nội dung keystore.
- Authorization header.
- Toàn bộ Environment hoặc toàn bộ Kafka client properties.
- Stack trace chứa chuỗi cấu hình có bí mật.

Các endpoint Actuator như env và configprops có thể hiển thị cấu hình ứng dụng. Chỉ expose endpoint cần thiết, giới hạn truy cập quản trị và dùng chính sách sanitization của Spring Boot. Không mở endpoint chẩn đoán nhạy cảm ra mạng công cộng. Hãy kiểm tra log startup, debug log của client và log hệ thống triển khai trước khi đưa ứng dụng vào production.

## 20. Kiểm thử cấu hình bảo mật với broker thật

Test Binder có thể kiểm tra function và binding ở mức framework, nhưng không chứng minh SASL, TLS handshake, certificate chain hoặc ACL của broker. Cần integration test với broker cấu hình bảo mật hoặc môi trường staging gần production.

Các tình huống cần kiểm tra:

1. Credential hợp lệ: consumer kết nối và nhận message.
2. Password/token sai: ứng dụng báo lỗi xác thực và không tiếp tục dùng credential mặc định.
3. Principal thiếu quyền: đọc topic hoặc publish bị từ chối đúng như policy.
4. Certificate CA không tin cậy: TLS handshake thất bại.
5. Hostname không khớp SAN: client từ chối broker.
6. Client certificate sai hoặc hết hạn: mTLS thất bại.
7. Secret bị rotate: client reconnect bằng secret mới.
8. Certificate được thay: client dùng truststore/keystore mới sau cơ chế reload hoặc restart đã thiết kế.
9. Multi-binder: mỗi cluster dùng đúng credential và trust material riêng.
10. Broker restart: connection phục hồi mà không log secret.
11. Vault không khả dụng lúc khởi động: ứng dụng xử lý theo policy fail-fast hoặc optional đã chọn.
12. Secret bị thu hồi: ứng dụng phát hiện lỗi, cảnh báo và chuyển sang credential hợp lệ theo quy trình.

Test nên có cả negative case. Một test chỉ xác minh ứng dụng kết nối thành công với password đúng không chứng minh client đang từ chối certificate giả mạo hoặc credential hết hạn.

## 21. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Kafka báo SASL authentication failed | JAAS config, username/password hoặc mechanism không khớp | Kiểm tra sasl.mechanism, JAAS và credential version |
| Kafka SSL handshake failed | Truststore thiếu CA, certificate hết hạn hoặc protocol mismatch | Kiểm tra chain, thời hạn và TLS protocol |
| Kafka client không đọc được keystore | Sai path, permission hoặc store password | Kiểm tra file mount, type và secret property |
| RabbitMQ ACCESS_REFUSED | User không có permission trên virtual host/exchange/queue | Kiểm tra broker permissions và vhost |
| RabbitMQ SSL peer verification failed | CA hoặc hostname không hợp lệ | Kiểm tra truststore, SAN và hostname verification |
| Pulsar authentication failed | Sai plugin class hoặc token parameter | Kiểm tra authentication plugin và tên property chính xác |
| Pulsar TLS client không kết nối | Chưa cấu hình client builder/admin builder hoặc sai URL scheme | Dùng pulsar+ssl://, https:// và customizer tương ứng |
| Ứng dụng vẫn dùng password cũ | Client đã tạo trước khi secret được cập nhật | Recreate/reconnect client hoặc rolling restart |
| Vault trả về property cũ | Sai path, profile context hoặc property source precedence | Kiểm tra ConfigData import và secret version |
| Secret không được nạp từ configtree | Tên file sai hoặc import path không đúng | Kiểm tra dotted filename, mount path và file permission |
| Môi trường dùng nhầm credential | Property nguồn ưu tiên cao ghi đè secret mong muốn | Kiểm tra thứ tự PropertySource và biến môi trường |
| Test local pass nhưng production fail | Local dùng plaintext hoặc credential mặc định | Thêm integration test TLS/SASL/ACL tương đương |

## 22. Checklist production

- Không commit password, token, JAAS config, private key hoặc keystore password.
- Tách cấu hình thường khỏi secret.
- Chọn nguồn cung cấp secret: Kubernetes Secret, Docker Secret, config tree hoặc Vault.
- Dùng configtree cho secret file được mount và giữ certificate/key ở file path riêng.
- Dùng workload identity hoặc cơ chế xác thực Vault phù hợp; tránh root token tĩnh.
- Cấp credential riêng cho từng ứng dụng và từng broker cluster.
- Cấp quyền Kafka ACL, RabbitMQ permission và Pulsar tenant/namespace tối thiểu.
- Dùng TLS và hostname verification; không trust-all certificate.
- Phân biệt truststore với keystore và CA certificate với private key.
- Dùng PKCS12/JKS/PEM theo khả năng của client version.
- Theo dõi expiry của password, token, certificate và lease.
- Có quy trình overlap khi thay CA hoặc certificate.
- Có kế hoạch reconnect/recreate client sau khi secret thay đổi.
- Không giả định Environment refresh sẽ tự cập nhật binder client.
- Không log secret hoặc expose env/configprops endpoint công khai.
- Kiểm thử credential sai, certificate sai, ACL thiếu quyền và rotation.
- Xác minh rolling restart không làm mất consumer capacity hoặc tạo lỗi publish kéo dài.

## 23. Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), thứ tự PropertySource, biến môi trường và config tree.
- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html), SSL bundles với JKS/PKCS12 và PEM, trust material và reload.
- [Spring Cloud Stream — Kafka Binder Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html), SASL, SSL, JAAS và multi-binder credential.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html), thuộc tính client dùng chung của Kafka Binder.
- [Spring Cloud Stream — RabbitMQ Binder Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/binder-properties.html), Rabbit binder sử dụng Spring Boot ConnectionFactory và prefix spring.rabbitmq.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html), username/password và thuộc tính RabbitMQ SSL.
- [Spring for Apache Pulsar — Pulsar Client](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/pulsar-client.html), TLS, authentication plugin, token, PEM/JKS và client builder customizer.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html), binder sử dụng Spring for Apache Pulsar và các thuộc tính client.
- [Spring Cloud Vault — ConfigData API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html), import vault:// và mount secret backend thành PropertySource.
- [Spring Vault — Property Sources](https://docs.spring.io/spring-vault/reference/vault/propertysource.html), VaultPropertySource và credential rotation.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/43/configuration/consumer-configs/), SSL keystore/truststore, SASL và security.protocol.

Quản lý mật khẩu, khóa và chứng chỉ bằng cấu hình bên ngoài giúp cùng một Spring Cloud Stream artifact chạy an toàn ở nhiều môi trường mà không mang theo credential production. Spring Boot cung cấp Environment và config tree; Spring Cloud Vault có thể cung cấp secret từ backend; từng binder nhận các thuộc tính bảo mật riêng theo Kafka, RabbitMQ hoặc Pulsar. Để bảo đảm kết nối lâu dài, cần quản lý quyền tối thiểu, xác minh certificate, theo dõi hạn dùng và thiết kế quy trình reconnect hoặc restart khi secret được thay.

