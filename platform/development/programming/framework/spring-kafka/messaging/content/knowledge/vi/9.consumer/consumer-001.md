# KafkaConsumer và lifecycle đọc record

`KafkaConsumer` là client dùng để đọc record từ topic Kafka. Consumer không nhận dữ liệu theo kiểu broker chủ động đẩy từng record vào ứng dụng; ứng dụng gọi `poll()` để lấy các record đang có và tiếp tục gọi `poll()` để duy trì tiến độ đọc. Vòng đời này gồm cấu hình, đăng ký topic hoặc partition, poll, xử lý record, xác nhận offset, xử lý rebalance và đóng consumer. Spring Kafka xây dựng trên KafkaConsumer và quản lý vòng lặp này thông qua listener container.

Hiểu đúng lifecycle giúp tránh đọc trùng ngoài ý muốn, mất record do commit sai thời điểm, consumer bị loại khỏi group vì xử lý quá lâu và lỗi do dùng KafkaConsumer từ nhiều thread. Bài viết đi từ API Kafka client cơ bản đến cách Spring Kafka quản lý consumer trong `@KafkaListener`.

## 1. Consumer đọc dữ liệu theo mô hình poll

Producer ghi record vào partition của topic. Mỗi record được gán offset tăng dần trong partition đó. Consumer thuộc một consumer group được gán một hoặc nhiều partition; khi gọi `poll()`, consumer nhận các record tiếp theo từ vị trí đọc hiện tại của những partition đang được gán.

Vòng đời đọc cơ bản:

```text
Tạo KafkaConsumer và cấu hình
          |
          v
subscribe(topic) hoặc assign(partitions)
          |
          v
poll(timeout)
          |
          v
Nhận ConsumerRecords
          |
          v
Xử lý từng ConsumerRecord
          |
          v
Commit offset theo chính sách
          |
          +----------> poll() tiếp theo
          |
          v
close() khi dừng ứng dụng
```

`poll()` trả về một `ConsumerRecords<K, V>`, có thể chứa record từ nhiều partition hoặc rỗng nếu chưa có dữ liệu trong khoảng chờ. Consumer phải gọi poll lặp lại ngay cả khi chưa nhận được record để tiếp tục tham gia hoạt động của consumer group và duy trì tiến độ đọc. Poll cũng là điểm client xử lý các sự kiện điều phối group, bao gồm thay đổi assignment khi rebalance.

Consumer không nên được tạo mới cho từng record. Một consumer thường sống trong suốt thời gian chạy của một worker hoặc listener container, giữ trạng thái assignment, vị trí đọc và kết nối cần thiết. Việc tạo và đóng liên tục làm tăng chi phí kết nối, tham gia group và có thể gây rebalance thường xuyên.

## 2. Cấu hình KafkaConsumer

Một consumer cần tối thiểu bootstrap server, group ID (khi dùng group management), deserializer cho key/value và chính sách offset phù hợp. Ví dụ dùng `Properties`:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-reader");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);
```

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `bootstrap.servers` | Danh sách broker để client khám phá cluster |
| `group.id` | Định danh consumer group khi dùng group management |
| `key.deserializer` | Chuyển byte của key thành kiểu Java |
| `value.deserializer` | Chuyển byte của value thành kiểu Java |
| `enable.auto.commit` | Bật/tắt cơ chế tự động commit offset của client |
| `auto.offset.reset` | Chính sách khi không có offset hợp lệ hoặc offset đã nằm ngoài phạm vi log |
| `max.poll.records` | Số record tối đa trả về trong một lần poll |
| `max.poll.interval.ms` | Giới hạn thời gian giữa các lần poll khi dùng group management |

Deserializer phải tương thích với serializer của producer. Nếu producer ghi JSON nhưng consumer dùng `StringDeserializer`, consumer nhận chuỗi JSON và ứng dụng có thể chuyển chuỗi đó thành object. Nếu dùng JSON deserializer trực tiếp, cần cấu hình type mapping và trusted packages phù hợp với phiên bản Spring Kafka; không nên tin cậy type header từ nguồn không đáng tin.

`group.id` xác định nhóm chia sẻ việc đọc partition. Các consumer có cùng group ID phối hợp để mỗi partition được giao cho tối đa một consumer trong group tại một thời điểm. Consumer không có group ID vẫn có thể đọc dữ liệu bằng cách tự gán partition (`assign`), nhưng không thể commit offset vào consumer group; nếu cần lưu tiến độ, ứng dụng phải tự lưu offset ở nơi khác và seek lại khi khởi động.

## 3. Đăng ký topic bằng subscribe hoặc gán partition bằng assign

### subscribe: để Kafka quản lý assignment

`subscribe()` đăng ký consumer vào một hoặc nhiều topic. Kafka group coordinator và partition assignor phối hợp phân phối partition cho các consumer trong group:

```java
consumer.subscribe(List.of("orders", "payments"));
```

Consumer có thể đăng ký bằng pattern nếu muốn theo dõi các topic khớp tên:

```java
consumer.subscribe(Pattern.compile("orders\\..*"));
```

Khi số consumer thay đổi, topic được thêm partition hoặc thành viên group rời đi, Kafka có thể thực hiện rebalance. Assignment mới được áp dụng cho các consumer liên quan. Đây là lựa chọn phổ biến cho ứng dụng nghiệp vụ vì group có thể tự điều phối partition.

### assign: ứng dụng tự quản lý partition

`assign()` gán trực tiếp partition cho consumer:

```java
TopicPartition partition0 = new TopicPartition("orders", 0);
TopicPartition partition1 = new TopicPartition("orders", 1);
consumer.assign(List.of(partition0, partition1));
```

Khi dùng `assign()`, consumer không tham gia cơ chế group coordination để Kafka tự phân phối partition. Ứng dụng phải tự chịu trách nhiệm tránh hai worker đọc cùng partition ngoài ý muốn, phát hiện thay đổi số partition và xử lý phân công lại. Không gọi `subscribe()` và `assign()` xen kẽ như hai cơ chế đồng thời; mỗi cách thể hiện một chiến lược sở hữu partition khác nhau.

`subscribe()` phù hợp khi cần consumer group tự động chia tải và rebalance. `assign()` phù hợp với tác vụ đọc partition cụ thể, công cụ vận hành hoặc hệ thống có cơ chế phân phối riêng. Việc tự gán partition không tự động mang lại bảo đảm xử lý duy nhất.

## 4. Poll và xử lý ConsumerRecords

Ví dụ vòng lặp đọc cơ bản với Kafka client:

```java
KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
consumer.subscribe(List.of("orders"));

try {
    while (running) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1000));

        for (ConsumerRecord<String, String> record : records) {
            process(record.value());
            log.info("topic={}, partition={}, offset={}, key={}",
                    record.topic(), record.partition(),
                    record.offset(), record.key());
        }

        consumer.commitSync();
    }
} finally {
    consumer.close();
}
```

Ví dụ lược bớt phần khai báo `running`, `process` và import. `poll(Duration)` chờ tối đa khoảng thời gian chỉ định để có dữ liệu; nó có thể trả về sớm khi có record. Giá trị timeout của poll không phải `max.poll.interval.ms`: một giá trị điều khiển thời gian chờ trong lần gọi hiện tại, giá trị còn lại giới hạn khoảng cách giữa các lần poll.

Mỗi `ConsumerRecord` cung cấp thông tin topic, partition, offset, key, value, timestamp và headers. Nên ghi nhận topic/partition/offset trong log khi xử lý lỗi để có thể truy vết record cụ thể. Không nên log toàn bộ payload nếu dữ liệu chứa thông tin nhạy cảm hoặc có kích thước lớn.

`ConsumerRecords` có thể chứa record từ nhiều partition. Khi xử lý tuần tự, consumer xử lý các record theo thứ tự mà iterator trả về; thứ tự có ý nghĩa được bảo đảm trong từng partition, không phải thứ tự toàn cục giữa các partition. Nếu xử lý song song, ứng dụng phải tự bảo đảm thứ tự và commit an toàn theo từng partition.

## 5. Offset và commit

Offset là vị trí của record trong một partition. Consumer có một vị trí đọc (position) cho biết offset tiếp theo sẽ được trả về; group cũng có offset đã commit được lưu bền vững để consumer tiếp tục sau khi restart hoặc rebalance.

Một điểm dễ nhầm: khi xử lý record có offset `42` thành công, offset cần commit thường là `43`, tức vị trí tiếp theo cần đọc. Kafka commit offset tiếp theo chứ không phải offset của record vừa xử lý. Ví dụ:

```text
Partition orders-0:
  offset 40  -> đã xử lý và commit
  offset 41  -> đã xử lý
  offset 42  -> đang xử lý
  offset 43  -> vị trí tiếp theo sau khi xử lý offset 42

Commit offset 43 để lần đọc tiếp theo bắt đầu tại 43.
```

### Auto commit

Khi `enable.auto.commit=true`, Kafka client tự động commit vị trí đọc theo chu kỳ `auto.commit.interval.ms`. Cách này đơn giản nhưng ứng dụng phải hiểu rõ thời điểm commit có thể xảy ra so với thời điểm xử lý nghiệp vụ. Nếu offset được commit trước khi kết quả nghiệp vụ được lưu bền vững, tiến trình có thể gặp sự cố và record bị bỏ qua khi khởi động lại.

### Manual commit

Với `enable.auto.commit=false`, ứng dụng chủ động xác nhận sau khi xử lý. `commitSync()` chờ broker xác nhận commit và thường được dùng trong ví dụ đơn giản. `commitAsync()` không chặn luồng chờ kết quả nhưng cần xử lý callback lỗi và thứ tự commit cẩn thận; một commit cũ hoàn tất muộn có thể ghi đè tiến độ mới nếu ứng dụng tự quản lý sai.

Ví dụ commit đồng bộ sau khi toàn bộ record của poll được xử lý:

```java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(1000));

for (ConsumerRecord<String, String> record : records) {
    processAndPersist(record);
}

consumer.commitSync();
```

Chỉ commit vị trí hiện tại sau khi tất cả record liên quan đã được xử lý thành công. Nếu xử lý một record thất bại và ứng dụng vẫn commit vị trí đã tiến qua record đó, record lỗi có thể bị bỏ qua. Nếu commit thất bại sau khi nghiệp vụ đã hoàn tất, record có thể được đọc lại; vì vậy consumer cần idempotency hoặc cơ chế chống xử lý trùng.

Khi cần commit theo partition, có thể tạo map offset rõ ràng. Offset map cũng phải chứa vị trí tiếp theo:

```java
Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();
offsets.put(new TopicPartition("orders", 0),
        new OffsetAndMetadata(43));
consumer.commitSync(offsets);
```

Đoạn ví dụ commit offset `43` cho partition `orders-0`. Trong ứng dụng thực tế, chỉ tạo map từ những offset đã xử lý bền vững và bảo đảm không commit vượt qua một record chưa hoàn tất ở cùng partition.

## 6. auto.offset.reset không phải chính sách replay tùy ý

`auto.offset.reset` chỉ được áp dụng khi group không có offset đã commit hợp lệ cho partition hoặc offset đã commit không còn nằm trong phạm vi log hiện tại. Các giá trị thường gặp:

| Giá trị | Hành vi |
|---|---|
| `earliest` | Bắt đầu từ offset sớm nhất còn được lưu |
| `latest` | Bắt đầu từ cuối log tại thời điểm cần reset |
| `none` | Ném lỗi nếu không có offset hợp lệ |

Đặt `earliest` không có nghĩa consumer luôn đọc lại toàn bộ lịch sử mỗi lần khởi động. Nếu group đã có committed offset hợp lệ, consumer tiếp tục từ offset đó. Muốn replay, cần dùng group ID mới, reset offset bằng công cụ quản trị phù hợp hoặc chủ động seek về vị trí cần đọc. Việc reset offset đang dùng trong production có thể làm record được xử lý lại hoặc bỏ qua, nên phải đánh giá tác động trước khi thao tác.

## 7. Rebalance và ConsumerRebalanceListener

Rebalance xảy ra khi group cần phân phối lại partition, ví dụ consumer mới tham gia, consumer rời group, partition thay đổi hoặc coordinator cần thực hiện assignment mới. Khi partition bị thu hồi, consumer cần hoàn tất công việc đang làm và lưu offset phù hợp trước khi nhường quyền sở hữu. Sau rebalance, consumer có thể nhận partition khác và tiếp tục từ committed offset.

Kafka client hỗ trợ `ConsumerRebalanceListener` để ứng dụng phản ứng trước và sau khi assignment thay đổi:

```java
consumer.subscribe(List.of("orders"), new ConsumerRebalanceListener() {
    @Override
    public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
        // Commit các offset đã xử lý thành công trước khi nhường partition.
        commitProcessedOffsets(partitions);
    }

    @Override
    public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
        // Khởi tạo trạng thái cần thiết cho các partition vừa nhận.
        log.info("Assigned partitions: {}", partitions);
    }
});
```

`commitProcessedOffsets` là logic ứng dụng, cần chỉ commit offset đã xử lý bền vững. Không commit mù quáng toàn bộ vị trí đọc nếu có record đang xử lý dở. Một số chiến lược rebalance và phiên bản client có thêm callback hoặc khác biệt về thời điểm thu hồi; hãy kiểm tra API đang dùng và thiết kế xử lý theo semantics của group protocol.

Rebalance thường xuyên làm giảm throughput vì consumer phải tạm dừng xử lý, trao đổi assignment và có thể đọc lại record chưa commit. Hãy theo dõi log rebalance, thời gian xử lý listener, consumer lag, số consumer và cấu hình poll. `max.poll.interval.ms` cần đủ lớn cho thời gian xử lý tối đa của một chu kỳ poll, nhưng không nên tăng quá cao để che giấu listener bị treo.

## 8. Lifecycle shutdown và WakeupException

Ứng dụng nên đóng consumer một cách có kiểm soát để giải phóng kết nối, rời group và hoàn tất các tài nguyên nội bộ. `KafkaConsumer` không thread-safe; phần lớn phương thức phải được gọi từ thread sở hữu consumer. `wakeup()` là cơ chế an toàn để một thread khác yêu cầu thread đang poll thoát khỏi vòng lặp.

Ví dụ xử lý tín hiệu dừng:

```java
AtomicBoolean running = new AtomicBoolean(true);
KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);

Thread shutdownHook = new Thread(() -> {
    running.set(false);
    consumer.wakeup();
});
Runtime.getRuntime().addShutdownHook(shutdownHook);

try {
    consumer.subscribe(List.of("orders"));
    while (running.get()) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1000));
        for (ConsumerRecord<String, String> record : records) {
            processAndPersist(record);
        }
        consumer.commitSync();
    }
} catch (WakeupException ex) {
    if (running.get()) {
        throw ex;
    }
} finally {
    consumer.close();
}
```

Đoạn code minh họa nguyên tắc: thread shutdown gọi `wakeup()`, thread sở hữu consumer bắt `WakeupException` và đóng consumer trong `finally`. Trong ứng dụng thật, cần bảo đảm không commit offset của record chưa xử lý xong trong lúc shutdown. `close()` có thể chờ để hoàn tất việc đóng; có thể truyền timeout phù hợp với thời gian dừng mà hệ thống cho phép.

Khi dùng Spring Kafka, không tự tạo shutdown hook cho consumer do container quản lý. Spring quản lý start/stop của listener container theo lifecycle của application context. Hãy cấu hình thời gian graceful shutdown của ứng dụng đủ để listener hoàn tất phần việc đang chạy và container đóng consumer.

## 9. KafkaConsumer không thread-safe

Một instance `KafkaConsumer` chỉ nên được sử dụng bởi một thread tại một thời điểm. Không chia sẻ cùng một consumer giữa nhiều thread để mỗi thread gọi `poll`, `commitSync`, `seek` hoặc `subscribe`. Nếu cần xử lý song song, có thể dùng một trong các cách:

- Tạo nhiều consumer instance, mỗi instance chạy trên thread riêng và tham gia cùng consumer group.
- Một thread poll rồi chuyển record sang worker pool, đồng thời tự quản lý thứ tự xử lý và commit offset theo partition.
- Dùng Spring Kafka concurrency để container tạo và quản lý nhiều consumer.

Mô hình poll một thread rồi dispatch sang worker pool có thể tăng throughput nhưng rất dễ commit vượt qua record chưa xử lý xong. Ví dụ partition có offset 10, 11, 12; nếu worker xử lý offset 12 xong trước 10 và 11, không được commit offset 13 vì khi khởi động lại hai record đầu có thể bị bỏ qua. Cần theo dõi offset liên tục đã xử lý theo từng partition và chỉ commit vị trí kế tiếp của chuỗi liên tục đó.

Nếu cần điều khiển consumer từ thread khác, dùng `wakeup()` để đánh thức thread poll. Không dùng `synchronized` đơn giản để biến KafkaConsumer thành client đa luồng; điều đó không thay đổi các ràng buộc về ownership và lifecycle của consumer.

## 10. Lifecycle consumer trong Spring Kafka

Với Spring Kafka, `@KafkaListener` khai báo phương thức xử lý message. Spring tạo listener container, container tạo và quản lý KafkaConsumer, gọi poll, chuyển record sang listener, xử lý ack/commit và phản ứng với rebalance.

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(topics = "orders", groupId = "order-reader")
    public void onMessage(ConsumerRecord<String, OrderCreated> record) {
        orderService.handle(record.value());
    }
}
```

Khai báo consumer cơ bản trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-reader
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.orders.events
```

Ví dụ này giả định ứng dụng có cấu hình JSON type mapping phù hợp với class `OrderCreated`; trong hệ thống production, nên khai báo type mapping rõ ràng hoặc dùng default type phù hợp thay vì mở trusted packages quá rộng.

Spring Kafka có các kiểu container chính như `KafkaMessageListenerContainer` và `ConcurrentMessageListenerContainer`. Container đầu tiên quản lý một consumer; container concurrent tạo nhiều child container/consumer theo cấu hình concurrency. Số consumer hữu ích bị giới hạn bởi số partition được gán cho group. Nếu có sáu partition và đặt concurrency bằng mười, không thể có mười consumer cùng nhận partition của topic đó trong cùng group; một số consumer sẽ không được gán partition.

### AckMode và xác nhận offset

Spring Kafka quản lý commit theo `AckMode` của listener container. Các chế độ phổ biến:

| AckMode | Ý nghĩa khái quát |
|---|---|
| `RECORD` | Commit sau khi listener xử lý xong từng record trong record listener |
| `BATCH` | Commit sau khi tất cả record của lần poll được xử lý xong |
| `TIME` | Commit khi đã qua khoảng thời gian cấu hình và có record được xử lý |
| `COUNT` | Commit khi đạt số record đã xử lý theo ngưỡng |
| `MANUAL` | Listener gọi acknowledge; container thực hiện commit theo quy tắc của chế độ này |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge được gọi trên consumer thread; ngoài thread có thể được xử lý theo cơ chế trì hoãn của container |

Tên và chi tiết hành vi cần đối chiếu phiên bản Spring Kafka. Khi dùng `enable.auto.commit=false`, mặc định container thường quản lý offset thay cho auto commit của Kafka client. Không bật đồng thời cơ chế tự commit của client nếu chưa hiểu rõ tác động vì có thể commit trước khi listener hoàn thành.

Ví dụ manual acknowledgment:

```java
@KafkaListener(topics = "orders", groupId = "order-reader")
public void onMessage(OrderCreated event, Acknowledgment acknowledgment) {
    orderService.handleAndPersist(event);
    acknowledgment.acknowledge();
}
```

Chỉ gọi `acknowledge()` sau khi nghiệp vụ đã hoàn tất hoặc công việc đã được ghi bền vững theo thiết kế. Nếu listener ném exception, Spring Kafka có thể chuyển lỗi sang error handler/retry policy tùy cấu hình. Cần thiết kế retry, dead-letter và commit cùng nhau để tránh mất record hoặc lặp nghiệp vụ không kiểm soát.

## 11. Các tình huống đọc record thường gặp

| Tình huống | Hành vi cần hiểu |
|---|---|
| Consumer khởi động lần đầu | Dùng `auto.offset.reset` nếu group chưa có offset hợp lệ |
| Consumer restart bình thường | Tiếp tục từ committed offset của group |
| Consumer bị rebalance | Partition có thể được giao cho consumer khác; record chưa commit có thể được đọc lại |
| Poll không có record | `ConsumerRecords` rỗng; tiếp tục poll theo vòng đời bình thường |
| Xử lý thành công nhưng commit thất bại | Record có thể được giao lại; cần xử lý idempotent |
| Commit trước khi lưu nghiệp vụ | Có nguy cơ mất record về mặt xử lý nếu tiến trình gặp sự cố sau commit |
| Consumer xử lý quá lâu | Có thể vượt `max.poll.interval.ms`, rời group và kích hoạt rebalance |
| Nhiều thread cùng gọi một consumer | Không an toàn; cần một thread sở hữu consumer hoặc nhiều consumer instance |

Kafka consumer mặc định phù hợp với mô hình at-least-once khi ứng dụng chỉ commit sau xử lý thành công: record có thể được giao lại nếu commit không thành công hoặc tiến trình dừng ở thời điểm không thuận lợi. Để tránh tác động nghiệp vụ trùng lặp, dùng idempotency key, unique constraint, upsert hoặc transaction ở hệ thống lưu trữ phù hợp. Exactly-once processing qua nhiều hệ thống cần thiết kế transaction và ranh giới nhất quán riêng; commit offset đơn thuần không tạo ra bảo đảm exactly-once cho side effect bên ngoài Kafka.

## 12. Theo dõi và chẩn đoán

Khi consumer đọc chậm hoặc rebalance liên tục, cần theo dõi cả trạng thái Kafka và thời gian xử lý ứng dụng:

- Consumer lag theo group và partition để biết khoảng cách giữa log end offset và committed/current position.
- Số record mỗi poll, thời gian poll và thời gian xử lý từng record/batch.
- Số lần rebalance, partition được revoke/assign và thời gian group ổn định.
- Số lần commit lỗi, thời gian commit và offset đã commit.
- Lỗi deserialize, lỗi nghiệp vụ, retry và dead-letter.
- Consumer bị pause, worker queue bị đầy hoặc downstream DB/HTTP chậm.

Khi kiểm tra thủ công, dùng `kafka-consumer-groups` để xem group, member, partition assignment và lag:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-reader
```

Trước khi thay đổi offset hoặc reset group, hãy xác định rõ record nào sẽ được đọc lại hoặc bỏ qua. Đối với sự cố processing, thường nên tìm nguyên nhân ở listener, dependency và commit strategy trước khi thay đổi offset bằng công cụ quản trị.

## Checklist trước khi đưa consumer vào production

- Consumer có `group.id` và deserializer tương thích với dữ liệu producer.
- Chọn `subscribe()` hay `assign()` đúng với chiến lược quản lý partition.
- Vòng lặp poll tiếp tục chạy và xử lý record trong giới hạn `max.poll.interval.ms`.
- `auto.offset.reset` được hiểu đúng: chỉ áp dụng khi offset không hợp lệ hoặc không tồn tại.
- Offset chỉ được commit sau khi record đã xử lý hoặc lưu bền vững.
- Có idempotency để chịu được record được giao lại.
- Mỗi KafkaConsumer chỉ do một thread sở hữu; shutdown dùng `wakeup()` và `close()` đúng luồng.
- Rebalance listener và logic commit không xác nhận vượt qua record chưa xử lý.
- Spring Kafka container quản lý lifecycle, AckMode, retry và error handler theo cấu hình đã kiểm chứng.
- Có metric cho lag, poll duration, processing duration, commit và rebalance.

Lifecycle của KafkaConsumer là vòng lặp liên tục giữa poll, xử lý và xác nhận offset. Khi hiểu cách consumer tham gia group, nhận partition, duy trì vị trí đọc và đóng đúng cách, ứng dụng Spring Kafka có thể tiêu thụ sự kiện ổn định, phục hồi được sau lỗi và kiểm soát tốt việc xử lý lại record.
