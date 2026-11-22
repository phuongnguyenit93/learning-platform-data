# Consumer-initiated transaction

Trong Spring Kafka, **consumer-initiated transaction** là mô hình mà **Kafka listener container bắt đầu Kafka transaction trước khi gọi business listener**. Listener đọc record từ một topic, xử lý dữ liệu và gửi kết quả sang topic khác bằng KafkaTemplate. Sau khi listener thành công, container đưa **consumed offsets** vào cùng transaction với các bản ghi đầu ra rồi commit. Nếu listener thất bại, transaction bị rollback: output Kafka thuộc transaction không trở thành committed và offset nguồn không được commit trong lần thử đó.

Đây là nền tảng của luồng **consume → process → produce** có tính nguyên tử trong phạm vi Kafka. Consumer-initiated transaction giúp tránh tình trạng output đã được ghi nhận nhưng offset nguồn chưa được commit, hoặc offset đã tiến mà output chưa được ghi nhận. Tuy nhiên, nó không có nghĩa listener chỉ chạy đúng một lần và **không tự mở rộng transaction sang database, REST API hay các hệ thống ngoài Kafka**.

## 1. Bài toán khi consume rồi produce

Giả sử một ứng dụng đọc event từ topic orders.created, chuẩn hóa payload, sau đó gửi event mới sang orders.normalized.

~~~text
orders.created
       |
       v
Spring Kafka @KafkaListener
       |
       +-- validate
       +-- transform
       +-- enrich
       |
       v
orders.normalized
~~~

Không có Kafka transaction, hai hành động dưới đây thường độc lập:

1. Produce event vào orders.normalized.
2. Commit offset của consumer group trên orders.created.

Nếu hệ thống crash giữa hai hành động, có thể xảy ra:

| Tình huống | Output | Offset đầu vào | Hệ quả |
|---|---|---|---|
| Crash trước khi produce | Chưa ghi | Chưa commit | Input có thể được đọc lại |
| Produce thành công rồi crash trước commit offset | Đã ghi | Chưa commit | Input có thể được đọc lại và tạo output trùng |
| Commit offset quá sớm rồi produce thất bại | Chưa ghi | Đã commit | Có nguy cơ mất output nghiệp vụ |

Consumer-initiated transaction xử lý vấn đề ở phạm vi Kafka bằng cách commit **output records và consumed offsets cùng một transaction**. Khi transaction abort, các records của transaction đó không hiển thị với consumer đọc theo read_committed và offset nguồn không tiến lên nhờ transaction lỗi.

## 2. Ai thực sự khởi tạo transaction?

Tên gọi consumer-initiated có thể gây hiểu nhầm rằng KafkaConsumer trực tiếp gọi beginTransaction(). Thực tế **transaction của Kafka do KafkaProducer cung cấp**. Spring Kafka listener container dùng transaction manager và transactional producer để tạo transaction khi đang xử lý một bản ghi tiêu thụ.

~~~text
KafkaConsumer.poll()
       |
       v
KafkaMessageListenerContainer
       |
       +-- bắt đầu Kafka transaction
       |
       v
Business @KafkaListener
       |
       +-- KafkaTemplate.send(...)
       |
       v
Container sendOffsetsToTransaction(...)
       |
       v
Kafka transaction commit / abort
~~~

Thành phần tham gia gồm:

- **ConsumerFactory** tạo KafkaConsumer đọc topic nguồn.
- **Listener container** quản lý poll loop, callback listener, assignment và transaction boundary.
- **Transactional ProducerFactory** tạo các KafkaProducer có transactional.id.
- **KafkaTransactionManager** hoặc KafkaAwareTransactionManager tương ứng với phiên bản Spring Kafka quản lý transaction.
- **KafkaTemplate** dùng producer thuộc transaction đang hoạt động để gửi output.
- **AfterRollbackProcessor** quyết định cách thử lại hoặc recovery khi transaction bị rollback.

Container quản lý vòng đời transaction; business listener không phải tự gọi producer.beginTransaction(), producer.sendOffsetsToTransaction() và producer.commitTransaction() bằng tay.

## 3. Luồng thành công: output và offset cùng commit

Ví dụ consumer group orders-transformer nhận record ở orders.created, partition 2, offset 51:

~~~text
Topic:     orders.created
Partition: 2
Offset:    51
Key:       order-1001
~~~

Trình tự xử lý khái quát:

1. Consumer poll và nhận record.
2. Listener container bắt đầu Kafka transaction.
3. Listener chuyển OrderCreated thành NormalizedOrder.
4. KafkaTemplate gửi NormalizedOrder đến orders.normalized trong transaction này.
5. Listener trả về thành công.
6. Container gửi consumed offset của consumer group vào transaction bằng cơ chế sendOffsetsToTransaction.
7. Container commit transaction.
8. Kafka công nhận output record và source offset cùng nhau.

~~~text
BEGIN TRANSACTION T1
    |
    +-- input: orders.created / P2 / offset 51
    |
    +-- output: orders.normalized / key order-1001
    |
    +-- sendOffsetsToTransaction:
    |       group orders-transformer
    |       orders.created / P2 -> 52
    |
COMMIT T1
    |
    +-- output committed
    +-- input offset 52 committed
~~~

**Vì sao commit offset 52 thay vì 51?** Kafka lưu committed offset là vị trí tiếp theo consumer group cần đọc. Nếu record ở offset 51 đã xử lý thành công thì vị trí tiếp theo thường là 52. Đây không phải offset gốc của record; original offset vẫn là 51.

Với batch listener, container có thể quản lý transaction cho toàn bộ batch theo cấu hình. Không giả định mọi lần poll luôn tương ứng đúng một transaction: ranh giới phụ thuộc listener là record hay batch và phiên bản container.

## 4. Luồng thất bại: transaction abort rồi retry

Giả sử listener đã gửi một output Kafka nhưng sau đó ném exception:

~~~text
BEGIN TRANSACTION T1
    |
    +-- consume orders.created/P2@51
    +-- produce orders.normalized (chưa committed)
    +-- exception từ listener
    |
ABORT TRANSACTION T1
    |
    +-- output T1 bị abort
    +-- consumed offset không commit bởi T1
    |
    v
AfterRollbackProcessor
    |
    +-- seek/điều phối record chưa xử lý
    +-- backoff và thử lại
    +-- hoặc recovery khi hết retry
~~~

Khi container abort, downstream consumer có isolation.level=read_committed sẽ không thấy output từ T1. Vì source offset chưa được commit bởi T1, record nguồn vẫn có thể được xử lý lại.

Trong lần thử mới T2, listener có thể chạy lại cùng record:

~~~text
T1: đọc offset 51 -> gửi output X -> lỗi -> ABORT
T2: đọc offset 51 -> gửi output X -> thành công -> COMMIT

Downstream read_committed:
  chỉ thấy output X của transaction đã commit
~~~

**Điểm cốt lõi:** transaction bảo vệ **kết quả Kafka được commit**, không ngăn listener code thực thi nhiều lần. Nếu listener đã gọi API bên ngoài hoặc ghi database trước khi abort, side effect đó có thể vẫn tồn tại.

## 5. Producer-initiated và consumer-initiated khác nhau

| Tiêu chí | Producer-initiated transaction | Consumer-initiated transaction |
|---|---|---|
| Điểm bắt đầu | Service method hoặc producer operation | Kafka listener container |
| Tác nhân kích hoạt | HTTP request, scheduler, command | Kafka consumer nhận record |
| Output | Nhiều Kafka records trong transaction | Kafka records do listener produce |
| Consumed offset | Không nhất thiết liên quan | Được container đưa vào transaction |
| Mục tiêu | Gửi nhiều record nguyên tử | Consume-process-produce nguyên tử trong Kafka |
| Xử lý lỗi | Rollback transaction do service quản lý | Container rollback, AfterRollbackProcessor xử lý record |

Với consumer-initiated transaction, không nên thêm @Transactional lên mọi @KafkaListener chỉ vì muốn Kafka transaction. Nếu container đã được gắn transaction manager, chính container tạo transaction trước khi listener được gọi.

Nếu ứng dụng cần transaction database và Kafka cùng lúc, hai transaction manager khác nhau không tự trở thành một distributed transaction nguyên tử.

## 6. Kafka transaction yêu cầu những gì?

Một cấu hình transaction đáng tin cậy cần đồng bộ nhiều thành phần:

- ProducerFactory hỗ trợ transaction và có transactionIdPrefix.
- KafkaTransactionManager dùng đúng ProducerFactory mà KafkaTemplate dùng.
- Listener container được cấu hình transaction manager.
- Consumer tắt auto-commit; container gửi offset qua transaction thay vì commit riêng.
- Listener không nuốt exception cần rollback.
- Downstream consumer dùng read_committed nếu phải loại bỏ output thuộc transaction abort.
- Kafka cluster hỗ trợ transactions với broker/transaction coordinator và cấu hình replication phù hợp.

~~~text
Transactional ProducerFactory
          |
          +--------> KafkaTransactionManager
          |                    |
          v                    v
     KafkaTemplate      Listener container
          |                    |
          +----- transaction --+
                               |
                          @KafkaListener
~~~

KafkaTemplate tham gia transaction nhờ transaction context phù hợp; chỉ tạo một KafkaTransactionManager bean trong Spring ApplicationContext **không chứng minh** mọi listener đã chạy transactional.

## 7. Cấu hình Spring Boot

Ví dụ ứng dụng Kafka-to-Kafka xử lý OrderCreated:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-transformer-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[acks]": all
    consumer:
      group-id: orders-transformer
      enable-auto-commit: false
      isolation-level: read_committed
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.orders.OrderCreated
        "[spring.json.trusted.packages]": com.example.orders
    listener:
      ack-mode: record
~~~

Các cấu hình chính:

- **transaction-id-prefix**: kích hoạt transactional producer factory; framework tạo transactional.id riêng cho transactional producers.
- **enable-auto-commit: false**: tránh consumer tự ghi offset độc lập với transaction của container.
- **isolation-level: read_committed**: consumer không nhận các transactional records đã abort trên topic nguồn.
- **acks=all**: yêu cầu acknowledgement tương ứng với mức durability; transactions có thêm điều kiện về broker và transaction coordinator.
- **ack-mode**: phối hợp với container; trong transactional listener, offset được đưa vào transaction theo semantics container.

Giá trị transaction-id-prefix trong ví dụ chỉ phù hợp cho một instance thử nghiệm. **Production phải bảo đảm các instance đang chạy đồng thời không tạo transactional.id trùng nhau.** Có thể gắn prefix với một instance ID riêng từ Kubernetes, deployment hoặc cấu hình môi trường.

Trong một ứng dụng Spring Boot phù hợp, khai báo producer.transaction-id-prefix có thể kích hoạt auto-configuration KafkaTransactionManager. Nếu ứng dụng có nhiều ProducerFactory, KafkaTemplate hoặc transaction manager, hãy wiring rõ ràng và kiểm tra listener container thực sự đã dùng manager mong muốn.

## 8. Cấu hình transaction manager và listener container tường minh

Nếu muốn tránh phụ thuộc hoàn toàn vào auto-configuration, có thể khai báo transaction manager từ transactional ProducerFactory:

~~~java
@Bean
KafkaTransactionManager<String, NormalizedOrder>
        kafkaTransactionManager(
                ProducerFactory<String, NormalizedOrder> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Sau đó gắn manager vào listener factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        transactionalListenerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                KafkaTransactionManager<String, NormalizedOrder> kafkaTxManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTxManager);
    return factory;
}
~~~

Đây là ví dụ theo API Spring Kafka có **setKafkaAwareTransactionManager**; ở các phiên bản cũ, kiểu hoặc setter có thể khác. Cần dùng đúng API của phiên bản Spring Kafka trong dự án. Tránh định nghĩa thêm bean KafkaTransactionManager thứ hai nếu Spring Boot đã tự tạo một bean tương đương mà không có chủ đích.

ProducerFactory phải đã có **transactionIdPrefix**. Chỉ tạo KafkaTransactionManager trên producer factory thông thường không đủ. KafkaTemplate cần dùng cùng ProducerFactory hoặc transaction infrastructure tương thích.

Ví dụ:

~~~java
@Bean
KafkaTemplate<String, NormalizedOrder> normalizedOrderKafkaTemplate(
        ProducerFactory<String, NormalizedOrder> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
~~~

Trong triển khai thật, ProducerFactory cần các serializer tương ứng, security, bootstrap servers và transaction ID prefix. Container factory cho listener phải được chọn đúng khi khai báo @KafkaListener.

## 9. Viết listener consume-process-produce

Ví dụ listener đọc orders.created rồi gửi orders.normalized:

~~~java
@Service
public class OrderTransformerListener {

    private final OrderMapper mapper;
    private final KafkaTemplate<String, NormalizedOrder> kafkaTemplate;

    public OrderTransformerListener(
            OrderMapper mapper,
            KafkaTemplate<String, NormalizedOrder> kafkaTemplate) {
        this.mapper = mapper;
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-transformer",
            containerFactory = "transactionalListenerFactory")
    public void handle(ConsumerRecord<String, OrderCreated> record) {
        NormalizedOrder normalized = mapper.normalize(record.value());

        kafkaTemplate.send(
                "orders.normalized",
                record.key(),
                normalized
        ).join();
    }
}
~~~

Hàm join() đợi CompletableFuture gửi Kafka hoàn tất và cho phép send failure xuất hiện như exception trước khi listener trả về. Nếu lỗi được truyền ra, container có thể rollback transaction. Không được bỏ qua các future lỗi rồi trả về bình thường như thể output đã được gửi thành công.

Trong một hệ thống tối ưu throughput, ứng dụng có thể gom futures và chờ tất cả trước khi trả về thay vì join từng send. Nhưng cần bảo đảm **mọi output cần thiết đã được chấp nhận đúng trong transaction** và lỗi được xử lý trước khi container commit.

Không gọi KafkaTemplate.executeInTransaction() bên trong listener để tự tạo một transaction producer **độc lập** nếu mục tiêu là gộp output với consumed offset do container quản lý. Một transaction khác có thể commit output riêng, làm mất tính nguyên tử mong muốn.

## 10. sendOffsetsToTransaction hoạt động ra sao?

Khi listener xử lý thành công, Spring Kafka đưa consumed offsets vào transaction của producer. Với record ở offset 51:

~~~text
orders.created / partition 2

offset 50: đã xử lý
offset 51: đang xử lý
offset 52: vị trí đọc tiếp theo

Transactional offset commit:
  group orders-transformer
  orders.created/P2 = 52
~~~

Container dùng thông tin group membership và các API Kafka tương ứng để chuyển offset vào transaction. Đây không phải consumer.commitSync() độc lập.

Nếu transaction abort, offset 52 không được commit từ transaction lỗi đó. Nếu transaction commit thành công, offset nguồn và output records có chung kết quả commit trong Kafka.

Không tự gọi consumer.commitSync() hoặc consumer.commitAsync() trong listener transactional để "cho chắc". Commit riêng ngoài transaction có thể phá vỡ semantics output + offset nguyên tử.

## 11. read_committed và read_uncommitted

Kafka broker có thể đã nhận output của transactional producer trước khi transaction được commit. Consumer dùng **read_uncommitted** có thể đọc cả record thuộc transaction đã abort. Consumer dùng **read_committed** chỉ trả về transactional records đã commit.

~~~text
Transaction T1:
  produce A
  produce B
  ABORT

Transaction T2:
  produce C
  COMMIT

Consumer read_committed:
  thấy C
  không thấy A, B
~~~

Nếu các service downstream không cấu hình read_committed, chúng có thể quan sát records đã abort và thực hiện side effect từ dữ liệu không được commit. Điều đó làm mất ý nghĩa quan trọng của transactional output đối với luồng xử lý tiếp theo.

Ví dụ consumer downstream:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: normalized-order-consumer
      isolation-level: read_committed
      enable-auto-commit: false
~~~

Read_committed vẫn đọc được records non-transactional hợp lệ. Đồng thời, một transaction đang mở ở đầu log có thể khiến read_committed consumer phải chờ ở **Last Stable Offset (LSO)**, làm tăng độ trễ dù broker đã nhận các records phía sau.

## 12. Exactly-once semantics có phạm vi nào?

Kafka transaction cung cấp nền tảng **exactly-once Kafka read-process-write** khi toàn bộ output cần bảo vệ được gửi transactional, consumed offsets thuộc cùng transaction và downstream chỉ đọc committed data.

Điều được bảo vệ:

- Các output Kafka của transaction cùng commit hoặc cùng abort.
- Consumed offsets được commit atomically cùng output trong phạm vi Kafka.
- Downstream read_committed không thấy aborted transactional output.

Điều **không** được bảo vệ chỉ bằng Kafka transaction:

- Java listener chắc chắn chỉ chạy một lần.
- Database transaction tự rollback khi Kafka abort.
- HTTP API, gửi email hoặc thanh toán tự undo.
- Hai Kafka clusters khác nhau tự commit cùng một transaction.
- Producer không transactional tự động tham gia transaction.

Khi ứng dụng crash trước commit, record nguồn có thể được đọc lại và listener chạy lần nữa. Điều quan trọng là những kết quả Kafka của lần xử lý bị abort không được công nhận.

Với external side effects, phải có idempotency, outbox hoặc cơ chế nhất quán khác nếu nghiệp vụ yêu cầu.

## 13. Exception và ranh giới rollback

Nếu listener ném RuntimeException và exception đi đến container, transaction có thể rollback. Nhưng nếu listener bắt exception và không ném lại, container có thể coi listener hoàn tất bình thường.

Ví dụ **không nên làm**:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderCreated event) {
    try {
        paymentService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Payment failed", ex);
        // Không throw lại: container có thể coi xử lý thành công.
    }
}
~~~

Nếu paymentService lỗi, code trên có thể khiến offset được commit dù nghiệp vụ chưa hoàn thành. Một cách an toàn hơn là xử lý log rồi rethrow:

~~~java
catch (RuntimeException ex) {
    log.error("Payment failed", ex);
    throw ex;
}
~~~

Hoặc tạo một exception nghiệp vụ phù hợp để transaction boundary và recovery policy nhận diện. Việc chọn exception retryable/non-retryable thuộc chiến lược xử lý lỗi, nhưng không nên nuốt lỗi rồi kỳ vọng container tự rollback.

## 14. AfterRollbackProcessor xử lý record sau abort

Với transactional listener, **AfterRollbackProcessor** là cơ chế quan trọng sau khi Kafka transaction rollback. Một implementation phổ biến là **DefaultAfterRollbackProcessor**.

~~~text
Listener exception
      |
      v
Abort Kafka transaction
      |
      v
AfterRollbackProcessor
      |
      +-- xác định offset cần giao lại
      +-- seek hoặc điều phối records
      +-- áp dụng BackOff
      +-- recover nếu hết retry
      |
      v
Consumer poll và xử lý lại
~~~

Khác với listener container không transactional thường cấu hình DefaultErrorHandler, transactional listener chủ yếu dùng after-rollback processing để giữ đúng semantics abort.

Nếu tự gắn một error handler cho transactional container, phải hiểu handler có **rethrow exception** hay không. Error handler xử lý xong và trả về bình thường có thể khiến container commit transaction vốn lẽ ra phải abort.

BackOff cần được giới hạn hợp lý. Retry vô hạn trong transaction processing có thể khiến một partition không tiến, tăng consumer lag và làm downstream bị thiếu output.

## 15. Recovery DLT sau rollback

Khi lỗi không thể xử lý sau nhiều lần retry, record có thể được chuyển sang DLT. Với transactional listener, cần phân biệt **transaction đã abort khi listener lỗi** và **transaction recovery dùng để publish DLT/commit recovered offset**.

~~~text
T1:
  consume input
  business listener lỗi
  ABORT

After rollback:
  backoff + retry
  ...
  hết attempts

Recovery:
  publish record lỗi vào DLT
  commit recovered input offset
  theo transaction/recovery semantics đã cấu hình
~~~

Không thể tiếp tục commit T1 sau khi đã abort. Spring Kafka hỗ trợ cấu hình DefaultAfterRollbackProcessor kết hợp ConsumerRecordRecoverer, ví dụ DeadLetterPublishingRecoverer, để recovery; trong một số cấu hình/phiên bản recovery có thể thực hiện trong **transaction mới** và commit recovered offset cùng DLT publish.

Những yếu tố cần xác định rõ:

1. Số lần retry và khoảng backoff.
2. Lỗi nào đủ điều kiện retry, lỗi nào recovery ngay.
3. DLT topic/partition và serializer có phù hợp không.
4. Recoverer publish thành công hay thất bại.
5. Recovered offset được commit lúc nào.
6. Nếu recovery transaction abort, record nguồn sẽ được giao lại như thế nào.

Không coi việc gọi recoverer là bằng chứng DLT đã ghi thành công. Phải quan sát kết quả publish và xử lý recovery failure.

## 16. Transactional.id và producer fencing

KafkaProducer dùng **transactional.id** để broker quản lý transaction và fence producer cũ sử dụng cùng identity. Spring Kafka ProducerFactory tạo các transactional.id bằng transactionIdPrefix và hậu tố phù hợp.

~~~text
Application instance A:
  transaction-id-prefix: pod-a-orders-tx-
  transactional.id:      pod-a-orders-tx-0

Application instance B:
  transaction-id-prefix: pod-b-orders-tx-
  transactional.id:      pod-b-orders-tx-0
~~~

Đây là giá trị minh họa. Trong production, các instance chạy **đồng thời** không nên vô tình dùng cùng transactional.id; chúng có thể fence lẫn nhau. Một instance mới cùng transactional.id có thể fence producer cũ, và đây là cơ chế bảo vệ Kafka khỏi hai producer ghi tiếp với cùng identity.

ProducerFencedException không nên được xử lý bằng cách tiếp tục retry trên chính producer đã bị fenced. Producer và container phải đi qua lifecycle phục hồi/restart thích hợp.

Khi vận hành, kiểm tra:

- Prefix có đủ phân biệt các pod/instance active không?
- Có chạy đồng thời phiên bản cũ và mới dùng cùng prefix không?
- Transactional producer cache có bị stale hoặc bị broker expire không?
- Có nhiều application contexts dùng cùng transactional.id ngoài ý muốn không?

## 17. Producer cache và vòng đời giao dịch

Spring Kafka có thể cache transactional producers để tái sử dụng. Khi concurrency cao, ứng dụng cần đủ producer capacity và các transactional IDs không xung đột.

Một số điểm quan trọng:

- Transactional producer yêu cầu producer factory có transactionIdPrefix.
- Producer cache, số thread và concurrency ảnh hưởng đến số producer có thể active.
- Broker có thời gian hết hạn transactional ID; producer idle lâu có thể gặp fencing khi được tái sử dụng.
- Các phiên bản Spring Kafka hỗ trợ **maxAge** cho DefaultKafkaProducerFactory để chủ động thay cached producer trước khi broker expiration.
- Thay đổi concurrency hoặc số replica có thể làm thay đổi số producer cần thiết; không giả định một KafkaTransactionManager chỉ có một KafkaProducer mãi mãi.

Không tăng concurrency chỉ vì transaction throughput thấp. Hãy đo consumer lag, producer request latency, transaction commit time, broker CPU và output partition count trước khi xác định bottleneck.

## 18. Rebalance trong lúc transaction đang chạy

Consumer group có thể rebalance khi pod restart, scale up/down, poll quá chậm hoặc member mất kết nối. Nếu partition đổi owner trong lúc listener đang xử lý, transaction có thể không commit offset hợp lệ theo consumer group membership hiện tại.

~~~text
Consumer A được giao P2@51
      |
      +-- bắt đầu T1
      +-- xử lý chậm
      |
Group rebalance
      |
P2 chuyển sang Consumer B
      |
Consumer A không còn ownership hợp lệ
      |
T1 có thể abort / commit offset thất bại
      |
Consumer B xử lý lại P2@51
~~~

Kafka transaction giảm nguy cơ ghi nhận dở dang trong Kafka; nhưng nếu Consumer A đã gọi API thanh toán trước khi mất ownership, thao tác đó có thể đã hoàn tất ngoài Kafka.

Cần dùng graceful shutdown, tránh listener chạy quá lâu, theo dõi rebalance và có idempotency cho external side effects. Với transaction coordinator và consumer group metadata, Kafka có cơ chế kiểm tra để tránh commit offset không hợp lệ từ member cũ.

## 19. transaction.timeout.ms và max.poll.interval.ms

Hai thông số liên quan đến thời gian nhưng có mục đích khác nhau:

| Thông số | Quy định | Nếu vượt ngưỡng |
|---|---|---|
| **transaction.timeout.ms** | Thời gian transaction có thể mở theo Kafka broker/producer | Transaction có thể bị broker abort hoặc commit thất bại |
| **max.poll.interval.ms** | Thời gian tối đa giữa các lần consumer poll theo group protocol | Consumer có thể mất membership và bị rebalance |

Ví dụ listener xử lý batch lớn, gọi REST API vài phút và gửi nhiều output. Dù max.poll.interval.ms đủ lớn, Kafka transaction vẫn có thể timeout. Ngược lại, transaction timeout đủ lớn nhưng poll bị trì hoãn quá lâu có thể gây rebalance.

Các thực hành cần thiết:

- Đo listener processing time, số record mỗi batch và transaction duration.
- Tránh giữ transaction mở khi phải chờ external service rất lâu.
- Điều chỉnh timeout dựa trên SLO và dữ liệu đo được, không tăng vô hạn.
- Cân nhắc tách công việc dài thành workflow khác thay vì giữ Kafka transaction mở.
- Đừng đồng nhất transaction timeout với timeout của HTTP client hoặc database.

Một transaction dài còn có thể khiến downstream read_committed consumer chờ ở Last Stable Offset cho đến khi transaction được giải quyết.

## 20. Database update không thuộc Kafka transaction

Giả sử listener vừa cập nhật database vừa publish output Kafka:

~~~text
orders.created
      |
      v
Kafka listener
      |
      +-- UPDATE orders SET status = ...
      |
      +-- KafkaTemplate.send("orders.normalized")
      |
      v
Kafka transaction COMMIT hoặc ABORT
~~~

Nếu UPDATE database thành công nhưng Kafka transaction abort, record Kafka nguồn có thể được xử lý lại. Lần retry có thể cập nhật database lần nữa.

Kafka transaction **không tự rollback database**. Dù dùng các cơ chế transaction synchronization của Spring để phối hợp commit theo thứ tự, đó thường là best-effort coordination, không phải atomic distributed XA transaction giữa Kafka và database.

Các giải pháp tùy nghiệp vụ:

- **Idempotent update:** lưu event ID/version trong database để lần xử lý lặp không tạo side effect mới.
- **Transactional outbox:** ghi state và event vào outbox trong cùng database transaction rồi publish riêng.
- **Saga/workflow:** điều phối các bước phân tán và hành động bù trừ.
- **Tách boundary:** Kafka-to-Kafka transactional, database side effect xử lý theo chính sách nhất quán riêng.

Nếu yêu cầu là "database và Kafka output phải luôn commit cùng nhau không có trường hợp trung gian", chỉ bật transaction-id-prefix trên Kafka producer chưa đủ.

## 21. External API và tính idempotent

Một listener có thể gọi API thanh toán trước khi transaction Kafka commit:

~~~text
Transaction T1:
  gọi payment API -> thành công
  send Kafka output -> lỗi
  abort Kafka transaction

Transaction T2:
  xử lý lại input
  có nguy cơ gọi payment API lần hai
~~~

Khi API hỗ trợ idempotency key, nên dùng event ID ổn định:

~~~java
public void charge(PaymentRequested event) {
    paymentClient.charge(
            event.paymentId(),
            event.amount(),
            event.eventId()); // idempotency key
}
~~~

Đoạn mã minh họa một client API tự định nghĩa; cú pháp cụ thể phụ thuộc hệ thống thanh toán. Nếu external API không hỗ trợ idempotency, ứng dụng cần một trạng thái deduplication/reconciliation riêng.

Một side effect không thuộc Kafka transaction có thể xảy ra nhiều lần dù Kafka output cuối cùng chỉ có một bản committed. Đó là lý do không nên nói consumer-initiated transaction bảo đảm exactly-once cho mọi thao tác nghiệp vụ.

## 22. Batch listener và rollback

Batch listener có thể xử lý nhiều records trong một lần gọi. Nếu container quản lý một transaction cho batch, tất cả output Kafka được gửi trong transaction đó sẽ cùng commit hoặc abort theo kết quả callback.

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-transformer",
        containerFactory = "transactionalBatchListenerFactory")
public void handleBatch(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        NormalizedOrder normalized =
                mapper.normalize(record.value());

        kafkaTemplate.send(
                "orders.normalized",
                record.key(),
                normalized
        ).join();
    }
}
~~~

Ví dụ cần một listener factory có batch mode và Kafka transaction manager phù hợp. Nếu một record giữa batch thất bại, transaction có thể abort, khiến output Kafka đã gửi trong chính transaction đó không hiển thị với read_committed.

Batch lớn tăng transaction duration và chi phí retry. Cần cân nhắc max.poll.records, timeouts, side effects và cách AfterRollbackProcessor xử lý batch, thay vì mặc định một lỗi chỉ retry đúng một record.

## 23. Non-blocking retry topic có kết hợp được không?

Spring Kafka hỗ trợ @RetryableTopic để gửi record thất bại sang retry topic có delay. Tuy nhiên, trong các cấu hình Spring Kafka phổ biến, **non-blocking retry không được kết hợp trực tiếp với container Kafka transactions**.

Transaction của consumer-initiated processing có thể được rollback và xử lý bởi AfterRollbackProcessor, trong khi non-blocking retry có cơ chế forward record sang retry topic và commit tiến độ xử lý theo topology riêng. Hai cơ chế có ranh giới transaction và ordering khác nhau.

Không nên chỉ thêm @RetryableTopic vào transactional listener rồi kỳ vọng toàn bộ retry topology và consumed offsets đều tự thuộc cùng Kafka transaction.

Nếu cần delay dài, có thể thiết kế một workflow riêng với transaction boundaries rõ ràng. Với listener transactional, thường bắt đầu từ blocking retry có giới hạn và recovery DLT theo transaction semantics phù hợp.

## 24. Quan sát transaction trong production

Các chỉ số quan trọng:

- Số transaction bắt đầu, commit thành công và abort.
- Transaction duration p50/p95/p99.
- Transaction timeout và producer fencing error.
- Listener processing latency, error rate, retries và recovery.
- Consumer lag theo partition, rebalance rate và thời gian rebalance.
- Producer send/commit latency, broker errors và request retries.
- Số record được chuyển DLT và DLT publish failure.
- Consumer downstream read_committed lag.
- Producer cache size/utilization và số transaction IDs active.

Một log ứng dụng có thể ghi:

~~~text
eventId=EVT-104
listener=orders-transformer
source=orders.created/P2/51
outputTopic=orders.normalized
transactionOutcome=aborted
exceptionClass=DownstreamTimeoutException
retryScheduled=true
~~~

Đây là ví dụ structured log ứng dụng, không phải định dạng Kafka tự sinh. Original topic/partition/offset và event ID nên nằm trong log hoặc trace, không nên làm metric labels có cardinality cao.

Khi lag tăng nhưng committed output không tăng, hãy phân biệt listener chậm, transaction abort lặp, producer bị fenced, transaction coordinator lỗi và read_committed consumer đang chờ open transaction.

## 25. Kiểm thử failure scenarios

Nên dùng Kafka test broker thực (ví dụ Testcontainers hoặc EmbeddedKafka) và một downstream consumer có isolation.level=read_committed.

### Case 1: happy path

1. Produce input event vào orders.created.
2. Listener transform và gửi output.
3. Đợi transaction commit.
4. Xác nhận consumer read_committed nhận output.
5. Xác nhận committed offset của consumer group tiến tới vị trí sau input.

### Case 2: exception sau send

1. Listener gửi Kafka output trong transaction.
2. Cố ý ném exception trước khi callback kết thúc.
3. Xác nhận transaction abort.
4. Xác nhận consumer read_committed không thấy output của lần thử lỗi.
5. Xác nhận record nguồn được retry hoặc recovery theo policy.

### Case 3: crash trước commit

1. Consumer đọc input và gửi output trong transaction.
2. Dừng process trước commit.
3. Khởi động lại consumer group.
4. Xác nhận record nguồn được xử lý lại nếu chưa có offset committed.
5. Xác nhận chỉ output committed xuất hiện với read_committed.

### Case 4: producer fencing

1. Giả lập hai instance dùng trùng transactional.id trong môi trường test.
2. Quan sát producer fencing và transaction failure.
3. Sửa prefix phân biệt instance.
4. Xác nhận hệ thống không tự fence giữa các pod còn active.

### Case 5: side effect ngoài Kafka

1. Listener cập nhật database hoặc gọi API.
2. Cố ý abort Kafka transaction sau side effect.
3. Xác nhận side effect ngoài Kafka có thể đã xảy ra.
4. Chạy lại input và kiểm chứng idempotency.

Không kết luận exactly-once chỉ từ happy path. Test cần bao phủ các ranh giới produce, offset commit, abort, crash và replay.

## 26. Các lỗi cấu hình thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| KafkaTemplate báo không có transaction | ProducerFactory hoặc listener container không transactional | Kiểm tra transaction-id-prefix, transaction manager và factory |
| Output bị trùng khi retry | Template không cùng transaction hoặc có side effect ngoài Kafka | Kiểm tra producer factory, read_committed và idempotency |
| ProducerFencedException | transactional.id bị trùng hoặc producer stale | Kiểm tra prefix mỗi instance, restart và producer cache |
| Commit transaction lỗi sau xử lý lâu | Transaction timeout hoặc mất group membership | Đo duration, max.poll.interval.ms và rebalance |
| Downstream thấy aborted output | Consumer dùng read_uncommitted | Dùng read_committed nếu cần semantics commit |
| Record nguồn bị bỏ qua dù listener lỗi | Exception bị nuốt hoặc offset commit riêng | Kiểm tra rethrow, ack mode và transaction boundary |
| DLT không nhận record sau retry | Recoverer, serializer hoặc recovery transaction lỗi | Kiểm tra producer, DLT topic và AfterRollbackProcessor |
| Output không visible dù producer đã send | Transaction chưa commit hoặc đã abort | Kiểm tra transaction outcome và consumer isolation |
| Database tạo dữ liệu trùng | Side effect nằm ngoài Kafka transaction | Bổ sung idempotency hoặc outbox |

## 27. Những hiểu nhầm phổ biến

**KafkaConsumer trực tiếp tạo transaction.** Không đúng. Trong Spring Kafka, listener container dùng transactional producer và transaction manager để tạo transaction khi consume.

**Chỉ cần @Transactional trên @KafkaListener là đủ.** Không đúng. Cần producer factory transactional và listener container gắn đúng transaction manager.

**KafkaTemplate nào cũng tự tham gia transaction.** Không đúng. ProducerFactory và transaction context phải tương thích.

**Transaction chỉ commit output records.** Không đúng. Điểm quan trọng của consumer-initiated transaction là gộp cả consumed offsets với output.

**Xử lý offset 51 thì commit offset 51.** Không đúng theo quy ước group committed offset là vị trí tiếp theo; thường là 52.

**Listener chỉ chạy một lần vì đã bật exactly-once.** Không đúng. Listener có thể chạy lại sau abort, crash hoặc rebalance; Kafka transaction bảo vệ committed results.

**Kafka rollback sẽ undo database/API.** Không đúng. Cần idempotency, transactional outbox hoặc workflow phù hợp.

**Downstream read_uncommitted là đủ để kiểm chứng transaction.** Không đúng khi cần loại aborted output; dùng read_committed.

**Có KafkaTransactionManager bean nghĩa là mọi listener transactional.** Không đúng. Cần kiểm tra listener container cụ thể.

**ProducerFencedException có thể bỏ qua rồi tiếp tục dùng cùng producer.** Không đúng. Producer đã bị fenced phải được xử lý theo lifecycle transaction manager.

**Non-blocking retry topic luôn hoạt động với container transaction.** Không đúng. Cần xem các giới hạn hỗ trợ của Spring Kafka và thiết kế đúng transaction boundary.

## 28. Quy trình thiết kế consumer-initiated transaction

Khi xây dựng Kafka-to-Kafka pipeline, nên thực hiện:

1. Xác định topic nguồn, topic đích và mọi side effect ngoài Kafka.
2. Xác định yêu cầu nguyên tử giữa output Kafka và consumed offset.
3. Cấu hình transactional ProducerFactory với transactionIdPrefix không xung đột giữa các instance active.
4. Tạo KafkaTransactionManager/KafkaAwareTransactionManager phù hợp với phiên bản Spring Kafka.
5. Gắn transaction manager vào listener container factory sử dụng bởi listener.
6. Đảm bảo KafkaTemplate dùng ProducerFactory và transaction context của container.
7. Tắt consumer auto-commit, không commit offset riêng ngoài Kafka transaction.
8. Dùng read_committed ở downstream khi cần bỏ qua aborted transactional output.
9. Để lỗi cần rollback được truyền ra container; cấu hình AfterRollbackProcessor và retry có giới hạn.
10. Thiết kế DLT và recovered offset commit theo recovery transaction phù hợp.
11. Bảo vệ database/API bằng idempotency hoặc outbox.
12. Theo dõi commit/abort, transaction duration, fencing, rebalance và consumer lag.
13. Kiểm thử exception sau send, crash trước commit, producer fencing và external side effects.

**Consumer-initiated transaction** là cơ chế then chốt để Spring Kafka thực hiện consume-process-produce với **output và consumed offset được commit nguyên tử trong Kafka**. Nó xử lý nguy cơ không nhất quán giữa output và tiến độ consumer khi xảy ra lỗi, nhưng không loại bỏ việc listener chạy lại và không mở rộng tính nguyên tử sang hệ thống ngoài Kafka. Thiết kế an toàn cần phối hợp producer transaction, container transaction manager, read_committed, rollback/recovery, transactional.id duy nhất giữa các instance và idempotency cho mọi side effect nghiệp vụ.
