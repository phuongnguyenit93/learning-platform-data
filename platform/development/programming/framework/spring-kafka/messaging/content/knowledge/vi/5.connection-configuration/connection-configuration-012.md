# Kiểm tra cấu hình đã được áp dụng

Một file `application.yml` có thể chứa đúng giá trị mà bạn mong đợi nhưng ứng dụng vẫn kết nối sai broker, dùng sai consumer group hoặc không áp dụng serializer như dự kiến. Nguyên nhân thường nằm ở profile đang chạy, biến môi trường ghi đè cấu hình, property được nạp từ nguồn khác hoặc một bean Kafka tự khai báo thay thế auto-configuration của Spring Boot.

Với ứng dụng Spring Kafka, cần xác minh cấu hình ở nhiều lớp: giá trị được nạp vào Spring Environment, thuộc tính được bind vào cấu hình Kafka của Boot, cấu hình thực tế được dùng để tạo producer/consumer, và trạng thái thực tế của broker/topic. Kiểm tra từng lớp giúp xác định chính xác cấu hình bị sai ở đâu.

## 1. Phân biệt các lớp cấu hình

Không có một màn hình duy nhất cho biết mọi thứ của Kafka đã được cấu hình đúng. Hãy phân biệt bốn lớp sau:

| Lớp | Nội dung cần kiểm tra | Nguồn quan sát |
| --- | --- | --- |
| Spring Environment | Property nào đang thắng sau khi hợp nhất file YAML, profile, biến môi trường, system property và command line | Actuator `env`, log khởi động, debugger |
| Spring Boot binding | Giá trị đã bind vào `KafkaProperties` và cấu hình auto-configuration | Actuator `configprops`, bean trong ApplicationContext |
| Kafka client runtime | Cấu hình thực tế của producer, consumer và admin được tạo ra | Dependency/bean inspection, log Kafka client, kiểm thử gửi/nhận |
| Kafka broker/topic | Broker nào đang phản hồi, topic có tồn tại, partition và cấu hình topic đang được áp dụng | Kafka CLI, `AdminClient`, log broker |

Ví dụ, `spring.kafka.bootstrap-servers=localhost:9092` trong Environment chỉ cho biết ứng dụng đã nạp property đó. Nó chưa chứng minh rằng `KafkaTemplate` đang dùng broker này: một `ProducerFactory` tự khai báo có thể dùng cấu hình khác. Tương tự, producer kết nối được broker cũng chưa chứng minh topic có retention hoặc số partition đúng yêu cầu.

## 2. Kiểm tra profile và nguồn cấu hình

Spring Boot có thể nạp cấu hình từ nhiều nguồn. Các nguồn có độ ưu tiên khác nhau; nguồn có ưu tiên cao hơn có thể ghi đè giá trị trong `application.yml`. Những nguồn thường gặp gồm:

- `application.yml` hoặc `application.properties` đóng gói trong ứng dụng.
- File theo profile, ví dụ `application-local.yml`, `application-test.yml` hoặc `application-prod.yml`.
- File cấu hình bên ngoài JAR, thư mục cấu hình được chỉ định hoặc cấu hình import.
- Biến môi trường của hệ điều hành/container.
- Java system properties và tham số dòng lệnh khi khởi chạy.
- Giá trị do test framework cung cấp trong lúc kiểm thử.

Đầu tiên, xác nhận profile đang hoạt động. Có thể khai báo khi chạy:

```bash
java -jar messaging-service.jar --spring.profiles.active=local
```

Hoặc đặt biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=local
```

Trong IDE, kiểm tra Run Configuration vì profile có thể được truyền bằng VM options, program arguments hoặc environment variables. Khi chạy trong Docker Compose hoặc Kubernetes, kiểm tra environment của container và ConfigMap/Secret được mount.

Ví dụ cấu hình theo profile:

```yaml
# application.yml
spring:
  kafka:
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
```

```yaml
# application-local.yml
spring:
  kafka:
    bootstrap-servers: localhost:9092
```

```yaml
# application-docker.yml
spring:
  kafka:
    bootstrap-servers: broker:19092
```

Nếu ứng dụng đang chạy với profile `docker`, giá trị `localhost:9092` trong file local không phải địa chỉ kết nối được chọn. Hãy xác minh profile và nguồn property trước khi thay đổi code.

Biến môi trường thường dùng để ghi đè cấu hình Spring Kafka:

| Property | Environment variable |
| --- | --- |
| `spring.kafka.bootstrap-servers` | `SPRING_KAFKA_BOOTSTRAP_SERVERS` |
| `spring.kafka.consumer.group-id` | `SPRING_KAFKA_CONSUMER_GROUP_ID` |
| `spring.kafka.consumer.auto-offset-reset` | `SPRING_KAFKA_CONSUMER_AUTO_OFFSET_RESET` |
| `spring.kafka.producer.acks` | `SPRING_KAFKA_PRODUCER_ACKS` |

Ví dụ PowerShell:

```powershell
$env:SPRING_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
$env:SPRING_PROFILES_ACTIVE = "local"
.\mvnw.cmd spring-boot:run
```

Khi giá trị trong YAML khác với biến môi trường, hãy kiểm tra property source đang có hiệu lực. Không nên sửa YAML nhiều lần nếu giá trị bị ghi đè từ Run Configuration hoặc môi trường chạy.

## 3. Kiểm tra giá trị trong Spring Environment bằng Actuator

Spring Boot Actuator cung cấp endpoint `env` để xem các property source và nguồn gốc của property. Endpoint `configprops` cho biết các bean `@ConfigurationProperties` đã được bind ra sao. Đây là hai điểm kiểm tra hữu ích khi nghi ngờ cấu hình không được nạp hoặc bị ghi đè.

Thêm Actuator nếu dự án chưa có dependency:

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

Trong môi trường local có thể expose endpoint phục vụ chẩn đoán:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops
```

Sau khi ứng dụng khởi động, kiểm tra:

```text
GET http://localhost:8080/actuator/env/spring.kafka.bootstrap-servers
GET http://localhost:8080/actuator/configprops
```

Endpoint `env` giúp xác định property xuất hiện từ nguồn nào và có giá trị nào đang được chọn. Endpoint `configprops` giúp xác minh dữ liệu đã bind vào bean cấu hình của Boot. Tên bean và cấu trúc response có thể thay đổi theo phiên bản Spring Boot.

Actuator có cơ chế che giấu các giá trị nhạy cảm, nhưng không nên dựa vào việc che giấu mặc định để mở endpoint cấu hình ra mạng. `env` và `configprops` có thể tiết lộ tên máy chủ, cấu trúc hệ thống hoặc giá trị cấu hình nội bộ. Chỉ expose trong môi trường chẩn đoán được bảo vệ, giới hạn quyền truy cập, và giữ chính sách hiển thị giá trị nhạy cảm ở chế độ an toàn. Không chia sẻ nguyên response của endpoint nếu chưa loại bỏ thông tin bí mật.

Nếu chỉ cần kiểm tra cấu hình đã được bind, hãy xem `configprops`. Nếu cần tìm property source đã ghi đè, xem `env` và đối chiếu profile, biến môi trường, system property và tham số khởi chạy.

## 4. Kiểm tra cấu hình Spring Kafka được bind

Spring Boot bind nhóm `spring.kafka.*` vào `KafkaProperties`. Các nhóm thường dùng gồm:

| Nhóm property | Nội dung |
| --- | --- |
| `spring.kafka.bootstrap-servers` | Địa chỉ broker bootstrap |
| `spring.kafka.client-id` | Client ID mặc định |
| `spring.kafka.admin.*` | Cấu hình Kafka admin |
| `spring.kafka.producer.*` | Serializer, acks, retries, batching và producer properties |
| `spring.kafka.consumer.*` | Group ID, deserializer, offset reset và consumer properties |
| `spring.kafka.listener.*` | Cấu hình listener container ở cấp Boot |
| `spring.kafka.properties.*` | Thuộc tính Kafka client dùng chung |

Ví dụ cấu hình:

```yaml
spring:
  kafka:
    bootstrap-servers:
      - localhost:9092
    client-id: order-service
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.messaging.event
```

Khi dùng JSON deserializer, cần cấu hình type mapping/trusted packages phù hợp với hợp đồng dữ liệu và phiên bản Spring Kafka. Không mở trusted packages rộng hơn nhu cầu chỉ để tránh lỗi deserialize.

Có thể kiểm tra bean `KafkaProperties` trong debugger hoặc thông qua Actuator `configprops`. Tuy nhiên, giá trị đã bind chưa nhất thiết là cấu hình cuối cùng của Kafka client. Spring Boot còn xây dựng các map cấu hình cho producer, consumer và admin; customizer hoặc bean do ứng dụng khai báo có thể tiếp tục thay đổi chúng.

## 5. Xác minh auto-configuration và bean thực tế

Spring Boot tự cấu hình các thành phần Kafka khi điều kiện auto-configuration phù hợp. Nếu ứng dụng khai báo bean riêng, một số cấu hình mặc định có thể được thay thế hoặc auto-configuration sẽ back off.

Các bean quan trọng cần kiểm tra trong ApplicationContext gồm:

- `KafkaTemplate`: đối tượng service thường inject để gửi bản ghi.
- `ProducerFactory`: tạo Kafka producer và cung cấp cấu hình producer.
- `ConsumerFactory`: tạo Kafka consumer cho listener container.
- `ConcurrentKafkaListenerContainerFactory`: factory tạo listener container.
- `KafkaAdmin`: thực hiện thao tác quản trị topic và broker.

Nếu dự án có nhiều bean cùng loại, kiểm tra `@Primary`, `@Qualifier`, tên bean và tham số mà service/listener đang inject. Một `KafkaTemplate` có thể được tạo từ `ProducerFactory` khác với factory mà bạn đang kiểm tra.

Có thể bật condition evaluation report khi chạy ứng dụng:

```bash
java -jar messaging-service.jar --debug
```

Report giúp xác định auto-configuration nào được áp dụng hoặc bị bỏ qua do thiếu class, property hoặc bean đã tồn tại. Nó không in ra toàn bộ cấu hình hiệu lực của Kafka client, nhưng hữu ích để giải thích vì sao Boot không tạo một bean dự kiến.

Khi cần kiểm tra sâu hơn, đặt breakpoint tại nơi tạo `ProducerFactory`/`ConsumerFactory`, hoặc kiểm tra các bean trong debugger. Nếu dùng factory mặc định của Spring Kafka, có thể xem configuration properties trên implementation tương ứng; tránh phụ thuộc vào API nội bộ hoặc cast một interface sang implementation nếu ứng dụng có thể thay đổi factory.

## 6. Phân biệt cấu hình client với cấu hình broker và topic

Một lỗi chẩn đoán phổ biến là tìm `retention.ms` trong `application.yml` rồi cho rằng đó là giá trị mà broker đang sử dụng. Retention là cấu hình topic/broker; nó không phải một thuộc tính producer hay consumer thông thường.

| Ví dụ | Nơi áp dụng | Cách kiểm tra |
| --- | --- | --- |
| `bootstrap.servers` | Kafka client | Actuator/configprops, client config và kết nối thực tế |
| `group.id` | Kafka consumer | Consumer config, `@KafkaListener`, consumer group CLI |
| `key.serializer` | Kafka producer | Producer config và kiểm thử gửi |
| `key.deserializer` | Kafka consumer | Consumer config và kiểm thử nhận |
| `retention.ms` | Topic | Kafka AdminClient hoặc `kafka-configs.sh` |
| `cleanup.policy` | Topic | Kafka AdminClient hoặc `kafka-configs.sh` |
| `num.partitions` | Topic mặc định khi tạo topic | `kafka-topics.sh --describe` hoặc AdminClient |
| `log.retention.hours` | Broker mặc định | Broker config qua công cụ quản trị |

Spring Kafka có thể tạo topic qua bean `NewTopic`, nhưng sau khi topic tồn tại, cần đọc cấu hình thực tế từ broker. Việc khai báo một bean trong source code không tự chứng minh broker đã áp dụng đúng cấu hình nếu topic đã được tạo trước đó hoặc quyền admin không đủ.

## 7. Kiểm tra broker và topic bằng Kafka CLI

Kiểm tra broker có phản hồi và API version:

```bash
kafka-broker-api-versions.sh --bootstrap-server localhost:9092
```

Liệt kê topic:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Xem partition, leader và replica của topic:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.events
```

Xem cấu hình topic:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders.events --describe
```

Xem tiến độ consumer group:

```bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group order-projection
```

Khi đọc kết quả, kiểm tra đúng cluster và đúng topic. Một topic có thể tồn tại ở local nhưng không tồn tại ở staging; cùng tên topic ở hai cluster không có nghĩa chúng chia sẻ dữ liệu hoặc cấu hình.

Lệnh `--describe` của topic giúp xác nhận số partition, leader và replica. Lệnh `kafka-configs.sh` giúp xem cấu hình topic đã được broker áp dụng. Lệnh consumer group cho biết current offset, log end offset và lag; lag thấp không tự chứng minh listener đã xử lý đúng nghiệp vụ, nhưng là một tín hiệu vận hành quan trọng.

## 8. Kiểm tra bằng Kafka AdminClient trong ứng dụng

Khi muốn kiểm tra broker từ code hoặc viết diagnostic endpoint nội bộ, có thể dùng `AdminClient`. Ví dụ sau tạo client với bootstrap server và đọc cluster metadata:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;

public class KafkaClusterInspector {

    public void inspect(String bootstrapServers) throws Exception {
        Map<String, Object> properties = new HashMap<>();
        properties.put(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers);

        try (AdminClient admin = AdminClient.create(properties)) {
            var description = admin.describeCluster();
            System.out.println("Cluster ID: " + description.clusterId().get());
            System.out.println("Nodes: " + description.nodes().get());
        }
    }
}
```

Trong môi trường có SASL hoặc TLS, map truyền cho AdminClient phải bao gồm cấu hình bảo mật tương ứng. Không tạo diagnostic client chỉ với `bootstrap.servers` nếu broker yêu cầu xác thực.

Để đọc cấu hình topic:

```java
import java.util.List;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.Config;
import org.apache.kafka.clients.admin.ConfigEntry;
import org.apache.kafka.common.config.ConfigResource;

public void inspectTopicConfig(AdminClient admin, String topicName)
        throws Exception {
    ConfigResource resource = new ConfigResource(
            ConfigResource.Type.TOPIC, topicName);

    Config config = admin.describeConfigs(List.of(resource))
            .values()
            .get(resource)
            .get();

    for (ConfigEntry entry : config.entries()) {
        String value = entry.isSensitive() ? "[hidden]" : entry.value();
        System.out.printf("%s=%s (source=%s)%n",
                entry.name(), value, entry.source());
    }
}
```

`ConfigEntry.source()` giúp phân biệt giá trị được đặt trực tiếp ở topic với giá trị kế thừa từ cấu hình mặc định. Đoạn code chỉ minh họa phần đọc topic config; cần xử lý timeout, authorization exception và lỗi kết nối trong ứng dụng thực tế. Không log các giá trị nhạy cảm của broker.

## 9. Xác minh producer và consumer thực sự hoạt động

Một cấu hình có vẻ đúng vẫn có thể sai khi tạo client hoặc khi broker từ chối kết nối. Hãy thực hiện một phép thử đầu-cuối:

1. Xác nhận broker trả lời qua địa chỉ bootstrap đang cấu hình.
2. Xác nhận topic tồn tại và có số partition mong muốn.
3. Gửi một bản ghi thử qua `KafkaTemplate` và chờ future hoàn tất.
4. Xác nhận record metadata trả về đúng topic và partition hợp lệ.
5. Nhận bản ghi bằng consumer group dự kiến và kiểm tra key/value sau deserialize.
6. Xem consumer group offset/lag để xác nhận consumer đã tiến lên.

Ví dụ kiểm tra producer trong integration test với Embedded Kafka:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.support.SendResult;

@SpringBootTest
@EmbeddedKafka(
        partitions = 1,
        topics = "configuration-check",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class KafkaConnectionIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Test
    void producerUsesConfiguredBroker() throws Exception {
        SendResult<String, String> result = kafkaTemplate
                .send("configuration-check", "probe", "configuration-ok")
                .get(10, TimeUnit.SECONDS);

        assertThat(result.getRecordMetadata().topic())
                .isEqualTo("configuration-check");
        assertThat(result.getRecordMetadata().partition())
                .isGreaterThanOrEqualTo(0);
    }
}
```

Test trên xác minh Spring context tạo được `KafkaTemplate` và producer gửi thành công tới broker nhúng. Nó chưa kiểm tra consumer listener hoặc môi trường broker bên ngoài. Muốn xác minh listener, bổ sung test nhận bản ghi và chờ assertion theo consumer group thực tế; muốn xác minh cấu hình production, cần kiểm tra trong môi trường có cấu hình tương đương.

## 10. Dùng log để chẩn đoán kết nối

Khi cần biết Kafka client đang gặp lỗi gì, có thể tăng log level tạm thời:

```yaml
logging:
  level:
    org.springframework.kafka: DEBUG
    org.apache.kafka.clients.NetworkClient: INFO
```

Các log này có thể giúp nhận diện lỗi DNS, connection refused, timeout, authentication failure, metadata hoặc lỗi serialize/deserialize. Chỉ bật mức chi tiết trong thời gian chẩn đoán và quay lại mức phù hợp sau đó. Tránh bật TRACE hoặc log toàn bộ cấu hình client trong production vì log có thể chứa dữ liệu nhạy cảm hoặc tạo lượng log lớn.

Một số dấu hiệu thường gặp:

| Log/hiện tượng | Hướng kiểm tra |
| --- | --- |
| `Connection to node ... could not be established` | Bootstrap server, advertised listener, DNS, port mapping và firewall |
| `Topic ... not present in metadata` | Tên topic, quyền truy cập, auto-create policy và cluster đang kết nối |
| `SaslAuthenticationException` | SASL mechanism, username/password, JAAS hoặc secret được nạp |
| `SSLHandshakeException` | Truststore, keystore, hostname verification và chứng chỉ |
| `SerializationException` | Serializer/deserializer và hợp đồng payload |
| Consumer không nhận record | Group ID, offset, partition assignment, subscription và consumer lag |

## 11. Checklist khi cấu hình không có hiệu lực như mong đợi

Trước khi thay đổi code, kiểm tra theo thứ tự:

- [ ] Profile đang hoạt động có đúng môi trường không?
- [ ] Có biến môi trường, JVM option hoặc command line ghi đè YAML không?
- [ ] `spring.kafka.bootstrap-servers` sau binding có đúng host và port không?
- [ ] Ứng dụng chạy trên host hay trong container; listener có đúng vị trí mạng không?
- [ ] `KafkaTemplate` đang dùng `ProducerFactory` nào?
- [ ] Listener container đang dùng `ConsumerFactory`/container factory nào?
- [ ] Có bean tự khai báo khiến Boot auto-configuration back off không?
- [ ] Serializer/deserializer có khớp kiểu dữ liệu và event schema không?
- [ ] Broker, topic, partition và cấu hình topic thực tế có đúng không?
- [ ] Consumer group có được assign partition và có tiến độ offset không?
- [ ] Có lỗi xác thực, TLS, ACL, DNS hoặc firewall không?
- [ ] Integration test có tái hiện được cấu hình đang chạy không?

Không nên đưa toàn bộ output của Actuator, Kafka client config hoặc environment variables vào ticket/chat công khai. Hãy che password, token, JAAS config, private key, truststore password và địa chỉ nội bộ nhạy cảm trước khi chia sẻ.

## 12. Kết luận

Để biết cấu hình Spring Kafka đã được áp dụng, hãy xác minh từ property source đến bean và Kafka client, sau đó đối chiếu với broker/topic thật. Actuator `env` giúp tìm nguồn property và giá trị đang thắng; `configprops` giúp xem cấu hình đã bind; condition report và bean inspection giúp phát hiện auto-configuration bị thay thế; Kafka CLI hoặc AdminClient xác minh cluster và topic; integration test chứng minh producer/consumer thực sự giao tiếp được.

Luôn phân biệt cấu hình client với cấu hình broker/topic, kiểm tra đúng profile và địa chỉ listener theo nơi chạy ứng dụng, đồng thời bảo vệ thông tin xác thực trong log và endpoint chẩn đoán. Khi kiểm tra theo từng lớp, nguyên nhân cấu hình sai sẽ dễ xác định và có thể sửa đúng vị trí.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Kafka — Reference](https://docs.spring.io/spring-kafka/reference/)
- [Apache Kafka — Admin API](https://kafka.apache.org/documentation/#adminapi)
