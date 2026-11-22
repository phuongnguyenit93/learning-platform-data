# ItemWriter gửi message

Trong Spring Batch, `ItemWriter<T>` thường được dùng để ghi item vào database hoặc file. Tuy nhiên, một step cũng có thể gửi item tới hệ thống khác thông qua message broker như Apache Kafka, JMS provider hoặc RabbitMQ. Khi đó, writer đóng vai trò producer: chuyển item đã được xử lý thành message, gắn key/header cần thiết và gửi tới destination tương ứng.

Ví dụ, một job đọc đơn hàng từ database, kiểm tra nghiệp vụ rồi phát sự kiện `OrderCreated` để các dịch vụ thanh toán, kho hàng và thông báo tiếp tục xử lý. `ItemWriter` là điểm tích hợp tự nhiên vì Spring Batch gọi writer theo từng chunk, cho phép gom nhiều item trước khi gửi.

Gửi message trong batch có một điểm cần thiết kế kỹ: transaction của chunk và việc broker nhận message có thể thuộc hai hệ thống khác nhau. Database rollback không tự động thu hồi message broker đã nhận; ngược lại, broker commit cũng không bảo đảm transaction database đã commit. Vì vậy, cần xác định delivery guarantee, acknowledgement, retry, idempotency và cách xử lý sự cố giữa hai hệ thống.

## ItemWriter gửi message là gì?

`ItemWriter<T>` là interface ghi một chunk item. Trong Spring Batch 5, chữ ký chính có dạng:

```java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

Writer nhận một `Chunk` thay vì từng item riêng lẻ. Implementation có thể lặp qua các item, chuyển chúng thành message và gửi tới broker. Nếu có lỗi không thể phục hồi, writer nên ném exception để step áp dụng transaction, retry hoặc skip policy đã cấu hình.

Luồng xử lý điển hình:

```text
ItemReader
    |
    v
ItemProcessor
    |
    v
Chunk<OrderEvent>
    |
    v
Message ItemWriter
    |
    +--> serialize payload
    +--> tạo key / headers
    +--> gửi message
    +--> chờ acknowledgement theo policy
    |
    v
Kafka / JMS / RabbitMQ broker
    |
    v
Consumer services
```

Writer chịu trách nhiệm chuyển item thành message và xác định khi nào thao tác gửi được xem là thành công đối với step. Broker chịu trách nhiệm nhận/lưu/chuyển tiếp theo cấu hình của nó. Consumer chịu trách nhiệm xử lý message và xác nhận theo semantics của giao thức.

## Vì sao gửi message trong ItemWriter?

Đưa thao tác gửi message vào writer có một số lợi ích:

- Tận dụng chunk processing để gom nhiều item trong một lần gọi writer.
- Dùng chung lifecycle, transaction boundary, retry và skip của step.
- Tách logic đọc, chuyển đổi và xuất dữ liệu.
- Có thể ghi message từ output đã được processor validate/enrich.
- Dễ kiểm thử writer độc lập và kiểm thử toàn bộ job.

Tuy nhiên, writer không tự biến message broker thành một phần của database transaction. Nếu message được gửi thành công rồi chunk rollback, message vẫn có thể được consumer nhìn thấy. Nếu writer gửi message bất đồng bộ nhưng trả về trước khi broker xác nhận, step có thể commit chunk trong khi message sau đó thất bại.

Vì vậy, writer cần có hợp đồng rõ ràng: trả về khi nào, acknowledgement nào được xem là đủ, và lỗi gửi được truyền lên Spring Batch ra sao.

## Thiết kế payload trước khi gửi

Không nên gửi trực tiếp entity JPA hoặc object nội bộ có nhiều lazy relationship. Hãy tạo message contract ổn định, chứa đúng dữ liệu consumer cần.

Ví dụ:

```java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal amount,
        String currency,
        Instant occurredAt,
        int schemaVersion) {
}
```

`eventId` dùng để deduplicate; `schemaVersion` giúp consumer biết cách diễn giải payload; `occurredAt` là thời điểm sự kiện xảy ra; `orderId` là business identifier. Trong hệ thống thực tế, có thể cần thêm tenant, correlation ID, trace ID hoặc nguồn phát sự kiện.

Message contract nên:

- Có tên field rõ ràng và ổn định.
- Dùng kiểu dữ liệu có semantics thống nhất giữa producer và consumer.
- Có version hoặc quy tắc tương thích schema.
- Tránh chứa secret, thông tin nhạy cảm không cần thiết hoặc toàn bộ entity graph.
- Không phụ thuộc vào tên class Java nội bộ nếu nhiều ngôn ngữ cùng tiêu thụ.
- Có ID duy nhất để hỗ trợ idempotency và tracing.

### Event khác command

Event mô tả điều đã xảy ra, ví dụ `OrderCreated`. Command yêu cầu một hệ thống thực hiện hành động, ví dụ `ReserveInventory`. Event thường được phát cho nhiều consumer và không nên bị diễn giải như một yêu cầu có thể ghi đè trạng thái nguồn. Command thường có người nhận và quy tắc xử lý cụ thể.

Đặt tên message theo ý nghĩa nghiệp vụ giúp consumer hiểu đúng semantics và tránh coupling vào implementation của batch job.

## Chuyển item thành message

Có thể tách việc tạo payload ra khỏi writer bằng một mapper:

```java
@FunctionalInterface
public interface MessageMapper<I, M> {
    M toMessage(I item);
}
```

Writer chỉ điều phối việc chuyển đổi và gửi:

```java
public class MessageItemWriter<I, M> implements ItemWriter<I> {

    private final MessageMapper<I, M> mapper;
    private final MessageSender<M> sender;

    public MessageItemWriter(
            MessageMapper<I, M> mapper,
            MessageSender<M> sender) {
        this.mapper = mapper;
        this.sender = sender;
    }

    @Override
    public void write(Chunk<? extends I> chunk) throws Exception {
        for (I item : chunk) {
            M message = mapper.toMessage(item);
            sender.send(message);
        }
    }
}
```

`MessageSender` là abstraction do ứng dụng định nghĩa:

```java
@FunctionalInterface
public interface MessageSender<M> {
    void send(M message) throws Exception;
}
```

Tách mapper và sender giúp unit test không cần broker thật. Trong production, sender có thể được triển khai bằng `KafkaTemplate`, `JmsTemplate`, `RabbitTemplate` hoặc client tương ứng.

Với batch lớn, writer có thể gửi theo batch API của broker thay vì gọi một lần cho từng item. Dù dùng cách nào, phải chờ kết quả gửi theo policy đã chọn trước khi writer báo thành công nếu muốn lỗi broker ảnh hưởng tới chunk hiện tại.

## Gửi message tới Kafka

Spring for Apache Kafka cung cấp `KafkaTemplate<K, V>` để gửi record tới Kafka. Một record thường gồm topic, key, value và có thể có headers. Key có vai trò quan trọng vì Kafka dùng key để chọn partition theo partitioner mặc định, từ đó ảnh hưởng tới ordering của các record cùng key.

Ví dụ writer cho Spring Kafka 3.x, nơi `KafkaTemplate.send(...)` trả về `CompletableFuture`:

```java
public class KafkaOrderWriter implements ItemWriter<OrderCreatedEvent> {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;
    private final String topic;

    public KafkaOrderWriter(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate,
            String topic) {
        this.kafkaTemplate = kafkaTemplate;
        this.topic = topic;
    }

    @Override
    public void write(Chunk<? extends OrderCreatedEvent> chunk)
            throws Exception {

        List<CompletableFuture<SendResult<String, OrderCreatedEvent>>> sends =
                new ArrayList<>();

        for (OrderCreatedEvent event : chunk) {
            sends.add(kafkaTemplate.send(
                    topic,
                    event.orderId(),
                    event));
        }

        for (CompletableFuture<SendResult<String, OrderCreatedEvent>> send : sends) {
            send.get(30, TimeUnit.SECONDS);
        }
    }
}
```

Ví dụ dùng `orderId` làm key để các event cùng đơn hàng thường được route tới cùng partition. `get(timeout)` chờ future hoàn tất và đưa lỗi gửi lên writer. Thời gian timeout phải phù hợp với SLA và broker configuration; không dùng timeout tùy tiện quá ngắn khiến batch fail khi broker chỉ đang chậm.

Spring Kafka các phiên bản cũ có thể dùng `ListenableFuture` thay vì `CompletableFuture`; hãy điều chỉnh code theo version dependency. Không copy nguyên kiểu future của Spring Kafka 3.x vào ứng dụng dùng version cũ.

### Chọn key và partition

Kafka đảm bảo thứ tự trong một partition, không đảm bảo thứ tự toàn cục giữa các partition. Nếu các event của cùng aggregate cần đúng thứ tự, thường dùng aggregate/business ID làm key.

Ví dụ:

```java
kafkaTemplate.send("order-events", event.orderId(), event);
```

Nếu dùng random key hoặc key null, các event cùng order có thể đi tới partition khác nhau và consumer không thể dựa vào thứ tự theo order. Key cũng ảnh hưởng tới phân phối tải; một key quá nóng có thể tạo hot partition.

### Producer acknowledgement

Future hoàn tất theo kết quả producer/broker, nhưng độ bền thực tế phụ thuộc Kafka producer và cluster configuration. Một số thiết lập quan trọng:

- `acks`: mức acknowledgement producer yêu cầu từ broker.
- `enable.idempotence`: hỗ trợ producer idempotence trong phạm vi semantics Kafka cung cấp.
- `retries`: số lần producer thử lại lỗi gửi có thể phục hồi.
- `delivery.timeout.ms`: thời gian tối đa cho một record được gửi thành công theo producer policy.
- Replication factor và `min.insync.replicas`: ảnh hưởng tới mức độ dữ liệu được replica chấp nhận.

`acks=all` cùng replication/min-ISR phù hợp thường tăng độ bền so với `acks=0` hoặc `acks=1`, nhưng không tự tạo exactly-once giữa database transaction và Kafka. Producer idempotence giảm duplicate do retry nội bộ của producer; nó không thay thế event ID và idempotency ở consumer khi batch job gửi lại sau restart.

### Chờ future hay gửi bất đồng bộ?

Nếu writer gọi `send()` rồi trả về ngay, Spring Batch có thể commit chunk trước khi producer future hoàn tất. Khi future thất bại sau đó, step không còn biết chunk nào cần rollback hoặc retry.

Các lựa chọn:

- Chờ tất cả future hoàn tất trước khi `write()` trả về.
- Dùng producer transaction được quản lý phù hợp với chunk.
- Gửi bất đồng bộ nhưng có một cơ chế flush/await và truyền lỗi lên writer trước khi commit.

Không bỏ qua future hoặc exception trong callback. Nếu cần throughput, có thể gửi song song trong chunk rồi chờ toàn bộ future; phải giới hạn concurrency và xử lý timeout/exception có chủ đích.

## Gửi message tới JMS

Với JMS, Spring cung cấp `JmsTemplate` để gửi message tới queue hoặc topic. Có thể dùng `convertAndSend` để chuyển object thành message thông qua `MessageConverter`.

Ví dụ custom writer:

```java
public class JmsOrderWriter implements ItemWriter<OrderCreatedEvent> {

    private final JmsTemplate jmsTemplate;
    private final String destination;

    public JmsOrderWriter(JmsTemplate jmsTemplate, String destination) {
        this.jmsTemplate = jmsTemplate;
        this.destination = destination;
    }

    @Override
    public void write(Chunk<? extends OrderCreatedEvent> chunk) {
        for (OrderCreatedEvent event : chunk) {
            jmsTemplate.convertAndSend(destination, event, message -> {
                message.setStringProperty("eventId", event.eventId());
                message.setStringProperty("eventType", "OrderCreated");
                return message;
            });
        }
    }
}
```

`MessageConverter` cần được cấu hình để serialize payload theo contract, ví dụ JSON. Destination có thể là queue hoặc topic tùy semantics hệ thống. Header/property dùng cho routing, correlation hoặc tracing; không nhét mọi metadata vào body nếu chúng có thể được biểu diễn đúng bằng message property.

### JMS transaction

JMS session có thể được quản lý theo transaction. Khi dùng `JmsTransactionManager` hoặc JTA phù hợp, thao tác gửi có thể tham gia transaction JMS. Tuy nhiên, transaction JMS và transaction database của chunk không tự động trở thành một transaction phân tán chỉ vì cùng nằm trong một step.

Nếu cần phối hợp database và JMS atomic, cần transaction manager có khả năng phối hợp resource theo thiết kế hệ thống, chẳng hạn JTA/XA khi broker và database hỗ trợ. XA làm tăng độ phức tạp vận hành và cần được lựa chọn có chủ đích. Một lựa chọn phổ biến khác là transactional outbox.

## Gửi message tới RabbitMQ / AMQP

Với RabbitMQ, Spring AMQP cung cấp `RabbitTemplate` để gửi message tới exchange với routing key. Exchange và binding quyết định queue nhận message.

Ví dụ minh họa:

```java
public class RabbitOrderWriter implements ItemWriter<OrderCreatedEvent> {

    private final RabbitTemplate rabbitTemplate;
    private final String exchange;
    private final String routingKey;

    public RabbitOrderWriter(
            RabbitTemplate rabbitTemplate,
            String exchange,
            String routingKey) {
        this.rabbitTemplate = rabbitTemplate;
        this.exchange = exchange;
        this.routingKey = routingKey;
    }

    @Override
    public void write(Chunk<? extends OrderCreatedEvent> chunk) {
        for (OrderCreatedEvent event : chunk) {
            rabbitTemplate.convertAndSend(
                    exchange,
                    routingKey,
                    event,
                    message -> {
                        message.getMessageProperties()
                                .setMessageId(event.eventId());
                        message.getMessageProperties()
                                .setType("OrderCreated");
                        return message;
                    });
        }
    }
}
```

Đoạn code minh họa việc publish; cấu hình converter, delivery mode, publisher confirms và returns cần được thiết lập theo Spring AMQP/RabbitMQ version. `convertAndSend` trả về không có nghĩa consumer đã xử lý message. Nếu cần xác nhận broker đã nhận publish, cấu hình publisher confirms và xử lý confirm/return theo API tương ứng.

Với RabbitMQ, phân biệt:

- **Publisher confirm:** broker xác nhận publish đã được xử lý theo semantics của broker.
- **Publisher return:** message không route được tới queue theo cấu hình mandatory/return.
- **Consumer acknowledgement:** consumer xác nhận đã xử lý message.

Ba tín hiệu này không thay thế nhau. Một publisher confirm thành công không chứng minh consumer đã xử lý xong.

## Message key, header và correlation metadata

Một message thường có body và metadata. Body chứa payload nghiệp vụ; metadata hỗ trợ routing, tracing, deduplication và schema evolution.

Các trường thường dùng:

| Metadata | Mục đích |
| --- | --- |
| `eventId` / message ID | Nhận diện duy nhất một event để deduplicate |
| `eventType` | Xác định loại event/contract |
| `schemaVersion` | Chọn schema hoặc deserializer phù hợp |
| `correlationId` | Liên kết các message trong một business flow |
| `causationId` | Cho biết message/event nào gây ra event hiện tại |
| `traceparent` | Truyền distributed tracing context |
| `tenantId` | Phân tách tenant nếu kiến trúc yêu cầu |
| partition/routing key | Điều khiển phân phối message |

Không đưa thông tin xác thực, access token hoặc secret vào header. Header có thể được log, lưu trong broker hoặc hiển thị cho operator; chỉ gửi metadata cần thiết.

## Gửi theo chunk và batching

Spring Batch gọi `write()` một lần cho mỗi chunk. Writer có thể gửi từng message hoặc dùng batch API của broker/client. Chunk size quyết định số item tối đa writer nhận trong một lần gọi.

Ví dụ chunk size 200:

```java
.chunk(200, transactionManager)
```

Writer nhận tối đa 200 item trong một chunk, có thể gửi 200 message. Nếu broker/client hỗ trợ batching nội bộ, các record có thể được gom theo batch size, linger time hoặc network request. Không nhất thiết một lần gọi `write()` tương đương một network request.

Các yếu tố ảnh hưởng throughput:

- Chunk size của Spring Batch.
- Số message mỗi lần gửi.
- Kích thước payload.
- Producer batch/linger/compression settings.
- Số partition/queue và phân phối key.
- Số request in-flight.
- Cách writer chờ acknowledgement.
- Network latency và broker load.

Chunk quá nhỏ làm tăng transaction và callback overhead. Chunk quá lớn có thể tăng memory, thời gian xử lý, số message cần retry và phạm vi rollback. Hãy benchmark với kích thước message và throughput gần production.

## Transaction giữa Spring Batch và message broker

Đây là phần cần cân nhắc kỹ nhất khi dùng message writer. Chunk-oriented step thường chạy trong transaction do `PlatformTransactionManager` quản lý. Broker có thể có transaction manager riêng hoặc semantics xác nhận riêng.

### Database transaction và broker transaction là hai resource

Giả sử step đọc row từ database, cập nhật trạng thái và gửi event tới Kafka:

```text
Chunk transaction (Database)
    |
    +--> UPDATE orders SET status = 'PUBLISHED'
    |
    +--> send OrderCreated to Kafka
    |
    +--> COMMIT database
```

Nếu Kafka nhận message nhưng database commit thất bại, consumer có thể xử lý event cho một thay đổi chưa commit. Ngược lại, database commit thành công nhưng message send thất bại thì hệ thống có trạng thái đã cập nhật nhưng thiếu event.

Một transaction local chỉ bảo vệ resource mà transaction manager quản lý. Không được giả định writer gửi message sẽ tự rollback theo database transaction.

### Trường hợp gửi trước rồi database rollback

1. Writer gửi message thành công.
2. Một thao tác khác trong chunk thất bại.
3. Database transaction rollback.
4. Message vẫn tồn tại trên broker.

Consumer có thể nhận message dù thay đổi database liên quan không được commit.

### Trường hợp database commit rồi gửi message thất bại

Nếu message send không tham gia transaction chung và lỗi xảy ra sau khi database commit, row có thể đã được đánh dấu published nhưng message chưa được broker nhận. Job restart có thể bỏ qua row đó và event bị mất.

Thứ tự thực thi và transaction synchronization ảnh hưởng tới cửa sổ lỗi, nhưng không thể biến hai resource độc lập thành atomic chỉ bằng cách đổi thứ tự gọi.

## Delivery guarantee

Khi thiết kế message writer, cần xác định hệ thống yêu cầu mức delivery nào:

| Mức | Ý nghĩa | Rủi ro chính |
| --- | --- | --- |
| At-most-once | Message có thể mất nhưng không chủ động gửi lại | Mất event khi lỗi trước khi broker nhận |
| At-least-once | Retry cho tới khi có xác nhận phù hợp; có thể duplicate | Consumer phải idempotent |
| Exactly-once theo phạm vi broker | Broker hỗ trợ semantics exactly-once trong phạm vi transaction/protocol cụ thể | Không tự bao trùm database và external side effects |

Trong batch integration, at-least-once cộng idempotent consumer thường là lựa chọn thực tế. Exactly-once end-to-end giữa database, broker và consumer thường đòi hỏi thiết kế phối hợp nhiều resource và vẫn cần xác định rõ phạm vi bảo đảm.

### Producer acknowledgement không phải consumer completion

Producer nhận broker acknowledgement chỉ xác nhận broker đã chấp nhận/ghi message theo cấu hình. Nó không chứng minh consumer đã đọc, xử lý và commit kết quả. Nếu nghiệp vụ cần biết consumer đã hoàn thành, cần response event, reply queue, workflow status hoặc cơ chế tracking riêng.

## Transaction manager và broker transaction

Một số broker hỗ trợ transaction riêng. Spring cũng có transaction manager cho Kafka, JMS hoặc resource khác. Việc một writer dùng transaction manager nào phụ thuộc cấu hình step và cách template được liên kết với transaction.

Không thể giả định `.writer(messageWriter)` tự động tham gia mọi transaction chỉ vì step có `PlatformTransactionManager`. Cần kiểm tra:

- Transaction manager của step quản lý resource nào?
- Template dùng connection/session/producer nào?
- Broker transaction được bắt đầu và commit ở đâu?
- Khi writer ném exception, broker rollback có thực sự xảy ra không?
- Khi database commit thất bại, broker transaction có thể rollback theo không?
- Commit ordering và synchronization behavior của framework version là gì?

Với Kafka, Spring Kafka có `KafkaTransactionManager` và transactional producer. Với JMS, có `JmsTransactionManager` hoặc JTA/XA tùy provider. Với RabbitMQ, channel transaction và publisher confirms có semantics riêng; publisher confirms không phải distributed transaction với database.

Nếu cần atomic commit giữa database và broker, đánh giá JTA/XA khi cả hai resource và hạ tầng hỗ trợ. Cần tính đến coordinator, recovery log, timeout, heuristic outcome và chi phí vận hành. Đừng chọn XA chỉ để tránh viết idempotency nếu hệ thống không thực sự cần hoặc broker không hỗ trợ phù hợp.

## Transactional outbox

Transactional outbox là pattern phổ biến để tránh mất event khi cập nhật database và publish message.

Thay vì gửi trực tiếp tới broker trong transaction xử lý chính, job ghi một outbox row cùng transaction với thay đổi nghiệp vụ:

```text
Chunk transaction (Database)
    |
    +--> UPDATE orders ...
    |
    +--> INSERT INTO outbox(event_id, payload, status)
    |
    +--> COMMIT
             |
             v
       Outbox publisher step/job
             |
             +--> read pending outbox rows
             +--> publish to broker
             +--> mark published
```

Nếu transaction database rollback, cả thay đổi nghiệp vụ và outbox row đều rollback. Nếu commit thành công, event nằm bền vững trong database và có thể được publisher retry sau này.

Ví dụ schema:

```sql
CREATE TABLE outbox_event (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    status VARCHAR(20) NOT NULL
);
```

Step nghiệp vụ ghi outbox:

```java
@Bean
JdbcBatchItemWriter<OutboxEvent> outboxWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OutboxEvent>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO outbox_event(
                        event_id, aggregate_id, event_type,
                        payload, created_at, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """)
            .itemPreparedStatementSetter((event, ps) -> {
                ps.setString(1, event.eventId());
                ps.setString(2, event.aggregateId());
                ps.setString(3, event.eventType());
                ps.setString(4, event.payload());
                ps.setTimestamp(5, Timestamp.from(event.createdAt()));
                ps.setString(6, "PENDING");
            })
            .build();
}
```

Một publisher step riêng đọc outbox row ở trạng thái pending, gửi message, sau đó đánh dấu published. Nếu publish thành công nhưng cập nhật trạng thái published thất bại, publisher có thể gửi lại; do đó event ID và consumer idempotency vẫn cần thiết.

### Outbox không tự loại bỏ duplicate

Outbox bảo đảm thay đổi database và việc tạo ý định phát event cùng commit. Nó không bảo đảm publish chỉ xảy ra đúng một lần. Nếu publisher crash sau khi broker nhận message nhưng trước khi đánh dấu row published, lần chạy sau có thể gửi lại. Consumer cần deduplicate bằng `eventId` hoặc lưu inbox/processed-message table trong cùng transaction với business update.

### Claim outbox row an toàn khi có nhiều publisher

Nếu nhiều worker cùng publish outbox, cần cơ chế claim/lease để tránh cùng xử lý một row. Có thể dùng status `PROCESSING`, owner, lease expiry hoặc locking strategy phù hợp database. Không giữ transaction database mở trong lúc chờ broker lâu nếu điều đó tạo lock contention; thiết kế claim và update status theo transaction ngắn.

## Idempotency và duplicate message

Với at-least-once delivery, duplicate là tình huống cần dự kiến. Writer có thể gửi lại một chunk sau restart hoặc retry. Producer/broker idempotence không thay thế idempotency ở tầng nghiệp vụ.

Các cách thường dùng:

- Tạo `eventId` ổn định từ event/business operation, không tạo ID mới mỗi lần retry.
- Consumer lưu `eventId` đã xử lý trong inbox/processed table có unique constraint.
- Consumer cập nhật business data và ghi nhận event ID trong cùng transaction.
- Dùng upsert hoặc unique key để chống ghi trùng.
- Thiết kế handler có thể chạy lại mà kết quả cuối không thay đổi.

Ví dụ bảng inbox:

```sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Consumer bắt đầu transaction, insert event ID vào bảng này; nếu unique constraint báo đã xử lý, bỏ qua business effect. Nếu insert và business update nằm cùng transaction, chúng commit hoặc rollback cùng nhau.

Không tạo `eventId = UUID.randomUUID()` bên trong writer cho mỗi lần retry nếu cùng một business event cần giữ identity. ID nên được tạo trước và lưu bền vững trong item hoặc outbox row.

## Retry và xử lý lỗi gửi message

Writer có thể gặp lỗi:

- Broker unavailable hoặc network timeout.
- Authentication/authorization failure.
- Topic/queue/exchange không tồn tại hoặc routing sai.
- Serialization error.
- Payload vượt giới hạn message size.
- Broker từ chối publish hoặc hết quota.
- Acknowledgement timeout.
- Lỗi transaction/producer fencing.

Không nên retry mọi lỗi như nhau:

| Loại lỗi | Hướng xử lý thường phù hợp |
| --- | --- |
| Network timeout tạm thời | Retry có giới hạn, backoff và timeout |
| Broker unavailable | Retry có giới hạn; fail step nếu vẫn không phục hồi |
| Authentication/authorization | Fail nhanh và báo cấu hình |
| Serialization/schema error | Reject/quarantine item hoặc fail theo contract; retry không sửa payload |
| Topic/queue không tồn tại | Fail nhanh, xử lý deployment/configuration |
| Message quá lớn | Từ chối hoặc chuyển sang object storage + reference theo contract |
| Duplicate do retry | Consumer idempotency xử lý |

Ví dụ fault-tolerant step:

```java
return new StepBuilder("publishOrdersStep", jobRepository)
        .<OrderCreatedEvent, OrderCreatedEvent>chunk(100, transactionManager)
        .reader(eventReader)
        .writer(kafkaOrderWriter)
        .faultTolerant()
        .retry(TransientBrokerException.class)
        .retryLimit(3)
        .build();
```

`TransientBrokerException` là exception ứng dụng phân loại từ lỗi broker có khả năng phục hồi. Trong thực tế, cần map đúng exception của Kafka/JMS/AMQP client và xác định retry policy theo phiên bản framework. Không retry lỗi serialization hoặc authorization như lỗi mạng.

### Backoff và retry ở hai tầng

Producer client thường đã có retry nội bộ. Spring Batch cũng có retry ở writer/step. Hai tầng có thể nhân số lần thử và kéo dài thời gian chờ ngoài dự kiến. Tính tổng retry budget, `delivery.timeout`, step retry limit và backoff để không tạo retry storm.

Không giữ chunk transaction mở quá lâu trong khi chờ retry nếu transaction đó giữ lock database quan trọng. Với broker outage kéo dài, outbox publisher tách biệt thường giúp cô lập sự cố tốt hơn.

## Skip và dead-letter queue

Skip có thể phù hợp với message không hợp lệ hoặc item không thể serialize, nhưng cần bảo đảm lỗi được phân loại chính xác. Nếu lỗi là broker outage, skip item sẽ làm mất event.

Một số lựa chọn:

- **Fail step:** khi không được phép mất bất kỳ message nào.
- **Skip + reject audit:** khi dữ liệu không hợp lệ và nghiệp vụ cho phép cách ly.
- **Dead-letter queue (DLQ):** khi broker/consumer có cơ chế chuyển message lỗi sang queue riêng.
- **Outbox pending/error:** giữ event trong database để retry hoặc điều tra.

DLQ thường xử lý message consumer không thể xử lý hoặc broker dead-letter theo policy; không phải tự động thay thế reject handling ở producer. Nếu writer không publish được do topic không tồn tại, DLQ ở consumer chưa chắc giúp được.

`SkipListener` có thể ghi nhận item bị skip:

```java
public class MessageSkipListener
        implements SkipListener<OrderCreatedEvent, OrderCreatedEvent> {

    @Override
    public void onSkipInRead(Throwable exception) {
        log.warn("Could not read event", exception);
    }

    @Override
    public void onSkipInProcess(
            OrderCreatedEvent item,
            Throwable exception) {
        log.warn("Event {} rejected during processing", item.eventId(), exception);
    }

    @Override
    public void onSkipInWrite(
            OrderCreatedEvent item,
            Throwable exception) {
        log.error("Event {} failed during publish", item.eventId(), exception);
    }
}
```

Nếu ghi reject file hoặc database trong listener, xem xét transaction và idempotency của side effect. Listener có thể được gọi trong các đường retry/rollback; không nên tạo audit duplicate không kiểm soát.

## Ordering và concurrency

Thứ tự message có thể quan trọng, ví dụ `OrderCreated` phải tới trước `OrderCancelled`. Tuy nhiên, chunk writer có thể gửi song song hoặc broker phân phối theo partition/queue.

Để giữ ordering:

- Dùng key ổn định theo aggregate trong Kafka để các event cùng aggregate vào cùng partition.
- Tránh gửi song song các event cùng key nếu thứ tự gửi là yêu cầu.
- Đảm bảo consumer xử lý tuần tự trong partition/queue theo semantics cần thiết.
- Có sequence/version trong payload để consumer phát hiện event đến sai thứ tự.
- Nếu cần thứ tự toàn cục, thiết kế một partition/queue hoặc coordinator có thứ tự rõ ràng; cân nhắc giới hạn throughput.

Không có ordering toàn cục tự động khi gửi tới nhiều topic/partition/queue. `ItemWriter` lặp theo thứ tự chunk không bảo đảm consumer quan sát đúng thứ tự nếu producer async, broker partitioning hoặc consumer concurrency thay đổi.

## Serialization và schema evolution

Message thường được serialize thành JSON, Avro, Protobuf hoặc format khác. Serialization phải nhất quán giữa producer và consumer.

Với JSON/Jackson:

```java
String payload = objectMapper.writeValueAsString(event);
```

Không serialize một object thành JSON rồi serialize chuỗi JSON đó lần nữa, vì consumer sẽ nhận JSON string chứa JSON thay vì object. Dùng converter hoặc serializer phù hợp với template để serialize đúng một lần.

Các nguyên tắc schema:

- Thêm field mới theo hướng tương thích khi consumer cũ có thể bỏ qua unknown field.
- Không đổi ý nghĩa hoặc kiểu field hiện có mà không version hóa.
- Quy định field bắt buộc, default và null semantics.
- Dùng schema registry nếu hệ sinh thái yêu cầu contract được quản lý tập trung.
- Kiểm thử producer payload với consumer contract/version được hỗ trợ.

Không gửi Java class name làm discriminator nếu message được tiêu thụ bởi nhiều ngôn ngữ hoặc không tin cậy. Dùng event type/version rõ ràng và allowlist deserialization.

## Message size và payload lớn

Broker thường có giới hạn message size. Không gửi entity graph hoặc file lớn trong một message nếu vượt giới hạn hoặc gây áp lực memory/network.

Với payload lớn:

1. Ghi nội dung vào object storage hoặc file bền vững.
2. Tạo reference bất biến, checksum và content type.
3. Gửi message nhỏ chứa URI/reference, metadata và event ID.
4. Consumer tải nội dung theo quyền truy cập phù hợp.

Reference phải trỏ tới object đã được publish bền vững trước khi message được gửi. Cần quy định retention và quyền truy cập để consumer có thể tải object trong thời gian cần thiết.

## Batch writer và message batch API

Một writer có thể gửi từng record bằng template hoặc dùng API batch của broker. Gửi từng record dễ xử lý lỗi theo item hơn, nhưng có thể tăng overhead. Batch API có thể tăng throughput nhưng thường làm lỗi gắn với cả batch hoặc trả kết quả theo từng record tùy client.

Khi chọn batch API, cần xác định:

- Một lỗi trong batch có làm fail toàn bộ chunk không?
- Có thể xác định record nào thất bại không?
- Partial success được biểu diễn thế nào?
- Có thể retry toàn bộ batch mà không tạo duplicate không?
- Broker có giới hạn số record hoặc tổng byte mỗi batch không?
- Batch có giữ ordering theo key/partition không?

Không catch lỗi từng message rồi tiếp tục như thể toàn bộ chunk thành công nếu không ghi nhận rõ item thất bại. Spring Batch chỉ biết `write()` thành công hay ném exception; nếu writer nuốt lỗi, checkpoint có thể tiến qua item chưa publish.

## Monitoring và observability

Một message writer cần cung cấp metrics để vận hành job và broker:

- Số item writer nhận.
- Số message gửi thành công.
- Số send failure và retry.
- Acknowledgement latency và timeout.
- Message size và serialization latency.
- Số item skip/reject.
- Topic/queue/exchange và partition/routing key.
- Correlation ID, event ID và JobExecution ID.
- Số event pending trong outbox nếu dùng pattern đó.

Không log toàn bộ payload nếu có dữ liệu cá nhân hoặc thông tin nhạy cảm. Log event ID, business key và correlation ID thường đủ để điều tra.

Khi job fail, operator cần biết message nào có thể đã được broker nhận trước lỗi. Ghi nhận event ID và send result giúp xác định phạm vi cần replay hoặc reconcile.

## Cấu hình writer trong step

Sau khi tạo writer bean, đăng ký nó như writer bình thường:

```java
@Bean
Step publishOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderCreatedEvent> eventReader,
        ItemProcessor<OrderCreatedEvent, OrderCreatedEvent> validator,
        ItemWriter<OrderCreatedEvent> messageWriter) {

    return new StepBuilder("publishOrdersStep", jobRepository)
            .<OrderCreatedEvent, OrderCreatedEvent>chunk(100, transactionManager)
            .reader(eventReader)
            .processor(validator)
            .writer(messageWriter)
            .build();
}
```

Step xử lý chunk và gọi writer. Nếu writer gửi message trực tiếp, transaction manager của step chỉ bảo vệ broker nếu writer/template thực sự tham gia transaction manager/resource đó. Hãy ghi rõ trong cấu hình và tài liệu vận hành.

Nếu writer không cần state thì không cần implement `ItemStream`. Nếu writer giữ buffer, file tạm hoặc checkpoint cần restart, implement `ItemStream` và bảo đảm stream lifecycle được đăng ký. Template producer thường do Spring quản lý; không tự đóng template/connection trong mỗi lần `write()`.

## Scope và thread safety

Message writer thường là singleton bean. Điều đó chỉ an toàn khi implementation không giữ mutable state theo item hoặc execution và template/client được thiết kế thread-safe theo contract của nó.

Các nguyên tắc:

- Không lưu `currentEvent`, `currentJobExecution` hoặc buffer mutable dùng chung trong field.
- Tạo correlation metadata theo từng item bằng biến local.
- Dùng template producer được Spring quản lý và cấu hình thread-safety đúng.
- Nếu writer cần state theo step, cân nhắc `@StepScope`.
- Nếu step chạy đa luồng, xác định ordering và concurrency của producer.
- Không tạo một producer connection/session mới cho từng item nếu template đã quản lý pool/lifecycle.

Với JMS, session thường không thread-safe; `JmsTemplate` quản lý việc tạo/sử dụng session theo contract. Không tự giữ một `Session` singleton rồi dùng từ nhiều thread.

## Kiểm thử ItemWriter gửi message

Nên có unit test cho mapping, routing và lỗi; integration test với broker hoặc test container cho acknowledgement, serialization, transaction và retry.

### Unit test với MessageSender mock

Với writer generic ở trên:

```java
@Test
void sendsEveryItemInChunk() throws Exception {
    MessageMapper<Order, OrderCreatedEvent> mapper = order ->
            new OrderCreatedEvent(
                    "event-" + order.orderId(),
                    order.orderId(),
                    order.customerId(),
                    order.amount(),
                    "VND",
                    Instant.parse("2026-11-15T00:00:00Z"),
                    1);

    MessageSender<OrderCreatedEvent> sender = mock(MessageSender.class);
    ItemWriter<Order> writer = new MessageItemWriter<>(mapper, sender);

    writer.write(new Chunk<>(List.of(order1, order2)));

    verify(sender, times(2)).send(any(OrderCreatedEvent.class));
}
```

Test này xác nhận mỗi item được map và gửi. Có thể capture argument để xác nhận event ID, amount, currency và schema version chính xác.

### Kiểm thử lỗi send

Mock sender ném exception ở một item và xác nhận `write()` truyền exception ra ngoài. Không để writer nuốt lỗi. Kiểm tra số lần gọi và hành vi khi item đầu/giữa/cuối chunk thất bại.

### Kiểm thử Kafka

Với Kafka, kiểm tra:

- Record được gửi đúng topic và key.
- Payload/header serialize đúng contract.
- Future failure làm writer fail.
- Timeout được xử lý đúng.
- `acks`, idempotence và transaction config đúng với yêu cầu.
- Restart/retry không làm consumer xử lý business effect trùng.

Có thể dùng embedded broker hoặc Testcontainers Kafka theo test infrastructure. Test trên broker tương đương production hữu ích để xác nhận partitioning, authentication, replication và producer configuration.

### Kiểm thử JMS/RabbitMQ

Với JMS, xác nhận destination, converter, message properties, delivery mode và transaction rollback/commit. Với RabbitMQ, xác nhận exchange/routing key, queue binding, publisher confirm/return và behavior khi broker unavailable.

Không chỉ assert `convertAndSend` được gọi; hãy nhận message từ broker test hoặc xác nhận publish result/confirm phù hợp.

### Kiểm thử chunk transaction

Tạo một chunk có nhiều item, cho một lần gửi thất bại và xác nhận:

- Writer ném lỗi để step xử lý.
- Database changes trong chunk rollback nếu thuộc cùng transaction.
- Message đã được broker nhận trước đó có thể vẫn tồn tại nếu broker không tham gia transaction chung.
- Retry/restart có thể gửi lại event.
- Consumer idempotency ngăn duplicate business effect.

Test này cần mô phỏng cửa sổ lỗi sau publish nhưng trước database commit. Đó là cách chứng minh giới hạn transaction thực tế.

### Kiểm thử outbox

Nếu dùng outbox, kiểm tra:

- Business update và outbox insert commit/rollback cùng nhau.
- Publisher chỉ claim row pending hợp lệ.
- Broker nhận event rồi publisher crash trước khi mark published: event có thể được gửi lại.
- Consumer deduplicate bằng event ID.
- Outbox row lỗi được retry hoặc chuyển trạng thái điều tra theo policy.
- Nhiều publisher không claim trùng row theo cơ chế lease/locking.

## Lỗi thường gặp

### Gửi bất đồng bộ rồi trả về ngay

Chunk có thể commit trước khi broker xác nhận. Chờ acknowledgement hoặc có cơ chế flush/await và truyền lỗi về writer.

### Nghĩ database rollback sẽ thu hồi message

Broker là resource riêng. Dùng transaction phối hợp phù hợp hoặc transactional outbox.

### Nhầm producer acknowledgement với consumer completion

Broker nhận message không có nghĩa consumer đã xử lý. Dùng reply/status workflow nếu cần theo dõi completion.

### Không có event ID ổn định

Retry/restart có thể gửi duplicate mà consumer không nhận diện được. Tạo ID trước và giữ qua mọi lần gửi lại.

### Chọn Kafka key không phù hợp

Event cùng aggregate có thể vào partition khác nhau và mất ordering. Dùng business key ổn định nếu cần thứ tự theo aggregate.

### Retry mọi exception

Lỗi schema, authentication hoặc topic không tồn tại không phục hồi bằng retry. Phân loại transient/permanent và đặt retry budget.

### Nuốt exception trong writer

Spring Batch có thể đánh dấu chunk thành công dù message chưa được gửi. Truyền lỗi lên hoặc ghi nhận reject theo hợp đồng rõ ràng.

### Gửi message quá lớn

Broker có giới hạn kích thước và payload lớn làm tăng memory/network. Dùng object storage reference cho nội dung lớn.

### Gửi trực tiếp entity JPA

Payload có thể chứa lazy proxy, vòng tham chiếu hoặc field nội bộ. Tạo DTO/event contract riêng.

### Không version hóa schema

Consumer cũ có thể không đọc được payload mới. Quản lý schema evolution và contract test.

### Dùng skip để xử lý broker outage

Skip làm mất event nếu không có outbox/reject persistence. Lỗi hạ tầng thường cần retry/fail.

### Cho rằng writer được gọi theo từng item

Writer nhận chunk. Thiết kế batching và xử lý lỗi theo cả chunk; không giả định mỗi item có transaction riêng.

### Không kiểm tra side effect ngoài transaction

Message, file và HTTP call có thể còn lại sau rollback. Dùng idempotency, outbox hoặc compensation.

## Nguyên tắc thiết kế

Khi triển khai `ItemWriter` gửi message, hãy xác định:

1. Message là event hay command và consumer contract là gì?
2. Payload có event ID, schema version, business key và correlation metadata chưa?
3. Broker/destination/key/routing có đúng semantics không?
4. Writer có serialize đúng một lần và giới hạn payload size không?
5. Writer trả về sau acknowledgement nào: producer future, publisher confirm hay transaction commit?
6. Chunk transaction và broker transaction có thực sự được phối hợp không?
7. Có cần transactional outbox thay cho publish trực tiếp không?
8. Retry budget có tính cả retry nội bộ của producer không?
9. Consumer có idempotent để xử lý duplicate không?
10. Ordering theo aggregate/partition có được bảo đảm không?
11. Side effect có thể tồn tại sau rollback và có cơ chế reconcile không?
12. Monitoring có event ID, correlation ID, send latency, failure và retry metrics không?
13. Test đã mô phỏng broker unavailable, acknowledgement failure, duplicate, rollback và restart chưa?

`ItemWriter` là điểm tích hợp phù hợp để phát message theo chunk, nhưng writer cần xác định rõ acknowledgement và transaction semantics. Dùng event DTO có ID/schema version, key ổn định, chờ send result khi cần lỗi ảnh hưởng tới step, và phân loại retry. Khi database update và message publish phải nhất quán, transactional outbox thường là lựa chọn dễ vận hành hơn publish trực tiếp; consumer vẫn cần idempotency vì outbox publisher có thể gửi lại. Kiểm thử các cửa sổ lỗi giữa broker acknowledgement và database commit trên broker/client thực tế.

## Ghi nhớ

`ItemWriter<T>` nhận một `Chunk` và có thể chuyển từng item thành message để gửi tới Kafka, JMS hoặc RabbitMQ. Thiết kế payload ổn định với event ID, schema version, business key và correlation metadata; dùng serializer/converter phù hợp và tránh gửi entity nội bộ hoặc payload quá lớn. Với Kafka, key ảnh hưởng partition/order và future cần được chờ nếu send failure phải làm writer fail; với JMS/RabbitMQ, cấu hình transaction, confirms/returns và delivery semantics theo broker. Transaction của database chunk không tự động atomic với broker; message đã publish có thể tồn tại sau rollback, hoặc database commit có thể xảy ra khi publish thất bại. Xác định delivery guarantee, dùng retry có giới hạn, consumer idempotency và transactional outbox khi cần đồng bộ database-message. Không nuốt exception, không gửi async rồi trả về trước khi biết kết quả theo policy, và kiểm thử acknowledgement, duplicate, rollback, restart cùng broker tương đương production.
