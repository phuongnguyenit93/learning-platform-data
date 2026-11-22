# Cấu hình theo profile và biến môi trường

Một ứng dụng Spring Kafka thường chạy ở nhiều môi trường: máy lập trình, môi trường tích hợp, staging và production. Mỗi môi trường có thể dùng Kafka cluster, địa chỉ broker, consumer group, cơ chế bảo mật và giới hạn vận hành khác nhau. Nếu đưa các giá trị này trực tiếp vào mã nguồn hoặc đóng gói cứng trong một file cấu hình, việc triển khai dễ nhầm môi trường và khó bảo vệ thông tin nhạy cảm.

Spring Boot hỗ trợ **externalized configuration**: ứng dụng đọc cấu hình từ file YAML/properties, biến môi trường, tham số dòng lệnh và các nguồn cấu hình bên ngoài. Kết hợp profile với biến môi trường giúp dùng cùng một artifact cho nhiều môi trường mà vẫn thay đổi được cấu hình kết nối Kafka.

## 1. Phân biệt profile và biến môi trường

Hai cơ chế này giải quyết hai nhu cầu khác nhau:

- **Profile** chọn một nhóm cấu hình theo mục đích chạy, ví dụ `local`, `dev`, `staging`, `prod` hoặc `test`.
- **Biến môi trường** truyền giá trị cụ thể từ nơi triển khai vào ứng dụng, ví dụ hostname Kafka, consumer group hoặc thông tin xác thực.

Profile thường quyết định *nhóm cấu hình nào được nạp*. Biến môi trường cung cấp *giá trị của cấu hình* tại thời điểm chạy.

Ví dụ, cùng profile `prod` có thể chạy trên hai Kubernetes cluster khác nhau. Cả hai đều dùng cấu hình production và SASL_SSL, nhưng `KAFKA_BOOTSTRAP_SERVERS` cùng thông tin xác thực được cấp khác nhau từ môi trường triển khai.

Không nên tạo một file cấu hình riêng cho từng máy chủ nếu chỉ khác hostname hoặc mật khẩu. Hãy giữ cấu trúc cấu hình chung và đưa các giá trị thay đổi theo môi trường ra bên ngoài.

## 2. Cấu trúc file cấu hình Spring Boot

Spring Boot tự động nạp file cấu hình theo quy ước tên. Một cấu trúc thường dùng:

```text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-dev.yml
├── application-staging.yml
└── application-prod.yml
```

- `application.yml` chứa cấu hình chung và giá trị mặc định an toàn cho phát triển.
- `application-local.yml` chứa cấu hình phục vụ chạy trên máy cá nhân.
- `application-dev.yml` chứa các khác biệt của môi trường development.
- `application-staging.yml` và `application-prod.yml` chứa cấu hình của các môi trường tương ứng.

Khi profile `dev` được kích hoạt, Spring Boot nạp cấu hình chung và cấu hình dành cho profile đó. Các giá trị trong file profile-specific có thể ghi đè giá trị chung cùng key.

### Cấu hình chung: application.yml

Ví dụ cấu hình cơ bản cho Spring Kafka:

```yaml
spring:
  application:
    name: spring-kafka-messaging

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all

    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP_ID:order-service}
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.messaging.event
```

Các giá trị trong ví dụ:

- `bootstrap-servers` là danh sách địa chỉ broker mà Kafka client dùng để khởi đầu kết nối và khám phá cluster.
- Producer dùng serializer tương ứng với kiểu key và payload gửi đi.
- Consumer dùng deserializer tương ứng với định dạng record.
- `group-id` xác định consumer group; các instance cùng xử lý một luồng nghiệp vụ thường dùng cùng group ID.
- `auto-offset-reset` chỉ áp dụng khi group chưa có offset hợp lệ hoặc offset hiện tại không còn tồn tại. Nó không tự đặt lại offset của group đã có offset hợp lệ.

Placeholder `${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}` nghĩa là dùng biến môi trường nếu có, nếu không thì dùng giá trị mặc định `localhost:9092`. Với cấu hình production quan trọng, có thể bỏ giá trị mặc định để ứng dụng báo lỗi ngay khi biến bắt buộc bị thiếu.

Tên package trong `spring.json.trusted.packages` chỉ là ví dụ. Hãy giới hạn vào package chứa event mà ứng dụng thực sự tin cậy; không mở rộng danh sách một cách tùy tiện.

## 3. Tạo cấu hình riêng cho từng profile

### Local: application-local.yml

Máy lập trình thường kết nối Kafka chạy bằng Docker Compose hoặc cài đặt local:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    consumer:
      group-id: order-service-local
      auto-offset-reset: earliest

logging:
  level:
    org.springframework.kafka: INFO
```

Có thể dùng group ID riêng cho local để dữ liệu thử nghiệm không làm thay đổi tiến độ đọc của consumer group development hoặc production.

### Development: application-dev.yml

Môi trường development thường dùng Kafka cluster dùng chung trong mạng nội bộ:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    consumer:
      group-id: order-service-dev
```

Ở đây không đặt giá trị mặc định cho `KAFKA_BOOTSTRAP_SERVERS`. Nếu môi trường chưa cấp biến này, ứng dụng sẽ không thể phân giải placeholder và quá trình khởi động thất bại sớm. Điều đó giúp phát hiện cấu hình thiếu thay vì vô tình kết nối vào một broker mặc định ngoài ý muốn.

### Production: application-prod.yml

Production thường cần TLS hoặc SASL tùy chính sách bảo mật của Kafka cluster:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: PLAIN
      sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}

    producer:
      acks: all

    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP_ID}
```

`KAFKA_SASL_JAAS_CONFIG` chứa cấu hình JAAS do nền tảng triển khai hoặc secret manager cấp. Không commit giá trị thật vào Git, không ghi nó ra log và không đưa secret vào ví dụ tài liệu hoặc ảnh chụp màn hình.

Cấu hình trên chỉ minh họa SASL_SSL với cơ chế PLAIN. Cơ chế xác thực thực tế phải khớp với broker. Nếu cluster dùng SCRAM, OAuth hoặc TLS client certificate, hãy cấu hình đúng mechanism, callback handler và chứng thư tương ứng.

Nếu dùng truststore hoặc keystore, Spring Boot có các thuộc tính dưới `spring.kafka.ssl.*`, ví dụ `trust-store-location`, `trust-store-password`, `key-store-location` và `key-store-password`. Đường dẫn file chứng thư thường được mount vào container từ secret hoặc volume được quản lý an toàn.

## 4. Kích hoạt profile

Có nhiều cách kích hoạt profile. Chọn cách phù hợp với môi trường chạy ứng dụng.

### Tham số dòng lệnh

```bash
java -jar messaging-service.jar --spring.profiles.active=dev
```

### Biến môi trường

Trên Linux hoặc macOS:

```bash
export SPRING_PROFILES_ACTIVE=dev
java -jar messaging-service.jar
```

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar messaging-service.jar
```

### Trong IDE

Có thể đặt environment variable `SPRING_PROFILES_ACTIVE=local` trong Run Configuration. Khi chạy ứng dụng, Spring Boot sẽ nạp `application-local.yml` cùng cấu hình chung.

Không nên cố định `spring.profiles.active` trong file profile-specific như `application-prod.yml`. Profile cần được chọn từ nguồn cấu hình không phụ thuộc profile đang được chọn, chẳng hạn biến môi trường, tham số dòng lệnh hoặc cấu hình triển khai.

### Kích hoạt nhiều profile

Spring Boot có thể chạy nhiều profile cùng lúc, ví dụ:

```bash
java -jar messaging-service.jar --spring.profiles.active=prod,metrics
```

Cách này hữu ích khi muốn tách cấu hình theo môi trường và theo nhóm chức năng. Tuy nhiên, nếu nhiều profile định nghĩa cùng một key, cần xác định rõ thứ tự ưu tiên và tránh tạo các tổ hợp khó dự đoán. Với cấu hình đơn giản, một profile môi trường duy nhất thường dễ vận hành hơn.

## 5. Ánh xạ Spring property sang biến môi trường

Spring Boot hỗ trợ relaxed binding. Quy tắc thông dụng khi chuyển tên property sang biến môi trường là:

1. Đổi dấu chấm (`.`) thành dấu gạch dưới (`_`).
2. Bỏ dấu gạch ngang (`-`).
3. Chuyển toàn bộ thành chữ hoa.

Ví dụ:

| Spring property | Biến môi trường |
|---|---|
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.kafka.bootstrap-servers` | `SPRING_KAFKA_BOOTSTRAP_SERVERS` |
| `spring.kafka.consumer.group-id` | `SPRING_KAFKA_CONSUMER_GROUP_ID` |
| `spring.kafka.producer.acks` | `SPRING_KAFKA_PRODUCER_ACKS` |
| `spring.kafka.properties.security.protocol` | `SPRING_KAFKA_PROPERTIES_SECURITY_PROTOCOL` |

Với property có dấu gạch ngang, dấu gạch ngang được loại bỏ khi tạo tên biến môi trường. Vì vậy, `group-id` trở thành `GROUP_ID`, không phải `GROUP-ID`.

Ví dụ cấu hình môi trường:

```text
SPRING_PROFILES_ACTIVE=prod
SPRING_KAFKA_BOOTSTRAP_SERVERS=kafka-1.example.internal:9093,kafka-2.example.internal:9093
SPRING_KAFKA_CONSUMER_GROUP_ID=order-service
```

Nếu dùng placeholder tùy chỉnh như `KAFKA_BOOTSTRAP_SERVERS`, biến đó được tham chiếu trực tiếp trong YAML bằng `${KAFKA_BOOTSTRAP_SERVERS}`. Nếu dùng tên biến theo property của Spring Boot, chẳng hạn `SPRING_KAFKA_BOOTSTRAP_SERVERS`, Spring Boot có thể bind trực tiếp vào property tương ứng mà không cần placeholder riêng.

Không nên khai báo hai nguồn có cùng ý nghĩa nhưng giá trị khác nhau nếu chưa hiểu thứ tự ưu tiên. Ví dụ, YAML đặt `bootstrap-servers` một giá trị trong khi môi trường đặt `SPRING_KAFKA_BOOTSTRAP_SERVERS` giá trị khác; biến môi trường có thể ghi đè cấu hình file và làm ứng dụng kết nối tới cluster khác dự kiến.

## 6. Thứ tự ưu tiên của nguồn cấu hình

Spring Boot hợp nhất cấu hình từ nhiều nguồn. Ở mức thực hành, cần nhớ:

- File cấu hình chung cung cấp giá trị mặc định.
- File profile-specific ghi đè giá trị chung khi profile tương ứng được kích hoạt.
- Biến môi trường và system properties có thể ghi đè cấu hình từ file.
- Tham số dòng lệnh thường có ưu tiên cao hơn các nguồn cấu hình thông thường.

Thứ tự đầy đủ có nhiều nguồn khác như test properties, `SPRING_APPLICATION_JSON`, cấu hình import và property source do framework thêm vào. Khi có xung đột, không nên đoán theo thứ tự file được đặt trong thư mục; hãy xác minh giá trị hiệu lực bằng cách kiểm tra cấu hình đang được nạp.

Ví dụ: `application.yml` đặt `bootstrap-servers` là `localhost:9092`, `application-prod.yml` đặt endpoint production, nhưng biến `SPRING_KAFKA_BOOTSTRAP_SERVERS` trong container lại chứa endpoint staging. Giá trị từ biến môi trường có thể thắng giá trị trong file và ứng dụng kết nối staging. Đây là lý do cần quản lý manifest và biến môi trường theo từng môi trường triển khai.

## 7. Đưa cấu hình vào Docker Compose

Trong Docker Compose, ứng dụng thường kết nối tới service name của Kafka trên cùng Docker network. Địa chỉ `localhost` bên trong container ứng dụng trỏ về chính container ứng dụng, không trỏ tới container Kafka.

Ví dụ service ứng dụng:

```yaml
services:
  messaging-service:
    image: example/messaging-service:1.0.0
    environment:
      SPRING_PROFILES_ACTIVE: dev
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      KAFKA_CONSUMER_GROUP_ID: order-service-dev
    depends_on:
      - kafka
```

Địa chỉ `kafka:9092` chỉ dùng được nếu Kafka service quảng bá listener có thể truy cập từ network của Compose. Cấu hình `advertised.listeners` của broker phải khớp với hostname và port mà ứng dụng sử dụng sau khi nhận metadata.

Nếu Compose được dùng cho production hoặc môi trường chia sẻ, hãy đưa credential qua secret mechanism của nền tảng. Không đặt mật khẩu thật trực tiếp trong file Compose được commit vào repository.

## 8. Đưa cấu hình vào Kubernetes

Kubernetes thường tách cấu hình không nhạy cảm và thông tin nhạy cảm:

- **ConfigMap** chứa profile, bootstrap server, consumer group và các tham số không bí mật.
- **Secret** chứa password, SASL JAAS config, private key hoặc truststore password.

Ví dụ Deployment rút gọn:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: messaging-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: messaging-service
  template:
    metadata:
      labels:
        app: messaging-service
    spec:
      containers:
        - name: app
          image: example/messaging-service:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: KAFKA_BOOTSTRAP_SERVERS
              valueFrom:
                configMapKeyRef:
                  name: messaging-config
                  key: kafka-bootstrap-servers
            - name: KAFKA_SASL_JAAS_CONFIG
              valueFrom:
                secretKeyRef:
                  name: kafka-credentials
                  key: sasl-jaas-config
```

ConfigMap và Secret phải được tạo riêng trong namespace triển khai. Quyền đọc Secret cần giới hạn theo service account và RBAC. Secret Kubernetes không tự động đồng nghĩa dữ liệu đã được mã hóa ở mọi lớp lưu trữ; môi trường vận hành nên cấu hình encryption at rest và quy trình quản lý/luân chuyển credential phù hợp.

Khi ConfigMap hoặc Secret được mount dưới dạng environment variable, tiến trình đang chạy không tự nhận giá trị mới. Thông thường cần rollout/restart Pod để ứng dụng đọc cấu hình mới. Nếu mount thành file, khả năng cập nhật file và cách ứng dụng reload còn phụ thuộc cơ chế cấu hình của ứng dụng; Kafka client cũng không tự động thay đổi mọi thiết lập kết nối chỉ vì file đã thay đổi.

## 9. Gom cấu hình nghiệp vụ bằng @ConfigurationProperties

Các thuộc tính Kafka chuẩn đã được Spring Boot bind qua `spring.kafka.*`. Với cấu hình riêng của ứng dụng, chẳng hạn tên topic, tên consumer group theo nghiệp vụ hoặc cờ bật/tắt publisher, nên gom vào một class cấu hình có kiểu dữ liệu rõ ràng.

Ví dụ:

```yaml
app:
  kafka:
    order-topic: order-events
    audit-topic: audit-events
```

Khai báo record cấu hình:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.kafka")
@Validated
public record AppKafkaProperties(
    @NotBlank String orderTopic,
    @NotBlank String auditTopic
) {
}
```

Các constraint như `@NotBlank` cần có implementation của Jakarta Bean Validation. Nếu dự án chưa có validation provider, hãy thêm `spring-boot-starter-validation` vào dependency chạy ứng dụng (Maven dùng group `org.springframework.boot`, artifact `spring-boot-starter-validation`; Gradle dùng `implementation("org.springframework.boot:spring-boot-starter-validation")`). Với Spring Boot 3, các annotation validation thuộc namespace `jakarta.validation`.

Bật scan configuration properties ở lớp ứng dụng:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
```

Sau đó inject `AppKafkaProperties` vào publisher hoặc listener cần dùng tên topic. Có thể dùng `@EnableConfigurationProperties(AppKafkaProperties.class)` thay cho `@ConfigurationPropertiesScan` nếu muốn đăng ký tường minh.

Với các thuộc tính bắt buộc, dùng validation như `@NotBlank`, `@NotNull`, `@Min` hoặc constraint phù hợp. Thiếu cấu hình nên làm ứng dụng thất bại khi khởi động, thay vì để lỗi xuất hiện muộn trong lúc xử lý record.

Không cần tạo lại class `@ConfigurationProperties` cho toàn bộ `spring.kafka.*` nếu Spring Boot đã cung cấp sẵn `KafkaProperties` và auto-configuration. Hãy dùng prefix riêng như `app.kafka` cho cấu hình đặc thù nghiệp vụ.

## 10. Kiểm thử cấu hình theo profile

Cấu hình theo profile cũng cần được kiểm thử. Có thể dùng `@ActiveProfiles` để chọn profile trong test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class KafkaConfigurationTest {

    @Autowired
    private Environment environment;

    @Test
    void loadsTestProfile() {
        assertThat(environment.getActiveProfiles())
            .contains("test");
    }
}
```

Nếu integration test dùng Embedded Kafka, hãy để `@EmbeddedKafka` cung cấp bootstrap address cho Spring Kafka:

```java
@SpringBootTest
@ActiveProfiles("test")
@EmbeddedKafka(
    partitions = 1,
    topics = "order-events",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderMessagingIntegrationTest {
    // Test KafkaTemplate và @KafkaListener tại đây.
}
```

Profile `test` có thể đặt các giá trị mặc định phục vụ kiểm thử, nhưng địa chỉ broker nhúng được annotation ghi vào property được chỉ định. Không để test vô tình dùng endpoint dev hoặc production do biến môi trường của máy chạy test.

Có thể kiểm tra cấu hình theo từng profile trong CI bằng cách chạy test riêng hoặc khởi động application context với profile tương ứng. Không cần kết nối production Kafka chỉ để xác minh rằng placeholder và validation hoạt động.

## 11. Quy trình chẩn đoán khi ứng dụng kết nối nhầm Kafka

Khi ứng dụng không kết nối được hoặc gửi record tới cluster ngoài dự kiến, hãy kiểm tra theo thứ tự:

1. **Profile đang hoạt động**: xác nhận `SPRING_PROFILES_ACTIVE` hoặc `--spring.profiles.active` có đúng không.
2. **Bootstrap servers hiệu lực**: kiểm tra `spring.kafka.bootstrap-servers` sau khi hợp nhất các nguồn cấu hình.
3. **Biến môi trường**: xác nhận tên biến, giá trị, dấu phẩy phân tách broker và việc cấp biến vào đúng process/container.
4. **Listener broker**: bảo đảm broker quảng bá hostname/port có thể truy cập từ nơi chạy ứng dụng.
5. **Bảo mật**: xác minh `security.protocol`, SASL mechanism, credential, truststore và chứng thư.
6. **Consumer group**: kiểm tra group ID để tránh nhiều môi trường vô tình dùng chung một group.
7. **Cấu hình đã cập nhật**: xác nhận Pod hoặc tiến trình đã được restart sau khi đổi environment variable hoặc secret.

Không in toàn bộ environment hoặc dump tất cả property source ra log trong production vì chúng có thể chứa credential. Nếu cần quan sát cấu hình hiệu lực, chỉ log những trường không nhạy cảm như profile đang hoạt động, hostname broker đã được che bớt hoặc consumer group. Các endpoint Actuator như `env` và `configprops` cần được bảo vệ nghiêm ngặt nếu bật trong môi trường vận hành.

## 12. Nguyên tắc vận hành

- Dùng `application.yml` cho cấu hình chung và file profile-specific cho khác biệt thực sự giữa các môi trường.
- Chọn profile từ biến môi trường hoặc tham số triển khai, không cố định production profile trong mã nguồn.
- Dùng biến môi trường hoặc secret manager để cấp endpoint và credential theo môi trường.
- Giữ secret ngoài Git, log, image layer và file cấu hình đóng gói.
- Dùng `@ConfigurationProperties` cùng validation cho cấu hình nghiệp vụ bắt buộc.
- Tách consumer group theo môi trường để tránh các môi trường dùng chung tiến độ đọc ngoài ý muốn.
- Kiểm tra `advertised.listeners` và đường mạng từ chính container/Pod chạy Spring Boot.
- Sau khi thay đổi cấu hình kết nối, rollout hoặc restart ứng dụng theo quy trình triển khai để Kafka client nhận cấu hình mới.

Khi profile, biến môi trường và secret được tổ chức rõ ràng, cùng một ứng dụng Spring Kafka có thể chạy ở local, development và production với đúng Kafka cluster, serializer, consumer group và cơ chế bảo mật của từng môi trường.

