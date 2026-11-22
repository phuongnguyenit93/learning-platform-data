# Externalized Kafka configuration trong Spring Kafka Reliability Operations

## 1. Bối cảnh: vì sao phải đưa cấu hình Kafka ra ngoài ứng dụng?

Một dịch vụ Spring Kafka có thể chạy cùng một phiên bản mã nguồn trên laptop, môi trường kiểm thử, staging và production. Nhưng mỗi môi trường có **bootstrap servers, topic, consumer group, phương thức xác thực, chứng chỉ TLS, mức concurrency và giới hạn xử lý** khác nhau. Nếu cố định những giá trị đó trong Java hoặc đóng gói bí mật trực tiếp vào JAR, việc triển khai dễ dẫn tới hai lỗi nguy hiểm:

- Bản build phục vụ staging tình cờ trỏ vào Kafka production hoặc đọc topic của tenant khác.
- Khi cần rotate credential hoặc đổi broker, nhóm vận hành phải sửa source/build lại image, trong khi secret cũ vẫn nằm trong Git, image layer và hệ thống CI.

**Externalized Kafka configuration** là thiết kế để **cùng một artifact ứng dụng** nhận cấu hình phù hợp từ môi trường triển khai, đồng thời duy trì ranh giới giữa cấu hình thông thường, bí mật bảo mật và chính sách reliability.

~~~text
                   ONE APPLICATION ARTIFACT
                  orders-worker:1.2.0
                           |
            +--------------+--------------+
            |              |              |
          LOCAL          STAGING          PROD
            |              |              |
       local config     ConfigMap        ConfigMap
       test broker      + Secret         + Secret
            |              |              |
            v              v              v
       localhost:9092  staging brokers   prod brokers
       PLAINTEXT        SASL_SSL          SASL_SSL
       test topics      test groups       prod groups
~~~

Trong *Spring Kafka Reliability Operations*, đây không chỉ là chủ đề cấu hình. Một giá trị sai có thể làm consumer **bỏ qua message**, **xử lý trùng**, gây **rebalance liên tục**, **mất khả năng kết nối** hoặc làm hỏng tính cô lập giữa các môi trường.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Tổ chức `application.yml`, profile, environment variables, ConfigMap và Secret rõ ràng.
2. Hiểu cách `spring.kafka.*` được Spring Boot chuyển thành cấu hình Kafka clients.
3. Tách topic/group-id nghiệp vụ vào `@ConfigurationProperties` có validation.
4. Đưa cấu hình SASL_SSL/TLS ra khỏi image và Git, dùng `configtree:` hoặc secret provider.
5. Nhận diện thay đổi cấu hình nào ảnh hưởng tới offset, phân vùng, idempotency và consumer group.
6. Thiết kế rollout, rotation và kiểm tra trước khi chuyển traffic production.
7. Kiểm thử configuration binding, kết nối broker và lỗi thiếu cấu hình.
8. Chẩn đoán sai broker, sai advertised listeners, ACL, TLS và lỗi profile.

Ví dụ chính sử dụng **Spring Boot 3.x, Spring Kafka 3.x, Java 17+**. Các nguyên tắc vẫn phù hợp với các dòng mới hơn, nhưng cần kiểm tên property và API theo BOM/Javadoc của phiên bản thực tế.

## 2. Những nhóm cấu hình cần tách biệt

Không nên gom mọi thứ vào một file cấu hình lớn hoặc một biến `KAFKA_CONFIG_JSON` duy nhất không được kiểm soát.

| Nhóm | Ví dụ | Nguồn khuyến nghị |
| --- | --- | --- |
| Kết nối | `bootstrap-servers`, DNS, cluster | ConfigMap, deployment variables, service discovery. |
| Consumer identity | `group-id`, `client-id` | Cấu hình theo workload/môi trường, có review thay đổi. |
| Producer reliability | `acks`, idempotence, delivery timeout | Base config được version control, override khi có lý do. |
| Consumer reliability | auto commit, ack mode, poll interval, concurrency | Base config + override vận hành có giới hạn. |
| Routing nghiệp vụ | input topic, DLT topic, audit topic | `app.messaging.*` có validation, ConfigMap. |
| Bảo mật | SASL mechanism, TLS protocol, certificate location | Protocol/method ở ConfigMap; key/password ở secret store. |
| Secret thực | password, JAAS credential, private key | Kubernetes Secret, Vault, cloud secret manager, mounted file. |
| Monitoring | client ID, metric tags, tracing | Base config và cấu hình quan sát. |
| Deployment | replica count, resources, rolling update | Kubernetes manifests/Helm/GitOps; không nhét vào Java code. |

**Quy tắc:** cấu hình chịu trách nhiệm *định tuyến và hành vi*, còn secret manager chịu trách nhiệm *giá trị xác thực*. Tên secret hoặc path cũng có thể nhạy cảm; cần đánh giá trước khi đưa vào log/dashboard.

## 3. Cấu hình Spring Boot được nạp như thế nào?

Spring Boot hỗ trợ **externalized configuration** từ nhiều nguồn: `application.yml`, `application-<profile>.yml`, file ngoài JAR, biến môi trường, Java system properties, command-line arguments, configuration trees và những nguồn Config Data tích hợp thêm.

Ví dụ một ứng dụng có cấu hình cơ sở trong JAR:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
~~~

Khi triển khai có thể cấp:

~~~bash
export KAFKA_BOOTSTRAP_SERVERS="kafka-1.example.internal:9093,kafka-2.example.internal:9093"
java -jar orders-worker.jar --spring.profiles.active=prod
~~~

Hoặc đưa biến môi trường vào manifest của Kubernetes. **Không cần rebuild JAR** khi đổi danh sách bootstrap servers.

### 3.1. Thứ tự ưu tiên

Về nguyên tắc, nguồn cấu hình có **độ ưu tiên cao hơn** sẽ override nguồn thấp hơn. Command-line options như `--spring.kafka.bootstrap-servers=...` thường có độ ưu tiên cao hơn các property lấy từ file. Environment variables cũng thường override giá trị trong file `application.yml` đóng gói.

Tuy nhiên, thứ tự đầy đủ còn có Config Data import, profile-specific documents, Java system properties và các nguồn khác. **Không tự đặt ra một bảng precedence đơn giản rồi xem nó luôn đúng**: dùng quy tắc trong tài liệu Spring Boot tương ứng phiên bản và kiểm kết quả binding thực tế.

~~~text
application.yml bên trong JAR
       |
       v
profile + external config + env + command line
       |
       v
       Spring Environment
       |
       +--> Spring Boot KafkaProperties
       |
       +--> @ConfigurationProperties(app.messaging)
       |
       v
Kafka ConsumerFactory / ProducerFactory / Listener
~~~

Các biến môi trường thường dùng kiểu uppercase underscore:

~~~text
spring.kafka.bootstrap-servers   -> SPRING_KAFKA_BOOTSTRAP_SERVERS
spring.kafka.consumer.group-id   -> SPRING_KAFKA_CONSUMER_GROUP_ID
spring.kafka.listener.concurrency -> SPRING_KAFKA_LISTENER_CONCURRENCY
~~~

Chú ý: `spring.kafka.properties` và `consumer.properties` là **Map chứa Kafka client properties có dấu chấm**. Việc thay `.` thành `_` một cách tùy ý có thể gây lỗi map key binding/normalization. Với Kafka keys như `max.poll.interval.ms` hoặc `sasl.jaas.config`, cách ít gây mơ hồ là **để key nguyên dạng trong YAML và lấy value bằng placeholder** từ môi trường/secret.

### 3.2. Placeholder và giá trị mặc định

~~~yaml
app:
  messaging:
    max-attempts: ${KAFKA_MAX_ATTEMPTS:3}
~~~

`${KAFKA_MAX_ATTEMPTS:3}` cho phép dùng giá trị mặc định 3. Với thông tin **bắt buộc** như bootstrap server production, topic, group hoặc security reference, không nên lạm dụng default giá trị local vì có thể khiến production kết nối nhầm cluster.

Ví dụ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
~~~

Nếu không có giá trị cần thiết, ứng dụng nên **fail sớm** thay vì tự trỏ về `localhost:9092` ngoài ý định.

## 4. Phân biệt `spring.kafka.*` và `app.messaging.*`

Spring Boot tự bind những property trong `spring.kafka.*` vào cấu hình Kafka clients. Ngược lại, `app.messaging.*` là **namespace do ứng dụng tự định nghĩa**, phục vụ tên topic, chính sách nghiệp vụ hoặc retry của hệ thống.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP}

app:
  messaging:
    input-topic: ${KAFKA_INPUT_TOPIC}
    dlt-topic: ${KAFKA_DLT_TOPIC}
~~~

Ở đây:

- `spring.kafka.consumer.group-id` là property Spring Boot Kafka hỗ trợ.
- `app.messaging.input-topic` **không** tự tạo topic hoặc auto-connect. Ứng dụng phải đọc property và dùng trong `@KafkaListener`/publisher.
- Cấu hình thuộc `app.messaging` có thể được validate bằng `@ConfigurationProperties`.
- Không nhầm tên topic trong ứng dụng với Kafka broker property hoặc topic-level configuration.

### Một số nhóm property Spring Boot

| Nhóm | Ví dụ |
| --- | --- |
| Common client | `spring.kafka.bootstrap-servers`, `spring.kafka.client-id`, `spring.kafka.properties.*` |
| Consumer | `spring.kafka.consumer.group-id`, `enable-auto-commit`, `auto-offset-reset`, `properties.*` |
| Producer | `spring.kafka.producer.acks`, `key-serializer`, `value-serializer`, `properties.*` |
| Listener | `spring.kafka.listener.ack-mode`, `concurrency`, `type` |
| SSL | `spring.kafka.ssl.*` hoặc Kafka client SSL properties phù hợp |
| Admin | `spring.kafka.admin.*` |
| Template/Streams | Các nhóm property riêng nếu dự án dùng KafkaTemplate hoặc Kafka Streams |

Các property client-level được đặt trong `spring.kafka.properties` có thể được dùng làm cấu hình chung. `spring.kafka.consumer.properties` và `spring.kafka.producer.properties` cho phép override riêng cho từng loại client theo cách Spring Boot build client configs.

## 5. Cấu trúc dự án thực hành

~~~text
orders-worker/
├── build.gradle
└── src/main/
    ├── java/com/example/orders/
    │   ├── OrdersWorkerApplication.java
    │   ├── MessagingProperties.java
    │   ├── OrderConsumer.java
    │   └── AuditPublisher.java
    └── resources/
        ├── application.yml
        ├── application-local.yml
        └── application-prod.yml

deployment/
├── orders-configmap.yaml
└── orders-deployment.yaml
~~~

Tất cả file cấu hình trong Git chỉ chứa **các giá trị công khai hoặc placeholder**, không chứa SASL password, access token hay private key thật.

### 5.1. Dependencies

Ví dụ Gradle cho Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
}
~~~

Giữ các version Spring Boot, Spring Kafka và Kafka client trong hệ thống dependency management/BOM tương thích. Tên module Testcontainers Kafka và API container thay đổi giữa một số dòng 1.x và 2.x, nên test mẫu phía dưới ghi rõ ngữ cảnh phiên bản.

## 6. Tạo `application.yml` làm cấu hình cơ sở

File `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: orders-worker

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    client-id: ${KAFKA_CLIENT_ID:orders-worker}

    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP}
      enable-auto-commit: false
      auto-offset-reset: ${KAFKA_AUTO_OFFSET_RESET:none}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        max.poll.records: ${KAFKA_MAX_POLL_RECORDS:100}
        max.poll.interval.ms: ${KAFKA_MAX_POLL_INTERVAL_MS:300000}

    listener:
      ack-mode: record
      concurrency: ${KAFKA_LISTENER_CONCURRENCY:2}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000

app:
  messaging:
    input-topic: ${KAFKA_INPUT_TOPIC}
    dlt-topic: ${KAFKA_DLT_TOPIC}
~~~

Ví dụ dùng `String` để tập trung vào externalized config. Nếu ứng dụng dùng JSON/Avro/Protobuf, serializer/deserializer và Schema Registry cũng phải được cấu hình, kiểm tương thích và xử lý lỗi deserialize.

### 6.1. Các lựa chọn reliability trong ví dụ

**`enable-auto-commit: false`**: ứng dụng để Spring Kafka container quản lý commit offset theo acknowledgment mode thay vì Kafka client auto-commit định kỳ.

**`ack-mode: record`**: đối với record listener thông thường, container có thể commit offset sau khi record được listener xử lý thành công, theo semantics thực tế của container/error handler. Điều này không tự tạo transaction giữa Kafka và database ngoài.

**`auto-offset-reset: none`**: nếu group chưa có committed offset hợp lệ, consumer sẽ không âm thầm bắt đầu ở `earliest` hoặc `latest`; nó phát lỗi cần được xử lý có chủ đích. Đây là chính sách **fail-fast minh họa**, không phải giá trị đúng cho mọi hệ thống. Nếu nghiệp vụ chấp nhận replay từ đầu, dùng `earliest`; nếu chỉ nhận event mới, `latest` có thể phù hợp nhưng phải hiểu rủi ro bỏ qua backlog.

**`max.poll.records`**: hạn chế số record nhận trong một lần poll. Nó không tự bảo đảm thời gian xử lý của listener.

**`max.poll.interval.ms`**: giới hạn thời gian giữa các lần poll cho consumer group. Nếu xử lý quá lâu, consumer có thể mất membership và gây rebalance. Cần cân bằng với batch size, độ trễ downstream, heartbeat và cơ chế pause/retry.

**`concurrency`**: số consumer thread container yêu cầu. Nếu tổng consumer thread của mọi replica lớn hơn số partition đang phân phối cho group, một số thread sẽ rỗi. Ví dụ 3 pod x concurrency 2 = 6 consumer; topic chỉ có 4 partition thì không phải mọi consumer đều có partition.

**`acks: all` và `enable.idempotence: true`**: tăng độ an toàn khi producer gửi lại request trong cùng phiên producer và với broker cấu hình phù hợp. Chúng **không bảo đảm exactly-once khi consumer ghi ra database, gọi HTTP hoặc khi app tự gửi cùng business event nhiều lần**.

## 7. `application-local.yml`: profile local không có credential production

File `src/main/resources/application-local.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP:orders-worker-local}
      auto-offset-reset: earliest
    properties:
      security.protocol: PLAINTEXT

app:
  messaging:
    input-topic: ${KAFKA_INPUT_TOPIC:orders.events.local}
    dlt-topic: ${KAFKA_DLT_TOPIC:orders.events.local.DLT}
~~~

Chạy local với profile:

~~~bash
java -jar orders-worker.jar --spring.profiles.active=local
~~~

Hoặc:

~~~bash
export SPRING_PROFILES_ACTIVE=local
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
java -jar orders-worker.jar
~~~

Các giá trị mặc định `localhost`, `PLAINTEXT` và `earliest` chỉ hợp lý trong **môi trường phát triển cách ly**. Không dùng profile local làm fallback tự động cho production.

Lưu ý: `localhost` bên trong container Docker hoặc Kubernetes nghĩa là chính container/Pod đó, **không phải máy host hoặc broker khác**. Với Docker Compose, cần hostname service trong network Compose; với Kubernetes, cần DNS/service endpoint phù hợp.

## 8. `application-prod.yml`: cấu hình bảo mật và fail-fast

File `src/main/resources/application-prod.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/etc/kafka-secrets/"

  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: ${kafka.jaas.config}

    ssl:
      trust-store-location: ${KAFKA_TRUSTSTORE_LOCATION:file:/etc/kafka-certs/truststore.p12}
      trust-store-type: PKCS12
      trust-store-password: ${kafka.truststore.password}
~~~

Những thông số có ý nghĩa khác nhau:

| Property | Chức năng |
| --- | --- |
| `security.protocol=SASL_SSL` | Kết nối TLS kèm xác thực SASL. |
| `sasl.mechanism=SCRAM-SHA-512` | Cơ chế xác thực Kafka client/broker đã thỏa thuận. |
| `sasl.jaas.config` | Thông tin đăng nhập cho SASL; **chứa secret**, không commit vào Git. |
| `trust-store-location` | Vị trí truststore dùng xác minh certificate broker. |
| `trust-store-type=PKCS12` | Kiểu truststore trong ví dụ. |
| `trust-store-password` | Mật khẩu mở truststore nếu có; lấy từ secret. |

Đây là **ví dụ cho cụm Kafka dùng SCRAM-SHA-512 và TLS**, không áp dụng nguyên trạng cho tất cả managed Kafka. Cụm dùng mTLS, OAuthBearer, IAM authentication hoặc cơ chế khác cần config/security provider tương ứng.

Đường dẫn `configtree:/etc/kafka-secrets/` **không có tiền tố `optional:`**, để nếu thư mục secret bắt buộc không tồn tại thì ứng dụng không lặng lẽ khởi động thiếu credential. Thư mục và tên file phải đúng với mount trong deployment.

### 8.1. Cấu trúc file của config tree

Sau khi secret được mount vào Pod, có thể thấy:

~~~text
/etc/kafka-secrets/
    kafka.jaas.config
    kafka.truststore.password

/etc/kafka-certs/
    truststore.p12
~~~

Mỗi **tên file** trong config tree tương ứng với một property key; nội dung file là property value. Vì vậy file `kafka.jaas.config` được tham chiếu qua `${kafka.jaas.config}` trong YAML.

Ví dụ định dạng nội dung của file JAAS, **không phải credential thật**:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required username="example-user" password="REPLACE-WITH-SECRET";
~~~

Không lưu nội dung thực tế này trong repository hoặc log. Một hệ thống cấp secret ngoài Git, ví dụ External Secrets Operator, Vault CSI driver, cloud secret manager hoặc cơ chế provisioning được bảo vệ, sẽ cung cấp file thực cho Pod.

### 8.2. Vì sao chọn secret file thay cho env variable?

Environment variable cũng có thể externalize credential, ví dụ một placeholder `${KAFKA_SASL_JAAS_CONFIG}`. Tuy nhiên:

- Biến môi trường có thể xuất hiện trong process diagnostics, dump, một số tooling và quyền truy cập container không đúng.
- Trên Kubernetes, secret được inject vào environment **không tự cập nhật trong process đang chạy** khi Secret resource thay đổi.
- Mount file có thể dễ kiểm permission/rotation hơn, nhưng **Kafka client không tự động đọc lại mọi credential chỉ vì file hoặc Config Data property thay đổi**.

Mô hình file không loại bỏ mọi rủi ro; secret vẫn đi vào Java memory và Kafka configuration khi client khởi tạo. Cần bảo vệ quyền truy cập Pod, API Kubernetes/etcd, log, backup và cơ chế rolling restart.

## 9. Kubernetes: ConfigMap cho non-secret, Secret cho credential

Một triển khai production thường phân chia rõ:

~~~text
Git / GitOps
   |
   +-- ConfigMap
   |    KAFKA_BOOTSTRAP_SERVERS
   |    KAFKA_CONSUMER_GROUP
   |    KAFKA_INPUT_TOPIC
   |    KAFKA_DLT_TOPIC
   |    KAFKA_LISTENER_CONCURRENCY
   |
   +-- Deployment
        image, replicas, resources, probes
              |
              v
             Pod
              |
              +-- envFrom(ConfigMap)
              |
              +-- volumeMount(Secret files)
                        |
                        v
             Spring Boot configtree
                        |
                        v
                  Kafka clients
~~~

### 9.1. ConfigMap

File `deployment/orders-configmap.yaml`:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-kafka-settings
data:
  KAFKA_BOOTSTRAP_SERVERS: "kafka-1.prod.example.internal:9093,kafka-2.prod.example.internal:9093"
  KAFKA_CONSUMER_GROUP: "orders-worker-v1"
  KAFKA_CLIENT_ID: "orders-worker"
  KAFKA_INPUT_TOPIC: "orders.events.v1"
  KAFKA_DLT_TOPIC: "orders.events.v1.DLT"
  KAFKA_LISTENER_CONCURRENCY: "2"
  KAFKA_MAX_POLL_RECORDS: "100"
  KAFKA_MAX_POLL_INTERVAL_MS: "300000"
  KAFKA_AUTO_OFFSET_RESET: "none"
~~~

Những host, topic và group ở đây là **tên minh họa**; khi chạy thực tế phải thay bằng giá trị được quản lý cho môi trường tương ứng.

ConfigMap **không phải secret store**. Không đặt password, bearer token hoặc PEM private key trong ConfigMap.

### 9.2. Deployment

File `deployment/orders-deployment.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-worker
  template:
    metadata:
      labels:
        app: orders-worker
    spec:
      containers:
        - name: app
          image: registry.example.org/orders-worker:1.2.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
          envFrom:
            - configMapRef:
                name: orders-kafka-settings
          volumeMounts:
            - name: kafka-credentials
              mountPath: /etc/kafka-secrets
              readOnly: true
            - name: kafka-certs
              mountPath: /etc/kafka-certs
              readOnly: true
      volumes:
        - name: kafka-credentials
          secret:
            secretName: orders-kafka-auth
            items:
              - key: jaas-config
                path: kafka.jaas.config
              - key: truststore-password
                path: kafka.truststore.password
        - name: kafka-certs
          secret:
            secretName: orders-kafka-truststore
            items:
              - key: truststore.p12
                path: truststore.p12
~~~

Đây là **manifest minh họa**; trước khi dùng production cần bổ sung resource requests/limits, health probes, rollout strategy, service account/Pod security và các chính sách cluster liên quan.

Hai Secret `orders-kafka-auth` và `orders-kafka-truststore` phải được provisioning qua quy trình bảo mật riêng. **Không commit manifest Secret chứa giá trị thật**, kể cả khi giá trị ở dạng Base64: Base64 chỉ là encoding, không phải mã hóa.

### 9.3. Những điều Kubernetes không tự làm

- Sửa ConfigMap không có nghĩa mọi Kafka consumer đang chạy được cấu hình lại ngay.
- Volume Secret có thể được cập nhật theo cơ chế kubelet, nhưng Java/Kafka clients đang hoạt động thường phải được **tái khởi tạo hoặc rollout** để dùng credential mới.
- Các biến môi trường được inject lúc Pod tạo không tự cập nhật giá trị khi ConfigMap/Secret đổi.
- Thay `group-id` không tương đương với rolling restart đơn thuần: nó thay **consumer group identity** và có thể làm đọc lại hoặc bỏ qua dữ liệu.
- `replicas` x `listener.concurrency` là số consumer thread dự kiến, phải cân nhắc số partition và khả năng xử lý downstream.

**Không dùng `kubectl describe`/log hoặc debug endpoint để in raw secret.** Trong điều tra, ưu tiên metadata, tên reference, trạng thái mount và kiểm quyền thay vì dump nội dung.

## 10. Externalized configuration trên VM hoặc Docker Compose

Không phải mọi ứng dụng đều chạy Kubernetes.

### 10.1. VM / systemd

Có thể dùng file cấu hình nằm ngoài JAR:

~~~bash
java -jar orders-worker.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/orders-worker/
~~~

Ví dụ `/etc/orders-worker/application-prod.yml` chỉ chứa cấu hình không bí mật và reference. Giá trị credential vẫn lấy từ secret store hoặc file được bảo vệ phù hợp.

Không đặt password trực tiếp trong command-line arguments: giá trị có thể bị nhìn thấy trong process listing, shell history và CI logs.

### 10.2. Docker Compose local

~~~yaml
services:
  orders-worker:
    image: registry.example.org/orders-worker:1.2.0
    environment:
      SPRING_PROFILES_ACTIVE: local
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      KAFKA_CONSUMER_GROUP: orders-worker-local
      KAFKA_INPUT_TOPIC: orders.events.local
      KAFKA_DLT_TOPIC: orders.events.local.DLT
    depends_on:
      - kafka
~~~

`kafka` phải là service DNS hợp lệ trong Compose network; ví dụ không triển khai broker cụ thể ở đây.

Nếu sử dụng `.env` trong phát triển, thêm file chứa bí mật vào `.gitignore`, nhưng **gitignore không bảo vệ dữ liệu đã từng commit**. Nếu secret bị lộ, cần revoke/rotate và xử lý lịch sử theo chính sách.

## 11. Type-safe configuration cho topic và nghiệp vụ

Đọc topic bằng `@Value("${...}")` rải rác trong nhiều class dễ gây typo và khó validate. Dùng `@ConfigurationProperties` cho **namespace ứng dụng**:

~~~java
package com.example.orders;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.messaging")
public record MessagingProperties(
        @NotBlank String inputTopic,
        @NotBlank String dltTopic) {
}
~~~

Trong class khởi động:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersWorkerApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` phát hiện record properties; `spring-boot-starter-validation` cho phép kiểm `@NotBlank` khi binding.

### Sử dụng trong listener

~~~java
package com.example.orders;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @KafkaListener(topics = "${app.messaging.input-topic}")
    public void consume(String payload) {
        // Parse + validate + thực hiện nghiệp vụ idempotent.
        // Khi xử lý lỗi: ném exception để error handler áp policy.
    }
}
~~~

### Sử dụng trong publisher

~~~java
package com.example.orders;

import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class AuditPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final MessagingProperties properties;

    public AuditPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            MessagingProperties properties) {
        this.kafkaTemplate = kafkaTemplate;
        this.properties = properties;
    }

    public CompletableFuture<SendResult<String, String>> publishAudit(
            String businessKey, String payload) {
        // Ví dụ minh họa: có thể đổi thành một topic audit riêng.
        return kafkaTemplate.send(
                properties.dltTopic(), businessKey, payload);
    }
}
~~~

Ở đây tên method `publishAudit` chỉ minh họa cơ chế sử dụng configuration property; trong dự án thực, **không dùng DLT làm audit topic**. Hãy định nghĩa property riêng `audit-topic` nếu cần xuất sự kiện audit. DLT dành cho các record không xử lý được theo error-handling policy.

Trả về `CompletableFuture` không có nghĩa broker đã ACK tại thời điểm method return. Caller phải xử lý completion/failure đúng, nhất là khi thông điệp quan trọng cần outbox hoặc transaction.

## 12. Cấu hình Kafka client-level và override đúng chỗ

Một điểm dễ gây lỗi là đặt property vào sai nhánh.

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL

    consumer:
      properties:
        max.poll.interval.ms: 300000
        fetch.min.bytes: 1

    producer:
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
~~~

| Vị trí | Ảnh hưởng |
| --- | --- |
| `spring.kafka.properties.*` | Property chung cho Kafka client factories khi được áp dụng. |
| `spring.kafka.consumer.properties.*` | Property riêng của consumer, có thể override giá trị chung cùng key. |
| `spring.kafka.producer.properties.*` | Property riêng của producer. |
| `spring.kafka.listener.*` | Container/acknowledgment behavior do Spring Kafka quản lý. |
| `app.messaging.*` | Property ứng dụng tự quản lý, không tự truyền vào Kafka clients. |

Không xem mọi Kafka client config đều có Boot typed shortcut. Các khóa Kafka client cụ thể như `max.poll.interval.ms`, `request.timeout.ms`, `sasl.jaas.config` có thể được truyền qua `properties` Map.

**Quan trọng:** key có dấu chấm nằm nguyên trong YAML Map; tránh “biến đổi” khóa thành chuỗi env không được bind như mong muốn. Nếu muốn override, tốt nhất cấp giá trị env vào placeholder tương ứng và xác minh property cuối cùng tại một test.

## 13. Những cấu hình tác động trực tiếp đến reliability

Cấu hình Kafka có thể externalize, nhưng thay đổi một số giá trị đòi hỏi **quy trình vận hành** chứ không chỉ `kubectl apply`.

| Property | Nếu thay đổi sai sẽ ra sao? | Cách quyết định |
| --- | --- | --- |
| Bootstrap servers | Không kết nối được hoặc kết nối nhầm cluster | Quản lý endpoint theo environment; xác minh DNS/TLS. |
| Consumer group ID | Có thể replay dữ liệu hoặc bỏ qua backlog theo offset-reset | Xem như thay đổi data-processing identity, cần kế hoạch migration. |
| `auto.offset.reset` | `earliest` có thể replay lớn; `latest` có thể bỏ record cũ | Chọn theo hợp đồng dữ liệu, không dùng như bản vá sự cố. |
| `enable.auto.commit` | Tăng rủi ro commit trước khi xử lý xong nếu cấu hình sai | Xác định rõ ack strategy và error handler. |
| Ack mode | Thời điểm commit offset khác nhau | Test lỗi, retry, rebalance và side effect. |
| Listener concurrency | Tạo thêm consumer threads, load và rebalances | Cân bằng partition count, replicas, database capacity. |
| `max.poll.records` | Một poll quá nhiều record làm xử lý lâu | Benchmark latency và batch size. |
| `max.poll.interval.ms` | Quá ngắn gây rebalance khi xử lý chậm | Đo p99 processing time và recovery. |
| Producer `acks` | `acks=0/1` có failure window khác `all` | Theo yêu cầu durability; hiểu broker `min.insync.replicas`. |
| Producer idempotence | Cấu hình xung đột có thể làm client không khởi động | Dùng `acks=all`, retry và in-flight tương thích. |
| Delivery/request timeouts | Quá ngắn gây fail hoặc duplicate retry ở tầng app | Cân bằng với SLA, broker/network latency. |
| SASL/TLS | Auth, handshake hoặc trust verification thất bại | Đồng bộ với broker policy và certificate chain. |
| Topic name | Consumer đọc nhầm topic hoặc DLT không tồn tại | Review IaC/ACL và kiểm sự tồn tại của topic. |

### 13.1. Không phải cứ `acks=all` là exactly-once

`acks=all` yêu cầu broker ACK theo điều kiện ISR hiện hành. Producer idempotence giúp hạn chế duplicate do retry trong phạm vi producer session phù hợp. Nhưng nếu consumer ghi database rồi crash **trước khi offset commit**, message có thể được giao lại.

~~~text
Kafka record #42
      |
      v
Consumer xử lý -> DB COMMIT thành công
      |
   process crash
      |
   offset CHƯA COMMIT
      |
      v
Kafka redelivery -> xử lý lại record #42
~~~

Giải pháp nằm ở thiết kế transaction/outbox hoặc idempotency nghiệp vụ (ví dụ unique key theo event ID), **không chỉ ở một property YAML**. Kafka transactions và Spring Kafka Exactly Once Semantics có điều kiện và phạm vi riêng; không tự bao gồm database ngoài Kafka transaction.

### 13.2. Consumer group thay đổi là thay đổi về dữ liệu

Nếu đổi:

~~~text
KAFKA_CONSUMER_GROUP=orders-worker-v1
```

thành:

~~~text
KAFKA_CONSUMER_GROUP=orders-worker-v2
~~~

thì group mới có tập committed offsets khác. Với `earliest`, nó có thể replay backlog lớn; với `latest`, có thể bỏ các record đã tồn tại trước khi group mới tham gia. Với `none`, consumer có thể phát lỗi nếu chưa có offset. **Không đổi group ID chỉ để xóa lỗi lag hoặc làm rollout nhanh hơn.**

## 14. Config validation và fail-fast

Ngoài validation của `MessagingProperties`, nên có một số bảo vệ:

1. Không chấp nhận bootstrap servers trống hoặc default `localhost` ngoài profile local.
2. Không cho prod chạy `PLAINTEXT` trừ khi policy bảo mật thực sự cho phép một cấu hình tương đương và đã được phê duyệt.
3. Topic và group phải khác rỗng, đúng naming convention.
4. Concurrency phải là số dương và có giới hạn theo capacity.
5. Các secret file/configtree bắt buộc phải tồn tại trước khi tạo Kafka clients.
6. Kiểm kiểu dữ liệu (ví dụ số nguyên milliseconds) và miền giá trị.
7. Kiểm certificate trust chain/hostname và ACL theo cluster.
8. Không xuất raw secret vào log lỗi validation.

**Cần phân biệt cấu hình được bind thành công và kết nối Kafka thực sự hoạt động.** Ứng dụng có thể khởi động được nhưng listener không join được group vì sai ACL hoặc DNS; startup validation của Spring không tự thay thế phép thử Kafka client.

### Ví dụ validation riêng cho profile production

Có thể xây một `ApplicationRunner` kiểm các property an toàn:

~~~java
@Bean
ApplicationRunner validateKafkaDeployment(
        Environment environment,
        MessagingProperties messaging) {

    return args -> {
        if (environment.acceptsProfiles(Profiles.of("prod"))) {
            String brokers = environment.getRequiredProperty(
                    "spring.kafka.bootstrap-servers");
            String protocol = environment.getRequiredProperty(
                    "spring.kafka.properties.security.protocol");

            if (brokers.isBlank()) {
                throw new IllegalStateException(
                        "Kafka bootstrap servers are missing");
            }
            if (!"SASL_SSL".equals(protocol)) {
                throw new IllegalStateException(
                        "Production Kafka must use SASL_SSL");
            }
        }
    };
}
~~~

Đây là **policy minh họa** của tổ chức chỉ dùng SCRAM/TLS. Một hệ thống dùng `SSL` với mTLS hoặc cơ chế bảo mật khác phải thay kiểm tra cho phù hợp, không copy policy này theo nghĩa phổ quát.

`ApplicationRunner` có thể chạy sau khi một số bean Kafka đã được tạo; nếu cần chặn **trước** mọi Kafka client/listener được khởi động, hãy đặt kiểm tra ở configuration binding/bean construction hoặc deployment admission, rồi chứng minh qua test. Đừng dựa riêng vào `ApplicationRunner` cho ranh giới fail-fast nghiêm ngặt.

## 15. Quản lý topic và ACL ngoài ứng dụng

Tên topic là config, nhưng **việc tạo topic**, số partition, replication factor, retention và ACL phải được quản lý có chủ đích.

~~~text
Application configuration:
    input-topic=orders.events.v1
    group-id=orders-worker-v1
    dlt-topic=orders.events.v1.DLT

Kafka infrastructure:
    topic exists?
    partition count?
    replication factor?
    min.insync.replicas?
    retention.ms?
    ACL: read topic + read group?
    producer ACL to DLT?
~~~

Trong một số môi trường Spring Boot/Spring Kafka có thể dùng `NewTopic` bean hoặc KafkaAdmin để tạo topic. Nhưng với production cần phân quyền rõ, việc tự động tạo topic khi khởi động app có thể che giấu sai tên topic hoặc khiến schema/partition khác mong đợi.

Thực hành thường dùng Terraform, Strimzi, GitOps operator hoặc nền tảng Kafka admin chuyên trách để tạo topic và ACL. Ứng dụng chỉ cần xác nhận topic và quyền phù hợp với nhu cầu.

### Đừng đặt DLT mà không có recovery policy

Chỉ externalize `KAFKA_DLT_TOPIC` **không** tự khiến mọi record lỗi được chuyển DLT. Ứng dụng phải cấu hình error handler/recoverer hoặc non-blocking retry theo Spring Kafka, cân nhắc retry budget, header, serialization và poison messages.

Ví dụ `DefaultErrorHandler`, backoff và `DeadLetterPublishingRecoverer` là phần **error-handling code** riêng. Khi muốn thay retry policy bằng config, bind policy vào một `@ConfigurationProperties` riêng và khởi tạo handler rõ ràng. Không xem một property topic đã đủ triển khai reliability.

## 16. Khi thay cấu hình runtime, chuyện gì thực sự xảy ra?

Các giá trị được Spring Boot nạp vào `Environment` rồi bind khi khởi tạo bean. Kafka producer/consumer có internal configuration của chính client khi nó được tạo.

Do đó:

- Sửa ConfigMap trong cluster **không tự bảo đảm** consumer đang chạy đổi group/topic hoặc poll timeout ngay.
- Sửa Secret volume có thể cập nhật file, nhưng JAAS config đã được client nạp có thể vẫn là giá trị cũ.
- Đổi `spring.kafka.consumer.group-id` ở ConfigMap nhưng không rollout Pod có thể tạo trạng thái **các Pod khác group ID** trong giai đoạn chuyển tiếp.
- Việc bật một cơ chế dynamic refresh cần hiểu khả năng tái tạo listener containers, producer factories và secret references; không nên mặc định có hot reload.

**Cách dễ dự đoán hơn là rolling restart/deployment mới sau khi thay config**, theo thứ tự phù hợp và với monitoring.

### Kế hoạch rolling change

1. Xác định property cần đổi và tác động đến delivery/offset.
2. Lưu phiên bản cấu hình, xác nhận thay đổi được review.
3. Thử tại môi trường staging có cấu hình auth/protocol tương đồng.
4. Cập nhật ConfigMap/Secret bằng công cụ quản lý được phê duyệt.
5. Trigger rolling update của Deployment để Pod mới nạp cấu hình.
6. Theo dõi consumer group membership, lag, rebalance, error rate và producer errors.
7. Xác minh output/idempotency khi có retry/redelivery.
8. Nếu lỗi, rollback **cấu hình và workload** theo kế hoạch; không reset offset bừa bãi.

Nếu thay group ID, topic nguồn, serialization hoặc offset policy, đó là **data migration decision**, cần cutover plan và chứng cứ đối soát, không chỉ một rolling deployment.

## 17. Rotate secret Kafka mà không làm ngừng dịch vụ dài

Trong production, password hoặc certificate cần rotate định kỳ hoặc khẩn cấp.

Một quy trình an toàn phụ thuộc khả năng broker hỗ trợ **nhiều credential còn hiệu lực trong một khoảng chuyển tiếp**:

~~~text
T0: Kafka broker chấp nhận credential A
T1: Tạo credential B và cấp quyền tương đương đã kiểm
T2: Secret manager cung cấp B cho Pod mới
T3: Rolling update: Pod mới kết nối bằng B
T4: Xác nhận tất cả Pod cũ đã ngừng dùng A
T5: Thu hồi A; kiểm kết nối và lỗi auth
~~~

Nếu broker không cho cùng lúc A/B hoặc cert cũ/mới, phải thiết kế maintenance window hoặc chiến lược rotation khác phù hợp.

Cần lưu ý:

- Pod mới nạp secret B; Pod cũ thường vẫn dùng credential A cho đến khi được tái khởi tạo.
- Certificate TLS đổi CA/hostname có thể cần cập nhật truststore trước server-side rotation.
- Không log JAAS string, password hoặc private key trong lúc debug.
- Không dựa vào readiness probe đơn giản để kết luận consumer đã join group và xử lý đúng topic.
- Theo dõi authentication errors, consumer lag và unavailable time trong quá trình rollout.

## 18. Thử nghiệm property binding trước khi kết nối broker

Tách test cấu hình ra khỏi test có Kafka thật để phát hiện typo nhanh.

Ví dụ test cho `@ConfigurationProperties` dùng Spring Boot Binder:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.*;

class MessagingPropertiesBindingTest {

    @Test
    void bindsTopicNamesFromEnvironment() {
        MockEnvironment env = new MockEnvironment()
                .withProperty(
                        "app.messaging.input-topic",
                        "orders.events.test")
                .withProperty(
                        "app.messaging.dlt-topic",
                        "orders.events.test.DLT");

        MessagingProperties props = Binder.get(env)
                .bind(
                    "app.messaging",
                    Bindable.of(MessagingProperties.class))
                .orElseThrow();

        assertEquals("orders.events.test", props.inputTopic());
        assertEquals("orders.events.test.DLT", props.dltTopic());
    }
}
~~~

Bài test này chỉ chứng minh binding, **không** chạy validation container và **không** kết nối Kafka. Để kiểm `@NotBlank`, hãy dùng Spring Boot application context có validation active hoặc kiểm `Validator` rõ ràng.

### Test fail-fast khi thiếu property

Trong test context riêng cho profile `prod`, cố ý **không cấp** `KAFKA_BOOTSTRAP_SERVERS`, topic hoặc secret files bắt buộc. Kỳ vọng app không khởi chạy listener sẵn sàng; tùy wiring, nguyên nhân có thể là unresolved placeholder, config location not found, validation failure hoặc Kafka client initialization failure.

Đừng tạo default `localhost:9092` cho prod chỉ để test khởi động xanh. Test này bảo vệ bạn khỏi việc triển khai một Pod “Ready” nhưng kết nối nhầm broker.

## 19. Integration test với Kafka thật bằng Testcontainers

Cần có một bài test tạo broker Kafka thật trong container để kiểm cấu hình, producer/consumer và offset.

Với **Testcontainers 1.x** tương thích image được chọn, một mẫu khung:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.springframework.boot.autoconfigure.kafka.KafkaProperties;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest(properties = {
    "spring.kafka.consumer.group-id=orders-worker-it"
})
@ActiveProfiles("local")
class KafkaConfigIT {

    @Container
    static KafkaContainer kafka = new KafkaContainer(
            DockerImageName.parse(
                "confluentinc/cp-kafka:7.6.1"));

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers);
        registry.add(
            "app.messaging.input-topic",
            () -> "orders.events.test");
        registry.add(
            "app.messaging.dlt-topic",
            () -> "orders.events.test.DLT");
    }

    @Autowired KafkaProperties kafkaProperties;
    @Autowired MessagingProperties messaging;

    @Test
    void bindsTestBrokerAndTopics() {
        assertTrue(kafkaProperties.getBootstrapServers()
                .contains(kafka.getBootstrapServers()));
        assertEquals(
            "orders.events.test", messaging.inputTopic());
    }
}
~~~

Đây là bài test **binding trong context có broker container**. Để kiểm end-to-end, hãy tạo topic đúng cách, gửi record bằng `KafkaTemplate`, đợi listener nhận và xác minh state đích. Testcontainers 2.x có API/package Kafka container khác; dùng dependency/documentation phù hợp phiên bản.

Các tình huống tích hợp cần bao phủ:

| Kịch bản | Xác minh |
| --- | --- |
| Profile local có broker hợp lệ | Producer/consumer tạo được và xử lý record. |
| Bootstrap server sai | Log kết nối và readiness/alert thể hiện lỗi; không nhầm với empty topic. |
| Topic sai tên | Listener không xử lý topic kỳ vọng; chính sách quản lý topic phát hiện. |
| Consumer group mới | Offset reset theo policy đã chọn; không tự bỏ qua/replay ngoài ý muốn. |
| TLS certificate sai | Handshake thất bại và lỗi được ghi nhận an toàn. |
| SASL credential sai | Auth thất bại; không lộ JAAS string trong log. |
| ACL thiếu quyền group/topic | Không tiêu thụ hoặc không publish, có tín hiệu vận hành. |
| Rollout khi đang tiêu thụ | Rebalance và redelivery không gây side effect trùng. |
| Config map / secret rotation | Pod mới dùng cấu hình mới; Pod cũ được xử lý an toàn. |

## 20. Observability cho cấu hình Kafka

Một hệ thống có thể khởi động thành công nhưng Kafka consumer đang không xử lý được dữ liệu. Monitoring nên có:

- **Kafka consumer lag**, record consumption rate và số partition assigned.
- **Rebalance rate** và thời gian xử lý record.
- **Producer send errors**, request latency, retry và delivery failures.
- **Authentication/authorization errors** theo loại, không log secret.
- **Listener errors**, số record được xử lý, retry và DLT publishing.
- **Consumer group membership** theo môi trường và workload.
- **Kết quả nghiệp vụ thực tế**: số order cập nhật, idempotency collisions, backlog.
- **Configuration version / deployment revision** để so sánh trước và sau rollout.

Khi dùng Spring Boot Actuator, cần bật mức quan sát phù hợp. Không mặc định actuator health có một chỉ báo “Kafka consumer đã join đúng group, đọc đúng topic và có offset” chỉ vì HTTP status là 200.

### Logging nên ghi điều gì?

Một dòng log phù hợp:

~~~text
kafka_client_ready
  app=orders-worker
  profile=prod
  clientId=orders-worker
  groupId=orders-worker-v1
  topic=orders.events.v1
  authProtocol=SASL_SSL
~~~

Không ghi:

~~~text
sasl.jaas.config
password
access token
private key
raw Authorization header
all Spring Environment properties
~~~

`/actuator/env`, `/actuator/configprops` và các endpoint quản trị khác cần hạn chế exposure, phân quyền và masking. Đừng phụ thuộc hoàn toàn vào masking mặc định; hãy ngăn secret xuất hiện ở log/trace ngay từ nơi tạo.

## 21. Chẩn đoán các lỗi cấu hình thường gặp

### 21.1. Không kết nối được broker

Triệu chứng thường gặp là reconnect liên tục hoặc timeout khi lấy metadata.

Kiểm theo thứ tự:

1. Profile đang kích hoạt đúng không?
2. `KAFKA_BOOTSTRAP_SERVERS` có trỏ tới endpoint trong đúng environment không?
3. Từ Pod/VM có phân giải DNS và kết nối tới bootstrap servers được không?
4. Broker trả về `advertised.listeners` mà client **thực sự có thể kết nối** không?
5. Port đó dành cho PLAINTEXT, SSL hay SASL_SSL?
6. Nếu TLS, CA/hostname và truststore có hợp lệ không?
7. ACL broker/group/topic có cho phép thao tác tương ứng không?

Lưu ý: `bootstrap.servers` chỉ là điểm **khởi đầu** để Kafka client lấy metadata. Sau đó client phải dùng broker endpoints trong `advertised.listeners`. Có thể kết nối bootstrap broker nhưng vẫn lỗi khi kết nối đến các broker được quảng bá bằng hostname chỉ dùng trong mạng nội bộ khác.

### 21.2. SASL authentication failed

Có thể do:

- Sai username/password hoặc JAAS syntax.
- Broker không hỗ trợ mechanism được chọn.
- TLS handshake hoặc hostname validation lỗi xảy ra trước SASL.
- Credential đã rotate nhưng Pod còn dùng bản cũ.
- Secret mount/configtree path không tồn tại hoặc file không đúng tên.
- Worker có quyền đọc secret nhưng principal không có Kafka ACL cần thiết.

Phân biệt **authentication** (chứng minh danh tính) và **authorization** (quyền truy cập topic/group). Một kết nối đăng nhập thành công chưa có nghĩa consumer đọc được topic.

### 21.3. Consumer không thấy record dù producer có gửi

Kiểm:

- Có trỏ đúng cluster và topic không?
- Consumer group ID là gì, committed offsets đã ở đâu?
- `auto-offset-reset` được áp dụng trong trường hợp chưa có offset hay offset không còn hợp lệ thế nào?
- Các partition có đang được gán cho consumer hay không?
- Có lỗi deserialization trước khi listener nhận dữ liệu không?
- Có nhiều Pod/consumer cùng group nên record nằm ở thread khác không?
- Listener error handler có retry/seek/pause làm kẹt phân vùng không?

**Không reset offset hay thay group ID ngay** trước khi biết rõ nguyên nhân. Đây là thao tác có thể gây replay hoặc mất backlog theo chính sách.

### 21.4. Pod chạy được ở local nhưng không chạy production

Thông thường khác biệt nằm ở profile, DNS, truststore, ACL hoặc mounted files. Kiểm tên property cuối cùng qua **kiểm thử binding an toàn**, không dump toàn bộ Environment ra log. Khi cần xác minh secret, kiểm sự tồn tại, permission và nguồn cấp chứ không in raw value.

## 22. Thay đổi cấu hình cần review theo mức độ rủi ro

Phân nhóm thay đổi để phê duyệt đúng người:

| Nhóm thay đổi | Ví dụ | Mức độ tác động |
| --- | --- | --- |
| Quan sát | Log level, metrics sampling | Thường thấp, nhưng có rủi ro log sensitive data. |
| Performance | Poll records, concurrency, timeout | Có thể tăng load/rebalance, cần benchmark. |
| Reliability | Ack mode, idempotence, retry policy | Cần kiểm fault/restart/idempotency. |
| Routing | Topic name, DLT, consumer group | Có thể đổi luồng dữ liệu/offset; rủi ro cao. |
| Security | SASL mechanism, credentials, truststore | Có thể gây outage hoặc lộ secret; cần rotation plan. |
| Cluster migration | Bootstrap servers, DNS, network | Có thể chuyển sang cluster khác; cần cutover/data plan. |

**Quản trị cấu hình tốt là một phần của reliability.** ConfigMap/Helm values nên nằm trong version control có review; secret nên ở secret manager có audit; deployment cần trace được config revision tương ứng với image revision.

## 23. Runbook cho một lần triển khai Kafka configuration

| Bước | Hành động | Điều cần xác nhận |
| --- | --- | --- |
| 1 | Xác định môi trường đích | Local/staging/prod và namespace/cluster đúng. |
| 2 | Review profile và source của property | Không có fallback từ prod sang localhost/PLAINTEXT. |
| 3 | Review topic, group ID, bootstrap servers | Đúng cluster, đúng data-processing identity. |
| 4 | Review TLS/SASL và secret references | Credential tồn tại, scope tối thiểu, không in log. |
| 5 | Validate ConfigMap và Secret mounts | File configtree và truststore đúng tên/đường dẫn. |
| 6 | Test kết nối, ACL và luồng dữ liệu ở staging | Listener đọc/producer gửi; DLT được xử lý theo policy. |
| 7 | Rollout dần | Theo dõi readiness, rebalance, lag và auth errors. |
| 8 | Đối soát dữ liệu sau rollout | Không replay/skip/duplicate ngoài chính sách. |
| 9 | Lưu version cấu hình và kết quả | Có thể tìm được root cause khi incident. |
| 10 | Chuẩn bị rollback | Cả image, config và cơ chế bảo toàn offsets. |

### Ví dụ incident

~~~text
Thời điểm: sau rollout prod v1.2.0
Triệu chứng: consumer không nhận record, lag tăng
Phát hiện:
  app profile = prod
  cluster endpoint = đúng
  group-id = orders-worker-v2 (bị đổi ngoài ý định)
  auto-offset-reset = none
  group v2 chưa có committed offsets

Nguyên nhân:
  Consumer identity thay đổi từ v1 sang v2 khi cập nhật ConfigMap.

Xử lý:
  Ngăn tiếp tục rollout.
  Đánh giá offset policy và dữ liệu cần xử lý.
  Khôi phục đúng group v1 theo kế hoạch.
  Rolling update và đối soát record/output.
  Bổ sung rule review group-id changes.
~~~

Trong case này, việc `auto-offset-reset=none` giúp phát hiện group ID mới chưa có offset thay vì âm thầm bỏ dữ liệu. Tuy nhiên, nếu business contract thật sự yêu cầu tạo group mới, phải có kế hoạch khởi tạo offsets đúng.

## 24. Bài tập thực hành

### Bài 1 — Externalize brokers và topics

Tạo một Spring Boot app có `application.yml`, `application-local.yml` và `application-prod.yml`. Không hard-code broker trong Java. Khi chạy local, dùng `localhost:9092`; khi chạy profile prod mà không có `KAFKA_BOOTSTRAP_SERVERS`, ứng dụng phải fail theo chính sách.

### Bài 2 — Type-safe configuration

Tạo `MessagingProperties` với `inputTopic` và `dltTopic` cùng `@NotBlank`. Dùng nó trong publisher và một `@KafkaListener`. Test binding với tên topic môi trường test.

### Bài 3 — SASL_SSL từ config tree

Dùng secret **giả** trong thư mục test có file `kafka.jaas.config`. Cấu hình `spring.config.import=configtree:` và xác minh Spring Boot đọc reference đúng, không in giá trị ra log. Không dùng secret thật trong fixture.

### Bài 4 — ConfigMap và Secret

Viết manifest để ConfigMap cung cấp broker/topic/group/concurrency, còn Secret mount JAAS/truststore. Giải thích vì sao đổi Secret trong cluster không tự làm Kafka client đang chạy refresh credential.

### Bài 5 — Nhận diện sai Kafka group

Cho hai profile dùng group khác nhau. Gửi một tập message, kiểm committed offsets và dự đoán hành vi khi group mới dùng `earliest`, `latest`, `none`. Không reset offset trên cluster production.

### Bài 6 — Testcontainers Kafka

Tạo integration test gửi record bằng KafkaTemplate tới topic test, listener nhận, rồi assert business side effect. Inject bootstrap servers động bằng `@DynamicPropertySource`; không sử dụng Kafka production cho test.

### Bài 7 — Rebalance và throughput

Thử số partition 3, replicas 2 và concurrency 1 rồi 3. Quan sát số consumer được gán partition, các thread rỗi, throughput và rebalance. Giải thích vì sao tăng concurrency không tự tăng partition count.

### Bài 8 — Security rotation

Mô phỏng credential A và B bằng môi trường test, tạo plan rolling rotation, xác minh Pod mới dùng B và Pod cũ được đóng đúng quy trình trước khi thu hồi A.

### Bài 9 — Failure injection

Cố ý cấu hình sai DNS, SASL mechanism, truststore hoặc ACL trên broker test. Phân loại lỗi đúng tầng và bảo đảm log không chứa credential.

### Bài 10 — Configuration review

Lập bảng tác động của những thay đổi sau: broker list, group ID, input topic, `enable-auto-commit`, ack mode, `max.poll.interval.ms`, `acks`, idempotence, SASL. Với từng thay đổi, chỉ ra test bắt buộc và khả năng rollback.

## 25. Tài liệu tham khảo chính thức

- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Kafka — Reference](https://docs.spring.io/spring-kafka/reference/)
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)

