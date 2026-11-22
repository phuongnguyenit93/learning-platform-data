# Ordering trong một producer

Kafka ghi record vào log của từng partition theo một thứ tự xác định. Khi một producer gửi nhiều record đến cùng partition, producer có thể bảo toàn thứ tự gửi của nó trong partition đó. Đây là nền tảng để phát sự kiện theo trình tự như tạo đơn hàng, xác nhận thanh toán và cập nhật trạng thái.

Tuy nhiên, bảo đảm này có phạm vi cụ thể. Nó không tạo thứ tự tổng thể giữa nhiều partition, không tự sắp xếp các lời gọi đồng thời từ nhiều thread theo thứ tự nghiệp vụ và cũng không thiết lập thứ tự nhân quả giữa nhiều producer độc lập. Muốn hệ thống giữ đúng trình tự, cần phối hợp key, partitioning, cấu hình producer, cách gửi bất đồng bộ và thiết kế luồng nghiệp vụ.

## 1. Ordering trong Kafka có phạm vi nào?

Mỗi partition là một log có thứ tự. Kafka gắn offset tăng dần cho record được append vào partition đó. Consumer đọc một partition theo thứ tự offset.

Ví dụ topic `orders` có hai partition:

```text
orders-0:
offset 0 -> OrderCreated(order-101)
offset 1 -> PaymentRequested(order-101)
offset 2 -> OrderConfirmed(order-101)

orders-1:
offset 0 -> OrderCreated(order-202)
offset 1 -> PaymentRequested(order-202)
```

Trong partition `orders-0`, record ở offset 0 đứng trước offset 1 và offset 2. Tương tự, `orders-1` có thứ tự riêng. Không tồn tại một offset chung để kết luận record ở `orders-0` offset 2 xảy ra trước hay sau record ở `orders-1` offset 1.

Các nguyên tắc cần nhớ:

- Kafka bảo đảm thứ tự trong một partition, không bảo đảm thứ tự tổng thể giữa các partition.
- Offset chỉ có ý nghĩa trong phạm vi topic và partition.
- Producer có thể gửi record vào partition bằng key, partitioner hoặc chỉ định partition tường minh.
- Một producer có thể giữ thứ tự gửi của chính nó đến cùng partition khi cấu hình retry không làm mất bảo đảm thứ tự.
- Nhiều producer cùng gửi vào một partition sẽ được Kafka append theo thứ tự broker nhận và xử lý request; Kafka không biết thứ tự nghiệp vụ mà ứng dụng mong muốn.

## 2. Một producer gửi nhiều record đến cùng partition

`KafkaProducer` gửi bất đồng bộ. Khi ứng dụng gọi `send()`, record được serialize và đưa vào buffer; producer gom record thành batch theo partition rồi gửi request đến broker. Ứng dụng không cần đợi từng record hoàn tất mới gửi record kế tiếp.

Nếu các lần gọi `send()` diễn ra tuần tự trên cùng producer và cùng partition, producer duy trì thứ tự của các record đó khi ghi vào partition, với điều kiện cấu hình retry không làm mất bảo đảm thứ tự.

Ví dụ một service phát ba sự kiện của cùng đơn hàng:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    void publishOrderLifecycle(String orderId) {
        kafkaTemplate.send(
                "orders",
                orderId,
                new OrderCreated(orderId)
        );

        kafkaTemplate.send(
                "orders",
                orderId,
                new PaymentRequested(orderId)
        );

        kafkaTemplate.send(
                "orders",
                orderId,
                new OrderConfirmed(orderId)
        );
    }
}
```

Với partitioner mặc định và cùng key `orderId`, ba record thường được đưa đến cùng partition. Cùng producer gửi chúng theo thứ tự lời gọi. Khi idempotence được bật và các ràng buộc cấu hình hợp lệ, producer duy trì thứ tự trong trường hợp phải retry request.

Không cần gọi `get()` sau mỗi lần `send()` chỉ để giữ thứ tự trong một luồng gửi tuần tự. Chờ từng future sẽ làm giảm khả năng batching và throughput. Hãy quan sát kết quả bất đồng bộ, đồng thời cấu hình producer để bảo đảm thứ tự khi retry.

## 3. Key giúp gom sự kiện của cùng thực thể

Với partitioner mặc định, key được hash để chọn partition. Những record có cùng key thường được đưa đến cùng partition trong cùng một trạng thái topic và cùng partitioning strategy.

Ví dụ:

```java
kafkaTemplate.send("orders", "order-101", createdEvent);
kafkaTemplate.send("orders", "order-101", paymentRequestedEvent);
kafkaTemplate.send("orders", "order-101", confirmedEvent);

kafkaTemplate.send("orders", "order-202", createdAnotherOrder);
```

Các sự kiện của `order-101` có thể cùng vào một partition, còn `order-202` có thể vào partition khác. Nhờ vậy, nhiều đơn hàng được xử lý song song giữa các partition, trong khi sự kiện của từng đơn hàng giữ cùng một luồng thứ tự.

Key không phải là partition number. Nó là đầu vào cho partitioner. Cần lưu ý:

- Key phải ổn định theo thực thể cần giữ thứ tự, ví dụ `orderId` hoặc `accountId`.
- Nếu key là `null`, partitioner có thể dùng cơ chế sticky partitioning để phân phối batch; không nên dựa vào null key để giữ thứ tự theo thực thể.
- Có thể chỉ định partition trực tiếp trong `ProducerRecord`, nhưng khi đó ứng dụng phải tự chịu trách nhiệm chọn đúng partition.
- Thay đổi số partition có thể làm key hash sang partition khác. Record cũ vẫn nằm ở partition cũ, record mới có thể vào partition mới, làm mất thứ tự liên tục theo key giữa hai partition.

Ví dụ gửi đến partition tường minh:

```java
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, OrderEvent> record =
        new ProducerRecord<>(
                "orders",
                2,
                "order-101",
                new PaymentRequested("order-101")
        );

kafkaTemplate.send(record);
```

Chỉ dùng partition tường minh khi có quy tắc phân vùng rõ ràng. Hard-code partition number trong nhiều service khiến việc tăng partition hoặc thay đổi topology trở nên khó khăn.

## 4. Idempotent producer bảo vệ thứ tự khi retry

Producer gửi request đến broker có thể gặp lỗi mạng hoặc timeout. Có trường hợp broker đã ghi batch nhưng phản hồi không đến được producer. Producer không biết chắc batch đã được ghi hay chưa nên có thể retry.

Khi có nhiều request đang in-flight, nếu một batch trước bị lỗi tạm thời nhưng batch sau đã được ghi thành công, retry không được kiểm soát có thể làm batch sau xuất hiện trước batch trước. Đây là nguy cơ reorder khi idempotence bị tắt.

Kafka hỗ trợ idempotent producer. Broker cấp Producer ID và producer sequence cho các batch; khi retry, broker nhận diện sequence để loại bỏ bản ghi gửi lại và giữ đúng thứ tự của producer trong partition.

Các cấu hình liên quan:

| Thuộc tính | Giá trị khuyến nghị khi cần ordering qua retry | Vai trò |
|---|---:|---|
| `enable.idempotence` | `true` | Bật cơ chế producer sequence và loại bỏ duplicate do retry nội bộ |
| `acks` | `all` | Chờ xác nhận theo ISR hiện tại |
| `retries` | Lớn hơn `0` | Cho phép producer retry lỗi có thể phục hồi |
| `max.in.flight.requests.per.connection` | Không lớn hơn `5` | Giữ tương thích với giới hạn idempotent producer |

Khi bật idempotence, Kafka yêu cầu các cấu hình liên quan tương thích. Với các phiên bản client hiện đại, producer có thể tự áp dụng một số mặc định phù hợp; khai báo rõ ràng giúp cấu hình dễ kiểm tra và tránh bị thay đổi ngoài ý muốn.

Idempotence bảo vệ retry nội bộ của cùng producer session. Nó không tự loại bỏ duplicate do ứng dụng chủ động gọi `send()` lại sau khi future báo lỗi, cũng không phối hợp thứ tự giữa nhiều producer độc lập.

## 5. Cấu hình producer trong Spring Boot

Có thể cấu hình producer bằng `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[retries]": 2147483647
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
```

Các khóa native Kafka có dấu chấm được giữ nguyên bằng cú pháp bracket trong map properties của Spring Boot. Hãy kiểm tra cấu hình thực tế được bind ở phiên bản Spring Boot của ứng dụng.

Có thể thiết lập trực tiếp khi tự tạo `ProducerFactory`:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

Map<String, Object> properties = new HashMap<>();

properties.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
);
properties.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
);
properties.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class
);
properties.put(ProducerConfig.ACKS_CONFIG, "all");
properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
properties.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
properties.put(
        ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
        5
);
properties.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
properties.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);

ProducerFactory<String, OrderEvent> producerFactory =
        new DefaultKafkaProducerFactory<>(properties);
```

`delivery.timeout.ms` là giới hạn tổng thời gian gửi thành công hoặc thất bại sau khi producer bắt đầu gửi, bao gồm thời gian chờ và retry. `request.timeout.ms` giới hạn thời gian chờ phản hồi cho một request. Hai giá trị phải tương thích với nhau và với `linger.ms`; không đặt delivery timeout nhỏ hơn tổng thời gian request và linger theo yêu cầu của Kafka client.

`acks=all` không có nghĩa mọi replica được gán đều luôn xác nhận. Broker chờ các replica hiện thuộc ISR theo cơ chế Kafka. Có thể kết hợp `min.insync.replicas` ở cấp topic để đặt ngưỡng tối thiểu về độ bền khi ghi.

## 6. Điều gì xảy ra nếu tắt idempotence?

Giả sử cùng producer gửi hai batch đến cùng partition:

```text
Thứ tự gửi:
  Batch A: OrderCreated
  Batch B: PaymentRequested

Tình huống lỗi khi idempotence tắt:
  1. Broker chưa xác nhận Batch A do lỗi request.
  2. Batch B được gửi và ghi thành công.
  3. Producer retry Batch A.
  4. Broker ghi Batch A sau Batch B.

Thứ tự trong log có thể trở thành:
  PaymentRequested
  OrderCreated
```

Tình huống này có thể xảy ra khi cho phép nhiều request in-flight và retry nhưng không bật idempotence. Nếu không thể dùng idempotence, một cách giữ thứ tự là đặt `max.in.flight.requests.per.connection=1`, khiến producer chỉ có một request chưa hoàn tất trên mỗi connection. Đổi lại, throughput có thể giảm do mất khả năng pipeline request.

Với producer hiện đại, lựa chọn thường phù hợp là bật idempotence và giữ `max.in.flight.requests.per.connection` trong giới hạn hỗ trợ, thay vì hạ xuống 1 mà không có lý do đo lường.

## 7. Gửi bất đồng bộ và theo dõi kết quả

`KafkaTemplate.send()` trả về future. Ứng dụng có thể đăng ký callback để xử lý kết quả mà không chặn thread gửi:

```java
import org.springframework.kafka.support.SendResult;

import java.util.concurrent.CompletableFuture;

CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send("orders", orderId, event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error(
                "Publish failed: orderId={}",
                orderId,
                exception
        );
        return;
    }

    var metadata = result.getRecordMetadata();

    log.info(
            "Published order event: key={}, topic={}, partition={}, offset={}",
            orderId,
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
    );
});
```

Ví dụ dùng API `CompletableFuture` của Spring Kafka 3.x. Một số phiên bản Spring Kafka cũ trả về `ListenableFuture`; cần dùng kiểu API tương ứng với dependency của ứng dụng.

Kết quả gửi giúp xác nhận record đã được broker acknowledge và cung cấp topic, partition, offset. Không nên coi việc gọi `send()` là bằng chứng record đã được ghi thành công.

Callback giúp quan sát kết quả, nhưng không nên dùng callback completion để tự sắp xếp lại các record đã được gửi. Nếu cần sự kiện B chỉ được phát sau khi sự kiện A đã được xác nhận hoặc sau khi nghiệp vụ A hoàn tất, hãy mô hình hóa quan hệ phụ thuộc đó ở tầng ứng dụng.

## 8. Một producer được gọi từ nhiều thread

Kafka producer thread-safe: nhiều thread có thể gọi `send()` trên cùng một producer. Producer quản lý buffer và request nội bộ để gửi dữ liệu.

Tuy nhiên, thread-safe không đồng nghĩa với thứ tự nghiệp vụ tự động. Nếu hai thread cùng phát sự kiện cho một đơn hàng, thứ tự mà producer nhận các lời gọi có thể khác thứ tự nghiệp vụ mà hệ thống mong muốn.

Ví dụ:

```text
Thread A: gửi OrderCreated(order-101)
Thread B: gửi PaymentRequested(order-101)
Thread B có thể gọi send trước Thread A nếu lịch chạy thay đổi.
```

Cả hai record có cùng key và cùng partition vẫn có thể được append theo thứ tự lời gọi thực tế đến producer. Kafka không biết rằng `OrderCreated` phải đứng trước `PaymentRequested`.

Nếu cần giữ thứ tự theo aggregate hoặc key:

- Tuần tự hóa việc phát sự kiện cho cùng một aggregate trước khi gọi producer.
- Dùng keyed executor hoặc queue phân vùng theo key để mỗi key chỉ có một luồng phát tại một thời điểm.
- Gắn sequence number hoặc aggregate version vào event để consumer có thể phát hiện sự kiện đến sai thứ tự.
- Chỉ song song giữa các key khác nhau khi nghiệp vụ cho phép.

Ví dụ đơn giản về ý tưởng: tất cả event của `order-101` đi qua cùng một hàng đợi xử lý tuần tự; event của `order-202` có thể đi qua hàng đợi khác. Cách này vừa bảo toàn thứ tự từng đơn hàng, vừa tận dụng song song giữa các đơn hàng.

## 9. Nhiều producer cùng gửi một key

Giả sử hai instance của cùng service đều gửi record key `order-101` đến topic `orders`. Partitioner có thể đưa cả hai record vào cùng partition, nhưng mỗi instance là một producer độc lập với Producer ID và sequence riêng.

Kafka sẽ ghi record theo thứ tự broker xử lý request. Nó không biết event nào có thứ tự nghiệp vụ trước. Idempotence của từng producer không phối hợp sequence giữa hai producer.

Các giải pháp thường dùng:

- Chỉ định một publisher sở hữu key hoặc shard tại một thời điểm.
- Đưa lệnh phát event qua một queue/actor tuần tự theo aggregate ID.
- Dùng transactional outbox và một cơ chế relay có partitioning ổn định, bảo đảm thứ tự lấy event theo aggregate.
- Đưa aggregate version hoặc sequence number vào payload để consumer kiểm tra, từ chối hoặc chờ sự kiện bị thiếu.
- Dùng optimistic locking hoặc fencing token để ngăn publisher cũ tiếp tục phát khi quyền sở hữu đã chuyển.

Không nên giả định rằng cùng key là đủ để phối hợp nhiều producer. Key giúp chọn partition; nó không phải khóa phân tán và không khóa các instance của ứng dụng.

## 10. Thay đổi số partition có thể ảnh hưởng ordering theo key

Với partitioner hash mặc định, partition được chọn dựa trên hash của key và số partition hiện tại. Khi tăng số partition, cùng key có thể được ánh xạ sang partition khác.

Ví dụ trước khi tăng partition:

```text
order-101 -> orders-1
```

Sau khi topic tăng partition:

```text
order-101 -> orders-4
```

Record cũ của `order-101` vẫn nằm ở `orders-1`, còn record mới có thể nằm ở `orders-4`. Hai partition có thứ tự riêng nên consumer không thể suy ra thứ tự liên tục chỉ bằng offset.

Nếu ordering theo key là yêu cầu quan trọng, cần lập kế hoạch tăng partition. Có thể dùng số partition cố định theo chiến lược dài hạn, hoặc dùng partitioning strategy ổn định có quản lý version và quy trình chuyển đổi. Một lựa chọn khác là mang sequence number theo aggregate để consumer kiểm tra thứ tự nghiệp vụ độc lập với partition offset.

## 11. Ordering và consumer xử lý song song

Producer có thể ghi đúng thứ tự trong partition nhưng consumer vẫn tạo ra side effect sai thứ tự nếu ứng dụng chuyển record sang thread pool hoặc xử lý bất đồng bộ không kiểm soát.

Ví dụ consumer đọc:

```text
offset 10 -> OrderCreated
offset 11 -> PaymentRequested
offset 12 -> OrderConfirmed
```

Nếu listener đẩy ba record vào ba task chạy song song, task của offset 12 có thể hoàn tất trước task offset 10. Kafka vẫn giữ thứ tự log, nhưng trạng thái database có thể được cập nhật sai trình tự.

Khi cần ordering end-to-end:

- Để các record của cùng partition được xử lý tuần tự.
- Nếu cần song song, chia công việc theo key nhưng bảo đảm cùng key luôn vào cùng worker/queue.
- Chỉ commit offset sau khi các record trước đó đã được xử lý thành công theo semantics đã chọn.
- Dùng aggregate version hoặc sequence number để phát hiện record đến sai thứ tự.
- Thiết kế consumer idempotent để chịu được việc giao lại sau lỗi hoặc rebalance.

Ordering trong producer chỉ là một phần của ordering end-to-end. Cần kiểm tra cả partition assignment, consumer concurrency, asynchronous dispatch và thứ tự cập nhật dữ liệu đích.

## 12. Transaction có thay thế idempotence không?

Kafka transaction cho phép producer ghi nhiều record vào nhiều partition một cách nguyên tử: consumer dùng `read_committed` chỉ nhìn thấy các transaction đã commit. Transaction hữu ích khi cần ghi nhiều output topic cùng nhau hoặc kết hợp xử lý consume-transform-produce theo cấu hình transaction.

Transaction không tạo một thứ tự tổng thể giữa các partition. Mỗi partition vẫn có thứ tự riêng. Transactional producer cũng dùng cơ chế idempotence, nhưng mục tiêu transaction là atomicity và fencing producer theo `transactional.id`, còn idempotence xử lý retry của producer.

Không nên xem transaction là cách thay thế cho key hoặc chiến lược tuần tự hóa event theo aggregate. Nếu hai producer độc lập cùng phát event cho một aggregate, transaction của từng producer không tự xác định event nào phải đứng trước.

## 13. Cách kiểm chứng ordering trong thực tế

Có thể tạo một event chứa aggregate ID và sequence number:

```java
public record OrderEvent(
        String orderId,
        long sequence,
        String eventType
) {
}
```

Producer gửi theo thứ tự:

```java
kafkaTemplate.send(
        "orders",
        orderId,
        new OrderEvent(orderId, 1, "OrderCreated")
);

kafkaTemplate.send(
        "orders",
        orderId,
        new OrderEvent(orderId, 2, "PaymentRequested")
);

kafkaTemplate.send(
        "orders",
        orderId,
        new OrderEvent(orderId, 3, "OrderConfirmed")
);
```

Consumer ghi log sequence cùng vị trí Kafka:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;

@KafkaListener(topics = "orders", groupId = "orders-audit")
public void audit(ConsumerRecord<String, OrderEvent> record) {
    OrderEvent event = record.value();

    log.info(
            "orderId={}, sequence={}, partition={}, offset={}, type={}",
            event.orderId(),
            event.sequence(),
            record.partition(),
            record.offset(),
            event.eventType()
    );
}
```

Khi kiểm thử, xác nhận các event của cùng key vào cùng partition và offset tăng theo sequence. Nên kiểm tra cả trường hợp producer retry và trường hợp nhiều thread gửi cùng key. Nếu chạy nhiều producer instance, hãy kiểm thử kịch bản cạnh tranh để xác minh cơ chế ownership hoặc sequence validation.

Sequence number trong event là thông tin nghiệp vụ do ứng dụng quản lý. Offset Kafka là vị trí lưu trữ do broker cấp. Hai giá trị phục vụ hai mục đích khác nhau và không nên thay thế cho nhau.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Event cùng key nhưng vào partition khác | Partition count thay đổi, partitioner khác hoặc key không giống nhau sau serialize | Kiểm tra key, partitioner và lịch sử thay đổi partition |
| Record bị đảo thứ tự khi retry | Idempotence tắt và có nhiều request in-flight | Bật idempotence, giữ `max.in.flight` không quá 5 |
| Event cùng key bị xử lý sai thứ tự | Nhiều thread hoặc consumer worker xử lý song song | Tuần tự hóa xử lý theo key hoặc dùng sequence validation |
| Hai producer cùng key tạo thứ tự không mong đợi | Idempotence chỉ có phạm vi từng producer | Dùng single-owner/shard, outbox ordering hoặc aggregate version |
| Future hoàn tất theo thứ tự khác kỳ vọng | Gửi đến nhiều partition hoặc ứng dụng dựa vào callback để điều phối | Dùng metadata partition/offset và quản lý dependency ở tầng nghiệp vụ |
| Retry thủ công tạo record trùng | Ứng dụng gọi `send()` lại như một lần gửi mới | Dùng event ID/idempotency key và xử lý duplicate ở consumer |
| Tăng partition làm mất thứ tự liên tục theo key | Key có thể được ánh xạ sang partition mới | Lập kế hoạch migration và dùng sequence number |
| Log cho thấy offset không liên tục | Compaction, transaction abort hoặc record bị ẩn bởi isolation level | Không giả định offset liền kề; kiểm tra record và isolation level |

## 15. Checklist bảo đảm ordering trong một producer

1. Chọn key ổn định theo thực thể cần giữ thứ tự.
2. Bảo đảm các event của cùng thực thể dùng cùng topic và partitioning strategy.
3. Bật `enable.idempotence=true` để giữ thứ tự khi producer retry.
4. Dùng `acks=all`, retries lớn hơn 0 và `max.in.flight.requests.per.connection` không lớn hơn 5 khi bật idempotence.
5. Không coi callback completion là cơ chế sắp xếp thứ tự nghiệp vụ.
6. Tuần tự hóa các lời gọi gửi cùng key nếu nhiều thread có thể phát event đồng thời.
7. Không giả định nhiều producer độc lập có thứ tự chung chỉ vì dùng cùng key.
8. Lập kế hoạch khi tăng partition vì key có thể chuyển partition.
9. Kiểm tra consumer có xử lý tuần tự theo partition/key hay không.
10. Dùng event ID và sequence number khi cần phát hiện duplicate hoặc sai thứ tự ở cấp nghiệp vụ.

Kafka bảo đảm thứ tự của log trong từng partition. Một producer được cấu hình idempotence có thể giữ thứ tự các record của chính nó khi retry đến cùng partition. Để bảo toàn trình tự nghiệp vụ, ứng dụng còn phải kiểm soát thứ tự gọi send, key/partition mapping, nhiều producer cạnh tranh và cách consumer thực thi side effect.
