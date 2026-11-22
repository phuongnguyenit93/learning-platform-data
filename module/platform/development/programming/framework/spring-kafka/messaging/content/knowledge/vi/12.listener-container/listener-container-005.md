# Record listener và batch listener

## 1. Hai cách nhận record trong Spring Kafka

Spring Kafka cung cấp hai kiểu listener phổ biến cho `@KafkaListener`:

- **Record listener**: phương thức listener được gọi cho từng record. Nếu một lần `poll()` trả về nhiều record, container lần lượt gọi phương thức cho từng record.
- **Batch listener**: phương thức listener được gọi một lần với một nhóm record mà consumer nhận từ một lần `poll()`.

Hai kiểu listener dùng chung Kafka consumer và listener container. Khác biệt chính nằm ở đơn vị dữ liệu mà phương thức ứng dụng nhận và cách ứng dụng xử lý lỗi, commit offset, metadata cũng như thông lượng.

Ví dụ topic `orders` có ba partition. Một lần `poll()` có thể trả về record từ cả ba partition:

```text
KafkaConsumer.poll()
       |
       +── orders-0: offset 10, 11
       +── orders-1: offset 20
       +── orders-2: offset 35, 36
       |
       +── Record listener: gọi listener 5 lần, mỗi lần 1 record
       |
       +── Batch listener: gọi listener 1 lần với nhóm 5 record
```

Batch ở đây là tập record consumer nhận được từ lần poll đó. Nó không nhất thiết chứa cùng số record ở mọi lần gọi, không nhất thiết chỉ thuộc một partition và không tự tạo một transaction nguyên tử.

## 2. Record listener hoạt động như thế nào?

Record listener nhận một record trong mỗi lần gọi phương thức. Đây là cách đơn giản và phổ biến khi mỗi sự kiện là một đơn vị nghiệp vụ độc lập.

```java
@Component
public class OrderRecordListener {

    private final OrderService orderService;

    public OrderRecordListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "recordKafkaListenerContainerFactory")
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
```

Container poll record từ Kafka, deserialize và chuyển payload thành `OrderCreated`, sau đó gọi `onOrder()` cho từng record. Nếu poll trả về 100 record, listener có thể được gọi 100 lần. Việc poll vẫn có thể lấy nhiều record trong một request; record listener không có nghĩa mỗi record cần một request mạng riêng.

### Nhận ConsumerRecord để truy cập metadata

Nếu cần key, topic, partition, offset, timestamp hoặc header gốc, listener có thể nhận `ConsumerRecord`:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "recordKafkaListenerContainerFactory")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    OrderCreated event = record.value();

    log.info("Received eventId={}, topic={}, partition={}, offset={}, key={}",
            event.eventId(), record.topic(), record.partition(),
            record.offset(), record.key());

    orderService.process(event);
}
```

Hoặc nhận payload cùng các header cần thiết:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(
        OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    log.info("Received {}, {}-{} at offset {}",
            event.orderId(), topic, partition, offset);
    orderService.process(event);
}
```

`ConsumerRecord` phù hợp khi cần nhiều metadata hoặc muốn truy cập trực tiếp headers của Kafka. Cách nhận payload và `@Header` gọn hơn khi nghiệp vụ chỉ cần một số thông tin vận chuyển.

## 3. Batch listener hoạt động như thế nào?

Batch listener nhận một danh sách record trong một lần gọi. Để bật batch mode, cấu hình listener container factory với `setBatchListener(true)`.

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(3);
        return factory;
    }
}
```

Khai báo listener nhận danh sách payload:

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

Container chuyển các record đã poll thành danh sách payload rồi gọi `onOrders()` một lần. Ứng dụng có thể xử lý cả danh sách bằng một thao tác batch, ví dụ ghi nhiều dòng vào database trong một lần hoặc gọi một API hỗ trợ bulk.

### Nhận ConsumerRecord trong batch

Khi cần metadata riêng của từng record, có thể nhận danh sách `ConsumerRecord`:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        log.info("topic={}, partition={}, offset={}, key={}",
                record.topic(), record.partition(),
                record.offset(), record.key());
        orderService.process(record.value());
    }
}
```

Một batch có thể chứa record từ nhiều partition. Offset chỉ có ý nghĩa trong từng partition; không so sánh offset của hai partition như một thứ tự toàn cục. Kafka giữ thứ tự trong từng partition, nhưng không bảo đảm thứ tự tổng thể giữa các partition.

Spring Kafka cũng hỗ trợ kiểu `ConsumerRecords<K, V>` cho batch listener khi ứng dụng muốn làm việc trực tiếp với cấu trúc kết quả poll được nhóm theo topic-partition. Chọn kiểu tham số theo mức metadata mà nghiệp vụ cần.

## 4. Cấu hình hai kiểu listener

Một ứng dụng có thể khai báo hai factory riêng để tránh nhầm kiểu listener:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    recordKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(false); // Record listener
        factory.setConcurrency(3);
        return factory;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true); // Batch listener
        factory.setConcurrency(3);
        return factory;
    }
}
```

Gắn đúng factory vào từng `@KafkaListener`:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "recordKafkaListenerContainerFactory")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}

@KafkaListener(
        topics = "orders-archive",
        groupId = "archive-service",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onArchiveBatch(List<OrderCreated> events) {
    archiveService.storeBatch(events);
}
```

Ví dụ rút gọn hai phương thức trên có thể nằm trong các bean listener riêng. Factory mặc định do Spring Boot auto-configuration tạo thường là record listener; nếu cần batch mode, hãy tạo factory batch riêng hoặc cấu hình factory được sử dụng một cách tường minh. Không truyền một phương thức nhận `List<T>` vào factory record listener và kỳ vọng container tự chuyển sang batch mode.

## 5. Kích thước batch do đâu quyết định?

Batch listener nhận số record mà `poll()` trả về trong lần gọi đó. Thuộc tính `max.poll.records` đặt giới hạn số record tối đa được trả về trong một lần poll; nó không bảo đảm lần nào cũng nhận đủ số lượng này.

Ví dụ cấu hình:

```yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
      properties:
        max.poll.interval.ms: 300000
```

`max-poll-records: 200` giới hạn tối đa 200 record trong một lần poll của consumer. Batch thực tế có thể ít hơn do lượng dữ liệu hiện có, tốc độ producer, giới hạn fetch, kích thước record và số partition được gán.

Một số thuộc tính khác cũng ảnh hưởng lượng dữ liệu được fetch:

| Thuộc tính | Vai trò |
|---|---|
| `max.poll.records` | Giới hạn số record tối đa trả về từ một lần `poll()` |
| `fetch.max.bytes` | Giới hạn tổng lượng dữ liệu fetch trong một request ở mức cấu hình consumer |
| `max.partition.fetch.bytes` | Giới hạn dữ liệu fetch cho mỗi partition trong một request, với một số ngoại lệ để consumer có thể tiến triển |
| `fetch.min.bytes` | Lượng dữ liệu tối thiểu broker cố gắng gom trước khi trả fetch response |
| `fetch.max.wait.ms` | Thời gian broker tối đa chờ để đáp ứng `fetch.min.bytes` trước khi trả response |

Không nên tăng `max.poll.records` chỉ để batch lớn hơn. Batch quá lớn có thể tăng bộ nhớ, thời gian xử lý một lần poll và nguy cơ vượt `max.poll.interval.ms`. Batch quá nhỏ có thể làm giảm hiệu quả bulk và tăng số lần gọi listener.

## 6. So sánh record listener và batch listener

| Tiêu chí | Record listener | Batch listener |
|---|---|---|
| Đơn vị gọi phương thức | Một record mỗi lần gọi | Một danh sách/nhóm record mỗi lần gọi |
| Cách khai báo | Tham số payload hoặc `ConsumerRecord` | `List<T>`, danh sách `ConsumerRecord` hoặc `ConsumerRecords` |
| Cấu hình factory | `setBatchListener(false)` hoặc mặc định | `setBatchListener(true)` |
| Xử lý nghiệp vụ | Từng sự kiện độc lập | Có thể xử lý nhiều sự kiện trong một thao tác bulk |
| Metadata | Có sẵn trên `ConsumerRecord` hoặc header của record | Có thể lấy metadata từng record qua `ConsumerRecord` hoặc header dạng danh sách |
| Lỗi | Dễ xác định record gây lỗi vì mỗi lần gọi xử lý một record | Cần xác định record lỗi trong batch hoặc chấp nhận retry cả batch |
| Commit | Có thể commit sau từng record với `AckMode.RECORD` | Thường commit theo batch; `AckMode.RECORD` không áp dụng cho batch listener |
| Thông lượng | Dễ tối ưu theo từng record, có thể có overhead gọi listener lớn | Có thể tăng throughput khi xử lý bulk, giảm overhead cho từng record |
| Độ trễ | Có thể xử lý ngay từng record | Có thể chờ đủ dữ liệu hoặc fetch response trước khi xử lý batch |
| Bộ nhớ | Thường giữ phạm vi xử lý nhỏ hơn | Cần bộ nhớ cho toàn bộ batch và các đối tượng chuyển đổi |

Record listener thường dễ hiểu, dễ retry theo record và phù hợp với nghiệp vụ có quy tắc xử lý riêng từng sự kiện. Batch listener hữu ích khi downstream hỗ trợ bulk hoặc chi phí mỗi lần gọi lớn, nhưng cần thiết kế cẩn thận cho lỗi từng phần, commit và thứ tự.

## 7. AckMode và thời điểm commit offset

Kiểu listener và AckMode là hai cấu hình khác nhau. Record listener không đồng nghĩa luôn commit từng record; batch listener cũng không đồng nghĩa tự động có transaction.

Với record listener:

- `AckMode.RECORD`: container commit sau khi listener xử lý thành công từng record.
- `AckMode.BATCH`: container commit sau khi xử lý thành công tất cả record nhận được từ một lần poll. Đây là chế độ mặc định phổ biến của listener container.
- `MANUAL` hoặc `MANUAL_IMMEDIATE`: listener chủ động gọi `Acknowledgment.acknowledge()` theo cấu hình.

Với batch listener, `AckMode.BATCH` phù hợp với đơn vị xử lý cả batch. `AckMode.RECORD` không được hỗ trợ vì phương thức listener nhận và xử lý một batch như một đơn vị. Nếu dùng manual acknowledgment, cần gọi acknowledge sau khi điều kiện xử lý của batch hoặc phần batch tương ứng đã hoàn tất.

Ví dụ batch listener với manual acknowledgment:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "manualBatchListenerFactory")
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records,
        Acknowledgment acknowledgment) {

    orderService.processBatch(records.stream()
            .map(ConsumerRecord::value)
            .toList());

    acknowledgment.acknowledge();
}
```

Factory tương ứng có thể đặt `ContainerProperties.AckMode.MANUAL`. Nếu xử lý batch thất bại và phương thức ném exception trước `acknowledge()`, offset chưa được xác nhận theo lời gọi manual đó và error handler sẽ quyết định retry/recovery.

Từ Spring Kafka 3.0.10, batch listener có thể dùng `Acknowledgment.acknowledge(index)` để xác nhận một phần batch trong điều kiện cấu hình phù hợp, cụ thể là `MANUAL_IMMEDIATE` và lời gọi trên consumer thread. Đây là API nâng cao, phụ thuộc phiên bản; cần đọc tài liệu đúng phiên bản và kiểm thử thứ tự offset trước khi áp dụng.

## 8. Xử lý lỗi với record listener

Với record listener, exception thường gắn trực tiếp với một record cụ thể. `DefaultErrorHandler` có thể retry record lỗi với backoff, sau đó phục hồi hoặc chuyển record sang dead-letter topic thông qua recoverer.

Ví dụ cấu hình minh họa:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    var backOff = new FixedBackOff(1_000L, 2L);
    return new DefaultErrorHandler(recoverer, backOff);
}
```

Ví dụ này cấu hình hai lần retry sau lần xử lý đầu tiên, mỗi lần cách nhau một giây. Sau khi hết retry, recoverer gửi record đến DLT theo quy tắc định tuyến mặc định hoặc cấu hình riêng. Cần cấu hình serializer và topic DLT phù hợp với payload, headers và kiểu dữ liệu có thể gặp.

Khi xử lý record listener, nên phân loại exception: lỗi tạm thời có thể retry; lỗi dữ liệu không hợp lệ thường cần chuyển DLT hoặc xử lý nghiệp vụ riêng. Handler vẫn nên idempotent vì record có thể được giao lại sau restart hoặc trước khi commit.

## 9. Xử lý lỗi với batch listener

Batch listener nhận nhiều record trong một lần gọi nên khi phương thức ném exception, container cần biết record nào trong batch gây lỗi để quyết định phần nào đã xử lý và phần nào cần retry.

Với `DefaultErrorHandler`, batch listener có thể ném `BatchListenerFailedException` để chỉ ra record hoặc index gây lỗi. Khi xác định được record lỗi, container có thể xử lý các record đứng trước theo tiến độ phù hợp và retry/recover từ record lỗi cùng các record còn lại. Nếu listener ném exception không xác định được record lỗi, chiến lược fallback có thể retry lại toàn bộ batch.

Ví dụ xử lý từng record trong batch và đánh dấu record lỗi:

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

Ví dụ dùng `BatchListenerFailedException` để thông báo record lỗi cho error handler. Hành vi commit/retry/recover cụ thể phụ thuộc cấu hình `DefaultErrorHandler`, AckMode và phiên bản Spring Kafka. Nếu listener xử lý cả batch bằng một câu lệnh bulk, có thể khó xác định record lỗi; khi đó cần thiết kế transaction database hoặc bước kiểm tra dữ liệu để xác định lỗi từng phần.

Batch listener không làm cho các record từ nhiều partition trở thành một đơn vị transaction. Nếu một batch chứa record từ `orders-0` và `orders-1`, offset vẫn được quản lý riêng cho từng partition. Một lỗi có thể làm một phần record bị giao lại; các thao tác nghiệp vụ phải chịu được retry.

## 10. Ordering và xử lý song song

Kafka bảo đảm thứ tự trong một partition. Record listener được gọi từng record; batch listener nhận một tập record có thể đến từ nhiều partition. Trong cả hai trường hợp, không có thứ tự toàn cục giữa các partition.

Nếu cùng `orderId` được gửi bằng cùng key và định tuyến vào cùng partition, record của đơn hàng đó có thứ tự append trong partition. Tuy nhiên:

- Batch có thể chứa record từ nhiều partition; không suy luận thứ tự nghiệp vụ bằng cách so sánh offset giữa các partition.
- Nếu ứng dụng xử lý các phần tử trong batch bằng parallel stream hoặc executor, thứ tự hoàn tất có thể khác thứ tự nhận.
- Nếu xử lý bất đồng bộ, chỉ commit offset liên tục đã hoàn tất trong từng partition; không commit vượt qua record còn đang xử lý.
- Tăng concurrency tạo thêm consumer trong group nhưng không cho phép hai consumer cùng xử lý một partition đồng thời theo assignment thông thường.

Với nghiệp vụ cần thứ tự theo entity, hãy giữ key ổn định, xử lý tuần tự trong partition hoặc xây dựng cơ chế tuần tự hóa theo key. Không dùng batch hoặc parallel processing nếu chưa có chiến lược bảo vệ ordering và commit.

## 11. Chọn record listener hay batch listener?

Chọn record listener khi mỗi sự kiện cần xử lý độc lập, muốn xác định lỗi và retry theo từng record, hoặc cần xử lý ngay khi record được poll. Đây thường là lựa chọn dễ bắt đầu cho consumer nghiệp vụ.

Chọn batch listener khi hệ thống nhận hỗ trợ xử lý nhiều bản ghi trong một lần gọi, chẳng hạn bulk insert, bulk API, tính toán theo lô hoặc giảm overhead chuyển đổi/call stack. Batch listener đặc biệt hữu ích khi hiệu quả xử lý tăng đáng kể theo kích thước lô.

Trước khi chọn batch, hãy cân nhắc:

1. Downstream có API bulk hoặc transaction phù hợp không?
2. Nếu một record lỗi, có thể xác định và xử lý phần còn lại không?
3. Batch tối đa cần bao nhiêu bộ nhớ?
4. Thời gian xử lý batch có nằm trong `max.poll.interval.ms` không?
5. Có cần giữ thứ tự theo partition hoặc key không?
6. AckMode và error handler có phản ánh đúng ranh giới xử lý thành công không?

Không chọn batch chỉ vì muốn tăng số record mỗi lần listener được gọi. Nếu bottleneck nằm ở một partition nóng, database chậm hoặc downstream không hỗ trợ bulk, batch lớn có thể làm tăng latency và thời gian retry mà không cải thiện throughput.

## 12. Kiểm thử hai kiểu listener

Kiểm thử tích hợp nên dùng topic có nhiều partition và record có key khác nhau để xác minh hành vi thực tế.

Các kịch bản hữu ích:

1. **Record listener:** gửi ba record và xác nhận phương thức được gọi ba lần, mỗi lần nhận một payload.
2. **Batch listener:** cấu hình batch factory, gửi nhiều record và xác nhận listener nhận danh sách; không giả định mọi lần poll đều đủ `max.poll.records`.
3. **Metadata:** xác nhận topic, partition, offset và key đúng khi nhận `ConsumerRecord` hoặc headers.
4. **Nhiều partition:** gửi record vào nhiều partition và xác nhận batch có thể chứa record từ nhiều partition.
5. **AckMode:** kiểm tra committed offset với `RECORD`, `BATCH` và manual acknowledgment.
6. **Lỗi record:** làm một record lỗi, xác nhận `DefaultErrorHandler` retry/recover theo cấu hình.
7. **Lỗi batch:** ném `BatchListenerFailedException` tại record xác định và kiểm tra phần record trước/sau theo chính sách retry.
8. **Batch timeout:** tạo batch xử lý lâu để kiểm tra `max.poll.interval.ms`, rebalance và consumer lag.
9. **Redelivery:** dừng consumer trước commit và xác nhận handler idempotent khi record được giao lại.

Có thể dùng `spring-kafka-test` hoặc Kafka test starter tương ứng với phiên bản Spring Boot. Với rebalance, timeout, transaction và tải lớn, nên kiểm thử thêm với broker/container gần môi trường triển khai.

## 13. Tổng kết

- Record listener gọi phương thức một lần cho mỗi record; batch listener gọi một lần với một nhóm record từ `poll()`.
- Record listener phù hợp với xử lý từng sự kiện và retry theo record; batch listener hữu ích khi downstream hỗ trợ bulk.
- Bật batch listener bằng `setBatchListener(true)` trên listener container factory và chỉ rõ factory ở `@KafkaListener`.
- Batch size chịu ảnh hưởng bởi `max.poll.records`, fetch settings và lượng dữ liệu hiện có; nó không phải kích thước cố định.
- Record listener và batch listener có thể dùng AckMode khác nhau; `AckMode.RECORD` không áp dụng cho batch listener.
- Batch listener cần chiến lược lỗi rõ ràng; `BatchListenerFailedException` giúp xác định record gây lỗi cho `DefaultErrorHandler`.
- Batch không đồng nghĩa với transaction nguyên tử và không tạo thứ tự toàn cục giữa partition.
- Cần kiểm soát `max.poll.interval.ms`, bộ nhớ, retry, ordering và idempotency khi xử lý batch lớn.

Khi hiểu rõ đơn vị nhận dữ liệu và cách container quản lý poll, offset, lỗi, ứng dụng Spring Kafka có thể chọn record listener hoặc batch listener phù hợp với đặc tính nghiệp vụ và mục tiêu throughput.
