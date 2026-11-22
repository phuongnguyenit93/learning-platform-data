# Cấu hình topic và partition trong Spring Kafka

Một hệ thống Spring Kafka có thể hoạt động tốt khi mới có một consumer và vài nghìn sự kiện mỗi ngày, nhưng gặp sự cố khi tăng lưu lượng: một partition quá tải, consumer bị idle, dữ liệu bị mất khi broker ngừng hoạt động, hoặc topic mới được tạo với cấu hình mặc định không đáp ứng SLA. Các vấn đề này thường bắt đầu từ **quyết định thiết kế và cấu hình topic/partition**, chứ không phải từ logic trong `@KafkaListener`.

Bài học thuộc **Spring Kafka Reliability Operations → Deployment và cấu hình**, hướng dẫn cách xác định số partition, replication factor, minimum in-sync replicas, retention, định tuyến message bằng key, cấu hình Spring Boot/Spring Kafka, triển khai thay đổi an toàn, kiểm thử và quan sát topic trong vận hành. Ví dụ dùng **Java 17, Spring Boot 3.x, Spring Kafka 3.x và Apache Kafka**, với các lệnh CLI trên môi trường kiểu Linux. Những con số được chọn là **ví dụ minh họa**, không phải thông số chuẩn cho mọi cluster.

## 1. Hiểu topic, partition, replica và consumer group

**Topic** là tên luồng sự kiện, chẳng hạn `orders.events.v1`. Mỗi topic gồm một hoặc nhiều **partition**; mỗi partition là một log có thứ tự offset riêng. Partition có một **leader replica** và có thể có những **follower replicas** trên các broker khác để tăng khả năng chịu lỗi.

```text
Topic: orders.events.v1

                    Kafka cluster
    +--------------------+--------------------+--------------------+
    | Broker 1           | Broker 2           | Broker 3           |
    |                    |                    |                    |
    | P0 leader          | P0 follower        | P0 follower        |
    | P1 follower        | P1 leader          | P1 follower        |
    | P2 follower        | P2 follower        | P2 leader          |
    +--------------------+--------------------+--------------------+

    P0: offset 0 -> offset 1 -> offset 2 -> ...
    P1: offset 0 -> offset 1 -> offset 2 -> ...
    P2: offset 0 -> offset 1 -> offset 2 -> ...
```

Trong sơ đồ, topic có 3 partition và replication factor 3. Mỗi partition có ba bản sao đặt trên ba broker; tại một thời điểm, chỉ **một leader** phục vụ đường ghi/đọc thông thường của partition. Follower đồng bộ dữ liệu từ leader và có thể được bầu làm leader theo cơ chế Kafka khi leader không còn sẵn sàng.

| Thành phần | Vai trò | Nhầm lẫn cần tránh |
| --- | --- | --- |
| Topic | Tên luồng dữ liệu | Topic không phải một hàng đợi duy nhất có thứ tự toàn cục nếu có nhiều partition |
| Partition | Đơn vị lưu trữ log, thứ tự offset, phân chia tải | Nhiều partition không làm một key đơn lẻ tự chạy song song |
| Offset | Vị trí record **trong một partition** | Offset 10 ở P0 không phải offset 10 ở P1 |
| Leader replica | Replica chịu trách nhiệm chính cho partition | Không phải mỗi replica đều là partition độc lập |
| Follower replica | Bản sao của partition | Follower không làm tăng số partition để chia việc cho consumer |
| Replication factor (RF) | Tổng số replica mong muốn của mỗi partition | RF=3 không có nghĩa có ba message nghiệp vụ |
| ISR | Những replica đang theo kịp leader theo tiêu chí Kafka | ISR có thể giảm khi broker hoặc network gặp lỗi |
| Consumer group | Các consumer phối hợp chia partition | Trong một group, một partition thường chỉ được gán cho một consumer tại một thời điểm |

### 1.1. Thứ tự được bảo đảm ở phạm vi nào?

Kafka bảo toàn thứ tự ghi trong **từng partition**. Nếu sự kiện của cùng một đơn hàng phải được xử lý theo thứ tự:

```text
ORDER_CREATED -> PAYMENT_AUTHORIZED -> ORDER_SHIPPED
```

thì nên dùng **cùng business key ổn định**, ví dụ `orderId`, để các sự kiện đó được định tuyến vào cùng partition theo chiến lược partitioning hiện hành. Không có bảo đảm thứ tự giữa các partition của một topic.

Lưu ý rằng thứ tự xử lý cuối cùng còn phụ thuộc concurrency và logic ứng dụng. Một listener tự gửi công việc sang thread pool bất đồng bộ có thể làm hoàn thành sự kiện sau trước sự kiện trước, dù Kafka giao record theo thứ tự offset. **Order trong partition không tự động là order của mọi side effect trong hệ thống**.

## 2. Những câu hỏi phải trả lời trước khi tạo topic

Trước khi chọn `partitions=6` và `replication-factor=3`, nên ghi rõ hợp đồng dữ liệu và tải:

1. **Loại sự kiện:** event theo entity, lệnh nghiệp vụ, audit log, CDC hay dữ liệu trạng thái mới nhất?
2. **Throughput:** số message/giây trung bình, cao điểm, kích thước message và tốc độ xử lý của consumer.
3. **Ordering key:** thứ tự cần giữ theo `orderId`, `customerId`, `accountId`, tenant hay toàn topic?
4. **Concurrency:** một consumer xử lý được bao nhiêu message/giây và dự kiến có bao nhiêu consumer instance?
5. **Retention:** cần giữ lịch sử 1 ngày, 7 ngày, 30 ngày hay chỉ giá trị mới nhất theo key?
6. **Reliability:** chịu được bao nhiêu broker lỗi, có chấp nhận ghi tạm ngừng để tránh mất dữ liệu hay không?
7. **Security:** ai được tạo topic, produce, consume, đọc message và xem metadata?
8. **Scale/change:** có dự kiến tăng partition, thay key/schema, di chuyển cluster hoặc replay dữ liệu lịch sử?

Ví dụ tài liệu quyết định:

```yaml
topic: orders.events.v1
purpose: Domain events for order lifecycle
key: orderId
partitions: 6
replicationFactor: 3
minInSyncReplicas: 2
cleanupPolicy: delete
retention: 7 days
producerAcks: all
consumerGroup: orders-worker
orderingScope: one orderId within one partition
```

Đây là **bản mô tả quyết định**, không phải một file cấu hình mà Kafka tự hiểu. Có thể đưa cấu hình thực vào công cụ provisioning, Spring Kafka `NewTopic`, CLI hoặc manifest của operator tương ứng.

## 3. Chọn số partition theo tải và concurrency

Partition là một trong những giới hạn song song quan trọng của consumer group. Giả sử topic có 3 partition:

```text
Topic: orders.events.v1
    P0 ----> Consumer A
    P1 ----> Consumer B
    P2 ----> Consumer C

Consumer D: không được gán partition trong cùng group
```

Nếu chạy 4 consumer cùng một group nhưng chỉ có 3 partition, tối đa 3 consumer có partition để đọc tại một thời điểm; consumer còn lại idle đối với topic này. Ngược lại, một consumer có thể xử lý **nhiều partition**.

### 3.1. Ước lượng ban đầu

Ví dụ:

| Thông số | Giá trị giả định |
| --- | ---: |
| Peak input | 9.000 message/giây |
| Năng lực một consumer worker | 2.000 message/giây |
| Số worker tối thiểu theo throughput | `ceil(9000/2000) = 5` |
| Partition dự kiến | 6 |
| Số replica ứng dụng consumer | 3 |
| Concurrency của mỗi replica | 2 |

Sáu partition cho phép triển khai tối đa sáu consumer threads có partition được gán, ví dụ 3 replica × 2 listener threads = 6 consumer trong cùng group. Nhưng phép tính này **chỉ là điểm xuất phát**, vì tốc độ xử lý thay đổi theo message size, DB latency, batch size, GC, network, rebalance và sự phân bố key.

Không có công thức đơn giản đảm bảo `partitions = peak throughput / worker throughput` sẽ luôn tối ưu. Cần benchmark trong môi trường gần production, có headroom cho burst và quan sát lag theo từng partition.

### 3.2. Không chọn partition chỉ bằng số pod

Số partition được lưu ở cấp topic, trong khi số pod/consumer có thể tăng giảm theo autoscaling. Ví dụ:

```text
6 partitions, 2 pods × concurrency 2 = 4 consumers
-> mỗi consumer có thể nhận 1-2 partitions

6 partitions, 3 pods × concurrency 2 = 6 consumers
-> tối đa 6 consumers đang làm việc

6 partitions, 5 pods × concurrency 2 = 10 consumers
-> một số consumer không được gán partition
```

Thêm pod chỉ tăng throughput nếu vẫn còn partition có thể chia, ứng dụng còn năng lực database/API và bottleneck không nằm ở một hot key.

### 3.3. Hot partition và key skew

Nếu key là `tenantId`, một tenant chiếm 80% lưu lượng có thể khiến partition chứa tenant đó bị quá tải. Các partition khác vẫn nhàn rỗi:

```text
Partition P0: 80% records  [HOT]
Partition P1:  8% records
Partition P2:  6% records
Partition P3:  6% records
```

Tăng số partition không tự chia một **key đơn lẻ** thành nhiều partition, vì mọi event cùng key cần giữ thứ tự đang được cố ý định tuyến cùng nơi. Các phương án phải đánh đổi rõ:

- Dùng key có độ phân tán tốt hơn, nếu nghiệp vụ không cần ordering theo tenant.
- Chia một tenant thành những sub-key như `tenantId + accountId`, nếu thứ tự theo account là đủ.
- Tách topic hoặc pipeline riêng cho nguồn nóng khi cần cách ly tải.
- Tối ưu xử lý consumer/DB thay vì chỉ tăng partition.

Không thêm salt ngẫu nhiên vào business key nếu cần bảo đảm thứ tự sự kiện theo key gốc.

## 4. Replication factor, ISR và khả năng chịu lỗi

Số partition quyết định khả năng chia tải; **replication factor** quyết định số replica của mỗi partition. Hai giá trị phục vụ những mục tiêu khác nhau.

Ví dụ với 3 broker:

```text
Topic orders.events.v1
  partitions = 6
  replication.factor = 3
  min.insync.replicas = 2

Producer:
  acks = all
```

Với cấu hình này, producer yêu cầu leader xác nhận theo `acks=all`, và Kafka chỉ chấp nhận ghi khi số ISR đáp ứng `min.insync.replicas=2`. Điều đó tăng khả năng một message đã được xác nhận vẫn tồn tại khi một broker lỗi, với điều kiện replication/leader election và hạ tầng hoạt động đúng.

| Tình trạng | ISR còn | `acks=all`, min ISR=2 | Ý nghĩa |
| --- | ---: | --- | --- |
| Ba replica đồng bộ | 3 | Ghi có thể thành công | Đáp ứng ngưỡng |
| Một broker lỗi/chậm | 2 | Ghi vẫn có thể thành công | Còn hai bản sao trong ISR |
| Hai broker lỗi/chậm | 1 | Ghi bị từ chối hoặc chờ/lỗi theo timeout | Ưu tiên tránh ghi khi không đủ replica |
| Leader mất, có ISR follower | Phụ thuộc replica còn sống | Có thể bầu leader mới | Độ sẵn sàng phụ thuộc leader election |
| Broker lỗi nhưng ứng dụng chỉ có RF=1 | Có thể không còn replica | Partition có thể không sẵn sàng | Không có bản sao dự phòng |

### 4.1. `acks=all` và `min.insync.replicas` phải đi cùng nhau

- `acks=0`: producer không chờ broker xác nhận.
- `acks=1`: leader trả ack sau khi ghi theo điều kiện của leader; dữ liệu đã ack vẫn có thể mất nếu leader lỗi trước khi follower đồng bộ.
- `acks=all`: producer chờ xác nhận theo các yêu cầu ISR của Kafka.
- `min.insync.replicas`: ngưỡng số replica đang in-sync cần có để tiếp tục ghi khi `acks=all`.

RF=3 nhưng `min.insync.replicas=1` không đem lại cùng mức bảo vệ ghi như RF=3/min ISR=2. Ngược lại, min ISR=3 yêu cầu cả ba replica trong ISR để ghi, nên một broker gặp sự cố có thể khiến write availability giảm. Đây là **đánh đổi giữa durability và availability**, không phải chỉ số càng cao càng tốt.

Không đặt `replication.factor` lớn hơn số broker sẵn sàng chứa replica theo ràng buộc của Kafka. Với cluster một broker dùng để phát triển/test, RF=3 không thể tạo thành công như trong production ba broker.

### 4.2. Không bật unclean leader election tùy tiện

Nếu cho phép một replica **không còn in-sync** trở thành leader khi không có ISR phù hợp, có nguy cơ mất dữ liệu đã được ghi trên leader cũ nhưng chưa có ở replica mới. Trong hệ thống ưu tiên độ bền, thông thường nên giữ `unclean.leader.election.enable=false` trừ khi đã phân tích rõ đánh đổi và chính sách khôi phục.

Replication chỉ bảo vệ khỏi một số lỗi broker; nó **không thay thế backup, kiểm soát xóa dữ liệu, phân quyền hoặc kế hoạch disaster recovery**. Nếu người vận hành xóa topic hoặc thay retention sai, ba replica có thể cùng mất lịch sử.

## 5. Tạo topic qua Kafka CLI

Trong production, nên quyết định **ai sở hữu topic provisioning**: đội platform, IaC/operator, deployment pipeline hay chính ứng dụng. Với topic có yêu cầu reliability, việc quản lý tập trung và review thay đổi thường an toàn hơn cho phép mọi service tự tạo topic.

Giả sử cluster có ít nhất ba broker, tạo topic như sau:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1:9092 \
  --create \
  --topic orders.events.v1 \
  --partitions 6 \
  --replication-factor 3 \
  --config min.insync.replicas=2 \
  --config retention.ms=604800000 \
  --config cleanup.policy=delete
```

`604800000` mili giây tương đương bảy ngày. `bootstrap-server` có thể là danh sách broker theo cấu hình mạng của cluster. Với cluster bảo mật, các lệnh Admin còn cần thông tin TLS/SASL, thường được cung cấp qua file cấu hình client có quyền truy cập hạn chế.

Kiểm tra topic sau khi tạo:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1:9092 \
  --describe \
  --topic orders.events.v1
```

Output có thể hiển thị partition count, replication factor, leader, replicas và ISR:

```text
Topic: orders.events.v1
PartitionCount: 6
ReplicationFactor: 3
Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
...
```

Đây là **output minh họa**, không phải một câu trả lời cố định từ broker. Danh sách leader/replicas/ISR thực tế phụ thuộc vào cluster. Trong vận hành, cần kiểm tra **mọi partition**, không chỉ partition đầu.

Xem topic-level overrides:

```bash
bin/kafka-configs.sh \
  --bootstrap-server broker-1:9092 \
  --entity-type topics \
  --entity-name orders.events.v1 \
  --describe
```

Một số giá trị Kafka có thể kế thừa từ broker defaults và không hiện thành override trong mọi cách hiển thị. Nếu cần đối chiếu cấu hình hiệu lực, dùng Kafka Admin API/công cụ platform phù hợp và ghi rõ cấu hình kế thừa.

### 5.1. `auto.create.topics.enable` không phải provisioning production

Kafka broker có tùy chọn `auto.create.topics.enable`. Nếu bật, một thao tác với topic chưa tồn tại có thể kích hoạt tạo topic theo mặc định của broker trong các điều kiện hỗ trợ. Đây là rủi ro nếu chỉ sai một ký tự topic name mà hệ thống vô tình tạo ra topic mới với số partition/RF không mong muốn.

Trong cluster được quản lý chặt, thường nên:

- Tạo topic tường minh bằng provisioning được kiểm soát.
- Vô hiệu broker auto topic creation nếu chính sách cluster cho phép.
- Giới hạn quyền `CREATE`/`ALTER`/`DELETE` bằng ACL hoặc RBAC phù hợp.
- Kiểm tra topic tồn tại và có cấu hình đúng trước khi deploy producer/consumer.

Đừng nhầm **broker auto creation** với **Spring `KafkaAdmin` có bean `NewTopic`**: chúng là hai đường tạo tài nguyên khác nhau và có thể được bật/tắt độc lập.

## 6. Định nghĩa `NewTopic` trong Spring Kafka

Spring Kafka có `KafkaAdmin` và `NewTopic` để khai báo topic bằng Java configuration. Một ứng dụng Spring Boot thường có thể tự cấu hình Kafka Admin khi dùng Kafka starter và có bootstrap servers phù hợp.

Ví dụ cho môi trường **local/test chỉ có một broker**:

```java
package com.example.kafka.config;

import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.kafka.config.TopicBuilder;
import org.apache.kafka.clients.admin.NewTopic;

@Configuration
public class LocalTopicConfiguration {

    @Bean
    @Profile({"local", "test"})
    NewTopic ordersEventsTopic() {
        return TopicBuilder.name("orders.events.v1")
                .partitions(3)
                .replicas(1)
                .config(TopicConfig.CLEANUP_POLICY_CONFIG,
                        TopicConfig.CLEANUP_POLICY_DELETE)
                .config(TopicConfig.RETENTION_MS_CONFIG, "86400000")
                .build();
    }
}
```

Ở local, RF=1 vì broker duy nhất không thể chứa ba replica. Không dùng môi trường local này để kết luận production với RF=3 chịu lỗi broker đúng như thiết kế.

Khi `KafkaAdmin` được phép chạy ở startup, nó có thể dùng `NewTopic` bean để tạo topic khi cần. **Không coi đoạn code trên là hệ thống GitOps tự reconcile mọi thay đổi topic đang tồn tại**: hành vi cập nhật tài nguyên phụ thuộc phiên bản Spring Kafka và loại cấu hình; một số thay đổi không thể thực hiện trực tiếp chỉ bằng chỉnh `NewTopic`.

### 6.1. Topic nên được quản lý ở đâu?

| Cách quản lý | Phù hợp khi | Cần kiểm soát |
| --- | --- | --- |
| `NewTopic` + `KafkaAdmin` | Local, test, service nhỏ được cấp quyền provision | Không tạo topic sai trong production; quyền startup |
| Kafka CLI / AdminClient | Điều tra hoặc thay đổi có kiểm soát | Review lệnh, audit, quyền operator |
| Terraform / platform IaC | Nhiều môi trường, review và drift management | State, thứ tự triển khai, khả năng rollback |
| Kubernetes operator như Strimzi | Kafka cluster được quản lý bằng CRD | Quyền trên CRD, reconciliation, các trường immutable/khó thay |
| Managed Kafka console/API | Cluster do nhà cung cấp quản lý | Hạn chế provider, quota, audit và quyền |

Ví dụ nếu production đã có topic do platform tạo, consumer service **không nhất thiết cần quyền CREATE topic**. Nó chỉ cần quyền đọc/ghi và truy cập consumer group theo hợp đồng vận hành.

## 7. Cấu hình Spring Boot producer/consumer cho topic đã provision

`application.yml` minh họa:

```yaml
app:
  kafka:
    topics:
      orders: orders.events.v1

spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true

    consumer:
      group-id: orders-worker
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        allow.auto.create.topics: false

    listener:
      concurrency: 3
      ack-mode: record
```

Các giá trị này minh họa **một consumer không transactional** có Spring container quản lý việc ghi nhận offset. Nếu dùng Kafka transactions, manual acknowledgment, batch listener hoặc retry/seek policy khác, cần cấu hình listener container theo **semantics riêng của trường hợp đó**; không sao chép `ack-mode` mà bỏ qua transaction manager.

`auto-offset-reset: earliest` chỉ có tác dụng khi group **không có committed offset hợp lệ** cho partition, hoặc theo các trường hợp offset không còn khả dụng. Nó không có nghĩa consumer sẽ đọc lại toàn topic mỗi lần khởi động. Trong production, lựa chọn `earliest`, `latest` hay `none` cần được thống nhất với chính sách bootstrap/replay, không để mặc định quyết định mất hoặc lặp dữ liệu.

### 7.1. Không trộn tên topic và business logic

Producer:

```java
package com.example.kafka.orders;

import java.util.concurrent.CompletableFuture;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> template;
    private final String topic;

    public OrderEventPublisher(
            KafkaTemplate<String, String> template,
            @Value("${app.kafka.topics.orders}") String topic) {
        this.template = template;
        this.topic = topic;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String eventPayload) {

        // Key ổn định để giữ event của cùng orderId
        // trên một partition khi partition count/partitioner không đổi.
        return template.send(topic, orderId, eventPayload);
    }
}
```

Consumer:

```java
package com.example.kafka.orders;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @KafkaListener(
        topics = "${app.kafka.topics.orders}",
        groupId = "${spring.kafka.consumer.group-id}")
    public void consume(ConsumerRecord<String, String> record) {
        String orderId = record.key();
        String payload = record.value();

        // Validate, process và ghi kết quả an toàn/idempotent.
        // Exception handling phải đi theo retry/DLT policy được duyệt.
        processBusinessEvent(orderId, payload);
    }

    private void processBusinessEvent(String orderId, String payload) {
        // Placeholder: thay bằng nghiệp vụ thực tế.
    }
}
```

Đây là **ví dụ cấu trúc**, không phải một event schema hoàn chỉnh. Với JSON/Avro/Protobuf, cấu hình serializer/deserializer tương ứng, xác thực schema và chính sách tương thích phiên bản phải được xác định riêng. Tránh log nguyên `eventPayload` nếu nó chứa dữ liệu nhạy cảm.

### 7.2. `concurrency` không tạo thêm partition

Nếu topic có 6 partition và listener container cấu hình `concurrency: 3`, một instance Spring thường khởi tạo 3 consumer trong cùng group. Nếu chạy 2 replica ứng dụng, tổng cộng có thể có 6 consumer trong group. Nhưng khi cùng group đã có những consumer khác, assignment phụ thuộc group membership và assignor.

```text
Topic: 6 partitions

Pod A / listener:
  Consumer A1 -> P0
  Consumer A2 -> P1
  Consumer A3 -> P2

Pod B / listener:
  Consumer B1 -> P3
  Consumer B2 -> P4
  Consumer B3 -> P5
```

Sơ đồ này chỉ minh họa một assignment có thể xảy ra. Kafka không hứa sẽ luôn phân bổ partition với thứ tự như vậy. Nếu deployment có 4 pod × concurrency 3 = 12 consumers cho 6 partitions, một số consumer sẽ không được gán partition của topic này.

## 8. Partition key và định tuyến message

Producer có thể gửi bằng key:

```java
kafkaTemplate.send("orders.events.v1", "order-101", "CREATED");
kafkaTemplate.send("orders.events.v1", "order-101", "PAID");
kafkaTemplate.send("orders.events.v1", "order-101", "SHIPPED");
```

Với cùng key và cấu hình partitioner/partition count giữ nguyên, các bản ghi sẽ thường đi cùng partition, nên consumer đọc chúng theo thứ tự offset. Nếu producer gửi **không có key**, client có thể chọn partition dựa trên chiến lược batching/sticky hoặc cơ chế partitioning của phiên bản client; không nên giả định phân bố round-robin cố định.

### 8.1. Chủ động chọn partition

Kafka producer API và `KafkaTemplate` cho phép chỉ định partition khi gửi:

```java
int partition = 2;

kafkaTemplate.send(
        "orders.events.v1",
        partition,
        "order-101",
        "ORDER_CREATED");
```

Cách này hữu ích trong một số giao thức tích hợp đặc biệt, nhưng ràng buộc ứng dụng vào topology vật lý. Khi số partition hoặc chính sách routing thay đổi, **code hardcode partition=2 có thể trở nên sai về thiết kế**. Thông thường business key ổn định và default partitioning phù hợp hơn.

Nếu cần custom partitioner, hãy kiểm tra tính deterministic, độ phân bố và tính ổn định giữa các producer versions. Không chỉ nhìn vào số partition mà bỏ qua chiến lược hashing và serialization key.

### 8.2. Thay số partition có thể thay đổi mapping của key

Với partition count ban đầu là 3:

```text
hash(order-101) % 3  -> P1
```

Sau khi tăng lên 6:

```text
hash(order-101) % 6  -> có thể là P4
```

Biểu thức trên chỉ mô tả nguyên lý của một số chiến lược hash partitioning, **không phải công thức đầy đủ cho mọi phiên bản Kafka producer**. Điểm quan trọng là: **cùng key có thể chuyển sang partition khác khi số partition tăng**.

Nếu hệ thống còn message cũ ở P1 nhưng message mới vào P4, hai consumer có thể xử lý song song và làm sai thứ tự nghiệp vụ theo `orderId`. Đây là một lý do không nên coi “tăng partition” là thay đổi hoàn toàn vô hại.

Nếu ordering theo key là ràng buộc nghiêm ngặt, cần thiết kế một kế hoạch migration, ví dụ:

1. Tạm dừng hoặc kiểm soát producer.
2. Drain/đối soát backlog trước khi đổi routing.
3. Tăng partition hoặc tạo topic version mới với định tuyến mới.
4. Chuyển consumer/producer theo một ranh giới dữ liệu rõ ràng.
5. Giám sát event ordering và idempotency trong giai đoạn cutover.

Nếu dùng custom partitioner, thay đổi thuật toán hashing cũng có rủi ro tương tự dù số partition không đổi.

## 9. Tăng partition và những thay đổi khó đảo ngược

Kafka cho phép **tăng số partition** của topic hiện có theo những điều kiện phù hợp:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1:9092 \
  --alter \
  --topic orders.events.v1 \
  --partitions 12
```

Lệnh này đổi topic từ 6 lên **12 partition tổng cộng**, không phải “thêm 12 partition”. Sau khi tăng:

- Consumer group có thêm cơ hội chia tải, nhưng phải rebalance/nhận assignment mới.
- Producer có thể phân phối key sang partition khác so với trước.
- Mỗi partition mới có offset bắt đầu riêng, không có dữ liệu lịch sử của các partition cũ.
- Tăng partition không di chuyển dữ liệu hiện có từ P0–P5 sang P6–P11 để cân bằng quá khứ.
- Số log segment, file handle, metadata và khối lượng quản lý của cluster tăng.

**Kafka không hỗ trợ giảm số partition của một topic bằng thao tác alter thông thường.** Nếu đã tạo quá nhiều partition, kế hoạch giảm thường cần topic mới, chuyển dữ liệu/routing và consumer cutover.

### 9.1. Đổi replication factor không giống tăng partition

Replication factor không nên được coi là một tham số luôn sửa được bằng `kafka-topics.sh --alter` tương tự partition count. Để thay đổi nơi lưu replica hoặc tăng/giảm replication cho topic hiện hữu, phải dùng **quy trình reassignment replica** được cluster/operator hỗ trợ, kiểm tra broker capacity, tiến độ replication và leader election.

Việc reassign có thể tạo I/O/network load lớn. Cần triển khai có kiểm soát, quan sát ISR và không làm thay đổi cấu hình quan trọng khi cluster đang mất replica hoặc dưới tải khẩn cấp.

### 9.2. Chuẩn bị rollback plan

Trước khi tăng partition, ghi lại:

```text
Topic name / environment
Current partition count / replicas / min ISR
Producer key/partitioner strategy
Consumer groups and current lag
Peak message rate / partition skew
Plan to pause/drain or version topics
Validation after change
Recovery plan if ordering/business output is affected
```

Không thể “rollback” bằng cách giảm partition trực tiếp nếu thay đổi đã được áp dụng. Vì vậy phương án đảo ngược thường là **chuyển producer/consumer sang topic version cũ hoặc topic mới** với dữ liệu đã đối soát, chứ không phải chỉnh số partition về giá trị trước.

## 10. Cấu hình retention và cleanup policy

Topic configuration không chỉ gồm partitions và RF. **Retention** quyết định dữ liệu có thể được giữ lại trong log bao lâu hoặc đến khi đạt ngưỡng dung lượng; **cleanup policy** quyết định cách Kafka dọn các log segment.

| Thuộc tính | Công dụng | Chú ý vận hành |
| --- | --- | --- |
| `retention.ms` | Thời gian giữ dữ liệu theo chính sách retention | Không phải TTL xóa từng record chính xác tại mili giây hết hạn |
| `retention.bytes` | Giới hạn dung lượng log **trên từng partition** | Tổng dung lượng còn phụ thuộc số partition và replica |
| `cleanup.policy=delete` | Dọn các log segment theo retention | Thường dùng cho event stream cần giữ lịch sử có thời hạn |
| `cleanup.policy=compact` | Giữ bản ghi gần nhất theo key theo cơ chế compaction | Không phải ngay lập tức chỉ còn một record cho mỗi key |
| `cleanup.policy=compact,delete` | Kết hợp compaction và xóa theo chính sách | Cần hiểu retention và segment cleanup tương tác |
| `min.insync.replicas` | Ngưỡng ISR cho ghi với `acks=all` | Không liên quan trực tiếp đến số consumer |
| `unclean.leader.election.enable` | Cho phép bầu leader ngoài ISR trong tình huống đặc biệt | Có rủi ro dữ liệu khi bật |
| `max.message.bytes` | Kích thước record/batch tối đa ở cấp topic | Phải phối hợp với producer/consumer fetch limits |

### 10.1. Event stream và state/changelog cần chính sách khác nhau

Với các sự kiện theo thời gian:

```text
orders.events.v1
cleanup.policy = delete
retention.ms  = 604800000  (7 ngày)
```

Với trạng thái mới nhất của entity:

```text
orders.current-state.v1
cleanup.policy = compact
key             = orderId
value           = trạng thái mới nhất
```

Một topic compacted vẫn có thể giữ **nhiều phiên bản của cùng key trong một khoảng thời gian**, vì compaction chạy theo cơ chế log cleaner và các ràng buộc segment. Message có value `null` (tombstone) có ý nghĩa xóa key trong log compacted và phải được thiết kế cẩn thận với consumer/replay.

### 10.2. Dung lượng đĩa và replication

Ví dụ, một partition lưu 100 GiB dữ liệu logic và RF=3 có thể cần xấp xỉ **300 GiB dung lượng replica**, chưa tính index, segment, overhead và phân bố broker. Với nhiều partition, cần tổng hợp dung lượng theo topic, thời gian retention, peak ingestion và tỷ lệ nén thực tế.

Không suy ra dung lượng bằng số message × kích thước payload thô mà bỏ qua compression, overhead protocol, index và replication. Cũng cần kiểm tra quota và giới hạn disk/network của managed Kafka provider.

## 11. Cấu hình bảo mật và tách môi trường

Một deployment đáng tin cậy không nên vô tình produce dữ liệu production vào topic của dev hoặc tạo topic mới do typo:

```text
dev.orders.events.v1
stg.orders.events.v1
prod.orders.events.v1
```

Đây là một chiến lược đặt tên **nếu tổ chức chia sẻ cluster**. Nếu mỗi môi trường có cluster độc lập, topic có thể giữ cùng tên `orders.events.v1` nhưng phân tách qua bootstrap servers và quyền truy cập. Điều quan trọng là policy rõ ràng, không nhất thiết mọi hệ thống đều thêm prefix môi trường.

Các kiểm soát nên có:

- Bootstrap servers và cluster identity được cung cấp từ cấu hình triển khai, không hardcode production endpoint vào source.
- Producer chỉ có quyền WRITE/DESCRIBE cần thiết; consumer có READ/DESCRIBE trên topic và quyền group tương ứng.
- Quyền CREATE/ALTER/DELETE topic dành cho provisioning principal, không phải mọi application service.
- TLS/SASL hoặc cơ chế authentication/authorization theo cluster; secret lưu trong secret manager.
- Phân biệt service account theo môi trường, có rotation và audit.
- Schema registry/compatibility nếu dùng Avro, Protobuf hoặc JSON Schema.
- Quota để một workload quá tải không làm ảnh hưởng toàn cluster.

Không log raw credentials, SASL JAAS config, access token hoặc message payload nhạy cảm khi troubleshooting. Topic compaction/retention không thay thế chính sách bảo vệ dữ liệu cá nhân.

## 12. Quy trình deployment an toàn: topic trước, service sau

Một thứ tự triển khai gợi ý:

```text
1. Review topic contract
         |
         v
2. Provision/verify topic
         |
         +--> partitions / replication / ISR
         +--> retention / cleanup / ACL
         |
         v
3. Verify schema + serializer/consumer contract
         |
         v
4. Deploy producer/consumer với cấu hình topic mới
         |
         v
5. Smoke test có kiểm soát
         |
         v
6. Monitor lag, partition skew, ISR và errors
```

Với topic mới:

1. Kiểm tra cluster có đủ broker/rack capacity cho replication mong muốn.
2. Tạo topic bằng công cụ provisioning có audit.
3. Kiểm tra leader/replica/ISR trên tất cả partition.
4. Đảm bảo credentials/ACL cho application principal đã được cấp.
5. Cấu hình producer `acks=all` và idempotence theo yêu cầu.
6. Triển khai consumer với group ID/chính sách offset rõ.
7. Gửi một message thử trong kênh an toàn, xác nhận key, partition, schema và kết quả xử lý.
8. Bật giám sát và alert trước khi tăng lưu lượng.

Nếu thay đổi trên topic đang phục vụ dữ liệu thật, cần kế hoạch canary/cutover và khả năng đối soát message; không chỉ gọi lệnh alter lúc traffic cao rồi giả định mọi consumer tự điều chỉnh mà không có tác động.

### 12.1. Topic contract nên được version hóa

Tên `orders.events.v1` có thể phản ánh contract sự kiện. Khi đổi key/ordering/schema một cách không tương thích, cân nhắc `orders.events.v2` với giai đoạn dual-publish hoặc dual-read đã được kiểm soát, thay vì sửa ngầm cách routing của topic cũ.

Nếu dual-publish, phải thiết kế **idempotency** cho downstream và xác định ranh giới dữ liệu nào đang là source of truth. Hai topic có thể nhận sự kiện vào thời điểm khác nhau; không mặc định trạng thái nhất quán giữa chúng chỉ vì producer gọi hai lần `send()`.

## 13. Test topic và partition với Embedded Kafka

Trong local/test, `spring-kafka-test` có `@EmbeddedKafka` để khởi tạo broker nhúng và topic có số partition xác định. Test có thể kiểm tra:

1. Topic tồn tại với partition count mong đợi.
2. Các message có cùng key được định tuyến về cùng partition khi topology không đổi.
3. Producer gửi vào partition chỉ định hợp lệ.
4. Consumer group nhận được dữ liệu theo cấu hình listener.

**Embedded Kafka một broker không đủ để chứng minh fault tolerance RF=3/min ISR=2.** Những kiểm tra replication, ISR khi broker chết, leader election và rolling upgrade cần một Kafka cluster test nhiều broker hoặc một môi trường integration chuyên dụng.

### 13.1. Dependency test

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

### 13.2. Test metadata và key routing

Đoạn test dưới đây dùng Spring Boot auto-configuration để tạo `KafkaTemplate<String,String>`, rồi kiểm tra metadata từ broker:

```java
package com.example.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest(
    classes = TopicPartitionTest.TestApp.class,
    properties = {
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer"
    }
)
@EmbeddedKafka(
    partitions = 3,
    topics = "orders.test.v1",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class TopicPartitionTest {

    static final String TOPIC = "orders.test.v1";

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {}

    @Autowired
    EmbeddedKafkaBroker broker;

    @Autowired
    KafkaTemplate<String, String> template;

    @Test
    void topicHasThreePartitions() throws Exception {
        Map<String, Object> props = Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                broker.getBrokersAsString());

        try (AdminClient admin = AdminClient.create(props)) {
            Map<String, TopicDescription> topics =
                    admin.describeTopics(List.of(TOPIC))
                            .allTopicNames()
                            .get(10, TimeUnit.SECONDS);

            assertThat(topics.get(TOPIC).partitions()).hasSize(3);
        }
    }

    @Test
    void sameKeyUsesSamePartitionWhenTopologyIsStable()
            throws Exception {

        RecordMetadata first = template
                .send(TOPIC, "order-101", "CREATED")
                .get(10, TimeUnit.SECONDS)
                .getRecordMetadata();

        RecordMetadata second = template
                .send(TOPIC, "order-101", "PAID")
                .get(10, TimeUnit.SECONDS)
                .getRecordMetadata();

        assertThat(first.partition()).isEqualTo(second.partition());
        assertThat(first.topic()).isEqualTo(TOPIC);
        assertThat(second.offset()).isGreaterThan(first.offset());
    }
}
```

Test này dùng topic cố định của broker test, không đưa ra cam kết cùng key sẽ luôn vào cùng partition **sau khi tăng partition hoặc đổi thuật toán partitioner**. Để kiểm tra RF/min ISR, cần dùng cluster nhiều broker; topic do `@EmbeddedKafka` tạo ở đây thường có RF=1.

### 13.3. Kiểm tra listener concurrency và assignment

Với một topic ba partition, có thể khai báo:

```java
@KafkaListener(
    topics = "orders.test.v1",
    groupId = "orders-test-group",
    concurrency = "3")
public void consume(ConsumerRecord<String, String> record) {
    // Ghi nhận topic/partition/offset để test.
}
```

Đoạn code là fragment listener; cần class Spring bean và import tương ứng. Trong integration test, hãy gửi các record **chỉ định partition 0, 1 và 2** để bảo đảm có dữ liệu trên mỗi partition, chờ listener được assign đủ partition trước khi gửi, rồi kiểm tra mỗi record được xử lý đúng một lần theo kịch bản cô lập.

Đừng dựa vào việc phát 30 message với 30 key ngẫu nhiên rồi cho rằng Kafka chắc chắn chia đúng 10 message cho mỗi partition: hash distribution không hứa cân bằng tuyệt đối cho một mẫu nhỏ.

### 13.4. Test replication và ISR bằng cluster ba broker

Đây là một test thuộc **tầng hạ tầng**, không phải unit test:

1. Tạo cluster Kafka ba broker trong môi trường test cô lập.
2. Provision topic có 3 partition, RF=3, min ISR=2.
3. Chạy producer `acks=all`, xác nhận ghi và đọc thành công.
4. Dừng một broker, chờ leader/ISR ổn định, xác nhận đường ghi vẫn đáp ứng policy khi còn đủ ISR.
5. Dừng thêm một broker hoặc làm ISR giảm dưới hai, xác nhận producer nhận lỗi hoặc timeout đúng như contract.
6. Khôi phục broker, kiểm tra ISR trở lại đầy đủ và không mất những record đã commit theo điều kiện test.

Không cố mô phỏng RF=3 trên một embedded broker duy nhất. Khi test failover, cần timeout có giới hạn, biết rõ broker nào là leader/follower và không kết luận từ một lần sleep ngẫu nhiên. Với managed Kafka, khả năng tắt broker có thể bị hạn chế, nên dùng môi trường Kafka chuyên dụng cho chaos test.

## 14. Quan sát topic và partition sau deployment

Một topic “đã tạo thành công” vẫn có thể hoạt động kém hoặc không đáp ứng độ bền. Dashboard cần quan sát cả **producer, broker, partition và consumer group**:

| Nhóm | Chỉ số/sự kiện cần xem | Ý nghĩa |
| --- | --- | --- |
| Broker/topic | Under-replicated partitions | Replica không theo kịp leader |
| Broker/topic | Offline partitions / unavailable leaders | Partition có thể không phục vụ |
| Replication | ISR shrink/expand | Độ an toàn ghi biến động |
| Producer | Record send rate, error rate, retries | Lỗi ghi hoặc tải tăng |
| Producer | Record latency và timeout | Bottleneck broker/network/ISR |
| Partition | Bytes in/out, messages in theo partition | Hot partition, key skew |
| Consumer group | Lag theo partition | Một partition bị tụt lại |
| Consumer | Rebalance frequency, poll/processing latency | Assignment thay đổi hoặc xử lý chậm |
| Storage | Disk usage, log size, retention/cleanup activity | Nguy cơ hết đĩa hoặc xóa dữ liệu ngoài dự kiến |
| Security | Authorization failures / unknown topic | ACL hoặc provisioning sai |

Một ví dụ diễn giải:

```text
Topic: orders.events.v1 (6 partitions)

P0 lag: 100
P1 lag: 80
P2 lag: 110
P3 lag: 95
P4 lag: 65,000   <-- cần điều tra
P5 lag: 90
```

Lag rất cao ở riêng P4 có thể do **hot key, consumer gắn P4 bị lỗi, retry poison record hoặc DB/API downstream chậm**. Tăng số pod ngay chưa chắc giúp vì trong cùng consumer group một partition không được chia đồng thời cho nhiều consumer theo cơ chế assignment thông thường.

### 14.1. Tránh metric cardinality cao

Các nhãn có số lượng hữu hạn như `topic`, `partition`, `consumer_group`, `client_id`, `error_code` có thể hữu ích tùy quy mô cluster. Không dùng `orderId`, `customerId`, message key hoặc offset làm time-series metric label: số lượng chuỗi sẽ tăng cực lớn và có thể làm lộ thông tin.

Trong log chẩn đoán, có thể ghi `topic`, `partition`, `offset` và execution/correlation reference đã được duyệt; tránh dump toàn bộ payload hoặc credentials.

## 15. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Tạo topic RF=3 trên local một broker thất bại | Không đủ broker cho replication | RF=1 cho local hoặc dựng cluster ba broker |
| Producer báo `UNKNOWN_TOPIC_OR_PARTITION` | Topic chưa tạo, sai tên hoặc metadata chưa cập nhật | Verify provisioning, bootstrap servers và ACL |
| Broker tự tạo topic sai cấu hình | `auto.create.topics.enable` được bật, typo topic | Provision tường minh, hạn chế quyền và auto create |
| Consumer mới không đọc dữ liệu lịch sử | Group chưa có offset và `auto-offset-reset=latest` | Chọn bootstrap offset policy có chủ đích |
| Một số consumer idle | Consumer trong group nhiều hơn partition | Giảm concurrency/pod hoặc điều chỉnh topology |
| Một partition lag cực cao | Hot key hoặc processor chậm | Kiểm tra key skew, capacity và ordering contract |
| `acks=all` bị timeout khi broker lỗi | ISR còn thấp hơn `min.insync.replicas` | Khôi phục replica/cluster, không hạ durability vô tội vạ |
| Dữ liệu cùng order bị xử lý sai thứ tự sau khi tăng partition | Cùng key bị map sang partition mới | Migration plan có drain/order boundary hoặc topic versioning |
| Retention xóa dữ liệu sớm hơn nhu cầu replay | `retention.ms/bytes` không đủ | Tính lại retention, storage budget và replay SLA |
| Topic compacted vẫn có record cũ | Compaction không tức thời | Hiểu log cleaner/segment semantics |
| Tăng partition không cân bằng dữ liệu quá khứ | Kafka không di chuyển record cũ sang partition mới | Điều chỉnh tải tương lai, không kỳ vọng rebalance lịch sử |
| Consumer group rebalance liên tục | Deployment/poll timeout/instance churn | Theo dõi membership, thời gian xử lý, cấu hình group |
| Application startup không provision được topic | Service thiếu CREATE hoặc broker chưa sẵn sàng | Provision trước deployment hoặc cấu hình KafkaAdmin phù hợp |
| Dùng topic config trong Java làm thay đổi toàn bộ topic hiện hữu | Hiểu nhầm `NewTopic` là full reconciliation | Dùng quy trình operator/IaC và verify post-change |
| Message key là random UUID trên mỗi event của cùng order | Không giữ ordering theo order | Dùng key theo business entity đã xác định |

## 16. Checklist trước khi đưa topic vào production

**Hợp đồng dữ liệu**

- Topic có tên/version rõ; schema và key được thống nhất giữa producer/consumer.
- Ordering scope được tài liệu hóa theo entity/partition.
- Có kế hoạch replay, retention và thời hạn lưu dữ liệu.

**Reliability**

- Partition count được chọn dựa trên peak load và consumer capacity.
- Replication factor và min ISR phù hợp số broker, SLA và yêu cầu độ bền.
- Producer `acks`, idempotence và retry được cấu hình nhất quán.
- Có cảnh báo under-replicated/offline partition và disk pressure.

**Triển khai**

- Topic được provision/verify trước khi ứng dụng phụ thuộc vào nó.
- ACL/RBAC, TLS/SASL và secret management hoạt động đúng.
- Consumer group ID và `auto-offset-reset` được chọn có chủ đích.
- Concurrency/pod count không gây quá tải database hoặc API downstream.

**Thay đổi và phục hồi**

- Không tăng partition khi chưa phân tích ảnh hưởng tới key mapping và ordering.
- Replication reassignment, retention change và schema evolution đều có kế hoạch rollback/cutover.
- Có dashboard lag theo partition và các test cho broker failure/rebalance nếu cần độ tin cậy cao.
- Có quy trình idempotency và deduplication cho event bị giao lại sau crash/rebalance.

## 17. Bài thực hành

Giả sử cần xây pipeline `orders.events.v1` với peak 9.000 message/giây và ba replica consumer:

1. **Thiết kế topic:** lựa chọn 6 partition, RF=3, min ISR=2 trên cluster ba broker; giải thích vì sao số partition khác RF.
2. **Provision:** tạo topic bằng Kafka CLI hoặc công cụ IaC, cấu hình retention bảy ngày và cleanup delete.
3. **Verify:** dùng `kafka-topics.sh --describe` và `kafka-configs.sh --describe` để kiểm tra partition count, replicas, ISR và các topic overrides.
4. **Spring Boot:** cấu hình `spring.kafka.bootstrap-servers`, producer `acks=all`, idempotence, consumer group và concurrency=2 cho mỗi pod.
5. **Ordering:** gửi `CREATED`, `PAID`, `SHIPPED` cho cùng `orderId`. Xác nhận metadata cho thấy các event đi vào cùng partition trong topology ổn định.
6. **Distribution:** gửi nhiều orderId khác nhau, thống kê message count theo partition và tìm key skew. Đừng yêu cầu phân bố chính xác đều trong mẫu nhỏ.
7. **Partition scale:** mô phỏng tăng từ 6 lên 12 partition ở môi trường test. Kiểm tra một số key có thay đổi partition hay không, sau đó viết kế hoạch bảo toàn ordering khi cutover.
8. **Concurrency:** chạy hai pod × concurrency=3 cho topic sáu partition; sau đó chạy bốn pod × concurrency=3 và giải thích vì sao nhiều thread idle.
9. **Broker failure:** trên cluster test ba broker, dừng một broker rồi quan sát leader/ISR và producer `acks=all`; làm ISR giảm dưới hai để thấy chính sách durability được thực thi.
10. **Retention:** so sánh `cleanup.policy=delete` với `compact` trên topic test khác, giải thích vì sao compaction không lập tức loại mọi phiên bản cũ.
11. **Monitoring:** tạo dashboard throughput, lag từng partition, ISR, producer errors và disk usage; đặt ngưỡng cảnh báo hot partition.
12. **Deployment:** tách topic provisioning khỏi service runtime, xác minh ACL và viết checklist thay đổi cấu hình có rollback/cutover plan.

## 18. Tổng kết

**Topic và partition là những quyết định kiến trúc có hậu quả vận hành lâu dài.** Partition quyết định mức độ song song và phạm vi ordering; replication factor, ISR và producer acknowledgments tạo nên chính sách chịu lỗi; retention và cleanup policy xác định khả năng giữ/replay dữ liệu; còn key/partitioner quyết định record được phân bố như thế nào.

Trong Spring Kafka, `KafkaTemplate` và `@KafkaListener` cần được cấu hình nhất quán với topic thực tế, nhưng **không thay thế được quy trình provision, verify, monitor và thay đổi an toàn ở cluster**. Khi thiết kế từ đầu theo tải, ordering, độ bền và quyền truy cập — rồi kiểm chứng bằng Embedded Kafka và môi trường nhiều broker khi cần — hệ thống sẽ dễ mở rộng và phục hồi hơn mà không đánh đổi tính đúng đắn của luồng dữ liệu.
