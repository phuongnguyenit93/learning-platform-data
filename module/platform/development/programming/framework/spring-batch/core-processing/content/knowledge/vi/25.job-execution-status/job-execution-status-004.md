# Custom ExitStatus

Trong Spring Batch, `ExitStatus` mô tả kết quả thoát của một Step hoặc Job bằng một mã kết quả và phần mô tả tùy chọn. Các mã chuẩn như `COMPLETED`, `FAILED` và `STOPPED` đáp ứng những trường hợp phổ biến. Tuy nhiên, nghiệp vụ đôi khi cần phân biệt chi tiết hơn: Step hoàn tất nhưng có item bị skip, không có dữ liệu đầu vào, cần review thủ công hoặc phát hiện dữ liệu đã được xử lý trước đó.

Spring Batch cho phép tạo **custom `ExitStatus`** để biểu diễn các kết quả đó. Job flow có thể dùng exit code tùy chỉnh để chọn Step tiếp theo. Ví dụ, `COMPLETED_WITH_SKIPS` có thể chuyển sang Step lập báo cáo lỗi, còn `NO_DATA` có thể kết thúc Job bình thường mà không chạy bước import.

Custom ExitStatus giúp mô tả kết quả nghiệp vụ và điều phối Job flow. Nó không tự thay đổi `BatchStatus`: một Step có thể vẫn là `BatchStatus.COMPLETED` trong khi `ExitStatus` là `COMPLETED_WITH_SKIPS`.

## 1. ExitStatus gồm exit code và exit description

`ExitStatus` là value object Spring Batch dùng để mô tả kết quả của một lần thực thi. Hai phần chính:

- **Exit code:** chuỗi định danh kết quả, thường được Job flow dùng để so khớp transition.
- **Exit description:** thông tin bổ sung giúp người vận hành hiểu vì sao Step kết thúc với mã đó.

Ví dụ:

```java
ExitStatus status = new ExitStatus(
        "COMPLETED_WITH_SKIPS",
        "Import completed with 7 skipped records"
);
```

Trong ví dụ này, `COMPLETED_WITH_SKIPS` là mã để Job flow định tuyến. Phần mô tả ghi thêm số lượng item bị skip để phục vụ log hoặc điều tra.

Spring Batch có các mã chuẩn thông dụng:

| ExitStatus | Ý nghĩa thường gặp |
|---|---|
| `COMPLETED` | Step/Job hoàn tất bình thường |
| `EXECUTING` | Đang thực thi trong một số ngữ cảnh |
| `FAILED` | Thực thi thất bại |
| `STOPPED` | Thực thi đã dừng |
| `NOOP` | Không có thao tác cần thực hiện trong một số tình huống |
| `UNKNOWN` | Không xác định được kết quả |

Ứng dụng có thể tạo exit code theo nghiệp vụ, ví dụ `NO_DATA`, `COMPLETED_WITH_SKIPS`, `NEEDS_REVIEW`, `ALREADY_PROCESSED` hoặc `SOURCE_NOT_READY`.

## 2. Phân biệt ExitStatus với BatchStatus

`BatchStatus` và `ExitStatus` thường có giá trị tương tự trong trường hợp đơn giản, nhưng chúng mô tả hai khía cạnh khác nhau.

| Tiêu chí | `BatchStatus` | `ExitStatus` |
|---|---|---|
| Mục đích | Trạng thái vòng đời thực thi | Kết quả thoát và mã kết quả |
| Giá trị | Enum chuẩn như `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` | Exit code dạng chuỗi và exit description |
| Ai dùng? | Spring Batch và công cụ vận hành | Job flow, log, tích hợp và báo cáo kết quả |
| Có mã tùy chỉnh? | Không theo cách tạo enum mới | Có thể tạo exit code tùy chỉnh |

Ví dụ, Step đọc 1.000 bản ghi, skip 7 bản ghi không hợp lệ và ghi thành công phần còn lại. Step có thể kết thúc với:

```text
BatchStatus = COMPLETED
ExitStatus  = COMPLETED_WITH_SKIPS
```

Step đã hoàn thành theo vòng đời của Spring Batch, nhưng kết quả nghiệp vụ cần được review. Custom ExitStatus biểu đạt phần thông tin bổ sung đó.

Không nên dùng custom ExitStatus để che giấu lỗi thực thi. Nếu writer ném exception không được retry hoặc skip, Step phải thể hiện thất bại qua trạng thái và exception phù hợp. Đặt exit code `COMPLETED` trong listener không biến một transaction đã thất bại thành thành công.

## 3. Tạo custom ExitStatus trong StepExecutionListener

Một cách phổ biến là triển khai `StepExecutionListener` và trả về ExitStatus tùy chỉnh trong `afterStep()`. Callback này chạy sau khi phần xử lý Step kết thúc, vì vậy có thể đọc các counter cuối cùng như `skipCount`, `readCount` hoặc `writeCount`.

Ví dụ, nếu Step hoàn tất nhưng có ít nhất một item bị skip, đặt exit code `COMPLETED_WITH_SKIPS`:

```java
public class ImportResultListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // Không cần xử lý trước Step.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() != BatchStatus.COMPLETED) {
            return stepExecution.getExitStatus();
        }

        int skipped = stepExecution.getSkipCount();
        if (skipped > 0) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "Import completed with " + skipped + " skipped items"
            );
        }

        return stepExecution.getExitStatus();
    }
}
```

Điều kiện `BatchStatus.COMPLETED` bảo đảm listener chỉ phân loại một Step đã hoàn tất. Nếu Step `FAILED` hoặc `STOPPED`, listener giữ nguyên ExitStatus hiện tại thay vì đổi thành một kết quả thành công.

Đăng ký listener vào Step:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer,
        ImportResultListener listener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(listener)
            .build();
}
```

`.listener(listener)` đăng ký callback cho Step. `afterStep()` không chạy sau từng chunk; nó chạy ở cấp StepExecution sau khi Step kết thúc.

## 4. Tạo custom ExitStatus trong Tasklet

Nếu kết quả nghiệp vụ được xác định ngay trong logic Tasklet, có thể đặt ExitStatus thông qua `StepContribution` trước khi trả về.

Ví dụ, Tasklet kiểm tra nguồn dữ liệu và kết thúc với `NO_DATA` nếu không có bản ghi:

```java
public class CheckInputTasklet implements Tasklet {

    private final InputRepository inputRepository;

    public CheckInputTasklet(InputRepository inputRepository) {
        this.inputRepository = inputRepository;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        if (!inputRepository.hasRecords()) {
            contribution.setExitStatus(
                    new ExitStatus("NO_DATA", "No input records were found")
            );
            return RepeatStatus.FINISHED;
        }

        return RepeatStatus.FINISHED;
    }
}
```

Tasklet trả `RepeatStatus.FINISHED` để kết thúc Step. `StepContribution.setExitStatus()` cung cấp kết quả cho StepExecution khi contribution được áp dụng.

Cách này phù hợp khi chính Tasklet biết kết quả. Nếu kết quả chỉ có thể xác định sau khi tổng hợp counter của toàn Step, `StepExecutionListener.afterStep()` thường rõ ràng hơn.

Không nên đặt ExitStatus thành công trước khi công việc thực sự hoàn tất. Nếu Tasklet tiếp tục xử lý và ném exception sau đó, trạng thái cuối cùng phải phản ánh lỗi thực thi.

## 5. Dùng custom ExitStatus để điều khiển Job flow

Job flow có thể so khớp exit code bằng `.on(...)`. Khi Step trả mã tùy chỉnh, transition tương ứng sẽ quyết định Step tiếp theo.

Ví dụ, Step import có thể kết thúc theo ba trường hợp:

- `COMPLETED`: tất cả item được xử lý bình thường.
- `COMPLETED_WITH_SKIPS`: Step hoàn tất nhưng có item bị bỏ qua.
- `FAILED`: Step thất bại.

Flow:

```text
importOrdersStep
       |
       +-- COMPLETED --------------------> publishReportStep
       |
       +-- COMPLETED_WITH_SKIPS ---------> reviewSkippedOrdersStep
       |
       +-- FAILED -----------------------> Job failed
       |
       +-- other ------------------------> fallback / fail
```

Java configuration:

```java
@Bean
public Job importJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        Step reviewSkippedOrdersStep,
        Step publishReportStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importOrdersStep)
                .on("COMPLETED_WITH_SKIPS").to(reviewSkippedOrdersStep)
            .from(importOrdersStep)
                .on("COMPLETED").to(publishReportStep)
            .from(importOrdersStep)
                .on("FAILED").fail()
            .from(importOrdersStep)
                .on("*").fail()
            .from(reviewSkippedOrdersStep)
                .on("*").to(publishReportStep)
            .from(publishReportStep)
                .on("*").end()
            .end()
            .build();
}
```

`on()` so khớp với exit code của Step. Vì vậy, khi listener trả `COMPLETED_WITH_SKIPS`, transition `.on("COMPLETED")` sẽ không được chọn cho Step đó. Cần khai báo đúng custom code mà Step thực sự trả về.

Wildcard `*` là nhánh dự phòng cho các exit code còn lại. Nên có fallback rõ ràng để Job không gặp lỗi thiếu transition khi một mã kết quả mới xuất hiện.

## 6. Exit description không dùng để định tuyến

Trong `ExitStatus`, exit code và exit description có vai trò khác nhau:

```java
new ExitStatus(
        "COMPLETED_WITH_SKIPS",
        "Skipped 7 records because their order dates were invalid"
);
```

Flow transition dùng code:

```java
.on("COMPLETED_WITH_SKIPS").to(reviewStep)
```

Description là thông tin giải thích. Không nên đưa thông tin biến động như ID item, thông điệp exception dài hoặc timestamp vào exit code, vì flow phải so khớp một tập mã ổn định.

Ví dụ không tốt:

```java
return new ExitStatus("SKIPPED_7_RECORDS_AT_2026-11-15");
```

Mã này tạo ra nhiều giá trị khác nhau theo từng lần chạy và khiến flow khó định tuyến. Nên dùng mã ổn định `COMPLETED_WITH_SKIPS`, còn số lượng và nguyên nhân ghi trong exit description hoặc log.

## 7. Quy ước đặt tên custom exit code

Custom exit code là hợp đồng giữa Step và Job flow. Tên cần ổn định, mô tả một kết quả rõ ràng và được dùng nhất quán trong listener, Tasklet, flow builder và hệ thống giám sát.

Một số quy tắc:

- Dùng chữ hoa và dấu gạch dưới theo một convention thống nhất.
- Đặt tên theo kết quả nghiệp vụ, ví dụ `NO_DATA`, `COMPLETED_WITH_SKIPS`, `NEEDS_REVIEW`.
- Không dùng mã quá chung như `OK`, `ERROR` nếu Job cần phân biệt nhiều tình huống.
- Không đưa dữ liệu động vào exit code; đưa vào exit description hoặc log.
- Không dùng custom code thành công để che lỗi kỹ thuật.
- Khi đổi code, cập nhật mọi transition phụ thuộc và dashboard/alert đang đọc code đó.
- Giữ code đủ ngắn và ổn định để có thể dùng trong metadata lâu dài.

Có thể định nghĩa constant để tránh lỗi chính tả:

```java
public final class StepExitCodes {

    public static final String NO_DATA = "NO_DATA";
    public static final String COMPLETED_WITH_SKIPS = "COMPLETED_WITH_SKIPS";
    public static final String NEEDS_REVIEW = "NEEDS_REVIEW";
    public static final String ALREADY_PROCESSED = "ALREADY_PROCESSED";

    private StepExitCodes() {
    }
}
```

Sử dụng cùng constant trong listener:

```java
return new ExitStatus(
        StepExitCodes.COMPLETED_WITH_SKIPS,
        "Skipped " + stepExecution.getSkipCount() + " items"
);
```

Và trong flow:

```java
.from(importOrdersStep)
    .on(StepExitCodes.COMPLETED_WITH_SKIPS).to(reviewSkippedOrdersStep)
```

## 8. Nhiều listener cùng thay đổi ExitStatus

Một Step có thể đăng ký nhiều listener. Các giá trị ExitStatus mà listener trả về được framework kết hợp với ExitStatus hiện tại của Step theo quy tắc `ExitStatus.and()`. Vì vậy, không nên giả định listener chạy sau sẽ luôn ghi đè hoàn toàn kết quả của listener chạy trước.

Nếu nhiều listener cùng trả custom code, kết quả kết hợp có thể không phải mã mà người viết flow dự định. Điều này đặc biệt khó hiểu khi một listener phân loại `COMPLETED_WITH_SKIPS`, còn listener khác trả `NEEDS_REVIEW`.

Các cách thiết kế dễ kiểm soát hơn:

- Tập trung logic phân loại kết quả cuối cùng vào một listener.
- Nếu có nhiều điều kiện, xác định thứ tự ưu tiên nghiệp vụ rõ ràng trong cùng một phương thức.
- Các listener chỉ ghi log/metric nên không trả custom ExitStatus mới nếu không cần thay đổi flow.
- Ghi log `stepExecution.getExitStatus()` sau khi Step kết thúc để xác nhận mã thực tế được lưu.

Ví dụ, nếu skip count lớn hơn ngưỡng thì kết quả cần là `NEEDS_REVIEW`; nếu chỉ có skip nhỏ hơn ngưỡng thì là `COMPLETED_WITH_SKIPS`. Hai điều kiện nên được xử lý trong một nơi:

```java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    if (stepExecution.getStatus() != BatchStatus.COMPLETED) {
        return stepExecution.getExitStatus();
    }

    int skipped = stepExecution.getSkipCount();
    if (skipped > 20) {
        return new ExitStatus("NEEDS_REVIEW", "Skip count exceeded 20");
    }
    if (skipped > 0) {
        return new ExitStatus("COMPLETED_WITH_SKIPS", "Some items were skipped");
    }

    return stepExecution.getExitStatus();
}
```

## 9. ExitStatus tùy chỉnh không thay đổi BatchStatus

Đây là điểm cần nhớ khi đọc metadata:

```text
StepExecution
  BatchStatus = COMPLETED
  ExitStatus  = COMPLETED_WITH_SKIPS
```

Custom ExitStatus cung cấp thông tin cho Job flow và người vận hành. Nó không tự chuyển `BatchStatus` thành `FAILED`, `STOPPED` hoặc một enum mới.

Nếu cần Job thất bại vì điều kiện nghiệp vụ, có thể thiết kế flow để kết thúc bằng `.fail()` khi nhận một mã như `VALIDATION_REJECTED`. Hoặc để Step thực sự ném exception nếu đây là lỗi thực thi. Chọn cách phù hợp với ý nghĩa của điều kiện:

- Step đã chạy xong nhưng Job cần thất bại theo quy tắc điều phối: có thể dùng custom exit code và transition `.fail()`.
- Step gặp lỗi kỹ thuật khi thực thi: để exception và BatchStatus phản ánh `FAILED`.
- Step hoàn tất nhưng cần review: giữ BatchStatus `COMPLETED`, trả custom code và chuyển đến review Step.

Đừng nhầm việc trả custom ExitStatus có chữ `FAILED` với việc StepExecution tự động có `BatchStatus.FAILED`. Nếu flow cần kết thúc thất bại, transition và terminal state phải được cấu hình tương ứng.

## 10. Phân biệt ExitStatus của Step và FlowExecutionStatus của Decider

`ExitStatus` thuộc StepExecution. Khi một Step hoàn tất, Job flow có thể đọc exit code của nó để chọn transition.

`FlowExecutionStatus` là trạng thái do `JobExecutionDecider` trả về tại một vị trí trong flow. Decider không phải Step và không thay đổi ExitStatus của Step trước đó.

| Tiêu chí | Custom ExitStatus | JobExecutionDecider |
|---|---|---|
| Nguồn tạo | Step/StepExecution hoặc listener | Phương thức `decide()` |
| Giá trị trả về | `ExitStatus` | `FlowExecutionStatus` |
| Phạm vi | Kết quả thoát của Step | Quyết định tại vị trí trong flow |
| Dùng khi | Step muốn công bố kết quả riêng | Điều kiện cần đọc nhiều thông tin để chọn nhánh |

Nếu Step đã biết kết quả như `NO_DATA` hoặc `COMPLETED_WITH_SKIPS`, custom ExitStatus thường là cách trực tiếp. Nếu cần kết hợp JobParameters, JobExecutionContext và metadata của Step trước, decider có thể phù hợp hơn.

## 11. Kiểm tra custom ExitStatus trong metadata

Sau khi Step hoàn tất, có thể đọc ExitStatus từ `StepExecution`:

```java
ExitStatus exitStatus = stepExecution.getExitStatus();

log.info(
        "step={}, batchStatus={}, exitCode={}, exitDescription={}",
        stepExecution.getStepName(),
        stepExecution.getStatus(),
        exitStatus.getExitCode(),
        exitStatus.getExitDescription()
);
```

`JobExplorer` có thể được dùng để đọc JobExecution và các StepExecution từ JobRepository. Điều này hữu ích khi dashboard cần hiển thị cả trạng thái vòng đời và kết quả nghiệp vụ của từng Step.

Với JDBC JobRepository tiêu chuẩn, thông tin StepExecution thường được lưu trong bảng `BATCH_STEP_EXECUTION`, ở các cột `STATUS`, `EXIT_CODE` và `EXIT_MESSAGE`. Tên bảng/cột có thể khác nếu schema hoặc prefix được tùy chỉnh.

Ví dụ truy vấn:

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    EXIT_MESSAGE,
    START_TIME,
    END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
```

`STATUS` là trạng thái vòng đời, `EXIT_CODE` là mã kết quả, còn `EXIT_MESSAGE` là phần mô tả. Không gộp ba trường thành một khái niệm.

JobExecution cuối cùng cũng có `BatchStatus` và `ExitStatus`. Job-level ExitStatus được xác định qua quá trình điều phối flow và kết quả của các Step. Nếu cần biết chính xác vì sao Job chọn nhánh nào, hãy kiểm tra StepExecution gây ra transition cùng JobExecution cuối cùng, thay vì chỉ xem một trường ở cấp Job.

## 12. Restart và custom ExitStatus

Custom ExitStatus được lưu cùng metadata của StepExecution. Khi Job restart, Spring Batch dựa trên trạng thái và metadata của execution trước để quyết định Step nào cần chạy lại.

Một số điểm cần lưu ý:

- Step đã `COMPLETED` thường được bỏ qua khi restart cùng JobInstance, trừ khi có cấu hình như `allowStartIfComplete(true)`.
- Custom ExitStatus không tự tạo JobInstance mới và không thay đổi identifying JobParameters.
- Nếu Job flow dùng custom exit code để chuyển sang Step review, trạng thái của Step review cũng được lưu riêng.
- Nếu cần chạy lại Step đã hoàn tất, hãy xác định rõ tác động của `allowStartIfComplete` và idempotency của side effect.
- Khi thay đổi tên custom exit code, cần xem xét các JobExecution đang dở và các transition được lưu trong phiên bản code mới.

Custom code nên ổn định qua các lần deploy. Nếu một execution cũ đã lưu `COMPLETED_WITH_SKIPS` nhưng phiên bản mới chỉ khai báo transition cho `NEEDS_REVIEW`, flow restart có thể không còn nhánh tương ứng với kết quả cũ.

## 13. Những nhầm lẫn thường gặp

**Cho rằng custom ExitStatus tạo BatchStatus mới.** `BatchStatus` là enum vòng đời; custom code thuộc ExitStatus.

**Dùng exit description để định tuyến.** Job flow so khớp exit code qua `.on(...)`. Description chỉ dành cho thông tin giải thích.

**Cho rằng `.on("COMPLETED")` vẫn khớp khi Step trả `COMPLETED_WITH_SKIPS`.** Đây là hai exit code khác nhau. Phải khai báo transition cho custom code.

**Trả mã thành công khi Step thực sự thất bại.** Điều này có thể làm flow đi sai nhánh và che giấu lỗi. Kiểm tra BatchStatus trước khi phân loại kết quả thành công.

**Cho rằng listener sau cùng ghi đè ExitStatus trước đó.** Framework kết hợp ExitStatus từ listener và trạng thái hiện tại theo quy tắc riêng. Tránh nhiều listener cạnh tranh đặt mã kết quả.

**Dùng mã động chứa ID hoặc timestamp.** Flow khó so khớp và metadata khó vận hành. Dùng mã ổn định, đưa chi tiết vào description/log.

**Cho rằng custom ExitStatus tự làm Job thất bại.** Nếu cần terminal failure, khai báo transition `.fail()` hoặc để Step thực sự thất bại theo logic xử lý.

## 14. Kiểm thử custom ExitStatus

Một bộ test nên xác nhận cả mã kết quả được tạo và nhánh Job flow được chọn:

1. Khi Step hoàn tất và không có skip, ExitStatus vẫn là `COMPLETED`.
2. Khi Step hoàn tất và có skip, ExitStatus là `COMPLETED_WITH_SKIPS`.
3. Khi Step `FAILED`, listener không đổi kết quả thành mã thành công.
4. Exit description chứa thông tin hữu ích nhưng không ảnh hưởng đến transition.
5. Job flow đi đến Step review khi nhận `COMPLETED_WITH_SKIPS`.
6. Job flow đi đến Step tiếp theo thông thường khi nhận `COMPLETED`.
7. Mã không dự kiến đi theo wildcard fallback.
8. JobExecution cuối cùng có trạng thái phù hợp với terminal transition.

Ví dụ unit test listener:

```java
@Test
void returnsCompletedWithSkipsWhenStepCompletedWithSkippedItems() {
    StepExecution stepExecution = new StepExecution("importOrdersStep", null);
    stepExecution.setStatus(BatchStatus.COMPLETED);
    stepExecution.setExitStatus(ExitStatus.COMPLETED);
    stepExecution.setReadSkipCount(2);

    ImportResultListener listener = new ImportResultListener();
    ExitStatus result = listener.afterStep(stepExecution);

    assertEquals("COMPLETED_WITH_SKIPS", result.getExitCode());
    assertTrue(result.getExitDescription().contains("2 skipped items"));
}
```

Đây là test minh họa cho listener. Integration test với JobRepository và Job flow mới xác nhận được transition thực tế và metadata cuối cùng.

## 15. Cách thiết kế custom ExitStatus

Hãy tạo custom ExitStatus khi Step cần công bố một kết quả nghiệp vụ cụ thể để Job flow hoặc công cụ vận hành phân biệt. Chọn exit code ổn định, ngắn gọn và có quy ước; dùng exit description để giải thích số lượng, nguyên nhân hoặc dữ liệu liên quan.

Đặt mã trong `StepExecutionListener.afterStep()` khi kết quả phụ thuộc counter cuối cùng, hoặc trong `Tasklet` qua `StepContribution` khi logic của Tasklet đã biết kết quả. Khai báo transition `.on(...)` cho từng mã và có wildcard fallback. Giữ nguyên BatchStatus phản ánh đúng vòng đời thực thi, không dùng custom ExitStatus để che lỗi. Kiểm tra cả metadata của Step và Job để xác nhận flow đã đi đúng nhánh.

Khi được thiết kế như một hợp đồng rõ ràng giữa Step và Job flow, custom ExitStatus giúp quy trình batch biểu diễn các kết quả nghiệp vụ phong phú mà vẫn giữ trạng thái thực thi và điều phối nhất quán.
