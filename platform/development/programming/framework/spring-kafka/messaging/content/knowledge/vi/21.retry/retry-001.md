# Retry đồng bộ trong listener

Trong Spring Kafka, retry đồng bộ là cách thử xử lý lại record ngay trong luồng tiêu thụ của listener container khi listener ném exception. Container giữ quyền điều khiển việc đọc và xác nhận offset, áp dụng backoff giữa các lần thử rồi quyết định tiếp tục, recover record hoặc chuyển record sang dead-letter topic (DLT).

Cách tiếp cận này thường được triển khai bằng **DefaultErrorHandler** và một chính sách **BackOff**. Retry diễn ra trên luồng consumer đang xử lý partition đó, vì vậy nó dễ triển khai và giữ được thứ tự xử lý trong partition theo cơ chế mặc định. Đổi lại, thời gian retry làm chậm consumer đang sở hữu partition; nếu chờ quá lâu, consumer có thể trễ poll, gây lag hoặc rebalance.

Bài học thuộc chương **Retry** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách cấu hình retry đồng bộ trong listener, phân loại lỗi có thể thử lại, kiểm soát số lần thử và phục hồi record thất bại an toàn.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích retry đồng bộ trong listener container hoạt động như thế nào.
- Phân biệt lần giao record đầu tiên với các lần redelivery.
- Cấu hình DefaultErrorHandler cùng FixedBackOff hoặc backoff có giới hạn.
- Phân loại exception tạm thời và exception không thể phục hồi.
- Hiểu cách seek và redelivery ảnh hưởng tới offset, partition và thứ tự.
- Chuyển record hết retry sang DLT bằng DeadLetterPublishingRecoverer.
- Đánh giá tác động của backoff tới poll loop, consumer lag và rebalance.
- Thiết kế listener idempotent để chịu được xử lý lặp.
- Phân biệt blocking retry với non-blocking retry bằng retry topic.
- Kiểm thử số lần retry, recovery, DLT và offset commit.

## 1. Retry đồng bộ là gì?

Consumer poll record từ Kafka và listener container gọi phương thức listener để xử lý. Nếu listener hoàn tất bình thường, container tiếp tục theo AckMode và commit offset phù hợp. Nếu listener ném exception, container chuyển lỗi cho CommonErrorHandler.

Với DefaultErrorHandler, container có thể chờ theo BackOff, sau đó giao lại record để listener thử xử lý lần nữa. Quá trình này được gọi là blocking hoặc synchronous retry vì luồng consumer xử lý record đó phải chờ các lần thử hoàn tất trước khi tiếp tục bình thường.

~~~mermaid
flowchart TD
    P[Consumer poll] --> L[Invoke listener]
    L --> S{Listener succeeds?}
    S -->|Yes| C[Commit according to AckMode]
    S -->|No| E[DefaultErrorHandler]
    E --> B[Wait according to BackOff]
    B --> R{Retries remain?}
    R -->|Yes| L
    R -->|No| D[Recover record]
    D --> DL[Continue or publish to DLT]
~~~

Retry đồng bộ phù hợp khi lỗi có khả năng tự hết sau một khoảng ngắn, ví dụ:

- Database tạm thời không nhận kết nối.
- HTTP service trả về lỗi 503 trong thời gian ngắn.
- Một dependency bị timeout do tải tăng đột biến.
- Resource tạm thời chưa sẵn sàng.

Nếu record chứa dữ liệu sai, thiếu field bắt buộc hoặc vi phạm quy tắc nghiệp vụ cố định, thử lại cùng payload thường không giải quyết được nguyên nhân. Những lỗi này nên được phân loại không retry hoặc chỉ retry rất hạn chế rồi recover.

## 2. Luồng xử lý của DefaultErrorHandler

DefaultErrorHandler là error handler phổ biến của Spring Kafka cho listener container không dùng transaction. Nó quản lý retry, backoff, phân loại exception và recovery sau khi hết số lần thử.

Các bước tổng quát:

1. Consumer poll record.
2. Container gọi listener.
3. Listener ném exception.
4. DefaultErrorHandler nhận exception và xác định chính sách retry.
5. BackOff quyết định khoảng chờ và số lần thử tiếp theo.
6. Container seek/redeliver record theo cơ chế error handler.
7. Nếu lần thử thành công, container tiếp tục xử lý.
8. Nếu hết retry, recoverer được gọi để xử lý record cuối cùng.

Trong record listener, error handler có thể seek về offset lỗi và các record chưa xử lý trong poll để chúng được giao lại. Vì vậy, khi một record lỗi, các record phía sau trong cùng partition có thể phải chờ record đó xử lý xong. Điều này giúp giữ thứ tự mặc định trong partition.

Không nên hiểu retry là vòng lặp tự gọi lại phương thức listener trong cùng một stack frame. Với DefaultErrorHandler, việc redelivery được phối hợp với consumer poll/seek của container.

## 3. Cấu hình FixedBackOff

FixedBackOff dùng một khoảng chờ cố định giữa các lần thử và số lần retry tối đa.

Ví dụ cấu hình listener container:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltKafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()
                    )
            );

    FixedBackOff backOff = new FixedBackOff(
            1_000L, // chờ 1 giây giữa các lần retry
            2L     // tối đa 2 lần retry sau lần giao đầu
    );

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Gắn error handler vào factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
orderKafkaListenerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Với cấu hình minh họa trên, record được giao lần đầu, sau đó có tối đa hai lần retry với khoảng chờ một giây giữa các lần retry. Nếu vẫn thất bại, recoverer được gọi.

Số lần retry không bao gồm lần giao đầu tiên. Khi mô tả chính sách cho đội vận hành, nên ghi rõ “2 retries” hay “3 total deliveries” để tránh hiểu nhầm.

DLT template và destination resolver cần phù hợp với key/value serializer và số partition của topic đích. Nếu không muốn dùng DLT, có thể cấu hình recoverer khác để ghi nhận lỗi hoặc bỏ qua record theo quyết định nghiệp vụ có chủ đích.

## 4. Cấu hình DefaultErrorHandler trong Spring Boot

Spring Boot cung cấp listener container factory tự động cấu hình. Có thể tạo bean DefaultErrorHandler rồi gắn vào factory tùy chỉnh như ví dụ trước, hoặc cấu hình factory qua cơ chế customizer phù hợp với phiên bản Spring Boot đang dùng.

Listener dùng factory:

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment",
            containerFactory = "orderKafkaListenerFactory"
    )
    public void consume(OrderCreatedEvent event) {
        orderService.handle(event);
    }
}
~~~

Nếu ứng dụng có nhiều listener với chính sách retry khác nhau, có thể tạo nhiều container factory và gắn từng listener vào factory tương ứng. Tránh dùng một error handler chung với backoff quá dài cho mọi luồng nếu SLA và loại lỗi của chúng khác nhau.

Trong Spring Kafka hiện đại, CommonErrorHandler là abstraction được listener container sử dụng. DefaultErrorHandler là implementation cho xử lý lỗi phổ biến. Các ví dụ cũ dùng SeekToCurrentErrorHandler thuộc các phiên bản trước; khi nâng cấp Spring Kafka, hãy dùng API tương thích với dependency hiện tại.

## 5. Phân loại exception: lỗi nào nên retry?

Không phải exception nào cũng nên retry. Cần phân loại dựa trên nguyên nhân và khả năng phục hồi.

| Loại lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Lỗi tạm thời | Timeout, HTTP 503, database connection reset | Retry có giới hạn và backoff. |
| Lỗi dữ liệu cố định | Payload sai, field bắt buộc thiếu, enum không hợp lệ | Không retry hoặc retry rất ít rồi DLT. |
| Lỗi nghiệp vụ không thể thay đổi bằng chờ | Đơn hàng đã hủy, trạng thái không cho phép | Recover hoặc chuyển xử lý nghiệp vụ riêng. |
| Lỗi cấu hình | Sai endpoint, credential hết hạn, schema mapping sai | Cảnh báo và sửa cấu hình; retry liên tục thường không giúp. |
| Lỗi phụ thuộc tải | Connection pool cạn, downstream quá tải | Retry có backoff, đồng thời giới hạn concurrency và tải. |

DefaultErrorHandler có phân loại một số exception không retry theo mặc định. Ứng dụng có thể bổ sung loại exception retryable hoặc non-retryable theo yêu cầu.

Ví dụ:

~~~java
DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));

handler.addNotRetryableExceptions(
        IllegalArgumentException.class
);

handler.addRetryableExceptions(
        TransientDataAccessException.class
);
~~~

Ví dụ coi IllegalArgumentException là lỗi không retry và TransientDataAccessException là lỗi có thể retry. Hãy chọn exception cụ thể của ứng dụng; không nên phân loại một lớp exception cha quá rộng vì có thể vô tình retry cả lỗi dữ liệu cố định.

Nếu cần quyết định retry theo nội dung record hoặc exception lồng nhau, có thể dùng exception classifier/backoff function của DefaultErrorHandler. Cấu hình đó cần được kiểm thử với exception thực tế mà listener phát ra.

## 6. Backoff và giới hạn retry

Backoff tạo khoảng nghỉ giữa các lần thử để tránh gọi dependency liên tục khi nó đang gặp sự cố.

Các lựa chọn thường gặp:

- Fixed backoff: khoảng nghỉ không đổi, dễ dự đoán.
- Exponential backoff: tăng khoảng nghỉ sau mỗi lần thất bại.
- Exponential backoff có giới hạn: tăng dần nhưng không vượt mức tối đa.
- Backoff có jitter: thêm độ ngẫu nhiên để nhiều consumer không retry cùng thời điểm.

Ví dụ một chuỗi exponential backoff có thể là 500 ms, 1 giây, 2 giây rồi dừng ở mức tối đa 5 giây. Các con số chỉ là minh họa; chính sách thực tế phải phù hợp với SLA và thời gian phục hồi của dependency.

Khi chọn backoff, hãy xác định:

1. Số lần retry sau lần giao đầu.
2. Khoảng chờ đầu tiên.
3. Hệ số tăng.
4. Khoảng chờ tối đa.
5. Tổng thời gian một record có thể bị giữ trong retry.
6. Hành động sau khi hết retry.

Không dùng retry vô hạn cho lỗi không xác định. Một record bị lỗi có thể giữ partition không tiến triển trong thời gian dài và làm consumer lag tăng liên tục.

## 7. Seek và redelivery ảnh hưởng tới partition như thế nào?

Kafka giữ thứ tự record trong từng partition. Khi một record thất bại, DefaultErrorHandler thường dùng seek để yêu cầu consumer đọc lại record lỗi và các record phía sau chưa được xử lý trong poll.

Ví dụ partition có các offset:

~~~text
Offset:       10   11   12   13
Processing:   OK   OK   FAIL ...
                         |
                         +-- retry offset 12
~~~

Nếu offset 12 thất bại, container có thể redeliver offset 12 trước khi xử lý tiếp offset 13. Khi retry thành công, consumer tiếp tục tiến lên.

Trong một consumer đang sở hữu nhiều partition, retry một record có thể ảnh hưởng thời gian xử lý các record khác được poll bởi consumer đó. Các partition do consumer member khác quản lý vẫn có thể tiếp tục được xử lý.

Không có một thứ tự tổng thể giữa các partition. Retry giữ cơ chế ordering trong partition theo cách xử lý của container, nhưng side effect bên ngoài vẫn có thể lặp hoặc hoàn tất sai thứ tự nếu listener tự đẩy công việc sang thread khác.

## 8. Retry đồng bộ ảnh hưởng tới poll loop và max.poll.interval.ms

Consumer cần tiếp tục gọi poll trong giới hạn max.poll.interval.ms. Với retry đồng bộ, thời gian xử lý record và các khoảng backoff cộng lại có thể làm consumer chậm gọi poll tiếp theo.

Ví dụ:

- Xử lý lần đầu mất 2 giây.
- Retry 1 chờ 5 giây và xử lý 2 giây.
- Retry 2 chờ 10 giây và xử lý 2 giây.

Tổng thời gian có thể vượt 20 giây, chưa tính thời gian commit và xử lý khác. Nếu khoảng thời gian giữa các lần poll vượt max.poll.interval.ms, consumer có thể rời group và kích hoạt rebalance.

Với backoff dài, Spring Kafka cung cấp ContainerPausingBackOffHandler ở các phiên bản hỗ trợ. Cơ chế này pause container trong thời gian chờ và tiếp tục poll để duy trì membership của consumer group. Thời gian pause thực tế phụ thuộc poll timeout nên có thể không chính xác tuyệt đối tới từng mili giây.

Các lựa chọn khi backoff dài:

- Dùng ContainerPausingBackOffHandler nếu phù hợp với phiên bản Spring Kafka.
- Điều chỉnh max.poll.interval.ms dựa trên thời gian xử lý đo được.
- Giảm số lần retry hoặc tổng thời gian retry.
- Chuyển sang non-blocking retry topic nếu không cần giữ partition chờ record lỗi.
- Cải thiện dependency hoặc tách công việc dài khỏi listener.

Không tăng max.poll.interval.ms vô hạn để che giấu listener xử lý chậm. Hãy đo thời gian xử lý p95/p99 và xác định thời gian chờ lớn nhất có thể xảy ra.

## 9. Retry đồng bộ và thứ tự xử lý

Retry đồng bộ thường phù hợp khi cần giữ thứ tự của các record trong một partition. Nếu record ở offset 20 thất bại, record offset 21 cùng partition thường phải chờ record lỗi được xử lý hoặc recover trước khi luồng tiếp tục.

Điều này quan trọng với các sự kiện như:

- OrderCreated trước OrderPaid.
- AccountOpened trước AccountDebited.
- InventoryReserved trước InventoryReleased.

Nếu bỏ qua record lỗi rồi tiếp tục ngay, nghiệp vụ phía sau có thể chạy trên trạng thái chưa đúng. Ngược lại, nếu retry record lỗi quá lâu, partition sẽ bị chặn và lag tích tụ.

Cần chọn chính sách theo hợp đồng nghiệp vụ:

- Nếu thứ tự là bắt buộc, retry có giới hạn rồi recovery có kiểm soát.
- Nếu record lỗi có thể được cô lập, DLT và quy trình replay có thể giúp partition tiếp tục.
- Nếu các record độc lập, có thể cân nhắc concurrency theo partition hoặc non-blocking retry topic.
- Nếu cần xử lý song song trong một partition, phải tự thiết kế sequence/ordering và offset management cẩn thận; không giả định retry mặc định vẫn bảo toàn thứ tự hoàn tất side effect.

## 10. DeadLetterPublishingRecoverer sau khi hết retry

Sau khi hết số lần retry, DefaultErrorHandler gọi recoverer để xử lý record. DeadLetterPublishingRecoverer là lựa chọn phổ biến để publish record lỗi sang DLT.

Ví dụ destination resolver gửi record vào topic nguồn cộng hậu tố .DLT và giữ nguyên partition number:

~~~java
@Bean
DeadLetterPublishingRecoverer recoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
            )
    );
}
~~~

Nếu resolver giữ partition number, topic DLT cần có đủ partition tương ứng. Có thể chọn một partition DLT tập trung hoặc quy tắc phân phối khác, nhưng cần đánh giá throughput và khả năng truy vết.

DLT nên giữ metadata nguồn như topic, partition, offset và thông tin exception. Hãy cấu hình serializer phù hợp với cả record đã deserialize và raw bytes nếu có lỗi deserialize.

Recovery thành công cho phép container tiếp tục theo chính sách commit của error handler. Nếu publish DLT thất bại, không nên giả định record đã được xử lý xong; cần cấu hình và kiểm thử hành vi khi recoverer ném exception.

## 11. Idempotency vì record có thể được giao lại

Retry và redelivery tạo ra khả năng một record được listener xử lý nhiều lần. Ngay cả khi listener đã cập nhật database thành công, consumer có thể dừng trước khi offset được commit. Khi group đọc lại từ offset cũ, cùng record sẽ tới listener lần nữa.

Ví dụ xử lý trừ tiền:

~~~java
public void handle(PaymentRequested event) {
    paymentRepository.debit(
            event.accountId(),
            event.amount()
    );
}
~~~

Nếu listener chạy lại cùng event, tài khoản có thể bị trừ tiền hai lần.

Có thể dùng eventId làm idempotency key:

~~~java
@Transactional
public void handle(PaymentRequested event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    accountRepository.debit(
            event.accountId(),
            event.amount()
    );

    processedEventRepository.save(
            new ProcessedEvent(event.eventId())
    );
}
~~~

Trong triển khai thực tế, kiểm tra và ghi nhận eventId phải được bảo vệ bằng unique constraint hoặc transaction phù hợp để hai lần xử lý đồng thời không cùng vượt qua bước kiểm tra.

Idempotency cần áp dụng cho cả lần xử lý đầu, retry trong cùng process và redelivery sau restart/rebalance. Retry không biến consumer thành exactly-once.

## 12. Batch listener và retry record lỗi

Với record listener, error handler nhận biết record cụ thể đã thất bại. Với batch listener, phương thức nhận nhiều record trong một lần gọi; khi một record lỗi, ứng dụng cần cho error handler biết record hoặc index nào thất bại.

Spring Kafka hỗ trợ BatchListenerFailedException để chỉ ra record lỗi trong batch:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-batch"
)
public void consume(List<ConsumerRecord<String, OrderCreatedEvent>> records) {
    for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
        try {
            orderService.handle(record.value());
        } catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Failed to process order event",
                    record
            );
        }
    }
}
~~~

Khi error handler biết vị trí record lỗi, nó có thể xử lý phần trước và retry/recover phần lỗi cùng phần còn lại theo semantics của batch listener.

Nếu batch listener ném exception chung mà không xác định record lỗi, error handler có thể phải xử lý lại toàn batch. Những record đã tạo side effect trước lỗi có thể được xử lý lại, do đó idempotency vẫn cần thiết.

Hành vi partial batch và offset phụ thuộc AckMode, phiên bản Spring Kafka và cấu hình error handler. Hãy kiểm thử bằng batch nhiều partition và một record lỗi ở giữa.

## 13. Phân biệt blocking retry với non-blocking retry topic

Spring Kafka hỗ trợ nhiều chiến lược retry. Blocking retry giữ record trong luồng consumer hiện tại và thử lại trước khi partition tiếp tục. Non-blocking retry thường dùng retry topic để chuyển record sang một topic chờ rồi consumer tiếp tục xử lý record khác.

| Tiêu chí | Blocking retry | Non-blocking retry |
|---|---|---|
| Cơ chế | Error handler chờ và redeliver record | Publish record sang retry topic với thời điểm xử lý sau |
| Partition nguồn | Có thể bị chặn ở record lỗi | Có thể tiếp tục sau khi record được chuyển đi thành công |
| Thứ tự | Dễ giữ thứ tự trong partition hơn | Có thể thay đổi thứ tự hoàn tất giữa các record |
| Backoff dài | Có thể giữ consumer bận hoặc pause container | Phù hợp hơn với thời gian chờ dài |
| Vận hành | Ít topic phụ hơn | Cần quản lý retry topic, consumer và DLT |
| Use case | Lỗi tạm thời, thời gian phục hồi ngắn, ordering quan trọng | Retry lâu, không muốn giữ partition chờ, chấp nhận thay đổi ordering |

Non-blocking retry trong Spring Kafka thường được cấu hình bằng @RetryableTopic hoặc RetryTopicConfiguration. Đây là cơ chế khác với DefaultErrorHandler blocking retry. Không nên cấu hình cả hai một cách chồng chéo mà chưa xác định rõ chiến lược.

Nếu ordering của aggregate là bắt buộc, hãy đánh giá cẩn thận việc đưa record sang retry topic vì record mới hơn trong topic chính có thể được xử lý trước record đang chờ retry.

## 14. Retry khi listener dùng transaction

Khi listener container được cấu hình Kafka transaction, lỗi listener có thể khiến transaction bị rollback. Trong mô hình transactional, Spring Kafka thường dùng DefaultAfterRollbackProcessor để xử lý record sau rollback, thay vì áp dụng máy móc DefaultErrorHandler như luồng non-transactional.

Sau rollback, record có thể được redeliver theo chính sách của processor; sau số lần thử nhất định có thể recover hoặc publish DLT. Khi dùng transaction, cần hiểu ranh giới giữa transaction output record và offset input.

Không trộn ví dụ DefaultErrorHandler non-transactional với transactional listener mà không kiểm tra semantics của phiên bản Spring Kafka. Hãy cấu hình DefaultAfterRollbackProcessor và transaction manager tương ứng, rồi kiểm thử rollback, retry, recovery và commit offset.

## 15. Những lỗi thường gặp khi cấu hình retry

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Retry mọi exception | Lỗi dữ liệu cố định bị thử đi thử lại | Phân loại retryable/non-retryable. |
| Backoff quá dài | Consumer trễ poll, lag tăng, có thể rebalance | Tính tổng thời gian retry và cân nhắc pause handler. |
| Retry vô hạn | Partition có thể không tiến triển | Đặt giới hạn và recovery. |
| Không có DLT hoặc recoverer | Record hết retry không có quy trình xử lý tiếp | Xác định hành động recovery rõ ràng. |
| DLT publish lỗi nhưng vẫn coi là thành công | Có thể mất record lỗi khỏi luồng chính | Kiểm tra hành vi recoverer failure. |
| Listener tạo side effect không idempotent | Retry/redelivery gây tác động trùng | Dùng eventId và transaction/unique constraint. |
| Dùng blocking retry cho backoff nhiều giờ | Giữ partition và consumer chờ quá lâu | Cân nhắc retry topic. |
| Không kiểm tra batch semantics | Toàn batch có thể bị xử lý lại | Dùng BatchListenerFailedException và test partial failure. |
| Dùng DefaultErrorHandler như transactional rollback processor | Sai cơ chế phục hồi transaction | Dùng DefaultAfterRollbackProcessor cho luồng transactional phù hợp. |

## 16. Kiểm thử retry đồng bộ

Kiểm thử cần chứng minh listener được gọi đúng số lần, backoff có giới hạn và record được recover sau khi hết retry.

Các kịch bản:

| Kiểm thử | Điều cần xác minh |
|---|---|
| Success ngay lần đầu | Listener chỉ xử lý một lần, offset tiến lên. |
| Lỗi một lần rồi thành công | Listener được redeliver và hoàn tất. |
| Lỗi đến hết retry | Recoverer được gọi sau đúng số lần thử. |
| Non-retryable exception | Không áp dụng các lần retry thông thường. |
| Retryable exception | Backoff và retry đúng cấu hình. |
| DLT success | Record tới đúng topic/partition DLT. |
| DLT publish failure | Record không bị đánh dấu recovery thành công sai. |
| Poll interval | Backoff dài không làm consumer rời group ngoài dự kiến. |
| Rebalance | Record chưa commit có thể được giao lại và xử lý idempotent. |
| Batch failure | Error handler xác định được record lỗi và partial batch semantics. |

Ví dụ dùng bộ đếm trong integration test:

~~~java
AtomicInteger attempts = new AtomicInteger();

doAnswer(invocation -> {
    if (attempts.incrementAndGet() < 3) {
        throw new TransientDataAccessException("Temporary database issue") {};
    }
    return null;
}).when(orderService).handle(any(OrderCreatedEvent.class));
~~~

Với FixedBackOff có hai retry sau lần giao đầu, test có thể xác minh service được gọi tối đa ba lần và sau đó hoàn tất. Nếu service tiếp tục lỗi, test cần xác minh recoverer/DLT nhận record.

Nên dùng EmbeddedKafka hoặc Testcontainers để kiểm tra container và offset thật. Dùng Awaitility hoặc latch có timeout để đợi kết quả; không dùng Thread.sleep cố định. Backoff trong test có thể giảm xuống vài mili giây để suite chạy nhanh, nhưng vẫn cần giữ semantics số lần retry.

## 17. Quan sát và vận hành retry

Retry có thể che giấu sự cố dependency nếu chỉ nhìn số record thành công cuối cùng. Cần theo dõi riêng hoạt động retry và recovery.

Các metric nên có:

- Số lần listener thất bại theo exception class.
- Số lần retry và số record hết retry.
- Backoff thực tế và thời gian một record nằm trong retry.
- Số record publish vào DLT.
- Số lần DLT publish thất bại.
- Consumer lag theo partition.
- Processing latency p95/p99.
- Số lần rebalance và lý do.
- Tỷ lệ thành công sau retry.

Log nên có topic, partition, offset, key hoặc eventId, attempt count và exception gốc. Không log toàn bộ payload nhạy cảm.

Đặt cảnh báo khi retry rate tăng đột biến, DLT backlog tăng, consumer lag tăng liên tục hoặc một partition bị giữ ở cùng offset quá lâu. DLT cần owner và runbook để điều tra, sửa nguyên nhân và replay có kiểm soát.

## 18. Bài tập tổng hợp: retry lỗi database trong OrderCreatedListener

Hãy xây dựng listener xử lý OrderCreatedEvent. Dịch vụ database đôi khi timeout nhưng có thể phục hồi sau một khoảng ngắn.

Yêu cầu:

1. Tạo DefaultErrorHandler cho listener container.
2. Cấu hình FixedBackOff với khoảng chờ một giây và hai retry.
3. Cấu hình TransientDataAccessException là retryable.
4. Cấu hình IllegalArgumentException là non-retryable.
5. Tạo DeadLetterPublishingRecoverer để gửi record hết retry sang orders.created.DLT.
6. Gửi một record mà lần đầu và lần hai thất bại, lần ba thành công.
7. Gửi một record luôn thất bại và xác minh DLT nhận đúng record.
8. Gửi một record có dữ liệu sai và xác minh không retry theo classifier.
9. Đo thời gian xử lý và consumer lag khi backoff tăng.
10. Thử backoff dài và quan sát max.poll.interval.ms/rebalance.
11. Thêm eventId idempotency để xử lý redelivery an toàn.
12. Viết integration test cho retry count, DLT, offset và side effect.
13. Viết runbook cho trường hợp dependency lỗi kéo dài.
14. Đề xuất khi nào chuyển từ blocking retry sang retry topic.

Bài tập hoàn thành khi bạn chứng minh được số lần thử, khoảng chờ, exception classification, recovery sau khi hết retry và khả năng xử lý lặp an toàn.

## 19. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Error flow | Listener exception và CommonErrorHandler | Mô tả được luồng lỗi từ listener tới error handler. |
| 2. Blocking retry | DefaultErrorHandler | Giải thích được redelivery trong consumer thread. |
| 3. BackOff | FixedBackOff và exponential backoff | Tính được số lần thử và tổng thời gian retry. |
| 4. Classification | Retryable và non-retryable exceptions | Chọn đúng lỗi cần retry. |
| 5. Recovery | Recoverer và DLT | Xử lý được record sau khi hết retry. |
| 6. Poll loop | max.poll.interval.ms và pause handler | Đánh giá được rủi ro khi backoff dài. |
| 7. Ordering | Seek, redelivery và partition | Giải thích được vì sao record lỗi có thể chặn record sau. |
| 8. Reliability | Idempotency và transaction | Không tạo side effect trùng khi redelivery. |
| 9. Strategy | Blocking và non-blocking retry | Chọn đúng cơ chế theo ordering và thời gian chờ. |
| 10. Testing | EmbeddedKafka/Testcontainers | Xác minh retry count, recovery và offset. |

Bài học hoàn thành khi bạn có thể cấu hình DefaultErrorHandler với số lần retry và backoff rõ ràng, phân loại exception theo khả năng phục hồi, đưa record hết retry vào quy trình recovery và giải thích tác động tới partition ordering, poll loop cùng offset.

Retry đồng bộ đơn giản và hữu ích cho lỗi tạm thời có thời gian phục hồi ngắn. Vì retry giữ consumer xử lý record lỗi, hãy đặt giới hạn, đo tổng thời gian chờ, giữ listener idempotent và có DLT/runbook cho record không thể xử lý.
