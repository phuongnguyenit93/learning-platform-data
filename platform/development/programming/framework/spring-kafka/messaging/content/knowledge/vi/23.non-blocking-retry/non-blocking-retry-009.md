# Chọn blocking hay non-blocking retry

## Mục tiêu của bài học

Trong chương **Non-blocking retry**, bài này giúp lựa chọn cách xử lý khi một Kafka record thất bại: giữ record trong luồng consumer để thử lại (blocking retry), hay chuyển record sang retry topic để xử lý lại sau (non-blocking retry).

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Lựa chọn retry cần phù hợp với đặc tính event và cách ứng dụng vận hành consumer group.

Sau bài học, người học có thể:

- Mô tả cơ chế blocking retry và non-blocking retry.
- Chọn chiến lược theo thời gian chờ, ordering, throughput và yêu cầu nghiệp vụ.
- Cấu hình blocking retry bằng DefaultErrorHandler và DeadLetterPublishingRecoverer.
- Cấu hình non-blocking retry bằng RetryableTopic, Backoff và DltHandler.
- Thiết kế retry topic, DLT, partition và retention.
- Phân loại exception retryable và non-retryable.
- Bảo đảm idempotency khi record được giao lại.
- Hiểu giới hạn của retry topic với batch listener và transaction.
- Kiểm thử retry, DLT, ordering và hành vi khi downstream lỗi kéo dài.

## 1. Hai cách retry trong Spring Kafka

Khi listener ném exception, Spring Kafka cần quyết định cách đưa record thất bại trở lại xử lý.

**Blocking retry** giữ việc retry trong luồng xử lý của listener container. Error handler chờ theo backoff rồi giao lại record. Trong thời gian record đang được xử lý lại, record phía sau trong cùng partition có thể bị trì hoãn.

**Non-blocking retry** chuyển record thất bại sang một retry topic. Một listener container khác đọc retry topic và xử lý record khi đến thời điểm phù hợp. Consumer của topic gốc có thể tiếp tục với các record tiếp theo.

~~~mermaid
flowchart TD
    A["Record từ topic chính"] --> B["Listener xử lý"]
    B --> C{"Thành công?"}
    C -->|Có| D["Commit offset"]
    C -->|Không| E{"Chiến lược retry"}
    E --> F["Blocking retry"]
    F --> G["Backoff trong luồng consumer"]
    G --> B
    E --> H["Non-blocking retry"]
    H --> I["Publish retry topic"]
    I --> J["Đợi thời điểm retry"]
    J --> K["Retry listener"]
    K --> L{"Thành công?"}
    L -->|Có| M["Hoàn tất"]
    L -->|Không| I
    I --> N["Hết attempt"]
    N --> O["Dead-letter topic"]
~~~

Hai cơ chế có mục đích chung là xử lý lỗi tạm thời, nhưng trade-off khác nhau. Không có một lựa chọn tốt cho mọi luồng event.

## 2. Blocking retry hoạt động như thế nào?

Blocking retry thường được cấu hình bằng DefaultErrorHandler. Khi listener ném exception:

1. Container chuyển exception tới error handler.
2. Error handler phân loại exception.
3. Nếu exception được retry, handler chờ theo backoff.
4. Record được giao lại theo cơ chế seek/redelivery của container.
5. Nếu retry hết giới hạn, recoverer được gọi.
6. Recoverer có thể publish record sang DLT.

Ví dụ cấu hình hai lần retry, mỗi lần chờ một giây:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler() {
    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);
    return new DefaultErrorHandler(backOff);
}
~~~

Trong ví dụ, FixedBackOff(1_000L, 2L) có nghĩa là hai lần retry sau lần xử lý ban đầu. Nếu lần đầu thất bại và cả hai lần retry đều thất bại, listener đã được gọi tổng cộng ba lần trước khi xử lý phục hồi cuối cùng.

Gắn handler vào listener container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Listener dùng factory này sẽ áp dụng retry policy đã cấu hình.

## 3. Blocking retry phù hợp khi nào?

Blocking retry thường phù hợp khi:

- Lỗi có khả năng tự hết trong thời gian ngắn.
- Tổng thời gian retry nhỏ và dự đoán được.
- Các event phía sau cần chờ event trước hoàn tất.
- Giữ thứ tự xử lý trong partition quan trọng.
- Ứng dụng dùng batch listener.
- Listener cần container transaction theo cấu hình tương thích.
- Không muốn tạo thêm nhiều retry topic và consumer group.

Ví dụ database connection vừa bị reset. Thử lại sau một giây có thể thành công khi connection pool phục hồi.

Blocking retry cũng phù hợp khi event cùng aggregate có quan hệ thứ tự. Nếu OrderCreated chưa xử lý xong, PaymentCaptured có thể cần chờ để tránh tạo trạng thái không hợp lệ.

## 4. Hạn chế của blocking retry

Blocking retry sử dụng thời gian của consumer thread. Khi backoff dài hoặc record liên tục thất bại:

- Consumer thread dành thời gian chờ thay vì xử lý record mới.
- Record phía sau trong cùng partition có thể bị trì hoãn.
- Consumer lag tăng.
- Thời gian xử lý có thể tiến gần hoặc vượt max.poll.interval.ms.
- Nhiều consumer cùng retry có thể tạo tải lớn lên downstream.
- Một poison message có thể làm chậm luồng nếu phân loại exception sai.

Không nên dùng blocking retry với số lần vô hạn. Cần giới hạn số lần và tổng thời gian retry, sau đó chuyển record sang DLT hoặc cơ chế cách ly phù hợp.

Với backoff dài, cần xem xét cách Spring Kafka quản lý container pause/resume. Tùy phiên bản, có thể cấu hình ContainerPausingBackOffHandler để tránh giữ consumer thread trong một khoảng sleep dài; vẫn phải kiểm tra poll interval và thời gian pause thực tế.

## 5. Non-blocking retry hoạt động như thế nào?

Non-blocking retry dùng retry topics. Khi listener thất bại:

1. Retry infrastructure nhận exception.
2. Record được publish sang retry topic phù hợp với lần retry tiếp theo.
3. Record mang metadata cần thiết để xác định topic gốc và trạng thái retry.
4. Retry topic được xử lý bởi listener container tương ứng.
5. Nếu vẫn thất bại, record được chuyển sang retry topic kế tiếp hoặc DLT khi hết attempt.
6. Consumer của topic gốc có thể tiếp tục nhận record mới.

Spring Kafka hỗ trợ mô hình này thông qua `@RetryableTopic`.

~~~mermaid
flowchart TD
    A["orders topic"] --> B["Main listener"]
    B -->|Lỗi| C["orders-retry-1000"]
    C --> D["Retry listener"]
    D -->|Lỗi| E["orders-retry-2000"]
    E --> F["Retry listener"]
    F -->|Lỗi| G["orders-retry-4000"]
    G --> H["Retry listener"]
    H -->|Hết attempt| I["orders.DLT"]
    B -->|Thành công| J["Hoàn tất"]
    D -->|Thành công| J
    F -->|Thành công| J
    H -->|Thành công| J
~~~

Tên retry topic thực tế phụ thuộc naming strategy và cấu hình của ứng dụng. Sơ đồ chỉ minh họa các cấp retry theo thời gian chờ.

## 6. Non-blocking retry phù hợp khi nào?

Non-blocking retry thường phù hợp khi:

- Khoảng chờ retry dài hơn mức blocking hợp lý.
- Downstream có thể hồi phục sau vài phút hoặc lâu hơn.
- Event phía sau có thể tiếp tục xử lý độc lập.
- Nghiệp vụ chấp nhận record được xử lý trễ và thứ tự có thể thay đổi.
- Muốn tách tải retry khỏi consumer của topic chính.
- Cần nhiều mức backoff theo thời gian.

Ví dụ một event cần chờ dịch vụ đối tác hoàn tất đồng bộ dữ liệu. Retry sau 1 phút, 5 phút và 15 phút hợp lý hơn việc giữ consumer thread chờ liên tục.

Non-blocking retry không phải lựa chọn tự động cho mọi lỗi lâu. Nếu event phía sau phụ thuộc event trước, việc đưa record cũ sang retry topic có thể làm sai thứ tự nghiệp vụ.

## 7. Cấu hình @RetryableTopic

Ví dụ listener retry tối đa bốn lần, với exponential backoff:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 10_000
    ),
    dltTopicSuffix = ".DLT"
)
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.createInvoice(event);
}
~~~

Trong ví dụ:

- `attempts = "4"` là tối đa bốn lần xử lý, thông thường bao gồm lần giao ban đầu.
- `delay = 1_000` là khoảng chờ ban đầu một giây.
- `multiplier = 2.0` tăng khoảng chờ theo hệ số hai.
- `maxDelay = 10_000` giới hạn khoảng chờ ở mười giây.
- `dltTopicSuffix = ".DLT"` chỉ định hậu tố tên DLT.

Hãy kiểm tra semantics của annotation theo phiên bản Spring Kafka trong dự án khi nâng cấp dependency. Thời gian thực tế còn phụ thuộc scheduler, consumer poll và tải broker, không phải một lịch chạy thời gian thực tuyệt đối.

### 7.1. Xử lý DLT bằng @DltHandler

Có thể đặt DLT handler trong cùng class với listener:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0)
)
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.createInvoice(event);
}

@DltHandler
public void handleDlt(OrderCreated event) {
    dltService.storeForInvestigation(event);
}
~~~

`@DltHandler` nhận record đã hết retry theo cấu hình. DLT handler cần ghi nhận đủ thông tin để điều tra và replay; với dữ liệu không deserialize được, cần cấu hình consumer/DLT phù hợp để giữ và đọc raw bytes.

Không nên tự động publish record từ DLT về topic chính liên tục. Hãy có quy trình sửa nguyên nhân, kiểm tra dữ liệu và replay có kiểm soát.

### 7.2. Phân loại exception cho retry topic

Có thể giới hạn loại exception được retry:

~~~java
@RetryableTopic(
    attempts = "4",
    include = {
        TransientDataAccessException.class,
        TimeoutException.class
    },
    exclude = {
        IllegalArgumentException.class,
        UnsupportedOperationException.class
    },
    backoff = @Backoff(delay = 1_000, multiplier = 2.0)
)
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.createInvoice(event);
}
~~~

Lỗi validation thường không tự hết khi chờ nên không cần retry. Lỗi timeout hoặc database transient có thể retry nếu thao tác có thể chạy lặp an toàn.

Nếu một exception bọc exception khác, hãy kiểm tra cấu hình traversing causes và phân loại dựa trên root cause. Tránh phân loại quá rộng khiến lỗi cấu hình hoặc dữ liệu bị retry vô ích.

## 8. So sánh blocking và non-blocking retry

| Tiêu chí | Blocking retry | Non-blocking retry |
|---|---|---|
| Cơ chế | Error handler giao lại record trong luồng container | Publish record sang retry topic |
| Consumer thread | Dành thời gian chờ/retry | Consumer topic chính có thể tiếp tục |
| Thời gian chờ | Tốt cho khoảng chờ ngắn | Tốt cho khoảng chờ dài |
| Ordering | Có thể giữ thứ tự partition tốt hơn | Có thể thay đổi thứ tự |
| Partition phía sau | Có thể bị trì hoãn | Có thể tiếp tục xử lý |
| Hạ tầng | Ít topic hơn | Cần retry topics và DLT |
| Batch listener | Có thể hỗ trợ theo error handler | Không hỗ trợ theo retry-topic feature |
| Container transaction | Có thể cấu hình phù hợp | Không tương thích với container transaction |
| Vận hành | Theo dõi error handler và retry count | Theo dõi nhiều topic, lag và retry schedule |
| Phù hợp | Retry ngắn, thứ tự quan trọng | Retry dài, event độc lập |

## 9. Ordering là tiêu chí quyết định

Kafka chỉ bảo đảm thứ tự trong từng partition của một topic. Blocking retry có thể giữ record thất bại trong luồng xử lý partition, vì vậy các record phía sau bị trì hoãn cho đến khi record lỗi được xử lý hoặc phục hồi.

Ví dụ:

~~~text
orders partition 0:
offset 10 -> OrderCreated(order-01)  [thất bại]
offset 11 -> PaymentCaptured(order-01)
offset 12 -> OrderCompleted(order-01)
~~~

Với blocking retry, offset 11 và 12 có thể phải chờ offset 10.

Với non-blocking retry, OrderCreated được chuyển sang retry topic. Consumer của orders topic có thể tiếp tục xử lý PaymentCaptured và OrderCompleted trước khi OrderCreated retry thành công.

Điều này chỉ an toàn nếu các event độc lập hoặc business logic có thể xử lý event đến trễ. Nếu không, cần:

- Giữ blocking retry.
- Dùng state machine để kiểm tra trạng thái hợp lệ.
- Mang sequence/version trong event.
- Trì hoãn event phụ thuộc khi prerequisite chưa hoàn tất.
- Thiết kế consumer có thể phát hiện và xử lý event đến sai thứ tự.

Dùng cùng key để các event vào cùng partition không tự giải quyết việc non-blocking retry thay đổi thứ tự giữa topic chính và retry topic.

## 10. Batch listener và transaction

Non-blocking retry topic có giới hạn quan trọng: Spring Kafka retry-topic feature không hỗ trợ batch listener và không kết hợp với container transaction theo các cấu hình được tài liệu Spring Kafka quy định.

Nếu endpoint cần nhận `List<ConsumerRecord<K,V>>` hoặc cần transaction do listener container quản lý, hãy cân nhắc blocking retry với `DefaultErrorHandler`.

Nếu muốn chuyển sang non-blocking retry, cần đánh giá lại listener method, transaction boundary và yêu cầu ordering. Không chỉ thêm annotation `@RetryableTopic` vào batch listener hiện có rồi giả định cơ chế sẽ hoạt động.

Với transaction, cần phân biệt:

- Database transaction bảo vệ cập nhật database.
- Kafka transaction có thể phối hợp việc publish record và offset theo cấu hình.
- Non-blocking retry chuyển record qua topic khác, nên semantics không phải một transaction duy nhất bao trùm toàn bộ chuỗi retry.

## 11. Cấu hình DLT cho blocking retry

Với blocking retry, có thể dùng `DeadLetterPublishingRecoverer`:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {
    return new DeadLetterPublishingRecoverer(kafkaTemplate);
}

@Bean
public DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

Khi retry hết giới hạn, recoverer publish record sang DLT. Resolver mặc định thường dùng hậu tố `.DLT` và giữ partition nguồn. Vì vậy, cần bảo đảm DLT có đủ partition hoặc cấu hình destination resolver phù hợp.

DLT publish có thể thất bại do ACL, topic chưa tồn tại, thiếu partition, serializer lỗi hoặc broker/network lỗi. Cần theo dõi recoverer và chỉ xem record đã được phục hồi khi publish DLT thành công theo semantics của handler.

## 12. Retry topic topology và quản lý topic

Non-blocking retry tạo thêm topic cho các mức chờ và một DLT. Với topic chính commerce.order.created, topology có thể có dạng:

~~~text
commerce.order.created
commerce.order.created-retry-1000
commerce.order.created-retry-2000
commerce.order.created-retry-4000
commerce.order.created.DLT
~~~

Tên topic thực tế phụ thuộc naming strategy, suffix và phiên bản Spring Kafka.

Khi thiết kế topology, cần xác định:

- Topic nào được tạo tự động và topic nào do platform quản lý.
- Số partition của retry topic và DLT.
- Replication factor.
- Retention của từng retry topic.
- ACL cho producer và consumer.
- Cleanup policy.
- Naming strategy để tránh trùng tên.
- Cách xử lý khi tăng số partition topic chính.

Nếu resolver giữ partition nguồn, retry topic/DLT phải có partition tương ứng. Kiểm tra cấu hình thực tế và tạo topic trước trong production khi auto-create không được phép.

Retry topic cần retention đủ dài cho lịch retry và khả năng vận hành. Không đặt retention ngắn hơn thời gian record có thể nằm chờ trong retry topology.

## 13. Throughput, lag và tải hệ thống

Blocking retry làm giảm thời gian consumer dành cho record mới khi phải chờ. Non-blocking retry giải phóng luồng chính nhưng tạo thêm lưu lượng publish/consume trên retry topics.

| Chỉ số | Blocking retry | Non-blocking retry |
|---|---|---|
| Consumer lag topic chính | Có thể tăng khi record bị retry lâu | Có thể thấp hơn vì record lỗi được chuyển đi |
| Broker I/O | Ít topic và lượt publish bổ sung | Tăng do publish/consume retry topics |
| Consumer thread | Có thể bị giữ trong backoff | Consumer retry riêng xử lý theo lịch |
| Downstream load | Retry theo backoff của consumer | Nhiều retry consumer có thể tạo tải nếu không giới hạn |
| Vận hành | Tương đối đơn giản | Cần theo dõi topology nhiều topic |

Non-blocking retry không làm lỗi biến mất. Nó chuyển công việc sang một luồng topic khác. Nếu downstream vẫn outage, retry topics sẽ tích lũy record và cần cảnh báo.

Theo dõi:

- Lag của topic chính và từng retry topic.
- Số record trong DLT.
- Tuổi của record cũ nhất.
- Retry attempt count.
- Tỷ lệ lỗi theo exception type.
- Thời gian xử lý mỗi attempt.
- Lỗi publish retry/DLT.
- Throughput và latency của downstream.

## 14. Idempotency khi retry

Cả hai cơ chế đều có thể khiến một nghiệp vụ được thử nhiều lần. Kafka consumer có thể nhận lại record sau lỗi, rebalance hoặc trước khi offset được commit.

Không giả định một record chỉ được xử lý đúng một lần. Hãy thiết kế idempotency bằng event ID và unique constraint hoặc inbox table.

Ví dụ bảng:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng database transaction:

1. Insert event ID.
2. Nếu đã tồn tại, bỏ qua side effect theo chính sách.
3. Nếu insert thành công, thực hiện nghiệp vụ.
4. Commit marker và thay đổi nghiệp vụ cùng nhau.

Với non-blocking retry, record có thể được xử lý ở topic chính, retry topic và DLT replay. Event ID gốc cần được giữ để idempotency hoạt động xuyên suốt.

## 15. Chọn chiến lược theo tình huống

| Tình huống | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Database timeout trong vài giây | Blocking retry | Backoff ngắn, đơn giản |
| API 503 kéo dài vài phút | Non-blocking retry | Không giữ consumer chính chờ lâu |
| Event sau phụ thuộc event trước | Blocking retry | Giữ luồng partition |
| Event có thể xử lý độc lập | Non-blocking retry | Luồng chính tiếp tục |
| Listener dùng batch | Blocking retry | Retry topic không hỗ trợ batch listener |
| Listener dùng container transaction | Blocking retry | Retry topic không tương thích container transaction |
| Payload sai schema | DLT/cách ly | Chờ không sửa được byte hoặc schema |
| HTTP 429 với Retry-After dài | Non-blocking hoặc lịch retry phù hợp | Tránh giữ consumer thread |
| Credential/ACL sai trên diện rộng | Dừng/cảnh báo và sửa cấu hình | Retry liên tục không giải quyết gốc lỗi |
| Retry ngắn nhưng cần giữ throughput | Đo tải và cân nhắc phân vùng luồng | Blocking có thể gây nghẽn partition |

Đừng chọn non-blocking chỉ vì muốn throughput cao. Nếu ordering là invariant nghiệp vụ, việc giải phóng partition có thể tạo lỗi dữ liệu khó phát hiện hơn consumer lag.

## 16. Kiểm thử blocking retry

Với blocking retry, test cần xác nhận:

- Listener được gọi đúng số lần.
- Backoff và giới hạn retry được áp dụng.
- Exception non-retryable không bị retry.
- Recoverer chỉ chạy sau khi retry hết hoặc lỗi được phân loại không retry.
- DLT nhận đúng key/value và metadata.
- Offset chỉ được commit theo policy sau khi xử lý hoặc phục hồi thành công.

Dùng EmbeddedKafka hoặc Testcontainers để khởi động container thật. Không gọi trực tiếp listener method rồi kết luận retry hoạt động, vì retry được điều phối bởi listener container và error handler.

## 17. Kiểm thử non-blocking retry

Với retry topic, cần kiểm tra toàn bộ topology:

1. Gửi record vào topic chính.
2. Làm listener thất bại có chủ đích.
3. Xác nhận record được publish vào retry topic.
4. Chờ đến thời điểm retry.
5. Cho listener xử lý thành công hoặc tiếp tục thất bại.
6. Xác nhận record chuyển qua các mức retry đúng cấu hình.
7. Khi hết attempt, xác nhận record xuất hiện trong DLT.
8. Kiểm tra headers nguồn, attempt và exception.
9. Xác nhận event phía sau trên topic chính có thể được xử lý trong lúc record kia chờ retry.
10. Kiểm tra duplicate và idempotency.

Thời gian retry trong test nên đủ ngắn để test không kéo dài, nhưng vẫn xác nhận được lịch chờ. Dùng Awaitility hoặc latch thay vì sleep cố định.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Record bị retry quá nhiều | attempts/backoff chưa hiểu đúng | Kiểm tra số attempt gồm lần đầu |
| Partition bị nghẽn | Blocking retry kéo dài | Giảm backoff hoặc cân nhắc retry topic nếu ordering cho phép |
| Event xử lý sai thứ tự | Non-blocking retry để event phụ thuộc chạy tiếp | Dùng blocking retry hoặc sequence/state validation |
| Retry topic không nhận record | Topic/ACL/serializer/destination resolver sai | Kiểm tra producer và topic topology |
| DLT publish thất bại | Thiếu partition, ACL hoặc topic | Tạo topic và cấu hình quyền |
| Retry topic tích lũy record | Downstream vẫn lỗi hoặc consumer retry thiếu capacity | Theo dõi lag, scale có kiểm soát, xử lý nguyên nhân |
| Listener batch không hoạt động với @RetryableTopic | Retry-topic feature không hỗ trợ batch | Dùng blocking retry hoặc thiết kế lại listener |
| Transaction listener không tương thích | Retry topic không hỗ trợ container transaction | Dùng blocking retry theo transaction model |
| Duplicate side effect | Retry/replay và consumer redelivery | Idempotency bằng event ID |
| Test không thấy retry | Gọi trực tiếp method thay vì container | Dùng integration test với listener container |

## 19. Quy trình triển khai lựa chọn retry

Trước khi triển khai, thực hiện theo thứ tự:

1. Phân loại lỗi: transient, validation, serialization hay configuration.
2. Xác định thời gian retry tối đa theo SLA.
3. Xác định event có phụ thuộc thứ tự với record phía sau không.
4. Kiểm tra listener có dùng batch hoặc container transaction không.
5. Chọn blocking hoặc non-blocking retry.
6. Cấu hình exception classification và số attempt.
7. Cấu hình DLT, partition, retention và ACL.
8. Thiết kế idempotency cho side effect.
9. Kiểm thử retry, DLT publish failure, replay và duplicate.
10. Thiết lập alert cho lag, retry rate và DLT rate.

~~~mermaid
flowchart TD
    A["Có record xử lý thất bại"] --> B{"Cần giữ thứ tự partition?"}
    B -->|Có| C["Blocking retry"]
    B -->|Không| D{"Cần chờ lâu?"}
    D -->|Không| C
    D -->|Có| E{"Batch listener hoặc container transaction?"}
    E -->|Có| C
    E -->|Không| F["Non-blocking retry"]
    C --> G["Retry giới hạn + backoff"]
    F --> H["Retry topics + backoff"]
    G --> I{"Hết retry?"}
    H --> I
    I -->|Không| J["Thử lại"]
    I -->|Có| K["DLT và quy trình replay"]
~~~

## 20. Checklist trước khi đưa vào production

- [ ] Đã phân loại exception retryable và non-retryable?
- [ ] Đã chọn blocking hay non-blocking theo ordering và thời gian chờ?
- [ ] Số attempt có bao gồm lần xử lý ban đầu?
- [ ] Backoff có giới hạn tổng thời gian?
- [ ] Listener có idempotent?
- [ ] Có batch listener hoặc container transaction cần giữ?
- [ ] Retry topic có đủ partition và retention?
- [ ] DLT có đủ partition, ACL và replication?
- [ ] Serializer xử lý được record lỗi và raw bytes?
- [ ] DLT có headers để truy vết nguồn?
- [ ] Replay có quy trình và audit?
- [ ] Có alert cho retry rate, DLT rate và retry topic lag?
- [ ] Đã kiểm thử ordering khi record bị retry?
- [ ] Đã kiểm thử DLT publish failure?
- [ ] Đã kiểm thử duplicate delivery và idempotency?
- [ ] Đã kiểm tra tương thích theo phiên bản Spring Kafka đang chạy?

## 21. Kết luận

Blocking retry phù hợp với lỗi tạm thời cần thử lại nhanh, đặc biệt khi thứ tự trong partition quan trọng hoặc listener dùng batch/container transaction. Non-blocking retry phù hợp khi cần chờ lâu và event phía sau có thể tiếp tục xử lý độc lập; Spring Kafka triển khai cơ chế này bằng retry topics và `@RetryableTopic`.

Non-blocking retry giải phóng luồng topic chính nhưng làm thay đổi thứ tự có thể quan sát và tăng độ phức tạp vận hành do có thêm retry topics. Blocking retry đơn giản hơn nhưng có thể giữ consumer thread và làm chậm partition. Hãy quyết định dựa trên ordering, SLA, thời gian chờ, loại listener, transaction, tải broker và khả năng idempotency; sau đó kiểm thử toàn bộ đường đi từ lần nhận đầu đến DLT và replay.

