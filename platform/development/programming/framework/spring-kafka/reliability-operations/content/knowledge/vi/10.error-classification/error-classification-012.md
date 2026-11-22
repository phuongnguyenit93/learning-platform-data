# Chính sách lỗi theo loại record

Trong Spring Kafka, không phải record nào gặp lỗi cũng nên được xử lý theo cùng một cách. Một event thanh toán có thể cần retry khi dịch vụ ngân hàng tạm thời không sẵn sàng; một event có schema không hỗ trợ có thể cần chuyển sang luồng cách ly; một event thông báo có thể được bỏ qua sau khi ghi nhận lỗi nếu nghiệp vụ cho phép. Chính sách lỗi cần kết hợp loại record, nguyên nhân lỗi, mức độ có thể phục hồi và tác động nếu xử lý lại.

Spring Kafka cung cấp error handler, backoff, retry listener và recoverer để điều khiển việc retry hoặc chuyển record sang Dead Letter Topic (DLT). Tuy nhiên, `DefaultErrorHandler` phân loại chủ yếu theo loại exception. Nếu nhiều loại event nằm chung một topic và cần chính sách khác nhau, ứng dụng phải bổ sung quy tắc dựa trên metadata của record hoặc tách listener/container theo loại luồng.

## 1. Vì sao cần chính sách lỗi theo loại record?

Một consumer có thể nhận nhiều nhóm record với đặc điểm khác nhau:

- Event nghiệp vụ quan trọng như `OrderCreated`, `PaymentAuthorized` hoặc `InventoryReserved` cần tránh mất dữ liệu và thường phải retry lỗi tạm thời.
- Event có dữ liệu không hợp lệ, thiếu trường bắt buộc hoặc phiên bản schema không được hỗ trợ thường không thể thành công nếu retry cùng payload.
- Event phụ trợ như email notification hoặc analytics có thể có mức ưu tiên thấp hơn và chính sách recovery khác với luồng thanh toán.
- Event từ hệ thống phụ thuộc có thể thất bại do timeout, rate limit hoặc outage; nguyên nhân có thể tự hết sau một khoảng backoff.

Nếu retry vô hạn mọi record, một poison record có thể giữ partition và làm chậm các record hợp lệ phía sau. Nếu chuyển mọi lỗi sang DLT ngay lập tức, một outage ngắn của database có thể khiến hàng loạt record bị cách ly dù chúng có thể xử lý thành công sau vài giây. Chính sách phải phân biệt lỗi tạm thời với lỗi không thể khắc phục bằng retry.

## 2. Phân loại record trước khi chọn hành động

Record nên mang metadata đủ để nhận diện loại event và truy vết. Một envelope thường có `eventId`, `eventType`, `schemaVersion`, `occurredAt` và payload. Nếu event type được truyền qua Kafka header, consumer có thể định tuyến theo header mà không phải suy đoán từ nội dung payload.

Ví dụ một event envelope:

```json
{
  "eventId": "evt-8f31",
  "eventType": "PaymentAuthorized",
  "schemaVersion": 2,
  "occurredAt": "2026-11-15T10:15:30Z",
  "payload": {
    "paymentId": "pay-1042",
    "orderId": "ord-208"
  }
}
```

Khi sử dụng header, producer có thể gắn loại event và phiên bản schema:

```java
ProducerRecord<String, PaymentEvent> record =
        new ProducerRecord<>("business-events", event.orderId(), event);

record.headers().add(
        "event-type",
        "PaymentAuthorized".getBytes(StandardCharsets.UTF_8));
record.headers().add(
        "schema-version",
        "2".getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
```

Header là metadata hỗ trợ định tuyến và quan sát; nó không thay thế validation của payload. Nếu header và payload mâu thuẫn, consumer cần có quy tắc xác định nguồn thông tin đáng tin cậy và ghi nhận trường hợp không nhất quán.

Một ma trận chính sách cơ bản:

| Nhóm record | Ví dụ lỗi | Hành động phù hợp |
|---|---|---|
| Event nghiệp vụ quan trọng | Timeout database, HTTP 503, rate limit | Retry có backoff và giới hạn số lần; sau đó recovery/DLT |
| Payload sai định dạng | Thiếu field, sai kiểu dữ liệu, JSON không parse được | Không retry lặp cùng payload; cách ly vào DLT/quarantine |
| Schema hoặc event version chưa hỗ trợ | Consumer chưa hiểu version mới | Cách ly, cảnh báo và xử lý sau khi cập nhật consumer hoặc schema mapping |
| Vi phạm quy tắc nghiệp vụ | Số tiền âm, trạng thái chuyển không hợp lệ | Thường không retry; ghi nhận lỗi nghiệp vụ và DLT nếu cần điều tra |
| Lỗi phụ thuộc tạm thời | Database unavailable, timeout, broker phụ trợ chập chờn | Retry có backoff, jitter hoặc circuit breaker phù hợp |
| Event phụ trợ có thể bỏ qua | Analytics không thiết yếu | Recovery theo SLO nghiệp vụ; có thể DLT hoặc ghi nhận bỏ qua có kiểm soát |

Đây là chính sách theo yêu cầu nghiệp vụ. Không nên quyết định retry chỉ dựa trên tên topic hoặc tên exception mà không xác định liệu cùng record có khả năng thành công sau khi thử lại hay không.

## 3. Phân loại nguyên nhân lỗi

### Lỗi tạm thời (transient)

Lỗi tạm thời có khả năng tự hết mà không cần thay đổi payload. Ví dụ gồm timeout kết nối, HTTP 429/503, database connection tạm thời không lấy được hoặc một dependency đang phục hồi. Những lỗi này thường phù hợp với retry có khoảng nghỉ.

Retry nên có giới hạn và backoff. Retry liên tục không có khoảng nghỉ có thể làm hệ thống phụ trợ quá tải nặng hơn. Với lỗi rate limit, cần tôn trọng `Retry-After` nếu ứng dụng có thể đọc được thông tin đó và thiết kế chính sách phù hợp.

### Lỗi dữ liệu hoặc nghiệp vụ không thể retry

Payload không parse được, event thiếu định danh bắt buộc, schema version không hỗ trợ hoặc quy tắc nghiệp vụ bị vi phạm thường không tự biến thành hợp lệ sau vài lần retry. Retry cùng payload chỉ tiêu tốn tài nguyên và có thể giữ partition.

Nhóm này thường nên được đánh dấu non-retryable và chuyển sang DLT hoặc quarantine sau lần xử lý thất bại đầu tiên. DLT cần lưu đủ metadata để đội vận hành điều tra và quyết định sửa dữ liệu, nâng cấp consumer hoặc loại bỏ record theo chính sách.

### Lỗi lập trình hoặc cấu hình

Null pointer, class cast, lỗi wiring bean hoặc cấu hình serializer sai có thể ảnh hưởng tới nhiều record cùng lúc. Retry từng record thường không giải quyết được lỗi gốc. Cần phân biệt lỗi do một payload riêng lẻ với lỗi triển khai diện rộng. Nếu mọi record cùng thất bại, cần cảnh báo và có thể dừng luồng để tránh đẩy toàn bộ backlog sang DLT.

### Lỗi không xác định

Khi chưa phân loại được nguyên nhân, nên dùng số lần retry giới hạn và recovery có thể quan sát. Không nên mặc định mọi lỗi lạ đều là lỗi dữ liệu hoặc đều là lỗi tạm thời. Log exception gốc, record metadata và delivery attempt để điều tra.

## 4. Spring Kafka phân loại exception bằng DefaultErrorHandler

Trong Spring Kafka hiện đại, `DefaultErrorHandler` là common error handler cho các listener container không dùng transaction rollback flow. Handler nhận exception từ listener, áp dụng backoff, retry record và gọi recoverer khi hết lần retry hoặc exception được phân loại non-retryable.

Có thể cấu hình exception không retry bằng `addNotRetryableExceptions()` và exception cần retry bằng `addRetryableExceptions()`:

```java
@Bean
DefaultErrorHandler businessErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(
            InvalidOrderPayloadException.class,
            UnsupportedEventVersionException.class,
            BusinessRuleViolationException.class);

    handler.addRetryableExceptions(
            TemporaryInventoryException.class,
            TransientDataAccessException.class);

    return handler;
}
```

`FixedBackOff(1_000L, 3L)` biểu thị khoảng nghỉ một giây giữa các lần retry và tối đa ba lần retry sau lần giao đầu tiên. Nếu cả ba lần retry đều thất bại, recoverer được gọi. Exception được phân loại non-retryable có thể đi thẳng tới recovery mà không chờ các lần retry này.

Danh sách exception và hành vi mặc định có thể thay đổi theo phiên bản Spring Kafka. `DefaultErrorHandler` hiện đại đã có một số loại exception mặc định được xem là fatal/non-retryable, ví dụ lỗi deserialization, message conversion hoặc method argument resolution. Khi cấu hình chính sách, hãy kiểm tra classifier của phiên bản đang dùng và bổ sung rõ các exception nghiệp vụ của ứng dụng.

Một exception có thể được bọc trong exception khác khi đi qua listener adapter hoặc tầng framework. Hãy kiểm tra exception thực tế trong log và cách classifier của phiên bản hiện tại xét cause chain. Không chỉ thêm wrapper chung vào danh sách retryable nếu điều đó vô tình biến lỗi dữ liệu không thể retry thành retryable.

## 5. Phân loại theo exception không đồng nghĩa phân loại theo record type

`DefaultErrorHandler` mặc định đưa ra quyết định dựa trên exception. Ví dụ `InvalidOrderPayloadException` được xem là non-retryable ở bất kỳ record nào ném exception đó. Handler không tự hiểu rằng `PaymentAuthorized` cần ba lần retry còn `AnalyticsEvent` chỉ cần một lần, nếu cả hai cùng ném một loại exception.

Nếu các loại record có chính sách retry khác nhau, có ba hướng thiết kế:

1. Tách topic hoặc listener theo nhóm nghiệp vụ và cấu hình error handler/backoff riêng cho từng listener container.
2. Dùng một listener chung nhưng xây dựng error handling tùy biến có thể đọc metadata record như header, topic, key hoặc event type.
3. Giữ một chính sách retry chung, nhưng tùy biến recoverer để định tuyến record sang DLT/quarantine khác nhau theo loại record.

Hướng thứ nhất thường dễ vận hành nhất khi các luồng có SLO, retry budget và đội sở hữu khác nhau. Hướng thứ hai phù hợp khi nhiều event type phải cùng nằm trong một topic và thực sự cần backoff khác nhau. Hướng thứ ba thay đổi đích recovery theo loại record nhưng bản thân nó không làm cho số lần retry khác nhau.

### Mỗi loại luồng dùng một listener factory

Ví dụ topic thanh toán và topic thông báo có chính sách khác nhau:

```java
@Bean
DefaultErrorHandler paymentErrorHandler(
        KafkaTemplate<Object, Object> template) {
    var recoverer = new DeadLetterPublishingRecoverer(template);
    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(2_000L, 4L));
    handler.addNotRetryableExceptions(
            InvalidPaymentException.class,
            UnsupportedPaymentVersionException.class);
    return handler;
}

@Bean
DefaultErrorHandler notificationErrorHandler(
        KafkaTemplate<Object, Object> template) {
    var recoverer = new DeadLetterPublishingRecoverer(template);
    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(500L, 1L));
    handler.addNotRetryableExceptions(
            InvalidNotificationException.class);
    return handler;
}
```

Mỗi `ConcurrentKafkaListenerContainerFactory` được gắn error handler tương ứng:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
paymentListenerFactory(
        ConsumerFactory<String, PaymentEvent> consumerFactory,
        DefaultErrorHandler paymentErrorHandler) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(paymentErrorHandler);
    return factory;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, NotificationEvent>
notificationListenerFactory(
        ConsumerFactory<String, NotificationEvent> consumerFactory,
        DefaultErrorHandler notificationErrorHandler) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, NotificationEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(notificationErrorHandler);
    return factory;
}
```

Listener chọn factory tương ứng:

```java
@KafkaListener(
        id = "payments-listener",
        topics = "payments",
        containerFactory = "paymentListenerFactory")
public void handlePayment(PaymentEvent event) {
    paymentService.process(event);
}

@KafkaListener(
        id = "notifications-listener",
        topics = "notifications",
        containerFactory = "notificationListenerFactory")
public void handleNotification(NotificationEvent event) {
    notificationService.send(event);
}
```

Nhờ tách factory, mỗi luồng có backoff và exception classification riêng. Cần bảo đảm consumer factory, deserializer và producer dùng cho DLT phù hợp với kiểu dữ liệu tương ứng.

## 6. Định tuyến DLT theo loại record

Khi các loại event dùng chung topic, có thể dùng `DeadLetterPublishingRecoverer` với destination resolver để chọn DLT dựa trên header. Ví dụ:

```java
@Bean
DeadLetterPublishingRecoverer eventDeadLetterRecoverer(
        KafkaTemplate<Object, Object> template) {

    return new DeadLetterPublishingRecoverer(template, (record, exception) -> {
        Header typeHeader = record.headers().lastHeader("event-type");
        String eventType = typeHeader == null
                ? "unknown"
                : new String(typeHeader.value(), StandardCharsets.UTF_8);

        String dltTopic = switch (eventType) {
            case "PaymentAuthorized" -> "payments.DLT";
            case "OrderCreated" -> "orders.DLT";
            case "InventoryReserved" -> "inventory.DLT";
            default -> "unknown-events.DLT";
        };

        return new TopicPartition(dltTopic, record.partition());
    });
}
```

Đoạn code yêu cầu Java hỗ trợ switch expression. Resolver được gọi khi record cần recovery; nó chọn topic theo header và giữ partition tương ứng. Nếu DLT giữ nguyên partition number, topic đích phải có đủ partition để nhận mọi partition nguồn. Nếu số partition không tương ứng, hãy chọn chiến lược phân vùng khác thay vì để publish DLT thất bại.

`DeadLetterPublishingRecoverer` có thể bổ sung các header chứa thông tin nguồn như topic, partition, offset, timestamp và exception metadata. Các header này rất hữu ích khi điều tra và replay. Không nên loại bỏ chúng nếu quy trình vận hành cần truy vết về record gốc.

Định tuyến DLT theo event type chỉ quyết định nơi lưu record sau recovery. Nếu `PaymentAuthorized` cần bốn lần retry còn `OrderCreated` cần một lần, cần thêm chiến lược backoff/classification theo record hoặc tách listener/container. Không nên cho rằng resolver DLT có thể tự thay đổi số lần retry.

## 7. Lỗi deserialization và ErrorHandlingDeserializer

Một số lỗi xảy ra trước khi listener nhận được object Java. Ví dụ JSON hỏng, byte payload không đúng định dạng hoặc deserializer không thể tạo object. Nếu consumer deserializer ném exception ngay trong `poll()`, listener không có cơ hội kiểm tra record và xử lý lỗi theo code nghiệp vụ.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để bắt lỗi deserialization và chuyển thông tin lỗi vào header của record, cho phép container error handler hoặc recoverer xử lý. Ví dụ cấu hình value deserializer trong Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.BusinessEvent
        spring.json.trusted.packages: com.example.events
```

Delegate deserializer thực hiện parse payload. Nếu parse thất bại, `ErrorHandlingDeserializer` lưu thông tin exception trong header để error handling có thể xử lý record. Cấu hình thực tế cần khớp serializer, type mapping, trusted package và phiên bản Spring Kafka; không bật trusted packages quá rộng nếu ứng dụng nhận dữ liệu từ nguồn không tin cậy.

Khi publish DLT cho record lỗi deserialization, payload có thể vẫn là byte array gốc thay vì object đã deserialize. Producer dùng để publish DLT cần serializer có thể xử lý cả byte array và các kiểu object thông thường, hoặc được cấu hình theo chiến lược serializer phù hợp. Nếu serializer không chấp nhận kiểu dữ liệu thực tế, recovery có thể thất bại và record vẫn cần được xử lý theo error handler.

Phân loại lỗi deserialization thường là non-retryable với cùng payload. Nếu lỗi do producer gửi nhầm schema hoặc payload bị cắt, retry không làm byte dữ liệu thay đổi. Cần DLT/quarantine và cảnh báo producer hoặc schema owner.

## 8. Validation và lỗi nghiệp vụ sau deserialization

Sau khi payload đã được chuyển thành object, listener hoặc service nghiệp vụ có thể kiểm tra các điều kiện:

- Field bắt buộc có giá trị.
- ID, currency, amount hoặc timestamp hợp lệ.
- Event type và schema version được hỗ trợ.
- Trạng thái hiện tại cho phép chuyển sang trạng thái mới.
- Record không vi phạm quy tắc idempotency hoặc tính duy nhất.

Ví dụ:

```java
@KafkaListener(topics = "payments", groupId = "payment-service")
public void handle(PaymentEvent event) {
    if (event.paymentId() == null || event.amount().signum() <= 0) {
        throw new InvalidPaymentException(
                "paymentId và amount phải hợp lệ");
    }

    paymentService.authorize(event);
}
```

`InvalidPaymentException` nên được phân loại non-retryable nếu dữ liệu đầu vào cần được sửa từ producer hoặc quy trình nghiệp vụ. Với lỗi như database timeout trong `authorize()`, nên dùng exception riêng thể hiện tính tạm thời để retry có kiểm soát.

Tránh dùng một exception chung như `RuntimeException` cho cả validation, timeout và lỗi lập trình. Nếu mọi lỗi đều cùng một loại, error handler không thể áp dụng chính sách khác nhau đáng tin cậy. Tạo exception theo nguyên nhân nghiệp vụ giúp log, retry classification và metric rõ ràng hơn.

## 9. Batch listener và xác định record lỗi

Với record listener, exception phát sinh trong một lần gọi thường gắn trực tiếp với record đang xử lý. Với batch listener, một lần gọi có thể chứa nhiều record. Nếu chỉ ném exception chung, error handler có thể không biết record nào trong batch gây lỗi và có thể phải retry lại cả batch.

Spring Kafka hỗ trợ `BatchListenerFailedException` để listener chỉ rõ record hoặc index bị lỗi. Ví dụ:

```java
@KafkaListener(topics = "orders", groupId = "order-projection")
public void handleBatch(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, OrderEvent> record = records.get(i);
        try {
            orderProjectionService.apply(record.value());
        }
        catch (InvalidOrderPayloadException ex) {
            throw new BatchListenerFailedException(
                    "Order payload không hợp lệ",
                    ex,
                    i);
        }
    }
}
```

Khi dùng `DefaultErrorHandler` với batch listener, thông tin record/index giúp handler xác định tiến độ đã xử lý và record cần retry hoặc recover. Nếu exception không chỉ rõ record lỗi, handler có thể phải xử lý theo cách retry toàn batch. Hãy chọn cách xử lý phù hợp với tính nguyên tử của batch và đảm bảo các side effect đã hoàn tất trước đó có thể chịu được replay.

Không nên tự bắt exception trong vòng lặp rồi tiếp tục các record phía sau nếu nghiệp vụ yêu cầu thứ tự hoặc tính toàn vẹn batch. Nếu một phần batch đã tạo side effect rồi batch được retry, cần idempotency cho từng event hoặc transaction database phù hợp.

## 10. Retry budget và backoff

Retry cần được giới hạn bởi ngân sách thời gian và số lần thử. Một record có thể giữ partition trong thời gian dài nếu retry liên tục. Cần cân nhắc:

- Thời gian xử lý mỗi lần thử.
- Số lần retry tối đa.
- Khoảng nghỉ giữa các lần retry.
- Thời gian outage dự kiến của dependency.
- `max.poll.interval.ms` và ảnh hưởng của retry tới consumer group.
- Mức độ ưu tiên của record và SLO xử lý.

Ví dụ dùng exponential backoff:

```java
BackOff backOff = new ExponentialBackOffWithMaxRetries(5);
((ExponentialBackOffWithMaxRetries) backOff).setInitialInterval(500L);
((ExponentialBackOffWithMaxRetries) backOff).setMultiplier(2.0);
((ExponentialBackOffWithMaxRetries) backOff).setMaxInterval(8_000L);

DefaultErrorHandler handler = new DefaultErrorHandler(recoverer, backOff);
```

Với cấu hình trên, retry bắt đầu sau khoảng 500 ms, tăng theo hệ số 2 và giới hạn mỗi khoảng nghỉ ở 8 giây, tối đa năm lần retry. Thời gian thực tế còn phụ thuộc thời gian xử lý từng lần và scheduling. Nếu cần jitter để tránh nhiều consumer retry đồng loạt sau một outage, hãy bổ sung cơ chế backoff có jitter phù hợp với phiên bản/framework hoặc điều phối retry qua hệ thống riêng.

Khi retry budget hết, recoverer cần thực hiện một hành động có thể quan sát: publish DLT, lưu quarantine, hoặc ghi nhận bỏ qua theo chính sách đã phê duyệt. Không nên để recovery thất bại rồi vẫn coi record đã được xử lý.

## 11. Retry topic và tách luồng lỗi dài hạn

Với lỗi cần chờ lâu, retry tại chỗ có thể giữ partition và chặn record phía sau. Retry topic cho phép chuyển record sang topic retry với thời gian chờ, sau đó một consumer khác nhận lại. Spring Kafka có hỗ trợ non-blocking retry topic qua `@RetryableTopic` trong các phiên bản phù hợp.

Ví dụ minh họa:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        include = {TemporaryInventoryException.class},
        exclude = {InvalidOrderPayloadException.class})
@KafkaListener(topics = "orders", groupId = "order-projection")
public void handle(OrderEvent event) {
    orderProjectionService.apply(event);
}
```

Annotation và các thuộc tính retry topic thay đổi theo phiên bản Spring Kafka; cần kiểm tra phiên bản dự án và khả năng tương thích với listener type, transaction mode và DLT routing. Retry topic tạo ra nhiều topic phụ trợ và có thể thay đổi thứ tự xử lý giữa các record cùng key. Chỉ dùng khi chấp nhận đặc tính này và có quy trình vận hành các topic retry.

Non-blocking retry topic phù hợp khi cần chờ lâu mà không giữ partition gốc. Với lỗi ngắn, retry blocking trong `DefaultErrorHandler` có thể đơn giản hơn. Không nên bật đồng thời nhiều tầng retry mà không tính tổng số lần giao và thời gian chờ; retry của HTTP client, service layer, error handler và retry topic có thể nhân số lần gọi ngoài dự kiến.

## 12. DLT và quy trình phục hồi

DLT lưu record đã hết retry hoặc được xác định không nên retry. Một record DLT cần giữ đủ thông tin để người vận hành trả lời:

- Record đến từ topic, partition và offset nào?
- Consumer group nào đã xử lý?
- Event ID, key, event type và schema version là gì?
- Exception class, message và stack trace nào đã xảy ra?
- Record đã thử bao nhiêu lần và lần cuối lúc nào?
- Dữ liệu có thể sửa và replay không, hay phải đánh dấu terminal?

Quy trình phục hồi nên gồm các bước:

1. Phân loại record trong DLT theo event type và nguyên nhân.
2. Xác định lỗi do dữ liệu, phiên bản consumer hay dependency.
3. Sửa dữ liệu hoặc triển khai consumer có khả năng xử lý schema/event version đó.
4. Replay có kiểm soát, giữ nguyên event ID và metadata nguồn.
5. Theo dõi kết quả replay và xác nhận record đã được xử lý hoặc được đóng theo chính sách.

Không replay toàn bộ DLT vào topic gốc một cách tự động nếu chưa biết nguyên nhân. Nếu lỗi vẫn còn, record sẽ quay lại DLT và có thể tạo vòng lặp. Replay cần idempotent để không lặp tác động đã hoàn tất trước lần lỗi hoặc lần dừng trước đó.

## 13. Retry, commit offset và transaction

Với consumer không transactional, `DefaultErrorHandler` phối hợp seek/retry và commit offset theo ack mode. Khi record được recover thành công, container có thể tiến offset qua record đó theo cấu hình handler. Nếu publish DLT thất bại, recovery phải được xem là thất bại để record không bị âm thầm bỏ qua.

Với listener container chạy trong Kafka transaction, lỗi listener thường dẫn tới rollback transaction. Chính sách retry/recovery được quản lý qua transaction rollback flow, thường dùng `DefaultAfterRollbackProcessor` thay vì chỉ áp dụng `DefaultErrorHandler` như một listener không transactional. Có thể cấu hình recoverer và backoff cho after-rollback processor; khi cần commit offset của record đã recover cùng với việc publish DLT, cần cấu hình transaction phù hợp.

Không nên trộn lẫn ví dụ cấu hình error handler non-transactional với transactional listener container mà không xem xét rollback flow. Hãy xác định listener có tham gia Kafka transaction hay không trước khi chọn handler, vì điểm commit offset, rollback và recovery khác nhau.

Kafka transaction có thể bảo vệ output Kafka và offset đầu vào trong cùng transaction. Nó không tự bảo vệ side effect trong database hoặc HTTP API. Với side effect ngoài Kafka, dùng idempotency, inbox/outbox hoặc transaction database phù hợp để record retry không gây tác động trùng.

## 14. Quan sát chính sách lỗi

Chính sách lỗi chỉ có hiệu quả khi vận hành có thể đo được. Nên theo dõi tối thiểu:

- Số lần retry theo topic, event type và exception class.
- Số record chuyển sang DLT/quarantine theo nguyên nhân.
- Tỷ lệ lỗi transient so với lỗi permanent.
- Thời gian từ lần giao đầu tiên tới lần xử lý thành công hoặc recovery.
- Consumer lag, rebalance và thời gian partition bị giữ bởi retry.
- Lỗi publish DLT và số record tồn trong DLT.
- Tỷ lệ duplicate bị phát hiện bởi idempotency hoặc inbox.

Log nên có topic, partition, offset, key, event ID, event type, schema version, consumer group, delivery attempt và exception class. Tránh log payload nhạy cảm. Khi có thể, dùng metric tag có cardinality thấp; không dùng event ID làm label metric vì số lượng giá trị có thể tăng không giới hạn.

Một `RetryListener` có thể ghi nhận mỗi lần retry:

```java
handler.setRetryListeners((record, exception, deliveryAttempt) -> {
    log.warn(
            "Retry topic={} partition={} offset={} attempt={} exception={}",
            record.topic(),
            record.partition(),
            record.offset(),
            deliveryAttempt,
            exception.getClass().getSimpleName());
});
```

Chữ ký callback cụ thể có thể khác giữa các phiên bản; dùng API tương ứng của Spring Kafka trong dự án. Kết hợp log với metric và alert để phát hiện một loại record đột ngột chuyển sang DLT hàng loạt.

## 15. Ví dụ thiết kế chính sách cho một topic nhiều event type

Giả sử topic `business-events` chứa `OrderCreated`, `PaymentAuthorized` và `InventoryReserved`. Mỗi event có header `event-type` và ID ổn định.

| Event type | Lỗi transient | Lỗi permanent | DLT |
|---|---|---|---|
| `OrderCreated` | Retry tối đa 3 lần với backoff ngắn | DLT để điều tra dữ liệu đơn hàng | `orders.DLT` |
| `PaymentAuthorized` | Retry tối đa 5 lần với backoff dài hơn | DLT và cảnh báo đội payment | `payments.DLT` |
| `InventoryReserved` | Retry ngắn, sau đó DLT | DLT và kiểm tra trạng thái tồn kho | `inventory.DLT` |
| Event type không biết | Không retry payload không nhận diện được | Quarantine và cảnh báo schema/producer | `unknown-events.DLT` |

Nếu chỉ cần DLT khác nhau nhưng retry chung, một `DefaultErrorHandler` với recoverer định tuyến theo header có thể đủ. Nếu số lần retry/backoff khác nhau theo event type, tách listener/container hoặc triển khai error handling tùy biến có khả năng đọc record metadata. Đừng cố biểu diễn toàn bộ chính sách record bằng một danh sách exception toàn cục nếu cùng exception có ý nghĩa khác nhau ở từng loại event.

Với topic chứa nhiều loại event, listener có thể deserialize thành envelope chung rồi dispatch theo `eventType`. Nếu deserialization thất bại trước khi envelope được tạo, cần `ErrorHandlingDeserializer` và chính sách dành cho record không thể nhận diện. Đây là lý do metadata event type nên được truyền ổn định trong header hoặc cấu trúc envelope có thể đọc được.

## 16. Nguyên tắc thiết kế

- Phân loại lỗi theo khả năng phục hồi: transient, permanent, programming/configuration và unknown.
- Phân biệt exception classification với record-type policy; `DefaultErrorHandler` mặc định phân loại exception.
- Dùng exception nghiệp vụ cụ thể để biểu đạt lỗi retryable và non-retryable.
- Giới hạn retry và dùng backoff phù hợp để tránh làm dependency quá tải.
- Dùng `ErrorHandlingDeserializer` cho lỗi xảy ra trước khi listener nhận object.
- Dùng DLT/quarantine cho record cần điều tra và giữ metadata nguồn để replay.
- Tách listener/container khi các nhóm record có retry budget hoặc SLO khác nhau.
- Với batch listener, chỉ rõ record lỗi bằng `BatchListenerFailedException` khi phù hợp.
- Không trộn cấu hình non-transactional error handler với rollback flow của transactional listener mà không xem xét semantics.
- Bảo vệ side effect ngoài Kafka bằng idempotency hoặc inbox/outbox.
- Theo dõi retry, DLT, consumer lag và lỗi recovery theo event type.

Chính sách lỗi theo loại record giúp consumer xử lý lỗi đúng với đặc tính nghiệp vụ của từng event. Hãy nhận diện record bằng metadata ổn định, phân biệt lỗi có thể retry với lỗi cần cách ly, chọn backoff và recovery theo retry budget, rồi đo lường kết quả. Khi các loại record có chính sách khác nhau rõ rệt, tách listener/container hoặc bổ sung error handling tùy biến để quyết định dựa trên record metadata thay vì chỉ dựa vào exception class.
