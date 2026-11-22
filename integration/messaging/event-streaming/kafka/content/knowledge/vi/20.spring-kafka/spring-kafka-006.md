# Record listener, batch listener và mức concurrency

## Chọn cách nhận record trong Spring Kafka

Spring Kafka cung cấp hai kiểu listener chính cho `@KafkaListener`:

- **Record listener** nhận và xử lý từng record trong một lần gọi listener. Kiểu này phù hợp khi mỗi event cần validation, xử lý lỗi và ghi nhận kết quả độc lập.
- **Batch listener** nhận nhiều record trong một lần gọi listener, thường là các record được lấy từ một lần `poll()`. Kiểu này phù hợp khi có thể xử lý theo lô, giảm overhead gọi service/database hoặc tận dụng bulk API.

Mức **concurrency** xác định số consumer/container con mà Spring Kafka tạo cho một listener. Mỗi consumer tham gia consumer group và được Kafka phân công partition. Vì vậy, mức song song thực tế bị giới hạn bởi số partition được giao, năng lực downstream và cách ứng dụng xử lý record.

Chọn listener type và concurrency là quyết định ảnh hưởng trực tiếp đến throughput, latency, ordering, memory, offset commit và rebalance. Trong module KAFKA, cần hiểu các yếu tố này để triển khai Java/Spring Kafka ổn định khi lưu lượng tăng hoặc downstream gặp sự cố.

## 1. Record listener hoạt động như thế nào?

### 1.1 Một lần gọi listener cho mỗi record

Với record listener, Spring Kafka gọi method một lần cho từng record được consumer poll và dispatch. Listener có thể nhận payload đã deserialize, key, header hoặc toàn bộ `ConsumerRecord`.

```java
@KafkaListener(
    id = "orders-record-listener",
    topics = "orders",
    groupId = "order-workers",
    concurrency = "3"
)
public void onOrder(ConsumerRecord<String, OrderEvent> record) {
    OrderEvent event = record.value();
    orderService.process(event);

    log.info("Processed topic={}, partition={}, offset={}, key={}",
            record.topic(), record.partition(), record.offset(), record.key());
}
```

Method được gọi riêng cho từng record. Ứng dụng dễ gắn lỗi với một event cụ thể, dễ áp dụng validation và retry theo record. Đổi lại, nếu xử lý từng event có overhead lớn như mở transaction database hoặc gọi remote API, chi phí lặp lại cho từng record có thể cao.

### 1.2 Nhận payload hoặc metadata

Nếu không cần metadata Kafka, listener có thể nhận trực tiếp payload:

```java
@KafkaListener(topics = "orders", groupId = "order-workers")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

Khi cần thông tin như topic, partition, offset, timestamp hoặc key, nhận `ConsumerRecord` hoặc dùng các header của Spring Kafka:

```java
@KafkaListener(topics = "orders", groupId = "order-workers")
public void onOrder(
        OrderEvent event,
        @Header(KafkaHeaders.RECEIVED_KEY) String key,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    orderService.process(event);
    log.info("key={}, partition={}, offset={}", key, partition, offset);
}
```

Tên header và kiểu dữ liệu cần đối chiếu với phiên bản Spring Kafka đang dùng. `ConsumerRecord` là lựa chọn rõ ràng khi cần đầy đủ metadata và không muốn khai báo nhiều tham số header.

### 1.3 Khi nào nên dùng record listener?

Record listener thường phù hợp khi:

- Mỗi event có logic nghiệp vụ riêng hoặc có thể thất bại độc lập.
- Cần retry, DLT hoặc ghi nhận lỗi theo từng record.
- Cần kiểm soát rõ thời điểm xử lý và commit offset.
- Công việc nhẹ, latency thấp quan trọng hơn bulk throughput.
- Cần xử lý tuần tự trong từng partition và dễ quan sát lỗi.

Record listener không có nghĩa Kafka chỉ fetch một record mỗi lần. Consumer vẫn có thể poll một batch gồm nhiều record; Spring Kafka chỉ gọi method riêng cho từng record trong batch đó.

## 2. Batch listener hoạt động như thế nào?

### 2.1 Một lần gọi listener cho nhiều record

Batch listener nhận một tập record trong một lần gọi. Tập record thường được tạo từ kết quả `poll()` của consumer và có thể chứa record từ nhiều partition mà consumer đang sở hữu.

Để dùng batch listener, cấu hình `ConcurrentKafkaListenerContainerFactory` với `setBatchListener(true)`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> batchFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(3);
        factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.BATCH);
        return factory;
    }
}
```

Listener chỉ định factory này:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-workers",
    containerFactory = "batchFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    List<OrderEvent> events = records.stream()
            .map(ConsumerRecord::value)
            .toList();

    orderService.processBatch(events);
}
```

`setBatchListener(true)` khiến container chuyển sang chế độ batch. Một batch không nhất thiết có đúng số record bằng `max.poll.records`; nó có thể nhỏ hơn khi traffic thưa, fetch chưa có đủ dữ liệu hoặc partition được giao có ít record.

### 2.2 Nhận metadata của batch

Nhận `List<ConsumerRecord<K,V>>` giúp truy cập metadata của từng record. Nếu chỉ nhận `List<OrderEvent>`, method tập trung vào payload nhưng ít thông tin hơn về partition và offset.

Batch listener cũng có thể nhận `ConsumerRecords<K,V>` trong những trường hợp cần thao tác theo partition. Dù dùng kiểu tham số nào, hãy nhớ một batch có thể chứa nhiều partition và không tạo ra thứ tự toàn cục giữa các partition.

### 2.3 Batch giúp giảm overhead như thế nào?

Giả sử mỗi event cần ghi vào database. Record listener có thể gọi một lệnh insert cho mỗi event. Batch listener có thể gom 100 event rồi gọi `batchInsert()` một lần, giảm số lần round-trip và tận dụng bulk insert.

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-workers",
    containerFactory = "batchFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    List<OrderEvent> events = records.stream()
            .map(ConsumerRecord::value)
            .toList();

    orderRepository.insertAll(events);
}
```

Batch listener có thể tăng throughput nếu downstream hỗ trợ bulk operation. Nếu service vẫn xử lý từng event tuần tự bên trong vòng lặp, lợi ích có thể chỉ đến từ giảm overhead dispatch và gom transaction; cần benchmark trước khi kết luận batch nhanh hơn.

## 3. So sánh record listener và batch listener

| Tiêu chí | Record listener | Batch listener |
|---|---|---|
| Số lần gọi method | Một lần cho mỗi record | Một lần cho một batch được poll |
| Đơn vị xử lý | Record | Danh sách/tập record |
| Xử lý lỗi | Dễ xác định record lỗi | Cần xác định record/index lỗi hoặc xử lý lại batch |
| Bulk database/API | Phải tự gom dữ liệu | Thuận tiện gom và gửi bulk |
| Latency | Có thể xử lý ngay từng record | Có thể chờ gom batch và xử lý cả lô |
| Memory ứng dụng | Thường giữ ít record trong mỗi lần xử lý | Giữ nhiều payload cùng lúc |
| Offset commit | Có thể commit theo record hoặc theo batch tùy AckMode | Thường commit sau khi xử lý batch; `RECORD` không hỗ trợ cho batch listener |
| Ordering | Dễ xử lý tuần tự từng partition | Cần giữ thứ tự trong từng partition khi xử lý batch/parallel |
| Phù hợp | Event độc lập, latency thấp, lỗi theo record | Bulk processing, throughput cao, downstream hỗ trợ batch |

Không có kiểu listener tốt nhất cho mọi topic. Hãy chọn dựa trên yêu cầu latency, khả năng bulk của downstream, mức độ độc lập giữa record và độ phức tạp của xử lý lỗi.

## 4. Concurrency trong Spring Kafka

### 4.1 Concurrency tạo nhiều consumer instance

Spring Kafka dùng `ConcurrentMessageListenerContainer` để quản lý nhiều `KafkaMessageListenerContainer` con. Mỗi container con sở hữu một Kafka consumer và thực thi listener trên luồng consumer riêng.

Ví dụ:

```java
factory.setConcurrency(3);
```

Spring tạo tối đa ba consumer cho listener đó. Các consumer dùng cùng `group.id`, vì vậy Kafka group coordinator phân phối partition giữa chúng. Concurrency không tạo thêm partition và cũng không làm một partition được nhiều consumer trong cùng group đọc đồng thời.

```mermaid
flowchart TB
    L[@KafkaListener: orders] --> C[ConcurrentMessageListenerContainer]
    C --> C1[Child container 1\nKafka consumer 1]
    C --> C2[Child container 2\nKafka consumer 2]
    C --> C3[Child container 3\nKafka consumer 3]
    C1 --> P1[Assigned partitions]
    C2 --> P2[Assigned partitions]
    C3 --> P3[Assigned partitions]
```

### 4.2 Số partition giới hạn mức song song

Giả sử topic có 6 partition và listener có concurrency 3. Kafka có thể phân phối khoảng 2 partition cho mỗi consumer, tùy assignor và các topic khác mà group đang subscribe.

Nếu concurrency là 8 nhưng topic chỉ có 3 partition, tối đa chỉ 3 consumer có partition để xử lý topic đó; các consumer còn lại có thể idle. Tăng concurrency vượt số partition không làm tăng throughput của topic.

| Số partition được group phân phối | Concurrency | Mức song song tối đa theo partition |
|---:|---:|---:|
| 3 | 1 | 1 consumer xử lý 3 partition |
| 6 | 3 | Tối đa 3 consumer cùng xử lý |
| 6 | 6 | Tối đa 6 consumer, thường một partition mỗi consumer |
| 3 | 8 | Tối đa 3 consumer có việc; phần còn lại idle |
| 12 | 4 | Tối đa 4 consumer, trung bình khoảng 3 partition mỗi consumer |

Số partition cần tính theo tổng partition được giao trong group, không chỉ số partition của một topic nếu listener subscribe nhiều topic.

### 4.3 Cấu hình concurrency ở đâu?

Có thể đặt concurrency tại factory:

```java
factory.setConcurrency(4);
```

Hoặc đặt trực tiếp trên listener:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-workers",
    concurrency = "4"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

Giá trị trên annotation có thể ghi đè concurrency mặc định của factory cho endpoint đó. Trong Spring Boot, có thể đặt concurrency mặc định bằng `spring.kafka.listener.concurrency`; với từng listener cần khác biệt, dùng thuộc tính `concurrency` của `@KafkaListener` hoặc factory riêng.

### 4.4 Concurrency với assignment tường minh

Khi listener dùng `topics` hoặc `topicPattern`, các consumer tham gia group và Kafka assignor phân phối partition. Khi dùng `topicPartitions`, ứng dụng chỉ định partition rõ ràng; Spring Kafka phân chia các partition đó cho child container theo cấu hình concurrency. Nếu số partition ít hơn concurrency, số consumer hoạt động thực tế có thể bị giới hạn theo số partition được chỉ định.

Không nhầm concurrency của listener với số partition. Nếu cần tăng song song, phải đánh giá cả partition count, key distribution, consumer capacity và downstream throughput.

## 5. Concurrency, ordering và partition

### 5.1 Kafka chỉ bảo đảm thứ tự trong một partition

Kafka bảo đảm thứ tự record trong từng partition. Trong cùng consumer group, một partition được giao cho tối đa một consumer member tại một thời điểm. Do đó, record listener xử lý tuần tự trên consumer thread có thể giữ thứ tự partition một cách tự nhiên.

Không có thứ tự tổng thể giữa các partition. Khi concurrency lớn hơn 1, các partition được xử lý song song và thời điểm hoàn tất giữa chúng có thể khác nhau.

### 5.2 Batch có thể chứa nhiều partition

Một batch có thể chứa record từ nhiều partition. Không nên giả định toàn bộ danh sách batch là một chuỗi nghiệp vụ có thứ tự toàn cục. Nếu ordering quan trọng theo `orderId`, hãy bảo đảm producer dùng `orderId` làm key để các event của cùng order đi vào cùng partition, rồi xử lý tuần tự theo partition.

Khi xử lý batch bằng worker pool, không phân tán record cùng partition theo cách cho phép record sau hoàn tất trước record trước nếu nghiệp vụ yêu cầu ordering. Có thể chia batch theo partition và xử lý tuần tự từng nhóm, đồng thời chạy các nhóm partition khác nhau song song.

### 5.3 Tăng concurrency không tăng ordering guarantee

Tăng concurrency giúp xử lý nhiều partition đồng thời, nhưng không biến topic thành một luồng có thứ tự toàn cục. Nếu cần xử lý tất cả event theo một thứ tự duy nhất, phải dùng một partition hoặc xây dựng cơ chế sequence/coordination riêng; một partition duy nhất sẽ giới hạn throughput.

## 6. Offset commit và AckMode

Spring Kafka listener container quản lý commit offset thông qua `AckMode`. Khi sử dụng container, thông thường nên để container quản lý commit và tắt auto commit của Kafka client.

### 6.1 Các AckMode thường gặp

| AckMode | Hành vi |
|---|---|
| `RECORD` | Commit sau khi mỗi record được listener xử lý thành công; chỉ dành cho record listener |
| `BATCH` | Commit sau khi tất cả record trong batch do một lần poll trả về đã được xử lý thành công |
| `TIME` | Commit khi đủ khoảng thời gian cấu hình và các điều kiện xử lý batch phù hợp |
| `COUNT` | Commit khi đạt số record đã xử lý theo ngưỡng |
| `COUNT_TIME` | Kết hợp ngưỡng số record và thời gian |
| `MANUAL` | Listener gọi `acknowledge()`; container xử lý commit theo batch/chu kỳ phù hợp |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge trên consumer thread; nếu gọi từ thread khác, hành vi có thể được xếp hàng tùy ngữ cảnh |

Với batch listener, `AckMode.RECORD` không được hỗ trợ vì method nhận và xử lý một batch như đơn vị. Thông thường dùng `BATCH` hoặc manual acknowledgment theo yêu cầu.

### 6.2 Record listener với manual acknowledgment

```java
@KafkaListener(topics = "orders", groupId = "order-workers")
public void onOrder(OrderEvent event, Acknowledgment acknowledgment) {
    orderService.process(event);
    acknowledgment.acknowledge();
}
```

Ví dụ này cần cấu hình container với `AckMode.MANUAL` hoặc `MANUAL_IMMEDIATE` và `enable.auto.commit=false`. Chỉ acknowledge sau khi side effect nghiệp vụ hoàn tất. Nếu acknowledge trước khi database commit, ứng dụng có thể bỏ qua record sau restart dù dữ liệu chưa được lưu.

### 6.3 Batch listener với manual acknowledgment

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-workers",
    containerFactory = "batchFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records,
        Acknowledgment acknowledgment) {

    List<OrderEvent> events = records.stream()
            .map(ConsumerRecord::value)
            .toList();

    orderService.processBatch(events);
    acknowledgment.acknowledge();
}
```

Trong ví dụ này, acknowledgment xác nhận batch sau khi `processBatch()` thành công. Nếu batch xử lý một phần rồi lỗi, không acknowledge toàn bộ batch; hãy dùng cơ chế batch error handling để chỉ ra record lỗi hoặc thiết kế xử lý idempotent để có thể retry batch.

### 6.4 Không commit vượt qua record chưa hoàn tất

Nếu ứng dụng xử lý record bất đồng bộ, offset commit phải phản ánh chuỗi record liên tục đã hoàn tất theo từng partition. Ví dụ offset 12 chưa xử lý xong nhưng offset 13 đã xong; commit offset 14 có thể khiến lần đọc sau bỏ qua offset 12. Dùng worker coordination và completion tracking để chỉ acknowledge tiến độ an toàn.

## 7. Error handling cho record listener và batch listener

### 7.1 Record listener

Với record listener, `DefaultErrorHandler` xử lý exception của từng record. Có thể cấu hình số lần retry, backoff và recoverer để chuyển record sang DLT sau khi hết retry.

```java
@Bean
DefaultErrorHandler recordErrorHandler(DeadLetterPublishingRecoverer recoverer) {
    FixedBackOff backOff = new FixedBackOff(1000L, 3L);
    return new DefaultErrorHandler(recoverer, backOff);
}
```

Ví dụ này dùng khoảng nghỉ cố định 1 giây và tối đa 3 lần retry sau lần xử lý ban đầu. Hãy phân loại exception không retry được, giới hạn tổng thời gian và bảo đảm publish DLT thành công trước khi tiến độ offset được xác nhận.

### 7.2 Batch listener cần xác định record lỗi

Nếu một record trong batch thất bại, ứng dụng nên chỉ rõ index của record đó bằng `BatchListenerFailedException`. Spring Kafka có thể xử lý các record trước index lỗi và retry/recover phần còn lại theo cấu hình error handler.

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-workers",
    containerFactory = "batchFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int i = 0; i < records.size(); i++) {
        try {
            orderService.process(records.get(i).value());
        } catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Cannot process order at batch index " + i,
                    exception,
                    i
            );
        }
    }
}
```

Khi không xác định được index lỗi, container có thể phải retry toàn bộ batch theo fallback behavior. Điều đó làm record đã xử lý thành công có thể được xử lý lại; downstream cần idempotent.

### 7.3 Non-blocking retry và batch listener

Spring Kafka `@RetryableTopic` hỗ trợ non-blocking retry bằng retry topics cho nhiều trường hợp record listener, nhưng không hỗ trợ batch listener. Nếu cần retry topic, hãy dùng record listener hoặc thiết kế pipeline tách batch thành record có metadata retry rõ ràng.

Nếu yêu cầu xử lý batch, có thể dùng blocking retry có giới hạn, batch error handler, hoặc tự chuyển các record lỗi sang retry/DLT bằng một quy trình bảo đảm offset và side effect nhất quán.

## 8. Điều chỉnh batch size và poll interval

### 8.1 `max.poll.records`

`max.poll.records` giới hạn số record tối đa trả về trong một lần `poll()`. Với batch listener, nó là một trong các yếu tố ảnh hưởng kích thước batch. Với record listener, nó vẫn ảnh hưởng số record mà consumer lấy về mỗi poll, dù listener method được gọi từng record.

Batch lớn có thể tăng hiệu quả bulk nhưng cũng:

- Tăng heap cần thiết để giữ payload đã deserialize.
- Tăng thời gian xử lý một lần gọi listener.
- Tăng thời gian trước khi consumer gọi `poll()` tiếp theo.
- Tăng phạm vi record có thể được xử lý lại nếu batch thất bại.

### 8.2 `max.poll.interval.ms`

Nếu thời gian xử lý batch vượt `max.poll.interval.ms`, consumer có thể bị xem là không còn tiến triển và group có thể rebalance. Tổng thời gian xử lý cần tính cả retry blocking, database/API call và thời gian GC.

Không chỉ tăng `max.poll.interval.ms` để che giấu batch quá lớn. Hãy đo p95/p99 processing time, giảm `max.poll.records`, giới hạn downstream concurrency hoặc chuyển retry dài sang retry topic nếu phù hợp.

### 8.3 Fetch size và bộ nhớ

`fetch.max.bytes` và `max.partition.fetch.bytes` ảnh hưởng lượng dữ liệu consumer fetch từ broker. Kích thước thực tế còn phụ thuộc record batch và partition. Khi tăng batch, hãy theo dõi heap, GC pause và queue depth; không đặt giới hạn quá thấp so với batch hợp lệ của producer.

## 9. Cấu hình Spring Boot

Ví dụ cấu hình listener dạng record với concurrency mặc định 3:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-workers
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
    listener:
      type: single
      concurrency: 3
      ack-mode: record
```

Để dùng batch listener mặc định cho factory được Spring Boot auto-configure, có thể đổi `spring.kafka.listener.type` thành `batch` và chọn `ack-mode` phù hợp. Nếu cùng ứng dụng có cả record và batch listener, nên khai báo hai `ConcurrentKafkaListenerContainerFactory` riêng để tránh cấu hình toàn cục gây nhầm lẫn.

Khi cần factory riêng, cấu hình rõ ràng trong Java:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> recordFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {
    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> batchFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {
    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(3);
    factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.BATCH);
    return factory;
}
```

Nếu cả hai listener cùng cần đọc toàn bộ topic độc lập, dùng group ID riêng. Nếu cùng group ID, chúng chia partition với nhau và mỗi partition chỉ thuộc một consumer member tại một thời điểm; hãy chắc chắn đây là ý định thiết kế.

## 10. Cách chọn concurrency theo workload

### 10.1 Tính theo partition trước

Bắt đầu từ số partition và số consumer member dự kiến. Nếu topic có 12 partition, concurrency 3 tạo tối đa 3 consumer hoạt động với khoảng 4 partition mỗi consumer; concurrency 12 có thể tạo 12 consumer với một partition mỗi consumer. Phân bố thực tế phụ thuộc assignor và subscription của group.

### 10.2 Tính theo năng lực downstream

Nếu mỗi listener gọi database, concurrency phải phù hợp connection pool và năng lực query. Ví dụ database chỉ cấp 20 connection cho service, không nên tạo 100 listener thread cùng lúc truy vấn database mà không có giới hạn riêng.

Đặt giới hạn đồng thời cho dependency, dùng connection pool có kích thước hợp lý và bounded worker queue. Concurrency Kafka cao hơn không làm database xử lý nhanh hơn nếu database là bottleneck.

### 10.3 Đo trước khi tăng

Theo dõi các chỉ số:

- Consumer lag theo partition và tốc độ lag giảm/tăng.
- Records consumed/second và processing latency p95/p99.
- Số consumer member có assignment và số partition trên mỗi member.
- Rebalance count/duration và lỗi heartbeat/poll interval.
- CPU, heap, GC pause, thread count và queue depth.
- Database connection pool, query latency, lock wait.
- Retry rate, DLT rate và lỗi deserialize.

Tăng concurrency từng bước. Nếu throughput không tăng nhưng CPU, context switching hoặc downstream latency tăng, hãy giảm concurrency hoặc tối ưu xử lý thay vì tiếp tục scale.

## 11. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nghĩ record listener nghĩa là consumer poll từng record | Hiểu sai batching ở Kafka client | Phân biệt poll batch với cách Spring gọi method |
| Bật batch listener nhưng method nhận sai kiểu | Lỗi chuyển đổi hoặc listener invocation | Dùng `List<T>`, `List<ConsumerRecord<K,V>>` hoặc kiểu batch được hỗ trợ |
| Đặt concurrency lớn hơn partition count | Có consumer idle, không tăng throughput | Chọn concurrency dựa trên partition được giao |
| Tăng concurrency vượt connection pool | Database/API quá tải | Giới hạn concurrency downstream và worker |
| Batch quá lớn | Heap tăng, xử lý lâu, vượt poll interval | Giảm `max.poll.records`, đo p99 |
| Dùng `AckMode.RECORD` với batch listener | Cấu hình không được hỗ trợ | Dùng `BATCH` hoặc manual acknowledgment |
| Acknowledge trước khi side effect hoàn tất | Có thể mất record sau restart | Ack sau khi xử lý thành công |
| Xử lý song song cùng partition không kiểm soát | Record hoàn tất sai thứ tự, commit vượt offset | Tuần tự theo partition và theo dõi contiguous offset |
| Batch lỗi nhưng không xác định index | Có thể retry cả batch, tạo duplicate | Ném `BatchListenerFailedException` với index phù hợp |
| Dùng `@RetryableTopic` cho batch listener | Không tương thích với batch listener | Dùng record listener hoặc blocking/batch retry phù hợp |
| Hai listener cần nhận độc lập nhưng dùng chung group ID | Chia partition thay vì mỗi listener nhận toàn bộ event | Dùng group ID riêng cho từng workload |

## 12. Checklist production

- Chọn record hay batch listener theo latency, bulk capability và cách xử lý lỗi.
- Factory của record/batch listener được cấu hình rõ ràng.
- Concurrency không vượt nhu cầu partition và năng lực downstream.
- Đã kiểm tra assignment thực tế sau khi group ổn định.
- `max.poll.records` và `max.poll.interval.ms` phù hợp p99 processing time.
- `AckMode` phù hợp listener type; batch listener không dùng `RECORD`.
- Auto commit được tắt khi container quản lý acknowledgment/commit.
- Side effect hoàn tất trước khi acknowledge/commit offset.
- Batch error handler xác định record lỗi hoặc chấp nhận retry batch với idempotency.
- Ordering được bảo đảm theo partition/key; không giả định thứ tự toàn cục.
- Worker queue, database connection và downstream concurrency có giới hạn.
- Dashboard theo dõi lag, processing latency, rebalance, heap, retry và DLT.
- Đã thử nghiệm tăng/giảm concurrency, batch lỗi giữa chừng, downstream chậm và consumer restart trong staging.

## Kết luận

Record listener gọi method cho từng record và phù hợp với xử lý độc lập, latency thấp cùng error handling theo record. Batch listener gọi method với nhiều record từ một lần poll, phù hợp khi downstream hỗ trợ bulk operation và có thể xử lý batch như một đơn vị. Concurrency tạo nhiều consumer trong cùng group, nhưng số partition được giao và năng lực downstream mới quyết định mức song song hữu ích.

Khi triển khai Spring Kafka, hãy cấu hình factory và AckMode đúng listener type, giới hạn `max.poll.records` theo heap và thời gian xử lý, rồi chọn concurrency dựa trên partition count và downstream capacity. Giữ ordering trong từng partition, xử lý batch failure có chủ đích và chỉ commit offset sau side effect thành công. Đo consumer lag, p99 latency, rebalance và tài nguyên trước khi tăng concurrency để đạt throughput ổn định mà không làm hệ thống phụ thuộc quá tải.
