# Skip limit và retry limit

Trong Spring Batch, `skipLimit` và `retryLimit` là hai giới hạn quan trọng khi cấu hình fault tolerance cho một chunk-oriented Step. `skipLimit` giới hạn số item mà Step được phép bỏ qua do lỗi. `retryLimit` giới hạn số lần thử lại một thao tác gặp exception được phân loại là retryable.

Hai giới hạn này giải quyết hai tình huống khác nhau. Retry phù hợp với lỗi tạm thời có khả năng tự phục hồi, chẳng hạn deadlock hoặc dịch vụ bên ngoài tạm thời không khả dụng. Skip phù hợp với lỗi gắn với một item mà nghiệp vụ cho phép loại khỏi kết quả, chẳng hạn một dòng file sai định dạng. Khi một exception vừa retryable vừa skippable, Spring Batch ưu tiên retry; nếu retry đã hết giới hạn mà lỗi vẫn xảy ra, skip policy mới quyết định có thể bỏ qua item hay không.

## 1. Skip limit là gì?

`skipLimit` quy định tổng số item được phép skip trong một Step. Một item chỉ được tính là skip khi exception phát sinh thuộc loại được cấu hình skippable và chính sách cho phép bỏ qua.

Ví dụ:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(10)
```

Với cấu hình trên, Step có thể bỏ qua tối đa 10 item gặp `FlatFileParseException`. Khi cần skip item thứ 11, Step vượt giới hạn và kết thúc thất bại.

Skip limit là giới hạn tổng cho cả ba giai đoạn đọc, xử lý và ghi; nó không phải một ngân sách riêng cho từng giai đoạn.

| Giai đoạn | Counter | Ví dụ |
|---|---|---|
| Read | `readSkipCount` | Dòng file không thể parse |
| Process | `processSkipCount` | Đơn hàng vi phạm quy tắc dữ liệu |
| Write | `writeSkipCount` | Một item bị writer từ chối theo chính sách skip |

Tổng số skip của Step được phản ánh qua `skipCount`. Nếu `skipLimit(10)`, tổng skip từ cả ba counter không được vượt quá 10. Ví dụ, Step đã skip 6 lỗi đọc và 4 lỗi xử lý thì đã dùng hết giới hạn. Nếu writer cần skip thêm một item, Step sẽ vượt giới hạn.

Khi không cấu hình skip limit, mặc định Step không cho phép skip item. Cần cấu hình rõ cả loại exception được skip và giới hạn tổng nếu nghiệp vụ chấp nhận bỏ dữ liệu.

## 2. Retry limit là gì?

`retryLimit` quy định giới hạn thử lại cho các exception được phân loại là retryable. Retry hữu ích khi lỗi có thể biến mất nếu thực hiện lại, ví dụ:

- Database deadlock hoặc lock contention tạm thời.
- HTTP 503 hoặc timeout ngắn từ một dịch vụ phụ thuộc.
- Lỗi kết nối có thể phục hồi sau một khoảng chờ.
- Một số lỗi tài nguyên tạm thời trong quá trình ghi.

Ví dụ cấu hình:

```java
.faultTolerant()
.retry(DeadlockLoserDataAccessException.class)
.retryLimit(3)
```

Trong ví dụ, lỗi deadlock thuộc nhóm retryable và framework được phép thử lại theo giới hạn đã đặt. `retryLimit` áp dụng cho lần xử lý bị lỗi theo retry policy, không phải số item tối đa trong Step và cũng không phải số lần rollback tổng thể của Step.

Lần gọi đầu tiên và các lần retry là những khái niệm khác nhau. Cách đếm tổng số lần gọi phụ thuộc retry policy/API của phiên bản Spring Batch và Spring Retry mà dự án sử dụng; khi cần xác định chính xác số invocation, hãy quan sát bằng `RetryListener` hoặc kiểm thử trên đúng phiên bản. Điều quan trọng trong thiết kế là đặt một giới hạn hữu hạn và hiểu retry policy đang áp dụng cho exception nào.

Khi không cấu hình retry, lỗi không được tự động thử lại chỉ vì nó có vẻ tạm thời. Cần khai báo exception retryable và retry limit rõ ràng.

## 3. So sánh skipLimit và retryLimit

| Tiêu chí | `skipLimit` | `retryLimit` |
|---|---|---|
| Kiểm soát | Tổng số item được phép bỏ qua | Số lần thử lại cho lỗi retryable |
| Đơn vị ý nghĩa | Item bị skip trong Step | Lần retry của một thao tác/item theo policy |
| Mục tiêu | Chấp nhận loại bỏ item lỗi theo nghiệp vụ | Phục hồi từ lỗi tạm thời |
| Khi vượt giới hạn | Step thất bại khi cần skip thêm | Không retry thêm; lỗi tiếp tục được xét theo skip policy hoặc làm Step thất bại |
| Phạm vi | Read, process và write | Tùy điểm phát sinh lỗi và retry policy |
| Kết quả thành công | Item bị bỏ qua và Step tiếp tục nếu còn skip budget | Thao tác thành công ở lần thử lại, item vẫn được xử lý |

Hai giới hạn không thay thế nhau. Một lỗi có thể được retry nhưng không được skip; nếu retry hết giới hạn, Step thất bại. Một lỗi khác có thể không retry nhưng được skip ngay nếu nghiệp vụ cho phép. Một exception có thể vừa retryable vừa skippable; khi đó retry được áp dụng trước, rồi mới xét skip nếu retry không thành công.

## 4. Cấu hình kết hợp skip và retry

Ví dụ Job nhập đơn hàng từ file:

- Lỗi parse dòng file được phép skip.
- Đơn hàng không hợp lệ được phép skip theo nghiệp vụ.
- Database deadlock được retry.
- Lỗi kết nối database kéo dài không được skip; khi retry hết giới hạn, Step phải thất bại.

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(DeadlockLoserDataAccessException.class)
            .retryLimit(3)
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .build();
}
```

`DeadlockLoserDataAccessException` chỉ được cấu hình retry. Nếu lỗi vẫn xảy ra sau khi retry policy hết lượt, nó không được skip và Step thất bại. `FlatFileParseException` và `InvalidOrderException` được cấu hình skippable; nếu tổng skip chưa vượt 50, Step có thể tiếp tục.

Các exception trên chỉ là ví dụ. Hãy chọn exception cụ thể do reader, processor, writer hoặc client thực tế ném ra. Không nên copy một danh sách exception chung mà chưa xác định lỗi đó có thể phục hồi hay có được phép bỏ qua về mặt nghiệp vụ hay không.

## 5. Khi một exception vừa retryable vừa skippable

Một exception có thể được khai báo trong cả retry policy và skip policy. Trong trường hợp đó, Spring Batch thử lại trước. Nếu thao tác thành công ở lần retry, item được xử lý bình thường và không bị tính là skip. Nếu retry đã hết giới hạn mà exception vẫn xảy ra, framework kiểm tra skip policy; nếu exception skippable và còn skip budget, item được bỏ qua.

Ví dụ:

```java
.faultTolerant()
.retry(TransientImportException.class)
.retryLimit(2)
.skip(TransientImportException.class)
.skipLimit(10)
```

Với cấu hình minh họa, `TransientImportException` được thử lại theo retry policy. Nếu các lần thử vẫn thất bại, item có thể bị skip nếu giới hạn skip của Step chưa bị vượt.

Hãy cân nhắc kỹ việc vừa retry vừa skip một loại exception. Nếu lỗi thực sự là hạ tầng đang ngừng hoạt động, skip có thể làm mất dữ liệu. Nếu lỗi là một bản ghi không thể xử lý, retry thường chỉ kéo dài thời gian mà không tăng khả năng thành công. Chính sách cần phản ánh nguyên nhân lỗi.

## 6. Skip limit được tính chung cho read, process và write

Skip limit là ngân sách tổng của Step, không reset khi chuyển từ read sang process hoặc write.

Giả sử `skipLimit(5)`:

| Giai đoạn | Skip mới | Tổng skip sau giai đoạn |
|---|---:|---:|
| Read | 2 | 2 |
| Process | 1 | 3 |
| Write | 2 | 5 |
| Write tiếp theo | 1 | 6 — vượt giới hạn |

Khi cần skip item thứ sáu, Step vượt `skipLimit(5)` và thất bại. Các counter riêng giúp xác định lỗi xảy ra ở đâu, nhưng giới hạn vẫn áp dụng trên tổng.

Điều này có ý nghĩa khi đánh giá chất lượng dữ liệu. Một Step có thể skip ít lỗi đọc nhưng nhiều lỗi xử lý; nếu chỉ nhìn từng counter riêng lẻ, người vận hành có thể không nhận ra tổng skip đã chạm ngưỡng.

## 7. Phân loại exception: retryable, skippable hay fatal

Trước khi cấu hình limit, cần phân loại lỗi theo khả năng phục hồi và quyết định nghiệp vụ.

| Loại lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Transient | Deadlock, HTTP 503, timeout ngắn | Retry có giới hạn, có thể backoff |
| Dữ liệu cá biệt không hợp lệ | Ngày sai định dạng, mã không tồn tại | Skip nếu nghiệp vụ chấp nhận; nếu không thì fail |
| Cấu hình | Thiếu tham số bắt buộc, sai tên bảng | Fail sớm; retry thường không giúp ích |
| Hạ tầng kéo dài | Database unavailable, broker mất kết nối lâu | Retry có giới hạn rồi fail; thường không skip |
| Lỗi lập trình | Null pointer, invariant bị phá vỡ | Fail và sửa lỗi; tránh skip rộng |

Một quy tắc hữu ích:

- Retry khi cùng một thao tác có cơ hội thành công sau khi điều kiện bên ngoài thay đổi.
- Skip khi bỏ riêng item đó là chấp nhận được về mặt nghiệp vụ.
- Fail khi không thể bảo đảm tính đúng đắn nếu tiếp tục.

Không nên dùng `retry(Exception.class)` hoặc `skip(Exception.class)` một cách rộng rãi. Các cấu hình này có thể bắt cả lỗi không thể phục hồi hoặc lỗi hệ thống nghiêm trọng.

## 8. Dùng noRetry và noSkip để loại trừ exception

Spring Batch cho phép khai báo các exception cần loại khỏi retry hoặc skip policy. Điều này hữu ích khi dùng một exception cha làm mặc định nhưng một số subclass cần xử lý khác.

Ví dụ, cho phép skip phần lớn lỗi dữ liệu nhưng không skip lỗi thiếu file:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(FileNotFoundException.class)
.skipLimit(20)
```

Ví dụ retry phần lớn lỗi truy cập dữ liệu nhưng không retry lỗi cấu hình:

```java
.faultTolerant()
.retry(DataAccessException.class)
.noRetry(BadSqlGrammarException.class)
.retryLimit(3)
```

Đây là cấu hình minh họa cho exception hierarchy. Cần kiểm tra loại exception thực tế và classifier mà phiên bản Spring Batch sử dụng. Một lỗi cụ thể có thể bị bọc trong exception khác; hãy xem root cause và thứ tự phân loại để tránh chính sách không như dự định.

Khi cấu hình rộng rồi loại trừ, hãy ghi rõ lý do cho từng `noSkip` hoặc `noRetry`. Trong nhiều hệ thống, khai báo trực tiếp các exception cần xử lý thường dễ hiểu và ít rủi ro hơn.

## 9. Retry và skip ở giai đoạn đọc

Reader có thể ném exception khi đọc file, parse dữ liệu hoặc truy vấn database. Nếu lỗi tạm thời như lỗi kết nối có thể phục hồi, có thể cấu hình retry cho exception đó. Nếu một dòng file sai định dạng và được phép loại bỏ, có thể cấu hình skip.

Ví dụ:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(FlatFileParseException.class)
.skipLimit(25)
```

Với read-skip, không có item hợp lệ được trả về từ lần đọc lỗi; reader cần có khả năng tiến đến bản ghi tiếp theo theo contract của implementation. Với file reader tích hợp sẵn, framework có thể nhận diện vị trí dòng lỗi và tiếp tục. Với custom reader, cần thiết kế hành vi sau exception rõ ràng để không lặp vô hạn tại cùng một vị trí hoặc bỏ qua sai nhiều bản ghi.

Nếu reader đọc từ transactional queue, rollback có thể làm message được broker phát lại. Cần phân biệt skip của item với redelivery của message và cấu hình transaction/reader đúng.

## 10. Retry và skip ở giai đoạn xử lý

Processor có thể ném exception khi validate hoặc biến đổi item. Ví dụ, đơn hàng có số tiền âm không hợp lệ:

```java
public class ValidateOrderProcessor implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (order.getAmount().signum() < 0) {
            throw new InvalidOrderException(
                    "Negative amount for order " + order.getId()
            );
        }

        return order;
    }
}
```

Nếu `InvalidOrderException` thuộc skip policy, item có thể bị bỏ qua. Nếu processor gọi một dịch vụ ngoài và nhận timeout tạm thời, có thể retry nếu thao tác đó an toàn khi gọi lại.

Processor nên tránh side effect không idempotent. Khi retry hoặc rollback làm processor được gọi lại, việc gửi email, tạo giao dịch hoặc tăng counter trong field có thể xảy ra nhiều lần. Ưu tiên processor stateless và để side effect trong writer hoặc một cơ chế có transaction/idempotency rõ ràng.

## 11. Retry và skip ở giai đoạn ghi

Writer thường nhận cả chunk. Nếu một item làm writer ném exception, transaction chunk có thể rollback. Với retry, framework có thể gọi lại thao tác ghi; với write-skip, framework có thể chia nhỏ tập item để xác định item gây lỗi, tùy cấu hình và loại writer.

Ví dụ:

```java
.faultTolerant()
.retry(DeadlockLoserDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(20)
```

Writer cần chịu được việc được gọi lại. Nếu ghi database bằng cùng transaction manager, rollback có thể hoàn tác phần ghi chưa commit. Nếu writer gửi message, gọi HTTP API hoặc ghi file ngoài transaction, rollback không tự thu hồi side effect đã xảy ra.

Với đích ghi ngoài transaction, hãy dùng idempotency key, unique constraint, outbox hoặc staging. Không retry một writer có side effect không thể lặp an toàn chỉ vì exception có vẻ transient.

## 12. Retry limit không phải số lần rollback của Step

Một lần retry có thể kéo theo rollback transaction của chunk, nhưng `retryLimit` và `rollbackCount` không phải cùng một bộ đếm.

- Retry limit thuộc retry policy cho exception/item được phân loại.
- Rollback count là counter của transaction rollback được ghi nhận ở cấp Step.
- Một rollback có thể phát sinh vì lỗi không retryable, lỗi writer, lỗi commit hoặc nguyên nhân khác.
- Một lần retry có thể liên quan đến việc gọi lại reader/processor/writer theo cơ chế fault tolerance, không thể suy ra chính xác chỉ từ rollback count.

Nếu cần đo số lần retry thực tế, dùng `RetryListener` hoặc metric chuyên biệt. Không dùng `rollbackCount` thay cho retry count.

## 13. Backoff giữa các lần retry

Với lỗi transient, thử lại ngay lập tức nhiều lần có thể làm hệ thống đích quá tải hơn. Backoff chèn khoảng chờ giữa các lần thử, có thể tăng dần theo số lần thất bại.

Ví dụ về ý tưởng backoff:

```text
Lần retry 1: chờ 200 ms
Lần retry 2: chờ 400 ms
Lần retry 3: chờ 800 ms
```

Đây là ví dụ minh họa, không phải giá trị mặc định của Spring Batch. Có thể cấu hình `BackOffPolicy` thông qua API phù hợp với phiên bản Spring Batch/Spring Retry của dự án.

Backoff hữu ích với database contention hoặc dịch vụ HTTP có rate limit. Cần kết hợp timeout, tổng thời gian retry và thời gian tối đa của Step. Không nên đặt retry limit lớn cùng backoff dài mà không tính tổng thời gian Job có thể bị giữ.

Với HTTP 429/503, nếu dịch vụ trả `Retry-After`, client nên tôn trọng hướng dẫn đó khi phù hợp. Với lỗi dữ liệu cố định, backoff không giúp ích; nên skip hoặc fail theo quy tắc nghiệp vụ.

## 14. Listener theo dõi retry và skip

`SkipListener` giúp ghi nhận item bị bỏ qua ở từng giai đoạn:

```java
public class ImportSkipListener implements SkipListener<Order, Order> {

    @Override
    public void onSkipInRead(Throwable throwable) {
        log.warn("Skip during read: {}", throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(Order item, Throwable throwable) {
        log.warn("Skip order {} during process: {}",
                item.getId(), throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        log.warn("Skip order {} during write: {}",
                item.getId(), throwable.getMessage());
    }
}
```

Đăng ký listener:

```java
.listener(new ImportSkipListener())
```

`RetryListener` có thể quan sát các lần thử và kết quả retry. API cụ thể phụ thuộc phiên bản Spring Retry được dùng cùng Spring Batch. Hãy dùng listener để ghi nhận loại exception, item key và số lần thử; tránh tạo side effect không idempotent trong callback.

## 15. Theo dõi các counter của StepExecution

Sau khi Step hoàn tất, có thể đọc các counter để đánh giá chất lượng xử lý:

| Counter | Ý nghĩa |
|---|---|
| `readCount` | Số item đọc thành công |
| `writeCount` | Số item ghi thành công |
| `readSkipCount` | Số item bị skip khi đọc |
| `processSkipCount` | Số item bị skip khi xử lý |
| `writeSkipCount` | Số item bị skip khi ghi |
| `skipCount` | Tổng số item bị skip |
| `commitCount` | Số lần commit được ghi nhận |
| `rollbackCount` | Số lần rollback được ghi nhận |

Ví dụ listener ghi metric:

```java
public class ImportMetricsListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info("Starting step {}", stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "step={}, read={}, write={}, readSkip={}, processSkip={}, " +
                "writeSkip={}, totalSkip={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getSkipCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount()
        );

        return stepExecution.getExitStatus();
    }
}
```

`rollbackCount` không phải số retry chính xác. Muốn quan sát retry, hãy dùng RetryListener hoặc metric từ retry policy. `skipCount` là chỉ số cần so với `skipLimit`; các counter riêng giúp tìm ra giai đoạn gây lỗi.

## 16. Đặt ExitStatus khi skip vượt ngưỡng nghiệp vụ

Có trường hợp Step chưa vượt `skipLimit` nhưng số skip vẫn cao hơn ngưỡng chất lượng dữ liệu mà doanh nghiệp chấp nhận. Ví dụ, Step cho phép skip tối đa 100 item để tránh thất bại ngay, nhưng nếu có hơn 20 item bị skip thì cần review thủ công.

Có thể dùng `StepExecutionListener` để trả custom `ExitStatus` sau Step:

```java
public class SkipThresholdListener implements StepExecutionListener {

    private final int warningThreshold;

    public SkipThresholdListener(int warningThreshold) {
        this.warningThreshold = warningThreshold;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // Không cần xử lý trước Step.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > warningThreshold) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "Skip count exceeded business warning threshold"
            );
        }

        return stepExecution.getExitStatus();
    }
}
```

Job flow có thể dùng exit code này để chuyển sang Step review. Đây là ngưỡng cảnh báo nghiệp vụ, khác với `skipLimit`: `skipLimit` quyết định Step có được tiếp tục bỏ item hay phải thất bại; warning threshold quyết định Job nên đi theo nhánh nào sau khi Step hoàn tất.

## 17. Chọn limit dựa trên nghiệp vụ và dữ liệu thực tế

Không nên chọn `skipLimit` chỉ vì muốn Job luôn hoàn tất. Hãy xác định số lỗi dữ liệu có thể chấp nhận và tác động nếu bỏ qua từng loại item.

Ví dụ:

- File có 10 triệu dòng, tối đa 5 lỗi định dạng có thể được chấp nhận.
- Job đối soát tài chính không cho phép skip bất kỳ giao dịch nào; `skipLimit(0)` hoặc không cấu hình skip phù hợp hơn.
- Job nhập danh mục tham chiếu có thể chấp nhận một số mã không hợp lệ, nhưng cần báo cáo rõ danh sách bị bỏ.

Retry limit cũng nên dựa trên thời gian phục hồi thực tế của hệ thống đích. Nếu deadlock thường được giải quyết sau một lần retry ngắn, giới hạn nhỏ cùng backoff có thể đủ. Nếu dịch vụ có thời gian gián đoạn dài, cần cân nhắc timeout tổng, retry policy và khả năng restart Job sau khi fail.

Ghi nhận metric theo từng lần chạy để điều chỉnh limit. Nếu Step thường xuyên gần chạm skip limit, đó có thể là dấu hiệu chất lượng dữ liệu hoặc upstream đang có vấn đề, không đơn thuần là lý do tăng limit.

## 18. Những nhầm lẫn thường gặp

**Cho rằng `skipLimit` là giới hạn riêng cho mỗi giai đoạn.** Skip limit là tổng của read, process và write skip trong cùng Step.

**Cho rằng `retryLimit` giới hạn số item lỗi.** Retry limit kiểm soát việc thử lại thao tác/item theo retry policy; nó không phải ngân sách lỗi toàn Step.

**Cho rằng retry hết giới hạn luôn dẫn đến skip.** Chỉ khi exception thuộc skip policy và còn skip budget thì item mới được bỏ qua. Nếu không, Step thất bại.

**Cho rằng retry và skip có thể cấu hình rộng cho mọi Exception.** Điều đó có thể che giấu lỗi lập trình, cấu hình hoặc hạ tầng. Hãy phân loại exception cụ thể.

**Cho rằng skip một item không ảnh hưởng đến kết quả nghiệp vụ.** Skip làm dữ liệu đầu ra thiếu item đó. Chỉ dùng khi nghiệp vụ cho phép và có cơ chế ghi nhận.

**Dùng rollback count để đo retry.** Hai counter có ý nghĩa khác nhau. Dùng RetryListener hoặc metric retry riêng.

**Bỏ qua side effect của writer khi retry.** Writer có thể được gọi lại sau rollback. API/message/file cần idempotency hoặc cơ chế phục hồi.

**Tăng skipLimit để tránh Job thất bại.** Limit lớn có thể khiến Job hoàn tất với quá nhiều dữ liệu bị bỏ. Hãy đặt ngưỡng theo yêu cầu chất lượng.

## 19. Kiểm thử skipLimit và retryLimit

Một bộ test hữu ích nên xác nhận cả hành vi của từng item và trạng thái cuối cùng của Step:

1. Tạo một lỗi transient thất bại ở lần đầu nhưng thành công khi retry; xác nhận item được ghi và không tăng skip count.
2. Tạo một item có exception skippable nhưng không retryable; xác nhận item bị skip ngay và Step tiếp tục nếu còn skip budget.
3. Tạo exception vừa retryable vừa skippable; xác nhận retry được thực hiện trước, sau đó item mới bị skip nếu retry hết giới hạn.
4. Tạo số item skip đúng bằng `skipLimit`; xác nhận Step có thể hoàn tất nếu các item còn lại xử lý thành công.
5. Tạo thêm một item cần skip vượt limit; xác nhận Step thất bại.
6. Tạo lỗi retryable không skippable vượt retry limit; xác nhận Step thất bại thay vì âm thầm bỏ item.
7. Tạo lỗi ở read, process và write để xác nhận counter đúng giai đoạn.
8. Làm writer ghi một phần rồi ném exception; xác nhận transaction rollback hoặc idempotency ngăn dữ liệu trùng khi replay.

Với retry policy có backoff, nên dùng cấu hình test hoặc clock có thể kiểm soát để tránh chờ thời gian thực dài. Với database, hãy dùng transaction manager và database test phù hợp để xác nhận rollback thật. Với API hoặc broker, kiểm tra số side effect ở hệ thống đích chứ không chỉ xác nhận số lần method được gọi.

## 20. Cách thiết kế skip limit và retry limit

Trước hết, phân loại exception theo nguyên nhân: lỗi transient để retry, lỗi dữ liệu có thể loại bỏ để skip, lỗi cấu hình hoặc lỗi lập trình để fail. Đặt `retryLimit` hữu hạn cho các exception retryable và cân nhắc backoff khi hệ thống đích cần thời gian phục hồi. Đặt `skipLimit` theo mức lỗi dữ liệu nghiệp vụ chấp nhận, nhớ rằng đây là tổng của read, process và write skip.

Nếu một exception vừa retryable vừa skippable, hãy xác định rõ việc bỏ item sau khi retry thất bại có an toàn hay không. Theo dõi retry bằng RetryListener, skip bằng SkipListener và các counter của StepExecution. Đảm bảo writer chịu được replay và side effect ngoài transaction có idempotency.

Một cấu hình fault-tolerant tốt không nhằm làm mọi Job luôn chạy đến cuối. Nó cho phép hệ thống tự phục hồi trước lỗi tạm thời, tiếp tục khi gặp item lỗi được phép loại bỏ, và thất bại rõ ràng khi không thể bảo đảm tính đúng đắn của dữ liệu.
