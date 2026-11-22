# Rollback transaction trong Spring Kafka

**Rollback transaction** trong Spring Kafka là hành vi hủy hiệu lực một giao dịch Kafka khi quá trình gửi hoặc xử lý record không hoàn tất đúng. Ở tầng Kafka producer, thao tác tương ứng là abortTransaction(). Với một transactional listener container, exception có thể khiến Kafka transaction bị abort, sau đó **AfterRollbackProcessor** quyết định cách seek và xử lý lại những record chưa hoàn tất.

Một Kafka transaction có thể bao gồm nhiều record output và **offset của consumer đầu vào**, giúp xây dựng luồng consume → process → produce: hoặc kết quả Kafka và offset cùng được commit, hoặc giao dịch bị abort và offset không tiến nhờ transaction đó.

Điều này **không có nghĩa database, REST API, email hoặc hệ thống bên ngoài cũng rollback**. Nếu listener đã cập nhật database rồi Kafka transaction abort, database vẫn có thể đã commit. Vì thế, rollback phải được hiểu cùng với offset, idempotency, retry, DLT và transaction boundary.

## 1. Giao dịch Kafka bảo vệ những thành phần nào?

Kafka producer có thể mở một transaction, gửi nhiều record đến một hay nhiều partition, rồi commit hoặc abort. Với luồng tiêu thụ và phát lại, offset của consumer group có thể được gửi vào chính transaction đó.

~~~text
orders.created (input topic)
        |
        v
Kafka listener container
        |
        +--> Begin Kafka transaction
        |
        +--> Gọi @KafkaListener
        |        |
        |        +--> Validate event
        |        +--> KafkaTemplate.send("orders.validated")
        |
        +--> Gửi input offsets vào transaction
        |
        +-------------+-------------+
        |                           |
        v                           v
   COMMIT TRANSACTION         ABORT TRANSACTION
        |                           |
        +--> Output Kafka           +--> Output Kafka
        |    được commit            |    không hiển thị với
        |                           |    read_committed
        +--> Input offsets          +--> Input offsets của
             được commit                 transaction không commit
~~~

Các thành phần của Spring Kafka:

- KafkaTemplate dùng producer do Spring quản lý để gửi record.
- KafkaTransactionManager quản lý producer transaction trong Spring transaction infrastructure.
- Listener container có thể mở Kafka transaction trước khi gọi listener.
- DefaultAfterRollbackProcessor xử lý record sau khi Kafka transaction bị rollback.
- DeadLetterPublishingRecoverer có thể xuất record không phục hồi được sang DLT.
- Consumer cấu hình isolation.level=read_committed chỉ quan sát transactional output đã commit.

Không phải mọi @KafkaListener đều transactional. Nó chỉ có hành vi trên khi container factory và transaction manager được cấu hình phù hợp.

## 2. Commit, rollback, retry và recovery khác nhau

| Thuật ngữ | Ý nghĩa | Hệ quả với input record |
|---|---|---|
| Commit transaction | Xác nhận output Kafka và các offset được đưa vào transaction | Group offset tiến khi transaction commit |
| Abort/rollback | Hủy giao dịch chưa commit | Offset không được commit bởi transaction đó |
| Retry | Chạy lại logic listener sau thất bại | Cùng record có thể được giao lại |
| Seek | Điều chỉnh consumer position | Cho phép poll lại record cần xử lý |
| AfterRollbackProcessor | Điều phối seek, backoff, recovery sau abort | Giữ hoặc xử lý record lỗi theo policy |
| DLT recovery | Lưu record thất bại vào topic riêng | Có thể tiến offset sau recovery thành công |
| Database rollback | Hoàn tác giao dịch database | Không do Kafka abort tự thực hiện |

**Rollback không xóa record đầu vào khỏi Kafka.** Record vẫn nằm trong source topic. Nếu offset input chưa được commit, consumer có thể gặp lại record khi tiếp tục xử lý hoặc khi partition được gán cho instance khác.

## 3. Vòng đời producer transaction

Tại Kafka client, vòng đời khái quát:

~~~text
initTransactions()
      |
      v
beginTransaction()
      |
      +--> send(record A)
      +--> send(record B)
      +--> sendOffsetsToTransaction(...) khi dùng consumer group
      |
      +--> Thành công ----------------> commitTransaction()
      |
      +--> Exception ----------------> abortTransaction()
~~~

Spring Kafka thường quản lý những bước này giúp ứng dụng. Với producer được KafkaTemplate và KafkaTransactionManager quản lý, không nên tự mở hoặc commit transaction trên cùng producer ở ngoài transaction scope.

Một transaction bị abort không đơn giản là các record bị xóa vật lý ngay lập tức khỏi log. Kafka dùng transaction markers để thể hiện commit/abort; consumer có isolation.level=read_committed không trả về record thuộc transaction abort.

Consumer dùng read_uncommitted có thể quan sát record trong transaction đã abort. Vì vậy, hệ thống downstream muốn dựa vào Kafka exactly-once semantics cần xem xét isolation level.

## 4. Cấu hình Spring Boot cho Kafka transactions

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      transaction-id-prefix: order-service-node-1-
      acks: all
      properties:
        "[enable.idempotence]": true
    consumer:
      group-id: order-validator
      enable-auto-commit: false
      isolation-level: read_committed
    listener:
      ack-mode: record
~~~

Ý nghĩa:

- transaction-id-prefix là tiền tố để tạo transactional.id cho các producer được Spring quản lý. Trong Spring Boot, cấu hình này có thể kích hoạt auto-configuration của Kafka transaction manager khi các điều kiện phù hợp.
- acks=all và enable.idempotence giúp đáp ứng cấu hình producer đáng tin cậy. Kafka transactional producer có những yêu cầu cấu hình idempotence tương ứng.
- enable-auto-commit=false để container chủ động quản lý offset và có thể đưa offset vào transaction.
- isolation-level=read_committed đặc biệt quan trọng với consumer đọc transactional output từ producer khác.
- ack-mode quyết định cách container ghi nhận tiến độ listener; offset trong Kafka transaction có thêm ngữ nghĩa riêng do container quản lý.

**Transactional ID phải tránh trùng giữa hai producer đang hoạt động.** Nếu nhiều replica sử dụng cùng danh tính transactional, Kafka có thể fence producer cũ. Khi scale hoặc rolling deployment, cần thiết kế prefix/suffix phù hợp với số instance và producer cache.

Nếu tự tạo ProducerFactory hoặc ConcurrentKafkaListenerContainerFactory, phải kiểm tra transaction manager có thực sự được gắn vào factory đang sử dụng. YAML không tự sửa cấu hình của một factory custom chưa được wiring.

## 5. Gửi nhiều record bằng KafkaTemplate.executeInTransaction

Khi ứng dụng chỉ cần gửi nhiều record như một đơn vị Kafka transaction, có thể dùng executeInTransaction:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishBoth(
            String orderId,
            OrderEvent event,
            OrderEvent auditEvent) {

        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("orders.events", orderId, event).join();
            operations.send("orders.audit", orderId, auditEvent).join();
            return null;
        });
    }
}
~~~

Ví dụ minh họa kiểu CompletableFuture của các phiên bản Spring Kafka hiện đại. KafkaTemplate phải có transactional ProducerFactory. Nếu một lời gọi send ném RuntimeException ra khỏi callback, Spring abort transaction. Nếu callback hoàn tất bình thường, Spring cố gắng commit transaction.

Việc gọi join() làm lỗi send bất đồng bộ được truyền ra trong callback. Nếu để lỗi bị nuốt, code có thể đi tới commit dù nghiệp vụ đã thất bại.

Ví dụ không phù hợp:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    try {
        operations.send("orders.events", orderId, event).join();
    }
    catch (RuntimeException ex) {
        log.error("Send failed", ex);
        // Nuốt lỗi, trả về bình thường.
    }
    return null;
});
~~~

Nếu cần abort, hãy ném exception ra khỏi callback. Không tự gọi producer.commitTransaction() hoặc abortTransaction() trên resource đã được KafkaTemplate quản lý.

executeInTransaction phù hợp cho producer-only Kafka transaction. Nếu cần gắn **offset của consumer đầu vào** vào giao dịch, nên dùng transactional listener container hoặc cơ chế quản lý consumer offsets trong transaction được framework hỗ trợ.

## 6. @Transactional và rollback rules của Spring

Có thể dùng Spring transaction abstraction với KafkaTransactionManager:

~~~java
@Service
public class BillingEventService {

    private final KafkaTemplate<String, BillingEvent> kafkaTemplate;

    public BillingEventService(
            KafkaTemplate<String, BillingEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publishBillingEvent(
            String invoiceId,
            BillingEvent event) {

        kafkaTemplate.send("billing.events", invoiceId, event);

        if (!event.isAllowed()) {
            throw new IllegalStateException(
                    "Billing event is not allowed"
            );
        }
    }
}
~~~

Ví dụ giả định bean KafkaTransactionManager có tên kafkaTransactionManager và KafkaTemplate được cấu hình cùng ProducerFactory hỗ trợ transaction.

Theo mặc định của Spring transaction abstraction:

- RuntimeException và Error thường kích hoạt rollback.
- Checked exception không mặc định kích hoạt rollback trừ khi cấu hình rollbackFor hoặc rollback rule khác.
- Transaction phải được mở thực sự qua Spring proxy hoặc transaction infrastructure; self-invocation có thể bỏ qua @Transactional.
- Bắt exception rồi trả về bình thường có thể làm transaction commit thay vì rollback.

Nếu business exception là checked exception, có thể khai báo:

~~~java
@Transactional(
        transactionManager = "kafkaTransactionManager",
        rollbackFor = Exception.class
)
public void publishWithCheckedFailure() throws Exception {
    // Gửi event và ném checked exception khi thất bại.
}
~~~

Không nên áp một quy tắc rollbackFor rộng mà không hiểu ngoại lệ nào thật sự cần rollback; nhưng phải biết rõ trường hợp checked exception nếu muốn giao dịch bị hủy.

## 7. Rollback trong transactional listener container

Transactional listener container là cấu hình quan trọng cho luồng **consume-process-produce**. Container bắt đầu Kafka transaction, gọi listener, đưa offset input vào transaction và commit khi xử lý thành công.

~~~text
KafkaConsumer.poll()
         |
         v
Container begin transaction
         |
         v
@KafkaListener
         |
         +--> KafkaTemplate.send(output)
         |
         +--> return normally
         |         |
         |         v
         |   send input offsets into transaction
         |         |
         |         v
         |      COMMIT
         |
         +--> throw exception
                   |
                   v
                 ABORT
                   |
                   v
           AfterRollbackProcessor
                   |
                   v
              Retry / recovery
~~~

Listener:

~~~java
@Component
public class OrderValidatorConsumer {

    private final OrderValidator validator;
    private final KafkaTemplate<String, OrderValidated> kafkaTemplate;

    public OrderValidatorConsumer(
            OrderValidator validator,
            KafkaTemplate<String, OrderValidated> kafkaTemplate) {
        this.validator = validator;
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-validator",
            containerFactory = "transactionalListenerFactory"
    )
    public void onOrder(OrderCreated event) {
        OrderValidated validated = validator.validate(event);

        kafkaTemplate.send(
                "orders.validated",
                event.orderId(),
                validated
        );
    }
}
~~~

Factory transactionalListenerFactory cần cấu hình Kafka-aware transaction manager theo API của phiên bản Spring Kafka đang dùng. KafkaTemplate gửi output phải tham gia đúng thread-bound Kafka transaction mà container mở. Chỉ ghi tên containerFactory trong annotation không làm listener tự transactional.

Listener không nên gọi consumer.commitSync() hoặc bật auto-commit nếu mục tiêu là commit Kafka offset cùng output transactional.

## 8. Exception được truyền ra để rollback

Ví dụ listener gửi output rồi ném exception:

~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "transactionalListenerFactory"
)
public void onOrder(OrderCreated event) {
    validator.validate(event);

    kafkaTemplate.send(
            "orders.validated",
            event.orderId(),
            toValidated(event)
    );

    if (event.needsManualReview()) {
        throw new BusinessProcessingException(
                "Manual review required"
        );
    }
}
~~~

Nếu exception thực sự được truyền tới container:

1. Container nhận exception.
2. Transaction manager abort Kafka transaction.
3. Output Kafka trong transaction bị abort.
4. Input offset gửi vào transaction đó không được commit.
5. AfterRollbackProcessor xử lý seek/redelivery hoặc recovery.
6. Record đầu vào vẫn nằm ở topic nguồn và có thể được thử lại.

**Cẩn thận khi nuốt exception:**

~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "transactionalListenerFactory"
)
public void onOrder(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Failed", ex);
        // Return bình thường có thể dẫn tới commit.
    }
}
~~~

Log lỗi không đồng nghĩa rollback. Nếu ứng dụng muốn container abort, hãy ném lại exception hoặc dùng chính sách rollback được framework hỗ trợ.

## 9. AfterRollbackProcessor và vị trí đọc sau rollback

Một KafkaConsumer có hai trạng thái cần phân biệt:

- Consumer position: offset mà consumer sẽ fetch tiếp sau poll/seek.
- Committed group offset: vị trí đã được lưu bền vững cho group.

Kafka transaction có thể chứa một offset **đang chờ commit**. Khi transaction abort, offset ấy không thành committed offset. Nhưng consumer đã poll nhiều record nên vị trí nội bộ của consumer có thể đã đi xa hơn. Vì vậy, container cần seek/redelivery thích hợp.

DefaultAfterRollbackProcessor của Spring Kafka xử lý tình huống đó:

~~~text
poll() nhận A, B, C
         |
         +--> xử lý A
         +--> xử lý B lỗi
         |
         v
Kafka transaction abort
         |
         v
DefaultAfterRollbackProcessor
         |
         +--> Xác định records chưa xử lý hoàn tất
         +--> BackOff policy
         +--> Seek về vị trí cần redelivery
         |
         v
poll() lại record tương ứng
~~~

Không nên hiểu abortTransaction() như một lệnh Kafka tự động seek consumer về đầu topic. Abort thay đổi trạng thái giao dịch tại Kafka; Spring container/AfterRollbackProcessor chịu trách nhiệm điều phối vị trí đọc để retry.

Với transactional container, exception cần được truyền ra để transaction rollback. Spring Kafka không mặc định xử lý lỗi transactional container bằng cách nuốt lỗi giống một số cấu hình phi transactional. Nếu tự cấu hình CommonErrorHandler, phải hiểu rõ nó có ném lại exception hay không.

## 10. Retry có giới hạn sau rollback

Có thể tạo DefaultAfterRollbackProcessor với recoverer và BackOff:

~~~java
DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
                (record, exception) -> {
                    log.error(
                            "Failed record: topic={}, partition={}, offset={}",
                            record.topic(),
                            record.partition(),
                            record.offset(),
                            exception
                    );
                },
                new FixedBackOff(1_000L, 2L)
        );
~~~

Ví dụ mô tả hai lần retry sau lần xử lý ban đầu, cách nhau một giây. Tuy nhiên, **recoverer chỉ ghi log chưa lưu record lỗi một cách bền vững**. Nếu cần bảo toàn dữ liệu, hãy dùng DeadLetterPublishingRecoverer hoặc một kho quarantine có bảo đảm ghi nhận thành công.

Các nguyên tắc khi retry:

- Đặt số attempts và backoff hữu hạn.
- Phân loại lỗi tạm thời và lỗi dữ liệu cố định.
- Payload sai cú pháp sẽ không tự sửa sau vài lần retry.
- Backoff dài giữ partition chờ và có thể tăng consumer lag.
- Bất kỳ side effect ngoài Kafka nào cũng cần chống duplicate.
- Nếu recoverer thất bại, lỗi không nên bị xem là đã được recovery.

Cần gắn AfterRollbackProcessor vào đúng container factory mà listener sử dụng, theo API của phiên bản Spring Kafka. Một bean processor độc lập không bảo đảm listener sẽ tự nhận được nó nếu factory chưa wiring.

## 11. Batch listener và rollback

Batch listener nhận nhiều record trong một callback. Nếu callback xử lý thành công vài record rồi ném exception, transaction chứa output của batch có thể abort. Toàn bộ hoặc một phần batch có thể cần được đọc lại theo recovery policy.

~~~text
poll batch:
  A: success
  B: success
  C: exception
  D: not processed
         |
         v
   Kafka transaction abort
         |
         v
   AfterRollbackProcessor
         |
         v
   Redelivery / recovery
~~~

Một exception chung từ batch listener không nhất thiết cho framework biết chính xác record nào đã gây lỗi. Tùy phiên bản, AfterRollbackProcessor có thể phải redeliver cả batch. Nếu A và B đã cập nhật database ngoài Kafka, chúng có thể bị thực thi lại dù Kafka output của transaction bị abort.

Khi dùng batch listener:

- Xác định rõ chiến lược recovery của batch trên phiên bản Spring Kafka.
- Dùng eventId và idempotency cho từng record.
- Nếu cần, sử dụng database transaction cho batch operation.
- Giới hạn batch size theo max.poll.interval.ms và transaction timeout.
- Không coi thành công của một phần batch là committed offset.
- Kiểm thử lỗi ở giữa batch, lỗi DLT và crash trước commit.

Nếu nghiệp vụ yêu cầu xử lý lỗi độc lập từng record, record listener có thể đơn giản hơn batch listener transactional.

## 12. Recovery sang DLT sau rollback

Một record cố định bị lỗi có thể làm transaction rollback nhiều lần mà không tự phục hồi. Khi hết retries, AfterRollbackProcessor có thể dùng recoverer gửi record sang DLT.

~~~text
Transactional listener
        |
        +--> exception
                |
                v
         Abort Kafka transaction
                |
                v
        AfterRollbackProcessor
                |
                +--> Retry/seek lại
                |
                +--> Hết retries
                         |
                         v
                 DeadLetterPublishingRecoverer
                         |
                         v
                        DLT
~~~

Ví dụ:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltKafkaTemplate);

DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
                recoverer,
                new FixedBackOff(2_000L, 3L)
        );
~~~

Cần hiểu ranh giới giao dịch: **transaction gây lỗi đã abort trước khi thực hiện recovery**. Để việc publish DLT và ghi nhận offset recovered có ngữ nghĩa nhất quán, Spring Kafka cung cấp các tùy chọn transactional recovery trong những phiên bản hỗ trợ, chẳng hạn setCommitRecovered(true) cùng KafkaTemplate phù hợp trên DefaultAfterRollbackProcessor.

Không bật một tùy chọn commitRecovered rồi giả định mọi thứ đã atomic mà không cấu hình đúng producer factory, KafkaTemplate, transaction manager và loại container.

Nếu publish DLT thất bại do serializer, ACL, partition không tồn tại hoặc broker lỗi, không nên coi record nguồn đã recovery thành công. Cần để lỗi được báo và xử lý lại theo policy.

Một cửa sổ duplicate vẫn có thể tồn tại nếu record đã xuất hiện ở DLT nhưng offset recovered chưa commit khi process crash. DLT consumer và công cụ replay phải dùng event ID để xử lý an toàn.

## 13. Consumer position và committed offset

Giả sử topic input có:

~~~text
offset 100: record A
offset 101: record B (lỗi)
offset 102: record C
~~~

Consumer có thể đã poll cả A, B, C. Position của consumer có thể ở offset 103, nhưng committed offset của group vẫn ở vị trí cũ. Nếu transaction abort, các offsets đang chờ commit trong transaction không trở thành committed offset. AfterRollbackProcessor có thể seek lại để xử lý những record cần retry.

Phân biệt:

| Giá trị | Định nghĩa |
|---|---|
| Record offset | Vị trí một record trong partition |
| Consumer position | Vị trí consumer sẽ poll tiếp sau seek/poll |
| Committed offset | Vị trí tiếp theo cần đọc đã được group lưu |
| Offset trong transaction | Offset chưa được xác nhận cho đến khi transaction commit |

Kafka commit giá trị offset của **record tiếp theo**. Nếu record offset 100 đã xử lý xong, giá trị commit tương ứng thường là 101.

Không tự gọi consumer.seek hoặc consumer.commitSync trong listener đang được container giao dịch quản lý nếu chưa có thiết kế rất cụ thể. Những thao tác đó có thể gây lệch trạng thái với transaction manager.

## 14. read_committed và output của transaction abort

Một downstream consumer muốn chỉ nhìn những Kafka records đã commit cần:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

Sự khác biệt:

~~~text
Kafka transaction T1:
  publish A
  publish B
  abort

Consumer read_committed:
  không trả A, B của T1

Consumer read_uncommitted:
  có thể nhìn A, B dù T1 đã abort
~~~

Kafka giữ metadata giao dịch và transaction markers. Record của giao dịch abort không nhất thiết bị xóa khỏi log ngay; read_committed filter chúng theo transaction state.

Một open transaction có thể ảnh hưởng tới Last Stable Offset và thời điểm read_committed consumer được nhìn các record phía sau. Vì vậy, transaction quá dài có thể tăng apparent consumer lag và latency, ngay cả khi consumer vẫn poll bình thường.

read_committed không tự biến mọi side effect downstream thành exactly-once, nhưng nó là điều kiện quan trọng khi consumer đọc output transactional.

## 15. Database rollback khác Kafka rollback

Đây là ranh giới dễ gây hiểu nhầm nhất.

~~~text
@KafkaListener
      |
      +--> Update database và commit thành công
      |
      +--> Send Kafka output
      |
      +--> Throw exception
                |
                v
        Kafka transaction abort
                |
                +--> Kafka output bị abort
                +--> Input offset chưa commit
                +--> Database có thể vẫn đã commit
~~~

Kafka transaction manager không tự rollback transaction của PostgreSQL/MySQL hoặc REST API. Kể cả khi phối hợp hai Spring transaction managers, **không mặc định có một transaction XA/2PC** bảo đảm hai resource commit/rollback nguyên tử trong mọi tình huống. Một resource có thể commit trước khi resource còn lại thất bại.

Các cơ chế bảo vệ:

1. **Idempotent consumer:** mỗi event có eventId ổn định; không áp dụng lại side effect đã hoàn tất.
2. **Transactional inbox:** ghi event đã xử lý và cập nhật domain trong cùng database transaction.
3. **Transactional outbox:** lưu domain change và outbox event trong cùng database transaction; publisher riêng gửi ra Kafka.
4. **Reconciliation:** định kỳ đối chiếu trạng thái database và Kafka output.
5. **Compensating action:** thực hiện nghiệp vụ bù trừ nếu giao dịch ngoài Kafka đã hoàn tất và không thể rollback.

Ví dụ inbox idempotency:

~~~java
@Transactional("transactionManager")
public void processOrder(OrderCreated event) {

    boolean firstTime =
            processedEventRepository.insertIfAbsent(event.eventId());

    if (!firstTime) {
        return;
    }

    orderRepository.applyCreation(event);
}
~~~

insertIfAbsent đại diện thao tác sử dụng unique constraint trên eventId. Cả việc ghi processed event và cập nhật order cần cùng database transaction. Đừng chỉ lưu event ID trong bộ nhớ JVM vì nó không bền qua restart.

## 16. Kafka exactly-once có phạm vi nào?

Trong luồng Kafka-to-Kafka, nếu input offset và output record nằm cùng Kafka transaction, và downstream đọc bằng read_committed, hệ thống có thể đạt exactly-once semantics cho các thay đổi Kafka được quản lý.

Nhưng:

- Listener method vẫn có thể được gọi lại sau abort, crash hoặc rebalance.
- Database có thể bị cập nhật hai lần nếu không có idempotency.
- Email đã gửi hoặc HTTP call đã hoàn tất không thể bị Kafka abort hoàn tác.
- Recovery sang DLT có thể gặp duplicate nếu bước publish và commit offset không đồng bộ an toàn.
- Nếu downstream dùng read_uncommitted, nó có thể đọc output thuộc transaction abort.

Không tuyên bố exactly-once end-to-end nếu chưa liệt kê toàn bộ resource có side effect và cách chúng được bảo vệ.

## 17. Transactional ID, fencing và lỗi fatal

Kafka producer dùng transactional.id để coordinator nhận diện producer, transaction và epoch. Nếu hai producer đang hoạt động sử dụng trùng transactional.id, producer cũ có thể bị fenced khi producer khác tạo epoch mới.

~~~text
Instance A: transactional.id = order-tx-0
        |
        +--> Begin transaction
        |
Instance B: cùng transactional.id
        |
        v
Kafka coordinator cấp epoch mới
        |
        v
Instance A bị fenced
        |
        v
Không thể commit như một lỗi mạng bình thường
~~~

Fencing bảo vệ hệ thống khỏi hai producer cùng danh tính giao dịch hoạt động đồng thời. Trong production:

- Quản lý transactionIdPrefix và suffix theo số replica, concurrency và producer cache.
- Tránh cấu hình một transactional.id tĩnh giống nhau trên tất cả pod.
- Theo dõi ProducerFencedException và các lỗi liên quan tới producer epoch.
- Không retry vô hạn trên producer đã bị fenced.
- Đóng/thay producer theo lifecycle do Spring Kafka/ProducerFactory quản lý.
- Kiểm thử rolling deployment và scale-out.

Không coi fencing đơn thuần là lỗi tạm thời để sleep rồi gửi lại bằng chính producer cũ.

## 18. Transaction timeout và poll timeout

Các timeout khác nhau:

| Cấu hình | Ý nghĩa |
|---|---|
| transaction.timeout.ms | Thời gian tối đa giao dịch có thể mở theo transaction coordinator |
| delivery.timeout.ms | Thời gian tổng để producer hoàn thành một send |
| request.timeout.ms | Thời gian chờ một producer request |
| max.poll.interval.ms | Giới hạn thời gian giữa các consumer poll |
| session.timeout.ms | Thời gian phát hiện mất heartbeat theo group protocol |

Nếu listener giữ transaction mở trong thời gian quá dài, transaction có thể timeout và bị abort bởi coordinator. Nếu listener giữ consumer thread trong xử lý hoặc sleep quá lâu, còn có thể vượt max.poll.interval.ms, dẫn đến rebalance.

Không giải quyết bằng cách tăng tất cả timeout lên rất lớn. Nên:

- Giảm thời gian xử lý trong Kafka transaction.
- Giới hạn kích thước batch.
- Áp timeout cho API/database.
- Phân loại lỗi tạm thời và lỗi cố định.
- Retry hữu hạn, dùng recovery/DLT cho poison pill.
- Với retry kéo dài hàng giờ, dùng luồng retry bền vững riêng thay vì giữ transaction mở.
- Kiểm tra non-blocking retry có tương thích với transactional listener container của phiên bản Spring Kafka hay không.

## 19. DefaultErrorHandler và AfterRollbackProcessor

| Thành phần | Khi nào hữu ích |
|---|---|
| KafkaTransactionManager | Quản lý Kafka producer transaction |
| KafkaTemplate.executeInTransaction | Gói nhiều output sends vào transaction cục bộ |
| DefaultErrorHandler | Retry/recovery trong listener container thông thường |
| DefaultAfterRollbackProcessor | Seek, retry và recovery sau transactional container rollback |
| DeadLetterPublishingRecoverer | Xuất record không phục hồi được sang DLT |
| @RetryableTopic | Non-blocking retry qua retry topic; cần kiểm tra giới hạn transaction |

Với transactional listener, exception phải được framework nhận thấy để rollback xảy ra. Một error handler bắt và trả về bình thường có thể làm giao dịch được commit thay vì abort. Nếu muốn recovery sau rollback, hãy dùng AfterRollbackProcessor đúng vai trò của nó.

## 20. Kiểm thử rollback với Kafka thật

Unit test chỉ gọi trực tiếp method @KafkaListener không xác nhận được Kafka transaction abort hay offset commit. Hãy dùng EmbeddedKafka, Testcontainers hoặc một Kafka cluster tích hợp để thử:

| Kịch bản | Kỳ vọng |
|---|---|
| Listener xử lý thành công | Output commit, offset input tiến |
| Listener ném RuntimeException | Transaction abort, output không hiện với read_committed |
| Lần đầu lỗi, lần sau thành công | Redelivery và output committed theo Kafka transaction |
| Payload sai cố định | Retry có giới hạn rồi DLT |
| DLT publish thất bại | Không xem record đã recovered thành công |
| Crash trước transaction commit | Input có thể redelivery, output chưa commit không hiện |
| Crash sau commit | Output và offsets vẫn đã commit |
| Producer fencing | Lỗi được xử lý theo lifecycle, không commit sai |
| Batch lỗi ở record giữa | Record/batch redelivery theo recovery policy |
| Database commit rồi Kafka abort | Không nhân đôi database side effect |
| Consumer read_uncommitted | Có thể thấy output abort, phơi bày rủi ro |
| Transaction timeout | Abort và recovery hoạt động đúng |

Luồng thử tiêu biểu:

~~~text
1. Publish eventId=evt-1 vào orders.created
2. Listener gửi output, sau đó cố ý ném exception
3. read_committed consumer không thấy output abort
4. AfterRollbackProcessor cho retry record
5. Lần xử lý tiếp theo thành công
6. read_committed consumer thấy output đã commit
7. Input offset được commit đúng
8. Database vẫn không có side effect trùng
~~~

Nên kiểm tra trạng thái output topic, committed offsets, DLT và database. Đếm số lần listener được gọi không đủ để chứng minh Kafka transaction semantics.

## 21. Metrics và vận hành

Các tín hiệu nên quan sát:

| Tín hiệu | Mục đích |
|---|---|
| Transaction abort rate | Xác định số giao dịch thất bại |
| Transaction commit latency | Đo thời gian commit |
| Transaction coordinator errors | Phát hiện lỗi hạ tầng Kafka transaction |
| Producer fencing count | Phát hiện trùng transactional IDs |
| AfterRollbackProcessor retry count | Quan sát redelivery |
| Consumer lag theo partition | Tìm partition bị chặn |
| DLT publish success/failure | Biết recovery có lưu record an toàn |
| Transaction timeouts | Phát hiện giao dịch mở quá lâu |
| Rebalance count | Phát hiện mất ổn định consumer group |
| Duplicate event detection | Đánh giá idempotency ngoài Kafka |
| End-to-end event latency | Đo độ trễ từ input đến output commit |

Tên metric phụ thuộc Kafka client, Spring Kafka, Micrometer và exporter. Một số metric cần ứng dụng tự ghi nhận. Log có cấu trúc nên chứa group ID, topic, partition, offset, eventId, exception class, retry count và kết quả commit/abort/recovery, nhưng không log raw payload nhạy cảm.

Các tình huống cần chú ý:

**Record lặp lại vô hạn:** kiểm tra exception, AfterRollbackProcessor, classifier và DLT. Không retry vô hạn một payload sai cố định.

**Output hiện trong broker nhưng read_committed không đọc được:** kiểm tra transaction state, aborted records và open transactions/Last Stable Offset.

**Database đã cập nhật nhưng Kafka abort:** thiết kế inbox/outbox và idempotency, không trông đợi abort Kafka hoàn tác database.

**Rollback bất thường khi deploy nhiều replica:** kiểm tra transactional ID và producer fencing.

**Transaction timeout trong batch lớn:** kiểm tra batch size, processing time, transaction.timeout.ms và max.poll.interval.ms.

**Có DefaultErrorHandler nhưng không rollback:** kiểm tra exception có bị nuốt trước khi transaction manager quan sát hay không.

**DLT có duplicate:** kiểm tra cửa sổ publish DLT thành công nhưng offset chưa commit; dùng eventId để nhận diện và xử lý lặp.

## 22. Checklist trước khi đưa transactional rollback vào production

- ProducerFactory được bật Kafka transactions đúng cách.
- transactionIdPrefix không gây fencing giữa các instance đang hoạt động.
- KafkaTemplate và KafkaTransactionManager dùng cùng transaction resource phù hợp.
- Listener container thực sự có Kafka-aware transaction manager khi cần consume-process-produce.
- Consumer auto-commit tắt và offset được container quản lý.
- Consumer cần EOS đặt isolation.level=read_committed.
- Exception cần abort được truyền khỏi listener.
- @Transactional có rollback rules phù hợp, kể cả checked exception khi cần.
- Không nhầm DefaultErrorHandler với DefaultAfterRollbackProcessor.
- Retry sau rollback có số lần và backoff hữu hạn.
- Lỗi dữ liệu cố định đi vào recovery/DLT thay vì retry mãi.
- DLT publish lỗi không được coi là recovery thành công.
- Transactional recovery dùng KafkaTemplate/commitRecovered phù hợp nếu được bật.
- Batch listener có chính sách rõ cho lỗi giữa batch.
- Transaction không kéo dài vượt timeout và gây rebalance.
- Database/API side effects dùng inbox/outbox/idempotency hoặc bù trừ.
- Có test abort, crash, commit failure, fencing, DLT failure và redelivery.
- Có monitoring cho rollback, commit, consumer lag và duplicate.
- Đã xác định phạm vi exactly-once của hệ thống.

**Kết luận:** Rollback Kafka transaction làm abort những output Kafka chưa commit và không commit input offsets thuộc transaction đó. Với transactional listener container, AfterRollbackProcessor giúp retry hoặc recover những record bị ảnh hưởng. Độ tin cậy không chỉ đến từ lệnh abortTransaction mà còn từ cấu hình transaction manager, exception propagation, consumer isolation level, DLT và cách bảo vệ side effects bên ngoài Kafka.

