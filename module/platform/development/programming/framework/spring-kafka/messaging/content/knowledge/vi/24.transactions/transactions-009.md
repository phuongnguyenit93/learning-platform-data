# Transaction synchronization với DataSource

Một nghiệp vụ có thể vừa ghi dữ liệu vào database vừa phát event lên Kafka. Ví dụ khi tạo đơn hàng, ứng dụng lưu order vào bảng orders và gửi event OrderCreated để billing, inventory hoặc notification service tiếp tục xử lý.

Nếu hai thao tác chạy độc lập, có thể xảy ra trạng thái lệch: database đã commit nhưng event chưa được gửi, hoặc event đã xuất hiện trong Kafka trong khi database rollback. Spring Kafka hỗ trợ transaction synchronization để phối hợp Kafka transaction với transaction của một transaction manager khác, chẳng hạn DataSourceTransactionManager.

Transaction synchronization giúp Spring gọi commit hoặc rollback cho resource thứ hai theo vòng đời transaction chính. Tuy vậy, database và Kafka vẫn là hai hệ thống có transaction riêng; cơ chế synchronization không phải distributed two-phase commit và không tạo bảo đảm nguyên tử tuyệt đối giữa hai hệ thống. Cần hiểu thứ tự commit và cửa sổ lỗi còn lại để chọn kiến trúc phù hợp.

Bài học thuộc chương **Transactions** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Bài toán ghi database và gửi Kafka

Giả sử Order Service xử lý yêu cầu tạo đơn:

1. Ghi đơn hàng vào database.
2. Gửi event OrderCreated lên topic order-events.
3. Các service khác nhận event để xử lý công việc tiếp theo.

Nếu không phối hợp transaction, hai thao tác có thể rơi vào các trạng thái:

| Database | Kafka | Hệ quả |
| --- | --- | --- |
| Commit | Gửi thành công | Trạng thái mong muốn. |
| Rollback | Không gửi | Không tạo đơn và không phát event. |
| Commit | Gửi thất bại | Có đơn trong DB nhưng service khác không nhận event. |
| Rollback | Gửi thành công | Consumer thấy event cho một đơn không tồn tại. |

Vấn đề là transaction của JDBC/JPA và transaction của Kafka do hai resource manager khác nhau quản lý. Một transaction database không tự động rollback Kafka producer, và Kafka transaction cũng không tự động rollback database.

## 2. Transaction synchronization là gì?

Spring Framework có cơ chế transaction synchronization để đăng ký callback theo vòng đời transaction hiện tại. Resource thứ hai có thể tham gia đồng bộ bằng cách đăng ký các thao tác cần thực hiện khi transaction chính commit hoặc rollback.

Trong Spring Kafka, KafkaTemplate có thể đồng bộ Kafka transaction với transaction đang hoạt động của một transaction manager khác khi ProducerFactory được cấu hình transactional. Ví dụ phổ biến là database transaction làm transaction chính, còn Kafka transaction được đồng bộ theo nó.

Mô hình khái quát:

~~~mermaid
flowchart TD
    A[Service method bắt đầu] --> B[DataSource transaction mở]
    B --> C[Thực hiện SQL]
    C --> D[KafkaTemplate gửi event]
    D --> E[Kafka transaction được đồng bộ]
    E --> F{Database transaction}
    F -->|Commit| G[Database commit]
    G --> H[Kafka transaction commit]
    F -->|Rollback| I[Database rollback]
    I --> J[Kafka transaction rollback]
~~~

Trong cấu hình thông dụng, database transaction commit trước, Kafka transaction commit sau. Nếu database rollback, Kafka transaction được rollback theo synchronization. Nếu database đã commit nhưng Kafka commit thất bại, database không thể tự rollback lại; ứng dụng phải có chiến lược phục hồi cho khoảng lỗi đó.

## 3. Phân biệt transaction manager và transaction synchronization

Hai transaction manager quản lý hai resource khác nhau:

| Thành phần | Resource được quản lý | Vai trò |
| --- | --- | --- |
| DataSourceTransactionManager | JDBC Connection | Commit/rollback thao tác SQL. |
| JdbcTransactionManager | JDBC Connection | Biến thể của DataSourceTransactionManager có hỗ trợ exception translation. |
| JpaTransactionManager | JPA EntityManager | Quản lý transaction JPA và có thể phối hợp với JDBC trên cùng DataSource theo cấu hình. |
| KafkaTransactionManager | Kafka Producer | Mở, commit và rollback Kafka transaction. |
| Transaction synchronization | Callback của Spring transaction | Phối hợp resource thứ hai theo vòng đời transaction đang hoạt động. |

Transaction manager xác định transaction chính được mở bởi annotation hoặc lời gọi quản lý transaction. Transaction synchronization đăng ký hành vi của resource thứ hai để phối hợp commit/rollback.

Không nên nhầm synchronization với một transaction manager phân tán duy nhất. Spring điều phối vòng đời nhưng không cung cấp XA atomic commit giữa Kafka và database chỉ bằng việc cả hai cùng được gọi trong một method.

## 4. Cấu hình Kafka producer có transaction

Để KafkaTemplate sử dụng Kafka transaction, ProducerFactory cần có transaction ID prefix. Spring Kafka dùng prefix để tạo transactional producer với ID riêng cho từng producer instance.

Với Spring Boot, có thể cấu hình:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: order-service-instance-unique-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
~~~

`transaction-id-prefix` bật khả năng tạo transactional producer thông qua ProducerFactory. Prefix phải duy nhất giữa các instance ứng dụng đang chạy đồng thời trong cùng cluster để tránh transactional ID xung đột/fencing.

Trong môi trường Kubernetes, có thể đưa pod identity hoặc một instance identity duy nhất vào prefix. Không hard-code cùng một prefix tĩnh cho mọi replica. ProducerFactory tạo phần suffix cho các producer được quản lý bên trong factory; ứng dụng cần bảo đảm prefix gốc không trùng giữa các instance.

Nếu tự tạo ProducerFactory bằng Java, có thể đặt prefix:

~~~java
@Bean
public ProducerFactory<String, OrderCreated> orderProducerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> properties =
        kafkaProperties.buildProducerProperties();

    DefaultKafkaProducerFactory<String, OrderCreated> factory =
        new DefaultKafkaProducerFactory<>(properties);

    factory.setTransactionIdPrefix("order-service-instance-a-tx-");
    return factory;
}
~~~

Ví dụ Java chỉ minh họa cấu hình. Trong ứng dụng thực tế, giá trị prefix cần được inject từ cấu hình triển khai và phải khác nhau giữa các instance.

## 5. Cấu hình DataSource transaction manager

Nếu ứng dụng dùng JDBC, DataSourceTransactionManager quản lý transaction trên JDBC Connection:

~~~java
@Bean
public PlatformTransactionManager dbTransactionManager(
        DataSource dataSource) {

    return new DataSourceTransactionManager(dataSource);
}
~~~

Nếu ứng dụng dùng JPA, thường sử dụng JpaTransactionManager cho EntityManager:

~~~java
@Bean
public PlatformTransactionManager dbTransactionManager(
        EntityManagerFactory entityManagerFactory) {

    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Không khai báo hai transaction manager cùng quản lý một transaction boundary nếu chưa hiểu cách chúng tương tác. Chọn transaction manager đúng với persistence technology của service và đặt tên bean rõ ràng khi application context có nhiều manager.

Khi dùng Spring Boot, auto-configuration có thể đã tạo transaction manager cho DataSource hoặc JPA. Hãy kiểm tra bean hiện có trước khi tự khai báo một bean mới; tránh tạo hai manager cạnh tranh cho cùng persistence context.

## 6. Gửi event trong DataSource transaction

Khi database transaction là transaction chính, method service được đánh dấu @Transactional với đúng bean transaction manager. KafkaTemplate dùng ProducerFactory transactional để đồng bộ lần gửi vào transaction hiện tại.

Ví dụ JDBC:

~~~java
@Service
@RequiredArgsConstructor
public class OrderApplicationService {

    private final JdbcTemplate jdbcTemplate;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Transactional(transactionManager = "dbTransactionManager")
    public void createOrder(Order order) {
        jdbcTemplate.update(
            "insert into orders(id, status) values (?, ?)",
            order.id(),
            "CREATED"
        );

        OrderCreated event = new OrderCreated(
            order.id(),
            order.customerId(),
            order.total()
        );

        kafkaTemplate.send(
            "order-events",
            order.id(),
            event
        );
    }
}
~~~

Điều quan trọng:

- Method chạy trong database transaction do dbTransactionManager quản lý.
- SQL và các thay đổi database thuộc transaction đó.
- KafkaTemplate dùng transactional producer và đồng bộ Kafka transaction với transaction hiện tại.
- Nếu database transaction rollback, Kafka transaction được rollback theo synchronization.
- Khi database commit thành công, Kafka transaction được commit theo thứ tự synchronization mặc định.

Không được bỏ transaction ID prefix rồi kỳ vọng một Kafka send thông thường tự động rollback theo database. ProducerFactory phải hỗ trợ transaction và KafkaTemplate phải tham gia đúng transaction synchronization.

## 7. Điều gì xảy ra khi method thành công?

Giả sử SQL và Kafka send đều thành công:

~~~text
1. Spring mở database transaction.
2. Service ghi order vào database.
3. KafkaTemplate gửi OrderCreated trong Kafka transaction được đồng bộ.
4. Method kết thúc bình thường.
5. Database transaction commit.
6. Kafka transaction commit.
7. Consumer dùng read_committed có thể đọc event đã commit.
~~~

Consumer cấu hình isolation level:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

`read_committed` khiến consumer chỉ đọc các record thuộc Kafka transaction đã commit và bỏ qua record thuộc transaction bị abort. Nó không làm consumer kiểm tra database; nó chỉ áp dụng visibility rule của Kafka transaction.

Nếu consumer dùng read_uncommitted, consumer có thể nhìn thấy record từ transaction chưa commit hoặc transaction sau đó bị abort, tùy vị trí đọc và trạng thái transaction. Với event cần tuân thủ Kafka transaction visibility, cấu hình read_committed cho consumer tương ứng.

## 8. Điều gì xảy ra khi database rollback?

Giả sử SQL thành công nhưng bước nghiệp vụ sau đó ném exception:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void createOrder(Order order) {
    jdbcTemplate.update(
        "insert into orders(id, status) values (?, ?)",
        order.id(),
        "CREATED"
    );

    kafkaTemplate.send(
        "order-events",
        order.id(),
        toEvent(order)
    );

    throw new IllegalStateException("Business operation failed");
}
~~~

Spring rollback database transaction. Kafka transaction đã được đồng bộ cũng được rollback. Consumer dùng read_committed không nhìn thấy event thuộc transaction Kafka đã abort.

Đây là lợi ích chính của synchronization: tránh event được commit trong Kafka khi transaction database chính rollback, với điều kiện Kafka send đã tham gia transaction synchronization đúng cách.

Nếu KafkaTemplate gửi ngoài transaction, dùng một ProducerFactory không transactional hoặc chuyển send sang thread khác không mang transaction context, kết quả có thể khác. Cần bảo đảm lệnh send nằm trong đúng thread và transaction boundary.

## 9. Thứ tự commit và cửa sổ lỗi còn lại

Trong cấu hình thông dụng khi database là transaction chính, Spring commit database trước rồi mới commit Kafka transaction.

Điều này tạo một cửa sổ lỗi:

~~~text
Database commit thành công
        |
        v
Ứng dụng/cluster gặp sự cố hoặc Kafka commit thất bại
        |
        v
Database có order nhưng event chưa được publish thành công
~~~

Khi database đã commit, Spring không thể rollback lại thay đổi đã bền vững chỉ vì Kafka commit sau đó thất bại. Vì vậy, transaction synchronization không đảm bảo atomic commit tuyệt đối giữa hai hệ thống.

Nếu đổi thứ tự để Kafka commit trước database, cửa sổ lỗi sẽ đảo lại: Kafka event có thể được commit nhưng database commit thất bại. Thay đổi thứ tự không loại bỏ vấn đề, chỉ chuyển loại inconsistency có thể xảy ra.

Đừng chọn thứ tự commit chỉ dựa trên cảm giác an toàn. Hãy xác định hệ thống nào là nguồn sự thật, mức độ chấp nhận inconsistency và cách phục hồi.

## 10. Vì sao transaction synchronization không phải XA?

XA/two-phase commit yêu cầu các resource manager tham gia một giao thức commit phân tán có coordinator và khả năng prepare/commit hoặc rollback theo protocol tương ứng.

Transaction synchronization của Spring chủ yếu dùng callback vòng đời transaction. Nó có thể yêu cầu resource thứ hai commit hoặc rollback sau transaction chính, nhưng không có một bước prepare nguyên tử chung cho cả JDBC database và Kafka.

| Khả năng | Transaction synchronization | XA/2PC |
| --- | --- | --- |
| Một transaction manager chính | Có | Có coordinator |
| Callback commit/rollback cho resource thứ hai | Có | Theo protocol prepare/commit |
| Atomic commit giữa mọi resource | Không bảo đảm | Có thể đạt trong phạm vi resource XA hỗ trợ |
| Khả năng xảy ra cửa sổ lỗi giữa hai commit | Có | Được xử lý bởi protocol, nhưng có chi phí và rủi ro vận hành riêng |
| Phù hợp Kafka + JDBC thông thường | Thường dùng để phối hợp | Không mặc định có XA chung cho Kafka producer và JDBC |

Không nên gọi synchronization là distributed transaction. Cách diễn đạt chính xác là hai local transaction được phối hợp theo thứ tự commit/rollback của Spring.

## 11. Vai trò của KafkaTransactionManager

`KafkaTransactionManager` quản lý Kafka producer transaction và có thể được dùng làm transaction manager cho một method chỉ cần transaction Kafka:

~~~java
@Bean
public KafkaTransactionManager<String, OrderCreated>
        kafkaTransactionManager(
            ProducerFactory<String, OrderCreated> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Một method dùng Kafka transaction manager:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishOrderEvent(OrderCreated event) {
    kafkaTemplate.send(
        "order-events",
        event.orderId(),
        event
    );
}
~~~

Trong trường hợp này, transaction boundary do KafkaTransactionManager quản lý. Nó phù hợp khi cần publish nhiều record Kafka trong một transaction, hoặc cần listener container dùng Kafka transaction cho consume-process-produce.

Nếu method còn ghi database, cần xác định rõ transaction manager nào là chính và cách manager còn lại được đồng bộ. Chỉ đặt hai annotation hoặc inject hai manager không tự tạo một transaction nguyên tử.

## 12. Chọn transaction manager cho method

Khi application context có nhiều PlatformTransactionManager, nên chỉ định rõ manager trong @Transactional:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void updateDatabaseAndPublishEvent() {
    // Database transaction là transaction chính.
}
~~~

Hoặc:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishSeveralKafkaRecords() {
    // Kafka transaction là transaction chính.
}
~~~

Không nên để method phụ thuộc vào transaction manager mặc định nếu ứng dụng có cả database và Kafka manager mà tên/primary selection không rõ ràng.

Nếu dùng meta-annotation hoặc transaction manager qualifier, hãy đặt convention thống nhất trong service. Review cần nhận ra transaction boundary ngay tại method entry.

## 13. Chú ý thread-bound transaction context

Spring transaction thông thường gắn với thread hiện tại. Transaction synchronization cũng dựa trên resource và synchronization context của thread đó.

Các trường hợp có thể làm mất sự phối hợp:

- Gửi Kafka trong một thread do executor tạo ra.
- Dùng `@Async` cho phần publish.
- Gọi KafkaTemplate từ callback chạy trên thread khác.
- Tách công việc sang scheduler hoặc reactive pipeline không được cấu hình transaction tương ứng.
- Gọi method nội bộ qua self-invocation khiến proxy @Transactional không được áp dụng như mong đợi.

Ví dụ không nên kỳ vọng đồng bộ transaction:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void createOrder(Order order) {
    jdbcTemplate.update(/* SQL */);

    executor.execute(() ->
        kafkaTemplate.send("order-events", order.id(), toEvent(order))
    );
}
~~~

Lệnh gửi được chạy ở thread khác, ngoài transaction context của method. Database rollback không tự động rollback send đó.

Nếu cần xử lý bất đồng bộ, hãy dùng outbox hoặc một cơ chế truyền dữ liệu bền vững giữa transaction database và publisher. Không dựa vào việc truyền ThreadLocal transaction context bằng cách tự sao chép state.

## 14. Propagation và transaction lồng nhau

Transaction propagation như REQUIRED, REQUIRES_NEW hoặc NESTED ảnh hưởng database transaction boundary. Khi có Kafka transaction được đồng bộ, cần xem nó gắn với transaction nào và thời điểm synchronization callback chạy.

Ví dụ REQUIRES_NEW tạo transaction database độc lập. Nếu Kafka send nằm trong method này, việc publish có thể được đồng bộ với transaction mới thay vì transaction bên ngoài, tùy cách proxy và manager được gọi.

Không nên dùng REQUIRES_NEW như cách khắc phục lỗi commit giữa DB và Kafka. Nó có thể làm ranh giới nhất quán phức tạp hơn. Hãy viết test cho các transaction boundary lồng nhau nếu nghiệp vụ thật sự cần chúng.

Self-invocation cũng cần chú ý: gọi một method @Transactional khác trong cùng instance thường không đi qua Spring proxy mặc định, nên propagation được khai báo ở method kia có thể không có hiệu lực.

## 15. Gửi nhiều event trong cùng database transaction

Một database transaction có thể phát nhiều event Kafka. Khi Kafka transaction được đồng bộ đúng, các record gửi trong cùng Kafka transaction sẽ được commit hoặc abort như một nhóm Kafka.

Ví dụ:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void completeOrder(Order order) {
    updateOrderStatus(order.id(), "COMPLETED");

    kafkaTemplate.send(
        "order-events",
        order.id(),
        new OrderCompleted(order.id())
    );

    kafkaTemplate.send(
        "billing-commands",
        order.id(),
        new CreateInvoice(order.id(), order.total())
    );

    kafkaTemplate.send(
        "inventory-commands",
        order.id(),
        new ReleaseReservation(order.id())
    );
}
~~~

Nếu database rollback, Kafka transaction đồng bộ cũng rollback. Nếu database commit rồi Kafka commit thất bại, database đã hoàn tất nhưng các event có thể không được công bố. Cần theo dõi commit result và có quy trình reconciliation hoặc outbox.

Kafka transaction bảo đảm các record trong transaction Kafka được commit/abort theo nhóm đối với consumer isolation read_committed. Nó không làm ba service downstream xử lý đồng thời thành một distributed transaction.

## 16. Transaction synchronization với JPA

Với JPA, có thể dùng JpaTransactionManager làm transaction chính và gửi Kafka event trong cùng method:

~~~java
@Service
@RequiredArgsConstructor
public class JpaOrderService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Transactional(transactionManager = "jpaTransactionManager")
    public void create(Order order) {
        orderRepository.save(order);

        kafkaTemplate.send(
            "order-events",
            order.getId(),
            new OrderCreated(order.getId(), order.getCustomerId())
        );
    }
}
~~~

JPA có thể trì hoãn SQL đến flush/commit. Nếu cần phát hiện constraint violation trước khi publish hoặc muốn chắc chắn SQL được gửi trước một bước nghiệp vụ, có thể flush trong transaction; nhưng flush không đồng nghĩa database đã commit.

Transaction synchronization vẫn phụ thuộc cấu hình transactional producer và manager đang hoạt động. Hãy kiểm thử với database thật/embedded phù hợp để xác nhận rollback và commit behavior, không chỉ mock repository.

## 17. Transaction synchronization và transactional outbox

Nếu nghiệp vụ yêu cầu không mất event khi database đã commit, transactional outbox thường là giải pháp phù hợp hơn.

Trong cùng một database transaction:

1. Ghi order vào bảng orders.
2. Ghi một outbox row chứa event vào bảng outbox.
3. Commit cả hai cùng nhau.

Một publisher riêng đọc outbox và gửi event sang Kafka. Khi gửi thành công, publisher đánh dấu row đã publish hoặc dùng CDC để chuyển đổi log database thành Kafka event.

~~~mermaid
flowchart TD
    A[Order service] --> B[Database transaction]
    B --> C[Update orders]
    B --> D[Insert outbox event]
    C --> E[DB commit]
    D --> E
    E --> F[Outbox relay hoặc CDC]
    F --> G[Kafka topic]
    G --> H[Consumer services]
~~~

Outbox đảm bảo thay đổi nghiệp vụ và ý định phát event được lưu nguyên tử trong cùng database transaction. Publisher có thể retry khi Kafka tạm thời không khả dụng mà không mất event đã commit trong outbox.

Outbox thường tạo semantics at-least-once: relay có thể gửi event rồi crash trước khi đánh dấu đã publish, khiến event được gửi lại. Consumer vẫn cần idempotency theo event ID.

| Tiêu chí | Transaction synchronization | Transactional outbox |
| --- | --- | --- |
| Ghi DB và gửi Kafka | Cùng method, hai local transaction được phối hợp | Ghi DB và outbox row trong một DB transaction |
| Cửa sổ DB commit/Kafka commit | Có | Publisher retry từ outbox |
| Độ phức tạp | Thấp hơn ban đầu | Cần relay/CDC và quản lý outbox |
| Khả năng phục hồi khi Kafka unavailable | Phụ thuộc commit/reconciliation | Event vẫn nằm bền vững trong outbox |
| Duplicate | Có thể xảy ra ở failure/retry | Có thể xảy ra khi relay retry |
| Use case | Phối hợp đơn giản, chấp nhận remedial action | Cần độ tin cậy cao cho phát event sau DB commit |

Outbox không loại bỏ mọi lỗi hoặc duplicate; nó làm cho ý định phát event bền vững và có thể retry độc lập với transaction Kafka.

## 18. Inbox/idempotency ở consumer

Khi consumer nhận event, xử lý database và commit Kafka offset cũng có thể gặp cửa sổ lỗi: database commit thành công nhưng offset chưa commit, nên event được đọc lại.

Có thể dùng inbox pattern:

- Mỗi event có eventId duy nhất.
- Consumer ghi eventId vào bảng processed_events trong cùng transaction với cập nhật nghiệp vụ.
- Nếu eventId đã tồn tại, bỏ qua tác dụng phụ và xác nhận record theo chính sách.
- Nếu transaction rollback, cả thay đổi nghiệp vụ và processed marker cùng rollback.

Inbox giúp xử lý duplicate từ Kafka một cách an toàn. Nó bổ sung cho outbox ở phía producer và idempotent handler ở phía consumer.

## 19. ChainedKafkaTransactionManager và cách tiếp cận hiện đại

`ChainedKafkaTransactionManager` từng được dùng để xếp chuỗi nhiều transaction manager, ví dụ database và Kafka. API này đã deprecated trong Spring Kafka từ phiên bản 2.7; không nên chọn làm thiết kế mới.

Với ứng dụng hiện đại, hãy ưu tiên transaction synchronization được Spring Kafka hỗ trợ, chọn transaction manager chính rõ ràng và hiểu thứ tự commit. Nếu yêu cầu nhất quán mạnh giữa database và Kafka, đánh giá transactional outbox thay vì cố tạo một distributed transaction bằng cách ghép hai manager.

Khi bảo trì ứng dụng cũ dùng chained manager, cần đọc tài liệu đúng phiên bản và lập kế hoạch chuyển đổi. Không thay đổi thứ tự manager hoặc transaction semantics trong production mà không có test failure/recovery tương ứng.

## 20. Kiểm thử transaction synchronization

Kiểm thử cần xác nhận cả database state và Kafka visibility. Dùng Testcontainers cho Kafka và database giúp kiểm tra tương tác thật giữa hai resource manager.

Các kịch bản:

1. Method thành công: row database được commit và event xuất hiện với consumer read_committed.
2. Ném exception trước commit: database rollback và event không xuất hiện với read_committed consumer.
3. Kafka broker tạm thời không khả dụng: quan sát lỗi commit và xác nhận database/Kafka state theo thứ tự commit thực tế.
4. Dùng producer factory không transactional: xác nhận không có giả định rollback Kafka theo DB.
5. Gửi event từ thread khác: xác nhận transaction synchronization không tự truyền sang thread đó.
6. Nhiều event trong một transaction: xác nhận các record Kafka cùng transaction được commit/abort như nhóm.
7. Chạy nhiều application instance: xác nhận transaction ID prefix không trùng và không fencing lẫn nhau.
8. Outbox relay retry: xác nhận event cuối cùng được publish và consumer xử lý duplicate an toàn.

Ví dụ kiểm tra thành công có thể dùng listener test hoặc consumer riêng với `isolation.level=read_committed`. Dùng Awaitility/latch với timeout để chờ record; tránh sleep cố định.

Đối với failure window sau database commit nhưng trước Kafka commit, việc tạo lỗi commit một cách xác định có thể cần broker fault injection hoặc test harness riêng. Không nên viết test chỉ giả lập exception trong service rồi kết luận đã kiểm tra được lỗi commit giữa hai resource.

## 21. Quan sát transaction trong production

Nên theo dõi:

- Database transaction duration và rollback count.
- Kafka transaction commit/abort count.
- Lỗi khi begin/commit/abort producer transaction.
- Producer fencing và transactional ID.
- Thời gian gửi event và số send failure.
- Chênh lệch giữa database state và event downstream nếu có reconciliation.
- Outbox backlog và tuổi của outbox row nếu dùng outbox.
- Consumer lag và duplicate processing rate.

Log cần correlation ID/event ID để nối database operation với Kafka record. Không log dữ liệu nhạy cảm trong payload. Khi có lỗi commit, cần phân biệt database commit failure với Kafka commit failure vì trạng thái bền vững có thể khác nhau.

Với outbox, cảnh báo khi outbox row tồn tại quá lâu hoặc relay không publish được. Đây là tín hiệu quan trọng cho thấy event chưa rời database dù transaction nghiệp vụ đã commit.

## 22. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| @Transactional trên DB tự rollback mọi Kafka send. | Chỉ khi Kafka producer transaction được cấu hình và send tham gia synchronization đúng cách. |
| Transaction synchronization là XA/2PC. | Đây là phối hợp callback theo vòng đời transaction chính, không phải atomic distributed commit. |
| Database rollback thì event đã gửi luôn bị xóa. | Chỉ đúng khi send nằm trong Kafka transaction được đồng bộ; send ngoài transaction có thể đã tồn tại. |
| Hai transaction manager cùng được inject nghĩa là một transaction. | Chúng vẫn quản lý hai resource; phải xác định transaction manager chính và synchronization. |
| DB và Kafka luôn commit cùng một thời điểm. | Commit diễn ra tuần tự; mặc định DB thường commit trước Kafka trong mô hình DB-primary. |
| Đổi thứ tự commit loại bỏ inconsistency. | Nó chỉ chuyển cửa sổ lỗi từ một hướng sang hướng khác. |
| Kafka read_committed kiểm tra database. | Nó chỉ lọc Kafka transaction chưa commit/đã abort. |
| Gửi Kafka từ @Async vẫn tham gia DB transaction. | Transaction context thông thường gắn với thread, không tự truyền sang thread khác. |
| ChainedKafkaTransactionManager là lựa chọn mới. | API đã deprecated; ưu tiên synchronization hoặc outbox theo yêu cầu. |
| Transactional outbox bảo đảm không có duplicate. | Relay có thể gửi lại; consumer vẫn cần idempotency. |

## 23. Checklist thiết kế

Trước khi dùng transaction synchronization với DataSource, hãy xác nhận:

1. Transaction manager chính là DataSource/JPA manager phù hợp.
2. ProducerFactory có transaction ID prefix.
3. Prefix duy nhất giữa các instance đang chạy đồng thời.
4. KafkaTemplate sử dụng đúng ProducerFactory transactional.
5. Kafka send chạy trong cùng thread và transaction boundary.
6. @Transactional chỉ rõ manager khi application có nhiều manager.
7. Đã hiểu thứ tự DB commit rồi Kafka commit trong cấu hình đang dùng.
8. Có cách xử lý nếu Kafka commit thất bại sau DB commit.
9. Consumer cần read_committed khi chỉ muốn đọc Kafka transaction đã commit.
10. Không giả định synchronization là XA hoặc atomic commit.
11. Không gửi event qua thread khác nếu kỳ vọng cùng transaction.
12. Đã đánh giá transactional outbox cho nghiệp vụ cần bảo đảm phát event.
13. Consumer có idempotency/inbox để xử lý redelivery.
14. Có integration test commit, rollback, Kafka unavailable và nhiều instance.

Transaction synchronization với DataSource giúp phối hợp Kafka transaction cùng database transaction trong một luồng Spring. Nó có thể rollback Kafka khi transaction database rollback và commit Kafka sau khi database commit theo thứ tự mặc định. Tuy nhiên, hai resource vẫn commit riêng và còn cửa sổ lỗi giữa các lần commit. Hãy chọn synchronization khi mức độ phối hợp này phù hợp, và dùng transactional outbox khi cần lưu bền vững ý định phát event cùng thay đổi database.



