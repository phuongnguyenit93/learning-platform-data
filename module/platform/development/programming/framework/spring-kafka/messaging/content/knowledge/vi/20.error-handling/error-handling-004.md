# CommonErrorHandler

Khi một phương thức `@KafkaListener` ném exception, Spring Kafka cần quyết định record sẽ được retry, phục hồi, chuyển sang dead-letter topic hay làm listener container dừng lại. `CommonErrorHandler` là abstraction thống nhất để listener container xử lý các lỗi phát sinh trong quá trình nhận và xử lý record, áp dụng cho cả record listener và batch listener.

Trong phần lớn ứng dụng, bạn không cần tự triển khai interface này. `DefaultErrorHandler` là lựa chọn tổng quát cho retry theo backoff và recovery. Có thể gắn handler vào `ConcurrentKafkaListenerContainerFactory`, cấu hình loại exception được retry, và dùng `DeadLetterPublishingRecoverer` để chuyển record không xử lý được sang DLT.

## 1. CommonErrorHandler giải quyết vấn đề gì?

Listener có thể gặp lỗi do nhiều nguyên nhân:

- Dữ liệu không hợp lệ hoặc thiếu trường bắt buộc.
- Database tạm thời không kết nối được.
- Dịch vụ downstream timeout hoặc bị giới hạn tốc độ.
- Lỗi chuyển đổi payload hoặc deserialize.
- Lỗi lập trình hoặc trạng thái nghiệp vụ không hợp lệ.

Nếu không có chính sách xử lý lỗi rõ ràng, consumer có thể liên tục đọc lại một record lỗi, dừng xử lý partition hoặc commit offset không đúng thời điểm. `CommonErrorHandler` cho phép container áp dụng một chiến lược thống nhất sau khi listener hoặc quá trình poll gặp exception.

Luồng xử lý khái quát:

```text
Kafka poll
    |
    v
Listener xử lý record/batch
    |
    +---- Thành công --------------------> Commit theo AckMode
    |
    +---- Ném exception
              |
              v
       CommonErrorHandler
              |
       +------+-------------------+
       |                          |
       v                          v
   Retry/backoff              Recovery
       |                          |
       |                          +--> Ghi DLT
       |                          +--> Bỏ qua có chủ đích
       |                          +--> Dừng container
       |
       +--> Gọi listener lại
```

Handler quyết định việc retry/recovery; listener container vẫn chịu trách nhiệm poll, seek, acknowledgement và commit offset theo cấu hình.

## 2. CommonErrorHandler và các API xử lý lỗi cũ

Từ Spring Kafka 2.8, `CommonErrorHandler` hợp nhất cách xử lý lỗi của record listener và batch listener. Nó thay thế các abstraction cũ `ErrorHandler` và `BatchErrorHandler`.

| API | Vai trò |
| --- | --- |
| `CommonErrorHandler` | Interface chung cho lỗi của listener container |
| `DefaultErrorHandler` | Retry theo `BackOff`, phân loại exception và phục hồi record sau khi hết retry |
| `CommonLoggingErrorHandler` | Ghi log exception theo chiến lược logging đơn giản |
| `CommonContainerStoppingErrorHandler` | Dừng container khi xảy ra lỗi để record chưa hoàn tất có thể được xử lý lại sau |
| `CommonDelegatingErrorHandler` | Chọn handler khác nhau dựa trên loại exception |
| `CommonMixedErrorHandler` | Dùng handler riêng cho record listener và batch listener |

Các lớp specialized phù hợp với chính sách vận hành cụ thể. Nếu cần retry có giới hạn và chuyển record lỗi sang DLT, `DefaultErrorHandler` thường là điểm bắt đầu phù hợp.

Không nên tiếp tục xây mới dựa trên `SeekToCurrentErrorHandler` hoặc `RecoveringBatchErrorHandler` trong code hiện đại; các trường hợp phổ biến của chúng đã được thay bằng `DefaultErrorHandler`.

Interface `CommonErrorHandler` cung cấp các điểm mở rộng cho những tình huống khác nhau: xử lý một record (`handleOne`), xử lý các record còn lại khi cần seek (`handleRemaining`), xử lý batch (`handleBatch`) và xử lý exception không gắn với một record cụ thể như lỗi poll (`handleOtherException`). `seeksAfterHandling()` cho biết handler có tự quản lý seek hay không; `isAckAfterHandle()` quyết định container có commit sau khi handler kết thúc bình thường. Chỉ triển khai interface trực tiếp khi các handler có sẵn không đáp ứng được chính sách cần thiết.

## 3. Gắn CommonErrorHandler vào listener container factory

`CommonErrorHandler` được cấu hình trên `ConcurrentKafkaListenerContainerFactory`. Mọi listener dùng factory đó sẽ nhận cùng chính sách lỗi, trừ khi ứng dụng dùng factory riêng.

Ví dụ tối thiểu với `DefaultErrorHandler`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public DefaultErrorHandler commonErrorHandler() {
        // Chờ 1 giây giữa các lần retry, tối đa 2 lần retry.
        return new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    DefaultErrorHandler commonErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);
        return factory;
    }
}
```

`FixedBackOff(1_000L, 2L)` nghĩa là chờ một giây giữa các lần retry và cho phép hai lần retry sau lần xử lý đầu tiên. Tổng cộng listener có thể được gọi tối đa ba lần cho một lần giao record nếu cả hai lần retry đều thất bại.

Các phương thức tạo bean `DefaultErrorHandler` ở những ví dụ tiếp theo là các cấu hình thay thế để minh họa từng lựa chọn. Trong một listener factory, chỉ đăng ký handler phù hợp với chính sách thực tế; không tạo nhiều bean cùng kiểu rồi inject theo kiểu mà không dùng `@Qualifier`.

Gắn factory vào listener:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-projection",
        containerFactory = "kafkaListenerContainerFactory")
public void onMessage(OrderCreatedEvent event) {
    orderService.process(event);
}
```

Nếu dùng Spring Boot auto-configuration, có thể tạo bean `CommonErrorHandler` và cấu hình factory theo cơ chế Boot của phiên bản đang dùng. Khi tự khai báo `ConcurrentKafkaListenerContainerFactory`, hãy gọi `setCommonErrorHandler(...)` tường minh để tránh nhầm lẫn factory nào đang sử dụng handler.

## 4. DefaultErrorHandler và retry/backoff

`DefaultErrorHandler` xử lý lỗi bằng cách thử lại record theo `BackOff`. Khi hết số lần retry, nó gọi recoverer để phục hồi record. Nếu không truyền recoverer, handler mặc định ghi log record đã thất bại sau khi hết retry.

Các loại backoff thường dùng:

| BackOff | Hành vi |
| --- | --- |
| `FixedBackOff` | Chờ một khoảng thời gian cố định giữa các lần retry |
| `ExponentialBackOff` | Tăng dần thời gian chờ theo hệ số nhân |
| `ExponentialBackOffWithMaxRetries` | Backoff lũy thừa với số lần retry tối đa rõ ràng |

Ví dụ backoff lũy thừa:

```java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.ExponentialBackOff;

@Bean
public DefaultErrorHandler retryErrorHandler() {
    ExponentialBackOff backOff = new ExponentialBackOff(500L, 2.0);
    backOff.setMaxInterval(5_000L);
    backOff.setMaxElapsedTime(20_000L);

    return new DefaultErrorHandler(backOff);
}
```

Thời gian chờ tăng từ 500 ms, nhân đôi sau mỗi lần retry và không vượt quá 5 giây. `maxElapsedTime` giới hạn tổng thời gian backoff theo cơ chế của `ExponentialBackOff`; nếu cần số lần thử chính xác và dễ đọc, `FixedBackOff` hoặc `ExponentialBackOffWithMaxRetries` thường rõ ràng hơn.

Retry là blocking retry: consumer thread giữ việc xử lý record trong thời gian retry/backoff. Điều này có thể làm partition tạm thời không tiến lên và ảnh hưởng consumer lag. Chọn số lần retry và thời gian chờ theo timeout của downstream, `max.poll.interval.ms` và yêu cầu latency.

## 5. Phân loại exception: lỗi nào nên retry?

Không phải lỗi nào cũng tự hết khi thử lại. Ví dụ, timeout database có thể là lỗi tạm thời; nhưng payload sai schema hoặc thiếu trường bắt buộc thường không thể sửa bằng retry.

`DefaultErrorHandler` có phân loại exception mặc định. Một số lỗi chuyển đổi/deserialization và lỗi kiểu dữ liệu như `DeserializationException`, `MessageConversionException`, `ConversionException`, `MethodArgumentResolutionException`, `NoSuchMethodException` và `ClassCastException` được xem là không retryable theo mặc định vì thử lại cùng record thường không giải quyết được vấn đề.

Có thể thêm exception không retryable hoặc retryable:

```java
import org.springframework.dao.TransientDataAccessException;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
public DefaultErrorHandler classifiedErrorHandler() {
    DefaultErrorHandler handler = new DefaultErrorHandler(
            new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(
            IllegalArgumentException.class,
            UnsupportedOperationException.class);

    handler.addRetryableExceptions(
            TransientDataAccessException.class);

    return handler;
}
```

Trong ví dụ, lỗi dữ liệu/logic được chỉ định sẽ đi thẳng đến recovery; lỗi database tạm thời được retry. Các exception chưa phân loại tiếp tục theo classification mặc định của `DefaultErrorHandler`.

Khi listener bọc exception gốc trong một exception khác, cần kiểm tra cause chain. `DefaultErrorHandler` hỗ trợ phân loại exception theo cause mặc định; tránh bọc lỗi làm mất nguyên nhân gốc hoặc chuyển mọi lỗi thành cùng một loại chung.

## 6. Recoverer và DeadLetterPublishingRecoverer

Khi hết retry, recoverer quyết định làm gì với record lỗi. Một lựa chọn thường gặp là `DeadLetterPublishingRecoverer`, dùng `KafkaTemplate` để publish record sang dead-letter topic (DLT).

Ví dụ:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
public DefaultErrorHandler dltErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}
```

Ví dụ định tuyến record từ `orders.created` partition 1 sang `orders.created.DLT` partition 1. DLT đích phải tồn tại hoặc được tạo theo cơ chế quản trị topic của ứng dụng, và phải có đủ partition tương ứng nếu giữ nguyên partition index.

Nếu dùng constructor mặc định của `DeadLetterPublishingRecoverer`, Spring Kafka định tuyến theo quy ước topic gốc cộng hậu tố `.DLT` và giữ partition gốc. Có thể thay resolver để định tuyến theo exception, tenant hoặc nhóm lỗi. Cần quyết định rõ khi nào giữ partition, khi nào chuyển về một DLT chung.

Recoverer có thể thêm các header mô tả exception, stack trace, topic/partition/offset gốc và thông tin delivery. Không nên log hoặc phát tán dữ liệu nhạy cảm trong payload/headers khi DLT được nhiều nhóm truy cập.

Nếu publish DLT thất bại, recoverer có thể ném exception. Khi đó container không nên coi record gốc đã được phục hồi thành công và commit offset một cách im lặng. Hãy giám sát lỗi publish DLT và bảo đảm producer DLT có serializer phù hợp với cả payload bình thường lẫn dữ liệu thô trong trường hợp deserialize thất bại.

## 7. Xử lý lỗi ở record listener

Với record listener, `DefaultErrorHandler` có thể retry record lỗi và sau đó phục hồi nó. Các record khác trong poll được xử lý theo cơ chế seek/commit của container.

Ví dụ listener:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(OrderCreatedEvent event) {
    orderService.process(event);
}
```

Nếu `orderService.process` ném exception, handler thực hiện retry theo backoff. Nếu lần retry thành công, container tiếp tục xử lý. Nếu hết retry, recoverer publish record sang DLT; sau khi recovery hoàn tất, offset có thể được commit theo cấu hình acknowledgement.

Không bắt exception rồi chỉ ghi log nếu muốn `CommonErrorHandler` xử lý retry. Listener phải truyền exception ra ngoài hoặc chủ động dùng API recovery/acknowledgement phù hợp.

## 8. Xử lý lỗi ở batch listener

Với batch listener, một lần gọi listener nhận nhiều record. Nếu chỉ ném exception chung, handler có thể không biết record nào trong batch gây lỗi và phải retry cả batch.

Để chỉ rõ record thất bại, có thể ném `BatchListenerFailedException` với index tương ứng:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.BatchListenerFailedException;

@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-projection",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onMessages(List<ConsumerRecord<String, OrderCreatedEvent>> records) {
    for (int index = 0; index < records.size(); index++) {
        try {
            orderService.process(records.get(index).value());
        }
        catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Cannot process order event",
                    exception,
                    index);
        }
    }
}
```

Với `DefaultErrorHandler`, thông tin index cho phép container xác định các record đứng trước record lỗi đã xử lý thành công, rồi commit phần phù hợp và retry/recover record lỗi cùng các record còn lại. Nếu không xác định được vị trí lỗi, cả batch có thể phải được xử lý lại.

Batch listener cần thiết kế thao tác idempotent vì một phần batch có thể được giao lại sau lỗi. Cũng cần xác định rõ transaction và acknowledgement mode đang dùng trước khi kết hợp partial batch recovery.

## 9. Seek và retained records sau lỗi

`DefaultErrorHandler` mặc định sử dụng seek để đưa consumer trở lại offset cần xử lý sau lỗi. Các record chưa xử lý được đọc lại từ broker ở lần poll tiếp theo.

Từ Spring Kafka 2.9, có thể cấu hình `seekAfterError=false` để container giữ lại các record chưa xử lý và giao lại chúng sau một lần poll tạm dừng nhằm duy trì consumer group. Cách này tránh seek thủ công về các offset còn lại, nhưng record vẫn có thể được giao lại và cần xử lý theo cùng chính sách lỗi.

Ví dụ:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L));
handler.setSeekAfterError(false);
```

Chọn seek hay retained records theo đặc điểm listener, kích thước batch và khả năng quản lý bộ nhớ. Với batch lớn hoặc retry kéo dài, cần theo dõi lượng record được giữ trong container.

## 10. AckAfterHandle và commit offset sau recovery

`CommonErrorHandler` có thể xử lý lỗi xong và trả quyền điều khiển cho container. `isAckAfterHandle()` quyết định container có commit offset khi handler đã xử lý exception mà không ném exception tiếp hay không.

`DefaultErrorHandler` mặc định bật `ackAfterHandle`. Khi record đã được recover thành công, ví dụ publish DLT thành công, container có thể commit offset gốc theo AckMode. Điều này cho phép group tiếp tục tiến lên thay vì đọc lại vô hạn record đã được chuyển sang DLT.

Có thể thay đổi:

```java
handler.setAckAfterHandle(false);
```

Chỉ tắt tùy chọn này khi có chủ đích giữ offset chưa commit sau recovery. Nếu không hiểu hệ quả, record đã được DLT nhưng offset gốc không tiến có thể tiếp tục được đọc lại. Cần kiểm tra tương tác giữa `AckMode`, manual acknowledgement, transaction và recovery trước khi thay đổi.

## 11. Lỗi deserialize xảy ra trước khi listener được gọi

Không phải mọi exception đều xuất phát từ phương thức `@KafkaListener`. Nếu JSON sai hoặc deserializer không tạo được object, lỗi xảy ra trong lúc Kafka consumer chuyển byte thành key/value, trước khi listener nhận payload.

Với lỗi này, cần cấu hình `ErrorHandlingDeserializer` bọc deserializer thật:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.messaging.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.messaging
```

`ErrorHandlingDeserializer` lưu thông tin lỗi để container/error handler có thể xử lý record hỏng. Nếu muốn publish raw bytes sang DLT, producer dùng cho DLT phải hỗ trợ cả byte array lẫn kiểu payload thông thường, ví dụ cấu hình serializer theo kiểu dữ liệu. Không giả định `CommonErrorHandler` có thể nhận một DTO hợp lệ khi deserialization đã thất bại.

## 12. Retry trong CommonErrorHandler và retry topic

`DefaultErrorHandler` thường thực hiện blocking retry: record lỗi được thử lại trên consumer thread, partition có thể phải chờ cho đến khi retry/recovery hoàn tất.

Spring Kafka cũng có cơ chế non-blocking retry topic, thường được cấu hình bằng `@RetryableTopic`. Cơ chế này chuyển record sang retry topic với thời gian chờ riêng, cho phép consumer tiếp tục xử lý record khác trong partition. Đây là mô hình retry khác với retry tại chỗ của `CommonErrorHandler`.

Không nên cấu hình hai cơ chế cùng xử lý một lỗi mà không có thiết kế rõ ràng. Hãy chọn:

- Blocking retry qua `DefaultErrorHandler` khi muốn giữ luồng xử lý partition và recovery theo offset.
- Non-blocking retry topic khi muốn tách thời gian chờ khỏi partition gốc và chấp nhận mô hình topic/ordering tương ứng.

Non-blocking retry topic không kết hợp với container transactions. Nếu luồng cần EOS read-process-write, cần thiết kế retry/rollback phù hợp với transaction thay vì mặc định thêm `@RetryableTopic`.

Với listener container dùng Kafka transaction, exception thoát khỏi listener sẽ làm transaction rollback. Cơ chế retry sau rollback thường được điều khiển bởi `DefaultAfterRollbackProcessor`; không nên cấu hình error handler theo cách nuốt exception rồi trả về bình thường, vì container có thể commit transaction thay vì rollback. Hãy thiết kế riêng recovery/DLT cho transactional listener theo hướng dẫn transaction của Spring Kafka.

## 13. Theo dõi delivery attempt và retry

`DefaultErrorHandler` hỗ trợ `RetryListener` để quan sát từng lần delivery, kết quả retry và recovery. Có thể dùng callback để ghi metric, log correlation ID hoặc gửi cảnh báo.

Ví dụ:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.RetryListener;

handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        log.warn(
                "Kafka delivery failed: topic={}, partition={}, offset={}, attempt={}",
                record.topic(), record.partition(), record.offset(),
                deliveryAttempt, exception);
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        log.error("Kafka record recovered: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset(), exception);
    }
});
```

Ví dụ giả định lớp cấu hình có logger `log`. Không log toàn bộ payload nếu có dữ liệu nhạy cảm. Nên ghi topic, partition, offset, event ID/correlation ID đã được phép, loại exception và delivery attempt.

Các chỉ số vận hành hữu ích:

- Số lần retry theo exception và topic.
- Số record được recover hoặc publish DLT.
- Tỷ lệ publish DLT thất bại.
- Thời gian xử lý listener và thời gian backoff.
- Consumer lag trong thời gian retry.
- Số lần container dừng do lỗi.

## 14. Khi nào cần CommonDelegatingErrorHandler?

Một số ứng dụng cần chính sách khác nhau theo exception. Ví dụ lỗi database tạm thời được retry, lỗi dữ liệu được chuyển DLT ngay, còn lỗi hạ tầng nghiêm trọng làm container dừng.

`CommonDelegatingErrorHandler` cho phép chọn handler theo loại exception. Các handler được delegate cần có cấu hình tương thích về các thuộc tính chung như `ackAfterHandle` và `seekAfterError`; không nên ghép các handler có hành vi container mâu thuẫn.

Với chính sách phân loại đơn giản, `DefaultErrorHandler.addRetryableExceptions(...)` và `addNotRetryableExceptions(...)` thường đủ. Chỉ dùng delegating handler khi mỗi nhóm lỗi thực sự cần một chiến lược xử lý khác nhau.

## 15. Kiểm thử CommonErrorHandler

Kiểm thử cần xác minh cả listener retry, recovery và offset behavior. Không chỉ assert rằng exception đã được log.

Một integration test điển hình:

1. Tạo topic input và DLT trong broker kiểm thử.
2. Cấu hình listener với `DefaultErrorHandler`, backoff ngắn và `DeadLetterPublishingRecoverer`.
3. Gửi record mà listener sẽ thất bại trong hai lần đầu rồi thành công ở lần tiếp theo.
4. Xác nhận listener được gọi đúng số lần và record không đi vào DLT.
5. Gửi record lỗi vĩnh viễn, xác nhận hết retry thì record xuất hiện trong DLT.
6. Xác nhận consumer group tiến qua offset đã được recover.

Các trường hợp nên kiểm tra thêm:

- Exception retryable và non-retryable.
- Batch listener ném `BatchListenerFailedException` tại index cụ thể.
- Lỗi deserialize được bọc bởi `ErrorHandlingDeserializer`.
- DLT producer lỗi hoặc topic DLT không tồn tại.
- `ackAfterHandle` bật/tắt và `seekAfterError` theo cấu hình.
- Container stopping handler và hành vi sau khi khởi động lại.

Dùng `CountDownLatch`, `BlockingQueue` hoặc Awaitility để chờ sự kiện với timeout. Tránh `Thread.sleep` cố định ngắn vì thời gian poll, retry và rebalance có thể thay đổi giữa các lần chạy.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Listener retry vô hạn | Dùng backoff không giới hạn hoặc không có recovery | Đặt số lần retry và recoverer rõ ràng |
| Payload sai vẫn retry nhiều lần | Chưa phân loại exception không retryable | Dùng `addNotRetryableExceptions` hoặc classification |
| Record bị xử lý lại sau khi đã vào DLT | Offset không được commit sau recovery hoặc publish DLT chưa thành công | Kiểm tra `ackAfterHandle`, AckMode và recoverer result |
| DLT publish lỗi serialization | DLT producer không hỗ trợ kiểu payload gốc hoặc raw bytes | Cấu hình serializer tương thích với các loại payload |
| Batch bị retry toàn bộ | Listener không chỉ rõ record/index lỗi | Ném `BatchListenerFailedException` với index phù hợp |
| Listener không được gọi khi JSON lỗi | Deserialization thất bại trước listener invocation | Dùng `ErrorHandlingDeserializer` |
| Partition bị chậm trong lúc retry | Blocking backoff giữ consumer thread | Giảm retry/backoff hoặc cân nhắc retry topic |
| Handler không được áp dụng | Factory của listener chưa gắn `setCommonErrorHandler` | Kiểm tra `containerFactory` và bean wiring |
| Lỗi bị bỏ qua và offset vẫn tiến | Listener nuốt exception hoặc recovery được xem là thành công | Xác định rõ semantics commit và recovery |

## 17. Kết luận

`CommonErrorHandler` là abstraction thống nhất để Spring Kafka listener container xử lý exception của record listener và batch listener. Trong đa số trường hợp, `DefaultErrorHandler` cung cấp đủ chức năng retry theo backoff, phân loại exception và recovery. Có thể kết hợp `DeadLetterPublishingRecoverer` để chuyển record không xử lý được sang DLT.

Hãy gắn handler vào đúng listener container factory, phân biệt lỗi tạm thời với lỗi dữ liệu vĩnh viễn, đặt giới hạn retry rõ ràng và hiểu cách recovery ảnh hưởng đến seek/offset commit. Với lỗi deserialize, cấu hình `ErrorHandlingDeserializer`; với batch listener, xác định record lỗi bằng `BatchListenerFailedException` khi có thể. Chính sách lỗi tốt phải giúp hệ thống tiếp tục tiến lên mà vẫn giữ được khả năng truy vết và phát lại dữ liệu lỗi.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka — DefaultErrorHandler](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html#default-eh)
- [Spring for Apache Kafka — Dead-Letter Publishing](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html#dead-letters)
- [Spring for Apache Kafka — ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html#error-handling-deserializer)
