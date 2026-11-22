# Xây producer idempotent trong Spring Kafka

Trong hệ thống xử lý sự kiện, producer có thể gửi một record tới Kafka nhưng không nhận được phản hồi vì mạng chậm, broker thay leader hoặc response bị mất. Kafka client thường retry để tăng khả năng gửi thành công. Nếu mỗi lần thử đều trở thành một record mới, consumer có thể xử lý trùng một sự kiện nghiệp vụ.

**Idempotent producer** là cơ chế của Apache Kafka nhằm ngăn một số trường hợp ghi trùng do **producer client tự retry cùng một batch**. Spring Kafka sử dụng Kafka Java client ở tầng dưới, nên có thể bật cơ chế này qua cấu hình producer mà không phải tự viết một thuật toán dedup ở `KafkaTemplate`.

Tuy nhiên, một producer được cấu hình `enable.idempotence=true` **không đảm bảo exactly-once cho toàn bộ ứng dụng**. Nó không tự hợp nhất hai lần ứng dụng gọi `send()`, không tạo transaction với PostgreSQL hay REST API, và không bảo đảm chống trùng khi một sự kiện được phát lại sau khi process chết rồi khởi động lại.

Bài thực hành **Xây producer idempotent** thuộc chương **Thực hành vận hành** của **Spring Kafka Reliability Operations**. Chúng ta sẽ cấu hình producer, viết mã gửi sự kiện có identity ổn định, kiểm thử với Kafka thật/Embedded Kafka, thử lỗi và lập quy tắc vận hành.

**Ngữ cảnh ví dụ:** Java 17, Spring Boot 3.x, Spring Kafka 3.x và Apache Kafka brokers có hỗ trợ idempotent producer. Với Spring Kafka 4.x hoặc Kafka client thế hệ khác, cần kiểm tra API, yêu cầu JDK và tài liệu tương ứng với dependency thực tế.

## 1. Kết quả cần đạt

Sau bài thực hành, người học có thể:

1. Giải thích vì sao producer retry có thể tạo duplicate khi không dùng idempotence.
2. Nắm ý nghĩa của producer ID, epoch và sequence number ở mức khái niệm.
3. Cấu hình `enable.idempotence`, `acks`, `retries` và `max.in.flight.requests.per.connection` đúng quan hệ.
4. Viết `KafkaTemplate` publisher với key và business event ID ổn định.
5. Phân biệt kết quả Kafka broker acknowledgment với kết quả xử lý nghiệp vụ tại consumer.
6. Biết khi nào gửi lại một record qua application-level retry có nguy cơ tạo duplicate.
7. Kết hợp transactional outbox và consumer idempotency khi phát sự kiện từ database.
8. Kiểm thử đường thành công, lỗi mạng/broker, producer restart và duplicate nghiệp vụ.
9. Giám sát retry, send latency, failure, buffer pressure và tính toàn vẹn record.
10. Thiết kế rollout, rollback và cách xử lý khi producer không chắc record đã được ghi hay chưa.

## 2. Vì sao retry có thể tạo record trùng?

Giả sử service gửi `OrderCreated`:

```text
orders-service                          Kafka broker
      |                                      |
      |------ Produce: event E ------------>|
      |                                      | lưu record E
      |<--------- ACK bị mất ----------------X
      |
      |------ Retry event E --------------->|
      |                                      | có thể lưu E lần nữa
      |<--------------- ACK -----------------|
```

Nếu không có cơ chế dedup tương ứng ở broker, retry có thể làm một sự kiện thành nhiều record trong log. Khi consumer thực hiện side effect như cộng điểm thưởng hoặc gửi email, duplicate có thể dẫn đến hành động lặp.

Trong những Kafka clients hỗ trợ idempotence, producer và broker phối hợp bằng producer identity cùng sequence numbers để broker nhận diện **batch retry trùng từ producer đó**. Mục tiêu là vẫn có thể retry khi lỗi tạm thời mà không nhân đôi record chỉ vì phản hồi bị mất.

### Các cấp độ cần tách riêng

| Cấp độ | Vấn đề | Cơ chế thường dùng |
| --- | --- | --- |
| Kafka client → broker | Cùng batch được Kafka client retry do lỗi gửi | **Idempotent producer**. |
| Ứng dụng → KafkaTemplate | Business event được ứng dụng gọi `send()` hai lần | Business ID + kiểm soát việc publish/unique key/outbox. |
| Database → Kafka | DB transaction commit nhưng process chết trước khi ghi nhận publish thành công | Transactional outbox, idempotent consumer và reconciliation. |
| Kafka → consumer | Offset chưa commit nên record được redeliver | Consumer idempotency hoặc Kafka transaction theo phạm vi được hỗ trợ. |
| Consumer → hệ thống ngoài | HTTP call thành công rồi consumer crash | Remote idempotency key, business dedup hoặc orchestration. |

**Không nhầm “record có cùng key” với “broker sẽ loại record trùng”.** Kafka partition key như `orderId` thường dùng để chọn partition và giữ thứ tự tương đối, không phải khóa unique làm Kafka tự loại mọi record có cùng key.

## 3. Cơ chế idempotence ở Kafka

Ở mức khái niệm, một producer idempotent sử dụng:

- **Producer ID (PID):** định danh do Kafka quản lý cho producer session.
- **Producer epoch:** hỗ trợ phân biệt các thế hệ/phiên producer trong những trường hợp liên quan.
- **Sequence number:** số thứ tự gắn với batch theo topic-partition trong cơ chế protocol.
- **Broker-side sequence tracking:** broker nhận diện các batch đã ghi hoặc thứ tự không phù hợp.

```text
Producer session P
    |
    +-- Partition orders.events-0
    |       batch seq=0 --> broker lưu
    |       batch seq=1 --> broker lưu
    |       batch seq=1 --> retry duplicate được nhận diện
    |
    +-- Partition orders.events-1
            batch seq=0 --> broker lưu
            batch seq=1 --> broker lưu
```

Sơ đồ giản lược để giải thích. Idempotence không yêu cầu developer tự tính sequence; Kafka producer client và broker xử lý các thông tin protocol này.

### Phạm vi bảo vệ chính

**Kafka client retry cùng một batch trong producer session** là trường hợp idempotence được thiết kế để xử lý. Nếu client gửi một record mới bằng một lời gọi `send()` khác, đó là một record mới dù payload, key hoặc event ID giống hệt record cũ.

Ví dụ:

```java
template.send("orders.events", "order-42", "{\"eventId\":\"evt-7\"}");
template.send("orders.events", "order-42", "{\"eventId\":\"evt-7\"}");
```

Hai lời gọi trên là **hai yêu cầu gửi riêng**. `enable.idempotence=true` không tự dedup chúng. Cơ chế của Kafka sẽ quản lý retry của mỗi yêu cầu, nhưng không biết rằng nghiệp vụ muốn “mỗi eventId chỉ được phát đúng một lần”.

### Producer restart là một ranh giới khác

Khi một ứng dụng gửi record, Kafka đã nhận nhưng process chết trước khi ứng dụng lưu trạng thái `SENT`, một instance mới có thể gửi lại cùng business event qua producer session mới. Idempotence client-side **không tạo một bản ghi nhớ nghiệp vụ bền vững qua mọi process restart**.

Vì vậy, cần thêm khóa sự kiện ổn định và cơ chế xử lý trùng ở lớp nghiệp vụ hoặc outbox/transaction phù hợp.

## 4. Điều kiện cấu hình idempotent producer

Các Kafka producer properties có liên hệ trực tiếp:

| Cấu hình | Giá trị phục vụ idempotence | Vai trò |
| --- | --- | --- |
| `enable.idempotence` | `true` | Bật cơ chế idempotent producer. |
| `acks` | `all` (tương đương `-1`) | Producer yêu cầu acknowledgment phù hợp từ in-sync replicas. |
| `retries` | Lớn hơn `0` | Cho phép Kafka client retry lỗi gửi có thể phục hồi. |
| `max.in.flight.requests.per.connection` | Nhỏ hơn hoặc bằng `5` | Đáp ứng ràng buộc thứ tự/sequence của idempotent producer. |
| `delivery.timeout.ms` | Ngân sách đủ cho request/retry | Giới hạn tổng thời gian producer cố gửi record. |
| `request.timeout.ms` | Giới hạn chờ request | Điều khiển timeout tầng request. |
| `linger.ms` | Có thể dùng để batch records | Ảnh hưởng batching/latency; không phải điều kiện bật idempotence. |

Trong các dòng Kafka client hiện đại, idempotence có thể đã **mặc định bật nếu không có cấu hình xung đột**. Tuy nhiên, đặt `enable.idempotence=true` một cách tường minh là lựa chọn dễ kiểm soát khi yêu cầu này thuộc hợp đồng tin cậy.

Nếu đặt `enable.idempotence=true` nhưng dùng `acks=1`, `retries=0` hoặc `max.in.flight.requests.per.connection` vượt ràng buộc, client có thể báo lỗi cấu hình. Với cấu hình idempotence ngầm định, một số tổ hợp xung đột có thể khiến idempotence không được bật như mong đợi. Đó là lý do nên xác minh **giá trị effective runtime**.

### Có cần `max.in.flight.requests.per.connection=1` không?

Không bắt buộc đối với idempotent producer hiện đại: **`<= 5`** là giới hạn quan trọng của Kafka client cho cơ chế này. Đặt bằng 1 có thể giảm mức song song và throughput, mặc dù đôi lúc phù hợp với một yêu cầu kiểm soát riêng.

Nếu idempotence bị tắt, nhiều in-flight requests kết hợp retry có thể dẫn tới record bị ghi lại không theo thứ tự mong đợi. Khi idempotence được bật đúng cách, Kafka client cung cấp những bảo đảm về ordering trong phạm vi topic-partition phù hợp với cơ chế producer.

### Vì sao `delivery.timeout.ms` quan trọng?

Một record có thể thất bại ở **delivery timeout** dù còn số lần retry cấu hình. Ví dụ:

```text
delivery.timeout.ms = 120000
request.timeout.ms  = 30000
linger.ms           = 5
retries             = số lớn
```

Producer không retry mãi mãi; nó còn bị giới hạn bởi ngân sách delivery. Với client hiện đại, `delivery.timeout.ms` cần được cấu hình đủ lớn so với `request.timeout.ms + linger.ms` và điều kiện ứng dụng.

**Kết quả timeout có thể không xác định:** khi ứng dụng nhận lỗi sau khi gửi, không mặc định record chắc chắn chưa nằm trên broker. Không vội phát lại một business event bằng producer session mới nếu không có kế hoạch dedup/reconciliation.

## 5. Độ bền Kafka: `acks=all` chưa phải toàn bộ câu chuyện

Idempotence và durability giải quyết những vấn đề khác nhau.

- **Idempotence:** hạn chế duplicate do client retry cùng batch.
- **`acks=all`:** xác định điều kiện acknowledgment của broker/ISR.
- **Replication factor:** số replicas của partition.
- **`min.insync.replicas`:** giới hạn số in-sync replicas tối thiểu để chấp nhận writes theo chính sách acknowledgment.
- **Unclean leader election:** lựa chọn liên quan đến đánh đổi tính sẵn sàng và khả năng mất dữ liệu.
- **Producer delivery timeout:** quyết định bao lâu producer cố gắng gửi.

Ví dụ cấu hình **production minh họa** cho topic:

```text
topic: orders.events
replication.factor = 3
min.insync.replicas = 2

producer:
  acks = all
  enable.idempotence = true
```

Với ba replicas và ít nhất hai in-sync replicas theo policy, hệ thống có thể giữ bảo đảm acknowledgment tốt hơn so với một broker đơn lẻ. Nhưng cần kiểm tra trạng thái ISR thực tế, loại lỗi, broker durability và cấu hình cluster.

Nếu ISR giảm dưới `min.insync.replicas`, produce request có thể bị từ chối hoặc thất bại tương ứng; đừng “sửa” bằng cách chuyển `acks` thành `0` hoặc `1` mà chưa đánh giá yêu cầu mất dữ liệu.

**Một Embedded Kafka broker trong test không chứng minh khả năng chịu lỗi của topic replication factor 3.** Nó phù hợp kiểm tra API/config/record delivery, còn durability phải được kiểm chứng trên cluster nhiều brokers.

## 6. Tạo dự án thực hành

Giả sử ứng dụng `orders-service` cần publish sự kiện `OrderCreated` lên topic `orders.events`.

Pipeline:

```text
Order command
    |
    v
Application validates / records business event
    |
    v
OrderEventPublisher
    |
    +-- eventId: ổn định theo sự kiện nghiệp vụ
    +-- key: orderId
    +-- value: JSON
    |
    v
KafkaTemplate<String, String>
    |
    v
Idempotent KafkaProducer
    |
    v
Kafka brokers: orders.events
```

### Dependency Gradle

Với Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'com.fasterxml.jackson.core:jackson-databind'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

Có thể dùng `spring-boot-starter-web` nếu cần HTTP API, nhưng publisher không phụ thuộc controller. Spring Boot dependency management nên quản lý tương thích giữa `spring-kafka` và `kafka-clients`; không ép version Kafka client bất kỳ chỉ để bật idempotence.

Trong project dùng Spring Boot starter cung cấp Jackson sẵn, dependency trực tiếp có thể không cần khai báo; ví dụ ghi rõ để xác định serializer JSON ở tầng ứng dụng.

### Topic

Topic ví dụ:

```text
orders.events
  partition 0
  partition 1
  partition 2
```

Chọn `orderId` làm Kafka record key để các sự kiện của **cùng đơn hàng** thường được route đến cùng partition với số partition/cấu hình partitioner ổn định. Đây là cơ chế phục vụ ordering theo key, **không phải dedup**.

Nếu tăng số partitions hoặc thay đổi partitioner, cùng key có thể được định tuyến khác so với lịch sử. Đừng suy luận có thứ tự toàn cục xuyên các partitions hoặc giữa những producers khác nhau chỉ vì key giống nhau.

## 7. Cấu hình Spring Boot producer idempotent

File `application.yml` minh họa:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      retries: 2147483647
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        linger.ms: 5
        compression.type: snappy
```

Những giá trị chỉ là **baseline thực hành**, không phải cấu hình tối ưu cho mọi hệ thống. `retries` được đặt lớn để `delivery.timeout.ms` trở thành một giới hạn thực tế quan trọng; retry không bảo đảm sẽ tiếp tục tới vô hạn.

Trong production:

- Trỏ `bootstrap-servers` tới endpoints được quản lý bằng cấu hình môi trường.
- Bật TLS/SASL và ACL phù hợp, không để secret trong source.
- Đo latency/throughput trước khi tăng `linger.ms`, `batch.size` hoặc compression.
- Xác định thời hạn gửi tối đa theo SLA và khả năng broker chịu tải.
- Đặt topic replication/ISR phù hợp yêu cầu durability.

### Vì sao không thêm `@Retryable` bao quanh `KafkaTemplate.send()` ngay?

Kafka client đã có retry ở tầng producer. Dùng `@Retryable` trên method publish có thể tạo **một lời gọi `send()` mới** sau khi lời gọi trước báo timeout. Lời gọi mới không phải bản retry cùng batch theo producer sequence; nó có thể tạo duplicate nghiệp vụ.

Nếu thực sự cần retry ở tầng application, phải thiết kế:

1. Event ID ổn định.
2. Trạng thái gửi bền vững/outbox hoặc quy tắc dedup.
3. Phân loại lỗi có outcome rõ hay không rõ.
4. Giới hạn attempt và backoff.
5. Consumer idempotency.
6. Reconciliation khi event có thể đã xuất hiện trên topic.

Không coi `enable.idempotence=true` là lý do an toàn để gọi `send()` không giới hạn.

## 8. Tạo event với business identity ổn định

Một `OrderCreated` event nên chứa ID riêng của **sự kiện**, không chỉ ID của đơn hàng:

```java
package example.kafka.orders;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        long totalCents,
        String currency,
        long aggregateVersion) {
}
```

Ví dụ:

```json
{
  "eventId": "evt-order-42-v1-created",
  "orderId": "order-42",
  "totalCents": 12500,
  "currency": "USD",
  "aggregateVersion": 1
}
```

Phân biệt:

- **`orderId`:** khóa thực thể/aggregate, dùng để routing đến Kafka partition và group events của cùng đơn.
- **`eventId`:** định danh một sự kiện logic, dùng để nhận diện sự kiện trùng trong ứng dụng.
- **`aggregateVersion`:** phiên bản trạng thái nghiệp vụ, hỗ trợ kiểm tra thứ tự và optimistic concurrency.
- **Payload fields:** dữ liệu nghiệp vụ theo contract, có schema version nếu cần evolution.

Không sinh `UUID.randomUUID()` ở **mỗi lần retry publish** một business event đã tồn tại. Event ID nên được tạo tại thời điểm ứng dụng ghi nhận sự kiện và **được giữ nguyên** qua mọi retry/restart.

Nếu producer process chết, hệ thống phải còn nơi lưu `eventId` và payload ổn định để gửi lại đúng cùng business event. Không thể đạt yêu cầu này chỉ bằng một biến Java trong memory.

## 9. Viết `OrderEventPublisher` với `KafkaTemplate`

Spring Kafka 3.x cho phép `KafkaTemplate.send(...)` trả về `CompletableFuture<SendResult<K,V>>`. Ta sẽ gửi `ProducerRecord` có key là `orderId` và header `eventId` để thuận tiện khi đối soát.

```java
package example.kafka.orders;

import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public final class OrderEventPublisher {

    private static final String TOPIC = "orders.events";

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            ObjectMapper objectMapper) {

        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper = objectMapper;
    }

    public CompletableFuture<PublishAck> publish(
            OrderCreatedEvent event) {

        Objects.requireNonNull(event, "event");

        if (event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()) {

            return CompletableFuture.failedFuture(
                    new IllegalArgumentException(
                            "Stable eventId and orderId are required"));
        }

        final String json;
        try {
            json = objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            return CompletableFuture.failedFuture(ex);
        }

        var record = new ProducerRecord<String, String>(
                TOPIC,
                event.orderId(),
                json);

        record.headers().add(
                "eventId",
                event.eventId().getBytes(StandardCharsets.UTF_8));

        return kafkaTemplate.send(record)
                .thenApply(result -> {
                    var metadata = result.getRecordMetadata();

                    return new PublishAck(
                            event.eventId(),
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset());
                });
    }

    public record PublishAck(
            String eventId,
            String topic,
            int partition,
            long offset) {
    }
}
```

### Giải thích thiết kế

- `OrderCreatedEvent` đã có `eventId` từ tầng nghiệp vụ; publisher không tự sinh ID mới.
- `orderId` là Kafka key để giữ sự kiện của cùng aggregate trong partition theo policy routing.
- `eventId` nằm trong payload và header; header giúp log/consumer truy cập nhanh nhưng không phải cơ chế dedup broker.
- `ObjectMapper` tạo JSON một lần cho lời gọi gửi.
- `KafkaTemplate.send(...)` sử dụng Kafka producer bên dưới; retry của Kafka client diễn ra theo cấu hình producer.
- `CompletableFuture` cho phép quan sát thành công/lỗi **bất đồng bộ**, không block thread gọi chỉ để chờ ACK.
- `PublishAck` chứa topic/partition/offset của record đã được broker acknowledge theo producer policy.

Trong project thực tế, tên topic nên cấu hình qua properties được quản lý, không hardcode trong publisher. Ví dụ dùng hằng `TOPIC` để bài thực hành tập trung vào idempotence.

**Cảnh báo:** Việc có `PublishAck` **không có nghĩa consumer đã xử lý event**. Nó chỉ là kết quả gửi đến Kafka theo điều kiện acknowledgment của producer.

## 10. Cách gọi publisher và xử lý kết quả

Ví dụ:

```java
OrderCreatedEvent event = new OrderCreatedEvent(
        "evt-order-42-v1-created",
        "order-42",
        12500,
        "USD",
        1L);

publisher.publish(event)
        .whenComplete((ack, error) -> {
            if (error != null) {
                // Ghi nhận trạng thái gửi chưa được xác nhận.
                // Không tự động tạo eventId mới rồi gửi lại.
                log.error(
                        "kafka.publish.failed eventId={} orderId={}",
                        event.eventId(),
                        event.orderId(),
                        error);
                return;
            }

            log.info(
                    "kafka.publish.acked eventId={} "
                        + "topic={} partition={} offset={}",
                    ack.eventId(),
                    ack.topic(),
                    ack.partition(),
                    ack.offset());
        });
```

Đoạn mã minh họa callback và giả định có biến `publisher`, `log` trong service gọi. Với `CompletableFuture`, completion có thể chạy trên thread khác thread HTTP hoặc thread gọi. Không nên thực hiện công việc block dài trong completion callback; cần chuyển sang một executor phù hợp nếu có xử lý hậu kỳ nặng.

### Callback thành công và thất bại

| Kết quả | Ý nghĩa | Việc tiếp theo |
| --- | --- | --- |
| Send future completed successfully | Kafka broker đã ACK theo cấu hình producer. | Ghi nhận offset/metadata, cập nhật trạng thái gửi nếu có outbox. |
| Send future completed exceptionally | Kafka client không hoàn tất gửi thành công theo hợp đồng API. | Phân loại lỗi; trạng thái remote có thể chưa rõ; cân nhắc reconciliation. |
| Process chết khi future chưa complete | Ứng dụng có thể mất kết quả cục bộ. | Khôi phục từ durable event/outbox; không phụ thuộc memory. |
| Callback bị lỗi khi cập nhật database | Kafka ACK có thể đã thành công nhưng DB chưa biết. | Outbox/idempotent consumer xử lý lần phát lại có thể xảy ra. |

Nếu HTTP endpoint gọi `publish()` và trả 200 ngay trước khi future thành công, phản hồi HTTP chỉ chứng minh **đã nộp yêu cầu nội bộ**. Cần định nghĩa rõ contract: API “accepted for publication” hay “Kafka acknowledged”. Nếu chỉ muốn publish có độ bền cao qua restart, dùng outbox thay vì coi CompletableFuture trong memory là một hàng đợi bền vững.

## 11. Kafka ack và độ bền của thông điệp

Có nhiều mốc khác nhau:

```text
Application
  |
  | publish(event)
  v
KafkaTemplate
  |
  | enqueue record
  v
KafkaProducer
  |
  | serialize / batch / retry
  v
Kafka broker leader + ISR
  |
  | acks=all satisfied
  v
Send future completed successfully
  |
  +-- Consumer later reads event
          |
          +-- Business processing succeeds
                  |
                  +-- offset committed
```

Đừng gộp các mốc trên thành một tín hiệu “đã xử lý chính xác một lần”.

### Nếu broker báo ACK nhưng consumer chưa thấy record?

Có thể consumer chưa poll kịp, partition đang lag, consumer group chưa được assign, deserializer lỗi, hoặc consumer đang dùng `read_committed` và record thuộc transaction chưa commit (nếu producer transactional). Với publisher **không transactional** trong bài cơ sở, ACK là điều kiện send, không bao gồm tiến độ consumer.

### Nếu future báo timeout?

Không khẳng định broker chắc chắn không có record. Ví dụ broker đã append nhưng response mất, hoặc client hết delivery deadline trước khi nhận xác nhận cuối. Chuyển event sang trạng thái cần điều tra/phát lại có kiểm soát, không tạo một event mới với identity mới.

## 12. Test bằng `@EmbeddedKafka`: đường gửi thành công

Integration test cần một Kafka broker test thực sự thay vì chỉ mock `KafkaTemplate`. Với `spring-kafka-test`, có thể dùng `@EmbeddedKafka`.

```java
package example.kafka.orders;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "spring.kafka.producer.key-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.consumer.key-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.value-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.producer.acks=all",
    "spring.kafka.producer.properties[enable.idempotence]=true",
    "spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5"
})
@EmbeddedKafka(
    partitions = 3,
    topics = "orders.events",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class IdempotentProducerIT {

    @Autowired
    private OrderEventPublisher publisher;

    @Autowired
    private EmbeddedKafkaBroker broker;

    @Test
    void publishesEventWithStableKeyAndId() throws Exception {
        String eventId = "evt-" + UUID.randomUUID();

        var event = new OrderCreatedEvent(
                eventId, "order-42", 12500, "USD", 1L);

        var properties = KafkaTestUtils.consumerProps(
                "publisher-it-" + UUID.randomUUID(),
                "false",
                broker);

        properties.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");

        try (Consumer<String, String> consumer =
                new DefaultKafkaConsumerFactory<String, String>(
                        properties,
                        new StringDeserializer(),
                        new StringDeserializer())
                        .createConsumer()) {

            broker.consumeFromAnEmbeddedTopic(
                    consumer, "orders.events");

            OrderEventPublisher.PublishAck ack =
                    publisher.publish(event)
                            .get(10, TimeUnit.SECONDS);

            var received = KafkaTestUtils.getSingleRecord(
                    consumer,
                    "orders.events",
                    Duration.ofSeconds(10));

            assertThat(ack.eventId()).isEqualTo(eventId);
            assertThat(ack.topic()).isEqualTo("orders.events");
            assertThat(received.key()).isEqualTo("order-42");
            assertThat(received.value()).contains(eventId);
            assertThat(received.partition())
                    .isEqualTo(ack.partition());
            assertThat(received.offset())
                    .isEqualTo(ack.offset());
        }
    }
}
```

### Các giả định của test

- `OrderEventPublisher` và `OrderCreatedEvent` được đăng ký/compile trong Spring Boot context.
- Có `ObjectMapper` bean và `KafkaTemplate<String,String>` từ Spring Boot auto-configuration hoặc cấu hình tương đương.
- `spring-kafka-test` tương thích với phiên bản runtime.
- Test không dùng chung topic/group với test khác đang chạy song song hoặc dữ liệu cũ; trong suite lớn, nên cô lập broker/context/topic theo nhu cầu.
- Embedded Kafka dùng một broker, nên không chứng minh cluster chịu lỗi khi leader đổi hoặc ISR thu hẹp.
- Test nhận một message và kiểm tra metadata; nó chỉ chứng minh **send/receive cơ bản**, chưa chứng minh retry dedup khi ACK bị mất.

Đừng đặt tên test `exactlyOnceUnderAllFailures` nếu chỉ gửi một record thành công. Bài test này là nền tảng trước khi thử fault injection.

## 13. Test cấu hình producer đang có hiệu lực

Một điểm dễ bỏ qua là ứng dụng khai báo `enable.idempotence=true` nhưng bean producer thực tế dùng một `ProducerFactory` tự tạo với properties khác.

Cần kiểm tra **effective producer configuration** của factory dùng bởi `KafkaTemplate` đang được test, không chỉ đọc file YAML.

Ví dụ với `DefaultKafkaProducerFactory` trong Spring Kafka 3.x:

```java
import org.apache.kafka.clients.producer.ProducerConfig;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;

import static org.assertj.core.api.Assertions.assertThat;

void verifyProducerSettings(
        DefaultKafkaProducerFactory<String, String> producerFactory) {

    var configs = producerFactory.getConfigurationProperties();

    assertThat(configs.get(
            ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG))
            .isEqualTo(true);

    assertThat(configs.get(
            ProducerConfig.ACKS_CONFIG))
            .isEqualTo("all");
}
```

Đây là đoạn kiểm tra cấu hình mang tính minh họa. Cần lấy đúng producer factory của ứng dụng và lưu ý giá trị property có thể là `String` hoặc kiểu đã chuyển đổi tùy nguồn cấu hình. Với một property Kafka client tự gán mặc định, nó có thể không xuất hiện trong map đầu vào dù giá trị effective ở runtime đã được áp dụng.

Để kiểm tra sâu hơn, có thể xem startup logs/metrics hoặc tạo producer thật và xác nhận không có configuration conflicts. Không in toàn bộ config ra log production vì SASL JAAS, mật khẩu và dữ liệu bảo mật có thể nằm trong map cấu hình.

### Phân biệt build dependency và runtime Kafka client

Spring Kafka là wrapper. Nếu ứng dụng vô tình dùng `kafka-clients` phiên bản khác dòng được hỗ trợ, startup có thể báo `NoSuchMethodError`, `ConfigException` hoặc hành vi khác. Khi thay Kafka client, kiểm tra dependency graph của artifact:

```bash
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
```

Trong Maven, dùng `mvn dependency:tree` với filter tương ứng. Không override Kafka client phiên bản tùy ý chỉ để dùng một property mà chưa kiểm tra ma trận hỗ trợ.

## 14. Một test quan trọng: gọi `send()` hai lần không được dedup

Giả sử ứng dụng gửi cùng business event hai lần:

```java
OrderCreatedEvent event = new OrderCreatedEvent(
        "evt-order-42-v1-created",
        "order-42",
        12500,
        "USD",
        1L);

publisher.publish(event).get(10, TimeUnit.SECONDS);
publisher.publish(event).get(10, TimeUnit.SECONDS);
```

Kafka producer idempotent **không** tự xem hai lời gọi ứng dụng là cùng một request. Thông thường, topic có thể nhận **hai records** với cùng key/eventId (hai sequence numbers hợp lệ).

Vì sao test này quan trọng?

- Nó bác bỏ kỳ vọng sai rằng `enable.idempotence=true` tương đương một unique constraint theo `eventId`.
- Nó nhắc developer không đặt `@Retryable` quanh publisher một cách không kiểm soát.
- Nó dẫn tới thiết kế event identity/outbox/consumer dedup.
- Nó phân biệt Kafka protocol idempotence với business idempotency.

Nếu xây integration test riêng, hãy chạy trên topic test sạch, gửi hai lần, poll đủ hai records và assert cùng `eventId` có thể xuất hiện hai lần. Đừng biến việc thấy hai records thành “Kafka idempotence bị lỗi”; đó là hai **application sends** độc lập.

## 15. Kiểm thử retry khi phản hồi broker bị mất

Kiểm thử thật cơ chế idempotent retry khó hơn gửi một message thông thường. Cần tạo lỗi xảy ra ở thời điểm **request có thể đã được broker ghi nhưng client không nhận được ACK**.

Một kịch bản khái niệm:

```text
Producer A (idempotence=true)           Broker test
         |                                  |
         |---- batch E -------------------->|
         |                                  | append E
         X<--------- ACK response ---------|
         |
         |---- Kafka internal retry ------->|
         |                                  | detect duplicate sequence
         |<----------------- ACK ------------|
         |
         v
Topic contains one record for that
internal retry scenario.
```

Để thử tình huống này, có thể dùng:

- Kafka cluster trong Testcontainers.
- Proxy kiểm soát đường mạng như Toxiproxy.
- Broker/test harness có khả năng gây lỗi response ở điểm cụ thể.
- Producer metrics/log để biết request đã retry thật.

**Chặn mạng ngẫu nhiên chưa chắc tái tạo “ACK lost after append”.** Nếu request không tới broker, retry không có gì để dedup; nếu client reconnect và gửi lệnh mới từ application, semantics lại khác. Test cần chứng minh fault thực sự tác động tới đường ACK sau khi broker append, nếu muốn dùng nó làm bằng chứng mạnh về broker-side dedup.

### Các bước kiểm thử thực hành

1. Tạo topic riêng, consumer ở group test riêng.
2. Bật idempotence, `acks=all`, retry và những timeout phù hợp.
3. Thiết lập proxy cho **mọi broker endpoint mà producer kết nối**, không chỉ bootstrap address.
4. Dùng công cụ lỗi để gây mất/đứt phản hồi vào cửa sổ thử nghiệm.
5. Gửi **một lời gọi `send()`** mang event ID ổn định; để Kafka client tự retry.
6. Quan sát send future, producer retry metrics, broker logs và topic contents.
7. Nếu retry thật sự diễn ra sau lần append đầu, xác nhận số records vật lý không tăng do nội bộ retry trùng.
8. Thu lại log/metrics trước khi kết luận; nếu fault không tái tạo đúng điều kiện, ghi rõ test inconclusive.

Trong Kafka qua proxy, broker metadata có `advertised.listeners`, client có thể kết nối trực tiếp đến broker sau bước bootstrap. Nếu chỉ chặn bootstrap mà không chặn endpoint advertised, test fault injection có thể không hề ảnh hưởng traffic thực tế.

### Test với broker leader failover

Một cluster nhiều brokers cho phép thử leader failover và ISR changes. Cần xác định replication factor, min ISR, quorum health và thời điểm failover. Không suy diễn mọi lỗi leader đều dẫn tới record duplicate hoặc record mất; mục tiêu là đánh giá kết quả theo Kafka client protocol và durability policy.

## 16. Thử producer restart và “unknown outcome”

Tình huống nguy hiểm hơn:

```text
orders-service                          Kafka
     |                                    |
     |--- send event E ------------------>|
     |                                    | stores E
     X process dies before saving ACK
     |
Restart application
     |
     |--- send E again with new session ->| stores another valid record
```

Producer idempotence không tự biết rằng hai `send()` ở hai sessions là cùng business operation.

Một test có thể:

1. Lưu event E vào một nguồn bền vững.
2. Dùng producer instance A gửi E; Kafka nhận.
3. Mô phỏng process A chết trước khi ứng dụng ghi nhận publish thành công.
4. Khởi tạo producer instance B.
5. Đọc E từ nguồn bền vững và gửi lại với **cùng event ID**.
6. Kiểm tra topic có thể chứa duplicate business event.
7. Kiểm tra consumer idempotent chỉ áp dụng side effect một lần.

Điều cần ghi trong báo cáo test là **Kafka producer idempotence và consumer idempotency giải quyết hai ranh giới khác nhau**.

Không thiết kế test theo kỳ vọng sai “producer B sẽ được Kafka broker tự động dedup với producer A vì hai records có cùng JSON”.

## 17. Consumer idempotency để bảo vệ kết quả nghiệp vụ

Khi consumer xử lý `OrderCreated`, không nên coi `eventId` là một string để log rồi quên. Nếu một business event có thể xuất hiện lại, consumer nên có cơ chế dedup bền vững.

Ví dụ PostgreSQL:

```sql
CREATE TABLE processed_kafka_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(160) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
```

Một chiến lược xử lý trong **cùng transaction database**:

```text
BEGIN DB TRANSACTION

INSERT INTO processed_kafka_event(consumer_name, event_id)
  ON CONFLICT DO NOTHING;

Nếu insert tạo bản ghi mới:
  -> áp dụng business update
Nếu key đã tồn tại:
  -> bỏ qua business update

COMMIT
Sau khi DB commit thành công:
  -> acknowledge/commit Kafka offset theo policy
```

**Cả marker dedup và business update phải nằm trong cùng transaction**, nếu không có thể xuất hiện tình huống đã ghi marker nhưng business update chưa xảy ra.

Ví dụ một JDBC service:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class IdempotentOrderConsumerService {

    private final JdbcTemplate jdbc;

    public IdempotentOrderConsumerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(OrderCreatedEvent event) {

        int inserted = jdbc.update(
                """
                INSERT INTO processed_kafka_event(
                    consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """,
                "order-projection",
                event.eventId());

        if (inserted == 0) {
            return false; // Already processed by this consumer.
        }

        jdbc.update(
                """
                INSERT INTO order_projection(
                    order_id, total_cents, currency)
                VALUES (?, ?, ?)
                ON CONFLICT (order_id) DO UPDATE SET
                    total_cents = EXCLUDED.total_cents,
                    currency = EXCLUDED.currency
                """,
                event.orderId(),
                event.totalCents(),
                event.currency());

        return true;
    }
}
```

Đây là một **ví dụ có điều kiện**: cần tự tạo bảng `order_projection`, cấu hình transaction manager cho cùng datasource, parser event và listener Kafka. SQL dùng PostgreSQL. Với thay đổi theo version, cần thêm optimistic concurrency/version check để một event cũ không ghi đè trạng thái mới chỉ vì nó được redeliver muộn.

Kafka offset commit vẫn không giao dịch nguyên tử với PostgreSQL trong thiết kế trên. Nhưng khi DB đã commit và consumer crash trước khi Kafka offset được commit, record redeliver sẽ gặp marker đã tồn tại, tránh **lặp side effect DB**.

### Đừng đưa mọi consumer dùng chung một `event_id` duy nhất

Nếu nhiều consumer/service độc lập đều cần xử lý cùng event, bảng marker phải phân biệt **consumer logical name** hoặc scope nghiệp vụ. Một `eventId` đã xử lý ở service A không nên khiến service B bỏ qua sự kiện đầu tiên của mình.

### HTTP/side effect bên ngoài

Nếu consumer gọi remote payment API, database marker dedup không tự bao phủ HTTP. Dùng idempotency key của remote hoặc orchestration/outbox ở phía consumer để bảo đảm kết quả đúng qua crash/retry.

## 18. Transactional outbox: producer idempotent chưa thay thế nó

Một ứng dụng điển hình lưu đơn hàng vào database rồi publish `OrderCreated`.

Một cách không an toàn:

```text
BEGIN DB TX
  INSERT orders
COMMIT DB TX
  |
  X process crashes
  |
No Kafka event
```

Đảo ngược thứ tự cũng không an toàn:

```text
Kafka send acked
  |
  X database transaction fails
  |
Kafka has OrderCreated, database has no order
```

**Transactional outbox** giải quyết việc ghi **trạng thái nghiệp vụ và ý định publish event trong cùng DB transaction**:

```text
API / command
     |
     v
BEGIN DB TX
   INSERT/UPDATE orders
   INSERT outbox(event_id, order_id, payload, status=NEW)
COMMIT DB TX
     |
     v
Outbox dispatcher
   claim NEW rows (short DB TX)
   KafkaTemplate.send(...) outside DB TX
   wait for ACK with bounded deadline
   mark SENT (short DB TX)
```

### Schema minh họa

```sql
CREATE TABLE order_event_outbox (
    event_id      VARCHAR(160) PRIMARY KEY,
    aggregate_id  VARCHAR(160) NOT NULL,
    event_type    VARCHAR(80) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    payload_json  JSONB NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'NEW',
    attempts      INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    lease_until   TIMESTAMPTZ,
    claim_token   VARCHAR(100),
    last_error    VARCHAR(120),
    created_at    TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_order_event_business
        UNIQUE (aggregate_id, event_type, aggregate_version)
);
```

Outbox là bảng ứng dụng, **không phải thành phần broker Kafka tự tạo**.

Điểm thiết kế:

- `event_id` ổn định qua retry/restart.
- Unique business constraint chống tạo hai event cho cùng nghĩa vụ logic, nếu đó là rule nghiệp vụ.
- `claim_token` và lease giúp xử lý multi-worker, tránh worker cũ cập nhật nhầm sau khi lease hết.
- `next_attempt_at` cho backoff.
- `payload_json` giữ đúng phiên bản event đã tạo; không sinh lại payload theo trạng thái database thay đổi mà không có chủ đích.
- `status` biểu diễn trạng thái publish, không phải trạng thái xử lý tại mọi consumer.

### Crash sau Kafka ACK nhưng trước DB ack

```text
Dispatcher A
  |
  +-- KafkaTemplate.send(event E) ACKED
  |
  X crashes before outbox.status=SENT
  |
Dispatcher B claims E
  |
  +-- KafkaTemplate.send(event E) again
```

Outbox có thể đảm bảo event không bị quên sau khi commit DB, nhưng do cửa sổ crash này, hệ thống vẫn có thể publish **hơn một lần**. Với producer instance B khác, idempotent producer không tự hợp nhất lần gửi mới. Cần consumer idempotency bằng `eventId` hoặc cơ chế transaction/streaming phù hợp với phạm vi giải quyết.

**Kết luận:** Idempotent producer + transactional outbox + idempotent consumer là các thành phần **bổ sung**, không phải ba tên gọi cho cùng một tính năng.

## 19. Phân biệt idempotent producer và Kafka transactions

Idempotence là nền tảng quan trọng, nhưng Kafka còn có **transactional producer** để commit hoặc abort một nhóm records như một đơn vị trong phạm vi Kafka.

| Cơ chế | Giải quyết | Không tự giải quyết |
| --- | --- | --- |
| `enable.idempotence=true` | Kafka client retry batch không làm ghi trùng trong producer session theo protocol. | Hai lần application `send()` độc lập, DB/HTTP transaction, duplicate từ consumer. |
| Kafka transactions | Atomic commit/abort nhiều Kafka records và offset trong những workflow được hỗ trợ. | Atomic transaction với mọi database/remote API bên ngoài. |
| `read_committed` consumer | Không cung cấp dữ liệu từ Kafka transactions đã abort theo isolation semantics. | Dedup business event từ hai application sends đều committed. |
| Transactional outbox | Ghi ý định publish cùng thay đổi DB trong local transaction. | Kafka publish exactly-once sau crash nếu không có phối hợp/consumer dedup. |
| Consumer idempotency | Chống lặp side effect theo business event ID. | Broker-side duplicate removal cho internal producer retries. |

### Khi nào cần Kafka transactions?

Ví dụ một Kafka Streams hoặc consume-process-produce workflow cần:

```text
Consume Kafka input
    |
    +-- Process
    |
    +-- Produce Kafka output
    |
    +-- Commit consumed offsets
             |
             v
      Same Kafka transaction
```

Nếu dùng Spring Kafka transactional producer, cấu hình producer transaction ID prefix và transaction manager/operations theo tài liệu dòng version thực tế. Mỗi instance đang hoạt động cần identity phù hợp để tránh producer fencing ngoài ý muốn.

Ví dụ khái niệm:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.validated", "order-42", "validated");
    operations.send("orders.audit", "order-42", "recorded");
    return null;
});
```

Đoạn code này là ví dụ phạm vi Kafka transaction; cần producer factory có transaction support, topic tồn tại và cấu hình broker phù hợp. Nếu yêu cầu xử lý cả **consumer offsets**, không chỉ gọi hai `send()` trong transaction rồi nghĩ offsets tự động tham gia.

**Transaction Kafka không rollback PostgreSQL hay HTTP side effects.** Nếu sự kiện cần gắn với database, outbox hoặc một cơ chế đồng bộ trạng thái khác vẫn là một lựa chọn quan trọng.

## 20. Ordering, partition key và các producer cùng ghi

Kafka đảm bảo thứ tự log **theo partition**, không có thứ tự toàn cục cho cả topic nhiều partitions. Trong một producer idempotent, sequence handling hỗ trợ những bảo đảm liên quan đến retry và ordering cho requests tới cùng partition.

Tuy nhiên, hãy phân biệt:

- **Một producer gửi nhiều records:** Kafka producer quản lý sequence; config `max.in.flight`/idempotence ảnh hưởng thứ tự khi retry.
- **Nhiều producer cùng gửi cho một key:** thứ tự logic giữa các producer không tự được Kafka sắp xếp theo business version.
- **Đổi số partitions:** cùng key có thể được route sang partition khác so với lịch sử tùy partitioner.
- **Producer restart:** idempotence không bảo vệ thứ tự nghiệp vụ xuyên mọi sessions khi có outbox workers cạnh tranh.

Ví dụ:

```text
Order #42
  version 1: CREATED
  version 2: PAID
  version 3: SHIPPED
```

Nếu publisher A gửi `v3` trước publisher B gửi `v2`, broker không thể suy đoán rằng `v2` “phải xảy ra trước”. Để bảo toàn thứ tự nghiệp vụ, có thể:

1. Giữ key `orderId` nhất quán.
2. Lấy sự kiện từ một outbox có `aggregateVersion`.
3. Không publish version kế tiếp trước version trước nếu contract yêu cầu thứ tự.
4. Sử dụng per-aggregate sequencing/locking ở dispatcher khi cần.
5. Cho consumer kiểm tra version hoặc bỏ qua event cũ khi an toàn.

Không đặt `max.in.flight=1` rồi cho rằng nó giải quyết thứ tự giữa các producer processes độc lập.

## 21. Retry policy trong producer: lỗi có thể phục hồi và lỗi dứt điểm

Kafka client tự phân loại một số lỗi có thể retry. Ứng dụng vẫn cần hiểu kết quả gửi đã báo thành công hay thất bại.

| Loại tình huống | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Network glitch tạm thời | Kết nối bị reset, leader đang chuyển | Kafka client retry theo cấu hình, giữ producer session khi còn hợp lệ. |
| Broker tạm không đủ ISR | `NotEnoughReplicasException` hoặc lỗi liên quan | Giữ `acks=all`, theo dõi cluster, không hạ durability vô tội vạ. |
| Delivery deadline hết | `TimeoutException` | Outcome có thể chưa rõ; phân loại và reconciliation. |
| Serialization thất bại | Payload không thể serialize | Sửa dữ liệu/code; không retry network vô hạn. |
| Authorization thất bại | Topic ACL không đủ | Điều tra ACL/credential, không coi là transient network. |
| Producer state lỗi nghiêm trọng | `OutOfOrderSequenceException` hoặc fatal producer error | Theo hợp đồng client, có thể cần tạo producer mới; cân nhắc unknown outcomes. |
| Transactional producer bị fence | `ProducerFencedException` | Xử lý lifecycle/identity, không tiếp tục dùng producer bị fence. |

Các exception có thể xuất hiện ở nhiều mức và khác nhau giữa Kafka client versions. Cần quan sát **root cause**, record topic/key, attempt/failure telemetry và trạng thái broker.

### Không tự động gửi lại mọi lần future failed

Ví dụ anti-pattern:

```java
publisher.publish(event).exceptionally(error -> {
    publisher.publish(event); // Mở một send mới, outcome cũ chưa rõ.
    return null;
});
```

Đoạn code này có thể tạo duplicate và che lỗi. Khi xảy ra thất bại, áp dụng một quy trình:

1. Xác định event ID ổn định và source/outbox record.
2. Phân loại lỗi có thể retry, lỗi cấu hình hay outcome unknown.
3. Giữ retry budget và backoff.
4. Nếu retry ứng dụng, dùng **cùng event ID**, không thay đổi payload một cách ngẫu nhiên.
5. Chuẩn bị dedup ở consumer.
6. Ghi nhận kết quả cuối và số attempts.

Không có cơ chế dedup/reconciliation thì việc “cứ gửi lại đến khi thành công” chưa phải chiến lược tin cậy.

## 22. Backpressure và tài nguyên producer

Một producer idempotent vẫn có giới hạn tài nguyên. Nếu application tạo record nhanh hơn broker xác nhận, hàng đợi/buffer phía client có thể đầy.

Các cấu hình có liên quan:

| Cấu hình | Tác động |
| --- | --- |
| `buffer.memory` | Bộ nhớ Kafka producer dùng để buffer records trước khi gửi. |
| `batch.size` | Batch size hướng tới batching/throughput. |
| `linger.ms` | Chờ gom batch thêm trước khi gửi trong những điều kiện nhất định. |
| `max.block.ms` | Thời gian các thao tác producer có thể chờ metadata/buffer trước khi lỗi. |
| `compression.type` | Giảm network bytes nhưng tốn CPU. |
| `max.request.size` | Giới hạn kích thước request producer. |
| `delivery.timeout.ms` | Giới hạn deadline gửi record. |
| `acks`/`min.insync.replicas` | Đánh đổi về khả năng xác nhận và durability. |

Không tăng `buffer.memory` vô hạn để che backlog. Nếu broker hoặc network chậm kéo dài, buffer lớn chỉ trì hoãn điểm nghẽn và tăng RAM. Cần có backpressure ở application, bounded in-flight sends và chính sách overload.

Ví dụ service không nên tạo một triệu `CompletableFuture` rồi giữ tất cả trong list memory để chờ:

```java
for (OrderCreatedEvent event : events) {
    futures.add(publisher.publish(event)); // Có thể tăng rất lớn.
}
```

Hướng tốt hơn là giới hạn concurrency, dùng một worker pool có queue bounded hoặc dispatcher outbox với số in-flight sends được kiểm soát. Chỉ ACK/xóa công việc nguồn sau khi có cơ chế đảm bảo trạng thái phù hợp.

### Chỉ số throughput không thay thế correctness

Một cấu hình `acks=1` có thể nhanh hơn `acks=all` trong một số workload, nhưng nếu hệ thống cần durability cao, không nên chọn chỉ dựa trên rows/second. Đo cả producer error rate, retries, latency P95/P99, broker ISR health và số sự kiện nghiệp vụ bị mất/trùng.

## 23. Quan sát producer idempotent trong production

Các Kafka producer metrics thường có nhóm record send/retry/error, request latency, buffer pressure và batch behavior. Tên metric chính xác phụ thuộc Kafka client/JMX/Micrometer bridge và phiên bản.

Ví dụ những tín hiệu cần thu thập:

| Nhóm | Tín hiệu | Điều cần quan sát |
| --- | --- | --- |
| Send | Record send rate, send total | Producer throughput có khớp input không. |
| Retry | Record retry rate/total | Broker/network có đang buộc client retry nhiều không. |
| Error | Record error rate/total | Có failure tăng sau deploy không. |
| Latency | Request latency, record queue time | Broker chậm hay producer buffer bị nghẽn. |
| Buffer | Buffer available bytes, bufferpool wait time | Ứng dụng có tạo nhanh hơn khả năng gửi không. |
| Batching | Batch size average, compression rate | Throughput và bandwidth trade-off. |
| Broker | Under-replicated partitions, ISR shrink | Khả năng đáp ứng `acks=all` và durability. |
| Business | Outbox backlog, oldest pending event age | Có sự kiện chưa được publish thành công không. |
| Consumer | Duplicate event ID handled, lag, DLT | Đầu ra có bị xử lý lại hoặc lỗi deserialize không. |

Không tự động xem `retry-rate > 0` là lỗi dữ liệu: retry có thể là hành vi bình thường khi gặp lỗi transient. Điều đáng lo là retry/error tăng kéo dài, latency vượt SLA, backlog không giảm hoặc business outcome sai.

### Logging có cấu trúc

Ví dụ:

```text
INFO kafka.publish.requested
  topic=orders.events
  eventId=evt-order-42-v1-created
  aggregateId=order-42

INFO kafka.publish.acked
  topic=orders.events
  eventId=evt-order-42-v1-created
  partition=2
  offset=71054
  durationMs=35

WARN kafka.publish.unknown
  topic=orders.events
  eventId=evt-order-42-v1-created
  errorType=TimeoutException
  nextAction=RECONCILE
```

Các giá trị chỉ là log minh họa, không phải kết quả chạy thật. Không log token, secret, dữ liệu tài chính nhạy cảm hoặc toàn bộ payload chưa được phép công bố.

Đối với metrics, **không gắn `eventId`, `orderId` hay offset làm metric tags** vì cardinality lớn. Những ID này nên ở log/tracing chi tiết; metrics dùng `topic`, `service`, `result` và những nhãn có số giá trị hữu hạn.

## 24. Checklist kiểm thử độ tin cậy

Một bộ kiểm thử cho producer idempotent cần đi từ cấu hình đến những thất bại có khả năng xảy ra:

| Kiểm thử | Setup | Điều cần chứng minh |
| --- | --- | --- |
| Cấu hình hợp lệ | Idempotence, acks, retries, max in-flight | Producer tạo được và gửi thành công. |
| Cấu hình xung đột | `enable.idempotence=true` + `acks=1` | Client từ chối tổ hợp không hợp lệ theo config contract. |
| Gửi bình thường | Embedded Kafka | Một application send được ACK và consumer đọc. |
| Hai application sends giống nhau | Cùng `eventId`, gọi `send()` hai lần | Business duplicate **vẫn có thể xuất hiện**; không hiểu sai idempotence. |
| Internal retry | ACK loss/leader fault được xác nhận | Kafka client retry không tạo bản sao của cùng batch trong cùng session. |
| Producer restart | Event được phát lại bởi instance mới | Có thể duplicate; consumer idempotency phải bảo vệ side effect. |
| Broker chưa đủ ISR | Cluster nhiều broker, giảm ISR | `acks=all` có thể thất bại; không hạ durability vô điều kiện. |
| Broker phục hồi | Tạm mất network/leader | Producer tiếp tục gửi hợp lệ khi fault hết; không retry storm. |
| Outbox crash window | Broker ACK trước khi DB mark sent | Event ID ổn định, replay không nhân đôi business effect. |
| Consumer restart | Offset chưa commit | Redelivery không gây business update trùng. |
| Serialization lỗi | Payload sai schema | Ghi lỗi rõ ràng, không retry network vô hạn. |
| Load test | Bounded queue/in-flight | Không OOM, throughput/latency đạt SLA. |

Đừng đánh dấu “passed Kafka dedup under retry” nếu test không hề tạo được một internal retry cùng batch **sau khi broker đã ghi**. Test naming và report phải phản ánh điều kiện đã thực sự xảy ra.

## 25. Thực hành lỗi cấu hình có chủ đích

Một cách hiểu rõ ràng về ràng buộc là thử tạo producer với các cấu hình không hợp lệ **trong môi trường test**, ví dụ:

```properties
enable.idempotence=true
acks=1
retries=10
max.in.flight.requests.per.connection=5
```

Hoặc:

```properties
enable.idempotence=true
acks=all
retries=0
max.in.flight.requests.per.connection=5
```

Với Kafka client có ràng buộc idempotence tương ứng, các tổ hợp này phải bị từ chối thay vì producer âm thầm chạy với semantics trái với yêu cầu. Không nên cố cấu hình sai trong production để “kiểm tra” bằng cách đẩy dữ liệu thật.

### Vì sao test negative config có giá trị?

- Chứng minh cấu hình được áp dụng cho **đúng producer factory**.
- Phát hiện một thư viện hoặc environment override làm thay đổi `acks` hay `retries`.
- Tránh hệ thống đi vào hoạt động mà developer tưởng đã bật idempotence nhưng thực tế không đáp ứng điều kiện.
- Làm rõ ràng buộc khi nhóm khác tối ưu throughput.

Cần lưu ý API và exception lúc validate config có thể khác giữa phiên bản Kafka client; test không nên phụ thuộc nguyên văn toàn bộ error message.

## 26. Bảo mật và vận hành triển khai

Idempotence không thay thế Kafka authentication, authorization hoặc transport security.

Trong production:

- Kết nối broker qua `SASL_SSL`/TLS và truststore/identity đúng chính sách.
- Cấp ACL tối thiểu để producer ghi đúng topic cần thiết.
- Quản lý credentials qua secret manager, không đặt password trong `application.yml` commit lên repository.
- Kiểm soát topic auto-creation; ứng dụng không nên tự tạo topic production không có replication/retention phù hợp.
- Đảm bảo event schema/size và headers không chứa dữ liệu nhạy cảm không cần thiết.
- Bảo vệ idempotency/business IDs trước thao tác tự ý giả mạo sự kiện.
- Ghi audit về producer deployment, topic, version và thay đổi cấu hình tin cậy.
- Quan sát ISR/leader failures cùng retry backlog để biết sự cố nằm ở Kafka hay ứng dụng.

### Rolling deployment

Khi deploy nhiều replicas:

```text
orders-service v1 (producer A)
orders-service v2 (producer B)
         |
         v
      Kafka topic
```

Mỗi producer instance có thể hoạt động idempotent riêng, nhưng **hai replicas vẫn có thể gửi cùng business event** nếu hai luồng xử lý cùng nhận một lệnh hoặc cùng quét một hàng outbox mà không claim nguyên tử.

Cần:

1. Claim outbox jobs nguyên tử và dùng lease/fencing phù hợp.
2. Event ID cố định, không tạo mới theo pod.
3. Chỉ có một rule nghiệp vụ xác định sự kiện nào cần publish.
4. Consumer dedup nếu một event có thể được phát lại.
5. Giới hạn in-flight work khi shutdown để không mất trạng thái.
6. Kiểm tra crash window trước khi xem rollout hoàn tất.

**Không dựa vào producer ID Kafka làm khóa định danh sự kiện nghiệp vụ.** PID thuộc Kafka client protocol/session, không phải ID thay thế cho `eventId`.

## 27. Sự khác nhau giữa producer idempotence và HTTP idempotency key

Một service HTTP có thể nhận:

```http
POST /orders
Idempotency-Key: req-123
Content-Type: application/json

{"orderId":"order-42","totalCents":12500}
```

Đó là cơ chế ở **HTTP API**: server phải lưu `Idempotency-Key`/request fingerprint để trả kết quả phù hợp khi client retry. Kafka producer idempotence là cơ chế khác ở tầng **Kafka protocol**.

Luồng tin cậy từ đầu tới cuối có thể là:

```text
HTTP client (request idempotency key)
    |
    v
orders-service
  validate command
  DB TX: insert order + outbox eventId
    |
    v
Outbox dispatcher
  Kafka producer idempotent
    |
    v
Kafka topic
    |
    v
Consumer dedup by eventId
  DB TX: marker + business update
```

Mỗi lớp có một “khóa” và một phạm vi cần được thiết kế rõ. Nếu client gửi lại HTTP command sau timeout, request ID giúp tránh tạo hai đơn; nếu Kafka internal retry, producer idempotence tránh một batch bị append trùng; nếu service restart, outbox/consumer ID giúp xử lý trường hợp event bị phát lại.

Đừng gộp ba cơ chế thành một cờ `exactlyOnce=true` tưởng tượng.

## 28. Kịch bản sự cố và hướng xử lý

### Kịch bản A: broker đổi leader trong lúc publish

Producer có thể gặp lỗi tạm thời rồi retry theo metadata mới. Quan sát request retry, send latency, leader/ISR changes. Nếu send future cuối cùng thành công, ghi nhận metadata ACK. Nếu timeout, giữ trạng thái unknown để reconciliation.

### Kịch bản B: ISR giảm dưới ngưỡng

Với `acks=all` và `min.insync.replicas` phù hợp, broker có thể từ chối ghi. Không chuyển `acks=1` chỉ để giảm lỗi mà chưa có quyết định về durability. Cần điều tra broker replication/ISR health.

### Kịch bản C: producer process chết sau ACK

Outbox chưa được mark `SENT`. Dispatcher mới có thể gửi lại cùng business event. Kafka idempotence của producer mới không ngăn duplicate ứng dụng. Consumer phải dedup bằng event ID hoặc hệ thống cần reconciliation.

### Kịch bản D: lỗi serialization

Publisher không thể tạo JSON hợp lệ hoặc serializer ném exception. Đây không phải network transient. Cần kiểm tra dữ liệu và schema, đừng retry Kafka vô hạn.

### Kịch bản E: producer buffer đầy

Gửi quá nhanh so với broker, `max.block.ms` và buffer pressure dẫn tới timeout hoặc backpressure. Giới hạn concurrency/queue và đo broker throughput, thay vì giữ vô hạn in-memory futures.

### Kịch bản F: cùng key nhưng business order sai

Hai producer publish `OrderPaid v2` và `OrderCreated v1` không theo thứ tự. Idempotent producer không điều phối thứ tự giữa chúng. Dùng aggregate version, outbox ordering và consumer version checks.

## 29. Bài tập thực hành

Giả sử hệ thống có `payment-service` phát sự kiện `PaymentCaptured` lên topic `payments.captured`. Mỗi payment có `paymentId` và `captureVersion`. Hệ thống cần chịu lỗi broker tạm thời, không mất sự kiện đã commit vào database và không cộng doanh thu hai lần do redelivery.

### Bài 1: Producer idempotent

1. Tạo `KafkaTemplate<String,String>` với `StringSerializer`.
2. Cấu hình `enable.idempotence=true`, `acks=all`, `retries>0` và `max.in.flight.requests.per.connection<=5`.
3. Tạo record có `eventId` ổn định, `paymentId` làm key.
4. Publish bất đồng bộ và ghi nhận ACK metadata.
5. Đảm bảo timeout/failure không được hiểu nhầm là “record chắc chắn chưa được gửi”.

### Bài 2: Chứng minh giới hạn

1. Gửi một event bình thường, đọc bằng consumer test.
2. Gửi lại **bằng lời gọi `send()` thứ hai** cùng payload/eventId.
3. Quan sát hai records có thể cùng tồn tại trên topic.
4. Giải thích tại sao đây **không phải lỗi của idempotent producer**.
5. Cài consumer dedup theo `eventId` và xác nhận business update chỉ chạy một lần.

### Bài 3: Đưa outbox vào kiến trúc

1. Trong transaction database, ghi payment state và `PaymentCaptured` outbox event.
2. Thêm unique constraint trên `(paymentId, captureVersion, eventType)`.
3. Dispatcher claim command, publish qua idempotent Kafka producer.
4. Sau ACK, mark `SENT` bằng transaction database ngắn.
5. Kill dispatcher sau khi broker ACK nhưng trước khi DB ack.
6. Restart dispatcher, xác minh event ID giữ nguyên và consumer không áp dụng side effect hai lần.

### Bài 4: Kiểm tra broker durability

1. Tạo Kafka test cluster nhiều broker.
2. Topic có replication factor và min ISR phù hợp.
3. Cố ý làm mất một broker hoặc leader theo quy trình test.
4. Quan sát retry, future completion, ISR, offset và dữ liệu nhận ở consumer.
5. Không giảm `acks` để làm bài test pass nếu chính sách hệ thống cần durability cao.

### Bài 5: Metrics và triển khai

1. Thu producer send/retry/error rate và P95 latency.
2. Thu outbox pending count và oldest event age.
3. Thu duplicate event IDs tại consumer.
4. Đặt cảnh báo khi retry liên tục, backlog tăng hoặc topic không đủ ISR.
5. Thử rolling deployment hai producer instances dùng chung outbox; kiểm tra claim/fencing/dedup.
6. Ghi lại version Kafka client/Spring Kafka và config đã dùng.

### Câu hỏi tự đánh giá

- `enable.idempotence=true` bảo vệ loại duplicate nào?
- Vì sao `acks=all` và `min.insync.replicas` giải quyết vấn đề khác nhau so với idempotence?
- Khi nào hai lời gọi `KafkaTemplate.send()` tạo hai records mặc dù key/payload giống nhau?
- Vì sao `max.in.flight.requests.per.connection=1` không bắt buộc khi producer idempotent được cấu hình đúng?
- Một future timeout có chứng minh broker chưa ghi record không?
- Vì sao producer mới sau restart không tự dedup event đã gửi bởi producer cũ?
- Transactional outbox ngăn “DB commit nhưng quên publish” như thế nào?
- Cửa sổ crash nào khiến outbox vẫn có thể publish trùng?
- Consumer dedup marker cần giao dịch cùng business update hay không? Vì sao?
- Kafka transactions có rollback database/HTTP side effect bên ngoài không?
- Khi leader failover, vì sao chỉ đếm số HTTP/client retries không đủ kết luận Kafka đã dedup đúng?
- Khi nhiều replicas cùng gửi cho một aggregate, làm sao giữ thứ tự phiên bản nghiệp vụ?

## 30. Tổng kết

Một producer có thể được gọi là **idempotent theo Kafka** khi Kafka Java client và broker sử dụng cơ chế producer identity/sequence để xử lý đúng những bản retry cùng batch trong phạm vi được hỗ trợ. Trong Spring Kafka, đó chủ yếu là **cấu hình producer**: bật `enable.idempotence` và giữ tương thích giữa `acks`, `retries`, `max.in.flight.requests.per.connection`.

Nhưng độ tin cậy nghiệp vụ cần thêm các lớp bảo vệ:

- **Event ID ổn định** để nhận diện cùng một sự kiện qua process restart.
- **Outbox hoặc transaction design** để không mất ý định publish khi database commit.
- **Consumer idempotency** để không lặp business side effect sau redelivery hoặc application resend.
- **Kafka transactions** khi cần atomicity trong đúng phạm vi Kafka được hỗ trợ.
- **Test có lỗi thực** và metrics để phân biệt client retry, broker ACK, unknown outcome và business completion.

Mục tiêu của bài thực hành không phải “bật một flag rồi coi mọi duplicate đã biến mất”, mà là hiểu chính xác **phạm vi bảo đảm của flag đó** và xây dựng hệ thống gửi sự kiện có thể phục hồi đúng khi lỗi xảy ra.

## Tài liệu tham khảo

- [Apache Kafka – Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs): `enable.idempotence`, `acks`, `retries`, `max.in.flight.requests.per.connection` và các timeout.
- [Apache Kafka – KafkaProducer API](https://kafka.apache.org/documentation/#producerapi): cơ chế gửi bất đồng bộ và các hành vi producer.
- [Apache Kafka – Design: Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-most-once, at-least-once và exactly-once trong phạm vi Kafka.
- [Spring for Apache Kafka – Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate`, send results và producer configuration.
- [Spring for Apache Kafka – Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): transactional producer và xử lý offsets trong Kafka transactions.
- [Spring for Apache Kafka – Testing](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka` và test utilities.
- [Spring Boot – Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): cấu hình Kafka producer/consumer trong Spring Boot.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): phát sự kiện bền vững sau khi ghi dữ liệu nghiệp vụ.
- [Testcontainers – Kafka Module](https://java.testcontainers.org/modules/kafka/): kiểm thử Kafka thực trong container và fault injection có kiểm soát.

