# Listener bị gọi lặp lại

Trong Spring Kafka, một listener có thể được gọi nhiều lần cho cùng một record khi lần xử lý trước thất bại hoặc consumer chưa commit offset. Đây thường là hệ quả của cơ chế at-least-once: Kafka ưu tiên giao lại record để tránh mất dữ liệu, nên ứng dụng phải chịu được việc xử lý trùng.

Khi thấy log cùng một event xuất hiện nhiều lần, cần xác định đó là retry có chủ đích, redelivery sau restart/rebalance, hay hai producer đã gửi hai record giống nhau. Ba trường hợp này có nguyên nhân và cách xử lý khác nhau. Không nên chỉ tăng timeout hoặc tăng concurrency trước khi xác định record nào đang được giao lại và offset nào đã commit.

## 1. Phân biệt retry, redelivery và duplicate event

| Hiện tượng | Ý nghĩa | Dấu hiệu thường gặp |
|---|---|---|
| Blocking retry | Error handler áp dụng backoff và yêu cầu container giao lại record trên luồng consumer | Cùng topic-partition-offset xuất hiện nhiều lần trong thời gian ngắn |
| Non-blocking retry | Record lỗi được publish sang retry topic rồi được listener xử lý lại | Cùng event ID xuất hiện trên topic retry với offset mới |
| Redelivery | Kafka giao lại record vì offset chưa được commit hoặc ownership thay đổi | Cùng topic-partition-offset xuất hiện sau restart/rebalance |
| Duplicate publish | Producer gửi cùng một sự kiện nghiệp vụ thành nhiều Kafka record | Event ID giống nhau nhưng topic/partition/offset khác nhau |
| Duplicate side effect | Một record được xử lý lại và tạo tác động nghiệp vụ lặp | Hai lần trừ tiền, tạo đơn hoặc gửi thông báo cho cùng event |

Record Kafka được nhận diện ở mức transport bằng bộ ba topic, partition và offset. Khi record được publish lại, nó có offset mới; vì vậy cần một event ID ổn định ở cấp nghiệp vụ để nhận diện cùng một sự kiện qua retry topic hoặc lần publish khác.

## 2. Luồng xử lý record và thời điểm commit

Với record listener, container poll record từ Kafka, gọi listener, sau đó commit offset theo acknowledgement mode và cấu hình container. Nếu listener ném exception, error handler quyết định retry, recover hoặc chuyển record sang DLT.

```text
Kafka partition
    |
    v
Consumer poll
    |
    v
Spring Kafka listener
    |
    +---- xử lý thành công ----> commit offset
    |
    +---- ném exception
              |
              v
        Error handler
              |
        backoff / retry
              |
        +-----+----------------+
        |                      |
     retry lại              recover
        |                      |
        v                      v
    listener lần nữa       DLT / skip
```

Với cấu hình Spring Kafka thông dụng, auto commit của Kafka consumer được tắt để listener container quản lý commit. Cách commit cụ thể phụ thuộc AckMode, transaction và loại listener. Hãy kiểm tra cấu hình thực tế thay vì giả định rằng listener trả về là offset luôn được commit ngay lập tức.

Một nguyên tắc quan trọng: listener hoàn tất side effect nhưng process chết trước khi offset được commit thì record có thể được giao lại. Đây là lý do xử lý idempotent là bắt buộc với các nghiệp vụ không được phép lặp.

## 3. Những nguyên nhân phổ biến khiến listener chạy nhiều lần

- Listener ném exception và error handler retry.
- Recoverer gửi DLT thất bại, nên quá trình recovery chưa hoàn tất.
- Container dừng hoặc JVM crash sau khi side effect đã xảy ra nhưng trước commit.
- Consumer mất group membership hoặc bị rebalance khi đang xử lý.
- Thời gian xử lý vượt giới hạn poll, khiến consumer rời group và partition được giao cho member khác.
- Commit thất bại hoặc không được thực hiện theo AckMode dự kiến.
- Ứng dụng chủ động seek/nack để đọc lại record.
- Producer publish cùng event nhiều lần do retry gửi hoặc lỗi ở tầng gọi nghiệp vụ.
- Hai listener hoặc hai ứng dụng dùng group ID khác nhau cùng subscribe một topic; mỗi group nhận một bản độc lập của record.
- Retry topic đưa record trở lại listener theo lịch backoff.
- Batch listener thất bại khiến một phần hoặc toàn bộ batch được giao lại.

Cần kiểm tra log theo group ID, topic, partition, offset và event ID. Nếu hai group ID khác nhau cùng đọc topic, mỗi group gọi listener một lần là hành vi bình thường, không phải Kafka giao trùng trong cùng group. Nếu chỉ tìm theo message text hoặc business key, có thể nhầm hai record khác nhau là một lần retry.

## 4. Blocking retry với DefaultErrorHandler

`DefaultErrorHandler` là error handler phổ biến cho record listener. Khi listener ném exception, handler áp dụng backoff và thử lại record. Trong khoảng retry, partition có thể bị chặn tại record lỗi, nên các record phía sau trên partition đó chưa được xử lý tiếp.

Ví dụ retry hai lần sau lần xử lý đầu tiên:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 2L)
            );

    return handler;
}
```

Với `FixedBackOff(1_000L, 2L)`, handler chờ một giây giữa các lần retry và thực hiện hai lần retry sau lần gọi đầu tiên: tổng cộng tối đa ba lần xử lý trước khi recover. Tham số thứ hai là số lần retry, không phải tổng số lần gọi.

Cấu hình handler trên listener container factory:

```java
factory.setCommonErrorHandler(kafkaErrorHandler);
```

Khi dùng Spring Boot, có thể đăng ký bean `CommonErrorHandler` để cấu hình factory tự động hoặc gắn handler vào factory riêng. Nếu có nhiều factory, hãy xác nhận listener đang dùng đúng bean qua thuộc tính `containerFactory` của `@KafkaListener`.

## 5. Chọn exception nào được retry?

Không phải lỗi nào cũng nên retry. Lỗi tạm thời như database connection timeout hoặc HTTP 503 có thể phục hồi sau một khoảng chờ. Lỗi dữ liệu như schema sai, thiếu field bắt buộc hoặc business rule không hợp lệ thường không tự hết khi thử lại.

Có thể phân loại exception:

```java
import org.springframework.kafka.support.ExponentialBackOffWithMaxRetries;

DefaultErrorHandler handler =
        new DefaultErrorHandler(
                recoverer,
                new ExponentialBackOffWithMaxRetries(4)
        );

handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class
);
```

Ví dụ này minh họa việc đánh dấu exception nghiệp vụ không retry. Các exception không retry sẽ đi thẳng đến recoverer theo phân loại của handler. Hãy cấu hình exception classifier có chủ đích và tránh đánh dấu mọi exception là retryable.

Một số lỗi hạ tầng có thể tạm thời nhưng retry quá nhanh làm tăng tải lên hệ thống đang lỗi. Chọn backoff có giới hạn, cân nhắc exponential backoff và jitter nếu hệ thống có nhiều consumer cùng retry.

## 6. DLT và lỗi trong quá trình recovery

Sau khi hết retry, `DeadLetterPublishingRecoverer` có thể publish record sang dead-letter topic. Nếu publish DLT thất bại, recovery chưa hoàn tất; record nguồn không nên được xem là đã xử lý thành công.

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                dltKafkaTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()
                )
        );

recoverer.setFailIfSendResultIsError(true);
```

Nếu dùng partition mapping như ví dụ, DLT phải có đủ partition tương ứng. Nếu DLT ít partition hơn topic nguồn, chọn partition routing khác hoặc để producer chọn partition.

Khi listener bị gọi lặp lại dù đã hết retry, hãy kiểm tra:

- DLT publish có thành công không.
- Producer DLT có serialize được key/value thực tế không.
- Recoverer có ném exception do send timeout hoặc broker lỗi không.
- Error handler có được cấu hình đúng cho listener container không.
- Offset có được commit sau recovery theo AckMode và version đang dùng không.

Không nuốt lỗi publish DLT. Nếu mất record ở cả topic nguồn và DLT, quá trình điều tra và khôi phục sẽ khó hơn nhiều.

## 7. Non-blocking retry với @RetryableTopic

`@RetryableTopic` đưa record lỗi sang retry topic thay vì giữ partition nguồn chờ backoff. Listener sẽ được gọi lại khi record đến retry topic theo lịch đã cấu hình.

Ví dụ:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000
        ),
        dltTopicSuffix = ".DLT"
)
@KafkaListener(
        topics = "orders",
        groupId = "orders-service"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

`attempts` biểu thị tổng số lần xử lý, bao gồm lần đầu trên topic gốc. Ví dụ `attempts = "4"` nghĩa là tối đa bốn lần xử lý trước khi record được chuyển tới DLT, theo semantics của retry topic configuration.

Non-blocking retry làm giảm việc chặn partition gốc, nhưng có thể thay đổi thứ tự nghiệp vụ: record phía sau trên topic gốc có thể được xử lý trước record đang chờ ở retry topic. Cần cân nhắc nếu thứ tự theo key là yêu cầu bắt buộc.

Non-blocking retry của Spring Kafka không hỗ trợ batch listener và không kết hợp với container transactions. Hãy kiểm tra tài liệu của phiên bản Spring Kafka đang dùng trước khi bật; nếu listener cần batch hoặc container transaction, chọn chiến lược retry phù hợp với các giới hạn đó.

## 8. Blocking retry và non-blocking retry khác nhau thế nào?

| Tiêu chí | Blocking retry | Non-blocking retry |
|---|---|---|
| Cơ chế | Error handler retry trên consumer/partition | Publish sang retry topic |
| Partition nguồn | Có thể bị chặn tại record lỗi | Có thể tiếp tục xử lý record phía sau |
| Thứ tự | Dễ giữ thứ tự trong partition hơn | Có thể đảo thứ tự giữa record lỗi và record phía sau |
| Topic phụ | Không cần retry topic cho mỗi lần retry | Cần retry topic và DLT |
| Vận hành | Theo dõi backoff, retry và DLT publish | Theo dõi retry topic, routing, DLT và nhiều consumer group |
| Phù hợp | Cần giữ thứ tự, retry ngắn và lỗi tạm thời | Có thể chấp nhận xử lý bất đồng bộ và cần tránh block partition |

Không nên cấu hình blocking retry với thời gian chờ quá dài cho một lỗi không thể phục hồi. Ngược lại, non-blocking retry không phù hợp nếu nghiệp vụ yêu cầu record sau không được vượt qua record trước trên cùng key.

## 9. Offset, AckMode và listener bị gọi lại

AckMode quyết định thời điểm container commit offset sau khi xử lý:

| AckMode | Hành vi khái quát |
|---|---|
| `RECORD` | Commit sau khi listener xử lý thành công từng record |
| `BATCH` | Commit sau khi xử lý các record trong poll batch |
| `MANUAL` | Listener gọi acknowledge; container commit theo semantics của mode |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge được gọi trong điều kiện thread/configuration phù hợp |

Với `BATCH`, nếu một record trong batch lỗi, các record khác có thể đã chạy side effect trước khi batch được retry. Nếu không idempotent, side effect của record đã xử lý thành công có thể lặp.

Với manual ack, chỉ acknowledge sau khi công việc nghiệp vụ đã hoàn tất theo contract. Không ack trước khi tác vụ bất đồng bộ hoàn tất. Nếu listener khởi chạy future rồi trả về mà không có cơ chế async acknowledgment đúng, container có thể commit sớm hơn thời điểm side effect kết thúc.

Không dùng commit sớm để giảm lag nếu điều đó làm mất khả năng giao lại record khi xử lý thất bại.

### Khi listener container dùng Kafka transaction

Nếu container được cấu hình transaction, exception từ listener làm transaction hiện tại rollback. Việc đưa record chưa xử lý về để đọc lại do `DefaultAfterRollbackProcessor` đảm nhiệm; luồng này khác với cấu hình record listener không dùng container transaction và `DefaultErrorHandler` thông thường. Hãy kiểm tra transaction manager, rollback behavior, backoff và recoverer của after-rollback processor trước khi kết luận retry count.

Kafka transaction có thể phối hợp việc consume và publish Kafka record trong một transaction, nhưng không tự rollback database hoặc HTTP side effect bên ngoài Kafka. Nếu listener đã gọi external API trước khi transaction rollback, lần giao lại vẫn có thể gọi API lần nữa. Vẫn cần idempotency hoặc outbox/inbox phù hợp.

## 10. Listener bị gọi lại sau restart hoặc rebalance

Kafka lưu committed offset theo group. Nếu consumer đã xử lý record nhưng chưa commit offset, consumer mới có thể đọc lại record đó sau restart hoặc rebalance.

Ví dụ:

```text
offset 100: listener xử lý thành công, ghi database
process crash trước commit
consumer mới nhận partition
offset 100 được đọc lại
listener xử lý lại cùng record
```

Trường hợp này có thể xảy ra dù listener không ném exception. Đây là hành vi at-least-once, không phải lỗi Kafka.

Kiểm tra:

- Log shutdown và startup quanh thời điểm record bị gọi lại.
- Group member thay đổi và rebalance event.
- Commit interval, AckMode và transaction.
- Thời gian xử lý record so với `max.poll.interval.ms`.
- Side effect đã commit ở database hay chưa.
- Consumer có bị terminate cưỡng bức trước khi container dừng graceful không.

## 11. Batch listener và retry toàn batch

Với batch listener, một lần gọi listener có thể nhận nhiều record. Nếu listener ném exception chung, container không phải lúc nào cũng biết record nào gây lỗi; tùy handler, cả batch có thể được retry.

Nếu xác định được record lỗi, có thể ném `BatchListenerFailedException` với record/index tương ứng để error handler xử lý phần đã thành công và phần lỗi theo semantics hỗ trợ.

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-batch-service"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderEvent> record = records.get(index);

        try {
            orderService.process(record.value());
        }
        catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Cannot process order",
                    exception,
                    index
            );
        }
    }
}
```

Cần dùng error handler và batch listener configuration tương thích. Nếu không xác định chính xác index record lỗi, retry cả batch có thể gọi lại side effect của các record đã xử lý trước đó.

## 12. Deserialization failure không phải lúc nào cũng gọi listener

Nếu key/value không deserialize được, lỗi có thể xảy ra trước khi method listener được gọi. Vì vậy log không thấy listener invocation không có nghĩa record không bị retry hoặc recover.

Dùng `ErrorHandlingDeserializer` để chuyển lỗi deserialize thành thông tin exception trong headers, cho phép container error handler xử lý. Nếu DLT phải giữ raw bytes, producer DLT cần serializer hỗ trợ byte array.

Cần phân biệt:

- Deserializer lỗi trước listener.
- Message converter lỗi khi chuyển record thành tham số method.
- Listener method chạy và ném exception.
- Business validation lỗi sau khi DTO đã được tạo.

Mỗi lỗi phát sinh ở tầng khác nhau và cần log/metric phù hợp. Không chỉ thêm log ở đầu listener rồi kết luận rằng mọi record retry đều phải xuất hiện tại đó.

## 13. Đo số lần gọi và truy vết một record

Để xác định listener có bị gọi lặp, log metadata ổn định của record:

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service"
)
public void onOrder(
        OrderEvent event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(name = KafkaHeaders.DELIVERY_ATTEMPT, required = false)
        Integer deliveryAttempt) {

    log.info(
            "Processing order eventId={}, topic={}, partition={}, offset={}, deliveryAttempt={}",
            event.eventId(),
            topic,
            partition,
            offset,
            deliveryAttempt
    );

    orderService.process(event);
}
```

Các import liên quan trong ví dụ:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.kafka.support.KafkaHeaders;
```

Dùng event ID để nhận diện cùng một sự kiện nghiệp vụ; dùng topic-partition-offset để nhận diện một record Kafka cụ thể. Khi event được gửi sang retry topic hoặc publish lại, topic/partition/offset sẽ khác nhưng event ID có thể giữ nguyên.

Có thể bật delivery attempt header trên error handler ở các phiên bản hỗ trợ:

```java
handler.setDeliveryAttemptHeader(true);
```

Sau đó đọc header delivery attempt bằng API tương ứng của phiên bản Spring Kafka. Không dựa vào header này như ID toàn cục; nó chỉ mô tả số lần giao trong phạm vi cơ chế error handling đó.

Theo dõi thêm:

- Listener invocation count.
- Retry attempt count.
- Recovery và DLT publish success/failure.
- Listener processing duration.
- Consumer lag và commit rate.
- Rebalance count và group member changes.
- Duplicate event ID hoặc duplicate business key.

Không log toàn bộ payload nếu chứa thông tin cá nhân, token hoặc dữ liệu nhạy cảm.

## 14. Idempotency để ngăn side effect bị lặp

Retry và redelivery không thể tự bảo đảm side effect chỉ xảy ra một lần. Listener cần thiết kế idempotent nếu cùng event có thể được xử lý nhiều lần.

Một cách phổ biến là lưu event ID đã xử lý trong cùng transaction database với thay đổi nghiệp vụ:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Luồng xử lý:

1. Bắt đầu database transaction.
2. Thử insert event ID vào bảng processed events với unique constraint.
3. Nếu event ID đã tồn tại, kết thúc mà không lặp side effect.
4. Nếu insert thành công, thực hiện thay đổi nghiệp vụ trong cùng transaction.
5. Commit transaction.
6. Chỉ sau khi listener hoàn tất, container mới commit Kafka offset theo AckMode.

Không chỉ dùng thao tác check-then-insert không có unique constraint; hai consumer hoặc hai lần xử lý đồng thời có thể cùng vượt qua bước check. Unique constraint hoặc cơ chế atomic insert mới là hàng rào chống duplicate.

Với external API, truyền idempotency key ổn định nếu nhà cung cấp hỗ trợ. Với luồng database rồi publish event, cân nhắc transactional outbox. Event ID nên được tạo từ producer và giữ nguyên qua retry/DLT/replay.

Không dùng riêng offset Kafka làm idempotency key nghiệp vụ vì cùng một event được publish lại sẽ có offset mới.

## 15. Những lỗi cấu hình khiến listener retry mãi

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Listener lặp lại liên tục | Backoff/retry không có giới hạn hoặc exception luôn retryable | Đặt retry limit và phân loại exception |
| Listener lặp lại sau khi đã ghi DB | Crash trước commit Kafka hoặc commit thất bại | Thiết kế idempotent và kiểm tra commit |
| Listener không tới DLT | Recoverer chưa được gắn vào đúng container factory hoặc chưa hết retry | Kiểm tra listener factory và retry count |
| DLT publish lỗi | Serializer không hỗ trợ kiểu value/key hoặc broker/topic không sẵn sàng | Kiểm tra DLT producer, serializer và send result |
| Partition bị kẹt tại một record | Blocking retry đang chờ hoặc lỗi phục hồi lặp | Kiểm tra backoff, exception và recovery failure |
| Record sau được xử lý trước record lỗi | Non-blocking retry đưa record sang retry topic | Đánh giá lại yêu cầu ordering |
| Listener bị gọi lại sau deploy | Offset chưa commit trước khi instance dừng | Graceful shutdown và idempotency |
| Batch tạo side effect trùng | Toàn batch bị retry sau một record lỗi | Dùng `BatchListenerFailedException` và xử lý idempotent |
| Không thấy log listener khi record lỗi | Deserialize/conversion lỗi trước khi method được gọi | Dùng `ErrorHandlingDeserializer` và log error handler |
| Retry không dừng với lỗi dữ liệu | Exception nghiệp vụ bị phân loại retryable | Đánh dấu non-retryable và recover vào DLT |

## 16. Runbook điều tra listener bị gọi lặp

Khi phát hiện cùng event xuất hiện nhiều lần, thực hiện theo trình tự:

1. Lấy event ID và metadata topic, partition, offset từ log.
2. So sánh các lần gọi: cùng offset hay các offset khác nhau?
3. Nếu cùng offset, kiểm tra blocking retry, commit, restart và rebalance.
4. Nếu offset khác nhưng event ID giống, kiểm tra producer retry, retry topic, DLT replay hoặc duplicate publish.
5. Đối chiếu timestamp với listener exception, error handler log và recovery result.
6. Kiểm tra AckMode, commit strategy, transaction và thời gian xử lý.
7. Kiểm tra DLT/retry topic có publish lỗi hoặc chuyển record theo cấu hình không.
8. Xác định side effect đã xảy ra ở lần trước hay chưa.
9. Kiểm tra idempotency key/unique constraint và sửa đường xử lý trước khi replay.
10. Sau khi khắc phục, theo dõi listener invocation count, lag, commit và DLT backlog.

Không xóa record hoặc reset offset chỉ để làm log bớt lặp. Hãy giữ lại metadata đủ để tái hiện và điều tra sự cố.

## 17. Kiểm thử retry và redelivery

Dùng Embedded Kafka hoặc Testcontainers để kiểm thử trên broker thật. Mỗi test nên dùng topic/group riêng hoặc dọn trạng thái rõ ràng để tránh offset từ test trước ảnh hưởng test sau.

Các tình huống cần xác minh:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Listener ném exception hai lần rồi thành công | Số lần gọi và backoff đúng cấu hình |
| Listener luôn ném exception | Hết retry thì recover/DLT |
| DLT producer thất bại | Recovery được xem là thất bại; record không bị coi là đã recover |
| Listener ghi DB rồi process chết trước commit | Record có thể được giao lại nhưng side effect không bị lặp nhờ idempotency |
| Consumer rebalance trong lúc xử lý | Record có thể được giao lại; side effect an toàn |
| Non-blocking retry | Record chuyển đúng retry topic và cuối cùng DLT |
| Batch listener có record lỗi ở giữa | Chỉ phần cần retry được xử lý lại theo handler đã cấu hình |
| JSON payload lỗi | Lỗi deserialize được error handler nhận diện |
| Exception không retryable | Đi thẳng tới recovery theo classifier |
| Event được replay | Event ID giữ nguyên và consumer không lặp side effect |

Dùng Awaitility hoặc polling assertion có deadline thay vì sleep cố định. Assert cả số lần listener invocation, offset, event ID, record ở retry/DLT và trạng thái side effect database. Đừng chỉ assert rằng listener cuối cùng đã chạy thành công.

## 18. Checklist ngăn và xử lý listener bị gọi lặp

1. Ghi event ID cùng topic, partition và offset cho mỗi lần xử lý.
2. Xác định retry là blocking, non-blocking hay redelivery sau restart.
3. Cấu hình retry có giới hạn và backoff phù hợp.
4. Phân loại exception tạm thời và lỗi dữ liệu không retry.
5. Kiểm tra recoverer/DLT publish result.
6. Chọn AckMode và commit strategy theo thời điểm hoàn tất nghiệp vụ.
7. Thiết kế idempotency bằng event ID và unique constraint.
8. Với batch listener, xác định rõ record lỗi và semantics retry.
9. Theo dõi rebalance, max poll interval và graceful shutdown.
10. Kiểm thử crash trước commit, recovery failure, retry topic và DLT replay.
11. Không dùng log message giống nhau làm bằng chứng duy nhất rằng cùng record bị giao lại.
12. Chỉ replay sau khi đã khắc phục nguyên nhân và bảo đảm side effect an toàn.

Listener bị gọi nhiều lần thường là biểu hiện của retry hoặc at-least-once delivery. Khi truy vết bằng event ID và topic-partition-offset, hiểu rõ commit/rebalance và thiết kế idempotent, ứng dụng Spring Kafka có thể phục hồi lỗi mà không tạo tác động nghiệp vụ trùng lặp.
