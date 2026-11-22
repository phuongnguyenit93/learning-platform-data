# Not-retryable exception

Trong Spring Kafka, không phải exception nào cũng nên được retry. Retry hữu ích khi lỗi có khả năng tự hết sau một khoảng thời gian, chẳng hạn database tạm thời quá tải hoặc kết nối mạng gián đoạn. Với lỗi bắt nguồn từ dữ liệu không hợp lệ, phiên bản event không được hỗ trợ hoặc cấu hình sai, gửi lại cùng một record thường chỉ tạo thêm tải và làm chậm các record phía sau.

**Not-retryable exception** là exception được phân loại để error handler không thử gọi listener lại theo retry policy thông thường. Khi gặp exception này, Spring Kafka chuyển thẳng tới bước recovery. Recovery có thể gửi record sang Dead Letter Topic (DLT), ghi vào vùng cách ly hoặc thực hiện một hành động thay thế do ứng dụng định nghĩa.

Không retry không có nghĩa là tự động xóa record. Error handler quyết định exception có được thử lại hay không; recoverer quyết định phải làm gì với record khi không retry hoặc khi retry đã hết. Hai trách nhiệm này cần được cấu hình cùng nhau.

## 1. Phân biệt lỗi tạm thời và lỗi không thể khắc phục bằng retry

Quyết định retry phải dựa trên nguyên nhân và khả năng phục hồi, không chỉ dựa vào tên exception. Cùng một loại exception tổng quát có thể đại diện cho nhiều nguyên nhân khác nhau. Ví dụ `RuntimeException` không cho biết lỗi có tạm thời hay không; cần xem exception cụ thể và cause bên trong.

| Nhóm lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, sai định dạng, giá trị nằm ngoài miền hợp lệ | Không retry; đưa vào DLT hoặc luồng xử lý từ chối nghiệp vụ |
| Event version không hỗ trợ | Consumer không biết schema/version được producer phát hành | Không retry cho tới khi code hoặc schema được cập nhật |
| Lỗi chuyển đổi/deserialization | Payload không thể chuyển thành kiểu dữ liệu mà listener yêu cầu | Thường không retry cùng payload; lưu record gốc và metadata để điều tra |
| Lỗi lập trình xác định | Mapping sai, cast không hợp lệ, gọi method không tồn tại | Không retry mù quáng; sửa code hoặc rollback release |
| Lỗi dependency tạm thời | Timeout database, connection reset, dịch vụ downstream quá tải ngắn hạn | Retry hữu hạn với backoff và giới hạn tải |
| Lỗi tài nguyên tạm thời | Lock contention, pool connection tạm hết, throttling có thời hạn | Retry có kiểm soát nếu dependency dự kiến phục hồi |
| Lỗi cấu hình/quyền truy cập | Sai credential, thiếu ACL, topic không tồn tại do triển khai thiếu | Thường không retry liên tục; cảnh báo và sửa cấu hình hoặc quyền |
| Quyết định nghiệp vụ từ chối | Đơn hàng bị từ chối theo quy tắc nghiệp vụ | Xử lý như kết quả nghiệp vụ có chủ đích; không dùng retry để thay đổi quyết định |

Ví dụ: một request ghi database timeout có thể thành công khi thử lại sau vài giây. Nhưng một event có `currency="XYZ_UNKNOWN"` sẽ tiếp tục thất bại dù retry 100 lần nếu code không hỗ trợ loại tiền đó. Retry trường hợp thứ hai chỉ làm tăng consumer lag và log noise.

Không nên phân loại tất cả lỗi `4xx` hoặc tất cả lỗi `5xx` theo một quy tắc chung nếu listener gọi HTTP service. Một `429 Too Many Requests` có thể phục hồi sau thời gian chờ; một `400 Bad Request` do payload sai thường không thể khắc phục bằng retry. Một `503 Service Unavailable` có thể tạm thời, nhưng cần backoff và giới hạn tổng thời gian. Hãy chuyển lỗi từ dependency thành exception cụ thể ở tầng adapter để error handler có thể phân loại chính xác.

## 2. Exception classification trong Spring Kafka

Spring Kafka dùng exception classifier trong error handling để quyết định exception có retryable hay không. Với `DefaultErrorHandler`, ứng dụng có thể thêm các exception không retry bằng `addNotRetryableExceptions(...)`, hoặc khai báo các exception cần retry bằng `addRetryableExceptions(...)`.

Từ Spring Kafka 2.8, `DefaultErrorHandler` là common error handler được dùng thay cho các error handler cũ như `SeekToCurrentErrorHandler` trong các luồng record listener thông thường. Các phiên bản cũ có API và hành vi khác; cần đối chiếu đúng phiên bản Spring Kafka trong dự án trước khi áp dụng cấu hình.

`DefaultErrorHandler` có sẵn một nhóm exception được xem là fatal (không retry) theo mặc định ở các phiên bản hiện đại, thường gồm:

- `DeserializationException`
- `MessageConversionException`
- `ConversionException`
- `MethodArgumentResolutionException`
- `NoSuchMethodException`
- `ClassCastException`

Các exception này thường chỉ ra consumer không thể chuyển hoặc ánh xạ record vào listener method theo cấu hình hiện tại. Retry cùng một record thường không thay đổi kết quả. Ứng dụng vẫn cần recoverer phù hợp để giữ lại record và thông tin lỗi.

Danh sách mặc định có thể thay đổi theo phiên bản. Không nên dựa vào trí nhớ hoặc một ví dụ trên mạng để suy ra toàn bộ classification đang chạy; hãy kiểm tra tài liệu của phiên bản được quản lý bởi dependency Spring Boot của dự án.

### 2.1. Thêm exception không retry

Ví dụ, hệ thống xử lý đơn hàng có hai lỗi xác định: dữ liệu đơn hàng không hợp lệ và event version không được hỗ trợ. Các lỗi này được gửi trực tiếp tới recoverer thay vì retry:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);
    recoverer.setFailIfSendResultIsError(true);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedEventVersionException.class);

    return handler;
}
```

Trong ví dụ, `FixedBackOff(1_000L, 3L)` cho phép tối đa ba lần retry sau lần delivery đầu tiên đối với exception thuộc nhóm retryable. `InvalidOrderException` và `UnsupportedEventVersionException` được recover ngay khi được phân loại là not-retryable. Recoverer mặc định của ví dụ gửi record sang topic DLT theo quy ước của `DeadLetterPublishingRecoverer`; cần bảo đảm DLT có đủ partition, serializer tương thích và quyền ghi.

`setFailIfSendResultIsError(true)` yêu cầu recoverer phản ánh lỗi khi gửi DLT thất bại ở các phiên bản Spring Kafka hỗ trợ API này. Nếu không phát hiện được publish failure, ứng dụng có nguy cơ coi recovery là thành công trong khi record chưa được lưu vào DLT. Cần kiểm tra timeout, kết quả gửi và hành vi của phiên bản đang sử dụng.

### 2.2. Khai báo exception có thể retry

Có thể bổ sung exception retryable khi ứng dụng cần một classification rõ ràng cho lỗi tạm thời:

```java
handler.addRetryableExceptions(
        InventoryServiceUnavailableException.class,
        TransientDatabaseException.class);
```

Các exception được đánh dấu retryable sẽ dùng backoff đã cấu hình. Chỉ thêm exception khi có lý do tin rằng thử lại có thể thành công. Không đánh dấu một exception tổng quát như `Exception` hoặc `RuntimeException` là retryable vì việc đó có thể biến lỗi lập trình và dữ liệu thành retry kéo dài.

Nếu cùng một class hoặc class cha/con xuất hiện trong cả danh sách retryable và not-retryable, kết quả phụ thuộc cách classifier lưu và tra cứu classification. Tránh khai báo chồng chéo. Mỗi exception nên có một chính sách rõ ràng, có thể kiểm thử được.

## 3. Exception được bọc trong exception khác

Trong listener container, exception gốc có thể được bọc bởi exception của Spring Kafka hoặc framework khác. Ví dụ listener ném `InvalidOrderException`, nhưng tầng gọi phía trên bọc nó trong `ListenerExecutionFailedException` hoặc một exception ứng dụng chung.

```text
ListenerExecutionFailedException
        |
        +-- cause: InvalidOrderException
```

Khi classifier chỉ nhìn exception ngoài cùng, ứng dụng có thể vô tình retry lỗi vốn không retryable. Spring Kafka có hỗ trợ phân loại theo cause chain; hành vi và cấu hình chi tiết phụ thuộc phiên bản. Hãy giữ cause gốc khi wrap exception, không bỏ mất thông tin nguyên nhân, và xác minh classifier có traverse cause chain theo cách mong muốn.

Ví dụ không nên làm:

```java
try {
    orderService.validate(event);
}
catch (InvalidOrderException ex) {
    throw new RuntimeException("Cannot process event");
}
```

Đoạn code trên làm mất cause gốc. Nên giữ exception làm cause:

```java
try {
    orderService.validate(event);
}
catch (InvalidOrderException ex) {
    throw new OrderProcessingException("Cannot process event", ex);
}
```

Hoặc để exception miền nghiệp vụ truyền trực tiếp tới error handler nếu không cần thêm ngữ cảnh. Nếu ứng dụng dùng wrapper, hãy cấu hình và kiểm thử cause traversal trên đúng phiên bản Spring Kafka. Không giả định mọi wrapper đều được phân loại theo cause nếu chưa xác nhận.

## 4. Not-retryable không có nghĩa là bỏ qua record

Khi `DefaultErrorHandler` nhận exception không retryable, handler bỏ qua các lần retry và gọi recoverer. Recoverer quyết định record được xử lý ra sao. Nếu dùng `DeadLetterPublishingRecoverer`, record được gửi sang DLT; nếu dùng recoverer tùy chỉnh, ứng dụng có thể lưu record và metadata vào một kho lỗi khác.

```text
Listener
   |
   v
Exception
   |
   v
Exception classifier
   |
   +---- retryable --------> BackOff --> gọi listener lại
   |
   +---- not-retryable ----> Recoverer ngay
                                  |
                                  +--> DLT / quarantine / action
```

Nếu không cấu hình recoverer phù hợp, hành vi mặc định của error handler có thể chỉ ghi log khi record được xem là đã exhausted/recovered. Log không phải nơi lưu trữ bền vững để replay. Với dữ liệu nghiệp vụ quan trọng, hãy cấu hình DLT hoặc kho cách ly có thể truy xuất và đặt cảnh báo khi record được chuyển vào đó.

Không dùng not-retryable như cách âm thầm loại bỏ mọi record gây lỗi. Trước khi bỏ qua một record, cần có quy tắc nghiệp vụ rõ ràng, dấu vết kiểm toán và khả năng đối soát nếu dữ liệu đó có ảnh hưởng tới trạng thái downstream.

## 5. Dùng DLT cho exception không retryable

DLT giúp tách record không thể xử lý khỏi luồng chính để consumer tiếp tục tiến lên. Một cấu hình minh họa:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    recoverer.setFailIfSendResultIsError(true);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedEventVersionException.class);

    return handler;
}
```

Resolver gửi record tới topic có hậu tố `.DLT` và giữ nguyên partition index. Vì vậy, topic DLT cần có đủ partition tương ứng với topic nguồn. Nếu DLT có ít partition hơn, hãy dùng resolver ánh xạ tới partition hợp lệ hoặc tạo topic đích với số partition phù hợp.

Record trong DLT nên giữ metadata nguồn như original topic, partition, offset, timestamp, exception và event ID. Header cụ thể do Spring Kafka thêm phụ thuộc phiên bản. DLT cũng cần replication, retention, ACL, monitoring và quy trình replay. Một record đã được gửi DLT vẫn cần người hoặc quy trình tự động điều tra và quyết định cách khắc phục.

Nếu listener nhận dữ liệu đã deserialize, DLT publisher cần serializer tương thích với kiểu key/value đó. Nếu lỗi xảy ra trước khi value được deserialize, payload có thể là `byte[]`; cấu hình template phải xử lý được cả dữ liệu gốc dạng byte. Với nhiều kiểu value, cân nhắc serializer phân loại theo kiểu dữ liệu hoặc template riêng.

## 6. Deserialization exception và ErrorHandlingDeserializer

Một lỗi deserialization có thể xảy ra trước khi listener method được gọi. Nếu consumer dùng deserializer trực tiếp và deserialization thất bại trong `poll()`, listener không có cơ hội bắt exception như một lỗi nghiệp vụ thông thường.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để bắt lỗi từ delegate deserializer và chuyển thông tin lỗi vào header của record, cho phép container error handling xử lý record. Ví dụ cấu hình:

```properties
spring.kafka.consumer.key-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer

spring.kafka.consumer.properties[spring.deserializer.key.delegate.class]=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.properties[spring.deserializer.value.delegate.class]=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.value.default.type]=com.example.events.OrderCreated
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events
```

Đây là ví dụ cho key chuỗi và value JSON. Các thuộc tính type mapping, trusted packages và delegate deserializer cần khớp schema thực tế của producer. Khi deserialization lỗi, `DefaultErrorHandler` có thể nhận diện `DeserializationException` qua header và xử lý theo classification mặc định hoặc cấu hình riêng.

Không retry vô hạn một payload mà deserializer không thể đọc. Khi producer phát hành schema mới, có thể cần nâng cấp consumer hoặc dùng schema compatibility; trong thời gian đó, DLT giúp giữ payload gốc để replay sau khi ứng dụng được cập nhật.

## 7. Lỗi nghiệp vụ: exception hay kết quả từ chối?

Không phải mọi trường hợp nghiệp vụ không được chấp nhận đều nên được biểu diễn thành exception kỹ thuật. Ví dụ đơn hàng vượt hạn mức tín dụng có thể là một kết quả hợp lệ của quy trình: hệ thống từ chối đơn hàng và phát ra `OrderRejected`. Nếu ném `InvalidOrderException` rồi gửi DLT, hệ thống có thể làm mất ý nghĩa nghiệp vụ và tạo ra backlog điều tra không cần thiết.

Nên phân biệt:

- **Business rejection:** một kết quả nghiệp vụ được dự kiến và cần được ghi nhận như trạng thái bình thường. Xử lý trực tiếp, cập nhật trạng thái và phát event kết quả nếu cần.
- **Invalid message:** record vi phạm hợp đồng dữ liệu hoặc không thể ánh xạ thành command hợp lệ. Không retry cùng payload; cách ly hoặc DLT.
- **Transient infrastructure failure:** không thể hoàn tất nghiệp vụ vì dependency tạm thời lỗi. Retry hữu hạn với backoff.
- **Unexpected programming failure:** bug hoặc invariant bị phá vỡ. Cần cảnh báo, điều tra và thường nên tránh retry mù quáng.

Nếu một business rule có thể thay đổi theo thời gian, quyết định retry cần được cân nhắc. Ví dụ, tài khoản hiện không đủ số dư có thể là từ chối nghiệp vụ cuối cùng; hoặc có thể là trạng thái chờ nếu hệ thống hỗ trợ thử lại sau khi số dư được cập nhật. Hãy mô hình hóa trạng thái rõ ràng thay vì dùng retry vô hạn như một hàng đợi chờ điều kiện nghiệp vụ.

## 8. Not-retryable với non-blocking retry topics

Spring Kafka có cơ chế non-blocking retries qua `@RetryableTopic`. Cơ chế này chuyển record sang retry topic thay vì chờ retry ngay trên partition nguồn. Có thể chỉ định exception không retry bằng thuộc tính `exclude`:

```java
@RetryableTopic(
        attempts = "4",
        exclude = {
                InvalidOrderException.class,
                UnsupportedEventVersionException.class
        },
        dltTopicSuffix = ".DLT")
@KafkaListener(topics = "orders", groupId = "billing-service")
public void consume(OrderCreated event) {
    billingService.process(event);
}
```

Trong cấu hình này, các exception được liệt kê trong `exclude` không đi qua các retry topic thông thường và được xử lý theo nhánh terminal/DLT của retry-topic mechanism. Cần kiểm tra chính sách DLT, số attempts, backoff và version API trong ứng dụng. Với annotation này, số lần thử và tên retry topic được quản lý bởi cơ chế non-blocking retry, khác với `FixedBackOff` của `DefaultErrorHandler`.

Non-blocking retry giúp partition nguồn tiếp tục xử lý các record khác trong khi record lỗi chờ retry. Đổi lại, thứ tự tương đối giữa các record có thể thay đổi: record sau có thể được xử lý trước record đang nằm ở retry topic. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo key, cần đánh giá kỹ trước khi dùng retry topics.

Không nên cấu hình đồng thời nhiều cơ chế retry cho cùng một listener mà không hiểu thứ tự hoạt động của chúng. `DefaultErrorHandler` xử lý exception tại listener container; `@RetryableTopic` thiết lập luồng retry topic riêng. Hãy chọn mô hình rõ ràng và tránh tạo nhiều tầng retry khiến tổng số lần thử và thời gian xử lý khó dự đoán.

## 9. Batch listener và not-retryable exception

Với batch listener, một lần poll có thể trả về nhiều record trong một danh sách. Khi một record lỗi, error handler cần biết record nào thất bại để có thể commit phần đã xử lý và recover record lỗi. Spring Kafka hỗ trợ `BatchListenerFailedException` để listener chỉ rõ index hoặc record gây lỗi.

Ví dụ:

```java
@KafkaListener(topics = "orders", groupId = "batch-billing")
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, OrderCreated> record = records.get(i);
        try {
            billingService.process(record.value());
        }
        catch (InvalidOrderException ex) {
            throw new BatchListenerFailedException(
                    "Invalid order payload", ex, i);
        }
    }
}
```

`DefaultErrorHandler` có thể sử dụng vị trí record trong batch để xác định phần đã xử lý và record cần retry hoặc recover. Với exception được phân loại là not-retryable, record lỗi có thể được chuyển thẳng tới recoverer theo chính sách của handler. Các record sau vị trí lỗi có thể được giao lại tùy acknowledgment mode và batch recovery semantics.

Nếu batch listener ném exception chung mà không chỉ rõ record thất bại, handler có thể phải xử lý lại cả batch. Điều này có thể tạo duplicate cho các record đã được xử lý trước khi exception xảy ra. Vì vậy, batch listener cần ghi nhận chính xác record lỗi và làm các side effect idempotent.

## 10. BackOff và retry policy vẫn quan trọng

Not-retryable exception được đưa thẳng tới recovery, nhưng các exception còn lại vẫn cần retry policy hợp lý. Không nên dùng retry vô hạn cho lỗi hạ tầng; một dependency bị outage dài có thể làm consumer giữ partition quá lâu, tăng lag và tạo áp lực lên broker hoặc downstream.

Ví dụ retry hữu hạn:

```java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(4);
backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler handler = new DefaultErrorHandler(recoverer, backOff);
handler.addNotRetryableExceptions(InvalidOrderException.class);
```

Backoff tăng dần giúp tránh gọi dependency liên tục trong thời gian outage. Trong production, cần chọn số lần retry và thời gian chờ tối đa theo latency nghiệp vụ, timeout của dependency, `max.poll.interval.ms` và mức lag có thể chấp nhận. Nếu thời gian retry dài hơn giới hạn poll hoặc listener container không thể poll đúng hạn, cần đánh giá pause/resume, container behavior hoặc non-blocking retry topics.

## 11. Kiểm thử classification và recovery

Kiểm thử nên xác nhận cả quyết định retry lẫn hành động cuối cùng đối với record:

1. Gửi một record hợp lệ và xác nhận listener xử lý một lần.
2. Gửi record gây `InvalidOrderException`; xác nhận listener không bị gọi lại theo backoff và recoverer được gọi ngay.
3. Gửi record gây `TransientDatabaseException`; xác nhận listener được retry đúng số lần và đúng backoff.
4. Bọc exception không retry trong wrapper; xác nhận cause traversal cho kết quả như thiết kế.
5. Mô phỏng DLT publish lỗi; xác nhận recovery không bị coi là thành công và offset không tiến qua record đó.
6. Xác nhận DLT chứa payload, key, headers và metadata nguồn cần thiết.
7. Với batch listener, xác nhận index trong `BatchListenerFailedException` trỏ đúng record.
8. Với `@RetryableTopic`, xác nhận exception trong `exclude` đi thẳng tới terminal/DLT path và exception khác đi qua retry topic theo cấu hình.

Không chỉ kiểm tra số lần listener được gọi. Cần xác nhận committed offset, record trong DLT, log và metric recovery để phát hiện trường hợp record đã bị bỏ qua nhưng không được lưu ở đâu.

## 12. Quan sát và vận hành

Các chỉ số nên theo dõi gồm:

- Số exception theo class và topic.
- Số lần retry theo loại lỗi.
- Số record đi thẳng tới recoverer do not-retryable classification.
- Số lần publish DLT thành công, thất bại và timeout.
- Consumer lag và tuổi record cũ nhất chưa xử lý.
- Tốc độ tăng record DLT và số record chờ replay.
- Tỷ lệ lỗi theo phiên bản ứng dụng hoặc schema version.

Không dùng event ID, order ID hoặc offset làm metric label có cardinality cao. Lưu định danh record trong log hoặc trace có kiểm soát. Log recovery cần có topic, partition, offset, event ID, exception class, cause và destination DLT để người trực có thể tìm record.

Khi tỷ lệ not-retryable tăng đột ngột sau release, hãy kiểm tra schema compatibility, mapping, validation rule và thay đổi domain model. Khi DLT tăng do lỗi dữ liệu đầu vào, cần phối hợp với producer hoặc hệ thống upstream để ngăn dữ liệu lỗi tiếp tục được phát ra. Khi DLT tăng do lỗi lập trình, rollback hoặc sửa phiên bản consumer trước khi replay hàng loạt.

## 13. Các lỗi phân loại thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Lỗi dữ liệu bị retry nhiều lần | Chưa thêm exception vào not-retryable classification | Thêm exception cụ thể bằng `addNotRetryableExceptions` và kiểm tra cause chain |
| Lỗi tạm thời đi thẳng DLT | Exception tổng quát hoặc class cha bị phân loại not-retryable | Thu hẹp classification, phân biệt exception theo nguyên nhân |
| Exception đã exclude nhưng vẫn retry | Listener dùng error handler/factory khác hoặc đang dùng cơ chế retry khác | Xác nhận đúng factory và phân biệt `DefaultErrorHandler` với `@RetryableTopic` |
| DLT không có record nhưng offset đã tiến | Recoverer không phản ánh publish failure hoặc hành động recovery không bền vững | Bật kiểm tra send result, theo dõi recovery và xác minh offset |
| Wrapper làm sai classification | Cause gốc bị mất hoặc cause traversal không như mong đợi | Giữ cause khi wrap và cấu hình/test classifier theo version |
| Record hợp lệ bị đưa vào DLT | Validation hoặc exception mapping quá rộng | Thu hẹp điều kiện exception, kiểm tra input và business rule |
| DLT tăng sau thay đổi schema | Consumer chưa hỗ trợ event version mới hoặc deserializer không tương thích | Kiểm tra schema compatibility, cập nhật consumer và replay có kiểm soát |

## 14. Nguyên tắc thiết kế production

Khi cấu hình not-retryable exception trong Spring Kafka, cần tuân thủ các nguyên tắc:

1. Phân loại theo nguyên nhân thực tế và khả năng phục hồi, không chỉ theo tên exception tổng quát.
2. Dùng `addNotRetryableExceptions` cho lỗi dữ liệu hoặc lỗi xác định không thể khắc phục bằng retry.
3. Giữ danh sách retryable và not-retryable rõ ràng, tránh classification chồng chéo.
4. Giữ cause gốc khi wrap exception và kiểm thử cause traversal.
5. Cấu hình recoverer bền vững; với dữ liệu quan trọng, ưu tiên DLT hoặc quarantine có thể điều tra/replay.
6. Kiểm tra publish result của DLT và không coi recovery là thành công nếu record chưa được lưu.
7. Tách business rejection khỏi lỗi kỹ thuật và lỗi dữ liệu không hợp lệ.
8. Chọn rõ blocking retry (`DefaultErrorHandler`) hoặc non-blocking retry (`@RetryableTopic`) theo yêu cầu thứ tự và độ trễ.
9. Với batch listener, xác định chính xác record lỗi và thiết kế side effect idempotent.
10. Theo dõi classification, retry, DLT, consumer lag và thay đổi theo phiên bản ứng dụng.

Not-retryable exception giúp hệ thống ngừng thử lại những lỗi mà việc gửi lại cùng một record không thể khắc phục. Khi phân loại chính xác và kết hợp với recoverer có khả năng lưu giữ record, consumer có thể tiếp tục xử lý luồng chính trong khi đội vận hành vẫn có đủ dữ liệu để điều tra, sửa nguyên nhân và replay có kiểm soát.
