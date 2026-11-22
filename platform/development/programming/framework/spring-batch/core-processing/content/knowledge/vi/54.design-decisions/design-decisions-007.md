# Chọn synchronous hay asynchronous launch trong Spring Batch

Một job Spring Batch có thể chạy trong vài giây hoặc nhiều giờ. Khi thiết kế cách khởi chạy job, cần quyết định: **bên gọi phải đợi job kết thúc rồi mới nhận kết quả, hay chỉ gửi yêu cầu chạy và theo dõi kết quả sau?** Đây là lựa chọn giữa **synchronous launch** và **asynchronous launch**. Quyết định này ảnh hưởng trực tiếp đến thời gian phản hồi HTTP, vòng đời ứng dụng, tài nguyên thread, khả năng giám sát, cách xử lý lỗi và độ tin cậy khi hệ thống bị khởi động lại.

Bài học thuộc **Spring Batch Core Processing → Quyết định thiết kế**. Các ví dụ sử dụng **Java 17, Spring Boot 3.x và Spring Batch 5.x**. Ta sẽ xem cơ chế `JobLauncher`, cấu hình `TaskExecutorJobLauncher`, cách chọn launch mode cho CLI và REST API, trạng thái `JobExecution`, giới hạn concurrency, lưu metadata, restart, kiểm thử và những sai lầm hay gặp.

## 1. Synchronous và asynchronous khác nhau ở điểm nào?

**Synchronous launch**: thread gọi `JobLauncher.run(job, parameters)` thường thực thi job và **chờ tới khi job hoàn thành** trước khi phương thức trả về. Bên gọi có thể kiểm tra trạng thái cuối như `COMPLETED` hoặc `FAILED` ngay sau đó.

**Asynchronous launch**: `JobLauncher.run(...)` sử dụng `TaskExecutor` để đưa quá trình thực thi job sang thread khác. Phương thức có thể **trả về trước khi job kết thúc**. Giá trị trả về là `JobExecution` đã được tạo, nhưng trạng thái khi đó thường còn `STARTING` hoặc `STARTED`, chưa phải kết quả cuối.

```text
SYNCHRONOUS

Caller thread:
   |
   +--> JobLauncher.run(job, parameters)
           |
           +--> JobRepository: tạo JobExecution
           +--> Job.execute(...)
                   |
                   +--> Step 1
                   +--> Step 2
                   +--> COMMIT / FAILED / STOPPED
           |
   <-------+ JobExecution với trạng thái sau khi chạy
   |
   +--> Caller xử lý kết quả


ASYNCHRONOUS

Caller thread:                         Worker thread:
   |                                        |
   +--> JobLauncher.run(...)                |
           |                                |
           +--> tạo JobExecution            |
           +--> TaskExecutor.execute(...) --+--> Job.execute(...)
           |                                |       |
   <-------+ trả về sớm                     |       +--> Step 1
   |                                        |       +--> Step 2
   +--> HTTP 202 / executionId              |       +--> trạng thái cuối
   |                                        |
   +--> GET execution status --------------> JobRepository / JobExplorer
```

Khác biệt chính là **thread gọi có phải chờ hay không**. Điều đó **không** làm Spring Batch tự động chạy nhanh hơn, không thay đổi định danh `JobInstance`, không biến job thành một công việc có hàng đợi bền vững và không tự bảo đảm kết quả sẽ sống sót khi JVM bị tắt.

## 2. Bảng so sánh để quyết định thiết kế

| Tiêu chí | Synchronous | Asynchronous |
| --- | --- | --- |
| Thời điểm `JobLauncher.run()` trả về | Thường sau khi job đã kết thúc | Có thể ngay sau khi execution được tạo và tác vụ được giao cho executor |
| Thread của caller | Bị chiếm trong thời gian thực thi | Được giải phóng sớm |
| Trạng thái `JobExecution` khi trả về | Thường đã là trạng thái cuối | Có thể còn `STARTING`/`STARTED` |
| Trả kết quả trong HTTP request | Chỉ phù hợp job rất ngắn và giới hạn timeout rõ | Hợp lý cho job dài: trả `202 Accepted` và execution ID |
| CLI chạy từ cron/Kubernetes Job | Thuận tiện để tiến trình trả exit code khi kết thúc | Cần cơ chế chờ/giám sát riêng, nếu không tiến trình có thể thoát sớm |
| Kiểm soát concurrency | Caller bị chặn, vẫn cần giới hạn số caller | Phải giới hạn worker threads, queue và số job đồng thời |
| Giám sát | Caller có thể nhận kết quả cuối trực tiếp | Cần polling, listener, event hoặc hệ thống giám sát |
| Xử lý lỗi | Xem trạng thái kết thúc ngay sau `run()` | Không được xem launch thành công là job thành công |
| Vòng đời | Phù hợp xử lý một lần rồi kết thúc JVM | Phù hợp service sống lâu hoặc executor được quản lý bền vững |
| Độ bền khi JVM crash | Job vẫn có rủi ro crash giữa chừng | Rủi ro tương tự; in-process queue không phải durable queue |

**Quy tắc thực dụng:** Nếu một tiến trình được scheduler gọi để làm đúng một công việc rồi thoát, synchronous thường dễ vận hành hơn. Nếu một HTTP API phải trả kết quả nhanh trong khi job chạy vài phút hoặc vài giờ, asynchronous thường phù hợp hơn — nhưng chỉ khi có `JobRepository` bền vững, cơ chế theo dõi, giới hạn tải và quy trình recovery.

## 3. Hiểu `JobLauncher`, `JobRepository` và `JobExecution`

Trong Spring Batch, việc launch không đơn giản là gọi một phương thức Java bất kỳ:

```java
JobExecution execution = jobLauncher.run(job, jobParameters);
```

Thông thường launcher:

1. Làm việc với `JobRepository` để xác định `JobInstance` dựa trên **tên job + identifying `JobParameters`**.
2. Kiểm tra các điều kiện như instance đã hoàn thành, execution đang chạy hoặc job có được restart hay không.
3. Tạo và lưu `JobExecution`.
4. Đưa công việc thực thi `Job.execute(...)` tới `TaskExecutor` được cấu hình.
5. Trả về `JobExecution` cho caller hoặc truyền ra exception nếu không thể launch.

Trong Spring Batch 5, class thường dùng là:

```java
org.springframework.batch.core.launch.support.TaskExecutorJobLauncher
```

Class này có thể hoạt động theo cả hai cách tùy `TaskExecutor`. Với `SyncTaskExecutor`, công việc được thực hiện trong thread gọi; với `ThreadPoolTaskExecutor`, công việc được dispatch sang thread của pool.

### 3.1. Phân biệt ba khái niệm

| Thành phần | Vai trò | Hệ quả khi restart |
| --- | --- | --- |
| `Job` | Định nghĩa pipeline xử lý, gồm các `Step` | Định nghĩa thường được dùng lại |
| `JobInstance` | Một công việc logic được xác định bởi job name và identifying parameters | Giữ nguyên nếu restart đúng instance |
| `JobExecution` | Một lần thử chạy instance, có ID và trạng thái riêng | Restart tạo execution mới trong cùng instance |

Ví dụ:

```text
Job name: dailyReportJob
Identifying parameters:
    businessDate=2026-11-16
    region=VN

JobInstance A
  ├── JobExecution #1001: FAILED
  └── JobExecution #1002: COMPLETED (restart)
```

Việc launch synchronous hay asynchronous **không thay đổi quy tắc định danh này**. Cùng identifying parameters có thể bị từ chối khi instance đã `COMPLETED` (`JobInstanceAlreadyCompleteException`) hoặc đang chạy (`JobExecutionAlreadyRunningException`); với instance `FAILED`, có thể restart nếu job cho phép.

### 3.2. `JobExecution` trả về không phải lời hứa thành công

Với synchronous launcher:

```java
JobExecution execution = syncLauncher.run(job, parameters);

if (execution.getStatus() == BatchStatus.COMPLETED) {
    // Job đã hoàn thành theo tiêu chí Spring Batch.
} else {
    // Job đã kết thúc nhưng chưa thành công, hoặc cần xem trạng thái.
}
```

Với asynchronous launcher:

```java
JobExecution execution = asyncLauncher.run(job, parameters);

long executionId = execution.getId();
BatchStatus observedStatus = execution.getStatus();

// observedStatus có thể là STARTING hoặc STARTED.
// Không kết luận job đã thành công tại đây.
```

Một synchronous job có thể **trả về `JobExecution` mang trạng thái `FAILED` mà không ném exception cho caller**. Ngoài ra, những lỗi khi tạo execution, xác thực tham số hoặc kiểm tra điều kiện chạy có thể phát sinh exception trước khi job được bắt đầu. Do đó cả hai đường đi đều cần xử lý **exception khi launch** và **trạng thái kết quả job**.

## 4. Cấu hình synchronous launcher trong Spring Batch 5

Một launcher rõ ràng có thể dùng `SyncTaskExecutor`:

```java
package com.example.batch.launch;

import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SyncTaskExecutor;

@Configuration
public class SyncLaunchConfig {

    @Bean("syncJobLauncher")
    JobLauncher syncJobLauncher(JobRepository jobRepository)
            throws Exception {

        TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
        launcher.setJobRepository(jobRepository);
        launcher.setTaskExecutor(new SyncTaskExecutor());
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

`SyncTaskExecutor` thực hiện tác vụ trong thread gọi, nên sau `run()` thông thường job đã kết thúc. Ví dụ tạo một bean tên `syncJobLauncher`; trong ứng dụng có nhiều bean `JobLauncher`, cần dùng `@Qualifier` khi inject để tránh nhầm launcher.

Trong dự án Spring Boot chỉ dùng mặc định, thường **không cần tự định nghĩa launcher**. Spring Batch/Spring Boot đã cấu hình hạ tầng từ `JobRepository`; hãy xác định cơ chế launch thực tế trước khi tạo bean bổ sung. Đoạn cấu hình trên hữu ích khi muốn chủ động quản lý hai chế độ launch cạnh nhau.

### 4.1. Gọi synchronous trong một service

```java
package com.example.batch.launch;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class SyncDailyReportService {

    private final JobLauncher launcher;
    private final Job dailyReportJob;

    public SyncDailyReportService(
            @Qualifier("syncJobLauncher") JobLauncher launcher,
            @Qualifier("dailyReportJob") Job dailyReportJob) {
        this.launcher = launcher;
        this.dailyReportJob = dailyReportJob;
    }

    public JobExecution runForDate(String businessDate) throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("region", "VN", true)
                .toJobParameters();

        JobExecution execution = launcher.run(dailyReportJob, params);
        if (execution.getStatus() != BatchStatus.COMPLETED) {
            // Caller quyết định xử lý FAILED/STOPPED theo hợp đồng.
            // Không nên chỉ dựa vào việc run() không ném exception.
        }
        return execution;
    }
}
```

Method trên trả `JobExecution` để caller tự xem trạng thái/ID. Trong ứng dụng sản xuất, nên validate ngày, region, quyền gọi job và danh tính đầu vào trước khi tạo parameters. `businessDate` dạng chuỗi ở đây là ví dụ; có thể chuẩn hóa bằng `LocalDate.parse(...)` và định dạng ISO.

## 5. Cấu hình asynchronous launcher bằng thread pool

Một cấu hình có kiểm soát thường dùng `ThreadPoolTaskExecutor`, không tạo thread mới vô hạn cho mỗi request:

```java
package com.example.batch.launch;

import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncLaunchConfig {

    @Bean("batchLaunchExecutor")
    ThreadPoolTaskExecutor batchLaunchExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("batch-launch-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        executor.initialize();
        return executor;
    }

    @Bean("asyncJobLauncher")
    JobLauncher asyncJobLauncher(
            JobRepository jobRepository,
            @Qualifier("batchLaunchExecutor") TaskExecutor executor)
            throws Exception {

        TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
        launcher.setJobRepository(jobRepository);
        launcher.setTaskExecutor(executor);
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

Cấu hình này đặt giới hạn ví dụ: **2 core threads, tối đa 4 threads, queue capacity 20**. Với queue có dung lượng dương, `ThreadPoolTaskExecutor` thường ưu tiên xếp vào hàng đợi sau khi core threads bận, rồi mới tăng số thread tới max khi queue đầy. Vì vậy `maxPoolSize=4` không có nghĩa luôn có bốn job chạy đồng thời.

`setWaitForTasksToCompleteOnShutdown(true)` và `setAwaitTerminationSeconds(60)` thể hiện ý định dọn dẹp executor khi application context đóng. Chúng **không thể bảo đảm một batch dài nhiều giờ luôn hoàn tất** nếu tiến trình bị kill, container hết graceful shutdown period hoặc máy chủ mất điện. Cần phối hợp chính sách shutdown, timeout hạ tầng, `JobRepository` và recovery.

### 5.1. Async launch không tự động tương đương durable queue

```text
POST /launch
     |
     v
TaskExecutorJobLauncher
     |
     +--> JobRepository tạo JobExecution
     |
     +--> ThreadPoolTaskExecutor queue (trong JVM)
                   |
                   +--> Worker thread chạy job
```

Queue của `ThreadPoolTaskExecutor` là **bộ nhớ trong tiến trình**. Nếu JVM chết trước khi một job trong queue được xử lý, request đã trả `202` có thể không dẫn tới một execution hoàn chỉnh. Metadata của `JobExecution` đã tạo cũng có thể còn trạng thái `STARTING`/`STARTED` cần được đối soát theo quy trình vận hành.

Nếu hệ thống yêu cầu **nhận yêu cầu một lần và bảo đảm xử lý dù JVM restart**, cần thêm một cơ chế điều phối bền vững, ví dụ message broker/queue có ack và idempotency, Quartz persistent scheduler được cấu hình phù hợp, Kubernetes Job hoặc một bảng lệnh điều phối có worker nhận việc. `JobRepository` giữ lịch sử thực thi batch nhưng **không thay thế durable submission queue**.

## 6. Nên chọn cách nào cho từng điểm kích hoạt?

### 6.1. Command line, cron và Kubernetes Job: thường chọn synchronous

Một scheduler ngoài thường gọi executable JAR, đợi tiến trình kết thúc và đọc process exit code:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 \
  region=VN

echo "Exit code: $?"
```

Với Spring Boot, `--spring.batch.job.name` là application property, còn `businessDate=...` và `region=...` là **non-option arguments** truyền thành `JobParameters` trong cơ chế startup job của Boot 3. Trong ví dụ này, startup runner phải được bật, thường qua `spring.batch.job.enabled=true`.

Khi job chạy đồng bộ và ứng dụng batch có vòng đời một lần, scheduler có thể liên hệ việc kết thúc JVM với việc kết thúc job. Tuy vậy, **mã thoát JVM phải được ánh xạ từ kết quả batch** nếu cần; `BatchStatus.FAILED` không tự bảo đảm exit code khác 0 trong mọi cấu hình. Có thể dùng `ExitCodeGenerator` và `SpringApplication.exit(context)` theo chính sách của ứng dụng.

Nếu thay launcher của startup runner bằng asynchronous launcher nhưng tiến trình JVM kết thúc ngay sau khi `SpringApplication.run(...)` trả về, có nguy cơ job chưa hoàn tất, output chưa commit và mã thoát scheduler không phản ánh kết quả. Với CLI dùng cron hoặc Kubernetes Job, **không chuyển sang asynchronous chỉ để làm lệnh Java trả về nhanh**.

### 6.2. REST API chạy job dài: thường chọn asynchronous

Một HTTP request nên có timeout và thời gian giữ connection ngắn. Nếu job chạy 45 phút, không nên giữ một request chờ tới khi hoàn thành:

```text
Client POST /batch/jobs/daily-report
      |
      | Launch accepted
      v
HTTP 202 Accepted
Location: /batch/executions/1003
Body: { "executionId": 1003, "status": "STARTING" }

Client GET /batch/executions/1003
      |
      v
HTTP 200 OK
Body: { "executionId": 1003, "status": "STARTED" }

Client GET /batch/executions/1003
      |
      v
HTTP 200 OK
Body: { "executionId": 1003, "status": "COMPLETED" }
```

`202 Accepted` có nghĩa **yêu cầu launch đã được chấp nhận theo hợp đồng API**, không có nghĩa job chắc chắn thành công. Client cần tra trạng thái cuối hoặc đăng ký callback/event ở tầng ứng dụng. Nếu submit không thể được đưa vào executor vì quá tải, API cần trả lỗi/response phù hợp, không tạo một kết quả “đã xong” giả.

### 6.3. Lịch nội bộ trong service: phụ thuộc vòng đời

Nếu một service sống lâu có `@Scheduled`, có thể dùng async để không chiếm thread scheduler, **nhưng** vẫn cần giới hạn concurrency, stop policy, thread pool riêng và xử lý job đang chạy khi service deploy lại.

Nếu scheduler nội bộ được thiết kế để chỉ có một job tại một thời điểm và cần biết kết quả trước khi chuyển sang job sau, synchronous có thể đơn giản hơn. Khi dùng `@Scheduled` để tự launch qua `JobLauncher`, nên cấu hình `spring.batch.job.enabled=false` để không tự chạy job thêm lần nữa lúc Boot startup.

### 6.4. Orchestrator chạy nhiều job phụ thuộc nhau

Ví dụ:

```text
importOrdersJob ---> reconcileJob ---> publishJob
```

Nếu orchestration đợi import thành công rồi mới chạy reconcile, synchronous invocation có thể diễn đạt luồng rõ ràng khi mỗi lệnh do orchestrator quản lý. Với async, orchestrator phải nhận execution ID, **chờ trạng thái cuối**, xử lý timeout/cancel/fail rồi mới chạy dependency. Chỉ “launch xong” không đủ để kết luận dependency đã được thỏa mãn.

## 7. Thiết kế REST API asynchronous với Spring Batch

Một API mẫu nên tách **submit** và **query status**; dữ liệu trả về chỉ gồm những trường cần thiết, không expose toàn bộ `JobExecution`, `JobParameters` hoặc exception message.

### 7.1. API contract

```text
POST /batch/jobs/daily-report
Content-Type: application/json

{
  "businessDate": "2026-11-16",
  "region": "VN"
}

202 Accepted
Location: /batch/executions/1003

{
  "executionId": 1003,
  "batchStatus": "STARTING"
}
```

Kiểm tra trạng thái:

```text
GET /batch/executions/1003

200 OK
{
  "executionId": 1003,
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED"
}
```

Giá trị JSON là minh họa. `exitCode` ở đây là **`ExitStatus` của Spring Batch**, không phải mã thoát JVM. Với một job còn đang chạy, `exitCode` có thể là trạng thái chưa hoàn tất hoặc giá trị mặc định; client không nên sử dụng nó như kết quả cuối trước khi trạng thái terminal.

### 7.2. Controller minh họa

```java
package com.example.batch.api;

import java.net.URI;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/batch")
public class DailyReportBatchController {

    public record LaunchRequest(String businessDate, String region) {}
    public record LaunchResponse(Long executionId, String batchStatus) {}
    public record ExecutionResponse(
            Long executionId, String batchStatus, String exitCode) {}

    private final JobLauncher launcher;
    private final Job dailyReportJob;
    private final JobExplorer jobExplorer;

    public DailyReportBatchController(
            @Qualifier("asyncJobLauncher") JobLauncher launcher,
            @Qualifier("dailyReportJob") Job dailyReportJob,
            JobExplorer jobExplorer) {
        this.launcher = launcher;
        this.dailyReportJob = dailyReportJob;
        this.jobExplorer = jobExplorer;
    }

    @PostMapping("/jobs/daily-report")
    public ResponseEntity<LaunchResponse> launch(
            @RequestBody LaunchRequest request) throws Exception {

        if (request == null || request.businessDate() == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Missing businessDate");
        }

        String businessDate;
        try {
            businessDate =
                    LocalDate.parse(request.businessDate()).toString();
        } catch (DateTimeParseException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "businessDate must be yyyy-MM-dd");
        }

        if (!"VN".equals(request.region())) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Unsupported region");
        }

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("region", request.region(), true)
                .toJobParameters();

        JobExecution execution;
        try {
            execution = launcher.run(dailyReportJob, parameters);
        } catch (JobExecutionAlreadyRunningException
                | JobInstanceAlreadyCompleteException
                | JobRestartException ex) {
            // Hợp đồng demo chọn 409; API thật có thể trả về ID cũ.
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "An execution for this business request conflicts");
        } catch (JobParametersInvalidException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid job parameters");
        }

        long id = execution.getId();
        URI location = URI.create("/batch/executions/" + id);

        return ResponseEntity.accepted()
                .location(location)
                .body(new LaunchResponse(
                        id, execution.getStatus().name()));
    }

    @GetMapping("/executions/{id}")
    public ExecutionResponse status(@PathVariable long id) {
        JobExecution execution = jobExplorer.getJobExecution(id);
        if (execution == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Execution not found");
        }
        return new ExecutionResponse(
                execution.getId(),
                execution.getStatus().name(),
                execution.getExitStatus().getExitCode());
    }
}
```

Controller là **mẫu kiến trúc**, giả định ứng dụng có `spring-boot-starter-web`, `JobExplorer`, bean `Job` tên `dailyReportJob`, cùng `asyncJobLauncher` ở phần 5. Cần đặt `spring.batch.job.enabled=false` khi service API chủ động điều khiển launch, để Boot không tự chạy job tại startup. Các lớp business job, datasource, security và audit chưa được triển khai trong ví dụ.

Một số điểm thiết kế:

- **Xác thực và phân quyền** trước khi được launch job. API không nên cho mọi client tự chọn job hoặc truyền SQL/path tùy ý.
- **Idempotency:** nếu client timeout sau khi server đã nhận request, client có thể gửi lại. Cần chính sách request idempotency key hoặc tra lại execution đang tồn tại; ví dụ trên trả `409` cho một số trường hợp.
- **Validation:** chuẩn hóa `businessDate` và `region` trước khi đưa vào identifying `JobParameters`.
- **Không đưa exception message nguyên văn** vào HTTP response hoặc log công khai; lỗi JDBC/HTTP có thể chứa payload nhạy cảm.
- **Không trả 200/COMPLETED sau khi mới submit.** `run()` async chỉ cho biết yêu cầu đã được dispatch theo cơ chế launcher.
- **Truy vấn trạng thái từ repository**, không giữ `JobExecution` mutable trong một `Map` static nội bộ rồi coi đó là nguồn dữ liệu duy nhất.

### 7.3. HTTP `202` không đồng nghĩa durable acceptance

Với ví dụ in-process thread pool, `202` xác nhận launcher đã nhận yêu cầu ở thời điểm trả lời, **không cam kết queue sẽ sống sót sau crash**. Nếu yêu cầu kinh doanh đòi bảo đảm nhận lệnh bền vững, hãy ghi yêu cầu vào bảng submission/outbox hoặc broker với transaction và idempotency, để một worker xử lý theo trạng thái bền vững. Khi ấy API mới có thể công bố một hợp đồng “durably accepted” đúng nghĩa.

## 8. Trạng thái job phải được quan sát độc lập với launch

Các trạng thái `BatchStatus` thường gặp:

| Trạng thái | Ý nghĩa | Cách client hiểu |
| --- | --- | --- |
| `STARTING` | Execution đã được tạo, đang chuẩn bị chạy | Đã submit/đang chờ bắt đầu; chưa có kết quả |
| `STARTED` | Job đang thực thi | Tiếp tục theo dõi |
| `STOPPING` | Có yêu cầu dừng | Chưa dừng hẳn |
| `STOPPED` | Job đã dừng | Có thể xem điều kiện restart |
| `COMPLETED` | Job hoàn thành theo flow | Kiểm tra thêm điều kiện nghiệp vụ/publish nếu có |
| `FAILED` | Job thất bại | Kiểm tra lỗi và đường phục hồi |
| `ABANDONED` | Execution bị đánh dấu bỏ dở | Cần xử lý theo quy trình vận hành |
| `UNKNOWN` | Không xác định được trạng thái tin cậy | Không tự coi là thành công |

**`BatchStatus` khác `ExitStatus`**: `ExitStatus` có thể mang exit code nghiệp vụ, ví dụ một flow có xử lý skip được chấp nhận. Cả hai lại khác mã thoát của **tiến trình JVM**, được scheduler/OS sử dụng.

Với asynchronous launch, có thể lấy execution ID và đọc trạng thái từ `JobExplorer`:

```java
JobExecution current = jobExplorer.getJobExecution(executionId);

if (current == null) {
    // Execution không tồn tại hoặc không truy cập được.
} else if (current.getStatus().isRunning()) {
    // Theo dõi tiếp; không coi là thành công.
} else {
    // Đọc trạng thái cuối và outcome nghiệp vụ.
}
```

Trong trường hợp crash, metadata có thể còn `STARTING`/`STARTED` dù process đã chết. Vì thế `isRunning()` từ metadata **không phải heartbeat sống** của JVM. Một monitor bền vững có thể kết hợp trạng thái execution, heartbeat/lease của worker và thời gian cập nhật cuối, sau đó cảnh báo các execution bị mắc kẹt để xử lý có kiểm soát.

### 8.1. Dùng listener cho sự kiện hoàn tất

Một `JobExecutionListener` có thể báo kết quả cuối và phát event sau khi job kết thúc:

```java
package com.example.batch.launch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class ExecutionResultLogger implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ExecutionResultLogger.class);

    @Override
    public void afterJob(JobExecution execution) {
        log.info(
                "event=batch_finished execution_id={} job={} "
                + "status={} exit_code={}",
                execution.getId(),
                execution.getJobInstance().getJobName(),
                execution.getStatus(),
                execution.getExitStatus().getExitCode());
    }
}
```

Gắn listener vào `JobBuilder` khi định nghĩa job:

```java
return new JobBuilder("dailyReportJob", jobRepository)
        .listener(new ExecutionResultLogger())
        .start(reportStep)
        .build();
```

Listener chạy trong đường thực thi job, nhưng **ghi log hoặc gửi event không tự bảo đảm sự kiện được giao thành công**. Nếu downstream cần một notification chắc chắn, nên sử dụng outbox/audit state bền vững và cơ chế retry thông báo riêng. Khi exception trong listener, phải cân nhắc hệ quả tới job và transaction.

## 9. Concurrency và giới hạn tài nguyên khi async

Async launcher giúp caller trả về sớm, nhưng không có nghĩa hệ thống có thể chạy bao nhiêu job cũng được. Giả sử mỗi job dùng bốn worker thread trong step, có một datasource pool tối đa 12 connections, còn launcher cho chạy bốn job cùng lúc:

```text
4 asynchronous JobExecutions
        |
        +--> Job A: 4 chunk workers
        +--> Job B: 4 chunk workers
        +--> Job C: 4 chunk workers
        +--> Job D: 4 chunk workers

Possible business connection demand: ~16
Shared pool limit: 12
```

Đó là **ước lượng** nếu mỗi worker có lúc cần một connection; reader cursor, `JobRepository` hoặc writer có thể dùng thêm connection. Khi pool cạn, job có thể chờ hoặc lỗi, dù API vẫn trả `202` nhanh.

### 9.1. Thread pool của launcher và executor bên trong step là hai thứ khác

| Thành phần | Nó giới hạn gì? |
| --- | --- |
| `batchLaunchExecutor` | Số `JobExecution` có thể được chạy đồng thời trong JVM |
| `TaskExecutor` của multi-threaded step | Số chunk/worker bên trong **một** step |
| Partition handler/executor | Số partition được xử lý đồng thời |
| HikariCP datasource pool | Số connection JDBC có thể mượn đồng thời |
| Scheduler/orchestrator | Số job request được phát và chạy chồng giữa các process |

Nếu mỗi job tự mở thêm thread pool, số lượng thread và connection có thể tăng theo phép nhân. Không dùng `SimpleAsyncTaskExecutor` không giới hạn trong production chỉ để API không bị chặn; nên dùng bounded pool/queue, metric và backpressure.

### 9.2. Khi executor/queue đầy

Một launcher có thể không dispatch được task vì pool đã quá tải hoặc executor đang shutdown. Trong thiết kế API:

- Không trả một response giả rằng job đã hoàn thành.
- Phân biệt **không nhận được yêu cầu** với **đã tạo execution nhưng không dispatch được**.
- Ghi event vận hành và đối soát metadata của các execution `STARTING` quá lâu.
- Áp dụng rate limiting, capacity check hoặc queue bền vững.
- Có thể trả `429 Too Many Requests` hoặc `503 Service Unavailable` tùy hợp đồng API, với retry/backoff cho client.

**Lưu ý tình huống khó:** `JobRepository` có thể đã tạo `JobExecution` trước khi `TaskExecutor` từ chối công việc. Vì vậy không thể chỉ nhìn HTTP error mà kết luận chắc chắn “không có execution nào đã được tạo”. Cần cơ chế recovery và đối soát các execution ở trạng thái chưa kết thúc.

### 9.3. Quản lý tính trùng lặp

Nếu hai request đồng thời gửi:

```text
jobName=dailyReportJob
businessDate=2026-11-16
region=VN
```

Spring Batch sử dụng identifying parameters để ràng buộc `JobInstance` và chống một số trường hợp chạy trùng trong `JobRepository`. Tuy nhiên, việc dùng **run ID ngẫu nhiên cho mỗi HTTP request** sẽ tạo ra nhiều instance khác nhau, có thể xử lý cùng dữ liệu lặp lại. Muốn idempotent submission, phải có khóa yêu cầu/batch rõ ràng và chính sách xử lý duplicate (trả lại execution ID cũ, conflict hoặc cho phép run mới có chủ đích).

Không nên coi các exception `JobExecutionAlreadyRunningException`/`JobInstanceAlreadyCompleteException` là lỗi hệ thống nghiêm trọng tự động cần retry vô hạn. Chúng thường phản ánh quy tắc định danh và trạng thái của một instance.

## 10. Transaction và context khi chạy bất đồng bộ

### 10.1. Không mang transaction của HTTP thread sang batch thread

Giả sử HTTP service ghi một row rồi gọi async job trong cùng phương thức `@Transactional`:

```text
HTTP thread:
    begin transaction
    insert batch_request
    asyncLauncher.run(job, params)
    commit transaction (sau đó)

Worker thread:
    begin job
    read batch_request -> có thể chưa thấy row vừa insert
```

Transaction context của Spring thường ràng buộc với thread. **Async worker không tự kế thừa transaction chưa commit của caller**. Vì vậy không nên launch ngay bên trong một transaction rồi mặc định worker nhìn thấy dữ liệu đã được ghi.

Lựa chọn an toàn hơn có thể là:

- Ghi request bền vững, commit trước, sau đó dispatch job.
- Sử dụng transactional outbox hoặc event sau commit, có cơ chế retry để không mất yêu cầu nếu process crash giữa commit và dispatch.
- Cho job đọc đầu vào đã được commit/đóng snapshot, không phụ thuộc vào request object mutable của HTTP thread.

### 10.2. MDC, security context và request scope

Thông tin trong thread-local như MDC correlation ID, security context hoặc request-scoped bean **không tự truyền chính xác** sang worker thread. Nếu cần `traceId`, hãy truyền một giá trị đã được phê duyệt qua JobParameters non-identifying hoặc cơ chế context propagation được cấu hình phù hợp; trong worker cần dọn MDC trong `finally` để tránh lẫn log giữa các job.

Không truyền `HttpServletRequest`, entity đang gắn với persistence context của request thread, đối tượng transaction-bound hoặc reference tới context sẽ bị dispose cho một job chạy nền. Dữ liệu dài hạn cần được lưu thành identity/snapshot bền vững và nạp lại trong worker.

### 10.3. Không nhầm task-level async với job-level async

- **Async job launch:** `JobLauncher` đưa **toàn bộ job** vào executor; caller có thể trả về sớm.
- **Multi-threaded step:** một step xử lý các chunk đồng thời; caller vẫn có thể launch synchronous rồi chờ job kết thúc.
- **Async processor/writer:** xử lý bất đồng bộ một số item trong step; khác với việc `JobLauncher.run()` có block hay không.
- **Partitioning/remote chunking:** phân tán phần việc, nhưng vẫn cần quyết định cách orchestration chờ kết quả.

Một job có launcher synchronous vẫn có thể chạy các step song song, và một job launch async vẫn có thể xử lý tuần tự từng item. Hai trục thiết kế này **độc lập**.

## 11. Vòng đời ứng dụng và graceful shutdown

Với service HTTP sống lâu, async job thường chạy cùng JVM với web server. Khi deploy lại:

1. Ngừng nhận yêu cầu launch mới.
2. Đặt readiness thích hợp để load balancer ngừng gửi yêu cầu mới.
3. Cho executor/job đang chạy cơ hội kết thúc, hoặc gửi stop request theo hợp đồng.
4. Chờ trong giới hạn shutdown của container/orchestrator.
5. Với job chưa hoàn thành, dùng metadata và chính sách restart/recovery sau khi service hoạt động trở lại.

Các cấu hình `awaitTerminationSeconds` hoặc Kubernetes `terminationGracePeriodSeconds` là **giới hạn thời gian chờ**, không phải bảo đảm hoàn tất một job kéo dài hàng giờ. Nếu job cần sống độc lập với vòng đời deploy của API, kiến trúc phù hợp hơn là **API ghi durable request → worker batch riêng nhận việc → persist status**.

### 11.1. Stop một async job

Spring Batch hỗ trợ `JobOperator` để yêu cầu dừng một execution khi có quyền quản trị:

```java
boolean stopRequested = jobOperator.stop(executionId);
```

Điều này là **yêu cầu dừng hợp tác**, không phải một lệnh kill thread tức khắc. Với tasklet đang block trong I/O hoặc writer không có timeout, job có thể không dừng ngay. Cần kiểm tra trạng thái thực tế về `STOPPED`, xử lý transaction đang mở và phân biệt **stop** với **restart** sau khi đã sửa vấn đề.

API dừng job phải được phân quyền chặt chẽ, có audit và tránh cho người dùng gọi tùy ý trên execution không thuộc phạm vi được phép.

## 12. Xử lý lỗi theo hai giai đoạn

Khi launch async, phải phân biệt:

**Giai đoạn A — Submission/launch:** caller gọi `JobLauncher.run(...)`. Các lỗi có thể gồm tham số sai, job không tồn tại trong context, trùng instance, repository không tạo được execution hoặc executor từ chối task.

**Giai đoạn B — Execution:** job đã bắt đầu thực thi và có thể thất bại ở reader, processor, writer, transaction, validation hoặc downstream API.

```text
POST /launch
    |
    +-- validation error --------> HTTP 400, không chạy job
    +-- already running ---------> HTTP 409 hoặc idempotent lookup
    +-- system cannot accept ----> HTTP 503/429 theo policy
    |
    +-- accepted ---------------> HTTP 202 + executionId
                                      |
                                      v
                                  JobExecution
                                   |       |
                               COMPLETED  FAILED/STOPPED
                                   |       |
                              publish?   alert/restart?
```

Một HTTP request thành công chỉ thể hiện trạng thái của **giai đoạn A**. Nếu job `FAILED` sau 10 phút, server không thể đổi lại response `202` đã trả trước đó. Vì vậy cần status endpoint, notification, dashboard hoặc callback có tính bền vững.

Với synchronous launch, hai giai đoạn diễn ra trong cùng lời gọi nên caller có thể nhận outcome ngay. Nhưng nếu synchronous job quá lâu, timeout HTTP/proxy có thể đóng request **trong khi server vẫn còn chạy job**. Client không được mặc định request timeout nghĩa là job chưa chạy và submit lại một instance mới.

## 13. Khi nào cần kiến trúc tách riêng batch worker?

Nếu job có những đặc điểm sau, không nên chỉ đổi `SyncTaskExecutor` thành `ThreadPoolTaskExecutor` rồi coi như đã giải quyết vấn đề:

- Job chạy hàng giờ hoặc tiêu thụ nhiều CPU/memory, ảnh hưởng latency của API.
- Có nhiều client gửi job cùng lúc, cần quota, priority queue và backpressure.
- Cần chịu được restart/deploy API mà không làm mất công việc đã nhận.
- Cần scale worker riêng với web server.
- Cần audit request, retry và trạng thái bền vững xuyên nhiều hệ thống.
- Có workflow nhiều job phụ thuộc hoặc deadline nghiêm ngặt.

Kiến trúc gợi ý:

```text
Client
  |
  | POST /batch-requests  (idempotency key)
  v
API service
  |
  +--> Durable request store / outbox
                  |
                  v
            Scheduler / Queue
                  |
                  v
           Dedicated batch worker
                  |
                  +--> JobLauncher (thường synchronous trong worker)
                  +--> JobRepository
                  +--> Result / publish state
                  |
                  v
             Status/notification
                  |
                  v
                Client
```

Ở tầng API, xử lý có vẻ “asynchronous” với client vì request kết thúc sớm. Nhưng **bên trong worker batch, synchronous launch có thể là lựa chọn tốt nhất**: worker chỉ hoàn thành message/command khi job đạt trạng thái được chấp nhận. Đây là một phân biệt kiến trúc quan trọng: **async với caller bên ngoài không nhất thiết phải async trong chính `JobLauncher`**.

Durable queue cần hợp đồng ack, lease/visibility timeout, dead-letter, deduplication/idempotency và at-least-once delivery phù hợp. `JobRepository` ghi lịch sử batch nhưng không tự thực hiện tất cả chức năng đó.

## 14. Kiểm thử lựa chọn synchronous và asynchronous

### 14.1. Kiểm thử hành vi blocking bằng latch

Đo bằng `Thread.sleep(1000)` là cách dễ gây test flaky trên CI. Thay vào đó, dùng **`CountDownLatch`** để biết job đã bắt đầu và chủ động cho nó kết thúc.

Một tasklet dùng trong fixture test có thể có dạng:

```java
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

Tasklet blockingTasklet = (contribution, chunkContext) -> {
    started.countDown();
    if (!release.await(10, TimeUnit.SECONDS)) {
        throw new IllegalStateException("TEST_RELEASE_TIMEOUT");
    }
    return RepeatStatus.FINISHED;
};
```

Đoạn trên là **fixture**, cần import `java.util.concurrent.CountDownLatch`, `TimeUnit`, `Tasklet` và `RepeatStatus`. Latch chỉ dành cho test, không nên dùng làm cách dừng một job production.

Hai kịch bản:

| Kịch bản | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Synchronous | Gọi launcher từ một test thread khác, chờ `started`, chưa `release` | Future của lời gọi `run()` **chưa hoàn tất** |
| Asynchronous | Gọi launcher async, chờ `started`, chưa `release` | `run()` có thể đã trả `JobExecution`; job vẫn đang chạy |
| Sau release | `release.countDown()` | Execution cuối chuyển `COMPLETED` |
| Job ném exception | Tasklet lỗi có chủ đích | Đọc `FAILED` từ repository, không suy ra chỉ từ việc gọi launch |

Đối với sync test, gọi `run()` trong một `ExecutorService` riêng để test thread có thể điều khiển latch:

```java
Future<JobExecution> submitted = testExecutor.submit(
        () -> syncLauncher.run(testJob, params));

assertThat(started.await(5, TimeUnit.SECONDS)).isTrue();
assertThat(submitted.isDone()).isFalse();

release.countDown();
JobExecution finished = submitted.get(5, TimeUnit.SECONDS);
assertThat(finished.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

Đoạn code là **phần trích test**: `testExecutor`, `syncLauncher`, `testJob`, `params`, `started`, `release`, AssertJ và các import cần có trong class test. Dùng `try/finally` để release latch và shutdown executor ngay cả khi assertion lỗi, tránh khiến test suite treo. Mỗi test cần identifying parameters khác nhau hoặc làm sạch metadata **chỉ trong database test riêng**.

Đối với async test, sau `JobExecution initial = asyncLauncher.run(testJob, params)`, có thể xác nhận lời gọi trả về trước khi `release` được mở, sau đó đọc `JobExplorer.getJobExecution(initial.getId())` cho tới trạng thái cuối với timeout hữu hạn. Không nên assert một trạng thái trung gian **chính xác bằng `STARTING`** vì scheduler có thể chuyển sang `STARTED` rất nhanh.

### 14.2. Test không được mất job khi submit trùng

Các request cùng `jobName` và identifying parameters cần một outcome được xác định rõ:

- Nếu đang chạy: trả conflict hoặc liên kết tới execution hiện tại.
- Nếu đã hoàn thành: không tạo job mới ngoài ý muốn.
- Nếu đã fail: restart nếu job restartable và chính sách cho phép.
- Nếu client retry vì HTTP timeout: không tạo instance mới bằng `run.id` ngẫu nhiên.

Test có thể gửi hai request đồng thời bằng latch và đếm số `JobInstance`/`JobExecution` trong `JobRepository`. Kỳ vọng phải phù hợp với thiết kế idempotency của ứng dụng, không chỉ dựa vào mã HTTP.

### 14.3. Test trạng thái cuối và lỗi thực thi

Với async:

1. Submit job, lấy execution ID.
2. Poll status cho đến khi trạng thái terminal hoặc hết timeout test.
3. Với fixture thành công, xác nhận `COMPLETED`.
4. Với fixture ném exception ở processor/writer, xác nhận `FAILED` và status API không trả `COMPLETED`.
5. Kiểm tra log/metric có execution ID, không có payload nhạy cảm.
6. Kiểm tra listener/notification phát sự kiện cuối đúng quy tắc, không gửi khi chỉ `STARTING`.

Nếu cần kiểm chứng khả năng phục hồi sau crash, test tích hợp phải khởi động lại process/worker và đối soát metadata/queue. Unit test của `TaskExecutorJobLauncher` không thể chứng minh in-memory queue có tính bền vững.

### 14.4. Kiểm thử capacity và shutdown

Một test tải có thể cấu hình executor nhỏ (`core=1`, `max=1`, queue giới hạn), giữ một job bằng latch và submit thêm nhiều request. Cần kiểm tra:

- Request bị từ chối được trả mã phù hợp, không báo thành công giả.
- Không có job chạy vượt giới hạn đã thiết kế.
- Không có execution `STARTING` bị bỏ quên mà không có cơ chế phát hiện.
- Dừng context theo chính sách đã định không làm mất dấu công việc.
- Số connection DB, worker thread và queue depth không tăng vô hạn.

Đây là kiểm thử **tầng điều phối**, khác với performance test throughput của một chunk step.

## 15. Các lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng synchronous launcher cho job 2 giờ trong HTTP request | HTTP timeout, giữ request thread lâu, client dễ submit lại | Trả `202`, theo dõi bằng execution ID hoặc dùng worker riêng |
| Dùng async launcher trong CLI rồi thoát JVM | Job có thể chưa kết thúc, exit code không phản ánh kết quả | CLI synchronous hoặc chờ completion có kiểm soát |
| Coi `JobLauncher.run()` async trả về là job thành công | Báo cáo sai kết quả | Theo dõi `JobExecution` tới trạng thái cuối |
| Dùng `SimpleAsyncTaskExecutor` không kiểm soát số task | Nhiều thread/job đồng thời, quá tải DB | Bounded executor và backpressure |
| Tạo `run.id` ngẫu nhiên cho mỗi request retry | Tạo nhiều `JobInstance` xử lý trùng dữ liệu | Stable identifying parameters và idempotent submission |
| Dùng chỉ một `Map` in-memory lưu trạng thái | Mất dấu job khi JVM restart | `JobRepository` bền vững, status qua `JobExplorer` |
| Coi queue của executor là durable queue | Request accepted có thể mất khi process crash | Durable command store/queue hoặc orchestrator |
| Không xử lý task rejection | Execution mắc kẹt, API trả trạng thái sai | Giới hạn tải, trả lỗi và đối soát metadata |
| Truyền entity/request scope sang thread async | Context đã đóng, dữ liệu chưa commit hoặc race condition | Lưu snapshot bền vững và nạp lại trong worker |
| Không giới hạn executor theo pool DB | Hàng loạt job chờ JDBC connection | Tính tổng concurrency và connection budget |
| Ghi exception message ra status API | Lộ SQL, payload hoặc thông tin nhạy cảm | Trả error code đã kiểm duyệt và execution ID |
| Stop async job bằng `Thread.interrupt()` tùy tiện | Dữ liệu/transaction có thể dang dở | `JobOperator.stop` với graceful stop và timeout |
| Quên tắt Boot startup runner trong API service | Job tự chạy khi deploy ngoài các request API | `spring.batch.job.enabled=false` |
| Restart job bằng parameters khác | Mất checkpoint, xử lý trùng | Giữ identifying parameters khi restart |
| Chỉ đo HTTP latency mà không đo job duration | API nhanh nhưng job trễ deadline | Theo dõi cả submission, queue delay, runtime và publish |

## 16. Bài thực hành: chọn launch mode theo nhu cầu

Giả sử bạn xây một hệ thống `dailyReportJob`, đọc 500.000 đơn hàng, tổng hợp theo vùng và ghi bảng báo cáo:

1. **Baseline synchronous:** cấu hình `SyncTaskExecutor`, chạy job từ Java service hoặc CLI. Ghi thời điểm gọi `run()`, thời điểm trả về, execution ID và trạng thái cuối.
2. **Async launcher:** cấu hình `ThreadPoolTaskExecutor` (`core=2`, `max=4`, queue có giới hạn). Submit cùng một job và quan sát `run()` trả về khi job còn chạy.
3. **Status API:** tạo `POST /batch/jobs/daily-report` trả `202` + `Location`, `GET /batch/executions/{id}` trả trạng thái từ `JobExplorer`. Không trả nguyên `JobExecution`.
4. **Duplicate submit:** gửi hai request cùng `businessDate` và `region`. Xác nhận hệ thống không tạo hai luồng xử lý nghiệp vụ độc lập ngoài ý muốn.
5. **Failure outcome:** cho processor ném exception sau khi job đã được nhận. Xác nhận HTTP `202` ban đầu không làm status cuối biến thành `COMPLETED`.
6. **Long-running job:** dùng latch giữ một step. Với sync, caller phải chờ; với async, caller được giải phóng nhưng worker vẫn chiếm tài nguyên.
7. **Executor saturation:** giữ các job đang chạy, làm đầy queue, thử submit thêm. Xác định response hợp lý và cách theo dõi execution chưa dispatch.
8. **CLI scheduler:** chạy cùng job dưới `java -jar`, so sánh cách lấy process exit code khi dùng synchronous với những rủi ro nếu startup launcher trả về trước khi job hoàn tất.
9. **Graceful shutdown:** giả lập restart service trong khi job async đang chạy. Kiểm tra metadata, stop/restart policy và khả năng phục hồi; giải thích vì sao in-memory queue không đủ cho yêu cầu bền vững.
10. **Đề xuất kiến trúc:** với job dự kiến kéo dài 45 phút, 20 request/ngày và yêu cầu không mất lệnh khi deploy API, chọn giữa async in-process và API + durable queue + worker riêng; chỉ ra lý do chọn dựa trên SLA, số job đồng thời và khả năng recovery.

## 17. Quy tắc ra quyết định cuối cùng

Có thể bắt đầu bằng bốn câu hỏi:

1. **Caller có thật sự cần kết quả cuối trong cùng lời gọi?** Nếu có và thời gian chạy ngắn, synchronous phù hợp.
2. **Caller phải phản hồi nhanh dù job chạy lâu?** Nếu có, asynchronous ở ranh giới giao tiếp là lựa chọn thích hợp.
3. **Job có cần tiếp tục đáng tin cậy khi JVM phục vụ request bị restart?** Nếu có, cần durable submission/worker hoặc orchestrator độc lập, không chỉ một executor trong JVM.
4. **Ai chịu trách nhiệm biết job đã hoàn tất hay thất bại?** Nếu không chỉ ra được status repository, cơ chế monitor và đường recovery, kiến trúc async chưa hoàn chỉnh.

**Kết luận:** Synchronous và asynchronous launch là lựa chọn về **cách phối hợp giữa caller và job execution**, chứ không phải lựa chọn trực tiếp về tốc độ xử lý item. **Synchronous** đơn giản cho batch CLI hoặc workflow phải chờ kết quả; **asynchronous** phù hợp cho API/service cần phản hồi nhanh, nhưng phải bổ sung trạng thái bền vững, giới hạn concurrency, idempotency, theo dõi lỗi và quản trị vòng đời. Với yêu cầu độ bền cao, một kiến trúc **API bất đồng bộ ở bên ngoài nhưng worker chạy Spring Batch đồng bộ bên trong** thường cho phép vừa phản hồi nhanh vừa quản lý kết quả nhất quán.
