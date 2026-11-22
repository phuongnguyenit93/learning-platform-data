# Partition là đơn vị ordering của Kafka

Kafka tổ chức dữ liệu của mỗi topic thành một hoặc nhiều partition. Mỗi partition là một log append-only có thứ tự: broker ghi record nối tiếp vào log và gán offset tăng dần cho từng vị trí. Consumer đọc một partition theo thứ tự offset, vì vậy partition là đơn vị ordering mà Kafka bảo đảm.

Một topic có thể có nhiều partition để phân tán dữ liệu và xử lý song song. Đổi lại, Kafka không tạo thứ tự tổng thể giữa các partition. Nếu hai event được ghi vào hai partition khác nhau, consumer có thể đọc và xử lý chúng song song; không thể suy ra event nào phải được quan sát trước chỉ bằng offset hoặc timestamp.

Khi nghiệp vụ cần giữ thứ tự theo một thực thể như đơn hàng, tài khoản hoặc sản phẩm, producer thường dùng định danh thực thể làm record key để các event liên quan được định tuyến vào cùng partition. Khi nghiệp vụ không cần thứ tự theo thực thể, có thể dùng key khác hoặc không có key để tận dụng khả năng phân phối tải. Lựa chọn partitioning vì thế là một quyết định về cả ordering lẫn throughput.

Bài học thuộc chương **Partition và ordering** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Partition là gì?

Topic là tên luồng dữ liệu logic mà producer gửi record vào và consumer đăng ký đọc. Một topic được chia thành các partition. Mỗi partition có log riêng, leader replica và chuỗi offset riêng.

Ví dụ topic `order-events` có ba partition:

~~~text
Topic: order-events

Partition 0:  [offset 0] [offset 1] [offset 2] [offset 3] ...
Partition 1:  [offset 0] [offset 1] [offset 2] ...
Partition 2:  [offset 0] [offset 1] [offset 2] [offset 3] ...
~~~

Các offset trên chỉ có ý nghĩa trong partition tương ứng. Record ở partition 0 offset 3 không thể được so sánh thứ tự trực tiếp với record ở partition 1 offset 2. Mỗi partition có log và tiến độ độc lập.

Partition phục vụ hai mục tiêu chính:

- **Ordering:** Kafka duy trì thứ tự append và đọc trong từng partition.
- **Parallelism:** nhiều partition cho phép nhiều consumer trong cùng group đọc song song các phần dữ liệu khác nhau.

Một partition tại một thời điểm chỉ được gán cho tối đa một consumer đang hoạt động trong cùng consumer group. Một consumer có thể nhận nhiều partition. Vì vậy, số partition đặt giới hạn trên cho mức song song đọc trong một group, dù throughput thực tế còn phụ thuộc broker, network, producer, consumer và logic nghiệp vụ.

## 2. Ordering được bảo đảm ở phạm vi nào?

Kafka bảo đảm thứ tự trong một partition theo thứ tự record được append vào log. Khi consumer đọc partition, record được trả về theo thứ tự offset.

Kafka không bảo đảm:

- Thứ tự tổng thể giữa các partition của cùng topic.
- Thứ tự giữa các topic khác nhau.
- Thứ tự event theo timestamp nghiệp vụ nếu producer gửi chúng không theo thời gian đó.
- Thứ tự hoàn thành của các tác vụ mà ứng dụng tự xử lý bất đồng bộ hoặc chuyển sang thread pool.
- Thứ tự giữa các record cùng thực thể nếu producer gửi chúng vào các partition khác nhau.

Ví dụ:

~~~text
Partition 0:
  offset 10: OrderCreated(order-1)
  offset 11: OrderPaid(order-1)
  offset 12: OrderShipped(order-1)

Partition 1:
  offset 20: OrderCreated(order-2)
  offset 21: OrderCancelled(order-2)
~~~

Trong partition 0, Kafka giữ thứ tự OrderCreated, OrderPaid, OrderShipped. Trong partition 1, Kafka giữ thứ tự OrderCreated, OrderCancelled. Nhưng không có thứ tự toàn cục giữa offset 10 ở partition 0 và offset 20 ở partition 1.

Nếu một consumer group có hai consumer, mỗi consumer có thể đọc một partition và xử lý song song. Đây là cách Kafka tăng throughput mà vẫn duy trì thứ tự trong từng partition.

## 3. Offset biểu diễn thứ tự như thế nào?

Offset là vị trí của record trong một partition. Khi broker append record mới, nó gán offset tiếp theo trong log của partition đó.

Ví dụ:

| Partition | Record | Offset |
| --- | --- | ---: |
| 0 | OrderCreated(order-1) | 100 |
| 0 | OrderPaid(order-1) | 101 |
| 0 | OrderShipped(order-1) | 102 |
| 1 | OrderCreated(order-2) | 80 |
| 1 | OrderCancelled(order-2) | 81 |

Consumer đọc partition 0 theo offset 100, 101, 102. Consumer đọc partition 1 theo offset 80, 81. Các offset này không phải số thứ tự của topic; offset 102 không có nghĩa record đó luôn xảy ra sau offset 81 ở partition khác.

Offset cũng không phải timestamp. Một event có occurredAt sớm hơn vẫn có thể được producer gửi sau và nhận offset lớn hơn. Nếu nghiệp vụ cần sắp xếp theo event time, cần thiết kế timestamp, watermark hoặc cơ chế xử lý thời gian riêng; không thể dùng offset của nhiều partition để tạo thứ tự thời gian toàn cục.

Trong log compaction hoặc với transaction, có thể có khoảng trống offset mà consumer không nhìn thấy như một record nghiệp vụ thông thường. Điều đó không phá vỡ quy tắc thứ tự: các record mà consumer nhận vẫn được đọc theo vị trí log trong partition.

## 4. Dùng key để giữ thứ tự theo thực thể

Cách phổ biến để giữ thứ tự cho các event của cùng một thực thể là sử dụng định danh thực thể làm key.

Ví dụ, các event của cùng đơn hàng dùng orderId:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {

        return kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );
    }
}
~~~

Với partitioner mặc định và key không null, Kafka producer dùng key đã serialize để chọn partition. Các record cùng key thường được định tuyến đến cùng partition trong cùng một topology partition.

Ví dụ minh họa:

~~~text
Topic order-events có 3 partition

key = order-1:
  OrderCreated  ─┐
  OrderPaid     ─┼──> Partition 1
  OrderShipped  ─┘

key = order-2:
  OrderCreated  ─┐
  OrderCancelled ─┴──> Partition 0
~~~

Khi cùng orderId được định tuyến vào một partition, consumer đọc các event đó theo thứ tự offset của partition. Điều này tạo nền tảng cho xử lý tuần tự theo đơn hàng.

Tuy nhiên, key chỉ đảm bảo định tuyến ổn định theo thuật toán và topology đang dùng. Nó không tự xác minh event có đúng thứ tự nghiệp vụ hay không. Nếu hai producer gửi event cùng key đồng thời, thứ tự append phản ánh thứ tự broker nhận và xử lý các request, không nhất thiết là thứ tự xảy ra nghiệp vụ ở hai service.

## 5. Chọn key theo yêu cầu nghiệp vụ

Key nên đại diện cho đơn vị dữ liệu cần được xử lý tuần tự. Một số ví dụ:

| Domain | Key thường dùng | Lý do |
| --- | --- | --- |
| Đơn hàng | orderId | Giữ thứ tự thay đổi trạng thái của một đơn hàng. |
| Tài khoản | accountId | Tuần tự hóa các cập nhật liên quan số dư hoặc trạng thái tài khoản. |
| Kho hàng | sku hoặc warehouseId + sku | Giữ thứ tự cập nhật tồn kho cho một mặt hàng trong một kho. |
| Thiết bị | deviceId | Giữ thứ tự telemetry hoặc trạng thái theo thiết bị. |
| Khách hàng | customerId | Tuần tự hóa các event liên quan một khách hàng khi nghiệp vụ yêu cầu. |

Không nên chọn key chỉ vì field đó luôn có sẵn. Nếu key có cardinality thấp, ví dụ chỉ dùng country hoặc eventType, nhiều record có thể dồn vào một partition. Đây là hiện tượng hot partition và làm giảm khả năng song song.

Key tốt cần cân bằng hai yêu cầu:

- Các event cần thứ tự phải có cùng key.
- Các key khác nhau nên phân bố đủ đều qua partition để tránh một partition quá tải.

Nếu một thực thể có lượng event quá lớn, dùng một key duy nhất có thể tạo bottleneck không thể giải quyết chỉ bằng tăng consumer. Cần xem lại yêu cầu ordering: có thật sự cần tuần tự toàn bộ event của thực thể đó hay có thể chia theo sub-entity/aggregate nhỏ hơn.

## 6. Partitioner chọn partition như thế nào?

Producer chọn partition trước khi gửi record tới broker. Các trường hợp thường gặp:

1. Ứng dụng chỉ định partition trực tiếp trong ProducerRecord.
2. Record có key; partitioner dùng key đã serialize để chọn partition.
3. Record không có key; partitioner dùng chiến lược dành cho key null, thường có sticky partitioning ở Kafka client hiện đại.
4. Ứng dụng cấu hình custom partitioner để thực hiện quy tắc riêng.

Với partitioner mặc định, key không null thường được băm rồi ánh xạ vào số partition hiện có. Có thể hình dung đơn giản:

\[
\text{partition} = \text{positive(hash(serializedKey))} \bmod N
\]

Trong đó N là số partition của topic. Đây là mô tả khái quát; thuật toán cụ thể phụ thuộc partitioner và phiên bản Kafka client.

Điểm quan trọng là partitioner sử dụng byte của key sau serialization. Nếu hai producer dùng serializer hoặc cách chuẩn hóa key khác nhau, cùng một giá trị nghiệp vụ có thể không tạo ra cùng byte và không nhất thiết đi đến cùng partition.

Khi dùng custom partitioner, cần bảo đảm tất cả producer gửi cùng loại key tuân theo một quy tắc nhất quán. Nếu mỗi service dùng một thuật toán khác nhau, ordering theo key có thể bị phá vỡ dù payload chứa cùng orderId.

## 7. Gửi record không key và ordering

Nếu producer không cung cấp key, partitioner chọn partition theo chiến lược dành cho record không key. Với Kafka client hiện đại, partitioner mặc định thường dùng sticky partitioning: giữ một partition trong một khoảng/batch để gom record hiệu quả rồi có thể chuyển sang partition khác.

Điều này giúp batching và throughput, nhưng không tạo affinity theo entity. Hai event của cùng một order có thể vào hai partition khác nhau nếu producer không truyền orderId làm key.

Ví dụ:

~~~java
// Không có key: không bảo đảm các event cùng orderId ở cùng partition
kafkaTemplate.send("order-events", event);

// Có key: định tuyến theo orderId
kafkaTemplate.send("order-events", event.orderId(), event);
~~~

Nếu nghiệp vụ cần thứ tự theo orderId, không nên dựa vào sticky partitioning hoặc việc các event tình cờ vào cùng partition. Hãy truyền key rõ ràng.

## 8. Tăng số partition có thể ảnh hưởng ordering theo key

Với partitioner dựa trên hash và modulo số partition, thay đổi số partition có thể thay đổi kết quả ánh xạ key. Ví dụ key order-1 trước đây được đưa vào partition 1 khi topic có ba partition; sau khi tăng lên sáu partition, key đó có thể được đưa vào partition 4.

Các record cũ vẫn nằm trong partition cũ. Record mới có thể đi vào partition mới. Khi đó, consumer có thể đọc các event cũ và mới của cùng orderId từ hai partition khác nhau; Kafka không bảo đảm thứ tự giữa chúng.

Vì vậy, tăng partition không phải thay đổi vô hại nếu ordering theo key là yêu cầu quan trọng.

Trước khi tăng partition, cần cân nhắc:

- Có thể chấp nhận giai đoạn một key xuất hiện ở cả partition cũ và mới không?
- Có cần drain backlog trước khi thay đổi không?
- Có thể version topic hoặc tạo topic mới với topology mới không?
- Consumer có cần phối hợp event sequence/version để phát hiện event đến sai thứ tự không?
- Có thể dùng custom partitioning ổn định hơn hay không?

Một cách an toàn về kiến trúc là xem partition count như một phần của contract vận hành topic, không tùy tiện thay đổi sau khi hệ thống đã phát sinh dữ liệu phụ thuộc thứ tự.

## 9. Producer concurrency, retries và thứ tự gửi

KafkaProducer hỗ trợ gửi bất đồng bộ và gom batch. Nhiều thread có thể gọi send trên cùng producer; producer quản lý request và partition buffer.

Với cùng một partition, Kafka duy trì thứ tự append theo thứ tự record được producer đưa vào luồng gửi và broker ghi nhận. Tuy nhiên, retries và nhiều request đang bay có thể ảnh hưởng ordering nếu cấu hình producer không phù hợp.

Khi idempotence bị tắt, retries được bật và `max.in.flight.requests.per.connection` lớn hơn một, một batch lỗi có thể được gửi lại sau một batch mới hơn, dẫn tới record bị reorder trong một số tình huống. Idempotent producer giúp bảo vệ thứ tự khi retry theo cơ chế sequence number của Kafka.

Cấu hình producer thường được cân nhắc:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "enable.idempotence": true
~~~

Idempotence yêu cầu các cấu hình liên quan tương thích. Kafka client hiện đại kiểm tra nhiều ràng buộc; nếu override retries hoặc max in-flight, cần đối chiếu tài liệu đúng phiên bản client. Idempotence bảo vệ retry ở tầng producer, không giải quyết việc ứng dụng chủ động phát cùng một event hai lần hoặc hai producer cạnh tranh thứ tự nghiệp vụ.

Nếu thứ tự của event cùng key quan trọng, nên giữ một quy tắc gửi rõ ràng từ producer, dùng key ổn định và tránh phân tán cùng một chuỗi event qua nhiều producer độc lập mà không có cơ chế sequence/version nghiệp vụ.

## 10. Consumer đọc tuần tự trong partition

Kafka consumer đọc các record theo thứ tự offset của từng partition được gán. Trong cùng consumer group, một partition tại một thời điểm được gán cho tối đa một consumer đang hoạt động.

Ví dụ topic có bốn partition và group có hai consumer:

~~~text
Topic order-events

Partition 0 ─┐
Partition 1 ─┼──> Consumer A
Partition 2 ─┐
Partition 3 ─┴──> Consumer B
~~~

Mỗi consumer có thể nhận nhiều partition, nhưng record trong mỗi partition vẫn được trả theo thứ tự offset. Consumer A có thể xử lý partition 0 và 1; consumer B xử lý partition 2 và 3. Không có thứ tự toàn cục giữa các record của bốn partition.

Spring Kafka listener container quản lý vòng poll và gọi listener. Ví dụ:

~~~java
@Component
public class OrderEventListener {

    @KafkaListener(
        topics = "order-events",
        groupId = "order-projection"
    )
    public void onOrderEvent(OrderEvent event) {
        orderProjection.apply(event);
    }
}
~~~

Với listener xử lý đồng bộ theo mặc định, container gọi phương thức listener trong luồng xử lý consumer. Khi listener hoàn tất, container tiếp tục theo cơ chế poll/ack/commit đã cấu hình.

## 11. Concurrency của listener container và ordering

Spring Kafka cho phép cấu hình concurrency để tạo nhiều consumer trong một listener container. Concurrency giúp đọc nhiều partition song song; nó không làm một partition được nhiều consumer trong cùng group xử lý đồng thời.

Ví dụ:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);
    return factory;
}
~~~

Nếu topic có bốn partition, concurrency bốn có thể cho phép mỗi consumer xử lý một partition. Nếu topic chỉ có hai partition, tối đa hai consumer có assignment hữu ích trong group tại một thời điểm.

Tăng concurrency không phá vỡ thứ tự đọc bên trong partition nếu container tiếp tục xử lý tuần tự theo consumer. Nhưng nếu listener tự gửi công việc sang thread pool hoặc xử lý bất đồng bộ, thứ tự hoàn thành tác vụ có thể khác thứ tự record.

Ví dụ nguy hiểm:

~~~java
@KafkaListener(topics = "order-events", groupId = "order-service")
public void onOrderEvent(OrderEvent event) {
    executor.submit(() -> orderService.handle(event));
}
~~~

Phương thức listener trả về ngay sau khi submit. Các tác vụ có thể hoàn tất theo thứ tự khác nhau, trong khi container có thể tiếp tục poll và commit theo cấu hình. Nếu nghiệp vụ yêu cầu tuần tự, cần chờ xử lý hoàn tất trước khi xác nhận record hoặc thiết kế executor có tuần tự hóa theo partition/key.

Không nên chỉ nhìn concurrency của container để kết luận ordering vẫn được bảo đảm; cần xem toàn bộ logic bên trong listener.

## 12. Retry có thể ảnh hưởng thứ tự như thế nào?

Khi listener xử lý một record thất bại, Spring Kafka có thể retry record theo error handler. Với blocking retry trên cùng partition, container có thể dừng tiến độ xử lý partition trong thời gian backoff/retry. Điều này giúp record sau không vượt qua record lỗi theo cách xử lý thông thường, nhưng làm giảm throughput của partition đó.

Nếu dùng non-blocking retry với retry topic, record lỗi được chuyển sang topic retry để xử lý sau, còn record tiếp theo trong topic gốc có thể tiếp tục. Khi đó, thứ tự nghiệp vụ giữa record lỗi và record đến sau không còn được bảo đảm như luồng tuần tự ban đầu.

Ví dụ:

~~~text
Topic gốc:
  OrderCreated(order-1)
  OrderPaid(order-1)       -> lỗi, chuyển sang retry topic
  OrderShipped(order-1)    -> xử lý trước khi OrderPaid retry thành công

Retry topic:
  OrderPaid(order-1)       -> xử lý sau
~~~

Nếu trạng thái đơn hàng cần chuyển theo đúng thứ tự, cần cân nhắc blocking retry, sequence number hoặc logic kiểm tra version ở consumer. Retry topic tăng khả năng cô lập lỗi và throughput nhưng có thể thay đổi thứ tự hoàn thành.

Với Spring Kafka, non-blocking retry có giới hạn và semantics phụ thuộc cách cấu hình retry topic và phiên bản. Cần xem tài liệu tương ứng trước khi kết hợp với batch listener hoặc transaction.

## 13. Rebalance không làm thay đổi thứ tự log

Rebalance xảy ra khi consumer group thay đổi thành viên, partition subscription hoặc assignment. Partition có thể được chuyển từ consumer này sang consumer khác.

Rebalance không sắp xếp lại record trong partition. Log và offset vẫn giữ thứ tự append. Consumer mới tiếp tục đọc từ committed offset của group theo chính sách đã cấu hình.

Tuy nhiên, record chưa commit có thể được đọc lại sau rebalance. Điều này tạo duplicate nhưng không có nghĩa Kafka đảo thứ tự trong log. Ứng dụng cần idempotency nếu xử lý lại cùng event có thể gây tác dụng phụ trùng lặp.

Nếu listener xử lý bất đồng bộ hoặc commit sai thời điểm, thứ tự hoàn tất nghiệp vụ có thể khác thứ tự log dù Kafka vẫn trả record theo offset.

## 14. Timestamp không thay thế partition ordering

Kafka record có timestamp, nhưng timestamp không tạo thứ tự toàn cục. Có thể có nhiều record ở các partition khác nhau với timestamp bằng nhau hoặc timestamp đến muộn hơn dù event xảy ra trước.

Timestamp có thể là CreateTime do producer đặt hoặc LogAppendTime do broker gán tùy cấu hình. Hai chế độ có semantics khác nhau:

- **CreateTime:** timestamp phản ánh thời gian record được tạo theo producer.
- **LogAppendTime:** broker gán timestamp khi append record vào log.

Đồng hồ giữa producer có thể lệch nhau; event có thể được gửi trễ; retry có thể làm thời điểm append khác thời điểm xảy ra nghiệp vụ. Vì vậy, không nên dùng timestamp đơn lẻ để suy ra thứ tự chính xác của event trên toàn topic.

Nếu nghiệp vụ cần phát hiện event đến sai thứ tự, có thể đưa sequence/version tăng dần theo aggregate vào payload và kiểm tra ở consumer. Timestamp hữu ích cho quan sát và xử lý event-time, còn sequence/version giúp kiểm tra thứ tự nghiệp vụ.

## 15. Transaction và ordering

Kafka transaction cho phép producer ghi nhiều record vào một transaction và commit hoặc abort nhóm ghi đó. Transaction giúp consumer dùng `read_committed` chỉ đọc các record thuộc transaction đã commit.

Transaction không tạo thứ tự toàn cục giữa các partition. Trong một transaction, các record có thể được ghi vào nhiều partition; consumer đọc từng partition theo thứ tự riêng và không có một thứ tự tổng thể giữa chúng.

Khi dùng transactional producer, cần cấu hình transaction ID prefix duy nhất giữa các instance. Nếu consumer cần chỉ nhìn thấy record đã commit, cấu hình isolation level phù hợp. Transaction giúp tính nguyên tử của một nhóm thao tác Kafka trong phạm vi được hỗ trợ; nó không thay thế key/partitioning để giữ thứ tự theo entity.

## 16. Kiểm thử ordering theo partition

Kiểm thử ordering nên tập trung vào điều hệ thống thực sự bảo đảm:

1. Gửi nhiều event cùng key vào một topic.
2. Chờ producer send hoàn tất.
3. Consumer đọc từ partition tương ứng.
4. Xác nhận thứ tự offset và sequence nghiệp vụ.
5. Kiểm tra event cùng key đi vào cùng partition trong topology đang test.
6. Gửi key khác để xác nhận có thể được phân phối sang partition khác, nhưng không giả định chính xác partition nếu không cố định partitioner/topology.
7. Kiểm tra retry và rebalance nếu các luồng này nằm trong yêu cầu.

Ví dụ event có sequence:

~~~java
public record OrderEvent(
    String orderId,
    long sequence,
    String eventType
) {}
~~~

Test có thể gửi chuỗi event:

~~~java
@Test
void eventsForSameOrderShouldBeWrittenToSamePartitionInOrder()
        throws Exception {

    kafkaTemplate.send(
        "order-events",
        "order-100",
        new OrderEvent("order-100", 1, "CREATED")
    ).get(10, TimeUnit.SECONDS);

    kafkaTemplate.send(
        "order-events",
        "order-100",
        new OrderEvent("order-100", 2, "PAID")
    ).get(10, TimeUnit.SECONDS);

    kafkaTemplate.send(
        "order-events",
        "order-100",
        new OrderEvent("order-100", 3, "SHIPPED")
    ).get(10, TimeUnit.SECONDS);

    // Consumer test đọc partition và xác nhận sequence 1, 2, 3.
}
~~~

Đây là khung minh họa; test hoàn chỉnh cần tạo topic/broker, consumer test với group riêng, cấu hình offset và chờ đủ ba record. Nên assert các record có cùng partition và sequence tăng dần theo thứ tự nhận.

Không nên viết test yêu cầu mọi key khác nhau phải rơi vào partition khác nhau. Hash có thể collision và số partition giới hạn; nhiều key vẫn có thể cùng partition.

## 17. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| Kafka bảo đảm thứ tự toàn topic. | Kafka bảo đảm thứ tự trong từng partition. |
| Offset lớn hơn ở partition này nghĩa record mới hơn partition khác. | Offset chỉ có ý nghĩa trong partition chứa nó. |
| Cùng key luôn bảo đảm thứ tự nghiệp vụ bất kể producer. | Cùng key hỗ trợ định tuyến cùng partition; nhiều producer đồng thời vẫn cần sequence/coordination nếu thứ tự nghiệp vụ quan trọng. |
| Key trong JSON tự động được dùng để partition. | Producer partitioner dùng record key, không tự đọc field trong value. |
| Tăng partition không ảnh hưởng ordering. | Ánh xạ key có thể đổi; record cũ và mới của cùng key có thể nằm ở partition khác nhau. |
| Tăng concurrency làm một partition xử lý song song an toàn. | Trong cùng group, một partition tại một thời điểm chỉ được gán cho tối đa một consumer. |
| Listener trả về ngay sau khi submit thread pool vẫn giữ thứ tự hoàn tất. | Tác vụ bất đồng bộ có thể hoàn tất sai thứ tự và commit có thể vượt xử lý. |
| Retry topic luôn giữ thứ tự gốc. | Non-blocking retry có thể để record sau được xử lý trước record lỗi. |
| Timestamp tạo ra thứ tự toàn cục. | Timestamp có thể lệch, trùng hoặc đến muộn; không thay thế partition ordering. |
| Rebalance sắp xếp lại log. | Rebalance thay đổi ownership partition; log order và offset không đổi. |

## 18. Checklist thiết kế ordering

Trước khi thiết kế topic và producer, hãy trả lời:

1. Đơn vị nghiệp vụ nào cần được xử lý tuần tự: order, account, device hay aggregate khác?
2. Record key có đại diện ổn định cho đơn vị đó không?
3. Mọi producer có dùng cùng quy tắc serialize và partition key không?
4. Số partition có đủ throughput mà vẫn phù hợp với yêu cầu ordering không?
5. Có kế hoạch tăng partition và đánh giá ánh xạ key cũ/mới không?
6. Producer có bật idempotence và cấu hình retry/in-flight phù hợp không?
7. Listener có xử lý tuần tự trong partition hay tự dispatch bất đồng bộ?
8. Retry là blocking hay non-blocking; có chấp nhận thay đổi thứ tự hoàn thành không?
9. Có sequence/version để phát hiện event đến sai thứ tự không?
10. Test có xác nhận ordering theo partition và key mà không giả định thứ tự toàn topic không?

Partition là ranh giới ordering của Kafka. Muốn giữ thứ tự cho một thực thể, producer cần định tuyến các event của thực thể đó vào cùng partition bằng key ổn định; consumer phải xử lý theo thứ tự và không làm đảo thứ tự qua thread pool, retry hoặc commit. Nhiều partition tạo khả năng song song, nhưng thứ tự giữa chúng thuộc trách nhiệm thiết kế nghiệp vụ của ứng dụng.

