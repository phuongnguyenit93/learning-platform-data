# Lọc record trước listener

Không phải record nào được consumer poll từ Kafka cũng cần đi vào logic nghiệp vụ. Ví dụ, một ứng dụng có thể chỉ xử lý sự kiện đơn hàng dành cho tenant hiện tại, bỏ qua sự kiện kiểm thử hoặc loại một loại thông báo mà listener không quan tâm. Spring Kafka cho phép lọc record trước khi gọi `@KafkaListener` bằng `RecordFilterStrategy`.

Filter chạy trong luồng xử lý của listener container. Nếu chiến lược đánh dấu record cần loại bỏ, adapter lọc bỏ record và không gọi phương thức listener cho record đó. Vì vậy, quyết định filter là quyết định kết thúc xử lý đối với record ở consumer này; nó không tạo retry hoặc tự động chuyển record sang dead-letter topic (DLT).

## 1. RecordFilterStrategy hoạt động thế nào?

`RecordFilterStrategy<K, V>` là interface của Spring Kafka dùng để quyết định một `ConsumerRecord` có bị loại hay không. Phương thức `filter()` trả về boolean với ý nghĩa:

- `true`: loại record, listener không nhận record này.
- `false`: giữ record, tiếp tục gọi listener như bình thường.

Spring Kafka bọc listener bằng filtering adapter để gọi chiến lược trước khi chuyển record cho listener. Ứng dụng không cần tự poll consumer hoặc tự quản lý offset chỉ để lọc record.

Ví dụ, listener chỉ xử lý đơn hàng thật và bỏ qua sự kiện được đánh dấu là dữ liệu kiểm thử:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.RecordFilterStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFilterConfiguration {

    @Bean
    RecordFilterStrategy<String, OrderCreated> testOrderFilter() {
        return record -> {
            OrderCreated event = record.value();
            return event != null && event.testEvent();
        };
    }
}
```

Trong ví dụ, record có payload null vẫn được giữ lại để ứng dụng quyết định cách xử lý, còn record có `testEvent()` bằng `true` bị loại. Tên và cấu trúc `OrderCreated` là ví dụ; hãy thay bằng event contract của ứng dụng.

## 2. Cấu hình filter trên listener container factory

Có thể gắn một `RecordFilterStrategy` mặc định cho tất cả listener dùng cùng factory bằng `setRecordFilterStrategy()`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.RecordFilterStrategy;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        RecordFilterStrategy<String, OrderCreated> testOrderFilter) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setRecordFilterStrategy(testOrderFilter);
    factory.setAckDiscarded(true);
    return factory;
}
```

`setAckDiscarded(true)` yêu cầu filtering adapter xác nhận record bị loại khi có `Acknowledgment` phù hợp. Giá trị mặc định của `ackDiscarded` là `false`. Hãy chọn giá trị này cùng với `AckMode` và transaction của container; đặc biệt kiểm thử cách offset được commit khi listener dùng manual acknowledgment. Nếu record bị loại cần được xem là đã xử lý, phải bảo đảm cấu hình acknowledgment thực sự đưa offset của record đó vào tiến trình commit.

Listener chỉ cần khai báo factory:

```java
@KafkaListener(
        topics = "${app.kafka.orders-topic}",
        containerFactory = "orderKafkaListenerContainerFactory")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

Factory có filter chung phù hợp khi các listener trong nhóm có cùng quy tắc. Nếu mỗi listener có tiêu chí riêng, có thể chọn filter ở cấp annotation.

## 3. Chọn filter riêng cho từng @KafkaListener

Từ Spring Kafka 2.8, `@KafkaListener` có thuộc tính `filter` để chỉ định tên bean `RecordFilterStrategy` cho listener đó. Cách này hữu ích khi nhiều listener dùng chung một factory nhưng cần quy tắc lọc khác nhau.

```java
@Bean
RecordFilterStrategy<String, OrderCreated> publicOrderFilter() {
    return record -> {
        OrderCreated event = record.value();
        return event == null || event.internalOnly();
    };
}

@KafkaListener(
        id = "public-order-listener",
        topics = "${app.kafka.orders-topic}",
        filter = "publicOrderFilter")
public void onPublicOrder(OrderCreated event) {
    orderService.publishToPublicView(event);
}
```

Trong ví dụ này, filter `publicOrderFilter` loại payload null và sự kiện chỉ dùng nội bộ. Tên bean trong `filter` phải khớp với bean Spring đã đăng ký. Thuộc tính `filter` cần Spring Kafka 2.8 trở lên; với phiên bản cũ, cấu hình filter qua container factory.

Khi một listener có filter riêng, hãy kiểm tra cách filter được chọn cùng factory của listener trong phiên bản đang dùng. Tránh cấu hình đồng thời nhiều filter với giả định chúng tự động được ghép nối; hãy xác định rõ chiến lược cuối cùng mà container sử dụng.

## 4. Điều gì xảy ra với record bị loại?

Record bị filter không được chuyển đến phương thức listener. Nó đã được consumer đọc từ Kafka, vì vậy ứng dụng cần quyết định rõ việc xác nhận offset. `ackDiscarded` điều khiển việc filtering adapter có xác nhận record bị loại trong trường hợp có acknowledgment hay không; việc commit thực tế vẫn tuân theo `AckMode`, transaction và container đang cấu hình.

| Cấu hình | Ý nghĩa cần kiểm tra |
| --- | --- |
| `ackDiscarded = false` | Adapter không chủ động acknowledge record bị loại. Với manual acknowledgment, cần xác định ai sẽ xác nhận record và khi nào offset được commit. |
| `ackDiscarded = true` | Adapter acknowledge record bị loại khi có `Acknowledgment`; container vẫn commit theo cơ chế acknowledgment đang dùng. |

Nếu record bị loại là dữ liệu không cần xử lý và không cần giao lại sau restart, hãy cấu hình acknowledgment để offset được xác nhận đúng chủ đích. Nếu không chắc chắn, hãy kiểm thử với `AckMode.RECORD`, `BATCH`, `MANUAL` hoặc `MANUAL_IMMEDIATE` mà ứng dụng thực sự sử dụng; đừng suy luận kết quả chỉ từ việc listener không được gọi.

Trong container dùng Kafka transaction, việc xác nhận offset phải tham gia transaction theo cấu hình container. Không tự commit trực tiếp từ filter strategy. `RecordFilterStrategy` chỉ quyết định giữ hay loại record, còn container quản lý offset và transaction.

## 5. Lọc theo payload, key hoặc headers

Filter có thể dựa trên nhiều phần của `ConsumerRecord`:

```java
@Bean
RecordFilterStrategy<String, OrderCreated> internalSourceFilter() {
    return record -> {
        var header = record.headers().lastHeader("source");
        if (header == null) {
            return false;
        }

        String source = new String(
                header.value(),
                java.nio.charset.StandardCharsets.UTF_8);
        return "internal-test".equals(source);
    };
}
```

Ví dụ loại các record có header `source=internal-test`. Nếu header không tồn tại, filter giữ record để listener tiếp tục xử lý. Với quy tắc dựa trên key, có thể kiểm tra `record.key()`; với quy tắc theo loại sự kiện, có thể đọc header event type hoặc trường phân biệt trong payload.

Hãy xác định rõ hành vi khi thiếu metadata. Mặc định giữ record thường an toàn hơn nếu thiếu header có thể là dấu hiệu của producer cũ hoặc dữ liệu chưa được nâng cấp. Nếu hợp đồng yêu cầu header bắt buộc, có thể loại hoặc đưa record vào quy trình lỗi riêng, nhưng cần thể hiện rõ quyết định đó.

## 6. Phân biệt filtering với error handling

Filtering và error handling giải quyết hai vấn đề khác nhau:

| Tình huống | Cơ chế phù hợp |
| --- | --- |
| Record hợp lệ nhưng listener không quan tâm | `RecordFilterStrategy` |
| Record cần xử lý nhưng lỗi tạm thời | `DefaultErrorHandler` hoặc retry topic |
| Payload không deserialize được | `ErrorHandlingDeserializer` và container error handler |
| Record vi phạm hợp đồng dữ liệu hoặc lỗi nghiệp vụ cần điều tra | Validation trong listener/service rồi chuyển qua recovery/DLT phù hợp |
| Cần quan sát, bổ sung metadata hoặc thực hiện logic trước/sau listener | `RecordInterceptor` |

Không dùng filter để che lỗi dữ liệu. Ví dụ, nếu `OrderCreated` thiếu `orderId`, loại record bằng filter có thể làm sự cố biến mất khỏi luồng quan sát trong khi không có bản ghi lỗi để điều tra. Hãy xác thực dữ liệu và ném exception để error handler/recoverer xử lý nếu record cần được lưu lại.

Filter cũng không phù hợp cho điều kiện tạm thời như dịch vụ thanh toán đang bận hoặc kho chưa đồng bộ. Nếu record có thể hợp lệ sau một khoảng chờ, hãy dùng retry thay vì loại bỏ nó.

## 7. Filtering và RecordInterceptor

`RecordInterceptor` là điểm mở rộng cho logic chạy quanh lời gọi listener, chẳng hạn ghi nhận metadata, tracing hoặc kiểm tra một điều kiện nhẹ. Phương thức `intercept()` có thể trả về record để tiếp tục gọi listener; trả về `null` sẽ bỏ qua lời gọi listener cho record đó.

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.RecordInterceptor;

RecordInterceptor<String, OrderCreated> tracingInterceptor =
        new RecordInterceptor<>() {
            @Override
            public ConsumerRecord<String, OrderCreated> intercept(
                    ConsumerRecord<String, OrderCreated> record,
                    Consumer<?, ?> consumer) {
                log.debug("Nhận record {}-{}@{}",
                        record.topic(), record.partition(), record.offset());
                return record;
            }
        };
```

Đăng ký interceptor trên factory bằng `setRecordInterceptor()`. Nếu mục tiêu chỉ là loại record theo predicate, `RecordFilterStrategy` diễn đạt rõ ý định hơn và có chính sách `ackDiscarded` chuyên biệt. Dùng interceptor cho cross-cutting logic; tránh dùng `null` như một bộ lọc thay thế khi không cần các callback trước/sau listener.

Không gọi API consumer để commit hoặc seek tùy tiện trong filter/interceptor. Các thao tác đó có thể xung đột với container và làm offset khó dự đoán. Hãy để container quản lý vòng đời consumer.

## 8. Nguyên tắc viết filter an toàn

Filter chạy trên đường xử lý của consumer, vì vậy cần ngắn, xác định và an toàn khi chạy đồng thời:

1. Ưu tiên kiểm tra payload, key và headers đã có trong record.
2. Không gọi REST, database hoặc dịch vụ từ xa trong filter; thao tác chậm làm giảm tốc độ poll và có thể gây rebalance.
3. Không tạo side effect trong filter. Filter có thể được gọi lại khi record được giao lại.
4. Viết strategy stateless hoặc bảo đảm thread-safe vì factory có thể dùng cho nhiều listener thread.
5. Xử lý rõ payload null, key null và header thiếu.
6. Không dùng filter làm cơ chế phân quyền. Kiểm tra quyền truy cập và tenant phải được thực thi ở lớp bảo mật/nghiệp vụ phù hợp.
7. Ghi nhận lý do loại record bằng metric hoặc log có chọn lọc; tránh ghi toàn bộ payload nhạy cảm.

Đặc biệt, với topic compacted, record có `value()` bằng null có thể là tombstone dùng để xóa key khỏi trạng thái đã compact. Không loại tombstone một cách máy móc nếu consumer cần duy trì state hoặc đồng bộ bản sao dữ liệu.

## 9. Quan sát và kiểm thử filtering

Nên có số liệu cho tổng record nhận, số record được giữ, số record bị loại và số lỗi trong filter. Khi log record bị loại, lưu topic, partition, offset, key hoặc event ID và lý do loại; không nhất thiết ghi toàn bộ payload.

Kiểm thử tích hợp nên xác minh cả hành vi listener lẫn offset:

1. Gửi record phù hợp filter; xác minh listener được gọi đúng một lần.
2. Gửi record bị filter; xác minh listener không được gọi.
3. Kiểm tra `ackDiscarded` với `AckMode` đang dùng và xác minh record bị loại có được commit theo yêu cầu sau khi consumer restart hay không.
4. Kiểm tra payload null, key null, header thiếu và header có giá trị không hợp lệ.
5. Nếu dùng `@KafkaListener(filter = "...")`, xác minh đúng bean được chọn cho listener.
6. Nếu dùng chung factory cho nhiều listener, xác minh mỗi listener nhận đúng chiến lược lọc.
7. Nếu có tombstone, xác minh filter giữ lại tombstone khi nghiệp vụ cần xử lý thao tác xóa.

## 10. Checklist triển khai

- [ ] `RecordFilterStrategy.filter()` trả về `true` đúng cho record cần loại và `false` cho record cần giữ.
- [ ] Filter được gắn đúng vào container factory hoặc thuộc tính `filter` của `@KafkaListener` (Spring Kafka 2.8+).
- [ ] `ackDiscarded` phù hợp với `AckMode`, manual acknowledgment và transaction.
- [ ] Filter không gọi dịch vụ từ xa, không làm side effect và không chặn consumer thread.
- [ ] Payload null, key null, header thiếu và tombstone đã được xem xét.
- [ ] Lỗi dữ liệu cần điều tra đi qua validation/error handling thay vì bị loại âm thầm.
- [ ] Có metric/log cho số record bị loại và lý do.
- [ ] Đã kiểm thử listener invocation, offset commit và hành vi sau restart.

`RecordFilterStrategy` là cách rõ ràng để loại record trước khi gọi listener. Khi quy tắc lọc chỉ phản ánh sự kiện mà consumer không cần, đồng thời acknowledgment và monitoring được cấu hình đúng, ứng dụng có thể giảm công việc nghiệp vụ mà vẫn kiểm soát được offset và khả năng điều tra dữ liệu bị loại.
