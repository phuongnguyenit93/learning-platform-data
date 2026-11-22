# Status khi skip vẫn hoàn tất trong Spring Batch

Trong Spring Batch, một step có thể bỏ qua một số item lỗi và vẫn kết thúc thành công. Nếu exception thuộc skip policy, tổng số item bị skip không vượt quá giới hạn và các phần việc còn lại hoàn tất, step thường có `BatchStatus.COMPLETED`. Job cũng có thể kết thúc `COMPLETED` dù `StepExecution` ghi nhận read skip, process skip hoặc write skip.

Điều này là hành vi có chủ đích: skip cho phép batch tiếp tục xử lý dữ liệu hợp lệ khi một số bản ghi riêng lẻ không thể xử lý. Tuy nhiên, trạng thái `COMPLETED` không có nghĩa mọi item đều được xử lý thành công. Muốn đánh giá chất lượng kết quả, cần đọc cả status, exit status và các bộ đếm skip.

## 1. Vì sao step có skip vẫn có thể COMPLETED?

Skip là một nhánh xử lý lỗi được cấu hình trước. Khi một item gây exception và exception đó được cho phép skip, Spring Batch loại item đó khỏi luồng xử lý và tiếp tục với những item còn lại.

Ví dụ, một file có 1.000 dòng. Hai dòng không hợp lệ được skip, 998 dòng còn lại được xử lý và ghi thành công. Nếu skip limit cho phép ít nhất hai lỗi, không có lỗi nghiêm trọng nào khác và flow hoàn tất bình thường, step có thể kết thúc với:

```text
BatchStatus = COMPLETED
ExitStatus  = COMPLETED
readSkipCount = 2
processSkipCount = 0
writeSkipCount = 0
skipCount = 2
```

Skip count cho biết có item bị bỏ qua; `BatchStatus.COMPLETED` cho biết step đã hoàn thành theo chính sách đã cấu hình. Hai thông tin này không mâu thuẫn.

Spring Batch không tự xem mọi skip là thất bại. Chính ứng dụng xác định loại exception được phép bỏ qua và số lượng skip tối đa. Khi các điều kiện đó được đáp ứng, việc tiếp tục và hoàn tất step là kết quả hợp lệ.

## 2. Cấu hình một step có thể skip

Để step cho phép skip, cần bật fault tolerance và khai báo exception cùng skip limit:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, OrderEntity> processor,
        ItemWriter<OrderEntity> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(20)
        .build();
}
```

Với cấu hình trên:

- `InvalidOrderException` và `FlatFileParseException` được xem là loại lỗi có thể skip.
- `skipLimit(20)` giới hạn tổng số skip trong step.
- Nếu số skip không vượt giới hạn và không có lỗi khác, step có thể hoàn tất bình thường.
- Exception không thuộc policy hoặc vượt skip limit có thể làm step thất bại.

Nếu không cấu hình skip limit, giá trị mặc định là 0. Vì vậy, chỉ khai báo loại exception mà không đặt một giới hạn dương không có nghĩa step sẽ tự động chấp nhận skip.

Không nên cho phép skip mọi exception chỉ để job có trạng thái thành công. Lỗi kết nối, lỗi xác thực, lỗi cấu hình hoặc bug trong processor thường cần làm step thất bại thay vì bỏ qua.

## 3. BatchStatus và ExitStatus là hai khái niệm khác nhau

Spring Batch lưu cả `BatchStatus` và `ExitStatus` cho job/step execution. Chúng liên quan nhưng không đồng nghĩa.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `BatchStatus` | Trạng thái vòng đời thực thi do Spring Batch quản lý. | `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`. |
| `ExitStatus` | Mã kết quả được dùng để mô tả kết quả và điều hướng flow. | `COMPLETED`, `FAILED`, `NOOP` hoặc mã tùy chỉnh. |

Khi step skip item trong giới hạn và kết thúc bình thường, trạng thái mặc định thường là:

```text
StepExecution:
  status     = COMPLETED
  exitStatus = COMPLETED
  skipCount  = 2
```

`skipCount` là số liệu bổ sung. Nó không tự động đổi `BatchStatus` thành `FAILED`, cũng không tự động đổi `ExitStatus` thành một mã như `COMPLETED WITH SKIPS`.

Ứng dụng có thể tùy chỉnh `ExitStatus` nếu muốn flow phân biệt step hoàn tất sạch với step hoàn tất nhưng có skip. Việc tùy chỉnh exit code không nhất thiết làm thay đổi `BatchStatus`.

## 4. Job có thể COMPLETED dù một step có skip

Job thường được điều phối qua một hoặc nhiều step. Nếu một step hoàn tất với skip count dương nhưng vẫn trong giới hạn, flow có thể tiếp tục sang step kế tiếp. Nếu các step cần thiết khác cũng hoàn tất và không có transition nào làm job thất bại hoặc dừng, job có thể kết thúc `BatchStatus.COMPLETED`.

Ví dụ:

```text
ImportStep
  BatchStatus = COMPLETED
  ExitStatus  = COMPLETED
  skipCount   = 2
        |
        v
ReportStep
  BatchStatus = COMPLETED
  ExitStatus  = COMPLETED
        |
        v
JobExecution
  BatchStatus = COMPLETED
  ExitStatus  = COMPLETED
```

Job status phản ánh kết quả điều phối tổng thể. Nó không phải phép khẳng định rằng tất cả record nguồn đều được ghi thành công. Muốn biết dữ liệu có bị bỏ qua hay không, phải xem skip counters của từng `StepExecution`.

Nếu job có nhiều step, một step trước có skip không nhất thiết ngăn step sau chạy. Điều đó phụ thuộc flow và exit status mà step trả về.

## 5. Khi nào skip vẫn dẫn đến FAILED?

Skip chỉ được chấp nhận khi exception thuộc skip policy và giới hạn chưa bị vượt. Một số tình huống vẫn khiến step thất bại:

- Exception không thuộc loại được phép skip.
- Tổng skip vượt `skipLimit`.
- Reader hoặc writer không thể tiếp tục an toàn sau lỗi.
- Listener hoặc thao tác lưu thông tin skip phát sinh lỗi không được xử lý.
- Lỗi hạ tầng hoặc lỗi lập trình khác xảy ra trong cùng step.
- Step bị dừng hoặc bị đánh dấu thất bại bởi logic khác.

Ví dụ, step cho phép tối đa 10 skip nhưng có 11 item gây lỗi:

```text
Skip 1..10  -> được chấp nhận
Skip 11     -> vượt skipLimit
Step        -> FAILED
Job         -> thường FAILED nếu flow không xử lý nhánh lỗi
```

Khi vượt giới hạn, Spring Batch có thể ném `SkipLimitExceededException`. `noRollback(...)` không làm tăng skip limit và không biến exception vượt giới hạn thành một skip hợp lệ.

## 6. Skip limit là tổng của read, process và write

Skip limit tiêu chuẩn áp dụng chung cho ba giai đoạn đọc, xử lý và ghi. Nó không phải ba giới hạn riêng.

Ví dụ `skipLimit(5)`:

| Phase | Số item bị skip |
| --- | ---: |
| Read | 2 |
| Process | 2 |
| Write | 1 |
| **Tổng** | **5** |

Nếu có item tiếp theo cần skip, tổng sẽ vượt giới hạn và step thất bại. Để theo dõi nguyên nhân, nên xem từng bộ đếm thay vì chỉ nhìn tổng skip count.

Các thuộc tính thường dùng trên `StepExecution`:

- `getReadSkipCount()`
- `getProcessSkipCount()`
- `getWriteSkipCount()`
- `getSkipCount()`

Ngoài ra, `readCount`, `writeCount` và `filterCount` giúp hiểu khối lượng dữ liệu qua các phase. `filterCount` là số item processor chủ động loại bằng cách trả về `null`, không phải skip và không làm tăng skip count.

## 7. Skip khác filter và retry

Không phải mọi item không xuất hiện trong output đều là skip:

| Cơ chế | Điều gì xảy ra? | Ảnh hưởng đến skip count |
| --- | --- | --- |
| Skip | Exception được policy chấp nhận và item bị bỏ qua. | Tăng bộ đếm skip tương ứng. |
| Filter | Processor trả về `null` theo quy tắc nghiệp vụ. | Không tăng skip count; tăng `filterCount`. |
| Retry rồi thành công | Thao tác lỗi được thử lại và cuối cùng thành công. | Không tính item đó là skip. |
| Fail | Exception không được retry/skip hoặc giới hạn bị vượt. | Step thất bại. |

Ví dụ, order đã hủy có thể được filter vì không cần xử lý. Order thiếu dữ liệu bắt buộc có thể ném `InvalidOrderException` và được skip. Lỗi database tạm thời có thể được retry. Ba trường hợp cần được theo dõi riêng vì chúng có ý nghĩa nghiệp vụ khác nhau.

## 8. Đọc status và skip count từ StepExecution

Sau khi step chạy, có thể đọc trạng thái và bộ đếm từ `StepExecution`:

```java
public class StepResultLogger implements StepExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(StepResultLogger.class);

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
            "step={}, batchStatus={}, exitStatus={}, read={}, written={}, " +
            "filtered={}, readSkips={}, processSkips={}, writeSkips={}, totalSkips={}",
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getExitStatus().getExitCode(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getFilterCount(),
            stepExecution.getReadSkipCount(),
            stepExecution.getProcessSkipCount(),
            stepExecution.getWriteSkipCount(),
            stepExecution.getSkipCount()
        );
        return null;
    }
}
```

Listener có thể được đăng ký trực tiếp với step:

```java
.listener(new StepResultLogger())
```

Không nên chỉ log `BatchStatus`. Một dòng log có cả `status`, `exitStatus` và skip counters sẽ giúp người vận hành nhận ra step đã hoàn tất nhưng có bỏ qua item.

Với job chạy nhiều step hoặc partition, hãy log theo `jobExecutionId`, `stepExecutionId` và partition name nếu có. Nhờ vậy có thể tìm đúng execution gây ra skip.

## 9. Truy vấn kết quả sau khi job hoàn tất

`JobExplorer` có thể dùng để đọc execution đã được lưu trong `JobRepository`. Điều này hữu ích cho màn hình vận hành hoặc báo cáo sau khi job kết thúc:

```java
JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    log.info(
        "job={}, status={}, exitStatus={}",
        execution.getJobInstance().getJobName(),
        execution.getStatus(),
        execution.getExitStatus().getExitCode()
    );

    for (StepExecution step : execution.getStepExecutions()) {
        log.info(
            "step={}, status={}, exitStatus={}, skips={}",
            step.getStepName(),
            step.getStatus(),
            step.getExitStatus().getExitCode(),
            step.getSkipCount()
        );
    }
}
```

Trong production, nên lưu `JobExecutionId` cùng batch ID hoặc business date để truy vấn đúng lần chạy. Không nên chỉ tìm execution mới nhất theo tên job nếu nhiều instance chạy đồng thời.

Nếu step được partition, manager step và worker step có execution riêng. Tổng skip của job cần được tổng hợp từ các worker execution phù hợp; không giả định một con số ở manager tự động mô tả đầy đủ mọi partition.

## 10. Hiển thị trạng thái “COMPLETED WITH SKIPS”

Trạng thái mặc định `COMPLETED` có thể chưa đủ thông tin cho vận hành. Ứng dụng có thể đặt một custom `ExitStatus` khi step hoàn tất nhưng có item bị skip.

Ví dụ:

```java
public class SkipExitStatusListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {
            return new ExitStatus("COMPLETED WITH SKIPS");
        }
        return null;
    }
}
```

Đăng ký listener:

```java
return new StepBuilder("importOrdersStep", jobRepository)
    .<Order, OrderEntity>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(InvalidOrderException.class)
    .skipLimit(20)
    .listener(new SkipExitStatusListener())
    .build();
```

Sau khi listener chạy, kết quả có thể được biểu diễn như sau:

```text
BatchStatus = COMPLETED
ExitStatus  = COMPLETED WITH SKIPS
skipCount   = 2
```

Đây là mã `ExitStatus` tùy chỉnh do ứng dụng định nghĩa. Nó không phải một giá trị `BatchStatus` mới và không có nghĩa job bị FAILED. Dùng custom exit code khi cần điều hướng flow hoặc hiển thị cảnh báo mà vẫn coi step đã hoàn tất theo chính sách.

## 11. Điều hướng flow dựa trên ExitStatus

Job flow thường dùng `ExitStatus` của step để quyết định bước tiếp theo. Khi custom listener trả về `COMPLETED WITH SKIPS`, job có thể chuyển sang step kiểm tra dữ liệu lỗi:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        Step reviewRejectedOrdersStep,
        Step publishReportStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(importOrdersStep)
            .on("COMPLETED WITH SKIPS").to(reviewRejectedOrdersStep)
        .from(importOrdersStep)
            .on("COMPLETED").to(publishReportStep)
        .from(reviewRejectedOrdersStep)
            .on("*").to(publishReportStep)
        .end()
        .build();
}
```

Trong flow này:

- Step hoàn tất không có skip trả về `COMPLETED` và đi thẳng đến `publishReportStep`.
- Step hoàn tất có skip trả về `COMPLETED WITH SKIPS` và đi qua `reviewRejectedOrdersStep`.
- Cả hai nhánh vẫn có thể hoàn tất job thành công nếu các step tiếp theo thành công.

Thứ tự và pattern transition cần được thiết kế rõ ràng. `on(...)` so khớp exit code, không phải `BatchStatus`. Nếu muốn dừng hoặc đánh dấu job thất bại, cần cấu hình transition/flow tương ứng; chỉ đổi exit code thành `COMPLETED WITH SKIPS` không tự làm job thất bại.

## 12. Dùng JobExecutionDecider để quyết định theo skip count

Nếu điều kiện điều hướng phức tạp hơn một exit code, có thể dùng `JobExecutionDecider`. Decider nhận `JobExecution` và `StepExecution` hiện tại, rồi trả về `FlowExecutionStatus`.

Ví dụ:

```java
public class SkipCountDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (stepExecution != null && stepExecution.getSkipCount() > 0) {
            return new FlowExecutionStatus("HAS_SKIPS");
        }

        return new FlowExecutionStatus("NO_SKIPS");
    }
}
```

Flow có thể dùng kết quả decider để chọn nhánh:

```java
return new JobBuilder("importJob", jobRepository)
    .start(importOrdersStep)
    .next(skipCountDecider)
        .on("HAS_SKIPS").to(reviewRejectedOrdersStep)
    .from(skipCountDecider)
        .on("NO_SKIPS").to(publishReportStep)
    .from(reviewRejectedOrdersStep)
        .on("*").to(publishReportStep)
    .end()
    .build();
```

`FlowExecutionStatus` là trạng thái điều hướng flow. Nó cũng không phải `BatchStatus`. Decider nên đọc dữ liệu execution đã được cập nhật và tránh thực hiện side effect nghiệp vụ trong lúc quyết định nhánh.

## 13. SkipListener dùng để lưu thông tin item bị bỏ qua

Status và skip count cho biết có lỗi, nhưng không cho biết cụ thể item nào bị skip. `SkipListener` giúp ghi nhận định danh và nguyên nhân ở từng phase:

```java
public class OrderSkipListener
        implements SkipListener<Order, OrderEntity> {

    private final RejectedOrderRepository repository;

    public OrderSkipListener(RejectedOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        repository.save(RejectedOrder.fromReadError(t));
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        repository.save(RejectedOrder.fromOrder(item, t));
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        repository.save(RejectedOrder.fromEntity(item, t));
    }
}
```

Read skip không có item hợp lệ để truyền vào callback; ứng dụng cần lấy thông tin nguồn từ exception nếu có, chẳng hạn file name và line number. Process skip nhận item đầu vào; write skip nhận item đầu ra.

Listener có thể ghi lỗi vào bảng quarantine cùng database transaction của step. Nếu ghi sang resource ngoài transaction, cần idempotency vì retry, restart hoặc redelivery có thể tạo tác động lặp. Không nên coi custom exit status hoặc skip count là thay thế cho danh sách record lỗi cần đối soát.

## 14. Báo cáo chất lượng dữ liệu khi job COMPLETED

Một job có thể hoàn tất thành công về mặt điều phối nhưng vẫn có chất lượng dữ liệu không đạt yêu cầu. Vì vậy, báo cáo vận hành nên kết hợp:

- `BatchStatus` và `ExitStatus` của job.
- Status và exit code của từng step.
- Read, process và write skip count.
- Filter count.
- Số item đọc và ghi.
- Tỷ lệ skip so với số item được xem xét.
- Nhóm exception và nguyên nhân skip.
- Danh sách item lỗi trong quarantine.

Ví dụ, một job có thể hiển thị:

```text
Job: importOrders
Status: COMPLETED
Exit status: COMPLETED WITH SKIPS

Step: importOrdersStep
Read: 1000
Written: 990
Filtered: 5
Read skips: 2
Process skips: 3
Write skips: 0
Total skips: 5
```

Các số trong ví dụ chỉ minh họa cách trình bày; không nên suy ra công thức cố định giữa read, write, filter và skip vì các phase có thể có số lượng khác nhau. Báo cáo nên lấy trực tiếp counters từ `StepExecution` và dữ liệu nghiệp vụ đã ghi.

Tỷ lệ skip cần được tính theo mẫu số phù hợp với nghiệp vụ. Ví dụ, tỷ lệ process skip trên số item đã đọc thành công có thể khác tỷ lệ read skip trên tổng số bản ghi nguồn. Đặt ngưỡng cảnh báo dựa trên dữ liệu lịch sử và yêu cầu chất lượng, không dùng một ngưỡng chung cho mọi job.

## 15. Kiểm thử trường hợp skip nhưng step vẫn COMPLETED

Integration test nên xác nhận cả status lẫn skip counters. Ví dụ một processor ném `InvalidOrderException` cho một item, step cho phép skip và writer ghi các item còn lại:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

StepExecution step = execution.getStepExecutions()
    .stream()
    .filter(s -> s.getStepName().equals("importOrdersStep"))
    .findFirst()
    .orElseThrow();

assertThat(step.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(step.getProcessSkipCount()).isEqualTo(1);
assertThat(step.getSkipCount()).isEqualTo(1);
assertThat(orderRepository.count()).isEqualTo(expectedValidOrders);
```

Test này chứng minh hai sự thật cùng lúc: step đã hoàn tất theo policy và có một item bị skip. Nếu listener đặt custom exit status, có thể thêm assertion:

```java
assertThat(step.getExitStatus().getExitCode())
    .isEqualTo("COMPLETED WITH SKIPS");
```

Không nên chỉ assert `JobExecution` là `COMPLETED`. Cần xác nhận đúng step và đúng skip counter, vì một job nhiều step có thể hoàn tất dù một step trước đó có skip.

## 16. Kiểm thử skip limit bị vượt

Tạo test riêng với số item lỗi lớn hơn `skipLimit`. Ví dụ limit bằng 2 nhưng processor ném exception cho ba item:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(2)
```

Kết quả mong đợi là step thất bại khi skip tiếp theo vượt giới hạn. Kiểm tra:

- `StepExecution.getStatus()` là `FAILED`.
- Failure exception phản ánh `SkipLimitExceededException` hoặc nguyên nhân tương ứng theo phiên bản/framework.
- Các chunk đã commit trước đó vẫn giữ dữ liệu.
- Chunk hiện tại tuân theo rollback behavior của exception và transaction configuration.
- Job status phản ánh nhánh flow cuối cùng.

Đây là test quan trọng để phân biệt “skip được chấp nhận và hoàn tất” với “skip vượt ngưỡng và thất bại”.

## 17. Kiểm thử custom ExitStatus

Nếu ứng dụng dùng `COMPLETED WITH SKIPS`, cần kiểm tra cả status và exit code:

```java
assertThat(stepExecution.getStatus())
    .isEqualTo(BatchStatus.COMPLETED);

assertThat(stepExecution.getExitStatus().getExitCode())
    .isEqualTo("COMPLETED WITH SKIPS");
```

Sau đó kiểm tra flow đi đúng nhánh. Với job có `reviewRejectedOrdersStep`, xác nhận step này được thực thi khi skip count dương và bị bỏ qua khi không có skip.

Nếu một listener khác cũng thay đổi `ExitStatus`, cần kiểm tra cách các exit status được kết hợp. Tránh nhiều listener cùng ghi đè exit code mà không có quy ước rõ ràng.

## 18. Các lỗi thường gặp khi đọc status

**Thấy COMPLETED rồi kết luận mọi item đều thành công:** status phản ánh kết quả step/job, không phải tỷ lệ item thành công. Xem skip counters và dữ liệu quarantine.

**Cho rằng mọi skip làm step FAILED:** skip nằm trong policy và dưới limit có thể cho step hoàn tất bình thường.

**Nhầm BatchStatus với ExitStatus:** một step có thể có `BatchStatus.COMPLETED` nhưng custom `ExitStatus` là `COMPLETED WITH SKIPS`.

**Cho rằng skip count là filter count:** filter là item processor chủ động loại bằng `null`; skip là item bị bỏ qua do exception.

**Chỉ cấu hình skip class mà quên skip limit:** mặc định limit là 0; không có nghĩa item lỗi tự động được bỏ qua.

**Không phân biệt read/process/write skip:** mỗi phase có bộ đếm và dữ liệu lỗi khác nhau; read skip thường không có item object.

**Đổi ExitStatus nhưng kỳ vọng BatchStatus đổi theo:** custom exit code dùng cho flow/monitoring, không tự biến execution thành FAILED.

**Không kiểm tra downstream flow:** step có skip vẫn có thể kích hoạt nhánh cần review hoặc tiếp tục như bình thường tùy exit status.

**Không lưu định danh item lỗi:** counters chỉ cho biết số lượng; cần `SkipListener` hoặc quarantine store để biết record nào bị bỏ qua.

## 19. Cách thiết kế status và skip trong production

Trước tiên, xác định rõ loại lỗi nào được phép skip và đặt `skipLimit` dựa trên yêu cầu chất lượng dữ liệu. Giữ lỗi hạ tầng, cấu hình và bug ngoài skip policy để step dừng khi không thể tiếp tục an toàn.

Tiếp theo, thiết kế cách vận hành muốn nhìn thấy kết quả. Nếu `COMPLETED` cùng skip counters đã đủ, giữ exit status mặc định và hiển thị counters trong dashboard. Nếu flow cần phân biệt step sạch với step có skip, dùng `StepExecutionListener.afterStep()` để trả về custom `ExitStatus` như `COMPLETED WITH SKIPS`, hoặc dùng `JobExecutionDecider` để chọn nhánh dựa trên skip count.

Lưu thông tin item lỗi bằng `SkipListener` và quarantine store khi cần đối soát. Theo dõi riêng read/process/write skip, filter count và tổng số item ghi. Kiểm thử cả trường hợp skip trong giới hạn, vượt giới hạn, custom exit status và downstream transition.

Trong Spring Batch, một job có skip vẫn có thể hoàn tất thành công vì skip là một phần của fault-tolerance policy. `COMPLETED` cho biết flow đã hoàn tất theo cấu hình; skip counters cho biết một số item đã bị bỏ qua. Khi đọc cả hai loại thông tin và thiết kế exit status/monitoring phù hợp, hệ thống có thể báo cáo trung thực kết quả mà vẫn tận dụng được khả năng tiếp tục xử lý của batch.
