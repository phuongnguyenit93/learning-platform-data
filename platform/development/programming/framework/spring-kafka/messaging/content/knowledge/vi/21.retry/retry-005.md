# Bỏ qua exception không nên retry

Retry giúp consumer vượt qua lỗi tạm thời, chẳng hạn một dịch vụ phụ thuộc đang timeout hoặc cơ sở dữ liệu vừa mất kết nối. Tuy nhiên, thử lại một sự kiện có payload sai, thiếu dữ liệu bắt buộc hoặc không được hỗ trợ thường không làm tình hình tốt hơn. Mỗi lần retry chỉ kéo dài thời gian xử lý, chiếm tài nguyên consumer và có thể làm các record hợp lệ phía sau bị chậm.

Trong Spring Kafka, có thể phân loại exception để `DefaultErrorHandler` bỏ qua bước retry đối với những lỗi đã biết là không thể tự phục hồi. Bỏ qua retry không đồng nghĩa vứt bỏ record: error handler vẫn chuyển record tới recovery path đã cấu hình, chẳng hạn ghi log hoặc gửi sang dead-letter topic (DLT).

## 1. Phân biệt lỗi tạm thời và lỗi không nên retry

Quyết định retry phải dựa trên nguyên nhân nghiệp vụ và khả năng lỗi tự biến mất, không chỉ dựa vào việc exception là checked hay unchecked.

| Nhóm lỗi | Ví dụ | Hướng xử lý thường phù hợp |
| --- | --- | --- |
| Tạm thời (transient) | Timeout gọi dịch vụ đối tác, kết nối cơ sở dữ liệu gián đoạn, HTTP 503, lock tạm thời | Retry có giới hạn, có backoff; sau đó recovery nếu vẫn thất bại |
| Không thể phục hồi bằng retry (permanent) | Payload thiếu trường bắt buộc, event type không được hỗ trợ, phiên bản schema không thể đọc, vi phạm quy tắc dữ liệu cố định | Không retry; ghi nhận nguyên nhân và chuyển DLT hoặc kho lỗi |
| Phụ thuộc trạng thái nghiệp vụ | Đơn hàng chưa đủ điều kiện vì một sự kiện khác chưa đến, tài nguyên đang tạm khóa | Xác định lỗi có thể tự hết hạn hay cần chờ sự kiện khác; chọn retry có giới hạn hoặc quy trình bù phù hợp |

Ví dụ, `InvalidOrderException` có thể đại diện cho dữ liệu đơn hàng không hợp lệ và không nên retry. Ngược lại, `PartnerServiceUnavailableException` có thể đại diện cho dịch vụ đối tác tạm thời không sẵn sàng và nên được retry. Hãy tạo exception theo ý nghĩa nghiệp vụ rõ ràng để chính sách không phụ thuộc vào một loại exception quá chung như `RuntimeException`.

## 2. Cách DefaultErrorHandler quyết định retry

`DefaultErrorHandler` là implementation của `CommonErrorHandler` thường dùng cho record listener. Khi listener ném exception, handler phân loại exception rồi áp dụng `BackOff` hoặc gọi recoverer:

1. Nếu exception được phân loại là retryable, handler chờ theo `BackOff` và giao lại record theo chính sách retry.
2. Nếu exception được phân loại là not retryable, handler bỏ qua các lần retry và gọi recoverer ngay trong lần thất bại đó.
3. Khi retryable exception đã hết số lần thử, recoverer cũng được gọi để xử lý record không thể tiếp tục.

Các phiên bản Spring Kafka hiện đại đã cấu hình sẵn một số exception kỹ thuật là fatal, nghĩa là không retry theo mặc định. Nhóm này thường gồm `DeserializationException`, `MessageConversionException`, `ConversionException`, `MethodArgumentResolutionException`, `NoSuchMethodException` và `ClassCastException`. Danh sách mặc định có thể thay đổi theo phiên bản; hãy đối chiếu tài liệu của dependency đang dùng trước khi dựa vào nó.

Ứng dụng có thể bổ sung exception nghiệp vụ vào danh sách not retryable. Đây là cách thích hợp khi đã xác định loại lỗi đó không thể được khắc phục bằng việc giao lại cùng một record.

## 3. Khai báo exception không được retry

`DefaultErrorHandler` cung cấp `addNotRetryableExceptions(...)` để đánh dấu một hoặc nhiều loại exception là không retryable. Ví dụ sau gửi record lỗi sang DLT ngay khi gặp một trong các lỗi nghiệp vụ đã khai báo:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedEventVersionException.class);

    return handler;
}
```

Trong ví dụ:

- `InvalidOrderException` và `UnsupportedEventVersionException` được đưa thẳng tới recoverer, không chờ một giây và không thử lại hai lần.
- Các exception retryable khác dùng `FixedBackOff(1_000L, 2L)`: chờ một giây giữa các lần thử và tối đa hai lần retry sau lần xử lý ban đầu.
- `DeadLetterPublishingRecoverer` dùng `KafkaTemplate` để xuất record không phục hồi được sang DLT theo quy tắc định tuyến của recoverer.

Đăng ký handler trên listener container factory để các listener dùng factory đó áp dụng cùng chính sách:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    return factory;
}
```

Listener sử dụng factory đó qua thuộc tính `containerFactory` của `@KafkaListener`. Tên bean, kiểu key/value và cấu hình deserializer phải khớp với ứng dụng thực tế.

## 4. Không retry không có nghĩa là bỏ record âm thầm

Phân loại not retryable chỉ quyết định không chạy lại listener theo `BackOff`. Sau đó, recoverer chịu trách nhiệm xử lý record thất bại. Có thể chọn một trong các cách sau:

- Gửi record và metadata lỗi sang DLT để đội vận hành kiểm tra, sửa dữ liệu hoặc phát lại sau khi khắc phục.
- Ghi vào một kho lỗi bền vững nếu ứng dụng có quy trình quản lý và phục hồi riêng.
- Dùng logging recoverer cho trường hợp record chỉ cần được ghi nhận theo chính sách đã chấp nhận; cần bảo đảm log đủ thông tin để truy vết.

Trong hệ thống nghiệp vụ, DLT thường hữu ích hơn việc chỉ ghi log vì nó giữ lại record để điều tra và xử lý sau. Cần bảo đảm topic đích tồn tại, cấu hình số partition phù hợp với cách định tuyến, và quyền ghi của producer được cấp. Có thể bổ sung headers chứa exception class, message, topic, partition, offset và timestamp để việc điều tra thuận tiện hơn.

Khi recoverer gửi DLT thành công, error handler xem record đã được phục hồi và container tiếp tục theo chính sách commit/acknowledgment đang cấu hình. Nếu việc gửi DLT thất bại, recovery chưa hoàn tất; phải theo dõi lỗi này và thiết kế chính sách giao lại phù hợp. Không được xem một lần gọi recoverer là bảo đảm record đã được lưu an toàn.

## 5. Chọn exception cụ thể và xử lý exception bị bọc

Nên khai báo các loại exception hẹp, thể hiện rõ lỗi không thể retry. Tránh cấu hình các lớp rộng như `Exception`, `RuntimeException` hoặc `IllegalStateException` nếu chúng cũng có thể đại diện cho lỗi tạm thời trong ứng dụng.

Ví dụ, nếu `IllegalArgumentException` được dùng cả cho dữ liệu đầu vào sai lẫn tham số nội bộ do cấu hình sai, đánh dấu toàn bộ loại này là not retryable có thể che khuất một lỗi cần được sửa ở code. Một exception nghiệp vụ riêng giúp chính sách rõ ràng hơn:

```java
public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Classifier thường xét kiểu exception theo quan hệ kế thừa. Tuy nhiên, listener, adapter hoặc lớp tích hợp có thể bọc lỗi gốc trong exception khác. Khi đó, cần kiểm tra exception thực tế được chuyển tới error handler và cách phiên bản Spring Kafka đang dùng xét chuỗi `cause`. Đừng giả định một exception lồng bên trong luôn được phân loại giống như khi nó được ném trực tiếp; hãy kiểm thử cả trường hợp có wrapper.

Nếu có một exception mặc định bị xem là fatal nhưng trong nghiệp vụ cụ thể lại có thể retry, `DefaultErrorHandler` cũng hỗ trợ `addRetryableExceptions(...)` để bổ sung phân loại retryable. Chỉ dùng khi đã xác nhận lỗi đó có khả năng tự phục hồi và có giới hạn retry phù hợp.

## 6. Quan hệ với KafkaListenerErrorHandler

`KafkaListenerErrorHandler` chạy ở cấp adapter của một `@KafkaListener`, còn `DefaultErrorHandler` quản lý lỗi ở cấp container. Nếu listener error handler bắt exception rồi trả về bình thường, adapter xem lỗi đã được xử lý và container không nhận exception đó để phân loại retry. Vì vậy:

- Muốn `DefaultErrorHandler` bỏ qua retry và gọi recoverer cho exception not retryable, listener error handler phải ném exception tiếp.
- Chỉ trả về bình thường khi listener error handler đã thực hiện phục hồi bền vững và chủ động chấp nhận không retry record đó.

Không nên nuốt exception chỉ để tránh retry. Cách đó có thể khiến offset được xác nhận trong khi sự kiện chưa được xử lý hoặc lưu vào nơi phục hồi nào.

## 7. Với non-blocking retry bằng retry topic

Nếu ứng dụng dùng cơ chế retry topic (`@RetryableTopic`), cần cấu hình danh sách exception loại trừ phù hợp với phiên bản Spring Kafka. Annotation hỗ trợ thuộc tính `exclude` trong các phiên bản có retry-topic feature tương ứng:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000L),
        exclude = {
                InvalidOrderException.class,
                UnsupportedEventVersionException.class
        })
@KafkaListener(topics = "${app.kafka.orders-topic}")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

Các exception trong `exclude` không được chuyển qua chuỗi retry topic. Hãy kiểm tra phiên bản Spring Kafka và chính sách `include`/`exclude` đang áp dụng, vì retry topic có cơ chế phân loại riêng với `DefaultErrorHandler`. Không cấu hình cùng một luồng theo hai chính sách retry mâu thuẫn.

## 8. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Retry lỗi validation không thể thay đổi | Tốn thời gian, làm backlog tăng | Đánh dấu exception nghiệp vụ là not retryable và chuyển DLT |
| Đánh dấu `RuntimeException` là not retryable | Các lỗi tạm thời bị bỏ qua retry | Dùng exception riêng cho lỗi vĩnh viễn |
| Nghĩ rằng not retryable đồng nghĩa tự động xóa record | Không có nơi lưu record để điều tra hoặc phục hồi | Cấu hình recoverer rõ ràng, thường là DLT |
| Listener error handler bắt lỗi rồi trả về bình thường | Container không thấy lỗi để phân loại | Ném exception tiếp nếu muốn container thực hiện recovery |
| Không kiểm tra exception wrapper | Phân loại không khớp với lỗi thực tế | Ghi nhận kiểu exception và cause; kiểm thử cả exception bị bọc |
| DLT không ghi được nhưng vẫn xem record là an toàn | Có nguy cơ mất đường phục hồi | Giám sát lỗi recoverer và xác minh hành vi khi recovery thất bại |

## 9. Kiểm thử chính sách not retryable

Kiểm thử nên xác minh số lần listener được gọi và nơi record kết thúc, thay vì chỉ kiểm tra exception đã xuất hiện trong log.

1. Gửi một record gây `InvalidOrderException`; xác minh listener chỉ được gọi một lần và record được chuyển tới DLT theo cấu hình.
2. Gửi một record gây `PartnerServiceUnavailableException`; xác minh listener được thử lại theo số lần và khoảng chờ của `BackOff`.
3. Gửi exception nghiệp vụ nằm bên trong một wrapper; xác minh classifier xử lý đúng theo cấu hình cause traversal của phiên bản đang dùng.
4. Làm DLT producer thất bại; xác minh lỗi recovery được quan sát và record không bị đánh dấu phục hồi thành công ngoài ý muốn.
5. Kiểm tra headers và metadata tại DLT để có thể xác định topic, partition, offset và nguyên nhân gốc.

## 10. Checklist triển khai

- [ ] Đã phân loại lỗi theo khả năng tự phục hồi, không chỉ theo checked/unchecked exception.
- [ ] Exception nghiệp vụ không retry có kiểu riêng và tên thể hiện đúng nguyên nhân.
- [ ] `DefaultErrorHandler.addNotRetryableExceptions(...)` được cấu hình trên handler dùng bởi listener container.
- [ ] BackOff chỉ áp dụng cho nhóm lỗi cần retry và có giới hạn phù hợp.
- [ ] Recoverer có hành vi rõ ràng; DLT tồn tại và có quyền ghi cần thiết nếu được sử dụng.
- [ ] Đã kiểm tra cách classifier xử lý exception kế thừa và exception bị bọc.
- [ ] `KafkaListenerErrorHandler` không vô tình nuốt exception cần container xử lý.
- [ ] Với retry topic, `exclude` được cấu hình riêng và tương thích với phiên bản Spring Kafka.
- [ ] Đã kiểm thử số lần gọi listener, kết quả recovery, headers DLT và lỗi khi gửi DLT thất bại.

Một chính sách tốt giúp lỗi tạm thời có cơ hội tự phục hồi, còn lỗi dữ liệu không thể sửa được nhanh chóng đi vào quy trình xử lý riêng. Nhờ vậy consumer không lặp vô ích trên cùng một record và các sự kiện hợp lệ tiếp theo có thể tiếp tục được xử lý.
