# AckMode BATCH

Trong Spring Kafka, **AckMode** quyết định thời điểm listener container xác nhận tiến độ đọc bằng cách commit offset của consumer group. Với **AckMode.BATCH**, container commit offset sau khi tất cả record được trả về trong một lần poll đã được xử lý thành công theo luồng listener. Đây là chế độ mặc định phổ biến của Spring Kafka và thường phù hợp khi muốn giảm số lần commit mà vẫn giữ cơ chế xác nhận do container quản lý.

BATCH không có nghĩa Kafka gộp các record thành một record, cũng không tạo transaction nghiệp vụ tự động. Nó xác định thời điểm commit offset cho các partition đã được poll. Muốn dùng hiệu quả, cần hiểu ranh giới của một poll, cách record listener và batch listener hoạt động, cũng như cách lỗi ảnh hưởng đến offset và việc giao lại record.

Bài học thuộc chương **Listener container** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách Spring Kafka quản lý listener, consumer group và offset để vận hành luồng sự kiện đáng tin cậy.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích AckMode.BATCH và thời điểm container commit offset.
- Phân biệt một lần poll với một lần gọi listener.
- Hiểu BATCH trong record listener và batch listener.
- Cấu hình AckMode.BATCH bằng Spring Boot hoặc listener container factory.
- Đọc offset được commit theo từng partition.
- Phân tích hành vi khi listener ném exception, retry hoặc chuyển record sang DLT.
- Nhận biết ảnh hưởng của batch size, thời gian xử lý và rebalance.
- Thiết kế listener idempotent để chịu được việc record được giao lại.
- Kiểm thử thời điểm commit và hành vi lỗi bằng EmbeddedKafka hoặc Testcontainers.

## 1. AckMode và vai trò của listener container

Kafka consumer đọc record từ partition và duy trì vị trí đọc. Khi ứng dụng xác nhận tiến độ, consumer commit offset lên Kafka để group có thể tiếp tục từ vị trí phù hợp sau khi restart hoặc rebalance.

Spring Kafka dùng listener container để quản lý vòng poll, gọi phương thức có @KafkaListener và commit offset theo AckMode. Ứng dụng thường không phải tự gọi commitSync hoặc commitAsync trong listener.

Các thành phần phối hợp:

~~~mermaid
flowchart TD
    B[Kafka broker] --> P[Consumer poll]
    P --> C[Listener container]
    C --> L["@KafkaListener"]
    L --> R[Xử lý record]
    R --> S{Xử lý thành công?}
    S -->|Có| A[AckMode.BATCH]
    A --> O[Commit offset theo partition]
    S -->|Không| E[Error handler]
    E --> RT[Retry / DLT / redelivery]
~~~

AckMode.BATCH nói với container rằng tiến độ của một poll được commit sau khi toàn bộ record thuộc poll đó đã được xử lý thành công theo quy tắc listener và error handler. Container giữ trách nhiệm phối hợp acknowledgement và commit.

Trong cấu hình Spring Kafka thông thường, container quản lý commit nên consumer auto-commit được tắt. Spring Kafka tự đặt enable.auto.commit=false nếu ứng dụng không chủ động bật lại; khai báo rõ trong cấu hình giúp tránh nhầm lẫn.

## 2. Một poll batch là gì?

Consumer gọi poll để lấy record từ các partition đã được gán. Một lần poll có thể trả về:

- Không có record nào.
- Một record từ một partition.
- Nhiều record từ một partition.
- Nhiều record từ nhiều partition.

Giới hạn số record tối đa trong một lần poll chịu ảnh hưởng của max.poll.records và dữ liệu hiện có ở broker. Một poll không nhất thiết chứa đủ số record tối đa đã cấu hình.

Ví dụ, một lần poll trả về:

| Partition | Các offset được trả về |
|---|---|
| orders.created-0 | 10, 11, 12 |
| orders.created-1 | 4, 5 |
| orders.created-2 | 27 |

Sau khi các record này được xử lý thành công, container có thể commit tiến độ cho từng partition:

| Partition | Offset record cuối trong poll | Offset commit tiếp theo |
|---|---:|---:|
| orders.created-0 | 12 | 13 |
| orders.created-1 | 5 | 6 |
| orders.created-2 | 27 | 28 |

Kafka lưu offset tiếp theo cần đọc. Vì vậy, nếu record có offset 12 đã được xử lý và commit thành công, offset được commit là 13.

Một poll có thể chứa record từ nhiều partition. Commit được quản lý riêng cho từng partition, không tồn tại một offset toàn cục cho cả topic.

## 3. AckMode.BATCH hoạt động với record listener

Record listener là cách dùng @KafkaListener phổ biến nhất: mỗi lần gọi phương thức nhận một record. Tuy nhiên, consumer vẫn poll theo batch ở phía client.

Với AckMode.BATCH:

1. Consumer poll và nhận một tập record từ các partition.
2. Listener container lần lượt chuyển các record cho phương thức listener.
3. Container theo dõi kết quả xử lý các record thuộc poll đó.
4. Khi toàn bộ record của poll được xử lý thành công, container commit offset theo partition.
5. Consumer tiếp tục poll vòng kế tiếp.

Ví dụ listener:

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment"
    )
    public void consume(OrderCreatedEvent event) {
        orderService.handle(event);
    }
}
~~~

Cấu hình BATCH cho listener container áp dụng dù phương thức nhận từng event. Phương thức listener không nhận một List chỉ vì AckMode là BATCH.

Điều này thường bị nhầm: **AckMode.BATCH là chính sách commit offset; batch listener là kiểu chữ ký phương thức nhận nhiều record**. Hai khái niệm liên quan nhưng không đồng nhất.

## 4. AckMode.BATCH hoạt động với batch listener

Nếu muốn phương thức listener nhận cả danh sách record từ một lần poll, cần bật batch listener cho container factory. Khi đó Spring Kafka chuyển batch record tới một lần gọi listener.

Ví dụ cấu hình factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
orderBatchListenerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

Listener nhận danh sách ConsumerRecord:

~~~java
@Component
public class OrderBatchListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-batch-processor",
            containerFactory = "orderBatchListenerFactory"
    )
    public void consume(
            List<ConsumerRecord<String, OrderCreatedEvent>> records) {

        for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
            orderService.handle(record.value());
        }
    }
}
~~~

Với batch listener, phương thức được gọi một lần cho batch do poll trả về. Khi phương thức hoàn tất bình thường, container có thể commit offset của batch theo AckMode.BATCH.

Batch listener hữu ích khi nghiệp vụ có thể xử lý nhiều record cùng lúc, chẳng hạn bulk insert hoặc gọi một API hỗ trợ batch. Tuy nhiên, batch lớn làm tăng thời gian xử lý và phạm vi record có thể phải giao lại nếu xảy ra lỗi.

## 5. Cấu hình AckMode.BATCH trong Spring Boot

Có thể cấu hình listener type và ack mode trong application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      type: single
      ack-mode: batch
~~~

Trong cấu hình này:

- type: single chọn record listener, mỗi lần gọi listener nhận một record.
- ack-mode: batch chọn commit sau khi các record thuộc một poll đã được xử lý.
- enable-auto-commit: false để container quản lý commit offset.
- group-id xác định consumer group lưu tiến độ.

Nếu muốn listener nhận cả batch, có thể dùng type: batch trong cấu hình Spring Boot phù hợp hoặc cấu hình riêng factory bằng setBatchListener(true). Kiểm tra phiên bản Spring Boot/Spring Kafka đang dùng vì các thuộc tính listener và cách cấu hình có thể thay đổi theo phiên bản.

Có thể cấu hình trực tiếp bằng Java:

~~~java
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);
~~~

AckMode.BATCH cũng là giá trị mặc định của ContainerProperties trong Spring Kafka. Dù vậy, khai báo tường minh trong ứng dụng quan trọng giúp người đọc hiểu chính sách commit mà listener đang sử dụng.

## 6. So sánh BATCH với các AckMode khác

AckMode xác định thời điểm commit; lựa chọn phù hợp phụ thuộc yêu cầu độ trễ, thông lượng và khả năng xử lý lại.

| AckMode | Thời điểm commit khái quát | Trường hợp thường cân nhắc |
|---|---|---|
| RECORD | Sau khi từng record listener được xử lý thành công | Muốn commit sát từng record. |
| BATCH | Sau khi toàn bộ record từ một poll được xử lý thành công | Cân bằng giữa thông lượng và số lần commit. |
| TIME | Khi đã có acknowledgement và đạt khoảng thời gian cấu hình | Muốn giới hạn chu kỳ commit theo thời gian. |
| COUNT | Khi đạt số acknowledgement cấu hình | Muốn commit theo ngưỡng số lượng. |
| COUNT_TIME | Khi đạt ngưỡng số lượng hoặc thời gian | Kết hợp hai điều kiện. |
| MANUAL | Listener chủ động gọi acknowledge; container commit theo semantics của batch | Nghiệp vụ quyết định thời điểm xác nhận. |
| MANUAL_IMMEDIATE | Listener acknowledge và container cố gắng commit ngay khi lời gọi diễn ra trên consumer thread | Cần điều khiển commit tường minh. |

RECORD và BATCH thường là hai chế độ dễ so sánh nhất. RECORD có thể tạo nhiều lần commit hơn; BATCH giảm số lần commit bằng cách gom tiến độ theo poll. Đổi lại, nếu lỗi xảy ra trong poll, cần hiểu chính sách error handler để biết record nào được giao lại.

TIME, COUNT và COUNT_TIME không phải cách thay thế trực tiếp cho xử lý batch ở listener. Chúng điều khiển ngưỡng commit dựa trên acknowledgement và cấu hình tương ứng.

## 7. BATCH không tạo transaction nghiệp vụ

Commit offset theo batch không đồng nghĩa toàn bộ xử lý nghiệp vụ của batch được thực hiện nguyên tử.

Ví dụ batch có ba record:

1. Record A cập nhật database thành công.
2. Record B cập nhật database thành công.
3. Record C gặp lỗi.
4. Listener ném exception nên container không thể coi toàn bộ poll đã hoàn tất thành công theo luồng bình thường.

Nếu các thay đổi database của A và B đã commit riêng lẻ, việc Kafka giao lại record sau lỗi có thể khiến A và B được xử lý lần nữa. BATCH chỉ điều khiển offset Kafka; nó không tự rollback database.

Nếu muốn xử lý batch database theo một transaction, có thể đặt các thay đổi database của batch trong transaction database phù hợp. Tuy nhiên, transaction database và commit offset Kafka vẫn là hai ranh giới khác nhau nếu không có cơ chế phối hợp được thiết kế rõ ràng.

Với các tác động nghiệp vụ có thể lặp, nên:

- Dùng eventId ổn định cho từng sự kiện.
- Tạo unique constraint hoặc inbox table để phát hiện event đã xử lý.
- Đảm bảo thao tác cập nhật có tính idempotent.
- Xem xét outbox/inbox khi cần phối hợp database và Kafka.
- Không giả định một lần commit offset BATCH bảo đảm exactly-once cho toàn bộ nghiệp vụ.

## 8. Khi listener gặp lỗi trong một poll

Khi listener ném exception, container chuyển việc xử lý cho error handler. Chính sách retry, seek, redelivery hoặc DLT quyết định consumer tiếp tục như thế nào.

Với record listener dùng AckMode.BATCH, container xử lý từng record trong poll. Nếu một record lỗi, không nên tự suy luận rằng mọi record trước đó chắc chắn đã commit hoặc cả poll chắc chắn luôn được đọc lại. Hành vi phụ thuộc loại listener, error handler, cấu hình retry và cách xử lý exception.

Với batch listener, nếu phương thức ném exception thông thường, Spring Kafka có thể phải xử lý lại batch theo chính sách error handler. Khi cần chỉ ra record lỗi trong batch, có thể ném BatchListenerFailedException để DefaultErrorHandler biết vị trí record thất bại và áp dụng xử lý phù hợp cho phần trước và phần còn lại.

Ví dụ minh họa:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-batch-processor",
        containerFactory = "orderBatchListenerFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreatedEvent>> records) {

    for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
        try {
            orderService.handle(record.value());
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                    "Cannot process order event",
                    record
            );
        }
    }
}
~~~

BatchListenerFailedException và cách xử lý partial batch phụ thuộc phiên bản Spring Kafka cùng error handler được cấu hình. Hãy dùng DefaultErrorHandler tương thích với phiên bản ứng dụng và kiểm thử chính sách thực tế.

Một error handler có thể retry một số lần, sau đó recover record bằng cách publish sang dead-letter topic. DLT giúp cô lập record không xử lý được, nhưng cần quy trình giám sát và replay sau khi sửa nguyên nhân.

Nếu listener bắt exception rồi không ném lại và cũng không chuyển record sang một cơ chế recovery đáng tin cậy, container có thể xem lần gọi là thành công và commit offset. Điều đó có thể làm mất cơ hội xử lý lại record. Chỉ nuốt exception khi nghiệp vụ đã ghi nhận lỗi và quyết định bỏ qua một cách có chủ đích.

## 9. Ảnh hưởng của batch size và thời gian xử lý

BATCH gom offset của các record từ một poll. Vì vậy, kích thước poll và thời gian xử lý ảnh hưởng tới độ trễ commit.

Các thuộc tính đáng chú ý:

- max.poll.records giới hạn số record tối đa được trả về trong một lần poll.
- max.poll.interval.ms giới hạn thời gian giữa các lần poll tiếp theo trước khi consumer có thể bị xem là không còn tiến triển.
- fetch.min.bytes và fetch.max.wait.ms ảnh hưởng cách broker chờ và trả dữ liệu cho fetch request.
- concurrency xác định số consumer worker mà listener container có thể tạo.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
    listener:
      ack-mode: batch
      concurrency: 3
~~~

Với record listener, nếu một poll trả 100 record, container có thể gọi listener nhiều lần trước khi commit batch. Với batch listener, phương thức nhận tối đa số record được poll trả về theo giới hạn và dữ liệu sẵn có.

Batch lớn có thể tăng hiệu quả commit và xử lý bulk, nhưng cũng có thể:

- Tăng thời gian xử lý một poll.
- Làm tăng độ trễ commit offset.
- Tăng số record có thể bị giao lại khi xử lý thất bại.
- Tăng bộ nhớ cần cho record và object đã deserialize.
- Làm listener vượt max.poll.interval.ms nếu xử lý quá lâu.

Không tăng max.poll.records chỉ để giảm số lần commit. Hãy đo thời gian xử lý p95/p99, kích thước payload, lag, throughput và giới hạn downstream trước khi điều chỉnh.

## 10. BATCH, concurrency và rebalance

Khi listener container có concurrency lớn hơn một, Spring Kafka tạo nhiều consumer worker. Mỗi consumer poll và quản lý các partition được gán cho nó. AckMode.BATCH được áp dụng theo tiến độ poll của từng consumer, không phải một batch toàn cục cho mọi thread.

Ví dụ topic có sáu partition và listener concurrency bằng ba. Mỗi consumer có thể nhận hai partition. Mỗi consumer có poll loop và batch offset riêng; một consumer hoàn tất poll của nó không có nghĩa các consumer khác cũng đã hoàn tất.

Khi consumer rời group hoặc bị rebalance, partition có thể được gán lại cho member khác. Offset đã commit theo BATCH là điểm phục hồi của group. Record đã xử lý nhưng chưa được commit có thể được giao lại.

Vì vậy, listener cần idempotent. Nếu một event cập nhật số lượng tồn kho, thao tác cần bảo vệ để cùng eventId không trừ tồn kho hai lần khi record được giao lại sau rebalance hoặc lỗi.

## 11. Commit đồng bộ và bất đồng bộ

AckMode.BATCH xác định thời điểm commit, còn cách gửi commit request có thể được cấu hình riêng.

Spring Kafka ContainerProperties có tùy chọn syncCommits. Mặc định, container thường sử dụng commitSync; có thể cấu hình commitAsync thông qua syncCommits=false tùy yêu cầu và phiên bản.

Commit đồng bộ chờ broker phản hồi commit, giúp container biết kết quả commit nhưng có thể tăng thời gian chờ. Commit bất đồng bộ không chờ kết quả theo cùng cách, có thể giảm thời gian chặn nhưng việc xử lý lỗi commit cần được cân nhắc.

Ví dụ cấu hình:

~~~java
factory.getContainerProperties().setSyncCommits(true);
~~~

Chỉ thay đổi sang async commit khi đã hiểu hành vi callback, lỗi commit và khả năng phục hồi. Sync/async commit không làm thay đổi ý nghĩa của AckMode.BATCH: offset vẫn được gom theo poll.

## 12. Kiểm thử AckMode.BATCH

Kiểm thử cần xác minh cả hai mặt: listener xử lý record và consumer group commit offset ở ranh giới batch.

Các lớp kiểm thử:

| Kiểm thử | Điều cần xác minh |
|---|---|
| Configuration test | Container được cấu hình AckMode.BATCH và auto-commit tắt. |
| Record listener integration test | Các record trong poll được xử lý trước khi offset của poll được commit. |
| Batch listener integration test | Listener nhận danh sách record và commit sau khi xử lý batch thành công. |
| Multi-partition test | Offset được commit riêng cho từng partition. |
| Failure test | Exception kích hoạt error handler và hành vi redelivery/retry mong đợi. |
| DLT test | Record không phục hồi được chuyển tới DLT theo cấu hình. |
| Rebalance test | Record chưa commit có thể được giao lại sau khi partition đổi owner. |
| Idempotency test | Giao lại record không lặp tác động nghiệp vụ. |

Có thể dùng EmbeddedKafka để kiểm thử nhanh trong Spring context hoặc Testcontainers khi cần broker gần với môi trường triển khai.

Khi kiểm tra offset, có thể dùng AdminClient để đọc offset của consumer group. Hãy đợi container xử lý và commit xong với timeout rõ ràng; không dùng Thread.sleep cố định. Offset commit là vị trí tiếp theo cần đọc, do đó nếu test xử lý record có offset 10 thì giá trị commit mong đợi thường là 11.

Để kiểm thử một poll có nhiều record, cần chuẩn bị dữ liệu và consumer timing có kiểm soát. Nếu gửi record trong khi listener đã chạy, broker có thể trả chúng trong nhiều poll khác nhau; không nên giả định chỉ vì gửi liên tiếp mà chúng chắc chắn nằm cùng một batch.

## 13. Những lỗi thường gặp khi dùng AckMode.BATCH

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ BATCH là batch listener | Hiểu sai chữ ký và số lần gọi listener | Phân biệt AckMode với listener type. |
| Bật auto-commit cùng container-managed ack | Commit tự động có thể xung đột với chính sách container | Để enable.auto.commit=false. |
| Nuốt exception trong listener | Container có thể coi xử lý thành công và commit offset | Ném lỗi hoặc dùng recovery có chủ đích. |
| Batch quá lớn | Commit chậm, tăng memory và phạm vi redelivery | Đo và điều chỉnh max.poll.records. |
| Xử lý lâu vượt max.poll.interval.ms | Consumer có thể rời group và gây rebalance | Tối ưu xử lý, kiểm soát batch và cấu hình interval hợp lý. |
| Cho rằng BATCH là transaction database | Tác động database trước lỗi có thể bị lặp khi record giao lại | Dùng transaction DB phù hợp và idempotency. |
| Không kiểm thử multi-partition | Hiểu sai offset commit là offset toàn topic | Kiểm tra offset riêng theo từng partition. |
| Giả định mọi lỗi làm replay nguyên batch | Có thể sai với error handler và partial batch handling | Kiểm tra cấu hình handler và kiểm thử failure path. |

## 14. Bài tập tổng hợp: listener xử lý batch đơn hàng

Hãy xây dựng listener cho topic orders.created và cấu hình AckMode.BATCH.

Yêu cầu:

1. Cấu hình group ID orders-fulfillment và enable.auto.commit=false.
2. Tạo record listener và xác minh container commit sau khi xử lý các record thuộc poll.
3. Tạo batch listener nhận List<ConsumerRecord<String, OrderCreatedEvent>>.
4. Gửi record tới ít nhất hai partition và kiểm tra offset commit riêng.
5. Tạo một lỗi ở giữa batch và cấu hình DefaultErrorHandler.
6. Thử BatchListenerFailedException để chỉ ra record lỗi trong batch listener.
7. Cấu hình retry có giới hạn và DLT cho record không phục hồi được.
8. Dùng eventId để bảo vệ logic xử lý lặp.
9. Điều chỉnh max.poll.records và đo thời gian xử lý, commit và consumer lag.
10. Chạy concurrency lớn hơn một và quan sát mỗi consumer có poll/commit riêng.
11. Dừng consumer giữa lúc xử lý để kiểm tra redelivery sau rebalance.
12. Viết integration test xác minh offset commit và kết quả xử lý nghiệp vụ.

Kết quả cần ghi lại gồm listener type, AckMode, số partition, concurrency, max.poll.records, thời gian xử lý mỗi poll, số lần retry, số record vào DLT và lag của consumer group.

## 15. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Offset commit | AckMode và listener container | Giải thích được container commit offset ở thời điểm nào. |
| 2. Poll batch | Poll và record theo partition | Tính được offset tiếp theo cần commit cho từng partition. |
| 3. Record listener | BATCH với listener nhận từng record | Hiểu nhiều lần gọi listener có thể thuộc một poll. |
| 4. Batch listener | setBatchListener và List<ConsumerRecord> | Nhận và xử lý batch do poll trả về. |
| 5. Configuration | Spring Boot và ContainerProperties | Cấu hình đúng BATCH và tắt auto-commit. |
| 6. Failure handling | DefaultErrorHandler, retry, DLT | Kiểm soát redelivery và partial batch failure. |
| 7. Performance | max.poll.records, interval, concurrency | Cân bằng throughput, độ trễ commit và lag. |
| 8. Reliability | Idempotency, transaction boundary | Không nhầm offset batch với exactly-once nghiệp vụ. |
| 9. Testing | EmbeddedKafka/Testcontainers, AdminClient | Xác minh offset và hành vi lỗi trong test. |

Bài học hoàn thành khi bạn có thể giải thích và cấu hình AckMode.BATCH, phân biệt record listener với batch listener, đọc offset commit theo từng partition và xử lý đúng lỗi trong poll. Quan trọng nhất, bạn cần biết commit theo batch là ranh giới tiến độ của Kafka consumer; tính nhất quán của database và side effect nghiệp vụ vẫn cần được thiết kế riêng.

AckMode.BATCH giảm số lần commit bằng cách xác nhận tiến độ sau khi xử lý xong các record của một poll. Nó phù hợp với nhiều ứng dụng Spring Kafka, nhưng độ tin cậy phụ thuộc vào error handler, kích thước poll, thời gian xử lý, idempotency và cách ứng dụng phối hợp offset với tác động bên ngoài.

