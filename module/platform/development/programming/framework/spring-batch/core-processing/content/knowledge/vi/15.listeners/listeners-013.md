# Kiểm thử listener với execution status

Trong Spring Batch, `JobExecutionListener` cung cấp hai callback `beforeJob()` và `afterJob()` để thực hiện công việc gắn với vòng đời của một lần chạy Job. Khi kiểm thử listener, cần xác nhận callback được gọi đúng thời điểm, nhận đúng `JobExecution` và xử lý đúng các trạng thái như `COMPLETED`, `FAILED` hoặc `STOPPED`.

Điểm quan trọng là listener làm việc với **JobExecution**, tức một lần thực thi cụ thể. Một JobInstance có thể có nhiều JobExecution nếu Job được restart. Vì vậy, bài test cần kiểm tra trạng thái của từng lần chạy và tránh dùng trạng thái lưu trong field của listener để suy ra kết quả.

## 1. Xác định hành vi cần kiểm thử

`JobExecutionListener` có hai phương thức:

```java
public interface JobExecutionListener {
    void beforeJob(JobExecution jobExecution);
    void afterJob(JobExecution jobExecution);
}
```

- `beforeJob()` được gọi trước khi Job bắt đầu thực hiện các Step. Có thể dùng để ghi nhận Job bắt đầu, JobParameters hoặc tạo audit record.
- `afterJob()` được gọi sau khi Job kết thúc. Có thể dùng để lưu trạng thái cuối, tổng hợp số liệu hoặc phát tín hiệu kết quả.

Một listener thường cần phản ứng khác nhau theo `BatchStatus`:

| BatchStatus | Ý nghĩa | Hành vi có thể kiểm thử |
|---|---|---|
| `COMPLETED` | Job kết thúc bình thường theo flow đã cấu hình | Ghi nhận thành công, lưu ExitStatus và thời điểm kết thúc. |
| `FAILED` | Job thất bại | Ghi nhận lỗi, lưu failure exception và phát cảnh báo. |
| `STOPPED` | Job được dừng có kiểm soát | Ghi nhận trạng thái dừng và thông tin phục hồi. |
| `ABANDONED` | Execution được đánh dấu không tiếp tục theo cách restart thông thường | Ghi nhận trạng thái quản trị riêng. |
| `UNKNOWN` | Không xác định chắc chắn trạng thái | Đưa vào luồng điều tra thay vì xem là thành công. |

`BatchStatus` và `ExitStatus` cần được kiểm tra riêng. Ví dụ, Job có thể có `BatchStatus.COMPLETED` nhưng `ExitStatus` mang mã nghiệp vụ `NO_DATA`. Test nên xác nhận listener giữ được cả hai thông tin.

## 2. Tách logic listener để có thể unit test

Một listener có thể gọi service để lưu audit. Nên truyền `JobExecution` vào service dưới dạng các giá trị cần thiết, để unit test không phụ thuộc database hoặc Spring context.

```java
import java.util.List;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class JobOutcomeListener implements JobExecutionListener {

    private final JobAuditService auditService;

    public JobOutcomeListener(JobAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void beforeJob(JobExecution jobExecution) {
        String jobName = jobExecution.getJobInstance().getJobName();
        auditService.recordStarted(
                jobExecution.getId(),
                jobName,
                jobExecution.getJobParameters());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        String jobName = jobExecution.getJobInstance().getJobName();
        List<String> failureMessages = jobExecution.getAllFailureExceptions()
                .stream()
                .map(Throwable::getMessage)
                .toList();

        auditService.recordOutcome(
                jobExecution.getId(),
                jobName,
                jobExecution.getStatus(),
                jobExecution.getExitStatus().getExitCode(),
                failureMessages);
    }
}
```

`JobAuditService` là service của ứng dụng, có thể lưu audit vào database hoặc chuyển dữ liệu sang hệ thống giám sát:

```java
import java.util.List;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobParameters;
import org.springframework.stereotype.Service;

@Service
public class JobAuditService {

    public void recordStarted(
            Long executionId,
            String jobName,
            JobParameters parameters) {
        // Lưu thời điểm bắt đầu và thông tin lần chạy.
    }

    public void recordOutcome(
            Long executionId,
            String jobName,
            BatchStatus status,
            String exitCode,
            List<String> failureMessages) {
        // Lưu trạng thái cuối và thông tin lỗi.
    }
}
```

Phần lưu audit được để trong service để listener tập trung vào việc lấy thông tin từ `JobExecution`. Trong unit test, có thể mock service và xác nhận listener truyền đúng dữ liệu.

## 3. Tạo JobExecution trong unit test

Để test callback trực tiếp, có thể tạo `JobExecution` cùng `JobInstance` và `JobParameters`, sau đó đặt trạng thái cần kiểm thử.

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;

private JobExecution newJobExecution() {
    JobInstance instance = new JobInstance(1L, "importOrdersJob");
    return new JobExecution(instance, 10L, new JobParameters());
}
```

Trong test, có thể thay `BatchStatus` và `ExitStatus` để mô phỏng kết quả thực thi:

```java
JobExecution execution = newJobExecution();
execution.setStatus(BatchStatus.COMPLETED);
execution.setExitStatus(ExitStatus.COMPLETED);
```

Đây là metadata object dùng để kiểm thử listener. Nó không thực thi Job thật và không ghi metadata vào `JobRepository`. Vì vậy, unit test loại này chạy nhanh và phù hợp để kiểm tra logic callback.

## 4. Kiểm thử beforeJob() bằng Mockito

Test `beforeJob()` nên xác nhận listener ghi nhận đúng execution ID, tên Job và JobParameters.

```java
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;

@ExtendWith(MockitoExtension.class)
class JobOutcomeListenerBeforeTest {

    @Mock
    private JobAuditService auditService;

    @InjectMocks
    private JobOutcomeListener listener;

    @Test
    void recordsJobStart() {
        JobInstance instance = new JobInstance(1L, "importOrdersJob");
        JobParameters parameters = new JobParameters();
        JobExecution execution = new JobExecution(instance, 10L, parameters);

        listener.beforeJob(execution);

        verify(auditService).recordStarted(10L, "importOrdersJob", parameters);
    }
}
```

Test gọi trực tiếp callback và dùng Mockito `verify` để xác nhận service được gọi đúng một lần với dữ liệu tương ứng. Nếu listener cần đặt giá trị vào Job `ExecutionContext`, hãy kiểm tra giá trị đó sau khi gọi `beforeJob()`.

## 5. Kiểm thử afterJob() với trạng thái COMPLETED

Với Job thành công, listener cần ghi nhận `BatchStatus.COMPLETED`, mã `ExitStatus` và danh sách lỗi rỗng.

```java
import static org.mockito.Mockito.verify;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;

@ExtendWith(MockitoExtension.class)
class JobOutcomeListenerCompletedTest {

    @Mock
    private JobAuditService auditService;

    @InjectMocks
    private JobOutcomeListener listener;

    @Test
    void recordsCompletedExecution() {
        JobExecution execution = new JobExecution(
                new JobInstance(1L, "importOrdersJob"),
                10L,
                new JobParameters());
        execution.setStatus(BatchStatus.COMPLETED);
        execution.setExitStatus(ExitStatus.COMPLETED);

        listener.afterJob(execution);

        verify(auditService).recordOutcome(
                10L,
                "importOrdersJob",
                BatchStatus.COMPLETED,
                "COMPLETED",
                List.of());
    }
}
```

Test này xác nhận listener không chỉ kiểm tra trạng thái mà còn chuyển đúng mã ExitStatus và danh sách exception. Nếu listener có gửi thông báo thành công, có thể mock notification service và xác nhận nó chỉ được gọi cho trạng thái phù hợp.

## 6. Kiểm thử FAILED và failure exceptions

Khi Job thất bại, `JobExecution` có thể chứa một hoặc nhiều failure exception. Listener thường cần lưu trạng thái và thông điệp lỗi để hỗ trợ điều tra.

```java
import static org.mockito.Mockito.verify;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;

@ExtendWith(MockitoExtension.class)
class JobOutcomeListenerFailedTest {

    @Mock
    private JobAuditService auditService;

    @InjectMocks
    private JobOutcomeListener listener;

    @Test
    void recordsFailedExecutionAndException() {
        JobExecution execution = new JobExecution(
                new JobInstance(2L, "importOrdersJob"),
                20L,
                new JobParameters());
        execution.setStatus(BatchStatus.FAILED);
        execution.setExitStatus(ExitStatus.FAILED);
        execution.addFailureException(
                new IllegalStateException("Input file is invalid"));

        listener.afterJob(execution);

        verify(auditService).recordOutcome(
                20L,
                "importOrdersJob",
                BatchStatus.FAILED,
                "FAILED",
                List.of("Input file is invalid"));
    }
}
```

Test này không cần cố tình làm database hoặc file thất bại. Chỉ cần tạo JobExecution có trạng thái và exception mong muốn để kiểm tra logic xử lý của listener.

Không nên chỉ kiểm tra rằng listener gọi phương thức `recordOutcome()`. Hãy xác nhận chính xác status, exit code và lỗi được truyền vào, vì sai một giá trị có thể làm dashboard hoặc cảnh báo báo cáo sai tình trạng Job.

## 7. Dùng parameterized test cho nhiều execution status

Khi listener xử lý nhiều trạng thái theo cùng một quy tắc, có thể dùng JUnit 5 `@ParameterizedTest` để kiểm tra từng trạng thái.

```java
import static org.mockito.Mockito.verify;

import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;

@ExtendWith(MockitoExtension.class)
class JobOutcomeListenerStatusTest {

    @Mock
    private JobAuditService auditService;

    @InjectMocks
    private JobOutcomeListener listener;

    static Stream<BatchStatus> terminalStatuses() {
        return Stream.of(
                BatchStatus.COMPLETED,
                BatchStatus.FAILED,
                BatchStatus.STOPPED,
                BatchStatus.ABANDONED);
    }

    @ParameterizedTest
    @MethodSource("terminalStatuses")
    void recordsEveryTerminalStatus(BatchStatus status) {
        JobExecution execution = new JobExecution(
                new JobInstance(3L, "importOrdersJob"),
                30L,
                new JobParameters());
        execution.setStatus(status);
        execution.setExitStatus(new ExitStatus(status.name()));

        listener.afterJob(execution);

        verify(auditService).recordOutcome(
                30L,
                "importOrdersJob",
                status,
                status.name(),
                List.of());
    }
}
```

`UNKNOWN` và các trạng thái đang chạy như `STARTING`, `STARTED` hoặc `STOPPING` không phải kết quả kết thúc bình thường để kiểm tra trong cùng nhóm terminal status. Nếu ứng dụng có xử lý riêng các trạng thái này, hãy viết test tương ứng để bảo đảm listener không xem chúng là thành công.

## 8. Kiểm thử ExitStatus tùy chỉnh

`BatchStatus` cho biết trạng thái vòng đời thực thi; `ExitStatus` có thể mang mã nghiệp vụ. Listener nên giữ được cả hai giá trị.

Ví dụ Job hoàn thành bình thường nhưng không có dữ liệu:

```java
JobExecution execution = newJobExecution();
execution.setStatus(BatchStatus.COMPLETED);
execution.setExitStatus(new ExitStatus("NO_DATA"));

listener.afterJob(execution);

verify(auditService).recordOutcome(
        10L,
        "importOrdersJob",
        BatchStatus.COMPLETED,
        "NO_DATA",
        List.of());
```

Test này giúp phát hiện lỗi phổ biến là chỉ lấy `BatchStatus` rồi ghi cùng giá trị đó làm exit code. Khi cần điều khiển nhánh Step, hãy kiểm thử riêng flow của Job dựa trên `ExitStatus` ở Step; listener chỉ nên quan sát kết quả cuối.

## 9. Kiểm thử tích hợp với Spring Batch Test

Unit test kiểm tra callback trực tiếp, nhưng chưa xác nhận Spring Batch thực sự gọi listener trong vòng đời của Job. Để kiểm tra tích hợp, có thể dùng module `spring-batch-test` và `JobLauncherTestUtils`.

Thêm dependency test tương ứng với phiên bản Spring Batch mà ứng dụng đang dùng. Ví dụ Maven:

```xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
```

Với Spring Boot, dependency management của Boot thường quản lý version tương thích. Không nên tự chọn một version khác với Spring Batch core của ứng dụng.

Ví dụ integration test cho Job thành công:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@SpringBatchTest
class ImportJobListenerIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobAuditRepository auditRepository;

    @Test
    void listenerPersistsSuccessfulExecution() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRun", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertTrue(auditRepository.existsByExecutionId(execution.getId()));
    }
}
```

Ví dụ giả định test context có một Job được cấu hình cho `JobLauncherTestUtils`, listener đã được đăng ký vào Job và `JobAuditRepository` có phương thức kiểm tra audit theo execution ID. Nếu context có nhiều Job, cần chỉ rõ Job mà `JobLauncherTestUtils` sử dụng. Tham số `testRun` duy nhất giúp các lần test tạo JobInstance riêng, tránh bị từ chối vì instance trước đã `COMPLETED`.

Để kiểm thử trường hợp thất bại, cấu hình một Job test có Step ném exception:

```java
@Bean
public Step failingStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {
    return new StepBuilder("failingStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                throw new IllegalStateException("Simulated failure");
            }, transactionManager)
            .build();
}
```

Khi launch Job test chứa Step này, kiểm tra `JobExecution.getStatus()` là `FAILED` và audit record ghi đúng execution ID cùng failure message. Nếu `JobLauncherTestUtils.launchJob()` ném exception trong môi trường hoặc cấu hình test cụ thể, có thể truy vấn JobExecution từ `JobRepository`/`JobExplorer` theo ID hoặc tham số để xác nhận metadata cuối cùng.

## 10. Kiểm tra listener có được gọi đúng thứ tự không

Trong một integration test, có thể dùng một listener test ghi nhận các sự kiện vào một bộ sưu tập thread-safe hoặc một bảng audit. Với Job chạy tuần tự, thứ tự mong đợi là:

```text
beforeJob
    |
    v
beforeStep
    |
    v
Step thực thi
    |
    v
afterStep
    |
    v
afterJob
```

Nếu Job có nhiều Step, các callback Step xuất hiện theo flow của Job; `beforeJob` vẫn diễn ra trước các Step và `afterJob` sau khi Job kết thúc. Khi Job có nhánh hoặc Step chạy song song, thứ tự giữa các callback Step có thể khác; không nên viết test phụ thuộc vào thứ tự thread không được bảo đảm.

Một cách kiểm tra là tạo `RecordingJobExecutionListener` chỉ dùng trong test:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class RecordingJobExecutionListener implements JobExecutionListener {

    private final List<String> events = new CopyOnWriteArrayList<>();

    @Override
    public void beforeJob(JobExecution jobExecution) {
        events.add("before:" + jobExecution.getId());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        events.add("after:" + jobExecution.getId());
    }

    public List<String> events() {
        return List.copyOf(events);
    }
}
```

Sau khi launch Job test đồng bộ, có thể xác nhận event đầu tiên là `before:<executionId>` và event cuối là `after:<executionId>`. `CopyOnWriteArrayList` phù hợp cho bộ ghi nhận sự kiện test nhỏ có thể được truy cập từ nhiều thread; với listener production, không nên giữ lịch sử execution trong collection của singleton bean.

## 11. Kiểm thử listener khi Job restart

Listener chạy theo từng JobExecution. Nếu JobInstance đầu tiên thất bại và được restart, listener cần nhận hai execution riêng biệt:

```text
JobInstance: importOrders / businessDate=2026-11-15
  |
  +--> JobExecution #1: FAILED
  |       beforeJob(#1)
  |       afterJob(#1)
  |
  +--> JobExecution #2: COMPLETED
          beforeJob(#2)
          afterJob(#2)
```

Một integration test restart có thể thực hiện các bước:

1. Launch Job lần đầu với identifying JobParameters cố định và cấu hình test khiến một Step thất bại.
2. Xác nhận JobExecution đầu tiên có trạng thái `FAILED` và listener đã ghi audit cho execution ID đó.
3. Thay điều kiện test để Step có thể hoàn tất, ví dụ bỏ cờ gây lỗi hoặc sửa dữ liệu đầu vào.
4. Launch lại cùng Job với cùng identifying JobParameters.
5. Xác nhận JobExecution thứ hai thuộc cùng JobInstance nhưng có ID khác, trạng thái `COMPLETED` và listener ghi audit riêng.

Không thêm UUID định danh mới giữa hai lần gọi nếu mục tiêu là kiểm tra restart. Nếu thay identifying parameters, Spring Batch tạo JobInstance mới và test sẽ không còn kiểm tra restart cùng instance.

Nếu Step đã hoàn tất ở lần đầu, Step đó thường được bỏ qua khi restart trừ khi cấu hình `allowStartIfComplete(true)`. Test nên dựa vào chính sách restart thực tế của Job và reader/writer, không giả định mọi Step đều chạy lại từ đầu.

## 12. Kiểm thử lỗi phát sinh trong listener

Listener là một phần của vòng đời Job, vì vậy lỗi trong `beforeJob()` hoặc `afterJob()` có thể ảnh hưởng đến việc thực thi hoặc việc ghi nhận kết quả. Cần quyết định hành vi mong muốn và kiểm thử nó.

Ví dụ, nếu lưu audit bắt đầu thất bại trong `beforeJob()`, ứng dụng có thể muốn dừng Job vì không được phép chạy khi không có audit. Ngược lại, nếu gửi thông báo thất bại trong `afterJob()` nhưng thông báo không phải điều kiện nghiệp vụ của Job, có thể ghi log và đưa thông báo vào hàng đợi retry riêng.

Các test nên bao gồm:

- `recordStarted()` ném exception: xác nhận Job có bị ngăn chạy theo chính sách mong muốn hay không.
- `recordOutcome()` ném exception: xác nhận cách ứng dụng ghi nhận lỗi callback và trạng thái Job.
- Notification service timeout: xác nhận lỗi gửi thông báo không gây gửi trùng hoặc làm mất audit.
- Retry callback: xác nhận thao tác audit/notification có idempotency key phù hợp.

Không nên bắt mọi exception trong listener rồi bỏ qua. Nếu lỗi audit có ý nghĩa bắt buộc, cần để hệ thống thể hiện rõ lỗi. Nếu lỗi chỉ ảnh hưởng đến một kênh thông báo phụ, hãy tách nó khỏi trạng thái xử lý nghiệp vụ và có cơ chế retry độc lập.

## 13. Listener và asynchronous JobLauncher

Với synchronous launcher, `launchJob()` thường trả về sau khi Job kết thúc nên test có thể kiểm tra trạng thái cuối ngay sau lời gọi.

Với asynchronous launcher, phương thức launch có thể trả về khi Job vẫn đang ở `STARTING` hoặc `STARTED`. Khi đó, không được khẳng định `afterJob()` đã chạy chỉ vì `run()` trả về. Integration test cần đợi theo cơ chế đồng bộ hóa có giới hạn hoặc theo dõi JobExecution qua `JobExplorer`/repository cho đến khi đạt trạng thái kết thúc.

Listener thường là singleton bean và có thể được gọi đồng thời cho nhiều JobExecution. Không dùng field mutable như `currentStatus`, `currentJobName` hoặc `startedAt` để lưu trạng thái riêng của một lần chạy. Mọi thông tin cần kiểm thử phải gắn với execution ID hoặc nằm trong `JobExecution` tương ứng.

## 14. Những lỗi kiểm thử thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ test trạng thái COMPLETED | Không phát hiện listener xử lý sai khi FAILED hoặc STOPPED. | Dùng test riêng hoặc parameterized test cho các terminal status. |
| Chỉ assert BatchStatus | Bỏ qua mã kết quả nghiệp vụ trong ExitStatus. | Assert cả `getStatus()` và `getExitStatus().getExitCode()`. |
| Không kiểm tra failure exceptions | Audit có thể lưu FAILED nhưng mất thông tin nguyên nhân. | Thêm exception vào JobExecution và xác nhận nội dung được chuyển tiếp. |
| Dùng JobExecution giả để kết luận callback được Spring gọi | Unit test chỉ kiểm tra logic listener, không kiểm tra đăng ký hoặc lifecycle. | Bổ sung integration test với `JobLauncherTestUtils`. |
| Test restart nhưng đổi identifying parameters | Tạo JobInstance mới thay vì restart instance cũ. | Giữ nguyên identifying JobParameters qua hai lần launch. |
| Dùng một listener field để giữ trạng thái giữa callback | Nhiều execution đồng thời có thể ghi đè dữ liệu. | Dùng JobExecution ID và metadata tương ứng. |
| Test async rồi assert ngay sau launch | Job có thể chưa kết thúc và afterJob chưa được gọi. | Theo dõi execution đến trạng thái terminal bằng cơ chế có timeout. |
| Gửi email thật trong unit test | Test phụ thuộc mạng và có tác dụng phụ. | Mock notification service hoặc dùng outbox test. |

## Kết luận

Kiểm thử listener với execution status cần bao phủ cả callback `beforeJob()` và `afterJob()`, các trạng thái `COMPLETED`, `FAILED`, `STOPPED` và mã `ExitStatus` tương ứng. Unit test có thể tạo `JobExecution` giả lập và dùng Mockito để xác nhận audit hoặc notification service nhận đúng dữ liệu. Integration test với `spring-batch-test` và `JobLauncherTestUtils` xác nhận Spring Batch thực sự gọi listener trong vòng đời Job, đồng thời có thể kiểm tra restart và thứ tự callback. Hãy gắn mọi kết quả với execution ID, xử lý rõ lỗi trong listener và không giả định Job đã kết thúc khi asynchronous launcher mới chỉ trả về.
