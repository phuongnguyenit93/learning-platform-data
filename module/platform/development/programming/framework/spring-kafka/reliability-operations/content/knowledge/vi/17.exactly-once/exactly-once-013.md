# Giới hạn của exactly once ngoài Kafka trong Spring Kafka

Trong Spring Kafka, **exactly-once semantics (EOS)** là một bảo đảm có phạm vi, không phải lời hứa rằng một sự kiện chỉ được thực thi đúng một lần ở mọi hệ thống. Kafka có thể phối hợp producer transactions, output records và input offsets để tránh các kết quả Kafka bị lặp hoặc bị công bố dở dang trong những luồng được hỗ trợ. Tuy nhiên, **database, HTTP API, payment gateway, email và object storage không tự động tham gia Kafka transaction**.

Một record Kafka có thể được chuyển cho cùng một listener nhiều lần sau crash, rebalance, timeout, seek hoặc DLT replay. Nếu listener đã thực hiện side effect bên ngoài Kafka rồi mới bị lỗi trước offset commit, tác động ấy có thể lặp lại. Vì vậy, bảo đảm quan trọng ở tầng nghiệp vụ thường là **effectively-once effect**: cho phép nhiều lần nhận/gọi xử lý, nhưng mỗi logical operation chỉ thay đổi trạng thái đích một lần theo quy tắc nghiệp vụ.

Bài này tập trung vào ranh giới giữa Kafka EOS và các external side effects, các điểm lỗi dual-write, và cách dùng **transactional inbox, transactional outbox, idempotency key, saga, state machine và reconciliation** trong Spring Kafka Reliability Operations.

## 1. Xác định rõ đối tượng của exactly once

Trước khi đánh giá một hệ thống "exactly once", cần xác định điều được đảm bảo:

- **Delivery:** một Kafka record có thể được consumer nhận lại khi offset chưa commit.
- **Listener execution:** một method @KafkaListener có thể chạy lại cùng record; Kafka EOS không cấm điều đó.
- **Kafka output visibility:** transactional output và input offsets có thể được commit cùng nhau; consumer read_committed không quan sát output thuộc transaction abort.
- **Database effect:** một hàng dữ liệu có được insert/update bao nhiêu lần; điều này được kiểm soát bởi DB transaction, unique constraint và domain rules.
- **External API effect:** một khoản tiền có bị charge hai lần hay không; điều này phụ thuộc idempotency contract của payment provider.
- **Physical effect:** email đã gửi hoặc thiết bị đã kích hoạt không thể bị Kafka abort kéo ngược lại.

~~~text
orders.created
      |
      v
Spring Kafka listener  <--- Có thể nhận lại cùng record
      |
      +--> KafkaTemplate.send(output)
      |         |
      |         +--> Kafka transaction có thể bao phủ
      |
      +--> Database INSERT/UPDATE
      |         |
      |         +--> Database transaction riêng
      |
      +--> HTTP POST /payments
      |         |
      |         +--> Payment provider riêng
      |
      +--> Email / Object storage
                |
                +--> Hệ thống ngoài Kafka
~~~

Muốn nói "đúng một lần" phải trả lời: một lần **gửi request**, một lần **gọi method**, một lần **commit Kafka output**, hay một lần **thay đổi số dư**? Đây là những mục tiêu khác nhau.

## 2. Kafka EOS bảo vệ luồng Kafka → Kafka

Trong một transactional listener container, container có thể mở Kafka transaction trước khi gọi listener. Listener phát các Kafka output records qua producer tham gia transaction đó. Khi xử lý thành công, container gửi consumer offsets vào cùng Kafka transaction trước khi commit.

~~~text
Input Kafka record
        |
        v
Transactional listener
        |
        +--> Gửi output Kafka
        |
        +--> Gửi input offset vào transaction
        |
        +--------------+---------------+
        |                              |
        v                              v
    COMMIT TX                       ABORT TX
        |                              |
        +--> Output visible             +--> Output không visible
        |    với read_committed         |    với read_committed
        +--> Input offset commit        +--> Input offset không commit
~~~

Một consumer downstream muốn chỉ đọc Kafka output đã commit phải đặt:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

Producer giao dịch cần cấu hình thích hợp, ví dụ:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: order-service-node-1-
      acks: all
      properties:
        "[enable.idempotence]": true
    consumer:
      enable-auto-commit: false
      isolation-level: read_committed
~~~

Các thiết lập này là ví dụ minh họa. Producer factory và listener container factory phải thực sự được cấu hình KafkaTransactionManager hoặc Kafka-aware transaction manager phù hợp với phiên bản Spring Kafka/Spring Boot. Chỉ đặt một property không đảm bảo factory tùy biến sẽ tự dùng transaction manager.

Kafka EOS giải quyết việc atomic commit của **những thao tác nằm trong Kafka transaction**, không tự bao phủ mọi lệnh Java trong listener. Consumer read_uncommitted vẫn có thể quan sát output transactional bị abort; do đó isolation level của downstream là một phần quan trọng của contract.

## 3. Kafka transactions không có nghĩa listener chỉ chạy một lần

Giả sử listener gửi Kafka output rồi thất bại trước khi transaction commit. Container abort transaction và record đầu vào có thể được giao lại.

~~~text
Lần 1:
  Input event E
      |
      +--> Listener chạy
      +--> Kafka output chưa commit
      +--> Exception
      +--> Abort transaction

Lần 2:
  Input event E được giao lại
      |
      +--> Listener chạy lại
      +--> Kafka output
      +--> Commit transaction
~~~

Listener được gọi hai lần, nhưng transactional output từ lần abort không được read_committed consumer quan sát. Đó là điểm khác biệt giữa **at-least-once execution** và EOS của Kafka output.

Nếu trong lần 1 listener đã gửi email hoặc cập nhật database, Kafka abort không hoàn tác các thao tác đó. Vì thế, việc chỉ đo số lần gọi listener không chứng minh mức bảo đảm Kafka transaction và cũng không chứng minh hiệu ứng nghiệp vụ đúng một lần.

## 4. Producer idempotence khác idempotency nghiệp vụ

Kafka producer idempotence giúp ngăn một số duplicate records phát sinh khi **cùng ProduceRequest** được retry theo cơ chế Kafka protocol. Nó không tự nhận diện các lời gọi nghiệp vụ được tạo mới từ hai lần consumer execution.

| Cơ chế | Phạm vi bảo vệ | Không bảo vệ |
|---|---|---|
| Producer idempotence | Retry của producer trong phạm vi protocol và producer session | Hai lần gọi business logic khác nhau dùng cùng event |
| Kafka transaction | Kafka output records và input offsets thuộc transaction | Database, payment, email |
| Unique constraint DB | Một loại bản ghi trùng theo khóa | API bên ngoài không dùng DB đó |
| Consumer inbox | Cùng logical event được xử lý lại | Output Kafka nếu thiếu outbox |
| API idempotency key | Cùng logical API request tại provider có hỗ trợ | Request mới có key khác |
| Aggregate version | Event cũ không ghi đè trạng thái mới | Thiếu event hoặc side effect khác |

Ví dụ cùng eventId được replay từ DLT. Ứng dụng gọi KafkaTemplate.send một lần ở mỗi execution. Nếu mỗi lần là một transaction Kafka hợp lệ riêng biệt, producer idempotence không tự biết eventId đã từng được xử lý nghiệp vụ.

Cần tạo **eventId** hoặc **operationId** ổn định ở nguồn và giữ nguyên qua retry/replay. Không tạo UUID mới cho mỗi attempt nếu muốn các lần đó được coi là cùng một thao tác.

## 5. Bài toán dual-write

Một service vừa ghi database vừa ghi Kafka đang cập nhật **hai resource độc lập**. Thứ tự commit nào cũng tồn tại điểm mà một resource đã commit còn resource kia chưa commit.

~~~java
@KafkaListener(topics = "orders.created", groupId = "order-service")
public void onOrder(OrderCreated event) {
    orderRepository.save(toEntity(event));
    kafkaTemplate.send("orders.processed", event.orderId(), event);
}
~~~

Code ngắn không cho biết cả hai bước đã được gắn với transaction nào. Các cửa sổ lỗi:

| Thời điểm crash | Database | Kafka output/offset | Rủi ro |
|---|---|---|---|
| Trước DB commit | Chưa thay đổi | Chưa commit | Có thể redelivery và thử lại |
| Sau DB commit trước input offset commit | Đã thay đổi | Offset chưa commit | Database side effect có thể bị lặp |
| Sau Kafka output commit trước DB commit | Chưa thay đổi | Output đã có | Consumer downstream thấy event không tương ứng DB |
| Sau DB commit trước Kafka output publish | Đã thay đổi | Thiếu output | Event downstream có thể bị mất nếu không có outbox |
| Cả hai đã commit nhưng caller chưa nhận response | Đều thành công | Caller không biết | Caller retry có thể nhân đôi yêu cầu |

Đổi thứ tự DB trước Kafka hay Kafka trước DB chỉ đổi cửa sổ lỗi. Try/catch không biến hai resource thành một distributed atomic transaction.

## 6. Vì sao @Transactional không đủ để bảo đảm atomicity DB + Kafka?

Ví dụ:

~~~java
@Transactional
public void saveAndPublish(OrderCreated event) {
    orderRepository.save(toEntity(event));
    kafkaTemplate.send("orders.processed", event.orderId(), event);
}
~~~

Nếu @Transactional dùng JpaTransactionManager, transaction đó quản lý database. KafkaTemplate có thể tham gia một Kafka transaction hoặc chạy khác tùy ProducerFactory và cấu hình transaction synchronization. Nhưng không có bảo đảm XA/2PC chỉ vì hai lời gọi nằm trong cùng Java method.

Ngay cả khi Spring đồng bộ hai transaction managers, vẫn có điểm:

~~~text
Database COMMIT thành công
           |
           v
Kafka COMMIT thất bại
           |
           v
Database đã thay đổi, Kafka output chưa hoàn tất
~~~

Hoặc đổi thứ tự thì Kafka commit trước rồi database thất bại.

Một Spring transaction annotation không tự làm Kafka và database cùng commit/rollback nguyên tử trong mọi tình huống lỗi. Với workflow quan trọng, hãy thiết kế một nguồn sự thật bền vững (thường database) và cơ chế khôi phục những bước còn lại.

## 7. Kafka → Database: transactional inbox

Một consumer đọc event rồi cập nhật database cần chịu được redelivery. **Transactional inbox** hoặc processed-events table lưu dấu event đã áp dụng cùng với database side effect trong một transaction.

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(150) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong Java:

~~~java
@Service
public class OrderProjectionService {

    private final ProcessedEventRepository processedEvents;
    private final OrderRepository orders;

    public OrderProjectionService(
            ProcessedEventRepository processedEvents,
            OrderRepository orders) {
        this.processedEvents = processedEvents;
        this.orders = orders;
    }

    @Transactional
    public void apply(OrderCreated event) {
        boolean firstTime = processedEvents.insertIfAbsent(
                "order-projection",
                event.eventId()
        );

        if (!firstTime) {
            return;
        }

        orders.insertOrderIfAbsent(
                event.orderId(),
                event.amount(),
                event.currency()
        );
    }
}
~~~

insertIfAbsent là một thao tác atomic được database bảo vệ bằng unique constraint, không đơn thuần là SELECT rồi INSERT không có kiểm soát concurrency.

Cần ghi dấu processed event và cập nhật order **trong cùng database transaction**. Nếu cập nhật order thất bại, dấu processed cũng phải rollback. Nếu ghi dấu commit trước rồi nghiệp vụ mới thất bại, lần giao lại sẽ bị bỏ qua và gây mất xử lý.

### Cửa sổ crash được inbox giải quyết

~~~text
Kafka input E
       |
       v
BEGIN DB TRANSACTION
       |
       +--> INSERT processed_events(E)
       +--> UPDATE orders
       |
       v
COMMIT DB
       |
       +--> Process crash trước Kafka offset commit
       |
       v
Kafka redelivery E
       |
       v
INSERT processed_events(E) bị unique conflict
       |
       v
Không lặp database side effect
       |
       v
Listener return; Kafka offset có thể commit
~~~

Như vậy, listener chạy lại nhưng **effect trên database** chỉ áp dụng một lần theo eventId và unique constraint được định nghĩa.

## 8. Atomic deduplication trong database

Một cách làm ở PostgreSQL:

~~~sql
INSERT INTO processed_events (
    consumer_name, event_id
)
VALUES (
    :consumer_name, :event_id
)
ON CONFLICT (consumer_name, event_id)
DO NOTHING
RETURNING event_id;
~~~

Nếu INSERT trả về một row, event mới được claim trong transaction đó; nếu không, event đã có.

Không dùng đoạn logic này nếu thiếu transaction chung:

~~~java
if (!processedEvents.exists(event.eventId())) {
    orders.insert(event);
    processedEvents.markProcessed(event.eventId());
}
~~~

Hai consumers hoặc một worker và một replay job có thể cùng kiểm tra không tồn tại rồi cùng thực thi side effect trước khi tranh chấp ghi processed marker. Unique constraint là chốt bảo vệ concurrency thực tế.

Nếu event có nhiều bước ngoài database, processed marker ở đây chỉ phản ánh **bước đã commit trong database**. Nó không tự chứng minh payment hoặc email cũng đã hoàn tất.

## 9. Database → Kafka: transactional outbox

Khi ứng dụng cập nhật database rồi phát event Kafka, **transactional outbox** giúp không làm mất ý định phát event sau khi DB commit.

~~~text
HTTP command
    |
    v
Database transaction
    |
    +--> INSERT orders
    +--> INSERT outbox_events
    |
    v
COMMIT DATABASE
    |
    v
Outbox publisher hoặc CDC
    |
    v
Kafka topic orders.created
~~~

Schema minh họa:

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(150) PRIMARY KEY,
    aggregate_id VARCHAR(150) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL
);
~~~

Ghi domain change và outbox row trong một DB transaction:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    Order order = orderRepository.insert(command);

    outboxRepository.insert(
            OutboxEvent.orderCreated(
                    command.requestId(),
                    order.id(),
                    order.toCreatedEvent()
            )
    );
}
~~~

Nếu transaction rollback, không có order và cũng không có outbox row. Nếu DB commit thành công, outbox row còn đó để gửi Kafka sau restart.

Publisher có thể đọc bảng định kỳ hoặc dùng Change Data Capture như Debezium. Tuy nhiên, **outbox không tự loại bỏ duplicate ở Kafka**: publish Kafka thành công rồi crash trước khi đánh dấu sent sẽ khiến publisher gửi lại. Downstream vẫn phải dùng eventId và idempotent consumer.

## 10. Kết hợp inbox + outbox cho Kafka → DB → Kafka

Đây là một mô hình quan trọng nếu một event đầu vào vừa cập nhật database vừa sinh event đầu ra.

~~~text
Kafka input
     |
     v
@KafkaListener
     |
     v
Database transaction
     |
     +--> INSERT inbox(eventId) nếu chưa có
     +--> UPDATE orders
     +--> INSERT outbox(outputEventId)
     |
     v
COMMIT DATABASE
     |
     +--> Listener return, Kafka input offset commit
     |
     +--> Outbox publisher gửi Kafka output
~~~

Bảng cửa sổ lỗi:

| Tình huống | Cách phục hồi |
|---|---|
| Crash trước DB commit | DB rollback, Kafka redelivery |
| Crash sau DB commit trước offset commit | Inbox chống duplicate |
| Crash trước outbox publish | Outbox row vẫn còn |
| Kafka unavailable khi publish | Publisher retry |
| Publish xong nhưng chưa mark-sent | Có thể publish trùng, downstream inbox chống duplicate |
| Output được nhận hai lần | Idempotent consumer ở downstream |

Code service minh họa:

~~~java
@Service
public class OrderProjector {

    private final InboxRepository inbox;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderProjector(
            InboxRepository inbox,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.inbox = inbox;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void apply(OrderCreated event) {

        boolean firstTime = inbox.insertIfAbsent(
                "order-projector",
                event.eventId()
        );

        if (!firstTime) {
            return;
        }

        OrderValidated validated = orders.applyCreated(event);

        outbox.insertIfAbsent(
                OutboxEvent.from(event.eventId(), validated)
        );
    }
}
~~~

Ở đây các repository methods đại diện implementation database thật, cần transaction chung và unique keys. Khi duplicate input được đọc lại, method có thể return thành công để container commit Kafka offset; không tạo thêm domain update hay outbox row.

## 11. HTTP API và tình huống timeout không rõ kết quả

HTTP timeout không chứng minh request chưa được xử lý. Với payment:

~~~text
Consumer                 Payment Provider
   |                            |
   |---- POST /charge --------->|
   |                            +--> Charge thành công
   |<---- Response bị mất -----X |
   |
   +--> Timeout exception
   |
   +--> Retry POST /charge
                                |
                                +--> Có thể charge lần hai
~~~

Kafka abort không thể hoàn tác charge đầu tiên. Nếu provider hỗ trợ **idempotency key**, hãy gửi cùng operationId cho mọi lần retry của cùng logical payment:

~~~java
paymentClient.charge(
        event.paymentId(),
        event.amount(),
        event.paymentOperationId()
);
~~~

operationId phải ổn định qua consumer restart, retry topics và DLT replay. Không dùng số lần attempt hoặc random UUID mới mỗi retry làm idempotency key.

Cần hiểu contract của provider:

- Idempotency key được lưu bao lâu?
- Cùng key nhưng payload khác nhau có bị từ chối không?
- Có trả về kết quả request trước hay chỉ báo duplicate?
- Khi request đầu tiên đang xử lý thì request thứ hai ra sao?
- Có API tra cứu trạng thái bằng operationId không?
- Có thể đối chiếu settlement hoặc webhook về sau không?

Sau timeout, nếu có thể, hãy **query trạng thái** trước khi tạo một thao tác mới. Với payment/financial operations, không nên cho rằng HTTP 500 hoặc timeout luôn có nghĩa transaction đích đã rollback.

## 12. API đích không hỗ trợ idempotency: giới hạn bất khả tránh

Nếu external API không có idempotency key, không có status lookup và response có thể bị mất, caller không thể biết chắc request đã thực thi hay chưa.

Hai lựa chọn đều có đánh đổi:

- **Retry để tránh bỏ sót:** có thể tạo duplicate effect.
- **Không retry để tránh trùng:** có thể bỏ sót effect nếu request chưa hoàn tất.

KafkaTransactionManager không thể giải quyết tình huống này vì Kafka không kiểm soát commit của API bên ngoài.

Hướng cải thiện:

1. Thay đổi API contract để hỗ trợ operationId idempotent.
2. Thêm status lookup hoặc reconciliation với hệ thống đích.
3. Ghi trạng thái request bền vững ở hệ thống gọi.
4. Có compensation để hoàn tác một số duplicate effects nếu nghiệp vụ cho phép.
5. Công bố rõ tradeoff delivery guarantee khi không thể loại bỏ hoàn toàn duplicate/missing effect.

Đây là giới hạn thực sự của distributed systems, không phải lỗi thiếu annotation trong Spring Kafka.

## 13. Email và SMS không thể được Kafka rollback

Một consumer gửi email thành công rồi crash trước Kafka offset commit có thể gửi lại email khi record redelivery. Kafka abort không thu hồi email đã tới mailbox.

~~~text
Kafka listener
     |
     +--> Email provider accepted message
     |
     +--> Process crash
     |
     +--> Kafka offset chưa commit
     |
     v
Retry/replay --> Email gửi thêm lần nữa
~~~

Có thể giảm khả năng lặp bằng:

- Notification ID ổn định và delivery state bền vững.
- Transactional outbox cho yêu cầu gửi.
- Idempotency key hoặc message status lookup nếu provider hỗ trợ.
- Rate limit và cooldown cho notification nhạy cảm.
- Webhook handling idempotent.
- Chính sách rõ ràng về chấp nhận duplicate hoặc missing notification.

Nếu provider không thể xác nhận đã gửi hay chưa và không hỗ trợ dedup, không nên hứa **chắc chắn không gửi trùng và không bỏ sót** trong mọi tình huống.

## 14. Object storage và file side effect

Ghi object/file cũng ở ngoài Kafka transaction.

~~~text
Kafka E
   |
   +--> putObject("reports/order-1.pdf") thành công
   |
   +--> Crash trước commit Kafka offset
   |
   +--> Redelivery E
   |
   +--> putObject lần hai
~~~

Để tăng idempotency, có thể dùng deterministic object key từ logical operation, kiểm tra checksum và conditional write (ví dụ ETag hoặc điều kiện object chưa tồn tại) theo API của storage.

Nhưng nếu còn phải commit metadata database, lại xuất hiện dual-write giữa storage và database. Có thể dùng workflow state PENDING/UPLOADING/UPLOADED/VERIFIED, outbox cho yêu cầu upload và reconciliation cho orphan objects.

Đừng dùng random filename mới mỗi attempt nếu mục tiêu là một object cho mỗi logical operation. Ngược lại, cũng không ghi đè một object của operation khác chỉ vì key bị trùng. Thiết kế key và quyền truy cập theo tenant cần được xác thực.

## 15. Một boolean processed không đủ cho workflow nhiều bước

Một nghiệp vụ có thể cần:

~~~text
1. Reserve inventory
2. Charge payment
3. Send confirmation
4. Publish fulfilled event
~~~

Nếu chỉ lưu processed(eventId)=true/false:

- Đánh dấu true ngay đầu: crash sau đó có thể bỏ sót các bước chưa chạy.
- Đánh dấu true ở cuối: crash giữa quy trình có thể lặp lại các bước đã hoàn tất.
- Không có trạng thái trung gian: khó xử lý timeout không rõ kết quả.

Thay bằng state machine bền vững:

~~~text
RECEIVED
   |
   v
INVENTORY_RESERVED
   |
   v
PAYMENT_CONFIRMED
   |
   v
NOTIFICATION_REQUESTED
   |
   v
COMPLETED
~~~

Mỗi bước nên có:

- Step ID/operation ID ổn định.
- Idempotency ở resource đích.
- Trạng thái và attempt count được lưu bền vững.
- Deadline, timeout và backoff.
- Retry hoặc compensation nếu bước sau thất bại.
- Audit để xác định bước nào thực sự hoàn tất.

Với nhiều resource độc lập, đây thường là mô hình **saga** hoặc workflow orchestration, không phải một transaction Kafka dài bao toàn bộ xử lý.

## 16. Saga và compensating actions

Saga chia nghiệp vụ thành nhiều local transactions. Nếu một bước thất bại, hệ thống có thể thực hiện thao tác bù trừ:

~~~text
Create order
     |
     v
Reserve stock
     |
     v
Charge payment
     |
     +--> Success --> Confirm order
     |
     +--> Failure --> Release stock
~~~

Release stock không giống rollback của một transaction database duy nhất. Nó là một **business action mới** có thể thất bại hoặc bị gọi lại. Vì vậy, compensation cũng cần idempotency key như reservationId hoặc paymentOperationId.

Nếu thanh toán đã xảy ra nhưng trạng thái local chưa cập nhật vì timeout, không nên refund một cách mù quáng; cần truy vấn và đối chiếu trạng thái trước khi quyết định bù trừ.

Saga cần ownership, state machine, audit, error routing, manual intervention và reconciliation cho những bước không thể tự sửa.

## 17. Consumer offset không phải chứng chỉ cho external effect

Consumer committed offset là vị trí đọc của consumer group. Nó không nói database đã commit hay payment đã được capture thành công.

~~~text
Consumer A xử lý event E
       |
       +--> Database COMMIT
       |
       +--> Kafka offset CHƯA commit
       |
       +--> Rebalance hoặc crash
                   |
                   v
Consumer B nhận partition
       |
       +--> Đọc lại E
       |
       +--> Inbox ngăn duplicate database effect
~~~

Với Kafka → DB, thứ tự thực tế thường nên là:

1. Bắt đầu database transaction.
2. Claim eventId bằng unique constraint.
3. Thực hiện domain update trong cùng transaction.
4. Commit database transaction.
5. Listener trả về thành công.
6. Kafka container commit input offset.

Nếu crash giữa bước 4 và 6, record có thể được đọc lại nhưng inbox giúp tránh side effect trùng. Nếu commit Kafka offset trước bước 4, có nguy cơ mất nghiệp vụ khi process crash.

Đây là lựa chọn có chủ đích: **chấp nhận redelivery, chống duplicate bằng dữ liệu bền vững**.

## 18. Retry topic, DLT và replay vẫn có thể tạo duplicate

Spring Kafka DefaultErrorHandler, RetryTopicConfiguration hoặc @RetryableTopic giúp retry/recovery, nhưng không tự bảo đảm exactly-once external effect.

~~~text
Topic nguồn
    |
    +--> Lỗi, chuyển retry topic
    |           |
    |           +--> Xử lý lại
    |
    +--> Hết attempts
                |
                v
               DLT
                |
                v
             Replay
                |
                v
         Listener chạy lại
~~~

Các cửa sổ đáng chú ý:

- Publish retry topic thành công nhưng source offset chưa commit.
- Publish DLT thành công nhưng crash trước source offset commit.
- Operator replay record đã có một số side effects.
- Retry topic làm record sau vượt record lỗi trong cùng business aggregate.
- Một external API đã nhận request nhưng listener vẫn báo lỗi.

DLT không chứng minh nghiệp vụ chưa có bất kỳ side effect nào. Trước khi replay, cần kiểm tra eventId, operationId, trạng thái external dependencies, quy tắc ordering và audit.

## 19. Kafka Streams exactly_once_v2 và external calls

Kafka Streams có processing guarantee exactly_once_v2 cho các thao tác Kafka được framework quản lý, bao gồm state stores/changelog và output/offsets theo khả năng transaction. Ví dụ:

~~~properties
processing.guarantee=exactly_once_v2
~~~

Điều này không có nghĩa một Kafka Streams processor gọi REST API không idempotent sẽ tạo exactly-once HTTP effect.

Một transformer có thể gọi payment provider thành công, sau đó Kafka transaction abort. Khi input được xử lý lại, transformer có thể gọi payment lần nữa. State store và Kafka changelog không tự rollback payment provider.

Do đó, ngay cả với Kafka Streams EOS, mọi external I/O cần idempotency, outbox, durable workflow state hoặc reconciliation.

## 20. Ordering và aggregate version

Dedup theo eventId ngăn cùng event được xử lý hai lần, nhưng không giải quyết **hai event khác nhau được xử lý sai thứ tự**.

~~~text
OrderStatusChanged(version=5) --> retry topic
OrderStatusChanged(version=6) --> thành công ở topic nguồn
OrderStatusChanged(version=5) --> replay muộn
~~~

Hai event có eventId khác nhau. Inbox không chặn version 5 khi nó chưa từng được xử lý, dù version 6 đã được áp dụng.

Có thể dùng optimistic/version check:

~~~sql
UPDATE orders
SET status = :new_status,
    version = :new_version
WHERE order_id = :order_id
  AND version = :expected_version;
~~~

Nếu affected rows bằng 0, cần xác định event cũ, event đến sai thứ tự, hoặc aggregate không ở trạng thái mong đợi. Không tự động retry vô hạn mọi version conflict.

Kafka partition key giúp giữ thứ tự trong từng topic/partition, nhưng retry topic, async processing và external APIs có thể phá thứ tự **hoàn tất side effect**. Kết hợp eventId, aggregate version và state transition rules khi nghiệp vụ đòi hỏi cả chống duplicate và đúng thứ tự.

## 21. Định danh idempotency và thời gian giữ dedup state

Một số khóa có mục đích khác nhau:

| Khóa | Ý nghĩa |
|---|---|
| eventId | Một event domain |
| commandId | Một yêu cầu nghiệp vụ từ caller |
| operationId | Một side effect cụ thể, ví dụ charge payment |
| aggregateId + version | Vị trí sự kiện trong vòng đời aggregate |
| consumerName + eventId | Phạm vi dedup cho một logical consumer |

Không dùng offset một mình làm eventId nghiệp vụ: offset chỉ duy nhất trong một partition của một topic. Record có thể được sao chép sang retry topic, DLT hoặc được replay với offset mới.

Nếu processed_events bị xóa sau TTL ngắn, replay cũ có thể bị coi là event mới. Cần chọn retention dedup dựa trên **replay horizon**, các yêu cầu audit và business unique constraints.

Với payment, idempotency key có thể có TTL ở provider. Nếu replay sau TTL, cần query trạng thái hoặc đối chiếu bằng business transaction ID thay vì giả định provider vẫn nhớ key.

## 22. Bảng lựa chọn bảo đảm theo loại side effect

| Luồng | Có thể đạt ở phạm vi nào? | Giải pháp chính |
|---|---|---|
| Kafka input → Kafka output | Kafka EOS cho transaction được hỗ trợ | Transactional producer/container, read_committed |
| Kafka input → Database | Effectively-once DB effect | Transactional inbox + unique constraint |
| Database → Kafka | Không mất ý định phát event sau DB commit | Transactional outbox + publisher/CDC |
| Kafka → DB → Kafka | DB effect idempotent, output eventually published | Inbox + outbox cùng DB transaction |
| Kafka → Payment API | Effectively-once nếu provider hỗ trợ | Stable idempotency key, status lookup |
| Kafka → Email/SMS | Không thể hứa tuyệt đối nếu provider không hỗ trợ | Delivery state, outbox, best-effort policy |
| Kafka → Object storage | Effectively-once object effect theo key | Deterministic key, conditional write |
| Kafka → nhiều external systems | Distributed workflow | Saga, per-step idempotency, compensation |

Chữ **effectively-once** phản ánh rằng attempt/delivery có thể nhiều lần, nhưng side effect cuối cùng được kiểm soát không trùng theo contract đã định.

## 23. Sai lầm thường gặp

**Bật transaction-id-prefix và cho rằng database cũng rollback**

Không. Database và Kafka có transaction managers khác nhau. Spring transaction synchronization không mặc định là distributed XA transaction.

**Bật enable.idempotence=true và cho rằng cùng eventId không bao giờ được gửi hai lần**

Producer idempotence không phải business dedup cho các executions độc lập.

**Gửi Kafka output trong @Transactional(database) và coi hai commit là nguyên tử**

Không có guarantee như vậy nếu không có giao dịch phân tán thực sự. Outbox thường giải quyết mục tiêu không mất event dễ vận hành hơn.

**Ghi processed marker trước khi domain update**

Nếu marker đã commit còn update thất bại, lần retry bỏ qua event. Ghi cả hai trong cùng DB transaction.

**Dùng SELECT rồi INSERT để chống duplicate**

Hai workers có thể cùng vượt qua SELECT. Dùng unique constraint và atomic insert.

**Mỗi retry tạo một UUID mới**

Làm mất khả năng dedup. Giữ operationId từ lần thực thi logic đầu tiên.

**Dùng inbox TTL quá ngắn**

Record cũ replay sau TTL có thể tạo side effect lại.

**Coi DLT đồng nghĩa chưa có side effect**

Record có thể đã gửi payment/email rồi mới thất bại ở bước khác.

**Cho rằng HTTP timeout là request chưa được xử lý**

Payment provider có thể đã commit rồi mất response. Cần status lookup/idempotency.

**Tuyên bố exactly-once end-to-end chỉ từ Kafka metrics**

Phải kiểm tra cả trạng thái database, external API và các workflow steps.

## 24. Kiểm thử crash window

Unit test chỉ gọi trực tiếp listener không đủ để chứng minh distributed reliability. Cần integration tests và fault injection ở các ranh giới commit.

| Vị trí crash/lỗi | Điều cần xác minh |
|---|---|
| Trước DB commit | DB rollback, Kafka redelivery |
| Sau DB commit trước Kafka offset commit | Redelivery không cập nhật DB hai lần |
| Sau outbox insert trước DB commit | Outbox rollback cùng domain |
| Sau DB commit trước outbox publish | Outbox publisher khôi phục được |
| Sau Kafka publish trước mark-sent | Duplicate output được downstream nhận diện |
| Sau payment accepted trước HTTP response | Retry cùng operationId không charge trùng |
| Sau email accepted trước local delivery status | Có chính sách duplicate/missing rõ ràng |
| Sau DLT publish trước offset commit | DLT duplicate không làm replay sai |
| Rebalance khi listener đang xử lý | Consumer mới không lặp side effect |
| Retry topic đảo thứ tự | Version/state guard xử lý event đến muộn |
| Replay sau TTL dedup hết hạn | Có business constraint hoặc quy trình kiểm tra trạng thái |

Với Spring Kafka, có thể dùng Testcontainers Kafka và database integration để tạo các tình huống, kết hợp stub external API có idempotency semantics. Kiểm tra **kết quả nghiệp vụ cuối cùng**, không chỉ số lần listener được gọi.

## 25. Monitoring và reconciliation

Một hệ thống có idempotency vẫn cần quan sát lỗi và bất nhất.

| Tín hiệu | Mục đích |
|---|---|
| Consumer redelivery count | Record bị giao lại bao nhiêu |
| Duplicate rejected count | Inbox/unique constraint đã ngăn bao nhiêu lần xử lý trùng |
| Unique business events applied | Bao nhiêu logical events hoàn tất |
| Outbox pending count và oldest age | Có event chờ publish lâu không |
| Outbox publish failures | Kafka hoặc serializer đang lỗi không |
| Payment unknown outcomes | Request timeout nhưng kết quả chưa rõ |
| API idempotency conflicts | Cùng key nhưng parameters khác nhau |
| DLT backlog/age | Record lỗi tồn đọng |
| Consumer lag | Group có theo kịp topic nguồn không |
| Reconciliation mismatch | Trạng thái giữa DB và external provider không khớp |
| Saga compensation failures | Workflow còn thao tác bù trừ chưa hoàn tất |
| Kafka transaction abort/fencing | Lỗi giao dịch Kafka |

Tránh dùng eventId, paymentId hoặc operationId làm metric label vì cardinality không giới hạn. Có thể ghi chúng trong log có cấu trúc với chính sách bảo vệ dữ liệu nhạy cảm.

**Reconciliation** nghĩa là so sánh trạng thái thực tế, không chỉ dựa vào thông điệp đã gửi. Ví dụ truy vấn payment provider để đối chiếu những đơn hàng PAYMENT_PENDING quá lâu, hoặc kiểm tra các outbox rows pending vượt SLA.

## 26. Checklist thiết kế hệ thống Spring Kafka

- Xác định phạm vi chính xác của từ "exactly once": Kafka output hay business effect.
- Hiểu listener có thể được gọi lại khi crash/rebalance/retry.
- Kafka producer idempotence không bị nhầm với business idempotency.
- Kafka transactions thực sự bao gồm Kafka output và input offsets khi cần Kafka-to-Kafka EOS.
- Downstream cần read_committed được cấu hình đúng.
- Database và external API không bị coi là tự tham gia Kafka transaction.
- Kafka → DB dùng inbox/unique constraint trong cùng DB transaction.
- DB → Kafka dùng transactional outbox hoặc cơ chế tương đương.
- Outbox publisher có thể gửi trùng; downstream có dedup.
- EventId, commandId và operationId ổn định qua retry, restart và replay.
- Payment/API có idempotency key và status lookup nếu khả dụng.
- HTTP timeout có chính sách cho kết quả không xác định.
- Email/SMS có delivery state và hiểu rõ giới hạn provider.
- Object storage có deterministic key/conditional write.
- Workflow nhiều resource có saga và trạng thái bền vững.
- Ordering theo aggregate được bảo vệ bằng version và state transitions.
- Retention dedup đủ dài so với replay horizon.
- DLT/retry không bị xem là chứng minh chưa có side effect.
- Fault-injection test bao phủ crash sau DB commit nhưng trước Kafka offset commit.
- Có monitoring cho duplicate, outbox lag, unknown outcomes và reconciliation.
- Có owner và quy trình xử lý các trạng thái không nhất quán.

**Kết luận:** Kafka EOS là một bảo đảm mạnh cho **những Kafka records và offsets tham gia cùng Kafka transaction**, nhưng không phải một giao dịch phân tán mặc định cho database, HTTP, email hay storage. Trong Spring Kafka, mục tiêu vận hành an toàn là chấp nhận redelivery có thể xảy ra và thiết kế từng side effect sao cho replay không làm sai trạng thái cuối cùng. Transactional inbox/outbox, operation IDs, idempotency, saga và reconciliation là những thành phần quyết định khi hệ thống bước ra ngoài ranh giới Kafka.

