# seekAfterError=false

Trong Spring Kafka, `DefaultErrorHandler` thường xử lý lỗi bằng cách đưa vị trí đọc của consumer quay lại record thất bại để record đó và các record chưa xử lý được đọc lại trong lần poll sau. Cách này dùng Kafka consumer seek để thay đổi vị trí đọc của partition.

Từ Spring Kafka 2.9, có thể cấu hình `seekAfterError=false` để container giữ các record chưa xử lý trong bộ nhớ và gửi lại chúng cho listener sau khi error handler hoàn tất. Thay vì seek partition để Kafka fetch lại các record đó, container tạm pause consumer, thực hiện một lần poll để duy trì membership/heartbeat của consumer group, rồi resubmit các record đã giữ.

Tùy chọn này thay đổi **cách container đưa record chưa xử lý trở lại listener**. Nó không thay thế retry policy, exception classification, recoverer, acknowledgment mode hoặc quy tắc commit offset. Những phần đó vẫn cần được thiết kế riêng.

## 1. Cách xử lý mặc định: seek sau lỗi

Giả sử một lần poll lấy được bốn record từ partition `orders-0`:

| Offset | Kết quả |
|---:|---|
| 100 | Listener xử lý thành công |
| 101 | Listener ném exception |
| 102 | Chưa được xử lý |
| 103 | Chưa được xử lý |

Với cơ chế seek mặc định, error handler xử lý record lỗi theo retry/backoff. Các partition liên quan được seek về vị trí cần đọc lại để consumer có thể fetch lại record thất bại hoặc các record còn lại chưa xử lý trong lần poll tiếp theo.

```text
Poll: 100, 101, 102, 103
       |
       +--> 100 xử lý thành công
       |
       +--> 101 lỗi
                |
                v
          DefaultErrorHandler
                |
                v
          retry / recover
                |
                v
          seek partition về offset cần đọc lại
                |
                v
          poll tiếp theo fetch record chưa xử lý
```

Seek thay đổi vị trí đọc của Kafka consumer. Các record cần xử lý lại được fetch từ broker trong poll tiếp theo. Đây là cơ chế truyền thống của `DefaultErrorHandler` và thường phù hợp với luồng xử lý record thông thường.

## 2. Cách xử lý khi `seekAfterError=false`

Khi đặt `seekAfterError=false`, container không dùng seek để đưa phần record chưa xử lý trở lại. Container giữ các record đó trong bộ nhớ và resubmit cho listener sau khi error handler kết thúc.

```text
Poll: 100, 101, 102, 103
       |
       +--> 100 xử lý thành công
       |
       +--> 101 lỗi
                |
                v
          DefaultErrorHandler
                |
                v
          retry / recover
                |
                v
          container giữ record chưa xử lý
                |
                v
          pause consumer
                |
                v
          poll một lần để giữ group membership
                |
                v
          resubmit record được giữ cho listener
```

Lần poll trong khi consumer bị pause là một phần quan trọng của cơ chế. Nó giúp consumer tiếp tục tham gia group và gửi heartbeat trong thời gian container đang giữ record để xử lý lại. Sau đó, container chuyển các record đã giữ trở lại listener mà không cần broker gửi lại toàn bộ các record đó qua một lần fetch mới.

Với ví dụ trên, record 100 đã xử lý xong không cần được xử lý lại. Record 101 được retry hoặc recover theo quyết định của error handler; record 102 và 103 chưa xử lý được giữ lại để tiếp tục sau khi handler hoàn tất. Chi tiết record nào được giữ lại phụ thuộc kiểu listener, vị trí lỗi và kết quả recovery.

## 3. Cấu hình trong DefaultErrorHandler

`seekAfterError` là thuộc tính của `DefaultErrorHandler`. Giá trị mặc định là `true`, vì vậy ứng dụng chỉ cần đặt `false` khi muốn dùng chế độ giữ và resubmit record.

Ví dụ cấu hình:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);
    recoverer.setFailIfSendResultIsError(true);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    handler.setSeekAfterError(false);
    return handler;
}
```

Trong ví dụ, listener có lần delivery ban đầu và tối đa hai lần retry, mỗi lần cách nhau một giây. Khi retry hết, recoverer gửi record sang DLT. `setFailIfSendResultIsError(true)` giúp phản ánh lỗi gửi DLT trong các phiên bản Spring Kafka hỗ trợ API này. Cần bảo đảm DLT tồn tại, có đủ partition, serializer tương thích và producer có quyền ghi.

Gắn handler vào listener container factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}
```

Listener sử dụng factory này:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "orderKafkaListenerContainerFactory")
public void consume(OrderCreated event) {
    orderService.processIdempotently(event);
}
```

Đây là cấu hình minh họa cho record listener. Tên bean, generic type, serializer và error handler cần phù hợp với cấu trúc ứng dụng. Nếu ứng dụng có nhiều listener container factory, chỉ những listener dùng factory được gắn handler này mới chịu ảnh hưởng của cấu hình `seekAfterError=false`.

## 4. `seekAfterError=false` không thay đổi retry policy

Hai quyết định cần được tách biệt:

- **Retry policy:** exception nào được retry, retry bao nhiêu lần và chờ bao lâu.
- **Redelivery mechanism:** sau khi error handler xử lý lỗi, container dùng seek/refetch hay giữ/resubmit các record chưa xử lý.

`seekAfterError=false` chỉ thay đổi quyết định thứ hai. Ví dụ:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(2_000L, 3L));

handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class);

handler.setSeekAfterError(false);
```

Trong cấu hình này:

- `InvalidOrderException` và `UnsupportedEventVersionException` được phân loại không retry, nên đi tới recoverer ngay.
- Exception retryable dùng `FixedBackOff` với tối đa ba lần retry sau lần delivery đầu tiên.
- Sau khi error handler hoàn tất, container giữ/resubmit record chưa xử lý thay vì seek partition để fetch lại.

Không nên tăng số lần retry chỉ vì chuyển sang `seekAfterError=false`. Nếu lỗi dữ liệu không thể khắc phục bằng retry, hãy phân loại not-retryable. Nếu lỗi dependency có thể phục hồi, hãy dùng backoff hữu hạn và giới hạn tổng thời gian.

## 5. Quan hệ với committed offset và acknowledgment mode

`seekAfterError=false` không tự commit offset. Container vẫn commit theo acknowledgment mode, trạng thái xử lý của listener và cấu hình error handler.

Với `AckMode.RECORD`, container commit sau khi từng record được xử lý thành công theo quy tắc của listener container. Với `AckMode.BATCH`, container commit theo batch sau khi các record trong batch được xử lý thành công. Với manual acknowledgment, listener phải gọi `acknowledge()` tại thời điểm công việc cần thiết đã hoàn tất.

Nếu recoverer xử lý record lỗi thành công, việc commit record recovered là một quyết định riêng. Ví dụ, `DefaultErrorHandler.setCommitRecovered(true)` yêu cầu container commit offset của record đã recover và cần `AckMode.MANUAL_IMMEDIATE`. Chỉ đặt `seekAfterError=false` không thay thế cấu hình này.

Ví dụ manual acknowledgment:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "manualOrderKafkaListenerContainerFactory")
public void consume(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(event);
    acknowledgment.acknowledge();
}
```

Listener chỉ acknowledge sau khi side effect nghiệp vụ hoàn tất. Nếu process dừng sau khi side effect thành công nhưng trước khi commit offset, record có thể được giao lại sau restart. Vì vậy, `processIdempotently()` cần thực hiện deduplication hoặc bảo đảm cùng một event không tạo side effect trùng.

Không dùng `seekAfterError=false` như một cơ chế exactly-once. Nó không làm cho commit offset và database transaction trở thành một giao dịch nguyên tử. Với side effect ngoài Kafka, vẫn cần inbox/outbox hoặc idempotency.

## 6. Hành vi khi recoverer thành công hoặc thất bại

Khi retry hết, recoverer có thể thực hiện một hành động thay thế như gửi record sang DLT. Kết quả recovery ảnh hưởng đến việc container tiếp tục với các record đang giữ.

### 6.1. Recovery thành công

Khi recoverer hoàn tất thành công, error handler có thể coi record lỗi đã được xử lý theo chính sách recovery. Container tiếp tục với các record còn lại chưa xử lý. Nếu cần commit offset recovered, cấu hình `commitRecovered` và acknowledgment mode phù hợp.

```text
Record lỗi
   |
   v
Retry hết
   |
   v
Publish DLT thành công
   |
   v
Recovery hoàn tất
   |
   v
Container tiếp tục các record chưa xử lý
```

### 6.2. Recovery thất bại

Nếu DLT publish thất bại, recoverer cần báo lỗi thay vì để handler coi record là đã recover. Khi đó, offset không được commit như thể record đã được xử lý xong; cần kiểm tra retry state, backoff và hành vi xử lý lỗi của phiên bản Spring Kafka đang dùng.

Với `DeadLetterPublishingRecoverer`, có thể dùng `setFailIfSendResultIsError(true)` ở các phiên bản hỗ trợ để lỗi send result được chuyển thành lỗi recovery. Đồng thời phải quan sát timeout, ACL, topic, partition và serializer của DLT.

Không để DLT outage tạo ra vòng retry vô hạn không kiểm soát. Hãy giới hạn backoff, cảnh báo recovery failure và có phương án giảm tốc hoặc pause consumer khi hệ thống nhận DLT không sẵn sàng.

## 7. Record listener và batch listener

### 7.1. Record listener

Với record listener, mỗi lần gọi listener xử lý một record. Khi một record lỗi, `DefaultErrorHandler` có thể retry record đó hoặc gọi recoverer. Các record chưa xử lý trong lần poll được container giữ lại khi `seekAfterError=false` và được resubmit sau khi error handler hoàn tất.

Record listener phù hợp khi từng event có ranh giới xử lý độc lập, exception có thể phân loại theo record và commit offset cần theo sát tiến độ từng event.

### 7.2. Batch listener

Batch listener nhận nhiều record trong một lần gọi. Nếu một record trong batch gây lỗi, error handler cần xác định vị trí lỗi để biết phần nào đã xử lý và phần nào cần retry/recover. Spring Kafka hỗ trợ `BatchListenerFailedException` để listener chỉ rõ index hoặc record gây lỗi.

```java
@KafkaListener(topics = "orders", groupId = "batch-order-service")
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int i = 0; i < records.size(); i++) {
        try {
            orderService.processIdempotently(records.get(i).value());
        }
        catch (InvalidOrderException ex) {
            throw new BatchListenerFailedException(
                    "Invalid order at batch index " + i, ex, i);
        }
    }
}
```

Khi exception xác định được record lỗi, error handler có thể xử lý phần trước lỗi, retry hoặc recover record lỗi và tiếp tục phần còn lại theo batch semantics. Nếu listener ném exception chung mà không chỉ rõ vị trí lỗi, handler có thể phải retry cả batch. Khi đó, các record đã tạo side effect trước khi lỗi xảy ra có thể được xử lý lại; cần idempotency.

`seekAfterError=false` thay đổi cơ chế container giữ/resubmit record chưa xử lý, nhưng không loại bỏ yêu cầu xác định record lỗi trong batch. Cần kiểm thử riêng batch listener với số record thực tế, batch index, commit mode và error handler.

## 8. Lợi ích và chi phí của chế độ không seek

| Khía cạnh | `seekAfterError=true` | `seekAfterError=false` |
|---|---|---|
| Cách đưa record chưa xử lý trở lại | Seek partition và fetch lại trong poll sau | Container giữ record và resubmit |
| Dữ liệu được dùng lại | Broker gửi lại qua fetch | Record đã poll được giữ trong bộ nhớ |
| Consumer trong thời gian chờ | Theo hành vi pause/backoff của error handler và container | Container pause và poll một lần để giữ group membership trước khi resubmit |
| Tác động bộ nhớ | Không cần giữ toàn bộ phần record để resubmit theo cơ chế này | Cần giữ các record chưa xử lý trong bộ nhớ |
| Retry/backoff | Do error handler quyết định | Vẫn do error handler quyết định |
| Commit offset | Theo ack mode và cấu hình recovery | Không thay đổi nguyên tắc commit |

Chế độ không seek có thể tránh việc fetch lại các record đã có trong bộ nhớ và giúp container quản lý luồng xử lý tiếp theo mà không thay đổi vị trí đọc partition. Đổi lại, container cần giữ các record chưa xử lý cho tới khi resubmit hoàn tất.

Với payload lớn, batch lớn hoặc nhiều partition, lượng dữ liệu giữ lại có thể đáng kể. Cần cân nhắc `max.poll.records`, kích thước record, fetch limits, concurrency và heap của ứng dụng. Không nên tăng `max.poll.records` chỉ để tăng throughput nếu listener có thể giữ nhiều record trong bộ nhớ trong thời gian retry dài.

## 9. Poll, pause và group membership

Khi container giữ record để resubmit, consumer cần tiếp tục duy trì membership trong group. Nếu consumer không poll đủ lâu, coordinator có thể xem consumer đã rời group và kích hoạt rebalance. Vì vậy, container pause consumer và thực hiện một poll để giữ heartbeat/group membership trước khi resubmit record.

Pause ở đây không đồng nghĩa consumer bị đóng hoặc rời group. Container vẫn quản lý consumer và thực hiện poll theo cơ chế nội bộ cần thiết. Điều này đặc biệt quan trọng khi backoff kéo dài hoặc record được giữ trong khi handler xử lý.

Tuy nhiên, ứng dụng vẫn phải cấu hình thời gian xử lý và backoff hợp lý. `max.poll.interval.ms`, `session.timeout.ms`, heartbeat và thời gian xử lý batch vẫn ảnh hưởng đến ổn định group. Cần kiểm tra behavior của phiên bản Kafka client và Spring Kafka đang dùng, đặc biệt khi tùy chỉnh poll, pause/resume hoặc dùng listener bất đồng bộ.

## 10. Khi nào nên dùng `seekAfterError=false`?

Chế độ này đáng cân nhắc khi:

- Muốn container giữ các record đã poll để gửi lại mà không seek partition.
- Muốn tránh fetch lại các record chưa xử lý trong một số luồng có batch hoặc payload cần được giữ nguyên trong bộ nhớ.
- Đã hiểu rõ tác động của việc giữ record trong heap và có giới hạn poll phù hợp.
- Dùng `DefaultErrorHandler` và muốn cấu hình rõ cơ chế resubmit trong container.
- Có kiểm thử chứng minh retry, recovery, commit và rebalance vẫn đúng với listener thực tế.

Giữ mặc định seek thường đơn giản hơn nếu ứng dụng không có nhu cầu cụ thể. Không nên bật chế độ này chỉ vì tên cấu hình có vẻ tối ưu hơn; lợi ích thực tế phụ thuộc kích thước batch, payload, thời gian backoff và tải consumer.

## 11. Các lỗi vận hành thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Record chưa xử lý không quay lại listener | Handler/recoverer đã coi record là recovered hoặc container factory không dùng handler mong muốn | Kiểm tra exception classification, recoverer và tên factory trên listener |
| Record được xử lý lặp | Side effect hoàn tất nhưng offset chưa commit; record được resubmit hoặc replay sau restart | Làm handler idempotent và kiểm tra acknowledgment/commit mode |
| Consumer lag tăng khi retry dài | Backoff dài, throughput xử lý thấp hoặc downstream tiếp tục lỗi | Giới hạn retry, điều chỉnh backoff và theo dõi tuổi record cũ nhất |
| Heap tăng trong thời gian lỗi | Container giữ nhiều record chưa xử lý; poll batch/payload lớn | Giảm `max.poll.records`, giới hạn payload/batch và kiểm tra heap/GC |
| Group rebalance trong khi xử lý lỗi | Consumer không poll kịp, processing/backoff vượt giới hạn hoặc mạng/heartbeat có vấn đề | Kiểm tra `max.poll.interval.ms`, session timeout và poll behavior |
| DLT publish lỗi nhưng luồng vẫn tiến | Recoverer không phản ánh send failure | Bật kiểm tra send result, theo dõi publish error và xác minh offset |
| Batch bị xử lý lại nhiều lần | Listener không chỉ rõ record lỗi hoặc side effect trước lỗi không idempotent | Dùng `BatchListenerFailedException` đúng index và thiết kế batch recovery |
| Thay đổi cấu hình không có tác dụng | Listener đang dùng container factory khác | Kiểm tra `containerFactory` trên `@KafkaListener` và bean thực tế |

Khi điều tra, luôn xác nhận đúng cluster, topic, partition, group ID và listener container. Kiểm tra log error handler cùng committed offset, lag, rebalance và trạng thái DLT. Không reset offset thủ công để che giấu lỗi resubmit hoặc recovery; reset lùi có thể tạo duplicate, reset tiến có thể bỏ qua dữ liệu.

## 12. Kiểm thử `seekAfterError=false`

Một kiểm thử tích hợp nên xác nhận cách container xử lý record trước, tại và sau vị trí lỗi. Có thể dùng Kafka test broker hoặc môi trường Kafka kiểm thử.

Kịch bản đề xuất:

1. Tạo topic có ít nhất một partition và consumer group mới.
2. Gửi các record có ID và offset có thể nhận diện.
3. Cấu hình listener thất bại có kiểm soát tại một record cụ thể, ví dụ record thứ hai.
4. Bật `DefaultErrorHandler.setSeekAfterError(false)` với backoff ngắn để kiểm thử.
5. Xác nhận số lần listener được gọi theo retry policy.
6. Xác nhận record lỗi được recover hoặc tiếp tục retry đúng classification.
7. Xác nhận các record chưa xử lý được resubmit và không bị bỏ sót.
8. Xác nhận committed offset chỉ tiến theo quy tắc acknowledgment/recovery đã cấu hình.
9. Mô phỏng DLT publish failure và xác nhận record không bị coi là recovered thành công.
10. Dừng/restart consumer giữa quá trình xử lý để xác nhận record chưa commit được giao lại theo offset bền vững.

Để phân biệt seek và resubmit, có thể quan sát log consumer/handler, số lần fetch nếu metric hỗ trợ và thứ tự record listener nhận. Không dựa duy nhất vào tổng số lần listener được gọi vì retry, redelivery và restart đều có thể làm tăng con số này.

## 13. Nguyên tắc triển khai production

Trước khi bật `seekAfterError=false`, cần xác nhận:

1. Phiên bản Spring Kafka hỗ trợ chế độ này; tính năng có từ Spring Kafka 2.9.
2. Listener thực tế sử dụng `DefaultErrorHandler` đã cấu hình `setSeekAfterError(false)`.
3. Retry/backoff và exception classification phù hợp với từng loại lỗi.
4. Recoverer lưu record bền vững; DLT publish failure được phản ánh thành lỗi recovery.
5. Ack mode và commit recovered được cấu hình độc lập, không nhầm với cơ chế resubmit.
6. Batch listener xác định đúng record lỗi và có side effect idempotent.
7. `max.poll.records`, kích thước payload, concurrency và heap đủ để giữ record trong thời gian xử lý lỗi.
8. `max.poll.interval.ms`, session timeout và heartbeat phù hợp với thời gian xử lý/backoff.
9. Dashboard có consumer lag, retry rate, DLT rate, rebalance, processing latency và heap/GC.
10. Kiểm thử recovery thành công, recovery thất bại, restart, rebalance và batch listener trước khi rollout.

`seekAfterError=false` cho phép Spring Kafka giữ các record chưa xử lý và resubmit chúng sau khi error handler hoàn tất. Cơ chế này giúp thay đổi cách redelivery diễn ra trong container, trong khi retry policy và commit offset vẫn giữ trách nhiệm riêng. Khi chọn chế độ này, cần quản lý bộ nhớ, poll interval, group membership và idempotency để bảo đảm luồng consumer tiếp tục an toàn khi có lỗi.
