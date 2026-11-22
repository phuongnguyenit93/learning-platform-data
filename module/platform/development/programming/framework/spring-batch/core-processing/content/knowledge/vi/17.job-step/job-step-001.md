# JobStep chạy một Job con trong một Step

Trong Spring Batch, một job thường được cấu thành từ nhiều step. Khi một quy trình lớn cần tái sử dụng một job đã có, hoặc cần chia quy trình thành các phần độc lập có thể vận hành riêng, có thể dùng `JobStep` để chạy một **job con như một step của job cha**.

`JobStep` đóng vai trò cầu nối giữa hai cấp điều phối: job cha xem việc chạy job con như một step; bên trong step đó, `JobLauncher` khởi chạy job con với bộ `JobParameters` được tạo bởi `JobParametersExtractor`. Job con có vòng đời, `JobInstance`, `JobExecution` và các step execution riêng trong metadata repository.

## 1. JobStep là gì?

`JobStep` là một implementation của `Step` dùng để khởi chạy một `Job` khác. Thay vì khai báo trực tiếp một tasklet hoặc chunk reader/processor/writer, step này ủy quyền việc xử lý cho một job con.

Ví dụ một quy trình tổng thể:

```text
ParentJob: dailySettlement
    |
    v
PrepareStep
    |
    v
RunValidationJobStep  ----> ChildJob: validateOrders
    |                              |
    |                              +--> ReadOrdersStep
    |                              +--> ValidateStep
    |                              +--> SaveValidationResultStep
    |
    v
RunSettlementJobStep  ----> ChildJob: settlePayments
    |                              |
    |                              +--> LoadValidOrdersStep
    |                              +--> CalculateSettlementStep
    |                              +--> WriteSettlementStep
    |
    v
PublishReportStep
```

Từ góc nhìn job cha, `RunValidationJobStep` và `RunSettlementJobStep` là các step bình thường trong flow. Nhưng mỗi step thực tế khởi chạy một job con có thể chứa nhiều step, flow, listener và cấu hình riêng.

`JobStep` hữu ích khi muốn đóng gói một quy trình con thành job có tên, có thể chạy độc lập hoặc được gọi từ nhiều job cha. Nó không tự động tạo thêm luồng song song; việc chạy job con vẫn tuân theo cấu hình `JobLauncher` và flow của job con.

## 2. Khi nào nên dùng JobStep?

Một số tình huống phù hợp:

- **Tái sử dụng quy trình:** nhiều job cha cần chạy chung một quy trình con như xác thực file, chuẩn hóa dữ liệu hoặc tạo báo cáo.
- **Chia module nghiệp vụ:** mỗi nhóm có thể sở hữu một job con với reader, processor, writer và listener riêng.
- **Điều phối nhiều cấp:** job cha quản lý thứ tự các quy trình lớn, còn từng job con quản lý chi tiết các step bên trong.
- **Vận hành độc lập:** job con có thể được khởi chạy riêng để xử lý một đơn vị công việc hoặc phục vụ điều tra.
- **Quản lý metadata rõ ràng:** mỗi job con có lịch sử execution riêng, giúp quan sát trạng thái và lỗi ở cấp quy trình con.

Không nên dùng `JobStep` chỉ để gom vài step đơn giản nếu một `Flow` đã đủ rõ ràng. Một job con có metadata và danh tính riêng; điều này hữu ích khi cần ranh giới vận hành độc lập nhưng tạo thêm trách nhiệm về tham số, restart và theo dõi.

## 3. JobStep khác gì FlowStep?

`JobStep` và `FlowStep` đều cho phép đóng gói nhiều thao tác thành một đơn vị trong flow của job cha, nhưng phạm vi thực thi khác nhau.

| Tiêu chí | `JobStep` | `FlowStep` |
| --- | --- | --- |
| Đối tượng được gọi | Một `Job` khác | Một `Flow` gồm các step/transition |
| Execution metadata | Job con có `JobInstance` và `JobExecution` riêng | Các step trong flow chạy trong phạm vi job execution hiện tại |
| Job parameters | Có `JobParametersExtractor` để tạo tham số cho job con | Dùng tham số của job hiện tại; không tạo job instance mới |
| Có thể chạy độc lập | Job con có thể được khởi chạy độc lập | Flow thường được dùng như một phần của job |
| Phù hợp khi | Cần một quy trình con có danh tính và vòng đời job riêng | Chỉ cần tổ chức lại flow của các step trong cùng job |

Nếu chỉ muốn tái sử dụng một chuỗi step trong cùng job execution, cân nhắc `Flow` hoặc `FlowStep`. Nếu cần job con có tên, tham số, lịch sử và khả năng chạy độc lập, `JobStep` là lựa chọn phù hợp hơn.

## 4. Cấu hình Job con

Job con được khai báo như một bean `Job` bình thường. Ví dụ job con xác thực đơn hàng:

```java
@Bean
Job validateOrdersJob(JobRepository jobRepository,
                      Step readOrdersStep,
                      Step validateOrdersStep,
                      Step saveValidationResultStep) {
    return new JobBuilder("validateOrdersJob", jobRepository)
        .start(readOrdersStep)
        .next(validateOrdersStep)
        .next(saveValidationResultStep)
        .build();
}
```

Job con có thể dùng chunk step, tasklet step, flow, decider, listener và các cơ chế Spring Batch khác như một job độc lập. Nó có tên riêng là `validateOrdersJob`; tên này tham gia xác định `JobInstance` của job con.

Các step của job con vẫn dùng `JobRepository` và transaction manager phù hợp với hạ tầng batch của ứng dụng. Trong nhiều ứng dụng, job cha và job con dùng chung metadata repository để việc theo dõi và điều phối thống nhất.

## 5. Tạo JobStep bằng JobStepBuilder

Trong Spring Batch 5, có thể tạo `JobStep` bằng `JobStepBuilder`. Builder nhận `StepBuilder` của step cha, job con, launcher và parameter extractor:

```java
@Bean
Step validateOrdersJobStep(JobRepository jobRepository,
                           JobLauncher jobLauncher,
                           Job validateOrdersJob,
                           JobParametersExtractor childJobParametersExtractor) {
    return new JobStepBuilder(
            new StepBuilder("validateOrdersJobStep", jobRepository)
        )
        .job(validateOrdersJob)
        .launcher(jobLauncher)
        .parametersExtractor(childJobParametersExtractor)
        .build();
}
```

Các thành phần chính:

- `StepBuilder("validateOrdersJobStep", jobRepository)` tạo định nghĩa step ở job cha.
- `.job(validateOrdersJob)` chỉ định job con sẽ được chạy.
- `.launcher(jobLauncher)` cung cấp cơ chế khởi chạy job con.
- `.parametersExtractor(...)` tạo `JobParameters` cho lần chạy job con từ execution của job cha.
- `.build()` tạo `JobStep` để job cha sử dụng trong flow.

API builder ở các phiên bản Spring Batch cũ có thể khác. Hãy dùng cách cấu hình tương ứng với phiên bản thư viện của dự án; ví dụ trên sử dụng API builder của Spring Batch 5.

## 6. JobLauncher và JobParametersExtractor

`JobStep` không tự quyết định toàn bộ tham số của job con. Nó gọi `JobParametersExtractor` để tạo bộ tham số, sau đó dùng `JobLauncher` khởi chạy job con.

Hai thành phần này có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
| --- | --- |
| `JobLauncher` | Nhận job con và `JobParameters`, tạo yêu cầu thực thi job. |
| `JobParametersExtractor` | Trích xuất hoặc xây dựng `JobParameters` dựa trên execution của job cha. |
| `JobRepository` của launcher | Lưu `JobInstance`, `JobExecution` và metadata của job con. |

Nếu job con cần cùng tham số nghiệp vụ với job cha, có thể chuyển tiếp các tham số đó. Nếu job con cần thêm thông tin được tính ở step trước, có thể đưa giá trị vào `JobExecutionContext` của job cha rồi trích xuất thành tham số cho job con.

## 7. Sử dụng DefaultJobParametersExtractor

`DefaultJobParametersExtractor` là implementation có sẵn cho trường hợp truyền tham số đơn giản. Có thể cấu hình các key cần lấy từ execution context để bổ sung cho job con:

```java
@Bean
JobParametersExtractor childJobParametersExtractor() {
    DefaultJobParametersExtractor extractor =
        new DefaultJobParametersExtractor();
    extractor.setKeys(new String[] {"businessDate", "region"});
    return extractor;
}
```

Khi sử dụng extractor mặc định, hãy kiểm tra quy tắc truyền các job parameters của parent execution và các key được cấu hình theo phiên bản Spring Batch đang dùng. Các giá trị cần thiết phải tồn tại trong context đúng phạm vi trước khi `JobStep` gọi extractor.

Nếu tham số của job con cần quy tắc đặc biệt, ví dụ chuyển đổi kiểu, đánh dấu identifying/non-identifying hoặc kết hợp nhiều nguồn, có thể tự triển khai `JobParametersExtractor`.

## 8. Tạo tham số cho job con bằng extractor tùy chỉnh

Ví dụ dưới đây giả định job cha đã lưu `region` trong `JobExecutionContext`. Extractor chuyển tiếp tham số của job cha và thêm `region` như một identifying parameter của job con:

```java
public class ChildJobParametersExtractor
        implements JobParametersExtractor {

    @Override
    public JobParameters getJobParameters(Job job, StepExecution stepExecution) {
        JobExecution parentExecution = stepExecution.getJobExecution();
        JobParametersBuilder builder =
            new JobParametersBuilder(parentExecution.getJobParameters());

        ExecutionContext parentContext = parentExecution.getExecutionContext();
        if (parentContext.containsKey("region")) {
            builder.addString("region", parentContext.getString("region"), true);
        }

        return builder.toJobParameters();
    }
}
```

Đăng ký extractor:

```java
@Bean
JobParametersExtractor childJobParametersExtractor() {
    return new ChildJobParametersExtractor();
}
```

Ở đây, `stepExecution` là execution của `JobStep` thuộc job cha. Từ đó extractor lấy `JobExecution` cha và đọc job parameters/context. Nếu context không có key bắt buộc, ứng dụng nên quyết định rõ có ném lỗi cấu hình hay dùng giá trị mặc định; không nên âm thầm tạo tham số sai.

Việc đánh dấu `region` là identifying chỉ là ví dụ. Nếu vùng là một phần định danh của đơn vị công việc con, đánh dấu identifying là hợp lý. Nếu nó chỉ là metadata mô tả, có thể chọn non-identifying. Quyết định phải phù hợp với ý nghĩa của `JobInstance` con.

## 9. Chuyển dữ liệu từ step cha sang job con

Một step trước `JobStep` có thể tạo dữ liệu cần dùng khi khởi chạy job con. Ví dụ `PrepareStep` xác định vùng xử lý rồi đưa giá trị từ step context lên job context bằng `ExecutionContextPromotionListener`.

```java
@Bean
ExecutionContextPromotionListener promoteRegionListener() {
    ExecutionContextPromotionListener listener =
        new ExecutionContextPromotionListener();
    listener.setKeys(new String[] {"region"});
    listener.setStatuses(new String[] {"COMPLETED"});
    return listener;
}
```

Gắn listener vào step chuẩn bị:

```java
@Bean
Step prepareStep(JobRepository jobRepository,
                 PlatformTransactionManager transactionManager,
                 ExecutionContextPromotionListener promoteRegionListener) {
    return new StepBuilder("prepareStep", jobRepository)
        .tasklet((contribution, chunkContext) -> {
            contribution.getStepExecution()
                .getExecutionContext()
                .putString("region", "APAC");
            return RepeatStatus.FINISHED;
        }, transactionManager)
        .listener(promoteRegionListener)
        .build();
}
```

Khi `PrepareStep` hoàn tất với exit status `COMPLETED`, key `region` được promote lên `JobExecutionContext`. Extractor tùy chỉnh ở phần trước có thể đọc giá trị đó để tạo tham số cho job con.

Luồng dữ liệu:

```text
PrepareStep
  StepExecutionContext: region=APAC
          |
          v
ExecutionContextPromotionListener
          |
          v
Parent JobExecutionContext: region=APAC
          |
          v
JobParametersExtractor
          |
          v
Child JobParameters: region=APAC
          |
          v
JobLauncher khởi chạy ChildJob
```

Promotion chỉ nên thực hiện khi step kết thúc ở trạng thái được chấp nhận. Nếu step chuẩn bị thất bại, job cha thường không đi tiếp đến `JobStep`, và giá trị chưa được promote không nên được xem là đầu vào hợp lệ của job con.

## 10. Ghép job con vào job cha

Sau khi khai báo job con và `JobStep`, job cha có thể sử dụng step này như bất kỳ step nào khác:

```java
@Bean
Job dailySettlementJob(JobRepository jobRepository,
                       Step prepareStep,
                       Step validateOrdersJobStep,
                       Step publishReportStep) {
    return new JobBuilder("dailySettlementJob", jobRepository)
        .start(prepareStep)
        .next(validateOrdersJobStep)
        .next(publishReportStep)
        .build();
}
```

Khi job cha chạy:

1. `PrepareStep` thực hiện công việc chuẩn bị và có thể ghi dữ liệu vào job context.
2. `validateOrdersJobStep` gọi `JobLauncher` để khởi chạy `validateOrdersJob` với tham số được extractor tạo.
3. Job con chạy các step của nó theo flow riêng.
4. Khi job con kết thúc, `JobStep` phản ánh kết quả thực thi con vào trạng thái/exit status của step cha.
5. Nếu job con hoàn tất thành công, flow của job cha có thể tiếp tục đến `PublishReportStep`.

Nếu child job thất bại, `JobStep` thất bại và job cha thường dừng theo flow đã cấu hình. Có thể dùng transition của job cha để điều hướng các kết quả khác nhau nếu exit status của `JobStep` được thiết kế phù hợp.

## 11. Metadata của job cha và job con

`JobStep` tạo ra hai cấp metadata:

- Job cha có `JobInstance`, `JobExecution` và `StepExecution` cho `JobStep`.
- Job con có `JobInstance`, `JobExecution` và các `StepExecution` riêng.

```text
Parent JobInstance
  |
  +-- Parent JobExecution
        |
        +-- PrepareStep / StepExecution
        |
        +-- JobStep / StepExecution
              |
              +-- Child JobInstance
                    |
                    +-- Child JobExecution
                          |
                          +-- ChildStepA / StepExecution
                          +-- ChildStepB / StepExecution
```

`JobStep` không biến các step của job con thành step trực tiếp của job cha. Job con có tên và metadata độc lập, nhờ đó có thể tra cứu execution của parent và child riêng biệt.

Trong cấu hình phổ biến, parent và child dùng chung `JobRepository` để metadata được lưu trong cùng hệ thống. Khi điều tra lỗi, hãy bắt đầu từ parent `JobExecution`, tìm `StepExecution` của `JobStep`, rồi truy vấn child execution tương ứng qua metadata hoặc log có execution ID.

## 12. JobInstance của job con và identifying parameters

Danh tính `JobInstance` được xác định bởi tên job và các identifying `JobParameters`. Quy tắc này áp dụng độc lập cho job con.

Ví dụ, `validateOrdersJob` chạy với:

```text
job name = validateOrdersJob
businessDate = 2026-11-15 (identifying)
region = APAC (identifying)
```

Hai lần gọi job con với cùng tên và cùng identifying parameters sẽ nhắm đến cùng một `JobInstance`, kể cả khi được khởi chạy từ hai parent job khác nhau. Điều này có thể dẫn đến việc child job đã hoàn tất hoặc đang chạy và lần gọi tiếp theo bị từ chối theo quy tắc của Spring Batch.

Hãy chọn identifying parameters theo đơn vị công việc logic của job con. Nếu mỗi ngày/vùng là một đơn vị riêng, `businessDate` và `region` có thể là identifying. Nếu child job phải xử lý riêng theo parent batch ID, có thể thêm `parentBatchId` làm identifying parameter khi đó thực sự là một phần danh tính nghiệp vụ.

Không thêm timestamp hoặc UUID ngẫu nhiên chỉ để né lỗi `JobInstanceAlreadyCompleteException`. Làm vậy có thể tạo nhiều instance cho cùng một đơn vị công việc và khiến restart, đối soát khó kiểm soát. Dùng một mã lần chạy mới chỉ khi nghiệp vụ thực sự yêu cầu một lần xử lý độc lập mới.

## 13. Restart khi job con thất bại

Giả sử parent job gọi child job `validateOrdersJob`. Child job xử lý hai step đầu thành công nhưng step thứ ba thất bại:

```text
ParentJobExecution: FAILED
  JobStep: FAILED
    ChildJobExecution 1: FAILED
      ChildStepA: COMPLETED
      ChildStepB: COMPLETED
      ChildStepC: FAILED
```

Khi restart parent job với cùng identifying parameters, job cha có thể chạy lại `JobStep` theo restart behavior. Nếu extractor tạo cùng identifying parameters cho child job, `JobLauncher` sẽ tìm cùng child `JobInstance`; vì execution trước thất bại và child job cho phép restart, child job có thể tạo `JobExecution` mới để tiếp tục theo metadata của nó.

Điều này đòi hỏi:

- Child job được cấu hình restartable.
- Child `JobParameters` có cùng danh tính với lần chạy trước nếu muốn restart cùng instance.
- Reader/writer của child job hỗ trợ checkpoint và xử lý lại an toàn.
- Metadata child job còn đầy đủ và tương thích với code hiện tại.
- Parent flow cho phép chạy lại `JobStep` sau khi step trước thất bại.

Nếu child job đã `COMPLETED`, chạy lại cùng identifying parameters thường không phải restart hợp lệ. Hãy phân biệt việc tiếp tục một child instance thất bại với việc yêu cầu child job xử lý một đơn vị nghiệp vụ mới.

## 14. Khi job con hoàn tất nhưng job cha thất bại sau đó

Một trường hợp cần chú ý: child job đã hoàn tất, `JobStep` của parent đã hoàn tất, nhưng một step phía sau của parent thất bại.

```text
ParentJobExecution: FAILED
  PrepareStep: COMPLETED
  ChildJobStep: COMPLETED
    ChildJobExecution: COMPLETED
  PublishReportStep: FAILED
```

Khi restart parent job, step `ChildJobStep` đã hoàn thành thường được bỏ qua theo restart behavior mặc định. Nếu cấu hình cho phép chạy lại step đã hoàn tất, JobStep có thể gọi lại child job với cùng parameters và child instance đã `COMPLETED`; khi đó việc chạy lại có thể bị từ chối.

Vì vậy, hãy xác định rõ liệu child job có cần chạy lại khi parent tiếp tục hay không. Nếu child job chỉ cần chạy một lần cho một batch, giữ step completed và tiếp tục từ step cha bị lỗi thường là hành vi mong muốn. Nếu cần chạy lại child job có chủ đích, hãy dùng identifying parameters mới cho một đơn vị công việc mới hoặc thiết kế quy trình reprocess riêng.

## 15. Trạng thái child job và flow của parent job

Kết quả của child job ảnh hưởng đến `JobStep` trong parent job. Khi child job hoàn tất, parent step có thể hoàn tất và flow đi tiếp. Khi child job thất bại hoặc dừng, parent step phản ánh kết quả tương ứng và parent flow có thể dừng hoặc chuyển nhánh tùy cấu hình.

Ví dụ minh họa transition ở job cha:

```java
@Bean
Job parentJob(JobRepository jobRepository,
              Step validateChildJobStep,
              Step handleValidationFailureStep,
              Step continueStep) {
    return new JobBuilder("parentJob", jobRepository)
        .start(validateChildJobStep)
            .on("COMPLETED").to(continueStep)
        .from(validateChildJobStep)
            .on("FAILED").to(handleValidationFailureStep)
        .from(continueStep)
            .on("*").end()
        .from(handleValidationFailureStep)
            .on("*").fail()
        .end()
        .build();
}
```

Transition pattern so khớp exit code của step. Nếu cần xử lý trạng thái tùy chỉnh từ child job, hãy xác định exit status mà child job trả về và cách JobStep chuyển kết quả đó lên parent step. Không nên chỉ nhìn `BatchStatus` mà bỏ qua `ExitStatus`.

## 16. JobLauncher đồng bộ và bất đồng bộ

`JobStep` dùng `JobLauncher` để khởi chạy job con. Với cách điều phối thông thường, launcher đồng bộ giúp `JobStep` nhận được kết quả cuối của child job trước khi parent flow tiếp tục.

Nếu dùng launcher bất đồng bộ, lời gọi có thể trả về khi child execution vẫn đang chạy. Khi đó, parent step không thể được thiết kế như thể child đã hoàn tất ngay lập tức nếu chưa có cơ chế theo dõi và đồng bộ kết quả. Cần cân nhắc kỹ cách launcher được cấu hình và yêu cầu orchestration; không nên thay launcher đồng bộ bằng asynchronous chỉ để tăng concurrency.

Nếu mục tiêu là chạy nhiều job con song song, hãy thiết kế cơ chế điều phối song song có theo dõi trạng thái, giới hạn tài nguyên và xử lý lỗi rõ ràng. `JobStep` tự nó không phải cấu hình parallel execution.

## 17. Transaction boundary giữa parent và child job

Parent `JobStep` và các step của child job có transaction boundary riêng. Transaction của step cha không bao bọc toàn bộ các chunk của job con thành một transaction duy nhất.

```text
Parent JobStep
  transaction của step cha / thao tác launch
        |
        v
Child JobExecution
  ChildStepA: chunk transaction 1, 2, ...
  ChildStepB: chunk transaction 1, 2, ...
  ChildStepC: tasklet/chunk transaction riêng
```

Các chunk của child job có thể đã commit trước khi child job thất bại. Khi parent job thất bại, những chunk đã commit của child job không tự động rollback. Việc restart child job dựa vào metadata và checkpoint của child execution.

Nếu child job ghi dữ liệu nghiệp vụ và parent job sau đó thất bại, dữ liệu child đã commit vẫn tồn tại. Parent job cần được thiết kế để tiếp tục từ trạng thái đó, hoặc có quy trình bù trừ/reprocess nếu nghiệp vụ yêu cầu.

Tương tự, side effect của child job như gửi email hoặc gọi API ngoài transaction không được hoàn tác chỉ vì parent step thất bại. Hãy áp dụng idempotency và transactional outbox ở nơi phát sinh tác động.

## 18. JobStep và khả năng tái sử dụng job con

Một ưu điểm của job con là có thể được gọi từ nhiều job cha. Ví dụ `validateOrdersJob` có thể được sử dụng trong `dailySettlementJob`, `monthlyReconciliationJob` và một job kiểm tra lại dữ liệu.

Tuy nhiên, tái sử dụng không có nghĩa mọi parent đều có thể truyền cùng tham số. Hãy định nghĩa hợp đồng tham số của child job:

- Tham số bắt buộc, chẳng hạn `businessDate` hoặc `inputFile`.
- Tham số identifying dùng để xác định đơn vị công việc con.
- Tham số non-identifying chỉ dùng cho thông tin vận hành.
- Giá trị mặc định hoặc quy tắc khi thiếu tham số.
- Những key context mà parent phải cung cấp.

Một child job nên kiểm tra tham số bắt buộc sớm, ví dụ trong validation step đầu tiên. Nếu parent gọi child job mà thiếu `businessDate`, lỗi nên được báo rõ thay vì để step sau thất bại với lỗi khó hiểu.

## 19. Theo dõi và điều tra lỗi JobStep

Khi parent job thất bại ở JobStep, cần theo dõi cả hai cấp execution:

1. Parent `JobExecution` cho biết toàn bộ job cha thất bại ở đâu.
2. Parent `StepExecution` của JobStep cho biết step gọi job con có trạng thái gì.
3. Child `JobExecution` cho biết job con được khởi chạy với tham số nào và kết thúc ra sao.
4. Các child `StepExecution` xác định step nội bộ nào thất bại và checkpoint cuối cùng.

Nên ghi log các thông tin:

- Parent job name và parent execution ID.
- Parent JobStep name và step execution ID.
- Child job name và child execution ID.
- Child identifying parameters cần thiết để đối soát.
- Batch ID hoặc business key của đơn vị công việc.
- Exit status và failure exception ở cả hai cấp.

Không ghi toàn bộ payload nhạy cảm của `JobParameters` hoặc `ExecutionContext` vào log. Chỉ ghi định danh và các trường cần thiết để truy vết.

Có thể dùng `JobExplorer` để truy vấn parent/child execution và `JobOperator` để thực hiện thao tác vận hành phù hợp. Trước khi restart, xác minh child execution không còn chạy ở node khác và child job có thể restart với cùng identifying parameters.

## 20. Kiểm thử JobStep

Nên kiểm thử cả việc job con được gọi đúng tham số và cách trạng thái child ảnh hưởng đến parent. Một test tích hợp có thể dùng `JobLauncherTestUtils` để chạy parent job, sau đó tra cứu metadata của child job bằng `JobExplorer`.

Các trường hợp cần kiểm tra:

- Parent job chạy thành công và child job được khởi chạy.
- Child job nhận đúng tham số từ parent job parameters.
- Giá trị được promote từ step context sang job context được extractor chuyển đúng.
- Child job hoàn tất thì parent JobStep hoàn tất và parent flow đi tiếp.
- Child job thất bại thì parent step/job phản ánh lỗi đúng.
- Restart parent sau khi child thất bại tiếp tục child instance với identifying parameters phù hợp.
- Parent restart sau khi child đã hoàn tất không vô tình chạy lại child nếu không cần.
- Hai parent job khác nhau gọi child job với cùng parameters được xử lý theo quy tắc `JobInstance` dự kiến.

Ví dụ kiểm tra child execution:

```java
JobExecution parentExecution = jobLauncherTestUtils.launchJob(parentParameters);

assertThat(parentExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

List<JobInstance> childInstances = jobExplorer.getJobInstances(
    "validateOrdersJob", 0, 10
);
assertThat(childInstances).isNotEmpty();

JobExecution childExecution = jobExplorer.getJobExecutions(
    childInstances.get(0)
).get(0);

assertThat(childExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

Đoạn code là ví dụ khái niệm; trong test có nhiều child instance, hãy chọn đúng instance bằng identifying parameters thay vì lấy phần tử đầu tiên. Cũng cần dùng database metadata riêng cho test và tắt auto-launch nếu Spring Boot tự động chạy job khi context khởi tạo.

## 21. Các lỗi thường gặp khi dùng JobStep

**Không cấu hình JobParametersExtractor:** child job có thể thiếu tham số bắt buộc hoặc nhận tham số không đúng. Khai báo extractor rõ ràng và test giá trị thực tế.

**Nhầm step context với job context:** dữ liệu từ step trước cần được promote hoặc chuyển bằng cơ chế khác trước khi extractor đọc. Không giả định child job tự nhìn thấy step context của parent.

**Trùng child JobInstance:** nhiều parent execution có thể tạo cùng child job name và identifying parameters. Thiết kế danh tính child job phù hợp với đơn vị công việc.

**Dùng timestamp ngẫu nhiên để tránh lỗi instance đã hoàn tất:** cách này tạo instance mới không cần thiết và làm mất semantics restart. Chỉ dùng identifying parameter mới khi đó là công việc logic mới.

**Cho rằng parent rollback sẽ rollback child:** child job có transaction và execution riêng; chunk đã commit của child không tự bị rollback khi parent thất bại.

**Dùng launcher bất đồng bộ mà không điều phối kết quả:** parent có thể không chờ child hoàn tất như mong đợi. Thiết kế rõ cơ chế đồng bộ/tracking nếu cần asynchronous.

**Dùng JobStep thay FlowStep cho mọi trường hợp:** nếu chỉ cần tổ chức các step trong cùng job, `Flow` có thể đơn giản hơn và tránh thêm một JobInstance.

**Không theo dõi child execution ID:** chỉ xem parent JobStep không đủ để chẩn đoán step nội bộ của child. Ghi và tra cứu cả hai cấp metadata.

**Job con không restartable hoặc reader không lưu checkpoint:** parent restart không thể tự làm child tiếp tục đúng vị trí nếu child job không hỗ trợ restart.

## 22. Cách thiết kế JobStep trong production

Trước tiên, xác định quy trình nào thực sự cần là job con độc lập. Nếu cần tái sử dụng, vận hành riêng, lịch sử execution riêng hoặc hợp đồng tham số riêng, hãy tách thành `Job`. Nếu chỉ cần nhóm các step trong cùng một job execution, ưu tiên `Flow`/`FlowStep`.

Tiếp theo, định nghĩa rõ hợp đồng tham số của child job. Dùng `JobParametersExtractor` để chuyển tiếp tham số cha và các giá trị cần thiết từ job context. Chọn identifying parameters theo đơn vị công việc logic của child job; tránh timestamp ngẫu nhiên để né lỗi trùng instance.

Khai báo `JobStep` với launcher và repository được cấu hình nhất quán. Trong cách điều phối thông thường, dùng launcher đồng bộ để parent flow nhận được kết quả cuối của child. Theo dõi cả parent execution và child execution, đồng thời kiểm tra restart ở hai cấp.

Cuối cùng, nhớ rằng child job có transaction boundary riêng. Các chunk đã commit của child vẫn tồn tại khi parent thất bại. Thiết kế writer idempotent, checkpoint reader và quy trình đối soát để parent có thể tiếp tục an toàn. Khi các ranh giới job, tham số và metadata được xác định rõ, `JobStep` giúp tổ chức các quy trình batch lớn thành những job con có thể tái sử dụng và vận hành độc lập.
