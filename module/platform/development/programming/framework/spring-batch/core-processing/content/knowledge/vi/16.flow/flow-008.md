# Skip step và stop job

Trong Spring Batch, flow của một Job có thể rẽ nhánh để bỏ qua một Step không cần chạy, kết thúc Job thành công, kết thúc Job thất bại hoặc dừng Job để có thể tiếp tục sau đó. Các quyết định này được mô tả bằng transition trong Job flow, thường dựa trên `ExitStatus` của Step hoặc kết quả từ `JobExecutionDecider`.

Hai ý niệm cần phân biệt rõ:

- **Skip một Step trong flow:** Job đi theo một nhánh khác và không thực thi Step đó. Đây là cách tổ chức luồng công việc có điều kiện.
- **Stop Job:** Job kết thúc ở trạng thái `STOPPED` theo một transition hoặc nhận yêu cầu dừng trong lúc đang chạy. Việc dừng được lưu trong metadata và có thể được tiếp tục theo chính sách restart.

Đây không phải cùng cơ chế với skip một item trong chunk processing. Item skip xử lý một bản ghi lỗi ở reader, processor hoặc writer; skip Step là bỏ qua một nút trong đồ thị flow. Spring Batch không có `BatchStatus.SKIPPED` cho một Step bị bypass trong flow.

## 1. Job flow và các transition

Một Job có thể gồm nhiều Step nối tiếp nhau hoặc rẽ nhánh theo kết quả của Step trước. Với Java configuration, flow thường được khai báo bằng `JobBuilder`:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateStep,
        Step importStep,
        Step archiveStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(validateStep)
                .on("COMPLETED").to(importStep)
            .from(importStep)
                .on("COMPLETED").to(archiveStep)
            .from(archiveStep)
                .on("*").end()
            .end()
            .build();
}
```

Các thành phần quan trọng:

- `start(step)` chỉ định Step đầu tiên của flow.
- `on(pattern)` chọn transition dựa trên mã kết quả.
- `to(step)` chuyển sang Step hoặc state tiếp theo.
- `from(step)` khai báo thêm transition bắt đầu từ Step đã chỉ định.
- `end()` kết thúc phần khai báo flow; khi dùng như transition target, nó cũng có ý nghĩa kết thúc Job với trạng thái hoàn tất.

Trong transition từ một Step, pattern được so khớp với `ExitStatus` của Step. Vì vậy, cần phân biệt exit code với `BatchStatus`: một Step có thể có `BatchStatus.COMPLETED` nhưng mang exit code tùy chỉnh như `NO_DATA` để Job rẽ nhánh.

## 2. Skip một Step bằng cách đi vòng qua nó

Để bỏ qua một Step, hãy thiết kế flow sao cho một nhánh chuyển thẳng đến Step sau đó, không đi qua Step muốn bỏ qua.

Ví dụ Job có ba bước: kiểm tra dữ liệu, làm giàu dữ liệu và nạp dữ liệu. Nếu dữ liệu đầu vào đã được làm giàu từ trước, Job có thể đi thẳng từ bước kiểm tra sang bước nạp:

```text
                 +--> NEEDS_ENRICHMENT --> Enrich Step --+
                 |                                      |
Validate Step ---+                                      +--> Load Step
                 |                                      |
                 +--> ALREADY_ENRICHED -----------------+
```

Có thể dùng exit code tùy chỉnh để tạo nhánh:

```java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        InputValidationService validationService) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                ValidationResult result = validationService.validate();

                if (result.alreadyEnriched()) {
                    contribution.setExitStatus(
                            new ExitStatus("ALREADY_ENRICHED"));
                } else {
                    contribution.setExitStatus(
                            new ExitStatus("NEEDS_ENRICHMENT"));
                }

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Flow sử dụng kết quả đó:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step enrichStep,
        Step loadStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(validateInputStep)
                .on("NEEDS_ENRICHMENT").to(enrichStep)
            .from(validateInputStep)
                .on("ALREADY_ENRICHED").to(loadStep)
            .from(enrichStep)
                .on("COMPLETED").to(loadStep)
            .from(loadStep)
                .on("*").end()
            .end()
            .build();
}
```

Khi `validateInputStep` trả `ALREADY_ENRICHED`, `enrichStep` không được gọi. Không có `StepExecution` cho `enrichStep` trong lần chạy đó vì Step đã bị bypass hoàn toàn. Đây là kết quả bình thường của conditional flow, không phải một Step thất bại hay một item bị skip.

## 3. Dùng JobExecutionDecider để quyết định Step có chạy hay không

Khi điều kiện rẽ nhánh không nên đặt trong một Step hoặc cần dựa trên kết quả tổng hợp của Job, có thể dùng `JobExecutionDecider`. Decider trả về một `FlowExecutionStatus` để flow chọn transition.

Ví dụ, Job quyết định có cần làm giàu dữ liệu hay không dựa trên JobParameters:

```java
@Bean
JobExecutionDecider enrichmentDecider() {
    return (jobExecution, stepExecution) -> {
        String mode = jobExecution.getJobParameters().getString("mode");

        if ("ALREADY_ENRICHED".equals(mode)) {
            return new FlowExecutionStatus("SKIP_ENRICHMENT");
        }

        return new FlowExecutionStatus("RUN_ENRICHMENT");
    };
}
```

Khai báo flow:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step prepareStep,
        JobExecutionDecider enrichmentDecider,
        Step enrichStep,
        Step loadStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(prepareStep)
            .next(enrichmentDecider)
                .on("RUN_ENRICHMENT").to(enrichStep)
            .from(enrichmentDecider)
                .on("SKIP_ENRICHMENT").to(loadStep)
            .from(enrichStep)
                .on("COMPLETED").to(loadStep)
            .from(loadStep)
                .on("*").end()
            .end()
            .build();
}
```

`JobExecutionDecider` không phải Step và không tạo `StepExecution`. Nó trả kết quả điều khiển flow. Transition từ Step thường khớp với `ExitStatus`; transition từ Decider khớp với `FlowExecutionStatus` mà Decider trả về.

## 4. Tạo ExitStatus tùy chỉnh để bypass Step

Một cách phổ biến là dùng `StepExecutionListener.afterStep` để đặt exit code tùy chỉnh. Ví dụ, nếu Step đọc dữ liệu nhưng không có bản ghi nào, Job có thể bỏ qua Step xử lý tiếp theo và chuyển thẳng đến bước tổng kết.

```java
@Bean
StepExecutionListener noDataListener() {
    return new StepExecutionListener() {
        @Override
        public void beforeStep(StepExecution stepExecution) {
            // Không cần xử lý trước Step.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            if (stepExecution.getStatus() == BatchStatus.COMPLETED
                    && stepExecution.getReadCount() == 0) {
                return new ExitStatus("NO_DATA");
            }
            return null;
        }
    };
}
```

Sau đó cấu hình flow:

```java
.start(readInputStep)
    .on("NO_DATA").to(createEmptyReportStep)
.from(readInputStep)
    .on("COMPLETED").to(processDataStep)
.from(processDataStep)
    .on("COMPLETED").to(createReportStep)
```

Listener chỉ thay đổi `ExitStatus` khi Step đã hoàn tất và không có dữ liệu. `BatchStatus` vẫn là `COMPLETED`. Cách này phù hợp khi Step kỹ thuật đã thực hiện thành công, nhưng kết quả nghiệp vụ cần điều khiển flow theo một nhánh riêng.

Không nên đặt `BatchStatus.FAILED` chỉ để bỏ qua một Step. Nếu công việc thực tế thành công nhưng không có dữ liệu, exit code tùy chỉnh thể hiện ý nghĩa chính xác hơn.

## 5. Các cách kết thúc flow: end, fail và stop

Spring Batch cung cấp các transition target khác nhau để xác định kết quả của Job khi flow đến một nhánh kết thúc.

| Transition | BatchStatus của Job | Ý nghĩa |
|---|---|---|
| `.end()` | `COMPLETED` | Kết thúc Job thành công theo flow. |
| `.fail()` | `FAILED` | Kết thúc Job với trạng thái thất bại. |
| `.stop()` | `STOPPED` | Dừng Job theo flow; có thể restart theo chính sách. |
| `.stopAndRestart(step)` | `STOPPED` | Dừng Job và chỉ định Step làm điểm tiếp tục khi restart. |

Các transition này khác với `.to(nextStep)`, vốn chuyển flow sang một Step khác.

### end(): kết thúc Job thành công

`.end()` kết thúc Job với `BatchStatus.COMPLETED`. Ví dụ, nếu không có dữ liệu cần xử lý và nghiệp vụ xem đó là kết quả hợp lệ, Job có thể kết thúc thành công:

```java
return new JobBuilder("optionalImportJob", jobRepository)
        .start(checkInputStep)
            .on("NO_DATA").end()
        .from(checkInputStep)
            .on("COMPLETED").to(importStep)
        .end()
        .build();
```

Khi Job đã `COMPLETED`, cùng JobInstance thường không thể được launch lại như một lần chạy mới. Nếu muốn xử lý một đợt nghiệp vụ mới, cần identifying parameters mới theo thiết kế. `.end()` không phải lệnh tạm dừng.

### fail(): kết thúc Job thất bại

`.fail()` kết thúc flow với `BatchStatus.FAILED`. Dùng khi điều kiện nghiệp vụ hoặc kết quả Step khiến Job không thể được xem là thành công:

```java
return new JobBuilder("controlledImportJob", jobRepository)
        .start(validateStep)
            .on("INVALID_DATA").fail()
        .from(validateStep)
            .on("COMPLETED").to(importStep)
        .end()
        .build();
```

Job thất bại có thể được restart nếu Job và trạng thái execution cho phép. Khi restart, Spring Batch dựa trên metadata và flow để xác định phần công việc cần tiếp tục. Nếu Job được cấu hình `preventRestart()`, việc restart sẽ bị ngăn.

### stop(): dừng Job theo flow

`.stop()` kết thúc flow với `BatchStatus.STOPPED`. Dùng khi cần tạm dừng có chủ đích, chẳng hạn sau bước kiểm tra để chờ phê duyệt:

```java
return new JobBuilder("approvalJob", jobRepository)
        .start(prepareApprovalStep)
            .on("COMPLETED").to(approvalCheckStep)
        .from(approvalCheckStep)
            .on("WAITING_FOR_APPROVAL").stop()
        .from(approvalCheckStep)
            .on("APPROVED").to(processPaymentStep)
        .end()
        .build();
```

Khi flow đi đến `stop()`, Job kết thúc ở trạng thái `STOPPED`, không phải `COMPLETED`. Có thể restart JobInstance sau khi điều kiện chờ đã được giải quyết, tùy metadata và cấu hình Step.

### stopAndRestart(step): chỉ định điểm tiếp tục

Nếu muốn dừng Job và chỉ định rõ Step sẽ được thực hiện khi restart, dùng `.stopAndRestart(step)`:

```java
return new JobBuilder("approvalJob", jobRepository)
        .start(prepareApprovalStep)
            .on("COMPLETED").to(approvalCheckStep)
        .from(approvalCheckStep)
            .on("WAITING_FOR_APPROVAL").stopAndRestart(processPaymentStep)
        .from(approvalCheckStep)
            .on("APPROVED").to(processPaymentStep)
        .from(processPaymentStep)
            .on("COMPLETED").to(archiveStep)
        .end()
        .build();
```

Flow dừng ở trạng thái `STOPPED`. Khi JobInstance được restart hợp lệ, flow tiếp tục tại `processPaymentStep` theo điểm restart đã chỉ định. Cách này hữu ích khi Step phê duyệt chỉ dùng để kiểm tra trạng thái chờ, và không cần chạy lại sau khi phê duyệt hoàn tất.

Hãy bảo đảm Step được chỉ định làm điểm restart có thể chạy an toàn với dữ liệu đã chuẩn bị ở các Step trước. Nếu Step trước đã tạo tác dụng phụ, không nên xóa hoặc sửa metadata để ép flow chạy từ một vị trí tùy ý.

## 6. Phân biệt stop trong flow với yêu cầu dừng Job đang chạy

`.stop()` là một transition được định nghĩa trước trong Job flow. Khi Job đến nhánh đó, framework kết thúc Job ở trạng thái `STOPPED`.

Trong vận hành, có thể cần dừng một Job đang chạy vì người vận hành yêu cầu, hệ thống bảo trì hoặc điều kiện bên ngoài thay đổi. Đây là một thao tác khác: ứng dụng gửi yêu cầu stop thông qua `JobOperator`.

```java
@Service
public class BatchControlService {

    private final JobOperator jobOperator;

    public BatchControlService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public void requestStop(long jobExecutionId) throws Exception {
        jobOperator.stop(jobExecutionId);
    }
}
```

`JobOperator.stop(executionId)` yêu cầu Spring Batch dừng execution đang chạy. Đây là yêu cầu dừng có kiểm soát, không phải lệnh kill thread hoặc hủy tiến trình ngay lập tức.

Với chunk Step, framework thường dừng tại điểm an toàn của quá trình xử lý, chẳng hạn sau khi chunk hiện tại hoàn tất transaction. Vì vậy, có thể cần thời gian để Job chuyển từ `STOPPING` sang `STOPPED`. Nếu reader, processor hoặc writer đang bị block trong một lời gọi I/O, cần timeout riêng để tránh chờ vô hạn.

Trước khi gửi yêu cầu stop, cần xác định đúng `JobExecutionId`. Không nên dừng chỉ dựa trên tên Job nếu có nhiều execution của Job đó.

## 7. BatchStatus và ExitStatus khi skip Step hoặc stop Job

`BatchStatus` và `ExitStatus` có vai trò khác nhau:

- `BatchStatus` phản ánh trạng thái vòng đời của JobExecution hoặc StepExecution, ví dụ `COMPLETED`, `FAILED`, `STOPPED`.
- `ExitStatus` chứa exit code và mô tả kết quả; flow dùng exit code để chọn transition.

Một Step có thể hoàn tất thành công về mặt kỹ thuật (`BatchStatus.COMPLETED`) nhưng có exit code `NO_DATA` hoặc `ALREADY_ENRICHED`. Flow dùng exit code này để bypass Step khác.

Một Job có thể kết thúc bằng `BatchStatus.STOPPED` do `.stop()` hoặc yêu cầu dừng từ `JobOperator`. Đây là trạng thái Job, không có nghĩa Step gần nhất đã bị skip.

| Tình huống | Step BatchStatus | Step ExitStatus | Job BatchStatus |
|---|---|---|---|
| Step kiểm tra thành công, cần chạy Step tiếp theo | `COMPLETED` | `COMPLETED` | Chưa kết thúc |
| Step kiểm tra thành công, bypass Step tùy chọn | `COMPLETED` | `ALREADY_ENRICHED` | Tiếp tục flow |
| Flow gọi `.end()` | Step cuối có thể `COMPLETED` | Theo transition cuối | `COMPLETED` |
| Flow gọi `.fail()` | Step trước đó có thể `COMPLETED` | Theo transition | `FAILED` |
| Flow gọi `.stop()` | Step trước đó có thể `COMPLETED` | Theo transition | `STOPPED` |
| Operator yêu cầu dừng Job đang chạy | Step hiện tại kết thúc theo điểm dừng an toàn | Có thể là `STOPPED` tùy đường dừng | `STOPPED` sau khi dừng xong |

Không nên dựa vào `ExitStatus` của Step để kết luận Job đã hoàn tất. Hãy kiểm tra cả trạng thái JobExecution và flow transition.

## 8. Pattern transition và nhánh mặc định

`on(pattern)` dùng pattern để so khớp exit code. Có thể dùng mã cụ thể hoặc wildcard như `*` làm nhánh mặc định.

Ví dụ:

```java
.start(validateStep)
    .on("NO_DATA").end()
.from(validateStep)
    .on("COMPLETED").to(importStep)
.from(validateStep)
    .on("*").fail()
```

Trong ví dụ, `NO_DATA` và `COMPLETED` được xử lý riêng; các kết quả khác đi vào nhánh fail. Nên khai báo đầy đủ các kết quả dự kiến và một nhánh fallback rõ ràng để flow không có kết quả chưa được xử lý.

Tránh dùng wildcard quá sớm khiến nhánh cụ thể không còn ý nghĩa hoặc làm các lỗi bất ngờ đi vào đường thành công. Hãy đọc flow như một đồ thị: từ mỗi Step/Decider, xác định các kết quả có thể có và đích của từng kết quả.

## 9. Bỏ qua Step khác với skip item

Hai khái niệm có tên gần nhau nhưng khác phạm vi:

| Khía cạnh | Skip item | Bypass Step |
|---|---|---|
| Phạm vi | Một item trong chunk | Một Step trong Job flow |
| Cơ chế | Exception + skip policy/skip limit | Conditional transition hoặc Decider |
| Thành phần liên quan | Reader, processor, writer, `SkipListener` | `JobBuilder`, Flow, `JobExecutionDecider`, ExitStatus |
| Metadata | Tăng skip counters trong StepExecution | Step bị bypass không có StepExecution trong lần chạy đó |
| Mục đích | Tiếp tục xử lý các item còn lại khi một item lỗi | Không chạy một giai đoạn không cần thiết |

Ví dụ, một file có 1.000 dòng, trong đó 5 dòng lỗi định dạng, là trường hợp cân nhắc item skip. Nếu file đã được làm sạch từ trước và không cần chạy Step `cleanFileStep`, flow có thể bypass cả Step đó.

Không dùng `.skip(...)` để bỏ qua một Step. Cấu hình skip áp dụng cho exception ở cấp item trong fault-tolerant Step.

## 10. Restart sau khi Job dừng

Job ở trạng thái `STOPPED` có thể được restart nếu JobInstance, Job và các Step cho phép. Khi restart:

- Spring Batch tạo JobExecution mới cho cùng JobInstance.
- Các Step đã hoàn tất thường được bỏ qua.
- Step chưa hoàn tất có thể được tiếp tục theo metadata và checkpoint.
- Với `.stopAndRestart(step)`, flow dùng điểm restart đã chỉ định.
- Nếu Step được cấu hình `allowStartIfComplete(true)`, Step đã hoàn tất có thể được chạy lại trong một lần restart phù hợp.

Ví dụ, Job dừng sau khi chuẩn bị dữ liệu và chờ phê duyệt. Khi phê duyệt hoàn tất, ứng dụng restart cùng JobInstance để tiếp tục Step xử lý. Nếu muốn tạo một đợt nghiệp vụ mới, cần identifying parameters mới thay vì restart execution cũ.

### Không nhầm restart với launch một JobInstance mới

Restart giữ định danh JobInstance và lịch sử execution để Spring Batch có thể tiếp tục. Tạo JobInstance mới bằng identifying parameters khác sẽ bắt đầu một lần nghiệp vụ mới, thường từ đầu flow.

Không tự thêm timestamp hoặc UUID vào identifying parameters chỉ để né trạng thái `COMPLETED` hoặc `STOPPED`. Hãy xác định rõ người dùng muốn tiếp tục công việc cũ hay tạo một đợt xử lý mới.

## 11. Thiết kế Step có thể được bypass an toàn

Một Step có thể được bypass khi điều kiện nghiệp vụ cho phép. Trước khi bỏ qua, hãy xác định:

- Step có thực sự tùy chọn hay không.
- Step tiếp theo có đủ dữ liệu và trạng thái cần thiết không.
- Các side effect mà Step bị bypass thường tạo ra có cần được thay thế hay không.
- JobParameters hoặc JobExecutionContext có đủ thông tin để nhánh sau tiếp tục không.
- Khi restart, flow có thể đi vào nhánh khác do điều kiện đã thay đổi hay không.

Ví dụ, nếu `enrichStep` bị bypass vì dữ liệu đã được làm giàu, `loadStep` phải nhận được cùng cấu trúc dữ liệu mà nó mong đợi sau khi `enrichStep` chạy. Nếu không, bypass sẽ tạo lỗi ở Step sau.

Điều kiện bypass nên được quyết định từ dữ liệu có thể kiểm chứng, chẳng hạn trạng thái batch hoặc một thuộc tính rõ ràng, thay vì chỉ dựa vào một cờ runtime dễ thay đổi.

## 12. Stop Job và tác dụng phụ bên ngoài

Yêu cầu dừng Job không tự hoàn tác mọi tác dụng phụ đã thực hiện. Với chunk processing, chunk hiện tại có thể hoàn tất và commit trước khi Step dừng. Các chunk trước cũng đã commit và được giữ lại.

Nếu Step gửi email, gọi API hoặc di chuyển file, những thao tác này không tự rollback cùng transaction database. Khi Job được restart, chúng có thể được thực hiện lại nếu flow chạy lại Step tương ứng.

Vì vậy:

- Thiết kế tác vụ idempotent khi có thể.
- Dùng business key hoặc idempotency key để ngăn xử lý trùng.
- Kiểm tra trạng thái file hoặc request trước khi thực hiện lại.
- Dùng outbox/inbox khi cần phối hợp thay đổi database và phát sự kiện.
- Trước khi restart sau stop, đối chiếu trạng thái nghiệp vụ thực tế.

## 13. Những lỗi thường gặp

### Nghĩ Step bị bypass sẽ có trạng thái SKIPPED

Một Step không được gọi trong flow thường không có StepExecution cho lần chạy đó. Không có `BatchStatus.SKIPPED` chuẩn cho trường hợp bypass Step.

### Dùng skip policy để bỏ qua cả Step

Skip policy xử lý exception của item trong chunk. Để bypass Step, dùng conditional flow hoặc JobExecutionDecider.

### Nhầm `.end()` với `.stop()`

`.end()` kết thúc Job thành `COMPLETED`; `.stop()` kết thúc Job thành `STOPPED` và có thể được restart. Chọn theo ý nghĩa nghiệp vụ.

### Dùng `.fail()` cho một nhánh không có dữ liệu

Không có dữ liệu có thể là kết quả hợp lệ. Nếu vậy, dùng exit code như `NO_DATA` rồi chuyển đến Step tổng kết hoặc kết thúc thành công.

### Nghĩ JobOperator.stop() hủy thread ngay lập tức

Đây là yêu cầu dừng có kiểm soát. Step thường cần đạt điểm an toàn để kết thúc transaction và cập nhật metadata. Cấu hình timeout I/O để tránh tác vụ bị treo.

### Không khai báo nhánh fallback

Nếu một exit code không có transition tương ứng, flow có thể kết thúc ngoài dự kiến. Hãy xác định đầy đủ các exit code và nhánh mặc định.

### Bypass Step nhưng Step sau vẫn cần output của nó

Điều này khiến Step sau thiếu dữ liệu hoặc trạng thái. Hãy bảo đảm nhánh bypass cung cấp đủ điều kiện đầu vào hoặc đi qua một Step thay thế.

### Tự sửa metadata để restart từ Step tùy ý

Sửa trực tiếp Job/Step execution status hoặc context có thể phá vỡ tính nhất quán. Dùng flow transition, `stopAndRestart` và API vận hành phù hợp.

## 14. Quy trình thiết kế skip Step và stop Job

Khi thiết kế flow có nhánh bỏ qua Step hoặc dừng Job, có thể thực hiện theo trình tự:

1. Vẽ các Step và điều kiện nghiệp vụ quyết định đường đi.
2. Xác định điều kiện được biểu diễn bằng ExitStatus của Step hay `JobExecutionDecider`.
3. Tạo exit code/FlowExecutionStatus rõ nghĩa cho từng nhánh.
4. Dùng `.to(nextStep)` để bypass Step tùy chọn.
5. Dùng `.end()` nếu Job đã hoàn tất thành công; `.fail()` nếu kết quả phải thất bại.
6. Dùng `.stop()` nếu cần dừng theo flow; dùng `.stopAndRestart(step)` nếu cần chỉ định điểm tiếp tục.
7. Dùng `JobOperator.stop(executionId)` khi cần gửi yêu cầu dừng một Job đang chạy.
8. Bổ sung nhánh fallback cho kết quả không mong đợi.
9. Kiểm tra các Step sau nhánh bypass có đủ dữ liệu và trạng thái cần thiết.
10. Kiểm thử Job hoàn tất, Job thất bại, Job dừng, restart và yêu cầu stop khi chunk đang chạy.

| Yêu cầu | Cơ chế nên dùng |
|---|---|
| Không chạy Step làm giàu nếu dữ liệu đã sẵn sàng | Conditional transition hoặc `JobExecutionDecider` để đi thẳng đến Step sau. |
| Bỏ qua một bản ghi lỗi trong chunk | `.skip(...)` và `.skipLimit(...)`. |
| Kết thúc Job thành công khi không có dữ liệu | ExitStatus riêng rồi `.end()` hoặc đi đến Step tổng kết. |
| Đánh dấu Job thất bại theo điều kiện nghiệp vụ | `.fail()`. |
| Dừng Job theo flow để chờ phê duyệt | `.stop()` hoặc `.stopAndRestart(step)`. |
| Người vận hành yêu cầu dừng Job đang chạy | `JobOperator.stop(jobExecutionId)`. |

## Kết luận

Để bỏ qua một Step, hãy thiết kế conditional transition hoặc dùng `JobExecutionDecider` để flow đi thẳng đến Step phù hợp; Step bị bypass không tạo `StepExecution` và không có trạng thái `SKIPPED` riêng. Để điều khiển kết quả cuối của Job, dùng `.end()` cho `COMPLETED`, `.fail()` cho `FAILED`, `.stop()` cho `STOPPED`, hoặc `.stopAndRestart(step)` khi cần chỉ định điểm tiếp tục. Khi cần dừng một Job đang chạy từ bên ngoài, dùng `JobOperator.stop(executionId)` và để framework dừng tại điểm an toàn. Luôn phân biệt bypass Step với skip item, kiểm tra restart behavior và bảo đảm các tác dụng phụ an toàn khi Job được tiếp tục.
