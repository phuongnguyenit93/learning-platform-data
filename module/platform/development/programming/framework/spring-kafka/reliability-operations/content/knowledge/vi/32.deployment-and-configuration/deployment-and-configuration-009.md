# Cấu hình security trong Spring Kafka Reliability Operations

## 1. Tại sao security là một phần của reliability?

Một ứng dụng Spring Kafka có thể chạy ổn định ở local với broker `localhost:9092`, nhưng ngay khi triển khai staging/production có thể gặp những vấn đề rất khác: kết nối bị từ chối do TLS, SASL đăng nhập không thành công, principal không có quyền đọc topic, chứng chỉ hết hạn hoặc credential bị rotate trong lúc consumer đang xử lý dữ liệu.

Các lỗi bảo mật không chỉ làm ứng dụng “không kết nối được”. Nếu người vận hành khắc phục bằng cách **chuyển sang PLAINTEXT**, **tắt hostname verification**, **đổi consumer group** hoặc **trỏ sang một cluster khác**, hậu quả có thể nghiêm trọng hơn: lộ thông tin nhạy cảm, mất khả năng cô lập tenant, bỏ sót sự kiện hoặc xử lý lại dữ liệu nhiều lần.

Trong phần *Deployment và cấu hình* của **Spring Kafka Reliability Operations**, “Cấu hình security” tập trung vào cách đưa các cơ chế bảo vệ Kafka vào **Spring Boot/Spring Kafka**, kết nối chúng với cấu hình của broker, quản lý secret và vận hành thay đổi an toàn.

Sau bài này, bạn có thể:

1. Phân biệt **TLS encryption**, **SASL authentication**, **mTLS**, **Kafka ACL/RBAC** và **network controls**.
2. Cấu hình `security.protocol`, `sasl.mechanism`, `sasl.jaas.config` và truststore/keystore trong Spring Boot.
3. Lựa chọn giữa `SSL`, `SASL_SSL`, `PLAINTEXT` và `SASL_PLAINTEXT` theo môi trường.
4. Tách credential khỏi source code/JAR bằng secret manager, mounted secret và `configtree:`.
5. Thiết kế principal, topic/group ACL và quyền publish DLT theo nguyên tắc least privilege.
6. Thực hiện rotation chứng chỉ/mật khẩu bằng rolling deployment mà không tùy tiện thay offset/group identity.
7. Kiểm thử kết nối, xác thực, phân quyền, TLS và tình huống lỗi có kiểm soát.
8. Chẩn đoán authentication failure, authorization failure, SSL handshake và sai broker endpoints.

Ví dụ chính sử dụng **Java 17+, Spring Boot 3.x, Spring Kafka 3.x**. Các nguyên tắc áp dụng rộng hơn, nhưng tên property và API cụ thể phải tương thích với Spring Boot BOM, Kafka client và broker thực tế.

## 2. Mô hình bảo vệ Kafka từ đầu đến cuối

Một kết nối consumer/producer đi qua nhiều lớp:

~~~text
                  Spring Kafka Application
                           |
                      Kafka clients
                           |
        +------------------+-------------------+
        |                  |                   |
        v                  v                   v
     Network             TLS               Identity
   DNS / firewall    encryption +        SASL credential
   VPC / policy     server identity      hoặc client cert
        |                  |                   |
        +------------------+-------------------+
                           |
                           v
                        Broker
                           |
                 Authenticate principal
                           |
                           v
                 Authorize Topic / Group
                           |
                           v
                    Read / Write / Commit
                           |
                           v
                   Business processing
                idempotency / auditing
~~~

| Lớp | Câu hỏi cần trả lời | Cơ chế |
| --- | --- | --- |
| **Network** | Client có được phép kết nối tới broker này không? | Firewall, security group, VPC, Kubernetes NetworkPolicy, private endpoint. |
| **Encryption in transit** | Dữ liệu có được mã hóa trên đường truyền không? | TLS qua `SSL` hoặc `SASL_SSL`. |
| **Server authentication** | Client có đang nói chuyện với broker đúng danh tính không? | Truststore, CA chain, hostname verification. |
| **Client authentication** | Broker biết client là ai bằng cách nào? | SASL/SCRAM, SASL/PLAIN, OAuth, mTLS hoặc provider-specific mechanism. |
| **Authorization** | Principal có quyền đọc/ghi topic, join group hay không? | Kafka ACL, RBAC của nền tảng, policy broker. |
| **Application security** | Record có đúng tenant/schema, không bị xử lý trùng không? | Validation, idempotency, schema governance, audit. |
| **Secret lifecycle** | Credential được cấp, rotate và thu hồi thế nào? | Vault/cloud secret manager, workload identity, RBAC, rotation. |

**TLS, SASL và ACL không thay thế nhau.** Một client có thể bắt tay TLS thành công nhưng SASL sai mật khẩu; client có thể SASL thành công nhưng vẫn không có quyền `Read` topic; có thể có quyền topic nhưng thiếu quyền `Group`.

## 3. Chọn `security.protocol` cho đúng

Kafka clients hỗ trợ các lựa chọn giao thức thường gặp:

| `security.protocol` | Mã hóa kết nối | Cách xác thực thường dùng | Khi nào phù hợp? |
| --- | --- | --- | --- |
| `PLAINTEXT` | Không | Thường không có client authentication qua Kafka protocol | Chỉ môi trường local/test cách ly được cho phép. |
| `SSL` | Có | Server TLS; có thể thêm **mTLS** khi broker yêu cầu chứng chỉ client | Kafka dùng TLS, thường là mTLS. |
| `SASL_PLAINTEXT` | Không | SASL (ví dụ SCRAM/PLAIN) nhưng không có TLS | **Tránh trên mạng production**; thông tin xác thực và dữ liệu không có lớp TLS bảo vệ. |
| `SASL_SSL` | Có | TLS xác minh broker + SASL xác thực client | Lựa chọn phổ biến cho SCRAM/PLAIN/OAuth qua TLS. |

Quy tắc triển khai phổ biến:

~~~text
local/test isolated     -> PLAINTEXT (chỉ khi được phê duyệt)
production with SCRAM   -> SASL_SSL
production with mTLS    -> SSL + client certificate
managed Kafka platform  -> theo provider (thường TLS + SASL/OAuth/IAM)
~~~

Không có một bộ cấu hình “production duy nhất” cho mọi cluster. Phải biết broker **đang mở listener nào, port nào, cơ chế SASL nào và CA nào**. Spring Kafka client không thể tự quyết định phương thức xác thực nếu broker không được cấu hình tương ứng.

### TLS một chiều và mTLS

**TLS một chiều:** client xác minh certificate của broker. Broker chưa chắc xác thực client bằng certificate; danh tính client có thể được xác nhận qua SASL.

**mTLS (mutual TLS):** ngoài việc client kiểm certificate broker, broker còn yêu cầu **client certificate**, xác minh chain và ánh xạ certificate thành principal. Thường dùng `security.protocol=SSL`, cùng truststore và keystore phía client.

**Truststore** chứa CA/certificate để tin tưởng phía đối tác; **keystore** có thể chứa private key + certificate của chính client. Không đặt private key vào ConfigMap hoặc Git.

## 4. Một cấu hình Spring Boot Kafka được nạp như thế nào?

Spring Boot lấy các property từ `application.yml`, profile, environment, command-line, file ngoài JAR, secret/configtree hoặc nguồn Config Data được tích hợp thêm.

~~~text
application.yml (cấu hình cơ sở)
          |
          +-- application-local.yml
          |
          +-- application-prod.yml
          |
          +-- env / ConfigMap / secret mount
                          |
                          v
                  Spring Environment
                          |
                          v
                  KafkaProperties
                          |
                 +--------+---------+
                 |                  |
                 v                  v
            ConsumerFactory    ProducerFactory
                 |                  |
                 v                  v
           @KafkaListener      KafkaTemplate
~~~

Những property Kafka client có thể đi vào:

- `spring.kafka.properties.*`: thuộc tính Kafka dùng chung, ví dụ `security.protocol`.
- `spring.kafka.consumer.properties.*`: thuộc tính riêng consumer.
- `spring.kafka.producer.properties.*`: thuộc tính riêng producer.
- `spring.kafka.ssl.*`: các thuộc tính SSL hỗ trợ bởi Spring Boot.
- `spring.kafka.consumer.*`, `spring.kafka.producer.*`, `spring.kafka.listener.*`: những property có tên typed/shortcut của Spring Boot.

**Không nhầm `spring.kafka.properties.sasl.jaas.config` với một property ứng dụng tên `app.kafka.*`.** Namespace ứng dụng chỉ có hiệu lực khi code tự bind và sử dụng; Kafka client properties phải được chuyển đúng vào factories.

### Cách giữ nguyên Kafka client keys có dấu chấm

Trong YAML, nên đặt Kafka client property dạng key nguyên bản:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
~~~

Các khóa như `sasl.jaas.config`, `ssl.endpoint.identification.algorithm` hay `max.poll.interval.ms` chứa dấu chấm. Nếu muốn override từ environment, dùng placeholder ở **value** thay vì đoán một tên environment variable thể hiện nested map key:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: ${KAFKA_SECURITY_PROTOCOL:SASL_SSL}
~~~

Với thông tin production bắt buộc, tránh fallback nguy hiểm như `PLAINTEXT` hoặc `localhost:9092`.

## 5. Thiết lập môi trường thực hành

Cấu trúc dự án minh họa:

~~~text
secure-orders-worker/
├── build.gradle
└── src/main/
    ├── java/com/example/orders/
    │   ├── SecureOrdersApplication.java
    │   ├── MessagingProperties.java
    │   ├── OrderConsumer.java
    │   └── ResultProducer.java
    └── resources/
        ├── application.yml
        ├── application-local.yml
        └── application-prod.yml

deployment/
├── orders-configmap.yml
└── orders-deployment.yml
~~~

### Dependency

File `build.gradle` trong một dự án Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
 
tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management nên quản lý các phiên bản tương thích của Spring Kafka và Kafka clients. Không nâng riêng Kafka client lên một version bất kỳ rồi giả định mọi cơ chế SASL/TLS/metrics vẫn tương thích.

Để tập trung vào security, ví dụ sử dụng message là `String`; hệ thống thực nên áp dụng serializer, schema validation, hạn kích thước record và kiểm dữ liệu đầu vào riêng.

## 6. Cấu hình cơ sở không chứa credential

File `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: secure-orders-worker

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

    client-id: ${KAFKA_CLIENT_ID:secure-orders-worker}

    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP}
      enable-auto-commit: false
      auto-offset-reset: ${KAFKA_AUTO_OFFSET_RESET:none}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

    listener:
      ack-mode: record
      concurrency: ${KAFKA_LISTENER_CONCURRENCY:2}

    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      properties:
        enable.idempotence: true

app:
  messaging:
    orders-topic: ${KAFKA_ORDERS_TOPIC}
    results-topic: ${KAFKA_RESULTS_TOPIC}
~~~

Các giá trị này được **externalize** để cùng một image dùng cho nhiều môi trường.

| Cấu hình | Vai trò | Tác động reliability |
| --- | --- | --- |
| `bootstrap-servers` | Broker bootstrap endpoints | Sai cluster có thể dẫn tới sai dữ liệu, không chỉ mất kết nối. |
| `group-id` | Danh tính consumer group | Đổi group có thể replay hoặc skip backlog theo policy offset. |
| `enable-auto-commit: false` | Tắt auto-commit do Kafka consumer thực hiện | Spring Kafka container quản lý thời điểm commit offset. |
| `ack-mode: record` | Commit theo record processing semantics | Không tự tạo transaction với database ngoài. |
| `auto-offset-reset: none` | Không tự chọn earliest/latest khi thiếu offset hợp lệ | Fail-fast với group mới, giảm nguy cơ âm thầm bỏ/replay. |
| `acks: all` | Producer chờ broker ACK theo ISR | Tăng durability khi broker được cấu hình phù hợp. |
| `enable.idempotence: true` | Producer dedup request retries phù hợp trong một session | Không thay thế application idempotency khi consumer redeliver. |

`auto-offset-reset=none` chỉ là ví dụ chính sách production thận trọng. Nếu ứng dụng cần khởi tạo group mới, phải có **kế hoạch offsets** rõ ràng. Security không nên được dùng như lý do để tùy tiện đổi `group-id` khi authentication thất bại.

## 7. Cấu hình local: chỉ dùng PLAINTEXT trong môi trường cách ly

File `application-local.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP:secure-orders-worker-local}
      auto-offset-reset: earliest
    properties:
      security.protocol: PLAINTEXT

app:
  messaging:
    orders-topic: ${KAFKA_ORDERS_TOPIC:orders.events.local}
    results-topic: ${KAFKA_RESULTS_TOPIC:orders.results.local}
~~~

Chạy local:

~~~bash
java -jar secure-orders-worker.jar \
  --spring.profiles.active=local
~~~

**Không dùng profile local làm profile mặc định của production.** Một lỗi điển hình là deployment thiếu profile, fallback về `localhost`/PLAINTEXT khiến Pod “khởi động thành công” nhưng không nhận message hoặc cố kết nối sai broker.

Nếu app chạy trong Docker, `localhost` bên trong container là chính container đó; cần DNS service Kafka trong network Docker, không mặc định trỏ tới máy host.

## 8. Production với SASL/SCRAM qua TLS

Giả sử broker đã cấu hình:

- Listener hỗ trợ TLS và SASL.
- `SCRAM-SHA-512` là cơ chế được bật.
- Một principal có credential và Kafka ACL phù hợp.
- Trust chain của certificate broker được client tin cậy.
- Port được phép đi qua firewall/network policy.

File `application-prod.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/etc/kafka-secrets/"

  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: ${kafka.sasl.jaas.config}

    ssl:
      trust-store-location: ${KAFKA_TRUSTSTORE_LOCATION:file:/etc/kafka-certs/truststore.p12}
      trust-store-type: PKCS12
      trust-store-password: ${kafka.truststore.password}
~~~

Ở ví dụ này:

- `security.protocol` quyết định giao thức nối broker.
- `sasl.mechanism` phải trùng cơ chế mà broker và principal hỗ trợ.
- `sasl.jaas.config` chứa thông tin xác thực, được nạp từ file secret.
- Truststore dùng xác minh certificate broker.
- `configtree:` đọc các file mount như configuration properties.
- **Không** cho toàn bộ JAAS credential xuất hiện trong source, Dockerfile, ConfigMap hoặc Git.

Lưu ý: truststore tùy thuộc kiểu certificate broker. Nếu CA công cộng đã được JVM trust sẵn và cấu hình không yêu cầu truststore riêng, có thể không cần cả khối truststore tùy use case. Nếu chỉ định truststore custom, phải đảm bảo nó chứa **đủ CA cần tin** cho những endpoint Kafka được dùng.

### 8.1. Nội dung secret được provision riêng

Trong Pod:

~~~text
/etc/kafka-secrets/
  kafka.sasl.jaas.config
  kafka.truststore.password

/etc/kafka-certs/
  truststore.p12
~~~

Spring Boot `configtree:` xem tên file là property key; file `kafka.sasl.jaas.config` cung cấp giá trị `${kafka.sasl.jaas.config}`. Phải đảm bảo người vận hành mount đúng tên file và đường dẫn.

**Ví dụ cú pháp JAAS với placeholder, KHÔNG chứa credential thật:**

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
username="example-orders-worker"
password="REPLACE_WITH_SECRET";
~~~

Trong file giá trị thực, dòng cấu hình thường được lưu như một JAAS configuration string hợp lệ. Password và username thực được cấp bởi secret-management workflow và không được copy vào tài liệu, log hoặc ticket.

### 8.2. Về `SCRAM-SHA-512`

SCRAM cung cấp challenge-response để client xác thực với broker; broker cần provisioning credential SCRAM đúng. Tuy nhiên:

- SCRAM **không thay TLS** cho mã hóa record và bảo vệ khỏi MITM.
- Một cấu hình client đúng không tự tạo tài khoản SCRAM trên broker.
- Nếu principal đã tồn tại nhưng thiếu ACL, SASL có thể thành công còn consume/produce vẫn thất bại.
- Nếu broker chỉ hỗ trợ `SCRAM-SHA-256` hoặc `PLAIN`, phải dùng cơ chế tương ứng đã được phê duyệt.

### 8.3. Không tắt hostname verification

Kafka TLS client thường dùng `ssl.endpoint.identification.algorithm=https` để xác minh broker hostname với chứng chỉ, tùy client version/configuration.

**Không sửa thành chuỗi rỗng** chỉ để bỏ qua lỗi certificate hostname mismatch. Đây là biện pháp làm yếu server authentication, có thể mở đường cho MITM.

Hãy giải quyết nguyên nhân: SAN/CN certificate, DNS broker, `advertised.listeners`, trust chain hoặc hostname thực tế.

## 9. Khi nào dùng SASL/PLAIN, OAuth hoặc IAM?

| Cơ chế | Cách hoạt động ở mức khái quát | Lưu ý |
| --- | --- | --- |
| `SCRAM-SHA-256` / `SCRAM-SHA-512` | Username/password và challenge-response | Dùng TLS, credential rotation và ACL. |
| `PLAIN` | Username/password qua SASL | **Bắt buộc dựa vào TLS theo security policy production**, vì PLAIN không tự mã hóa mật khẩu. |
| `OAUTHBEARER` | Token được cấp bởi identity provider | Cần login callback/token refresh, issuer/audience/TTL đúng. |
| Cloud-specific IAM/OAuth | Credential/workload identity hoặc callback/provider plugin | Cần Kafka client plugin/cấu hình theo tài liệu của nhà cung cấp. |
| mTLS | Client certificate/private key | Phân quyền theo principal của chứng chỉ, có CA/rotation. |

Không nên giả định chuyển `sasl.mechanism` thành `OAUTHBEARER` là xong. Nhiều nền tảng yêu cầu `sasl.login.callback.handler.class`, login module hoặc plugin cụ thể. Tương tự, AWS IAM authentication không đồng nghĩa mọi Kafka cluster hỗ trợ cùng cấu hình JAAS của SCRAM.

Nếu lựa chọn cloud-managed Kafka, dùng tài liệu của **chính provider và phiên bản** để quyết định auth mechanism. Tránh gắn một password tĩnh vào properties khi nền tảng hỗ trợ workload identity ngắn hạn.

## 10. Production với mutual TLS

Khi broker yêu cầu client certificate, client dùng TLS với keystore chứa chứng chỉ và private key của workload:

~~~text
Spring Kafka consumer
   |
   | TLS ClientHello
   v
Kafka broker certificate ---> client kiểm truststore, SAN/hostname
   |
   | Server yêu cầu client certificate
   v
Client certificate + proof private key
   |
   v
Broker xác minh cert CA và ánh xạ principal
   |
   v
ACL/RBAC cho topic/group
~~~

Ví dụ profile **thay thế** cho trường hợp mTLS (không dùng đồng thời như một override ngẫu nhiên lên cấu hình SCRAM):

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SSL

    ssl:
      trust-store-location: file:/etc/kafka-certs/truststore.p12
      trust-store-type: PKCS12
      trust-store-password: ${kafka.truststore.password}

      key-store-location: file:/etc/kafka-certs/client-keystore.p12
      key-store-type: PKCS12
      key-store-password: ${kafka.keystore.password}
      key-password: ${kafka.key.password}
~~~

Các `${kafka.*.password}` trong ví dụ được nạp từ configtree/secret provider tương tự phần SASL. Đây là ví dụ **PKCS12**: một số tổ chức dùng PEM hoặc các cơ chế key material khác; phải chọn cấu hình client đúng loại.

Lưu ý mTLS gồm **cả cấu hình broker**. Broker phải bật listener `SSL` và chính sách yêu cầu hoặc kiểm client certificate; nếu broker không yêu cầu cert client, chỉ có TLS một chiều chứ không tự nhiên có mTLS. Phần client không thể tự bật chế độ xác minh client tại broker.

**Không đặt private key trong ConfigMap.** Chứng chỉ public riêng lẻ có thể ít nhạy cảm hơn, nhưng cần quản lý theo chính sách; keystore chứa private key là secret.

## 11. Đường truyền bảo mật chưa đủ: phải có Authorization

Sau khi xác thực thành công, Kafka broker xác định principal để kiểm **ACL** hoặc RBAC. Quyền thường gắn với **resource type** (Topic, Group, Cluster, TransactionalId...) và **operation** (Read, Write, Describe...).

### 11.1. Tách principal producer và consumer

Đối với hệ thống quan trọng, có thể tạo hai workload identity:

~~~text
orders-consumer-principal
    |
    +-- READ orders.events.v1
    +-- READ consumer group orders-worker-v1
    +-- no WRITE to unrelated topics

orders-result-producer-principal
    |
    +-- WRITE orders.results.v1
    +-- no READ to orders.events.v1
    +-- no access to unrelated groups
~~~

Nếu cùng JVM dùng một bộ credential cho cả producer và consumer, principal cần tập quyền tương ứng; điều này đơn giản hơn nhưng tăng phạm vi ảnh hưởng khi credential lộ. Với workload phân tách được, principal riêng thường cho phép least privilege rõ hơn.

### 11.2. Ví dụ yêu cầu quyền

| Hoạt động | Quyền Kafka thường cần | Kiểm thêm |
| --- | --- | --- |
| Consume từ topic | `Read` trên Topic; `Read` trên Group, cùng một số quyền mô tả tùy broker | Topic tồn tại, group được cấp quyền, offsets hợp lệ. |
| Produce tới topic | `Write` trên Topic; có thể cần `Describe` hoặc quyền phụ liên quan | Quota/ACL, acks, retention. |
| Publish DLT | `Write` trên DLT topic | Error handler/recoverer có thật, serializer và ACL phù hợp. |
| Dùng transactional producer | Quyền thích hợp trên TransactionalId và topic | Transaction ID prefix và broker transaction support. |
| Idempotent producer | Quyền liên quan tới idempotent write tùy Kafka broker/version | `acks=all`, idempotence và các client configs tương thích. |
| Tạo/đổi topic | `Create`/`Alter` theo policy | Nên phân cho admin/IaC, không mặc định cấp cho ứng dụng. |
| Xem cluster metadata | `Describe` hoặc quyền liên quan | Không tự cấp Cluster All cho client thường. |

Các quyền chính xác phụ thuộc broker version, authorizer và provider. **Đừng copy máy móc một bộ ACL “full access”**. Hãy kiểm quyền tối thiểu qua test xác thực/authorization thực tế và xem audit của Kafka cluster.

### 11.3. ACL mẫu bằng Kafka CLI

Đoạn minh họa dưới đây **không chứa username/password** và chỉ áp dụng khi đang dùng Apache Kafka authorizer/CLI phù hợp:

~~~bash
# Principal giả định User:orders-consumer đã tồn tại.
kafka-acls.sh --bootstrap-server broker-admin.example.internal:9093 \
  --add --allow-principal User:orders-consumer \
  --operation Read --topic orders.events.v1

kafka-acls.sh --bootstrap-server broker-admin.example.internal:9093 \
  --add --allow-principal User:orders-consumer \
  --operation Read --group orders-worker-v1

# Producer được cấp Write trên topic kết quả.
kafka-acls.sh --bootstrap-server broker-admin.example.internal:9093 \
  --add --allow-principal User:orders-producer \
  --operation Write --topic orders.results.v1
~~~

**Đây là lệnh minh họa quyền ACL, không phải hướng dẫn chạy trực tiếp lên production.** Admin CLI cũng cần `--command-config` hoặc cấu hình xác thực phù hợp broker, và phải chạy theo quy trình approval/Infrastructure as Code. Đừng truyền raw password trên command line.

Quyền nhóm có thể được cấp theo tên chính xác hoặc prefix kiểm soát. Wildcard/broad prefix dễ tạo quyền ngoài ý định, nhất là khi một principal dùng chung giữa nhiều tenant.

## 12. Identity và permission cho consumer group

Consumer cần cả quyền topic và group. Một lỗi thường gặp:

~~~text
SASL handshake: SUCCESS
Topic metadata: SUCCESS
JoinGroup: GroupAuthorizationException
~~~

Nghĩa là broker đã nhận principal, có thể topic quyền hợp lệ, nhưng **group-id không được cấp Read**. Chuyển `group-id` sang tên khác để “được phép join” là phương án rất nguy hiểm vì consumer group identity quyết định tập committed offsets.

~~~text
group-id = orders-worker-v1
  committed offset partition 0: 2000

đổi group-id = orders-worker-v2
  chưa có committed offsets
       |
       +-- earliest -> có thể replay lượng lớn record
       +-- latest   -> có thể bỏ backlog hiện có
       +-- none     -> báo lỗi vì chưa có offset hợp lệ
~~~

Khắc phục đúng: xác minh principal, group ACL và topic ACL. Nếu business cần chuyển group thật, phải có kế hoạch offset migration/cutover, test idempotency và đối soát.

## 13. Không cấp quyền admin cho ứng dụng chỉ để khỏi lỗi

Trong một số môi trường, ứng dụng dùng `NewTopic`/`KafkaAdmin` để tự tạo topic. Khi bật ACL, startup có thể lỗi vì principal không có quyền Create.

Không nên giải quyết bằng cách cấp `All` trên Cluster hoặc tất cả Topic. Lựa chọn an toàn hơn:

1. Quản lý topic, partitions, replication, retention và ACL bằng Terraform/Strimzi/GitOps/Kafka admin.
2. Ứng dụng chỉ có quyền Read/Write cần thiết.
3. Tắt hoặc điều chỉnh auto-creation nếu production không cho phép.
4. Test một topic thiếu phải được phát hiện và cảnh báo rõ.
5. Nếu thật sự cần tự provision, cấp quyền rất hẹp và audit đầy đủ.

Quyền thay đổi broker security policy thuộc đường triển khai hạ tầng, khác quyền xử lý message nghiệp vụ.

## 14. Secret không nằm trong source code hoặc image

Những cách dưới đây dễ rò secret:

~~~text
BAD:
  application-prod.yml chứa password thật
  Dockerfile: ENV KAFKA_PASSWORD=...
  java -jar worker.jar --spring.kafka.properties.sasl.jaas.config="..."
  Helm values.yaml commit raw JAAS credential
  CI logs in toàn bộ environment variables
  REST debug endpoint trả tất cả KafkaProperties
~~~

Ngay cả khi giá trị được Base64 trong Kubernetes Secret manifest, **Base64 không phải mã hóa**. Nếu file chứa bí mật đã được commit, `.gitignore` về sau không xóa được lịch sử; cần rotate/revoke và xử lý lưu trữ theo policy.

### Các kênh cung cấp secret

| Kênh | Cách dùng | Điểm cần kiểm |
| --- | --- | --- |
| Vault | Workload identity lấy secret hoặc mount qua agent | Lease/TTL, policy, audit, rotation. |
| AWS Secrets Manager | Pod/VM dùng IAM role/workload identity | Quyền tối thiểu theo secret ARN. |
| Google Cloud Secret Manager | Workload identity lấy secret phiên bản phù hợp | IAM, audit, namespace/project boundary. |
| Azure Key Vault | Managed identity truy xuất credential/certificate | Role/permission và rotation. |
| Kubernetes Secret | Mount file hoặc inject env | etcd encryption, Kubernetes RBAC, node/Pod permissions. |
| External Secrets Operator/CSI | Đồng bộ secret từ provider thành file/mount | Đồng bộ/refresh không đồng nghĩa Kafka client reload. |

`configtree:/etc/kafka-secrets/` là một phương án thực dụng trong Spring Boot: cấu hình ứng dụng vẫn ở Git, còn secret value được cấp qua filesystem được bảo vệ.

### Vì sao mounted secret chưa giải quyết hết vòng đời?

Kafka client thường đọc JAAS config, keystore hoặc callback handler **khi khởi tạo**. Nếu mounted file được cập nhật do rotation:

- File trên disk có thể đã đổi.
- Spring Environment hoặc Kafka client đã tạo trước đó **chưa chắc tự reload**.
- Một kết nối đang hoạt động có thể tiếp tục dùng credential/certificate cũ.
- Producer/consumer có thể cần restart hoặc tái tạo factories/containers.

Không mặc định hot reload chỉ vì Kubernetes cập nhật projected Secret volume. Thiết kế rolling restart/refresh có kiểm thử là cách dễ dự đoán hơn.

## 15. Kubernetes: tách ConfigMap và Secret

Sơ đồ triển khai:

~~~text
GitOps:
  orders-kafka-config (ConfigMap)
       | -- KAFKA_BOOTSTRAP_SERVERS
       | -- KAFKA_CONSUMER_GROUP
       | -- KAFKA_ORDERS_TOPIC
       | -- KAFKA_RESULTS_TOPIC
       v
  Deployment
       |
       +-- envFrom ConfigMap
       |
       +-- Secret volume: kafka.jaas.config
       +-- Secret volume: kafka.truststore.password
       +-- Secret volume: truststore.p12
                 |
                 v
           Spring Boot configtree
                 |
                 v
            SASL_SSL clients
~~~

### 15.1. ConfigMap không chứa credential

File `deployment/orders-configmap.yml`:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: secure-orders-kafka-settings
data:
  KAFKA_BOOTSTRAP_SERVERS: "broker-1.prod.example.internal:9093,broker-2.prod.example.internal:9093"
  KAFKA_CONSUMER_GROUP: "orders-worker-v1"
  KAFKA_CLIENT_ID: "orders-worker"
  KAFKA_ORDERS_TOPIC: "orders.events.v1"
  KAFKA_RESULTS_TOPIC: "orders.results.v1"
  KAFKA_AUTO_OFFSET_RESET: "none"
  KAFKA_LISTENER_CONCURRENCY: "2"
~~~

Đây là địa chỉ và tên topic **minh họa**. Chúng không phải endpoint thật.

### 15.2. Deployment mount secret được tạo riêng

File `deployment/orders-deployment.yml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: secure-orders-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: secure-orders-worker
  template:
    metadata:
      labels:
        app: secure-orders-worker
    spec:
      containers:
        - name: worker
          image: registry.example.org/secure-orders-worker:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
          envFrom:
            - configMapRef:
                name: secure-orders-kafka-settings
          volumeMounts:
            - name: kafka-auth
              mountPath: /etc/kafka-secrets
              readOnly: true
            - name: kafka-certs
              mountPath: /etc/kafka-certs
              readOnly: true
      volumes:
        - name: kafka-auth
          secret:
            secretName: secure-orders-kafka-auth
            items:
              - key: jaas-config
                path: kafka.sasl.jaas.config
              - key: truststore-password
                path: kafka.truststore.password
        - name: kafka-certs
          secret:
            secretName: secure-orders-kafka-truststore
            items:
              - key: truststore.p12
                path: truststore.p12
~~~

**Chú ý:** manifest trên không tạo hai Secret chứa credential. Chúng phải được provision trước bằng một quy trình bảo mật riêng. Một triển khai production còn cần resource requests/limits, probes, service account, RBAC, network policy, rollout policy và log management.

### 15.3. Secret access của Pod

Cần bảo đảm:

- Chỉ workload/namespace phù hợp mới truy cập được Secret.
- Pod và container không chạy với quyền rộng ngoài yêu cầu.
- Secret volume được mount read-only với quyền filesystem phù hợp.
- Service account không có quyền `list`/`get` Secret tràn lan nếu không cần.
- Etcd và backup được mã hóa/phân quyền theo chuẩn cluster.
- Không cho phép `kubectl exec` hoặc debug của người không có quyền vào Pod chứa secret.
- Không copy secret file vào artifact build/log khi thu thập diagnostic.

Kubernetes Secret khác với Kafka ACL: quyền đọc Secret ở Kubernetes **không chứng minh** principal có quyền Kafka; Kafka ACL cũng không giới hạn ai đọc Secret resource nếu Kubernetes RBAC sai.

## 16. Mạng và broker endpoints cũng là thành phần security

Trong Kafka, `bootstrap.servers` là điểm để client kết nối ban đầu và lấy metadata. Sau đó client phải kết nối tới broker endpoints được trả về trong `advertised.listeners`.

~~~text
Application
   |
   | bootstrap: kafka-bootstrap.example:9093
   v
Bootstrap broker
   |
   | metadata includes:
   | broker1.internal.example:9093
   | broker2.internal.example:9093
   v
Client connects directly to returned broker endpoints
~~~

Nếu client ngoài mạng nội bộ không resolve được hostname do broker quảng bá, ứng dụng có thể:

- TLS bootstrap thành công nhưng không đọc/ghi được message.
- Nhận timeout/reconnect liên tục.
- Báo hostname mismatch trên cert của broker con.
- Trông giống “Kafka password sai” dù nguyên nhân là DNS/listener config.

Hãy kiểm:

1. DNS từ chính Pod/VM.
2. Network route, firewall, security group và Kubernetes NetworkPolicy.
3. Port/protocol tương ứng với listener: `SSL` hay `SASL_SSL`.
4. Hostname SAN của certificate với cả bootstrap và advertised broker endpoints.
5. Kafka broker `advertised.listeners` trả về hostname client có thể kết nối.
6. Kafka ACL sau khi network/auth đã hoạt động.

**Không dùng tắt certificate validation để “sửa” một vấn đề DNS hay advertised listeners.**

## 17. Producer và consumer cần cùng security hay khác?

Spring Boot property `spring.kafka.properties` được áp dụng chung theo cơ chế Boot config; có thể đặt property riêng ở:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL

    consumer:
      properties:
        # Consumer-specific Kafka client properties.
        max.poll.interval.ms: 300000

    producer:
      properties:
        # Producer-specific Kafka client properties.
        delivery.timeout.ms: 120000
~~~

Trong nhiều hệ thống, consumer và producer cùng xác thực với broker bằng cùng principal. Nhưng nếu cần tách quyền:

- Mỗi Kafka client factory có credential/JAAS riêng.
- Tách `ConsumerFactory` và `ProducerFactory` có property sets tương ứng.
- Với code tự tạo factory, dùng đúng cấu hình SSL/SASL từ `KafkaProperties` hoặc explicit mapping; **không bỏ sót security properties**.
- Kiểm admin clients (`KafkaAdmin`) có cần credentials riêng hay không.
- Nếu dùng Kafka Streams, Schema Registry, Connect hay REST Proxy, mỗi thành phần có cấu hình bảo mật **riêng**, không tự thừa hưởng toàn bộ `spring.kafka` của ứng dụng.

Không nhầm `spring.kafka.consumer.properties.sasl.jaas.config` với `spring.kafka.properties.sasl.jaas.config`; cái đầu chỉ dành cho consumer. Một lỗi phổ biến là consumer kết nối được nhưng DLT publisher thất bại vì producer thiếu credential.

## 18. KafkaTemplate, listener và cấu hình security

Spring Boot auto-configuration có thể tạo `ConsumerFactory`, `ProducerFactory`, `KafkaTemplate` và listener container dựa trên các properties đã bind.

Một consumer đơn giản:

~~~java
package com.example.orders;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @KafkaListener(topics = "${app.messaging.orders-topic}")
    public void handle(String payload) {
        // Parse, validate schema, kiểm business key và xử lý idempotent.
        // Exception được chuyển cho error handler theo policy của app.
    }
}
~~~

Producer:

~~~java
package com.example.orders;

import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class ResultProducer {

    private final KafkaTemplate<String, String> kafka;
    private final MessagingProperties messaging;

    public ResultProducer(
            KafkaTemplate<String, String> kafka,
            MessagingProperties messaging) {
        this.kafka = kafka;
        this.messaging = messaging;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String resultJson) {

        return kafka.send(
                messaging.resultsTopic(), orderId, resultJson);
    }
}
~~~

Property binding:

~~~java
package com.example.orders;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.messaging")
public record MessagingProperties(
        @NotBlank String ordersTopic,
        @NotBlank String resultsTopic) {
}
~~~

Trong class `@SpringBootApplication`, thêm `@ConfigurationPropertiesScan` để record properties được đăng ký. Giá trị `orders-topic` trong YAML được bind sang `ordersTopic` theo relaxed binding của Boot.

**Quan trọng:** Spring Kafka không thể sửa một broker ACL sai chỉ bằng code listener. Các class trên sử dụng credential và permission do `spring.kafka.*`/broker provisioning quyết định.

`KafkaTemplate.send` trả một future; thao tác gửi **không được xem là đã durable chỉ vì method return**. Xử lý success/failure callback phù hợp, không log payload chứa dữ liệu nhạy cảm.

## 19. Không lưu secret trong JobParameters, headers hoặc payload chỉ để debug

Mặc dù Kafka có TLS, dữ liệu vẫn có thể xuất hiện ở:

- Producer/consumer logs.
- DLT payload và error headers.
- Application traces hoặc monitoring backend.
- Record key, topic name, header và message body.
- Database output hoặc state store.
- Data backup của Kafka broker hay downstream service.

Một header như:

~~~text
Authorization: Bearer <raw-access-token>
~~~

không nên được đưa vào Kafka message để “worker khác dùng lại”. Một consumer có thể được cấp quyền đọc topic qua ACL nhưng không có quyền truy cập credential của hệ thống ngoài. Nếu một bước cần token, hãy resolve credential của chính workload qua secret manager.

### Error handler và DLT

Nếu record thất bại, `DefaultErrorHandler`/`DeadLetterPublishingRecoverer` (hoặc retry-topic mechanism) có thể chuyển record sang DLT theo chính sách. Cần:

- Producer principal có `Write` trên DLT topic.
- DLT topic có retention/ACL và encryption at rest phù hợp.
- Error headers không lộ mật khẩu, token hoặc exception message chứa dữ liệu nhạy cảm.
- Consumer DLT/quarantine có quyền hẹp, audit truy cập và workflow xử lý lại rõ.
- Không tự coi DLT là nơi an toàn để dump request nguyên văn chứa secret.

Đưa tên DLT vào YAML **không tự tạo** error handler hoặc quyền publish DLT; phải cấu hình recovery logic riêng.

## 20. Rotation credential an toàn

Một vòng đời rotation thông thường cần **giai đoạn chồng lấp** giữa credential cũ và mới khi nền tảng hỗ trợ.

~~~text
T0  Broker chấp nhận credential A
 |
T1  Provision credential B và ACL tương đương
 |
T2  Cập nhật Secret/secret manager cho B
 |
T3  Rolling Deployment: Pod mới dùng B
 |
T4  Xác nhận producer/consumer trên Pod mới hoạt động
 |
T5  Pod cũ dùng A được drain và dừng
 |
T6  Revoke credential A, kiểm audit và lỗi auth
~~~

Nếu broker không hỗ trợ đồng thời hai credential hoặc policy bắt buộc revoke ngay, phải có maintenance window/transition strategy phù hợp.

### Rotation password SASL

- Không in `sasl.jaas.config` khi kiểm tra.
- Kiểm principal B có cùng **đúng tập ACL cần thiết**, không cấp rộng hơn.
- Đừng thay `group-id` để làm Pod mới join dễ hơn.
- Theo dõi consumer lag, rebalance, authentication failure, producer send errors.
- Đảm bảo old consumers được dừng có kiểm soát để tránh workload cùng thao tác trên downstream theo cách không idempotent.

### Rotation certificate

- CA mới có thể cần được thêm vào truststore **trước khi** broker chuyển sang certificate ký bởi CA mới.
- Khi thay certificate broker, SAN phải khớp tất cả endpoint client dùng.
- Khi thay client certificate cho mTLS, principal mapping trên broker có thể đổi (ví dụ subject DN khác), khiến ACL cũ không còn khớp.
- Keystore/truststore password mới phải đồng bộ với file thực.
- Có thể cần restart Kafka client để nó nạp key material mới.

### Emergency revoke

Nếu secret có khả năng bị lộ, ưu tiên revoke/rotate theo incident response. Nhưng cần lập kế hoạch tránh toàn bộ consumer group mất quyền cùng lúc. Không giữ credential đã bị lộ chỉ vì sợ rebalance; thay bằng kế hoạch phục hồi bảo đảm an toàn và dữ liệu.

## 21. Rollout và điều khiển sự cố khi thay security

Security config là **runtime configuration**, nhưng Java Kafka clients không tự động refresh mọi property khi `ConfigMap`/`Secret` thay đổi.

Một quy trình rollout thực tế:

1. Xác định cấu hình/secret version cũ và mới, môi trường và phạm vi ảnh hưởng.
2. Kiểm secret/protocol bằng integration test hoặc staging tương đương production.
3. Provision broker principal/ACL/trust anchors trước khi rollout client.
4. Cập nhật ConfigMap/Secret theo quy trình versioned GitOps/secret management.
5. Rolling deploy Pod mới để Kafka clients nạp cấu hình mới.
6. Quan sát readiness, authentication/authorization failures, consumer membership, lag và producer ACK.
7. Đối soát side effect sau rebalance/redelivery (DB, API, audit).
8. Khi Pod mới hoạt động ổn định, dừng Pod cũ và thu hồi credential cũ.
9. Lưu change record/config version và phương án rollback.

**Rollback cần cả môi trường broker.** Nếu đã revoke credential A, rollback Pod mới về image/config cũ dùng A có thể không hoạt động. Thứ tự thay đổi broker/client và thời gian tồn tại credential chuyển tiếp là một phần của runbook.

### Consumer shutdown và rebalance

Rolling deployment sẽ gây consumer group rebalance hoặc thay đổi partition ownership. Một record có thể đã được xử lý DB nhưng chưa commit offset trước khi Pod chết, dẫn tới redelivery.

~~~text
Consumer A xử lý event X
   |
   v
DB commit thành công
   |
   v
Pod bị dừng trước offset commit
   |
   v
Consumer B nhận lại event X
```

SASL/TLS bảo vệ kết nối, **không bảo đảm exactly-once cho database ngoài Kafka**. Cần idempotency key, unique constraint, transactional outbox hoặc chiến lược phù hợp.

## 22. Security observability: theo dõi điều gì?

Một dashboard cho Spring Kafka production nên có tín hiệu kết nối và nghiệp vụ:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Authentication failures | Sai credential, mechanism, rotation hoặc broker login. |
| SSL handshake errors | Trust chain, hostname, cert expiry hoặc protocol. |
| Authorization exceptions | Principal thiếu quyền topic/group/transactional ID. |
| Consumer group lag | Consumer đang mất khả năng xử lý hoặc throughput thấp. |
| Consumer group member count | Có Pod thực sự join đúng group không? |
| Rebalance rate | Rollout, timeout hoặc consumer crash có làm group bất ổn không? |
| Producer send errors/timeouts | Broker ACK/ACL/connectivity/quotas có vấn đề. |
| DLT publish failures | Recovery path có đủ quyền và kết nối không? |
| Secret/certificate expiry | Có cần rotate trước hạn không? |
| Business throughput/idempotency failures | Record xử lý đúng hay đang duplicate/skip? |

**Không tự giả định HTTP health `200` nghĩa Kafka đã authenticated và consumer được assign partition.** Spring Boot có health indicators tùy dependency/cấu hình, nhưng không có một kiểm tra mặc định chứng minh toàn bộ consumer group và business output đúng.

### Log an toàn

Nên ghi những field hữu ích:

~~~text
service=secure-orders-worker
environment=production
clientId=orders-worker
groupId=orders-worker-v1
topic=orders.events.v1
authProtocol=SASL_SSL
errorCategory=authorization_failed
deploymentRevision=1.0.0
~~~

Không in:

~~~text
sasl.jaas.config
password
oauth access token
private key
keystore content
complete Spring Environment
HTTP Authorization header
full payload if it contains secrets or personal data
~~~

Nếu exception hoặc Kafka client debug logs chứa thông tin nhạy cảm, cấu hình log redaction và quyền đọc log backend phải được rà soát. Không bật debug logging lâu dài trên production chỉ để giải quyết một lỗi kết nối.

## 23. Chẩn đoán lỗi TLS

### 23.1. `SSLHandshakeException` hoặc `PKIX path building failed`

Nguyên nhân thường gặp:

- Truststore không chứa CA đã ký certificate broker.
- Certificate hết hạn hoặc chain không đầy đủ.
- Keystore/truststore không tải được vì path/password/type sai.
- Client trỏ tới cổng không phải TLS.
- JVM không hỗ trợ TLS version/cipher được broker yêu cầu.
- Proxy/SSL interception thay đổi certificate chain.

Quy trình:

1. Đọc **nhóm lỗi**, không in raw secret.
2. Xác nhận `security.protocol` và Kafka listener port.
3. Kiểm DNS và broker certificate chain bằng công cụ TLS được phê duyệt.
4. Kiểm truststore path/type/password **bằng kết quả load**, không cần in password.
5. Kiểm thời gian hệ thống và thời hạn certificate.
6. Kiểm các hostname trong SAN với broker endpoints được quảng bá.
7. Cập nhật truststore/certificate đúng, rollout và đo kết quả.

Không tắt TLS/hostname verification để làm test xanh.

### 23.2. Hostname verification failed

Nếu broker certificate chỉ có `broker-1.example.internal` nhưng client kết nối tới IP hoặc DNS alias khác không nằm trong SAN, handshake có thể bị từ chối.

**Khắc phục đúng:** sửa certificate SAN, DNS alias hoặc `advertised.listeners` sao cho endpoint khớp certificate. Tránh set `ssl.endpoint.identification.algorithm` thành rỗng.

### 23.3. Client cert không được chấp nhận

Với mTLS, cần kiểm:

- Broker đang yêu cầu client certificate chưa?
- Client keystore có private key + certificate chain đúng không?
- Client cert còn hạn và được broker trust không?
- Principal mapping dựa trên subject/SAN có thay đổi không?
- Principal sau mapping có Kafka ACL phù hợp không?

Có thể mTLS handshake thành công nhưng ACL lại fail nếu principal đổi sau certificate rotation.

## 24. Chẩn đoán lỗi SASL và ACL

| Triệu chứng | Lớp có khả năng lỗi | Gợi ý |
| --- | --- | --- |
| `SaslAuthenticationException` | Authentication | Username/password, mechanism, JAAS syntax, credential rotation. |
| Lỗi SSL trước SASL | TLS | Truststore, cert, hostname, protocol/port. |
| `TopicAuthorizationException` | Authorization Topic | Kafka ACL `Read`/`Write` theo principal và topic. |
| `GroupAuthorizationException` | Authorization Group | Group ID, ACL, không thay group bừa bãi. |
| `ClusterAuthorizationException` | Authorization Cluster | API yêu cầu quyền cluster; đánh giá tính cần thiết. |
| Transactional producer bị từ chối | TransactionalId/Topic ACL | Quyền, `transactional.id` và broker policy. |
| DLT publisher lỗi quyền | Authorization DLT | Principal producer có Write DLT không? |
| Reconnect liên tục | Network/TLS/Auth | DNS, bootstrap vs advertised listeners, cert/JAAS. |
| Consumer không có partition | Group assignment/Topic | Consumer count, partitions, group và subscription. |
| Consumer không nhận record | Offsets/Topic/Error handling | Không coi mọi vấn đề là security. |

### Phân biệt authentication và authorization

~~~text
Authentication:
    "Bạn là ai?"
    -> SASL challenge-response / mTLS client certificate

Authorization:
    "Danh tính này được phép làm gì?"
    -> Topic Read / Write, Group Read, TransactionalId, ...
~~~

Một principal đúng password nhưng thiếu ACL cần được cấp **đúng quyền thiếu** qua quy trình Kafka admin. Không “sửa” bằng cách tạo password khác, đổi topic, reset offset hoặc tắt TLS.

### Trường hợp broker không truy cập được từ Pod

Vấn đề có thể nằm ngoài security client. Kiểm:

~~~bash
# Từ môi trường có quyền kiểm kết nối:
nslookup broker-1.prod.example.internal

# Kiểm port từ một host thử nghiệm có quyền.
# Linux tùy distro có thể dùng:
nc -vz broker-1.prod.example.internal 9093
~~~

Hai lệnh chỉ giúp kiểm DNS/TCP, **không chứng minh SASL/TLS/ACL đúng**. Các lệnh probe mạnh hơn phải dùng client configuration an toàn, không truyền raw credential trong command line hoặc lưu vào shell history.

## 25. Kiểm thử security configuration

Mục tiêu là chứng minh:

- Property binding nhận đúng protocol, mechanism và topic.
- Production không khởi động thiếu secret/path bắt buộc.
- Client thật có thể thực hiện TLS và SASL handshake với broker test.
- Principal có **đúng quyền**, không nhiều hơn yêu cầu.
- Thay credential/cert theo runbook không làm consumer bỏ hoặc xử lý trùng record.
- Log/metric không chứa credential.

Tách các lớp kiểm thử thay vì chỉ có một test nặng.

### 25.1. Binding test với Spring Boot

Có thể viết một unit test cho namespace ứng dụng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.*;

class MessagingPropertiesBindingTest {

    @Test
    void bindsTopicsFromExternalConfiguration() {
        MockEnvironment env = new MockEnvironment()
                .withProperty(
                    "app.messaging.orders-topic", "orders.events.test")
                .withProperty(
                    "app.messaging.results-topic", "orders.results.test");

        MessagingProperties props = Binder.get(env)
                .bind(
                    "app.messaging",
                    Bindable.of(MessagingProperties.class))
                .orElseThrow();

        assertEquals("orders.events.test", props.ordersTopic());
        assertEquals("orders.results.test", props.resultsTopic());
    }
}
~~~

Test này chứng minh binding, **không** khởi tạo Kafka client và không thực hiện handshake. Để kiểm `@NotBlank`, dùng Spring context có validation được bật hoặc gọi `Validator` rõ ràng.

### 25.2. Bắt lỗi khi thiếu secret production

Dựng một Spring Boot test context cho profile prod nhưng cố tình không có `/etc/kafka-secrets/`. Vì:

~~~yaml
spring:
  config:
    import: "configtree:/etc/kafka-secrets/"
~~~

không có tiền tố `optional:`, việc thiếu thư mục bắt buộc phải làm startup fail. Đây là một kiểm tra configuration safety, không chứng minh credential bên trong là hợp lệ.

Nếu môi trường test không có đường dẫn này, dùng cơ chế test configtree riêng thay vì mount secret production vào máy developer.

### 25.3. Broker integration test có SASL/TLS thật

`@EmbeddedKafka` hoặc Kafka Testcontainers mặc định thường chạy **không bật SASL/TLS** theo cấu hình đơn giản. Test producer/consumer bằng PLAINTEXT chỉ chứng minh message flow và không chứng minh cấu hình security production đúng.

Một integration test security đúng cần:

1. Broker test có listener TLS/SASL cùng loại với production, với certificate test và credential test.
2. Principal test được provision và Kafka ACL tương ứng.
3. Spring context nhận bootstrap server, configtree/secret path qua profile test.
4. Producer kết nối, gửi record và chờ ACK.
5. Consumer đúng group nhận record và xử lý.
6. Negative test với password sai, CA sai, topic/group thiếu ACL.
7. Test không in credential vào logs hoặc test reports.

Có thể dùng Testcontainers với cấu hình Kafka broker bảo mật tùy image, hoặc một cluster staging/test dành riêng cho security integration. Đừng quảng cáo một container Kafka PLAINTEXT mặc định như bằng chứng đã test `SASL_SSL`.

### 25.4. Test negative scenarios

| Kịch bản | Kỳ vọng |
| --- | --- |
| Thiếu `KAFKA_BOOTSTRAP_SERVERS` ở prod | Context không sẵn sàng hoặc fail validation rõ ràng. |
| Thiếu thư mục `configtree` bắt buộc | Config import thất bại trước khi hệ thống hoạt động. |
| JAAS username/password sai | Authentication failure, không log raw secret. |
| Broker cert không đáng tin | TLS handshake thất bại. |
| SAN không khớp hostname | Hostname verification từ chối. |
| Consumer thiếu Topic Read | Topic authorization failure. |
| Consumer thiếu Group Read | Group authorization failure. |
| Producer thiếu Write | Publish thất bại, future thể hiện lỗi. |
| DLT producer thiếu quyền | Recoverer publish thất bại có cảnh báo. |
| Secret rotate, Pod mới dùng B | Kết nối tiếp tục; offsets và side effect được đối soát. |
| Principal cố đọc topic khác | Bị từ chối theo least privilege. |

Không thực hiện negative test security bằng credential production hoặc tác động ACL của cluster đang phục vụ nghiệp vụ.

## 26. Type-safe validation và fail-safe deployment

Một số điều kiện nên được kiểm **trước khi ứng dụng được nhận traffic**:

- Profile đúng môi trường; prod không chạy `PLAINTEXT` ngoài policy.
- `bootstrap-servers` không rỗng, không vô tình trỏ tới localhost.
- `sasl.mechanism` nhất quán với `security.protocol`.
- Topic/group ID có giá trị và đúng naming scheme.
- Required secret files tồn tại, có quyền đọc thích hợp.
- Certificate còn hạn và hostname đúng.
- Principal có quyền Kafka cần thiết, không phải admin rộng.
- `auto-offset-reset` và group ID có kế hoạch khi group mới.
- Producer không bị cấu hình trái với yêu cầu acks/idempotence.
- Không expose `/actuator/env` hoặc dump raw KafkaProperties.

`@ConfigurationProperties` với Bean Validation giúp bắt dữ liệu nghiệp vụ thiếu/sai. Một deployment preflight hoặc integration test cần bắt lỗi TLS/ACL. Đừng cho rằng bind xong YAML nghĩa là Kafka client đã authenticated.

### Kiểm security ở Kubernetes probes

Readiness probe thường chỉ biết application process có đáp ứng HTTP hay không. Một probe có thể báo Ready trong khi consumer chưa có partition hoặc producer không gửi được. Cần kết hợp readiness với signal về Kafka connectivity/group assignment **phù hợp nghiệp vụ**, tránh tạo vòng lặp restart liên tục khi broker tạm thời không sẵn sàng.

Liveness probe không nên đánh giá một authentication failure bằng cách kill/restart Pod vô tận: nếu secret hoặc ACL sai, restart không tự sửa root cause. Monitoring/alert cần cho thấy lỗi cấu hình và hướng xử lý.

## 27. Security không tự giải quyết xử lý trùng message

Ngay cả khi có TLS, SASL và ACL:

~~~text
Kafka partition: record offset 250
          |
          v
Consumer authenticated + authorized
          |
          v
Business DB commit thành công
          |
          X process chết trước offset commit
          |
          v
Record offset 250 được giao lại
          |
          v
Consumer mới xử lý lại
~~~

Phải dùng:

- Unique business key/idempotency key phù hợp.
- Transaction boundary rõ ràng.
- Transactional outbox hoặc chiến lược consistency khi produce sau DB commit.
- Retry/backoff/DLT theo nhóm lỗi.
- Audit các side effect quan trọng.
- Đối soát sau rotation/rolling deployments.

Kafka producer `enable.idempotence=true` không có nghĩa mọi request nghiệp vụ của consumer là exactly-once. Kafka transactions có phạm vi bảo đảm riêng; side effect ngoài Kafka transaction cần giải pháp nhất quán khác.

## 28. Runbook triển khai security Kafka

| Bước | Việc phải làm | Kết quả kỳ vọng |
| --- | --- | --- |
| 1 | Xác định cluster, environment và listener endpoint | Không trỏ nhầm staging/prod hoặc sai port. |
| 2 | Chốt auth mechanism: SCRAM, mTLS, OAuth/IAM | Client và broker hỗ trợ cùng protocol. |
| 3 | Provision principal/credential/cert trên hệ thống được phê duyệt | Không lưu raw secret vào Git/JAR. |
| 4 | Cấp ACL topic/group/transaction/DLT tối thiểu | Producer/consumer có đúng quyền cần thiết. |
| 5 | Cấu hình ConfigMap + secret mounts/configtree | `spring.kafka.*` nhận đúng values/paths. |
| 6 | Kiểm TLS chain và hostname | Không phải tắt hostname verification. |
| 7 | Thử ở staging/test broker có security tương đương | Positive và negative authentication/authorization tests. |
| 8 | Rollout dần | Theo dõi lag, rebalance, producer send errors. |
| 9 | Đối soát dữ liệu và audit | Không có duplicate/loss ngoài policy. |
| 10 | Thu hồi credential cũ sau cutover | Rotation hoàn tất, không gây outage. |
| 11 | Lưu runbook, cấu hình version và lịch cert expiry | Sẵn sàng lần rotation tiếp theo. |

### Ví dụ incident: TLS được nhưng Group ACL thiếu

~~~text
Time: sau deployment production
Spring application: STARTED
TLS: handshake thành công
SASL: authentication thành công
Kafka: GroupAuthorizationException
Consumer lag: tăng
Producer: không ảnh hưởng

Root cause:
  principal orders-consumer được phép Read Topic
  nhưng chưa được phép Read Group orders-worker-v1

Correct action:
  cấp Group Read đúng principal và group
  theo quy trình Kafka admin
  rollout/restart khi cần và xác nhận consumer join group
  đối soát offset + dữ liệu sau hồi phục

Wrong action:
  đổi group-id sang tên tùy ý
  tắt TLS
  cấp Cluster All để tránh lỗi
~~~

### Ví dụ incident: certificate hết hạn

~~~text
Time: broker certificate đã hết hiệu lực
Symptom: SSLHandshakeException ở các client mới
Cause: quy trình cert rotation không được thực hiện trước hạn

Response:
  xác nhận tình trạng cert/hostname/CA
  cấp cert hợp lệ đúng broker endpoints
  cập nhật broker/truststore theo rolling plan
  kiểm auth/ACL và dữ liệu sau phục hồi

Prevention:
  alert trước certificate expiry
  dual-trust/rotation runbook
  kiểm trong staging với cert mới
~~~

Cả hai tình huống cho thấy security failure cần được chẩn đoán ở **đúng tầng**, không nên giải quyết bằng một config override vội vàng làm suy yếu an toàn dữ liệu.

## 29. Những sai lầm thường gặp

**1. Production dùng `PLAINTEXT` vì local chạy được.** Dữ liệu và credential không có lớp TLS bảo vệ.

**2. Dùng `SASL_PLAINTEXT` trên mạng không tin cậy.** SASL không mã hóa toàn bộ traffic; cần TLS theo security policy.

**3. Nhầm truststore với keystore.** Truststore dùng xác minh bên kia; keystore có thể chứa private key/client certificate.

**4. Đặt raw password trong `application-prod.yml`.** Secret sẽ đi vào Git, artifacts, backups hoặc log.

**5. Base64 password trong ConfigMap/Secret manifest rồi coi là mã hóa.** Base64 không bảo vệ giá trị.

**6. Bỏ hostname verification khi TLS lỗi.** Làm suy yếu xác minh broker, che giấu DNS/certificate/config thực.

**7. SASL thành công rồi kết luận mọi thứ đúng.** Topic/Group ACL còn có thể từ chối.

**8. Cấp `All` trên Cluster cho ứng dụng chỉ đọc topic.** Vi phạm least privilege, tăng blast radius.

**9. Đổi consumer group ID để thoát lỗi Group ACL.** Có thể làm replay hoặc bỏ backlog.

**10. Cho rằng ConfigMap/Secret cập nhật là Kafka clients tự refresh.** Client thường cần restart/tái tạo để nhận credential mới.

**11. Gắn `sasl.jaas.config` chỉ cho consumer trong khi producer cũng cần gửi DLT.** Producer có thể không authenticate.

**12. Dùng `@EmbeddedKafka` PLAINTEXT để khẳng định SASL_SSL đã được test.** Cần secured broker test thật.

**13. In toàn bộ KafkaProperties hoặc debug log để tìm lỗi.** Có thể làm lộ JAAS password, token và private key.

**14. Coi TLS/SASL là exactly-once.** Authentication/encryption không tự giải quyết redelivery và DB side effects.

**15. Rotate credential và thu hồi bản cũ trước khi Pod mới sẵn sàng.** Có thể gây outage hàng loạt.

**16. Quên certificate SAN của advertised broker endpoints.** Bootstrap thành công nhưng các kết nối sau thất bại.

**17. Mở actuator endpoints công khai để monitoring.** Có thể tiết lộ config hoặc chi tiết hệ thống.

**18. Chỉ sửa client khi broker policy chưa hỗ trợ mechanism.** SCRAM/mTLS/OAuth luôn yêu cầu hai phía được cấu hình tương thích.

## 30. Bài tập thực hành

### Bài 1 — Phân biệt các giao thức

Vẽ sơ đồ `PLAINTEXT`, `SSL`, `SASL_PLAINTEXT`, `SASL_SSL`. Với mỗi giao thức, ghi rõ dữ liệu có TLS encryption không và cách broker xác thực client.

### Bài 2 — Chạy local và prod theo profile

Viết `application-local.yml` dùng Kafka test cách ly. Viết `application-prod.yml` dùng `SASL_SSL`, SCRAM và truststore từ secret file. Đảm bảo image không thay đổi giữa hai môi trường.

### Bài 3 — Secret qua configtree

Tạo secret **giả** trong thư mục test có file `kafka.sasl.jaas.config`. Kiểm Spring Boot bind đúng property và test không in giá trị credential ra log. Không dùng token/password thật trong fixture.

### Bài 4 — ACL tối thiểu

Thiết kế principal consumer được đọc topic `orders.events.v1`, dùng group `orders-worker-v1`, không được ghi vào topic. Principal producer chỉ được ghi `orders.results.v1`. Lập bảng quyền và các negative tests.

### Bài 5 — TLS handshake

Dùng broker test có TLS certificate, rồi thử truststore đúng/sai và hostname đúng/sai. Ghi lại loại lỗi. Không bỏ hostname verification để làm test xanh.

### Bài 6 — GroupAuthorizationException

Cấp Topic Read nhưng cố ý bỏ Group Read trên broker test. Quan sát consumer không join được group; bổ sung đúng ACL và xác minh xử lý record trở lại, không cần đổi group ID.

### Bài 7 — Rotation SCRAM

Tạo credential thử nghiệm A/B (trên broker test hỗ trợ). Roll Pod từ A sang B, đo consumer lag/rebalance và xác nhận dữ liệu không duplicate ngoài chính sách. Chỉ revoke A khi B đã hoạt động.

### Bài 8 — mTLS

Tạo client certificate/keystore và broker test yêu cầu client cert. Kiểm certificate hợp lệ và client cert không được broker trust; xác nhận lỗi đúng lớp và principal mapping phù hợp.

### Bài 9 — DLT security

Dùng `DefaultErrorHandler` và DLT publisher trên môi trường test. Cố ý thiếu quyền Write DLT, quan sát failure và alert; sau đó cấp đúng quyền. Kiểm log/error headers không chứa secret.

### Bài 10 — Security incident drill

Giả lập một JAAS password bị lộ trong log test. Lập kế hoạch thu hồi, rotation, log access, backup retention, rolling deploy và xác minh ACL. Không dùng credential production cho bài tập.

## 31. Tài liệu tham khảo chính thức

- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Kafka — Reference](https://docs.spring.io/spring-kafka/reference/)
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/)
- [Apache Kafka — Security](https://kafka.apache.org/documentation/#security)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

