# Ordering giữa nhiều partition

Kafka bảo đảm thứ tự record bên trong từng partition. Khi một topic có nhiều partition, mỗi partition là một log độc lập với offset và leader riêng. Producer có thể ghi đồng thời vào nhiều partition, còn consumer group có thể đọc nhiều partition song song. Đổi lại, Kafka không cung cấp một thứ tự tổng thể giữa tất cả record của topic.

Khi thiết kế ứng dụng Spring Kafka, cần xác định chính xác nghiệp vụ cần thứ tự ở phạm vi nào: không cần thứ tự giữa các thực thể, cần thứ tự riêng cho từng key, hay cần một thứ tự toàn cục cho mọi sự kiện. Mỗi yêu cầu có cách phân vùng, gửi và tiêu thụ khác nhau. Tăng số partition có thể tăng khả năng song song, nhưng không tạo thêm một dòng thứ tự chung.

## 1. Vì sao nhiều partition không có thứ tự tổng thể?

Một topic được chia thành nhiều partition. Mỗi partition có log riêng, offset riêng và có thể có leader trên broker khác nhau.

Ví dụ topic `orders` có ba partition:

```text
orders-0:
  offset 0 -> OrderCreated(order-101)
  offset 1 -> PaymentRequested(order-101)
  offset 2 -> OrderConfirmed(order-101)

orders-1:
  offset 0 -> OrderCreated(order-202)
  offset 1 -> PaymentRequested(order-202)

orders-2:
  offset 0 -> OrderCreated(order-303)
  offset 1 -> PaymentRequested(order-303)
```

Có thể khẳng định record offset 0 của `orders-0` đứng trước record offset 1 của cùng partition. Nhưng không thể dùng offset để kết luận record ở `orders-0` offset 2 xảy ra trước hay sau record ở `orders-1` offset 1.

Mỗi partition có thứ tự cục bộ:

- `orders-0` có thứ tự theo offset của partition 0.
- `orders-1` có thứ tự theo offset của partition 1.
- `orders-2` có thứ tự theo offset của partition 2.

Không có global offset chung cho cả topic. Kafka cũng không cung cấp một đồng hồ thứ tự toàn cục cho các record trên những partition khác nhau.

## 2. Producer ghi đồng thời vào nhiều partition

Producer chọn partition cho từng record thông qua một trong các cách:

- Dựa trên key và partitioner.
- Ứng dụng chỉ định partition trong `ProducerRecord`.
- Partitioner tùy chỉnh quyết định partition.
- Với record không có key, partitioner có thể dùng chiến lược phân phối như sticky partitioning.

Một producer có thể có nhiều batch đang được gửi đến các partition khác nhau cùng lúc. Broker xử lý từng partition độc lập; thứ tự append được bảo đảm trong từng partition, không tạo quan hệ thứ tự giữa các partition.

Ví dụ:

```text
Producer gửi:
  Event A -> orders-0
  Event B -> orders-1
  Event C -> orders-2

Broker có thể append:
  orders-2: Event C
  orders-0: Event A
  orders-1: Event B
```

Kết quả này không vi phạm ordering của Kafka vì ba record thuộc ba log độc lập. Nếu nghiệp vụ yêu cầu Event A phải được ghi nhận trước Event B trên toàn topic, thiết kế nhiều partition không thể tự bảo đảm yêu cầu đó.

Ngay cả khi một thread gọi `send(A)` rồi `send(B)`, nếu A và B đi đến các partition khác nhau thì không có một thứ tự append toàn cục mà consumer có thể dựa vào. Future hoàn tất của hai lần gửi cũng có thể theo thứ tự khác thứ tự gọi.

## 3. Phân biệt ba mức ordering

Trước khi chọn số partition, hãy phân loại yêu cầu:

| Mức ordering | Ví dụ | Thiết kế phù hợp |
|---|---|---|
| Không cần thứ tự giữa các event | Ghi nhận view, telemetry, cập nhật độc lập | Nhiều partition và consumer xử lý song song |
| Thứ tự theo key/entity | Sự kiện của cùng `orderId` hoặc `accountId` | Key ổn định để các event cùng entity vào một partition |
| Thứ tự toàn cục | Mọi giao dịch phải theo cùng một trình tự | Một partition hoặc một cơ chế sequencing tập trung |

Đa số hệ thống nghiệp vụ không cần mọi event toàn hệ thống có thứ tự tuyệt đối. Thường chỉ cần thứ tự theo aggregate hoặc entity. Chọn đúng phạm vi giúp tận dụng song song mà không phải ép toàn bộ topic vào một partition.

## 4. Giữ thứ tự theo key giữa nhiều partition

Cách phổ biến là dùng key đại diện cho entity cần giữ thứ tự. Với partitioner mặc định, các record có cùng key thường được hash vào cùng partition, miễn là topic có cùng số partition và partitioning strategy không đổi.

Ví dụ producer gửi sự kiện đơn hàng:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    OrderPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    void publish(OrderEvent event) {
        kafkaTemplate.send(
                "orders",
                event.orderId(),
                event
        );
    }
}
```

Nếu các event của `order-101` đều dùng key `order-101`, chúng sẽ đi cùng partition trong cùng một partitioning strategy. Các event của `order-202` có thể được gửi đến partition khác và được xử lý song song.

Ví dụ:

```text
key=order-101 -> orders-0:
  OrderCreated
  PaymentRequested
  OrderConfirmed

key=order-202 -> orders-1:
  OrderCreated
  PaymentRequested

key=order-303 -> orders-2:
  OrderCreated
  PaymentRequested
```

Kafka giữ thứ tự trong từng partition. Do đó, event cùng key có thể được tiêu thụ theo thứ tự offset trong partition đó, trong khi các key khác nhau chạy song song.

Cách này thường được gọi là per-key ordering hoặc per-entity ordering. Nó không tạo thứ tự giữa `order-101` và `order-202`.

## 5. Chọn key theo aggregate, không theo loại event

Key cần phản ánh đối tượng mà các sự kiện phải được xử lý theo thứ tự. Ví dụ:

| Luồng dữ liệu | Key nên cân nhắc | Vì sao |
|---|---|---|
| Vòng đời đơn hàng | `orderId` | Các trạng thái của một đơn hàng cần tuần tự |
| Số dư tài khoản | `accountId` | Các giao dịch trên cùng tài khoản cần theo trình tự |
| Hồ sơ khách hàng | `customerId` | Các cập nhật cùng khách hàng cần nhất quán |
| Thiết bị IoT | `deviceId` | Sự kiện của một thiết bị có thứ tự riêng |
| Kho hàng | `sku` hoặc `warehouseId + sku` | Cập nhật tồn kho cùng mặt hàng cần tuần tự |

Không nên chọn event type làm key nếu nhiều loại event của cùng entity phải theo thứ tự. Ví dụ key `OrderCreated` và `PaymentRequested` có thể đưa hai loại event vào các partition khác nhau; cách chọn này không bảo đảm các event của cùng đơn hàng nằm chung partition.

Một key tốt thường có các đặc điểm:

- Ổn định trong suốt vòng đời entity.
- Không null nếu nghiệp vụ yêu cầu per-entity ordering.
- Có phân bố đủ tốt để tránh dồn quá nhiều tải vào một partition.
- Được tất cả producer dùng thống nhất.
- Không thay đổi định dạng hoặc cách serialize giữa các service nếu điều đó làm thay đổi hash key.

## 6. Tại sao timestamp không tạo ordering giữa partition?

Record có timestamp, nhưng timestamp không phải global sequence.

Producer có thể chạy trên các máy khác nhau với clock lệch nhau. Hai event đồng thời có thể có cùng timestamp. Broker dùng `CreateTime` hoặc `LogAppendTime` theo cấu hình, nhưng timestamp của record trên hai partition vẫn không tạo quan hệ append toàn cục.

Ví dụ:

```text
orders-0:
  offset 10, timestamp 10:00:00.100 -> OrderCreated

orders-1:
  offset 22, timestamp 10:00:00.090 -> PaymentRequested
```

Không thể chỉ dựa vào timestamp để kết luận PaymentRequested thực sự xảy ra trước OrderCreated. Timestamp có thể bị ảnh hưởng bởi clock skew, độ trễ mạng, batch và cách broker ghi nhận.

Nếu nghiệp vụ cần sắp xếp theo thời gian sự kiện, có thể dùng event time cùng watermark và quy tắc xử lý late event. Nhưng đó là bài toán xử lý dữ liệu theo event time, không phải bảo đảm ordering của Kafka.

## 7. Consumer group đọc nhiều partition như thế nào?

Trong một consumer group, mỗi partition được gán cho tối đa một consumer member tại một thời điểm. Một consumer có thể nhận nhiều partition. Khi có nhiều consumer, Kafka phân phối partition theo assignor.

Ví dụ topic có 6 partition và group có 3 consumer:

```text
Consumer A -> orders-0, orders-1
Consumer B -> orders-2, orders-3
Consumer C -> orders-4, orders-5
```

Mỗi consumer đọc các partition được gán và giữ thứ tự trong từng partition. Tuy nhiên, consumer không tạo ra thứ tự chung giữa các partition mà nó đang đọc.

Nếu group có concurrency lớn hơn 1 trong Spring Kafka, container tạo các consumer thread. Các thread xử lý partition được gán độc lập; record ở partition khác có thể được listener xử lý hoặc hoàn tất trước.

`@KafkaListener` với concurrency:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-projection",
            concurrency = "3"
    )
    public void onOrder(OrderEvent event) {
        projectionService.apply(event);
    }
}
```

Concurrency giúp xử lý nhiều partition song song. Nó không đảm bảo thứ tự toàn cục. Nếu yêu cầu ordering theo key, producer phải đảm bảo cùng key vào cùng partition và consumer phải giữ thứ tự xử lý trong partition đó.

## 8. Batch poll không có global ordering giữa partition

Một lần `poll()` có thể trả record từ nhiều partition. Các record có thứ tự trong từng partition, nhưng ứng dụng không nên dựa vào thứ tự iteration của toàn bộ batch để suy ra thứ tự giữa các partition.

Ví dụ batch có:

```text
orders-0: offset 10, 11, 12
orders-1: offset 7, 8
orders-2: offset 20, 21
```

Có thể xử lý tuần tự từng partition theo offset, nhưng không có căn cứ nói record `orders-0` offset 10 phải được xử lý trước `orders-1` offset 7.

Với batch listener, nếu logic cần thứ tự cục bộ, hãy nhóm record theo topic-partition và xử lý từng nhóm theo offset. Không áp đặt thứ tự giữa các nhóm:

```java
import java.util.List;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class BatchOrderListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-batch",
            containerFactory = "batchFactory"
    )
    public void onBatch(
            List<ConsumerRecord<String, OrderEvent>> records) {

        Map<TopicPartition, List<ConsumerRecord<String, OrderEvent>>> byPartition =
                new HashMap<>();

        for (ConsumerRecord<String, OrderEvent> record : records) {
            TopicPartition topicPartition =
                    new TopicPartition(record.topic(), record.partition());
            byPartition.computeIfAbsent(
                    topicPartition,
                    ignored -> new ArrayList<>()
            ).add(record);
        }

        for (List<ConsumerRecord<String, OrderEvent>> partitionRecords
                : byPartition.values()) {
            partitionRecords.sort(
                    Comparator.comparingLong(
                            (ConsumerRecord<String, OrderEvent> record) ->
                                    record.offset()
                    )
            );

            for (ConsumerRecord<String, OrderEvent> record : partitionRecords) {
                log.info(
                        "key={}, partition={}, offset={}",
                        record.key(),
                        record.partition(),
                        record.offset()
                );
            }
        }
    }
}
```

Không tự sắp xếp tất cả record theo offset đơn thuần vì offset ở các partition không cùng một thang đo. Nếu cần merge theo một trường nghiệp vụ như sequence hoặc event time, phải có quy tắc merge riêng.

## 9. Khi nào cần global ordering?

Nếu mọi event đều phải theo một thứ tự duy nhất, cách đơn giản nhất là ghi chúng vào một partition. Một partition chỉ có một leader và một log thứ tự, vì vậy mọi record được append vào partition đó có một vị trí offset chung.

Ví dụ:

```text
events-0:
  offset 0 -> AccountOpened
  offset 1 -> MoneyDeposited
  offset 2 -> MoneyWithdrawn
  offset 3 -> AccountClosed
```

Đổi lại, một partition giới hạn khả năng ghi và đọc song song của topic. Một consumer group cũng chỉ có một consumer có thể được gán partition này tại một thời điểm. Đây là đánh đổi giữa global ordering và throughput/parallelism.

Một partition tạo ra một thứ tự append duy nhất do broker xác lập. Nếu nhiều producer cùng gửi, thứ tự đó vẫn là thứ tự broker xử lý request; nó không tự biết thứ tự nghiệp vụ mà các producer mong muốn. Khi cần bảo đảm trình tự nghiệp vụ toàn cục, ứng dụng phải tuần tự hóa việc phát event hoặc dùng một sequencer/owner có trách nhiệm điều phối trước khi gửi.

Một topic một partition phù hợp khi:

- Lưu lượng nhỏ hoặc vừa.
- Mọi event thật sự cần cùng một trình tự.
- Độ trễ và throughput có thể đáp ứng với một partition.
- Hệ thống chấp nhận một điểm giới hạn song song.

Không nên dùng một partition chỉ vì muốn dễ hiểu. Nếu chỉ cần thứ tự theo account hoặc order, per-key ordering thường mở rộng tốt hơn.

## 10. Dùng sequence number để merge nhiều partition

Nếu dữ liệu phải được ghi trên nhiều partition nhưng consumer cần khôi phục một thứ tự nghiệp vụ chung, ứng dụng có thể gắn sequence number hoặc global event number.

Ví dụ:

```java
public record BusinessEvent(
        long globalSequence,
        String aggregateId,
        String eventType,
        String payload
) {
}
```

Consumer có thể dùng sequence để kiểm tra sự kiện nào đến trước, sự kiện nào đến sau. Tuy nhiên, chỉ thêm sequence number chưa đủ để tạo ordering. Consumer phải có cơ chế:

1. Biết sequence tiếp theo đang chờ.
2. Lưu tạm event đến trước hoặc sau thứ tự mong muốn.
3. Phát hiện gap khi thiếu sequence.
4. Chờ event bị thiếu hoặc áp dụng timeout.
5. Xử lý duplicate và sequence cũ.
6. Xử lý phục hồi sau restart mà không làm mất buffer.

Ví dụ consumer nhận sequence 12 trước sequence 11:

```text
Expected sequence = 11

Received 12:
  buffer event 12
  wait for event 11

Received 11:
  process 11
  process buffered 12
  Expected sequence = 13
```

Đây là resequencing. Nó yêu cầu state và có thể làm tăng độ trễ. Nếu event 11 bị mất hoặc không bao giờ được phát, consumer cần chính sách timeout, cảnh báo hoặc xử lý gap.

Global sequence cũng cần được cấp bởi một cơ chế có tính tuần tự. Nếu mỗi producer tự tăng số đếm trong bộ nhớ, các instance có thể tạo sequence trùng hoặc sai thứ tự. Có thể dùng database sequence, transactional outbox hoặc một service sequencing tập trung, nhưng phải phối hợp việc cấp sequence với thứ tự publish để không tạo gap giả.

## 11. Resequencer cần quản lý state như thế nào?

Một resequencer thường giữ state theo luồng cần sắp xếp. Nếu thứ tự toàn cục, state được chia sẻ cho toàn bộ stream; nếu thứ tự theo aggregate, state có thể được partition theo aggregate ID.

Các thành phần cơ bản:

| Thành phần | Trách nhiệm |
|---|---|
| Expected sequence | Số thứ tự kế tiếp cần xử lý |
| Pending buffer | Event đã nhận nhưng còn thiếu event trước |
| Duplicate detection | Nhận diện event đã xử lý hoặc sequence cũ |
| Gap timer | Phát hiện sequence bị thiếu quá lâu |
| Recovery state | Lưu expected sequence và buffer để phục hồi sau restart |
| Poison/gap handling | Quyết định dừng, cảnh báo, bỏ qua hoặc chuyển luồng lỗi |

Không nên giữ pending buffer vô hạn. Cần giới hạn số event, dung lượng và thời gian chờ; nếu vượt ngưỡng thì phát cảnh báo và áp dụng chính sách phục hồi.

Nếu event đến từ nhiều partition, consumer phải quản lý offset commit cẩn thận. Không commit offset của event đã được buffer như thể event đã hoàn tất nghiệp vụ nếu việc phục hồi buffer chưa được lưu bền vững. Có thể lưu event vào durable store trước khi commit Kafka offset, hoặc dùng một thiết kế stateful stream processor có checkpoint phù hợp.

## 12. Kafka Streams và repartition theo key

Kafka Streams cho phép xử lý, group và repartition dữ liệu theo key. Khi cần per-key ordering, một thao tác repartition theo aggregate ID có thể đưa các record cùng key về cùng partition của internal topic.

Ví dụ ý tưởng:

```java
KStream<String, OrderEvent> orders = builder.stream("orders");

KStream<String, OrderEvent> byOrderId =
        orders.selectKey((oldKey, event) -> event.orderId())
              .repartition();

byOrderId.processValues(() -> new OrderStateProcessor());
```

Các record có cùng key được xử lý trong cùng partition sau repartition. Kafka Streams duy trì thứ tự record theo partition trong topology, nhưng không tạo global ordering giữa các partition. Nếu cần một thứ tự toàn cục, repartition topic cũng phải có một partition hoặc phải có sequencing/resequencing ở tầng ứng dụng.

Repartition giúp chuẩn hóa key khi upstream topic dùng key chưa phù hợp. Nó không khắc phục được thứ tự nghiệp vụ đã bị mất trước khi record đến topology.

## 13. Retry và dead-letter có thể ảnh hưởng ordering

Khi một record lỗi, cách retry quyết định record sau có được xử lý tiếp hay không.

Với blocking retry trong listener container, consumer thường dừng tiến trình của partition liên quan trong lúc retry hoặc phục hồi record, giúp tránh xử lý record sau vượt qua record lỗi tùy cấu hình error handler.

Với non-blocking retry dùng retry topic, record lỗi được chuyển sang topic retry và các record tiếp theo trên topic gốc có thể tiếp tục được xử lý. Điều này tăng throughput nhưng có thể làm đảo thứ tự nghiệp vụ theo key:

```text
Topic gốc:
  offset 10 -> OrderCreated
  offset 11 -> PaymentRequested (bị lỗi, chuyển retry topic)
  offset 12 -> OrderConfirmed (được xử lý ngay)

Retry topic:
  PaymentRequested được xử lý sau

Kết quả side effect:
  OrderCreated
  OrderConfirmed
  PaymentRequested
```

Nếu cần ordering nghiêm ngặt theo key, hãy đánh giá kỹ blocking retry, partition pausing hoặc thiết kế retry có sequencing. Không dùng retry topic mặc định mà bỏ qua tác động đến thứ tự của các event tiếp theo.

Dead-letter topic lưu record không xử lý được để điều tra hoặc xử lý lại. Khi replay từ DLT, cần kiểm tra aggregate sequence/version và tránh ghi side effect cũ đè lên trạng thái mới.

## 14. Thay đổi số partition ảnh hưởng per-key ordering

Với partitioner hash mặc định, partition được chọn dựa trên key và số partition hiện tại. Khi tăng số partition, cùng key có thể được ánh xạ sang partition khác.

Ví dụ:

```text
Trước khi tăng:
  order-101 -> orders-1

Sau khi tăng:
  order-101 -> orders-4
```

Event cũ của `order-101` vẫn ở partition 1, event mới có thể ở partition 4. Hai partition có offset riêng, vì vậy consumer không thể suy ra thứ tự liên tục giữa các event cũ và mới chỉ bằng offset.

Nếu per-key ordering là yêu cầu quan trọng:

- Xác định số partition theo dự báo tải dài hạn.
- Có kế hoạch migration khi cần tăng partition.
- Cân nhắc partitioner ổn định hoặc chiến lược shard có version.
- Đưa aggregate sequence vào event để phát hiện thứ tự bị đứt.
- Có thể chuyển sang topic mới và thực hiện cutover có kiểm soát nếu cần thay đổi topology.

Không tăng partition tùy tiện trong topic đang có yêu cầu thứ tự theo key mà chưa đánh giá tác động.

## 15. Consumer concurrency và side effect

Ngay cả khi producer đã gửi đúng thứ tự vào một partition, consumer vẫn có thể làm side effect sai thứ tự nếu ứng dụng tự chuyển record sang executor hoặc xử lý bất đồng bộ.

Ví dụ:

```text
Partition orders-0:
  offset 10 -> OrderCreated
  offset 11 -> PaymentRequested
  offset 12 -> OrderConfirmed

Worker pool:
  task 10: xử lý 500 ms
  task 11: xử lý 100 ms
  task 12: xử lý 50 ms
```

Task 12 có thể hoàn tất trước task 10. Kafka không thể kiểm soát thứ tự ghi database sau khi listener đã chuyển việc ra thread khác.

Để giữ thứ tự end-to-end:

- Xử lý tuần tự record trong từng partition.
- Nếu cần xử lý song song, dùng queue/worker theo key để cùng key luôn vào một luồng tuần tự.
- Chỉ commit offset khi công việc tương ứng đã hoàn tất theo semantics đã chọn.
- Dùng optimistic locking hoặc aggregate version để ngăn cập nhật cũ ghi đè trạng thái mới.
- Làm handler idempotent vì record có thể được giao lại sau lỗi hoặc rebalance.

Concurrency của Spring Kafka tăng số consumer thread; nó không tạo global ordering giữa các partition. Trong cùng group, một partition chỉ được gán cho một consumer member tại một thời điểm, nhưng một consumer có thể quản lý nhiều partition.

## 16. Chọn chiến lược ordering theo yêu cầu

| Yêu cầu | Chiến lược | Đánh đổi |
|---|---|---|
| Không cần thứ tự giữa event | Nhiều partition, consumer song song | Throughput cao, logic đơn giản |
| Thứ tự theo entity | Key theo aggregate ID | Song song giữa entity, mỗi entity tuần tự |
| Thứ tự toàn cục | Một partition hoặc sequencer tập trung | Giới hạn throughput, tăng coordination |
| Merge event từ nhiều partition theo sequence | Sequence number + resequencer | Cần buffer, durable state và xử lý gap |
| Đổi key ở upstream | Kafka Streams repartition | Có thêm internal topic và chi phí chuyển dữ liệu |
| Retry nhưng vẫn cần thứ tự | Blocking retry hoặc retry có sequencing | Có thể giảm throughput và tăng độ trễ |

Không có cấu hình `acks`, `retries` hay `concurrency` nào tự tạo global ordering giữa nhiều partition. Đây là quyết định kiến trúc về cách chia log và cách ứng dụng điều phối sự kiện.

## 17. Kiểm chứng ordering giữa nhiều partition

Khi kiểm thử, hãy tạo event có aggregate ID và sequence number:

```java
public record OrderEvent(
        String orderId,
        long sequence,
        String eventType
) {
}
```

Producer phát các event của nhiều đơn hàng:

```java
kafkaTemplate.send(
        "orders",
        "order-101",
        new OrderEvent("order-101", 1, "OrderCreated")
);

kafkaTemplate.send(
        "orders",
        "order-101",
        new OrderEvent("order-101", 2, "PaymentRequested")
);

kafkaTemplate.send(
        "orders",
        "order-202",
        new OrderEvent("order-202", 1, "OrderCreated")
);
```

Consumer ghi log partition, offset và sequence:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(topics = "orders", groupId = "orders-audit")
public void audit(ConsumerRecord<String, OrderEvent> record) {
    OrderEvent event = record.value();

    log.info(
            "orderId={}, sequence={}, partition={}, offset={}",
            event.orderId(),
            event.sequence(),
            record.partition(),
            record.offset()
    );
}
```

Các điểm nên xác minh:

1. Event cùng `orderId` đi vào cùng partition.
2. Offset tăng theo sequence trong từng entity.
3. Event của entity khác có thể nằm ở partition khác và được xử lý song song.
4. Không so sánh offset của hai partition như một thứ tự chung.
5. Kiểm thử với consumer concurrency lớn hơn 1.
6. Kiểm thử retry, rebalance và replay từ DLT nếu ordering là yêu cầu quan trọng.
7. Kiểm thử tăng partition trên môi trường thử nghiệm nếu thiết kế có thể thay đổi partition count.

Nếu cần global ordering, hãy kiểm thử cả cơ chế cấp sequence, buffer, gap detection và phục hồi state của resequencer. Chỉ quan sát timestamp hoặc thời điểm callback hoàn tất là chưa đủ.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách xử lý |
|---|---|---|
| Offset lớn hơn nghĩa là event mới hơn trên toàn topic | Offset chỉ thuộc một partition | So sánh trong cùng topic-partition |
| Timestamp quyết định thứ tự giữa partition | Clock skew và broker timing có thể khác nhau | Dùng sequence hoặc event-time watermark theo nghiệp vụ |
| Cùng key bảo đảm global order | Cùng key chỉ giúp chọn cùng partition theo partitioner | Dùng một partition hoặc sequencer nếu cần thứ tự toàn cục |
| Tăng concurrency vẫn giữ thứ tự mọi event | Consumer xử lý các partition độc lập | Xác định ordering scope và serialize theo key |
| Một lần poll trả list có thứ tự toàn topic | Batch có thể chứa record từ nhiều partition độc lập | Xử lý theo partition hoặc dùng quy tắc merge riêng |
| Retry topic giữ nguyên thứ tự topic gốc | Non-blocking retry có thể để event sau đi trước | Chọn retry strategy theo yêu cầu ordering |
| Kafka transaction tạo global order | Transaction bảo đảm atomic visibility, không tạo thứ tự tổng thể giữa partition | Dùng key/partition hoặc sequencing |
| Tăng partition không ảnh hưởng key | Hash mapping có thể đổi partition | Lập kế hoạch migration và sequence validation |

## 19. Checklist thiết kế ordering giữa nhiều partition

1. Xác định nghiệp vụ cần ordering toàn cục, theo key hay không cần ordering.
2. Chọn key theo aggregate/entity cần xử lý tuần tự.
3. Bảo đảm các producer dùng cùng quy ước key và partitioning.
4. Không dùng timestamp hoặc offset để suy ra thứ tự giữa các partition.
5. Giữ consumer xử lý tuần tự trong partition nếu side effect cần ordering.
6. Nếu xử lý bất đồng bộ, dùng worker/queue có thứ tự theo key.
7. Đánh giá retry topic và DLT vì chúng có thể thay đổi thứ tự side effect.
8. Lập kế hoạch thay đổi partition count.
9. Dùng sequence/version để phát hiện gap hoặc event đến sai thứ tự.
10. Nếu bắt buộc global ordering, cân nhắc một partition hoặc sequencer tập trung và chấp nhận giới hạn throughput.

Kafka cung cấp thứ tự cục bộ trong từng partition. Muốn giữ thứ tự giữa nhiều partition, ứng dụng phải định nghĩa phạm vi ordering và bổ sung chiến lược phù hợp: key để giữ thứ tự theo entity, một partition để có log toàn cục, hoặc sequence/resequencer để hợp nhất nhiều luồng. Chọn đúng phạm vi giúp hệ thống tận dụng xử lý song song mà vẫn bảo vệ được thứ tự nghiệp vụ cần thiết.
