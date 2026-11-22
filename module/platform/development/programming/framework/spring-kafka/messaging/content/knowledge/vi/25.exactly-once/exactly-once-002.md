# Phân biệt at-most-once, at-least-once và exactly-once

Khi consumer đọc một Kafka record, ứng dụng phải quyết định thời điểm xác nhận offset so với thời điểm hoàn tất xử lý. Nếu xác nhận quá sớm, process có thể dừng và làm mất cơ hội xử lý record. Nếu xác nhận quá muộn, process có thể dừng sau khi tạo side effect nhưng trước khi offset được lưu, khiến record được giao lại và side effect có thể lặp.

Ba delivery semantics mô tả cách hệ thống cân bằng giữa hai rủi ro đó:

- **At-most-once**: một record được xử lý không quá một lần; có thể mất record nếu lỗi xảy ra sau khi offset đã được xác nhận.
- **At-least-once**: record không bị bỏ qua do xác nhận sớm; đổi lại có thể được xử lý nhiều lần khi commit thất bại hoặc consumer khởi động lại.
- **Exactly-once**: kết quả nghiệp vụ trong phạm vi được bảo vệ chỉ được ghi nhận một lần về mặt hiệu lực. Với Kafka, bảo đảm mạnh nhất áp dụng cho pipeline consume-transform-produce khi output và input offset được commit trong cùng Kafka transaction.

Bài học thuộc chương **Exactly-once** của module **SPRING_KAFKA_MESSAGING**, tập trung vào thời điểm commit offset, failure window, cách cấu hình Spring Kafka và giới hạn của exactly-once khi listener tạo tác động bên ngoài Kafka.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích khác biệt giữa at-most-once, at-least-once và exactly-once.
- Vẽ được failure window giữa xử lý record và commit offset.
- Dự đoán khi nào record bị mất và khi nào record có thể được giao lại.
- Chọn AckMode phù hợp trong Spring Kafka.
- Hiểu vai trò của `enable.auto.commit=false` và thời điểm acknowledgment.
- Phân biệt idempotent producer với exactly-once processing.
- Cấu hình transactional listener để commit output và input offset nguyên tử.
- Hiểu `isolation.level=read_committed`.
- Thiết kế idempotency cho database và side effect bên ngoài.
- Xác định chính xác phạm vi bảo đảm và kiểm thử từng semantics.

## 1. Delivery semantics nói về điều gì?

Delivery semantics mô tả quan hệ giữa việc nhận một message, thực hiện xử lý và xác nhận tiến độ. Trong bài này, trọng tâm là phía consumer: record có thể được giao lại bao nhiêu lần và ứng dụng có thể tạo ra kết quả nào khi process, broker hoặc network gặp lỗi.

Một Kafka consumer đọc record theo offset của từng partition. Offset được commit là vị trí tiếp theo consumer muốn đọc, không phải offset của record cuối vừa xử lý.

Ví dụ:

| Record vừa xử lý | Offset được commit |
|---:|---:|
| 40 | 41 |
| 41 | 42 |
| 42 | 43 |

Consumer group lưu offset riêng cho từng partition. Khi consumer khởi động lại hoặc partition được giao cho member khác, consumer tiếp tục từ offset đã commit theo chính sách reset và dữ liệu còn trong retention.

Câu hỏi cốt lõi của ba semantics là: **offset được xác nhận trước hay sau khi xử lý hoàn tất, và làm thế nào để kết quả xử lý cùng offset có tính nguyên tử?**

## 2. At-most-once: xác nhận trước, xử lý sau

At-most-once ưu tiên tránh xử lý trùng. Consumer xác nhận offset trước khi thực hiện side effect. Nếu process dừng sau commit nhưng trước khi xử lý xong, Kafka coi record đã được tiêu thụ và sẽ không tự giao lại record đó cho group.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant K as Kafka
    participant S as Business service
    C->>K: Poll record offset 40
    C->>K: Commit next offset 41
    K-->>C: Commit acknowledged
    C->>S: Process record 40
    Note over C,S: Process crashes before completion
    Note over K: Restart continues from offset 41
~~~

Ưu điểm:

- Tránh việc consumer tự xử lý lại record chỉ vì commit offset thất bại sau side effect.
- Hữu ích khi duplicate gây hậu quả lớn và chấp nhận mất một số record trong failure window.
- Luồng xử lý đơn giản nếu nghiệp vụ cho phép bỏ qua record khi process gặp sự cố.

Nhược điểm:

- Có thể mất record nếu consumer dừng sau khi commit offset nhưng trước khi hoàn tất xử lý.
- Không phù hợp với nghiệp vụ cần bảo đảm mọi sự kiện đều được xử lý.
- Không bảo đảm side effect bên ngoài đã hoàn tất; offset có thể tiến dù database hoặc HTTP call chưa chạy.

At-most-once có nghĩa một record được giao cho logic xử lý không quá một lần theo tiến độ đã xác nhận. Nó không có nghĩa listener chắc chắn được gọi một lần: record có thể không được xử lý lần nào.

## 3. Cấu hình at-most-once trong Spring Kafka

Để minh họa at-most-once với listener record, có thể dùng manual acknowledgment và xác nhận ngay trước khi chạy nghiệp vụ. Consumer auto commit cần tắt để container không tự commit theo một lịch độc lập.

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
~~~

Listener:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-at-most-once"
)
public void consume(
        OrderCreatedEvent event,
        Acknowledgment acknowledgment) {

    // Commit offset trước khi tạo side effect.
    acknowledgment.acknowledge();

    orderService.handle(event);
}
~~~

Với `AckMode.MANUAL_IMMEDIATE`, acknowledgment được gọi trên consumer thread sẽ yêu cầu commit ngay. Nếu process dừng sau dòng acknowledge nhưng trước hoặc trong `orderService.handle`, record có thể không được giao lại.

Cách này chỉ minh họa semantics at-most-once. Hãy dùng khi nghiệp vụ chấp nhận khả năng mất record. Không gọi acknowledgment trước khi dispatch một tác vụ bất đồng bộ rồi giả định tác vụ đó chắc chắn hoàn tất.

## 4. At-least-once: xử lý trước, xác nhận sau

At-least-once ưu tiên không mất record do commit sớm. Consumer chỉ xác nhận offset sau khi listener xử lý thành công. Nếu process dừng sau side effect nhưng trước khi offset commit, Kafka có thể giao lại record.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant S as Business service
    participant K as Kafka
    C->>K: Poll record offset 40
    C->>S: Process record 40
    S-->>C: Processing succeeded
    C->>K: Commit next offset 41
    K-->>C: Commit acknowledged
~~~

Nếu process dừng sau khi xử lý thành công nhưng trước commit:

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant S as Business service
    participant K as Kafka
    C->>K: Poll record offset 40
    C->>S: Process record 40
    S-->>C: Side effect completed
    Note over C,K: Process crashes before offset commit
    C->>K: Restart and poll from committed offset 40
    K-->>C: Record 40 is delivered again
    C->>S: Process record 40 again
~~~

Ưu điểm:

- Record chưa được xác nhận có thể được giao lại sau crash hoặc rebalance.
- Phù hợp với nghiệp vụ cần ưu tiên không bỏ sót sự kiện.
- Là lựa chọn phổ biến cho consumer xử lý đơn hàng, thanh toán, tồn kho và audit.

Nhược điểm:

- Listener có thể xử lý cùng record nhiều lần.
- Side effect không idempotent có thể bị lặp.
- Cần thiết kế deduplication hoặc idempotency ở ranh giới nghiệp vụ.

At-least-once là semantics phổ biến khi consumer xử lý record rồi mới commit offset. Đây thường là điểm khởi đầu phù hợp cho ứng dụng Spring Kafka.

## 5. Cấu hình at-least-once trong Spring Kafka

Tắt auto commit và để listener container commit sau khi xử lý thành công. Có thể chọn `RECORD` để commit sau từng record hoặc `BATCH` để commit sau khi xử lý thành công các record của poll.

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

Ví dụ listener:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment"
)
public void consume(OrderCreatedEvent event) {
    orderService.handle(event);
}
~~~

Với `AckMode.RECORD`, container commit offset sau khi listener xử lý record thành công. Nếu listener ném exception, error handler quyết định retry hoặc recovery; offset không được coi là đã xử lý thành công chỉ vì listener đã được gọi.

Với `AckMode.BATCH`, container commit offset cho các record của poll sau khi batch được xử lý thành công theo semantics của container. Cả hai cách đều có thể tạo at-least-once khi commit xảy ra sau xử lý và auto commit đã tắt.

Không nên bật `enable.auto.commit=true` rồi đồng thời giả định AckMode quyết định toàn bộ thời điểm commit. Auto commit có thể tiến offset độc lập với việc xử lý nghiệp vụ.

## 6. Exactly-once: output và offset cùng commit

Exactly-once trong Kafka consume-transform-produce được xây dựng bằng transaction. Consumer đọc input, producer gửi output, sau đó offset input được thêm vào cùng transaction. Kafka commit hoặc abort toàn bộ đơn vị đó.

~~~mermaid
flowchart TD
    A[Consume input record] --> B[Transform]
    B --> C[Begin Kafka transaction]
    C --> D[Produce output record]
    D --> E[Add input offset to transaction]
    E --> F{Commit transaction}
    F -->|Commit| G[Output visible and input offset advances]
    F -->|Abort| H[Output is aborted and input offset stays]
    H --> I[Input can be redelivered]
~~~

Kết quả:

- Commit thành công: output được công bố và input offset tiến cùng transaction.
- Abort: output của transaction không hiển thị với consumer `read_committed`, input offset không được commit trong transaction đó và record có thể được giao lại.
- Consumer downstream dùng `read_committed` để chỉ đọc output của transaction đã commit.

Exactly-once không có nghĩa phương thức listener chỉ được gọi đúng một lần. Listener có thể chạy lại sau abort hoặc crash. Điều được bảo đảm là kết quả Kafka đã commit không bị nhân đôi bởi failure window giữa output và input offset trong pipeline được cấu hình đúng.

## 7. So sánh ba semantics

| Tiêu chí | At-most-once | At-least-once | Exactly-once trong Kafka |
|---|---|---|---|
| Thời điểm xác nhận | Trước xử lý | Sau xử lý thành công | Cùng transaction với output |
| Có thể mất record do crash | Có | Không do commit sớm, nếu retention và recovery đáp ứng | Không do lệch giữa output và offset trong transaction |
| Có thể xử lý lặp | Thông thường tránh redelivery sau commit | Có | Listener vẫn có thể chạy lại, nhưng output Kafka transaction đã commit không bị lặp do failure window |
| Cơ chế chính | Commit trước side effect | Process rồi commit | Transactional producer + offset trong transaction |
| Độ phức tạp | Thấp | Trung bình; cần idempotency | Cao hơn; cần transaction và isolation phù hợp |
| Phù hợp | Có thể chấp nhận mất record | Cần xử lý không bỏ sót, chấp nhận dedupe | Kafka consume-transform-produce cần atomicity |

Có thể nhớ bằng thứ tự:

- At-most-once: **commit → process**.
- At-least-once: **process → commit**.
- Exactly-once: **process + output + offset trong cùng transaction**.

## 8. Failure window quyết định semantics

Hãy xét consumer đọc record offset 40 và tạo một thay đổi nghiệp vụ.

| Thời điểm process dừng | At-most-once | At-least-once | Exactly-once Kafka |
|---|---|---|---|
| Trước khi xử lý | Nếu offset chưa commit, record có thể được đọc lại; nếu đã commit thì có thể mất | Offset chưa commit nên record có thể được đọc lại | Transaction chưa commit; input có thể được giao lại |
| Sau side effect nhưng trước commit | Offset đã commit trước đó; record không được giao lại dù side effect có thể chưa xong hoặc đã xong | Record được giao lại; side effect có thể lặp | Nếu side effect là output Kafka trong transaction chưa commit, output bị abort cùng offset |
| Sau commit | Record không được giao lại theo offset đã lưu | Record không được giao lại theo offset đã lưu | Output và input offset cùng được commit |
| Commit response bị mất | Có thể không biết commit đã thành công hay chưa; cần kiểm tra offset | Có thể bị redelivery nếu commit chưa được lưu | Transaction protocol xác định trạng thái; ứng dụng cần xử lý kết quả commit theo Kafka client |

Bảng này giả định consumer group, offset và transaction được cấu hình đúng, đồng thời loại trừ việc retention xóa record trước khi consumer phục hồi.

Điểm quan trọng: exactly-once Kafka chỉ đóng failure window cho các thao tác nằm trong transaction Kafka. Nếu listener cập nhật database ngoài transaction rồi transaction Kafka abort, database vẫn có thể đã thay đổi.

## 9. Producer idempotence không đồng nghĩa exactly-once

Producer idempotence giúp Kafka loại bỏ duplicate do producer retry cùng request theo protocol, dùng producer ID và sequence number.

~~~properties
enable.idempotence=true
acks=all
~~~

Cơ chế này không tự bảo đảm:

- Một nghiệp vụ không bị ứng dụng gửi lại từ một process mới.
- Consumer không xử lý lại record sau crash.
- Output và input offset được commit nguyên tử.
- Database hoặc HTTP side effect không bị lặp.

| Cơ chế | Bảo đảm chính |
|---|---|
| Idempotent producer | Giảm duplicate do retry ở tầng producer protocol. |
| Consumer idempotency | Một event ID không tạo side effect nghiệp vụ lặp. |
| Kafka transaction | Atomicity giữa nhiều output record và offset input trong Kafka. |
| Outbox/inbox | Phối hợp bền vững giữa database và việc phát/nhận event. |

Một ứng dụng có thể dùng idempotent producer mà vẫn vận hành at-least-once ở consumer. Để có exactly-once Kafka consume-transform-produce, cần transaction bao gồm output và offset input.

## 10. Cấu hình transactional producer trong Spring Boot

Spring Boot có thể cấu hình transaction ID prefix cho producer:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${HOSTNAME:orders-service}-tx-
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Transaction ID prefix phải duy nhất giữa các application instance chạy đồng thời. Trong Kubernetes, có thể dùng pod name hoặc instance ID duy nhất. Nếu mọi pod dùng cùng một prefix không có suffix phân biệt, producer có thể fence lẫn nhau.

Khi transaction được cấu hình, Spring Kafka có thể tạo ProducerFactory hỗ trợ transaction và KafkaTransactionManager theo cơ chế auto-configuration của phiên bản Spring Boot tương ứng.

`read_committed` ở consumer bảo đảm downstream chỉ nhận record thuộc transaction đã commit. Consumer `read_uncommitted` có thể nhìn thấy record thuộc transaction chưa commit hoặc đã abort, làm mất ý nghĩa visibility mà pipeline exactly-once hướng tới.

## 11. Cấu hình transactional listener container

Với consume-transform-produce, listener container bắt đầu transaction trước khi gọi listener. KafkaTemplate gửi output tham gia transaction đó. Khi listener hoàn tất, container đưa offset input vào transaction rồi commit.

Ví dụ cấu hình khái quát:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
transactionalListenerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
        KafkaTransactionManager<String, Object> transactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(transactionManager);

    return factory;
}
~~~

Listener:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        containerFactory = "transactionalListenerFactory"
)
public void process(OrderCreatedEvent event) {
    OrderAcceptedEvent output = fulfillmentService.accept(event);

    kafkaTemplate.send(
            "orders.accepted",
            event.orderId(),
            output
    );
}
~~~

Cần bảo đảm KafkaTemplate dùng cùng transactional ProducerFactory phù hợp với transaction của container. Nếu listener gửi bằng một producer độc lập không tham gia transaction, output có thể commit riêng trong khi offset input rollback.

Tên setter và cách khai báo transaction manager phụ thuộc phiên bản Spring Kafka. Dùng API tương thích với dependency của dự án; sau đó kiểm thử cả commit và rollback.

## 12. Transaction rollback và redelivery

Nếu listener ném exception trước khi transaction commit, container rollback transaction. Output record đã gửi trong transaction bị abort; offset input không được commit trong transaction đó.

Spring Kafka dùng `DefaultAfterRollbackProcessor` để quyết định việc redeliver, retry hoặc recover record sau rollback. Đây là cơ chế cần xem xét cho transactional listener; không áp dụng máy móc cấu hình `DefaultErrorHandler` của luồng non-transactional.

Một listener vẫn có thể được gọi nhiều lần:

~~~text
Attempt 1:
  read input -> produce output -> exception -> abort

Attempt 2:
  read input again -> produce output -> success -> commit
~~~

Output của attempt 1 không được consumer `read_committed` nhìn thấy. Output của attempt 2 được công bố cùng offset input. Đó là cách exactly-once Kafka bảo vệ kết quả cuối cùng, dù code xử lý có thể chạy nhiều lần.

Nếu listener tạo side effect ngoài Kafka trước khi ném exception, side effect đó không được rollback cùng Kafka transaction. Hãy dùng idempotency hoặc outbox/inbox cho phần đó.

## 13. Exactly-once với Kafka Streams

Nếu ứng dụng dùng Kafka Streams thay vì listener thủ công, có thể cấu hình processing guarantee:

~~~properties
processing.guarantee=exactly_once_v2
~~~

Kafka Streams quản lý transaction cho việc đọc input, ghi output và cập nhật state store/changelog theo semantics của framework. `exactly_once_v2` là lựa chọn hiện đại cho ứng dụng Kafka Streams ở các phiên bản hỗ trợ.

Đây là cơ chế của Kafka Streams. Trong Spring Kafka listener thông thường, cần cấu hình transactional producer, listener container và offset-in-transaction theo cách đã trình bày. Không dùng thuộc tính Kafka Streams để bật exactly-once cho một `@KafkaListener` thông thường.

## 14. Exactly-once và database: cần idempotency hoặc outbox/inbox

Giả sử listener đọc `orders.created`, cập nhật database rồi phát `orders.accepted`. Kafka transaction không tự rollback database nếu transaction Kafka abort.

Hai hệ thống có transaction manager độc lập không tự trở thành một transaction phân tán nguyên tử chỉ vì cùng nằm trong một phương thức Java.

Các lựa chọn:

- **Idempotency**: dùng event ID và unique constraint để một event không tạo side effect lặp.
- **Inbox**: lưu event ID đã xử lý trong cùng database transaction với thay đổi nghiệp vụ.
- **Outbox**: ghi thay đổi nghiệp vụ và outbox row trong cùng database transaction; relay/CDC phát outbox sang Kafka.
- **Saga/compensation**: khi nghiệp vụ trải qua nhiều hệ thống độc lập, thiết kế bước bù trừ thay vì giả định có một rollback toàn cục.

Ví dụ inbox:

~~~java
@Transactional
public void handle(OrderCreatedEvent event) {
    if (inboxRepository.existsByEventId(event.eventId())) {
        return;
    }

    orderRepository.create(event);
    inboxRepository.insert(event.eventId());
}
~~~

Trong production, `event_id` cần unique constraint và insert inbox phải cùng transaction với thay đổi nghiệp vụ. Nếu chỉ kiểm tra tồn tại rồi insert mà không có ràng buộc duy nhất, hai lần xử lý đồng thời có thể cùng vượt qua bước kiểm tra.

## 15. Chọn semantics theo nghiệp vụ

| Use case | Semantics thường phù hợp | Lý do |
|---|---|---|
| Telemetry có thể mất một vài mẫu, duplicate gây tốn chi phí | At-most-once hoặc best-effort | Chấp nhận mất dữ liệu trong failure window. |
| Audit log, đơn hàng, sự kiện thanh toán | At-least-once + idempotency | Ưu tiên không bỏ sót; chống side effect trùng. |
| Consumer chuyển đổi topic A sang B, cần output và offset nguyên tử | Exactly-once Kafka | Transaction gộp output và input offset. |
| Cập nhật database rồi phát Kafka | Outbox + at-least-once relay + idempotent consumer | Bảo vệ ranh giới DB/Kafka. |
| Kafka Streams aggregate/stateful pipeline | Exactly-once v2 nếu yêu cầu phù hợp | Framework quản lý transaction cho state và output. |
| Gửi email/SMS từ event | At-least-once + idempotency/deduplication | Kafka transaction không thể thu hồi email đã gửi. |

Không có semantics nào tự động là tốt nhất cho mọi use case. Cần xác định chi phí mất record, chi phí duplicate, yêu cầu ordering và ranh giới side effect.

## 16. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
|---|---|
| At-most-once nghĩa là chắc chắn xử lý đúng một lần | Có thể xử lý zero lần nếu process dừng sau commit sớm. |
| At-least-once nghĩa là luôn có duplicate | Duplicate có thể xảy ra, nhưng không phải lần nào cũng xảy ra. |
| Exactly-once nghĩa listener chỉ được gọi một lần | Listener có thể chạy lại; kết quả Kafka đã commit mới là điều được bảo vệ. |
| Producer idempotence tạo exactly-once end-to-end | Nó chủ yếu xử lý duplicate do producer retry protocol. |
| `read_committed` tự tạo transaction | Nó chỉ kiểm soát visibility của record transactional. |
| Kafka transaction rollback được database | Transaction Kafka không bao phủ database độc lập. |
| Commit offset thành công chứng minh nghiệp vụ thành công | Chỉ đúng nếu thời điểm commit được gắn với hoàn tất nghiệp vụ theo thiết kế. |
| Exactly-once không cần idempotency | Side effect ngoài Kafka và replay vẫn cần idempotency. |

## 17. Kiểm thử ba delivery semantics

Kiểm thử cần mô phỏng crash ở các thời điểm khác nhau, thay vì chỉ kiểm tra listener nhận được record.

| Kịch bản | At-most-once | At-least-once | Exactly-once Kafka |
|---|---|---|---|
| Crash trước xử lý | Record có thể đã bị commit sớm và mất | Record được giao lại nếu chưa commit | Input chưa commit trong transaction, có thể redeliver |
| Crash sau side effect trước commit | Không redeliver nếu offset đã commit | Có thể redeliver và lặp side effect | Output Kafka trong transaction abort; input có thể redeliver |
| Commit thành công | Không giao lại | Không giao lại | Output và offset cùng commit |
| Consumer restart | Tiếp tục từ offset đã xác nhận | Có thể đọc lại record chưa commit | Tiếp tục từ offset transaction đã commit |
| Downstream read isolation | Không liên quan nếu không dùng transaction | Không liên quan nếu không dùng transaction | Dùng read_committed để chỉ thấy output đã commit |

Các test cần có:

- Tắt consumer/process sau commit trước xử lý để xác minh at-most-once có thể mất record.
- Tắt process sau side effect trước commit để xác minh at-least-once redelivery.
- Abort transaction sau khi gửi output để xác minh output không hiển thị với read_committed.
- Commit transaction để xác minh output và offset input cùng tiến.
- Gửi lại cùng event ID để xác minh idempotency ở database.
- Kiểm tra producer fencing khi transactional ID bị dùng đồng thời.
- Đọc committed offset bằng AdminClient sau khi test đạt điều kiện.
- Dùng EmbeddedKafka hoặc Testcontainers và Awaitility/latch có timeout; không dùng Thread.sleep cố định.

Khi test exactly-once, hãy tạo consumer test với `isolation.level=read_committed`. Nếu chỉ đọc bằng `read_uncommitted`, test có thể nhìn thấy record thuộc transaction chưa commit hoặc đã abort và kết luận sai.

## 18. Quan sát và vận hành

Các metric giúp đánh giá delivery semantics trong production:

- Consumer lag và tốc độ tăng lag theo partition.
- Số lần listener thất bại, retry và redelivery.
- Số lần transaction commit/abort.
- Transaction duration và commit latency.
- Producer retry, timeout và fencing exception.
- Số event ID bị deduplicate ở inbox.
- Số record được chuyển vào DLT.
- Tỷ lệ side effect thành công và thất bại ở database/downstream.

Log nên chứa topic, partition, offset, event ID, correlation ID, group ID và trạng thái transaction cần thiết. Không log payload nhạy cảm.

Nếu transaction mở quá lâu, consumer `read_committed` có thể bị giới hạn bởi Last Stable Offset (LSO), khiến record phía sau chưa được trả về dù đã được ghi vào log. Theo dõi transaction duration, abort rate và lag cùng nhau để phân biệt broker chậm với transaction chưa hoàn tất.

## 19. Bài tập tổng hợp: so sánh ba semantics cho OrderCreatedEvent

Xây dựng ba listener độc lập đọc topic `orders.created`:

1. Listener A chạy at-most-once bằng manual immediate acknowledgment trước side effect.
2. Listener B chạy at-least-once bằng `AckMode.RECORD` và auto commit tắt.
3. Listener C chạy transactional consume-transform-produce, ghi `orders.accepted` và commit offset input trong cùng transaction.

Yêu cầu:

- Gửi cùng một bộ event có eventId ổn định.
- Mô phỏng process dừng trước xử lý.
- Mô phỏng process dừng sau side effect nhưng trước commit.
- Mô phỏng listener ném exception và transaction abort.
- Đọc output bằng consumer `read_committed`.
- So sánh số lần listener được gọi, số record output đã commit và số side effect database.
- Thêm inbox/unique constraint cho database để chống duplicate.
- Dùng AdminClient kiểm tra offset group sau từng kịch bản.
- Ghi rõ record nào có thể mất, record nào có thể redeliver và kết quả nào được bảo đảm.
- Đề xuất semantics cho luồng đơn hàng và giải thích trade-off.

Bài tập hoàn thành khi bạn chứng minh được failure window của từng semantics và phân biệt được số lần listener chạy với số lần kết quả nghiệp vụ có hiệu lực.

## 20. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Offset model | Offset tiếp theo cần đọc | Tính đúng offset commit sau một record. |
| 2. At-most-once | Commit trước xử lý | Giải thích được failure window gây mất record. |
| 3. At-least-once | Xử lý trước commit | Giải thích được redelivery và duplicate. |
| 4. Spring AckMode | RECORD, BATCH, MANUAL_IMMEDIATE | Chọn đúng thời điểm xác nhận. |
| 5. Producer idempotence | Retry protocol | Phân biệt producer dedupe với consumer semantics. |
| 6. Kafka transaction | Output + input offset atomicity | Commit hoặc abort cả hai cùng nhau. |
| 7. Read isolation | read_committed | Chỉ đọc output transactional đã commit. |
| 8. External effects | Inbox, outbox, idempotency | Bảo vệ database và dịch vụ ngoài Kafka. |
| 9. Testing | Crash window và transaction rollback | Kiểm thử được mất, trùng và redelivery. |
| 10. Operations | Lag, abort, retry và dedupe metrics | Theo dõi đúng chất lượng xử lý trong production. |

Bài học hoàn thành khi bạn có thể giải thích chính xác thời điểm commit của at-most-once và at-least-once, cấu hình được ba cách xử lý trong Spring Kafka, và nêu rõ exactly-once bảo vệ kết quả nào trong Kafka. Bạn cũng cần chỉ ra vì sao database, HTTP và các side effect ngoài Kafka vẫn cần idempotency hoặc outbox/inbox.

At-most-once đánh đổi khả năng mất record để tránh redelivery; at-least-once ưu tiên không bỏ sót nhưng cần chịu được xử lý lặp; exactly-once Kafka phối hợp output và input offset trong cùng transaction. Chọn semantics theo rủi ro nghiệp vụ và ranh giới hệ thống, không chỉ theo tên cấu hình.

