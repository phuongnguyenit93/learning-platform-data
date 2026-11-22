# Sequential flow giữa các step

Trong Spring Batch, một Job thường được chia thành nhiều `Step`, mỗi Step đảm nhiệm một phần công việc. **Sequential flow** là cách tổ chức Job để các Step được thực thi lần lượt theo một thứ tự đã khai báo. Ví dụ, Job import dữ liệu có thể xác thực file trước, import các bản ghi sau đó và cuối cùng tạo báo cáo.

Luồng tuần tự giúp chia một quy trình lớn thành các đơn vị dễ hiểu, theo dõi và khôi phục. Mỗi Step có trạng thái thực thi riêng trong `JobRepository`. Nếu một Step thất bại, Job có thể dừng tại đó; sau khi xử lý nguyên nhân, Job có thể được restart theo quy tắc restart của Spring Batch.

## 1. Sequential flow là gì?

Sequential flow mô tả thứ tự các Step trong Job. Step sau chỉ được thực thi khi luồng điều khiển đi tới Step đó. Một Job đơn giản có thể gồm ba Step:

```text
customerImportJob
        |
        v
  validateFileStep
        |
        v
  importCustomersStep
        |
        v
  generateReportStep
        |
        v
       End
```

Trong ví dụ này:

1. `validateFileStep` kiểm tra file đầu vào và các điều kiện cần thiết.
2. `importCustomersStep` đọc, xử lý và ghi dữ liệu khách hàng.
3. `generateReportStep` tổng hợp kết quả import và tạo báo cáo.

Việc tách thành nhiều Step giúp mỗi phần có cấu hình, transaction, listener, bộ đếm và chính sách lỗi riêng. Nó cũng cho phép Spring Batch lưu trạng thái hoàn thành của từng Step để hỗ trợ restart.

## 2. Khai báo chuỗi Step bằng `start()` và `next()`

Với một Job có luồng tuyến tính, Spring Batch cung cấp API builder ngắn gọn. `start(step)` xác định Step đầu tiên; mỗi lời gọi `next(step)` thêm Step tiếp theo vào chuỗi.

Ví dụ với Spring Batch 5:

```java
@Bean
Job customerImportJob(
        JobRepository jobRepository,
        Step validateFileStep,
        Step importCustomersStep,
        Step generateReportStep) {

    return new JobBuilder("customerImportJob", jobRepository)
            .start(validateFileStep)
            .next(importCustomersStep)
            .next(generateReportStep)
            .build();
}
```

Thứ tự gọi `next()` chính là thứ tự thực thi được khai báo. Spring Batch chạy `validateFileStep` trước, rồi đến `importCustomersStep`, sau cùng là `generateReportStep` nếu luồng tiếp tục bình thường.

`JobBuilder` nhận `JobRepository` để lưu metadata Job và Step. Các Step được truyền vào builder thường được định nghĩa thành bean riêng, giúp tái sử dụng dependency và cấu hình rõ ràng.

## 3. Định nghĩa từng Step trong Job

Mỗi Step có thể dùng Tasklet hoặc chunk-oriented processing. Sequential flow không yêu cầu tất cả Step phải cùng một loại.

### Step xác thực file bằng Tasklet

```java
@Bean
Step validateFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ValidateFileTasklet tasklet) {

    return new StepBuilder("validateFileStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

Tasklet có thể kiểm tra file tồn tại, cấu trúc header, ngày nghiệp vụ hoặc checksum. Nếu đầu vào không hợp lệ, Tasklet có thể ném exception để Step thất bại và ngăn các Step phía sau chạy.

### Step import bằng chunk processing

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Step này đọc và xử lý tối đa 500 item trong một chunk rồi ghi và commit transaction. Nếu file có nhiều dữ liệu, Step có thể tạo nhiều chunk trước khi hoàn tất.

### Step tạo báo cáo bằng Tasklet

```java
@Bean
Step generateReportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        GenerateReportTasklet tasklet) {

    return new StepBuilder("generateReportStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

Step cuối có thể tổng hợp số liệu, tạo file kết quả hoặc lưu trạng thái hoàn tất cho lô import.

## 4. Step được chạy theo thứ tự nào?

Với chuỗi `.start(A).next(B).next(C)`, Job bắt đầu ở A. Nếu A hoàn tất thành công, luồng chuyển tới B; nếu B hoàn tất thành công, luồng chuyển tới C. Khi C hoàn tất, Job kết thúc.

```text
START
  |
  v
 Step A
  |
  | hoàn tất
  v
 Step B
  |
  | hoàn tất
  v
 Step C
  |
  | hoàn tất
  v
 END
```

Trong một Job tuần tự cơ bản, nếu một Step thất bại (`BatchStatus.FAILED`), Job thường dừng tại Step đó và các Step tiếp theo chưa được thực thi. Ví dụ, nếu `importCustomersStep` thất bại, `generateReportStep` sẽ không chạy trong lần JobExecution đó.

Không nên hiểu `.next(stepB)` là “luôn chạy B bất kể kết quả của A”. `.next()` khai báo thứ tự tuyến tính của flow; việc Step có kết thúc thành công để Job tiếp tục hay không vẫn phụ thuộc kết quả thực thi. Nếu cần xử lý nhánh theo kết quả, hãy khai báo flow có điều kiện.

## 5. Thứ tự Step không phải thứ tự khởi tạo bean

Các Step thường được khai báo thành Spring bean, nhưng thứ tự khai báo method `@Bean`, thứ tự Spring khởi tạo bean hoặc annotation `@Order` không quyết định luồng Job.

Thứ tự thực thi do Job builder hoặc flow definition xác định:

```java
return new JobBuilder("myJob", jobRepository)
        .start(stepA)
        .next(stepB)
        .next(stepC)
        .build();
```

Ngay cả khi `stepC` được khởi tạo trước `stepA`, Job vẫn chạy A, B, C theo chuỗi đã khai báo. Nếu muốn đổi thứ tự, cần thay đổi flow definition.

## 6. Sequential flow không phải một transaction duy nhất

Một Job gồm nhiều Step không có nghĩa toàn bộ Job nằm trong một transaction database lớn. Mỗi Step quản lý transaction theo loại xử lý và cấu hình riêng:

- Với TaskletStep, mỗi lần gọi Tasklet được quản lý trong transaction của lần gọi đó.
- Với chunk-oriented Step, transaction thường được commit theo từng chunk.
- Khi Step hoàn tất, metadata thực thi được cập nhật trong `JobRepository`.

Ví dụ:

```text
validateFileStep
   transaction -> commit
        |
        v
importCustomersStep
   chunk 1 -> commit
   chunk 2 -> commit
   chunk 3 -> rollback (lỗi)
        |
        v
JobExecution FAILED
```

Trong ví dụ, transaction của Step xác thực đã commit và hai chunk đầu của Step import cũng đã commit. Khi chunk thứ ba rollback, những thay đổi đã commit trước đó không tự động bị hoàn tác chỉ vì Job thất bại.

Nếu nghiệp vụ cần hoàn tác tác động của các Step trước khi một Step sau thất bại, cần thiết kế cơ chế bù trừ (compensation), trạng thái trung gian hoặc quy trình saga. Không nên kỳ vọng Spring Batch tự rollback tất cả dữ liệu của Job như một transaction duy nhất.

## 7. Truyền dữ liệu giữa các Step

Các Step tuần tự thường cần sử dụng kết quả của Step trước. Có một số cách truyền dữ liệu, tùy kích thước và vòng đời dữ liệu.

### Dùng JobExecutionContext cho dữ liệu nhỏ

Một Step có thể ghi kết quả trung gian vào `JobExecutionContext` để Step tiếp theo đọc. Ví dụ Step xác thực lưu version của file:

```java
@Component
public class ValidateFileTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        JobExecution jobExecution = contribution
                .getStepExecution()
                .getJobExecution();

        jobExecution.getExecutionContext()
                .putString("validatedFileVersion", "v3");

        return RepeatStatus.FINISHED;
    }
}
```

Step sau có thể đọc giá trị bằng `@StepScope` và SpEL:

```java
@Bean
@StepScope
Tasklet importTasklet(
        @Value("#{jobExecutionContext['validatedFileVersion']}") String version,
        CustomerImportService importService) {

    return (contribution, chunkContext) -> {
        importService.importVersion(version);
        return RepeatStatus.FINISHED;
    };
}
```

Nếu dữ liệu được tạo trong StepExecutionContext, có thể dùng `ExecutionContextPromotionListener` để promote những key cần chia sẻ lên JobExecutionContext khi Step hoàn tất. JobExecutionContext phù hợp với metadata nhỏ, mã tham chiếu hoặc kết quả trung gian; không nên lưu cả tập dữ liệu lớn trong context.

### Dùng database hoặc file cho dữ liệu lớn

Nếu Step đầu tạo ra hàng triệu bản ghi cần Step sau xử lý, hãy lưu chúng trong bảng staging, file hoặc object storage. JobExecutionContext chỉ cần giữ một định danh như `stagingBatchId` hoặc đường dẫn file. Step sau dùng định danh đó để đọc dữ liệu.

Ví dụ:

```text
validateFileStep
      |
      +--> lưu batchId vào JobExecutionContext
      |
      v
importCustomersStep
      |
      +--> đọc dữ liệu staging theo batchId
      |
      v
generateReportStep
      |
      +--> tổng hợp theo batchId
```

### JobParameters là đầu vào chung

Nếu các Step cùng cần ngày nghiệp vụ, mã file hoặc phạm vi dữ liệu do caller cung cấp khi launch Job, hãy dùng `JobParameters`. Những giá trị này mô tả công việc cần chạy; ExecutionContext dành cho trạng thái hoặc dữ liệu phát sinh trong lúc thực thi.

## 8. Restart khi một Step trong chuỗi thất bại

Spring Batch lưu `JobInstance`, `JobExecution` và `StepExecution` trong `JobRepository`. Khi một JobInstance thất bại và được restart bằng cùng identifying JobParameters, framework sử dụng trạng thái đã lưu để quyết định Step nào cần thực thi.

Thông thường, những Step đã `COMPLETED` được bỏ qua khi restart. Step thất bại có thể được chạy lại nếu Job cho phép restart và giới hạn thực thi của Step chưa bị vượt. Ví dụ:

```text
Lần chạy đầu:

validateFileStep       COMPLETED
        |
        v
importCustomersStep   FAILED
        |
        v
generateReportStep    chưa chạy

Restart cùng JobInstance:

validateFileStep       được bỏ qua
        |
        v
importCustomersStep   chạy lại/tiếp tục theo checkpoint
        |
        v
generateReportStep    chạy khi Step import hoàn tất
```

Với chunk-oriented Step, reader hỗ trợ lưu trạng thái có thể khôi phục checkpoint từ `StepExecutionContext`. Các chunk đã commit được giữ lại; phần chưa commit có thể phải xử lý lại theo trạng thái reader và transaction.

Nếu muốn một Step đã hoàn thành được chạy lại mỗi lần Job restart, có thể cấu hình `allowStartIfComplete(true)` cho Step đó. Chỉ bật khi tác vụ có thể thực hiện lại an toàn. Ví dụ, một Step gửi email hoặc tạo giao dịch không có idempotency có thể gây tác dụng phụ trùng khi chạy lại.

`startLimit(n)` có thể giới hạn số lần Step được bắt đầu trong cùng JobInstance. Cấu hình này cần được cân nhắc nếu Step có chi phí cao hoặc việc thử lại không giới hạn là không phù hợp.

## 9. Step thất bại và điều kiện chuyển tiếp

Chuỗi `.start().next()` phù hợp với quy trình tuyến tính. Khi cần chọn Step tiếp theo theo kết quả, có thể định nghĩa flow dựa trên `ExitStatus`.

Ví dụ, nếu xác thực thành công thì import; nếu thất bại thì chuyển sang Step ghi nhận file bị từ chối:

```java
@Bean
Job customerImportFlow(
        JobRepository jobRepository,
        Step validateFileStep,
        Step importCustomersStep,
        Step rejectFileStep) {

    return new JobBuilder("customerImportFlow", jobRepository)
            .start(validateFileStep)
                .on("COMPLETED").to(importCustomersStep)
            .from(validateFileStep)
                .on("FAILED").to(rejectFileStep)
            .end()
            .build();
}
```

Đây là `FlowJob` với các transition được khai báo tường minh. `on("COMPLETED")` và `on("FAILED")` so khớp với exit code của Step. Khi xây dựng flow thực tế, cần xác định đầy đủ các trạng thái có thể xảy ra và hành vi khi không có transition nào khớp.

`BatchStatus` và `ExitStatus` liên quan nhưng không giống nhau:

- `BatchStatus` mô tả trạng thái thực thi như `STARTED`, `COMPLETED`, `FAILED` hoặc `STOPPED`.
- `ExitStatus` mô tả mã kết quả được dùng trong flow transition, có thể chứa giá trị chuẩn hoặc mã tùy chỉnh.

Nếu một Step hoàn tất về mặt kỹ thuật nhưng cần rẽ nhánh theo kết quả nghiệp vụ, có thể đặt ExitStatus tùy chỉnh qua listener hoặc logic phù hợp rồi khai báo transition tương ứng. Không nên dùng mã tùy chỉnh để che giấu trạng thái lỗi thực sự.

## 10. Thứ tự Step và các dependency nghiệp vụ

Khi thiết kế chuỗi Step, mỗi Step nên có đầu vào và đầu ra rõ ràng. Step sau chỉ nên phụ thuộc vào dữ liệu mà Step trước đã tạo và lưu bền vững.

Ví dụ một quy trình đối soát:

| Step | Công việc | Đầu ra cho Step tiếp theo |
|---|---|---|
| `loadTransactionsStep` | Nạp giao dịch nguồn vào staging | `batchId` và trạng thái nạp |
| `validateTransactionsStep` | Kiểm tra định dạng, khóa trùng và dữ liệu bắt buộc | Số lượng hợp lệ/lỗi, trạng thái xác thực |
| `reconcileTransactionsStep` | Đối chiếu với hệ thống đích | Bảng kết quả đối soát |
| `generateReconciliationReportStep` | Tạo báo cáo và lưu kết quả | Đường dẫn báo cáo, trạng thái hoàn tất |

Nếu Step giữa thất bại, Step sau không nên chạy với dữ liệu chưa sẵn sàng. Việc sắp xếp thứ tự Step cần phản ánh dependency thực tế, không chỉ sắp theo tên hoặc theo thứ tự file cấu hình.

Nên giữ các Step tương đối độc lập để dễ restart và thay đổi. Nếu một Step vừa nạp dữ liệu, vừa xác thực, vừa đối soát và vừa tạo báo cáo, việc tách thành các Step có ranh giới rõ có thể giúp xác định lỗi và vận hành dễ hơn.

## 11. Điều gì xảy ra nếu một Step không có dữ liệu?

Một Step có thể hoàn tất thành công dù không có item để xử lý. Ví dụ, reader trả `null` ngay lần đầu vì file rỗng. Step có thể kết thúc với `BatchStatus.COMPLETED` và `readCount` bằng 0.

Nếu nghiệp vụ yêu cầu dữ liệu phải tồn tại, Step xác thực trước đó nên kiểm tra điều kiện này và làm Job thất bại hoặc đặt ExitStatus phù hợp. Không nên giả định Step import không có item sẽ tự động làm Step báo cáo bị bỏ qua.

Trong chuỗi tuần tự cơ bản, nếu Step hoàn tất bình thường, Step tiếp theo vẫn có thể chạy ngay cả khi Step trước xử lý 0 item. Nếu muốn thay đổi hành vi theo số lượng item, hãy dùng điều kiện flow rõ ràng, listener hoặc dữ liệu trạng thái được lưu để quyết định.

## 12. Tên Step và metadata ổn định

`Step` có tên được lưu trong metadata của `JobRepository`. Tên Step được dùng để nhận diện StepExecution và hỗ trợ restart. Vì vậy:

- Đặt tên Step rõ ràng, ổn định và có ý nghĩa nghiệp vụ.
- Tránh dùng tên động thay đổi theo timestamp hoặc dữ liệu từng lần chạy.
- Không tùy tiện đổi tên Step trong Job đang có lịch sử execution cần restart.
- Không dùng cùng một tên Step cho hai phần công việc khác nhau trong cùng một Job flow.

Khi thay đổi cấu trúc Job hoặc tên Step trong lúc một JobInstance cũ còn cần restart, cần xem xét tương thích metadata và quy trình xử lý các execution đang tồn tại.

## 13. Theo dõi một Job có nhiều Step

`JobExplorer`, `JobRepository` và các listener có thể giúp theo dõi trạng thái của Job và từng Step. Các thông tin nên quan sát gồm:

- JobInstance ID, JobExecution ID và identifying JobParameters.
- Thứ tự Step và trạng thái từng StepExecution.
- Thời điểm bắt đầu, kết thúc và thời gian chạy của từng Step.
- Read count, write count, filter count, skip count và rollback count của chunk Step.
- Exception cuối cùng nếu Step thất bại.
- Checkpoint và trạng thái restart nếu Step hỗ trợ.

Log nên gắn JobExecution ID, StepExecution ID và mã lô nghiệp vụ để có thể liên kết sự kiện giữa các Step. Nếu Step sau chậm, metrics theo Step giúp xác định bottleneck nằm ở đọc dữ liệu, xử lý, ghi database hay service phụ thuộc.

## 14. Các lỗi thường gặp khi xây dựng sequential flow

**Cho rằng `.next()` luôn chạy Step tiếp theo dù Step trước thất bại:** trong luồng tuần tự cơ bản, Step thất bại thường làm Job dừng. Nếu cần xử lý nhánh lỗi, hãy định nghĩa transition theo ExitStatus.

**Nhầm thứ tự khởi tạo bean với thứ tự chạy:** thứ tự thực thi do `start()` và `next()` hoặc flow definition quyết định.

**Cho rằng toàn bộ Job nằm trong một transaction:** mỗi Step và mỗi chunk có ranh giới transaction riêng. Các thay đổi đã commit trước đó vẫn tồn tại nếu Step sau thất bại.

**Truyền dữ liệu lớn qua ExecutionContext:** context phù hợp với metadata nhỏ và checkpoint. Dùng database hoặc file cho tập dữ liệu lớn, rồi truyền khóa tham chiếu.

**Đổi identifying JobParameters khi restart:** tham số identifying mới tạo JobInstance mới, không restart instance cũ.

**Cho rằng Step đã hoàn thành luôn chạy lại khi restart:** mặc định Step `COMPLETED` thường được bỏ qua. Dùng `allowStartIfComplete(true)` chỉ khi cần và tác vụ an toàn khi lặp.

**Để Step sau chạy khi dữ liệu chưa sẵn sàng:** xác thực điều kiện đầu vào và dependency trước khi chuyển sang Step tiếp theo.

**Đổi tên Step tùy tiện:** metadata cũ có thể không còn khớp với flow mới, gây khó khăn cho restart và điều tra lịch sử.

## Kết luận

Sequential flow tổ chức Job thành chuỗi Step thực thi theo thứ tự được khai báo bằng `.start(stepA).next(stepB).next(stepC)`. Mỗi Step có trạng thái và ranh giới transaction riêng; nếu Step thất bại, Job tuần tự cơ bản dừng và các Step sau chưa chạy. Khi restart cùng JobInstance, những Step đã hoàn thành thường được bỏ qua, còn Step cần tiếp tục dựa vào metadata và checkpoint. Dữ liệu nhỏ giữa các Step có thể truyền qua JobExecutionContext; dữ liệu lớn nên lưu ở database hoặc file và truyền khóa tham chiếu. Khi cần rẽ nhánh theo kết quả, hãy dùng Flow transition dựa trên ExitStatus thay vì coi chuỗi `.next()` là một điều kiện luôn chạy tiếp.
