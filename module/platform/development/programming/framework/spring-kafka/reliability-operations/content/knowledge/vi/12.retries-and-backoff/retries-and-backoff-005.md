# Số lần giao tối đa

Trong Spring Kafka, một record có thể được listener nhận nhiều lần nếu xử lý thất bại và error handler thực hiện retry. Khi cấu hình retry, cần xác định rõ số lần giao tối đa: listener được phép xử lý record ban đầu bao nhiêu lần, có bao nhiêu lần thử lại, và sau khi hết giới hạn thì record được phục hồi hoặc chuyển đi đâu.

Điểm dễ nhầm là một số cấu hình đếm **số lần retry**, trong khi một số cấu hình đếm **tổng số lần thử bao gồm lần đầu tiên**. Với `DefaultErrorHandler` kết hợp `FixedBackOff`, `maxAttempts` của backoff là số lần retry sau lần giao ban đầu. Với retry topic của Spring Kafka, thuộc tính `attempts` biểu diễn tổng số lần thử, bao gồm lần xử lý ban đầu. Cần phân biệt hai cách đếm trước khi đưa cấu hình vào production.

## 1. Delivery, attempt và retry

Các thuật ngữ thường được dùng gần giống nhau nhưng có ý nghĩa khác nhau:

- **Delivery:** một lần record được consumer giao đến listener để xử lý.
- **Attempt:** một lần thử xử lý record. Lần xử lý ban đầu cũng là một attempt.
- **Retry:** một lần thử lại sau khi attempt trước thất bại.
- **Recovery:** hành động được thực hiện khi không retry thêm, chẳng hạn gửi record đến dead-letter topic (DLT), ghi nhận lỗi hoặc đưa vào quy trình xử lý thủ công.

Nếu listener nhận record một lần, xử lý thất bại và được gọi lại ba lần, tổng số lần giao là bốn: một lần ban đầu và ba lần retry.

```text
Attempt 1: lần giao ban đầu -> thất bại
     |
     v
Attempt 2: retry lần 1 -> thất bại
     |
     v
Attempt 3: retry lần 2 -> thất bại
     |
     v
Attempt 4: retry lần 3 -> thất bại
     |
     v
Hết giới hạn -> recovery / DLT
```

Số lần giao tối đa là giới hạn cho một chu kỳ retry được cấu hình. Nó không đồng nghĩa với số lần một event có thể xuất hiện trong toàn bộ vòng đời hệ thống: restart, rebalance, replay thủ công, tạo group ID mới hoặc một quy trình retry độc lập có thể làm record được xử lý lại ở một thời điểm khác.

## 2. Số lần giao tối đa với DefaultErrorHandler và FixedBackOff

`DefaultErrorHandler` của Spring Kafka dùng một `BackOff` để xác định số lần retry và khoảng chờ giữa các lần thử. Khi dùng `FixedBackOff`, constructor nhận hai tham số:

```java
new FixedBackOff(interval, maxAttempts)
```

Trong đó:

| Tham số | Ý nghĩa |
|---|---|
| `interval` | Khoảng chờ giữa các lần retry, tính bằng millisecond. |
| `maxAttempts` | Số lần retry tối đa sau lần giao ban đầu. |

Ví dụ:

```java
FixedBackOff backOff = new FixedBackOff(1_000L, 3L);
DefaultErrorHandler errorHandler = new DefaultErrorHandler(backOff);
```

Listener được giao record ban đầu. Nếu lần đó thất bại, handler cho phép retry tối đa ba lần, mỗi lần cách nhau một giây. Nếu tất cả lần thử đều thất bại, tổng số lần listener có thể được gọi trong chu kỳ này là bốn.

| `maxAttempts` trong FixedBackOff | Lần giao ban đầu | Retry tối đa | Tổng lần giao tối đa |
|---:|---:|---:|---:|
| 0 | 1 | 0 | 1 |
| 1 | 1 | 1 | 2 |
| 2 | 1 | 2 | 3 |
| 3 | 1 | 3 | 4 |
| 5 | 1 | 5 | 6 |

Có thể nhớ công thức:

```text
Tổng lần giao tối đa = 1 + số lần retry tối đa
```

Giá trị `maxAttempts=0` có nghĩa là không retry. Sau lần giao ban đầu thất bại, handler chuyển ngay đến recovery theo cấu hình. Đây là lựa chọn phù hợp với lỗi không thể khắc phục bằng cách thử lại, hoặc khi muốn đưa record lỗi vào DLT ngay.

## 3. Cấu hình DefaultErrorHandler với số lần retry rõ ràng

Ví dụ sau cho phép một lần giao ban đầu và ba lần retry, với khoảng chờ một giây:

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler() {
        FixedBackOff backOff = new FixedBackOff(1_000L, 3L);
        return new DefaultErrorHandler(backOff);
    }
}
```

Gắn handler vào listener container factory:

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
```

Listener xử lý record:

```java
@KafkaListener(topics = "orders")
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

Khi `orderService.handle()` ném exception, container chuyển lỗi đến `DefaultErrorHandler`. Handler sử dụng backoff để quyết định có retry hay không. Khi backoff hết, recoverer được gọi. Nếu không truyền recoverer tùy chỉnh, handler vẫn có hành vi recovery mặc định; trong production, cần xác định rõ record lỗi được ghi log, bỏ qua hay gửi đến DLT theo chính sách ứng dụng.

## 4. Số lần thử với Retry Topic

Spring Kafka cũng hỗ trợ non-blocking retry bằng retry topic. Thay vì giữ consumer chính trong chu kỳ retry tại chỗ, record lỗi được chuyển sang topic retry theo lịch backoff. Listener trên retry topic thử xử lý lại sau khoảng chờ được cấu hình.

Với `@RetryableTopic`, thuộc tính `attempts` là **tổng số lần thử**, bao gồm lần giao ban đầu. Ví dụ:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0),
    dltTopicSuffix = ".DLT"
)
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

Với `attempts = "4"`, luồng có tối đa bốn attempt: một lần ở topic chính và tối đa ba lần ở các retry topic. Khi hết attempt mà vẫn thất bại, record được chuyển đến DLT theo cấu hình retry topic.

| Cấu hình `attempts` | Lần giao ban đầu | Lần retry tối đa | Tổng lần thử tối đa |
|---:|---:|---:|---:|
| `"1"` | 1 | 0 | 1 |
| `"2"` | 1 | 1 | 2 |
| `"3"` | 1 | 2 | 3 |
| `"4"` | 1 | 3 | 4 |
| `"5"` | 1 | 4 | 5 |

Vì `attempts` là tổng số lần thử, không cộng thêm một lần ban đầu khi tính cấu hình retry topic. Đây là điểm khác với `FixedBackOff.maxAttempts` trong blocking retry.

## 5. So sánh cách đếm giữa blocking retry và retry topic

Hai cơ chế đều có thể giới hạn số lần listener thử xử lý record, nhưng cách cấu hình và vận hành khác nhau:

| Cơ chế | Thuộc tính đếm | Cách hiểu | Ví dụ tổng lần giao |
|---|---|---|---:|
| `DefaultErrorHandler` + `FixedBackOff` | `maxAttempts` | Số retry sau lần ban đầu. | `maxAttempts=3` -> 4 lần. |
| `@RetryableTopic` | `attempts` | Tổng số attempt, gồm lần ban đầu. | `attempts="4"` -> 4 lần. |

Không sao chép nguyên một con số giữa hai cơ chế mà không đổi cách diễn giải. Nếu yêu cầu nghiệp vụ là “tối đa bốn lần giao”, có thể cấu hình `FixedBackOff(..., 3L)` hoặc `@RetryableTopic(attempts = "4")`. Hai cấu hình có tổng lần thử tương đương về mặt đếm, nhưng thời gian retry, thứ tự và cách xử lý lỗi khác nhau.

Blocking retry phù hợp khi muốn thử lại nhanh trong cùng consumer flow và số lần retry nhỏ. Non-blocking retry topic phù hợp khi cần trì hoãn lâu hơn mà không giữ partition consumer chính trong thời gian chờ. Retry topic tạo thêm topic, consumer và luồng điều phối; thứ tự record có thể thay đổi khi record được chuyển sang retry topic rồi quay lại xử lý.

## 6. Điều gì xảy ra sau lần giao cuối cùng?

Khi số lần retry đã hết, error handler cần có một hành động recovery rõ ràng. Một số lựa chọn:

- Gửi record sang DLT để điều tra hoặc xử lý lại sau.
- Ghi log và lưu metadata lỗi trong một kho theo dõi.
- Chuyển record sang quy trình xử lý thủ công.
- Bỏ qua record chỉ khi nghiệp vụ cho phép và quyết định đó được ghi nhận.

Ví dụ dùng `DeadLetterPublishingRecoverer` với `DefaultErrorHandler`:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);
    FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

    return new DefaultErrorHandler(recoverer, backOff);
}
```

Sau một lần giao ban đầu và ba lần retry thất bại, recoverer gửi record sang DLT theo quy tắc định tuyến. Với cấu hình mặc định, tên topic DLT thường dùng hậu tố `.DLT`; cần tạo topic đích, cấu hình số partition và serializer phù hợp. Nếu publish DLT thất bại, recovery chưa hoàn tất và handler phải xử lý lỗi recovery theo cấu hình.

Với retry topic, có thể khai báo DLT handler:

```java
@DltHandler
public void handleDlt(OrderCreated event) {
    log.error("Order event exhausted retry attempts: eventId={}",
            event.eventId());
}
```

DLT handler nên ghi nhận event ID, topic gốc, partition, offset, exception và thời điểm xử lý để có thể điều tra. Không nên chỉ log payload rồi xóa dấu vết lỗi. Nếu cần replay, hãy có quy trình chọn record, xác định nguyên nhân gốc và kiểm soát khả năng xử lý trùng.

## 7. Exception không retry làm giảm số lần giao

Số lần giao tối đa cấu hình trong backoff là giới hạn trên cho các lỗi được phép retry. `DefaultErrorHandler` có thể phân loại một số exception là không retry. Khi gặp lỗi loại này, handler có thể bỏ qua các lần retry và chuyển thẳng đến recoverer.

Ví dụ:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler() {
    FixedBackOff backOff = new FixedBackOff(1_000L, 3L);
    DefaultErrorHandler handler = new DefaultErrorHandler(backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedCurrencyException.class);

    return handler;
}
```

Trong cấu hình này, lỗi `InvalidOrderException` và `UnsupportedCurrencyException` không sử dụng đủ ba retry. Chúng được chuyển đến recovery theo chính sách của handler. Các lỗi tạm thời khác có thể dùng backoff đã cấu hình.

Nên phân loại theo bản chất lỗi:

- Timeout hoặc lỗi kết nối tạm thời: thường có thể retry với giới hạn.
- Dữ liệu không hợp lệ hoặc thiếu trường bắt buộc: thường không có ích khi retry cùng payload.
- Vi phạm quy tắc nghiệp vụ: cần xác định có phải trạng thái tạm thời hay lỗi vĩnh viễn.
- Lỗi lập trình: retry nhiều lần thường chỉ kéo dài thời gian phát hiện lỗi.

Khi exception bị wrap trong một exception khác, hãy kiểm tra cause chain và cấu hình classifier phù hợp. Nếu phân loại sai, record có thể bị retry quá nhiều hoặc bị chuyển DLT quá sớm.

## 8. Số lần giao tối đa không phải giới hạn toàn cục của event

Một giới hạn retry thường áp dụng cho một chu kỳ xử lý do error handler điều phối. Nó không nhất thiết giới hạn tổng số lần một event được xử lý trong mọi lần chạy của hệ thống.

Ví dụ với blocking retry:

1. Consumer nhận event và xử lý thất bại.
2. Error handler cho phép ba lần retry sau lần ban đầu.
3. Process dừng hoặc consumer bị rebalance trước khi hoàn tất chu kỳ.
4. Partition được giao cho member khác; record có thể được đọc lại từ committed offset.
5. Một chu kỳ xử lý mới có thể bắt đầu.

Vì vậy, tổng số lần listener được gọi trong toàn bộ vòng đời event có thể lớn hơn `1 + maxAttempts`. Số lần giao còn phụ thuộc commit offset, restart, rebalance và replay do vận hành.

Với retry topic, trạng thái retry được thể hiện qua việc record di chuyển giữa các topic retry và các header liên quan. Tuy nhiên, replay thủ công, publish lại record hoặc tạo một luồng retry mới vẫn có thể làm event xuất hiện thêm lần nữa. Không nên dùng retry count như một khóa chống trùng nghiệp vụ.

Nếu yêu cầu nghiệp vụ đặt ra giới hạn tuyệt đối cho một event, hãy lưu trạng thái attempt bền vững theo event ID ở một nơi phù hợp và xác định cách xử lý khi trạng thái đó không khả dụng. Đây là một chính sách nghiệp vụ riêng, không thể thay thế chỉ bằng số retry của error handler.

## 9. Quan sát số lần giao bằng delivery attempt header

Với `DefaultErrorHandler`, Spring Kafka có thể đưa số lần giao vào header `KafkaHeaders.DELIVERY_ATTEMPT` khi bật `deliveryAttemptHeader`. Thuộc tính này mặc định không bật trong các cấu hình thông thường của handler; cần kiểm tra phiên bản đang dùng.

Ví dụ cấu hình:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler() {
    DefaultErrorHandler handler =
            new DefaultErrorHandler(new FixedBackOff(1_000L, 3L));
    handler.setDeliveryAttemptHeader(true);
    return handler;
}
```

Listener có thể đọc header:

```java
@KafkaListener(topics = "orders")
public void consume(
        OrderCreated event,
        @Header(name = KafkaHeaders.DELIVERY_ATTEMPT,
                required = false,
                defaultValue = "1") Integer deliveryAttempt) {

    log.info("Processing order event, deliveryAttempt={}", deliveryAttempt);
    orderService.handle(event);
}
```

Giá trị header giúp log và metric biết listener đang ở lần giao nào trong cơ chế hỗ trợ. Header không phải bộ đếm toàn cục bất biến của event. Khi record được replay hoặc đi qua một cơ chế khác, cách đếm có thể thay đổi. Nếu cần đối chiếu xuyên suốt, hãy log thêm event ID và metadata topic/partition/offset.

## 10. Tính tổng thời gian của số lần giao

Giới hạn số lần giao ảnh hưởng trực tiếp đến thời gian một record có thể nằm trong retry. Với fixed backoff:

```text
T_backoff = interval × số lần retry
T_processing = tổng thời gian thực thi listener qua mọi attempt
T_total ≈ T_backoff + T_processing + T_overhead
```

Ví dụ:

```text
Lần giao tối đa: 4
Thời gian mỗi lần listener: 800 ms
Khoảng chờ: 1.000 ms
Số retry: 3

T_processing = 4 × 800 ms = 3.200 ms
T_backoff = 3 × 1.000 ms = 3.000 ms
T_total ≈ 6.200 ms + overhead
```

Đây là thời gian gần đúng trong trường hợp mọi attempt đều thất bại. Nếu dependency timeout mất 10 giây ở mỗi lần thử, thời gian thực tế sẽ cao hơn nhiều.

Blocking retry diễn ra trong luồng xử lý consumer và có thể làm chậm lần `poll()` tiếp theo. Khi tổng thời gian xử lý và backoff tiến gần `max.poll.interval.ms`, consumer có thể bị loại khỏi group và gây rebalance. Hãy tính cả thời gian timeout của database/HTTP, batch size và khoảng chờ, không chỉ lấy interval nhân số retry.

Retry topic có thể trì hoãn record sang một topic khác và cho consumer chính tiếp tục xử lý record khác. Tuy nhiên, thời gian đến lần thử kế tiếp phụ thuộc lịch backoff, lịch poll của retry consumer và tình trạng tải của topic retry. Cấu hình số lần attempt không đồng nghĩa với SLA hoàn tất record.

## 11. Retry có thể tạo xử lý trùng

Nếu listener đã tạo hiệu ứng bên ngoài rồi thất bại trước khi offset được commit, record có thể được giao lại. Ví dụ, listener gọi API thanh toán thành công nhưng process dừng trước commit. Lần giao tiếp theo có thể gọi API lần nữa.

Thiết kế idempotency theo event ID:

```java
@Transactional
public void handle(OrderCreated event) {
    if (processedEventRepository.existsByEventId(event.eventId())) {
        return;
    }

    orderRepository.createOrder(event);
    processedEventRepository.save(event.eventId());
}
```

Trong ứng dụng thực tế, cần unique constraint trên event ID và lưu dấu vết cùng transaction với thay đổi nghiệp vụ để tránh race condition. Với API bên ngoài, dùng idempotency key nếu API hỗ trợ. Nếu không, cần thiết kế quy trình đối soát hoặc outbox/inbox phù hợp.

Số lần giao tối đa giới hạn số lần thử trong chính sách retry, còn idempotency bảo vệ nghiệp vụ trước việc cùng một event được giao nhiều lần. Hai cơ chế phục vụ hai mục đích khác nhau.

## 12. Theo dõi và cảnh báo theo số lần giao

Để vận hành retry có kiểm soát, nên quan sát các chỉ số sau:

- Tổng số listener delivery theo topic và consumer group.
- Số lần retry theo exception type và listener endpoint.
- Số record đạt lần giao cuối cùng và được chuyển đến DLT.
- Số lần recovery thất bại hoặc publish DLT thất bại.
- Phân bố delivery attempt, đặc biệt tỷ lệ record phải thử từ lần thứ hai trở đi.
- Thời gian xử lý mỗi attempt và tổng thời gian retry.
- Consumer lag, poll interval và số lần rebalance.

Có thể dùng `RetryListener` của `DefaultErrorHandler` để quan sát delivery thất bại:

```java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        log.warn("Delivery failed: topic={}, partition={}, offset={}, attempt={}",
                record.topic(),
                record.partition(),
                record.offset(),
                deliveryAttempt,
                exception);
    }
});
```

Chữ ký API có thể khác giữa các phiên bản Spring Kafka; kiểm tra dependency đang dùng trước khi triển khai. Log nên có event ID và exception type để hỗ trợ truy vết. Tránh ghi toàn bộ payload nếu record chứa dữ liệu nhạy cảm.

Đặt cảnh báo khi tỷ lệ record phải retry tăng đột biến, DLT tăng nhanh, recovery thất bại hoặc lag tăng đồng thời với retry. Nếu chỉ theo dõi số lần listener thất bại mà không theo dõi DLT và lag, có thể bỏ sót tình trạng record bị chuyển khỏi luồng chính hoặc consumer bị chậm.

## 13. Những lỗi thường gặp khi cấu hình số lần giao tối đa

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Listener được gọi nhiều hơn dự kiến | Nhầm `maxAttempts` của FixedBackOff là tổng lần giao. | Tính `1 + maxAttempts`. |
| Retry topic có số lần thử ít hơn mong đợi | Nhầm `attempts` là số retry thay vì tổng attempt. | Nhớ `@RetryableTopic(attempts=...)` bao gồm lần ban đầu. |
| Record đi DLT ngay sau lần đầu | `maxAttempts=0`, `attempts="1"` hoặc exception không retry. | Kiểm tra cơ chế retry và exception classification. |
| Record được xử lý nhiều hơn giới hạn cấu hình | Restart, rebalance hoặc replay tạo chu kỳ giao mới. | Đối chiếu event ID, offset, committed offset và lịch sử deployment. |
| Consumer bị rebalance khi retry | Backoff và thời gian listener vượt ngân sách poll. | Tính tổng thời gian xử lý và điều chỉnh interval, số lần retry hoặc cơ chế retry. |
| DLT tăng nhanh | Dependency lỗi kéo dài hoặc số lần giao quá thấp. | Phân tích exception, thời gian phục hồi và chính sách recovery. |
| Nghiệp vụ bị lặp dù số lần retry có giới hạn | Listener không idempotent hoặc API ngoài không có idempotency key. | Thêm khóa chống trùng theo event ID và đối soát giao dịch. |

## 14. Quy trình chọn số lần giao cho một listener

Khi thiết kế chính sách retry, hãy làm theo trình tự:

1. Xác định lỗi nào có thể phục hồi và lỗi nào cần chuyển thẳng sang recovery.
2. Chọn blocking retry hay retry topic dựa trên thời gian chờ, thứ tự xử lý và khả năng chấp nhận thêm topic.
3. Quyết định yêu cầu nghiệp vụ là tổng số lần giao hay số lần retry bổ sung.
4. Với `FixedBackOff`, đặt `maxAttempts = tổng lần giao mong muốn - 1`.
5. Với `@RetryableTopic`, đặt `attempts` bằng tổng số lần thử mong muốn, bao gồm lần ban đầu.
6. Tính tổng thời gian xử lý và backoff; kiểm tra giới hạn `max.poll.interval.ms` nếu dùng blocking retry.
7. Xác định recoverer hoặc DLT và cách xử lý record sau lần thử cuối.
8. Thiết kế listener idempotent để chịu được restart, rebalance và replay.
9. Theo dõi delivery attempt, retry rate, DLT rate, recovery failure và consumer lag sau triển khai.

Số lần giao tối đa giúp giới hạn thời gian và tải mà một record có thể tiêu tốn trong chính sách retry. Khi hiểu rõ cách đếm của từng cơ chế, phân loại exception hợp lý và xác định recovery sau lần thử cuối, Spring Kafka có thể xử lý lỗi tạm thời mà vẫn giữ được khả năng điều tra và phục hồi các record không thể xử lý.
