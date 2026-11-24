# Mẫu transactional outbox và tích hợp bộ chuyển tiếp sự kiện

Một dịch vụ Spring thường phải cập nhật dữ liệu nghiệp vụ trong cơ sở dữ liệu rồi phát sự kiện để các dịch vụ khác biết thay đổi đó. Ví dụ, khi tạo đơn hàng, dịch vụ đơn hàng vừa ghi đơn hàng vào database vừa phát OrderCreated lên Kafka, RabbitMQ hoặc Pulsar. Nếu hai thao tác này được thực hiện độc lập, hệ thống có thể rơi vào trạng thái database đã commit nhưng message chưa được gửi, hoặc message đã được gửi nhưng database rollback.

Transactional outbox giải quyết khoảng trống này bằng cách ghi dữ liệu nghiệp vụ và bản ghi sự kiện vào cùng một transaction database. Một bộ chuyển tiếp (relay) đọc các bản ghi outbox đã commit rồi gửi chúng tới broker. Vì database transaction không bao trùm broker một cách tự động, relay có thể gửi lại khi kết quả không chắc chắn; do đó consumer cần idempotency để xử lý an toàn message trùng.

Trong hệ sinh thái Spring, Spring Boot quản lý transaction và cấu hình ứng dụng, Spring Data có thể lưu outbox, còn Spring Cloud Stream cung cấp binding và binder để relay gửi sự kiện tới Kafka, RabbitMQ hoặc broker khác có binder tương thích. Bài học này trình bày cách thiết kế bảng outbox, ghi sự kiện cùng transaction nghiệp vụ, xây dựng relay bằng polling hoặc CDC, xử lý retry và thứ tự, tích hợp với Spring Cloud Stream, kiểm thử và vận hành.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích lỗi dual-write khi cập nhật database và gửi message bằng hai thao tác độc lập.
- Thiết kế bảng outbox lưu event ID, aggregate, schema, payload và trạng thái gửi.
- Ghi dữ liệu nghiệp vụ cùng bản ghi outbox trong một transaction.
- So sánh relay polling với Change Data Capture (CDC).
- Dùng Spring Cloud Stream hoặc StreamBridge để gửi sự kiện từ relay tới destination.
- Thiết kế claim, lease, retry và phục hồi khi relay dừng giữa chừng.
- Bảo toàn thứ tự theo aggregate và hiểu giới hạn của partition key.
- Kết hợp outbox với inbox/idempotent consumer để xử lý giao nhận ít nhất một lần.
- Kiểm thử transaction, relay, broker failure và khả năng phát lại.

## 1. Vấn đề dual-write

Giả sử một dịch vụ tạo đơn hàng bằng hai thao tác:

1. Lưu đơn hàng vào database.
2. Gửi sự kiện OrderCreated tới broker.

Một đoạn code đơn giản có thể trông như sau:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.from(command));
    streamBridge.send("orders-out-0", toMessage(order));
}
~~~

Annotation Transactional chỉ quản lý transaction mà transaction manager của database điều khiển. Lời gọi gửi message tới broker không tự động trở thành một phần của transaction database. Vì vậy, có hai cửa sổ lỗi:

| Trình tự | Kết quả có thể xảy ra |
|---|---|
| Database commit thành công, broker gửi thất bại | Đơn hàng tồn tại nhưng dịch vụ khác không nhận OrderCreated |
| Broker nhận message, database rollback | Dịch vụ khác xử lý một đơn hàng chưa được tạo thành công |
| Broker đã nhận nhưng producer timeout trước khi biết kết quả | Relay hoặc ứng dụng có thể gửi lại, tạo message trùng |
| Ứng dụng dừng giữa hai thao tác | Kết quả phụ thuộc thao tác nào đã hoàn tất |

Đây là dual-write problem: hai hệ thống lưu trữ độc lập cần được cập nhật như một thay đổi nghiệp vụ nhưng không có một transaction nguyên tử bao trùm cả hai.

Có thể dùng distributed transaction trong một số kiến trúc, nhưng việc phối hợp transaction giữa database và broker làm tăng độ phức tạp, phụ thuộc hỗ trợ của từng hệ thống và ảnh hưởng tới khả năng vận hành. Transactional outbox là một mẫu phổ biến để loại bỏ khoảng trống giữa việc commit dữ liệu nghiệp vụ và việc ghi nhận ý định phát sự kiện.

## 2. Nguyên lý transactional outbox

Thay vì gửi message trực tiếp trong transaction nghiệp vụ, ứng dụng ghi một bản ghi outbox:

~~~text
Một transaction database:
  1. INSERT đơn hàng
  2. INSERT sự kiện OrderCreated vào outbox
  3. COMMIT

Relay chạy riêng:
  1. Đọc các outbox event đã commit
  2. Gửi event tới broker
  3. Đánh dấu event đã phát sau khi có xác nhận phù hợp
~~~

Hai bản ghi được commit cùng nhau. Nếu transaction rollback, cả đơn hàng và outbox event đều không tồn tại. Nếu transaction commit, event được lưu bền vững trong database để relay có thể gửi sau, kể cả khi broker tạm thời không sẵn sàng.

Transactional outbox không khiến database và broker cùng commit trong một transaction phân tán. Nó đảm bảo rằng ứng dụng không thể commit thay đổi nghiệp vụ mà quên ghi lại sự kiện cần phát. Relay chịu trách nhiệm chuyển sự kiện đã lưu sang broker.

~~~mermaid
flowchart TD
    A[Request tạo đơn hàng] --> B[Database transaction]
    B --> C[INSERT Order]
    B --> D[INSERT Outbox Event]
    C --> E[COMMIT cùng transaction]
    D --> E
    E --> F[Outbox Relay]
    F --> G[Publish qua Spring Cloud Stream]
    G --> H[(Kafka / RabbitMQ / Pulsar)]
    H --> I[Consumer]
    I --> J[Idempotent xử lý nghiệp vụ]
~~~

## 3. Thiết kế bảng outbox

Một bảng outbox cần lưu đủ thông tin để relay có thể gửi lại sự kiện mà không phải tái tạo payload từ trạng thái hiện tại của aggregate.

Ví dụ schema cho PostgreSQL:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(160) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_by VARCHAR(120),
    locked_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    last_error TEXT,
    CONSTRAINT outbox_status_check
        CHECK (status IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'FAILED'))
);

CREATE INDEX outbox_pending_idx
    ON outbox_event (next_attempt_at, created_at)
    WHERE status = 'PENDING';

CREATE INDEX outbox_lease_idx
    ON outbox_event (locked_until)
    WHERE status = 'PROCESSING';

CREATE UNIQUE INDEX outbox_aggregate_version_idx
    ON outbox_event (aggregate_type, aggregate_id, aggregate_version)
    WHERE aggregate_version IS NOT NULL;
~~~

Các trường quan trọng:

| Trường | Vai trò |
|---|---|
| event_id | ID ổn định, duy nhất cho một sự kiện |
| aggregate_type, aggregate_id | Xác định aggregate phát sinh sự kiện |
| aggregate_version | Phiên bản hoặc thứ tự sự kiện trong aggregate |
| event_type | Tên loại sự kiện, ví dụ OrderCreated |
| schema_version | Phiên bản hợp đồng payload |
| payload | Snapshot dữ liệu sự kiện đã được serialize |
| occurred_at | Thời điểm sự kiện xảy ra theo nghiệp vụ |
| status | Trạng thái xử lý của relay |
| attempts, next_attempt_at | Số lần thử và thời điểm được thử tiếp |
| locked_by, locked_until | Lease cho worker đang xử lý |
| published_at | Thời điểm relay ghi nhận sự kiện đã phát |
| last_error | Thông tin lỗi gần nhất để điều tra |

Schema trên là một thiết kế tham khảo. Hệ quản trị database, quy mô lưu trữ, cách dùng CDC và yêu cầu kiểm toán có thể dẫn đến cấu trúc khác. Ví dụ, nếu dùng CDC, có thể không cần cập nhật status từng bản ghi như polling relay; connector theo dõi log transaction và offset riêng.

### 3.1. Lưu snapshot sự kiện

Payload nên biểu diễn dữ liệu cần thiết tại thời điểm sự kiện xảy ra. Không nên chỉ lưu aggregate ID rồi để relay tải lại entity hiện tại để tạo event, vì entity có thể đã thay đổi trước khi relay chạy.

Ví dụ, OrderCreated cần chứa orderId, customerId, tổng tiền và currency tại thời điểm tạo. Nếu relay đọc lại đơn hàng sau đó, có thể lấy nhầm trạng thái đã được cập nhật hoặc bị xóa.

Sự kiện nên được xem là bất biến sau khi transaction nghiệp vụ commit. Nếu payload cần thay đổi, hãy phát một sự kiện mới hoặc áp dụng một chiến lược migration/schema version có chủ đích.

### 3.2. Event ID và aggregate version

event_id nhận diện một lần phát sinh sự kiện và phải giữ nguyên khi relay retry. Không tạo event ID mới cho mỗi lần gửi lại, vì consumer sẽ không nhận ra đây là cùng một sự kiện.

aggregate_version có thể dùng để kiểm tra thứ tự sự kiện theo aggregate. Ví dụ, OrderCreated có version 1, PaymentAuthorized có version 2 và OrderShipped có version 3. Consumer có thể phát hiện event đến sai thứ tự hoặc bị thiếu version.

Không phải mọi domain đều cần version riêng. Nếu có yêu cầu thứ tự nghiêm ngặt, cần định nghĩa rõ cách cấp version trong cùng transaction cập nhật aggregate.

## 4. Ghi outbox cùng transaction nghiệp vụ

Service nghiệp vụ thực hiện hai thao tác database trong cùng transaction: lưu aggregate và lưu event vào outbox.

~~~java
@Service
class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;

    OrderApplicationService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public void createOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(Order.create(command));

        OrderCreated event = new OrderCreated(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                order.getTotal(),
                Instant.now());

        outboxRepository.save(OutboxEvent.pending(
                event.eventId(),
                "Order",
                order.getId(),
                order.getVersion(),
                "OrderCreated",
                1,
                writeJson(event),
                event.occurredAt()));
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize outbox event", ex);
        }
    }
}
~~~

Các lớp Order, OrderCreated và OutboxEvent trong ví dụ là mô hình minh họa. Điểm cốt lõi là cả orderRepository.save và outboxRepository.save tham gia cùng một transaction manager database. Nếu serialize event thất bại, transaction phải rollback để không tạo đơn hàng mà thiếu outbox event.

Không gọi StreamBridge.send trong transaction này với kỳ vọng rằng database và broker sẽ cùng rollback. Relay phải chạy sau khi outbox row đã commit.

### 4.1. Đặt ranh giới transaction rõ ràng

Một transaction chỉ nên thực hiện thao tác database cần thiết để bảo đảm tính nhất quán của aggregate và outbox row. Không giữ database transaction mở trong lúc chờ broker hoặc gọi mạng.

Lý do:

- Giao dịch dài giữ lock lâu và làm tăng contention.
- Broker chậm có thể kéo dài transaction database.
- Timeout của broker và timeout database có thể không đồng bộ.
- Việc rollback database không thể thu hồi message mà broker đã nhận.

Vì vậy, relay thường có ít nhất hai ranh giới transaction: transaction claim bản ghi, sau đó gửi message ngoài transaction; cuối cùng transaction khác cập nhật trạng thái gửi hoặc lịch retry.

## 5. Tích hợp relay với Spring Cloud Stream

Relay đọc outbox event và phát message tới output binding. Spring Cloud Stream cho phép ứng dụng gửi message động bằng StreamBridge hoặc dùng một hàm producer đã được bind.

### 5.1. Khai báo output binding

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.events
          content-type: application/json
~~~

Với Kafka binder, destination thường ánh xạ tới topic. Với Rabbit binder, binder ánh xạ destination tới exchange và các queue/binding theo cấu hình. Binder khác có thể dùng tài nguyên tương ứng của broker đó.

### 5.2. Gửi message bằng StreamBridge

Ví dụ relay gửi một outbox event:

~~~java
@Component
class StreamBridgeEventPublisher {

    private final StreamBridge streamBridge;

    StreamBridgeEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean send(OutboxEvent event) {
        Message<String> message = MessageBuilder
                .withPayload(event.payload())
                .setHeader("eventId", event.eventId().toString())
                .setHeader("eventType", event.eventType())
                .setHeader("aggregateId", event.aggregateId())
                .setHeader("schemaVersion", event.schemaVersion())
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .build();

        return streamBridge.send("orders-out-0", message);
    }
}
~~~

StreamBridge hữu ích khi destination được chọn trong runtime hoặc khi relay gửi các loại sự kiện qua binding đã cấu hình. Nếu ứng dụng chỉ có một output binding cố định, có thể dùng Supplier/Function để biểu diễn nguồn phát theo mô hình hàm.

**Lưu ý về xác nhận gửi:** giá trị boolean từ StreamBridge.send cho biết message đã được gửi vào channel của ứng dụng theo API đó. Không được mặc định rằng true đồng nghĩa broker đã lưu message bền vững hoặc đã xác nhận publish. Cách nhận kết quả gửi cuối cùng phụ thuộc binder và producer client. Nếu trạng thái PUBLISHED của outbox phải có nghĩa broker đã xác nhận, adapter xuất bản cần chờ hoặc quan sát cơ chế confirmation/acknowledgement phù hợp với binder đang dùng.

### 5.3. Tách hợp đồng publisher khỏi relay

Để relay không phụ thuộc chi tiết của từng broker, có thể định nghĩa một interface:

~~~java
public interface OutboxEventPublisher {
    void publishAndConfirm(OutboxEvent event);
}
~~~

Hợp đồng publishAndConfirm chỉ hoàn tất bình thường khi adapter đã đạt mức xác nhận mà ứng dụng yêu cầu. Nếu không thể xác định kết quả, adapter cần ném lỗi hoặc trả về trạng thái chưa xác định để relay không đánh dấu event là PUBLISHED một cách tùy tiện.

Các implementation có thể dùng Kafka producer callback/future, publisher confirm của RabbitMQ hoặc API tương ứng của Pulsar. Khi dùng Spring Cloud Stream, cần xem khả năng expose producer result của binder và phiên bản cụ thể; không giả định một API confirmation chung giống nhau trên mọi binder.

## 6. Xây dựng polling relay

Polling relay định kỳ tìm outbox row đang chờ, claim một batch, gửi từng event rồi cập nhật kết quả. Mẫu này dễ triển khai với Spring Data/JDBC và hoạt động với nhiều loại broker.

### 6.1. Claim bằng lease

Nếu nhiều relay instance cùng đọc một bảng outbox, chúng cần phối hợp để không cùng xử lý một bản ghi. Có thể dùng row lock và SKIP LOCKED trong PostgreSQL, sau đó cập nhật trạng thái PROCESSING và lease.

Ví dụ SQL:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_event
    WHERE
        (status = 'PENDING' AND next_attempt_at <= now())
        OR
        (status = 'PROCESSING' AND locked_until < now())
    ORDER BY created_at
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_event AS event
SET status = 'PROCESSING',
    locked_by = :worker_id,
    locked_until = :lease_until,
    attempts = event.attempts + 1
FROM candidates
WHERE event.event_id = candidates.event_id
RETURNING event.*;
~~~

Đoạn SQL minh họa cơ chế claim theo cú pháp PostgreSQL. Toàn bộ câu lệnh phải chạy trong một transaction ngắn và commit trước khi relay gửi message. SKIP LOCKED cho phép worker khác lấy các hàng chưa bị khóa thay vì phải chờ worker đầu tiên.

Lease có thời hạn giúp phục hồi khi worker chết sau khi claim. Khi lease hết hạn, một worker khác có thể claim lại bản ghi PROCESSING. Thời hạn lease cần dài hơn thời gian xử lý thông thường hoặc được gia hạn khi tác vụ kéo dài.

### 6.2. Gửi ngoài transaction claim

Luồng xử lý nên có ba giai đoạn:

1. Claim batch trong transaction A và commit.
2. Gửi message tới broker ngoài transaction A.
3. Với mỗi event, mở transaction B để đánh dấu PUBLISHED hoặc lên lịch retry.

Ví dụ phác thảo:

~~~java
@Component
class OutboxRelay {

    private final OutboxClaimService claimService;
    private final OutboxEventPublisher publisher;
    private final OutboxStateService stateService;

    OutboxRelay(
            OutboxClaimService claimService,
            OutboxEventPublisher publisher,
            OutboxStateService stateService) {
        this.claimService = claimService;
        this.publisher = publisher;
        this.stateService = stateService;
    }

    @Scheduled(fixedDelay = 500)
    public void relayBatch() {
        List<OutboxEvent> events = claimService.claimBatch(100);

        for (OutboxEvent event : events) {
            try {
                publisher.publishAndConfirm(event);
                stateService.markPublished(event.eventId());
            } catch (Exception ex) {
                stateService.scheduleRetry(event.eventId(), ex);
            }
        }
    }
}
~~~

Các service claimService và stateService nên quản lý transaction riêng. Không đặt một transaction bao quanh toàn bộ phương thức relayBatch nếu điều đó khiến database lock được giữ trong suốt thời gian chờ broker.

Đây là skeleton kiến trúc, không phải một implementation hoàn chỉnh. Cần thêm giới hạn thời gian, xử lý lease, logging, metrics, shutdown và chính sách retry. Nếu publisher không thể xác định broker đã nhận message hay chưa, relay phải coi kết quả là không chắc chắn và cho phép retry; consumer sẽ loại bỏ tác động trùng bằng event ID.

### 6.3. Vì sao cần lease?

Giả sử worker A claim một event rồi process bị dừng trước khi gửi. Nếu bản ghi mãi ở PROCESSING, event không bao giờ được gửi. Lease cho phép worker B nhận lại event sau khi locked_until hết hạn.

Lease cũng cần tránh tình huống worker A xử lý quá lâu trong khi worker B đã claim lại. Có thể dùng lease đủ dài, gia hạn định kỳ hoặc fencing token/version cho mỗi lần claim. Khi cập nhật trạng thái, worker cần kiểm tra locked_by hoặc claim token vẫn thuộc về mình để worker cũ không ghi đè kết quả của worker mới.

## 7. Delivery semantics: ít nhất một lần và message trùng

Outbox relay thường cung cấp giao nhận ít nhất một lần (at-least-once), vì có thể xảy ra tình huống:

1. Relay gửi event và broker đã nhận.
2. Relay dừng trước khi cập nhật outbox row thành PUBLISHED.
3. Lease hết hạn và worker khác gửi lại cùng event.

Message được phát hai lần dù broker chỉ lưu một lần ở lần đầu. Đây là hệ quả của việc relay không thể nguyên tử hóa publish với transaction database.

Không nên cố giải quyết bằng cách đánh dấu PUBLISHED trước khi gửi. Cách đó tạo nguy cơ mất event nếu relay dừng sau khi commit trạng thái nhưng trước khi broker nhận message.

Thiết kế đúng là chấp nhận duplicate có kiểm soát:

- Giữ event_id ổn định qua mọi lần retry.
- Consumer có bảng inbox hoặc processed-event để phát hiện event đã xử lý.
- Ghi dấu event ID và cập nhật dữ liệu nghiệp vụ trong cùng transaction consumer.
- Chỉ ack/commit message sau khi transaction consumer thành công theo cơ chế binder.

## 8. Idempotent consumer và inbox pattern

Inbox pattern bổ sung một bảng ghi nhận event đã xử lý:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer dùng event ID để bảo đảm cùng một consumer không áp dụng tác động nghiệp vụ hai lần:

~~~java
@Transactional
public void handle(OrderCreated event) {
    boolean firstDelivery = processedEventRepository.insertIfAbsent(
            "billing-service", event.eventId());

    if (!firstDelivery) {
        return;
    }

    billingService.createInvoice(event.orderId(), event.total());
}
~~~

insertIfAbsent cần được triển khai bằng thao tác nguyên tử, ví dụ INSERT ... ON CONFLICT DO NOTHING và kiểm tra số hàng được thêm. Nếu event ID đã tồn tại, consumer bỏ qua tác động nghiệp vụ.

Việc ghi processed_event và cập nhật invoice phải nằm trong cùng transaction database. Nếu transaction rollback, dấu inbox cũng rollback, cho phép message được giao lại và xử lý lại. Nếu commit thành công, message trùng sẽ bị nhận diện.

Inbox không tự bảo đảm exactly-once cho side effect bên ngoài database, chẳng hạn gửi email hoặc gọi API thanh toán. Những side effect đó cần idempotency key, outbox tiếp theo hoặc một cơ chế phối hợp phù hợp.

## 9. Bảo toàn thứ tự theo aggregate

Outbox table có thể chứa nhiều sự kiện cho cùng một aggregate. Nếu relay có nhiều worker hoặc gửi song song, event version 2 có thể tới broker trước version 1.

Ví dụ:

~~~text
Order 100:
  version 1: OrderCreated
  version 2: PaymentAuthorized
  version 3: OrderShipped
~~~

Nếu thứ tự này quan trọng, cần bảo đảm:

- Gán aggregate_version trong transaction cập nhật aggregate.
- Relay không gửi event mới hơn khi event cũ hơn của cùng aggregate chưa được xác nhận.
- Partition key của broker là aggregate_id để sự kiện cùng aggregate đi vào cùng partition hoặc queue partition.
- Consumer xử lý tuần tự trong phạm vi key khi nghiệp vụ yêu cầu.

Kafka: dùng aggregate_id làm record key hoặc partition key theo cấu hình binder để các sự kiện của aggregate được gửi về cùng partition. Kafka giữ thứ tự record trong partition, nhưng consumer xử lý song song có thể làm thứ tự hoàn tất khác thứ tự đọc.

RabbitMQ: dùng routing/partition key phù hợp với queue phân vùng của Rabbit binder. Queue có thứ tự nhận message, nhưng nhiều consumer, prefetch, redelivery và thời gian xử lý khác nhau có thể làm thứ tự hoàn tất không còn như mong muốn.

Một chiến lược đơn giản cho polling relay là chỉ claim event đầu tiên chưa publish của mỗi aggregate. Các event tiếp theo chỉ đủ điều kiện khi mọi version trước đã PUBLISHED. Cách này giảm song song giữa event cùng aggregate nhưng cho phép các aggregate khác nhau được xử lý đồng thời.

## 10. Retry, backoff và sự kiện lỗi lâu dài

Relay cần phân loại lỗi:

| Loại lỗi | Ví dụ | Hành động |
|---|---|---|
| Tạm thời | Broker timeout, mất kết nối ngắn hạn | Retry với backoff |
| Quá tải | Broker từ chối hoặc producer bị throttling | Backoff, giảm batch hoặc tốc độ gửi |
| Cấu hình | Credentials sai, destination không tồn tại | Cảnh báo và sửa cấu hình |
| Payload/schema | JSON không hợp lệ hoặc schema không tương thích | Cách ly, điều tra và sửa dữ liệu |
| Không xác định | Timeout sau khi gửi, không biết broker đã nhận chưa | Retry với cùng event ID; consumer phải idempotent |

Backoff có thể tăng theo số lần thử:

~~~java
Duration retryDelay(int attempts) {
    long exponent = Math.min(attempts, 10);
    long baseMillis = 500L;
    long cappedMillis = Math.min(300_000L, baseMillis * (1L << exponent));
    long jitterMillis = ThreadLocalRandom.current()
            .nextLong(Math.max(1L, cappedMillis / 2));
    return Duration.ofMillis(cappedMillis / 2 + jitterMillis);
}
~~~

Đây là ví dụ minh họa exponential backoff có jitter. Hệ thống thực tế cần giới hạn số lần thử, giới hạn thời gian retry và đặt next_attempt_at trong database. Jitter giúp nhiều worker không cùng retry tại một thời điểm sau khi broker phục hồi.

### 10.1. Trạng thái FAILED và quy trình phát lại

Không xóa bản ghi outbox khi vượt quá số lần retry. Có thể chuyển sang FAILED, lưu last_error và phát cảnh báo. Nhân viên vận hành hoặc một quy trình tự động có thể:

1. Xem event ID, aggregate, loại sự kiện và lỗi.
2. Xác minh payload và trạng thái broker.
3. Sửa cấu hình hoặc dữ liệu nếu cần.
4. Đưa event về PENDING hoặc tạo lệnh replay có kiểm soát.
5. Theo dõi consumer để phát hiện duplicate.

Không tự động phát lại vô hạn một payload sai định dạng. Điều đó có thể tạo vòng lặp lỗi, tăng tải và che khuất các event hợp lệ.

### 10.2. Retry ở relay và retry ở consumer

Hai lớp retry giải quyết hai lỗi khác nhau:

- Relay retry khi không thể xuất bản event tới broker.
- Consumer retry khi nhận được event nhưng xử lý nghiệp vụ thất bại.

Không gộp hai chính sách này. Nếu broker đã nhận event nhưng consumer xử lý thất bại, relay không nên phát lại event chỉ vì consumer chưa hoàn tất. Consumer/broker phải áp dụng retry, redelivery hoặc DLQ theo cơ chế của binder.

## 11. Polling relay và CDC relay

Có hai cách phổ biến để chuyển outbox event tới broker:

| Tiêu chí | Polling relay | CDC relay |
|---|---|---|
| Cách đọc | Truy vấn bảng outbox theo lịch | Đọc transaction log của database |
| Độ trễ | Phụ thuộc poll interval và batch | Có thể gần thời gian thực |
| Cập nhật trạng thái row | Thường cập nhật PENDING/PROCESSING/PUBLISHED | Có thể không cần cập nhật row sau publish |
| Lock/lease | Cần nếu nhiều worker cùng claim | Connector quản lý offset/log position |
| Hạ tầng | Có thể chỉ cần ứng dụng và database | Cần connector CDC và hạ tầng vận hành tương ứng |
| Khả năng điều khiển | Dễ điều chỉnh batch, retry và lịch | Phụ thuộc connector và cấu hình CDC |
| Tác động database | Tạo truy vấn đọc/ghi trạng thái | Đọc WAL/binlog và cần retention phù hợp |

### 11.1. Polling relay

Polling relay phù hợp khi muốn triển khai đơn giản, lưu lượng vừa phải hoặc cần kiểm soát logic gửi trong ứng dụng. Cần thiết kế index cho truy vấn pending, batch size, lease và chính sách dọn dữ liệu.

Poll interval quá ngắn tạo nhiều truy vấn khi không có event. Poll interval quá dài làm tăng độ trễ. Hãy chọn dựa trên SLA và số lượng event.

### 11.2. CDC relay

Change Data Capture đọc thay đổi từ transaction log của database như PostgreSQL WAL hoặc MySQL binlog. Một công cụ như Debezium có thể theo dõi bảng outbox và chuyển row thành event tới Kafka. Event Router SMT của Debezium có thể ánh xạ các trường outbox như event type, aggregate ID và payload sang message.

Với CDC, ứng dụng vẫn ghi outbox row trong transaction nghiệp vụ. Connector đọc thay đổi sau khi transaction commit. Offset của connector giúp tiếp tục đọc từ vị trí đã lưu sau khi restart.

CDC giảm nhu cầu polling và cập nhật status từng row, nhưng đòi hỏi vận hành connector, quyền đọc transaction log, retention, schema và monitoring. Nếu destination cuối cùng là RabbitMQ hoặc Pulsar, cần một cầu nối hoặc pipeline tích hợp tương ứng; không giả định mọi cấu hình CDC đều xuất trực tiếp tới mọi binder Spring Cloud Stream.

### 11.3. Chọn cách nào?

Chọn polling khi muốn một relay nằm trong ứng dụng Spring, tải chưa quá lớn và đội vận hành muốn kiểm soát trực tiếp retry/lease. Chọn CDC khi cần throughput cao, độ trễ thấp và đã có năng lực vận hành connector transaction log.

Hai phương án cùng dùng outbox table; khác biệt chủ yếu nằm ở cách đọc và chuyển bản ghi ra broker.

## 12. Kiểm thử transactional outbox

Một chiến lược test nên bao gồm transaction database, relay, broker và consumer.

### 12.1. Kiểm thử transaction ghi outbox

Kiểm tra khi tạo đơn hàng thành công, database có cả order và outbox row. Khi transaction rollback, cả hai đều không tồn tại.

~~~java
@SpringBootTest
class OrderOutboxTransactionTest {

    @Autowired
    OrderApplicationService service;

    @Autowired
    OrderRepository orderRepository;

    @Autowired
    OutboxRepository outboxRepository;

    @Test
    void storesOrderAndEventTogether() {
        service.createOrder(new CreateOrderCommand("customer-1", 2500));

        assertThat(orderRepository.count()).isEqualTo(1);
        assertThat(outboxRepository.count()).isEqualTo(1);
    }
}
~~~

Test này cần database test thật hoặc Testcontainers nếu muốn xác minh transaction semantics của hệ quản trị đang triển khai. Nếu test framework tự rollback transaction test ở cuối phương thức, cần lưu ý cách transaction của service tham gia transaction test.

### 12.2. Kiểm thử relay

Mock OutboxEventPublisher để xác minh:

- Event PENDING được claim.
- Publish thành công dẫn tới trạng thái PUBLISHED.
- Publish thất bại dẫn tới next_attempt_at và attempts được cập nhật.
- Event có lease hết hạn được claim lại.
- Event FAILED không bị gửi liên tục ngoài chính sách replay.

Kiểm tra relay không đánh dấu PUBLISHED khi publisher chỉ báo rằng message đã được đưa vào channel nhưng chưa có xác nhận broker theo hợp đồng của ứng dụng.

### 12.3. Kiểm thử broker thật

Dùng Testcontainers hoặc môi trường integration riêng để xác minh:

- Kafka topic/partition và record key.
- RabbitMQ exchange, queue và publisher confirms.
- Pulsar topic, producer send result và subscription.
- Message có event ID, event type, schema version và payload đúng.
- Broker dừng trong lúc relay gửi.
- Relay restart sau khi broker nhận message nhưng trước khi row được đánh dấu PUBLISHED.

Tình huống cuối phải chứng minh consumer loại bỏ tác động trùng khi relay gửi lại cùng event ID.

### 12.4. Kiểm thử consumer inbox

Gửi cùng một event hai lần và xác minh nghiệp vụ chỉ được áp dụng một lần. Sau đó giả lập transaction consumer rollback và xác minh dấu inbox cũng rollback, để lần redelivery có thể xử lý lại.

## 13. Vận hành và quản lý vòng đời outbox

Transactional outbox tạo một luồng dữ liệu bền vững trong database. Nếu relay dừng, backlog sẽ tăng. Cần giám sát:

| Chỉ số | Ý nghĩa |
|---|---|
| Outbox pending count | Số event đang chờ gửi |
| Oldest pending age | Tuổi event chờ lâu nhất |
| Processing count | Số event đang có lease |
| Expired lease count | Số event cần được claim lại |
| Publish success/failure rate | Tỷ lệ xuất bản thành công và thất bại |
| Retry count | Số lần gửi lại |
| Failed event count | Số event cần điều tra |
| Relay batch duration | Thời gian xử lý một batch |
| Consumer duplicate count | Số event trùng được inbox nhận diện |

### 13.1. Dọn dữ liệu outbox

Không xóa event ngay sau khi gửi thành công nếu hệ thống cần audit, replay hoặc điều tra. Có thể giữ lại theo retention rồi archive hoặc xóa theo batch. Nếu dùng CDC, cần phân biệt retention của bảng outbox với retention của transaction log; connector phải đọc kịp trước khi log bị dọn.

### 13.2. Bảo mật payload

Payload outbox có thể chứa thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm. Áp dụng quyền truy cập database tối thiểu, mã hóa khi cần, hạn chế log payload và đặt retention phù hợp. Relay chỉ nên có quyền đọc/cập nhật các cột cần thiết.

### 13.3. Shutdown và nhiều instance

Khi relay shutdown, ngừng claim batch mới. Các event đã claim nhưng chưa hoàn tất sẽ được xử lý hoặc để lease hết hạn cho worker khác. Khi chạy nhiều instance, dùng row locking/lease hoặc cơ chế CDC offset để tránh bỏ sót và phối hợp tiến độ.

## 14. Những lỗi thiết kế thường gặp

1. **Gửi broker trực tiếp trong transaction database**: tưởng rằng hai hệ thống cùng commit. Hãy ghi outbox row trong transaction và relay sau commit.
2. **Đánh dấu PUBLISHED trước khi gửi**: relay crash có thể làm mất event. Chỉ cập nhật trạng thái sau xác nhận phù hợp.
3. **Coi StreamBridge.send trả true là broker đã lưu bền vững**: giá trị này không tự chứng minh broker confirmation. Hãy dùng adapter xác nhận theo binder.
4. **Tạo event ID mới khi retry**: consumer không nhận ra duplicate. Giữ event ID ban đầu qua mọi lần gửi lại.
5. **Không có lease hoặc lock khi nhiều relay chạy**: nhiều worker có thể gửi cùng event đồng thời. Hãy claim nguyên tử.
6. **Giữ transaction database mở trong lúc gửi mạng**: lock kéo dài và tăng contention. Tách transaction claim, publish và cập nhật trạng thái.
7. **Không lưu snapshot payload**: relay có thể đọc trạng thái aggregate mới hơn thời điểm sự kiện xảy ra. Hãy lưu payload bất biến trong outbox.
8. **Không xử lý thứ tự theo aggregate**: event version sau có thể được gửi trước. Hãy tuần tự hóa theo aggregate và dùng partition key ổn định.
9. **Retry vô hạn không backoff**: tạo tải lớn và vòng lặp lỗi. Hãy dùng exponential backoff, jitter và trạng thái FAILED.
10. **Chỉ có outbox mà không có idempotent consumer**: crash sau publish có thể tạo duplicate. Hãy dùng inbox hoặc processed-event với unique key.
11. **Cho rằng inbox bao phủ side effect bên ngoài database**: email hoặc HTTP call vẫn có thể bị lặp. Hãy dùng idempotency key hoặc outbox tiếp theo.
12. **Không giám sát backlog**: relay có thể ngừng chạy mà không ai nhận ra. Hãy theo dõi tuổi pending lâu nhất và tỷ lệ publish.
13. **Dùng polling quá dày hoặc batch quá lớn**: tăng tải database hoặc làm relay giữ worker quá lâu. Hãy đo và điều chỉnh poll interval, index và batch size.
14. **Chọn CDC nhưng không giám sát transaction log retention**: connector có thể mất vị trí đọc khi log bị dọn. Hãy theo dõi lag và cấu hình retention đủ dài.

## 15. Quy trình triển khai transactional outbox

Khi áp dụng mẫu này cho một dịch vụ Spring Cloud Stream:

1. Xác định thay đổi nghiệp vụ nào cần phát sự kiện.
2. Thiết kế event payload bất biến, event ID, event type và schema version.
3. Tạo bảng outbox với trạng thái, chỉ mục và thông tin retry/lease cần thiết.
4. Ghi aggregate và outbox row trong cùng transaction database.
5. Chọn polling relay hoặc CDC dựa trên tải, độ trễ và năng lực vận hành.
6. Nếu polling, thiết kế claim nguyên tử, lease và batch giới hạn.
7. Cấu hình output binding/destination và binder cho broker.
8. Xác định chính xác mức confirmation trước khi đánh dấu PUBLISHED.
9. Dùng aggregate ID làm partition/routing key nếu cần thứ tự theo aggregate.
10. Thiết kế retry, backoff, FAILED và quy trình replay.
11. Xây dựng idempotent consumer bằng inbox hoặc processed-event.
12. Kiểm thử rollback, duplicate, broker outage, relay restart và thứ tự.
13. Thiết lập metrics, cảnh báo, retention và graceful shutdown.

## Kết luận

Transactional outbox giúp dịch vụ ghi thay đổi nghiệp vụ và ý định phát sự kiện trong cùng một transaction database. Relay đọc những event đã commit và gửi chúng tới broker qua Spring Cloud Stream. Polling relay dùng truy vấn, lock và lease; CDC relay đọc transaction log bằng connector như Debezium. Cả hai cách đều cần được vận hành và giám sát riêng.

Outbox không loại bỏ mọi message trùng và không tạo transaction nguyên tử giữa database với broker. Một relay có thể gửi thành công rồi dừng trước khi đánh dấu PUBLISHED, dẫn đến lần gửi lại. Vì vậy, giữ event ID ổn định, xác nhận gửi theo semantics của binder, bảo toàn thứ tự theo aggregate và xây dựng idempotent consumer là những phần thiết yếu của một hệ thống giao nhận tin cậy.

## Tài liệu tham khảo

- [Spring Cloud Stream — StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
