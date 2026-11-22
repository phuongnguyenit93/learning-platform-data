# Đồng bộ Kafka transaction với DB transaction

Trong ứng dụng Spring Kafka, một luồng nghiệp vụ thường phải **ghi database và phát Kafka event** sau khi xử lý một message. Ví dụ, consumer nhận lệnh tạo đơn hàng, cập nhật bảng orders trong PostgreSQL rồi phát OrderAccepted lên Kafka để các service khác tiếp tục xử lý. Hai thao tác này thuộc **hai hệ thống có transaction manager riêng**: database commit một transaction SQL, còn Kafka commit một Kafka transaction.

Spring hỗ trợ **transaction synchronization** để phối hợp thứ tự bắt đầu, kết thúc và commit của các transaction. Tuy nhiên, đồng bộ thứ tự commit **không phải** một distributed transaction nguyên tử giữa database và Kafka. Nếu một bên đã commit còn bên kia lỗi, dữ liệu vẫn có thể lệch nhau. Đây là vấn đề cốt lõi cần hiểu khi thiết kế Kafka và database reliability.

Bài học giải thích cách Spring Kafka phối hợp KafkaTransactionManager với transaction manager của database, thứ tự commit thường gặp, cửa sổ lỗi, idempotency, transactional outbox và cách kiểm thử các tình huống thất bại trong production.

## 1. Bài toán dual write

Xét một service nhận event từ topic orders.requested rồi thực hiện hai hành động:

1. Ghi order vào database.
2. Gửi event OrderCreated sang topic orders.created.

~~~text
orders.requested
       |
       v
Spring Kafka listener
       |
       +----> PostgreSQL: INSERT orders
       |
       +----> Kafka: publish orders.created
~~~

Nếu cả hai bước thành công, dữ liệu nhất quán. Nhưng nếu crash, timeout hoặc commit failure xuất hiện giữa hai thao tác:

| Trạng thái DB | Trạng thái Kafka event | Hệ quả |
|---|---|---|
| Chưa commit | Chưa commit | Có thể retry từ đầu |
| Đã commit | Đã commit | Trạng thái mong muốn |
| Đã commit | Chưa commit | DB đã thay đổi nhưng downstream chưa nhận event |
| Chưa commit | Đã commit | Downstream thấy event trong khi DB chưa có dữ liệu |

Hai hàng cuối là **dual-write inconsistency**. Bật transaction riêng cho mỗi hệ thống chưa giải quyết được, vì hai commit có thể thành công hoặc thất bại độc lập.

Điều cần phân biệt ngay từ đầu:

- **Local DB transaction** bảo đảm tính nguyên tử của những thao tác tham gia cùng transaction database.
- **Kafka transaction** bảo đảm các Kafka output records và, khi cấu hình consumer-initiated transaction, consumed offsets có thể commit hoặc abort cùng nhau trong Kafka.
- **Spring transaction synchronization** điều phối các callback/transaction boundaries nhưng không biến hai transaction managers thành một atomic two-phase commit.
- **Transactional outbox** dùng một DB transaction để ghi trạng thái nghiệp vụ cùng bản ghi event cần phát, rồi publish Kafka ở bước khác để tránh khoảng mất event sau DB commit.

## 2. Những transaction manager trong Spring

Một ứng dụng Spring Boot dùng JPA và Kafka thường có:

| Thành phần | Trách nhiệm | Tài nguyên điều khiển |
|---|---|---|
| **JpaTransactionManager** | Begin/commit/rollback DB transaction cho JPA | JDBC connection và JPA EntityManager |
| **DataSourceTransactionManager** | Begin/commit/rollback DB transaction cho JDBC | JDBC connection |
| **KafkaTransactionManager** | Begin/commit/abort Kafka transaction | Transactional KafkaProducer |
| **KafkaMessageListenerContainer** | Poll, gọi listener, điều phối offset và xử lý lỗi | KafkaConsumer và container lifecycle |
| **KafkaTemplate** | Publish Kafka records, tham gia transaction phù hợp | KafkaProducer |

Một ứng dụng thông thường chọn **một database transaction manager phù hợp với persistence stack**, không phải đồng thời dùng JpaTransactionManager và DataSourceTransactionManager trên cùng thao tác rồi giả định chúng tự hợp nhất.

Annotation **@Transactional** chọn transaction manager theo cấu hình Spring, bean name/qualifier và transaction context. Khi có nhiều manager, nên chỉ rõ:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void updateDatabase(...) {
    // Chạy trong DB transaction.
}

@Transactional(transactionManager = "kafkaTransactionManager")
public void publishEvents(...) {
    // Chạy trong Kafka transaction nếu producer factory transactional.
}
~~~

Đây là ví dụ chỉ về cách chọn manager; các bean tên dbTransactionManager và kafkaTransactionManager phải được khai báo hoặc xác nhận thực sự tồn tại. **@Transactional** không tự mở một distributed transaction bao phủ mọi tài nguyên được gọi trong method.

## 3. Kafka transaction bảo đảm điều gì?

Kafka transaction hữu ích khi cần gửi nhiều output records nguyên tử hoặc khi triển khai **Kafka consume → process → produce** với source offsets được đưa vào cùng transaction.

~~~text
Kafka transaction T1:
    produce orders.created
    produce orders.audit
    send consumed offset nếu là consume-process-produce
    COMMIT

Kết quả Kafka:
    outputs và offsets cùng committed
~~~

Nếu T1 abort, các Kafka records của transaction bị abort sẽ không được consumer **read_committed** trả về. Khi consumed offsets thuộc transaction, offset commit đó cũng không được ghi nhận.

Kafka transaction **không kiểm soát transaction của PostgreSQL**. Producer không thể tự hủy UPDATE DB đã commit chỉ vì Kafka commit thất bại. Tương tự, database không thể xóa Kafka record đã commit chỉ bằng một SQL rollback.

Vì vậy, câu nói "Kafka và DB cùng được đánh dấu transactional" không đủ để kết luận hệ thống có exactly-once end-to-end.

## 4. Hai cách bắt đầu transaction thường gặp

Có hai ngữ cảnh cần phân biệt:

### Producer-initiated: service method bắt đầu bằng DB transaction

Service thực hiện nghiệp vụ trong một method @Transactional dùng DB manager, rồi gọi KafkaTemplate. Nếu producer factory được cấu hình transactional và KafkaTemplate tham gia Spring transaction synchronization, Kafka transaction được phối hợp với DB transaction.

~~~text
@Transactional DB service
       |
       +-- DB write
       +-- KafkaTemplate.send(...)
       |
       v
DB commit
       |
       v
Kafka transaction commit (synchronized)
~~~

Trong luồng này, **DB commit trước, Kafka commit sau** theo thứ tự đồng bộ phổ biến. Đây vẫn là hai commit riêng biệt và có cửa sổ lỗi giữa chúng.

### Consumer-initiated: Kafka listener container bắt đầu Kafka transaction

Container có Kafka transaction manager, bắt đầu Kafka transaction trước khi gọi listener. Bên trong listener, một service method dùng @Transactional với DB manager mở DB transaction.

~~~text
Kafka listener container: BEGIN Kafka transaction
       |
       v
@KafkaListener gọi DB service
       |
       v
@Transactional DB service: BEGIN DB transaction
       |
       +-- DB write
       +-- KafkaTemplate.send(...) cùng Kafka transaction
       |
       v
DB transaction COMMIT
       |
       v
Listener hoàn tất
       |
       v
Container sendOffsetsToTransaction + COMMIT Kafka transaction
~~~

Trong luồng này, vì DB transaction nằm **bên trong** transaction container, DB thường commit trước Kafka. Kafka commit có thể bao gồm cả output và source consumed offsets.

Hai mô hình có ranh giới khác nhau nhưng đều cần xử lý trường hợp DB đã commit rồi Kafka commit thất bại.

## 5. Cấu hình transactional Kafka producer bằng Spring Boot

Để KafkaTemplate có thể tham gia Kafka transaction, producer factory phải được cấu hình transactional. Một cách phổ biến trong Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-instance-a-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[acks]": all
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      isolation-level: read_committed
    listener:
      ack-mode: record
~~~

Những điểm quan trọng:

- **transaction-id-prefix** là cấu hình để Spring Kafka tạo transactional producers với transactional.id.
- Prefix phải được quản lý để **không trùng giữa các application instances đang hoạt động đồng thời**.
- **enable-auto-commit: false** tránh consumer tự commit offset ngoài container-managed transaction.
- **isolation-level: read_committed** giúp consumer không đọc những transactional records đã abort khi topic có transactional producers.
- **acks=all** hỗ trợ durability của producer, nhưng không thay thế Kafka transaction hoặc cấu hình replication thích hợp của broker.

Khi cấu hình phù hợp, Spring Boot có thể tự tạo KafkaTransactionManager. Nếu tự khai báo nhiều ProducerFactory hoặc transaction manager, cần wiring rõ bean nào được KafkaTemplate và listener container sử dụng.

Ví dụ transaction-id-prefix trong YAML chỉ là minh họa cho một instance. Với Kubernetes, cần bảo đảm instance identity ổn định trong thời gian một pod đang chạy và không xảy ra xung đột transactional.id khi scale.

## 6. Ví dụ listener Kafka và DB transaction

Giả sử có model OrderRequested, entity Order và output OrderAccepted. Một Kafka listener đọc input rồi gọi service:

~~~java
@Component
public class OrderRequestListener {

    private final OrderApplicationService service;

    public OrderRequestListener(OrderApplicationService service) {
        this.service = service;
    }

    @KafkaListener(
            topics = "orders.requested",
            groupId = "orders-service",
            containerFactory = "transactionalListenerFactory")
    public void onOrder(OrderRequested event) {
        service.saveAndPublish(event);
    }
}
~~~

Service sử dụng **database transaction manager**:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderAccepted> kafkaTemplate;

    public OrderApplicationService(
            OrderRepository orderRepository,
            KafkaTemplate<String, OrderAccepted> kafkaTemplate) {
        this.orderRepository = orderRepository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void saveAndPublish(OrderRequested event) {
        Order order = Order.from(event);
        orderRepository.save(order);

        OrderAccepted accepted =
                new OrderAccepted(order.getId(), event.eventId());

        kafkaTemplate.send(
                "orders.accepted",
                order.getId(),
                accepted
        ).join();
    }
}
~~~

Đoạn mã trên minh họa transaction boundaries; các class và bean trong ứng dụng thực tế cần được khai báo tương ứng. **KafkaTemplate phải dùng ProducerFactory tham gia cùng Kafka transaction với container.** Nếu không, thao tác Kafka có thể commit ngoài transaction mong muốn.

Vì listener gọi service qua một Spring bean khác, proxy của **@Transactional** được áp dụng. Nếu method được gọi bằng **this.saveAndPublish(...)** trong cùng bean qua self-invocation, Spring proxy-based transaction interception có thể không chạy; đó là một lỗi thường gặp.

### Ý nghĩa của join()

KafkaTemplate.send(...) thường là bất đồng bộ. join() trong ví dụ giúp phát hiện lỗi produce sớm trước khi method trả về. Nhưng **send thành công không đồng nghĩa Kafka transaction đã commit**. Trong mô hình container-managed transaction, Kafka commit diễn ra khi transaction boundary phía ngoài hoàn tất.

Do đó, có thể xảy ra:

~~~text
DB service:
    UPDATE DB
    Kafka send acknowledged
    DB COMMIT thành công

Kafka listener container:
    Kafka COMMIT thất bại
~~~

Trong tình huống này, DB đã thay đổi nhưng output Kafka hoặc consumed offset có thể chưa commit theo kết quả transaction cuối cùng. join() không loại bỏ cửa sổ lỗi đó.

## 7. Gắn Kafka transaction manager vào listener container

Với consumer-initiated transaction, listener container cần được cấu hình transaction manager dùng đúng transactional producer factory.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderRequested>
        transactionalListenerFactory(
                ConsumerFactory<String, OrderRequested> consumerFactory,
                KafkaTransactionManager<String, OrderAccepted> kafkaTxManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderRequested>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTxManager);
    return factory;
}
~~~

Ví dụ sử dụng API có **setKafkaAwareTransactionManager** của các phiên bản Spring Kafka hỗ trợ; tên setter hoặc cách wiring có thể khác ở phiên bản cũ. Trong dự án dùng Spring Boot auto-configuration, có thể không cần bean này nếu container factory đã nhận manager chính xác.

KafkaTransactionManager dùng ProducerFactory transactional:

~~~java
@Bean
KafkaTransactionManager<String, OrderAccepted> kafkaTransactionManager(
        ProducerFactory<String, OrderAccepted> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Tránh tạo hai KafkaTransactionManager khác nhau chỉ vì một bean được Spring Boot auto-configure và một bean do ứng dụng tạo, nếu chúng làm template/container không dùng cùng transaction infrastructure.

## 8. DB-first commit: thứ tự mặc định và lợi ích

Trong nhiều ứng dụng dùng @Transactional DB bên trong listener Kafka transactional, thứ tự thường là:

~~~text
T0  Consumer poll input
T1  Kafka container begin transaction K1
T2  DB service begin transaction D1
T3  UPDATE / INSERT trong D1
T4  KafkaTemplate gửi output trong K1
T5  DB service return -> COMMIT D1
T6  Listener return
T7  Container send source offset vào K1
T8  Container COMMIT K1
~~~

Ưu điểm của thứ tự **DB-first, Kafka-second**:

- Nếu DB transaction lỗi và exception được truyền ra, Kafka transaction có thể abort trước khi output được công nhận.
- Tránh phát Kafka event đã committed trong trường hợp DB write thất bại trước commit.
- Dễ hiểu khi DB là source of truth của trạng thái nghiệp vụ.

Nhược điểm quan trọng: **nếu D1 commit thành công nhưng K1 commit thất bại, DB không thể tự rollback**. Cần một cơ chế phục hồi để cuối cùng Kafka nhận được event tương ứng mà không làm lại side effect nghiệp vụ sai cách.

Nếu một Kafka transaction commit trả về lỗi do network hoặc coordinator, trạng thái commit cuối cùng đôi khi cần được điều tra thay vì mặc định transaction chắc chắn abort. Không nên tự động bù trừ DB mà chưa đánh giá kết quả thực tế.

## 9. Cửa sổ lỗi sau DB commit

Đây là failure window có ảnh hưởng lớn nhất trong mô hình transaction synchronization:

~~~text
DB transaction D1:
   INSERT order O-1001
   COMMIT D1 -> SUCCESS

Kafka transaction K1:
   SEND OrderAccepted(O-1001)
   COMMIT K1 -> FAILURE / UNKNOWN

Ứng dụng:
   nhận exception hoặc restart
~~~

Tại thời điểm đó:

- Database đã có order O-1001.
- Kafka transaction có thể đã abort hoặc có trạng thái cần xác minh.
- Consumer group có thể chưa có consumed offset committed từ K1.
- Input có thể được xử lý lại.

Nếu lần retry chỉ chạy lại INSERT order bằng khóa chính, có thể gặp duplicate key. Nếu code thấy order đã tồn tại và lập tức return, **Kafka event bị thiếu có thể không bao giờ được tạo**.

Ví dụ lỗi logic:

~~~java
@Transactional("dbTransactionManager")
public void handle(OrderRequested event) {
    if (orderRepository.existsById(event.orderId())) {
        return;  // Nguy hiểm: có thể bỏ qua event chưa được publish!
    }

    orderRepository.save(Order.from(event));
    kafkaTemplate.send("orders.accepted", ...).join();
}
~~~

Code trên có vẻ idempotent đối với DB nhưng **không bảo đảm output Kafka**. Nếu DB commit thành công rồi Kafka commit lỗi, lần retry sẽ thấy order tồn tại và không gửi lại event.

Đây là lý do cần phân biệt **idempotency của thao tác DB** với **reliability của việc phát event**. Transactional outbox hoặc một durable state machine theo dõi event chưa phát là giải pháp phù hợp hơn khi không được mất event.

## 10. Ngoại lệ Kafka commit sau DB commit

Khi DB transaction đã commit, nếu Kafka transaction commit sau đó thất bại, ứng dụng cần biết lỗi để xử lý bù trừ hoặc reconciliation.

Hành vi exception propagation trong Spring Kafka đã thay đổi qua các nhánh phiên bản: ở các bản vá hiện đại, lỗi của secondary Kafka commit trong transaction synchronization thường được **ném lên caller**, thay vì chỉ ghi log như một số bản cũ. Hãy kiểm tra hành vi của đúng Spring Kafka version đang chạy.

Quan trọng là phân biệt:

- **Exception từ KafkaTemplate.send()** trước DB commit: có thể khiến DB rollback nếu được truyền ra.
- **Exception từ DB commit**: DB có thể rollback hoặc trạng thái cần xác minh tùy lỗi.
- **Exception từ Kafka commit sau DB commit**: DB đã commit; không thể đơn giản gọi rollback DB transaction đó nữa.
- **Timeout trong lúc chờ kết quả commit**: cần điều tra xem broker đã commit hay chưa; không được giả định luôn thất bại.

Nếu phải khôi phục bằng nghiệp vụ bù trừ, thao tác bù trừ cũng có thể thất bại và cần idempotency. Với pipeline quan trọng, nên thiết kế ngay một **durable recovery record** thay vì phụ thuộc vào việc process còn sống để bắt exception và gửi lại Kafka.

## 11. Kafka-first: có đảo thứ tự commit được không?

Spring cho phép cấu hình các method @Transactional lồng nhau để Kafka transaction commit trước DB transaction trong một số producer-initiated workflow.

Ví dụ thiết kế với hai Spring beans và hai managers:

~~~java
@Service
public class DbWorkflowService {

    private final OrderRepository orderRepository;
    private final KafkaPublishingService publisher;

    @Transactional("dbTransactionManager")
    public void saveThenPublish(OrderRequested event) {
        orderRepository.save(Order.from(event));
        publisher.publishInKafkaTransaction(event);
    }
}

@Service
public class KafkaPublishingService {

    private final KafkaTemplate<String, OrderAccepted> kafkaTemplate;

    @Transactional("kafkaTransactionManager")
    public void publishInKafkaTransaction(OrderRequested event) {
        kafkaTemplate.send(
                "orders.accepted",
                event.orderId(),
                new OrderAccepted(event.orderId(), event.eventId())
        ).join();
    }
}
~~~

Đây là **cấu trúc khái niệm**: code minh họa hai service khác nhau để Spring proxies áp dụng hai transaction managers. Constructors, repositories, bean names, propagation và producer factory phải được cấu hình trong ứng dụng cụ thể. Không sao chép mẫu này vào transactional Kafka listener đang có transaction bên ngoài mà chưa phân tích rõ transaction nesting.

Với DB transaction ở method ngoài và Kafka transaction ở method bên trong, Kafka có thể commit khi method bên trong hoàn tất, trước khi DB outer transaction commit. Nhưng đây **vẫn không phải atomic commit**:

~~~text
BEGIN DB transaction
    INSERT order
    BEGIN Kafka transaction
        SEND OrderAccepted
    COMMIT Kafka transaction  -> thành công
COMMIT DB transaction         -> thất bại
~~~

Kết quả: downstream có thể đã đọc OrderAccepted dù database chưa có order. Kafka-first chỉ **di chuyển cửa sổ lỗi** sang hướng ngược lại; nó không xóa dual-write problem.

Với DB là source of truth, đảo thứ tự commit thường không giải quyết nhu cầu bảo đảm event phản ánh trạng thái DB đã committed.

## 12. Chained transaction managers có phải 2PC?

Một số dự án cũ sử dụng mô hình **chained transaction manager** để phối hợp hai transaction managers trong một thứ tự commit. Spring Kafka từng có **ChainedKafkaTransactionManager** (đã bị deprecate trong các phiên bản cũ), hoặc dự án có thể dựa vào những cơ chế chain tương đương.

Điều cần nhớ: chain **không biến Kafka và database thành một XA two-phase commit**. Chain chỉ bắt đầu/commit/rollback các local transactions theo thứ tự. Nếu manager thứ nhất đã commit và manager thứ hai lỗi, manager thứ nhất không thể tự quay ngược.

~~~text
DB local transaction ----- COMMIT -> đã xong
Kafka local transaction -- COMMIT -> lỗi

Không có global prepare+commit nguyên tử
cho cả hai tài nguyên.
~~~

Vì vậy, không nên chọn chained manager chỉ vì tên nghe giống một distributed transaction. Khi nâng cấp Spring Kafka, hãy ưu tiên transaction synchronization được hỗ trợ, hiểu rõ commit order và có phương án xử lý partial commit.

## 13. Transaction synchronization của Spring hoạt động ra sao?

Spring quản lý transaction resources và synchronization callbacks trong ngữ cảnh thread. Khi DB transaction đang hoạt động, một KafkaTemplate được cấu hình transactional có thể đồng bộ Kafka transaction theo vòng đời transaction ngoài, thay vì commit ngay ở từng send.

~~~text
Spring DB @Transactional boundary
    |
    +-- TransactionSynchronizationManager
    |
    +-- DB connection / EntityManager
    |
    +-- KafkaTemplate tham gia transaction synchronization
    |
    v
DB commit
    |
    v
Kafka transaction completion theo synchronization
~~~

Tính năng này giúp giảm code điều phối commit thủ công. Tuy nhiên:

- Transaction context thường gắn với thread.
- Một @Async method chạy trên thread khác không tự có transaction context của caller.
- KafkaTemplate dùng ProducerFactory không transactional có thể produce bên ngoài transaction.
- Một transaction manager khác được chọn bởi @Transactional sẽ thay đổi boundary thực tế.
- External API không tham gia transaction synchronization chỉ vì được gọi trong method transactional.

Không nên dùng ThreadLocal transaction context như một bảo đảm end-to-end khi listener chuyển công việc sang executor hoặc CompletableFuture rồi trả về trước khi công việc hoàn tất.

## 14. Consumer-initiated Kafka transaction và DB side effect

Với transactional Kafka listener container, một phương án hay gặp:

~~~text
Kafka BEGIN K1
    |
    +-- DB BEGIN D1
    |     |
    |     +-- update order
    |     +-- insert audit row
    |     |
    |     v
    |   DB COMMIT D1
    |
    +-- Kafka outputs và source offset
    |
Kafka COMMIT K1
~~~

Nếu D1 thất bại trước commit và exception truyền ra ngoài, container rollback K1. Nhưng nếu D1 commit thành công rồi K1 abort, DB state không rollback.

Một điểm khác là **consumed offset** cũng nằm trong Kafka transaction. Nếu K1 abort, consumer group có thể xử lý lại cùng input ngay cả khi DB write đã commit. Điều này làm idempotency cho DB càng quan trọng.

Không được đặt consumer.commitSync() trong listener transactional để cố tiến offset sau khi DB write, vì như vậy offset có thể commit ngoài Kafka transaction và phá vỡ Kafka consume-process-produce semantics.

## 15. Idempotency trong DB: cần nhưng chưa đủ

Trong hệ thống at-least-once hoặc có retry, một Kafka event có thể được xử lý nhiều lần. Một phương án phổ biến là bảng processed_events với event ID duy nhất:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trong cùng DB transaction, service cố ghi event ID và chỉ thực hiện DB side effect nếu event chưa được xử lý.

Với PostgreSQL có thể dùng:

~~~sql
INSERT INTO processed_events(event_id)
VALUES (:event_id)
ON CONFLICT (event_id) DO NOTHING;
~~~

Ứng dụng kiểm tra số row insert thành công để xác định event mới hay trùng. Unique constraint trong database mới là cơ chế chặn race condition chính; chỉ gọi existsById() trước khi insert **không đủ an toàn khi nhiều consumer xử lý cạnh tranh**.

Tuy nhiên, chỉ dùng processed_events mà không có cách lưu trạng thái publish Kafka có thể gây **missing output**:

~~~text
Attempt 1:
  INSERT processed_events(E123) -> DB COMMIT
  Kafka COMMIT -> FAILED

Attempt 2:
  processed_events(E123) đã tồn tại
  skip toàn bộ logic

orders.accepted không có event E123
~~~

Muốn không mất event, cần đảm bảo sau khi DB state được ghi, hệ thống vẫn có một cách **bền vững** để phát Kafka output nếu lần đầu commit thất bại. Transactional outbox chính là một cách giải quyết điều này.

## 16. Transactional outbox: giải pháp cho DB-first reliability

**Transactional outbox** không cố commit DB và Kafka cùng lúc. Thay vào đó, nó ghi hai thứ **trong cùng một DB transaction**:

1. Business state, ví dụ bản ghi orders.
2. Một outbox event mô tả Kafka message cần phát.

~~~text
Kafka input
    |
    v
Spring service
    |
    v
BEGIN DB TRANSACTION
    |
    +-- UPDATE/INSERT orders
    +-- INSERT outbox_events
    +-- INSERT processed_events (nếu cần)
    |
COMMIT DB TRANSACTION
    |
    v
Outbox relay / CDC
    |
    v
Kafka orders.accepted
~~~

Nếu DB transaction rollback, cả state và outbox event đều không tồn tại. Nếu DB commit, event cần phát được lưu bền vững ngay cả khi Kafka broker hoặc application process tạm unavailable.

Điều đó xóa cửa sổ **DB committed nhưng không có dấu vết event phải publish**, vốn tồn tại khi chỉ gửi Kafka trực tiếp trong cùng service rồi đồng bộ commit.

Outbox không tự bảo đảm event Kafka chỉ được publish đúng một lần. Relay có thể publish rồi crash trước khi đánh dấu outbox đã gửi. Vì thế outbox thường cho **at-least-once publish** và consumer downstream cần idempotency.

## 17. Thiết kế bảng outbox

Một schema minh họa cho PostgreSQL:

~~~sql
CREATE TABLE orders (
    id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL
);

CREATE INDEX idx_outbox_unpublished
ON outbox_events (created_at)
WHERE published_at IS NULL;
~~~

Các field có mục đích khác nhau:

| Field | Mục đích |
|---|---|
| id | Event ID bất biến để deduplicate và trace |
| aggregate_id | Key Kafka giúp giữ thứ tự theo một aggregate khi phù hợp |
| event_type | Loại event, phục vụ routing/schema |
| payload_json | Nội dung event đã chuẩn bị để phát |
| created_at | Thời điểm tạo event trong DB |
| published_at | Dấu hiệu relay đã ghi nhận Kafka publish thành công |

Trong hệ thống có nhiều tenants, schema version, correlation ID hoặc compliance, có thể bổ sung metadata tương ứng. Không đưa thông tin nhạy cảm vào payload outbox nếu không có quy định mã hóa/retention phù hợp.

Một outbox event nên có **ID không đổi** qua mọi lần publish lại. Nếu relay tạo event ID mới ở mỗi retry, downstream sẽ khó deduplicate.

## 18. Ghi business state và outbox trong một DB transaction

Service sau minh họa một DB-only transaction:

~~~java
@Service
public class OrderCommandService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;

    @Transactional("dbTransactionManager")
    public void accept(OrderRequested event) {
        Order order = Order.from(event);
        orderRepository.save(order);

        OutboxEvent outboxEvent = OutboxEvent.orderAccepted(
                event.eventId(),
                order.getId(),
                order.getStatus());

        outboxRepository.save(outboxEvent);
    }
}
~~~

Ở đây KafkaTemplate **không cần được gọi bên trong DB transaction**. Cả Order và OutboxEvent cùng commit hoặc rollback bằng database transaction manager.

Đây là code minh họa; production cần kết hợp unique constraints/processed event ID, xác định event ID ổn định và chính sách khi duplicate input. Nếu một record Kafka nguồn được replay, service cần tránh insert trùng outbox event với ID khác và tránh side effect nghiệp vụ lặp.

Nếu event đầu vào có eventId duy nhất, có thể dùng nó làm phần khóa idempotency và bảo đảm việc lưu trạng thái với outbox cùng transaction.

## 19. Outbox relay: polling và CDC

Có hai nhóm triển khai phổ biến.

### Polling relay

Một background worker đọc các outbox rows chưa publish:

~~~text
SELECT outbox chưa publish
       |
       v
KafkaTemplate.send(...)
       |
       +-- thất bại --> giữ row để retry
       |
       v
Kafka broker acknowledge
       |
       v
UPDATE outbox.published_at
~~~

Trong PostgreSQL, khi nhiều relay workers cùng chạy có thể dùng **FOR UPDATE SKIP LOCKED** hoặc một cơ chế claim/lease phù hợp để giảm tranh chấp. Tuy nhiên, không nên giữ DB transaction/row lock mở quá lâu trong khi chờ Kafka network send.

Một flow an toàn hơn thường gồm claim có timeout/lease, publish, xác nhận kết quả rồi đánh dấu hoàn thành; nếu worker crash trước mark, row được claim lại sau lease và có thể publish trùng. Do đó downstream phải idempotent.

### Change Data Capture (CDC)

Một connector CDC như Debezium có thể đọc database transaction log và chuyển các thay đổi outbox sang Kafka. Khi đó, service không cần tự polling SQL table để phát event.

~~~text
DB COMMIT orders + outbox
         |
         v
Database transaction log
         |
         v
CDC connector
         |
         v
Kafka orders.accepted
~~~

CDC giúp giảm logic polling trong ứng dụng, nhưng vẫn cần vận hành connector, schema, offsets, error handling và idempotent downstream processing. Không nên giả định CDC biến DB và Kafka thành một global XA transaction.

## 20. Vì sao outbox vẫn có duplicate publish?

Xét polling relay:

~~~text
1. Relay đọc outbox row E123.
2. Relay publish E123 vào Kafka.
3. Broker acknowledge thành công.
4. Relay crash trước khi UPDATE published_at.
5. Relay restart, thấy E123 chưa published.
6. Relay publish E123 lần nữa.
~~~

Kafka có thể chứa hai records cùng event ID E123. Đây là hành vi có thể chấp nhận khi kiến trúc được thiết kế at-least-once với deduplication.

Để kiểm soát:

- Dùng event ID ổn định trong key/header/value.
- Dùng producer idempotence và acknowledgement phù hợp, nhưng đừng nhầm producer idempotence với end-to-end business deduplication.
- Consumer downstream lưu processed event ID trong transaction cùng side effect.
- Không để relay tự ý đổi event ID khi retry.
- Theo dõi outbox backlog, tuổi event lâu nhất và publish failure.

Nếu business yêu cầu không phát ra output trùng ngay cả ở mức Kafka log, cần phân tích transaction boundaries, relay ownership và deduplication cơ sở dữ liệu kỹ hơn. Chỉ có DB outbox row không tự cung cấp exactly-once log append cho Kafka.

## 21. So sánh transaction synchronization và outbox

| Tiêu chí | DB + Kafka synchronization | Transactional outbox |
|---|---|---|
| Kafka được gửi khi nào? | Thường ngay trong service transaction | Sau DB commit qua relay/CDC |
| Atomic DB + Kafka commit? | **Không** | **Không**, nhưng DB state + outbox intent atomic |
| DB commit rồi Kafka commit fail | Có nguy cơ thiếu event, cần recovery | Event intent vẫn ở DB để relay retry |
| Kafka outage | Có thể làm business path thất bại hoặc commit lỗi | DB có thể commit event intent, relay chờ Kafka |
| Latency Kafka output | Có thể thấp khi cả hai hệ thống khỏe | Có thêm relay/CDC delay |
| Hạ tầng vận hành | Transaction managers, Kafka producer, compensation | Outbox table, relay/CDC, monitoring và cleanup |
| Duplicate event | Có thể xuất hiện khi retry/uncertain commit | Có thể xuất hiện khi relay retry |
| Tính bền vững khi process crash | Phải thiết kế xử lý commit gap | Event intent tồn tại trong DB nếu DB đã commit |
| Khi phù hợp | Có thể chấp nhận partial-failure policy và reconciliation | Không được làm mất event sau khi DB state commit |

Nếu DB là source of truth và event Kafka là phần bắt buộc để hệ thống khác cập nhật đúng, outbox thường dễ đạt tính **eventual consistency có thể phục hồi** hơn việc chỉ dựa vào synchronization callbacks.

Nếu workload chỉ là Kafka-to-Kafka và không có DB side effect, Kafka transaction với consumed offsets có thể là lựa chọn tự nhiên, không cần outbox.

## 22. Transaction timeout, DB lock và Kafka poll

Khi DB transaction và Kafka transaction cùng tồn tại, thời gian xử lý có thể bị giới hạn bởi nhiều timeout:

| Thông số | Phạm vi |
|---|---|
| Kafka transaction.timeout.ms | Thời gian tối đa một Kafka transaction được phép mở theo cấu hình producer/broker |
| Consumer max.poll.interval.ms | Khoảng thời gian tối đa giữa các lần poll theo consumer group protocol |
| DB transaction timeout | Thời gian database/Spring cho một transaction thực hiện |
| SQL lock timeout | Thời gian chờ lock của database |
| HTTP client timeout | Thời gian gọi external service |

Một transaction kéo dài do chờ DB lock có thể khiến Kafka transaction timeout. Nếu consumer không poll đủ thường xuyên, group có thể rebalance và partition chuyển owner. Khi commit consumed offset trong Kafka transaction, membership hoặc producer fencing có thể khiến commit thất bại.

Không tăng mọi timeout vô hạn để "tránh lỗi". Cần xác định nút thắt: SQL chậm, lock contention, Kafka coordinator, network, batch lớn hay listener xử lý quá lâu.

Các thực hành nên áp dụng:

- Giữ DB transaction ngắn, tránh gọi external API lâu trong DB transaction.
- Không chờ retry backoff dài khi Kafka transaction còn mở.
- Đo transaction duration, lock wait, Kafka commit latency và consumer poll interval.
- Giới hạn max.poll.records/batch size theo thời gian xử lý thực tế.
- Thử nghiệm graceful shutdown, rebalance và restart khi transaction đang hoạt động.

## 23. Kafka consumer ownership và retry DB write

Khi listener là transactional, exception truyền ra container làm Kafka transaction rollback. Sau đó, Spring Kafka có thể dùng **DefaultAfterRollbackProcessor** để seek/retry record theo BackOff.

~~~text
Consumer A nhận orders.requested/P1@80
       |
       +-- Kafka transaction K1
       +-- DB transaction D1
       |
       +-- DB COMMIT D1 thành công
       |
       +-- Kafka K1 abort/fail
       |
       v
Record P1@80 có thể được xử lý lại
       |
       v
DB cần idempotency và Kafka output cần recovery
~~~

Nếu group rebalance trong khoảng này, một consumer khác có thể nhận lại partition và xử lý cùng event. **Không dùng việc Kafka chỉ có một owner tại một thời điểm ổn định để suy ra DB side effect chắc chắn chỉ thực hiện một lần.**

Với các thao tác không idempotent như cộng tiền, trừ tồn kho hoặc gửi hóa đơn, cần event ID/transaction ID và kiểm tra trạng thái nghiệp vụ trong DB transaction.

Sau nhiều lần retry, record có thể được chuyển DLT. Nhưng **DLT chỉ chứng minh record không được xử lý theo policy**, không đảm bảo database đã rollback hoặc chưa có side effect. DLT handler cần xem DB state trước khi replay.

## 24. DLT và recovery khi DB đã commit

Giả sử:

~~~text
orders.requested/P1@80
   |
   +-- DB COMMIT order O-1001
   |
   +-- Kafka COMMIT lỗi
   |
   v
AfterRollbackProcessor retry nhiều lần
   |
   v
Record được đưa vào DLT
~~~

Tại DLT, business order có thể **đã tồn tại trong database**. Nếu operator nhìn thấy record DLT và thực hiện replay bằng cách INSERT order mới, có nguy cơ duplicate hoặc lỗi unique constraint.

Quy trình recovery cần:

1. Đọc original topic, partition, offset và event ID từ DLT.
2. Kiểm tra DB có trạng thái nghiệp vụ tương ứng không.
3. Kiểm tra Kafka output đã committed hoặc đã được phát bởi lần retry khác chưa.
4. Xác định chỉ thiếu output, chỉ thiếu DB, hay cả hai đã thành công.
5. Chọn hành động bù trừ/replay có idempotency và audit.
6. Không đơn giản retry toàn bộ listener nếu một phần side effect đã committed ngoài Kafka.

Nếu dùng outbox, một event intent bền vững trong DB làm việc xác định output chưa publish dễ hơn: relay có thể tiếp tục cho đến khi publish được hoặc operator xử lý lỗi một cách rõ ràng.

## 25. Observability cho dual-write pipeline

Một hệ thống phối hợp Kafka và DB cần theo dõi **cả hai transaction outcomes** thay vì chỉ log listener success/error.

Các metric nên có:

- Số DB transaction commit/rollback và p95/p99 duration.
- Số Kafka transaction commit/abort và commit errors.
- Consumer lag theo topic/partition.
- Producer send error, request latency và transaction coordinator errors.
- Số lỗi commit Kafka sau khi DB đã commit.
- Số record bị retry sau DB commit.
- Số business event thiếu output được phát hiện qua reconciliation.
- Outbox backlog, event age, relay throughput, publish failures nếu dùng outbox.
- DLT count, replay success/failure và duplicate processing attempts.

Một log có cấu trúc:

~~~text
eventId=E123
orderId=O-1001
inputTopic=orders.requested
inputPartition=1
inputOffset=80
dbOutcome=committed
kafkaOutcome=commit_failed_or_unknown
recoveryState=pending_reconciliation
~~~

Đây là định dạng log ứng dụng minh họa. Không dùng event ID hoặc offset làm metric labels có cardinality cao; đưa chúng vào log/trace để truy vết.

Với một transaction commit timeout, tránh log bừa "Kafka chắc chắn đã abort" khi trạng thái thực tế chưa được xác minh. Cần kiểm tra committed offset, event ID tại output topic hoặc trạng thái relay để quyết định hành động tiếp theo.

## 26. Reconciliation: phát hiện bất nhất đã xảy ra

Không kiến trúc distributed system nào nên chỉ dựa vào happy path. Với DB-first direct produce, một **reconciliation job** có thể đối chiếu trạng thái DB và event/outbox publish state.

Ví dụ:

~~~text
Database:
  order O-1001 status=ACCEPTED

Kafka output:
  chưa tìm thấy OrderAccepted(eventId=E123)

Reconciliation:
  kiểm tra trạng thái publish bền vững
  xác định cần phát lại event
  publish theo idempotency key E123
~~~

Nếu chỉ quét Kafka topic để tìm event, cần lưu ý retention có thể đã xóa record cũ và offset không phải khóa nghiệp vụ. Một bảng outbox hoặc published-event audit store đáng tin cậy giúp reconciliation xác định kết quả rõ hơn.

Reconciliation cũng phải bảo vệ trường hợp **Kafka event đã commit nhưng acknowledgement bị mất**. Publish lại theo event ID ổn định và downstream deduplication thường an toàn hơn việc giả định không có event.

Không nên auto-delete DB rows mỗi khi không thấy output Kafka; đó là thao tác bù trừ nghiệp vụ có thể gây mất dữ liệu và cần đánh giá trạng thái cuối cùng của hệ thống.

## 27. Kiểm thử transaction synchronization

Nên dùng **Kafka broker thật trong test** (ví dụ Testcontainers Kafka hoặc EmbeddedKafka) và database tương ứng với production khi có thể. Không thể chứng minh commit order và failure window chỉ bằng unit test mock KafkaTemplate.

### Test 1: DB và Kafka đều thành công

1. Gửi OrderRequested với event ID E123.
2. Chờ listener thực hiện và hoàn tất các commit.
3. Kiểm tra DB có order.
4. Kiểm tra consumer read_committed nhận OrderAccepted.
5. Kiểm tra consumed offset tiến đúng nếu container transactional.

### Test 2: DB rollback trước Kafka commit

1. Giả lập lỗi SQL hoặc constraint violation.
2. Để exception truyền ra transaction boundary.
3. Kiểm tra DB transaction không commit.
4. Kiểm tra Kafka output thuộc transaction lỗi không visible với read_committed.
5. Kiểm tra record đầu vào được retry/recovery theo cấu hình.

### Test 3: Kafka commit lỗi sau DB commit

1. Thiết lập fault injection ở giai đoạn commit Kafka.
2. Đảm bảo DB commit đã thành công.
3. Xác nhận ứng dụng ghi nhận trạng thái Kafka commit failure/unknown.
4. Kiểm tra lần xử lý lại không tạo DB side effect trùng.
5. Kiểm tra pipeline có cơ chế phục hồi event output còn thiếu.

Đây là failure scenario quan trọng nhất; một test chỉ làm KafkaTemplate.send() throw trước DB commit **không mô phỏng** được commit failure xảy ra sau DB commit.

### Test 4: Crash giữa hai commit

1. Dừng process sau DB commit nhưng trước Kafka commit khi test harness cho phép.
2. Restart ứng dụng với cùng group.
3. Xác nhận DB state vẫn còn.
4. Xác nhận source record có thể được đọc lại.
5. Kiểm tra idempotency và recovery output.

### Test 5: Outbox relay crash

1. DB commit business state và outbox event trong cùng transaction.
2. Relay publish Kafka event.
3. Giả lập crash trước khi đánh dấu published_at.
4. Cho relay xử lý lại.
5. Xác nhận event ID bất biến và downstream không tạo side effect trùng.

### Test 6: Rebalance và transaction timeout

1. Chạy nhiều consumer replicas.
2. Làm listener xử lý lâu hơn hoặc tạo rebalance khi đang xử lý.
3. Quan sát Kafka transaction abort/fencing hoặc commit failure.
4. Kiểm tra DB có chịu được record giao lại.
5. Xác nhận hệ thống không mất event sau recovery.

Không dùng sleep cố định để suy luận transaction hoàn tất; nên chờ kết quả theo điều kiện có timeout và đối chiếu cả DB lẫn Kafka.

## 28. Lỗi thiết kế thường gặp

| Sai lầm | Vì sao nguy hiểm | Thay thế |
|---|---|---|
| Cho rằng @Transactional bao phủ Kafka và DB nguyên tử | Hai managers commit độc lập | Hiểu commit order, dùng outbox khi không được mất event |
| Thấy DB record tồn tại thì bỏ qua Kafka output | DB commit trước Kafka commit có thể để lại event bị thiếu | Lưu outbox event hoặc durable publish state |
| Kafka commit trước DB để "an toàn hơn" | Có thể phát event khi DB rollback | Chọn commit order theo semantics, không xem là 2PC |
| Nuốt exception của listener | Container có thể commit Kafka transaction dù business thất bại | Rethrow lỗi cần rollback |
| Dùng producer không transactional trong Kafka listener transactional | Output có thể nằm ngoài consumed-offset transaction | Dùng KafkaTemplate/ProducerFactory tham gia đúng transaction |
| Tự commit consumer offset trong listener | Phá vỡ nguyên tử offset + output Kafka | Để container sendOffsetsToTransaction |
| Ghi database rồi gửi Kafka mà không có recovery bền vững | Có cửa sổ mất event sau DB commit | Transactional outbox hoặc durable reconciliation |
| Chỉ retry vô hạn khi Kafka outage | Giữ thread/DB lock, tăng lag | Backoff hữu hạn, outbox relay và alert |
| Giữ DB transaction mở khi gọi API lâu | Lock contention, timeout, rebalance | Transaction ngắn, idempotent workflow |
| Replay DLT mà không kiểm tra DB | Có thể lặp side effect đã commit | Audit event ID, kiểm tra DB/output và replay có kiểm soát |

## 29. Lựa chọn kiến trúc theo yêu cầu

| Yêu cầu nghiệp vụ | Hướng tiếp cận phù hợp |
|---|---|
| Consume Kafka và produce Kafka, không ghi DB | Consumer-initiated Kafka transaction với consumed offsets |
| DB state và Kafka event phải nhất quán sau sự cố | Transactional outbox + relay/CDC + idempotent consumer |
| DB-first direct produce nhưng mất event có thể được bù trừ | Transaction synchronization + durable reconciliation |
| Nhiều service, API và DB tham gia workflow | Saga/state machine, outbox và idempotency từng bước |
| Event cần thứ tự theo aggregate | Kafka key theo aggregate ID, outbox ordering policy và downstream version check |
| Không được xử lý duplicate side effect | Event ID duy nhất, DB unique constraint và idempotent handler |

Nếu dùng Spring transaction synchronization, tài liệu thiết kế nên ghi rõ manager nào là outer, manager nào inner, thứ tự commit, hành vi khi exception bị ném và cách phục hồi khi commit thứ hai thất bại. Những điều này quan trọng hơn việc chỉ liệt kê annotation @Transactional trong code.

## 30. Quy trình triển khai đáng tin cậy

Đối với một pipeline kết hợp Spring Kafka và database:

1. Xác định DB hay Kafka là source of truth cho trạng thái nghiệp vụ.
2. Liệt kê tất cả side effects: SQL write, Kafka output, REST API, email, cache.
3. Xác định transaction manager và boundary thực sự của từng side effect.
4. Nếu dùng Kafka container transaction, bảo đảm KafkaTemplate, ProducerFactory và consumed offset tham gia cùng Kafka transaction.
5. Nếu dùng DB transaction, đặt đúng qualifier và kiểm tra lời gọi qua Spring proxy.
6. Tài liệu hóa commit order DB-first/Kafka-first và failure window.
7. Không dựa vào synchronization như một distributed atomic transaction.
8. Dùng transactional outbox nếu không được để DB commit thành công mà mất event cần phát.
9. Dùng event ID ổn định, unique constraints và idempotent side effects.
10. Đảm bảo downstream Kafka consumer read_committed nếu cần bỏ qua aborted transactional output.
11. Cấu hình retry, DLT và reconciliation cho cả Kafka commit failures lẫn database failures.
12. Theo dõi DB/Kafka commit outcomes, outbox backlog, DLT và độ trễ recovery.
13. Kiểm thử crash giữa hai commit, DB rollback, Kafka commit failure, rebalance và duplicate delivery.

**Đồng bộ Kafka transaction với DB transaction** trong Spring Kafka chủ yếu giúp **điều phối hai local transaction theo một thứ tự nhất định**. Nó không làm commit của database và Kafka trở thành nguyên tử tuyệt đối. Với luồng Kafka-to-Kafka, Kafka transaction có thể commit output và consumed offsets cùng nhau. Nhưng khi business state nằm trong database, vẫn tồn tại cửa sổ lỗi sau một commit thành công và trước commit còn lại. Nếu yêu cầu là **không mất event sau khi DB đã commit**, transactional outbox cùng idempotency và reconciliation thường là nền tảng đáng tin cậy hơn việc chỉ bật @Transactional và transaction synchronization.
