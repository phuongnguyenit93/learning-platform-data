# BackOff trong error handler

## 1. BackOff giải quyết vấn đề gì?

Khi listener xử lý một Kafka record và ném exception, Spring Kafka có thể thử xử lý lại record đó. Nếu retry ngay lập tức và liên tục, ứng dụng sẽ tạo tải lớn lên database, API hoặc broker đang gặp sự cố. Nếu chờ quá lâu, consumer lag và độ trễ nghiệp vụ tăng.

**BackOff** định nghĩa khoảng thời gian chờ giữa các lần retry và thời điểm dừng retry. Nó giúp error handler điều tiết tốc độ thử lại, tạo thời gian cho hệ thống phụ thuộc phục hồi và giới hạn số lần xử lý một record trước khi chuyển sang bước recovery.

Trong Spring Kafka, `DefaultErrorHandler` sử dụng abstraction `BackOff` của Spring Framework. Error handler phối hợp ba phần:

- **Listener:** xử lý record và có thể ném exception.
- **BackOff:** quyết định chờ bao lâu trước lần thử tiếp theo và khi nào hết retry.
- **Recoverer:** thực hiện hành động khi không retry nữa, ví dụ publish record sang Dead Letter Topic (DLT), lưu quarantine hoặc ghi nhận lỗi bền vững.

```text
Kafka record
    |
    v
Listener xử lý
    |
    +---- thành công --------------------> container tiếp tục/commit theo cấu hình
    |
    +---- ném exception
              |
              v
       DefaultErrorHandler
              |
              v
          BackOff
          /     \
   còn retry    hết retry (STOP)
       |             |
       v             v
   chờ delay       Recoverer
       |             |
       v             +---- DLT / lưu lỗi / recovery
   gọi listener lại
```

BackOff chỉ điều khiển lịch chờ và giới hạn retry. Nó không tự sửa dữ liệu, không bảo đảm hệ thống phụ thuộc sẽ phục hồi và không tự tạo exactly-once.

## 2. BackOff và BackOffExecution

Spring Framework định nghĩa hai interface chính trong package `org.springframework.util.backoff`:

- `BackOff`: tạo một lần thực thi lịch retry mới thông qua `start()`.
- `BackOffExecution`: giữ trạng thái của lịch đó và trả về khoảng chờ tiếp theo qua `nextBackOff()`.

`nextBackOff()` trả về số mili giây cần chờ trước lần retry tiếp theo. Khi lịch retry đã kết thúc, nó trả `BackOffExecution.STOP` (giá trị sentinel `-1`). Error handler dùng tín hiệu này để ngừng retry và gọi recoverer.

Mỗi lần xử lý record thất bại có một tiến trình BackOff riêng. Không nên dùng một `BackOffExecution` chia sẻ thủ công giữa nhiều record vì trạng thái số lần retry sẽ bị trộn lẫn. Hãy truyền một `BackOff` có khả năng tạo execution mới cho từng lần xử lý.

Luồng cơ bản:

1. Listener xử lý record lần đầu.
2. Listener ném exception.
3. Error handler bắt đầu hoặc tiếp tục `BackOffExecution` của record.
4. Nếu `nextBackOff()` trả delay, error handler chờ rồi thử lại theo chính sách container.
5. Nếu `nextBackOff()` trả `STOP`, error handler gọi recoverer.
6. Nếu recovery thành công, container tiếp tục theo cơ chế commit/seek tương ứng; nếu recovery thất bại, lỗi recovery được xử lý theo cấu hình error handler.

## 3. FixedBackOff: khoảng chờ cố định

`FixedBackOff` là lựa chọn đơn giản nhất. Nó dùng một khoảng chờ giống nhau giữa các lần retry và một số lần retry tối đa.

```java
import org.springframework.util.backoff.FixedBackOff;

var backOff = new FixedBackOff(1_000L, 2L);
```

Hai tham số lần lượt là:

- `interval`: khoảng chờ giữa các lần retry, tính bằng mili giây.
- `maxAttempts`: số lần retry sau lần xử lý đầu tiên.

Với `new FixedBackOff(1_000L, 2L)`, listener được gọi tối đa ba lần nếu cả ba lần đều thất bại:

| Lần gọi | Kết quả | Hành động tiếp theo |
|---:|---|---|
| 1 | Lần xử lý ban đầu thất bại | Chờ 1 giây |
| 2 | Retry lần 1 thất bại | Chờ 1 giây |
| 3 | Retry lần 2 thất bại | BackOff kết thúc, gọi recoverer |

`maxAttempts` trong `FixedBackOff` là số lần retry, không phải tổng số lần listener được gọi. Đây là điểm thường bị nhầm khi đọc cấu hình.

### Ví dụ không retry

```java
var noRetry = new FixedBackOff(0L, 0L);
```

Lần xử lý đầu tiên thất bại sẽ đi thẳng đến recoverer. Cách này phù hợp với lỗi dữ liệu không thể khắc phục bằng việc thử lại, nhưng cần chắc chắn recoverer có hành động bảo toàn record.

### Ví dụ retry nhiều lần với khoảng chờ ngắn

```java
var shortRetry = new FixedBackOff(250L, 4L);
```

Listener có tối đa năm lần được gọi: lần đầu và bốn lần retry, với khoảng chờ 250 ms giữa các lần retry. Đây có thể là lựa chọn cho lỗi hạ tầng ngắn hạn, nhưng không phù hợp với sự cố kéo dài nhiều phút.

Không nên dùng số lần retry rất lớn cùng interval bằng 0 cho lỗi không có khả năng tự phục hồi. Cách đó có thể tạo vòng lặp nóng, tiêu thụ CPU và làm consumer group bị nghẽn.

## 4. Cấu hình FixedBackOff với DefaultErrorHandler

Ví dụ dưới đây cấu hình hai lần retry, mỗi lần cách nhau một giây, sau đó publish record lỗi sang DLT:

```java
@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        ConsumerRecordRecoverer recoverer =
                new DeadLetterPublishingRecoverer(dltTemplate);

        BackOff backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }
}
```

Gắn error handler vào listener container factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
```

Listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Khi `orderService.process()` ném exception, `DefaultErrorHandler` áp dụng BackOff. Nếu retry hết, `DeadLetterPublishingRecoverer` chuyển record đến DLT theo destination resolver mặc định hoặc resolver do ứng dụng cấu hình.

Trong ứng dụng thực tế, template DLT phải serialize được key/value và headers của record lỗi. Nếu consumer dùng `ErrorHandlingDeserializer` và record có raw `byte[]`, cần cấu hình serializer DLT hỗ trợ cả byte array và payload bình thường.

## 5. Exponential BackOff: tăng dần thời gian chờ

Với lỗi phụ thuộc có thể cần nhiều thời gian để phục hồi, khoảng chờ cố định có thể tạo nhiều request retry dồn dập. Exponential backoff tăng dần thời gian chờ sau mỗi lần thất bại.

Ví dụ lịch chờ với initial interval 500 ms, multiplier 2 và max interval 5 giây:

| Lần retry | Thời gian chờ dự kiến |
|---:|---:|
| 1 | 500 ms |
| 2 | 1.000 ms |
| 3 | 2.000 ms |
| 4 | 4.000 ms |
| 5 trở đi | 5.000 ms (đã chạm max interval) |

Có thể cấu hình `ExponentialBackOff` của Spring Framework:

```java
import org.springframework.util.backoff.ExponentialBackOff;

ExponentialBackOff backOff = new ExponentialBackOff();
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(5_000L);
backOff.setMaxElapsedTime(20_000L);
```

`maxInterval` giới hạn thời gian chờ của một lần retry. `maxElapsedTime` giới hạn tổng thời gian thực thi lịch BackOff; khi đạt giới hạn, execution có thể trả `STOP` dù số lần retry chưa đạt một con số cố định.

Khác với `FixedBackOff`, số lần retry của exponential backoff có thể được quyết định bởi tổng thời gian đã trôi qua và các tham số interval. Hãy kiểm thử lịch thực tế nếu cần giới hạn số lần gọi chính xác.

Không nhầm `org.springframework.util.backoff.BackOff` với `BackOffPolicy` của Spring Retry. Đây là hai abstraction khác nhau. `DefaultErrorHandler` của Spring Kafka nhận `BackOff` thuộc Spring Framework.

## 6. Chọn BackOff theo loại lỗi

Không phải lỗi nào cũng nên retry giống nhau. Một chính sách thường chia lỗi thành ba nhóm:

| Nhóm lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Lỗi tạm thời | Timeout database, lỗi mạng ngắn hạn, dịch vụ phụ thuộc tạm unavailable | Retry có giới hạn với fixed hoặc exponential backoff |
| Lỗi dữ liệu không thể tự sửa | JSON sai cú pháp, payload thiếu trường bắt buộc, type header không hợp lệ | Không retry hoặc retry rất ít; chuyển DLT/quarantine để điều tra |
| Lỗi nghiệp vụ cần can thiệp | Trạng thái đơn hàng không cho phép chuyển bước, tài khoản bị khóa | Phân loại theo nghiệp vụ; có thể DLT, chờ sự kiện khác hoặc xử lý thủ công |

Nếu retry lỗi dữ liệu không thể tự sửa, consumer chỉ đọc lại cùng byte và nhận cùng exception. Việc chờ lâu hơn không làm record trở nên hợp lệ.

### Phân loại exception trong DefaultErrorHandler

`DefaultErrorHandler` có thể phân loại exception retryable và non-retryable. Ví dụ:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        new DeadLetterPublishingRecoverer(dltTemplate),
        new FixedBackOff(1_000L, 3L));

handler.addNotRetryableExceptions(
        InvalidOrderPayloadException.class,
        UnsupportedEventVersionException.class);

handler.addRetryableExceptions(
        TemporaryInventoryUnavailableException.class);
```

Các exception non-retryable sẽ bỏ qua lịch retry và đi đến recovery ngay. Các exception retryable dùng BackOff đã cấu hình. Cần kiểm tra exception thực tế mà listener hoặc deserializer ném ra; exception có thể được bọc trong một exception khác.

Spring Kafka cũng có danh sách phân loại mặc định. Hãy đọc tài liệu đúng phiên bản và chỉ bổ sung các phân loại cần thiết, tránh vô tình biến lỗi dữ liệu thành retryable hoặc lỗi hạ tầng thành non-retryable.

## 7. BackOff tùy chỉnh

Khi cần lịch chờ đặc thù, có thể triển khai `BackOff` và `BackOffExecution`. Ví dụ dưới đây tạo lịch chờ 500 ms, sau đó 2 giây, rồi dừng:

```java
BackOff customBackOff = () -> new BackOffExecution() {
    private int attempt;

    @Override
    public long nextBackOff() {
        return switch (attempt++) {
            case 0 -> 500L;
            case 1 -> 2_000L;
            default -> BackOffExecution.STOP;
        };
    }
};

DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, customBackOff);
```

Lịch này cho phép hai lần retry sau lần xử lý ban đầu. Mỗi lần gọi `start()` tạo một execution mới với bộ đếm riêng. Đây là điều quan trọng khi nhiều partition có record lỗi đồng thời.

Custom BackOff hữu ích khi:

- Khoảng chờ cần theo từng loại exception.
- Muốn giới hạn theo tổng thời gian thay vì số lần retry.
- Cần một chuỗi delay không đều theo SLA của hệ thống phụ thuộc.
- Muốn tích hợp lịch retry được tính từ cấu hình nghiệp vụ.

Giữ logic BackOff thuần và dễ kiểm thử. Không gọi database, HTTP hoặc Kafka broker bên trong `nextBackOff()`; phương thức này được gọi trong luồng điều khiển retry và nên trả về nhanh, ổn định.

## 8. BackOff handler: chờ bằng cách nào?

BackOff quyết định **chờ bao lâu**; `BackOffHandler` quyết định **thực hiện thời gian chờ đó bằng cách nào**.

Trong `DefaultErrorHandler`, cách mặc định là chờ trên consumer thread. Với delay ngắn, cách này đơn giản. Tuy nhiên, nếu delay dài, consumer thread có thể không gọi `poll()` trong thời gian chờ và vượt `max.poll.interval.ms`, khiến member bị loại khỏi group và gây rebalance.

Spring Kafka cung cấp `ContainerPausingBackOffHandler` để tạm dừng listener container trong thời gian backoff thay vì chỉ sleep trên consumer thread. Container vẫn có thể thực hiện các poll cần thiết để giữ group membership; độ chính xác thời gian chờ phụ thuộc `pollTimeout` và lịch chạy của container.

Ví dụ:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(60_000L, 2L),
        new ContainerPausingBackOffHandler());
```

Ví dụ này yêu cầu delay một phút giữa các lần retry và dùng container pausing handler. Với backoff dài, đây thường là lựa chọn phù hợp hơn sleep consumer thread. Cần kiểm tra hành vi với phiên bản Spring Kafka và cấu hình container cụ thể.

### Khi nào dùng từng cách?

| Cách chờ | Phù hợp | Điểm cần lưu ý |
|---|---|---|
| Default sleep-based handler | Delay ngắn, xử lý nhanh, không có nguy cơ chạm `max.poll.interval.ms` | Consumer thread bị chặn trong lúc chờ |
| `ContainerPausingBackOffHandler` | Delay dài, cần giữ container/group hoạt động trong thời gian chờ | Delay thực tế có thể lệch theo poll timeout; container bị pause nên partition không xử lý record mới trong thời gian đó |

Không chọn container pausing với kỳ vọng consumer vẫn xử lý các record tiếp theo của cùng partition. Mục tiêu là duy trì vòng đời container/group trong lúc chờ retry; partition đang bị pause không tiếp tục xử lý luồng chính như bình thường.

## 9. BackOff và max.poll.interval.ms

Kafka consumer cần gọi `poll()` thường xuyên theo giới hạn `max.poll.interval.ms`. Nếu thời gian xử lý một batch cộng với thời gian retry/backoff vượt giới hạn này, consumer có thể bị xem là không còn tiến triển và rời group.

Ví dụ:

- `max.poll.interval.ms = 300000` (5 phút).
- Listener xử lý batch mất 90 giây.
- BackOff chờ 4 phút trước lần retry.
- Tổng thời gian không poll có thể vượt 5 phút.

Khi đó có thể xảy ra rebalance. Partition được giao cho consumer khác và record chưa commit có thể được giao lại. Vì vậy, khi thiết kế backoff cần tính cả thời gian xử lý listener, batch size, retry count và khoảng chờ.

Các hướng xử lý:

1. Giảm thời gian xử lý một record/batch bằng cách tối ưu nghiệp vụ.
2. Giảm `max.poll.records` nếu một poll batch quá lớn, đồng thời đánh giá throughput.
3. Chọn backoff ngắn hơn nếu SLA và loại lỗi cho phép.
4. Dùng `ContainerPausingBackOffHandler` cho delay dài.
5. Xem xét retry topic/non-blocking retry nếu không muốn giữ partition chính chờ lâu và nghiệp vụ chấp nhận thay đổi ordering.

Không chỉ tăng `max.poll.interval.ms` để che giấu retry quá dài. Hãy cân nhắc thời gian failover, rebalance, xử lý trùng và độ trễ tối đa mà nghiệp vụ chấp nhận.

## 10. Blocking retry và non-blocking retry

BackOff trong `DefaultErrorHandler` thường được dùng cho blocking retry: record lỗi được thử lại trong luồng xử lý của partition. Trong thời gian chờ và retry, các record tiếp theo của partition đó không vượt qua record lỗi theo luồng xử lý thông thường.

`@RetryableTopic` là cơ chế khác: Spring Kafka chuyển record lỗi sang retry topic với thời gian chờ tương ứng, rồi consumer của retry topic thử xử lý sau. Consumer topic chính có thể tiếp tục record tiếp theo.

| Tiêu chí | Blocking retry với DefaultErrorHandler | Non-blocking retry topic |
|---|---|---|
| Nơi chờ | Luồng consumer/container đang xử lý record lỗi | Retry topic và lịch chuyển tiếp |
| Record sau trong partition chính | Thường bị chặn sau record lỗi | Có thể tiếp tục trước record đang retry |
| Ordering | Dễ giữ thứ tự theo partition hơn | Có thể làm sự kiện sau hoàn tất trước sự kiện lỗi |
| Phù hợp | Cần ordering hoặc lỗi chỉ cần chờ ngắn | Cần luồng chính tiếp tục và chấp nhận retry bất đồng bộ |
| BackOff | `BackOff`/`BackOffHandler` của error handler | Cấu hình backoff của retry topic, ví dụ qua `@RetryableTopic` |

Không nên cấu hình hai cơ chế như thể chúng là một lịch retry duy nhất. Hãy xác định retry nào diễn ra trong listener container và retry nào được chuyển sang topic riêng. Đặc biệt, nếu cùng aggregate/key cần xử lý đúng thứ tự, non-blocking retry có thể làm đảo thứ tự nghiệp vụ.

## 11. BackOff với batch listener

Với batch listener, error handler cần xác định phạm vi record bị lỗi. Nếu listener ném `BatchListenerFailedException` và chỉ rõ record/index, `DefaultErrorHandler` có thể retry từ record lỗi theo chính sách phù hợp, thay vì luôn xử lý lại toàn bộ batch.

Nếu batch listener ném exception chung mà không xác định được record lỗi, error handler có thể phải retry cả batch. Khi đó BackOff áp dụng cho lần xử lý lại theo phạm vi batch.

Ví dụ:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchListenerFactory")
public void onOrders(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int index = 0; index < records.size(); index++) {
        try {
            orderService.process(records.get(index).value());
        } catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Cannot process order record", exception, index);
        }
    }
}
```

Với cách này, error handler biết index record lỗi. Cần kiểm tra hành vi offset, retry và recovery với batch có nhiều partition, vì offset vẫn độc lập theo từng partition. Nếu listener thực hiện bulk database operation không thể xác định record lỗi, hãy thiết kế transaction hoặc bước validate để có thể cô lập lỗi.

## 12. BackOff trong transactional listener

Khi listener container dùng Kafka transaction, exception từ listener thường làm transaction rollback. Trong mô hình này, luồng retry sau rollback thường do `AfterRollbackProcessor` (mặc định là `DefaultAfterRollbackProcessor`) quản lý, không nên áp dụng nguyên xi cấu hình `DefaultErrorHandler` của non-transactional listener.

`DefaultAfterRollbackProcessor` cũng hỗ trợ `BackOff` và recoverer để quyết định số lần xử lý lại sau rollback và hành động khi retry hết. Vì vậy, có thể dùng cùng khái niệm `FixedBackOff` hoặc exponential backoff nhưng cần cấu hình tại thành phần xử lý sau rollback.

Các điểm cần phân biệt:

- Với non-transactional listener, `DefaultErrorHandler` điều khiển retry/recovery.
- Với transactional listener, exception làm rollback transaction; `AfterRollbackProcessor` điều khiển việc seek/retry/recover sau rollback.
- BackOff không làm side effect bên ngoài Kafka trở thành transactional.
- Nếu database đã commit trước khi Kafka transaction rollback, record có thể được xử lý lại; cần idempotency hoặc thiết kế phối hợp transaction phù hợp.

Không được suy luận rằng Kafka transaction cộng BackOff tự động tạo exactly-once cho database, HTTP hoặc email.

## 13. Recovery sau khi BackOff kết thúc

Khi BackOff trả `STOP`, error handler gọi recoverer. Recoverer có thể:

- Publish record sang DLT bằng `DeadLetterPublishingRecoverer`.
- Lưu payload và metadata vào bảng quarantine.
- Gửi thông báo vận hành hoặc tạo ticket qua một cơ chế khác.
- Đánh dấu record không thể xử lý và cho phép group tiếp tục.

Recovery phải có ý nghĩa bền vững. Nếu recoverer chỉ log lỗi rồi trả về, container có thể xem record đã được phục hồi và tiến độ tiếp tục; nếu log không đủ để khôi phục dữ liệu, record có thể bị mất khỏi luồng xử lý nghiệp vụ.

Ví dụ DLT:

```java
ConsumerRecordRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltTemplate);

DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(2_000L, 3L));
```

Với cấu hình này, listener có tối đa bốn lần được gọi: lần đầu và ba lần retry. Sau lần thất bại cuối cùng, recoverer publish record sang DLT. Cần kiểm tra publish result và cấu hình serializer, topic, partition mapping và ACL để recovery không thất bại.

Nếu recoverer ném exception, việc phục hồi chưa hoàn tất. `DefaultErrorHandler` có chính sách reset BackOff khi recovery thất bại; hành vi cụ thể có thể cấu hình và cần kiểm tra theo phiên bản. Không nên giả định record đã được xử lý chỉ vì recoverer đã được gọi.

## 14. Theo dõi hiệu quả của BackOff

BackOff cần được đánh giá bằng số liệu vận hành, không chỉ bằng cấu hình trong code. Nên theo dõi:

- Số lần listener thất bại và số lần retry theo exception class.
- Thời gian chờ thực tế giữa các lần retry.
- Số record đã hết retry và được recover.
- DLT publish success/failure rate.
- Consumer lag theo partition và thời gian record nằm trong retry.
- Số lần rebalance trong thời gian retry kéo dài.
- Thời gian xử lý record p95/p99 và thời gian phục hồi dịch vụ phụ thuộc.

Log nên có `eventId`, topic, partition, offset, exception class, retry attempt và recovery destination. Không log toàn bộ payload nhạy cảm chỉ để quan sát retry.

Nếu retry rate tăng đột biến, hãy kiểm tra dependency health và loại exception. Tăng số lần retry hoặc giảm delay một cách tự động có thể làm hệ thống phụ thuộc quá tải nặng hơn.

## 15. Kiểm thử BackOff

Kiểm thử cần xác nhận số lần gọi listener, thời gian chờ, recovery và hành vi sau restart:

1. **FixedBackOff:** cấu hình 2 retries và xác nhận listener được gọi tối đa 3 lần trước recoverer.
2. **No retry:** cấu hình `FixedBackOff(0, 0)` và xác nhận recoverer được gọi sau lần xử lý đầu thất bại.
3. **ExponentialBackOff:** xác nhận chuỗi delay tăng theo initial interval, multiplier và max interval.
4. **Exception classification:** xác nhận non-retryable exception đi thẳng recovery, retryable exception dùng BackOff.
5. **Recoverer thành công:** xác nhận record được chuyển DLT hoặc lưu quarantine và consumer tiếp tục theo chính sách.
6. **Recoverer thất bại:** xác nhận record chưa bị xem là phục hồi thành công và BackOff/error handler hành xử đúng cấu hình.
7. **Long backoff:** so sánh sleep-based handler và `ContainerPausingBackOffHandler`; theo dõi `max.poll.interval.ms` và rebalance.
8. **Batch listener:** xác nhận `BatchListenerFailedException` chỉ rõ record lỗi và phạm vi retry đúng.
9. **Transactional listener:** xác nhận rollback và `AfterRollbackProcessor` dùng BackOff như mong muốn.
10. **Redelivery/idempotency:** dừng ứng dụng trong quá trình retry và xác nhận side effect không bị nhân đôi ngoài dự kiến.

Có thể dùng `spring-kafka-test` hoặc Kafka test starter tương ứng với Spring Boot. Với kiểm thử thời gian chờ, nên dùng BackOff ngắn và có kiểm soát; tránh test suite phụ thuộc vào delay dài không cần thiết. Các kịch bản rebalance và broker failure cần integration test gần với môi trường chạy thật.

## 16. Lỗi thường gặp khi cấu hình BackOff

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Listener được gọi nhiều hơn dự kiến | Nhầm `maxAttempts` là tổng số lần gọi thay vì số lần retry | Cộng thêm lần xử lý ban đầu khi tính tổng |
| Retry diễn ra liên tục | Interval bằng 0 hoặc quá ngắn | Đặt delay phù hợp, dùng exponential backoff và giới hạn retry |
| Consumer rebalance khi retry lâu | Consumer thread không poll trong thời gian backoff và vượt `max.poll.interval.ms` | Dùng `ContainerPausingBackOffHandler`, giảm thời gian xử lý hoặc điều chỉnh poll strategy |
| Record lỗi dữ liệu bị retry mãi | Chưa phân loại exception non-retryable hoặc retry policy không có giới hạn | Phân loại lỗi và cấu hình recoverer/DLT |
| DLT không có record | Recoverer/template/topic/serializer/ACL sai hoặc publish thất bại | Kiểm tra kết quả publish, serializer và destination |
| Record sau bị chậm dù không liên quan | Blocking retry giữ partition tại record lỗi | Xem xét retry topic nếu nghiệp vụ chấp nhận thay đổi ordering |
| Batch bị retry toàn bộ | Listener không chỉ rõ record lỗi | Ném `BatchListenerFailedException` với index/record phù hợp |
| Transaction rollback nhưng không thấy DefaultErrorHandler retry | Transactional container dùng AfterRollbackProcessor | Cấu hình BackOff tại `DefaultAfterRollbackProcessor` |
| Tăng retry làm hệ thống tệ hơn | Dependency đang quá tải và retry tạo thêm tải | Giảm retry pressure, dùng backoff dài hơn, giới hạn concurrency và khôi phục dependency |

## 17. Quy trình chọn BackOff

1. Xác định loại exception và khả năng tự phục hồi của nó.
2. Chọn retryable hay non-retryable cho từng nhóm exception.
3. Đặt giới hạn số lần retry hoặc tổng thời gian retry theo SLA.
4. Chọn fixed backoff cho lỗi ngắn, dễ dự đoán; exponential backoff cho sự cố cần thời gian phục hồi dài hơn.
5. Với delay dài, chọn `ContainerPausingBackOffHandler` và đánh giá `max.poll.interval.ms`.
6. Xác định recoverer sau khi BackOff kết thúc: DLT, quarantine hoặc xử lý thủ công.
7. Nếu dùng batch listener, xác định record lỗi; nếu dùng transaction, cấu hình `AfterRollbackProcessor`.
8. Kiểm thử retry count, delay, recovery failure, rebalance và idempotency.
9. Theo dõi retry rate, lag, recovery và sức khỏe dependency sau triển khai.

Không chọn số lần retry theo cảm tính. Hãy dựa trên thời gian phục hồi thực tế của hệ thống phụ thuộc, thời gian record được phép nằm trong luồng, retention và khả năng xử lý backlog sau khi dịch vụ phục hồi.

## 18. Tổng kết

- BackOff quyết định khoảng chờ giữa retry và thời điểm dừng; recoverer quyết định xử lý gì sau khi retry hết.
- `BackOff` tạo `BackOffExecution`; `nextBackOff()` trả delay hoặc `STOP`.
- `FixedBackOff(interval, maxAttempts)` dùng interval cố định; `maxAttempts` là số lần retry sau lần xử lý ban đầu.
- `ExponentialBackOff` tăng dần delay và có thể giới hạn max interval/tổng elapsed time.
- `DefaultErrorHandler` kết hợp BackOff với retry/recovery cho non-transactional listener.
- `BackOffHandler` quyết định cách chờ; `ContainerPausingBackOffHandler` hữu ích với delay dài để tránh chặn consumer thread quá lâu.
- Blocking retry giữ record lỗi trong luồng partition; retry topic có thể cho record sau vượt lên trước.
- Batch listener cần chỉ rõ record lỗi khi có thể; transactional listener thường dùng `AfterRollbackProcessor`.
- Recovery cần bền vững; retry và BackOff không thay thế idempotency hay exactly-once.

Khi chọn đúng BackOff theo loại lỗi và SLA, Spring Kafka có thể retry có kiểm soát, tránh tạo tải dồn lên dependency, đồng thời chuyển record không thể phục hồi sang quy trình xử lý riêng để consumer group tiếp tục hoạt động.

## Tài liệu tham khảo

- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka API — DefaultErrorHandler](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DefaultErrorHandler.html)
- [Spring Framework API — BackOff](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/backoff/BackOff.html)
- [Spring Framework API — ExponentialBackOff](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/backoff/ExponentialBackOff.html)
