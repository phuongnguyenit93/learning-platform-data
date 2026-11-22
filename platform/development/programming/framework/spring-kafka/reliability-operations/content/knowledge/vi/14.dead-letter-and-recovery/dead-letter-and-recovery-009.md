# Recovery record và logRecoveryRecord

Trong một consumer Spring Kafka có retry, không phải record lỗi nào cũng có thể xử lý thành công ở lần thử tiếp theo. Sau khi đã retry đủ số lần cho phép, hoặc khi exception được xác định là không nên retry, ứng dụng cần một **bước recovery**: ghi nhận record lỗi, gửi sang dead-letter topic (DLT), hoặc chuyển sang quy trình xử lý khác. Bước này giúp consumer không bị kẹt vô hạn tại cùng một record nhưng vẫn giữ được thông tin để điều tra.

`DeadLetterPublishingRecoverer` là recoverer thường dùng để publish record thất bại sang DLT. Từ **Spring Kafka 3.1**, lớp này có phương thức `setLogRecoveryRecord(boolean)`; đặt `true` để ghi log **recovery record và exception**. Tính năng `logRecoveryRecord` hỗ trợ quan sát sự kiện được đưa vào quy trình recovery, nhưng **không tự bảo đảm việc gửi DLT thành công, không thay đổi số lần retry và không thay thế cơ chế xử lý trùng**.

## 1. Recovery record là gì?

Một *recovery record* là record đã đi đến nhánh phục hồi theo chính sách xử lý lỗi. Trong phạm vi bài học, đó thường là `ConsumerRecord<?, ?>` mà listener không xử lý được và error handler quyết định chuyển cho một `ConsumerRecordRecoverer`.

Ví dụ một record thuộc topic `orders`, partition 2, offset 150:

```text
orders-2, offset=150
          |
          v
@KafkaListener xử lý OrderCreated
          |
          v
HTTP timeout / ValidationException / lỗi nghiệp vụ
          |
          v
DefaultErrorHandler quyết định retry?
          |
     +----+----+
     |         |
    Có       Không / hết retry
     |         |
     v         v
Thử lại   ConsumerRecordRecoverer
               |
               v
      Ghi log hoặc publish DLT
```

Recovery không đồng nghĩa nghiệp vụ đã hoàn tất. Nếu một `OrderCreated` không thể xử lý và được chuyển thành công vào `orders.DLT`, tiến độ tiêu thụ có thể tiếp tục theo cấu hình, nhưng đơn hàng đó vẫn cần điều tra hoặc xử lý lại. Vì vậy cần phân biệt hai khái niệm:

| Khái niệm | Điều đã xảy ra | Điều chưa được bảo đảm |
|---|---|---|
| Listener success | Phương thức listener hoàn tất bình thường. | Mọi hệ thống ngoài Kafka đều đã bền vững, nếu logic không bảo đảm điều đó. |
| Recovery success | Recoverer hoàn tất theo hợp đồng và chính sách lỗi của nó. | Nghiệp vụ chính đã xử lý thành công hoặc đã có người giải quyết DLT. |

Khi gặp lỗi, record có thể retry nhiều lần trước khi vào recovery. Với lỗi được phân loại không retry, record có thể đi vào recovery ngay sau lần thất bại đầu tiên.

## 2. Mối quan hệ giữa DefaultErrorHandler và recoverer

`DefaultErrorHandler` điều phối việc xử lý lỗi của Kafka listener container. Với record listener, handler sử dụng `BackOff` để quyết định có thử xử lý lại record hay chuyển sang recovery. Khi backoff đã cạn, handler gọi recoverer tương ứng.

Ví dụ dùng `FixedBackOff`:

```java
FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(backOff);
```

`2L` là **hai lần retry sau lần giao ban đầu**, tức tối đa ba lần gọi listener trong một chu kỳ retry thông thường. Nếu mọi lần đều thất bại, handler gọi cơ chế recovery mặc định. Mặc định, recoverer của `DefaultErrorHandler` ghi log record thất bại; nếu cần đưa record sang DLT, hãy cung cấp một recoverer chuyên dụng.

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L));
```

Ở ví dụ thứ hai, `DefaultErrorHandler` vẫn là thành phần điều phối retry. `DeadLetterPublishingRecoverer` chỉ nhận record khi handler quyết định chuyển vào recovery. Không nên hiểu rằng việc khai báo recoverer khiến listener gửi mọi record trực tiếp vào DLT.

## 3. DeadLetterPublishingRecoverer gửi đi đâu?

Với một `DeadLetterPublishingRecoverer` được tạo từ `KafkaTemplate` mà không có resolver tùy chỉnh, quy tắc mặc định thường là gửi đến topic gốc cộng hậu tố `.DLT` và cùng partition số với record gốc.

Ví dụ:

```text
Nguồn: orders-2, offset=150
        |
        v
DeadLetterPublishingRecoverer
        |
        v
Đích: orders.DLT, partition=2
```

Kafka offset ở topic DLT được cấp riêng. Record gốc ở offset 150 **không** có nghĩa bản sao trong DLT cũng ở offset 150. Khi truy vết, cần dùng thông tin nguồn trong header và một event ID ổn định.

Nếu muốn định tuyến theo exception hoặc nghiệp vụ, có thể truyền destination resolver:

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> {
                    String destination =
                            exception instanceof IllegalArgumentException
                                    ? "orders-invalid.DLT"
                                    : "orders.DLT";

                    return new TopicPartition(destination, record.partition());
                });
```

Ví dụ này cần các topic DLT tồn tại và có partition tương ứng, cùng producer serializer và quyền ghi phù hợp. Nếu topic đích không có partition được yêu cầu, cách framework kiểm tra và lựa chọn partition phụ thuộc phiên bản/cấu hình; đừng coi một destination trả về là bằng chứng publish chắc chắn thành công.

## 4. logRecoveryRecord là gì, và có từ phiên bản nào?

`setLogRecoveryRecord(boolean)` là phương thức của **`org.springframework.kafka.listener.DeadLetterPublishingRecoverer`**, được cung cấp từ **Spring Kafka 3.1**. Ý nghĩa của phương thức là bật hoặc tắt việc ghi log record đang được recover và exception tương ứng.

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

recoverer.setLogRecoveryRecord(true);
```

Khi được bật, recoverer ghi thông tin record và exception trong quá trình recovery. Điều này giúp người vận hành biết record nào đã đến nhánh phục hồi mà không phải chỉ dựa vào log listener ban đầu.

Cần phân biệt ba việc khác nhau:

| Cơ chế | Mục đích |
|---|---|
| `setLogRecoveryRecord(true)` | Ghi log recovery record và exception trong `DeadLetterPublishingRecoverer`. |
| `DefaultErrorHandler` + `BackOff` | Quyết định khi nào retry và khi nào chuyển sang recoverer. |
| `setFailIfSendResultIsError(true)` | Yêu cầu recoverer phát hiện và báo lỗi từ kết quả publish bất đồng bộ khi được hỗ trợ. |

**`logRecoveryRecord` không phải thuộc tính của Kafka broker** và không phải cú pháp `spring.kafka.consumer.logRecoveryRecord` của Kafka client. Nó là cấu hình trên đối tượng Java recoverer. Nếu ứng dụng chạy Spring Kafka trước 3.1, không thể gọi phương thức này; cần nâng phiên bản phù hợp hoặc triển khai logging ở tầng recovery bằng API sẵn có.

Không bật `logRecoveryRecord` chỉ vì muốn biết record lỗi. Có thể hệ thống đã có log tại error handler, retry listener và DLT consumer; khi đó bật thêm tính năng này có thể tạo log trùng, tăng dung lượng lưu trữ hoặc làm lộ payload. Hãy quyết định dựa trên mục đích giám sát và chính sách dữ liệu.

## 5. Ví dụ cấu hình đầy đủ với Spring Kafka

Đoạn cấu hình sau dùng `DefaultErrorHandler`, `FixedBackOff` và `DeadLetterPublishingRecoverer`. Listener thử lại tối đa hai lần sau lần đầu; khi hết retry, recoverer gửi record sang DLT và ghi log recovery record.

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class OrderKafkaErrorConfig {

    @Bean
    public DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        recoverer.setLogRecoveryRecord(true);
        recoverer.setFailIfSendResultIsError(true);
        recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));

        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory,
                    DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);
        return factory;
    }
}
```

Listener chỉ cần làm nghiệp vụ và ném exception khi thất bại:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void handle(OrderCreated event) {
    orderService.process(event);
}
```

Ví dụ trên giả định ứng dụng đã cấu hình `ConsumerFactory`, `KafkaTemplate`, serializer/deserializer và logging framework. Đối tượng `OrderCreated` là kiểu dữ liệu nghiệp vụ do ứng dụng tự định nghĩa. `KafkaTemplate<Object, Object>` cần một producer factory tương thích kiểu key/value trong cả luồng bình thường và luồng recovery; không mặc định một serializer có thể xử lý mọi kiểu payload lỗi.

Với Spring Boot, có thể cấu hình các thuộc tính consumer nền tảng như sau:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
    producer:
      acks: all
```

Đừng nhầm `enable-auto-commit: false` với việc đã đảm bảo commit an toàn. Listener container vẫn cần chính sách acknowledgment, cách commit và recovery phù hợp. Giá trị `acks: all` giúp producer yêu cầu acknowledgment từ broker theo cấu hình replication, nhưng một mình nó không tạo giao dịch nguyên tử với committed offset của consumer.

## 6. Log recovery được tạo vào thời điểm nào?

Luồng xử lý điển hình:

```text
Consumer poll record
        |
        v
Listener xử lý và ném exception
        |
        v
DefaultErrorHandler thực hiện các lần retry được phép
        |
        v
BackOff hết hoặc exception không retry
        |
        v
DeadLetterPublishingRecoverer.accept(record, exception)
        |
        +--> logRecoveryRecord = true:
        |      ghi thông tin record và exception
        |
        +--> tạo ProducerRecord cho DLT
        |      + thêm header nguồn/lỗi
        |
        +--> publish qua KafkaTemplate
        |
        v
Kết quả publish và xử lý recovery theo cấu hình
```

Đây là sơ đồ logic. Thứ tự chính xác giữa lời gọi logging, tạo record và nhận producer acknowledgment phụ thuộc triển khai/phiên bản. **Một dòng log recovery không phải bằng chứng record đã tồn tại bền vững trong DLT**. Nếu cần xác minh, hãy theo dõi kết quả send, số record thực tế ở DLT và các lỗi của producer.

Có ít nhất ba loại log cần phân biệt:

1. **Listener failure:** ghi nhận lần xử lý record thất bại.
2. **Retry exhausted hoặc recovery attempt:** ghi nhận record đã đi đến nhánh phục hồi.
3. **DLT publishing outcome:** ghi nhận việc publish thực sự thành công hay thất bại theo chính sách chờ/kết quả gửi.

Chỉ bật `logRecoveryRecord` giúp quan sát loại thứ hai; nó không tự thay thế hai loại log còn lại.

## 7. Phân biệt default recoverer log và logRecoveryRecord

Nếu không truyền recoverer tùy chỉnh cho `DefaultErrorHandler`, khi retry cạn Spring Kafka mặc định có thể **log record lỗi**. Đây là hành vi recovery của error handler. Nó khác với việc bật `setLogRecoveryRecord(true)` trên một `DeadLetterPublishingRecoverer` cụ thể.

Ví dụ:

```java
// Dùng recoverer mặc định của DefaultErrorHandler.
DefaultErrorHandler handler =
        new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));

// Dùng recoverer gửi DLT và yêu cầu log record đang recover.
DeadLetterPublishingRecoverer publishingRecoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);
publishingRecoverer.setLogRecoveryRecord(true);

DefaultErrorHandler publishingHandler =
        new DefaultErrorHandler(
                publishingRecoverer,
                new FixedBackOff(1_000L, 2L));
```

Trong cấu hình đầu tiên, `DefaultErrorHandler` không tự xuất hiện một bước publish sang DLT. Trong cấu hình thứ hai, record được đưa qua publishing recoverer; `logRecoveryRecord` chỉ bổ sung khả năng logging trong thành phần này.

Cũng cần phân biệt `setLogRecoveryRecord` với mức log exception của error handler (`setLogLevel(...)` ở các API thích hợp). Mức log của exception do handler ném ra và log record mà recoverer đang chuyển đi có thể thuộc những nhánh khác nhau, nên thay đổi một cái không có nghĩa mọi log lỗi sẽ biến mất.

## 8. Kiểm soát dữ liệu nhạy cảm trong recovery log

`ConsumerRecord` có thể chứa key, value và các header của message. Exception có thể chứa message nghiệp vụ, URL, dữ liệu đầu vào hoặc stack trace. Vì vậy, khi bật `setLogRecoveryRecord(true)` cần xem chính sách bảo mật log:

- Không đưa mật khẩu, token, số thẻ thanh toán hoặc thông tin cá nhân vào payload được ghi log.
- Tránh lưu payload nguyên vẹn khi record chứa dữ liệu nhạy cảm hoặc quá lớn.
- Xem lại cách `toString()` của payload nghiệp vụ được triển khai; phương thức này có thể lộ trường dữ liệu mà ứng dụng không muốn công bố.
- Chỉ cấp quyền đọc log recovery cho nhóm cần vận hành.
- Đặt thời gian retention phù hợp cho log và DLT; hai nơi này có chính sách bảo vệ độc lập.
- Dùng correlation/event ID để truy vết thay vì phụ thuộc nội dung payload.

Khi ứng dụng cần log có kiểm soát, có thể dùng `RetryListener.recovered(...)` để ghi metadata đã chọn thay vì bật log nguyên record. Ví dụ:

```java
DefaultErrorHandler handler =
        new DefaultErrorHandler(
                publishingRecoverer,
                new FixedBackOff(1_000L, 2L));

handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        // Tránh in payload ở mỗi lần retry.
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        log.warn(
            "Kafka record recovered: topic={}, partition={}, offset={}, exception={}",
            record.topic(),
            record.partition(),
            record.offset(),
            exception.getClass().getSimpleName());
    }
});
```

`recovered()` là tín hiệu từ error handler khi recoverer không ném lỗi tại thời điểm được gọi. Nếu việc gửi DLT còn có thể thất bại bất đồng bộ mà recoverer chưa xác minh, tín hiệu này không tự bảo đảm bản sao đã được broker lưu. Với hệ thống cần xác nhận publish, hãy đồng thời cấu hình cơ chế quan sát kết quả send của recoverer.

## 9. Lỗi publish DLT và trạng thái recovery

Một record có thể không xử lý được tại listener và cũng không publish được sang DLT. Ví dụ, topic DLT chưa tồn tại, producer thiếu ACL, serializer không hỗ trợ kiểu value, hoặc broker không phản hồi.

```text
orders-2, offset 150
         |
         v
Listener lỗi và retry cạn
         |
         v
DeadLetterPublishingRecoverer
         |
         +--> Publish DLT thành công
         |       |
         |       v
         |   Có thể kết thúc recovery theo cấu hình
         |
         +--> Publish DLT thất bại
                 |
                 v
             Recovery failure
                 |
                 v
        Cần xử lý lại / điều tra lỗi publish
```

Spring Kafka có các cấu hình như `setFailIfSendResultIsError(true)` và `setWaitForSendResultTimeout(...)` để recoverer phát hiện lỗi gửi trả về và kiểm soát thời gian chờ kết quả. Khi recoverer thực sự ném exception vì recovery thất bại, `DefaultErrorHandler` có thể đưa record lỗi trở lại chu kỳ retry; mặc định trạng thái backoff có thể được reset sau lỗi recovery.

Ví dụ:

```java
publishingRecoverer.setLogRecoveryRecord(true);
publishingRecoverer.setFailIfSendResultIsError(true);
publishingRecoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));

DefaultErrorHandler handler = new DefaultErrorHandler(
        publishingRecoverer,
        new FixedBackOff(2_000L, 3L));
```

Trong thực tế cần cấu hình timeout của producer, broker và ứng dụng cho phù hợp. Nếu chờ send kết quả quá lâu trên consumer thread, thời gian xử lý có thể tiến sát `max.poll.interval.ms`. Nếu không chờ hoặc không bắt lỗi publish, có rủi ro nhận định recovery thành công quá sớm. Cần cân bằng hai nguy cơ này theo yêu cầu độ tin cậy.

**Không dùng log của `logRecoveryRecord` làm tiêu chí duy nhất để xóa hoặc bỏ qua record lỗi.** Muốn xác nhận chuyển giao, hãy dùng kết quả publish, offset, số lượng record trên DLT và các metric tương ứng.

## 10. Recovery và committed offset không phải một giao dịch mặc định

Khi record được recover, consumer có thể tiếp tục sang record sau tùy acknowledgment mode và chính sách error handler. Tuy nhiên, hành vi commit offset phụ thuộc cấu hình container, không phụ thuộc duy nhất vào `logRecoveryRecord`.

Ví dụ, record `orders-2@150` lỗi và được gửi DLT:

```text
Consumer xử lý orders-2@150 thất bại
          |
          v
Recoverer publish bản sao sang orders.DLT
          |
          v
Container được phép tiến qua record lỗi theo cấu hình
          |
          v
Consumer group có thể commit next offset = 151
```

Trong các chế độ manual, cần hiểu rõ việc acknowledge và commit recovered offset. Với `AckMode.MANUAL_IMMEDIATE`, `DefaultErrorHandler` hỗ trợ `setCommitRecovered(true)` khi muốn commit offset của record đã recover; cấu hình này có điều kiện và không phải luôn cần bật cho các ack mode khác.

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        publishingRecoverer,
        new FixedBackOff(1_000L, 2L));

handler.setCommitRecovered(true);

// Container tương ứng cần AckMode.MANUAL_IMMEDIATE.
factory.getContainerProperties()
       .setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);
```

Đây là ví dụ cấu hình, không phải lời khuyên bật `commitRecovered` cho mọi listener. Phải cân nhắc thời điểm ghi DLT, trạng thái lỗi recovery và bảo đảm nghiệp vụ. Commit offset nguồn và publish DLT không tự trở thành một transaction nguyên tử trong mọi cấu hình; crash giữa hai hành động có thể dẫn đến xử lý lại. Thiết kế replay và idempotency vẫn cần thiết.

## 11. RetryListener để theo dõi ba trạng thái

`RetryListener` của `DefaultErrorHandler` có các callback hữu ích để tách ba giai đoạn: một lần delivery thất bại, một recovery hoàn tất và một recovery thất bại.

```java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        log.warn("Delivery failed: topic={}, partition={}, offset={}, attempt={}",
                record.topic(), record.partition(), record.offset(),
                deliveryAttempt, exception);
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        log.info("Recovery completed: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset());
    }

    @Override
    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception failure) {
        log.error("Recovery failed: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset(), failure);
    }
});
```

Các API callback cụ thể có thể khác theo phiên bản Spring Kafka, đặc biệt ở batch listener; cần dùng chữ ký phù hợp với dependency của dự án. Một `RetryListener` có thể được dùng để đếm metric và log metadata mà không cần ghi toàn bộ payload.

Ví dụ phân tách metric:

| Metric | Khi nào tăng? | Ý nghĩa |
|---|---|---|
| `kafka_listener_failure_total` | Listener xử lý thất bại. | Có lỗi nghiệp vụ/technical tại listener. |
| `kafka_record_recovered_total` | Recovery callback được gọi. | Handler đã đi qua bước recovery theo hợp đồng của recoverer. |
| `kafka_record_recovery_failed_total` | Recoverer ném lỗi. | Cần xử lý vấn đề recovery, DLT hoặc producer. |
| `kafka_dlt_publish_failure_total` | Hệ thống ghi nhận lỗi publish DLT. | Chuyển giao record lỗi sang DLT có vấn đề. |

Các tên metric ở trên là tên minh họa do ứng dụng có thể tự định nghĩa, không phải tên mặc định bắt buộc của Spring Kafka.

## 12. logRecoveryRecord trong non-blocking retry

Với `@RetryableTopic`, Spring Kafka có thể dùng `DeadLetterPublishingRecoverer` được tạo bởi hạ tầng retry-topic để **chuyển record qua retry topic hoặc đến DLT**. Trong trường hợp đó, log recovery có thể phản ánh **bước forwarding sang topic tiếp theo**, không nhất thiết chỉ phản ánh sự kiện đã vào DLT cuối cùng.

```text
orders
  |
  +--> retry-1000ms
           |
           +--> retry-2000ms
                    |
                    +--> orders-dlt
```

Khi quan sát log, cần xem `current topic`, `destination topic`, `attempt` và exception. Một dòng log của recoverer có thể xuất hiện trước khi record kết thúc toàn bộ chuỗi retry-topic.

Nếu muốn tùy biến recoverer do hạ tầng retry-topic tạo ra, Spring Kafka cung cấp các điểm cấu hình/customizer phụ thuộc phiên bản. Chẳng hạn, ở các phiên bản hỗ trợ `RetryTopicConfigurationSupport` có thể custom recoverer thay vì tự gắn một handler DLT riêng vào mọi container. Cần đảm bảo điểm mở rộng thực sự được gọi trong phiên bản sử dụng và không tạo xung đột giữa các cách bật retry-topic infrastructure.

Đừng cấu hình một `DefaultErrorHandler` riêng với recoverer gửi DLT trực tiếp cho listener chính nếu mục tiêu là sử dụng đầy đủ đường đi của `@RetryableTopic`, trừ khi đã chủ đích phối hợp các tầng retry. Nếu không, record có thể đi DLT sớm hoặc trải qua số lần retry khác với dự tính.

## 13. Quan sát record từ nguồn đến DLT

Một hệ thống vận hành tốt cần có correlation ID ổn định xuyên các topic. Ví dụ, một event có thể xuất hiện lần lượt ở `orders`, `orders-retry-1000` và `orders.DLT`, với offset khác nhau ở mỗi topic.

Log đề xuất ở lớp nghiệp vụ hoặc recovery monitoring:

```text
event_id=order-4821-created
original_topic=orders
original_partition=2
original_offset=150
current_topic=orders-retry-1000
destination_topic=orders.DLT
attempt=3
exception_type=DownstreamTimeoutException
recovery_result=PUBLISH_ATTEMPTED
```

Đây là ví dụ minh họa; `PUBLISH_ATTEMPTED` cố ý khác với `PUBLISH_CONFIRMED`. Để ghi `PUBLISH_CONFIRMED`, cần có bằng chứng producer đã nhận kết quả phù hợp từ broker theo chính sách gửi.

Các dấu hiệu nên theo dõi gồm retry rate, recovery success/failure, số record DLT nhận được, lag của consumer group chính và group retry, thời gian publish DLT, lỗi serialization, timeout và lỗi ACL. Chỉ nhìn thấy lag của topic chính giảm có thể che giấu nhiều record chưa hoàn thành nghiệp vụ đang chờ trong retry topic hoặc DLT.

## 14. Những tình huống dễ hiểu sai

| Hiện tượng | Cách hiểu sai | Cách hiểu đúng / hướng xử lý |
|---|---|---|
| Có log recovery nhưng DLT chưa có record | Nghĩ log nghĩa là broker đã lưu DLT. | Xác minh producer send result, destination, serializer, ACL và số record ở DLT. |
| Không thấy log recovery | Nghĩ không có record nào được recover. | Xem `setLogRecoveryRecord`, log level, handler/recoverer thực tế và metric DLT. |
| Record đã vào DLT nhưng nghiệp vụ chưa hoàn tất | Nghĩ recovery tương đương business success. | DLT là bước lưu record lỗi để xử lý tiếp; cần quy trình điều tra/replay. |
| Cùng record xuất hiện nhiều lần trong log | Nghĩ có nhiều event độc lập. | Có thể là retry, rebalance, replay hoặc log từ nhiều tầng; đối chiếu event ID và offset nguồn. |
| Recovery log chứa payload nhạy cảm | Bật log để dễ debug mà không kiểm soát dữ liệu. | Giảm logging raw record, dùng RetryListener với metadata và kiểm soát retention/quyền đọc. |
| `setLogRecoveryRecord` không compile | Dùng Spring Kafka trước 3.1 hoặc sai class recoverer. | Kiểm tra version và import `org.springframework.kafka.listener.DeadLetterPublishingRecoverer`. |
| Listener retry mãi sau khi DLT lỗi | Recoverer thất bại khiến backoff được reset / record giao lại. | Kiểm tra producer failure, cơ chế reset backoff và trạng thái recovery. |
| Bật logRecoveryRecord nhưng offset không tiến | Nhầm logging với commit hoặc recovery success. | Điều tra exception, send result, ack mode, `commitRecovered` và rebalance. |

## 15. Quy trình triển khai thực tế

Để đưa recovery logging vào một listener production, có thể thực hiện theo trình tự:

1. Xác định các exception có thể retry và các exception nên chuyển ngay đến recovery.
2. Chọn recoverer: ghi log, publish DLT hoặc gọi một quy trình phục hồi khác; xác định khi nào được coi là thành công.
3. Cấu hình `DefaultErrorHandler` và `BackOff` với ngân sách thời gian có giới hạn.
4. Nếu dùng `DeadLetterPublishingRecoverer` trên Spring Kafka 3.1+, cân nhắc bật `setLogRecoveryRecord(true)` khi chính sách log cho phép.
5. Đảm bảo producer gửi DLT có serializer, topic/partition, ACL và timeout phù hợp.
6. Cấu hình phát hiện lỗi publish và log/metric riêng cho recovery failure; không dùng log recovery làm bằng chứng duy nhất cho việc chuyển giao.
7. Kiểm tra ảnh hưởng đến `AckMode`, committed offset và tính idempotent của nghiệp vụ.
8. Theo dõi log/metric retry, recovery, publish DLT và consumer lag của toàn bộ các topic liên quan.
9. Chuẩn bị quy trình tiếp nhận, phân loại và replay record DLT có kiểm soát.

`logRecoveryRecord` là một tùy chọn quan sát trong `DeadLetterPublishingRecoverer`, không phải công cụ bảo đảm delivery semantics. Khi hiểu rõ ranh giới giữa **listener failure**, **recovery attempt**, **DLT publish outcome** và **offset commit**, đội vận hành có thể điều tra record lỗi đáng tin cậy hơn mà không nhầm logging với xử lý nghiệp vụ thành công.
