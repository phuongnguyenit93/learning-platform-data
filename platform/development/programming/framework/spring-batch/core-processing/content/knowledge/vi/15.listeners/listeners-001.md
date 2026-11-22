# JobExecutionListener trước và sau job

Trong Spring Batch, `JobExecutionListener` cung cấp hai callback để thực hiện công việc gắn với vòng đời của một lần chạy Job: `beforeJob()` được gọi trước khi Job thực hiện các Step và `afterJob()` được gọi sau khi Job kết thúc. Listener thường được dùng để ghi nhận thời điểm bắt đầu/kết thúc, lưu audit, tổng hợp kết quả hoặc phát thông báo dựa trên trạng thái thực thi.

Listener nhận đối tượng `JobExecution`, vì vậy có thể đọc JobParameters, trạng thái `BatchStatus`, `ExitStatus`, thời gian chạy, các StepExecution và exception. Cần nhớ listener gắn với **một lần thực thi Job**. Nếu JobInstance được restart, Spring Batch tạo JobExecution mới và các callback được gọi lại cho lần thực thi mới.

## 1. JobExecutionListener là gì?

`JobExecutionListener` là interface trong Spring Batch với hai phương thức:

```java
public interface JobExecutionListener {

    void beforeJob(JobExecution jobExecution);

    void afterJob(JobExecution jobExecution);
}
```

- `beforeJob(JobExecution)`: chạy trước khi các Step của Job bắt đầu thực hiện.
- `afterJob(JobExecution)`: chạy sau khi Job đã kết thúc, bất kể Job hoàn thành thành công hay thất bại.

Listener phù hợp với các hành động ở cấp Job. Ví dụ, ghi log bắt đầu một lần nhập dữ liệu, lưu thời điểm kết thúc và kết quả, hoặc gửi thông báo khi Job thất bại.

Luồng tổng quát:

```text
JobLauncher
    |
    v
Tạo JobExecution
    |
    v
beforeJob(jobExecution)
    |
    v
Thực hiện các Step
    |
    +----> Job hoàn tất
    |         hoặc
    +----> Job thất bại / bị dừng
    |
    v
afterJob(jobExecution)
    |
    v
JobExecution kết thúc
```

`beforeJob` và `afterJob` không thay thế logic xử lý dữ liệu của Step. Chúng là điểm móc vòng đời để thực hiện công việc chung cho toàn Job.

## 2. Ý nghĩa của beforeJob()

`beforeJob()` được gọi trước khi Job bắt đầu thực hiện các Step. Đây là nơi phù hợp để ghi nhận một lần chạy bắt đầu hoặc đọc các thông tin đầu vào cần dùng cho audit.

Các công việc thường đặt trong `beforeJob()`:

- Ghi log tên Job, JobExecution ID và identifying JobParameters.
- Ghi nhận thời điểm bắt đầu hoặc tạo audit record cho lần thực thi.
- Đưa một giá trị nhỏ dùng chung vào Job `ExecutionContext` nếu các Step cần đọc.
- Gắn correlation ID hoặc thông tin truy vết với lần thực thi.

Ví dụ listener ghi log khi Job bắt đầu:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class ImportJobListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportJobListener.class);

    @Override
    public void beforeJob(JobExecution jobExecution) {
        log.info("Job {} is starting. executionId={}, parameters={}",
                jobExecution.getJobInstance().getJobName(),
                jobExecution.getId(),
                jobExecution.getJobParameters());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        // Xử lý kết quả ở callback sau.
    }
}
```

`beforeJob()` không phải nơi thích hợp để xử lý hàng loạt bản ghi hoặc thực hiện một tác vụ dài. Hãy đặt công việc nghiệp vụ trong Step để nó có transaction boundary, trạng thái và khả năng restart riêng.

Nếu `beforeJob()` cần ghi audit vào database, nên gọi một service có transaction phù hợp. Không nên tự mở transaction bao trùm toàn bộ Job chỉ để giữ audit record.

## 3. Ý nghĩa của afterJob()

`afterJob()` được gọi sau khi Job kết thúc, dù kết quả là thành công hay thất bại. Listener cần kiểm tra trạng thái trong `JobExecution` để quyết định hành động phù hợp.

Các công việc thường đặt trong `afterJob()`:

- Ghi thời điểm kết thúc và thời lượng thực thi.
- Lưu trạng thái cuối cùng và mã `ExitStatus` vào audit.
- Tổng hợp số liệu từ các StepExecution.
- Ghi nhận exception khi Job thất bại.
- Gửi thông báo hoặc phát tín hiệu cho hệ thống giám sát.

Ví dụ:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class ImportJobListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportJobListener.class);

    @Override
    public void beforeJob(JobExecution jobExecution) {
        log.info("Starting job execution {}", jobExecution.getId());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        if (jobExecution.getStatus() == BatchStatus.COMPLETED) {
            log.info("Job execution {} completed with exit status {}",
                    jobExecution.getId(), jobExecution.getExitStatus());
        } else if (jobExecution.getStatus() == BatchStatus.FAILED) {
            log.error("Job execution {} failed. Exceptions: {}",
                    jobExecution.getId(),
                    jobExecution.getAllFailureExceptions());
        } else {
            log.warn("Job execution {} ended with status {}",
                    jobExecution.getId(), jobExecution.getStatus());
        }
    }
}
```

Không nên chỉ kiểm tra `COMPLETED` và `FAILED` rồi mặc định mọi trạng thái khác là thành công. Job có thể kết thúc với trạng thái như `STOPPED`, `ABANDONED` hoặc một trạng thái khác cần được vận hành xử lý riêng.

## 4. Phân biệt BatchStatus và ExitStatus trong listener

`JobExecution` cung cấp cả `BatchStatus` và `ExitStatus`. Hai giá trị này liên quan nhưng có mục đích khác nhau:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| `BatchStatus` | Trạng thái vòng đời thực thi do Spring Batch quản lý | `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` |
| `ExitStatus` | Mã kết quả thoát của Job, có thể mang mã tùy chỉnh | `COMPLETED`, `FAILED`, `NO_DATA`, `INVALID_INPUT` |

Trong `afterJob()`, `BatchStatus` thường được dùng để quyết định Job có thành công hay thất bại về mặt thực thi. `ExitStatus` hữu ích khi cần phân biệt các kết quả nghiệp vụ. Ví dụ, Job có thể kết thúc với mã `NO_DATA` để thể hiện không có dữ liệu trong ngày, trong khi trạng thái thực thi vẫn hoàn tất bình thường.

Nếu cần điều hướng giữa các Step, hãy cấu hình flow dựa trên `ExitStatus` của Step. `JobExecutionListener` chủ yếu quan sát vòng đời Job; không nên dùng listener để thay thế luồng điều khiển đã được khai báo trong Job.

## 5. Đọc thông tin từ JobExecution

Callback nhận một `JobExecution`, trong đó có nhiều thông tin hữu ích:

| API | Thông tin |
|---|---|
| `getId()` | ID của lần thực thi Job. |
| `getJobInstance()` | JobInstance mà lần thực thi thuộc về. |
| `getJobParameters()` | Các tham số đầu vào của lần chạy. |
| `getStatus()` | BatchStatus hiện tại/cuối cùng. |
| `getExitStatus()` | ExitStatus của Job. |
| `getStartTime()` | Thời điểm bắt đầu. |
| `getEndTime()` | Thời điểm kết thúc. |
| `getStepExecutions()` | Các StepExecution thuộc lần chạy này. |
| `getAllFailureExceptions()` | Các exception thất bại được ghi nhận. |
| `getExecutionContext()` | Job ExecutionContext của lần thực thi. |

Có thể tổng hợp số liệu từ StepExecution trong `afterJob()`:

```java
@Override
public void afterJob(JobExecution jobExecution) {
    for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
        log.info(
                "Step {} status={}, read={}, write={}, filter={}, skip={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getFilterCount(),
                stepExecution.getSkipCount());
    }
}
```

Số liệu này giúp tạo báo cáo tổng kết một lần chạy. Nếu Job có nhiều Step hoặc các nhánh flow, cần đọc tất cả StepExecution thay vì giả định Job luôn có một Step duy nhất.

## 6. Đăng ký JobExecutionListener trong Job

Với Spring Batch 5 trở lên, có thể đăng ký listener bằng phương thức `.listener(...)` trên `JobBuilder`:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ImportJobConfig {

    @Bean
    public ImportJobListener importJobListener() {
        return new ImportJobListener();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep,
            ImportJobListener importJobListener) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .listener(importJobListener)
                .start(importOrdersStep)
                .build();
    }
}
```

Sau khi đăng ký, Spring Batch gọi listener trong vòng đời của mỗi JobExecution. Nếu Job có nhiều Step, listener vẫn được gọi ở cấp Job một lần trước các Step và một lần sau khi Job kết thúc.

Một listener có thể được đăng ký cho nhiều Job nếu cùng một logic phù hợp. Khi đó, nên dùng `jobExecution.getJobInstance().getJobName()` để phân biệt Job và tránh lưu trạng thái riêng của lần chạy vào field mutable dùng chung.

## 7. Dùng annotation @BeforeJob và @AfterJob

Ngoài cách triển khai interface, Spring Batch hỗ trợ các annotation `@BeforeJob` và `@AfterJob` cho phương thức listener. Cách này có thể giúp tách callback thành các phương thức có tên rõ nghĩa:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.annotation.AfterJob;
import org.springframework.batch.core.annotation.BeforeJob;

public class AnnotatedImportListener {

    @BeforeJob
    public void before(JobExecution jobExecution) {
        System.out.println("Starting: "
                + jobExecution.getJobInstance().getJobName());
    }

    @AfterJob
    public void after(JobExecution jobExecution) {
        System.out.println("Finished with status: "
                + jobExecution.getStatus());
    }
}
```

Bean annotation listener cũng phải được đăng ký với Job:

```java
return new JobBuilder("importOrdersJob", jobRepository)
        .listener(annotatedImportListener)
        .start(importOrdersStep)
        .build();
```

Các phương thức callback cần nhận đúng loại tham số mà annotation hỗ trợ. Nếu muốn cách triển khai tường minh, dễ tìm bằng IDE và dễ tổ chức logic chung, interface `JobExecutionListener` là lựa chọn trực tiếp.

## 8. Listener được gọi lại khi restart

`JobExecutionListener` gắn với JobExecution, không gắn một lần duy nhất với JobInstance. Khi một JobInstance thất bại và được restart, Spring Batch tạo JobExecution mới. Do đó, cả `beforeJob()` và `afterJob()` được gọi cho lần thực thi mới.

Ví dụ:

```text
JobInstance: importOrders / fileId=orders-2026-11-15
  |
  +--> JobExecution #101: FAILED
  |       beforeJob()
  |       Step chạy và thất bại
  |       afterJob()
  |
  +--> JobExecution #108: COMPLETED
          beforeJob()
          Step restart và hoàn tất
          afterJob()
```

Vì callback được gọi lại, các hành động trong listener phải được thiết kế phù hợp với nhiều lần thực thi. Ví dụ, nếu `afterJob()` gửi email, lần restart thành công có thể gửi một email mới. Nếu yêu cầu chỉ gửi thông báo một lần cho một đơn vị nghiệp vụ, cần dùng khóa chống trùng dựa trên JobInstance hoặc một mã nghiệp vụ phù hợp.

Không nên dùng một field như `startedAt` trong singleton listener để giữ thời gian bắt đầu giữa `beforeJob()` và `afterJob()`. Nếu hai JobExecution chạy đồng thời, giá trị field có thể bị ghi đè. Hãy lấy thời gian từ chính `JobExecution` hoặc lưu trạng thái cần thiết vào `ExecutionContext`.

## 9. Ghi audit và gửi thông báo an toàn

Một listener có thể gọi service để lưu audit record sau khi Job kết thúc:

```java
@Service
public class JobAuditService {

    @Transactional
    public void recordOutcome(
            long executionId,
            String jobName,
            String status,
            String exitCode) {
        // Lưu một audit record trong transaction ngắn.
    }
}
```

Listener gọi service này từ `afterJob()`:

```java
@Component
public class AuditingJobListener implements JobExecutionListener {

    private final JobAuditService auditService;

    public AuditingJobListener(JobAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void beforeJob(JobExecution jobExecution) {
        // Có thể ghi log hoặc tạo audit bắt đầu nếu cần.
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        String jobName = jobExecution.getJobInstance().getJobName();
        auditService.recordOutcome(
                jobExecution.getId(),
                jobName,
                jobExecution.getStatus().name(),
                jobExecution.getExitStatus().getExitCode());
    }
}
```

Transaction của `JobAuditService` là transaction ngắn cho thao tác audit. Không cần giữ một transaction mở trong toàn bộ thời gian Job chỉ để ghi kết quả.

Đối với email, HTTP hoặc message broker, cần cân nhắc việc callback có thể được gọi lại và tác dụng phụ ngoài database không thể rollback cùng Job. Có thể ghi một sự kiện hoàn tất vào outbox, sau đó một tiến trình khác gửi thông báo với idempotency key. Cách này giảm nguy cơ gửi trùng khi callback hoặc hệ thống bên ngoài gặp lỗi.

Listener là một phần của luồng thực thi Job. Vì vậy, callback nên ngắn và có kiểm soát lỗi. Nếu việc gửi thông báo không được phép làm thay đổi kết quả xử lý batch, hãy cô lập lỗi gửi thông báo, ghi nhận để retry riêng hoặc dùng outbox. Không nên để lỗi mạng nhất thời làm mất khả năng theo dõi kết quả Job.

## 10. JobExecutionListener và StepExecutionListener khác nhau thế nào?

Spring Batch có listener ở nhiều cấp độ. Cần chọn đúng listener theo phạm vi sự kiện muốn quan sát:

| Listener | Phạm vi | Callback thường dùng |
|---|---|---|
| `JobExecutionListener` | Toàn bộ một JobExecution | Trước và sau Job |
| `StepExecutionListener` | Một StepExecution | Trước và sau Step |
| `ChunkListener` | Một chunk | Trước và sau chunk, khi chunk bị lỗi |
| `ItemReadListener` | Một lần đọc item | Trước/sau đọc và khi đọc lỗi |
| `ItemProcessListener` | Một lần xử lý item | Trước/sau xử lý và khi processor lỗi |
| `ItemWriteListener` | Một lần ghi nhóm item | Trước/sau ghi và khi writer lỗi |

Ví dụ:

- Ghi nhận tổng thời gian nhập đơn hàng: dùng `JobExecutionListener`.
- Ghi thời gian riêng của Step đọc file: dùng `StepExecutionListener`.
- Ghi số lần một chunk rollback: dùng `ChunkListener` hoặc metadata tương ứng.
- Điều tra một bản ghi cụ thể gây lỗi processor: dùng `ItemProcessListener`.

Không nên đặt logic audit của từng item trong `afterJob()` vì callback này chỉ chạy ở cấp Job và không cung cấp sự kiện chi tiết cho từng item.

## 11. Lưu ý về thread và asynchronous JobLauncher

Trong Spring Boot hoặc ứng dụng Spring, listener thường được khai báo thành singleton bean. Nhiều JobExecution có thể dùng cùng một instance listener, đặc biệt khi Job được chạy đồng thời. Vì vậy:

- Tránh lưu trạng thái riêng của JobExecution trong field mutable của listener.
- Dùng dữ liệu trên `JobExecution` hoặc `ExecutionContext` thay cho biến dùng chung.
- Các dependency được gọi từ listener phải hỗ trợ cách sử dụng đồng thời của ứng dụng.
- Không giả định callback luôn chạy trên thread đã gọi `JobLauncher`.

Nếu dùng asynchronous `JobLauncher`, `run()` có thể trả về khi Job mới bắt đầu được gửi đến executor. `afterJob()` được gọi ở thread thực thi Job khi Job kết thúc. Caller không nên chờ kết quả bằng cách giữ transaction mở; hãy theo dõi JobExecution qua repository, explorer hoặc cơ chế thông báo phù hợp.

## 12. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ xử lý `COMPLETED` trong afterJob | Bỏ qua trường hợp Job thất bại hoặc bị dừng. | Xử lý rõ các BatchStatus cần quan tâm. |
| Nghĩ listener chỉ chạy một lần cho JobInstance | Listener thực tế chạy theo từng JobExecution. | Thiết kế audit và notification cho cả restart. |
| Lưu thời gian bắt đầu trong field của singleton listener | Nhiều execution đồng thời có thể ghi đè field. | Dùng JobExecution hoặc ExecutionContext. |
| Thực hiện toàn bộ nghiệp vụ trong beforeJob/afterJob | Khó quản lý transaction, retry và restart của phần nghiệp vụ. | Đưa xử lý chính vào Step; listener chỉ làm lifecycle work. |
| Gửi email trực tiếp rồi không kiểm soát lỗi | Thông báo có thể gửi trùng hoặc lỗi callback ảnh hưởng luồng thực thi. | Dùng outbox, idempotency key và retry riêng. |
| Nhầm JobExecutionListener với StepExecutionListener | Ghi nhận sai phạm vi hoặc thiếu dữ liệu chi tiết. | Chọn listener theo cấp Job, Step, chunk hoặc item. |
| Cho rằng afterJob chạy trên thread gọi launch | Asynchronous launcher thực thi Job ở thread khác. | Theo dõi execution bằng metadata và cơ chế giám sát. |

## Kết luận

`JobExecutionListener` cung cấp `beforeJob()` và `afterJob()` để xử lý các công việc gắn với vòng đời của một lần chạy Job. `beforeJob()` phù hợp để ghi nhận bắt đầu và thông tin đầu vào; `afterJob()` phù hợp để đọc trạng thái cuối, tổng hợp StepExecution, lưu audit hoặc phát tín hiệu kết quả. Listener cần phân biệt `BatchStatus` với `ExitStatus`, được đăng ký vào Job bằng `.listener(...)` và được gọi lại cho mỗi JobExecution, kể cả khi restart. Giữ callback ngắn, tránh trạng thái mutable dùng chung và dùng outbox/idempotency cho thông báo sẽ giúp theo dõi Job tin cậy mà không làm phức tạp transaction của các Step.
