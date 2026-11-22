# Xác nhận đã gửi, broker đã nhận và consumer đã xử lý

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức tích hợp qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter của Spring Integration. Một luồng đặt hàng có thể cập nhật PostgreSQL, phát sự kiện sang Kafka/RabbitMQ và để consumer khác đồng bộ báo cáo hoặc gửi thông báo. Trong luồng ấy, ba câu hỏi rất dễ bị đánh đồng:

- **Producer đã gửi?** Lời gọi API gửi đã khởi tạo, được đưa vào buffer hay đã nhận kết quả cuối của producer?
- **Broker đã nhận?** Broker đã xác nhận theo mức bảo đảm nào, record đã tới topic/queue đích và có còn bền vững sau sự cố không?
- **Consumer đã xử lý?** Consumer mới nhận message, hay đã commit business transaction rồi ghi nhận ACK/offset?

Một lời gọi `send()` không có exception **không chứng minh** người tiêu thụ đã hoàn tất nghiệp vụ. Ngay cả broker confirm ACK cũng không cho biết báo cáo đã được cập nhật. Ngược lại, consumer có thể đã commit database nhưng mất kết nối trước ACK và buộc phải nhận lại cùng sự kiện.

Bài thuộc chương **Nền tảng nhắn tin**, tập trung vào **Xác nhận đã gửi, broker đã nhận và consumer đã xử lý**. Nội dung kết hợp Kafka, RabbitMQ/AMQP và JMS với hợp đồng dữ liệu, transactions, lỗi, xử lý trùng lặp, kiểm thử và observability trong thực tế.

Sau bài học, bạn có thể:

1. Phân biệt send invoked, producer completion, broker acknowledgement, consumer delivery, business commit và consumer ACK/offset commit.
2. Giải thích kết quả `KafkaTemplate.send(...)` và tác dụng của `acks`, idempotent producer, group offset.
3. Giải thích RabbitMQ publisher confirms, mandatory returns, consumer `basic.ack`/`basic.nack` và prefetch.
4. Nhận diện transaction/acknowledgement modes của JMS.
5. Thiết kế outbox/inbox và business idempotency key bền vững.
6. Phân tích các failure windows khi một bên commit nhưng bên khác chưa ghi nhận ACK.
7. Viết integration tests cho retry, crash/replay, DLQ và broker outage.
8. Đo metrics khác nhau cho broker confirmed, consumer delivered và business applied.

> **Nguyên tắc:** Phải nói rõ **ai xác nhận, xác nhận điều gì, tại thời điểm nào và trong phạm vi transaction nào**. Chỉ ghi “message thành công” trong log hoặc dashboard là chưa đủ.

## 1. Các mốc của một message

~~~mermaid
sequenceDiagram
    participant P as Producer Service
    participant DB as Producer Database
    participant B as Broker
    participant C as Consumer
    participant R as Consumer Database
    P->>DB: Commit business state + outbox intent
    P->>B: Send event
    B-->>P: Publisher/broker ACK
    B->>C: Deliver record/message
    C->>R: BEGIN + apply event + inbox
    R-->>C: COMMIT
    C-->>B: Consumer ACK / commit offset
    Note over P,C: Publisher ACK và Consumer ACK không phải một
~~~

| Mốc | Bên phát bằng chứng | Có thể kết luận | Không thể kết luận |
| --- | --- | --- | --- |
| **Intent committed** | Producer database | Ý định phát sự kiện được lưu bền vững | Event đã ở broker |
| **Send invoked** | Producer app | Gửi đã được gọi/queued tại client | Broker đã nhận |
| **Producer send completed** | Producer client callback/future | Hoàn tất theo cấu hình producer | Consumer đã xử lý |
| **Broker accepted** | Kafka broker hoặc Rabbit publisher confirm | Broker xác nhận theo quy tắc của nó | Message được mọi downstream xử lý |
| **Consumer delivered** | Kafka poll/AMQP delivery | Consumer đã nhận quyền truy cập message | Handler đã commit |
| **Business committed** | Consumer DB/service | Side effect đã hoàn thành ở phạm vi được xác nhận | ACK broker đã thành công |
| **Consumer acknowledged** | Consumer→broker | Broker ghi nhận tiến độ/settlement | Một transaction SQL khác chắc chắn thành công |

Trong Kafka, consumer tiến độ được lưu bằng **offset commit** của group; record vẫn được giữ theo retention/compaction. Trong RabbitMQ, consumer ACK thường xác nhận một delivery và cho phép broker loại nó khỏi queue. Hai cơ chế **khác nhau** dù đều thường bị gọi tắt là “ack”.

### 1.1. Cần đặt tên trạng thái chính xác

Nên dùng trạng thái rõ như:

~~~text
OUTBOX_PENDING
  -> PRODUCER_IN_FLIGHT
  -> BROKER_CONFIRMED

CONSUMER_DELIVERED
  -> BUSINESS_APPLIED
  -> CONSUMER_ACKNOWLEDGED

CONSUMER_DELIVERED
  -> RETRY_PENDING
  -> PARKED_IN_DLQ
~~~

Đây là các **trạng thái hoặc sự kiện thuộc hai hệ thống khác nhau**, không nhất thiết một bảng duy nhất có thể nhìn thấy tất cả. Producer không tự biết consumer đã commit; nếu cần biết, thiết kế completion event, status API, shared audit store hoặc reconciliation.

### 1.2. Tại sao “đã gửi” dễ bị hiểu nhầm?

~~~text
t0    Service gọi KafkaTemplate.send()
t1    Hàm trả CompletableFuture
t2    Kafka client đưa record vào buffer
t3    Broker append/replicate theo acks policy
t4    Producer future hoàn tất thành công
t5    Consumer poll() lấy record
t6    Business transaction SQL commit
t7    Consumer commit offset
t8    Reporting UI hiển thị kết quả
~~~

Tại `t1` không thể khẳng định đã đến broker. Tại `t4` không thể khẳng định đã xử lý. Tại `t6` chưa chắc consumer offset đã commit. Và tại `t7` chưa chắc mọi cache/view khác đã được cập nhật.

## 2. Delivery semantics: at-most-once, at-least-once, exactly-once

| Semantics | Ý nghĩa | Trade-off |
| --- | --- | --- |
| **At-most-once** | Mỗi message có thể được thực hiện không quá một lần, nhưng có thể mất | Đơn giản nhưng không bảo đảm hoàn thành |
| **At-least-once** | Message được thử xử lý lại cho tới khi ghi nhận thành công theo policy | Consumer phải chống side effect trùng |
| **Exactly-once trong phạm vi hỗ trợ** | Một kết quả được commit một lần trong ranh giới công nghệ cụ thể | Không tự mở rộng tới SQL, HTTP, Redis và broker khác |

Ví dụ Kafka idempotent producer giảm duplicate do **producer retries bên trong một phiên producer** với sequence tương ứng. Kafka transactions có thể phối hợp records và consumer offsets theo cơ chế của Kafka khi xử lý **Kafka → Kafka**. Nhưng Kafka transaction không tự biến `INSERT INTO orders` của PostgreSQL và HTTP POST sang ERP thành cùng một transaction atomic.

**Khóa idempotency phải là business identity ổn định**, ví dụ `eventId`/`operationId` được giữ qua replay, không phải trace ID, Kafka offset, Rabbit delivery tag hay Spring Message ID.

## 3. Kafka producer: send và các cấu hình ACK

Spring Kafka cung cấp `KafkaTemplate<K,V>`. Trên Spring Kafka 3.x, `send(...)` trả `CompletableFuture<SendResult<K,V>>`:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>>
            publish(OrderEvent event) {

        return kafkaTemplate.send(
                "orders.events",
                event.orderId(),
                event);
    }
}
~~~

`OrderEvent` là một DTO/record hợp đồng ứng dụng được trình bày chi tiết ở mục 11. Producer cần serializer/topic/security settings phù hợp.

**Kết luận theo mốc:**

- `send(...)` được gọi và return future: **chưa chứng minh broker nhận**.
- Future hoàn thành bình thường: send hoàn thành **theo producer `acks` config**.
- `SendResult.getRecordMetadata()`: có topic/partition/offset để đối soát trong Kafka, **không phải kết quả xử lý consumer**.
- Future hoàn thành exceptionally: có lỗi producer, nhưng nếu ACK bị mất sau khi broker append, **không chắc message chưa tồn tại**.

### 3.1. Một callback đúng ý nghĩa

~~~java
public void publishWithCallback(OrderEvent event) {

    kafkaTemplate
            .send("orders.events", event.orderId(), event)
            .whenComplete((result, failure) -> {
                if (failure != null) {
                    // Lưu attempt error / unknown để retry và đối soát.
                    // Không kết luận broker chắc chắn chưa nhận.
                    recordPublishFailure(event.eventId(), failure);
                    return;
                }

                var metadata = result.getRecordMetadata();

                // Đây chỉ là producer/broker completion.
                recordBrokerConfirmed(
                        event.eventId(),
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset());
            });
}
~~~

Các method `recordPublishFailure` và `recordBrokerConfirmed` là cổng minh họa. Callback bất đồng bộ có thể xảy ra sau khi HTTP response đã trả; process crash ngay sau broker ACK nhưng trước khi DB ghi trạng thái có thể dẫn đến retry và duplicate. Không đặt business status `CONSUMER_PROCESSED` từ callback producer.

### 3.2. acks=0, acks=1, acks=all

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
~~~

| Setting | Điều kiện producer coi là thành công | Ý nghĩa đối với durability |
| --- | --- | --- |
| `acks=0` | Producer không chờ broker xác nhận | Rất dễ đánh mất bằng chứng broker đã nhận |
| `acks=1` | Leader broker xác nhận | Có thể mất khi leader hỏng trước khi replica đủ dữ liệu |
| `acks=all` hoặc `acks=-1` | Leader chờ đủ acknowledgements theo ISR/policy | Phụ thuộc replication factor, `min.insync.replicas` và cluster health |
| `enable.idempotence=true` | Dùng producer sequence để hạn chế duplicate từ retry nội bộ | Không chống business event được publish lại từ outbox mới |
| `delivery.timeout.ms` | Deadline của producer cho việc delivery | Không đồng nghĩa request chưa tới broker khi timeout |
| `max.in.flight.requests.per.connection` | Mức in-flight requests | Cần tương thích ordering/idempotence policy |

**Không diễn giải `acks=all` là “mọi broker trên cluster đã lưu vĩnh viễn”.** Nó phụ thuộc ISR hiện hành, cấu hình topic, số replica, min ISR và tính toàn vẹn của storage. Với cluster chỉ một replica, `acks=all` vẫn không tạo ra HA.

### 3.3. ACK bị mất có thể gây duplicate

~~~mermaid
sequenceDiagram
    participant P as Kafka Producer
    participant K as Kafka Broker
    P->>K: Produce eventId=E-100
    K->>K: Append record
    K--xP: ACK lost / network interruption
    P->>P: Timeout / unknown outcome
    P->>K: Retry eventId=E-100
    Note over P,K: Broker hoặc consumer có thể thấy duplicate
~~~

Producer idempotence hỗ trợ một số producer-retry windows, nhưng nếu ứng dụng tạo **một record khác sau restart**, consumer vẫn phải dedupe bằng `eventId` nếu nghiệp vụ không cho phép áp dụng lại.

### 3.4. Producer ACK không đo consumer lag

`RecordMetadata` chứa offset của record trong partition. Consumer có thể chưa subscribe, đang replay dữ liệu cũ, bị rebalancing, hoặc đã đọc nhưng DB transaction thất bại. Dashboard cần đặt **producer confirmation** và **consumer business outcome** thành hai nhóm riêng.

## 4. Kafka consumer: nhận record và commit offset

~~~mermaid
sequenceDiagram
    participant K as Kafka Broker
    participant C as Consumer
    participant D as Reporting DB
    K->>C: Poll event offset=1042
    C->>D: BEGIN + update projection + inbox
    D-->>C: COMMIT OK
    C->>K: Commit offset=1043
    Note over C,K: ACK/commit offset có thể fail sau DB COMMIT
~~~

Kafka có các khái niệm:

- **Record offset:** vị trí record trong một partition.
- **Consumer position:** vị trí sẽ fetch tiếp của consumer đang chạy.
- **Committed offset:** vị trí đã lưu bền cho consumer group.
- **Consumer lag:** chênh lệch giữa log end offset và tiến độ theo cách đo.

Lag bằng 0 không tự chứng minh các message đã được commit đúng về business: có thể offset được commit sớm, handler lọc bỏ sai hoặc update chỉ ở RAM.

### 4.1. Spring Kafka manual acknowledgment

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
~~~

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final OrderProjectionService service;

    public OrderProjectionListener(
            OrderProjectionService service) {
        this.service = service;
    }

    @KafkaListener(
            topics = "orders.events",
            groupId = "reporting-projection")
    public void consume(
            OrderEvent event,
            Acknowledgment acknowledgment) {

        service.applyIdempotently(event);

        // Chỉ ACK sau khi service đã commit thành công.
        acknowledgment.acknowledge();
    }
}
~~~

`OrderProjectionService` cần thực sự tạo transaction và hoàn tất commit trước khi return. Container phải cấu hình manual acknowledgement; đây là ví dụ dành cho Kafka listener synchronous. Nếu service chỉ tạo `CompletableFuture` hoặc đẩy sang executor rồi return, việc ACK ngay sau đó **có thể làm mất message** khi process crash.

### 4.2. Failure window: ACK trước database commit

~~~text
Record delivered
    |
    +-- Commit Kafka offset
    |
    +-- SQL UPDATE
          |
          +-- Process crash / SQL rollback
~~~

Consumer group có thể tiếp tục từ offset mới; record chưa được apply sẽ không tự quay lại trong dòng tiêu thụ bình thường. Đây là một cách tạo **at-most-once business effect** ngoài ý muốn.

### 4.3. Failure window: database commit trước offset ACK

~~~text
Record delivered
    |
    +-- SQL COMMIT thành công
    |
    +-- Process crash trước offset commit
    |
    +-- Redelivery cùng eventId
~~~

Đây là tình huống bình thường trong at-least-once. Cần **idempotent consumer**: insert inbox record và business update trong cùng database transaction để replay không gây side effect mới.

### 4.4. Rebalance, partition và thứ tự

Một Kafka consumer group phân phối partitions giữa các instances. Khi rebalance, record chưa có committed progress có thể xuất hiện lại. Không dùng in-memory `Set<eventId>` làm dedupe vì instance mới không có lịch sử.

Thứ tự Kafka có ý nghĩa theo **partition**, không có thứ tự toàn cục giữa partitions. Nếu các event của một order phải xử lý theo version, dùng Kafka message key theo `orderId` và kiểm tra `aggregateVersion` tại database. Partitioning giúp ordering nhưng không thay business version guard.

## 5. RabbitMQ publisher: confirms và returns là hai chuyện khác nhau

RabbitMQ publisher gửi message vào **exchange**, rồi exchange route tới một hoặc nhiều queues theo binding/routing key.

~~~mermaid
flowchart LR
    P["RabbitTemplate publisher"] --> E["Exchange"]
    E -->|"Binding match"| Q["Queue"]
    E -->|"No binding"| U["Unroutable"]
    E -. "Publisher confirm ACK" .-> P
    U -. "Return if mandatory" .-> P
    Q --> C["Consumer"]
    C -. "basic.ack / basic.nack" .-> Q
~~~

Publisher confirm xác nhận broker đã xử lý publish theo cơ chế của RabbitMQ. Nhưng nếu **không có binding phù hợp**, một message có thể được confirm ACK mà không nằm trong queue mong đợi. Để xác minh khả năng routing, dùng `mandatory` và publisher returns theo chính sách.

### 5.1. Cấu hình correlated confirm và returns

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
~~~

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Các tên tài khoản/mật khẩu phải được cấu hình từ nguồn bí mật của môi trường. `publisher-confirm-type=correlated` cho phép liên kết confirm với publish cụ thể. `publisher-returns=true` kết hợp `mandatory=true` giúp nhận thông báo về unroutable messages theo semantics broker.

### 5.2. CorrelationData và confirm callback

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class RabbitOrderPublisher {

    private final RabbitTemplate rabbitTemplate;

    public RabbitOrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(OrderEvent event) {
        CorrelationData data =
                new CorrelationData(event.eventId());

        rabbitTemplate.convertAndSend(
                "orders.exchange",
                "order.confirmed",
                event,
                data);

        data.getFuture().whenComplete((confirm, failure) -> {
            if (failure != null) {
                recordPublishError(event.eventId(), failure);
                return;
            }

            if (!confirm.isAck()) {
                recordNack(event.eventId(), confirm.getReason());
                return;
            }

            // Broker confirmed; kiểm tra returns/routing riêng.
            recordConfirmAndReturn(
                    event.eventId(), data.getReturned());
        });
    }
}
~~~

Các methods `recordPublishError`/`recordNack`/`recordConfirmAndReturn` là application-specific. `getFuture()` và `getReturned()` thuộc Spring AMQP hiện đại, cần đối chiếu version; message converter và exchange phải được cấu hình đúng.

**Lưu ý:** `RabbitTemplate.convertAndSend(...)` không throw chỉ cho biết lời gọi publish tại client không bị lỗi ngay. Callback confirm **không** chứng minh consumer đã xử lý. Nếu outbox cần biết kết quả routing, phải lưu và phân loại returned message ngoài confirm.

### 5.3. Durability của RabbitMQ không chỉ là confirm

Các yếu tố liên quan:

- Durable exchange/queue topology.
- Persistent message delivery mode khi cần.
- Queue type (classic/quorum), replication/failover.
- Publisher confirms và publisher returns.
- Message TTL, queue expiration, dead-letter settings.
- Broker disk/memory alarms, storage reliability và policies.

Một message đã được confirm vẫn có thể hết hạn, bị route sai, bị consumer xử lý rồi ACK hoặc bị xóa theo lifecycle policy. Không đồng nhất **publisher-confirmed** với “message chắc chắn còn mãi trong queue”.

## 6. RabbitMQ consumer ACK: nhận trách nhiệm sau xử lý

Các phương thức AMQP:

| API | Ý nghĩa |
| --- | --- |
| `basic.ack(deliveryTag, false)` | ACK một delivery cụ thể |
| `basic.ack(deliveryTag, true)` | ACK nhiều deliveries chưa ack tới delivery tag trong channel |
| `basic.nack(tag, false, true)` | Từ chối và requeue theo broker policy |
| `basic.nack(tag, false, false)` | Từ chối, không requeue; có thể dead-letter nếu cấu hình |
| `basic.reject(tag, requeue)` | Từ chối một message |
| `basic.qos(prefetch)` | Giới hạn deliveries chưa ACK ở phạm vi áp dụng |

Manual consumer ack trong Spring AMQP:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 10
~~~

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderRabbitConsumer {

    private final OrderProjectionService service;

    public OrderRabbitConsumer(
            OrderProjectionService service) {
        this.service = service;
    }

    @RabbitListener(queues = "orders.reporting")
    public void consume(
            OrderEvent event,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG)
            long deliveryTag) throws IOException {

        service.applyIdempotently(event);

        channel.basicAck(deliveryTag, false);
    }
}
~~~

Ví dụ giả định đã có message converter ánh xạ body sang `OrderEvent`, Rabbit listener container và xử lý lỗi phù hợp. Khi `service.applyIdempotently` ném lỗi, handler phải có policy requeue/retry/DLQ rõ. Không mặc định một exception trong manual mode sẽ tự ACK/NACK như ý muốn.

### 6.1. Vì sao ACK sớm nguy hiểm?

~~~text
Broker delivers message
  -> Handler pushes work into in-memory executor
  -> basic.ack() ngay
  -> Worker process crashes
  -> Work in RAM lost
~~~

Broker đã loại delivery khỏi queue trước khi tác động bền vững được thực hiện. Nếu cần xử lý bất đồng bộ, **handoff phải được lưu bền** (work table/outbox hoặc broker durable khác) rồi mới ACK source.

### 6.2. Requeue liên tục gây retry storm

Nếu một message vi phạm schema mà consumer luôn gọi `basic.nack(requeue=true)`, RabbitMQ có thể redeliver ngay làm CPU/logs tăng và cản trở các messages tốt. Với permanent error, đẩy đến DLQ/parking theo policy; với transient error, dùng delayed retry/backoff có giới hạn.

**Handoff tới DLQ cũng cần được xác nhận:** nếu consumer tự publish vào DLQ rồi ACK message gốc trước khi broker xác nhận DLQ publish, crash có thể làm mất message ở cả hai nơi. Broker dead-lettering có cơ chế khác nhau theo queue type; kiểm thử semantics thật.

### 6.3. Prefetch và concurrency

Prefetch giới hạn số deliveries chưa ACK; nó không tạo parallelism một cách tự động. Concurrency phụ thuộc listener container, executor, database pool và throughput của handler. Prefetch quá lớn làm tăng messages in-flight, mức độ requeue sau crash và memory pressure.

## 7. JMS acknowledgement và Spring transaction

JMS cũng có các ranh giới send, provider receipt, consumer delivery và application processing, nhưng APIs khác Kafka/RabbitMQ.

| JMS mode | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Provider/container ACK theo lifecycle của receive/listener | Không mặc định kết hợp SQL transaction |
| `CLIENT_ACKNOWLEDGE` | Client chủ động gọi `Message.acknowledge()` | Có thể ACK nhiều messages đã nhận cùng session |
| `DUPS_OK_ACKNOWLEDGE` | Cho phép lazy acknowledgements | Duplicate có thể xuất hiện |
| `SESSION_TRANSACTED` | JMS session commit/rollback cục bộ | Không tự atomic với JDBC |
| XA/JTA | Phối hợp resource managers trong transaction phân tán được cấu hình | Chi phí/độ phức tạp, broker/DB phải hỗ trợ |

`JmsTemplate.send(...)` hoàn tất không chứng minh listener đã hoàn tất nghiệp vụ. `@JmsListener` hoạt động theo acknowledgement và transaction config của listener container.

Một `@Transactional` sử dụng `DataSourceTransactionManager` không tự đưa JMS session hoặc Kafka offset vào cùng database transaction. Cần chỉ định đúng transaction manager, hoặc dùng outbox/inbox nếu không lựa chọn XA/JTA.

## 8. Bảng đối chiếu ba nền tảng

| Câu hỏi | Kafka | RabbitMQ | JMS |
| --- | --- | --- | --- |
| Producer completion | Send future/callback theo `acks` | Publisher confirm (nếu bật) | Theo JMS provider/send semantics |
| Định tuyến | Topic/partition key | Exchange, binding, routing key → queue | Provider destination |
| Consumer progress | Offset commit của consumer group | Consumer `basic.ack`/`nack` | Session acknowledgement/transaction |
| Message còn sau consumption? | Kafka log theo retention/compaction | Queue message thường được settled/removed sau ACK | Theo provider/destination |
| Redelivery khi crash? | Có nếu offset chưa commit | Có nếu delivery chưa ACK hoặc bị requeue | Có theo mode/provider |
| Producer ACK = consumer processed? | **Không** | **Không** | **Không** |
| Consumer ACK atomic với SQL? | **Không mặc định** | **Không mặc định** | **Không mặc định** |
| Hỗ trợ dead-letter | DLT topic/app policy | DLX/DLQ topology | Provider/application policy |

Khi viết telemetry, sử dụng tên rõ như `kafka.producer.acked`, `rabbitmq.publisher.confirmed`, `rabbitmq.consumer.acked`, `kafka.consumer.offset.committed` và `business.event.applied`. Tránh một counter tên `messages.success` chung cho mọi tầng.

## 9. Transactional outbox: ghi ý định gửi cùng nghiệp vụ

Anti-pattern:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    orderRepository.markConfirmed(orderId);
    kafkaTemplate.send(
            "orders.events",
            orderId,
            new OrderConfirmed(orderId));
}
~~~

Với Kafka async, gọi `send(...)` trong JDBC transaction **không** tạo transaction chung. Event có thể publish dù SQL rollback, hoặc SQL commit nhưng publish thất bại. Cần thiết kế transaction boundary rõ ràng.

### 9.1. Outbox flow

~~~mermaid
flowchart LR
    A["Order command"] --> B["SQL transaction"]
    B --> C["Update order"]
    B --> D["Insert outbox event"]
    D --> E["Relay / CDC / worker"]
    E --> F["Kafka/RabbitMQ/JMS"]
    F --> G["Consumer"]
    G --> H["Inbox + business update"]
    E -.-> I["Retry + monitor broker confirms"]
~~~

Trong **cùng SQL transaction**, update order và insert outbox row chứa `eventId` duy nhất, payload contract và trạng thái PENDING. Khi transaction commit, hệ thống đã nhận trách nhiệm giữ ý định phát; relay đọc outbox để gửi, ghi broker outcome và retry khi cần.

### 9.2. SQL schema minh họa PostgreSQL

~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version INT NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    broker_confirmed_at TIMESTAMPTZ NULL
);

CREATE INDEX idx_outbox_due
ON integration_outbox(status, next_attempt_at, created_at);
~~~

`event_id` không được đổi mỗi lần publish lại; nếu đổi ID, consumer inbox không thể nhận diện một intent bị replay. Cần kế hoạch lưu giữ/truy cập payload có PII và lifecycle archive/delete phù hợp quy định.

### 9.3. Publish confirm không tạo exactly-once end-to-end

~~~mermaid
sequenceDiagram
    participant R as Outbox Relay
    participant B as Broker
    participant D as SQL Outbox
    R->>B: Publish eventId=E-100
    B-->>R: Broker confirmed ACK
    R->>D: Update BROKER_CONFIRMED
    Note over R,D: Process crash trước SQL commit
    R->>B: Retry E-100 khi restart
    Note over R,B: Có thể có duplicate record
~~~

Outbox thường bảo đảm **at-least-once publication**. Nếu broker ACK thành công rồi process crash trước khi ghi `BROKER_CONFIRMED`, một lần retry nữa là hợp lý để tránh mất event. Consumer phải chịu được duplicate.

### 9.4. Claim outbox nhiều workers

Trong PostgreSQL, `FOR UPDATE SKIP LOCKED` có thể giúp nhiều workers chọn rows không đụng nhau **khi row lock được giữ trong transaction**.

~~~sql
SELECT event_id, payload
FROM integration_outbox
WHERE status = 'PENDING'
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

Đây chỉ là bước chọn trong transaction. Sau khi transaction kết thúc, lock được thả. Nếu publish diễn ra ngoài transaction, phải thiết kế **status/lease owner, expiry và reclaim** bền vững; đừng nghĩ một `SELECT ... SKIP LOCKED` tự khóa row suốt thời gian gửi broker.

## 10. Consumer inbox: thực hiện side effect đúng một lần theo eventId

Consumer dùng một business event key đáng tin cậy như `eventId` để kiểm tra đã xử lý:

~~~sql
CREATE TABLE processed_integration_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Mỗi consumer có nghiệp vụ riêng nên khóa gồm `consumer_name + event_id` để hai consumers khác nhau vẫn xử lý hợp lệ cùng event.

### 10.1. Transaction idempotent PostgreSQL

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbcTemplate;

    public OrderProjectionService(
            JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void applyIdempotently(OrderEvent event) {

        int inserted = jdbcTemplate.update(
                """
                INSERT INTO processed_integration_events(
                    consumer_name, event_id, processed_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (consumer_name, event_id)
                DO NOTHING
                """,
                "reporting-projection",
                UUID.fromString(event.eventId()));

        if (inserted == 0) {
            return; // Duplicate, business side effect đã thực hiện.
        }

        jdbcTemplate.update(
                """
                INSERT INTO reporting_orders(order_id, state)
                VALUES (?, ?)
                ON CONFLICT (order_id)
                DO UPDATE SET state = EXCLUDED.state
                """,
                event.orderId(),
                event.state());
    }
}
~~~

Bảng `reporting_orders` phải được tạo bằng migration. Ví dụ giả định `event.eventId()` là UUID string hợp lệ và service method được gọi qua Spring proxy `@Transactional` với đúng transaction manager. `INSERT inbox` và `UPDATE/INSERT business` phải commit **cùng một SQL transaction**. Nếu update lỗi, cả inbox insert phải rollback, không được để event được đánh dấu processed nhưng nghiệp vụ chưa áp dụng.

**Chú ý ordering:** Dedupe event ID không ngăn event version cũ ghi đè bản mới. Với aggregate có `aggregateVersion`, repository cần điều kiện cập nhật chỉ áp dụng khi version cao hơn/đúng sequence.

### 10.2. External side effects không nằm trong cùng SQL transaction

Nếu consumer ghi inbox rồi gửi HTTP/SMTP, việc HTTP đã chấp nhận hay chưa không tự được rollback cùng PostgreSQL. Có thể ghi inbox + **outbox tiếp theo** trong một transaction, sau đó adapter riêng gửi HTTP với operationId ổn định và reconciliation.

Không dùng inbox SQL để khẳng định một thanh toán ở remote ERP đã thực hiện exactly-once nếu remote API không có idempotency/lookup.

## 11. Schema và hợp đồng thông điệp

Ví dụ event:

~~~java
public record OrderEvent(
        String eventId,
        String orderId,
        long aggregateVersion,
        String eventType,
        int schemaVersion,
        String state,
        String occurredAt) {
}
~~~

| Thuộc tính | Công dụng |
| --- | --- |
| `eventId` | Khóa dedupe qua retry/redelivery |
| `orderId` | Khóa nghiệp vụ và Kafka partition key |
| `aggregateVersion` | Chặn event cũ ghi đè state mới |
| `eventType` | Phân loại message/handler |
| `schemaVersion` | Tiến hóa hợp đồng serializer |
| `state` | Trạng thái nghiệp vụ |
| `occurredAt` | Audit, không thay idempotency key |
| `traceId` (header) | Liên kết observability một attempt |

Khi retry publish **cùng một ý định**, giữ nguyên `eventId` và business fields. Broker metadata như Kafka offset, RabbitMQ delivery tag và Spring `Message.id` có thể thay đổi mỗi lần, không làm khóa dedupe phù hợp.

Schema Registry, JSON Schema, Avro hoặc Protobuf có thể giúp enforce schema evolution, nhưng broker ACK không có nghĩa payload đã pass business validation hoặc authorized cho tenant.

## 12. Failure windows theo trình tự

| Failure window | Hậu quả | Hướng thiết kế |
| --- | --- | --- |
| SQL commit trước publish, process crash | Ý định gửi có thể mất | Outbox |
| Publish trước SQL commit, SQL rollback | Consumer thấy sự kiện chưa có thật | Outbox cùng SQL transaction |
| Broker append nhưng producer không nhận ACK | Producer timeout, có thể gửi lại | Stable eventId, idempotent producer, consumer inbox |
| Rabbit confirm ACK nhưng không route | Không có queue nhận | Mandatory returns và binding tests |
| Producer confirm trước outbox state update, crash | Duplicate publish khi replay | Consumer idempotency |
| Consumer ACK trước SQL commit, crash | Mất business effect | ACK sau commit |
| Consumer SQL commit trước ACK, crash | Redelivery và duplicate attempt | Inbox/unique constraint |
| Consumer handoff vào RAM rồi ACK | Pending work mất sau restart | Durable handoff |
| Filter/permanent error bị requeue mãi | Retry storm, backlog | DLQ/parking/rejection store |
| DLT publish chưa confirmed nhưng ACK nguồn | Có thể mất message hoàn toàn | Durable DLQ handoff |
| Consumer apply event cũ sau event mới | State bị đảo ngược | AggregateVersion/partition ordering |

### 12.1. Khoảng DB commit trước consumer ACK là bình thường

Với at-least-once, consumer **cố tình** cho phép redelivery khi ACK thất bại, vì nếu ACK trước business commit sẽ có nguy cơ mất tác động. Do đó business consumer phải idempotent. “Consumer nhận trùng” không tự là lỗi broker.

### 12.2. ACK một message lỗi cũng có thể đúng

Nếu message sai schema, consumer không nên retry vô hạn. Sau khi **ghi rejection hoặc chuyển bền vững vào DLQ**, policy có thể ACK message nguồn để tránh poison message chặn queue. Nhưng trạng thái business vẫn là `REJECTED`/`PARKED`, không phải `SUCCESS`.

## 13. Retry, dead letter và concurrency

### 13.1. Phân loại lỗi

| Loại | Ví dụ | Policy |
| --- | --- | --- |
| Payload sai schema/invalid data | Missing required field, unknown contract | Không retry vô hạn; reject/DLQ |
| Broker temporarily unavailable | Connect/rebalance/broker outage | Retry có backoff và budget |
| Database deadlock/timeout | SQL transient failure | Retry transaction/item với idempotency |
| Authorization sai | ACL/credential lỗi | Sửa cấu hình, alert |
| Downstream HTTP 503 | Partner overload | Retry giới hạn, circuit breaker |
| Downstream request timeout sau write | Outcome unknown | Status lookup/idempotency/reconciliation |
| Duplicate event ID | Inbox đã có | Không apply lại, có thể ACK |

Không để producer retry 3 lần, listener retry 3 lần, HTTP client retry 3 lần và scheduler retry 3 lần một cách vô tình. Tổng attempts có thể tăng nhanh và làm downstream quá tải. Chọn ranh giới retry chủ đạo và theo dõi budget.

### 13.2. Dead letter không tương đương business completion

Kafka DLT hoặc RabbitMQ DLQ dùng để giữ sự kiện không xử lý được, hỗ trợ kiểm tra và replay. Một message đến DLT chứng minh nó đã bị **parked** theo workflow, không phải nghiệp vụ downstream thành công. Dashboard không cộng DLT count vào `business_applied`.

### 13.3. Concurrency và ordering

Kafka: partition key giúp giữ thứ tự theo key/partition, nhưng có thể xuất hiện replay; dùng version guard.

RabbitMQ: prefetch và listener concurrency quyết định số deliveries in flight, không bảo đảm completion order.

JMS: destination/provider concurrency và session transaction ảnh hưởng ordering/ack semantics.

Không dùng thời gian message “được nhận” làm bằng chứng tác động “đã commit” nếu handler xử lý async trên worker threads.

## 14. Observability phân tầng

| Metric | Đo gì | Không chứng minh |
| --- | --- | --- |
| `integration.outbox.created` | Số ý định gửi được commit | Broker đã nhận |
| `integration.producer.attempts` | Lượt gửi | Thành công |
| `integration.producer.confirmed` | Broker xác nhận theo policy | Consumer xử lý |
| `integration.producer.returned` | Rabbit publisher return/unroutable | Consumer xử lý |
| `integration.consumer.deliveries` | Message consumer nhận | DB commit |
| `integration.consumer.business_applied` | Side effect commit thành công | Consumer offset commit |
| `integration.consumer.duplicates` | Inbox dedupe | Dữ liệu luôn hợp lệ |
| `integration.consumer.ack_errors` | Lỗi ghi tiến độ ACK/offset | Business failed |
| `integration.consumer.dlq` | Message được parked | Business success |
| `integration.end_to_end.lag` | Trễ từ intent đến business outcome | Mỗi phase riêng lẻ |

Một trường hợp hợp lệ:

~~~text
Producer broker-confirmed events: 100
Consumer deliveries:            104
Unique business applied:        98
Duplicate deliveries:            4
Parked in DLQ:                   2
~~~

Những số liệu này có thể nhất quán vì broker/consumer thực hiện **at-least-once**, còn hai event chưa áp dụng được giữ trong DLQ. Không đánh dấu “100/100 business success” từ `producer confirmed=100`.

### 14.1. Các loại latency

- **Producer acknowledgement latency:** lúc send đến producer callback/future completion.
- **Broker/consumer lag:** thời gian record ở broker trước khi được consumer xử lý.
- **Business processing latency:** từ handler bắt đầu đến business transaction commit.
- **ACK/offset commit latency:** ghi nhận tiến độ sau xử lý.
- **End-to-end business latency:** từ producer intent commit đến downstream business effect hoàn tất.

Một producer p95 rất thấp có thể đi kèm consumer lag hàng giờ nếu consumer crash hoặc database chậm. Muốn điều tra nguyên nhân, quan sát cả ingress rate, broker backlog, database pool và business handler.

### 14.2. Micrometer Observation cho business processing

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public void observedApply(
        ObservationRegistry registry,
        OrderProjectionService service,
        OrderEvent event) {

    Observation.createNotStarted(
                    "integration.order.consumer.apply", registry)
            .lowCardinalityKeyValue(
                    "consumer", "reporting-projection")
            .observe(() ->
                    service.applyIdempotently(event));
}
~~~

Observation đo lời gọi synchronous; nếu method `@Transactional` được proxy và commit xảy ra lúc method return, timer có thể bao gồm phần commit theo instrumentation. Nó không tự đo Kafka offset commit vì method chưa gọi `acknowledge()` tại đây.

Tags nên hữu hạn, ví dụ `broker=kafka`, `topic=orders.events`, `outcome=applied/duplicate/error`. Không đặt `eventId`, `orderId`, `customerId` hay raw payload vào Prometheus labels; dùng audit/log/trace IDs có kiểm soát để đối soát một sự kiện.

## 15. Kiểm thử từng ranh giới

### 15.1. Unit test producer callback

Test các trường hợp:

1. `send(...)` trả future chưa hoàn tất: không ghi BROKER_CONFIRMED.
2. Future completed normally: chỉ cập nhật broker confirmed.
3. Future failed: giữ outbox retryable/unknown theo policy.
4. Rabbit confirm ACK nhưng return unroutable: không coi là queued tới consumer.
5. Callback bị bỏ qua khi process crash: outbox vẫn có thể replay.

Đây là test của **adapter publish**, không phải end-to-end test của consumer.

### 15.2. Test SQL inbox idempotency

Một test integration với PostgreSQL Testcontainers nên assert:

~~~text
Given eventId=E-100 and orderId=ORD-100
When consumer applies event first time
Then inbox has one row for (consumer, E-100)
And reporting business state is updated once

When the same E-100 is delivered again
Then inbox still has one row
And business effect is not applied twice
~~~

Với concurrent duplicate deliveries, cần test hai transactions cùng cố insert `(consumer_name,event_id)`; unique constraint phải bảo vệ race. Không dựa vào `SELECT exists` trong application rồi mới insert mà thiếu unique constraint.

### 15.3. Test crash giữa DB COMMIT và ACK

~~~text
Given consumer received E-100
And SQL transaction committed business + inbox
When process crashes before consumer ACK
And broker redelivers E-100
Then consumer detects duplicate
And no extra business effect occurs
And consumer can ACK again safely
~~~

Đây là test quan trọng nhất cho at-least-once consumer. Dù mock listener có thể minh họa, kiểm thử thực cần DB transaction và broker behavior phù hợp.

### 15.4. Kafka integration tests

Dùng EmbeddedKafka hoặc Kafka Testcontainers để kiểm tra:

- Kafka producer future, partition key và record metadata.
- Manual ack mode và committed group offset.
- Consumer failure trước DB commit dẫn đến retry.
- Consumer crash sau DB commit, replay và inbox dedupe.
- Rebalance/concurrency không phá aggregate ordering policy.
- DLT/parking semantics và business status.

Một Kafka test broker single-node không chứng minh multi-broker durability/ISR failover. Nếu cần bảo đảm HA, kiểm thử thêm môi trường có topology tương tự production.

### 15.5. RabbitMQ integration tests

Dùng RabbitMQ Testcontainers hoặc broker test instance:

- Exchange, routing keys, queue bindings, publisher confirms.
- Unroutable mandatory return dù confirm ACK.
- Manual consumer ACK sau business commit.
- Nack/requeue và DLX behavior.
- Listener crash trước ACK khiến message có thể redeliver.
- Queue durability/persistence/quorum theo config thật.

Không bắn load test vào broker production nếu chưa có quyền và giới hạn an toàn.

### 15.6. Test asynchronous handoff

Nếu consumer chỉ đưa work vào executor rồi ACK:

~~~text
Consumer receives E-100
    |
    +-- executor.submit(task)
    |
    +-- consumer ACK
    |
    +-- JVM crashes before task runs
~~~

Đó là **mất việc** nếu task chưa được ghi bền. Test nên inject crash hoặc stop consumer sau handoff, rồi xác minh durable work table/queue vẫn giữ trách nhiệm xử lý; chỉ khi handoff bền vững mới ACK.

## 16. Runbook khi producer nói thành công mà consumer chưa thấy

1. Xác minh producer thật sự chờ future/confirm hay chỉ không bị exception khi gọi send.
2. Kiểm tra `acks` và topic replication/min ISR của Kafka; confirms/returns/routing của RabbitMQ.
3. Xác nhận topic/partition hoặc exchange/routing key/queue đúng môi trường.
4. Kiểm tra retention/TTL, DLT/DLQ, queue policies và khả năng message đã được consumer ACK.
5. Xác nhận consumer group/queue binding, quyền broker ACL và credential.
6. Kiểm tra Kafka committed offset/lag hoặc RabbitMQ ready/unacked, prefetch và requeue.
7. Kiểm tra handler logs, schema errors, SQL transaction state, inbox và business tables.
8. Kiểm tra có redelivery/duplicate đang được xử lý đúng hay bị lọc nhầm.
9. Đối soát eventId/operationId ổn định qua producer và consumer audit.
10. Replay có kiểm soát, không tạo eventId mới cho cùng một ý định gửi.

### 16.1. Bảng chẩn đoán nhanh

| Dấu hiệu | Khả năng | Kiểm tra |
| --- | --- | --- |
| Kafka send không throw | Send chỉ được queue async | Future/callback và `acks` |
| Kafka offset tồn tại | Broker ghi record | Consumer group/business outcome |
| Kafka lag bằng 0 nhưng report thiếu | ACK/offset commit sớm hoặc handler bỏ qua | Inbox, DB transaction, errors |
| Rabbit confirm ACK nhưng queue rỗng | Unroutable hoặc consumer đã ACK | Publisher returns và bindings |
| Rabbit unacked tăng | Worker chậm, DB pool cạn, handler treo | Prefetch, database locks, thread metrics |
| Redelivery lặp liên tục | Poison message, requeue không delay | DLQ/error taxonomy |
| Duplicate sau crash | DB COMMIT trước ACK | Inbox/idempotency |
| Outbox BROKER_CONFIRMED nhưng report chưa có | Consumer lag, DLT hoặc failure | Consumer business completion |
| DLT count tăng nhưng success dashboard vẫn tốt | Nhầm producer confirmed và applied | Tách success counters |

**Không sửa offset, purge queue hoặc force-ack** để làm “sạch backlog” trước khi xác nhận business state và khả năng recovery.

## 17. Bảo mật và hợp đồng dữ liệu

- Kafka/RabbitMQ/JMS clients dùng TLS/mTLS/SASL/auth phù hợp; xác minh certificate và hostname.
- Broker ACLs giới hạn publish/consume theo topic, exchange, queue và service identity.
- Không hardcode secrets trong YAML/repository; không ghi raw payload chứa PII vào logs hoặc metric tags.
- Validate serializer/schemaVersion và business constraints cả phía producer/consumer.
- Không tin `tenantId`/`eventType`/`operationId` do caller ngoài không được xác thực tự khai báo.
- Thiết lập retention, dead-letter và audit lifecycle phù hợp dữ liệu nhạy cảm.
- Tách staging/test topics, consumer groups và credentials khỏi production.

Broker ACK phản ánh protocol/broker contract, **không chứng minh message hợp lệ về nghiệp vụ hoặc service có quyền hành động thay tenant**. Authorization vẫn phải được kiểm tra ở application/domain boundary.

## 18. Checklist triển khai

- [ ] Đã đặt tên rõ ràng cho send invoked, broker confirmed, delivered, business applied và consumer acknowledged.
- [ ] Producer không coi return của send async là broker ACK.
- [ ] Kafka `acks`/idempotence/min ISR/topic replication được cấu hình và kiểm thử theo policy.
- [ ] RabbitMQ publisher confirms, mandatory returns và queue bindings được kiểm tra riêng.
- [ ] Consumer ACK/commit offset chỉ sau business commit hoặc **durable handoff** phù hợp.
- [ ] Không dùng RAM queue/callback in-memory làm bằng chứng durable.
- [ ] Producer có transactional outbox khi phải phối hợp với SQL.
- [ ] Consumer có inbox/unique constraint và business write cùng local transaction.
- [ ] Event ID/operationId ổn định qua retries; trace ID/offset không thay business identity.
- [ ] DLQ/parking được coi là trạng thái lỗi chờ xử lý, không phải business success.
- [ ] Có backoff/retry budget, phân loại permanent vs transient và tránh retry storm.
- [ ] Có ordering/version guard khi các events của một aggregate ảnh hưởng cùng state.
- [ ] Có tests crash trước/sau producer confirm, DB COMMIT và consumer ACK.
- [ ] Có metrics riêng cho producer acknowledgements, consumer deliveries, applied/duplicate, lag và DLT.
- [ ] Broker TLS/ACL/secrets, schema evolution và payload privacy được quản lý.

**Ghi nhớ:** **Đã gửi**, **broker đã nhận**, **consumer đã xử lý** là ba mốc khác nhau. Producer future/publisher confirm phản ánh kết quả publish theo broker configuration; Kafka offset commit hoặc RabbitMQ consumer ACK phản ánh tiến độ tiêu thụ; chỉ một **business commit hoặc completion event đáng tin cậy** mới chứng minh tác động nghiệp vụ đã hoàn thành. Tích hợp production cần kết hợp outbox, inbox/idempotency, retry có giới hạn, kiểm thử failure windows và observability theo từng tầng.

## Tài liệu tham khảo

- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs): acks, retries, idempotence và producer delivery timeouts.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): group offsets, auto commit và isolation.
- [Apache Kafka — Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-most-once, at-least-once và exactly-once theo phạm vi.
- [Spring Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): KafkaTemplate future và callbacks.
- [Spring Kafka — Message Listener Container](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): manual acknowledgement và offset commits.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): hai loại ACK và failure handling.
- [RabbitMQ — Reliability](https://www.rabbitmq.com/docs/reliability): durability, broker failures và recovery.
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): RabbitTemplate/CorrelationData và returned messages.
- [Spring AMQP — Receiving Messages](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): listener container và acknowledgment modes.
- [Spring Framework — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): JMS listener, sessions và transaction semantics.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): deduplication và replay an toàn.
