# Exactly-once semantics trong Kafka

Exactly-once semantics (EOS) trong Kafka là khả năng bảo đảm kết quả của một luồng xử lý Kafka được công bố đúng một lần về mặt trạng thái đã commit, dù producer hoặc consumer có thể retry, crash hay khởi động lại. Để đạt được điều này trong luồng consume-process-produce, Kafka cần kết hợp **idempotent producer**, **transaction** và **offset input được commit trong cùng transaction với output**.

EOS không có nghĩa phương thức Java chỉ được gọi đúng một lần. Listener có thể chạy lại sau rollback hoặc crash. Điều Kafka bảo đảm là output của lần xử lý chưa commit không được consumer `read_committed` nhìn thấy, còn output và offset của lần xử lý thành công được commit nguyên tử. Các tác động ngoài Kafka như database, HTTP, email hoặc file storage vẫn cần idempotency, inbox/outbox hoặc cơ chế phối hợp riêng.

## 1. Vì sao cần Exactly-once?

Giả sử một service đọc sự kiện từ `orders.in`, tính projection rồi gửi kết quả sang `orders.out`. Hai thao tác chính là:

1. Ghi kết quả vào topic output.
2. Commit offset của record input để consumer group biết đã xử lý đến đâu.

Nếu hai thao tác độc lập, crash có thể tạo ra hai trạng thái không nhất quán:

| Thời điểm crash | Hệ quả |
| --- | --- |
| Output đã ghi, offset chưa commit | Record input được đọc lại; output có thể bị ghi trùng |
| Offset đã commit, output chưa ghi | Consumer bỏ qua record input; output bị thiếu |

Kafka transaction cho phép đưa output record và offset input vào cùng một transaction. Broker chỉ công bố transaction khi commit thành công. Nếu transaction abort, cả output lẫn offset đều không được commit.

```text
orders.in
    |
    v
Consumer đọc record
    |
    v
Xử lý nghiệp vụ
    |
    +---- Gửi output vào orders.out
    |
    +---- Đưa offset input vào transaction
                    |
                    v
             Kafka transaction
                    |
              +-----+-----+
              |           |
           COMMIT        ABORT
              |           |
              v           v
       Output + offset   Không output/offset
       cùng có hiệu lực  nào được commit
```

## 2. Phân biệt at-most-once, at-least-once và exactly-once

| Semantics | Cách xử lý | Rủi ro chính |
| --- | --- | --- |
| At-most-once | Commit offset trước khi xử lý | Có thể mất tác vụ nếu crash sau commit |
| At-least-once | Xử lý trước rồi commit offset | Có thể xử lý lặp nếu crash trước commit |
| Exactly-once trong Kafka | Output và offset input cùng commit trong transaction | Listener vẫn có thể chạy lại; chỉ trạng thái Kafka được bảo đảm nguyên tử |

At-least-once kết hợp idempotency thường là lựa chọn phù hợp cho consumer cập nhật database. EOS phù hợp khi cần read-process-write giữa các topic Kafka và cần output/offset nhất quán trong cùng transaction.

Không nên dùng cụm từ “exactly-once delivery” theo nghĩa record chỉ được truyền qua mạng đúng một lần. Kafka có thể truyền lại request hoặc thực thi lại listener; EOS bảo đảm trạng thái cuối cùng đã commit theo semantics của transaction.

## 3. Idempotent producer

Producer có thể retry khi gửi record do lỗi mạng, broker tạm thời không khả dụng hoặc request timeout. Nếu broker đã ghi record nhưng phản hồi bị mất, producer có thể gửi lại request. Nếu không có cơ chế nhận diện retry, cùng một record có thể được ghi hai lần.

Kafka hỗ trợ idempotent producer bằng thuộc tính:

```properties
enable.idempotence=true
```

Broker cấp producer ID (PID) và producer dùng sequence number cho từng partition. Broker theo dõi sequence để nhận biết request gửi lại và loại bỏ bản ghi trùng do retry của cùng producer session.

```text
Producer (PID 42)
  Partition 0, sequence 10 ---> Broker ghi record
  Partition 0, sequence 10 ---> Broker nhận retry, nhận diện duplicate
                                Không ghi thêm bản sao
```

Idempotent producer bảo vệ việc gửi lại do retry ở Kafka producer. Nó không tự chống duplicate do ứng dụng chủ động gọi `send()` lần nữa với một event mới, ví dụ service nhận timeout rồi tạo một lần publish mới bằng producer khác.

Idempotence cũng không thay thế transaction. Nó không tự liên kết offset consumer với output record. Nếu consumer đọc một event rồi publish output, producer idempotent một mình vẫn chưa giải quyết cửa sổ crash giữa output và offset commit.

### Cấu hình idempotence

Có thể bật tường minh trong producer properties:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
```

Kafka producer hiện đại thường bật idempotence mặc định nếu không có cấu hình xung đột; khai báo rõ giúp thể hiện ý định. Khi bật idempotence, các điều kiện tương thích gồm `acks=all`, `retries` lớn hơn 0 và `max.in.flight.requests.per.connection` không vượt quá 5. Kafka client sẽ kiểm tra các điều kiện này khi khởi tạo producer.

## 4. Kafka transaction

Idempotent producer chống duplicate do retry trong phạm vi producer. Kafka transaction mở rộng khả năng này bằng cách gom nhiều thao tác ghi vào một đơn vị nguyên tử.

Một transaction có thể:

- Ghi nhiều record vào một hoặc nhiều topic.
- Ghi record vào nhiều partition.
- Đưa offset đã xử lý của consumer group vào cùng transaction.
- Commit tất cả thao tác hoặc abort tất cả thao tác.

Producer transaction cần có `transactional.id` ổn định. Broker dùng transaction coordinator để quản lý trạng thái transaction và producer epoch. Producer phải khởi tạo transaction trước khi gửi:

```java
producer.initTransactions();

producer.beginTransaction();
try {
    producer.send(new ProducerRecord<>("orders.out", key, output));
    producer.sendOffsetsToTransaction(offsets, consumer.groupMetadata());
    producer.commitTransaction();
}
catch (Exception exception) {
    producer.abortTransaction();
    throw exception;
}
```

Đây là pseudocode mô tả thứ tự thao tác, không phải vòng poll consumer hoàn chỉnh. Trong ứng dụng thực tế cần xử lý assignment/rebalance, loại exception, retry transaction và đóng producer/consumer đúng cách. Khi dùng Spring Kafka listener container, container tự quản lý transaction và offset; listener không cần gọi các API transaction này.

## 5. Consume-process-produce nguyên tử

Luồng EOS phổ biến nhất là consumer đọc record, ứng dụng xử lý rồi producer ghi kết quả sang topic khác. Offset input được đưa vào cùng transaction với output.

Ví dụ:

```text
Consumer group: order-projection
Input: orders.in, partition 2, offset 104
             |
             v
       Process order event
             |
             v
       Produce orders.out
             |
             v
       Add offset 105 for partition 2
             |
             v
       Commit transaction
```

Nếu transaction commit, record output có hiệu lực và group offset chuyển sang 105. Nếu transaction abort, output không được công bố với consumer `read_committed`, còn offset input không tiến lên theo transaction đó. Record input có thể được đọc lại.

Đây là ranh giới nguyên tử của Kafka EOS. Nó không có nghĩa phần xử lý CPU, gọi hàm Java hoặc log trong listener chỉ được thực hiện một lần. Những thao tác đó có thể chạy lại khi transaction rollback.

## 6. Producer ID, sequence number và producer epoch

Kafka dùng các định danh để nhận diện producer và kiểm soát transaction:

| Thành phần | Vai trò |
| --- | --- |
| Producer ID (PID) | Nhận diện producer ở phía broker |
| Sequence number | Nhận diện thứ tự batch record theo producer và partition, hỗ trợ phát hiện retry duplicate |
| `transactional.id` | Định danh logic của transactional producer qua các lần khởi tạo |
| Producer epoch | Phiên bản fencing của transactional producer; epoch mới vô hiệu hóa producer cũ dùng cùng transactional ID |
| Transaction coordinator | Quản lý trạng thái transaction và điều phối commit/abort |

Khi một producer mới khởi tạo với `transactional.id` đã được dùng trước đó, broker tăng epoch. Producer cũ có epoch thấp hơn bị fence và không thể tiếp tục hoàn tất transaction. Cơ chế này ngăn hai producer cùng ghi như một producer logic trong cùng thời điểm.

Với transactional producer, `transactional.id` cần ổn định cho cùng logical producer và duy nhất giữa các logical producer chạy đồng thời. Không tạo cùng ID cho các instance độc lập.

## 7. Consumer isolation.level

Consumer có thể đọc record thuộc transaction đang mở hoặc đã abort nếu dùng `read_uncommitted`. Để chỉ nhìn thấy output transaction đã commit, đặt:

```properties
isolation.level=read_committed
```

Trong Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

| Isolation level | Hành vi |
| --- | --- |
| `read_uncommitted` | Đọc cả record transactional chưa hoàn tất hoặc đã abort |
| `read_committed` | Chỉ trả record thuộc transaction đã commit |

Consumer `read_committed` chỉ đọc đến last stable offset (LSO), là ranh giới trước transaction đang mở sớm nhất trong partition. Nếu có transaction mở lâu, consumer có thể chờ dù phía sau đã có record khác. Vì vậy transaction cần ngắn và có timeout phù hợp.

Nếu topic input cũng được ghi bởi transactional producer và ứng dụng không muốn xử lý dữ liệu từ transaction bị abort, consumer đọc input cũng nên dùng `read_committed`.

## 8. Exactly-once trong Spring Kafka

Spring Kafka hỗ trợ EOS cho transactional listener container. Cần cấu hình producer factory với transaction ID prefix, tạo `KafkaTransactionManager` và gắn manager vào listener container. `KafkaTemplate` phải dùng cùng producer factory để lệnh gửi tham gia transaction đang hoạt động.

### Cấu hình bằng Spring Boot

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${INSTANCE_ID}-orders-tx-
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
```

Khi `spring.kafka.producer.transaction-id-prefix` được đặt, Spring Boot cấu hình transactional producer factory và `KafkaTransactionManager` cho cấu hình auto-configured. Listener container auto-configured dùng transaction manager; `KafkaTemplate` auto-configured cũng dùng producer factory tương ứng.

Với nhiều replica, `INSTANCE_ID` phải được cấp và khác nhau giữa các instance; nếu biến môi trường chưa được thiết lập, ứng dụng nên fail khi bind cấu hình thay vì âm thầm dùng chung một prefix mặc định. Không dùng cùng prefix cố định cho mọi pod. Spring Kafka listener container quản lý offset; `enable.auto.commit` cần là `false` và framework tự đặt `false` nếu không được khai báo.

### Cấu hình listener container bằng Java

Nếu tự tạo factory, gắn `KafkaAwareTransactionManager`:

```java
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

Producer factory phải được cấu hình transaction ID prefix trước đó. Từ Spring Kafka 3.2, dùng `setKafkaAwareTransactionManager(...)`; API `setTransactionManager(...)` cũ đã deprecated.

### Listener gửi output

```java
@Component
public class OrderProjectionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderProjectionListener(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.in",
            groupId = "order-projection",
            containerFactory = "kafkaListenerContainerFactory")
    public void onMessage(ConsumerRecord<String, String> record) {
        String output = "projection:" + record.value();
        kafkaTemplate.send("orders.out", record.key(), output);
    }
}
```

Container bắt đầu transaction trước khi gọi listener. Lệnh `KafkaTemplate.send()` tham gia transaction; khi listener hoàn tất, container gửi offset input vào transaction rồi commit. Nếu listener ném exception, transaction rollback và `AfterRollbackProcessor` điều phối retry/recovery.

## 9. EOS V2 và fencing trong Spring Kafka

Spring Kafka hiện đại dùng `EOSMode.V2`. V2 sử dụng consumer group metadata trong thao tác gửi offset vào transaction, cho phép broker fence producer cũ khi partition được chuyển sang consumer khác.

EOS V2 yêu cầu Kafka broker từ 2.5 trở lên. Từ Spring Kafka 3.0, V2 là mode duy nhất được hỗ trợ; các mode cũ V1/ALPHA/BETA không còn là lựa chọn trong ứng dụng hiện đại.

Trong V2, không cần tạo transactional producer riêng cho từng tổ hợp group/topic/partition như cách cũ. Producer factory có thể cache producer, nhưng transactional ID được tạo từ prefix và suffix do factory quản lý. Prefix vẫn phải duy nhất giữa các application instance chạy đồng thời.

Nếu producer bị idle lâu hơn `transactional.id.expiration.ms` của broker, có thể xem xét `maxAge` của `DefaultKafkaProducerFactory` thấp hơn thời hạn broker để factory làm mới producer trước khi nó bị fence do hết hạn.

## 10. Các tình huống lỗi và kết quả EOS

| Tình huống | Kết quả mong đợi với Kafka transaction |
| --- | --- |
| Producer gửi output rồi listener ném exception | Transaction abort; output không thấy bởi consumer `read_committed`; offset input chưa commit |
| Listener xử lý thành công, transaction commit | Output và offset input cùng có hiệu lực |
| Consumer crash khi transaction đang mở | Coordinator xử lý transaction chưa hoàn tất theo timeout/recovery; output chưa commit không được `read_committed` hiển thị |
| Producer gửi lại batch do lỗi mạng trong cùng producer session | Idempotent producer nhận diện sequence và tránh ghi duplicate do retry |
| Producer mới khởi tạo cùng transactional ID | Producer epoch mới fence producer cũ |
| Ứng dụng gửi lại cùng event như một lần publish mới | Có thể tạo record mới; cần event ID/idempotency nếu muốn loại duplicate nghiệp vụ |
| Database commit nhưng Kafka transaction abort | Database không tự rollback; cần inbox/outbox hoặc idempotency |

EOS xử lý atomicity của trạng thái Kafka, không che giấu mọi lỗi ở tầng ứng dụng. Cần thiết kế retry và side effect theo đúng ranh giới transaction.

## 11. Exactly-once không bao trùm database hoặc external service

Kafka transaction không tự tạo distributed transaction giữa Kafka và database quan hệ, REST API, email provider hoặc file system.

Ví dụ listener cập nhật database rồi gửi Kafka:

1. Database commit thành công.
2. Kafka transaction thất bại.
3. Kafka input record được đọc lại.
4. Database update có thể chạy lần nữa.

Nếu listener gửi Kafka trước rồi gọi database, tình huống ngược lại cũng có thể xảy ra. Kafka transaction không thể rollback một HTTP request đã được dịch vụ khác xử lý hoặc một email đã gửi.

Các chiến lược thường dùng:

- **Transactional outbox:** lưu business update và event vào cùng database transaction; publisher riêng gửi outbox event lên Kafka.
- **Inbox/deduplication:** lưu `eventId` với unique constraint cùng transaction database để event giao lại không tạo side effect lần nữa.
- **Idempotent API:** gửi idempotency key tới downstream để cùng một yêu cầu không tạo nhiều kết quả.
- **Saga/compensation:** thiết kế hành động bù trừ khi quy trình trải qua nhiều hệ thống độc lập.

Với nhiều ứng dụng, at-least-once + idempotent business operation thường đơn giản hơn việc cố mở rộng khái niệm EOS ra ngoài Kafka.

## 12. Exactly-once và idempotency ở tầng nghiệp vụ

Idempotency nghĩa là thực hiện cùng một event nhiều lần vẫn tạo ra kết quả nghiệp vụ tương đương một lần. Ví dụ dùng event ID:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Trong một database transaction:

```java
@Transactional
public void processOnce(OrderCreatedEvent event) {
    boolean firstDelivery = processedEventRepository
            .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderRepository.createProjection(event);
}
```

`insertIfAbsent` phải được triển khai bằng unique constraint hoặc câu lệnh insert/upsert nguyên tử. Không chỉ `SELECT` rồi `INSERT`, vì hai consumer có thể chạy đồng thời và cùng thấy event chưa tồn tại.

Ghi dấu event và cập nhật nghiệp vụ phải nằm trong cùng database transaction. Sau đó listener mới commit offset Kafka. Nếu crash sau database commit nhưng trước offset commit, record được giao lại nhưng event ID đã tồn tại nên business update không lặp.

## 13. Transactional ID và cấu hình broker

Kafka transaction dùng transaction coordinator và topic nội bộ `__transaction_state`. Cluster cần cấu hình replication và min ISR phù hợp để transaction state có độ bền.

Một số cấu hình broker liên quan:

| Property | Ý nghĩa |
| --- | --- |
| `transaction.state.log.replication.factor` | Replication factor của transaction state topic |
| `transaction.state.log.min.isr` | Số replica tối thiểu phải in-sync để chấp nhận ghi transaction state |
| `transaction.max.timeout.ms` | Giới hạn transaction timeout tối đa broker chấp nhận |

Producer có `transaction.timeout.ms`; giá trị phải không vượt giới hạn broker. Với cluster một broker dùng để học tập, replication factor và min ISR có thể cần đặt bằng 1, nhưng cấu hình đó không cung cấp độ bền tương đương cluster production.

Khi bật ACL, producer cần quyền sử dụng transactional ID và ghi topic đích. Consumer cần quyền đọc input topic và tham gia consumer group. Lỗi `TransactionalIdAuthorizationException` thường yêu cầu kiểm tra quyền transactional ID; lỗi topic/group cần kiểm tra quyền tương ứng.

## 14. Giới hạn của transaction và throughput

Transaction tạo thêm round trip với coordinator và yêu cầu commit/abort. Transaction quá dài có thể làm tăng latency, giữ last stable offset ở vị trí cũ và khiến consumer `read_committed` chờ.

Các điểm cần kiểm soát:

- Giữ transaction ngắn, chỉ bao gồm công việc cần atomicity.
- Không thực hiện HTTP/database call chậm trong transaction nếu có thể tách ra.
- Chọn `transaction.timeout.ms` phù hợp với thời gian xử lý cao nhất có thể dự đoán.
- Theo dõi transaction commit/abort rate và transaction duration.
- Tránh mở nhiều transaction nhỏ không cần thiết trong một luồng producer-only.
- Đánh giá throughput/latency trước và sau khi bật transaction.

Không tăng timeout vô hạn để che giấu listener bị treo. Nếu nghiệp vụ xử lý lâu, cân nhắc chia nhỏ công việc hoặc dùng workflow/outbox phù hợp.

## 15. Khi nào cần EOS và khi nào at-least-once là đủ?

| Use case | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Consume Kafka, transform và publish sang Kafka; output và offset phải nguyên tử | Kafka transaction + EOS | Hai thao tác cùng commit/abort |
| Producer retry có thể ghi trùng do lỗi mạng | Idempotent producer | Deduplicate retry của cùng producer |
| Consumer chỉ cập nhật database | At-least-once + inbox/idempotency | Database không nằm trong Kafka transaction |
| Gửi event từ database sau khi cập nhật dữ liệu | Transactional outbox | Đồng bộ business data và event trong database |
| Gửi email hoặc gọi REST API | Idempotency key/outbox/compensation | Kafka không rollback external side effect |
| Chỉ gửi nhiều record Kafka cần atomic visibility | Producer transaction | Commit/abort nhóm output mà không nhất thiết có input offset |
| Luồng không cần atomicity và ưu tiên latency đơn giản | At-least-once hoặc at-most-once theo yêu cầu | Giảm chi phí và độ phức tạp transaction |

Chỉ bật EOS khi yêu cầu nghiệp vụ cần atomic read-process-write trong Kafka. Nếu consumer chỉ ghi database, EOS không tự giải quyết được vấn đề quan trọng nhất là đồng bộ database với offset.

## 16. Kiểm thử Exactly-once

Kiểm thử EOS cần xác minh những gì consumer downstream nhìn thấy và trạng thái offset input, không chỉ kiểm tra listener được gọi.

### Kịch bản commit thành công

1. Tạo input topic và output topic trong broker kiểm thử.
2. Cấu hình producer factory với transaction ID prefix duy nhất.
3. Gắn `KafkaTransactionManager` vào listener container.
4. Gửi một record vào input topic.
5. Listener gửi output bằng `KafkaTemplate` dùng cùng producer factory.
6. Consumer `read_committed` nhận đúng một output đã commit.
7. Xác minh group offset input đã tiến lên.

### Kịch bản rollback

1. Gửi record khác vào input topic.
2. Listener gửi output rồi ném exception trước khi transaction hoàn tất.
3. Xác nhận consumer `read_committed` không nhìn thấy output thuộc transaction abort.
4. Xác nhận input record được retry theo `AfterRollbackProcessor`.
5. Cho lần xử lý sau thành công và xác nhận output chỉ xuất hiện từ transaction commit.

### Kịch bản producer retry và fencing

- Mô phỏng retry gửi record và xác nhận idempotent producer không tạo duplicate do retry trong cùng producer session.
- Khởi tạo producer mới với cùng transactional ID để kiểm tra producer cũ bị fence.
- Chạy nhiều application instance với prefix khác nhau để xác minh không tranh chấp transactional ID.

### Kịch bản external side effect

- Cho database commit thành công rồi mô phỏng Kafka offset chưa commit.
- Xác nhận record được giao lại.
- Xác nhận inbox/event ID ngăn database update lặp.

Dùng Embedded Kafka hoặc broker kiểm thử, `CountDownLatch`, `BlockingQueue` hoặc Awaitility để chờ transaction và offset với timeout. Tránh chỉ dùng `Thread.sleep` ngắn để kết luận transaction đã commit hoặc abort.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Producer retry vẫn tạo duplicate | Idempotence tắt hoặc ứng dụng gửi lại như một publish mới | Bật idempotence; dùng event ID để deduplicate ở nghiệp vụ |
| Output commit nhưng offset input chưa commit | Output và offset không nằm trong cùng transaction | Dùng transactional listener/container hoặc `sendOffsetsToTransaction` |
| Offset commit nhưng output thiếu | Commit hai thao tác độc lập hoặc dùng sai transaction boundary | Đưa output và offset vào cùng transaction |
| Consumer thấy record thuộc transaction abort | Consumer dùng `read_uncommitted` | Đặt `isolation.level=read_committed` |
| `ProducerFencedException` | Trùng transactional ID hoặc producer cũ bị epoch mới fence | Dùng transactional ID/prefix duy nhất theo logical instance |
| Transaction timeout | Listener xử lý lâu hoặc timeout không phù hợp | Giảm thời gian transaction và điều chỉnh timeout có giới hạn |
| EOS không bảo vệ database | Database nằm ngoài Kafka transaction | Dùng outbox/inbox và idempotency |
| Listener vẫn chạy nhiều lần | Rollback, redelivery hoặc crash trước offset commit | Thiết kế listener idempotent; EOS bảo đảm trạng thái Kafka chứ không bảo đảm một lần gọi code |
| `read_committed` bị chậm | Transaction mở lâu làm LSO không tiến | Tìm transaction treo, giảm thời gian xử lý và theo dõi coordinator |

## 18. Checklist triển khai

- [ ] Producer dùng idempotence; các producer properties tương thích.
- [ ] Luồng read-process-write dùng Kafka transaction.
- [ ] Offset input được đưa vào cùng transaction với output.
- [ ] Transactional ID ổn định cho logical producer và duy nhất giữa instance chạy đồng thời.
- [ ] `KafkaTemplate` dùng cùng `ProducerFactory` với transaction manager.
- [ ] Listener container được gắn `KafkaAwareTransactionManager`.
- [ ] Consumer cần dữ liệu transactional dùng `read_committed`.
- [ ] Listener truyền exception để rollback khi xử lý thất bại.
- [ ] Retry/recovery của transactional listener dùng `AfterRollbackProcessor` phù hợp.
- [ ] Database và external side effect có outbox/inbox hoặc idempotency.
- [ ] Transaction timeout, broker transaction state log và ACL đã được kiểm tra.
- [ ] Có integration test cho commit, abort, retry, fencing và redelivery.

## 19. Kết luận

Exactly-once semantics trong Kafka dựa trên hai cơ chế phối hợp: idempotent producer loại bỏ duplicate do retry của cùng producer, còn Kafka transaction gom output và offset input vào một đơn vị commit/abort nguyên tử. Consumer `read_committed` chỉ nhìn thấy output đã commit. Trong Spring Kafka, transactional listener container quản lý transaction, gửi offset input vào transaction và dùng `KafkaTemplate` cùng producer factory để gửi output.

EOS bảo đảm trạng thái Kafka của luồng read-process-write, không bảo đảm listener chỉ chạy một lần và không tự bao trùm database hay external service. Hãy dùng transactional ID/prefix đúng cách, giữ transaction ngắn, cấu hình `read_committed`, thiết kế side effect idempotent và kiểm thử các tình huống crash/rollback. Với nhiều nghiệp vụ, at-least-once kết hợp inbox/outbox có thể đơn giản và phù hợp hơn việc cố mở rộng EOS ra ngoài Kafka.

## Tài liệu tham khảo

- [Apache Kafka — Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics)
- [Apache Kafka — Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka — Transactions](https://kafka.apache.org/documentation/#transactions)
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
