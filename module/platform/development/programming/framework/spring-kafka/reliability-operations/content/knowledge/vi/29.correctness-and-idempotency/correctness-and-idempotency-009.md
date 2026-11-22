# Ordering theo partition

Apache Kafka bảo đảm thứ tự records **bên trong từng partition**. Khi broker append records vào một partition, mỗi record nhận một offset tăng dần; consumer đọc partition đó theo thứ tự offset. Nhưng Kafka không tạo một thứ tự tổng thể giữa nhiều partitions. Record ở partition 0 có thể được xử lý trước hoặc sau record ở partition 3, và kết quả phụ thuộc scheduling, assignment, tải, retry và thời gian xử lý.

Với Spring Kafka, hiểu đúng ordering theo partition là điều kiện để giữ tính đúng của các luồng như cập nhật trạng thái đơn hàng, số dư tài khoản, inventory, projection và event sourcing. Một thiết kế đúng thường chọn **business aggregate key** làm Kafka record key, để các events của cùng aggregate đi vào cùng partition. Sau đó producer phải giữ thứ tự publish, consumer phải tránh xử lý song song làm đảo thứ tự side effects, và retry/replay phải được thiết kế theo ordering contract.

Bài học thuộc chương **Tính đúng và idempotency** của **Spring Kafka Reliability Operations**. Nội dung giải thích ordering guarantee, key và partitioner, producer retries/idempotence, consumer concurrency, batch/async processing, retry topics/DLT, thay đổi partition count, per-key sequencing, idempotency và cách kiểm thử trong production-like environments.

## 1. Kafka bảo đảm thứ tự ở phạm vi nào?

Một Kafka topic được chia thành nhiều partitions. Mỗi partition là một log append-only có offset riêng.

~~~text
Topic: orders

Partition 0:  offset 0 -> A1 -> offset 1 -> A2 -> offset 2 -> A3
Partition 1:  offset 0 -> B1 -> offset 1 -> B2
Partition 2:  offset 0 -> C1 -> offset 1 -> C2
~~~

Kafka bảo đảm records trong mỗi partition được đọc theo thứ tự offset:

- Partition 0: A1 trước A2 trước A3.
- Partition 1: B1 trước B2.
- Partition 2: C1 trước C2.

Nhưng Kafka không bảo đảm quan hệ thời gian giữa A1, B1 và C1. Các partitions có thể được fetch và xử lý đồng thời.

### 1.1 Offset chỉ có ý nghĩa trong một partition

Một record được định vị bằng bộ ba:

~~~text
topic + partition + offset
~~~

Offset 15 của partition 0 không có quan hệ thứ tự với offset 15 của partition 1. Không thể so sánh hai offset để kết luận record nào xảy ra trước trên toàn topic.

Ví dụ:

| Record | Partition | Offset | Có thể kết luận |
|---|---:|---:|---|
| Order A created | 0 | 10 | Đứng trước offset 11 của partition 0 |
| Order A confirmed | 0 | 11 | Đứng sau offset 10 cùng partition |
| Order B created | 1 | 8 | Không có thứ tự toàn cục với hai record partition 0 |
| Order C created | 2 | 4 | Không có thứ tự toàn cục với các partition khác |

### 1.2 Kafka append order khác business event time

Producer có thể tạo event lúc 10:00:05 nhưng gửi sau event được tạo lúc 10:00:07. Broker append theo thứ tự nhận và xử lý produce requests, không tự sắp xếp lại theo business timestamp.

Vì vậy:

- Offset phản ánh thứ tự append trong partition.
- Event timestamp phản ánh thời điểm do producer/application gắn vào.
- Business sequence number phản ánh thứ tự nghiệp vụ nếu ứng dụng tự quản lý.
- Consumer completion time phản ánh lúc side effect hoàn tất.

Đây là bốn khái niệm khác nhau. Không dùng timestamp của record để suy ra Kafka append order hoặc business causal order nếu chưa có contract rõ.

## 2. Key quyết định ordering domain

Để events của cùng một business entity được đặt trong cùng partition, producer thường đặt **record key** bằng một identifier ổn định của entity/aggregate.

Ví dụ với orders:

~~~java
kafkaTemplate.send(
    "orders.events",
    order.getId(),
    event
);
~~~

Nếu cùng order ID được gửi với cùng key serializer, partitioner và partition count, các events thường được route về cùng partition.

~~~text
key=order-1001
  OrderCreated
  OrderPaid
  OrderPacked
  OrderShipped
        |
        v
    partition 2
        |
        v
    offsets 40, 41, 42, 43
~~~

Các events của order-1002 có thể vào partition khác và được xử lý song song.

### 2.1 Chọn key theo aggregate cần giữ thứ tự

| Use case | Key thường phù hợp | Ordering cần giữ |
|---|---|---|
| Order lifecycle | orderId | Các thay đổi của một đơn hàng |
| Account ledger | accountId | Các giao dịch của một tài khoản |
| Inventory | sku hoặc inventoryAggregateId | Cập nhật tồn kho cùng mặt hàng |
| Shipment | shipmentId | Các trạng thái của một lô giao |
| User profile | userId | Các thay đổi profile của một user |
| Device telemetry | deviceId | Events tuần tự từ một thiết bị |

Key cần đại diện cho **đơn vị cần xử lý tuần tự**. Chọn customerId khi thực tế chỉ cần thứ tự theo orderId có thể gom quá nhiều traffic vào một partition. Chọn eventId làm key thường khiến mỗi event đi vào một partition khác và không giữ được thứ tự theo aggregate.

### 2.2 Key không phải partition ID

Key là dữ liệu routing. Partitioner quyết định partition đích từ key và metadata topic. Nếu cần chỉ định partition cụ thể, ProducerRecord có thể chứa partition number, nhưng hardcode partition ID thường làm ứng dụng phụ thuộc topology và khó scale.

### 2.3 Null key không tạo per-entity ordering

Nếu record không có key, partitioner có thể phân phối records theo sticky/round-robin behavior tùy Kafka client version và configuration. Không có đảm bảo các records của cùng business entity sẽ vào một partition.

Nếu ordering là yêu cầu nghiệp vụ, hãy cung cấp key ổn định và test partition routing.

## 3. Default partitioner và cùng key

Với keyed records, default Kafka partitioning thường dùng hash của serialized key để chọn partition. Khái niệm đơn giản:

~~~text
partition = positiveHash(serializedKey) % partitionCount
~~~

Đây là mô tả khái quát; implementation cụ thể phụ thuộc Kafka client version và partitioner configuration.

Nếu cùng key, cùng partitioner và cùng số partitions, kết quả routing ổn định trong điều kiện thông thường. Vì thế các events của một aggregate có thể được append vào cùng partition.

### 3.1 Key serialization phải ổn định

Nếu key serializer tạo byte sequence khác nhau cho cùng một logical ID, hash cũng có thể khác. Ví dụ:

~~~text
"order-1001"
"ORDER-1001"
"order-1001 "
~~~

Đây là ba giá trị key khác nhau nếu serializer giữ nguyên các bytes đó.

Nên chuẩn hóa key theo contract:

- Cùng format và charset.
- Không thay đổi casing ngoài chủ đích.
- Không thêm whitespace.
- Không dùng object serialization không ổn định.
- Không đổi serializer giữa các producer mà không migration.
- Không để một producer dùng orderId còn producer khác dùng customerId cho cùng stream nếu ordering contract yêu cầu orderId.

### 3.2 Custom partitioner có thể phá routing assumption

Một custom Partitioner có thể route cùng key sang partition khác dựa trên tenant, region, time hoặc metadata. Khi dùng custom partitioner, phải kiểm tra:

- Cùng key có luôn về cùng partition không?
- Mapping có thay đổi khi deploy version mới không?
- Có fallback khi key null không?
- Partition count tăng có làm mapping đổi không?
- Nhiều producer có dùng cùng thuật toán và configuration không?

Ordering theo key chỉ có ý nghĩa khi routing policy nhất quán giữa tất cả producers.

## 4. Producer gửi records theo đúng thứ tự

Ngay cả khi cùng key route vào cùng partition, producer application vẫn cần bảo đảm thứ tự gửi.

Ví dụ:

~~~java
kafkaTemplate.send("orders.events", orderId, createdEvent);
kafkaTemplate.send("orders.events", orderId, paidEvent);
kafkaTemplate.send("orders.events", orderId, shippedEvent);
~~~

Các calls trên khởi tạo sends theo thứ tự trong code, nhưng send là asynchronous. Cần hiểu producer batching, in-flight requests, retries và nhiều threads để đảm bảo thứ tự broker append.

### 4.1 Producer retries và in-flight requests

Kafka producer có thể có nhiều requests in-flight cùng lúc. Nếu request trước fail và retry trong khi request sau thành công, ordering có thể bị ảnh hưởng khi idempotence không được bật hoặc cấu hình không đáp ứng điều kiện ordering.

Với Kafka producer hiện đại, **enable.idempotence** được hỗ trợ để chống duplicate do retry và giữ ordering trong các điều kiện cấu hình tương thích. Khi bật idempotence, max.in.flight.requests.per.connection được giới hạn theo Kafka version; ở các client hiện đại, giá trị tới 5 được hỗ trợ mà vẫn giữ ordering với idempotence.

Cấu hình explicit minh họa:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        retries: 2147483647
~~~

Đây là ví dụ policy cho Kafka clients hỗ trợ các thiết lập này. Spring Boot property binding và Kafka client version phải tương thích. Producer idempotence có thể yêu cầu acks=all, retries lớn hơn 0 và max.in.flight nằm trong giới hạn cho phép.

### 4.2 Idempotence không thay thế business ordering

Idempotent producer bảo vệ producer sequence trong protocol Kafka, tránh duplicate writes do retries theo semantics của producer. Nó không biết OrderCreated phải xảy ra trước OrderPaid ở business layer.

Nếu hai application threads gọi send cùng key nhưng thread B gửi trước thread A do race, producer có thể append đúng thứ tự requests nó nhận được, dù thứ tự nghiệp vụ mong muốn ngược lại.

### 4.3 Nhiều producer cùng ghi một key

Giả sử service A và service B cùng publish events cho order-1001. Mỗi producer giữ ordering nội bộ của nó, nhưng broker không có một business sequence coordinator tự động giữa hai producer.

~~~text
Producer A: OrderAddressChanged
Producer B: OrderCancelled
        \       /
         \     /
       same key / partition
             |
             v
        broker append order
~~~

Broker tạo một thứ tự append, nhưng thứ tự đó không nhất thiết trùng business causality giữa hai producers.

Nếu cùng aggregate có nhiều writers, cần một owner/sequencer hoặc versioning strategy. Chỉ dùng cùng key chưa đủ để định nghĩa thứ tự nghiệp vụ giữa nhiều producer processes.

## 5. Serializing sends cho cùng aggregate

Khi một service có nhiều threads, các events của cùng aggregate có thể được tạo đồng thời. Có thể dùng một trong các cách:

- Một aggregate owner xử lý commands tuần tự.
- Partitioned executor theo aggregate key.
- Outbox relay sắp xếp theo aggregate sequence.
- Optimistic concurrency/version check ở database.
- Một sequencer cấp sequence numbers.

Không nên dùng một synchronized block toàn application nếu điều đó serialize tất cả aggregates và làm mất throughput. Mục tiêu là **serialize theo key**, vẫn cho phép các keys khác nhau chạy song song.

### 5.1 Sequence number nghiệp vụ

Một event có thể chứa aggregateVersion:

~~~json
{
  "orderId": "order-1001",
  "aggregateVersion": 42,
  "eventType": "OrderPaid"
}
~~~

Consumer có thể xác nhận version tiếp theo là 42 sau version 41. Nếu nhận version 43 trước 42, consumer có thể buffer, retry, reject hoặc reconcile theo policy.

Sequence number giúp phát hiện gaps/reordering; nó không tự ngăn broker append sai thứ tự.

### 5.2 Sequence cấp ở đâu?

Sequence phải được cấp tại nơi có quyền quyết định thứ tự aggregate. Nếu hai producers tự tăng một local counter độc lập, chúng có thể tạo trùng hoặc đảo version.

Một cách phổ biến là lưu aggregate version trong cùng database transaction cập nhật state và ghi outbox event. Khi transaction commit, event mang version mới. Outbox relay phải publish theo aggregate order.

## 6. Partition count ảnh hưởng key mapping

Một chi tiết vận hành dễ bị bỏ qua: với hash partitioning, tăng số partitions có thể làm cùng một key được route sang partition khác.

Ví dụ minh họa:

~~~text
Trước:
  partitionCount = 4
  key order-1001 -> partition 2

Sau khi tăng:
  partitionCount = 8
  key order-1001 -> partition 6
~~~

Record cũ của order-1001 vẫn nằm ở partition 2. Record mới có thể được append vào partition 6. Hai partitions có thể được consumer xử lý đồng thời.

Khi đó, event mới có thể hoàn tất trước event cũ còn backlog. Kafka vẫn giữ thứ tự trong từng partition, nhưng ordering theo orderId đã bị chia đôi.

### 6.1 Tăng partitions là thay đổi ordering contract

Trước khi tăng partition count của topic keyed theo aggregate:

1. Xác định ordering domain và key distribution.
2. Xác định backlog hiện tại theo partition.
3. Đánh giá producer partitioner và key hash mapping.
4. Đánh giá khả năng một key chuyển partition.
5. Xác định consumer side effects có thể chồng lấn giữa old/new partition không.
6. Chọn migration strategy.
7. Chỉ tăng partitions sau khi đã chấp nhận semantics và có test.

Không xem tăng partitions là một thay đổi capacity hoàn toàn không ảnh hưởng correctness.

### 6.2 Các chiến lược giảm rủi ro

- Giữ partition count cố định nếu strict per-key order là yêu cầu cao.
- Dùng logical shard/virtual partition mapping ổn định do application quản lý.
- Chuyển sang topic version mới và thực hiện migration/drain có kiểm soát.
- Pause/drain old stream trước khi bắt đầu routing mới, nếu SLA cho phép.
- Dùng aggregate sequence/version để phát hiện và xử lý gaps.
- Xây routing layer có epoch để consumer biết mapping nào đang hiệu lực.

Mỗi chiến lược có chi phí và operational complexity. Không có thao tác tăng partition đơn giản nào tự di chuyển lịch sử và tái lập thứ tự theo key.

## 7. Consumer group và ordering

Trong một consumer group, một partition tại một thời điểm được assign cho tối đa một consumer member. Consumer xử lý records của partition theo offset order.

~~~text
Topic orders, 6 partitions
        |
        v
Consumer group orders-projection
  consumer-0 -> partitions 0, 3
  consumer-1 -> partitions 1, 4
  consumer-2 -> partitions 2, 5
~~~

Các consumer members xử lý partitions song song. Bên trong mỗi partition, consumer giữ thứ tự record delivery theo offset. Không có global order giữa consumer-0 và consumer-1.

### 7.1 Concurrency của Spring Kafka

Ví dụ:

~~~java
factory.setConcurrency(3);
~~~

Nếu topic có 6 partitions, ba child consumers có thể nhận khoảng hai partitions mỗi consumer tùy assignor. Nếu concurrency lớn hơn partition count, một số consumers có thể idle.

Concurrency tăng throughput bằng cách xử lý nhiều partitions song song. Nó không tăng số thứ tự độc lập bên trong một partition.

### 7.2 Một partition không được xử lý đồng thời bởi hai members cùng group

Kafka group assignment bảo đảm một partition được gán cho một consumer member trong group tại một thời điểm. Tuy nhiên, ứng dụng vẫn có thể tự tạo parallelism bên trong member bằng executor hoặc async processing. Đó là nơi thứ tự side effects có thể bị đảo.

### 7.3 Hai consumer groups độc lập

Nếu hai groups cùng subscribe topic, mỗi group đọc toàn bộ partitions theo offset order của riêng mình. Nhưng thời điểm hoàn tất giữa hai groups không được đồng bộ.

Không dùng consumer group A và B để tạo một thứ tự global giữa hai processing pipelines. Nếu downstream cần phối hợp, cần explicit coordination hoặc sequence/version checks.

## 8. Async processing có thể làm đảo thứ tự

Một listener đồng bộ:

~~~java
@KafkaListener(topics = "orders.events")
public void handle(OrderEvent event) {
    orderService.apply(event);
}
~~~

Container gọi listener cho record và chờ method hoàn tất theo processing model. Với record của cùng partition, đây là cách đơn giản để giữ thứ tự side effects.

Nhưng nếu listener offload công việc:

~~~java
@KafkaListener(topics = "orders.events")
public void handle(OrderEvent event) {
    executor.submit(() -> orderService.apply(event));
}
~~~

method có thể return ngay. Task cho offset 41 và 42 chạy đồng thời; task 42 có thể commit database trước task 41. Kafka delivery order không đồng nghĩa business completion order.

### 8.1 Ví dụ đảo thứ tự

~~~text
Kafka delivery:
  offset 41 -> OrderAddressChanged
  offset 42 -> OrderShipped

Async execution:
  task 41: DB call chậm 800 ms
  task 42: DB call nhanh 100 ms

Completion:
  offset 42 side effect finishes first
  offset 41 side effect finishes later
~~~

Kết quả cuối có thể ghi address update sau khi trạng thái đã shipped, hoặc ghi state cũ đè state mới.

### 8.2 Cách giữ per-key order với async work

- Dùng executor có serial queue theo aggregate key.
- Dùng keyed mailbox/actor model: một key có một task active.
- Dùng partition-aligned worker với tuần tự processing.
- Đặt optimistic version check ở database.
- Không acknowledge/commit trước khi business task hoàn tất theo contract.
- Giới hạn queue để tránh memory growth.

Không dùng một executor single-thread toàn application nếu cần throughput cao trên nhiều partitions. Serial hóa theo partition hoặc aggregate key thường giữ được parallelism giữa các keys khác nhau.

### 8.3 KafkaConsumer không thread-safe

Không chuyển KafkaConsumer object sang executor threads để tự poll, commit, seek hoặc pause. Spring Kafka container quản lý consumer thread và lifecycle. Async business processing phải dùng các API/acknowledgment patterns được framework hỗ trợ.

## 9. Batch listener và ordering

Một batch listener có thể nhận records từ nhiều partitions trong một poll. Batch order tổng thể không tạo ra global ordering giữa partitions.

Ví dụ batch:

~~~text
Partition 0: offset 10, 11
Partition 1: offset 20, 21
Partition 2: offset 30
~~~

Batch có thể chứa records được fetch từ nhiều partitions. Trong mỗi partition, thứ tự offset vẫn quan trọng; giữa partition 0 và 1 không có thứ tự tổng thể.

### 9.1 Dùng ConsumerRecord để giữ metadata

~~~java
@KafkaListener(topics = "orders.events")
public void handleBatch(
        List<ConsumerRecord<String, OrderEvent>> records) {

    Map<TopicPartition, List<ConsumerRecord<String, OrderEvent>>> byPartition =
        records.stream().collect(
            Collectors.groupingBy(
                record -> new TopicPartition(
                    record.topic(),
                    record.partition()
                )
            )
        );

    byPartition.values().forEach(partitionRecords ->
        partitionRecords.sort(
            Comparator.comparingLong(ConsumerRecord::offset)
        )
    );

    // Xử lý tuần tự trong từng partition theo offset.
}
~~~

Ví dụ minh họa grouping/sorting. Kafka đã cung cấp records theo fetch order trong từng partition; grouping giúp thể hiện rõ ordering domain khi business batch logic xử lý nhiều partitions. Cần giữ semantics acknowledgment và exception của batch listener.

### 9.2 Parallelize giữa partitions, không giữa records cùng partition

Một batch có thể được chia thành các nhóm partition. Các nhóm khác nhau có thể xử lý song song nếu business effects độc lập; trong mỗi nhóm cần xử lý tuần tự theo offset.

Tuy nhiên, nếu database hoặc downstream có shared state giữa các keys/partitions, cần thêm concurrency control. Partition boundary không tự đảm bảo business entities khác nhau hoàn toàn độc lập.

### 9.3 Batch retry có thể xử lý lại nhiều records

Batch listener exception có thể khiến framework redeliver/recover một batch hoặc phần records theo error handler semantics và version. Không giả định chỉ record cuối cùng được retry.

Nếu một batch có nhiều aggregate keys, một lỗi có thể làm nhiều records được xử lý lại. Business operations cần idempotent và batch retry behavior phải được test.

## 10. Blocking retry giữ thứ tự nhưng có thể chặn partition

Với DefaultErrorHandler và blocking retry, record lỗi có thể được seek/redeliver sau BackOff. Consumer chưa thể tiến bình thường qua record lỗi cho tới khi xử lý/recovery theo policy.

~~~text
Partition 0:
  offset 100 -> success
  offset 101 -> failure, retry
  offset 102 -> chờ phía sau
  offset 103 -> chờ phía sau
~~~

Đây là trade-off: giữ ordering trong partition bằng cách không để records sau vượt qua record lỗi, nhưng một poison record có thể làm partition progress chậm.

### 10.1 Head-of-line blocking

Nếu offset 101 retry trong 30 giây, offset 102 và 103 có thể phải chờ. Consumer lag của partition tăng dù các records sau có thể xử lý nhanh.

Để giảm impact:

- Phân loại non-retryable exceptions.
- BackOff hữu hạn.
- DLT/recovery cho poison records.
- Tách workload có SLA khác nhau thành topics/partitions phù hợp.
- Theo dõi lag per partition và retry duration.

Không bypass record lỗi nếu business ordering bắt buộc offset sau không được vượt qua.

### 10.2 Recovery và offset progression

Khi record được recover sang DLT, container có thể tiếp tục tiến theo error handler/acknowledgment semantics. Điều đó có nghĩa record đã được quarantine, không phải business effect thành công.

Nếu cần replay sau khi sửa dữ liệu, phải xác định cách replay để không gây out-of-order side effects cho các events mới hơn đã được xử lý.

## 11. Non-blocking retry có thể làm đảo thứ tự

Với @RetryableTopic, failed record được route sang retry topic và main topic có thể tiếp tục xử lý records sau.

~~~text
Main topic:
  offset 100 -> OrderCreated -> success
  offset 101 -> OrderPaid -> failure, routed to retry
  offset 102 -> OrderShipped -> success

Retry topic later:
  OrderPaid -> success
~~~

Trong ví dụ, OrderShipped có thể được xử lý trước OrderPaid. Đây là hành vi có chủ đích của non-blocking retries, nhưng có thể phá strict ordering theo aggregate.

### 11.1 Khi nào retry topics phù hợp?

Non-blocking retry hữu ích khi:

- Các records độc lập hoặc eventual ordering chấp nhận được.
- Một record lỗi không nên block toàn partition.
- Downstream outage cần delay dài.
- Business logic có version checks/idempotency để chịu reordering.
- Retry topics được thiết kế cùng retention, partitioning và ACL.

Không dùng @RetryableTopic một cách máy móc cho event streams yêu cầu strict per-key sequencing.

### 11.2 Các cách giữ correctness khi dùng retry topics

- Mỗi event mang aggregate sequence/version.
- Consumer từ chối hoặc buffer event có version vượt quá version mong đợi.
- Side effects idempotent.
- Retry handler không ghi state mới hơn trước state cũ.
- Reconciliation job xử lý gaps.
- DLT/replay workflow giữ source metadata.

Nếu cần strict order tuyệt đối, blocking retry hoặc một sequencing layer có thể phù hợp hơn.

## 12. DLT và replay có thể tạo reordering

Khi record cũ được đưa vào DLT, các records mới hơn có thể tiếp tục được xử lý. Khi replay DLT sau nhiều giờ, event cũ có thể đến sau state mới.

Ví dụ:

~~~text
10:00 OrderAddressChanged v12 -> DLT
10:01 OrderShipped v13 -> main consumer success
11:00 Replay v12 -> consumer sees stale event
~~~

Nếu consumer áp dụng v12 sau v13 mà không kiểm tra version, state có thể bị lùi.

### 12.1 Replay cần ordering policy

Trước khi replay:

1. Xác định aggregate key và sequence/version của record.
2. Xác định state hiện tại của aggregate.
3. Kiểm tra event đã được áp dụng chưa.
4. Quyết định skip, reconcile, replay theo thứ tự hoặc rebuild projection.
5. Đảm bảo replay không vượt qua các events mới hơn một cách nguy hiểm.
6. Ghi audit trail về replay operation.

DLT replay không chỉ là đưa record trở lại main topic. Nó là một thao tác thay đổi lịch sử xử lý, cần idempotency và sequencing.

### 12.2 Không xóa metadata gốc khi chuyển DLT

Giữ source topic, partition, offset, timestamp và exception headers theo policy để điều tra. Các metadata này giúp truy nguyên vị trí ban đầu, dù DLT topic có offset mới riêng.

## 13. Consumer rebalance và ownership chuyển partition

Khi consumer group rebalance, partition có thể được revoke từ consumer cũ và assign cho consumer mới.

~~~text
Before:
  consumer-0 owns partition 0

Rebalance:
  partition 0 revoked from consumer-0

After:
  consumer-1 owns partition 0
~~~

Kafka bảo đảm group assignment ownership theo generation/epoch semantics. Nhưng nếu consumer cũ đã offload business tasks sang executor, những tasks đó có thể vẫn chạy sau khi partition được assign cho consumer mới.

Khi đó hai tasks cho cùng key có thể chồng lấn dù Kafka chỉ assign partition cho một consumer member tại một thời điểm.

### 13.1 Graceful shutdown và in-flight work

Khi revoke/stop:

- Ngừng nhận work mới cho partition.
- Drain hoặc cancel tasks theo policy.
- Chờ business tasks hoàn tất trong giới hạn thời gian.
- Không commit offset trước khi side effect hoàn tất.
- Đảm bảo task cũ không ghi đè state mới từ consumer mới.
- Sử dụng fencing/version checks nếu có thể.

Nếu không thể drain trong thời gian giới hạn, database optimistic locking và aggregate sequence checks giúp ngăn stale writes.

### 13.2 Cooperative rebalancing không phải bảo đảm business order end-to-end

Cooperative sticky assignment giảm phạm vi partitions bị revoke trong rebalance, nhưng không tự giải quyết async tasks, retries hoặc side effects đã chạy ngoài consumer thread.

## 14. Key skew và hot partitions

Key-based partitioning giữ ordering theo key nhưng có thể tạo hot partition nếu một key hoặc một nhóm keys chiếm phần lớn traffic.

Ví dụ:

~~~text
partition 0: 90,000 records/s
partition 1:  3,000 records/s
partition 2:  3,500 records/s
partition 3:  3,500 records/s
~~~

Nếu một tenant hoặc account có lượng events cực lớn, tất cả events của key đó phải đi qua một partition để giữ thứ tự. Không thể chia cùng một strict ordering domain ra nhiều partitions mà không thêm sequencing mechanism.

### 14.1 Đo skew

Theo dõi:

- Records in/out per partition.
- Bytes in/out per partition.
- Consumer lag per partition.
- Processing duration per key/category nếu có aggregation an toàn.
- Retry rate và DLT rate per partition.
- Partition assignment distribution.

Không đưa raw key vào metrics tags. Có thể dùng key class/tenant tier hoặc top-key analysis offline có kiểm soát dữ liệu.

### 14.2 Khi hot key không thể scale ngang

Các lựa chọn:

- Tối ưu business work cho key đó.
- Tách aggregate thành sub-aggregates nếu nghiệp vụ cho phép.
- Dùng per-subkey ordering nếu invariant cho phép.
- Giảm event chatter/coalesce updates.
- Tăng capacity của consumer cho partition và downstream.
- Thiết kế sequencer/reorder buffer nếu cần phân tán một key.

Không tăng partition count rồi hy vọng hot key tự chia đều; cùng key vẫn được route vào một partition.

## 15. Ordering toàn cục cần kiến trúc riêng

Nếu business yêu cầu mọi events của toàn bộ hệ thống có một thứ tự duy nhất, nhiều partitions không thể tự cung cấp guarantee đó.

Một topic một partition có thể tạo một log order toàn cục cho topic, nhưng throughput và parallelism bị giới hạn. Một consumer group chỉ có một consumer active cho partition đó tại một thời điểm.

Các lựa chọn khác:

- Central sequencer cấp global sequence.
- Single-writer log/service.
- Database transaction log/outbox với sequence.
- Event time + watermark/reorder buffer cho use cases chấp nhận bounded delay.
- Explicit causal dependencies giữa aggregates.

### 15.1 Global order có chi phí

Một global sequence yêu cầu coordination. Nếu mọi service phải chờ cùng một sequencer, throughput, availability và latency phụ thuộc thành phần đó.

Phần lớn business domains chỉ cần ordering theo aggregate, ví dụ từng order hoặc từng account, chứ không cần thứ tự giữa mọi orders trong hệ thống.

## 16. Idempotency và ordering bổ trợ nhau

Ordering bảo đảm event đến theo trình tự trong một partition. Idempotency bảo đảm xử lý lại một event không tạo side effect trùng. Cần cả hai trong at-least-once systems.

Ví dụ:

~~~text
OrderCreated v1
OrderPaid v2
OrderShipped v3
~~~

Consumer xử lý v1 và v2, sau đó crash trước khi offset commit. Khi restart, v2 có thể được giao lại. Nếu không idempotent, consumer có thể trừ tiền hoặc ghi side effect hai lần.

### 16.1 Inbox table

Một consumer có thể lưu event ID đã xử lý trong cùng database transaction với business state:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Pseudo flow:

~~~text
BEGIN DB TRANSACTION
  INSERT event_id into processed_events
  if duplicate:
      skip business side effect
  else:
      apply state transition
COMMIT
ACK/commit Kafka offset according to listener policy
~~~

Cần xử lý duplicate key conflict một cách an toàn và giữ idempotency record cùng transaction với side effect. Nếu insert inbox và update business state ở hai transaction khác nhau, crash có thể tạo trạng thái không nhất quán.

### 16.2 Version guard

Với aggregateVersion:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version = :incomingVersion - 1;
~~~

Nếu update không ảnh hưởng row nào, event có thể là duplicate, stale hoặc gap. Ứng dụng cần phân biệt ba trường hợp và quyết định retry/reconcile/skip.

Version guard ngăn stale event ghi đè state mới hơn; nó không tự bảo đảm event được xử lý đúng thứ tự nếu business logic không có recovery path cho gaps.

### 16.3 Exactly-once Kafka không bao trùm mọi database side effect

Kafka transactions có thể atomically commit consumed offsets và produced Kafka records trong transaction boundary được cấu hình đúng. Chúng không tự atomically commit một PostgreSQL transaction thông thường cùng Kafka transaction.

Nếu consumer ghi DB, cần idempotency/inbox/outbox hoặc transaction coordination phù hợp. Không suy luận EOS nghĩa là mọi external side effect exactly once.

## 17. Transactional outbox và per-aggregate order

Transactional outbox thường dùng khi service cập nhật database và cần publish Kafka event nhất quán:

~~~text
DB transaction:
  update orders
  insert outbox event with aggregate_id + aggregate_version
COMMIT

Outbox relay:
  read unpublished rows
  publish to Kafka with key=aggregate_id
  mark published
~~~

Cùng aggregate key giúp các events đi vào cùng Kafka partition. Nhưng relay vẫn phải đọc/publish theo aggregate sequence.

### 17.1 Nhiều relay workers

Nếu nhiều relay workers claim outbox rows song song, worker A có thể publish version 11 chậm trong khi worker B publish version 12 trước. Cùng key không sửa được thứ tự producer sends đã bị đảo trước khi đến broker.

Cần:

- Claim rows theo aggregate với locking/partitioning.
- Chỉ cho một worker active trên aggregate/shard.
- Publish sequence tăng dần.
- Không đánh dấu published trước khi broker acknowledgment theo policy.
- Có idempotent relay khi crash sau publish nhưng trước mark.
- Kiểm tra duplicates và version gaps ở consumer.

### 17.2 Outbox key và Kafka key phải thống nhất

Nếu outbox aggregate_id là orderId nhưng relay publish bằng customerId, ordering domain sẽ thay đổi. Contract cần thống nhất giữa database, event schema, producer và consumer.

## 18. Spring Kafka configuration mẫu

Một cấu hình consumer record listener có concurrency phù hợp:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            CommonErrorHandler ordersErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(4);
        factory.setCommonErrorHandler(ordersErrorHandler);

        factory.getContainerProperties()
               .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Producer:

~~~java
@Bean
KafkaTemplate<String, OrderEvent> ordersKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    return new KafkaTemplate<>(producerFactory);
}
~~~

Publish theo aggregate key:

~~~java
public CompletableFuture<SendResult<String, OrderEvent>> publish(
        OrderEvent event) {

    return kafkaTemplate.send(
        "orders.events",
        event.orderId(),
        event
    );
}
~~~

Các API return types có thể khác theo Spring Kafka version. Mẫu này minh họa key-based routing; producer properties như idempotence/acks/retries cần được cấu hình và xác nhận riêng.

### 18.1 Concurrency không tạo thứ tự giữa partitions

Concurrency=4 cho phép xử lý tối đa nhiều partitions song song nếu topic có đủ partitions. Nếu mọi events của cùng orderId luôn cùng partition và listener synchronous, các records đó được xử lý tuần tự trong partition.

Nếu listener offload task async, concurrency=4 không bảo vệ side effect order bên trong partition. Cần xử lý như phần async processing.

## 19. Producer send order và future completion

KafkaTemplate.send trả về future. Nếu application gửi nhiều events và không chờ kết quả, cần hiểu thứ tự gửi và failure handling.

~~~java
CompletableFuture<SendResult<String, OrderEvent>> first =
    kafkaTemplate.send("orders.events", orderId, created);

CompletableFuture<SendResult<String, OrderEvent>> second =
    kafkaTemplate.send("orders.events", orderId, paid);
~~~

Gọi send theo thứ tự tạo ra thứ tự invocation ở thread đó. Tuy nhiên, nhiều threads có thể interleave calls; futures hoàn thành ở thời điểm khác nhau; completion callback không phải broker append order.

Nếu business cần bảo đảm OrderCreated được publish trước OrderPaid, phải serialize command/event creation cho aggregate và kiểm soát send failures trước khi phát event phụ thuộc.

### 19.1 Không chờ future theo cách block mọi key

Có thể chain sends cho cùng aggregate:

~~~java
kafkaTemplate.send("orders.events", orderId, created)
    .thenCompose(result ->
        kafkaTemplate.send("orders.events", orderId, paid)
    );
~~~

Đây là ví dụ sequencing trong một flow; cần xử lý exception và tránh tạo một chain không bounded. Không cần serialize sends của những order IDs khác nhau nếu chúng độc lập.

## 20. Tái phân vùng và migration topic

Khi partition count cần tăng, một cách migration có thể là tạo topic mới với topology mới:

~~~text
orders.v1 (4 partitions)
        |
        v
drain / snapshot / migration
        |
        v
orders.v2 (8 partitions)
        |
        v
new producers and consumers
~~~

Một migration an toàn cần định nghĩa cutover boundary để không có cùng aggregate phát song song vào hai topic với hai mapping khác nhau.

### 20.1 Các câu hỏi cần trả lời

- Ai là owner của producer cutover?
- Làm sao biết mọi events trước cutover đã được drain?
- Consumer mới bắt đầu từ đâu?
- Aggregate version tiếp tục tăng như thế nào?
- Có duplicate giữa v1 và v2 không?
- Consumer side effects được deduplicate ra sao?
- DLT records cũ replay vào topic nào?
- Rollback producer routing có làm đảo sequence không?

Không có một lệnh Kafka nào tự migration ordering contract khi partition count thay đổi.

## 21. Monitoring ordering và correctness

Kafka metrics thông thường đo throughput, lag và latency; chúng không tự chứng minh business events đúng thứ tự.

Có thể instrument thêm:

| Metric/log | Mục đích |
|---|---|
| consumer_lag per partition | Phát hiện partition backlog |
| records_processed_total per listener | Throughput |
| retry_attempts_total | Retry behavior |
| dlt_records_total | Quarantine volume |
| aggregate_version_gap_total | Event version gap |
| stale_event_rejected_total | Event cũ bị chặn |
| duplicate_event_total | Duplicate detected |
| processing_completion_duration | Business completion time |
| rebalance_total | Ownership changes |

Không dùng aggregate ID, event ID hoặc offset làm Prometheus tags. Hãy aggregate theo listener, topic, error category và các dimensions có cardinality thấp.

### 21.1 Detect out-of-order bằng sequence

Nếu event có aggregateVersion, consumer có thể phát hiện:

~~~text
current version = 12
incoming version = 14
expected version = 13
~~~

Đây là gap. Có thể event 13 đang retry, producer đã publish sai thứ tự, hoặc consumer đã bỏ qua event. Không tự động skip version 14 nếu business invariant yêu cầu đầy đủ transitions.

### 21.2 Dashboard theo partition

Một dashboard hữu ích hiển thị:

- Lag theo từng partition.
- Records consumed rate.
- Processing duration.
- Retry/DLT counts.
- Assignment/consumer members.
- Hot partition/skew.
- Business sequence gap và stale event counts.

Aggregate lag toàn topic có thể che một partition nóng đang block toàn bộ events của một aggregate.

## 22. Integration tests cho ordering

Ordering cần được test qua Kafka broker thật hoặc Testcontainers/Embedded Kafka tương ứng, không chỉ mock KafkaTemplate.

### 22.1 Cùng key phải vào cùng partition

1. Tạo topic có nhiều partitions.
2. Gửi nhiều events với cùng aggregate key.
3. Dùng ProducerRecord hoặc SendResult metadata để đọc partition.
4. Xác nhận mọi events của key nằm cùng partition trong cùng topology.
5. Xác nhận offset tăng theo publish order.
6. Gửi thêm keys khác và xác nhận có thể phân phối qua nhiều partitions.

Không assert key nào phải vào partition số cụ thể nếu test không cố định partitioner/hash implementation.

### 22.2 Consumer xử lý tuần tự trong partition

1. Gửi events cùng key với sequence 1..N.
2. Listener ghi nhận sequence theo thứ tự hoàn tất business processing.
3. Xác nhận kết quả 1..N.
4. Bật concurrency lớn hơn 1 để chứng minh các partitions khác có thể xử lý song song.
5. Không offload async trong test baseline.

### 22.3 Test async reorder

1. Listener offload records sang executor.
2. Làm event đầu xử lý chậm hơn event sau.
3. Quan sát completion order.
4. Xác nhận test có thể tái hiện reorder.
5. Thêm per-key serial executor/version guard.
6. Chạy lại và xác nhận invariant được giữ.

### 22.4 Test producer retry/idempotence

- Tạo tình huống broker/network retry có kiểm soát nếu test environment hỗ trợ.
- Gửi nhiều records cùng key.
- Kiểm tra ordering và duplicates.
- Xác nhận producer properties tương thích idempotence.
- Không dùng một mock future để kết luận broker append order.

### 22.5 Test blocking retry

- Gửi sequence 1, 2, 3 cùng key.
- Làm sequence 2 fail tạm thời.
- Xác nhận sequence 3 không hoàn tất trước 2 nếu policy yêu cầu strict partition order.
- Cho sequence 2 thành công hoặc recover.
- Xác nhận offset progression.

### 22.6 Test non-blocking retry

- Gửi sequence 1, 2, 3 cùng key.
- Làm sequence 2 route sang retry topic.
- Xác nhận main topic có thể xử lý sequence 3 trước.
- Xác nhận version guard/buffer/reconciliation giữ business correctness.
- Test retry event được replay sau sequence mới hơn.

### 22.7 Test partition expansion

- Tạo topic ban đầu có partition count nhỏ.
- Gửi events của cùng key.
- Tăng partition count.
- Gửi events mới cùng key.
- Kiểm tra mapping có thể thay đổi.
- Xác nhận migration/version policy ngăn stale side effects.

### 22.8 Test rebalance và in-flight work

- Dùng listener async hoặc executor.
- Trigger consumer rebalance/stop.
- Kiểm tra task cũ có còn chạy khi partition được assign cho consumer mới không.
- Xác nhận drain/cancel/version guard.
- Kiểm tra không commit offset trước completion theo policy.

## 23. Runbook khi phát hiện out-of-order events

1. Xác định aggregate key và event sequence/version.
2. Thu source topic/partition/offset cho từng event.
3. So sánh Kafka offset order trong mỗi partition.
4. Xác nhận các events có cùng partition không.
5. Kiểm tra producer partitioner, key serializer và partition count tại thời điểm publish.
6. Kiểm tra producer threads, multiple producers và send futures.
7. Kiểm tra consumer concurrency và partition assignment.
8. Kiểm tra listener async/executor completion order.
9. Kiểm tra blocking retry, @RetryableTopic và DLT replay.
10. Kiểm tra rebalance/in-flight tasks.
11. Xác định event nào đã ghi side effect vào database.
12. Dùng aggregate version/inbox state để đánh giá stale, duplicate và gaps.
13. Chặn stale writes hoặc pause flow theo incident policy.
14. Reconcile/replay theo sequence order.
15. Ghi lại partition topology và producer/consumer versions.
16. Bổ sung test tái hiện nguyên nhân trước khi mở lại rollout.

Không reset toàn bộ consumer offsets để sửa một lỗi ordering nếu chưa biết tác động. Reset có thể replay lượng lớn records và tạo thêm duplicates/out-of-order effects.

## 24. Những hiểu nhầm thường gặp

**“Kafka giữ thứ tự toàn topic.”** Sai. Guarantee mặc định là trong từng partition.

**“Cùng key luôn có cùng partition mãi mãi.”** Không nếu partition count hoặc partitioner mapping thay đổi.

**“Producer gọi send theo thứ tự nghĩa là business events chắc chắn được append đúng thứ tự.”** Chỉ trong điều kiện producer flow, concurrency và retries phù hợp; nhiều writers có thể race.

**“Idempotent producer đảm bảo business event order.”** Không. Nó bảo vệ producer retry/duplicate semantics, không cấp sequence nghiệp vụ.

**“Concurrency lớn hơn 1 làm đảo thứ tự trong cùng partition.”** Không tự động nếu container xử lý tuần tự; async offloading hoặc custom parallelism mới có thể làm đảo side effects.

**“Batch listener có một thứ tự tổng thể giữa mọi records.”** Không. Batch có thể chứa nhiều partitions; chỉ ordering trong mỗi partition có ý nghĩa.

**“Retry topic luôn giữ strict per-key order.”** Không. Non-blocking retry có thể để record mới hơn được xử lý trước record đang retry.

**“DLT replay chỉ là gửi lại record cũ.”** Không. Replay có thể đưa event stale tới sau state mới; cần sequence/idempotency policy.

**“Consumer rebalance bảo đảm mọi async task cũ đã kết thúc.”** Không. App phải quản lý in-flight work.

**“Exactly-once giải quyết mọi duplicate và ordering.”** Không. Kafka transaction có phạm vi riêng; external DB side effects cần idempotency/coordination.

**“Tăng partitions chỉ tăng throughput.”** Không. Nó có thể đổi key-to-partition mapping và ảnh hưởng per-key order.

**“Offset lớn hơn ở partition khác nghĩa là event mới hơn.”** Không. Offsets chỉ so sánh trong cùng partition.

## 25. Checklist thiết kế ordering

**Producer**

- [ ] Xác định aggregate/key cần giữ thứ tự.
- [ ] Tất cả producers dùng cùng key contract và serializer.
- [ ] Key không null cho records cần per-entity ordering.
- [ ] Partitioner mapping ổn định và được test.
- [ ] enable.idempotence và producer retry settings phù hợp.
- [ ] Multiple producer writers có sequencer/version strategy.
- [ ] Outbox relay publish theo aggregate sequence.
- [ ] Partition count change có migration plan.

**Consumer**

- [ ] Một partition có processing flow tuần tự theo thiết kế.
- [ ] Concurrency được chọn theo partition count và workload.
- [ ] Async work không hoàn tất out of order hoặc có version guard.
- [ ] Batch processing giữ thứ tự trong từng partition.
- [ ] Rebalance drain/cancel in-flight tasks đúng cách.
- [ ] Offset acknowledgment theo business completion semantics.
- [ ] Blocking retry và non-blocking retry được chọn theo ordering contract.
- [ ] DLT replay có sequence/reconciliation policy.

**Correctness**

- [ ] Events có aggregate ID và sequence/version khi cần.
- [ ] Consumer idempotent với duplicate delivery.
- [ ] Inbox/unique event ID được lưu cùng business side effect.
- [ ] Stale events và version gaps được phân biệt.
- [ ] Kafka EOS không bị hiểu nhầm là DB exactly-once.
- [ ] Business ordering domain được ghi trong contract.

**Operations and verification**

- [ ] Lag được theo dõi per partition.
- [ ] Hot keys/partition skew được quan sát.
- [ ] Retry/DLT/rebalance metrics có dashboard.
- [ ] Có integration test cùng key, nhiều keys, retry và rebalance.
- [ ] Có test partition expansion và replay.
- [ ] Có runbook xử lý out-of-order event.
- [ ] Không dùng key/offset/event ID làm metric labels.

## 26. Tài liệu tham khảo

- Apache Kafka Documentation — Introduction and topics/partitions: https://kafka.apache.org/documentation/
- Apache Kafka Producer Configuration: https://kafka.apache.org/documentation/#producerconfigs
- Apache Kafka Consumer Configuration: https://kafka.apache.org/documentation/#consumerconfigs
- Spring for Apache Kafka — Message Listener Containers: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring for Apache Kafka — Handling Exceptions: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring for Apache Kafka — Retry Topic: https://docs.spring.io/spring-kafka/reference/retrytopic.html
- Spring for Apache Kafka — Transactions: https://docs.spring.io/spring-kafka/reference/kafka/transactions.html

Hãy đối chiếu chi tiết producer defaults, idempotence, retry semantics và listener API với Kafka client/Spring Kafka version đang triển khai.

## 27. Kết luận

Kafka bảo đảm thứ tự records **trong một partition**, không tạo global order giữa nhiều partitions. Để giữ thứ tự theo business aggregate, producer cần dùng key ổn định, partitioner nhất quán và send flow có sequencing; consumer cần xử lý tuần tự trong partition và tránh async side effects hoàn tất out of order. Producer idempotence giúp xử lý retries/duplicates ở protocol layer nhưng không thay thế business sequence numbers hoặc idempotency.

Ordering còn có thể bị ảnh hưởng bởi tăng partition count, multiple producers, blocking/non-blocking retry, DLT replay, batch processing và consumer rebalance. Một thiết kế production đáng tin cậy kết hợp per-key routing, aggregate version, inbox/outbox, retry policy phù hợp, lag/sequence monitoring và integration tests. Hãy xác định rõ ordering domain trước khi chọn partition key, concurrency hoặc retry strategy; những lựa chọn này trực tiếp quyết định tính đúng của dữ liệu.

