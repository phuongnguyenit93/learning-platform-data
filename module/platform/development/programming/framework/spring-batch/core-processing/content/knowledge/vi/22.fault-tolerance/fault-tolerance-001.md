# FaultTolerantStepBuilder

Trong Spring Batch, `FaultTolerantStepBuilder` là builder mở rộng cấu hình cho một chunk-oriented Step khi cần xử lý lỗi có kiểm soát. Nó cho phép khai báo exception nào được retry, exception nào được skip, giới hạn số lần thử hoặc số item bị bỏ qua, chính sách rollback, backoff và các listener liên quan.

Builder này được tạo từ `SimpleStepBuilder` bằng phương thức `faultTolerant()`. Nó không tự làm cho mọi lỗi trở nên có thể phục hồi. Ứng dụng vẫn phải phân loại exception theo nghiệp vụ, thiết kế Reader/Processor/Writer phù hợp với việc gọi lại và xác định rõ dữ liệu nào được phép bỏ qua.

## 1. FaultTolerantStepBuilder nằm ở đâu trong cấu hình Step?

Một chunk-oriented Step thông thường có `ItemReader`, `ItemProcessor` và `ItemWriter`. Nếu không cấu hình fault tolerance, exception không được xử lý sẽ làm Step thất bại theo transaction policy.

Khi cần retry hoặc skip, gọi `.faultTolerant()` trên builder của chunk Step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

`faultTolerant()` chuyển cấu hình sang `FaultTolerantStepBuilder`, bổ sung các phương thức liên quan đến skip, retry và rollback. Các thành phần Reader, Processor, Writer và commit interval vẫn được cấu hình như chunk Step thông thường.

Builder là API cấu hình ở thời điểm tạo Step. Khi Job chạy, Spring Batch sử dụng các policy đã cấu hình để điều phối transaction và xử lý exception.

## 2. Fault tolerance không có nghĩa là bỏ qua mọi lỗi

Mục tiêu của fault tolerance là phân biệt lỗi có thể phục hồi với lỗi cần dừng Job. Ví dụ:

| Loại lỗi | Hành vi thường phù hợp |
|---|---|
| Dòng CSV sai định dạng, bản ghi không hợp lệ | Skip nếu nghiệp vụ cho phép loại bản ghi đó. |
| Database tạm thời deadlock hoặc lỗi kết nối có thể phục hồi | Retry có giới hạn và backoff. |
| Thiếu cấu hình bắt buộc hoặc schema sai | Thường fail ngay để người vận hành sửa cấu hình. |
| Lỗi lập trình như `NullPointerException` ngoài dự kiến | Thường fail; không nên skip để che lỗi. |
| Item vi phạm quy tắc nghiệp vụ không được phép bỏ qua | Fail hoặc chuyển sang quy trình xử lý riêng. |

Không nên cấu hình `.skip(Exception.class)` một cách rộng rãi. Cách đó có thể làm Job hoàn tất dù lỗi hạ tầng, lỗi lập trình hoặc lỗi dữ liệu nghiêm trọng đã xảy ra. Hãy chọn các exception cụ thể và có lý do nghiệp vụ rõ ràng.

## 3. Skip exception bằng skip() và skipLimit()

`skip()` khai báo loại exception được phép bỏ qua. `skipLimit()` đặt giới hạn tổng số skip của Step execution, tính trên các lỗi đọc, xử lý và ghi.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(10)
        .build();
```

Trong ví dụ, các dòng file không parse được và đơn hàng không hợp lệ có thể bị skip. Tổng số skip tối đa là 10. Khi có lỗi skippable tiếp theo làm vượt giới hạn, Step thất bại.

`skipLimit` là giới hạn chung cho read skip, process skip và write skip, không phải 10 lỗi cho từng giai đoạn.

| Số skip tích lũy | Kết quả với `skipLimit(10)` |
|---:|---|
| 0–9 | Các lỗi phù hợp có thể tiếp tục được skip. |
| 10 | Lỗi thứ 10 vẫn nằm trong giới hạn. |
| 11 | Lỗi tiếp theo vượt giới hạn và làm Step thất bại. |

Nếu không cấu hình skip rule, lỗi không được mặc định xem là có thể bỏ qua. Có thể dùng `noSkip()` để loại trừ một exception cụ thể khỏi nhóm skip đã khai báo rộng hơn:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(IllegalStateException.class)
.skipLimit(10)
```

Tuy nhiên, cách khai báo skip theo một superclass rộng rồi loại trừ từng exception dễ bỏ sót trường hợp. Thường nên liệt kê các exception cần skip cụ thể ngay từ đầu.

## 4. Skip ở Reader, Processor và Writer

Spring Batch có thể skip lỗi ở ba giai đoạn của chunk:

### Read skip

Reader ném exception khi đọc dữ liệu. Ví dụ `FlatFileItemReader` gặp dòng không đúng định dạng và ném `FlatFileParseException`. Nếu exception được cấu hình skip, framework có thể bỏ qua dòng lỗi và tiếp tục đọc.

### Process skip

Processor ném exception khi một item không vượt qua quy tắc nghiệp vụ. Ví dụ thiếu mã khách hàng hoặc giá trị số tiền không hợp lệ. Nếu exception được cho phép skip, item đó không được chuyển đến Writer.

### Write skip

Writer ném exception khi ghi dữ liệu. Trường hợp này phức tạp hơn vì Writer thường nhận cả một chunk. Spring Batch có thể cần cô lập item gây lỗi bằng cách thử lại hoặc ghi theo nhóm nhỏ hơn tùy cấu hình và khả năng của Writer.

Các bộ đếm tương ứng trên `StepExecution`:

| Bộ đếm | Ý nghĩa |
|---|---|
| `readSkipCount` | Số lỗi đọc đã được skip. |
| `processSkipCount` | Số lỗi xử lý đã được skip. |
| `writeSkipCount` | Số lỗi ghi đã được skip. |
| `skipCount` | Tổng số skip. |
| `filterCount` | Số item bị filter vì Processor trả về `null`; không phải skip. |

Khi vận hành, nên xem từng bộ đếm riêng để biết lỗi đến từ nguồn đọc, quy tắc xử lý hay đích ghi. Một Job có `skipCount` cao có thể hoàn tất nhưng chất lượng dữ liệu đầu vào vẫn cần được xem xét.

## 5. Retry exception bằng retry() và retryLimit()

Retry phù hợp với lỗi tạm thời có khả năng tự hết khi thử lại, chẳng hạn deadlock hoặc lỗi truy cập database ngắn hạn. `retry()` khai báo loại exception được phép thử lại; `retryLimit()` giới hạn số lần thử theo policy.

```java
import org.springframework.dao.TransientDataAccessException;

return new StepBuilder("updateOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

`TransientDataAccessException` là nhóm lỗi truy cập dữ liệu được xem là có thể tạm thời. Có thể chọn exception cụ thể hơn nếu chỉ muốn retry một loại lỗi nhất định.

Retry khác skip:

- Retry thử lại thao tác lỗi với hy vọng lần sau thành công.
- Skip chấp nhận bỏ qua item sau khi lỗi được phân loại là có thể bỏ qua và giới hạn chưa bị vượt.
- Nếu retry hết giới hạn mà exception cũng thuộc nhóm skip, policy skip có thể cho phép bỏ qua item; nếu không, Step thất bại.

Không nên retry vô hạn. Retry quá nhiều có thể kéo dài Job, giữ tài nguyên và làm hệ thống đích quá tải. Retry cũng không sửa được lỗi dữ liệu cố định như ngày tháng sai định dạng hoặc mã bắt buộc bị thiếu.

## 6. Backoff giữa các lần retry

Nếu các lần retry diễn ra ngay lập tức, nhiều worker có thể cùng thử lại đúng lúc dịch vụ đang quá tải hoặc database đang tranh chấp. Backoff tạo khoảng chờ giữa các lần thử để hệ thống có thời gian phục hồi.

Spring Retry cung cấp các policy backoff có thể cấu hình cùng FaultTolerantStepBuilder. Ví dụ dùng `ExponentialBackOffPolicy`:

```java
import org.springframework.retry.backoff.ExponentialBackOffPolicy;

ExponentialBackOffPolicy backOffPolicy = new ExponentialBackOffPolicy();
backOffPolicy.setInitialInterval(500L);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(5_000L);

return new StepBuilder("updateOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .backOffPolicy(backOffPolicy)
        .build();
```

Ví dụ bắt đầu chờ 500 ms, tăng khoảng chờ theo hệ số 2 và giới hạn tối đa 5 giây. Giá trị cụ thể phụ thuộc SLA, timeout của hệ thống đích và số worker đồng thời.

Backoff không thay thế timeout của database hoặc HTTP client. Nếu một lần gọi bị treo không có timeout, retry policy có thể không lấy lại quyền điều khiển đúng lúc. Hãy cấu hình timeout cho từng tài nguyên bên ngoài.

## 7. Dùng RetryPolicy và SkipPolicy tùy chỉnh

Các phương thức `retry()`/`retryLimit()` và `skip()`/`skipLimit()` phù hợp với quy tắc đơn giản. Nếu điều kiện phụ thuộc nhiều yếu tố hơn, có thể dùng policy riêng.

### SkipPolicy

`SkipPolicy` quyết định một exception có được skip hay không dựa trên exception và số lượng skip hiện tại:

```java
import org.springframework.batch.core.step.skip.SkipLimitExceededException;
import org.springframework.batch.core.step.skip.SkipPolicy;

public class OrderSkipPolicy implements SkipPolicy {

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof InvalidOrderException) {
            return skipCount < 10;
        }

        return false;
    }
}
```

Đăng ký policy:

```java
.faultTolerant()
.skipPolicy(new OrderSkipPolicy())
```

Khi dùng `skipPolicy`, policy chịu trách nhiệm quyết định cả điều kiện và giới hạn skip. Không nên đồng thời thêm nhiều rule `skip()`/`skipLimit()` khiến chính sách trở nên khó hiểu.

### RetryPolicy

`RetryPolicy` tùy chỉnh có thể quyết định có thử lại exception hay không, dựa trên loại lỗi, số lần thử hoặc thông tin context. Có thể đăng ký bằng `.retryPolicy(...)` khi cần policy vượt quá danh sách exception và retry limit đơn giản.

Ví dụ, một hệ thống có thể retry lỗi kết nối database nhưng không retry lỗi validation. Nếu dùng policy tùy chỉnh, cần unit test rõ ràng cho từng exception và ngưỡng retry; tránh giữ counter mutable trong singleton policy nếu policy được chia sẻ giữa nhiều Step hoặc JobExecution.

## 8. Phân biệt retry và rollback

Retry không có nghĩa là transaction hiện tại tiếp tục từ đúng câu lệnh bị lỗi. Trong chunk processing, một exception có thể làm transaction chunk rollback trước khi framework thực hiện lần thử tiếp theo. Lần thử lại có thể chạy trong transaction mới.

```text
Chunk attempt 1
  BEGIN
  READ / PROCESS / WRITE
  Deadlock exception
  ROLLBACK
       |
       v
Backoff
       |
       v
Chunk attempt 2
  BEGIN
  Thực hiện lại thao tác cần thiết
  WRITE thành công
  COMMIT
```

Các chunk đã commit trước đó vẫn được giữ. Chunk đang thất bại có thể phải xử lý lại. Vì vậy, Processor và Writer phải chịu được việc được gọi lại, còn các tác dụng phụ ngoài transaction cần idempotency key hoặc transactional outbox.

Nếu một Writer vừa cập nhật database vừa gọi HTTP, rollback database không thể thu hồi request HTTP đã được hệ thống ngoài xử lý. Retry có thể gửi request lần nữa. Không nên thực hiện side effect không idempotent trực tiếp trong đường retry.

## 9. noRollback() điều chỉnh rollback policy

Mặc định, nhiều exception trong quá trình chunk có thể làm transaction rollback. `noRollback()` chỉ định một exception không làm rollback transaction:

```java
.faultTolerant()
.skip(NonCriticalValidationException.class)
.noRollback(NonCriticalValidationException.class)
```

Hai cấu hình có vai trò khác nhau:

- `skip()` xác định exception có thể được bỏ qua.
- `noRollback()` điều chỉnh việc exception đó có làm rollback transaction hay không.

`noRollback()` không có nghĩa exception biến mất hoặc item tự động được ghi. Exception vẫn cần được xử lý theo skip/retry policy và luồng thực thi. Chỉ dùng khi trạng thái transaction vẫn nhất quán nếu không rollback.

Ví dụ, nếu Processor phát hiện một điều kiện validation không ảnh hưởng đến dữ liệu đã thay đổi trong transaction, có thể cân nhắc noRollback. Nhưng nếu Writer đã ghi một phần dữ liệu rồi gặp exception, cho phép commit có thể để lại trạng thái dở dang. Cần phân tích chính xác thời điểm và tác động của exception trước khi áp dụng.

## 10. processorNonTransactional() và việc gọi lại Processor

Trong fault-tolerant Step, một item có thể phải đi qua logic xử lý lại khi chunk rollback hoặc retry. Nếu Processor là thành phần không transactional và việc gọi lại nó không cần thiết, có thể dùng `processorNonTransactional()` để cho Spring Batch cache kết quả xử lý và không gọi lại Processor cho item đã được xử lý trong tình huống retry phù hợp.

```java
return new StepBuilder("enrichOrdersStep", jobRepository)
        .<Order, EnrichedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .processorNonTransactional()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Tùy chọn này phù hợp khi Processor có kết quả ổn định cho cùng input và không cần chạy lại sau rollback. Nó không làm Processor trở thành thread-safe, cũng không bảo vệ side effect của Writer. Nếu Processor phụ thuộc dữ liệu bên ngoài có thể thay đổi giữa các lần thử hoặc có tác dụng phụ cần thực hiện lại, cần xem xét kỹ trước khi cache kết quả.

## 11. KeyGenerator và nhận diện item trong retry

Trong một số trường hợp, framework cần nhận diện item đã được xử lý để quản lý cache/retry. Nếu `equals()` và `hashCode()` của item không phản ánh đúng danh tính nghiệp vụ, có thể cấu hình `KeyGenerator` để tạo khóa ổn định.

```java
import org.springframework.batch.item.KeyGenerator;

KeyGenerator orderKeyGenerator = item -> {
    Order order = (Order) item;
    return order.sourceSystem() + ":" + order.sourceOrderId();
};
```

Đăng ký trong cấu hình fault-tolerant Step:

```java
.faultTolerant()
.keyGenerator(orderKeyGenerator)
```

Khóa cần ổn định qua retry và restart. Không dùng index trong bộ nhớ hoặc UUID mới mỗi lần gọi. `KeyGenerator` hỗ trợ nhận diện item trong cơ chế nội bộ của fault-tolerant processing; nó không thay thế unique constraint ở database và không tự ngăn bản ghi nghiệp vụ bị nhân đôi.

## 12. Gắn SkipListener để ghi nhận item bị bỏ qua

`SkipListener` cung cấp callback riêng cho lỗi đọc, xử lý và ghi:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class OrderSkipListener
        implements SkipListener<Order, ProcessedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInRead(Throwable throwable) {
        log.warn("Read skip: {}", throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(Order item, Throwable throwable) {
        log.warn("Process skip for order {}: {}",
                item.sourceOrderId(), throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(ProcessedOrder item, Throwable throwable) {
        log.warn("Write skip for order {}: {}",
                item.sourceOrderId(), throwable.getMessage());
    }
}
```

Đăng ký listener trong builder:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(10)
.listener(orderSkipListener)
```

`onSkipInRead()` không có item vì Reader có thể thất bại trước khi tạo đối tượng. Với lỗi parse file, có thể lấy số dòng và thông tin nguồn từ exception cụ thể như `FlatFileParseException`.

Nếu listener ghi reject vào database, file hoặc gửi message, cần nhớ chunk có thể rollback và item có thể được xử lý lại. Dùng khóa duy nhất theo JobInstance/business key, upsert hoặc outbox để tránh reject record và notification bị nhân đôi.

## 13. Ví dụ FaultTolerantStepBuilder hoàn chỉnh

Ví dụ sau kết hợp retry, backoff, skip, noRollback và SkipListener:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter,
        OrderSkipListener orderSkipListener) {

    ExponentialBackOffPolicy backOffPolicy = new ExponentialBackOffPolicy();
    backOffPolicy.setInitialInterval(500L);
    backOffPolicy.setMultiplier(2.0);
    backOffPolicy.setMaxInterval(5_000L);

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .backOffPolicy(backOffPolicy)
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(10)
            .noRollback(NonCriticalValidationException.class)
            .listener(orderSkipListener)
            .build();
}
```

Các kiểu `Order`, `ProcessedOrder`, `InvalidOrderException` và `NonCriticalValidationException` là domain type của ứng dụng. `FlatFileParseException` cần được import từ Spring Batch FlatFile module. Cấu hình trên chỉ là ví dụ: `NonCriticalValidationException` chỉ nên dùng trong `noRollback` nếu transaction vẫn an toàn khi không rollback. Nếu exception đó không cần skip, không nên thêm nó vào skip policy chỉ để Step tiếp tục.

Trong hệ thống thật, hãy chọn exception retry và skip không chồng lấn ngoài ý muốn. Nếu một exception được cấu hình vừa retry vừa skip, cần hiểu thứ tự policy và kết quả sau khi retry hết giới hạn. Viết test cho các loại exception quan trọng sẽ giúp tránh một cấu hình có vẻ hợp lý nhưng tạo hành vi khác dự kiến.

## 14. FaultTolerantStepBuilder và restart

Retry/skip thường xử lý lỗi trong cùng một lần thực thi Step. Nếu Step vẫn thất bại, Job có thể được restart bằng cùng identifying JobParameters nếu Job cho phép.

```text
JobExecution #1: FAILED
  Chunk 1: COMMITTED
  Chunk 2: có item được skip, COMMITTED
  Chunk 3: retry hết giới hạn, ROLLED BACK

Restart cùng JobInstance
  |
  v
JobExecution #2
  Reader khôi phục checkpoint sau Chunk 2
  Chunk 3 được xử lý lại
```

Các điểm cần chú ý:

- Reader phải hỗ trợ lưu state nếu muốn tiếp tục từ checkpoint.
- Item trong chunk đã commit, kể cả item bị skip, thường không được đọc lại khi restart thông thường.
- Item thuộc chunk rollback có thể được đọc và xử lý lại.
- SkipListener có thể được gọi lại cho item được xử lý lại sau rollback; thao tác ghi reject phải idempotent.
- Writer cần chịu được retry/restart và không tạo dữ liệu trùng.
- Không thay identifying JobParameters nếu mục tiêu là restart cùng JobInstance.

FaultTolerantStepBuilder không tự bảo đảm restart. Nó cấu hình cách xử lý lỗi trong Step; restart còn phụ thuộc JobRepository, ExecutionContext, ItemStream và thiết kế dữ liệu nghiệp vụ.

## 15. Ảnh hưởng của transaction và side effect ngoài database

Retry thường đi cùng rollback. Nếu Writer cập nhật database và gọi một API ngoài trong cùng một lần ghi, rollback database không thể thu hồi API call đã thành công.

Ví dụ:

```text
Chunk transaction
  |
  +--> UPDATE imported_order
  +--> POST event to external service (success)
  +--> Error on another item
  |
  +--> ROLLBACK database
  |
  +--> Retry may send the same external event again
```

Các cách xử lý:

1. Dùng idempotency key ổn định khi gọi API.
2. Ghi sự kiện vào transactional outbox cùng transaction với dữ liệu nghiệp vụ.
3. Để một Step riêng gửi message sau khi dữ liệu đã commit.
4. Dùng thao tác bù nếu hệ thống ngoài không hỗ trợ idempotency và hành động có thể cần thu hồi.

Không nên đặt `REQUIRES_NEW` cho mọi thao tác trong Writer để tránh rollback. Cách đó có thể commit dữ liệu một phần trong khi chunk bên ngoài thất bại, làm phức tạp restart và tính nhất quán.

## 16. Kiểm thử cấu hình fault-tolerant

Nên kiểm thử riêng từng policy và một số tình huống tích hợp. Không chỉ kiểm tra Job kết thúc `COMPLETED`; cần xác nhận item nào được ghi, item nào bị skip và thao tác nào được retry.

### Kiểm thử SkipPolicy

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class OrderSkipPolicyTest {

    private final OrderSkipPolicy policy = new OrderSkipPolicy();

    @Test
    void skipsInvalidOrderWithinLimit() throws Exception {
        assertTrue(policy.shouldSkip(
                new InvalidOrderException("Invalid amount"), 2));
    }

    @Test
    void doesNotSkipUnexpectedException() throws Exception {
        assertFalse(policy.shouldSkip(
                new IllegalStateException("Unexpected state"), 0));
    }
}
```

### Kiểm thử retry

Có thể mock dependency để lần gọi đầu ném lỗi tạm thời và lần tiếp theo thành công. Xác nhận số lần gọi đúng giới hạn và kết quả chỉ được ghi một lần. Với retry policy tùy chỉnh, kiểm tra cả exception được phép và không được phép retry.

### Kiểm thử Step

Với `spring-batch-test` và `JobLauncherTestUtils`, tạo dữ liệu gồm item hợp lệ, item bị skip và item gây lỗi không thể retry. Kiểm tra:

- `BatchStatus` và `ExitStatus` của Job/Step.
- `readSkipCount`, `processSkipCount`, `writeSkipCount` và `filterCount`.
- Số lần Reader/Processor/Writer được gọi nếu đó là điều kiện quan trọng.
- Nội dung bảng đích và bảng reject.
- Hành vi khi restart cùng JobInstance sau chunk rollback.
- Không có bản ghi hoặc thông báo bị nhân đôi.

Khi kiểm thử retry, dùng một lỗi có thể phục hồi xác định để test không phụ thuộc mạng hoặc database bên ngoài. Khi kiểm thử deadlock thật, nên có integration test riêng với database phù hợp và giới hạn thời gian rõ ràng.

## 17. Những lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Skip `Exception.class` quá rộng | Lỗi lập trình hoặc lỗi hạ tầng bị bỏ qua. | Chỉ skip exception nghiệp vụ đã xác định. |
| Nhầm `skipLimit` với `retryLimit` | Giới hạn sai hành vi lỗi. | Skip limit đếm item bị bỏ qua; retry limit giới hạn lần thử. |
| Retry lỗi dữ liệu cố định | Job tốn thời gian nhưng lỗi không thể tự hết. | Dùng validation/skip hoặc fail tùy quy tắc nghiệp vụ. |
| Retry không có backoff | Worker có thể liên tục gây tải lên hệ thống đang lỗi. | Dùng backoff và timeout phù hợp. |
| Dùng `noRollback()` như cách bỏ qua exception | Transaction có thể commit dữ liệu dở dang. | Phân biệt rollback policy với skip policy và kiểm tra tính nhất quán. |
| Processor có side effect nhưng cache bằng `processorNonTransactional()` | Kết quả hoặc side effect không còn phù hợp với lần thử sau. | Chỉ dùng khi Processor an toàn, ổn định và không cần gọi lại. |
| Writer không idempotent | Retry hoặc restart tạo dữ liệu trùng. | Unique constraint, upsert, idempotency key hoặc outbox. |
| SkipListener ghi reject trực tiếp không chống trùng | Item được xử lý lại có thể tạo reject record trùng. | Dùng unique key và thao tác ghi idempotent. |
| Cấu hình policy nhưng không test exception hierarchy | Exception subclass có thể được phân loại ngoài dự kiến. | Test cả exception cụ thể và superclass/subclass liên quan. |

## Kết luận

`FaultTolerantStepBuilder` mở rộng cấu hình chunk Step để xử lý lỗi bằng retry, skip và rollback policy. `skip()`/`skipLimit()` xác định item nào được bỏ qua và giới hạn tổng skip; `retry()`/`retryLimit()` cùng backoff xử lý lỗi tạm thời; `noRollback()` điều chỉnh exception có làm rollback transaction hay không. `SkipPolicy`, `RetryPolicy`, `SkipListener`, `processorNonTransactional()` và `KeyGenerator` hỗ trợ các trường hợp cần kiểm soát chi tiết hơn. Cấu hình fault tolerance chỉ đáng tin cậy khi đi cùng Reader có checkpoint, Writer idempotent, xử lý side effect ngoài transaction và kiểm thử restart thực tế.
