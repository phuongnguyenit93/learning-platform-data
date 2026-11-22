# ConsumerRecordRecoverer

Khi một record đã hết số lần retry hoặc thuộc nhóm exception không nên retry, consumer cần một bước recovery để quyết định dữ liệu sẽ đi đâu tiếp theo. Spring Kafka cung cấp `ConsumerRecordRecoverer` làm callback ở cấp container cho bước này. Recoverer nhận record Kafka gốc cùng exception gây thất bại, nhờ đó ứng dụng có thể lưu record vào kho lỗi, ghi nhận audit hoặc chuyển record sang dead-letter topic (DLT).

`ConsumerRecordRecoverer` thường được truyền vào `DefaultErrorHandler`. Error handler quyết định record có được retry hay không; recoverer chỉ được gọi khi error handler đi đến bước phục hồi. Phân tách hai trách nhiệm này giúp chính sách retry và cách lưu dữ liệu lỗi được cấu hình độc lập.

## 1. Hợp đồng của ConsumerRecordRecoverer

`ConsumerRecordRecoverer` là một functional interface trong package `org.springframework.kafka.listener`. Nó có một phương thức:

```java
void accept(ConsumerRecord<?, ?> record, Exception exception);
```

Hai tham số mang ý nghĩa khác nhau:

- `record`: `ConsumerRecord` gốc do Kafka consumer nhận, gồm topic, partition, offset, timestamp, key, value và headers.
- `exception`: lỗi khiến listener không xử lý được record. Dùng exception này để phân loại, ghi nguyên nhân và hỗ trợ điều tra.

Do nhận `ConsumerRecord` thay vì đối tượng `Message<?>` đã chuyển đổi, recoverer có thể lưu record cùng metadata Kafka gốc trước khi listener xử lý nghiệp vụ. Nếu deserialize thất bại và ứng dụng dùng `ErrorHandlingDeserializer`, `value()` có thể không chứa payload đã chuyển đổi; thông tin lỗi deserialize và dữ liệu thô được giữ trong headers theo cơ chế của deserializer. Recoverer hoặc DLT cần bảo toàn các headers đó nếu quy trình phục hồi cần đọc lại dữ liệu gốc.

Ví dụ, một record có thể được nhận diện bằng bộ ba topic, partition và offset. Key và event ID trong payload cũng hữu ích cho việc truy vết nghiệp vụ. Không nên chỉ ghi `exception.getMessage()` rồi bỏ mất record gốc, vì thông tin đó thường không đủ để điều tra hoặc phục hồi.

## 2. Khi nào recoverer được gọi?

Với record listener sử dụng `DefaultErrorHandler`, luồng xử lý khái quát như sau:

1. Consumer poll record và container gọi listener.
2. Nếu listener ném exception retryable, `DefaultErrorHandler` chờ theo `BackOff` rồi thử lại record.
3. Nếu exception được phân loại là not retryable, error handler bỏ qua retry.
4. Khi retry đã hết hoặc exception không retryable, error handler gọi `ConsumerRecordRecoverer` đã cấu hình.
5. Nếu recovery thành công, container tiếp tục theo chính sách commit/acknowledgment đang cấu hình. Nếu recovery thất bại, exception từ recoverer được xử lý như một lỗi recovery và record có thể được giao lại.

Như vậy, recoverer không phải callback được gọi cho mọi record và cũng không phải nơi đặt logic retry. Nó xử lý record mà error handler đã quyết định cần phục hồi.

## 3. Tạo recoverer tùy chỉnh

Một recoverer tùy chỉnh có thể lưu record cùng exception vào kho lỗi bền vững. Ví dụ dưới đây giả định ứng dụng có `FailureArchive` để ghi dữ liệu vào cơ sở dữ liệu hoặc kho lưu trữ riêng:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;

@Bean
ConsumerRecordRecoverer orderRecordRecoverer(FailureArchive failureArchive) {
    return (record, exception) -> {
        failureArchive.persist(
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                record.value(),
                record.headers(),
                exception);
    };
}
```

`FailureArchive` là thành phần nghiệp vụ minh họa; chữ ký phương thức cần điều chỉnh theo schema lưu trữ thực tế. Điểm quan trọng là thao tác `persist` phải hoàn tất thành công trước khi recoverer trả về. Nếu chỉ khởi chạy một tác vụ bất đồng bộ rồi thoát, container có thể xem recovery đã xong trong khi dữ liệu chưa được lưu bền vững.

Khi ghi kho lỗi, nên lưu tối thiểu:

- Định danh record: topic, partition, offset và timestamp.
- Key, payload gốc và headers cần thiết để điều tra hoặc phát lại.
- Loại exception, thông điệp lỗi và thông tin nguyên nhân gốc có ích.
- Thời điểm recovery, số lần giao lại nếu ứng dụng có theo dõi, cùng trạng thái xử lý.

Payload có thể chứa dữ liệu nhạy cảm. Hãy giới hạn quyền truy cập, thời gian lưu và nội dung log theo chính sách dữ liệu của ứng dụng.

## 4. Kết hợp ConsumerRecordRecoverer với DefaultErrorHandler

Truyền recoverer vào constructor của `DefaultErrorHandler`, sau đó gắn error handler vào listener container factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler orderErrorHandler(
        ConsumerRecordRecoverer orderRecordRecoverer) {

    return new DefaultErrorHandler(
            orderRecordRecoverer,
            new FixedBackOff(1_000L, 2L));
}

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

Trong ví dụ, `FixedBackOff(1_000L, 2L)` đặt khoảng nghỉ một giây và tối đa hai lần retry sau lần xử lý ban đầu. Khi các lần retry không thành công, `orderRecordRecoverer` được gọi. Exception được phân loại not retryable cũng đi tới recoverer mà không chờ các lần retry đó.

Listener sử dụng factory bằng tên bean trong thuộc tính `containerFactory` của `@KafkaListener`. Nếu ứng dụng có nhiều nhóm listener với chính sách khác nhau, có thể tạo factory và recoverer riêng cho từng nhóm.

## 5. Dùng DeadLetterPublishingRecoverer để gửi DLT

Nếu muốn lưu record lỗi trong Kafka để đội vận hành có thể kiểm tra và phát lại, Spring Kafka đã có `DeadLetterPublishingRecoverer`. Class này triển khai `ConsumerRecordRecoverer` và dùng `KafkaTemplate` để publish record lỗi sang DLT.

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
    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}
```

Theo định tuyến mặc định phổ biến, record từ topic gốc được gửi tới topic có hậu tố `.DLT` và giữ partition tương ứng. Cần tạo topic đích với số partition tương thích, cấp quyền ghi cho producer và kiểm tra cấu hình broker trước khi vận hành. Có thể dùng destination resolver tùy chỉnh nếu muốn đặt tên DLT hoặc quy tắc partition khác.

`DeadLetterPublishingRecoverer` có thể bổ sung headers chứa thông tin exception và vị trí record gốc. Khi cần bảo đảm gửi thành công trước khi xem recovery hoàn tất, hãy cấu hình và kiểm tra hành vi chờ kết quả gửi của recoverer theo phiên bản Spring Kafka đang dùng. Không nên tự thay bằng một lệnh `KafkaTemplate.send()` bất đồng bộ rồi trả về ngay mà không quan sát kết quả.

## 6. Recovery thất bại và tính idempotent

Một recoverer cũng có thể gặp lỗi: cơ sở dữ liệu lưu kho lỗi không sẵn sàng, DLT không tồn tại, producer không có quyền ghi hoặc broker đang mất kết nối. Trong tình huống đó, recovery chưa hoàn tất. Hãy để lỗi được truyền ra khỏi recoverer để error handler biết thao tác phục hồi thất bại; không bắt rồi bỏ qua exception.

Khi recovery thất bại, `DefaultErrorHandler` có thể đưa record trở lại luồng giao nhận. Trạng thái BackOff có được đặt lại sau lỗi recovery hay không có thể điều chỉnh bằng cấu hình `resetStateOnRecoveryFailure`; cần xác minh giá trị và hành vi theo phiên bản Spring Kafka của dự án. Dù chọn chính sách nào, ứng dụng cũng phải giám sát lỗi recovery để record không bị mắc kẹt mà không ai nhận biết.

Record có thể được giao lại sau khi listener đã chạy một phần hoặc sau khi recoverer đã thực hiện side effect nhưng chưa hoàn tất. Vì vậy, thao tác lưu kho lỗi hoặc gửi sang hệ thống khác nên idempotent. Có thể dùng topic-partition-offset làm khóa duy nhất cho record gốc, hoặc dùng event ID ổn định nếu nghiệp vụ đã có định danh sự kiện.

## 7. Phân biệt ConsumerRecordRecoverer với các handler khác

Các thành phần xử lý lỗi trong Spring Kafka hoạt động ở những tầng khác nhau:

| Thành phần | Đầu vào chính | Trách nhiệm |
| --- | --- | --- |
| `KafkaListenerErrorHandler` | Message đã chuyển đổi và `ListenerExecutionFailedException` | Xử lý lỗi gắn với một `@KafkaListener`; có thể ném lỗi tiếp cho container |
| `CommonErrorHandler` / `DefaultErrorHandler` | Exception và ngữ cảnh consumer/container | Phân loại retry, BackOff, seek, commit và quyết định khi nào recovery |
| `ConsumerRecordRecoverer` | `ConsumerRecord<?, ?>` và `Exception` | Thực hiện hành động cuối cùng với record đã đến bước recovery |
| `DeadLetterPublishingRecoverer` | Record và exception | Một implementation gửi record lỗi sang DLT bằng `KafkaTemplate` |

Recoverer không nhận `Consumer` hay `Acknowledgment`, vì vậy không nên dùng nó để tự seek hoặc commit offset. Việc điều khiển offset thuộc về error handler và container. Tương tự, recoverer không thay thế `KafkaListenerErrorHandler`: một bên xử lý record ở bước recovery của container, bên kia chạy quanh lời gọi listener.

## 8. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ log exception mà không lưu record | Không đủ dữ liệu để điều tra hoặc phát lại | Lưu record và metadata vào DLT hoặc kho lỗi bền vững |
| Nuốt exception khi lưu kho lỗi thất bại | Container có thể xem recovery thành công ngoài ý muốn | Để lỗi recovery được truyền lên error handler |
| Gửi DLT bất đồng bộ rồi trả về ngay | Offset có thể được xử lý trước khi publish hoàn tất | Xác minh kết quả gửi trước khi kết thúc recovery |
| Không làm recovery idempotent | Record giao lại có thể tạo nhiều bản ghi lỗi | Dùng khóa duy nhất từ vị trí Kafka hoặc event ID |
| Không kiểm tra partition của DLT | Publish có thể thất bại khi partition đích không tồn tại | Tạo số partition tương thích hoặc dùng resolver phù hợp |
| Ghi toàn bộ payload vào log không kiểm soát | Lộ dữ liệu nhạy cảm và tăng dung lượng log | Giới hạn trường lưu, quyền truy cập và thời gian lưu |

## 9. Kiểm thử ConsumerRecordRecoverer

Kiểm thử cần xác nhận cả dữ liệu recoverer nhận được và kết quả lưu trữ sau khi error handler hoàn tất:

1. Tạo listener cố ý ném exception retryable; xác minh listener được thử lại theo BackOff và recoverer chỉ được gọi sau khi hết retry.
2. Tạo exception not retryable; xác minh recoverer được gọi ngay, không chờ các lần retry.
3. Kiểm tra recoverer nhận đúng topic, partition, offset, key, value, headers và exception.
4. Làm kho lỗi hoặc DLT không sẵn sàng; xác minh exception recovery được quan sát và record có thể được giao lại theo cấu hình.
5. Gửi lại cùng một record; xác minh khóa idempotency ngăn việc tạo dữ liệu lỗi trùng.
6. Nếu dùng `DeadLetterPublishingRecoverer`, đọc record ở DLT và kiểm tra payload, partition cùng headers nguồn.

## 10. Checklist triển khai

- [ ] `ConsumerRecordRecoverer` được đăng ký thành bean hoặc được tạo và truyền rõ ràng vào `DefaultErrorHandler`.
- [ ] Recoverer lưu record gốc cùng metadata và nguyên nhân lỗi cần thiết.
- [ ] Thao tác recovery hoàn tất đồng bộ hoặc có cơ chế xác nhận kết quả trước khi trả về.
- [ ] Exception từ thao tác recovery thất bại được truyền lên error handler.
- [ ] Recovery idempotent để chịu được việc record được giao lại.
- [ ] Nếu dùng DLT, topic, partition, ACL và cấu hình publish đã được xác minh.
- [ ] Chính sách BackOff, exception not retryable và recovery được thiết kế thống nhất.
- [ ] Có metric/log cho số record được phục hồi, lỗi recovery và số record vào DLT.
- [ ] Đã kiểm thử cả recovery thành công lẫn recovery thất bại.

`ConsumerRecordRecoverer` là điểm nối giữa quyết định dừng retry và hành động giữ lại dữ liệu lỗi. Khi recoverer lưu được record gốc một cách tin cậy, ứng dụng có thể tiếp tục xử lý luồng sự kiện và vẫn giữ đủ thông tin để điều tra, sửa lỗi hoặc phát lại sau này.
