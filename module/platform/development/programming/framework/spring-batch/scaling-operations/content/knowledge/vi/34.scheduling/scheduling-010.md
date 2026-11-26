# Điều phối worker theo lịch trong Spring Batch

> **Chương:** Scheduling
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán phù hợp. Bài học tập trung vào lịch khởi chạy, thời điểm cấp việc cho worker, giới hạn tài nguyên, thread safety, retry/restart và vận hành job an toàn khi nhiều tiến trình phối hợp.

Khi một job xử lý 30 triệu bản ghi bằng 20 worker, câu hỏi không chỉ là **“chạy job lúc mấy giờ?”**. Ta còn phải quyết định **khi nào cho phép worker nhận việc mới**, mỗi thời điểm có bao nhiêu worker, khi nào dừng nhận việc vì OLTP đang cao tải, xử lý công việc tồn đọng ra sao nếu lỡ một kỳ và cách tránh một partition bị hai worker cùng thực thi sau timeout.

Trong Spring Batch, **scheduler**, **JobLauncher**, **manager step**, **PartitionHandler**, **JobRepository** và **remote worker** có trách nhiệm khác nhau. Điều phối worker theo lịch là thiết kế các ranh giới phối hợp đó; **không phải gắn `@Scheduled` lên từng worker rồi gọi `JobLauncher.run(...)` tùy ý**.

## Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Phân biệt **lịch kích hoạt JobInstance**, **lịch phân phối partition/chunk**, **lịch cấp tài nguyên worker** và **lịch publish kết quả**.
2. Thiết kế một coordinator có `JobParameters` ổn định, không khởi chạy trùng logical job khi có nhiều scheduler replicas hoặc cron bị kích hoạt lại.
3. Chọn giữa **local partitioning**, **remote partitioning**, **remote chunking** và **work queue tự quản** theo yêu cầu điều phối theo giờ.
4. Hiểu `gridSize`, số partition, worker concurrency, số chunks đồng thời và capacity database là những khái niệm **khác nhau**.
5. Áp dụng khung giờ hoạt động, admission control, backpressure, autoscaling và graceful shutdown mà không phá checkpoint của job.
6. Thiết kế claim/lease/fencing cho **work queue tự quản** khi cần cấp việc động; phân biệt nó với cơ chế `StepExecution` của partitioning.
7. Vận hành miss schedule, backfill, retry/restart, trạng thái không rõ sau timeout và publish gate theo business date/snapshot.
8. Xây metrics, log, kiểm thử concurrency/fault injection và runbook cho hệ thống nhiều worker.

## 1. Tình huống thực tế: worker không thể chạy tối đa cả ngày

Một hệ thống bán lẻ có:

- Job tổng hợp giao dịch ngày hôm trước, input khoảng **30 triệu records**.
- **24 remote workers** có thể chạy trên các pods độc lập.
- Database nghiệp vụ phải ưu tiên người dùng từ 08:00 đến 22:00.
- Nhà cung cấp API chỉ cho tối đa một số request/s.
- Công việc cần hoàn tất trước thời điểm công bố báo cáo lúc 07:00.
- Một số partitions lớn hơn các partitions khác; có thể có worker crash.

Kịch bản điều phối ban đầu:

~~~text
00:30  Input snapshot được chốt.
01:00  Scheduler yêu cầu launch manager job.
01:00  Manager phân chia partitions theo manifest bất biến.
01:05  Workers nhận phần việc trong giới hạn capacity.
04:00  Worker lỗi được retry/restart theo policy, không tạo input mới.
06:00  Reconcile output/quarantine và kiểm tra publish gate.
07:00  Publish nếu đủ điều kiện; nếu không, alert và chặn công bố.
08:00  Giảm hoặc ngừng cấp workload batch mới để ưu tiên OLTP.
~~~

Đây là **chính sách ví dụ**, không phải chức năng tự động có sẵn trong Spring Batch. Muốn thực hiện đúng cần các thành phần orchestration, resource control, trạng thái bền vững và quan sát.

### Điều gì xảy ra khi chỉ có @Scheduled?

~~~java
// Anti-pattern khi cài trên mọi worker pod:
@Scheduled(cron = "0 0 1 * * *")
public void runEverything() {
    jobLauncher.run(importJob, new JobParameters());
}
~~~

Nếu 24 pods đều chứa bean này, mỗi pod có thể cùng gọi launcher lúc 01:00. Dùng `new JobParameters()` rỗng cũng không diễn đạt business date/snapshot; sau lần hoàn tất đầu, cùng `JobInstance` có thể không chạy lại theo ý định kỳ sau. Nếu mỗi pod thêm identifying timestamp để né lỗi, nhiều `JobInstance` cùng input có thể xuất hiện, dẫn tới nhân đôi side effect.

**Nguyên tắc đầu tiên:** Có **một logical manager launch cho mỗi kỳ dữ liệu**, còn scale worker thuộc **tầng phân công/tiêu thụ việc và capacity**.

## 2. Bốn loại lịch không được đánh đồng

| Lịch hoặc chính sách | Đơn vị được điều khiển | Ví dụ | Lưu trạng thái chính ở đâu? |
| --- | --- | --- | --- |
| **Job trigger schedule** | Một `JobInstance`/`JobExecution` | 01:00 mỗi ngày | Scheduler/run registry + `JobRepository` |
| **Work dispatch/admission** | Partition/chunk/work item được cấp | Không cấp thêm work khi DB bão hòa | Manager/handler/broker/queue |
| **Worker capacity schedule** | Số worker/consumer đang chạy | 24 replicas ban đêm, 4 ban ngày | Orchestrator/HPA/KEDA/worker pool |
| **Publication schedule/gate** | Bộ kết quả được công bố | Chỉ publish sau reconciliation | Business manifest/run registry |

Một scheduler có thể làm tốt loại thứ nhất nhưng không tự cung cấp ba loại còn lại.

### Phân biệt thời điểm và tính chất

- **Cron schedule** xác định *thời điểm kích hoạt*, không xác định job chạy bao lâu.
- **Time window** xác định *khoảng thời gian được phép nhận công việc mới*.
- **Concurrency limit** xác định *tối đa bao nhiêu việc được xử lý đồng thời*.
- **SLA deadline** xác định *khi nào phải có kết quả hoặc cảnh báo*.
- **Retry/backoff policy** xác định *khi nào thử lại một công việc lỗi*.
- **Restart policy** xác định *khi nào tạo execution mới cho cùng JobInstance*.

Không dùng một cron expression duy nhất để thay thế tất cả các quyết định trên.

## 3. Sơ đồ coordinator, manager và workers

~~~mermaid
flowchart TB
    SCH["External scheduler / cron"] --> CO["Launch coordinator<br/>business date, snapshot, policy"]
    CO --> JR[("JobRepository<br/>JobInstance/JobExecution")]
    CO --> JL["JobLauncher"]
    JL --> MAN["Manager JobExecution"]
    MAN --> PAR["Partitioner / chunk manager"]
    PAR --> ADM{"Admission & capacity<br/>within allowed window?"}
    ADM -- "Có" --> MSG["TaskExecutor / broker"]
    ADM -- "Chưa" --> HOLD["Hold/backpressure<br/>durable pending work"]
    MSG --> W1["Worker A"]
    MSG --> W2["Worker B"]
    MSG --> W3["Worker C"]
    W1 --> BD[("Business DB / storage")]
    W2 --> BD
    W3 --> BD
    W1 --> JR
    W2 --> JR
    W3 --> JR
    JR --> OBS["Monitoring / stop / restart"]
    BD --> REC["Reconciliation & publish gate"]
~~~

Sơ đồ ghép các **trách nhiệm logic**; không phải mọi kiến trúc Spring Batch có một class `AdmissionController` tích hợp. Với remote partitioning, có thể điều chỉnh worker consumer concurrency, broker dispatch và kích thước pool; với work queue tự quản thì admission áp dụng ngay ở bước claim.

### Nguồn chân lý cho mỗi nhiệm vụ

| Câu hỏi | Nguồn nên tra |
| --- | --- |
| Kỳ dữ liệu nào phải xử lý? | Business schedule/run registry + sealed input manifest |
| Job này đã chạy/đang chạy chưa? | `JobRepository` với identifying `JobParameters` |
| Worker step nào COMPLETED/FAILED? | `StepExecution` và `ExecutionContext` |
| Request đã tới worker chưa? | Middleware delivery/ACK/correlation |
| Tác dụng nghiệp vụ đã xảy ra chưa? | Business output/ledger/provider có thẩm quyền |
| Có nên nhận việc mới lúc này? | Admission policy + capacity telemetry |
| Có được publish không? | Reconciliation và quality gate |

**Không** suy ra output đã commit chỉ vì scheduler ghi “đã trigger”, manager nhận reply hay một pod chuyển `Ready`.

## 4. Chọn mô hình điều phối phù hợp Spring Batch

### 4.1. Local partitioning

Manager `PartitionStep` chia input thành các `ExecutionContext`, `TaskExecutorPartitionHandler` hoặc builder tương ứng chạy các worker `StepExecution` trên thread pool trong **cùng JVM**.

- Phù hợp khi một host đủ CPU/RAM/I/O và không cần nhiều máy.
- Điều phối lịch ở **manager** và giới hạn worker pool.
- Không tạo `JobExecution` riêng cho mỗi partition.
- Không giả định `@StepScope` làm reader stateful thread-safe trong **multi-threaded chunks**.

### 4.2. Remote partitioning

Manager phát **partition execution requests** qua middleware; workers chạy **worker step** trên JVM/pod khác.

- Tốt khi mỗi partition có input range/file/object rõ ràng.
- Worker có `StepExecution` và `ExecutionContext` riêng, metadata repository được chia sẻ theo kiến trúc.
- Có thể scale số consumers theo giờ hoặc backlog, nhưng thay worker count không đồng nghĩa được phép thay **partition mapping** trong cùng JobInstance.
- Một worker timeout có thể vẫn đang ghi dữ liệu; cần kiểm tra liveness, lease/fencing khi thích hợp, và writer idempotent.

### 4.3. Remote chunking

Manager thông thường **đọc input**, chia chunk requests, gửi worker để process/write và nhận replies.

- Worker capacity theo giờ có thể điều chỉnh số consumers và outstanding requests.
- Manager/reader là một nguồn tải riêng; worker thiếu capacity có thể làm **inflight/backlog** tăng.
- Broker requeue/ACK loss có thể khiến chunk được giao lại.
- Worker không cần tự gọi `JobLauncher` cho mỗi chunk.

### 4.4. Work queue tự quản

Nếu cần hàng triệu work units nhỏ, có độ ưu tiên, lease, scheduling per tenant hoặc reroute động, ứng dụng có thể dùng một bảng queue/transport có **claim** bền vững.

Đây là **một mô hình bổ sung/tùy biến**, không đồng nghĩa tự động với remote partitioning của Spring Batch. Nếu đã dùng Spring Batch remote partitioning và `JobRepository` để quản lý worker step executions, **không tạo thêm scheduler/lease độc lập cho cùng partition mà không có một mô hình ownership duy nhất**.

| Nhu cầu | Cách tiếp cận thường hợp lý |
| --- | --- |
| Ít partitions cố định, workload gần tương đương | Static partition plan + worker pool |
| Nhiều file/object khác kích thước | Partition theo file với grouping phù hợp, có theo dõi skew |
| Chunks chứa item payload và worker process/write độc lập | Remote chunking |
| Dữ liệu có thể chia theo tenant/range và đọc ngay tại worker | Remote partitioning |
| Nhiều nhiệm vụ nhỏ, claim/lease/retry tùy nghiệp vụ | Durable work queue/dispatcher có quyền sở hữu rõ |

## 5. Identifying JobParameters: lịch lặp không có nghĩa công việc mới

Giả sử mỗi ngày chạy một lần trên snapshot ngày hôm trước:

~~~text
jobName       = settlementImport
businessDate  = 2026-11-25
manifestId    = settlement-2026-11-25-v1
triggeredBy   = SCHEDULER
~~~

`JobInstance` được xác định bởi **job name + identifying JobParameters**; `JobExecution` là một lần chạy/restart của instance đó.

~~~text
JobInstance 100:
  settlementImport + businessDate=2026-11-25
  + manifestId=settlement-2026-11-25-v1

  JobExecution 501 FAILED
  JobExecution 502 COMPLETED (restart cùng JobInstance)
~~~

Đối với cùng logical period/snapshot:

- Lịch chạy lại, scheduler retry sau network timeout hoặc operator kích hoạt lại **không** tự tạo identifying timestamp mới.
- `triggeredBy`/request correlation có thể là **non-identifying**.
- Snapshot/manifest phải được **sealed**, không gọi LIST rồi đổi bộ input mỗi lần launch/restart.
- Khi `COMPLETED`, launch với cùng identifying parameters có thể bị từ chối bằng `JobInstanceAlreadyCompleteException`.
- Khi đang chạy, launch trùng có thể bị từ chối bằng `JobExecutionAlreadyRunningException`.
- Một instance `FAILED/STOPPED` có thể được restart nếu policy cho phép và trạng thái hợp lệ.

### Anti-pattern: phát sinh UUID mỗi cron tick

~~~java
new JobParametersBuilder()
    .addString("businessDate", businessDate, true)
    .addString("runId", UUID.randomUUID().toString(), true)
    .toJobParameters();
~~~

Mỗi `runId` identifying mới tạo **JobInstance khác**, cho dù input giống hệt. Điều đó có thể hợp lý với job ad-hoc độc lập có chủ đích, nhưng không nên được dùng để **lách trạng thái restart** của một kỳ dữ liệu.

## 6. Ví dụ scheduler kích hoạt manager một lần

Ví dụ Spring Batch 5.x / Java 17, sử dụng `@Scheduled` ở **dịch vụ coordinator chuyên trách**, không đặt cùng bean schedule trên mọi worker pod.

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class SettlementCoordinator {

    private static final Logger log =
            LoggerFactory.getLogger(SettlementCoordinator.class);
    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private final JobLauncher launcher;
    private final Job settlementImportJob;
    private final SealedManifestRegistry manifests;
    private final Clock clock;

    public SettlementCoordinator(
            JobLauncher launcher,
            @Qualifier("settlementImportJob") Job settlementImportJob,
            SealedManifestRegistry manifests,
            Clock clock) {
        this.launcher = launcher;
        this.settlementImportJob = settlementImportJob;
        this.manifests = manifests;
        this.clock = clock;
    }

    @Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")
    public void requestDailyRun() {
        LocalDate day = LocalDate.now(clock.withZone(BUSINESS_ZONE))
                .minusDays(1);

        // Registry phải bảo đảm cùng businessDate nhận cùng
        // immutable manifest, hoặc từ chối run chưa được seal.
        String manifestId = manifests.requireSealed(day);

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", day.toString(), true)
                .addString("manifestId", manifestId, true)
                .addString("triggeredBy", "SCHEDULER", false)
                .toJobParameters();

        try {
            JobExecution execution =
                    launcher.run(settlementImportJob, parameters);

            log.info("event=job_launch_accepted "
                    + "jobExecutionId={} status={} businessDate={} "
                    + "manifestId={}",
                    execution.getId(), execution.getStatus(),
                    day, manifestId);
        } catch (JobExecutionAlreadyRunningException ex) {
            log.info("event=duplicate_trigger_active businessDate={}", day);
        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info("event=duplicate_trigger_completed businessDate={}", day);
        } catch (JobRestartException | JobParametersInvalidException ex) {
            log.error("event=job_launch_rejected businessDate={}",
                    day, ex);
            // Chuyển alert/ticket cho operator theo policy ứng dụng.
        }
    }
}
~~~

`SealedManifestRegistry` là interface ứng dụng cần triển khai, ví dụ:

~~~java
import java.time.LocalDate;

public interface SealedManifestRegistry {
    String requireSealed(LocalDate businessDate);
}
~~~

Các public types ở snippets phải được đặt trong các file Java riêng. `Clock` cần được cấu hình thành bean và injected, tránh phụ thuộc giờ máy khi test. Bean scheduler cần được kích hoạt bằng `@EnableScheduling` và vận hành **chỉ trong coordinator deployment** hoặc dưới clustered scheduling/leader election có chủ đích.

**Không coi log `job_launch_accepted` là `COMPLETED`** nếu `JobLauncher` chạy bất đồng bộ. `TaskExecutorJobLauncher` có thể giao job sang executor và trả về khi execution còn `STARTING/STARTED`. Cần `JobExplorer`, `JobOperator` hoặc monitoring của orchestration để quan sát trạng thái cuối.

### Đồng bộ hay bất đồng bộ?

| Launcher | Khi nào phù hợp | Điều cần tránh |
| --- | --- | --- |
| **Đồng bộ** | Một command/container Batch chạy rồi thoát theo kết quả cuối | Scheduler tưởng job thành công khi process chưa kiểm tra status/exit |
| **Bất đồng bộ** | Web/API/coordinator cần trả lời nhanh rồi theo dõi execution | Tuyên bố hoàn tất ngay sau `run(...)` |

JobLauncher executor **không** phải worker executor/consumer pool. Tăng launcher threads chỉ có thể tăng số JobExecutions cùng được khởi phát, không làm một worker xử lý nhanh hơn.

## 7. Hai scheduler replicas: không dùng check-then-run như khóa phân tán

~~~mermaid
sequenceDiagram
    participant A as Scheduler A
    participant B as Scheduler B
    participant R as Shared JobRepository
    A->>R: findRunning... trả rỗng
    B->>R: findRunning... trả rỗng
    A->>R: run(job, same identifying params)
    B->>R: run(job, same identifying params)
    R-->>A: Xử lý theo identity/status repository
    R-->>B: Đã chạy/đã hoàn tất hoặc lỗi phù hợp
~~~

`JobExplorer.findRunningJobExecutions(...)` chỉ đọc dữ liệu tại thời điểm truy vấn. Hai replicas có thể cùng đọc “chưa có execution” rồi cùng launch. Đây là race **time-of-check-to-time-of-use**.

### Các hàng rào cần phối hợp

1. **Scheduler leader/cluster lock**: giảm việc nhiều coordinator cùng phát một trigger.
2. **Shared JobRepository**: bảo vệ JobInstance identity và execution lifecycle theo transaction/schema framework.
3. **Identifying JobParameters ổn định**: cùng kỳ/snapshot phải trỏ về một logical job instance.
4. **Business operation idempotency**: chống double effect khi worker request được phát lại hoặc có execution bị lỗi.
5. **Run registry và policy**: giải quyết backfill, cùng một kỳ nhiều snapshots, approval và publish.

Một lock TTL hết hạn **không chứng minh** manager hoặc workers của lượt trước đã dừng. Nếu lease được chuyển cho coordinator mới, cần phân biệt **quyền schedule** với **quyền business commit**; fencing/idempotency có thể vẫn cần ở đích.

## 8. Lịch gửi việc không phụ thuộc hoàn toàn vào cron

Ví dụ hệ thống cho phép batch dùng database tối đa 8 connections từ 08:00 đến 22:00, và 24 connections ngoài giờ. Nếu manager khởi động 01:00 nhưng job chưa xong lúc 08:00, cron ngày hôm sau **không quyết định** việc 08:00 có nên tiếp tục nhận thêm partitions.

### Admission control

~~~text
schedule_allowed = nằm trong cửa sổ nhận việc
resource_allowed = DB/API/broker còn capacity
job_allowed      = JobInstance/snapshot hợp lệ, chưa bị stop

dispatch_allowed = schedule_allowed AND
                   resource_allowed AND
                   job_allowed
~~~

Đây là **chính sách ứng dụng**, không phải method `StepBuilder.dispatchAllowed()`. Khi một điều kiện sai, cần:

- **Ngừng cấp thêm work unit**, nếu kiến trúc hỗ trợ hold/backpressure.
- Giữ trạng thái **durable pending** để công việc không biến mất khi process restart.
- Cho phép in-flight work hoàn tất/rollback tại boundary an toàn tùy policy.
- Không tự skip item chỉ vì “hết giờ”.

### Ngừng cấp việc khác stop toàn job

| Hành động | Hiệu quả | Rủi ro |
| --- | --- | --- |
| Giảm consumer concurrency | Giảm số request/chunk đang xử lý mới | Inflight vẫn cần được hoàn tất |
| Dừng dispatcher/queue claim | Giữ pending work bền vững | Manager có thể đang chờ reply |
| `JobOperator.stop(executionId)` | Yêu cầu dừng job theo lifecycle Batch | Cooperative; worker bị block trong I/O có thể chưa dừng ngay |
| Kill manager pod | Chấm dứt process manager | Remote workers vẫn có thể đang chạy; trạng thái có thể không rõ |
| Scale worker replicas về 0 | Tạm ngừng khả năng tiêu thụ | Có thể làm treo outstanding replies; có thể mất state trên local disk |
| Đặt `skipLimit` rất cao | Không phải phương án điều phối | Có thể làm mất dữ liệu hợp lệ |

Không được coi `JobOperator.stop` là một API **pause/resume không phá trạng thái** cho mọi kiến trúc: stop là yêu cầu kết thúc execution có kiểm soát; tiếp tục thường yêu cầu restart phù hợp và xử lý các ràng buộc liên quan.

## 9. Thiết kế time window và SLA theo timezone nghiệp vụ

Với workload ban đêm, nên ghi rõ:

~~~text
businessTimezone = Asia/Ho_Chi_Minh
launchAt          = 01:00
admissionWindow   = 01:00 - 06:00
processingDeadline= 06:30
publishDeadline   = 07:00
maxActiveWorkers  = 24
~~~

**Ba mốc khác nhau:**

- `launchAt`: bắt đầu yêu cầu job.
- `admissionWindow`: khoảng thời gian được phép cấp **việc mới**.
- `processingDeadline`: nếu còn pending/inflight, cần cảnh báo hoặc áp chính sách dừng.
- `publishDeadline`: thời hạn nghiệp vụ; **không** tự publish dữ liệu chưa đối soát.

### LocalDate từ lúc pod chạy có thể sai khi miss schedule

Một pod được khởi động bù lúc 10:00 ngày 27 có thể vẫn phải xử lý **businessDate ngày 25**, chứ không phải “ngày hôm qua tính tại thời điểm pod thực thi”.

Với backfill/misfire, schedule event nên mang:

~~~text
scheduledBusinessDate
scheduledFireTime
triggerRequestId
sealedManifestId
~~~

Các trường này phân biệt **kỳ dữ liệu dự kiến** với **thời điểm thực tế** nhận trigger. `LocalDate.now()` chỉ phù hợp khi chính sách businessDate thực sự “ngày hôm trước của thời điểm khởi chạy”; không phù hợp cho mọi ca backfill.

### DST

Timezone khác Việt Nam có thể có giờ 02:00 không tồn tại hoặc lặp khi chuyển daylight saving time. Lựa chọn scheduler (Quartz, Kubernetes CronJob, Spring `@Scheduled`, external orchestration) có quy tắc riêng. Cần test lịch trong timezone nghiệp vụ, không suy rằng cron local luôn chạy đúng một lần mỗi ngày.

## 10. Partition plan bất biến, capacity có thể thay đổi

Một câu hỏi thường gặp: **giảm workers từ 24 xuống 8 có làm thay đổi gridSize và các partition không?**

Không nên đánh đồng:

| Khái niệm | Ý nghĩa |
| --- | --- |
| `gridSize` | Tham số gợi ý/điều phối của partition step theo handler/partitioner |
| **Số partitions logic** | Số work units `Partitioner` thực sự tạo, phụ thuộc implementation |
| **Worker concurrency** | Số worker StepExecutions/consumer tasks đang chạy đồng thời |
| **Chunk size** | Số items mỗi chunk transaction ở worker |
| **JobLauncher pool** | Số jobs có thể khởi phát/đang thực thi trên executor |
| **DB pool** | Số connections có thể cùng phục vụ SQL |

Khi restart một `JobInstance`, **mapping partitionName → source range/file/snapshot phải giữ nguyên**. Có thể điều chỉnh số consumers/capacity theo kiến trúc và khả năng restart đã kiểm thử, nhưng **không** thay nguồn của `partition-0007` từ file A sang file B chỉ vì tối hôm sau có ít pods hơn.

### Ví dụ local partition manager

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;

@Bean
Step settlementManagerStep(
        JobRepository jobRepository,
        Partitioner manifestPartitioner,
        Step settlementWorkerStep,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("settlementManagerStep", jobRepository)
            .partitioner(
                    settlementWorkerStep.getName(),
                    manifestPartitioner)
            .step(settlementWorkerStep)
            .gridSize(12)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
~~~

Đây là **ví dụ local partitioning** cho Spring Batch 5.x, không phải cấu hình remote messaging. `manifestPartitioner` phải xây dựng partitions dựa trên manifest bất biến, không dựa vào danh sách input thay đổi lúc restart. `partitionTaskExecutor` là executor cho worker steps, **không phải** launcher executor. Mã còn cần job, worker step, beans và transaction managers đầy đủ.

## 11. Lịch theo năng lực: giới hạn tốc độ và backpressure

### Ví dụ capacity budget

Giả sử API downstream cho phép 300 requests/s và DB chỉ chịu khoảng 12 concurrent transactions batch trước khi tăng lock wait:

~~~text
Worker pool max = 12 (ban đầu để benchmark)
API rate limit  = 300 requests/s toàn cụm
DB pool budget  = đo theo thực tế, dành headroom cho OLTP
Chunk size      = 100 records, tùy workload
~~~

Không thể lấy `12 workers × 100 items` rồi suy ra đúng 1.200 DB connections. Mỗi worker có thể giữ connection trong thời gian khác nhau, service khác có pool riêng, và một worker có thể thực hiện nhiều HTTP requests cho một item.

### Backpressure đúng chỗ

| Nút thắt | Tín hiệu | Điều chỉnh ưu tiên |
| --- | --- | --- |
| DB pool hết slot | Connection wait/timeout | Giảm worker/chunk concurrency; sửa transaction dài |
| DB lock contention | Lock wait, deadlock, rollback | Phân vùng theo hot key, giảm writes đồng thời |
| API trả 429 | Retry/latency tăng | Token bucket/rate limit chung; bounded backoff |
| Broker backlog lớn | Queue depth/consumer lag | Xem worker capacity, network, message size |
| JobRepository chậm | Step metadata updates kéo dài | Giảm quá nhiều tiny partitions, tối ưu metadata IO |
| Object storage 503 | Request retries/latency | Giới hạn parallel GET/PUT và backoff |
| Worker CPU 100% | Processing latency | Scale CPU hoặc tăng workers khi downstream còn headroom |

**Không tăng worker chỉ vì queue depth lớn** khi database, API hoặc repository đã đạt giới hạn. Tăng concurrency trong outage còn có thể tạo retry storm.

### Retry lồng nhau

~~~text
Spring Batch item/chunk retry
    × HTTP SDK retry
    × broker redelivery
    × JobExecution restart

Tổng attempts thực có thể lớn hơn rất nhiều
so với một con số retryLimit trong cấu hình.
~~~

Điều phối theo lịch nên có **retry budget**, timeout, exponential backoff và jitter phù hợp tầng chịu trách nhiệm; tránh mọi worker cùng thức dậy và gọi downstream một lúc.

## 12. Worker theo cửa sổ: khi nào giữ job chạy, khi nào stop?

Có ít nhất hai kiến trúc phù hợp khác nhau.

### Kiến trúc A: một JobExecution hoàn tất trong một cửa sổ

~~~text
01:00 launch job
01:00..05:30 process tất cả partitions
05:30 reconcile
06:00 publish
~~~

Nếu quá deadline, phát alert và yêu cầu stop/restart có kiểm soát. Kiến trúc đơn giản khi đa số lần chạy hoàn tất trong cửa sổ và không cần pause qua nhiều ngày.

### Kiến trúc B: công việc bền vững tồn tại qua nhiều cửa sổ

~~~text
Ngày 1: claim/process một phần work queue
22:00: ngừng nhận việc mới, pending được giữ
Ngày 2: resume claim những work còn hợp lệ
Sau khi hoàn tất: reconcile và publish
~~~

Phù hợp với backlogs dài, input đã sealed và một **durable work queue** có owner/lease. Cần quyết định ranh giới **một JobInstance dài**, **nhiều JobInstances xử lý các batch slice**, hoặc một **orchestrated workflow** bao nhiều JobInstances; không được coi một StepExecution đã `STOPPED` là worker tự resume nguyên trạng qua ngày nếu không có cơ chế restart phù hợp.

### Điều gì nên đứng ngoài chunk?

Chính sách giờ làm việc, tenant priority, quota và autoscaling thường được điều phối ở **coordinator/worker pool/queue**, thay vì ném exception “ngoài giờ” trong processor cho mọi item rồi dựa vào skip/retry. Lỗi “không thuộc cửa sổ thời gian” không phải lỗi dữ liệu của từng record.

## 13. Durable work queue: một lựa chọn điều phối theo lịch

Phần này trình bày **mô hình tự quản lý work units** khi cần nhận việc động, không phải một schema tự động do Spring Batch tạo.

### 13.1. Trạng thái queue

~~~text
PENDING -> CLAIMED -> DONE
             |
             +--> RETRYABLE -> PENDING
             +--> QUARANTINED (lỗi item được xác nhận)
             +--> UNKNOWN (external effect cần reconcile)
~~~

Các trường tối thiểu:

- `work_id`: logical work unit ID duy nhất, không đổi qua retry.
- `manifest_id`: snapshot nguồn.
- `state`: trạng thái xử lý.
- `available_at`: khi nào được phép claim (retry delay/schedule).
- `lease_until`, `worker_id`: hạn sở hữu tạm thời.
- `claim_generation`: fencing token tăng khi đổi owner.
- `attempt_count`: số attempts được quản lý bền vững.
- `priority` và `tenant_id` khi cần fairness.
- `updated_at`, `last_error_code` cho vận hành.

### 13.2. Schema PostgreSQL minh họa

~~~sql
CREATE TABLE batch_work_queue (
    work_id            VARCHAR(160) PRIMARY KEY,
    manifest_id        VARCHAR(160) NOT NULL,
    tenant_id          VARCHAR(80) NOT NULL,
    partition_key      VARCHAR(160) NOT NULL,
    state              VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    priority           INTEGER NOT NULL DEFAULT 0,
    available_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    worker_id          VARCHAR(160),
    lease_until        TIMESTAMPTZ,
    claim_generation   BIGINT NOT NULL DEFAULT 0,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    last_error_code    VARCHAR(100),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_work_state CHECK (state IN (
        'PENDING', 'CLAIMED', 'RETRYABLE',
        'DONE', 'QUARANTINED', 'UNKNOWN'
    ))
);

CREATE INDEX idx_batch_queue_ready
    ON batch_work_queue
       (state, available_at, priority DESC, work_id);
~~~

**Không dùng work_id là JobExecutionId hoặc StepExecutionId** nếu work unit logic cần sống qua restart. Những execution IDs có thể thay đổi; business work ID phải ổn định và có liên hệ với manifest.

### Khi nào không nên làm queue riêng?

Nếu bạn đang dùng **Spring Batch remote partitioning chuẩn**, `JobRepository` đã có khái niệm worker `StepExecution` và checkpoint. Một bảng `batch_work_queue` khác chỉ nên được thêm khi có **phân định ownership rõ**: ai tạo work units, ai cập nhật DONE, làm sao đối soát với StepExecution? Nếu không, hệ thống sẽ có hai trạng thái “đã xong” có thể mâu thuẫn và khó restart.

## 14. Claim atomically bằng FOR UPDATE SKIP LOCKED

PostgreSQL hỗ trợ `FOR UPDATE SKIP LOCKED` để nhiều consumers claim các rows khác nhau trong cùng bảng queue. Ví dụ claim tối đa `:batchSize` work units đã đến giờ:

~~~sql
-- PostgreSQL, chạy trong transaction claim ngắn.
WITH picked AS (
    SELECT work_id
    FROM batch_work_queue
    WHERE state IN ('PENDING', 'RETRYABLE')
      AND available_at <= NOW()
    ORDER BY priority DESC, available_at, work_id
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE batch_work_queue AS q
SET state = 'CLAIMED',
    worker_id = :workerId,
    lease_until = NOW() + INTERVAL '5 minutes',
    claim_generation = q.claim_generation + 1,
    attempt_count = q.attempt_count + 1,
    updated_at = NOW()
FROM picked
WHERE q.work_id = picked.work_id
RETURNING
    q.work_id, q.manifest_id, q.partition_key,
    q.claim_generation, q.lease_until;
~~~

Đây là **PostgreSQL-specific SQL**; `:batchSize`/`:workerId` là placeholders của tầng ứng dụng, không phải cú pháp SQL thuần được chạy trực tiếp. Một transaction claim nên **commit sớm**, rồi worker xử lý ở transaction khác phù hợp.

### Ba lưu ý quan trọng

1. `SKIP LOCKED` giúp giảm tranh chấp khi **claim**, không bảo đảm FIFO tuyệt đối và có thể khiến một row bị bỏ qua nhiều lần nếu liên tục bị lock.
2. Khi claim transaction commit, hàng đã có `state='CLAIMED'`; worker chết sau đó khiến work **mắc kẹt** nếu không có lease recovery.
3. `claim_generation` chỉ hữu ích để chống stale owner nếu **mọi commit quan trọng** hoặc trạng thái hoàn tất kiểm tra fencing token; ghi một token vào DB mà writer bỏ qua nó thì không tạo ra an toàn.

### Complete có kiểm tra owner generation

~~~sql
UPDATE batch_work_queue
SET state = 'DONE',
    worker_id = NULL,
    lease_until = NULL,
    updated_at = NOW()
WHERE work_id = :workId
  AND state = 'CLAIMED'
  AND worker_id = :workerId
  AND claim_generation = :claimGeneration
  AND lease_until > NOW();
~~~

Ứng dụng phải kiểm tra **update count**:

- `1`: worker còn quyền sở hữu tại thời điểm cập nhật.
- `0`: lease hết, token/owner không khớp hoặc công việc đã chuyển trạng thái. **Không** ghi đè thành DONE mù.

Nếu business output và queue cùng database, cập nhật business row + DONE nên nằm **trong một transaction phù hợp**, đồng thời kiểm tra owner/fencing **trước khi tạo effect**. Nếu effect là HTTP/API khác DB, câu UPDATE này **không thể thu hồi** request mà worker cũ đã gửi. Dùng provider-side idempotency key, durable intent/outbox và reconciliation.

### Lease expiry không tự chứng minh worker đã chết

Worker A có lease đến 02:10, bị pause do GC đến 02:12. Worker B reclaims work, A tỉnh lại:

~~~text
02:09 Worker A: claim_generation = 7
02:10 lease A hết hạn
02:11 Worker B: claim_generation = 8
02:12 Worker A: tiếp tục thực thi công việc cũ
~~~

Nếu A không kiểm tra generation tại ranh giới ghi, cả A và B có thể phát side effects. **Stale owner** là một vấn đề độc lập với scheduler time window.

## 15. Lease renewal, reclaim và công việc chưa rõ kết quả

### Heartbeat

Worker có thể gia hạn lease khi vẫn khỏe và đang xử lý:

~~~sql
UPDATE batch_work_queue
SET lease_until = NOW() + INTERVAL '5 minutes',
    updated_at = NOW()
WHERE work_id = :workId
  AND state = 'CLAIMED'
  AND worker_id = :workerId
  AND claim_generation = :claimGeneration
  AND lease_until > NOW();
~~~

Heartbeat là **tín hiệu còn giữ quyền**, không phải bằng chứng đã commit mọi business records. Nếu update count = 0, worker phải nhận ra mình đã mất ownership và dừng tạo effects mới theo chính sách.

### Reclaim có kiểm soát

Một reaper/dispatcher riêng có thể tìm `CLAIMED` quá hạn:

~~~sql
SELECT work_id, manifest_id, claim_generation
FROM batch_work_queue
WHERE state = 'CLAIMED'
  AND lease_until < NOW()
ORDER BY lease_until;
~~~

**Không nhất thiết đưa mọi row hết lease về PENDING ngay**:

- Work unit có thể đã commit business output nhưng status reply chưa tới.
- Worker cũ có thể vẫn đang xử lý.
- Remote API có thể đã thực thi nhưng client timeout.
- Một job `STOPPING` có thể đang cần drain thay vì requeue.

Khi effect không rõ, chuyển sang **UNKNOWN** hoặc workflow reconcile tùy thiết kế, tra theo stable business operation ID trước khi retry. Với work thuần idempotent và tác dụng nằm trong cùng transaction DB, có thể reclaim có điều kiện, nhưng vẫn cần giới hạn attempts/backoff.

### Không đặt lease quá ngắn

Nếu chunk/operation bình thường chạy 3 phút, lease 30 giây không có heartbeat đúng sẽ gây reclaims giả. Đo P95/P99 task duration, GC pauses, API latency và network jitter; lease window, heartbeat cadence, timeout và recovery SLA phải tương thích.

## 16. Điều phối bằng worker autoscaling theo giờ và backlog

Trong Kubernetes, có thể điều chỉnh số replicas của **remote worker deployment** theo:

- Thời điểm ban đêm/ban ngày;
- Broker queue depth hoặc consumer lag;
- CPU/memory;
- API/backend capacity;
- Những công việc còn pending và deadline.

Ví dụ chiến lược:

~~~text
01:00-06:00:
  max worker replicas = 24
  scale theo queue lag và DB health

06:00-08:00:
  không dispatch task mới loại không khẩn cấp
  giữ đủ workers để drain các requests đang chạy

08:00-22:00:
  min workers = 2 (hoặc 0 nếu kiến trúc an toàn)
  chỉ xử lý workloads được ưu tiên
~~~

Các giá trị là **ví dụ policy**, không phải kích thước phù hợp mọi cluster.

### Autoscaling không bảo đảm correctness

| Chuyển đổi capacity | Rủi ro | Điều kiện an toàn |
| --- | --- | --- |
| 24 → 4 workers | Đang có 20 requests inflight | Graceful drain/ACK và termination grace |
| 4 → 24 workers | DB/API chưa đủ headroom | Rate limiter/connection pool/admission |
| Scale to zero | Manager vẫn chờ chunk reply | Durable messages, timeout và resume/monitor |
| Restart pod | Local staging/cache bị mất | Input immutable, checkpoint bền vững |
| Worker mới nhận task của worker cũ | Duplicate execution | Claim/fencing/idempotent writer |
| Scale tăng khi queue depth cao | Sequencer/DB có thể đang nghẽn | Scale theo bottleneck, không chỉ backlog |

Không coi HPA/KEDA worker replica count là số `JobInstance` hay partition identity. Worker instance là **năng lực thực thi**, có thể thay đổi; logical work vẫn cố định.

### Về KEDA/Cron scaler

KEDA có thể tích hợp với các nguồn metrics/queue hoặc lịch theo khung giờ tùy loại scaler/version. Khi dùng chính sách scale theo giờ:

1. Kiểm tra timezone và phiên bản controller.
2. Đảm bảo ngoài giờ vẫn có cách xử lý in-flight work.
3. Định nghĩa priority/urgent work nếu không được phép chờ đến ca sau.
4. Không chỉ dùng một scaler cron để khẳng định đủ capacity; quan sát backlog/latency/DB.
5. Thử scale-down, pod termination, broker reconnect và recovery trong môi trường gần production.

## 17. Kubernetes CronJob chỉ nên launch manager phù hợp

Nếu hệ thống chọn một container manager ngắn hạn cho mỗi kỳ, có thể dùng Kubernetes CronJob:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: settlement-manager
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
              image: example.registry/settlement-manager:1.0.0
              args:
                - "--app.batch.run-once=true"
                - "--spring.batch.job.enabled=false"
~~~

Đây là **manifest minh họa**:

- `app.batch.run-once` là flag **do ứng dụng tự định nghĩa**; cần một command runner/ApplicationRunner gọi launcher và kiểm tra terminal status.
- `spring.batch.job.enabled=false` có thể tránh cơ chế tự launch jobs lúc startup trong Spring Boot phù hợp; nó không tự khởi chạy job.
- Với launcher async, process **không được thoát 0 ngay sau khi submit** nếu muốn Kubernetes Job phản ánh việc thực thi Batch thực sự.
- `spec.timeZone` yêu cầu Kubernetes/controller có hỗ trợ tương ứng.
- `concurrencyPolicy: Forbid` tác động đến các Jobs thuộc **cùng CronJob resource**, không phải mọi manual triggers/replicas khác hoặc remote workers.
- Nếu job trước chạy lâu, `Forbid` có thể làm lịch mới bị bỏ/miss; cần backfill policy.

**Không tạo 24 CronJobs riêng**, mỗi cái tự launch cùng manager job chỉ vì muốn có 24 workers. Dùng remote worker Deployment/consumer pool và điều phối từ một manager.

## 18. Graceful shutdown và dừng trước giờ cao tải

Một yêu cầu kiểu “06:00 dừng workers ngay” có thể gây mất reply hoặc commit không rõ.

### Trình tự an toàn

~~~mermaid
flowchart TD
    T["Đến giờ đóng admission window"] --> A["Không nhận work mới"]
    A --> D["Cho in-flight chunk/partition drain"]
    D --> C{"Hoàn tất trong grace period?"}
    C -- "Có" --> S["Ghi status/ACK/checkpoint theo hợp đồng"]
    C -- "Không" --> U["Phân loại UNKNOWN/STOPPING<br/>xác minh worker/broker/business output"]
    S --> W["Giảm worker capacity"]
    U --> R["Reconcile + controlled stop/restart"]
    W --> M["Giám sát pending work kỳ sau"]
~~~

### Worker đang ở giữa transaction

Nếu worker hoàn tất một chunk rồi mới dừng, checkpoint và output có thể nhất quán. Nếu kill giữa chunk, business transaction chưa commit cần rollback; nhưng **external HTTP/Kafka side effects đã xảy ra** không tự rollback cùng DB.

Do đó:

- Tạo deadline/thời gian chờ lớn hơn thời gian hoàn tất một work unit hợp lý.
- Có timeout cho HTTP/DB/network; tránh thread treo vô hạn.
- Ngừng cấp requests mới ở broker/coordinator trước khi scale-down.
- Cho worker hoàn thành/ACK khi an toàn; nếu dừng cưỡng bức, cần recovery path.
- Không coi pod `Terminated` là `StepExecution.STOPPED` chắc chắn.

### JobOperator.stop

`JobOperator.stop(executionId)` gửi yêu cầu stop theo cơ chế Spring Batch; đây thường là **cooperative stop**, không cam kết interrupt tức thì tất cả remote processes. Với remote partitioning, phải kiểm tra adapter/transport và worker stop propagation thực tế; có trường hợp worker vẫn chạy sau khi manager đã mất liên lạc.

## 19. Missed schedule, backfill và thứ tự các kỳ

Giả sử coordinator ngừng hoạt động hai ngày:

~~~text
Đáng lẽ chạy:
  2026-11-24
  2026-11-25

Ngày 2026-11-26 coordinator khôi phục.
~~~

Không chỉ chạy `businessDate = yesterday` rồi bỏ mặc ngày 24. Hệ thống nên có **durable run registry**:

| Business date | Manifest | Run state | Hành động |
| --- | --- | --- | --- |
| 2026-11-24 | `m-24-v1` | `PENDING` | Backfill khi tài nguyên cho phép |
| 2026-11-25 | `m-25-v1` | `FAILED` | Xem xét restart đúng JobInstance |
| 2026-11-26 | Chưa seal | `WAITING_INPUT` | Chờ snapshot sẵn sàng |

### Coalesce hay chạy từng kỳ?

- Nếu mỗi ngày có **báo cáo độc lập**, có thể backfill từng kỳ theo thứ tự hoặc song song nếu không xung đột.
- Nếu kỳ sau **phụ thuộc kết quả kỳ trước**, cần dependency gate; không publish ngày 25 trước khi ngày 24 được xác nhận.
- Nếu workload cho phép tính lại từ snapshot mới, có thể coalesce theo policy rõ, nhưng phải giải thích **kỳ nào đã được thay thế**.

Một scheduler miss-fire policy đơn thuần **không biết business dependencies**. Tầng workflow/run registry cần quản lý chúng.

### Một logical input không nên tự đổi trong backfill

Khi backfill cùng businessDate, dùng `manifestId` đã sealed theo kỳ, không LIST “prefix ngày 24” sau khi upstream đã thêm/sửa file. Nếu muốn xử lý snapshot sửa đổi, tạo version mới với policy rõ và đối soát kết quả trước đó.

## 20. Stop, restart và lỗi chưa rõ trên nhiều workers

### State machine ở cấp JobExecution

~~~text
Launch request
   -> STARTING / STARTED
   -> COMPLETED
   -> FAILED / STOPPED
   -> (nếu restart được) execution mới cùng JobInstance
~~~

Các status cụ thể và transition phụ thuộc Spring Batch lifecycle và lỗi thực tế; `UNKNOWN` trong bài là **trạng thái nghiệp vụ ngoài framework** dùng khi external outcome chưa xác nhận, không phải `BatchStatus.UNKNOWN` được tự động hiểu như một hàng đợi cần replay. Không tự thay đổi JobRepository metadata để biến một execution stuck thành completed.

### Worker timeout không chứng minh worker chưa commit

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant B as Broker
    participant W as Worker
    participant D as Business DB
    M->>B: Dispatch partition P-7
    B->>W: Deliver P-7
    W->>D: Ghi output, COMMIT
    W--xM: Reply mất / worker mạng chậm
    M->>M: Timeout/uncertain
    Note over M: Chưa được coi P-7 là dữ liệu xấu
    M->>D: Reconcile business operation keys
    M->>M: Quyết định restart/resume theo chứng cứ
~~~

Các broker có behavior ACK/redelivery khác nhau. Có hệ thống redeliver request, có hệ thống cần operator retry; không giả định adapter luôn tự chữa mọi timeout.

### Restart đúng

1. Kiểm tra `JobInstance` + identifying parameters đúng snapshot.
2. Xác minh StepExecutions nào `COMPLETED`, `FAILED`, `STOPPED` hoặc chưa rõ.
3. Kiểm tra old worker process/lease/claim, xử lý stale owner.
4. Đối soát business effects đã commit và message/HTTP outcomes.
5. Restart cùng JobInstance khi hợp lệ, giữ partition mapping và checkpoint.
6. Đảm bảo writer idempotent nếu một phần work được replay.
7. Không tạo identifying `run.id` mới để “né” worker đang chạy.

## 21. Bảo vệ tác dụng nghiệp vụ khỏi trùng do schedule/retry

**Chống launch trùng không tương đương chống business effect trùng.** Dù chỉ có một JobInstance hợp lệ, crash/restart hoặc broker redelivery vẫn có thể đưa cùng item tới writer nhiều lần.

### Bốn lớp identity

~~~text
Logical job:
  (jobName, businessDate, manifestId)

Logical partition:
  (JobInstance identity, managerStep, partitionName)

Transport request:
  (chunk/partition correlationId, delivery/attemptId)

Business operation:
  (tenantId, operationId)
~~~

Mỗi lớp có mục đích khác nhau; `StepExecutionId` và `deliveryId` thay đổi theo attempt **không nên dùng** làm business operation ID.

### Ví dụ unique operation ledger

~~~sql
CREATE TABLE settlement_operation (
    tenant_id      VARCHAR(80) NOT NULL,
    operation_id   VARCHAR(160) NOT NULL,
    payload_hash   VARCHAR(128) NOT NULL,
    status         VARCHAR(30) NOT NULL,
    result_ref     VARCHAR(160),
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

Khi replay, writer:

- Kiểm tra key đã tồn tại và payload tương đương → no-op/đọc kết quả đã xác nhận.
- Nếu cùng key khác payload → **conflict** cần điều tra.
- Nếu operation chưa hoàn tất → retry theo state machine/transaction.
- Nếu external provider timeout → giữ `UNKNOWN` cho đến khi provider xác nhận.

Với transaction DB và event publish, cân nhắc **transactional outbox**. Outbox làm việc gửi event trở nên bền vững nhưng vẫn có thể phát lặp, nên consumer cần dedupe/idempotency.

## 22. Fairness: worker không nên luôn ưu tiên một tenant

Nếu một tenant có 10 triệu work units ưu tiên cao, một queue chỉ `ORDER BY priority DESC` có thể khiến các tenant khác **không bao giờ được chạy**.

### Chính sách có thể cân nhắc

- **Per-tenant quotas:** giới hạn active tasks/requests cho từng tenant.
- **Weighted fair scheduling:** chia capacity theo trọng số nhưng có phần tối thiểu cho nhóm nhỏ.
- **Aging priority:** work chờ lâu có thể được nâng ưu tiên theo policy.
- **Deadline-aware:** ưu tiên công việc gần SLA nhưng vẫn giữ dependency order.
- **Resource classes:** tasks I/O-heavy và CPU-heavy có pool khác nhau.
- **Hot-key routing:** những operations cùng aggregate cần serial order thì vào một lane thích hợp.

Các chính sách trên là **tầng orchestration/queue tùy biến**, không tự có khi đặt `gridSize`. Nếu chia work theo range/file tĩnh, fairness có thể đến từ **partition sizing và worker placement** thay vì dynamic claim queue.

### Khi nào work stealing phù hợp?

Work stealing giảm straggler nếu nhiều tasks độc lập có thể chuyển owner. Nhưng không được tự “cướp” phần việc của một worker vẫn đang commit:

- Claim cần lease/fencing hoặc cơ chế đảm bảo một owner hợp lệ.
- Side effect cần business idempotency.
- Input/operation identity phải giữ ổn định.
- Work đang có transaction dài hoặc stateful reader checkpoint phức tạp có thể **không thích hợp** để tách/chuyển tùy ý.

## 23. Observability: theo dõi cả lịch và worker

### Structured event names

~~~text
schedule_trigger_received
job_launch_accepted
job_launch_duplicate
partition_dispatched
worker_claimed
worker_heartbeat
worker_lease_expired
worker_completed
job_stop_requested
job_restarted
schedule_missed
backfill_enqueued
publish_blocked
~~~

Ví dụ event:

~~~json
{
  "event": "worker_lease_expired",
  "jobName": "settlementImport",
  "jobInstanceId": 100,
  "jobExecutionId": 502,
  "businessDate": "2026-11-25",
  "manifestId": "settlement-2026-11-25-v1",
  "partitionName": "file-0007",
  "workerId": "worker-pod-04",
  "claimGeneration": 7,
  "errorCode": "LEASE_TIMEOUT"
}
~~~

Đây là **schema log của ứng dụng**, không phải fields Spring Batch tự tạo. `partitionName`, `manifestId` và worker/correlation IDs cần được truyền qua `ExecutionContext`/message envelope phù hợp, rồi bind vào structured logger/MDC ở worker.

### Metric và cảnh báo

| Metric | Ý nghĩa |
| --- | --- |
| `scheduled_runs_expected_total` | Kỳ dữ liệu đến lịch cần xử lý |
| `scheduled_runs_missed_total` | Lịch bị miss mà chưa có run hợp lệ |
| `job_launch_duplicate_total` | Trigger lặp (không nhất thiết là incident) |
| `active_job_executions` | Số executions đang chạy |
| `active_worker_executions` | Worker thực sự đang xử lý |
| `pending_work_units` | Backlog work chưa claim/dispatch |
| `oldest_pending_age_seconds` | SLA backlog |
| `worker_lease_expired_total` | Workers mất quyền theo lease |
| `worker_retry_exhausted_total` | Attempts vượt retry budget |
| `step_rollback_total` | Chỉ báo DB/transaction issue |
| `broker_queue_depth` / `reply_latency` | Bottleneck remote transport |
| `db_connection_pool_wait_seconds` | DB capacity constraint |
| `business_output_mismatch_total` | Thiếu/trùng so với manifest |
| `publish_gate_blocked_total` | Không công bố do dữ liệu chưa đạt |

**Không gắn từng `workId`, `StepExecutionId` hoặc source record ID làm metric label** nếu cardinality cao. Dùng logs/audit cho chi tiết, metrics cho tổng hợp.

### Dashboard vận hành nên trả lời

1. Hôm nay có bao nhiêu business periods cần xử lý, đã trigger và chưa trigger?
2. Job nào đang chạy, đã failed hoặc chưa xác định terminal status?
3. Mỗi job có bao nhiêu partitions expected, running, completed, failed?
4. Worker capacity đang bằng bao nhiêu; có đang ở ngoài admission window?
5. Job đang bottleneck ở DB, broker, API, CPU hay thiếu workers?
6. Có leases expired, retries exhausted, duplicate claims/outputs?
7. Kỳ nào sắp trễ deadline hoặc chưa đạt publish gate?

## 24. Kiểm thử concurrency và lỗi theo lịch

Unit test scheduler tick đúng lúc không đủ. Cần kiểm tra repository, DB, broker và worker processes thật nếu mô hình phân tán.

### 24.1. Test JobParameters/định danh kỳ

Với cùng `businessDate` và `manifestId`:

- Hai scheduled triggers có cùng **identifying** JobParameters.
- `triggeredBy=SCHEDULER`/`OPERATOR` là non-identifying nếu dùng cho metadata.
- Không sinh `run.id` identifying khi retrigger cùng snapshot.
- Một businessDate có manifest chưa seal phải không được launch.
- Khi miss schedule rồi backfill, businessDate phải là **kỳ được yêu cầu**, không mặc nhiên ngày hôm qua của pod.

### 24.2. Test hai coordinators launch cùng job

1. Dùng database `JobRepository` giống production.
2. Hai threads/processes đồng thời gửi `JobLauncher.run(job, sameParams)`.
3. Dùng latch để giữ JobExecution đầu chưa kết thúc.
4. Xác minh không có **hai active executions hợp lệ cho cùng JobInstance** theo framework config.
5. Xác minh request còn lại nhận duplicate/restart-related status thay vì tự tạo JobInstance mới.
6. Kết thúc job, kiểm tra business effects không trùng.

Một test chỉ dùng `synchronized` singleton trong cùng JVM **không chứng minh** an toàn giữa hai scheduler pods.

### 24.3. Test cửa sổ giờ và deadline bằng Clock

~~~java
import java.time.Clock;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class AdmissionWindow {

    private final Clock clock;
    private final ZoneId zone;
    private final LocalTime from;
    private final LocalTime until;

    public AdmissionWindow(
            Clock clock, ZoneId zone,
            LocalTime from, LocalTime until) {
        this.clock = clock;
        this.zone = zone;
        this.from = from;
        this.until = until;
    }

    // Ví dụ đơn giản chỉ cho window nằm trong cùng một ngày.
    public boolean allowNewWork() {
        LocalTime now = ZonedDateTime.now(clock.withZone(zone))
                .toLocalTime();
        return !now.isBefore(from) && now.isBefore(until);
    }
}
~~~

Đây là **logic thuần ví dụ**, thích hợp test bằng `Clock.fixed(...)` và các trường hợp 00:59/01:00/05:59/06:00. Với window **qua nửa đêm** (như 22:00–06:00), predicate trên **không áp dụng** và phải viết/test logic khác. Kiểm thử còn cần timezone/DST nếu hệ thống chạy đa quốc gia.

**Không nhúng `allowNewWork()` trực tiếp vào `ItemProcessor` để mỗi item ngoài giờ ném exception rồi skip.** Nó phải được dùng ở lớp admission/dispatcher hay điểm kiểm soát nhận việc mới đúng kiến trúc.

### 24.4. Test atomic claim và fencing

Hai worker connections cùng claim từ work queue:

- Một `work_id` chỉ có **một owner/generation hợp lệ** tại thời điểm claim.
- Worker A mất lease, worker B reclaim generation mới; A không được hoàn tất bằng token cũ.
- Heartbeat của owner cũ sau khi generation đổi trả update count = 0.
- Worker crash ngay sau claim commit có đường reclaim theo policy.
- Nếu business output đã commit nhưng ACK/queue state chưa update, replay không tạo effect kép.
- Claim transaction rollback không làm mất `PENDING` work.

Test phải chạy trên DBMS thực và concurrency thật; mock in-memory không chứng minh `SKIP LOCKED` hay lock semantics.

### 24.5. Test worker autoscaling và drain

~~~text
Given: 12 workers, 50 partitions pending, 8 in-flight.
When : policy giảm capacity xuống 3.
Then :
  - không mất pending partitions;
  - in-flight hoàn tất/rollback theo timeout/grace;
  - không bị ghi hai business effects sau redelivery;
  - manager không tự đánh dấu các requests chưa xác nhận COMPLETED;
  - sau scale-up, worker mới tiếp tục từ trạng thái bền vững.
~~~

Thử kill/pause worker, broker disconnect, DB outage và scaling trong lúc commit để bắt đúng crash windows.

### 24.6. Ma trận fault injection

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Hai cron triggers cùng kỳ | Cùng JobInstance identity; không chạy business work hai lần |
| Async launcher trả ngay | Coordinator không báo `COMPLETED` trước status terminal |
| JobRepository outage | Launch fail/alert, không tạo run ID khác để lách |
| Cron miss một ngày | Run registry phát hiện, có backfill |
| Ngày có DST chuyển giờ | Không bỏ/nhân kỳ dữ liệu ngoài policy |
| Job kéo dài qua admission window | Không cấp work mới; in-flight được quản lý an toàn |
| Scale worker 20 → 4 | Không mất outstanding requests |
| Worker crash sau claim | Lease/recovery và idempotency |
| Worker cũ chạy sau lease expiry | Fencing token chống DONE sai; external effects có idempotency |
| Manager mất reply nhưng worker đã commit | Reconcile trước redelivery/restart |
| Worker rollback một chunk | Không báo business output đã commit |
| Source manifest đổi khi restart | Phát hiện conflict, không đổi input âm thầm |
| Requeue nhiều lần cùng work | Retry budget/available_at bền vững |
| Broker 429/backlog tăng | Backpressure và đo lag, không tăng worker mù |
| API downstream rate limit | Giới hạn requests toàn cụm và bounded retry |
| Partition skew lớn | Theo dõi straggler, không đổi mapping restart |
| Publish deadline đến khi còn pending | Chặn publish, alert thiếu dữ liệu |
| Job đa tenant | Fairness/quota không để tenant nhỏ starvation |

### 24.7. Kiểm thử kết quả nghiệp vụ

Sau bất kỳ fault injection nào, không chỉ assert `BatchStatus`:

- Set source business keys thuộc sealed manifest.
- Set outputs/operations đã xác nhận **duy nhất**.
- Set filtered/quarantined/pending/unknown theo hợp đồng.
- Không thiếu source key bắt buộc, không duplicate external operation.
- Các StepExecutions có status và checkpoint phù hợp với output đã commit.
- Những snapshots chưa đạt quality gate không được publish.

## 25. Runbook khi lịch và worker bị lệch nhau

Một operator nhận cảnh báo: “Job chạy từ 01:00, đến 07:00 còn 200 partitions; một số pods đã scale về 0.”

1. **Chốt identity:** Job name, identifying JobParameters, businessDate, sealed manifestId.
2. **Kiểm tra scheduler:** Có miss/duplicate trigger, leader failover hoặc CronJob overlap?
3. **Tra JobRepository:** `JobInstance`/`JobExecution` nào thực sự chạy; `StepExecution` nào `COMPLETED/FAILED/STARTED/STOPPED`?
4. **Đo backlog:** Expected partitions/chunks, pending, inflight, retrying, unknown.
5. **Xem admission:** Có đang ngoài window hoặc gate chặn do DB/API degraded?
6. **Xem worker capacity:** Replica count thực, readiness, broker connectivity, executor queue và scale-down events.
7. **Xác minh worker cũ:** Pod vừa chết có hoàn tất business commit chưa? Lease/fencing đã đổi owner chưa?
8. **Khoanh vùng bottleneck:** DB pool, lock wait, broker lag, object storage, API 429, CPU hoặc file skew.
9. **Tránh sửa sai:** Không tăng skipLimit để bỏ qua backlog; không tạo JobInstance mới bằng run ID khác.
10. **Khôi phục dependency/capacity:** Mở work admission có kiểm soát, điều chỉnh rate limit và pool theo headroom.
11. **Stop/restart hợp lệ:** Khi cần, dùng API lifecycle được hỗ trợ và xác minh old workers, metadata, checkpoint.
12. **Đối soát:** Unique business operations, output/checksum, quarantine, pending/unknown và retry effects.
13. **Quyết định publish:** Chỉ công bố sau khi quality gate và deadline policy được xét rõ; nếu trễ, báo trạng thái thật.
14. **Hậu kiểm:** Bổ sung regression tests cho cron miss, concurrency, scale-down, expiry và reply loss.

### Các anti-pattern cần tránh

- Mỗi remote worker tự bật `@Scheduled` rồi gọi `JobLauncher.run(...)` với timestamp khác.
- Thay đổi partition key → input range giữa các lần restart để phù hợp số pods mới.
- Coi `gridSize=24` là cam kết luôn có 24 worker active.
- Coi broker queue đã trống là mọi external side effects đã được xác nhận.
- Tắt worker pods ngay khi hết giờ mà không drain outstanding work.
- Coi lease expiry là bằng chứng worker cũ không còn chạy.
- Chỉ dùng `JobExplorer.findRunning...` làm distributed mutex.
- Tự sửa status trong bảng `BATCH_*` để unblock launcher.
- Chạy lại thanh toán với operation ID mới khi mất reply.
- Publish file/report trước khi đối soát những partitions chưa hoàn tất.

## 26. Bài tập tình huống

Một nền tảng xử lý **18 triệu giao dịch** mỗi đêm. Spring Batch manager sử dụng remote partitioning với 40 partitions và tối đa 20 worker pods, còn scheduler kích hoạt lúc 00:30. Từ 06:00 đến 22:00 phải giảm tải Batch; mỗi tenant có quota riêng.

Thiết kế ban đầu có các vấn đề:

- Cả 3 manager replicas cùng bật `@Scheduled` và thêm identifying `run.id=System.currentTimeMillis()`.
- Hệ thống set `gridSize=40` và kỳ vọng có 40 workers dù cluster chỉ có 20 pods.
- KEDA scale workers về 0 đúng 06:00 trong lúc một số partitions chưa gửi reply.
- Reaper thấy lease quá hạn và ngay lập tức cấp partition cho worker mới; worker cũ vẫn đang thực thi.
- Writer cập nhật balance qua DB và gửi payment API với idempotency key sinh mới mỗi lần retry.
- Một kỳ dữ liệu bị lỡ vì scheduler downtime, và operator chỉ chạy `businessDate=yesterday`.
- Báo cáo được publish khi manager `COMPLETED`, dù còn operation ở trạng thái `UNKNOWN` tại provider.

**Câu hỏi:**

1. Vì sao có thể sinh ba JobInstances cho cùng businessDate?
2. Phân biệt `gridSize`, số partitions và worker concurrency trong tình huống này.
3. Khi 06:00 đến, nên đóng admission, drain và stop/restart theo trình tự nào?
4. Lease hết hạn có đủ chứng minh worker cũ đã dừng? Cần token/guard gì?
5. Làm sao tránh thanh toán hai lần sau timeout và replay?
6. Lịch bị lỡ phải được backfill bằng businessDate/manifest nào?
7. Làm sao bảo đảm tenant nhỏ không bị queue của tenant lớn chặn mãi?
8. Những nguồn nào cho biết một worker đã commit: broker reply, StepExecution hay business ledger?
9. Khi nào được publish báo cáo?
10. Bạn sẽ thêm những concurrency/fault-injection tests và metrics nào trước production?

**Định hướng trả lời:** Scheduler leader hoặc clustered orchestration giảm trigger trùng; identifying parameters dùng businessDate và sealed manifest ổn định để `JobRepository` nhận diện cùng JobInstance. Manager chia 40 logical partitions, nhưng chỉ cấp work theo capacity 20 workers và admission window. Khi đóng window, dừng phân phối mới và drain các work đang chạy; kiểm tra ownership/lease trước retry, dùng fencing + stable business operation ID và provider idempotency. Không tạo payment key mới sau timeout; giữ `UNKNOWN` cho tới reconciliation. Run registry bảo lưu các kỳ bị miss để backfill. Fair scheduling/quotas áp theo tenant. Publish gate phải kiểm tra manifest, outcomes và external effects, không chỉ manager status.

## Tài liệu tham khảo

- [Spring Batch Reference — Running a Job](https://docs.spring.io/spring-batch/reference/job/running.html): `JobLauncher`, `JobParameters`, JobInstance và JobExecution.
- [Spring Batch Reference — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): metadata, transaction và concurrent launches.
- [Spring Batch Reference — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobExplorer`, `JobOperator` và vận hành.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, partitioning và parallel workers.
- [Spring Batch Reference — Remote Partitioning / Chunking](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): mô hình message-driven manager/worker.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint, restart và `ItemStream`.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): status/counters và `StepExecution`.
- [Spring Framework Reference — Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled`, cron, executor và scheduler.
- [Kubernetes Documentation — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): concurrencyPolicy, timezone và missed schedules.
- [Kubernetes Documentation — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): shutdown và termination.
- [KEDA Documentation — Scalers](https://keda.sh/docs/latest/scalers/): worker scaling dựa trên sự kiện/metrics và các scaler theo lịch.
- [PostgreSQL Documentation — SELECT](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE SKIP LOCKED`.
- [PostgreSQL Documentation — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locking và transaction boundaries.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): commit, rollback và external resource boundaries.

> **Ghi nhớ:** **Lịch kích hoạt manager không phải lịch cho mỗi worker tự tạo JobInstance.** Hãy dùng identifying parameters và sealed input manifest ổn định, để manager/partition handler điều phối đúng worker executions, còn worker capacity và admission được điều chỉnh bằng schedule, backlog, quotas và sức chịu tải thực. Khi worker được dừng hoặc cấp lại việc, phải giữ checkpoint, ownership/fencing và business idempotency; khi có timeout hay side effect chưa rõ, cần **reconciliation trước restart/publish**. Tăng số pods mà không kiểm soát các ranh giới này chỉ làm rủi ro mất/trùng dữ liệu lớn hơn.
