# Status khi retry recovery

Trong Spring Batch, một thao tác có thể được retry khi gặp lỗi tạm thời. Nếu retry thành công, step tiếp tục xử lý bình thường. Nếu retry hết mà lỗi vẫn còn, framework phải đi theo nhánh recovery đã cấu hình: bỏ qua item nếu skip policy cho phép, hoặc làm step thất bại. Khi theo dõi job, cần hiểu trạng thái được phản ánh ở đâu và vào thời điểm nào.

Điểm dễ nhầm là Spring Batch không có một `BatchStatus` chuẩn tên `RETRYING` hay `RETRY_EXHAUSTED`. Các lần thử lại thường diễn ra bên trong một step execution đang chạy. Trạng thái cuối cùng của step/job chỉ được xác định khi quá trình xử lý kết thúc hoặc bị dừng. Muốn quan sát từng retry attempt, ứng dụng cần bổ sung log, listener hoặc metric phù hợp.

## 1. Hai loại trạng thái cần phân biệt

Spring Batch sử dụng hai khái niệm chính để biểu diễn kết quả thực thi:

- `BatchStatus`: trạng thái vòng đời của `JobExecution` hoặc `StepExecution`, cho biết execution đang khởi tạo, đang chạy, hoàn tất, thất bại hay đã dừng.
- `ExitStatus`: mã kết quả dùng để mô tả kết thúc step/job và điều khiển flow. Ngoài các mã mặc định, ứng dụng có thể tạo mã tùy chỉnh như `COMPLETED_WITH_WARNINGS`.

Hai giá trị này liên quan nhưng không đồng nghĩa. Ví dụ, step có thể kết thúc với `BatchStatus.COMPLETED` và `ExitStatus` là `COMPLETED_WITH_WARNINGS` khi job xử lý xong nhưng có một số item bị skip theo chính sách.

| Khái niệm | Trả lời câu hỏi |
|---|---|
| `BatchStatus` | Execution đang ở trạng thái vòng đời nào? |
| `ExitStatus` | Step/job kết thúc với mã kết quả nào và flow nên đi theo nhánh nào? |

Khi theo dõi retry recovery, hãy xem cả hai. Chỉ nhìn `BatchStatus` có thể bỏ qua thông tin nghiệp vụ về cảnh báo hoặc dữ liệu bị loại.

## 2. Các BatchStatus thường gặp

`BatchStatus` là enum của Spring Batch. Những giá trị thường gặp gồm:

| BatchStatus | Ý nghĩa tổng quát |
|---|---|
| `STARTING` | Execution đang được khởi tạo. |
| `STARTED` | Job hoặc step đang thực thi. |
| `STOPPING` | Có yêu cầu dừng và execution đang đi vào quá trình dừng. |
| `STOPPED` | Execution đã dừng theo yêu cầu dừng có kiểm soát. |
| `COMPLETED` | Execution hoàn tất thành công theo trạng thái framework. |
| `FAILED` | Execution thất bại do lỗi không được xử lý thành công. |
| `ABANDONED` | Execution/step được đánh dấu bỏ lại và không tiếp tục theo quy trình restart thông thường. |
| `UNKNOWN` | Framework không thể xác định chắc chắn trạng thái cuối cùng. |

Không có trạng thái `RETRYING` trong danh sách này. Khi một writer gặp deadlock và Spring Batch đang thử lại, `StepExecution` thường vẫn đang ở `STARTED`; `JobExecution` cha cũng thường vẫn là `STARTED`. Nếu retry thành công, step có thể kết thúc `COMPLETED`. Nếu lỗi thoát ra khỏi step, step kết thúc `FAILED` và job thường cũng kết thúc `FAILED`.

## 3. Retry attempt không phải một JobExecution mới

Retry trong fault-tolerant step thường diễn ra bên trong cùng một lần thực thi step. Ví dụ, writer gặp lỗi deadlock ba lần rồi thành công ở lần tiếp theo. Các lần gọi writer không tạo ra ba `JobExecution` hoặc ba `StepExecution` mới.

```text
JobExecution #501: STARTED
  |
  +-- StepExecution #802: STARTED
          |
          +-- writer attempt 1 -> deadlock
          +-- writer attempt 2 -> deadlock
          +-- writer attempt 3 -> success
          |
          +-- chunk commit
          |
          +-- StepExecution #802: COMPLETED
  |
  +-- JobExecution #501: COMPLETED
```

Trong ví dụ, framework theo dõi trạng thái execution ở cấp job/step; các attempt là hoạt động bên trong step. `StepExecution` không cung cấp một counter chuẩn riêng tên `retryCount` để lưu tổng số lần retry. Nếu dashboard cần số attempt, ứng dụng phải ghi nhận bằng cơ chế quan sát riêng.

## 4. Trạng thái khi retry thành công

Giả sử một step ghi dữ liệu và gặp lỗi tạm thời. Step được cấu hình retry cho loại exception đó. Nếu một attempt sau thành công, thao tác tiếp tục như một lần xử lý bình thường.

```text
StepExecution: STARTED
      |
      v
Writer attempt 1 -> TransientDataAccessException
      |
      v
Retry
      |
      v
Writer attempt 2 -> success
      |
      v
Chunk commit
      |
      v
StepExecution: COMPLETED
```

Retry thành công không làm tăng skip count. Các counter như `readCount`, `writeCount`, `commitCount` phản ánh hoạt động xử lý/commit theo semantics của step; chúng không thay thế metric retry attempt.

Nếu toàn bộ step hoàn tất, `BatchStatus` của step là `COMPLETED`. Job có thể tiếp tục step tiếp theo và cuối cùng kết thúc `COMPLETED`, tùy flow.

## 5. Trạng thái khi retry hết và item được skip

Trong Spring Batch, retry policy và skip policy là hai quyết định độc lập. Một exception có thể được retry trước; nếu retry hết mà exception cũng thuộc skip policy, framework có thể bỏ qua item miễn là chưa vượt `skipLimit`.

Ví dụ cấu hình:

```java
return new StepBuilder("publishOrdersStep", jobRepository)
        .<Order, PartnerRequest>chunk(50, transactionManager)
        .reader(orderReader)
        .processor(requestProcessor)
        .writer(partnerWriter)
        .faultTolerant()
        .retry(ResourceAccessException.class)
        .retryLimit(3)
        .skip(ResourceAccessException.class)
        .skipLimit(25)
        .listener(partnerSkipListener)
        .build();
```

Ở đây, timeout được thử lại trong giới hạn. Nếu vẫn thất bại, skip policy có thể cho phép bỏ qua item. Nếu step tiếp tục hoàn tất và tổng skip không vượt giới hạn, `StepExecution` vẫn có thể kết thúc `COMPLETED`, đồng thời `skipCount` tăng.

Điều đó không có nghĩa item đã được xử lý thành công. Nó có nghĩa step đã hoàn tất theo chính sách fault tolerance được cấu hình. Cần xem skip counter và danh sách item lỗi để đánh giá kết quả nghiệp vụ.

## 6. Trạng thái khi retry hết nhưng không được skip

Nếu exception không thuộc skip policy, hoặc skip limit đã bị vượt, exception không được chuyển thành một skip hợp lệ. Nó thoát ra khỏi quá trình xử lý chunk và step thất bại.

```text
JobExecution: STARTED
  |
  +-- StepExecution: STARTED
          |
          +-- writer attempt 1 -> deadlock
          +-- writer attempt 2 -> deadlock
          +-- writer attempt 3 -> deadlock
          |
          +-- retry exhausted
          +-- exception không skippable
          +-- chunk rollback
          +-- StepExecution: FAILED
  |
  +-- JobExecution: FAILED
```

Trong tình huống này, `BatchStatus` của step là `FAILED`; job thường cũng `FAILED` nếu không có flow xử lý lỗi theo cách khác. Transaction hiện tại được rollback theo transaction manager. Các chunk đã commit trước đó vẫn giữ nguyên.

Không có status riêng `RETRY_EXHAUSTED`. Để biết retry đã hết, cần xem exception cuối cùng, log/metric attempt và trạng thái cuối của step.

## 7. Recovery callback và skip policy không phải cùng một thứ

Trong hệ sinh thái Spring, từ “recovery” có thể chỉ nhiều cơ chế khác nhau. Cần phân biệt:

- Trong fault-tolerant step của Spring Batch, nhánh sau retry có thể đi qua skip policy. Nếu exception không được skip, step thất bại.
- Trong Spring Retry, `RetryTemplate` có thể nhận `RecoveryCallback` để thực hiện hành động thay thế khi retry policy hết attempt.
- `RetryListener` dùng để quan sát vòng đời retry; nó không tự động thay thế logic recovery nghiệp vụ.

Ví dụ dùng Spring Retry trực tiếp:

```java
RetryTemplate retryTemplate = RetryTemplate.builder()
        .maxAttempts(3)
        .fixedBackoff(1000)
        .retryOn(TransientDataAccessException.class)
        .build();

PartnerResult result = retryTemplate.execute(
        context -> partnerClient.submit(request),
        context -> recoveryService.markPending(
                request,
                context.getLastThrowable()));
```

Trong ví dụ, recovery callback chạy khi `RetryTemplate` đã hết attempt theo policy. Callback trả về một kết quả thay thế theo hợp đồng ứng dụng. Nếu callback không thể tạo kết quả hợp lệ, nó nên ném exception để caller nhận biết lỗi.

Đây là API Spring Retry độc lập. Không nên nhầm callback này với skip policy của Spring Batch hoặc mặc định rằng một fault-tolerant step tự gọi callback tùy ý sau retry exhaustion.

## 8. Cấu hình backoff ảnh hưởng đến thời gian ở trạng thái STARTED

Backoff tạo khoảng chờ giữa các lần thử. Trong thời gian chờ, step vẫn đang được thực thi; status không chuyển sang một enum retry riêng.

Ví dụ:

```java
ExponentialBackOffPolicy backOffPolicy = new ExponentialBackOffPolicy();
backOffPolicy.setInitialInterval(500L);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(5000L);

return new StepBuilder("callPartnerStep", jobRepository)
        .<PartnerRequest, PartnerResponse>chunk(50, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(ResourceAccessException.class)
        .retryLimit(3)
        .backOffPolicy(backOffPolicy)
        .build();
```

Nếu dashboard chỉ đọc `BatchStatus`, trong thời gian backoff nó có thể hiển thị `STARTED` dù worker đang chờ trước attempt tiếp theo. Vì vậy, khi cần hiển thị chi tiết, hãy bổ sung metric như số attempt, thời gian chờ, exception gần nhất và thời điểm retry gần nhất.

## 9. Retry không có counter chuẩn trong StepExecution

`StepExecution` có nhiều counter chuẩn như:

- `readCount`
- `writeCount`
- `filterCount`
- `readSkipCount`
- `processSkipCount`
- `writeSkipCount`
- `skipCount`
- `commitCount`
- `rollbackCount`

Các counter này không phải số lần retry. Một item có thể được thử lại nhiều lần rồi thành công mà `skipCount` vẫn bằng 0. Ngược lại, một item có thể bị skip ngay mà không trải qua retry.

Nếu muốn theo dõi retry, có thể ghi metric hoặc log ở nơi thực hiện retry. Tùy API/version đang dùng, Spring Retry cung cấp `RetryListener`; Spring Batch cũng có các listener và callback tương ứng trong fault-tolerant processing. Hãy kiểm tra đúng phiên bản thư viện để đăng ký listener với chữ ký phù hợp.

Nên ghi nhận tối thiểu:

- Job name, JobExecution ID và StepExecution ID.
- Step name và partition name nếu có.
- Exception type và cause.
- Attempt number hoặc tổng attempt.
- Thời gian bắt đầu và kết thúc mỗi attempt.
- Kết quả cuối: thành công, skip hay step failed.
- Business key hoặc correlation ID của item.

## 10. Theo dõi retry bằng RetryListener

`RetryListener` của Spring Retry cho phép quan sát các sự kiện trong vòng đời retry. Một listener có thể dùng để ghi log hoặc phát metric khi một attempt thất bại.

Ví dụ khái niệm:

```java
public class RetryMetricsListener implements RetryListener {

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        // Tăng metric retry failure và ghi exception type.
        retryMetrics.recordFailure(throwable.getClass().getSimpleName());
    }
}
```

Chữ ký listener thay đổi theo phiên bản Spring Retry. Đoạn code trên minh họa API ở các phiên bản có callback tương ứng; cần đối chiếu dependency thực tế trước khi copy vào dự án.

Listener nên tập trung quan sát, không thực hiện thao tác nghiệp vụ không idempotent. Nếu listener gửi thông báo mỗi lần retry, một lỗi kéo dài có thể tạo rất nhiều cảnh báo. Nên dùng metric tổng hợp hoặc cảnh báo khi vượt ngưỡng.

## 11. Theo dõi item được recovery bằng SkipListener

Nếu nhánh recovery của Spring Batch là skip, `SkipListener` cung cấp callback riêng cho read, process và write.

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable throwable) {
        // Reader lỗi trước khi tạo được item.
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable throwable) {
        // Ghi business key và nguyên nhân lỗi.
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        // Ghi business key của item đầu ra không ghi được.
    }
}
```

Sau khi item được skip, các counter tương ứng trong `StepExecution` được cập nhật. `SkipListener` giúp lưu chi tiết item và exception; counter giúp tổng hợp số lượng.

Nếu listener ghi vào database cùng transaction, cần bảo đảm cách ghi phù hợp với transaction của chunk. Nếu gửi message hoặc gọi API ngoài, rollback database không thể tự thu hồi tác dụng phụ đó; hãy dùng outbox hoặc idempotency key khi cần.

## 12. StepExecutionListener đọc status cuối cùng

`StepExecutionListener.afterStep` có thể đọc trạng thái và counter sau khi step kết thúc. Đây là nơi phù hợp để ghi tổng kết hoặc đặt `ExitStatus` tùy chỉnh theo kết quả nghiệp vụ.

```java
public class RetryRecoverySummaryListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "Step {}: batchStatus={}, exitStatus={}, " +
                "skipCount={}, rollbackCount={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus().getExitCode(),
                stepExecution.getSkipCount(),
                stepExecution.getRollbackCount());

        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {
            return new ExitStatus("COMPLETED_WITH_WARNINGS");
        }

        return null;
    }
}
```

Listener trả `null` nếu không cần thay đổi ExitStatus. Nếu có skip và step vẫn `COMPLETED`, ví dụ đặt exit code `COMPLETED_WITH_WARNINGS` để flow hoặc dashboard phân biệt kết quả có cảnh báo.

Việc thay đổi `ExitStatus` không biến `BatchStatus.COMPLETED` thành `FAILED`. Hai trạng thái phục vụ mục đích khác nhau. Nếu nghiệp vụ yêu cầu job thất bại khi có skip, hãy thiết kế flow/exit behavior rõ ràng và bảo đảm trạng thái cuối phản ánh đúng yêu cầu.

## 13. JobExecutionListener đọc kết quả của job

`JobExecutionListener.afterJob` được gọi khi job kết thúc. Nó phù hợp để ghi nhận status cuối, thời gian chạy và tổng hợp các step execution.

```java
public class JobStatusListener implements JobExecutionListener {

    @Override
    public void afterJob(JobExecution jobExecution) {
        log.info(
                "Job {} execution {} finished: status={}, exit={}",
                jobExecution.getJobInstance().getJobName(),
                jobExecution.getId(),
                jobExecution.getStatus(),
                jobExecution.getExitStatus().getExitCode());

        for (StepExecution step : jobExecution.getStepExecutions()) {
            log.info(
                    "Step {} status={} skips={} rollbacks={}",
                    step.getStepName(),
                    step.getStatus(),
                    step.getSkipCount(),
                    step.getRollbackCount());
        }
    }
}
```

Job listener không quan sát từng retry attempt. Nó chỉ phù hợp để tổng kết kết quả sau khi job kết thúc. Muốn biết một step đã retry bao nhiêu lần trước khi hoàn tất, cần metric/log ở retry boundary.

## 14. Trạng thái trong các trường hợp recovery khác nhau

Bảng sau tóm tắt kết quả thường gặp ở cấp step/job:

| Tình huống | Step BatchStatus | Job BatchStatus thường gặp | Ghi chú |
|---|---|---|---|
| Retry thành công và tất cả công việc hoàn tất | `COMPLETED` | `COMPLETED` | Retry attempt không làm tăng skip count. |
| Retry hết, item được skip và step hoàn tất | `COMPLETED` | `COMPLETED` | Skip counter tăng; ExitStatus có thể tùy chỉnh. |
| Retry hết, exception không skippable | `FAILED` | `FAILED` | Chunk hiện tại rollback theo transaction manager. |
| Retry hết, skip limit bị vượt | `FAILED` | `FAILED` | Skip limit là tổng giới hạn cho step. |
| Có yêu cầu dừng trong khi step đang chạy | Có thể chuyển qua trạng thái dừng | Có thể chuyển qua trạng thái dừng | Kết quả phụ thuộc thời điểm và cách step xử lý stop. |
| Recovery callback riêng trả fallback hợp lệ và caller hoàn tất | Tùy step | Tùy job | Callback không tự quyết định BatchStatus; kết quả trả về được xử lý bởi caller. |

Đây là các kết quả khái quát. Flow transition, listener, exception handler và cấu hình ứng dụng có thể làm `ExitStatus` hoặc trạng thái cuối khác với ví dụ đơn giản.

## 15. ExitStatus tùy chỉnh cho kết quả recovery

Một step có thể hoàn tất về mặt kỹ thuật nhưng muốn biểu diễn rằng đã có item được recovery bằng skip. Có thể dùng ExitStatus tùy chỉnh để định tuyến flow.

Ví dụ:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        Step warningReportStep,
        Step successReportStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importStep)
                .on("COMPLETED_WITH_WARNINGS").to(warningReportStep)
            .from(importStep)
                .on("COMPLETED").to(successReportStep)
            .from(warningReportStep)
                .on("*").end()
            .from(successReportStep)
                .on("*").end()
            .end()
            .build();
}
```

Listener của `importStep` có thể đặt `COMPLETED_WITH_WARNINGS` khi `skipCount` lớn hơn 0. Flow sau đó chạy báo cáo cảnh báo. Cần khai báo các nhánh lỗi còn lại để job không vô tình đi vào nhánh thành công.

Không nên đổi ExitStatus thành `COMPLETED_WITH_WARNINGS` chỉ vì có retry. Retry thành công là một cơ chế phục hồi bình thường; nếu không có item bị bỏ qua hoặc điều kiện cảnh báo khác, step có thể kết thúc với `COMPLETED`.

## 16. Retry recovery và transaction rollback

Retry thường gắn với transaction của chunk. Khi writer thất bại, chunk transaction có thể rollback trước khi framework thực hiện retry theo policy. Nếu lần thử sau thành công, chunk được ghi và commit. Nếu retry hết và item được skip, framework tiếp tục theo fault-tolerant semantics. Nếu không thể skip, step thất bại.

```text
BEGIN chunk transaction
  read/process items
  write chunk -> transient exception
ROLLBACK (theo cơ chế fault tolerance)

Retry attempt
  write lại
  +-- success -> commit
  +-- fail hết retry
          +-- skippable -> recovery/skip rồi tiếp tục
          +-- không skippable -> step FAILED
```

Các chunk trước đã commit không bị rollback chỉ vì chunk hiện tại thất bại. Tác dụng phụ ngoài transaction như email, HTTP request hoặc publish message cũng không tự động được hoàn tác. Vì vậy, retry recovery cần được thiết kế cùng idempotency và đối soát.

## 17. Status khi restart sau retry recovery thất bại

Nếu step kết thúc `FAILED` sau retry exhaustion, người vận hành có thể sửa nguyên nhân rồi restart JobInstance. Restart tạo JobExecution mới; execution cũ vẫn được giữ trong JobRepository.

```text
JobInstance: importOrdersJob / businessDate=2026-11-15
  |
  +-- JobExecution #501: FAILED
  |      +-- importOrdersStep: FAILED
  |
  +-- JobExecution #602: COMPLETED (restart)
         +-- importOrdersStep: COMPLETED
```

Khi restart:

- Dùng lại identifying JobParameters để tiếp tục cùng JobInstance.
- Kiểm tra step đã hoàn tất có được bỏ qua theo mặc định hay được cấu hình `allowStartIfComplete`.
- Reader/writer cần khôi phục checkpoint từ `ExecutionContext` nếu muốn tiếp tục đúng vị trí.
- Item chưa commit có thể được đọc/xử lý lại.
- Writer và tích hợp ngoài phải idempotent để tránh tác dụng phụ trùng.

Không nhầm retry attempt với restart. Retry diễn ra trong cùng step execution; restart tạo JobExecution mới cho cùng JobInstance sau khi execution trước kết thúc ở trạng thái cho phép restart.

## 18. Tra cứu status và counter bằng JobExplorer

`JobExplorer` là API đọc metadata đã lưu trong JobRepository. Nó phù hợp cho dashboard, API giám sát hoặc công cụ điều tra.

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    log.info("Job status={}, exit={}",
            execution.getStatus(), execution.getExitStatus().getExitCode());

    for (StepExecution step : execution.getStepExecutions()) {
        log.info(
                "Step {}: status={}, readSkip={}, processSkip={}, " +
                "writeSkip={}, totalSkip={}, rollback={}",
                step.getStepName(),
                step.getStatus(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getSkipCount(),
                step.getRollbackCount());
    }
}
```

JobExplorer giúp đọc trạng thái và counter đã lưu. Nó không phải luồng sự kiện thời gian thực cho từng retry attempt. Nếu dashboard cần hiển thị “đang retry lần 2”, phải lưu trạng thái quan sát riêng hoặc lấy metric/log từ retry listener.

Khi job đang chạy, metadata có thể được cập nhật theo vòng đời step/chunk và transaction. Không nên giả định mọi lần retry nội bộ đều được ghi thành một bản ghi metadata riêng.

## 19. Không nên tạo status tùy chỉnh tên RETRYING trong BatchStatus

`BatchStatus` là enum framework. Ứng dụng không thể thêm một enum value mới như `RETRYING` bằng cách khai báo `ExitStatus` hoặc listener.

Nếu giao diện cần hiển thị trạng thái chi tiết, có thể tạo một trường/metric vận hành riêng, ví dụ:

```text
executionStatus = STARTED
activity        = RETRYING
attempt         = 2
lastException   = DeadlockLoserDataAccessException
nextAttemptAt   = 2026-11-15T15:35:00Z
```

Trong mô hình này:

- `executionStatus` vẫn lấy từ BatchStatus của Spring Batch.
- `activity` là trạng thái quan sát do ứng dụng quản lý.
- `attempt`, `lastException` và `nextAttemptAt` là metric/metadata bổ sung.

Đừng ghi đè BatchStatus trong JobRepository bằng chuỗi tùy chỉnh. Làm vậy có thể phá vỡ trạng thái lifecycle và logic restart của framework. Nếu lưu activity riêng, cần xác định vòng đời và cách xóa/reset sau khi retry kết thúc.

## 20. Các lỗi thường gặp khi theo dõi status retry recovery

| Vấn đề | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Dashboard không có trạng thái `RETRYING` | Spring Batch không định nghĩa BatchStatus này. | Hiển thị BatchStatus `STARTED` cùng metric activity riêng. |
| Step COMPLETED nhưng vẫn có lỗi | Item đã được skip trong giới hạn. | Xem skip counter, ExitStatus và rejected-item store. |
| Retry thành công nhưng skip count tăng | Nhầm retry counter với skip counter hoặc item khác bị skip. | Ghi attempt riêng và đối chiếu business key. |
| Retry hết nhưng step vẫn STARTED | Execution chưa kết thúc hoặc worker vẫn đang xử lý/đợi recovery. | Xem log, thread, timeout và trạng thái cuối sau khi xử lý hoàn tất. |
| Step FAILED nhưng không biết retry bao nhiêu lần | StepExecution không có retryCount chuẩn. | Bổ sung RetryListener/log/metric. |
| Job COMPLETED dù có item chưa gửi được | Exception được skip hoặc recovery trả fallback và step hoàn tất. | Định nghĩa ExitStatus cảnh báo và quy trình xử lý pending. |
| JobExplorer không hiển thị từng attempt | JobExplorer đọc metadata execution, không phải retry event stream. | Dùng metric/log hoặc bảng giám sát riêng. |
| Status job cha không phản ánh chi tiết child retry | Retry diễn ra bên trong step/job con. | Theo dõi execution của child và liên kết với parent. |
| Restart bị coi là execution mới | Thay identifying JobParameters. | Giữ nguyên identifying values khi restart. |

## 21. Quy trình điều tra một job có retry recovery

Khi dashboard báo job chạy lâu hoặc kết thúc với cảnh báo/thất bại, có thể điều tra theo trình tự:

1. **Xác định JobExecution:** lấy job name, execution ID, JobInstance và identifying parameters.
2. **Xác định StepExecution:** tìm step đang chạy hoặc step thất bại.
3. **Đọc BatchStatus và ExitStatus:** phân biệt lifecycle với kết quả/nhánh flow.
4. **Kiểm tra log/metric retry:** tìm attempt, exception type, backoff và item/business key.
5. **Đọc skip counter:** xem read/process/write skip và tổng skip.
6. **Kiểm tra transaction:** xác định chunk đã commit, rollback và tác dụng phụ ngoài transaction.
7. **Xác định nhánh recovery:** retry thành công, skip, fallback callback hay step failure.
8. **Đánh giá dữ liệu nghiệp vụ:** kiểm tra rejected/pending item và đối soát với hệ thống ngoài.
9. **Khắc phục nguyên nhân:** xử lý deadlock, timeout, dữ liệu sai hoặc lỗi hạ tầng.
10. **Restart nếu cần:** dùng đúng identifying parameters và kiểm tra checkpoint/idempotency.
11. **Xác nhận trạng thái cuối:** theo dõi execution mới, ExitStatus và dữ liệu đầu ra.

Không nên chỉ nhìn `STARTED` rồi kết luận job bị treo. Nó có thể đang xử lý, đang backoff giữa các attempt hoặc đang chờ tài nguyên. Hãy kết hợp heartbeat, log, thread dump/metric phù hợp với quyền vận hành và thời gian cập nhật metadata.

## 22. Những điểm cần ghi nhớ

- Spring Batch không có `BatchStatus.RETRYING` hoặc `BatchStatus.RETRY_EXHAUSTED` mặc định.
- Retry attempt thường diễn ra bên trong cùng `StepExecution`; không tạo JobExecution mới cho mỗi lần thử.
- Trong lúc step đang retry/backoff, BatchStatus thường vẫn là `STARTED`.
- Retry thành công có thể dẫn đến step/job `COMPLETED` mà không tăng skip count.
- Retry hết và item được skip trong giới hạn vẫn có thể dẫn đến step/job `COMPLETED`, nhưng skip counter tăng.
- Retry hết và exception không skippable, hoặc vượt skip limit, thường làm step/job `FAILED`.
- `BatchStatus` mô tả lifecycle; `ExitStatus` mô tả mã kết quả và có thể dùng để điều khiển flow.
- `StepExecution` không có retry counter chuẩn; muốn quan sát attempt cần listener, log hoặc metric riêng.
- `SkipListener` ghi nhận item được skip; `StepExecutionListener` và `JobExecutionListener` tổng kết trạng thái cuối.
- `RecoveryCallback` của Spring Retry khác với skip policy trong Spring Batch.
- `JobExplorer` đọc metadata đã lưu nhưng không cung cấp event riêng cho từng retry attempt.
- Restart tạo JobExecution mới cho cùng JobInstance; retry không tạo execution mới.
- Writer và tích hợp ngoài cần idempotency/outbox/đối soát để recovery không tạo tác dụng phụ trùng.

Khi hiển thị trạng thái retry recovery, hãy dùng BatchStatus để biểu diễn vòng đời thực thi, ExitStatus để thể hiện kết quả và metric riêng để theo dõi từng attempt. Cách phân tách này giúp dashboard phản ánh đúng việc job vẫn đang chạy, đã phục hồi thành công, đã bỏ qua item hay thực sự thất bại sau khi hết retry.
