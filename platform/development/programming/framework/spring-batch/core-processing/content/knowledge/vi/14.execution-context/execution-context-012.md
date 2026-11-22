# Kiểm tra state sau một lần chạy

Sau khi một job Spring Batch chạy xong, ứng dụng thường cần đọc lại trạng thái để biết job đã kết thúc ra sao, step nào đã chạy, checkpoint cuối cùng nằm ở đâu và những giá trị nào đã được lưu trong `ExecutionContext`. Việc kiểm tra này hữu ích cho kiểm thử, dashboard vận hành, đối soát và quyết định có cần restart hay không.

Spring Batch lưu metadata thực thi và execution context trong `JobRepository`. Sau khi có một `JobExecution`, ta có thể đọc `JobExecution.getExecutionContext()` để xem trạng thái ở phạm vi job, hoặc lấy từng `StepExecution` rồi đọc `StepExecution.getExecutionContext()` để xem trạng thái riêng của step. Khi cần đọc lại dữ liệu đã được lưu bền vững sau khi job hoàn tất, `JobExplorer` là API phù hợp vì nó truy vấn metadata từ repository.

Điều quan trọng là xác định đúng lần chạy cần kiểm tra. Một `JobInstance` có thể có nhiều `JobExecution` do restart hoặc các lần thực thi khác nhau theo cùng định danh nghiệp vụ. Hãy dùng `JobExecution` ID để truy vấn đúng execution, sau đó đọc context ở đúng phạm vi.

## 1. State sau một lần chạy gồm những gì?

Sau một lần chạy, có một số loại trạng thái thường cần kiểm tra:

- **Trạng thái job:** `BatchStatus`, `ExitStatus`, thời điểm bắt đầu/kết thúc, thời lượng và lỗi nếu có.
- **Trạng thái từng step:** step nào đã hoàn thành, thất bại hoặc bị dừng; step nào đã được thực thi trong job execution đó.
- **ExecutionContext của job:** các giá trị nhỏ được lưu để chia sẻ giữa các step trong cùng `JobExecution`.
- **ExecutionContext của step:** checkpoint và trạng thái nội bộ của từng `StepExecution`, ví dụ vị trí reader hoặc tiến độ tasklet.
- **Bộ đếm thực thi:** số item đọc, ghi, filter, skip, số lần commit và rollback.
- **Dữ liệu nghiệp vụ:** kết quả thực tế được ghi vào database, file hoặc hệ thống bên ngoài.

Các nhóm trên có liên quan nhưng không thay thế nhau. `ExecutionContext` lưu các giá trị key-value mà ứng dụng hoặc thành phần Spring Batch cần khôi phục. Các bộ đếm như `readCount` và `writeCount` là thuộc tính metadata của `StepExecution`. Dữ liệu hóa đơn, đơn hàng hoặc thanh toán vẫn nằm trong kho dữ liệu nghiệp vụ.

## 2. Phân biệt JobExecution, StepExecution và JobInstance

Trước khi đọc state, cần biết các đối tượng thực thi đại diện cho điều gì:

| Đối tượng | Ý nghĩa | Dùng khi kiểm tra |
|---|---|---|
| `JobInstance` | Một lần xử lý nghiệp vụ được nhận diện bởi tên job và identifying `JobParameters` | Nhóm các lần thực thi của cùng một batch |
| `JobExecution` | Một lần thực thi cụ thể của `JobInstance` | Đọc trạng thái và Job ExecutionContext của một lần chạy |
| `StepExecution` | Một lần thực thi cụ thể của step trong một `JobExecution` | Đọc trạng thái, bộ đếm và Step ExecutionContext của step |

Ví dụ, một job nhập file có thể chạy lần đầu và thất bại ở step thứ hai. Khi restart, Spring Batch tạo một `JobExecution` mới cho cùng `JobInstance`. Mỗi execution có ID riêng và lịch sử trạng thái riêng. Vì vậy, nếu cần kiểm tra lần restart vừa hoàn thành, hãy dùng ID của execution đó thay vì chỉ tra cứu theo tên job hoặc `JobInstance`.

## 3. Đọc state trực tiếp từ JobExecution sau khi chạy đồng bộ

Khi `JobLauncher` chạy đồng bộ, lời gọi `run()` chỉ trả về sau khi job kết thúc. Có thể đọc trạng thái từ đối tượng `JobExecution` trả về:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, jobParameters);

BatchStatus status = execution.getStatus();
ExitStatus exitStatus = execution.getExitStatus();
Long executionId = execution.getId();

log.info("Job execution {} finished with status {} and exit code {}",
        executionId,
        status,
        exitStatus.getExitCode());
```

Đối tượng này cho biết kết quả của lần thực thi vừa được khởi chạy. Ta cũng có thể đọc Job ExecutionContext và các StepExecution đã gắn với execution:

```java
ExecutionContext jobContext = execution.getExecutionContext();

if (jobContext.containsKey("summary.reference")) {
    String summaryReference =
            jobContext.getString("summary.reference");
    log.info("Summary reference: {}", summaryReference);
}

for (StepExecution stepExecution : execution.getStepExecutions()) {
    log.info("Step {}: status={}, read={}, write={}, commits={}, rollbacks={}",
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount());
}
```

Đây là cách thuận tiện khi job được gọi đồng bộ trong test hoặc một tiến trình điều phối. Nếu ứng dụng cần kiểm tra trạng thái đã lưu trong repository sau khi job kết thúc, nên tải lại execution bằng `JobExplorer`.

## 4. Đọc lại state đã lưu bằng JobExplorer

`JobExplorer` cung cấp API chỉ đọc để tra cứu job instance, job execution và step execution từ `JobRepository`. Nó phù hợp với dashboard vận hành, API trạng thái và kiểm tra sau khi job đã chạy.

Ví dụ service nhận `executionId` và tải lại execution:

```java
@Service
public class BatchStateReader {

    private final JobExplorer jobExplorer;

    public BatchStateReader(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution loadExecution(Long executionId) {
        JobExecution execution =
                jobExplorer.getJobExecution(executionId);

        if (execution == null) {
            throw new NoSuchElementException(
                    "Job execution not found: " + executionId);
        }

        return execution;
    }
}
```

Sau đó có thể đọc context:

```java
JobExecution storedExecution =
        batchStateReader.loadExecution(executionId);

ExecutionContext jobContext = storedExecution.getExecutionContext();

if (jobContext.containsKey("summary.reference")) {
    String reference = jobContext.getString("summary.reference");
}

for (StepExecution stepExecution : storedExecution.getStepExecutions()) {
    ExecutionContext stepContext = stepExecution.getExecutionContext();

    if (stepContext.containsKey("orders.lastProcessedId")) {
        long lastId = stepContext.getLong("orders.lastProcessedId");
    }
}
```

`JobExplorer` giúp đọc lại dữ liệu metadata đã lưu, kể cả khi đối tượng `JobExecution` ban đầu không còn trong bộ nhớ của request hoặc ứng dụng đã được khởi động lại. Nó là API tra cứu; không nên sửa context đã tải qua `JobExplorer` rồi mong repository tự lưu thay đổi đó.

## 5. Đọc Job ExecutionContext và Step ExecutionContext đúng phạm vi

Hai context có mục đích khác nhau:

| Context | API truy cập | Dữ liệu thường gặp |
|---|---|---|
| Job ExecutionContext | `jobExecution.getExecutionContext()` | Tham chiếu báo cáo, mã artifact, kết quả nhỏ cần chia sẻ giữa các step |
| Step ExecutionContext | `stepExecution.getExecutionContext()` | Offset file, trang tiếp theo, khóa cuối reader, trạng thái tasklet |

Ví dụ, `importOrdersStep` có thể lưu checkpoint:

```java
ExecutionContext stepContext =
        contribution.getStepExecution().getExecutionContext();

stepContext.putLong("orders.lastProcessedId", lastCommittedOrderId);
```

Sau khi job chạy, đọc giá trị từ đúng step execution:

```java
for (StepExecution stepExecution : storedExecution.getStepExecutions()) {
    if ("importOrdersStep".equals(stepExecution.getStepName())) {
        ExecutionContext context = stepExecution.getExecutionContext();

        if (context.containsKey("orders.lastProcessedId")) {
            long lastId = context.getLong("orders.lastProcessedId");
            log.info("Last checkpointed order ID: {}", lastId);
        }
    }
}
```

Không nên giả định các khóa trong Step ExecutionContext tự động xuất hiện trong Job ExecutionContext. Nếu step sau hoặc code sau job cần dùng một giá trị của step, hãy promotion khóa đó hoặc lưu một tham chiếu phù hợp trong Job ExecutionContext.

## 6. Ghi một giá trị có thể kiểm tra sau khi job chạy

Để kiểm tra context, trước hết cần biết giá trị được ghi vào đâu và vào thời điểm nào.

Ví dụ một tasklet lưu mã tham chiếu kết quả trong Step ExecutionContext:

```java
@Bean
Step createSummaryStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        SummaryService summaryService) {

    return new StepBuilder("createSummaryStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                String reference = summaryService.createSummary();

                contribution.getStepExecution()
                        .getExecutionContext()
                        .putString("summary.reference", reference);

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Sau khi step hoàn tất, giá trị được lưu trong Step ExecutionContext và có thể được đọc qua `StepExecution` của execution tương ứng.

Nếu cần giá trị đó ở cấp job, có thể dùng `ExecutionContextPromotionListener` để promotion khóa khi step hoàn tất:

```java
@Bean
ExecutionContextPromotionListener promoteSummaryReference() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[] {"summary.reference"});
    return listener;
}
```

Đăng ký listener với step tạo giá trị:

```java
return new StepBuilder("createSummaryStep", jobRepository)
        .tasklet(createSummaryTasklet, transactionManager)
        .listener(promoteSummaryReference)
        .build();
```

Khi step hoàn tất theo trạng thái mà listener chấp nhận, khóa được promotion lên Job ExecutionContext. Sau khi job chạy, có thể đọc bằng:

```java
String reference = storedExecution.getExecutionContext()
        .getString("summary.reference");
```

Promotion listener thường chỉ promotion khi trạng thái step khớp các exit status được cấu hình (mặc định là `COMPLETED`). Nếu step thất bại, không nên giả định khóa đã được đưa lên job context. Hãy đọc Step ExecutionContext để xem trạng thái đã lưu của chính step đó.

## 7. Đọc state sau job bất đồng bộ

Nếu `JobLauncher` dùng executor bất đồng bộ, `run()` có thể trả về ngay khi job mới được gửi đi hoặc đang bắt đầu. Khi đó, `JobExecution` trả về chưa chắc chứa trạng thái cuối cùng.

Không nên làm như sau:

```java
JobExecution execution = jobLauncher.run(job, parameters);
// Không giả định execution đã COMPLETED nếu launcher chạy async.
return execution.getExecutionContext();
```

Thay vào đó, lấy `executionId` từ response và tra cứu lại qua `JobExplorer` sau khi job hoàn tất. API trạng thái có thể trả `STARTING` hoặc `STARTED` trong lúc job đang chạy, rồi trả trạng thái cuối như `COMPLETED`, `FAILED` hoặc `STOPPED`.

Một cách tổ chức thường dùng:

1. API nhận yêu cầu và khởi chạy job bất đồng bộ.
2. API trả `202 Accepted` cùng `executionId`.
3. Client truy vấn endpoint trạng thái bằng ID đó.
4. Endpoint dùng `JobExplorer` đọc trạng thái mới nhất.
5. Khi execution đã kết thúc, endpoint có thể trả thêm các giá trị context được phép công khai.

Nếu cần polling nội bộ, hãy dùng khoảng chờ và timeout có giới hạn hoặc cơ chế thông báo sự kiện. Không lặp truy vấn liên tục không có giới hạn. Khi đọc trạng thái cuối, nên tải lại execution từ repository thay vì dùng object cũ có thể đã lỗi thời.

## 8. Kiểm tra state trong listener

Nếu cần ghi log hoặc tạo một hành động sau khi step/job kết thúc trong cùng tiến trình, có thể dùng listener.

Ví dụ `StepExecutionListener`:

```java
@Component
public class ImportStepListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportStepListener.class);

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        ExecutionContext context = stepExecution.getExecutionContext();

        if (context.containsKey("orders.lastProcessedId")) {
            log.info("Step {} checkpoint={}",
                    stepExecution.getStepName(),
                    context.getLong("orders.lastProcessedId"));
        }

        return null;
    }
}
```

`afterStep()` hữu ích để quan sát trạng thái của step khi callback được gọi. Tuy nhiên, nếu cần xác nhận metadata đã được lưu bền vững và đọc từ một thành phần khác sau khi job kết thúc, hãy truy vấn lại bằng `JobExplorer`.

Tương tự, `JobExecutionListener.afterJob()` có thể quan sát `JobExecution` và Job ExecutionContext sau khi các step đã kết thúc. Listener phù hợp cho log, metric hoặc thông báo trong cùng tiến trình. Không nên dùng listener như một thay thế cho API tra cứu metadata từ repository.

## 9. Kiểm tra state trong test

Trong test tích hợp, `JobLauncherTestUtils` có thể khởi chạy job và trả về `JobExecution`. Sau khi job chạy đồng bộ, có thể kiểm tra status, step context và job context.

Ví dụ:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class ExecutionContextStateTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobExplorer jobExplorer;

    @Test
    void storesCheckpointAfterSuccessfulRun() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", "STATE-TEST-001")
                .toJobParameters();

        JobExecution launched =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, launched.getStatus());

        JobExecution stored =
                jobExplorer.getJobExecution(launched.getId());
        assertNotNull(stored);

        StepExecution importStep = stored.getStepExecutions()
                .stream()
                .filter(step -> step.getStepName().equals("importOrdersStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(BatchStatus.COMPLETED, importStep.getStatus());
        assertTrue(importStep.getExecutionContext()
                .containsKey("orders.lastProcessedId"));
    }
}
```

`BatchTestConfiguration` cần cung cấp job có step tên `importOrdersStep` và reader/tasklet ghi khóa context trong quá trình thực thi. Test nên dùng repository và datasource phù hợp với mục tiêu kiểm tra. Nếu chỉ kiểm tra việc đọc lại metadata đã lưu, hãy bảo đảm `JobExplorer` và `JobRepository` dùng cùng kho metadata.

Có thể kiểm tra giá trị cụ thể:

```java
long lastId = importStep.getExecutionContext()
        .getLong("orders.lastProcessedId");

assertEquals(8450L, lastId);
```

Không nên chỉ xác nhận khóa tồn tại nếu nghiệp vụ cần một giá trị cụ thể. Hãy kiểm tra giá trị và đối chiếu với dữ liệu thực tế được ghi bởi writer.

## 10. Kiểm tra state khi job thất bại

Một job thất bại vẫn có thể có state hữu ích. Ví dụ, step đã commit 10 chunk rồi thất bại ở chunk thứ 11. Step ExecutionContext có thể chứa checkpoint của chunk thứ 10; đó là trạng thái bền vững gần nhất, không nhất thiết là item cuối cùng mà reader từng đọc trong bộ nhớ.

Khi kiểm tra execution thất bại, nên xem:

- `JobExecution.getStatus()` và `getExitStatus()`.
- `StepExecution.getStatus()` và `getExitStatus()` của step lỗi.
- `StepExecution.getExecutionContext()` để xem checkpoint đã lưu.
- `rollbackCount`, `commitCount`, `readCount`, `writeCount` và các bộ đếm skip.
- `FailureExceptions` hoặc thông tin lỗi phù hợp để điều tra.
- Dữ liệu nghiệp vụ đã commit trước khi lỗi xảy ra.

Không suy luận rằng context rỗng có nghĩa job chưa làm gì. Một step có thể không lưu khóa tùy chỉnh, reader có thể dùng khóa nội bộ, hoặc execution có thể thất bại trước checkpoint đầu tiên. Ngược lại, context có giá trị không chứng minh tất cả dữ liệu tương ứng đã được commit nếu ứng dụng tự cập nhật trạng thái sai thời điểm.

## 11. Phân biệt context với các bộ đếm và trạng thái framework

Khi đọc state sau một lần chạy, không nên nhầm giá trị trong `ExecutionContext` với metadata có sẵn:

| Thông tin cần biết | Nơi đọc |
|---|---|
| Job hoàn thành hay thất bại | `JobExecution.getStatus()` |
| Mã kết thúc job | `JobExecution.getExitStatus()` |
| Step đã hoàn thành hay chưa | `StepExecution.getStatus()` |
| Số item reader đọc | `StepExecution.getReadCount()` |
| Số item writer ghi | `StepExecution.getWriteCount()` |
| Số lần commit/rollback | `StepExecution.getCommitCount()` / `getRollbackCount()` |
| Checkpoint reader hoặc trạng thái tùy chỉnh | `StepExecution.getExecutionContext()` |
| Giá trị chia sẻ giữa step | `JobExecution.getExecutionContext()` |
| Trạng thái hóa đơn/đơn hàng/thanh toán | Repository hoặc database nghiệp vụ |

Các bộ đếm do framework quản lý, không cần sao chép chúng vào context nếu không có mục đích nghiệp vụ cụ thể. Nếu cần hiển thị trạng thái của một đối tượng nghiệp vụ, hãy đọc mô hình dữ liệu nghiệp vụ thay vì suy ra từ `writeCount`.

## 12. Kiểm tra context có khóa hay không

Không nên giả định một key luôn tồn tại sau mỗi lần chạy. Giá trị có thể không được ghi nếu step đi theo nhánh khác, bị dừng trước checkpoint hoặc chưa thực hiện đoạn code tạo key.

Hãy dùng `containsKey()` trước khi đọc một khóa tùy chọn:

```java
ExecutionContext context = stepExecution.getExecutionContext();

if (context.containsKey("report.reference")) {
    String reference = context.getString("report.reference");
} else {
    log.info("Step did not produce a report reference");
}
```

Với khóa bắt buộc theo hợp đồng của step, có thể kiểm tra và báo lỗi rõ nếu thiếu. Tránh đọc một giá trị với default như `0` rồi mặc định coi đó là checkpoint hợp lệ; giá trị mặc định có thể che giấu việc step chưa ghi state.

Reader chuẩn có thể lưu các khóa nội bộ dựa trên tên reader. Không nên phụ thuộc vào tên key nội bộ nếu không có tài liệu API cam kết ổn định. Nếu ứng dụng cần một trạng thái để hiển thị hoặc đối soát, hãy lưu một khóa tùy chỉnh có tên rõ ràng và quản lý vòng đời của nó.

## 13. Đọc nhiều lần chạy của cùng JobInstance

Một `JobInstance` có thể có nhiều `JobExecution`, ví dụ lần chạy đầu thất bại và lần restart thành công. Khi cần xem lịch sử, dùng `JobExplorer` lấy instance rồi đọc các executions của instance đó:

```java
JobInstance instance = jobExplorer.getJobInstance(instanceId);
if (instance == null) {
    throw new NoSuchElementException("Job instance not found");
}

List<JobExecution> executions = jobExplorer.getJobExecutions(instance);

for (JobExecution execution : executions) {
    log.info("Execution {} status={} start={} end={}",
            execution.getId(),
            execution.getStatus(),
            execution.getStartTime(),
            execution.getEndTime());
}
```

Mỗi execution có Job ExecutionContext và StepExecution riêng của lần thực thi đó. Nếu cần xem checkpoint của lần thất bại, phải đọc đúng execution thất bại; nếu cần xem trạng thái lần restart, đọc execution mới hơn. Không gộp các context thành một trạng thái duy nhất nếu không có quy tắc nghiệp vụ rõ ràng.

## 14. Lưu ý với execution context đã serialize

ExecutionContext được lưu trong repository theo serializer được cấu hình. Các giá trị nên là kiểu dữ liệu nhỏ, có thể serialize và tương thích khi job được restart sau khi ứng dụng deploy phiên bản mới.

Khi đọc state sau một lần chạy:

- Chỉ đọc các key mà ứng dụng sở hữu hoặc key có hợp đồng rõ ràng.
- Tránh giả định object tùy chỉnh luôn có thể deserialize sau khi class thay đổi.
- Giữ tên key và kiểu dữ liệu ổn định trong thời gian các execution cũ còn cần restart.
- Không lưu mật khẩu, token hoặc secret trong context.
- Không đưa danh sách item lớn hoặc payload file vào metadata.
- Không ghi toàn bộ context ra log hoặc trả nguyên context cho API client.

Nếu context chứa một giá trị không thể deserialize do thay đổi phiên bản, việc tải execution có thể gặp lỗi. Với job dài và có thể restart qua nhiều lần deploy, cần quản lý tương thích schema/serializer và kiểu dữ liệu context.

## 15. JobExplorer là API đọc, không phải nơi sửa state

`JobExplorer` được thiết kế cho việc tra cứu metadata. Khi tải `JobExecution` hoặc `StepExecution`, không nên sửa context trên object vừa đọc rồi mong thay đổi được lưu xuống repository.

Nếu một step cần ghi trạng thái, hãy cập nhật context trong vòng đời thực thi của step, nơi Spring Batch có thể lưu nó tại checkpoint hoặc khi step hoàn tất. Nếu cần chia sẻ một giá trị, dùng Job ExecutionContext hoặc promotion listener. Nếu cần sửa dữ liệu nghiệp vụ sau job, hãy dùng service/repository nghiệp vụ và transaction phù hợp.

Không tự cập nhật trực tiếp các bảng `BATCH_JOB_EXECUTION_CONTEXT` hoặc `BATCH_STEP_EXECUTION_CONTEXT` bằng SQL. Những bảng này thuộc schema metadata do Spring Batch quản lý; sửa thủ công có thể làm sai trạng thái restart hoặc phá vỡ khả năng đọc metadata.

## 16. Bảo mật khi hiển thị state

ExecutionContext có thể chứa đường dẫn file, mã batch, tên artifact hoặc thông tin kỹ thuật khác. Dù context không nên chứa secret, vẫn cần kiểm soát việc hiển thị:

- Chỉ trả về các key được phép công khai thay vì serialize toàn bộ `ExecutionContext`.
- Kiểm tra quyền người gọi trước khi cho xem execution ID.
- Không hiển thị đường dẫn nội bộ, thông tin cá nhân hoặc nội dung exception nhạy cảm cho người dùng cuối.
- Không ghi token, mật khẩu hoặc payload nhạy cảm vào log.
- Tách API trạng thái vận hành khỏi API truy vấn dữ liệu nghiệp vụ khi quyền truy cập khác nhau.

Một DTO trạng thái có thể chỉ chứa `executionId`, `jobName`, `batchStatus`, thời điểm bắt đầu/kết thúc và một số trường tiến độ đã được chọn. Cách này giữ hợp đồng API ổn định ngay cả khi cấu trúc context nội bộ thay đổi.

## 17. Những lỗi thường gặp khi kiểm tra state

**Đọc Job ExecutionContext trong khi key nằm ở Step ExecutionContext.** Context không tự chia sẻ khóa giữa hai phạm vi. Hãy đọc đúng `StepExecution` hoặc promotion giá trị nếu cần chia sẻ.

**Dùng JobInstance ID thay cho JobExecution ID.** Hai ID đại diện cho hai loại đối tượng khác nhau. Khi truy vấn một lần chạy cụ thể, dùng execution ID.

**Đọc object cũ sau khi khởi chạy bất đồng bộ.** Object trả về từ `run()` có thể chưa có trạng thái cuối. Tải lại bằng `JobExplorer` sau khi execution kết thúc.

**Giả định mọi key đều tồn tại.** Step có thể không ghi key nếu nhánh xử lý không chạy hoặc thất bại trước checkpoint. Kiểm tra `containsKey()`.

**Coi context là bộ đếm item.** Dùng các trường `StepExecution` cho `readCount`, `writeCount`, commit và skip; context chỉ chứa state key-value cần thiết.

**Cho rằng `COMPLETED` chứng minh nghiệp vụ đúng.** Hãy kiểm tra context mong đợi và dữ liệu nghiệp vụ thực tế.

**Sửa context qua JobExplorer.** JobExplorer là API đọc. Ghi state trong step lifecycle hoặc qua cơ chế Spring Batch phù hợp.

**Log hoặc trả toàn bộ context.** Context có thể chứa thông tin kỹ thuật hoặc dữ liệu không nên công khai. Chọn key cụ thể và kiểm soát quyền truy cập.

## Kết luận

Để kiểm tra state sau một lần chạy, trước hết lấy đúng `JobExecution` ID, sau đó đọc `JobExecution.getExecutionContext()` cho phạm vi job và `StepExecution.getExecutionContext()` cho từng step. `JobExplorer` giúp tải lại metadata đã lưu từ `JobRepository`, đặc biệt hữu ích khi job chạy bất đồng bộ hoặc khi cần tra cứu sau khi ứng dụng đã khởi động lại.

Hãy phân biệt execution context với `BatchStatus`, `ExitStatus`, bộ đếm của step và dữ liệu nghiệp vụ. Đọc đúng key, kiểm tra sự tồn tại trước khi truy cập, giữ context nhỏ và có thể serialize, đồng thời không sửa metadata qua API chỉ đọc. Khi kiểm tra cả context lẫn dữ liệu nghiệp vụ thực tế, ta có thể xác nhận job đã lưu đúng checkpoint, step đã đi qua trạng thái mong đợi và kết quả sau lần chạy có thể được sử dụng hoặc restart một cách có kiểm soát.
