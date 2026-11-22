# BatchStatus và ExitStatus

Trong Spring Batch, `BatchStatus` và `ExitStatus` đều mô tả kết quả thực thi của job hoặc step, nhưng chúng phục vụ hai mục đích khác nhau. `BatchStatus` biểu thị trạng thái vòng đời mà framework quản lý, chẳng hạn đang chạy, hoàn thành, thất bại hoặc bị dừng. `ExitStatus` mô tả mã kết thúc và thông tin bổ sung của lần thực thi; mã này thường được dùng để quyết định luồng tiếp theo của job.

Ví dụ, một step có thể xử lý xong tất cả item nhưng có một số item bị skip theo chính sách. Framework có thể đánh dấu `BatchStatus.COMPLETED`, trong khi ứng dụng đặt `ExitStatus` thành `COMPLETED_WITH_SKIPS`. Nhờ vậy, hệ thống vẫn biết step đã kết thúc bình thường về mặt thực thi, đồng thời flow có thể chuyển sang step rà soát dữ liệu bị bỏ qua.

Hai loại status thường có cùng mã mặc định như `COMPLETED` hoặc `FAILED`, nên dễ bị nhầm là một. Khi thiết kế flow, cần hiểu `on(...)` so khớp với exit code của step; nó không trực tiếp so khớp enum `BatchStatus`.

## 1. BatchStatus là gì?

`BatchStatus` là enum do Spring Batch định nghĩa để biểu diễn trạng thái thực thi của `JobExecution` hoặc `StepExecution`. Nó cho biết framework xem lần thực thi đang ở giai đoạn nào hoặc đã kết thúc ra sao.

Các giá trị thường gặp:

| BatchStatus | Ý nghĩa |
|---|---|
| `STARTING` | Execution đang được khởi tạo |
| `STARTED` | Job hoặc step đang thực thi |
| `STOPPING` | Đang xử lý yêu cầu dừng |
| `STOPPED` | Execution đã dừng theo yêu cầu hoặc cơ chế stop |
| `COMPLETED` | Execution hoàn tất bình thường theo góc nhìn framework |
| `FAILED` | Execution thất bại do lỗi không được xử lý thành công |
| `ABANDONED` | Execution được đánh dấu không tiếp tục restart theo cách thông thường |
| `UNKNOWN` | Không xác định được trạng thái đáng tin cậy; thường cần điều tra |

`BatchStatus` được framework cập nhật trong vòng đời thực thi. Ứng dụng thường đọc nó qua `JobExecution.getStatus()` hoặc `StepExecution.getStatus()` để biết execution đang chạy, đã hoàn tất hay thất bại.

Ví dụ:

```java
BatchStatus jobStatus = jobExecution.getStatus();
BatchStatus stepStatus = stepExecution.getStatus();

if (jobStatus == BatchStatus.COMPLETED) {
    log.info("Job execution completed");
} else if (jobStatus == BatchStatus.FAILED) {
    log.error("Job execution failed");
}
```

Không nên tự đặt `BatchStatus` tùy ý để điều khiển nghiệp vụ. Hãy để framework quản lý trạng thái vòng đời thông qua kết quả thực thi, exception, thao tác stop/abandon và flow transition phù hợp.

## 2. ExitStatus là gì?

`ExitStatus` là một value object mô tả kết quả kết thúc của job hoặc step. Nó gồm hai phần chính:

- `exitCode`: mã kết thúc, thường là chuỗi như `COMPLETED`, `FAILED`, `STOPPED` hoặc mã tùy chỉnh do ứng dụng định nghĩa.
- `exitDescription`: mô tả bổ sung, thường dùng để ghi nguyên nhân, ngữ cảnh hoặc thông tin giải thích kết quả.

Một số giá trị hằng có sẵn:

| ExitStatus | Ý nghĩa thường dùng |
|---|---|
| `ExitStatus.EXECUTING` | Execution đang thực thi |
| `ExitStatus.COMPLETED` | Hoàn tất bình thường |
| `ExitStatus.NOOP` | Không có thao tác thực tế cần thực hiện |
| `ExitStatus.FAILED` | Thực thi thất bại |
| `ExitStatus.STOPPED` | Thực thi bị dừng |
| `ExitStatus.UNKNOWN` | Kết quả không xác định |

Ứng dụng có thể tạo mã riêng:

```java
ExitStatus status = new ExitStatus(
        "COMPLETED_WITH_SKIPS",
        "Step completed with skipped records");
```

Mã tùy chỉnh giúp flow phản ánh kết quả nghiệp vụ chi tiết hơn các trạng thái mặc định. Ví dụ, `COMPLETED_WITH_SKIPS`, `COMPLETED_WITH_WARNINGS` hoặc `NO_DATA` có thể được dùng để phân nhánh nếu chúng mang ý nghĩa rõ ràng trong quy trình.

`ExitStatus` không phải enum; mã kết thúc là chuỗi và có thể mở rộng theo ứng dụng. Vì vậy, cần thống nhất tên mã giữa listener, flow transition, dashboard và kiểm thử. Tránh dùng nhiều cách viết khác nhau cho cùng một kết quả.

## 3. Khác biệt cốt lõi giữa BatchStatus và ExitStatus

| Tiêu chí | BatchStatus | ExitStatus |
|---|---|---|
| Kiểu dữ liệu | Enum do Spring Batch định nghĩa | Value object gồm exit code và exit description |
| Mục đích | Trạng thái vòng đời thực thi | Mã kết quả và thông tin kết thúc |
| Giá trị | Tập giá trị cố định như `STARTED`, `COMPLETED`, `FAILED` | Giá trị chuẩn hoặc mã tùy chỉnh như `COMPLETED_WITH_SKIPS` |
| Ai quản lý | Chủ yếu do framework quản lý | Framework đặt giá trị mặc định; ứng dụng có thể bổ sung mã kết thúc qua listener/flow |
| Dùng trong flow | Không phải giá trị được `on(...)` so khớp trực tiếp | Exit code được dùng để so khớp transition |
| Truy cập | `execution.getStatus()` | `execution.getExitStatus()` |

Ví dụ một step xử lý 1.000 bản ghi, ghi thành công 990 bản ghi và skip 10 bản ghi theo chính sách. Step có thể kết thúc với:

```text
BatchStatus = COMPLETED
ExitStatus  = COMPLETED_WITH_SKIPS
```

Điều này không mâu thuẫn. `BatchStatus` nói rằng step hoàn tất theo cơ chế thực thi; `ExitStatus` nói rằng kết quả có một đặc điểm mà flow cần biết.

Ngược lại, nếu writer ném lỗi không được xử lý, step thường có:

```text
BatchStatus = FAILED
ExitStatus  = FAILED
```

Các giá trị mặc định thường tương ứng nhau, nhưng không bắt buộc mọi mã `ExitStatus` đều phải trùng tên với một giá trị `BatchStatus`.

## 4. Đọc cả hai status sau khi job chạy

Sau khi `JobLauncher` trả về `JobExecution` trong chế độ đồng bộ, có thể đọc trạng thái job và từng step:

```java
JobExecution jobExecution =
        jobLauncher.run(importJob, jobParameters);

log.info("Job status={}, exitCode={}, exitDescription={}",
        jobExecution.getStatus(),
        jobExecution.getExitStatus().getExitCode(),
        jobExecution.getExitStatus().getExitDescription());

for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
    log.info("Step {} status={}, exitCode={}",
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getExitStatus().getExitCode());
}
```

Nếu job chạy bất đồng bộ, `JobLauncher.run()` có thể trả về khi job mới bắt đầu hoặc được gửi sang executor. Khi đó, status trong object trả về chưa phải trạng thái cuối. Hãy dùng `JobExplorer` với execution ID để tải trạng thái mới nhất sau đó.

Ví dụ:

```java
JobExecution latest = jobExplorer.getJobExecution(executionId);
if (latest != null) {
    BatchStatus batchStatus = latest.getStatus();
    ExitStatus exitStatus = latest.getExitStatus();
}
```

Không nên chỉ đọc status của job mà bỏ qua từng step. Một job nhiều step có thể có step đầu hoàn thành, step tiếp theo thất bại và step sau chưa được thực thi. `StepExecution` giúp xác định chính xác giai đoạn xảy ra vấn đề.

## 5. ExitStatus mặc định được tạo như thế nào?

Trong trường hợp thông thường, Spring Batch tự đặt `ExitStatus` phù hợp với kết quả step:

- Step hoàn tất bình thường thường có `ExitStatus.COMPLETED`.
- Step thất bại do exception không được xử lý thường có `ExitStatus.FAILED`.
- Step bị dừng thường có `ExitStatus.STOPPED`.
- Step không có công việc cần thực hiện có thể có kết quả `NOOP` trong một số tình huống.

Ứng dụng không cần tự tạo `ExitStatus.COMPLETED` sau mọi step thành công. Chỉ bổ sung mã tùy chỉnh khi flow hoặc hệ thống vận hành cần phân biệt một kết quả cụ thể.

`ExitStatus` cũng có phần mô tả. Có thể bổ sung thông tin giải thích khi cần điều tra, nhưng không nên đưa secret, token hoặc payload nhạy cảm vào description vì metadata có thể được hiển thị trong dashboard hoặc log.

## 6. Tùy chỉnh ExitStatus bằng StepExecutionListener

Một cách phổ biến để đặt exit code tùy chỉnh là dùng `StepExecutionListener.afterStep()`. Listener có thể đọc bộ đếm hoặc dữ liệu trong `StepExecution`, rồi trả về một `ExitStatus` mới.

Ví dụ: nếu step có item bị skip, đặt mã kết thúc `COMPLETED_WITH_SKIPS`:

```java
public class SkipAwareStepListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getSkipCount() > 0) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "One or more items were skipped");
        }

        return null;
    }
}
```

Trả về `null` nghĩa là listener không yêu cầu thay đổi exit status hiện có. Khi trả về status khác, Spring Batch kết hợp nó với exit status hiện tại của step. Nên chọn mã có quy ước rõ và tránh ghi đè thông tin lỗi thật bằng một mã có vẻ thành công.

Đăng ký listener với step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer,
        SkipAwareStepListener skipAwareStepListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .listener(skipAwareStepListener)
            .build();
}
```

Khi step hoàn thành với một hoặc nhiều item bị skip, listener có thể đặt mã `COMPLETED_WITH_SKIPS`. `BatchStatus` vẫn có thể là `COMPLETED`; mã exit tùy chỉnh cung cấp thêm thông tin cho flow.

Không dùng `afterStep()` để thay đổi trạng thái tùy tiện sau khi step thất bại. Nếu exception làm step thất bại, mã `FAILED` và thông tin lỗi cần được giữ nguyên trừ khi có một quy tắc flow/exit rõ ràng đã được thiết kế và kiểm thử.

## 7. Dùng ExitStatus để điều khiển flow

Trong job nhiều step, `.on(...)` được dùng để khai báo transition dựa trên exit code của step trước. Đây là lý do `ExitStatus` rất quan trọng với chương Flow.

Ví dụ, sau khi nhập đơn hàng:

- Nếu không có item bị skip (`COMPLETED`), tiếp tục công bố kết quả.
- Nếu có item bị skip (`COMPLETED_WITH_SKIPS`), chuyển sang step rà soát dữ liệu lỗi.
- Nếu step thất bại (`FAILED`), kết thúc job theo trạng thái thất bại.

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        Step reviewSkippedOrdersStep,
        Step publishOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
                .on("COMPLETED_WITH_SKIPS").to(reviewSkippedOrdersStep)
            .from(importOrdersStep)
                .on("COMPLETED").to(publishOrdersStep)
            .from(importOrdersStep)
                .on("*").fail()
            .end()
            .build();
}
```

Trong ví dụ, `on("COMPLETED_WITH_SKIPS")` so khớp exit code tùy chỉnh. `on("COMPLETED")` so khớp kết quả hoàn tất bình thường. Transition `on("*")` là nhánh dự phòng cho các exit code khác và kết thúc flow theo kết quả fail.

Các transition cần bao phủ những kết quả mà step có thể trả về. Nếu bỏ sót một mã exit code, flow có thể không tìm được transition phù hợp và job có thể kết thúc với lỗi điều khiển flow. Với các flow quan trọng, nên định nghĩa nhánh mặc định có chủ đích.

## 8. Wildcard trong transition

`on(...)` hỗ trợ pattern để so khớp exit code. Các pattern thường dùng:

- `on("COMPLETED")`: khớp chính xác mã `COMPLETED`.
- `on("FAILED")`: khớp chính xác mã `FAILED`.
- `on("COMPLETED_*")`: khớp các mã bắt đầu bằng `COMPLETED_` theo quy tắc pattern.
- `on("*")`: khớp mọi mã exit code còn lại.

Ví dụ:

```java
return new JobBuilder("batchJob", jobRepository)
        .start(processStep)
            .on("COMPLETED_WITH_*").to(reviewStep)
        .from(processStep)
            .on("COMPLETED").to(publishStep)
        .from(processStep)
            .on("*").fail()
        .end()
        .build();
```

Nên khai báo các mã cụ thể và nhánh wildcard dự phòng rõ ràng. Tránh dùng `*` quá sớm nếu còn các mã tùy chỉnh cần được xử lý riêng. Khi thêm exit code mới, hãy cập nhật flow và test tương ứng.

## 9. Phân biệt ExitStatus với FlowExecutionStatus

Khi dùng `JobExecutionDecider`, có thêm một kiểu trạng thái là `FlowExecutionStatus`. Đây không phải `BatchStatus` hoặc `ExitStatus`.

- `BatchStatus` mô tả vòng đời job/step.
- `ExitStatus` mô tả mã kết thúc của job/step và được transition `.on(...)` sử dụng.
- `FlowExecutionStatus` biểu diễn kết quả của một nhánh flow hoặc quyết định do decider trả về.

Ví dụ decider:

```java
public class OrderVolumeDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (stepExecution != null && stepExecution.getWriteCount() > 10000) {
            return new FlowExecutionStatus("HIGH_VOLUME");
        }

        return new FlowExecutionStatus("NORMAL_VOLUME");
    }
}
```

Decider trả về `FlowExecutionStatus`, sau đó flow có thể dùng `.on("HIGH_VOLUME")` hoặc `.on("NORMAL_VOLUME")` để chọn nhánh. Dùng decider khi quyết định phụ thuộc nhiều dữ liệu hoặc logic phức tạp hơn exit code của một step.

Nếu chỉ cần phân biệt step hoàn thành bình thường hay có skip, `ExitStatus` tùy chỉnh thường đủ. Không cần thêm decider nếu một listener và transition đơn giản đã mô tả được quy tắc.

## 10. BatchStatus và ExitStatus ở cấp job

Job cũng có `BatchStatus` và `ExitStatus`, tương tự step. `JobExecution.getStatus()` cho biết trạng thái cuối của execution theo framework; `JobExecution.getExitStatus()` cho biết exit code và description của job.

Với flow nhiều step, trạng thái job được tổng hợp theo kết quả flow và các transition đã cấu hình. Vì vậy, status cuối của job không nhất thiết chỉ là phép sao chép trực tiếp từ một step cuối cùng nếu flow có nhánh, kết thúc có điều kiện hoặc mã tùy chỉnh.

Ví dụ, một step nhập dữ liệu có `ExitStatus.COMPLETED_WITH_SKIPS`, sau đó flow chuyển sang step rà soát. Nếu step rà soát hoàn tất và flow kết thúc bình thường, job có thể kết thúc với `BatchStatus.COMPLETED`; exit status cuối của job phụ thuộc kết quả flow và cấu hình kết thúc. Nếu nghiệp vụ cần giữ dấu vết “đã có item bị skip”, hãy lưu thông tin đó trong dữ liệu hoặc metadata phù hợp và xác định rõ exit code cuối cùng mà hệ thống muốn công bố.

Đừng suy ra trạng thái nghiệp vụ của từng item chỉ từ `JobExecution.getStatus()`. Job có thể hoàn thành dù đã skip item theo chính sách. Nếu cần biết từng đơn hàng được chấp nhận hay từ chối, hãy lưu trạng thái nghiệp vụ riêng.

## 11. Kết thúc flow: end, fail và stop

Khi khai báo transition, cần phân biệt các cách kết thúc flow:

- `.to(nextStep)`: chuyển sang step hoặc flow tiếp theo.
- `.end()`: kết thúc flow theo trạng thái hoàn thành được định nghĩa cho transition đó.
- `.fail()`: kết thúc flow với trạng thái thất bại.
- `.stop()`: kết thúc flow với trạng thái dừng; có thể kết hợp thông tin restart như restart target theo API được dùng.

Ví dụ flow kết thúc thất bại khi step trả `FAILED`:

```java
return new JobBuilder("validateAndImportJob", jobRepository)
        .start(validateStep)
            .on("FAILED").fail()
        .from(validateStep)
            .on("COMPLETED").to(importStep)
        .from(validateStep)
            .on("*").fail()
        .end()
        .build();
```

Ở đây, `.fail()` kết thúc flow với kết quả thất bại. `.stop()` phù hợp khi muốn dừng job có chủ đích và có thể restart sau đó. `.end()` kết thúc flow như một nhánh đã hoàn tất; không nên dùng nó thay cho `.fail()` nếu mục tiêu là đánh dấu job thất bại.

Khi dùng `.stopAndRestart(...)` hoặc các API stop liên quan, hãy xác định rõ step/flow target để restart và kiểm thử trạng thái thực tế của `JobExecution`. Không nên tự đặt `BatchStatus` trực tiếp để mô phỏng một transition.

## 12. Khi nào nên dùng mã ExitStatus tùy chỉnh?

Mã tùy chỉnh hữu ích khi hai kết quả đều hoàn tất về mặt kỹ thuật nhưng cần xử lý tiếp theo khác nhau.

Ví dụ:

- `COMPLETED_WITH_SKIPS`: step hoàn tất nhưng có item bị skip.
- `COMPLETED_WITH_WARNINGS`: step hoàn tất và phát hiện cảnh báo không làm job thất bại.
- `NO_DATA`: không có dữ liệu trong phạm vi xử lý.
- `VALIDATION_REJECTED`: đầu vào không đáp ứng điều kiện nghiệp vụ và cần nhánh xử lý riêng.
- `RECONCILIATION_MISMATCH`: đối soát không khớp và cần điều tra.

Trước khi thêm mã, hãy xác định:

1. Mã đại diện cho kết quả nào và ai chịu trách nhiệm xử lý?
2. `BatchStatus` cuối của step nên là gì?
3. Flow cần chuyển đến step nào hoặc kết thúc theo trạng thái nào?
4. Mã có cần được giữ ở cấp job hay chỉ ở cấp step?
5. Dashboard, alert, test và runbook có hiểu mã đó không?

Không tạo mã tùy chỉnh chỉ để thay tên `COMPLETED` hoặc `FAILED` nếu không có khác biệt về xử lý. Quá nhiều mã không có hợp đồng rõ ràng làm flow khó đọc và khó vận hành.

## 13. ExitDescription và thông tin chẩn đoán

`ExitStatus` có thể mang `exitDescription` để cung cấp ngữ cảnh bổ sung. Ví dụ:

```java
ExitStatus status = new ExitStatus(
        "RECONCILIATION_MISMATCH",
        "Expected total 125000.00 but actual total was 124500.00");
```

Description phù hợp với thông tin chẩn đoán ngắn, có thể giúp người vận hành hiểu lý do của kết quả. Không nên dùng description làm nơi lưu toàn bộ báo cáo, danh sách item lỗi hoặc payload lớn. Những dữ liệu đó nên được lưu trong bảng nghiệp vụ, file báo cáo hoặc hệ thống log/observability phù hợp; context và exit description chỉ giữ mã tham chiếu nếu cần.

Không đưa mật khẩu, access token, dữ liệu cá nhân hoặc thông tin nhạy cảm vào exit description. Metadata có thể được đọc qua `JobExplorer` hoặc hiển thị trên dashboard.

## 14. Kiểm thử BatchStatus và ExitStatus

Kiểm thử cần xác nhận cả trạng thái vòng đời và mã kết thúc. Ví dụ với step có item bị skip:

```java
JobExecution execution =
        jobLauncherTestUtils.launchJob(jobParameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution importStep = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, importStep.getStatus());
assertEquals("COMPLETED_WITH_SKIPS",
        importStep.getExitStatus().getExitCode());
assertTrue(importStep.getSkipCount() > 0);
```

Đoạn test giả định step có `SkipAwareStepListener` và dữ liệu đầu vào tạo ra ít nhất một item bị skip. `JobLauncherTestUtils` cần được cấu hình để chạy đúng job trong test context.

Ngoài ra, nên kiểm thử các trường hợp:

1. Step thành công bình thường: `BatchStatus.COMPLETED`, `ExitStatus.COMPLETED`.
2. Step thất bại do exception không được xử lý: `BatchStatus.FAILED`, exit code tương ứng.
3. Step bị dừng: kiểm tra trạng thái `STOPPED` và exit code phù hợp.
4. Step hoàn tất với mã tùy chỉnh: status vẫn phản ánh vòng đời, exit code mang kết quả bổ sung.
5. Transition theo exit code: xác nhận đúng step tiếp theo được chạy.
6. Transition wildcard: xác nhận mã không được liệt kê được xử lý theo nhánh dự phòng.
7. Flow kết thúc bằng `.fail()`, `.stop()` hoặc `.end()`: xác nhận trạng thái job cuối cùng đúng với ý định.
8. Job nhiều step: xác nhận `JobExecution` và từng `StepExecution` có status/exit status như mong đợi.

Không chỉ kiểm tra `JobExecution.getStatus()`. Một flow có thể đi sai nhánh dù job cuối cùng vẫn hoàn thành. Hãy kiểm tra danh sách step execution và các side effect của nhánh được chọn.

## 15. Những lỗi thường gặp

**Nhầm `BatchStatus` với `ExitStatus`.** `BatchStatus` là enum vòng đời; `ExitStatus` là mã kết thúc có thể tùy chỉnh. Khi dùng `.on(...)`, hãy nghĩ đến exit code.

**Cho rằng `COMPLETED_WITH_SKIPS` làm BatchStatus trở thành trạng thái mới.** Mã tùy chỉnh thuộc `ExitStatus`; `BatchStatus` vẫn có thể là `COMPLETED`.

**Dùng `on("FAILED")` để bắt mọi lỗi nghiệp vụ.** Nếu listener đặt mã exit tùy chỉnh hoặc flow trả kết quả khác, pattern chính xác có thể không khớp. Xem exit code thực tế và khai báo wildcard dự phòng có chủ đích.

**Quên đăng ký listener.** Class tạo `ExitStatus` tùy chỉnh nhưng không gắn vào step thì callback không được gọi. Đăng ký listener với builder và kiểm thử mã kết thúc.

**Trả mã tùy chỉnh che mất lỗi thật.** Không biến một step thất bại thành mã có vẻ thành công chỉ để flow đi tiếp. Nếu cần xử lý lỗi, định nghĩa nhánh recovery rõ ràng và giữ lại thông tin lỗi.

**Không khai báo transition cho mọi kết quả có thể xảy ra.** Flow có thể không tìm được nhánh phù hợp. Dùng transition cụ thể và nhánh dự phòng phù hợp.

**Dùng ExitDescription làm kho dữ liệu.** Description chỉ nên chứa thông tin ngắn; dữ liệu chi tiết cần được lưu ở nơi phù hợp.

**Chỉ kiểm tra status cuối của job.** Hãy kiểm tra cả step execution và nhánh flow đã thực sự chạy.

## Kết luận

`BatchStatus` cho biết vòng đời thực thi của job hoặc step; `ExitStatus` cho biết mã kết thúc và mô tả kết quả. Trong trường hợp thông thường, chúng có các giá trị tương ứng như `COMPLETED`, `FAILED` hoặc `STOPPED`, nhưng ứng dụng có thể đặt `ExitStatus` tùy chỉnh để phân biệt những kết quả cần xử lý khác nhau.

Trong flow, `.on(...)` so khớp exit code của step. Có thể tạo mã tùy chỉnh qua `StepExecutionListener`, dùng transition để điều hướng sang step phù hợp và dùng `JobExecutionDecider` khi cần logic quyết định phức tạp hơn. Khi vận hành và kiểm thử, hãy đọc cả `BatchStatus`, `ExitStatus`, từng `StepExecution` và kết quả nghiệp vụ thực tế để biết job đã chạy như thế nào và flow đã chọn đúng nhánh hay chưa.
