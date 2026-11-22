# ExceptionClassifier

Khi một `@KafkaListener` ném exception, Spring Kafka cần quyết định có nên thử xử lý record thêm lần nữa hay chuyển thẳng sang bước phục hồi như gửi dead-letter topic (DLT). Retry mọi exception theo cùng một chính sách thường không hiệu quả: timeout tạm thời có thể tự hết, nhưng payload sai định dạng hoặc vi phạm quy tắc nghiệp vụ sẽ tiếp tục thất bại dù thử lại nhiều lần.

`ExceptionClassifier` cung cấp cơ chế phân loại exception thành nhóm có thể retry và không nên retry. Các error handler như `DefaultErrorHandler` sử dụng kết quả phân loại này để quyết định áp dụng backoff/retry hay gọi recoverer. Nắm rõ classifier giúp cấu hình retry đúng với bản chất lỗi, tránh retry vô ích và tránh bỏ qua record có thể phục hồi.

## 1. ExceptionClassifier giải quyết vấn đề gì?

Giả sử consumer xử lý sự kiện thanh toán. Trong lúc xử lý có thể xuất hiện các lỗi khác nhau:

| Exception | Nguyên nhân | Chính sách thường phù hợp |
|---|---|---|
| `SocketTimeoutException` | Dịch vụ phụ thuộc phản hồi chậm tạm thời | Retry có giới hạn và backoff |
| `TransientDataAccessException` | Database tạm thời không truy cập được | Retry có giới hạn |
| `InvalidPaymentException` | Dữ liệu nghiệp vụ không hợp lệ | Không retry; chuyển DLT hoặc xử lý thủ công |
| `IllegalArgumentException` | Payload hoặc tham số không hợp lệ | Thường không retry |
| `DeserializationException` | Không thể chuyển byte thành kiểu dữ liệu mong muốn | Thường không retry cho tới khi dữ liệu hoặc schema được sửa |

Nếu mọi lỗi đều retry, consumer có thể giữ partition quá lâu vì một record không thể xử lý. Nếu mọi lỗi đều không retry, một sự cố mạng ngắn có thể khiến record bị chuyển DLT quá sớm.

Classifier cho phép ứng dụng diễn đạt quy tắc rõ ràng: lỗi tạm thời thì retry; lỗi dữ liệu hoặc lỗi nghiệp vụ không thể tự phục hồi thì đi tới recoverer.

## 2. Classifier, error handler, backoff và recoverer khác nhau thế nào?

Các thành phần xử lý lỗi có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| `ExceptionClassifier` | Phân loại exception là retryable hay non-retryable |
| `DefaultErrorHandler` | Điều phối xử lý lỗi của record listener, retry và phục hồi record |
| `BackOff` | Xác định thời gian chờ và số lần thử lại |
| `ConsumerRecordRecoverer` | Xử lý record sau khi retry đã hết hoặc exception không retry được |
| `DeadLetterPublishingRecoverer` | Một recoverer phổ biến, publish record lỗi sang DLT |

Classifier không tự gọi listener lần nữa và cũng không tự gửi record tới DLT. Nó chỉ cung cấp quyết định phân loại cho error handler. Error handler mới kết hợp quyết định đó với backoff và recoverer để thực hiện hành động.

```text
@KafkaListener xử lý record
          |
          +---- thành công ----------------------> tiếp tục / commit theo AckMode
          |
          +---- ném exception
                    |
                    v
             ExceptionClassifier
                    |
             +------+------+
             |             |
         Retryable     Non-retryable
             |             |
             v             v
          BackOff       Recoverer
             |             |
          Seek/retry       DLT hoặc xử lý khác
             |
       Hết retry mà vẫn lỗi
             |
             v
          Recoverer
```

## 3. Cách phân loại exception trong Spring Kafka

Trong Spring Kafka, `org.springframework.kafka.listener.ExceptionClassifier` cung cấp logic phân loại được các error handler sử dụng. `DefaultErrorHandler` có chính sách mặc định: phần lớn exception được xem là retryable, trong khi một số lỗi cho thấy record không thể xử lý bằng cách thử lại được xem là fatal/non-retryable. Các phương thức như `addRetryableExceptions()` và `addNotRetryableExceptions()` được kế thừa để cấu hình chính sách.

Các exception mặc định thường được xếp vào nhóm fatal gồm:

- `DeserializationException`.
- `MessageConversionException`.
- `ConversionException`.
- `MethodArgumentResolutionException`.
- `NoSuchMethodException`.
- `ClassCastException`.

Danh sách mặc định có thể thay đổi theo phiên bản Spring Kafka. Hãy kiểm tra Javadoc/tài liệu của phiên bản dự án khi cần phụ thuộc vào danh sách cụ thể. Có thể bổ sung hoặc thay đổi classification theo quy tắc của ứng dụng.

### Đánh dấu exception không retry

Ví dụ, dữ liệu đơn hàng không hợp lệ không thể trở nên hợp lệ chỉ bằng cách chạy listener lần nữa:

```java
public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Giả sử `recoverer` đã được tạo, thêm exception này vào nhóm non-retryable của handler:

```java
import java.net.SocketTimeoutException;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

var errorHandler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
);

errorHandler.addNotRetryableExceptions(
        InvalidOrderException.class,
        IllegalArgumentException.class
);
```

Nếu listener ném `InvalidOrderException`, error handler bỏ qua các lần retry thông thường và chuyển record tới recoverer. Với lỗi khác chưa được phân loại non-retryable, handler tiếp tục áp dụng chính sách mặc định và backoff.

### Đánh dấu exception có thể retry

Một số lỗi nghiệp vụ hoặc lỗi hạ tầng có thể được ứng dụng xác định rõ là tạm thời:

```java
public class InventoryTemporarilyUnavailableException extends RuntimeException {

    public InventoryTemporarilyUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đăng ký exception vào nhóm retryable của cùng handler:

```java
errorHandler.addRetryableExceptions(
        InventoryTemporarilyUnavailableException.class,
        SocketTimeoutException.class
);
```

Điều này hữu ích khi một exception thuộc danh sách mặc định fatal nhưng ứng dụng có lý do cụ thể để thử lại, hoặc khi muốn ghi rõ chính sách cho các lỗi tạm thời quan trọng. Không nên đánh dấu retryable chỉ vì muốn tránh DLT; cần xác định lỗi có khả năng tự phục hồi và đặt giới hạn retry phù hợp.

## 4. Cấu hình đầy đủ với DefaultErrorHandler và DLT

Ví dụ sau dùng `DeadLetterPublishingRecoverer` để gửi record sang DLT khi lỗi non-retryable hoặc đã hết số lần retry:

```java
import java.net.SocketTimeoutException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class KafkaErrorHandlingConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 3L);
        var handler = new DefaultErrorHandler(recoverer, backOff);

        handler.addRetryableExceptions(
                InventoryTemporarilyUnavailableException.class,
                SocketTimeoutException.class
        );
        handler.addNotRetryableExceptions(
                InvalidOrderException.class,
                IllegalArgumentException.class
        );

        return handler;
    }
}
```

Gắn error handler vào listener container factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Configuration
class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler kafkaErrorHandler) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);
        return factory;
    }
}
```

Listener sử dụng factory này:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection",
            containerFactory = "kafkaListenerContainerFactory"
    )
    public void consume(OrderEvent event) {
        orderService.process(event);
    }
}
```

Ví dụ giả định ứng dụng đã có `OrderEvent`, `orderService`, `InvalidOrderException`, `InventoryTemporarilyUnavailableException` và các bean serializer/deserializer tương ứng. `FixedBackOff(1_000L, 3L)` chờ một giây giữa các lần retry và cho phép tối đa ba lần retry sau lần xử lý đầu tiên. Nếu vẫn thất bại, recoverer được gọi.

Nếu ứng dụng dùng factory tùy chỉnh cho một listener, hãy gắn `CommonErrorHandler` vào đúng factory mà listener sử dụng. Tạo bean `DefaultErrorHandler` mà container không tham chiếu tới sẽ không thay đổi cách listener xử lý lỗi.

## 5. ExceptionClassifier xử lý exception lồng nhau

Spring Kafka có thể bọc exception từ listener trong exception khác, ví dụ `ListenerExecutionFailedException`. Exception gốc có thể nằm trong chuỗi `getCause()`:

```text
ListenerExecutionFailedException
  └── InventoryTemporarilyUnavailableException
        └── SocketTimeoutException
```

Nếu quy tắc phân loại cần xét cả cause chain, có thể cấu hình classifier duyệt causes:

```java
errorHandler.setTraverseCauses(true);
```

Khi bật traversal, classifier có thể tìm exception được đăng ký trong chuỗi nguyên nhân thay vì chỉ xét exception ngoài cùng. Hãy kiểm tra hành vi mặc định và API của phiên bản Spring Kafka đang dùng; cấu hình tường minh giúp tránh phụ thuộc vào giả định về wrapping.

Việc phân loại theo cause đặc biệt hữu ích khi thư viện database hoặc HTTP client bọc exception gốc trong exception nghiệp vụ. Tuy nhiên, không nên phân loại một cause chung quá rộng nếu cùng loại cause có thể xuất hiện trong cả lỗi tạm thời lẫn lỗi không thể phục hồi.

## 6. Phân loại theo kiểu exception và kế thừa

Quy tắc classification có thể áp dụng cho một lớp exception và các lớp con của nó theo cơ chế phân loại exception của Spring. Ví dụ, nếu `InvalidOrderException` là lớp cha của nhiều lỗi dữ liệu, có thể đăng ký lớp cha để áp dụng cùng chính sách cho toàn bộ nhóm.

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

class MissingOrderIdException extends InvalidOrderException {
    public MissingOrderIdException() {
        super("orderId is required");
    }
}
```

Đăng ký `InvalidOrderException.class` vào nhóm non-retryable sẽ áp dụng cho cả `MissingOrderIdException` theo quy tắc phân loại lớp cha/lớp con. Cách này giúp chính sách ngắn gọn khi có một họ exception nghiệp vụ.

Khi các lớp exception có quan hệ kế thừa phức tạp, hãy kiểm tra test classification để xác nhận lớp nào được ưu tiên. Tránh đăng ký cùng một lớp hoặc các lớp cha/con vào hai nhóm trái ngược nhau vì kết quả có thể khó đọc và dễ thay đổi khi refactor.

## 7. Phân loại và số lần retry là hai quyết định riêng

Classifier chỉ trả lời exception có được retry hay không. Backoff quyết định retry bao nhiêu lần và chờ bao lâu.

Ví dụ:

```java
import java.net.SocketTimeoutException;

// Giả sử recoverer đã được tạo và được truyền vào handler.
var backOff = new FixedBackOff(2_000L, 4L);
var handler = new DefaultErrorHandler(recoverer, backOff);

handler.addNotRetryableExceptions(InvalidOrderException.class);
handler.addRetryableExceptions(SocketTimeoutException.class);
```

Với `SocketTimeoutException`, handler có thể thực hiện tối đa bốn lần retry, chờ hai giây giữa các lần. Với `InvalidOrderException`, handler không chờ backoff và gọi recoverer ngay. Một exception retryable vẫn có thể được recover sau khi hết số lần thử.

| Classification | BackOff | Kết quả |
|---|---|---|
| Retryable | Còn lần thử | Chờ rồi retry theo cơ chế error handler |
| Retryable | Hết lần thử | Gọi recoverer |
| Non-retryable | Không áp dụng retry | Gọi recoverer ngay |

Chọn backoff theo thời gian phục hồi dự kiến của dependency. Retry quá dày có thể làm hệ thống đang quá tải càng quá tải hơn; retry quá lâu có thể giữ partition và tăng consumer lag.

## 8. ExceptionClassifier và deserialization errors

Deserialization xảy ra trước khi listener nhận được payload. Nếu consumer không thể deserialize byte, phương thức `@KafkaListener` có thể không được gọi. Để Spring Kafka error handler xử lý loại lỗi này, thường cần dùng `ErrorHandlingDeserializer` bọc deserializer thực tế.

Ví dụ consumer JSON:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderEvent
        spring.json.trusted.packages: com.example.events
```

`ErrorHandlingDeserializer` lưu thông tin lỗi deserialization vào header để listener container/error handler có thể nhận diện và xử lý record lỗi. `DeserializationException` thường thuộc nhóm fatal mặc định vì retry cùng byte và cùng deserializer không làm payload hợp lệ trở lại.

Nếu lỗi đến từ schema hoặc phiên bản producer/consumer không tương thích, cần sửa hợp đồng hoặc cấu hình serializer/deserializer trước khi phát lại record. Có thể gửi record lỗi sang DLT để điều tra và xử lý sau.

## 9. ExceptionClassifier với retry topic

`DefaultErrorHandler` và `@RetryableTopic` là hai cơ chế điều phối retry khác nhau. Classification được cấu hình trên `DefaultErrorHandler` không tự động trở thành quy tắc cho retry topic.

Với non-blocking retry, có thể khai báo exception được retry và exception bị loại trừ ngay trên annotation:

```java
import java.net.SocketTimeoutException;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
class PaymentListener {

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(delay = 1_000, multiplier = 2.0),
            include = {SocketTimeoutException.class},
            exclude = {InvalidPaymentException.class}
    )
    @KafkaListener(topics = "payments.events", groupId = "payment-projection")
    public void consume(PaymentEvent event) {
        paymentService.process(event);
    }
}
```

Ví dụ giả định `PaymentEvent`, `paymentService` và `InvalidPaymentException` đã được khai báo trong ứng dụng. Nó minh họa chính sách retry topic: timeout được đưa qua các retry topic, còn lỗi dữ liệu nghiệp vụ bị loại khỏi retry. Khi dùng `@RetryableTopic`, hãy kiểm tra phiên bản Spring Kafka, tên retry/DLT topic, tổng số attempts và các giới hạn về batch/transaction để cấu hình phù hợp.

## 10. Classification trong listener có transaction

Khi container dùng Kafka transaction, exception từ listener có thể làm transaction rollback. Cơ chế xử lý sau rollback thường được điều phối bởi `AfterRollbackProcessor` hoặc `DefaultAfterRollbackProcessor`, thay vì áp dụng nguyên xi luồng xử lý của `DefaultErrorHandler` trên container không transaction.

Các processor xử lý lỗi sau rollback cũng có cơ chế phân loại exception trong hierarchy Spring Kafka. Có thể áp dụng quy tắc retryable/non-retryable tương tự, nhưng phải cấu hình trên đúng processor mà container sử dụng. Không nên nghĩ rằng cấu hình trên một `DefaultErrorHandler` tự động điều khiển mọi transaction rollback.

Khi dùng transaction, cần xác định rõ:

- Exception nào khiến transaction rollback.
- Bao nhiêu lần thử lại trước khi recover.
- Recoverer có publish DLT trong transaction phù hợp hay không.
- Offset được commit cùng transaction nào.
- Side effect ngoài Kafka có cơ chế phối hợp riêng hay cần idempotency.

Kafka transaction không tự động bao gồm database hoặc HTTP service. Nếu listener cập nhật database, hãy dùng mô hình inbox/outbox hoặc cơ chế phối hợp transaction phù hợp với kiến trúc.

## 11. Kiểm thử quy tắc ExceptionClassifier

Classification nên được kiểm thử độc lập với logic nghiệp vụ để tránh lỗi cấu hình khiến record bị retry hoặc bị bỏ qua sai cách. Có thể tạo handler trong test và xác nhận kết quả classification bằng API tương ứng của phiên bản Spring Kafka.

Ngoài kiểm thử unit, nên có integration test với embedded Kafka hoặc broker test để xác nhận hành vi thực tế:

1. Exception retryable làm listener được gọi lại theo số lần đã cấu hình.
2. Exception non-retryable không chờ backoff và được recover theo chính sách.
3. Exception lồng trong cause chain được phân loại như mong muốn khi bật traversal.
4. Recoverer publish DLT thành công trước khi offset nguồn được xác nhận.
5. Lỗi publish DLT không làm record nguồn bị đánh dấu recovered sai.
6. Deserialization error được chuyển tới error handler khi dùng `ErrorHandlingDeserializer`.
7. Consumer tiếp tục xử lý record tiếp theo sau khi record lỗi đã được recover.

Khi test retry, ghi nhận số lần listener được gọi và thời gian chờ thực tế. Tránh chỉ kiểm tra log vì log không chứng minh offset đã commit hoặc DLT đã nhận record.

## 12. Quy trình thiết kế exception classification

Một quy trình thực tế có thể thực hiện theo các bước:

1. Liệt kê exception từ listener, serializer/deserializer, database và dịch vụ ngoài.
2. Xác định lỗi nào có thể tự phục hồi khi chờ hoặc thử lại.
3. Đánh dấu lỗi dữ liệu, lỗi nghiệp vụ không thể phục hồi và lỗi cấu hình thành non-retryable.
4. Xác định các exception bị bọc trong cause chain và cấu hình traversal nếu cần.
5. Chọn backoff, số lần retry và giới hạn tổng thời gian phù hợp.
6. Cấu hình recoverer/DLT để lưu record không thể xử lý và metadata phục vụ điều tra.
7. Kiểm thử retry, recovery, commit và hành vi khi DLT publish thất bại.
8. Theo dõi retry rate, DLT rate, consumer lag và lỗi theo loại exception trong production.

Không nên phân loại dựa trên tên exception một cách máy móc. Cùng một loại exception tổng quát có thể đại diện cho nhiều nguyên nhân; hãy ưu tiên exception nghiệp vụ cụ thể hoặc phân tích cause chain có kiểm soát.

## 13. Những nhầm lẫn thường gặp

1. **Cho rằng ExceptionClassifier tự thực hiện retry.** Classifier chỉ quyết định retryable/non-retryable; error handler điều phối backoff và recoverer.
2. **Cho rằng mọi exception đều nên retry.** Lỗi dữ liệu hoặc lỗi cấu hình không tự hết khi thử lại.
3. **Cho rằng non-retryable nghĩa là record bị bỏ ngay.** Error handler vẫn có thể gọi recoverer, ví dụ publish record sang DLT.
4. **Nhầm classification với số lần retry.** Số lần và thời gian chờ do `BackOff` quyết định.
5. **Không xét exception lồng nhau.** Listener container hoặc thư viện có thể bọc exception gốc; classifier cần được cấu hình phù hợp với cause chain.
6. **Cho rằng cấu hình DefaultErrorHandler áp dụng cho retry topic.** `@RetryableTopic` có cơ chế include/exclude riêng.
7. **Cho rằng cấu hình error handler thông thường tự điều khiển transaction rollback.** Container transactional sử dụng after-rollback processor theo cấu hình.
8. **Không dùng ErrorHandlingDeserializer khi muốn xử lý lỗi deserialize qua container.** Lỗi xảy ra trước listener và cần được chuyển thành metadata lỗi để error handler xử lý.
9. **Cho rằng publish DLT luôn thành công.** Cần quan sát kết quả gửi và chỉ xác nhận recovery khi recoverer hoàn tất đúng cách.

ExceptionClassifier giúp Spring Kafka áp dụng chính sách lỗi dựa trên bản chất exception. Hãy tách rõ classification, backoff và recovery; retry có giới hạn đối với lỗi tạm thời, chuyển lỗi không thể phục hồi sang DLT và kiểm thử cả offset commit. Cách phân loại đúng giúp consumer tránh bị mắc kẹt ở một record lỗi, đồng thời không bỏ qua những sự cố có thể tự phục hồi.
