# Transaction với broker

Trong Spring Batch, một Step có thể nhận message từ broker, xử lý dữ liệu rồi gửi message sang broker khác. Broker có thể là JMS provider như ActiveMQ/Artemis, Apache Kafka hoặc một hệ thống messaging khác. Khi một chunk vừa cập nhật database vừa acknowledge message đầu vào hoặc publish message đầu ra, câu hỏi quan trọng là: các thao tác đó có commit hoặc rollback cùng nhau hay không?

Một transaction của Spring Batch không tự động bao phủ mọi tài nguyên mà code sử dụng. Transaction manager quản lý một loại resource hoặc một transaction coordinator cụ thể. Database transaction, JMS local transaction và Kafka transaction có phạm vi khác nhau. Nếu chúng không cùng tham gia một transaction phân tán, lỗi giữa các bước commit có thể tạo message bị mất, message trùng hoặc trạng thái database không khớp với broker.

Thiết kế cần xác định rõ transaction boundary, thứ tự commit, chính sách redelivery, idempotency và cơ chế phục hồi. Với nhiều hệ thống, transactional outbox/inbox thường là lựa chọn thực tế hơn việc cố gắng tạo một transaction phân tán xuyên suốt mọi resource.

## 1. Broker transaction là gì?

Message broker lưu trữ và chuyển message giữa producer và consumer. Một số thao tác broker có thể được quản lý trong transaction:

- Nhận message và chỉ acknowledge khi transaction commit.
- Gửi message và chỉ làm message hiển thị cho consumer sau khi transaction commit.
- Commit offset/position của consumer cùng với message được publish, nếu broker hỗ trợ transaction cho luồng đó.
- Rollback transaction để message đầu vào được redeliver hoặc message đầu ra không được publish.

Transaction broker giúp gom các thao tác messaging vào một đơn vị commit theo semantics của broker. Nhưng transaction broker không mặc nhiên bao gồm database hoặc file system.

Ví dụ, một consumer nhận message `OrderCreated`, ghi order vào database rồi gửi `OrderAccepted` đến broker. Có ít nhất ba thao tác:

1. Nhận/acknowledge `OrderCreated`.
2. Ghi dữ liệu order vào database.
3. Publish `OrderAccepted`.

Nếu database commit nhưng broker rollback, dữ liệu và message không còn đồng bộ. Nếu broker commit trước nhưng database rollback, consumer có thể đã xác nhận message trong khi dữ liệu nghiệp vụ chưa được lưu.

## 2. Transaction boundary trong chunk-oriented Step

Spring Batch thường thực hiện một chunk trong một transaction:

```text
Begin chunk transaction
       |
       v
Read item(s)
       |
       v
Process item(s)
       |
       v
Write chunk
       |
       v
Update ItemStream / ExecutionContext
       |
       v
Commit transaction
```

Transaction manager được truyền vào `chunk(size, transactionManager)` quản lý transaction của chunk. Reader, processor và writer có thể thực hiện thao tác trên broker, nhưng các thao tác đó chỉ thuộc transaction của chunk nếu chúng thực sự tham gia cùng transaction manager/coordinator và resource được enlist đúng cách.

Ví dụ, `DataSourceTransactionManager` quản lý JDBC connection. Nó không tự quản lý một JMS Session hoặc Kafka producer transaction. Tương tự, `JmsTransactionManager` quản lý một JMS ConnectionFactory; nó không tự commit database transaction. Dùng cùng một Step không có nghĩa mọi resource tự động atomic.

## 3. Local transaction và distributed transaction

**Local transaction** chỉ bao phủ một resource hoặc một transaction domain. Ví dụ:

- JDBC transaction trên một database.
- JMS transacted session trên một ConnectionFactory.
- Kafka producer transaction trên một Kafka cluster.

**Distributed transaction** phối hợp nhiều resource thông qua một transaction coordinator, thường dùng XA/JTA và two-phase commit nếu tất cả resource hỗ trợ XA.

| Cách quản lý | Resource được bao phủ | Giới hạn chính |
|---|---|---|
| `DataSourceTransactionManager` | Một JDBC DataSource | Không tự enlist JMS/Kafka |
| `JmsTransactionManager` | Một JMS ConnectionFactory | Không tự enlist database |
| `KafkaTransactionManager` | Kafka producer transaction | Không tự enlist JDBC database |
| `JtaTransactionManager` với XA | Các XA resource được enlist | Cần XA support, coordinator, recovery và vận hành phức tạp hơn |
| Outbox/inbox | Nhiều local transaction được phối hợp bằng dữ liệu bền vững và retry | Eventual consistency; cần idempotency/deduplication |

Không nên chọn XA chỉ vì muốn “một transaction cho tất cả”. Cần xác nhận broker, database, driver, transaction coordinator và deployment environment đều hỗ trợ XA và recovery. Nếu không, outbox/inbox thường dễ vận hành hơn.

## 4. Nhận JMS message trong transaction

Với JMS, một transacted Session có thể nhận message và chỉ hoàn tất acknowledgement khi transaction commit. Nếu transaction rollback, message có thể được redeliver theo cấu hình broker.

Spring cung cấp `JmsTransactionManager` để quản lý local transaction của một JMS `ConnectionFactory`:

```java
@Bean
public PlatformTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
```

Nếu một Step chỉ xử lý JMS resource và không cần atomic commit với database, có thể dùng transaction manager này cho chunk Step. Các thao tác JMS thực hiện qua Spring-managed `JmsTemplate` có thể tham gia transaction đang hoạt động nếu cùng ConnectionFactory và được cấu hình phù hợp.

Điều cần nhớ là `JmsTransactionManager` là local transaction manager. Nếu writer của Step còn ghi JDBC bằng một `DataSource` khác, database operation không tự động nằm trong JMS transaction.

## 5. Publish JMS message trong transaction

Một `JmsTemplate` có thể gửi message trong JMS transaction hiện tại. Ví dụ writer gửi event cho từng item:

```java
@Bean
public ItemWriter<OrderAccepted> jmsOrderWriter(JmsTemplate jmsTemplate) {
    return chunk -> {
        for (OrderAccepted event : chunk) {
            jmsTemplate.convertAndSend("orders.accepted", event);
        }
    };
}
```

Nếu `JmsTemplate` sử dụng đúng ConnectionFactory và tham gia transaction được `JmsTransactionManager` quản lý, các message được gửi trong cùng JMS transaction. Khi transaction commit, broker hoàn tất việc gửi; khi rollback, các send thuộc transaction đó bị rollback theo semantics của provider.

Nếu `JmsTemplate` dùng ConnectionFactory khác, tự tạo session không tham gia transaction hiện tại hoặc được cấu hình theo cách không transactional, không thể giả định send được rollback cùng chunk. Cần kiểm tra cấu hình thực tế và kiểm thử với broker đang sử dụng.

## 6. Một JMS transaction không tự atomic với database

Giả sử Step dùng `DataSourceTransactionManager` và trong writer gọi `JmsTemplate`:

```text
Database transaction                 JMS resource
---------------------                 -----------
BEGIN DB
INSERT order
                                      SEND OrderAccepted
COMMIT DB
                                      JMS send chưa commit / lỗi
```

Nếu database commit thành công nhưng JMS send không được commit, order tồn tại trong database nhưng event không được gửi. Đảo thứ tự commit cũng có rủi ro ngược lại: message đã được gửi nhưng database rollback.

Một transaction manager thông thường không thể hoàn tác transaction đã commit của resource khác. Thứ tự gọi `commit()` tuần tự không tạo ra distributed atomicity.

Nếu cả hai resource cần atomic commit, cần một coordinator hỗ trợ XA/JTA hoặc thiết kế outbox để lưu ý định phát event cùng transaction database.

## 7. XA/JTA cho database và JMS

Nếu database và JMS provider đều cung cấp XA resource, có thể phối hợp chúng trong JTA transaction. `JtaTransactionManager` làm việc với transaction coordinator; XA-aware DataSource và XA ConnectionFactory được enlist vào transaction.

Luồng two-phase commit ở mức khái niệm:

```text
Application / Spring Batch
          |
          v
JTA Transaction Coordinator
          |
          +------> XA Database Resource
          |
          +------> XA JMS Resource
                    |
          Phase 1: prepare
          Phase 2: commit / rollback
```

Trong phase prepare, các resource xác nhận có thể commit. Coordinator sau đó yêu cầu commit hoặc rollback theo quyết định chung. Nếu process hoặc coordinator dừng giữa hai phase, transaction có thể ở trạng thái in-doubt và cần recovery.

Điều kiện triển khai:

- Database cung cấp XA DataSource/driver phù hợp.
- JMS provider cung cấp XA ConnectionFactory.
- JTA coordinator được cấu hình và có durable transaction log.
- Resource được enlist đúng vào transaction.
- Recovery credentials và resource identity được cấu hình ổn định.
- Timeout, pool và giới hạn connection được điều chỉnh phù hợp.

XA tăng độ phức tạp, round trip và thời gian giữ resource. Không phải broker hoặc database nào cũng hỗ trợ XA trong mọi deployment mode. Cần kiểm tra tài liệu chính thức của provider và kiểm thử crash/recovery, không chỉ kiểm thử happy path.

## 8. Cấu hình transaction manager cho Step

Nếu kiến trúc dùng JTA để bao phủ cả database và JMS XA resource, Step cần dùng transaction manager JTA:

```java
@Bean
public Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager jtaTransactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderAccepted> processor,
        ItemWriter<OrderAccepted> writer) {

    return new StepBuilder("processOrdersStep", jobRepository)
            .<Order, OrderAccepted>chunk(100, jtaTransactionManager)
            .reader(orderReader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Đoạn code chỉ chọn transaction manager cho chunk. Nó không tự biến DataSource/JMS ConnectionFactory thành XA resource. Việc cấu hình XA pool, JTA coordinator và enlistment phải được thực hiện ở tầng hạ tầng/application server hoặc thư viện transaction coordinator.

JobRepository cũng cần được xem xét riêng: nếu repository dùng cùng JTA transaction và được cấu hình phù hợp, metadata checkpoint có thể tham gia transaction. Nếu repository dùng resource/transaction manager khác, không được giả định metadata và business data commit nguyên tử.

## 9. Kafka transaction khác JMS transaction

Kafka có transaction API cho producer. Producer transaction có thể gửi nhiều record và commit hoặc abort chúng như một đơn vị. Với consume-transform-produce, Kafka hỗ trợ transactional processing trong đó output records và consumer offsets có thể được commit trong cùng Kafka transaction theo cấu hình phù hợp.

Spring Kafka cung cấp `KafkaTransactionManager` để quản lý Kafka producer transaction:

```java
@Bean
public KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
        ProducerFactory<String, OrderEvent> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
```

Producer factory cần được cấu hình transactional ID prefix phù hợp. Spring Kafka có thể quản lý producer transaction thông qua `KafkaTemplate` và transaction manager.

Kafka transaction không giống JMS local transaction và cũng không tự enlist JDBC database. Nó quản lý transaction trong Kafka cluster, bao gồm các record được gửi và offsets khi được thực hiện trong đúng consume-transform-produce flow.

## 10. Kafka consume-transform-produce và offset commit

Trong một Kafka consume-transform-produce flow, consumer đọc input records, ứng dụng xử lý và producer gửi output records. Với Kafka transactions, output records và offsets của input có thể được commit trong cùng Kafka transaction.

```text
Kafka input topic
       |
       v
Consumer reads records
       |
       v
Transform / validate
       |
       v
Producer sends output records
       |
       v
Kafka transaction commits
       |
       +--> Output records visible to read_committed consumers
       +--> Input offsets committed
```

Nếu transaction abort, output records không được xem là committed bởi consumer dùng `isolation.level=read_committed`, và offsets không được commit trong transaction đó. Input có thể được xử lý lại.

Điều này hỗ trợ exactly-once semantics trong phạm vi Kafka consume-transform-produce khi cấu hình và cách xử lý đáp ứng yêu cầu của Kafka. Nó không bao gồm side effect ghi vào database bên ngoài, gọi HTTP hoặc ghi file.

## 11. KafkaTransactionManager trong Spring Batch

Nếu Step chỉ thực hiện công việc trong Kafka transaction, có thể cấu hình chunk Step dùng `KafkaTransactionManager` và thực hiện publish qua `KafkaTemplate` được liên kết với transaction đó.

Ví dụ writer:

```java
@Bean
public ItemWriter<OrderEvent> kafkaOrderWriter(
        KafkaTemplate<String, OrderEvent> kafkaTemplate) {
    return chunk -> {
        for (OrderEvent event : chunk) {
            kafkaTemplate.send(
                    "orders.processed",
                    Long.toString(event.orderId()),
                    event
            );
        }
    };
}
```

Step có thể dùng `KafkaTransactionManager` làm transaction manager nếu toàn bộ transaction boundary phù hợp với Kafka. Tuy nhiên, Spring Batch JobRepository thường lưu metadata trong database. Nếu JobRepository không tham gia cùng transaction, metadata commit và Kafka commit có thể tách rời.

Khi thiết kế Step có Kafka writer và database-backed JobRepository, cần quyết định rõ resource nào là primary transaction, cách đồng bộ transaction phụ, và cách phục hồi nếu một commit thành công còn commit kia thất bại. Không giả định việc chọn `KafkaTransactionManager` sẽ tự bao phủ repository database.

## 12. Database và Kafka: transaction synchronization không phải XA

Spring Kafka có thể phối hợp Kafka transaction với một transaction manager khác thông qua transaction synchronization trong một số cấu hình. Điều này cho phép sắp xếp thứ tự commit giữa database transaction và Kafka transaction, nhưng hai local transaction vẫn không trở thành một XA transaction nguyên tử.

Ví dụ, nếu database commit trước rồi Kafka commit sau:

```text
DB commit thành công
       |
       v
Kafka commit thất bại
       |
       v
Database đã đổi nhưng event chưa được publish
```

Nếu thứ tự commit ngược lại, có thể xuất hiện message đã publish trong khi database rollback hoặc commit thất bại. Transaction synchronization giúp phối hợp thứ tự và rollback trong một số giai đoạn, nhưng không thể rollback một resource đã commit độc lập.

Với database + Kafka, transactional outbox là một pattern phổ biến: lưu business data và outbox event trong cùng database transaction; publisher riêng gửi outbox event lên Kafka và đánh dấu đã gửi. Consumer downstream xử lý idempotent.

## 13. Transactional outbox

Outbox giải quyết vấn đề dual write: một ứng dụng vừa cập nhật database vừa publish message. Thay vì ghi database và broker trực tiếp trong cùng một luồng, ứng dụng ghi business data và một bản ghi outbox trong cùng database transaction.

Ví dụ bảng:

```sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(100) PRIMARY KEY,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(100) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);
```

Trong transaction xử lý order:

```java
@Transactional
public void acceptOrder(Order order) {
    orderRepository.save(order);

    OutboxEvent event = new OutboxEvent(
            UUID.randomUUID().toString(),
            order.getId().toString(),
            "ORDER_ACCEPTED",
            serialize(order)
    );
    outboxRepository.save(event);
}
```

Nếu transaction commit, cả order và outbox row đều tồn tại. Nếu rollback, cả hai đều không tồn tại. Một Spring Batch Job hoặc publisher riêng đọc outbox và gửi event lên broker.

Outbox không tạo atomic commit giữa database và broker. Nó bảo đảm ý định publish được lưu bền vững cùng business update; publisher có thể retry cho đến khi broker nhận event.

## 14. Outbox publisher trong Spring Batch

Một Job có thể đọc các outbox row chưa publish, gửi message và cập nhật trạng thái:

```text
Outbox table
    |
    v
ItemReader<OutboxEvent>
    |
    v
ItemProcessor (serialize / validate)
    |
    v
ItemWriter (publish to broker)
    |
    v
Mark published / update outbox state
```

Nếu publisher ghi `published_at` trong cùng transaction database với việc đọc/claim outbox, nhưng Kafka/JMS publish là local transaction khác, vẫn tồn tại cửa sổ lỗi giữa broker commit và database commit. Ví dụ broker nhận message rồi process crash trước khi đánh dấu outbox đã publish; lần chạy sau sẽ gửi lại message.

Vì vậy outbox thường cung cấp **at-least-once publication**. Consumer cần deduplicate bằng `event_id` hoặc xử lý idempotent. Đừng đánh dấu event đã publish trước khi gửi broker; nếu gửi thất bại sau khi đánh dấu, event có thể bị mất.

Một cách triển khai là claim event bằng trạng thái `NEW` → `IN_PROGRESS` có lease, publish, rồi đánh dấu `PUBLISHED`. Nếu worker crash, lease hết hạn và event được claim lại. Cần đảm bảo nhiều publisher không cùng xử lý một event ngoài ý muốn.

## 15. Inbox pattern cho consumer idempotent

Inbox giúp consumer xử lý message trùng một cách an toàn. Consumer lưu message ID vào bảng inbox cùng transaction với cập nhật business data.

Ví dụ:

```sql
CREATE TABLE inbox_message (
    message_id   VARCHAR(100) PRIMARY KEY,
    received_at  TIMESTAMP NOT NULL
);
```

Luồng xử lý:

1. Nhận message có `message_id` ổn định.
2. Bắt đầu database transaction.
3. Insert message ID vào inbox.
4. Nếu unique constraint báo ID đã tồn tại, message đã được xử lý; bỏ qua business update.
5. Nếu insert mới thành công, cập nhật business data.
6. Commit database transaction.
7. Acknowledge/commit offset ở broker theo cơ chế consumer.

Nếu process crash sau database commit nhưng trước broker ack, broker có thể gửi lại message. Lần sau, inbox nhận ra `message_id` đã tồn tại và không áp dụng business update lần nữa.

Inbox chỉ có tác dụng khi insert inbox row và business update nằm trong cùng database transaction. Nếu ghi inbox trước rồi business update ở transaction khác, một lỗi có thể làm message bị đánh dấu đã xử lý trong khi dữ liệu nghiệp vụ chưa được cập nhật.

## 16. At-most-once, at-least-once và exactly-once

Các thuật ngữ delivery mô tả khả năng message được xử lý bao nhiêu lần:

| Semantics | Ý nghĩa | Rủi ro |
|---|---|---|
| At-most-once | Message được giao/xử lý tối đa một lần | Có thể mất message nếu ack/offset commit trước xử lý bền vững |
| At-least-once | Message được giao ít nhất một lần cho đến khi xác nhận | Có thể nhận trùng khi xử lý xong nhưng ack chưa commit |
| Exactly-once | Hiệu ứng xử lý được bảo đảm đúng một lần trong phạm vi được định nghĩa | Cần transaction/deduplication và phạm vi bảo đảm rõ ràng |

Trong hệ thống phân tán, “exactly once” cần nói rõ là ở đâu. Kafka có thể cung cấp exactly-once cho consume-transform-produce trong Kafka transaction. Điều đó không có nghĩa một database update, một email và một HTTP call bên ngoài cũng chỉ xảy ra đúng một lần.

Với side effect ngoài broker, idempotency và inbox/outbox thường là nền tảng để tạo hiệu ứng nghiệp vụ tương đương exactly-once dù message transport có redelivery.

## 17. Acknowledge message đầu vào và database commit

Nếu Step nhận message từ broker rồi ghi database, thứ tự commit có ý nghĩa:

**Ack broker trước, commit database sau:** nếu database rollback sau khi broker đã xác nhận message, message có thể không được gửi lại và dữ liệu bị mất.

**Commit database trước, ack broker sau:** nếu database commit thành công nhưng process crash trước ack, broker redeliver message. Database có thể nhận cùng message lần nữa; cần inbox/idempotency.

```text
Database-first:
  DB commit ---- crash ---- Broker ack
      |                         |
      +-- business data saved   +-- may be redelivered
```

Với hai local transaction không có XA, thường ưu tiên tránh mất dữ liệu bằng cách commit business state trước khi acknowledge message, sau đó xử lý duplicate bằng inbox/unique key. Cách cụ thể phụ thuộc broker acknowledgement model và framework listener/reader.

## 18. Đọc message bằng Spring Batch

Spring Batch có thể dùng custom `ItemReader` hoặc integration component để nhận message từ broker. Với JMS, reader có thể dùng `JmsTemplate`; với Kafka, reader có thể dùng consumer API hoặc một integration adapter. Cần đảm bảo việc nhận message và acknowledgement tuân theo transaction model đã chọn.

Không nên viết reader chỉ gọi `receive()` rồi ack ngay nếu chunk còn có thể rollback. Nếu message đã bị ack trước khi database writer commit, lỗi writer có thể làm mất message.

Một reader transactional cần xác định:

- Message được giữ lại đến khi nào?
- Ack xảy ra khi `read()` trả item, khi chunk commit hay ở callback riêng?
- Khi chunk rollback, message có redeliver không?
- Spring Batch có buffer item đã đọc để replay trong cùng process không?
- Khi process restart, checkpoint của JobRepository có khớp broker offset/ack state không?

Đối với queue/broker reader có semantics transactional, cần cấu hình reader/transaction manager theo tài liệu integration tương ứng. Không giả định một custom `ItemReader` triển khai `ItemStream` là đủ để broker message được rollback; `ItemStream` chỉ quản lý checkpoint/lifecycle, không tự làm message consumption transactional.

## 19. Gửi message bằng ItemWriter

Một writer có thể gửi event cho mỗi item trong chunk:

```java
public class OrderEventWriter implements ItemWriter<OrderEvent> {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventWriter(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Override
    public void write(Chunk<? extends OrderEvent> chunk) {
        for (OrderEvent event : chunk) {
            kafkaTemplate.send(
                    "orders.events",
                    Long.toString(event.orderId()),
                    event
            );
        }
    }
}
```

Đoạn code thể hiện việc publish theo chunk, nhưng transaction behavior phụ thuộc KafkaTemplate và transaction manager. Nếu muốn mọi send trong chunk thuộc Kafka transaction, phải cấu hình producer factory, Kafka transaction manager và Step transaction boundary phù hợp.

Nếu Step đồng thời ghi database, hãy chọn một mô hình nhất quán: XA nếu tất cả resource hỗ trợ, hoặc outbox nếu không. Đừng chỉ thêm `@Transactional` quanh writer và nghĩ Kafka send sẽ tự atomic với JDBC.

## 20. Retry và redelivery

Broker thường redeliver message khi consumer không acknowledge/commit offset theo thời hạn hoặc transaction rollback. Spring Batch cũng có retry/skip policy ở mức item/chunk. Hai cơ chế này có thể tương tác và làm một message được xử lý nhiều lần.

Ví dụ:

```text
Broker delivers message M
       |
       v
Batch reads M
       |
       v
Processor / Writer fails
       |
       v
Chunk rollback
       |
       v
Message redelivery hoặc item replay
       |
       v
Retry processing M
```

Hãy xác định lỗi nào được retry trong cùng Step, lỗi nào làm chunk rollback, lỗi nào khiến broker redeliver, và số lần thử tổng thể. Nếu cả Spring Retry và broker redelivery đều retry, số lần xử lý thực tế có thể lớn hơn giới hạn mỗi tầng.

Các nguyên tắc:

- Retry lỗi tạm thời như broker timeout hoặc database deadlock với giới hạn và backoff.
- Không retry vô hạn lỗi schema, payload sai hoặc thiếu writer.
- Dùng message ID ổn định để deduplicate.
- Có dead-letter/quarantine policy cho poison message.
- Theo dõi delivery count, retry count và nguyên nhân cuối.
- Đảm bảo writer idempotent khi chunk được gọi lại.

## 21. Poison message và dead-letter queue

Poison message là message luôn thất bại khi xử lý, ví dụ JSON malformed, schema version không hỗ trợ hoặc dữ liệu nghiệp vụ không hợp lệ. Nếu broker redeliver liên tục, một message có thể chặn tiến độ của consumer.

Một chính sách xử lý có thể là:

1. Thử lại lỗi hạ tầng tạm thời trong giới hạn.
2. Với lỗi dữ liệu cố định, ghi payload/metadata an toàn vào quarantine hoặc dead-letter queue.
3. Chỉ acknowledge/commit input khi việc chuyển sang DLQ đã hoàn tất theo transaction policy.
4. Ghi message ID, source topic/queue, partition/offset hoặc delivery tag và error code.
5. Có quy trình sửa dữ liệu và replay từ DLQ.

Không log toàn bộ message nếu chứa token, thông tin cá nhân hoặc dữ liệu thanh toán. Dead-letter policy cần giữ đủ thông tin để điều tra nhưng phải kiểm soát quyền truy cập và retention.

## 22. Idempotency ở writer

Một writer idempotent có thể nhận cùng một item nhiều lần mà không tạo thêm hiệu ứng nghiệp vụ ngoài ý muốn.

Ví dụ database dùng unique event ID:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    order_id BIGINT NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
```

Khi ghi, có thể insert với unique constraint và xử lý duplicate theo chính sách. Cú pháp upsert phụ thuộc database. Không nên bắt mọi `DataIntegrityViolationException` rồi bỏ qua, vì lỗi constraint khác cũng có thể bị che giấu.

Với Kafka, dùng message key/event ID ổn định giúp partitioning và deduplication ở consumer. Kafka producer idempotence giảm duplicate do retry ở producer protocol, nhưng không thay thế idempotency nghiệp vụ nếu ứng dụng chủ động gửi cùng event hai lần trong hai transaction khác nhau.

## 23. Spring Batch ExecutionContext và broker offset

Spring Batch lưu checkpoint trong `ExecutionContext`; broker cũng có vị trí tiêu thụ riêng như JMS acknowledgement state hoặc Kafka consumer offset. Đây là hai loại tiến độ khác nhau.

```text
JobRepository                         Broker
-------------                         ------
StepExecutionContext                  Consumer offset / ack state
  - item count                          - partition offset
  - reader checkpoint                   - message acknowledgement
  - resource position                   - committed position
```

Nếu hai checkpoint không commit nguyên tử, có thể xảy ra lệch:

- JobRepository tiến trước broker: restart của Job nghĩ item đã commit nhưng broker có thể redeliver.
- Broker tiến trước JobRepository: broker không gửi lại message nhưng Job checkpoint chưa ghi nhận; Job có thể không khôi phục được item đó.

Để tránh mất message, cần thiết kế thứ tự commit và deduplication. Với Kafka, có thể dùng Kafka transaction để commit output và offsets trong cùng Kafka transaction khi toàn bộ consume-transform-produce nằm trong Kafka. Với database ngoài Kafka, outbox/inbox hoặc XA là lựa chọn tùy hạ tầng.

Không tự lưu offset vào `ExecutionContext` rồi commit độc lập với broker mà không có chiến lược phục hồi. Offset được ghi trong JobRepository không tự acknowledge message trên broker, và broker offset không tự cập nhật Batch checkpoint.

## 24. Chọn mô hình theo use case

| Use case | Mô hình nên cân nhắc |
|---|---|
| Chỉ nhận JMS message và xử lý trong JMS transaction | `JmsTransactionManager` nếu reader/consumer tham gia cùng local transaction |
| Chỉ publish Kafka records trong một chunk | `KafkaTransactionManager` và transactional producer |
| Nhận JMS và cập nhật database cần atomicity | XA/JTA nếu cả JMS và database hỗ trợ; nếu không, inbox/idempotency |
| Cập nhật database rồi phát Kafka event | Transactional outbox + publisher + idempotent consumer |
| Consume Kafka, transform và produce Kafka | Kafka transaction với offsets/output trong cùng transaction |
| Consume Kafka và cập nhật database | Inbox/idempotency hoặc mô hình phối hợp đã được kiểm chứng; không giả định Kafka offset và DB commit atomic |
| Gửi email/HTTP sau khi database commit | Outbox hoặc retryable dispatch; không thể rollback side effect đã xảy ra |

## 25. XA hay outbox/inbox?

XA/JTA phù hợp khi:

- Business requirement thực sự cần atomic commit xuyên database và broker.
- Mọi resource đều hỗ trợ XA.
- Hệ thống có transaction coordinator và durable recovery.
- Đội vận hành có thể xử lý in-doubt transaction, timeout và recovery log.
- Chi phí throughput/latency của 2PC chấp nhận được.

Outbox/inbox phù hợp khi:

- Chấp nhận eventual consistency trong thời gian ngắn.
- Muốn giữ database transaction local và đơn giản.
- Broker hoặc database không hỗ trợ XA.
- Cần retry, replay và audit rõ ràng.
- Có thể thiết kế consumer/writer idempotent.

Outbox/inbox không làm message chỉ được giao một lần. Chúng biến duplicate thành tình huống có thể nhận diện và xử lý an toàn. Đây thường là sự đánh đổi dễ kiểm soát hơn một distributed transaction phức tạp.

## 26. Transaction timeout và resource lifecycle

Chunk transaction có thể giữ database connection, JMS Session hoặc Kafka producer transaction trong thời gian xử lý. Nếu processor gọi API chậm hoặc xử lý CPU lâu, transaction có thể vượt timeout.

Hãy cân nhắc:

- Chunk size và thời gian xử lý mỗi chunk.
- Database transaction timeout.
- Broker transaction timeout và producer transaction timeout.
- Consumer session/visibility timeout hoặc max poll interval tùy broker.
- Connection/session/producer pool capacity.
- Deadlock và lock duration.
- Shutdown/rebalance khi Step đang xử lý.

Không giữ transaction mở trong lúc chờ người dùng hoặc gọi dịch vụ bên ngoài có latency không giới hạn. Nếu cần xử lý dài, chia thành các bước ngắn, lưu trạng thái bền vững và dùng retryable workflow.

## 27. Transactional listener và Spring Batch

Một ứng dụng có thể dùng message listener để nhận message kích hoạt Job thay vì để Step trực tiếp tiêu thụ toàn bộ payload. Trong mô hình đó, listener thường:

1. Nhận message chứa batch ID hoặc input reference.
2. Validate và tạo JobParameters.
3. Khởi chạy Spring Batch Job.
4. Acknowledge message theo chính sách sau khi đã ghi nhận việc nhận Job request.

Không nên giữ broker transaction mở trong toàn bộ thời gian Job chạy nếu Job kéo dài nhiều phút/giờ. Thay vào đó, lưu yêu cầu khởi chạy bền vững, dùng idempotency key cho Job request và để JobRepository quản lý lifecycle của Job.

Nếu listener ack message ngay sau khi gọi `JobLauncher.run()` nhưng trước khi Job request được lưu bền vững, process crash có thể làm mất yêu cầu. Cần xác định `JobLauncher` synchronous/asynchronous, JobRepository commit timing và cách listener xử lý redelivery.

## 28. Quan sát và vận hành transaction với broker

Để điều tra lỗi, cần theo dõi cả batch metadata và broker metadata:

- JobInstance/JobExecution/StepExecution ID.
- Batch ID và message ID/event ID.
- Topic/queue, partition, offset hoặc delivery tag.
- Transaction begin/commit/rollback result.
- Redelivery count và retry count.
- Outbox/inbox status.
- Dead-letter count và error code.
- Transaction timeout, coordinator recovery và in-doubt status nếu dùng XA.
- Database commit status và broker publish/ack status.

Log nên có correlation ID xuyên suốt reader, processor, writer và consumer. Tránh log raw payload chứa dữ liệu nhạy cảm.

Với outbox, theo dõi số event `NEW`, `IN_PROGRESS`, `PUBLISHED`, tuổi của event chưa publish và số lần retry. Với inbox, theo dõi duplicate count và lỗi xử lý. Với XA, theo dõi transaction recovery và resource health.

## 29. Kiểm thử transaction với broker

Unit test mock writer không thể chứng minh broker transaction commit/rollback đúng. Cần integration test với broker/database tương tự production hoặc test container phù hợp.

Các tình huống quan trọng:

1. Publish thành công và commit transaction; consumer nhận được message.
2. Writer ném exception trước commit; message đầu ra không xuất hiện nếu send thuộc transaction.
3. Database writer thành công nhưng broker commit thất bại; xác nhận recovery/outbox behavior.
4. Broker publish thành công nhưng process dừng trước khi đánh dấu outbox; consumer xử lý duplicate an toàn.
5. Consumer commit database rồi crash trước ack; message redelivery không làm business update lặp.
6. Chunk rollback; xác nhận message đầu vào được replay hoặc redeliver theo cấu hình.
7. Kafka consume-transform-produce abort; output và offset không được commit như một phần transaction.
8. Poison message vượt retry limit và được chuyển DLQ theo chính sách.
9. Job restart sau khi một chunk đã commit; JobRepository và broker position không gây mất message.
10. XA coordinator/process crash ở các giai đoạn prepare/commit và recovery hoàn tất đúng.
11. Transaction timeout, broker unavailable và connection pool exhaustion.
12. Nhiều worker cùng claim outbox event; một event không bị publish với hiệu ứng nghiệp vụ trùng.

Test phải xác nhận trạng thái cuối ở cả database và broker, không chỉ kiểm tra exception của Step. Với XA, cần test recovery thật sự chứ không chỉ rollback trong cùng process. Với outbox/inbox, cần mô phỏng crash ở khoảng giữa hai local commit.

## 30. Những nhầm lẫn thường gặp

**Cho rằng transaction của chunk tự bao phủ broker.** Chỉ resource tham gia đúng transaction manager/coordinator mới được commit cùng chunk.

**Cho rằng `JmsTransactionManager` commit database.** Đây là local transaction manager cho JMS ConnectionFactory.

**Cho rằng `KafkaTransactionManager` enlist JDBC.** Kafka transaction quản lý Kafka resource; database cần transaction manager và cơ chế phối hợp riêng.

**Cho rằng gọi send trong writer đồng nghĩa message đã commit.** Send có thể chỉ được commit khi transaction hoàn tất; semantics phụ thuộc template/session/producer configuration.

**Ack message ngay trong read() rồi mới ghi database.** Nếu database rollback sau ack, message có thể bị mất.

**Cho rằng retry không tạo duplicate.** Redelivery và retry có thể gọi writer nhiều lần; cần idempotency.

**Cho rằng Kafka exactly-once bao gồm database và HTTP.** EOS chỉ có phạm vi được Kafka transaction bảo vệ; external side effect cần outbox/inbox hoặc cơ chế riêng.

**Cho rằng transaction synchronization là XA.** Đồng bộ thứ tự commit giữa hai local transaction không cung cấp atomic rollback sau khi một resource đã commit.

**Đánh dấu outbox published trước khi broker nhận message.** Crash sau đó có thể làm event mất. Publish rồi mark có thể tạo duplicate, vì vậy consumer cần dedupe.

**Lưu broker offset riêng trong ExecutionContext và coi là ack.** JobRepository checkpoint và broker offset là hai state store khác nhau.

## 31. Cách thiết kế transaction với broker

Trước hết, liệt kê mọi side effect của một chunk: message được nhận, database được cập nhật, message được publish và checkpoint được lưu ở đâu. Xác định transaction manager của Step đang quản lý resource nào, các reader/writer có thực sự tham gia transaction đó hay không, và thứ tự commit có thể tạo cửa sổ mất/trùng dữ liệu nào.

Nếu chỉ làm việc với một broker, dùng transaction manager tương ứng và cấu hình acknowledgement/producer transaction đúng. Nếu cần atomic commit giữa database và JMS, chỉ dùng XA/JTA khi mọi resource và hạ tầng hỗ trợ đầy đủ. Với database + Kafka hoặc các hệ thống không XA, ưu tiên transactional outbox/inbox, message ID ổn định và writer/consumer idempotent.

Đối với message input, tránh acknowledge trước khi business state được lưu bền vững. Đối với message output, lưu ý định publish cùng business update trong outbox rồi publish/retry riêng. Đồng bộ checkpoint Spring Batch với broker position bằng một chiến lược có thể phục hồi, không coi hai metadata store là một transaction tự động.

Kiểm thử các điểm crash giữa commit, rollback, redelivery, retry và restart. Transaction với broker không chỉ là cấu hình một annotation; đó là quyết định về phạm vi atomicity, delivery semantics và khả năng phục hồi của toàn bộ pipeline.
