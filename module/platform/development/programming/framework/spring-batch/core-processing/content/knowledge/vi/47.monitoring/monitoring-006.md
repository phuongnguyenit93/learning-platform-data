# Theo dõi job duration trong Spring Batch

## 1. Job duration là gì và vì sao phải theo dõi?

Trong hệ thống xử lý batch, **job duration** là thời gian một lần thực thi job thực sự chạy, thường được tính từ lúc **JobExecution.startTime** đến **JobExecution.endTime**. Chỉ số này giúp trả lời các câu hỏi vận hành:

- Job nhập đơn hàng chạy mất bao lâu trong mỗi kỳ?
- Job có bắt đầu chậm hơn lịch dự kiến hay không?
- Thời gian hoàn thành tăng vì số lượng dữ liệu lớn hơn, vì một Step chậm hay vì dịch vụ ngoài bị timeout?
- Job còn đang chạy có nguy cơ vượt thời hạn hoàn thành (SLA/SLO) không?
- Sau khi tối ưu chunk size, truy vấn hoặc số worker, thời gian xử lý có thực sự cải thiện?

Ví dụ một job được lên lịch lúc 01:00, bắt đầu chạy lúc 01:04 và hoàn thành lúc 01:19:

~~~text
01:00          01:04                          01:19
  |              |                              |
  v              v                              v
Scheduled     STARTED                       COMPLETED
  |-- 4 phút --|----------- 15 phút -----------|
    Trễ khởi    Job duration = 15 phút
    chạy

Thời gian từ lịch dự kiến đến hoàn tất = 19 phút
~~~

**Job duration = 15 phút** trong ví dụ này; **độ trễ khởi chạy = 4 phút** là chỉ số riêng. Nếu chỉ đo một trong hai, hệ thống có thể bỏ sót nguyên nhân khiến output đến downstream muộn.

Trong Spring Batch, phải phân biệt **JobInstance** (công việc logic, được định danh bằng tên job và identifying job parameters) với **JobExecution** (một lần chạy cụ thể của JobInstance). Khi job thất bại rồi restart, có thể có nhiều JobExecution thuộc cùng một JobInstance. Duration của mỗi execution khác với tổng thời gian xử lý đến khi công việc logic hoàn tất.

## 2. Các loại thời gian cần phân biệt

| Chỉ số | Điểm bắt đầu | Điểm kết thúc | Công dụng |
|---|---|---|---|
| **Job execution duration** | JobExecution.startTime | JobExecution.endTime | Đo thời gian một lần chạy đã kết thúc |
| **Running elapsed time** | startTime của execution đang chạy | Thời điểm quan sát hiện tại | Phát hiện job chạy lâu bất thường |
| **Step duration** | StepExecution.startTime | StepExecution.endTime | Khoanh vùng Step gây chậm |
| **Start delay** | Thời điểm dự kiến/sự kiện trigger | startTime | Phát hiện scheduler, hàng đợi hoặc tài nguyên khởi động chậm |
| **Queue/infrastructure delay** | Thời điểm tạo yêu cầu/JobExecution | startTime, tùy cơ chế launch | Quan sát thời gian chờ cấp quyền/chạy |
| **End-to-end latency** | Thời điểm dữ liệu cần được xử lý | Thời điểm output READY | Đánh giá hạn giao dữ liệu thực tế |
| **Total elapsed across restarts** | Execution đầu tiên bắt đầu | Execution cuối hoàn tất | Gồm cả khoảng dừng/chờ giữa các attempt |
| **Active processing time across attempts** | Tổng các khoảng start→end của từng execution | Tổng cộng theo JobInstance | Ước lượng tổng thời gian thực sự chạy, khác elapsed toàn bộ |

**Không dùng một tên “duration” cho tất cả các đại lượng trên.** Ví dụ job dừng hai giờ để chờ upstream sửa dữ liệu rồi restart: tổng wall-clock đến khi có output hoàn chỉnh có thể rất lớn, trong khi từng execution chỉ chạy vài phút.

Duration cũng khác **throughput**. Một job xử lý 100.000 item trong 10 phút và một job xử lý 1.000.000 item trong 12 phút có duration gần nhau nhưng năng suất hoàn toàn khác. Nên đi cùng các metric về item và byte đã xử lý.

### Trạng thái ảnh hưởng đến ý nghĩa duration

| BatchStatus | Cách đọc chỉ số thời gian |
|---|---|
| COMPLETED | Duration là thời gian một lần xử lý hoàn tất theo flow của job; vẫn cần đối soát chất lượng output riêng |
| FAILED | Duration là thời gian đến lúc thất bại, không phải thời gian để xử lý xong toàn bộ dữ liệu |
| STOPPED | Duration của lần chạy đã dừng có kiểm soát; output có thể chưa đủ |
| STARTED / STARTING / STOPPING | Chưa có duration kết thúc; chỉ tính elapsed tạm thời |
| UNKNOWN / ABANDONED | Cần đánh giá metadata và quy trình vận hành trước khi suy luận kết quả |

Khi tính thống kê **p95 duration của các job thành công**, phải lọc riêng status **COMPLETED**. Duration của FAILED ngắn vì chết ngay ở đầu không được đưa vào để làm đẹp số đo latency thành công; đồng thời phải có biểu đồ thất bại riêng.

## 3. JobRepository ghi nhận thời gian thế nào?

Spring Batch lưu metadata execution trong **JobRepository** và cung cấp API để đọc lại qua **JobExplorer**. Với các phiên bản hiện đại, JobExecution và StepExecution có thời điểm bắt đầu/kết thúc; khi job đang chạy hoặc metadata bị gián đoạn, giá trị endTime có thể chưa có.

Các bảng metadata thường gặp:

~~~text
BATCH_JOB_INSTANCE
    JOB_INSTANCE_ID
    JOB_NAME
       |
       v
BATCH_JOB_EXECUTION
    JOB_EXECUTION_ID
    JOB_INSTANCE_ID
    CREATE_TIME
    START_TIME
    END_TIME
    STATUS
       |
       v
BATCH_STEP_EXECUTION
    STEP_EXECUTION_ID
    JOB_EXECUTION_ID
    STEP_NAME
    START_TIME
    END_TIME
    READ_COUNT / WRITE_COUNT / ...
~~~

**CREATE_TIME** cho biết JobExecution được tạo trong repository; nó không tự động là thời điểm lịch chạy dự kiến. **START_TIME** là mốc chính để đo execution duration. **END_TIME** chỉ có ý nghĩa khi execution đã thực sự kết thúc và metadata được cập nhật.

Nếu ứng dụng bị kill, mất kết nối repository hoặc host crash, database có thể còn status **STARTED** và END_TIME rỗng. Không nên tự coi những execution như vậy là “job vô hạn”; cần kết hợp heartbeat/worker liveness và runbook recovery.

### Đọc duration của một JobExecution bằng Java

Ví dụ Spring Batch 5+ dùng kiểu thời gian **LocalDateTime**:

~~~java
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.springframework.batch.core.JobExecution;

public final class BatchDurationCalculator {

    private BatchDurationCalculator() {
    }

    public static Optional<Duration> completedExecutionDuration(
            JobExecution execution) {

        LocalDateTime started = execution.getStartTime();
        LocalDateTime ended = execution.getEndTime();

        if (started == null || ended == null) {
            return Optional.empty();
        }
        return Optional.of(Duration.between(started, ended));
    }
}
~~~

Ví dụ sử dụng:

~~~java
Optional<Duration> duration =
        BatchDurationCalculator.completedExecutionDuration(execution);

duration.ifPresent(value ->
        System.out.println("durationSeconds=" + value.toMillis() / 1000.0));
~~~

Trong Spring Batch cũ hơn, API timestamp có thể dùng kiểu \`Date\`, nên phải điều chỉnh phần chuyển đổi theo phiên bản dự án. Khi thiết kế môi trường triển khai, cần thống nhất quy tắc timezone và đồng bộ đồng hồ của các máy; timestamp dạng LocalDateTime không chứa múi giờ để diễn giải độc lập với môi trường.

Phép tính trên dành cho **execution đã có start/end hợp lệ**. Đối với execution vẫn đang chạy, không thay endTime bằng thời điểm hiện tại rồi lưu như duration đã hoàn tất; hãy đưa nó vào metric **running elapsed seconds** riêng.

## 4. Đo elapsed time của job đang chạy

Đối với một execution đang chạy:

\[
\text{runningElapsed}(t) = t - \text{startTime}
\]

Ví dụ một job bắt đầu lúc 02:00 và đến 02:17 vẫn STARTED: **elapsed = 17 phút**, chưa có final duration.

Ứng dụng giám sát có thể đọc execution qua JobExplorer:

~~~java
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public class RunningJobInspector {

    private final JobExplorer jobExplorer;

    public RunningJobInspector(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public Optional<Duration> elapsed(long executionId) {
        JobExecution execution = jobExplorer.getJobExecution(executionId);
        if (execution == null || execution.getStartTime() == null) {
            return Optional.empty();
        }
        BatchStatus status = execution.getStatus();
        if (status != BatchStatus.STARTED
                && status != BatchStatus.STARTING
                && status != BatchStatus.STOPPING) {
            return Optional.empty();
        }
        return Optional.of(Duration.between(
                execution.getStartTime(), LocalDateTime.now()));
    }
}
~~~

Mã trên minh họa phép đo từ metadata. Trong hệ thống đa node, clock skew có thể làm elapsed âm hoặc sai; nên đồng bộ NTP, thống nhất timezone và không xem thời gian tính từ một bản ghi STARTED cũ là bằng chứng process còn sống.

Nếu cần đo khoảng thời gian **trong cùng một process đang chạy** với độ chính xác cao, đồng hồ đơn điệu như \`System.nanoTime()\` phù hợp hơn vì tránh thay đổi đồng hồ hệ thống. Nhưng kết quả này chỉ còn trong RAM; metadata repository vẫn là nguồn lịch sử cho các execution đã hoàn tất.

### Phát hiện job “treo” cần nhiều tín hiệu

Job duration kéo dài không nhất thiết là job treo. Một Step có thể hợp lệ khi đang xử lý tập dữ liệu lớn. Để phân biệt, theo dõi thêm:

- Thời điểm **last progress**: lần cuối readCount/writeCount tăng hoặc chunk commit.
- Trạng thái thread/process, heartbeat của worker và tình trạng JobRepository.
- Thời gian chờ DB lock, API latency, retry và backoff.
- Input volume của execution so với lịch sử.
- Số record còn chờ, nếu có cách đo đáng tin cậy.

Chẳng hạn một job chạy 30 phút nhưng readCount tăng đều có thể vẫn khỏe, trong khi job chỉ chạy 5 phút nhưng không có progress, thread đang chờ mạng không timeout, có nguy cơ cần can thiệp.

## 5. Truy vấn lịch sử duration từ các bảng Spring Batch

Khi muốn phân tích nhiều lần chạy, có thể đọc metadata qua JobExplorer hoặc SQL reporting read-only. Ví dụ sau dùng cú pháp **PostgreSQL** và giả định sử dụng schema metadata mặc định của Spring Batch.

~~~sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME,
    EXTRACT(EPOCH FROM (je.END_TIME - je.START_TIME))
        AS duration_seconds
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.START_TIME IS NOT NULL
  AND je.END_TIME IS NOT NULL
  AND je.END_TIME >= :fromTime
ORDER BY je.END_TIME DESC;
~~~

Kết quả có thể giống:

| JOB_NAME | EXECUTION_ID | STATUS | Duration (s) |
|---|---:|---|---:|
| importOrdersJob | 1001 | COMPLETED | 380 |
| importOrdersJob | 1002 | COMPLETED | 420 |
| importOrdersJob | 1003 | FAILED | 45 |
| importOrdersJob | 1004 | COMPLETED | 610 |

Nếu tính thời gian thực hiện thành công trên tập trên, dùng **380, 420, 610 giây**. Execution FAILED ở 45 giây phải được phân tích như lỗi, không đưa vào cùng phân phối hoàn tất nếu metric định nghĩa là successful job duration.

Truy vấn riêng thời gian của từng Step:

~~~sql
SELECT
    se.JOB_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.START_TIME,
    se.END_TIME,
    EXTRACT(EPOCH FROM (se.END_TIME - se.START_TIME))
        AS step_duration_seconds
FROM BATCH_STEP_EXECUTION se
WHERE se.JOB_EXECUTION_ID = :executionId
  AND se.START_TIME IS NOT NULL
  AND se.END_TIME IS NOT NULL
ORDER BY se.START_TIME, se.STEP_EXECUTION_ID;
~~~

Khi job có Step chạy song song, **không cộng tất cả Step duration rồi gọi tổng đó là job duration**. Nếu hai Step mỗi Step chạy 10 phút nhưng chồng lấn hoàn toàn, tổng Step durations là 20 phút còn thời gian wall-clock của job có thể khoảng 10 phút.

### Truy vấn execution đang chạy quá ngưỡng

~~~sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - je.START_TIME))
        AS elapsed_seconds
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.STATUS IN ('STARTING', 'STARTED', 'STOPPING')
  AND je.START_TIME IS NOT NULL
  AND je.START_TIME < CURRENT_TIMESTAMP - INTERVAL '30 minutes'
ORDER BY elapsed_seconds DESC;
~~~

Đây là **danh sách ứng viên cần điều tra**, không phải khẳng định tất cả đều đang chạy thật. Nếu metadata bị bỏ lại sau crash, cần đối chiếu với process/worker heartbeat.

Với Oracle, SQL Server, MySQL hoặc database khác, phải đổi phần tính chênh lệch thời gian theo dialect. Không nên chạy câu query lịch sử không có giới hạn thời gian hoặc không có chỉ mục phù hợp trên bảng metadata lớn; các bảng JobRepository phục vụ vận hành job, vì vậy workload báo cáo cần được kiểm soát.

## 6. Đo bằng Micrometer và Spring Boot Actuator

Nếu ứng dụng dùng Spring Boot, **Micrometer** và **Actuator** là nền tảng phổ biến để công bố metrics tới Prometheus, OpenTelemetry collector hoặc backend quan sát tương ứng. Spring Batch cũng có instrumentation tích hợp trong nhiều phiên bản; tên meter và tag có thể khác giữa phiên bản Spring Batch, Spring Boot, Micrometer và cách cấu hình.

Vì thế, trước khi tạo metric tùy chỉnh, hãy:

1. Xác định ứng dụng đã bật metric Spring Batch hay chưa.
2. Kiểm tra các meter thực tế qua Actuator hoặc MeterRegistry trong runtime.
3. Xem metric đã có timer cho Job và Step, kèm các tag như job name, step name, status hay chưa.
4. Chỉ thêm metric mới khi cần một định nghĩa duration hoặc tập tag không được đáp ứng.

Không giả định một tên Prometheus cụ thể sẽ xuất hiện chỉ vì thêm Spring Batch vào classpath.

### Cấu hình Actuator và endpoint Prometheus

Ví dụ Gradle cho ứng dụng Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Ví dụ \`application.yml\`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        application.batch.job.duration: true
~~~

Cấu hình \`percentiles-histogram\` ở đây dành cho **timer tùy chỉnh có tên application.batch.job.duration** trong phần sau, và chỉ cần thiết nếu muốn truy vấn histogram/quantile theo cách tương ứng. Số lượng bucket và chi phí lưu trữ cần được kiểm soát trên môi trường production.

Các endpoint \`/actuator/metrics\` và \`/actuator/prometheus\` cần cấu hình bảo mật và phạm vi truy cập; không nên công khai metric chứa tên hệ thống nội bộ và thông tin vận hành cho internet.

### Micrometer Timer đo gì?

**Timer** ghi nhận nhiều lần đo duration, thường cung cấp **count**, **total time** và **max** tùy registry; histogram/percentile có thể được xuất khi được cấu hình. Timer phù hợp với duration của **những execution đã kết thúc**.

Một timer không tự cho biết hiện có bao nhiêu job STARTED hoặc một job cụ thể đã chạy bao lâu. Với công việc đang chạy, phải dùng metric riêng, chẳng hạn active execution count hoặc elapsed gauge được cập nhật bằng nguồn giám sát phù hợp.

## 7. Tạo custom Timer qua JobExecutionListener

Khi cần metric theo quy ước ứng dụng, có thể ghi một lần đo khi job kết thúc. Ví dụ sau dùng **Micrometer Timer.Sample**, lưu sample theo JobExecutionId để hỗ trợ nhiều lần chạy đồng thời trong một JVM.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class JobDurationMetricsListener implements JobExecutionListener {

    private final MeterRegistry meterRegistry;
    private final ConcurrentMap<Long, Timer.Sample> runningSamples =
            new ConcurrentHashMap<>();

    public JobDurationMetricsListener(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void beforeJob(JobExecution jobExecution) {
        Long executionId = jobExecution.getId();
        if (executionId != null) {
            runningSamples.put(executionId, Timer.start(meterRegistry));
        }
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        Long executionId = jobExecution.getId();
        if (executionId == null) {
            return;
        }

        Timer.Sample sample = runningSamples.remove(executionId);
        if (sample == null) {
            return;
        }

        sample.stop(Timer.builder("application.batch.job.duration")
                .description("Elapsed time of an in-process job execution")
                .tag("job", jobExecution.getJobInstance().getJobName())
                .tag("status", jobExecution.getStatus().name())
                .register(meterRegistry));
    }
}
~~~

Đăng ký listener khi xây dựng Job:

~~~java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        JobDurationMetricsListener durationListener) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .listener(durationListener)
            .build();
}
~~~

Ví dụ dùng phong cách builder Spring Batch 5+ và giả định bean **importOrdersStep** đã có. Nếu có nhiều Job cần theo dõi, gắn listener vào từng Job hoặc dùng cấu hình đăng ký instrumentation phù hợp.

**Phạm vi phép đo:** mẫu Timer sử dụng đồng hồ đơn điệu kể từ callback **beforeJob** đến **afterJob** trong **cùng tiến trình**. Nó bao gồm phần thực thi trong các callback và các Step theo luồng job, nhưng có thể không trùng tuyệt đối với \`endTime - startTime\` được repository ghi vì thời điểm gọi listener khác thời điểm cập nhật metadata.

Giới hạn cần biết:

- Nếu tiến trình bị kill hoặc crash, **afterJob không chạy**, sample còn trong RAM bị mất và sẽ không có một quan sát duration hoàn chỉnh cho execution đó.
- Nếu một execution chạy trên JVM khác, map của listener cũ không thể chứa sample cho JVM mới. Restart của job tạo JobExecution khác và có sample mới.
- Không thêm **executionId**, **batchId**, **customerId**, filename hay timestamp làm label của metric; các giá trị này tạo **high cardinality**, tăng memory và chi phí lưu trữ.
- Các tag ít biến thiên như **job** và **status** phù hợp hơn cho tổng hợp; hãy kiểm soát số lượng job name được tạo động.
- Nếu instrumentation có sẵn đã xuất cùng loại timer, không nên thêm custom metric có ý nghĩa trùng nhưng tên khác làm dashboard đếm hai lần.

Khi cần một nguồn tính duration lịch sử chống lại việc tiến trình crash, vẫn phải dựa trên **JobRepository** hoặc hệ thống audit bền vững có cùng ngữ nghĩa; timer trong RAM không thay thế metadata.

## 8. Thiết kế metric và nhãn cho monitoring

Một bộ chỉ số thực tế nên kết hợp thời gian, kết quả thực thi và tiến độ:

| Metric khái niệm | Loại | Nhãn nên dùng | Mục tiêu |
|---|---|---|---|
| job duration | Timer/histogram | job, status | Phân phối thời gian các execution kết thúc |
| step duration | Timer/histogram | job, step, status | Xác định Step chậm |
| job executions total | Counter | job, status | Tần suất hoàn tất/thất bại/dừng |
| running jobs | Gauge | job hoặc job group | Số job đang hoạt động |
| running elapsed | Gauge hoặc truy vấn từ metadata | job; execution ID trong log/traces | Cảnh báo job đang chạy lâu |
| processed items | Counter | job, step, outcome | Throughput và tiến độ |
| skip/retry/rollback | Counter | job, step, reason nhóm | Chẩn đoán tình huống xử lý chậm |
| last successful completion | Gauge timestamp | job | Phát hiện kỳ batch chưa có output đúng hạn |
| input volume | Histogram/Gauge theo execution | job | Giải thích duration tăng khi dữ liệu tăng |

Đối với **running elapsed của từng execution**, đôi khi cần dashboard bảng riêng truy vấn JobRepository hoặc service giám sát thay vì nhồi executionId thành nhãn Prometheus. Nếu dùng Gauge chia theo executionId sẽ tạo nhiều time series liên tục; phải có chính sách tạo/xóa và tính đến job ngắn.

Trong log có cấu trúc, ngược lại, **executionId và batchId rất hữu ích** vì log/traces được thiết kế để truy vết các lần chạy cụ thể:

~~~text
event=JOB_FINISHED
jobName=importOrdersJob
jobExecutionId=2048
batchId=B20261116
status=COMPLETED
durationMs=428350
readCount=100000
writeCount=99320
filterCount=600
skipCount=80
~~~

Đây là ví dụ log, không phải số liệu thực tế. Nếu tổng read/write không trùng, trước tiên cần xem logic filter, skip và biến đổi output; không gắn nhãn “lỗi dữ liệu” chỉ từ chênh lệch counter.

## 9. Dashboard duration: trung bình chưa đủ

Giả sử có 10 execution COMPLETED với thời gian:

~~~text
8, 9, 9, 10, 10, 10, 11, 12, 13, 45 phút
~~~

Giá trị trung bình là **13,7 phút**, nhưng chín lần đầu chỉ nằm quanh 8–13 phút. Execution 45 phút là một trường hợp bất thường cần điều tra. Nếu chỉ hiển thị trung bình, biểu đồ có thể che khuất đuôi chậm.

Dashboard nên thể hiện:

1. **p50, p95, p99 duration** đối với những job đủ số lượng execution để percentile có ý nghĩa.
2. **Max duration** và danh sách các lần chạy chậm nhất, có thể drill-down bằng executionId trong log/traces.
3. **Số execution theo status**: COMPLETED, FAILED, STOPPED.
4. **Thời gian Step** để nhìn ra nơi tăng latency.
5. **Input volume và throughput** tương ứng cùng kỳ.
6. **Elapsed của job đang chạy** cùng thời hạn hoàn tất.
7. **Time since last successful completion** cho các job theo lịch.

Với job chỉ chạy một lần mỗi ngày, p99 của vài ngày dữ liệu không đáng tin như một thước đo thống kê ổn định. Trong trường hợp đó, so sánh từng execution với baseline theo thứ/ngày, volume và giới hạn lịch kinh doanh có thể hữu ích hơn.

### Ví dụ cấu trúc dashboard

~~~text
Batch processing / Import orders

Last run:
  status                 COMPLETED
  execution duration     12m 35s
  input records          150,000
  throughput             198 items/s
  completed at           02:18 local time

24-hour history:
  successful executions  12
  failed executions       1
  p50 duration          11m
  p95 duration          17m
  slowest step          enrichCustomer

Running executions:
  executionId 2081       STARTED  elapsed 8m

SLO:
  99% daily outputs READY before 03:00
~~~

Mỗi chỉ số trên cần có nguồn và định nghĩa rõ. Ví dụ **throughput = item đã ghi / duration** có thể không phản ánh công sức lọc/skip của processor; đôi khi dùng **readCount / duration** để đo tốc độ input, đồng thời báo write throughput riêng.

## 10. Ví dụ Prometheus/PromQL

Giả sử **custom Timer** ở mục 7 được export sang Prometheus và histogram đã được bật. Tên metric theo convention chuyển đổi thường xuất hiện như:

~~~text
application_batch_job_duration_seconds_count
application_batch_job_duration_seconds_sum
application_batch_job_duration_seconds_bucket
~~~

Đây là **tên minh họa cần kiểm tra trên endpoint Prometheus thực tế**; việc xuất bucket phụ thuộc registry/distribution config. Nếu dự án dùng metric có sẵn từ Spring Batch, phải thay tên metric bằng tên thực được export.

### 10.1. Duration trung bình của job thành công trong 24 giờ

~~~promql
sum by (job) (
  increase(application_batch_job_duration_seconds_sum{
    status="COMPLETED"
  }[24h])
)
/
sum by (job) (
  increase(application_batch_job_duration_seconds_count{
    status="COMPLETED"
  }[24h])
)
~~~

Đơn vị của kết quả là **giây**. Dashboard cần xử lý mẫu số bằng 0 khi không có job hoàn tất trong cửa sổ quan sát; tránh hiển thị một con số giả định.

### 10.2. p95 duration từ histogram

~~~promql
histogram_quantile(
  0.95,
  sum by (le, job) (
    rate(application_batch_job_duration_seconds_bucket{
      status="COMPLETED"
    }[7d])
  )
)
~~~

Ví dụ dùng cửa sổ bảy ngày để thu đủ execution cho job chạy thưa. Công thức áp dụng cho **classic histogram** có nhãn **le**; nếu backend dùng native histogram hay loại distribution khác, cú pháp phải thay đổi.

### 10.3. Đếm số lần job FAILED trong 24 giờ

~~~promql
sum by (job) (
  increase(application_batch_job_duration_seconds_count{
    status="FAILED"
  }[24h])
)
~~~

Metric này chỉ đếm các lần execution FAILED đã đi qua listener và được ghi Timer. **Không thấy FAILED không có nghĩa không có crash**, bởi tiến trình chết có thể không chạy afterJob. Cần bổ sung kiểm tra metadata/heartbeat hoặc event giám sát từ scheduler.

### Phân biệt quantile của histogram và trung bình

Histogram phục vụ phân phối thời gian khi các khoảng đo đã hoàn tất; **p95 không thể được suy ra từ trung bình**. Đối với job thời gian dài nhưng ít lần chạy, cần thiết kế bucket phù hợp (ví dụ nhiều phút hoặc hàng giờ) để histogram không quá thô.

## 11. Alert dựa trên duration và deadline

Có thể định nghĩa hai nhóm cảnh báo:

**Cảnh báo job chạy lâu:** một execution vẫn đang STARTED và elapsed vượt ngưỡng dành cho job đó. Mục tiêu là phát hiện nguy cơ timeout, deadlock, API chậm hoặc input volume bất thường.

**Cảnh báo output trễ deadline:** đến mốc kinh doanh bắt buộc mà chưa có một bản output READY, dù job đã FAILED, STOPPED, chưa được scheduler chạy hay chạy xong nhưng đối soát dữ liệu không đạt.

Ví dụ:

| Job | Ngưỡng duration tham khảo | Deadline nghiệp vụ | Hành động khi vượt |
|---|---|---|---|
| importOrdersJob | 20 phút trong điều kiện volume chuẩn | READY trước 03:00 | Xem step chậm, số record và API latency |
| billingSettlementJob | 60 phút | READY trước 06:00 | Escalate vì ảnh hưởng dữ liệu thanh toán |
| nightlyExportJob | 90 phút | File/manifest READY trước 07:00 | Kiểm tra writer, storage và publish |

Các ngưỡng chỉ là ví dụ. Thực tế nên đặt theo lịch chạy, volume, baseline từng loại ngày, số lượng partition và thời gian cần dự phòng để khắc phục trước deadline.

### Cảnh báo động theo dữ liệu đầu vào

Một job xử lý 5 triệu dòng có thể hợp lệ khi chạy lâu gấp nhiều lần job xử lý 50 nghìn dòng. Có thể xây baseline kiểu:

\[
T_{\text{expected}} = T_{\text{setup}} +
\frac{N_{\text{items}}}{R_{\text{expected}}}
\]

Trong đó:

- \(T_{\text{setup}}\): thời gian cố định để khởi tạo kết nối/Step.
- \(N_{\text{items}}\): số item đầu vào thực tế hoặc dự kiến.
- \(R_{\text{expected}}\): tốc độ xử lý dự kiến (items/giây).

Ví dụ setup 30 giây, 120.000 item, throughput dự kiến 200 items/giây:

\[
T_{\text{expected}} = 30 + \frac{120000}{200}
= 630 \text{ giây} = 10{,}5 \text{ phút}
\]

Nếu execution kéo dài 25 phút với cùng volume, đó là tín hiệu cần điều tra. Nhưng công thức chỉ là mô hình tham khảo: chi phí transform không đồng đều, partition contention, API rate limit và skip/retry có thể làm tốc độ phi tuyến.

### Tránh alert noise

Không cảnh báo mỗi lần duration tăng nhẹ so với trung bình. Có thể đặt ngưỡng theo baseline lịch sử, điều kiện volume và duration tuyệt đối, cùng khoảng xác nhận để không tạo hàng loạt thông báo khi một job đã được xử lý.

Với job chỉ chạy một lần/ngày, cảnh báo **không có lần COMPLETED mới trước deadline** thường quan trọng hơn cảnh báo p95. Đối với job chạy liên tục nhiều lần/giờ, p95/p99 và tỷ lệ thất bại có thể phản ánh xu hướng rõ hơn.

## 12. Truy tìm nguyên nhân khi duration tăng

Một job chậm không đủ để kết luận chính Step nào gây vấn đề. Quy trình điều tra:

~~~text
Job duration tăng
        |
        v
Input volume có tăng tương ứng không?
   | Có                          | Không/không đủ giải thích
   v                              v
So throughput                   Xem Step duration
   |                              |
   v                              v
Throughput ổn?                  Step nào tăng mạnh?
   |                              |
   v                              v
Nếu ổn: dự kiến lâu hơn          DB / API / Writer / CPU
Nếu giảm: chẩn đoán sâu          lock / retry / GC / I/O
~~~

Có thể chia việc phân tích theo các lớp:

| Lớp | Tín hiệu chẩn đoán |
|---|---|
| Reader | Query chậm, paging, lock, kích thước file, network storage |
| Processor | CPU, GC, transform nặng, cache hit, lời gọi API |
| Writer | Batch insert, commit latency, row lock, unique constraint, flush |
| Transaction | Rollback, retry, deadlock và transaction timeout |
| Hạ tầng | CPU throttling, memory pressure, disk/network I/O |
| Điều phối | Job chạy cạnh tranh, thread pool, partition imbalance |
| Downstream | HTTP 429/503, rate limit, queue backlog |

Nếu job gồm nhiều Step, truy vấn Step duration là điểm bắt đầu. Nếu Step xử lý chunk chứa cả reader, processor và writer, cần instrument thêm **chunk duration**, thời gian DB và API để biết chính pha nào tiêu tốn thời gian.

### Không đánh đồng số lần retry với throughput

Một item có thể được xử lý nhiều lần do retry hoặc rollback; đọc/ghi cuối cùng không luôn phản ánh toàn bộ số lời gọi tới API. Khi duration tăng, kết hợp:

- \`readCount\`, \`writeCount\`, \`filterCount\`, \`readSkipCount\`, \`processSkipCount\`, \`writeSkipCount\`.
- \`rollbackCount\`, exception histogram và retry attempt từ lớp ứng dụng.
- Số request, latency và error rate của external service.
- Duration của chunk, DB transaction và API request.

Không tăng số worker ngay khi job chậm nếu bottleneck nằm ở database lock hoặc API rate limit: thêm song song có thể làm job chậm hơn.

## 13. Theo dõi duration trong job nhiều Step và partition

Ví dụ job có các Step:

~~~text
importOrdersJob
  |
  +-- loadStaging          3 phút
  |
  +-- enrichRisk           8 phút
  |
  +-- writeOutput          4 phút
  |
  +-- verifyAndPublish     2 phút
~~~

Nếu chạy tuần tự và bỏ qua overhead, duration gần **17 phút**. Nhưng khi một Step song song với Step khác hoặc partition cùng xử lý:

~~~text
partition-1: 00:00 ------- 00:08
partition-2: 00:00 ------------- 00:12
partition-3: 00:00 ---------- 00:10
~~~

Thời gian toàn Step partitioned thường bị chi phối bởi partition chậm nhất và overhead điều phối; **không cộng 8+12+10 = 30 phút** thành wall-clock của Step. Nên theo dõi cả median/max partition duration để tìm **straggler** (partition chậm).

Khi job có luồng bất đồng bộ, đừng lấy tổng duration các Step làm tổng job duration. Tổng Step duration vẫn hữu ích như chỉ số lượng công việc, nhưng phải đặt nhãn khác như **sum of step durations** để tránh gây hiểu nhầm.

### Gắn correlation ID

Log, traces và audit nên dùng \`jobExecutionId\`, \`stepExecutionId\`, \`batchId\` để liên kết các event:

~~~text
jobExecutionId=3051 step=readAndEnrich chunk=12
chunkDurationMs=820
readerDurationMs=85
externalApiDurationMs=670
writerDurationMs=40
commitDurationMs=25
~~~

Thông số trên là ví dụ. Với lệnh gọi nhiều API trong chunk, cách đo từng lớp phải nhất quán để tránh trùng khoảng thời gian (ví dụ async API có thể chồng lấn). Các ID động nên nằm trong trace/log để truy vết; hạn chế dùng chúng làm nhãn metric tổng hợp.

## 14. Đo duration khi job bị restart

Xét một JobInstance xử lý batch \`B20261116\`:

~~~text
JobExecution #41
  STARTED 01:00
  FAILED  01:08         duration = 8 phút

Khắc phục nguồn dữ liệu:
  01:08 -> 01:30        chờ = 22 phút

JobExecution #42 (restart cùng JobInstance)
  STARTED 01:30
  COMPLETED 01:40      duration = 10 phút
~~~

Ta có ba con số khác nhau:

- **Execution duration #41:** 8 phút, trạng thái FAILED.
- **Execution duration #42:** 10 phút, trạng thái COMPLETED.
- **End-to-end elapsed của JobInstance từ lần bắt đầu tới hoàn tất:** 40 phút, bao gồm 22 phút chờ giữa các lần chạy.

Tổng thời gian hai execution đã chạy là **18 phút**, khác 40 phút end-to-end. Không ghi đè hai execution thành một duration duy nhất nếu không nói rõ cách gộp.

Trong dashboard có thể tách:

| Phạm vi | Metric | Ý nghĩa |
|---|---|---|
| JobExecution | execution duration | So hiệu suất mỗi attempt |
| JobInstance | attempts count | Nhìn số lần restart |
| JobInstance | time to final completion | Đánh giá SLA của công việc logic |
| JobInstance | total active attempt time | Đánh giá thời gian tài nguyên tham gia chạy |

Nếu có các execution STOPPED/FAILED nhưng chưa từng COMPLETED, **time to final completion chưa tồn tại**. Không lấy thời gian hiện tại làm “completed duration”; thay vào đó là **time since first attempt** hoặc **age of unresolved batch**.

## 15. Kiểm thử chức năng theo dõi duration

Một lớp monitoring cần được kiểm thử ở mức tính toán và tích hợp, nhưng kết quả kỳ vọng phải phù hợp với loại đồng hồ:

| Tình huống | Kỳ vọng |
|---|---|
| Job COMPLETED và có start/end | Có duration không âm, đúng đơn vị |
| Job FAILED nhưng đã kết thúc | Duration được ghi với status FAILED |
| Job vẫn STARTED, endTime null | Không xuất final duration; có running elapsed riêng |
| Job kết thúc gần như ngay lập tức | Duration có thể rất nhỏ, không bị làm tròn thành “không tồn tại” |
| Job bị STOPPED | Có duration của execution dừng, nhãn trạng thái đúng |
| Job restart | Hai execution được theo dõi riêng |
| Job có Step song song | Job duration không được tính bằng tổng Step duration |
| Process crash trước afterJob | Timer in-memory có thể thiếu; giám sát metadata/heartbeat phát hiện execution bất thường |
| Job khác nhau chạy đồng thời | Timer sample không bị hoán đổi |
| Metric có tag thay đổi theo execution | Không tạo time series/cardinality không kiểm soát |

### Unit test phép tính thời gian

Có thể tạo JobExecution giả lập hoặc dùng test double và gắn thời điểm cố định. Mục tiêu là kiểm tra **Duration.between** với hai mốc đã biết và xử lý null, không cần \`Thread.sleep\`.

Ví dụ với một hàm thuần:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.junit.jupiter.api.Test;

class DurationCalculationTest {

    private static Optional<Duration> calculate(
            LocalDateTime start,
            LocalDateTime end) {
        if (start == null || end == null) {
            return Optional.empty();
        }
        return Optional.of(Duration.between(start, end));
    }

    @Test
    void calculatesNinetyFiveSeconds() {
        LocalDateTime start =
                LocalDateTime.of(2026, 11, 16, 1, 0, 0);
        LocalDateTime end =
                LocalDateTime.of(2026, 11, 16, 1, 1, 35);

        assertEquals(Duration.ofSeconds(95),
                calculate(start, end).orElseThrow());
    }

    @Test
    void runningExecutionHasNoFinalDuration() {
        assertTrue(calculate(LocalDateTime.now(), null).isEmpty());
    }
}
~~~

Hàm mẫu giả định timestamp start/end đã được chuẩn hóa và end không trước start. Trong ứng dụng thật, có thể phát hiện duration âm để cảnh báo đồng hồ/metadata bất thường thay vì đưa số âm vào Timer.

### Integration test với SimpleMeterRegistry

Để kiểm tra listener ở mục 7, có thể dùng \`SimpleMeterRegistry\` của Micrometer trong test (không cần Prometheus server). Đối với một job nhỏ chạy trong test, kiểm tra Timer có **count = 1** sau khi hoàn tất và tag **status** đúng.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

// Sau khi dựng listener với registry và chạy job trong test:
Timer timer = registry.find("application.batch.job.duration")
        .tag("job", "importOrdersJob")
        .tag("status", "COMPLETED")
        .timer();

assertEquals(1L, timer.count());
~~~

Đoạn này minh họa assertion cần có sau một JobExecution đã chạy, **không phải một test class hoàn chỉnh**. Tránh assert duration bằng một giá trị thời gian tuyệt đối quá sát, vì tốc độ máy CI thay đổi. Nếu cần kiểm thử clock chính xác, truyền vào một abstraction clock hoặc kiểm thử riêng logic thuần.

Khi dùng \`SimpleMeterRegistry\`, test không chứng minh histogram Prometheus được xuất với tên phù hợp. Việc đó cần một test adapter/exporter riêng hoặc kiểm tra endpoint trong ứng dụng với cấu hình deployment.

### Kiểm thử toàn bộ pipeline giám sát

Một integration test đầy đủ có thể thực hiện:

1. Launch job có fixture nhỏ, chờ JobExecution kết thúc.
2. Đọc JobExplorer, xác nhận start/end được lưu hợp lệ.
3. Truy vấn StepExecution để xác nhận duration mỗi Step.
4. Đọc Timer theo job/status và xác nhận ít nhất một phép đo được ghi.
5. Với exporter Prometheus, kiểm tra metric/tên/tag có xuất hiện nếu feature được bật.
6. Xác minh dashboard/query chỉ dùng status COMPLETED khi tính successful duration.
7. Giả lập FAILED/STOPPED để tránh quy đồng mọi duration.

Đối với chương trình cần bảo đảm phần monitoring không cản trở batch, nên kiểm tra khi backend metrics không khả dụng hoặc registry export lỗi: job vẫn phải giữ hành vi nghiệp vụ theo policy, metric/log phải có cơ chế xử lý phù hợp.

## 16. Những sai lầm thường gặp

**Dùng CREATE_TIME thay START_TIME để đo execution duration.** CREATE_TIME có thể bao gồm thời gian trước khi job bắt đầu. Nếu cần đo start delay, đặt nó thành metric riêng.

**Tính duration hoàn tất bằng NOW() khi END_TIME chưa có.** Điều này gán thời gian tạm thời thành kết quả cuối. Dùng running elapsed và phân biệt trạng thái.

**Trộn FAILED/STOPPED với COMPLETED khi tính p95 thành công.** Một job lỗi sớm có thể làm duration trung bình trông tốt hơn, che khuất rủi ro SLA.

**Cộng Step duration để ra Job duration trong flow song song.** Các Step/partition có thể chồng lấn, nên dùng JobExecution start/end cho wall-clock.

**Cho rằng COMPLETED đồng nghĩa output READY.** Job có thể cần Step đối soát và publish riêng; deadline nghiệp vụ phải lấy từ tín hiệu output sẵn sàng theo hợp đồng.

**Đặt executionId hoặc batchId làm label Prometheus.** Mỗi lần chạy sinh thêm time series, làm tăng chi phí và giảm ổn định backend. Dùng log, trace và bảng audit cho các ID động.

**Dùng Timer sau Job để phát hiện job đang treo.** Timer chỉ có mẫu khi lời gọi kết thúc; cần running elapsed, progress và heartbeat.

**Chỉ nhìn duration mà bỏ qua volume.** Job lớn hơn đương nhiên có thể chạy lâu hơn; so throughput và cấu trúc workload để nhận diện hồi quy.

**Không quan sát retry, rollback, API latency và lock contention.** Một JobExecution chậm chỉ là triệu chứng; cần thêm timing ở Step/chunk/dependency để tìm nguyên nhân.

**Chỉ dùng metric in-memory.** Tiến trình crash có thể làm mất quan sát cuối; metadata repository và hệ thống giám sát độc lập giúp nhận biết execution bất thường.

**Không thống nhất đơn vị.** Một phần report dùng mili giây, phần khác dùng giây/phút dễ gây alert sai 1.000 lần. Đặt suffix rõ ràng, ghi đơn vị trên dashboard và cẩn trọng khi chuyển đổi.

**Đặt cảnh báo percentile khi số mẫu quá ít.** Job chạy hàng ngày chỉ có vài execution trong một tuần nên cần thêm cảnh báo deadline và phân tích từng lần chạy.

**Bỏ qua timezone và độ lệch đồng hồ.** Với JobRepository chung và nhiều worker ở các host khác nhau, clock skew làm thời gian âm hoặc tăng bất thường. Đồng bộ giờ, thống nhất lưu/hiển thị và phân biệt local time với UTC.

## 17. Quy trình triển khai thực tế

Để đưa monitoring duration vào một hệ thống Spring Batch đang vận hành:

1. **Định nghĩa duration theo nghiệp vụ:** execution time, end-to-end time tới READY, start delay và running elapsed là các metric riêng.
2. **Chọn nguồn dữ liệu:** JobRepository/JobExplorer cho lịch sử bền vững; Micrometer cho phân phối duration và dashboard realtime; scheduler/manifest cho deadline.
3. **Chuẩn hóa các chiều so sánh:** jobName ổn định, status, Step, môi trường, volume theo các thước đo cần thiết.
4. **Cấu hình instrumentation:** ưu tiên metric Spring Batch có sẵn; thêm custom Timer nếu còn thiếu và tránh label cardinality cao.
5. **Xây dashboard:** completed p50/p95/max, thất bại, running elapsed, slowest Step, read/write throughput, last READY.
6. **Đặt ngưỡng cảnh báo:** vượt duration, không có lần chạy thành công, quá hạn output, không có progress, STARTED kéo dài bất thường.
7. **Liên kết điều tra:** từ alert tới executionId trong log/traces và StepExecution trong JobRepository, rồi tới DB/API/I/O.
8. **Thử các trạng thái đặc biệt:** FAILED, STOPPED, restart, chạy song song và process crash.
9. **Theo dõi chi phí:** lưu trữ histogram, số time series, tần suất truy vấn metadata và retention của dashboard.
10. **Cập nhật baseline:** sau thay đổi volume, chunk size, partition count, schema DB hoặc năng lực dịch vụ ngoài.

Một hệ thống theo dõi tốt không dừng ở con số “job chạy mất bao lâu”. Nó cho phép biết **lần chạy nào chậm, chậm ở đâu, có ảnh hưởng deadline không, có còn tiến triển không và dữ liệu đã sẵn sàng chưa**. Khi phân biệt rõ các mốc thời gian, lưu metadata bền vững và kết hợp duration với trạng thái, tiến độ và output contract, Spring Batch có thể được vận hành và tối ưu dựa trên những bằng chứng có thể kiểm tra.
