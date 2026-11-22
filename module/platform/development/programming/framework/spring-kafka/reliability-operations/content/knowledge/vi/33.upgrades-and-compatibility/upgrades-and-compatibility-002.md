# Tương thích Spring Boot trong Spring Kafka — hướng dẫn nâng cấp an toàn

## 1. Vấn đề: nâng Spring Boot không chỉ là thay version

Một ứng dụng xử lý sự kiện đơn hàng đang chạy ổn định bằng Spring Boot 2.x và Spring Kafka 2.x. Sau khi nhóm phát triển đổi sang Spring Boot 3.x, build có thể vẫn thành công nhưng producer callback không còn khớp API, listener dùng exception handler cũ, hoặc consumer không thể deserialize JSON có type header từ hệ thống trước đó. Khi nâng tiếp lên Boot 4.x, những thay đổi về modular starters, Jackson 3, Kafka client 4 và retry API trở thành một phần của bài toán.

Đối với hệ thống Kafka, **tương thích Spring Boot** nghĩa là bảo toàn đúng **hành vi vận chuyển và xử lý message**, không chỉ biên dịch được:

- Producer vẫn gửi record tới đúng topic/partition, được broker xác nhận theo `acks`.
- Consumer vẫn join đúng group, đọc/commit offset theo chính sách.
- Payload và headers do phiên bản cũ ghi còn được phiên bản mới đọc.
- Retry, backoff, dead-letter topic (DLT) vẫn hoạt động và không bỏ sót message.
- Khi app crash/rebalance, replay không làm nhân đôi tác động nghiệp vụ.
- Metrics/traces/logs còn phản ánh đúng tình trạng vận hành.
- Kafka broker, Kafka clients, Spring Kafka và Spring Boot nằm trong tập phiên bản được hỗ trợ.

Bài này thuộc **Spring Kafka Reliability Operations → Nâng cấp và tương thích → Tương thích Spring Boot**, dùng Java 17+, Spring Kafka, Kafka clients, Gradle/Maven, JUnit 5, Embedded Kafka và Testcontainers. Các ví dụ Boot 3.x/Spring Kafka 3.x và Boot 4.x/Spring Kafka 4.x cần được áp dụng **theo đúng phiên bản patch** mà dự án đang sử dụng.

> Bảng phiên bản và ghi chú migration trong bài dựa trên các nguồn chính thức được tham khảo vào **16/11/2026**. Ma trận hỗ trợ, các patch phát hành và dependency BOM tiếp tục thay đổi; trước một đợt nâng cấp thực, luôn xem trang compatibility và release notes hiện hành của chính versions dự kiến triển khai.

### Sau bài học, bạn cần làm được gì?

1. Phân biệt compatibility ở mức source API, runtime binary, Kafka protocol và message schema.
2. Chọn một bộ Java–Spring Boot–Spring Kafka–Kafka clients–broker có căn cứ.
3. Dùng Spring Boot BOM thay vì trộn các dependency versions tùy tiện.
4. Nhận ra thay đổi khi di chuyển Boot 2 → 3 → 4: future API, error handler, Jakarta, starters, KRaft, Jackson và retry.
5. Thiết kế test matrix gồm mixed-version producer/consumer, DLT, replay, transactions và bảo mật.
6. Lập kế hoạch canary/rolling deployment/rollback dựa trên business outcomes.
7. Điều tra những lỗi phổ biến sau upgrade như `NoSuchMethodError`, `ClassNotFoundException`, tăng lag hoặc mất DLT.

---

## 2. Bốn tầng tương thích cốt lõi

```text
            Application code
     KafkaTemplate / @KafkaListener
                   |
                   v
            Spring Boot
      auto-configuration / properties
      starters / Actuator / tracing
                   |
                   v
             Spring Kafka
      consumer container / retry / DLT
         transactions / serializers
                   |
                   v
         Apache kafka-clients
        Producer / Consumer / Admin
       wire protocol / authenticator
                   |
                   v
          Apache Kafka brokers
       partitions / ISR / ACL / KRaft

Cắt ngang các tầng:
  JDK, Spring Framework, Jackson,
  schema registry, Kafka Streams,
  build tools, security, testing.
```

| Tầng | Câu hỏi phải trả lời |
| --- | --- |
| Java / Spring Framework | JDK và APIs có hỗ trợ Boot target không? |
| Spring Boot | Dependency management và auto-config có đúng không? |
| Spring Kafka | Listener, error handler, retry và transaction APIs còn phù hợp không? |
| Kafka clients | Version có nằm trong dải client Spring Kafka hỗ trợ không? |
| Kafka broker | Cluster/feature level có hỗ trợ client/protocol đó không? |
| Wire schema | Consumer mới có đọc được record/headers do producer cũ tạo không? |
| Runtime semantics | Ack/offset/retry/DLT có giữ hành vi mong muốn không? |
| Infrastructure | TLS/SASL, ACL, DNS, ports và topic policy có tương thích không? |

### 2.1. Source compatibility, binary compatibility và behavioral compatibility

**Source compatibility** trả lời “code còn compile không?” — chẳng hạn một API trả `ListenableFuture` ở phiên bản cũ nhưng chuyển thành `CompletableFuture` ở phiên bản mới.

**Binary compatibility** trả lời “bytecode/linkage lúc chạy có khớp không?” — ví dụ `NoSuchMethodError` khi Spring Kafka biên dịch với một phiên bản `kafka-clients` nhưng runtime nạp JAR khác.

**Behavioral compatibility** trả lời “message có được xử lý và lưu đúng không?” — ví dụ listener vẫn nhận record nhưng sau upgrade commit offset sớm hơn business transaction khiến mất dữ liệu, hoặc type headers không còn ánh xạ đúng Java class.

Một pipeline không đạt behavioral compatibility thì không thể xem là nâng cấp an toàn dù hai lớp đầu thành công.

### 2.2. Boot version không phải Kafka broker version

Thay `org.springframework.boot` từ major 3 sang 4 **không nâng cấp Kafka brokers**. Broker có release train, protocol feature level, replication và metadata riêng. Khi nâng client lớn hơn, phải xác minh compatibility với broker đang vận hành trước; việc bắt tay TCP thành công không chứng minh mọi API/protocol feature được hỗ trợ.

---

## 3. Đọc ma trận Spring Boot / Spring Kafka

Trang [Spring for Apache Kafka](https://spring.io/projects/spring-kafka/) có **Kafka Client and Spring Boot Compatibility**. Các tuyến thường gặp trong ma trận tính tới thời điểm bài viết:

| Spring Boot | Spring Kafka phù hợp theo thế hệ | Ghi chú |
| --- | --- | --- |
| Boot 2.x | Kafka 2.x | Legacy; cần migration nếu chuyển lên Boot 3 |
| Boot 3.1.x | Kafka 3.0.x | Một tuyến trong ma trận được công bố |
| Boot 3.2.x | Kafka 3.1.x | Một tuyến trong ma trận được công bố |
| Boot 3.3.x | Kafka 3.2.x | Một tuyến trong ma trận được công bố |
| Boot 3.4.x | Kafka 3.3.x | Một tuyến trong ma trận được công bố |
| Boot 3.5.x | Kafka 3.3.x ở nhiều patch | Xem BOM của **patch Boot cụ thể** |
| Boot 4.0.x | Kafka 4.0.x | Spring Framework 7, Kafka clients 4, Jackson 3 |
| Boot 4.1.x | Kafka 4.1.x | Dải mới hơn theo compatibility matrix |

Bảng này chỉ dùng để **định hướng**. Một trang dependency coordinates của Boot 3.5 ở patch mới đã quản lý Spring Kafka 3.3.x và Kafka clients 3.9.x. Điều đó cho thấy không thể suy đoán version `kafka-clients` từ chữ “Boot 3.5” mà bỏ qua patch và BOM.

### 3.1. Đừng dùng ma trận sai phạm vi

Ma trận Boot ↔ Spring Kafka ↔ kafka-clients **khác** ma trận kafka-clients ↔ broker. Với các cặp major mới/cũ, cần tra tài liệu Apache Kafka và xác nhận trên broker cluster tương đương production.

Một số kết luận không hợp lệ:

- “Kafka client 4.0 chắc chắn kết nối được tất cả Kafka brokers 2.x.”
- “Spring Kafka 4.0 được dùng tùy ý với Boot 3.5 vì cả hai đều là Spring.”
- “Version mới hơn lúc nào cũng chạy tốt hơn với các API cũ.”
- “KafkaTemplate gửi thành công nghĩa consumer cũ đọc được JSON.”
- “Đã green unit tests thì retry/offset behavior không đổi.”

### 3.2. Bộ nguồn tham khảo

Nên đối chiếu theo thứ tự:

1. [Spring Kafka project compatibility](https://spring.io/projects/spring-kafka/).
2. [Spring Boot managed dependencies](https://docs.spring.io/spring-boot/reference/appendix/dependency-versions/coordinates.html).
3. [Spring Kafka change history](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html).
4. [Spring Boot 4 migration guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide) khi nâng major.
5. [Apache Kafka documentation](https://kafka.apache.org/documentation/) về client/broker protocol.
6. Dependency graph **đã resolve** của build sản xuất, không chỉ `build.gradle` trên Git.

---

## 4. Dependency management: dùng Spring Boot BOM làm nguồn chính

### 4.1. Vì sao không ghi version riêng cho mọi Kafka dependency?

Cấu hình có vấn đề:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka:4.0.0'
    implementation 'org.apache.kafka:kafka-clients:3.7.0'
    testImplementation 'org.springframework.kafka:spring-kafka-test:3.0.0'
}
```

Đây là ví dụ **cố tình trộn** ba phiên bản, không phải một tổ hợp được khuyên dùng. `spring-kafka-test` có thể phụ thuộc helper/APIs không còn khớp runtime; `spring-kafka` có thể gọi method chỉ có ở một version `kafka-clients` khác.

Với Spring Boot, thông thường:

- Boot quản lý Spring Kafka và Kafka clients qua BOM.
- Runtime và test Spring Kafka cùng thế hệ.
- Override version chỉ được thực hiện sau khi có lý do rõ và test tương thích.
- Đối với Gradle multi-module, quản lý một convention/BOM được thống nhất, tránh mỗi module ép Kafka versions khác nhau.

### 4.2. Gradle với Boot 3.x

Ví dụ cho Spring Boot 3.x (thay plugin patch bằng bản được tổ chức phê duyệt):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ở Boot 3.x, dự án thường dùng `org.springframework.kafka:spring-kafka` trực tiếp. Kafka dependencies không gắn version riêng; BOM của Boot chọn phiên bản phù hợp.

### 4.3. Gradle với Boot 4.x

Boot 4 modularize nhiều phần hạ tầng và cung cấp Kafka starter chuyên biệt:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-kafka-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-kafka` và `spring-boot-starter-kafka-test` thuộc cách tổ chức starter ở Boot 4. Không sao chép tọa độ này sang Boot 3 nếu chưa xác minh artifact. Ngược lại, khi nâng từ 3 lên 4, dùng starter mới giúp auto-configuration/classpath rõ ràng hơn.

Gradle cũng có thể quản lý BOM bằng `platform(...)` thay cho `io.spring.dependency-management`. Chọn **một chiến lược thống nhất** và kiểm tra resolved versions vì tính ưu tiên constraint/force phụ thuộc cách cấu hình.

### 4.4. Maven với Boot 3.x

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

### 4.5. Maven với Boot 4.x

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.0.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Nếu không dùng Boot parent, import BOM qua `dependencyManagement`. Không vừa dùng Boot BOM vừa gắn versions tùy tiện ở mọi dependency.

---

## 5. Đọc dependency graph thực tế

### 5.1. Gradle

```bash
./gradlew dependencyInsight \
  --dependency spring-kafka \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency kafka-clients \
  --configuration runtimeClasspath

./gradlew dependencies \
  --configuration testRuntimeClasspath
```

Với multi-module, chọn đúng `:service-name:dependencyInsight`. `testRuntimeClasspath` có thể nạp JAR khác `runtimeClasspath`; test phải phản ánh application sẽ được deploy.

### 5.2. Maven

```bash
mvn dependency:tree \
  -Dincludes=org.springframework.kafka,org.apache.kafka

mvn help:effective-pom
```

Kiểm tra cả Kafka Streams, Avro/Schema Registry clients, Jackson 2/3, Micrometer, Spring Retry và module legacy. Một classpath có nhiều versions/packaging có thể compile nhưng lỗi lúc runtime.

### 5.3. Inventory trước khi upgrade

```text
Service:                 orders-consumer
Current Java:            [version]
Target Java:             [version]
Current Spring Boot:     [version + patch]
Target Spring Boot:      [version + patch]
Spring Kafka:            [resolved version]
kafka-clients:           [resolved version]
Kafka Streams:           [version if used]
Jackson:                 [major/version]
Spring Retry:            [if referenced]
Broker versions:         [every broker, feature level]
Topic schema versions:   [consumer/producer contract]
Auth:                    [TLS/SASL/ACL]
Producer acks:           [policy]
Consumer ack mode:       [policy]
DLT topology:            [topic/partitions/retention]
```

Không dùng runtime log version của một dependency để tự suy ra tất cả transitive versions. Inventory cần kết hợp dependency report, broker info và cấu hình deploy.

---

## 6. Override dependency: trường hợp cần thiết và rủi ro

### 6.1. Khi nào được override?

Một override có thể hợp lý khi cần bản vá bảo mật, sửa lỗi Kafka client hoặc tương thích broker đặc biệt mà Boot BOM chưa cập nhật. Tuy nhiên, việc override phải dựa vào **dải versions được Spring Kafka hỗ trợ** và đã được thử với Kafka brokers thực tế.

### 6.2. Maven properties

Trong các dự án Spring Boot quản lý dependency theo cơ chế có hỗ trợ override, Spring Kafka hướng dẫn các property:

```xml
<properties>
    <!-- Chỉ mang tính minh họa về cú pháp. -->
    <kafka.version>3.9.1</kafka.version>
    <spring-kafka.version>3.3.10</spring-kafka.version>
</properties>
```

Hai số trên **không phải cặp được khẳng định an toàn** cho mọi Boot patch. Kiểm tra Spring Kafka release notes, broker compatibility và dependency report sau override.

### 6.3. Gradle

Với plugin `io.spring.dependency-management`:

```groovy
ext['kafka.version'] = '3.9.1'
ext['spring-kafka.version'] = '3.3.10'
```

Với native Gradle platform/version catalogs, cách override khác và `ext` không tự động bảo đảm tác dụng. Luôn đo phiên bản resolved bằng `dependencyInsight`.

### 6.4. Quy trình override được kiểm soát

1. Viết rõ issue/CVE/tính năng khiến phải override.
2. Kiểm tra client–Spring Kafka–broker matrix.
3. Nâng `spring-kafka-test` theo runtime khi cần.
4. Kiểm tra Kafka Streams/Connect nếu cùng application.
5. Chạy producer/consumer, serializer, retry/DLT và offset/replay integration tests.
6. Chạy canary với broker feature levels giống production.
7. Ghi lại ngày review/bỏ override khi Boot BOM đã xử lý.

Không dùng `latest.release` hay `force` rộng trong release build: không tái lập và có thể vô tình nhảy major.

---

## 7. Spring Boot Kafka auto-configuration

### 7.1. Boot tự động tạo gì?

Khi các dependency/bean conditions phù hợp:

```text
  spring.kafka.* properties
            |
            v
       KafkaProperties
            |
     +------+------+-----------------+
     |             |                 |
     v             v                 v
ProducerFactory ConsumerFactory    KafkaAdmin
     |             |                 |
     v             v                 v
KafkaTemplate  Listener factory    NewTopic beans
                   |
                   v
               @KafkaListener
```

Nếu ứng dụng tự tạo một bean cùng type/name, Boot có thể **back off** và không tạo bean mặc định. Sau upgrade, đây là nguyên nhân phổ biến khiến `DefaultErrorHandler` không áp dụng: handler được khai báo nhưng custom listener factory thực tế không sử dụng nó.

### 7.2. Cấu hình Boot 3.x minh họa

```yaml
spring:
  kafka:
    bootstrap-servers: KAFKA_BOOTSTRAP_HOSTS
    client-id: orders-service
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
    consumer:
      group-id: orders-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      auto-offset-reset: earliest
      enable-auto-commit: false
      properties:
        max.poll.records: 100
    listener:
      concurrency: 3
      ack-mode: record
```

`KAFKA_BOOTSTRAP_HOSTS` ở đây là giá trị cấu hình do môi trường cung cấp; thay bằng URL/service discovery của cluster được cấp phép. Với production không hardcode `localhost:9092` để chạy mọi nơi.

Một số options là thuộc Kafka client (`delivery.timeout.ms`, `max.poll.records`, `acks`), không phải do Spring Boot định nghĩa lại. Sau khi nâng Kafka client cần kiểm tra defaults và semantics.

### 7.3. Config dưới `properties`

```yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
    producer:
      properties:
        max.in.flight.requests.per.connection: 5
    consumer:
      properties:
        isolation.level: read_committed
```

Những cấu hình này có thể được override ở role-specific properties hoặc custom factories. Phải kiểm tra effective config từ startup logs với bảo vệ secrets, không chỉ đọc YAML.

### 7.4. `KafkaAdmin` và việc tạo topic

Boot/Spring Kafka có thể dùng `NewTopic` bean để yêu cầu tạo topic nếu được cấp quyền. Nhiều production clusters tắt auto-create và không cấp CREATE ACL cho ứng dụng. Nếu upgrade làm startup lỗi vì admin client, không cấp permission rộng bừa bãi; kiểm tra `KafkaAdmin`, topic manifest và ACL phù hợp.

---

## 8. Producer API thay đổi khi lên Spring Kafka 3

### 8.1. Từ `ListenableFuture` sang `CompletableFuture`

Code Spring Kafka 2.x có thể dùng:

```java
// Dạng legacy:
ListenableFuture<SendResult<String, String>> result =
    kafkaTemplate.send(topic, key, value);

result.addCallback(
    success -> log.info("Sent"),
    failure -> log.error("Send failed", failure));
```

Spring Kafka 3.x sử dụng `CompletableFuture` cho các overload send thông dụng:

```java
package example.kafka;

import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> template;

    public OrderPublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String eventId, String value) {
        return template.send(
            "orders.events", eventId, value);
    }
}
```

### 8.2. Callback mới

```java
publisher.publish(
    "evt-101", "{\"state\":\"CREATED\"}")
    .whenComplete((result, error) -> {
        if (error != null) {
            // Xử lý lỗi gửi, retry có giới hạn
            // hoặc chuyển sang outbox.
        } else {
            var metadata = result.getRecordMetadata();
            // metadata.topic(), partition(), offset()
        }
    });
```

Không lấy `send(...).get()` không timeout làm mặc định cho mọi request production. Integration test có thể chờ `get(10, TimeUnit.SECONDS)` để assert broker ack hữu hạn.

### 8.3. Producer ack không phải consumer success

`acks=all` trên một topic có replication factor 1 không chứng minh dữ liệu sống qua broker failover. Và producer future success không chứng minh `@KafkaListener` đã xử lý business effect. Sau upgrade phải test cả downstream consumer và DB output.

---

## 9. Listener và consumer group compatibility

### 9.1. Minimal listener

```java
package example.kafka;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderProjectionService service;

    public OrderListener(OrderProjectionService service) {
        this.service = service;
    }

    @KafkaListener(
        id = "orders-listener",
        topics = "orders.events",
        groupId = "orders-projection"
    )
    public void handle(
            ConsumerRecord<String, String> record) {

        service.applyIdempotently(
            record.key(), record.value());
    }
}
```

`OrderProjectionService` là domain service do ứng dụng cung cấp. Trong production nó cần bảo vệ unique business event ID để xử lý lại cùng message không gây tác động ngoài ý muốn.

### 9.2. `group.id` là định danh tiến độ xử lý

Khi rolling upgrade, không tự đổi `group.id` từ `orders-projection` thành `orders-projection-v2` chỉ để app “đọc lại cho sạch”.

- Group mới không có committed offsets cũ.
- `auto.offset.reset=earliest` có thể phát lại toàn bộ dữ liệu còn retention.
- `auto.offset.reset=latest` có thể bỏ qua record đã tồn tại.
- Nhiều groups cùng nghe topic sẽ nhận những copies độc lập.

Nếu muốn replay, cần workflow và business idempotency rõ. Nếu chỉ nâng framework, giữ group ID theo contract vận hành trừ khi có migration plan.

### 9.3. Listener concurrency

```yaml
spring:
  kafka:
    listener:
      concurrency: 4
```

Nếu topic chỉ có 2 partitions, cùng consumer group không có bốn partitions để phân đều cho bốn members. Cần kiểm tra partition count, assignments và rebalance khi deploy thêm instances. Nâng Boot không tự tăng throughput chỉ nhờ tăng concurrency.

### 9.4. Offset commit so với business commit

```text
Consume E
    |
    v
DB transaction commits E
    |
    X app crashes before Kafka offset commit
    |
    v
E is replayed after restart
```

At-least-once delivery nghĩa là consumer phải chịu được replay. Spring Boot/Kafka version mới không bảo đảm exactly-once cho database ngoài Kafka transaction.

### 9.5. Ack mode

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

`RECORD`, `BATCH`, `MANUAL`, `MANUAL_IMMEDIATE` khác nhau về thời điểm offset được commit. Nếu listener sử dụng `Acknowledgment` thủ công, cấu hình manual ack mode tương ứng. Thay đổi listener factory giữa các version có thể đổi behavior dù code listener không đổi.

---

## 10. Error handler migration: Boot 2/Spring Kafka 2 → Boot 3/Spring Kafka 3

### 10.1. Nhận diện APIs legacy

Trong code Spring Kafka 2.x có thể có:

```text
SeekToCurrentErrorHandler
SeekToCurrentBatchErrorHandler
ErrorHandler / BatchErrorHandler
Legacy listener container error handler overrides
```

Thế hệ Spring Kafka 3.x tập trung vào `CommonErrorHandler` và `DefaultErrorHandler`. Không giữ JAR cũ chỉ để né migration error handling.

### 10.2. `DefaultErrorHandler` với DLT

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler commonErrorHandler(
        KafkaTemplate<String, String> template) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(template);

    // Initial attempt + 2 retries.
    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(500L, 2L));
}
```

Phải bảo đảm `CommonErrorHandler` được gắn vào **factory đang chạy**. Nếu ứng dụng tự khai báo `ConcurrentKafkaListenerContainerFactory`, hãy kiểm tra custom wiring tương ứng, không giả định Boot luôn gắn mọi bean tự động.

### 10.3. Những gì phải assert

Với poison message B:

```text
Topic input:
  A valid
  B POISON
  C valid

Expected:
  A -> processed once logically
  B -> attempts bounded -> DLT
  C -> processed
```

Không chỉ assert listener ném exception. Đo:

- Số delivery attempts theo cấu hình.
- DLT topic, partition, key, value, original-topic/error headers.
- Recovery publisher failure làm gì với source offset.
- Ordering của C sau B, tùy blocking/non-blocking retry.
- DB side effects không nhân đôi.

### 10.4. `@RetryableTopic` không giống blocking retry

Non-blocking retries chuyển record sang retry topics, giải phóng partition khỏi việc chờ dài nhưng có thể thay đổi thứ tự xử lý giữa records cùng key. Khi upgrade, cần kiểm tra retry topic names, partitions, consumer groups, concurrency và backoff.

Nếu dùng cả `DefaultErrorHandler` và `@RetryableTopic`, phải hiểu precedence và cấu hình error handler tại từng container, tránh hai lớp retry vô tình cộng attempts.

---

## 11. Spring Boot 4 và Spring Kafka 4: những điểm migration đặc thù

### 11.1. Spring Framework 7 và modular starters

Boot 4 chuyển sang Spring Framework 7 và tách nhiều auto-configuration modules. Dependency:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-kafka'
testImplementation 'org.springframework.boot:spring-boot-starter-kafka-test'
```

nên được xem xét khi nâng từ Boot 3. Các import từ `org.springframework.boot.autoconfigure.*` internal có thể đổi package. Nếu dự án xây custom starters, kiểm tra Boot 4 migration guide thay vì chỉ đổi version plugin.

### 11.2. Kafka client 4 và KRaft-only embedded broker

Spring Kafka 4 dùng Kafka clients thế hệ 4, và embedded test infrastructure chỉ còn KRaft. Những APIs cũ:

```text
EmbeddedKafkaZKBroker
EmbeddedKafkaRule
ZooKeeper properties in @EmbeddedKafka
@EmbeddedKafka(kraft=false)
```

không còn phù hợp với Spring Kafka 4. Chuyển test harness theo tài liệu Spring Kafka 4, kiểm tra embedded broker startup, partitions, transaction internal topics và listener assignment.

### 11.3. Kafka client interfaces

Nếu ứng dụng tự implement `Producer`, `Consumer`, tạo `ConsumerRecords` trực tiếp hoặc dùng Kafka Streams APIs cũ, khi nâng Kafka client 4 có thể phải thay method signatures/constructors. Một example MockConsumer/MockProducer viết nhiều năm trước cần compile với target version và chạy integration test mới.

### 11.4. Jackson 3 được ưu tiên trong Boot 4

Jackson 3 chuyển nhiều API từ `com.fasterxml.jackson.*` sang `tools.jackson.*`. Spring Kafka 4 hỗ trợ các counterparts Jackson 3 cho serializers/deserializers/converters.

| Lớp thường gặp ở Jackson 2 | Hướng migration ở Spring Kafka 4 |
| --- | --- |
| `JsonSerializer` | `JacksonJsonSerializer` |
| `JsonDeserializer` | `JacksonJsonDeserializer` |
| `JsonSerde` | `JacksonJsonSerde` |
| `JsonMessageConverter` family | `JacksonJsonMessageConverter` family |
| `DefaultJackson2JavaTypeMapper` | `DefaultJacksonJavaTypeMapper` |

Trong Spring Kafka 4, hỗ trợ Jackson 2 vẫn có thể tồn tại dưới dạng deprecated trong một giai đoạn, nhưng không nên dùng làm đích dài hạn. **Không đổi serializer class mà không chạy schema/wire contract tests**.

### 11.5. JSON configuration chuyển thế hệ

Ví dụ consumer Spring Kafka 3/Jackson 2:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: example.events.OrderEvent
        spring.json.trusted.packages: example.events
```

Khi chuyển sang counterpart Jackson 3 trong Spring Kafka 4:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JacksonJsonDeserializer
      properties:
        spring.json.value.default.type: example.events.OrderEvent
        spring.json.trusted.packages: example.events
```

Cấu hình mới yêu cầu dependencies/Jackson major phù hợp. Kiểm tra headers của producer cũ (type info), schema compatibility và type mappings; không đặt `trusted.packages=*` chỉ để vượt lỗi bảo mật.

### 11.6. Retry API trong Spring Kafka 4

Spring Kafka 4 loại dependency Spring Retry khỏi cơ chế retry core và chuyển sang cơ chế mới của Spring Framework 7. Ví dụ migration:

```java
// Trước - Spring Kafka 3:
@RetryableTopic(
    backoff = @Backoff(
        delay = 2000,
        maxDelay = 10000,
        multiplier = 2))
```

```java
// Sau - Spring Kafka 4:
@RetryableTopic(
    backOff = @BackOff(
        delayString = "2s",
        maxDelayString = "10s",
        multiplier = 2))
```

Chú ý chữ hoa `backOff` và annotation `@BackOff` mới; import/type phải theo release. Các custom exception classifiers, backoff generators, retrying deserializers cũng cần rà soát API thay đổi.

### 11.7. Kafka Streams migration riêng

Nếu dự án còn dùng `@EnableKafkaStreams`, Kafka Streams Serdes, processors, state stores hoặc Spring Kafka Streams utilities, không chỉ test `KafkaTemplate` và `@KafkaListener`. Spring Kafka 4/Kafka clients 4 còn có những thay đổi API của Kafka Streams; cần review state-store compatibility, topology version và application ID trước rolling deployment.

---

## 12. JSON schema, headers và tương thích giữa hai bản deploy

### 12.1. Rolling deployment luôn có giai đoạn hỗn hợp

```text
producer old (Boot 3)
         |
         v
      Topic A
         |
   +-----+------+
   |            |
   v            v
consumer old   consumer new
(Boot 3)       (Boot 4)
```

Trong giai đoạn rolling, consumer mới vẫn phải đọc được các records mà producer cũ đã lưu. Sau khi producers chuyển sang phiên bản mới, consumers cũ chưa dừng cũng có thể đọc messages mới. Do đó compatibility cần kiểm tra **hai chiều** nếu có thời gian phiên bản hỗn hợp.

### 12.2. Schema compatibility

- **Backward:** consumer mới đọc được dữ liệu cũ.
- **Forward:** consumer cũ đọc được dữ liệu mới.
- **Full:** cả hai chiều đều phù hợp theo contract.
- **Breaking:** một thay đổi phá giả định của một bên, chẳng hạn đổi required field type.

Ví dụ JSON payload:

```json
{
  "eventId": "evt-101",
  "orderId": "O-100",
  "state": "CREATED",
  "schemaVersion": 1
}
```

Nếu thêm `currency`, consumer cũ có chấp nhận unknown field không? Nếu bỏ `orderId`, consumer mới có default hợp lệ không? Nếu đổi ngày sang timestamp, schema/version cần thay đổi như thế nào?

### 12.3. Type headers có thể phá dù JSON body không đổi

Spring Kafka serializers có thể gắn header chứa Java type name:

```text
Producer old:
  type header = com.legacy.events.OrderCreated

Consumer new:
  class = com.newapp.events.OrderCreated

=> deserialization may fail
```

Nên dùng stable logical type alias/type mappings hoặc schema registry khi phù hợp, thay vì phụ thuộc lâu dài vào fully-qualified Java class name làm wire contract.

### 12.4. Test contract theo bytes và headers

Một contract test nên:

1. Lấy payload + headers do producer cũ tạo.
2. Consumer mới phải deserialize đúng.
3. Lấy payload + headers do producer mới tạo.
4. Consumer cũ phải deserialize nếu rolling rollout yêu cầu.
5. Test missing optional fields, unknown fields, null, enum mới, date/time formats.
6. Test invalid JSON và DLT serializer cho raw bytes.

Không chỉ kiểm tra object Java trong unit test; serialization compatibility nằm ở wire representation.

---

## 13. Deserialization failures xảy ra trước `@KafkaListener`

Luồng:

```text
Kafka bytes
     |
     v
Deserializer
     |
     +-- Invalid JSON / unknown type
     |          |
     |          v
     |      error handling
     |
     v
ConsumerRecord<K, V>
     |
     v
@KafkaListener
```

Nếu value deserializer ném exception trước khi tạo object, listener business không được gọi. Một test listener ném `IllegalArgumentException` không mô phỏng được deserialization failure.

### 13.1. `ErrorHandlingDeserializer`

Cấu hình dạng minh họa cho Spring Kafka 3.x:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: example.events
```

Khi dùng Spring Kafka 4/Jackson 3, cập nhật delegate class tương ứng. Cần kiểm tra DLT recoverer có thể gửi raw bytes và error headers bằng serializer phù hợp.

### 13.2. Test bắt buộc

- Gửi valid JSON → listener business xử lý.
- Gửi malformed JSON → error handler nhận thông tin lỗi.
- Malformed payload được gửi DLT hoặc xử lý theo chính sách.
- DLT giữ original topic/partition/offset, exception metadata cần cho audit.
- Partition không bị kẹt vô hạn.
- Không dùng wildcard `trusted.packages=*` nếu không có threat model và kiểm soát.

---

## 14. Offset, acknowledgement và replay sau nâng cấp

### 14.1. Kafka offset là tiến độ của group, không phải business ID

```text
topic orders.events / partition 0
 offset 10 : E-A
 offset 11 : E-B
 offset 12 : E-C

consumer group orders-projection
 committed offset = 12
 -> lần tiếp theo đọc từ offset 12
```

Một committed offset không có nghĩa record đã được xử lý exactly-once trong database. Consumer có thể crash sau DB commit nhưng trước offset commit.

### 14.2. Giữ ack semantics

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Nếu app dùng manual ack:

```java
@KafkaListener(
    topics = "orders.events",
    groupId = "orders-projection")
public void onRecord(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    orderService.persistIdempotently(
        record.key(), record.value());

    acknowledgment.acknowledge();
}
```

Import `org.springframework.kafka.support.Acknowledgment` và cấu hình manual ack mode phù hợp. Ack sau business commit vẫn không tự làm DB transaction + Kafka offset commit thành một distributed atomic transaction.

### 14.3. Replay cần idempotency

Tạo bảng:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

PostgreSQL example:

```sql
INSERT INTO processed_event (event_id, order_id)
VALUES (?, ?)
ON CONFLICT (event_id) DO NOTHING;
```

Nếu replay cùng eventId, duplicate insert không làm tăng số logical rows. Đây là ví dụ; nếu consumer còn gọi payment/email API thì cần idempotency key phía hệ thống đó, không chỉ unique constraint trong DB.

### 14.4. Consumer group protocol

Kafka 4 hỗ trợ consumer rebalance protocol mới trong những điều kiện phù hợp. Khi nâng đồng thời brokers/clients, cần kiểm tra group membership, assignment, rebalance frequency, `max.poll.interval.ms` và static membership. Không giả định chỉ nâng client là tự áp dụng protocol mới một cách an toàn cho cluster cũ.

---

## 15. Kafka transactions: ranh giới quan trọng khi migration

### 15.1. Kafka-to-Kafka

Trong topology consume một topic rồi publish sang topic khác với Kafka transactions được cấu hình đúng, có thể phối hợp records được publish và consumed offsets trong cùng Kafka transaction.

Consumer đọc transactional output có thể dùng:

```yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
```

### 15.2. Kafka transaction không bọc mọi hệ thống

```text
Consumer E
   |
   v
PostgreSQL COMMIT
   |
   X  Kafka transaction fails
   |
   v
E delivered again
```

Kafka transactions không tự rollback PostgreSQL, HTTP, email hoặc payment systems. Khi Boot/Spring Kafka major version đổi, các APIs điều phối transaction cũ như chained transaction managers cần được rà soát vì deprecation/removal. Xây idempotency/outbox/reconciliation theo yêu cầu nghiệp vụ.

### 15.3. Transaction ID prefix

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-
```

Cần kiểm tra chiến lược tạo transactional IDs theo app instance và concurrency để không fencing nhầm producers khi rolling upgrade. Tự dùng cùng một transactional ID cố định ở hai replicas có thể khiến một producer bị fencing.

### 15.4. Transaction integration test

- Publish committed record; `read_committed` consumer thấy.
- Abort Kafka transaction; `read_committed` consumer không thấy record đã abort.
- Crash sau DB commit trước offset commit; replay không nhân đôi DB state.
- Rolling upgrade của hai replicas không làm transaction fencing ngoài dự kiến.
- Broker/topic `transaction.state.log.*` được thiết lập phù hợp topology.

Single-broker Embedded Kafka thường cần replication/ISR settings thích hợp cho internal transaction topics; test đó không tương đương durability của production multi-broker.

---

## 16. TLS/SASL/ACL: compatibility ở tầng security

### 16.1. Mẫu cấu hình

```yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: INJECTED_JAAS_SECRET
    ssl:
      trust-store-location: file:/etc/kafka/client.truststore.p12
      trust-store-password: INJECTED_TRUSTSTORE_PASSWORD
```

Không commit secrets hoặc JAAS credentials vào repository. Hãy inject qua secret manager/configuration của môi trường deploy.

Sau upgrade cần xác minh:

- JDK mới có truststore type/TLS ciphers tương thích broker không?
- Kafka client có nhận đúng JAAS/SASL configs không?
- KafkaAdmin có cùng credentials?
- Producer có WRITE ACL, consumer có READ ACL, group có permission?
- DLT/retry topics có được tạo/ghi/đọc theo chính sách không?
- Transactional ID ACL có đúng không?

### 16.2. Auth failure không phải lỗi retry vô hạn

`AuthenticationException`, `AuthorizationException` và SSL handshake errors cần được phân loại. Tăng retry/backoff không sửa một credential sai, và có thể gây alert storm. Nếu production consumer không xử lý được sau upgrade, kiểm tra auth/protocol trước khi đổi offset/group.

---

## 17. Observability và Micrometer sau nâng Boot

Boot 3 đẩy mạnh Micrometer Observation/Tracing; Boot 4 tiếp tục phát triển observability infrastructure. Khi nâng major, một meter hoặc span không xuất hiện chưa chắc vì traffic bằng 0; có thể do meter name, tags, enable flags hoặc auto-config thay đổi.

### 17.1. Những chỉ số nên có

| Signal | Ý nghĩa |
| --- | --- |
| Consumer lag theo group/partition | Backlog và SLA |
| Listener p95/p99 | Processing latency |
| Producer send errors/latency | Delivery health |
| Retry attempts / DLT volume | Recovery path |
| Rebalance count/frequency | Group stability |
| Offset commit failures | Replay risk |
| Deserialization errors | Wire contract problems |
| DB duplicate key or idempotency conflict | Replay side effects |
| SASL/TLS failures | Security compatibility |
| Business completion delay | Ảnh hưởng tới người dùng |

Không lấy `eventId` hoặc `customerId` làm metric tag cho từng record vì cardinality cao. Structured logs có thể chứa identifiers đã sanitize, tùy chính sách quyền truy cập.

### 17.2. Baseline và canary

Trước upgrade, ghi baseline ít nhất một chu kỳ traffic có ý nghĩa. Trong canary so sánh:

- Messages consumed/second, producer errors, lag.
- Retry/DLT rate và độ tuổi records chưa xử lý.
- Consumer rebalance frequency.
- Business DB output, duplicate/reconciliation findings.
- JVM CPU/heap/GC và latency.
- Traces và dashboards có còn vận hành được không?

Không kết luận canary 5 phút là đủ nếu workload quan trọng chạy một lần mỗi ngày.

---

## 18. Kiểm thử tương thích bằng Embedded Kafka

### 18.1. Test runtime/test dependency đồng bộ

Nếu production chạy Spring Kafka 3.x nhưng `spring-kafka-test` bị khóa phiên bản 2.x hoặc 4.x, test harness có thể không đồng bộ. Luôn để BOM quản lý test dependencies tương ứng.

### 18.2. Test producer-consumer với broker thật

Ví dụ Spring Kafka 3.x/Boot 3.x:

```java
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@EmbeddedKafka(
    topics = {"orders.compat.it"},
    partitions = 1,
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaCompatibilityIT {

    @Autowired
    KafkaTemplate<String, String> template;

    @Autowired
    EmbeddedKafkaBroker broker;

    @Test
    void producerAndConsumerAreCompatible() throws Exception {
        String eventId = "e-" + UUID.randomUUID();

        Map<String, Object> props =
            KafkaTestUtils.consumerProps(
                "compat-" + UUID.randomUUID(), "false", broker);

        try (Consumer<String, String> consumer =
                new DefaultKafkaConsumerFactory<>(
                    props,
                    new StringDeserializer(),
                    new StringDeserializer()).createConsumer()) {

            broker.consumeFromAnEmbeddedTopic(
                consumer, "orders.compat.it");

            var sent = template.send(
                "orders.compat.it", eventId, "CREATED")
                .get(10, TimeUnit.SECONDS);

            assertEquals(
                "orders.compat.it",
                sent.getRecordMetadata().topic());

            var record = KafkaTestUtils.getSingleRecord(
                consumer,
                "orders.compat.it",
                Duration.ofSeconds(10));

            assertEquals(eventId, record.key());
            assertEquals("CREATED", record.value());
        }
    }
}
```

Ví dụ kiểm tra producer/consumer Kafka client. Nó chưa test `@KafkaListener` của ứng dụng hoặc business database. Cần thêm test listener thực, đợi partition assignment bằng `ContainerTestUtils.waitForAssignment` và assert kết quả nghiệp vụ bằng Awaitility.

### 18.3. Spring Kafka 4 Embedded Kafka

Embedded framework 4.x chỉ dùng KRaft: xóa các ZooKeeper props/classes như `EmbeddedKafkaZKBroker`, `EmbeddedKafkaRule` và `kraft=false`. Chạy lại transactional tests, bootstrap listeners và topic/partition setup. Việc `@EmbeddedKafka` vẫn compile không có nghĩa những assumption cũ về broker lifecycle còn hợp lệ.

### 18.4. Tránh flaky tests

- Không hardcode `localhost:9092`; dùng bootstrap servers do broker test cung cấp.
- Tạo topic/partitions rõ ràng.
- Tạo consumer group riêng cho mỗi test hoặc bảo đảm reset offsets.
- Đợi listener assignment trước khi gửi nếu test phụ thuộc subscription.
- Dùng blocking queue/Awaitility có timeout, không `Thread.sleep` cố định.
- Không phụ thuộc JUnit test-method execution order.
- Tách DLT/source topics và kiểm tra partitions phù hợp.
- Test trên Kafka image/version đã pin và có log evidence khi fail.

---

## 19. Testcontainers kiểm thử với broker và database thật

### 19.1. Vì sao cần Testcontainers?

Embedded Kafka giúp test nhanh. Testcontainers thêm process isolation và phù hợp khi cần Kafka + PostgreSQL, networking, serialization/ACL scenario hoặc broker image chính xác.

Ví dụ Testcontainers 1.x:

```java
@Testcontainers
@SpringBootTest
class KafkaPostgresIT {

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse(
                "confluentinc/cp-kafka:7.6.1"));

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers);
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl);
        registry.add(
            "spring.datasource.username",
            postgres::getUsername);
        registry.add(
            "spring.datasource.password",
            postgres::getPassword);
    }
}
```

Imports/Testcontainers module versions phải được căn với build; ví dụ chỉ mô tả hạ tầng test, chưa gồm listener và topic. Khi chuyển sang Testcontainers 2.x, một số Kafka container module/packages có thể đổi: dùng versioned docs tương ứng.

### 19.2. `@ServiceConnection`

Spring Boot có thể tạo connection details từ Testcontainers thông qua `@ServiceConnection` nếu starter support/phiên bản phù hợp. Khi dùng cách này, tránh khai báo trùng `@DynamicPropertySource` cho cùng Kafka bootstrap servers nếu không có lý do, vì có thể gây khó chẩn đoán effective endpoint.

### 19.3. Test DB idempotency

Dùng bảng `processed_event` có primary key `event_id`. Gửi cùng event ID hai lần hoặc chủ động replay sau crash trước offset commit. Assert:

- Consumer có thể nhận lại record.
- Chỉ một logical business effect tồn tại.
- Không bỏ qua record hợp lệ kế tiếp.
- Offset vẫn tiến đúng khi business operation thành công.

Một Testcontainers Kafka broker không mô phỏng đầy đủ cluster replication; muốn test leader failover/ISR phải có topology nhiều brokers hoặc staging cluster.

---

## 20. Ma trận regression test cho nâng cấp

| ID | Tình huống | Môi trường | Tiêu chí đạt |
| --- | --- | --- | --- |
| C01 | Producer send string | Embedded | Broker ack và record đúng key/value |
| C02 | Listener app nhận record | Embedded | Business output persisted |
| C03 | Consumer mới đọc JSON cũ | Contract/Embedded | Object và headers đúng |
| C04 | Consumer cũ đọc JSON mới | Contract/Embedded | Không phá mixed-version rollout |
| C05 | Deserialization lỗi | Embedded | Record lỗi vào DLT |
| C06 | Listener throw transient exception | Embedded | Retry hữu hạn, recovery đúng |
| C07 | Poison message | Embedded | DLT có record, partition tiến |
| C08 | Kafka offset replay | Kafka + DB container | Output không nhân đôi |
| C09 | Kafka transaction abort | Transaction-enabled broker | `read_committed` không thấy aborted record |
| C10 | Consumer rebalance | Container/multi-instance | Không bỏ business records |
| C11 | TLS/SASL authentication | Staging | Không mất ACL/security |
| C12 | Broker/client target compatibility | Versioned cluster | Không protocol error |
| C13 | Topic ordering per key | Multi-partition | Events cùng key giữ thứ tự partition |
| C14 | DLT publisher failure | Container fault | Record không silently mất |
| C15 | Rolling mixed versions | Preproduction | Old/new apps cùng wire contract |
| C16 | Observability upgrade | Staging/canary | Metrics/traces tồn tại, alert đúng |

Không nhất thiết chạy toàn bộ trong mỗi local commit. Nhưng trước release, những test ở mức Kafka + DB, retry/DLT, schema và broker security phải có evidence.

---

## 21. Triển khai rolling không làm gián đoạn dòng message

### 21.1. Các bước thực tế

1. **Inventory:** ghi JDK, Boot, Spring Kafka, kafka-clients, broker, topics, groups, schemas.
2. **Compatibility:** xác minh matrix cho phiên bản target.
3. **Fix build:** thay BOM/starter, loại version overrides không cần thiết.
4. **Migrate APIs:** futures, handlers, retry annotations, Jackson, Embedded Kafka.
5. **Test contract:** old producer → new consumer và ngược lại nếu mixed rollout.
6. **Test reliability:** retry/DLT, offset/replay, DB idempotency, transactions.
7. **Stage:** kết nối broker có cùng security/feature levels production.
8. **Canary:** một nhóm nhỏ instances, theo dõi lag/DLT/duplicates.
9. **Rolling:** nâng lần lượt, bảo vệ consumer group và transactional IDs.
10. **Reconcile:** kiểm tra outputs/offsets/DLT trước khi tuyên bố hoàn tất.

### 21.2. Consumer-first hay producer-first?

Nếu consumer mới có thể đọc cả payload cũ và mới, consumer-first thường giúp giảm rủi ro: nâng consumers rồi mới cho producers phát schema mới. Tuy nhiên phải xác minh cả chiều ngược lại trong rolling phase; một số thay đổi protocol/serializer không hỗ trợ sống chung và cần dual-write/dual-read hoặc versioned topic.

### 21.3. Tách upgrade ứng dụng và broker

Không cần buộc application Boot nâng cùng ngày broker cluster. Đổi đồng thời broker protocol, schema, Spring Kafka và JDK khiến việc xác định nguyên nhân khi lỗi khó hơn nhiều. Ưu tiên từng bước có rollback/evidence riêng.

### 21.4. Rollback phải tính tới dữ liệu

Rollback JAR không tự undo:

- Kafka records đã publish theo format mới.
- Consumer offsets đã commit.
- DLT records đã ghi.
- DB rows đã update.
- Broker feature/protocol level đã nâng.

Nếu consumer cũ không đọc được schema mới, “rollback code” có thể làm hệ thống tệ hơn. Duy trì compatibility window và remediation plan thay vì coi rollback là thao tác đơn giản.

---

## 22. Runbook chẩn đoán lỗi sau upgrade

### 22.1. `NoClassDefFoundError` hoặc `NoSuchMethodError`

Khả năng: binary dependency mismatch, lớp API đã bị loại, Jackson 2/3 conflicts.

Điều tra:

```text
Stacktrace class/method owner
  -> runtimeClasspath
  -> dependencyInsight/dependency:tree
  -> Boot BOM + transitive versions
  -> Spring Kafka change history
  -> clean rebuild / container image
```

Không sửa bằng cách thêm ngẫu nhiên một JAR version mới mà không tra matrix.

### 22.2. `NoSuchBeanDefinitionException` hoặc listener không start

Khả năng: thiếu Kafka starter/module, Boot auto-config back off, custom bean factory thiếu configuration, package import đã đổi ở Boot 4.

Kiểm tra `ConditionEvaluationReport`, KafkaProperties, bean types và listener registry. Đảm bảo factory chứa đúng error handler/serializer/security configs.

### 22.3. Producer gửi thành công nhưng consumer không xử lý

- Consumer group ID có đổi không?
- Committed offsets và `auto.offset.reset` ra sao?
- Listener đã assign partitions chưa?
- Deserializer có ném lỗi trước method?
- Topic name/ACL/SASL/TLS có đúng?
- JSON type header còn ánh xạ được class mới?
- Lag và rebalances thế nào?

Producer ack không có nghĩa consumer thành công.

### 22.4. Poison record không vào DLT

Khả năng:

- Error handler không được gắn factory.
- DLT topic chưa tồn tại hoặc sai partition.
- ACL thiếu WRITE.
- DLT serializer không hỗ trợ raw bytes.
- Retry policy không bao giờ exhausted.
- `@RetryableTopic` bị thay đổi API/bean topology.
- Recoverer ném exception và offset handling chưa được kiểm tra.

Dùng integration test cố ý ném lỗi với một event ID riêng và assert DLT record/headers.

### 22.5. Consumer lag tăng sau upgrade

Kiểm tra poll interval, `max.poll.records`, listener latency, DB pool, CPU/GC, concurrency so với partitions, group rebalance protocol và broker/network. Không tăng concurrency vô hạn vì ordering, DB contention và rate limits.

### 22.6. Duplicate business effects

Nếu record bị replay, kiểm tra business event ID, DB unique constraint, offset commit timing, recovery policy và transaction ordering. Không giải quyết bằng cách đổi group ID hoặc `auto-offset-reset=latest`; điều đó có thể bỏ mất records chưa xử lý.

### 22.7. TLS/ACL regression

Nếu producer hoạt động nhưng DLT publisher thất bại, có thể thiếu ACL riêng cho DLT. Nếu listener không join group, có thể thiếu GROUP READ permissions. Nếu KafkaAdmin khởi động lỗi, có thể không được phép tạo topics. Chọn quyền tối thiểu phù hợp thay vì cấp wildcard ACL cho ứng dụng.

---

## 23. Những sai lầm hay gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đổi `spring-boot` version | Starter/API chưa migration | Theo guide và full compatibility plan |
| Trộn Spring Kafka/kafka-clients/test versions | Runtime linkage error | BOM + dependency report |
| Dùng Kafka client latest với broker cũ | Protocol/feature mismatch | Client/broker matrix |
| Giữ `ListenableFuture` code ở Kafka 3 | Compile/source incompatibility | `CompletableFuture` |
| Giữ `SeekToCurrentErrorHandler` legacy | Error handler API mismatch | `DefaultErrorHandler` + test |
| Dùng `@Backoff` cũ khi nâng Kafka 4 | Retry config không tương thích | `@BackOff` migration |
| Giữ `EmbeddedKafkaZKBroker` | Test fail trên Kafka 4 | KRaft-only test harness |
| Đổi JSON class package không sửa type mapping | Deserialization fail | Logical aliases/schema contract |
| Bật `trusted.packages=*` để né lỗi | Rủi ro deserialization | Whitelist trusted packages |
| Chỉ assert producer future | Consumer/DLT có thể lỗi | End-to-end business assertions |
| Đổi consumer group ID theo release | Replay/mất lịch sử offset | Giữ group hoặc migration rõ |
| Coi Kafka EOS bao cả PostgreSQL | Duplicate DB side effects | Idempotent projection/outbox |
| Rollback code không xét schema | Consumer cũ không đọc được message mới | Compatibility window |
| Không theo dõi DLT sau upgrade | Poison records mất khả năng recovery | DLT metrics/test |
| Testcontainers suite bị skip trên CI | Mất bằng chứng broker thật | Enforce test policy |
| Tăng retries khi lỗi credentials | Retry storm | Phân loại lỗi auth và sửa ACL |
| Nâng broker và ứng dụng cùng một lúc | Khó rollback/phân tích nguyên nhân | Nâng theo phases |

---

## 24. Bài thực hành

### Bài 1 — Kiểm tra dependency compatibility

Cho build:

```text
Spring Boot:       3.5.x
Spring Kafka:      3.3.x
kafka-clients:     4.0.x (override)
spring-kafka-test: 3.1.x
Broker:            3.x
```

Hãy tìm các điểm rủi ro, tra ma trận chính thức và viết dependencyInsight/dependency:tree để chứng minh version resolved. Không tự khẳng định client 4 chắc chắn chạy được với broker 3.

### Bài 2 — Migrating producer callback

Chuyển một producer Spring Kafka 2.x dùng `ListenableFuture.addCallback` sang Spring Kafka 3.x dùng `CompletableFuture.whenComplete`. Test cả broker ack và lỗi gửi với timeout hữu hạn.

### Bài 3 — Listener compatibility

Tạo topic ba partitions, producer với key `orderId` và listener concurrency 2. Sau upgrade, assert events cùng order key giữ thứ tự trong partition. Không đòi ordering toàn topic.

### Bài 4 — Retry/DLT

Tạo listener ném lỗi cho payload `POISON`. Cấu hình `DefaultErrorHandler` với 2 retries, DLT recoverer. Assert attempts, original topic/offset metadata và record hợp lệ phía sau được xử lý.

### Bài 5 — JSON Boot 3 → 4

Chuẩn bị JSON + type headers được tạo bởi Jackson 2/Spring Kafka 3. Cấu hình Spring Kafka 4/Jackson 3 để đọc được. Test producer mới → consumer cũ, enum bổ sung và unknown fields nếu rolling deployment yêu cầu.

### Bài 6 — Embedded Kafka KRaft

Lấy một test `EmbeddedKafkaZKBroker` cũ. Chuyển sang KRaft-enabled test của Spring Kafka 4. Xóa ZooKeeper-only options và test producer/consumer, DLT, transaction support phù hợp.

### Bài 7 — Kafka + PostgreSQL Testcontainers

Tạo một event projection table có `event_id` unique. Gửi một event hai lần và mô phỏng restart trước offset commit. Assert một logical record còn tồn tại.

### Bài 8 — Offset và group ID

Tạo hai consumer groups với `earliest` và `latest` trên topic đã có records. Quan sát điểm bắt đầu đọc. Giải thích vì sao đổi group ID ở release có thể tạo replay hoặc bỏ messages.

### Bài 9 — Transaction scope

Xây Kafka-to-Kafka processing với Kafka transaction; test `read_committed` trên committed/aborted outputs. Thêm JDBC side effect rồi mô tả cửa sổ DB commit nhưng Kafka transaction thất bại.

### Bài 10 — Migration plan

Lập phiên bản nguồn và đích, test matrix, thứ tự deploy, rollback triggers và cách đối soát DLT/DB sau rollback. Chọn consumer-first hoặc dual-read/dual-write với lý do cụ thể.

### Bài 11 — Lỗi runtime

Một ứng dụng Boot 4 ném `ClassNotFoundException` khi JSON type header chứa `com.legacy.OrderEvent`. Hãy phân biệt thiếu JAR với lỗi wire type mapping và thiết kế schema contract test.

### Bài 12 — Observability

Vẽ dashboard consumer lag, listener p95, retries, DLT volume, producer failures, rebalances, duplicates và business SLA. Chỉ ra metric nào có thể đổi tên khi Boot/Micrometer nâng version và cách xác nhận qua Actuator.

---

## 25. Checklist nâng cấp production

### Tầng platform và build

- [ ] JDK và Spring Framework đáp ứng yêu cầu Boot target.
- [ ] Spring Kafka nằm trong dải tương thích với Boot target.
- [ ] `kafka-clients` nằm trong dải Spring Kafka và Kafka broker hỗ trợ.
- [ ] `spring-kafka-test` / Boot Kafka test starter phù hợp runtime.
- [ ] Kafka Streams/Schema Registry dependencies đã kiểm tra riêng nếu dùng.
- [ ] Không có version overrides không được phê duyệt.
- [ ] Dependency graph runtime/test được lưu trong release evidence.

### Application/wire semantics

- [ ] Producer futures/callbacks được migration.
- [ ] KafkaTemplate, consumer factory và listener factory đúng.
- [ ] `group.id`, topics, partitions và ack mode giữ contract.
- [ ] JSON/Avro/Protobuf schemas tương thích old/new producer–consumer.
- [ ] Error handler/retry/DLT đã test trên broker thật.
- [ ] Invalid JSON/deserialization errors có recovery path.
- [ ] DB/event IDs bảo vệ khỏi duplicate replay.
- [ ] Kafka transaction scope và external side effects được phân định.

### Vận hành

- [ ] TLS/SASL/ACL và broker feature levels đã được thử.
- [ ] Dashboard metrics/traces/logs còn hoạt động.
- [ ] Canary có baseline và ngưỡng rollback rõ ràng.
- [ ] Rollback tính đến schema, offsets và dữ liệu đã commit.
- [ ] CI không quietly skip container integration tests bắt buộc.
- [ ] Runbook DLT replay/poison message/idempotency đã sẵn sàng.
- [ ] Có owner đánh giá sự cố và thời điểm kết thúc compatibility window.

## 26. Kết luận

Nâng cấp Spring Boot cho một ứng dụng Kafka không phải một thao tác tách rời. Cần kiểm soát đồng thời:

\[
\mathrm{Java}
\rightarrow
\mathrm{Spring\ Boot}
\rightarrow
\mathrm{Spring\ Kafka}
\rightarrow
\mathrm{kafka\!-\!clients}
\rightarrow
\mathrm{Kafka\ brokers}
\]

và **wire schema, offset commits, retry/DLT, transactions, security và metrics**.

Phương pháp an toàn là **để Spring Boot BOM quản lý dependencies theo mặc định**, đối chiếu compatibility matrix chính thức, viết regression tests với broker thật, hỗ trợ giai đoạn mixed-version rollout và có cách khôi phục dữ liệu sau sự cố.

Một service có thể start thành công và health endpoint xanh, nhưng nếu DLT không ghi được poison messages hoặc DB bị nhân đôi do replay thì bản nâng cấp chưa đạt **reliability compatibility**. Tiêu chí cuối cùng phải là kết quả nghiệp vụ đúng qua cả happy path lẫn failure path.

## 27. Tài liệu tham khảo

- [Spring for Apache Kafka — Project Compatibility](https://spring.io/projects/spring-kafka/): ma trận giữa Spring Kafka, Kafka clients và Spring Boot.
- [Spring Kafka — Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html): quản lý/override Kafka versions.
- [Spring Kafka — Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html): Spring Kafka 3 → 4, KRaft, Jackson và retry.
- [Spring Kafka — Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html): Kafka starter và Java baseline.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): DefaultErrorHandler, DLT.
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): retry topics và @RetryableTopic.
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): Kafka transactions và exactly-once scope.
- [Spring Kafka — Testing](https://docs.spring.io/spring-kafka/reference/testing.html): Embedded Kafka và test helpers.
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): Spring Boot Kafka auto-configuration.
- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/reference/appendix/dependency-versions/coordinates.html): managed versions theo release.
- [Spring Boot 4 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): modular starters, Jackson 3 và API migration.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): service connections.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): client/broker protocol, transactions, security.
