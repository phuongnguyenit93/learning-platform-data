# KafkaListenerErrorHandler

Trong ứng dụng Spring Kafka, một listener có thể cần chính sách xử lý lỗi riêng: ghi nhận payload gây lỗi, bổ sung thông tin nghiệp vụ vào log, lưu dấu vết phục vụ điều tra hoặc quyết định chuyển lỗi cho cơ chế retry chung. `KafkaListenerErrorHandler` cung cấp một điểm mở rộng ở cấp từng `@KafkaListener` để thực hiện các công việc đó.

Interface này thuộc lớp adapter gọi phương thức listener. Nó nhận message đã được chuyển đổi cùng exception do listener ném ra. Handler có thể xử lý lỗi và kết thúc bình thường, hoặc ném exception tiếp để container áp dụng cơ chế xử lý lỗi ở cấp consumer. Vì vậy, cần hiểu rõ khác biệt giữa hai lựa chọn này trước khi cấu hình.

## 1. Vị trí của KafkaListenerErrorHandler trong luồng xử lý

Với một record listener, luồng xử lý khái quát như sau:

1. Consumer poll record từ Kafka.
2. Spring Kafka chuyển đổi record thành đối số phù hợp với phương thức `@KafkaListener`.
3. Adapter gọi phương thức listener.
4. Nếu listener ném exception, adapter gọi `KafkaListenerErrorHandler` được khai báo cho listener đó.
5. Nếu handler kết thúc bình thường, lỗi được xem là đã được xử lý ở cấp listener. Nếu handler tiếp tục ném exception, exception được chuyển lên container để `CommonErrorHandler` quyết định retry, phục hồi hoặc chuyển sang dead-letter topic (DLT).

`KafkaListenerErrorHandler` không thay thế error handler của container. Nó phù hợp để áp dụng logic gắn với một listener cụ thể, còn container error handler quản lý vòng đời xử lý record, backoff, seek, commit và recovery.

## 2. Khai báo bean và gắn vào @KafkaListener

`KafkaListenerErrorHandler` là một functional interface. Phương thức `handleError` nhận hai đối số:

- `Message<?> message`: message Spring đã chuyển đổi, gồm payload và headers.
- `ListenerExecutionFailedException exception`: exception đại diện cho lỗi xảy ra trong quá trình gọi listener; nguyên nhân gốc thường nằm trong `getCause()`.

Ví dụ sau ghi lại thông tin lỗi nghiệp vụ rồi ném exception trở lại container:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.KafkaListenerErrorHandler;

@Configuration
class ListenerErrorConfiguration {

    @Bean
    KafkaListenerErrorHandler orderListenerErrorHandler(
            FailureAuditService failureAuditService) {

        return (message, exception) -> {
            failureAuditService.recordFailure(
                    message.getPayload(), message.getHeaders(), exception);
            throw exception;
        };
    }
}
```

`FailureAuditService` là service nghiệp vụ của ứng dụng, chịu trách nhiệm ghi dấu vết lỗi. Tên phương thức và kiểu dữ liệu của service cần được điều chỉnh theo mô hình thực tế. Nếu việc ghi audit thất bại, exception từ thao tác đó cũng phải được xử lý theo chính sách đã chọn; không nên giả vờ rằng lỗi gốc đã được phục hồi.

Gắn bean bằng tên phương thức `@Bean` trong thuộc tính `errorHandler`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    private final OrderService orderService;

    OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "${app.kafka.orders-topic}",
            errorHandler = "orderListenerErrorHandler")
    public void onOrder(OrderCreated event) {
        orderService.handle(event);
    }
}
```

Tên trong `errorHandler` phải khớp với tên bean Spring. Nếu không khai báo thuộc tính này, listener sử dụng cơ chế xử lý lỗi của container theo cấu hình factory.

## 3. Hai cách kết thúc handler và ý nghĩa của chúng

Quyết định quan trọng nhất là handler sẽ trả về bình thường hay ném exception tiếp. Hai hành vi này dẫn đến kết quả khác nhau.

### Ghi nhận rồi chuyển lỗi cho container

```java
@Bean
KafkaListenerErrorHandler orderListenerErrorHandler(
        FailureAuditService failureAuditService) {
    return (message, exception) -> {
        failureAuditService.recordFailure(
                message.getPayload(), message.getHeaders(), exception);
        throw exception;
    };
}
```

Handler thực hiện công việc bổ sung rồi ném exception. Container tiếp tục nhận lỗi và áp dụng `CommonErrorHandler`, chẳng hạn chờ theo BackOff, thử lại record hoặc gọi recoverer khi hết retry. Đây là lựa chọn phù hợp khi ứng dụng vẫn muốn giữ chính sách retry và recovery tập trung.

Vì cùng một record có thể được giao lại, thao tác audit có thể chạy nhiều lần. Hãy dùng event ID, topic-partition-offset hoặc khóa nghiệp vụ ổn định để chống ghi trùng. Nếu audit là bắt buộc, chỉ nên ném lại exception sau khi thông tin audit đã được lưu bền vững.

### Lưu lỗi vào nơi phục hồi rồi đánh dấu đã xử lý

```java
@Bean
KafkaListenerErrorHandler archiveAndHandleError(
        FailureArchive failureArchive) {
    return (message, exception) -> {
        failureArchive.persist(message, exception);
        return null;
    };
}
```

Khi handler trả về bình thường, adapter xem exception đã được xử lý. Container không nhận exception đó để retry theo `CommonErrorHandler`. Với listener không có hợp đồng request/reply, giá trị trả về thường không được sử dụng; điều quan trọng là handler đã kết thúc bình thường.

Chỉ chọn cách này nếu `persist` đã hoàn tất việc lưu lỗi vào nơi bền vững hoặc đã thực hiện một hành động phục hồi tương đương. Nếu chỉ ghi log rồi trả về, record có thể được xác nhận theo `AckMode` hiện tại và không được retry, dù nghiệp vụ chưa thành công. Nếu gửi bản tin sang DLT bằng `KafkaTemplate`, cần chờ kết quả gửi thành công trước khi trả về; không khởi chạy gửi bất đồng bộ rồi để listener hoàn tất ngay.

| Kết quả của handler | Hành vi tiếp theo | Khi nào dùng |
| --- | --- | --- |
| Ném exception | Container nhận lỗi và áp dụng error handler cấp container | Muốn retry, backoff hoặc recovery theo chính sách chung |
| Trả về bình thường | Lỗi được xem là đã xử lý ở cấp listener; không retry lỗi đó qua container handler | Đã lưu lỗi bền vững hoặc đã phục hồi thành công |

## 4. Kết hợp với CommonErrorHandler

`CommonErrorHandler` hoạt động ở cấp listener container và được cấu hình trên `ConcurrentKafkaListenerContainerFactory`. Ví dụ dưới đây đặt retry chung cho các listener sử dụng factory này:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler commonKafkaErrorHandler() {
    // Một lần xử lý ban đầu và tối đa hai lần retry, cách nhau một giây.
    return new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler commonKafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(commonKafkaErrorHandler);
    return factory;
}
```

Khi listener ném exception, `KafkaListenerErrorHandler` có thể ghi audit rồi ném lại để `DefaultErrorHandler` xử lý. Nếu listener error handler trả về bình thường, container không có exception đó để thực hiện retry. `FixedBackOff` trong ví dụ cho phép hai lần retry sau lần xử lý đầu tiên; khi retry cạn, cần cấu hình recoverer phù hợp với chính sách dữ liệu, ví dụ `DeadLetterPublishingRecoverer` để xuất record sang DLT.

Không nên tạo hai chính sách retry độc lập mà không xác định thứ tự và số lần thử. Listener-level handler nên tập trung vào chính sách cục bộ; container-level handler nên sở hữu retry, seek, commit và recovery của consumer.

## 5. Dữ liệu có thể quan sát trong handler

Đối tượng `Message<?>` cung cấp payload sau chuyển đổi và các headers mà message converter đưa vào. Đây là nơi thuận tiện để lấy thông tin phục vụ log hoặc audit, chẳng hạn loại sự kiện, khóa nghiệp vụ và metadata Kafka nếu chúng được ánh xạ vào headers.

Không nên giả định payload luôn là một DTO cụ thể. Kiểu payload phụ thuộc cấu hình deserializer, message converter và chữ ký phương thức listener. Nếu listener nhận `Message<OrderCreated>`, payload thường là `OrderCreated`; nếu listener nhận kiểu khác, handler cũng nhận kiểu payload tương ứng. Hãy ghi cả thông tin nhận diện record và exception để có thể truy vết về topic, partition, offset hoặc event ID.

`ListenerExecutionFailedException` cung cấp ngữ cảnh lỗi của listener. Khi cần phân loại lỗi nghiệp vụ, hãy kiểm tra chuỗi `cause` thay vì chỉ dựa vào chuỗi thông báo. Có thể phân biệt lỗi tạm thời như timeout dịch vụ phụ thuộc với lỗi dữ liệu không thể sửa bằng retry, ví dụ payload vi phạm quy tắc nghiệp vụ.

## 6. Các biến thể có Consumer và Acknowledgment

Ngoài `KafkaListenerErrorHandler`, Spring Kafka có các interface mở rộng cho trường hợp cần thêm ngữ cảnh:

- `ConsumerAwareListenerErrorHandler` cung cấp thêm đối tượng `Consumer<?, ?>`.
- `ManualAckListenerErrorHandler` cung cấp thêm `Acknowledgment` khi listener dùng chế độ xác nhận thủ công.

Chỉ sử dụng các biến thể này khi thật sự cần truy cập các đối tượng đó. Consumer không an toàn khi dùng đồng thời từ nhiều thread. Đặc biệt, không tự `seek` trong listener error handler: container không theo dõi được thao tác seek được thực hiện ở tầng adapter và trạng thái offset có thể không nhất quán. Nếu cần điều khiển seek hoặc vị trí đọc lại, hãy triển khai logic đó trong `CommonErrorHandler` ở cấp container.

Tương tự, không gọi `acknowledge()` chỉ để làm cho lỗi biến mất. Với manual acknowledgment, việc xác nhận phải tuân theo thời điểm nghiệp vụ đã hoàn tất và `AckMode` của container. Xác nhận quá sớm có thể khiến record bị bỏ qua sau khi consumer khởi động lại.

## 7. Những lỗi không thuộc phạm vi của listener error handler

`KafkaListenerErrorHandler` được gọi khi adapter xử lý exception phát sinh từ lời gọi listener. Nó không phải điểm bắt mọi lỗi trong toàn bộ vòng đời consumer. Một số tình huống cần cơ chế khác:

| Tình huống | Cơ chế nên xem xét |
| --- | --- |
| Listener ném exception khi xử lý sự kiện | `KafkaListenerErrorHandler` và/hoặc `CommonErrorHandler` |
| Deserialization thất bại trước khi có payload hợp lệ | `ErrorHandlingDeserializer` kết hợp container error handler |
| Cần retry, seek, phục hồi offset hoặc DLT ở cấp consumer | `CommonErrorHandler`, chẳng hạn `DefaultErrorHandler` cùng recoverer |
| Batch listener thất bại tại một phần tử cụ thể | Batch error handling và `BatchListenerFailedException` |
| Lỗi liên quan đến transaction và rollback | Cấu hình transaction của container cùng cơ chế xử lý sau rollback phù hợp |

Với lỗi deserialize, `ErrorHandlingDeserializer` có thể giữ thông tin exception trong headers để cơ chế xử lý ở cấp container phân tích. Đừng trông chờ `KafkaListenerErrorHandler` nhận được một đối tượng nghiệp vụ hợp lệ khi dữ liệu chưa deserialize được.

Với batch listener, một lần gọi có thể chứa nhiều record và cần xác định chính xác record lỗi. Hãy dùng cơ chế batch error handling ở container; listener error handler không thay thế thông tin vị trí lỗi của batch.

## 8. Thiết kế handler an toàn

Một handler dễ vận hành thường tuân theo các nguyên tắc sau:

1. Phân biệt lỗi tạm thời và lỗi không thể retry bằng cách phân loại exception có chủ đích.
2. Nếu muốn retry, ghi nhận ngữ cảnh cần thiết rồi ném exception để container quyết định.
3. Nếu muốn đánh dấu đã xử lý, phải lưu lỗi hoặc kết quả phục hồi bền vững trước khi trả về bình thường.
4. Làm cho thao tác audit, lưu lỗi và gửi DLT có tính idempotent vì chúng có thể được thực hiện lại.
5. Không tự commit offset hoặc seek trong handler cấp listener.
6. Tránh log toàn bộ payload nếu payload chứa dữ liệu nhạy cảm; ưu tiên event ID và metadata đã được chọn lọc.
7. Đo số lần retry, số record được phục hồi, số lỗi chuyển DLT và thời gian xử lý để phát hiện lỗi kéo dài.

## 9. Checklist triển khai và kiểm thử

- [ ] Bean `KafkaListenerErrorHandler` đã được đăng ký trong Spring context.
- [ ] Thuộc tính `errorHandler` của `@KafkaListener` tham chiếu đúng tên bean.
- [ ] Handler phân biệt rõ trường hợp ném exception và trường hợp trả về bình thường.
- [ ] Nếu trả về bình thường, lỗi đã được lưu hoặc phục hồi bền vững.
- [ ] Nếu ném exception, `CommonErrorHandler`, BackOff và recoverer có chính sách rõ ràng.
- [ ] Audit và DLT có cơ chế chống ghi trùng khi record được giao lại.
- [ ] Không thực hiện seek hoặc xác nhận offset tùy tiện trong handler cấp listener.
- [ ] Lỗi deserialize, batch và transaction có cơ chế xử lý ở đúng tầng.

Khi kiểm thử, tạo một listener cố ý ném exception và xác minh handler được gọi với payload, headers và nguyên nhân lỗi mong đợi. Kiểm tra riêng hai nhánh: handler ném lại thì container retry theo BackOff; handler lưu lỗi thành công rồi trả về thì record được xem là đã xử lý theo `AckMode`. Thử thêm trường hợp dịch vụ audit hoặc kho lưu lỗi bị lỗi để chắc chắn ứng dụng không âm thầm xác nhận một record chưa được phục hồi. Cuối cùng, kiểm tra DLT và khả năng chống xử lý trùng khi consumer nhận lại record.
