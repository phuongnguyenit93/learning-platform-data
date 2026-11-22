# Gửi theo partition chỉ định

Kafka producer thường để partitioner tự chọn partition dựa trên key hoặc chính sách phân phối mặc định. Trong một số tình huống, ứng dụng cần gửi record vào **một partition cụ thể** để tuân theo quy tắc định tuyến đã xác định, cô lập một luồng dữ liệu hoặc tương thích với cách phân vùng của hệ thống hiện có. Spring Kafka hỗ trợ việc này qua các overload của `KafkaTemplate.send(...)` và đối tượng `ProducerRecord`.

Trong module `SPRING_KAFKA_MESSAGING`, producer gửi event bằng `KafkaTemplate`, còn consumer đọc event bằng `@KafkaListener`. Chỉ định partition là quyết định ở phía producer; record sau khi được ghi vẫn tuân theo các quy tắc lưu trữ, offset và consumer group của Kafka.

## 1. Partition là gì và chỉ định partition có nghĩa gì?

Một topic được chia thành nhiều partition. Mỗi partition là một log có thứ tự riêng và có dãy offset riêng. Khi producer gửi record, Kafka cần xác định record sẽ được ghi vào partition nào.

Ví dụ topic `orders` có bốn partition:

```text
orders
├── partition 0: offset 0, 1, 2, ...
├── partition 1: offset 0, 1, 2, ...
├── partition 2: offset 0, 1, 2, ...
└── partition 3: offset 0, 1, 2, ...
```

Nếu ứng dụng chỉ định partition `2`, record sẽ được gửi tới `orders-2`. Chỉ số partition bắt đầu từ `0`, do đó topic có bốn partition thì các chỉ số hợp lệ là `0`, `1`, `2` và `3`.

Khi không chỉ định partition, producer có thể dùng key và partitioner để lựa chọn. Khi chỉ định partition tường minh, partition đó được ưu tiên và producer không dùng key để chọn partition nữa. Key vẫn được lưu trong record, phục vụ consumer và log compaction, nhưng không còn quyết định vị trí ghi của record đó.

| Cách gửi | Ai chọn partition? | Vai trò của key |
|---|---|---|
| Có key, không chỉ định partition | Partitioner của producer | Thường được dùng để định tuyến ổn định theo key |
| Không có key và không chỉ định partition | Partitioner mặc định, có thể dùng sticky partitioning | Không có key để định tuyến theo thực thể |
| Chỉ định partition tường minh | Ứng dụng chọn partition | Vẫn được lưu trong record nhưng không dùng để chọn partition |

Chỉ định partition không tạo thêm partition và cũng không thay đổi cấu hình topic. Topic phải có partition đó trước khi producer gửi record.

## 2. Gửi đến partition bằng `KafkaTemplate`

Spring Kafka cung cấp overload nhận topic, partition, key và value:

```java
kafkaTemplate.send(topic, partition, key, value);
```

Ví dụ producer gửi event đơn hàng vào partition được truyền vào:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            int partition,
            OrderCreatedEvent event) {

        if (partition < 0) {
            throw new IllegalArgumentException(
                    "Partition must be zero or greater"
            );
        }

        return kafkaTemplate.send(
                "orders",
                partition,
                event.orderId(),
                event
        );
    }
}
```

Trong ví dụ:

- `"orders"` là tên topic.
- `partition` là chỉ số partition đã chọn, bắt đầu từ `0`.
- `event.orderId()` vẫn được lưu làm key của record.
- `event` là payload được serializer chuyển thành byte.

Kiểm tra `partition >= 0` chỉ loại bỏ chỉ số âm. Để chắc chắn partition tồn tại, ứng dụng cần đối chiếu metadata của topic hoặc dựa vào cấu hình provisioning đã được kiểm soát. Nếu gửi đến partition không tồn tại, broker có thể trả lỗi như `UNKNOWN_TOPIC_OR_PARTITION`; producer không tự tạo partition mới.

Trong các phiên bản Spring Kafka hiện đại (3.x), `KafkaTemplate.send(...)` trả về `CompletableFuture<SendResult<K, V>>`. Các phiên bản cũ hơn có thể dùng `ListenableFuture`; hãy đối chiếu API của phiên bản dependency trong dự án.

## 3. Tạo `ProducerRecord` để kiểm soát đầy đủ metadata

Khi cần chỉ định thêm timestamp hoặc headers, tạo `ProducerRecord` tường minh rồi gửi bằng `KafkaTemplate`:

```java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderRecordPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderRecordPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(int partition, OrderCreatedEvent event) {
        List<Header> headers = List.of(
                new RecordHeader(
                        "event-type",
                        "OrderCreated".getBytes(StandardCharsets.UTF_8)
                )
        );

        ProducerRecord<String, OrderCreatedEvent> record =
                new ProducerRecord<>(
                        "orders",
                        partition,
                        event.occurredAt().toEpochMilli(),
                        event.orderId(),
                        event,
                        headers
                );

        kafkaTemplate.send(record);
    }
}
```

Constructor đầy đủ ở đây nhận topic, partition, timestamp, key, value và headers. Timestamp được truyền theo mili giây từ Unix epoch. Nếu không cần timestamp hoặc headers tùy chỉnh, overload của `KafkaTemplate.send(...)` ngắn gọn hơn.

`ProducerRecord` chỉ mô tả record cần gửi. Kết quả gửi vẫn bất đồng bộ và có thể thất bại do lỗi mạng, broker, quyền truy cập, metadata hoặc serialization. Trong ứng dụng thật, nên trả future về caller hoặc đăng ký callback để quan sát kết quả thay vì bỏ qua lỗi.

## 4. Xác minh partition trước khi gửi

Ứng dụng cần biết partition được chỉ định có tồn tại trong topic hay không. Có thể đọc metadata bằng `KafkaTemplate.partitionsFor(topic)`:

```java
import java.util.List;

import org.apache.kafka.common.PartitionInfo;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class TopicPartitionValidator {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public TopicPartitionValidator(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void validate(String topic, int requestedPartition) {
        if (requestedPartition < 0) {
            throw new IllegalArgumentException("Negative partition index");
        }

        List<PartitionInfo> partitions = kafkaTemplate.partitionsFor(topic);
        boolean exists = partitions.stream()
                .anyMatch(info -> info.partition() == requestedPartition);

        if (!exists) {
            throw new IllegalArgumentException(
                    "Partition " + requestedPartition
                            + " does not exist in topic " + topic
            );
        }
    }
}
```

`partitionsFor(...)` cần lấy metadata từ Kafka và có thể phát sinh độ trễ hoặc lỗi kết nối. Không nên gọi phương thức này cho từng record trong luồng throughput cao. Thường nên xác minh topic/partition khi ứng dụng khởi động, khi nạp routing configuration hoặc theo chu kỳ quản trị; sau đó sử dụng cấu hình đã được kiểm tra.

Việc xác minh trước cũng không loại bỏ hoàn toàn lỗi lúc gửi: topic có thể thay đổi hoặc broker có thể gặp sự cố sau thời điểm kiểm tra. Producer vẫn cần xử lý send failure.

## 5. Chọn partition theo quy tắc nghiệp vụ

Có ba cách phổ biến để quyết định partition:

1. **Cấu hình cố định:** ứng dụng gửi một loại record vào partition đã được cấu hình, chẳng hạn luồng tích hợp cũ yêu cầu partition `0`.
2. **Bảng định tuyến:** ứng dụng tra cứu mapping như `region -> partition` hoặc `tenant -> partition` được quản lý tập trung.
3. **Tính toán từ routing key:** ứng dụng áp dụng một thuật toán xác định để cùng một thực thể luôn ra cùng partition.

Ví dụ tính partition theo `accountId` với số partition đã biết:

```java
public final class AccountPartitionRouter {

    private final int partitionCount;

    public AccountPartitionRouter(int partitionCount) {
        if (partitionCount <= 0) {
            throw new IllegalArgumentException(
                    "Partition count must be positive"
            );
        }
        this.partitionCount = partitionCount;
    }

    public int partitionFor(String accountId) {
        return Math.floorMod(accountId.hashCode(), partitionCount);
    }
}
```

`Math.floorMod(...)` bảo đảm kết quả không âm, kể cả khi `hashCode()` trả về số âm. Với cùng `accountId` và cùng `partitionCount`, thuật toán trên cho ra cùng partition trong ứng dụng Java.

Đây chỉ là ví dụ về routing tự quản lý. Nó không giống thuật toán hash của Kafka partitioner mặc định. Nếu producer có thể để Kafka chọn partition từ key, hãy ưu tiên cơ chế mặc định để tránh tự duy trì thuật toán định tuyến. Chỉ tính partition thủ công khi có yêu cầu nghiệp vụ rõ ràng hoặc cần tương thích với mapping có sẵn.

Nếu nhiều ngôn ngữ hoặc nhiều service cùng tính partition, phải công bố chính xác thuật toán hash, cách chuẩn hóa key và cách xử lý số âm. Không để mỗi service tự triển khai một thuật toán khác nhau.

## 6. Ảnh hưởng đến key, thứ tự và consumer group

### 6.1. Key vẫn tồn tại nhưng không quyết định partition

Giả sử record có key `order-1001` nhưng producer chỉ định partition `3`. Kafka lưu record với key đó tại partition `3`, kể cả khi partitioner mặc định có thể chọn partition khác cho cùng key.

Điều này cho phép ứng dụng kiểm soát vị trí ghi, nhưng cũng có nghĩa producer phải tự bảo đảm các event cần đi cùng nhau được định tuyến nhất quán. Nếu một event của `order-1001` được gửi vào partition `1` và event kế tiếp vào partition `3`, Kafka không thể bảo đảm thứ tự giữa hai partition.

### 6.2. Thứ tự chỉ được bảo đảm trong một partition

Kafka duy trì thứ tự record trong từng partition theo offset. Nếu mọi event của cùng một aggregate luôn được gửi vào cùng partition và producer gửi chúng theo thứ tự mong muốn, consumer có thể đọc chuỗi record theo thứ tự offset của partition đó.

Kafka không bảo đảm thứ tự toàn cục giữa các partition. Timestamp giống nhau hoặc tăng dần cũng không thay thế được thứ tự offset. Nếu nhiều producer cùng ghi vào một partition, thứ tự được xác định theo thứ tự broker append record, không nhất thiết là thứ tự thời gian nghiệp vụ mà các producer quan sát độc lập.

### 6.3. Consumer group nhận partition như thế nào?

Chỉ định partition ở producer không buộc một consumer cụ thể nhận record. Kafka consumer group vẫn dùng cơ chế assignment để phân phối partition cho các consumer member. Trong cùng một group, một partition tại một thời điểm được gán cho tối đa một member.

Ví dụ topic có bốn partition và consumer group có hai consumer:

```text
Topic orders                 Consumer group orders-service
partition 0 ────────────────> consumer A
partition 1 ────────────────> consumer A
partition 2 ────────────────> consumer B
partition 3 ────────────────> consumer B
```

Record gửi vào partition `3` sẽ được consumer đang sở hữu partition `3` trong group đọc. Nó không nhất thiết được consumer B mãi mãi; assignment có thể thay đổi khi rebalance.

Không nhầm việc producer chỉ định partition với `@TopicPartition` hoặc `TopicPartitionOffset` ở consumer. Một bên quyết định nơi ghi record; bên kia quyết định consumer subscribe hoặc assign partition nào.

## 7. Khi nào nên và không nên chỉ định partition?

| Tình huống | Khuyến nghị | Lý do |
|---|---|---|
| Cần giữ một mapping partition đã được chuẩn hóa từ hệ thống cũ | Có thể chỉ định partition | Tương thích với quy tắc định tuyến hiện hữu |
| Có quy tắc phân vùng theo tenant/region cần kiểm soát rõ | Có thể dùng routing table hoặc router | Cho phép điều phối tải theo yêu cầu nghiệp vụ |
| Chỉ cần các event cùng `orderId` đi cùng partition | Thường chỉ cần dùng `orderId` làm key | Kafka partitioner đã xử lý định tuyến theo key |
| Muốn tăng throughput bằng cách gửi tất cả record vào một partition | Không nên | Một partition trở thành nút thắt và giới hạn consumer parallelism |
| Muốn ép một consumer cụ thể xử lý record | Không dùng partition như định danh consumer | Consumer group assignment do Kafka quản lý và có thể thay đổi |
| Muốn có thứ tự toàn cục cho mọi topic | Không giải quyết được bằng chỉ định partition | Thứ tự chỉ có ý nghĩa trong từng partition của một topic |

Chỉ định partition là công cụ điều khiển định tuyến, không phải cách tăng tốc mặc định. Nếu không có yêu cầu rõ ràng, hãy để Kafka partitioner lựa chọn dựa trên key.

## 8. Xử lý kết quả gửi và lỗi partition

Gửi record là thao tác bất đồng bộ. Ứng dụng cần phân biệt lỗi trước khi gửi (ví dụ partition index âm), lỗi metadata/partition, lỗi serialization và lỗi broker trả về sau khi gửi.

Ví dụ quan sát kết quả gửi:

```java
import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class AuditedOrderPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(AuditedOrderPublisher.class);

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public AuditedOrderPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            int partition,
            OrderCreatedEvent event) {

        CompletableFuture<SendResult<String, OrderCreatedEvent>> future =
                kafkaTemplate.send("orders", partition, event.orderId(), event);

        return future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                        "Failed to publish order {} to partition {}",
                        event.orderId(),
                        partition,
                        exception
                );
                return;
            }

            var metadata = result.getRecordMetadata();
            log.info(
                    "Published order {} to topic={} partition={} offset={}",
                    event.orderId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
    }
}
```

Record metadata trả về cho biết partition và offset thực tế broker đã ghi. Đây là dữ liệu hữu ích để đối chiếu khi debug. Không chỉ log partition được yêu cầu; hãy kiểm tra partition trong `RecordMetadata` để xác nhận kết quả thực tế.

Không nên retry vô hạn cho lỗi cấu hình như partition không tồn tại hoặc topic sai tên. Với lỗi tạm thời như mất kết nối, cần áp dụng retry/backoff phù hợp với producer configuration và chính sách nghiệp vụ. Nếu send result thất bại, caller cần quyết định báo lỗi, retry hay ghi nhận trạng thái để xử lý sau.

## 9. Cấu hình và quản lý partition theo môi trường

Không nên hardcode chỉ số partition rải rác trong nhiều class. Nếu phải chỉ định partition, đưa routing rule vào cấu hình hoặc một thành phần chuyên trách:

```yaml
app:
  kafka:
    topics:
      orders: orders
    routing:
      orders:
        default-partition: 0
```

Ví dụ này chỉ phù hợp khi yêu cầu thực sự là luôn gửi vào partition `0`. Nếu topic được tạo với số partition khác nhau giữa local và production, hãy xác minh giá trị cấu hình trước khi chạy. Với routing theo key, cấu hình partition count phải đồng bộ với metadata topic và mọi producer tham gia cùng luồng.

Khi tăng số partition của topic, thuật toán `hash(key) % partitionCount` có thể ánh xạ cùng key sang partition mới. Nếu thứ tự theo thực thể là yêu cầu nghiêm ngặt, cần có kế hoạch chuyển đổi mapping, xử lý dữ liệu đang tồn tại và tránh việc cùng thực thể đồng thời được ghi vào partition cũ lẫn mới.

Với routing table, nên quản lý version của mapping và rollout đồng bộ giữa các producer. Nếu hai instance dùng hai phiên bản mapping khác nhau, event của cùng một key có thể bị gửi vào partition khác nhau trong giai đoạn triển khai.

## 10. Kiểm thử producer gửi theo partition

Kiểm thử cần xác minh record thực sự được ghi vào partition được yêu cầu, đồng thời kiểm tra key và payload.

Các mức kiểm thử phù hợp:

- **Unit test router:** kiểm tra cùng routing key cho kết quả nhất quán, partition nằm trong khoảng hợp lệ và xử lý hash âm đúng.
- **Unit test publisher:** mock `KafkaTemplate`, xác minh overload `send(topic, partition, key, value)` được gọi với đúng tham số và caller nhận được future.
- **Integration test với Embedded Kafka hoặc Testcontainers:** tạo topic có số partition đã biết, gửi record tới một partition, rồi đọc metadata hoặc consume để xác minh partition thực tế.
- **Test lỗi:** thử partition âm, partition ngoài phạm vi, topic chưa tồn tại hoặc broker không sẵn sàng; xác minh ứng dụng xử lý lỗi theo chính sách.

Ví dụ kiểm thử tích hợp nên dùng topic riêng cho test và không phụ thuộc vào partition count mặc định của broker. Khi kiểm tra kết quả, ưu tiên `RecordMetadata.partition()` từ send result hoặc `ConsumerRecord.partition()` thay vì chỉ kiểm tra payload đã được nhận.

## 11. Những lỗi thường gặp

- **Nhầm chỉ số partition bắt đầu từ 1:** Kafka đánh số từ `0`; topic có bốn partition dùng chỉ số `0` đến `3`.
- **Chỉ định partition vượt phạm vi:** producer gửi tới partition không tồn tại và nhận lỗi từ broker. Hãy xác minh metadata hoặc provisioning.
- **Nghĩ rằng key vẫn tự chọn partition khi đã truyền partition:** partition chỉ định được ưu tiên; key chỉ còn là dữ liệu của record.
- **Gửi event cùng aggregate vào các partition khác nhau:** thứ tự giữa chúng không được bảo đảm. Duy trì routing nhất quán.
- **Dồn mọi record vào partition `0`:** gây partition nóng và giới hạn khả năng tiêu thụ song song.
- **Tính partition theo số lượng partition thay đổi:** cùng key có thể bị remap khi topic tăng partition.
- **Nhầm partition producer với assignment của consumer:** producer chọn nơi ghi; Kafka consumer group quyết định consumer member nào đọc partition.
- **Bỏ qua future trả về từ `send`:** ứng dụng không phát hiện được lỗi gửi bất đồng bộ.
- **Xác minh partition cho từng record:** gọi metadata liên tục làm tăng overhead; hãy xác minh khi khởi tạo hoặc khi routing configuration thay đổi.

## 12. Checklist trước khi gửi theo partition chỉ định

- [ ] Có lý do nghiệp vụ rõ ràng để chỉ định partition thay vì dùng key-based partitioning.
- [ ] Partition index bắt đầu từ `0` và nằm trong phạm vi topic hiện tại.
- [ ] Topic đã được provisioning với partition count phù hợp.
- [ ] Routing rule ổn định giữa các producer và instance.
- [ ] Các event cần giữ thứ tự theo thực thể được gửi vào cùng partition.
- [ ] Đã đánh giá nguy cơ partition nóng và phân bố tải.
- [ ] Đã tính đến tác động khi tăng số partition hoặc thay đổi routing mapping.
- [ ] Producer quan sát send result và xử lý lỗi bất đồng bộ.
- [ ] Integration test xác minh partition thực tế qua metadata hoặc consumer record.

Khi chỉ định partition có chủ đích, producer có thể kiểm soát vị trí ghi record mà vẫn giữ key, value, timestamp và headers như bình thường. Hãy duy trì một quy tắc routing thống nhất, kiểm tra partition theo metadata topic và theo dõi kết quả gửi để bảo đảm luồng messaging giữ được thứ tự và khả năng mở rộng mong muốn.
