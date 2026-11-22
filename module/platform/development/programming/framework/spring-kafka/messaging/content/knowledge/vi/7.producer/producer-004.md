# Chọn partition bằng key

Khi gửi một bản ghi đến Kafka topic có nhiều partition, producer cần xác định bản ghi sẽ được ghi vào partition nào. Cách chọn partition ảnh hưởng trực tiếp đến khả năng xử lý song song, phân bố tải và thứ tự sự kiện. Với Spring Kafka, ứng dụng thường truyền một **key** khi gọi `KafkaTemplate.send(...)`; Kafka producer sử dụng key đó để định tuyến bản ghi theo partitioner.

Key nên đại diện cho thực thể nghiệp vụ mà hệ thống cần giữ thứ tự, chẳng hạn `orderId`, `accountId` hoặc `customerId`. Khi các sự kiện của cùng một thực thể dùng cùng key và cùng quy tắc partitioning, chúng thường được ghi vào cùng partition. Kafka bảo đảm thứ tự bản ghi trong từng partition, vì vậy consumer có thể xử lý chuỗi sự kiện của thực thể đó theo thứ tự log.

## 1. Topic có nhiều partition và bài toán định tuyến

Một topic được chia thành nhiều partition để Kafka phân tán dữ liệu và cho phép consumer xử lý song song. Ví dụ topic `orders.events` có ba partition:

```text
orders.events
  ├── Partition 0: offset 0, 1, 2, ...
  ├── Partition 1: offset 0, 1, 2, ...
  └── Partition 2: offset 0, 1, 2, ...
```

Producer phải quyết định mỗi record đi vào partition nào. Có thể chỉ định partition trực tiếp, hoặc để partitioner tự chọn dựa trên key và metadata của topic.

Kafka chỉ bảo đảm thứ tự trong phạm vi một partition. Không có một thứ tự tổng thể giữa Partition 0, Partition 1 và Partition 2. Nếu các sự kiện `OrderCreated`, `OrderPaid`, `OrderShipped` của cùng đơn hàng bị ghi vào những partition khác nhau, một consumer có thể nhận chúng theo thứ tự không mong muốn.

Do đó, thiết kế key là quyết định về ranh giới thứ tự. Key xác định nhóm bản ghi cần được định tuyến cùng nhau; partition là đơn vị lưu trữ và xử lý có thứ tự.

## 2. Kafka chọn partition từ key như thế nào?

Khi không chỉ định partition cụ thể, default partitioner của Kafka hoạt động theo nguyên tắc:

1. Producer serialize key và value thành byte array.
2. Nếu key có giá trị, partitioner tính hash từ byte của key.
3. Hash được chuyển thành giá trị không âm và dùng để chọn một partition trong số partition hiện có.
4. Nếu key là `null`, default partitioner sử dụng cơ chế sticky partitioning để gom các record không có key vào một partition trong một khoảng/batch, sau đó có thể chuyển sang partition khác nhằm cải thiện batching và phân bố tải.

Với default partitioner truyền thống, cách tính cho key có thể biểu diễn khái quát như sau:

```text
partition = positive(hash(serializedKey)) % partitionCount
```

Kafka client mặc định sử dụng thuật toán hash trên byte đã serialize của key (Murmur2 trong default partitioner). Ứng dụng thường không cần tự tính partition; chỉ cần chọn key ổn định và để producer thực hiện định tuyến. Nếu cấu hình custom partitioner hoặc chỉ định partition tường minh, quy tắc có thể khác.

Ví dụ với topic có ba partition:

| Key | Kết quả định tuyến minh họa |
| --- | --- |
| `order-1001` | Partition 2 |
| `order-1002` | Partition 0 |
| `order-1003` | Partition 1 |
| `order-1001` (lần gửi tiếp theo) | Partition 2 |

Các số partition trong bảng chỉ minh họa. Không thể suy ra một key cụ thể luôn thuộc partition nào nếu không biết partition count, serializer và partitioner đang dùng. Nhiều key khác nhau cũng có thể hash về cùng một partition; Kafka không tạo một partition riêng cho từng key.

## 3. Chọn key theo thực thể nghiệp vụ

Hãy chọn key theo câu hỏi: **Những bản ghi nào cần được Kafka giữ thứ tự tương đối với nhau?**

| Nghiệp vụ | Key thường phù hợp | Lý do |
| --- | --- | --- |
| Vòng đời đơn hàng | `orderId` | Các thay đổi của cùng đơn hàng được đưa về cùng partition |
| Giao dịch tài khoản | `accountId` | Các thay đổi số dư của một tài khoản có cùng luồng thứ tự |
| Hồ sơ khách hàng | `customerId` | Các cập nhật của cùng khách hàng có cùng partition |
| Trạng thái thiết bị IoT | `deviceId` | Sự kiện của cùng thiết bị được gom theo key |
| Sự kiện kiểm kê sản phẩm | `productId` | Các cập nhật của cùng sản phẩm có thể được xử lý theo thứ tự |

Ví dụ, một đơn hàng có các sự kiện:

```text
OrderCreated(orderId=ORD-42)
OrderPaid(orderId=ORD-42)
OrderPacked(orderId=ORD-42)
OrderShipped(orderId=ORD-42)
```

Nếu cả bốn record được gửi đến cùng topic với key `ORD-42`, default partitioner sẽ chọn cùng partition (với cùng partition count và cùng cách serialize key). Consumer đọc partition đó sẽ thấy các record theo thứ tự offset.

Không nên dùng một UUID mới cho từng event làm key nếu mục tiêu là gom các event theo đơn hàng. Mỗi UUID khác nhau sẽ phân tán event và làm mất tính affinity theo `orderId`. UUID của event vẫn hữu ích, nhưng nên nằm trong payload hoặc header để nhận diện duy nhất từng event; key tiếp tục là `orderId`.

## 4. Gửi record có key bằng `KafkaTemplate`

Spring Kafka cung cấp overload `send(topic, key, data)` để truyền key trực tiếp. Ví dụ dưới đây dùng `orderId` làm key và JSON event làm value.

```java
import java.time.Instant;
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

record OrderEvent(
        String eventId,
        String orderId,
        String eventType,
        Instant occurredAt) {
}

@Service
public class OrderEventPublisher {

    private static final String TOPIC = "orders.events";

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {
        return kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
}
```

`KafkaTemplate<String, OrderEvent>` thể hiện kiểu key và value của producer. Lệnh `send` truyền `event.orderId()` làm key, còn toàn bộ event là value. `StringSerializer` sẽ serialize key thành byte; serializer value (ví dụ `JsonSerializer`) chịu trách nhiệm chuyển event thành byte.

Cấu hình producer tối thiểu có thể như sau:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

Sau khi gửi, có thể xem partition mà broker xác nhận trong metadata:

```java
publisher.publish(event)
        .thenAccept(result -> {
            int partition = result.getRecordMetadata().partition();
            long offset = result.getRecordMetadata().offset();
            log.info("Order event sent to partition={}, offset={}",
                    partition, offset);
        })
        .exceptionally(exception -> {
            log.error("Cannot publish order event", exception);
            return null;
        });
```

Đoạn callback giả định lớp có logger `log`. Việc gọi `send` là bất đồng bộ; chỉ khi future hoàn tất thành công mới có metadata xác nhận broker đã nhận record. Không nên ghi log thành công ngay sau dòng gọi `send`.

## 5. Key phải được serialize ổn định

Partitioner dựa trên byte đã serialize của key. Vì vậy, cùng một giá trị logic nhưng serialize thành byte khác nhau có thể được đưa đến partition khác nhau.

Ví dụ, nếu producer A serialize ID số `42` thành chuỗi UTF-8 `"42"`, còn producer B serialize cùng ID thành một biểu diễn nhị phân khác, hai producer có thể tính hash khác nhau. Để giữ partition affinity giữa nhiều producer, cần thống nhất:

- Kiểu dữ liệu của key.
- Key serializer.
- Quy tắc chuẩn hóa giá trị trước khi serialize, ví dụ chữ hoa/chữ thường hoặc khoảng trắng.
- Cách biểu diễn ID có tính tương thích qua các phiên bản ứng dụng.

Với ID nghiệp vụ dạng chuỗi, `StringSerializer` thường là lựa chọn đơn giản. Không nên thay serializer hoặc format key tùy tiện trong khi topic vẫn đang được nhiều producer/consumer sử dụng.

## 6. Key, partition tường minh và custom partitioner

Thông thường, hãy để Kafka chọn partition từ key. Tuy nhiên, `KafkaTemplate` cũng có overload cho phép chỉ định partition:

```java
kafkaTemplate.send("orders.events", 1, orderId, event);
```

Lệnh này gửi record vào partition `1`, bất kể default partitioner sẽ chọn partition nào từ key. Chỉ số partition phải tồn tại trong topic. Khi chỉ định partition thủ công, ứng dụng chịu trách nhiệm phân phối tải và bảo đảm mọi event cần cùng thứ tự được gửi vào cùng partition.

Trong một số hệ thống, quy tắc định tuyến phức tạp hơn hash mặc định. Kafka producer cho phép cài custom partitioner để ánh xạ key sang partition theo thuật toán riêng. Cần cân nhắc kỹ trước khi sử dụng vì custom partitioner làm tăng trách nhiệm đồng bộ logic giữa producer và các phiên bản ứng dụng. Mọi producer ghi vào cùng topic cần áp dụng quy tắc tương thích.

Không nên vừa chỉ định partition tường minh, vừa kỳ vọng key tự bảo đảm affinity. Khi partition được cung cấp, partition đó là lựa chọn định tuyến.

## 7. Key và thứ tự xử lý

Key không tự tạo ra thứ tự toàn topic. Nó chỉ giúp những record có cùng key được đưa về cùng partition theo quy tắc partitioning.

Ví dụ:

```text
Producer
  OrderCreated(ORD-42) ─┐
  OrderPaid(ORD-42) ────┼── key=ORD-42 ──> Partition 1
  OrderShipped(ORD-42) ─┘

  OrderCreated(ORD-99) ───── key=ORD-99 ──> Partition 0
```

Trong một consumer group, mỗi partition tại một thời điểm được gán cho tối đa một consumer. Vì thế, consumer group có thể xử lý nhiều partition song song trong khi thứ tự trong từng partition được giữ. Nếu cần xử lý theo `orderId`, hãy đảm bảo listener không chuyển các record cùng partition sang các luồng xử lý bất đồng bộ thiếu kiểm soát khiến nghiệp vụ hoàn tất sai thứ tự.

Producer cũng cần được cấu hình phù hợp khi retry. Với producer idempotent được bật, Kafka bảo đảm thứ tự của các batch được gửi từ producer trong các tình huống retry mà cấu hình hỗ trợ. Nếu tắt idempotence và cho phép nhiều request in-flight, retry có thể làm thay đổi thứ tự append của batch. Khi thứ tự nghiệp vụ quan trọng, nên giữ idempotence theo mặc định phù hợp của Kafka client và không vô hiệu hóa tùy tiện.

Nếu nhiều instance hoặc nhiều producer đồng thời phát event cho cùng một key, Kafka vẫn ghi chúng vào cùng partition và tạo một thứ tự offset duy nhất theo thứ tự broker append. Tuy nhiên, thứ tự đó không nhất thiết là thứ tự nghiệp vụ mà các producer mong muốn nếu không có cơ chế điều phối nguồn phát.

## 8. Điều gì xảy ra khi tăng số partition?

Với default partitioner, partition thường được tính bằng hash của key modulo số partition. Vì mẫu số thay đổi khi tăng partition count, một key có thể được ánh xạ sang partition mới sau khi topic được mở rộng.

Ví dụ:

```text
Trước: hash(key) % 3 = 1  -> Partition 1
Sau:   hash(key) % 4 = 3  -> Partition 3
```

Đây chỉ là ví dụ số học. Hệ quả thực tế là các event cũ của `ORD-42` có thể nằm ở partition 1, còn event mới sau khi mở rộng topic lại nằm ở partition 3. Hai partition được consumer xử lý độc lập, nên không còn một thứ tự duy nhất cho toàn bộ lịch sử key đó.

Nếu nghiệp vụ phụ thuộc chặt vào thứ tự theo key, hãy xem số partition là một quyết định kiến trúc cần lập kế hoạch từ đầu. Trước khi tăng partition, đánh giá ảnh hưởng đến ordering, consumer concurrency, phân bố dữ liệu và cách dựng lại trạng thái. Có thể cân nhắc tạo topic phiên bản mới và chuyển đổi có kiểm soát nếu cần bảo toàn thứ tự lịch sử.

## 9. Tránh hot partition và lệch tải

Chọn key giúp giữ thứ tự nhưng cũng quyết định cách phân phối tải. Nếu một key chiếm phần lớn traffic, tất cả record của key đó đi về cùng partition và partition trở thành **hot partition**. Thêm partition không chia nhỏ được một key duy nhất khi vẫn dùng cùng quy tắc hash.

Các nguyên nhân thường gặp:

- Dùng một giá trị cố định như `"ORDER"` cho mọi record.
- Dùng `tenantId` khi một tenant tạo phần lớn traffic.
- Dùng key có độ phân bố lệch, ví dụ một số thiết bị gửi dữ liệu nhiều hơn hẳn thiết bị khác.
- Dùng `null` key cho mọi record rồi kỳ vọng thứ tự theo thực thể, trong khi null key không biểu diễn được thực thể cần gom nhóm.

Một số hướng xử lý:

1. Chọn key có độ phân bố tốt nhưng vẫn giữ đúng ranh giới thứ tự nghiệp vụ.
2. Nếu nghiệp vụ cho phép chia nhỏ một thực thể, dùng composite key như `accountId:shardId`; chỉ làm vậy khi chấp nhận rằng thứ tự toàn account không còn được bảo đảm giữa các shard.
3. Theo dõi record rate, bytes in/out và consumer lag theo partition để phát hiện lệch tải.
4. Tránh một key cố định hoặc một key quá rộng chỉ vì tiện triển khai.

Không thể vừa phân tán một luồng của cùng thực thể sang nhiều partition, vừa dựa vào Kafka để giữ một thứ tự tổng thể tự nhiên cho luồng đó. Đây là đánh đổi giữa ordering và parallelism cần được quyết định theo nghiệp vụ.

## 10. Key trong topic compact và trong consumer

Key còn có vai trò đặc biệt với topic dùng `cleanup.policy=compact`. Kafka compaction giữ lại trạng thái mới nhất theo key trong từng partition. Nếu producer dùng `customerId` làm key, topic có thể biểu diễn trạng thái gần nhất của từng khách hàng.

Với topic compact, key phải ổn định và không null nếu muốn compaction nhóm các phiên bản của cùng thực thể. Gửi tombstone (key có value `null`) là cách biểu diễn việc xóa key khỏi trạng thái compact; tombstone cần được hiểu theo quy tắc retention riêng của compaction.

Ở phía consumer, key có thể được đọc từ `ConsumerRecord.key()`:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(topics = "orders.events", groupId = "order-projection")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    String orderId = record.key();
    OrderEvent event = record.value();

    // Xử lý thay đổi của đúng đơn hàng.
}
```

Consumer có thể dùng key để cập nhật read model, kiểm tra thứ tự nghiệp vụ hoặc chọn bản ghi cần chống xử lý trùng. Key không thay thế event ID: event ID dùng nhận diện duy nhất một lần phát sự kiện, còn key xác định nhóm dữ liệu có quan hệ về partitioning.

## 11. Kiểm thử partition affinity

Một kiểm thử tích hợp đơn giản có thể gửi hai record cùng key và xác nhận metadata trả về cùng partition. Không nên hard-code partition index cụ thể vì kết quả phụ thuộc partition count và partitioner.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
        partitions = 3,
        topics = "orders.partition-test",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderPartitioningTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Test
    void recordsWithSameKeyUseSamePartition() throws Exception {
        SendResult<String, String> first = kafkaTemplate
                .send("orders.partition-test", "ORD-42", "OrderCreated")
                .get(10, TimeUnit.SECONDS);

        SendResult<String, String> second = kafkaTemplate
                .send("orders.partition-test", "ORD-42", "OrderPaid")
                .get(10, TimeUnit.SECONDS);

        assertThat(second.getRecordMetadata().partition())
                .isEqualTo(first.getRecordMetadata().partition());
    }
}
```

Kiểm thử này chứng minh partition affinity với cùng key trong cùng topic và cùng cấu hình test. Có thể bổ sung assertion về offset để xác minh record thứ hai được append sau record thứ nhất trong partition. Nó không kiểm tra phân bố tải trên nhiều key, thứ tự giữa nhiều producer đồng thời hoặc hành vi sau khi thay đổi partition count.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Mỗi key có một partition riêng | Nhiều key có thể cùng hash về một partition |
| Cùng key luôn ở cùng partition dù topic thay đổi | Điều này đúng khi partition count, serializer và partitioner giữ nguyên |
| Kafka bảo đảm thứ tự toàn topic | Kafka chỉ bảo đảm thứ tự trong từng partition |
| Không truyền key vẫn có thứ tự theo entity | Null key không xác định entity; default partitioner dùng sticky partitioning |
| Tăng partition luôn an toàn với ordering | Một key có thể được ánh xạ sang partition khác sau khi tăng số partition |
| Event ID nên luôn là key | Chọn key theo thực thể cần giữ thứ tự; event ID có thể nằm trong payload/header |
| Chỉ cần cùng key là mọi producer sẽ có thứ tự nghiệp vụ chính xác | Broker tạo thứ tự append; hệ thống phát sự kiện vẫn phải điều phối thứ tự nghiệp vụ nếu nhiều producer đồng thời |

## 13. Kết luận

Key là cơ chế quan trọng để định tuyến record đến partition. Với default partitioner, Kafka sử dụng byte đã serialize của key để chọn partition; các record cùng key thường đi cùng partition khi topic giữ nguyên số partition và quy tắc serialize/partitioning. Nhờ thứ tự offset trong partition, ứng dụng có thể giữ thứ tự xử lý cho một thực thể nghiệp vụ như đơn hàng hoặc tài khoản.

Trong Spring Kafka, hãy truyền key rõ ràng qua `KafkaTemplate.send(topic, key, value)`, chọn serializer ổn định và quan sát partition từ metadata khi kiểm thử. Thiết kế key cần cân bằng thứ tự với phân bố tải; đồng thời phải đánh giá tác động của hot partition và việc tăng partition count trước khi thay đổi topic đang chạy.
