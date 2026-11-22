# AckMode COUNT trong Spring Kafka

Trong Spring Kafka, **AckMode COUNT** cho phép listener container commit consumer offset sau khi đã xử lý đủ một số lượng record được cấu hình. Thay vì commit sau từng record hoặc đợi hết một poll batch, container tích lũy số record đã xử lý rồi commit các offset đang chờ khi đạt ngưỡng ackCount.

Cách này giúp cân bằng giữa chi phí commit và độ trễ xác nhận offset. Commit ít thường xuyên hơn có thể giảm overhead khi throughput cao, nhưng cũng làm tăng số record có khả năng được đọc lại nếu consumer dừng đột ngột trước lần commit tiếp theo. Vì vậy, COUNT cần được chọn cùng với acknowledgement mode, retry/error handler, concurrency, tần suất record và khả năng xử lý duplicate của nghiệp vụ.

## 1. Offset và acknowledgement trong listener container

Kafka lưu offset theo từng partition. Consumer group commit offset để ghi nhận vị trí tiếp theo cần đọc trong partition đó. Nếu ứng dụng đã xử lý record có offset 41 và commit thành công offset 42, lần khởi động sau consumer group có thể tiếp tục từ vị trí 42.

Một listener container của Spring Kafka quản lý quá trình poll, gọi listener, ghi nhận tiến độ và commit offset. Khi listener xử lý record thành công, container có thể đưa vị trí đã xử lý vào tập offset đang chờ commit. AckMode quyết định thời điểm container gửi các offset này về Kafka.

~~~text
Topic orders, partition 0
  offset 40 --> record A
  offset 41 --> record B
  offset 42 --> record C
  offset 43 --> record D
                  |
                  v
        Spring Kafka listener
                  |
                  +--> xử lý record
                  |
                  +--> ghi nhận offset đã xử lý
                  |
                  +--> commit offset tiếp theo
                              |
                              v
                       Consumer group
                       committed offset
~~~

Offset commit không lưu nội dung nghiệp vụ đã xử lý. Nó chỉ lưu vị trí đọc của consumer group. Nếu ứng dụng đã cập nhật database nhưng chưa commit offset, record có thể được giao lại. Nếu ứng dụng commit offset trước khi hoàn tất nghiệp vụ, record có thể bị bỏ qua khi consumer khởi động lại.

Do đó, acknowledgement mode cần phản ánh đúng thứ tự giữa xử lý nghiệp vụ và commit offset.

## 2. AckMode COUNT hoạt động như thế nào?

Với ContainerProperties.AckMode.COUNT, container theo dõi số record đã được xử lý kể từ lần commit trước. Khi số lượng đạt ngưỡng ackCount, container commit các offset đang chờ.

Ví dụ đặt ackCount=5:

~~~text
Record 1 --> listener xử lý xong --> count = 1
Record 2 --> listener xử lý xong --> count = 2
Record 3 --> listener xử lý xong --> count = 3
Record 4 --> listener xử lý xong --> count = 4
Record 5 --> listener xử lý xong --> count = 5
                                      |
                                      v
                              COMMIT OFFSETS
                                      |
                                      v
                               count = 0
Record 6 --> listener xử lý xong --> count = 1
...
~~~

Với record listener, container xử lý từng record và có thể kiểm tra ngưỡng sau khi listener hoàn tất. Khi ngưỡng đạt, container commit tiến độ đã tích lũy cho consumer đó.

Một số điểm quan trọng:

- ackCount là số record, không phải số byte, số partition hay thời gian.
- Ngưỡng được theo dõi ở từng consumer/container instance. Nó không phải một bộ đếm toàn cục dùng chung cho cả consumer group.
- Nếu một consumer được gán nhiều partition, các record từ những partition đó cùng đóng góp vào ngưỡng của consumer đó.
- Khi commit, Kafka nhận offset cho các partition liên quan; container không commit một con số record toàn cục.
- Nếu lưu lượng thấp và chưa đạt ngưỡng, COUNT có thể không tạo commit mới trong một khoảng thời gian dài.
- Lỗi listener vẫn do error handler, acknowledgement mode và transaction quyết định. COUNT không biến một record thất bại thành thành công.

COUNT là ngưỡng kích hoạt commit, không phải một bộ hẹn giờ. Nếu ứng dụng cần giới hạn cả số record chưa commit lẫn khoảng thời gian giữa các lần commit, hãy xem COUNT_TIME.

## 3. Cấu hình AckMode COUNT bằng Spring Boot

Spring Boot cho phép cấu hình acknowledgement mode và ngưỡng record trong phần listener properties.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      ack-mode: count
      ack-count: 100
      concurrency: 3
~~~

Giải thích:

- enable-auto-commit: false: để Spring Kafka listener container kiểm soát commit offset.
- ack-mode: count: chọn chính sách commit theo số record.
- ack-count: 100: yêu cầu commit khi ngưỡng 100 record đã được xử lý.
- concurrency: 3: tạo tối đa ba consumer child container cho listener container tương ứng, tùy số partition và cấu hình factory.

ack-count chỉ có ý nghĩa với COUNT và COUNT_TIME. Nếu dùng RECORD, BATCH, TIME hoặc manual acknowledgement, thuộc tính này không quyết định thời điểm commit theo cách COUNT sử dụng.

Với application.properties, cấu hình tương đương:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=order-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.listener.ack-mode=count
spring.kafka.listener.ack-count=100
spring.kafka.listener.concurrency=3
~~~

Tên property và hỗ trợ binding có thể phụ thuộc phiên bản Spring Boot. Hãy dùng phiên bản Spring Boot tương thích với Spring Kafka trong ứng dụng và kiểm tra cấu hình được bind thực tế khi khởi tạo.

## 4. Cấu hình COUNT bằng Java

Nếu ứng dụng tự tạo listener container factory, có thể đặt AckMode và ack count trên ContainerProperties.

~~~java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    orderListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.COUNT
        );
        factory.getContainerProperties().setAckCount(100);

        return factory;
    }
}
~~~

Listener sử dụng factory này:

~~~java
@Component
public class OrderConsumer {

    private final OrderService orderService;

    public OrderConsumer(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "order-service",
            containerFactory = "orderListenerContainerFactory"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

Khi có nhiều factory, cần chỉ định đúng containerFactory trên @KafkaListener. Nếu endpoint vẫn dùng factory khác, cấu hình COUNT trên factory vừa tạo sẽ không có tác dụng với endpoint đó.

Nếu ứng dụng dùng factory mặc định do Spring Boot tạo, có thể cấu hình qua spring.kafka.listener mà không cần tạo factory mới chỉ để đặt ack count.

## 5. COUNT khác gì RECORD, BATCH, TIME và COUNT_TIME?

Spring Kafka cung cấp nhiều acknowledgement mode để phù hợp với throughput và yêu cầu phục hồi.

| AckMode | Thời điểm commit | Đặc điểm |
|---|---|---|
| RECORD | Sau khi listener xử lý thành công từng record | Commit thường xuyên, cửa sổ replay nhỏ |
| BATCH | Sau khi xử lý hết các record nhận từ một lần poll | Phù hợp batch và giảm số lần commit |
| TIME | Khi thời gian từ lần commit trước đạt ackTime | Commit theo thời gian |
| COUNT | Khi số record đã xử lý đạt ackCount | Commit theo lưu lượng |
| COUNT_TIME | Khi đạt ackCount hoặc ackTime, tùy điều kiện nào đến trước | Kết hợp giới hạn theo số lượng và thời gian |
| MANUAL | Listener gọi acknowledge; container xử lý commit theo batch semantics | Ứng dụng quyết định khi nào acknowledge |
| MANUAL_IMMEDIATE | Commit ngay khi acknowledge được gọi trên consumer thread | Kiểm soát commit tường minh hơn |

### COUNT và RECORD

RECORD commit sau mỗi record listener xử lý thành công. Với COUNT, container tích lũy nhiều record rồi mới commit.

Nếu ackCount=100, một consumer xử lý 100 record có thể tạo một lần commit thay vì commit sau mỗi record. Điều này có thể giảm số lần gọi commit khi throughput cao.

Đổi lại, nếu consumer dừng sau khi xử lý 90 record nhưng chưa đạt ngưỡng 100, các record đó có thể được đọc lại vì offset chưa được commit. Do đó, COUNT tạo cửa sổ replay lớn hơn RECORD.

### COUNT và BATCH

BATCH commit sau khi listener xử lý toàn bộ record nhận từ một lần poll. Kích thước batch phụ thuộc max.poll.records, số partition được gán và lượng dữ liệu sẵn có.

COUNT sử dụng ngưỡng record tích lũy qua quá trình xử lý. Nếu một lần poll trả ít record, container có thể cần nhiều lần poll để đạt ngưỡng. Nếu một poll trả nhiều record, ngưỡng có thể được đạt trong quá trình xử lý batch đó, tùy loại listener và cách container xử lý.

Với batch listener, method nhận cả một danh sách record trong một lần gọi. COUNT không biến callback batch thành các lần commit độc lập cho từng phần tử của danh sách. Nếu cần xử lý và commit từng record riêng, cân nhắc record listener với RECORD; nếu dùng batch listener, thiết kế theo semantics batch và error handling tương ứng.

### COUNT và TIME

TIME commit khi thời gian kể từ lần commit trước đạt ackTime. Nó hữu ích khi muốn commit dựa trên thời gian thay vì lưu lượng.

COUNT không đảm bảo một khoảng thời gian tối đa giữa các lần commit. Nếu không có đủ record, ngưỡng không được kích hoạt.

Ví dụ: ackCount=100, nhưng topic chỉ có 10 record trong một giờ. COUNT có thể chưa commit các offset mới trong khoảng thời gian đó. Nếu ứng dụng dừng đột ngột, các record đã xử lý nhưng chưa commit có thể được giao lại.

### COUNT và COUNT_TIME

COUNT_TIME kết hợp hai điều kiện. Container commit khi đạt số record ackCount hoặc khi thời gian ackTime đã trôi qua, tùy điều kiện nào xảy ra trước.

Ví dụ:

~~~yaml
spring:
  kafka:
    listener:
      ack-mode: count_time
      ack-count: 100
      ack-time: 5000
~~~

Trong ví dụ, container có thể commit khi đã xử lý đủ 100 record hoặc khi đạt khoảng thời gian 5 giây kể từ lần commit trước. Điều này giúp tránh giữ offset chưa commit quá lâu khi traffic thấp, đồng thời vẫn giảm commit overhead khi traffic cao.

Nếu cần cả giới hạn theo throughput lẫn thời gian, COUNT_TIME thường là lựa chọn đáng cân nhắc hơn COUNT thuần.

## 6. COUNT ảnh hưởng đến duplicate và khả năng phục hồi ra sao?

AckMode COUNT không cung cấp exactly-once processing. Nó chỉ quyết định thời điểm commit offset. Khi ứng dụng đã thực hiện side effect nhưng chưa commit offset, record có thể được giao lại.

Ví dụ với ackCount=10:

~~~text
Consumer xử lý record 1..8
      |
      +--> Database đã commit các thay đổi
      |
      +--> Offset Kafka chưa đạt ngưỡng commit
      |
      v
Process bị dừng
      |
      v
Consumer khởi động lại
      |
      v
Kafka giao lại record từ offset đã commit gần nhất
      |
      v
Record 1..8 có thể được xử lý lại
~~~

Nếu listener tạo hóa đơn, trừ tồn kho hoặc ghi nhận thanh toán, việc xử lý lại có thể gây duplicate. Cần làm nghiệp vụ idempotent.

Một cách phổ biến là dùng event ID ổn định và bảng inbox/processed events có unique constraint. Việc ghi nhận event ID và cập nhật dữ liệu nghiệp vụ cần nằm trong cùng transaction database.

~~~java
@Transactional
public void process(OrderCreated event) {
    boolean firstDelivery =
            processedEventRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderRepository.apply(event);
}
~~~

insertIfAbsent đại diện cho thao tác insert có ràng buộc unique trong database. Nếu event đã được xử lý, consumer không lặp lại hiệu ứng nghiệp vụ. Nếu transaction rollback, cả dấu vết processed event và cập nhật nghiệp vụ cùng rollback.

Một số nguyên tắc:

- Chọn event ID ổn định xuyên suốt các lần giao lại.
- Không dựa vào biến trong bộ nhớ để chống duplicate qua restart.
- Không commit offset trước khi side effect cần bảo vệ hoàn tất.
- Với API bên ngoài, dùng idempotency key nếu API hỗ trợ.
- Theo dõi số lần redelivery và tỷ lệ duplicate ở tầng nghiệp vụ.

## 7. COUNT và xử lý exception

COUNT chỉ quyết định thời điểm commit trong luồng xử lý bình thường. Khi listener ném exception, container chuyển lỗi cho error handler được cấu hình. Error handler quyết định retry, recovery, DLT và offset behavior.

Ví dụ:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-service"
)
public void onOrder(OrderCreated event) {
    orderService.process(event); // Có thể ném exception.
}
~~~

Nếu listener ném exception:

1. Container nhận lỗi từ listener.
2. CommonErrorHandler/DefaultErrorHandler áp dụng retry và backoff.
3. Nếu listener retry thành công, container tiếp tục xử lý offset theo acknowledgement mode.
4. Nếu hết retry, recoverer có thể chuyển record sang DLT.
5. Offset chỉ tiến theo chính sách recovery và commit của container.

Không nên bắt exception rồi chỉ log và trả về nếu muốn container retry:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Processing failed", ex);
        // Nếu không ném lại, container có thể coi listener đã thành công.
    }
}
~~~

COUNT không cứu được lỗi bị nuốt. Khi method kết thúc bình thường, container có thể tính record vào tiến độ xử lý và commit khi đạt ngưỡng.

### Recovery và DLT

Nếu dùng DefaultErrorHandler với DeadLetterPublishingRecoverer, record không phục hồi được có thể được gửi sang DLT sau số lần retry đã cấu hình. Cần kiểm tra kết quả publish DLT; recovery chỉ được xem là hoàn tất khi recoverer thực hiện thành công theo chính sách của container.

COUNT không quyết định DLT có được gửi hay không. Nó chỉ tham gia vào thời điểm commit offset đối với các record mà error handler đã xử lý xong.

## 8. COUNT với concurrency và nhiều partition

Khi cấu hình concurrency, ConcurrentMessageListenerContainer tạo nhiều child container. Mỗi child quản lý một Kafka consumer và có bộ đếm tiến độ riêng.

Ví dụ:

~~~yaml
spring:
  kafka:
    listener:
      ack-mode: count
      ack-count: 100
      concurrency: 3
~~~

Nếu có ba child consumer, mỗi consumer theo dõi số record của chính nó. Đây không phải một bộ đếm chung chờ toàn bộ group xử lý 100 record.

Giả sử topic có sáu partition và ba consumer, mỗi consumer có thể nhận khoảng hai partition tùy partition assignment strategy. Các record từ partition được gán cho cùng consumer cùng đóng góp vào ngưỡng COUNT của consumer đó.

Ví dụ minh họa:

~~~text
Child consumer 1: partition 0, 1 --> đếm riêng đến 100 --> commit offset
Child consumer 2: partition 2, 3 --> đếm riêng đến 100 --> commit offset
Child consumer 3: partition 4, 5 --> đếm riêng đến 100 --> commit offset
~~~

Số partition thực tế trên mỗi child có thể không chia đều. Nếu topic có ít partition hơn concurrency, một số child có thể không nhận partition và không xử lý record.

Điều này ảnh hưởng tới commit rate và khả năng replay:

- Mỗi child có tốc độ đạt ngưỡng khác nhau.
- Consumer xử lý traffic cao có thể commit thường xuyên.
- Consumer xử lý traffic thấp có thể giữ offset lâu hơn.
- Khi rebalance, partition chuyển sang consumer khác; offset đã commit là điểm khôi phục đáng tin cậy.
- COUNT không đặt ngưỡng toàn group và không bảo đảm các child commit cùng thời điểm.

## 9. COUNT liên quan thế nào đến max.poll.records và poll interval?

max.poll.records giới hạn số record tối đa được trả về trong một lần poll. ackCount là ngưỡng số record xử lý giữa các lần commit. Hai cấu hình có mục đích khác nhau.

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 500
      properties:
        "[max.poll.interval.ms]": 300000
    listener:
      ack-mode: count
      ack-count: 100
~~~

Trong ví dụ:

- Một poll có thể trả tối đa 500 record.
- Container commit theo ngưỡng 100 record đã xử lý.
- Thời gian xử lý listener vẫn cần phù hợp với max.poll.interval.ms.

Không nên cho rằng ack-count=100 có nghĩa consumer chỉ poll 100 record. Poll size vẫn do consumer configuration và lượng record sẵn có quyết định.

Nếu listener xử lý quá lâu, consumer có thể vượt max.poll.interval.ms, rời group và gây rebalance. COUNT không tăng poll interval và không giải quyết listener bị treo. Cần đo thời gian xử lý, điều chỉnh batch/poll size, concurrency và dependency latency.

Cũng cần phân biệt:

- max.poll.records: số record tối đa trả về trong một poll.
- ack-count: số record cần xử lý để kích hoạt commit theo COUNT.
- max.poll.interval.ms: giới hạn khoảng thời gian giữa các lần poll mà consumer phải tuân thủ.
- ack-time: ngưỡng thời gian dùng với TIME hoặc COUNT_TIME.

## 10. COUNT với batch listener

Record listener nhận từng record trong mỗi lần gọi method. Batch listener nhận nhiều record cùng lúc. Việc chọn batch listener ảnh hưởng cách ứng dụng xử lý lỗi và tiến độ offset.

Ví dụ batch listener:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch",
        containerFactory = "batchListenerFactory"
)
public void onOrders(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

Factory cần bật batch listener:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
batchListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.COUNT
    );
    factory.getContainerProperties().setAckCount(100);

    return factory;
}
~~~

Khi dùng batch listener, method được gọi với batch nhận từ poll. Container không thể giả định từng phần tử đã hoàn tất độc lập nếu method chưa trả về hoặc chưa có cơ chế báo record lỗi phù hợp.

Nếu batch có một record thất bại, có thể cần BatchListenerFailedException để chỉ ra vị trí record lỗi cho error handler. Nếu không xác định được vị trí, toàn bộ batch có thể được retry hoặc recovery theo chính sách. Những record đã xử lý trước đó có thể bị chạy lại, vì vậy batch operation nên idempotent.

Nếu mục tiêu chính là commit riêng sau mỗi record, record listener với RECORD thường diễn đạt yêu cầu rõ ràng hơn. Nếu mục tiêu là xử lý batch và giảm số lần commit, hãy thiết kế batch error handling cẩn thận.

## 11. COUNT trong transactional listener container

Khi listener container sử dụng Kafka transaction manager, offset được gửi vào Kafka transaction và commit cùng các record đầu ra thuộc transaction đó. Nếu listener ném exception, transaction có thể abort và record được xử lý lại theo transaction recovery.

AckMode quyết định tiến độ offset được đưa vào transaction theo cấu hình container. Trong transactional processing, cần phân biệt commit offset bên ngoài transaction với commit offset như một phần của transaction Kafka.

~~~text
Kafka transaction bắt đầu
       |
       v
Listener xử lý record
       |
       +--> gửi output qua KafkaTemplate
       |
       +--> listener hoàn tất
       |        |
       |        v
       |    Offset được thêm vào transaction
       |        |
       |        v
       |    Commit transaction
       |
       +--> exception
                |
                v
             Abort transaction
                |
                v
       Rollback/recovery theo cấu hình
~~~

Nếu dùng COUNT cùng transaction, hãy xác nhận hành vi trên đúng phiên bản Spring Kafka và loại listener đang triển khai. Không coi ngưỡng COUNT là một transaction độc lập hoặc là bảo đảm exactly-once cho database. Database ngoài Kafka vẫn cần transaction manager phù hợp, inbox/outbox hoặc idempotency.

## 12. Khi nào nên chọn COUNT?

COUNT phù hợp khi:

- Consumer xử lý throughput tương đối cao.
- Commit sau mỗi record tạo overhead đáng kể.
- Nghiệp vụ chấp nhận một cửa sổ replay hữu hạn và có idempotency.
- Lưu lượng đủ đều để ngưỡng record được đạt trong thời gian hợp lý.
- Hệ thống có thể quan sát commit latency, consumer lag và redelivery.

COUNT ít phù hợp khi:

- Topic có traffic rất thấp hoặc không đều.
- Nghiệp vụ yêu cầu offset được commit trong khoảng thời gian ngắn dù ít record.
- Duplicate có chi phí cao và không có cơ chế idempotency.
- Listener batch cần xử lý lỗi riêng từng record nhưng chưa có thiết kế phù hợp.
- Consumer thường xuyên dừng hoặc rebalance trước khi đạt ngưỡng.

Nếu traffic thấp nhưng vẫn muốn giảm commit overhead, hãy cân nhắc COUNT_TIME để có giới hạn thời gian. Nếu cần commit ngay sau từng record, dùng RECORD. Nếu muốn commit sau mỗi poll batch, dùng BATCH.

## 13. Cách chọn ackCount

Không có một ngưỡng đúng cho mọi consumer. Hãy chọn dựa trên throughput, chi phí commit và mức độ chấp nhận replay.

### Ngưỡng nhỏ

Ví dụ ackCount=10:

- Commit thường xuyên hơn.
- Số record chưa commit thường ít hơn khi traffic ổn định.
- Tăng số lần commit và có thể tăng overhead broker/network.
- Có thể phù hợp với consumer throughput thấp hoặc nghiệp vụ nhạy với replay.

### Ngưỡng lớn

Ví dụ ackCount=1000:

- Giảm số lần commit khi traffic cao.
- Có thể cải thiện hiệu quả xử lý nếu commit overhead là nút thắt đã được đo.
- Tăng số record có thể được giao lại sau crash trước commit.
- Với traffic thấp, thời gian chờ đạt ngưỡng có thể rất dài.

### Ước lượng thời gian đạt ngưỡng

Nếu một child consumer xử lý trung bình 200 record mỗi giây và ackCount=100, thời gian lý thuyết để đạt ngưỡng xấp xỉ:

~~~text
100 records / 200 records per second = 0.5 seconds
~~~

Nếu consumer chỉ xử lý 2 record mỗi phút, cùng ngưỡng 100 có thể cần khoảng 50 phút để đạt ngưỡng. Đây là lý do COUNT thuần có thể không phù hợp với traffic thấp.

Ước lượng này chỉ dùng để định hướng. Throughput thực tế thay đổi theo partition, batch, thời gian listener, rebalance, backpressure và lỗi dependency.

### Quy trình lựa chọn

1. Đo throughput theo từng consumer instance/child container.
2. Đo commit rate và commit latency hiện tại.
3. Xác định số record có thể chấp nhận bị replay sau crash.
4. Chọn ngưỡng ban đầu nhỏ, quan sát và tăng dần nếu có bằng chứng commit overhead là nút thắt.
5. Kiểm tra traffic thấp để xem khoảng thời gian giữa các lần commit.
6. Thử restart/rebalance trước và sau khi đạt ngưỡng.
7. Xác nhận consumer idempotent khi record được giao lại.
8. Nếu cần giới hạn thời gian, chuyển sang COUNT_TIME và chọn ackTime phù hợp.

## 14. Theo dõi COUNT trong production

Cần theo dõi cả tiến độ xử lý và tiến độ commit. Chỉ nhìn throughput không cho biết offset có được commit đều đặn hay không.

| Chỉ số | Điều cần quan sát |
|---|---|
| Consumer records consumed rate | Tốc độ record được xử lý |
| Consumer commit rate | Tần suất commit offset |
| Commit latency | Thời gian broker phản hồi commit |
| Consumer lag | Khoảng cách giữa offset hiện tại và offset đã commit |
| Records lag max | Partition có độ trễ lớn nhất |
| Rebalance rate | Tần suất consumer group phải phân phối lại partition |
| Listener processing time | Thời gian xử lý từng record hoặc batch |
| Redelivery / retry count | Số lần record phải xử lý lại |
| DLT publish count | Số record được recovery sang DLT |

Tên metric cụ thể phụ thuộc Kafka client, Micrometer và hệ thống exporter. Hãy kiểm tra các metric thực tế đang được xuất trong ứng dụng.

Một số dấu hiệu cần điều tra:

- Consumer xử lý nhanh nhưng commit rate thấp bất thường.
- Consumer lag tăng dù producer throughput không đổi.
- Sau restart, nhiều record đã xử lý trước đó bị giao lại.
- Một child container đạt COUNT nhanh trong khi child khác ít khi commit.
- Commit latency tăng khi broker tải cao.
- Retry hoặc DLT count tăng sau một đợt rebalance.

Log nên ghi nhận group ID, topic, partition, offset, event ID và thời điểm commit/recovery khi cần điều tra. Tránh log payload nhạy cảm chỉ để quan sát acknowledgement.

## 15. Các lỗi cấu hình thường gặp

**Đặt ack-mode=count nhưng quên ack-count**

Nếu ngưỡng không được đặt theo ý định, ứng dụng có thể dùng giá trị mặc định hoặc giá trị được bind từ cấu hình khác. Hãy kiểm tra ContainerProperties.getAckCount() hoặc log cấu hình container khi khởi động.

**Đặt ack-count quá lớn**

Với traffic thấp, offset có thể chưa được commit trong thời gian dài. Crash có thể làm phát lại nhiều record. Cân nhắc COUNT_TIME hoặc ngưỡng nhỏ hơn.

**Nhầm ack-count với max.poll.records**

Hai thuộc tính điều khiển hai hành vi khác nhau. max.poll.records giới hạn kích thước poll; ack-count đặt ngưỡng commit.

**Nhầm COUNT với manual acknowledgement**

COUNT là chế độ container tự theo dõi số record. MANUAL yêu cầu listener gọi Acknowledgment.acknowledge(). ackCount không thay thế thao tác acknowledge của manual mode.

**Bắt exception và không ném lại**

Container có thể xem listener kết thúc thành công, khiến record được tính vào tiến độ xử lý. Nếu cần retry, hãy để exception truyền tới error handler hoặc áp dụng recovery rõ ràng.

**Cho rằng COUNT tạo exactly-once**

COUNT chỉ điều khiển offset commit. Nó không gộp cập nhật database vào transaction Kafka và không ngăn side effect chạy hai lần sau redelivery.

**Không tính concurrency**

Mỗi child consumer có ngưỡng riêng. Không lấy ackCount nhân hoặc chia theo concurrency rồi coi đó là một bộ đếm toàn group.

## 16. Ví dụ cấu hình hoàn chỉnh

Một cấu hình minh họa cho record listener với traffic đều:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 300
    listener:
      ack-mode: count
      ack-count: 100
      concurrency: 3
      missing-topics-fatal: false
~~~

Listener:

~~~java
@Component
public class OrderConsumer {

    private final OrderService orderService;

    public OrderConsumer(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "order-service"
    )
    public void consume(OrderCreated event) {
        orderService.processIdempotently(event);
    }
}
~~~

Trong ví dụ:

- Container quản lý commit offset.
- Mỗi child consumer tích lũy số record đã xử lý.
- Khi đạt 100 record, container commit các offset đang chờ của consumer đó.
- max-poll-records=300 giới hạn số record tối đa trả về trong một poll, độc lập với ack count.
- concurrency=3 cho phép tối đa ba child consumer, phụ thuộc partition assignment.
- processIdempotently đại diện cho logic nghiệp vụ chống duplicate.

Nếu lưu lượng không đều và cần commit trong tối đa khoảng thời gian mong muốn, có thể chuyển sang:

~~~yaml
spring:
  kafka:
    listener:
      ack-mode: count_time
      ack-count: 100
      ack-time: 5000
~~~

Khi đó, container commit khi đạt 100 record hoặc khi khoảng thời gian ack-time đã trôi qua kể từ lần commit trước. Hãy kiểm tra đơn vị thời gian của property theo API/phiên bản Spring Kafka; ackTime được cấu hình bằng mili giây ở ContainerProperties.

## 17. Checklist trước khi đưa COUNT vào production

- enable.auto.commit đã tắt để container quản lý offset.
- Factory thực tế của listener dùng ContainerProperties.AckMode.COUNT.
- ackCount được cấu hình rõ ràng và có giá trị phù hợp.
- Đã phân biệt ack count với max.poll.records và max.poll.interval.ms.
- Đã hiểu mỗi child consumer có bộ đếm riêng.
- Đã đo traffic cao và traffic thấp để ước lượng thời gian đạt ngưỡng.
- Đã xác định số record tối đa có thể bị replay sau crash.
- Listener có idempotency cho side effect nghiệp vụ.
- Exception được truyền tới error handler khi cần retry.
- Retry/backoff/recovery/DLT có giới hạn và quan sát được.
- Nếu cần giới hạn thời gian giữa các lần commit, đã cân nhắc COUNT_TIME.
- Nếu dùng batch listener hoặc Kafka transaction, đã xác định rõ semantics của listener và offset.
- Đã theo dõi commit rate, commit latency, consumer lag, rebalance và redelivery.
- Đã thử restart và rebalance khi số record đã xử lý chưa đạt ngưỡng.

AckMode COUNT hữu ích khi consumer có throughput đủ cao và cần giảm số lần commit offset. Đổi lại, ứng dụng chấp nhận một cửa sổ record chưa commit lớn hơn và có thể phải xử lý lại sau crash. Chọn ackCount dựa trên số liệu của từng consumer, kết hợp idempotency và dùng COUNT_TIME khi cần một giới hạn thời gian cho việc commit.
