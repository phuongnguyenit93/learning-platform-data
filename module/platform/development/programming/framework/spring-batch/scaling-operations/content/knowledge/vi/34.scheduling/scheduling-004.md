# Launcher cho Job phân tán trong Spring Batch

> **Chương:** Scheduling
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán; đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế.

Một job có 12 partition không có nghĩa phải khởi chạy 12 `JobExecution`. Trong thiết kế phổ biến, **scheduler kích hoạt một manager job**, còn các step của job phân chia công việc cho nhiều worker. Nếu nhiều instance ứng dụng cùng chạy lịch, hoặc `JobLauncher` được cấu hình bất đồng bộ nhưng ứng dụng hiểu nhầm trạng thái trả về, hệ thống có thể tạo các lượt chạy ngoài ý muốn, tranh chấp `JobRepository` và xử lý trùng dữ liệu.

**Launcher cho Job phân tán** là cách thiết kế ranh giới từ **lịch chạy → quyết định có được chạy → tạo JobExecution → manager điều phối worker → theo dõi → stop/restart**. Cần tách bạch launcher, scheduler, repository và worker; không cố giải quyết mọi chuyện bằng một `@Scheduled` hoặc tăng thread pool.

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích vai trò khác nhau của `JobLauncher`, `TaskExecutorJobLauncher`, `JobRepository`, `JobOperator`, scheduler, manager step và remote worker.
2. Thiết kế `JobParameters` với **identifying parameters** ổn định để nhận diện đúng `JobInstance` và ngăn launch trùng theo một kỳ dữ liệu.
3. Viết mã khởi chạy job từ `@Scheduled`/external trigger; phân biệt **launcher đồng bộ và bất đồng bộ** mà không coi lệnh `run(...)` trả về là job đã hoàn tất.
4. Phân tích khi **hai scheduler replicas** cùng kích hoạt, cách phối hợp bằng cơ chế scheduler/leader lock và rào chắn của `JobRepository`.
5. Chọn mô hình điều phối **local partitioning, remote partitioning và remote chunking**; biết worker nào cần nhận `StepExecution`/chunk và nơi nào thực sự gọi launcher.
6. Xử lý duplicate triggers, failed starts, stop/restart, execution không rõ trạng thái, kết quả đã commit nhưng reply bị mất; bảo đảm idempotency.
7. Thiết lập metric, log, runbook và bài test concurrency/fault injection cho job phân tán.

## 1. Kiến trúc tổng thể: scheduler không phải worker

Ví dụ job nhập 6 triệu giao dịch mỗi đêm. Một scheduler gửi yêu cầu chạy `ordersImportJob` với bộ tham số xác định kỳ dữ liệu; manager tạo partition, rồi worker xử lý từng range.

~~~mermaid
flowchart TB
    S["Scheduler: cron / Quartz / Kubernetes CronJob"] --> G["Launch coordinator<br/>validate trigger, business date"]
    G --> L["JobLauncher"]
    L --> R[("JobRepository<br/>JobInstance / JobExecution")]
    L --> J["Manager JobExecution"]
    J --> M["Partition manager step"]
    M --> Q["PartitionHandler / broker"]
    Q --> A["Worker partition-0000"]
    Q --> B["Worker partition-0001"]
    Q --> C["Worker partition-0002"]
    A --> D[("Business DB / external systems")]
    B --> D
    C --> D
    A --> R
    B --> R
    C --> R
    R --> O["JobExplorer / JobOperator / Monitoring"]
~~~

Sơ đồ thể hiện **mô hình logic**, không phải mọi hệ thống đều có một broker. Local partitioning có thể dùng `TaskExecutorPartitionHandler` mà không cần middleware; remote partitioning thường truyền yêu cầu và kết quả qua messaging.

### Ai chịu trách nhiệm việc gì?

| Thành phần | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| **Scheduler** | Xác định khi nào cần chạy, lịch timezone, misfire/backfill | Tự sửa metadata để ép job thành công |
| **Launch coordinator** | Xây `JobParameters` ổn định, xác thực input, ghi nhận yêu cầu | Tạo identifying UUID mới cho mỗi retry cùng kỳ |
| **JobLauncher** | Gọi `JobRepository` để tạo/chạy `JobExecution` | Đóng vai trò broker phân phối từng business item |
| **JobRepository** | Lưu `JobInstance`, `JobExecution`, `StepExecution`, status, checkpoint | Đảm bảo tất cả HTTP/email side effects exactly-once |
| **Manager job/step** | Điều phối flow, partition plan, worker executions | Bị khởi động một `JobInstance` mới cho từng partition không cần thiết |
| **Worker** | Đọc/xử lý/ghi phần dữ liệu được giao | Sinh tự do JobInstance mới cho cùng phần việc |
| **JobExplorer** | Đọc metadata để điều tra/truy vấn trạng thái | Trở thành khóa phân tán atomic khi chỉ làm check-then-launch |
| **JobOperator** | Thao tác vận hành như stop/restart theo API hỗ trợ | Thay thế toàn bộ quản lý approval, input snapshot và idempotency |

Điểm nhấn: **JobLauncher là điểm vào của một job execution**, còn parallelism được điều khiển bởi step/flow/partition handler, executor và broker ở tầng sau.

## 2. Job, JobInstance và JobExecution: ba identity khác nhau

Giả sử mỗi ngày nhập dữ liệu của ngày hôm trước:

~~~text
jobName         = ordersImportJob
businessDate    = 2026-11-25
sourceVersion   = orders-2026-11-25-v1
~~~

Theo Spring Batch, `JobInstance` được xác định bởi **job name + tập identifying JobParameters**.

~~~text
JobInstance #100
  identifying:
    businessDate  = 2026-11-25
    sourceVersion = orders-2026-11-25-v1

  JobExecution #501   FAILED
  JobExecution #502   COMPLETED (restart của cùng JobInstance)
~~~

Nếu scheduler chạy lần nữa với **cùng bộ identifying parameters**:

- Nếu execution tương ứng còn chạy: framework có thể ném `JobExecutionAlreadyRunningException`.
- Nếu instance đã hoàn tất: có thể ném `JobInstanceAlreadyCompleteException`.
- Nếu lần trước `FAILED` và job restartable: một execution mới có thể được tạo cho **cùng JobInstance**, theo chính sách cho phép.
- Nếu job/step không restartable hoặc trạng thái không phù hợp: có thể nhận `JobRestartException` hoặc lỗi khởi chạy liên quan.

**Không** coi một lần scheduler tick là một `JobInstance` khác. Lặp trigger có thể là yêu cầu trùng, và không phải lúc nào cũng nên tự biến thành một lượt chạy mới.

### Tại sao `run.id` hoặc timestamp mới có thể nguy hiểm?

~~~java
// Anti-pattern cho bài toán đúng một lần theo businessDate:
new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addLong("run.id", System.currentTimeMillis(), true)
        .toJobParameters();
~~~

Tham số `run.id` **identifying** đổi sau mỗi trigger khiến Spring Batch xem đó là **JobInstance khác**, dù input cùng kỳ. Việc làm này có thể phù hợp với những job chạy lặp độc lập có chủ đích, nhưng **không phù hợp** nếu yêu cầu “mỗi ngày một logical import” và dữ liệu đích không cho phép thực thi hai lần.

### Identifying và non-identifying parameters

| Tham số | Vai trò đề xuất | Ghi chú |
| --- | --- | --- |
| `businessDate` | Identifying | Một kỳ dữ liệu cụ thể |
| `sourceVersion` | Identifying **nếu** một snapshot là một đơn vị công việc riêng | Phải cố định trước start/restart |
| `tenantGroup` | Identifying khi tạo job độc lập theo nhóm tenant | Cần namespace rõ |
| `triggeredBy` | Non-identifying | SCHEDULER / OPERATOR / API |
| `requestId` | Thường non-identifying | Dùng correlation, không mở JobInstance mới vô tình |
| `requestedAt` | Non-identifying nếu dùng để audit | Không thay đổi semantics của business input |
| `attemptId` | Không nên dùng làm identifying cho cùng logical run | Attempt đã được phản ánh bởi `JobExecution` |

**Lưu ý về input thay đổi:** Nếu thêm `sourceVersion` vào identifying parameters nhưng mỗi lần trigger lại tạo snapshot version mới, vô tình có thể khởi chạy **hai JobInstance cho cùng businessDate**. Cần **cơ chế seal/đăng ký snapshot duy nhất theo kỳ** ở tầng nghiệp vụ hoặc policy rõ cho phép nhiều phiên bản.

## 3. Launcher đồng bộ và bất đồng bộ

Với Spring Batch 5.x, `TaskExecutorJobLauncher` được cấu hình với `JobRepository` và một `TaskExecutor`. Executor quyết định việc thực thi job có diễn ra ngay trên thread gọi hay được giao sang thread khác.

| Cách chạy | Hành vi của lời gọi `run(job, params)` | Điều scheduler/API cần hiểu |
| --- | --- | --- |
| **Đồng bộ** (ví dụ `SyncTaskExecutor`) | Thread gọi chờ job thực thi tới điểm hoàn tất/kết thúc | Có thể nhận `JobExecution` terminal, nhưng vẫn kiểm tra status/exit code |
| **Bất đồng bộ** (thread pool) | Lời gọi có thể trả về khi job **vừa được đăng ký/khởi phát**, chưa chạy xong | Không tự trả HTTP “đã hoàn thành”; monitor `JobRepository` |
| **Bị từ chối scheduling** | Executor có thể reject hoặc việc dispatch lỗi | Phải điều tra `JobExecution` đã được tạo/chưa được chạy và tránh tạo trùng |

### Một launcher bất đồng bộ cấu hình minh họa

~~~java
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
ThreadPoolTaskExecutor jobLaunchExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("job-launch-");
    executor.initialize();
    return executor;
}

@Bean
JobLauncher asynchronousJobLauncher(
        JobRepository jobRepository,
        ThreadPoolTaskExecutor jobLaunchExecutor) throws Exception {

    TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
    launcher.setJobRepository(jobRepository);
    launcher.setTaskExecutor(jobLaunchExecutor);
    launcher.afterPropertiesSet();
    return launcher;
}
~~~

Đây là **mẫu cho Spring Batch 5.x**, không phải yêu cầu phải thay bean launcher mặc định của mọi dự án. Spring Boot có thể tự cấu hình `JobLauncher`; nếu tạo thêm bean launcher, hãy dùng `@Qualifier` hoặc tách rõ tên để tránh injection mơ hồ. Khi dùng `@EnableBatchProcessing` với Spring Boot, cần hiểu việc auto-configuration có thể thay đổi; đừng lắp chồng hai cấu hình launcher không kiểm soát.

**Quan trọng:** Executor của `JobLauncher` chỉ quyết định **job được khởi phát trên thread nào**. Nó không tự tạo 8 partition workers hoặc làm `ItemReader` thread-safe. Concurrency của manager/partition handler/broker cần cấu hình và capacity riêng.

### Khi nào chọn launcher đồng bộ?

- Batch job chạy từ một command/container riêng, tiến trình **chờ kết quả** rồi thoát với exit code thích hợp.
- Đơn vị schedule ngoài (như Kubernetes CronJob) cần biết container process đã hoàn thành hay thất bại.
- Vận hành ưu tiên quy trình rõ, số job chạy đồng thời thấp và lifetime của process phù hợp.

### Khi nào chọn launcher bất đồng bộ?

- Một API nhận yêu cầu khởi chạy và trả response nhanh với **execution ID**, tiếp tục theo dõi bằng endpoint khác.
- Scheduler thread không nên bị block hàng giờ.
- Có cơ chế monitor/restart, giới hạn launch queue, graceful shutdown và xử lý executor rejection.

**Không** chọn async chỉ để “scale dữ liệu”: tốc độ xử lý 6 triệu item phụ thuộc partitioning, reader/writer, DB/CPU/broker, không phải việc `run(...)` trả về sớm.

## 4. Ví dụ @Scheduled kích hoạt một manager job

Một service Spring có thể dùng `@Scheduled` để chạy job mỗi ngày lúc 01:00 theo timezone nghiệp vụ. Trong ví dụ, `businessDate` là **ngày hôm trước**, chỉ nhằm minh họa kỳ đối soát.

### 4.1. Bật scheduler và tránh job tự chạy ngoài ý muốn

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
~~~

Với Spring Boot đã auto-launch các `Job` khi startup trong cấu hình tương ứng, thường đặt:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

Đây là cấu hình **khi muốn chỉ khởi chạy theo scheduler/API chủ động**; phải kiểm tra Spring Boot version và bootstrap thực tế. Không nên vô tình chạy job lúc application startup rồi lại chạy qua cron cùng kỳ.

### 4.2. Dựng parameters có identity ổn định

~~~java
import java.time.LocalDate;
import java.time.ZoneId;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class DailyImportSchedule {

    private static final Logger log =
            LoggerFactory.getLogger(DailyImportSchedule.class);

    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private final JobLauncher launcher;
    private final Job ordersImportJob;
    private final SealedSnapshotResolver snapshots;

    public DailyImportSchedule(
            JobLauncher launcher,
            @Qualifier("ordersImportJob") Job ordersImportJob,
            SealedSnapshotResolver snapshots) {
        this.launcher = launcher;
        this.ordersImportJob = ordersImportJob;
        this.snapshots = snapshots;
    }

    @Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")
    public void submitPreviousBusinessDate() {
        LocalDate businessDate =
                LocalDate.now(BUSINESS_ZONE).minusDays(1);
        String sourceVersion =
                snapshots.requireSealedVersion(businessDate);

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate",
                        businessDate.toString(), true)
                .addString("sourceVersion", sourceVersion, true)
                .addString("triggeredBy", "SCHEDULER", false)
                .toJobParameters();

        try {
            JobExecution execution =
                    launcher.run(ordersImportJob, parameters);

            log.info("event=job_launch_submitted "
                    + "jobExecutionId={} status={} businessDate={} "
                    + "sourceVersion={}",
                    execution.getId(), execution.getStatus(),
                    businessDate, sourceVersion);
        } catch (JobExecutionAlreadyRunningException e) {
            log.info("event=job_launch_duplicate_running "
                    + "businessDate={}", businessDate);
        } catch (JobInstanceAlreadyCompleteException e) {
            log.info("event=job_launch_already_complete "
                    + "businessDate={}", businessDate);
        } catch (JobRestartException
                 | JobParametersInvalidException e) {
            log.error("event=job_launch_rejected "
                    + "businessDate={} reason={}",
                    businessDate, e.getClass().getSimpleName(), e);
            // Có alert/ticket ở hệ thống vận hành thực tế.
        }
    }
}
~~~

`SealedSnapshotResolver` là interface ứng dụng **chưa triển khai trong snippet**, ví dụ:

~~~java
public interface SealedSnapshotResolver {
    String requireSealedVersion(LocalDate businessDate);
}
~~~

Mục đích là lấy **đúng một phiên bản input đã chốt**, dùng lại khi scheduler lặp hoặc job restart. Trong Java, đặt các public top-level types vào các file riêng. Ví dụ dùng `LocalDate.now(...)` cho dễ đọc; production nên inject `Clock` để kiểm thử thời điểm đổi ngày/DST, xử lý ngày lễ và backfill.

**Không tự nuốt mọi lỗi:** Các exception trùng launch có thể được coi là **idempotent trigger** nếu đúng job/parameters; lỗi cấu hình/validator/JobRepository cần báo sự cố. Một exception runtime hoặc scheduler unavailable cũng cần alert, retry trigger có kiểm soát và đối chiếu repository.

### Một điều dễ nhầm

Trong mã trên, log event `job_launch_submitted` **không có nghĩa job đã COMPLETED** khi launcher chạy bất đồng bộ. Nó chỉ ghi nhận `JobExecution` có ID và trạng thái lúc trả về. Phải đọc status terminal từ `JobRepository` hoặc callback/monitor riêng để xác định hoàn tất.

## 5. Hai scheduler replicas: check-then-launch chưa đủ

Giả sử ứng dụng có ba replicas, mỗi replica đều có `@Scheduled`:

~~~mermaid
sequenceDiagram
    participant A as Scheduler pod A
    participant B as Scheduler pod B
    participant R as Shared JobRepository
    A->>R: Đọc: chưa thấy execution active
    B->>R: Đọc: chưa thấy execution active
    A->>R: JobLauncher.run(job, same parameters)
    B->>R: JobLauncher.run(job, same parameters)
    R-->>A: Một request được xử lý theo repository policy
    R-->>B: Request còn lại bị chặn/nhận lỗi duplicate hoặc trạng thái liên quan
~~~

Hai replica có thể **cùng đọc “chưa chạy”** trước khi một replica tạo metadata. Vì thế:

~~~java
// Anti-pattern: TOCTOU race (time-of-check to time-of-use).
if (jobExplorer.findRunningJobExecutions("ordersImportJob").isEmpty()) {
    jobLauncher.run(ordersImportJob, parameters);
}
~~~

Đoạn `JobExplorer` chỉ là query trạng thái, **không phải thao tác claim atomic**. Dùng nó cho dashboard/guardrail phụ, không dùng riêng nó như distributed lock.

### Rào chắn nào nên phối hợp?

| Lớp | Công dụng | Giới hạn |
| --- | --- | --- |
| Scheduler cluster lock / leader election | Giảm duplicate triggers, có một coordinator phát lịch | Phải xử lý lease expiry, failover và manual trigger |
| `JobRepository` dùng chung + identifying parameters đúng | Bảo vệ identity và trạng thái `JobInstance/JobExecution` trong phạm vi DB/framework | Không tự dedupe side effects ở DB/API khác |
| Business run registry có unique key theo kỳ | Chốt một source snapshot và quyền launch/backfill | Cần thiết kế atomic claim/state transitions |
| Worker business idempotency | Ngăn tác dụng ghi trùng khi replay hoặc hai managers lỗi | Phải đặt tại nơi thực hiện side effect |
| Monitoring/reconciliation | Phát hiện launch bị kẹt, job thất bại và effect không rõ | Không thay transaction/idempotency |

**Nguyên tắc:** Tránh trigger trùng ở scheduler để tiết kiệm tài nguyên, dùng repository bảo vệ danh tính Batch, và dùng business idempotency cho kết quả cuối cùng. Không nên kỳ vọng một tầng thay thế hoàn toàn các tầng khác.

### Các lựa chọn scheduler phổ biến

- Một **instance scheduler riêng** chạy cố định, các worker replicas không bật lịch.
- **Quartz clustering** nếu đã có Quartz và một shared JobStore được cấu hình đúng.
- **Leader election/distributed lock** với TTL/fencing/health check phù hợp.
- **Kubernetes CronJob** tạo Job/Pod theo lịch, kết hợp `concurrencyPolicy` như `Forbid` hoặc `Replace` theo yêu cầu.
- External orchestration (Airflow, enterprise scheduler, Argo Workflows…) gửi yêu cầu qua API hoặc command launcher.

`concurrencyPolicy: Forbid` của **một Kubernetes CronJob** giúp ngăn các Job đang chạy **của cùng CronJob resource** chồng lên nhau theo semantics controller; nó không chặn người vận hành chạy command thủ công, hai CronJob resources khác nhau hoặc một scheduler ngoài cùng kích hoạt logical job. Vẫn cần identifying parameters và repository.

## 6. Ví dụ Kubernetes CronJob kích hoạt manager

Nếu muốn **một process Batch riêng cho mỗi lịch**, một CronJob có thể tạo container chạy launcher đồng bộ, thay vì ba long-lived web replicas đều mang `@Scheduled`.

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: orders-import-manager
spec:
  schedule: "0 1 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 1800
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: manager
              image: registry.example.com/orders-batch:1.0.0
              args:
                - "--spring.batch.job.enabled=false"
                - "--app.batch.run-once=true"
              env:
                - name: JOB_REPOSITORY_URL
                  valueFrom:
                    secretKeyRef:
                      name: orders-batch-db
                      key: jdbc-url
~~~

**Đây là deployment minh họa**, image, command entrypoint, custom flag `app.batch.run-once` và secret phải được ứng dụng triển khai. Tham số `spring.batch.job.enabled=false` không tự làm job chạy: cần một `ApplicationRunner`/command handler riêng khi `app.batch.run-once=true` để gọi `JobLauncher` đồng bộ, rồi thoát với **process exit code phản ánh BatchStatus/ExitStatus**. Nếu process thoát `0` ngay sau khi enqueue launcher async, CronJob có thể báo thành công dù manager job chưa hoàn thành.

### Những điểm không được bỏ qua

1. Hỗ trợ `spec.timeZone` phụ thuộc version Kubernetes/controller; cần xác nhận ở cluster thực tế.
2. `Forbid` giúp tránh overlap của lịch cùng CronJob nhưng có thể **bỏ lỡ lịch** khi lần trước kéo dài. Cần policy backfill/misfire.
3. `Replace` có thể dừng pod cũ trước khi job cũ cleanup; việc dừng là **cơ chế container**, chưa chắc worker từ xa đã ngừng hoặc transaction đã được hủy.
4. `backoffLimit` và pod retry có thể tạo lại process launcher; cùng identifying parameters phải tránh sinh JobInstance trùng ngoài ý muốn.
5. Source snapshot và businessDate phải được tính/đăng ký theo kỳ **nghiệp vụ**, không chỉ dựa vào ngày thực tế lúc pod cuối cùng khởi chạy.
6. Database metadata dùng chung phải sẵn sàng và đủ capacity cho manager/worker.

Không copy manifest này vào production mà chưa có ứng dụng launcher/monitor hoàn chỉnh, RBAC, secret management, resources, termination grace, probes, retry/backfill và retention policy.

## 7. JobLauncher bất đồng bộ: trạng thái trả về chỉ là điểm bắt đầu

Một API ví dụ:

~~~text
POST /batch/orders-import
{
  "businessDate": "2026-11-25",
  "sourceVersion": "orders-2026-11-25-v1"
}
~~~

Sau khi validate/authorize trigger và gọi `JobLauncher.run(...)`, API có thể trả:

~~~json
{
  "jobExecutionId": 502,
  "accepted": true,
  "currentStatus": "STARTING",
  "businessDate": "2026-11-25"
}
~~~

Đây là **contract API do ứng dụng thiết kế**, không phải REST endpoint built-in của Spring Batch. Response “accepted” có nghĩa đã **ghi nhận yêu cầu/chuyển cho launcher**, **không** có nghĩa các worker đã commit toàn bộ output.

### Sau đó monitor thế nào?

~~~text
Client / scheduler
    |
    +-- 202 Accepted, jobExecutionId=502
    |
    +-- GET /batch/job-executions/502
          |
          +-- STARTING/STARTED/STOPPING (chưa terminal)
          +-- COMPLETED / FAILED / STOPPED / ABANDONED (cần diễn giải)
~~~

Endpoint `GET` trong sơ đồ cũng là **API ứng dụng**. Bên trong có thể dùng `JobExplorer`/metadata hoặc các API vận hành tương ứng để đọc `JobExecution`, `StepExecution` và timestamps.

### Trạng thái chưa terminal không phải lỗi

Không dùng:

~~~java
JobExecution execution = launcher.run(job, params);
if (execution.getStatus() != BatchStatus.COMPLETED) {
    throw new IllegalStateException("Job failed!");
}
~~~

Với launcher async, `getStatus()` ngay sau `run(...)` có thể đang `STARTING`/`STARTED`. Cần chờ thông qua cơ chế monitor có timeout hợp lý, callback/event hoặc công cụ orchestrator. **Không busy-loop** truy vấn DB mỗi vài mili giây; dùng polling interval/backoff và tránh làm nóng `JobRepository`.

### Cảnh báo executor rejection và orphaned execution

Nếu queue của launcher đã đầy hoặc process bị kill ngay sau khi tạo metadata, có thể xuất hiện execution chưa đạt terminal status. Cần:

- Quan sát queue size và rejection của executor.
- Có runbook xác định `JobExecution` còn thực sự chạy không bằng process/pod/heartbeat và `JobRepository`.
- Không gọi `run(...)` với một identifying UUID mới để “né” execution cũ chưa rõ.
- Khôi phục theo cơ chế stop/restart/bảo trì metadata **được hỗ trợ**, sau khi xác nhận worker cũ đã dừng và side effects được đối soát.

## 8. Launch một manager job, không launch mọi partition

### 8.1. Local partitioning

Trong local partitioning, manager step chia công việc qua `Partitioner` rồi dùng `TaskExecutorPartitionHandler` để worker steps chạy trong các threads cùng JVM.

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.core.task.TaskExecutor;

@Bean
Step ordersManagerStep(
        JobRepository jobRepository,
        Partitioner ordersPartitioner,
        Step ordersWorkerStep,
        TaskExecutor partitionExecutor) {

    return new StepBuilder("ordersManagerStep", jobRepository)
            .partitioner(ordersWorkerStep.getName(), ordersPartitioner)
            .step(ordersWorkerStep)
            .gridSize(8)
            .taskExecutor(partitionExecutor)
            .build();
}
~~~

Đoạn mã minh họa **Spring Batch 5.x**, cần các bean `ordersPartitioner`/`ordersWorkerStep`/`partitionExecutor` thật. Chỉ có **một manager JobExecution** cho lần launch đó; manager step điều phối nhiều `StepExecution` worker.

### Vì sao không dùng launcher pool làm partition pool?

~~~text
TaskExecutorJobLauncher pool  -> số JobExecutions có thể bắt đầu đồng thời
TaskExecutorPartitionHandler  -> số worker StepExecutions trong một manager job
Multi-threaded step executor -> số chunk tasks của một StepExecution
Broker consumer concurrency  -> số remote messages đang được xử lý
~~~

Bốn mức concurrency có thể độc lập. Nếu không phân biệt, bạn có thể tăng cả bốn pool cùng lúc, làm cạn DB connection, `JobRepository` pool và API downstream.

### 8.2. Remote partitioning

Trong remote partitioning, manager gửi **worker step execution requests** qua middleware, remote worker ở process khác thực thi worker step và cập nhật/đáp ứng theo cơ chế tích hợp.

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant L as Manager JobLauncher
    participant R as JobRepository
    participant M as Manager PartitionStep
    participant Q as Broker/Middleware
    participant W as Remote Worker
    S->>L: Trigger ordersImportJob(businessDate)
    L->>R: Tạo JobExecution
    L->>M: Thực thi manager step
    M->>R: Tạo/tra worker StepExecutions
    M->>Q: Dispatch worker request
    Q->>W: Deliver partition request
    W->>R: Đọc/cập nhật worker execution metadata
    W->>W: Reader / Processor / Writer
    W->>R: Ghi checkpoint và status
    W-->>Q: Reply/notification theo adapter
    Q-->>M: Correlated result
~~~

**Không** biến worker thành chương trình gọi `JobLauncher.run(ordersImportJob, ...)` cho mỗi partition. Worker thường được điều phối bởi remote partitioning integration với **StepExecution identity** và `ExecutionContext` riêng; framework/adapter hỗ trợ đường thực thi worker step. Việc gọi một JobLauncher mới ở worker làm mất mô hình một manager job/metadata thống nhất và có thể tạo các JobInstance thừa.

**Phụ thuộc version/adapter:** Chi tiết request/reply, persistence, headers, timeout và cách manager nhận kết quả khác nhau giữa Spring Batch Integration/Spring Integration/Kafka/AMQP. Không suy ngược mọi thiết kế về một lớp message cố định nếu chưa kiểm tra bản thư viện và middleware đang dùng.

### 8.3. Remote chunking

Trong remote chunking, manager thường đọc input/chia **chunk requests** rồi gửi worker; worker xử lý/ghi chunk và trả **replies**.

| Mô hình | Manager đảm nhiệm | Worker nhận | Điểm launch |
| --- | --- | --- | --- |
| Local partitioning | Chia partitions, quản lý worker steps trong JVM | `StepExecution` theo range/file | Launcher chạy manager job |
| Remote partitioning | Chia partitions và gửi worker step requests | Worker `StepExecution`/ExecutionContext | Launcher chạy manager job |
| Remote chunking | Reader/chia chunk, gửi request và theo dõi replies | Chunk items cần process/write | Launcher chạy manager job |

Với remote chunking, đừng nhầm `ChunkRequest` với `JobParameters` hoặc tạo `JobExecution` cho mỗi chunk. Worker nhận chunk cũng không nên tạo identifying timestamp mới để “giữ job chạy”.

## 9. JobRepository phải là nguồn metadata thống nhất

Để điều phối phân tán an toàn, các manager/worker cần hiểu **cùng lịch sử JobInstance/JobExecution/StepExecution** theo kiến trúc được triển khai.

### Các điều kiện quan trọng

- Metadata database được quản lý bền vững, có schema phù hợp Spring Batch version và transaction manager.
- Những thành phần cần dùng chung repository phải trỏ **đúng cùng logical repository**, không mỗi pod tự dùng một H2 in-memory.
- Identifying `JobParameters` phải ổn định và chuẩn hóa: timezone, tenant/source version, kiểu dữ liệu, tên parameter.
- Job name và step names không thay tùy tiện nếu còn các JobInstances cần restart.
- Partition key → input range/file/snapshot được giữ ổn định trên restart.
- Repository database được cấp đủ connection/IO capacity khi nhiều workers cập nhật checkpoint.
- Bảo vệ secrets, quyền ghi metadata và quy trình backup/restore phù hợp.

### Isolation của JobRepository không thay isolation writer

Spring Batch có cơ chế isolation khi **tạo JobInstance/JobExecution** để phối hợp các concurrent launches. Cấu hình này khác với isolation của **transaction chunk** đọc/ghi business data; `SERIALIZABLE` ở phần tạo metadata không biến mọi business query thành serializable hoặc chống side effects ngoài DB.

Nếu repository và business database nằm trên **hai datasource khác nhau**, checkpoint và business commit **không tự atomic**. Khi commit business thành công nhưng metadata chưa ghi nhận, restart có thể replay item. Phải có business idempotency/unique key và reconciliation.

### Không dùng `JobExplorer` như distributed mutex

`JobExplorer` đọc metadata, giúp xem trạng thái. Một request `findRunningJobExecutions(...)` là **ảnh chụp tại lúc truy vấn**; giữa “check” và “launch”, pod khác có thể bắt đầu job.

Rào chắn cuối của Batch vẫn là thao tác tạo execution của `JobRepository` có transaction/identity đúng. Nếu hệ thống cần **policy cao hơn** (một job cho mỗi tenant/kỳ trên nhiều công cụ trigger), cần thêm run registry/atomic claim bên nghiệp vụ.

## 10. Xử lý đồng thời hai trigger cùng một kỳ

Giả sử pod A và pod B cùng gọi `launcher.run(job, sameParams)`.

### Expected behavior

1. Cả hai gửi cùng tên job và **same identifying parameters**.
2. Repository phân xử việc tạo/tiếp tục execution theo constraints/transaction và trạng thái instance.
3. Một request được chấp nhận, request khác có thể nhận lỗi **already running/complete/restart related**; hành vi cụ thể phụ thuộc timing và trạng thái.
4. Coordinator log event `duplicate_trigger`, đối chiếu existing execution và không tự tạo identifying timestamp mới.
5. Operator vẫn có thể xem job nào thực sự chạy thông qua repository.

### Không chắc chắn ở ranh giới network

Client gọi launcher/API quản lý từ xa, request timeout. Client **không biết** phía manager đã tạo execution chưa. Nếu retry cùng identifying parameters, repository có cơ hội nhận ra instance đã tồn tại; nếu sinh key mới, hệ thống có thể chạy dữ liệu cùng kỳ hai lần.

Khi cần bảo đảm request idempotency ở **API trước launcher**, thêm:

~~~text
requestId (stable per logical launch request)
        |
        v
request registry (unique requestId -> jobInstance/execution)
        |
        v
JobLauncher.run(job, stable identifying parameters)
~~~

Request registry cần transaction/unique constraint và state machine; không chỉ cache RAM. Nhưng **requestId cũng không nhất thiết là JobInstance identity**: hai request khác ID cùng yêu cầu chạy kỳ 2026-11-25 vẫn nên trỏ về **cùng logical job instance**, theo hợp đồng.

## 11. Retry launch khác retry một chunk

| Hành động | Điều được thực thi lại | Ai kiểm soát |
| --- | --- | --- |
| Retry API launch sau timeout | Yêu cầu khởi động job | Coordinator/repository |
| `JobLauncher.run(job, sameParams)` sau failure | Có thể tạo một JobExecution mới của JobInstance cũ nếu restartable | Spring Batch JobRepository |
| `JobOperator.restart(executionId)` | Restart execution theo ID đã thất bại/dừng theo policy | JobOperator/JobRepository |
| Retry một item/chunk | Item/chunk transaction và business operations | Fault-tolerant step |
| Remote broker redelivery | Worker partition request hoặc chunk request | Middleware/worker |

Không lấy `retryLimit(3)` của step làm số lần scheduler được phép launch. Không dùng `RunIdIncrementer` để “restart” cùng logical work khi semantics kỳ/snapshot phải giữ nguyên.

### Khi nào cần chọn tự động restart?

- Lỗi temporary và dữ liệu đầu vào đã **sealed**, có checkpoint/idempotency phù hợp.
- Operator đã có policy cho phép retry theo số lần, backoff, thời gian và loại lỗi.
- Worker cũ được xác minh không còn tiếp tục gây side effects ngoài transaction.
- `FAILED/STOPPED` execution còn restartable theo framework.

Với thanh toán, ghi sổ hoặc external API trả timeout, **không auto-restart mù** khi chưa đối soát trạng thái `UNKNOWN`. Một lần launch mới không tự hoàn tác hoặc dedupe được tác dụng phụ đã xảy ra.

## 12. Stop và restart Job phân tán

`JobOperator` cung cấp các thao tác vận hành stop/restart theo API của Spring Batch; `JobExplorer` có thể được dùng để xem trạng thái và metadata.

### Luồng stop an toàn

~~~mermaid
flowchart TD
    O["Operator yêu cầu stop"] --> P["JobOperator.stop(executionId)"]
    P --> M["Manager/JobRepository ghi nhận yêu cầu STOPPING"]
    M --> W["Workers kiểm tra stop theo lifecycle"]
    W --> C["Hoàn tất/rollback tại boundary an toàn"]
    C --> S["STOPPED khi hệ thống xác nhận"]
    S --> R{"Được phép restart?"}
    R -- "Có" --> N["Restart cùng JobInstance"]
    R -- "Không" --> X["Điều tra + reconcile trước"]
~~~

Đây là **hành vi mục tiêu**, không phải cam kết một lệnh `stop` chấm dứt tức thì mọi thread/process. Spring Batch stop thường mang tính **cooperative**: một worker bị treo trong I/O, remote worker mất liên lạc hoặc một container đang crash có thể chưa chuyển trạng thái ngay.

### Rủi ro khi “restart” bằng kill pod

Kill manager pod không đồng nghĩa:

- Các remote workers đã dừng.
- Transaction bên ngoài đã rollback.
- `JobRepository` kịp ghi status terminal.
- Broker sẽ không giao lại request cũ.
- Input snapshot, partition mapping hoặc business dedupe vẫn còn hợp lệ.

Với hệ thống phân tán, cần quy trình xác minh `JobExecution`/`StepExecution`, tình trạng worker/broker và business effects. Nếu metadata kẹt ở `STARTED` do hard crash, không sửa trực tiếp các bảng `BATCH_*` theo cảm tính; xử lý bằng runbook/version-supported operations và kiểm toán trước restart.

### Restart cùng JobInstance

~~~text
JobInstance:
  ordersImportJob + businessDate=2026-11-25
  + sourceVersion=orders-2026-11-25-v1

Execution #501: FAILED
Execution #502: COMPLETED after restart

partition-0000: đã COMPLETED ở #501 -> có thể được giữ trạng thái completed
partition-0001: FAILED ở #501 -> cần chạy lại theo checkpoint
partition-0002: COMPLETED ở #501 -> không cần làm lại
~~~

Đây là kết quả **dự kiến khi partitioning/restart được cấu hình đúng**, không phải đảm bảo tuyệt đối cho mọi custom splitter hoặc khi input plan thay đổi. Phải giữ mapping logical partition name → input range/file ổn định.

## 13. Thiết kế idempotency khi remote worker bị giao lại

Một launcher chỉ quyết định **JobInstance identity**. Nó không thể ngăn mọi duplicate business operation phát sinh khi:

- Chunk transaction đã commit, manager mất reply.
- Broker redeliver cùng request.
- Remote worker cũ vẫn chạy sau timeout nhưng manager khởi động worker mới.
- Job restart và reader đọc lại item kể từ checkpoint cũ.
- Hai partitions bị overlap do partitioner chia sai.

### Ba mức identity thường cần

~~~text
JobInstance identity:
  (jobName, identifying JobParameters)

Logical partition identity:
  (JobInstance identity, managerStepName, partitionName, sourceVersion)

Business operation identity:
  (tenantId, operationId)
~~~

**Không dùng `StepExecutionId` làm business operation ID**: execution ID có thể thay khi restart, còn việc ghi tiền/ledger vẫn là **cùng operation**.

### Ví dụ chống ghi trùng tại đích

~~~sql
-- PostgreSQL: unique business key độc lập JobExecutionId.
CREATE TABLE imported_order (
    tenant_id       VARCHAR(80)  NOT NULL,
    operation_id    VARCHAR(160) NOT NULL,
    source_version  VARCHAR(160) NOT NULL,
    order_id        VARCHAR(160) NOT NULL,
    payload_hash    VARCHAR(128) NOT NULL,
    status          VARCHAR(30) NOT NULL,
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

Khi worker retry/restart, writer phải dùng **cùng operation ID**. Nếu key đã tồn tại, xác minh payload/semantics tương đương và xem đó là replay hợp lệ; nếu payload khác, báo conflict/quarantine chứ không âm thầm `ON CONFLICT DO NOTHING` cho mọi lỗi.

**Với HTTP/broker side effects:** Database unique key tại worker **không đủ** để bảo vệ API bên ngoài nếu một request đã gửi trước khi transaction rollback. Dùng provider-side idempotency key, transactional outbox/inbox, durable operation intent và reconciliation theo thiết kế.

## 14. Scheduler backfill, missed run và overlap qua ngày

Một job mất 5 giờ trong khi lịch chạy mỗi 4 giờ. Nếu scheduler không có overlap policy, có thể có **hai JobInstances khác kỳ** cùng chạy, tranh chấp DB/CPU và gây cập nhật thứ tự sai.

### Ba chính sách khác nhau

| Chính sách | Ý nghĩa | Cần quyết định thêm |
| --- | --- | --- |
| **Skip when active** | Nếu job đang chạy, bỏ lịch mới | Kỳ bị bỏ sẽ backfill hay vĩnh viễn không chạy? |
| **Queue/coalesce** | Ghi pending run, chạy lần lượt | Queue bền vững, thứ tự theo business date, giới hạn backlog |
| **Allow overlap** | Cho phép nhiều ngày/kỳ xử lý song song | Snapshot, isolation, resource quota và cross-period business conflicts |

Một scheduler lock chỉ chống **trùng cùng lịch** không nhất thiết chặn một JobInstance cho hôm trước đang chạy và một JobInstance khác cho hôm nay bắt đầu. Nếu đầu vào hoặc tài nguyên đích phụ thuộc thứ tự, cần **business run coordinator**.

### Backfill phải explicit

Thay vì đổi clock hệ thống hoặc tạo identifying UUID:

~~~text
Request backfill:
  jobName=ordersImportJob
  businessDate=2026-11-20
  sourceVersion=orders-2026-11-20-v1
  triggeredBy=OPERATOR (non-identifying)
~~~

Nếu instance ngày 20 đã `COMPLETED` nhưng muốn xử lý **dữ liệu đã chỉnh sửa**, cần policy riêng cho reprocessing/new snapshot và business idempotency, không đơn giản dùng `JobLauncher.run` với timestamp khác để lách status `COMPLETED`.

### Timezone, DST và lịch ngày

Scheduler có thể chạy theo timezone cụ thể, còn timestamp log lưu UTC; business date cần được chốt theo **timezone nghiệp vụ**. Trong ví dụ Việt Nam, `Asia/Ho_Chi_Minh` không có chuyển DST theo quy tắc hiện hành, nhưng kiến trúc đa quốc gia có thể gặp giờ bị lặp hoặc bị bỏ qua khi đổi DST.

Nên tách `scheduledFireTime` và `businessDate`, có cách xác định **ngày dữ liệu chuẩn** khi trigger trễ/missed run. Khi cần tính lại lịch lịch sử, không suy business date từ `LocalDate.now()` của một pod chạy muộn mà không có quy tắc.

## 15. Điều phối nhiều manager jobs và tài nguyên

Đôi khi một scheduler chạy nhiều jobs/flows độc lập: `importOrdersJob`, `enrichCustomersJob` và `publishReportJob`. Chúng có thể chia sẻ business database và downstream API.

### Resource budget

~~~text
Số manager jobs đang active
  × số partition worker/manager
  × số chunk threads/worker
  × số connections và external requests/worker

→ tổng tải có thể vượt DB pool/broker/API quota.
~~~

Công thức chỉ là **mô tả nguy cơ nhân concurrency**, không phải số connections chính xác. Reader có thể giữ cursor connection riêng, JobRepository có datasource riêng, worker có HTTP pool riêng.

### Kiểm soát từ launcher xuống worker

1. Giới hạn **số JobExecutions active** nếu chạy nhiều kỳ/job.
2. Chọn `gridSize` và worker concurrency theo benchmark thực tế.
3. Giới hạn chunk threads nếu worker step multi-threaded.
4. Đặt pool size, timeout, backpressure và rate limit phù hợp downstream.
5. Giữ metadata repository đủ capacity; không dùng nó như hàng đợi xử lý toàn bộ business messages.
6. Theo dõi latency, retry/rollback, queue lag và business throughput.

**Không tăng `TaskExecutorJobLauncher` pool để xử lý vấn đề DB bottleneck.** Launcher chỉ cho phép nhiều JobExecutions cùng chạy; nếu database đã bão hòa, throughput có thể giảm.

## 16. Log, metrics và tracing qua manager/worker

Một launch request nên tạo được đường truy vết:

~~~text
scheduler trigger
  -> jobName + businessDate + sourceVersion
  -> JobInstanceId + JobExecutionId
  -> managerStep/partitionName
  -> worker StepExecutionId
  -> message correlationId (nếu remote)
  -> business operation ID
~~~

| Event | Trường đáng có | Thời điểm ghi |
| --- | --- | --- |
| `job_launch_requested` | jobName, businessDate, sourceVersion, triggerSource | Nhận trigger |
| `job_launch_accepted` | JobExecutionId, JobInstanceId, status | Repository đã ghi nhận |
| `job_launch_duplicate` | identifying parameters, existing execution nếu xác minh được | Trigger bị chặn/coalesce |
| `job_started` | JobExecutionId, start time | Job thực sự bắt đầu |
| `partition_dispatched` | partitionName, worker step, correlationId | Manager gửi work |
| `partition_finished` | StepExecutionId, status, read/write/skip/rollback counters | Worker kết thúc |
| `job_finished` | JobExecutionId, BatchStatus, ExitStatus, duration | Job terminal |
| `job_restart_requested` | prior execution ID, reason, operator | Trước restart |
| `external_effect_unknown` | business operation key, reason code | Cần reconciliation |

**Một log `job_launch_accepted` không có nghĩa `job_finished(COMPLETED)`.** Nếu manager crash, event kết thúc có thể không được ghi; dùng `JobRepository` và giám sát process/worker/broker để xác định thực tế.

### Metrics nên có

- Job launches requested/accepted/duplicate/rejected theo job.
- Running/failed/completed JobExecutions và Job duration.
- Active partitions, partition skew, worker queue/consumer lag.
- Step read/write/skip/rollback và chunk commit rate.
- JobRepository connection pool và create/update latency.
- Scheduler drift/misfire/backfill queue depth.
- Business input expected, output unique, pending/unknown và reconciliation mismatches.

Không gắn `JobExecutionId`, source IDs hoặc partitionNames không giới hạn làm nhãn metric dài hạn vì cardinality cao. Đưa identity chi tiết vào structured logs/audit có retention và quyền truy cập phù hợp.

## 17. Health, readiness và graceful shutdown

### Manager readiness

Một pod scheduler nhận trigger khi `JobRepository` không kết nối được có thể thất bại trước khi tạo execution. Cần health/readiness và retry trigger có kiểm soát, nhưng **không** phát hiện outage bằng cách tạo identifying ID mới mỗi lần.

### Worker readiness

Worker remote chỉ nên nhận work khi có đủ kết nối tới metadata repository, broker và business DB theo kiến trúc. Nếu một dependency mất kết nối giữa chừng, cần timeout/backoff, rollback và trạng thái `FAILED/UNKNOWN` phù hợp.

### Graceful shutdown

Khi scale down hoặc rolling deploy:

1. Ngừng nhận **trigger/work mới**.
2. Dừng dispatch với cơ chế scheduler/leader thích hợp.
3. Cho in-flight chunk commit/rollback tại boundary an toàn.
4. Chờ/báo cáo completion của worker và cập nhật metadata khi có thể.
5. Nếu timeout vượt grace period, ghi nhận nguy cơ execution đang dở; operator reconcile trước restart.

Kill container hoặc mất broker reply không đồng nghĩa transaction/HTTP effects đã rollback. Lệnh stop của Spring Batch mang tính cooperative; cần kiểm chứng toàn bộ remote workers thực sự ngừng.

## 18. Kiểm thử launcher và lịch phân tán

### 18.1. Unit test identifying JobParameters

Nên tách việc tạo JobParameters thành hàm thuần được test độc lập:

~~~java
import java.time.LocalDate;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

public final class ImportJobParametersFactory {

    public JobParameters forDay(
            LocalDate businessDate, String sealedSourceVersion,
            String triggeredBy) {

        return new JobParametersBuilder()
                .addString("businessDate",
                        businessDate.toString(), true)
                .addString("sourceVersion",
                        sealedSourceVersion, true)
                .addString("triggeredBy", triggeredBy, false)
                .toJobParameters();
    }
}
~~~

Test kỳ vọng hai triggers `SCHEDULER` và `OPERATOR` của **cùng ngày/snapshot** có **cùng identifying values**, dù `triggeredBy` khác. Không chỉ assert `JobParameters.equals(...)` toàn bộ nếu non-identifying field thay đổi; xác minh **identity được Spring Batch sử dụng** theo semantics của identifying parameters.

### 18.2. Integration test: cùng JobInstance được launch trùng

Với `JobRepository` dùng database thật:

1. Tạo một job có step chờ latch để bảo đảm execution đầu **chưa kết thúc**.
2. Dùng hai threads hoặc hai processes gọi `JobLauncher.run(job, same identifying parameters)` gần đồng thời.
3. Assert repository **không có hai active executions hợp lệ cho cùng một JobInstance** theo contract/framework cấu hình.
4. Ghi nhận request còn lại bị reject/duplicate hoặc trạng thái tương ứng, không tự thay tham số để ép chạy.
5. Giải phóng latch, xác minh metadata final và không tạo duplicate business output.

Test cần DB và transaction manager giống môi trường production; test chỉ dùng in-memory Map hoặc một singleton `synchronized` **không chứng minh** an toàn across pods.

### 18.3. Test async launcher

~~~text
Given:
  Job có step chờ tín hiệu từ test.
When:
  launcher async nhận run(job, params).
Then:
  run(...) trả về JobExecution đã có ID.
  JobExecution ngay lúc trả về không bắt buộc COMPLETED.
  Sau khi giải phóng tín hiệu, monitor thấy status terminal.
~~~

Kiểm thử executor bị reject/queue full, process shutdown sớm và JobRepository còn execution chưa terminal. Mục tiêu không phải assert mọi lần async đều đúng trạng thái `STARTING` vì timing thread pool khác nhau.

### 18.4. Test launcher đồng bộ + process exit

Một CronJob runner cần:

- `BatchStatus.COMPLETED` và exit code nghiệp vụ thành công → process exit code 0.
- `FAILED`/không đạt publish gate → process exit code khác 0.
- `STOPPED` hoặc trạng thái chưa xác nhận → không tự báo thành công.
- Job launcher exception xảy ra trước execution → log/alert và exit code phù hợp.

Test phải chờ job **thực sự terminal**, không chỉ chờ `run(...)` trả về trong launcher async.

### 18.5. Test restart và JobParameters

| Kịch bản | Kỳ vọng |
| --- | --- |
| Launch lần đầu cùng ngày/snapshot | Tạo JobInstance/JobExecution hợp lệ |
| Trigger trùng khi instance đang chạy | Không tự tạo logical work trùng |
| Trigger trùng sau `COMPLETED` | Không chạy lại như một JobInstance mới ngoài policy |
| Execution `FAILED`, restart được duyệt | Execution mới thuộc **cùng JobInstance** |
| Backfill kỳ cũ | Nhận đúng businessDate/sourceVersion cũ |
| Snapshot đổi cho cùng businessDate | Bị chặn hoặc tạo versioned run theo policy rõ |
| `JobExecutionId` mới sau restart | Partition names và business operation keys vẫn ổn định |
| Worker partition đã `COMPLETED` | Không tự chạy lại nếu restart policy giữ completed work |
| Manager reply timeout | Không suy rằng worker chưa commit |
| Kill manager pod | Runbook phát hiện workers/metadata còn dở |
| Worker cũ vẫn active sau failover | Claim/fencing/idempotency không tạo effect trùng |
| Remote broker redelivery | Request correlation và business output an toàn |
| JobRepository outage | Không tạo JobInstance ngoài repository bằng workaround nguy hiểm |
| DB pool thiếu/đối tác 429 | Backpressure và alert, không tăng launch pool mù |

### 18.6. Test partition concurrency và tập dữ liệu

Với 4–8 partitions có input manifest cố định:

- Kiểm tra range/file/tenant của từng partition **không overlap** ngoài chủ đích.
- Tổng union của partition inputs khớp source snapshot.
- Các worker có `StepExecution` và `ExecutionContext` riêng.
- Một worker `FAILED` rồi restart giữ logical partition name/input version.
- Business output không nhân đôi khi replay chunk/request.
- Sau khi job terminal, đối soát read/write/skip cùng **unique business keys**, không chỉ cộng counters.

## 19. Runbook: job bị kích hoạt hai lần hoặc không hoàn tất

1. **Xác định business period:** Job name, businessDate, sourceVersion, tenant group và identifying parameters.
2. **Tra JobRepository:** Có bao nhiêu `JobInstance` cho logical work? Các `JobExecution` mang trạng thái nào?
3. **Tìm nguồn trigger:** Pod `@Scheduled` nào, CronJob/Quartz/API/manual invocation nào đã gửi yêu cầu?
4. **Phân biệt duplicate với restart:** Có cùng identifying parameters hay một tham số `run.id`/timestamp bị tạo mới?
5. **Kiểm tra manager:** JobExecution có thực sự bắt đầu không, partition plan nào đã dispatch?
6. **Kiểm tra workers:** `StepExecution` status, heartbeat, in-flight tasks, broker redelivery và reply correlation.
7. **Đánh giá side effects:** Business ledger/unique operation keys, output snapshot, transactions và external API có trạng thái `UNKNOWN` nào?
8. **Dừng cấp thêm work nếu cần:** Ngăn scheduler duplicate, giữ nguyên input seal; tránh kill workers không kiểm soát.
9. **Khắc phục dependency:** JobRepository, broker, DB pool, API downstream, cấu hình versions và schema.
10. **Khôi phục đúng cách:** Stop/restart thông qua các API/tool được hỗ trợ sau khi xác minh trạng thái cũ, không thêm identifying UUID để né lỗi.
11. **Đối soát trước publish:** Mọi source key có outcome hợp lệ, không double effect, không mất/quarantine bị bỏ quên.
12. **Cập nhật phòng ngừa:** Sửa scheduler leader/concurrency policy, thêm test simultaneous launch, restart, async rejection, redelivery và backfill.

### Những điều tuyệt đối không nên làm

- Mỗi worker gọi `JobLauncher.run(...)` với identifying timestamp riêng để “đánh dấu partition”.
- Dùng `JobExplorer.findRunningJobExecutions(...)` làm distributed lock duy nhất.
- Coi launcher async trả về là `COMPLETED`.
- Tăng launch executor pool để bù database lock contention.
- Mở JobInstance mới sau timeout mà không kiểm tra metadata của request cũ.
- Tự cập nhật `BATCH_JOB_EXECUTION` thành `COMPLETED` cho đẹp dashboard.
- Gọi thanh toán hoặc ghi ledger lần nữa bằng operation ID mới khi restart.

## 20. Lựa chọn kiến trúc theo bối cảnh

| Bối cảnh | Lựa chọn launch thường phù hợp | Lưu ý |
| --- | --- | --- |
| Batch nhỏ, chạy độc lập trong một container | External scheduler + launcher đồng bộ | Exit code phản ánh job terminal |
| Web/API nhận yêu cầu launch | Launcher bất đồng bộ + execution ID + monitor | Authorization, rate limit, không báo thành công sớm |
| Nhiều app replicas đều có lịch | Chỉ một scheduler leader hoặc clustered scheduling | Repository/idempotency vẫn bắt buộc |
| Partition local trên một JVM | Một manager JobExecution + local partition handler | Executor partition ≠ executor launcher |
| Worker trên nhiều pods/JVM | Một manager launch + remote partitioning/messaging | Shared metadata, correlation, worker liveness |
| Manager đọc/chia chunk, worker xử lý từ xa | Một manager launch + remote chunking | Broker redelivery và per-item idempotency |
| Kỳ dữ liệu có thể backfill | Stable businessDate/sourceVersion và run registry | Không dùng random identifying run ID cho replay |
| External effects có thể chưa rõ | Durable intent/outbox/reconciliation | Stop/restart chỉ khi outcome có bằng chứng |

### Quy tắc chọn nhanh

**Một logical input snapshot → một JobInstance.** Scheduler có thể gửi nhiều trigger, job có thể có nhiều `JobExecution` khi restart, và manager có thể điều phối nhiều worker `StepExecution`. **Đừng nhầm ba cấp identity này.**

## 21. Bài tập tình huống

Hệ thống xử lý 12 triệu records mỗi đêm bằng Spring Batch remote partitioning. Có ba pods ứng dụng đều bật `@Scheduled(cron="0 0 1 * * *")`, JobLauncher dùng thread pool async. Mỗi lần launch thêm `run.id=System.currentTimeMillis()` làm **identifying parameter**. Manager chia 16 partitions, worker ghi vào một database khác với `JobRepository` và phát sự kiện Kafka trực tiếp trong writer.

Đến 01:00:

- Ba pods cùng gửi trigger cho một `businessDate`.
- Scheduler thấy `JobLauncher.run(...)` trả về nhanh và log “Import completed”.
- Có nhiều JobInstances cùng xử lý một source snapshot.
- Một manager chết sau khi worker đã ghi dữ liệu nhưng trước khi nhận reply.
- Một operator restart bằng `run.id` mới; database đích có duplicate rows và downstream nhận duplicate events.

**Câu hỏi:**

1. Vì sao có thể sinh nhiều JobInstances dù dữ liệu cùng kỳ?
2. Vì sao `JobLauncher.run(...)` trả về nhanh không chứng minh job hoàn tất?
3. Nên thiết kế identifying `JobParameters` và source snapshot registration như thế nào?
4. Ba pods cần phối hợp scheduler ra sao? Tại sao chỉ thêm một `if (no active jobs)` không đủ?
5. Manager và remote workers cần chia sẻ những metadata nào?
6. Sau khi manager chết, có thể khẳng định worker chưa commit không? Vì sao?
7. Cần thay writer/Kafka path ra sao để hạn chế duplicate effects?
8. Khi muốn restart đúng kỳ, nên thao tác với JobInstance/JobExecution nào?
9. Bạn sẽ thêm những alerts/test nào để phát hiện sự cố trước production?

**Định hướng trả lời:** Mỗi timestamp identifying tạo một JobInstance mới, khiến repository không nhận diện đó là cùng logical input. Dùng `businessDate` và `sourceVersion` đã seal làm identity ổn định, scheduler cluster/leader chống trigger lặp nhưng vẫn dùng `JobRepository` và business idempotency. Launcher async chỉ xác nhận execution được tạo/dispatch, phải monitor terminal status. Manager tạo worker `StepExecution`/ExecutionContext, không gọi JobLauncher ở từng worker. Timeout/reply loss có thể xảy ra sau commit; cần unique business operation key, outbox/inbox hoặc provider idempotency, đối soát trước restart. Restart cùng JobInstance theo policy, không thêm run ID mới. Test multi-replica launch, async state, executor rejection, partition redelivery, manager crash, broker duplicate và business reconciliation.

## Tài liệu tham khảo

- [Spring Batch Reference — Running a Job](https://docs.spring.io/spring-batch/reference/job/running.html): `JobLauncher`, JobParameters và vận hành việc chạy job.
- [Spring Batch Reference — Job Parameters](https://docs.spring.io/spring-batch/reference/job/running.html#jobparameters): identifying parameters và JobInstance.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): repository và transaction khi tạo executions.
- [Spring Batch Reference — JobOperator](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): các chức năng vận hành/metadata liên quan.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, partitioning và xử lý từ xa.
- [Spring Batch Reference — Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote chunking, remote partitioning và middleware.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint, completed steps và restart.
- [Spring Batch API — TaskExecutorJobLauncher](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/launch/support/TaskExecutorJobLauncher.html): launcher với executor.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled`, cron và `TaskExecutor`.
- [Kubernetes Documentation — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): timezone, concurrencyPolicy, missed schedules và job retries.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction scopes và commit boundaries.

> **Ghi nhớ:** **Scheduler kích hoạt logical job; JobLauncher tạo JobExecution; manager step điều phối worker.** JobInstance phải có identifying parameters **ổn định theo kỳ/snapshot**, launcher async chỉ báo **đã khởi phát**, và nhiều replicas cần phối hợp trigger mà không làm mất rào chắn của `JobRepository`. Khi workload phân tán, restart và broker redelivery vẫn có thể lặp item: cần **checkpoint đúng, business idempotency, đối soát và quan sát đầy đủ** thay vì tạo JobInstance mới để né lỗi.
