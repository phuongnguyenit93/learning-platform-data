# Nested @Transactional cho thứ tự commit

Một nghiệp vụ Spring Boot thường cần **vừa cập nhật database vừa công bố sự kiện Kafka**. Ví dụ khi xác nhận đơn hàng, ứng dụng cập nhật trạng thái trong PostgreSQL và gửi OrderConfirmed tới topic orders.events. Hai thao tác này có thể nằm trong hai local transactions do hai transaction manager khác nhau quản lý. Dù cùng nằm trong một Java method, việc commit database và commit Kafka **không tự động trở thành một thao tác nguyên tử duy nhất**.

**Nested @Transactional cho thứ tự commit** là kỹ thuật đặt các phương thức transactional bên trong nhau, dùng transaction manager phù hợp cho từng tài nguyên, nhằm điều khiển **database commit trước Kafka** hoặc **Kafka commit trước database**. Chọn thứ tự quan trọng vì sau khi tài nguyên thứ nhất commit, tài nguyên thứ hai vẫn có thể thất bại.

Trong chương **Kafka và database** của **Spring Kafka Reliability Operations**, điều phải hiểu là: nested transactional methods giúp kiểm soát thứ tự commit; chúng **không phải two-phase commit**, không tự cung cấp exactly-once xuyên database và Kafka, và vẫn cần idempotency, outbox hoặc reconciliation khi dữ liệu không được phép lệch.

## 1. Một business operation, hai commit points

Giả sử service có hai side effects:

1. Đổi trạng thái order 1001 từ CREATED sang CONFIRMED trong database.
2. Công bố event OrderConfirmed(orderId=1001) lên Kafka.

~~~mermaid
flowchart LR
    A["HTTP confirmOrder"] --> S["OrderService"]
    S --> D["PostgreSQL orders"]
    S --> K["Kafka orders.events"]
    D --> C1["DB COMMIT"]
    K --> C2["Kafka COMMIT"]
~~~

Nếu không có một giao thức phân tán chung để commit cả hai, có bốn trạng thái sau:

| Database | Kafka | Kết quả nghiệp vụ |
|---|---|---|
| Committed | Committed | DB và event cùng phản ánh xác nhận đơn |
| Committed | Không committed | DB đã đổi nhưng downstream thiếu event |
| Không committed | Committed | Downstream nhận event không tương ứng DB committed |
| Không committed | Không committed | Operation có thể được retry theo chính sách |

Hai trạng thái ở giữa là **dual-write inconsistency**. Không có cách sắp xếp hai local commits nào loại bỏ mọi failure window. Thứ tự chỉ quyết định **loại bất nhất nào có thể xảy ra sau commit đầu tiên**.

### 1.1 Lỗi không chỉ là exception khi gửi

Một KafkaTemplate.send() hoàn tất thành công chỉ phản ánh một mốc trong quá trình gửi tới Kafka. Khi producer đang trong transaction, **send acknowledgment khác transaction commit**. Kafka record có thể đã được broker ACK nhưng transaction sau đó bị abort; consumer read_committed sẽ không đọc record đã abort như record hợp lệ.

Tương tự, repository.save() hoặc EntityManager.flush() thành công không có nghĩa SQL transaction đã commit. Database commit có thể thất bại sau flush vì constraint trì hoãn, network hoặc lỗi tại thời điểm commit.

Vì vậy, khi nói “DB-first” hoặc “Kafka-first”, phải nói rõ **commit thực sự**, không phải thứ tự gọi save() và send().

## 2. Hai transaction managers độc lập

Spring dùng transaction manager để thiết lập và kết thúc một local transaction.

- **JpaTransactionManager** thường quản lý JPA/Hibernate database transaction.
- **DataSourceTransactionManager** thường quản lý JDBC database transaction.
- **KafkaTransactionManager** quản lý Kafka transaction qua transactional ProducerFactory.

Một annotation cần chỉ rõ manager mà nó sử dụng:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void updateDatabase() {
    // ...
}

@Transactional(transactionManager = "kafkaTransactionManager")
public void publishKafkaEvent() {
    // ...
}
~~~

Trong ứng dụng có cả DB và Kafka managers, annotation chỉ viết @Transactional có thể dùng manager mặc định không đúng kỳ vọng. Để commit order có thể đọc và kiểm thử, hãy đặt tên manager rõ ràng trong cả outer và inner methods.

### 2.1 “Nested” là nested calls, không phải Propagation.NESTED

Trong bài này, **nested @Transactional** nghĩa là phương thức A có DB transaction gọi phương thức B có Kafka transaction qua Spring proxy. Chúng là **hai local transactions khác nhau**.

Nó **không** đồng nghĩa:

~~~java
@Transactional(propagation = Propagation.NESTED)
~~~

Propagation.NESTED có thể dùng database savepoint khi manager hỗ trợ. Database savepoint không tạo một Kafka subtransaction, không làm Kafka và SQL commit nguyên tử.

Tương tự, dùng Propagation.REQUIRES_NEW trên một manager không biến hai resources thành distributed transaction. REQUIRES_NEW thay đổi lifecycle/suspend của transaction tương ứng; nó không cung cấp two-phase commit xuyên Kafka và database.

## 3. Định nghĩa DB-first và Kafka-first chính xác

| Chiến lược | Commit thứ nhất | Commit thứ hai | Failure window quan trọng |
|---|---|---|---|
| **DB-first** | Database | Kafka | DB đã committed, Kafka commit có thể thất bại |
| **Kafka-first** | Kafka | Database | Kafka đã committed, DB commit có thể thất bại |

Có hai cách tổ chức thường gặp:

**DB-first qua Spring transaction synchronization:**

~~~text
Outer @Transactional(dbTransactionManager)
    UPDATE database
    KafkaTemplate.send() trong Kafka transaction được đồng bộ
Outer method kết thúc
    DB COMMIT
    Kafka COMMIT (synchronized secondary transaction)
~~~

**Kafka-first qua nested transactional methods:**

~~~text
Outer @Transactional(dbTransactionManager)
    UPDATE database
    Inner @Transactional(kafkaTransactionManager)
        KafkaTemplate.send()
    Inner method kết thúc
        Kafka COMMIT
Outer method kết thúc
    DB COMMIT
~~~

Điểm dễ nhầm: **Kafka-first không có nghĩa Kafka transaction phải là outermost transaction**. Nếu Kafka transaction là outer và DB transaction là inner thì DB transaction có thể commit trước khi outer Kafka transaction kết thúc — lại thành DB-first.

## 4. Điều kiện: Kafka ProducerFactory phải transaction-capable

KafkaTemplate cần producer transactional để tham gia Kafka transaction hoặc synchronization với Spring database transaction.

Với Spring Boot, cấu hình thường gồm:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      transaction-id-prefix: orders-tx-instance-01-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        acks: all
        enable.idempotence: true
        transaction.timeout.ms: 60000
~~~

Đây chỉ là **một instance minh họa**. Trong production nhiều pod, transaction ID prefix phải duy nhất giữa các ProducerFactory instances đang chạy đồng thời. Không dùng cùng giá trị instance-01 cho mọi pod, vì các transactional producer có transactional.id trùng nhau có thể fencing lẫn nhau.

Một guard lúc khởi động:

~~~java
@Component
public class TransactionalProducerGuard {

    public TransactionalProducerGuard(
            ProducerFactory<String, OrderConfirmed> factory) {

        if (!factory.transactionCapable()) {
            throw new IllegalStateException(
                "Order publisher requires transactional ProducerFactory"
            );
        }
    }
}
~~~

Phải kiểm tra **factory thực sự được KafkaTemplate dùng**. Một ứng dụng có factory transactional và non-transactional song song; kiểm tra nhầm factory không có giá trị.

### 4.1 KafkaTransactionManager và KafkaTemplate cùng factory

Ví dụ khai báo beans:

~~~java
@Bean
KafkaTemplate<String, OrderConfirmed> orderKafkaTemplate(
        ProducerFactory<String, OrderConfirmed> orderProducerFactory) {
    return new KafkaTemplate<>(orderProducerFactory);
}

@Bean
KafkaTransactionManager<String, OrderConfirmed> kafkaTransactionManager(
        ProducerFactory<String, OrderConfirmed> orderProducerFactory) {
    return new KafkaTransactionManager<>(orderProducerFactory);
}
~~~

KafkaTemplate và KafkaTransactionManager dùng cùng instance ProducerFactory. Nếu dùng Spring Boot auto-configuration, Boot có thể cấu hình các beans tương ứng khi được bật bằng properties và không bị custom beans ghi đè; cần kiểm tra trên phiên bản đang triển khai.

**transactionCapable()=true chỉ nói factory có khả năng tạo transactional producer**, không có nghĩa giao dịch đã được mở hoặc consumer offsets đã được đưa vào transaction.

## 5. DB-first bằng database @Transactional và Kafka synchronization

Spring Kafka hỗ trợ đồng bộ Kafka transaction với một Spring-managed database transaction. Khi DB transaction là transaction chính và KafkaTemplate được sử dụng với transactional ProducerFactory, Kafka transaction có thể được synchronized với transaction ngoài theo cơ chế framework.

Ví dụ:

~~~java
@Service
public class DbFirstOrderService {

    private final OrderRepository repository;
    private final KafkaTemplate<String, OrderConfirmed> kafkaTemplate;

    public DbFirstOrderService(
            OrderRepository repository,
            KafkaTemplate<String, OrderConfirmed> kafkaTemplate) {
        this.repository = repository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void confirm(String orderId) {

        Order order = repository.findById(orderId)
            .orElseThrow();

        order.confirm();

        kafkaTemplate.send(
            "orders.events",
            orderId,
            new OrderConfirmed(orderId)
        );
    }
}
~~~

Giả định DB transaction manager đúng với repository (JpaTransactionManager nếu dùng JPA), KafkaTemplate transactional, Spring transaction synchronization đang có hiệu lực và không có Kafka outer transaction khác. Khi đó:

~~~mermaid
sequenceDiagram
    participant S as DbFirstOrderService
    participant DB as Database
    participant KT as KafkaTemplate
    participant K as Kafka broker
    S->>DB: BEGIN DB transaction
    S->>DB: UPDATE orders
    S->>KT: send(OrderConfirmed)
    KT->>K: Produce record trong Kafka transaction
    S->>DB: COMMIT DB
    S->>K: COMMIT Kafka transaction
~~~

### 5.1 Tại sao đây là DB-first?

Mặc dù KafkaTemplate.send() được gọi trước khi DB commit, Kafka transaction vẫn chưa kết thúc. Spring synchronization điều phối việc hoàn tất Kafka transaction sau transaction chính (DB). Thứ tự **send** không phải thứ tự **commit**.

Ví dụ timeline:

~~~text
t0  BEGIN DB
t1  UPDATE orders
t2  Kafka send được đưa vào Kafka transaction
t3  Java method kết thúc bình thường
t4  DB COMMIT                            <-- DB đã bền vững
t5  Kafka COMMIT                         <-- event committed
~~~

### 5.2 Lỗi sau DB commit

Nếu t4 thành công, t5 thất bại:

~~~text
orders.status = CONFIRMED         [DB COMMITTED]
OrderConfirmed event             [KAFKA COMMIT FAILED]
~~~

Đây là rủi ro quan trọng của DB-first. Database không thể tự rollback transaction đã hoàn tất chỉ vì Kafka commit sau đó lỗi. Ở các phiên bản Spring Kafka hiện đại, lỗi commit của transaction đồng bộ thứ cấp có thể được propagate tới caller; cần kiểm tra semantics cụ thể của version đang chạy.

Một HTTP 500 sau exception **không chứng minh DB rollback**. Nếu client retry toàn command, nó có thể tạo duplicate business effect hoặc event, hoặc bỏ qua event bị thiếu vì database đã ở trạng thái CONFIRMED.

### 5.3 Khi DB-first phù hợp

DB-first có thể phù hợp nếu:

- Database là source of truth.
- Event được tái tạo bằng reconciliation đáng tin cậy.
- Không có yêu cầu tuyệt đối rằng event phải được publish tức thời.
- Request có idempotency key và hệ thống phân biệt “DB thành công nhưng event đang chờ”.
- Có monitoring phát hiện các operation thiếu Kafka event.

Nếu event **không được phép mất** và không có durable publication intent, nên cân nhắc transactional outbox thay vì chỉ synchronization.

## 6. Kafka-first bằng nested @Transactional

Muốn Kafka commit trước khi DB commit, dùng **outer DB @Transactional** gọi **inner Kafka @Transactional** nằm trên một Spring bean khác. Khi inner method kết thúc, KafkaTransactionManager commit. Sau đó outer method kết thúc mới đến DB commit.

~~~mermaid
sequenceDiagram
    participant API as API
    participant OUT as Outer DB service
    participant IN as Inner Kafka publisher
    participant DB as Database
    participant K as Kafka broker
    API->>OUT: confirm(orderId)
    OUT->>DB: BEGIN DB transaction
    OUT->>DB: UPDATE order
    OUT->>IN: publishConfirmed() qua Spring proxy
    IN->>K: BEGIN Kafka transaction
    IN->>K: SEND OrderConfirmed
    IN->>K: COMMIT Kafka transaction
    IN-->>OUT: Return
    OUT->>DB: COMMIT DB
    OUT-->>API: Return
~~~

### 6.1 Outer DB service

~~~java
@Service
public class KafkaFirstOrderService {

    private final OrderRepository repository;
    private final TransactionalOrderPublisher publisher;

    public KafkaFirstOrderService(
            OrderRepository repository,
            TransactionalOrderPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void confirm(String orderId) {

        Order order = repository.findById(orderId)
            .orElseThrow();

        order.confirm();

        // Đi qua Spring proxy ở bean khác:
        publisher.publishConfirmed(orderId);

        // DB transaction chỉ commit sau khi method này kết thúc.
    }
}
~~~

### 6.2 Inner Kafka publisher

~~~java
@Service
public class TransactionalOrderPublisher {

    private final KafkaTemplate<String, OrderConfirmed> kafkaTemplate;

    public TransactionalOrderPublisher(
            KafkaTemplate<String, OrderConfirmed> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishConfirmed(String orderId) {

        kafkaTemplate.send(
            "orders.events",
            orderId,
            new OrderConfirmed(orderId)
        );
    }
}
~~~

Với transaction managers và Spring proxy được cấu hình đúng, inner Kafka transaction được commit khi publishConfirmed() kết thúc. Outer DB transaction vẫn đang mở cho đến khi confirm() kết thúc.

### 6.3 Timeline Kafka-first

~~~text
t0  BEGIN DB
t1  UPDATE orders (chưa commit)
t2  BEGIN Kafka transaction từ inner method
t3  Kafka send(OrderConfirmed)
t4  Kafka COMMIT                            <-- event committed
t5  inner publishConfirmed() return
t6  DB COMMIT                               <-- DB committed
~~~

Nếu Kafka commit thất bại tại t4 và exception được propagate, outer DB transaction có thể rollback theo rollback rules. Tuy nhiên, nếu Kafka commit thành công rồi DB commit thất bại tại t6, event vẫn có thể tồn tại trong Kafka.

### 6.4 Kafka-first có một race nghiêm trọng

Ngay sau t4 nhưng trước t6, consumer đọc read_committed có thể nhìn thấy OrderConfirmed và query database. Với isolation phù hợp, consumer vẫn thấy order status CREATED vì DB transaction chưa commit.

Nếu DB cuối cùng rollback, consumer đã nhận một event mô tả thay đổi **không bao giờ trở thành DB committed state**.

Kafka-first vì vậy không nên được lựa chọn chỉ để “publish sớm”. Nó phù hợp khi kiến trúc có thể chịu hoặc bù trừ trường hợp event committed trước database; nếu database là nguồn sự thật và consumer phải dựa vào DB state, DB-first hoặc outbox thường dễ vận hành hơn.

### 6.5 Không gửi Kafka trước khi mở inner transaction

Nếu outer DB method đã gọi KafkaTemplate.send() trước rồi mới gọi inner Kafka publisher, template có thể đã đồng bộ Kafka transaction với DB transaction bên ngoài. Khi đó boundary mong muốn không còn rõ.

Trong thiết kế Kafka-first, gom những Kafka sends cần commit trước vào **đúng inner Kafka transactional method** và kiểm chứng transaction outcome bằng test.

## 7. Đảo outer/inner không đồng nghĩa đảo commit order

Một sai lầm phổ biến:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void outer() {
    databaseService.updateInTransaction();
    kafkaTemplate.send(...);
}
~~~

Nếu databaseService.updateInTransaction() dùng DB transaction và kết thúc trước outer Kafka method, **DB commit có thể xảy ra trước Kafka commit**. Đây vẫn là DB-first mặc dù Kafka transaction được mở trước.

Tương tự, một @Transactional không chỉ định manager không chứng minh manager nào được dùng khi ứng dụng có nhiều transaction managers.

Hãy nhớ quy tắc:

**Commit của inner method thường diễn ra trước commit của outer method, miễn hai methods thật sự mở hai local transactions độc lập đúng như thiết kế.**

Không suy luận thứ tự commit bằng thứ tự annotation xuất hiện trong source code. Muốn chính xác, cần xác định transaction nào được mở bởi proxy hoặc container, manager của transaction đó, và thời điểm interceptors kết thúc.

## 8. Spring AOP proxy và self-invocation

Nested @Transactional chỉ hoạt động như dự định khi inner method được Spring transaction interceptor xử lý.

Ví dụ **không đáng tin cậy**:

~~~java
@Service
public class OneBeanOrderService {

    @Transactional(transactionManager = "dbTransactionManager")
    public void confirm(String orderId) {
        repository.updateStatus(orderId, "CONFIRMED");

        // Self-invocation:
        publishConfirmed(orderId);
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishConfirmed(String orderId) {
        kafkaTemplate.send("orders.events", orderId, ...);
    }
}
~~~

Cuộc gọi từ confirm() đến publishConfirmed() đi thẳng vào cùng object thay vì qua Spring proxy trong proxy mode mặc định. Do vậy, annotation @Transactional của inner method có thể **không được áp dụng**. KafkaTemplate có thể chỉ đồng bộ với DB transaction ngoài, khiến thứ tự trở thành DB-first, hoặc ném exception tùy cấu hình.

### 8.1 Phương án an toàn hơn

~~~text
KafkaFirstOrderService.confirm()
    @Transactional(dbTransactionManager)
       |
       v qua Spring proxy
TransactionalOrderPublisher.publishConfirmed()
    @Transactional(kafkaTransactionManager)
       |
       v
KafkaTemplate
~~~

Tách thành hai Spring beans riêng để mỗi proxy interceptor có thể mở và commit resource transaction tại boundary dự kiến.

### 8.2 Các trường hợp khác có thể phá transaction boundary

- Method private hoặc final không được proxied theo cơ chế mặc định tương ứng.
- Object được khởi tạo bằng new thay vì do Spring quản lý.
- Một method cùng bean gọi method khác qua this.
- @Async hoặc executor làm việc Kafka chuyển sang thread khác, không nhận transaction context theo thread.
- Annotation nằm trên code path không được gọi qua proxy.
- Ứng dụng đã có Kafka listener container transaction bao ngoài khiến inner @Transactional tham gia một Kafka transaction hiện có.

Chỉ đọc source code có hai annotations là chưa đủ. **Cần integration test xác nhận commit order.**

## 9. @Transactional rollback rules và exception propagation

Spring @Transactional có rollback policy. Theo mặc định trong nhiều cấu hình imperative, RuntimeException và Error khiến transaction rollback, còn checked exception có thể cần rollbackFor cụ thể.

Xét Kafka-first:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void confirm(String orderId) {
    repository.updateStatus(orderId, "CONFIRMED");
    publisher.publishConfirmed(orderId);
}
~~~

Nếu Kafka transaction thất bại và exception lan ra khỏi confirm(), outer database transaction có thể rollback. Nhưng nếu code bắt exception, log rồi return bình thường:

~~~java
try {
    publisher.publishConfirmed(orderId);
}
catch (Exception ex) {
    log.error("Kafka publish failed", ex);
    // Return bình thường: outer DB transaction có thể commit.
}
~~~

DB commit có thể vẫn xảy ra dù Kafka đã fail. Đây có thể là chủ đích nếu có outbox/reconciliation, nhưng không nên do vô tình nuốt lỗi.

### 9.1 Commit failure sau tài nguyên thứ nhất không thể rollback ngược

DB-first:

~~~text
DB COMMIT [thành công]
Kafka COMMIT [thất bại]
~~~

Kafka-first:

~~~text
Kafka COMMIT [thành công]
DB COMMIT [thất bại]
~~~

Một exception phát sinh ở commit thứ hai không tự rollback commit thứ nhất. Khi đó cần nghiệp vụ bù trừ hoặc khôi phục, không phải một rollback Java method đơn giản.

### 9.2 Kết quả commit có thể chưa rõ

Nếu Kafka commit request đã đến broker nhưng client không nhận response vì timeout, từ phía ứng dụng có thể khó kết luận ngay liệu commit đã được chấp nhận hay chưa. Tương tự, database commit có thể có các lỗi network khiến caller chưa biết kết quả.

Không suy diễn “ném exception nên chắc chắn chưa commit”. Dùng operation/event ID, quan sát trạng thái bền vững, idempotency và reconciliation trước khi retry toàn operation.

## 10. KafkaTemplate.send() và transaction commit là hai bước khác nhau

KafkaTemplate.send() trong Spring Kafka hiện đại thường trả CompletableFuture; các phiên bản cũ có thể dùng API future khác. Future hoàn tất không đồng nghĩa toàn bộ Kafka transaction đã commit.

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishConfirmed(String orderId) {

    CompletableFuture<SendResult<String, OrderConfirmed>> future =
        kafkaTemplate.send(
            "orders.events",
            orderId,
            new OrderConfirmed(orderId)
        );

    // Có thể quan sát kết quả gửi, nhưng commit sẽ
    // được KafkaTransactionManager xử lý ở transaction boundary.
}
~~~

Có bốn mốc cần phân biệt:

1. KafkaTemplate.send() được gọi.
2. Producer nhận send result/ACK hoặc exception.
3. Kafka transaction commit/abort.
4. read_committed consumer có thể đọc record committed.

Nếu nghiệp vụ cần phát hiện send failure ngay trong method, có thể chờ future có timeout hợp lý. Nhưng việc chờ kéo dài transaction lifetime, và dù send future thành công thì transaction commit vẫn có thể thất bại.

**Không đẩy send sang CompletableFuture.runAsync() trong inner Kafka transactional method rồi return ngay**, nếu chưa thiết kế propagation transaction context và failure handling. Transaction của Spring thường gắn với thread; công việc trên executor thread khác có thể nằm ngoài transaction dự kiến.

## 11. Bảng quyết định commit order

| Điều kiện nghiệp vụ | DB-first | Kafka-first | Ghi chú |
|---|---|---|---|
| DB là source of truth | Thường dễ hiểu hơn | Rủi ro event trước DB state | Vẫn cần xử lý event thiếu |
| Kafka là nguồn sự thật, DB tái tạo được | Có thể | Có thể cân nhắc | Cần event-first/replay được thiết kế rõ |
| Event không được phép thiếu sau DB commit | Chưa đủ một mình | Không tự giải quyết | Outbox phù hợp hơn |
| Consumer phải query DB ngay khi thấy event | Thường an toàn hơn về visibility | Có race | Không bảo đảm atomic dual write |
| Có thể bù trừ event đã phát nhưng DB rollback | Tùy | Có thể chấp nhận | Cần compensation protocol |
| Muốn API đồng bộ đơn giản | Có thể | Có thể | Cả hai vẫn có failure window |
| Yêu cầu exactly-once xuyên SQL và Kafka | Không | Không | Cần kiến trúc khác hoặc nhất quán cuối cùng |

Nên viết rõ trong design document: transaction nào là primary, transaction nào secondary, và hệ thống làm gì nếu commit thứ hai lỗi.

## 12. Nested transactions khác transactional outbox

**Transactional outbox** thường phù hợp khi database là nguồn sự thật và không được phép thiếu Kafka event sau khi DB update.

~~~mermaid
flowchart TD
    S["Business service"] --> T["Một DB transaction"]
    T --> D["UPDATE orders"]
    T --> O["INSERT outbox_event"]
    D --> C["DB COMMIT"]
    O --> C
    C --> R["Outbox relay / CDC"]
    R --> K["Kafka orders.events"]
    K --> P["Downstream consumers"]
~~~

Trong một DB transaction:

1. Cập nhật orders.
2. Ghi outbox_event chứa event ID và payload/contract.
3. Commit một lần tại database.

Outbox relay phát sự kiện Kafka sau commit. Nếu Kafka không khả dụng, outbox row vẫn tồn tại để retry. Nếu relay phát Kafka thành công rồi crash trước khi đánh dấu row đã publish, có thể publish trùng; consumer cần idempotency.

Ví dụ ý tưởng:

~~~java
@Service
public class OutboxOrderService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional(transactionManager = "dbTransactionManager")
    public void confirm(String orderId, String operationId) {

        Order order = orders.findById(orderId).orElseThrow();
        order.confirm();

        outbox.save(
            OutboxEvent.orderConfirmed(
                operationId,
                orderId
            )
        );
    }
}
~~~

Outbox giải quyết **durable publication intent**: DB state và ý định phát event được ghi nguyên tử trong cùng database. Nó không hứa mỗi event chỉ có một Kafka record vật lý; phía consumer phải deduplicate.

### 12.1 Khi nào vẫn dùng nested @Transactional?

Nested @Transactional có thể hữu ích khi:

- Mục tiêu chính là điều khiển commit order.
- Inconsistency có cơ chế reconciliation rõ ràng.
- Có thể chấp nhận event eventually consistent.
- Hệ thống không cần durable outbox cho nghiệp vụ này.
- Muốn kiểm soát một đoạn transactional Kafka publish trong cùng business operation.

Nhưng nếu quy định là “một khi DB đã xác nhận đơn, sự kiện bắt buộc phải được phát dù Kafka outage”, outbox thường là giải pháp tin cậy hơn việc hy vọng commit thứ hai luôn thành công.

## 13. Request idempotency và consumer inbox

Vì các local transactions có thể commit không đồng bộ, client và downstream cần được bảo vệ khỏi duplicate.

### 13.1 Request ID

API xác nhận order nên có operationId/requestId ổn định. Khi client retry vì HTTP timeout hoặc 500, service kiểm tra operation đã được thực hiện chưa.

Không tạo event ID mới theo mỗi lần retry rồi coi đó là một operation mới nếu nghiệp vụ chỉ muốn một lần xác nhận.

### 13.2 Event ID

Một OrderConfirmed có eventId duy nhất. Nếu outbox relay hoặc Kafka producer phát lại, consumer có thể phát hiện duplicate bằng eventId.

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong một DB transaction của consumer, ghi processed event cùng với business effect. Dựa duy nhất vào SELECT exists rồi INSERT riêng rẽ không có unique constraint có thể bị race khi hai workers cùng xử lý.

### 13.3 Kafka exactly-once không bao trùm DB side effect

Trong consume-transform-produce, Kafka có thể atomic commit output records và consumed offsets nếu container transactional được cấu hình đúng. Nhưng ghi database trong listener vẫn là transaction khác. Nếu database committed rồi Kafka transaction abort, input record có thể được giao lại, làm database side effect lặp.

Nested @Transactional không thay thế inbox/deduplication ở consumer.

## 14. Đặc biệt lưu ý @KafkaListener transactional container

Một ví dụ outer DB service gọi inner Kafka publisher **không được áp dụng máy móc cho @KafkaListener đang chạy trong Kafka container transaction**.

Với transactional listener container, Kafka transaction có thể được mở **trước khi listener method được gọi**:

~~~text
Kafka listener container opens Kafka transaction
    listener invoked
        DB transactional method begins
        DB COMMIT
    listener returns
    container sends consumed offsets to Kafka transaction
Kafka COMMIT
~~~

Đây thường là DB-first về thứ tự commit, vì DB transaction bên trong kết thúc trước Kafka transaction của container.

Khi đã có active Kafka transaction bên ngoài, một inner method @Transactional("kafkaTransactionManager") có thể tham gia transaction đang có thay vì tạo Kafka transaction mới commit ngay. Vì vậy, không kết luận một call graph là Kafka-first chỉ vì đã tách inner Kafka method.

Cần phân biệt:

- **Producer service workflow:** outer DB transaction và inner Kafka transaction như ví dụ Kafka-first.
- **Consumer container workflow:** container có thể mở Kafka transaction trước listener, và commit Kafka outputs + consumed offsets khi listener thành công.
- **Database trong listener:** vẫn là local DB transaction, có failure window và idempotency requirement.

Với transactional listener, exception thường làm Kafka transaction abort; Spring Kafka có các cơ chế rollback/recovery như AfterRollbackProcessor theo phiên bản. Không dùng trực tiếp mô hình DefaultErrorHandler non-transactional để suy luận toàn bộ transactional flow.

## 15. Producer fencing, timeout và lifecycle

Nested transactions có thể thất bại do cấu hình Kafka producer chứ không phải code DB.

### 15.1 transactionIdPrefix trùng giữa pods

~~~text
Pod A: transactionIdPrefix = orders-tx-common-
Pod B: transactionIdPrefix = orders-tx-common-
~~~

Nếu factory sinh cùng transactional.id, một producer có thể fencing producer khác. Lỗi ProducerFencedException có thể làm Kafka commit thất bại. Cần cấp prefix duy nhất cho từng active instance và quản lý producer lifecycle đúng.

### 15.2 Transaction kéo dài

Nếu inner Kafka method thực hiện nhiều external network requests hoặc chờ quá lâu, transaction có thể vượt transaction.timeout.ms. Transaction coordinator có thể abort.

Không dùng Kafka transaction để giữ nguyên một workflow kéo dài. Chỉ bao những Kafka operations cần commit/abort cùng nhau, giới hạn thời gian xử lý và timeout rõ ràng.

### 15.3 Trùng lặp do retry sau commit không rõ

Khi remote commit trả về lỗi mạng, service phải coi outcome là cần đối chiếu. Không retry vô hạn với producer bị fenced hoặc fatal, và không tự động phát business event ID mới mỗi lần retry.

## 16. Theo dõi commit order trong production

Cần quan sát riêng:

- DB commit / rollback outcome.
- Kafka send ACK.
- Kafka transaction commit / abort outcome.
- Transaction synchronization error.
- Operation ID và event ID.
- Retry/reconciliation state.
- Outbox pending count và oldest pending age, nếu có outbox.
- Duplicate detection ở consumer.
- Kafka producer fencing và transaction timeout.

Ví dụ log có ngữ cảnh:

~~~text
operationId=confirm-1001
eventId=evt-1001
strategy=DB_FIRST
dbCommit=SUCCESS
kafkaCommit=FAILED
action=RECONCILIATION_REQUIRED
~~~

Với Kafka-first:

~~~text
operationId=confirm-1002
eventId=evt-1002
strategy=KAFKA_FIRST
kafkaCommit=SUCCESS
dbCommit=FAILED
action=COMPENSATION_REQUIRED
~~~

Đừng log một dòng “publish success” ngay khi send() return rồi xem đó là Kafka transaction commit.

### 16.1 Cách điều tra khi bất nhất

1. Xác định operationId/eventId.
2. Đọc DB state đã committed.
3. Xác định event thực sự committed trên Kafka theo topic/key/eventId.
4. Kiểm tra strategy hiện tại và transaction managers của method.
5. Kiểm tra method invocation có đi qua Spring proxy không.
6. Phân biệt send failure, Kafka commit failure và DB commit failure.
7. Kiểm tra transaction ID prefix, broker health và timeout.
8. Đối chiếu downstream side effects.
9. Quyết định publish missing event, emit compensation hoặc chạy reconciliation.
10. Chỉ retry operation khi có idempotency/recovery policy rõ ràng.

## 17. Integration test chứng minh thứ tự commit

Mock KafkaTemplate hoặc repository không chứng minh được commit order. Nên dùng database thật (PostgreSQL Testcontainers) và Kafka broker tích hợp để kiểm thử hai local transactions.

### 17.1 Test DB-first happy path

- Gọi DB-first confirm với operation ID mới.
- Xác nhận DB order status đã committed.
- Dùng Kafka consumer read_committed để đọc OrderConfirmed.
- Xác nhận event ID và order ID khớp DB.
- Thu transaction lifecycle logs/traces để xác minh DB commit trước Kafka commit.

### 17.2 Test Kafka-first happy path

- Gọi outer DB service.
- Inner Kafka publisher commit thành công.
- Dùng một barrier/test latch để giữ outer DB transaction chưa kết thúc.
- Dùng read_committed consumer nhận Kafka event.
- Query DB qua một connection khác; tùy isolation level, trạng thái uncommitted chưa xuất hiện.
- Cho DB commit rồi xác nhận trạng thái cuối cùng.

Test này chứng minh event có thể visible **trước** DB committed trong Kafka-first.

### 17.3 Fault injection đúng failure window

DB-first test phải làm **DB commit thành công** rồi mô phỏng **Kafka commit thất bại**. Ném exception trong method trước commit không kiểm tra được khoảng lỗi đó.

Kafka-first test phải làm **Kafka commit thành công** rồi mô phỏng **DB commit thất bại**. Ném exception trước khi gọi inner publisher cũng không kiểm tra được khoảng lỗi.

Các failure-injection hook và proxy cần được thiết kế cẩn thận để không làm giả sai thứ tự transaction.

### 17.4 Test self-invocation

- Gọi inner annotated method trong cùng bean.
- Quan sát proxy không intercept self-invocation trong cấu hình mặc định.
- Tách inner method sang bean khác.
- Chạy lại và xác nhận transaction boundary/commit order như dự kiến.

### 17.5 Test retry và outbox

- Client retry cùng operationId sau một response lỗi.
- Xác nhận database không tạo business effect trùng.
- Xác nhận outbox event vẫn tồn tại khi Kafka outage.
- Cho relay publish lại rồi crash trước khi đánh dấu published.
- Xác nhận consumer inbox/deduplication xử lý trùng an toàn.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Tưởng Kafka-first nhưng vẫn DB-first | Self-invocation hoặc inner transaction không mở | Tách Spring beans và xác minh proxy |
| KafkaTemplate không có transaction | ProducerFactory không transaction capable | transactionIdPrefix và wiring |
| Event xuất hiện trước DB update | Kafka-first commit trước DB | Đánh giá race và contract downstream |
| DB đã đổi, event thiếu | Kafka commit thất bại sau DB commit | Outbox/reconciliation |
| Event có nhưng DB rollback | DB commit thất bại sau Kafka commit | Compensation/reconciliation |
| Hai pods fencing nhau | Trùng transactional ID prefix | Identity riêng cho từng active instance |
| @Transactional chạy nhưng sai manager | Manager mặc định không phải DB/Kafka dự kiến | Explicit transactionManager name |
| Kafka send ACK thành công nhưng read_committed không thấy | Transaction chưa commit hoặc abort | Xem transaction outcome, LSO |
| Database update lặp sau retry | Thiếu request/event idempotency | Unique constraints, inbox |
| Nested Kafka method không commit ngay | Đã có Kafka transaction bao ngoài | Xác định container transaction boundary |

## 19. Những hiểu nhầm cần tránh

**“Hai @Transactional bằng một distributed transaction.”** Không. Đây thường là hai local transactions.

**“Nested @Transactional nghĩa là Propagation.NESTED.”** Không trong ngữ cảnh này; nested là phương thức DB và Kafka gọi lồng nhau.

**“Kafka là outer transaction thì Kafka commit trước.”** Không nhất thiết; inner DB transaction có thể commit trước outer Kafka.

**“Đã gọi send() trước thì Kafka commit trước.”** Không. Send order khác commit order.

**“Kafka-first luôn tốt hơn vì event ra sớm.”** Không. Consumer có thể đọc event trước DB commit hoặc thấy event dù DB rollback.

**“DB-first bảo đảm event không mất.”** Không. Kafka commit sau DB có thể thất bại.

**“Có exception thì commit thứ nhất được rollback.”** Không. Commit đã hoàn tất không bị đảo ngược chỉ vì commit sau đó lỗi.

**“REQUIRES_NEW tạo 2PC.”** Không.

**“Cùng một bean gọi inner @Transactional vẫn mở transaction khác.”** Không được giả định trong Spring proxy mode mặc định.

**“Kafka EOS bảo đảm database side effect exactly-once.”** Không. Kafka EOS có ranh giới Kafka output + consumed offsets; DB cần idempotency/inbox.

**“Outbox khiến Kafka không có duplicate.”** Không. Outbox đảm bảo durable intent; relay và consumer vẫn cần deduplication.

## 20. Checklist triển khai

**Transaction manager và code**

- [ ] DB và Kafka transaction managers có tên rõ ràng.
- [ ] ProducerFactory đúng trả transactionCapable()=true.
- [ ] KafkaTemplate dùng đúng ProducerFactory.
- [ ] Đã xác định strategy DB-first hoặc Kafka-first.
- [ ] Inner Kafka method được gọi qua Spring proxy.
- [ ] Không có self-invocation, async thread handoff hoặc transaction container ngoài ý muốn.
- [ ] Không nhầm nested methods với Propagation.NESTED.

**Failure handling**

- [ ] Có runbook khi DB commit rồi Kafka commit fail.
- [ ] Có runbook khi Kafka commit rồi DB commit fail.
- [ ] Có cách xác định outcome không rõ sau timeout.
- [ ] Không nuốt exception làm outer transaction commit ngoài ý muốn.
- [ ] Có operationId/eventId cố định qua retries.
- [ ] Có outbox hoặc reconciliation khi không được phép mất event.
- [ ] Consumer có idempotency/inbox cho duplicate.

**Verification và observability**

- [ ] Đã kiểm thử bằng DB và Kafka thật.
- [ ] Đã chứng minh commit order bằng transaction events, không chỉ send calls.
- [ ] Đã test đúng failure window giữa hai commits.
- [ ] Đã test self-invocation và lựa chọn manager.
- [ ] Có metrics DB commit, Kafka commit/abort và producer fencing.
- [ ] Có cảnh báo outbox backlog/inconsistency.
- [ ] Đã xem riêng @KafkaListener transactional container nếu ứng dụng dùng listener.

## 21. Kết luận

**Nested @Transactional cho thứ tự commit** là cách điều khiển **hai local transaction boundaries**, không phải một giao dịch phân tán. Với Spring Kafka, DB transaction làm primary và KafkaTemplate transaction synchronization thường tạo **DB-first**. Để làm **Kafka-first**, có thể đặt outer DB @Transactional gọi qua Spring proxy tới một inner Kafka @Transactional, để Kafka commit khi inner method kết thúc rồi DB mới commit.

Dù chọn thứ tự nào, vẫn có **khoảng lỗi giữa hai commits**. DB-first có thể để lại database state đã commit nhưng event Kafka thiếu; Kafka-first có thể tạo event đã committed trong khi database chưa commit hoặc rollback. Vì vậy, phải chọn dựa trên business invariant, đo commit outcome thực tế và thiết kế idempotency, reconciliation hoặc transactional outbox nếu dữ liệu không được phép mất hay sai lệch.

