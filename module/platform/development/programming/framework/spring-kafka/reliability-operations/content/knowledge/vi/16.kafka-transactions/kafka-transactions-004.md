# KafkaTemplate trong transaction

## 1. Vì sao KafkaTemplate cần hỗ trợ transaction?

Trong hệ thống event-driven, một thao tác nghiệp vụ có thể phát nhiều Kafka record liên quan với nhau. Nếu producer gửi từng record độc lập, sự cố ở lần gửi sau có thể khiến downstream nhìn thấy một phần thay đổi mà không thấy phần còn lại.

Ví dụ Order Service xác nhận một đơn hàng và cần gửi hai record:

- **OrderConfirmed** vào topic orders.events.
- **ReserveInventory** vào topic inventory.commands.

Nếu KafkaTemplate dùng một **Kafka transaction**, các ghi Kafka tham gia transaction được kết thúc bằng một quyết định **commit** hoặc **abort**. Consumer đặt **isolation.level=read_committed** chỉ đọc những record transactional đã commit, không giao những record của transaction abort.

~~~text
Order Service
     |
     v
Transactional KafkaTemplate
     |
     +---- send OrderConfirmed -----> orders.events
     |
     +---- send ReserveInventory ---> inventory.commands
     |
     v
 Kafka transaction
     |
     +---- COMMIT -> read_committed consumer đọc output đã commit
     |
     +---- ABORT  -> read_committed consumer bỏ qua output đã abort
~~~

Kafka transaction bảo vệ **những thao tác Kafka nằm trong transaction**, và trong luồng consume-transform-produce có thể bao gồm commit offset consumer group. Nó **không** tự tạo atomic commit giữa Kafka và PostgreSQL, MySQL, HTTP API hay hệ thống thanh toán.

Trong Spring Kafka, **KafkaTemplate** là API gửi record, còn **KafkaTransactionManager**, **ProducerFactory** và **listener container** xác định cách transaction được bắt đầu, đồng bộ, commit và abort.

## 2. Các thành phần liên quan

| Thành phần | Vai trò |
|---|---|
| KafkaTemplate | API gửi record, nhận CompletableFuture, cung cấp executeInTransaction |
| KafkaProducer | Producer client dùng trong transaction ở tầng Kafka |
| DefaultKafkaProducerFactory | Tạo/caching transactional producer và gán transactional.id |
| KafkaTransactionManager | Tích hợp Kafka transaction với Spring TransactionManager |
| @Transactional | Khai báo transaction boundary khi Spring AOP chọn đúng manager |
| ConcurrentKafkaListenerContainerFactory | Tạo listener container, có thể cấu hình transaction cho consumer-driven flow |
| KafkaConsumer | Poll record và quản lý offset của consumer group |
| Transaction coordinator | Thành phần broker quản lý commit/abort của Kafka transaction |

Một KafkaTemplate có transaction-capable ProducerFactory có thể được dùng theo ba mô hình:

1. **Producer-initiated:** service chủ động mở transaction qua @Transactional, gửi nhiều record rồi commit.
2. **Local KafkaTemplate transaction:** method **executeInTransaction** bắt đầu transaction cục bộ bao quanh callback.
3. **Consumer-initiated:** listener container bắt đầu transaction, KafkaTemplate gửi output và container gửi offset đầu vào vào cùng transaction.

Đặc biệt phải phân biệt transaction ở cấp template với transaction do listener container quản lý. Chúng không tự động đồng nhất chỉ vì cùng dùng một KafkaTemplate bean.

## 3. Transaction ở Kafka broker hoạt động ra sao?

Transactional producer có định danh **transactional.id**. Kafka cấp producer ID và epoch để theo dõi phiên producer và ngăn producer cũ tiếp tục khi xuất hiện producer mới cùng transactional ID.

Một luồng transaction điển hình:

~~~text
initTransactions()
       |
       v
beginTransaction()
       |
       +--> send record A tới topic 1
       |
       +--> send record B tới topic 2
       |
       v
commitTransaction() hoặc abortTransaction()
       |
       v
Transaction coordinator quyết định trạng thái
       |
       v
Broker lưu transaction markers phù hợp
       |
       v
read_committed consumer chỉ đọc dữ liệu committed
~~~

Các record transactional có thể đã tồn tại trên log vật lý trước commit. Vì vậy, **broker ack cho một send không tương đương với commit của toàn bộ transaction**.

Kafka transaction có thể gồm nhiều topic và partition. Tuy nhiên, hai consumer downstream khác nhau vẫn poll và xử lý theo lịch riêng. Commit Kafka không tạo ra một transaction phân tán giữa mọi ứng dụng downstream.

### 3.1. Idempotence khác transaction

**enable.idempotence=true** giúp producer tránh duplicate do retry của chính producer trong phạm vi hỗ trợ. Nó không tạo ranh giới commit/abort cho nhiều output record.

**Kafka transaction** sử dụng idempotent producer và mở rộng bảo đảm cho một nhóm ghi Kafka, đồng thời có thể phối hợp offset input với output trong consume-transform-produce.

| Cơ chế | Mục đích |
|---|---|
| Idempotent producer | Hạn chế producer retry tạo record trùng |
| Transactional producer | Atomically commit/abort một nhóm thao tác Kafka |
| Consumer read_committed | Không giao những record transactional bị abort |
| Idempotent business consumer | Tránh side effect lặp ở DB/HTTP khi record bị giao lại |
| Transactional outbox | Phối hợp lưu DB và ý định publish Kafka một cách bền vững |

## 4. Chuẩn bị broker, ProducerFactory và quyền

Trước khi dùng transaction, cần:

- Kafka broker và transaction coordinator hoạt động bình thường.
- Transaction state log có replication/min ISR phù hợp môi trường.
- ProducerFactory có cấu hình **transaction ID prefix**.
- Producer có serializer đúng cho key/value, **acks=all** và cấu hình reliability phù hợp.
- Principal có quyền WRITE trên các topic, quyền tương ứng trên transactional ID và các quyền cluster bổ sung khi phiên bản/authorizer yêu cầu.
- Consumer downstream dùng **read_committed** nếu phải ẩn aborted output.
- Ranh giới transaction trong code được chọn rõ ràng.

Một môi trường development chỉ có một broker có thể cần cấu hình transaction state log replication theo số broker thực tế. Không hạ durability của internal transaction topic trong production để giải quyết nhanh lỗi khởi tạo.

## 5. Cấu hình transactional KafkaTemplate trong Spring Boot

Ví dụ application.yml:

~~~yaml
spring:
  application:
    name: order-service
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      transaction-id-prefix: "order-service-pod-a-tx-"
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
~~~

**transaction-id-prefix** khiến ProducerFactory tạo transactional producer. Trong Spring Boot, khi các điều kiện auto-configuration phù hợp, một **KafkaTransactionManager** cũng được cấu hình.

Trong ví dụ trên, tên pod được ghi cố định để minh họa. Ứng dụng production nhiều replica phải lấy **instance identity riêng cho từng pod/process** từ cơ chế cấu hình hoặc environment variable, thay vì dùng chung chuỗi order-service-pod-a-tx-.

Không nên gán cùng transactional ID cho các producer khác nhau đang chạy đồng thời. Kafka sẽ fence producer cũ khi producer mới khởi tạo cùng transactional ID.

### 5.1. Producer transactional có thể cần active transaction

Nếu KafkaTemplate dùng transaction-capable ProducerFactory và template không cho phép gửi non-transactional, gọi send bên ngoài transaction có thể ném lỗi kiểu “No transaction is in process”.

Điều này khác với KafkaTemplate thông thường. Cách sử dụng đúng là:

- Mở Kafka transaction bằng **@Transactional** với KafkaTransactionManager.
- Dùng **KafkaTemplate.executeInTransaction** cho một transaction cục bộ.
- Gửi từ listener đã có Kafka transaction do container tạo.
- Chỉ khi nghiệp vụ cho phép gửi ngoài transaction mới cân nhắc API **setAllowNonTransactional(true)** của KafkaTemplate.

Không bật allowNonTransactional đơn thuần để che lỗi cấu hình, vì khi đó một số output có thể được gửi ngoài transaction trong khi các output khác được gửi transactional.

## 6. Cách 1: @Transactional với KafkaTransactionManager

Khi một method nghiệp vụ cần gửi nhiều record trong một transaction, có thể dùng Spring transaction abstraction:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(
            String orderId,
            OrderConfirmed confirmed,
            InventoryReservationRequested reserve) {

        var first = kafkaTemplate.send(
            "orders.events",
            orderId,
            confirmed
        );

        var second = kafkaTemplate.send(
            "inventory.commands",
            orderId,
            reserve
        );

        CompletableFuture.allOf(first, second).join();
    }
}
~~~

Với KafkaTransactionManager phù hợp, luồng tổng quát là:

1. Spring transaction interceptor mở Kafka transaction trước khi vào method.
2. KafkaTemplate dùng transactional producer gắn với transaction hiện hành.
3. Các lời gọi send phát record vào transaction.
4. Method hoàn tất bình thường thì manager yêu cầu commit.
5. Method ném exception khiến Spring áp dụng rollback rules thì manager abort.

**CompletableFuture.allOf(...).join()** giúp lỗi gửi bất đồng bộ xuất hiện trong transaction boundary thay vì chỉ được ghi log sau khi method kết thúc.

Ví dụ dựa trên Spring Kafka phiên bản có KafkaTemplate.send trả về CompletableFuture. Với version cũ, kiểu future và API callback có thể khác; cần dùng API của dependency thực tế.

### 6.1. Chọn đúng transaction manager

Khi ứng dụng vừa có database transaction manager vừa có KafkaTransactionManager, **@Transactional** không có qualifier có thể chọn manager không phải Kafka.

Ví dụ:

~~~java
@Transactional("kafkaTransactionManager")
public void publishKafkaEvents() {
    // Kafka transaction
}
~~~

Nếu manager bean được đặt tên khác, annotation phải tham chiếu tên thực tế. Không mặc định rằng @Transactional sử dụng Kafka chỉ vì code bên trong gọi KafkaTemplate.

### 6.2. Spring proxy và self-invocation

Spring @Transactional thường dựa trên AOP proxy. Nếu một method trong cùng class gọi trực tiếp **this.publishKafkaEvents()**, lời gọi có thể không đi qua proxy để mở transaction.

Khi đó template có thể hoạt động như đang ngoài transaction và ném lỗi. Đặt boundary ở method được gọi qua Spring bean proxy hoặc dùng programmatic transaction khi cần.

## 7. Cách 2: KafkaTemplate.executeInTransaction

KafkaTemplate cung cấp **executeInTransaction** để bao một callback trong một Kafka transaction cục bộ.

~~~java
public void publishPair(
        String orderId,
        OrderConfirmed confirmed,
        InventoryReservationRequested reserve) {

    kafkaTemplate.executeInTransaction(operations -> {
        operations.send(
            "orders.events",
            orderId,
            confirmed
        ).join();

        operations.send(
            "inventory.commands",
            orderId,
            reserve
        ).join();

        return null;
    });
}
~~~

Hình dung:

~~~text
executeInTransaction(callback)
           |
           v
     begin transaction
           |
           v
     callback thực thi
           |
      +----+----+
      |         |
   success   exception
      |         |
      v         v
    commit     abort
      |         |
      v         v
    return   propagate lỗi
~~~

Cách này phù hợp với một method gửi Kafka nhỏ, muốn ranh giới transaction cụ thể mà không phụ thuộc AOP annotation ở service ngoài cùng.

### 7.1. Lưu ý về transaction đang tồn tại

**executeInTransaction tạo một Kafka transaction cục bộ riêng, không tham gia transaction đang mở ở bên ngoài.**

Ví dụ listener container đã mở Kafka transaction để phối hợp output và consumer offsets, nhưng code trong listener lại gọi executeInTransaction. Output của callback có thể commit ở một transaction khác, không nằm cùng transaction của offset đầu vào. Điều đó phá vỡ giả định consume-transform-produce atomically.

Vì thế, trong listener transactional, thông thường **gọi kafkaTemplate.send trực tiếp**, để template dùng producer của transaction container đang hoạt động.

### 7.2. So sánh hai cách

| Nhu cầu | @Transactional với KafkaTransactionManager | executeInTransaction |
|---|---|---|
| Transaction boundary ở service method | Phù hợp | Có thể dùng nhưng không cần annotation |
| Cần AOP/proxy | Có trong mô hình thông thường | Không |
| Callback tạo transaction cục bộ | Không | Có |
| Có thể phối hợp nhiều method trong Spring transaction | Có nếu tham gia cùng manager | Callback là ranh giới riêng |
| Đang có Kafka transaction của listener | Dùng theo thiết kế container | Không dùng để thay transaction container |
| Đảm bảo DB+Kafka atomic | Không | Không |

## 8. Send future không phải transaction commit

KafkaTemplate.send thường trả về **CompletableFuture<SendResult<K,V>>**. Future báo kết quả của một send, không phải kết quả commit toàn transaction.

~~~java
var future = kafkaTemplate.send(
    "orders.events",
    orderId,
    event
);

future.whenComplete((result, failure) -> {
    if (failure != null) {
        log.error("Kafka send failed orderId={}", orderId, failure);
    }
    else {
        log.info(
            "Broker acknowledged topic={} partition={} offset={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition(),
            result.getRecordMetadata().offset()
        );
    }
});
~~~

Nếu callback báo send thành công, record có thể đã được broker acknowledge nhưng transaction vẫn chưa commit. Nếu transaction abort sau đó, read_committed consumer không nhận record đó.

Ngược lại, nếu callback báo lỗi nhưng code chỉ log rồi để method hoàn tất bình thường, ứng dụng không chủ động truyền failure vào rollback rules. Producer commit có thể báo lỗi tiếp, nhưng không nên trông đợi hệ thống tự suy luận chính sách nghiệp vụ.

### 8.1. Chờ future trong transaction khi cần

~~~java
var a = kafkaTemplate.send("orders.events", orderId, confirmed);
var b = kafkaTemplate.send("inventory.commands", orderId, reserve);

CompletableFuture.allOf(a, b).join();
~~~

Với cách này, một send failure làm **join()** ném CompletionException ngay trong method transactional. Hãy đặt delivery timeout, request timeout và giới hạn blocking time phù hợp để tránh giữ transaction quá lâu.

Không dùng callback bất đồng bộ chạy sau khi method @Transactional kết thúc làm chỗ quyết định rollback một transaction đã commit hoặc abort.

## 9. Commit, abort và các tình huống thất bại

| Tình huống | Ý nghĩa |
|---|---|
| Tất cả send ack, transaction commit | Các record Kafka trong transaction được committed |
| Một send lỗi, transaction abort | Các output của transaction không được read_committed consumer giao |
| JVM chết trước commit | Transaction chưa commit được broker xử lý theo timeout/recovery |
| Transaction coordinator không khả dụng | Commit có thể lỗi hoặc outcome chưa rõ |
| Producer bị fence | Producer cũ không thể tiếp tục giao dịch hợp lệ |
| Transaction timeout | Coordinator có thể abort transaction quá thời hạn |
| Consumer read_uncommitted | Có thể đọc record transactional bị abort |

Phải phân biệt:

1. **send invoked**: ứng dụng đã gọi KafkaTemplate.send.
2. **send acknowledged**: broker trả kết quả ghi record.
3. **transaction committed**: coordinator xác nhận commit cho transaction.

Một log “send succeeded” không thể thay thế bằng chứng transaction commit. Khi commit outcome không rõ do timeout hoặc crash, hãy dùng idempotency và đối soát thay vì suy luận mọi send đã thành công.

## 10. Transactional ID và producer fencing

**transactional.id** định danh một producer logic. Broker dùng producer ID/epoch để fence producer cũ nếu producer mới khởi tạo cùng transactional ID.

~~~text
Producer A: transactional.id = orders-tx-0
          |
          v
Producer B khởi tạo cùng transactional.id
          |
          v
Broker tăng epoch, producer A bị fence
          |
          v
Producer A không tiếp tục transaction hợp lệ
~~~

Fencing bảo vệ tính đúng đắn nhưng có thể trở thành lỗi vận hành nếu các replica không có transactional ID riêng.

### 10.1. Prefix nên được chọn thế nào?

- Có namespace ứng dụng và môi trường.
- Phân biệt instance/process đang hoạt động đồng thời.
- Không tạo ID ngẫu nhiên trên mỗi event.
- Không dùng event ID hoặc request ID làm transactional ID.
- Giữ tương thích với ACL prefix và hạn chế quyền rộng.
- Theo dõi ID collision khi scale pod hoặc restart.

Ví dụ cho từng instance:

~~~text
order-service-prod-pod-a-tx-0
order-service-prod-pod-a-tx-1
order-service-prod-pod-b-tx-0
order-service-prod-pod-b-tx-1
~~~

Nếu producer nhận **ProducerFencedException**, đừng chỉ retry cùng producer đã bị fence. Cần để framework xử lý lifecycle producer mới và điều tra xung đột ID hoặc tình trạng restart/rollout.

## 11. Gửi tới nhiều topic/partition trong một transaction

Kafka transaction có thể bao phủ nhiều topic/partition:

~~~java
@Transactional("kafkaTransactionManager")
public void publishWorkflow(
        String orderId,
        OrderConfirmed confirmed,
        InventoryReserved reserved,
        OrderAudit audit) {

    var first = kafkaTemplate.send(
        "orders.events", orderId, confirmed
    );

    var second = kafkaTemplate.send(
        "inventory.events", orderId, reserved
    );

    var third = kafkaTemplate.send(
        "orders.audit", orderId, audit
    );

    CompletableFuture.allOf(first, second, third).join();
}
~~~

Đoạn mã giả định KafkaTemplate value type và serializer hỗ trợ cả ba event class. Với Avro/Protobuf/JSON Schema, cần bảo đảm serializer, schema subject và type mapping phù hợp.

**Kafka commit atomically không có nghĩa mọi downstream consumer xử lý cùng lúc.** Một consumer đọc orders.events và consumer khác đọc inventory.events có thể hoàn tất ở thời điểm khác nhau. Nếu cần phối hợp nghiệp vụ, dùng correlation ID và state machine hoặc orchestration thích hợp.

## 12. Consume-transform-produce với KafkaTemplate

Một use case quan trọng là đọc record đầu vào, biến đổi và publish output Kafka, đồng thời commit input offsets cùng transaction.

~~~text
orders.in
    |
    v
Transactional listener container
    |
    +-- begin Kafka transaction
    |
    v
@KafkaListener
    |
    +-- transform input
    +-- kafkaTemplate.send("orders.validated", output)
    |
    v
Container sends consumed offsets to transaction
    |
 +--+---+
 |      |
commit  abort
 |      |
 v      v
output  output aborted
+offset input offset không được commit
committed
~~~

Ví dụ listener:

~~~java
@KafkaListener(
    topics = "orders.in",
    groupId = "orders-transformer",
    containerFactory = "transactionalListenerContainerFactory"
)
public void transform(OrderCreated input) {
    ValidatedOrder output = validator.validate(input);

    kafkaTemplate.send(
        "orders.validated",
        input.orderId(),
        output
    );
}
~~~

Ví dụ trên giả định **transactionalListenerContainerFactory** đã được cấu hình với Kafka-aware transaction manager hoặc API tương ứng của Spring Kafka version đang chạy. KafkaTemplate phải dùng producer tham gia transaction do container mở.

**Chỉ gắn @Transactional lên listener không thay thế việc cấu hình container để gửi input offset vào Kafka transaction.** Container là thành phần điều phối commit offset sau khi listener hoàn tất.

### 12.1. Vì sao offsets và output phải cùng transaction?

Nếu output commit thành công nhưng input offset chưa commit, consumer có thể đọc lại input sau crash và phát output trùng. Khi container gửi output và offsets trong cùng Kafka transaction, commit hoặc abort của chúng được phối hợp theo semantics Kafka.

Điều này tạo cơ sở cho exactly-once consume-transform-produce **thuần Kafka** khi downstream đọc read_committed. Nó không tự đảm bảo exactly-once với hệ thống ngoài Kafka.

### 12.2. Tránh executeInTransaction trong listener transactional

Một lỗi thiết kế dễ mắc là gọi **executeInTransaction** trong callback listener vốn đã được container mở Kafka transaction. Transaction do method này mở là transaction độc lập. Output có thể commit khi input offset trong transaction container chưa commit.

Trong flow yêu cầu atomic input-offset + output-Kafka, hãy gọi **KafkaTemplate.send** bình thường để tham gia transaction hiện hành.

## 13. Consumer read_committed

Consumer downstream nên dùng:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
~~~

Nếu dùng **read_uncommitted**, consumer có thể nhìn thấy record transactional đã abort và làm side effect trên dữ liệu lẽ ra phải bị ẩn.

Một lưu ý vận hành: read_committed consumer có thể bị giới hạn bởi **Last Stable Offset (LSO)** khi có open transaction. Một producer giữ transaction mở lâu có thể làm dữ liệu phía sau chưa sẵn sàng để consumer read_committed đọc, dù log end offset đã tăng.

Khi thấy lag bất thường, cần kiểm tra open transactions và transaction duration, không chỉ tốc độ xử lý của listener.

## 14. Kafka transaction không bao gồm database

Ví dụ:

~~~java
@Transactional
public void createOrder(CreateOrder command) {
    orderRepository.save(new Order(...));
    kafkaTemplate.send("orders.created", ...);
}
~~~

Nếu **@Transactional** ở đây dùng JpaTransactionManager, code không mặc nhiên có Kafka transaction. Nếu nó dùng KafkaTransactionManager, DB cũng không mặc nhiên được atomically committed với Kafka.

Đây là hai tài nguyên khác nhau; Kafka transaction không phải distributed XA transaction giữa broker Kafka và database.

### 14.1. Khoảng lỗi giữa hai lần commit

Ngay cả khi Spring phối hợp transaction synchronization cho database và Kafka, vẫn có tình huống:

~~~text
DB commit thành công
        |
        v
Kafka transaction commit thất bại
        |
        v
DB đã có Order nhưng Kafka chưa có event committed
~~~

Hoặc thứ tự commit ngược lại có thể tạo một khoảng lỗi đối xứng. Spring transaction synchronization giúp điều phối thứ tự thao tác, nhưng không xóa được mọi tình huống thất bại giữa hai hệ thống.

### 14.2. Transactional Outbox

Nếu yêu cầu nghiệp vụ là không được mất event sau khi DB transaction commit, một thiết kế phổ biến là transactional outbox:

~~~text
Create order request
      |
      v
Một DB transaction
      |
      +-- INSERT order
      +-- INSERT outbox_event
      |
      v
    COMMIT
      |
      v
Outbox publisher
      |
      v
KafkaTemplate sends event
      |
      v
Kafka topic
~~~

Outbox publisher có thể gửi lại event sau crash, vì vậy consumer vẫn cần idempotency. Đổi lại, order state và ý định publish được lưu atomically trong cùng DB transaction.

Khi cần nhiều bước qua hệ thống khác nhau, cân nhắc thêm inbox, saga hoặc compensation. Không kỳ vọng KafkaTemplate.executeInTransaction thay thế được các pattern này.

## 15. KafkaTemplate.executeInTransaction và DB side effect

Ví dụ không nên giả định atomic DB+Kafka:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    orderRepository.save(order);
    operations.send("orders.created", orderId, event);
    return null;
});
~~~

Callback trên chỉ tạo transaction Kafka cho các thao tác Kafka. Việc save DB không tự động nằm trong cùng atomic transaction. Nếu DB commit rồi Kafka abort, ứng dụng vẫn có thể mất event.

Giải pháp phụ thuộc mục tiêu nhất quán:

- Outbox khi DB là nguồn dữ liệu chính.
- Inbox/idempotent consumer cho replay.
- Saga hoặc bù trừ khi có nhiều dịch vụ.
- Đối soát định kỳ cho các workflow cần bảo đảm kết quả cuối.
- Kafka-only transaction nếu dữ liệu và offset đều nằm trong Kafka.

## 16. Các lỗi transaction và cách xử lý

| Nhóm lỗi | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Send timeout | Future thất bại hoặc delivery timeout | Kiểm tra broker/network và retry ở boundary an toàn |
| Serialization error | Không tạo được bytes | Sửa serializer/schema |
| Authorization error | Thiếu topic WRITE/TransactionalId quyền | Sửa ACL/principal |
| ProducerFencedException | Producer cũ bị fence | Tạo producer hợp lệ, kiểm tra trùng ID |
| Transaction timeout | Transaction giữ mở quá lâu | Rút ngắn transaction, điều chỉnh timeout theo policy |
| Coordinator unavailable | Không begin/commit được transaction | Kiểm tra broker/transaction coordinator |
| Commit outcome không chắc chắn | Timeout hoặc process chết khi commit | Idempotency và đối soát |
| DLT recovery failure | Publish DLT hoặc recovery thất bại | Không commit nhầm, kiểm tra serializer/ACL |

Không phải mọi lỗi có thể sửa bằng cách retry một KafkaTemplate.send trong cùng transaction. Khi transaction đã lỗi hoặc bị abort, có thể phải **khởi tạo transaction mới và thử lại cả đơn vị nghiệp vụ**, thay vì chỉ gửi lại một record.

~~~text
Transaction #1:
    send A -> ack
    send B -> error
    ABORT

Transaction #2:
    xác định trạng thái nghiệp vụ an toàn
    send A + send B
    COMMIT
~~~

Khi retry một transaction ở cấp ứng dụng, cần bảo đảm caller hoặc consumer không tạo side effect nghiệp vụ trùng.

## 17. Transaction timeout, cache và producer maxAge

Transaction mở lâu có thể làm tăng rủi ro timeout, giữ tài nguyên và làm read_committed consumer chờ LSO. Các nguyên nhân thường gặp:

- Listener xử lý batch rất lớn trong một transaction.
- Method @Transactional gọi HTTP API không có timeout.
- DB lock hoặc downstream chậm.
- Retry/backoff dài xảy ra khi transaction còn mở.
- GC pause hoặc thread blocking kéo dài.

Giữ transaction ngắn, có timeout rõ ràng và hạn chế thao tác không liên quan trong transaction boundary.

### 17.1. Producer cache và transactional ID suffix

DefaultKafkaProducerFactory có thể cache transactional producer. Producer được tạo với những transactional ID khác nhau dựa trên prefix và suffix:

~~~text
order-pod-a-tx-0
order-pod-a-tx-1
order-pod-a-tx-2
~~~

Nếu có nhiều transaction đồng thời, cần bảo đảm ProducerFactory đủ khả năng cung cấp producer và broker transaction coordinator chịu được tải tương ứng.

### 17.2. Tái sử dụng producer sau thời gian idle

Kafka broker có cơ chế expiration đối với transactional IDs không hoạt động. Một cached producer không dùng quá lâu có thể gặp vấn đề khi được tái sử dụng, tùy version và broker configuration.

Spring Kafka cung cấp lựa chọn **maxAge** trên DefaultKafkaProducerFactory ở các phiên bản hỗ trợ để làm mới producer trước khi tới ngưỡng expiration. Hãy kiểm tra broker **transactional.id.expiration.ms**, phiên bản client và phương thức cấu hình maxAge thực tế.

## 18. ACL và authentication cho transactional producer

Producer transactional có thể cần:

- WRITE trên mỗi topic đầu ra.
- Quyền phù hợp trên **TransactionalId** được sử dụng.
- Quyền idempotent write/cluster-level trong cấu hình/version yêu cầu.
- Nếu tham gia consume-transform-produce, consumer có READ trên topic input và group permission tương ứng.

Khi transactional IDs có hậu tố từ ProducerFactory, ACL literal quá hẹp có thể không khớp. Có thể dùng prefix ACL được giới hạn riêng cho service và environment.

Không thêm application principal thành superuser chỉ để né lỗi authorization. Hãy xác định principal, resource, operation từ broker log, rồi cấp least privilege.

## 19. Transactional listener và error handler

Error handling ở container transactional có semantics khác với non-transactional listener.

Với non-transactional container, **DefaultErrorHandler** thường được dùng để seek/retry/recover. Với container transactional, một exception có thể abort transaction và cơ chế sau rollback thường đi qua **AfterRollbackProcessor**.

Khi thiết kế consume-transform-produce, cần xác định:

1. Ai bắt đầu Kafka transaction: container hay service?
2. KafkaTemplate có tham gia đúng transaction không?
3. Offset đầu vào có được gửi vào transaction không?
4. Nếu listener lỗi, transaction nào abort?
5. Nếu gửi DLT, output DLT và commit input offset có được phối hợp an toàn không?
6. Có DB/HTTP side effect nào cần idempotency hoặc compensation không?

Không tự gọi commit/abort trên KafkaProducer được container quản lý. Spring Kafka cần giữ quyền điều phối producer lifecycle, offset và transaction outcome.

### 19.1. DLT trong luồng transactional

Một poison record cần được xử lý để không chặn mãi partition. Nếu DLT publish thất bại nhưng input offset vẫn commit, record có thể bị bỏ qua mà chưa được cô lập.

Cần xác minh DLT recoverer/AfterRollbackProcessor và commit policy của phiên bản Spring Kafka đang chạy, thay vì giả định cấu hình record listener non-transactional áp dụng nguyên xi.

## 20. Monitoring KafkaTemplate trong transaction

| Metric / tín hiệu | Điều cần theo dõi |
|---|---|
| Transaction commit/abort count | Giao dịch Kafka kết thúc theo kết quả nào |
| Transaction duration | Có transaction mở lâu bất thường không |
| Producer send failures | Topic hoặc partition nào lỗi ghi |
| Transaction commit latency | Kafka coordinator phản hồi chậm không |
| Producer fencing errors | Có transactional ID collision không |
| Transactional ID distribution | Các replica có dùng namespace riêng không |
| Producer cache usage | Producer có bị tạo/đóng quá thường xuyên không |
| read_committed consumer lag | Output có bị kẹt do open transaction không |
| Last Stable Offset | Open transaction đang giữ tiến độ đọc không |
| DLT recovery success/failure | Poison record có được cô lập an toàn không |
| Downstream duplicate detection | Replay có tạo side effect lặp không |

Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer và exporter. Một số thông tin transaction outcome phải instrument ở tầng service hoặc container.

Log có thể ghi:

~~~text
service=order-service
action=publishOrderEvents
topic=orders.events
transactionOutcome=committed
transactionDurationMs=38
correlationId=ord-801
~~~

Không log token, password, JAAS config, private key hay payload nhạy cảm. Tránh dùng event ID và order ID làm metric labels có cardinality cao.

## 21. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| “No transaction is in process” | send ngoài transaction | Xác nhận @Transactional manager, executeInTransaction, AOP proxy |
| ProducerFencedException sau scale | Replica trùng transactional ID | Xem transaction-id-prefix theo pod |
| TransactionalIdAuthorizationException | Thiếu ACL trên ID thật | Xem broker principal/resource |
| Send future thành công nhưng consumer không thấy | Transaction chưa commit, bị abort hoặc consumer chưa poll | Xem outcome và isolation.level |
| DB commit nhưng Kafka không có event | Không có atomic DB+Kafka commit | Đánh giá outbox |
| Consumer lag tăng dù broker có record | Open transaction giữ LSO | Xem read_committed và transaction duration |
| Lỗi sau idle dài | Cached transactional producer và ID expiration | Xem maxAge và broker config |
| DLT ghi không thành công | Serializer, topic, ACL, broker | Xác minh recovery result |
| Timeout khi commit | Coordinator/network/transaction duration | Xem coordinator và timeout |

### 21.1. Không coi send success là commit success

Producer future có thể hoàn tất thành công trước khi Kafka transaction commit. Nếu transaction abort sau đó, downstream read_committed vẫn không nhận record.

Log transaction outcome ở boundary thích hợp và giữ correlation ID để đối soát khi commit outcome chưa xác định.

### 21.2. Fencing sau rollout

Nếu hai pod cùng dùng prefix cố định và tạo transactional ID trùng, chúng có thể liên tục fence nhau. Khi lỗi chỉ xuất hiện sau tăng replicas, kiểm tra namespace ID trước khi tăng retry count.

## 22. Integration test cho Kafka transaction

Nên kiểm tra các trường hợp bằng Embedded Kafka hoặc Testcontainers có broker hỗ trợ transaction.

### 22.1. Test commit

1. Cấu hình ProducerFactory transactional và KafkaTemplate.
2. Mở transaction bằng @Transactional hoặc executeInTransaction.
3. Gửi record A và B tới topic/partition phù hợp.
4. Commit transaction.
5. Dùng consumer read_committed đọc lại.
6. Xác nhận hai output committed xuất hiện.

### 22.2. Test abort

1. Bắt đầu transaction.
2. Gửi record A.
3. Ném RuntimeException trong callback.
4. Xác nhận transaction abort.
5. Consumer read_committed không trả record A.
6. Thử transaction mới để xác nhận producer lifecycle tiếp tục theo policy.

Ví dụ minh họa:

~~~java
assertThrows(
    IllegalStateException.class,
    () -> kafkaTemplate.executeInTransaction(ops -> {
        ops.send("orders.events", "o-1", event).join();
        throw new IllegalStateException("force abort");
    })
);
~~~

Đây là snippet minh họa test; cần tạo test data, KafkaTemplate và imports tương ứng.

### 22.3. Test restart, fencing và external consistency

- Restart producer trước commit và kiểm tra read_committed output.
- Cố ý tạo hai producer cùng transactional ID trong môi trường test để quan sát fencing.
- Gây lỗi coordinator/commit và xác nhận app không coi outcome không chắc chắn là thành công chắc chắn.
- Nếu có DB, thử crash giữa DB commit và Kafka commit.
- Kiểm tra outbox publisher gửi lại event vẫn an toàn nhờ idempotency.

## 23. Runbook vận hành

1. Xác định KafkaTemplate và ProducerFactory thực tế đang dùng.
2. Kiểm tra transaction-id-prefix hiệu lực cho từng instance.
3. Xác nhận KafkaTransactionManager được chọn đúng trong @Transactional.
4. Xác định boundary: annotation, executeInTransaction hay listener container.
5. Kiểm tra producer đã tham gia transaction hiện hành chưa.
6. Với consume-transform-produce, xác minh input offsets đi cùng output Kafka.
7. Kiểm tra downstream dùng read_committed nếu cần loại aborted record.
8. Xác nhận ACL cho topic và TransactionalId.
9. Quan sát transaction duration, commit/abort và producer fencing.
10. Khi lỗi, phân biệt send timeout, commit timeout, authorization và producer bị fence.
11. Retry theo phạm vi transaction an toàn; không tạo duplicate side effect.
12. Kiểm tra DB/HTTP side effects với outbox, inbox hoặc compensation.
13. Thử restart, abort, fencing, DLT recovery và producer idle.
14. Ghi cách đối soát khi commit outcome chưa chắc chắn.

## 24. Những nhầm lẫn cần tránh

**KafkaTemplate.send thành công nghĩa là transaction đã commit.** Sai: send acknowledgment có thể đến trước transaction commit.

**executeInTransaction luôn dùng lại transaction listener.** Sai: method này mở transaction cục bộ riêng.

**@Transactional tự động gộp DB và Kafka thành một XA transaction.** Sai: transaction manager và tài nguyên khác nhau.

**Kafka idempotence tương đương transaction.** Sai: idempotence xử lý duplicate do retry; transaction quản lý commit/abort của nhóm thao tác Kafka.

**read_uncommitted chỉ đọc record đã commit.** Sai: nó có thể trả aborted transactional record.

**Mọi pod có thể dùng một transactional ID.** Sai: cùng ID đồng thời gây fencing.

**Retry vô hạn ProducerFencedException.** Sai: producer cũ đã bị fence không thể tiếp tục như bình thường.

**Giữ transaction mở thật lâu sẽ an toàn hơn.** Sai: transaction dài dễ timeout và ảnh hưởng read_committed consumer.

**Kafka transaction bảo đảm hai ứng dụng downstream xử lý cùng lúc.** Sai: Kafka atomic commit không điều khiển lịch poll hoặc side effect của downstream.

## 25. Ghi nhớ

**KafkaTemplate trong transaction** cho phép Spring Kafka gửi nhiều record tới Kafka như một đơn vị commit/abort. Producer-initiated transaction thường dùng **@Transactional** với KafkaTransactionManager hoặc **KafkaTemplate.executeInTransaction**. Trong consumer-initiated transaction, listener container mở transaction và KafkaTemplate gửi output để input offset và output Kafka cùng được quản lý theo semantics Kafka.

Để vận hành an toàn, phải cấu hình transactional ProducerFactory, transaction-id-prefix duy nhất theo instance, ACL, timeout và downstream read_committed. Send acknowledgment không đồng nghĩa transaction commit; cần quan sát commit/abort, fencing và thời gian transaction.

Kafka transaction không atomically commit thay cho DB hay HTTP. Với workflow xuyên hệ thống, hãy kết hợp outbox/inbox, idempotency và recovery phù hợp để bảo đảm tính đúng đắn ngay cả khi process crash hoặc commit outcome không chắc chắn.
