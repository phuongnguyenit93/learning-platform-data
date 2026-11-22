# FixedBackOff

Trong Spring Kafka, `FixedBackOff` là một chính sách chờ có khoảng thời gian cố định giữa các lần thử lại. Khi listener ném exception, `DefaultErrorHandler` có thể dùng chính sách này để quyết định chờ bao lâu trước khi giao lại record. Nếu số lần thử lại đã hết, error handler chuyển record cho recoverer để ghi log, gửi sang dead-letter topic hoặc thực hiện một hành động phục hồi khác.

`FixedBackOff` thuộc Spring Framework (`org.springframework.util.backoff.FixedBackOff`), không phải một cấu hình riêng của Kafka broker. Nó mô tả khoảng chờ và số lần retry; `DefaultErrorHandler` sử dụng chính sách đó trong quá trình xử lý lỗi của listener container.

## 1. FixedBackOff giải quyết vấn đề gì?

Một record có thể thất bại vì nguyên nhân tạm thời, chẳng hạn database đang quá tải, dịch vụ HTTP tạm thời không phản hồi hoặc một dependency vừa khởi động lại. Nếu listener dừng ngay sau lần lỗi đầu tiên, những lỗi có thể tự phục hồi sẽ làm gián đoạn xử lý.

Retry cho phép ứng dụng thử lại sau một khoảng chờ. `FixedBackOff` giữ khoảng chờ đó không đổi giữa các lần thử:

```text
Listener nhận record
       |
       v
   Xử lý lỗi
       |
       v
   Chờ 1 giây
       |
       v
   Thử lại
       |
       v
   Xử lý lỗi
       |
       v
   Chờ 1 giây
       |
       v
   Thử lại
       |
       v
 Hết số lần retry? ---- Không ----> tiếp tục retry theo chính sách
       |
      Có
       |
       v
 Recoverer xử lý record
```

Khoảng chờ cố định phù hợp khi dependency thường phục hồi nhanh và thời gian chờ dự kiến có thể giữ ổn định. Nó cũng dễ tính tổng thời gian retry và dễ vận hành. Với hệ thống cần tăng dần khoảng chờ để giảm áp lực lên dependency đang gặp sự cố, exponential backoff có thể phù hợp hơn.

## 2. Cấu trúc và cách đếm số lần thử

`FixedBackOff` có constructor chính nhận hai giá trị:

```java
new FixedBackOff(interval, maxAttempts)
```

| Tham số | Ý nghĩa |
|---|---|
| `interval` | Khoảng chờ giữa các lần retry, tính bằng millisecond. |
| `maxAttempts` | Số lần retry tối đa sau lần xử lý ban đầu. |

Điểm dễ nhầm là `maxAttempts` không phải tổng số lần listener được gọi. Lần giao record ban đầu được tính riêng. Ví dụ:

```java
FixedBackOff backOff = new FixedBackOff(1_000L, 3L);
```

Ý nghĩa là chờ 1.000 ms giữa các lần retry và cho phép tối đa ba lần retry sau lần xử lý ban đầu. Nếu tất cả đều thất bại, listener có thể được gọi tổng cộng tối đa bốn lần:

| Lần gọi | Vai trò | Hành động tiếp theo nếu vẫn lỗi |
|---:|---|---|
| 1 | Lần xử lý ban đầu | Chờ 1 giây rồi retry lần 1. |
| 2 | Retry lần 1 | Chờ 1 giây rồi retry lần 2. |
| 3 | Retry lần 2 | Chờ 1 giây rồi retry lần 3. |
| 4 | Retry lần 3 | Hết retry; gọi recoverer. |

Với ba retry, tổng thời gian chờ backoff trong trường hợp tất cả lần xử lý đều lỗi là khoảng ba giây. Thời gian thực tế còn bao gồm thời gian listener thực thi, thời gian điều phối container và độ trễ của các dependency.

Các giá trị mặc định của `FixedBackOff` trong Spring Framework thường được biểu diễn bằng `DEFAULT_INTERVAL` và `DEFAULT_MAX_ATTEMPTS`. Khi muốn cấu hình rõ ràng cho ứng dụng, nên truyền cả hai tham số thay vì dựa vào giá trị mặc định.

## 3. Cấu hình FixedBackOff với DefaultErrorHandler

Trong Spring Kafka 2.8 trở lên, `DefaultErrorHandler` là common error handler cho listener container. Có thể tạo handler với một `FixedBackOff`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

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

Với Spring Boot, ứng dụng có thể đã có sẵn factory tự cấu hình. Trong trường hợp đó, hãy cấu hình đúng factory mà listener đang dùng hoặc cung cấp bean theo cơ chế auto-configuration của phiên bản Spring Boot/Spring Kafka đang chạy. Nếu có nhiều factory, đừng giả định handler được áp dụng tự động cho tất cả.

Ví dụ listener:

```java
@KafkaListener(topics = "orders")
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

Khi `orderService.handle()` ném exception, container chuyển lỗi đến `DefaultErrorHandler`. Handler sử dụng `FixedBackOff` để điều khiển các lần retry. Khi hết retry, recoverer được gọi theo cấu hình của handler.

## 4. Cấu hình recoverer sau khi hết retry

`FixedBackOff` chỉ quyết định khoảng chờ và số lần retry. Nó không tự quyết định phải làm gì với record sau khi retry hết. Việc đó thuộc về recoverer của `DefaultErrorHandler`.

Một recoverer có thể ghi log và chuyển record lỗi sang dead-letter topic (DLT). Ví dụ dùng `DeadLetterPublishingRecoverer`:

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

Với cấu hình mặc định của `DeadLetterPublishingRecoverer`, record thường được gửi đến topic có hậu tố `.DLT` và giữ số partition tương ứng. Cần tạo topic đích phù hợp, bảo đảm có đủ partition và cấu hình serializer/deserializer tương thích. Quy tắc định tuyến có thể tùy chỉnh khi khởi tạo recoverer.

Luồng xử lý:

```text
Record từ topic orders
        |
        v
Listener thất bại
        |
        v
FixedBackOff: retry tối đa 3 lần, chờ 1 giây
        |
        v
Hết retry
        |
        v
DeadLetterPublishingRecoverer
        |
        v
orders.DLT
```

Nếu recoverer cũng thất bại, record chưa được phục hồi thành công. `DefaultErrorHandler` có cơ chế xử lý lỗi recovery; cần hiểu cấu hình reset backoff khi recovery thất bại và bảo đảm DLT producer có thể gửi dữ liệu. Không nên coi việc hết retry đồng nghĩa record đã được xử lý an toàn.

## 5. Phân biệt retry và tổng số lần delivery

Khi thiết kế chính sách, hãy ghi rõ số lần retry và tổng số lần listener có thể nhận record. Bảng sau minh họa một số cấu hình:

| FixedBackOff | Lần xử lý ban đầu | Retry tối đa | Tổng lần gọi tối đa khi mọi lần đều lỗi |
|---|---:|---:|---:|
| `new FixedBackOff(500L, 0L)` | 1 | 0 | 1 |
| `new FixedBackOff(1_000L, 1L)` | 1 | 1 | 2 |
| `new FixedBackOff(1_000L, 3L)` | 1 | 3 | 4 |
| `new FixedBackOff(2_000L, 5L)` | 1 | 5 | 6 |

`maxAttempts=0` có nghĩa là không retry. Sau lần xử lý ban đầu thất bại, handler có thể gọi recoverer ngay. Cấu hình này hữu ích khi lỗi không thể khắc phục bằng retry hoặc khi muốn đưa record vào DLT ngay lập tức.

Đừng nhầm số lần retry với `max.poll.records`. `max.poll.records` giới hạn số record được trả về trong một lần poll; `FixedBackOff.maxAttempts` giới hạn số lần retry cho một lần xử lý record thất bại. Hai thuộc tính điều khiển hai khía cạnh khác nhau của consumer.

## 6. Chọn khoảng chờ và số lần retry

Khoảng chờ cần phù hợp với thời gian phục hồi của dependency và giới hạn thời gian xử lý của consumer. Ví dụ, nếu database thường hồi phục trong vài giây sau một đợt failover, retry cách nhau một giây có thể đủ. Nếu dịch vụ đích cần nhiều thời gian hơn để phục hồi, retry quá dày sẽ tạo thêm tải và log lỗi.

Có thể ước lượng thời gian chờ tối đa:

```text
T_backoff = interval × maxAttempts
```

Ví dụ:

```text
interval = 2.000 ms
maxAttempts = 4
T_backoff = 2.000 × 4 = 8.000 ms
```

Tổng thời gian record nằm trong chu kỳ xử lý còn bao gồm thời gian của mỗi lần listener chạy:

```text
T_total ≈ (initial + maxAttempts) × T_processing
          + maxAttempts × interval
          + T_overhead
```

Đây là ước lượng cho retry tuần tự và thời gian xử lý gần tương đương giữa các lần thử. Trong thực tế, thời gian mỗi lần thử có thể khác nhau đáng kể.

Nếu retry được thực hiện đồng bộ trên consumer thread, tổng thời gian retry cũng góp vào khoảng thời gian giữa hai lần `poll()`. Khi `T_total` tiến gần hoặc vượt `max.poll.interval.ms`, consumer có thể bị loại khỏi group và gây rebalance. Hãy phối hợp chính sách backoff với `max.poll.interval.ms`, kích thước batch và timeout của dependency.

## 7. FixedBackOff không phải exponential backoff

`FixedBackOff` luôn chờ cùng một khoảng thời gian giữa các lần retry. Ví dụ `new FixedBackOff(2_000L, 4L)` tạo bốn khoảng chờ, mỗi khoảng hai giây.

```text
Lần lỗi 1 --2s--> Retry 1
Retry 1   --2s--> Retry 2
Retry 2   --2s--> Retry 3
Retry 3   --2s--> Retry 4
```

Exponential backoff tăng khoảng chờ sau mỗi lần thất bại, ví dụ 1 giây, 2 giây, 4 giây, 8 giây. Cách này giảm tần suất gọi dependency khi sự cố kéo dài. Spring Kafka có các lựa chọn backoff khác, chẳng hạn `ExponentialBackOffWithMaxRetries`, có thể dùng với `DefaultErrorHandler` khi cần tăng dần khoảng chờ.

| Tiêu chí | Fixed backoff | Exponential backoff |
|---|---|---|
| Khoảng chờ | Không đổi giữa các lần retry. | Tăng dần theo hệ số. |
| Tính toán thời gian | Dễ dự đoán và đơn giản. | Cần tính tổng chuỗi khoảng chờ và giới hạn tối đa. |
| Tải lên dependency | Có thể tạo retry đều đặn khi sự cố kéo dài. | Giảm tần suất retry theo thời gian. |
| Phù hợp | Lỗi ngắn, thời gian phục hồi tương đối ổn định. | Dependency có thể cần thời gian phục hồi dài hoặc không xác định. |

Không nên chọn backoff chỉ vì một loại có vẻ phức tạp hơn. Hãy dựa trên đặc điểm lỗi, giới hạn latency và năng lực phục hồi của hệ thống đích.

## 8. Phân loại exception trước khi retry

Không phải mọi exception đều có thể khắc phục bằng cách chờ rồi thử lại. Ví dụ, lỗi kết nối database tạm thời có thể retry; lỗi dữ liệu không hợp lệ hoặc vi phạm quy tắc nghiệp vụ thường sẽ thất bại lặp lại nếu gửi cùng record thêm nhiều lần.

`DefaultErrorHandler` hỗ trợ phân loại exception. Có thể khai báo exception không retry:

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

Với các lỗi này, handler bỏ qua các lần retry và chuyển thẳng đến recoverer theo cấu hình. Có thể thêm exception retryable khi cần điều chỉnh phân loại mặc định. Cần xem toàn bộ cause chain và cách exception được wrap bởi framework; phân loại theo exception ngoài cùng có thể không phản ánh nguyên nhân gốc.

Một quy tắc thực tế:

- Lỗi tạm thời: cân nhắc retry có giới hạn, ví dụ timeout, lỗi kết nối hoặc dịch vụ tạm unavailable.
- Lỗi dữ liệu/validation: thường chuyển thẳng đến recoverer hoặc DLT để điều tra.
- Lỗi lập trình: sửa code; retry liên tục thường chỉ kéo dài thời gian phát hiện lỗi.
- Lỗi không xác định: dùng số lần retry nhỏ, log đủ context và có cơ chế phục hồi rõ ràng.

## 9. Retry có giới hạn và xử lý idempotent

Retry đồng nghĩa listener có thể được gọi nhiều lần cho cùng một record. Nếu listener thực hiện một thao tác không idempotent, retry có thể tạo hiệu ứng trùng. Ví dụ, nếu listener cộng thêm 100 điểm thưởng rồi lỗi trước khi commit offset, lần retry có thể cộng thêm 100 điểm lần nữa.

Hãy thiết kế nghiệp vụ có khả năng nhận cùng một event nhiều lần:

```java
@Transactional
public void applyReward(RewardRequested event) {
    if (processedEventRepository.existsByEventId(event.eventId())) {
        return;
    }

    accountRepository.addPoints(event.accountId(), event.points());
    processedEventRepository.save(event.eventId());
}
```

Ví dụ trên cần ràng buộc duy nhất cho `eventId` và thao tác lưu dấu vết phải nằm trong cùng transaction với thay đổi điểm thưởng. Kiểm tra `exists` đơn thuần mà không có ràng buộc duy nhất có thể gặp race condition khi có nhiều luồng xử lý. Với các hệ thống cần độ tin cậy cao, dùng unique constraint hoặc cơ chế inbox có tính nguyên tử.

Không dựa vào `FixedBackOff` để tạo exactly-once processing. Backoff chỉ quyết định khi nào thử lại; idempotency và cơ chế giao dịch mới bảo vệ hiệu ứng nghiệp vụ trước việc record được giao nhiều lần.

## 10. Ảnh hưởng đến offset và consumer group

Khi listener ném exception, `DefaultErrorHandler` quyết định retry hoặc phục hồi record. Với record listener, container có thể seek để đọc lại record và các record còn lại theo chiến lược xử lý lỗi. Offset chỉ được tiến lên theo chính sách acknowledgment/commit sau khi xử lý hoặc recovery được xem là hoàn tất.

Khi retry chưa hết, record lỗi vẫn cần được xử lý lại. Nếu ứng dụng dừng trong thời gian backoff hoặc group rebalance, record có thể được giao lại cho member khác. Vì thế, số lần thử thực tế trong toàn bộ vòng đời có thể chịu ảnh hưởng của restart và việc xử lý lại sau rebalance; `maxAttempts` không phải giới hạn toàn cục vĩnh viễn cho một event trong mọi lần chạy của ứng dụng.

Khi recoverer xử lý thành công record sau khi hết retry, handler có thể coi record đã được phục hồi và cho phép tiến độ consumer tiếp tục theo cấu hình. Nếu recoverer thất bại, record có thể được giao lại và quá trình recovery được thử lại theo hành vi/cấu hình của handler. Không commit offset trước khi việc phục hồi quan trọng đã hoàn tất.

Đối với batch listener, cách xác định record lỗi và phần batch cần retry có thể khác record listener. Nếu batch listener ném `BatchListenerFailedException` kèm chỉ số record lỗi, `DefaultErrorHandler` có thể xử lý phần record trước đó và retry từ record lỗi. Nếu không xác định được record lỗi, handler có thể áp dụng cơ chế retry toàn batch. Hãy chọn cách ném exception phù hợp với hợp đồng của batch listener.

## 11. Theo dõi retry và backoff

Để vận hành chính sách `FixedBackOff`, cần biết record nào đang retry, số lần thử, thời gian chờ và kết quả recovery. Có thể cấu hình `RetryListener` để nhận thông báo khi retry hoặc recovery:

```java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        log.warn("Kafka delivery failed: topic={}, partition={}, offset={}, attempt={}",
                record.topic(),
                record.partition(),
                record.offset(),
                deliveryAttempt,
                exception);
    }
});
```

Chữ ký callback có thể thay đổi giữa các phiên bản Spring Kafka; kiểm tra API phiên bản đang dùng khi triển khai. Có thể dùng các callback recovery tương ứng để ghi nhận record đã được phục hồi hoặc recovery thất bại.

Nên theo dõi:

- Số lần listener thất bại theo exception type.
- Số lần retry và phân bố delivery attempt.
- Tổng thời gian retry/backoff.
- Số record được recover hoặc gửi đến DLT.
- Số lần DLT publish thất bại.
- Consumer lag và thời gian xử lý listener.
- Rebalance hoặc poll timeout xuất hiện trong lúc retry.

Không log toàn bộ payload nếu chứa dữ liệu cá nhân hoặc bí mật. Topic, partition, offset, event ID và exception type thường đủ để nối sự kiện retry với log nghiệp vụ.

## 12. Các lỗi thường gặp khi dùng FixedBackOff

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Listener được gọi nhiều hơn dự kiến | `maxAttempts` là số retry sau lần ban đầu, không phải tổng số lần gọi. | Tính tổng số lần tối đa bằng `1 + maxAttempts`. |
| Record bị đưa vào DLT ngay | `maxAttempts=0`, exception được phân loại không retry hoặc handler không dùng backoff mong muốn. | Kiểm tra `FixedBackOff`, exception classification và factory. |
| Retry diễn ra quá nhanh | `interval` quá nhỏ hoặc bằng 0. | Tăng interval theo thời gian phục hồi thực tế và tránh retry dồn dập. |
| Consumer bị rebalance trong lúc retry | Tổng thời gian xử lý và backoff vượt `max.poll.interval.ms`. | Tính tổng thời gian retry, giảm số lần thử hoặc dùng chiến lược backoff phù hợp. |
| DLT không nhận record | Recoverer hoặc producer gửi DLT lỗi; topic đích/serializer không phù hợp. | Kiểm tra producer, quyền ghi, topic DLT và lỗi recovery. |
| Nghiệp vụ bị lặp sau retry | Listener không idempotent hoặc record được giao lại sau crash. | Dùng event ID, unique constraint hoặc inbox/outbox. |
| Exception dữ liệu bị retry liên tục | Chưa phân loại lỗi không thể retry. | Thêm `addNotRetryableExceptions` và chuyển lỗi sang recovery. |
| Batch bị xử lý lại nhiều lần | Handler không xác định được record lỗi trong batch. | Dùng `BatchListenerFailedException` khi phù hợp và hiểu chiến lược batch retry. |

## 13. Quy trình chọn FixedBackOff cho một listener

Khi thiết kế retry cho listener mới, có thể làm theo trình tự:

1. Liệt kê các exception có thể phát sinh và phân loại lỗi tạm thời, lỗi dữ liệu, lỗi lập trình.
2. Đo thời gian phục hồi thường gặp của dependency và chọn khoảng chờ cố định phù hợp.
3. Chọn số retry tối đa dựa trên latency nghiệp vụ và giới hạn poll interval.
4. Tính tổng số lần gọi listener bằng một lần ban đầu cộng số retry.
5. Chọn recoverer sau khi hết retry: log, DLT hoặc quy trình xử lý thủ công.
6. Bảo đảm recoverer có thể gửi dữ liệu bền vững và có giám sát lỗi riêng.
7. Thiết kế listener idempotent để chịu được retry, restart và rebalance.
8. Đo retry rate, recovery rate, lag và thời gian xử lý sau khi triển khai.

`FixedBackOff` cung cấp một chính sách retry đơn giản, dễ dự đoán cho `DefaultErrorHandler`. Khi cấu hình đúng số lần retry, khoảng chờ, phân loại exception và recoverer, consumer có thể xử lý các lỗi tạm thời có kiểm soát và đưa những record không thể xử lý sang quy trình phục hồi rõ ràng.
