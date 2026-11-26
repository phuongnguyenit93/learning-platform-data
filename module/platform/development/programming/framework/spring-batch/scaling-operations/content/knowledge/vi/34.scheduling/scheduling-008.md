# Backfill dữ liệu theo ngày trong Spring Batch

Một hệ thống thanh toán không chạy được batch tổng hợp trong sáu ngày vì downstream database quá tải. Sau sự cố, đội vận hành cần bù các ngày **18–23/11/2026**, nhưng daily job của hôm nay vẫn phải giữ SLA. Một yêu cầu tưởng đơn giản như “chạy lại sáu ngày” đặt ra nhiều câu hỏi khó: ngày được tính theo UTC hay giờ nghiệp vụ, late events có được tính, ngày đã hoàn thành có chạy lại không, hai người vận hành cùng submit có gây trùng, và khi một ngày thất bại thì xử lý tiếp như thế nào?

**Backfill dữ liệu theo ngày** là một workflow có kiểm soát để xử lý những ngày bị thiếu, bị trễ hoặc cần tính lại. Nó không đồng nghĩa thêm một cron trigger, không đồng nghĩa restart toàn bộ JobInstance, và càng không thể chỉ lặp qua danh sách `LocalDate` rồi gọi `JobLauncher.run`.

Bài **“Backfill dữ liệu theo ngày”** thuộc chương **Scheduling** trong module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch qua multi-threaded step, parallel steps, partitioning, xử lý phân tán, đo nút thắt, thread safety, retry/restart và vận hành dựa trên tài nguyên thực.

Các ví dụ dùng **Spring Batch 5.2.x, Spring Framework 6.x, Java 17+ và PostgreSQL**. Code là các mảnh tham khảo có ghi rõ bean/kiểu ứng dụng cần cung cấp; các ngày, quota và số liệu là giả định học tập, không phải dữ liệu production.

**Luận điểm chính:** lịch sử xử lý phải gắn với **ngày nghiệp vụ + snapshot đầu vào + phiên bản logic**, và mỗi lần công bố kết quả phải qua **quality gate**. Scheduler, JobRepository, dữ liệu nghiệp vụ và hệ thống publish là các tầng có trách nhiệm khác nhau.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

1. Phân biệt daily scheduled run, catch-up, backfill, restart và correction/reprocess.
2. Tính cửa sổ ngày `[startInclusive,endExclusive)` bằng `LocalDate` và `ZoneId`, kể cả ngày có DST.
3. Phân biệt `event_time`, `ingested_at`, watermark, freeze cutoff và immutable snapshot.
4. Xây dựng durable backfill plan và ledger theo ngày có audit, revision, dependencies và lease.
5. Chọn identifying `JobParameters` để Spring Batch quản lý đúng JobInstance và restart.
6. Dùng scheduler để **enqueue công việc**, không coi cron là hệ thống lưu trạng thái bền vững.
7. Chặn hai schedulers/worker generations cùng xử lý một logical work mà vẫn bảo vệ restart.
8. Thiết kế `@StepScope` reader và idempotent writer theo ngày, snapshot, version.
9. Chọn chạy tuần tự, song song theo ngày hoặc partition trong một ngày theo dependency/resource budget.
10. Phân biệt xử lý xong và **publish revision** sau khi đối soát dữ liệu.
11. Thiết lập quota DB/API/broker, timeout, retry, SLA/backpressure cho backfill lớn.
12. Viết fault-injection tests, metrics và runbook khôi phục các ngày thất bại.

## 2. Daily schedule, backfill và restart là các tầng khác nhau

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Daily run | Kích hoạt công việc ngày thường theo lịch | 02:15 lập kế hoạch cho ngày hôm qua |
| Catch-up | Bù những kỳ đã lỡ do scheduler/worker outage | Ngày 18, 19 không có JobExecution |
| Backfill | Xử lý quá khứ theo khoảng ngày đã yêu cầu | Lập plan 18–23/11 |
| Restart | Tạo **JobExecution mới trong cùng JobInstance** bị FAILED/STOPPED | Tiếp tục ngày 20 từ checkpoint |
| Reprocess/correction | Tính lại kết quả một ngày đã COMPLETED theo input/logic revision mới | Late events của ngày 20, revision v2 |
| Replay | Một item/chunk được xử lý lại | Crash sau business commit trước checkpoint |
| Partitioning | Tách một Step thành worker StepExecutions | Ngày 20 chia thành 32 file/range |
| Publish | Cho người dùng nhìn thấy output revision đạt validation | Pointer ngày 20 trỏ sang v2 |

**Không có transaction toàn ngày** trong một chunk-oriented step thông thường. Mỗi chunk có ranh giới transaction; nếu chunk thứ 501 rollback, 500 chunks trước có thể đã commit.

### 2.1. Ba vòng đời độc lập

~~~mermaid
flowchart LR
    S["Scheduler trigger"] --> P["Durable Backfill Plan"]
    P --> D["Daily work item"]
    D --> J["Spring Batch JobInstance"]
    J --> E["JobExecution + checkpoint"]
    E --> O[("Versioned business output")]
    O --> V["Validate/reconcile"]
    V --> PUB["Publish revision pointer"]
~~~

Scheduler tạo **ý định xử lý**. `JobRepository` ghi **lịch sử thực thi**. Business database lưu **kết quả đã commit**. Publish gate quyết định **revision nào được công bố**. Các tầng này có thể ở các database/resource khác nhau nên không tự commit atomic.

### 2.2. Một ngày đã COMPLETED khác một ngày chưa từng chạy

- **Chưa chạy:** tạo JobInstance mới với identifying params cố định.
- **FAILED/STOPPED:** sửa nguyên nhân, restart **cùng JobInstance** bằng `JobOperator.restart(failedExecutionId)` nếu đủ điều kiện.
- **COMPLETED:** chạy lại cùng identifying params thường bị từ chối (`JobInstanceAlreadyCompleteException`). Nếu cần correction, tạo **revision có chủ đích** và JobInstance mới, không chỉnh trạng thái metadata bằng SQL.
- **STARTED nhưng không thấy worker:** kiểm tra liveness, JobRepository, leases và side effects trước re-dispatch.

## 3. Ngày nghiệp vụ khác “24 giờ tính từ một timestamp”

Một ngày có thể được định nghĩa theo múi giờ `Asia/Ho_Chi_Minh`, theo từng tenant, hoặc theo giờ cutover (ví dụ 05:00 sáng theo hợp đồng). Không dùng timezone mặc định của container để tính ngày nghiệp vụ.

Với ngày D và zone Z, cửa sổ lịch chuẩn là:

\[
W(D,Z)=[\operatorname{startOfDay}(D,Z),\operatorname{startOfDay}(D+1,Z)).
\]

Item có event-time t thuộc D nếu:

\[
t\ge t_{\mathrm{from}}\quad\land\quad t<t_{\mathrm{to}}.
\]

Đây là **half-open interval**: bao gồm đầu, không bao gồm cuối. Các ngày liền kề sẽ không trùng mốc ranh giới.

### 3.1. Java 17: tính Instant chính xác theo ZoneId

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

record DayWindow(
        LocalDate businessDate,
        ZoneId zone,
        Instant startInclusive,
        Instant endExclusive) {

    static DayWindow of(LocalDate day, ZoneId zone) {
        Instant from = day.atStartOfDay(zone).toInstant();
        Instant to = day.plusDays(1).atStartOfDay(zone).toInstant();
        if (!from.isBefore(to)) {
            throw new IllegalStateException("Invalid day window");
        }
        return new DayWindow(day, zone, from, to);
    }
}
~~~

Sử dụng trong method/test:

~~~java
DayWindow w = DayWindow.of(
        LocalDate.parse("2026-11-20"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Ở vùng có **daylight saving time (DST)**, ngày dân sự có thể dài **23 hoặc 25 giờ**. Không tính end bằng `start.plusSeconds(86400)` nếu contract là “ngày theo lịch tại ZoneId”. Tính `day.plusDays(1).atStartOfDay(zone)` như trên, hoặc tính theo business cutover rule đã chốt.

Nếu muốn tái lập backfill nhiều năm sau, nên lưu **startInstant/endInstant đã chốt** và zone/tzdata policy trong immutable manifest; không phụ thuộc timezone database của JVM luôn giữ cùng quy tắc lịch sử.

### 3.2. SQL không trùng boundary

~~~sql
-- :startUtc và :endUtc là bound Instant/TIMESTAMPTZ.
SELECT event_id, event_time_utc, amount
FROM payment_event
WHERE event_time_utc >= :startUtc
  AND event_time_utc <  :endUtc
ORDER BY event_time_utc, event_id;
~~~

Index tham khảo:

~~~sql
CREATE INDEX idx_payment_event_time_id
    ON payment_event(event_time_utc, event_id);
~~~

Tránh `BETWEEN start AND end` cho các ngày liên tiếp vì nó thường bao gồm cả cuối. Tránh bọc cột bởi `DATE(event_time_utc AT TIME ZONE ...)` nếu predicate range có thể dùng index/partition pruning; cần xác minh kế hoạch truy vấn bằng `EXPLAIN ANALYZE`.

## 4. Event time, ingestion time, watermark và dữ liệu đến muộn

Một sự kiện xảy ra lúc 23:59 ngày D nhưng đến nguồn lúc 02:00 ngày D+2 cần thuộc **ngày D** nếu nghiệp vụ phân ngày theo event time. Chỉ lọc `ingested_at` theo ngày chạy sẽ sai.

| Trường | Ý nghĩa | Vai trò |
| --- | --- | --- |
| `event_time` | Sự kiện nghiệp vụ xảy ra | Chọn business day |
| `ingested_at` | Hệ thống nhận event | Theo dõi lateness và cutoff |
| `businessDate` | Ngày theo business timezone/cutover | Key kế hoạch và output |
| `sourceWatermark` | Mốc hoàn tất theo cam kết upstream | Điều kiện ngày READY |
| `freezeCutoff` | Mốc ingest/snapshot đã chốt | Tái lập nguồn |
| `snapshotId` | Định danh manifest/tập nguồn bất biến | Restart cùng input |
| `pipelineVersion` | Phiên bản quy tắc chuyển đổi | Identity/correction |
| `outputRevision` | Phiên bản kết quả có thể publish | Supersede và rollback pointer |

### 4.1. Allowed lateness là policy, không phải chứng minh đầy đủ

Giả sử chờ thêm 48 giờ sau cuối ngày:

\[
\operatorname{eligible}(D)
\Leftrightarrow
t_{\mathrm{now}}\ge \operatorname{endOfDay}(D,Z)+48h.
\]

Đây chỉ là chính sách chờ, **không chứng minh** upstream sẽ không xuất hiện sự kiện muộn hơn SLA. Một nguồn có watermark/snapshot hoàn tất đáng tin là điều kiện mạnh hơn; nếu quá hạn vẫn có late events, cần **correction revision** thay vì mutate input của JobInstance cũ.

### 4.2. Immutable snapshot manifest

~~~text
snapshotId        = payments-2026-11-20-r3
businessDate      = 2026-11-20
timeZone          = Asia/Ho_Chi_Minh
startUtc          = 2026-11-19T17:00:00Z
endUtc            = 2026-11-20T17:00:00Z
freezeCutoffUtc   = 2026-11-23T02:00:00Z
sourceFiles       = [versioned URI + etag/checksum, ...]
sourceCount       = 1,237,882
sourceChecksum    = sha256:<verified-value>
sourceSchema      = payments-v5
sourceWatermark   = <verified-value>
immutable         = true
~~~

Các giá trị `sourceChecksum`/`sourceCount` ở production phải được **đo**, không điền ví dụ thành dữ liệu thật. `latest` URI hoặc query bảng source mutable không đủ cho restart.

**Cảnh báo:** `WHERE ingested_at <= :cutoff` không tự tạo snapshot bất biến nếu rows cũ vẫn được UPDATE/DELETE sau cutoff. Cần immutable event store, frozen staging, versioned file manifest, CDC offsets/LSNs hoặc snapshot đã materialize.

### 4.3. Late correction sau publish

Khi daily output v1 đã publish mà late events đến:

1. Chốt source snapshot v2.
2. Tạo **JobInstance mới theo input revision v2**.
3. Tính kết quả v2 trong staging/versioned tables.
4. So với v1 và expected source keys, xác minh số lượng/tổng tiền.
5. Đổi publication pointer sang v2 chỉ khi validation đạt.
6. Giữ audit/rollback pointer về v1 nếu v2 có sự cố.

Không “restart” một `COMPLETED` JobInstance v1 với nguồn thay đổi.

## 5. Durable backfill plan: không giữ tiến độ trong vòng for RAM

Một request backfill tốt lưu:

~~~text
planId               = payments-backfill-202611-A
fromDateInclusive    = 2026-11-18
toDateExclusive      = 2026-11-24
zoneId               = Asia/Ho_Chi_Minh
pipelineVersion      = normalize-v3
snapshotPolicy       = immutable-per-day
priority             = BELOW_DAILY
maxConcurrentDays    = 2
maxWorkerPartitions  = 6 per day
requestedBy          = approved-operator
reason               = scheduler-outage
state                = PLANNED
~~~

Nếu UI nói “18 đến hết 23”, chuyển thành `[18,24)` **một lần tại boundary**. Nếu process crash sau ngày thứ ba, planner vẫn phải biết từng ngày `READY`/`RUNNING`/`FAILED`/`SUCCEEDED` để resume.

### 5.1. Schema PostgreSQL minh họa

~~~sql
CREATE TABLE backfill_plan (
    plan_id VARCHAR(100) PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    date_from DATE NOT NULL,
    date_to_exclusive DATE NOT NULL,
    zone_id VARCHAR(80) NOT NULL,
    pipeline_version VARCHAR(80) NOT NULL,
    priority INTEGER NOT NULL,
    max_concurrent_days INTEGER NOT NULL,
    state VARCHAR(24) NOT NULL,
    requested_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (date_from < date_to_exclusive),
    CHECK (max_concurrent_days > 0)
);

CREATE TABLE backfill_day (
    plan_id VARCHAR(100) NOT NULL REFERENCES backfill_plan(plan_id),
    business_date DATE NOT NULL,
    snapshot_id VARCHAR(120) NOT NULL,
    state VARCHAR(24) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    lease_owner VARCHAR(120),
    lease_token BIGINT NOT NULL DEFAULT 0,
    lease_until TIMESTAMPTZ,
    job_instance_id BIGINT,
    last_job_execution_id BIGINT,
    output_revision VARCHAR(120),
    validation_state VARCHAR(24),
    error_code VARCHAR(80),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(plan_id, business_date)
);
CREATE INDEX idx_backfill_day_claim
    ON backfill_day(state, next_attempt_at, updated_at);
~~~

Đây là schema **planner của ứng dụng**, không phải Spring Batch metadata tables. `PRIMARY KEY(plan_id,business_date)` **không** chặn hai plan khác nhau cùng xử lý một businessDate/snapshot và ghi một output key. Cần thêm unique logical work key, owner registry hoặc output-level guard theo yêu cầu.

### 5.2. Vì sao tách planner và JobRepository?

- Planner quyết định **ngày nào eligible**, resource admission, priority, dependencies, validation và publish.
- JobRepository quyết định **JobInstance/JobExecution/StepExecution**, checkpoints và restart.
- Business database lưu **output** và commit evidence.
- Các transitions như `PLANNED`, `READY`, `CLAIMED`, `PUBLISHED` là **trạng thái ứng dụng**, không phải `BatchStatus`.

Không đánh dấu planner `SUCCEEDED` ngay khi `JobLauncher.run` trả về: có launcher bất đồng bộ; ngay cả Job `COMPLETED` cũng cần quality gate trước publish.

## 6. JobInstance = ngày + snapshot + phiên bản logic

Spring Batch định danh JobInstance bằng **job name + identifying JobParameters**. Một JobInstance có thể có nhiều JobExecutions khi restart.

~~~text
Job name        = dailyPaymentProjection
businessDate    = 2026-11-20          identifying
snapshotId      = payments-20261120-r3 identifying
pipelineVersion = normalize-v3        identifying
zoneId          = Asia/Ho_Chi_Minh    identifying
planId          = payments-backfill-A non-identifying, audit only
requestedBy     = approved-operator   non-identifying, audit only
~~~

`planId` là non-identifying chỉ khi cùng ngày/snapshot/logic từ hai plans **thực sự được coi là một logical work**. Nếu một plan đòi độc lập về output, hãy dùng revision có nghĩa nghiệp vụ và unique logical key, không thêm `run.id` ngẫu nhiên để lách trạng thái COMPLETED.

### 6.1. Java Spring Batch 5.2: JobParametersBuilder

~~~java
import java.time.LocalDate;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

record DailyRunRequest(
        LocalDate businessDate, String snapshotId,
        String pipelineVersion, String zoneId,
        String planId, String requestedBy) {}

final class DailyParameters {
    static JobParameters from(DailyRunRequest req) {
        return new JobParametersBuilder()
                .addString("businessDate",
                        req.businessDate().toString(), true)
                .addString("snapshotId", req.snapshotId(), true)
                .addString("pipelineVersion",
                        req.pipelineVersion(), true)
                .addString("zoneId", req.zoneId(), true)
                .addString("planId", req.planId(), false)
                .addString("requestedBy", req.requestedBy(), false)
                .toJobParameters();
    }
}
~~~

API `addString(name,value,identifying)` được hỗ trợ trong Spring Batch 5.2. Phải chốt cả **những thông số ảnh hưởng output** trong identifying params hoặc immutable manifest do identifying key trỏ tới; non-identifying audit fields không được làm thay đổi tập dữ liệu.

### 6.2. Khi nào launch, restart hoặc correction?

| Trạng thái logic | Quyết định |
| --- | --- |
| Chưa có JobInstance | Launch Job với identifying params đã chốt |
| `STARTED` | Không tạo thêm execution đang chạy cho cùng instance |
| `FAILED`/`STOPPED` | Sau recovery check, `JobOperator.restart(executionId)` |
| `COMPLETED` | Không chạy lại cùng params theo mặc định; muốn correction tạo revision mới |
| `UNKNOWN`/stale STARTED | Điều tra worker liveness và metadata, không sửa BATCH_* mù |

`JobOperator.startNextInstance`/`RunIdIncrementer` không phải lệnh “resume đúng instance”: chúng có thể tạo **JobInstance mới**. Nếu cùng ngày đã completed nhưng dữ liệu mới đến, dùng source revision mới và publish workflow phù hợp.

### 6.3. Hai schedulers cùng launch: TOCTOU

Hai pods có thể cùng gọi `JobExplorer.findRunningJobExecutions(jobName)`, cùng thấy “không chạy”, rồi cùng launch. Pre-check không là distributed lock. Cần:

- Atomic claim/admission trong durable planner, có lease/fencing.
- JDBC JobRepository với constraints/isolation được cấu hình đúng.
- Catch `JobExecutionAlreadyRunningException`, `JobInstanceAlreadyCompleteException` và `JobRestartException`.
- Đối chiếu JobInstance bằng identifying params nếu claim bị mất sau crash.
- Không cho hai revisions cùng ghi đè output không versioned.

JobRepository bảo vệ lịch sử trong **cùng repository**, không tự khóa mọi external API side effect hoặc mọi planner không dùng cùng identity.

## 7. Scheduler chỉ kích hoạt, không thay durable work state

| Giải pháp | Phù hợp khi | Giới hạn cần xử lý |
| --- | --- | --- |
| Spring `@Scheduled` | Lịch đơn giản trong application | Replicas kích hoạt trùng; missed fires không tự replay bền |
| Quartz JDBC clustered | Lịch có state, misfires, cluster | JobStore/cluster config/ownership |
| Kubernetes CronJob | Launch workloads trong K8s | Missed schedules, `concurrencyPolicy`, timezone và job lifecycle |
| Airflow/Dagster | Backfill DAG/dependencies, UI/audit | Vẫn cần Spring Batch idempotency |
| Durable DB planner | Per-day priority/retry/lease/revision | Cần transaction/claim/fencing/reconciliation |
| Cloud scheduler + queue | Trigger ngoài JVM và workers độc lập | At-least-once/deduplication, quota |

**Spring Batch không phải cron scheduler**: `JobLauncher` chạy batch; JobRepository lưu executions; scheduler/planner quản lý kỳ lịch, missed days, holiday calendar, readiness và resource budgets.

### 7.1. @Scheduled enqueue thay vì chạy vòng backfill trong callback

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

@Configuration
@EnableScheduling
public class DailyScheduleTrigger {
    private static final ZoneId ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");
    private final DailyPlanService planner;

    public DailyScheduleTrigger(DailyPlanService planner) {
        this.planner = planner;
    }

    @Scheduled(cron = "0 15 2 * * *",
               zone = "Asia/Ho_Chi_Minh")
    public void enqueuePreviousDay() {
        LocalDate day = LocalDate.now(ZONE).minusDays(1);
        planner.requestIfEligible(day);
    }
}
~~~

`DailyPlanService` là service ứng dụng tự xây dựng. Spring cron có **6 trường** second/minute/hour/day/month/day-of-week; `0 15 2 * * *` là 02:15 trong zone chỉ định. Hàm không chạy Job nặng trong scheduler thread; nó yêu cầu planner lưu một work item idempotently **nếu ngày đã sẵn sàng**.

Nếu ứng dụng có 4 replicas, có thể có 4 triggers; `requestIfEligible` phải atomic dedupe hoặc chỉ leader lập kế hoạch. Nếu cluster downtime lúc 02:15, fire bị bỏ lỡ không tự replay chỉ vì `@Scheduled`; cần reconciler quét missing days.

### 7.2. Catch-up scanner khôi phục missed schedules

Một reconciler có thể chạy định kỳ:

~~~text
expected = allEligibleDates(calendarStart, latestReadyDay)
published = readPublishedDailyRevisions()
waived = readApprovedNotApplicableDays()
missing = expected - published - waived

for each day in missing:
    enqueueIfAbsent(day, immutableSnapshotId, pipelineVersion)
~~~

Cần giới hạn quãng tìm, phân biệt holiday/closed business day, watermark và retention. Không enqueue vô hạn mọi ngày lịch sử khi nguồn chưa ready.

### 7.3. Quartz, Kubernetes, DAG scheduler không thay business lock

- Kubernetes `CronJob.concurrencyPolicy=Forbid` áp dụng cho các Jobs thuộc **một CronJob resource**, không khóa các manual backfill khác.
- Quartz `@DisallowConcurrentExecution` ngăn overlap theo cùng `JobDetail/JobKey` trong scheduler cluster cấu hình đúng, không khóa ứng dụng ngoài Quartz.
- Airflow catch-up/backfill có data intervals và max-active-runs riêng; phải truyền đúng business date, snapshot/revision và không ghi output mù.

Mọi nguồn khởi động phải chia sẻ **logical work identity** hoặc có transaction-level output protection.

## 8. Quyết định song song theo ngày dựa trên dependency

| Loại workload | Có thể chạy ngày D và D+1 song song? | Điều kiện |
| --- | --- | --- |
| Aggregate events độc lập từng ngày | Thường có | Output keys theo ngày/version |
| Settlement đối soát riêng ngày | Có điều kiện | Số liệu upstream mỗi ngày đã frozen |
| Số dư lũy kế, carry-forward balance | Không được chạy bừa | D+1 cần output đã publish của D |
| Rolling 7-day feature | Có điều kiện | Bảy ngày input versioned, dependency rõ |
| Global deduplication qua history | Có điều kiện | Shared deterministic dedupe state |
| Bảng single-row “latest total” | Không an toàn nếu không versioned | Ngày cũ có thể ghi đè ngày mới |

~~~mermaid
flowchart LR
    A["18/11"] --> B["19/11"]
    B --> C["20/11"]
    C --> D["21/11"]
    D --> E["22/11"]
    E --> F["23/11"]
    F --> V["Reconcile/publish"]
~~~

Với balance có dependency xuyên ngày, phải tuân DAG; `maxConcurrentDays=2` không có nghĩa có thể chạy hai ngày bất kỳ. Với daily aggregates độc lập, có thể chạy nhiều ngày cùng lúc nhưng phải bảo đảm **cùng một output revision không có hai writers**.

### 8.1. Một JobInstance mỗi ngày hay một JobInstance toàn khoảng?

| Tiêu chí | Job mỗi ngày | Job toàn khoảng, partition theo ngày |
| --- | --- | --- |
| SLA/status theo ngày | Tự nhiên | Cần custom state theo partition |
| Restart một ngày | Restart JobInstance ngày đó | Restart worker StepExecution failed |
| Correction late events | Revision theo ngày rõ | Thường phải quản lý revision của cả plan |
| Dependencies xuyên ngày | DAG planner | Không nên parallel partition phụ thuộc |
| Partition manifest | Riêng mỗi ngày | Tên/ranges toàn Job phải cố định |
| Resource quota theo ngày | Admission ở planner | Handler/step-level admission |
| Metadata overhead | Nhiều JobInstances | Nhiều partition StepExecutions |

**Gợi ý:** với backfill lịch sử có publish/SLA riêng từng ngày, **JobInstance theo ngày + partition trong ngày nếu lớn** là thiết kế dễ vận hành. Nếu cả khoảng chỉ được publish cùng nhau và plan bất biến, có thể partition theo ngày trong một JobInstance.

### 8.2. Partition trong một ngày lớn

~~~text
jobName=dailyPaymentProjection
businessDate=2026-11-20
snapshotId=payments-20261120-r3

dailyWorker:shard-000 => event_id [1,250001)
dailyWorker:shard-001 => event_id [250001,500001)
...
dailyWorker:shard-031 => ...
~~~

`Partitioner` tạo stable names và `ExecutionContext` theo immutable manifest. `gridSize` không phải số threads; không phân chia lại ranges hoặc đặt random partition name khi restart cùng JobInstance.


## 9. Chống hai schedulers claim cùng ngày

Backfill planner nhiều replicas cần một **atomic claim** trước khi launch JobExecution. Ví dụ PostgreSQL, trong một transaction ngắn:

~~~sql
WITH candidate AS (
    SELECT plan_id, business_date
    FROM backfill_day
    WHERE state = 'READY'
      AND (next_attempt_at IS NULL OR next_attempt_at <= NOW())
    ORDER BY business_date
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE backfill_day d
SET state = 'CLAIMED',
    lease_owner = :plannerId,
    lease_token = lease_token + 1,
    lease_until = NOW() + INTERVAL '5 minutes',
    updated_at = NOW()
FROM candidate c
WHERE d.plan_id = c.plan_id
  AND d.business_date = c.business_date
RETURNING d.plan_id, d.business_date,
          d.snapshot_id, d.lease_token;
~~~

Câu lệnh này khóa một **planner row**. Hai plans có cùng ngày/snapshot/logic version nhưng khác `plan_id` vẫn có thể claim riêng. Để bảo vệ output thật, cần **unique logical work key** dùng chung giữa mọi plans (job name + date + snapshot + pipeline version + zone) hoặc một output-generation lock/fencing. Không cho hai writers cùng ghi một revision chỉ vì cả hai schedulers đều được phép chạy.

### 9.1. Một claim không phải transaction kéo dài cả Job

Quy trình an toàn:

1. Claim row trong DB transaction ngắn và commit.
2. Xác minh snapshot checksum, identifying `JobParameters` và dependencies.
3. Tra lịch sử trong `JobRepository` theo **job name + identifying params**.
4. Launch JobInstance mới hoặc restart execution cũ theo state/policy.
5. Persist `JobInstanceId`, `JobExecutionId` vào planner cùng owner/lease heartbeat.
6. Theo dõi StepExecutions, output và quality gate tới khi hoàn tất.
7. Đánh dấu ledger `SUCCEEDED` chỉ khi Job `COMPLETED` **và** validation đạt.
8. Publish revision hoặc đưa item vào `FAILED/RETRY_WAIT` với audit.

**Crash window:** worker/planner có thể chết sau `JobLauncher.run` nhưng trước khi lưu execution ID vào planner. Khi lease hết hạn, claimant mới phải **lookup JobRepository**, không tạo Job mới mù. Lease hết hạn **không chứng minh remote worker cũ đã dừng**; cần liveness/fencing và idempotency.

### 9.2. Giới hạn độ dài range

~~~java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

final class BackfillDateRange {
    static void requireApprovedRange(
            LocalDate from, LocalDate toExclusive) {
        if (!from.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid date range");
        }
        if (ChronoUnit.DAYS.between(from, toExclusive) > 366) {
            throw new IllegalArgumentException(
                    "Approval required for large backfill");
        }
    }
}
~~~

Giới hạn 366 là **policy ví dụ**. Cần kiểm soát ngày tối thiểu/tối đa, quota và retention; không tạo hàng trăm JobExecutions đồng thời chỉ vì range đã hợp lệ.

## 10. Đóng băng dữ liệu từng ngày

Nếu backfill một ngày lịch sử mất vài giờ, input không được đổi khi retry/restart. Có thể tạo staging table chỉ được ghi trước khi manifest READY:

~~~sql
CREATE TABLE frozen_payment_event (
    snapshot_id VARCHAR(120) NOT NULL,
    business_date DATE NOT NULL,
    event_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    PRIMARY KEY(snapshot_id, event_id)
);
CREATE INDEX idx_frozen_payment_day
    ON frozen_payment_event(snapshot_id, business_date, event_id);
~~~

Một `snapshotId` có thể chứa dữ liệu một ngày hoặc nhiều ngày, nhưng phải có contract rõ; `business_date` không được tự tính lại khác nhau giữa hai lần JobExecution. Sau khi snapshot READY, bảo vệ khỏi UPDATE/DELETE; late data sẽ tạo revision mới.

**Không** dùng pagination OFFSET trên bảng nguồn mutable rồi coi đó là restart checkpoint an toàn. Dùng immutable rows và deterministic ordering hoặc keyset paging.

## 11. Java Spring Batch 5.2: reader theo ngày, snapshot và checkpoint

~~~java
import java.time.LocalDate;
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

record PaymentSnapshotRow(
        long eventId, long sourceVersion,
        java.math.BigDecimal amount, String payloadHash) {}

@Bean("dailySnapshotReader")
@StepScope
public JdbcCursorItemReader<PaymentSnapshotRow> dailySnapshotReader(
        @Qualifier("sourceDataSource") DataSource sourceDs,
        @Value("#{jobParameters['snapshotId']}") String snapshotId,
        @Value("#{jobParameters['businessDate']}") String dayText) {

    LocalDate day = LocalDate.parse(dayText);
    return new JdbcCursorItemReaderBuilder<PaymentSnapshotRow>()
            .name("dailySnapshotReader")
            .dataSource(sourceDs)
            .sql("""
                SELECT event_id, source_version, amount, payload_hash
                FROM frozen_payment_event
                WHERE snapshot_id = ? AND business_date = ?
                ORDER BY event_id
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, snapshotId);
                ps.setObject(2, day);
            })
            .rowMapper((rs, n) -> new PaymentSnapshotRow(
                    rs.getLong("event_id"),
                    rs.getLong("source_version"),
                    rs.getBigDecimal("amount"),
                    rs.getString("payload_hash")))
            .fetchSize(1_000)
            .saveState(true)
            .build();
}
~~~

Code là bean method để đặt trong class `@Configuration`; record/beans hạ tầng của ứng dụng cần được khai báo ở file đúng. Các API `preparedStatementSetter`, `name` và `saveState` thuộc Spring Batch 5.2. Với `@StepScope`, reader được tạo theo `StepExecution` của worker, **không** theo từng thread nếu một multi-threaded step chia sẻ StepExecution.

Các điều kiện restart:

- `event_id` là unique trong snapshot, làm `ORDER BY event_id` xác định.
- `snapshotId`, `businessDate` và source data bất biến qua restart.
- `ItemStream` lifecycle được framework quản lý, checkpoint được persist.
- Nếu nguồn từ connection riêng, source có cursor/resource budget riêng.
- Nếu worker crash sau business commit nhưng trước checkpoint, reader có thể replay; writer cần idempotency.
- Nếu checkpoint tiến nhưng business output chưa ghi, idempotency **không tự khôi phục missing row**; cần transaction coordination hoặc reconciliation.

## 12. Writer idempotent theo business key và revision

Không viết một incremental counter kiểu:

~~~sql
-- KHÔNG idempotent khi replay:
UPDATE customer_balance
SET balance = balance + :amount
WHERE customer_id = :customerId;
~~~

Khi chunk replay, balance có thể cộng lại. Với normalized facts, lưu một record cho mỗi event + immutable revision:

~~~sql
CREATE TABLE daily_payment_fact (
    business_date DATE NOT NULL,
    output_revision VARCHAR(120) NOT NULL,
    event_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    PRIMARY KEY(business_date, output_revision, event_id)
);

-- Dùng trong JDBC chunk transaction:
INSERT INTO daily_payment_fact(
    business_date, output_revision, event_id,
    source_version, amount, payload_hash)
VALUES (
    :businessDate, :revision, :eventId,
    :sourceVersion, :amount, :payloadHash)
ON CONFLICT (business_date, output_revision, event_id)
DO NOTHING;
~~~

`output_revision` phải ổn định cho cả JobInstance. Khi cùng key đã tồn tại, `DO NOTHING` có thể tạo update count 0; đây là hành vi replay hợp lệ, nhưng **nếu payload_hash/source_version/amount khác** thì hệ thống phải phát hiện conflict và fail. Unique key **không** tự chứng minh hai payload giống nhau.

### 12.1. Spring JdbcBatchItemWriter minh họa

~~~java
import java.time.LocalDate;
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;

record DailyFact(
        LocalDate businessDate, String outputRevision,
        long eventId, long sourceVersion,
        java.math.BigDecimal amount, String payloadHash) {}

@Bean("dailyFactWriter")
public JdbcBatchItemWriter<DailyFact> dailyFactWriter(
        @Qualifier("businessDataSource") DataSource ds) {
    return new JdbcBatchItemWriterBuilder<DailyFact>()
            .dataSource(ds)
            .sql("""
                INSERT INTO daily_payment_fact(
                    business_date, output_revision, event_id,
                    source_version, amount, payload_hash)
                VALUES (
                    :businessDate, :revision, :eventId,
                    :sourceVersion, :amount, :payloadHash)
                ON CONFLICT (
                    business_date, output_revision, event_id)
                DO NOTHING
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                        .addValue("businessDate", item.businessDate())
                        .addValue("revision", item.outputRevision())
                        .addValue("eventId", item.eventId())
                        .addValue("sourceVersion", item.sourceVersion())
                        .addValue("amount", item.amount())
                        .addValue("payloadHash", item.payloadHash()))
            .assertUpdates(false)
            .build();
}
~~~

`DailyFact` phải được tạo bởi processor xác định date/revision từ identifying params hoặc manifest; không tạo ngẫu nhiên khi retry. `assertUpdates(false)` chấp nhận upsert/no-op hợp lệ, **không được bỏ bước kiểm tra conflict payload**.

### 12.2. Worker Step transaction

~~~java
@Bean("dailyWorkerStep")
public Step dailyWorkerStep(
        JobRepository repository,
        @Qualifier("businessTxManager")
            PlatformTransactionManager tx,
        @Qualifier("dailySnapshotReader")
            ItemReader<PaymentSnapshotRow> reader,
        ItemProcessor<PaymentSnapshotRow, DailyFact> processor,
        @Qualifier("dailyFactWriter") ItemWriter<DailyFact> writer) {
    return new StepBuilder("dailyWorkerStep", repository)
            .<PaymentSnapshotRow, DailyFact>chunk(500, tx)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Imports Spring Batch `Step`, `StepBuilder`, `JobRepository`, `ItemReader/Processor/Writer` và `PlatformTransactionManager` cần bổ sung trong class `@Configuration`. Writer phải tham gia **business datasource transaction** đúng manager. Nếu repository checkpoint ở datasource khác, two-local-commit failure window vẫn có.

### 12.3. Recompute aggregate theo revision

~~~sql
SELECT business_date, output_revision,
       COUNT(*) AS event_count,
       COALESCE(SUM(amount),0) AS total_amount
FROM daily_payment_fact
WHERE business_date = :businessDate
  AND output_revision = :revision
GROUP BY business_date, output_revision;
~~~

Tránh `total = total + delta` khi retry không có idempotent event ledger. Recompute từ immutable facts của một revision để dễ validation và correction.

## 13. Stage → validate → publish, không để người dùng đọc partial output

Một JobExecution `COMPLETED` chỉ nói framework hoàn tất kỹ thuật. Trước khi publish:

1. So expected/actual **unique business keys** từ snapshot.
2. Kiểm tra source version, amount, payload hash, duplicates/conflicts.
3. Đối chiếu tổng tiền, null/negative rules và business invariants.
4. Xác minh mọi worker/StepExecutions trong ngày đã hoàn tất.
5. Ghi evidence validation (count, checksum, code version, timestamps).
6. Chuyển publication pointer tới revision đã được nghiệm thu.

### 13.1. Publication pointer và optimistic guard

~~~sql
CREATE TABLE daily_publication (
    business_date DATE PRIMARY KEY,
    current_revision VARCHAR(120) NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generation BIGINT NOT NULL DEFAULT 1
);

UPDATE daily_publication
SET current_revision = :newRevision,
    published_at = NOW(),
    generation = generation + 1
WHERE business_date = :day
  AND generation = :expectedGeneration;
~~~

Nếu UPDATE count 0, phân biệt ngày chưa có pointer với generation conflict. Với ngày đầu tiên dùng `INSERT` dưới unique key và kiểm tra race. Consumer/dashboard phải chỉ đọc revision mà pointer trỏ tới, không tự query tất cả rows staging.

- **Publish từng ngày** nếu downstream chấp nhận các ngày có revision khác nhau.
- **Publish cả range** sau khi tất cả 18–23 validated nếu báo cáo đòi consistency một lần phát hành. Nếu pointers trong cùng DB, có thể cập nhật trong một transaction ngắn; với nhiều stores cần versioned manifest/release protocol.

**Business DB và object storage không tự atomic**: nếu output là file/object, cần temporary output + checksum + commit marker/manifest pointer, không giả sử JDBC rollback xóa file.

## 14. Backfill không được tranh hết tài nguyên của daily SLA

| Tài nguyên | Dự trữ daily (ví dụ) | Backfill (ví dụ) |
| --- | ---: | ---: |
| Business DB connections | 30 | 12 |
| JobRepository connections | 8 | 4 |
| HTTP requests/s | 60 | 20 |
| Active worker partitions | 12 | 6 |
| Concurrent backfill days | N/A | 2 |
| CPU/heap/IOPS | Theo benchmark | Chỉ dùng phần được cấp |

Nếu 2 ngày backfill, mỗi ngày cấu hình 6 worker partitions, có thể yêu cầu 12 workers, nhưng nếu dùng shared executor 6 threads thì chỉ tối đa 6 active. `gridSize`, executor core/max/queue, JDBC pool, remote workers và API quota **không là cùng một chỉ số**.

### 14.1. SLA sizing với committed throughput

Giả định backlog 7.200.000 items và cửa sổ xử lý 4 giờ:

\[
R_{\mathrm{required}}=
\frac{7{,}200{,}000}{4\times3600}
=500\ \mathrm{committed\ items/s}.
\]

Một worker đo được 110 items/s khi chạy một mình cho số lý tưởng:

\[
C_{\mathrm{ideal}}=
\left\lceil500/110\right\rceil=5.
\]

Nhưng `5×110` không phải bảo đảm: contention DB, data skew, retries và GC làm throughput không tuyến tính. Benchmark tại concurrency 1,2,4,6,8,... dưới ngân sách toàn cluster, đo **committed throughput và output correctness**.

### 14.2. Downstream quá tải: giảm admission trước

Nếu Hikari pending, DB lock waits, HTTP 429/503 hoặc broker lag tăng:

- Dừng nhận thêm **ngày mới** hoặc giảm worker concurrency.
- Bounded retry/backoff+jitter, tôn trọng `Retry-After`.
- Không `Thread.sleep` lâu trong chunk transaction đang giữ JDBC resource.
- Với finite Job phải dừng, `JobOperator.stop` là cooperative; đợi `STOPPED` rồi restart đúng instance.
- Giữ backlog trong durable ledger, không ACK/drop work chưa hoàn tất.
- Khi khỏe lại, ramp capacity theo p95/p99 và committed throughput, không xả toàn bộ backlog.

## 15. Dependencies xuyên ngày và business calendar

Một số workloads không thể chạy song song theo ngày:

- **Balance carry-forward:** openingBalance(D)=closingBalance(D-1).
- **Cumulative unique count:** D cần state đã kiểm chứng của D-1.
- **Rolling 7 days:** tính D phụ thuộc các version đã freeze của D-6..D.
- **Late correction ở ngày cũ:** các ngày sau đang dựa vào revision trước có thể cần rebuild.

### 15.1. Dependency invalidation

Nếu ngày 20 chuyển revision r1 → r2 mà ngày 21 tính từ số dư r1, planner phải:

1. Xác định revisions downstream phụ thuộc ngày 20 r1.
2. Đánh dấu **STALE/NEEDS_REBUILD** trong ledger (ứng dụng tự định nghĩa).
3. Tạo plan tái tính theo DAG tới ngày bị ảnh hưởng cuối.
4. Ghi output versions mới song song với versions cũ.
5. Validation và publish theo thứ tự/manifest phù hợp.

Không chỉ kiểm tra `JobExecution.COMPLETED` của ngày 20 rồi bỏ qua downstream dependencies.

### 15.2. Holiday calendar và cutover

`LocalDate.minusDays(1)` là ngày lịch trước, không chắc là **business day trước** khi gặp cuối tuần/ngày nghỉ. Với settlement, cần calendar versioned theo market/tenant, quy tắc holiday và cutover giờ. Backfill plan nên chốt calendar version để restart không tự thêm/bớt kỳ khi lịch thay đổi.

**Câu hỏi thiết kế:** “ngày” của hệ thống là civil date, trading day, bank posting date hay accounting period? Scheduler và reconciliation đều phải dùng cùng định nghĩa.


## 16. Partition trong một ngày và tránh worker skew

Một JobInstance/ngày vẫn có thể chia workload của ngày đó thành nhiều partitions theo file, tenant hoặc ID range. Dùng `Partitioner` để tạo tên ổn định, `ExecutionContext` theo worker, và `PartitionHandler` chạy trên `TaskExecutor` hoặc remote workers.

### 16.1. Spring Batch 5.2 local partition manager

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;

@Bean("dailyPartitionManager")
public Step dailyPartitionManager(
        JobRepository repository,
        Partitioner immutableDayPartitioner,
        @Qualifier("dailyWorkerStep") Step workerStep,
        @Qualifier("dailyPartitionExecutor") TaskExecutor executor) {

    return new StepBuilder("dailyPartitionManager", repository)
            .partitioner("dailyWorkerStep", immutableDayPartitioner)
            .step(workerStep)
            .gridSize(8)
            .taskExecutor(executor)
            .build();
}
~~~

Đây là bean method trong `@Configuration`; cần cung cấp `immutableDayPartitioner` và bounded executor. `gridSize(8)` là input/hint để chia/dispatch, **không phải luôn có tám threads**. `Partitioner.partition(...)` phải trả tên partition duy nhất gắn với frozen manifest; nếu hỗ trợ `PartitionNameProvider` thì tập tên từ `getPartitionNames(...)` phải khớp kế hoạch gốc khi restart.

### 16.2. Partition key và reader context

~~~text
JobInstance: dailyPaymentProjection(date=2026-11-20,snapshot=r3)

dailyWorkerStep:file-000
  snapshotId = payments-20261120-r3
  fileUri    = .../file-000.parquet
  fileHash   = sha256:...
dailyWorkerStep:file-001
  snapshotId = payments-20261120-r3
  fileUri    = .../file-001.parquet
  fileHash   = sha256:...
~~~

Không thay file list, shard ranges, tên partitions hoặc `gridSize`-dependent plan giữa restart cùng JobInstance. Worker `@StepScope` lấy `stepExecutionContext` tương ứng. Nếu dùng một query cursor reader thay vì file reader, nên partition theo disjoint key ranges và sort deterministic.

### 16.3. Skew ảnh hưởng SLA

Giả sử 8 partitions, 7 partitions chạy 3 phút, riêng partition thứ 8 chạy 40 phút do quá nhiều events. Tổng job không xong trong 3 phút dù có tám threads. Giải pháp là cải thiện split dựa trên **ước lượng cardinality/bytes/cost**, không thay partition plan khi đang restart. Nếu phải tạo split mới, thực hiện qua **một JobInstance/revision mới** có chiến lược supersession và checkpoint/data migration rõ.

## 17. Retry và restart theo ngày không làm mất lịch sử các ngày khác

Giả sử plan gồm sáu ngày:

| Ngày | Kết quả lần đầu | Hành động |
| --- | --- | --- |
| 18/11 | `COMPLETED` + validated | Giữ output, không chạy lại |
| 19/11 | `COMPLETED` + validated | Giữ output, không chạy lại |
| 20/11 | `FAILED` ở chunk thứ 150 | Restart JobInstance của ngày 20 |
| 21/11 | `READY`, chưa claim | Chờ admission/dependency |
| 22/11 | `BLOCKED` vì watermark | Chờ snapshot READY |
| 23/11 | `CLAIMED` nhưng mất worker | Reconcile lease/JobRepository trước dispatch |

Không xóa tất cả output sáu ngày chỉ vì ngày 20 bị lỗi. Nếu ngày 20 đã commit 149 chunks, **chúng vẫn tồn tại**; restart phải dùng checkpoint và writer replay-safe.

### 17.1. JobOperator.restart đúng cách

~~~java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class BackfillRecoveryService {
    private final JobOperator operator;

    public BackfillRecoveryService(JobOperator operator) {
        this.operator = operator;
    }

    public long restartAfterValidation(long failedExecutionId)
            throws Exception {
        // Caller đã kiểm tra status, input snapshot,
        // worker liveness, admission và business reconciliation.
        return operator.restart(failedExecutionId);
    }
}
~~~

`restart` của Spring Batch 5.2 nhận JobExecution ID đã failed/stopped, không phải JobInstance ID. Nó không phải cách chạy lại JobInstance đã `COMPLETED`. Production cần xử lý `JobInstanceAlreadyCompleteException`, `NoSuchJobExecutionException`, `JobRestartException`, audit và authorization riêng.

### 17.2. Multi-day retry budget phải bền

`retryLimit(3)` ở `FaultTolerantStepBuilder` là policy retry trong worker execution, **không phải global cap cho cùng event xuyên mọi JobExecutions**. Nếu scheduler cứ restart một ngày failed mỗi 5 phút suốt ba ngày, tổng attempts có thể rất lớn.

Backfill ledger nên có:

- `attempt_count` bền vững theo logical day/revision.
- `next_attempt_at` với exponential backoff/jitter/Retry-After.
- `error_code` phân loại transient/permanent/data poison.
- Maximum restarts/daily work theo policy.
- Thời điểm chuyển `QUARANTINED/MANUAL_REVIEW` nếu lỗi không thể tự phục hồi.
- Audit operation IDs dùng cùng idempotency key cho external effects.

Tránh dùng `skip` chỉ để job báo xanh nếu dữ liệu tài chính bắt buộc không được bỏ qua.

### 17.3. JobRepository và business DB có hai loại transaction

Nếu chunk business writer dùng manager A nhưng repository lưu `ExecutionContext` trên DB B, checkpoint và data **không tự atomic**. Crash có thể dẫn tới:

- Business commit nhưng checkpoint cũ → item replay; writer phải idempotent.
- Checkpoint tiến mà business output chưa commit → item có thể bị bỏ sót; cần reconciliation/repair.

Đối với một ngày lớn, lỗi thứ hai đặc biệt khó phát hiện chỉ qua `writeCount`. So tập event IDs/hash với snapshot expected trước publish, không chỉ dựa vào JobExecution `COMPLETED`.

## 18. SQL đối soát ngày, revision và metadata

### 18.1. Chứng minh output chứa đủ event IDs

~~~sql
-- Những source events chưa có kết quả cùng ngày/revision/version.
SELECT s.event_id, s.source_version, s.payload_hash
FROM frozen_payment_event s
LEFT JOIN daily_payment_fact f
  ON f.business_date = s.business_date
 AND f.output_revision = :revision
 AND f.event_id = s.event_id
 AND f.source_version = s.source_version
 AND f.payload_hash = s.payload_hash
WHERE s.snapshot_id = :snapshotId
  AND s.business_date = :businessDate
  AND f.event_id IS NULL;
~~~

Query trả những events thiếu **hoặc không khớp version/hash**. Kết quả phải rỗng với contract one-to-one. Bổ sung query tìm **extra** output rows không thuộc snapshot (ngoài source) và duplicate logical keys nếu unique constraint không đủ theo business rules.

### 18.2. Đối chiếu counts và totals

~~~sql
SELECT COUNT(*) AS expected_count,
       COALESCE(SUM(amount), 0) AS expected_amount
FROM frozen_payment_event
WHERE snapshot_id = :snapshotId
  AND business_date = :businessDate;

SELECT COUNT(*) AS actual_count,
       COALESCE(SUM(amount), 0) AS actual_amount
FROM daily_payment_fact
WHERE business_date = :businessDate
  AND output_revision = :revision;
~~~

Một count bằng nhau có thể che một record thiếu và một record thừa; số tiền bằng nhau cũng có thể do các sai lệch triệt tiêu. **So khóa/version/hash là bắt buộc** bên cạnh counts/totals.

### 18.3. Lịch sử Spring Batch JobInstance

~~~sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS AS JOB_STATUS,
    je.START_TIME,
    je.END_TIME,
    se.STEP_NAME,
    se.STATUS AS STEP_STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE ji.JOB_INSTANCE_ID = :jobInstanceId
ORDER BY je.JOB_EXECUTION_ID, se.STEP_EXECUTION_ID;
~~~

Query chỉ đọc, giúp phát hiện StepExecution nào đã `COMPLETED`, ngày bị restart mấy lần và rollback counts. `READ_COUNT` là thống kê kỹ thuật, **không phải số unique business records** qua các retries/executions.

### 18.4. Kiểm tra khoảng ngày thiếu

Một bảng `daily_publication` cho phép tra ngày chưa có revision published. Ví dụ PostgreSQL:

~~~sql
SELECT d::date AS missing_day
FROM generate_series(
         CAST(:fromDay AS date),
         CAST(:lastDayInclusive AS date),
         INTERVAL '1 day') AS d
LEFT JOIN daily_publication p
  ON p.business_date = d::date
WHERE p.business_date IS NULL
ORDER BY missing_day;
~~~

Trong môi trường có **non-business days**, cần join lịch nghiệp vụ thay vì coi mọi calendar day đều bắt buộc. Đừng dùng kết quả query này để auto-backfill mọi ngày thiếu nếu upstream watermark/snapshot chưa đủ.

## 19. Observability và SLA của backfill

Một dashboard hữu ích phải phân biệt *ngày được lập kế hoạch*, *ngày hoàn tất kỹ thuật* và *ngày đã publish*.

| Nhóm | Metric/field đề xuất | Câu hỏi |
| --- | --- | --- |
| Planner | planned/ready/claimed/running/blocked/failed days | Backlog ở state nào? |
| Eligibility | watermark delay, snapshot age, manifest failures | Ngày bị kẹt do nguồn hay do capacity? |
| Scheduler | last trigger, missed expected days, claim conflicts | Có bỏ lỡ ngày không? |
| Batch | JobExecution/StepExecution status, chunk commits, rollback | Chunk có tiến bền không? |
| Resource | active partitions, Hikari active/pending, CPU, heap | Có tranh daily SLA không? |
| HTTP/broker | 429/503, rate, in-flight, retries, unacked/lag | Downstream có quá tải? |
| Correctness | expected/actual keys, hash mismatch, total amount | Có missing/duplicate không? |
| Publish | revision age, pointer generation, validation state | Người dùng đã nhìn thấy revision mới? |
| SLA | committed items/s, ETA, plan deadline, recovery buffer | Có kịp hết backlog? |
| Drift | snapshot/partition manifest mismatch | Restart có an toàn? |

Tên metric là **đề xuất**, tùy Spring Batch/Micrometer/instrumentation thực tế. Tránh đưa `event_id` và hàng triệu `businessDate+tenantId+revision` combinations vào metric labels; dùng logs/traces/ledger có retention phù hợp.

### 19.1. ETA theo ngày, không chỉ theo số records

Nếu các ngày có skew lớn, ETA phải tính cả thời gian ngày chậm nhất, dependencies và publish. Với serial DAG:

\[
T_{\mathrm{total}}
\gtrsim \sum_{d} T_d
+T_{\mathrm{validation}}
+T_{\mathrm{publish}}
+T_{\mathrm{recovery}}.
\]

Với các ngày độc lập chạy song song có giới hạn C, thời gian lý tưởng không thấp hơn cả:

\[
T_{\mathrm{parallel}}
\ge\max\left(
\max_d T_d,\;
\frac{\sum_d T_d}{C}
\right)
\]

trong mô hình đơn giản chưa tính shared-resource contention. **Nút thắt downstream**, không phải số ngày, có thể quyết định thời gian thực.

### 19.2. Backfill impact budget

Theo dõi thêm daily production metrics khi chạy backfill: p99 của daily job, number of missed deadlines, DB lock waits, read replicas lag, HTTP quota và queue age. Nếu backfill throughput tăng nhưng daily SLA giảm mạnh, cần giảm admission backfill hoặc đổi giờ chạy.

## 20. Fault-injection: kiểm thử từng ngày và toàn kế hoạch

| Tình huống | Cách thử | Kết quả đúng |
| --- | --- | --- |
| Scheduler outage | Tắt tất cả replicas qua thời điểm cron | Reconciler phát hiện missing day |
| Duplicate trigger | Hai pods cùng enqueue ngày D | Một logical work được nhận |
| Lost planner lease | Kill process sau claim trước launch | Work được claim lại sau liveness check |
| Crash sau JobLauncher.run | Kill trước persist JobExecution ID | Tra JobRepository, không tạo duplicate work |
| Business commit trước checkpoint | Kill ở crash window | Replay idempotent |
| Checkpoint trước business commit | Fault injection khi metadata/data tách DB | Reconciliation phát hiện missing keys |
| Worker fail sau 150 chunks | Ném lỗi ở một partition | Chunks trước vẫn có, restart phần chưa xong |
| Source snapshot drift | Thay hash/files khi restart | Fail closed, không xử lý nguồn khác |
| Partition plan drift | Đổi shard names/ranges | Phát hiện, không silently repartition |
| Late event sau publish | Đưa event D vào sau cutoff | Revision mới, supersede có validation |
| Cumulative dependency fail | D-1 FAILED, D vẫn READY | Planner BLOCKED D, không chạy sai |
| Two plans same day | Cùng date/snapshot/logic khác planId | Global logical key ngăn duplicate writer |
| Publish pointer race | Hai revisions cùng publish | Generation guard phát hiện conflict |
| API rate limited | Fake 429/503 với Retry-After | Backpressure, không retry storm |
| DB saturation | Giảm pool/tăng contention | Bounded concurrency/retry, không mất work |
| Remote worker crash | Kill sau commit trước reply | Liveness/fencing và writer idempotency |
| Operator cancel/stop | Stop giữa chunk rồi restart | Checkpoint và output đúng |
| SQL aggregate mismatch | Inject missing/extra row | Quality gate FAIL, không publish |
| Rolling update surge | Chạy old+new workers | Cluster quotas vẫn trong budget |
| Calendar version đổi | Sửa holiday/cutover policy | Existing plan vẫn dùng version cũ |

### 20.1. Integration test một ngày FAILED rồi restart

~~~text
Given:
  ngày D có 1.000 source events trong immutable snapshot;
  chunk size 100, output revision r3 rỗng.

When:
  chunk 1–4 COMMIT;
  chunk 5 ném RuntimeException trước commit;
  retry budget hết; JobExecution FAILED.

Then:
  400 events đầu đã commit còn trong output;
  chunk 5 không có partial writes nếu đúng DB TX;
  không publish r3.

When:
  sửa dependency và restart JobExecution cũ;
  reader phục hồi checkpoint, writer replay-safe.

Then:
  output r3 có đúng 1.000 unique event keys/version/hash;
  daily publication pointer chỉ chuyển sang r3 sau validation;
  không có duplicate side effects.
~~~

### 20.2. Test nhiều ngày với dependencies

~~~text
Given:
  Plan 18..23, cumulative balance;
  D=20 bị FAILED và D=21..23 chưa được thực hiện.

When:
  backfill scheduler chạy với maxConcurrentDays=3.

Then:
  D=21 không được start trước D=20 validated/published;
  các ngày 18,19 vẫn giữ COMPLETED output;
  restart D=20 rồi mới unlock D=21;
  final cumulative balance == clean reference run.
~~~

Không chỉ assert `BatchStatus.COMPLETED`; so actual business keys, versions, totals, publication revisions và outbox/external effects.

## 21. Runbook backfill lịch sử

### 21.1. Trước khi chạy

1. Ghi incident/change ID, người yêu cầu và phê duyệt phạm vi dữ liệu.
2. Xác định **business calendar, zone/cutover**, from inclusive/to exclusive.
3. Xác định ngày missing, failed, blocked và completed từ ledger/JobRepository.
4. Xác minh allowed lateness, watermark và source completeness.
5. Freeze immutable snapshot/manifest cho từng ngày, ghi counts/checksums/schema.
6. Chốt pipeline version, output revision và identifying JobParameters.
7. Xác định dependencies, những ngày cần chạy tuần tự.
8. Chọn admission budget sau khi bảo vệ daily SLA và online traffic.
9. Ước lượng throughput/ETA, timeout, retry/backoff và SLA headroom.
10. Thử dry run/validation query trên mẫu đại diện trước production.

### 21.2. Trong khi chạy

11. Enqueue durable plan và để planner atomic claim work, không manual loop launch vô kiểm soát.
12. Theo dõi JobInstance/JobExecution identity, active StepExecutions và partition names.
13. Phân biệt `READY` vì nguồn đủ với `RUNNING` vì đã có worker slot.
14. Đo committed throughput, Hikari pending, DB locks, HTTP quota, consumer lag.
15. Với ngày FAILED, phân loại transient/permanent/data poison, không restart vô hạn.
16. Với `STARTED` stale, xác minh worker cũ đã dừng trước khi phát lại.
17. Không sửa `BATCH_*` statuses để “cho xanh”, không tạo `run.id` tùy ý.
18. Nếu downstream quá tải, giảm admission ngày mới, giữ durable backlog.

### 21.3. Trước và sau publish

19. So từng ngày expected/actual keyset, versions, hashes, totals.
20. Đánh dấu validation PASS/FAIL cùng evidence và audit.
21. Kiểm tra các phụ thuộc xuyên ngày đã dùng đúng revision upstream.
22. Publish per-day hoặc all-range qua pointer/manifest atomic phù hợp.
23. Theo dõi dashboard downstream để chắc kết quả revision đã được đọc đúng.
24. Khi có late correction, tạo revision mới, không mutate source của JobInstance cũ.
25. Lưu kết quả, SLA miss/recovery overhead, thay đổi capacity và nguyên nhân sự cố.

## 22. Những hiểu nhầm thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “Backfill là gọi cron sáu lần.” | Cần kế hoạch bền, snapshots, versions, admission và quality gate. |
| “Một ngày luôn dài 24 giờ.” | Ngày theo ZoneId có thể 23/25 giờ do DST. |
| “`LocalDate.now()` của pod xác định business day.” | Phải chọn business timezone/cutover rõ. |
| “`BETWEEN` không trùng ngày.” | Hai biên inclusive có thể nhân đôi item ở ranh giới. |
| “Source có cutoff là bất biến.” | UPDATE/DELETE sau cutoff có thể thay input. |
| “Lịch đã trigger nên ngày có dữ liệu.” | Scheduler success khác snapshot completeness/output. |
| “`@Scheduled` trên 4 pods chạy đúng một lần.” | Mỗi replica có thể fire, cần dedupe/leader. |
| “`findRunningJobExecutions` là distributed lock.” | Kiểm tra-đến-launch vẫn có race. |
| “Job COMPLETED có thể restart để sửa dữ liệu.” | Correction phải có revision/JobInstance được quản lý. |
| “Thêm run.id là restart an toàn.” | Tạo JobInstance mới, có thể chạy lại toàn input. |
| “One planId key chặn plans khác chạy trùng ngày.” | Cần logical work identity chung giữa mọi plans. |
| “Lease hết hạn nghĩa worker đã chết.” | Có thể worker vẫn commit; cần liveness/fencing. |
| “GridSize là max worker threads.” | Partition hint khác executor/pod capacity. |
| “Một chunk FAILED làm rollback cả ngày.” | Chunks đã commit trước đó vẫn còn. |
| “DO NOTHING đủ chứng minh same payload.” | Phải kiểm tra hash/version conflict. |
| “Idempotent upsert chữa checkpoint ahead.” | Item bị bỏ qua cần reconciliation/repair. |
| “Ngày độc lập có thể ghi chung latest output.” | Cần versioned keys/publish pointer. |
| “D+1 có thể chạy dù D chưa xong số dư.” | Cumulative dependencies phải được tôn trọng. |
| “Daily job khỏe thì backfill không ảnh hưởng.” | Chia sẻ DB/CPU/API pool có thể gây miss SLA. |
| “Count bằng nhau là dữ liệu đúng.” | Cần so business keyset, versions, hashes, totals. |
| “Job COMPLETED nghĩa đã publish.” | Validation và publication là bước riêng. |
| “Kubernetes Forbid chặn mọi backfill khác.” | Chỉ cùng CronJob resource; cần global work dedupe. |

## 23. Checklist trước production

- [ ] Ngày nghiệp vụ, zone/cutover và business calendar được định nghĩa/versioned.
- [ ] Backfill range dùng `[fromInclusive,toExclusive)` nhất quán.
- [ ] Các ngày được quét thiếu qua ledger, không chỉ tin cron fire history.
- [ ] Dữ liệu source theo ngày có snapshot/version/checksum bất biến.
- [ ] Watermark/allowed lateness và late correction policy rõ ràng.
- [ ] Backfill plan và từng daily item được lưu bền vững.
- [ ] Identifying JobParameters phản ánh date/snapshot/pipeline/zone.
- [ ] Non-identifying audit fields không làm đổi input/output.
- [ ] Đồng thời nhiều schedulers dùng atomic claim + global logical work key.
- [ ] Lease TTL/heartbeat/fencing có quy trình khi worker còn STARTED.
- [ ] Planner tra JobRepository sau crash giữa launch và persist execution ID.
- [ ] Restart FAILED/STOPPED cùng JobInstance; không đổi run.id mù.
- [ ] Correction COMPLETED dùng revision riêng và publish có kiểm soát.
- [ ] Reader `@StepScope` có deterministic order và ItemStream checkpoint.
- [ ] Writer dùng đúng transaction manager và idempotent business keys.
- [ ] Payload conflict cùng key/version được phát hiện, không chỉ DO NOTHING.
- [ ] Partition plan/worker names ổn định khi restart.
- [ ] DAG dependencies xuyên ngày được enforce, không chỉ max concurrency.
- [ ] Daily SLA được reserve connections/threads/API quotas trước backfill.
- [ ] Hikari pools tính tổng qua mọi pods, kể cả rolling update surge.
- [ ] Retry budgets, backoff, timeouts và admission control có giới hạn.
- [ ] JobRepository metadata và business output được đối soát khi tách DB.
- [ ] Quality gate kiểm tra missing/extra keys, versions, hashes và totals.
- [ ] Publication pointer chỉ đổi khi revision đã validate; có audit/rollback.
- [ ] Fault tests bao gồm scheduler outage, duplicate launch, source drift và commit/reply crash.
- [ ] Runbook hỗ trợ manual hold, repair, reprocess và SLA miss reporting.

## 24. Câu hỏi tự kiểm tra

1. Backfill theo ngày khác restart cùng JobInstance như thế nào?
2. Vì sao ngày trong ZoneId có thể không dài đúng 24 giờ?
3. Điều kiện SQL nào tránh trùng record tại ranh giới hai ngày?
4. `event_time` khác `ingested_at`; late events nên xếp vào ngày nào?
5. Watermark và freeze cutoff đóng vai trò gì?
6. Vì sao `WHERE ingested_at <= cutoff` chưa chắc tạo immutable snapshot?
7. Những trường nào nên identifying trong `JobParameters` cho backfill?
8. Vì sao `run.id` ngẫu nhiên có thể phá restart semantics?
9. Nếu hai Spring `@Scheduled` chạy trên hai pods, chặn enqueue trùng thế nào?
10. Vì sao pre-check `findRunningJobExecutions` chưa đủ làm lock?
11. Crash sau `JobLauncher.run` nhưng trước khi planner lưu execution ID cần xử lý sao?
12. Lease hết hạn có đảm bảo worker cũ đã dừng không?
13. Hai plans khác nhau cùng ngày có thể cùng claim không nếu key là `(planId,date)`?
14. `gridSize` có luôn là số active worker threads không?
15. Vì sao `@StepScope` reader quan trọng khi partitioning?
16. Nếu business commit nhưng JobRepository checkpoint cũ, restart có nguy cơ gì?
17. Nếu checkpoint tiến còn business output chưa commit, upsert idempotent có tự sửa không?
18. Vì sao writer `total=total+amount` nguy hiểm khi replay?
19. `ON CONFLICT DO NOTHING` có chứng minh payload hash giống nhau không?
20. Tại sao ngày 21 tính cumulative balance không nên chạy trước ngày 20?
21. Late correction ngày 20 có thể ảnh hưởng ngày 21–23 bằng cách nào?
22. Khi một ngày đã COMPLETED nhưng cần tính lại, cần đổi những gì?
23. Làm sao ngăn backfill dùng hết JDBC connections của daily job?
24. `BatchStatus.COMPLETED` có đồng nghĩa output đã được publish không?
25. Những kiểm chứng nào quan trọng hơn việc count output bằng expected?
26. Nếu backlog 7.200.000 records, 4 giờ xử lý, cần throughput trung bình bao nhiêu?
27. Một worker đạt 110 items/s khi chạy đơn lẻ: vì sao không thể tự nhân số đó với 16 workers?
28. Scheduler outage qua một ngày cron có thể được phát hiện bằng cơ chế nào?
29. Lý do phải dùng generation guard khi hai revisions cố publish cùng một ngày?
30. Khi restart backfill một ngày, điều gì tuyệt đối không được mutate?

**Gợi ý:** (1) Backfill lên kế hoạch kỳ lịch sử; restart tiếp tục JobInstance chưa hoàn tất. (2) DST/cutover. (3) `>= start AND < end`. (4) Event time theo business contract. (5) Readiness và snapshot version. (6) Source rows vẫn có thể UPDATE/DELETE. (7) Date, snapshot, pipeline, zone và mọi input-affecting params. (8) Tạo instance mới. (9) Atomic dedupe/lease. (10) Race giữa check và launch. (11) Lookup repository bằng identifying params. (12) Không. (13) Có. (14) Không. (15) Context/checkpoint theo worker. (16) Replay, cần idempotency. (17) Không, cần reconciliation. (18) Cộng trùng. (19) Không. (20) Phụ thuộc số dư ngày 20. (21) Derived outputs bị stale. (22) Source/output revision mới, JobInstance/validation/publish contract. (23) Shared admission, quota và connection budgets. (24) Không. (25) Keyset/hash/version/amount invariants. (26) 500 committed items/s. (27) Contention, skew, quotas. (28) Periodic catch-up reconciler. (29) Ngăn lost update/double publish. (30) Frozen snapshot, partition plan, identifying parameters.

## Tài liệu tham khảo

- [Spring Batch 5.2 — Configuring a Job](https://docs.spring.io/spring-batch/reference/5.2/job/configuring.html): restartability và JobInstance/JobExecution semantics.
- [Spring Batch 5.2 — Job Parameters](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html): metadata/identifying parameters và JobOperator.
- [Spring Batch 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): `ExecutionContext`, `ItemStream`.
- [Spring Batch 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): partitioning, `gridSize`, TaskExecutor/remote work.
- [Spring Batch 5.2 — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): repository transaction/metadata, isolation khi tạo instance.
- [Spring Batch 5.2 API — JobParametersBuilder](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParametersBuilder.html): identifying và non-identifying parameters.
- [Spring Batch 5.2 API — JobOperator](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/launch/JobOperator.html): `restart(long executionId)`.
- [Spring Batch 5.2 API — JdbcCursorItemReaderBuilder](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/database/builder/JdbcCursorItemReaderBuilder.html): `saveState`, `preparedStatementSetter`.
- [Spring Framework 6.2 — @Scheduled API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html): six-field cron và zone.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): scheduler/cron.
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): timeZone, concurrencyPolicy, missed schedules.
- [Quartz — JobStore and Clustering](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/configuration/ConfigJobStoreTX.html): JDBC scheduler storage.
- [PostgreSQL — SELECT/Locking](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE SKIP LOCKED` và cạnh tranh claim.

**Điểm cốt lõi:** Backfill dữ liệu theo ngày phải là **một workflow có trạng thái bền**, không chỉ một vòng lặp cron. Mỗi ngày cần **business window chính xác, immutable snapshot và identifying JobParameters cố định**; các ngày được scheduler claim theo resource budget và dependency, các worker ghi **versioned idempotent output**, JobRepository hỗ trợ restart những phần failed, và **reconciliation/publish pointer** quyết định khi nào dữ liệu mới được công bố. Scale chỉ có giá trị khi giữ đúng dữ liệu, không tranh SLA daily job và phục hồi an toàn qua scheduler/worker/DB crashes.
