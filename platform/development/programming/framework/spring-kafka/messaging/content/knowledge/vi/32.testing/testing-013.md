# Kiểm thử transaction

Kafka transaction giúp gom nhiều thao tác ghi vào Kafka thành một đơn vị commit hoặc abort. Với Spring Kafka, transaction có thể được dùng khi producer gửi một nhóm record, hoặc khi listener đọc record đầu vào, xử lý rồi gửi output và commit offset trong cùng transaction. Kiểm thử transaction cần chứng minh **consumer chỉ nhìn thấy dữ liệu đã commit, dữ liệu của transaction abort không được công bố với `read_committed`, và offset đầu vào tiến cùng output khi dùng transactional listener**.

Chỉ kiểm tra listener đã được gọi hoặc `KafkaTemplate.send()` không ném exception là chưa đủ. Transaction là hành vi phối hợp giữa producer, broker transaction coordinator, consumer isolation level và listener container. Bài test phải quan sát trạng thái sau commit/abort từ một consumer được cấu hình đúng.

## 1. Mục tiêu của kiểm thử transaction

Một transaction test cần trả lời các câu hỏi:

- Producer có thể mở transaction, gửi record và commit thành công không?
- Khi transaction abort, consumer `read_committed` có bỏ qua các record thuộc transaction đó không?
- Nhiều output record có được commit/abort cùng nhau không?
- Với transactional listener, output và offset input có cùng commit không?
- Listener ném exception có làm transaction rollback và record được retry theo chính sách không?
- Producer có bị fencing khi transactional ID bị dùng bởi producer khác không?
- Consumer có xử lý đúng khi transaction đang mở hoặc chưa hoàn tất không?

Phạm vi EOS ở đây là trạng thái Kafka. Nếu listener cập nhật database hoặc gọi HTTP, các side effect đó nằm ngoài Kafka transaction và cần được kiểm thử riêng bằng inbox/outbox hoặc idempotency.

## 2. Phân biệt producer transaction và transactional listener

Spring Kafka hỗ trợ hai tình huống kiểm thử chính:

| Tình huống | Cách dùng | Điều cần xác minh |
| --- | --- | --- |
| Producer-only transaction | `KafkaTemplate.executeInTransaction(...)` | Các output trong callback cùng commit hoặc cùng abort |
| Transactional listener container | Gắn `KafkaTransactionManager` vào listener container | Output và offset input cùng commit/abort |

Producer-only transaction phù hợp khi ứng dụng cần publish một nhóm record nguyên tử mà không có consumer offset liên quan. Transactional listener phù hợp với luồng consume-process-produce: container bắt đầu transaction trước khi gọi listener, `KafkaTemplate` dùng cùng producer factory tham gia transaction, sau đó container gửi offset input vào transaction.

Hai tình huống có thể dùng chung broker test nhưng cần assertion khác nhau. Test producer-only không chứng minh offset consumer được commit nguyên tử. Test listener container mới kiểm tra được quan hệ giữa output và input offset.

## 3. Cấu hình broker test hỗ trợ transaction

Transaction test cần broker Kafka hỗ trợ transaction. Với broker test một node, transaction state topic phải có replication factor và min ISR phù hợp với số broker. Ví dụ `@EmbeddedKafka`:

```java
import org.springframework.kafka.test.context.EmbeddedKafka;

@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.input", "orders.output"},
        brokerProperties = {
                "transaction.state.log.replication.factor=1",
                "transaction.state.log.min.isr=1"
        },
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class KafkaTransactionIntegrationTest {
}
```

Với broker một node, đặt replication factor và min ISR bằng 1 chỉ phục vụ test. Cấu hình này không đại diện cho độ bền của cluster production nhiều broker. Nếu dùng Testcontainers, hãy kiểm tra image Kafka và broker properties có hỗ trợ transaction như môi trường cần mô phỏng.

Đảm bảo test topic được tạo trước khi chạy test và partition count cố định. Không phụ thuộc auto topic creation vì số partition mặc định có thể làm thay đổi kết quả partition assignment hoặc offset assertion.

## 4. Cấu hình Spring Kafka transaction trong test

Transactional producer factory cần `transactionIdPrefix`. Prefix phải duy nhất cho từng producer factory đang hoạt động đồng thời. Ví dụ cấu hình Spring Boot:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: test-orders-${random.uuid}-
    consumer:
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
```

`transaction-id-prefix` khiến Spring Boot cấu hình producer factory hỗ trợ transaction và transaction manager cho cấu hình auto-configured. Trong test dùng nhiều context hoặc nhiều producer factory đồng thời, hãy cấp prefix riêng để tránh `ProducerFencedException` ngoài ý muốn.

Nếu tự cấu hình Java, các thành phần cần liên kết cùng producer factory:

```java
@Bean
ProducerFactory<String, String> producerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

    var factory = new DefaultKafkaProducerFactory<String, String>(props);
    factory.setTransactionIdPrefix("test-orders-" + UUID.randomUUID() + "-");
    return factory;
}

@Bean
KafkaTransactionManager<String, String> kafkaTransactionManager(
        ProducerFactory<String, String> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
```

Transactional listener container factory phải được gắn transaction manager:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
transactionalListenerFactory(
        ConsumerFactory<String, String> consumerFactory,
        KafkaTransactionManager<String, String> transactionManager) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(transactionManager);
    return factory;
}
```

Từ Spring Kafka 3.2, dùng `setKafkaAwareTransactionManager(...)`; API `setTransactionManager(...)` cũ đã deprecated. `KafkaTemplate` dùng cùng `ProducerFactory` với transaction manager để các lệnh gửi từ listener tham gia transaction hiện tại.

## 5. Kiểm thử producer transaction commit

`KafkaTemplate.executeInTransaction(...)` mở transaction cục bộ cho callback. Nếu callback hoàn tất bình thường, transaction commit; nếu callback ném exception, transaction abort và exception được truyền ra caller.

Ví dụ gửi hai record trong một transaction:

```java
@Autowired
KafkaTemplate<String, String> kafkaTemplate;

@Test
void commitsAllRecordsInTransaction() {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders.output", "order-1", "created");
        operations.send("orders.output", "order-2", "confirmed");
        return null;
    });

    List<String> values = readCommittedValues("orders.output", 2);

    assertThat(values).containsExactlyInAnyOrder("created", "confirmed");
}
```

`readCommittedValues` là helper test tự xây dựng để consume record bằng consumer `read_committed` với timeout. Ví dụ chỉ minh họa ranh giới transaction; trong test thật nên dùng topic riêng cho mỗi test hoặc dọn topic/group state để không đọc nhầm record từ lần chạy trước.

Nếu callback trả về bình thường nhưng lệnh send hoàn tất bất đồng bộ với lỗi, `KafkaTemplate` xử lý kết quả gửi trong transaction. Đối với assertion, hãy đợi transaction callback kết thúc và sau đó đọc từ consumer test; không dùng thời điểm gọi `send()` làm bằng chứng commit.

## 6. Kiểm thử producer transaction abort

Khi callback ném exception, transaction cần abort. Consumer `read_committed` không được trả về record đã gửi trong transaction bị abort:

```java
@Test
void abortedTransactionIsInvisibleToReadCommittedConsumer() {
    assertThatThrownBy(() -> kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders.output", "order-3", "must-abort");
        throw new IllegalStateException("force rollback");
    })).isInstanceOf(IllegalStateException.class);

    List<String> values = readCommittedValues("orders.output", 1);

    assertThat(values).doesNotContain("must-abort");
}
```

Helper cần có timeout hữu hạn và topic dành riêng cho test. Với một test chỉ xác minh không có record, nên dùng poll trong một khoảng thời gian xác định sau khi transaction abort; không chờ vô hạn vì kết quả mong đợi là không có message.

Consumer `read_uncommitted` có thể nhìn thấy record thuộc transaction đã abort. Vì vậy, nếu mục tiêu là xác minh dữ liệu không được công bố cho ứng dụng downstream theo EOS, consumer test phải đặt `isolation.level=read_committed`.

## 7. Tạo consumer test với read_committed

Khi dùng `KafkaTestUtils.consumerProps(...)`, hãy override isolation level rõ ràng:

```java
Map<String, Object> consumerProps = KafkaTestUtils.consumerProps(
        "transaction-test-group",
        "false",
        embeddedKafkaBroker);
consumerProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
consumerProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");

try (Consumer<String, String> consumer = new KafkaConsumer<>(consumerProps)) {
    consumer.subscribe(List.of("orders.output"));
    // Poll bằng timeout và kiểm tra record.
}
```

Ví dụ cần import `KafkaTestUtils`, `EmbeddedKafkaBroker`, `KafkaConsumer`, `Consumer` và các cấu hình serializer/deserializer phù hợp. Một consumer test độc lập nên có group ID riêng, `enable.auto.commit=false` và `auto.offset.reset=earliest` nếu muốn đọc dữ liệu từ đầu topic.

Chờ consumer assignment trước khi dựa vào `poll()`. Với topic test mới và một partition, có thể poll đến khi assignment xuất hiện rồi tiếp tục. Không giả định `subscribe()` đồng nghĩa partition đã được gán ngay lập tức.

## 8. Kiểm thử transactional listener commit

Với transactional listener, container bắt đầu transaction trước khi gọi listener. Listener gửi output bằng `KafkaTemplate` dùng cùng producer factory. Khi listener hoàn tất, container đưa offset input vào transaction và commit.

Ví dụ listener:

```java
@Component
public class OrderTransactionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderTransactionListener(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            id = "order-transaction-listener",
            topics = "orders.input",
            groupId = "order-transaction-test",
            containerFactory = "transactionalListenerFactory")
    public void onMessage(ConsumerRecord<String, String> record) {
        kafkaTemplate.send(
                "orders.output",
                record.key(),
                "processed:" + record.value());
    }
}
```

Integration test cần:

1. Gửi một record vào `orders.input`.
2. Chờ listener xử lý và transaction commit.
3. Consume `orders.output` bằng consumer `read_committed`.
4. Xác nhận output có đúng key/value.
5. Xác minh offset group của `order-transaction-test` đã tiến qua offset input.

Để kiểm tra offset, có thể dùng `AdminClient.listConsumerGroupOffsets(...)` hoặc một consumer cùng group đọc committed offset. Offset commit thường là vị trí tiếp theo cần đọc, tức offset của record vừa xử lý cộng một trong trường hợp xử lý tuần tự một record.

Không gọi `acknowledge()` thủ công trong transactional listener chỉ để ép commit offset. Container transaction quản lý offset; hãy để exception thoát listener khi muốn rollback.

## 9. Kiểm thử rollback và redelivery của transactional listener

Một bài test quan trọng là listener gửi output rồi ném exception. Output của lần thử thất bại phải bị abort; input record được retry; lần thử thành công mới tạo output đã commit.

Có thể tạo listener test với bộ đếm:

```java
@Component
public class FailingOnceTransactionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final AtomicInteger attempts = new AtomicInteger();

    public FailingOnceTransactionListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.retry-input",
            groupId = "transaction-retry-test",
            containerFactory = "transactionalListenerFactory")
    public void onMessage(ConsumerRecord<String, String> record) {
        int attempt = attempts.incrementAndGet();
        kafkaTemplate.send("orders.retry-output", record.key(), "attempt-" + attempt);

        if (attempt == 1) {
            throw new IllegalStateException("fail first delivery");
        }
    }
}
```

`DefaultAfterRollbackProcessor` sẽ điều phối việc seek và giao lại record sau rollback theo cấu hình. Test có thể cấu hình backoff ngắn và giới hạn retry phù hợp. Sau khi lần xử lý thứ hai thành công, consumer `read_committed` trên output chỉ nên nhìn thấy `attempt-2`; `attempt-1` thuộc transaction abort và không được công bố.

Đây là ví dụ đơn giản để minh họa. Trong test thực tế, dùng listener bean riêng cho test hoặc `@MockitoBean`/cơ chế thay thế bean theo phiên bản Spring đang dùng. Tránh chia sẻ `AtomicInteger` giữa nhiều test hoặc nhiều partition nếu không có chủ đích.

## 10. Kiểm thử offset input và output cùng commit

Để chứng minh EOS của transactional listener, kiểm tra cả hai phía của transaction:

| Kết quả listener | Output `read_committed` | Offset input |
| --- | --- | --- |
| Listener thành công | Output xuất hiện | Offset tiến |
| Listener gửi output rồi ném exception | Output của lần thử lỗi không xuất hiện | Offset không tiến bởi transaction abort |
| Retry sau đó thành công | Output của lần commit thành công xuất hiện | Offset tiến cùng transaction đó |

Nếu chỉ kiểm tra output, test có thể bỏ sót lỗi offset. Nếu chỉ kiểm tra offset, test có thể bỏ sót output bị thiếu. Cần quan sát cả hai bằng consumer group và consumer output tương ứng.

Khi đọc committed offset bằng AdminClient, hãy chờ container hoàn tất transaction và dùng Awaitility để đợi offset đạt giá trị mong đợi. Không đọc ngay sau khi listener method bắt đầu hoặc sau khi producer gửi output nhưng transaction chưa commit.

## 11. Kiểm thử transaction timeout và producer fencing

Transaction timeout xảy ra khi transaction mở lâu hơn `transaction.timeout.ms` hoặc broker áp dụng giới hạn tương ứng. Producer có thể nhận lỗi khi commit hoặc thao tác tiếp theo. Test timeout nên dùng cấu hình nhỏ ở broker test và producer test riêng; không thay timeout production chỉ để test chạy nhanh.

Producer fencing xảy ra khi một producer mới khởi tạo với cùng `transactional.id` và epoch mới vô hiệu hóa producer cũ. Có thể kiểm tra fencing bằng hai producer transactional dùng cùng ID:

1. Khởi tạo producer A với transactional ID cố định và gọi `initTransactions()`.
2. Khởi tạo producer B với cùng transactional ID.
3. Thực hiện thao tác transaction tiếp theo từ producer A.
4. Xác nhận producer A bị fence và không thể tiếp tục commit transaction cũ.

Test này cần quản lý producer lifecycle cẩn thận và chỉ nên chạy trong môi trường test cô lập. Không để hai test song song dùng cùng transactional ID vì sẽ tạo fencing ngẫu nhiên.

## 12. Kiểm thử nhiều producer và nhiều instance

Trong ứng dụng Spring, `transactionIdPrefix` cần duy nhất giữa các instance chạy đồng thời. Kiểm thử cấu hình nên xác minh:

- Mỗi application context/instance nhận prefix khác nhau.
- Producer factory trong cùng instance tạo transactional ID suffix khác nhau cho producer được cache.
- Hai instance không fence lẫn nhau ngoài ý muốn.
- Khi cố tình cấu hình prefix trùng, test/diagnostic có thể nhận diện `ProducerFencedException`.

Không nên dùng prefix cố định toàn cục cho mọi test class nếu test chạy song song. Tạo prefix có UUID hoặc namespace theo test run.

## 13. Kiểm thử transaction với batch listener

Với batch listener transactional, một transaction bao bọc lần xử lý batch. Nếu listener ném exception, transaction batch rollback; offset của batch không được commit trong transaction đó.

Test cần kiểm tra:

- Batch nhận đúng số record và đúng partition/offset.
- Khi toàn batch thành công, output và offsets được commit.
- Khi một record làm listener ném exception, output đã gửi trong transaction batch bị abort.
- `AfterRollbackProcessor` xử lý retry theo semantics batch đã cấu hình.
- Side effect bên ngoài Kafka không bị giả định là rollback cùng Kafka transaction.

Không kiểm tra batch listener như nhiều record listener độc lập. Ranh giới transaction và retry khác nhau; hãy dùng batch size xác định và kiểm thử với một batch nhỏ.

## 14. Kiểm thử recovery/DLT sau rollback

Transactional listener thường dùng `AfterRollbackProcessor` thay cho việc áp dụng máy móc `DefaultErrorHandler` của listener non-transactional. Khi hết retry, record có thể được recover và publish sang DLT.

Nếu yêu cầu DLT publish và offset input được commit nguyên tử, cấu hình after-rollback recovery theo transaction, ví dụ `commitRecovered=true` với `KafkaTemplate` transactional phù hợp theo phiên bản Spring Kafka. Test cần xác minh:

- Record lỗi cuối cùng xuất hiện trên DLT.
- DLT consumer `read_committed` đọc được record sau khi recovery transaction commit.
- Offset input tiến sau recovery thành công.
- Nếu DLT publish thất bại, offset input không bị commit như thể recovery thành công.
- Header DLT giữ topic, partition, offset và exception metadata cần thiết.

Nếu DLT publish nằm ngoài transaction hoặc dùng producer factory khác, không được giả định nó nguyên tử với offset input. Hãy kiểm tra cấu hình recoverer thực tế.

## 15. Không kết hợp non-blocking retry với container transaction

`@RetryableTopic` chuyển record sang retry topic để thực hiện non-blocking retry. Cơ chế này không hỗ trợ listener container transactions.

Vì vậy, transaction test nên chọn một mô hình phù hợp:

- Transactional listener: kiểm tra rollback/retry qua `AfterRollbackProcessor`.
- Non-blocking retry: kiểm tra main/retry/DLT topology với listener không chạy container transaction.

Không cấu hình `@RetryableTopic` trên transactional listener rồi kỳ vọng input offset, retry topic và output nghiệp vụ nằm trong một Kafka transaction duy nhất.

## 16. Transaction không rollback database: kiểm thử ranh giới ngoài Kafka

Kafka transaction chỉ bao gồm Kafka records và consumer offsets được gửi vào transaction. Nó không tự rollback database, HTTP request, email hoặc file write.

Một test tích hợp có thể mô phỏng:

1. Listener cập nhật database thành công.
2. Listener gửi output Kafka.
3. Transaction Kafka abort.
4. Record input được giao lại.
5. Database update được gọi lại.

Nếu database update không idempotent, trạng thái nghiệp vụ có thể bị nhân đôi dù Kafka EOS hoạt động đúng. Kiểm thử cần chứng minh inbox/event ID ngăn side effect lặp hoặc outbox giữ business change và event trong cùng database transaction.

Đừng viết assertion rằng “listener chỉ được gọi một lần” như bằng chứng EOS. Listener có thể được gọi nhiều lần; điều cần chứng minh là trạng thái Kafka đã commit và side effect nghiệp vụ cuối cùng đúng.

## 17. Đồng bộ test bất đồng bộ và tránh flaky

Kafka transaction và listener container chạy bất đồng bộ. Các nguyên tắc giúp test ổn định:

- Chờ `CompletableFuture` của producer với timeout khi cần xác nhận send completion.
- Dùng Awaitility, `CountDownLatch` hoặc `BlockingQueue` để chờ listener và committed offset.
- Chờ consumer assignment trước khi poll dữ liệu.
- Dùng topic và group ID riêng cho từng test hoặc test class.
- Dùng transactional ID prefix riêng, đặc biệt khi test chạy song song.
- Đặt `auto.offset.reset=earliest` cho consumer test cần đọc record từ đầu.
- Dùng `read_committed` cho assertion về output đã commit.
- Không dùng `Thread.sleep` cố định làm bằng chứng transaction đã commit/abort.
- Đóng consumer, producer và container sau test.

Khi assertion timeout, ghi thêm topic, partition, offset, group ID, transaction outcome và listener assignment để chẩn đoán.

## 18. Embedded Kafka hay Testcontainers cho transaction test?

| Tiêu chí | Embedded Kafka | Testcontainers |
| --- | --- | --- |
| Khởi động | Nhanh và tích hợp trực tiếp với Spring Kafka test | Khởi động container, phụ thuộc Docker |
| Transaction | Có thể test producer transaction và listener transaction | Có thể test transaction trên broker image/version cụ thể |
| Cấu hình broker | Cần đặt transaction state replication phù hợp broker test | Có thể cấu hình gần môi trường triển khai |
| Mục đích | Transaction integration test thường xuyên | Compatibility test, broker config và môi trường gần production |

Embedded Kafka phù hợp để kiểm tra logic Spring Kafka trong suite thường xuyên. Testcontainers phù hợp khi cần kiểm tra version broker, KRaft/configuration hoặc broker image gần production. Dù dùng công cụ nào, phải kiểm tra transaction settings của broker test.

## 19. Ma trận test transaction

| Kịch bản | Producer-only | Transactional listener |
| --- | :---: | :---: |
| Gửi một record và commit | ✓ | ✓ |
| Gửi nhiều record trong một transaction | ✓ | ✓ |
| Ném exception và abort | ✓ | ✓ |
| `read_committed` không thấy aborted output | ✓ | ✓ |
| Offset input cùng commit với output |  | ✓ |
| Listener redelivery sau rollback |  | ✓ |
| `AfterRollbackProcessor` retry/recovery |  | ✓ |
| Batch transaction |  | ✓ |
| Producer fencing | ✓ | ✓ |
| DLT recovery và offset |  | ✓ |
| Database idempotency/outbox | Test riêng ở tầng ứng dụng | Test riêng ở tầng ứng dụng |

## 20. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Transaction test không khởi tạo được | Broker test thiếu transaction state replication/min ISR phù hợp | Cấu hình broker test theo số node |
| Consumer vẫn đọc record đã abort | Consumer dùng `read_uncommitted` | Đặt `isolation.level=read_committed` |
| Listener gửi output nhưng offset không tiến cùng | Container chưa gắn transaction manager hoặc template dùng factory khác | Kiểm tra `KafkaAwareTransactionManager` và ProducerFactory dùng chung |
| Listener ném exception nhưng transaction commit | Exception bị bắt và không truyền ra container | Ném exception để rollback |
| Test nhận output trùng | Test đọc cả aborted records hoặc listener retry tạo side effect ngoài Kafka | Dùng `read_committed`, kiểm tra business idempotency |
| `ProducerFencedException` ngẫu nhiên | Test dùng chung transactional ID/prefix hoặc chạy song song | Cấp prefix riêng cho từng test/instance |
| Test không thấy record | Consumer chưa assign, offset reset sai hoặc poll quá sớm | Chờ assignment, đặt `earliest`, dùng timeout |
| Offset assertion sai một đơn vị | Committed offset là vị trí tiếp theo cần đọc | So sánh với offset record đã xử lý cộng một |
| DLT có record nhưng offset input chưa tiến | Recovery/commit policy không đúng hoặc DLT publish ngoài transaction | Kiểm tra `AfterRollbackProcessor` và commitRecovered |
| Database bị cập nhật hai lần | Database nằm ngoài Kafka transaction | Dùng inbox/outbox hoặc idempotent operation |

## 21. Checklist trước khi phát hành

- [ ] Broker test hỗ trợ transaction và transaction state topic có cấu hình phù hợp.
- [ ] Producer factory có `transactionIdPrefix` riêng.
- [ ] Transaction manager và `KafkaTemplate` dùng cùng producer factory.
- [ ] Listener container được gắn `KafkaAwareTransactionManager`.
- [ ] Consumer assertion dùng `read_committed`.
- [ ] Producer-only commit/abort đã được kiểm thử.
- [ ] Transactional listener commit/rollback đã được kiểm thử.
- [ ] Output và input offset được xác minh cùng commit.
- [ ] `AfterRollbackProcessor` retry/recovery được kiểm thử.
- [ ] DLT publish và offset recovery được kiểm tra nếu có sử dụng.
- [ ] Fencing và transaction timeout được kiểm tra theo rủi ro.
- [ ] Batch listener có test riêng nếu được sử dụng.
- [ ] Database/external side effect có test idempotency/outbox riêng.
- [ ] Test có timeout, topic/group/prefix cô lập và cleanup rõ ràng.

## 22. Kết luận

Kiểm thử transaction trong Spring Kafka phải chứng minh trạng thái đã commit, không chỉ chứng minh lời gọi send hoặc listener đã chạy. Với producer-only transaction, kiểm tra các output commit/abort cùng nhau. Với transactional listener, kiểm tra output và offset input cùng commit, đồng thời xác minh rollback, redelivery và recovery qua `AfterRollbackProcessor`.

Dùng broker test hỗ trợ transaction, consumer `read_committed`, transactional ID prefix riêng và cơ chế chờ bất đồng bộ có timeout. Kiểm tra cả offset lẫn output để xác nhận atomicity. Cuối cùng, giữ ranh giới rõ ràng: Kafka transaction không bao trùm database hay external service; các side effect đó cần idempotency, inbox/outbox và bài test riêng.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Testing](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring for Apache Kafka — Embedded Kafka Broker](https://docs.spring.io/spring-kafka/reference/testing.html#embedded-kafka)
- [Apache Kafka — Transactions](https://kafka.apache.org/documentation/#transactions)
