# Topic, queue, consumer group và cách ly dữ liệu kiểm thử

## 1. Vì sao kiểm thử messaging thường flaky hoặc cho kết luận sai?

Một API đồng bộ thường có một lời gọi và một kết quả trả về. Messaging khác: producer, broker, partition/queue, consumer, acknowledgment, offset, retry và dead-letter processing vận hành trên nhiều luồng, nhiều thời điểm. Nếu test chỉ gọi `send(...)` rồi assert ngay vào một biến, nó dễ thất bại vì consumer chưa xử lý xong. Nếu test dùng lại topic, queue hoặc consumer group từ lần chạy trước, có thể đọc dữ liệu cũ rồi PASS giả, bị consumer test khác giành message, hoặc skip event vì offset đã commit.

Bài học này tập trung một yêu cầu rõ: **hiểu topic, queue, consumer group và thiết kế dữ liệu/hạ tầng riêng biệt để kiểm thử messaging đáng tin** trong Spring Boot.

Bạn sẽ học:

1. Phân biệt Kafka **topic/partition/consumer group/offset** với RabbitMQ **exchange/queue/binding/competing consumers**.
2. Hiểu một message có thể được phát tới bao nhiêu consumer: **một lần trong một group**, mỗi **group khác nhau** đọc độc lập, hoặc mỗi **queue khác nhau** nhận bản sao nếu exchange route như vậy.
3. Phân biệt broker acknowledgment, consumer processing, Kafka offset commit, RabbitMQ basicAck/NACK và business side effects.
4. Tạo unique topic, unique group ID, unique queue/exchange và unique event ID cho từng test hoặc test class.
5. Dùng Testcontainers thay vì broker production/shared environment; hiểu `@ServiceConnection`, `@DynamicPropertySource` và Spring TestContext caching.
6. Đợi listener/container readiness và message receipt bằng signal có giới hạn thời gian, không dùng `Thread.sleep`.
7. Kiểm isolation khi chạy song song, replay và auto-offset-reset, partition ordering, redelivery và duplicate messages.
8. Biết khi nào dùng `@EmbeddedKafka`, Kafka Testcontainers, RabbitMQ Testcontainers và khi nào cần multi-node integration.
9. Dùng domain fixture có testRunId/correlationId và assertions chống nhận nhầm message.
10. Xây **hai project Maven độc lập** với Java 17, Spring Boot 3.5.16, JUnit Jupiter và broker trong Testcontainers:
    - Kafka: Spring `@KafkaListener` với unique topic/group; test hai consumers cùng group và một consumer thuộc group khác.
    - RabbitMQ: Spring `@RabbitListener` với queue riêng; test fanout exchange tới hai queues và chứng minh mỗi queue có bản sao riêng.

**Mục tiêu kiểm thử:** Không chỉ “message đã được gửi”, mà kiểm chính xác **ai nhận**, **bao nhiêu lần**, **ở partition/queue nào**, **khi nào được xác nhận**, và **dữ liệu của test khác có thể lọt vào hay không**.

> Các bài lab chạy broker thật trên Docker/Testcontainers. Mã được rà soát về cấu trúc và API tương thích Boot 3.5/Spring Kafka 3.3/Spring AMQP 3.2; kết quả Maven/Docker cần chạy xác nhận trong môi trường có Docker. Không suy một test PASS nếu Surefire báo SKIPPED.

## 2. Bản đồ khái niệm: Kafka và RabbitMQ không tương đương một-một

### 2.1. Kafka: append-only log theo topic và partition

Kafka ghi messages vào những **partition logs** của một topic. Một topic có nhiều partitions, mỗi record có offset **trong partition**; offset là vị trí đọc, không phải ID business của message.

~~~text
Producer -> Kafka topic orders.created
                       |
           +-----------+-----------+
           |                       |
     Partition 0               Partition 1
     offset 0: A               offset 0: C
     offset 1: B               offset 1: D
           |                       |
           +-----------+-----------+
                       |
                 Consumer Group G1
                  c1 <-> p0
                  c2 <-> p1

                 Consumer Group G2
                  c3 <-> p0,p1
~~~

Trong một group ổn định, mỗi partition thường được gán cho **tối đa một consumer member của group ở cùng thời điểm**. Hai consumers G1 chia các partitions; consumer của G2 có thể đọc **cùng records** độc lập vì offsets của G2 không phụ thuộc G1.

Không mặc định suy một record trên Kafka chỉ được xử lý exactly-once: consumer có thể xử lý xong nhưng crash trước khi commit offset, sau đó đọc lại. Delivery/processing thường nên thiết kế **at-least-once với idempotency** trừ khi sử dụng/kiểm đúng transactional semantics được hỗ trợ trong một ranh giới xác định.

### 2.2. RabbitMQ: exchanges định tuyến tới queues

Producer trong AMQP gửi message tới **exchange**. Exchange dùng bindings và routing keys để đưa message vào một hoặc nhiều **queues**. Consumer nhận message từ queue, không trực tiếp “subscribe một Kafka topic”.

~~~text
                           fanout exchange
                          /               \
Producer -> event       /                 \
                      queue.shipping     queue.analytics
                           |                 |
                       consumer A         consumer B
                           |                 |
                      bản sao event      bản sao event
~~~

Nếu có **hai consumers cùng một queue**, chúng là competing consumers: một delivery thường được gửi cho **một consumer** tại một thời điểm; nếu chưa được ack và kết nối hỏng hoặc bị nack/requeue, message có thể được giao lại, thậm chí tới consumer khác.

~~~text
Producer -> exchange -> queue.jobs
                           |
                       +---+---+
                       |       |
                  worker A   worker B

Một message trong queue jobs được phân phối đến một worker;
không phải cả A và B cùng nhận một bản sao ổn định.
~~~

Để mỗi subscriber độc lập nhận **một bản sao** cùng event, tạo **queue riêng** và bind chúng vào fanout/topic exchange theo routing contract.

### 2.3. Bảng so sánh

| Khía cạnh | Kafka | RabbitMQ/AMQP |
| --- | --- | --- |
| Nơi producer ghi | Topic (partitioned log) | Exchange với routing key |
| Consumer đăng ký | Topic/partitions qua group | Queue |
| Broadcast độc lập | Các consumer groups khác nhau đọc log riêng | Các queues riêng cùng được exchange route |
| Phân chia công việc | Partition assignment trong một group | Competing consumers của cùng queue |
| Vị trí đọc | Offset theo topic-partition, group | Queue quản lý pending/unacked deliveries |
| Message sau khi consume | Thường còn trên log theo retention | Thường bị xóa khỏi queue khi ack |
| Replay | Seek/reset/new group + retained data | Phải requeue/re-publish hoặc dùng cơ chế lưu trữ khác |
| Ordering | Trong **một partition** (với caveats retry/producer config) | Trật tự queue có thể đổi ở nhiều consumers/requeue/priorities |
| Xác nhận | Producer broker ack và consumer offset commit khác nhau | Publisher confirm và consumer basicAck khác nhau |
| Isolation identifier | Topic, group.id, key, eventId | Exchange, queue, routing key, messageId |
| Test startup | Metadata/topic readiness, group assignment | Queue/exchange/binding declaration, listener readiness |
| Testcontainers | KafkaContainer/ConfluentKafkaContainer | RabbitMQContainer |
| Spring listener | `@KafkaListener` | `@RabbitListener` |

**Đừng gọi RabbitMQ “topic” mà không nói rõ đang nhắc tới `TopicExchange` hay một mô hình publish/subscribe; nó không phải Kafka topic.**

## 3. Kafka topic/partition/group: những điều phải kiểm đúng

### 3.1. Topic giữ dữ liệu theo retention

Kafka consumer đọc record từ log, không xóa record chỉ vì đã xử lý xong. Retention có thể do time/size/compaction, không do group commit. Một topic test dùng chung qua nhiều lần CI chạy có thể chứa records cũ.

Để tránh:
- Topic riêng cho class/test khi cần isolation mạnh.
- Thêm `testRunId` và `eventId` vào payload/key/header.
- Tạo group ID mới nếu muốn đọc lại từ đầu.
- Chọn `auto-offset-reset=earliest` khi group mới chưa có committed offset và test cần đọc những records đã gửi.
- Không dùng `earliest` như giải pháp xóa backlog cũ: topic shared vẫn có historical data.
- Với nhiều partitions, không dựa vào thứ tự global giữa các records.

### 3.2. Consumer group và assignment

Trong group G:
- 2 partitions, 1 consumer → consumer có thể nhận cả 2.
- 2 partitions, 2 consumers → mỗi consumer thường được phân một partition.
- 2 partitions, 3 consumers → một consumer thường idle vì số partitions ít hơn số consumers.
- Một partition không được xử lý song song bởi hai members **đồng thời** trong cùng một group ổn định.
- Khi member join/leave, rebalance thay assignment; trước/sau rebalance một record có thể bị xử lý lặp do commit offset/side-effect timing.

Không assert “consumer A nhận chính xác partition 0” nếu assignment strategy không bảo đảm; test nên assert **mỗi partition được giao cho đúng một group member**, còn union results đầy đủ.

### 3.3. Offset và auto.offset.reset

`auto.offset.reset` chỉ quyết định vị trí khi group **chưa có committed offset hợp lệ** (hoặc offset bị invalid/out of range):
- `earliest`: đọc từ đầu retained log.
- `latest`: bắt đầu tại cuối retained log; messages gửi **trước** khi new consumer group initialize có thể không được nhận.
- `none`: fail nếu không có offset thích hợp.

Nếu group đã commit offset, đổi `earliest` không tự reset group về đầu. Để replay có chủ đích, dùng new group, seek hoặc Kafka admin reset offsets đúng quy trình.

### 3.4. Key và partition ordering

Kafka producer có key; cùng key (với ổn định partitioner/partition count) thường map cùng partition. Tính ordering được đảm bảo theo offset **trong partition**; nếu records phân nhiều partitions, không có total order toàn topic.

Test có thể dùng explicit partition trong producer test để kiểm group distribution deterministic. Nhưng production keying/partitioner phải được test riêng nếu rule phụ thuộc ordering theo customer/order ID.

### 3.5. Producer send ack không phải consumer processed

~~~java
SendResult<String, String> result =
        template.send(topic, key, value).get(10, TimeUnit.SECONDS);
~~~

Snippet cần `KafkaTemplate` và `TimeUnit` trong context. Future success chứng minh producer đã nhận Kafka send result theo `acks` và config, **không** chứng minh consumer business handler đã chạy, không chứng minh DB write đã commit, cũng không chứng minh mọi subscribers đã nhận.

Dùng latch/probe/DB readback riêng cho consumer result.

## 4. RabbitMQ exchanges, queues và bindings

### 4.1. Direct, topic và fanout exchanges

- **DirectExchange**: routing key match binding key chính xác.
- **TopicExchange**: routing theo pattern; `*` khớp một word, `#` khớp zero-or-more words (words phân tách bằng dấu chấm).
- **FanoutExchange**: route bản sao đến mọi queue được bind, bỏ qua routing key.
- **HeadersExchange**: routing theo headers khi có requirement.

Ví dụ:

~~~text
TopicExchange: events.topic
  Binding shipping.q: "orders.created"
  Binding audit.q:    "orders.#"

Publish routingKey "orders.created":
  -> shipping.q
  -> audit.q

Publish routingKey "payments.captured":
  -> không vào hai queues trên
~~~

Đừng nhầm Kafka topic partitions với RabbitMQ TopicExchange; tên có vẻ giống nhưng cách tiêu thụ và retention khác.

### 4.2. Default exchange

RabbitMQ có unnamed default direct exchange `""`. Mỗi queue thường được auto-bind theo routing key bằng đúng queue name, nên Spring:

~~~java
rabbitTemplate.convertAndSend("", queueName, payload);
~~~

gửi tới queue có tên `queueName` qua default exchange. Đây **không phải** một producer “send trực tiếp tới queue” ở giao thức AMQP; routing vẫn qua default exchange.

### 4.3. Competing consumers trên cùng queue

Nếu `queue.jobs` có hai `@RabbitListener` instances hoặc listener concurrency=2, mỗi ready message được chuyển cho một consumer delivery; broker không tự nhân bản cho cả hai. Nếu consumer xử lý fail rồi `basicNack(requeue=true)`, message có thể được giao lại. Vì thế “queue xử lý mỗi message đúng một lần” là kỳ vọng **quá mạnh** trừ khi kiểm rõ ack/transaction/idempotency.

Sử dụng unique `messageId`/idempotency key và business-side deduplication khi repeated processing gây hậu quả.

### 4.4. Hai queues độc lập nhận broadcast

Với fanout exchange:
- Mỗi queue bound đều nhận một bản sao của event (trong điều kiện exchange/queue/binding sẵn có khi publish).
- Consumer của queue A ack không ảnh hưởng delivery của queue B.
- Queue B bị chậm có thể giữ backlog riêng.
- Queue mới bind sau khi event đã publish **không tự replay** event cũ: Rabbit classic queue khác Kafka retained log.

### 4.5. Queue, ack, nack và dead-letter

- **Consumer ack**: xác nhận một delivery đã được xử lý, broker có thể xóa khỏi queue.
- **Nack/reject + requeue**: chuyển message trở lại queue, có thể lặp lại.
- **Nack/reject không requeue**: message có thể bị drop hoặc dead-letter nếu queue đã cấu hình DLX.
- **Publisher confirm**: publisher xác nhận broker tiếp nhận publish (theo cấu hình), không chứng minh consumer xử lý.
- **Mandatory return**: giúp phát hiện publish không route tới queue khi được cấu hình; publisher confirm có thể thành công dù message unroutable nếu không kiểm returns.

Test reliability cần kiểm ack/nack/DLX cụ thể, không chỉ `RabbitTemplate.convertAndSend` không ném exception.

## 5. Vì sao messaging tests dễ bị nhiễm dữ liệu nhau?

### 5.1. Dùng chung topic hoặc queue cố định

Test A gửi event vào `orders.created`; test B cùng lúc cũng gửi; consumer B có thể nhận event của A hoặc đếm cả hai. Shared broker giữa local/CI thậm chí giữ records của hôm trước. Test chỉ assert “có một event” dễ PASS giả.

**Giải pháp:** unique resource name per test class/run, ví dụ `orders.test.<random-id>` hoặc `orders.test.2026...`, testRunId trên event và cleanup/lifecycle rõ.

### 5.2. Dùng chung Kafka group.id

Hai test processes dùng chung `group.id` có thể join cùng group và chia partitions. Khi mỗi process nghĩ mình sẽ nhận mọi message, một test sẽ thiếu records. Consumer group là một **đơn vị tiêu thụ logic**, không phải tên ngẫu nhiên có thể chia sẻ vô hại.

### 5.3. Reuse Rabbit queue giữa tests

Hai listeners trên cùng queue **cạnh tranh** nhận message. Test A có thể vô tình ăn message của B. Cần unique queue names cho những subscribers độc lập, hoặc chạy isolated broker/container.

### 5.4. Queue cleanup không đúng lúc

Gọi `purgeQueue` trong test A khi test B đang dùng cùng queue xóa message của B. Xóa queue hoặc topic shared có thể phá consumer group khác. Không cleanup bằng cách purge/delete resource global của team; namespace tài nguyên test và cleanup đúng resource do test sở hữu.

### 5.5. “Đợi 1 giây” không giải quyết contamination

`Thread.sleep(1000)` chỉ trì hoãn; không phân biệt message nguồn. Một test đúng cần:
- Correlation ID hoặc eventId riêng.
- Đúng destination/topic/group.
- Bounded await và kiểm đúng payload.
- Kiểm số lượng/negative case khi contract yêu cầu.
- Resource ownership/cleanup.

## 6. Các mức cách ly dữ liệu kiểm thử

| Mức isolation | Kafka | RabbitMQ | Khi nào dùng |
| --- | --- | --- | --- |
| Broker/container mỗi class | KafkaContainer riêng | RabbitMQContainer riêng | Integration tests tin cậy, Docker cho phép |
| Topic/queue mỗi test class | Unique topic + group | Unique queue/exchange | Có broker chung nhưng mỗi class cô lập |
| Resource mỗi test method | NewTopic + group mới | Declare queue/exchange mới | Parallel methods hoặc test đặc biệt |
| Event-level isolation | eventId/testRunId/header | messageId/correlationId/header | Cần lọc/đối chiếu trong test |
| Consumer state isolation | New consumer group/offset reset có chủ đích | Independent queue + ack state | Replay, repeated tests |
| Application context isolation | Unique Spring properties / context lifecycle | Unique queue property / listener lifecycle | Nhiều `@SpringBootTest` |
| Post-test cleanup | Delete test topic/ephemeral container | Delete test queues/exchanges/ephemeral container | Tránh dữ liệu tồn dư |

**Không có một biện pháp duy nhất đủ mọi trường hợp.** Unique eventId không ngăn consumer A vô tình lấy message B rồi ack nó; unique queue/topic bảo vệ ở broker. Một container riêng lại không thay cho correlation ID khi test có nhiều messages cùng luồng.

### 6.1. Isolation cho Spring context

`@KafkaListener(topics="${lab.kafka.topic}", groupId="${lab.kafka.group}")` đọc các placeholders khi context tạo. Nếu muốn thay topic giữa các test methods mà dùng cùng cached `ApplicationContext`, thay Java static variable ở runtime **không** tự đổi listener subscription. Với topic-per-method, cần tạo listener container/consumer programmatically hoặc context riêng, không cố sửa property sau context startup.

`@RabbitListener(queues="${lab.rabbit.queue}")` tương tự. Chọn resource-per-class như hai lab; hoặc khai báo/subscribe riêng trong test method nếu muốn resource-per-test.

### 6.2. Unique ID và assertion

Payload tối giản có thể là:

~~~json
{
  "eventId": "test-abc-event-001",
  "testRunId": "run-abc",
  "orderId": "order-42",
  "type": "ORDER_CREATED",
  "version": 1
}
~~~

Event ID cần mang meaning để assert đúng message. Lab Kafka dùng String payload đơn giản `eventId|CREATED`, Rabbit dùng message String để tập trung routing semantics. Trong hệ thống thật, thường dùng JSON/Avro/Protobuf cùng schema/version compatibility.

### 6.3. Đặt tên resource

Resource names phải theo broker rules:
- Kafka topic names thường chứa chữ, số, `. _ -`; giới hạn độ dài và ký tự nên được kiểm theo broker/version.
- Rabbit queue/exchange names cũng có restrictions/ownership; tránh dùng prefix dành cho system như `amq.`.
- Dùng stable prefix `it.orders.` + short random ID cho dễ debug.
- Không đưa tên khách hàng thật, PII hoặc secrets vào resource IDs.

## 7. Kafka lab: runnable Java 17 / Spring Boot 3.5.16

### 7.1. Phạm vi

**Project độc lập thứ nhất**. Broker Kafka thực chạy trong Testcontainers. Spring Boot context cấu hình producer, listener và `NewTopic`; test kiểm message roundtrip. Một lớp JUnit Java thuần dùng Kafka low-level client kiểm **hai members cùng group** và **một group độc lập** với topic riêng.

Không cần tải/khởi động Kafka bằng shell ngoài Testcontainers. Cần Docker hỗ trợ chạy Apache Kafka single-node image và đủ tài nguyên (RAM/CPU/network).

### 7.2. Cây file

~~~text
kafka-topic-isolation-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/kafkalab/
│   ├── KafkaLabApplication.java
│   ├── KafkaTopicConfiguration.java
│   ├── ReceivedOrders.java
│   └── OrderConsumer.java
└── src/test/java/com/example/kafkalab/
    ├── KafkaSpringTopicIsolationTest.java
    └── KafkaConsumerGroupSemanticsTest.java
~~~

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>kafka-topic-isolation-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.kafka</groupId>
      <artifactId>spring-kafka</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.kafka</groupId>
      <artifactId>spring-kafka-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-testcontainers</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>kafka</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Boot BOM 3.5 quản lý các dependencies thích hợp, gồm Testcontainers 1.x module `org.testcontainers:kafka`. Nếu project nâng Testcontainers 2.x, module coordinates có thể thay (ví dụ `testcontainers-kafka`), phải kiểm BOM/import của version đó thay vì copy cùng một package vô điều kiện.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
lab.kafka.topic=orders.local
lab.kafka.group=orders.local.consumer
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.listener.ack-mode=record
~~~

`localhost:9092` là **fallback cho chạy app ngoài test** khi bạn chủ động có broker local. Trong JUnit Testcontainers, `@ServiceConnection` cung cấp `KafkaConnectionDetails` từ container nên bootstrap servers runtime **không** phụ thuộc port cố định này; dynamic properties override topic/group.

Consumer config `auto-offset-reset=earliest` chỉ hỗ trợ group mới chưa có offset. Không làm sạch history của shared topic/group. `ack-mode=record` giúp commit offset sau khi listener xử lý record theo semantics Spring Kafka container, nhưng xử lý DB/broker transactions ngoài vẫn cần thiết kế riêng.

### 7.5. KafkaLabApplication.java

~~~java
package com.example.kafkalab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KafkaLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(KafkaLabApplication.class, args);
    }
}
~~~

Spring Boot auto-configure Kafka khi `spring-kafka` có mặt, và có thể phát hiện `@KafkaListener` thông qua annotation infrastructure. Không thêm một custom consumer factory khi Boot default đã đủ. Khi production cần security SASL/SSL, schema registry hoặc transactions, cấu hình riêng theo broker contract.

### 7.6. KafkaTopicConfiguration.java

~~~java
package com.example.kafkalab;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration(proxyBeanMethods = false)
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic(
            @Value("${lab.kafka.topic}") String topicName) {
        return TopicBuilder.name(topicName)
                .partitions(2)
                .replicas(1)
                .build();
    }
}
~~~

`KafkaAdmin` trong Spring Boot nhận `NewTopic` bean để create topic nếu chưa tồn tại. Hai partitions đủ cho bài consumer-group sharing. Single-node Kafka Testcontainers dùng replication factor 1; đây **không** phải production HA recommendation.

Lưu ý: Topic creation là một bước infrastructure setup, **không** được dùng làm thử nghiệm topic retention/replay production. Trong CI, kiểm logs/admin metadata nếu listener không assignment được.

### 7.7. ReceivedOrders.java

~~~java
package com.example.kafkalab;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.stereotype.Component;

@Component
public class ReceivedOrders {

    private final BlockingQueue<ConsumerRecord<String, String>> records =
            new LinkedBlockingQueue<>();

    void record(ConsumerRecord<String, String> event) {
        records.add(event);
    }

    public ConsumerRecord<String, String> await(
            Duration timeout) throws InterruptedException {
        return records.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Probe là **in-memory observation** để test chờ listener, không phải một offset store hay consumer production. Dùng `BlockingQueue.poll` với deadline nên không phải gọi `Thread.sleep`. Với nhiều test methods, phải lọc/đối chiếu `eventId`, giữ state isolation hoặc xóa probe có kiểm soát; lab chỉ có một integration method thuộc topic listener này.

### 7.8. OrderConsumer.java

~~~java
package com.example.kafkalab;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    private final ReceivedOrders probe;

    public OrderConsumer(ReceivedOrders probe) {
        this.probe = probe;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "${lab.kafka.topic}",
            groupId = "${lab.kafka.group}")
    public void onOrder(ConsumerRecord<String, String> record) {
        probe.record(record);
    }
}
~~~

Annotation property placeholders được resolve lúc Spring context tạo listener. Group ID khác nhau có offsets độc lập. Lưu record vào queue chỉ là probe; production listener còn phải validate schema, idempotent write/side effects và handle failure/retry đúng.

### 7.9. KafkaSpringTopicIsolationTest.java

`src/test/java/com/example/kafkalab/KafkaSpringTopicIsolationTest.java`:

~~~java
package com.example.kafkalab;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Testcontainers(disabledWithoutDocker = true)
class KafkaSpringTopicIsolationTest {

    private static final String RUN_ID =
            UUID.randomUUID().toString().replace("-", "");

    private static final String TOPIC =
            "it.orders." + RUN_ID;

    private static final String GROUP =
            "it.orders.consumer." + RUN_ID;

    @Container
    @ServiceConnection
    static final KafkaContainer kafka =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("lab.kafka.topic", () -> TOPIC);
        registry.add("lab.kafka.group", () -> GROUP);
    }

    @Autowired
    KafkaTemplate<String, String> producer;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    ReceivedOrders received;

    @Test
    void uniqueTopicAndGroupReceiveOnlyOurEvent()
            throws Exception {
        var listener = registry.getListenerContainer(
                "ordersListener");
        assertThat(listener).isNotNull();

        // Đợi listener được assign đủ 2 partitions
        // trước khi producer gửi message.
        ContainerTestUtils.waitForAssignment(listener, 2);

        String eventId = "event-" + RUN_ID;
        String payload = eventId + "|CREATED";

        var sendResult = producer.send(
                TOPIC, eventId, payload)
                .get(20, TimeUnit.SECONDS);

        assertThat(sendResult.getRecordMetadata().topic())
                .isEqualTo(TOPIC);

        ConsumerRecord<String, String> event =
                received.await(Duration.ofSeconds(15));

        assertThat(event).isNotNull();
        assertThat(event.topic()).isEqualTo(TOPIC);
        assertThat(event.key()).isEqualTo(eventId);
        assertThat(event.value()).isEqualTo(payload);
        assertThat(event.partition()).isBetween(0, 1);
        assertThat(event.offset()).isGreaterThanOrEqualTo(0L);
    }
}
~~~

**Điều gì được kiểm?**
- Kafka broker là **container thật**, không Mockito fake producer.
- Topic/group có random run-specific suffix, không đọc consumer offsets cũ từ test khác.
- `@ServiceConnection` cung cấp đúng bootstrap servers; Spring context không dùng broker local production.
- `@DynamicPropertySource` cấp đúng names cho `NewTopic`/`@KafkaListener`.
- `ContainerTestUtils.waitForAssignment` đợi consumer subscription/partition assignment, tránh race khi producer gửi quá sớm; đây là helper của `spring-kafka-test`.
- `send(...).get` đợi broker send result, `received.await` đợi **listener** thực thi.
- Assertions kiểm topic, key, payload, partition, offset để giảm false positives.
- Không assert một global ordering giữa partitions.

**Caveat:** Có Docker mới chạy thực sự. Annotation `disabledWithoutDocker=true` bỏ qua class nếu Docker không tồn tại; CI integration job phải báo số tests executed, không coi skipped là PASS.

### 7.10. KafkaConsumerGroupSemanticsTest.java

Class này sử dụng **Apache Kafka clients trực tiếp** với một topic mới cho method: hai consumers cùng group và một consumer ở group khác. Không cần Spring context vì mục tiêu là broker group semantics, và test tự tạo topic/clients/teardown trong scope method.

`src/test/java/com/example/kafkalab/KafkaConsumerGroupSemanticsTest.java`:

~~~java
package com.example.kafkalab;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers(disabledWithoutDocker = true)
class KafkaConsumerGroupSemanticsTest {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @Test
    void sameGroupSharesPartitionsDifferentGroupReplaysAll()
            throws Exception {

        String runId = UUID.randomUUID()
                .toString().replace("-", "");
        String topic = "it.groups." + runId;

        String sharedGroup = "it.shared." + runId;
        String independentGroup = "it.independent." + runId;

        try (AdminClient admin = AdminClient.create(Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                kafka.getBootstrapServers()))) {
            admin.createTopics(List.of(
                    new NewTopic(topic, 2, (short) 1)))
                    .all()
                    .get(30, TimeUnit.SECONDS);
        }

        try (KafkaConsumer<String, String> first =
                        consumer(sharedGroup);
             KafkaConsumer<String, String> second =
                        consumer(sharedGroup);
             KafkaConsumer<String, String> independent =
                        consumer(independentGroup);
             KafkaProducer<String, String> producer =
                        producer()) {

            first.subscribe(List.of(topic));
            second.subscribe(List.of(topic));
            independent.subscribe(List.of(topic));

            awaitAssignments(first, second, independent);

            List<String> expected = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                String id = "event-" + runId + "-" + i;
                expected.add(id);

                // Partition 0 và 1 đều có records.
                producer.send(new ProducerRecord<>(
                                topic,
                                i % 2,
                                "order-" + i,
                                id))
                        .get(15, TimeUnit.SECONDS);
            }

            List<String> sharedValues = new ArrayList<>();
            List<String> independentValues =
                    new ArrayList<>();

            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(20);

            while (System.nanoTime() < deadline
                    && (sharedValues.size() < expected.size()
                        || independentValues.size()
                                < expected.size())) {

                collect(first.poll(Duration.ofMillis(150)),
                        sharedValues);
                collect(second.poll(Duration.ofMillis(150)),
                        sharedValues);
                collect(independent.poll(Duration.ofMillis(150)),
                        independentValues);
            }

            assertThat(first.assignment()).hasSize(1);
            assertThat(second.assignment()).hasSize(1);
            assertThat(independent.assignment()).hasSize(2);

            // Hai consumers cùng group chia 8 records;
            // cộng lại đúng 8, không phải mỗi người 8.
            assertThat(sharedValues)
                    .containsExactlyInAnyOrderElementsOf(
                            expected);

            // Group độc lập đọc toàn bộ 8 retained records.
            assertThat(independentValues)
                    .containsExactlyInAnyOrderElementsOf(
                            expected);

            assertThat(new HashSet<>(sharedValues))
                    .hasSize(8);
        }
    }

    private KafkaConsumer<String, String> consumer(
            String groupId) {
        Map<String, Object> props = new HashMap<>();
        props.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                kafka.getBootstrapServers());
        props.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
                false);
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        return new KafkaConsumer<>(props);
    }

    private KafkaProducer<String, String> producer() {
        Map<String, Object> props = new HashMap<>();
        props.put(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                kafka.getBootstrapServers());
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        return new KafkaProducer<>(props);
    }

    private static void collect(
            ConsumerRecords<String, String> batch,
            List<String> sink) {
        for (ConsumerRecord<String, String> record : batch) {
            sink.add(record.value());
        }
    }

    private static void awaitAssignments(
            KafkaConsumer<String, String> a,
            KafkaConsumer<String, String> b,
            KafkaConsumer<String, String> c) {

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(25);

        while (System.nanoTime() < deadline) {
            a.poll(Duration.ofMillis(150));
            b.poll(Duration.ofMillis(150));
            c.poll(Duration.ofMillis(150));

            if (a.assignment().size() == 1
                    && b.assignment().size() == 1
                    && c.assignment().size() == 2) {
                return;
            }
        }

        throw new IllegalStateException(
                "Kafka group assignment not ready");
    }
}
~~~

**Giải thích sâu:**

- `AdminClient` tạo topic unique với **hai partitions** trước khi consumers join.
- Hai consumers có **cùng group ID**. Kafka phân bố partitions giữa members; test không khẳng định member nào có partition 0.
- Consumer thứ ba thuộc group ID **khác**, được assign cả hai partitions và đọc toàn bộ retained records.
- Tạo group mới, `auto-offset-reset=earliest` và topic mới giúp offsets hoàn toàn riêng; không phụ thuộc run trước.
- `awaitAssignments` poll cho tới khi group assignment ổn định theo expected shape, có deadline 25 giây; không phải fixed sleep.
- Producer gửi 8 records vào partition 0/1 một cách tường minh để không phụ thuộc key hash/partitioner.
- Hai members của shared group được poll theo vòng lặp và union results; independent group cũng được poll tới đủ 8.
- Test không commit offsets vì mục tiêu là delivery/assignment trong phiên test hiện tại, không phải restart/resume behavior.
- `containsExactlyInAnyOrderElementsOf` tránh giả định **global ordering** giữa partitions.
- Nếu broker rebalance mạnh, một record có thể được xử lý lại; test của ổn định assignment này không chứng minh exactly-once under failures. Các failure/rebalance scenarios cần tests riêng.

**Góc nhìn test isolation:** Unique topic *và* group trong method là yếu tố khiến test không đọc backlog cũ. Chỉ đổi group ID trên một shared topic đã có historical messages vẫn có thể khiến `earliest` đọc các messages không thuộc test.

### 7.11. Chạy Kafka lab

~~~bash
mvn -q clean test
mvn -q -Dtest=KafkaSpringTopicIsolationTest test
mvn -q -Dtest=KafkaConsumerGroupSemanticsTest test
~~~

Khi có Docker và tests executed:
- Kafka Spring test publish/read một event có topic/group unique.
- Group semantics test tạo topic riêng và chứng minh nhóm shared cùng nhau nhận 8 events, nhóm độc lập nhận 8 events.
- Maven trả exit code 0 khi thành công, reports trong `target/surefire-reports`.

Không có stdout cố định do Docker/image pulls, Kafka startup, group joins và OS khác nhau. **Không đồng nhất một build exit 0 khi tất cả tests SKIPPED với integration PASS.**

## 8. RabbitMQ lab: queue và exchange isolation

### 8.1. Phạm vi

**Project Maven độc lập thứ hai**, dùng RabbitMQContainer. Test đầu verify một Spring `@RabbitListener` nhận message trên unique queue; test thứ hai tạo fanout exchange và hai independent queues, assert mỗi queue nhận một bản sao.

Không có listener competition trên fanout queues; `RabbitTemplate.receiveAndConvert` pull trực tiếp mỗi queue giúp thấy routing result. Một queue dành cho `@RabbitListener` được tách hoàn toàn khỏi hai fanout test queues.

### 8.2. Cây file

~~~text
rabbit-queue-isolation-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/rabbitlab/
│   ├── RabbitLabApplication.java
│   ├── RabbitQueueConfiguration.java
│   ├── ReceivedMessages.java
│   └── OrderQueueListener.java
└── src/test/java/com/example/rabbitlab/
    └── RabbitMessagingIsolationTest.java
~~~

### 8.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>rabbit-queue-isolation-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-testcontainers</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>rabbitmq</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

RabbitMQContainer cần broker image; example dùng `rabbitmq:3.13-alpine`. Spring Boot 3.5 `RabbitConnectionDetails` hỗ trợ typed RabbitMQContainer. Nếu dùng management UI không cần cho tests này, không cần expose management port ra ngoài.

### 8.4. application.properties

`src/main/resources/application.properties`:

~~~properties
lab.rabbit.queue=it.orders.local
spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.listener.simple.concurrency=1
spring.rabbitmq.listener.simple.max-concurrency=1
~~~

Đây là fallback khi tự chạy app với RabbitMQ ở local. Trong Testcontainers, `@ServiceConnection` cung cấp host/port/user/password đúng từ container; queue name được đổi qua dynamic property.

### 8.5. RabbitLabApplication.java

~~~java
package com.example.rabbitlab;

import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableRabbit
public class RabbitLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(RabbitLabApplication.class, args);
    }
}
~~~

`@EnableRabbit` đăng ký cơ chế annotation-driven `@RabbitListener`; Boot auto-configure connection factory, RabbitTemplate và default listener container factory. Khi nâng cấu hình vào production, cần kiểm ack mode, retries, prefetch, concurrency và DLQ riêng.

### 8.6. RabbitQueueConfiguration.java

~~~java
package com.example.rabbitlab;

import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitQueueConfiguration {

    @Bean
    Queue ordersQueue(
            @Value("${lab.rabbit.queue}") String queueName) {
        return QueueBuilder.nonDurable(queueName).build();
    }
}
~~~

RabbitAdmin (qua Spring Boot) có thể auto-declare queue bean này khi listener/broker connection được mở. Queue **non-durable** chỉ dành cho integration test; production queue cần durability/arguments được thiết kế theo SLA.

Nếu queue đã tồn tại nhưng khác durability/arguments, broker có thể trả `PRECONDITION_FAILED`. Unique queue name tránh va chạm với queue của phiên chạy trước.

### 8.7. ReceivedMessages.java

~~~java
package com.example.rabbitlab;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

@Component
public class ReceivedMessages {

    private final BlockingQueue<String> inbox =
            new LinkedBlockingQueue<>();

    void record(String payload) {
        inbox.add(payload);
    }

    public String await(Duration timeout)
            throws InterruptedException {
        return inbox.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Probe dùng queue trong memory để test đợi consumer xử lý. Không thay cho AMQP queue hoặc storage. Không dùng `Thread.sleep`, không dùng static mutable global list.

### 8.8. OrderQueueListener.java

~~~java
package com.example.rabbitlab;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderQueueListener {

    private final ReceivedMessages probe;

    public OrderQueueListener(ReceivedMessages probe) {
        this.probe = probe;
    }

    @RabbitListener(queues = "${lab.rabbit.queue}")
    public void onMessage(String payload) {
        probe.record(payload);
    }
}
~~~

Mọi Spring instances của listener trên **cùng queue name** là competing consumers. Listener này nhận từ một unique queue, không liên quan hai queues của fanout routing test bên dưới.

### 8.9. RabbitMessagingIsolationTest.java

`src/test/java/com/example/rabbitlab/RabbitMessagingIsolationTest.java`:

~~~java
package com.example.rabbitlab;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.FanoutExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Testcontainers(disabledWithoutDocker = true)
class RabbitMessagingIsolationTest {

    private static final String RUN_ID =
            UUID.randomUUID().toString().replace("-", "");

    private static final String LISTENER_QUEUE =
            "it.orders.listener." + RUN_ID;

    @Container
    @ServiceConnection
    static final RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:3.13-alpine");

    @DynamicPropertySource
    static void rabbitProperties(
            DynamicPropertyRegistry registry) {
        registry.add("lab.rabbit.queue", () -> LISTENER_QUEUE);
    }

    @Autowired
    RabbitTemplate template;

    @Autowired
    AmqpAdmin admin;

    @Autowired
    ReceivedMessages received;

    @Test
    void listenerGetsMessageFromItsOwnUniqueQueue()
            throws Exception {

        String payload = "order-" + RUN_ID + "|CREATED";

        // Empty exchange name = default direct exchange.
        template.convertAndSend(
                "", LISTENER_QUEUE, payload);

        String delivered = received.await(
                Duration.ofSeconds(10));

        assertThat(delivered).isEqualTo(payload);
    }

    @Test
    void fanoutExchangeCopiesOneEventToEachBoundQueue() {
        String suffix = UUID.randomUUID()
                .toString().replace("-", "");

        String exchangeName = "it.fanout." + suffix;
        String shippingName = "it.shipping." + suffix;
        String analyticsName = "it.analytics." + suffix;

        FanoutExchange exchange =
                new FanoutExchange(exchangeName, false, false);

        Queue shipping =
                QueueBuilder.nonDurable(shippingName).build();
        Queue analytics =
                QueueBuilder.nonDurable(analyticsName).build();

        admin.declareExchange(exchange);
        admin.declareQueue(shipping);
        admin.declareQueue(analytics);
        admin.declareBinding(
                BindingBuilder.bind(shipping).to(exchange));
        admin.declareBinding(
                BindingBuilder.bind(analytics).to(exchange));

        try {
            String payload = "event-" + suffix + "|PAID";

            template.convertAndSend(
                    exchangeName, "", payload);

            Object shippingCopy =
                    template.receiveAndConvert(
                            shippingName, 5000);
            Object analyticsCopy =
                    template.receiveAndConvert(
                            analyticsName, 5000);

            assertThat(shippingCopy).isEqualTo(payload);
            assertThat(analyticsCopy).isEqualTo(payload);

            // Sau khi pull và ack, hai test queues rỗng.
            assertThat(template.receiveAndConvert(
                    shippingName)).isNull();
            assertThat(template.receiveAndConvert(
                    analyticsName)).isNull();
        }
        finally {
            admin.deleteQueue(shippingName);
            admin.deleteQueue(analyticsName);
            admin.deleteExchange(exchangeName);
        }
    }
}
~~~

**Điều gì được kiểm?**
- Listener test có queue name per run để không ăn data của test khác.
- `RabbitTemplate.convertAndSend("", queueName, payload)` đi qua default exchange theo routing key đúng queue name.
- Listener `@RabbitListener` nhận và đưa payload vào probe; test chờ bounded.
- Fanout test tự khai báo exchange, hai **queues khác nhau**, hai bindings; cùng event được route đến từng queue.
- `receiveAndConvert(queueName, 5000)` là blocking receive có timeout; không dùng sleep. Vì không có auto-consumer trên hai fanout queues, test tự nhận từng copy.
- Pull/ack xong, queue rỗng (với default auto-ack semantics của RabbitTemplate synchronous receive). Điều này khác với Kafka retained log.
- `finally` xóa **đúng hai queues/exchange do method sở hữu**; không purge hoặc delete shared queue.
- Test uses `@ServiceConnection` để không đụng RabbitMQ ở localhost thật.

### 8.10. Chạy RabbitMQ lab

~~~bash
mvn -q clean test
mvn -q -Dtest=RabbitMessagingIsolationTest test
~~~

Khi có Docker và chạy thực sự:
- Listener test nhận một payload duy nhất trên unique queue.
- Fanout test nhận cùng payload từ **hai queue độc lập**, sau đó cleanup.
- Maven trả exit code 0 nếu assertions thành công; xem `target/surefire-reports`.

Queue declaration cần hoàn tất trước publish. Trong lab, listener queue được Spring Boot RabbitAdmin declare như một `Queue` bean; fanout queues/exchange/bindings được method khai báo trực tiếp trước khi gửi message.

## 9. Test competing consumers trên RabbitMQ

### 9.1. Hai consumers cùng queue không phải broadcast

Ví dụ có hai service instances cùng `@RabbitListener(queues="jobs.q")`. Queue có 100 jobs. RabbitMQ phân phối jobs tới các consumers theo prefetch, ack/availability và scheduling; không thể kết luận chắc 50/50. Điều kiện nên kiểm:
- Tổng business task IDs đã xử lý = expected set.
- Với môi trường ổn định/auto-ack đúng, không xử lý sai ID.
- Không yêu cầu mỗi consumer nhận cùng message.
- Không giả định phân phối công bằng tuyệt đối.
- Với manual ack/requeue/restarts, chấp nhận redelivery và kiểm idempotency.

### 9.2. Test plan cho hai listener instances

1. Dùng một queue **riêng cho test**.
2. Khởi động hai consumers cùng queue, mỗi consumer có instance ID.
3. Chờ cả hai consumers registered/broker connection usable.
4. Gửi nhiều messages với eventId khác nhau.
5. Thu kết quả vào một thread-safe probe/DB table.
6. Assert union IDs đúng expected và không có event lạ.
7. Nếu test specifically đòi “both workers participate”, cần kiểm consumer readiness, prefetch và supply đủ load; không coi việc một worker idle là Rabbit routing bug.
8. Test requeue/nack/consumer crash riêng, không trộn vào happy path.

Đây là **kịch bản mở rộng** chứ không phải test đã implement ở lab mục 8; tránh tuyên bố code fanout chứng minh competing consumers.

### 9.3. Publisher confirm, consumer ack và idempotency

Một message có thể được publisher confirm nhưng không được consumer xử lý (message còn trong queue). Consumer có thể đã ghi DB rồi crash trước ack, khiến broker redeliver. Do vậy test cần phân tách:
- Producer broker accepted.
- Queue routing đúng.
- Consumer method được gọi.
- Side effect/DB transaction committed.
- Consumer ack/offset state đạt yêu cầu.

Với consumer replay, business operation nên dùng unique constraint/idempotency key để tránh nhân đôi payment/order/email.

## 10. Kafka replay và group offsets

### 10.1. Đổi group để replay retained records

Một Kafka message trong topic có thể được đọc bởi group G1 và G2 riêng. Khi G1 commit offset cuối, chạy lại G1 thường không thấy record cũ; group G2 mới với `earliest` có thể thấy record đang còn theo retention. Đây **không** giống RabbitMQ queue đã ack, nơi bản copy thường biến mất khỏi queue.

### 10.2. Auto-offset-reset không xóa committed offsets

Nếu group có offset đã commit, `auto-offset-reset=earliest` thường **không reset** group. Cách test replay đúng:
- Tạo group ID riêng.
- Chủ động seek vào vị trí cần test.
- Dùng admin reset offsets khi không có active consumers.
- Tạo topic riêng nếu cần tránh historical noise.
- Assert expected IDs thay vì `count()>0`.

### 10.3. Không dùng một group ID ở hai test classes

Hai Spring tests song song có cùng group ID/topic sẽ tham gia một group và chia partitions. Mỗi test có thể mất một phần dữ liệu mong đợi. Tạo group IDs khác nhau, hoặc nếu muốn test group sharing, **chủ động** đặt cùng group như Kafka group semantics test.

### 10.4. Kafka retention và message cleanup

Kafka không có thao tác “remove message X sau assert” theo cách `queue.basicAck` của Rabbit. Có thể delete topic, rút retention, truncate log/seek, hoặc đơn giản để **ephemeral broker container** tự bị hủy. Khi topic phải được chia sẻ trên broker test long-lived, xóa đúng topic do test sở hữu và kiểm admin API hoàn tất trước reuse tên.

### 10.5. At-least-once và duplicate tests

Khi listener xử lý thành công nhưng offset chưa commit, rebalance/restart có thể đọc lại. Một test happy path group assignment không chứng minh exactly-once. Để test idempotency:
- Gửi cùng `eventId` hai lần.
- Consumer dùng dedupe store/unique constraint.
- Assert một business side effect cho eventId.
- Kiểm offset/DB transaction boundary riêng.
- Với Kafka transactions, hiểu `read_committed`, producer transactions, processing guarantees trong **Kafka** và DB side effects ngoài Kafka.

## 11. Retry, dead-letter và poison messages

### 11.1. Kafka error handling

Spring Kafka có `DefaultErrorHandler` và `DeadLetterPublishingRecoverer` cho retry/DLT routing. Một message lỗi có thể được retry nhiều lần, đi tới `orders.DLT` hoặc bị xử lý theo recovery policy. Test cần xác định:
- Retry budget/backoff.
- Không block partition vô hạn.
- DLT topic name và payload/headers.
- Consumer group có thể tiếp tục sau poison record.
- Idempotency khi retry.
- DLT topic riêng trong integration tests.

Không giả định `@KafkaListener` auto-commit behavior giống một `@Transactional` JPA; offset commit và DB commit là hai boundaries.

### 11.2. RabbitMQ NACK/requeue/DLX

Trong Rabbit:
- Listener exception có thể dẫn đến requeue hoặc reject tùy container settings.
- `basicNack(requeue=true)` có thể redeliver liên tục.
- `basicReject(requeue=false)` có thể dead-letter nếu queue có `x-dead-letter-exchange`; không có DLX, message có thể bị drop.
- DLQ và routing cần được khai báo **trước publish**.
- Policy/classic/quorum queue behavior có thể khác nhau.

Khi test DLQ, dùng **queue/exchange riêng** cho main và DLQ, bounded await ở DLQ, assert headers/messageId và lý do reject. Sau test cleanup đúng những resources đó. Không dùng production DLX trong CI.

### 11.3. Duplicate không chỉ do broker

Duplicate có thể xuất hiện vì producer retry, client HTTP gửi lại, outbox relay retry sau broker ACK nhưng trước DB state update, consumer restart hoặc worker logic gửi event nhiều lần. Dùng eventId/idempotency key, không dựa vào “messageId tự sinh” có thể đổi qua mỗi retry.

### 11.4. Transactional outbox

Nếu database commit rồi producer publish có thể mất event khi app crash, dùng **transactional outbox**: ghi business row và outbox row cùng DB transaction; relay publish từ committed outbox; consumer idempotent. Test này cần ranh giới DB + broker, khác với một test `KafkaTemplate.send().get()` đơn thuần.

## 12. Readiness và async synchronization

### 12.1. Kafka listener assignment là bước thực

`@SpringBootTest` context có thể đã tạo listener bean nhưng Kafka consumer chưa nhận partitions. Gửi record với group mới và `auto-offset-reset=latest` lúc này có thể khiến test miss record. Spring Kafka test helper:

~~~java
ContainerTestUtils.waitForAssignment(
        registry.getListenerContainer("ordersListener"), 2);
~~~

Đoạn này cần Spring Kafka Test dependency và listener ID thực. Chỉ assert assignment là **precondition**; vẫn phải đợi handler receipt/side effect.

### 12.2. RabbitMQ listener readiness

Rabbit listener container cần broker connection, queue declarations và consumer registration. Nếu queue tồn tại và message được publish trước listener attach, broker có thể giữ message cho tới khi consumer nhận, không giống một Kafka new group ở `latest` bị miss records trước join. Nhưng gửi trước khi exchange/queue/binding tồn tại có thể bị unroutable hoặc mất. Test Rabbit nên đảm bảo declaration trước publish, sau đó chờ bounded message receipt.

### 12.3. Không dùng Thread.sleep

Sai:

~~~java
template.send(topic, key, payload);
Thread.sleep(1000);
assertThat(inbox.size()).isEqualTo(1);
~~~

Đúng hơn:
- Đợi producer broker ACK riêng (nếu contract).
- Đợi consumer assignment/queue declaration khi cần.
- Dùng `BlockingQueue.poll(timeout)` hoặc Awaitility.
- Assert đúng `eventId` và payload.
- Nếu timeout, in logs/metadata/consumer assignment, không lặp sleep tùy ý.

### 12.4. Bounded await chống treo CI

Nên có budget hợp lý:
- Broker/container startup có Testcontainers wait/readiness.
- Producer send result `.get(15s)`.
- Consumer receive `poll(10s)`.
- Business DB readback có bounded eventually assertion nếu eventual consistency là contract.
- JUnit tổng thời gian có upper bound, tránh preemptive timeout phá transactional ThreadLocal nếu test có `@Transactional`.

Đặt timeout lớn có căn cứ theo broker startup/CI, nhưng không biến test thành 5 phút chờ một resource bị cấu hình sai.

## 13. Topic/queue provisioning và cleanup

### 13.1. Kafka NewTopic vs broker auto-create

Trong Spring Boot, `NewTopic` bean + `KafkaAdmin` giúp khai báo topic có partition count/replication factor rõ. Dựa vào Kafka auto.create.topics.enable có thể tạo topic với số partitions khác expected và gây false-positive.

Nếu test group sharing cần hai partitions, phải tạo topic đúng **2 partitions**, rồi đợi metadata. Không nên tạo topic bằng một publish nhầm trước khi config đúng.

### 13.2. Rabbit admin declarations

Spring AMQP `RabbitAdmin`/`AmqpAdmin` tạo queue/exchange/binding. Một queue có durability/auto-delete/exclusive semantics cố định; declare lại cùng tên với arguments khác có thể trả `PRECONDITION_FAILED`. Unique test names tránh va chạm nhưng không thay cho việc hiểu queue options.

### 13.3. Cleanup Rabbit đúng ownership

- Xóa queues test tự tạo.
- Xóa exchanges test tự tạo.
- Không xóa system exchanges hoặc shared production routes.
- Không purge shared queues khi test khác có thể dùng.
- Cleanup trong `finally` để vẫn cố gắng sau assertion fail; ephemeral container là safety net nếu JVM bị kill.
- Nếu listener đang chạy trên queue, stop listener container trước khi xóa queue nếu test chủ động delete nó trong cùng Spring context; lab không xóa listener queue giữa tests.

### 13.4. Cleanup Kafka đúng ownership

- Nếu mỗi test có KafkaContainer riêng, shutdown container cuối class là cách cô lập đơn giản.
- Nếu broker shared, delete test-owned topics bằng AdminClient và đợi completion; không delete topic của test khác.
- Đừng reset group offsets trên shared consumer group.
- Unique topic names giúp giảm collision, nhưng có thể tạo hàng nghìn topics trên shared broker; cần lifecycle cleanup/quotas.

## 14. Mẫu lựa chọn ranh giới test

| Mục tiêu | Kiểu test | Setup |
| --- | --- | --- |
| Domain event serialization/validation | Pure JUnit | JSON/Avro fixture, schema validator |
| Logic handler nhận message | Unit test handler class | Mock repository/gateway, kiểm business rules |
| Producer record key/header | KafkaTemplate contract test | Embedded broker hoặc Testcontainers |
| Kafka group/partition semantics | Testcontainers Kafka | Unique topic/group, clients thật |
| Rabbit queue routing/fanout | Testcontainers RabbitMQ | Unique exchange/queues/bindings |
| Offset resume/rebalance | Integration/fault tests | Group restart/seek/assignment control |
| Retry/DLT | Broker integration tests | DLT resources/test failure handler |
| Durable outbox | DB + broker integration | DB transaction, relay, eventId |
| Auth/TLS/ACL | Security integration | Broker sandbox credentials/certs |
| Multi-broker failover/durability | Production-like cluster | Không chỉ single-node container |
| REST request tạo message | `@SpringBootTest` + broker | HTTP service + async listener, cleanup |

Các mức test bổ sung nhau. Không cần Kafka Testcontainers cho mọi phép tính domain; cũng không coi unit test mock `KafkaTemplate` đã kiểm broker routing.

## 15. Lỗi thường gặp và cách khắc phục

### 15.1. Kafka consumer không nhận message

Kiểm topic/partition có tồn tại, bootstrap server có đúng Testcontainers endpoint không, listener đã assignment chưa, group ID có bị dùng chung không, `auto-offset-reset` có đang `latest` không, offset đã commit từ test trước chưa, serializer/deserializer có khớp.

Không chữa mọi lỗi bằng cách sleep thêm vài giây: consumer có thể đọc sai topic hoặc group.

### 15.2. Kafka test đôi lúc chỉ thấy một nửa records

Có thể hai test classes dùng cùng `group.id` và vô tình share partition assignment. Với cùng group, **chia** workload là expected. Nếu muốn mỗi test nhận mọi record, dùng group khác nhau hoặc topic riêng.

### 15.3. Kafka test đọc records từ lần chạy trước

Topic shared còn retained log; group mới + `earliest` đọc từ đầu. Dùng unique topic/testRunId, hoặc lọc/seek có chủ đích. Đừng chỉ assert `count>=1`.

### 15.4. Kafka order assertion fail

Nếu records ở nhiều partitions, không có total order global. Chỉ assert ordering trong một partition/key partitioning thích hợp, hoặc dùng `containsExactlyInAnyOrder` khi business không cần ordering.

### 15.5. Kafka duplicate sau consumer restart

Offset commit xảy ra sau business action hoặc commit failed; record được redeliver. Thiết kế handler idempotent và test retry/rebalance semantics, không claim exactly-once mặc định.

### 15.6. Kafka Producer future PASS nhưng consumer timeout

Broker ack không chứng minh handler đã được gọi. Kiểm listener assignment, topic/partition/group, error handler, deserializer, poison event, test await. Không assert ngay sau `send`.

### 15.7. RabbitMQ publisher gửi nhưng không queue nào nhận

Có thể gửi sai exchange/routing key, queue chưa bind, hoặc message unroutable. Dùng queue/exchange declaration trước publish và publisher confirms/returns khi routing contract quan trọng.

### 15.8. RabbitMQ hai workers không cùng nhận một message

Đây là competing-consumer semantics của cùng queue. Nếu cần broadcast, tạo queue riêng cho từng subscriber và bind vào fanout/topic exchange.

### 15.9. RabbitMQ queue declaration PRECONDITION_FAILED

Một queue đã tồn tại với durability/exclusive/arguments khác. Dùng unique queue test resource, hoặc sửa declarations cho khớp configuration đã quản lý. Không xóa queue shared để làm test xanh.

### 15.10. Rabbit message bị xử lý lại

Consumer crash trước ack, reject/requeue, retry hoặc connection loss có thể redeliver. Kiểm `redelivered` flag khi hữu ích nhưng không coi nó là idempotency token duy nhất; dùng event ID được quản lý bởi ứng dụng.

### 15.11. Rabbit listener có queue nhưng test bị race

Listener container có thể chưa register hoặc message publish trước binding. Queue tồn tại vẫn giữ message nhưng exchange route phải đúng. Dùng declarations và bounded poll; không dựa sleep.

### 15.12. Test @SpringBootTest fail context vì broker chưa start

Static `@Container` và `@ServiceConnection` cần dependencies testcontainers và annotation đúng. Kiểm container runtime, image, service connection factory và context initialization. Đừng trỏ test về broker production để “chạy nhanh”.

### 15.13. Spring context cache trỏ container đã dừng

JUnit Testcontainers static container dừng sau class; Spring TestContext cache context giữa classes có thể reuse connection details/clients cũ. Dùng Spring-managed container beans theo Boot docs, isolate contexts hoặc quản lý container lifecycle phù hợp.

### 15.14. Docker tests SKIPPED nhưng build exit 0

`@Testcontainers(disabledWithoutDocker=true)` có thể skip class khi Docker unavailable. CI integration phải yêu cầu Docker và Surefire `skipped=0`; không claim tests đã chạy khi thực tế không.

### 15.15. Chạy parallel tests gây message stealing

Shared Kafka group hoặc Rabbit queue khiến tests cạnh tranh. Dùng topic/group/queue riêng, kiểm correlation/eventId, không dùng global mutable probe.

### 15.16. DLT/DLQ đụng data của test khác

Tên default `orders.DLT` hoặc `dead-letter.queue` shared giữa tests có thể tích lũy message lỗi. Tạo dead-letter resources riêng, asserted event IDs và cleanup.

### 15.17. @DirtiesContext được dùng như cleanup broker

`@DirtiesContext` chỉ invalidates Spring ApplicationContext cache; không xóa Kafka topic/offset hay Rabbit queue. Dọn resource broker thực hoặc rely ephemeral container theo test ownership.

### 15.18. Kafka transaction bị coi tương đương DB transaction

Kafka transaction có phạm vi Kafka records/offsets theo API và config; không tự bao trùm một JDBC transaction ngoài Kafka. Nếu application ghi DB và gửi event trong một workflow bắt buộc atomic, cân nhắc transactional outbox và idempotency.

### 15.19. Rabbit consumer ack bị coi là business commit

Ack có thể xảy ra sau hoặc trước DB commit tùy container/handler config. Một consumer crash giữa DB commit và ack có thể dẫn tới duplicate. Test business side effect và ack/requeue policy độc lập.

### 15.20. Container đơn được coi giống production cluster

Single-node Kafka/RabbitMQ container kiểm protocol/routing cơ bản. Nó không chứng minh 3-node replication, rack-awareness, quorum failover, network partitions hoặc broker security policies. Với yêu cầu HA/SLA, cần test environment tương ứng.

## 16. Checklist bảo mật và tính lặp lại

- Không kết nối topic/queue production trong integration tests tự động.
- Không dùng credentials thật, customer data thật hoặc payment information trong messages test.
- Broker container dùng port động; không hard-code endpoints.
- Pin image tag/digest được phê duyệt khi cần reproducibility.
- Unique IDs namespaced theo test để tránh collision khi chạy song song.
- Producer/consumer serializers, headers và message schema được versioned.
- Consumer group ID thuộc test, không reuse group production.
- Kafka topic partitions/retention được provision có chủ đích.
- Rabbit exchange/queue/binding được declare trước publish.
- Không dùng `Thread.sleep` như readiness/synchronization.
- Dùng bounded await và cleanup in finally.
- Keep logs đủ để debug nhưng scrub secrets/PII.
- CI xác thực tests executed chứ không chỉ build status.
- Với parallel/group tests, không assert assignment member cụ thể nếu không có contract.
- Không khẳng định exactly-once khi chỉ có happy path.
- Có test negative/duplicate/retry/DLT khi business risk yêu cầu.
- Dữ liệu nhiều consumers phải được đọc đúng theo group/queue semantics.

## 17. Bài tập thực hành

1. Tạo Kafka topic hai partitions, hai consumers cùng group: quan sát partition assignment, assert union records chứ không đòi mỗi consumer đọc hết.
2. Thêm một group thứ hai với `earliest`, kiểm nó đọc cùng retained records nhưng offset độc lập.
3. Đổi new group từ `earliest` sang `latest`, gửi message trước/sau lúc assignment; giải thích những event bị miss và vì sao.
4. Tái sử dụng group cũ với committed offsets và giải thích vì sao `earliest` không replay toàn bộ.
5. Tạo topic per-test method bằng AdminClient, cleanup topic do method sở hữu.
6. Dùng cùng key cho ba Kafka records, kiểm partition ổn định khi partition count không đổi.
7. Gửi records vào hai partitions, thử assert global order và sửa assertion theo partition.
8. Giả lập Kafka consumer restart trước offset commit, đưa idempotency key vào handler.
9. Tạo RabbitMQ default exchange và unique queue, gửi một message, nhận từ queue.
10. Gắn hai consumers cùng queue và giải thích vì sao chỉ một consumer được giao mỗi delivery.
11. Dùng fanout exchange bind hai queues, chứng minh mỗi queue nhận bản sao riêng.
12. Dùng topic exchange pattern `orders.*` và `orders.#`, kiểm routing keys khớp khác nhau.
13. Cố tình publish trước khi tạo binding và quan sát unroutable behavior; thêm publisher returns/confirm handling.
14. Tạo DLQ riêng, reject một message không requeue và kiểm headers/payload ở DLQ.
15. Đặt `eventId`/`testRunId` vào payload, test lọc đúng event trong môi trường nhiều messages.
16. Chạy hai Spring test classes song song với cùng group/queue rồi đổi sang unique resource names.
17. Tắt Docker, chạy Maven tests và phân biệt `SKIPPED` với `PASS` trong Surefire.
18. Chuyển Kafka producer mock test sang broker Testcontainers, mô tả phần rủi ro nào mới được kiểm.
19. Dùng fake handler unit test cho validation/serialization, so sánh chi phí với broker integration.
20. Thiết kế outbox row + broker integration, kiểm một event duplicate không tạo hai business side effects.

## 18. Checklist trước khi merge

- [ ] Đã xác định backend là Kafka hay RabbitMQ/AMQP, không trộn terminology?
- [ ] Kafka topic/partition/group/offset semantics được hiểu đúng?
- [ ] Rabbit exchange/queue/binding/consumer semantics được hiểu đúng?
- [ ] Nếu cần broadcast, dùng independent Kafka groups hoặc independent Rabbit queues?
- [ ] Nếu cần workload sharing, dùng Kafka group hoặc Rabbit queue competition đúng?
- [ ] Resource names riêng theo class/test/run?
- [ ] Event IDs/correlation IDs được assert chính xác?
- [ ] Kafka group ID không vô tình chia sẻ giữa tests?
- [ ] Kafka `auto-offset-reset` phù hợp với position cần test?
- [ ] Topic partitions/replication và Rabbit bindings được provision trước send?
- [ ] Có consumer assignment/queue declaration readiness?
- [ ] Producer broker ACK và consumer processed outcome được kiểm khác nhau?
- [ ] Có bounded poll/await thay vì fixed `Thread.sleep`?
- [ ] Không assert global Kafka ordering giữa partitions?
- [ ] Không assert Rabbit workers chia workload đúng 50/50?
- [ ] Không dùng `@DirtiesContext` thay broker cleanup?
- [ ] Cleanup chỉ resource do test sở hữu, không phá shared topic/queue?
- [ ] Tests parallel có isolation thực và không dùng global mutable probes?
- [ ] Có retry/DLT/DLQ/idempotency tests theo domain risk?
- [ ] Docker CI chạy broker thật, không chỉ skip?
- [ ] Container lifecycle và Spring cached context đúng?
- [ ] Không chứa secrets/PII hoặc gửi message tới production?
- [ ] Versions Boot/Testcontainers/kafka-client/AMQP tương thích?
- [ ] Surefire reports được kiểm và lỗi async có diagnostic logs?

**Kết luận:** Kafka consumer group và RabbitMQ queue đều hỗ trợ chia việc, nhưng ở các abstraction khác nhau: **Kafka partition assignment theo group và offsets độc lập**; **RabbitMQ exchange định tuyến bản sao tới queues, consumers cùng queue cạnh tranh nhận delivery**. Test đáng tin cần resource ownership, topic/group/queue độc lập, eventId có thể đối chiếu, readiness và bounded await, cùng kiểm đúng broker acknowledgment versus business processing. Không chỉ gửi message rồi ngủ hoặc đếm một event bất kỳ. Khi hiểu chính xác topology và isolation, bạn có thể làm messaging integration tests nhanh hơn, ít flaky hơn và phát hiện lỗi routing/consumer group/ack thực sự.

## 19. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Apache Kafka messaging: https://docs.spring.io/spring-boot/3.5/reference/messaging/kafka.html
- Spring Boot 3.5 — AMQP / RabbitMQ: https://docs.spring.io/spring-boot/3.5/reference/messaging/amqp.html
- Spring Boot 3.5 — Testcontainers & service connections: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Kafka 3.3 — Testing: https://docs.spring.io/spring-kafka/reference/3.3/testing.html
- Spring Kafka 3.3 — @KafkaListener: https://docs.spring.io/spring-kafka/reference/3.3/kafka/receiving-messages/listener-annotation.html
- Spring Kafka 3.3 — Topic configuration: https://docs.spring.io/spring-kafka/reference/3.3/configuration/topic.html
- Spring Kafka 3.3 — Consumer offset commits: https://docs.spring.io/spring-kafka/reference/3.3/kafka/receiving-messages/message-listener-container.html
- Spring AMQP 3.2 — Annotation-driven Rabbit listeners: https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/async-annotation-driven.html
- Spring AMQP 3.2 — Sending messages: https://docs.spring.io/spring-amqp/reference/3.2/amqp/sending-messages.html
- Spring AMQP 3.2 — Listener acknowledgement modes: https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/async-consumer.html
- Testcontainers Java — Kafka module: https://java.testcontainers.org/modules/kafka/
- Testcontainers Java — RabbitMQ module: https://java.testcontainers.org/modules/rabbitmq/
- Testcontainers Java — JUnit 5: https://java.testcontainers.org/quickstart/junit_5_quickstart/
- Apache Kafka — Consumer concepts: https://kafka.apache.org/documentation/#consumerapi
- RabbitMQ — AMQP concepts (exchanges, bindings, queues): https://www.rabbitmq.com/tutorials/amqp-concepts
- RabbitMQ — Consumer acknowledgements & publisher confirms: https://www.rabbitmq.com/docs/confirms
- RabbitMQ — Consumer prefetch: https://www.rabbitmq.com/docs/consumer-prefetch
