# Checklist transaction và idempotency

Kafka giúp truyền event bền vững, nhưng một luồng messaging tin cậy còn phải trả lời hai câu hỏi: **khi nào một nhóm thao tác được xem là hoàn tất cùng nhau** và **điều gì xảy ra nếu cùng một event được giao nhiều lần**. Kafka transaction có thể phối hợp việc consume record, publish record mới và commit offset trong một Kafka transaction. Idempotency giúp nghiệp vụ chịu được duplicate do retry, crash, rebalance hoặc replay.

Hai cơ chế này bổ trợ nhau nhưng không giống nhau. Producer idempotence chống duplicate do producer retry trong một phiên producer; Kafka transaction tạo ranh giới atomic cho các thao tác Kafka; business idempotency ngăn side effect bị áp dụng lặp. Không cơ chế nào tự làm cho một database update, HTTP call hoặc payment API trở thành exactly-once.

Bài này là checklist thiết kế và vận hành cho Spring Kafka. Dùng nó khi review producer, consumer, retry/DLT, transaction, database integration và quy trình replay trước khi đưa luồng event lên production.

## 1. Phân biệt các cơ chế bảo đảm

| Cơ chế | Bảo vệ điều gì? | Giới hạn |
| --- | --- | --- |
| Producer idempotence | Broker không ghi duplicate do producer retry trong cùng producer session/sequence | Không ngăn ứng dụng chủ động gửi cùng business event nhiều lần |
| Kafka transaction | Nhiều thao tác Kafka được commit hoặc abort cùng nhau | Không tự bao gồm database, HTTP hoặc hệ thống ngoài Kafka |
| Consumer offset commit | Lưu vị trí consumer group đã xử lý đến đâu | Có thể redeliver nếu side effect xong nhưng offset chưa commit |
| Business idempotency | Cùng event/request ID không áp dụng side effect nghiệp vụ nhiều lần | Cần lưu key và kết quả đủ lâu, xử lý race condition đúng |
| Inbox pattern | Ghi nhận event đã xử lý cùng transaction database với business update | Chỉ bảo vệ các side effect nằm trong cùng DB transaction |
| Outbox pattern | Lưu business change và ý định publish event trong cùng DB transaction | Relay/CDC vẫn có thể phát lại; consumer vẫn nên idempotent |
| Saga/compensation | Điều phối và bù trừ workflow qua nhiều hệ thống | Không phải transaction ACID phân tán |

Hãy xác định yêu cầu thực tế trước khi chọn cơ chế: cần không mất event, không xử lý nghiệp vụ trùng, không phát output khi input bị abort, hay cần phối hợp nhiều hệ thống? Mỗi yêu cầu có ranh giới bảo đảm khác nhau.

## 2. Xác định ranh giới transaction

Trước khi cấu hình Spring Kafka, vẽ rõ các thao tác thuộc một luồng:

```text
Producer service
  1. Tạo event
  2. Publish Kafka record

Consumer service
  3. Consume input record
  4. Cập nhật database
  5. Publish output/event tiếp theo
  6. Commit input offset
```

Đánh dấu từng thao tác thuộc Kafka, database hay external system. Kafka transaction chỉ điều phối các thao tác Kafka được tham gia vào transaction đó. Nếu bước 4 là JDBC commit độc lập, Kafka không thể tự rollback database khi bước 5 thất bại.

**Checklist ranh giới:**

- [ ] Đã xác định transaction bắt đầu ở producer hay listener container.
- [ ] Đã liệt kê mọi side effect trong luồng: Kafka, database, HTTP, payment, email, file hoặc cache.
- [ ] Đã xác định thao tác nào thật sự nằm trong cùng một Kafka transaction.
- [ ] Đã xác định database transaction có ranh giới riêng hay dùng outbox/inbox.
- [ ] Đã quyết định hành vi khi process crash giữa hai side effect.
- [ ] Đã xác định thao tác nào có thể được retry hoặc redeliver.
- [ ] Đã định nghĩa thế nào là event được xử lý thành công ở góc nhìn nghiệp vụ.

## 3. Producer: idempotence và cấu hình gửi

Kafka producer idempotence dùng producer ID và sequence number để broker nhận biết retry của cùng batch, tránh ghi duplicate do lỗi mạng hoặc retry ở tầng producer. Cơ chế này là nền tảng hữu ích cho độ tin cậy khi publish.

Với Kafka client hiện đại, idempotence thường được bật mặc định trong các cấu hình tương thích; vẫn nên xác minh cấu hình hiệu lực của ứng dụng và broker/client version. Cấu hình minh họa:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
```

`acks=all` yêu cầu broker chờ các replica trong ISR xác nhận theo semantics của Kafka; replication factor, `min.insync.replicas` và ISR health cũng phải được thiết kế phù hợp. Idempotence có các ràng buộc tương thích giữa `acks`, retries và `max.in.flight.requests.per.connection`; không tự thay đổi các giá trị này độc lập mà không kiểm tra client version.

**Checklist producer:**

- [ ] Producer idempotence được bật hoặc đã xác minh default của Kafka client đang dùng.
- [ ] `acks` và `min.insync.replicas` đáp ứng durability mong muốn.
- [ ] Retry, delivery timeout và request timeout có giá trị phù hợp với SLA.
- [ ] `max.in.flight.requests.per.connection` tương thích với idempotence và yêu cầu ordering.
- [ ] Key/partition strategy được xác định để giữ ordering cho cùng aggregate khi cần.
- [ ] Callback/future send failure được xử lý và ghi nhận, không bỏ qua.
- [ ] Business event có `eventId` ổn định được tạo một lần trước khi publish/retry.
- [ ] Producer không tạo event ID mới mỗi khi gửi lại cùng một business action.
- [ ] Schema, serializer và headers được kiểm tra trước khi gửi production.

Producer idempotence không thay thế business event ID. Nếu code gọi `send()` hai lần cho cùng một event, broker có thể nhận hai record hợp lệ vì đó là hai lần gửi ở cấp ứng dụng.

## 4. Kafka transaction trong Spring Kafka

Kafka transaction cho phép publish nhiều record và commit consumer offsets trong cùng transaction. Nếu transaction abort, output record không được hiển thị cho consumer `read_committed`, và offset tham gia transaction không được commit như một phần của transaction đó.

Trong Spring Boot, cấu hình `transaction-id-prefix` để Spring Kafka tạo transactional producer:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${INSTANCE_ID:orders-1}-tx-
      properties:
        enable.idempotence: true
    consumer:
      properties:
        isolation.level: read_committed
```

`transaction-id-prefix` phải duy nhất giữa các application instance đang hoạt động. Nếu hai instance dùng cùng prefix và tạo transactional ID trùng nhau, broker có thể fence producer cũ. Dùng pod/instance identity ổn định trong vòng đời instance và kiểm tra cách cấp prefix khi scale/restart.

Spring Boot có thể auto-configure transactional `ProducerFactory` khi có `spring.kafka.producer.transaction-id-prefix`. Nếu tự tạo `ProducerFactory`, hãy xác minh transaction ID prefix và cấu hình transaction được áp dụng cho factory đó.

Tạo `KafkaTransactionManager` từ đúng `ProducerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory
    ) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

Spring Boot có thể đã tạo bean `KafkaTransactionManager` khi transaction prefix được cấu hình. Chỉ khai báo bean thủ công nếu ứng dụng cần custom manager hoặc auto-configuration chưa cung cấp bean tương ứng; tránh tạo hai manager cùng quản lý một `ProducerFactory` mà không có chủ đích.

Với listener container, gắn Kafka-aware transaction manager vào container properties:

```java
factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTransactionManager);
```

Khi container quản lý Kafka transaction, listener có thể publish output bằng `KafkaTemplate` tham gia transaction đang hoạt động. Offset của input record được gửi vào transaction để commit cùng output.

Với producer service chủ động gửi một nhóm record trong transaction, có thể dùng transaction manager bằng qualifier:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(OrderEvent event) {
        kafkaTemplate.send("orders.events", event.orderId(), event);
        kafkaTemplate.send("orders.audit", event.orderId(), event.toAuditEvent());
    }
}
```

Hai lần gửi tham gia cùng Kafka transaction đang gắn với thread. Nếu method ném exception làm transaction rollback, cả hai output được abort. Đây là transaction Kafka; nếu method cũng cập nhật database bằng một transaction manager khác thì cần áp dụng phân tích dual-write/outbox ở phần sau.

**Checklist Kafka transaction:**

- [ ] ProducerFactory thực sự là transactional producer factory.
- [ ] `transaction-id-prefix` duy nhất giữa các instance đang chạy.
- [ ] Listener container dùng đúng `KafkaTransactionManager` nếu cần consume-process-produce atomic trong Kafka.
- [ ] `KafkaTemplate` được tạo từ ProducerFactory tương ứng để tham gia transaction.
- [ ] Consumer downstream dùng `isolation.level=read_committed` nếu không được phép thấy output đã abort.
- [ ] Transaction timeout đủ cho xử lý bình thường nhưng không dài quá mức.
- [ ] Listener không thực hiện công việc blocking quá lâu bên trong transaction.
- [ ] Exception cần rollback không bị bắt rồi nuốt mất.
- [ ] Có chính sách xử lý lỗi sau rollback và DLT/recovery tương ứng.
- [ ] Có metric/log cho transaction commit, abort, timeout và producer fencing.

## 5. Exactly-once semantics: bảo đảm đến đâu?

Kafka exactly-once semantics (EOS) thường nói đến việc phối hợp consume-process-produce trong Kafka: input offsets và output records được commit trong cùng Kafka transaction. Điều này tránh trường hợp output đã được commit nhưng input offset chưa commit, hoặc ngược lại, trong luồng Kafka-to-Kafka được cấu hình đúng.

EOS không có nghĩa business method chỉ được gọi đúng một lần. Listener có thể được gọi lại sau crash hoặc rollback; side effect ngoài Kafka vẫn cần idempotency.

Ví dụ:

```text
Input topic -> listener -> Output topic
                  |
                  +-- Kafka transaction:
                      - publish output record
                      - commit input offset
```

Nếu transaction abort, output không hiển thị với `read_committed` consumer và input offset không được commit trong transaction đó. Record input có thể được giao lại để xử lý lần nữa.

**Checklist EOS:**

- [ ] Phạm vi exactly-once được mô tả cụ thể là Kafka-to-Kafka.
- [ ] Producer transaction và listener container transaction được cấu hình đúng.
- [ ] Input offset tham gia cùng transaction với output.
- [ ] Downstream consumer dùng `read_committed` khi cần ẩn aborted output.
- [ ] Business side effect bên ngoài Kafka có idempotency hoặc outbox/inbox riêng.
- [ ] Không quảng cáo “exactly once toàn hệ thống” chỉ vì đã bật Kafka transaction.

## 6. Consumer offset và ranh giới xử lý

Với xử lý thông thường, consumer group commit offset sau khi listener xử lý thành công theo `AckMode` và container semantics. Nếu database commit thành công nhưng process chết trước khi offset commit, record có thể được giao lại. Nếu offset commit trước khi database commit, process chết có thể làm mất cơ hội xử lý lại record.

```text
DB commit -> process crash -> Kafka offset chưa commit
                         -> record được giao lại
                         -> business operation có nguy cơ chạy lần hai
```

Đây là lý do consumer cần idempotency khi có side effect ngoài Kafka.

**Checklist consumer:**

- [ ] `enable.auto.commit` và Spring Kafka `AckMode` được chọn có chủ đích.
- [ ] Offset chỉ được xác nhận sau ranh giới xử lý đã định nghĩa.
- [ ] Listener exception không bị nuốt nếu cần container rollback/retry.
- [ ] Manual acknowledgment chỉ gọi sau khi side effect hoàn tất.
- [ ] Có xử lý duplicate do crash giữa business commit và offset commit.
- [ ] Có kiểm tra behavior khi rebalance hoặc shutdown giữa lúc xử lý.
- [ ] Batch listener có chính sách partial failure/acknowledgment rõ ràng.
- [ ] Async handoff không commit offset trước khi công việc thực sự hoàn tất.

Với Kafka transactional listener, offset có thể được gửi vào Kafka transaction. Với database listener thông thường, DB commit và Kafka offset commit vẫn là hai hệ thống commit riêng nếu không có giải pháp phối hợp bổ sung.

## 7. Idempotency key cho event và command

Mỗi event/command có side effect cần một định danh ổn định. Có thể dùng `eventId`, `commandId` hoặc `requestId` do producer tạo trước khi gửi. Định danh đó phải giữ nguyên qua producer retry, consumer redelivery và DLT replay.

Ví dụ event envelope:

```java
public record OrderPaid(
        String eventId,
        String orderId,
        String paymentId,
        long occurredAt
) {}
```

`eventId` định danh một event cụ thể; `orderId` định danh aggregate; `paymentId` có thể định danh thao tác thanh toán ở hệ thống payment. Không tự dùng một trường thay thế cho tất cả mục đích nếu semantics không giống nhau.

**Checklist idempotency key:**

- [ ] ID được tạo tại nguồn nghiệp vụ trước lần publish đầu tiên.
- [ ] ID không đổi khi producer retry hoặc republish cùng event.
- [ ] ID có namespace/loại event nếu nhiều nguồn có thể tạo ID trùng.
- [ ] Consumer xác định rõ phạm vi unique: toàn hệ thống, tenant, event type hay consumer.
- [ ] ID được lưu đủ lâu so với retention, retry, DLT và replay window.
- [ ] Replay có thể giữ event ID gốc để deduplicate.
- [ ] Không dùng Kafka offset làm business idempotency key vì offset chỉ duy nhất trong một partition/topic.

## 8. Inbox/deduplication table trong database

Với consumer cập nhật database, inbox pattern lưu dấu event đã xử lý và business update trong cùng database transaction. Nếu event được giao lại, unique constraint trên event ID giúp phát hiện duplicate.

Ví dụ schema:

```sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Ví dụ service:

```java
@Transactional
public void handle(OrderPaid event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
            "billing-projection",
            event.eventId()
    );

    if (!firstDelivery) {
        return; // Event đã được áp dụng trong consumer này.
    }

    invoiceRepository.markPaid(event.orderId(), event.paymentId());
}
```

`insertIfAbsent` phải dựa trên unique constraint hoặc câu lệnh upsert nguyên tử phù hợp database. Không thực hiện `SELECT` rồi `INSERT` tách rời mà không xử lý race condition: hai consumer thread có thể cùng thấy event chưa tồn tại.

Inbox row và business update phải nằm trong cùng DB transaction. Nếu business update rollback, inbox insert cũng rollback; lần giao tiếp theo có thể xử lý lại. Nếu transaction commit, lần giao lại sẽ thấy inbox row và bỏ qua side effect trùng.

**Checklist inbox:**

- [ ] Unique constraint bảo vệ `(consumer_name, event_id)` hoặc khóa tương đương.
- [ ] Insert inbox và business update ở cùng DB transaction.
- [ ] Duplicate path trả về thành công để offset có thể tiếp tục commit.
- [ ] Race condition giữa các consumer được database constraint giải quyết.
- [ ] Có chiến lược retention/cleanup không xóa key còn trong retry/replay window.
- [ ] Có metric đếm duplicate bị bỏ qua.
- [ ] Consumer name/handler version được quản lý để các projection độc lập không dùng chung dedup namespace sai mục đích.

## 9. Outbox pattern cho database-to-Kafka

Một service thường cần cập nhật database và publish event tương ứng. Nếu commit DB trước rồi publish thất bại, dữ liệu đã đổi nhưng event không được phát. Nếu publish trước rồi DB rollback, event có thể mô tả một thay đổi chưa tồn tại.

Outbox giải quyết dual-write bằng cách lưu business change và outbox row trong cùng DB transaction:

```text
BEGIN DB TRANSACTION
  UPDATE orders ...
  INSERT INTO outbox(event_id, aggregate_id, event_type, payload, ...)
COMMIT

Outbox relay / CDC -> Kafka topic
```

Ví dụ schema đơn giản:

```sql
CREATE TABLE outbox_events (
    event_id VARCHAR(160) PRIMARY KEY,
    aggregate_id VARCHAR(160) NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
```

Relay có thể polling bảng outbox hoặc dùng CDC như Debezium. Nếu relay publish thành công nhưng chết trước khi đánh dấu row đã gửi, cùng event có thể được publish lại. Consumer vẫn phải idempotent bằng event ID.

**Checklist outbox:**

- [ ] Business update và outbox insert nằm trong cùng DB transaction.
- [ ] Outbox event có ID ổn định, aggregate ID, event type, schema version và timestamp.
- [ ] Relay/CDC có retry và quan sát backlog.
- [ ] Relay xử lý nhiều worker có cơ chế claim/locking phù hợp.
- [ ] Publish lặp được chấp nhận và consumer deduplicate.
- [ ] Có retention/cleanup sau khi event đã được phát và không còn cần replay từ outbox.
- [ ] Có cảnh báo khi outbox backlog tăng hoặc event cũ chưa publish quá SLA.

Outbox bảo đảm ý định publish được lưu bền vững cùng business update; nó không biến toàn bộ hệ thống thành một transaction distributed duy nhất.

## 10. Kết hợp Kafka transaction với database

Spring có thể phối hợp nhiều transaction manager theo thứ tự hoặc qua transaction synchronization, nhưng điều đó không tự tạo một distributed atomic commit giữa Kafka và relational database. Một transaction manager có thể commit trước; nếu transaction manager còn lại commit thất bại, hai hệ thống có thể lệch trạng thái.

Khi listener vừa cập nhật database vừa publish Kafka, cần trả lời:

- Database commit trước hay Kafka commit trước?
- Nếu commit thứ hai thất bại, thao tác đầu tiên có rollback được không?
- Listener redelivery có thể lặp DB update hoặc output không?
- Có outbox/inbox để khôi phục không?

Với nghiệp vụ quan trọng, outbox/inbox thường dễ vận hành và kiểm chứng hơn việc giả định hai local transaction manager tạo ra XA transaction. Chỉ dùng XA/JTA khi hạ tầng, driver, broker và yêu cầu vận hành hỗ trợ rõ ràng và team hiểu chi phí của distributed transaction.

| Kiểu luồng | Hướng thiết kế thường phù hợp |
| --- | --- |
| Kafka input → Kafka output | Kafka transaction + consume-process-produce EOS |
| Kafka input → database update | Inbox/dedup trong cùng DB transaction, offset commit sau listener thành công |
| Database update → Kafka output | Transactional outbox + relay/CDC |
| Kafka input → external API | Downstream idempotency key, query/reconciliation và compensation khi cần |
| Kafka input → database + Kafka output | Inbox cho input và outbox cho output; xác định rõ transaction DB và offset Kafka |

## 11. Idempotency cho external API và side effect

Nếu listener gọi payment gateway, gửi email hoặc gọi HTTP service khác, DB inbox không thể tự rollback side effect bên ngoài. Có thể dùng idempotency key mà downstream API hỗ trợ:

```text
POST /payments
Idempotency-Key: payment-command-8f...
```

Downstream lưu key và kết quả, trả lại cùng kết quả khi nhận lại request. Nếu downstream không hỗ trợ idempotency, cần thiết kế workflow trạng thái, reconciliation hoặc compensation; không thể đảm bảo exactly-once chỉ bằng Kafka offset.

**Checklist external side effects:**

- [ ] Mỗi command có idempotency key ổn định.
- [ ] Downstream API nhận và lưu key nếu có hỗ trợ.
- [ ] Timeout không bị hiểu nhầm là thao tác chắc chắn thất bại.
- [ ] Có cách query trạng thái khi kết quả call không xác định.
- [ ] Email/notification có deduplication hoặc chấp nhận duplicate được mô tả.
- [ ] Side effect không thể rollback có bước compensation/reconciliation.
- [ ] Không retry mù một lệnh thanh toán khi chưa xác định trạng thái lần gọi trước.

## 12. Retry, DLT và replay

Retry có thể làm một record được xử lý nhiều lần. Blocking retry, non-blocking retry topic và DLT có semantics khác nhau về ordering, offset và thời điểm xử lý. Dù chọn cách nào, business handler vẫn nên idempotent.

Checklist retry/DLT:

- [ ] Phân loại lỗi transient, permanent và validation.
- [ ] Chỉ retry lỗi có khả năng thành công ở lần sau.
- [ ] Giới hạn attempts và backoff; tránh retry vô hạn.
- [ ] Xác định blocking hay non-blocking retry và chấp nhận trade-off ordering.
- [ ] DLT giữ event ID, original topic/partition/offset, exception metadata và trace headers cần thiết.
- [ ] Có cảnh báo khi DLT nhận record hoặc backlog tăng.
- [ ] Có quy trình phân tích và phê duyệt replay.
- [ ] Replay giữ event ID gốc nếu đó là cùng business event.
- [ ] Consumer idempotency vẫn hoạt động khi replay.
- [ ] Không xóa DLT record trước khi xác nhận recovery hoàn tất.

Replay có thể là lần đầu một consumer projection mới nhìn thấy event hoặc là lần xử lý lại event cũ. Cần xác định dedup namespace và policy tương ứng; không xóa inbox table một cách tùy tiện trước replay.

## 13. Ordering và concurrency

Kafka chỉ bảo đảm thứ tự trong một partition. Nếu các event của cùng aggregate cần xử lý theo thứ tự, dùng aggregate ID làm key để chúng đi vào cùng partition.

Khi tăng consumer concurrency, số consumer hữu ích trong một group bị giới hạn bởi partition assignment. Nếu listener dispatch record sang thread pool và xử lý song song, thứ tự hoàn tất nghiệp vụ có thể khác thứ tự Kafka giao record.

Checklist ordering/concurrency:

- [ ] Chọn message key theo aggregate cần giữ thứ tự.
- [ ] Các event liên quan dùng cùng topic/partitioning strategy.
- [ ] Concurrency không vượt quá năng lực partition và downstream.
- [ ] Async processing không commit offset trước khi side effect hoàn tất.
- [ ] Nếu xử lý song song, có sequence/version check ở aggregate khi cần.
- [ ] Retry/DLT không tạo ra ordering guarantee mà hệ thống không thực sự có.
- [ ] Duplicate và out-of-order event có policy rõ ràng.

## 14. Event contract và schema evolution

Idempotency chỉ hoạt động nếu event identity và contract ổn định. Event nên có envelope thống nhất, chẳng hạn:

```json
{
  "eventId": "evt-01J...",
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "aggregateId": "order-123",
  "occurredAt": "2026-11-17T10:15:30Z",
  "correlationId": "request-456",
  "payload": {
    "paymentId": "pay-789"
  }
}
```

Checklist contract:

- [ ] `eventId` duy nhất và ổn định.
- [ ] Có event type và schema version.
- [ ] Có aggregate key phù hợp ordering.
- [ ] Timestamp dùng chuẩn rõ ràng, ưu tiên UTC.
- [ ] Correlation ID và trace context có mục đích riêng.
- [ ] Consumer tương thích schema cũ/mới theo compatibility policy.
- [ ] Không dùng payload mutable để tính idempotency key sau khi event đã phát.

## 15. Security và quyền transaction

Transactional producer dùng transactional ID và cần ACL phù hợp trên cluster. Consumer cần quyền đọc topic và group; producer cần quyền ghi topic. Quyền transaction resource phụ thuộc cơ chế authorization và Kafka version/cluster configuration.

Checklist security:

- [ ] Producer/consumer dùng TLS hoặc SASL theo policy cluster.
- [ ] Principal chỉ có quyền cần thiết trên topic/group/transactional ID.
- [ ] Transactional ID prefix không dùng chung tùy tiện giữa ứng dụng khác nhau.
- [ ] Secret và credential không nằm trong source hoặc log.
- [ ] Event payload không chứa dữ liệu nhạy cảm không cần thiết.
- [ ] DLT và outbox/inbox table có access control và retention phù hợp.
- [ ] Replay tool có audit trail và quyền hạn chế.

## 16. Kiểm thử transaction và idempotency

Unit test kiểm tra logic deduplication và xử lý duplicate; integration test cần broker thật hoặc môi trường Kafka tương đương để kiểm tra transaction, offset và isolation semantics.

**Kịch bản bắt buộc nên có:**

1. Publish một record thành công với idempotent producer.
2. Producer retry sau lỗi mạng và xác minh không tạo duplicate do retry nội bộ.
3. Listener consume input, publish output trong transaction và commit thành công.
4. Ném exception trước commit và xác minh transaction abort.
5. Dùng `read_committed` consumer để xác minh aborted output không hiển thị.
6. Gửi cùng event ID hai lần và xác minh business side effect chỉ áp dụng một lần.
7. Gửi đồng thời hai bản cùng event ID để kiểm tra unique constraint/race handling.
8. Crash sau DB commit nhưng trước Kafka offset commit và xác minh inbox ngăn side effect lặp.
9. Outbox relay publish thành công rồi restart trước khi đánh dấu published; xác minh consumer deduplicate.
10. Retry hết attempts và đưa record vào DLT.
11. Replay DLT với event ID gốc và xác minh behavior đúng policy.
12. Gửi event ngoài thứ tự và xác minh aggregate version/sequence guard nếu có.
13. Restart/rebalance consumer trong lúc xử lý để kiểm tra offset và duplicate behavior.
14. Kiểm tra transactional ID fencing khi hai instance vô tình dùng prefix trùng trong môi trường test riêng.

Không chỉ assert listener được gọi. Cần kiểm tra trạng thái database, committed offset, output topic visibility và số lần side effect. Dùng Testcontainers hoặc Embedded Kafka tương thích version để test broker behavior; tránh `Thread.sleep()` cố định, dùng Awaitility/latch và timeout có giới hạn.

## 17. Failure drill trước production

Thực hiện các bài diễn tập có kiểm soát trong staging:

| Failure drill | Kết quả mong đợi |
| --- | --- |
| Kill producer sau khi gửi nhưng trước khi caller nhận ack | Caller xử lý kết quả không xác định; event ID ổn định giúp retry an toàn |
| Kill consumer sau DB commit, trước offset commit | Record có thể redeliver; inbox ngăn side effect trùng |
| Abort Kafka transaction sau khi tạo output | `read_committed` consumer không thấy output bị abort |
| Mất kết nối broker trong transaction | Transaction timeout/abort được ghi nhận; listener retry theo policy |
| Restart một instance transactional | Instance mới có transactional ID hợp lệ; producer cũ bị fence nếu ID bị chiếm |
| Outbox relay dừng lâu | Backlog tăng, alert phát hiện; relay tiếp tục từ outbox bền vững |
| DLT replay cùng event ID | Dedup policy ngăn duplicate business update không mong muốn |
| Downstream HTTP timeout sau khi đã xử lý | Query/idempotency key giúp xác định kết quả trước khi retry |

Chỉ chạy failure drill khi có môi trường và dữ liệu test được phép. Ghi lại metric, log, offset và DB state để xác minh recovery chứ không chỉ kiểm tra process tự khởi động lại.

## 18. Metrics và alert cần có

Theo dõi các chỉ số sau để phát hiện transaction/idempotency đang có vấn đề:

| Metric/log | Mục đích |
| --- | --- |
| Transaction commit/abort rate | Phát hiện rollback tăng bất thường |
| Transaction duration/timeout | Phát hiện transaction giữ quá lâu |
| Producer send failure/retry | Theo dõi publish reliability |
| Producer fencing count/error | Phát hiện transactional ID conflict |
| Consumer redelivery/retry count | Đo mức độ xử lý lại |
| Idempotency duplicate hit | Theo dõi duplicate event được deduplicate |
| Inbox insert conflict | Phát hiện delivery trùng hoặc replay |
| Outbox pending count/oldest age | Phát hiện event chưa được relay |
| Consumer lag | Phát hiện backlog |
| DLT publish rate/backlog | Theo dõi record không xử lý được |
| Replay count và operator identity | Audit thao tác recovery |

Alert nên dựa trên xu hướng và SLA: transaction abort kéo dài, fencing xuất hiện, outbox oldest age vượt ngưỡng, DLT backlog tăng hoặc consumer lag không giảm. Không alert chỉ vì một transaction abort đơn lẻ nếu đó là rollback dự kiến do validation/business exception.

## 19. Vận hành dữ liệu idempotency

Inbox/processed-message table có thể tăng liên tục. Cần chính sách lưu trữ phù hợp với khả năng event được gửi lại hoặc replay.

Checklist retention:

- [ ] Retention dài hơn cửa sổ retry tối đa.
- [ ] Retention dài hơn DLT replay window được cam kết.
- [ ] Có cân nhắc thời gian producer/outbox có thể phát lại.
- [ ] Cleanup theo batch để tránh lock/IO spike.
- [ ] Không xóa key đang được replay hoặc còn cần reconciliation.
- [ ] Có index/partitioning phù hợp để truy vấn duplicate không làm chậm hot path.
- [ ] Có backup/restore policy cho inbox/outbox và business data.

Nếu hệ thống cần replay event lịch sử nhiều năm, lưu idempotency key chỉ vài ngày sẽ không bảo vệ được replay. Khi đó cần xác định replay semantics: tạo projection mới với namespace riêng, hoặc giữ dedup key đủ lâu để tránh lặp side effect.

## 20. Go-live checklist tổng hợp

### Thiết kế và semantics

- [ ] Đã xác định delivery semantics mong muốn cho từng luồng.
- [ ] Đã phân biệt producer idempotence, Kafka transaction và business idempotency.
- [ ] Đã xác định ranh giới Kafka/DB/external side effect.
- [ ] Đã định nghĩa event ID, correlation ID, aggregate key và schema version.
- [ ] Đã xác định ordering, concurrency, retry và replay policy.

### Producer và Kafka transaction

- [ ] Idempotent producer, `acks` và replication policy được kiểm tra.
- [ ] Transaction ID prefix duy nhất giữa các instance.
- [ ] Listener container và KafkaTemplate dùng đúng transactional ProducerFactory.
- [ ] Input offset và output records tham gia cùng Kafka transaction khi yêu cầu EOS.
- [ ] Consumer downstream dùng `read_committed` nếu cần ẩn aborted output.

### Database và side effect

- [ ] Consumer có inbox/unique constraint nếu DB side effect phải idempotent.
- [ ] Outbox được dùng khi DB update và Kafka publish phải có ý định commit bền vững cùng nhau.
- [ ] External API có idempotency key hoặc workflow reconciliation.
- [ ] DB commit và Kafka offset commit không bị giả định là atomic.

### Reliability và recovery

- [ ] Retry/DLT attempts, backoff và exception classification rõ ràng.
- [ ] Replay giữ event ID gốc hoặc dùng namespace mới theo policy.
- [ ] Consumer xử lý duplicate và out-of-order event an toàn.
- [ ] Shutdown/rebalance/crash đã được kiểm thử.
- [ ] Failure drill xác minh trạng thái cuối cùng ở Kafka và database.

### Security và operations

- [ ] ACL, TLS/SASL, transactional ID và secret được bảo vệ.
- [ ] Inbox/outbox retention, backup và cleanup có kế hoạch.
- [ ] Metrics transaction, retry, duplicate, outbox, DLT và lag có dashboard/alert.
- [ ] Replay tool có audit trail và quyền giới hạn.
- [ ] Runbook mô tả cách xử lý fencing, abort, duplicate, backlog và DLT.

Một luồng Kafka đáng tin cậy không đến từ một cờ cấu hình duy nhất. Producer idempotence xử lý retry ở tầng producer; Kafka transaction phối hợp output và offset trong Kafka; inbox/outbox và business idempotency bảo vệ ranh giới database; downstream idempotency/reconciliation bảo vệ side effect bên ngoài. Hãy kiểm thử các điểm crash và replay thực tế, rồi dùng checklist này như điều kiện go-live và tài liệu review định kỳ.

## 21. Tự kiểm tra

1. Producer idempotence khác business idempotency như thế nào?
2. Kafka transaction có thể bảo đảm atomic cho những thao tác nào?
3. Vì sao Kafka EOS không làm database update trở thành exactly-once?
4. `transaction-id-prefix` cần duy nhất ở phạm vi nào và lỗi gì xảy ra nếu trùng?
5. Vì sao downstream consumer nên dùng `read_committed` khi đọc transactional output?
6. Crash sau DB commit nhưng trước offset commit gây ra tình huống gì?
7. Inbox pattern cần unique constraint và DB transaction như thế nào?
8. Outbox giải quyết dual-write ra sao và tại sao relay vẫn có thể publish duplicate?
9. Vì sao external payment/email side effect cần idempotency key riêng?
10. DLT replay nên giữ event ID gốc trong trường hợp nào?
11. Cần failure drill nào để chứng minh offset, transaction và idempotency hoạt động đúng?
12. Những metrics nào giúp phát hiện transactional ID fencing, duplicate và outbox backlog?
