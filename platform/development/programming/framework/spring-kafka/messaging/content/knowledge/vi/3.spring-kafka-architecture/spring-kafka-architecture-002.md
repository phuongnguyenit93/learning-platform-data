# KafkaTemplate và lớp trừu tượng gửi tin

## 1. KafkaTemplate đứng ở đâu trong kiến trúc gửi tin?

Trong Spring Kafka, `KafkaTemplate` là API cấp cao để ứng dụng gửi record đến Kafka. Thay vì tự tạo và quản lý một Kafka producer cho từng lần gửi, ứng dụng inject một bean `KafkaTemplate<K, V>` rồi gọi các phương thức gửi tin.

`KafkaTemplate` làm việc với `ProducerFactory`. Producer factory tạo và quản lý các Kafka producer dựa trên cấu hình bootstrap server, serializer, bảo mật và những thuộc tính producer khác. Nhờ đó, mã nghiệp vụ tập trung vào sự kiện cần gửi; phần giao tiếp với Kafka được Spring Kafka đảm nhiệm.

Luồng gửi tin thường có dạng:

~~~mermaid
flowchart LR
    A["Application service"] --> B["Event publisher port"]
    B --> C["Kafka adapter"]
    C --> D["KafkaTemplate"]
    D --> E["ProducerFactory"]
    E --> F["Kafka broker"]
    F --> G["Broker acknowledgement"]
    G --> D
    D --> C
    C --> B
~~~

Trong kiến trúc này, application service phát ra yêu cầu công bố sự kiện thông qua một interface của ứng dụng. Adapter triển khai interface đó bằng `KafkaTemplate`. Khi cần đổi Kafka sang một cơ chế truyền tin khác, phần nghiệp vụ vẫn giữ nguyên interface và hợp đồng sự kiện.

`KafkaTemplate` phù hợp cho cả những thao tác gửi đơn giản lẫn các trường hợp cần điều khiển key, partition, timestamp, header, callback hoặc giao dịch Kafka.

## 2. Cấu hình KafkaTemplate và serializer

Với Spring Boot, khi có dependency Spring Kafka và cấu hình producer hợp lệ, ứng dụng thường được tự động cấu hình `ProducerFactory` và `KafkaTemplate`. Có thể khai báo các thuộc tính cơ bản trong `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all

app:
  kafka:
    topics:
      orders: orders
~~~

Trong ví dụ:

- `bootstrap-servers` chỉ định địa chỉ Kafka broker.
- `key-serializer` chuyển key kiểu `String` thành byte để producer ghi vào Kafka.
- `value-serializer` chuyển object sự kiện thành byte. `JsonSerializer` của Spring Kafka hỗ trợ chuyển object Java thành JSON.
- `acks: all` yêu cầu producer chờ xác nhận từ các replica đang nằm trong tập ISR theo quy tắc của Kafka. Mức độ bền vững thực tế còn phụ thuộc replication factor và cấu hình `min.insync.replicas` của topic/broker.
- `app.kafka.topics.orders` là cấu hình ứng dụng để adapter biết topic nghiệp vụ cần gửi.

Kiểu generic của template phải phù hợp với serializer. Ví dụ, `KafkaTemplate<String, OrderCreatedEvent>` dùng key `String` và value `OrderCreatedEvent`; nếu cấu hình serializer không thể chuyển đổi các kiểu đó, thao tác gửi sẽ thất bại.

Không nên tạo một `KafkaTemplate` mới cho từng record. Hãy dùng bean được cấu hình và quản lý bởi Spring để tái sử dụng producer factory, cấu hình và tài nguyên kết nối.

## 3. Các cách gửi record phổ biến

`KafkaTemplate` cung cấp nhiều overload để chọn mức điều khiển phù hợp.

| Cách gọi | Ý nghĩa |
|---|---|
| `send(topic, value)` | Gửi value đến topic, không chỉ định key |
| `send(topic, key, value)` | Gửi record có key để partitioner chọn partition |
| `send(topic, partition, key, value)` | Chỉ định partition đích |
| `send(topic, partition, timestamp, key, value)` | Chỉ định partition và timestamp |
| `send(ProducerRecord)` | Tự tạo record để kiểm soát đầy đủ hơn |
| `send(Message<?>)` | Gửi Spring Message và ánh xạ payload/header sang Kafka record |
| `sendDefault(...)` | Gửi đến topic mặc định đã cấu hình cho template |

Ví dụ gửi một object đơn giản:

~~~java
OrderCreatedEvent event = new OrderCreatedEvent(
    "ORD-1001",
    "CUS-42",
    System.currentTimeMillis()
);

kafkaTemplate.send("orders", event);
~~~

Nếu muốn các sự kiện của cùng một đơn hàng được định tuyến nhất quán, hãy dùng mã đơn hàng làm key:

~~~java
kafkaTemplate.send("orders", event.orderId(), event);
~~~

Khi không chỉ định partition, partitioner sử dụng key và cấu hình liên quan để chọn partition. Khi chỉ định partition tường minh, record sẽ đi đến partition đó thay vì để partitioner chọn. Chỉ nên ghim partition khi có yêu cầu rõ ràng về định tuyến.

### Dùng ProducerRecord để kiểm soát header

`ProducerRecord<K, V>` biểu diễn một record gửi đến Kafka, gồm topic, partition tùy chọn, timestamp tùy chọn, key, value và headers. Khi cần gắn correlation ID hoặc metadata của ứng dụng, có thể tạo record trực tiếp:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, OrderCreatedEvent> record =
    new ProducerRecord<>("orders", event.orderId(), event);

record.headers().add(
    "correlation-id",
    correlationId.getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record);
~~~

Header phù hợp để truyền metadata phục vụ tracing, correlation hoặc phân loại sự kiện. Không nên đưa dữ liệu nghiệp vụ cốt lõi vào header nếu consumer cần nó như một phần của payload.

### Dùng Spring Message

Nếu ứng dụng đã sử dụng Spring Messaging, có thể dùng `MessageBuilder` và các header Kafka:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreatedEvent> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, "orders")
    .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
    .setHeader("correlation-id", correlationId)
    .build();

kafkaTemplate.send(message);
~~~

Cách này hữu ích khi muốn tận dụng mô hình message của Spring. Với luồng gửi đơn giản, overload `send(topic, key, value)` thường dễ đọc hơn.

## 4. Gửi bất đồng bộ và xử lý kết quả

Gửi record đến Kafka thường là thao tác bất đồng bộ. Trong Spring Kafka 3.x, các phương thức `send(...)` trả về `CompletableFuture<SendResult<K, V>>`. Future hoàn tất khi producer nhận được kết quả gửi theo chính sách xác nhận đã cấu hình, hoặc khi thao tác gặp lỗi.

Có thể đăng ký callback bằng `whenComplete`:

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.support.SendResult;

kafkaTemplate.send("orders", event.orderId(), event)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error("Không gửi được sự kiện đơn hàng", error);
            return;
        }

        RecordMetadata metadata = result.getRecordMetadata();
        log.info(
            "Đã gửi topic={}, partition={}, offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    });
~~~

`SendResult` cung cấp record đã gửi và `RecordMetadata` do Kafka trả về. Metadata giúp xác định record được ghi vào topic, partition và offset nào.

Cần phân biệt ba mốc:

1. Ứng dụng gọi `send(...)`: yêu cầu gửi đã được tạo.
2. Future hoàn tất thành công: producer đã nhận xác nhận theo cấu hình `acks`.
3. Consumer xử lý xong sự kiện: đây là tiến trình riêng của consumer group, không được bảo đảm chỉ vì producer nhận được acknowledgement.

Vì vậy, không nên xem việc `send(...)` trả về ngay là bằng chứng sự kiện đã đến broker. Cũng không nên xem future thành công là bằng chứng dịch vụ nhận tin đã xử lý nghiệp vụ.

### Khi nào cần chờ đồng bộ?

Trong một số luồng, ứng dụng cần biết kết quả gửi trước khi tiếp tục. Có thể chờ future với timeout:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.springframework.kafka.support.SendResult;

try {
    SendResult<String, OrderCreatedEvent> result =
        kafkaTemplate.send("orders", event.orderId(), event)
            .get(5, TimeUnit.SECONDS);

    // Có thể đọc metadata khi đã nhận được kết quả gửi.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Luồng gửi Kafka bị gián đoạn", ex);
} catch (ExecutionException | TimeoutException ex) {
    throw new IllegalStateException("Không xác nhận được việc gửi sự kiện", ex);
}
~~~

Chờ bằng `get()` sẽ chặn thread hiện tại. Chỉ dùng khi luồng nghiệp vụ thực sự cần kết quả ngay và đã chọn timeout phù hợp. Không nên chặn mọi request thread chỉ để ghi log hoặc lấy offset. Nếu timeout xảy ra, kết quả cuối cùng có thể chưa rõ đối với ứng dụng; cần thiết kế retry và tính idempotent để tránh tạo tác động trùng lặp.

Lưu ý về phiên bản: Spring Kafka 3.x dùng `CompletableFuture` cho API gửi tin; các dự án Spring Kafka 2.x cũ có thể dùng `ListenableFuture`. Khi áp dụng ví dụ vào dự án hiện hữu, hãy đối chiếu phiên bản dependency thực tế.

## 5. Tạo lớp trừu tượng gửi sự kiện

Nếu controller hoặc application service gọi trực tiếp `KafkaTemplate`, mã nghiệp vụ sẽ phụ thuộc vào Spring Kafka, tên topic, serializer và cách xử lý lỗi của hạ tầng. Một lớp trừu tượng gửi tin giúp giữ ranh giới rõ ràng:

- Application service quyết định khi nào cần phát sự kiện và nội dung sự kiện.
- Interface của ứng dụng định nghĩa hợp đồng công bố sự kiện.
- Kafka adapter chuyển hợp đồng đó thành record và gửi bằng `KafkaTemplate`.
- Adapter chuyển metadata kỹ thuật thành kết quả mà phần ứng dụng cần, đồng thời truyền lỗi gửi về nơi gọi.

Ví dụ, định nghĩa một hợp đồng công bố sự kiện không phụ thuộc Spring Kafka. Đặt interface và record kết quả trong các file riêng:

~~~java
import java.util.concurrent.CompletionStage;

public interface EventPublisher<T> {
    CompletionStage<PublishReceipt> publish(String key, T event);
}
~~~

~~~java
public record PublishReceipt(
    String topic,
    int partition,
    long offset
) {}
~~~

`CompletionStage` cho phép phần ứng dụng biết kết quả bất đồng bộ mà không cần phụ thuộc trực tiếp vào `KafkaTemplate` hay `SendResult`. `PublishReceipt` chỉ chứa metadata mà ứng dụng muốn công khai.

Định nghĩa event trong file riêng:

~~~java
public record OrderCreatedEvent(
    String orderId,
    String customerId,
    long createdAtEpochMillis
) {}
~~~

Triển khai adapter bằng KafkaTemplate:

~~~java
import java.util.concurrent.CompletionStage;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class KafkaOrderEventPublisher
        implements EventPublisher<OrderCreatedEvent> {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;
    private final String topic;

    public KafkaOrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate,
            @Value("${app.kafka.topics.orders}") String topic) {
        this.kafkaTemplate = kafkaTemplate;
        this.topic = topic;
    }

    @Override
    public CompletionStage<PublishReceipt> publish(
            String key,
            OrderCreatedEvent event) {

        return kafkaTemplate.send(topic, key, event)
            .thenApply(result -> {
                RecordMetadata metadata = result.getRecordMetadata();

                return new PublishReceipt(
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
                );
            });
    }
}
~~~

Adapter chịu trách nhiệm chuyển `OrderCreatedEvent` thành record Kafka, chọn topic, truyền key và ánh xạ kết quả gửi. Nếu gửi thất bại, future trả về từ `KafkaTemplate` hoàn tất ở trạng thái exceptional; lỗi tiếp tục truyền qua chuỗi `thenApply` đến nơi gọi.

Application service chỉ cần phụ thuộc vào interface:

~~~java
import java.util.concurrent.CompletionStage;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final EventPublisher<OrderCreatedEvent> eventPublisher;

    public OrderApplicationService(
            EventPublisher<OrderCreatedEvent> eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public CompletionStage<PublishReceipt> publishCreated(
            OrderCreatedEvent event) {
        return eventPublisher.publish(event.orderId(), event);
    }
}
~~~

Cách tổ chức này giúp kiểm thử application service bằng một implementation giả của `EventPublisher`. Kiểm thử adapter riêng để xác minh topic, key, payload, header và cách ánh xạ metadata sang kết quả.

Trong một ứng dụng có nhiều loại sự kiện, có thể dùng một interface tổng quát như ví dụ trên hoặc định nghĩa các port theo nghiệp vụ, chẳng hạn `OrderEventPublisher`. Port theo nghiệp vụ thường dễ diễn đạt quy tắc và hạn chế việc application service tự chọn tên topic. Chọn cách nào tùy vào số lượng event và ranh giới module; không cần tạo nhiều lớp wrapper nếu chúng không mang thêm ý nghĩa.

## 6. Xử lý lỗi và những giới hạn cần hiểu

Lỗi gửi tin có thể xuất hiện do nhiều nguyên nhân: broker không khả dụng, lỗi kết nối, timeout, lỗi xác thực, topic không phù hợp hoặc serializer không chuyển đổi được payload. Vì thao tác bất đồng bộ, lỗi thường được quan sát qua future. Phần gọi cần xử lý lỗi thay vì bỏ qua future.

Ví dụ xử lý kết quả ở nơi gọi:

~~~java
eventPublisher.publish(event.orderId(), event)
    .whenComplete((receipt, error) -> {
        if (error != null) {
            log.error("Công bố OrderCreated thất bại", error);
            return;
        }

        log.info(
            "OrderCreated đã được xác nhận tại {}-{}",
            receipt.topic(),
            receipt.partition()
        );
    });
~~~

Một số nguyên tắc thực tế:

- **Không bỏ qua lỗi:** nếu không quan sát future, ứng dụng có thể bỏ lỡ lỗi gửi bất đồng bộ.
- **Không retry vô hạn ở tầng ứng dụng:** producer đã có cơ chế retry theo cấu hình; retry thêm ở tầng nghiệp vụ cần giới hạn số lần, backoff và chính sách xử lý khi hết lượt.
- **Thiết kế idempotent:** một lần gửi lại có thể tạo record hoặc hiệu ứng nghiệp vụ lặp. Consumer nên có cách nhận diện sự kiện đã xử lý, ví dụ bằng event ID hoặc khóa nghiệp vụ.
- **Theo dõi kết quả:** ghi log có correlation ID và đo số lần gửi thành công, thất bại, độ trễ gửi và timeout.
- **Không nhầm acknowledgement với xử lý nghiệp vụ:** producer xác nhận việc ghi record; consumer cần xác nhận tiến độ xử lý riêng.

Producer idempotence và `acks` hỗ trợ độ tin cậy của việc gửi từ producer theo phạm vi bảo đảm của Kafka. Chúng không tự làm cho toàn bộ quy trình nghiệp vụ, chẳng hạn ghi database rồi gửi sự kiện, trở thành một giao dịch nguyên tử.

Nếu ứng dụng cần đảm bảo thay đổi database và sự kiện Kafka không bị lệch nhau khi một trong hai thao tác thất bại, hãy tìm hiểu Transactional Outbox. Nếu cần giao dịch Kafka cho nhiều record Kafka, Spring Kafka cung cấp cấu hình producer transaction và các API giao dịch phù hợp. Đây là các chủ đề riêng; chỉ thêm transaction vào `KafkaTemplate` không tự tạo giao dịch phân tán với một database thông thường.

## 7. Kiểm thử lớp gửi tin

Nên kiểm thử hai ranh giới khác nhau:

| Phần cần kiểm thử | Cách tiếp cận | Điều cần xác minh |
|---|---|---|
| Application service | Fake hoặc mock `EventPublisher` | Nghiệp vụ phát đúng event, đúng key và phản ứng đúng khi future thành công/thất bại |
| Kafka adapter | Kafka test broker, Embedded Kafka hoặc Testcontainers | Record thực sự được gửi với topic, key, payload và header mong muốn |

Với kiểm thử adapter, hãy đọc record từ topic bằng một consumer thuộc group thử nghiệm riêng. Chờ có giới hạn thời gian thay vì dùng sleep cố định, để bài kiểm thử ổn định hơn. Nếu chỉ mock `KafkaTemplate`, bài kiểm thử xác minh cách adapter gọi API nhưng không xác minh serializer, kết nối hoặc broker.

Với kiểm thử lỗi, có thể mô phỏng future hoàn tất exceptional để xác nhận application service không nuốt lỗi. Với kiểm thử tích hợp, cần kiểm tra cả trường hợp gửi thành công và broker không sẵn sàng hoặc cấu hình serialization sai.

## 8. Checklist khi thiết kế API gửi tin

Trước khi đưa lớp gửi tin vào vận hành, hãy kiểm tra:

- [ ] `KafkaTemplate<K, V>` có kiểu generic khớp serializer và payload thực tế.
- [ ] Topic được cấu hình tập trung, không rải rác trong mã nghiệp vụ.
- [ ] Key được chọn theo yêu cầu phân vùng và thứ tự của thực thể nghiệp vụ.
- [ ] Metadata cần thiết như correlation ID được đưa vào header hoặc payload có chủ đích.
- [ ] Future được quan sát và lỗi được chuyển đến nơi có thể xử lý.
- [ ] Luồng đồng bộ có timeout rõ ràng; luồng bất đồng bộ không chặn thread không cần thiết.
- [ ] Retry, idempotence và xử lý trùng lặp được thiết kế theo yêu cầu nghiệp vụ.
- [ ] Kiểm thử tách biệt hợp đồng application và tích hợp Kafka adapter.

`KafkaTemplate` cung cấp API gửi tin nhất quán cho ứng dụng Spring Kafka. Khi đặt nó sau một lớp trừu tượng theo nghiệp vụ, ứng dụng có thể giữ mã nghiệp vụ gọn, kiểm thử độc lập và kiểm soát rõ kết quả gửi. Điều quan trọng là hiểu chính xác future xác nhận điều gì, quản lý lỗi gửi ra sao và không nhầm việc broker nhận record với việc consumer đã hoàn tất xử lý.
