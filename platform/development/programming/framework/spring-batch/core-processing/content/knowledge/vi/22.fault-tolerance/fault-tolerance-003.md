# Exception classifier

Trong Spring Batch, exception classifier là cách phân loại exception theo loại lỗi hoặc nguyên nhân để chọn chính sách xử lý phù hợp. Một chunk Step có thể gặp lỗi dữ liệu của từng item, lỗi truy cập database tạm thời, lỗi cấu hình hoặc lỗi nghiêm trọng của hệ thống. Mỗi nhóm lỗi cần cách xử lý khác nhau: retry, skip, rollback hoặc dừng Step.

Thay vì xem mọi exception là một loại lỗi giống nhau, classifier ánh xạ exception sang một nhóm hoặc một policy. Ví dụ, `InvalidRecordException` có thể được phép skip; `DeadlockLoserDataAccessException` có thể được retry; `FatalImportException` phải làm Step thất bại. Phân loại đúng giúp Job tiếp tục khi có thể phục hồi và dừng sớm khi dữ liệu hoặc trạng thái hệ thống không còn đáng tin cậy.

## 1. Exception classifier là gì?

Classifier nhận một đối tượng đầu vào, trong trường hợp này là `Throwable`, rồi trả về kết quả phân loại. Kết quả có thể là một enum, một boolean hoặc một policy cụ thể.

```text
Exception phát sinh
       |
       v
 Exception classifier
       |
       +-- Lỗi dữ liệu item ------> SkipPolicy
       |
       +-- Lỗi tạm thời ----------> RetryPolicy
       |
       +-- Lỗi không an toàn -----> Fail Step
       |
       +-- Lỗi không rollback ----> No-rollback rule (nếu phù hợp)
```

Classifier chỉ quyết định exception thuộc nhóm nào hoặc policy nào cần áp dụng. Thành phần thực thi policy mới quyết định hành động cuối cùng, ví dụ có retry hay không, đã hết giới hạn skip hay chưa, hoặc transaction có rollback hay không.

Một classifier tốt cần có quy tắc rõ ràng, ổn định và có thể kiểm thử. Không nên phân loại dựa trên chuỗi message của exception nếu có thể dùng exception type hoặc mã lỗi có cấu trúc, vì message có thể thay đổi theo phiên bản thư viện, database hoặc locale.

## 2. Vì sao cần phân loại exception?

Trong một Job import, có thể xuất hiện nhiều lỗi khác nhau:

| Exception hoặc tình huống | Nhóm lỗi | Hướng xử lý thường cân nhắc |
|---|---|---|
| `InvalidRecordException` | Dữ liệu riêng của item không hợp lệ | Skip nếu nghiệp vụ cho phép và có giới hạn. |
| `FlatFileParseException` | Một dòng nguồn không đọc được | Read skip nếu reader có thể tiếp tục an toàn. |
| `DeadlockLoserDataAccessException` | Xung đột database có thể tạm thời | Retry có giới hạn và backoff. |
| `TransientDataAccessException` | Lỗi truy cập dữ liệu tạm thời | Retry nếu thao tác an toàn khi lặp. |
| `FatalImportException` | Lỗi nghiệp vụ/hệ thống không thể tiếp tục | Fail Step. |
| `FileNotFoundException` với file bắt buộc | Thiếu đầu vào cấp Job | Thường fail sớm, không skip từng item. |

Nếu không phân loại, ứng dụng dễ mắc hai lỗi đối lập:

- Retry cả lỗi dữ liệu cố định, khiến cùng một item thất bại nhiều lần mà không có khả năng tự phục hồi.
- Skip lỗi hạ tầng, khiến Job báo hoàn tất dù một phần dữ liệu chưa được xử lý do database hoặc dịch vụ ngoài đang gặp sự cố.

Classifier giúp đặt chính sách theo nguyên nhân thực tế thay vì dùng một cách xử lý chung cho mọi exception.

## 3. Phân loại theo exception type

Cách đơn giản nhất là kiểm tra kiểu exception bằng `instanceof` hoặc cấu hình class exception trong builder.

Ví dụ phân loại trong Java:

```java
enum FailureKind {
    INVALID_DATA,
    TRANSIENT_INFRASTRUCTURE,
    FATAL,
    UNKNOWN
}

public class BatchExceptionClassifier {

    public FailureKind classify(Throwable throwable) {
        if (throwable instanceof FatalImportException) {
            return FailureKind.FATAL;
        }

        if (throwable instanceof InvalidRecordException) {
            return FailureKind.INVALID_DATA;
        }

        if (throwable instanceof TransientDataAccessException) {
            return FailureKind.TRANSIENT_INFRASTRUCTURE;
        }

        return FailureKind.UNKNOWN;
    }
}
```

Thứ tự kiểm tra có ý nghĩa khi các exception có quan hệ kế thừa. Ví dụ, nếu một exception cụ thể kế thừa từ một lớp cha tổng quát, hãy kiểm tra trường hợp cụ thể trước. Nếu kiểm tra lớp cha trước, nhánh cụ thể có thể không bao giờ được thực hiện.

Trong ví dụ, `UNKNOWN` không tự động được xem là skip hoặc retry. Một lỗi chưa được phân loại nên được xử lý thận trọng, thường là để Step thất bại và bổ sung quy tắc sau khi đã hiểu nguyên nhân.

## 4. Dùng cấu hình fault tolerance có sẵn

Với các quy tắc đơn giản, không cần viết classifier riêng. Spring Batch cho phép khai báo trực tiếp exception được retry, skip hoặc không rollback trên fault-tolerant Step.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .skip(InvalidRecordException.class)
            .skip(FlatFileParseException.class)
            .skipLimit(50)
            .noSkip(FatalImportException.class)
            .build();
}
```

Trong ví dụ:

- `TransientDataAccessException` được chọn để retry tối đa theo retry limit.
- `InvalidRecordException` và `FlatFileParseException` được phép skip trong giới hạn tổng cộng 50 item.
- `FatalImportException` được loại khỏi nhóm exception được skip.

Đây là cách cấu hình phân loại theo kiểu exception bằng API của Step builder. Nếu chỉ có vài nhóm exception rõ ràng, cách này thường dễ đọc và dễ bảo trì hơn một classifier tùy chỉnh.

Không nên cấu hình `.skip(Exception.class)` một cách rộng rồi cố loại trừ mọi lỗi nghiêm trọng bằng `.noSkip(...)`. Hãy bắt đầu từ danh sách exception cụ thể đã được nghiệp vụ chấp nhận.

## 5. Phân loại retry bằng ExceptionClassifierRetryPolicy

Khi mỗi nhóm exception cần một retry policy khác nhau, Spring Retry cung cấp `ExceptionClassifierRetryPolicy`. Policy này chọn một `RetryPolicy` dựa trên exception phát sinh.

Ví dụ, deadlock được thử tối đa 4 lần, một lỗi optimistic locking được thử tối đa 2 lần, còn exception không nằm trong map không được retry:

```java
import java.util.HashMap;
import java.util.Map;

import org.springframework.classify.SubclassClassifier;
import org.springframework.retry.RetryPolicy;
import org.springframework.retry.policy.ExceptionClassifierRetryPolicy;
import org.springframework.retry.policy.NeverRetryPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;

@Bean
RetryPolicy classifiedRetryPolicy() {
    Map<Class<? extends Throwable>, RetryPolicy> policies =
            new HashMap<>();

    policies.put(
            DeadlockLoserDataAccessException.class,
            new SimpleRetryPolicy(4));

    policies.put(
            OptimisticLockingFailureException.class,
            new SimpleRetryPolicy(2));

    ExceptionClassifierRetryPolicy classifierPolicy =
            new ExceptionClassifierRetryPolicy();

    classifierPolicy.setExceptionClassifier(
            new SubclassClassifier<>(policies, new NeverRetryPolicy()));

    return classifierPolicy;
}
```

`SubclassClassifier` chọn policy dựa trên kiểu exception và các lớp cha tương ứng. Policy mặc định `NeverRetryPolicy` có nghĩa exception không khớp với map sẽ không được retry. `SimpleRetryPolicy` giới hạn số lần thử; trong Spring Retry, `maxAttempts` bao gồm cả lần thực hiện đầu tiên.

Đăng ký policy vào Step:

```java
return new StepBuilder("updateOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retryPolicy(classifiedRetryPolicy)
        .build();
```

Khi dùng `.retryPolicy(...)`, policy tùy chỉnh quyết định hành vi retry; không nên đồng thời khai báo các rule `.retry(...)`/`.retryLimit(...)` khác mà không hiểu cách builder kết hợp cấu hình. Hãy kiểm tra API theo phiên bản Spring Batch và Spring Retry trong ứng dụng.

### Khi nào dùng ExceptionClassifierRetryPolicy?

Nó hữu ích khi:

- Các nhóm exception có số lần thử tối đa khác nhau.
- Một số lỗi cần retry còn các lỗi khác phải fail ngay.
- Chính sách retry phụ thuộc loại lỗi hoặc một quy tắc phân loại rõ ràng.
- Muốn dùng các policy Spring Retry có sẵn thay vì tự viết toàn bộ `RetryPolicy`.

Nếu tất cả exception retryable đều có cùng giới hạn và backoff, cấu hình `.retry(...)` cùng `.retryLimit(...)` có thể đủ.

## 6. Phân loại skip bằng SkipPolicy

Skip policy quyết định một exception có thể được bỏ qua hay không. Với quy tắc đơn giản, dùng `.skip(...)`, `.noSkip(...)` và `.skipLimit(...)`. Khi cần phân loại theo nhiều nhóm, có thể triển khai `SkipPolicy`.

Hợp đồng cơ bản:

```java
public interface SkipPolicy {
    boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException;
}
```

Ví dụ policy chỉ skip lỗi dữ liệu riêng của item, trong giới hạn:

```java
public class ClassifiedOrderSkipPolicy implements SkipPolicy {

    private final long skipLimit;

    public ClassifiedOrderSkipPolicy(long skipLimit) {
        this.skipLimit = skipLimit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount) {
        if (throwable instanceof FatalImportException) {
            return false;
        }

        if (!(throwable instanceof InvalidRecordException)
                && !(throwable instanceof FlatFileParseException)) {
            return false;
        }

        return skipCount < skipLimit;
    }
}
```

Policy trả về `true` khi exception được phép skip và giới hạn chưa bị vượt. Khi trả về `false`, exception không được skip và được truyền ra theo cơ chế của Step. Nếu cần phân biệt rõ trường hợp vượt giới hạn bằng `SkipLimitExceededException`, policy tùy chỉnh có thể ném exception đó theo hợp đồng của Spring Batch.

Đăng ký custom policy:

```java
.faultTolerant()
.skipPolicy(new ClassifiedOrderSkipPolicy(50))
```

Khi dùng custom `SkipPolicy`, policy chịu trách nhiệm quyết định exception nào được skip. Không nên trộn `.skip(...)`, `.noSkip(...)` và custom policy nếu chưa xác định rõ quy tắc kết hợp của builder.

## 7. ExceptionClassifierSkipPolicy

Spring Batch cũng cung cấp `ExceptionClassifierSkipPolicy` để ủy quyền quyết định skip cho một policy được phân loại theo exception. Ý tưởng tương tự `ExceptionClassifierRetryPolicy`: exception khác nhau có thể được chuyển đến các `SkipPolicy` khác nhau.

Ví dụ về cách tổ chức policy:

```text
Exception
   |
   v
Classifier<Throwable, SkipPolicy>
   |
   +-- InvalidRecordException --> LimitCheckingItemSkipPolicy
   |
   +-- FlatFileParseException --> LimitCheckingItemSkipPolicy
   |
   +-- FatalImportException ---> NeverSkipItemSkipPolicy
   |
   +-- Unknown exception ------> NeverSkipItemSkipPolicy
```

Trong thiết kế này, mỗi nhóm exception được ánh xạ sang một policy skip phù hợp. Policy mặc định nên là không skip để lỗi chưa biết không bị bỏ qua ngoài ý muốn. Cách cấu hình cụ thể của classifier và policy map phụ thuộc phiên bản Spring Batch; khi cần nhiều quy tắc đơn giản, custom `SkipPolicy` có thể dễ đọc hơn việc tạo nhiều lớp adapter.

## 8. Phân loại exception và cause chain

Trong ứng dụng Spring, exception thực tế có thể được bọc bởi một exception khác. Ví dụ, một lỗi database có thể xuất hiện bên trong `DataAccessException`, `RetryException` hoặc một exception do lớp service tạo ra.

```text
BatchProcessingException
        |
        +-- cause: DataAccessException
                   |
                   +-- cause: SQLException
```

Nếu classifier chỉ kiểm tra kiểu của exception ngoài cùng, nó có thể không nhận ra lỗi gốc. Ngược lại, luôn lấy root cause cũng có thể làm mất ý nghĩa của exception domain bên ngoài.

Một cách tiếp cận là duyệt cause chain theo thứ tự và ưu tiên các loại exception đã định nghĩa rõ:

```java
public FailureKind classify(Throwable throwable) {
    for (Throwable current = throwable;
            current != null;
            current = current.getCause()) {

        if (current instanceof FatalImportException) {
            return FailureKind.FATAL;
        }

        if (current instanceof InvalidRecordException) {
            return FailureKind.INVALID_DATA;
        }

        if (current instanceof TransientDataAccessException) {
            return FailureKind.TRANSIENT_INFRASTRUCTURE;
        }
    }

    return FailureKind.UNKNOWN;
}
```

Đây là một ví dụ phân loại theo cause chain. Thứ tự ưu tiên phải phản ánh chính sách của ứng dụng. Nếu exception ngoài cùng là một lỗi fatal nhưng cause bên trong là lỗi tạm thời, ứng dụng thường nên tôn trọng phân loại fatal của exception domain thay vì tự động retry chỉ vì tìm thấy một cause thuộc nhóm transient.

Không nên duyệt cause chain vô hạn mà không phát hiện vòng lặp. Trong thực tế, cấu trúc cause chuẩn thường không tạo chu kỳ, nhưng một helper dùng chung vẫn nên bảo vệ trường hợp `cause == current` hoặc các wrapper bất thường.

## 9. Phân loại theo exception type hay error code?

Type-based classification thường là lựa chọn đầu tiên vì exception class thể hiện loại lỗi trong code. Tuy nhiên, một số hệ thống có thể dùng cùng một exception type cho nhiều mã lỗi database hoặc dịch vụ ngoài.

Ví dụ, `DataIntegrityViolationException` có thể đại diện cho unique constraint, foreign key constraint hoặc một vi phạm dữ liệu khác. Nếu nghiệp vụ chỉ cho phép skip duplicate key, classifier cần xem mã SQL state, vendor error code hoặc một exception domain đã được mapping trước đó.

Không nên kiểm tra chuỗi message như `"duplicate key"` nếu driver cung cấp mã lỗi có cấu trúc. Message có thể thay đổi giữa database hoặc phiên bản driver.

Một hướng thiết kế tốt:

1. Ở tầng repository/service, chuyển lỗi kỹ thuật đã hiểu thành exception domain cụ thể khi phù hợp.
2. Giữ nguyên cause để điều tra nguyên nhân gốc.
3. Classifier ở tầng Batch phân loại exception domain hoặc mã lỗi có cấu trúc.
4. Policy quyết định retry, skip hoặc fail.

Ví dụ, service có thể ném `DuplicateOrderException` khi phát hiện unique key trùng theo một quy tắc đã được xác nhận. Batch Step chỉ cần biết `DuplicateOrderException` có được skip hay không, không cần phân tích message SQL trong processor.

## 10. Classifier và rollback policy

Retry, skip và rollback là ba quyết định liên quan nhưng không giống nhau:

- **Retry:** có nên thử lại thao tác sau exception không?
- **Skip:** có được bỏ qua item gây exception và tiếp tục không?
- **Rollback:** transaction hiện tại có cần rollback khi exception xảy ra không?

Spring Batch cho phép cấu hình exception không làm rollback bằng `.noRollback(...)` trong fault-tolerant Step:

```java
.faultTolerant()
.noRollback(NonCriticalValidationException.class)
```

`noRollback` không có nghĩa exception được skip hoặc retry. Nó chỉ thay đổi hành vi rollback cho loại exception đã chỉ định. Nếu Step không xử lý exception đó theo chính sách khác, exception vẫn có thể làm Step thất bại.

Chỉ dùng `noRollback` khi đã xác nhận transaction có thể tiếp tục nhất quán sau exception. Với lỗi xảy ra sau khi writer đã thay đổi một phần dữ liệu, tránh bỏ rollback nếu điều đó có thể để lại trạng thái dở dang.

## 11. Bảng quyết định exception classifier

Một policy matrix giúp đội phát triển thống nhất cách xử lý lỗi:

| Nhóm | Ví dụ | Retry | Skip | Kết quả khi không phục hồi |
|---|---|---|---|---|
| Dữ liệu item không hợp lệ | `InvalidRecordException` | Thường không | Có, nếu nghiệp vụ cho phép | Fail khi vượt skip limit. |
| Lỗi parse một dòng | `FlatFileParseException` | Thường không | Có, nếu reader tiếp tục an toàn | Fail khi vượt skip limit. |
| Database deadlock | `DeadlockLoserDataAccessException` | Có giới hạn | Thường không | Fail Step sau retry exhaustion. |
| Lỗi dịch vụ tạm thời | Timeout exception đã phân loại | Có giới hạn/backoff | Thường không | Fail Step nếu hết retry. |
| Thiếu file bắt buộc | `FileNotFoundException` | Thường không | Không | Fail sớm. |
| Lỗi cấu hình hoặc lập trình | Exception đã xác định là fatal | Không | Không | Fail Step/Job. |
| Exception chưa biết | `UNKNOWN` | Không mặc định | Không mặc định | Fail để điều tra. |

Bảng này chỉ là mẫu thiết kế. Một exception cụ thể có thể được xử lý khác tùy nghiệp vụ, loại reader/writer và tính idempotent của thao tác.

## 12. Thứ tự ưu tiên khi có nhiều rule

Khi một exception có thể khớp với nhiều rule, cần xác định quy tắc ưu tiên. Ví dụ:

```java
class InvalidRecordException extends RuntimeException { }
class FatalImportException extends RuntimeException { }
```

Nếu classifier dùng map theo class hierarchy, exception cụ thể nên được chọn trước lớp cha tổng quát. Với custom classifier dùng `instanceof`, thứ tự `if` cũng ảnh hưởng kết quả.

Các nguyên tắc nên áp dụng:

- Kiểm tra exception domain cụ thể trước lớp cha chung.
- Đặt default policy là fail/no retry/no skip.
- Không để một rule tổng quát như `RuntimeException` nuốt mọi trường hợp.
- Nếu xét cause chain, định nghĩa rõ ưu tiên exception ngoài cùng và nguyên nhân bên trong.
- Kiểm thử exception kế thừa nhiều cấp và exception bị wrapper.

## 13. Classifier không phải listener

Classifier và listener đều có thể được gọi khi exception xảy ra, nhưng trách nhiệm khác nhau:

| Thành phần | Vai trò |
|---|---|
| Exception classifier | Phân loại exception hoặc chọn policy. |
| RetryPolicy | Quyết định retry còn được phép hay không. |
| SkipPolicy | Quyết định item lỗi có được bỏ qua hay không. |
| RetryListener | Quan sát retry operation và các lần thử lỗi. |
| SkipListener | Ghi nhận item thực sự bị skip. |
| StepExecutionListener | Quan sát trạng thái trước/sau Step. |

Không đặt quyết định retry trong `RetryListener.onError` hoặc quyết định skip trong `SkipListener`. Listener phù hợp để logging, metrics và audit; classifier/policy mới quyết định hành vi fault tolerance.

## 14. Thread safety và hiệu năng

Classifier có thể được gọi nhiều lần và từ nhiều thread nếu Step chạy song song hoặc nhiều Job sử dụng chung bean. Vì vậy:

- Ưu tiên classifier stateless và thread-safe.
- Không lưu exception hiện tại vào field mutable của singleton.
- Không gọi database hoặc HTTP trong `classify`.
- Không phân tích stack trace hoặc message dài nếu không cần thiết.
- Giữ map policy bất biến sau khi khởi tạo.
- Dùng `RetryContext` hoặc context của execution cho state thuộc một operation, không dùng field dùng chung.

Classification thường là thao tác nhỏ trên mỗi exception. Tuy nhiên, retry/skip có thể làm classifier được gọi nhiều lần trong một chunk. Giữ logic xác định và nhanh giúp tránh làm tăng độ trễ xử lý lỗi.

## 15. Logging và metrics theo nhóm exception

Sau khi phân loại, ứng dụng có thể ghi nhận số lỗi theo nhóm để theo dõi chất lượng dữ liệu và sức khỏe hạ tầng.

Các metric hữu ích:

- Số lần retry theo exception category.
- Số item bị skip theo loại lỗi và giai đoạn read/process/write.
- Số Step thất bại theo nhóm lỗi.
- Số lần retry exhaustion.
- Thời gian phục hồi trung bình sau lỗi transient.

Nên dùng tag có cardinality thấp như Job name, Step name, exception category. Không dùng customer ID, order ID hoặc message tùy ý làm metric tag vì có thể tạo số lượng time series rất lớn.

Log nên có JobExecution ID, StepExecution ID, loại exception và business key được phép ghi nhận. Tránh log password, token, dữ liệu cá nhân hoặc payload đầy đủ.

## 16. Kiểm thử exception classifier

Classifier cần được kiểm thử độc lập vì một nhầm lẫn nhỏ có thể làm dữ liệu bị bỏ qua hoặc một lỗi tạm thời không được retry.

Các trường hợp nên kiểm tra:

- Exception dữ liệu được phân loại thành skip.
- Exception transient được phân loại thành retry.
- Exception fatal không bị retry hoặc skip.
- Exception không biết rơi vào default policy an toàn.
- Exception con được phân loại theo rule cụ thể thay vì lớp cha quá rộng.
- Exception bị wrapper vẫn được xử lý theo quy tắc cause chain đã chọn.
- Skip limit được áp dụng đúng tại giá trị biên.
- Retry max attempts và backoff đúng cấu hình.
- Classifier dùng đồng thời bởi nhiều thread không lẫn state.

Ví dụ unit test cho classifier đơn giản:

```java
class BatchExceptionClassifierTest {

    private final BatchExceptionClassifier classifier =
            new BatchExceptionClassifier();

    @Test
    void classifiesInvalidRecordAsDataError() {
        assertEquals(
                FailureKind.INVALID_DATA,
                classifier.classify(new InvalidRecordException("bad row")));
    }

    @Test
    void classifiesTransientDatabaseFailure() {
        assertEquals(
                FailureKind.TRANSIENT_INFRASTRUCTURE,
                classifier.classify(new TransientDataAccessException("timeout") { }));
    }

    @Test
    void unknownExceptionIsNotAutomaticallyRetryable() {
        assertEquals(
                FailureKind.UNKNOWN,
                classifier.classify(new IllegalStateException("unexpected")));
    }
}
```

Các class exception trong ví dụ là class domain hoặc Spring exception tương ứng của ứng dụng. Integration test ở cấp Step cần xác nhận classifier/policy thực sự ảnh hưởng đến retry count, skip count, transaction rollback và BatchStatus như mong đợi.

## 17. Những lỗi thường gặp

### Phân loại mọi RuntimeException là retryable

Nhiều lỗi lập trình và lỗi dữ liệu cũng là unchecked exception. Retry chúng có thể lặp lại cùng một lỗi mà không có khả năng phục hồi. Chỉ retry loại lỗi có tính tạm thời.

### Skip mọi exception chưa biết

Điều này khiến lỗi hạ tầng hoặc lỗi lập trình bị che giấu. Default classifier nên fail/no skip/no retry cho exception chưa được nhận diện.

### Kiểm tra lớp cha trước exception cụ thể

Một rule tổng quát có thể bắt mất các nhánh cụ thể. Hãy ưu tiên exception domain cụ thể và kiểm thử thứ tự phân loại.

### Chỉ kiểm tra exception ngoài cùng

Exception bị wrapper có thể che nguyên nhân. Quyết định rõ có cần duyệt cause chain hay không; đừng mặc định mọi classifier tự động xét root cause.

### Dựa vào message để nhận diện lỗi

Message có thể thay đổi theo driver, locale hoặc phiên bản. Ưu tiên class, SQL state, vendor code hoặc exception domain.

### Nhầm classifier với listener

Listener quan sát sự kiện; classifier/policy quyết định hành vi. Không đặt logic quyết định skip/retry trong listener.

### Dùng chung state mutable trong classifier

Classifier singleton có thể được gọi đồng thời. Giữ classifier stateless hoặc dùng cấu trúc thread-safe.

### Bỏ qua tính idempotent khi retry

Classifier có thể chọn retry đúng nhưng thao tác bên trong vẫn tạo side effect trùng. Writer và service ngoài cần idempotency key, unique key hoặc outbox.

## 18. Quy trình thiết kế exception classifier

Khi xây dựng fault-tolerance policy, có thể thực hiện theo trình tự:

1. Liệt kê exception có thể phát sinh ở reader, processor và writer.
2. Phân biệt lỗi dữ liệu riêng của item, lỗi tạm thời, lỗi cấu hình và lỗi nghiêm trọng.
3. Tạo exception domain cụ thể ở tầng nghiệp vụ khi exception kỹ thuật quá tổng quát.
4. Chọn cách phân loại đơn giản bằng `.retry(...)`, `.skip(...)`, `.noSkip(...)` nếu đủ.
5. Dùng `ExceptionClassifierRetryPolicy` khi mỗi nhóm cần retry policy riêng.
6. Dùng custom `SkipPolicy` hoặc exception classifier skip khi cần quy tắc skip phức tạp.
7. Đặt default là không retry/không skip cho exception chưa biết.
8. Xác định cách xử lý wrapper/cause chain và thứ tự ưu tiên exception cụ thể.
9. Kiểm tra transaction rollback và tính idempotent của thao tác được retry.
10. Bổ sung listener, log và metric để quan sát nhưng không dùng listener thay policy.
11. Kiểm thử exception hierarchy, retry exhaustion, skip limit và concurrency.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Một vài exception có cùng retry limit | `.retry(...)` và `.retryLimit(...)` |
| Mỗi loại exception có retry policy riêng | `ExceptionClassifierRetryPolicy` |
| Một vài exception dữ liệu được bỏ qua | `.skip(...)`, `.noSkip(...)`, `.skipLimit(...)` |
| Quy tắc skip dựa trên nhiều điều kiện | Custom `SkipPolicy` hoặc classifier skip policy |
| Quan sát từng lần retry | `RetryListener` |
| Ghi nhận item bị skip | `SkipListener` |
| Một exception không nên rollback transaction | `.noRollback(...)`, sau khi xác minh tính nhất quán |

## Kết luận

Exception classifier ánh xạ exception sang nhóm lỗi hoặc policy để Spring Batch xử lý phù hợp. Dùng cấu hình `.retry(...)`, `.skip(...)`, `.noSkip(...)` và `.noRollback(...)` cho các quy tắc đơn giản; dùng `ExceptionClassifierRetryPolicy` hoặc custom `SkipPolicy` khi mỗi nhóm exception cần chính sách khác nhau. Hãy ưu tiên exception type hoặc mã lỗi có cấu trúc, xử lý rõ exception hierarchy và cause chain, đặt default là fail khi chưa biết nguyên nhân, đồng thời kiểm thử retry/skip limit và bảo đảm thao tác được retry là idempotent. Classifier quyết định cách phân loại; listener chỉ quan sát và ghi nhận sự kiện.
