# Redelivery sau rollback

Trong Spring Kafka, **transaction Kafka** cho phép ứng dụng phối hợp việc ghi record đầu ra và commit offset đầu vào trong cùng một Kafka transaction. Nếu listener xử lý thành công, transaction có thể commit cả output records và offset đã xử lý. Nếu listener thất bại và transaction bị rollback (abort), **offset của record đầu vào không được commit trong transaction đó**, nên record có thể được giao lại cho consumer.

Cơ chế **redelivery sau rollback** không chỉ là một lần gọi lại listener. Nó liên quan đến Kafka consumer position, committed offset, trạng thái transaction trên broker, cách listener container điều chỉnh vị trí đọc, chính sách retry/recovery và khả năng xử lý idempotent. Hiểu đúng ranh giới này giúp tránh hai lỗi nguy hiểm: mất record do đánh dấu đã xử lý quá sớm, và tạo side effect trùng lặp khi record được giao lại.

Trong bài, các ví dụ hướng tới Spring Kafka sử dụng listener container và Kafka transaction manager. API cấu hình có thể khác nhau giữa các phiên bản Spring Kafka; khi áp dụng cần đối chiếu dependency thực tế của dự án.

## 1. Redelivery sau rollback nghĩa là gì?

Xét luồng consume-process-produce:

    Topic orders.created
           |
           v
    Spring Kafka consumer
           |
           v
    @KafkaListener
           |
           +---- xử lý nghiệp vụ
           |
           +---- KafkaTemplate.send("orders.validated")
           |
           v
    Gửi offset đã xử lý vào Kafka transaction
           |
           v
    Commit transaction

Nếu toàn bộ transaction hoàn tất, record kết quả được công bố và offset consumer được commit cùng transaction. Nếu listener ném exception hoặc transaction thất bại trước commit, transaction bị abort.

    Record đầu vào offset 120
           |
           v
    Kafka transaction T1 bắt đầu
           |
           v
    Listener tạo output X
           |
           v
    Listener ném exception
           |
           v
    Abort T1
           |
           +---- Output X không hiển thị với consumer read_committed
           |
           +---- Offset 121 chưa được commit bởi T1
           |
           v
    Consumer được định vị để đọc lại
           |
           v
    Redelivery record offset 120

Record được giao lại có cùng topic, partition, offset và nội dung gốc theo dữ liệu còn trong Kafka log. Tuy nhiên, **nó không nhất thiết được giao lại ngay lập tức**: container có thể áp dụng backoff, xử lý rebalance hoặc phải chờ sự cố broker/dependency được khắc phục.

Redelivery là kết quả có thể xảy ra khi offset chưa được commit; nó không phải lời hứa rằng mọi lỗi luôn tạo đúng một lần gọi lại. Cấu hình retry, recovery, thời điểm shutdown, quyền sở hữu partition và thời gian retention đều ảnh hưởng đến khả năng xử lý tiếp.

## 2. Phân biệt consumer position và committed offset

Kafka consumer duy trì ít nhất hai khái niệm khác nhau:

- **Consumer position:** offset mà consumer dự kiến lấy tiếp theo trong phiên làm việc hiện tại; một lần poll có thể làm vị trí này tiến lên.
- **Committed offset:** offset lưu cho consumer group, được dùng để xác định nơi tiếp tục khi consumer restart hoặc partition được gán lại.

Ví dụ:

    Topic orders.created, partition 0

    Offset:          120      121      122      123
    Record:           A        B        C        D

    Committed offset ban đầu: 120
    poll() trả về A, B, C, D
    Consumer position có thể là 124
    Listener đang xử lý B rồi thất bại

Consumer position đã tiến qua nhiều record không có nghĩa A, B, C, D đã được xử lý hoặc commit. Sau rollback, container cần xử lý record chưa hoàn tất và bảo đảm không bỏ qua chúng. Tùy cơ chế của phiên bản đang dùng, container có thể seek lại tới offset an toàn hoặc giữ các record còn lại để giao lại.

Offset được commit thường là **offset tiếp theo cần đọc**. Nếu record ở offset 120 hoàn tất, giá trị commit tương ứng là 121. Nếu record 120 thất bại và offset 121 chưa được commit an toàn, lần đọc tiếp phải còn khả năng quay lại offset 120.

Chỉ nhìn consumer lag hoặc vị trí poll là không đủ để kết luận record đã xử lý xong. Cần phân biệt trạng thái thực tế của nghiệp vụ với offset transaction.

## 3. Atomicity của Kafka transaction

Một Kafka transaction có thể bao gồm:

1. Các record do transactional Kafka producer gửi tới một hoặc nhiều topic/partition.
2. Các offset của consumer group được gửi vào transaction.
3. Quyết định commit hoặc abort trên broker.

Khi transaction commit, Kafka bảo đảm tính nguyên tử của các thao tác **thuộc phạm vi Kafka transaction**. Khi transaction abort, các output record thuộc transaction đó không được giao tới consumer cấu hình isolation.level=read_committed; offset gửi trong transaction đó cũng không được commit.

Ví dụ:

    Consume: orders.created-0@120
    Produce: orders.validated-2@X
    Send offset: orders.created-0 => 121

    Commit transaction:
      - Output trở nên committed
      - Offset 121 trở nên committed cho group

    Abort transaction:
      - Output bị abort
      - Offset 121 không được ghi nhận từ transaction này
      - Input vẫn có thể được redeliver

Điều này hỗ trợ **exactly-once semantics (EOS) trong luồng Kafka-to-Kafka** khi các điều kiện cần thiết được đáp ứng. Nó **không** tự làm cho database, HTTP API, gửi email hoặc thanh toán bên ngoài Kafka trở thành một phần của cùng transaction.

Nếu listener đã ghi database rồi Kafka transaction abort, database có thể vẫn giữ thay đổi. Khi record đầu vào được giao lại, side effect database có thể chạy lần thứ hai nếu không có idempotency.

## 4. Vì sao Spring Kafka cần AfterRollbackProcessor?

Khi một container đang dùng Kafka transaction và listener ném exception, container rollback transaction rồi thực hiện bước xử lý sau rollback. Thành phần **AfterRollbackProcessor** được dùng để quyết định cách định vị lại các record chưa được xử lý và, trong trường hợp lỗi lặp lại, cách recover một record khó xử lý.

Implementation phổ biến là **DefaultAfterRollbackProcessor**.

Sơ đồ:

    poll() -> listener -> exception
                           |
                           v
                   Rollback Kafka TX
                           |
                           v
                 AfterRollbackProcessor
                           |
                +----------+-----------+
                |                      |
                v                      v
            Chưa hết retry        Đã tới ngưỡng recover
                |                      |
                v                      v
        Seek/reposition + backoff   Recoverer / DLT
                |                      |
                v                      v
          Redelivery lần sau   Chính sách offset recovered

Các trách nhiệm thường gặp của DefaultAfterRollbackProcessor:

- Điều chỉnh vị trí tiêu thụ để record lỗi và các record còn lại chưa được xử lý có thể được giao lại.
- Kết hợp BackOff để tránh lặp retry quá nhanh.
- Theo dõi số lần xử lý thất bại theo record trong phạm vi mà phiên bản hỗ trợ.
- Sau khi đạt giới hạn, gọi recoverer để xử lý một record không thể tiêu thụ bình thường.
- Trong cấu hình phù hợp, hỗ trợ commit offset của record được recover trong **một Kafka transaction mới**.

**AfterRollbackProcessor không phải chính transaction manager.** Transaction manager thực hiện commit/rollback Kafka transaction; AfterRollbackProcessor xử lý diễn tiến đọc lại/recovery sau khi rollback xảy ra.

## 5. Khác biệt với DefaultErrorHandler

Spring Kafka có hai cơ chế thường bị nhầm:

| Cơ chế | Ngữ cảnh tiêu biểu | Vai trò |
|---|---|---|
| CommonErrorHandler / DefaultErrorHandler | Listener container không dùng Kafka transaction | Retry, seek/retention, recover và xử lý lỗi listener |
| AfterRollbackProcessor / DefaultAfterRollbackProcessor | Listener container dùng Kafka transaction và transaction bị rollback | Điều chỉnh redelivery sau rollback, áp dụng backoff/recovery |
| KafkaTransactionManager | Kafka transaction | Bắt đầu, commit hoặc rollback transaction theo lifecycle |
| DeadLetterPublishingRecoverer | Recovery | Publish record lỗi sang DLT, có thể dùng với error handler hoặc after-rollback processor |

Với listener giao dịch, Spring Kafka thường không cấu hình CommonErrorHandler mặc định theo cách nuốt exception: exception phải lan ra để container rollback transaction. Nếu tự đăng ký CommonErrorHandler, cần xem handler đó có được phép trả về bình thường hay không.

**Nếu một handler bắt exception rồi trả về như đã xử lý thành công, container có thể coi listener thành công và commit transaction.** Khi đó không còn rollback, dù nghiệp vụ đã thất bại. Với lỗi cần rollback, exception phải được ném tiếp hoặc được xử lý bằng một chính sách giao dịch đã thiết kế rõ.

Ví dụ dễ gây hiểu nhầm:

~~~java
@KafkaListener(topics = "orders.created", groupId = "billing")
public void consume(OrderCreated event) {
    try {
        billingService.bill(event);
    }
    catch (Exception exception) {
        log.error("Billing failed", exception);
        // Không ném exception => container có thể coi xử lý thành công.
    }
}
~~~

Nếu bill() thất bại nhưng listener kết thúc bình thường, không thể chỉ trông chờ Kafka transaction tự rollback. Thay vào đó:

~~~java
@KafkaListener(topics = "orders.created", groupId = "billing")
public void consume(OrderCreated event) {
    try {
        billingService.bill(event);
    }
    catch (Exception exception) {
        log.error("Billing failed", exception);
        throw exception;
    }
}
~~~

Trong thực tế, nên giữ đúng exception type hoặc wrap với cause gốc để AfterRollbackProcessor có thể nhận diện lỗi và hệ thống log có đủ thông tin.

## 6. Cấu hình transaction ở Spring Kafka

Một cấu hình Spring Boot phổ biến bật transactional producer bằng transaction-id prefix và tắt consumer auto commit:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: order-service-tx-
      properties:
        acks: all
        enable.idempotence: true
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
    listener:
      ack-mode: record
~~~

Ý nghĩa:

- **transaction-id-prefix**: cho phép ProducerFactory tạo transactional producer với transactional.id riêng.
- **enable-auto-commit=false**: offset không được auto commit tách rời khỏi xử lý nghiệp vụ.
- **isolation.level=read_committed**: khi consumer đọc output transactional, nó chỉ nhìn thấy dữ liệu thuộc transaction đã commit.
- **acks=all** và idempotence: tăng an toàn phía producer; không thay thế transaction.
- **ack-mode**: phối hợp với cách listener container xác nhận record; transaction lifecycle quyết định khi nào offset thực sự được commit.

Ở các phiên bản Spring Boot phù hợp, cấu hình transaction-id prefix có thể kích hoạt auto-configuration của KafkaTransactionManager. Với factory do ứng dụng tự tạo, phải gắn Kafka-aware transaction manager đúng cách vào listener container factory.

Ví dụ ý tưởng cấu hình tường minh:

~~~java
@Bean
KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
        ProducerFactory<String, OrderEvent> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Sau đó cấu hình transaction manager vào listener container factory bằng API tương ứng với Spring Kafka mà dự án sử dụng. Tên setter ở các dòng version có thể là setTransactionManager hoặc setKafkaAwareTransactionManager trên ContainerProperties; cần đối chiếu version thực tế.

Không nên copy đoạn cấu hình từ version khác rồi kết luận listener đã chạy transactional. Hãy kiểm tra producer factory có transaction-capable hay không, listener container thực sự nhận transaction manager và log/metric broker có transaction commit/abort.

## 7. Ví dụ consume-process-produce có rollback

Giả sử listener đọc một sự kiện đơn hàng và phát kết quả đã xác thực:

~~~java
@Service
public class OrderValidationListener {

    private final KafkaTemplate<String, OrderValidated> kafkaTemplate;
    private final OrderValidator validator;

    public OrderValidationListener(
            KafkaTemplate<String, OrderValidated> kafkaTemplate,
            OrderValidator validator) {

        this.kafkaTemplate = kafkaTemplate;
        this.validator = validator;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-validation",
        containerFactory = "transactionalListenerFactory"
    )
    public void onOrder(ConsumerRecord<String, OrderCreated> record) {

        OrderCreated event = record.value();

        validator.validate(event); // Có thể ném exception.

        OrderValidated result = new OrderValidated(
            event.eventId(),
            event.orderId(),
            "VALID"
        );

        kafkaTemplate.send(
            "orders.validated",
            record.key(),
            result
        );
    }
}
~~~

Ví dụ này giả định transactionalListenerFactory đã được cấu hình để dùng KafkaTransactionManager và KafkaTemplate dùng một ProducerFactory phù hợp cho transaction.

Các khả năng:

- **validate thành công, Kafka send thành công, transaction commit thành công:** output được commit và offset đầu vào được commit trong transaction.
- **validate ném exception:** container rollback transaction; offset đầu vào không commit; record có thể redelivery.
- **Kafka send thất bại bất đồng bộ:** nếu listener không quan sát lỗi và transaction commit xử lý lỗi sau đó, transaction có thể thất bại tại thời điểm commit; cần theo dõi exception transaction chứ không chỉ xem listener trả về.
- **Broker không xác nhận commit:** trạng thái thực tế có thể không rõ từ góc nhìn client. Khi khởi động lại, hãy dùng eventId và idempotency để phòng trường hợp được giao lại.

Một điểm cần nhớ là KafkaTemplate.send() có thể trả future trước khi broker ghi record xong. Đừng xem lời gọi send không ném exception tức là toàn bộ transaction đã commit.

## 8. Timeline rollback và redelivery

Giả sử committed offset ban đầu của partition là 50:

| Thời điểm | Hành động | Committed offset |
|---|---|---|
| T0 | Consumer poll record offset 50 | 50 |
| T1 | Container bắt đầu Kafka transaction T1 | 50 |
| T2 | Listener gửi output record | 50 |
| T3 | Listener ném exception | 50 |
| T4 | Container abort T1 | 50 |
| T5 | AfterRollbackProcessor điều chỉnh vị trí và backoff | 50 |
| T6 | Record offset 50 được giao lại | 50 |
| T7 | Listener xử lý thành công trong T2 | 50 |
| T8 | Container gửi offset 51 và commit T2 | 51 |

Record có thể được gọi listener nhiều lần nhưng output Kafka đã abort trong T1 không hiển thị với consumer read_committed. Khi T2 commit thành công, output mới và offset 51 trở nên committed.

Nếu hệ thống có consumer sử dụng isolation.level=read_uncommitted, consumer đó có thể nhìn thấy record của transaction đã abort. Vì vậy, các downstream consumer cần cấu hình read_committed khi yêu cầu bảo đảm không đọc output bị rollback.

## 9. Redelivery khác với duplicate nghiệp vụ

Hai việc có thể xảy ra đồng thời:

- Kafka redelivery lại cùng record vì offset chưa commit.
- Hệ thống nghiệp vụ lặp side effect do thao tác ở ngoài Kafka transaction đã thành công trước khi rollback.

Ví dụ:

    Listener nhận PaymentRequested(evt-1)
       |
       v
    Gọi paymentGateway.charge() -> thành công
       |
       v
    KafkaTemplate.send("payment.completed") -> lỗi
       |
       v
    Kafka transaction rollback
       |
       v
    Redelivery PaymentRequested(evt-1)
       |
       v
    Gọi paymentGateway.charge() thêm lần nữa?

Kafka transaction không rollback được paymentGateway.charge(). Nếu không gửi **idempotency key** ổn định, có thể phát sinh khoản thanh toán trùng.

Biện pháp:

1. Định danh sự kiện bằng eventId duy nhất và ổn định.
2. Với database, ghi dấu mốc eventId cùng transaction database với side effect.
3. Với HTTP API, sử dụng idempotency key do API hỗ trợ.
4. Với producer phát event, giữ key và eventId nhất quán qua retry.
5. Không sinh eventId mới khi nhận lại cùng record Kafka.

Mô hình Inbox hoặc idempotent consumer đặc biệt quan trọng với nghiệp vụ có side effect không thuộc Kafka.

## 10. Record nào được giao lại sau rollback?

Một poll thường trả nhiều record. Khi xử lý record listener, các record trước record lỗi có thể đã được xử lý trong cùng nhịp poll, nhưng tính bền vững của offset phụ thuộc ranh giới transaction.

Ví dụ:

    orders-0:
       offset 10 -> A
       offset 11 -> B
       offset 12 -> C
       offset 13 -> D

    poll() nhận A, B, C, D
    Listener hoàn tất A
    Listener xử lý B -> exception

Sau rollback, cần bảo đảm B và những record chưa xử lý C/D không bị bỏ qua. Tùy cấu hình transaction và phiên bản container, processor sẽ seek/reposition các partition tới offset thích hợp để những record cần giao lại được đọc tiếp.

Không nên khẳng định mọi tình huống chỉ B được redeliver. Nếu A cũng thuộc transaction đã abort và offset của A chưa commit, A có thể được xử lý lại. Nếu mỗi record đã được commit trong transaction riêng trước B, A không cần redelivery vì rollback của B không ảnh hưởng transaction đã commit.

Để suy luận đúng, cần quan sát **transaction boundary**, **ack mode**, **offset commit thực tế** và **những record đã được xử lý** chứ không chỉ nhìn kết quả poll.

## 11. DefaultAfterRollbackProcessor và BackOff

DefaultAfterRollbackProcessor có thể dùng BackOff để trì hoãn lần redelivery tiếp theo của record lỗi. Với lỗi tạm thời, retry vài lần có thể đủ để phục hồi dependency.

Ví dụ cấu hình:

~~~java
@Bean
DefaultAfterRollbackProcessor<String, OrderCreated>
afterRollbackProcessor() {

    return new DefaultAfterRollbackProcessor<>(
        (record, exception) -> {
            log.error(
                "Record exhausted rollback retries: {}-{}@{}",
                record.topic(),
                record.partition(),
                record.offset(),
                exception
            );
        },
        new FixedBackOff(1_000L, 3L)
    );
}
~~~

Đoạn trên dùng recoverer dạng log để minh họa signature, **không phải recovery production an toàn**. Nếu recoverer chỉ log và sau đó cho phép bỏ qua record, dữ liệu có thể bị mất khỏi luồng xử lý nghiệp vụ. Với record cần bảo toàn, nên dùng DeadLetterPublishingRecoverer hoặc một nơi lưu record lỗi bền vững.

Nếu listener container factory hỗ trợ setter tương ứng, gắn processor vào factory:

~~~java
factory.setAfterRollbackProcessor(afterRollbackProcessor);
~~~

Cách hoạt động khái quát:

1. Listener ném exception.
2. Kafka transaction hiện tại rollback.
3. Processor áp dụng backoff, điều chỉnh vị trí hoặc theo dõi attempt.
4. Record được giao lại trong lần xử lý tiếp theo.
5. Khi đạt ngưỡng retry, recoverer được gọi theo chính sách đã cấu hình.

Lưu ý rằng số lần retry, cách đếm delivery attempt và thời điểm gọi recoverer phụ thuộc cấu hình BackOff và version Spring Kafka. Không nên dựa vào số lần mặc định mà không ghi rõ trong file cấu hình hoặc integration test.

## 12. Poison pill và vòng lặp rollback vô hạn

**Poison pill** là record mà listener không thể xử lý thành công bằng cách thử lại đơn giản: JSON không hợp lệ, dữ liệu vi phạm business rule, thiếu reference vĩnh viễn hoặc bug logic.

Nếu mọi lần retry đều rollback và record chưa được recover, consumer có thể mắc kẹt:

    offset 80 -> invalid payload -> rollback
    offset 80 -> invalid payload -> rollback
    offset 80 -> invalid payload -> rollback
    ...

Hệ quả:

- Lag của partition tăng.
- Các record phía sau không được xử lý.
- CPU, log volume và số lần gọi dependency có thể tăng.
- Dịch vụ phụ thuộc bị gọi lại vô ích.
- Khi có nhiều partition bị lỗi đồng thời, toàn bộ consumer group có thể suy giảm throughput.

Một chính sách production nên phân loại:

| Loại lỗi | Retry? | Xử lý khi hết retry |
|---|---|---|
| HTTP 503 tạm thời | Có, giới hạn | DLT hoặc recovery có điều kiện |
| Database deadlock | Có, với backoff | DLT/cảnh báo nếu kéo dài |
| Validation cố định | Thường không hoặc rất ít | DLT để sửa dữ liệu |
| Deserialization lỗi cấu trúc | Thường không | DLT giữ dữ liệu gốc nếu có thể |
| Permission/credential sai | Tránh retry bão hòa | Cảnh báo và dừng/sửa cấu hình |
| Bug NullPointerException | Có giới hạn thấp | DLT, sửa code và re-drive |

Với transaction rollback, cần thiết kế đường **recover + commit offset** có tính bền vững. Chỉ log lỗi rồi tiếp tục có thể vô tình bỏ qua nghiệp vụ.

## 13. Recovery sang DLT sau rollback

Một lựa chọn phổ biến là DeadLetterPublishingRecoverer. Sau khi record thất bại nhiều lần, recoverer xuất bản nó sang DLT kèm metadata nguồn và exception.

Ví dụ cấu hình recoverer cho AfterRollbackProcessor:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
            recoverer,
            new FixedBackOff(1_000L, 3L)
        );

factory.setAfterRollbackProcessor(processor);
~~~

Giả sử nguồn là orders.created partition 1, DLT thường được định tuyến tới orders.created.DLT partition 1 theo ví dụ. Topic DLT phải tồn tại với số partition phù hợp, hoặc resolver phải quyết định partition đích an toàn.

DLT nên lưu:

- Key/value gốc hoặc payload có thể khôi phục.
- Topic/partition/offset nguồn.
- Event ID, correlation ID.
- Exception class và thông tin lỗi cần cho điều tra.
- Trạng thái của lần retry/recovery.

Nếu recoverer publish DLT thất bại, không nên đánh dấu offset nguồn là đã xử lý. Cần cấu hình và kiểm tra cơ chế phát hiện lỗi send result, timeout, broker availability và retry của recovery.

## 14. Commit offset của record được recover trong transaction mới

Đây là điểm đặc biệt quan trọng trong **redelivery sau rollback**.

Khi transaction của listener đã abort, không thể coi offset của record lỗi đã được commit chỉ vì recoverer được gọi. Muốn vừa lưu record vào DLT vừa ghi nhận rằng record nguồn đã được recover, cần thiết kế một **Kafka transaction mới** chứa các thao tác phù hợp.

Mẫu mong muốn:

    Transaction T1:
       Listener xử lý record 80
       Exception
       Abort T1

    Recovery transaction T2:
       Publish record 80 -> DLT
       Send source offset 81 to transaction
       Commit T2

Khi T2 commit thành công, consumer read_committed có thể thấy record DLT, và group có thể tiếp tục từ offset 81. Nếu T2 abort, offset 81 không được commit bởi T2 và output DLT cũng không có hiệu lực committed.

DefaultAfterRollbackProcessor trong các phiên bản hỗ trợ **commitRecovered** và KafkaOperations/KafkaTemplate để đưa offset recovered vào một transaction mới. Cần cấu hình đúng KafkaTemplate và xác nhận các điều kiện về transaction, recoverer, listener container và version API.

Hướng cấu hình minh họa:

~~~java
DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
            new DeadLetterPublishingRecoverer(dltKafkaTemplate),
            new FixedBackOff(1_000L, 3L)
        );

// Các phiên bản hỗ trợ cho phép bật commit offset recovered.
processor.setCommitRecovered(true);

// Cấu hình KafkaOperations/Template dùng cho recovery transaction
// theo API chính xác của phiên bản Spring Kafka đang chạy.
~~~

Lời gọi setCommitRecovered(true) **một mình không đủ** để suy ra DLT publish và offset recovered đã được commit nguyên tử. Cần kiểm tra processor được cấp KafkaOperations transaction-capable và cách transaction mới được quản lý. Tên setter hoặc constructor có thể khác giữa các phiên bản.

Nếu hệ thống không thực hiện commit offset recovered trong transaction phù hợp, record đã chuyển DLT có thể tiếp tục xuất hiện sau restart/rebalance. Ngược lại, commit offset trước khi DLT được lưu bền vững có thể làm mất record khỏi luồng recovery.

## 15. Batch listener và rollback toàn batch

Với batch listener, một lần gọi nhận nhiều records:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-batch-service",
    containerFactory = "transactionalBatchFactory"
)
public void onBatch(List<ConsumerRecord<String, OrderCreated>> batch) {

    for (ConsumerRecord<String, OrderCreated> record : batch) {
        orderService.process(record.value());
    }
}
~~~

Nếu record thứ tư thất bại sau khi ba record trước đó đã được xử lý, transaction Kafka của batch có thể bị rollback. Nếu cả batch thuộc cùng một transaction chưa commit, output Kafka của ba record trước đó cũng bị abort; các record cần thiết có thể được giao lại.

Khác với record listener, batch listener không luôn cung cấp cho processor thông tin chắc chắn về record cụ thể nào gây lỗi. **Một batch có thể được redeliver/retry toàn bộ**, tùy error handling và API.

Không nên mặc định DefaultAfterRollbackProcessor có thể bỏ qua duy nhất một poison record trong mọi batch listener. Những phiên bản hỗ trợ có thể xử lý tốt hơn khi listener ném BatchListenerFailedException với record/index phù hợp; tuy nhiên khả năng recovery của batch vẫn phụ thuộc vào Spring Kafka version và transaction semantics. Cần kiểm thử đường batch cụ thể.

Nếu mỗi record tạo side effect bên ngoài Kafka, retry cả batch làm tăng rủi ro duplicate. Có thể cân nhắc record listener, idempotent writes hoặc chia workload để giới hạn tác động.

## 16. Redelivery, seek và tính thứ tự trong partition

Kafka duy trì thứ tự record trong một partition. Khi record lỗi được giữ lại để redelivery, các record phía sau trong cùng partition thường phải chờ để bảo đảm không bỏ qua nó.

Ví dụ:

    orders-0:
       30: OrderCreated(A)  -> thành công
       31: OrderCreated(B)  -> lỗi
       32: OrderCreated(C)  -> chờ
       33: OrderCreated(D)  -> chờ

Nếu B được retry blocking, C và D có thể bị trì hoãn. Khi B được recover sang DLT và offset được xử lý theo chính sách, container có thể tiếp tục C/D.

Cần phân biệt thứ tự record được **đọc từ Kafka** với thứ tự **side effect nghiệp vụ thực thi**. Nếu listener phát công việc sang executor và trả về ngay, transaction có thể commit trước khi task hoàn tất; thứ tự xử lý ngoài Kafka không còn được bảo đảm chỉ vì topic có một partition.

Với giao dịch cần tính thứ tự theo key, có thể giữ logic xử lý đồng bộ trong listener hoặc điều phối completion và acknowledgment theo từng partition. Không đánh dấu record là thành công chỉ vì task đã được submit.

## 17. Redelivery khi consumer restart hoặc rebalance

Redelivery không chỉ xảy ra sau rollback do listener ném exception. Nó còn có thể xảy ra sau:

- Pod bị kill giữa transaction.
- JVM crash sau khi ghi side effect database nhưng trước Kafka commit.
- Group rebalance làm partition chuyển sang consumer khác.
- Network chập chờn khiến kết quả commit transaction không rõ ràng.
- Transaction producer bị fencing hoặc transaction timeout.
- Consumer gặp lỗi trước khi commit offset.

Khi khởi động lại, consumer group bắt đầu từ committed offset gần nhất, chịu ảnh hưởng của auto.offset.reset nếu chưa có committed offset hoặc offset cũ không còn trong retention. Không nên dùng auto.offset.reset=latest như một cách “chữa” lỗi redelivery nếu điều đó làm mất các record còn backlog.

Một consumer mới có thể nhận lại record mà consumer cũ từng thực thi side effect, nhưng transaction Kafka chưa commit. Vì vậy, idempotency cần dựa vào eventId và trạng thái bền vững, không dựa vào biến nhớ trong RAM của một pod.

## 18. ErrorHandlingDeserializer với transactional listener

Lỗi deserialize có thể phát sinh trong consumer.poll(), trước khi listener được gọi. Nếu deserializer ném exception trực tiếp, listener không có cơ hội rollback theo logic nghiệp vụ của mình.

Spring Kafka hỗ trợ ErrorHandlingDeserializer để đóng gói thông tin lỗi deserialize vào headers và cho container/error handler xử lý record lỗi theo chính sách.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
~~~

Nếu payload không parse được thành OrderCreated, recoverer có thể cần gửi raw bytes sang DLT. KafkaTemplate dùng để xuất bản DLT phải có serializer phù hợp với kiểu payload thực tế, không mặc định là OrderCreated.

Một malformed record thường không thể được sửa bằng cách rollback và đọc lại nhiều lần. Hãy kiểm soát số lần retry, phân loại lỗi cố định và giữ payload để điều tra hoặc re-drive sau khi schema được sửa.

## 19. Giao dịch Kafka và database không tự nguyên tử

Mẫu consume-process-produce có thể ghi database đồng thời với gửi Kafka output:

~~~java
@Transactional
public void updateOrder(OrderCreated event) {
    orderRepository.save(...);
    kafkaTemplate.send("orders.updated", event.orderId(), ...);
}
~~~

Annotation @Transactional có thể chọn transaction manager khác nhau tùy cấu hình ứng dụng. Nếu không xác định rõ transaction manager và cách transaction được phối hợp, không thể kết luận database và Kafka sẽ cùng commit hoặc cùng rollback hoàn toàn.

Ngay cả khi cấu hình thứ tự commit giữa database và Kafka, hai hệ thống độc lập vẫn có cửa sổ lỗi: database commit thành công nhưng Kafka commit thất bại. Khi input Kafka redelivery, database có thể nhận thao tác trùng.

Các giải pháp thường dùng:

- **Idempotent consumer:** khóa duy nhất theo eventId trong database transaction.
- **Transactional Inbox:** ghi nhận record đã xử lý trong cùng transaction database.
- **Transactional Outbox:** lưu output event trong database cùng thay đổi nghiệp vụ, rồi một publisher riêng chuyển event sang Kafka.
- **Idempotent API:** dùng idempotency key cho dependency ngoài Kafka.

Kafka EOS có giá trị lớn khi đầu vào, đầu ra và offset đều nằm trong Kafka; với side effect bên ngoài, cần thêm mô hình nhất quán phù hợp.

## 20. Transaction timeout và producer fencing

Một Kafka transaction không nên giữ mở quá lâu. Nếu listener xử lý quá chậm, transaction có thể vượt timeout ở broker hoặc client.

Các tình huống cần quan sát:

- transaction.timeout.ms quá ngắn so với thời gian xử lý.
- max.poll.interval.ms không phù hợp với batch processing.
- Transactional producer bị fencing khi một producer khác dùng cùng transactional.id.
- Broker không xác nhận commit/abort kịp thời.
- Ứng dụng scale hoặc restart nhưng transaction-id prefix không bảo đảm định danh producer thích hợp.

Trong các trường hợp này, container có thể không commit được transaction, và input record có thể được giao lại. Không nên retry mù mọi lỗi transaction bằng cùng một producer đã bị fencing; một số lỗi yêu cầu tạo lại producer/container theo lifecycle của framework.

Khi scale ứng dụng, cần hiểu cách Spring Kafka tạo transactional.id từ prefix và cache producer. Không tự gán một transactional.id cố định giống nhau cho nhiều application instance hoạt động đồng thời.

## 21. Blocking retry và non-blocking retry khi dùng transaction

Một số hệ thống dùng @RetryableTopic để chuyển record lỗi sang topic retry thay vì giữ partition chính trong vòng retry. Tuy nhiên, retry topic, listener transaction và AfterRollbackProcessor có những ranh giới khác nhau.

| Chiến lược | Diễn tiến khi lỗi | Điểm cần cân nhắc |
|---|---|---|
| AfterRollbackProcessor + BackOff | Transaction rollback, record được điều chỉnh để redelivery | Giữ partition chờ, cần giới hạn retry |
| DLT recover sau rollback | Khi hết retry, gửi DLT và xử lý offset recovered | Cần tính bền vững/transaction của recovery |
| @RetryableTopic | Chuyển record sang topic retry cho lần thử sau | Có thể thay đổi thứ tự theo key; tương tác với transactions phụ thuộc version |
| Dừng consumer để khắc phục dependency | Không chủ động tiêu thụ thêm | Lag tăng; cần kiểm soát rollout và resume |

Không tự ghép @RetryableTopic với transactional listener rồi giả định mọi đường gửi retry topic đều nằm trong cùng Kafka transaction. Kiểm tra hạn chế và khả năng hỗ trợ của phiên bản Spring Kafka, đặc biệt cơ chế recoverer, container factory và offset commit. Thiết kế integration test cho đúng đường xử lý dự kiến.

Với giao dịch cần thứ tự nghiêm ngặt, blocking retry ngắn rồi recover sang DLT có thể dễ suy luận hơn, nhưng phải chấp nhận rằng poison record có thể làm chậm các record khác trong partition.

## 22. Quan sát redelivery trong production

Muốn biết rollback/redelivery có đang diễn ra đúng hay không, cần theo dõi cả Kafka transaction, consumer và nghiệp vụ.

**Transaction**

- Số transaction commit/abort.
- Tỷ lệ commit thất bại.
- Transaction duration và timeout.
- Producer fencing hoặc lỗi coordinator.
- DLT recovery transaction success/failure nếu có.

**Consumer**

- Số lần listener nhận cùng topic-partition-offset.
- Retry/backoff count và nguyên nhân exception.
- Consumer lag theo group/partition.
- Rebalance count và thời gian rebalance.
- Thời gian từ poll đến xử lý thành công.

**Nghiệp vụ**

- Số eventId đã xử lý thành công.
- Số duplicate được idempotent layer nhận diện.
- Số external side effect thất bại và retry.
- Số record chuyển DLT, số record re-drive.
- Thời gian phục hồi của dependency.

Log nên có eventId, groupId, topic, partition, offset, exception class, attempt/recovery stage và correlationId. Không ghi toàn bộ payload nhạy cảm. Để quan sát transaction cần bật metric/log phù hợp, nhưng không nên suy ra trạng thái broker chỉ từ một dòng log “sent output” trước khi transaction commit.

## 23. Kịch bản kiểm thử redelivery sau rollback

Một integration test nên dùng broker thật ở mức test (Embedded Kafka hoặc Testcontainers), vì transaction và offset semantics phụ thuộc broker/coordinator chứ không chỉ logic Java.

### 23.1. Lỗi listener trước khi gửi output

1. Gửi một record nguồn có eventId cố định.
2. Cấu hình listener transactional để ném exception ở lần xử lý đầu.
3. Xác nhận transaction rollback.
4. Xác nhận offset nguồn chưa commit do lần xử lý thất bại.
5. Cho listener xử lý thành công ở lần tiếp.
6. Xác nhận output committed xuất hiện một lần với consumer read_committed.
7. Xác nhận source offset tiến qua record sau transaction thành công.

### 23.2. Lỗi sau khi KafkaTemplate.send()

1. Listener gửi output record rồi ném exception trước khi transaction commit.
2. Xác nhận output thuộc transaction abort không hiển thị với read_committed consumer.
3. Xác nhận record nguồn được redeliver.
4. Cho lần redelivery xử lý thành công.
5. Xác nhận output cuối cùng và committed offset nhất quán.

Nếu test dùng read_uncommitted consumer, nó có thể nhìn thấy output của transaction abort và dẫn tới kết luận sai về EOS.

### 23.3. Side effect database thành công rồi rollback Kafka

1. Listener ghi database và commit thay đổi.
2. Sau đó Kafka output lỗi hoặc transaction abort.
3. Record nguồn redelivery.
4. Listener gọi lại database với cùng eventId.
5. Xác nhận unique constraint/inbox ngăn double update.
6. Xác nhận Kafka output cuối cùng được commit đúng.

Test này chứng minh phần Kafka transaction không bảo vệ side effect ngoài Kafka.

### 23.4. Poison record và DLT

1. Gửi record luôn ném validation exception.
2. Cấu hình BackOff hữu hạn.
3. Theo dõi số lần redelivery.
4. Sau khi hết retry, xác nhận recoverer gửi DLT.
5. Nếu cấu hình commitRecovered, xác nhận offset nguồn được commit theo cơ chế recovery transaction.
6. Làm DLT publish thất bại và xác nhận record nguồn không bị mất.
7. Re-drive record đã sửa với eventId gốc và xác nhận idempotency.

### 23.5. Batch listener và rebalance

1. Gửi nhiều record trong một poll.
2. Cố ý làm record giữa batch thất bại.
3. Quan sát record nào được redeliver sau rollback.
4. Dừng một consumer hoặc kích hoạt rebalance khi transaction đang chạy.
5. Xác nhận consumer mới tiếp tục từ committed offset an toàn.
6. Xác nhận không có side effect nghiệp vụ trùng ngoài phạm vi idempotency.

Những test này cần thu thập offset, transaction outcome, DLT record và số lần gọi side effect. Chỉ assert số lần listener được gọi không đủ để chứng minh semantics.

## 24. Quy trình xử lý sự cố rollback lặp lại

Khi phát hiện consumer liên tục nhận lại cùng offset:

1. **Xác định key:** groupId, topic, partition, offset, eventId.
2. **Xác nhận lỗi:** exception do listener, deserializer, producer send, transaction commit hay fencing.
3. **Kiểm tra transaction:** transaction thực sự abort hay listener đã nuốt lỗi rồi commit?
4. **Kiểm tra committed offset:** tiến hay đứng yên; không nhầm với consumer position.
5. **Kiểm tra AfterRollbackProcessor:** BackOff, số lần retry, recoverer và DLT.
6. **Kiểm tra dependency:** database/API có đang timeout, rate limit hoặc không sẵn sàng?
7. **Kiểm tra side effect:** có cần bật hoặc sửa idempotency trước khi retry tiếp?
8. **Kiểm tra DLT:** topic/partition, serializer, quyền publish và send result.
9. **Kiểm tra rebalance/transaction timeout:** có làm vòng retry không thể kết thúc?
10. **Phục hồi có kiểm soát:** sửa dependency/data/code rồi re-drive hoặc cho consumer chạy tiếp với giám sát.

Không giải quyết sự cố bằng cách tăng committed offset thủ công để bỏ qua record mà chưa có quyết định nghiệp vụ và kế hoạch lưu record lỗi. Việc seek/commit sai có thể làm mất dữ liệu cần xử lý.

## 25. Các lỗi hiểu sai thường gặp

| Nhận định sai | Rủi ro | Cách hiểu đúng |
|---|---|---|
| Rollback Kafka cũng rollback database | Ghi database trùng khi redelivery | Database ngoài phạm vi Kafka transaction |
| Listener ném exception nhưng offset vẫn tự commit | Mất khả năng phân biệt trạng thái | Phải kiểm tra auto commit, transaction và handler |
| Consumer position đã tiến tức là record hoàn tất | Bỏ qua record chưa xử lý | Committed offset mới xác định vị trí restart |
| KafkaTemplate.send() không lỗi nghĩa là output committed | Có thể output vẫn bị abort sau đó | Kết quả transaction commit mới quyết định |
| Mỗi rollback chỉ giao lại đúng một record | Bỏ sót khả năng replay batch/các record cùng transaction | Phụ thuộc transaction boundary và processing mode |
| DLT publish một lần là đã recover an toàn | Có thể DLT send failure hoặc offset chưa commit | Cần recovery transaction và xử lý lỗi send |
| Retry vô hạn là an toàn vì không mất record | Poison record làm nghẽn partition | Giới hạn retry, DLT và cảnh báo |
| read_uncommitted cũng bảo đảm không thấy output abort | Downstream đọc dữ liệu đã rollback | Dùng read_committed khi cần semantics đó |
| Exception bị catch và log vẫn dẫn đến rollback | Container có thể coi xử lý thành công | Rethrow exception hoặc đánh dấu rollback theo thiết kế |
| Kafka EOS bảo vệ luôn HTTP/email/payment | Side effect ngoài Kafka bị lặp | Dùng idempotency key và mô hình nhất quán bổ sung |

## 26. Nguyên tắc thiết kế

- Xác định transaction boundary của listener container trước khi suy luận record nào được redeliver.
- Tắt consumer auto commit khi muốn offset là một phần của Kafka transaction.
- Dùng transactional producer/factory phù hợp; không chỉ thêm annotation mà nghĩ đã bật Kafka transaction.
- Đảm bảo lỗi cần rollback được ném ra khỏi listener hoặc xử lý theo hợp đồng transaction đúng.
- Hiểu rằng rollback làm offset trong transaction chưa commit, nên record có thể được giao lại.
- Dùng DefaultAfterRollbackProcessor cho redelivery/recovery trong container transactional.
- Giới hạn BackOff và số lần thử; không giữ poison record vô hạn.
- Dùng DLT bền vững, phân loại exception và kiểm soát recovery publish failure.
- Với record recovered, kiểm soát Kafka transaction mới nếu cần commit DLT + source offset nguyên tử.
- Dùng read_committed ở consumer downstream khi cần ẩn output đã abort.
- Giữ eventId ổn định và side effect idempotent cho database, API và các hệ thống ngoài Kafka.
- Đánh giá batch listener và rebalance riêng vì có thể redelivery nhiều record.
- Đặt timeout, điều phối producer fencing và graceful shutdown.
- Quan sát committed offset, transaction abort, redelivery, DLT và duplicate.
- Kiểm thử rollback cả trước/sau Kafka send, trước commit, sau side effect ngoài Kafka và trong rebalance.

**Redelivery sau rollback** là một phần cốt lõi của độ tin cậy consumer transactional: khi một lần xử lý không hoàn tất Kafka transaction, các record chưa được xác nhận vẫn phải có đường xử lý lại hoặc recovery có kiểm soát. Tính nhất quán Kafka-to-Kafka được bảo vệ bởi transaction và offset commit nguyên tử; tính nhất quán của nghiệp vụ chỉ đạt được khi phối hợp thêm backoff, DLT, idempotency và quan sát vận hành.
