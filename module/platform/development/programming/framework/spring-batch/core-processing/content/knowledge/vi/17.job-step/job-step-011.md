# Kiểm thử parent và child job

Trong Spring Batch, một job có thể khởi chạy một job khác như một bước trong flow bằng `JobStep`. Job điều phối bên ngoài thường được gọi là **parent job**, còn job được khởi chạy bên trong là **child job**. Cấu trúc này hữu ích khi một quy trình lớn cần được chia thành các job con có trách nhiệm riêng, có thể tái sử dụng hoặc có vòng đời vận hành độc lập.

Khi kiểm thử mô hình parent/child, cần xác nhận cả hai cấp độ: child job có xử lý đúng khi chạy độc lập hay không, và parent job có truyền đúng tham số, khởi chạy child, nhận trạng thái kết quả và điều khiển flow đúng hay không. Chỉ kiểm tra parent job kết thúc `COMPLETED` là chưa đủ; cần quan sát cả `JobExecution` của child và `StepExecution` đại diện cho `JobStep` trong parent.

Spring Batch Test cung cấp `@SpringBatchTest`, `JobLauncherTestUtils` và `JobRepositoryTestUtils` để hỗ trợ kiểm thử. `JobExplorer` giúp truy vấn metadata đã được lưu, bao gồm các execution của child job. Các test nên dùng repository và transaction manager tương tự cấu hình ứng dụng để kiểm tra đúng hành vi orchestration và restart.

## Parent job, child job và JobStep

`JobStep` là một step của parent job có nhiệm vụ khởi chạy một child `Job` thông qua `JobLauncher`. Nó dùng `JobParametersExtractor` để tạo bộ `JobParameters` cho child từ thông tin của parent execution và step execution.

Ví dụ flow:

```text
parentJob
    |
    v
validateInputStep
    |
    v
runChildJobStep --------------+
    |                          |
    | JobLauncher              v
    +--------------------> childJob
                              |
                              +--> childExtractStep
                              |
                              +--> childProcessStep
                              |
                              +--> childFinalizeStep
    |
    v
parentSummaryStep
    |
    v
parentJob hoàn tất
```

Các đối tượng execution ở hai cấp có vai trò khác nhau:

| Đối tượng | Thuộc job nào? | Vai trò |
| --- | --- | --- |
| Parent `JobExecution` | Parent job | Theo dõi lần chạy toàn bộ quy trình bên ngoài |
| Parent `StepExecution` của `JobStep` | Parent job | Theo dõi step có nhiệm vụ khởi chạy child job |
| Child `JobExecution` | Child job | Theo dõi lần chạy thực tế của job con |
| Child `StepExecution` | Child job | Theo dõi từng step bên trong child job |

Parent và child thường dùng chung `JobRepository` để metadata của cả hai job được quản lý trong một hệ thống repository. Child vẫn có `JobInstance`, `JobExecution`, parameters và step executions riêng. Parent `JobStep` không biến các step bên trong child thành step của parent.

## Cấu hình JobStep

Trong Spring Batch 5, `JobStepBuilder` được tạo từ một `StepBuilder` và nhận child job, launcher cùng parameter extractor.

```java
@Bean
Step runChildJobStep(
        JobRepository jobRepository,
        JobLauncher jobLauncher,
        @Qualifier("childJob") Job childJob,
        JobParametersExtractor childParametersExtractor) {

    return new JobStepBuilder(
            new StepBuilder("runChildJobStep", jobRepository))
            .job(childJob)
            .launcher(jobLauncher)
            .parametersExtractor(childParametersExtractor)
            .build();
}
```

`JobParametersExtractor` quyết định những parameter nào được chuyển sang child. Đây là một hợp đồng quan trọng cần được kiểm thử, vì thay đổi identifying parameter có thể làm child job tạo `JobInstance` khác, không thể restart cùng instance hoặc vô tình đụng vào một child execution đã hoàn thành.

Ví dụ extractor tùy chỉnh truyền ngày nghiệp vụ cùng định danh ổn định của parent instance:

```java
@Bean
JobParametersExtractor childParametersExtractor() {
    return (parentJobExecution, parentStepExecution) ->
            new JobParametersBuilder()
                    .addString(
                            "businessDate",
                            parentJobExecution.getJobParameters()
                                    .getString("businessDate"),
                            true)
                    .addString(
                            "parentJobName",
                            parentJobExecution.getJobInstance().getJobName(),
                            true)
                    .addLong(
                            "parentInstanceId",
                            parentJobExecution.getJobInstance().getInstanceId(),
                            true)
                    .toJobParameters();
}
```

Trong ví dụ, `businessDate`, `parentJobName` và `parentInstanceId` tạo ra danh tính child instance gắn với một parent logical instance. `parentInstanceId` ổn định khi parent được restart vì restart tạo execution mới cho cùng `JobInstance`. Tùy nghiệp vụ, có thể dùng một business key ổn định khác. Không nên đưa timestamp hoặc parent execution ID mới vào identifying parameters nếu mục tiêu là restart cùng child instance.

API cụ thể của builder và extractor cần tương thích với phiên bản Spring Batch dự án đang dùng. Với cấu hình khác, có thể sử dụng `DefaultJobParametersExtractor`; điều quan trọng khi kiểm thử là xác nhận chính xác kết quả extractor thực tế.

## Cấu trúc test cần có

Nên chia kiểm thử thành các nhóm để mỗi test trả lời một câu hỏi rõ ràng:

| Nhóm kiểm thử | Điều cần xác nhận |
| --- | --- |
| Child job độc lập | Các step con xử lý đúng input, business data, trạng thái và lỗi |
| Parameter extractor | Child nhận đúng tên, giá trị, kiểu và identifying flag |
| Parent orchestration | Parent `JobStep` thực sự khởi chạy child và chờ kết quả phù hợp |
| Status propagation | Kết quả child ảnh hưởng đúng trạng thái step và flow của parent |
| Restart | Child có thể restart với identifying parameters ổn định sau lỗi |
| Isolation/cleanup | Metadata của test này không làm ảnh hưởng test khác |

Unit test phù hợp cho logic thuần như parameter extractor hoặc mapper. Integration test với Spring context và `JobRepository` phù hợp để kiểm tra `JobStep`, metadata, transaction và restart. Không nên chỉ mock `JobLauncher` trong toàn bộ test suite vì như vậy không kiểm tra được child execution thực tế và cách repository lưu trạng thái.

## Chuẩn bị test với Spring Batch Test

`@SpringBatchTest` đăng ký các tiện ích kiểm thử Spring Batch, thường bao gồm `JobLauncherTestUtils` và `JobRepositoryTestUtils`, cùng các scope hỗ trợ test. Có thể kết hợp với `@SpringBootTest` để nạp cấu hình ứng dụng.

Ví dụ khung integration test:

```java
@SpringBootTest
@SpringBatchTest
class ParentChildJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("parentJob")
    private Job parentJob;

    @Autowired
    private JobExplorer jobExplorer;

    @BeforeEach
    void selectParentJob() {
        jobLauncherTestUtils.setJob(parentJob);
    }
}
```

`JobLauncherTestUtils` cần biết job nào là job được test. Khi application context có nhiều bean kiểu `Job`, hãy chỉ định rõ parent job trước khi gọi `launchJob`. Nếu test child độc lập bằng cùng tiện ích, có thể đặt child job cho test đó hoặc dùng `JobLauncher` trực tiếp.

Với nhiều job bean, tránh dựa vào việc Spring tự chọn một bean `Job` duy nhất. Dùng `@Qualifier` để inject đúng job, đúng step và đúng launcher cần kiểm thử.

### Test database và metadata

Integration test nên dùng database test phù hợp với schema Spring Batch. Có thể dùng database embedded cho test đơn giản nếu SQL nghiệp vụ tương thích; với job phụ thuộc cú pháp database cụ thể, Testcontainers hoặc database test cùng hệ quản trị thường phản ánh production chính xác hơn.

`JobRepositoryTestUtils` hỗ trợ dọn batch metadata do test tạo ra. Cần dùng cleanup có kiểm soát sau khi test hoàn tất, đặc biệt nếu các test dùng chung database. Không xóa metadata của job đang được test hoặc của execution do môi trường khác tạo ra.

## Kiểm thử child job độc lập

Trước khi kiểm thử parent orchestration, nên kiểm thử child job như một job bình thường. Mục tiêu là chứng minh child job có thể chạy đúng với bộ parameter mà nó yêu cầu, không phụ thuộc vào parent đang gọi nó.

Ví dụ dùng `JobLauncher` trực tiếp:

```java
@SpringBootTest
@SpringBatchTest
class ChildJobIntegrationTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    @Qualifier("childJob")
    private Job childJob;

    @Test
    void childJobCompletesForValidParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .addString("parentJobName", "parentJob", true)
                .addLong("parentInstanceId", 1001L, true)
                .toJobParameters();

        JobExecution execution = jobLauncher.run(childJob, parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals("childJob", execution.getJobInstance().getJobName());
        assertEquals(
                "2026-11-15",
                execution.getJobParameters().getString("businessDate"));
    }
}
```

Các giá trị parent trong ví dụ là parameter test minh họa. Trong test parent-child thật, extractor sẽ tạo chúng từ parent execution. Test độc lập giúp tách lỗi bên trong child job khỏi lỗi truyền parameter hoặc điều phối ở parent.

Các trường hợp nên kiểm tra ở child job:

- Parameter bắt buộc có mặt và có kiểu đúng.
- Parameter không hợp lệ làm child thất bại theo validation mong muốn.
- Business data được ghi đúng và không bị trùng khi chạy lại theo quy tắc nghiệp vụ.
- Các step trong child có trạng thái và exit status mong đợi.
- Child job có thể restart sau khi một step thất bại nếu thiết kế cho phép.
- Child job không phụ thuộc vào object hoặc thread context chỉ tồn tại trong parent.

## Kiểm thử parameter extractor

Extractor là nơi xác định child job sẽ chạy với danh tính nào. Nên kiểm thử độc lập mapping giữa parent execution, parent step execution và child parameters.

Ví dụ kiểm tra kết quả extractor:

```java
@Test
void extractsStableChildParameters() {
    JobParameters parentParameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .addString("requestedBy", "test-user", false)
            .toJobParameters();

    JobInstance parentInstance = new JobInstance(42L, "parentJob");
    JobExecution parentExecution =
            new JobExecution(parentInstance, parentParameters);
    StepExecution parentStepExecution =
            new StepExecution("runChildJobStep", parentExecution);

    JobParametersExtractor extractor = childParametersExtractor();
    JobParameters childParameters =
            extractor.getJobParameters(parentExecution, parentStepExecution);

    assertEquals(
            "2026-11-15",
            childParameters.getString("businessDate"));
    assertEquals("parentJob", childParameters.getString("parentJobName"));
    assertEquals(42L, childParameters.getLong("parentInstanceId"));
}
```

Đây là unit test minh họa cho extractor được định nghĩa ở trên. Constructor của `JobInstance`/`JobExecution` có thể khác theo API phiên bản đang dùng; nếu cần tạo execution test đầy đủ, có thể dùng factory hoặc repository test thay vì tự dựng object.

Ngoài giá trị, cần kiểm tra identifying flag:

```java
JobParameter<?> dateParameter =
        childParameters.getParameters().get("businessDate");

assertTrue(dateParameter.isIdentifying());
```

Việc kiểm tra cờ identifying rất quan trọng. Nếu parameter cần giữ nguyên danh tính child instance lại bị đánh dấu non-identifying hoặc ngược lại, hành vi launch/restart có thể khác dự kiến dù giá trị hiển thị giống nhau.

## Kiểm thử parent job khởi chạy child job

Đây là integration test cốt lõi. Khởi chạy parent bằng `JobLauncherTestUtils`, sau đó xác nhận parent hoàn thành và child job có execution tương ứng trong `JobRepository`.

```java
@Test
void parentLaunchesChildJobAndCompletes() throws Exception {
    JobParameters parentParameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .addString("testRunId", UUID.randomUUID().toString(), true)
            .toJobParameters();

    JobExecution parentExecution =
            jobLauncherTestUtils.launchJob(parentParameters);

    assertEquals(BatchStatus.COMPLETED, parentExecution.getStatus());

    StepExecution jobStepExecution = parentExecution.getStepExecutions()
            .stream()
            .filter(step -> step.getStepName().equals("runChildJobStep"))
            .findFirst()
            .orElseThrow();

    assertEquals(BatchStatus.COMPLETED, jobStepExecution.getStatus());
}
```

Đoạn test xác nhận parent step có trạng thái hoàn tất. Để xác nhận child thực sự chạy, cần truy vấn `JobExplorer` và tìm child execution theo tên job cùng các identifying parameters do extractor tạo.

```java
List<JobExecution> findChildExecutions(
        JobExplorer jobExplorer,
        String businessDate,
        String parentJobName,
        Long parentInstanceId) {

    return jobExplorer.findJobInstancesByName("childJob", 0, 100)
            .stream()
            .flatMap(instance -> jobExplorer.getJobExecutions(instance).stream())
            .filter(execution -> businessDate.equals(
                    execution.getJobParameters().getString("businessDate")))
            .filter(execution -> parentJobName.equals(
                    execution.getJobParameters().getString("parentJobName")))
            .filter(execution -> parentInstanceId.equals(
                    execution.getJobParameters().getLong("parentInstanceId")))
            .toList();
}
```

Sau khi parent chạy:

```java
List<JobExecution> childExecutions = findChildExecutions(
        jobExplorer,
        "2026-11-15",
        "parentJob",
        parentExecution.getJobInstance().getInstanceId());

assertEquals(1, childExecutions.size());
assertEquals(BatchStatus.COMPLETED, childExecutions.get(0).getStatus());
```

`findJobInstancesByName` trả về các instance theo tên child job; test lọc tiếp execution theo parameter để tránh nhầm execution từ test khác. Trong suite lớn, có thể giới hạn khoảng truy vấn, dùng một test database riêng hoặc cleanup metadata sau mỗi test.

## Xác nhận parent nhận trạng thái child

`JobStep` dùng kết quả child execution để xác định trạng thái của step trong parent. Vì vậy, nên kiểm tra ít nhất ba lớp:

1. `JobExecution` của child có trạng thái và exit status đúng.
2. `StepExecution` tương ứng với `JobStep` trong parent phản ánh kết quả child.
3. Flow của parent đi tới step tiếp theo, nhánh lỗi hoặc trạng thái kết thúc theo cấu hình.

Không nên chỉ assert `parentExecution.getStatus() == COMPLETED` nếu job có transition tùy chỉnh. Một child có thể kết thúc với custom exit code và parent điều hướng sang nhánh khác mà vẫn có kết quả tổng thể hợp lệ theo thiết kế.

Nếu parent flow dùng `on("FAILED").to(recoveryStep)` hoặc custom `ExitStatus`, test cần xác nhận step nào được thực thi và step nào bị bỏ qua. Có thể đọc danh sách `StepExecution` từ parent execution để kiểm tra.

## Kiểm thử child job thất bại

Một tình huống quan trọng là child job thất bại trong một step. Parent cần nhận kết quả thất bại từ `JobStep` và áp dụng flow đã khai báo.

Ví dụ cấu hình parent điều hướng khi child step thất bại:

```java
@Bean
Job parentJob(
        JobRepository jobRepository,
        Step runChildJobStep,
        Step recoveryStep,
        Step summaryStep) {

    return new JobBuilder("parentJob", jobRepository)
            .start(runChildJobStep)
                .on("FAILED").to(recoveryStep)
            .from(runChildJobStep)
                .on("*").to(summaryStep)
            .from(recoveryStep)
                .on("*").to(summaryStep)
            .end()
            .build();
}
```

Test nên tạo dữ liệu khiến child thất bại theo cách xác định, ví dụ một parameter không hợp lệ hoặc một test double của service nghiệp vụ ném exception. Sau đó xác nhận:

- Child `JobExecution` ở trạng thái `FAILED`.
- Parent `StepExecution` của `runChildJobStep` có kết quả lỗi phù hợp.
- Parent đi tới `recoveryStep` nếu transition đã cấu hình như ví dụ.
- `summaryStep` chạy hoặc không chạy theo flow thực tế.
- Business data đã commit trước lỗi vẫn được giữ nếu nó nằm trong các chunk transaction trước đó.

Không nên giả định toàn bộ dữ liệu child tự rollback khi child job thất bại. Các chunk đã commit trước đó vẫn có thể tồn tại; test cần xác nhận trạng thái business data thực tế.

## Kiểm thử parameter được truyền sang child

Parent và child có thể có bộ parameter khác nhau. Parent không nhất thiết chuyển toàn bộ parameter sang child; extractor quyết định chính xác giá trị nào được chuyển.

Ví dụ parent nhận:

```text
businessDate = 2026-11-15       identifying
requestedBy  = test-user        non-identifying
testRunId    = 8c...            identifying (chỉ để cô lập test)
```

Child có thể chỉ nhận:

```text
businessDate    = 2026-11-15    identifying
parentJobName   = parentJob     identifying
parentInstanceId = 42           identifying
```

Test nên xác nhận:

- Parameter bắt buộc của child có mặt.
- Giá trị được map đúng từ parent hoặc step context.
- Kiểu dữ liệu được giữ đúng.
- Identifying flag đúng với ý nghĩa nghiệp vụ.
- Parameter không được phép truyền không xuất hiện trong child.
- Giá trị mặc định hoặc optional parameter được xử lý rõ ràng.

Không nên chỉ kiểm tra child có chạy hay không. Child có thể chạy thành công với bộ parameter sai nhưng vẫn xử lý nhầm phạm vi dữ liệu.

## Kiểm thử restart của child job

Restart là phần quan trọng của parent/child orchestration. Khi child job thất bại, parent có thể được restart để `JobStep` khởi chạy lại child. Để child tiếp tục cùng logical instance, extractor phải tạo cùng identifying parameters như lần chạy trước.

Ví dụ chiến lược parameter:

- `businessDate`: identifying và ổn định.
- `parentJobName`: identifying và ổn định.
- `parentInstanceId`: identifying, giữ nguyên qua các lần restart của cùng parent `JobInstance`.
- `parentExecutionId`: nếu cần lưu để truy vết thì nên là non-identifying; không dùng ID execution mới làm danh tính child khi muốn restart cùng child instance.

Test restart có thể theo trình tự:

1. Chạy parent với bộ identifying parameters xác định.
2. Cho child hoàn thành một số step rồi thất bại ở step sau.
3. Xác nhận child execution đầu tiên là `FAILED` và metadata/checkpoint được lưu.
4. Restart parent với cùng identifying parameters.
5. Xác nhận extractor tạo cùng identifying parameters cho child.
6. Xác nhận child được restart theo quy tắc của `JobRepository`, tiếp tục từ checkpoint hợp lệ và hoàn tất.
7. Đối chiếu business data để chắc chắn các chunk đã commit không bị ghi trùng.

Nếu mỗi lần restart extractor thêm timestamp identifying mới, child sẽ được xem là một `JobInstance` mới. Khi đó, child có thể chạy lại từ đầu thay vì restart execution đã thất bại.

### Restart khi child đã hoàn thành nhưng parent thất bại sau đó

Một tình huống khác: child đã `COMPLETED`, nhưng parent thất bại ở `parentSummaryStep`. Khi restart parent, flow restart có thể bỏ qua `JobStep` đã hoàn thành và tiếp tục từ step lỗi theo metadata của parent. Nếu parent được cấu hình để chạy lại `JobStep`, child đã hoàn thành với cùng identifying parameters có thể bị từ chối vì `JobInstance` đã hoàn tất.

Test cần phản ánh flow restart thật của ứng dụng. Không nên thêm parameter ngẫu nhiên để né `JobInstanceAlreadyCompleteException`; hãy xác định liệu child có cần chạy lại hay parent chỉ cần tiếp tục step sau child.

## Kiểm thử child job độc lập và qua parent có mục đích khác nhau

Hai kiểu test không thay thế nhau:

| Test child độc lập | Test qua parent |
| --- | --- |
| Kiểm tra logic step của child | Kiểm tra parent gọi đúng child |
| Kiểm tra validator và parameter của child | Kiểm tra extractor map parameter đúng |
| Kiểm tra business data child | Kiểm tra parent/child metadata liên kết theo parameter |
| Kiểm tra restart child | Kiểm tra restart của parent kích hoạt child đúng cách |
| Dễ cô lập lỗi trong child | Phát hiện lỗi wiring, flow và launcher |

Một suite integration tốt thường có cả hai: test nhỏ cho child logic và test parent-child end-to-end cho orchestration.

## Kiểm tra metadata bằng JobExplorer

`JobExplorer` là API đọc metadata Spring Batch. Trong test, nó giúp tìm child `JobInstance`, lấy danh sách `JobExecution` và kiểm tra `StepExecution` mà không cần truy vấn trực tiếp bảng `BATCH_*`.

Ví dụ:

```java
JobInstance childInstance = jobExplorer.findJobInstancesByName(
        "childJob", 0, 10).stream()
        .filter(instance -> jobExplorer.getJobExecutions(instance).stream()
                .anyMatch(execution ->
                        "2026-11-15".equals(execution.getJobParameters()
                                .getString("businessDate"))))
        .findFirst()
        .orElseThrow();

List<JobExecution> executions =
        jobExplorer.getJobExecutions(childInstance);

assertFalse(executions.isEmpty());
```

Trong test thực tế, nên lọc thêm `parentJobName` và `parentInstanceId` hoặc một correlation parameter ổn định để không lấy nhầm execution từ lần chạy khác.

Có thể dùng `JobRepository` để đọc hoặc cập nhật metadata trong một số test đặc thù, nhưng `JobExplorer` phù hợp hơn cho truy vấn quan sát. Không nên sửa trực tiếp các bảng `BATCH_*` bằng SQL để ép trạng thái trong test thông thường.

## Dùng JobLauncherTestUtils đúng cách

`JobLauncherTestUtils` cung cấp các phương thức như `launchJob(...)` và `launchStep(...)`. Với parent-child:

- Dùng `launchJob(parentParameters)` để chạy toàn bộ parent job.
- Dùng `launchStep(stepName, parameters)` khi muốn cô lập một step của job đã được gắn vào test utility.
- Đặt job mục tiêu bằng `setJob(...)` nếu application context có nhiều job.
- Dùng `JobExplorer` để tìm child execution sau khi parent `JobStep` hoàn tất.

Không nên dùng `launchStep("runChildJobStep")` để thay thế test parent flow nếu mục tiêu là xác nhận transition giữa nhiều step. `launchStep` tập trung vào một step; nó không chứng minh toàn bộ flow parent chạy đúng.

Nếu muốn chạy child trực tiếp, có thể dùng `JobLauncher.run(childJob, childParameters)` hoặc cấu hình một test utility riêng cho child. Hãy bảo đảm child job nhận đúng parameter mà extractor production sẽ tạo.

## Kiểm thử đồng bộ và bất đồng bộ

Với `JobStep`, launcher được dùng để khởi chạy child. Trong integration test thông thường, nên dùng `SyncTaskExecutor` hoặc launcher đồng bộ để lời gọi `JobStep` nhận được kết quả child sau khi child thực thi xong. Điều này làm cho assertion về child status và parent flow có tính xác định.

Nếu cấu hình launcher bất đồng bộ, `JobLauncher.run` có thể trả về khi child vẫn đang chạy. Khi đó, parent `JobStep` có thể quan sát trạng thái chưa hoàn tất nếu không có cơ chế chờ/điều phối phù hợp. Không nên chỉ đổi launcher sang async và giả định JobStep tự chờ child hoàn thành.

Nếu kiến trúc cần chạy child bất đồng bộ, hãy thiết kế một cơ chế orchestration rõ ràng, ví dụ parent ghi nhận yêu cầu, step tiếp theo poll trạng thái qua `JobExplorer` với timeout hoặc dùng một hệ thống điều phối riêng. Test cần kiểm tra cả trạng thái trung gian, timeout, child failure và việc parent không đánh dấu hoàn thành trước khi điều kiện nghiệp vụ được đáp ứng.

Đối với test đồng bộ, vẫn cần tránh dùng `Thread.sleep` để chờ job. Dùng launcher đồng bộ hoặc cơ chế await có timeout rõ ràng và điều kiện kết thúc quan sát được.

## Test isolation và JobParameters duy nhất

Spring Batch không cho phép khởi chạy lại cùng một `JobInstance` đã hoàn thành như một execution mới thông thường. Nếu nhiều test dùng cùng job name và identifying parameters, test sau có thể gặp `JobInstanceAlreadyCompleteException` hoặc `JobExecutionAlreadyRunningException`.

Các cách cô lập test:

- Dùng `testRunId` identifying riêng cho mỗi test nếu mục tiêu là tạo instance độc lập.
- Dùng ngày nghiệp vụ hoặc business key khác nhau khi điều đó phản ánh phạm vi dữ liệu test.
- Dùng database riêng cho mỗi test suite hoặc test container.
- Dọn batch metadata sau test bằng `JobRepositoryTestUtils` khi phù hợp.
- Dọn business data và dữ liệu staging tương ứng, không chỉ xóa metadata.

Không thêm parameter ngẫu nhiên vào test restart. Trong test restart, cần giữ nguyên identifying parameters giữa lần chạy đầu và lần restart để kiểm tra đúng cùng một `JobInstance`.

Ví dụ tạo parameter độc lập cho mỗi test:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("testRunId", UUID.randomUUID().toString(), true)
        .toJobParameters();
```

Trong test restart, tạo bộ parameter một lần rồi tái sử dụng chính bộ đó; không sinh UUID mới ở lần restart.

## Cleanup bằng JobRepositoryTestUtils

`JobRepositoryTestUtils` hỗ trợ dọn các job executions được tạo trong test. Có thể dùng trong `@AfterEach` hoặc `@AfterAll` tùy phạm vi database và cách tổ chức suite.

```java
@Autowired
private JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanBatchMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Cleanup metadata không tự động xóa business records, file, object storage hoặc message đã tạo bởi child job. Cần cleanup các resource đó theo cách riêng, với định danh test để không ảnh hưởng dữ liệu của test khác.

Nếu test chạy song song trên cùng repository, việc gọi `removeJobExecutions()` toàn cục có thể xóa metadata mà test khác đang sử dụng. Khi chạy song song, ưu tiên database/schema riêng hoặc cleanup theo phạm vi execution do test sở hữu.

## Kiểm thử dữ liệu nghiệp vụ của parent và child

Metadata cho biết job có chạy và kết thúc như thế nào, nhưng không chứng minh output nghiệp vụ chính xác. Mỗi test cần kiểm tra dữ liệu ở đúng ranh giới:

- Child job tạo đúng records, trạng thái hoặc file theo input.
- Parent step sau child nhận đúng kết quả hoặc tham chiếu được child công bố.
- Child failure không khiến parent summary xử lý dữ liệu chưa sẵn sàng.
- Các chunk đã commit trước khi child thất bại vẫn được phản ánh đúng.
- Restart không tạo duplicate hoặc bỏ sót business records.
- Nếu child phát message, kiểm tra event ID, payload và khả năng xử lý lặp của consumer/outbox.

Không nên chỉ assert `BatchStatus.COMPLETED`. Một job có thể hoàn thành nhưng writer ghi sai bảng, nhận sai business date hoặc xử lý sai số lượng bản ghi. Hãy assert cả metadata lẫn kết quả nghiệp vụ.

## Kiểm thử flow và ExitStatus

Parent có thể điều hướng dựa trên exit code của `JobStep`. Child có thể trả `COMPLETED`, `FAILED` hoặc custom `ExitStatus` tùy cấu hình step và listener.

Các test nên bao gồm:

| Kết quả child | Điều cần xác nhận ở parent |
| --- | --- |
| `COMPLETED` | Parent đi tới step tiếp theo thông thường |
| `FAILED` | Parent dừng hoặc đi tới recovery flow theo cấu hình |
| Custom exit code | Transition khớp pattern đã khai báo |
| Child bị từ chối do instance đang chạy/đã hoàn tất | Parent xử lý exception hoặc trạng thái theo hợp đồng vận hành |
| Parameter child không hợp lệ | Child không xử lý business data và parent nhận lỗi phù hợp |

Nếu dùng custom exit code, kiểm tra cả `BatchStatus` và `ExitStatus`. Hai giá trị có liên quan nhưng không đồng nghĩa; flow transition thường dựa vào exit code.

## Kiểm thử khi child đã chạy trước đó

Child job có thể được gọi bởi nhiều parent instance hoặc được chạy độc lập trước khi parent gọi. Khi child đã có metadata, kết quả lần launch mới phụ thuộc identifying parameters và trạng thái execution hiện có.

Các trường hợp nên kiểm thử:

- Child instance chưa tồn tại: child được tạo và chạy lần đầu.
- Child instance đang chạy: yêu cầu khởi chạy trùng được xử lý đúng.
- Child instance đã hoàn thành: parent có hành vi đã thiết kế khi gọi lại cùng parameters.
- Child instance thất bại: restart cùng identifying parameters được cho phép nếu job restartable.
- Child instance không restartable: parent nhận lỗi và flow xử lý rõ ràng.

Không nên thêm timestamp identifying tự động chỉ để tránh lỗi instance đã hoàn thành. Làm vậy có thể tạo child instance mới và xử lý lại dữ liệu nghiệp vụ. Nếu nghiệp vụ cần một lần chạy mới, hãy dùng parameter identifying có ý nghĩa như `reprocessVersion` hoặc `runSequence` và kiểm tra tác động dữ liệu.

## Test khi parent và child dùng chung JobRepository

Trong cấu hình thông dụng, parent và child cùng dùng một `JobRepository`. Điều này cho phép truy vấn metadata của cả hai job qua `JobExplorer` và hỗ trợ restart dựa trên lịch sử execution.

Integration test cần xác nhận:

- Parent và child được đăng ký trong cùng repository mà `JobStep` sử dụng.
- Child execution xuất hiện trong metadata sau khi parent chạy.
- Tên child job và parameters đúng.
- Step executions của child được lưu riêng.
- Parent step có trạng thái phản ánh kết quả child.
- Restart sử dụng lại metadata hiện có thay vì một repository test hoặc in-memory repository khác.

Nếu parent và child vô tình dùng repository khác nhau, parent có thể không quan sát được trạng thái child như mong đợi và việc restart trở nên khó điều phối. Hãy inject rõ `JobRepository`/launcher trong cấu hình nhiều datasource.

## Test với nhiều Job bean và nhiều test class

Một application context có thể chứa nhiều parent job, child job và job dùng cho mục đích khác. Điều này dễ tạo ambiguity khi inject `JobLauncherTestUtils` hoặc `Job`.

Các nguyên tắc:

- Dùng `@Qualifier` cho từng `Job` và `Step`.
- Gọi `jobLauncherTestUtils.setJob(parentJob)` trước khi launch parent.
- Nếu nhiều test class dùng cùng test utility singleton, tránh thay đổi job selection đồng thời.
- Với test chạy song song, dùng utility riêng hoặc gọi `JobLauncher` trực tiếp với job đã inject rõ.
- Giữ cấu hình test nhất quán để không có test phụ thuộc thứ tự chạy.

Không nên đặt tên parent và child giống nhau. Tên job được dùng trong metadata và khi truy vấn `JobExplorer`; tên riêng giúp test, vận hành và log dễ phân biệt.

## Chẩn đoán test thất bại

### Parent COMPLETED nhưng không tìm thấy child execution

Kiểm tra parent có thực sự chứa `JobStep` được test hay không, step có được gọi theo flow không, child job bean được inject đúng chưa và `JobStep` có dùng đúng `JobLauncher`/`JobRepository` không. Kiểm tra tên child job và cách truy vấn metadata.

### Child chạy nhưng nhận sai parameter

Kiểm tra `JobParametersExtractor`, tên key, kiểu dữ liệu và identifying flag. Có thể child dùng default extractor khác với extractor mà test giả định.

### Test thứ hai gặp JobInstanceAlreadyCompleteException

Hai test đang dùng cùng job name và identifying parameters, hoặc metadata chưa được cleanup. Dùng parameter test riêng cho test độc lập; giữ nguyên parameters trong test restart.

### Restart tạo child JobInstance mới

Extractor có thể thêm timestamp, UUID hoặc parent execution ID identifying mới mỗi lần. Chuyển sang business key hoặc parent instance ID ổn định nếu mục tiêu là restart cùng child instance.

### Parent step thất bại dù child đã chạy xong

Kiểm tra launcher có chạy bất đồng bộ không, trạng thái trả về tại thời điểm `JobLauncher.run` hoàn tất, exception từ child và cách `JobStep` chuyển exit status. Với orchestration đồng bộ thông thường, dùng launcher đồng bộ để parent nhận kết quả hoàn tất.

### Metadata test bị lẫn giữa các test

Kiểm tra database/schema có được dùng chung không, test có chạy song song không và cleanup có xóa đúng phạm vi không. Tạo test database riêng hoặc dùng correlation parameter ổn định để lọc execution.

### Child FAILED nhưng business data vẫn tồn tại

Đây có thể là hành vi đúng nếu các chunk trước đó đã commit. Kiểm tra từng `StepExecution`, checkpoint và business records thay vì giả định toàn bộ child job là một transaction duy nhất.

## Ma trận test tối thiểu

Một bộ integration test parent/child có thể bắt đầu với các trường hợp sau:

| Test case | Kết quả mong đợi |
| --- | --- |
| Child chạy độc lập với parameters hợp lệ | Child `COMPLETED`, output đúng |
| Child nhận thiếu parameter bắt buộc | Child thất bại trước khi ghi business data |
| Extractor map parameters từ parent | Child nhận đúng value, type và identifying flags |
| Parent gọi child qua `JobStep` | Có child `JobExecution`, parent `JobStep` hoàn tất |
| Child thất bại | Parent nhận trạng thái và đi đúng recovery flow |
| Restart child sau lỗi | Cùng identifying parameters, tiếp tục từ checkpoint hợp lệ |
| Parent restart sau khi child đã hoàn tất | Child không bị chạy lại ngoài ý muốn |
| Child instance đang chạy hoặc đã hoàn tất | Parent xử lý duplicate launch theo quy tắc |
| Nhiều test chạy cùng suite | Không lẫn metadata hoặc business data |
| Child có chunk đã commit trước lỗi | Dữ liệu đã commit được giữ và restart không tạo duplicate |

Không phải mọi dự án đều cần tất cả trường hợp ngay từ đầu, nhưng các tình huống parameter, status, restart và test isolation là những phần quan trọng của mô hình parent/child.

## Nguyên tắc thiết kế test

Khi viết test cho parent và child job, hãy làm rõ:

1. Child có thể chạy độc lập với bộ parameter xác định không?
2. Parent `JobStep` có gọi đúng child job không?
3. `JobParametersExtractor` tạo bộ parameter nào và cờ identifying ra sao?
4. Parent và child có dùng repository/launcher phù hợp không?
5. Child `JobExecution` có trạng thái, exit status và step executions đúng không?
6. Parent flow xử lý `COMPLETED`, `FAILED` và custom exit code như thế nào?
7. Restart có giữ nguyên child identifying parameters không?
8. Các chunk đã commit có được bảo toàn và writer có idempotent không?
9. Test có dùng parameter riêng và cleanup metadata/business data đúng phạm vi không?
10. Có kiểm tra kết quả nghiệp vụ ngoài trạng thái metadata không?

Với phần lớn ứng dụng, cách tiếp cận đáng tin cậy là kiểm thử child job độc lập để xác nhận logic, rồi chạy parent integration test với repository thật để xác nhận `JobStep`, parameter extraction, status propagation và restart. Dùng `JobExplorer` để quan sát child execution, giữ identifying parameters ổn định cho restart và cô lập dữ liệu test để các lần chạy không ảnh hưởng lẫn nhau.

## Ghi nhớ

Parent job dùng `JobStep` để khởi chạy child job thông qua `JobLauncher` và `JobParametersExtractor`. Child có `JobInstance`, `JobExecution` và step executions riêng; parent có `StepExecution` đại diện cho bước gọi child. Hãy kiểm thử child độc lập, kiểm thử extractor, rồi chạy integration test parent để xác nhận child execution thực sự được tạo, nhận đúng parameters và trả trạng thái phù hợp cho parent flow. Dùng `JobExplorer` để truy vấn metadata, kiểm tra cả business data, failure và restart. Identifying parameters của child phải ổn định qua restart; test độc lập cần parameters riêng, còn test restart phải tái sử dụng cùng bộ parameters. Với JobStep đồng bộ, dùng launcher đồng bộ trong test để kết quả dễ xác định và bảo đảm parent chỉ tiếp tục theo trạng thái child đã hoàn tất.
