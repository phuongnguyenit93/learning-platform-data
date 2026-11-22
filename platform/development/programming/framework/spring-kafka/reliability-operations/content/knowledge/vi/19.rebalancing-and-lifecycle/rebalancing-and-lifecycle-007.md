# Rebalance do poll chậm

Trong Spring Kafka, một listener có thể xử lý record đúng về nghiệp vụ nhưng vẫn gây ra **consumer group rebalance** nếu quá lâu không quay lại vòng gọi `KafkaConsumer.poll()`. Tình huống này xuất hiện khi xử lý batch lớn, gọi database hoặc HTTP chậm, giữ lock lâu, dừng ở debugger, thiếu CPU, hoặc dùng backoff chặn luồng consumer trong thời gian dài. Kafka diễn giải việc ứng dụng không gọi `poll()` đúng hạn là dấu hiệu member không còn tiến triển đủ nhanh để tiếp tục sở hữu partition.

Rebalance do poll chậm đặc biệt nguy hiểm vì lỗi có thể không xuất hiện ngay trong business method. Side effect đã được ghi xuống database nhưng partition bị thu hồi trước khi offset được commit; một consumer khác sau đó đọc lại record, dẫn tới xử lý trùng. Tăng số lần retry hoặc tăng concurrency không tự giải quyết nguyên nhân. Cần hiểu chính xác **`max.poll.interval.ms`**, **`session.timeout.ms`**, thời gian thực thi listener và cách Spring Kafka tổ chức consumer thread.

## 1. Consumer group cần cả heartbeat lẫn tiến độ poll

Một consumer trong Kafka group phải chứng minh hai điều khác nhau:

1. **Nó còn sống và kết nối với group coordinator** thông qua cơ chế heartbeat hoặc group protocol tương ứng.
2. **Ứng dụng tiếp tục gọi `poll()` trong thời hạn cho phép**, thể hiện rằng consumer không bị treo ở xử lý record vô hạn.

Hai cơ chế dùng các giới hạn thời gian khác nhau:

| Thuộc tính/cơ chế | Ý nghĩa | Nếu vi phạm |
|---|---|---|
| `max.poll.interval.ms` | Khoảng thời gian tối đa giữa các lời gọi `poll()` liên tiếp trong mô hình consumer group thông thường | Kafka coi member không tiến triển; có thể rời group/bị thu hồi partition và rebalance |
| `session.timeout.ms` | Thời hạn coordinator chờ heartbeat của member theo group protocol áp dụng | Member mất phiên, partition được gán lại |
| `heartbeat.interval.ms` | Nhịp heartbeat phía consumer trong classic group protocol | Điều chỉnh tần suất kiểm tra sự sống, **không thay thế** poll interval |
| `max.poll.records` | Số record tối đa trả về mỗi lần `poll()` | Không trực tiếp gây rebalance; batch quá lớn làm thời gian xử lý vượt poll interval |
| `pollTimeout` của Spring listener container | Thời gian một lời gọi Kafka `poll()` có thể chờ dữ liệu | Khác hoàn toàn với `max.poll.interval.ms`; không phải giới hạn thời gian xử lý nghiệp vụ |

Trong Kafka client hiện đại, heartbeat có thể chạy độc lập với business processing. Vì thế **vẫn có heartbeat nhưng không poll đủ thường xuyên** là một tình huống thực tế. Kafka không dùng việc còn heartbeat làm lý do để cho consumer giữ partition mãi khi vượt `max.poll.interval.ms`.

Trong **classic consumer group protocol** với member động, khi hết `max.poll.interval.ms`, consumer thường chủ động rời group và coordinator tiến hành gán lại partition. Với **static membership** (`group.instance.id`), khi vượt poll interval, consumer có thể ngừng gửi heartbeat nhưng chưa bị gán lại partition cho đến khi hết session timeout. Các chi tiết thời điểm và cơ chế heartbeat còn phụ thuộc protocol/client version; không nên coi việc đặt `group.instance.id` là cách vô hiệu hóa giới hạn poll.

## 2. Vì sao Spring Kafka dễ gặp poll chậm khi listener đồng bộ?

Trong cấu hình record listener đồng bộ thông thường, container gọi `poll()`, lấy một tập `ConsumerRecord`, rồi lần lượt gọi phương thức `@KafkaListener`. Phần lớn logic xử lý record chạy trên consumer thread của container. **Trong lúc listener đang chạy đồng bộ, thread đó chưa quay lại `poll()`**.

```text
Consumer thread của một partition assignment
           |
           v
KafkaConsumer.poll() -> nhận nhiều record
           |
           +--> listener(record 1) -> database
           +--> listener(record 2) -> HTTP API
           +--> listener(record 3) -> tính toán
           +--> ...
           |
           v
KafkaConsumer.poll() tiếp theo

<---------------- khoảng cách giữa hai poll ---------------->
```

Một `ConcurrentMessageListenerContainer` có thể tạo nhiều child containers/consumer threads theo cấu hình concurrency. Mỗi Kafka consumer vẫn có vòng `poll()` và giới hạn thời gian của **chính consumer đó**. Tăng concurrency không biến một lần gọi listener đang chặn thành non-blocking, cũng không chia nhỏ một batch đã được trao cho một consumer trong lúc nó xử lý.

Đây là lỗi ở **vòng xử lý của consumer**, không nhất thiết là broker chậm. Broker có thể hoàn toàn khỏe mạnh, topic có dữ liệu, heartbeat vẫn được ghi, nhưng consumer thread bị giữ tại database, REST client hoặc business lock.

## 3. Timeline: từ poll chậm đến rebalance

Giả sử consumer dùng `max.poll.interval.ms=300000` (5 phút), `max.poll.records=500`. Mỗi record cần trung bình 800 ms để xử lý đồng bộ. Một poll trả về 500 record; tổng thời gian chỉ riêng business processing khoảng 400 giây, chưa tính commit, serialization, GC hoặc retry.

```text
t=0s       poll() trả về 500 records
           |
           v
t=0..300s  listener xử lý lần lượt, chưa poll lại
           |
t≈300s     vượt max.poll.interval.ms (300 giây)
           |
           v
           member mất quyền tiếp tục sở hữu assignment
           / có thể rời group; rebalance bắt đầu
           |
           v
t≈400s     business method mới hoàn tất
           |
           v
           commit offset có thể thất bại do generation/assignment đã đổi
```

Hậu quả phụ thuộc member type, protocol và thời điểm group hoàn tất rebalance. Một consumer khác có thể được giao partition đã thu hồi và đọc lại từ **committed offset cuối cùng**, trong khi consumer cũ vẫn đang hoàn thành side effect của những record trước đó.

Ví dụ partition `orders-2`:

| Offset | Diễn tiến có thể xảy ra |
|---:|---|
| 100 | Consumer A đã xử lý và commit thành công |
| 101 | Consumer A ghi database thành công nhưng chưa commit offset |
| 102 | Consumer A đang gọi downstream lâu |
| — | Poll interval hết; partition được gán lại cho consumer B |
| 101 | Consumer B có thể đọc lại từ committed offset và xử lý trùng |

Không nên kết luận rằng Kafka đã “giao cùng một record hai lần trái quy tắc”. Với delivery semantics thông thường, offset chưa được commit có thể được giao lại khi assignment thay đổi hoặc tiến trình restart. Đây là **at-least-once delivery**, đòi hỏi side effect idempotent.

## 4. Phân biệt rebalance do poll chậm và mất heartbeat

Hai sự cố có thể cùng biểu hiện là consumer mất partition, lag tăng và xuất hiện rebalance log, nhưng cách sửa khác nhau.

| Quan sát | Nghi ngờ `max.poll.interval.ms` | Nghi ngờ session/heartbeat |
|---|---|---|
| Listener chạy lâu trong DB/API | Rất phù hợp | Không nhất thiết |
| Log có nội dung `consumer poll timeout has expired` | Bằng chứng mạnh | Không phải chỉ báo chính |
| `time-between-poll-max` sát/vượt ngưỡng | Bằng chứng mạnh | Có thể không tăng |
| Consumer thread chặn trên lock/GC hoặc retry sleep | Rất phù hợp | Có thể gián tiếp |
| Network timeout hoặc coordinator không nhận heartbeat | Có thể cùng xảy ra | Cần kiểm tra |
| Partition bị gán lại dù process còn sống | Có thể | Có thể |
| Sau rebalance xuất hiện `CommitFailedException` | Có thể là hậu quả | Cũng có thể là hậu quả |

Một dấu hiệu thường gặp trong log Kafka client là thông báo tương tự:

```text
consumer poll timeout has expired
```

Thông điệp thực tế thay đổi theo phiên bản client và có thể kèm `max.poll.interval.ms`, lý do rời group hoặc gợi ý tăng interval/giảm `max.poll.records`. Cần đối chiếu log với thời gian xử lý listener thay vì chỉ dựa vào một dòng cảnh báo.

Nếu rebalance trùng với rolling deployment, consumer restart hoặc broker outage, đừng vội kết luận nguyên nhân là poll chậm. Rebalance còn có thể do thành viên group thay đổi, topic partition count tăng hoặc cơ chế assignment hoạt động bình thường.

## 5. `max.poll.records` và ngân sách thời gian xử lý

Một ước lượng ban đầu hữu ích:

```text
T_poll_gap ≈ T_process_records + T_error_handling
             + T_commit + T_runtime_overhead

T_process_records ≈ N_records × T_per_record

Yêu cầu vận hành:
T_poll_gap phải nhỏ hơn max.poll.interval.ms với khoảng dự phòng đủ lớn
```

Ví dụ:

| Chỉ số | Giá trị giả định |
|---|---:|
| `max.poll.interval.ms` | 300.000 ms (300 giây) |
| Thời gian xử lý p99/record | 700 ms |
| Số record trong một poll | 500 |
| Ước lượng 500 × 700 ms | 350 giây |
| Kết luận | Đã vượt ngân sách 300 giây trước khi tính overhead |

Đây không phải phép đảm bảo thống kê: nhân p99 của từng record với số record là một ước lượng bảo thủ, và phân phối latency/batch thực tế cần được đo. Với batch listener, có thể có thời gian gọi API theo lô hoặc transaction chung, nên tổng thời gian không nhất thiết bằng tổng các latency từng record. Dù vậy, công thức giúp chỉ ra vì sao `max.poll.records` lớn có thể gây poll timeout.

Giải pháp đầu tiên thường là **giới hạn số record mỗi lần poll** và giảm thời gian xử lý đồng bộ, không phải tăng `max.poll.interval.ms` vô hạn. Số record nhỏ làm mỗi vòng poll ngắn hơn nhưng có thể tăng overhead, vì vậy phải đo throughput và latency sau khi thay đổi.

## 6. Cấu hình Spring Boot: giới hạn poll và batch

Ví dụ cấu hình một listener cho record processing thông thường:

```properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=order-worker
spring.kafka.consumer.enable-auto-commit=false

# Không để mỗi lần poll lấy quá nhiều record nếu mỗi record xử lý lâu.
spring.kafka.consumer.max-poll-records=100

# Thuộc tính Kafka client: thời hạn giữa các lời gọi poll.
spring.kafka.consumer.properties[max.poll.interval.ms]=300000

spring.kafka.listener.ack-mode=record
spring.kafka.listener.concurrency=3
```

Các số trên chỉ minh họa. `max.poll.interval.ms` cần đủ cho phần xử lý p99/worst-case hợp lý, retry và overhead; `max.poll.records` phải cân bằng giữa batch efficiency và khả năng quay lại `poll()` đúng hạn.

`spring.kafka.listener.concurrency=3` cho phép tối đa ba consumer child containers đối với factory mặc định trong các điều kiện phù hợp, nhưng mức sử dụng thực tế phụ thuộc số partition được gán. Nếu group chỉ nhận hai partition, tăng concurrency lên 12 không tạo ra 12 đường xử lý hữu ích cho hai partition đó.

Một `@KafkaListener` sử dụng default factory có thể viết:

```java
@KafkaListener(topics = "orders", groupId = "order-worker")
public void onOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
```

Trong ví dụ, `OrderEvent` và `orderService` là class/service giả định; deserializer, schema, exception handler và downstream timeout cần cấu hình riêng. Nếu ứng dụng khai báo nhiều `ConsumerFactory` hoặc container factory, hãy xác nhận listener đang dùng đúng factory nhận các property trên. Một cấu hình global có thể bị bean chuyên biệt ghi đè.

## 7. Tùy chỉnh `ConsumerFactory` riêng theo workload

Khi một nhóm listener có thời gian xử lý dài hơn, có thể tạo `ConsumerFactory` riêng thay vì tăng global `max.poll.interval.ms` cho toàn hệ thống.

```java
@Bean("slowOrderConsumerFactory")
ConsumerFactory<String, OrderEvent> slowOrderConsumerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> props =
            new HashMap<>(kafkaProperties.buildConsumerProperties());

    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 25);
    props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 600_000);

    return new DefaultKafkaConsumerFactory<>(props);
}

@Bean("slowOrderListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
slowOrderListenerContainerFactory(
        @Qualifier("slowOrderConsumerFactory")
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}
```

Listener gắn rõ factory:

```java
@KafkaListener(
        topics = "slow-orders",
        groupId = "slow-order-worker",
        containerFactory = "slowOrderListenerContainerFactory")
public void handleSlowOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
```

Đoạn cấu hình dùng `KafkaProperties` để kế thừa client settings như bootstrap, security và deserializer; cách gọi `buildConsumerProperties()` có thể có overload khác tùy phiên bản Spring Boot. Kiểm tra runtime client config để xác nhận property đã được đưa vào consumer thực tế.

Việc tăng `max.poll.interval.ms` từ 5 lên 10 phút là một **trade-off**: member có thể giữ partition lâu hơn khi application không tiến triển. Nếu một consumer thực sự treo, việc phát hiện và gán lại công việc có thể chậm hơn. Chỉ tăng sau khi đã kiểm soát các nguyên nhân gây chậm và xác định rõ SLO.

## 8. Lỗi thường gặp: gọi downstream không có timeout

Một trong những nguyên nhân hay gặp nhất là listener gọi database hoặc HTTP service mà không có timeout ở từng tầng. Một connection timeout không giới hạn hoặc một query chờ lock có thể giữ consumer thread lâu hơn `max.poll.interval.ms`.

Ví dụ không nên làm:

```java
@KafkaListener(topics = "orders")
public void consume(OrderEvent event) {
    // HTTP call có thể chờ rất lâu nếu không cấu hình timeout.
    externalInventoryClient.reserve(event);
    orderRepository.save(event.toOrder());
}
```

Thiết kế tốt hơn cần timeout, retry budget và isolation cho từng dependency:

```java
@KafkaListener(topics = "orders")
public void consume(OrderEvent event) {
    // Adapter phải có connect/read/request timeout rõ ràng.
    inventoryAdapter.reserveWithBoundedTimeout(event);
    orderService.saveIdempotently(event);
}
```

Trong ví dụ, method `reserveWithBoundedTimeout` là API do ứng dụng tự định nghĩa. Timeout thực tế phải được đặt tại HTTP client/connection pool, database driver/query hoặc proxy tương ứng; đặt tên method không làm lời gọi tự có timeout.

Nên tính **ngân sách end-to-end**. Nếu một record cho phép ba lần retry HTTP, mỗi lần read timeout 30 giây, cộng backoff 10 giây giữa các lần, tổng thời gian có thể vượt 100 giây cho một record. Một poll lấy năm record tương tự có thể vượt 5 phút rất nhanh.

## 9. Retry blocking, backoff và poll interval

`DefaultErrorHandler` có thể retry record với `FixedBackOff`, exponential backoff hoặc logic khác. Nếu listener thất bại và container chờ lâu trước khi retry cùng record, tổng thời gian không quay lại `poll()` có thể tăng. Đặt retry policy dài mà không tính `max.poll.interval.ms` có thể gây rebalance ngay khi ứng dụng đang cố phục hồi.

Ví dụ:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(30_000L, 4L));

    handler.addNotRetryableExceptions(
            InvalidOrderPayloadException.class);

    return handler;
}
```

Riêng các khoảng chờ cho bốn lần retry đã có thể lên tới 120 giây, chưa kể thời gian listener làm việc ở từng attempt. Nếu một attempt cần 60 giây và có nhiều attempt, tổng thời gian dễ chạm 300 giây.

Trong Spring Kafka, cách error handler đợi backoff và tương tác với poll có thể khác tùy phiên bản/cấu hình. Đối với khoảng chờ dài, có cơ chế **container-pausing backoff handler** (`ContainerPausingBackOffHandler`) giúp container pause consumer rồi tiếp tục `poll()` trong thời gian chờ, thay vì chỉ ngủ chặn luồng qua toàn bộ khoảng backoff. Đây là lựa chọn đáng xem xét khi muốn giữ group membership trong thời gian retry kéo dài.

Với non-blocking retry thông qua `@RetryableTopic`, record lỗi được publish sang retry topic và consumer nguồn có thể tiến tới record tiếp theo, giảm việc giữ partition nguồn do backoff dài. Đổi lại, **thứ tự xử lý tương đối có thể thay đổi**, vì record sau được xử lý trước record lỗi đang chờ trên retry topic. Không áp dụng giải pháp này nếu nghiệp vụ bắt buộc xử lý các event cùng key theo thứ tự nghiêm ngặt mà chưa có cơ chế phiên bản/trạng thái phù hợp.

## 10. Pause consumer không giống ngừng poll

Một nhầm lẫn phổ biến là “pause consumer để tránh rebalance”. Kafka consumer có thể được pause để tạm ngừng fetch record trên partition, nhưng để duy trì membership thì container **vẫn phải tiếp tục gọi `poll()`** đúng hạn.

```text
Pause + vẫn poll định kỳ:
  tạm không nhận record mới
  vẫn giữ kết nối, heartbeat/membership
  có thể resume khi downstream hồi phục

Thread sleep/chặn vô hạn:
  listener chưa trở lại poll()
  dễ vượt max.poll.interval.ms
  có thể bị gán lại partition
```

Spring Kafka listener container có API quản lý `pause()`/`resume()` và cơ chế pause theo partition; nên ưu tiên điều khiển qua container registry hoặc API container thích hợp thay vì tự ý gọi `consumer.pause()` từ thread khác. `KafkaConsumer` không thread-safe; việc thao tác consumer từ thread xử lý bất đồng bộ có thể gây race hoặc lỗi.

Pause không phải công cụ để “nới” thời gian cho một listener **đang chặn cùng consumer thread**. Nếu luồng vẫn ở trong một lời gọi database chưa trả về, container không thể tự nhiên tiếp tục vòng `poll()` chỉ vì đã đánh dấu pause. Cần giới hạn thời gian xử lý, đưa work sang thiết kế async có ranh giới an toàn, hoặc dùng backoff handler được container hỗ trợ.

## 11. Async processing không tự động an toàn

Đưa công việc sang một thread pool có thể giúp consumer thread quay lại `poll()` sớm hơn, nhưng cũng tạo các rủi ro mới: offset được commit trước khi xử lý xong, thứ tự theo partition bị thay đổi, bộ nhớ tăng do task backlog, hoặc consumer bị revoke partition khi task vẫn còn đang chạy.

Ví dụ anti-pattern:

```java
@KafkaListener(topics = "payments")
public void onPayment(PaymentCaptured event) {
    executor.execute(() -> paymentService.capture(event));
    // Method trả về ngay. Container có thể coi record đã xử lý xong.
}
```

Với một listener đồng bộ và ack mode tự động, method trả về có thể khiến container commit offset trước khi task bất đồng bộ hoàn tất. Nếu tiến trình crash ngay sau commit, task chưa xử lý có thể mất khỏi tiến độ tiêu thụ. Đây là **nguy cơ mất xử lý**, không phải cải thiện reliability.

Nếu cần async, hãy chọn một mô hình được Spring Kafka và phiên bản đang dùng hỗ trợ, có:

- Cách xác định chính xác task nào đã hoàn tất trước khi acknowledge offset.
- Kiểm soát in-flight tasks, hàng đợi bounded và backpressure.
- Quản lý partition ownership khi rebalance hoặc shutdown.
- Idempotency để chịu redelivery/crash.
- Quy tắc giữ thứ tự per partition/per key nếu nghiệp vụ yêu cầu.
- Quy trình xử lý exception từ future, tránh nuốt lỗi trong thread pool.

Các phiên bản Spring Kafka mới có một số cơ chế hỗ trợ asynchronous acknowledgments hoặc listener return types bất đồng bộ, nhưng cần kiểm tra semantics cụ thể. Không gọi `Acknowledgment.acknowledge()` từ thread tùy ý nếu chưa hiểu thread-safety, ordering, commit mode và cơ chế mà container thực sự hỗ trợ.

## 12. `AckMode` và commit offset khi rebalance

Spring Kafka hỗ trợ các acknowledgment modes như `RECORD`, `BATCH`, `MANUAL` và `MANUAL_IMMEDIATE`. Ack mode quyết định khi nào container ghi nhận và commit tiến độ của những record đã xử lý, nhưng **không thay đổi giới hạn giữa hai lần `poll()`**.

| Ack mode | Đặc điểm liên quan tới poll chậm |
|---|---|
| `RECORD` | Commit sau từng record xử lý thành công; nếu listener quá lâu vẫn có thể vượt poll interval |
| `BATCH` | Commit theo batch; một batch lớn chậm làm cửa sổ xử lý chưa commit rộng hơn |
| `MANUAL` | Ứng dụng chỉ định khi nào đã xử lý; commit thực tế còn tùy container semantics |
| `MANUAL_IMMEDIATE` | Có thể commit khi acknowledgment được gọi theo điều kiện của container; không chữa listener blocking |

Khi group generation thay đổi vì rebalance, consumer cũ có thể không còn quyền commit offset cho các partition vừa bị revoke. Một lỗi như `CommitFailedException` xuất hiện **sau khi business method chạy thành công** thường là triệu chứng assignment đã thay đổi, không nhất thiết là commit API bị lỗi độc lập.

Vì vậy, khi thấy `CommitFailedException`, cần xem log rebalance và poll interval **trước đó**, không chỉ tăng retry của offset commit. Nếu partition đã được consumer khác sở hữu, cố lặp lại commit ở member cũ không đảm bảo hợp lệ.

## 13. `ConsumerRebalanceListener` và lifecycle

Khi rebalance xảy ra, partition có thể được revoke khỏi consumer cũ và assigned cho consumer mới. Spring Kafka cho phép ứng dụng tham gia lifecycle này qua `ConsumerAwareRebalanceListener` hoặc các callback tương ứng của container. Những callback này có thể dùng để flush/bàn giao trạng thái in-memory, ghi log assignment hoặc ngăn các work item thuộc partition đã mất quyền tiếp tục ghi side effect.

```java
@Bean("ordersContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersContainerFactory(ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setConsumerRebalanceListener(
            new ConsumerAwareRebalanceListener() {
                @Override
                public void onPartitionsRevokedBeforeCommit(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {
                    // Ghi nhận các partition đang được thu hồi.
                    // Không thực hiện I/O chậm trong callback.
                }

                @Override
                public void onPartitionsAssigned(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {
                    // Khởi tạo trạng thái theo assignment mới nếu cần.
                }
            });

    return factory;
}
```

Đây là ví dụ khái niệm của listener lifecycle; method và callback cụ thể cần phù hợp với phiên bản Spring Kafka. Tránh đặt database transaction kéo dài, HTTP call hoặc xử lý batch nặng bên trong rebalance callback vì bản thân callback chậm có thể tiếp tục kéo dài việc ổn định group.

Rebalance listener **không thay thế** idempotency. Khi revoke partition, một số side effect có thể đã xảy ra trước khi callback được gọi; cần thiết kế để consumer mới xử lý lại an toàn.

## 14. Ảnh hưởng của eager/cooperative rebalance và static membership

Kafka có nhiều chiến lược partition assignment. Với eager rebalance, một lần thay đổi member có thể khiến nhiều partition bị revoke rồi gán lại. Với cooperative incremental rebalance, broker/client có thể thu hồi partition theo từng đợt để giảm gián đoạn. Nhưng nếu một member không đáp ứng yêu cầu poll, assignment của nó vẫn có thể bị thay đổi.

**Cooperative rebalance** giúp giảm phạm vi gián đoạn trong một số topology; nó **không sửa** logic listener chặn quá lâu. **Static membership** với `group.instance.id` giúp hạn chế một số rebalance không cần thiết khi instance khởi động lại ngắn hạn, nhưng không biến một consumer ngừng poll vô hạn thành member khỏe mạnh.

Với static member trong classic protocol, khi vượt `max.poll.interval.ms`, việc gán lại partition có thể bị trì hoãn đến khi hết session timeout thay vì diễn ra ngay. Điều này có thể giúp một restart ngắn tránh mất assignment, nhưng cũng kéo dài khoảng thời gian partition không được xử lý nếu instance thực sự kẹt. Chọn static membership cần cân nhắc pod identity ổn định, rolling deployment và session timeout.

Khi dùng group protocol mới, hành vi heartbeat/session timeout có thể do cấu hình broker quyết định. Không áp dụng máy móc giá trị tuning từ classic protocol mà không xác nhận Kafka client, broker và assignor đang triển khai.

## 15. Monitoring: đo đúng khoảng cách giữa các lần poll

Để phát hiện nguy cơ sớm, cần quan sát **độ trễ của từng vòng consumer**, không chỉ consumer lag tổng thể. Các tín hiệu thường hữu ích:

| Chỉ số hoặc log | Câu hỏi vận hành cần trả lời |
|---|---|
| `time-between-poll-max` (Kafka consumer metric, nếu được xuất) | Khoảng cách lớn nhất giữa các lần `poll()` có tiến gần ngưỡng? |
| `last-poll-seconds-ago` hoặc metric tương đương | Consumer đã lâu không gọi `poll()` đến mức nào? |
| Listener processing duration p95/p99 | Record hoặc batch thực sự xử lý mất bao lâu? |
| `max.poll.interval.ms` thực tế | Ngưỡng đang áp dụng cho consumer là bao nhiêu? |
| Rebalance count/rate, assigned partitions | Partition có bị thu hồi thường xuyên? |
| Offset commit failure / `CommitFailedException` | Commit thất bại sau thay đổi assignment hay vì lý do khác? |
| Consumer lag và oldest unprocessed age | Poll chậm đang gây backlog lớn đến đâu? |
| Database/HTTP timeout, pool waiting, GC pause | Downstream/runtime nào đang giữ consumer thread? |

Tên metric cụ thể tùy Kafka client, Micrometer và cấu hình observation; chỉ sử dụng tên có sẵn sau khi kiểm tra runtime. Thêm tag như application, listener ID, group và topic có thể giúp khoanh vùng, nhưng tránh dùng event ID hoặc offset làm metric label vì cardinality quá cao.

Nên ghi structured log cho một poll/batch hoặc một record có duration, topic, partition, offset, listener/container ID, exception class và downstream dependency. Nếu log chỉ có group ID, khó biết child container nào trong concurrency 6 đang xử lý lâu.

Một dashboard điển hình:

```text
Consumer group: order-worker

max poll interval        300 s
max time between polls   280 s   <-- sát ngưỡng
listener batch p99       245 s
consumer lag             tăng
rebalance rate           tăng
commit failures          xuất hiện

Hướng kiểm tra:
  slow listener / downstream timeout -> poll gap -> rebalance
```

Đây là số liệu giả định để minh họa liên hệ nguyên nhân và hậu quả. Không quy mọi lần rebalance cho poll chậm nếu poll gap không tăng và log member lifecycle chỉ ra nguyên nhân khác.

## 16. Runbook xử lý rebalance do poll chậm

Khi nhận cảnh báo consumer lag, partition assignment thay đổi liên tục và có poll timeout log, nên xử lý theo thứ tự:

1. **Khoanh vùng:** xác định cluster, topic, consumer group, listener ID và partition bị thu hồi.
2. **Xác nhận nguyên nhân:** tìm log poll timeout; đo khoảng cách giữa các lần poll và thời gian chạy listener.
3. **Kiểm tra các dependency:** database lock/query timeout, HTTP timeouts, connection pool, GC pause, CPU throttling và thread starvation.
4. **Phân biệt restart/deploy:** đối chiếu log scaling, rolling deployment, broker/assignment thay đổi để loại trừ rebalance bình thường.
5. **Giảm batch/in-flight:** điều chỉnh `max.poll.records`, số tác vụ đồng thời và giới hạn tải downstream nếu batch quá lớn.
6. **Giới hạn timeout:** đặt hạn mức rõ cho HTTP, SQL và retry; loại bỏ các lời gọi blocking vô hạn.
7. **Tối ưu retry:** chọn backoff phù hợp; với backoff dài xem xét container pause hoặc non-blocking retry nếu ordering cho phép.
8. **Chỉ sau đó cân nhắc tăng `max.poll.interval.ms`:** chọn mức dựa trên p99/worst-case hợp lý và recovery SLO.
9. **Xác minh idempotency:** kiểm tra offset chưa commit có thể được giao lại; không tạo side effect trùng khi rebalance.
10. **Theo dõi sau chỉnh sửa:** poll gap, rebalance rate, commit failure, lag và xử lý thành công phải cùng cải thiện.

Không reset consumer group offset để “hết lag” khi chưa đánh giá dữ liệu chưa xử lý. Reset tiến có thể bỏ qua event; reset lùi có thể làm duplicate. Tương tự, đổi nhóm consumer mới hoặc tăng concurrency đột ngột có thể làm lượng tải lên database tăng và làm lỗi poll chậm tệ hơn.

## 17. Kiểm thử tích hợp: tái hiện poll timeout một cách chủ động

Có thể kiểm thử với một broker Kafka trong Testcontainers và hai consumer instance cùng group để quan sát việc chuyển ownership partition. Chọn khoảng poll interval đủ ngắn cho môi trường test và dùng các side effect giả định có idempotency key.

Kịch bản đơn giản:

1. Tạo topic có một partition và consumer group mới.
2. Cấu hình `max.poll.interval.ms` ở mức test, ví dụ 20 giây; `max.poll.records` đủ nhỏ để dễ quan sát.
3. Listener A nhận một record, chủ động chặn hơn 20 giây bằng latch/test hook.
4. Khởi động consumer B thuộc cùng group; ghi nhận assignment và thời điểm rebalance.
5. Cho listener A kết thúc sau khi vượt poll interval; quan sát offset commit failure nếu tình huống tạo ra lỗi đó.
6. Xác nhận consumer B có thể nhận record chưa commit từ offset bền vững.
7. Xác nhận cùng event ID không tạo hai side effect nghiệp vụ khi A/B cùng chạy nhờ inbox/unique constraint.
8. Giảm thời gian xử lý hoặc `max.poll.records`, chạy lại và quan sát poll/rebalance ổn định.

Nếu dùng static membership, kết quả và thời điểm re-assignment có thể khác do session timeout; bài test phải đặt kỳ vọng theo protocol/member type. Đừng xây kiểm thử chỉ dựa vào thời gian `sleep` cứng nếu có thể dùng synchronization/latch và quan sát sự kiện assignment thực tế.

Một ví dụ minh họa listener dễ gây timeout (chỉ dùng trong test):

```java
@KafkaListener(topics = "orders", groupId = "poll-timeout-test")
public void simulateSlowProcessing(OrderEvent event) {
    testLatch.awaitForProcessingRelease(); // test helper chặn có kiểm soát
    orderService.processIdempotently(event);
}
```

`testLatch` là đối tượng điều khiển từ test harness, không phải API chuẩn Spring Kafka. Trong production không nên sử dụng lời gọi chặn không giới hạn trên consumer thread.

## 18. Bảng quyết định phương án khắc phục

| Nguyên nhân chính | Hướng khắc phục ưu tiên | Cần cảnh giác |
|---|---|---|
| Một poll trả quá nhiều record | Giảm `max.poll.records`, đo processing time | Batch nhỏ làm tăng poll/commit overhead |
| SQL query/lock chậm | Query timeout, index/lock analysis, giảm tranh chấp | Tăng poll interval che giấu database bottleneck |
| HTTP API đôi khi treo | Connect/read timeout, circuit breaker, bounded retries | Retry liên tục có thể làm dependency thêm quá tải |
| Blocking retry/backoff dài | Giới hạn attempts hoặc dùng container-pausing/non-blocking retry phù hợp | Non-blocking retry có thể đổi thứ tự event |
| Listener thực sự cần thời gian dài | Tăng `max.poll.interval.ms` có cơ sở, giảm số record/batch | Member treo có thể giữ partition lâu hơn |
| CPU/GC/thread starvation | Tuning tài nguyên và workload, bounded queue | Tăng concurrency khi thiếu CPU có thể phản tác dụng |
| Async work không được theo dõi | Dùng model async/ack có backpressure và idempotency | Commit sớm gây mất xử lý, commit muộn gây duplicate |
| Rebalance trong rolling deployment | Kiểm tra shutdown, static membership/cooperative assignment | Không phải mọi rebalance là poll timeout |

## 19. Nguyên tắc thiết kế production

Khi triển khai listener Spring Kafka có khả năng xử lý chậm, cần nhớ:

1. `max.poll.interval.ms` đo khoảng thời gian giữa các lần gọi `poll()`, không phải heartbeat timeout.
2. Listener đồng bộ dài, batch lớn và retry blocking có thể làm consumer thread không quay lại `poll()` đúng hạn.
3. Heartbeat vẫn chạy không chứng minh consumer đáp ứng giới hạn poll; static membership chỉ làm khác thời điểm thu hồi partition.
4. Thiết kế thời gian tối đa cho mỗi record/batch, gồm SQL, HTTP, retry, serialization và commit overhead.
5. Giảm `max.poll.records` và đặt timeout cho dependency trước khi nới `max.poll.interval.ms` quá cao.
6. Pause có ích khi container vẫn tiếp tục poll; pause không chữa một callback đang chặn consumer thread vô hạn.
7. Đưa công việc sang async phải có bounded in-flight, xử lý lỗi, acknowledgment đúng và bảo vệ ordering.
8. Khi partition bị revoke, committed offset cũ có thể làm record được giao lại; side effect phải idempotent.
9. Quan sát poll gap, listener duration, rebalance, commit failure, lag và hiệu năng downstream cùng nhau.
10. Kiểm thử mất assignment trong lúc xử lý để chứng minh quy trình phục hồi không gây mất dữ liệu hoặc side effect trùng.

**Kết luận:** rebalance do poll chậm là cơ chế Kafka bảo vệ consumer group khi ứng dụng ngừng thể hiện tiến độ xử lý trong thời gian quá dài. Trong Spring Kafka, nguyên nhân thường nằm ở việc listener hoặc error handler giữ consumer thread lâu hơn ngân sách `max.poll.interval.ms`, không nhất thiết do broker hay heartbeat hỏng. Cách xử lý bền vững là giảm thời gian chặn, kiểm soát batch và retry, duy trì polling đúng cách, đồng thời chấp nhận khả năng redelivery bằng idempotency và đối soát offset.
