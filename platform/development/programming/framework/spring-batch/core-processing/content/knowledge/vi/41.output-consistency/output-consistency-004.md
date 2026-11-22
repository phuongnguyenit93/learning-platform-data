# Message output và duplicate delivery

Trong Spring Batch, một Step có thể đọc dữ liệu từ database hoặc file, xử lý theo chunk rồi publish message tới Kafka, RabbitMQ, JMS hoặc một hệ thống messaging khác. Một vấn đề quan trọng là message có thể đã được broker nhận nhưng chunk chưa commit. Nếu Job retry hoặc restart, cùng một message có thể được publish lần nữa.

Duplicate delivery không nhất thiết là lỗi của broker. Nó thường xuất hiện từ khoảng thời gian giữa hai thao tác độc lập: gửi message ra ngoài và commit transaction của chunk hoặc JobRepository. Nếu ứng dụng không thể thực hiện hai thao tác đó trong một transaction nguyên tử, crash ở giữa có thể tạo trạng thái không chắc chắn.

Thiết kế output consistency cần hướng tới hai mục tiêu: không mất output khi Job gặp lỗi hoặc restart; và nếu output được gửi lại, consumer không áp dụng hiệu ứng nghiệp vụ nhiều lần.

## 1. Message output trong chunk-oriented Step

Một Job thường chuyển dữ liệu thành event sau khi xử lý:

~~~text
Database / File Reader
        |
        v
ItemProcessor
        |
        v
Chunk of output events
        |
        v
Message ItemWriter
        |
        v
Kafka / RabbitMQ / JMS
~~~

Ví dụ một order chuyển từ trạng thái PAID sang SHIPPED. Processor tạo event OrderShipped và writer publish event đó để các service khác cập nhật dữ liệu của chúng.

Một chunk có thể chứa nhiều event. Writer có thể gửi từng event, gửi theo batch API hoặc dùng producer transaction. Dù cách nào, Spring Batch vẫn cần biết writer hoàn tất hay thất bại để quyết định commit hoặc rollback chunk.

Điểm cần phân biệt là transaction của Step và transaction của broker. Nếu chúng độc lập, việc publish thành công không có nghĩa chunk đã commit; chunk commit cũng không có nghĩa mọi consumer đã xử lý event.

## 2. Vì sao duplicate delivery xảy ra?

Giả sử writer publish event E-100 thành công, nhưng process dừng trước khi chunk transaction commit:

~~~text
1. Reader lấy order 100
2. Processor tạo event E-100
3. Writer publish E-100
4. Broker xác nhận đã nhận E-100
5. Process crash trước chunk commit
6. Spring Batch restart chunk
7. Writer publish lại E-100
~~~

Broker có thể chứa hai bản E-100. Từ góc nhìn writer, lần publish đầu đã thành công. Từ góc nhìn Spring Batch, chunk chưa hoàn tất nên phải xử lý lại.

Một cửa sổ khác là network timeout sau khi broker đã nhận message nhưng trước khi client nhận confirm. Client không biết message đã tới hay chưa. Retry là hợp lý, nhưng message đầu có thể đã tồn tại.

Duplicate cũng có thể xảy ra khi writer gửi một phần chunk rồi lỗi ở event tiếp theo. Khi Spring Batch retry chunk, các event đã gửi trong lần trước có thể được gửi lại.

## 3. Publish thành công khác với chunk commit

Một lời gọi producer trả về thành công thường chỉ chứng minh broker đã nhận hoặc xác nhận publish theo mức bảo đảm của API. Nó không chứng minh transaction database của Step đã commit.

~~~text
Spring Batch chunk transaction
       |
       +--> Writer publish event E1
       |         |
       |         +--> Broker confirm
       |
       +--> Writer publish event E2
       |         |
       |         +--> Broker confirm
       |
       +--> Chunk commit
~~~

Nếu commit thất bại sau khi E1 và E2 đã được broker xác nhận, Spring Batch có thể chạy lại chunk. Nếu broker không tham gia transaction cùng chunk, E1 và E2 vẫn có thể được giao lại.

Ngược lại, nếu writer trả về bình thường trước khi message thực sự được broker xác nhận, chunk có thể commit trong khi publish vẫn đang thất bại ở background. Với message nghiệp vụ quan trọng, writer cần chờ kết quả publish theo semantics phù hợp hoặc ghi outbox bền vững.

Không dùng log "send started" hay việc tạo producer record làm bằng chứng output đã được lưu.

## 4. Các cửa sổ lỗi chính

| Thời điểm crash/lỗi | Trạng thái có thể xảy ra | Hệ quả |
|---|---|---|
| Trước khi publish | Broker chưa nhận event | Chunk có thể chạy lại và gửi lần đầu |
| Trong khi publish, chưa rõ kết quả | Broker có thể đã nhận hoặc chưa | Retry có thể tạo duplicate |
| Broker confirm, trước chunk commit | Event đã ở broker, chunk chưa commit | Restart có thể publish lại |
| Sau chunk commit | Chunk đã hoàn tất | Không nên replay event từ chunk đó |
| Consumer nhận event, trước khi ghi DB consumer | Event có thể được giao lại | Consumer phải xử lý idempotent |
| Consumer DB commit, trước khi ACK | DB đã cập nhật, message có thể redeliver | Inbox/deduplication ngăn hiệu ứng lặp |

Thiết kế phải xử lý các cửa sổ không chắc chắn, đặc biệt là broker đã nhận nhưng caller chưa biết, và database đã commit nhưng acknowledgement chưa hoàn tất.

## 5. At-least-once output là lựa chọn thực tế

Khi publish message quan trọng, hệ thống thường ưu tiên at-least-once:

- Retry nếu không biết publish đã thành công hay chưa.
- Giữ output bền vững cho tới khi có xác nhận phù hợp.
- Chấp nhận broker hoặc consumer có thể thấy cùng event nhiều lần.
- Dùng event ID và deduplication để tránh lặp hiệu ứng nghiệp vụ.

At-most-once có thể tránh duplicate bằng cách không retry sau lỗi không rõ kết quả, nhưng có nguy cơ mất event.

Exactly-once delivery là một tuyên bố rất mạnh và thường không thể bảo đảm xuyên qua nhiều hệ thống độc lập. Mục tiêu thực dụng hơn là exactly-once effect: message có thể được giao nhiều lần nhưng consumer chỉ áp dụng một lần cho mỗi event ID.

## 6. Event ID ổn định

Mỗi message nghiệp vụ nên có ID ổn định, được tạo từ định danh event hoặc operation nguồn. ID phải giữ nguyên qua retry, restart và republish.

Ví dụ event:

~~~json
{
  "eventId": "evt-order-100-ship-1",
  "eventType": "OrderShipped",
  "aggregateId": "order-100",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-15T10:30:00Z",
  "schemaVersion": 1,
  "payload": {
    "orderId": 100,
    "trackingNumber": "TRK-9001"
  }
}
~~~

Nếu writer tạo UUID mới mỗi lần retry, consumer không thể nhận ra hai message là cùng một operation. Event ID cần được tạo trước hoặc được tính tất định từ khóa nghiệp vụ và sequence/version.

Không nên chỉ dùng orderId làm event ID nếu một order có thể phát sinh nhiều event hợp lệ. OrderPaid và OrderShipped phải có ID khác nhau.

## 7. Phân biệt message ID, business key và correlation ID

Các ID có vai trò khác nhau:

| Identifier | Vai trò |
|---|---|
| eventId/messageId | Nhận diện duy nhất một event logic; dùng deduplicate |
| aggregateId/business key | Nhận diện đối tượng nghiệp vụ, ví dụ orderId |
| aggregateVersion/sequence | Xác định thứ tự thay đổi của một aggregate |
| correlationId | Liên kết các message cùng một workflow/request |
| causationId | Chỉ ra event hoặc command đã gây ra event hiện tại |
| batchId/jobExecutionId | Theo dõi event được tạo từ lần chạy batch nào |

Không dùng JobExecution ID làm event ID nếu restart tạo JobExecution mới nhưng cùng một event logic. Event ID phải ổn định xuyên suốt restart.

Correlation ID cũng không thay thế event ID: nhiều event có thể thuộc cùng correlation ID nhưng vẫn là các sự kiện riêng biệt.

## 8. Writer publish theo từng item

Một custom ItemWriter có thể gửi từng event trong chunk:

~~~java
public class OrderEventWriter implements ItemWriter<OrderEvent> {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventWriter(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Override
    public void write(Chunk<? extends OrderEvent> chunk) {
        for (OrderEvent event : chunk) {
            kafkaTemplate.send(
                    "order-events",
                    event.aggregateId(),
                    event);
        }
    }
}
~~~

Đoạn minh họa trên không chờ kết quả send. Một số producer API trả về future; nếu writer trả về ngay, Step có thể commit trước khi biết send có thất bại hay không.

Với output cần được xác nhận trước khi writer hoàn tất, hãy chờ kết quả publish theo API của client hoặc dùng cơ chế transaction/outbox. Cần tránh chờ từng message tuần tự nếu có thể gửi song song trong giới hạn an toàn; nhưng writer vẫn phải quan sát tất cả kết quả trước khi trả về.

Không để exception trong callback bất đồng bộ bị bỏ qua. Lỗi phải được chuyển thành lỗi writer hoặc được lưu bền vững để xử lý lại.

## 9. Chờ producer acknowledgement

Với KafkaTemplate, send thường trả về CompletableFuture trong các phiên bản Spring Kafka hiện đại. Writer có thể chờ future:

~~~java
@Override
public void write(Chunk<? extends OrderEvent> chunk) {
    List<CompletableFuture<SendResult<String, OrderEvent>>> sends =
            new ArrayList<>();

    for (OrderEvent event : chunk) {
        sends.add(kafkaTemplate.send(
                "order-events",
                event.aggregateId(),
                event));
    }

    for (CompletableFuture<?> send : sends) {
        send.join();
    }
}
~~~

Ví dụ cần điều chỉnh kiểu future và exception handling theo Spring Kafka version. Nếu future thất bại, join có thể ném CompletionException; writer cần giữ cause để retry classifier phân loại đúng.

Chờ broker acknowledgement giúp writer không trả về thành công khi send còn pending. Tuy nhiên, nó không giải quyết cửa sổ broker confirm thành công nhưng chunk commit thất bại. Khi đó event vẫn có thể được publish lại.

Producer acknowledgement là một lớp bảo đảm; idempotency/outbox xử lý lớp nhất quán giữa các lần thực thi.

## 10. Kafka producer idempotence

Kafka producer hỗ trợ idempotence để giảm duplicate do retry ở tầng producer protocol. Khi được bật và cấu hình phù hợp, producer dùng producer ID và sequence number để broker nhận diện retry của cùng batch request.

Cấu hình thường dùng:

~~~properties
enable.idempotence=true
acks=all
retries=2147483647
max.in.flight.requests.per.connection=5
~~~

Các giá trị và constraint phụ thuộc phiên bản Kafka client. Với client hiện đại, idempotence có thể được bật mặc định khi cấu hình tương thích. Hãy kiểm tra effective producer config.

Producer idempotence không đồng nghĩa với idempotency của nghiệp vụ:

- Nó xử lý retry protocol của producer trong phạm vi producer session.
- Nó không tự nhận diện cùng event được gửi lại bởi một JobExecution mới hoặc producer instance mới.
- Nó không chống consumer xử lý cùng event nhiều lần do offset/ack/restart.
- Nó không làm database transaction của Spring Batch atomic với Kafka.

Vì vậy, vẫn cần event ID ổn định và consumer deduplication.

## 11. Kafka transaction cho output

Kafka transaction có thể gom nhiều record publish thành một transaction. Consumer cấu hình isolation phù hợp có thể chỉ đọc record thuộc transaction đã commit.

Ví dụ cấu hình producer transaction trong Spring Kafka có thể dùng transactionIdPrefix trên ProducerFactory/KafkaTransactionManager. Step cần được cấu hình để transaction manager quản lý Kafka transaction ở ranh giới phù hợp.

Luồng khái niệm:

~~~text
Begin Kafka transaction
        |
        v
Publish E1, E2, E3
        |
        v
All sends succeed
        |
        v
Commit Kafka transaction
~~~

Nếu lỗi trước commit, Kafka transaction có thể abort và consumer đọc theo read_committed sẽ không thấy các record đã abort.

Điều này hữu ích khi toàn bộ output cần nằm trong Kafka transaction. Nhưng nếu chunk còn ghi database bằng transaction khác, hai resource vẫn chưa atomic với nhau.

## 12. Kafka transaction không tự commit database

Giả sử Step vừa update database vừa publish Kafka event:

~~~text
Database transaction T1
   +--> UPDATE orders

Kafka transaction T2
   +--> publish OrderShipped
~~~

Nếu T1 commit nhưng T2 abort, database thay đổi mà event không xuất hiện. Nếu T2 commit nhưng T1 rollback, event có thể mô tả một thay đổi chưa tồn tại.

Cần transaction coordination thực sự nếu muốn atomic giữa hai resource, chẳng hạn JTA/XA khi cả database, broker, driver và coordinator hỗ trợ. Cách này có chi phí vận hành và recovery đáng kể.

Trong nhiều hệ thống, transactional outbox đơn giản hơn: update database và ghi outbox row trong cùng transaction, sau đó publisher riêng gửi event.

Không gọi Kafka exactly-once semantics là exactly-once cho cả database và broker nếu database không tham gia transaction đó.

## 13. RabbitMQ publisher confirms

RabbitMQ publisher confirms cho phép producer biết broker đã nhận responsibility cho publish theo semantics của broker. Producer nên bật confirm mode và xử lý nack/return.

Cần phân biệt:

- Publisher confirm: broker xác nhận publish đã được xử lý ở phía broker.
- Mandatory return: message không route được tới queue phù hợp có thể được trả lại nếu dùng mandatory publishing và return callback.
- Consumer acknowledgement: consumer xác nhận đã xử lý message.
- Durable queue/message persistence: cấu hình độ bền của queue/message và broker storage.

Confirm không chứng minh consumer đã xử lý message. Nó cũng không tạo transaction chung với database chunk.

Nếu confirm bị timeout, producer không biết message có được nhận hay chưa. Retry có thể tạo duplicate. Dùng message ID ổn định và consumer deduplication.

## 14. RabbitMQ transaction và confirm không giống nhau

RabbitMQ có transaction channel và publisher confirm mode; đây là hai cơ chế khác nhau và không nên hiểu như cùng một guarantee.

Publisher confirms thường phù hợp cho throughput và xác nhận broker đã nhận publish. Channel transaction có chi phí và semantics riêng; nó không tự atomic với database transaction của Spring Batch.

Khi dùng Spring AMQP, cấu hình RabbitTemplate/connection factory và confirm callback theo phiên bản. Writer cần xử lý cả confirm ack, nack, return và timeout theo contract.

Nếu publish đã được broker nhận nhưng confirm bị mất trên network, producer retry có thể gửi lại. Consumer vẫn cần idempotency.

## 15. JMS persistent delivery và transaction

JMS hỗ trợ delivery mode persistent/non-persistent và transacted session. Persistent delivery yêu cầu broker lưu message theo cấu hình và implementation; nó không tự bảo đảm database cùng commit với message.

Một JMS transacted session có thể commit hoặc rollback việc gửi message trong session. Khi dùng cùng Spring Batch, cần xác định transaction manager nào điều khiển session và chunk.

Nếu database và JMS session độc lập, vẫn có cửa sổ lỗi giữa hai commit. JTA/XA có thể phối hợp nếu resource hỗ trợ và được cấu hình đầy đủ; nếu không, outbox/inbox là lựa chọn phổ biến.

Persistent delivery giúp durability của broker sau khi nhận message. Nó không thay thế idempotency ở consumer.

## 16. Partial publish trong một chunk

Giả sử chunk có bốn event:

~~~text
Chunk = [E1, E2, E3, E4]

Publish E1 -> broker confirm
Publish E2 -> broker confirm
Publish E3 -> timeout
Publish E4 -> chưa gửi
~~~

Writer ném exception. Spring Batch rollback chunk và có thể retry. Khi retry, E1 và E2 có thể được gửi lại; E3 có thể đã tới broker dù confirm timeout; E4 được gửi lần đầu.

Do đó, một lần write(chunk) không tự atomic chỉ vì đó là một method call.

Các cách xử lý:

- Dùng Kafka transaction để commit/abort toàn bộ các output Kafka trong chunk nếu phù hợp.
- Dùng outbox để lưu danh sách event bền vững rồi relay.
- Dùng event ID ổn định và consumer deduplication.
- Theo dõi trạng thái publish theo event khi cần đối soát.
- Không giả định writer retry chỉ gửi lại item thất bại.

## 17. Transactional outbox

Outbox lưu event trong database cùng transaction với thay đổi nghiệp vụ. Một publisher riêng đọc outbox và gửi event tới broker.

~~~text
Spring Batch chunk
       |
       +--> Update business table
       |
       +--> Insert outbox event rows
       |
       v
Database COMMIT
       |
       v
Outbox publisher
       |
       +--> Publish event
       |
       +--> Receive broker confirm
       |
       +--> Mark event SENT
~~~

Nếu chunk rollback, cả business update và outbox rows rollback. Nếu chunk commit rồi process dừng, event vẫn nằm trong outbox để publisher xử lý sau.

Đây là cách tách nhất quán database khỏi availability của broker. Writer của Step không cần gọi broker trực tiếp; nó chỉ ghi database transaction.

## 18. Thiết kế bảng outbox

Một bảng outbox có thể chứa:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(200) PRIMARY KEY,
    aggregate_id VARCHAR(200) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(100) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    published_at TIMESTAMP
);
~~~

Các trường quan trọng:

- event_id: idempotency key ổn định.
- aggregate_id: khóa đối tượng nghiệp vụ.
- aggregate_version: thứ tự thay đổi.
- event_type/schema_version: contract của payload.
- payload: nội dung event hoặc reference tới payload.
- status: trạng thái relay.
- created_at/published_at: thời điểm tạo và publish.

Có thể bổ sung retry_count, next_attempt_at, lease_owner, lease_until và last_error. Không lưu secret hoặc dữ liệu nhạy cảm không cần thiết trong payload.

Đặt index phù hợp cho truy vấn pending event, ví dụ status và created_at. Với bảng lớn, cần retention/archive cho event đã gửi.

## 19. Ghi outbox trong cùng chunk transaction

Một writer có thể ghi business entity và outbox event qua cùng transaction/database:

~~~java
public class OrderAndOutboxWriter implements ItemWriter<OrderResult> {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;

    @Override
    public void write(Chunk<? extends OrderResult> chunk) {
        for (OrderResult result : chunk) {
            orderRepository.save(result.toOrder());

            OutboxEvent event = OutboxEvent.from(
                    result.eventId(),
                    result.orderId(),
                    result.toEventPayload());

            outboxRepository.save(event);
        }
    }
}
~~~

Nếu cả hai repository tham gia cùng transaction của Step, business update và outbox row commit hoặc rollback cùng nhau.

Cần tránh một repository dùng REQUIRES_NEW hoặc transaction manager khác ngoài ý muốn. Kiểm tra DataSource, propagation và transaction manager thực tế.

Nếu dùng CompositeItemWriter với hai database delegate, thứ tự có thể là business writer rồi outbox writer; cả hai phải cùng transaction. Nếu outbox writer lỗi, business write cũng rollback.

## 20. Outbox publisher và claim event

Nhiều publisher instance có thể cùng đọc các event PENDING. Cần claim event để tránh hai publisher gửi cùng lúc.

Một số chiến lược:

- SELECT ... FOR UPDATE SKIP LOCKED trong transaction ngắn.
- Update trạng thái thành IN_PROGRESS cùng lease owner và lease expiry.
- Claim theo partition/key.
- Dùng queue hoặc CDC để phát hiện outbox rows.

Ví dụ SQL khái niệm với database hỗ trợ SKIP LOCKED:

~~~sql
SELECT event_id, payload
FROM outbox_event
WHERE status = 'PENDING'
ORDER BY created_at, event_id
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

Cú pháp LIMIT/FOR UPDATE khác nhau theo database. Transaction claim nên ngắn; không giữ row lock trong khi chờ network publish lâu.

Một thiết kế khác là cập nhật lease trong transaction, commit claim, publish bên ngoài transaction, rồi cập nhật SENT sau confirm. Nếu publisher crash, lease hết hạn để event được claim lại.

## 21. Outbox vẫn có thể publish duplicate

Publisher có thể gặp tình huống:

~~~text
1. Claim event E-100
2. Publish E-100
3. Broker confirm
4. Process crash trước khi update status SENT
5. Lease hết hạn
6. Publisher khác claim E-100
7. Publish E-100 lần nữa
~~~

Đây là behavior at-least-once của outbox relay. Không nên đánh dấu SENT trước khi publish vì crash sau khi đánh dấu nhưng trước publish sẽ làm mất event.

Vì không thể luôn biết chắc broker đã nhận khi client mất kết nối, duplicate là lựa chọn an toàn hơn mất message. Consumer cần deduplicate bằng event_id.

Nếu broker transaction/producer idempotence có thể giảm duplicate trong một số cửa sổ, vẫn giữ deduplication ở consumer cho recovery qua process restart.

## 22. Consumer inbox/deduplication

Consumer lưu event ID đã xử lý trong cùng transaction với business update.

~~~sql
CREATE TABLE inbox_event (
    event_id VARCHAR(200) PRIMARY KEY,
    received_at TIMESTAMP NOT NULL
);
~~~

Pseudo-code:

~~~java
@Transactional
public void consume(OrderShipped event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
            event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderProjection.apply(event);
}
~~~

Insert inbox row và cập nhật projection phải cùng transaction. Nếu projection update lỗi, inbox row rollback để message có thể redeliver và thử lại.

Nếu inbox insert commit trước business update, event có thể bị đánh dấu đã xử lý trong khi projection chưa cập nhật.

Với broker manual acknowledgement, chỉ ACK sau transaction commit. Nếu commit thành công nhưng ACK thất bại, message redelivery sẽ bị inbox phát hiện là duplicate và có thể ACK an toàn.

## 23. Idempotent upsert và deduplication

Không phải mọi consumer đều cần bảng inbox riêng. Có thể dùng unique event ID trong bảng kết quả hoặc upsert theo business key nếu operation thực sự idempotent.

Ví dụ một projection ghi trạng thái theo aggregate version:

~~~sql
INSERT INTO order_projection(order_id, status, version)
VALUES (:orderId, :status, :version)
ON CONFLICT (order_id)
DO UPDATE SET
    status = EXCLUDED.status,
    version = EXCLUDED.version
WHERE order_projection.version < EXCLUDED.version;
~~~

Cú pháp trên là PostgreSQL-specific. Ý tưởng là chỉ áp dụng event có version mới hơn.

Idempotent upsert không phù hợp với mọi loại event. Ví dụ cộng thêm 10 điểm thưởng là thao tác không idempotent nếu lặp lại. Với delta event, cần dedup theo event ID trước khi cộng.

Hãy phân loại event:

- State-setting event: đặt trạng thái thành một giá trị, có thể idempotent nếu có version.
- Delta event: cộng/trừ hoặc tạo giao dịch, thường cần dedup theo event ID.
- Command: yêu cầu thực hiện side effect; cần idempotency key và trạng thái command.

## 24. Ordering của message output

Duplicate không phải rủi ro duy nhất. Message có thể đến sai thứ tự, đặc biệt khi nhiều worker publish song song hoặc retry event cũ sau event mới.

Ví dụ:

~~~text
Order 100:
  version 6: OrderPaid
  version 7: OrderShipped

Consumer nhận:
  version 7 trước
  version 6 sau
~~~

Nếu consumer áp dụng version 6 sau version 7, trạng thái có thể bị lùi.

Giải pháp:

- Dùng aggregateId làm partition key để event cùng aggregate đi cùng partition nếu broker hỗ trợ ordering theo partition.
- Đính kèm aggregateVersion hoặc sequence.
- Consumer kiểm tra version trước khi áp dụng.
- Tránh publish song song các event cần thứ tự toàn cục.
- Thiết kế retry/DLQ không làm event cũ chen vào sau event mới mà không được phát hiện.

Kafka chỉ bảo đảm thứ tự trong một partition. RabbitMQ ordering có thể bị ảnh hưởng bởi nhiều consumer, redelivery và requeue. Không giả định thứ tự toàn cục nếu broker không cung cấp guarantee đó.

## 25. Spring Batch partitioning và message order

Nếu Job chạy nhiều partition hoặc worker, mỗi worker có thể publish event đồng thời. Thứ tự giữa các partition không được bảo đảm chỉ vì Job có thứ tự Step.

Nếu event của cùng aggregate cần đúng thứ tự, partition key nên giữ toàn bộ aggregate trong cùng một worker hoặc broker partition. Nếu dữ liệu được chia theo ID range nhưng cùng aggregate có thể xuất hiện ở nhiều range, cần điều chỉnh partition strategy.

Có thể dùng một khóa serialization theo aggregate hoặc consumer version check. Không dùng global lock nếu throughput cao và chỉ một số aggregate cần thứ tự.

Nếu thứ tự chỉ cần trong từng file/batch, hãy giữ sequence number nguồn và kiểm tra consumer có thể phát hiện gap.

## 26. Retry và duplicate trong Spring Batch

Khi writer ném exception, Spring Batch có thể rollback chunk và retry theo policy. Lần retry thường gọi writer cho chunk theo semantics của framework, không biết producer đã gửi thành công event nào trong lần trước.

Ví dụ:

~~~text
Attempt 1:
  E1 publish success
  E2 publish success
  E3 publish timeout
  writer throws

Attempt 2:
  E1 publish again
  E2 publish again
  E3 publish again
~~~

Do đó:

- Event ID không đổi giữa attempts.
- Writer phải truyền lỗi ra ngoài nếu chunk không thể hoàn tất.
- Không tạo event ID mới trong mỗi lần gọi write.
- Consumer cần deduplication.
- Nếu dùng outbox, retry chunk chỉ ghi lại cùng event ID trong transaction; unique constraint giúp tránh duplicate outbox rows.

Retry có giới hạn và backoff. Lỗi validation hoặc schema không nên retry như lỗi network tạm thời.

## 27. Write skip và message output

Skip writer exception có thể khiến một số item không được publish. Điều này chỉ hợp lệ nếu nghiệp vụ cho phép và item bị skip được lưu ở nơi bền vững để xử lý sau.

Không cấu hình skip rộng cho mọi exception khi message output là bắt buộc.

Nếu một item không thể publish:

1. Xác định lỗi permanent hay transient.
2. Retry theo policy nếu lỗi transient.
3. Nếu permanent và được phép loại bỏ, ghi event vào rejected/outbox-failed store.
4. Lưu event ID, payload/reference và nguyên nhân.
5. Chỉ đánh dấu item hoàn tất theo quy tắc nghiệp vụ rõ ràng.
6. Có replay process để publish lại sau khi sửa lỗi.

Không coi log hoặc listener callback là kho rejected event. Nếu rejected storage không ghi được, chunk nên thất bại để giữ khả năng xử lý lại.

## 28. DLQ cho outbound message

DLQ thường được nói tới ở phía consumer, nhưng publisher cũng cần một nơi lưu event không thể gửi sau số lần thử.

Nếu dùng outbox, có thể giữ event ở trạng thái FAILED/DEAD sau retry limit, kèm last_error và next action. Không xóa event khỏi outbox ngay khi publisher hết retry.

~~~text
PENDING
   |
   v
IN_PROGRESS
   |
   +--> confirm --> SENT
   |
   +--> transient failure --> PENDING (retry later)
   |
   +--> permanent / exhausted --> DEAD
                                  |
                                  v
                             Manual replay
~~~

Một event ở DEAD vẫn cần được tra cứu và replay. Chỉ đánh dấu SENT khi broker confirm và routing policy đáp ứng yêu cầu.

Nếu broker xác nhận publish nhưng message bị unroutable, confirm có thể không đủ; với RabbitMQ cần xử lý mandatory return hoặc topology/route validation phù hợp.

## 29. Transaction synchronization và after-commit callback

Có thể đăng ký callback để publish sau khi chunk transaction commit:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                publisher.publish(event);
            }
        });
~~~

Cách này tránh gửi message trước khi transaction commit. Tuy nhiên, callback chạy trong process memory. Nếu database commit xong rồi process crash trước khi callback chạy, event có thể không được publish và không có durable record để khôi phục.

Callback cũng có thể chạy nhưng publish thất bại sau commit; transaction database không thể rollback nữa.

Dùng afterCommit cho tín hiệu phụ có thể tái tạo hoặc không bắt buộc. Với message nghiệp vụ quan trọng, transactional outbox an toàn hơn vì event được lưu bền vững cùng transaction.

## 30. Spring Batch ItemWriter với outbox

Một Step có thể dùng writer ghi outbox thay vì publish trực tiếp:

~~~java
@Bean
public ItemWriter<OrderResult> outboxWriter(
        OrderRepository orderRepository,
        OutboxRepository outboxRepository) {

    return chunk -> {
        for (OrderResult result : chunk) {
            orderRepository.save(result.toOrder());

            OutboxEvent event = OutboxEvent.from(
                    result.eventId(),
                    result.orderId(),
                    result.toPayload());

            outboxRepository.save(event);
        }
    };
}
~~~

Cấu hình Step:

~~~java
@Bean
public Step createOrderEventsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderResult> reader,
        ItemWriter<OrderResult> outboxWriter) {

    return new StepBuilder("createOrderEventsStep", jobRepository)
            .<OrderResult, OrderResult>chunk(100, transactionManager)
            .reader(reader)
            .writer(outboxWriter)
            .build();
}
~~~

Cả business write và outbox write phải dùng cùng transaction manager/resource. Khi chunk rollback, cả hai rollback; khi commit, event được lưu để relay.

Publisher outbox thường chạy như một service/Step riêng, có retry và monitoring riêng. Nó không cần nằm trong transaction của Step tạo event.

## 31. Batch Job chỉ publish ra Kafka

Nếu Job chỉ tạo output Kafka và không ghi database, có thể dùng Kafka transaction manager cho chunk nếu Spring Batch/Spring Kafka version và cấu hình hỗ trợ.

Cần xác định:

- ProducerFactory có transactionIdPrefix.
- KafkaTransactionManager được dùng cho Step.
- Writer dùng KafkaTemplate gắn với ProducerFactory tương ứng.
- Chunk transaction commit/rollback điều khiển Kafka transaction.
- Consumer đọc với isolation phù hợp nếu cần chỉ thấy committed records.
- Restart và offset/reader state không tạo output lặp ngoài transaction.

Đây là pattern khác với outbox. Kafka transaction có thể atomic các output Kafka trong transaction đó, nhưng không bao phủ một database bên ngoài nếu database không tham gia cùng distributed transaction.

Test phải xác nhận record trong transaction abort không được consumer read_committed nhìn thấy.

## 32. Kafka output và consumer isolation

Với Kafka transaction, consumer có thể dùng isolation.level=read_committed để chỉ đọc record thuộc transaction đã commit. Nếu dùng read_uncommitted, consumer có thể nhìn thấy record từ transaction bị abort trước khi transaction hoàn tất.

Ví dụ cấu hình:

~~~properties
isolation.level=read_committed
~~~

Đây là cấu hình consumer, không phải producer. Nó chỉ áp dụng trong phạm vi Kafka transaction semantics.

Nếu producer gửi record non-transactional, record vẫn được đọc bình thường. Nếu hệ thống dùng nhiều topic/partition, transaction commit marker và consumer behavior cần được kiểm tra theo Kafka version.

Read committed không deduplicate event được publish lại trong hai transaction khác nhau. Nếu Job restart tạo một transaction mới và publish lại cùng event ID, consumer vẫn có thể nhận cả hai; cần deduplication nghiệp vụ.

## 33. RabbitMQ publisher reliability

Với RabbitMQ, writer cần phân biệt confirm, return và routing:

- Confirm ACK: broker xác nhận publish theo protocol.
- Confirm NACK: broker từ chối/không thể xác nhận thành công.
- Return: message không route được khi dùng mandatory.
- Timeout/connection loss: kết quả có thể không rõ.
- Persistent message và durable queue: hỗ trợ durability sau restart theo cấu hình broker.

Không đánh dấu output SENT chỉ vì basicPublish không ném exception. Cần chờ confirm và xử lý unroutable return nếu yêu cầu message phải vào queue.

Nếu confirm timeout, retry với cùng message ID; consumer deduplication xử lý trường hợp lần publish trước đã tới broker.

## 34. Message schema và version

Duplicate delivery cần giữ cùng nội dung logic. Nếu cùng event ID nhưng payload thay đổi giữa retry, consumer có thể nhận hai bản khác nhau với cùng ID và không biết bản nào đúng.

Tạo event payload một cách deterministic hoặc lưu payload trong outbox trước khi publish. Không tái tạo event từ entity đã thay đổi sau restart mà vẫn dùng event ID cũ nếu nội dung có thể khác.

Nên có:

- eventType.
- schemaVersion.
- occurredAt.
- eventId.
- aggregateId.
- aggregateVersion.
- payload.

Schema evolution cần quy tắc tương thích. Consumer có thể nhận event cũ sau khi deploy phiên bản mới; giữ deserializer tương thích và có migration/replay policy.

## 35. Retention và replay

Broker retention hoặc queue TTL ảnh hưởng khả năng replay. Event đã publish có thể bị xóa theo retention trước khi consumer phục hồi.

Với outbox, lưu event đủ lâu để publisher retry và đối soát. Sau khi SENT, có thể archive theo policy nhưng không xóa quá sớm nếu cần audit/replay.

Cần xác định:

- Thời gian broker giữ message.
- Thời gian outbox giữ event.
- Thời gian inbox giữ deduplication key.
- Quy trình replay sau DLQ.
- Cách xử lý event cũ tới sau event mới.
- Cách khôi phục từ archive khi retention đã hết.

Nếu inbox record bị xóa trước khi message cũ được replay, consumer có thể áp dụng lại event. Deduplication retention phải lớn hơn cửa sổ replay tối đa hoặc có quy tắc version/sequence bảo vệ.

## 36. Monitoring duplicate và output consistency

Theo dõi cả batch và broker:

| Metric | Ý nghĩa |
|---|---|
| events_created | Số event logic được tạo |
| outbox_pending | Số event chờ publish |
| outbox_oldest_age | Tuổi event pending lâu nhất |
| publish_attempts | Số lần thử publish |
| publish_confirmed | Số publish được broker xác nhận |
| publish_nacks | Số publish bị từ chối |
| publish_timeouts | Số lần không rõ kết quả |
| duplicate_publish_detected | Số event ID được publish lại |
| consumer_duplicate_count | Số event bị inbox deduplicate |
| consumer_lag | Độ trễ consumer |
| dead_event_count | Số event bị chuyển DEAD |
| chunk_rollback_count | Số chunk rollback |

Log nên có eventId, aggregateId, aggregateVersion, batchId, JobExecution ID và outbox row ID. Không log payload nhạy cảm.

Một chỉ số hữu ích là tuổi của outbox PENDING lâu nhất. Nó phát hiện publisher dừng hoặc broker không khả dụng trước khi backlog quá lớn.

## 37. Kiểm thử duplicate khi writer lỗi

Một integration test cần tái tạo cửa sổ broker publish thành công nhưng chunk rollback:

1. Tạo một chunk có E1 và E2.
2. Writer publish E1 và E2, broker confirm thành công.
3. Cố ý ném exception trước khi chunk commit.
4. Xác nhận Step rollback.
5. Restart cùng JobInstance hoặc retry chunk.
6. Xác nhận event ID vẫn là E1/E2.
7. Consumer nhận các bản duplicate.
8. Inbox/unique key chỉ áp dụng mỗi event một lần.

Nếu dùng Kafka transaction, test cần xác nhận transaction abort không để lại visible output cho consumer read_committed. Nếu dùng outbox, test cần xác nhận rollback không tạo outbox row và commit tạo đúng event rows.

## 38. Kiểm thử crash sau confirm trước khi đánh dấu SENT

Với outbox publisher:

~~~text
1. Claim E-100
2. Publish E-100
3. Broker confirm
4. Kill publisher trước update SENT
5. Lease hết hạn
6. Publisher mới claim E-100
7. Publish E-100 lại
8. Consumer deduplicate eventId
~~~

Test phải chứng minh:

- Outbox row không bị mất.
- Event có thể publish lại.
- Event ID giữ nguyên.
- Consumer business effect chỉ xảy ra một lần.
- Trạng thái SENT cuối cùng được lưu.
- Retry và lease không làm hai publisher cùng gửi không kiểm soát.

Đây là test quan trọng hơn việc chỉ mock producer và kiểm tra send() được gọi một lần.

## 39. Kiểm thử ordering

Tạo hai event cùng aggregate với version 1 và 2. Cho publisher/consumer xử lý có độ trễ để cố ý làm version 2 tới trước.

Xác nhận consumer:

- Nhận biết version cũ.
- Không ghi đè trạng thái mới bằng event cũ.
- Có thể buffer/retry event bị thiếu version nếu nghiệp vụ yêu cầu.
- Ghi nhận gap để đối soát.
- Không áp dụng duplicate version hai lần.

Nếu hệ thống yêu cầu strict ordering, test với partition key hoặc serialization mechanism thật. Unit test list order không chứng minh broker delivery order trong môi trường nhiều worker.

## 40. Những lỗi thường gặp

### Cho rằng send() thành công nghĩa là chunk đã commit

Broker confirm và transaction commit là hai mốc khác nhau. Crash giữa chúng có thể tạo duplicate.

### Không chờ producer future/confirm

Step có thể commit trước khi publish thất bại. Writer phải quan sát kết quả hoặc dùng outbox.

### Tạo event ID mới mỗi lần retry

Consumer không nhận ra cùng event. ID phải ổn định qua retry và restart.

### Chỉ bật Kafka producer idempotence rồi bỏ deduplication

Idempotence không chống mọi lần resend từ Job restart hoặc producer instance mới. Consumer vẫn cần idempotency.

### Dùng Kafka transaction để tuyên bố database cũng atomic

Kafka transaction chỉ quản lý resource Kafka trừ khi có coordination phù hợp. Dùng outbox hoặc XA khi cần.

### Đánh dấu outbox SENT trước khi publish

Crash giữa update và send làm mất event. Publish/confirm trước rồi mới đánh dấu SENT; chấp nhận duplicate nếu crash ở khoảng giữa.

### Xóa outbox event ngay sau confirm

Có thể mất khả năng audit/replay. Dùng retention/archive phù hợp.

### Không xử lý RabbitMQ return hoặc nack

Confirm không bảo đảm message đã route đúng queue. Kiểm tra return/nack/timeout.

### Publish từng phần chunk rồi retry toàn bộ

Event trước có thể bị gửi lại. Dùng event ID ổn định và consumer deduplication.

### Publish trong afterCommit callback rồi coi là durable

Process có thể crash trước callback hoặc publish lỗi sau commit. Dùng outbox cho event quan trọng.

### Không giữ ordering theo aggregate

Event cũ có thể tới sau event mới. Dùng partition key, version và consumer guard.

### Xóa inbox deduplication record quá sớm

Replay message cũ có thể tạo business effect trùng. Giữ dedup key đủ lâu hoặc dùng version/sequence.

## 41. Quy trình thiết kế message output nhất quán

Trước khi triển khai writer publish message, hãy xác định:

1. Output được gửi tới Kafka, RabbitMQ, JMS hay broker nào?
2. Writer chờ confirm/ack từ broker hay chỉ enqueue bất đồng bộ?
3. Chunk commit có cùng transaction với broker không?
4. Nếu broker confirm nhưng chunk commit thất bại, event được gửi lại thế nào?
5. Nếu confirm timeout, làm sao xử lý kết quả không rõ?
6. Event ID có ổn định qua retry và restart không?
7. Producer idempotence có được bật và giới hạn của nó là gì?
8. Có cần transactional outbox không?
9. Outbox publisher claim/lease và retry ra sao?
10. Consumer lưu inbox/dedup key cùng business update không?
11. Event có aggregate version và partition key để giữ ordering không?
12. Retry/skip có giới hạn và DLQ/rejected store không?
13. Retention của broker, outbox và inbox có đủ cho replay không?
14. Metrics có theo dõi pending age, publish confirm, timeout và duplicate không?
15. Integration test có mô phỏng crash sau confirm, chunk rollback, restart và duplicate delivery không?

Message output trong Spring Batch có thể bị gửi trùng khi broker đã nhận event nhưng chunk chưa commit, hoặc khi producer không nhận được confirm và phải retry. Không nên cố loại bỏ mọi duplicate bằng cách bỏ retry vì điều đó có thể làm mất output. Hãy dùng event ID ổn định, xác nhận publish đúng semantics của broker, giữ output bền vững bằng transactional outbox khi database và broker độc lập, rồi deduplicate ở consumer bằng inbox hoặc unique business operation key. Nếu chỉ dùng Kafka transaction, giới hạn guarantee trong phạm vi Kafka và kiểm thử read_committed. Kết hợp ordering/version, retry có giới hạn, retention và crash-window integration tests để mỗi event tạo hiệu ứng nghiệp vụ đúng một lần dù message có thể được giao nhiều lần.
