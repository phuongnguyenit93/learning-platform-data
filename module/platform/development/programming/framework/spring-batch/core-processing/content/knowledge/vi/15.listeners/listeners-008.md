# RetryListener

Trong Spring Batch, `RetryListener` là hook cho phép ứng dụng quan sát vòng đời của một thao tác được thực hiện theo cơ chế retry. Listener có thể ghi log mỗi lần thử thất bại, thu thập metric, lưu thông tin chẩn đoán hoặc thực hiện một số xử lý bổ trợ khi retry bắt đầu và kết thúc.

`RetryListener` thuộc cơ chế retry của Spring Retry, được Spring Batch sử dụng trong các chunk Step có cấu hình fault tolerance. Listener giúp quan sát quá trình retry, còn `RetryPolicy` và cấu hình của Step mới quyết định exception nào được retry và số lần thử tối đa. Vì vậy, listener không thay thế `.retry(...)`, `.retryLimit(...)` hay chính sách skip.

## 1. RetryListener nằm ở đâu trong Spring Batch?

Trong chunk-oriented Step, reader, processor hoặc writer có thể ném exception. Nếu exception thuộc loại được cấu hình retry, Spring Batch sử dụng cơ chế retry để thử lại thao tác theo policy đã khai báo.

```text
Chunk Step
   |
   v
Reader / Processor / Writer
   |
   +-- Thành công ----------------------> Tiếp tục chunk
   |
   +-- Ném exception
          |
          v
      RetryPolicy
          |
          +-- Còn lượt thử? ------------> Thử lại callback
          |                                  |
          |                                  v
          |                             RetryListener
          |
          +-- Hết lượt thử / không retry
                    |
                    v
             Skip policy hoặc Step failure
```

`RetryListener` nhận các callback trong vòng đời một lần thực thi retry. Nó thường được dùng để quan sát:

- Khi một retry operation bắt đầu.
- Khi một lần thử kết thúc bằng exception.
- Khi retry operation kết thúc thành công hoặc thất bại.

Listener không tự quyết định exception có được retry hay không. Quyết định đó thuộc retry policy của Spring Retry và cấu hình fault-tolerant Step.

## 2. RetryListener thuộc Spring Retry

Interface `RetryListener` nằm trong package `org.springframework.retry`. Hợp đồng cơ bản gồm ba callback:

```java
public interface RetryListener {

    <T, E extends Throwable> boolean open(
            RetryContext context,
            RetryCallback<T, E> callback);

    <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable);

    <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable);
}
```

Các phiên bản Spring Retry mới có thể bổ sung callback mặc định khác, tùy phiên bản thư viện. Ba callback trên là những điểm chính cần hiểu khi tích hợp listener với Spring Batch.

### open

`open` được gọi khi retry operation bắt đầu, trước khi các lần thử được thực hiện. Nó nhận `RetryContext` và `RetryCallback`.

Phương thức trả về boolean:

- `true`: cho phép retry operation bắt đầu.
- `false`: yêu cầu Spring Retry chấm dứt retry operation trước khi thực hiện callback, theo cơ chế kết thúc retry của framework.

Thông thường listener trả về `true`. Chỉ trả về `false` khi có một lý do rõ ràng để ngăn operation bắt đầu; không nên dùng callback này để thay thế validation đầu vào hoặc logic nghiệp vụ.

### onError

`onError` được gọi khi một lần thực thi callback kết thúc bằng exception. Nếu policy cho phép thử lại, callback có thể được chạy tiếp lần nữa.

Đây là nơi phù hợp để:

- Ghi nhận loại exception và retry count.
- Tăng metric số lần thử thất bại.
- Ghi log thông tin tương quan như JobExecution ID hoặc business key đã được cho phép.
- Theo dõi những lỗi tạm thời thường xuyên xảy ra.

Không nên xem mọi lần `onError` là lỗi cuối cùng của item. Một exception có thể chỉ là lỗi tạm thời ở một lần thử và lần retry sau có thể thành công.

### close

`close` được gọi khi retry operation kết thúc. Tham số `throwable` cho biết lỗi cuối cùng nếu operation kết thúc thất bại; khi thành công, thông thường không có throwable cuối cùng.

Callback này phù hợp để:

- Ghi nhận kết quả cuối cùng của retry operation.
- Hoàn tất metric hoặc trace đã mở ở `open`.
- Ghi log retry thành công sau một hoặc nhiều lần thất bại.
- Ghi nhận retry exhaustion nếu operation không thành công sau giới hạn.

Không nên đặt logic ghi dữ liệu nghiệp vụ quan trọng vào `close`. Listener là điểm quan sát và hỗ trợ vận hành; nó không thay thế writer hoặc transaction của chunk.

## 3. RetryContext lưu thông tin gì?

`RetryContext` là ngữ cảnh của retry operation. Nó giúp listener biết operation đã thử bao nhiêu lần và exception gần nhất là gì.

Một số thông tin thường được dùng:

| API | Ý nghĩa |
|---|---|
| `getRetryCount()` | Số lần retry được ghi nhận trong context hiện tại. |
| `getLastThrowable()` | Exception gần nhất được ghi nhận. |
| `getAttribute(key)` | Đọc thuộc tính gắn với context. |
| `setAttribute(key, value)` | Lưu thuộc tính trong context. |
| `removeAttribute(key)` | Xóa thuộc tính khỏi context. |

`RetryContext` có vòng đời gắn với retry operation. Nó hữu ích để chia sẻ dữ liệu giữa các callback của cùng operation, ví dụ thời điểm bắt đầu, mã tương quan hoặc một cờ đánh dấu đã có lỗi.

Không nên nhầm `RetryContext` với `ExecutionContext`:

| Đối tượng | Mục đích |
|---|---|
| `RetryContext` | Trạng thái tạm thời của một retry operation trong process đang chạy. |
| `ExecutionContext` | Trạng thái Job/Step được lưu bền vững trong JobRepository để hỗ trợ chia sẻ và restart. |

`RetryContext` không phải checkpoint bền vững. Không dùng nó để thay thế reader checkpoint hoặc lưu tiến độ cần khôi phục sau khi process dừng.

## 4. Cài đặt RetryListener

Có thể triển khai `RetryListener` để ghi log khi một operation bắt đầu, thất bại ở một lần thử và kết thúc.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;

public class BatchRetryListener implements RetryListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchRetryListener.class);

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context,
            RetryCallback<T, E> callback) {

        log.debug("Retry operation started");
        return true;
    }

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        log.warn("Retry attempt {} failed: {}",
                context.getRetryCount(),
                throwable.getClass().getSimpleName());
    }

    @Override
    public <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        if (throwable == null) {
            log.debug("Retry operation completed successfully");
        } else {
            log.error("Retry operation exhausted or terminated", throwable);
        }
    }
}
```

Ví dụ này chỉ ghi log, không thay đổi chính sách retry. `getRetryCount()` cung cấp số lần thử được ghi nhận trong context; cách hiển thị số thứ tự attempt nên dựa trên ngữ nghĩa của phiên bản Spring Retry đang dùng, tránh tự giả định rằng mọi lần gọi callback bắt đầu từ cùng một giá trị.

Trong ứng dụng thực tế, nên bổ sung JobExecution ID, StepExecution ID hoặc business key nếu có thể lấy chúng một cách an toàn. Tránh ghi toàn bộ item hoặc dữ liệu nhạy cảm vào log.

## 5. Đăng ký RetryListener vào fault-tolerant Step

Với Spring Batch 5, `RetryListener` có thể được đăng ký trên `FaultTolerantStepBuilder` cùng cấu hình retry:

```java
@Bean
RetryListener batchRetryListener() {
    return new BatchRetryListener();
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        RetryListener batchRetryListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .listener(batchRetryListener)
            .build();
}
```

Trong ví dụ:

- `.faultTolerant()` bật cấu hình fault tolerance cho chunk Step.
- `.retry(TransientDataAccessException.class)` chỉ định loại lỗi có thể được retry.
- `.retryLimit(3)` đặt giới hạn retry theo cấu hình của Spring Batch.
- `.listener(batchRetryListener)` đăng ký callback quan sát vòng đời retry.

`RetryListener` không làm cho một exception bất kỳ tự động được retry. Nếu exception không được policy cho phép, listener không thể biến nó thành lỗi retryable chỉ bằng cách ghi log trong `onError`.

## 6. RetryListener khác RetryPolicy như thế nào?

Hai thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `RetryPolicy` | Quyết định có retry exception hiện tại hay đã hết giới hạn. |
| `RetryListener` | Quan sát vòng đời retry và nhận thông tin về các lần thử. |
| `BackOffPolicy` | Điều khiển khoảng chờ giữa các lần thử lại. |
| `SkipPolicy` | Quyết định có thể bỏ qua item lỗi sau khi xảy ra exception hay không. |
| `SkipListener` | Nhận callback khi một item thực sự được skip. |

Ví dụ, Step cấu hình retry cho `TransientDataAccessException`. Khi writer gặp exception này, retry policy xác định có được thử lại hay không. RetryListener ghi nhận lần thử thất bại. Nếu đã hết lượt retry, Step có thể thất bại hoặc xử lý theo skip policy nếu exception cũng được phép skip và flow fault tolerance tương ứng.

Không nên đặt quyết định nghiệp vụ “bỏ qua bản ghi này” trong `RetryListener`. Hãy dùng processor trả `null` cho filter, skip policy cho exception được phép bỏ qua và retry policy cho lỗi có khả năng phục hồi.

## 7. Phân biệt RetryListener với các listener khác

Spring Batch có nhiều loại listener được gọi ở các giai đoạn khác nhau. Chọn đúng listener giúp code dễ hiểu và tránh đặt logic vào callback không phù hợp.

| Listener | Khi nào được gọi | Mục đích chính |
|---|---|---|
| `RetryListener` | Trong vòng đời retry operation | Quan sát retry attempt và kết quả cuối. |
| `SkipListener` | Khi item bị skip do exception | Ghi nhận item và lý do bị bỏ qua. |
| `StepExecutionListener` | Trước/sau một Step | Audit trạng thái và exit status của Step. |
| `ChunkListener` | Trước/sau một chunk | Quan sát ranh giới chunk. |
| `ItemReadListener` | Trước/sau khi đọc hoặc khi đọc lỗi | Quan sát reader. |
| `ItemProcessListener` | Trước/sau khi xử lý hoặc khi processor lỗi | Quan sát processor. |
| `ItemWriteListener` | Trước/sau khi ghi hoặc khi writer lỗi | Quan sát writer. |

Ví dụ, nếu cần biết một đơn hàng cuối cùng đã bị skip sau khi hết retry, `SkipListener` là nơi phù hợp để ghi nhận item. `RetryListener` chỉ cho biết operation đã có các lần thử lỗi và kết thúc ra sao.

## 8. RetryListener và retry ở reader, processor, writer

Trong fault-tolerant chunk Step, lỗi có thể xảy ra ở nhiều thành phần. Retry listener được gắn với cơ chế retry của Step và có thể quan sát retry operation được framework thực hiện.

### Reader

Reader có thể gặp lỗi tạm thời khi truy cập nguồn dữ liệu, chẳng hạn timeout kết nối. Nếu exception được cấu hình retry, listener có thể ghi nhận các lần thử. Với reader đọc file hoặc nguồn không transactional, cần hiểu cơ chế buffering và khôi phục vị trí đọc khi rollback.

### Processor

Processor có thể gọi dịch vụ tham chiếu hoặc thực hiện tính toán phụ thuộc hệ thống ngoài. Nếu gặp lỗi tạm thời, retry có thể phù hợp. Tuy nhiên, processor nên tránh tác dụng phụ không idempotent vì nó có thể được gọi lại.

### Writer

Writer có thể gặp deadlock hoặc lỗi truy cập database tạm thời. Retry có thể giúp phục hồi. Trong một số tình huống write retry, Spring Batch có thể rollback và gọi writer lại với chunk hoặc nhóm item nhỏ hơn để xác định lỗi. Không nên giả định mỗi callback tương ứng với đúng một item duy nhất.

Vì retry granularity có thể phụ thuộc loại lỗi và cách xử lý chunk, listener nên ghi nhận context và loại exception thay vì suy luận rằng một lần `onError` luôn đại diện cho một item nghiệp vụ riêng.

## 9. Theo dõi retry count và exception

`RetryContext` cho phép đọc số lần thử và exception gần nhất. Có thể dùng dữ liệu này để tạo metric:

```java
@Override
public <T, E extends Throwable> void onError(
        RetryContext context,
        RetryCallback<T, E> callback,
        Throwable throwable) {

    retryAttemptsCounter.increment();

    log.warn("Retry count={}, exceptionType={}",
            context.getRetryCount(),
            throwable.getClass().getName());
}
```

Trong ứng dụng có Micrometer, có thể ghi counter hoặc timer theo tên Job/Step và loại exception. Nên giới hạn tập tag để tránh cardinality cao; không đưa order ID, customer ID hoặc nội dung exception tùy ý vào metric tag.

Các metric hữu ích:

- Tổng số retry attempt.
- Số operation kết thúc thành công sau retry.
- Số operation hết lượt retry và thất bại.
- Tỷ lệ retry theo loại exception.
- Thời gian từ lúc retry bắt đầu đến khi kết thúc.

Retry count tăng liên tục có thể chỉ ra database đang quá tải, dịch vụ ngoài không ổn định hoặc timeout quá ngắn. Cần dùng metric để tìm nguyên nhân gốc thay vì chỉ tăng retry limit.

## 10. Ghi log an toàn trong RetryListener

RetryListener thường được gọi khi lỗi xảy ra, nên log cần đủ thông tin chẩn đoán nhưng không được làm lộ dữ liệu.

Nên ghi:

- Tên Job và Step nếu có ngữ cảnh.
- JobExecution ID hoặc StepExecution ID.
- Loại exception và số lần thử.
- Business key đã được phép ghi log.
- Kết quả cuối cùng của retry operation.

Tránh ghi:

- Password, token, API key hoặc secret.
- Toàn bộ payload chứa dữ liệu cá nhân.
- SQL có tham số nhạy cảm.
- Exception message nếu nó chứa thông tin nhạy cảm từ hệ thống ngoài.

Nếu listener cần truy cập execution context, có thể lấy thông tin từ context phù hợp hoặc dùng cơ chế truyền correlation ID. Không nên lưu dữ liệu nghiệp vụ lớn trong `RetryContext` chỉ để phục vụ log.

## 11. Thread safety và scope của listener

Listener thường được đăng ký như một bean dùng chung. Trong ứng dụng có nhiều Job chạy đồng thời hoặc Step đa luồng, các callback có thể được gọi từ nhiều thread.

Vì vậy:

- Không lưu retry count của từng operation trong field mutable của singleton listener.
- Dùng `RetryContext` để giữ dữ liệu thuộc một retry operation.
- Dùng metric implementation thread-safe.
- Nếu cần ghi audit vào database, dùng service có transaction và cơ chế chống trùng phù hợp.
- Không giữ tham chiếu đến item hoặc exception lâu hơn vòng đời cần thiết.

Ví dụ không nên dùng field `currentRetryCount` trong listener singleton để theo dõi từng item; hai operation đồng thời có thể ghi đè giá trị của nhau. Dữ liệu riêng của một retry operation nên nằm trong `RetryContext` hoặc một cấu trúc có khóa theo execution/correlation ID.

## 12. Kết hợp RetryListener với BackOffPolicy

Retry nhanh liên tục có thể tạo áp lực lớn lên database hoặc dịch vụ ngoài đang gặp sự cố. `BackOffPolicy` điều khiển khoảng chờ giữa các lần thử; `RetryListener` quan sát các lần thử và kết quả.

Ví dụ cấu hình backoff theo thời gian:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(4)
.backOffPolicy(new ExponentialBackOffPolicy())
.listener(batchRetryListener)
```

`ExponentialBackOffPolicy` tăng khoảng chờ giữa các lần thử theo cấu hình của policy. Có thể cấu hình initial interval, multiplier và maximum interval nếu cần. Cần cân bằng thời gian chờ với thời gian chạy tối đa của Job và SLA nghiệp vụ.

Listener không tự tạo backoff. Nếu muốn điều chỉnh thời gian chờ, hãy cấu hình `BackOffPolicy`; nếu muốn ghi nhận attempt, dùng `RetryListener`.

## 13. Khi retry hết giới hạn

Khi retry policy không cho phép thử thêm, retry operation kết thúc với exception cuối cùng. Listener `close` có thể ghi nhận kết quả thất bại. Sau đó, hành vi của Step phụ thuộc cấu hình fault tolerance:

- Nếu exception được skip và skip limit chưa vượt, item có thể được bỏ qua.
- Nếu exception không được skip, Step thường thất bại.
- Nếu có recovery logic phù hợp, framework có thể thực hiện nhánh xử lý sau retry theo cấu hình.

Không nên giả định RetryListener có thể tự quyết định điều gì xảy ra sau retry exhaustion. Hãy dùng retry policy, skip policy, recovery callback hoặc flow Step tương ứng để định nghĩa hành vi.

## 14. RetryListener và tính idempotent

Retry có nghĩa một thao tác có thể được thực hiện nhiều lần. Nếu thao tác tạo tác dụng phụ, cần bảo đảm việc lặp không tạo dữ liệu sai.

Ví dụ, một writer gửi yêu cầu thanh toán đến API ngoài. Nếu API đã xử lý nhưng response bị timeout, Spring Batch có thể retry và gửi yêu cầu lần nữa. Nếu API không hỗ trợ idempotency, khách hàng có thể bị trừ tiền hai lần.

Các biện pháp:

- Dùng idempotency key ổn định theo business operation.
- Dùng unique business key hoặc upsert khi ghi database.
- Hạn chế gọi API/email trong processor hoặc writer nếu không kiểm soát được retry.
- Dùng transactional outbox để phát sự kiện sau khi transaction dữ liệu chính commit.
- Ghi nhận trạng thái request để đối soát trước khi retry những thao tác có hậu quả lớn.

RetryListener giúp quan sát việc thử lại, nhưng không biến một thao tác không idempotent thành an toàn. Tính idempotent phải được bảo đảm bởi thiết kế nghiệp vụ và hệ thống đích.

## 15. Kiểm thử RetryListener

Có thể kiểm thử listener độc lập bằng cách gọi các callback với `RetryContext` phù hợp hoặc kiểm thử tích hợp một Step có lỗi tạm thời.

Các trường hợp nên xác nhận:

- `open` được gọi khi retry operation bắt đầu.
- `onError` ghi nhận exception của lần thử thất bại.
- Lần retry sau thành công thì `close` ghi nhận operation thành công.
- Hết retry limit thì `close` nhận được lỗi cuối cùng.
- Listener không thay đổi retry policy hoặc làm nuốt exception.
- Nhiều retry operation đồng thời không làm lẫn state.
- Log và metric không chứa dữ liệu nhạy cảm.

Ví dụ test đơn giản cho listener có thể dùng mock logger/metric hoặc một recorder thread-safe để xác nhận callback. Integration test ở cấp Step hữu ích hơn khi cần xác nhận Spring Batch thực sự gọi listener theo retry policy đã cấu hình.

## 16. Những lỗi thường gặp

### Nghĩ RetryListener quyết định exception có được retry

Listener chủ yếu quan sát vòng đời retry. `.retry(...)`, `.retryLimit(...)` hoặc `RetryPolicy` mới quyết định exception có được thử lại hay không.

### Xem mỗi onError là một lỗi cuối cùng

`onError` được gọi cho một lần thử thất bại; operation vẫn có thể thành công sau đó. Muốn biết kết quả cuối, xem callback `close` và trạng thái Step.

### Dùng RetryListener để skip item

Listener không thay thế `SkipPolicy` hoặc `SkipListener`. Hãy cấu hình skip rõ ràng cho exception item-level được phép bỏ qua.

### Retry mọi exception

Retry lỗi dữ liệu cố định hoặc lỗi lập trình không giúp phục hồi. Chỉ retry exception có khả năng tạm thời và thao tác có thể lặp an toàn.

### Lưu state theo operation trong field singleton

Nhiều execution đồng thời có thể dùng chung listener. Dùng `RetryContext` hoặc state thread-safe có correlation ID.

### Ghi toàn bộ payload vào log

Retry thường xảy ra ở dữ liệu lỗi hoặc hệ thống ngoài. Log payload không kiểm soát có thể làm lộ dữ liệu cá nhân hoặc bí mật. Chỉ ghi business key và thông tin đã được phép.

### Nghĩ retry đảm bảo exactly-once

Retry có thể gọi lại thao tác. Cần idempotency, unique key hoặc outbox để chống tác dụng phụ trùng lặp.

## 17. Quy trình triển khai RetryListener

Khi thêm RetryListener vào một chunk Step, có thể thực hiện theo trình tự:

1. Xác định loại exception tạm thời thực sự có thể retry.
2. Cấu hình `.faultTolerant()`, `.retry(...)` và `.retryLimit(...)` cho Step.
3. Chọn `BackOffPolicy` nếu cần khoảng chờ giữa các lần thử.
4. Triển khai `RetryListener` với `open`, `onError` và `close`.
5. Dùng `RetryContext` để đọc retry count và exception gần nhất.
6. Đăng ký listener bằng `.listener(retryListener)` trên fault-tolerant Step builder.
7. Ghi metric/log theo Job, Step và exception type; tránh log payload nhạy cảm.
8. Bảo đảm listener thread-safe nếu Job/Step có thể chạy đồng thời.
9. Kiểm thử retry thành công, retry exhaustion, skip sau retry và tác dụng phụ khi thao tác được gọi lại.
10. Theo dõi tỷ lệ retry để điều chỉnh policy và xử lý nguyên nhân gốc.

## Kết luận

`RetryListener` là hook của Spring Retry được Spring Batch sử dụng trong fault-tolerant Step để quan sát vòng đời retry. `open` được gọi khi operation bắt đầu, `onError` ghi nhận một lần thử thất bại và `close` được gọi khi operation kết thúc. Listener có thể dùng `RetryContext` để theo dõi retry count và exception gần nhất, ghi log hoặc tạo metric. Nó không thay thế `RetryPolicy`, `.retry(...)`, `.retryLimit(...)`, `BackOffPolicy` hay `SkipListener`. Hãy chỉ retry lỗi có khả năng phục hồi, giữ listener thread-safe và bảo đảm thao tác có tác dụng phụ được thiết kế idempotent.
