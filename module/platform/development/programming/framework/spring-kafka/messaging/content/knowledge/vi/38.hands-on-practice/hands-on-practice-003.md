# Thiết kế topic và key cho đơn hàng

Trong một hệ thống xử lý đơn hàng, nhiều service cần nhận các sự kiện như `OrderCreated`, `OrderPaid`, `OrderShipped` và `OrderCancelled`. Thiết kế topic và key quyết định các sự kiện được lưu ở đâu, consumer nào nhận chúng, khả năng mở rộng theo partition và việc giữ thứ tự cho từng đơn hàng.

Bài thực hành này yêu cầu thiết kế một topology Kafka cho luồng đơn hàng bằng Spring Kafka. Bạn sẽ chọn topic theo mục đích dữ liệu, chọn key theo aggregate cần giữ ordering, xác định partition/replication/retention, cấu hình producer và kiểm chứng metadata gửi thực tế. Mục tiêu là tạo thiết kế có thể giải thích và kiểm thử được, thay vì chọn partition hoặc key theo cảm tính.

## 1. Bối cảnh và yêu cầu nghiệp vụ

Giả sử hệ thống thương mại điện tử có các thành phần:

- `order-service` nhận yêu cầu đặt hàng và phát sự kiện vòng đời đơn hàng.
- `order-projection` đọc sự kiện để cập nhật read model phục vụ truy vấn.
- `notification-service` đọc sự kiện để gửi email hoặc thông báo.
- `analytics-service` đọc sự kiện để tổng hợp số liệu.
- Một màn hình vận hành cần đọc trạng thái mới nhất của từng đơn hàng.

Các yêu cầu chính:

1. Những sự kiện của cùng một đơn hàng phải được xử lý theo thứ tự nghiệp vụ.
2. Nhiều service độc lập đều nhận được cùng luồng sự kiện.
3. Các service có thể scale consumer riêng mà không làm service khác mất record.
4. Trạng thái mới nhất của một đơn hàng có thể được đọc như một bản ghi hiện hành.
5. Record lỗi có nơi cách ly để điều tra và replay.
6. Thiết kế phải có khả năng mở rộng partition, đồng thời nêu rõ ảnh hưởng khi thay đổi số partition.

Điểm cần phân biệt: Kafka bảo đảm thứ tự trong một partition. Muốn giữ thứ tự cho các sự kiện của một đơn hàng, producer phải định tuyến chúng vào cùng partition và consumer không được làm đảo thứ tự khi xử lý bất đồng bộ.

## 2. Chọn topic theo mục đích dữ liệu

Không nên tạo một topic cho từng record hoặc gộp mọi dữ liệu không liên quan vào một topic duy nhất. Hãy nhóm dữ liệu theo vòng đời, cách tiêu thụ, retention và chính sách vận hành.

Thiết kế đề xuất cho bài lab:

| Topic | Mục đích | Cleanup policy | Key | Retention/ghi chú |
|---|---|---|---|---|
| `orders.events` | Luồng sự kiện bất biến về vòng đời đơn hàng | `delete` | `orderId` | Ví dụ giữ 7 ngày; điều chỉnh theo nhu cầu replay và lưu trữ. |
| `orders.status` | Changelog trạng thái mới nhất của mỗi đơn hàng | `compact` | `orderId` | Kafka giữ giá trị mới nhất theo key sau quá trình compaction; phù hợp cho state snapshot. |
| `orders.dlt` | Record không xử lý được sau retry/recovery | `delete` | Giữ key gốc, thường là `orderId` | Ví dụ giữ 30 ngày để điều tra; có quy trình replay và kiểm soát quyền truy cập. |

`orders.events` là event stream. Mỗi thay đổi nghiệp vụ được ghi thành một record mới; không cập nhật hoặc ghi đè sự kiện cũ. `orders.status` là changelog compacted: với cùng key, các giá trị cũ có thể được dọn sau khi broker compaction chạy. Đây không phải cơ chế lưu mọi lịch sử thay đổi.

`orders.dlt` là vùng cách ly vận hành. Nếu `DeadLetterPublishingRecoverer` giữ partition nguồn khi publish DLT, topic DLT cần có đủ partition tương ứng. Không trộn record lỗi vào `orders.events` như thể đó là sự kiện nghiệp vụ mới.

Chỉ thêm `orders.commands` nếu hệ thống có luồng command bất đồng bộ với quyền ghi, consumer và vòng đời retry riêng. Command thể hiện yêu cầu cần thực hiện; event thể hiện điều đã xảy ra. Không cần tạo topic command nếu ứng dụng chỉ phát domain event.

## 3. Chọn key: vì sao dùng `orderId`?

Key quyết định partition khi producer không chỉ định partition trực tiếp. Với partitioner mặc định, cùng key thường được ánh xạ vào cùng partition nếu topic partition count và partitioner không thay đổi.

Trong bài lab, chọn `orderId` làm key cho `orders.events`:

| Key đề xuất | Phù hợp khi | Hạn chế |
|---|---|---|
| `orderId` | Cần thứ tự các sự kiện trong cùng đơn hàng | Các đơn hàng phân bố theo hash; một đơn hàng rất nóng vẫn tập trung vào một partition. |
| `customerId` | Mọi thay đổi của khách hàng cần được xử lý theo thứ tự chung | Một khách hàng có nhiều đơn hàng sẽ dồn vào cùng partition, có thể tạo hot key. |
| `eventId` | Cần định tuyến từng sự kiện độc lập | Các sự kiện cùng đơn hàng có thể vào partition khác nhau, mất ordering theo đơn hàng. |
| `null` | Không có định danh để phân vùng theo aggregate | Không có bảo đảm các sự kiện cùng đơn hàng vào cùng partition. |

Với vòng đời đơn hàng, `orderId` là lựa chọn tự nhiên vì các event `Created`, `Paid`, `Shipped` và `Cancelled` cùng mô tả một aggregate. Không dùng `eventId` làm key chỉ vì mỗi record có một ID duy nhất; điều đó làm mất mối liên hệ partition giữa các sự kiện của cùng đơn hàng.

Producer gửi key ổn định:

```java
kafkaTemplate.send("orders.events", event.orderId(), event);
```

Nếu phát trạng thái hiện hành vào `orders.status`, cũng dùng `orderId` làm key để mọi bản cập nhật của cùng đơn hàng thay thế đúng logical entry trong compacted topic:

```java
kafkaTemplate.send("orders.status", status.orderId(), status);
```

Không nên tự tính `hash(orderId) % partitionCount` ở business service. Để Kafka producer partitioner xử lý mapping và kiểm tra partition thực tế qua `RecordMetadata`. Việc tự tính dễ lệch thuật toán partitioner, xử lý key null hoặc metadata topic.

## 4. Xác định partition count và replication factor

Partition count ảnh hưởng mức song song tối đa của một consumer group. Nếu `orders.events` có 6 partition, một group có tối đa 6 consumer active được gán partition tại cùng thời điểm. Tăng số replica vượt số partition không tự tăng throughput của group.

Trong bài lab, chọn 6 partition làm điểm bắt đầu để thực hành scale consumer. Đây là con số minh họa, không phải giá trị mặc định cho production. Khi thiết kế thật, cần ước lượng:

- Throughput đầu vào và throughput mà một consumer xử lý được.
- Số consumer/concurrency dự kiến trong mỗi service.
- Số replica tối đa và kế hoạch autoscaling.
- Số topic/partition broker phải quản lý.
- Tỷ lệ key nóng và phân bố đơn hàng.
- Yêu cầu ordering và khả năng thay đổi partition count về sau.

Replication factor là số bản sao partition trong cluster. Với môi trường production có tối thiểu ba broker, có thể bắt đầu đánh giá replication factor 3 và cấu hình `min.insync.replicas` phù hợp với `acks=all`. Với embedded broker hoặc local development chỉ có một broker, phải dùng replication factor 1; không thể tạo topic RF=3 trên broker đơn.

| Môi trường | Partition gợi ý cho lab | Replication factor | Mục đích |
|---|---:|---:|---|
| Local/Embedded Kafka một broker | 6 | 1 | Kiểm thử routing, key và consumer assignment. |
| Cluster production từ ba broker | Theo throughput và scale plan | Thường đánh giá RF=3 | Chịu lỗi broker và tăng độ bền dữ liệu. |

Trước khi tăng partition count của topic đang có dữ liệu, hãy đánh giá key mapping. Cùng `orderId` có thể được ánh xạ sang partition mới sau khi partition count thay đổi; record cũ vẫn nằm ở partition cũ. Nếu ordering liên tục theo aggregate là yêu cầu cứng, cần kế hoạch migration hoặc sequence/version để phát hiện event đến muộn.

## 5. Chọn retention và cleanup policy

`orders.events` cần giữ lịch sử sự kiện trong khoảng thời gian đủ cho consumer phục hồi, replay hoặc tái dựng projection. Ví dụ bài lab dùng 7 ngày:

```text
cleanup.policy=delete
retention.ms=604800000
```

Giá trị này tương đương 7 ngày. Production cần dựa trên thời gian outage tối đa chấp nhận, thời gian replay, lưu lượng, dung lượng broker và yêu cầu audit. Nếu cần lưu lịch sử lâu dài, cân nhắc archive sang object storage hoặc hệ thống lưu trữ chuyên dụng thay vì tăng retention vô hạn trên broker.

`orders.status` dùng `cleanup.policy=compact`. Compaction giữ giá trị mới nhất theo key sau khi log cleaner xử lý; nó diễn ra bất đồng bộ, nên không có nghĩa mọi giá trị cũ biến mất ngay khi producer gửi bản cập nhật mới. Khi gửi tombstone (value null) cho một key, ứng dụng đánh dấu key đó cần bị loại khỏi compacted view theo quy tắc tombstone retention.

`orders.dlt` thường dùng `delete` với retention đủ dài cho điều tra. DLT phải có chủ sở hữu, dashboard, cảnh báo và quy trình replay. Không để DLT thành nơi lưu trữ vô thời hạn mà không kiểm soát dung lượng hoặc quyền truy cập.

## 6. Tạo topic cho bài thực hành

Với Kafka local một broker, tạo ba topic bằng replication factor 1:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.events \
  --partitions 6 \
  --replication-factor 1 \
  --config cleanup.policy=delete \
  --config retention.ms=604800000

bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.status \
  --partitions 6 \
  --replication-factor 1 \
  --config cleanup.policy=compact

bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.dlt \
  --partitions 6 \
  --replication-factor 1 \
  --config cleanup.policy=delete \
  --config retention.ms=2592000000
```

Trong production cluster ba broker, đánh giá replication factor 3 và `min.insync.replicas` phù hợp. Không sao chép lệnh RF=1 của local thành cấu hình production nếu yêu cầu độ bền cần replication.

Kiểm tra topology sau khi tạo:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.events

bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.status
```

Xác minh số partition, leader, replica và topic config. Nếu topic đã tồn tại với cấu hình khác, lệnh `--create` có thể báo topic tồn tại; hãy mô tả và điều chỉnh bằng quy trình quản trị rõ ràng thay vì xóa topic có dữ liệu.

## 7. Định nghĩa event envelope ổn định

Một event nên có metadata đủ để consumer xác định loại sự kiện, định danh, aggregate và phiên bản. Ví dụ:

```java
public record OrderEvent(
        String eventId,
        String orderId,
        long aggregateVersion,
        String eventType,
        Instant occurredAt,
        Map<String, Object> data) {
}
```

Ví dụ payload:

```json
{
  "eventId": "evt-1001",
  "orderId": "order-42",
  "aggregateVersion": 1,
  "eventType": "OrderCreated",
  "occurredAt": "2026-11-17T05:00:00Z",
  "data": {
    "currency": "VND",
    "totalAmount": 1250000
  }
}
```

`eventId` nhận diện một lần phát sự kiện và hữu ích cho idempotency. `orderId` là key Kafka và aggregate identity. `aggregateVersion` giúp consumer phát hiện event trùng hoặc đến sai thứ tự. `eventType` cho biết ý nghĩa nghiệp vụ; `occurredAt` phục vụ truy vết, không thay thế offset để xác định thứ tự append trong partition.

Khi schema thay đổi, cần có chiến lược compatibility rõ ràng. Không đổi ý nghĩa field cũ hoặc tái sử dụng event type cho payload không tương thích. Với hệ thống lớn, cân nhắc schema registry và schema format có kiểm soát thay vì dựa hoàn toàn vào `Map<String, Object>`.

## 8. Cấu hình producer Spring Kafka

Ví dụ cấu hình Spring Boot dùng `StringSerializer` cho key và `JsonSerializer` cho event value:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
```

Producer service gửi event bằng `orderId` làm key:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {

        return kafkaTemplate.send(
                "orders.events",
                event.orderId(),
                event);
    }
}
```

Ví dụ dùng API `CompletableFuture` của các phiên bản Spring Kafka hiện đại. Nếu dự án đang dùng phiên bản cũ hơn, kiểu future có thể là `ListenableFuture`; hãy dùng API phù hợp với dependency của dự án. Trong callback gửi thành công, ghi nhận `topic`, `partition`, `offset`, `eventId` và `orderId` để xác minh routing.

`acks=all` yêu cầu broker xác nhận theo ISR hiện tại. Kết hợp với idempotent producer giúp tăng độ tin cậy gửi record; nó không thay thế idempotency ở consumer cho side effect nghiệp vụ.

## 9. Thiết kế consumer group cho các service

Mỗi service độc lập cần nhận toàn bộ event stream nên dùng consumer group riêng:

| Service | `group.id` | Vai trò |
|---|---|---|
| `order-projection` | `order-projection` | Cập nhật read model và trạng thái. |
| `notification-service` | `notification-service` | Gửi thông báo cho khách hàng. |
| `analytics-service` | `analytics-service` | Tổng hợp số liệu. |

Các replica của cùng một service dùng chung group ID để chia partition. Không dùng cùng group ID cho ba service trên nếu mỗi service đều phải nhận mọi event; Kafka sẽ phân phối record giữa các consumer trong cùng group thay vì broadcast cho từng service.

Ví dụ listener projection:

```java
@KafkaListener(topics = "orders.events", groupId = "order-projection")
public void project(OrderEvent event) {
    projectionService.apply(event);
}
```

Consumer của `orders.status` có thể dùng group riêng để dựng cache hoặc phục hồi trạng thái hiện hành. Consumer cần hiểu compacted topic có thể chứa nhiều version theo key trong lúc compaction chưa chạy; nếu cần dựng state, hãy áp dụng record theo thứ tự offset và xử lý tombstone.

## 10. Kiểm tra partition và ordering

Gửi ít nhất ba event của cùng một đơn hàng và một event của đơn hàng khác. Trong test, chờ từng lần gửi được broker xác nhận để có thể so sánh metadata và tránh kết thúc test trước khi producer hoàn tất:

```java
publisher.publish(new OrderEvent(
        "evt-1", "order-42", 1, "OrderCreated", Instant.now(), Map.of()))
        .get(10, TimeUnit.SECONDS);
publisher.publish(new OrderEvent(
        "evt-2", "order-42", 2, "OrderPaid", Instant.now(), Map.of()))
        .get(10, TimeUnit.SECONDS);
publisher.publish(new OrderEvent(
        "evt-3", "order-42", 3, "OrderShipped", Instant.now(), Map.of()))
        .get(10, TimeUnit.SECONDS);
publisher.publish(new OrderEvent(
        "evt-4", "order-99", 1, "OrderCreated", Instant.now(), Map.of()))
        .get(10, TimeUnit.SECONDS);
```

Sau khi broker xác nhận gửi, kiểm tra metadata:

- Ba event của `order-42` phải có cùng partition nếu topic partition count và partitioner không đổi.
- Offset của ba event đó phải tăng theo thứ tự gửi đã được producer xác nhận.
- `order-99` có thể vào cùng hoặc khác partition; không assert rằng hai order bắt buộc khác partition.
- Consumer group của projection, notification và analytics phải nhận độc lập cùng luồng event.

Có thể kiểm tra bằng lệnh console consumer hoặc integration test dùng `EmbeddedKafka`:

```bash
bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.events \
  --from-beginning \
  --property print.key=true \
  --property print.partition=true \
  --property print.offset=true
```

Không khẳng định có thứ tự toàn cục giữa partition 0, 1, 2. Kafka chỉ bảo đảm thứ tự trong từng partition. Nếu listener gửi công việc sang thread pool, completion order có thể khác delivery order; khi đó cần kiểm tra sequence/version và cách xử lý theo key.

## 11. Phân tích tình huống thay đổi partition count

Giả sử `orders.events` ban đầu có 6 partition và producer dùng `orderId` làm key. Sau một thời gian, đội vận hành tăng lên 12 partition để tăng song song. Record cũ vẫn nằm ở partition ban đầu, nhưng key có thể được ánh xạ sang partition khác với số partition mới.

Điều này có thể làm lịch sử một order nằm trên nhiều partition. Consumer group không có cách tự sắp xếp toàn cục các record đó theo aggregate. Nếu cần giữ ordering liên tục, cân nhắc:

- Chọn partition count đủ cho kế hoạch tăng trưởng ngay từ đầu.
- Dùng `aggregateVersion` và chỉ áp dụng event có version hợp lệ.
- Tạo topic phiên bản mới và migration dữ liệu theo quy trình có kiểm soát.
- Dùng một partitioning strategy ổn định do ứng dụng quản lý, nhưng phải đánh giá khả năng mở rộng và hot partition.

Không tăng partition count chỉ vì consumer lag tăng. Trước hết xác định lag đến từ thiếu consumer, xử lý chậm, key skew, downstream saturation hay fetch configuration.

## 12. Bài tập thực hành

Thực hiện theo thứ tự sau trong môi trường local hoặc embedded Kafka:

1. Tạo `orders.events` với 6 partition, cleanup `delete` và retention 7 ngày.
2. Tạo `orders.status` với 6 partition và cleanup `compact`.
3. Tạo `orders.dlt` với 6 partition và retention đủ cho điều tra.
4. Định nghĩa `OrderEvent` có `eventId`, `orderId`, `aggregateVersion`, `eventType`, `occurredAt` và `data`.
5. Viết publisher dùng `orderId` làm key cho `orders.events`.
6. Gửi ba event liên tiếp cho `order-42` và ít nhất một event cho `order-99`.
7. Ghi lại metadata gửi: topic, partition và offset.
8. Tạo hai consumer group độc lập và xác minh cả hai đều nhận các event.
9. Tạo listener cập nhật `orders.status` theo key `orderId`.
10. Thử gửi event với `eventId` làm key và giải thích vì sao ordering theo order không còn được bảo đảm.
11. Mô phỏng thay đổi partition count trong môi trường test riêng và phân tích khả năng remap key.
12. Viết ghi chú sizing: throughput mục tiêu, số consumer, concurrency, partition count, replication và retention.

### Sản phẩm cần nộp

- Bảng mô tả ba topic, mục đích, partition, replication factor, cleanup policy và retention.
- Giải thích vì sao `orderId` là key cho event stream và status topic.
- Mã publisher Spring Kafka gửi đúng topic/key.
- Kết quả metadata của ít nhất ba event cùng order.
- Kết quả kiểm tra hai consumer group độc lập.
- Phân tích rủi ro khi tăng partition count và phương án giữ ordering.

## 13. Tiêu chí nghiệm thu

| Tiêu chí | Điều kiện đạt |
|---|---|
| Topic design | Phân biệt event stream, compacted state và DLT theo mục đích rõ ràng. |
| Key design | Các event của cùng order dùng cùng `orderId` làm key. |
| Partition | Số partition được giải thích theo throughput/concurrency, không chọn tùy tiện. |
| Replication | Local RF=1 và production RF được chọn theo số broker cùng yêu cầu độ bền. |
| Retention | Event và DLT có retention phù hợp; status topic dùng compaction. |
| Producer | Gửi đúng topic/key và ghi nhận metadata broker trả về. |
| Consumer group | Các service độc lập dùng group ID riêng; replica cùng service dùng chung group ID. |
| Ordering | Chỉ cam kết ordering trong partition và nhận diện rủi ro khi tăng partition count. |
| Vận hành | Có kế hoạch theo dõi lag, hot partition, DLT và replay. |

## 14. Câu hỏi tự đánh giá

1. Vì sao `eventId` không phải key phù hợp nếu cần giữ thứ tự vòng đời của một đơn hàng?
2. Nếu `order-42` và `order-99` được hash vào cùng partition, điều đó có sai thiết kế không? Vì sao?
3. Vì sao ba service cần xử lý cùng event phải dùng ba consumer group khác nhau?
4. Compacted topic khác event stream có retention delete ở điểm nào?
5. Tại sao tăng partition count có thể làm các event mới của cùng order vào partition khác với event cũ?
6. Nếu record có partition và offset đúng nhưng trạng thái database bị cập nhật ngược thứ tự, cần kiểm tra tầng nào?

Thiết kế topic và key tốt bắt đầu từ aggregate và cách dữ liệu được tiêu thụ. Với luồng đơn hàng, `orders.events` dùng `orderId` làm key để giữ thứ tự trong partition, `orders.status` dùng cùng key cho trạng thái mới nhất, còn `orders.dlt` tách riêng dữ liệu cần điều tra. Khi partition count, retention, replication và consumer group được lựa chọn theo yêu cầu rõ ràng, hệ thống Spring Kafka có thể mở rộng mà vẫn giữ được khả năng truy vết và tính đúng đắn của luồng đơn hàng.
