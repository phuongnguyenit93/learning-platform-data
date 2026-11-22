# Transactional listener container

Trong Spring Kafka, listener container có thể quản lý Kafka transaction cho mỗi lần xử lý record hoặc batch. Container bắt đầu transaction trước khi gọi `@KafkaListener`; các lệnh gửi bằng `KafkaTemplate` trong listener tham gia transaction đó. Khi listener kết thúc thành công, container đưa offset đầu vào vào cùng transaction rồi commit. Nếu listener ném exception, transaction rollback và record có thể được đọc lại.

Cơ chế này giúp thực hiện luồng **read → process → write** nguyên tử trong Kafka: output record và offset input cùng commit hoặc cùng abort. Đây là nền tảng của Exactly Once Semantics (EOS) trong Spring Kafka. Để hoạt động đúng, producer factory phải hỗ trợ transaction, listener container phải được gắn `KafkaAwareTransactionManager`, và `KafkaTemplate` phải dùng cùng producer factory.

## 1. Transactional listener container là gì?

Listener container thông thường gọi listener và commit offset theo `AckMode`. Với transactional listener container, container mở Kafka transaction để bao bọc quá trình xử lý. Khi listener gửi output đến topic khác, output được ghi trong transaction hiện tại; offset của record đã đọc cũng được gửi vào transaction trước khi commit.

```text
Input topic
    |
    v
Kafka consumer poll
    |
    v
Listener container bắt đầu Kafka transaction
    |
    v
@KafkaListener xử lý record
    |
    +---- KafkaTemplate.send(output) ----> Output record trong transaction
    |
    v
Container gửi offset input vào transaction
    |
    v
COMMIT TRANSACTION
    |
    +---- Output được công bố
    +---- Offset input được commit
```

Nếu listener ném exception trước khi transaction commit:

```text
Listener ném exception
        |
        v
Kafka transaction ABORT
        |
        +---- Output của transaction không được công bố với read_committed
        |
        v
AfterRollbackProcessor xử lý vị trí consumer
        |
        v
Record được retry hoặc recovery
```

Container chịu trách nhiệm vòng đời transaction. Listener không cần tự gọi `beginTransaction()`, `commitTransaction()` hoặc `sendOffsetsToTransaction()`.

## 2. Các thành phần cần có

Một transactional listener container cần các thành phần sau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `DefaultKafkaProducerFactory` có `transactionIdPrefix` | Tạo và quản lý cache các transactional producer |
| `KafkaTransactionManager` | Bắt đầu, commit và rollback Kafka transaction |
| `ConcurrentKafkaListenerContainerFactory` | Gắn transaction manager vào listener container |
| `KafkaTemplate` dùng cùng producer factory | Gửi output tham gia transaction hiện tại |
| Kafka broker hỗ trợ transaction | Lưu transaction state và điều phối commit/abort |
| Consumer downstream `read_committed` | Chỉ đọc output thuộc transaction đã commit |

Chỉ đặt `EOSMode.V2` không đủ để biến listener thành transactional. Phải cấu hình transaction ID prefix trên producer factory và gắn transaction manager vào container.

## 3. Bật transaction với Spring Boot

Với Spring Boot, cách cấu hình ngắn gọn là đặt `spring.kafka.producer.transaction-id-prefix`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${INSTANCE_ID:local}-orders-tx-
    consumer:
      group-id: order-projection
      properties:
        "[isolation.level]": read_committed
```

Khi property `transaction-id-prefix` được đặt, Spring Boot cấu hình producer factory hỗ trợ transaction, tạo `KafkaTransactionManager` và gắn manager vào listener container factory auto-configured. `KafkaTemplate` được auto-configure cũng dùng producer factory đó, nên lệnh gửi trong listener có thể tham gia transaction của container.

`INSTANCE_ID` cần duy nhất cho mỗi instance ứng dụng chạy đồng thời, ví dụ Kubernetes pod name hoặc instance ID do nền tảng triển khai cấp. Giá trị `local` chỉ phù hợp khi chạy một instance local. Nếu nhiều instance dùng cùng prefix, transactional producer có thể fence lẫn nhau.

Nếu ứng dụng tự khai báo producer factory hoặc listener container factory, không nên giả định auto-configuration sẽ tự gắn manager vào factory tùy chỉnh. Hãy cấu hình tường minh như phần tiếp theo.

## 4. Cấu hình Java không dùng auto-configuration

Producer factory phải có transaction ID prefix. Ví dụ dưới đây minh họa các bean cốt lõi:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    public ProducerFactory<String, String> producerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);

        var factory = new DefaultKafkaProducerFactory<String, String>(properties);
        factory.setTransactionIdPrefix("orders-instance-a-tx-");
        return factory;
    }

    @Bean
    public KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

Trong production, prefix phải được cấp riêng cho từng instance thay vì hard-code cùng một giá trị. Cấu hình trên chỉ minh họa producer factory và transaction manager; ứng dụng còn cần `ConsumerFactory`, deserializer, bootstrap/security properties và listener container factory.

Gắn manager vào listener container factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, String> consumerFactory,
                KafkaTransactionManager<String, String> transactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(transactionManager);
    return factory;
}
```

Từ Spring Kafka 3.2, dùng `setKafkaAwareTransactionManager(...)`. API `setTransactionManager(...)` cũ đã deprecated. `KafkaAwareTransactionManager` là abstraction mà listener container cần để quản lý Kafka transaction.

## 5. KafkaTemplate phải dùng cùng ProducerFactory

Lệnh gửi chỉ tham gia transaction đang hoạt động khi `KafkaTemplate` dùng cùng `ProducerFactory` với `KafkaTransactionManager` của container. Spring Kafka dùng tài nguyên producer được bind vào thread xử lý listener.

Ví dụ:

```java
@Bean
public KafkaTemplate<String, String> kafkaTemplate(
        ProducerFactory<String, String> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

Khi container bắt đầu transaction, `KafkaTemplate` được tạo từ producer factory này sẽ lấy producer đang gắn với transaction hiện tại. Các lệnh `send()` được đưa vào transaction đó.

Nếu template dùng một producer factory khác, lệnh gửi có thể chạy trong transaction riêng hoặc không thuộc transaction của listener. Khi đó output và offset input không còn được commit nguyên tử như dự kiến.

Trong listener transactional, gọi `KafkaTemplate.send(...)` trực tiếp trên luồng xử lý của listener. Nếu chuyển việc gửi sang executor/thread khác, transaction context gắn với thread hiện tại không tự động truyền sang thread nền; thao tác gửi đó không mặc nhiên tham gia transaction của container.

## 6. Ví dụ read-process-write với transactional listener

Giả sử service đọc `orders.in`, tạo projection và gửi kết quả sang `orders.out`:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderProjectionListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.in",
            groupId = "order-projection",
            containerFactory = "kafkaListenerContainerFactory")
    public void process(ConsumerRecord<String, String> record) {
        String result = transform(record.value());

        kafkaTemplate.send(
                "orders.out",
                record.key(),
                result);
    }

    private String transform(String input) {
        return "projection:" + input;
    }
}
```

Khi `process` được gọi, container đã bắt đầu Kafka transaction. `KafkaTemplate.send` tham gia transaction hiện tại. Sau khi listener kết thúc bình thường, container gửi offset của record input vào transaction và commit.

Nếu `transform` hoặc logic listener ném exception, transaction rollback. Output đã gửi trong transaction đó không hiển thị với consumer `read_committed`; record input được xử lý lại theo chính sách rollback/retry.

Không cần tự gọi `KafkaTemplate.executeInTransaction(...)` bên trong listener container transactional. Lệnh gửi trực tiếp đã tham gia transaction của container. `executeInTransaction` tạo transaction cục bộ mới thay vì tham gia transaction đang tồn tại, nên có thể phá vỡ mục tiêu gom output và offset vào cùng transaction.

## 7. Transaction boundary với record listener và batch listener

Ranh giới transaction phụ thuộc kiểu listener:

| Loại listener | Ranh giới transaction |
| --- | --- |
| Record listener | Một transaction cho mỗi record được xử lý |
| Batch listener | Một transaction cho toàn bộ batch nhận từ một lần poll |

Với record listener, nếu một record thất bại, transaction của record đó rollback. Các record khác có thể được xử lý trong các transaction riêng theo tiến trình container.

Với batch listener, listener nhận một danh sách record. Nếu listener ném exception, transaction của batch rollback; batch có thể được giao lại theo chính sách after-rollback. Vì một phần batch có thể đã thực hiện side effect trước lỗi, logic batch cần idempotent hoặc dùng cơ chế transaction phù hợp cho hệ thống lưu trữ bên ngoài.

## 8. Offset input được commit trong Kafka transaction

Container tự đưa offset đã xử lý vào transaction bằng cơ chế Kafka consumer group metadata và `sendOffsetsToTransaction()`. Ứng dụng không cần gọi `consumer.commitSync()` hoặc tự gửi offset.

Khi transaction commit thành công:

- Output record được commit và có thể được consumer `read_committed` đọc.
- Offset input được commit trong cùng transaction.
- Consumer group tiếp tục từ vị trí kế tiếp.

Khi transaction abort:

- Output record của transaction không được công bố cho consumer `read_committed`.
- Offset input không được commit trong transaction đã abort.
- Consumer có thể đọc lại record theo vị trí được phục hồi.

Đây là điểm cốt lõi của EOS: không có trạng thái output đã commit nhưng offset input của cùng transaction chưa commit, hoặc ngược lại.

## 9. Consumer downstream cần read_committed

Kafka consumer có hai mức isolation chính:

| `isolation.level` | Hành vi |
| --- | --- |
| `read_uncommitted` | Có thể đọc record thuộc transaction chưa hoàn tất hoặc đã abort |
| `read_committed` | Chỉ trả record thuộc transaction đã commit |

Để downstream không nhìn thấy output của transaction bị rollback, cấu hình consumer:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

`read_committed` có thể làm consumer chờ qua vùng log chưa hoàn tất transaction (last stable offset), nên latency quan sát được có thể tăng khi có transaction mở lâu. Hãy giữ transaction ngắn và theo dõi transaction timeout.

## 10. EOS V2 và fencing

Spring Kafka hiện đại dùng `EOSMode.V2` làm cơ chế Exactly Once Semantics. V2 yêu cầu Kafka broker từ 2.5 trở lên và dùng consumer group metadata khi gửi offset vào transaction để broker kiểm tra producer còn hợp lệ hay đã bị fence.

Với Spring Kafka 3.0 trở lên, V2 là mode duy nhất được hỗ trợ. Trong các dòng Spring Kafka cũ, `V1` dùng cơ chế producer/fencing gắn với group/topic/partition; không nên dùng lại mode cũ trong ứng dụng hiện đại.

Fencing bảo vệ group khi partition được chuyển từ consumer cũ sang consumer mới. Producer cũ không thể tiếp tục hoàn tất transaction không còn hợp lệ sau khi broker đã fence producer đó.

Không nhầm fencing với idempotency nghiệp vụ. Listener có thể được gọi lại sau rollback; EOS bảo đảm output Kafka và offset input được commit nguyên tử, không bảo đảm phương thức Java chỉ chạy một lần.

## 11. Producer transactional ID và chạy nhiều instance

`transactionIdPrefix` được dùng để tạo `transactional.id` cho từng producer trong cache của factory. Prefix phải duy nhất giữa các application instance chạy đồng thời.

Ví dụ:

```text
orders-projection-pod-a-tx-0
orders-projection-pod-b-tx-0
orders-projection-pod-c-tx-0
```

Nếu hai instance dùng cùng prefix, chúng có thể tạo cùng transactional ID. Khi producer mới khởi tạo với ID đã được producer khác dùng, producer cũ có thể bị fence và nhận `ProducerFencedException`.

Các lưu ý vận hành:

- Tạo prefix từ application name cộng với instance ID duy nhất.
- Không dùng cùng prefix cố định cho mọi pod/replica.
- Khi scale deployment, bảo đảm mỗi instance được cấp prefix riêng.
- Theo dõi `ProducerFencedException`, transaction timeout và lỗi coordinator.
- Nếu producer có thể idle lâu hơn `transactional.id.expiration.ms` của broker, xem xét cấu hình `maxAge` của producer factory thấp hơn thời hạn broker để làm mới producer trước khi bị fence do hết hạn.

## 12. Retry và rollback: AfterRollbackProcessor

Với transactional listener, exception thoát khỏi listener làm Kafka transaction rollback. Cơ chế xử lý sau rollback được quản lý bởi `AfterRollbackProcessor`, thường dùng implementation `DefaultAfterRollbackProcessor`.

Luồng xử lý:

```text
Listener bắt đầu trong transaction
          |
          v
Xử lý thất bại, ném exception
          |
          v
Transaction rollback
          |
          v
DefaultAfterRollbackProcessor
          |
     +----+----------------+
     |                     |
     v                     v
  Seek/retry             Hết retry
     |                     |
     v                     v
Listener chạy lại       Recover/DLT
```

Không nên nuốt exception trong listener nếu muốn transaction rollback. Nếu listener bắt exception rồi trả về bình thường, container có thể xem lần xử lý là thành công và commit transaction.

`DefaultErrorHandler` thường được dùng cho listener không transactional. Với container transaction, cần thiết kế retry/recovery theo `AfterRollbackProcessor`; không áp dụng máy móc cấu hình blocking retry của non-transactional listener.

Sau số lần retry, có thể cấu hình recoverer để publish record sang DLT. Nếu muốn thao tác publish DLT và offset gốc được commit nguyên tử, cần cấu hình after-rollback processor với recovery trong transaction, chẳng hạn `commitRecovered=true` cùng `KafkaTemplate` transactional phù hợp theo API phiên bản Spring Kafka đang dùng.

## 13. Non-blocking retry không dùng với container transaction

`@RetryableTopic` triển khai non-blocking retry bằng cách publish record sang retry topic và để consumer xử lý sau. Cơ chế này không tương thích với container transactions.

Nếu listener cần EOS read-process-write, hãy dùng transaction rollback và blocking retry thông qua `AfterRollbackProcessor`. Nếu ưu tiên tách record lỗi khỏi main partition và chấp nhận ordering thay đổi, dùng retryable topics với listener không chạy container transaction.

Không kết hợp `@RetryableTopic` và transactional listener với kỳ vọng output, retry topic và input offset sẽ nằm trong một Kafka transaction duy nhất.

## 14. Transactional listener không tự bao trùm database

Kafka transaction chỉ quản lý thao tác Kafka. Nếu listener vừa cập nhật database vừa gửi output Kafka, hai hệ thống không tự động trở thành một distributed transaction nguyên tử.

Ví dụ có thể xảy ra:

1. Database transaction commit thành công.
2. Kafka transaction commit thất bại.
3. Input record được giao lại.
4. Database update có thể chạy lần nữa.

Hoặc theo thứ tự ngược lại, Kafka commit thành công nhưng database transaction thất bại. Vì vậy, không mô tả Kafka EOS là exactly-once cho cả database, HTTP service hoặc email.

Các cách xử lý phổ biến:

- Dùng transactional outbox để lưu business change và event trong cùng database transaction; publisher riêng gửi event lên Kafka.
- Dùng inbox/event ID và unique constraint để consumer xử lý lặp an toàn.
- Thiết kế thao tác nghiệp vụ idempotent.
- Dùng saga/compensation nếu quy trình trải qua nhiều hệ thống không có distributed transaction chung.

Spring có thể đồng bộ thứ tự commit giữa Kafka transaction manager và một transaction manager khác trong một số mô hình, nhưng đó không phải XA/distributed atomic commit. Cần xác định rõ transaction nào commit trước và xử lý cửa sổ lỗi giữa các hệ thống.

## 15. Transaction timeout và thời gian xử lý listener

Producer transaction có giới hạn thời gian. Thuộc tính `transaction.timeout.ms` đặt timeout transaction phía producer; broker có giới hạn tối đa `transaction.max.timeout.ms`.

Listener xử lý quá lâu có thể gặp transaction timeout, consumer vượt `max.poll.interval.ms`, rebalance hoặc producer bị fence. Cần kiểm soát:

- Thời gian xử lý record/batch ở percentile cao.
- Timeout database/HTTP được gọi trong listener.
- `transaction.timeout.ms` và giới hạn broker.
- `max.poll.interval.ms` và `max.poll.records`.
- Backoff/retry và thời gian transaction mở.
- Transaction coordinator và broker health.

Không tăng transaction timeout vô hạn để che giấu listener xử lý chậm. Tối ưu thao tác đồng bộ, giảm batch size hoặc tách công việc dài sang quy trình khác khi cần.

## 16. Cấu hình broker và quyền truy cập

Kafka transaction dùng transaction coordinator và topic nội bộ `__transaction_state`. Cluster production cần replication factor và min ISR phù hợp để lưu transaction state bền vững.

Một số cấu hình broker liên quan:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `transaction.state.log.replication.factor` | Replication factor của transaction state topic |
| `transaction.state.log.min.isr` | Số replica tối thiểu phải in-sync để chấp nhận ghi transaction state |
| `transaction.max.timeout.ms` | Giới hạn transaction timeout tối đa broker chấp nhận |

Với cluster một broker dùng để học tập, replication factor/min ISR có thể cần đặt bằng 1. Cấu hình đó không cung cấp độ bền và khả năng chịu lỗi tương đương cluster production nhiều broker.

Khi bật ACL, principal của producer cần quyền sử dụng transactional ID và ghi các topic đích; consumer cần quyền đọc topic input và tham gia group. Quyền cụ thể phụ thuộc cơ chế authorization của cluster. Hãy kiểm tra cả quyền transaction coordinator và quyền topic khi gặp `TransactionalIdAuthorizationException` hoặc lỗi authorization.

## 17. Quan sát transactional listener

Để xác định transaction hoạt động đúng, theo dõi:

- Số transaction commit/abort và tỷ lệ abort.
- Transaction duration và timeout.
- `ProducerFencedException`.
- Consumer lag và rebalance.
- Lỗi `AfterRollbackProcessor` và số lần retry.
- DLT publish/recovery failures.
- Listener processing time và downstream latency.

Khi điều tra một record, nên ghi topic, partition, offset, key, event ID/correlation ID và transaction outcome. Tránh log payload nhạy cảm.

## 18. Kiểm thử transactional listener container

Integration test cần xác minh cả output topic lẫn offset input. Chỉ kiểm tra listener method được gọi không đủ để chứng minh transaction atomicity.

Kịch bản commit thành công:

1. Tạo input topic và output topic trong broker kiểm thử.
2. Cấu hình producer factory có transaction ID prefix duy nhất.
3. Gắn `KafkaTransactionManager` vào listener container factory.
4. Gửi record vào input topic.
5. Listener gửi output bằng `KafkaTemplate` dùng cùng producer factory.
6. Xác nhận consumer `read_committed` nhận output và group offset input tiến lên.

Kịch bản rollback:

1. Gửi record khác vào input topic.
2. Listener gửi output rồi ném exception trước khi kết thúc.
3. Xác nhận output của transaction abort không xuất hiện với consumer `read_committed`.
4. Xác nhận record input được retry theo `AfterRollbackProcessor`.
5. Cho lần retry thành công và xác nhận output chỉ xuất hiện từ transaction commit.

Kiểm thử thêm nhiều application instance với prefix khác nhau, producer fencing, transaction timeout, DLT recovery và consumer restart trong lúc xử lý. Dùng latch/condition có timeout để chờ assignment, commit và redelivery; tránh sleep cố định ngắn.

## 19. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Listener không chạy trong transaction | Producer factory thiếu transaction ID prefix hoặc container chưa gắn manager | Kiểm tra `transactionIdPrefix` và `setKafkaAwareTransactionManager` |
| Output commit dù listener lỗi | Exception bị bắt và không truyền ra ngoài | Ném exception để container rollback |
| Output và input offset không nguyên tử | `KafkaTemplate` dùng producer factory khác | Dùng cùng producer factory với transaction manager |
| Downstream nhìn thấy output đã abort | Consumer dùng `read_uncommitted` | Đặt `isolation.level=read_committed` |
| `ProducerFencedException` | Transactional ID/prefix trùng giữa instance hoặc producer cũ bị fence | Cấp prefix duy nhất, xem xét producer maxAge |
| Transaction timeout | Listener xử lý quá lâu hoặc timeout cấu hình thấp | Đo processing time, tối ưu I/O và điều chỉnh timeout có giới hạn |
| Record retry không như mong đợi | Dùng sai cơ chế error handler cho transactional listener | Cấu hình `AfterRollbackProcessor` và để exception thoát listener |
| Non-blocking retry không hoạt động cùng transaction | `@RetryableTopic` không hỗ trợ container transaction | Chọn blocking rollback retry hoặc non-blocking retry không transaction |
| DB và Kafka lệch trạng thái | Kafka transaction không bao trùm database | Dùng outbox/inbox và idempotency |

## 20. Checklist trước khi triển khai

- [ ] Producer factory có `transactionIdPrefix`.
- [ ] Prefix duy nhất giữa các instance đang chạy đồng thời.
- [ ] `KafkaTransactionManager` dùng đúng producer factory.
- [ ] Listener container factory được gắn `KafkaAwareTransactionManager`.
- [ ] `KafkaTemplate` dùng cùng producer factory.
- [ ] Listener không nuốt exception cần rollback.
- [ ] Consumer downstream dùng `read_committed`.
- [ ] Retry/recovery được cấu hình bằng `AfterRollbackProcessor` phù hợp.
- [ ] Không kết hợp non-blocking retry topic với container transaction.
- [ ] Database và external side effect có outbox/inbox hoặc idempotency.
- [ ] Transaction timeout, poll interval và downstream timeout đã được kiểm tra.
- [ ] Broker transaction state topic, replication và ACL đã sẵn sàng.
- [ ] Có integration test chứng minh commit và rollback.

## 21. Kết luận

Transactional listener container của Spring Kafka mở Kafka transaction trước khi gọi listener. Các lệnh `KafkaTemplate` dùng cùng producer factory tham gia transaction; khi listener hoàn tất, container gửi offset input vào transaction rồi commit. Nếu listener ném exception, transaction rollback và `AfterRollbackProcessor` điều phối retry/recovery.

Để triển khai, cấu hình producer factory với transaction ID prefix duy nhất, tạo `KafkaTransactionManager`, gắn manager vào container bằng `setKafkaAwareTransactionManager(...)` và bảo đảm template dùng cùng producer factory. Consumer downstream cần `read_committed` để chỉ thấy output đã commit. Cơ chế này cung cấp EOS cho read-process-write giữa các topic Kafka; database và external side effect vẫn cần outbox/inbox hoặc idempotency riêng.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring for Apache Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Apache Kafka — Transactions](https://kafka.apache.org/documentation/#transactions)
