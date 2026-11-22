# read-process-write exactly once

Trong hệ thống Spring Kafka, một luồng phổ biến là **đọc record từ topic đầu vào, xử lý nghiệp vụ và ghi record kết quả sang topic đầu ra**. Nếu ứng dụng bị crash, broker mất kết nối hoặc consumer group rebalance đúng giữa các bước, cùng một record đầu vào có thể được đọc lại. Khi đó, câu hỏi quan trọng không chỉ là consumer xử lý bao nhiêu lần, mà là **kết quả cuối cùng có bị nhân đôi hoặc bị mất hay không**.

Kafka cung cấp cơ chế **exactly-once semantics (EOS)** cho luồng đọc–xử lý–ghi mà các thao tác liên quan đều nằm trong Kafka. Spring Kafka hỗ trợ phối hợp producer transaction với offset của consumer group để việc xuất bản output và việc ghi nhận tiến độ tiêu thụ diễn ra trong **cùng một Kafka transaction**.

Cần hiểu rõ phạm vi: EOS không có nghĩa phương thức listener chỉ được gọi đúng một lần. Listener có thể chạy lại sau lỗi. Điều Kafka transaction bảo đảm là **output đã commit và offset đã commit cùng thành công hoặc cùng không có hiệu lực** trong phạm vi giao dịch Kafka, khi hệ thống được cấu hình đúng. Side effect trên database, email, HTTP API và các dịch vụ khác không tự động thuộc cùng transaction đó.

## 1. Bài toán: đọc, xử lý, rồi ghi có những cửa sổ lỗi nào?

Giả sử service order-validator tiêu thụ orders.created và tạo orders.validated.

    orders.created
          |
          v
    Consumer poll record A
          |
          v
    Validate A
          |
          v
    Producer send result X
          |
          v
    Consumer commit source offset

Nếu chỉ dùng producer bình thường và commit offset riêng, có ít nhất hai kiểu lỗi.

**Ghi output xong, chưa commit offset:**

    Poll A -> Process A -> Write X thành công
                              |
                              v
                        Crash trước commit
                              |
                              v
                        Consumer đọc lại A
                              |
                              v
                        Write X lần thứ hai

Output có thể bị nhân đôi vì Kafka consumer group chưa biết A đã được xử lý.

**Commit offset trước, chưa ghi output:**

    Poll A -> Commit offset A
                    |
                    v
             Crash trước write X
                    |
                    v
            Restart đọc record sau A

Lần này output X có thể bị mất vì consumer không còn đọc lại A theo offset đã commit.

Nếu output và offset được commit **nguyên tử trong Kafka transaction**, hai cửa sổ lỗi trên được xử lý theo một hợp đồng thống nhất: hoặc cả output và offset đều committed, hoặc transaction bị abort và record đầu vào vẫn có đường redelivery.

## 2. “Exactly once” áp dụng cho đối tượng nào?

Cụm từ exactly once dễ gây hiểu sai vì hệ thống có nhiều lớp.

| Đối tượng | Điều EOS Kafka bảo đảm | Điều EOS Kafka không tự bảo đảm |
|---|---|---|
| Output Kafka records | Output thuộc transaction commit được hiển thị cho read_committed consumer | Không ngăn các ứng dụng khác cố ý publish một event nghiệp vụ mới có cùng nội dung |
| Consumer group offsets | Offset được ghi cùng transaction chứa output | Không ngăn listener được gọi lại trước khi transaction commit |
| Xử lý in-memory | Có thể chạy lại mà output Kafka đã abort không bị coi là committed | Không bảo đảm hàm Java chỉ chạy một lần |
| Database | Không nằm trong atomicity của Kafka transaction | Không tự rollback/commit cùng Kafka |
| HTTP/payment/email | Không nằm trong atomicity của Kafka transaction | Không chống gửi request, thanh toán hoặc email trùng |
| Consumer phía sau | Có thể chỉ thấy transaction đã commit nếu read_committed | read_uncommitted có thể nhìn thấy record thuộc transaction đã abort |

EOS cho luồng read-process-write cần được diễn giải ở ranh giới hệ thống: **dữ liệu đầu ra Kafka và tiến độ đọc Kafka có quan hệ nguyên tử**. Nếu xử lý chỉ là phép biến đổi từ event đầu vào thành event đầu ra, đây là nền tảng rất mạnh để tránh mất hoặc phát trùng output do retry sau crash.

Một record có thể được listener thử xử lý hai lần, nhưng nếu lần đầu thuộc transaction đã abort thì consumer read_committed ở downstream không nhận output của lần đó như một kết quả hợp lệ.

## 3. Ba thao tác trong một Kafka transaction

Một giao dịch read-process-write thành công gồm ba hoạt động logic:

1. Consumer đọc input record bằng poll.
2. Transactional producer gửi output records tới Kafka.
3. Offset của consumer group được gửi **vào chính transaction** trước khi commit.

Sơ đồ:

    Transaction T1 bắt đầu
          |
          v
    Input: orders.created-0@120
          |
          v
    Process -> OrderValidated
          |
          v
    Produce: orders.validated
          |
          v
    Send source offset=121 to transaction
          |
          v
    commitTransaction()
          |
          +---- Output X committed
          |
          +---- Source offset 121 committed

Nếu transaction abort:

    abortTransaction()
          |
          +---- Output X trong T1 bị đánh dấu aborted
          |
          +---- Source offset 121 không commit bởi T1
          |
          +---- Input offset 120 có thể được xử lý lại

**Offset 121** là vị trí tiếp theo sau record ở offset 120. Commit offset không phải ghi “record 120”, mà là ghi vị trí tiếp tục tiêu thụ.

Producer transaction trong Kafka phối hợp nhiều partition/topic và offset trong cùng transaction. Không cần output nằm trên cùng partition với input; tuy nhiên ordering, phân bổ partition và throughput vẫn cần được thiết kế riêng.

## 4. Vì sao idempotent producer chưa đủ?

Kafka producer có cơ chế idempotence để giảm nguy cơ duplicate khi producer retry cùng một batch do phản hồi mạng không chắc chắn.

Ví dụ producer đã gửi batch tới broker, nhưng response bị mất. Nếu producer retry, idempotent producer dùng producer identity/sequence để tránh ghi lặp batch trong phạm vi được hỗ trợ.

Tuy nhiên, **idempotent producer không tự kết nối output với consumer offset**.

    Read A
    Send X bằng idempotent producer
    Crash trước offset commit
    Restart -> Read A lần nữa
    Send X trong lần xử lý mới

Hai lần xử lý có thể tạo hai lần send nghiệp vụ khác nhau. Idempotence ở producer không tự biết chúng cùng bắt nguồn từ input A. Cần transaction chứa cả output và offset để tránh khoảng trống giữa write và commit.

Kafka transactions dựa trên các cơ chế producer idempotence, transaction coordination và fencing; chúng cung cấp mức nhất quán rộng hơn idempotent send đơn lẻ.

## 5. Prerequisites cho exactly-once read-process-write

Các điều kiện chính:

- Broker Kafka hỗ trợ transactions và có cấu hình transaction state log phù hợp với môi trường.
- Producer output được khởi tạo dưới dạng **transactional producer**, có transactional.id hợp lệ.
- Consumer tự động commit offset được tắt, để offset được đưa vào Kafka transaction.
- Listener container được cấu hình dùng Kafka transaction manager hoặc cơ chế transactional tương ứng.
- Output được gửi bằng KafkaTemplate tham gia transaction do container quản lý.
- Consumer downstream cần dùng **isolation.level=read_committed** nếu muốn không thấy output thuộc transaction đã abort.
- Mọi topic/partition sử dụng có khả năng tiếp nhận record và đáp ứng quyền truy cập.
- Transaction ID được cấp phát đủ phân biệt giữa các instance hoạt động đồng thời.
- Thời gian transaction, thời gian xử lý, retry/backoff và poll interval tương thích với nhau.

Trên môi trường development chỉ có một broker, có thể cần điều chỉnh các tham số replication của transaction state log để khởi tạo transaction. Production cần cấu hình replication/min ISR thích hợp với khả năng chịu lỗi, không áp dụng nguyên thiết lập một broker cho cluster thực.

Nếu một phần luồng ghi dữ liệu qua producer không tham gia transaction, không thể coi phần đó có atomicity chỉ nhờ listener container được đánh dấu transactional.

## 6. Cấu hình Spring Boot để bật Kafka transaction

Ví dụ cấu hình nền tảng với Spring Boot/Spring Kafka hiện đại:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    consumer:
      group-id: order-validator
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        isolation.level: read_committed
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
        spring.json.use.type.headers: false

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      transaction-id-prefix: order-validator-tx-
      properties:
        acks: all
        enable.idempotence: true

    listener:
      ack-mode: record
~~~

Ý nghĩa các thuộc tính trọng tâm:

| Thuộc tính | Vai trò |
|---|---|
| producer.transaction-id-prefix | Kích hoạt các transactional producer do Spring quản lý |
| consumer.enable-auto-commit=false | Không commit offset tự động, tách khỏi transaction |
| consumer.properties.isolation.level=read_committed | Bỏ qua output của transaction bị abort và chưa commit |
| producer.properties.acks=all | Đòi hỏi acknowledgment của các replica theo cấu hình ISR |
| producer.properties.enable.idempotence=true | Idempotent producer hỗ trợ an toàn retry |
| listener.ack-mode | Điều khiển cách listener container ghi nhận tiến độ trước khi gửi offset vào transaction |

Với Spring Boot có auto-configuration thích hợp, cấu hình transaction-id-prefix có thể làm Boot tạo KafkaTransactionManager, rồi gắn nó vào listener container factory mặc định. **Không giả định mọi custom factory đều được cấu hình giống factory mặc định**. Nếu ứng dụng tự xây ConcurrentKafkaListenerContainerFactory, phải kiểm tra transaction manager thực sự được gắn vào container đó.

Trong production, không để mọi pod có cùng transaction-id-prefix nếu cách cấp phát transactional.id từ prefix có nguy cơ trùng giữa các instance. Prefix nên mang identity instance hoặc được quản lý sao cho transactional.id duy nhất cho các producer đang hoạt động.

## 7. Ví dụ @KafkaListener đọc rồi ghi trong transaction

Giả sử hệ thống có hai event Java record:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        long amount) {
}

public record OrderValidated(
        String eventId,
        String orderId,
        String validationStatus) {
}
~~~

Service xử lý:

~~~java
@Service
public class OrderValidationListener {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public OrderValidationListener(
            KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        id = "orderValidationListener",
        topics = "orders.created",
        groupId = "order-validator"
    )
    public void onOrder(
            ConsumerRecord<String, OrderCreated> record) {

        OrderCreated event = record.value();

        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId missing");
        }

        OrderValidated output = new OrderValidated(
            event.eventId(),
            event.orderId(),
            "VALID"
        );

        kafkaTemplate.send(
            "orders.validated",
            event.orderId(),
            output
        );
    }
}
~~~

Đoạn code này giả định KafkaTemplate và @KafkaListener container cùng tham gia Kafka transaction, được cấu hình bằng transaction-capable ProducerFactory và KafkaTransactionManager. Nếu thiếu cấu hình này, code trông giống consume-process-produce nhưng **không có bảo đảm atomic offset+output**.

Khi listener thành công, container phối hợp gửi offset đã xử lý vào transaction rồi commit. Khi listener ném exception, container abort transaction; output chưa committed không có hiệu lực đối với downstream read_committed và input có thể được giao lại.

Trong Spring Kafka, ranh giới transaction thường gắn với một lượt poll của container, ngay cả khi listener là record listener, tùy phiên bản và cấu hình. Không suy luận rằng mỗi lời gọi method listener mặc nhiên tạo một transaction độc lập.

## 8. Có cần @Transactional trên listener không?

**Không nên tự thêm @Transactional chỉ để “bật EOS”** mà chưa xác định transaction manager được chọn.

Trong mô hình container-managed Kafka transaction:

1. Listener container mở Kafka transaction.
2. Container gọi listener.
3. KafkaTemplate tham gia transaction đang mở.
4. Container gửi offset vào transaction và commit/abort.

Listener method có thể không cần annotation @Transactional. Nếu dùng @Transactional không chỉ định manager trong ứng dụng có cả DataSourceTransactionManager/JpaTransactionManager và KafkaTransactionManager, annotation có thể chọn transaction manager không như mong đợi.

Ví dụ dễ gây hiểu lầm:

~~~java
@Transactional
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    orderRepository.save(...);
    kafkaTemplate.send("orders.validated", ...);
}
~~~

Nếu annotation chọn JPA transaction manager, nó không tự làm database và Kafka trở thành một distributed transaction nguyên tử. Container Kafka có thể đang mở transaction độc lập, hoặc hoàn toàn không có Kafka transaction tùy cấu hình.

Hãy xác định **ai bắt đầu transaction**, **transaction manager nào được sử dụng**, và **offset được send vào transaction bằng cách nào**. Không dựa chỉ vào sự hiện diện của annotation.

## 9. Vai trò của KafkaTransactionManager

KafkaTransactionManager là transaction manager do Spring Kafka cung cấp cho Kafka producer transaction. Nó làm việc với ProducerFactory có hỗ trợ transactional producer.

Ví dụ tạo bean tường minh:

~~~java
@Bean
KafkaTransactionManager<String, Object> kafkaTransactionManager(
        ProducerFactory<String, Object> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Khi tùy chỉnh listener factory, cần gắn manager vào ContainerProperties bằng API của phiên bản Spring Kafka cụ thể.

Ví dụ định hướng:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
transactionalListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        KafkaTransactionManager<String, Object> transactionManager) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);

    // Spring Kafka 3.x có các API cấu hình transaction manager
    // trên ContainerProperties; dùng đúng tên method của version.
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(transactionManager);

    return factory;
}
~~~

Tên setter có thể khác giữa các dòng Spring Kafka (một số phiên bản cũ dùng setTransactionManager). Ví dụ trên minh họa cách nối manager, không thay thế việc xác định chính xác phiên bản dependency.

Nếu ứng dụng có nhiều KafkaTemplate hoặc nhiều ProducerFactory, cần đảm bảo template dùng để gửi output trong listener được gắn với producer factory phù hợp để tham gia transaction. Một KafkaTemplate được tạo từ producer factory không liên quan có thể gửi ngoài transaction nếu ứng dụng cấu hình sai.

## 10. Offset được gửi vào transaction như thế nào?

Kafka Java client có API sendOffsetsToTransaction() trên Producer. Ở phiên bản Kafka hiện đại, API nhận map offset và ConsumerGroupMetadata.

Ví dụ mang tính mô tả ở mức Kafka client:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets =
        Map.of(
            new TopicPartition(record.topic(), record.partition()),
            new OffsetAndMetadata(record.offset() + 1)
        );

producer.sendOffsetsToTransaction(
    offsets,
    consumer.groupMetadata()
);
~~~

Đoạn này không phải một listener hoàn chỉnh. Nếu tự dùng KafkaConsumer và KafkaProducer, ứng dụng còn phải quản lý beginTransaction(), send(), commitTransaction(), abortTransaction(), poll(), error handling và seek/redelivery. KafkaConsumer không thread-safe; không dùng consumer.groupMetadata() hoặc thao tác commit từ thread bất kỳ.

Trong mô hình Spring Kafka container-managed transaction, **container tự thực hiện việc đưa offset đã xử lý vào transaction**. Ứng dụng không nên tự gọi sendOffsetsToTransaction() thêm lần nữa cho cùng flow nếu không có lý do và thiết kế rõ ràng.

Mục đích của consumer group metadata là giúp broker gắn offset commit với group membership. Trong EOS v2, metadata này hỗ trợ fencing và xử lý đúng khi assignment/rebalance thay đổi.

## 11. read_committed quan trọng như thế nào?

Kafka transaction có thể ghi dữ liệu vào log rồi abort. Record thuộc transaction bị abort vẫn có thể tồn tại vật lý trong log tới khi hết retention, nhưng không được coi là output committed.

Consumer có hai isolation level:

| Isolation level | Consumer thấy gì? |
|---|---|
| read_uncommitted | Có thể thấy record của transaction đã commit, chưa commit hoặc đã abort |
| read_committed | Chỉ nhận record committed và record non-transactional phù hợp; loại bỏ record thuộc transaction abort |

Ví dụ:

    Transaction T1:
      write X1
      write X2
      abort

    Transaction T2:
      write Y1
      commit

    read_uncommitted:
      có thể quan sát X1, X2, Y1

    read_committed:
      chỉ quan sát Y1 (và record non-transactional khác)

Downstream muốn tận dụng EOS phải dùng read_committed khi đọc output transactional. Nếu một hệ thống phân tích vẫn dùng read_uncommitted, nó có thể nhìn thấy dữ liệu mà nghiệp vụ đã rollback, rồi tính tổng/đồng bộ sai.

Một hệ quả vận hành: read_committed consumer chỉ đọc tới **last stable offset (LSO)**, bị giới hạn bởi transaction đang mở sớm nhất. Một transaction mở lâu hoặc bị treo có thể làm downstream lag/độ trễ tăng dù producer đã gửi nhiều record khác. Cần theo dõi transaction duration và transaction timeout.

## 12. Rollback và redelivery sau lỗi

Trong listener giao dịch, khi method ném exception, container cần abort transaction rồi điều chỉnh consumer để các record chưa xử lý thành công có thể được giao lại.

Chuỗi điển hình:

    poll input A
       |
       v
    Begin T1
       |
       v
    Listener xử lý A
       |
       v
    KafkaTemplate.send X
       |
       v
    Exception trước commit
       |
       v
    Abort T1
       |
       v
    AfterRollbackProcessor
       |
       v
    Seek/reposition record cần xử lý lại
       |
       v
    Begin T2 -> Redeliver A

Trong Spring Kafka, DefaultAfterRollbackProcessor thường được dùng để điều phối redelivery/backoff/recovery sau transaction rollback. Nó khác DefaultErrorHandler ở container không transactional.

Khi rollback xảy ra, output Kafka thuộc T1 không được downstream read_committed coi là committed, và offset input gửi vào T1 cũng không được commit. Redelivery có thể làm listener chạy thêm lần nữa, nhưng transaction mới chỉ cho ra output committed khi lần xử lý sau thành công.

## 13. Đừng nuốt exception trong listener

Một cách phá vỡ EOS rất phổ biến là bắt exception rồi chỉ ghi log:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    try {
        orderService.validate(event);
        kafkaTemplate.send("orders.validated", event);
    }
    catch (Exception exception) {
        log.error("Validation failed", exception);
        // Không throw -> container có thể xem listener đã xử lý xong.
    }
}
~~~

Trong ví dụ này, container không biết logic nghiệp vụ đã thất bại. Nó có thể tiếp tục gửi offset vào Kafka transaction và commit. Input sẽ không được redelivery như kỳ vọng, dù output có thể không tồn tại.

Nếu lỗi phải dẫn tới rollback, để exception lan ra:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    try {
        orderService.validate(event);
        kafkaTemplate.send("orders.validated", event);
    }
    catch (Exception exception) {
        log.error("Validation failed", exception);
        throw exception;
    }
}
~~~

Nếu muốn xử lý một record lỗi rồi tiếp tục, hãy thiết kế recoverer/DLT và cách commit offset recovered một cách có chủ đích. Không thay thế recovery bằng việc nuốt exception để “tránh retry”.

## 14. Transaction boundary: một record hay một poll batch?

Với record listener, method có thể được gọi nhiều lần trong một vòng poll. Điều đó không có nghĩa mỗi record luôn có một transaction riêng. Trong Spring Kafka, container transactional thường quản lý transaction ở phạm vi bản ghi do poll nhận, tùy loại listener và cấu hình.

Ví dụ:

    poll() -> A, B, C

    Transaction T1 begin
      listener(A) -> send XA
      listener(B) -> send XB
      listener(C) -> exception
    T1 abort

Nếu cả A, B và C thuộc cùng transaction T1, các output XA/XB cũng abort. Các input đã xử lý trong transaction chưa commit có thể được giao lại theo offset an toàn.

Nếu cấu hình sử dụng ranh giới transaction khác, phạm vi replay cũng khác. Vì thế khi phân tích duplicate và throughput cần xác định transaction boundary thực tế thay vì giả định mỗi call là một transaction.

Batch listener còn phải quan tâm cách xác định record lỗi trong batch, vì một exception chung có thể khiến cả batch phải xử lý lại. Nếu xử lý trong batch có side effect bên ngoài Kafka, idempotency là bắt buộc để tránh lặp thao tác.

## 15. Retry, backoff và poison pill trong luồng EOS

Một record thất bại liên tục có thể khiến partition bị chặn và transaction bị abort lặp lại. Các nguyên nhân có thể là:

- Dependency HTTP tạm unavailable.
- Database deadlock hoặc timeout.
- Event sai schema hoặc thiếu trường bắt buộc.
- Bug NullPointerException hoặc logic không xử lý được trạng thái mới.
- Không đủ quyền produce topic output.
- Transaction producer bị fenced hoặc timeout.

Không nên retry vô hạn với cùng khoảng chờ ngắn. Có thể dùng DefaultAfterRollbackProcessor với FixedBackOff hoặc ExponentialBackOff và recoverer.

Ví dụ minh họa:

~~~java
DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
            (record, exception) -> {
                log.error(
                    "Could not process record {}-{}@{}",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    exception
                );
            },
            new FixedBackOff(1_000L, 3L)
        );
~~~

Đoạn trên **chỉ log**, nên không phải chính sách recovery production đầy đủ. Sau khi hết retry, nếu cho phép bỏ qua record mà không lưu bền vững, nghiệp vụ có thể mất dữ liệu. Nên dùng DLT hoặc một cơ chế recovery đáng tin cậy.

Chọn thời gian backoff theo thời gian phục hồi dependency, giới hạn SLA và max.poll.interval.ms. Lỗi dữ liệu cố định thường không thể tự phục hồi bằng retry.

## 16. DLT và “exactly once” khi recovery

Một record có thể được xử lý nhiều lần nhưng luôn thất bại. Khi hết retry, hệ thống thường chuyển nó sang DLT để không chặn partition vô thời hạn.

Mục tiêu:

    T1:
      Read bad record A
      Listener fails
      Abort T1

    Recovery transaction T2:
      Publish A -> orders.created.DLT
      Send input offset past A to transaction
      Commit T2

Nếu DLT record và offset source cùng commit trong một transaction mới, chúng có tính nguyên tử tương tự read-process-write. Nếu recovery transaction abort, source offset không được ghi nhận, nên record còn khả năng được xử lý lại.

Với Spring Kafka, DefaultAfterRollbackProcessor hỗ trợ các tùy chọn như commitRecovered và KafkaOperations trong những phiên bản nhất định. Cấu hình phải gắn đúng transactional KafkaTemplate, processor và listener transaction manager.

Ví dụ định hướng:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltKafkaTemplate);

DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
            recoverer,
            new FixedBackOff(1_000L, 3L)
        );

// Bật khả năng commit offset recovered theo API hỗ trợ.
processor.setCommitRecovered(true);

// Đồng thời cần cung cấp KafkaOperations phù hợp,
// cấu hình processor/container cho recovery transaction
// theo đúng Spring Kafka version đang sử dụng.
~~~

Không suy luận rằng gọi setCommitRecovered(true) một mình đủ để DLT send và source offset commit nguyên tử. Cần xác minh khả năng tham gia transaction và đường xử lý lỗi DLT send.

Nếu broker không nhận DLT record hoặc producer serializer không xử lý được payload lỗi, recoverer phải báo lỗi thay vì làm container commit source offset như đã recover thành công.

## 17. Side effect database không nằm trong Kafka transaction

Giả sử listener vừa ghi PostgreSQL vừa publish Kafka output:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    orderRepository.save(toEntity(event));
    kafkaTemplate.send("orders.validated", validate(event));
}
~~~

Nếu database commit thành công nhưng Kafka transaction abort, input sẽ redelivery. Lần xử lý lại có thể ghi cùng order lần nữa hoặc cập nhật counter hai lần.

Kafka EOS không tạo transaction phân tán giữa Kafka và database. Ngay cả khi dùng @Transactional và sắp xếp thứ tự commit, vẫn có những cửa sổ lỗi giữa hai resource manager.

Các giải pháp:

**Idempotent update:** ghi bản ghi bằng khóa duy nhất theo eventId, hoặc upsert có điều kiện.

**Transactional Inbox:** trong một database transaction, vừa đánh dấu eventId đã xử lý, vừa cập nhật dữ liệu nghiệp vụ. Khi Kafka redelivery, consumer thấy eventId cũ và không lặp side effect.

**Transactional Outbox:** lưu event đầu ra cùng thay đổi nghiệp vụ trong database, rồi một publisher riêng gửi outbox event sang Kafka. Cần thiết kế duplicate handling/idempotency của publisher và downstream.

**Saga/compensation:** nếu workflow gồm nhiều dịch vụ ngoài Kafka, cần điều phối trạng thái và các bước bù thay vì trông chờ rollback toàn hệ thống.

Nếu business side effect là thanh toán hoặc gửi email, bắt buộc sử dụng idempotency key hoặc trạng thái gửi bền vững. Việc Kafka output không trùng không chứng minh khách hàng không bị tính phí/gửi email hai lần.

## 18. Transactional ID, producer fencing và scale nhiều instance

Mỗi transactional producer được Kafka nhận diện qua transactional.id. Broker sử dụng producer ID/epoch và transaction coordinator để chống một producer cũ tiếp tục commit sau khi producer mới cùng transactional.id đã chiếm quyền.

**Producer fencing** có vai trò quan trọng khi instance cũ bị treo, network partition hoặc restart. Producer cũ có thể nhận lỗi như ProducerFencedException và phải ngừng sử dụng producer đó theo cơ chế của framework.

Trong môi trường nhiều pod:

    Pod A: transaction-id-prefix = order-validator-A-
    Pod B: transaction-id-prefix = order-validator-B-
    Pod C: transaction-id-prefix = order-validator-C-

Mỗi pod cần namespace transactional ID tránh va chạm với pod đang hoạt động khác. Spring Kafka có cách tạo transactional.id từ prefix và cache producer, nhưng identity của prefix vẫn phải được quản lý khi scale.

Không gán cùng transactional.id cố định cho tất cả pod. Nếu hai producer hoạt động cùng ID, chúng có thể fencing lẫn nhau và làm transaction liên tục abort.

Khi rolling deployment, có thể dùng identity gắn với pod/instance và kế hoạch lifecycle để tránh producer cũ đang sống mà instance mới dùng cùng transactional.id. Đồng thời cần dừng container đủ graceful để transaction hoàn tất hoặc abort có kiểm soát.

## 19. EOS v2 trong Spring Kafka

Ở các dòng Spring Kafka hiện đại, cơ chế **EOSMode.V2** là chế độ được sử dụng cho Kafka exactly-once phù hợp với khả năng của Kafka clients/brokers mới.

Một đặc điểm quan trọng là producer gửi offset vào transaction cùng consumer group metadata, hỗ trợ fencing và tính đúng đắn khi consumer group thay đổi assignment. Cơ chế này cải thiện cách điều phối producer/consumer group so với các mode lịch sử.

Không nên copy cấu hình EOS mode cũ từ một blog dùng phiên bản Spring Kafka khác. Nhiều enum, property và API transaction đã thay đổi khi Spring Kafka tiến hóa. Hãy kiểm tra version đang dùng và contract của KafkaTransactionManager, listener container và ProducerFactory.

Dù dùng EOS v2, yêu cầu read_committed ở downstream, transaction-aware KafkaTemplate, offset gửi trong transaction và idempotency cho hệ thống bên ngoài vẫn giữ nguyên.

## 20. Transaction timeout và max.poll.interval.ms

Các timeout ảnh hưởng tới tính sẵn sàng của luồng EOS:

| Tham số | Ý nghĩa | Rủi ro nếu cấu hình sai |
|---|---|---|
| transaction.timeout.ms | Thời gian tối đa Kafka transaction được phép tồn tại | Transaction dài bị abort do timeout |
| max.poll.interval.ms | Thời gian tối đa giữa các lần poll | Consumer có thể mất assignment nếu xử lý quá lâu |
| request.timeout.ms | Thời gian chờ phản hồi request | Lỗi timeout/cắt ngắn giao tiếp |
| delivery.timeout.ms | Giới hạn thời gian delivery của producer | Producer send lỗi khiến transaction abort |
| producer max.in.flight.requests.per.connection | Số request chưa được xác nhận | Cần tương thích với idempotence và yêu cầu throughput |
| shutdown timeout | Thời gian chờ listener/container dừng | Pod bị kill giữa transaction nếu quá ngắn |

Nếu một poll trả nhiều record và listener xử lý chậm, transaction có thể kéo dài. Trong khi transaction đang mở, downstream read_committed có thể chờ LSO và throughput thực tế giảm.

Không chỉ tăng timeout để che giấu xử lý chậm. Cần đo thời gian từng record, số record mỗi poll, latency của dependency, thời gian commit và khả năng phân chia work theo partition.

## 21. Thứ tự record, concurrency và partition

Kafka bảo đảm thứ tự theo partition, không phải theo toàn bộ topic. Trong consumer group, mỗi partition được assign cho tối đa một consumer tại một thời điểm, và Spring Kafka concurrency tạo nhiều consumer song song để tăng throughput.

Ví dụ:

    orders.created: 8 partitions
    deployment: 2 pods
    concurrency per pod: 4
    => tối đa 8 consumer có thể nhận partition

Mỗi child consumer có thể có transactional producer được quản lý theo lifecycle và cache của Spring Kafka. Cần bảo đảm transaction-id prefix không xung đột giữa các instance.

Các lưu ý:

- Tăng concurrency vượt số partition không tạo thêm song song hữu ích.
- Gửi output theo key ổn định nếu downstream cần order theo aggregate.
- Một transaction có thể ghi nhiều output partition, nhưng Kafka không tạo thứ tự toàn cục giữa chúng.
- Nếu listener tự chuyển task sang executor và trả về ngay, container có thể commit offset trước khi task hoàn tất; EOS cho output phụ thuộc task đó có thể bị phá vỡ.
- Không dùng KafkaConsumer đồng thời từ nhiều thread; container quản lý thread sở hữu consumer.

Với async processing, phải đảm bảo completion được tích hợp vào ranh giới transaction và offset. Chỉ gọi executor.submit() không làm task nền trở thành một phần của Kafka transaction.

## 22. Kafka Streams so với Spring Kafka listener

Kafka Streams có hỗ trợ EOS cho topologies read-process-write bằng cơ chế transaction và quản lý offset/state. Với Kafka Streams, việc cấu hình processing.guarantee phù hợp cho phép runtime phối hợp trạng thái xử lý, changelog và output Kafka trong phạm vi được hỗ trợ.

Spring Kafka listener là mô hình thấp hơn: ứng dụng điều khiển listener và có thể cấu hình KafkaTransactionManager, KafkaTemplate, AfterRollbackProcessor cùng business logic riêng.

| Tiêu chí | Spring Kafka listener | Kafka Streams |
|---|---|---|
| Mô hình | Listener nhận record/batch và chạy code ứng dụng | Topology stream processing |
| Cấu hình EOS | Container transaction + producer/offset | Processing guarantee của Streams |
| State | Do ứng dụng tự quản lý hoặc dùng DB | State stores/changelog của Streams |
| Retry/recovery | Error handler, after-rollback, DLT | Cơ chế lỗi/processing của Streams |
| Side effect ngoài Kafka | Cần idempotency/transaction model khác | Cũng không tự có distributed transaction với DB/API |

Chọn Spring Kafka nếu ứng dụng chủ yếu thực hiện nghiệp vụ tích hợp với service/repository. Chọn Kafka Streams nếu nhu cầu cốt lõi là biến đổi, join, aggregate hoặc xử lý stateful stream theo topology. Đừng coi Streams là giải pháp tự động cho exactly-once side effect ở mọi hệ thống.

## 23. Quan sát tính đúng đắn trong production

Một dashboard chỉ có consumer lag và producer throughput chưa đủ để chứng minh EOS. Cần quan sát cả transaction và kết quả nghiệp vụ.

**Producer transaction**

- Số transaction bắt đầu, commit và abort.
- Transaction duration và tỷ lệ timeout.
- Lỗi producer fencing, coordinator hoặc commit.
- Producer send error và delivery timeout.

**Consumer**

- Committed offset theo group/partition.
- Consumer lag và số lần rebalance.
- Số lần một topic-partition-offset được redeliver.
- Thời gian từ poll đến commit/abort.
- Các lỗi after-rollback và DLT recovery.

**Output**

- Số output committed mà downstream read_committed nhận được.
- Số output eventId trùng được phát hiện.
- Độ trễ end-to-end từ input event đến output visible.
- Số record mắc kẹt trong transaction đang mở hoặc DLT.

**Nghiệp vụ**

- Số eventId được xử lý thành công.
- Số duplicate bị idempotency layer bỏ qua.
- Số side effect ngoài Kafka chạy lại.
- Độ lệch giữa input hợp lệ và output nghiệp vụ kỳ vọng.

Log nên chứa eventId, groupId, topic, partition, offset, transaction/recovery stage và exception class. Không cần ghi payload nhạy cảm hoặc stack trace trong mọi lần retry.

## 24. Kiểm thử read-process-write exactly once

Unit test listener không đủ để xác nhận EOS, vì atomicity giữa producer output và consumer offset phụ thuộc broker transaction coordinator. Nên có integration test dùng broker tương thích với client (Embedded Kafka hoặc Testcontainers).

### 24.1. Happy path

1. Tạo topic input và output.
2. Bật transaction-id-prefix, tắt auto commit, cấu hình listener transactional.
3. Gửi input event A có eventId cố định.
4. Chờ output X được thấy bằng read_committed consumer.
5. Xác nhận consumer group commit offset qua A.
6. Restart consumer và xác nhận không publish thêm X từ cùng input A.

### 24.2. Crash sau send nhưng trước commit

1. Listener gửi output X trong Kafka transaction T1.
2. Chủ động tạo exception trước lúc container commit.
3. Kiểm tra transaction T1 bị abort.
4. Dùng downstream read_committed để xác nhận không thấy X của T1.
5. Cho lần retry xử lý A thành công trong T2.
6. Xác nhận chỉ output committed từ T2 được thấy.
7. Xác nhận offset input chỉ tiến sau T2 commit.

### 24.3. Failure khi commit transaction

1. Mô phỏng broker/coordinator không sẵn sàng trong commit.
2. Quan sát transaction exception/abort theo khả năng của môi trường test.
3. Không suy luận commit chắc chắn thất bại chỉ từ timeout client.
4. Khởi động lại và xác nhận luồng có thể phục hồi mà không tạo kết quả nghiệp vụ trùng trong phạm vi EOS.
5. Nếu có external side effect, kiểm tra idempotency.

### 24.4. read_uncommitted so với read_committed

1. Cố tình tạo transaction có output rồi abort.
2. Dùng hai downstream consumers cùng topic nhưng isolation khác nhau.
3. read_uncommitted có thể đọc record của transaction abort.
4. read_committed không trả record output đã abort như dữ liệu hợp lệ.
5. Kiểm tra log/metric transaction để đối chiếu.

### 24.5. Database side effect và rollback

1. Ghi một row database với eventId A.
2. Sau database commit, làm Kafka transaction abort.
3. Cho input A redelivery.
4. Xác nhận unique constraint hoặc Inbox ngăn ghi lặp.
5. Xác nhận Kafka output cuối cùng committed đúng một lần theo kịch bản.

### 24.6. Poison record và DLT

1. Gửi event vi phạm validation cố định.
2. Kiểm tra backoff/retry hữu hạn sau rollback.
3. Xác nhận DLT publish và source offset commit nếu recovery transaction được cấu hình.
4. Làm DLT producer thất bại và xác nhận input còn khả năng redelivery.
5. Re-drive với eventId gốc và xác nhận không có side effect trùng.

### 24.7. Rebalance trong transaction

1. Tạo nhiều consumer cùng group.
2. Giữ listener đang xử lý rồi dừng một consumer hoặc thay đổi membership.
3. Xác nhận transaction không thể commit sai owner khi cần fencing.
4. Consumer mới đọc từ committed offset an toàn.
5. Xác nhận không mất output Kafka và không có side effect ngoài Kafka vượt idempotency policy.

Các test cần đối chiếu **record đã committed**, **offset thực tế**, **transaction outcome** và **side effect nghiệp vụ**, không chỉ đếm số lần listener method được gọi.

## 25. Các lỗi cấu hình thường gặp

| Sai sót | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ bật enable.idempotence | Offset không atomic với output | Dùng Kafka transaction và send offset cùng transaction |
| Quên transaction-id-prefix | Producer có thể không transactional | Cấu hình transactional ProducerFactory |
| Consumer bật auto commit | Offset có thể đi trước output | Tắt auto commit để container quản lý |
| Downstream dùng read_uncommitted | Đọc output transaction abort | Dùng read_committed |
| @Transactional chọn JPA manager | Nhầm database transaction với Kafka transaction | Kiểm tra transaction manager và container |
| KafkaTemplate không tham gia container transaction | Output ngoài transaction | Dùng template/factory đúng |
| Listener catch exception rồi trả bình thường | Container có thể commit offset dù xử lý lỗi | Rethrow hoặc recovery theo chính sách |
| Transactional ID trùng giữa pod | Producer fencing liên tục | Dùng prefix/identity duy nhất |
| Transaction timeout quá ngắn | Abort do timeout, redelivery nhiều | Đo xử lý và cấu hình timeout thích hợp |
| Async task chạy sau listener return | Commit offset trước side effect | Phối hợp completion với transaction |
| Chỉ log rồi skip poison record | Có thể mất record khỏi nghiệp vụ | DLT/recovery bền vững |
| Coi DB/API là thành phần của Kafka EOS | Ghi side effect trùng khi rollback | Inbox, Outbox, idempotency key |
| Chỉ test happy path | Bỏ sót cửa sổ crash/rebalance | Test abort, fencing, redelivery và DLT |

## 26. Quy trình triển khai EOS vào production

Một cách tiếp cận có kiểm soát:

1. Liệt kê input topic, output topic, consumer group, eventId và các side effect khác Kafka.
2. Xác định ranh giới chính xác cần nguyên tử: Kafka output + input offsets.
3. Cấu hình transaction-capable producer và transaction-id prefix duy nhất theo instance.
4. Tắt consumer auto commit; cấu hình listener container transaction manager.
5. Dùng cùng KafkaTemplate/ProducerFactory tham gia transaction khi gửi output.
6. Đặt read_committed cho các downstream consumer cần bỏ qua output abort.
7. Cấu hình exception propagation, after-rollback, BackOff và DLT recovery.
8. Thiết kế idempotency/Inbox/Outbox cho các thay đổi database hoặc external API.
9. Đặt timeout và graceful shutdown phù hợp với thời gian xử lý.
10. Kiểm thử trên broker test: happy path, abort, redelivery, restart, DLT, rebalance.
11. Triển khai theo từng đợt và đo transaction abort rate, lag, output visible, duplicate.
12. Có runbook xử lý fencing, commit error, poison record và recovery failure.

Không chuyển toàn bộ consumer group sang chế độ transaction chỉ để đạt một nhãn “exactly once” nếu ứng dụng thực chất chỉ ghi database. Khi đó, mô hình Inbox với idempotent update có thể là phần bảo đảm quan trọng hơn Kafka producer transaction. Chọn cơ chế phù hợp với ranh giới nghiệp vụ.

## 27. Kết luận và nguyên tắc ghi nhớ

- **Exactly-once read-process-write** trên Kafka nghĩa là output Kafka và consumer offsets được phối hợp trong một transaction.
- Producer idempotence hữu ích nhưng không thay thế transaction có offset.
- Listener có thể chạy nhiều lần sau crash/abort; đây không mâu thuẫn với EOS của output committed.
- Downstream cần read_committed để không thấy output của transaction đã abort.
- Không nuốt exception nếu cần container rollback.
- DefaultAfterRollbackProcessor và recovery policy quyết định đường redelivery khi lỗi.
- DLT cần được publish và commit offset recovered theo chính sách bền vững; tránh skip âm thầm.
- Transactional.id/prefix phải được quản lý để tránh fencing giữa instance.
- Transaction không tự bảo vệ database, email, HTTP hay payment.
- Với external side effect, dùng Inbox, Outbox, unique constraint hoặc idempotency key.
- Đừng coi @Transactional tự động biến hai resource manager thành một transaction phân tán.
- Kiểm thử cần quan sát broker, offset, isolation level và failure window, không chỉ số lần gọi listener.

Khi thiết kế đúng, Spring Kafka cho phép ứng dụng đọc sự kiện đầu vào, xử lý và xuất bản kết quả với mối quan hệ nguyên tử giữa **output được commit** và **offset input được commit**. Đây là nền tảng của EOS Kafka-to-Kafka: hệ thống có thể retry hoặc redeliver sau lỗi mà không công bố nhiều lần những output đã abort. Với tác vụ nghiệp vụ vượt ra ngoài Kafka, vẫn phải bổ sung idempotency và mô hình nhất quán phù hợp để đạt độ tin cậy end-to-end.
