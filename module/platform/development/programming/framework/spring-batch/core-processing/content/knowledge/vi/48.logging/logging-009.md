# Log retry và recovery trong Spring Batch

## 1. Mục tiêu và tình huống thực tế

Trong một batch job, lỗi không phải lúc nào cũng khiến cả job thất bại ngay. Kết nối cơ sở dữ liệu có thể timeout trong vài giây, API bên ngoài có thể tạm thời trả lỗi 503, hoặc một bản ghi nghiệp vụ có thể không hợp lệ và cần được bỏ qua theo chính sách. Spring Batch cho phép cấu hình **retry**, **skip** và xử lý sau lỗi; đồng thời có thể **restart** job khi một lần thực thi đã thất bại hoặc bị dừng.

Tuy nhiên, nếu chỉ log một dòng `ERROR` cho mỗi exception, người vận hành khó phân biệt:

- Một lỗi tạm thời đã được retry và lần sau thành công.
- Một item đã thử nhiều lần rồi được skip theo chính sách.
- Retry đã hết giới hạn, step `FAILED` và job cần restart.
- Một batch execution mới đang restart từ execution cũ.
- Một exception phát sinh nhiều lần nhưng chỉ là **một vấn đề nghiệp vụ**, không phải nhiều bản ghi lỗi độc lập.

**Log retry và recovery** phải phản ánh hành trình từ *lần thử thất bại* đến *kết quả cuối*, giúp điều tra mà không tạo hàng nghìn cảnh báo giả.

Sau bài học, bạn có thể:

1. Phân biệt retry, skip, recovery và restart trong Spring Batch Core Processing.
2. Chọn đúng listener để log từng lần retry, lần skip và kết quả của step/job.
3. Gắn các ID cần thiết để liên hệ log với `JobExecution` và `StepExecution`.
4. Cấu hình một fault-tolerant chunk step và các listener bằng Java.
5. Tránh log trùng, để lộ dữ liệu nhạy cảm hoặc ghi sai rằng một lỗi đã “recovered”.
6. Thiết kế test cho các kịch bản retry thành công, retry hết giới hạn, skip và restart.

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Batch 5.x, Spring Retry và SLF4J. Các trường dữ liệu nghiệp vụ được minh họa bằng việc xử lý bản ghi thanh toán.

## 2. Phân biệt retry, recovery, skip và restart

Các khái niệm này có mối liên hệ nhưng **không đồng nghĩa**:

| Khái niệm | Phạm vi | Điều xảy ra | Điều nên log |
| --- | --- | --- | --- |
| **Retry** | Một thao tác đọc, xử lý hoặc ghi trong step | Gọi lại thao tác sau exception được phép retry | Lỗi tạm thời, loại exception, số lần thất bại, step/execution |
| **Recovery** | Xử lý khi lỗi không còn được retry hoặc có hướng dự phòng thành công | Chọn phương án xử lý thay thế: skip, fallback, dead-letter hay kết thúc lỗi theo thiết kế | Phương án đã thực sự được áp dụng và kết quả cuối |
| **Skip** | Một item trong fault-tolerant step | Chấp nhận bỏ item lỗi nếu loại lỗi và giới hạn skip cho phép | Item key an toàn, giai đoạn read/process/write, exception class |
| **Restart** | Một JobInstance qua nhiều JobExecution | Khởi chạy một execution mới của instance chưa hoàn tất | JobInstance ID giữ nguyên, JobExecution ID thay đổi |

Ví dụ một writer gọi dịch vụ cập nhật trạng thái đơn hàng:

```text
JobInstance  301 (businessDate = 2026-11-15)
  |
  +-- JobExecution 901
       |
       +-- StepExecution 5001
            |
            +-- ghi bản ghi P-17 -> timeout (lần 1)
            +-- ghi bản ghi P-17 -> timeout (lần 2)
            +-- ghi bản ghi P-17 -> thành công (lần 3)
            |
            +-- ghi bản ghi P-18 -> lỗi dữ liệu không hợp lệ
            +-- P-18 được skip theo chính sách
            |
            +-- Step COMPLETED với số skip được ghi nhận
```

Hai lần timeout đầu là sự kiện lỗi **có retry**; chúng không tự động đồng nghĩa item cuối cùng thất bại. Item P-18 bị skip là một sự kiện kết quả khác. Ở ví dụ này, job có thể `COMPLETED` dù đã có những exception trong quá trình xử lý.

### Recovery không phải một callback duy nhất có sẵn cho mọi job

Trong Spring Retry, `RetryTemplate` có thể được cấu hình với `RecoveryCallback` để chạy khi retry cạn. Nhưng đối với **chunk step Spring Batch**, luồng sau retry phụ thuộc cấu hình fault tolerance: một item có thể được skip nếu exception skippable và `skipLimit` còn cho phép, hoặc step có thể thất bại. Không nên giả định cứ bật `.retry(...)` là có một callback `recover()` chung hoặc có dead-letter queue tự động.

Vì vậy tài liệu/log nên nói chính xác: `retry.attempt_failed`, `item.skipped`, `fallback.applied` hoặc `step.failed`, tùy sự kiện thực tế. Từ “recovered” chỉ nên dùng khi có bằng chứng xử lý thay thế thành công theo yêu cầu nghiệp vụ.

## 3. Vòng đời retry và các điểm phát log

Một thao tác trong chunk có thể đi theo luồng khái niệm:

```text
                       Thực hiện read/process/write
                                  |
                             Thành công?
                            /           \
                          Có            Không
                          |               |
                          v               v
                    Tiếp tục chunk    Exception
                                          |
                                          v
                                  Retry có áp dụng?
                                    /           \
                                  Có           Không
                                  |              |
                                  v              v
                           Còn lượt thử?     Skip được phép?
                            /      \           /       \
                          Có       Không      Có       Không
                          |          |         |          |
                       Thử lại   Xử lý sau  Bỏ item      Step FAILED
                                 retry      (skip)
                                 cạn
                                    |
                           Skip / fallback / fail
```

Sơ đồ chỉ thể hiện ý tưởng; thực tế còn phụ thuộc nơi exception phát sinh, transaction rollback, retry policy và skip policy.

Những điểm quan sát hữu ích:

| Điểm quan sát | API hoặc cơ chế | Nên ghi gì |
| --- | --- | --- |
| Mỗi lần thử gây exception | `RetryListener.onError(...)` | Sự kiện thất bại trong vòng retry, loại exception, retry count |
| Lỗi của reader/processor/writer | `ItemReadListener.onReadError`, `ItemProcessListener.onProcessError`, `ItemWriteListener.onWriteError` | Bối cảnh giai đoạn phát sinh lỗi, tránh log lặp không kiểm soát |
| Một item thực sự được skip | `SkipListener.onSkipInRead/Process/Write` | Sự kiện skip theo giai đoạn, key được phép ghi, nguyên nhân |
| Chunk có lỗi hoặc rollback | `ChunkListener.afterChunkError` và metadata step | Bối cảnh transaction/chunk, không tự kết luận job FAILED |
| Step hoàn tất | `StepExecutionListener.afterStep` | `BatchStatus`, `ExitStatus`, read/write/filter/skip/rollback counts |
| Job kết thúc | `JobExecutionListener.afterJob` | Kết quả cuối của execution và correlation IDs |
| Job được restart | Launcher/scheduler và JobRepository | Execution mới thuộc JobInstance cũ |

**Quan trọng:** `RetryListener.onError` được gọi khi một lần thử gặp exception, gồm cả lần thử cuối có thể không còn retry. Không nên viết log kiểu “retry đã thành công” hoặc “đang có thêm một lần thử” chỉ dựa trên `onError`. Muốn khẳng định thành công, cần quan sát kết quả sau đó hoặc trạng thái kết thúc phù hợp.

## 4. Những thông tin nên đưa vào log retry và recovery

Một dòng log có cấu trúc nên chứa các trường giúp gắn sự kiện với một lần thực thi cụ thể:

| Trường | Ý nghĩa |
| --- | --- |
| `event` | Loại sự kiện: `batch.retry.error`, `batch.item.skipped`, `batch.step.finished` |
| `jobName` | Tên job |
| `jobInstanceId` | Instance nghiệp vụ, giữ nguyên qua restart |
| `jobExecutionId` | Lần thực thi hiện tại |
| `stepName` và `stepExecutionId` | Bước đang xử lý |
| `businessDate` hoặc `fileId` | Khóa nghiệp vụ an toàn để phân biệt tập dữ liệu |
| `phase` | `READ`, `PROCESS`, `WRITE` |
| `retryFailureCount` | Số lần lỗi trong RetryContext hiện tại |
| `exceptionType` / `errorCode` | Loại lỗi có thể phân loại |
| `itemKey` | ID an toàn của item; có thể `NULL` khi lỗi reader chưa tạo item |
| `outcome` | Kết quả cuối: `SKIPPED`, `COMPLETED`, `FAILED`, `FALLBACK_APPLIED` |

Phân biệt rõ **số lỗi trong RetryContext** với **số attempt của toàn bộ job**. Retry count có phạm vi của một vòng retry và có thể được khởi tạo lại cho item/chunk/operation khác, hoặc thay đổi theo cách framework tổ chức stateful retry. Không cộng tùy tiện mọi retry count trong log để suy ra số lần gọi vật lý chính xác.

Ví dụ log:

```text
WARN  event=batch.retry.error job=paymentImportJob jobExecutionId=901 step=chargeStep stepExecutionId=5001 retryFailureCount=1 exceptionType=QueryTimeoutException

WARN  event=batch.retry.error job=paymentImportJob jobExecutionId=901 step=chargeStep stepExecutionId=5001 retryFailureCount=2 exceptionType=QueryTimeoutException

INFO  event=batch.item.skipped job=paymentImportJob jobExecutionId=901 step=chargeStep stepExecutionId=5001 phase=PROCESS itemKey=P-18 exceptionType=InvalidPaymentException

INFO  event=batch.step.finished job=paymentImportJob jobExecutionId=901 step=chargeStep status=COMPLETED readCount=120 writeCount=119 skipCount=1 rollbackCount=2
```

Các số trong log chỉ minh họa cách trình bày. Số rollback thực tế phụ thuộc chunk, transaction và loại lỗi; retry count không có quan hệ một-một cố định với `rollbackCount`.

## 5. Cấu hình fault-tolerant step

Giả sử hệ thống đọc các bản ghi thanh toán. Lỗi cơ sở dữ liệu tạm thời được retry; lỗi dữ liệu nghiệp vụ đã xác nhận là không hợp lệ có thể được skip trong giới hạn.

Định nghĩa mô hình minh họa:

```java
import java.math.BigDecimal;

public record PaymentRecord(
        String paymentId,
        BigDecimal amount) {
}

public class InvalidPaymentException extends RuntimeException {
    public InvalidPaymentException(String message) {
        super(message);
    }
}
```

Ví dụ cấu hình step theo phong cách Spring Batch 5.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class PaymentStepConfiguration {

    @Bean
    Step chargeStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<PaymentRecord> reader,
            ItemProcessor<PaymentRecord, PaymentRecord> processor,
            ItemWriter<PaymentRecord> writer,
            BatchRetryLogListener retryLogListener,
            BatchSkipLogListener skipLogListener,
            BatchStepLogListener stepLogListener) {

        return new StepBuilder("chargeStep", jobRepository)
            .<PaymentRecord, PaymentRecord>chunk(
                50, transactionManager
            )
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .skip(InvalidPaymentException.class)
            .skipLimit(5)
            .listener(retryLogListener)
            .listener(skipLogListener)
            .listener(stepLogListener)
            .build();
    }
}
```

Ví dụ giả định đã có các bean `ItemReader`, `ItemProcessor`, `ItemWriter` và những listener được định nghĩa ở các phần tiếp theo. Khi cấu hình thực tế, cần xác định exception từ client/JDBC có được chuyển thành `TransientDataAccessException` hay không; framework chỉ áp dụng chính sách retry cho exception khớp quy tắc được cấu hình.

Trong đoạn cấu hình:

- `retry(TransientDataAccessException.class)` chỉ định nhóm lỗi tạm thời phù hợp để thử lại.
- `retryLimit(3)` đặt giới hạn cho cơ chế retry của step; hãy kiểm tra hành vi số lần gọi thực tế với phiên bản và retry policy đang sử dụng, thay vì suy ra một con số từ log.
- `skip(InvalidPaymentException.class)` cho phép loại bản ghi nghiệp vụ lỗi khi exception được nhận dạng ở giai đoạn thích hợp.
- `skipLimit(5)` giới hạn tổng số skip được cho phép trong một StepExecution; khi vượt giới hạn, step thường thất bại.
- Các listener quan sát lỗi và kết quả, không thay thế retry/skip policy.

**Lưu ý về recovery:** Một exception không nằm trong nhóm được skip vẫn có thể làm step `FAILED` sau khi retry hết giới hạn. Không có logic tự động đưa mọi lỗi thất bại vào dead-letter queue. Muốn lưu bản ghi lỗi để xử lý thủ công, cần thiết kế writer/skip sink phù hợp và tính đến transaction.

## 6. Ghi log từng lần retry bằng RetryListener

Spring Batch tích hợp Spring Retry cho fault tolerance. `org.springframework.retry.RetryListener` cho phép quan sát callback trong vòng retry.

Một implementation chỉ lưu log, không giữ biến trạng thái giữa các lần chạy:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.StepContext;
import org.springframework.batch.core.scope.context.StepSynchronizationManager;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;
import org.springframework.stereotype.Component;

@Component
public class BatchRetryLogListener implements RetryListener {

    private static final Logger log =
        LoggerFactory.getLogger(BatchRetryLogListener.class);

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        StepContext stepContext =
            StepSynchronizationManager.getContext();

        if (stepContext == null) {
            log.warn(
                "event=batch.retry.error retryFailureCount={} " +
                "exceptionType={} step=unknown",
                context.getRetryCount(),
                throwable.getClass().getSimpleName()
            );
            return;
        }

        StepExecution step = stepContext.getStepExecution();

        log.warn(
            "event=batch.retry.error job={} jobInstanceId={} " +
            "jobExecutionId={} step={} stepExecutionId={} " +
            "retryFailureCount={} exceptionType={}",
            step.getJobExecution().getJobInstance().getJobName(),
            step.getJobExecution().getJobInstance().getInstanceId(),
            step.getJobExecutionId(),
            step.getStepName(),
            step.getId(),
            context.getRetryCount(),
            throwable.getClass().getSimpleName()
        );
    }
}
```

Ở đây, `RetryContext.getRetryCount()` biểu diễn số lần lỗi mà context ghi nhận. Trong cơ chế RetryListener thông thường, `onError` được gọi sau một lần thử có exception; nhưng đừng coi giá trị này là một bộ đếm bền vững của toàn bộ StepExecution.

`StepSynchronizationManager.getContext()` giúp lấy bối cảnh step trên thread hiện tại. Nó có thể không có ở một test gọi listener trực tiếp, hoặc ở mã chạy ngoài scope mà Spring Batch quản lý. Ví dụ đã xử lý trường hợp context là `null`.

**Không dùng RetryListener làm nơi quyết định retry.** Listener chỉ nên quan sát; cho phép framework áp dụng retry/skip policy. Một listener ném exception hoặc gọi dịch vụ ngoài chậm có thể ảnh hưởng đến step, do đó logic ghi log nên ngắn và an toàn.

### Có thể log item key ở đây không?

Một `RetryListener` tổng quát thường không trực tiếp nhận `PaymentRecord` trong callback. Không nên lấy khóa bản ghi bằng cách ép kiểu `RetryCallback` hoặc phụ thuộc vào cấu trúc nội bộ không được bảo đảm. Nếu cần correlation ở cấp item, có thể bổ sung ID ở processor/writer với dữ liệu đã được kiểm soát hoặc log sự kiện skip nơi listener nhận item. Với xử lý đa luồng, tránh lưu “item đang xử lý” vào field của singleton bean vì dễ lẫn giữa các thread.

## 7. Ghi log recovery ở đường skip bằng SkipListener

Khi một item **thực sự bị skip**, Spring Batch gọi callback của `SkipListener` theo giai đoạn. Đây là nơi thích hợp để log kết quả xử lý item lỗi.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;
import org.springframework.stereotype.Component;

@Component
public class BatchSkipLogListener
        implements SkipListener<PaymentRecord, PaymentRecord> {

    private static final Logger log =
        LoggerFactory.getLogger(BatchSkipLogListener.class);

    @Override
    public void onSkipInRead(Throwable throwable) {
        // Lỗi đọc có thể xảy ra trước khi tạo được PaymentRecord.
        log.warn(
            "event=batch.item.skipped phase=READ " +
            "exceptionType={}",
            throwable.getClass().getSimpleName()
        );
    }

    @Override
    public void onSkipInProcess(
            PaymentRecord item,
            Throwable throwable) {

        log.warn(
            "event=batch.item.skipped phase=PROCESS " +
            "itemKey={} exceptionType={}",
            item.paymentId(),
            throwable.getClass().getSimpleName()
        );
    }

    @Override
    public void onSkipInWrite(
            PaymentRecord item,
            Throwable throwable) {

        log.warn(
            "event=batch.item.skipped phase=WRITE " +
            "itemKey={} exceptionType={}",
            item.paymentId(),
            throwable.getClass().getSimpleName()
        );
    }
}
```

Trong ví dụ, `paymentId` được giả định là một khóa được phép xuất hiện trong log. Nếu khóa gốc chứa dữ liệu cá nhân hoặc thông tin nhạy cảm, hãy dùng mã tham chiếu nội bộ, giá trị đã băm theo chính sách hoặc bỏ trường này.

Sự kiện `onSkipInRead` không có item để nhận diện vì lỗi có thể xảy ra trước khi reader ánh xạ thành công một đối tượng. Nếu cần biết số dòng file hay khóa nguồn, hãy bổ sung thông tin từ reader hoặc adapter theo cách riêng của ứng dụng.

Một điểm vận hành: callback skip được thiết kế để chạy gần thời điểm hoàn tất xử lý chunk và trước commit. Không nên xem một log gửi ra hệ thống bên ngoài là bằng chứng rằng giao dịch dữ liệu cuối cùng đã commit thành công. Nếu việc ghi nhận item bị loại phải **bền vững và nhất quán với transaction**, hãy thiết kế bảng lỗi/outbox trong cùng transaction phù hợp, sau đó phát sự kiện ra ngoài theo cơ chế có thể retry và không gây trùng.

### Filter và skip khác nhau

Processor có thể trả về `null` để lọc bản ghi không cần xử lý. Khi đó Spring Batch tăng `filterCount`, không mặc định gọi `SkipListener` hay tiêu thụ `skipLimit`. Nếu nghiệp vụ muốn phân biệt “không cần xử lý” với “bản ghi lỗi”, phải chủ động thiết kế hai đường kết quả và hai loại log tương ứng.

## 8. Ghi kết quả cuối tại StepExecutionListener

Khi xem nhiều log retry, câu hỏi quan trọng nhất là **step cuối cùng đã ra sao**. StepExecution chứa trạng thái và các bộ đếm chuẩn để trả lời.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class BatchStepLogListener implements StepExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(BatchStepLogListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
            "event=batch.step.finished jobExecutionId={} " +
            "step={} stepExecutionId={} status={} exitCode={} " +
            "readCount={} writeCount={} filterCount={} " +
            "readSkipCount={} processSkipCount={} " +
            "writeSkipCount={} commitCount={} rollbackCount={}",
            step.getJobExecutionId(),
            step.getStepName(),
            step.getId(),
            step.getStatus(),
            step.getExitStatus().getExitCode(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getFilterCount(),
            step.getReadSkipCount(),
            step.getProcessSkipCount(),
            step.getWriteSkipCount(),
            step.getCommitCount(),
            step.getRollbackCount()
        );

        // Không thay đổi ExitStatus đã được Spring Batch xác định.
        return null;
    }
}
```

Để tránh biến báo cáo thành “job thành công” một cách sai lệch, nên kiểm tra đồng thời `BatchStatus` và `ExitStatus`.

Các bộ đếm có ý nghĩa:

| Trường | Mô tả |
| --- | --- |
| `readCount` | Số item reader đọc thành công theo metadata step |
| `writeCount` | Số item được ghi theo thống kê Spring Batch |
| `filterCount` | Số item bị processor lọc bằng cách trả về `null` |
| `readSkipCount` | Lỗi đọc được skip |
| `processSkipCount` | Lỗi xử lý được skip |
| `writeSkipCount` | Lỗi ghi được skip |
| `commitCount` | Số lần commit được ghi nhận |
| `rollbackCount` | Số lần rollback được ghi nhận |

**Không có một `StepExecution.getRetryCount()` tổng quát** để kết luận “toàn bộ step đã retry N lần”. Các vòng retry cần được đo bằng listener/metric riêng nếu nghiệp vụ cần thống kê số lỗi tạm thời hoặc số lần gọi lại thao tác. Ngay cả khi có metric retry, cần định nghĩa phạm vi theo operation và trạng thái, đặc biệt với stateful retry và rollback.

## 9. Recovery sau khi hết retry: các đường đi cần log khác nhau

Khi retry không giải quyết được lỗi, có nhiều cách hệ thống có thể xử lý.

### 9.1. Skip item nếu policy cho phép

Ví dụ một lỗi nghiệp vụ thuộc nhóm có thể bỏ qua và chưa vượt `skipLimit`: step bỏ item đó và tiếp tục. Log tại `SkipListener` thể hiện kết quả skip; log step cho biết tổng số skip và trạng thái cuối.

Không nên ghi “recovered” tại lần cuối `RetryListener.onError` rồi đoán step sẽ skip. Quyết định skip phụ thuộc chính sách được áp dụng sau lỗi và trạng thái giới hạn.

### 9.2. Fallback hoặc dead-letter theo thiết kế riêng

Một nghiệp vụ có thể định nghĩa rằng sau khi gọi dịch vụ ngoài quá số lần cho phép, bản ghi phải được chuyển sang bảng chờ xử lý thủ công hoặc dead-letter queue.

Điều này **không tự xảy ra** khi chỉ cấu hình `.retry(...)`. Phải triển khai đường fallback/dead-letter rõ ràng, đảm bảo idempotency và quyết định điều gì được xem là “đã xử lý”.

Khi có đường xử lý thay thế thành công, nên log:

```text
event=batch.recovery.applied
jobExecutionId=901
step=chargeStep
itemKey=P-18
strategy=QUARANTINE
outcome=COMMITTED
errorCode=REMOTE_TIMEOUT
```

Các trường ở đây là quy ước log của ứng dụng, không phải thuộc tính Spring Batch tự sinh. Đặc biệt, chỉ ghi `outcome=COMMITTED` khi có cơ chế xác minh giao dịch đã commit, không phải ngay khi vừa gọi một API ghi dữ liệu.

### 9.3. Step thất bại và job được restart

Nếu retry cạn và exception không thể skip, step có thể chuyển sang `FAILED`. `StepExecutionListener.afterStep` và `JobExecutionListener.afterJob` là những nơi log kết quả cuối. Lần chạy sau với cùng identifying parameters có thể tạo JobExecution mới nếu job hỗ trợ restart.

```text
JobInstance 301
  JobExecution 901 -> FAILED
  JobExecution 902 -> COMPLETED (restart)

stepExecutionId và retry contexts thuộc từng execution riêng.
```

Restart khác retry trong cùng execution. Không nên cộng RetryContext giữa các execution và gọi đó là số lần “retry item” chung mà không định nghĩa một mô hình tổng hợp chính thức.

## 10. RecoveryCallback của Spring Retry và Spring Batch

Nếu ứng dụng dùng `RetryTemplate` trực tiếp bên ngoài cơ chế fault-tolerant chunk, có thể khai báo `RecoveryCallback` để định nghĩa rõ đường xử lý khi retry đã hết:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.support.RetryTemplate;

public class RemoteLookupService {

    private static final Logger log =
        LoggerFactory.getLogger(RemoteLookupService.class);

    private final RetryTemplate retryTemplate =
        RetryTemplate.builder()
            .maxAttempts(3)
            .retryOn(TransientDataAccessException.class)
            .build();

    public String lookupWithFallback(String paymentId) {
        return retryTemplate.execute(
            context -> requestRemoteStatus(paymentId),
            context -> {
                Throwable last = context.getLastThrowable();

                log.error(
                    "event=remote.lookup.recovered paymentKey={} " +
                    "strategy=MANUAL_REVIEW errorType={}",
                    paymentId,
                    last == null
                        ? "UNKNOWN"
                        : last.getClass().getSimpleName()
                );

                return "MANUAL_REVIEW";
            }
        );
    }

    private String requestRemoteStatus(String paymentId) {
        // TODO: Gọi dịch vụ thật, có thể ném exception được retry.
        return "PAID";
    }
}
```

Trong ví dụ, `MANUAL_REVIEW` là **kết quả dự phòng do ứng dụng tự định nghĩa**; nó không có nghĩa giao dịch thanh toán đã thành công. Khi áp dụng trong Batch processor, phải kiểm tra giá trị trả về có dẫn đến writer ghi trạng thái phù hợp hay không.

**Tránh retry lồng nhau không kiểm soát.** Nếu một `RetryTemplate` bên trong processor thử tối đa 3 lần, trong khi Spring Batch cũng retry processor 3 lần, một lỗi kéo dài có thể tạo ra nhiều lời gọi đến dịch vụ hơn dự kiến. Nên chọn rõ tầng chịu trách nhiệm retry, giới hạn timeout và tính tổng số lần gọi có thể phát sinh.

## 11. Stateful retry, rollback và log trùng

Spring Batch xử lý chunk trong các transaction. Tùy vị trí lỗi và chính sách, một item/chunk có thể được xử lý lại, transaction có thể rollback, reader có thể đọc lại dữ liệu, hoặc retry state được duy trì qua những lần xử lý.

Do đó, khi quan sát log:

- **Một item có thể tạo nhiều sự kiện lỗi** vì nhiều lần thử.
- **Một chunk có thể rollback** sau khi một số thao tác trong chunk đã chạy.
- **Một sự kiện log đã gửi ra ngoài thường không rollback theo transaction** của batch.
- **Một lần restart** có thể tạo các log retry cho dữ liệu từng được thử trong execution trước.
- `SkipListener` cho biết item bị skip theo chính sách nhưng không tự chứng minh dữ liệu lỗi đã được lưu bền vững ngoài Batch repository.

Điều này ảnh hưởng đến dashboard: không nên đếm số dòng `batch.retry.error` làm “số bản ghi thất bại” vì một bản ghi có thể phát nhiều dòng. Nếu muốn biết số bản ghi bị loại, cần dùng `skipCount` theo step và dữ liệu lưu trong error table. Nếu cần biết độ ổn định hạ tầng, số lượng retry errors lại là một metric hữu ích riêng.

### Mối quan hệ với idempotency

Writer gửi email, gọi API thanh toán hoặc ghi dữ liệu ngoài transaction phải được thiết kế sao cho retry/restart không tạo tác động trùng. Log không thể tự bảo đảm idempotency. Sử dụng business key, unique constraint, outbox hoặc cơ chế xác nhận trạng thái từ hệ thống đích khi phù hợp.

Ví dụ một API có thể đã xử lý yêu cầu nhưng response timeout; nếu RetryListener log timeout rồi step retry, lời gọi thứ hai có nguy cơ lặp tác động. Audit và idempotency key sẽ quyết định khả năng khôi phục chính xác.

## 12. Phân loại mức log

Không phải mọi lỗi tạm thời đều cần mức `ERROR`.

| Sự kiện | Mức đề xuất | Lý do |
| --- | --- | --- |
| Một attempt thất bại nhưng retry còn khả năng xử lý | `DEBUG` hoặc `WARN` có giới hạn tần suất | Chưa chắc là thất bại cuối |
| Retry kéo dài vượt ngưỡng cảnh báo | `WARN` | Có nguy cơ ảnh hưởng SLA |
| Một item được skip đúng chính sách | `INFO` hoặc `WARN` tùy mức độ nghiệp vụ | Là kết quả xử lý có chủ đích |
| Fallback được áp dụng thành công | `INFO`/`WARN` | Cần phân biệt đường xử lý thay thế |
| Step/job cuối cùng `FAILED` | `ERROR` | Cần theo dõi và điều tra |
| Lỗi dữ liệu nhạy cảm không được phép skip | `ERROR` với mã đã chuẩn hóa | Tránh lộ payload trong log |

Một số môi trường thích ghi retry attempt ở `DEBUG` rồi chỉ tăng metric và cảnh báo khi tỷ lệ retry vượt ngưỡng. Cách này giảm nhiễu nếu lỗi tạm thời xảy ra thường xuyên và được phục hồi tự động.

### Hạn chế log quá nhiều trong batch lớn

Nếu job đọc một triệu bản ghi và 10% phải retry ba lần, ghi stack trace cho từng attempt sẽ tiêu tốn tài nguyên đáng kể. Một cách tổ chức là:

1. Log mỗi loại lỗi với trường phân loại ngắn và correlation ID.
2. Giới hạn stack trace đầy đủ ở mẫu đại diện hoặc lỗi cuối của step.
3. Dùng counter/metric để đo tổng lượt retry theo job, step, loại lỗi và outcome.
4. Tại `afterStep`, ghi tổng read/write/skip/rollback.
5. Khi cần điều tra item cụ thể, truy xuất audit/error table theo key được phép lưu.

Không dùng `itemId` hoặc `jobExecutionId` duy nhất cho từng sự kiện làm label metric time series nếu hệ thống metric không phù hợp với cardinality cao. Những ID này nên nằm trong log, trace hoặc bảng audit.

## 13. Không làm lộ dữ liệu nghiệp vụ trong log

Một exception khi đọc CSV, ghi SQL hoặc gọi API có thể chứa chuỗi đầu vào trong message. Log kiểu:

```java
log.error("Failed item: {}", paymentRecord, exception);
```

có thể vô tình ghi số tài khoản, tên khách hàng hoặc dữ liệu thanh toán. Cách tốt hơn:

```java
log.error(
    "event=batch.item.failed paymentKey={} exceptionType={}",
    safePaymentKey,
    exception.getClass().getSimpleName()
);
```

Khi cần stack trace, log tại kênh truy cập hạn chế và có chính sách masking phù hợp. Không ghi token, mật khẩu, thông tin thẻ, nguyên message body hoặc toàn bộ JobParameters trừ khi đã được kiểm duyệt.

Các trường về thời gian nên thống nhất UTC hoặc định dạng ISO-8601 có múi giờ. Với hệ thống gồm nhiều scheduler/worker, gắn thêm trace ID hoặc launch correlation ID để có thể theo dõi một yêu cầu xuyên các service mà không phụ thuộc thứ tự dòng log.

## 14. Test các sự kiện retry và recovery

Một bộ test tốt có thể chia thành unit test với retry callback giả lập và integration test chạy step thật, dùng dữ liệu và exception được kiểm soát. Khi mục tiêu là logging, cần xác minh **loại sự kiện và quan hệ với kết quả cuối**, tránh kiểm tra chuỗi log quá cứng gây lỗi khi đổi tên field.

### 14.1. Các kịch bản nên có

| Kịch bản | Setup | Điều cần quan sát |
| --- | --- | --- |
| Thành công ngay | Writer/processor không ném lỗi | Không có `batch.retry.error`; step `COMPLETED` |
| Lỗi tạm thời rồi thành công | Cho thao tác ném lỗi 1–2 lần trước khi trả thành công | Có log lỗi attempt; item được xử lý thành công; không bị skip |
| Retry cạn và không được skip | Luôn ném exception retryable, không có recovery hợp lệ | Step `FAILED`, job có kết quả cuối phù hợp |
| Bản ghi lỗi được skip | Ném `InvalidPaymentException` trong processor, bật skip policy | `onSkipInProcess`, `processSkipCount` tăng |
| Lỗi read được skip | Reader ném lỗi có thể skip theo cấu hình | `onSkipInRead`, không giả định có item key |
| Ghi dữ liệu bị lỗi | Writer ném lỗi có kiểm soát | Log đúng phase và kết quả rollback/skip/fail |
| Restart sau failure | Execution đầu `FAILED`, chạy lại cùng identifying params | JobInstance ID không đổi, JobExecution ID mới, log mới |
| Launcher từ chối instance đã hoàn tất | Yêu cầu chạy trùng với params cũ | Không có callback retry/step mới; log tại launcher/coordinator |
| Cơ chế fallback riêng | RetryTemplate cạn, RecoveryCallback trả kết quả dự phòng | Log fallback và kiểm tra đầu ra mang trạng thái dự phòng |

### 14.2. Unit test với RetryListener

`RetryListener` có thể được gọi trực tiếp để kiểm tra log lỗi:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.context.RetryContextSupport;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class BatchRetryLogListenerTest {

    @Test
    void logsRetryFailureWithoutStepContext(CapturedOutput output) {
        BatchRetryLogListener listener =
            new BatchRetryLogListener();

        RetryContextSupport context =
            new RetryContextSupport(null);

        RuntimeException error =
            new TransientDataAccessResourceException("timeout");

        context.registerThrowable(error);

        RetryCallback<Void, RuntimeException> callback =
            retryContext -> null;

        listener.onError(context, callback, error);

        assertThat(output.getOut())
            .contains("event=batch.retry.error")
            .contains("exceptionType=TransientDataAccessResourceException")
            .contains("step=unknown");
    }
}
```

Đây là test thuần listener, nên `StepSynchronizationManager.getContext()` không được thiết lập; listener log `step=unknown` theo thiết kế. Nó chứng minh định dạng thông điệp khi gặp lỗi, nhưng **không** chứng minh chính sách retry của step được áp dụng đúng.

### 14.3. Integration test với step thật

Đối với phép kiểm tra retry/skip trên Spring Batch, nên dùng `spring-batch-test` với `JobRepository` test và các dependency giả lập có số lần gọi được kiểm soát. Có thể dùng `AtomicInteger` để làm writer lần đầu ném lỗi tạm thời, lần sau thành công. Mỗi test dùng database metadata riêng hoặc dọn metadata cẩn thận; tắt auto-run với `spring.batch.job.enabled=false`.

Assertion cần bao gồm:

- `BatchStatus`/`ExitStatus` của step và job.
- `readCount`, `writeCount`, `filterCount`, `readSkipCount`, `processSkipCount`, `writeSkipCount`, `rollbackCount` khi có ý nghĩa.
- Số lần lời gọi tới dependency giả lập để biết retry đã xảy ra.
- Dữ liệu đầu ra thật: không có duplicate do retry/rollback.
- Có event log retry khi lỗi tạm thời; event skip chỉ khi item bị skip.
- Execution mới và JobInstance cũ khi job restart.

Với các phép thử phụ thuộc tính đồng thời, dùng tín hiệu như `CountDownLatch` thay vì `Thread.sleep` và đoán thời điểm job đang chạy.

## 15. Ghi nhận retry qua metric và bảng lỗi

Log hữu ích cho việc điều tra từng execution, nhưng khi quản trị batch lớn cần tổng hợp xu hướng. Có thể đặt một bộ metric hoặc error table có các trường:

```text
batch_retry_errors_total{
  job="paymentImportJob",
  step="chargeStep",
  exception="QueryTimeoutException"
}

batch_skipped_items_total{
  job="paymentImportJob",
  step="chargeStep",
  phase="PROCESS",
  reason="INVALID_AMOUNT"
}
```

Đây là **ví dụ tên metric do ứng dụng định nghĩa**, không phải tên metric mặc định mà Spring Batch luôn cung cấp. Metrics của môi trường cụ thể phụ thuộc phiên bản và bộ instrumentation được cài đặt.

Nếu cần theo dõi lâu dài từng item bị skip, có thể ghi vào bảng lỗi với business key, execution ID, bước xử lý, mã lý do và thời điểm. Việc ghi dữ liệu lỗi phải có quy tắc idempotency khi step restart hoặc chunk rollback. Không suy ra chính xác số item lỗi duy nhất bằng cách đếm dòng log retry.

Một dashboard thực tế nên có tỷ lệ step `FAILED`, số skip, thời lượng, các exception phổ biến và số execution phải restart. Nên cảnh báo theo **kết quả cuối/SLA**, sau đó dùng retry/error logs để xác định nguyên nhân.

## 16. Những lỗi thường gặp khi triển khai logging

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Một lỗi tạm thời tạo nhiều cảnh báo `ERROR` | Log mọi attempt là lỗi cuối | Log attempt mức phù hợp, cảnh báo theo step/job outcome |
| Log “recovered” nhưng job sau đó `FAILED` | Coi `onError` hoặc `close` là recovery thành công | Chỉ ghi recovery khi đường xử lý thay thế thực sự hoàn thành |
| Không có log item khi reader lỗi | `onSkipInRead` không nhận item | Ghi phase/exception và bổ sung source location từ reader nếu có |
| Log skip nhưng không thấy dữ liệu bảng lỗi | Log không thuộc transaction hoặc external write thất bại | Có error table/outbox, transaction và reconciliation |
| Skip count bằng 0 dù processor trả về null | Nhầm filter và skip | Kiểm tra `filterCount`, thiết kế policy rõ |
| Step có nhiều retry nhưng `rollbackCount` thấp | Hai counter đo các sự kiện khác nhau | Không suy ra retry từ rollback hoặc ngược lại |
| Retry trong Spring Batch và RetryTemplate làm API bị gọi nhiều | Retry lồng nhau | Xác định tầng retry, số lần tối đa và timeout |
| Retry một lần nhưng job tạo JobInstance khác | Restart dùng identifying params khác | Giữ business key ổn định khi restart |
| Restart làm tổng log retry tăng | Nhiều JobExecution trong cùng instance | Thống kê theo execution và instance riêng |
| Item ID của người khác lọt vào log | Log nguyên payload hoặc exception message | Allowlist/redact dữ liệu, phân quyền truy cập |
| Log step không có thông tin failure | Chỉ log read/write counts | Ghi BatchStatus, ExitStatus và exception classification |
| Không thấy callback RetryListener | Chưa đăng ký listener hoặc exception không thuộc retry policy | Kiểm tra cấu hình listener và exception classifier |
| Retry count bị cộng thành số item lỗi | Một item có nhiều attempts | Dùng skip counts hoặc bảng lỗi để đếm item |

## 17. Bài tập thực hành

Hãy tạo một job nhập giao dịch thanh toán từ file hoặc database. Step sử dụng chunk size 10, áp dụng retry cho lỗi mạng tạm thời và skip cho bản ghi nghiệp vụ sai định dạng trong giới hạn cho phép.

Yêu cầu triển khai:

1. `RetryListener` log từng lỗi retry với step, jobExecutionId, retryFailureCount và exceptionType.
2. `SkipListener` log bản ghi bị loại ở giai đoạn đọc, xử lý hoặc ghi; item key phải được ẩn nếu chứa dữ liệu nhạy cảm.
3. `StepExecutionListener` log kết quả cuối, các số đếm read/write/filter/skip/rollback.
4. Một lần xử lý thất bại sau khi retry cạn phải xuất hiện rõ `FAILED`, còn lỗi được retry thành công không tự bị tính là item đã skip.
5. Khi restart, log phải cho thấy JobInstance ID giữ nguyên và JobExecution ID mới.

Tạo bốn bộ dữ liệu kiểm thử: tất cả hợp lệ; lỗi mạng xảy ra một lần rồi hết; bản ghi sai nghiệp vụ được skip; lỗi mạng kéo dài khiến step fail. Sau đó kiểm tra số lần gọi của thành phần giả lập, đầu ra nghiệp vụ, metadata Spring Batch và thông điệp log.

Thử bổ sung một `RetryTemplate` có `RecoveryCallback` trả trạng thái `MANUAL_REVIEW`. Kiểm tra chính xác khi nào callback được gọi, cách dữ liệu dự phòng được ghi vào đích và liệu chính sách rollback có thể gây tác động lặp hay không.

## 18. Kết luận

Logging retry và recovery trong Spring Batch phải làm rõ **một lần thử gặp lỗi**, **item được skip hoặc áp dụng fallback**, và **step/job cuối cùng thành công hay thất bại**. `RetryListener` giúp quan sát từng exception trong vòng retry; `SkipListener` ghi sự kiện bỏ item; `StepExecutionListener` và `JobExecutionListener` xác nhận kết quả cuối của execution. Các log cần khóa tương quan, loại lỗi, phase và số đếm phù hợp, đồng thời được kiểm soát tần suất và dữ liệu nhạy cảm. Phân biệt retry trong execution với restart của JobInstance giúp việc điều tra sự cố và theo dõi chất lượng xử lý batch chính xác hơn.
