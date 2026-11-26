# Restart sau cửa sổ chạy trong Spring Batch

## Mục tiêu bài học

Một job Spring Batch được scheduler kích hoạt hằng đêm lúc 01:00, dự kiến kết thúc trước 04:00. Lúc 03:50 worker gặp lỗi database và `JobExecution` chuyển thành `FAILED`. Database phục hồi lúc 05:20, tức **sau cửa sổ chạy ban đầu**. Có nên restart lúc 05:30? Nếu làm vậy, job phải xử lý **business date nào**, có đụng với lịch của kỳ tiếp theo không, và phải thông báo downstream như thế nào khi SLA đã trễ?

**Restart sau cửa sổ chạy** kết hợp hai cơ chế vốn **độc lập**:

1. **Spring Batch restart semantics:** tiếp tục một `JobInstance` thất bại hoặc bị dừng từ `JobRepository` và `ExecutionContext`.
2. **Scheduling/business policy:** khi nào được khởi chạy, cho phép recovery ngoài lịch tới đâu, có hard stop hay chỉ có hạn giao kết quả, và các kỳ xử lý được phép chồng lấn không.

Spring Batch có thể cho phép restart về mặt kỹ thuật dù scheduler đã hết giờ. Ngược lại, scheduler vẫn có thể phát trigger kỳ sau dù job kỳ trước chưa hoàn tất. **Chính sách ứng dụng phải nối hai thế giới này** để không xử lý nhầm business date, nhân đôi side effects hoặc bỏ qua yêu cầu đối soát.

Bài thuộc chương **Scheduling**, module **SPRING_BATCH_SCALING_OPERATIONS**: mở rộng Spring Batch cho workload dữ liệu lớn với multi-threaded step, parallel steps, partitioning và phân tán; đo bottleneck, giữ thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế.

Sau bài này, bạn có thể:

- Phân biệt trigger time, start window, execution deadline, business cutoff, SLA deadline và recovery window.
- Hiểu JobInstance, JobExecution, identifying JobParameters và checkpoint khi restart.
- Lựa chọn late restart, stop, fail, backfill hay manual approval.
- Tránh tạo JobInstance mới khi mục tiêu là restart kỳ cũ.
- Dùng JobOperator/JobLauncher với policy gate và chống concurrent launch.
- Phân biệt scheduler misfire với Spring Batch failed execution.
- Bảo vệ source snapshot, partition ranges, file output và side effects.
- Phối hợp late restart với kỳ tiếp theo, worker capacity, downstream và SLA.
- Kiểm thử fault injection, giám sát và viết runbook phục hồi.

## 1. Ví dụ mở đầu: thất bại trước giờ đóng cửa sổ

Giả sử pipeline `dailySettlementJob`:

~~~text
Business date           : 2026-11-25
Scheduler trigger       : 2026-11-26 01:00 Asia/Ho_Chi_Minh
Start window            : 01:00–04:00
SLA publish             : 04:30
JobExecution #8100      : STARTED 01:02
Worker DB outage        : 03:48
JobExecution #8100      : FAILED 03:51
DB phục hồi             : 05:20
Operator xem sự cố      : 05:30
~~~

Ba kết luận khác nhau:

- **Kỹ thuật:** nếu job restartable, checkpoint hợp lệ và framework cho phép, JobExecution mới có thể tiếp tục **cùng JobInstance**.
- **Lịch:** cửa sổ 01:00–04:00 đóng rồi. Scheduler không mặc nhiên có quyền phát lệnh lúc 05:30.
- **Nghiệp vụ:** SLA 04:30 đã trễ. Restart muộn không làm kết quả đó thành “đúng giờ”.

Câu hỏi vận hành thực sự là: **restart sau cửa sổ có an toàn, hợp lệ và còn ý nghĩa với dữ liệu/downstream không?**

## 2. Sáu mốc thời gian cần tách bạch

| Mốc | Ý nghĩa | Khi restart kỳ cũ |
| --- | --- | --- |
| `scheduledAt` | Lúc scheduler dự kiến phát trigger | Giữ audit gốc |
| `startWindowOpen/Close` | Khoảng cho phép **bắt đầu** | Không âm thầm dời |
| `executionDeadline` | Hạn dừng hoặc hoàn tất nếu là hard deadline | Tuân thủ policy |
| `businessDate` | Kỳ dữ liệu nghiệp vụ | **Giữ nguyên** |
| `sourceCutoff/sourceVersion` | Snapshot nguồn đã chốt | **Giữ nguyên** |
| `publishSlaAt` | Hạn kết quả phải tới downstream | Giữ để ghi nhận trễ |

Thêm `recoveryAllowedUntil` là hạn cuối được phép **restart kỳ cũ** không cần ngoại lệ.

### Start window không nhất thiết là hard stop

- **Start window:** cấm khởi chạy một job mới ngoài khoảng này; job đã bắt đầu có thể tiếp tục qua giờ đóng.
- **Execution window/hard stop:** không cho work tiếp tục sau một deadline; cần cơ chế stop/rollback có kiểm soát.
- **SLA deadline:** vượt thời hạn là vi phạm SLA, nhưng job có thể cần hoàn tất để đảm bảo dữ liệu.
- **Recovery window:** khoảng riêng cho late restart/backfill của kỳ cũ.

Không dùng một trường `endTime=04:00` rồi suy ra đồng thời cả bốn chính sách.

## 3. Timeline: hết giờ khởi chạy không đồng nghĩa transaction dừng

~~~mermaid
flowchart LR
    A["01:00 trigger"] --> B["01:02 running"]
    B --> C["03:51 failed"]
    C --> D["04:00 start window closes"]
    D --> E["04:30 SLA breached"]
    E --> F["05:20 dependency recovers"]
    F --> G{"05:30 late restart policy?"}
    G -->|Allowed| H["Restart same JobInstance"]
    G -->|Forbidden| I["Manual review/backfill"]
~~~

Nếu scheduler chỉ dùng **start window**, một JobExecution đang STARTED trước 04:00 có thể tiếp tục sau 04:00. Nếu nghiệp vụ có hard stop, phải gửi stop request có kiểm soát; một cron expression **không tự rollback** các chunk đang xử lý.

Nếu late restart hoàn thành lúc 06:15, ghi nhận thực tế là `completedLate=true`/vi phạm SLA, không sửa lại `publishSlaAt` cho đẹp dashboard.

## 4. JobInstance, JobExecution và ExecutionContext

Spring Batch phân biệt:

- **Job:** định nghĩa Steps/flow.
- **JobInstance:** đơn vị xử lý logic, xác định bởi **Job name + identifying JobParameters**.
- **JobExecution:** một attempt thực thi JobInstance.
- **StepExecution:** metadata thực thi của Step trong một attempt.
- **ExecutionContext:** checkpoint/input offsets và state phục vụ restart khi component hỗ trợ.

~~~mermaid
flowchart TB
    J["Job: dailySettlementJob"] --> I["JobInstance: businessDate=2026-11-25, source=V17"]
    I --> E1["JobExecution #8100 FAILED"]
    I --> E2["JobExecution #8155 STARTED → COMPLETED"]
    E1 --> C1["Old StepExecutions / checkpoints"]
    E2 --> C2["Restarted StepExecutions"]
~~~

Một restart hợp lệ tạo JobExecution mới nhưng giữ **JobInstance cũ**, không tự biến failed business date thành kỳ hiện tại. JobInstance đã COMPLETED thường không được restart như một lần lỗi; reprocess phải có phiên bản/bộ tham số mới với chủ đích và đối soát.

### Sai lầm nguy hiểm

Nếu operator luôn thêm `run.id=System.currentTimeMillis()` làm **identifying JobParameter**, lệnh “chạy lại” có thể tạo JobInstance mới và bắt đầu xử lý input từ đầu thay vì resume checkpoint. Với thanh toán, output append hoặc event publication, đây là cửa sổ duplicate nghiêm trọng.

## 5. Identifying JobParameters: giữ kỳ dữ liệu ổn định

Ví dụ contract:

~~~text
jobName=dailySettlementJob
businessDate=2026-11-25              [IDENTIFYING]
sourceGeneration=source-V17          [IDENTIFYING]
cutoffUtc=2026-11-25T17:00:00Z       [IDENTIFYING]
scheduledAtUtc=2026-11-25T18:00:00Z  [NON-IDENTIFYING]
dispatchRequestId=trigger-0100       [NON-IDENTIFYING]
~~~

Nếu restart lúc 05:30, không đổi businessDate, sourceGeneration hoặc cutoffUtc. Non-identifying parameters phục vụ audit cũng cần được quản lý nhất quán; không để đọc dữ liệu phụ thuộc `LocalDate.now()` khi chạy lại.

Java 17, Spring Batch 5.x:

~~~java
import java.time.Instant;
import java.time.LocalDate;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

public final class SettlementParameters {

    private SettlementParameters() {}

    public static JobParameters forBusinessRun(
            LocalDate businessDate,
            String sourceGeneration,
            Instant cutoff,
            Instant scheduledAt) {

        return new JobParametersBuilder()
                .addString(
                    "businessDate",
                    businessDate.toString(), true)
                .addString(
                    "sourceGeneration",
                    sourceGeneration, true)
                .addString(
                    "cutoffUtc", cutoff.toString(), true)
                .addString(
                    "scheduledAtUtc",
                    scheduledAt.toString(), false)
                .toJobParameters();
    }
}
~~~

**Quy tắc thiết kế:** hai executions phải chia sẻ checkpoint/business output của cùng một run thì cần cùng identifying parameters. Nếu thay source snapshot hoặc transform contract, hãy tạo run revision mới có lineage thay vì thay đổi dữ liệu bên dưới JobInstance cũ.

## 6. Retry, restart, re-run và backfill là bốn hành động khác nhau

| Khái niệm | Ý nghĩa | Không nên nhầm |
| --- | --- | --- |
| **Chunk retry** | Thử lại transaction/chunk lỗi | Không thay business period |
| **Job restart** | JobExecution mới trong **cùng JobInstance** | Không tạo run.id mới theo đồng hồ |
| **Re-run** | Xử lý lại có chủ đích theo logic đã định | Có thể cần revision/output mới |
| **Backfill** | Bù một hay nhiều business periods quá hạn | Không phải tự động continue checkpoint |
| **Scheduler retry** | Scheduler thử dispatch lại trigger | Không chắc job trước chưa launch |
| **Message redelivery** | Broker giao lại request chưa ACK | Worker trước có thể đã commit |
| **Recovery workflow** | Kiểm tra/repair state sau lỗi | Không phải lúc nào cũng gọi restart |

Nếu operator gọi `startNextInstance` hoặc phát JobParameters ngẫu nhiên thay vì `restart`, đó có thể là **khởi động instance kế tiếp**, không phải phục hồi kỳ cũ.

## 7. Trạng thái BatchStatus và quyết định phục hồi

| BatchStatus | Điều thường cần làm |
| --- | --- |
| `COMPLETED` | Không restart bình thường; muốn reprocess cần revision/contract mới |
| `FAILED` | Xem restartability, source/checkpoint và policy cửa sổ |
| `STOPPED` | Có thể restart nếu job/steps và nghiệp vụ cho phép |
| `STARTING`/`STARTED` | Có thể vẫn chạy hoặc metadata stale; xác minh worker ownership |
| `STOPPING` | Chờ stop hoàn tất hoặc reconcile |
| `ABANDONED` | Không coi là mặc định được auto-restart; runbook riêng |
| `UNKNOWN` | Không biết commit/state chính xác; cần đối soát trước hành động |

**Không kết luận process chết chỉ vì manager timeout hoặc JobRepository có trạng thái cũ.** Một worker remote partitioning có thể còn chạy và commit. Nếu restart khi phần việc cũ vẫn chạy, có thể tạo hai worker cùng ghi một business key.

### Restartable ở hai cấp độ

1. **Framework:** Spring Batch có chấp nhận restart (trạng thái, `preventRestart`, Step configuration, metadata)?
2. **Business policy:** dữ liệu, lịch, downstream, approval và ownership có cho phép **late restart**?

Chỉ khi cả hai đều PASS mới dispatch.

## 8. Decision matrix khi quá cửa sổ

| Tình huống | Hướng xử lý | Lưu ý |
| --- | --- | --- |
| Trước giờ đóng, còn deadline | Restart/retry theo budget | Phải giữ cùng JobInstance |
| Qua cửa sổ nhưng còn recovery allowance | Late restart có audit | Ghi nhận SLA trễ |
| Quá recovery deadline | Manual review/backfill | Không tự dời business date |
| Kỳ cũ đã được publish | Không ghi đè | Correction version/compensating run |
| Kỳ mới sắp bắt đầu | Serialize/queue hoặc song song nếu độc lập | Tính DB/worker capacity |
| Input phiên bản gốc đã mất | Không resume trên input mới | Fail recovery, tổ chức reprocess |
| Metadata STARTED nhưng worker không liên lạc | Reconcile status và ownership | Tránh duplicate execution |
| Broker/DB đang outage | Backoff/hold, không restart storm | Đợi dependency an toàn |
| Hard stop theo quy định | Stop/quarantine, xin approval | Không “mượn” thêm giờ |
| Chỉ SLA publish đã trễ | Có thể vẫn hoàn thành muộn | Downstream nhận late correction có kiểm soát |

Các ngưỡng là quyết định nghiệp vụ/vận hành, **không tự suy ra từ Cron**.

## 9. Immutable source snapshot khi restart muộn

Một lỗi thường gặp:

~~~text
JobExecution #8100:
  đọc file V1 và checkpoint record 800000

05:00 upstream ghi V2 đè cùng tên file

JobExecution #8155 restart:
  đọc từ record 800001 của V2

Output = prefix V1 + suffix V2
~~~

Checkpoint số thứ tự vẫn có thể “hợp lệ” về mặt offset nhưng output **không thuộc cùng một tập nguồn**.

Cần:

- Pin source object generation/version hoặc immutable URI khi tạo JobInstance.
- Lưu checksum/schema/transform version/cutoff có thể xác minh khi restart.
- Với database reader, dùng business snapshot/cutoff/version policy nhất quán.
- Giữ deterministic partition ranges, names và source identity qua attempts.
- Nếu snapshot V1 mất, **không** lấy V2 rồi tự nhận là restart; chạy reprocess/backfill revision mới.
- Với file writer, xác minh partial output, file offset và ItemStream semantics trước khi append.

**Checkpoint chỉ có giá trị khi input có thể được tái lập.**

## 10. Timezone, business calendar và DST

Không suy `businessDate` từ `LocalDate.now()` của worker sau restart. Với lịch tại Việt Nam:

~~~text
businessDate   = 2026-11-25
scheduledLocal = 2026-11-26 01:00 Asia/Ho_Chi_Minh
scheduledUtc   = 2026-11-25T18:00:00Z
sourceCutoff   = 2026-11-25T17:00:00Z
~~~

Lưu mốc thời gian kỹ thuật bằng `Instant/UTC` và vùng giờ chính sách bằng `ZoneId`. Business date là giá trị nghiệp vụ, không phải một timestamp tình cờ.

Ở các vùng có DST, giờ local có thể mất hoặc lặp; một cron 01:30 có thể diễn giải khác nhau tùy scheduler và ngày. Cần kiểm thử ngày chuyển giờ, ngày nghỉ thị trường và lịch ngân hàng, tách **scheduled occurrence** khỏi `businessDate`.

## 11. Scheduler misfire không giống JobExecution FAILED

~~~text
A. Scheduler down 01:00–02:00:
   Trigger 01:00 bị bỏ lỡ (misfire).
   Có thể chưa có JobExecution nào.

B. Trigger đã phát và JobExecution #8100 FAILED:
   Cần Job restart, không chỉ tạo misfire trigger.

C. Scheduler gọi JobLauncher, response timeout:
   JobExecution có thể đã STARTED.
   Phải tra JobRepository trước khi gọi lại.
~~~

**Misfire:** scheduler bỏ lỡ planned trigger. **Failed execution:** batch đã được launch và thất bại. **Uncertain dispatch:** không biết launcher đã nhận yêu cầu hay chưa.

Trước khi thử bù trigger, hỏi: *đã tồn tại JobInstance cho business period này chưa; nếu có thì trạng thái thật và ownership là gì?*

## 12. Kubernetes CronJob, Quartz và Spring @Scheduled

| Công cụ | Phụ trách | Không tự làm |
| --- | --- | --- |
| **Spring @Scheduled** | Kích hoạt method trong process theo lịch | Durable distributed lock, Batch checkpoint |
| **Quartz** | Triggers/misfire và durable job store khi cấu hình | Không thay JobRepository semantics |
| **Kubernetes CronJob** | Tạo Kubernetes Jobs theo Cron | Không tự restart JobInstance cũ |
| **Enterprise scheduler** | Dependency, calendar, approval, SLA | Không tự hiểu ExecutionContext |
| **Spring Batch JobRepository** | Lưu execution metadata/checkpoint | Không có business recovery window mặc định |

Với Kubernetes CronJob:

- `concurrencyPolicy` (`Allow`, `Forbid`, `Replace`) nói về các Kubernetes Jobs thuộc CronJob, không kiểm soát mọi Spring Batch executions được launch theo đường khác.
- `startingDeadlineSeconds` giới hạn mức trễ để một **schedule bị bỏ lỡ** còn được khởi chạy, không phải giới hạn restart của JobExecution đã FAILED.
- `timeZone` ở phiên bản hỗ trợ kiểm soát cách diễn giải Cron, không thay business date parameter.
- `Replace` có thể chấm dứt job cũ để chạy kỳ mới, nguy hiểm nếu worker StepExecution đang xử lý/chưa checkpoint.
- `backoffLimit` của Kubernetes Job và Spring Batch job/chunk retry là các tầng khác nhau.

**Không dựa duy nhất vào `Forbid` hoặc một scheduler leader lock để chứng minh không có hai instances cùng ghi business output**: có thể vẫn có manual launches và remote workers cũ đang chạy.

## 13. State machine điều phối late restart

Một ứng dụng có thể có **business-run ledger** riêng để điều phối, nhưng ledger không thay thế JobRepository:

~~~mermaid
stateDiagram-v2
    [*] --> SCHEDULED
    SCHEDULED --> RUNNING: Start window + launch PASS
    RUNNING --> SUCCEEDED: Job COMPLETED + output gate PASS
    RUNNING --> FAILED: Step/Job failure
    FAILED --> RECOVERY_ELIGIBLE: Policy, snapshot, ownership PASS
    FAILED --> MANUAL_REVIEW: Quá hạn hoặc trạng thái không chắc
    RECOVERY_ELIGIBLE --> RESTARTING: Durable claim + audit
    RESTARTING --> RUNNING: New JobExecution
    MANUAL_REVIEW --> RECOVERY_ELIGIBLE: Approved
    FAILED --> EXPIRED: Recovery forbidden
    SUCCEEDED --> [*]
    EXPIRED --> [*]
~~~

Đây là state machine **do ứng dụng đề xuất**, không phải enum Spring Batch. Các trạng thái ledger cần reconcile được với JobRepository.

Chỉ chuyển sang RECOVERY_ELIGIBLE khi:

- Tìm được đúng JobInstance và identifying parameters của kỳ cũ.
- Framework cho phép restart (status/restartability).
- Không có JobExecution/worker cũ đang chạy hoặc ownership UNKNOWN.
- Business date, source snapshot, cutoff, transform version không thay.
- Recovery window còn hiệu lực hoặc đã được phê duyệt đúng quyền.
- Output chưa được publish theo cách khiến replay ghi đè.
- DB, broker, worker resources đủ để tránh retry storm.
- Kỳ tiếp theo được kiểm soát overlap/dependency.
- Lưu `requestedAt`, `reason`, `approvedBy` và original deadline.

**Không chỉ ghi ledger RESTARTING rồi tin rằng restart đã được launch.** Process có thể chết giữa cập nhật ledger và tạo JobExecution; retry dispatcher phải tra trạng thái thật.

## 14. JobOperator.restart: tiếp tục execution bị lỗi

Spring Batch có `JobOperator` để restart một execution ID đã tồn tại. Ví dụ Spring Batch 5.x:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public final class ApprovedRestartService {

    private static final Logger log =
            LoggerFactory.getLogger(ApprovedRestartService.class);

    private final JobOperator operator;

    public ApprovedRestartService(JobOperator operator) {
        this.operator = operator;
    }

    public long restartApproved(
            long failedExecutionId, String approvalId)
            throws Exception {

        // Giả định đã kiểm tra policy, snapshot,
        // JobRepository, ownership và durable claim.
        long newExecutionId =
                operator.restart(failedExecutionId);

        log.info(
            "event=late_restart_submitted oldId={} newId={} approval={}",
            failedExecutionId, newExecutionId, approvalId);

        return newExecutionId;
    }
}
~~~

**Giới hạn:** ví dụ chưa có policy gate thật, authorization, distributed locking hoặc trạng thái downstream. `JobOperator.restart` có thể từ chối execution đã COMPLETED, đang chạy, không restartable hay job không được đăng ký; cần phân loại exception theo API/version. ID trả về **không chứng minh job đã COMPLETED**; phải theo dõi JobRepository.

Nếu lời gọi timeout, **không gọi lại ngay**. Có thể execution mới đã được tạo, nhưng response mất; tra JobRepository theo JobInstance trước.

**Không thay `JobOperator.restart` bằng `startNextInstance` chỉ để tránh exception**: startNextInstance tạo/chuyển sang JobInstance kế tiếp theo incrementer, có thể xử lý kỳ dữ liệu khác.

## 15. JobLauncher với JobParameters gốc

`JobLauncher.run(job, parameters)` nhận job và parameters; Spring Batch xác định JobInstance từ job name + identifying parameters.

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;

public final class ExplicitLaunchService {
    private final JobLauncher launcher;
    private final Job job;

    public ExplicitLaunchService(
            JobLauncher launcher, Job job) {
        this.launcher = launcher;
        this.job = job;
    }

    public JobExecution launch(JobParameters originalParameters)
            throws Exception {
        return launcher.run(job, originalParameters);
    }
}
~~~

Đây là wrapper kỹ thuật, **không phải safe public restart endpoint**. Phải có policy, ownership, JobRepository checks, authorization và durable audit.

Nếu một lần chạy lại dùng thêm identifying `run.id=now`, nó có thể tạo JobInstance mới, xử lý lại từ đầu. Nếu original JobInstance đã COMPLETED, Spring Batch thường ngăn launch lại. Đừng tự sửa params để ép chạy khi chưa có reprocess contract.

## 16. Step restartability, completion và start limits

Các yếu tố cần phân biệt:

- `JobBuilder.preventRestart()` có thể cấm restart JobInstance.
- Step đã COMPLETED thường không được chạy lại trong restart mặc định; `allowStartIfComplete(true)` thay đổi điều đó.
- `startLimit` giới hạn số lần Step bắt đầu theo framework, khác thời hạn business recovery.
- Reader/Writer `ItemStream.open/update/close` phải lưu đúng checkpoint.
- Tasklet có side effect phải được thiết kế idempotent nếu có khả năng re-execution.
- JobRepository metadata và business writes ở hai DataSources không mặc nhiên atomic.

~~~text
extract     COMPLETED
transform   COMPLETED
publish     FAILED

Restart cùng instance:
  extract, transform được xem xét theo Step completion policy
  publish được tiếp tục theo Step/restart semantics
~~~

Không bật `allowStartIfComplete(true)` “cho chắc” nếu Step hoàn thành đã chuyển tiền, gửi thông báo hoặc phát immutable output. Nếu staged outputs cũ đã mất, cần reprocess/revision policy có audit chứ không tùy tiện sửa flags.

## 17. Java policy gate cho recovery window

Policy quyết định bằng **mốc cố định của business run**, không tính lại từ ngày hiện tại:

~~~java
import java.time.Instant;
import java.util.Objects;

public final class LateRestartPolicy {

    public enum Decision {
        ALLOW,
        REQUIRE_APPROVAL,
        REJECT_PUBLISHED,
        REJECT_SOURCE_CHANGED,
        REJECT_OWNERSHIP_UNKNOWN
    }

    public record Context(
            Instant recoveryAllowedUntil,
            boolean sourceSnapshotMatches,
            boolean ownershipResolved,
            boolean outputAlreadyPublished,
            boolean lateApprovalGranted) {}

    public static Decision evaluate(
            Instant now, Context c) {
        Objects.requireNonNull(now);
        Objects.requireNonNull(c);
        Objects.requireNonNull(c.recoveryAllowedUntil());

        if (c.outputAlreadyPublished()) {
            return Decision.REJECT_PUBLISHED;
        }
        if (!c.sourceSnapshotMatches()) {
            return Decision.REJECT_SOURCE_CHANGED;
        }
        if (!c.ownershipResolved()) {
            return Decision.REJECT_OWNERSHIP_UNKNOWN;
        }
        if (now.isAfter(c.recoveryAllowedUntil())
                && !c.lateApprovalGranted()) {
            return Decision.REQUIRE_APPROVAL;
        }
        return Decision.ALLOW;
    }
}
~~~

**Đây chỉ là pure domain decision**, không thực hiện JobRepository query/lock, không xét BatchStatus hay hard regulatory stop. `ALLOW` chưa cấp quyền dispatch cho đến khi có **durable ownership claim** và điều kiện framework được kiểm tra.

Đặc biệt `recoveryAllowedUntil` phải được tính từ lịch kỳ đó và lưu lại bằng `Instant`. Nếu mỗi lần retry lại tính từ `LocalDate.now()`, cửa sổ phục hồi sẽ tự trôi mãi.

## 18. Durable ownership: hai controllers không được cùng restart

~~~text
05:30 scheduler-recovery thấy JobExecution FAILED
05:30 operator-dashboard cũng thấy FAILED
05:30 cả hai gửi restart(oldExecutionId)
~~~

Framework có bảo vệ trạng thái JobInstance, nhưng còn có network timeouts, metadata stale và external side effects. Nên thêm run-level coordination với key `(jobName,businessDate,sourceVersion)`:

- Unique/conditional state transition `FAILED → RESTARTING`.
- Lease/claim owner và fencing generation khi có nhiều controllers.
- Lưu old execution ID, approval, reason và deadline gốc.
- Sau dispatch, lưu new execution ID và theo dõi.
- Khi dispatch timeout, tra JobRepository trước khi thử lại.
- Không coi lease hết hạn là chứng minh remote worker cũ đã dừng.

SQL ví dụ **schema ứng dụng, không phải bảng Spring Batch**:

~~~sql
UPDATE business_run
SET scheduler_state = 'RESTARTING',
    recovery_owner = :controllerId,
    recovery_generation = recovery_generation + 1,
    restart_requested_at = now()
WHERE job_name = :jobName
  AND business_date = :businessDate
  AND source_version = :sourceVersion
  AND scheduler_state = 'FAILED'
RETURNING recovery_generation;
~~~

Chỉ khi row update thành công mới được claim theo policy. Nhưng vẫn có **dual-system gap** giữa business_run ledger và JobRepository; controller phải reconcile khi crash.

Không giữ DB row lock suốt một job chạy nhiều giờ. Dùng durable state/lease với fencing phù hợp, transaction ngắn và kiểm tra ownership của work thật.

## 19. Cửa sổ đóng nhưng remote worker vẫn STARTED

Ví dụ:

~~~text
03:58 manager dispatch partition P7
04:01 manager mất broker connection
04:02 manager timeout, không nhận reply
04:05 worker vẫn đang COMMIT DB chunk P7
04:06 operator định restart job
~~~

Manager timeout **không chứng minh worker đã ngừng**. Không giao cùng partition sang worker khác khi có thể xảy ra duplicate execution.

Trước khi restart:

1. Xem JobRepository status và StepExecutions.
2. Xác định worker instance, heartbeat/progress và khả năng còn chạy.
3. Xem broker request/ACK/reply, DB transaction/commit state.
4. Đối soát checkpoint, idempotency ledger và business outputs.
5. Chỉ khi worker cũ đã dừng hoặc có fencing đúng mới cho retry/redispatch.
6. Nếu metadata STARTED stale/UNKNOWN, dùng runbook repair, không sửa BATCH tables tùy tiện.

Một JobExecution STARTED trong repository không đảm bảo process sống; **timeout cũng không đảm bảo nó chết**.

## 20. Multi-threaded step khi late restart

Với multi-threaded chunk processing:

- Nhiều chunks chạy trong một StepExecution, commit order có thể đảo.
- Reader/ItemStream có thể không thread-safe; `@StepScope` theo StepExecution, không per chunk thread.
- Khi deadline tới, một số chunks vẫn inflight.
- Processor/writer có thể bị gọi lại sau retry/rollback.
- Step counters qua nhiều executions không bằng unique business records.
- Một JDBC connection pool bị nghẽn có thể làm retry storm tệ hơn nếu tăng threads.

Late restart an toàn cần bảo vệ **business operation identity** và chứng minh input/checkpoint ổn định. Nếu DB hot-row contention là root cause, tăng concurrency sau cửa sổ có thể làm job **chậm hơn**.

## 21. Local và remote partitioning khi restart

Một Partitioner nên tạo **deterministic partition names và ranges**:

~~~text
partition-0000 → [0, 250000)
partition-0001 → [250000, 500000)
partition-0002 → [500000, 750000)
partition-0003 → [750000, 1000000)
~~~

Qua restart cùng JobInstance:

- Không đổi source generation/cutoff.
- Không đổi phân vùng input theo cách phá checkpoint.
- Completed partitions được xử lý theo framework completion semantics.
- Failed partitions có recovery state rõ, không đồng thời chạy ở hai workers.
- Worker `ExecutionContext` giữ các cận và source identity.
- Output per partition có idempotency và manifest.

~~~mermaid
flowchart TB
    M["Manager: businessDate D"] --> W0["P0 COMPLETED"]
    M --> W1["P1 FAILED"]
    M --> W2["P2 COMPLETED"]
    W1 --> R["Late restart failed work"]
    W0 --> O["Output / staging for D"]
    W2 --> O
    R --> O
    O --> G{"Global reconcile"}
    G -->|PASS| P["Publish D as late"]
~~~

Thực tế StepExecutions nào được chạy lại phụ thuộc Spring Batch/PartitionHandler/StepExecutionSplitter và topology; cần test đúng version.

**Remote partitioning:** reply thất lạc sau commit là tình huống cần idempotency + ownership, không chỉ JobOperator. Worker có thể đổi JVM sau restart, nhưng partition logical identity phải giữ nguyên.

## 22. Remote chunking: cùng event có thể được gửi lại

~~~text
Manager gửi chunk C42
Worker ghi business DB và COMMIT
Reply C42 LOST
Manager timeout
Late restart có thể khiến cùng event tới worker khác
~~~

Nếu writer chạy `balance = balance + delta` hai lần, dữ liệu bị nhân đôi. Dùng stable business event ID, unique ledger/inbox và transaction phù hợp; đừng lấy chunk correlation ID làm domain idempotency key nếu một business event có thể chuyển sang chunk khác.

Cần tách **request order, worker processing order và DB commit order**; broker FIFO không tự bảo đảm business update theo sequence khi nhiều workers.

## 23. DB commit ngay lúc cửa sổ đóng

~~~text
03:59:59 writer UPDATE
04:00:00 start window closes
04:00:02 business DB COMMIT
04:00:03 JobRepository checkpoint
~~~

Nếu chính sách chỉ giới hạn **new starts**, hành vi này có thể hợp lệ. Nếu có hard execution deadline, cần graceful stop với deadline đủ để xử lý chunks, không chỉ kill JVM đúng 04:00.

Nếu business DB và JobRepository dùng hai resource managers, metadata checkpoint **không mặc nhiên commit atomically** với side effect. Khi worker chết giữa hai commits, restart có thể replay đã ghi. Cần idempotency và reconciliation.

**Không tuyên bố chunk rollback chỉ vì worker chết trước log hoàn tất.** Business commit có thể đã thành công.

## 24. File output: resume hay tạo output attempt mới?

File writes trên filesystem/object storage không mặc nhiên rollback cùng Spring Batch chunk transaction. Khi late restart:

- Staging file có thể chứa bytes sau checkpoint.
- Worker có thể chết trước flush/close hoặc trước upload hoàn tất.
- `FlatFileItemWriter`/`ItemStream` có state/restart semantics nhưng phải test trên filesystem thực.
- Hai attempts của một partition có thể để lại hai files; không được merge cả hai.
- Final file đã được downstream tiêu thụ không được sửa âm thầm.

~~~text
staging/
  settlement-2026-11-25/
    partition-0007/
      attempt-01/data.csv  # PARTIAL
      attempt-02/data.csv  # VALIDATED
~~~

**Finalizer chỉ chọn một validated attempt** cho mỗi logical partition sau khi xác nhận hash, logical record count, business key diff và source snapshot. Nếu output đã publish, late correction nên tạo version/manifest mới, không overwrite path cũ.

Không công bố partial file chỉ để giảm mức trễ. Output trễ nhưng đúng, có `late=true` và downstream chấp nhận correction, tốt hơn output sai phát sớm.

## 25. Outbox và side effect ngoài database

Một Step vừa UPDATE DB vừa gửi Kafka/RabbitMQ có dual-write gap:

~~~text
Business DB COMMIT thành công
Worker chết trước broker publish
Scheduler yêu cầu late restart
Không biết event đã phát hay chưa
~~~

**Transactional Outbox** lưu business change + event intent cùng DB transaction, publisher phát sau commit. Tuy nhiên publisher có thể gửi lại khi broker đã nhận nhưng ACK hoặc trạng thái SENT bị mất.

Cần:

- Stable business event ID xuyên restart, không sinh từ `now()`.
- Consumer inbox/idempotency để không áp dụng external effect hai lần.
- Event gắn đúng `businessDate`/`sourceVersion`.
- Phân biệt `JobExecution COMPLETED` với “tất cả event đã publish” nếu publisher async.
- Đối soát API/payment/email side effects vì DB rollback không undo chúng.
- Dùng đúng barrier/deadline nếu downstream cần mọi event đã publish trước khi coi kỳ xử lý hoàn tất.

**Không bật `allowStartIfComplete(true)` chỉ để gửi lại một broker reply bị mất.** Đối soát và sửa đúng tầng gây lỗi.

## 26. Khi kỳ kế tiếp đã bắt đầu

Nếu kỳ D trễ trong khi kỳ D+1 đến lịch:

| Chiến lược | Dùng khi | Rủi ro |
| --- | --- | --- |
| Serialize D rồi D+1 | D+1 cần closing balance của D | Backlog/SLA D+1 |
| Parallel D và D+1 | Dữ liệu/outputs tách biệt, DB còn capacity | Lock contention, sequencing |
| Backfill queue | Nhiều business periods trễ | Fairness/priority/retention |
| Correction/revision | Kỳ D đã published hoặc source đổi | Downstream phải hỗ trợ version |
| Expire/skip theo policy | Có hợp đồng cho phép không xử lý | Cần audit/compensation |

Báo cáo analytics độc lập theo ngày có thể chạy song song; job tính cumulative balances có thể **bắt buộc chạy tuần tự**.

### Resource budget toàn cluster

Các kỳ cùng tiêu DB connections/locks, JobRepository writes, worker threads, broker throughput và filesystem I/O. Tăng worker cho late run khi DB hot-row contention có thể khiến cả kỳ mới chậm hơn.

## 27. Ước lượng thời gian phục hồi

Giả sử còn 3 triệu logical records và cluster dành được 2.000 **unique committed items/s** khi xử lý cùng kỳ mới:

\[
T_\mathrm{remaining}
\approx \frac{3{,}000{,}000}{2{,}000}
=1{,}500\ \mathrm{s}
=25\ \mathrm{phút}
\]

Chưa tính startup, retries, tail partitions, checkpoint và publication.

| Worker plan | Useful throughput | Thời gian 3M/R | Đánh giá |
| --- | ---: | ---: | --- |
| 2 workers | 1.200/s | 41,7 phút | Ít contention nhưng chậm |
| 4 workers | 2.000/s | 25 phút | Có thể hợp lý |
| 8 workers, DB lock-bound | 2.200/s | 22,7 phút | Lợi ích biên nhỏ |
| 12 workers, retry storm | 1.500/s | 33,3 phút | Nhiều worker lại chậm |

Số liệu **giả định**, không phải benchmark Spring Batch. Nếu `now + estimatedRemaining + validationAndPublish` vượt recovery deadline, cần approval/escalation thay vì bí mật dời deadline.

**Useful throughput** là business effects hợp lệ đã commit, không gồm rollback/redelivery attempts.

## 28. Retry budget nhiều tầng và restart storm

Một lần lỗi có thể được retry bởi:

- Spring Batch item/chunk retry.
- Step/job restart.
- Scheduler misfire/launch retry.
- Kubernetes Job pod retries.
- Broker message redelivery.
- Publisher Outbox retry.
- Manual operator restart.

Nếu mỗi tầng retry ngay vô hạn, DB/broker vừa hồi phục có thể chịu tải gấp nhiều lần bình thường.

### Chính sách khuyến nghị

1. Phân loại transient (deadlock, network) và permanent (schema mismatch, invalid input).
2. Chunk retry hữu hạn, rollback rồi backoff + jitter.
3. Job restart theo **business period retry budget**, không lặp vô hạn.
4. Nếu scheduler timeout, tra JobRepository trước dispatch lại.
5. Message redelivery phải idempotent.
6. Khi DB/broker outage, chặn intake nếu cần thay vì restart pod hàng loạt.
7. Retry exhaustion tạo alert và audit; không skip records bắt buộc chỉ để job COMPLETED.
8. Một approval không xóa failure/retry history.
9. Giới hạn manager outstanding work và worker executor queue.

Late restart được chấp thuận **không có nghĩa mọi deadline/retry limit tự được nới**.

## 29. Hard deadline và graceful stop

Nếu nghiệp vụ cấm business write sau 04:00, scheduler phải có cơ chế gửi **stop request**. `JobOperator.stop(executionId)` yêu cầu Spring Batch dừng theo lifecycle; nó không mặc nhiên interrupt ngay DB transaction đang chạy.

Cần:

- Gửi stop đủ sớm theo transaction/chunk latency.
- Theo dõi STOPPING → STOPPED và mọi worker StepExecutions.
- Nếu remote partitioning, bảo đảm stop/ownership policy ở worker JVM.
- Chọn Kubernetes termination grace theo p99 chunk/rollback.
- Xác minh business commits quanh cutoff trước restart.
- Không kill JVM đúng 04:00 rồi tuyên bố mọi chunk đã rollback.

**Start window, execution hard stop và recovery window có thể khác nhau**. Một job bị STOPPED lúc 04:00 vẫn có thể được restart lúc 05:30 nếu chính sách cho phép; hoặc phải chuyển sang correction process nếu business ledger đã đóng.

Clock skew giữa nodes có thể tạo lệch deadline/lease. Dùng `Instant` lưu cố định, đồng bộ thời gian phù hợp và khi cần dùng authoritative DB time cho admission.

## 30. Downstream dependency khi output đến muộn

~~~mermaid
flowchart LR
    A["Ingest D"] --> B["Settlement D"]
    B --> C["Statement D"]
    C --> E["Partner delivery"]
    B --> F["Risk model D+1"]
~~~

Khi settlement D trễ:

- Downstream có thể còn chờ marker.
- Có thể đã timeout và báo data unavailable.
- Có thể đã chạy bằng stale/default data.
- Có thể đã publish một bản tạm cần correction.
- D+1 có thể đã dùng closing state D cũ.

Một immutable output manifest nên chứa:

~~~text
businessDate          = D
sourceGeneration      = V17
transformVersion      = v5
originalSlaAt         = 04:30
actualPublishedAt     = 06:12
late                  = true
publicationRevision   = 1
reconciliation        = PASS
~~~

Downstream phải chấp nhận đúng version/correction semantics. Không đánh dấu “đúng hạn” chỉ vì late restart đã COMPLETED. Partner có hard cutoff có thể cần manual compensation thay vì tự gửi late file.

## 31. SLA, SLO và recovery metrics

Ba góc nhìn:

| Góc | Câu hỏi |
| --- | --- |
| Correctness | Kết quả đúng, đủ, không duplicate sau restart? |
| Lateness | Publish trễ bao lâu so với SLA gốc? |
| Recovery | Từ failure/detection tới restored/COMPLETED bao lâu? |

Ví dụ:

~~~text
SLA original    : 04:30
Failure         : 03:51
Detected        : 03:55
Restart         : 05:30
Published       : 06:12

Lateness        : 102 phút
Detection lag   : 4 phút
Failure→Restart : 99 phút
Post-restart    : 42 phút
~~~

Các số minh họa. Cần định nghĩa MTTR end state: job completed khác downstream published. Một JobExecution COMPLETED nhưng reconciliation FAIL thì incident **chưa được đóng**.

Đặt alert khi gần recovery deadline, khi D+1 bị blocked bởi D và khi đã publish muộn cần partner reconciliation.

## 32. Scheduler dispatch at-least-once và đồng bộ JobRepository

Một trigger có thể bị gửi lại do network timeout:

~~~text
Scheduler gọi JobLauncher cho businessDate D
JobRepository tạo JobExecution #8100
Response đến scheduler bị mất
Scheduler retry launch kỳ D
~~~

Nếu identifying parameters đúng, Spring Batch có kiểm tra instance đang chạy/đã hoàn thành. Tuy nhiên phải **xử lý exception bằng cách re-query state**, không gắn random `run.id` để ép tạo JobInstance mới.

Với nhiều scheduler nodes:

- Dùng durable admission claim/distributed scheduler election.
- Đảm bảo chỉ một controller sở hữu restart decision cho business run.
- Khi `JobExecutionAlreadyRunningException` hoặc lỗi tương tự, đọc JobRepository và worker status.
- Không đổi identifying parameters để tránh duplicate guard.
- Không sửa trực tiếp BATCH metadata khi chưa đối soát.
- Chú ý JobRepository DB pool/metadata load từ các worker partitions.

**At-least-once dispatch + stable run identity + durable reconciliation** thường đáng tin hơn giả định scheduler gửi chính xác một lần trên mạng không lỗi.

## 33. Backfill khi không thể restart kỳ cũ

Chọn backfill/reprocess revision khi:

1. Source snapshot gốc không còn.
2. Transform/schema đã đổi không tương thích checkpoint.
3. JobInstance đã COMPLETED nhưng output đã publish sai.
4. Business period đóng sổ, chỉ được gửi adjustment.
5. Recovery window đã hết và phải có manual approval.
6. Checkpoint không còn chứng minh trạng thái xử lý.
7. Downstream cần correction version thay vì ghi đè.

~~~text
businessDate        = 2026-11-25
originalRun         = settlement-2026-11-25-rev1
reprocessRevision   = rev2
sourceGeneration    = V18-corrected
transformVersion    = v6
publicationMode     = correction
~~~

Đây là **JobInstance mới có chủ đích**, không phải restart cùng instance. Ghi lineage từ revision mới về run gốc và làm rõ consumer idempotency. Với cumulative balance, backfill D có thể yêu cầu tái tính các kỳ sau theo thứ tự, không chỉ chạy song song tất cả ngày.

## 34. Bằng chứng trước khi chấp thuận late restart

| Nhóm | Cần xem |
| --- | --- |
| Run identity | JobName, JobInstanceId, businessDate, sourceVersion |
| Execution | Old JobExecutionId, BatchStatus, failed Step |
| Timing | ScheduledAt, windowClose, originalSlaAt, recoveryAllowedUntil |
| Ownership | Active worker executions, broker state, job manager |
| Checkpoint | Reader offsets, partition ranges, ItemStream state |
| Business effects | DB ledger, external API requests, outbox events |
| Output | File manifest, staging attempts, publication marker |
| Capacity | Active periods, worker/DB budgets, remaining throughput |
| Authorization | Requester, reason, approver, approval expiry |
| Recovery action | Restart same instance, revision, quarantine, cancel |

Có thể tự động cho FAILED job restart khi lỗi transient, còn recovery window, source hợp lệ, owner rõ, chưa publish và retry budget chưa cạn. Với status UNKNOWN, source drift, hard stop, external payment hoặc output đã publish, cần manual review theo risk policy.

**Approval phải dựa trên kết quả có thể review**, không chỉ một nút “force restart” và warning chung.

## 35. Structured log và audit của late restart

Ví dụ request log:

~~~text
event=late_restart_requested
jobName=dailySettlementJob
jobInstanceId=7021
oldExecutionId=8100
businessDate=2026-11-25
sourceVersion=V17
scheduledAt=2026-11-25T18:00:00Z
originalSlaAt=2026-11-25T21:30:00Z
requestedAt=2026-11-25T22:30:00Z
policyDecision=ALLOW
approvalId=A-9201
requestId=retry-724
~~~

Sau dispatch:

~~~text
event=late_restart_submitted
oldExecutionId=8100
newExecutionId=8155
jobInstanceId=7021
recoveryGeneration=2
~~~

Log cần có original business period, source snapshot, old/new execution IDs, recovery owner/generation, reason, deadline và output reconciliation. Timestamp và timezone chỉ mang ý nghĩa theo lịch cụ thể; các giá trị trên là minh họa.

**Không dùng JobExecutionId làm business idempotency key**, vì nó thay đổi khi restart. Không đưa PII/tokens/raw payload vào log chỉ để debug.

## 36. Metrics cho lịch, phục hồi và trễ SLA

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `batch_scheduled_runs_total` | Kỳ dự kiến |
| `batch_scheduler_misfires_total` | Trigger bị lỡ |
| `batch_launch_uncertain_total` | Dispatch timeout |
| `batch_late_restart_requested_total` | Yêu cầu muộn |
| `batch_late_restart_allowed_total` | Policy PASS |
| `batch_late_restart_rejected_total` | Policy FAIL |
| `batch_recovery_wait_seconds` | Thời gian từ failure tới restart |
| `batch_recovery_execution_seconds` | Restart tới completion |
| `batch_publish_lateness_seconds` | Trễ theo SLA gốc |
| `batch_active_business_periods` | Số kỳ đang xử lý |
| `batch_oldest_incomplete_period_age` | Độ tuổi kỳ chưa xong |
| `batch_worker_active_partitions` | Worker partitions đang chạy |
| `batch_checkpoint_staleness_seconds` | Lần checkpoint gần nhất |
| `batch_reconciliation_failure_total` | Output không đạt validation |

Các tên là **gợi ý**, không phải metric Spring Batch tự sinh. Dùng labels có cardinality kiểm soát (`job`, `step`, `outcome`, `errorCategory`). Exact `jobExecutionId`, `partitionName` và `requestId` đưa vào logs, không làm Prometheus labels mặc định.

**Oldest incomplete business period** đặc biệt hữu ích: tất cả pods có thể READY nhưng pipeline vẫn tồn đọng một kỳ đã quá hạn nhiều ngày.

## 37. Unit test chính sách cửa sổ

Với `LateRestartPolicy` ở phần 17, JUnit 5 nên kiểm tra boundary thời gian và rủi ro:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class LateRestartPolicyTest {

    @Test
    void requiresApprovalAfterDeadline() {
        Instant deadline =
                Instant.parse("2026-11-25T21:00:00Z");

        var context = new LateRestartPolicy.Context(
                deadline, true, true, false, false);

        assertEquals(
                LateRestartPolicy.Decision.ALLOW,
                LateRestartPolicy.evaluate(deadline, context));

        assertEquals(
                LateRestartPolicy.Decision.REQUIRE_APPROVAL,
                LateRestartPolicy.evaluate(
                        deadline.plusSeconds(1), context));
    }

    @Test
    void publishedRunMustNotBeRestarted() {
        var context = new LateRestartPolicy.Context(
                Instant.parse("2026-11-25T23:00:00Z"),
                true, true, true, true);

        assertEquals(
                LateRestartPolicy.Decision.REJECT_PUBLISHED,
                LateRestartPolicy.evaluate(
                        Instant.parse("2026-11-25T22:00:00Z"),
                        context));
    }
}
~~~

Đây là unit test **policy pure function**, không chứng minh distributed lock hay JobRepository đúng.

Bổ sung cases: `now == deadline`, approval expired, source mismatch dù đã approve, ownership UNKNOWN dù thời gian còn, output đã publish, timezone DST, concurrency hai requests và clock skew.

## 38. Spring Batch integration test: cùng JobInstance

Một kiểm thử với JobRepository thật:

1. Seed input V17 và identifying parameters của businessDate D.
2. Run job với một Step/Writer được inject lỗi sau khi vài chunks commit.
3. Assert JobExecution đầu FAILED, ghi nhận JobInstance ID.
4. Gỡ lỗi và gọi `JobOperator.restart(oldExecutionId)`.
5. Assert execution mới thuộc **cùng JobInstance ID**.
6. Assert completed steps không chạy lại ngoài contract.
7. Assert checkpoint/restart đúng và không duplicate business records.
8. Assert output/global reconciliation PASS trước publication.
9. Assert SLA trễ được ghi nhận theo deadline gốc, không đổi.
10. Assert source version đổi giữa attempts khiến policy fail.

Mock operator được gọi **không chứng minh** restart thành công. Hai jobs cùng businessDate nhưng khác identifying run.id cũng **không** chứng minh cùng instance.

## 39. Fault injection với worker phân tán

| Failure window | Kiểm tra |
| --- | --- |
| Scheduler down lúc trigger | Misfire policy đúng, không tạo instance nhầm |
| Launcher response lost | Re-query, không thêm random run.id |
| DB chết trước chunk commit | Rollback/retry đúng |
| DB chết sau business commit trước checkpoint | Idempotency khi replay |
| Broker reply lost | Không tự redispatch khi worker cũ còn chạy |
| Worker kill khi step RUNNING | Recovery ownership và checkpoint |
| JobRepository outage | Reconcile metadata vs business DB |
| Source bị overwrite | Snapshot mismatch FAIL |
| Hai controllers cùng restart | Một durable claim duy nhất |
| Recovery deadline hết | Escalate/manual, không auto launch |
| D+1 đang chạy | Overlap/serialize policy đúng |
| Outbox ACK unknown | Consumer dedup |
| File output partial | Không publish, chọn validated attempt |
| Commit marker đã ghi nhưng response mất | Idempotent publish recovery |
| DST transition | Mỗi scheduled occurrence có meaning xác định |
| Rolling deploy đổi schema | Compatibility/reprocess rõ |
| Hard stop giữa chunk dài | Stop/recovery theo transaction policy |

Test phải đối chiếu **JobRepository, broker/worker state và business data**, không chỉ HTTP health hoặc console logs.

## 40. Checklist bất biến tính đúng của late restart

Một kỳ D phải có:

- Business identity nhất quán qua attempts.
- Source snapshot/cutoff bất biến khi restart.
- Execution/partition ownership không chồng lấn.
- Idempotent committed business operations.
- Output attempt/manifest duy nhất được chọn và validated.
- Không tự gửi lại external side effects đã xảy ra.
- Downstream correction/publication có version rõ.
- SLA gốc được giữ nguyên để đo lateness.
- Worker/concurrency/DB budgets không bị vượt.
- Approval/exception được audit và có thời hạn.
- Retry có giới hạn và có thể dừng khi dependency outage.
- Không có direct SQL metadata repair thiếu runbook.

**Lịch chạy đúng không chứng minh dữ liệu đúng, và dữ liệu đúng không xóa được việc đã trễ SLA.** Cả hai đều cần được đo độc lập.

## 41. Case study: 24 triệu events trong cửa sổ 3 giờ

Một công ty tài chính chạy `dailySettlementJob` để chuẩn hóa **24.000.000 events** của business date D. Job dùng remote partitioning, nhiều worker JVM và PostgreSQL, sau đó xuất báo cáo theo immutable manifest.

Lịch:

~~~text
Business period         : D = 2026-11-25
Start window            : 2026-11-26 01:00–04:00 (Asia/Ho_Chi_Minh)
Publish SLA             : 2026-11-26 04:30
Recovery allowed until  : 2026-11-26 07:00
Source snapshot         : settlement-D-V17
Partition count         : 24
Worker JVMs             : 8
~~~

Throughput lý tưởng nếu muốn xử lý hết trong ba giờ:

\[
R_{\mathrm{required}}
=\frac{24{,}000{,}000}{3\times3600}
\approx 2{,}222\ \mathrm{events/s}
\]

Đây là **cận lý tưởng** chưa gồm startup, retries, tail partition, reconciliation và publish. Hệ thống cần headroom.

### Sự cố

~~~text
01:00  Scheduler dispatch businessDate D
01:03  JobExecution #8100 STARTED
03:50  Đã commit 18M events, 6M còn lại
03:51  Shared DB outage làm một worker partition FAILED
03:57  Manager xác nhận JobExecution FAILED
04:00  Start window closes
04:30  Publish SLA breached
05:20  Database phục hồi
05:30  Operator review và policy gate PASS
05:32  JobOperator.restart(#8100) → JobExecution #8155
~~~

**Điểm cần kiểm chứng trước restart:** 18 triệu events đã commit có business idempotency; partition ranges/JobRepository checkpoint khớp; tất cả workers cũ ngừng; snapshot V17 còn; chưa có final manifest COMMITTED; thời gian hồi phục vẫn trước `recoveryAllowedUntil`.

### Tính phần còn lại

Giả định 6 triệu events chưa commit, throughput hữu ích thực tế khi restart là 2.500 events/s:

\[
T_{\mathrm{remaining}}
=\frac{6{,}000{,}000}{2{,}500}
=2{,}400\ \mathrm{s}=40\ \mathrm{phút}
\]

Nếu restart thực sự chạy lúc 05:32, hoàn tất processing khoảng 06:12. Dành thêm 13 phút validation và 5 phút publish, output COMMITTED khoảng **06:30**, nghĩa là trễ **2 giờ** so với SLA 04:30.

Đây là **mô hình minh họa**, không phải guarantee. Tail partition, lock waits, retry overhead và queue lag có thể khiến thời gian dài hơn.

### Tại sao vẫn restart?

Business policy cho phép recover trước 07:00 và downstream có late-correction contract. Không chạy lại toàn bộ 24 triệu events như một instance mới; chỉ tiếp tục theo checkpoint/Step restart behavior được kiểm thử. Downstream nhận manifest có `businessDate=D`, `late=true`, `actualPublishedAt=06:30` và `reconciliation=PASS`.

### Nếu không còn snapshot V17?

Operator không được “resume” bằng source V18 chỉ vì path giống nhau. Chuyển sang **manual reprocess revision** với immutable V18, reconciliation mới và approval riêng.

### Nếu kỳ D+1 cần closing balance D?

Không cho job D+1 dùng số dư kết thúc D chưa hoàn chỉnh. Hoặc serialize theo kỳ, hoặc phát correction/replay downstream theo contract được chứng minh; không vì số worker còn rảnh mà chạy chồng một nghiệp vụ có phụ thuộc thứ tự.

### Một bảng benchmark giả định

| Phương án | Useful throughput sau restart | 6M/R | Business impact |
| --- | ---: | ---: | --- |
| 2 workers | 1.400/s | 71,4 phút | Ít DB lock, nhưng gần recovery deadline |
| 4 workers | 2.100/s | 47,6 phút | Có headroom vừa phải |
| 8 workers | 2.500/s | 40,0 phút | Phù hợp giả định |
| 12 workers, DB hot row | 2.300/s | 43,5 phút | Lợi ích âm do contention |
| New JobInstance chạy lại 24M | Attempts lớn hơn | Không so bằng 6M/R | Rủi ro duplicate business effects |

Số liệu hoàn toàn **giả định**. Nhận xét phải dựa vào throughput hữu ích và tính đúng dữ liệu, không dùng số invocations làm evidence.

### Điều kiện đóng incident

- JobExecution mới COMPLETED đúng JobInstance.
- Không missing/duplicate business events theo reconciliation.
- Output checksum/manifest PASS.
- Downstream đã chấp nhận late delivery đúng business date và revision.
- SLA breach 120 phút được ghi nhận và escalated.
- Lý do DB outage, timeline recovery và các biện pháp ngăn lặp được lưu lại.

**Bài học case study:** late restart có thể cứu dữ liệu đúng và hoàn tất nghĩa vụ nghiệp vụ, nhưng **không biến một kỳ trễ thành kỳ đúng hạn**.

## 42. Runbook restart sau cửa sổ chạy

Khi nhận alert FAILED sau windowClose, xử lý theo trình tự thay vì nhấn retry ngay.

**Bước 1 — Cố định identity.** Ghi Job name, JobInstanceId, old JobExecutionId, identifying params, businessDate, source snapshot/cutoff và lịch gốc.

**Bước 2 — Phân biệt trigger vs execution.** Đây là scheduler misfire chưa launch job, JobExecution FAILED/STOPPED hay dispatch UNKNOWN? Không dùng cùng cách xử lý cho cả ba.

**Bước 3 — Xác minh trạng thái thật.** JobRepository status, active StepExecutions, remote workers, broker pending/ACK/reply và DB commits. Không coi timeout là worker đã dừng.

**Bước 4 — Đọc policy.** Start window đã đóng? Có hard stop không? `recoveryAllowedUntil` còn? SLA đã trễ? Cần approval nào?

**Bước 5 — Kiểm tra source và checkpoint.** Immutable source generation, partition range, ExecutionContext, reader offsets, Step completion và transform compatibility.

**Bước 6 — Đánh giá side effects.** Business DB/outbox/consumer inbox, external API, files/staging/output manifest. Nếu output đã published, chuyển correction/reprocess policy.

**Bước 7 — Tính capacity.** D+1 có đang chạy, DB pools/lock waits, worker concurrency, ETA phần còn lại và publication lag.

**Bước 8 — Claim và dispatch.** Durable run-level claim, audit approval, gọi `JobOperator.restart(oldExecutionId)` đúng một lần theo workflow; khi response UNKNOWN, re-query.

**Bước 9 — Theo dõi recovery.** New execution ID, Step status/progress, rollback/retry, resource pressure, deadline và downstream dependencies.

**Bước 10 — Đối soát.** Business keys/amounts, JobRepository, outbox, output files/hash/manifest, duplicated side effects; không chỉ JobExecution COMPLETED.

**Bước 11 — Publish và thông báo.** Có thể phát output late với đúng business date và correction version; thông báo SLA breach và downstream handling.

**Bước 12 — Đóng sự cố có bằng chứng.** Lưu timeline, nguyên nhân, approval, final artifact identity, reproduction/fault test và follow-up cải tiến.

### Những hành động phải tránh

- Thêm `run.id=now` để launcher chấp nhận request.
- Sửa `businessDate` thành ngày restart.
- Sử dụng input latest thay source snapshot đã khóa.
- Tăng worker count vô hạn khi DB lock-bound.
- Bật lại Step COMPLETED không có idempotency.
- Sửa trực tiếp BATCH metadata chỉ để đổi STARTED thành FAILED.
- Đánh dấu late publish là within SLA.
- Gửi file output khi reconciliation còn FAIL.
- Restart hai lần khi request đầu timeout mà chưa tra JobRepository.

## 43. Các ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
| --- | --- |
| “Qua start window thì Spring Batch tự cấm restart.” | Framework restart và scheduling policy là hai hệ khác nhau. |
| “Cửa sổ kết thúc 04:00 nghĩa mọi transaction tự rollback lúc 04:00.” | Chỉ đúng nếu ứng dụng có hard-stop protocol, không tự động. |
| “Job COMPLETED lúc 06:00 nghĩa SLA 04:30 đạt.” | SLA gốc đã vi phạm. |
| “Scheduler misfire là JobExecution FAILED.” | Misfire có thể chưa có execution. |
| “CronJob startingDeadlineSeconds là thời hạn JobOperator restart.” | Nó điều khiển lịch trễ của CronJob, không phải Batch recovery. |
| “concurrencyPolicy Forbid là distributed lock cho mọi Batch instance.” | Chỉ phạm vi Kubernetes CronJob Jobs tương ứng. |
| “Replace có thể kill job cũ mà không ảnh hưởng correctness.” | Worker/chunk có thể vẫn commit hoặc metadata chưa cập nhật. |
| “Thêm run.id sẽ restart thành công.” | Thường tạo JobInstance khác. |
| “Thay source V1 bằng V2 rồi resume offset.” | Kết quả có thể trộn snapshot. |
| “FAILED luôn có nghĩa không có side effect commit.” | Một số chunks đã commit trước lỗi. |
| “STARTED sau timeout nghĩa worker vẫn còn sống.” | Metadata có thể stale. |
| “STARTED sau timeout nghĩa worker đã chết.” | Worker có thể vẫn chạy; phải reconcile. |
| “JobRepository alone đảm bảo distributed lease cho mọi worker.” | Cần ownership/recovery đúng topology. |
| “allowStartIfComplete an toàn với mọi Step.” | Có thể phát side effect hai lần. |
| “Tăng concurrency sẽ đuổi kịp lịch.” | DB contention/lock có thể tăng và throughput giảm. |
| “Message ACK và DB commit là cùng transaction.” | Không mặc nhiên atomic. |
| “Sau restart không cần kiểm tra output file.” | File writes thường không rollback như JDBC. |
| “JobExecution COMPLETED đồng nghĩa outbox đã publish hết.” | Publisher có thể chạy async, còn backlog. |
| “Approval late restart đồng nghĩa được sửa deadline.” | Approval cho hành động, không xóa SLA breach. |
| “Backfill là restart JobInstance cũ.” | Thường là reprocess/new run revision có lineage. |

## 44. Checklist triển khai production

- [ ] Định nghĩa rõ start window, execution hard stop, business cutoff, SLA và recovery deadline.
- [ ] Lưu scheduled occurrence gốc bằng Instant cùng ZoneId/business calendar.
- [ ] Business date không tính từ current clock khi restart.
- [ ] Identifying JobParameters giữ đúng kỳ/source snapshot.
- [ ] Có immutable source identity/manifest và transform version.
- [ ] Kiểm tra JobInstance và JobExecution trước dispatch.
- [ ] Phân biệt scheduler misfire, launch UNKNOWN và Batch FAILED.
- [ ] Không ép new JobInstance bằng random identifying run.id.
- [ ] Đã kiểm tra `preventRestart`, `allowStartIfComplete`, `startLimit` và ItemStream state.
- [ ] Có durable policy gate, approval, claim và recovery generation/fencing khi cần.
- [ ] Hai controllers đồng thời không tạo active writers trùng.
- [ ] Remote workers/partitions cũ được xác minh dừng hoặc có ownership an toàn.
- [ ] Source snapshot/cutoff và partition ranges ổn định qua attempts.
- [ ] Chunk writes/idempotent business effects được kiểm thử sau rollback/crash.
- [ ] Remote chunking duplicate requests không nhân đôi domain events.
- [ ] File writer có attempt paths và global reconciliation trước publish.
- [ ] Outbox/external API effects có idempotency/reconciliation.
- [ ] Recovery ETA bao gồm validation/publication chứ không chỉ processing.
- [ ] Kỳ D/D+1 có dependency/concurrency policy rõ.
- [ ] DB/worker/broker capacity budgets tính trên toàn cluster.
- [ ] Retry ở nhiều tầng có budget/backoff/jitter; tránh restart storm.
- [ ] Hard-stop/termination policy đã test với long chunk.
- [ ] Có alert trước recovery deadline và khi backlog business periods tăng.
- [ ] Trễ SLA được giữ theo original deadline, không được sửa cho đẹp chỉ số.
- [ ] Late output có businessDate, sourceVersion, revision và immutable manifest.
- [ ] Operator dashboard hiển thị bằng chứng/approval trước restart.
- [ ] Runbook và audit đầy đủ old/new execution IDs, người yêu cầu và outcome.
- [ ] Unit tests cho boundary window/timezone và overlap.
- [ ] Integration test restart **cùng JobInstance** qua JobRepository.
- [ ] Fault injection trước/sau DB commit, broker reply, file close và publish.
- [ ] Không coi JobExecution COMPLETED là toàn bộ downstream correctness.
- [ ] Một run chỉ được đóng khi business reconciliation và publication PASS.

## 45. Câu hỏi tự kiểm tra

**1. Cửa sổ start kết thúc lúc 04:00; job STARTED từ 03:55 còn chạy lúc 04:10. Có mặc nhiên sai không?**

Không. Nếu đó chỉ là **start window**, job có thể chạy tiếp. Nếu có hard execution deadline, cần stop policy riêng.

**2. Job FAILED lúc 03:51, operator restart lúc 05:30. BusinessDate nên là ngày nào?**

Vẫn là ngày nghiệp vụ gốc của JobInstance thất bại, không tính lại từ đồng hồ lúc 05:30.

**3. Vì sao JobOperator.restart khác JobLauncher với run.id mới?**

`restart` tiếp tục JobInstance đã tồn tại theo execution ID; random identifying run.id có thể tạo JobInstance mới và xử lý lại từ đầu.

**4. JobExecution mới có cùng JobInstanceId với execution cũ. Điều đó chứng minh gì?**

Cho thấy cùng logical JobInstance theo framework. Không tự chứng minh dữ liệu và external side effects đã đúng; phải đối soát.

**5. Scheduler bị down lúc 01:00 và không có JobExecution nào. Đây là failed job hay misfire?**

Đây là missed scheduling trigger/misfire theo scheduler semantics, chưa phải Spring Batch job failure.

**6. Vì sao startup response timeout không đồng nghĩa launcher thất bại?**

JobRepository có thể đã tạo execution nhưng response trên mạng bị mất. Cần re-query trước khi thử lại.

**7. Có nên cho phép restart JobExecution STARTED sau khi manager timeout?**

Không tự động. Worker cũ có thể còn chạy hoặc đã commit; phải reconcile ownership và trạng thái.

**8. Tại sao không đổi source file version khi restart?**

Checkpoint offsets/partitions được tạo trên snapshot cũ. Đổi source giữa attempts có thể tạo output trộn hai phiên bản.

**9. Khi nào nên backfill thay restart?**

Khi source/transform không tương thích, kỳ cũ đã published, checkpoint hỏng hoặc business policy cần correction revision.

**10. Nếu bước publish đã COMPLETED trong execution cũ, có nên bật allowStartIfComplete để phát lại?**

Không mặc định. Có thể tạo duplicate side effects; cần kiểm tra publication ledger/outbox và revision contract.

**11. Vì sao một job chạy muộn có thể làm kỳ tiếp theo chậm?**

Hai kỳ cùng tranh DB connections, locks, worker threads, queue và downstream quota; một số kỳ có dependency theo thứ tự.

**12. Worker đã commit DB nhưng broker reply mất. Restart có rủi ro gì?**

Business event có thể được xử lý lại, gây duplicate nếu không có stable event ID, ledger/inbox hoặc idempotent writer.

**13. Có thể báo SLA PASS nếu job hoàn thành lúc 06:12 nhưng deadline là 04:30 không?**

Không. Job có thể đúng dữ liệu nhưng đã trễ 102 phút; phải ghi hai kết quả độc lập.

**14. Kubernetes CronJob Forbid có thay thế business run lock không?**

Không. Nó chỉ kiểm soát Kubernetes Jobs trong phạm vi CronJob, không quản lý mọi manual/remote Batch execution.

**15. Liveness của worker UP có chứng minh StepExecution đang tiến triển không?**

Không. Worker có thể sống nhưng kẹt DB lock; cần Step progress, checkpoint, broker và DB metrics.

**16. Khi nào late restart có thể được tự động hóa tương đối an toàn?**

Khi lỗi transient, input/version ổn định, framework restartable, ownership rõ, chưa publish, retry budget còn, resource đủ và trong recovery policy.

**17. Vì sao approval late restart không xóa SLA breach?**

Approval cho phép phục hồi dữ liệu sau giờ; nó không thay đổi original contractual deadline.

**18. Thế nào là đóng incident thành công?**

Cùng JobInstance được phục hồi đúng, business data không thiếu/trùng, output/side effects được đối soát, downstream nhận đúng revision và lateness được báo cáo rõ.

---

**Ghi nhớ:** **Restart sau cửa sổ chạy là quyết định của business recovery policy, không phải hiệu ứng tự động của Cron.** Spring Batch cho phép tiếp tục một JobInstance bằng JobExecution mới khi trạng thái và checkpoint phù hợp; scheduler phải phân biệt trigger bị lỡ với execution đã thất bại. Khi restart muộn, giữ **businessDate, identifying parameters và immutable source snapshot**, xác minh worker ownership, chống duplicate side effects, điều phối kỳ kế tiếp, đo capacity, và chỉ publish sau reconciliation. Kết quả có thể đúng dữ liệu dù trễ SLA: hãy giữ deadline gốc, ghi nhận sự chậm trễ và phục hồi có audit thay vì tạo JobInstance mới hoặc tự dời lịch để che vấn đề.
