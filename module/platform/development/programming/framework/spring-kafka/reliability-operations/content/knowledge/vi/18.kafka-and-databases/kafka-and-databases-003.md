# Kafka-first commit order

Trong một ứng dụng Spring Kafka vừa thao tác **Apache Kafka** vừa ghi **database**, thứ tự commit giữa hai tài nguyên quyết định điều gì sẽ xảy ra khi một bên thành công còn bên kia thất bại. **Kafka-first commit order** nghĩa là **Kafka transaction được commit trước database transaction**. Cách này khác với mô hình thường gặp là database commit trước rồi Kafka commit.

Đây là bài toán độ tin cậy, không chỉ là thứ tự gọi phương thức. Hai transaction manager khác nhau không tự tạo ra một distributed transaction nguyên tử. Dù ứng dụng commit Kafka rồi mới commit database, vẫn luôn có một khoảng thời gian mà trạng thái hai hệ thống chưa đồng nhất; nếu lần commit thứ hai thất bại, lần commit đầu tiên **không tự được rollback**.

Bài học tập trung vào bối cảnh Spring Kafka, Spring transaction management và database giao dịch như PostgreSQL/MySQL. Cần phân biệt **producer-initiated transaction** (service nhận một command và chủ động phát Kafka event) với **consumer/container-initiated transaction** (listener container quản lý Kafka transaction và consumer offsets). Hai ngữ cảnh có ranh giới và cách cấu hình khác nhau.

## 1. Vì sao commit order quan trọng?

Giả sử service tạo đơn hàng:

1. Lưu Order vào database.
2. Publish OrderCreated lên Kafka.
3. Hoàn tất request.

Dữ liệu nghiệp vụ mong muốn:

    Database:
      orders[id=O-123, status=CREATED]

    Kafka:
      orders.events -> OrderCreated(orderId=O-123)

Nếu chỉ một trong hai thao tác được commit, có thể xuất hiện trạng thái không nhất quán:

- Kafka có OrderCreated nhưng database chưa có Order.
- Database đã có Order nhưng Kafka chưa có OrderCreated.

Hệ thống phải quyết định tình huống nào có thể chấp nhận tạm thời, cách phát hiện, thời gian được phép lệch nhau và cơ chế khôi phục sau lỗi.

Thứ tự commit không loại bỏ cửa sổ lỗi, mà chỉ **đổi cửa sổ lỗi**:

| Thứ tự | Commit 1 | Commit 2 | Nếu commit 2 thất bại |
|---|---|---|---|
| DB-first | Database | Kafka | Database đã đổi; Kafka event có thể chưa được publish |
| Kafka-first | Kafka | Database | Kafka event đã publish; database có thể rollback |

Không có một thứ tự nào bảo đảm atomicity xuyên hai resource manager nếu chỉ phối hợp bằng những Spring transaction manager độc lập.

## 2. Transaction nào đang được nói tới?

Một Kafka producer transaction cho phép ứng dụng gom nhiều Kafka writes và commit/abort chúng cùng nhau. Khi giao dịch Kafka commit, dữ liệu trở thành committed đối với downstream consumer cấu hình isolation.level=read_committed.

Một database transaction gom các thao tác SQL như INSERT/UPDATE/DELETE và commit/rollback chúng trên database.

Hai transaction này có phạm vi khác nhau:

    KafkaTransactionManager:
      begin -> KafkaTemplate.send(...) -> commit Kafka

    DataSourceTransactionManager / JpaTransactionManager:
      begin -> repository.save(...) -> commit database

Nếu cùng một business operation gọi cả hai, việc có hai chữ "transaction" không đồng nghĩa hai hệ thống dùng chung một atomic commit protocol.

Ví dụ này **không** đồng nghĩa với XA/two-phase commit:

    TransactionManager A (Kafka)  -----> Broker
    TransactionManager B (JPA)    -----> Database

Khi transaction của Kafka đã commit, một lỗi DB xảy ra sau đó không thể làm transaction Kafka trước đó quay ngược lại thành aborted.

## 3. Kafka-first diễn ra như thế nào?

Với Kafka-first, luồng dự kiến là:

    Receive CreateOrder command
               |
               v
    Begin database transaction
               |
               v
    Insert order row (chưa commit)
               |
               v
       Begin Kafka transaction
               |
               v
       Send OrderCreated event
               |
               v
       COMMIT Kafka transaction
               |
               v
       COMMIT database transaction
               |
               v
          Return success

Ở thời điểm Kafka commit nhưng database chưa commit, downstream có thể đọc được OrderCreated trước khi câu lệnh INSERT trở nên visible với connection DB khác.

Nếu database commit thành công ngay sau đó, trạng thái cuối cùng nhất quán. Nếu database commit thất bại, OrderCreated đã committed không tự biến mất.

Đây là điểm mấu chốt của Kafka-first: **Kafka là hệ thống hoàn tất commit sớm hơn, database là hệ thống có thể thất bại sau**.

## 4. Cửa sổ lỗi của Kafka-first

Giả sử transaction database chưa commit, nhưng transaction Kafka đã commit. Có thể xảy ra các tình huống:

| Thời điểm lỗi | Kafka | Database | Hệ quả |
|---|---|---|---|
| Trước Kafka send | Chưa commit | Chưa commit | Có thể rollback cả hai |
| Kafka send lỗi trước commit | Kafka TX abort/fail | DB TX có thể rollback | Không nên báo thành công |
| Kafka commit thành công, DB đang chờ | Event đã committed | Order chưa committed | Downstream đọc event quá sớm |
| DB commit thất bại sau Kafka commit | Event đã committed | Không có thay đổi DB như mong đợi | **Orphan event / inconsistency** |
| DB commit thành công, response mất | Event đã committed | Order đã committed | Client retry có thể tạo duplicate command |
| Kafka commit kết quả không chắc chắn | Chưa xác nhận chắc chắn | DB quyết định theo exception/flow | Cần reconciliation, không đoán theo timeout |

Một lỗi phổ biến là nhìn thấy KafkaTemplate.send() trả về future thành công rồi gọi đó là Kafka committed. Thành công của send chưa nhất thiết là transaction commit. Với producer transactional, chỉ khi transaction commit thành công thì downstream read_committed mới coi output là đã committed.

Một lỗi khác là nghĩ DB rollback sẽ kéo theo rollback Kafka khi Kafka đã commit. Điều đó không đúng với hai transaction riêng biệt.

## 5. DB-first và Kafka-first có gì khác nhau?

Trong ứng dụng Spring Kafka dùng transaction synchronization, **DB-first** thường là hướng mặc định khi một outer @Transactional database method gọi KafkaTemplate tham gia transaction được đồng bộ với database transaction: database commit trước, sau đó Kafka commit. Chi tiết phụ thuộc cách cấu hình transaction manager và phiên bản Spring.

Nếu muốn **Kafka-first**, không nên chỉ đổi thứ tự các dòng:

~~~java
repository.save(order);
kafkaTemplate.send("orders.events", event);
~~~

Trong một database transaction, repository.save() chưa đồng nghĩa DB commit. Tương tự, send() chưa đồng nghĩa Kafka commit. Thứ tự **method call** và thứ tự **transaction commit** là hai việc khác nhau.

Ví dụ đối chiếu:

    DB-first:
      save() -> send()
      commit database -> commit Kafka

    Kafka-first:
      save() -> send() trong transaction riêng
      commit Kafka -> commit database

Với Kafka-first, phải tổ chức ranh giới giao dịch sao cho **inner Kafka transaction kết thúc** trước khi outer database transaction kết thúc.

## 6. Mô hình nested @Transactional cho Kafka-first

Một kỹ thuật thường được Spring Kafka mô tả là dùng **hai phương thức @Transactional riêng**, trong đó:

- Phương thức ngoài mở database transaction.
- Phương thức trong mở Kafka transaction.
- Phương thức trong trả về sau khi Kafka transaction đã commit.
- Phương thức ngoài kết thúc sau, do đó database commit sau Kafka.

Sơ đồ:

    Outer method: @Transactional("dbTransactionManager")
      |
      +-- DB save/update
      |
      +-- Inner bean method: @Transactional("kafkaTransactionManager")
      |        |
      |        +-- KafkaTemplate.send(...)
      |        |
      |        +-- Kafka COMMIT khi inner method kết thúc
      |
      +-- DB COMMIT khi outer method kết thúc

Đây là **hai transaction local phối hợp theo thứ tự**, không phải một transaction phân tán. Cần chuẩn bị cho trường hợp Kafka inner commit thành công nhưng outer DB commit thất bại.

## 7. Ví dụ code với hai Spring bean

Giả sử ứng dụng nhận một command tạo đơn hàng ngoài Kafka, chẳng hạn REST request. Ví dụ dưới đây dùng bean riêng để Spring AOP transaction proxy thực sự intercept lời gọi inner method.

### 7.1. Service chỉ chịu trách nhiệm publish trong Kafka transaction

~~~java
@Service
public class OrderKafkaPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderKafkaPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publish(OrderCreated event) {
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
        // Khi method trả về, KafkaTransactionManager sẽ commit.
    }
}
~~~

KafkaTemplate cần sử dụng transaction-capable ProducerFactory phù hợp với kafkaTransactionManager. Việc gọi send() trong method chưa nói lên kết quả cuối: nếu producer gửi lỗi hoặc commit lỗi, Kafka transaction có thể không commit thành công.

### 7.2. Service mở database transaction bên ngoài

~~~java
@Service
public class OrderCommandService {

    private final OrderRepository orderRepository;
    private final OrderKafkaPublisher publisher;

    public OrderCommandService(
            OrderRepository orderRepository,
            OrderKafkaPublisher publisher) {
        this.orderRepository = orderRepository;
        this.publisher = publisher;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void createOrder(CreateOrder command) {
        OrderEntity entity = new OrderEntity(
            command.orderId(),
            command.amount()
        );

        orderRepository.save(entity);

        OrderCreated event = new OrderCreated(
            command.eventId(),
            command.orderId(),
            command.amount()
        );

        // Được gọi qua bean khác: Kafka transaction commit trước.
        publisher.publish(event);

        // Khi createOrder() trả về, DB transaction mới commit.
    }
}
~~~

Giả định các class OrderEntity, CreateOrder và OrderCreated đã được định nghĩa trong ứng dụng; ví dụ chỉ trình bày cấu trúc transaction.

**Lưu ý trọng yếu:** lời gọi publisher.publish(event) không phải nested call trong cùng một Spring bean. Nếu đặt hai method trong cùng một class rồi gọi this.publish(), Spring proxy mặc định có thể không intercept được self-invocation; kết quả là @Transactional trên inner method có thể không được áp dụng.

### 7.3. Luồng thực thi thành công

    OrderCommandService.createOrder()
      DB TX begin
        INSERT order
        OrderKafkaPublisher.publish()
          Kafka TX begin
          Kafka send
          Kafka TX commit
        return from publisher.publish()
      DB TX commit
    return from createOrder()

Ở đây Kafka commit thực sự xảy ra trước database commit nếu Kafka transaction manager và Spring proxy hoạt động như thiết kế.

## 8. Cấu hình KafkaTransactionManager và DB transaction manager

Cấu hình ProducerFactory cần hỗ trợ transaction. Ví dụ Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: order-command-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        acks: all
        enable.idempotence: true
~~~

Với Spring Boot auto-configuration phù hợp, transaction-id-prefix có thể giúp tạo KafkaTransactionManager. Nếu ứng dụng định nghĩa các transaction manager tường minh, hãy bảo đảm bean name trùng với tên trong @Transactional.

Ví dụ Kafka manager:

~~~java
@Bean("kafkaTransactionManager")
KafkaTransactionManager<String, OrderCreated> kafkaTransactionManager(
        ProducerFactory<String, OrderCreated> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Ví dụ cho JDBC:

~~~java
@Bean("dbTransactionManager")
DataSourceTransactionManager dbTransactionManager(
        DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
~~~

Nếu hệ thống dùng JPA/Hibernate, thường cần JpaTransactionManager phù hợp với EntityManagerFactory thay cho DataSourceTransactionManager. Không đăng ký đồng thời nhiều manager không cần thiết rồi giả định repository sẽ tự chọn đúng; hãy cấu hình transaction manager và persistence stack một cách nhất quán.

Một số phiên bản Spring Boot/Spring Framework có cơ chế tên bean mặc định hoặc primary transaction manager khác nhau. Vì vậy việc chỉ rõ transactionManager = "..." trong các ví dụ giúp thể hiện ý định commit order.

## 9. Cạm bẫy: @Transactional chưa chắc đã áp dụng

Một số lỗi thường gặp làm Kafka-first không thật sự hoạt động:

- **Self-invocation:** cùng bean gọi inner method qua this, Spring proxy không tạo transaction như dự kiến.
- **Method không được proxy:** cấu hình proxy, visibility hoặc lifecycle không phù hợp.
- **Chọn nhầm manager:** annotation không chỉ rõ manager trong dự án có nhiều PlatformTransactionManager.
- **ProducerFactory không transactional:** KafkaTemplate không mở/nhập Kafka transaction theo cách mong muốn.
- **Template khác factory:** inner publisher dùng KafkaTemplate trỏ tới producer factory ngoài transaction.
- **Method trả future trước khi công việc Kafka hoàn tất:** ranh giới transaction và async work không phù hợp.
- **Exception bị catch và nuốt:** outer DB method tiếp tục commit dù inner transaction đã thất bại.
- **Transaction đã có sẵn từ lớp gọi:** propagation và transaction synchronization làm thứ tự phức tạp hơn dự kiến.

Có thể xác nhận bằng integration test quan sát trạng thái Kafka output và database commit khi cố ý tạo lỗi. Chỉ nhìn thứ tự log từ repository.save() và kafkaTemplate.send() không chứng minh commit order.

## 10. Nếu Kafka commit thành công nhưng DB commit thất bại

Đây là failure mode đặc trưng nhất của Kafka-first.

    DB TX: INSERT order O-123 (uncommitted)
             |
             v
    Kafka TX: publish OrderCreated(O-123)
             |
             v
    Kafka commit SUCCESS
             |
             v
    DB commit FAIL: deadlock / constraint / disconnect
             |
             v
    Kafka có event, DB không có order

Một downstream service có thể nhận event và gọi lại Order API ngay. Nó thấy 404 hoặc trạng thái chưa tồn tại.

Không thể sửa bằng một lệnh rollback Kafka transaction đã commit. Các lựa chọn cần được thiết kế trước:

1. **Compensation event:** publish OrderCreationFailed/OrderCancelled nếu nghiệp vụ cho phép bù trừ. Compensation là một thao tác mới, không xóa event cũ.
2. **Reconciliation:** hệ thống kiểm tra event và database định kỳ, phát hiện order chưa có row rồi khôi phục hoặc báo lỗi.
3. **Event-first architecture:** coi Kafka event là dữ liệu đầu vào chủ đạo; database là materialized projection có thể cập nhật sau.
4. **Outbox:** nếu database là nguồn sự thật, ghi event vào outbox trong cùng DB transaction và publish sau DB commit thường phù hợp hơn.
5. **Consumer tolerance:** downstream retry truy vấn DB khi event đi trước quá trình commit, nhưng phải có timeout và phân biệt “chưa commit” với “DB không bao giờ commit”.

Chọn chiến lược theo yêu cầu nghiệp vụ. Một downstream retry 404 vài giây có thể xử lý trường hợp DB commit chậm, nhưng không khắc phục được trường hợp DB đã rollback vĩnh viễn.

## 11. Nếu Kafka commit thất bại trước DB commit

Trong mô hình nested transactions trên, nếu inner Kafka transaction ném exception khi gửi/commit, exception có thể lan ra outer database method và làm DB rollback.

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void createOrder(CreateOrder command) {
    orderRepository.save(toEntity(command));
    publisher.publish(toEvent(command)); // Có thể ném exception.
}
~~~

Nếu publisher.publish() thất bại, outer method không hoàn tất bình thường; Spring DB transaction interceptor có thể rollback theo rollback rules đã cấu hình.

Cần nhớ:

- Với RuntimeException, mặc định Spring transaction thường rollback.
- Với checked exception, mặc định rollback rule có thể khác; dùng rollbackFor phù hợp nếu cần.
- Nếu code catch exception nhưng không rethrow hoặc không mark rollback-only, DB có thể commit dù Kafka không thành công.
- Với lỗi commit do timeout/network, client có thể không chắc broker đã commit hay chưa. Không nên kết luận chắc chắn event chưa tồn tại chỉ vì method ném timeout.

Một cấu hình rõ ràng có thể khai báo rollbackFor:

~~~java
@Transactional(
    transactionManager = "dbTransactionManager",
    rollbackFor = Exception.class
)
public void createOrder(CreateOrder command) throws Exception {
    orderRepository.save(toEntity(command));
    publisher.publish(toEvent(command));
}
~~~

Tuy nhiên, rollbackFor không giải quyết được Kafka đã commit nhưng database sau đó thất bại; nó chỉ điều khiển hành vi rollback của transaction hiện tại khi exception xảy ra trong phạm vi xử lý.

## 12. Lỗi không chắc chắn và idempotency

Distributed systems có một trạng thái quan trọng: **không biết chắc commit đã xảy ra hay chưa**.

Ví dụ Kafka commit thành công ở broker, nhưng response về client bị mất. Ứng dụng có thể nhận timeout hoặc exception. Nếu tự động retry toàn bộ command, nó có thể publish một event nữa với một Kafka transaction mới.

Vì vậy:

- Gắn một business eventId ổn định cho mỗi command.
- Không sinh eventId mới chỉ vì client retry request.
- Dùng request-id hoặc idempotency key để định danh nghiệp vụ.
- Consumer downstream phải idempotent theo eventId/commandId.
- Lưu audit/reconciliation về quyết định xử lý khi có trạng thái không chắc chắn.

Kafka producer idempotence xử lý retry ở mức producer protocol theo khả năng của Kafka client; nó không tự hiểu hai lần người dùng gửi CreateOrder là cùng một business operation.

Một endpoint có thể cần trả trạng thái “processing/unknown” và cho phép client tra cứu kết quả theo commandId, thay vì bảo đảm thất bại nghĩa là không có event được publish.

## 13. Downstream đọc event trước khi database commit

Kafka-first tạo ra một race condition ngay cả khi cả hai transaction cuối cùng đều thành công.

    Thread 1 — OrderCommandService
      10:00:00.000 DB insert uncommitted
      10:00:00.010 Kafka TX commit
      10:00:00.040 DB TX commit

    Thread 2 — OrderConsumer
      10:00:00.020 Đọc OrderCreated từ Kafka
      10:00:00.025 Query DB lấy Order
      10:00:00.026 Không thấy row (chưa commit)

Nếu downstream phụ thuộc vào record database đã tồn tại ngay khi event xuất hiện, Kafka-first có thể vi phạm giả định đó.

Các cách thiết kế:

- Đưa dữ liệu cần thiết ngay trong event để downstream không phải query DB nguồn.
- Chọn event mô tả **intent** hoặc trạng thái có thể eventual consistent, thay vì khẳng định DB transaction đã commit.
- Chấp nhận retry có giới hạn khi lookup chưa thấy row.
- Chỉ publish event sau DB commit bằng outbox nếu cần bảo đảm “event => state đã commit”.
- Dùng correlation ID để truy vết race condition thay vì xem 404 là lỗi dữ liệu vĩnh viễn ngay lập tức.

Không nên dùng sleep() trong publisher để đợi database commit; inner Kafka transaction đang ở bên trong outer DB transaction, nên delay đó chỉ làm cửa sổ lâu hơn.

## 14. Producer-initiated và consumer-initiated transactions khác nhau

Trong **producer-initiated** flow (REST request, job, service method):

    REST -> DB outer transaction
                |
                +-> Kafka inner transaction commit
                |
           DB outer commit

Mô hình nested method có thể tạo Kafka-first như ví dụ ở trên.

Trong **consumer-initiated** flow do Spring Kafka listener container quản lý Kafka transaction:

    Container Kafka TX begin
       |
       v
    @KafkaListener
       |
       +-> DB local transaction begin/commit
       |
       v
    Container Kafka TX commit (gồm offset Kafka input nếu cấu hình đúng)

Ở mô hình container-initiated, **Kafka transaction là lớp ngoài** do container mở trước khi gọi listener và commit sau khi listener xử lý xong. Nếu listener tự mở DB transaction bên trong, DB thường commit trước Kafka. Đó là **DB-first** ở cấp hai tài nguyên.

Do vậy, không thể chỉ thêm @Transactional("kafkaTransactionManager") trên một inner method rồi mặc định Kafka sẽ commit trước DB khi listener container đã có một Kafka transaction đang hoạt động. Inner call có thể tham gia resource transaction hiện tại; transaction Kafka ngoài vẫn chưa commit cho tới khi container hoàn tất.

Muốn cam kết commit order khác, cần thiết kế lại ranh giới transaction và kiểm thử; không nên giả định nested annotation có thể điều khiển commit của container transaction đang mở.

## 15. Offset Kafka làm tình huống phức tạp hơn

Nếu application tiêu thụ Kafka input, ghi database rồi publish Kafka output, có ba trạng thái cần xét:

1. Database transaction.
2. Kafka output transaction.
3. Consumer group offset của input.

Trong container Kafka transaction chuẩn, output và offset đầu vào có thể commit **nguyên tử cùng nhau**. Nếu cố commit Kafka transaction trước DB, offset input cũng có thể được commit trước khi database commit.

Ví dụ nguy hiểm:

    Input order-request@offset 90
       |
       v
    Kafka TX chứa output và input offset=91
       |
       v
    Commit Kafka SUCCESS
       |
       v
    Commit DB FAIL

Nếu Kafka transaction đã commit offset 91, consumer group có thể tiếp tục từ record kế tiếp mà không tự đọc lại offset 90, trong khi DB side effect chưa hoàn tất. Đây không còn đơn thuần là “event đi trước DB”; nó còn có thể làm **mất cơ hội xử lý lại input theo offset**.

Vì vậy, với consumer-initiated flow, cần ưu tiên kiểm soát ranh giới container transaction và idempotency/consistency với database. Không áp dụng recipe Kafka-first của producer-initiated service một cách máy móc cho listener.

## 16. So sánh các kiến trúc khi Kafka và DB phải nhất quán

| Kiến trúc | Commit order | Tính nguyên tử | Phù hợp |
|---|---|---|---|
| DB-first synchronization | DB rồi Kafka | Không nguyên tử xuyên hai resource | Chấp nhận reconciliation khi Kafka fail |
| Kafka-first nested TX | Kafka rồi DB | Không nguyên tử xuyên hai resource | Event-first, chấp nhận DB eventual consistency |
| Transactional outbox | DB state + outbox cùng DB transaction; publisher gửi Kafka sau | State và ý định publish nguyên tử trong DB | DB là source of truth, cần không mất event |
| Transactional inbox | Processed marker + DB state cùng DB transaction | DB side effect và dedup nguyên tử trong DB | Consumer nhận Kafka input, cần chống duplicate |
| Kafka-only transaction | Kafka outputs + input offsets commit cùng Kafka TX | Nguyên tử trong Kafka | Pure Kafka read-process-write |
| Saga/compensation | Nhiều bước độc lập, có event bù | Eventual consistency | Workflow đa dịch vụ, side effect ngoài Kafka |

Nếu database là nguồn sự thật và event mô tả một thay đổi đã commit, **transactional outbox** thường có tính phù hợp cao hơn việc cố sửa commit order.

Nếu Kafka event là log sự kiện chuẩn còn database là projection được xây dựng sau, Kafka-first có thể phù hợp về mặt mô hình, nhưng khi đó nên thiết kế DB như projection có khả năng replay và rebuild, không giả định DB commit phải đồng thời với event.

## 17. Transactional outbox là giải pháp gì?

Với outbox, một database transaction ghi cả trạng thái nghiệp vụ lẫn event cần publish:

    Begin DB transaction
       |
       +-> INSERT orders
       |
       +-> INSERT outbox_event(eventId, payload)
       |
    Commit DB transaction
       |
       v
    Outbox publisher đọc outbox_event
       |
       v
    KafkaTemplate.send(...)
       |
       v
    Đánh dấu outbox đã publish

Ưu điểm: nếu database commit, event cần publish đã được lưu bền vững trong outbox; nếu database rollback, cả Order và outbox row đều không có hiệu lực.

Nhược điểm: publisher có thể gửi event lên Kafka thành công rồi crash trước khi đánh dấu outbox đã publish. Event có thể được gửi lại, vì vậy downstream vẫn cần idempotency theo eventId.

Outbox không làm Kafka send đúng một lần ở mọi failure window; nó giải quyết **khả năng không mất ý định publish do commit lệch** giữa database và Kafka, sau đó dùng at-least-once delivery + deduplication.

## 18. Transactional inbox cho consumer ghi database

Với Kafka consumer cần cập nhật DB, một cách chống redelivery trùng là ghi dấu mốc eventId trong cùng DB transaction:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong transaction DB:

~~~text
BEGIN;

INSERT processed_events(consumer_name,event_id,...)
  nếu chưa tồn tại;

Nếu event đã tồn tại:
  không áp dụng lại side effect;
Nếu mới:
  UPDATE/INSERT business data;

COMMIT;
~~~

Khi Kafka record được giao lại do offset chưa commit, consumer tra marker đã tồn tại và không lặp cập nhật nghiệp vụ.

Cần bảo đảm câu lệnh dedup và thay đổi DB nằm **trong cùng transaction**, có unique constraint để xử lý concurrent attempt. Chỉ kiểm tra tồn tại rồi ghi ở hai transaction khác nhau có thể gặp race condition.

Inbox không loại bỏ nhu cầu commit offset Kafka; nó giúp business operation an toàn khi Kafka redelivery.

## 19. Dùng event-first khi nào?

Kafka-first dễ chấp nhận hơn khi **event được coi là sự thật chuẩn**, còn database là trạng thái suy ra từ event.

Ví dụ kiến trúc:

    Producer command
         |
         v
    Kafka committed event
         |
         v
    Projection consumer
         |
         v
    Database materialized view

Trong mô hình này, không cần một transaction Kafka-first lồng dưới một transaction DB để cùng tạo một sự kiện và một row. Thường đơn giản hơn là commit event vào Kafka trước, rồi một consumer độc lập đọc event và cập nhật DB projection.

Nếu projection consumer lỗi, Kafka event vẫn là nguồn để replay. Database có thể phục hồi từ log Kafka nếu retention và cơ chế snapshot/rebuild phù hợp.

Cách này có trade-off:

- Database có độ trễ eventual consistency.
- Command API cần mô hình trạng thái pending hoặc query không đồng bộ.
- Consumer projection cần idempotent và theo dõi lag.
- Schema evolution và event retention cần hỗ trợ rebuild lâu dài.
- Replay cần tránh side effect không phù hợp.

Event-first không đồng nghĩa với việc một API đã tạo Order có thể lập tức đọc thấy Order trong DB. Contract với client và downstream phải phản ánh điều đó.

## 20. Spring transaction synchronization và thứ tự commit

Trong Spring, KafkaTemplate với transactional ProducerFactory có thể tham gia một transaction đang hoạt động qua synchronization. Khi database transaction là outer transaction, các resource Kafka liên kết có thể được commit sau database theo hành vi synchronization thông dụng.

Điều này giúp giảm boilerplate cho một số đường xử lý, nhưng có những rủi ro:

- Database đã commit, Kafka commit sau đó có thể thất bại.
- Exception Kafka commit có thể được trả về caller sau khi DB đã commit; caller phải biết DB đã thay đổi.
- Ứng dụng phải kiểm tra version của Spring Kafka vì cách xử lý exception trong synchronized commit từng thay đổi.
- Transaction synchronization không biến Kafka và DB thành distributed atomic transaction.

Để chủ động Kafka-first, sử dụng inner method với KafkaTransactionManager và outer method với DB transaction manager là một kỹ thuật phổ biến. Nhưng lời gọi phải qua Spring proxy và dùng đúng resource manager.

Không nên dùng các mẫu chained transaction manager lịch sử như bằng chứng đã có atomic transaction xuyên Kafka và DB. Một chuỗi local transaction manager vẫn có partial commit failure; nhiều API chained từng bị deprecated và không phải lựa chọn ưu tiên cho thiết kế mới.

## 21. Chọn transaction propagation phù hợp

Spring @Transactional có propagation mặc định là REQUIRED. Với hai transaction manager khác nhau, cần hiểu propagation theo từng manager.

Trong ví dụ:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void outer() {
    repository.save(...);
    publisher.inner();
}

@Transactional(transactionManager = "kafkaTransactionManager")
public void inner() {
    kafkaTemplate.send(...);
}
~~~

Nếu outer tạo DB transaction và inner tạo Kafka transaction riêng, hai manager quản lý hai tài nguyên khác nhau. Inner Kafka commit khi method inner return, trong khi DB vẫn mở.

Nhưng nếu có Kafka transaction đang hoạt động trước khi gọi inner, propagation REQUIRED có thể tham gia transaction Kafka đã có. Khi đó inner return **không có nghĩa** transaction Kafka đã commit.

Có thể xem xét propagation REQUIRES_NEW trong những kiến trúc thực sự cần transaction độc lập, nhưng nó không nên được dùng như một bản sửa lỗi mù: transaction Kafka hiện tại, producer factory, resource binding, transaction synchronization và offsets của container đều có thể tương tác. Cần kiểm tra API và test commit order cụ thể.

Không dùng propagation NESTED và suy luận có savepoint chung giữa Kafka và DB. Kafka transaction không hỗ trợ một database savepoint xuyên hai hệ thống.

## 22. Các yếu tố producer cần cấu hình

Kafka-first phụ thuộc khả năng Kafka transaction commit bền vững trước khi DB commit.

Các cấu hình cần hiểu:

| Thuộc tính | Vai trò |
|---|---|
| transaction-id-prefix / transactional.id | Kích hoạt transactional producer, hỗ trợ coordinator và fencing |
| enable.idempotence | Tránh duplicate do một số retry ở producer protocol |
| acks=all | Yêu cầu xác nhận theo replica/ISR |
| delivery.timeout.ms | Giới hạn thời gian producer hoàn tất send |
| transaction.timeout.ms | Giới hạn thời gian transaction được phép mở |
| request.timeout.ms | Thời gian chờ phản hồi request |
| max.in.flight.requests.per.connection | Ảnh hưởng pipeline send; phải tương thích idempotence |
| retry settings | Cần kết hợp timeout, không thay thế business idempotency |

Nếu transaction timeout quá dài, Kafka output có thể bị giữ chưa visible cho read_committed downstream và chiếm tài nguyên. Nếu quá ngắn, các thao tác chậm có thể làm Kafka transaction abort trước khi logic kết thúc.

Mỗi instance đang hoạt động cần namespace transactional ID được quản lý an toàn. Dùng cùng một transactional.id cố định cho nhiều pod có thể gây producer fencing và khiến giao dịch liên tục thất bại.

## 23. Error handling theo giai đoạn commit

Để vận hành, cần phân biệt exception xảy ra ở giai đoạn nào:

### Giai đoạn A: trước Kafka commit

Thí dụ validation failed, DB insert failed trước publish hoặc Kafka send failed. Thông thường có thể rollback cả hai transaction đang mở, nhưng phải giữ exception lan lên outer interceptor.

### Giai đoạn B: Kafka commit bị lỗi hoặc không chắc chắn

Không tự kết luận broker chưa có event. Thu thập eventId và transaction/error metadata, đưa command vào luồng reconciliation hoặc kiểm tra trạng thái idempotent trước khi retry.

### Giai đoạn C: Kafka commit đã thành công, DB commit thất bại

Không thể rollback Kafka. Đây là tình huống cần compensation, event-first reconciliation hoặc chuyển sang outbox để thay đổi kiến trúc.

### Giai đoạn D: cả hai commit thành công nhưng response tới client mất

Client có thể retry. Dùng commandId/idempotency key và unique business constraint để tránh tạo Order/event mới ngoài dự kiến.

Một runbook cần trả lời: ai chịu trách nhiệm kiểm tra, khi nào retry, khi nào bù trừ và hệ thống nào có thẩm quyền đưa ra trạng thái cuối.

## 24. Kiểm thử Kafka-first commit order

Một unit test gọi mock KafkaTemplate và mock Repository không đủ để chứng minh thứ tự commit. Commit nằm ở transaction interceptor và resource manager, không phải chỉ ở hai lời gọi method.

Dùng integration test với database và Kafka broker thật ở môi trường test (ví dụ Testcontainers), đồng thời xác nhận dữ liệu committed.

### 24.1. Happy path

1. Gọi outer service bằng một command có eventId cố định.
2. Xác nhận Kafka event xuất hiện với consumer read_committed.
3. Xác nhận database row đã commit.
4. Ghi nhận transaction completion để kiểm tra thứ tự.
5. Xác nhận client nhận success chỉ sau database commit.

### 24.2. Kafka commit thất bại

1. Mô phỏng lỗi producer/coordinator hoặc broker trước Kafka commit.
2. Xác nhận inner Kafka method không hoàn tất bình thường.
3. Xác nhận outer DB transaction rollback theo rollback rule.
4. Xác nhận không có database row committed.
5. Kiểm tra trường hợp Kafka commit outcome không chắc chắn bằng eventId.

### 24.3. Database commit thất bại sau Kafka commit

Đây là test cốt lõi cho Kafka-first:

1. Bắt đầu outer DB transaction, lưu row nhưng chưa commit.
2. Gọi inner Kafka transactional publisher và để Kafka commit thành công.
3. Cố ý làm database commit thất bại sau khi inner method trả về.
4. Xác nhận downstream read_committed thấy Kafka event.
5. Xác nhận database không có row committed tương ứng.
6. Xác nhận hệ thống có cảnh báo/reconciliation, không báo lỗi rồi im lặng.

Trong test phải tạo lỗi ở đúng **thời điểm database commit**, không chỉ ném exception ở giữa outer method nếu cách tạo lỗi vô tình khiến inner Kafka transaction chưa commit.

### 24.4. Consumer đọc trước database commit

1. Giữ outer DB transaction mở sau khi Kafka inner transaction đã commit.
2. Cho downstream đọc event bằng read_committed consumer.
3. Kiểm tra truy vấn DB từ connection khác chưa thấy row.
4. Sau đó cho outer DB commit thành công.
5. Xác nhận downstream retry/handling eventual consistency phù hợp.

### 24.5. Duplicate command sau response timeout

1. Gửi commandId X và để cả hai commit thành công.
2. Giả lập mất response.
3. Gửi lại cùng commandId X.
4. Xác nhận không tạo duplicate side effect/event ngoài hợp đồng.
5. Xác nhận eventId ổn định giữa các attempt.

### 24.6. Container-initiated transaction

1. Tạo transactional @KafkaListener và DB transaction bên trong.
2. Quan sát thứ tự DB commit trước container Kafka commit theo cấu hình thực tế.
3. Xác nhận inner Kafka method không tự đóng container transaction nếu chỉ tham gia transaction hiện tại.
4. Làm Kafka commit fail và kiểm tra idempotency DB khi redelivery.
5. Không áp dụng kết luận của producer-initiated nested method sang listener khi chưa xác thực.

## 25. Quan sát commit order trong production

Các tín hiệu cần theo dõi:

**Kafka transaction**

- Số transaction commit/abort và tỷ lệ lỗi.
- Transaction duration, timeout, producer fencing.
- Delivery timeout và lỗi KafkaTemplate.
- EventId/correlationId ở output committed.

**Database**

- Transaction commit/rollback count.
- Deadlock, constraint violation và connection error.
- Thời gian từ INSERT tới DB commit.
- Số giao dịch commit thất bại sau khi Kafka publish.

**Consistency**

- Số Kafka event chưa có DB row tương ứng sau một ngưỡng thời gian.
- Số DB row không có Kafka event nếu ứng dụng còn dùng các path DB-first.
- Số compensation/reconciliation attempt.
- Số duplicate command bị idempotency layer từ chối.
- Tuổi của sự cố chưa reconcile lâu nhất.

Đối với commit order, có thể ghi các lifecycle marker an toàn như:

    commandId=cmd-123 stage=db_tx_open
    commandId=cmd-123 stage=kafka_tx_commit_success
    commandId=cmd-123 stage=db_tx_commit_success

Nếu database commit fail:

    commandId=cmd-123 stage=kafka_tx_commit_success
    commandId=cmd-123 stage=db_tx_commit_failed

Không log bí mật Kafka credential, nội dung thanh toán hoặc payload nhạy cảm. Log stage có thể thất lạc, vì vậy reconciliation nên dùng trạng thái bền vững và định danh nghiệp vụ, không chỉ dựa vào log.

## 26. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Gọi KafkaTemplate.send trước repository.save sẽ commit Kafka trước | Method order khác commit order |
| Có @Transactional là DB và Kafka nguyên tử | Hai transaction manager không tự dùng XA |
| Kafka-first tốt hơn DB-first trong mọi trường hợp | Nó chuyển rủi ro sang orphan Kafka event |
| Kafka commit rồi DB rollback sẽ rollback Kafka | Kafka transaction đã commit không thể abort ngược |
| KafkaTemplate.send thành công là Kafka transaction đã commit | Transaction commit là ranh giới riêng |
| @Transactional inner luôn tạo Kafka transaction mới | Có thể tham gia transaction Kafka đang có |
| Nested annotations trong cùng bean luôn hiệu lực | Self-invocation có thể bỏ qua Spring AOP proxy |
| read_committed bảo đảm DB đã commit | Nó chỉ xét Kafka transaction, không xét database |
| Producer idempotence ngăn duplicate business command | Cần commandId/eventId và dedup |
| Kafka-first giải quyết mọi lỗi khi container consume Kafka | Input offsets và container transaction tạo thêm rủi ro |
| Retry sau Kafka timeout luôn an toàn | Commit outcome có thể không chắc chắn |
| Thay đổi commit order thay thế outbox | Outbox giải quyết failure window bằng mô hình khác |

## 27. Khi nào nên cân nhắc Kafka-first?

Kafka-first có thể được cân nhắc khi:

- Kafka event là nguồn dữ liệu ưu tiên và database chỉ là projection có thể tái tạo.
- Downstream chấp nhận eventual consistency và không giả định DB row đã commit khi thấy event.
- Có cơ chế reconciliation hoặc compensation rõ ràng.
- Mọi command có ID ổn định và duplicate được xử lý idempotent.
- Đội vận hành đã kiểm thử lỗi DB commit sau khi Kafka commit.
- Quy trình nghiệp vụ coi event là intent hoặc một bước có thể bù trừ, không phải cam kết DB final state.

Không nên chọn Kafka-first chỉ vì muốn “Kafka nhanh hơn database”. Với service có DB là nguồn sự thật, event biểu thị thay đổi DB đã có hiệu lực và consumer cần truy vấn DB ngay, transactional outbox thường là lựa chọn dễ đảm bảo độ tin cậy hơn.

## 28. Nguyên tắc ghi nhớ

- **Kafka-first commit order = Kafka commit trước, database commit sau.**
- Tạo thứ tự commit bằng transaction boundaries, không phải thứ tự gọi save/send.
- Với producer-initiated flow, outer DB @Transactional và inner Kafka @Transactional trên **hai Spring bean riêng** là một mô hình được dùng.
- Inner Kafka method phải dùng KafkaTransactionManager và KafkaTemplate/ProducerFactory đúng.
- Nếu Kafka inner commit lỗi, outer DB có thể rollback theo rollback rules.
- Nếu Kafka commit thành công rồi DB commit lỗi, Kafka event vẫn còn: đây là failure window không thể loại bỏ bằng nested transactions.
- Downstream read_committed chỉ bảo vệ khỏi Kafka transaction abort, không chờ DB commit.
- Container-initiated Kafka transaction có ranh giới khác producer-initiated transaction; không sao chép cấu hình một cách máy móc.
- Nếu input Kafka offset được commit trước DB side effect, có nguy cơ không tự redelivery record khi DB fail.
- Dùng eventId/commandId ổn định, idempotency và cơ chế reconciliation.
- Nếu DB là source of truth, cân nhắc transactional outbox/inbox.
- Kiểm thử Kafka success + DB commit fail và các trường hợp commit outcome không chắc chắn.

Kafka-first không phải “bảo đảm exactly once giữa Kafka và database”. Nó là một lựa chọn **thứ tự commit** với lợi ích và rủi ro riêng. Thiết kế đáng tin cậy phải gọi tên rõ cửa sổ lỗi Kafka-committed/DB-not-committed, quyết định ai chịu trách nhiệm khôi phục và bảo đảm không có nghiệp vụ bị nhân đôi hay mất dấu khi request, listener hoặc transaction bị retry.
