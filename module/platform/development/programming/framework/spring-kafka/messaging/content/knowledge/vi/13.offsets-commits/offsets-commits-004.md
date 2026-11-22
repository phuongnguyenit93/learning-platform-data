# Commit theo record và theo batch

## 1. Vì sao cần chọn chiến lược commit?

Kafka consumer đọc record từ các partition theo offset. Sau khi ứng dụng xử lý dữ liệu, consumer group cần lưu lại vị trí có thể tiếp tục đọc trong lần chạy tiếp theo. Thao tác lưu vị trí này gọi là **commit offset**.

Ứng dụng có thể commit sau từng record hoặc sau khi xử lý xong một nhóm record được trả về từ một lần `poll()`. Hai cách này tạo ra sự cân bằng khác nhau giữa thông lượng, chi phí commit và phạm vi record có thể được giao lại khi ứng dụng gặp sự cố.

- **Commit theo record**: xác nhận tiến độ ngay sau khi từng record được xử lý thành công. Nếu record tiếp theo lỗi, những record trước đã commit có thể không cần đọc lại.
- **Commit theo batch**: xử lý toàn bộ record của một lần poll rồi mới xác nhận tiến độ của các partition tương ứng. Cách này giảm số lần commit nhưng có thể khiến nhiều record đã xử lý bị giao lại nếu ứng dụng dừng trước khi commit.

Commit offset không đồng nghĩa Kafka biết database hay nghiệp vụ đã hoàn tất. Ứng dụng cần đặt commit sau ranh giới xử lý thành công và thiết kế consumer chịu được việc record được giao lại.

## 2. Offset được commit là vị trí kế tiếp cần đọc

Kafka lưu offset kế tiếp mà consumer group cần đọc, không phải offset của record cuối cùng đã xử lý.

Ví dụ, consumer xử lý thành công record có offset `40`, sau đó commit `41`:

```text
Record đã xử lý:  offset 40
Committed offset: 41
Lần đọc tiếp:     bắt đầu từ offset 41
```

Nếu consumer xử lý các record `40`, `41`, `42` trong một batch và tất cả thành công, vị trí commit tiếp theo thường là `43`. Offset được quản lý độc lập theo từng topic-partition; offset `43` của `orders-0` không liên quan đến offset `43` của `orders-1`.

Offset có thể có khoảng trống do log compaction, transaction marker hoặc record không được trả về theo isolation level. Vì vậy, không nên lấy số record quan sát được để thay thế cho offset thực tế.

## 3. Commit theo từng record trong Kafka Consumer API

Với Kafka Java Consumer thuần, ứng dụng có thể tắt auto-commit, xử lý từng record rồi commit offset kế tiếp của partition đó.

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders"));

    while (true) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1_000));

        for (TopicPartition partition : records.partitions()) {
            for (ConsumerRecord<String, String> record : records.records(partition)) {
                processBusiness(record);

                // Commit offset kế tiếp của partition sau khi record thành công.
                consumer.commitSync(Map.of(
                        partition,
                        new OffsetAndMetadata(record.offset() + 1)));
            }
        }
    }
}
```

Với mỗi record, ứng dụng thực hiện nghiệp vụ trước rồi commit `record.offset() + 1`. Nếu `processBusiness()` ném lỗi, lệnh commit cho record đó không chạy; sau khi consumer khởi động lại hoặc partition được giao lại, record có thể được đọc lại.

Ví dụ trên commit đồng bộ sau từng record nên dễ quan sát nhưng tạo nhiều round-trip commit. Trong hệ thống có throughput cao, chi phí này có thể đáng kể. Ngoài ra, nếu một poll chứa record của nhiều partition, cần theo dõi tiến độ riêng cho từng partition; không commit một offset của partition này cho partition khác.

## 4. Commit theo batch trong Kafka Consumer API

Nếu ứng dụng chỉ commit sau khi toàn bộ record trong lần poll đã xử lý thành công, có thể gọi `commitSync()` sau vòng lặp:

```java
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders"));

    while (true) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1_000));

        for (ConsumerRecord<String, String> record : records) {
            processBusiness(record);
        }

        // Chỉ commit sau khi mọi record trong poll đã xử lý thành công.
        consumer.commitSync();
    }
}
```

`commitSync()` không truyền map sẽ commit các vị trí hiện tại mà consumer đã đọc trên những partition được gán. Vì vậy, chỉ gọi ở cuối batch khi tất cả record trong poll đã hoàn tất. Nếu một record lỗi giữa vòng lặp, chương trình thoát khỏi vòng xử lý trước khi commit; batch có thể được giao lại từ committed offset cũ.

Điều này tạo khả năng xử lý lặp: các record đầu batch có thể đã cập nhật database thành công trước khi một record sau đó lỗi. Consumer nên idempotent, ví dụ lưu `eventId` đã xử lý với ràng buộc duy nhất hoặc dùng khóa nghiệp vụ để thao tác lặp không tạo thêm tác dụng phụ.

### Commit map offset tường minh

Khi muốn kiểm soát chính xác partition và vị trí commit, có thể truyền map `TopicPartition` → `OffsetAndMetadata`:

```java
Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

for (TopicPartition partition : records.partitions()) {
    List<ConsumerRecord<String, String>> partitionRecords =
            records.records(partition);

    for (ConsumerRecord<String, String> record : partitionRecords) {
        processBusiness(record);
    }

    if (!partitionRecords.isEmpty()) {
        long nextOffset = partitionRecords
                .get(partitionRecords.size() - 1)
                .offset() + 1;
        offsets.put(partition, new OffsetAndMetadata(nextOffset));
    }
}

if (!offsets.isEmpty()) {
    consumer.commitSync(offsets);
}
```

Đoạn mã xử lý tuần tự các record trong từng partition và chỉ thêm offset cuối cùng đã xử lý thành công vào map. Nếu một record trong partition lỗi, vòng lặp ném exception trước khi partition đó được thêm vào map; những partition đã xử lý trước có thể được commit nếu ứng dụng bắt và xử lý lỗi theo thiết kế riêng. Ví dụ trên không bắt exception để đơn giản hóa luồng chính.

Khi tự quản lý offset, chỉ commit đến offset liên tục đã xử lý thành công trong mỗi partition. Không commit vượt qua một record còn đang xử lý hoặc đã lỗi.

## 5. commitSync() và commitAsync()

Kafka Consumer cung cấp hai cách gửi yêu cầu commit:

| API | Hành vi | Đánh đổi |
|---|---|---|
| `commitSync()` | Gửi yêu cầu commit và chờ broker trả kết quả | Dễ biết commit thành công hay lỗi; luồng consumer phải chờ |
| `commitAsync()` | Gửi yêu cầu commit và không chờ kết quả ngay | Giảm thời gian chặn nhưng cần xử lý callback và thứ tự các lần commit |

Ví dụ commit bất đồng bộ:

```java
consumer.commitAsync((offsets, exception) -> {
    if (exception != null) {
        log.error("Offset commit failed: {}", offsets, exception);
        return;
    }

    log.debug("Offset committed: {}", offsets);
});
```

`commitAsync()` trả quyền điều khiển ngay cho luồng gọi. Nếu nhiều commit bất đồng bộ đang chờ, callback có thể hoàn tất theo thứ tự khác với kỳ vọng của ứng dụng tùy tình huống. Không nên gửi một commit cũ sau commit mới theo cách làm lùi tiến độ group. Khi cần đóng consumer hoặc xử lý ranh giới rebalance, `commitSync()` thường được dùng để chờ hoàn tất commit cuối cùng.

`commitAsync()` không tự tăng độ tin cậy. Nếu callback báo lỗi, ứng dụng cần quyết định cách xử lý; bỏ qua lỗi có thể khiến group khôi phục từ committed offset cũ và đọc lại record.

## 6. Commit theo record trong Spring Kafka

Khi dùng `@KafkaListener`, listener container quản lý `KafkaConsumer`, vòng lặp poll và commit offset. Ứng dụng chọn chiến lược qua `ContainerProperties.AckMode` hoặc cấu hình Spring Boot `spring.kafka.listener.ack-mode`.

`AckMode.RECORD` yêu cầu container commit sau khi listener xử lý thành công từng record. Nếu listener ném exception, commit cho record đó không được thực hiện theo luồng thành công; error handler quyết định retry hoặc recovery.

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
    listener:
      ack-mode: record
```

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(topics = "orders")
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
```

Trong cấu hình này, mỗi lần `onOrder()` hoàn tất thành công, container có thể commit tiến độ của record đó theo `RECORD`. Đây là cách phù hợp khi muốn giảm phạm vi record có thể bị phát lại nếu một record sau đó lỗi.

Từ Spring Kafka 2.3, framework tự đặt `enable.auto.commit=false` nếu ứng dụng chưa cấu hình rõ thuộc tính này. Điều đó cho phép listener container quản lý commit theo AckMode. Không nên bật Kafka client auto-commit cùng lúc nếu mục tiêu là kiểm soát commit theo kết quả listener.

## 7. Commit theo batch trong Spring Kafka

`AckMode.BATCH` là chế độ mặc định phổ biến của listener container. Container commit offset sau khi tất cả record nhận được từ một lần poll đã được xử lý thành công.

Với record listener, phương thức vẫn được gọi một lần cho mỗi record, nhưng container đợi xử lý xong toàn bộ batch poll trước khi commit. Với batch listener, phương thức nhận một danh sách record và thường xử lý danh sách như một đơn vị; sau khi listener hoàn tất thành công, container commit offset của batch.

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
```

Ví dụ batch listener:

```java
@Component
public class OrderBatchListener {

    private final OrderService orderService;

    public OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "batchKafkaListenerContainerFactory")
    public void onOrders(List<OrderCreated> events) {
        orderService.processBatch(events);
    }
}
```

Factory được dùng cho endpoint cần bật batch mode:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
batchKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.BATCH);
    return factory;
}
```

Kích thước batch không cố định. `max.poll.records` giới hạn số record tối đa trả về trong một lần poll; số thực tế có thể thấp hơn do lượng dữ liệu, fetch settings và số partition được gán. Batch poll cũng có thể chứa record từ nhiều partition, mỗi partition có offset riêng.

`AckMode.RECORD` không được hỗ trợ cho batch listener vì phương thức nhận một nhóm record như một lần gọi. Nếu cần xác nhận một phần batch, phải dùng cơ chế manual acknowledgment phù hợp phiên bản và bảo đảm không commit vượt qua record chưa xử lý.

## 8. So sánh commit theo record và batch trong Spring Kafka

| Tiêu chí | `AckMode.RECORD` | `AckMode.BATCH` |
|---|---|---|
| Thời điểm commit | Sau từng lần listener xử lý thành công một record | Sau khi tất cả record của một lần poll được xử lý thành công |
| Đơn vị xử lý listener | Record listener | Record listener hoặc batch listener |
| Số lần commit | Có thể nhiều hơn, phụ thuộc số record | Thường ít hơn, theo batch poll |
| Thông lượng | Có thể thấp hơn do commit thường xuyên | Có thể cao hơn nhờ giảm chi phí commit |
| Phạm vi phát lại khi lỗi | Thường hẹp hơn, gần record lỗi | Có thể gồm các record trước đó trong batch chưa được commit |
| Cách dùng | Khi cần tiến độ commit sát từng record | Khi muốn cân bằng throughput và commit |
| Batch listener | Không hỗ trợ | Là lựa chọn tự nhiên cho xử lý batch |

Ví dụ poll trả về các record offset `10`, `11`, `12` của cùng partition:

```text
RECORD:
  xử lý 10 ── commit 11
  xử lý 11 ── commit 12
  xử lý 12 ── commit 13

BATCH:
  xử lý 10 ── xử lý 11 ── xử lý 12 ── commit 13
```

Nếu xử lý offset `12` thất bại sau khi `10` và `11` đã hoàn tất:

- Với `RECORD`, tiến độ đã commit có thể ở `12`, nên khi retry consumer tiếp tục từ record lỗi theo cơ chế error handler.
- Với `BATCH`, commit cuối batch chưa diễn ra; các record `10` và `11` có thể được giao lại cùng record `12`.

Trong cả hai trường hợp, hành vi thực tế còn phụ thuộc error handler, recovery, transaction và AckMode. Vì vậy, handler nên idempotent ngay cả khi dùng `RECORD`.

## 9. Manual acknowledgment khi cần tự quyết định commit

Nếu listener cần quyết định thời điểm xác nhận sau một điều kiện nghiệp vụ cụ thể, có thể dùng `MANUAL` hoặc `MANUAL_IMMEDIATE` và nhận `Acknowledgment`.

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
manualListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.MANUAL);
    return factory;
}
```

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "manualListenerFactory")
public void onOrder(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.process(event);
    acknowledgment.acknowledge();
}
```

`MANUAL` đưa yêu cầu acknowledge vào cơ chế commit theo batch của container. `MANUAL_IMMEDIATE` commit ngay nếu `acknowledge()` được gọi trên consumer thread. Với record listener, hãy chỉ acknowledge sau khi thao tác nghiệp vụ hoàn tất; với batch listener, chỉ acknowledge sau khi phần batch mà ứng dụng xác nhận đã xử lý an toàn.

Manual acknowledgment không tạo exactly-once cho database. Nếu database commit thành công nhưng process dừng trước khi offset Kafka được commit, record có thể được giao lại. Vẫn cần idempotency hoặc thiết kế outbox/inbox phù hợp.

## 10. Lỗi trong batch và BatchListenerFailedException

Với batch listener, nếu một record lỗi, ứng dụng có thể ném `BatchListenerFailedException` để chỉ rõ record hoặc index gây lỗi. `DefaultErrorHandler` có thể dùng thông tin này để xử lý các record trước đó và retry/recover từ vị trí lỗi theo cấu hình.

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        try {
            orderService.process(record.value());
        } catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Failed to process order event", exception, record);
        }
    }
}
```

Nếu listener ném exception mà không xác định được record lỗi, error handler có thể phải retry cả batch theo chiến lược fallback. Khi xử lý bulk trong database, cần quyết định transaction database có rollback toàn batch hay không; nếu một phần batch đã commit độc lập, retry có thể lặp lại tác dụng phụ.

Với record listener dùng `AckMode.BATCH`, exception ở một record cũng có thể ngăn commit batch poll. `DefaultErrorHandler` và cấu hình ack sẽ quyết định cách seek, retry và commit phần đã xử lý. Không nên suy luận rằng chỉ cần listener xử lý xong một record là offset đã được commit nếu AckMode đang là `BATCH`.

## 11. Ảnh hưởng của commit đến at-most-once và at-least-once

Thời điểm commit so với thời điểm xử lý nghiệp vụ quyết định nguy cơ mất record hoặc xử lý lặp:

### At-most-once

Commit offset thành công trước khi xử lý nghiệp vụ. Nếu process dừng sau commit nhưng trước khi xử lý xong, Kafka sẽ tiếp tục từ offset sau record đó và record chưa hoàn tất có thể bị bỏ qua. Nếu commit thất bại, ứng dụng không nên tiếp tục xử lý rồi coi đó là at-most-once. Cách này giảm khả năng xử lý lặp nhưng chấp nhận nguy cơ mất xử lý.

### At-least-once

Xử lý nghiệp vụ thành công rồi mới commit. Nếu process dừng sau xử lý nhưng trước commit, record có thể được giao lại. Cách này tránh bỏ qua record chưa hoàn tất nhưng yêu cầu consumer idempotent.

### Exactly-once trong Kafka

Commit theo record hoặc batch không tự tạo exactly-once. Với luồng consume-transform-produce giữa các topic Kafka, Kafka transaction có thể phối hợp output record và offset input trong cùng transaction. Consumer downstream dùng `isolation.level=read_committed` để chỉ đọc dữ liệu transaction đã commit.

Nếu listener cập nhật database hoặc gọi API ngoài Kafka, Kafka transaction không tự tạo transaction ACID chung với hệ thống bên ngoài. Cần outbox/inbox, transaction database hoặc idempotency để bảo đảm kết quả nghiệp vụ.

| Mục tiêu | Trình tự điển hình | Rủi ro |
|---|---|---|
| At-most-once | Commit rồi xử lý | Có thể mất xử lý nếu dừng sau commit |
| At-least-once | Xử lý rồi commit | Có thể xử lý lặp nếu dừng trước commit |
| Exactly-once trong Kafka | Ghi output và offset trong Kafka transaction | Cần cấu hình transaction/isolation đúng; không tự bao gồm database hoặc API ngoài Kafka |

## 12. Các AckMode khác ngoài RECORD và BATCH

Spring Kafka còn hỗ trợ các chế độ commit theo ngưỡng:

| AckMode | Hành vi khái quát |
|---|---|
| `TIME` | Commit các offset đã xử lý khi đạt khoảng thời gian cấu hình |
| `COUNT` | Commit khi đạt số lượng record đã xử lý cấu hình |
| `COUNT_TIME` | Commit khi đạt ngưỡng thời gian hoặc số lượng record |
| `MANUAL` | Listener gọi `acknowledge()`; container xử lý commit theo cơ chế manual/batch |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge được gọi trên consumer thread |

`TIME`, `COUNT` và `COUNT_TIME` vẫn không cho phép commit vượt qua record chưa xử lý. Chúng điều chỉnh tần suất commit các offset đã hoàn tất, không thay thế việc xác định ranh giới nghiệp vụ thành công.

Mặc định listener container thường dùng `BATCH`. Spring Kafka cũng tự tắt Kafka client auto-commit nếu ứng dụng không cấu hình rõ `enable.auto.commit`, để tránh hai cơ chế commit cùng điều khiển tiến độ.

## 13. Theo dõi và kiểm tra committed offset

Có thể dùng Kafka CLI để xem committed offset và lag của group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
```

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| `CURRENT-OFFSET` | Committed offset của group và partition |
| `LOG-END-OFFSET` | End offset được dùng để so sánh tiến độ |
| `LAG` | Khoảng cách giữa end offset và committed offset |
| `CONSUMER-ID` | Consumer member đang được gán partition, nếu có |

Nếu consumer đã poll và xử lý record nhưng chưa commit, `CURRENT-OFFSET` vẫn có thể thấp hơn position runtime. Do đó, lag hiển thị ở CLI có thể lớn hơn lượng record thực sự chưa được listener poll. Cần đọc committed offset cùng position, throughput và trạng thái xử lý để chẩn đoán.

Theo dõi thêm:

- Commit latency và commit failure.
- Consumer lag theo từng partition.
- Số lần retry và record chuyển sang DLT.
- Thời gian xử lý listener và thời gian giữa các lần poll.
- Rebalance, partition revoked/assigned và lỗi broker/network.

## 14. Kiểm thử commit theo record và batch

Kiểm thử nên xác minh cả committed offset lẫn tác dụng phụ nghiệp vụ, không chỉ kiểm tra listener đã được gọi.

Các kịch bản nên có:

1. **Record thành công:** với `AckMode.RECORD`, gửi nhiều record và xác nhận committed offset tiến sau từng lần xử lý thành công.
2. **Batch thành công:** với `AckMode.BATCH`, gửi nhiều record trong một poll và xác nhận commit sau khi batch hoàn tất.
3. **Record lỗi giữa poll:** làm một record lỗi sau khi các record trước đã xử lý; so sánh phạm vi redelivery giữa RECORD và BATCH.
4. **Manual acknowledgment:** xác nhận offset chưa commit trước `acknowledge()` và được commit theo chế độ đã chọn sau lời gọi.
5. **Restart trước commit:** dừng consumer sau khi nghiệp vụ hoàn tất nhưng trước commit, sau đó xác nhận record có thể được giao lại và handler không tạo side effect trùng.
6. **Nhiều partition:** xác nhận offset được commit độc lập cho từng partition và không commit vượt qua record chưa xử lý.
7. **Commit lỗi:** mô phỏng lỗi broker hoặc rebalance để xác nhận ứng dụng quan sát lỗi commit và có hành vi phục hồi phù hợp.
8. **Batch failure:** ném `BatchListenerFailedException` tại một record và xác nhận retry/recovery theo error handler.

Có thể dùng `spring-kafka-test` hoặc Kafka test starter phù hợp với dòng Spring Boot. Với rebalance, lỗi mạng và transaction, nên bổ sung kiểm thử với broker/container gần môi trường triển khai.

## 15. Chọn chiến lược nào?

| Nhu cầu | Chiến lược khởi đầu | Lý do |
|---|---|---|
| Mỗi sự kiện là một đơn vị độc lập, muốn commit sát từng record | Record listener + `AckMode.RECORD` | Thu hẹp phạm vi record có thể bị phát lại khi lỗi |
| Ưu tiên thông lượng và xử lý theo lô | Batch listener + `AckMode.BATCH` | Giảm số lần commit và tận dụng bulk processing |
| Muốn record listener nhưng gom commit theo poll | Record listener + `AckMode.BATCH` | Listener vẫn nhận từng record; container chỉ commit sau khi poll batch hoàn tất |
| Nghiệp vụ cần quyết định thời điểm xác nhận | `MANUAL` hoặc `MANUAL_IMMEDIATE` | Listener chủ động acknowledge sau điều kiện xử lý |
| Consume-transform-produce cần atomic trong Kafka | Kafka transaction và offset gửi trong transaction | Kết hợp output record và tiến độ input trong cùng transaction Kafka |

Không có lựa chọn tối ưu cho mọi workload. Hãy đo throughput, commit latency, processing time và redelivery khi lỗi. Nếu downstream là database, bảo đảm tính idempotent hoặc dùng outbox/inbox trước khi tăng mức song song hay giảm tần suất commit.

## 16. Tổng kết

- Commit offset là lưu vị trí kế tiếp cần đọc cho từng consumer group và partition.
- Commit theo record xác nhận sau từng record; commit theo batch xác nhận sau khi xử lý xong các record của một lần poll.
- Kafka Consumer API hỗ trợ `commitSync()` và `commitAsync()`; ứng dụng phải commit offset kế tiếp, không phải offset record cuối cùng.
- Spring Kafka dùng `AckMode.RECORD` và `AckMode.BATCH` để listener container quản lý commit; `BATCH` là mặc định phổ biến.
- Batch commit giảm số lần commit nhưng có thể làm nhiều record đã xử lý bị giao lại khi batch chưa commit.
- Manual acknowledgment cho phép listener chủ động xác nhận, nhưng không tạo transaction nguyên tử với database.
- At-least-once thường yêu cầu consumer idempotent; exactly-once cần Kafka transaction trong phạm vi Kafka và thiết kế riêng cho side effect ngoài Kafka.
- Kiểm thử phải xác minh committed offset, redelivery và kết quả nghiệp vụ trong các tình huống lỗi/restart.

Khi hiểu rõ commit theo record và theo batch, đội ngũ có thể chọn ranh giới xác nhận phù hợp cho listener Spring Kafka, cân bằng chi phí commit với phạm vi phát lại và xây dựng consumer đáng tin cậy khi ứng dụng hoặc broker gặp sự cố.
