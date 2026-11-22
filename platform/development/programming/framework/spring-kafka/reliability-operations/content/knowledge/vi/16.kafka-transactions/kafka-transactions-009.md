# Listener container transaction

Trong Spring Kafka, **listener container transaction** là cơ chế để listener container quản lý Kafka transaction xung quanh việc tiêu thụ record. Với mô hình **consume–process–produce**, ứng dụng đọc một Kafka topic, xử lý và ghi sang topic khác; container có thể đưa **output records** và **offset đã xử lý của consumer** vào cùng một Kafka transaction. Khi transaction commit, cả output lẫn tiến độ xử lý có hiệu lực. Nếu transaction abort, output chưa commit không hiển thị với consumer `read_committed` và offset đầu vào không được xác nhận trong transaction đó.

Đây là nền tảng cho **exactly-once semantics của pipeline Kafka-to-Kafka**, nhưng không có nghĩa Java listener chỉ chạy một lần và **không** tự bảo đảm exactly-once cho database, HTTP API, thanh toán hoặc email. Khi transaction rollback hay process crash, listener có thể được gọi lại; side effect ngoài Kafka phải có cơ chế idempotency.

## 1. Vòng đời của một Kafka transaction do container khởi tạo

~~~text
Kafka consumer poll()
        |
        v
Container mở Kafka transaction
        |
        v
@KafkaListener nhận record
        |
        +--- KafkaTemplate gửi output records trong transaction
        |
        +--- Xử lý thành công?
                  |
             +----+----+
             |         |
            Có        Không
             |         |
             v         v
Container đưa       Abort Kafka
offset vào Kafka    transaction
transaction             |
             |          v
             v       After-rollback
Commit Kafka tx      retry/recovery
             |
             v
Output + offset
cùng được commit
~~~

Container bắt đầu transaction trước khi gọi listener, sau đó điều phối việc đưa offset tương ứng vào transaction và commit khi listener kết thúc thành công. Nếu listener ném exception, transaction bị rollback và record có thể được xử lý lại theo cơ chế rollback processor.

Không tự gọi `consumer.commitSync()` để “chốt offset cho nhanh” trong một listener transactional. Offset cần được phối hợp **bên trong** Kafka transaction do container quản lý.

## 2. Exactly-once trong phạm vi nào?

Giả sử consumer nhận `OrderApproved` từ `orders.approved` và gửi `ShipmentRequested` sang `shipments.requested`.

Nếu không có transaction giữa output và offset, có thể xảy ra:

1. Output đã gửi nhưng process dừng trước khi commit offset: sau restart input được giao lại và xuất thêm output.
2. Offset input được commit nhưng output gửi thất bại: event đầu vào bị bỏ qua dù chưa có output.

Kafka transaction cho phép gộp output và input offset:

| Kết quả | Output Kafka | Offset input |
|---|---|---|
| Transaction commit | Consumer `read_committed` nhìn thấy | Offset được commit trong giao dịch |
| Transaction abort | Output trong giao dịch không được nhìn thấy bởi `read_committed` | Không được commit bằng giao dịch đó |
| Transaction còn mở | Output chưa sẵn sàng với `read_committed` | Chưa có kết quả commit |

Một record có thể bị **listener thực thi nhiều lần** sau rollback. Kết quả đã commit trên Kafka vẫn có semantics phù hợp với transaction. Không suy luận từ chữ “exactly-once” rằng mọi side effect được thực thi một lần duy nhất.

## 3. Các thành phần của listener transaction

| Thành phần | Vai trò |
|---|---|
| `ConcurrentMessageListenerContainer` | Poll record, chạy listener, quản lý transaction và offset |
| `ConsumerFactory` | Tạo Kafka consumer đầu vào |
| `ProducerFactory` | Tạo transactional Kafka producer |
| `KafkaTransactionManager` | Điều phối transaction qua producer factory |
| `KafkaTemplate` | Publish record Kafka và tham gia transaction hiện hành khi dùng đúng producer factory |
| `DefaultAfterRollbackProcessor` | Điều phối xử lý record sau rollback |
| `DeadLetterPublishingRecoverer` | Có thể ghi record lỗi sang Dead Letter Topic (DLT) |
| Consumer `read_committed` | Chỉ thấy transactional records đã commit, không thấy records abort |

Listener container tạo ra từ `@KafkaListener` thường được quản lý qua `KafkaListenerEndpointRegistry`. Để có transaction, cần bảo đảm container thực sự được gắn Kafka transaction manager và `KafkaTemplate` dùng producer factory transactional phù hợp.

Trong một listener đã do container khởi tạo Kafka transaction, thường **không cần** thêm `@Transactional` chỉ để mở transaction cho Kafka output. `@Transactional` có thể còn được dùng để mở **database transaction** nhưng đó là resource khác.

## 4. Cấu hình Spring Boot

Ví dụ cấu hình transactional producer và record listener:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example:9092,kafka-2.example:9092
    producer:
      transaction-id-prefix: order-transform-instance-01-
      acks: all
    consumer:
      group-id: order-transformer
      enable-auto-commit: false
      isolation-level: read_committed
    listener:
      ack-mode: record
~~~

Giải thích:

- `transaction-id-prefix` cho phép producer factory tạo transactional producer. Prefix phải **duy nhất giữa các instance chạy đồng thời** có nguy cơ tạo trùng transactional ID. Khi chạy nhiều pod, inject prefix riêng qua hệ thống cấu hình.
- `acks: all` phù hợp với yêu cầu durability của transactional publishing.
- `enable-auto-commit: false` bảo đảm Kafka client không tự commit offset ngoài container. Trong Spring Kafka, container cũng chủ động điều phối auto commit; khai báo tường minh giúp ý định rõ ràng.
- `isolation-level: read_committed` bảo consumer không đọc transaction đã abort. Điều này đặc biệt quan trọng trên **consumer của output topic**.
- `ack-mode: record` minh họa việc xử lý tiến độ theo record; offset thực tế được container đưa vào transaction theo cấu hình listener.

Với Spring Boot auto-configuration, khai báo transactional producer factory có thể khiến Kafka transaction manager được tạo và áp dụng tự động. Nếu có custom `ConcurrentKafkaListenerContainerFactory`, phải xác nhận wiring; **đừng cho rằng mọi listener đều transactional chỉ vì YAML có prefix**.

Ví dụ prefix cho ba pod:

~~~text
pod-a -> order-transform-a-
pod-b -> order-transform-b-
pod-c -> order-transform-c-
~~~

Không dùng chung prefix cho tất cả replica đang chạy. Một producer mới có cùng `transactional.id` có thể fence producer cũ.

## 5. Cấu hình container factory bằng Java

Với ứng dụng tự tạo factory, có thể gắn `KafkaTransactionManager` vào container:

~~~java
@Configuration
public class TransactionalListenerConfiguration {

    @Bean
    KafkaTransactionManager<String, ShipmentRequested> shipmentTransactionManager(
            ProducerFactory<String, ShipmentRequested> producerFactory) {

        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderApproved>
    orderTransactionalListenerFactory(
            ConsumerFactory<String, OrderApproved> consumerFactory,
            KafkaTransactionManager<String, ShipmentRequested> transactionManager) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderApproved>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
               .setKafkaAwareTransactionManager(transactionManager);
        factory.getContainerProperties()
               .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Ví dụ dùng API `setKafkaAwareTransactionManager` của những phiên bản Spring Kafka hỗ trợ; phiên bản cũ có cách đặt transaction manager khác. Nếu Boot đã tạo transaction manager, nên inject/reuse bean đó thay vì tạo manager thứ hai mà không kiểm soát producer factory.

Type đầu vào là `OrderApproved`, còn output có thể là `ShipmentRequested`: chúng không bắt buộc cùng loại Java. Điểm quan trọng là producer factory của manager phải là **cùng producer factory** mà `KafkaTemplate` dùng để publish output muốn được bao bọc trong transaction.

Listener tương ứng:

~~~java
@Component
public class OrderListener {

    private final KafkaTemplate<String, ShipmentRequested> kafkaTemplate;

    public OrderListener(
            KafkaTemplate<String, ShipmentRequested> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        id = "order-transactional-listener",
        topics = "orders.approved",
        groupId = "order-transformer",
        containerFactory = "orderTransactionalListenerFactory")
    public void onOrder(OrderApproved event) {

        ShipmentRequested shipment = new ShipmentRequested(
            event.orderId(),
            event.customerId(),
            event.approvedAt()
        );

        kafkaTemplate.send(
            "shipments.requested",
            event.orderId(),
            shipment
        );
    }
}
~~~

Listener không tự bắt đầu/commit/abort transaction trong code: container điều phối các thao tác ấy. Nếu ứng dụng có nhiều `KafkaTemplate` hoặc nhiều producer factory, cần tránh inject nhầm một producer không transactional.

## 6. Đường đi khi xử lý thành công

Giả sử consumer đọc `orders.approved-1@204`:

| Bước | Hoạt động | Trạng thái |
|---|---|---|
| 1 | Container poll offset 204 | Record chưa xác nhận |
| 2 | Container mở Kafka transaction | Transaction đang chạy |
| 3 | Listener tạo và gửi `ShipmentRequested` | Output chưa commit |
| 4 | Listener trả về không ném exception | Xử lý thành công ở mức listener |
| 5 | Container đưa offset input phù hợp vào transaction | Output và offset cùng transaction |
| 6 | Transaction commit | Được công bố cùng nhau |
| 7 | Consumer downstream `read_committed` đọc output | Tiến độ input đã được xác nhận |

Hãy xem đây là thứ tự **khái niệm**; Spring Kafka quản lý chi tiết producer/consumer API và phạm vi transaction theo loại listener/ack mode. Không viết lại các bước này bằng `KafkaProducer.commitTransaction()` thủ công trong `@KafkaListener`.

## 7. Đường đi khi listener thất bại

Ví dụ listener gửi output rồi ném exception:

~~~java
@KafkaListener(
    topics = "orders.approved",
    containerFactory = "orderTransactionalListenerFactory")
public void onOrder(OrderApproved event) {

    kafkaTemplate.send(
        "shipments.requested",
        event.orderId(),
        toShipment(event)
    );

    if (!availabilityService.isReady()) {
        throw new TemporaryDependencyException("Dependency unavailable");
    }
}
~~~

Khi exception được chuyển lên container, Kafka transaction bị rollback. Output chưa committed trong transaction sẽ không hiển thị đối với consumer `read_committed`. Offset input cũng không được commit trong transaction đã abort.

~~~text
beginTransaction
  -> send output trong giao dịch
  -> listener throws exception
  -> abortTransaction
  -> after-rollback processing
  -> seek/retry hoặc recover theo chính sách
~~~

Không nên **nuốt exception** nếu việc xử lý thực sự thất bại:

~~~java
// Sai nếu record thất bại nhưng listener trả về bình thường.
try {
    remoteService.call(event);
}
catch (Exception ex) {
    log.error("Remote call failed", ex);
    // Không ném lại: container có thể commit transaction.
}
~~~

Nếu ứng dụng chủ động chấp nhận lỗi như một trạng thái nghiệp vụ thành công, quyết định đó phải được mô hình hóa rõ ràng, không phải vô tình biến failure thành success.

## 8. Offset, ack mode và transaction

Kafka container kết hợp offset mà nó xác định đã xử lý với transaction đang chạy. Khi transaction thành công, offset và output records commit cùng nhau. Cơ chế liên quan là `sendOffsetsToTransaction`, nhưng listener **không tự gọi API này** khi container đã chịu trách nhiệm.

Những điểm cần nhớ:

- `enable.auto.commit` của Kafka consumer không được tự commit thay cho container transaction.
- Ack mode ảnh hưởng khi nào container coi các record là đã xử lý; với transactional listener, offset được commit **theo giao dịch**.
- Với record listener và batch listener, phạm vi xử lý lỗi/rollback có thể khác nhau. Một batch gặp lỗi giữa chừng có thể làm transaction của batch rollback, và các record đã gọi trước đó có thể bị giao lại.
- DLT/recovery có thể làm tiến offset của một record đã được quyết định không retry nữa, nhưng phải cấu hình recovery transaction chính xác.

Commit offset bằng `consumer.commitSync()` trong listener hoặc dùng producer riêng nằm ngoài transaction sẽ làm suy yếu atomicity Kafka-to-Kafka.

## 9. Vì sao cần read_committed ở downstream?

Kafka broker có thể chứa các record được transactional producer gửi nhưng transaction chưa commit hoặc về sau bị abort. Consumer cấu hình `read_uncommitted` có thể thấy cả dữ liệu thuộc aborted transaction.

Consumer muốn chỉ nhìn thấy hiệu quả của transaction đã commit nên cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

`read_committed` cũng đọc được non-transactional records bình thường. Khi có transaction đang mở, consumer có thể bị giới hạn đọc bởi **Last Stable Offset (LSO)**. Vì thế, độ trễ quan sát trên output topic có thể tăng khi transaction dài hoặc bị treo.

Phân biệt:

- **Committed consumer group offset:** tiến độ tiêu thụ.
- **Committed transaction:** Kafka writes và offsets trong giao dịch đã có hiệu lực.
- **LSO:** ranh giới đọc an toàn cho consumer `read_committed`.

Không gọi pipeline “exactly-once” rồi để consumer output đọc `read_uncommitted` khi ứng dụng dựa vào việc che aborted records.

## 10. Transactional ID và producer fencing

Mỗi Kafka transactional producer có `transactional.id`. Broker dùng transactional ID và producer epoch để ngăn producer cũ tiếp tục publish như thể vẫn có quyền sở hữu giao dịch. Nếu instance khác tạo producer dùng cùng ID, producer trước đó có thể bị **fenced**.

~~~text
Sai khi chạy song song:
  instance-A: tx prefix = orders-tx-
  instance-B: tx prefix = orders-tx-

Có thể tạo transactional.id trùng nhau.

Định hướng đúng:
  instance-A: tx prefix = orders-tx-A-
  instance-B: tx prefix = orders-tx-B-
~~~

Spring Kafka sinh transactional ID từ prefix và hậu tố/chiến lược quản lý producer theo phiên bản. Prefix nên được kiểm soát ở cấp instance/pod; không chỉ đặt một giá trị cố định cho toàn bộ replica.

Nếu thấy `ProducerFencedException` hoặc lỗi tương tự:

1. Kiểm tra có hai process cùng dùng transactional ID hay không.
2. Kiểm tra rolling deployment có overlap giữa phiên bản cũ và mới.
3. Kiểm tra producer cache, concurrency và transaction manager.
4. Kiểm tra broker transaction coordinator và timeout.
5. Không bắt lỗi fencing rồi tiếp tục gửi như producer vẫn hợp lệ.

## 11. Transaction timeout và long-running listener

Một Kafka transaction không nên mở vô thời hạn. Các cấu hình liên quan:

| Cấu hình | Ý nghĩa |
|---|---|
| `transaction.timeout.ms` | Thời gian tối đa của Kafka transaction theo producer/broker |
| Broker `transaction.max.timeout.ms` | Giới hạn transaction timeout được chấp nhận |
| `max.poll.interval.ms` | Giới hạn thời gian giữa các poll của consumer |
| `max.poll.records` | Giới hạn record lấy trong một lần poll |
| Producer `maxAge` trong Spring Kafka | Hỗ trợ thay thế producer idle trước khi transactional ID hết hạn ở các phiên bản phù hợp |

Nếu listener gọi HTTP API có thể treo hàng phút, transaction giữ mở lâu, làm tăng nguy cơ timeout và giữ output chưa visible với downstream `read_committed`. Nếu consumer vượt `max.poll.interval.ms`, group rebalance có thể làm thêm tình huống fail/rollback.

Cách giảm rủi ro:

- Đặt timeout cụ thể cho HTTP/database dependency.
- Giảm thời gian xử lý bên trong transaction.
- Giới hạn batch size theo khả năng xử lý thực tế.
- Dùng workflow/outbox cho tác vụ dài thay vì giữ Kafka transaction nhiều phút.
- Chọn retry budget và backoff dựa trên thời gian phục hồi dependency.

## 12. Error handling: DefaultAfterRollbackProcessor

Đối với listener container transactional, exception thường dẫn đến rollback, sau đó Spring Kafka dùng `DefaultAfterRollbackProcessor` để quyết định seek/retry/recover. Đây là đường khác với `DefaultErrorHandler` thông thường ở listener không transactional.

Ví dụ cấu hình after-rollback processor:

~~~java
@Bean
DefaultAfterRollbackProcessor<String, OrderApproved>
orderAfterRollbackProcessor(DeadLetterPublishingRecoverer recoverer) {

    return new DefaultAfterRollbackProcessor<>(
        (record, exception) -> recoverer.accept(record, exception),
        new FixedBackOff(1_000L, 3L)
    );
}
~~~

Áp dụng vào factory thích hợp:

~~~java
factory.setAfterRollbackProcessor(orderAfterRollbackProcessor);
~~~

Ở ví dụ trên, `FixedBackOff` chờ một giây giữa các lần retry, tối đa ba lần retry theo semantics của Spring Framework. Đối với exception permanent, nên có phân loại non-retryable thích hợp để tránh retry cùng payload vô ích.

**Recovery và transaction mới:** Nếu cần publish record đã recover sang DLT **và** commit offset nguồn trong một transaction recovery mới, cần cấu hình tính năng như `commitRecovered` và `KafkaTemplate/KafkaOperations` tương ứng của `DefaultAfterRollbackProcessor` theo phiên bản Spring Kafka. Không giả định rằng chỉ gọi `DeadLetterPublishingRecoverer` là đủ để DLT và tiến offset tự động atomic.

Nếu publish DLT thất bại, không nên coi record đã được recover. Container phải tiếp tục xử lý failure theo cơ chế đã định để tránh bỏ mất record.

## 13. Đừng mặc định kết hợp @RetryableTopic với transaction

`@RetryableTopic` triển khai non-blocking retry qua các topic trung gian và delay. Trong nhiều phiên bản Spring Kafka, non-blocking retry **không hỗ trợ kết hợp trực tiếp với container transactions** theo cấu hình thông thường.

Lý do là việc forward record qua retry topic, tiến offset đầu vào, trì hoãn xử lý và transaction rollback phải được xác định ranh giới nhất quán. Nếu chỉ gắn thêm `@RetryableTopic` vào listener transactional, hệ thống có thể không đạt semantics mong muốn.

Khi cần retry:

- Lỗi ngắn: cân nhắc retry/backoff qua after-rollback processor.
- Lỗi permanent: recover sang DLT có kiểm soát.
- Retry dài hạn: thiết kế workflow/retry topology riêng, quy định rõ transaction boundary, ordering và idempotency.
- Không bật nhiều tầng retry mà không tính tổng số lần xử lý và các failure window.

## 14. Database transaction khác Kafka transaction

Listener có thể vừa ghi database vừa gửi Kafka output:

~~~java
@KafkaListener(
    topics = "payments.received",
    containerFactory = "transactionalPaymentListenerFactory")
public void onPayment(PaymentReceived event) {

    paymentService.saveState(event); // DB transaction riêng
    kafkaTemplate.send(
        "payments.applied",
        event.paymentId(),
        new PaymentApplied(event.paymentId())
    );
}
~~~

Nếu `paymentService.saveState` dùng `@Transactional` của database, đó là **database transaction**. Kafka container transaction là **một transaction khác**; Spring không mặc định tạo XA transaction atomic giữa hai hệ thống.

Tình huống rủi ro:

~~~text
Kafka container transaction bắt đầu
  -> DB transaction bắt đầu
  -> Ghi DB thành công
  -> DB commit thành công
  -> Kafka transaction commit thất bại
  -> Record đầu vào được giao lại
  -> DB có thể bị ghi trùng nếu không idempotent
~~~

Kafka transaction không rollback được DB commit đã hoàn tất. Cũng không thể rollback email hoặc HTTP request đã được dịch vụ bên ngoài nhận.

Các mô hình phổ biến:

1. **Inbox/idempotent consumer:** ghi event ID đã xử lý và business state trong cùng database transaction.
2. **Transactional outbox:** business state và event cần phát được lưu chung trong database transaction; publisher gửi event sau, với deduplication.
3. **Saga/state machine:** nhiều bước qua các service dùng trạng thái bền vững và compensation.
4. **Idempotency key:** dịch vụ HTTP/payment hỗ trợ nhận lại cùng request mà không lặp tác động.

Không gắn `@Transactional` một cách máy móc rồi kết luận database và Kafka đã được commit nguyên tử.

## 15. Idempotency trong listener có side effect ngoài Kafka

Ví dụ một inbox table trong database:

~~~java
@Service
public class OrderProjectionService {

    @Transactional // database transaction
    public void apply(OrderApproved event) {

        boolean firstTime =
            processedEventRepository.insertIfAbsent(event.eventId());

        if (!firstTime) {
            return;
        }

        orderRepository.markApproved(event.orderId());
    }
}
~~~

`insertIfAbsent` là thao tác khái niệm; phải có unique constraint và transaction database để tránh race condition. Cả dấu đã xử lý và thay đổi business state phải commit cùng nhau.

Nếu Kafka transaction rollback sau khi DB đã commit, listener có thể được gọi lại. Inbox sẽ ngăn lặp DB update. Tuy nhiên, nếu output Kafka chưa được commit trong lần đầu mà lần replay lại **không gửi output** chỉ vì inbox báo “đã xử lý”, ứng dụng có thể làm mất một output cần thiết. Trường hợp đó cần outbox hoặc logic tái tạo output nhất quán từ state đã commit.

**Idempotency cho DB không tự chứng minh tính atomic giữa DB và Kafka output.** Cần chọn mô hình đảm bảo toàn bộ invariant nghiệp vụ.

## 16. Async task và context transaction

Transaction của container gắn với vòng đời xử lý trên listener/consumer thread. Nếu listener submit công việc chạy ở thread khác rồi trả về trước khi công việc hoàn tất, Kafka producer gửi trong task đó có thể không tham gia transaction đã mở.

Ví dụ không an toàn:

~~~java
@KafkaListener(
    topics = "orders.approved",
    containerFactory = "orderTransactionalListenerFactory")
public void onOrder(OrderApproved event) {

    CompletableFuture.runAsync(() -> {
        kafkaTemplate.send(
            "shipments.requested",
            event.orderId(),
            toShipment(event)
        );
    });

    // Listener kết thúc trước khi async task hoàn tất.
}
~~~

Container có thể commit transaction trước khi task thật sự chạy. Nếu task lỗi, exception cũng không tự động quay về consumer thread để rollback input offset.

Nếu cần xử lý bất đồng bộ, phải thiết kế rõ cách chờ kết quả, propagation của transaction context và xử lý lỗi. Với tác vụ dài hoặc cần tách khỏi poll loop, ưu tiên workflow bền vững thay vì cố giữ Kafka transaction mở vô hạn.

Không tự gọi `KafkaTemplate.executeInTransaction` lồng trong container transaction mà không hiểu nó có thể tạo transaction độc lập với transaction container.

## 17. Concurrency và transaction scope

Một `ConcurrentMessageListenerContainer` với `concurrency = 3` tạo ba child consumers hoạt động song song, mỗi consumer có consumer thread và transaction lifecycle của mình.

~~~text
Listener container (concurrency=3)
  |
  +-- consumer A -> Kafka tx A
  +-- consumer B -> Kafka tx B
  +-- consumer C -> Kafka tx C
~~~

Điều này không tạo một Kafka transaction toàn cục cho cả consumer group.

- Lỗi ở một consumer không mặc định rollback giao dịch của consumer khác.
- Tăng concurrency làm tăng nhu cầu producer transactional và transaction ID.
- Consumer nhiều hơn partition hữu ích không tăng throughput tương ứng.
- Cần cân nhắc output key để giữ ordering theo aggregate.
- Kafka transaction không cung cấp một total order trên mọi partition.

Producer factory và transaction manager phải đủ tài nguyên cho số transaction đồng thời. Quan sát cả CPU, memory, Kafka producer cache và tình trạng broker coordinator khi scale.

## 18. Các failure window quan trọng

| Sự cố | Output Kafka | Input offset | Kết quả cần xử lý |
|---|---|---|---|
| Exception trước khi gửi output | Không có | Không commit trong transaction lỗi | Retry/recovery |
| Exception sau khi gửi, trước commit | Transaction abort | Không commit | Downstream `read_committed` không thấy output abort |
| Process crash giữa transaction | Có thể bị broker abort khi timeout/fencing | Chưa commit trong tx | Input có thể giao lại |
| Kafka commit đã hoàn tất nhưng app mất kết nối | Phụ thuộc kết quả broker | Phụ thuộc kết quả transaction | Không kết luận từ local exception |
| DB đã commit nhưng Kafka commit lỗi | DB vẫn có side effect | Kafka tx chưa commit | Cần idempotency/outbox |
| DLT publisher thất bại | DLT chưa lưu chắc chắn | Không được coi recovery xong | Retry recovery, cảnh báo |
| Consumer downstream `read_uncommitted` | Có thể thấy output abort | Không liên quan offset input | Vi phạm kỳ vọng isolation |
| Hai pod trùng transactional ID | Producer có thể bị fenced | Transaction thất bại | Sửa prefix/rollout |

Với lỗi producer fencing, đừng âm thầm retry send trên cùng producer như một lỗi mạng thoáng qua; cần kiểm tra transaction state và quyền sở hữu transactional ID.

## 19. Vận hành trên Kubernetes và Kafka cluster

Khi deploy nhiều replica:

1. Cấp transaction ID prefix duy nhất cho từng instance hoạt động đồng thời.
2. Kiểm tra rolling deployment để không có overlap cùng transactional ID.
3. Provision topic/ACL và bảo đảm broker transaction coordinator hoạt động.
4. Kiểm tra consumer group, partition count và concurrency phù hợp.
5. Căn chỉnh graceful shutdown với timeout listener và transaction.
6. Kiểm tra consumer downstream dùng `read_committed` khi cần.
7. Theo dõi producer fencing, transaction timeout, retry và DLT.
8. Nếu dùng một broker trong môi trường local/test, cấu hình transaction state log replication/min ISR phù hợp; production phải dùng mức replication đảm bảo durability.

Tín hiệu SIGTERM không bảo đảm transaction luôn commit. Nếu process bị kill, broker có thể abort transaction còn mở và input có thể được giao lại. Listener phải tiếp tục chịu được replay.

## 20. Observability cho transactional listener

| Metric/tín hiệu | Vì sao cần |
|---|---|
| Kafka transaction commit/abort/error | Đánh giá ổn định giao dịch |
| Transaction duration | Phát hiện transaction giữ mở quá lâu |
| `ProducerFencedException` | Phát hiện trùng ID hoặc producer không hợp lệ |
| Broker transaction coordinator errors | Sự cố hạ tầng transaction |
| Consumer lag và rebalance | Theo dõi tiến độ input |
| Kafka output publishing failures | Transactional output có thất bại không |
| After-rollback retry count | Lỗi listener đang lặp |
| DLT recovery count/failures | Record không thể xử lý |
| Consumer `read_committed` lag | Quan sát ảnh hưởng LSO |
| Duplicate event IDs trong inbox | Theo dõi replay và idempotency |

Log nên chứa topic, partition, offset, consumer group, event ID và exception class; tránh log secret hoặc payload nhạy cảm. Đừng dùng event ID làm metric label vì cardinality rất lớn.

Cảnh báo khi transaction fail tăng sau deploy, fencing xuất hiện ở nhiều pod, transaction duration vượt ngân sách hoặc lag tăng trong lúc listener liên tục rollback.

## 21. Runbook khi transactional listener bất thường

**Trường hợp output bị trùng:** kiểm tra downstream isolation `read_committed`, xác nhận KafkaTemplate tham gia cùng producer factory transactional, và kiểm tra upstream có publish duplicate business event hay không. Nếu duplicate nằm trong database hoặc HTTP side effect, phải sửa idempotency của hệ thống ngoài Kafka.

**Trường hợp producer bị fenced:** kiểm tra transaction ID prefix của tất cả pod, rollout overlap, producer cache và broker coordinator. Không coi fencing là record lỗi thông thường rồi commit offset.

**Trường hợp timeout tăng:** đo thời gian listener, database/HTTP latency, transaction timeout và `max.poll.interval.ms`. Dùng dependency timeout và giảm thời gian xử lý trong transaction thay vì nâng timeout vô hạn.

**Trường hợp record retry mãi:** kiểm tra exception do listener ném, after-rollback processor, backoff và phân loại retryable/non-retryable. Xác nhận recovery/DLT publish thành công khi hết retry budget.

**Trường hợp listener trả về bình thường nhưng không có kết quả:** tìm code bắt exception rồi không ném lại, async task không được chờ hoặc KafkaTemplate không tham gia transaction hiện hành.

## 22. Các tình huống kiểm chứng hành vi

Một môi trường test có Kafka broker hỗ trợ transactions nên quan sát ba đường xử lý.

**Thành công:** publish một input event, listener gửi output, Kafka transaction commit, downstream `read_committed` thấy output và offset input tiến phù hợp.

**Rollback có chủ đích:** sau khi gửi output trong listener, ném exception. Downstream `read_committed` không được thấy output abort; input được retry/recover theo cấu hình.

**Crash/failover:** dừng process trước commit, khởi động instance thay thế và xác nhận Kafka output/offset có kết cục nhất quán. Nếu có database side effect, xác nhận inbox/idempotency không lặp cập nhật.

Những tình huống này giúp phân biệt transaction thực sự hoạt động với việc producer chỉ có thuộc tính `transaction-id-prefix` trong cấu hình nhưng listener container chưa dùng transaction manager.

## 23. Chọn mô hình theo yêu cầu consistency

| Nhu cầu | Hướng thiết kế |
|---|---|
| Đọc Kafka và ghi Kafka, muốn output + input offset cùng commit | Container-initiated Kafka transaction |
| Đọc Kafka và chỉ cập nhật database | DB transaction + inbox/idempotency |
| Cập nhật database rồi phát Kafka event tin cậy | Transactional outbox |
| Nhiều API bên ngoài cần phối hợp | Workflow/saga với state và idempotency |
| Retry ngắn trong transactional listener | After-rollback processor và backoff |
| Payload không thể xử lý | Recovery/DLT theo chính sách |
| Retry trì hoãn lâu qua nhiều topic | Kiến trúc retry riêng; kiểm tra hạn chế kết hợp container transactions |
| Consumer không được nhìn record abort | `isolation.level=read_committed` |

**Listener container transaction giúp Spring Kafka gộp output records và tiến độ offset đầu vào trong một Kafka transaction.** Để tận dụng đúng, hãy bảo đảm container dùng KafkaTransactionManager và transactional producer factory phù hợp, đặt transaction ID prefix duy nhất theo instance, để container quản lý commit/rollback, và dùng `read_committed` ở các consumer cần isolation. Với side effect ngoài Kafka, vẫn cần thiết kế idempotency, inbox, outbox hoặc workflow bởi Kafka transaction không thể rollback database và các hệ thống bên ngoài.
