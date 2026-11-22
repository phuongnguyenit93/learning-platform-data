# Lỗi tạm thời và lỗi không thể phục hồi

Khi consumer xử lý một record Kafka, lỗi có thể đến từ một sự cố ngắn hạn hoặc từ dữ liệu/nghiệp vụ vốn không thể thành công nếu chạy lại nguyên trạng. Hai nhóm lỗi này cần cách xử lý khác nhau. Lỗi tạm thời có thể được retry với số lần và thời gian chờ giới hạn; lỗi không thể phục hồi nên được dừng retry sớm, ghi nhận nguyên nhân và chuyển sang dead-letter topic (DLT), quarantine hoặc luồng xử lý thủ công.

Nếu retry mọi lỗi, một record sai dữ liệu có thể chiếm consumer vô thời hạn, làm partition bị nghẽn và tăng lag. Nếu không retry lỗi tạm thời, một timeout ngắn ở database hoặc dịch vụ phụ thuộc cũng có thể khiến record bị đưa vào DLT dù chỉ cần chờ một chút là xử lý được. Vì vậy, bước đầu tiên của thiết kế error handling là phân loại lỗi dựa trên nguyên nhân và khả năng khắc phục.

## 1. Phân biệt lỗi tạm thời và lỗi không thể phục hồi

**Lỗi tạm thời (transient/retryable)** là lỗi có khả năng tự hết khi điều kiện bên ngoài thay đổi: dịch vụ phụ thuộc đang quá tải, kết nối bị gián đoạn ngắn, lock database đang được giữ hoặc hệ thống giới hạn tốc độ trong một khoảng thời gian. Gửi lại cùng thao tác sau một khoảng chờ hợp lý có thể thành công.

**Lỗi không thể phục hồi (permanent/non-retryable)** là lỗi mà việc gửi lại cùng record, với cùng dữ liệu và cùng điều kiện, không làm kết quả tốt hơn. Ví dụ payload thiếu trường bắt buộc, mã tiền tệ không được hỗ trợ, schema không hợp lệ hoặc quyền truy cập bị cấu hình sai. Những lỗi này cần sửa dữ liệu, sửa cấu hình hoặc xử lý thủ công.

| Tiêu chí | Lỗi tạm thời | Lỗi không thể phục hồi |
|---|---|---|
| Khả năng thành công khi thử lại | Có thể tăng sau khi chờ hoặc điều kiện phụ thuộc hồi phục | Thường không đổi nếu record và cấu hình giữ nguyên |
| Ví dụ | Timeout DB, HTTP 503, connection reset, rate limit có thời hạn | Validation thất bại, schema sai, currency không hỗ trợ, payload không parse được |
| Hành động | Retry có backoff và giới hạn | Không retry hoặc chỉ retry theo chính sách sửa dữ liệu; recover/DLT |
| Tác động khi retry lâu | Tăng latency và lag, nhưng có thể phục hồi | Lãng phí tài nguyên và có thể chặn partition |
| Cách khắc phục | Chờ, giảm tải, phục hồi dependency | Sửa dữ liệu, contract, quyền hoặc cấu hình; sau đó replay có kiểm soát |

Phân loại phải dựa trên semantics của lỗi trong hệ thống cụ thể. Một HTTP 404 có thể là lỗi vĩnh viễn nếu tài nguyên không tồn tại, nhưng cũng có thể là tạm thời nếu request được gửi trước khi dữ liệu được đồng bộ. Một `DataAccessException` có thể bao gồm lỗi kết nối tạm thời lẫn lỗi SQL không thể khắc phục. Không nên phân loại chỉ dựa trên một tên exception tổng quát.

## 2. Những nguyên nhân thường có thể retry

Các trường hợp sau thường có thể retry nếu nghiệp vụ cho phép và thao tác có tính idempotent:

- Timeout khi gọi database, HTTP service hoặc hệ thống lưu trữ.
- Kết nối bị đóng/reset trong lúc dependency đang phục hồi.
- Database deadlock hoặc lock contention có thể được giải phóng sau một khoảng chờ.
- HTTP 429 (Too Many Requests) hoặc 503 (Service Unavailable), nếu có chính sách retry và tôn trọng `Retry-After` khi cần.
- Lỗi tạm thời khi truy cập object storage, cache hoặc dịch vụ nội bộ.
- Lỗi leader/network ngắn hạn khi gọi một dịch vụ Kafka hoặc dependency khác.

Ví dụ listener gọi dịch vụ kho hàng:

```java
@KafkaListener(topics = "orders.created", groupId = "order-worker")
public void onOrder(OrderCreated event) {
    try {
        inventoryClient.reserve(event.orderId(), event.items());
    } catch (InventoryUnavailableException ex) {
        throw new TransientInventoryException(
                "Inventory service tạm thời không sẵn sàng", ex);
    }
}
```

Ứng dụng chuyển lỗi phụ thuộc thành exception nghiệp vụ có tên rõ ràng. Error handler có thể phân loại `TransientInventoryException` là retryable. Việc bọc exception giúp listener diễn đạt ý nghĩa vận hành thay vì buộc error handler hiểu mọi exception HTTP/DB ở các tầng thấp.

Không retry một lỗi chỉ vì nó là `RuntimeException`. Hãy xác định dependency nào có thể phục hồi, thời gian phục hồi thường gặp và hậu quả khi chạy lại thao tác.

## 3. Những nguyên nhân thường không nên retry

Các lỗi sau thường cần dừng retry sớm:

- Dữ liệu thiếu trường bắt buộc hoặc vi phạm quy tắc validation.
- JSON/XML/Avro không đúng format hoặc không tương thích schema.
- Giá trị enum, loại tiền tệ, trạng thái hoặc mã nghiệp vụ không được hỗ trợ.
- Business rule từ chối thao tác một cách dứt khoát, ví dụ đơn hàng đã bị hủy và không thể thanh toán.
- Người dùng/ứng dụng không có quyền thực hiện thao tác do cấu hình hoặc credential sai.
- Topic, endpoint, schema mapping hoặc cấu hình ứng dụng sai và không thể tự sửa bằng cách chờ.
- Lỗi lập trình như truy cập null không hợp lệ hoặc cast sai kiểu.

Ví dụ validation:

```java
@KafkaListener(topics = "orders.created", groupId = "order-worker")
public void onOrder(OrderCreated event) {
    if (event.orderId() == null || event.items().isEmpty()) {
        throw new InvalidOrderException("Order phải có id và ít nhất một item");
    }

    orderService.create(event);
}
```

Nếu dữ liệu sai, retry cùng payload sẽ tiếp tục thất bại. Nên chuyển record sang DLT cùng metadata lỗi để đội phụ trách kiểm tra và sửa dữ liệu. Sau khi sửa nguyên nhân, có thể replay record từ DLT bằng quy trình riêng.

Một số lỗi cấu hình như authentication hoặc authorization có thể được khắc phục sau khi cập nhật secret/ACL. Tuy nhiên, consumer không nên retry nhanh liên tục trong lúc cấu hình chưa được sửa; cần fail fast, backoff dài hoặc dừng listener và phát cảnh báo theo chính sách vận hành.

## 4. Phân loại theo khả năng khắc phục, không chỉ theo tên exception

Tên exception là tín hiệu kỹ thuật, còn quyết định retry cần xét cả bối cảnh:

| Tình huống | Có thể retry? | Lý do |
|---|---|---|
| `SocketTimeoutException` khi gọi dịch vụ nội bộ | Thường có | Dịch vụ có thể phản hồi ở lần gọi sau |
| `SQLTransientConnectionException` | Thường có | Kết nối có thể được khôi phục |
| Deadlock database | Thường có | Transaction khác có thể nhả lock |
| HTTP 429 | Có, với backoff | Cần tôn trọng giới hạn tốc độ và `Retry-After` |
| HTTP 503 | Thường có | Dịch vụ đang tạm ngừng hoặc quá tải |
| HTTP 400 do payload sai | Thường không | Gửi lại payload không sửa được request |
| `MethodArgumentNotValidException` | Thường không | Dữ liệu không thỏa contract |
| `ClassCastException` | Không | Thường là lỗi kiểu dữ liệu/lập trình |
| `AuthenticationException` | Thường không retry nhanh | Credential hoặc cơ chế xác thực cần được sửa |
| `IllegalStateException` | Phụ thuộc nguyên nhân | Có thể là lỗi trạng thái tạm thời hoặc bug/configuration |

Không nên áp dụng bảng này máy móc. Ví dụ HTTP 400 đôi khi được API dùng cho một trạng thái có thể retry sau khi bổ sung dữ liệu; HTTP 404 có thể chỉ là eventual consistency. Hãy tạo exception nghiệp vụ cụ thể hoặc chuyển lỗi thành kết quả có mã phân loại rõ ràng.

## 5. Retry không đồng nghĩa với chạy lại an toàn

Retry làm listener thực hiện lại cùng thao tác. Nếu lần đầu đã ghi database hoặc gọi dịch vụ ngoài nhưng response bị timeout, lần retry có thể tạo side effect trùng lặp.

Ví dụ:

```text
Consumer nhận OrderCreated
        |
        v
Gọi Payment API
        |
        v
Payment đã thành công
        |
        v
Response bị timeout trên đường về
        |
        v
Listener ném TransientPaymentException
        |
        v
Retry cùng record
        |
        v
Payment có nguy cơ bị tạo lần thứ hai
```

Để retry an toàn, dùng idempotency key ổn định, thường là event ID hoặc business operation ID:

```java
paymentClient.charge(
        event.paymentId(),       // idempotency key ổn định
        event.orderId(),
        event.amount());
```

Database cũng có thể dùng unique constraint trên event ID, inbox table hoặc upsert để tránh xử lý trùng. Kafka offset commit và transaction của database không tự tạo exactly-once cho side effect bên ngoài Kafka.

## 6. Retry trong Spring Kafka hoạt động ở đâu?

Với record listener, listener container gọi phương thức `@KafkaListener`. Nếu phương thức ném exception, container chuyển lỗi tới `CommonErrorHandler`. Trong Spring Kafka hiện đại, `DefaultErrorHandler` là implementation phổ biến để phân loại exception, thực hiện backoff, seek/retry và gọi recoverer khi đã hết số lần thử.

Luồng xử lý khái quát:

```text
poll() -> listener xử lý record
              |
              v
         Có exception?
          /       \
        Không      Có
         |          |
         v          v
   xử lý xong    ErrorHandler phân loại
                    |
              +-----+------+
              |            |
          Retryable    Non-retryable
              |            |
              v            v
        BackOff/retry   Recoverer ngay
              |
         còn retry?
          /      \
        Có        Hết
        |          |
        v          v
     xử lý lại   Recoverer/DLT
```

`DefaultErrorHandler` xử lý lỗi sau khi listener được gọi. Lỗi deserialize xảy ra trước khi listener nhận được record cần có `ErrorHandlingDeserializer` để đưa exception vào cơ chế xử lý của container. Lỗi khởi động ứng dụng, lỗi kết nối broker hoặc lỗi cấu hình container cũng không phải lúc nào được giải quyết bởi error handler của listener.

## 7. Mặc định phân loại exception của DefaultErrorHandler

Trong các phiên bản Spring Kafka hiện đại (2.8 trở lên), `DefaultErrorHandler` mặc định xem một số exception là fatal/non-retryable vì retry cùng record thường không có ích. Nhóm thường gặp gồm:

- `DeserializationException`.
- `MessageConversionException`.
- `ConversionException`.
- `MethodArgumentResolutionException`.
- `NoSuchMethodException`.
- `ClassCastException`.

Các exception khác mặc định thường được xem là retryable, nhưng ứng dụng nên cấu hình rõ những lỗi nghiệp vụ không thể phục hồi. Danh sách mặc định có thể thay đổi theo phiên bản; kiểm tra tài liệu Spring Kafka đúng version trước khi dựa vào hành vi mặc định.

Một điểm cần chú ý: listener container có thể bọc exception nghiệp vụ trong exception của framework, chẳng hạn `ListenerExecutionFailedException`. Khi cấu hình classifier, cần kiểm tra exception thực tế mà handler nhận được và cách classifier xét cause chain. Nên log cả class exception và root cause để tránh phân loại nhầm một lỗi nghiệp vụ thành retryable chỉ vì wrapper bên ngoài.

## 8. Đánh dấu exception không retry bằng DefaultErrorHandler

Có thể tạo `DefaultErrorHandler` với backoff và thêm các exception không retry. Ví dụ:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    ExponentialBackOffWithMaxRetries backOff =
            new ExponentialBackOffWithMaxRetries(4);
    backOff.setInitialInterval(1_000L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(10_000L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedCurrencyException.class,
            InvalidCustomerStateException.class);

    handler.addRetryableExceptions(
            TransientInventoryException.class,
            TransientPaymentException.class);

    return handler;
}
```

Trong ví dụ, các exception validation được chuyển thẳng tới recoverer. Lỗi inventory/payment tạm thời được retry theo exponential backoff. Các giá trị 1 giây, multiplier 2 và tối đa 10 giây chỉ là ví dụ; cần chọn theo timeout dependency, SLA và thời gian xử lý cho phép.

`ExponentialBackOffWithMaxRetries(4)` giới hạn số lần retry theo API của Spring Framework/Spring Kafka tương ứng; số lần gọi listener tổng cộng gồm lần đầu và các lần retry. Hãy xác minh cách đếm attempt của phiên bản đang dùng và ghi rõ trong cấu hình vận hành để tránh hiểu nhầm giữa “4 lần retry” và “4 lần thử tổng cộng”.

Gắn handler vào container factory:

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
```

Nếu Spring Boot auto-configures factory mặc định, có thể tùy biến factory hiện có bằng configurer hoặc khai báo bean factory riêng. Đảm bảo listener dùng đúng `containerFactory`; nếu không, error handler đã cấu hình có thể không được áp dụng cho endpoint đó.

## 9. Phân loại bằng setClassifications

Khi cần kiểm soát cả retryable và non-retryable trong một bảng, có thể dùng `setClassifications(...)`:

```java
Map<Class<? extends Throwable>, Boolean> classifications = new HashMap<>();
classifications.put(InvalidOrderException.class, false);
classifications.put(UnsupportedCurrencyException.class, false);
classifications.put(TransientInventoryException.class, true);
classifications.put(TransientPaymentException.class, true);

handler.setClassifications(classifications, true);
```

Giá trị `true` nghĩa là retryable; `false` nghĩa là không retry. Tham số thứ hai là giá trị mặc định cho exception không được liệt kê. Trong ví dụ, exception chưa khai báo vẫn retryable. Nếu chọn mặc định `false`, phải khai báo đầy đủ các exception tạm thời cần retry, nếu không chúng sẽ được recover ngay.

`addRetryableExceptions(...)` và `addNotRetryableExceptions(...)` thường dễ đọc hơn khi chỉ cần bổ sung vài loại exception vào chính sách mặc định. `setClassifications(...)` phù hợp khi muốn sở hữu toàn bộ bảng phân loại. Không nên cấu hình đồng thời nhiều cách mà không kiểm tra thứ tự ghi đè.

Lưu ý: `setClassifications(...)` thiết lập classifier theo map được cung cấp. Nếu đặt mặc định là `true`, những exception framework vốn mặc định fatal nhưng không có trong map cũng có thể bị xem là retryable. Khi tự định nghĩa toàn bộ bảng, hãy thêm các exception không retry mặc định như `DeserializationException`, `MessageConversionException`, `ConversionException`, `MethodArgumentResolutionException`, `NoSuchMethodException` và `ClassCastException` với giá trị `false`; hoặc dùng `addNotRetryableExceptions(...)` để giữ chính sách mặc định và chỉ bổ sung các loại nghiệp vụ.

## 10. Chọn backoff và giới hạn retry

Retry cần có giới hạn. Ba kiểu thường gặp:

| Backoff | Hành vi | Khi phù hợp |
|---|---|---|
| Fixed | Chờ một khoảng thời gian cố định giữa các lần thử | Lỗi ngắn hạn, latency ổn định |
| Exponential | Tăng dần thời gian chờ sau mỗi lần thất bại | Dependency đang phục hồi hoặc quá tải |
| Exponential có giới hạn | Tăng dần nhưng không vượt max interval | Muốn giảm áp lực mà vẫn giữ thời gian chờ dự đoán được |

Không retry liên tục không có delay khi dependency đang lỗi. Điều đó có thể tạo retry storm, làm dịch vụ phụ thuộc càng quá tải. Với HTTP 429, có thể cần tôn trọng `Retry-After`; với hệ thống phân tán nhiều consumer, jitter giúp tránh tất cả consumer retry cùng một thời điểm.

Tổng thời gian chờ phải phù hợp với `max.poll.interval.ms`, thời gian xử lý record và SLA. Blocking retry giữ luồng consumer trong quá trình backoff; partition có thể không tiến triển trong thời gian đó. Nếu cần trì hoãn lâu, cân nhắc retry topic/non-blocking retry thay vì giữ consumer thread chờ nhiều phút.

## 11. Non-retryable không có nghĩa là bỏ record âm thầm

Khi xác định lỗi không thể phục hồi, hệ thống vẫn cần một hành động kết thúc rõ ràng. Các lựa chọn phổ biến:

- Gửi record sang dead-letter topic để lưu payload, key, headers và metadata lỗi.
- Ghi record vào quarantine store nếu cần phê duyệt hoặc sửa dữ liệu trước khi replay.
- Phát cảnh báo và dừng container nếu lỗi cho thấy cấu hình/hệ thống bị hỏng diện rộng.
- Với lỗi nghiệp vụ được chấp nhận như một kết quả bình thường, trả về trạng thái từ chối có chủ đích và commit theo contract thay vì ném exception.

Không cấu hình non-retryable rồi mặc định rằng record sẽ tự động vào DLT. `DefaultErrorHandler` cần một recoverer phù hợp; nếu dùng recoverer mặc định, hành vi có thể chỉ log và đánh dấu record đã recover theo cấu hình. Muốn publish DLT, cấu hình `DeadLetterPublishingRecoverer` hoặc recoverer riêng.

## 12. Gửi lỗi không thể phục hồi sang Dead Letter Topic

`DeadLetterPublishingRecoverer` có thể publish record lỗi tới topic DLT. Mặc định, destination thường được tạo bằng cách thêm `.DLT` vào tên topic gốc và dùng partition tương ứng; cần bảo đảm DLT có đủ partition nếu giữ nguyên partition number.

Ví dụ cấu hình destination tùy chỉnh:

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()));
```

Nếu DLT không có partition tương ứng, publish có thể thất bại. Có thể chọn partition khác hoặc để partition resolver trả `null` để producer tự chọn partition theo key/partitioner. Hãy tạo topic DLT và kiểm tra replication factor, retention, ACL, quota và serializer trước khi bật production.

DLT record thường giữ metadata nguồn như original topic, partition, offset, timestamp, exception class và exception message qua các header do Spring Kafka thêm. Không nên chỉ lưu stack trace vào log rồi bỏ payload; DLT phải đủ thông tin để điều tra và replay an toàn.

## 13. Lỗi deserialize và lỗi nghiệp vụ cần đường xử lý khác nhau

Lỗi deserialize xảy ra khi Kafka client chuyển byte thành key/value. Listener chưa được gọi nên không thể bắt lỗi bằng `try/catch` trong `@KafkaListener`. Spring Kafka cung cấp `ErrorHandlingDeserializer` để giữ exception và dữ liệu gốc trong header, giúp error handler/recoverer xử lý.

Ví dụ bọc JSON deserializer:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.OrderCreated
        "[spring.json.trusted.packages]": com.example.orders
```

JSON sai format thường là lỗi không retry được nếu payload không thay đổi. Lỗi listener gọi DB timeout lại có thể retry. Hãy phân biệt:

| Giai đoạn | Ví dụ | Chính sách gợi ý |
|---|---|---|
| Deserialization | Byte không hợp lệ, JSON hỏng, schema không tương thích | Non-retryable; DLT/quarantine |
| Message conversion | Không chuyển payload sang kiểu tham số listener | Thường non-retryable; DLT và kiểm tra contract |
| Business validation | Thiếu order ID, amount âm | Non-retryable; DLT hoặc business rejection |
| Dependency call | Database timeout, HTTP 503 | Retry có giới hạn, sau đó DLT |
| Programming error | `ClassCastException`, bug logic | Thường không retry mù; alert và DLT hoặc dừng tùy mức độ |

Nếu lỗi deserialize xảy ra trên key, cần xử lý key exception header tương ứng. Khi publish DLT, producer có thể cần hỗ trợ cả payload đã deserialize và raw `byte[]` được lưu trong exception header. Cấu hình serializer của DLT publisher phải tương thích với cả hai loại.

## 14. Blocking retry và non-blocking retry

Spring Kafka hỗ trợ hai hướng retry chính:

**Blocking retry** dùng `DefaultErrorHandler` để chờ backoff rồi thử lại record trên luồng consumer. Cách này giữ retry gần với partition gốc và thường phù hợp khi số lần retry ít, thời gian chờ ngắn. Trong thời gian retry, partition có thể bị chặn, làm các record phía sau phải đợi.

**Non-blocking retry** dùng retry topics, thường cấu hình qua `@RetryableTopic` hoặc `RetryTopicConfiguration`. Record lỗi được chuyển sang retry topic có thời gian chờ, sau đó một listener khác tiêu thụ và thử lại. Cách này giải phóng consumer của topic gốc sớm hơn, phù hợp với delay dài hoặc cần tránh block partition.

Non-blocking retry làm thay đổi thứ tự xử lý: record mới hơn có thể được xử lý trước record cũ đang nằm trong retry topic. Nếu nghiệp vụ yêu cầu ordering nghiêm ngặt theo key, cần cân nhắc kỹ hoặc giữ blocking retry trong giới hạn phù hợp. Cũng cần kiểm tra phiên bản Spring Kafka và loại listener được hỗ trợ trước khi chọn retry topics.

Không cấu hình hai cơ chế retry chồng lấn một cách vô tình. Nếu `DefaultErrorHandler` retry nhiều lần rồi `@RetryableTopic` tiếp tục retry nhiều lần, tổng số lần thử và thời gian xử lý có thể lớn hơn dự kiến.

## 15. Không retry lỗi hệ thống diện rộng theo kiểu vô hạn

Một lỗi có vẻ tạm thời ở một record có thể là dấu hiệu của sự cố hệ thống diện rộng: database mất kết nối, credential hết hạn hoặc downstream đang quá tải. Nếu tất cả consumer retry liên tục, hệ thống có thể tạo thêm tải và làm sự cố kéo dài.

Nên kết hợp:

- Số lần retry tối đa và backoff có giới hạn.
- Circuit breaker hoặc rate limiter ở client gọi dependency khi phù hợp.
- Timeout kết nối và timeout request rõ ràng.
- Giới hạn concurrency để không làm quá tải dependency.
- Alert khi tỷ lệ retry, DLT hoặc timeout tăng bất thường.
- Dừng/pause listener theo runbook khi lỗi cấu hình diện rộng cần can thiệp.

Đặc biệt, lỗi authentication/authorization thường không tự hết khi retry nhanh. Khi secret hoặc ACL được sửa, ứng dụng mới có thể hoạt động lại. Nên phát hiện lỗi này sớm và thông báo vận hành thay vì tiêu tốn toàn bộ retry budget cho cùng một nguyên nhân.

## 16. Quan sát retry và phân loại lỗi

Để biết classifier có đúng hay không, cần quan sát số lần thử và nguyên nhân ở từng bước:

- Tổng số record thất bại theo exception class và root cause.
- Số lần retry trước khi thành công.
- Số record được recover ngay vì non-retryable.
- Số record hết retry và được publish DLT.
- Backoff thực tế và thời gian record nằm trong trạng thái retry.
- Consumer lag theo topic/partition và thời gian xử lý listener.
- Tỷ lệ lỗi theo dependency, HTTP status, SQL state hoặc mã nghiệp vụ.
- Số lần publish DLT thất bại và số record đang chờ xử lý thủ công.

Có thể triển khai `RetryListener` trên `DefaultErrorHandler` để quan sát retry và recovery:

```java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(ConsumerRecord<?, ?> record,
                               Exception exception,
                               int deliveryAttempt) {
        log.warn("Retry attempt={}, topic={}, partition={}, offset={}, cause={}",
                deliveryAttempt,
                record.topic(),
                record.partition(),
                record.offset(),
                exception.getClass().getSimpleName());
    }

    @Override
    public void recovered(ConsumerRecord<?, ?> record,
                          Exception exception) {
        log.error("Record recovered to DLT or alternate path: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset());
    }
});
```

API callback có thể có thêm overload theo phiên bản Spring Kafka. Trong metric, tránh dùng event ID, order ID hoặc exception message làm label có cardinality cao; dùng các nhóm exception và topic ổn định, còn ID cụ thể đưa vào log có kiểm soát.

## 17. Kiểm thử phân loại retryable và non-retryable

Kiểm thử cần chứng minh cả hai nhánh: lỗi tạm thời được thử lại đúng số lần và lỗi không retry được đi thẳng tới recoverer/DLT.

Các tình huống tối thiểu:

| Tình huống | Kỳ vọng |
|---|---|
| Listener ném `TransientInventoryException` rồi thành công | Có retry và record cuối cùng được xử lý |
| Listener luôn ném transient exception | Retry đúng giới hạn, sau đó recover/DLT |
| Listener ném `InvalidOrderException` | Không chờ backoff retry; chuyển recoverer theo cấu hình |
| Listener ném wrapper có root cause non-retryable | Classifier nhận đúng root cause theo cấu hình cause traversal |
| Deserializer gặp JSON hỏng | Listener không nhận payload sai; error handler/recoverer xử lý record lỗi |
| DLT broker/topic không khả dụng | Recovery publish thất bại được phát hiện; record không bị coi là đã recover thành công một cách âm thầm |
| Dependency trả HTTP 429 | Backoff/rate limit được áp dụng theo chính sách |
| Timeout sau side effect đã hoàn tất | Retry không tạo side effect trùng nhờ idempotency |

Với Embedded Kafka hoặc Testcontainers, có thể gửi record vào topic thật, quan sát số lần listener được gọi, kiểm tra offset commit và xác nhận record xuất hiện trong DLT với header nguồn. Dùng mock recoverer/backoff cho unit test classifier để kiểm tra nhanh, sau đó có ít nhất một integration test cho toàn bộ container flow.

## 18. Quy trình thiết kế chính sách lỗi

1. Liệt kê các dependency và lỗi có thể phát sinh ở mỗi bước xử lý.
2. Tạo exception nghiệp vụ riêng cho lỗi tạm thời và lỗi không thể phục hồi.
3. Xác định retry có thể làm thao tác thành công hay chỉ lặp lại cùng một thất bại.
4. Kiểm tra side effect và bổ sung idempotency key/unique constraint.
5. Cấu hình `DefaultErrorHandler`, retryable/non-retryable classifier và backoff hữu hạn.
6. Cấu hình recoverer/DLT cho lỗi không retry hoặc đã hết retry.
7. Xác định hành vi khi chính DLT publish thất bại.
8. Kiểm thử exception wrapper, deserialize error, retry exhaustion, DLT và duplicate delivery.
9. Theo dõi retry rate, lag, DLT volume và thời gian xử lý để điều chỉnh chính sách.
10. Viết runbook sửa dữ liệu, replay DLT và xử lý lỗi cấu hình diện rộng.

## 19. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Mọi `RuntimeException` đều nên retry | Phải phân loại theo nguyên nhân và khả năng phục hồi |
| Non-retryable nghĩa là bỏ message | Cần recoverer, DLT, quarantine hoặc business rejection rõ ràng |
| `DefaultErrorHandler` tự gửi mọi lỗi sang DLT | Cần cấu hình `DeadLetterPublishingRecoverer` hoặc recoverer riêng |
| Retry thành công nghĩa là không có duplicate | Lần trước có thể đã tạo side effect trước khi timeout; cần idempotency |
| `auto.offset.reset` quyết định retry | Thuộc tính đó xử lý offset không hợp lệ/không tồn tại, không phân loại exception listener |
| Tăng số retry luôn làm hệ thống đáng tin hơn | Retry quá nhiều có thể làm partition nghẽn và tạo retry storm |
| HTTP 4xx luôn permanent, 5xx luôn transient | Phải xét contract API và ngữ cảnh nghiệp vụ |
| DLT publish thất bại không ảnh hưởng tiến độ | Recovery chưa thành công phải được xử lý; cần kiểm tra hành vi error handler và recoverer |
| Non-blocking retry giữ nguyên thứ tự partition | Retry topic có thể khiến record mới hơn được xử lý trước record đang chờ retry |

## Checklist trước khi đưa error handling vào production

- Đã phân loại exception theo khả năng khắc phục và có exception nghiệp vụ rõ ràng.
- Lỗi validation, schema và cấu hình không bị retry mù.
- Lỗi tạm thời có số lần retry, backoff và tổng thời gian chờ giới hạn.
- Classifier đã được kiểm tra với exception wrapper và root cause thực tế.
- `ErrorHandlingDeserializer` được dùng nếu cần đưa lỗi deserialize vào error handler.
- Recoverer/DLT được cấu hình rõ ràng; topic DLT có partition, ACL và retention phù hợp.
- DLT publisher hỗ trợ serializer cho payload hợp lệ lẫn raw bytes khi cần.
- Có idempotency cho side effect có thể lặp lại.
- Blocking retry không vượt quá thời gian xử lý/poll cho phép; cân nhắc retry topics cho delay dài.
- Có metric/log cho retry, recovery, DLT và lỗi publish DLT.
- Đã kiểm thử retry exhaustion, non-retryable, DLT failure và replay.
- Có runbook sửa dữ liệu, sửa cấu hình và phát lại record sau khi nguyên nhân được khắc phục.

Lỗi tạm thời và lỗi không thể phục hồi cần hai chính sách khác nhau. Retry có giới hạn giúp vượt qua sự cố ngắn hạn; phân loại non-retryable và DLT giúp cô lập dữ liệu hoặc lỗi nghiệp vụ không thể tự sửa. Khi classifier, backoff, recoverer và idempotency được thiết kế cùng nhau, consumer Spring Kafka có thể phục hồi có kiểm soát mà không làm partition bị kẹt hoặc tạo side effect trùng lặp ngoài ý muốn.
