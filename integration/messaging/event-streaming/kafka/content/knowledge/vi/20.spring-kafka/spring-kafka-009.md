# CommonErrorHandler, DefaultErrorHandler và bộ khôi phục bản ghi

Trong Spring Kafka, listener container quản lý vòng lặp poll, gọi phương thức listener, commit offset và phối hợp với consumer group. Khi listener ném exception, container chuyển lỗi cho error handler để quyết định retry, bỏ qua, khôi phục hoặc chuyển record sang dead-letter topic (DLT).

Từ Spring Kafka 2.8, `CommonErrorHandler` là hợp đồng chung cho xử lý lỗi của record listener và batch listener. `DefaultErrorHandler` là implementation phổ biến, cung cấp retry theo BackOff, phân loại exception, seek hoặc giữ lại record để giao lại, và gọi recoverer khi hết retry.

Để chọn đúng cách xử lý, cần hiểu error handler nằm ở đâu trong lifecycle của container, offset được commit khi nào và recovery được xem là thành công theo chính sách nào.

## 1. Error handler nằm ở đâu trong listener container?

Với `@KafkaListener`, ứng dụng không trực tiếp gọi `poll()`. Spring Kafka tạo listener container, container sở hữu KafkaConsumer và gọi listener trên consumer thread.

~~~mermaid
flowchart TD
    A["Listener container poll()"] --> B["Gọi @KafkaListener"]
    B --> C{"Listener thành công?"}
    C -->|Có| D["Ack / commit theo AckMode"]
    C -->|Không| E["CommonErrorHandler"]
    E --> F{"Còn retry?"}
    F -->|Có| G["BackOff"]
    G --> H["Seek hoặc giữ record"]
    H --> A
    F -->|Không| I["Recoverer"]
    I --> J{"Recovery thành công?"}
    J -->|Có| K["Commit offset theo cấu hình"]
    J -->|Không| L["Recovery failure / retry lại"]
~~~

Container thực hiện các thao tác Kafka như poll, seek, pause, resume và commit. Error handler cung cấp quyết định xử lý lỗi; với `DefaultErrorHandler`, framework điều phối việc retry và phục hồi record theo cấu hình.

Điều này giúp ứng dụng không phải tự viết vòng lặp poll hoặc gọi seek trong từng listener. Listener chỉ cần thực hiện nghiệp vụ và ném exception khi không thể hoàn tất.

## 2. CommonErrorHandler là gì?

`CommonErrorHandler` là interface chuẩn hóa cách Spring Kafka xử lý exception phát sinh trong listener container. Nó thay thế các abstraction cũ tách riêng record error handler và batch error handler.

Một số khả năng quan trọng:

- Xử lý lỗi của record listener.
- Xử lý lỗi của batch listener.
- Xử lý exception phát sinh trong quá trình poll hoặc container hoạt động nhưng không gắn với một record cụ thể.
- Quyết định container có cần seek lại offset hay không.
- Cho biết offset của record đã được recover có được commit sau khi handler hoàn tất hay không.

Ứng dụng thường không cần tự implement interface này. Hãy dùng `DefaultErrorHandler` nếu retry/backoff/recoverer tiêu chuẩn đáp ứng yêu cầu; chỉ viết custom handler khi có quy tắc nghiệp vụ hoặc điều phối đặc thù.

### 2.1. Cấu hình handler trên listener container factory

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            CommonErrorHandler commonErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);

        return factory;
    }
}
~~~

`setCommonErrorHandler()` gắn handler vào các container được tạo từ factory. Nếu ứng dụng có nhiều factory, hãy cấu hình đúng factory được listener sử dụng; listener có thể chỉ định factory qua thuộc tính `containerFactory`.

### 2.2. Khi nào cần custom CommonErrorHandler?

Custom implementation phù hợp khi cần:

- Phân loại lỗi theo metadata hoặc nghiệp vụ đặc thù.
- Điều phối một quy trình recovery ngoài DLT mặc định.
- Tích hợp hệ thống incident hoặc quarantine riêng.
- Áp dụng chính sách khác nhau theo topic, tenant hoặc loại event.

Custom handler phải hiểu rõ semantics của `handleOne`, `handleRemaining`, `handleBatch`, `handleOtherException`, `seeksAfterHandling` và `isAckAfterHandle`. Xử lý sai có thể làm record bị giao lại vô hạn hoặc offset tiến qua record chưa hoàn tất.

## 3. DefaultErrorHandler và retry mặc định

`DefaultErrorHandler` là implementation phổ biến cho record listener và batch listener. Nó kết hợp:

- BackOff để quyết định thời gian và số lần retry.
- Exception classification để xác định lỗi nào retry được.
- Consumer seek hoặc cơ chế giữ record để giao lại.
- Recoverer để xử lý record khi retry đã hết.
- RetryListener để quan sát từng lần thất bại và recovery.

Ví dụ tạo handler với hai lần retry, mỗi lần cách nhau một giây:

~~~java
@Bean
DefaultErrorHandler defaultErrorHandler(
        ConsumerRecordRecoverer recoverer) {

    FixedBackOff backOff = new FixedBackOff(1000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Với `FixedBackOff(1000L, 2L)`, interval là 1.000 ms và số retry là 2 sau lần giao đầu tiên. Tổng số lần listener có thể nhận record trong trường hợp retry bình thường là 3: lần đầu và hai lần thử lại.

Hãy phân biệt số lần giao với số lần retry. Nhiều cấu hình ghi `attempts=3` có nghĩa ba lần giao tổng cộng, trong khi `FixedBackOff` nhận số lần retry sau lần đầu.

### 3.1. Cấu hình BackOff cố định

~~~java
FixedBackOff backOff = new FixedBackOff(
    2000L, // interval: 2 giây
    3L     // số lần retry sau lần giao đầu
);
~~~

Cách này dễ dự đoán và phù hợp khi downstream có thời gian phục hồi tương đối ổn định.

### 3.2. Exponential backoff

Khi lỗi có thể kéo dài, exponential backoff giảm áp lực lên downstream:

~~~java
ExponentialBackOff backOff = new ExponentialBackOff(
    500L,  // initial interval
    2.0    // multiplier
);

backOff.setMaxInterval(5000L);
backOff.setMaxElapsedTime(20000L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, backOff);
~~~

Các giá trị trên là minh họa. Kiểm tra API BackOff của Spring Framework đi cùng phiên bản Spring Kafka đang dùng. Với hệ thống có nhiều consumer, cân nhắc jitter ở tầng retry nếu chính sách BackOff hoặc cơ chế điều phối cho phép để tránh các consumer đồng loạt gọi lại downstream.

Không đặt thời gian retry dài hơn khả năng chịu đựng của listener container mà không xem xét poll progress và cơ chế pause.

## 4. Phân loại exception: lỗi nào retry, lỗi nào recover ngay?

Không phải mọi lỗi đều tự hết khi thử lại. Ví dụ timeout ngắn có thể phục hồi, nhưng lỗi schema hoặc quyền truy cập thường không thay đổi sau vài giây.

`DefaultErrorHandler` hỗ trợ thêm exception vào nhóm không retry hoặc retry:

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, new FixedBackOff(1000L, 2L));

handler.addNotRetryableExceptions(
    IllegalArgumentException.class,
    UnsupportedOperationException.class
);

handler.addRetryableExceptions(
    TransientDataAccessException.class,
    SocketTimeoutException.class
);
~~~

Ví dụ phân loại:

| Nhóm lỗi | Ví dụ | Chính sách thường dùng |
|---|---|---|
| Lỗi tạm thời | Socket timeout, connection reset, HTTP 503 | Retry có giới hạn |
| Rate limit | HTTP 429 | Retry theo Retry-After hoặc backoff |
| Lỗi dữ liệu | Payload sai định dạng, thiếu field bắt buộc | Không retry vô hạn; recover/DLT |
| Lỗi schema | Schema không tương thích, deserialization failure | Thường recover/DLT và xử lý contract |
| Lỗi nghiệp vụ vĩnh viễn | Đơn hàng không đủ điều kiện | Ghi nhận kết quả nghiệp vụ hoặc DLT |
| Lỗi quyền/cấu hình | Authorization failure, endpoint sai | Dừng retry và sửa cấu hình |

`DefaultErrorHandler` có danh sách exception được xem là fatal/non-retryable mặc định; danh sách cụ thể phụ thuộc phiên bản Spring Kafka. Hãy kiểm tra tài liệu phiên bản đang dùng và bổ sung phân loại tường minh cho lỗi nghiệp vụ của ứng dụng.

Không nên bắt mọi exception trong listener rồi chỉ log. Nếu listener không ném lỗi trở lại container, error handler không thể thực hiện retry hoặc recovery theo chính sách.

## 5. Seek và giao lại record sau lỗi

Sau khi retry thất bại, container phải xác định record nào cần đọc lại.

Với record listener, `DefaultErrorHandler` mặc định sử dụng seek semantics để đưa offset của record lỗi và các record chưa xử lý tiếp theo về vị trí cần đọc lại. Các record đã xử lý thành công trước record lỗi không cần giao lại trong trường hợp thông thường.

Ví dụ partition `orders-0` có batch:

| Offset | Kết quả |
|---:|---|
| 100 | Listener thành công |
| 101 | Listener ném exception |
| 102 | Chưa được xử lý |
| 103 | Chưa được xử lý |

Khi xử lý lỗi offset 101, container có thể seek partition về 101 để lần poll sau giao lại 101, 102 và 103. Offset 100 đã hoàn tất nên không cần xử lý lại theo luồng record listener tiêu chuẩn.

### 5.1. seekAfterError

Các phiên bản Spring Kafka mới có tùy chọn `seekAfterError` trên `DefaultErrorHandler`. Mặc định là `true`, sử dụng seek để giao lại các record chưa hoàn tất.

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, new FixedBackOff(1000L, 2L));

handler.setSeekAfterError(false);
~~~

Khi đặt `false`, framework giữ lại các record chưa xử lý và giao lại chúng sau một lần poll tạm dừng thay vì seek consumer về offset cũ. Container vẫn cần tiếp tục poll theo cách framework quản lý để duy trì hoạt động group.

Giữ record trong bộ nhớ có thể hữu ích khi muốn tránh seek, nhưng cần cân nhắc batch size, memory pressure và thời gian retry. Tên API và hành vi chi tiết cần được xác minh theo phiên bản Spring Kafka.

### 5.2. Vì sao không tự seek trong listener?

Không nên tự gọi `consumer.seek()` từ phương thức `@KafkaListener` thông thường. Listener không sở hữu consumer lifecycle và có thể không chạy trong ngữ cảnh an toàn để điều khiển offset.

Hãy để error handler và container quản lý seek/re-delivery. Nếu cần custom recovery, dùng API được Spring Kafka cung cấp hoặc một custom `CommonErrorHandler` có hiểu biết đầy đủ về container semantics.

## 6. Recoverer là gì?

Recoverer được gọi khi retry đã hết hoặc record được phân loại là không retry. Nó quyết định phải làm gì với record không thể xử lý.

Một số lựa chọn:

- Ghi log và đánh dấu cần can thiệp.
- Publish record sang dead-letter topic.
- Ghi payload và metadata lỗi vào quarantine store.
- Gọi một quy trình nghiệp vụ bù trừ.
- Chuyển record sang trạng thái chờ operator xử lý.

Nếu recoverer hoàn tất bình thường, error handler xem record đã được xử lý theo recovery policy. Nếu recoverer ném exception, recovery thất bại; record có thể tiếp tục được giao lại theo semantics của handler.

### 6.1. DeadLetterPublishingRecoverer

Spring Kafka cung cấp `DeadLetterPublishingRecoverer` để publish record lỗi sang DLT.

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(kafkaTemplate);
}

@Bean
DefaultErrorHandler defaultErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1000L, 2L)
    );
}
~~~

Theo resolver mặc định phổ biến, record được chuyển đến topic có hậu tố `.DLT` và partition tương ứng với partition nguồn. Vì vậy, DLT thường cần được tạo trước và có đủ partition tương ứng. Hành vi có thể được tùy chỉnh bằng destination resolver; hãy xác minh cấu hình thực tế của ứng dụng.

~~~text
orders
  ├── orders-0
  ├── orders-1
  └── orders-2

orders.DLT
  ├── orders.DLT-0
  ├── orders.DLT-1
  └── orders.DLT-2
~~~

### 6.2. Header trong DLT

`DeadLetterPublishingRecoverer` thường bổ sung header chứa thông tin nguồn và exception, ví dụ:

- Original topic.
- Original partition.
- Original offset.
- Exception class/message.
- Stack trace hoặc thông tin delivery attempt tùy cấu hình và phiên bản.

Giữ event ID và key gốc để điều tra, deduplicate và re-drive. Không ghi thông tin nhạy cảm vào header hoặc stack trace nếu log/DLT được nhiều nhóm truy cập.

### 6.3. Recovery thất bại

Publish DLT cũng có thể thất bại do broker không sẵn sàng, ACL hoặc serialization. Không được commit input offset như thể record đã được lưu an toàn vào DLT nếu recoverer không xác nhận thành công.

Hãy kiểm tra callback/future của publisher theo cách recoverer hỗ trợ và quan sát metric recovery failure. Nếu recovery thất bại, cần giữ khả năng đọc lại record hoặc chuyển sang quy trình quarantine bền vững.

## 7. Commit offset sau khi recovery

Khi listener xử lý thành công, container commit offset theo `AckMode`. Khi listener thất bại nhưng recoverer hoàn tất, offset có được commit hay không phụ thuộc cấu hình container và handler.

`DefaultErrorHandler` có thuộc tính `ackAfterHandle`, mặc định thường là `true`. Khi handler hoàn tất xử lý lỗi bình thường, container có thể commit offset của record đã được recover theo acknowledgement mode.

Với `AckMode.MANUAL_IMMEDIATE`, nếu muốn commit offset của record được recover ngay theo cơ chế manual immediate, cần cấu hình `commitRecovered=true` trên handler và bảo đảm listener/container dùng đúng acknowledgement mode.

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.MANUAL_IMMEDIATE
);

handler.setCommitRecovered(true);
~~~

Không bật `commitRecovered` một cách máy móc cho mọi AckMode. Đọc kỹ semantics của mode đang dùng và kiểm tra phiên bản Spring Kafka.

### 7.1. Các AckMode thường gặp

| AckMode | Cách commit tổng quát | Khi xem xét |
|---|---|---|
| RECORD | Commit sau từng record listener thành công | Muốn checkpoint gần từng record |
| BATCH | Commit sau khi xử lý batch poll | Throughput tốt, có thể xử lý lại phần batch khi lỗi |
| MANUAL | Listener ack, container commit theo semantics manual | Ứng dụng quyết định thời điểm ack |
| MANUAL_IMMEDIATE | Commit ngay khi ack trên consumer thread | Cần kiểm soát checkpoint tường minh |

Không commit offset vượt qua record chưa xử lý hoặc chưa được recovery bền vững. Nếu DLT publish thành công nhưng offset không commit do crash, record có thể được giao lại và gửi DLT lần nữa. Consumer DLT nên có event ID để chống duplicate.

## 8. Batch listener và BatchListenerFailedException

Record listener nhận từng record một. Batch listener nhận danh sách record từ một lần poll. Vì vậy, khi một record trong batch lỗi, error handler cần biết vị trí record lỗi để xử lý offset chính xác.

Với batch listener, có thể ném `BatchListenerFailedException` để chỉ rõ record thất bại:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-worker"
)
public void processBatch(List<ConsumerRecord<String, String>> records) {

    for (ConsumerRecord<String, String> record : records) {
        try {
            orderService.process(record.value());
        } catch (Exception exception) {
            throw new BatchListenerFailedException(
                "Cannot process order",
                record
            );
        }
    }
}
~~~

Khi handler biết record lỗi, nó có thể commit tiến độ trước record đó theo acknowledgement semantics, retry record lỗi và phần còn lại.

Nếu batch listener ném exception thông thường mà không xác định record lỗi, handler có thể phải retry toàn batch. Điều này làm các record đã xử lý thành công trước đó được gọi lại; handler cần idempotent.

Với batch listener, việc xử lý song song trong ứng dụng cần quản lý offset liên tục theo từng partition. Không lấy offset lớn nhất đã hoàn thành rồi commit nếu vẫn còn record trước đó chưa xử lý.

## 9. Deserialization error và ErrorHandlingDeserializer

Một lỗi có thể xảy ra trước khi listener được gọi: Kafka client không deserialize được byte thành object. Khi đó listener không nhận được một payload hợp lệ để tự ném exception.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để bắt lỗi deserialize và chuyển thông tin lỗi qua header, giúp container/error handler xử lý record lỗi theo quy trình phù hợp.

~~~properties
spring.kafka.consumer.key-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer

spring.kafka.consumer.properties.spring.deserializer.key.delegate.class=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.properties.spring.deserializer.value.delegate.class=org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Đây là ví dụ cấu hình minh họa; delegate class và trusted packages phải phù hợp schema/serializer của ứng dụng. Không bật trusted packages rộng tùy tiện khi deserialize payload không đáng tin cậy.

Deserialization exception thường được phân loại là fatal/non-retryable vì cùng một byte payload sẽ tiếp tục lỗi nếu thử lại không có thay đổi. Có thể chuyển record sang DLT để điều tra, giữ raw bytes và metadata nguồn.

## 10. RetryListener để quan sát quá trình retry

`RetryListener` cho phép ghi metric hoặc log khi record thất bại, được retry, recovery thành công hoặc recovery thất bại.

~~~java
@Bean
DefaultErrorHandler defaultErrorHandler(
        DeadLetterPublishingRecoverer recoverer,
        MeterRegistry meterRegistry) {

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1000L, 2L));

    handler.setRetryListeners(new RetryListener() {
        @Override
        public void failedDelivery(
                ConsumerRecord<?, ?> record,
                Exception exception,
                int deliveryAttempt) {

            meterRegistry.counter(
                "kafka.listener.retry",
                "topic", record.topic(),
                "exception", exception.getClass().getSimpleName()
            ).increment();
        }

        @Override
        public void recovered(
                ConsumerRecord<?, ?> record,
                Exception exception) {

            meterRegistry.counter(
                "kafka.listener.recovered",
                "topic", record.topic()
            ).increment();
        }

        @Override
        public void recoveryFailed(
                ConsumerRecord<?, ?> record,
                Exception original,
                Exception failure) {

            meterRegistry.counter(
                "kafka.listener.recovery.failed",
                "topic", record.topic()
            ).increment();
        }
    });

    return handler;
}
~~~

Các callback và overload có thể thay đổi theo phiên bản Spring Kafka. Ví dụ cần bổ sung import và cấu hình Micrometer trong ứng dụng thực tế.

Metric nên có topic và exception class nhưng tránh dùng event ID, customer ID hoặc key có cardinality cao làm label. Đưa các định danh đó vào log có kiểm soát hoặc trace thay vì metric label.

## 11. Retry lâu và ContainerPausingBackOffHandler

Blocking backoff mặc định có thể làm consumer thread chờ giữa các lần retry. Với thời gian chờ dài, điều này có thể ảnh hưởng poll progress và gây rebalance.

Spring Kafka có `ContainerPausingBackOffHandler` trong các phiên bản hỗ trợ. Handler này pause container trong thời gian backoff, đồng thời container tiếp tục poll theo cơ chế nội bộ để duy trì hoạt động group.

~~~java
DefaultErrorHandler handler = new DefaultErrorHandler(
    recoverer,
    new FixedBackOff(30000L, 2L),
    new ContainerPausingBackOffHandler()
);
~~~

Cấu hình cụ thể phụ thuộc phiên bản. Container pausing backoff phù hợp khi delay dài hơn thời gian poll thông thường. Cần kiểm tra tác động lên tất cả partition trong container và khả năng xử lý các partition khác.

Nếu chỉ một partition có record lỗi và các partition khác cần tiếp tục, cần cân nhắc thiết kế pause theo partition hoặc retry topic. Không giả định pause toàn container tương đương pause riêng partition.

## 12. Phân biệt blocking retry và non-blocking retry

Spring Kafka có thể triển khai retry theo hai cách chính:

| Tiêu chí | Blocking retry qua DefaultErrorHandler | Non-blocking retry qua retry topics |
|---|---|---|
| Record lỗi | Được giao lại trong luồng container hiện tại | Được publish sang retry topic |
| Consumer chính | Chờ retry/backoff | Có thể tiếp tục xử lý record sau |
| Ordering | Có thể giữ thứ tự trong partition nếu không vượt qua record lỗi | Có thể thay đổi thứ tự khi record sau được xử lý trước |
| Delay dài | Cần pause/backoff phù hợp | Phù hợp với nhiều mức delay |
| DLT | Recoverer sau khi hết retry | Retry topic cuối hoặc DLT theo cấu hình |
| Độ phức tạp | Thấp hơn | Cần quản lý retry topics, consumer và topology |

`@RetryableTopic` là lựa chọn cho non-blocking retry trong các trường hợp phù hợp. Nó không thay thế `DefaultErrorHandler` cho mọi loại lỗi; cần cân nhắc ordering, transaction và batch listener support theo phiên bản Spring Kafka.

## 13. Transactional listener: dùng AfterRollbackProcessor

Khi listener chạy trong Kafka transaction, exception thường làm transaction rollback. Luồng retry sau rollback được điều phối bởi `AfterRollbackProcessor`, phổ biến là `DefaultAfterRollbackProcessor`, thay vì chỉ cấu hình `DefaultErrorHandler` như một listener không transactional.

Luồng tổng quát:

1. Container bắt đầu transaction.
2. Listener xử lý record và thực hiện output transactional.
3. Listener ném exception.
4. Transaction rollback.
5. AfterRollbackProcessor quyết định redelivery/backoff/recovery.
6. Khi recovery hoàn tất, offset được xử lý theo transactional semantics tương ứng.

Nếu ứng dụng dùng transactional container factory, hãy cấu hình recovery theo `DefaultAfterRollbackProcessor` và kiểm tra cách DLT recovery được thực hiện. Không trộn lẫn ví dụ non-transactional `DefaultErrorHandler` với transactional rollback path mà không hiểu thứ tự commit/abort.

## 14. Java cấu hình đầy đủ cho record listener

Ví dụ kết hợp recoverer, phân loại lỗi, BackOff và CommonErrorHandler:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    DeadLetterPublishingRecoverer ordersRecoverer(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        return new DeadLetterPublishingRecoverer(kafkaTemplate);
    }

    @Bean
    CommonErrorHandler ordersErrorHandler(
            DeadLetterPublishingRecoverer ordersRecoverer) {

        FixedBackOff backOff = new FixedBackOff(1000L, 3L);

        DefaultErrorHandler handler =
            new DefaultErrorHandler(ordersRecoverer, backOff);

        handler.addNotRetryableExceptions(
            IllegalArgumentException.class
        );

        handler.addRetryableExceptions(
            SocketTimeoutException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            CommonErrorHandler ordersErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(ordersErrorHandler);

        factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD
        );

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory"
    )
    public void onOrder(String payload) {
        orderService.process(payload);
    }
}
~~~

Listener để exception thoát ra container. Error handler sẽ áp dụng retry/recovery. Trong triển khai thực tế, cần tạo DLT, cấu hình producer serializer tương thích với payload và xác minh destination resolver.

## 15. Kiểm thử error handler

Nên kiểm thử cả đường retry thành công, hết retry và recovery thất bại:

| Kịch bản | Cách tạo | Điều cần xác minh |
|---|---|---|
| Thành công lần đầu | Listener xử lý bình thường | Offset tiến theo AckMode |
| Lỗi tạm thời rồi thành công | Handler ném exception ở lần đầu, thành công lần sau | Số lần retry và kết quả cuối đúng |
| Hết retry | Listener luôn ném retryable exception | Recoverer được gọi sau số lần retry cấu hình |
| Lỗi non-retryable | Ném IllegalArgumentException đã phân loại | Không thực hiện retry không cần thiết |
| DLT publish lỗi | DLT broker/topic/ACL không sẵn sàng | Recovery không bị xem là thành công giả |
| Crash sau recovery trước commit | Dừng process ở khoảng giữa | Record có thể giao lại; DLT consumer chịu duplicate |
| Batch listener lỗi ở record giữa | Ném BatchListenerFailedException | Offset trước record lỗi được xử lý đúng |
| Deserialization lỗi | Gửi payload không hợp lệ | ErrorHandlingDeserializer và DLT giữ raw record |
| Retry delay dài | Dùng backoff vượt poll interval thông thường | Container pausing hoặc poll behavior không gây rebalance ngoài ý muốn |
| Rebalance trong retry | Thêm/bớt consumer khi record đang retry | Assignment và offset không bị commit sai |

Kiểm thử cần xác minh số lần listener được gọi, offset cuối, nội dung DLT, header nguồn, event ID và side effect trong database. Chỉ xác nhận exception đã được log không đủ để chứng minh recovery an toàn.

## 16. Metric và log cần theo dõi

Các chỉ số hữu ích:

- Listener invocation count.
- Retry attempt count theo exception type.
- Recovery success/failure count.
- DLT publish rate.
- Consumer lag và oldest record age.
- Listener processing duration p95/p99.
- Backoff duration.
- Rebalance count.
- Commit latency.
- Số record đang được giữ hoặc retry nếu dùng retain mode.

Log nên chứa topic, partition, offset, event ID (nếu có), consumer group, exception class và delivery attempt. Tránh log toàn bộ payload nếu có dữ liệu cá nhân hoặc bí mật.

Khi DLT tăng đột biến, hãy phân biệt lỗi dữ liệu, lỗi schema, lỗi quyền và downstream outage. Một lỗi non-retryable có thể làm DLT tăng nhanh dù retry rate thấp.

## 17. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Listener retry vô hạn | BackOff hoặc recoverer không đúng; recovery liên tục thất bại | Kiểm tra BackOff, recoverer và retry failure |
| Record bị bỏ qua sau khi lỗi | Offset commit/recovery policy không đúng | Kiểm tra AckMode, ackAfterHandle và commitRecovered |
| DLT không có record | Destination resolver, serializer, ACL hoặc publish lỗi | Kiểm tra recoverer và producer result |
| DLT publish lỗi nhưng offset vẫn tiến | Recovery failure bị xử lý sai hoặc custom handler trả sai | Kiểm tra exception path và handler contract |
| Rebalance trong backoff dài | Consumer thread bị chặn hoặc poll progress không đạt | Giảm delay, dùng container pausing backoff hoặc retry topic |
| Batch bị xử lý lại toàn bộ | Không chỉ rõ record lỗi trong batch listener | Dùng BatchListenerFailedException đúng record |
| Deserialization error không vào listener | Lỗi xảy ra trước listener invocation | Cấu hình ErrorHandlingDeserializer |
| Record lỗi bị xử lý sai thứ tự | Retry topic cho phép record sau vượt qua | Dùng sequence guard hoặc chiến lược giữ thứ tự |
| Recovery chạy nhưng offset không commit | AckMode hoặc commitRecovered chưa phù hợp | Kiểm tra cấu hình acknowledgement |

## 18. Checklist triển khai CommonErrorHandler

- [ ] Đã xác định listener là record hay batch.
- [ ] Container factory được gắn đúng CommonErrorHandler.
- [ ] BackOff có giới hạn số lần và thời gian.
- [ ] Exception retryable và non-retryable được phân loại.
- [ ] Đã hiểu seekAfterError và hành vi redelivery.
- [ ] Recoverer chỉ đánh dấu thành công khi lưu/publish record an toàn.
- [ ] DLT tồn tại, serializer phù hợp và partition mapping hợp lệ.
- [ ] Event ID, key và metadata nguồn được giữ lại.
- [ ] AckMode, ackAfterHandle và commitRecovered được cấu hình nhất quán.
- [ ] Batch listener xác định chính xác record lỗi khi cần.
- [ ] Deserialization failure có ErrorHandlingDeserializer phù hợp.
- [ ] Backoff dài không làm poll progress vượt giới hạn.
- [ ] Transactional listener dùng AfterRollbackProcessor phù hợp.
- [ ] Retry, recovery, DLT, lag và rebalance có metric.
- [ ] Đã kiểm thử recovery failure và crash trước commit.

`CommonErrorHandler` là hợp đồng xử lý lỗi của listener container; `DefaultErrorHandler` cung cấp retry, phân loại exception, seek/retain và recovery theo BackOff. Khi hết retry, recoverer có thể chuyển record sang DLT hoặc một nơi lưu trữ khác. Để không mất dữ liệu, cần phối hợp recovery với AckMode và commit offset, đồng thời kiểm tra lỗi khi publish DLT. Với batch listener và transactional listener, semantics khác record listener thông thường; hãy cấu hình đúng `BatchListenerFailedException` hoặc `AfterRollbackProcessor` theo trường hợp sử dụng.
