# Chọn retry hay dead letter

## Mục tiêu của bài học

Trong chương **Retry**, bài này hướng dẫn lựa chọn cách xử lý khi một Kafka message không được listener xử lý thành công: thử lại (retry), chuyển sang dead-letter topic (DLT), hay kết hợp cả hai. Quyết định cần dựa trên nguyên nhân lỗi, khả năng phục hồi, thời gian chờ, yêu cầu thứ tự và tác động tới consumer group.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Retry và DLT là hai phần của chiến lược xử lý lỗi nhằm giữ luồng messaging đáng tin cậy khi downstream gặp sự cố hoặc dữ liệu không hợp lệ.

Sau bài học, người học có thể:

- Phân biệt lỗi tạm thời, lỗi dữ liệu và lỗi cấu hình/hệ thống.
- Quyết định khi nào nên retry, khi nào nên chuyển thẳng sang DLT.
- Thiết kế retry có giới hạn, backoff và phân loại exception.
- Cấu hình `DefaultErrorHandler` và `DeadLetterPublishingRecoverer`.
- Hiểu blocking retry và non-blocking retry bằng retry topics.
- Đánh giá ảnh hưởng tới ordering, partition, consumer lag và throughput.
- Thiết kế DLT consumer, quy trình replay và idempotency.
- Kiểm thử số lần retry, DLT publish và các tình huống lỗi.

## 1. Retry và dead letter giải quyết vấn đề gì?

Kafka lưu record bền vững trong topic. Khi consumer nhận một record, listener có thể xử lý thành công hoặc ném exception. Nếu xử lý thất bại, ứng dụng cần quyết định điều gì sẽ xảy ra tiếp theo.

Hai cơ chế chính:

- **Retry:** thử xử lý lại cùng record sau một khoảng chờ hoặc theo một lịch retry.
- **Dead letter:** chuyển record không thể xử lý thành công sang một topic riêng để điều tra, sửa dữ liệu hoặc replay sau này.

Chúng không loại trừ nhau. Một chiến lược thường dùng là retry một số lần với backoff, sau đó chuyển record thất bại sang DLT.

~~~mermaid
flowchart TD
    A["Consumer nhận record"] --> B["Listener xử lý"]
    B --> C{"Thành công?"}
    C -->|Có| D["Commit offset theo AckMode"]
    C -->|Không| E{"Lỗi có thể phục hồi?"}
    E -->|Có| F["Retry có giới hạn"]
    F --> B
    E -->|Không| G["Dead-letter topic"]
    F --> H{"Hết retry?"}
    H -->|Chưa| B
    H -->|Rồi| G
    G --> I["Điều tra / sửa / replay"]
~~~

Mục tiêu không phải là retry mọi lỗi. Retry chỉ có ích khi có cơ hội lần xử lý sau thành công. Với dữ liệu sai vĩnh viễn, retry lặp lại cùng một thao tác thường chỉ làm chậm partition và tăng tải.

## 2. Phân loại lỗi trước khi chọn chính sách

Trước khi cấu hình Spring Kafka, hãy phân loại lỗi theo khả năng phục hồi.

| Nhóm lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Lỗi tạm thời (transient) | Timeout ngắn, HTTP 503, database connection tạm mất | Retry có backoff và giới hạn |
| Lỗi giới hạn tốc độ | HTTP 429, downstream yêu cầu chờ | Retry sau thời gian phù hợp hoặc đưa vào retry topic |
| Lỗi dữ liệu (poison message) | Thiếu trường bắt buộc, enum không hợp lệ, business rule bị vi phạm | DLT ngay hoặc retry rất ít nếu dữ liệu có thể được bổ sung |
| Lỗi serialization/deserialization | Byte không đúng format, schema không tương thích | Cách ly/DLT sau khi cấu hình error handling phù hợp |
| Lỗi cấu hình/hạ tầng kéo dài | Sai credential, ACL, topic không tồn tại, endpoint sai | Dừng hoặc cảnh báo và sửa cấu hình; retry mù không giải quyết nguyên nhân |
| Lỗi nghiệp vụ có thể thay đổi theo thời gian | Tài khoản chưa được kích hoạt, phụ thuộc vào event khác | Retry có thời hạn hoặc retry topic theo lịch nghiệp vụ |

Ví dụ:

- Database vừa mất kết nối trong vài giây: retry có thể thành công.
- Event thiếu `orderId`: cùng payload sẽ tiếp tục thiếu `orderId`, nên retry không giúp ích.
- API trả 429 và có `Retry-After`: nên tôn trọng thời gian chờ của downstream.
- Credential bị thu hồi: retry liên tục có thể tạo tải và log noise trong khi cần sửa secret/quyền truy cập.

Phân loại exception phải dựa trên nguyên nhân thực tế. Không nên chỉ dựa vào tên exception nếu cùng một exception type có thể đại diện cho cả lỗi tạm thời lẫn lỗi vĩnh viễn.

## 3. Khi nào nên retry?

Retry phù hợp khi lỗi có khả năng tự hết mà không cần thay đổi message hoặc code.

Ví dụ:

- Network timeout ngắn.
- Database connection reset.
- Dịch vụ downstream đang deploy hoặc restart.
- HTTP 503 trong thời gian ngắn.
- Rate limit có thời gian chờ xác định.
- Deadlock database mà transaction có thể chạy lại an toàn.

Một retry policy tốt cần xác định:

1. Exception nào được retry.
2. Số lần retry tối đa.
3. Khoảng chờ giữa các lần thử.
4. Tổng thời gian tối đa dành cho retry.
5. Hành động khi hết retry.
6. Cách bảo đảm thao tác lặp không gây side effect trùng.

Retry không nên vô hạn. Retry vô hạn có thể giữ một partition bị chặn rất lâu, làm tăng consumer lag và ngăn các record sau trong partition được xử lý.

## 4. Khi nào nên chuyển thẳng sang DLT?

DLT phù hợp khi record không thể xử lý thành công với dữ liệu hiện tại hoặc cần con người/hệ thống khác can thiệp.

Các tình huống thường gặp:

- Payload không hợp lệ hoặc thiếu dữ liệu bắt buộc.
- Giá trị enum hoặc mã nghiệp vụ không được hỗ trợ.
- Schema không tương thích và không thể deserialize.
- Business rule xác định record không được chấp nhận.
- Đã retry đủ số lần nhưng lỗi vẫn còn.
- Cần cách ly record để giữ luồng chính tiếp tục.

Chuyển DLT không có nghĩa là xóa lỗi. DLT là nơi lưu record thất bại để điều tra và quyết định bước tiếp theo.

Không nên đưa mọi lỗi vào DLT ngay lập tức. Nếu downstream chỉ mất kết nối trong 2 giây, DLT sẽ nhận nhiều record có thể xử lý thành công sau khi dịch vụ hồi phục, tạo thêm quy trình replay không cần thiết.

## 5. Bảng quyết định retry hay DLT

| Câu hỏi | Nếu có | Nếu không |
|---|---|---|
| Lỗi có khả năng tự hết trong thời gian ngắn? | Retry có giới hạn | Xem xét DLT hoặc sửa cấu hình |
| Payload có hợp lệ và đủ dữ liệu? | Tiếp tục đánh giá retry | DLT hoặc từ chối theo nghiệp vụ |
| Downstream có đưa ra thời gian retry? | Tuân thủ thời gian chờ nếu có thể | Dùng backoff đã thiết kế |
| Thao tác có idempotent? | Có thể retry an toàn hơn | Phải bổ sung idempotency trước |
| Thời gian chờ có làm nghẽn partition? | Blocking retry có thể phù hợp | Dùng retry topic hoặc cách ly |
| Đã vượt số lần/thời gian retry? | Chuyển DLT | Tiếp tục theo policy |

Một quy tắc thực tế:

- Lỗi transient ngắn: retry có giới hạn.
- Lỗi dữ liệu không thể tự sửa: DLT ngay.
- Lỗi transient nhưng cần chờ lâu: cân nhắc retry topic.
- Lỗi cấu hình diện rộng: cảnh báo, khắc phục nguyên nhân và kiểm soát consumer thay vì retry liên tục.
- Hết retry: chuyển DLT và tạo tín hiệu vận hành để xử lý.

## 6. Blocking retry trong Spring Kafka

Với blocking retry, consumer giữ luồng xử lý của record thất bại và thử lại theo backoff. Cách này thường được cấu hình qua `DefaultErrorHandler`.

Ví dụ tạo handler với hai lần retry, mỗi lần cách nhau một giây:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler() {
    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(backOff);
}
~~~

Trong ví dụ, `FixedBackOff(1_000L, 2L)` nghĩa là khoảng chờ 1.000 ms và tối đa hai lần retry sau lần xử lý ban đầu. Tổng số lần listener có thể được gọi là ba: một lần đầu và hai lần retry.

Gắn handler vào container factory:

~~~java
@Bean(name = "ordersKafkaListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);

    return factory;
}
~~~

Các listener dùng factory này sẽ sử dụng common error handler đã cấu hình. Nếu nhóm listener có retry policy khác nhau, hãy tạo factory riêng để mỗi nhóm có chính sách phù hợp.

### 6.1. Blocking retry ảnh hưởng partition như thế nào?

Kafka bảo đảm thứ tự trong một partition. Khi một record ở đầu luồng bị lỗi và đang được retry theo cơ chế blocking, các record tiếp theo của partition đó có thể phải chờ.

Ví dụ:

~~~text
Partition 0:
offset 10 -> OrderCreated (thất bại, đang retry)
offset 11 -> PaymentCaptured
offset 12 -> OrderCompleted
~~~

Nếu offset 10 chưa được xử lý hoặc phục hồi, listener có thể chưa tiếp tục xử lý các record sau theo semantics của error handler và container.

Đây là trade-off:

- Giữ luồng xử lý theo thứ tự của partition.
- Chấp nhận record lỗi có thể làm chậm record phía sau.

Nếu các event không cần chờ nhau và có thể được xử lý độc lập, retry topic có thể giúp luồng chính tiếp tục. Nhưng khi chuyển sang retry topic, thứ tự xử lý ban đầu có thể thay đổi.

## 7. Backoff: chờ bao lâu giữa các lần retry?

Backoff giúp tránh retry liên tục khi downstream đang gặp sự cố.

### 7.1. Fixed backoff

Mỗi lần retry chờ cùng một khoảng thời gian:

~~~java
FixedBackOff backOff = new FixedBackOff(1_000L, 3L);
~~~

Phù hợp với lỗi tạm thời có thời gian hồi phục ngắn và ổn định. Giá trị trên là ba lần retry, mỗi lần cách nhau một giây.

### 7.2. Exponential backoff

Khoảng chờ tăng dần theo số lần retry. Ví dụ 1 giây, 2 giây, 4 giây, 8 giây.

~~~java
ExponentialBackOff backOff =
    new ExponentialBackOff(1_000L, 2.0);

backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(backOff);
~~~

Trong ví dụ, khoảng chờ bắt đầu ở 1 giây, tăng theo hệ số 2, không vượt 10 giây và tổng thời gian backoff được giới hạn theo cấu hình.

Exponential backoff phù hợp khi downstream cần thời gian hồi phục tăng dần. Với nhiều consumer retry cùng lúc, có thể cân nhắc jitter nếu tầng retry hỗ trợ, nhằm tránh tất cả consumer gọi lại downstream cùng thời điểm.

### 7.3. Backoff không thay thế giới hạn retry

Chỉ cấu hình khoảng chờ chưa đủ. Cần đặt số lần hoặc tổng thời gian retry tối đa. Nếu không, record lỗi có thể giữ partition trong thời gian không kiểm soát.

Hãy chọn giới hạn theo:

- SLO của luồng nghiệp vụ.
- Thời gian hồi phục dự kiến của downstream.
- `max.poll.interval.ms` và thời gian xử lý container.
- Lượng record đang chờ trong partition.
- Khả năng tải của dịch vụ phụ thuộc.

## 8. Phân loại exception trong DefaultErrorHandler

Không phải exception nào cũng nên retry. Có thể đánh dấu exception không retry được:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler() {
    DefaultErrorHandler handler = new DefaultErrorHandler(
        new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class,
        UnsupportedOperationException.class
    );

    return handler;
}
~~~

Ví dụ, `IllegalArgumentException` do payload sai có thể được chuyển tới recoverer ngay sau lần xử lý đầu tiên. Các exception còn lại dùng retry policy mặc định của handler, trừ khi được phân loại thêm.

Có thể bổ sung exception retry được bằng `addRetryableExceptions(...)` khi cần điều chỉnh phân loại mặc định.

Phân loại exception cần cẩn trọng:

- Đừng đánh dấu exception gốc là non-retryable nếu nó có thể bọc lỗi network tạm thời.
- Đừng retry lỗi validation không thể thay đổi bằng cách chờ.
- Tách exception nghiệp vụ khỏi exception hạ tầng.
- Log nguyên nhân gốc, không chỉ log wrapper exception.
- Viết test để xác nhận mỗi loại lỗi có đúng số lần thử.

## 9. Kết hợp retry với DeadLetterPublishingRecoverer

Khi retry hết giới hạn, có thể publish record lỗi sang DLT bằng `DeadLetterPublishingRecoverer`.

Ví dụ:

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

Với resolver mặc định, Spring Kafka thường dùng tên topic nguồn cộng hậu tố `.DLT` và giữ partition nguồn. Ví dụ record từ `commerce.order.created` ở partition 2 sẽ được gửi tới `commerce.order.created.DLT` ở partition 2.

Vì partition được giữ nguyên, DLT thường cần có ít nhất số partition tương ứng với topic nguồn. Nếu muốn định tuyến sang partition khác hoặc một DLT dùng chung, hãy cấu hình destination resolver phù hợp và kiểm tra khả năng phân phối.

`KafkaTemplate` dùng để publish DLT phải serialize được key/value của record thất bại. Với lỗi deserialize, record có thể chứa raw byte và thông tin exception; cấu hình producer/recoverer cần hỗ trợ cả dữ liệu gốc lẫn kiểu object nếu ứng dụng có nhiều loại record.

### 9.1. Sơ đồ retry rồi DLT

~~~mermaid
flowchart TD
    A["Listener nhận record"] --> B{"Xử lý thành công?"}
    B -->|Có| C["Commit offset"]
    B -->|Không| D["DefaultErrorHandler"]
    D --> E{"Exception retryable?"}
    E -->|Có| F["Backoff và retry"]
    F --> A
    E -->|Không| G["Recoverer"]
    F --> H{"Hết retry?"}
    H -->|Chưa| A
    H -->|Rồi| G
    G --> I["DeadLetterPublishingRecoverer"]
    I --> J["orders.DLT"]
    J --> K["Điều tra / sửa / replay"]
~~~

### 9.2. DLT publish cũng có thể thất bại

Không nên giả định publish DLT luôn thành công. Có thể gặp:

- DLT chưa tồn tại và broker không cho auto-create.
- Producer thiếu ACL ghi DLT.
- Serializer không serialize được key/value.
- DLT không có partition tương ứng với partition nguồn.
- Broker hoặc network đang lỗi.
- Publish timeout hoặc send result thất bại.

Cần giám sát lỗi recoverer, kiểm tra kết quả publish theo API/phiên bản đang dùng và xác định hành vi khi recoverer thất bại. Nếu record chưa được publish an toàn, không nên đánh dấu xử lý thành công rồi bỏ mất record.

## 10. DLT nên chứa thông tin gì?

DeadLetterPublishingRecoverer của Spring Kafka bổ sung các headers giúp truy vết record gốc và exception. Các thông tin thường dùng gồm:

- Topic gốc.
- Partition gốc.
- Offset gốc.
- Timestamp gốc.
- Exception class.
- Exception message.
- Stack trace theo cấu hình.

Trong code, có thể đọc các header DLT bằng các hằng số của `KafkaHeaders`, ví dụ `DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION`, `DLT_ORIGINAL_OFFSET` và `DLT_EXCEPTION_MESSAGE`. Tên và khả năng hỗ trợ cụ thể cần đối chiếu phiên bản Spring Kafka đang sử dụng.

Không chỉ lưu message lỗi ở log rồi bỏ payload. DLT cần đủ thông tin để người vận hành xác định record nào thất bại, vì sao, ở đâu và có thể replay như thế nào.

## 11. Xử lý record trong DLT

DLT nên có consumer hoặc quy trình vận hành riêng. Không nên tạo listener tự động đọc DLT rồi publish ngược lại topic gốc liên tục, vì điều đó có thể tạo vòng lặp lỗi vô hạn.

Ví dụ listener kiểm tra DLT:

~~~java
@KafkaListener(
    topics = "commerce.order.created.DLT",
    groupId = "order-dlt-inspector"
)
public void inspect(ConsumerRecord<String, OrderCreated> record) {
    Header reasonHeader = record.headers().lastHeader(
        KafkaHeaders.DLT_EXCEPTION_MESSAGE
    );
    String reason = reasonHeader == null
        ? "unknown"
        : new String(reasonHeader.value(), StandardCharsets.UTF_8);

    log.error(
        "DLT record: topic={}, partition={}, offset={}, key={}, reason={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key(),
        reason
    );

    dltAuditService.store(record);
}
~~~

Ví dụ trên minh họa việc ghi nhận record lỗi. Trong ứng dụng thực tế, cần xử lý header có thể null và đọc đúng kiểu byte value. Nếu record không deserialize được thành `OrderCreated`, DLT consumer phải dùng deserializer có khả năng đọc raw bytes hoặc error payload tương ứng.

DLT consumer có thể thực hiện:

- Lưu record vào hệ thống quản lý lỗi.
- Gửi cảnh báo tới đội vận hành.
- Gắn trạng thái phân loại lỗi.
- Chờ dữ liệu hoặc schema được sửa.
- Replay có kiểm soát sau khi xác nhận nguyên nhân đã được khắc phục.
- Đánh dấu bỏ qua vĩnh viễn theo quyết định nghiệp vụ.

## 12. Replay record từ DLT

Replay là đưa record đã cách ly trở lại luồng xử lý sau khi nguyên nhân lỗi đã được sửa.

Quy trình nên có kiểm soát:

1. Xác định record gốc qua headers topic/partition/offset.
2. Điều tra exception và payload.
3. Sửa dữ liệu, schema, cấu hình hoặc dependency gây lỗi.
4. Xác định record có còn hợp lệ theo nghiệp vụ hay không.
5. Chọn topic đích và key phù hợp.
6. Publish lại record hoặc payload đã sửa.
7. Ghi nhận người thực hiện, thời gian và kết quả replay.
8. Theo dõi consumer xử lý thành công.

Không nên reset offset của topic chính một cách tùy tiện để replay một record đơn lẻ. Reset offset có thể làm consumer đọc lại nhiều record khác, gây duplicate và thay đổi tiến trình của consumer group.

Khi replay, cần giữ event ID gốc hoặc ghi replay metadata để hệ thống idempotency nhận diện sự kiện đã được xử lý trước đó.

## 13. Retry topic và non-blocking retry

Blocking retry giữ record trong luồng xử lý của consumer và chờ retry. Nếu cần chờ lâu, có thể dùng retry topic để chuyển record sang topic retry có thời gian chờ phù hợp.

Spring Kafka hỗ trợ non-blocking retry thông qua `@RetryableTopic` trong các phiên bản có tính năng này.

Ví dụ minh họa:

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

Spring Kafka tạo các retry topic và DLT theo cấu hình. `attempts` biểu diễn số lần xử lý tối đa trước khi gửi DLT và thông thường bao gồm lần giao ban đầu. Hãy xác nhận semantics của phiên bản dependency đang dùng, nhất là khi nâng cấp Spring Kafka.

Non-blocking retry phù hợp khi:

- Khoảng chờ retry dài hơn thời gian blocking hợp lý.
- Không muốn một record lỗi giữ luồng chính trong suốt thời gian chờ.
- Event phía sau có thể tiếp tục xử lý độc lập.
- Nghiệp vụ chấp nhận thay đổi thứ tự do record đi qua retry topic.

Cần lưu ý non-blocking retry có các giới hạn theo phiên bản Spring Kafka; đặc biệt, không hỗ trợ batch listener và không kết hợp với container transaction trong các cấu hình được tài liệu Spring Kafka quy định. Kiểm tra tài liệu đúng phiên bản trước khi áp dụng.

### 13.1. Blocking retry và retry topic khác nhau thế nào?

| Tiêu chí | Blocking retry | Non-blocking retry topic |
|---|---|---|
| Cách retry | Consumer thử lại record trong luồng xử lý | Publish record sang retry topic |
| Ảnh hưởng partition gốc | Có thể làm record phía sau chờ | Luồng chính có thể tiếp tục |
| Độ trễ dài | Có thể giữ consumer/partition lâu | Phù hợp hơn với lịch chờ dài |
| Ordering | Dễ giữ thứ tự partition hơn | Có thể thay đổi thứ tự |
| Hạ tầng | Error handler và backoff | Cần retry topic, DLT và consumer tương ứng |
| Vận hành | Tập trung ở listener container | Cần theo dõi nhiều topic hơn |
| Phù hợp | Retry ngắn, lỗi transient | Retry có lịch chờ dài và event độc lập |

## 14. Chọn thời gian retry theo đặc tính nghiệp vụ

Không phải mọi lỗi đều cần cùng một backoff.

| Loại lỗi | Chính sách gợi ý |
|---|---|
| Database timeout ngắn | Retry vài lần với backoff tăng dần |
| HTTP 503 | Retry có giới hạn, tôn trọng Retry-After nếu có |
| HTTP 429 | Chờ theo rate limit hoặc retry topic |
| Validation error | DLT ngay |
| Schema không tương thích | DLT/cách ly và cảnh báo schema |
| Tài khoản chưa sẵn sàng | Retry topic với thời gian chờ nghiệp vụ |
| Credential sai | Dừng/cảnh báo và sửa cấu hình; tránh retry mù |
| Hết retry nhưng dependency vẫn lỗi | DLT hoặc cơ chế circuit breaker/hold có kiểm soát tùy yêu cầu |

Thời gian retry cần nhỏ hơn hoặc phù hợp với SLA xử lý event. Nếu đơn hàng phải được xử lý trong 30 giây, một retry schedule kéo dài 24 giờ không đáp ứng yêu cầu nghiệp vụ.

## 15. Idempotency: điều kiện quan trọng để retry an toàn

Retry có thể khiến listener thực hiện cùng một nghiệp vụ nhiều lần. Kafka consumer cũng có thể nhận lại record khi xử lý thành công nhưng chưa commit offset, hoặc sau rebalance.

Ví dụ listener tạo hóa đơn:

~~~java
public void listen(OrderCreated event) {
    invoiceService.create(event);
}
~~~

Nếu lần đầu đã tạo hóa đơn nhưng consumer chưa commit offset, lần sau event được giao lại và có thể tạo hóa đơn thứ hai.

Thiết kế idempotent có thể dựa trên event ID và unique constraint:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng database transaction:

1. Thử ghi event ID vào `processed_event`.
2. Nếu event ID đã tồn tại, không thực hiện lại side effect.
3. Nếu insert thành công, thực hiện nghiệp vụ.
4. Commit trạng thái xử lý và thay đổi nghiệp vụ cùng nhau.

Idempotency cũng quan trọng khi replay từ DLT. Không dựa vào việc “record chỉ được xử lý một lần” để bảo vệ side effect bên ngoài.

## 16. Retry và thứ tự nghiệp vụ

Kafka chỉ bảo đảm thứ tự trong từng partition. Retry có thể ảnh hưởng cách các event liên quan được xử lý.

Với blocking retry, record lỗi có thể giữ luồng partition trong thời gian retry. Cách này hữu ích nếu event sau phụ thuộc event trước.

Với retry topic, record lỗi rời topic chính và có thể được xử lý sau record mới hơn. Ví dụ:

~~~text
Topic chính:
OrderCreated(order-01) -> retry topic
PaymentCaptured(order-01) -> xử lý ngay
OrderCompleted(order-01) -> xử lý ngay
~~~

Nếu nghiệp vụ yêu cầu `OrderCreated` phải hoàn tất trước `PaymentCaptured`, non-blocking retry có thể làm sai thứ tự nghiệp vụ.

Các lựa chọn:

- Dùng blocking retry khi cần giữ luồng partition.
- Dùng key ổn định để các event cùng entity ở cùng partition.
- Thiết kế state machine để từ chối hoặc trì hoãn event đến sai thứ tự.
- Dùng version/sequence number trong event để phát hiện event đến muộn.
- Chọn retry topic chỉ khi nghiệp vụ cho phép xử lý không theo thứ tự ban đầu.

## 17. Retry, consumer lag và throughput

Retry tiêu thụ tài nguyên và làm giảm khả năng xử lý record mới.

Các tác động có thể có:

- Consumer thread dành thời gian cho record lỗi.
- Partition bị chặn trong blocking retry.
- Consumer lag tăng.
- Downstream tiếp tục bị gọi trong lúc quá tải.
- Retry topic làm tăng số topic, partition, broker I/O và metric cần giám sát.
- DLT tạo thêm quy trình lưu trữ, điều tra và replay.

Nếu một downstream đang outage trên diện rộng, retry từng record có thể tạo retry storm. Có thể cần circuit breaker, pause/stop listener có kiểm soát hoặc cơ chế giới hạn tốc độ để tránh làm downstream quá tải thêm.

Đừng chỉ đo tổng số record thành công. Cần theo dõi retry count, DLT rate, consumer lag, processing time, thời gian recoverer publish và tuổi của record cũ nhất.

## 18. Xử lý lỗi deserialize

Lỗi deserialize xảy ra trước khi listener nhận được payload Java. Ví dụ producer gửi JSON sai hoặc consumer dùng schema không tương thích.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để chuyển lỗi deserialize thành thông tin có thể được error handler xử lý.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
~~~

Khi deserialize thất bại, cần cấu hình error handler và DLT publisher tương thích với raw bytes và exception header. Không giả định DLT consumer luôn có thể deserialize record lỗi thành class event bình thường.

## 19. Kiểm thử retry và DLT

Kiểm thử cần xác nhận hành vi quan sát được, không chỉ xác nhận exception được ghi log.

Các tình huống nên có:

| Test case | Kết quả cần xác nhận |
|---|---|
| Listener lỗi lần đầu, lần sau thành công | Retry đúng số lần và record được xử lý |
| Lỗi retryable liên tục | Dừng ở giới hạn và chuyển DLT |
| Lỗi non-retryable | Không retry không cần thiết |
| DLT publish thành công | Record xuất hiện trong DLT với metadata gốc |
| DLT publish thất bại | Recoverer báo lỗi và record không bị đánh dấu thành công sai |
| Deserialize lỗi | Error handler nhận được lỗi và raw record được cách ly |
| Replay DLT | Record được xử lý sau khi nguyên nhân được sửa |
| Duplicate delivery | Side effect không bị lặp nhờ idempotency |
| Retry topic | Record được giao theo lịch và DLT nhận record hết attempt |
| Ordering | Kiểm tra event liên quan không bị xử lý sai thứ tự |

Ví dụ stub service trong integration test để kiểm tra hai lần thất bại rồi thành công:

~~~java
doThrow(new TransientDataAccessResourceException("Temporary failure"))
    .doThrow(new TransientDataAccessResourceException("Temporary failure"))
    .doNothing()
    .when(billingService)
    .createInvoice(event);
~~~

Sau khi gửi event vào topic thử nghiệm, chờ listener xử lý rồi xác nhận `billingService.createInvoice(event)` được gọi ba lần. Test phải khởi chạy listener container với `DefaultErrorHandler` thật; gọi trực tiếp phương thức listener sẽ không kích hoạt cơ chế retry của container. Nếu nhiều event chạy đồng thời, xác minh số lần gọi theo từng event ID.

Với DLT, gửi một record gây lỗi và đọc topic DLT để xác nhận:

- Key/value hoặc raw bytes được giữ theo cấu hình.
- Header topic, partition, offset gốc có mặt.
- Exception header có lý do phù hợp.
- Record chỉ chuyển DLT sau đúng số lần retry.
- Consumer group chính tiếp tục xử lý record sau theo chính sách.

## 20. Vận hành DLT và quy trình xử lý

DLT cần có owner, retention và quy trình xử lý. Nếu không, DLT sẽ trở thành nơi chứa record lỗi không ai theo dõi.

Nên xác định:

- Ai nhận cảnh báo khi DLT tăng.
- DLT giữ record trong bao lâu.
- Payload có chứa dữ liệu nhạy cảm hay không.
- Ai được phép đọc/replay DLT.
- Cách sửa payload hoặc schema.
- Cách tránh replay trùng.
- Cách ghi audit cho thao tác replay.
- Khi nào được đánh dấu record là bỏ qua vĩnh viễn.

DLT cũng cần đủ tài nguyên và quyền truy cập. Tạo topic, partition, retention và ACL theo chính sách của môi trường. Không phụ thuộc vào auto-create topic trong production nếu quy trình vận hành yêu cầu topic được quản lý trước.

## 21. Checklist lựa chọn retry hay DLT

- [ ] Đã phân loại lỗi transient, permanent, validation hay configuration?
- [ ] Chỉ retry exception có khả năng phục hồi?
- [ ] Retry có số lần và tổng thời gian tối đa?
- [ ] Backoff phù hợp với SLA và khả năng downstream?
- [ ] Có tránh retry storm khi dependency outage?
- [ ] Listener có idempotent trước khi bật retry?
- [ ] Đã đánh giá blocking retry có làm nghẽn partition?
- [ ] Retry topic có làm thay đổi ordering nghiệp vụ?
- [ ] DLT topic tồn tại và có đủ partition?
- [ ] Producer dùng để publish DLT serialize được key/value/raw bytes?
- [ ] DLT headers đủ để truy vết record gốc?
- [ ] DLT consumer có xử lý dữ liệu không deserialize được?
- [ ] Replay có kiểm soát và giữ event ID?
- [ ] Có cảnh báo khi retry rate, DLT rate hoặc lag tăng?
- [ ] Đã kiểm thử retry thành công, hết retry, DLT publish failure và replay?

## Kết luận

Retry phù hợp với lỗi tạm thời có khả năng tự phục hồi; DLT phù hợp với dữ liệu không hợp lệ, lỗi không thể xử lý bằng cách thử lại hoặc record đã vượt giới hạn retry. Một chiến lược phổ biến là phân loại exception, retry có giới hạn với backoff, sau đó chuyển record thất bại sang DLT để điều tra và replay có kiểm soát.

Blocking retry giúp giữ luồng partition trong khi xử lý record lỗi nhưng có thể làm record phía sau chờ. Retry topic phù hợp với thời gian chờ dài và event độc lập, song có thể thay đổi thứ tự và có giới hạn theo loại listener/transaction. Dù chọn cách nào, hãy thiết kế idempotency, kiểm tra DLT publish, giám sát consumer lag và kiểm thử toàn bộ đường đi của record lỗi để luồng Kafka vận hành đáng tin cậy.
