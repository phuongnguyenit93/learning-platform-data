# Rollback khi listener thất bại

Trong Spring Kafka, listener có thể chạy bên trong Kafka transaction do listener container quản lý. Container mở transaction trước khi gọi phương thức listener, sau đó gửi offset đã xử lý vào cùng Kafka transaction. Nếu listener hoàn tất bình thường, transaction commit và offset được ghi nhận cùng các Kafka record mà ứng dụng phát ra trong transaction. Nếu listener ném exception, transaction rollback; offset không được commit nên record có thể được đọc và xử lý lại.

Cơ chế này đặc biệt hữu ích với luồng consume-process-produce: consumer nhận một event, xử lý nghiệp vụ rồi phát event tiếp theo. Khi xử lý thất bại, Kafka có thể rollback cả output record lẫn offset của input trong cùng transaction. Tuy nhiên, rollback không tự hoàn tác side effect đã commit ở database hoặc HTTP service bên ngoài. Cần thiết kế idempotency, transaction synchronization hoặc outbox/inbox khi listener tương tác với hệ thống khác.

Bài học thuộc chương **Transactions** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Rollback trong listener container là gì?

Với transactional listener container, Kafka transaction bao quanh việc xử lý record hoặc batch. Container chịu trách nhiệm bắt đầu transaction, gọi listener và hoàn tất transaction theo kết quả xử lý.

Luồng record listener:

~~~mermaid
flowchart TD
    A[Consumer poll record] --> B[Container bắt đầu Kafka transaction]
    B --> C[Gọi @KafkaListener]
    C --> D{Listener thành công?}
    D -->|Có| E[Gửi offset vào transaction]
    E --> F[Commit Kafka transaction]
    D -->|Không, ném exception| G[Rollback Kafka transaction]
    G --> H[AfterRollbackProcessor]
    H --> I[Retry và seek để đọc lại]
    H --> J[Recover hoặc gửi DLT]
~~~

Khi transaction commit, offset của record được commit cùng transaction. Khi transaction rollback, offset chưa được commit trong group. Consumer có thể đọc lại record đó sau khi container thực hiện seek hoặc sau khi consumer khởi động lại.

Rollback là kết quả của exception thoát khỏi listener invocation. Nếu listener bắt exception rồi return bình thường, container thường xem invocation là thành công và tiếp tục commit transaction.

## 2. Cấu hình Kafka transaction cho listener container

Để listener container quản lý Kafka transaction, ProducerFactory cần được cấu hình transactional bằng transaction ID prefix. Mỗi application instance chạy đồng thời cần prefix duy nhất để tránh transactional ID xung đột và producer fencing không mong muốn.

Ví dụ Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: order-service-instance-a-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Các điểm cần chú ý:

- `transaction-id-prefix` bật transactional producer qua ProducerFactory.
- Prefix phải khác nhau giữa các instance đang chạy đồng thời.
- `enable-auto-commit` phải tắt để container quản lý offset.
- `read_committed` giúp consumer chỉ đọc record thuộc Kafka transaction đã commit.
- Consumer group cần có quyền đọc topic và tham gia group; producer cần quyền ghi topic và quyền transactional ID phù hợp.

Không dùng cùng một transaction ID prefix tĩnh cho tất cả replica. Trong môi trường container, inject identity ổn định và duy nhất của instance vào cấu hình.

## 3. Gắn KafkaTransactionManager vào container factory

Có thể tạo KafkaTransactionManager từ ProducerFactory và gắn vào container properties:

~~~java
@Bean
public KafkaTransactionManager<String, OrderEvent>
        kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTransactionManager);

    return factory;
}
~~~

`setKafkaAwareTransactionManager` là API dành cho Kafka-aware transaction manager trong các phiên bản Spring Kafka hiện đại. Ở các phiên bản cũ, có thể gặp API `setTransactionManager` đã deprecated. Hãy dùng API tương ứng với phiên bản dependency của dự án.

Listener chỉ định factory:

~~~java
@KafkaListener(
    id = "orderProcessor",
    topics = "order-events",
    groupId = "order-processor",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    orderService.process(event);
}
~~~

Container factory được gắn transaction manager mới tạo transactional boundary quanh listener invocation. Chỉ khai báo KafkaTransactionManager bean mà không gắn nó vào container factory thì chưa đủ để bảo đảm listener đang chạy trong Kafka transaction.

## 4. Listener thành công: commit output và offset

Giả sử listener nhận OrderCreated, ghi một event khác lên Kafka và kết thúc bình thường:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-processor",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    OrderValidated validated = orderService.validate(event);

    kafkaTemplate.send(
        "validated-orders",
        event.orderId(),
        validated
    );
}
~~~

Nếu KafkaTemplate sử dụng ProducerFactory transactional phù hợp với container transaction, record gửi ra được tham gia transaction hiện tại. Khi listener hoàn tất thành công, container gửi offset của input vào Kafka transaction rồi commit.

Với consumer downstream dùng `read_committed`, output record chỉ hiển thị sau khi transaction commit. Offset input cũng được commit trong Kafka transaction, giúp tránh trạng thái output đã commit nhưng input offset vẫn chưa được ghi nhận trong cùng Kafka transaction.

Đây là nền tảng của consume-process-produce transaction trong Kafka. Nó không bao gồm database hoặc HTTP side effect trừ khi các resource đó có cơ chế phối hợp riêng.

## 5. Listener ném exception: điều gì bị rollback?

Ví dụ listener xử lý event rồi phát output, nhưng bước cuối thất bại:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-processor",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    OrderValidated validated = orderService.validate(event);

    kafkaTemplate.send(
        "validated-orders",
        event.orderId(),
        validated
    );

    throw new IllegalStateException("Không thể hoàn tất xử lý");
}
~~~

Khi exception thoát khỏi listener:

1. Listener invocation thất bại.
2. Kafka transaction hiện tại bị rollback.
3. Output record gửi trong transaction bị abort và không hiển thị với consumer read_committed.
4. Offset input không được commit trong transaction đó.
5. AfterRollbackProcessor được gọi để quyết định seek, retry hoặc recover.
6. Record có thể được giao lại.

Rollback Kafka transaction không tự hoàn tác một HTTP request đã thành công, email đã gửi hoặc database transaction đã commit độc lập. Những side effect đó cần idempotency hoặc một thiết kế phối hợp transaction riêng.

## 6. Exception phải thoát khỏi listener để kích hoạt rollback

Nếu listener bắt exception và không ném lại, container không biết nghiệp vụ đã thất bại:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-processor",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    try {
        orderService.process(event);
    }
    catch (Exception exception) {
        log.error("Xử lý order thất bại", exception);
        // Return bình thường: container có thể commit transaction.
    }
}
~~~

Cách này có thể khiến offset được commit dù nghiệp vụ chưa hoàn tất. Nếu muốn rollback, hãy ném lại exception:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-processor",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    try {
        orderService.process(event);
    }
    catch (Exception exception) {
        log.error("Xử lý order thất bại", exception);
        throw exception;
    }
}
~~~

Nếu cần ghi log hoặc bổ sung context, hãy giữ exception gốc làm cause khi wrap:

~~~java
throw new OrderProcessingException(
    "Không xử lý được order " + event.orderId(),
    exception
);
~~~

Không nên chỉ trả về kết quả lỗi hoặc ghi log rồi return nếu contract yêu cầu container retry record.

## 7. Phân biệt rollback của container và @Transactional trên service

Có hai transaction boundary có thể xuất hiện trong một listener:

- Kafka transaction do listener container quản lý.
- Database transaction do DataSource/JPA transaction manager quản lý trong service.

Ví dụ service:

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {

    private final OrderRepository repository;

    @Transactional(transactionManager = "dbTransactionManager")
    public void process(OrderEvent event) {
        Order order = repository.findById(event.orderId())
            .orElseThrow();

        order.validate();
        repository.save(order);
    }
}
~~~

Nếu database transaction rollback và exception thoát ra listener, Kafka container transaction cũng rollback. Tuy nhiên, nếu database transaction đã commit thành công rồi một bước sau đó làm Kafka transaction rollback, database không tự quay lại trạng thái trước đó.

Trong mô hình listener container dùng Kafka transaction làm transaction chính, transaction database được đồng bộ theo cơ chế Spring khi cấu hình đúng. Thứ tự commit và cửa sổ lỗi cần được kiểm thử; không được suy luận rằng hai resource luôn commit nguyên tử.

Nếu nghiệp vụ cần bảo đảm cập nhật database và phát event không bị lệch, cân nhắc transactional outbox ở phía producer hoặc inbox/idempotency ở phía consumer.

## 8. Record listener và batch listener có phạm vi rollback khác nhau

Phạm vi transaction gắn với cách listener container gọi listener:

| Chế độ | Đơn vị listener invocation | Khi listener ném exception |
| --- | --- | --- |
| Record listener | Một record mỗi lần gọi | Transaction của record thất bại bị rollback; record lỗi được xử lý lại theo after-rollback policy. |
| Batch listener | Một batch từ poll mỗi lần gọi | Transaction của batch bị rollback; batch/records chưa được xác nhận có thể được đọc lại theo processor. |

Với record listener, các record đã xử lý thành công trước record lỗi thường đã hoàn tất transaction riêng. Record lỗi và các record còn lại từ poll có thể được seek để đọc lại.

Với batch listener, nhiều record được xử lý trong cùng một lần gọi. Nếu method ném exception, toàn bộ transaction của batch có thể rollback. Điều này khiến các record đã xử lý trước lỗi trong cùng batch cũng có thể được giao lại. Code batch nên idempotent.

Nếu cần xác định record lỗi trong batch, có thể dùng cơ chế batch error handling phù hợp với phiên bản Spring Kafka, chẳng hạn BatchListenerFailedException hoặc BatchToRecordAdapter trong trường hợp thích hợp. Không giả định partial progress tự động được giữ lại sau khi transaction batch rollback.

## 9. Offset được quản lý như thế nào trong transactional listener?

Trong transactional listener container, offset của record đã xử lý được gửi vào Kafka transaction bằng cơ chế transactional offset commit. Khi transaction commit, output records và offset input được commit như một transaction Kafka.

Khi transaction rollback:

- Offset input chưa được commit.
- Output record trong transaction bị abort.
- Container/AfterRollbackProcessor xác định record cần seek hoặc retry.
- Record có thể được đọc lại sau rollback.

`enable.auto.commit` nên tắt để tránh Kafka client tự commit offset ngoài transaction do container quản lý. Không tự gọi consumer commitSync/commitAsync trong listener transactional nếu chưa hiểu rõ tương tác với container.

Với consumer downstream, `read_committed` loại bỏ record thuộc transaction bị abort. Nó không thay thế error handling hoặc idempotency; nó chỉ kiểm soát visibility của Kafka transaction.

## 10. AfterRollbackProcessor làm nhiệm vụ gì?

`AfterRollbackProcessor` được listener container gọi sau khi transaction rollback. Processor quyết định cách xử lý record chưa hoàn tất:

- Seek về offset của record lỗi để đọc lại.
- Xử lý lại các record còn lại trong poll.
- Áp dụng retry/backoff.
- Sau số lần thử, gọi recoverer để chuyển record lỗi sang DLT hoặc xử lý phục hồi khác.
- Trong cấu hình phù hợp, commit offset của record đã recover trong một Kafka transaction mới.

`DefaultAfterRollbackProcessor` là implementation phổ biến. Nó hỗ trợ retry, backoff và recovery sau rollback cho transactional listener container.

Đây là cơ chế riêng cho đường rollback của transactional container. Với listener container không dùng Kafka transaction, lỗi thường được xử lý bởi CommonErrorHandler như DefaultErrorHandler. Không nên đánh đồng hai cơ chế vì vị trí xử lý và semantics offset khác nhau.

## 11. Cấu hình DefaultAfterRollbackProcessor

Có thể cấu hình retry sau rollback bằng `DefaultAfterRollbackProcessor` và `FixedBackOff`:

~~~java
@Bean
public DefaultAfterRollbackProcessor<String, OrderEvent>
        afterRollbackProcessor(
            DeadLetterPublishingRecoverer recoverer,
            KafkaTemplate<Object, Object> kafkaTemplate) {

    DefaultAfterRollbackProcessor<String, OrderEvent> processor =
        new DefaultAfterRollbackProcessor<>(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );

    processor.setCommitRecovered(true);
    processor.setKafkaTemplate(kafkaTemplate);

    return processor;
}
~~~

Ví dụ này cấu hình khoảng chờ một giây và hai lần retry sau lần xử lý đầu tiên. Khi hết retry, recoverer được gọi để xử lý record lỗi.

`setCommitRecovered(true)` yêu cầu processor commit offset của record đã recover. Cần cung cấp KafkaTemplate transactional và listener container phải dùng KafkaTransactionManager để offset của record đã recover được commit trong một Kafka transaction mới. Nhờ đó, record đã gửi sang DLT thành công không tiếp tục bị đọc lại chỉ vì offset nguồn chưa được ghi nhận.

Cấu hình trên là ví dụ cho record listener. Kiểu generic, KafkaTemplate và serializer thực tế phải phù hợp với key/value của ứng dụng; với deserialization failure, template còn phải hỗ trợ raw byte[] nếu cần bảo toàn payload lỗi.

## 12. Gắn AfterRollbackProcessor vào container factory

Gắn processor vào factory đang được listener sử dụng:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager,
            DefaultAfterRollbackProcessor<String, OrderEvent>
                afterRollbackProcessor) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTransactionManager);
    factory.setAfterRollbackProcessor(afterRollbackProcessor);

    return factory;
}
~~~

Factory có hai cấu hình liên quan nhưng khác nhiệm vụ:

- KafkaTransactionManager mở/commit/rollback Kafka transaction quanh listener.
- AfterRollbackProcessor quyết định xử lý record sau khi transaction rollback.

Nếu ứng dụng có nhiều listener container factory, phải gắn processor vào đúng factory. Chỉ khai báo bean processor không đảm bảo mọi container tự động sử dụng nó.

## 13. Retry và backoff sau rollback

Retry cho phép xử lý lại lỗi có khả năng tự hết, ví dụ database tạm thời unavailable hoặc downstream trả HTTP 503. Backoff tạo khoảng nghỉ giữa các lần thử để tránh gửi request liên tục vào dependency đang quá tải.

Ví dụ:

~~~java
new FixedBackOff(2_000L, 3L)
~~~

Cấu hình trên chờ hai giây giữa các lần retry và giới hạn ba lần retry sau lần đầu. Tổng số lần listener được thử thường là lần đầu cộng số lần retry; hãy kiểm tra log/metric thực tế để tránh nhầm `maxAttempts` với tổng số invocation.

Phân loại lỗi trước khi chọn retry:

| Loại lỗi | Hướng xử lý gợi ý |
| --- | --- |
| Database connection timeout tạm thời | Retry hữu hạn với backoff. |
| HTTP 503 hoặc rate limit | Retry theo backoff, tôn trọng Retry-After nếu ứng dụng hỗ trợ. |
| Dữ liệu event sai contract | Không retry dài; recover sang DLT sau chính sách phù hợp. |
| Vi phạm business rule vĩnh viễn | Không retry tự động nếu dữ liệu không thể tự thay đổi. |
| Bug trong code | Dừng vòng lặp retry vô ích, cảnh báo và chuyển quy trình điều tra. |

Có thể cấu hình exception không retry bằng API phân loại của processor, ví dụ:

~~~java
processor.addNotRetryableExceptions(InvalidOrderEventException.class);
~~~

Hãy xác nhận API và semantics theo phiên bản Spring Kafka đang dùng. Không đánh dấu lỗi tạm thời là non-retryable nếu hệ thống có thể tự phục hồi trong thời gian ngắn.

## 14. Poison record và chuyển sang DLT

Poison record là record luôn làm listener thất bại, ví dụ payload không hợp lệ hoặc event vi phạm contract. Nếu chỉ retry vô hạn, partition có thể không tiến triển.

Sau số lần thử hữu hạn, recoverer có thể chuyển record sang DLT:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(dltTemplate);
}
~~~

Với resolver mặc định phổ biến, record từ topic nguồn được gửi sang topic có hậu tố `.DLT` và giữ partition index nguồn. DLT phải có partition tương ứng hoặc dùng destination resolver tùy chỉnh phù hợp topology.

Khi kết hợp với `setCommitRecovered(true)`, processor có thể publish record lỗi và commit offset đã recover trong một Kafka transaction mới. Nếu publish DLT thất bại, recovery không được xem là thành công; record nguồn cần tiếp tục được xử lý theo chính sách retry/recovery.

DLT nên giữ metadata nguồn như topic, partition, offset, timestamp và exception để đội vận hành điều tra. Không log toàn bộ payload nếu chứa dữ liệu nhạy cảm.

## 15. Commit recovered offset trong transaction mới

Khi retry hết và recoverer đã xử lý record, ứng dụng cần bảo đảm consumer group tiến qua record đó. Nếu chỉ publish sang DLT nhưng không commit offset nguồn, record có thể được đọc lại sau restart/rebalance và gửi sang DLT lần nữa.

`setCommitRecovered(true)` cùng KafkaTemplate cho phép DefaultAfterRollbackProcessor thực hiện commit offset của record đã recover trong transaction mới.

~~~mermaid
flowchart TD
    A[Listener thất bại] --> B[Rollback transaction ban đầu]
    B --> C[Retry theo backoff]
    C --> D{Còn retry?}
    D -->|Có| A
    D -->|Không| E[Recoverer publish DLT]
    E --> F{Publish thành công?}
    F -->|Không| G[Recovery thất bại, tiếp tục xử lý lỗi]
    F -->|Có| H[Mở Kafka transaction mới]
    H --> I[Commit offset record đã recover]
    I --> J[Commit transaction mới]
    J --> K[Partition tiếp tục tiến]
~~~

Việc publish DLT và commit offset recovered trong transaction mới giúp hai thao tác Kafka này nhất quán với nhau. Nó không bao gồm database transaction bên ngoài và không loại bỏ duplicate nếu recovery hoặc ứng dụng bị lỗi ở các ranh giới khác.

## 16. Batch listener rollback và xử lý từng record

Với batch listener, listener nhận nhiều record trong một lần gọi. Nếu method ném exception, transaction của lần gọi batch bị rollback. Các record đã xử lý trước khi lỗi trong cùng batch có thể được giao lại, vì offset của batch chưa được commit.

Ví dụ:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-processor",
    containerFactory = "orderBatchListenerFactory"
)
public void onBatch(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.process(record.value());
    }
}
~~~

Nếu xử lý record thứ ba thất bại và exception thoát ra, cả transaction batch có thể rollback. Những record đầu đã chạy thành công trong vòng lặp vẫn có thể được đọc lại. Vì vậy, thao tác trong batch cần idempotent.

Nếu muốn xử lý và retry theo từng record, cân nhắc record listener hoặc cơ chế batch-to-record phù hợp. `BatchToRecordAdapter` có thể giúp chuyển batch thành lời gọi record listener trong một số cấu hình; hãy kiểm tra semantics transaction và error handling của phiên bản đang dùng.

Không giả định `BatchListenerFailedException` tự động tạo một transaction độc lập cho từng phần tử. Phạm vi commit/rollback phụ thuộc container mode và cấu hình processor.
## 17. Database side effect không tự rollback theo Kafka

Ví dụ listener cập nhật database rồi ném exception:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "billing-service",
    containerFactory = "transactionalListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    billingService.updateInvoice(event);
    throw new IllegalStateException("Lỗi sau khi cập nhật database");
}
~~~

Nếu `updateInvoice` đã commit database transaction riêng trước khi exception thoát ra, Kafka transaction rollback không thể hoàn tác thay đổi đó. Khi record được đọc lại, invoice có thể bị cập nhật lần nữa.

Các cách giảm rủi ro:

- Cho handler idempotent theo event ID.
- Ghi inbox/processed event marker trong cùng database transaction với thay đổi nghiệp vụ.
- Đồng bộ database transaction với Kafka transaction khi phù hợp và chấp nhận failure window.
- Dùng outbox cho chiều phát event từ database.
- Tránh gọi side effect không thể đảo ngược trước khi biết transaction sẽ commit.

Nếu service method dùng @Transactional và cần rollback với checked exception, khai báo `rollbackFor` phù hợp vì Spring transaction mặc định thường rollback với RuntimeException và Error, không tự rollback mọi checked exception. Kafka listener container vẫn cần nhận exception để thực hiện rollback Kafka transaction.

## 18. Non-blocking retry và transactional listener

Non-blocking retry bằng retry topic là một mô hình khác với blocking retry sau rollback. Nó chuyển record sang retry topic và để partition nguồn tiếp tục xử lý record sau.

Không nên mặc định kết hợp retry topic với transactional listener container. Spring Kafka có các giới hạn tương thích theo phiên bản; non-blocking retry không được hỗ trợ với container transaction trong các cấu hình phổ biến. Khi cần transaction rollback và retry, ưu tiên AfterRollbackProcessor với blocking retry hoặc thiết kế lại luồng retry thành một quy trình riêng không dựa vào transactional listener container.

Nếu chọn retry topic, cần hiểu ordering có thể thay đổi: event sau có thể được xử lý trước event đang chờ ở retry topic. Điều này ảnh hưởng aggregate cùng key và sequence nghiệp vụ.

## 19. DefaultErrorHandler và AfterRollbackProcessor khác nhau thế nào?

Hai thành phần có vai trò gần nhau nhưng nằm ở hai đường xử lý khác nhau:

| Thành phần | Dùng trong trường hợp | Vai trò |
| --- | --- | --- |
| DefaultErrorHandler | Listener container không dùng Kafka transaction theo đường rollback | Retry/recover exception bằng common error handling. |
| AfterRollbackProcessor | Transactional listener container sau khi Kafka transaction rollback | Seek/retry/recover record chưa được commit sau rollback. |
| DefaultAfterRollbackProcessor | Implementation mặc định của AfterRollbackProcessor | Cung cấp backoff, retry và recovery sau rollback. |
| DeadLetterPublishingRecoverer | Được dùng bởi error handler/rollback processor | Publish record đã recover sang DLT. |

Khi dùng Kafka transaction cho listener, hãy cấu hình AfterRollbackProcessor để kiểm soát đường retry sau rollback. Không cấu hình DefaultErrorHandler với giả định nó thay thế hoàn toàn after-rollback processing.

Cần đọc tài liệu đúng phiên bản Spring Kafka vì error handling API và cách container kết hợp các handler đã thay đổi qua các phiên bản.

## 20. Kiểm thử rollback khi listener thất bại

Integration test nên dùng Kafka thật qua Testcontainers hoặc Embedded Kafka phù hợp với phiên bản dự án. Cần xác nhận cả transaction visibility, offset và hành vi retry.

Các kịch bản:

1. Listener thành công: output record và input offset được commit.
2. Listener ném exception: Kafka transaction rollback và output record không hiển thị với `read_committed` consumer.
3. Record input được đọc lại sau rollback.
4. Retry/backoff chạy đúng số lần cấu hình.
5. Retry hết: recoverer publish record sang DLT.
6. `commitRecovered=true`: offset nguồn tiến sau khi DLT publish thành công.
7. DLT publish thất bại: record không bị coi là recovered và offset không tiến sai.
8. Batch listener thất bại: xác nhận phạm vi batch bị rollback và record có thể được giao lại.
9. Listener bắt exception rồi return: xác nhận container xem invocation là thành công theo thiết kế hiện tại.
10. Database side effect: xác nhận idempotency/inbox ngăn tác dụng phụ lặp.
11. Consumer downstream dùng `read_committed` không nhìn thấy record thuộc transaction abort.
12. Rebalance/restart trong lúc retry: xác nhận record không bị mất và duplicate được xử lý an toàn.

Dùng event ID duy nhất, latch hoặc Awaitility với timeout. Không chỉ assert listener method đã được gọi; cần đọc topic output/DLT và kiểm tra committed offset hoặc hành vi redelivery.

## 21. Quan sát và vận hành rollback

Theo dõi các metric và log sau:

- Số Kafka transaction commit và abort.
- Số listener exception theo topic/group.
- Số lần rollback và retry cho mỗi record.
- Backoff duration và thời gian listener xử lý.
- DLT publish success/failure.
- Consumer lag và offset progression.
- Producer fencing hoặc transactional ID collision.
- Duplicate event được phát hiện bởi idempotency/inbox.
- Rebalance trong khi listener đang retry.

Log nên chứa topic, partition, offset, group ID, event ID và exception class. Không log toàn bộ payload nếu có dữ liệu nhạy cảm.

Nếu rollback tăng đột biến, kiểm tra thay đổi producer schema, downstream availability, database connection pool, lỗi code và transaction timeout. Một poison record lặp lại ở cùng partition thường cần được nhận diện qua source offset và retry count.

## 22. Checklist thiết kế rollback

Trước khi triển khai transactional listener, hãy xác nhận:

1. ProducerFactory có transaction ID prefix duy nhất cho mỗi instance.
2. Listener container được gắn KafkaTransactionManager.
3. Auto commit của consumer đã tắt.
4. Consumer cần đọc transactional output dùng read_committed.
5. Exception nghiệp vụ được ném ra khỏi listener khi cần rollback.
6. Không nuốt exception rồi return nếu không muốn commit.
7. AfterRollbackProcessor được cấu hình đúng factory.
8. Retry/backoff hữu hạn và phù hợp loại lỗi.
9. DLT có partition topology và serializer phù hợp.
10. Commit recovered offset chỉ bật khi recovery và transaction mới được cấu hình đúng.
11. Batch listener hiểu rằng rollback có thể làm đọc lại toàn batch.
12. Database/HTTP side effect có idempotency hoặc cơ chế phối hợp riêng.
13. Checked exception có rollbackFor phù hợp ở database transaction.
14. Có integration test commit, rollback, retry, DLT và redelivery.
15. Có metric/log để phát hiện poison record, retry storm và fencing.

Khi listener thất bại trong transactional container, Kafka transaction rollback khiến output record và offset input không được commit như một giao dịch thành công. AfterRollbackProcessor điều khiển seek, retry và recovery; DefaultAfterRollbackProcessor có thể chuyển record lỗi sang DLT và commit offset recovered trong transaction mới. Thiết kế đúng cần tính đến phạm vi record/batch, side effect ngoài Kafka, idempotency và kiểm thử failure path.




