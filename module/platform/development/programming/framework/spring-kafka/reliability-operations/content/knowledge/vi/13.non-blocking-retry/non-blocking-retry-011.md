# Non-blocking retry không hỗ trợ batch listener

## 1. Vấn đề cốt lõi

Spring Kafka cung cấp **non-blocking retry** để chuyển record xử lý lỗi sang các retry topic và tiêu thụ lại sau một khoảng trễ, thường được cấu hình qua `@RetryableTopic` hoặc `RetryTopicConfiguration`. Cơ chế này phù hợp với **record listener**: mỗi lần listener nhận và xử lý một record, và khi record thất bại, framework có thể xác định đúng record cần đưa sang retry topic.

**Non-blocking retry của Spring Kafka không hỗ trợ batch listener.** Khi listener nhận một batch gồm nhiều record trong một lần gọi, không thể ghép trực tiếp batch listener với cấu hình retry topic theo cách được hỗ trợ bởi framework. Kết hợp `@RetryableTopic` với batch listener không tạo thành một chiến lược retry từng phần tử đáng tin cậy.

Ví dụ về sự khác biệt:

~~~text
Record listener:
  Kafka record A -> listener(A) -> lỗi -> retry topic -> listener(A) lần sau
  Kafka record B -> listener(B) -> thành công -> tiếp tục

Batch listener:
  Kafka poll -> [A, B, C] -> listener([A, B, C])
                               |
                               +-- B lỗi
~~~

Ở tình huống batch, framework còn phải biết record nào lỗi, các record nào đã tạo side effect, phần nào được phép commit, có cần phát lại cả batch hay chỉ record B, và thứ tự xử lý trong từng partition. Đây là các yêu cầu khác với việc chuyển một record riêng lẻ sang retry topic.

Vì vậy, khi thiết kế Spring Kafka Reliability Operations cần chọn rõ một trong hai mô hình:

- Giữ batch listener và dùng cơ chế xử lý lỗi phù hợp với batch, thường là `DefaultErrorHandler` với blocking retry/recovery.
- Chuyển sang record listener nếu bắt buộc cần non-blocking retry bằng retry topic.
- Nếu cần đồng thời xử lý theo lô và trì hoãn retry từng record, thiết kế cơ chế retry nghiệp vụ riêng với hợp đồng offset, idempotency và DLT tường minh.

## 2. Non-blocking retry thực sự hoạt động thế nào?

### 2.1. Retry bằng topic trung gian

Khác với blocking retry, non-blocking retry không giữ consumer thread chờ hết thời gian backoff. Khi một record xử lý lỗi, framework dùng producer để gửi record đó đến một retry topic và cho phép consumer của topic gốc tiếp tục xử lý các record khác theo chính sách container.

Sau khoảng trễ đã cấu hình, listener gắn với retry topic nhận record và thực hiện lại logic xử lý. Nếu vẫn lỗi và còn lượt thử, record đi tiếp đến retry topic hoặc lượt retry tương ứng; sau khi hết lượt, record có thể được chuyển đến dead-letter topic (DLT).

~~~mermaid
flowchart LR
    A[Topic orders] --> B[Record listener]
    B -->|Thành công| C[Hoàn tất xử lý]
    B -->|Lỗi retryable| D[Retry topic]
    D -->|Đủ thời gian chờ| E[Retry listener]
    E -->|Thành công| C
    E -->|Tiếp tục lỗi| F{Còn lượt retry?}
    F -->|Có| D
    F -->|Không| G[DLT]
~~~

Đây là sơ đồ logic: số topic được tạo, tên topic, cách tái sử dụng topic và cách định tuyến phụ thuộc cấu hình retry topic của phiên bản Spring Kafka.

Non-blocking retry không có nghĩa toàn bộ quá trình xử lý là bất đồng bộ hoặc không có thread. Consumer của topic chính và các retry topic vẫn chạy trên thread/container; điều được tránh là giữ thread chờ trực tiếp cho từng khoảng backoff dài.

### 2.2. Một record là đơn vị lỗi và retry

Với record listener, framework có đủ metadata để định danh record gặp lỗi: topic, partition, offset, key, value và các headers liên quan. Retry infrastructure có thể tạo record mới ở retry topic, mang metadata và headers phục vụ theo dõi lần thử.

Ví dụ:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000L, multiplier = 2.0)
)
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrder(OrderCreated event) {
    billingService.applyIdempotently(event);
}
~~~

Ví dụ dùng annotation trong Spring Kafka có hỗ trợ retry topic, cùng các import tương ứng. `attempts = "4"` mô tả tổng số lần delivery theo semantics của annotation, gồm lần đầu và các lần retry. Khoảng chờ ban đầu là một giây và có thể tăng theo hệ số 2.

Nếu record xử lý thành công ở một lần thử, record không cần đi tiếp đến các retry topic khác. Nếu hết lượt retry, record được định tuyến sang DLT theo cấu hình.

### 2.3. Không duy trì ordering chặt theo partition

Khi record A lỗi và được chuyển sang retry topic, topic gốc có thể tiếp tục xử lý record B đến sau A. Vì vậy, non-blocking retry có thể khiến thứ tự hoàn tất nghiệp vụ khác thứ tự offset ban đầu.

~~~text
Topic chính (partition P0): A(offset 10), B(offset 11)

A lỗi -> chuyển sang retry topic, chờ 5 giây
B thành công ngay
A được retry và thành công sau đó

Thứ tự hoàn tất: B -> A
~~~

Nếu các event của cùng order, account hoặc aggregate đòi hỏi xử lý đúng thứ tự, cần đánh giá rất kỹ trước khi dùng retry topic. Điều này đúng cả với record listener; chuyển batch listener sang record listener không tự khôi phục ordering sau khi dùng non-blocking retry.

## 3. Batch listener là gì?

Batch listener nhận một danh sách record từ một lần poll hoặc một nhóm record do container cung cấp, thay vì chỉ nhận một record.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderCreated> events) {
    billingService.processBatch(events);
}
~~~

Factory cần được cấu hình ở chế độ batch:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);

    return factory;
}
~~~

Một batch có thể chứa record từ nhiều partition được gán cho cùng consumer. Kích thước batch thực tế chịu ảnh hưởng của số record có sẵn, `max.poll.records`, fetch configuration và các điều kiện poll.

Batch listener hữu ích khi downstream cho phép thao tác theo lô, chẳng hạn ghi hàng trăm bản ghi trong một database transaction hoặc giảm số lần gọi network. Đổi lại, xử lý lỗi và commit offset trở nên phức tạp khi một số phần tử thành công còn phần tử khác thất bại.

## 4. Vì sao không thể ghép trực tiếp non-blocking retry với batch listener?

### 4.1. Đơn vị lỗi không khớp với đơn vị retry

Retry topic infrastructure xử lý từng record riêng biệt. Batch listener nhận một collection, và một exception trong listener có thể đại diện cho lỗi của một record hoặc của cả batch.

Giả sử một batch gồm:

~~~text
Partition orders-0:
  offset 100: event A -> ghi DB thành công
  offset 101: event B -> lỗi timeout
  offset 102: event C -> chưa xử lý
~~~

Nếu chuyển cả batch sang một retry topic như một payload duy nhất, metadata gốc của từng record không tự động được giữ đúng theo mô hình record listener. Nếu chỉ chuyển B, ứng dụng phải phân biệt A đã hoàn tất hay chưa, C chưa chạy hay đã chạy, và offset nào được phép commit.

Spring Kafka cung cấp xử lý lỗi riêng cho batch listener, nhưng non-blocking retry topic infrastructure không có hợp đồng hỗ trợ batch listener như một phần của cơ chế đó.

### 4.2. Batch có thể trải trên nhiều partition

Một batch có thể chứa:

~~~text
orders-0 offset 100
orders-0 offset 101
orders-1 offset 45
orders-1 offset 46
~~~

Offset commit được lưu riêng theo topic-partition. Một batch lỗi không tương ứng với một offset duy nhất. Nếu đã hoàn tất một số record, container cần xác định tiến độ liên tục của từng partition; không được commit vượt qua record chưa được xử lý hoặc chưa được phục hồi.

### 4.3. Chuyển một record sang retry topic tác động đến commit nguồn

Với non-blocking retry, record lỗi được phát đến retry topic và xử lý tiếp ở luồng retry. Tiến độ consumer của topic nguồn phải phản ánh hợp đồng chuyển giao: nếu publish retry thất bại mà offset nguồn vẫn tiến, có nguy cơ mất sự kiện; nếu publish thành công nhưng offset nguồn không được commit, có thể tạo record retry trùng sau restart.

Cơ chế record listener được thiết kế cho đường đi này. Batch listener có thêm các trường hợp partial success, partial commit và lỗi batch khiến đường đi phức tạp hơn đáng kể.

### 4.4. Thứ tự và transaction của batch có thể bị phá vỡ

Nếu `processBatch(events)` có một database transaction cho cả batch, chuyển một phần tử bị lỗi sang retry topic có thể không giữ được ý nghĩa nguyên tử của thao tác ban đầu. Ngược lại, nếu từng record đã commit riêng trong database, retry toàn batch có thể lặp lại side effect.

Do vậy, giới hạn hỗ trợ này là ranh giới thiết kế cần tôn trọng khi chọn kiến trúc retry.

## 5. Ví dụ cấu hình không phù hợp

Đoạn sau biểu thị ý định kết hợp hai tính năng không được Spring Kafka hỗ trợ trong cùng endpoint:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2_000L)
)
@KafkaListener(
    topics = "orders",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderCreated> events) {
    billingService.processBatch(events);
}
~~~

Vấn đề nằm ở chỗ container factory sử dụng batch listener, trong khi `@RetryableTopic` dành cho non-blocking retry của record listener. Tùy phiên bản và cấu hình, ứng dụng có thể gặp lỗi lúc tạo endpoint/container hoặc không có hành vi retry được hỗ trợ như kỳ vọng. Không nên dựa vào việc một cấu hình tình cờ khởi động được để coi nó đã có semantics phục hồi đúng.

Cũng không thể sửa bằng cách tăng `concurrency`, đổi `ack-mode` hay thêm `@DltHandler`. Những thay đổi đó không biến non-blocking retry thành cơ chế hỗ trợ batch listener.

## 6. Cách 1: Giữ batch listener và dùng DefaultErrorHandler

Đây là lựa chọn thông dụng nếu ưu tiên hiệu quả xử lý theo batch, có thể chấp nhận blocking retry ở container, và cần kiểm soát rõ lỗi theo index.

### 6.1. Cấu hình container batch và error handler

~~~java
@Configuration
public class BatchConsumerConfiguration {

    @Bean
    public DefaultErrorHandler batchErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate
    ) {
        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            batchKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler batchErrorHandler
            ) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setCommonErrorHandler(batchErrorHandler);

        return factory;
    }
}
~~~

Ví dụ dùng Spring Kafka hỗ trợ `DefaultErrorHandler`. `FixedBackOff(1_000L, 2L)` cho phép hai lần retry bổ sung, mỗi lần cách một giây. Khi hết retry, recoverer có thể publish record lỗi sang DLT theo cấu hình.

DLT publisher phải được cấu hình với serializer, topic destination, partition và quyền ghi phù hợp. Nếu recovery không thành công, không được coi record đã được phục hồi.

### 6.2. Chỉ ra record bị lỗi bằng BatchListenerFailedException

Nếu batch được xử lý tuần tự theo từng phần tử và listener biết index nào lỗi, có thể ném `BatchListenerFailedException`:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
    List<ConsumerRecord<String, OrderCreated>> records
) {
    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, OrderCreated> record = records.get(i);

        try {
            billingService.applyIdempotently(record.value());
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                "Cannot process record at batch index " + i,
                ex,
                i
            );
        }
    }
}
~~~

`BatchListenerFailedException` mang thông tin index (hoặc record) gây lỗi, giúp error handler xác định phần đã xử lý và phần còn lại. Cách commit các offset trước record lỗi, redelivery và recovery phụ thuộc cấu hình container/error handler và phiên bản Spring Kafka.

Đây là **blocking retry theo batch error handling**, không phải non-blocking retry qua retry topic. Consumer xử lý bản ghi lỗi trong phạm vi container và có thể trì hoãn việc xử lý record tiếp theo cho đến khi hoàn tất retry/recovery.

Nếu batch có record từ nhiều partition, phải dựa vào error handler và acknowledgment mode để quản lý offset từng partition, không tự suy ra toàn batch có một offset chung.

### 6.3. Trường hợp không biết record nào lỗi

Nếu phương thức xử lý batch ném một exception chung, không xác định được phần tử lỗi, `DefaultErrorHandler` có thể sử dụng cơ chế fallback batch retry. Khi đó cả batch có thể được thử lại và các record đã tạo side effect ở lần trước có thể được xử lý lại.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderCreated> events) {
    billingService.processBatch(events); // Lỗi không chỉ rõ index
}
~~~

Mô hình này phù hợp hơn nếu `processBatch` được bảo vệ bằng transaction database nguyên tử: thành công thì commit cả batch, lỗi thì rollback toàn bộ thao tác database. Nếu batch đã commit side effect từng phần, retry toàn batch cần idempotency cho từng event.

## 7. Blocking retry ảnh hưởng gì đến vận hành?

Blocking retry giữ record/batch trên đường xử lý của consumer container trong khi thực hiện retry và backoff. Điều này có thể làm chậm partition hoặc các partition khác do cùng consumer sở hữu.

Ví dụ listener batch đang xử lý 500 record và một phần tử gặp timeout database. Nếu error handler thử lại nhiều lần với backoff dài, consumer lag có thể tăng trong thời gian đó.

Các yếu tố cần kiểm soát:

| Cấu hình / yếu tố | Tác động |
|---|---|
| `max.poll.records` | Số record tối đa trả về trong một poll; ảnh hưởng kích thước batch |
| `max.poll.interval.ms` | Giới hạn thời gian giữa các lần poll; xử lý quá lâu có thể gây rebalance |
| `FixedBackOff` / `ExponentialBackOff` | Số lần và thời gian chờ retry |
| `AckMode` | Cách container commit tiến độ sau xử lý |
| Listener processing duration | Thời gian thực thi nghiệp vụ |
| `concurrency` | Số consumer trong container, giới hạn bởi partition |
| DLT recoverer | Điểm xử lý khi đã hết lượt retry |

Không đặt backoff vô hạn nếu một poison record có thể chặn toàn bộ luồng. Với lỗi không thể tự khắc phục như payload sai schema, nên phân loại non-retryable và đưa sang recovery theo chính sách.

## 8. Cách 2: Chuyển sang record listener để dùng @RetryableTopic

Nếu yêu cầu cốt lõi là **retry từng record sau thời gian trì hoãn mà không giữ consumer chính chờ**, record listener là đường đi được hỗ trợ.

### 8.1. Ví dụ đầy đủ

~~~java
@Component
@RequiredArgsConstructor
public class OrderConsumer {

    private final BillingService billingService;

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 2_000L, multiplier = 2.0),
        autoCreateTopics = "false"
    )
    @KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        containerFactory = "recordKafkaListenerContainerFactory"
    )
    public void onOrder(OrderCreated event) {
        billingService.applyIdempotently(event);
    }

    @DltHandler
    public void onDlt(
        OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String receivedTopic
    ) {
        log.error("Order could not be processed from {}", receivedTopic);
        // Ghi nhận event ID và trạng thái cần xử lý thủ công.
    }
}
~~~

Ví dụ minh họa các annotation cần thiết; dự án phải cấu hình producer/consumer serialization, retry/DLT topics và các import tương ứng. Với `autoCreateTopics = "false"`, topic retry và DLT cần được provision đúng trước khi chạy.

Container factory của endpoint này phải ở chế độ **record listener**:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        recordKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(false);

    return factory;
}
~~~

Tùy Spring Kafka version, có thể cần khai báo thêm cấu hình retry topic, beans và KafkaTemplate để framework tạo hạ tầng retry. Không gắn batch factory vào endpoint này.

### 8.2. Batching vẫn có thể diễn ra ở Kafka client

Record listener không có nghĩa Kafka client fetch từng record một. Một lần `poll()` vẫn có thể trả nhiều record, nhưng container chuyển chúng đến phương thức listener lần lượt.

Điều bị loại bỏ là callback nghiệp vụ nhận cả collection cùng lúc. Nhờ đó framework xác định chính xác record nào lỗi và chuyển nó sang retry topic.

### 8.3. Nếu cần tối ưu throughput

Có thể tối ưu record listener bằng:

- Tăng concurrency hợp lý với số partition và số replica.
- Giảm chi phí thao tác database cho mỗi event.
- Dùng cache hoặc statement batching ở tầng repository với transaction rõ ràng.
- Xử lý idempotent để chống duplicate.
- Đặt timeout cho HTTP/database call.
- Theo dõi throughput và consumer lag trước khi điều chỉnh.

Nếu muốn gom các record đã nhận để ghi database theo lô, có thể dùng một bộ đệm nghiệp vụ có giới hạn, nhưng phải xác định thời điểm listener được xem là thành công. Nếu listener trả về trước khi buffer được flush bền vững, container có thể tiến offset quá sớm, tạo nguy cơ mất dữ liệu khi process dừng.

## 9. Cách 3: Tách ingestion theo record và batch processing phía sau

Một kiến trúc khác là dùng record listener có non-blocking retry ở lớp tiếp nhận, sau đó đưa các event đã qua validation vào một queue hoặc outbox bền vững để xử lý theo batch ở service khác.

~~~mermaid
flowchart TD
    A[Kafka orders] --> B[Record listener + @RetryableTopic]
    B -->|Validation/ingestion thành công| C[Durable inbox hoặc work queue]
    B -->|Lỗi tạm thời| R[Retry topic]
    R --> B
    B -->|Hết lượt| D[DLT]
    C --> E[Batch worker]
    E --> F[Database batch operation]
~~~

Thiết kế này tạo hai ranh giới rõ ràng:

- **Tiếp nhận Kafka**: mỗi record được ghi bền vững vào inbox/queue trước khi listener trả về thành công.
- **Xử lý batch**: worker đọc các item đã lưu, gom lô theo kích thước/thời gian, xử lý và cập nhật trạng thái.

Ưu điểm là có thể vừa sử dụng retry topic cho lỗi ingestion vừa có batch operation cho downstream. Tuy nhiên, hệ thống phải có nơi lưu bền vững, lifecycle của work item, idempotency, retry riêng cho batch worker và cơ chế xử lý lại khi worker lỗi.

Không được dùng một `List` trong RAM làm hàng đợi duy nhất rồi trả về listener như thể event đã được xử lý bền vững.

## 10. Cách 4: Tự thiết kế non-blocking retry cho record lỗi trong batch

Một số hệ thống cần giữ batch listener nhưng chỉ trì hoãn một vài record lỗi. Khi đó có thể tự xây dựng đường chuyển record lỗi sang retry topic:

1. Batch listener nhận danh sách record.
2. Ứng dụng xử lý các record theo chính sách tường minh, xác định record thành công và record lỗi.
3. Record lỗi được publish sang topic retry riêng cùng event ID, original topic/partition/offset và thông tin attempt.
4. Chỉ khi publish retry được xác nhận theo tiêu chí độ bền đã chọn, ứng dụng mới xem việc chuyển giao record lỗi là thành công.
5. Offset của nguồn được commit theo cách không bỏ qua record chưa xử lý/chưa chuyển giao thành công.
6. Một record listener riêng tiêu thụ retry topic và áp dụng retry/ DLQ policy.

Đây là một **thiết kế custom**, không phải tính năng `@RetryableTopic` hỗ trợ trực tiếp batch listener. Khi xây dựng phải giải quyết nhiều điểm dễ sai:

- Nếu publish retry thành công nhưng commit offset nguồn thất bại, record có thể xuất hiện lại; cần idempotency.
- Nếu commit offset nguồn trước khi publish retry hoàn tất, record có thể bị mất khi process dừng.
- Nếu một record của partition chưa hoàn tất mà commit vượt qua offset đó, consumer restart có thể bỏ qua record.
- Nếu batch có nhiều partition, phải kiểm soát tiến độ riêng từng partition.
- Nếu retry topic xử lý chậm, có thể cần retention, DLT, replay, alert và quota riêng.
- Nếu nghiệp vụ yêu cầu ordering theo key, chuyển record ra topic retry có thể làm thay đổi thứ tự hoàn tất.
- Nếu publish retry bị timeout, broker có thể đã ghi thành công; gửi lại có thể tạo duplicate.

Cần cân nhắc chi phí triển khai và vận hành trước khi chọn cách này. Với yêu cầu thông thường, `DefaultErrorHandler` cho batch hoặc record listener với `@RetryableTopic` dễ kiểm soát hơn.

## 11. Commit offset khi xử lý batch lỗi

### 11.1. Offset luôn thuộc từng topic-partition

Giả sử poll trả:

~~~text
orders-0: offset 30, 31, 32
orders-1: offset 10, 11
~~~

Nếu `orders-0` offset 31 thất bại, không được commit offset 33 cho partition 0 khi record 31 chưa xử lý/recover an toàn. Tuy nhiên, tiến độ của partition 1 độc lập với partition 0; container và error handler cần quản lý chúng theo chính sách phù hợp.

Committed offset là vị trí **tiếp theo** group sẽ đọc, không phải offset của record đã xử lý cuối cùng.

### 11.2. Batch retry có thể gây redelivery

Nếu listener ghi database thành công cho offset 30 nhưng crash trước khi commit offset, Kafka có thể giao lại offset 30 sau restart. Bởi vậy, kể cả khi dùng `BatchListenerFailedException`, nghiệp vụ vẫn nên dùng event ID ổn định, unique constraint, inbox hoặc thao tác upsert idempotent.

Ví dụ khái quát:

~~~java
@Transactional
public void applyIdempotently(OrderCreated event) {
    if (!inboxRepository.insertIfAbsent(event.eventId())) {
        return;
    }

    orderRepository.updateFromEvent(event);
}
~~~

Insert inbox và cập nhật nghiệp vụ cần cùng database transaction. Nếu cập nhật thất bại, inbox insert cũng rollback. Khi nhận lại event, unique constraint giúp phát hiện bản ghi đã xử lý và tránh side effect trùng.

### 11.3. Không coi DLT là tự động commit

Publish record lỗi sang DLT là bước recovery. Offset nguồn được commit thế nào phụ thuộc error handler và acknowledgment mode. Nếu DLT publisher thất bại, không được âm thầm coi record đã recover.

Khi dùng `DeadLetterPublishingRecoverer`, cần xác định cơ chế kiểm tra kết quả send, timeout và khả năng retry recovery. Hệ thống phải phân biệt việc producer nhận lời gọi send với việc broker đã xác nhận record.

## 12. BatchListenerFailedException và lỗi không xác định index

Spring Kafka phân biệt trường hợp listener biết record lỗi trong batch và trường hợp chỉ biết cả batch thất bại.

| Tình huống | Cách báo lỗi | Hệ quả |
|---|---|---|
| Một record lỗi tại index rõ ràng | Ném `BatchListenerFailedException` | Error handler có thể xử lý phần đã hoàn tất và phần còn lại theo index |
| Batch operation nguyên tử thất bại | Ném exception thông thường | Có thể cần retry toàn batch hoặc rollback toàn bộ side effect |
| Nhiều record lỗi riêng biệt trong batch | Cần chính sách ứng dụng rõ ràng | Không thể dùng một index để biểu diễn mọi lỗi độc lập |
| Deserialize thất bại trước khi tạo object | Cần error handling của deserializer/container | Listener có thể không nhận được object bình thường |
| Recovery/DLT publish lỗi | Recoverer ném exception | Record chưa chắc đã được recover; cần tiếp tục xử lý |

Không bắt exception rồi trả về bình thường nếu vẫn còn record chưa xử lý. Khi listener trả về thành công, container có thể xem batch đã hoàn tất và commit offset, tùy mode.

Nếu xử lý từng phần tử và chỉ phát hiện nhiều lỗi sau khi đi hết batch, phải thiết kế cách lưu các record lỗi và commit tiến độ sao cho không bỏ sót khoảng offset chưa hoàn tất.

## 13. Batch listener với transaction

Nếu batch được ghi vào database trong một transaction, việc commit/rollback toàn batch giúp giảm partial success ở tầng database. Ví dụ một phương thức service có `@Transactional` ghi cả lô và rollback khi ném exception.

~~~java
@Service
@RequiredArgsConstructor
public class BatchBillingService {

    private final OrderRepository repository;

    @Transactional
    public void processBatch(List<OrderCreated> events) {
        for (OrderCreated event : events) {
            repository.apply(event);
        }
    }
}
~~~

Điều này chỉ tạo atomicity trong phạm vi database transaction. Kafka offset commit vẫn là một thao tác riêng, trừ khi kiến trúc có transaction coordination phù hợp. Sau database commit nhưng trước offset commit, batch vẫn có thể được giao lại; idempotency vẫn cần thiết.

Một giới hạn khác: non-blocking retry infrastructure của Spring Kafka không hỗ trợ kết hợp với batch listener, và cũng có những hạn chế khi kết hợp non-blocking retry với container transactions. Không nên bật đồng thời nhiều cơ chế transaction và retry rồi giả định chúng tự phối hợp thành exactly-once xuyên database và Kafka.

Nếu nghiệp vụ yêu cầu xử lý một batch nguyên tử, lựa chọn retry toàn batch trong container có thể giữ semantics đơn giản hơn việc tách từng record sang retry topic.

## 14. DLT trong hai phương án

Cả batch error handler và non-blocking retry cho record listener đều có thể đưa record không phục hồi được sang dead-letter topic, nhưng đường đi khác nhau.

| Đặc điểm | Batch + DefaultErrorHandler | Record + @RetryableTopic |
|---|---|---|
| Nơi lỗi phát sinh | Batch listener | Record listener |
| Cách retry | Blocking trong container hoặc cơ chế batch handling | Chuyển sang retry topic, tiêu thụ lại theo trễ |
| Đơn vị lỗi cần xác định | Record index hoặc cả batch | Một record |
| Sau khi hết retry | Recoverer, có thể publish DLT | Retry topic infrastructure định tuyến sang DLT |
| Ordering | Có thể giữ tuần tự chặt hơn khi retry blocking | Record phía sau có thể hoàn tất trước |
| Tài nguyên | Consumer/container chờ trong lúc retry | Thêm topic, producer và retry consumers |
| Vận hành | Theo dõi batch failure, handler, lag | Theo dõi retry topic, DLT lag, delay, attempt |

Không nên chỉ dựa vào việc DLT tồn tại để đánh giá độ tin cậy. Cần theo dõi DLT publish success/failure, thời gian lưu trữ, số record chờ xử lý và quy trình replay.

DLT consumer phải xử lý duplicate an toàn, đặc biệt khi timeout khiến hệ thống không biết chắc record đã được publish hay chưa.

## 15. Ảnh hưởng đến ordering và SLA

### 15.1. Khi ưu tiên ordering

Nếu event `OrderCreated`, `OrderPaid` và `OrderShipped` phải được áp dụng đúng thứ tự, chuyển event đầu sang retry topic trong khi event sau vẫn được xử lý có thể phá vỡ điều kiện nghiệp vụ.

Với trường hợp này, cân nhắc blocking retry theo partition, giới hạn thời gian chờ và cơ chế xử lý poison record rõ ràng. Cũng có thể dùng state machine hỗ trợ event đến trễ hoặc lưu event pending, nhưng đó là thay đổi kiến trúc nghiệp vụ.

### 15.2. Khi ưu tiên throughput

Nếu record độc lập, có thể được xử lý theo bất kỳ thứ tự nào và thời gian phục hồi của downstream biến động, non-blocking retry ở record listener có thể giúp topic chính tiếp tục tiến khi một record lỗi.

Tuy nhiên, retry topic tạo tải bổ sung cho broker, producer, consumer và monitoring. Nếu số record lỗi tăng mạnh, retry topic có thể trở thành backlog lớn. Cần đặt retry policy, DLT và cảnh báo tương ứng.

### 15.3. Khi ưu tiên batch I/O

Nếu thao tác database theo batch giúp tiết kiệm đáng kể thời gian và mạng, giữ batch listener với `DefaultErrorHandler` thường là lựa chọn thực tế. Cần thử tải với batch size, concurrency và backoff để bảo đảm `max.poll.interval.ms` không bị vượt do xử lý quá lâu.

## 16. Thiết kế retry policy cho batch listener

Một retry policy phù hợp nên phân loại lỗi:

- **Transient**: timeout database, kết nối tạm thời, HTTP 503. Có thể retry với backoff có giới hạn.
- **Permanent**: payload vi phạm schema, thiếu trường bắt buộc, kiểu dữ liệu không hợp lệ. Thường nên recover hoặc đưa DLT sớm.
- **Duplicate hợp lệ**: event ID đã được xử lý; listener có thể trả về thành công mà không lặp side effect.
- **Lỗi chưa rõ kết quả**: database transaction hoặc publish DLT timeout. Cần kiểm tra trạng thái bền vững và áp dụng idempotency.

Ví dụ phân loại trên handler:

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );

handler.addNotRetryableExceptions(
    IllegalArgumentException.class
);
~~~

Danh sách exception cần phù hợp với domain. Có những lỗi như unique constraint violation có thể biểu thị duplicate hợp lệ hoặc lỗi nghiệp vụ nghiêm trọng; không nên phân loại cứng khi chưa hiểu nguyên nhân.

Backoff phải được giới hạn. Một poison record không thể xử lý không nên giữ partition mãi mãi và làm consumer lag tăng không kiểm soát.

## 17. Cấu hình consumer và batch size

Batch listener không được kết hợp với retry topic, nhưng vẫn có nhiều tham số ảnh hưởng độ tin cậy và throughput.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      max-poll-records: 200
      auto-offset-reset: earliest
    listener:
      type: batch
      concurrency: 3
      ack-mode: batch
~~~

Ví dụ dùng Spring Boot có hỗ trợ các listener properties nêu trên. Cần kiểm tra cấu hình hiệu lực nếu ứng dụng có factory tùy chỉnh vì factory có thể ghi đè lựa chọn của Boot.

Giải thích:

- `max-poll-records` giới hạn số record trả về trong một lần poll, không bảo đảm batch luôn có đúng 200 phần tử.
- `concurrency` điều khiển số consumer của container, mức song song tối đa phụ thuộc số partition và số replica.
- `ack-mode: batch` commit theo tiến độ poll/batch được container quản lý.
- `enable-auto-commit: false` tránh commit tự động theo timer tách khỏi kết quả listener.

Nếu tăng batch size làm thời gian xử lý vượt `max.poll.interval.ms`, consumer có thể bị rebalance và record được giao lại. Điều chỉnh batch size, concurrency, downstream timeout và retry duration cùng nhau.

## 18. Khả năng quan sát khi batch listener lỗi

Nên thu thập các thông tin sau để xác định record nào bị lỗi và cơ chế recovery có hoạt động đúng không:

| Thông tin / metric | Công dụng |
|---|---|
| Original topic, partition, offset | Truy vết đúng record nguồn |
| Consumer group và client ID | Xác định instance xử lý |
| Batch size | Đo quy mô dữ liệu khi lỗi |
| Failed record index | Phân biệt lỗi một phần tử với lỗi cả batch |
| Exception class và root cause | Phân loại lỗi transient/permanent |
| Retry attempts, backoff | Xác định bao nhiêu lần đã thử |
| Recovery/DLT send result | Biết record lỗi đã được chuyển giao bền vững chưa |
| Consumer lag theo partition | Phát hiện partition bị nghẽn |
| Listener processing duration | Dự đoán nguy cơ vượt max poll interval |
| DLT topic lag | Phát hiện backlog cần vận hành |

Log cần tránh ghi toàn bộ payload nếu có dữ liệu cá nhân hoặc bí mật. Có thể ghi event ID, correlation ID, topic, partition, offset và loại exception.

Với non-blocking retry, nên theo dõi riêng throughput và lag của retry topics, số record đang chờ, độ trễ retry thực tế và DLT. Không gộp retry success vào success của topic gốc nếu việc đó gây đếm trùng.

## 19. Kịch bản kiểm thử để xác nhận lựa chọn kiến trúc

### 19.1. Batch + DefaultErrorHandler

1. Tạo topic thử nghiệm có ít nhất một partition.
2. Gửi nhiều record trong cùng một poll.
3. Cho một record tại index xác định ném exception ở lần đầu.
4. Dùng `BatchListenerFailedException` và `FixedBackOff`.
5. Xác nhận phần trước lỗi, phần lỗi và phần sau lỗi được xử lý theo policy.
6. Xác nhận committed offset không vượt qua record chưa hoàn tất.
7. Cho recoverer/DLT hoạt động sau khi hết retry.
8. Kiểm tra duplicate và idempotency sau khi restart consumer.

### 19.2. Record + @RetryableTopic

1. Tạo topic chính, retry topic và DLT theo cấu hình.
2. Cho record A ném exception lần đầu.
3. Gửi record B sau A trên cùng partition.
4. Xác nhận A được chuyển sang retry topic, B có thể được xử lý ở topic chính.
5. Xác nhận A được thử lại sau khoảng trễ mong đợi.
6. Khi A tiếp tục lỗi, xác nhận event được chuyển DLT theo chính sách.
7. Đối chiếu sự thay đổi thứ tự hoàn tất và consumer lag.
8. Kiểm tra việc publish retry topic bị lỗi không làm record nguồn bị bỏ qua.

### 19.3. Chuyển batch listener sang record listener

Khi migration, cần kiểm thử thêm:

- Throughput ở cùng tải và số partition.
- Database connection pool và số transaction.
- Thời gian xử lý p95/p99.
- Số lần side effect khi record bị giao lại.
- Ordering theo key và cách ứng dụng xử lý event đến trễ.
- Số retry topic, retention và DLT processing capacity.

Không suy ra rằng ứng dụng nhanh hơn hay đáng tin cậy hơn chỉ vì chuyển sang record listener. Cần đo cả chi phí batch I/O đã mất đi và lợi ích của việc cô lập record lỗi.

## 20. Lỗi thiết kế thường gặp

**Gắn `@RetryableTopic` vào batch listener:** đây là tổ hợp không được hỗ trợ; không dùng làm đường retry production.

**Cho rằng annotation có thể retry riêng từng phần tử trong List:** framework không được cung cấp hợp đồng batch retry topic như vậy.

**Dùng `BatchListenerFailedException` như cách bật non-blocking retry:** exception này giúp xử lý lỗi batch với error handler phù hợp; nó không biến batch listener thành record listener.

**Retry cả batch khi đã commit side effect từng phần:** có thể lặp update hoặc publish event, cần transaction hoặc idempotency.

**Bắt lỗi rồi trả về bình thường:** container có thể commit offset dù batch chưa xử lý xong.

**Commit vượt record chưa hoàn tất:** làm mất cơ hội xử lý record khi consumer restart.

**Tự publish record lỗi sang retry topic nhưng không chờ kết quả:** nếu offset nguồn được commit trước khi publish retry bền vững, record có thể bị mất.

**Không kiểm tra ordering:** record sau có thể hoàn tất trước record đang chờ retry topic.

**Backoff không giới hạn:** một record lỗi có thể làm batch listener chờ quá lâu và tăng consumer lag.

**Không provision retry/DLT topic:** thiếu topic, thiếu partition hoặc ACL có thể khiến recovery thất bại ngay khi cần nhất.

**Không kiểm tra DLT publisher:** recoverer có thể thất bại hoặc timeout; chưa thể coi record đã được chuyển giao thành công.

**Dùng queue trong RAM làm ranh giới xử lý bền vững:** process crash có thể làm mất event sau khi offset đã commit.

## 21. Quy tắc chọn giải pháp trong production

| Yêu cầu chính | Lựa chọn đề xuất | Điểm cần bảo vệ |
|---|---|---|
| Cần batch database operation và retry khi batch lỗi | Batch listener + DefaultErrorHandler | Transaction, index lỗi, commit và idempotency |
| Cần delay retry từng record, topic chính tiếp tục | Record listener + @RetryableTopic | Ordering, retry/DLT topics và idempotency |
| Cần batch downstream và record-level retry riêng biệt | Record listener + durable inbox/queue + batch worker | Atomic handoff, backpressure, worker retry |
| Batch xử lý nguyên tử, phải rollback toàn bộ khi lỗi | Batch listener + transaction + batch error handling | DB commit và Kafka offset commit |
| Cần xử lý lỗi vĩnh viễn mà không chặn mãi | DLT/recoverer có xác nhận | DLT reliability và replay |
| Cần strict ordering theo key | Ưu tiên retry không vượt record lỗi hoặc xử lý stateful | Partition ordering và deadline |
| Cần tự chuyển record trong batch sang topic retry | Custom solution có hợp đồng rõ | Partial commits, duplicate và ownership |

Một quy trình ra quyết định phù hợp:

1. Xác định side effect của batch là nguyên tử hay từng record độc lập.
2. Xác định có chấp nhận hoàn tất record phía sau trước record lỗi không.
3. Xác định retry delay tối đa và khả năng container chờ trong thời gian đó.
4. Đo throughput khi dùng record listener so với batch listener.
5. Chọn đường retry được Spring Kafka hỗ trợ cho listener tương ứng.
6. Thiết kế commit offset, idempotency, DLT và metrics trước khi rollout.
7. Kiểm thử lỗi giữa database commit, publish retry/DLT và Kafka offset commit.

**Non-blocking retry của Spring Kafka không hỗ trợ batch listener** là một giới hạn cần đưa vào thiết kế ngay từ đầu. Nếu cần retry bằng retry topic, hãy dùng record listener và chủ động quản lý ordering. Nếu cần xử lý theo batch, dùng error handler phù hợp với batch và kiểm soát partial failure, transaction cùng offset. Nếu phải đáp ứng cả hai nhu cầu, hãy tách ranh giới ingest theo record và xử lý theo lô bằng một tầng lưu trữ bền vững có idempotency.
