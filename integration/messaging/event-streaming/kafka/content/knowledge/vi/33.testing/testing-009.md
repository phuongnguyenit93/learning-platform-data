# Kiểm thử lặp bản ghi, commit lỗi và giao dịch bị hủy

Kafka thường cung cấp cách xử lý theo hướng **at-least-once** khi consumer thực hiện tác dụng phụ rồi mới commit offset. Nếu ứng dụng xử lý xong một record nhưng commit offset thất bại, record có thể được giao lại sau khi consumer khởi động lại hoặc partition được gán cho consumer khác. Producer retry cũng có thể tạo ra tình huống cần kiểm soát bản ghi trùng. Vì vậy, ứng dụng phải kiểm thử khả năng xử lý lặp một cách an toàn.

Kafka transaction bổ sung khả năng ghi nhiều record và commit offset tiêu thụ trong cùng một giao dịch Kafka. Một giao dịch bị abort không được consumer dùng chế độ read_committed nhìn thấy như dữ liệu đã commit. Consumer read_uncommitted có thể đọc cả record thuộc giao dịch đã bị hủy. Những khác biệt này cần được kiểm thử trực tiếp với broker để xác nhận cấu hình và hành vi thực tế.

Bài học hướng dẫn xây dựng test cho ba tình huống thường gây lỗi trong hệ thống event streaming: duplicate delivery, commit offset thất bại và transactional record bị abort. Các ví dụ đặt trong bối cảnh Java/Spring Kafka, nơi producer, consumer, database và transaction cần phối hợp đúng.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt duplicate do retry của producer với duplicate do consumer xử lý lại.
- Giải thích vì sao commit offset thất bại có thể dẫn đến redelivery.
- Thiết kế consumer idempotent bằng event ID, inbox hoặc unique constraint.
- Viết unit test mô phỏng commit failure và kiểm tra tác dụng phụ chỉ xảy ra một lần.
- Viết integration test xác nhận read_committed bỏ qua record của transaction đã abort.
- Kiểm thử transaction commit/abort và hành vi của consumer khi đọc transactional topic.
- Kiểm tra việc commit output record cùng consumed offset trong một Kafka transaction.
- Chọn Embedded Kafka hoặc Testcontainers phù hợp với mức kiểm thử cần thiết.

## 1. Phân loại các dạng duplicate

Một record có thể xuất hiện nhiều lần ở tầng xử lý vì các nguyên nhân khác nhau. Trước khi viết test, cần xác định duplicate xảy ra ở đâu.

### Producer retry

Producer gửi record nhưng không nhận được response do timeout hoặc lỗi mạng. Producer có thể gửi lại request. Với idempotent producer, Kafka dùng producer ID và sequence number để nhận diện retry của cùng một batch trong phạm vi session và ngăn append trùng do retry được hỗ trợ.

Tuy nhiên, idempotence không loại bỏ hai lần gửi nghiệp vụ riêng biệt. Nếu ứng dụng gọi send() hai lần cho cùng một event ID, đó là hai lần gửi độc lập và Kafka có thể lưu cả hai. Idempotent producer cũng không thay thế cơ chế deduplication giữa các producer session hoặc giữa các ứng dụng khác nhau.

### Consumer redelivery

Consumer đọc record, thực hiện tác dụng phụ rồi mới commit offset. Nếu tiến trình dừng trước khi commit thành công, group có thể đọc lại record đó. Đây là hành vi bình thường của at-least-once.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant K as Kafka
    participant C as Consumer
    participant DB as Database

    K->>C: Record offset 25
    C->>DB: Cập nhật đơn hàng
    DB-->>C: Commit thành công
    C->>K: Commit offset 26
    K--xC: Commit thất bại hoặc response timeout
    Note over C,K: Group có thể đọc lại offset 25
    K->>C: Redelivery offset 25
    C->>DB: Xử lý lại record
~~~

Nếu database đã cập nhật nhưng offset chưa được commit, lần đọc lại có thể thực hiện tác dụng phụ lần thứ hai. Consumer cần idempotent để cùng một event không làm trạng thái nghiệp vụ thay đổi lặp.

### Duplicate do gửi lại sự kiện nghiệp vụ

Một dịch vụ upstream có thể gửi lại cùng event vì retry ở tầng HTTP, job chạy lại hoặc người dùng bấm gửi nhiều lần. Dù Kafka producer idempotence được bật, hai lần gọi send() riêng biệt vẫn có thể tạo hai record.

Do đó, event ID cần tồn tại xuyên suốt luồng nghiệp vụ và được dùng ở consumer hoặc hệ thống đích để nhận diện sự kiện đã xử lý.

| Nguồn duplicate | Ví dụ | Cơ chế kiểm soát |
|---|---|---|
| Producer retry cùng batch | Broker đã ghi nhưng response bị mất | Idempotent producer |
| Gửi lại nghiệp vụ | API tạo cùng event hai lần | Event ID và deduplication |
| Consumer xử lý xong nhưng commit offset lỗi | Record được đọc lại sau restart/rebalance | Consumer idempotent, inbox |
| Replay có chủ đích | Đọc lại topic từ earliest | Idempotency key và kho đích phù hợp |

## 2. Idempotency ở consumer

Một thao tác idempotent có thể thực hiện nhiều lần với cùng một đầu vào mà kết quả nghiệp vụ cuối cùng không thay đổi sau lần áp dụng đầu tiên.

Với event-driven application, một cách phổ biến là lưu event ID vào bảng inbox có unique constraint. Việc ghi event ID và cập nhật dữ liệu nghiệp vụ cần nằm trong cùng một transaction database.

Ví dụ bảng:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Consumer nhận event có ID evt-1001. Nếu ID chưa tồn tại, ứng dụng ghi ID rồi áp dụng thay đổi nghiệp vụ. Nếu ID đã tồn tại, ứng dụng bỏ qua tác dụng phụ và vẫn cho phép offset tiến lên sau khi xác nhận record đã được xử lý trước đó.

Mã minh họa với Spring:

~~~java
public record OrderPaid(
        String eventId,
        String orderId,
        BigDecimal amount
) {
}
~~~

~~~java
@Service
public class OrderPaidHandler {

    private final ProcessedEventRepository processedEvents;
    private final AccountRepository accounts;

    public OrderPaidHandler(
            ProcessedEventRepository processedEvents,
            AccountRepository accounts) {
        this.processedEvents = processedEvents;
        this.accounts = accounts;
    }

    @Transactional
    public void handle(OrderPaid event) {
        boolean firstDelivery =
                processedEvents.insertIfAbsent(event.eventId());

        if (!firstDelivery) {
            return;
        }

        accounts.applyPayment(event.orderId(), event.amount());
    }
}
~~~

insertIfAbsent cần được triển khai bằng unique constraint hoặc câu lệnh insert có xử lý conflict nguyên tử. Không nên chỉ SELECT trước rồi INSERT, vì hai consumer thread có thể cùng kiểm tra một ID chưa tồn tại và cùng thực hiện tác dụng phụ.

Nếu inbox insert và cập nhật tài khoản nằm trong cùng transaction database, lỗi giữa hai thao tác sẽ rollback cả hai. Nếu tác dụng phụ là gọi API bên ngoài, transaction database không thể rollback API đó; hãy truyền event ID làm idempotency key cho dịch vụ đích hoặc dùng một quy trình phối hợp phù hợp.

## 3. Unit test: gửi cùng event hai lần chỉ tạo một tác dụng phụ

Unit test nên xác nhận invariant nghiệp vụ, không phụ thuộc vào cách Kafka phân phối record.

Ví dụ JUnit 5:

~~~java
class OrderPaidHandlerTest {

    private ProcessedEventRepository processedEvents;
    private AccountRepository accounts;
    private OrderPaidHandler handler;

    @BeforeEach
    void setUp() {
        processedEvents = new InMemoryProcessedEventRepository();
        accounts = new InMemoryAccountRepository();
        handler = new OrderPaidHandler(processedEvents, accounts);
    }

    @Test
    void duplicateEventChangesAccountOnlyOnce() {
        OrderPaid event = new OrderPaid(
                "evt-1001",
                "order-42",
                new BigDecimal("125.00")
        );

        handler.handle(event);
        handler.handle(event);

        assertEquals(
                new BigDecimal("125.00"),
                accounts.balanceFor("order-42")
        );
        assertEquals(1, processedEvents.countByEventId("evt-1001"));
    }
}
~~~

Repository in-memory chỉ là test double cho logic. Cần thêm integration test với database thật hoặc database test tương thích để xác nhận unique constraint, transaction rollback và xử lý conflict đồng thời.

Các trường hợp nên bổ sung:

- Hai thread xử lý cùng event ID đồng thời.
- Cùng event ID nhưng payload khác nhau: hệ thống phải phát hiện hoặc ghi nhận vi phạm hợp đồng, không âm thầm coi là một sự kiện hợp lệ khác.
- Hai event ID khác nhau nhưng cùng order ID: cả hai là sự kiện riêng và phải áp dụng theo quy tắc nghiệp vụ.
- Database lỗi sau khi inbox insert: transaction rollback, lần thử lại vẫn có thể xử lý.
- Database commit thành công nhưng Kafka offset chưa commit: lần giao lại không tạo thêm tác dụng phụ.

## 4. Commit offset thất bại có thể làm record được giao lại

Với consumer tắt auto commit và dùng manual commit, ứng dụng thường xử lý record trước rồi gọi commitSync hoặc commitAsync. Nếu commit thất bại, group có thể chưa ghi nhận offset mới. Khi partition được giao lại hoặc consumer khởi động lại, record đã xử lý có thể được đọc lần nữa.

Ví dụ xử lý thủ công:

~~~java
ConsumerRecord<String, OrderPaid> record = records.iterator().next();

handler.handle(record.value());

TopicPartition partition =
        new TopicPartition(record.topic(), record.partition());

OffsetAndMetadata nextOffset =
        new OffsetAndMetadata(record.offset() + 1);

consumer.commitSync(Map.of(partition, nextOffset));
~~~

Offset được commit là vị trí tiếp theo cần đọc, nên phải dùng record.offset() + 1. Trong ứng dụng thực tế, cần commit đúng các offset đã xử lý liên tục của từng partition, đặc biệt khi consumer xử lý bất đồng bộ hoặc poll nhiều record.

### Các nguyên nhân commit thất bại

- Consumer đã mất quyền sở hữu partition sau rebalance.
- Commit được gửi với generation hoặc member metadata đã lỗi thời.
- Broker hoặc group coordinator không phản hồi trước timeout.
- Consumer bị đóng hoặc mất kết nối khi commit đang diễn ra.
- Ứng dụng commit offset không hợp lệ hoặc vượt quá vị trí đã xử lý.

CommitFailedException thường liên quan đến việc group không còn chấp nhận commit từ consumer đó, ví dụ do rebalance. TimeoutException có thể làm kết quả commit không rõ ràng: request có thể đã được broker xử lý nhưng response không đến được client. Vì vậy, không được kết luận mọi commit exception đều đồng nghĩa offset chắc chắn chưa được lưu.

### Kiểm thử commit failure bằng test double

Tách thao tác commit thành một dependency nhỏ giúp mô phỏng lỗi xác định trong unit test:

~~~java
public interface OffsetCommitter {
    void commit(TopicPartition partition, long nextOffset);
}
~~~

~~~java
public class OrderConsumerWorker {

    private final OrderPaidHandler handler;
    private final OffsetCommitter committer;

    public OrderConsumerWorker(
            OrderPaidHandler handler,
            OffsetCommitter committer) {
        this.handler = handler;
        this.committer = committer;
    }

    public void process(ConsumerRecord<String, OrderPaid> record) {
        handler.handle(record.value());

        TopicPartition partition =
                new TopicPartition(record.topic(), record.partition());

        committer.commit(partition, record.offset() + 1);
    }
}
~~~

Test mô phỏng commit thất bại sau khi handler đã chạy:

~~~java
@Test
void redeliveryAfterCommitFailureDoesNotRepeatSideEffect() {
    OrderPaid event = new OrderPaid(
            "evt-2001",
            "order-77",
            new BigDecimal("80.00")
    );

    ConsumerRecord<String, OrderPaid> record =
            new ConsumerRecord<>("orders.paid", 0, 15L, "order-77", event);

    OffsetCommitter failingCommitter = (partition, offset) -> {
        throw new SimulatedCommitFailure();
    };

    OrderConsumerWorker firstAttempt =
            new OrderConsumerWorker(handler, failingCommitter);

    assertThrows(
            SimulatedCommitFailure.class,
            () -> firstAttempt.process(record)
    );

    OffsetCommitter successfulCommitter = (partition, offset) -> {
        // Test double: commit thành công.
    };

    OrderConsumerWorker retry =
            new OrderConsumerWorker(handler, successfulCommitter);

    retry.process(record);

    assertEquals(
            new BigDecimal("80.00"),
            accounts.balanceFor("order-77")
    );
}
~~~

Test này chứng minh handler idempotent khi cùng record được giao lại sau commit failure. Nó không thay thế integration test với Kafka group coordinator; test double chỉ kiểm tra phản ứng của ứng dụng tại ranh giới commit.

### Kiểm thử redelivery với broker thật

Một integration test có thể:

1. Tạo topic một partition và consumer group có ID cố định.
2. Gửi một event vào topic.
3. Consumer A đọc record, thực hiện tác dụng phụ vào kho test.
4. Dừng consumer A trước khi commit offset.
5. Khởi động consumer B với cùng group ID.
6. Xác nhận consumer B nhận lại record.
7. Chạy handler idempotent và xác nhận tác dụng phụ chỉ xảy ra một lần.

Để kiểm thử commit failure cụ thể, có thể dùng một commit adapter cho phép inject lỗi hoặc tạo tình huống rebalance có kiểm soát. Không nên dựa vào timing ngẫu nhiên của một rebalance để làm test duy nhất vì dễ gây flaky test.

Với timeout commit, cần kiểm thử cả hai khả năng: broker chưa lưu offset và broker đã lưu offset nhưng response bị mất. Cơ chế idempotency phải giữ an toàn trong cả hai trường hợp.

## 5. Idempotent producer và phạm vi bảo vệ

Producer có thể bật idempotence để Kafka nhận diện retry của batch trong cùng producer session:

~~~properties
enable.idempotence=true
acks=all
retries=2147483647
max.in.flight.requests.per.connection=5
~~~

Các Kafka client hiện đại thường bật idempotence mặc định khi các cấu hình tương thích, nhưng nên cấu hình và kiểm tra rõ theo phiên bản client. Khi idempotence bật, max.in.flight.requests.per.connection phải nằm trong giới hạn được Kafka hỗ trợ; giá trị tối đa hiện nay là 5.

Spring Boot có thể cấu hình:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
~~~

Producer idempotence bảo vệ khỏi duplicate do retry được nhận diện bằng producer ID và sequence number. Nó không đảm bảo mỗi event ID chỉ tồn tại một lần trong topic nếu ứng dụng chủ động gọi send nhiều lần, nếu producer khác gửi cùng event, hoặc nếu một lần phát lại nghiệp vụ tạo batch mới.

Vì vậy, test cần phân biệt:

| Kiểm thử | Điều cần xác nhận |
|---|---|
| Gọi send hai lần với cùng event ID | Hai lần gửi độc lập có thể tạo hai record |
| Retry cùng batch trong producer session | Idempotence ngăn duplicate do retry được hỗ trợ |
| Producer restart rồi gửi lại event cũ | Consumer vẫn cần deduplication theo event ID |
| Hai producer gửi cùng event ID | Idempotency ở tầng nghiệp vụ/database bảo vệ tác dụng phụ |

Để kiểm thử retry ở mức broker, có thể dùng proxy mạng hoặc fault injection để làm mất response sau khi broker đã nhận request. Đây là kiểm thử nâng cao; không nên thay bằng việc gọi send hai lần rồi kết luận idempotence hoạt động.

## 6. Transactional record và trạng thái aborted

Kafka producer transaction cho phép nhóm nhiều lần gửi thành một đơn vị commit hoặc abort. Nếu producer gọi abortTransaction, các record thuộc transaction đó không được xem là dữ liệu đã commit.

Consumer có thuộc tính isolation.level để chọn dữ liệu được đọc:

| Giá trị | Hành vi |
|---|---|
| read_uncommitted | Đọc cả record transactional đã commit, đang mở và đã abort (theo tiến độ log có thể quan sát) |
| read_committed | Chỉ trả về record transactional đã commit và record không transactional; bỏ qua record của transaction bị abort |

read_uncommitted là giá trị mặc định của Kafka consumer. Với luồng dữ liệu có giao dịch, ứng dụng downstream thường cần read_committed để không áp dụng các record đã bị hủy.

### Last Stable Offset (LSO)

Với read_committed, consumer không đọc vượt qua Last Stable Offset (LSO), tức ranh giới an toàn trước transaction đang mở sớm nhất trong partition. Nếu có một transaction chưa kết thúc, các record phía sau có thể chưa được trả về cho consumer read_committed cho đến khi transaction commit hoặc abort.

Điều này có thể làm consumer tạm thời không thấy record đã được append phía sau một transaction đang mở, dù log end offset đã tăng. Khi kiểm thử, cần phân biệt log end offset với LSO và không kết luận consumer bị mất dữ liệu chỉ vì record chưa xuất hiện trong poll.

~~~mermaid
flowchart TD
    A["Append record trong transaction T1"] --> B["T1 đang mở"]
    B --> C["Record thường phía sau"]
    C --> D{"T1 kết thúc thế nào?"}
    D -->|Commit| E["read_committed có thể đọc T1 và record phía sau"]
    D -->|Abort| F["read_committed bỏ qua record T1"]
    F --> G["read_committed tiếp tục record phía sau"]
    B --> H["read_uncommitted có thể thấy record T1 trước khi kết thúc"]
~~~

## 7. Integration test: read_committed bỏ qua transaction đã abort

Transaction semantics phải được kiểm thử với Kafka broker thật hoặc môi trường test hỗ trợ transaction. Mock producer/consumer không thể chứng minh broker đã ghi transaction marker và áp dụng isolation đúng.

Producer transactional cần có transactional.id duy nhất trong phạm vi các producer đang hoạt động và gọi initTransactions() trước khi gửi:

~~~java
Properties producerProps = new Properties();
producerProps.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        bootstrapServers
);
producerProps.put(
        ProducerConfig.TRANSACTIONAL_ID_CONFIG,
        "testing-abort-" + UUID.randomUUID()
);
producerProps.put(
        ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
        "true"
);
producerProps.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName()
);
producerProps.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName()
);

KafkaProducer<String, String> producer =
        new KafkaProducer<>(producerProps);

producer.initTransactions();
~~~

Gửi một record rồi abort:

~~~java
producer.beginTransaction();

producer.send(
        new ProducerRecord<>(
                "tx-events",
                "order-42",
                "must-not-be-visible-as-committed"
        )
).get();

producer.abortTransaction();
~~~

Sau khi abort hoàn tất, gửi một record thường làm mốc kết thúc cho test:

~~~java
nonTransactionalProducer.send(
        new ProducerRecord<>("tx-events", "marker", "after-abort")
).get();
~~~

Tạo hai consumer có group ID riêng và cấu hình khác nhau:

~~~java
Properties consumerProps = new Properties();
consumerProps.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        bootstrapServers
);
consumerProps.put(
        ConsumerConfig.GROUP_ID_CONFIG,
        "abort-test-" + UUID.randomUUID()
);
consumerProps.put(
        ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
        "earliest"
);
consumerProps.put(
        ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
        "false"
);
consumerProps.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName()
);
consumerProps.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName()
);

// Chọn một trong hai chế độ:
consumerProps.put(
        ConsumerConfig.ISOLATION_LEVEL_CONFIG,
        "read_committed"
);
~~~

Kết quả mong đợi:

| Consumer | Record trong transaction đã abort | Record marker sau abort |
|---|---|---|
| read_uncommitted | Có thể đọc được | Đọc được |
| read_committed | Không trả về | Đọc được |

Trong test, poll cho đến khi nhận marker hoặc hết timeout. Với read_committed, marker xác nhận consumer đã đi qua ranh giới của transaction đã abort. Nếu chỉ poll một lần rồi thấy danh sách rỗng, test có thể kết luận sai vì broker chưa trả dữ liệu hoặc LSO chưa tiến tới marker.

Sau khi xác nhận, đóng consumer và producer trong finally hoặc try-with-resources để giải phóng connection.

## 8. Kiểm thử commit và abort của Kafka transaction

Ngoài việc xác nhận consumer không thấy record aborted, cần kiểm thử transaction commit hiển thị đầy đủ các record dự kiến.

### Transaction commit

1. Producer gọi beginTransaction().
2. Producer gửi một hoặc nhiều record.
3. Producer gọi commitTransaction().
4. Consumer read_committed đọc được tất cả record trong transaction.

Nếu transaction gồm nhiều output record, consumer read_committed không được nhìn thấy một phần transaction rồi coi đó là transaction đã hoàn tất. Transaction marker quyết định khả năng hiển thị của các record.

### Transaction abort

1. Producer gọi beginTransaction().
2. Producer gửi record.
3. Producer gọi abortTransaction().
4. Consumer read_committed không trả về record thuộc transaction đó.
5. Consumer read_uncommitted có thể trả về record đã abort.

Cần test cả commit và abort, vì chỉ kiểm tra abort không chứng minh đường commit hoạt động đúng.

### Transaction timeout và producer fencing

Transaction có thể bị abort do ứng dụng chủ động, timeout hoặc producer bị fence. Nếu hai producer dùng cùng transactional.id, producer mới có thể fence producer cũ. Producer cũ không được tiếp tục commit transaction sau khi bị fence.

Test nên xác nhận:

- Producer bị fence nhận lỗi khi tiếp tục thao tác transactional.
- Transaction đã bị abort không xuất hiện với consumer read_committed.
- Producer mới với transactional ID đó có thể khởi tạo session mới theo đúng quy trình.
- Ứng dụng xử lý lỗi transaction và không tiếp tục coi record là đã commit.

Không dùng chung transactional.id cố định giữa nhiều test chạy song song. Hãy tạo ID riêng theo test hoặc worker để tránh các test fence lẫn nhau.

## 9. Consume-transform-produce: commit output và offset nguyên tử

Một mẫu xử lý quan trọng là consumer đọc input, producer ghi output rồi commit offset input trong cùng transaction Kafka. Nếu transaction commit, output và offset cùng có hiệu lực. Nếu transaction abort, output không hiển thị với read_committed và offset input không được tiến lên theo transaction đó.

Producer transaction hỗ trợ thao tác:

~~~java
producer.beginTransaction();

producer.send(
        new ProducerRecord<>(
                "orders.enriched",
                orderId,
                enrichedEvent
        )
);

producer.sendOffsetsToTransaction(
        Map.of(
                inputPartition,
                new OffsetAndMetadata(inputRecord.offset() + 1)
        ),
        consumer.groupMetadata()
);

producer.commitTransaction();
~~~

Consumer đầu vào phải tắt auto commit. Offset truyền vào sendOffsetsToTransaction là offset tiếp theo cần đọc, không phải offset vừa xử lý.

Test hai nhánh:

| Kết quả transaction | Output topic với read_committed | Input group offset |
|---|---|---|
| Commit | Output record xuất hiện | Offset được tiến lên |
| Abort | Output record không xuất hiện | Offset không được commit bởi transaction đó |

Sau nhánh abort, khởi động lại consumer cùng group ID và xác nhận input record được đọc lại. Đây là kiểm thử quan trọng để phát hiện trường hợp ứng dụng ghi output nhưng không commit offset nguyên tử hoặc commit offset ngoài transaction.

Khi kiểm tra offset, dùng AdminClient hoặc consumer group describe để đọc committed offset sau khi transaction hoàn tất. Không chỉ dựa vào consumer position trong bộ nhớ của consumer cũ vì position có thể đã tiến lên do poll dù committed offset chưa thay đổi.

## 10. Spring Kafka: transaction và test

Spring Kafka hỗ trợ transaction thông qua transactional producer factory và KafkaTransactionManager hoặc transaction của listener container. Khi dùng transaction, producer factory cần transactionIdPrefix duy nhất cho các instance producer đang chạy.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: local-orders-tx-
      properties:
        acks: all
        enable.idempotence: true
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Prefix phải duy nhất giữa các application instance có thể chạy đồng thời trong cùng cluster. Spring Kafka sẽ tạo transactional ID cụ thể từ prefix và suffix của producer.

Với KafkaTemplate, có thể kiểm thử transaction cục bộ bằng executeInTransaction:

~~~java
@Test
void abortedTemplateTransactionIsInvisibleToReadCommittedConsumer() {
    assertThrows(
            IllegalStateException.class,
            () -> kafkaTemplate.executeInTransaction(operations -> {
                operations.send(
                        "orders.transactional",
                        "order-42",
                        "temporary-output"
                );

                throw new IllegalStateException("force abort");
            })
    );

    // Poll consumer cấu hình isolation.level=read_committed.
    // Xác nhận không có temporary-output.
}
~~~

Khi callback ném exception, transaction được abort và exception được truyền ra caller. Test cần chờ consumer đọc qua ranh giới log phù hợp trước khi khẳng định record không xuất hiện.

Đối với listener container dùng transaction manager, cần kiểm thử cả exception trong listener và rollback behavior. Tùy cấu hình, exception có thể khiến transaction abort, record được giao lại hoặc chuyển sang error handler/recoverer. Hãy xác nhận rõ chính sách retry và DLT của ứng dụng thay vì giả định mọi exception đều dẫn đến cùng hành vi.

### Embedded Kafka hay Testcontainers?

| Công cụ | Phù hợp với | Lưu ý |
|---|---|---|
| Embedded Kafka | Test Spring Kafka nhanh trong JVM, kiểm tra listener và serialization cơ bản | Phiên bản broker và cấu hình cần tương thích; kiểm tra khả năng hỗ trợ transaction của phiên bản được dùng |
| Testcontainers Kafka | Integration test gần với broker triển khai, transaction, isolation, group và network | Khởi động chậm hơn, cần Docker |
| MockConsumer / test double | Unit test logic xử lý, commit failure injection, retry policy | Không xác minh broker transaction marker, replication hoặc metadata thực |

Với aborted transaction và read_committed, ưu tiên integration test với broker thật. Với logic deduplication, test double và database integration test thường cho phản hồi nhanh hơn. Không cần ép mọi test thành một loại duy nhất.

## 11. Test matrix cho pipeline Kafka

Một bộ kiểm thử tốt cần kiểm tra kết quả quan sát được ở consumer và hệ thống đích, không chỉ kiểm tra producer method đã được gọi.

| Tình huống | Thiết lập | Kết quả mong đợi |
|---|---|---|
| Gửi cùng event ID hai lần | Gọi producer hai lần hoặc phát lại record | Consumer chỉ tạo một tác dụng phụ nghiệp vụ |
| Producer retry cùng batch | Idempotence bật và fault injection | Không append duplicate do retry được hỗ trợ |
| Database commit, Kafka offset commit lỗi | Xử lý record rồi inject lỗi commit | Record có thể được giao lại nhưng tác dụng phụ không lặp |
| Commit offset trước khi xử lý xong | Mô phỏng sai thứ tự commit | Test phát hiện nguy cơ bỏ qua record sau restart |
| Transaction commit | Gửi record trong transaction rồi commit | read_committed nhìn thấy record |
| Transaction abort | Gửi record rồi abort | read_committed không nhìn thấy record |
| Đọc aborted record | Cùng topic với read_uncommitted | Có thể nhìn thấy record đã abort |
| Transaction đang mở | Gửi record, giữ transaction chưa kết thúc | read_committed dừng tại LSO |
| Consume-transform-produce commit | Output và input offset trong một transaction | Cả output và offset được commit |
| Consume-transform-produce abort | Abort transaction sau khi gửi output | Output không hiển thị và input offset không tiến theo transaction |
| Producer bị fence | Hai producer dùng cùng transactional ID | Producer cũ không thể tiếp tục commit |

Nên chạy các test có trạng thái group và topic riêng biệt. Dùng topic/group ID duy nhất theo test hoặc dọn dữ liệu theo quy trình xác định để test không phụ thuộc thứ tự chạy.

## 12. Tránh flaky test và false positive

### Không kiểm tra bằng một lần poll

Consumer có thể cần thời gian lấy metadata, nhận assignment, đợi transaction marker hoặc đợi LSO tiến lên. Dùng deadline hữu hạn và poll lặp đến khi đạt điều kiện mong đợi. Tránh sleep cố định dài vì làm suite chậm và vẫn không bảo đảm đồng bộ.

### Tách topic và group giữa các test

Nếu nhiều test cùng dùng topic và group ID, record từ test trước có thể làm test sau đọc nhầm dữ liệu. Mỗi test nên dùng tên topic/group riêng hoặc một fixture có cleanup và offset được kiểm soát.

### Đợi assignment trước khi gửi record

Nếu test consumer dùng subscribe theo group, chờ partition assignment hoàn tất trước khi gửi hoặc kiểm tra dữ liệu. Nếu dùng assign trực tiếp, ghi rõ partition được chỉ định và seek về offset mong muốn.

### Không coi empty poll là bằng chứng abort

Một lần poll rỗng có thể do dữ liệu chưa sẵn sàng, consumer chưa nhận metadata hoặc transaction chưa hoàn tất. Hãy dùng marker sau transaction và deadline để xác định consumer đã đi qua vùng dữ liệu cần kiểm tra.

### Kiểm tra committed offset riêng với consumer position

Consumer position là vị trí hiện tại trong tiến trình consumer, còn committed offset là tiến độ lưu cho group. Khi test transaction hoặc commit failure, phải kiểm tra committed offset từ broker sau khi thao tác hoàn tất.

### Kiểm soát resource và timeout

Đóng producer, consumer, AdminClient và container sau test. Transaction timeout, request timeout và test deadline cần đủ lớn cho CI nhưng vẫn hữu hạn. Nếu test cần chờ broker khởi động hoặc transaction hoàn tất, hãy đồng bộ bằng điều kiện quan sát thay vì tăng timeout vô hạn.

## 13. Checklist trước khi hoàn tất test

- [ ] Đã phân biệt duplicate do producer retry, duplicate nghiệp vụ và consumer redelivery.
- [ ] Producer idempotence được cấu hình và test đúng phạm vi.
- [ ] Consumer có event ID hoặc cơ chế idempotency phù hợp.
- [ ] Inbox insert và tác dụng phụ database nằm trong cùng transaction.
- [ ] Test mô phỏng commit failure sau khi tác dụng phụ đã hoàn thành.
- [ ] Integration test xác nhận record có thể được giao lại sau khi offset chưa commit.
- [ ] read_committed bỏ qua record thuộc transaction đã abort.
- [ ] read_uncommitted thể hiện khác biệt với read_committed.
- [ ] Test transaction commit và abort đều có assertion.
- [ ] Đã kiểm tra LSO khi transaction đang mở.
- [ ] Nếu consume-transform-produce, output và input offset được commit trong cùng transaction.
- [ ] Test dùng topic/group/transactional ID tách biệt và đóng tài nguyên sau khi chạy.
- [ ] Không dùng một empty poll làm bằng chứng duy nhất rằng record đã abort không thể đọc được.

## Kết luận

Duplicate delivery là điều cần dự liệu trong hệ thống Kafka, đặc biệt khi consumer thực hiện tác dụng phụ rồi mới commit offset. Producer idempotence xử lý retry của batch trong phạm vi hỗ trợ, còn event ID và consumer idempotency bảo vệ nghiệp vụ khi record được gửi hoặc xử lý lại. Commit failure có thể khiến record được giao lại, và timeout còn có thể tạo trạng thái commit không rõ ràng.

Kafka transaction cho phép commit hoặc abort một nhóm record; read_committed chỉ trả về dữ liệu đã commit và tuân theo Last Stable Offset. Khi kết hợp output record với consumed offset trong cùng transaction, ứng dụng có thể kiểm soát tính nguyên tử của pipeline Kafka. Hãy dùng unit test cho logic idempotency và commit failure, integration test với broker thật cho transaction/isolation, rồi xác nhận kết quả ở cả topic, committed offset và hệ thống đích.

