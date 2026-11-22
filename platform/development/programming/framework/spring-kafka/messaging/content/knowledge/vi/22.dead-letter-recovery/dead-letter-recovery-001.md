# Dead-letter topic là gì?

Trong một luồng Kafka, có những record không thể xử lý thành công dù consumer đã thử lại theo chính sách. Ví dụ, payload sai định dạng, dữ liệu vi phạm quy tắc nghiệp vụ hoặc một lỗi phụ thuộc đã vượt quá số lần retry cho phép. Nếu cứ giữ record đó ở luồng chính, consumer có thể liên tục gặp lại lỗi và làm chậm các record phía sau.

**Dead-letter topic (DLT)** là một Kafka topic riêng dùng để lưu các record đã thất bại và được chuyển ra khỏi luồng xử lý chính. DLT giúp consumer tiếp tục xử lý dữ liệu bình thường, trong khi đội phát triển vẫn giữ lại payload cùng metadata về nguồn và nguyên nhân lỗi để điều tra, sửa dữ liệu hoặc phát lại sau này.

DLT không phải một loại topic đặc biệt do Kafka định nghĩa. Nó là topic Kafka thông thường, được ứng dụng và Spring Kafka sử dụng theo quy ước để lưu record lỗi. Vì vậy, DLT cần được tạo, phân quyền, cấu hình retention, giám sát và vận hành như các topic khác.

## 1. Vì sao cần dead-letter topic?

Giả sử consumer đọc topic `orders.events`. Một record có `orderId` không hợp lệ khiến listener ném exception. Nếu record luôn được retry mà không có giới hạn, consumer có thể không tiến tới các record tiếp theo trên partition đó. Nếu bỏ qua record mà không lưu lại, đội vận hành sẽ mất dữ liệu cần thiết để điều tra và khắc phục.

DLT giải quyết bài toán bằng cách chuyển record lỗi sang một topic khác sau khi chính sách retry kết thúc hoặc khi lỗi được phân loại là không thể retry.

```text
orders.events
      |
      v
  @KafkaListener
      |
      +---- xử lý thành công ----------------------> commit theo AckMode
      |
      +---- xử lý thất bại
                |
                v
        Exception classification
                |
          +-----+------+
          |            |
       Retryable    Non-retryable
          |            |
       BackOff         |
          |            |
       Retry lại       |
          |            |
       Hết retry       |
          +-----+------+
                |
                v
       DeadLetterPublishingRecoverer
                |
                v
          orders.events.DLT
                |
                v
       Điều tra / sửa / replay
```

Khi recoverer chuyển record thành công, error handler có thể xác nhận record nguồn đã được xử lý theo acknowledgement mode và cấu hình commit. Nếu việc publish DLT thất bại, cần để lỗi đó được báo lại và xử lý theo chính sách, tránh đánh dấu record nguồn đã recover trong khi bản sao DLT chưa được lưu.

## 2. DLT chứa những thông tin gì?

Thông thường, record được gửi sang DLT giữ lại key và payload của record gốc, đồng thời có thêm headers mô tả nguồn gốc và lỗi.

| Thành phần | Ý nghĩa |
|---|---|
| Key | Key của record nguồn, nếu có |
| Value | Payload gốc hoặc byte gốc tùy đường đi serialize/deserialize |
| Original topic | Topic nơi record phát sinh lỗi |
| Original partition | Partition nguồn |
| Original offset | Offset của record nguồn |
| Original timestamp | Timestamp của record nguồn nếu có |
| Exception class | Tên lớp exception gây lỗi |
| Exception message | Thông điệp lỗi |
| Exception stack trace | Stack trace phục vụ chẩn đoán, nếu được cấu hình ghi header |
| Consumer group | Group đã xử lý record nguồn, nếu có metadata tương ứng |

Spring Kafka sử dụng các header có tên quy ước, ví dụ `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET`, `KafkaHeaders.DLT_EXCEPTION_FQCN` và `KafkaHeaders.DLT_EXCEPTION_MESSAGE`. Các header cụ thể phụ thuộc phiên bản và recoverer đang sử dụng.

Metadata nguồn rất quan trọng khi cần truy ngược record. Một record DLT có offset mới trong topic DLT; offset đó không phải offset ban đầu trong topic nguồn. Hãy dùng original topic/partition/offset headers để xác định vị trí phát sinh lỗi.

## 3. DLT khác retry topic như thế nào?

Retry topic và DLT đều là topic Kafka thông thường, nhưng có mục đích khác nhau:

| Tiêu chí | Retry topic | Dead-letter topic |
|---|---|---|
| Mục đích | Giữ record để thử xử lý lại sau một khoảng chờ | Lưu record đã hết retry hoặc không được retry |
| Thời điểm chuyển vào | Khi lỗi được phép retry theo chính sách non-blocking | Khi retry kết thúc hoặc exception không retry được |
| Xử lý tiếp | Consumer retry đọc lại record | Con người hoặc luồng xử lý DLT điều tra và quyết định bước tiếp theo |
| Kết quả mong muốn | Quay lại xử lý nghiệp vụ bình thường | Cô lập lỗi để không chặn luồng chính |

Với blocking retry, `DefaultErrorHandler` thường seek consumer về record lỗi và thử lại tại chỗ. Khi hết retry, recoverer có thể gửi record sang DLT. Với non-blocking retry, `@RetryableTopic` tạo các retry topic theo backoff và chuyển record tới DLT khi hết attempts.

DLT không thay thế retry. Retry phù hợp với lỗi có khả năng tự phục hồi; DLT phù hợp để cô lập record vẫn không thể xử lý sau chính sách đã định.

## 4. Spring Kafka gửi record sang DLT bằng cách nào?

Với record listener, Spring Kafka thường kết hợp `DefaultErrorHandler` và `DeadLetterPublishingRecoverer`:

- `DefaultErrorHandler` nhận exception từ listener.
- Exception classifier quyết định lỗi có retry được hay không.
- `BackOff` quy định thời gian chờ và số lần retry.
- Khi cần recover, `DeadLetterPublishingRecoverer` tạo record mới và publish tới DLT.

Ví dụ cấu hình:

```java
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
        recoverer.setFailIfSendResultIsError(true);

        var backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }
}
```

Trong ví dụ, consumer thử xử lý record ban đầu rồi có tối đa hai lần retry, chờ một giây giữa các lần thử. Nếu vẫn thất bại, recoverer publish record sang DLT. `setFailIfSendResultIsError(true)` yêu cầu recoverer báo lỗi nếu kết quả gửi DLT thất bại; hãy kiểm tra API theo phiên bản Spring Kafka của dự án.

Gắn handler vào container factory:

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

Listener sử dụng factory đó:

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

Các lớp `OrderEvent`, `orderService` và cấu hình serializer/deserializer là thành phần của ứng dụng minh họa. Nếu listener dùng một container factory khác, phải gắn `DefaultErrorHandler` vào đúng factory đó.

## 5. Tên DLT và cách định tuyến mặc định

Khi dùng `new DeadLetterPublishingRecoverer(kafkaTemplate)` mà không cung cấp destination resolver riêng, Spring Kafka mặc định định tuyến record tới topic có hậu tố `.DLT` và partition tương ứng với partition nguồn.

Ví dụ:

```text
orders.events, partition 2, offset 105
             |
             | recover
             v
orders.events.DLT, partition 2
```

Vì recoverer giữ partition tương ứng theo mặc định, topic DLT cần có partition đích tồn tại. Cách đơn giản là tạo DLT có số partition ít nhất bằng topic nguồn. Nếu topic nguồn có sáu partition, ví dụ DLT cũng nên có ít nhất sáu partition.

Có thể tạo topic bằng Spring Kafka `TopicBuilder`:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
class DeadLetterTopicConfiguration {

    @Bean
    NewTopic ordersDeadLetterTopic() {
        return TopicBuilder.name("orders.events.DLT")
                .partitions(6)
                .replicas(1)
                .build();
    }
}
```

Replication factor `1` trong ví dụ chỉ phù hợp môi trường local hoặc demo. Production cần chọn replication factor, min ISR và retention theo yêu cầu độ bền, dung lượng và chính sách vận hành. Nếu cluster không bật auto topic creation, hãy tạo DLT trước khi record lỗi được publish.

### Tùy chỉnh destination resolver

Có thể định tuyến DLT theo quy ước riêng, ví dụ đổi hậu tố hoặc gom lỗi theo loại topic:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

var recoverer = new DeadLetterPublishingRecoverer(
        kafkaTemplate,
        (record, exception) -> new TopicPartition(
                record.topic() + ".dead-letter",
                record.partition()
        )
);
```

Nếu định tuyến sang partition khác hoặc gom nhiều topic nguồn vào một DLT, phải bảo đảm partition đích hợp lệ và metadata nguồn vẫn đủ để truy vết. Không nên chọn partition theo phép modulo tùy tiện nếu chưa tính tới số partition đích và thứ tự nghiệp vụ.

## 6. DLT cho non-retryable exception và lỗi hết retry

Hai trường hợp phổ biến khiến record được gửi DLT:

1. **Non-retryable exception:** lỗi dữ liệu hoặc lỗi nghiệp vụ không thể tự phục hồi bằng cách thử lại, ví dụ `InvalidOrderException`.
2. **Retry exhausted:** lỗi ban đầu có thể retry, nhưng đã vượt số lần hoặc thời gian thử lại mà vẫn thất bại.

Có thể khai báo exception không retry trên `DefaultErrorHandler`:

```java
handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        IllegalArgumentException.class
);
```

Các lỗi khác vẫn dùng chính sách retry/backoff đã cấu hình. Sau khi recoverer gửi DLT thành công, container xử lý commit offset theo acknowledgement mode và các thiết lập của error handler. Nếu publish DLT thất bại, recoverer nên báo lỗi để record nguồn chưa bị xác nhận nhầm là đã chuyển thành công.

Không nên xem DLT là nơi gửi mọi lỗi ngay lập tức. Nếu dependency chỉ mất kết nối trong vài giây, retry có backoff có thể khôi phục được record mà không cần thao tác thủ công.

## 7. DLT khi dùng @RetryableTopic

Spring Kafka hỗ trợ non-blocking retry bằng `@RetryableTopic`. Annotation này cấu hình retry topics và DLT cho một listener. Sau khi record đi hết các lần thử, framework chuyển nó tới DLT.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
class PaymentListener {

    private static final Logger log = LoggerFactory.getLogger(PaymentListener.class);

    private final PaymentService paymentService;

    PaymentListener(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(delay = 1_000, multiplier = 2.0),
            dltTopicSuffix = ".DLT"
    )
    @KafkaListener(topics = "payments.events", groupId = "payment-projection")
    public void consume(PaymentEvent event) {
        paymentService.process(event);
    }

    @DltHandler
    public void handleDlt(PaymentEvent event) {
        log.error("Payment event moved to DLT: paymentId={}", event.paymentId());
    }
}
```

Trong ví dụ, `attempts = "4"` biểu thị tổng số lần thử, bao gồm lần xử lý ban đầu. Khi hết attempts, record được chuyển tới topic `payments.events.DLT` theo suffix đã cấu hình. Nếu không khai báo suffix, `@RetryableTopic` có quy ước mặc định riêng (thường là `-dlt`), khác với hậu tố `.DLT` của `DeadLetterPublishingRecoverer` mặc định.

`@DltHandler` là phương thức nhận record từ DLT trong cấu hình retry topic tương ứng. Có thể dùng nó để ghi nhận, cảnh báo hoặc tạo yêu cầu xử lý thủ công. Nếu chỉ cần DLT là kho lưu trữ, có thể tạo một listener riêng đọc topic DLT thay vì xử lý ngay trong cùng lớp.

Non-blocking retry có thể làm record phía sau được xử lý trước record đang chờ ở retry topic. Nếu nghiệp vụ yêu cầu thứ tự chặt theo key hoặc partition, cần cân nhắc blocking retry và DLT thay vì chỉ chọn retry topic vì thời gian chờ không chặn luồng chính.

## 8. Đọc và điều tra record trong DLT

DLT là topic bình thường, vì vậy có thể đọc bằng `@KafkaListener` như các topic khác. Nên dùng consumer group riêng cho luồng điều tra để không ảnh hưởng group xử lý topic chính.

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.stereotype.Component;

@Component
class OrderDeadLetterListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderDeadLetterListener.class);

    @KafkaListener(
            topics = "orders.events.DLT",
            groupId = "orders-dlt-inspector"
    )
    public void consume(ConsumerRecord<String, String> record) {
        String originalTopic = readHeader(record, KafkaHeaders.DLT_ORIGINAL_TOPIC);

        log.error(
                "Dead letter received: dltTopic={}, originalTopic={}, key={}, value={}",
                record.topic(),
                originalTopic,
                record.key(),
                record.value()
        );
    }

    private String readHeader(ConsumerRecord<String, String> record, String name) {
        Header header = record.headers().lastHeader(name);
        if (header == null || header.value() == null) {
            return null;
        }
        return new String(header.value(), StandardCharsets.UTF_8);
    }
}
```

Khi đọc header, nên dùng hằng số `KafkaHeaders.DLT_ORIGINAL_TOPIC` của Spring Kafka thay vì tự gõ tên header. Tên header thực tế do Spring Kafka định nghĩa; hãy dùng API/hằng số của phiên bản dự án. Tránh ghi payload nhạy cảm vào log production; log ID, topic, partition, offset và exception metadata thường đủ để truy vết.

Ví dụ dùng hằng số Spring Kafka:

```java
import org.springframework.kafka.support.KafkaHeaders;

Header originalTopicHeader = record.headers()
        .lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC);
```

Khi điều tra, cần lưu tối thiểu:

- Topic, partition và offset nguồn.
- Consumer group đã xử lý record.
- Loại exception, message và stack trace nếu được lưu.
- Thời điểm lỗi và số lần delivery/retry nếu metadata có sẵn.
- Trạng thái khắc phục và người/tiến trình thực hiện replay.

## 9. Serialization của DLT producer

Record DLT được gửi bằng producer nên key/value phải serialize được với cấu hình producer. Trong luồng bình thường, consumer có thể đã deserialize value thành object Java; recoverer sau đó cần serializer tương thích để gửi object đó sang DLT.

Với lỗi deserialization, payload gốc có thể chỉ còn byte array vì không tạo được object. Khi đó producer DLT phải hỗ trợ cả kiểu object thông thường và `byte[]` nếu cùng một recoverer xử lý cả hai loại record. Spring Kafka có thể dùng `DelegatingByTypeSerializer` để chọn serializer theo kiểu runtime.

Ví dụ ý tưởng cấu hình:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

Map<Class<?>, org.apache.kafka.common.serialization.Serializer<?>> delegates =
        new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(Object.class, new JsonSerializer<>());

var valueSerializer = new DelegatingByTypeSerializer(delegates);
```

Đây là minh họa chọn serializer theo kiểu; khi cấu hình producer factory thực tế, cần bảo đảm generic type, thứ tự match và serializer key/value tương thích với phiên bản Spring Kafka đang dùng. Nếu hệ thống chỉ xử lý JSON hợp lệ và không đưa raw deserialization error qua cùng producer, có thể dùng serializer đơn giản hơn.

Không giả định mọi record DLT đều là object Java đã deserialize. Với dữ liệu lỗi, giữ byte gốc thường cần thiết để điều tra hoặc sửa rồi phát lại.

## 10. DLT publish thất bại thì sao?

Việc chuyển record sang DLT chỉ hoàn tất khi producer gửi record thành công theo chính sách xác nhận đã cấu hình. Nếu DLT topic không tồn tại, partition đích không hợp lệ, ACL từ chối hoặc broker không sẵn sàng, publish có thể thất bại.

Một số nguyên tắc vận hành:

1. Tạo DLT và partition phù hợp trước khi bật consumer production.
2. Cấp quyền ghi DLT cho producer/recoverer và quyền đọc cho consumer DLT.
3. Cấu hình recoverer báo lỗi khi send result thất bại, nếu phiên bản hỗ trợ.
4. Theo dõi lỗi publish DLT và không commit record nguồn như thể recovery đã hoàn tất.
5. Kiểm thử cả trường hợp DLT broker/topic không khả dụng.

Nếu DLT publish thất bại nhưng record nguồn vẫn bị commit, record có thể mất khỏi luồng xử lý và không có bản sao để điều tra. Đây là lý do cần quan sát send result của recoverer và xác minh hành vi commit theo acknowledgement mode.

Với transactional listener, DLT publish có thể được phối hợp trong Kafka transaction nếu cấu hình transaction manager và recoverer đúng cách. Hãy phân biệt transaction của Kafka với side effect ở database hoặc HTTP service; DLT publish trong Kafka transaction không tự động bao gồm tài nguyên bên ngoài Kafka.

## 11. Replay record từ DLT

DLT không tự động sửa dữ liệu và cũng không tự động đưa record trở lại topic nguồn. Sau khi tìm ra nguyên nhân, có thể chọn một trong các cách:

- Sửa dữ liệu hoặc schema rồi publish record đã hiệu chỉnh vào topic nghiệp vụ.
- Dùng một replay consumer đọc DLT và gửi record sang topic nguồn hoặc topic phục hồi.
- Chạy công cụ replay có kiểm soát, giới hạn theo topic/partition/offset hoặc event ID.
- Bỏ record nếu đã xác định không còn giá trị nghiệp vụ, đồng thời lưu audit về quyết định.

Khi replay, record được publish lại sẽ có offset mới. Nên giữ metadata nguồn trong custom headers hoặc payload audit để biết nó bắt nguồn từ DLT nào và offset cũ nào.

Replay có thể tạo side effect lặp. Ví dụ, lần xử lý đầu đã ghi database thành công nhưng lỗi xảy ra trước commit offset, sau đó record bị chuyển DLT hoặc được replay. Hệ thống nghiệp vụ cần idempotency bằng event ID, unique constraint, upsert hoặc inbox pattern để tránh tạo đơn hàng/thanh toán trùng.

Không nên replay hàng loạt trực tiếp vào production khi chưa đánh giá tốc độ phát lại, consumer capacity, thứ tự key và tác động tới dịch vụ phụ thuộc. Hãy thử với một nhóm nhỏ, xác nhận kết quả rồi mới mở rộng.

## 12. Retention, bảo mật và giám sát DLT

DLT thường được giữ lâu hơn luồng chính để đội vận hành có thời gian điều tra, nhưng không nên lưu vô thời hạn mà không có kế hoạch dung lượng và dữ liệu.

Các khía cạnh cần cấu hình:

| Hạng mục | Câu hỏi vận hành |
|---|---|
| Retention | Giữ record lỗi bao lâu để điều tra và replay? |
| Replication | Cần bao nhiêu replica để chịu lỗi broker? |
| ACL | Dịch vụ nào được publish, đọc và xóa dữ liệu DLT? |
| Encryption | Dữ liệu nhạy cảm có được bảo vệ khi truyền và lưu không? |
| Monitoring | DLT tăng đột biến, tuổi record lớn nhất và publish failure có được cảnh báo không? |
| Ownership | Ai chịu trách nhiệm điều tra và quyết định replay/bỏ record? |

Các metric nên theo dõi gồm số record được chuyển vào DLT theo topic và exception class, tuổi record lâu nhất, consumer lag của DLT inspector, số record replay thành công/thất bại và lỗi publish DLT. Một đợt tăng đột biến DLT thường báo hiệu producer thay đổi schema, lỗi nghiệp vụ hoặc dependency gặp sự cố.

Không ghi token, mật khẩu, thông tin xác thực hoặc dữ liệu cá nhân nhạy cảm vào exception message hay log DLT nếu không cần thiết. Payload DLT có thể chứa dữ liệu nghiệp vụ gốc nên phải áp dụng quyền truy cập và retention phù hợp.

## 13. Những nhầm lẫn thường gặp

1. **Cho rằng DLT là loại topic đặc biệt của Kafka.** DLT chỉ là topic thông thường được dùng theo quy ước.
2. **Cho rằng DLT thay thế retry.** Retry xử lý lỗi có thể tự phục hồi; DLT cô lập record sau khi chính sách retry kết thúc hoặc lỗi không retry được.
3. **Cho rằng gửi DLT thành công đồng nghĩa payload đã được sửa.** DLT chỉ lưu record và metadata lỗi để điều tra hoặc replay.
4. **Cho rằng offset trên DLT là offset nguồn.** Record DLT có offset mới; cần đọc original offset headers.
5. **Không tạo đủ partition cho DLT.** Resolver mặc định có thể giữ partition nguồn nên partition đích phải tồn tại.
6. **Cho rằng mọi DLT đều có hậu tố giống nhau.** `DeadLetterPublishingRecoverer` mặc định và `@RetryableTopic` có quy ước suffix khác nhau; hãy cấu hình rõ khi cần thống nhất.
7. **Bỏ qua lỗi publish DLT.** Nếu gửi DLT thất bại mà record nguồn vẫn được xác nhận, có thể mất bản ghi cần điều tra.
8. **Cho rằng replay không gây xử lý lặp.** Side effect bên ngoài Kafka có thể được thực hiện lại; cần idempotency.
9. **Không tính retention và bảo mật.** DLT có thể giữ payload nghiệp vụ và stack trace trong thời gian dài.

DLT là vùng lưu trữ có kiểm soát cho record không thể xử lý trong luồng chính. Trong Spring Kafka, `DeadLetterPublishingRecoverer` và `@RetryableTopic` giúp chuyển record lỗi tới topic riêng, kèm metadata để truy vết. Một thiết kế DLT tốt cần bảo đảm publish được xác nhận, partition và serializer tương thích, có người chịu trách nhiệm điều tra, đồng thời có quy trình replay idempotent và giám sát retention rõ ràng.
