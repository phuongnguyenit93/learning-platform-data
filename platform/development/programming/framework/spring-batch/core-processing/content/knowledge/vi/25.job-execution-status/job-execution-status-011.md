# Kiểm thử trạng thái cuối

Trong Spring Batch, kiểm thử trạng thái cuối giúp xác nhận một Job hoặc Step kết thúc đúng như thiết kế sau khi xử lý dữ liệu, gặp lỗi, đi qua nhánh flow hoặc được dừng có chủ đích. Một bài kiểm thử Batch không nên chỉ xác nhận phương thức launch không ném exception; cần kiểm tra metadata mà Spring Batch ghi vào `JobExecution` và `StepExecution`.

Hai thông tin cần kiểm tra cùng nhau là `BatchStatus` và `ExitStatus`:

- `BatchStatus` mô tả trạng thái vòng đời của JobExecution hoặc StepExecution, ví dụ `COMPLETED`, `FAILED`, `STOPPED`.
- `ExitStatus` mô tả mã kết quả và thông tin bổ sung, ví dụ `COMPLETED`, `FAILED`, `STOPPED` hoặc mã nghiệp vụ tùy chỉnh như `NO_DATA`.

Một Step có thể có `BatchStatus.COMPLETED` nhưng `ExitStatus` là `NO_DATA`; Job dùng mã này để chọn nhánh flow. Vì vậy, chỉ kiểm tra một trong hai trường có thể bỏ sót lỗi điều khiển flow hoặc kết quả nghiệp vụ.

## 1. BatchStatus và ExitStatus khác nhau như thế nào?

`BatchStatus` là enum thể hiện vòng đời thực thi. Các trạng thái thường gặp:

| BatchStatus | Ý nghĩa |
|---|---|
| `STARTING` | Execution đang trong quá trình khởi tạo. |
| `STARTED` | Execution đang chạy. |
| `STOPPING` | Đã nhận yêu cầu dừng và đang chờ dừng. |
| `STOPPED` | Execution đã dừng và có thể được restart nếu đủ điều kiện. |
| `FAILED` | Execution kết thúc do lỗi. |
| `COMPLETED` | Execution hoàn tất thành công theo flow. |
| `ABANDONED` | Execution được đánh dấu bỏ, không tiếp tục restart theo quy trình thông thường. |
| `UNKNOWN` | Không xác định được trạng thái thực thi đáng tin cậy. |

`ExitStatus` là một value object có exit code và exit description. Exit code thường được dùng để điều khiển transition của Job flow. Một số giá trị chuẩn tương ứng với trạng thái phổ biến:

```java
ExitStatus.COMPLETED
ExitStatus.FAILED
ExitStatus.STOPPED
```

Ứng dụng cũng có thể tạo exit code riêng:

```java
new ExitStatus("NO_DATA")
new ExitStatus("VALIDATION_WARNING")
new ExitStatus("ALREADY_PROCESSED")
```

Ví dụ, Step validation thực hiện thành công nhưng phát hiện không có dữ liệu. Step có thể có `BatchStatus.COMPLETED` và `ExitStatus.NO_DATA`. Job flow có thể dùng `on("NO_DATA")` để kết thúc thành công hoặc chuyển đến Step tạo báo cáo rỗng.

## 2. Nên kiểm tra trạng thái ở cấp Job hay Step?

Một Job có thể gồm nhiều Step. Mỗi Step có `StepExecution` riêng, còn toàn bộ lần chạy Job có `JobExecution`.

Kiểm thử nên xác nhận cả hai cấp khi trạng thái Step ảnh hưởng đến kết quả Job:

- Job có kết thúc `COMPLETED`, `FAILED` hay `STOPPED` như mong đợi không?
- Step quan trọng có `BatchStatus` đúng không?
- Exit code của Step có đúng để chọn nhánh flow không?
- Step nào đã chạy, Step nào bị bypass?
- Có failure exception nào được ghi nhận không?
- Skip, read, write, commit và rollback count có phản ánh kết quả mong đợi không?

Ví dụ, Job có thể kết thúc `COMPLETED` dù một Step trả exit code `NO_DATA` và một Step tùy chọn đã bị bypass. Nếu chỉ kiểm tra Job status, bài test chưa xác nhận được nhánh flow đúng.

## 3. Dùng @SpringBatchTest và JobLauncherTestUtils

Spring Batch cung cấp các tiện ích kiểm thử trong module `spring-batch-test`. Annotation `@SpringBatchTest` đăng ký các tiện ích và listener hỗ trợ kiểm thử Job/Step, trong đó có:

- `JobLauncherTestUtils`: launch Job hoặc một Step để kiểm thử.
- `JobRepositoryTestUtils`: hỗ trợ dọn metadata execution trong môi trường test.
- `StepScopeTestExecutionListener` và `JobScopeTestExecutionListener`: hỗ trợ kiểm thử bean có scope Batch.

Ví dụ dùng Spring Boot và JUnit 5:

```java
@SpringBootTest
@SpringBatchTest
class ImportJobStatusTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("importJob")
    private Job importJob;

    @BeforeEach
    void configureJob() {
        jobLauncherTestUtils.setJob(importJob);
    }

    @Test
    void jobCompletesSuccessfully() throws Exception {
        JobExecution execution = jobLauncherTestUtils.launchJob(
                testJobParameters());

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getExitStatus().getExitCode())
                .isEqualTo(ExitStatus.COMPLETED.getExitCode());
    }

    private JobParameters testJobParameters() {
        return new JobParametersBuilder()
                .addString("businessDate", "2026-11-15")
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();
    }
}
```

Các import chính đến từ `org.springframework.batch.test`, `org.springframework.batch.core`, `org.springframework.batch.core.launch`, `org.springframework.batch.core.repository`, cùng JUnit và AssertJ. Test cần có `spring-batch-test` trong test dependencies và một cấu hình Batch có `JobRepository`, `JobLauncher` cùng Job được kiểm thử.

Nếu application context có nhiều Job bean, hãy chỉ định Job cần kiểm thử bằng `setJob(job)` hoặc cấu hình test context phù hợp. Không để utility tự chọn một Job không xác định.

### Vì sao cần JobParameters riêng cho mỗi test?

Spring Batch xác định `JobInstance` bằng Job name và identifying JobParameters. Nếu một test chạy Job thành công rồi test khác launch cùng Job với cùng identifying parameters, lần launch sau có thể bị từ chối vì JobInstance đã `COMPLETED`.

Một cách đơn giản là thêm identifying parameter dành riêng cho test, ví dụ `testRunId` dùng UUID. Nếu test đang kiểm tra restart của cùng JobInstance, ngược lại phải giữ nguyên chính xác identifying parameters giữa lần chạy đầu và lần restart.

Không nên thêm parameter ngẫu nhiên vào mọi test mà không hiểu mục tiêu. Test trạng thái độc lập cần JobInstance mới; test restart cần cùng JobInstance.

## 4. Kiểm thử Job hoàn tất thành công

Với Job thành công, kiểm tra `BatchStatus.COMPLETED` và exit code mong đợi. Nếu không tùy chỉnh ExitStatus, mã kết quả thường là `COMPLETED`.

```java
@Test
void importJobHasCompletedStatus() throws Exception {
    jobLauncherTestUtils.setJob(importJob);

    JobExecution execution = jobLauncherTestUtils.launchJob(
            testJobParameters());

    assertThat(execution.getStatus())
            .isEqualTo(BatchStatus.COMPLETED);
    assertThat(execution.getExitStatus().getExitCode())
            .isEqualTo("COMPLETED");
    assertThat(execution.getEndTime()).isNotNull();
}
```

`endTime` giúp xác nhận execution đã kết thúc. Với JobLauncher đồng bộ, `launchJob` thường trả về sau khi Job kết thúc. Nếu ứng dụng cấu hình asynchronous JobLauncher, không được giả định execution đã terminal ngay khi phương thức launch trả về; cần chờ kết thúc và đọc lại execution từ `JobExplorer`.

## 5. Kiểm thử StepExecution

`JobExecution` cung cấp các `StepExecution` được tạo trong lần chạy đó. Có thể tìm Step theo tên và kiểm tra trạng thái:

```java
private StepExecution findStepExecution(
        JobExecution execution,
        String stepName) {

    return execution.getStepExecutions().stream()
            .filter(step -> step.getStepName().equals(stepName))
            .findFirst()
            .orElseThrow(() -> new AssertionError(
                    "StepExecution not found: " + stepName));
}

@Test
void loadStepCompletes() throws Exception {
    jobLauncherTestUtils.setJob(importJob);

    JobExecution execution = jobLauncherTestUtils.launchJob(
            testJobParameters());

    StepExecution loadStep = findStepExecution(execution, "loadStep");

    assertThat(loadStep.getStatus())
            .isEqualTo(BatchStatus.COMPLETED);
    assertThat(loadStep.getExitStatus().getExitCode())
            .isEqualTo("COMPLETED");
    assertThat(loadStep.getEndTime()).isNotNull();
}
```

Kiểm tra Step riêng giúp định vị lỗi. Job có thể kết thúc theo một transition tùy chỉnh trong khi Step trước có exit code riêng; việc chỉ xem trạng thái Job không cho biết Step nào đã chạy và kết quả ra sao.

## 6. Kiểm thử Job thất bại

Để kiểm thử `FAILED`, cần tạo một điều kiện lỗi xác định trong test, ví dụ một Tasklet test ném exception hoặc một processor nhận item lỗi. Không nên phụ thuộc vào dịch vụ thật đang ngẫu nhiên lỗi.

Ví dụ một Step cố ý thất bại trong test:

```java
@Bean
Step failingStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("failingStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                throw new IllegalStateException("Expected test failure");
            }, transactionManager)
            .build();
}

@Bean
Job failingJob(JobRepository jobRepository, Step failingStep) {
    return new JobBuilder("failingJob", jobRepository)
            .start(failingStep)
            .build();
}
```

Kiểm thử kết quả:

```java
@Test
void jobFailsWhenStepThrowsException() throws Exception {
    jobLauncherTestUtils.setJob(failingJob);

    JobExecution execution = jobLauncherTestUtils.launchJob(
            testJobParameters());

    assertThat(execution.getStatus())
            .isEqualTo(BatchStatus.FAILED);
    assertThat(execution.getExitStatus().getExitCode())
            .isEqualTo(ExitStatus.FAILED.getExitCode());
    assertThat(execution.getAllFailureExceptions()).isNotEmpty();

    StepExecution step = findStepExecution(execution, "failingStep");
    assertThat(step.getStatus()).isEqualTo(BatchStatus.FAILED);
    assertThat(step.getFailureExceptions()).isNotEmpty();
}
```

Một số exception có thể được xử lý bằng retry hoặc skip, nên không phải cứ ném exception trong processor/writer là Job chắc chắn `FAILED`. Test phải cấu hình exception nằm ngoài retry/skip policy hoặc làm vượt giới hạn để kiểm tra nhánh thất bại.

## 7. Kiểm thử STOPPED

Job có thể dừng theo flow transition `.stop()` hoặc `.stopAndRestart(...)`. Đây là cách tạo kết quả `STOPPED` xác định trong integration test, không cần dựa vào timing của một thread đang chạy.

Ví dụ flow có nhánh chờ phê duyệt:

```java
@Bean
Job approvalJob(
        JobRepository jobRepository,
        Step approvalCheckStep,
        Step paymentStep) {

    return new JobBuilder("approvalJob", jobRepository)
            .start(approvalCheckStep)
                .on("WAITING_FOR_APPROVAL").stop()
            .from(approvalCheckStep)
                .on("APPROVED").to(paymentStep)
            .end()
            .build();
}
```

Khi test fixture làm `approvalCheckStep` trả exit code `WAITING_FOR_APPROVAL`, kiểm tra:

```java
assertThat(execution.getStatus()).isEqualTo(BatchStatus.STOPPED);
assertThat(execution.getExitStatus().getExitCode())
        .isEqualTo(ExitStatus.STOPPED.getExitCode());
```

Đồng thời kiểm tra `paymentStep` chưa có `StepExecution`, vì flow dừng trước khi gọi Step đó.

### Kiểm thử JobOperator.stop

`JobOperator.stop(executionId)` gửi yêu cầu dừng một Job đang chạy. Kiểm thử đường này thường cần JobLauncher bất đồng bộ hoặc một Step có thời gian chờ/điểm đồng bộ được kiểm soát. Test cần:

1. Launch Job và lấy JobExecution ID.
2. Chờ đến khi execution thực sự bắt đầu.
3. Gọi `jobOperator.stop(executionId)`.
4. Chờ Job chuyển sang trạng thái terminal.
5. Đọc lại execution và xác nhận `STOPPED`.

Không nên dùng `Thread.sleep` với một khoảng thời gian tùy ý rồi giả định Job đã ở đúng trạng thái. Dùng latch/barrier trong test fixture hoặc thư viện chờ có timeout để đồng bộ theo một sự kiện xác định. Cũng cần phân biệt yêu cầu stop đã được chấp nhận với việc Job đã thực sự chuyển sang `STOPPED`.

## 8. Kiểm thử ExitStatus tùy chỉnh và flow routing

Một Step có thể hoàn tất thành công về mặt kỹ thuật nhưng trả exit code nghiệp vụ:

```java
@Bean
Step checkInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("checkInputStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                contribution.setExitStatus(new ExitStatus("NO_DATA"));
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Flow có thể dùng exit code đó để kết thúc thành công hoặc đi đến Step khác:

```java
@Bean
Job optionalImportJob(
        JobRepository jobRepository,
        Step checkInputStep,
        Step importStep,
        Step emptyReportStep) {

    return new JobBuilder("optionalImportJob", jobRepository)
            .start(checkInputStep)
                .on("NO_DATA").to(emptyReportStep)
            .from(checkInputStep)
                .on("COMPLETED").to(importStep)
            .from(emptyReportStep)
                .on("COMPLETED").end()
            .from(importStep)
                .on("COMPLETED").end()
            .end()
            .build();
}
```

Kiểm thử cần xác nhận cả exit code của Step và Step tiếp theo được gọi:

```java
StepExecution check = findStepExecution(execution, "checkInputStep");

assertThat(check.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(check.getExitStatus().getExitCode()).isEqualTo("NO_DATA");

assertThat(execution.getStepExecutions())
        .extracting(StepExecution::getStepName)
        .contains("emptyReportStep")
        .doesNotContain("importStep");
```

Job có thể kết thúc `COMPLETED` sau khi chạy `emptyReportStep`. Test chỉ kiểm tra Job status mà không kiểm tra các Step sẽ không phát hiện trường hợp flow đi nhầm nhánh.

## 9. Kiểm thử Step bị bypass

Khi conditional transition bỏ qua một Step, Step đó không được thực thi và không có `StepExecution` trong JobExecution hiện tại.

Có thể kiểm tra bằng cách xác nhận danh sách StepExecution không chứa tên Step bị bypass:

```java
assertThat(execution.getStepExecutions())
        .extracting(StepExecution::getStepName)
        .doesNotContain("optionalEnrichmentStep");
```

Đây là kiểm tra flow. Không tìm `BatchStatus.SKIPPED` cho Step bị bypass; skip item trong chunk và bypass Step là hai cơ chế khác nhau.

## 10. Kiểm thử skip và retry nhưng Job vẫn COMPLETED

Một Job có thể kết thúc `COMPLETED` dù có item bị skip hoặc được retry thành công. Vì vậy, bài test trạng thái cuối nên kiểm tra thêm bộ đếm khi fault tolerance là một phần yêu cầu.

Ví dụ Step cho phép skip một exception dữ liệu:

```java
@Test
void jobCompletesWithinSkipLimit() throws Exception {
    jobLauncherTestUtils.setJob(importJob);

    JobExecution execution = jobLauncherTestUtils.launchJob(
            testJobParameters());

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

    StepExecution step = findStepExecution(execution, "importStep");
    assertThat(step.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    assertThat(step.getSkipCount()).isEqualTo(2);
    assertThat(step.getProcessSkipCount()).isEqualTo(2);
}
```

Các giá trị trong ví dụ là kết quả mong đợi của test fixture, không phải giá trị mặc định. Nếu retry cuối cùng thành công, Step vẫn có thể `COMPLETED`; cần kiểm tra retry metric/listener hoặc số lần gọi mock để xác nhận retry đã xảy ra.

Nếu skip count vượt `skipLimit`, Step thường thất bại. Nên có test riêng cho đúng ngưỡng và vượt ngưỡng để xác nhận policy hoạt động như thiết kế.

## 11. Kiểm thử restart và JobInstance identity

Restart là một phần quan trọng của trạng thái cuối. Sau một execution `FAILED` hoặc `STOPPED` đủ điều kiện, lần chạy tiếp theo cần tạo JobExecution mới cho cùng JobInstance.

Ví dụ kiểm thử với cùng identifying parameters:

```java
@Test
void restartUsesSameJobInstance() throws Exception {
    jobLauncherTestUtils.setJob(restartableJob);

    JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15")
            .addString("testRunId", UUID.randomUUID().toString())
            .toJobParameters();

    JobExecution firstExecution =
            jobLauncherTestUtils.launchJob(parameters);

    assertThat(firstExecution.getStatus()).isEqualTo(BatchStatus.FAILED);

    // Test fixture được cấu hình để lần chạy kế tiếp thành công.
    JobExecution restartedExecution =
            jobLauncherTestUtils.launchJob(parameters);

    assertThat(restartedExecution.getStatus())
            .isEqualTo(BatchStatus.COMPLETED);
    assertThat(restartedExecution.getJobInstance().getInstanceId())
            .isEqualTo(firstExecution.getJobInstance().getInstanceId());
    assertThat(restartedExecution.getId())
            .isNotEqualTo(firstExecution.getId());
}
```

Test fixture cần tạo được lần chạy đầu thất bại và lần chạy sau thành công, ví dụ service test có trạng thái điều khiển. Điều quan trọng là hai lần launch dùng cùng identifying parameters. Nếu thêm `testRunId` mới ở lần thứ hai, test sẽ tạo JobInstance mới và không kiểm tra restart.

Nếu muốn kiểm tra API restart trực tiếp, có thể dùng `JobOperator.restart(previousExecutionId)` sau khi execution cũ đã ở trạng thái restartable. Khi đó có thể tra cứu JobExecution mới qua `JobExplorer` bằng ID được trả về.

## 12. Kiểm tra failure exception và exit description

Khi Job thất bại, chỉ assert `BatchStatus.FAILED` có thể chưa đủ. Có thể kiểm tra failure exception ở cấp Job hoặc Step:

```java
assertThat(execution.getAllFailureExceptions())
        .anySatisfy(exception ->
                assertThat(exception)
                        .isInstanceOf(IllegalStateException.class));

StepExecution failedStep = findStepExecution(execution, "failingStep");

assertThat(failedStep.getFailureExceptions())
        .anySatisfy(exception ->
                assertThat(exception.getMessage())
                        .contains("Expected test failure"));
```

`ExitStatus.getExitDescription()` cũng có thể chứa thông tin chẩn đoán. Không nên assert toàn bộ stack trace hoặc message phụ thuộc môi trường nếu mục tiêu test chỉ là xác nhận trạng thái. Hãy kiểm tra exception type, mã lỗi nghiệp vụ hoặc một đoạn thông tin ổn định.

Tránh đưa dữ liệu nhạy cảm vào failure description hoặc log. Các message từ database, HTTP client hoặc input file có thể chứa thông tin không nên hiển thị trong dashboard vận hành.

## 13. Kiểm thử trạng thái của Job flow nhiều nhánh

Với Job có nhiều transition, nên kiểm tra từng đường đi quan trọng:

| Điều kiện | Step/ExitStatus đầu vào | Kết quả mong đợi |
|---|---|---|
| Dữ liệu hợp lệ | `COMPLETED` | Chạy Step import rồi report; Job `COMPLETED`. |
| Không có dữ liệu | `NO_DATA` | Bypass import, chạy report rỗng; Job `COMPLETED`. |
| Dữ liệu không hợp lệ nghiêm trọng | `INVALID_DATA` | Đi nhánh fail hoặc Step báo lỗi; Job `FAILED`. |
| Chờ phê duyệt | `WAITING_FOR_APPROVAL` | Flow stop; Job `STOPPED`. |
| Step xử lý ném exception không được skip/retry | `FAILED` | Job `FAILED`, failure exception được ghi nhận. |

Không cần kiểm thử mọi tổ hợp có thể tưởng tượng. Hãy tập trung vào từng nhánh flow được khai báo và các điều kiện biên có ý nghĩa nghiệp vụ. Mỗi test nên có dữ liệu đầu vào xác định để kết quả có thể lặp lại.

## 14. Kiểm thử JobLauncherTestUtils.launchStep

Nếu chỉ muốn kiểm tra một Step mà không chạy toàn bộ Job, `JobLauncherTestUtils` cung cấp `launchStep`:

```java
@Test
void validateStepCompletesInIsolation() throws Exception {
    jobLauncherTestUtils.setJob(importJob);

    JobExecution execution = jobLauncherTestUtils.launchStep(
            "validateStep",
            testJobParameters());

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

    StepExecution step = findStepExecution(execution, "validateStep");
    assertThat(step.getStatus()).isEqualTo(BatchStatus.COMPLETED);
}
```

`launchStep` hữu ích để kiểm tra reader, processor, writer, listener hoặc StepScope bean trong phạm vi Step. Tuy nhiên, nó không thay thế integration test cho toàn bộ Job flow. Nếu cần xác nhận transition, bypass Step, Job final status hoặc restart, hãy launch Job thực tế.

## 15. Kiểm thử StepScope và JobScope

Reader/processor/writer có thể dùng `@StepScope` hoặc `@JobScope` để nhận JobParameters và ExecutionContext. Trong test, `@SpringBatchTest` đăng ký các listener hỗ trợ tạo scope tương ứng.

Với kiểm thử component độc lập, có thể dùng `StepScopeTestUtils` để chạy một callback trong StepScope với `ExecutionContext` xác định:

```java
ExecutionContext context = new ExecutionContext();
context.putString("inputFile", "classpath:orders.csv");

StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(jobParameters, context);

StepScopeTestUtils.doInStepScope(stepExecution, () -> {
    ItemReader<OrderInput> reader = applicationContext.getBean(
            "orderReader", ItemReader.class);
    // Thực hiện các lần read và assert kết quả.
    return null;
});
```

Đoạn code minh họa cách thiết lập scope; kiểu generic và cách lấy bean cần khớp với bean definition trong ứng dụng. Với JobScope, dùng tiện ích test tương ứng hoặc chạy Job qua `JobLauncherTestUtils` để framework thiết lập scope tự nhiên.

## 16. JobRepositoryTestUtils và dữ liệu test

Job metadata được lưu trong JobRepository. Nếu nhiều test dùng cùng database metadata và identifying parameters giống nhau, kết quả test có thể ảnh hưởng lẫn nhau.

Hai cách thường dùng:

- Tạo identifying JobParameters riêng cho từng test.
- Dùng `JobRepositoryTestUtils` để dọn metadata sau test trong một repository dành riêng cho test.

Ví dụ:

```java
@Autowired
private JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanBatchMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Chỉ dùng cách dọn này trên database/test repository cô lập. `removeJobExecutions()` có thể xóa các execution metadata trong repository được cấu hình; không gọi trên repository dùng chung với dữ liệu vận hành hoặc test khác. Trong môi trường test song song, mỗi test suite nên có database/schema riêng hoặc chiến lược isolation rõ ràng.

Không nên dựa vào `@Transactional` trên test method để tự động rollback toàn bộ Job. JobLauncher có thể chạy trong transaction khác hoặc thread khác; metadata và business data có thể được commit độc lập với transaction của test.

## 17. Kiểm thử asynchronous JobLauncher

Nếu JobLauncher dùng TaskExecutor bất đồng bộ, `launchJob()` có thể trả về khi Job vẫn ở trạng thái `STARTED`. Khi đó, đoạn test sau có thể sai:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);
assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

Test cần chờ execution đạt trạng thái terminal, sau đó đọc lại từ `JobExplorer` hoặc repository để có metadata mới nhất.

Một cách tiếp cận:

1. Launch Job và lấy execution ID.
2. Dùng `JobExplorer.getJobExecution(id)` để đọc trạng thái mới nhất.
3. Chờ có giới hạn đến khi trạng thái là `COMPLETED`, `FAILED`, `STOPPED` hoặc trạng thái terminal mong đợi.
4. Nếu hết timeout mà vẫn `STARTED`/`STOPPING`, fail test với thông tin trạng thái và StepExecution hiện tại.

Dùng `CountDownLatch`, test listener hoặc thư viện chờ như Awaitility để đồng bộ theo sự kiện. Tránh `Thread.sleep` dài tùy ý vì test sẽ chậm và dễ flaky.

## 18. Kiểm thử process bị kill khác với kiểm thử Job thất bại

Một test làm Tasklet ném exception kiểm tra đường kết thúc `FAILED` bình thường. Nó không mô phỏng process bị kill, vì Spring Batch vẫn có cơ hội bắt exception và cập nhật metadata.

Nếu cần kiểm thử crash recovery, phải chạy Job trong một process có thể chấm dứt độc lập, kill process tại một điểm được kiểm soát, rồi khởi động lại ứng dụng với cùng JobRepository và JobParameters. Sau đó kiểm tra:

- Metadata execution cũ có stale `STARTED` hay không.
- Quy trình recovery có đưa execution về trạng thái restartable không.
- Checkpoint cuối đã commit được khôi phục đúng không.
- Chunk đã commit không bị ghi lại ngoài ý muốn.
- Side effect bên ngoài không bị lặp hoặc có thể đối soát.
- JobExecution mới thuộc cùng JobInstance.

Đây là integration/system test có chi phí cao hơn test trạng thái thông thường. Không thể chứng minh bằng một unit test chỉ gọi `launchJob` rồi assert `FAILED`.

## 19. Những lỗi thường gặp khi kiểm thử trạng thái cuối

### Chỉ assert Job BatchStatus

Job có thể `COMPLETED` nhưng flow đi sai nhánh hoặc một Step tùy chọn không chạy. Kiểm tra thêm StepExecution, ExitStatus và danh sách Step đã thực thi.

### Chỉ assert ExitStatus

Exit code tùy chỉnh không nói đầy đủ về vòng đời. Kiểm tra cả BatchStatus để phân biệt `COMPLETED`, `FAILED` và `STOPPED`.

### Dùng cùng JobParameters cho nhiều test độc lập

JobInstance cũ có thể đã hoàn tất và ngăn launch tiếp. Dùng identifying parameter riêng cho test độc lập; giữ nguyên tham số cho test restart.

### Giả định launchJob luôn đồng bộ

Với asynchronous JobLauncher, execution có thể vẫn `STARTED`. Chờ terminal state và đọc lại metadata.

### Không kiểm tra failure exception

Job `FAILED` có thể do lỗi khác với lỗi test mong đợi. Kiểm tra exception type hoặc mã lỗi ổn định.

### Dùng Step test để kết luận Job flow đúng

`launchStep` không kiểm tra toàn bộ transition của Job. Dùng `launchJob` cho test flow, bypass, stop và final Job status.

### Xóa metadata trên repository dùng chung

Cleanup có thể ảnh hưởng test khác hoặc dữ liệu vận hành. Dùng repository/database test cô lập.

### Xem exception đã ném là bằng chứng Job thất bại

Exception có thể được retry hoặc skip. Assert trạng thái và bộ đếm cuối cùng, không chỉ verify mock đã ném exception.

### Dùng test thông thường để tuyên bố đã kiểm thử process kill

Exception test không tương đương SIGKILL. Crash recovery cần process boundary và JobRepository bền vững.

## 20. Ma trận kiểm thử trạng thái cuối

Một bộ test trạng thái cơ bản có thể bao gồm:

| Kịch bản | Job BatchStatus | Job ExitStatus | Kiểm tra bổ sung |
|---|---|---|---|
| Tất cả Step hoàn tất | `COMPLETED` | `COMPLETED` hoặc mã flow đã định nghĩa | Các Step mong đợi đều có StepExecution. |
| Exception không được xử lý | `FAILED` | `FAILED` | Failure exception và Step thất bại. |
| Nhánh chờ phê duyệt | `STOPPED` | `STOPPED` | Step sau điểm dừng chưa chạy; có thể restart nếu đủ điều kiện. |
| Step trả `NO_DATA` rồi kết thúc thành công | `COMPLETED` | Theo flow cuối | Step có `ExitStatus.NO_DATA`; Step import bị bypass. |
| Có item skip trong giới hạn | Thường `COMPLETED` | Theo flow | Skip count và SkipListener đúng. |
| Vượt skip limit | `FAILED` | `FAILED` | Skip count vượt ngưỡng và failure exception phù hợp. |
| Retry thành công | Thường `COMPLETED` | Theo flow | Retry count/callback đúng; không tạo output trùng. |
| Restart sau execution thất bại | `COMPLETED` sau lần chạy mới nếu phục hồi thành công | Theo flow | Cùng JobInstance, JobExecution ID mới. |

Đây là ma trận định hướng. Job có thể đặt ExitStatus tùy chỉnh ở cấp Step hoặc Job, nên test cần assert mã kết quả đúng theo flow thực tế thay vì luôn giả định ExitStatus phải bằng tên BatchStatus.

## 21. Quy trình viết test cho trạng thái cuối

Khi bổ sung test cho một Job, có thể thực hiện theo trình tự:

1. Xác định các trạng thái cuối hợp lệ của Job: `COMPLETED`, `FAILED`, `STOPPED` hoặc trường hợp vận hành đặc biệt.
2. Liệt kê các ExitStatus tùy chỉnh mà flow sử dụng để rẽ nhánh.
3. Chuẩn bị test fixture xác định cho success, failure, skip, retry và stop.
4. Dùng `@SpringBatchTest` và `JobLauncherTestUtils` để launch Job.
5. Tạo JobParameters riêng cho test độc lập; giữ nguyên parameters khi test restart.
6. Assert cả `JobExecution.getStatus()` và `getExitStatus().getExitCode()`.
7. Tìm StepExecution quan trọng và assert status, exit code, counters, failure exceptions.
8. Kiểm tra Step được chạy hoặc bị bypass theo flow.
9. Nếu launcher asynchronous, chờ terminal state và đọc lại bằng JobExplorer.
10. Dọn metadata chỉ trên repository test cô lập.
11. Với crash recovery, chạy test process riêng và mô phỏng kill thực tế.

## Kết luận

Kiểm thử trạng thái cuối trong Spring Batch cần xác nhận cả `BatchStatus` và `ExitStatus` của Job/Step, đồng thời kiểm tra các Step đã chạy, nhánh flow, failure exception và counters liên quan. `@SpringBatchTest` cùng `JobLauncherTestUtils` phù hợp để launch Job/Step trong integration test; `JobRepositoryTestUtils` hỗ trợ dọn metadata trong repository test cô lập. Hãy dùng JobParameters riêng cho các test độc lập, giữ nguyên identifying parameters khi kiểm tra restart và chờ trạng thái terminal nếu JobLauncher chạy bất đồng bộ. Một test ném exception không thay thế kiểm thử process kill; crash recovery cần mô phỏng process boundary, JobRepository bền vững, checkpoint và side effect thực tế.
