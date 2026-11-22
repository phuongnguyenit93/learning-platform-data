# Retry batch listener

Trong Spring Kafka, **batch listener** nhận một nhóm record trong một lần gọi thay vì nhận từng record riêng lẻ. Cách này giảm overhead khi xử lý nhiều message, nhưng tạo ra một câu hỏi quan trọng khi lỗi xảy ra: record nào trong batch thất bại, và những record còn lại đã được xử lý đến đâu?

**DefaultErrorHandler** hỗ trợ retry cho batch listener. Nếu listener ném một exception thông thường, framework không biết chính xác record nào gây lỗi nên thường phải retry toàn bộ batch. Nếu listener xác định được record lỗi, nó có thể ném **BatchListenerFailedException** kèm vị trí record để handler commit phần đứng trước và retry từ record lỗi trở đi.

Chọn đúng chiến lược giúp giảm xử lý lặp, tránh một record lỗi chặn cả batch quá lâu và giữ offset nhất quán. Cần hiểu rõ batch retry, backoff, exception classification, recovery/DLT và sự khác nhau giữa batch listener với record listener.

## 1. Batch listener hoạt động như thế nào?

Với record listener, container gọi listener một lần cho mỗi record. Với batch listener, container lấy các record từ một lần poll và chuyển cả nhóm cho một lần gọi listener.

Ví dụ record listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service"
)
public void handle(OrderCreated event) {
    orderService.process(event);
}
~~~

Ví dụ batch listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service"
)
public void handle(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

Batch listener phù hợp khi có thể xử lý nhiều record cùng lúc, chẳng hạn bulk insert, batch update hoặc gom các thao tác I/O. Nó cũng giúp giảm số lần gọi listener và có thể cải thiện throughput.

Tuy nhiên, một lần gọi listener có thể đại diện cho nhiều record và nhiều offset. Nếu listener xử lý được 9 record rồi thất bại ở record thứ 10, container cần biết 9 record trước đã hoàn tất hay chưa để quyết định commit và retry.

### 1.1 Bật batch listener

Khi tự cấu hình ConcurrentKafkaListenerContainerFactory, bật batch mode:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersBatchListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        CommonErrorHandler errorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setCommonErrorHandler(errorHandler);

    return factory;
}
~~~

Listener sử dụng factory:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "ordersBatchListenerFactory"
)
public void handle(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

Nếu dùng Spring Boot auto-configuration, có thể bật batch listener qua property phù hợp với phiên bản Spring Boot/Spring Kafka. Khi dùng factory custom, cấu hình phải được đặt trên đúng factory mà listener tham chiếu.

### 1.2 Kích thước batch đến từ đâu?

Batch listener thường nhận các record do một lần poll trả về. Kích thước thực tế chịu ảnh hưởng bởi:

- **max.poll.records**: giới hạn số record consumer trả về trong một lần poll.
- Lượng record đang có sẵn trên các partition được gán.
- Kích thước record và giới hạn fetch.
- Thời gian giữa các lần poll.
- Partition assignment của consumer.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.records: 200
~~~

Giá trị 200 là giới hạn số record tối đa được trả về trong một lần poll của consumer; batch thực tế có thể nhỏ hơn. Với concurrent container, mỗi child consumer có poll riêng, vì vậy mỗi child có thể nhận batch khác nhau.

Không nên tăng max.poll.records mà không đo thời gian xử lý. Batch quá lớn có thể làm listener mất nhiều thời gian, tăng bộ nhớ, tăng thời gian retry và gây khó khăn khi xác định record lỗi.

## 2. DefaultErrorHandler xử lý lỗi batch như thế nào?

**DefaultErrorHandler** là common error handler của Spring Kafka. Nó có thể xử lý exception từ record listener và batch listener, nhưng cách xác định phạm vi retry khác nhau.

Với record listener, container biết record nào đang được xử lý khi exception xảy ra. Với batch listener, nếu chỉ có một exception thông thường, container không biết record cụ thể nào trong batch thất bại.

Do đó có hai đường xử lý chính:

1. **Không xác định được record lỗi**: handler dùng fallback batch retry và thử lại toàn bộ batch.
2. **Xác định được record lỗi**: listener ném BatchListenerFailedException kèm index hoặc record lỗi để handler xử lý phần batch trước và phần còn lại riêng biệt.

~~~mermaid
flowchart TD
    A["Batch listener nhận batch"] --> B["Listener xử lý records"]
    B --> C{"Có exception?"}
    C -->|Không| D["Container xử lý commit theo AckMode"]
    C -->|Có| E{"Có BatchListenerFailedException?"}
    E -->|Không| F["Fallback batch retry"]
    F --> G["Retry toàn bộ batch theo BackOff"]
    G --> H{"Đã hết retry?"}
    H -->|Chưa| B
    H -->|Rồi| I["Recovery theo cấu hình handler"]
    E -->|Có| J["Xác định failed index/record"]
    J --> K["Commit phần trước record lỗi"]
    K --> L["Retry record lỗi và phần còn lại"]
    L --> M{"Retry thành công?"}
    M -->|Có| N["Tiếp tục xử lý batch"]
    M -->|Không| O["Recover record lỗi theo policy"]
~~~

Sơ đồ mô tả hai chiến lược ở mức khái niệm. Chi tiết seek, giữ batch trong bộ nhớ, commit và recovery phụ thuộc cấu hình container cũng như phiên bản Spring Kafka.

## 3. Retry toàn bộ batch khi không biết record lỗi

Nếu batch listener ném exception thông thường, ví dụ **RuntimeException**, handler không biết record nào gây lỗi. Với fallback batch handler, Spring Kafka retry toàn bộ batch theo BackOff.

Ví dụ batch có năm record:

| Vị trí | Record | Kết quả lần đầu |
|---:|---|---|
| 0 | order-101 | Xử lý thành công |
| 1 | order-102 | Xử lý thành công |
| 2 | order-103 | Xử lý thành công |
| 3 | order-104 | Gây exception |
| 4 | order-105 | Chưa xử lý |

Nếu listener chỉ ném **RuntimeException**, handler không biết record 3 là nguyên nhân. Toàn bộ batch có thể được retry, bao gồm order-101, order-102 và order-103 đã hoàn tất ở lần gọi trước.

### 3.1 Tác động của retry toàn batch

Ưu điểm:

- Listener không cần xác định index lỗi.
- Phù hợp với lỗi ảnh hưởng toàn bộ batch, ví dụ database unavailable hoặc service downstream timeout.
- Dễ giữ nguyên logic xử lý batch khi thao tác chỉ hoàn tất hoặc thất bại ở cấp nhóm.

Hạn chế:

- Record đã xử lý thành công có thể bị xử lý lại.
- Batch lớn làm chi phí retry cao.
- Một poison record có thể khiến toàn bộ batch thất bại nhiều lần.
- Side effect có thể bị lặp nếu listener không idempotent.
- Thời gian phục hồi của batch phụ thuộc record chậm hoặc lỗi nhất.

Nếu batch listener ghi database từng record rồi mới xử lý record tiếp theo, một exception giữa batch có thể xảy ra sau khi một phần side effect đã commit. Retry toàn batch sẽ chạy lại phần đã hoàn tất. Cần dùng transaction database phù hợp hoặc idempotency key để xử lý an toàn.

### 3.2 FallbackBatchErrorHandler và retry trong bộ nhớ

Trong đường fallback batch retry, Spring Kafka có thể giữ batch cần retry trong bộ nhớ và tạm pause consumer trong khi thực hiện BackOff. Container tiếp tục poll theo cơ chế cần thiết để giữ consumer sống trong group, sau đó gọi lại listener với batch đó.

Điều này khác với việc đơn giản seek toàn bộ partition rồi đợi một poll mới tạo batch khác. Mục đích là retry đúng batch đã thất bại khi chưa xác định được record gây lỗi.

Vì batch được giữ để retry, cần chú ý:

- Batch có thể chiếm bộ nhớ trong suốt thời gian retry.
- Backoff dài làm tăng thời gian xử lý của batch.
- Consumer cần tiếp tục duy trì lifecycle và poll theo cơ chế container.
- Các partition thuộc consumer có thể bị ảnh hưởng trong lúc batch đang retry.
- Retry toàn batch có thể lặp lại side effect đã xảy ra trước exception.

Chi tiết hành vi fallback có thể thay đổi theo phiên bản. Cần xác nhận cách handler được cấu hình và kiểm thử trên version đang triển khai.

## 4. Xác định record lỗi bằng BatchListenerFailedException

Nếu listener biết chính xác record nào thất bại, hãy ném **BatchListenerFailedException** với index hoặc record tương ứng. Điều này giúp DefaultErrorHandler xử lý batch theo ranh giới record.

Ví dụ batch listener nhận danh sách ConsumerRecord:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "ordersBatchListenerFactory"
)
public void handle(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record = records.get(index);

        try {
            orderService.process(record.value());
        }
        catch (Exception ex) {
            throw new BatchListenerFailedException(
                "Failed to process order at batch index " + index,
                ex,
                index
            );
        }
    }
}
~~~

Ví dụ dùng constructor có message, cause và index; hãy xác nhận constructor phù hợp với Spring Kafka version của dự án.

Khi handler nhận BatchListenerFailedException, nó biết vị trí record lỗi trong batch:

- Các record đứng trước index lỗi có thể được commit theo cơ chế batch error handling.
- Record lỗi và các record sau nó được xử lý lại.
- Nếu retry record lỗi hết số lần cho phép, recoverer có thể xử lý record đó theo policy.
- Sau khi record lỗi được recover thành công, phần còn lại của batch có thể tiếp tục.

Điều này giúp tránh chạy lại những record đã được xác nhận hoàn tất trước record lỗi.

### 4.1 Chọn index chính xác

Index phải tương ứng với vị trí record trong batch mà listener nhận. Không dùng offset Kafka làm index. Offset là vị trí trong partition, còn index là vị trí phần tử trong danh sách.

Ví dụ:

| Index trong batch | Topic-partition | Offset |
|---:|---|---:|
| 0 | orders-0 | 501 |
| 1 | orders-1 | 207 |
| 2 | orders-0 | 502 |
| 3 | orders-2 | 91 |

Index 2 không có nghĩa offset 2. Nếu record lỗi ở phần tử thứ ba, index truyền vào exception là 2.

Nếu listener lọc, sort hoặc chuyển batch thành một danh sách khác trước khi xử lý, cần giữ mapping về batch gốc. Nếu index sai, handler có thể commit nhầm phần đã xử lý hoặc retry sai phạm vi.

### 4.2 Xác định record bằng ConsumerRecord

Khi phù hợp với phiên bản Spring Kafka, BatchListenerFailedException có thể nhận ConsumerRecord lỗi thay vì index. Cách này hữu ích khi listener thao tác với record metadata và muốn tránh nhầm lẫn giữa index đã biến đổi với batch gốc.

Dù dùng index hay record, listener phải cung cấp đúng record nằm trong batch hiện tại. Nếu không xác định được record lỗi một cách chắc chắn, dùng fallback batch retry là an toàn hơn việc đoán index.

## 5. Quy trình xử lý khi record lỗi được xác định

Giả sử batch có các record theo thứ tự:

| Index | Record | Kết quả |
|---:|---|---|
| 0 | A | Thành công |
| 1 | B | Thành công |
| 2 | C | Thất bại |
| 3 | D | Chưa xử lý |
| 4 | E | Chưa xử lý |

Listener ném BatchListenerFailedException với index 2.

Về nguyên tắc, DefaultErrorHandler có thể:

1. Commit offset của các record trước C đã được xử lý thành công.
2. Retry từ record C và các record phía sau.
3. Nếu C xử lý thành công, tiếp tục D và E.
4. Nếu C tiếp tục lỗi đến khi hết BackOff, gọi recoverer theo cấu hình.
5. Nếu recovery thành công, commit vị trí tương ứng và tiếp tục xử lý phần còn lại theo container flow.

Các record trước lỗi không cần bị chạy lại trong trường hợp handler nhận đúng failed index và commit thành công. Tuy nhiên, nếu batch trải trên nhiều partition, commit offset được thực hiện theo từng topic-partition và thứ tự offset của từng partition. Không diễn giải index như một offset toàn cục.

### 5.1 Vì sao các record phía sau cũng được retry?

Listener xử lý batch theo một lần poll. Khi record C lỗi, D và E chưa được xác nhận hoàn tất. Container cần đảm bảo các record đó vẫn được xử lý sau khi C được retry hoặc recover.

Nếu chỉ bỏ C rồi commit tất cả offset phía sau, ứng dụng có thể mất xử lý D và E. Do đó, phần từ record lỗi trở đi phải được xử lý theo trình tự phù hợp với offset và partition.

### 5.2 Nếu record lỗi được recover

Sau khi hết retry, recoverer có thể chuyển record lỗi sang DLT hoặc thực hiện một hành động recovery khác. Nếu recovery hoàn tất theo policy, handler có thể coi record lỗi đã được xử lý và tiến hành commit offset tương ứng.

Nếu recoverer ném exception hoặc publish DLT thất bại, không nên xem record đã được recover. Handler cần giữ khả năng xử lý lại theo semantics offset để tránh mất record.

Cần kiểm tra log và metric của recoverer, đặc biệt khi DLT broker/topic không khả dụng. Recovery thất bại là một sự cố xử lý riêng.

## 6. Cấu hình DefaultErrorHandler cho batch listener

DefaultErrorHandler nhận một recoverer và một BackOff. Có thể dùng FixedBackOff để retry với khoảng thời gian cố định, hoặc ExponentialBackOff để tăng thời gian chờ giữa các lần thử.

Ví dụ:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) ->
                new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
        );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

Ví dụ này minh họa cấu hình recoverer gửi record lỗi sang topic có hậu tố **.DLT**, giữ partition number nguồn. Topic DLT phải tồn tại và có đủ partition tương ứng; cần cấu hình replication, retention, ACL và monitoring cho DLT.

**FixedBackOff(1_000L, 2L)** có nghĩa khoảng chờ 1 giây và tối đa 2 lần retry sau lần xử lý ban đầu. Tổng cộng có thể có 3 lần thực thi listener cho cùng một record trong đường retry tương ứng: lần đầu và hai lần thử lại.

### 6.1 Gắn handler vào listener factory

Đăng ký CommonErrorHandler trên factory dùng cho batch listener:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersBatchListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        CommonErrorHandler ordersErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setCommonErrorHandler(ordersErrorHandler);

    return factory;
}
~~~

Nếu có nhiều factory, phải gắn handler vào đúng factory mà listener đang sử dụng. Một bean DefaultErrorHandler tồn tại trong application context không có nghĩa mọi listener tự động sử dụng nó.

### 6.2 FixedBackOff và ExponentialBackOff

**FixedBackOff** giữ khoảng chờ cố định:

~~~java
new FixedBackOff(1_000L, 3L)
~~~

Nghĩa là chờ 1 giây giữa các lần retry, tối đa 3 lần retry.

**ExponentialBackOff** tăng thời gian chờ theo cấp số nhân:

~~~java
ExponentialBackOff backOff = new ExponentialBackOff(1_000L, 2.0);
backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);
~~~

Ví dụ bắt đầu 1 giây, hệ số nhân 2 và khoảng chờ tối đa 10 giây. Cấu hình thực tế cần kiểm tra API và giới hạn của phiên bản Spring Framework/Spring Kafka đang dùng.

BackOff nên được chọn theo loại lỗi:

- Database tạm thời unavailable: có thể dùng exponential backoff.
- Rate limit: cần tôn trọng thời gian retry do downstream yêu cầu.
- Lỗi dữ liệu cố định: retry nhiều lần thường không giúp ích.
- Lỗi cấu hình hoặc authentication diện rộng: cần dừng retry dồn dập và sửa nguyên nhân.

## 7. Phân loại exception: retryable và non-retryable

Không phải exception nào cũng nên retry. DefaultErrorHandler có cơ chế phân loại exception để quyết định lỗi nào có thể retry và lỗi nào cần đi thẳng đến recovery.

Ví dụ:

- Timeout database hoặc network có thể tạm thời.
- Rate limit có thể phục hồi sau backoff.
- Payload không hợp lệ có thể không thể tự sửa bằng retry.
- Lỗi mapping hoặc validation có thể là lỗi dữ liệu hoặc lỗi code.
- Authentication failure thường cần sửa credential hoặc cấu hình.

Có thể thêm exception vào nhóm không retry:

~~~java
handler.addNotRetryableExceptions(
    IllegalArgumentException.class,
    IllegalStateException.class
);
~~~

Hoặc thêm loại exception cần retry theo policy của ứng dụng:

~~~java
handler.addRetryableExceptions(
    TransientDataAccessException.class,
    TimeoutException.class
);
~~~

Đây là ví dụ phân loại; không nên sao chép danh sách exception mà chưa hiểu nguyên nhân và tính phục hồi của từng lỗi. Spring Kafka có các nhóm exception được xem là fatal/non-retryable theo mặc định và danh sách có thể thay đổi theo version.

### 7.1 BatchListenerFailedException là tín hiệu về vị trí lỗi

BatchListenerFailedException không chỉ là một exception nghiệp vụ. Nó là tín hiệu cho error handler biết record nào trong batch thất bại.

Nếu listener biết index lỗi, dùng exception này. Nếu listener chỉ ném IllegalStateException hoặc RuntimeException chung, handler không có thông tin để xác định record và có thể retry toàn bộ batch.

Không nên bắt mọi exception rồi bọc với index 0. Điều đó có thể làm handler tưởng record đầu tiên thất bại dù lỗi thực tế xảy ra sau nhiều record, dẫn đến commit/retry sai phạm vi.

### 7.2 Tránh retry vô hạn

Retry vô hạn có thể làm:

- Batch bị giữ và không tiến triển.
- Partition lag tăng.
- Consumer dành phần lớn thời gian cho một record lỗi.
- Downstream bị gọi lặp và quá tải.
- Các record phía sau bị chặn.
- Alert và recovery trở nên khó kiểm soát.

Hãy chọn số lần retry, tổng thời gian retry và hành động sau khi hết retry. Nếu lỗi có thể kéo dài hàng giờ, nên cân nhắc tách record ra DLT hoặc dùng quy trình xử lý lại riêng.

## 8. Dead Letter Topic và batch recovery

DLT thường được dùng để cô lập record không thể xử lý sau khi retry. Với batch listener, cần hiểu rõ handler đang recovery một record được xác định hay đang xử lý fallback batch.

### 8.1 Recovery theo failed record

Khi listener ném BatchListenerFailedException với đúng record/index, handler có thông tin về record lỗi. Recoverer như DeadLetterPublishingRecoverer có thể publish record đó đến DLT theo routing strategy.

Một chiến lược thường dùng là:

~~~text
orders-0  -> orders.DLT-0
orders-1  -> orders.DLT-1
orders-2  -> orders.DLT-2
~~~

Giữ partition number có thể hữu ích cho replay theo partition, nhưng chỉ hoạt động nếu DLT có đủ partition. Nếu DLT có ít partition hơn nguồn, publish có thể thất bại hoặc routing không đúng như mong muốn.

### 8.2 Recovery sau fallback batch retry

Khi không có failed index, handler retry toàn bộ batch. Hành vi recovery cuối cùng phụ thuộc batch fallback handler và recoverer được cấu hình. Không nên mặc định rằng một exception toàn batch sẽ tự động cho biết record nào cần gửi DLT.

Nếu cần xử lý từng record lỗi và gửi đúng record vào DLT, listener nên xác định failed record và ném BatchListenerFailedException. Nếu lỗi thật sự là lỗi toàn batch, cần có recovery policy cho batch phù hợp và kiểm thử với đúng phiên bản Spring Kafka.

### 8.3 DLT phải được vận hành như topic chính

Cần có:

- Replication factor phù hợp.
- Retention đủ dài cho thời gian điều tra.
- ACL riêng cho publisher và operator replay.
- Alert khi DLT tăng nhanh hoặc publish thất bại.
- Metadata nguồn: topic, partition, offset, exception và event id.
- Runbook sửa dữ liệu, replay và xác nhận side effect.

Không xem record đã vào DLT là nghiệp vụ đã hoàn tất. DLT là vùng cách ly để điều tra và xử lý tiếp.

## 9. Batch listener, acknowledgment và offset commit

Batch retry liên quan trực tiếp đến offset. Cần hiểu khi nào container xem batch là hoàn tất và khi nào commit offset.

### 9.1 Batch ack mode

Với batch listener, container thường xử lý commit theo batch: khi listener trả về thành công, offset của các record trong batch được commit theo AckMode và cấu hình container.

**AckMode.RECORD** không phù hợp với batch listener vì listener xử lý cả batch trong một lần gọi. Với batch listener, thường dùng **BATCH** hoặc manual acknowledgment theo semantics mà ứng dụng cần.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
~~~

Tắt auto commit giúp container quản lý offset theo ack mode. Nó không tự quyết định record nào trong batch đã thành công khi listener ném exception. Đối với partial batch failure, BatchListenerFailedException cung cấp thông tin vị trí cần thiết.

### 9.2 Manual acknowledgment

Batch listener có thể dùng Acknowledgment khi cần kiểm soát thời điểm xác nhận. Tuy nhiên, không nên gọi ack trước khi mọi side effect được bảo đảm hoàn tất.

Ví dụ nguy hiểm:

1. Listener nhận batch.
2. Gửi công việc sang executor.
3. Gọi ack ngay.
4. Process chết trước khi executor hoàn tất.

Offset đã commit nhưng business effect có thể chưa được thực hiện. Nếu dùng manual ack hoặc async processing, cần gắn acknowledgment với kết quả thực tế và hiểu rõ thread-safety/lifecycle của Acknowledgment theo phiên bản framework.

### 9.3 Commit phần trước record lỗi

Khi dùng BatchListenerFailedException, handler có thể commit các record trước failed index. Việc commit được thực hiện theo offset từng partition, không phải một số index duy nhất.

Nếu batch có record từ nhiều partition, một partition có thể có nhiều record và offset khác nhau. Cần hiểu commit offset là vị trí tiếp theo cần đọc của mỗi partition. Không tự tính offset bằng index + 1.

### 9.4 Rebalance trong lúc retry

Nếu retry kéo dài, consumer vẫn phải đáp ứng poll/heartbeat/lifecycle requirements. Fallback batch retry có cơ chế pause/poll theo framework để duy trì consumer, nhưng cần cấu hình thời gian xử lý và timeout phù hợp.

Nếu consumer mất group membership trong khi retry, partition có thể được gán cho member khác và record chưa commit được giao lại. Vì vậy, listener phải idempotent ngay cả khi dùng partial batch retry.

## 10. Database transaction và side effect khi retry batch

Batch listener thường được dùng để bulk write database. Cần quyết định liệu batch được xử lý nguyên tử ở database hay mỗi record commit riêng.

### 10.1 Một database transaction cho toàn batch

Nếu toàn bộ batch nằm trong một database transaction, một lỗi giữa chừng có thể rollback tất cả thay đổi trong batch. Retry toàn batch có thể phù hợp vì side effect của lần trước đã được rollback.

Ví dụ:

~~~java
@Transactional
public void processBatch(List<OrderCreated> events) {
    for (OrderCreated event : events) {
        repository.save(toEntity(event));
    }
}
~~~

Đoạn code minh họa transaction ở database. Cần bảo đảm listener thực sự gọi qua proxy transaction của Spring và transaction boundary bao phủ toàn bộ batch.

Nếu transaction rollback hoàn toàn, việc retry batch không tạo duplicate từ các thay đổi đã rollback. Tuy nhiên, các side effect ngoài database transaction như HTTP call hoặc email vẫn có thể đã xảy ra.

### 10.2 Mỗi record commit riêng

Nếu listener xử lý và commit từng record riêng, một phần batch có thể đã được ghi bền vững trước khi record sau thất bại.

Trong trường hợp này:

- Retry toàn batch có thể ghi lại các record trước đó.
- Partial retry với BatchListenerFailedException giảm phần phải xử lý lại.
- Idempotency hoặc unique constraint vẫn cần để bảo vệ duplicate.
- Cần ghi nhận event id và trạng thái xử lý để đối chiếu.

Không giả định annotation @Transactional ở một method con sẽ làm toàn bộ batch thành một transaction nếu method được gọi nội bộ trong cùng bean và không đi qua Spring proxy.

### 10.3 Idempotency key

Một cách bảo vệ là dùng event id hoặc business key duy nhất. Ví dụ database có unique constraint trên event_id. Khi record được giao lại, ứng dụng phát hiện event đã được xử lý và không tạo side effect lần nữa.

Idempotency nên nằm ở ranh giới ghi dữ liệu hoặc gọi downstream, không chỉ dựa vào một biến trong bộ nhớ. Sau restart, bộ nhớ mất đi nhưng duplicate record vẫn có thể được giao lại.

## 11. Chọn retry toàn batch hay partial batch retry

Hai chiến lược phù hợp với các loại lỗi khác nhau.

| Tiêu chí | Retry toàn batch | Partial batch retry |
|---|---|---|
| Biết record lỗi | Không cần | Cần biết chính xác |
| Exception điển hình | RuntimeException chung | BatchListenerFailedException |
| Phạm vi xử lý lại | Toàn batch | Record lỗi và phần sau |
| Record trước lỗi | Có thể chạy lại | Có thể commit và không cần chạy lại |
| Độ phức tạp listener | Thấp hơn | Cao hơn vì phải giữ đúng index/record |
| Phù hợp | Lỗi toàn batch hoặc không xác định được record | Lỗi riêng lẻ có thể định vị |
| Rủi ro duplicate | Cao hơn nếu side effect trước lỗi đã commit | Thấp hơn nhưng vẫn cần idempotency |
| Thứ tự xử lý | Retry cả nhóm | Giữ phần trước lỗi, xử lý lại từ lỗi trở đi |

### 11.1 Khi nên retry toàn batch?

- Database hoặc downstream đang unavailable cho toàn batch.
- Batch processing có transaction nguyên tử.
- Không thể xác định record lỗi một cách đáng tin cậy.
- Chi phí retry cả batch thấp.
- Listener được thiết kế idempotent.

### 11.2 Khi nên partial retry?

- Listener xử lý từng record tuần tự và có thể xác định chính xác lỗi.
- Một record dữ liệu không hợp lệ gây lỗi nhưng các record trước đã hoàn tất.
- Batch lớn, retry toàn batch tốn kém.
- Muốn chuyển đúng record lỗi sang DLT.
- Có thể giữ mapping index và metadata gốc chính xác.

Nếu lỗi là lỗi hệ thống áp dụng cho mọi record, không nên cố gắng gán nó cho một index bất kỳ. Hãy để handler retry toàn batch theo backoff và phục hồi dependency.

## 12. Batch size, concurrency và thời gian retry

Retry batch có thể ảnh hưởng throughput lớn hơn retry một record. Cần điều chỉnh batch size và concurrency cùng nhau.

### 12.1 Batch size lớn

Batch lớn giúp amortize overhead và có thể tăng throughput, nhưng:

- Listener cần nhiều thời gian hơn để xử lý.
- Một record lỗi có thể khiến nhiều record bị retry.
- Bộ nhớ cần để giữ batch lớn hơn.
- Database transaction có thể kéo dài.
- Dễ vượt thời gian poll nếu xử lý chậm.

### 12.2 Concurrency cao

Tăng concurrency tạo nhiều consumer và nhiều batch listener invocation song song. Điều này có thể làm downstream nhận nhiều batch đồng thời.

Ví dụ ba pod, mỗi pod concurrency 4, có thể có tối đa 12 consumer cùng xử lý batch. Nếu mỗi batch có tối đa 100 record, số record đang nằm trong các lần xử lý có thể lớn. Không có nghĩa luôn có 1.200 record đang xử lý, nhưng con số này cho thấy mức tải tối đa cần tính khi thiết kế.

### 12.3 max.poll.interval.ms

Nếu thời gian xử lý batch quá dài, consumer có thể vượt max.poll.interval.ms và bị coi là không tiếp tục poll đúng hạn. Group có thể rebalance, partition được gán lại và record chưa commit bị giao lại.

Cần đo p95/p99 processing duration của batch, số record mỗi batch và thời gian retry. Đặt max.poll.interval.ms có khoảng dự phòng phù hợp; không dùng giá trị rất lớn để che listener bị treo vô hạn.

## 13. Quan sát batch retry trong production

Theo dõi theo listener, group, topic, partition và child consumer để xác định batch nào đang retry.

Các tín hiệu nên có:

| Nhóm | Metrics/log cần quan sát |
|---|---|
| Batch listener | Batch size, processing duration, batch success/error count |
| Retry | Retry count, backoff duration, exception type, lần thử hiện tại |
| Recovery | Recovery success/failure, DLT publish rate, recoverer exception |
| Consumer | Consumer lag, poll interval, rebalance, commit latency |
| Partition | Assigned partition, offset tiến triển, partition bị kẹt |
| Downstream | Database pool, query latency, timeout, HTTP error rate |
| Business | Event id, batch id, số record thành công, số record lỗi, duplicate detection |

Khi log batch failure, nên ghi:

- Listener id và group id.
- Topic, partition, offset của failed record.
- Batch index nếu có.
- Event id/business key.
- Exception class và root cause.
- Số lần retry hoặc recovery attempt.

Không log toàn bộ payload nhạy cảm. Dùng event id và metadata để truy vết.

### 13.1 Phân biệt lỗi batch với lỗi một record

Nếu nhiều batch cùng lỗi với cùng exception như database timeout, có thể downstream đang gặp sự cố diện rộng. Nếu chỉ một event id liên tục lỗi trong khi các record khác bình thường, có thể là poison record hoặc dữ liệu không hợp lệ.

Đừng tăng retry count chỉ dựa trên số lần lỗi. Cần phân loại root cause và phạm vi ảnh hưởng.

### 13.2 Theo dõi tiến triển sau recovery

Sau khi record được chuyển DLT hoặc recovery thành công, xác nhận:

- Offset của partition tiếp tục tăng.
- Consumer lag giảm.
- Record phía sau được xử lý.
- DLT publish thành công.
- Side effect nghiệp vụ không bị nhân đôi.
- Không có recovery exception bị bỏ qua.

## 14. Quy trình điều tra khi batch listener retry liên tục

Khi listener retry batch nhiều lần hoặc partition không tiến triển:

1. Xác định listener id, group id, topic, partition và thời điểm bắt đầu.
2. Ghi nhận batch size, các offset và event id trong batch.
3. Xác định listener ném exception thông thường hay BatchListenerFailedException.
4. Nếu dùng BatchListenerFailedException, xác nhận index/record đúng với batch gốc.
5. Xem BackOff, số lần retry và exception classification.
6. Kiểm tra record lỗi có phải poison message hay lỗi downstream diện rộng.
7. Đối chiếu database transaction, connection pool và các side effect đã hoàn tất.
8. Kiểm tra consumer poll interval, rebalance và offset commit.
9. Xác nhận recoverer/DLT có hoạt động và topic đích có đủ partition.
10. Sau khi sửa lỗi, xác nhận batch tiến triển, offset commit đúng và duplicate được kiểm soát.

Không reset offset hoặc xóa record ngay khi thấy retry liên tục. Trước tiên xác định record nào lỗi, side effect nào đã xảy ra và batch đang được retry theo đường fallback hay partial failure.

## 15. Các hiểu nhầm cần tránh

**“Batch listener lỗi thì Spring luôn biết record nào gây lỗi.”** Sai. Nếu listener ném exception thông thường, handler không biết index; fallback batch retry có thể thử lại toàn bộ batch.

**“BatchListenerFailedException chỉ là exception khác tên.”** Sai. Nó cung cấp thông tin failed record/index cho error handler để xử lý partial batch.

**“Index trong BatchListenerFailedException là Kafka offset.”** Sai. Index là vị trí trong batch listener nhận; offset là vị trí record trong partition.

**“Các record trước record lỗi luôn được xử lý lại.”** Không nhất thiết. Khi failed index được xác định đúng, handler có thể commit phần trước lỗi và retry từ record lỗi trở đi.

**“Retry thành công có nghĩa side effect chỉ xảy ra một lần.”** Sai. Side effect có thể đã commit trước exception. Cần transaction hoặc idempotency.

**“DLT publish thành công nghĩa nghiệp vụ đã hoàn tất.”** Sai. DLT chỉ cô lập record để điều tra hoặc replay; nghiệp vụ vẫn cần quy trình xử lý tiếp.

**“Tăng max.poll.interval.ms sẽ chữa mọi batch retry.”** Sai. Nó chỉ thay đổi giới hạn thời gian giữa các lần poll; không sửa poison record, downstream outage hoặc listener bị treo.

**“Retry toàn batch luôn an toàn.”** Sai nếu các record trước lỗi đã tạo side effect bền vững. Cần transaction nguyên tử hoặc idempotency.

**“Concurrency càng cao thì batch retry càng nhanh.”** Không nhất thiết. Downstream có thể quá tải hơn và partition count vẫn giới hạn consumer assignment.

**“DefaultErrorHandler và transactional rollback handler luôn giống nhau.”** Sai. Với transactional listener, exception thường dẫn đến rollback Kafka transaction và việc xử lý sau rollback thuộc cơ chế AfterRollbackProcessor. Cần cấu hình theo transaction model thực tế.

## 16. Transactional batch listener: điểm cần phân biệt

DefaultErrorHandler thường được dùng cho container không chạy transaction. Nếu listener container dùng Kafka transaction, exception trong listener làm transaction rollback. Spring Kafka sử dụng cơ chế sau rollback, thường là DefaultAfterRollbackProcessor, để xử lý redelivery/recovery theo cấu hình.

Do đó:

- Không mặc định DefaultErrorHandler là cơ chế duy nhất xử lý lỗi cho transactional container.
- Phân biệt transaction Kafka với transaction database.
- Xác định batch input offset và output record có nằm trong cùng Kafka transaction hay không.
- Kiểm tra recovery/DLT có được publish trong transaction mới hay không.
- Kiểm thử rollback và redelivery trên đúng factory và Spring Kafka version.

Nếu batch listener consume input rồi produce output trong transaction, lỗi ở bất kỳ record nào có thể làm transaction rollback theo thiết kế. Khi đó, các output trong transaction không được consumer read_committed nhìn thấy và input offset chưa được commit trong transaction đó. Side effect ngoài Kafka vẫn cần idempotency/outbox hoặc cơ chế phối hợp riêng.

## 17. Kiểm thử retry batch listener

Nên kiểm thử trong môi trường tích hợp với topic có nhiều partition và record id dễ truy vết.

### 17.1 Retry toàn batch

- Cấu hình batch listener và DefaultErrorHandler với FixedBackOff.
- Gửi một batch có nhiều record.
- Khi xử lý một record, ném exception thông thường.
- Xác nhận fallback retry gọi lại listener với batch theo hành vi version đang dùng.
- Xác nhận record trước lỗi có thể được xử lý lại.
- Kiểm tra idempotency hoặc transaction bảo vệ side effect.

### 17.2 Partial batch retry

- Gửi batch có ít nhất năm record.
- Xử lý thành công hai record đầu.
- Cố ý làm record thứ ba thất bại.
- Ném BatchListenerFailedException với index đúng.
- Xác nhận offset của phần trước lỗi được commit theo handler semantics.
- Xác nhận record lỗi và phần sau được xử lý lại.
- Khôi phục record lỗi và xác nhận batch tiếp tục tiến triển.

### 17.3 Recovery và DLT

- Cấu hình recoverer gửi failed record vào DLT.
- Làm record tiếp tục thất bại đến khi hết retry.
- Xác nhận DLT nhận đúng event id, topic, partition, offset và exception metadata.
- Tạm làm DLT không khả dụng để kiểm tra recovery failure.
- Xác nhận record không bị coi là recovered khi publish thất bại.
- Replay một record sau khi sửa dữ liệu và kiểm tra duplicate.

### 17.4 Exception classification

- Gửi record gây transient exception và xác nhận retry.
- Gửi record gây non-retryable exception và xác nhận đi theo recovery policy.
- Xác nhận lỗi downstream không tạo retry storm.
- Kiểm tra log cho biết exception class và retry count.

### 17.5 Rebalance và poll interval

- Tạo batch processing duration gần giới hạn poll interval.
- Kiểm tra consumer có bị rebalance không.
- Tạo backoff đủ dài để quan sát lifecycle container.
- Xác nhận container tiếp tục poll/pause theo cơ chế framework.
- Kiểm tra record chưa commit được giao lại an toàn sau restart.

Không chạy fault injection trên production nếu chưa có phạm vi, phê duyệt và cơ chế dừng. Mỗi bài kiểm thử cần có expected result, batch id, event id, offset và bằng chứng recovery.

## 18. Checklist cấu hình và vận hành

**Batch listener**

- [ ] Factory đúng listener được cấu hình batch mode.
- [ ] Batch size phù hợp với throughput, memory và processing time.
- [ ] Listener không giả định index batch bằng Kafka offset.
- [ ] Nếu xác định được failed record, listener ném BatchListenerFailedException đúng index/record.
- [ ] Nếu không xác định được record lỗi, retry toàn batch được chấp nhận và side effect idempotent.

**DefaultErrorHandler**

- [ ] BackOff có số lần retry và khoảng chờ rõ ràng.
- [ ] Retryable và non-retryable exceptions được phân loại.
- [ ] Recoverer được cấu hình và kiểm thử.
- [ ] DLT có đủ partition nếu giữ partition number nguồn.
- [ ] Recovery failure không bị xem là thành công.
- [ ] Transactional container dùng cơ chế rollback/recovery phù hợp.

**Offset và side effect**

- [ ] Ack mode phù hợp với batch listener.
- [ ] Offset chỉ được commit sau khi phần xử lý tương ứng hoàn tất.
- [ ] Partial batch commit được hiểu theo từng topic-partition.
- [ ] Database transaction boundary rõ ràng.
- [ ] Event id hoặc idempotency key bảo vệ duplicate.
- [ ] Async work không được ack trước khi hoàn tất.

**Quan sát và kiểm thử**

- [ ] Có metrics cho batch size, processing duration, retry và recovery.
- [ ] Log có listener id, group id, topic, partition, offset và event id.
- [ ] Theo dõi consumer lag, rebalance và poll interval.
- [ ] Đã kiểm thử fallback batch retry và partial batch retry.
- [ ] Đã kiểm thử DLT failure, replay và duplicate handling.
- [ ] Có runbook điều tra batch bị kẹt và recovery không thành công.

Batch retry cần được chọn theo khả năng xác định record lỗi và ranh giới side effect. Khi lỗi ảnh hưởng cả batch hoặc không thể xác định vị trí lỗi, retry toàn batch là đường xử lý phù hợp nếu side effect an toàn khi lặp. Khi xác định được record lỗi, BatchListenerFailedException cho phép DefaultErrorHandler commit phần đã xử lý trước đó và retry từ vị trí lỗi. Kết hợp BackOff hữu hạn, recovery rõ ràng, offset commit đúng thời điểm và idempotency giúp batch listener tiếp tục tiến triển mà vẫn bảo vệ dữ liệu nghiệp vụ.

