# Kiểm thử tasklet với step contribution

Trong Spring Batch, `Tasklet` là cách mô hình hóa một step thực hiện một tác vụ cụ thể, chẳng hạn dọn tệp tạm, gọi stored procedure, tạo báo cáo hoặc xử lý một nhóm dữ liệu theo cách do ứng dụng kiểm soát. Khi được gọi, tasklet nhận `StepContribution` và `ChunkContext`, sau đó trả về `RepeatStatus` để cho framework biết step đã hoàn tất hay cần tiếp tục lặp.

Kiểm thử tasklet cần xác nhận cả hành vi nghiệp vụ lẫn thông tin thực thi mà tasklet đóng góp cho step. `StepContribution` là nơi tasklet có thể ghi nhận số lượng đọc/ghi, số lượng bị lọc hoặc bị skip, và `ExitStatus` tùy chỉnh. Khi chạy thực tế, `TaskletStep` áp dụng contribution vào `StepExecution` và lưu metadata theo transaction. Khi gọi tasklet trực tiếp trong unit test, việc áp dụng contribution không tự xảy ra; bài kiểm thử cần phân biệt hai lớp đối tượng này.

## 1. Tasklet nhận StepContribution và ChunkContext

Interface `Tasklet` có phương thức `execute`:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

Hai tham số có vai trò khác nhau:

- **`StepContribution`** đại diện cho phần thay đổi mà lần thực thi tasklet đóng góp vào `StepExecution`, ví dụ số lượng bản ghi được ghi hoặc `ExitStatus` tùy chỉnh.
- **`ChunkContext`** cung cấp ngữ cảnh của chunk/tasklet hiện tại, bao gồm `StepContext`, `StepExecution`, job parameters và các thuộc tính được lưu trong context của chunk.

Tasklet trả về một trong các giá trị `RepeatStatus`:

| Giá trị | Ý nghĩa |
|---|---|
| `RepeatStatus.FINISHED` | Lần thực thi tasklet đã hoàn tất; step có thể kết thúc nếu không còn điều kiện điều phối khác |
| `RepeatStatus.CONTINUABLE` | Tasklet cần được gọi lại; thường dùng khi mỗi lần gọi xử lý một phần công việc |

Một tasklet đơn giản thường trả về `FINISHED`. Tasklet xử lý theo từng đợt có thể trả về `CONTINUABLE` cho đến khi hết dữ liệu.

## 2. StepContribution là gì?

`StepContribution` là một tập hợp các thay đổi phát sinh trong một đơn vị thực thi của step. Nó được gắn với một `StepExecution` và ghi nhận phần đóng góp mới, thay vì trực tiếp thay đổi toàn bộ bộ đếm tích lũy của step trong từng câu lệnh nghiệp vụ.

Những thông tin có thể được ghi nhận gồm:

- Số item đã đọc (`readCount`).
- Số item đã ghi (`writeCount`).
- Số item được lọc (`filterCount`).
- Số item bị skip ở giai đoạn đọc, xử lý hoặc ghi.
- Số lần rollback hoặc commit được ghi nhận theo API và flow thực thi.
- `ExitStatus` của phần thực thi.

Trong tasklet xử lý dữ liệu, có thể tăng bộ đếm khi biết chính xác số bản ghi đã xử lý. Ví dụ, nếu một tác vụ ghi thành công 12 bản ghi, tasklet có thể gọi `contribution.incrementWriteCount(12)`.

Không nên tự tăng bộ đếm chỉ để làm số liệu trông có vẻ đầy đủ. Tasklet dọn thư mục hoặc gọi một stored procedure không nhất thiết có `readCount` hay `writeCount` theo nghĩa item. Nếu tác vụ không xử lý item, các bộ đếm item có thể vẫn bằng 0 dù tasklet đã hoàn thành công việc.

## 3. StepContribution khác StepExecution như thế nào?

Hai đối tượng có quan hệ trực tiếp nhưng không thay thế nhau:

| Đối tượng | Vai trò | Phạm vi |
|---|---|---|
| `StepContribution` | Ghi nhận phần thay đổi của một lần gọi/đơn vị xử lý | Contribution hiện tại |
| `StepExecution` | Lưu trạng thái và số liệu tích lũy của lần chạy step | Toàn bộ execution của step |

Khi chạy tasklet trong `TaskletStep`, framework tạo contribution, truyền nó vào `execute`, sau đó áp dụng các thay đổi vào `StepExecution` trong vòng đời thực thi step. Các cập nhật metadata được phối hợp với transaction của tasklet step.

Trong unit test gọi `tasklet.execute(...)` trực tiếp, framework không đứng giữa để áp dụng contribution. Vì vậy, sau khi gọi tasklet, có thể kiểm tra trực tiếp `contribution.getWriteCount()`. Nếu muốn kiểm tra trạng thái tích lũy như khi framework áp dụng contribution, test có thể gọi `stepExecution.apply(contribution)` một cách tường minh.

Đây là điểm quan trọng khi viết test: nếu chỉ kiểm tra `stepExecution.getWriteCount()` sau khi gọi tasklet trực tiếp, kết quả có thể vẫn là 0 vì contribution chưa được apply.

## 4. Ví dụ tasklet có ghi nhận số lượng

Giả sử một tasklet tạo các bản ghi tổng hợp từ dữ liệu đã được chuẩn bị. Service trả về số bản ghi thực sự được ghi thành công.

```java
public class GenerateSummaryTasklet implements Tasklet {

    private final SummaryService summaryService;

    public GenerateSummaryTasklet(SummaryService summaryService) {
        this.summaryService = summaryService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        int written = summaryService.generate();
        contribution.incrementWriteCount(written);

        if (written == 0) {
            contribution.setExitStatus(new ExitStatus("NO_DATA"));
        }

        return RepeatStatus.FINISHED;
    }
}
```

Trong ví dụ:

- `SummaryService` thực hiện nghiệp vụ và trả về số bản ghi đã ghi.
- `incrementWriteCount(written)` ghi nhận số bản ghi đầu ra thực tế.
- Khi không có dữ liệu, tasklet đặt exit code `NO_DATA` để flow hoặc báo cáo có thể phân biệt với trường hợp có dữ liệu.
- `FINISHED` cho biết tasklet không cần được gọi lại.

`ExitStatus` là mã kết quả của step/job, còn `BatchStatus` là trạng thái vòng đời thực thi. Một step có thể kết thúc về mặt thực thi nhưng mang exit code tùy chỉnh để flow chuyển sang nhánh khác.

## 5. Kiểm thử unit trực tiếp Tasklet

Unit test có thể gọi `execute` trực tiếp mà không cần khởi chạy toàn bộ Spring Batch job. Để làm điều đó, tạo một `StepExecution`, một `StepContribution` gắn với execution đó và một `ChunkContext` chứa `StepContext`.

```java
StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
StepContribution contribution = new StepContribution(stepExecution);
ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));
```

`MetaDataInstanceFactory` thuộc module `spring-batch-test` và tạo metadata test tiện dụng. Cách dựng này giúp tasklet nhận được context hợp lệ mà không cần khởi chạy repository thật.

Ví dụ với JUnit 5 và Mockito:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.scope.context.StepContext;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.MetaDataInstanceFactory;

class GenerateSummaryTaskletTest {

    @Test
    void recordsWrittenCountAndFinishes() throws Exception {
        SummaryService summaryService = org.mockito.Mockito.mock(SummaryService.class);
        when(summaryService.generate()).thenReturn(3);

        GenerateSummaryTasklet tasklet =
                new GenerateSummaryTasklet(summaryService);

        StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
        StepContribution contribution = new StepContribution(stepExecution);
        ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));

        RepeatStatus result = tasklet.execute(contribution, chunkContext);

        assertEquals(RepeatStatus.FINISHED, result);
        assertEquals(3, contribution.getWriteCount());
        assertEquals("COMPLETED", contribution.getExitStatus().getExitCode());
        verify(summaryService).generate();
    }
}
```

Đoạn test kiểm tra ba điều: tasklet kết thúc, contribution ghi nhận ba bản ghi và service được gọi đúng một lần. `ExitStatus` mặc định của contribution thường là `COMPLETED`; khi tasklet đặt mã riêng, có thể kiểm tra mã đó thay cho giá trị mặc định.

Các import Mockito có thể được rút gọn bằng static import `mock(...)` trong dự án. Điều quan trọng là test không cần khởi tạo toàn bộ application context nếu mục tiêu chỉ là kiểm tra logic `execute`.

## 6. Kiểm tra StepExecution sau khi apply contribution

Khi muốn xác nhận cách contribution được cộng vào bộ đếm tích lũy, có thể mô phỏng bước framework áp dụng contribution:

```java
StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
StepContribution contribution = new StepContribution(stepExecution);
ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));

tasklet.execute(contribution, chunkContext);

stepExecution.apply(contribution);

assertEquals(3, stepExecution.getWriteCount());
assertEquals("COMPLETED", stepExecution.getExitStatus().getExitCode());
```

`StepExecution.apply(contribution)` cộng các bộ đếm và áp dụng thông tin exit status từ contribution vào execution. Trong test trực tiếp, đây là thao tác mô phỏng phần tích hợp do framework đảm nhiệm. Khi chạy step thật qua `JobLauncher`, ứng dụng không tự gọi `apply` trong tasklet; `TaskletStep` quản lý vòng đời này.

Không gọi `apply` hai lần cho cùng một contribution trong test, vì điều đó sẽ cộng số liệu hai lần và không phản ánh cách thực thi bình thường.

## 7. Kiểm thử nhánh không có dữ liệu và ExitStatus tùy chỉnh

Nếu tasklet có nhánh nghiệp vụ khác nhau, hãy kiểm tra từng nhánh. Ví dụ, không có dữ liệu thì trả về `FINISHED` và đặt exit code `NO_DATA`.

```java
@Test
void returnsNoDataExitStatusWhenNothingWasWritten() throws Exception {
    SummaryService summaryService = mock(SummaryService.class);
    when(summaryService.generate()).thenReturn(0);

    GenerateSummaryTasklet tasklet = new GenerateSummaryTasklet(summaryService);
    StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
    StepContribution contribution = new StepContribution(stepExecution);
    ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));

    RepeatStatus result = tasklet.execute(contribution, chunkContext);

    assertEquals(RepeatStatus.FINISHED, result);
    assertEquals(0, contribution.getWriteCount());
    assertEquals("NO_DATA", contribution.getExitStatus().getExitCode());
}
```

Nếu step dùng exit code để điều hướng flow, integration test nên kiểm tra cả step exit status và step tiếp theo được chạy đúng. Chỉ kiểm tra `RepeatStatus.FINISHED` chưa đủ để chứng minh flow xử lý đúng kết quả nghiệp vụ.

## 8. Kiểm thử lỗi và exception

Tasklet có thể ném exception khi service thất bại. Unit test nên xác nhận exception được truyền ra và không ghi nhận số lượng thành công giả.

```java
@Test
void propagatesServiceFailure() throws Exception {
    SummaryService summaryService = mock(SummaryService.class);
    when(summaryService.generate()).thenThrow(new IOException("Output unavailable"));

    GenerateSummaryTasklet tasklet = new GenerateSummaryTasklet(summaryService);
    StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
    StepContribution contribution = new StepContribution(stepExecution);
    ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));

    assertThrows(IOException.class,
            () -> tasklet.execute(contribution, chunkContext));

    assertEquals(0, contribution.getWriteCount());
    verify(summaryService).generate();
}
```

Test này xác nhận tasklet không nuốt exception và không tăng `writeCount` khi service chưa báo ghi thành công. Nếu service có thể ghi một phần trước khi ném lỗi, unit test này không chứng minh dữ liệu đã được rollback; cần integration test với transaction manager và resource thực.

Không nên bắt mọi exception trong tasklet rồi trả `FINISHED`. Nếu tasklet che giấu lỗi, framework có thể đánh dấu step thành công dù nghiệp vụ chưa hoàn tất.

## 9. Kiểm thử RepeatStatus.CONTINUABLE

Một tasklet có thể xử lý dữ liệu theo từng đợt. Mỗi lần gọi xử lý một phần rồi trả `CONTINUABLE`; khi hết dữ liệu thì trả `FINISHED`.

Ví dụ logic:

```java
public class ProcessPagesTasklet implements Tasklet {

    private final PageService pageService;

    public ProcessPagesTasklet(PageService pageService) {
        this.pageService = pageService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        int written = pageService.processNextPage();
        contribution.incrementWriteCount(written);

        return pageService.hasMorePages()
                ? RepeatStatus.CONTINUABLE
                : RepeatStatus.FINISHED;
    }
}
```

Với tasklet lặp, nên kiểm tra:

- Lần gọi có dữ liệu trả `CONTINUABLE` khi vẫn còn phần việc.
- Lần gọi cuối trả `FINISHED`.
- Mỗi lần gọi chỉ xử lý một phần công việc đã xác định.
- Số liệu contribution được ghi nhận cho đúng phần xử lý.
- Nếu một lần gọi thất bại, transaction và state cho phép tiếp tục mà không xử lý trùng hoặc bỏ sót.

Trong `TaskletStep`, framework quản lý các lần gọi và transaction theo vòng lặp. Khi unit test trực tiếp, có thể gọi tasklet nhiều lần với contribution tương ứng để kiểm tra logic từng lượt; để xác nhận hành vi repeat và transaction thực tế, nên chạy integration test với step đã cấu hình.

Tasklet lặp cần có điều kiện kết thúc rõ ràng. Nếu `hasMorePages()` luôn trả true do lỗi state, step có thể chạy vô hạn. Có thể bổ sung giới hạn số lượt, timeout hoặc điều kiện dừng vận hành phù hợp.

## 10. Kiểm thử tasklet có dùng StepScope hoặc JobParameters

Tasklet có thể được khai báo `@StepScope` để nhận job parameters hoặc step execution context tại thời điểm chạy. Khi đó, unit test gọi constructor trực tiếp có thể không kiểm tra được cơ chế late binding của Spring.

Spring Batch Test cung cấp `StepScopeTestUtils` để chạy một đoạn code trong step scope với `StepExecution` giả lập:

```java
StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution(
        new JobParametersBuilder()
                .addString("outputFile", "target/test-output.csv", true)
                .toJobParameters());

StepScopeTestUtils.doInStepScope(stepExecution, () -> {
    // Lấy bean @StepScope và kiểm tra logic trong ngữ cảnh step.
    assertNotNull(tasklet);
    return null;
});
```

Trong ví dụ, `tasklet` đại diện cho bean step-scoped được inject từ test context. `StepScopeTestUtils` kích hoạt scope trong thời gian callback, nhờ đó các biểu thức tham chiếu `jobParameters` hoặc `stepExecutionContext` có thể được resolve.

Nếu cần kiểm tra việc Spring tạo bean và inject tham số đúng, nên dùng test context có cấu hình batch thật. Nếu chỉ kiểm tra thuật toán nghiệp vụ, có thể truyền giá trị vào constructor hoặc mock collaborator để test đơn giản hơn.

## 11. Integration test với JobLauncherTestUtils

Unit test gọi `execute` trực tiếp không kiểm tra được toàn bộ hành vi của `TaskletStep`, transaction manager, `JobRepository`, lưu metadata hoặc flow transition. Với những yêu cầu đó, nên chạy step thông qua `JobLauncherTestUtils`.

`@SpringBatchTest` hỗ trợ đăng ký các tiện ích test của Spring Batch như `JobLauncherTestUtils`, `JobRepositoryTestUtils` và các listener phục vụ step/job scope. Ví dụ khái quát với JUnit 5:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class ArchiveStepIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @AfterEach
    void cleanMetadata() {
        jobRepositoryTestUtils.removeJobExecutions();
    }

    @Test
    void launchesArchiveStepAndRecordsContribution() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchStep(
                "archiveStep", parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution stepExecution = execution.getStepExecutions()
                .stream()
                .filter(step -> "archiveStep".equals(step.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(3, stepExecution.getWriteCount());
    }
}
```

Đây là khung minh họa; `BatchTestConfiguration` cần cung cấp job, step, repository, datasource, transaction manager và các collaborator cần thiết. `launchStep` chạy step được chọn thông qua hạ tầng Spring Batch, vì vậy test có thể kiểm tra trạng thái và contribution sau khi framework hoàn tất.

Nếu test chạy lặp lại, cần quản lý metadata và identifying parameters để không gặp `JobInstanceAlreadyCompleteException`. Có thể dọn execution metadata bằng `JobRepositoryTestUtils` trong môi trường test hoặc dùng identifying parameters riêng cho từng lần test. Không dùng cách dọn metadata này trên repository production.

## 12. Kiểm thử rollback bằng database thật trong test

Một unit test mock service ném exception chỉ chứng minh tasklet phản ứng với lỗi. Nó không chứng minh transaction đã rollback dữ liệu. Muốn kiểm tra rollback, cần integration test sử dụng database test và transaction manager thực tế của step.

Ví dụ tình huống:

1. Tasklet dùng `JdbcTemplate` để insert một dòng vào bảng test.
2. Sau insert, tasklet ném exception có chủ đích.
3. `TaskletStep` nhận exception và transaction rollback.
4. Test truy vấn database sau khi job kết thúc và xác nhận dòng insert không tồn tại.

Tasklet minh họa:

```java
public class InsertThenFailTasklet implements Tasklet {

    private final JdbcTemplate jdbcTemplate;

    public InsertThenFailTasklet(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        jdbcTemplate.update(
                "insert into batch_test_record(id, name) values (?, ?)",
                1L, "temporary");

        contribution.incrementWriteCount(1);
        throw new IllegalStateException("Force rollback for test");
    }
}
```

Trong integration test, launch step rồi xác nhận `BatchStatus.FAILED` và truy vấn `select count(*) from batch_test_record where id = 1` cho kết quả 0. Test cần bảo đảm `JdbcTemplate` sử dụng cùng `DataSource` và transaction manager mà step sử dụng. Nếu tasklet tự mở connection hoặc ghi qua hệ thống ngoài transaction, assertion rollback có thể không đúng.

Một lưu ý nữa: `writeCount` được tăng trong contribution trước khi exception xảy ra không đồng nghĩa với dữ liệu đã commit. Khi transaction thất bại, contribution của lần thực thi không được áp dụng như một chunk thành công. Hãy kiểm tra cả metadata cuối cùng và dữ liệu thực tế, không suy luận từ biến cục bộ trước exception.

## 13. Kiểm thử ExitStatus và flow transition

Một tasklet có thể đặt `ExitStatus` tùy chỉnh để job chuyển sang step khác theo kết quả nghiệp vụ.

Ví dụ, `archiveStep` có thể trả `NO_DATA` khi không có tệp cần lưu trữ. Job có thể cấu hình flow:

```java
return new JobBuilder("archiveJob", jobRepository)
        .start(archiveStep)
            .on("NO_DATA").to(noDataNotificationStep)
        .from(archiveStep)
            .on("COMPLETED").to(reportStep)
        .from(archiveStep)
            .on("FAILED").fail()
        .end()
        .build();
```

Flow cụ thể có thể cần transition mặc định hoặc các trạng thái khác tùy cấu hình. Ý nghĩa là exit code của step có thể quyết định nhánh tiếp theo.

Khi kiểm thử, hãy xác nhận:

- Tasklet đặt đúng exit code cho từng trường hợp.
- Step kết thúc với `BatchStatus` phù hợp.
- Flow chọn đúng step tiếp theo.
- Job có `BatchStatus` và `ExitStatus` cuối cùng đúng với kết quả mong đợi.

Không nhầm `RepeatStatus.FINISHED` với `ExitStatus.COMPLETED`. `RepeatStatus` điều khiển việc lặp lời gọi tasklet; `ExitStatus` biểu diễn kết quả step để flow và hệ thống vận hành sử dụng.

## 14. Kiểm thử lỗi khi tasklet được gọi nhiều lần

Nếu tasklet trả về `CONTINUABLE`, nó có thể chạy nhiều lần trong cùng step execution. Một lỗi có thể xảy ra ở lần gọi thứ hai hoặc thứ ba sau khi những lần trước đã hoàn tất transaction.

Ví dụ, tasklet xử lý từng trang:

| Lần gọi | Kết quả nghiệp vụ | RepeatStatus | Transaction |
|---|---|---|---|
| 1 | Ghi trang 1 | `CONTINUABLE` | Commit nếu thành công |
| 2 | Ghi trang 2 | `CONTINUABLE` | Commit nếu thành công |
| 3 | Lỗi khi ghi trang 3 | Exception | Rollback transaction lần gọi 3 |
| Restart | Tiếp tục theo state đã lưu | Tùy kết quả | Các lần gọi đã commit được giữ |

Test cần xác định state của tasklet được lưu ở đâu. Nếu tasklet giữ `currentPage` trong field của một bean singleton, state có thể không được khôi phục đúng sau restart hoặc có thể bị chia sẻ giữa execution khác. Có thể dùng `ExecutionContext`, reader/stream phù hợp hoặc một khóa checkpoint nghiệp vụ được lưu bền vững.

Tasklet lặp nên xử lý từng đơn vị công việc một cách idempotent. Nếu lần gọi bị rollback rồi chạy lại, cùng trang không được tạo bản ghi trùng hoặc làm sai tổng số liệu.

## 15. Những điều không nên làm trong test tasklet

- **Chỉ kiểm tra mock được gọi:** điều đó chưa chứng minh contribution, exit status hoặc transaction có đúng.
- **Gọi tasklet trực tiếp rồi mong StepExecution tự đổi:** unit test phải đọc contribution hoặc gọi `apply` nếu cần mô phỏng phần tích hợp.
- **Mock transaction manager khi muốn kiểm tra rollback database:** mock không chứng minh database đã hoàn tác thao tác ghi.
- **Tăng writeCount cho mọi tác vụ:** chỉ ghi số liệu khi có ý nghĩa rõ ràng với số item thực sự được ghi.
- **Bắt exception trong tasklet rồi trả FINISHED:** có thể khiến step báo thành công trong khi công việc thất bại.
- **Dùng `@Transactional` bao ngoài test mà không hiểu transaction của job:** transaction test và transaction do `TaskletStep` mở có thể khác nhau; kết quả truy vấn có thể không phản ánh commit/rollback của job.
- **Dùng lại identifying parameters của một execution đã hoàn tất:** test có thể gặp lỗi instance đã hoàn tất; hãy quản lý metadata hoặc tham số test phù hợp.
- **Kiểm tra chỉ `RepeatStatus`:** cần kiểm tra thêm `BatchStatus`, `ExitStatus`, contribution và dữ liệu đích khi các yếu tố đó thuộc yêu cầu.

## 16. Phân chia unit test và integration test

Không phải mọi kiểm thử tasklet đều cần khởi chạy cả Spring Batch context. Có thể chọn mức test theo câu hỏi cần trả lời:

| Mục tiêu | Cách kiểm thử phù hợp |
|---|---|
| Tasklet gọi service đúng và trả `FINISHED` | Unit test gọi `execute` trực tiếp với mock |
| Tasklet tăng contribution đúng số lượng | Unit test kiểm tra `StepContribution` |
| Tasklet đặt exit code tùy chỉnh | Unit test kiểm tra `contribution.getExitStatus()` |
| Tasklet trả `CONTINUABLE` rồi kết thúc | Unit test các lần gọi; integration test nếu cần xác nhận vòng lặp của step |
| `@StepScope` nhận đúng job parameter | Test với Spring context và `StepScopeTestUtils` hoặc `@SpringBatchTest` |
| `TaskletStep` lưu StepExecution và metadata | Integration test qua `JobLauncherTestUtils` |
| Database rollback khi tasklet ném exception | Integration test với database và transaction manager thật |
| Flow chọn đúng nhánh theo ExitStatus | Integration test khởi chạy job và kiểm tra step executions |

Phân chia như vậy giúp unit test nhanh, tập trung vào logic tasklet; integration test tập trung vào phần framework, transaction, repository và flow mà unit test không mô phỏng đầy đủ.

## 17. Những nguyên tắc cần nhớ

- `Tasklet.execute` nhận `StepContribution` và `ChunkContext`, trả về `RepeatStatus`.
- `FINISHED` kết thúc việc lặp tasklet; `CONTINUABLE` yêu cầu framework gọi lại.
- `StepContribution` ghi nhận phần thay đổi của lần thực thi; `StepExecution` giữ số liệu tích lũy của step.
- Khi gọi tasklet trực tiếp trong unit test, kiểm tra contribution; framework không tự áp dụng contribution vào `StepExecution` trong lời gọi trực tiếp đó.
- Có thể gọi `StepExecution.apply(contribution)` trong test để mô phỏng bước áp dụng contribution, nhưng không gọi hai lần cho cùng contribution.
- Chỉ tăng read/write/filter/skip count khi số liệu phản ánh đúng công việc tasklet thực hiện.
- Dùng `MetaDataInstanceFactory` để tạo metadata test và `ChunkContext`/`StepContext` phù hợp.
- Dùng unit test để kiểm tra kết quả, contribution, exit status và exception; dùng integration test để kiểm tra transaction, rollback, repository và flow.
- Với tasklet dùng `@StepScope`, kiểm tra late binding bằng Spring Batch Test utilities hoặc context test phù hợp.
- Với tasklet lặp, kiểm tra `CONTINUABLE`, điều kiện kết thúc, state và khả năng chạy lại an toàn.

Kiểm thử tasklet với step contribution giúp xác nhận không chỉ tác vụ nghiệp vụ có chạy đúng mà còn cả số liệu và kết quả mà tasklet báo cho Spring Batch. Kết hợp unit test trực tiếp với integration test qua `TaskletStep` sẽ giúp phân biệt lỗi logic của tasklet với lỗi do transaction, metadata hoặc flow điều phối.
